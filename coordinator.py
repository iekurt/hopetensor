from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import requests
import time
import sqlite3
import uuid
import re
from datetime import datetime
from fastapi import FastAPI

app = FastAPI()

APP_NAME = "HOPEtensor Coordinator"
APP_VERSION = "2.2.0"

TASK_API_BASE = "http://127.0.0.1:8001"
POLL_INTERVAL_SECONDS = 1
POLL_TIMEOUT_SECONDS = 20
DB_PATH = "memory.db"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Coordinator service for HOPEtensor",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    text: str = Field(..., description="User input text")
    session_id: Optional[str] = Field(default=None, description="Conversation/session id")
    user_id: Optional[str] = Field(default=None, description="User id")
    mode: Optional[str] = Field(default="default", description="Execution mode")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    ok: bool
    task_id: int
    status: str
    input: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    mode: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.on_event("startup")
def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, key)
            )
            """
        )
        conn.commit()


def set_mem(user_id: str, key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO memory (user_id, key, value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, key)
            DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (user_id, key, value, now_iso()),
        )
        conn.commit()


def get_mem(user_id: str, key: str) -> Optional[str]:
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM memory WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
    return row["value"] if row else None


def get_profile(user_id: str) -> Dict[str, Optional[str]]:
    return {
        "name": get_mem(user_id, "name"),
        "location": get_mem(user_id, "location"),
        "interest": get_mem(user_id, "interest"),
        "goal": get_mem(user_id, "goal"),
    }


def extract_name(text: str) -> Optional[str]:
    text_l = text.strip().lower()

    blocked = {
        "ne", "neydi", "nedir", "kim", "kimdi", "neymiş", "hangi"
    }

    patterns = [
        r"\bbenim adım\s+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b",
        r"\badım\s+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b",
        r"\bmy name is\s+([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text_l, re.IGNORECASE)
        if m:
            value = m.group(1).strip().lower()
            if value in blocked:
                return None
            return value.capitalize()

    return None


def extract_location(text: str) -> Optional[str]:
    text_l = text.strip().lower()

    direct_cities = [
        "istanbul", "ankara", "izmir", "bursa", "antalya", "adana"
    ]

    if text_l in direct_cities:
        return text_l.capitalize()

    for city in direct_cities:
        if (
            f"{city}dayım" in text_l
            or f"{city}deyim" in text_l
            or f"{city}tayım" in text_l
            or f"{city}teyim" in text_l
        ):
            return city.capitalize()

    patterns = [
        r"\b([a-zA-ZçğıöşüÇĞİÖŞÜ]+)dayım\b",
        r"\b([a-zA-ZçğıöşüÇĞİÖŞÜ]+)deyim\b",
        r"\b([a-zA-ZçğıöşüÇĞİÖŞÜ]+)tayım\b",
        r"\b([a-zA-ZçğıöşüÇĞİÖŞÜ]+)teyim\b",
        r"\bi live in ([a-zA-ZçğıöşüÇĞİÖŞÜ]+)\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text_l, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if value:
                return value.capitalize()

    return None


def extract_interest(text: str) -> Optional[str]:
    patterns = [
        r"\b(.+?) seviyorum\b",
        r"\bi like (.+)",
        r"\bi love (.+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text.strip(), re.IGNORECASE)
        if m:
            value = m.group(1).strip(" .,!?:;")
            if value:
                return value[:1].upper() + value[1:]

    return None


def extract_goal(text: str) -> Optional[str]:
    patterns = [
        r"\b(.+?) kuruyorum\b",
        r"\b(.+?) yapmak istiyorum\b",
        r"\bi want to (.+)",
        r"\bi am building (.+)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text.strip(), re.IGNORECASE)
        if m:
            value = m.group(1).strip(" .,!?:;")
            if value:
                return value[:1].upper() + value[1:]

    return None


def is_asking_name(text: str) -> bool:
    t = text.strip().lower()
    checks = [
        "benim adım ne",
        "benim adım neydi",
        "adım ne",
        "adım neydi",
        "what is my name",
        "what was my name",
        "do you remember my name",
    ]
    return any(x in t for x in checks)


def update_profile(user_id: str, text: str) -> Dict[str, str]:
    updated: Dict[str, str] = {}

    name = extract_name(text)
    if name:
        set_mem(user_id, "name", name)
        updated["name"] = name

    location = extract_location(text)
    if location:
        set_mem(user_id, "location", location)
        updated["location"] = location

    interest = extract_interest(text)
    if interest:
        set_mem(user_id, "interest", interest)
        updated["interest"] = interest

    goal = extract_goal(text)
    if goal:
        set_mem(user_id, "goal", goal)
        updated["goal"] = goal

    return updated


def build_context(user_id: str, text: str) -> str:
    profile = get_profile(user_id)

    parts = []
    parts.append("SYSTEM CONTEXT:")
    parts.append("Use the user profile only when relevant.")
    parts.append("Do not repeat the raw system context back to the user.")
    parts.append("")
    parts.append("USER PROFILE:")

    if profile["name"]:
        parts.append(f"- name: {profile['name']}")
    if profile["location"]:
        parts.append(f"- location: {profile['location']}")
    if profile["interest"]:
        parts.append(f"- interest: {profile['interest']}")
    if profile["goal"]:
        parts.append(f"- goal: {profile['goal']}")

    if not any(profile.values()):
        parts.append("- no stored profile yet")

    parts.append("")
    parts.append("CURRENT USER MESSAGE:")
    parts.append(text)

    return "\n".join(parts)


def create_task(body: Dict[str, Any]) -> Dict[str, Any]:
    try:
        r = requests.post(
            f"{TASK_API_BASE}/v1/tasks",
            json=body,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Task API create error: {str(e)}"
        )


def get_task(task_id: int) -> Dict[str, Any]:
    try:
        r = requests.get(
            f"{TASK_API_BASE}/v1/tasks/{task_id}",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Task API fetch error: {str(e)}"
        )


@app.get("/")
def root():
    return {
        "message": "HOPEtensor coordinator is running",
        "app": APP_NAME,
        "version": APP_VERSION,
        "task_api_base": TASK_API_BASE,
        "memory_db": DB_PATH,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "task_api_base": TASK_API_BASE,
        "memory_db": DB_PATH,
    }


@app.get("/memory/{user_id}")
def read_memory(user_id: str):
    return {
        "ok": True,
        "user_id": user_id,
        "profile": get_profile(user_id),
    }


@app.post("/query", response_model=QueryResponse)
def query(q: QueryRequest):
    text = (q.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    user = (q.user_id or "anon").strip()
    session_id = q.session_id

    if is_asking_name(text):
        name = get_mem(user, "name")
        reply_text = f"Adın {name}." if name else "Adını henüz bilmiyorum."

        return QueryResponse(
            ok=True,
            task_id=0,
            status="done",
            input=text,
            session_id=session_id,
            user_id=user,
            mode=q.mode,
            result={
                "text": reply_text,
                "source": "coordinator_memory",
                "memory": get_profile(user),
            },
            message="Answered from coordinator memory",
        )

    profile_updates = update_profile(user, text)
    enriched = build_context(user, text)

    task = create_task({
        "text": enriched,
        "user_id": user,
        "session_id": session_id,
        "mode": q.mode,
        "metadata": {
            **(q.metadata or {}),
            "original_text": text,
            "profile_updates": profile_updates,
            "memory": get_profile(user),
        }
    })

    task_id = task.get("id")
    if not task_id:
        raise HTTPException(status_code=502, detail="Task API did not return task id")

    deadline = time.time() + POLL_TIMEOUT_SECONDS

    while time.time() < deadline:
        task_data = get_task(task_id)
        status = task_data.get("status", "unknown")

        if status == "completed":
            return QueryResponse(
                ok=True,
                task_id=task_id,
                status="done",
                input=text,
                session_id=session_id,
                user_id=user,
                mode=q.mode,
                result=task_data.get("result"),
                message="Task completed successfully",
            )

        if status == "failed":
            return QueryResponse(
                ok=False,
                task_id=task_id,
                status="failed",
                input=text,
                session_id=session_id,
                user_id=user,
                mode=q.mode,
                result=task_data.get("result"),
                message="Task failed",
            )

        time.sleep(POLL_INTERVAL_SECONDS)

    return QueryResponse(
        ok=False,
        task_id=task_id,
        status="timeout",
        input=text,
        session_id=session_id,
        user_id=user,
        mode=q.mode,
        result=None,
        message="Task is still running",
    )
