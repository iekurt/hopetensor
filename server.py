from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3

# =========================
# APP CONFIG
# =========================
APP_NAME = "HOPEtensor"
APP_VERSION = "0.4.0"

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="HOPEtensor Core API"
)

# =========================
# DB SETUP
# =========================
DB_NAME = "hopetensor.db"

def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        done BOOLEAN NOT NULL DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()

# app başlarken DB oluştur
init_db()

# =========================
# MODELS
# =========================
class TaskCreate(BaseModel):
    title: str

class TaskUpdate(BaseModel):
    done: bool

# =========================
# ROOT
# =========================
@app.get("/")
def root():
    return {
        "message": "HOPEtensor is running",
        "app": APP_NAME,
        "version": APP_VERSION
    }

# =========================
# HEALTH
# =========================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION
    }

# =========================
# TASKS (DB)
# =========================

# GET ALL
@app.get("/v1/tasks")
def list_tasks():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tasks")
    rows = cursor.fetchall()

    tasks = [dict(row) for row in rows]

    conn.close()

    return {
        "items": tasks,
        "count": len(tasks)
    }

# CREATE
@app.post("/v1/tasks")
def create_task(task: TaskCreate):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO tasks (title, done) VALUES (?, ?)",
        (task.title, False)
    )

    conn.commit()
    task_id = cursor.lastrowid
    conn.close()

    return {
        "id": task_id,
        "title": task.title,
        "done": False
    }

# UPDATE
@app.patch("/v1/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdate):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE tasks SET done = ? WHERE id = ?",
        (payload.done, task_id)
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")

    conn.commit()
    conn.close()

    return {
        "id": task_id,
        "done": payload.done
    }

# DELETE
@app.delete("/v1/tasks/{task_id}")
def delete_task(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")

    conn.commit()
    conn.close()

    return {"deleted": task_id}
