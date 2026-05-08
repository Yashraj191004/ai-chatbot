import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext

load_dotenv()

SECRET = os.getenv("JWT_SECRET", "change-me-in-env")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

ACCESS_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_EXPIRE_MINUTES", "15"))
REFRESH_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_EXPIRE_DAYS", "7"))

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


# 🔐 PASSWORD
def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(password: str, hashed):
    return pwd_context.verify(password, hashed)


# 🎟️ TOKENS
def create_access_token(data: dict):
    payload = data.copy()
    payload.update({
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_EXPIRE_MINUTES),
        "type": "access"
    })
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    payload = data.copy()
    payload.update({
        "exp": datetime.utcnow() + timedelta(days=REFRESH_EXPIRE_DAYS),
        "type": "refresh"
    })
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None