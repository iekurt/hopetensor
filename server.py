from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import sqlite3
import threading
import queue
import json
import time
import os
import requests
from datetime import datetime, timezone

APP_NAME = "HOPEtensor"
APP_VERSION = "1.5.0"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="HOPEtensor Worker API with AI + Memory",
)

DB_NAME = "hopetensor.db"
task_queue: "queue.Queue[int]" = queue.Queue()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DB_NAME,
        check_same_thread=False,
        timeout=30,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT,
            session_id TEXT,
            user_id TEXT,
            mode TEXT,
            metadata TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            result TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_session_id ON tasks(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages(session_id, id)")

        cursor.execute("PRAGMA table_info(tasks)")
        columns = [row["name"] for row in cursor.fetchall()]

        migrations = {
            "text": "ALTER TABLE tasks ADD COLUMN text TEXT",
            "session_id": "ALTER TABLE tasks ADD COLUMN session_id TEXT",
            "user_id": "ALTER TABLE tasks ADD COLUMN user_id TEXT",
            "mode": "ALTER TABLE tasks ADD COLUMN mode TEXT",
            "metadata": "ALTER TABLE tasks ADD COLUMN metadata TEXT",
            "status": "ALTER TABLE tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'queued'",
            "result": "ALTER TABLE tasks ADD COLUMN result TEXT",
            "created_at": "ALTER TABLE tasks ADD COLUMN created_at TEXT",
            "updated_at": "ALTER TABLE tasks ADD COLUMN updated_at TEXT",
        }

        for col, sql in migrations.items():
            if col not in columns:
                cursor.execute(sql)

        now = now_iso()
        cursor.execute("UPDATE tasks SET created_at = COALESCE(created_at, ?)", (now,))
        cursor.execute("UPDATE tasks SET updated_at = COALESCE(updated_at, ?)", (now,))
        cursor.execute("UPDATE tasks SET status = COALESCE(status, 'queued')")
        cursor.execute("UPDATE tasks SET mode = COALESCE(mode, 'default')")
        cursor.execute("UPDATE tasks SET metadata = COALESCE(metadata, '{}')")

        conn.commit()
    finally:
        conn.close()


init_db()

AI_MODE = os.getenv("AI_MODE", "mock")  # mock | openai_compatible
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://127.0.0.1:11434/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "dummy")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")


class TaskCreate(BaseModel):
    text: str = Field(..., description="User input text")
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    mode: Optional[str] = "default"
    metadata: Dict[str, Any] = Field(default_factory=dict)


def row_to_task_dict(row: sqlite3.Row) -> Dict[str, Any]:
    item = dict(row)

    if item.get("metadata"):
        try:
            item["metadata"] = json.loads(item["metadata"])
        except Exception:
            item["metadata"] = {}

    if item.get("result"):
        try:
            item["result"] = json.loads(item["result"])
        except Exception:
            pass

    return item


def get_conversation_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    rows = list(reversed(rows))
    return [
        {
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def save_messages_batch(session_id: str, user_text: str, assistant_text: str) -> None:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ts1 = now_iso()
        ts2 = now_iso()
        cursor.executemany(
            """
            INSERT INTO messages (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                (session_id, "user", user_text, ts1),
                (session_id, "assistant", assistant_text, ts2),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def call_mock_llm(task: Dict[str, Any]) -> Dict[str, Any]:
    time.sleep(1)

    text = task["text"]
    session_id = task.get("session_id") or "default"
    history = get_conversation_history(session_id=session_id, limit=10)
    metadata = task.get("metadata", {}) or {}
    original_text = metadata.get("original_text", text)

    reply = f"[memory={len(history)}] Mesajını aldım: {original_text}"

    return {
        "provider": "mock",
        "model": "demo-model",
        "reply": reply,
        "history_used_count": len(history),
        "session_id": session_id,
        "user_id": task.get("user_id"),
        "mode": task.get("mode"),
        "metadata": metadata,
    }


def call_openai_compatible_llm(task: Dict[str, Any]) -> Dict[str, Any]:
    text = task["text"]
    session_id = task.get("session_id") or "default"
    user_id = task.get("user_id")
    mode = task.get("mode")
    metadata = task.get("metadata", {}) or {}

    history = get_conversation_history(session_id=session_id, limit=12)

    messages = [
        {
            "role": "system",
            "content": (
                "You are the HOPEtensor reasoning engine. "
                "Use conversation history when relevant. "
                "Be clear, grounded, and concise. "
                "Do not echo hidden system context unless explicitly asked."
            ),
        }
    ]

    for item in history:
        messages.append({
            "role": item["role"],
            "content": item["content"],
        })

    messages.append({
        "role": "user",
        "content": text,
    })

    url = f"{AI_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.7,
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    reply = data["choices"][0]["message"]["content"]

    return {
        "provider": "openai_compatible",
        "model": AI_MODEL,
        "reply": reply,
        "history_used_count": len(history),
        "session_id": session_id,
        "user_id": user_id,
        "mode": mode,
        "metadata": metadata,
    }


def process_task(task: Dict[str, Any]) -> Dict[str, Any]:
    session_id = task.get("session_id") or "default"

    if AI_MODE == "mock":
        llm_result = call_mock_llm(task)
    elif AI_MODE == "openai_compatible":
        llm_result = call_openai_compatible_llm(task)
    else:
        raise ValueError(f"Unsupported AI_MODE: {AI_MODE}")

    original_text = task.get("metadata", {}).get("original_text", task["text"])

    save_messages_batch(
        session_id=session_id,
        user_text=original_text,
        assistant_text=llm_result["reply"],
    )

    return {
        "input": original_text,
        "output": llm_result["reply"],
        "provider": llm_result["provider"],
        "model": llm_result["model"],
        "session_id": session_id,
        "user_id": task.get("user_id"),
        "mode": task.get("mode"),
        "metadata": task.get("metadata", {}),
        "history_used_count": llm_result.get("history_used_count", 0),
        "status": "done",
    }


def worker() -> None:
    while True:
        task_id = task_queue.get()

        conn = get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                ("processing", now_iso(), task_id),
            )
            conn.commit()

            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()

            if not row:
                continue

            task_data = row_to_task_dict(row)
            result = process_task(task_data)

            cursor.execute(
                "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                ("completed", json.dumps(result, ensure_ascii=False), now_iso(), task_id),
            )
            conn.commit()

        except Exception as e:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?",
                    (
                        "failed",
                        json.dumps({"error": str(e)}, ensure_ascii=False),
                        now_iso(),
                        task_id,
                    ),
                )
                conn.commit()
            except Exception:
                pass
        finally:
            conn.close()
            task_queue.task_done()


threading.Thread(target=worker, daemon=True).start()


@app.get("/")
def root():
    return {
        "message": "HOPEtensor running",
        "version": APP_VERSION,
        "ai_mode": AI_MODE,
        "ai_model": AI_MODEL,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": APP_VERSION,
        "ai_mode": AI_MODE,
        "ai_model": AI_MODEL,
    }


@app.post("/v1/tasks")
def create_task(task: TaskCreate):
    conn = get_connection()
    try:
        cursor = conn.cursor()

        created_at = now_iso()
        updated_at = created_at
        metadata_json = json.dumps(task.metadata or {}, ensure_ascii=False)

        cursor.execute(
            """
            INSERT INTO tasks (
                text, session_id, user_id, mode, metadata,
                status, result, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.text,
                task.session_id,
                task.user_id,
                task.mode or "default",
                metadata_json,
                "queued",
                None,
                created_at,
                updated_at,
            ),
        )

        conn.commit()
        task_id = cursor.lastrowid
    finally:
        conn.close()

    task_queue.put(task_id)

    return {
        "id": task_id,
        "status": "queued",
        "created_at": created_at,
        "updated_at": updated_at,
    }


@app.get("/v1/tasks/{task_id}")
def get_task(task_id: int):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Task not found")

    return row_to_task_dict(row)


@app.get("/v1/tasks")
def list_tasks():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks ORDER BY id DESC")
        rows = cursor.fetchall()
    finally:
        conn.close()

    return {
        "items": [row_to_task_dict(row) for row in rows],
        "count": len(rows),
    }


@app.get("/v1/sessions/{session_id}/messages")
def get_session_messages(session_id: str):
    history = get_conversation_history(session_id=session_id, limit=100)
    return {
        "session_id": session_id,
        "count": len(history),
        "items": history,
    }
