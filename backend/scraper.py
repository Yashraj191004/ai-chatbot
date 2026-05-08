from dataclasses import dataclass
from datetime import datetime
from time import sleep
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class Assignment:
    title: str
    due_date: str | None = None
    source_url: str | None = None
    scraped_at: str = datetime.utcnow().isoformat()


@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str
    pdf_links: list[str]
    links: list[dict]


@dataclass
class McqOption:
    label: str
    element_id: str


@dataclass
class McqQuestion:
    question: str
    options: list[McqOption]


def create_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--no-sandbox")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)
    return driver


def extract_mcq_questions(driver):
    grouped = {}
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
    for index, input_el in enumerate(inputs):
        if not input_el.is_displayed() or not input_el.is_enabled():
            continue

        group_key = (
            input_el.get_attribute("name")
            or input_el.get_attribute("aria-labelledby")
            or f"question-{index}"
        )
        option_label = _input_label_text(driver, input_el)
        question_text = _question_text(input_el, option_label)
        grouped.setdefault(group_key, {
            "question": question_text,
            "options": [],
        })
        grouped[group_key]["options"].append(McqOption(
            label=option_label or f"Option {len(grouped[group_key]['options']) + 1}",
            element_id=input_el.id,
        ))

    questions = []
    for group in grouped.values():
        if len(group["options"]) < 2:
            continue
        question_text = group["question"] or "Question"
        questions.append(McqQuestion(
            question=question_text[:1000],
            options=group["options"],
        ))
    return questions


def _input_label_text(driver, input_el):
    element_id = input_el.get_attribute("id")
    if element_id:
        labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{element_id}']")
        for label in labels:
            text = label.text.strip()
            if text:
                return text

    try:
        label = input_el.find_element(By.XPATH, "./ancestor::label[1]")
        text = label.text.strip()
        if text:
            return text
    except Exception:
        pass

    aria = input_el.get_attribute("aria-label")
    if aria:
        return aria.strip()

    try:
        parent_text = input_el.find_element(By.XPATH, "./ancestor::*[self::li or self::div or self::span][1]").text.strip()
        return parent_text
    except Exception:
        return ""


def _question_text(input_el, option_label):
    try:
        legend = input_el.find_element(By.XPATH, "./ancestor::fieldset[1]//legend")
        text = legend.text.strip()
        if text:
            return text
    except Exception:
        pass

    try:
        container = input_el.find_element(By.XPATH, "./ancestor::*[self::fieldset or self::li or self::div][contains(@class,'question') or contains(@class,'quiz') or contains(@class,'item')][1]")
    except Exception:
        try:
            container = input_el.find_element(By.XPATH, "./ancestor::*[self::fieldset or self::li or self::div][1]")
        except Exception:
            return ""

    text = container.text.strip()
    if option_label and text.endswith(option_label):
        text = text[: -len(option_label)].strip()
    return text


def scrape_assignment_cards(
    url,
    card_selector,
    title_selector,
    due_selector=None,
    wait_selector=None,
    headless=True,
):
    """
    Generic Selenium scraper for LMS assignment pages.

    Pass CSS selectors for the assignment card, title, and optional due date.
    For sites requiring login, open with headless=False and log in manually,
    or adapt this helper with your school's specific login steps.
    """
    driver = create_driver(headless=headless)
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector or card_selector)))

        assignments = []
        for card in driver.find_elements(By.CSS_SELECTOR, card_selector):
            title = _safe_text(card, title_selector)
            if not title:
                continue
            assignments.append(
                Assignment(
                    title=title,
                    due_date=_safe_text(card, due_selector) if due_selector else None,
                    source_url=url,
                )
            )
        return assignments
    finally:
        driver.quit()


def scrape_assignment_page(url, headless=True, wait_seconds=2, manual_login=False, login_wait_seconds=90):
    """
    Scrape visible assignment page text and discover PDF links.

    For LMS pages that require login/MFA, use headless=False. Selenium will open
    Chrome, you can log in manually, and the scraper will read the page after
    wait_seconds.
    """
    driver = create_driver(headless=False if manual_login else headless)
    try:
        try:
            driver.get(url)
        except TimeoutException as exc:
            raise RuntimeError("The assignment page took too long to load.") from exc

        if manual_login:
            sleep(max(10, min(login_wait_seconds, 300)))

        if wait_seconds:
            sleep(wait_seconds)

        title = driver.title or "Assignment page"
        text = driver.find_element(By.TAG_NAME, "body").text.strip()
        lower_text = text.lower()
        lower_title = title.lower()

        login_signals = [
            "log in",
            "login",
            "sign in",
            "canvas login",
            "instructure",
            "username",
            "password",
            "single sign-on",
            "duo",
        ]
        if not manual_login and any(signal in lower_text for signal in login_signals) and (
            "assignment" not in lower_text or "login" in lower_title or "sign in" in lower_title
        ):
            raise RuntimeError(
                "This page appears to require login. Try again using login-required mode so a visible browser can open for you to sign in."
            )

        if len(text.split()) < 20:
            raise RuntimeError("I could not find enough readable assignment text on that page.")

        pdf_links = []
        links = []

        for link in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
            href = link.get_attribute("href")
            if not href:
                continue

            absolute_url = urljoin(url, href)
            label = link.text.strip() or link.get_attribute("aria-label") or absolute_url
            lower_href = absolute_url.lower()
            if ".pdf" in lower_href:
                link_type = "pdf"
                pdf_links.append(absolute_url)
            elif any(ext in lower_href for ext in [".docx", ".xlsx", ".pptx", ".csv", ".zip"]):
                link_type = "file"
            else:
                link_type = "web"

            links.append({
                "label": label[:160],
                "url": absolute_url,
                "type": link_type,
            })

        return ScrapedPage(
            url=url,
            title=title,
            text=text,
            pdf_links=sorted(set(pdf_links)),
            links=_dedupe_links(links),
        )
    finally:
        driver.quit()


def _safe_text(root, selector):
    try:
        return root.find_element(By.CSS_SELECTOR, selector).text.strip()
    except Exception:
        return None


def _dedupe_links(links):
    seen = set()
    unique = []
    for link in links:
        url = link["url"]
        if url in seen:
            continue
        seen.add(url)
        unique.append(link)
    return unique[:50]
