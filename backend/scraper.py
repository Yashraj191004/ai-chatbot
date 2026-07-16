from dataclasses import dataclass
from time import sleep
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager


@dataclass
class ScrapedPage:
    url: str
    title: str
    text: str
    pdf_links: list[str]
    links: list[dict]


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


def fetch_page(url, headless=True, wait_seconds=2, manual_login=False, login_wait_seconds=90):
    """Load a page and return whatever it actually shows: title, text, links.

    No content guessing — callers (the agent or the user) decide what the
    page means. With manual_login=True a visible Chrome opens and waits so
    the user can sign in before the page is read.
    """
    driver = create_driver(headless=False if manual_login else headless)
    try:
        try:
            driver.get(url)
        except TimeoutException as exc:
            raise RuntimeError("The page took too long to load.") from exc

        if manual_login:
            sleep(max(10, min(login_wait_seconds, 300)))
        if wait_seconds:
            sleep(wait_seconds)

        title = driver.title or url
        text = driver.find_element(By.TAG_NAME, "body").text.strip()

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


@dataclass
class McqOption:
    label: str
    element_id: str


@dataclass
class McqQuestion:
    question: str
    options: list[McqOption]


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
        return input_el.find_element(By.XPATH, "./ancestor::*[self::li or self::div or self::span][1]").text.strip()
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
