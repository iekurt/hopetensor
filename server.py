from fastapi import FastAPI

app = FastAPI()

import os
import time
import hashlib
import secrets
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

import sqlite3

conn = sqlite3.connect("hope.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT,
    password TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")



conn.commit()

@app.post("/v1/did/login")
def login(payload: dict):
    email = payload.get("email")
    password = payload.get("password")

    cursor.execute(
        "SELECT * FROM users WHERE email=? AND password=?",
        (email, password)
    )
    user = cursor.fetchone()

    if user:
        return {"status": "ok", "email": email}
    else:
        return {"status": "fail"}

    

@app.post("/v1/did/register")
def register(payload: dict):
    email = payload.get("email")
    password = payload.get("password")

    cursor.execute(
        "INSERT INTO users (email, password) VALUES (?, ?)",
        (email, password)
    )
    conn.commit()

    return {
        "status": "registered",
        "email": email
    }

@app.get("/v1/did/users")
def get_users():
    cursor.execute("SELECT id, email, created_at FROM users")
    rows = cursor.fetchall()

    return [
        {
            "id": r[0],
            "email": r[1],
            "created_at": r[2]
        }
        for r in rows
    ]


APP_NAME = "HOPEtensor"
APP_VERSION = "1.0.0"

app = FastAPI(
    title="HOPEtensor API",
    version=APP_VERSION,
    description="HOPEverse single-backend API with DID identity system.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dataizm.net",
        "https://www.dataizm.net",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USERS: Dict[str, Dict[str, Any]] = {}
SESSIONS: Dict[str, str] = {}


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    purpose: Optional[str] = "Ethics before power. Human-centered. Conscience-aware."


class LoginRequest(BaseModel):
    identifier: Optional[str] = None
    email: Optional[EmailStr] = None
    did: Optional[str] = None
    password: str


def now() -> int:
    return int(time.time())


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def make_did(email: str) -> str:
    seed = hashlib.sha256(f"{email}:{time.time()}:{secrets.token_hex(8)}".encode()).hexdigest()
    return f"did:hope:{seed[:24]}"


def make_token() -> str:
    return secrets.token_urlsafe(48)


def public_profile(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "did": user["did"],
        "name": user["name"],
        "email": user["email"],
        "purpose": user.get("purpose"),
        "status": "verified",
        "created_at": user["created_at"],
        "trust_layer": {
            "ethics": "active",
            "identity": "did",
            "network": "HOPEverse",
        },
    }


def get_user_from_auth(authorization: Optional[str]) -> Dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.replace("Bearer ", "").strip()
    email = SESSIONS.get(token)

    if not email or email not in USERS:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return USERS[email]


@app.get("/")
def root():
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "status": "online",
        "message": "HOPEverse API is alive.",
        "docs": "/docs",
        "endpoints": [
            "GET /health",
            "POST /did/register",
            "POST /did/login",
            "GET /did/profile",
        ],
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "timestamp": now(),
    }


@app.post("/did/register")
def did_register(payload: RegisterRequest):
    email = payload.email.lower().strip()

    if email in USERS:
        raise HTTPException(status_code=409, detail="User already exists")

    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    salt = secrets.token_hex(16)
    did = make_did(email)

    user = {
        "did": did,
        "name": payload.name.strip(),
        "email": email,
        "purpose": payload.purpose,
        "salt": salt,
        "password_hash": hash_password(payload.password, salt),
        "created_at": now(),
    }

    USERS[email] = user

    token = make_token()
    SESSIONS[token] = email

    return {
        "ok": True,
        "message": "DID registered successfully",
        "access_token": token,
        "token_type": "bearer",
        "profile": public_profile(user),
    }


@app.post("/did/login")
def did_login(payload: LoginRequest):
    identifier = (
        payload.email
        or payload.identifier
        or payload.did
        or ""
    )

    identifier = str(identifier).lower().strip()

    user = None

    if identifier in USERS:
        user = USERS[identifier]
    else:
        for candidate in USERS.values():
            if candidate["did"].lower() == identifier:
                user = candidate
                break

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    expected = hash_password(payload.password, user["salt"])

    if expected != user["password_hash"]:
        raise HTTPException(status_code=401, detail="Invalid password")

    token = make_token()
    SESSIONS[token] = user["email"]

    return {
        "ok": True,
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
        "profile": public_profile(user),
    }


@app.get("/did/profile")
def did_profile(authorization: Optional[str] = Header(default=None)):
    user = get_user_from_auth(authorization)

    return {
        "ok": True,
        "profile": public_profile(user),
    }


@app.post("/did/logout")
def did_logout(authorization: Optional[str] = Header(default=None)):
    if not authorization:
        return {"ok": True, "message": "No active session"}

    token = authorization.replace("Bearer ", "").strip()
    SESSIONS.pop(token, None)

    return {
        "ok": True,
        "message": "Logged out",
    }


# Compatibility aliases
@app.post("/register")
def register_alias(payload: RegisterRequest):
    return did_register(payload)


@app.post("/login")
def login_alias(payload: LoginRequest):
    return did_login(payload)


@app.get("/profile")
def profile_alias(authorization: Optional[str] = Header(default=None)):
    return did_profile(authorization)


@app.get("/me")
def me_alias(authorization: Optional[str] = Header(default=None)):
    return did_profile(authorization)




@app.post("/v1/reason")
def reason(payload: dict):
    prompt = payload.get("prompt", "")
    user_id = payload.get("user_id")  # 👈 BURADA TANIMLANIR

    # 👇 BURAYA KOY
    cursor.execute(
        "SELECT * FROM users WHERE email=?",
        (user_id,)
    )
    user = cursor.fetchone()

    return {
        "answer": f"{user_id} → {prompt}",
        "confidence": 0.9,
        "vicdan_status": "ok"
    }





