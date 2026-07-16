from uuid import uuid4
import json
import os
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session

import agent
import tools
from auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from database import Base, SessionLocal, engine
from models import Chat, DocumentChunk, ImageAttachment, Message, User
from scraper import scrape_assignment_page

load_dotenv()

app = FastAPI()
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

PASSWORD_RESET_TOKENS = {}
PASSWORD_RESET_CODES = {}
OAUTH_STATES = {}
PASSWORD_RESET_EXPIRE_MINUTES = 20
RESET_CODE_EXPIRE_MINUTES = 10
OAUTH_STATE_EXPIRE_MINUTES = 10
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://127.0.0.1:8000")
OAUTH_PROVIDERS = {
    "google": {
        "client_id_env": "GOOGLE_CLIENT_ID",
        "client_secret_env": "GOOGLE_CLIENT_SECRET",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "scope": "openid email profile",
    },
}

MODEL_ALIASES = {
    "llama3": "llama3:latest",
    "llama3.1": "llama3.1:latest",
    "llava": "llava:latest",
    "qwen3": "qwen3:8b",
    "qwen2.5vl": "qwen2.5vl:7b",
    "llama3.2-vision": "llama3.2-vision:latest",
}

HISTORY_MESSAGE_LIMIT = 12


class AuthRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ResetCodeRequest(BaseModel):
    email: str
    code: str


class ChangePasswordRequest(BaseModel):
    email: str
    reset_token: str
    password: str


class StreamRequest(BaseModel):
    chat_id: str
    message: str
    model: str | None = None


class RenameRequest(BaseModel):
    title: str


class ScrapeRequest(BaseModel):
    url: str
    headless: bool = True
    wait_seconds: int = 2
    include_pdfs: bool = True
    manual_login: bool = False
    login_wait_seconds: int = 90
    model: str | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def mask_email(email: str):
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        masked_name = name[:1] + "*"
    else:
        masked_name = f"{name[:2]}{'*' * min(5, len(name) - 2)}"
    return f"{masked_name}@{domain}"


def email_configured():
    return bool(os.getenv("RESEND_API_KEY") and os.getenv("EMAIL_FROM"))


def reset_code_email_content(code: str):
    text = (
        f"Use this code to reset your Study Assistant password: {code}\n\n"
        f"This code expires in {RESET_CODE_EXPIRE_MINUTES} minutes. If you did not request it, you can ignore this email."
    )
    html = f"""
        <div style="font-family:Arial,sans-serif;max-width:560px;color:#111827">
          <h2>Reset your password</h2>
          <p>Use this code to reset your Study Assistant password:</p>
          <div style="font-size:28px;font-weight:700;letter-spacing:6px;padding:14px 18px;background:#f3f4f6;border-radius:8px;display:inline-block">{code}</div>
          <p style="color:#667085">This code expires in {RESET_CODE_EXPIRE_MINUTES} minutes. If you did not request it, you can ignore this email.</p>
        </div>
        """
    return text, html


def send_reset_code_email(email: str, code: str):
    if not email_configured():
        raise RuntimeError("Email is not configured. Set RESEND_API_KEY and EMAIL_FROM.")

    text, html = reset_code_email_content(code)
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
            "Content-Type": "application/json",
        },
        json={
            "from": os.getenv("EMAIL_FROM"),
            "to": [email],
            "subject": "Your Study Assistant password reset code",
            "text": text,
            "html": html,
        },
        timeout=20,
    )
    response.raise_for_status()


def create_reset_code(email: str):
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    PASSWORD_RESET_CODES[email] = {
        "code": code,
        "expires_at": datetime.utcnow() + timedelta(minutes=RESET_CODE_EXPIRE_MINUTES),
        "attempts": 0,
        "verified": False,
    }
    return code


def oauth_redirect_uri(provider: str):
    return f"{BACKEND_PUBLIC_URL}/oauth/{provider}/callback"


def get_or_create_oauth_user(db: Session, email: str):
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        db_user = User(id=str(uuid4()), email=email, password=hash_password(secrets.token_urlsafe(24)))
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
    return db_user


def oauth_success_page(access_token: str, refresh_token: str):
    return HTMLResponse(f"""
    <!doctype html>
    <html>
      <body>
        <script>
          localStorage.setItem("token", {json.dumps(access_token)});
          localStorage.setItem("refresh_token", {json.dumps(refresh_token)});
          window.location.replace({json.dumps(FRONTEND_URL)});
        </script>
        Signing you in...
      </body>
    </html>
    """)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    data = decode_token(credentials.credentials)
    if not data or data.get("type") != "access":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return data["user"]


def get_current_user_optional(
    token: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
):
    raw_token = token or (credentials.credentials if credentials else None)
    data = decode_token(raw_token) if raw_token else None
    if not data or data.get("type") != "access":
        raise HTTPException(status_code=401, detail="Unauthorized")
    return data["user"]


def get_owned_chat(chat_id: str, user: str, db: Session):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


def normalize_model_name(model_name: str | None):
    selected = model_name or agent.DEFAULT_OLLAMA_MODEL
    return MODEL_ALIASES.get(selected, selected)


def resolve_model(model_name: str | None, installed_model_names):
    """Pick the requested model if installed, otherwise fall back sensibly."""
    selected = normalize_model_name(model_name)
    if selected in installed_model_names:
        return selected
    prefix_match = next(
        (name for name in installed_model_names if name.startswith(selected.split(":")[0])),
        None,
    )
    if prefix_match:
        return prefix_match
    if agent.DEFAULT_OLLAMA_MODEL in installed_model_names:
        return agent.DEFAULT_OLLAMA_MODEL
    return next(iter(sorted(installed_model_names)), selected)


def save_message_pair(db: Session, chat_id: str, user_text: str, assistant_text: str):
    db.add_all([
        Message(id=str(uuid4()), chat_id=chat_id, role="user", content=user_text),
        Message(id=str(uuid4()), chat_id=chat_id, role="assistant", content=assistant_text),
    ])
    db.commit()


# ---------------------------------------------------------------------------
# Health / models / files
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/models")
def models():
    try:
        installed_models = agent.fetch_installed_ollama_models()
        model_names = [model["name"] for model in installed_models]
    except requests.RequestException:
        model_names = []

    return {"default": agent.DEFAULT_OLLAMA_MODEL, "models": model_names}


@app.get("/models/status")
def model_status():
    try:
        installed_models = agent.fetch_installed_ollama_models()
    except requests.RequestException:
        return {
            "ollama": "offline",
            "default": agent.DEFAULT_OLLAMA_MODEL,
            "models": {},
        }

    statuses = {
        model["name"]: {
            "available": True,
            "status": "active",
            "vision": agent.is_vision_model(model["name"]),
            "tools": agent.likely_supports_tools(model["name"]),
            "size": model.get("size"),
            "modified_at": model.get("modified_at"),
            "family": (model.get("details") or {}).get("family"),
        }
        for model in installed_models
    }

    if agent.DEFAULT_OLLAMA_MODEL in statuses or not statuses:
        default_model = agent.DEFAULT_OLLAMA_MODEL
    else:
        default_model = next(
            (name for name in statuses if name.startswith(agent.DEFAULT_OLLAMA_MODEL.split(":")[0])),
            next(iter(statuses)),
        )

    return {"ollama": "online", "default": default_model, "models": statuses}


@app.get("/capabilities")
def capabilities():
    return {
        "agent": [
            "the model decides when to use tools (no keyword commands needed)",
            "multi-step tool chains: search, fetch, read, act, answer",
        ],
        "tools": [tool["function"]["name"] for tool in agent.TOOLS],
        "files": ["PDF", "DOCX", "XLSX", "TXT/CSV/MD", "image OCR", "vision model support"],
        "safety": [
            "never submits quizzes/forms automatically",
            "typed/pasted drafts are left for user review",
        ],
    }


@app.get("/generated-files")
def generated_files(user=Depends(get_current_user)):
    tools.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for path in sorted(tools.GENERATED_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
        if path.is_file():
            stat = path.stat()
            files.append({
                "name": path.name,
                "size": stat.st_size,
                "url": tools.generated_file_url(path),
            })
    return files[:50]


@app.get("/generated/{filename}")
def download_generated_file(filename: str, user=Depends(get_current_user_optional)):
    from pathlib import Path

    safe_name = Path(filename).name
    path = (tools.GENERATED_DIR / safe_name).resolve()
    root = tools.GENERATED_DIR.resolve()
    if root not in path.parents or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Generated file not found")
    return FileResponse(path, filename=path.name)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/signup")
def signup(user: AuthRequest, db: Session = Depends(get_db)):
    email = user.email.lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    new_user = User(id=str(uuid4()), email=email, password=hash_password(user.password))
    db.add(new_user)
    db.commit()
    return {"msg": "user created"}


@app.post("/login")
def login(user: AuthRequest, db: Session = Depends(get_db)):
    email = user.email.lower()
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user or not db_user.password or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "access_token": create_access_token({"user": db_user.email}),
        "refresh_token": create_refresh_token({"user": db_user.email}),
    }


@app.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = data.email.lower().strip()
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Account does not exist")
    return {
        "msg": "Account found",
        "email": db_user.email,
        "masked_email": mask_email(db_user.email),
    }


@app.post("/send-reset-code")
def send_reset_code(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    email = data.email.lower().strip()
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Account does not exist")

    code = create_reset_code(db_user.email)
    try:
        send_reset_code_email(db_user.email, code)
    except RuntimeError as exc:
        PASSWORD_RESET_CODES.pop(db_user.email, None)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        PASSWORD_RESET_CODES.pop(db_user.email, None)
        raise HTTPException(status_code=502, detail="Could not send reset email. Check Resend settings.") from exc

    return {
        "msg": "Email reset code has been sent to your email",
        "masked_email": mask_email(db_user.email),
        "expires_minutes": RESET_CODE_EXPIRE_MINUTES,
    }


@app.post("/verify-reset-code")
def verify_reset_code(data: ResetCodeRequest, db: Session = Depends(get_db)):
    email = data.email.lower().strip()
    reset = PASSWORD_RESET_CODES.get(email)
    if not reset or reset["expires_at"] < datetime.utcnow():
        PASSWORD_RESET_CODES.pop(email, None)
        raise HTTPException(status_code=400, detail="Reset code is invalid or expired")

    reset["attempts"] += 1
    if reset["attempts"] > 5:
        PASSWORD_RESET_CODES.pop(email, None)
        raise HTTPException(status_code=429, detail="Too many attempts. Request a new code.")

    if reset["code"] != data.code.strip():
        raise HTTPException(status_code=400, detail="Verification code is wrong")

    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Account not found")

    token = secrets.token_urlsafe(32)
    PASSWORD_RESET_TOKENS[token] = {
        "email": email,
        "expires_at": datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_EXPIRE_MINUTES),
    }
    reset["verified"] = True
    return {"msg": "ok", "reset_token": token}


@app.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    reset = PASSWORD_RESET_TOKENS.get(data.token)
    if not reset or reset["expires_at"] < datetime.utcnow():
        PASSWORD_RESET_TOKENS.pop(data.token, None)
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired")

    password = data.password.strip()
    if len(password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    db_user = db.query(User).filter(User.email == reset["email"]).first()
    if not db_user:
        PASSWORD_RESET_TOKENS.pop(data.token, None)
        raise HTTPException(status_code=404, detail="Account not found")

    db_user.password = hash_password(password)
    db.commit()
    PASSWORD_RESET_TOKENS.pop(data.token, None)
    return {"msg": "Password updated"}


@app.post("/change-password")
def change_password(data: ChangePasswordRequest, db: Session = Depends(get_db)):
    reset = PASSWORD_RESET_TOKENS.get(data.reset_token)
    email = data.email.lower().strip()
    if not reset or reset["email"] != email or reset["expires_at"] < datetime.utcnow():
        PASSWORD_RESET_TOKENS.pop(data.reset_token, None)
        raise HTTPException(status_code=400, detail="Password reset session is invalid or expired")

    password = data.password.strip()
    if len(password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="Account not found")

    db_user.password = hash_password(password)
    db.commit()
    PASSWORD_RESET_TOKENS.pop(data.reset_token, None)
    PASSWORD_RESET_CODES.pop(email, None)
    return {"msg": "ok"}


@app.get("/oauth/{provider}/start")
def oauth_start(provider: str):
    provider = provider.lower()
    config = OAUTH_PROVIDERS.get(provider)
    if not config:
        raise HTTPException(status_code=404, detail="Unsupported login provider")

    client_id = os.getenv(config["client_id_env"])
    if not client_id or not os.getenv(config["client_secret_env"]):
        raise HTTPException(status_code=503, detail=f"{provider.title()} login is not configured")

    state = secrets.token_urlsafe(24)
    OAUTH_STATES[state] = {
        "provider": provider,
        "expires_at": datetime.utcnow() + timedelta(minutes=OAUTH_STATE_EXPIRE_MINUTES),
    }
    params = {
        "client_id": client_id,
        "redirect_uri": oauth_redirect_uri(provider),
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "offline"
        params["prompt"] = "select_account"
    return RedirectResponse(f"{config['authorize_url']}?{urlencode(params)}")


@app.get("/oauth/{provider}/callback")
def oauth_callback(provider: str, code: str | None = None, state: str | None = None, db: Session = Depends(get_db)):
    provider = provider.lower()
    config = OAUTH_PROVIDERS.get(provider)
    state_data = OAUTH_STATES.pop(state or "", None)
    if not config or not code or not state_data or state_data["provider"] != provider:
        raise HTTPException(status_code=400, detail="Invalid login response")
    if state_data["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Login session expired")

    token_res = requests.post(
        config["token_url"],
        data={
            "client_id": os.getenv(config["client_id_env"]),
            "client_secret": os.getenv(config["client_secret_env"]),
            "code": code,
            "redirect_uri": oauth_redirect_uri(provider),
            "grant_type": "authorization_code",
        },
        headers={"Accept": "application/json"},
        timeout=20,
    )
    token_res.raise_for_status()
    access_token = token_res.json().get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Provider did not return an access token")

    user_res = requests.get(
        config["userinfo_url"],
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=20,
    )
    user_res.raise_for_status()
    email = user_res.json().get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Provider account did not include a verified email")

    db_user = get_or_create_oauth_user(db, email.lower())
    return oauth_success_page(
        create_access_token({"user": db_user.email}),
        create_refresh_token({"user": db_user.email}),
    )


@app.post("/refresh")
def refresh(credentials: HTTPAuthorizationCredentials = Depends(security)):
    data = decode_token(credentials.credentials)
    if not data or data.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return {"access_token": create_access_token({"user": data["user"]})}


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

@app.post("/chat/create")
def create_chat(user=Depends(get_current_user), db: Session = Depends(get_db)):
    chat = Chat(id=str(uuid4()), title="New Chat", user_id=user)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@app.get("/chats")
def get_chats(user=Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Chat).filter(Chat.user_id == user).all()


@app.get("/history/{chat_id}")
def history(chat_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    get_owned_chat(chat_id, user, db)
    return db.query(Message).filter(Message.chat_id == chat_id).all()


@app.put("/chat/{chat_id}")
def rename_chat(
    chat_id: str,
    data: RenameRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    chat = get_owned_chat(chat_id, user, db)
    chat.title = data.title.strip() or chat.title
    db.commit()
    return {"msg": "updated"}


@app.delete("/chat/{chat_id}")
def delete_chat(chat_id: str, user=Depends(get_current_user), db: Session = Depends(get_db)):
    chat = get_owned_chat(chat_id, user, db)
    db.query(Message).filter(Message.chat_id == chat_id).delete()
    db.query(DocumentChunk).filter(DocumentChunk.chat_id == chat_id).delete()
    db.query(ImageAttachment).filter(ImageAttachment.chat_id == chat_id).delete()
    tools.close_browser(chat_id)
    db.delete(chat)
    db.commit()
    return {"msg": "deleted"}


# ---------------------------------------------------------------------------
# Uploads and page scraping (indexing + a real model-written summary)
# ---------------------------------------------------------------------------

@app.post("/upload/{chat_id}")
def upload(
    chat_id: str,
    file: UploadFile = File(...),
    model: str | None = Form(None),
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_chat(chat_id, user, db)
    file_bytes = file.file.read()
    is_image = tools.is_image_filename(file.filename)
    if is_image:
        tools.save_image_attachment(db, chat_id, file.filename, file_bytes)

    try:
        content = tools.extract_file_text(file.filename, file_bytes).strip()
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    if not content and not is_image:
        raise HTTPException(status_code=422, detail="No text extracted from file")
    if not content and is_image:
        content = "No readable OCR text was extracted from this image."

    chunk_count = tools.save_document_text(db, chat_id, file.filename, content)

    try:
        installed_model_names = {item["name"] for item in agent.fetch_installed_ollama_models()}
    except requests.RequestException:
        installed_model_names = set()

    selected_model = resolve_model(model, installed_model_names) if installed_model_names else normalize_model_name(model)

    if is_image and installed_model_names:
        vision_model = selected_model if agent.is_vision_model(selected_model) else next(
            (name for name in installed_model_names if agent.is_vision_model(name)), None
        )
        if vision_model:
            try:
                import base64

                response = requests.post(
                    agent.OLLAMA_GENERATE_URL,
                    json={
                        "model": vision_model,
                        "prompt": (
                            "Describe this uploaded image clearly and concisely. "
                            "If it contains text, transcribe the visible text."
                        ),
                        "images": [base64.b64encode(file_bytes).decode("utf-8")],
                        "stream": False,
                    },
                    timeout=(10, agent.OLLAMA_TIMEOUT_SECONDS),
                )
                response.raise_for_status()
                vision_text = agent.strip_thinking(response.json().get("response", "").strip())
                if vision_text:
                    assistant_content = f"I looked at {file.filename}:\n\n{vision_text}"
                    if content and "No readable OCR text" not in content:
                        assistant_content += f"\n\nOCR text was also saved to chat memory, so you can ask about it anytime."
                    save_message_pair(db, chat_id, f"Uploaded file: {file.filename}", assistant_content)
                    return {
                        "msg": "uploaded",
                        "filename": file.filename,
                        "chunks": chunk_count,
                        "assistant_message": assistant_content,
                        "preview": content[:500],
                    }
            except requests.RequestException:
                pass

    text_model = selected_model
    if agent.is_vision_model(text_model) and installed_model_names:
        text_model = next(
            (name for name in installed_model_names if not agent.is_vision_model(name)),
            text_model,
        )
    assistant_content = agent.summarize_content(content, file.filename, text_model)
    save_message_pair(db, chat_id, f"Uploaded file: {file.filename}", assistant_content)

    return {
        "msg": "uploaded",
        "filename": file.filename,
        "chunks": chunk_count,
        "assistant_message": assistant_content,
        "preview": content[:500],
    }


@app.post("/scrape/{chat_id}")
def scrape_page(
    chat_id: str,
    data: ScrapeRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_chat(chat_id, user, db)
    try:
        page = scrape_assignment_page(
            data.url,
            headless=data.headless,
            wait_seconds=max(0, min(data.wait_seconds, 20)),
            manual_login=data.manual_login,
            login_wait_seconds=max(10, min(data.login_wait_seconds, 300)),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    chunk_count = tools.save_document_text(db, chat_id, page.title, f"URL: {page.url}\n\n{page.text}")
    combined_content = page.text
    imported_pdfs = []

    if data.include_pdfs:
        for pdf_url in page.pdf_links[:5]:
            try:
                response = requests.get(pdf_url, timeout=30)
                response.raise_for_status()
                pdf_text = tools.extract_file_text(pdf_url, response.content)
                pdf_chunks = tools.save_document_text(db, chat_id, pdf_url, pdf_text)
                combined_content += "\n\n" + pdf_text
                imported_pdfs.append({"url": pdf_url, "chunks": pdf_chunks})
                chunk_count += pdf_chunks
            except Exception as exc:
                imported_pdfs.append({"url": pdf_url, "error": str(exc)})

    try:
        installed_model_names = {item["name"] for item in agent.fetch_installed_ollama_models()}
    except requests.RequestException:
        installed_model_names = set()
    summary_model = resolve_model(data.model, installed_model_names) if installed_model_names else normalize_model_name(data.model)

    assistant_content = agent.summarize_content(combined_content, page.title, summary_model)
    if imported_pdfs:
        ok = sum(1 for item in imported_pdfs if "chunks" in item)
        failed = len(imported_pdfs) - ok
        note = f"\n\nI also imported {ok} linked PDF{'s' if ok != 1 else ''}."
        if failed:
            note += f" {failed} PDF link{'s' if failed != 1 else ''} could not be read."
        assistant_content += note

    save_message_pair(db, chat_id, f"Added page: {data.url}", assistant_content)
    return {
        "msg": "scraped",
        "title": page.title,
        "chunks": chunk_count,
        "assistant_message": assistant_content,
        "pdf_links": page.pdf_links,
        "links": page.links,
        "imported_pdfs": imported_pdfs,
        "preview": page.text[:500],
    }


# ---------------------------------------------------------------------------
# The agent endpoint — one entry point for every message
# ---------------------------------------------------------------------------

@app.post("/agent")
def agent_endpoint(
    data: StreamRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    get_owned_chat(data.chat_id, user, db)

    try:
        installed_model_names = {model["name"] for model in agent.fetch_installed_ollama_models()}
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Ollama is offline. Start Ollama, then try again.") from exc
    if not installed_model_names:
        raise HTTPException(status_code=503, detail="No Ollama models installed. Run: ollama pull qwen3:8b")

    selected_model = resolve_model(data.model, installed_model_names)
    history_messages = (
        db.query(Message)
        .filter(Message.chat_id == data.chat_id)
        .all()[-HISTORY_MESSAGE_LIMIT:]
    )
    image_payloads = (
        tools.get_latest_image_payloads(db, data.chat_id)
        if agent.is_vision_model(selected_model)
        else None
    )

    def generate():
        final_text = ""
        try:
            for event in agent.run_agent(
                db,
                data.chat_id,
                data.message,
                selected_model,
                history_messages,
                image_payloads,
            ):
                if event["type"] == "token":
                    final_text += event["text"]
                elif event["type"] == "error":
                    final_text = final_text or event["text"]
                yield json.dumps(event) + "\n"
        except Exception as exc:
            message = f"Something went wrong while working on that: {exc}"
            final_text = final_text or message
            yield json.dumps({"type": "error", "text": message}) + "\n"

        save_message_pair(db, data.chat_id, data.message, final_text or "(no answer)")
        yield json.dumps({"type": "done"}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.post("/stream")
def stream(
    data: StreamRequest,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Legacy plain-text endpoint: same agent, but only answer tokens are streamed."""
    get_owned_chat(data.chat_id, user, db)

    try:
        installed_model_names = {model["name"] for model in agent.fetch_installed_ollama_models()}
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="Ollama is offline. Start Ollama, then try again.") from exc

    selected_model = resolve_model(data.model, installed_model_names)
    history_messages = (
        db.query(Message)
        .filter(Message.chat_id == data.chat_id)
        .all()[-HISTORY_MESSAGE_LIMIT:]
    )

    def generate():
        final_text = ""
        for event in agent.run_agent(db, data.chat_id, data.message, selected_model, history_messages):
            if event["type"] in ("token", "error"):
                final_text += event["text"]
                yield event["text"]
        save_message_pair(db, data.chat_id, data.message, final_text or "(no answer)")

    return StreamingResponse(generate(), media_type="text/plain")
