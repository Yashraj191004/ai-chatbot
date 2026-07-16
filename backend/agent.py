"""Agentic loop over Ollama.

The model gets a toolbox (web search, scraping, browser control, PDF reading,
document memory, desktop control, file creation) and decides itself which
tools to call, in a loop, until it can answer.

Models with native tool support (qwen3, qwen2.5, llama3.1/3.2, mistral...)
use Ollama's /api/chat tools API. For models without it, a JSON-protocol
fallback is used so every model still works.
"""

import json
import os
import re

import requests

import tools

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300"))
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")

MAX_TOOL_ROUNDS = 8

# Fallbacks only for old Ollama versions whose /api/show has no capabilities field.
_VISION_KEYWORD_FALLBACK = ("llava", "vision", "moondream", "minicpm-v", "vl")
_TOOLS_KEYWORD_FALLBACK = ("qwen", "llama3.1", "llama3.2", "llama3.3", "mistral", "mixtral", "command-r", "granite")

_capability_cache = {}


def get_model_capabilities(model_name: str):
    """Ask Ollama what a model actually supports (vision, tools, thinking...)."""
    if model_name in _capability_cache:
        return _capability_cache[model_name]
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/show",
            json={"model": model_name},
            timeout=5,
        )
        response.raise_for_status()
        capabilities = response.json().get("capabilities")
    except requests.RequestException:
        return None  # Ollama unreachable: do not cache, retry next time
    _capability_cache[model_name] = capabilities
    return capabilities


def is_vision_model(model_name: str):
    capabilities = get_model_capabilities(model_name)
    if capabilities is not None:
        return "vision" in capabilities
    lowered = model_name.lower()
    return any(keyword in lowered for keyword in _VISION_KEYWORD_FALLBACK)


def likely_supports_tools(model_name: str):
    capabilities = get_model_capabilities(model_name)
    if capabilities is not None:
        return "tools" in capabilities
    lowered = model_name.lower()
    return any(keyword in lowered for keyword in _TOOLS_KEYWORD_FALLBACK)


def fetch_installed_ollama_models(timeout=3):
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout)
    response.raise_for_status()
    models = []
    for model in response.json().get("models", []):
        name = model.get("name")
        if not name:
            continue
        models.append({
            "name": name,
            "size": model.get("size"),
            "modified_at": model.get("modified_at"),
            "details": model.get("details") or {},
        })
    return sorted(models, key=lambda item: item["name"].lower())


def ollama_error_detail(response):
    if response is None:
        return ""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("error") or payload.get("detail")
        if detail:
            return str(detail).strip()
    return (response.text or "").strip()


def summarize_content(text: str, label: str, model: str):
    """Ask the model for a real summary of an uploaded/scraped document."""
    prompt = (
        f"The user just added a document called '{label}' to the chat. "
        "Summarize it in a few short sentences: what it is, the key points, and any "
        "deadlines, questions, or requirements it contains. Then say you're ready for questions about it.\n\n"
        f"Document text (may be truncated):\n{text[:8000]}"
    )
    try:
        response = requests.post(
            OLLAMA_GENERATE_URL,
            json={"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 400}},
            timeout=(10, OLLAMA_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        summary = response.json().get("response", "").strip()
        summary = strip_thinking(summary)
        if summary:
            return summary
    except requests.RequestException:
        pass
    words = len(text.split())
    return (
        f"I saved {label} to this chat's memory ({words} words), but I could not reach the model "
        "to summarize it — make sure Ollama is running, then ask me about it."
    )


def strip_thinking(text: str):
    """Remove <think>...</think> blocks that reasoning models emit."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


# ---------------------------------------------------------------------------
# Tool schemas (Ollama /api/chat "tools" format)
# ---------------------------------------------------------------------------

def _tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
            },
        },
    }


TOOLS = [
    _tool(
        "web_search",
        "Search the web and get titles, URLs and snippets of the top results. Use for current information, facts you are unsure about, or finding pages.",
        {"query": {"type": "string", "description": "The search query"}},
        ["query"],
    ),
    _tool(
        "fetch_webpage",
        "Download and read a public webpage (no login) headlessly. Returns the page text and links, and saves it to chat memory.",
        {"url": {"type": "string", "description": "Full URL of the page to read"}},
        ["url"],
    ),
    _tool(
        "read_pdf",
        "Download a PDF from a URL, extract its text, and save it to chat memory.",
        {"url": {"type": "string", "description": "Direct URL of the PDF"}},
        ["url"],
    ),
    _tool(
        "search_documents",
        "Semantically search everything saved in this chat's memory: uploaded files (PDF/DOCX/XLSX/images), scraped pages, and browser reads. Always use this when the user asks about their uploaded or scraped content.",
        {"query": {"type": "string", "description": "What to look for"}},
        ["query"],
    ),
    _tool(
        "list_documents",
        "List the names of all documents saved in this chat's memory.",
    ),
    _tool(
        "open_browser",
        "Open a visible Chrome window on the user's screen at a URL. Use when the page needs login (Canvas, Classroom, portals) or the user wants to see/interact with it. The user can log in and navigate; afterwards use read_browser_page.",
        {"url": {"type": "string", "description": "URL or site to open"}},
        ["url"],
    ),
    _tool(
        "read_browser_page",
        "Read the text and links of whatever page is currently shown in the visible Chrome window, and save it to chat memory.",
    ),
    _tool(
        "browser_navigate",
        "Navigate the already-open visible Chrome window to a different URL.",
        {"url": {"type": "string", "description": "URL to navigate to"}},
        ["url"],
    ),
    _tool("close_browser", "Close the visible Chrome window for this chat."),
    _tool(
        "read_quiz_questions",
        "Extract visible multiple-choice questions (radio buttons/checkboxes) from the open browser page.",
    ),
    _tool(
        "select_quiz_answers",
        "Click chosen answer options on the open quiz page. Never submits the quiz — the user reviews and submits.",
        {
            "answers": {
                "type": "array",
                "description": 'List like [{"question": 1, "choice": "A"}]',
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "integer"},
                        "choice": {"type": "string"},
                    },
                },
            }
        },
        ["answers"],
    ),
    _tool(
        "open_app",
        "Open an application on the user's Windows PC (word, excel, powerpoint, notepad, calculator, chrome, vscode, camera, settings...). The opened app becomes the focused window.",
        {"name": {"type": "string", "description": "App name to open"}},
        ["name"],
    ),
    _tool(
        "type_text",
        "Paste text into the currently focused window/app on the user's PC (e.g. into Word or Notepad after opening it). Write the full final text yourself.",
        {"text": {"type": "string", "description": "The exact text to type/paste"}},
        ["text"],
    ),
    _tool(
        "send_keys",
        "Send keyboard shortcuts to the focused window using SendKeys syntax: ^s save, ^c copy, ^v paste, ^z undo, {ENTER}, {TAB}, {ESC}, %{F4} close window.",
        {"keys": {"type": "string", "description": "SendKeys sequence, e.g. ^s or {ENTER}"}},
        ["keys"],
    ),
    _tool(
        "create_file",
        "Create a downloadable file (docx, xlsx, pptx, or txt) with content you write. For xlsx, separate columns with | or tabs, one row per line. For pptx, separate slides with blank lines (first line = slide title).",
        {
            "file_type": {"type": "string", "description": "docx, xlsx, pptx, or txt"},
            "title": {"type": "string", "description": "Document title / filename base"},
            "content": {"type": "string", "description": "The complete, polished content of the file"},
        },
        ["file_type", "title", "content"],
    ),
]


def execute_tool(db, chat_id, name, args):
    """Dispatch one tool call. Returns a string result (errors become strings too)."""
    try:
        if name == "web_search":
            return tools.web_search(str(args.get("query", "")))
        if name == "fetch_webpage":
            return tools.fetch_webpage(db, chat_id, str(args.get("url", "")))
        if name == "read_pdf":
            return tools.read_pdf_url(db, chat_id, str(args.get("url", "")))
        if name == "search_documents":
            return tools.search_chat_documents(db, chat_id, str(args.get("query", "")))
        if name == "list_documents":
            names = tools.list_chat_documents(db, chat_id)
            return "Documents in this chat:\n" + "\n".join(f"- {n}" for n in names) if names else "No documents saved in this chat yet."
        if name == "open_browser":
            return tools.open_browser(chat_id, str(args.get("url", "")))
        if name == "read_browser_page":
            return tools.read_browser_page(db, chat_id)
        if name == "browser_navigate":
            return tools.browser_navigate(chat_id, str(args.get("url", "")))
        if name == "close_browser":
            return tools.close_browser(chat_id)
        if name == "read_quiz_questions":
            return tools.read_quiz_questions(chat_id)
        if name == "select_quiz_answers":
            answers = args.get("answers", [])
            if isinstance(answers, str):
                try:
                    answers = json.loads(answers)
                except json.JSONDecodeError:
                    return 'Could not parse answers. Pass a list like [{"question": 1, "choice": "A"}].'
            return tools.select_quiz_answers(chat_id, answers)
        if name == "open_app":
            return tools.open_app(chat_id, str(args.get("name", "")))
        if name == "type_text":
            return tools.type_text(str(args.get("text", "")))
        if name == "send_keys":
            return tools.send_keys(str(args.get("keys", "")))
        if name == "create_file":
            return tools.create_file(
                str(args.get("file_type", "docx")),
                str(args.get("title", "Assistant Output")),
                str(args.get("content", "")),
            )
        return f"Unknown tool: {name}"
    except Exception as exc:
        return f"Tool {name} failed: {exc}"


def describe_tool_call(name, args):
    """Short human-readable status line shown live in the UI."""
    arg = args.get("query") or args.get("url") or args.get("name") or args.get("title") or args.get("keys") or ""
    labels = {
        "web_search": "Searching the web",
        "fetch_webpage": "Reading webpage",
        "read_pdf": "Reading PDF",
        "search_documents": "Searching your documents",
        "list_documents": "Listing your documents",
        "open_browser": "Opening browser",
        "read_browser_page": "Reading the open browser page",
        "browser_navigate": "Navigating browser",
        "close_browser": "Closing browser",
        "read_quiz_questions": "Reading quiz questions",
        "select_quiz_answers": "Clicking answer choices",
        "open_app": "Opening app",
        "type_text": "Typing into the focused app",
        "send_keys": "Pressing keys",
        "create_file": "Creating file",
    }
    label = labels.get(name, f"Running {name}")
    return f"{label}: {arg}" if arg else label


def build_system_prompt(db, chat_id):
    doc_names = tools.list_chat_documents(db, chat_id)
    doc_note = (
        "Documents saved in this chat's memory: " + ", ".join(doc_names[:15])
        if doc_names
        else "No documents are saved in this chat yet."
    )
    return f"""You are JARVIS, a capable local AI assistant running on the user's own PC. You work like an autonomous agent: you have tools and you decide when to use them.

Principles:
- Answer directly from knowledge when you can. Use tools when you need current information, page content, the user's documents, or to act on their PC.
- When the user asks about an uploaded file, scraped page, or "the document/assignment", ALWAYS call search_documents first — never guess its contents.
- For questions about current events, prices, versions, or anything you are unsure of, use web_search, then fetch_webpage on the best result.
- For pages that need login (Canvas, Google Classroom, portals), use open_browser so the user can log in, then read_browser_page.
- Chain tools across multiple steps when needed (search → fetch → answer; open app → type_text).
- When creating files or typing into apps, write complete polished content yourself — never placeholders or templates unless asked.
- Never submit quizzes, forms, or applications; prepare everything and let the user do the final action. Say so when relevant.
- Be honest about what you did: only claim actions your tools actually performed.
- Respond in clear, concise language. Do not mention tool names to the user; describe what you did naturally.

{doc_note}"""


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def run_agent(db, chat_id, user_message, model, history, image_payloads=None):
    """Generator yielding event dicts:
    {"type": "status", "text": ...}   — a tool is being used
    {"type": "token", "text": ...}    — a piece of the final answer
    {"type": "error", "text": ...}
    """
    messages = [{"role": "system", "content": build_system_prompt(db, chat_id)}]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    user_entry = {"role": "user", "content": user_message}
    if image_payloads:
        user_entry["images"] = image_payloads
    messages.append(user_entry)

    use_native_tools = True

    for round_index in range(MAX_TOOL_ROUNDS + 1):
        final_round = round_index == MAX_TOOL_ROUNDS
        if final_round:
            messages.append({
                "role": "user",
                "content": "Stop using tools now and give your best final answer from what you have gathered.",
            })

        if use_native_tools and not final_round:
            try:
                content, tool_calls, streamed = yield from _chat_round(model, messages, TOOLS)
            except ToolsUnsupportedError:
                use_native_tools = False
                yield from _run_json_fallback(db, chat_id, user_message, model, messages)
                return
            except requests.RequestException as exc:
                yield {"type": "error", "text": _friendly_ollama_error(exc, model)}
                return
        else:
            try:
                content, tool_calls, streamed = yield from _chat_round(model, messages, None)
            except requests.RequestException as exc:
                yield {"type": "error", "text": _friendly_ollama_error(exc, model)}
                return

        if not tool_calls:
            if not streamed and content:
                yield {"type": "token", "text": content}
            if not content:
                yield {"type": "token", "text": "I could not produce an answer. Try rephrasing or another model."}
            return

        messages.append({"role": "assistant", "content": content or "", "tool_calls": tool_calls})
        for call in tool_calls:
            function = call.get("function", {})
            name = function.get("name", "")
            args = function.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}

            yield {"type": "status", "text": describe_tool_call(name, args)}
            result = execute_tool(db, chat_id, name, args)
            messages.append({"role": "tool", "content": str(result)})


class ToolsUnsupportedError(Exception):
    pass


def _chat_round(model, messages, tool_schemas):
    """One streaming /api/chat call. Yields token events for content as it
    arrives (when no tool call has appeared) and returns (content, tool_calls,
    streamed) via StopIteration value."""
    payload = {"model": model, "messages": messages, "stream": True}
    if tool_schemas:
        payload["tools"] = tool_schemas

    response = requests.post(
        OLLAMA_CHAT_URL,
        json=payload,
        stream=True,
        timeout=(10, OLLAMA_TIMEOUT_SECONDS),
    )
    if response.status_code == 400 and "does not support tools" in (response.text or ""):
        raise ToolsUnsupportedError()
    response.raise_for_status()

    content = ""
    tool_calls = []
    streamed = False
    in_think = False

    for line in response.iter_lines():
        if not line:
            continue
        chunk = json.loads(line.decode("utf-8"))
        message = chunk.get("message", {})

        for call in message.get("tool_calls") or []:
            tool_calls.append(call)

        token = message.get("content", "")
        if token:
            content += token
            # Hide <think> blocks from reasoning models (qwen3 etc.).
            if "<think>" in token:
                in_think = True
            if not in_think and not tool_calls:
                yield {"type": "token", "text": token}
                streamed = True
            if "</think>" in token:
                in_think = False

        if chunk.get("done"):
            break

    content = strip_thinking(content)
    if streamed and tool_calls:
        # Some content leaked out before a tool call appeared; the frontend
        # will replace it once the final answer streams.
        streamed = False
    return content, tool_calls, streamed


def _friendly_ollama_error(exc, model):
    if isinstance(exc, requests.ConnectionError):
        return "Ollama is offline. Start Ollama, then try again."
    if isinstance(exc, requests.Timeout):
        return f"`{model}` took too long to respond. Try again or use a smaller model."
    if isinstance(exc, requests.HTTPError):
        detail = ollama_error_detail(exc.response)
        return f"Ollama returned an error for `{model}`." + (f" {detail}" if detail else "")
    return f"Could not reach `{model}` through Ollama: {exc}"


# ---------------------------------------------------------------------------
# JSON-protocol fallback for models without native tool support
# ---------------------------------------------------------------------------

FALLBACK_INSTRUCTIONS = """
You can use tools by replying with ONLY a JSON object (no other text):
{"tool": "<tool_name>", "args": {...}}

Available tools:
- web_search {"query": "..."} — search the web
- fetch_webpage {"url": "..."} — read a public webpage
- read_pdf {"url": "..."} — read a PDF from a URL
- search_documents {"query": "..."} — search files/pages saved in this chat
- list_documents {} — list saved documents
- open_browser {"url": "..."} — open a visible Chrome window (for login pages)
- read_browser_page {} — read the open Chrome page
- browser_navigate {"url": "..."} — navigate the open Chrome window
- close_browser {} — close the Chrome window
- read_quiz_questions {} — extract MCQs from the open page
- select_quiz_answers {"answers": [{"question": 1, "choice": "A"}]} — click choices (never submits)
- open_app {"name": "..."} — open a Windows app (word, notepad, calculator...)
- type_text {"text": "..."} — paste text into the focused app
- send_keys {"keys": "..."} — send shortcuts (^s, {ENTER}, ...)
- create_file {"file_type": "docx|xlsx|pptx|txt", "title": "...", "content": "..."} — create a downloadable file

After each tool result you may call another tool or give the final answer as normal text.
If no tool is needed, just answer normally.
"""


def _run_json_fallback(db, chat_id, user_message, model, base_messages):
    messages = list(base_messages)
    messages[0] = {"role": "system", "content": messages[0]["content"] + "\n" + FALLBACK_INSTRUCTIONS}

    for round_index in range(MAX_TOOL_ROUNDS):
        try:
            response = requests.post(
                OLLAMA_CHAT_URL,
                json={"model": model, "messages": messages, "stream": False},
                timeout=(10, OLLAMA_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            yield {"type": "error", "text": _friendly_ollama_error(exc, model)}
            return

        content = strip_thinking(response.json().get("message", {}).get("content", "").strip())
        call = _parse_json_tool_call(content)
        if not call:
            yield {"type": "token", "text": content or "I could not produce an answer."}
            return

        name, args = call
        yield {"type": "status", "text": describe_tool_call(name, args)}
        result = execute_tool(db, chat_id, name, args)
        messages.append({"role": "assistant", "content": content})
        messages.append({
            "role": "user",
            "content": f"TOOL RESULT ({name}):\n{result}\n\nContinue. Call another tool if needed, otherwise give the final answer as plain text.",
        })

    yield {"type": "token", "text": "I used the maximum number of tool steps without finishing. Here is what I have so far — ask me to continue if needed."}


def _parse_json_tool_call(content):
    match = re.search(r"\{.*\}", content, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "tool" not in data:
        return None
    return str(data["tool"]), data.get("args") or {}
