from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import time

app = FastAPI()

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prod'da domainini kısıtla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB ---
conn = sqlite3.connect("hope.db", check_same_thread=False)
cursor = conn.cursor()

# Users
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    password TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Reason history
cursor.execute("""
CREATE TABLE IF NOT EXISTS reason_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    prompt TEXT,
    answer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# --- Health ---
@app.get("/")
def root():
    return {"status": "ok", "service": "HOPEtensor"}

# --- DID REGISTER ---
@app.post("/v1/did/register")
def register(payload: dict):
    email = payload.get("email")
    password = payload.get("password")

    try:
        cursor.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            (email, password)
        )
        conn.commit()
        return {"status": "registered", "email": email}
    except sqlite3.IntegrityError:
        return {"status": "exists", "email": email}

# --- DID LOGIN ---
@app.post("/v1/did/login")
def login(payload: dict):
    email = payload.get("email")
    password = payload.get("password")

    cursor.execute(
        "SELECT id FROM users WHERE email=? AND password=?",
        (email, password)
    )
    user = cursor.fetchone()

    if user:
        return {"status": "ok", "email": email}
    return {"status": "fail"}

# --- USERS LIST (debug) ---
@app.get("/v1/did/users")
def get_users():
    cursor.execute("SELECT id, email, created_at FROM users ORDER BY id DESC")
    rows = cursor.fetchall()

    return [
        {"id": r[0], "email": r[1], "created_at": r[2]}
        for r in rows
    ]

# --- REASON (user bağlı + history yaz) ---
@app.post("/v1/reason")
def reason(payload: dict):
    prompt = payload.get("prompt", "")
    user_id = payload.get("user_id")  # email

    # kullanıcıyı doğrula (opsiyonel ama iyi)
    cursor.execute("SELECT id FROM users WHERE email=?", (user_id,))
    user = cursor.fetchone()

    if not user:
        return {"error": "user not found"}

    # basit cevap (sonra engine bağlayacağız)
    answer = f"{user_id} → {prompt}"

    # history yaz
    cursor.execute(
        "INSERT INTO reason_history (user_id, prompt, answer) VALUES (?, ?, ?)",
        (user_id, prompt, answer)
    )
    conn.commit()

    return {
        "answer": answer,
        "confidence": 0.9,
        "vicdan_status": "ok",
        "trace_id": f"trace_{int(time.time())}"
    }

# --- HISTORY ---
@app.get("/v1/reason/history")
def get_history(user_id: str):
    cursor.execute(
        "SELECT prompt, answer, created_at FROM reason_history WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    )
    rows = cursor.fetchall()

    return [
        {"prompt": r[0], "answer": r[1], "created_at": r[2]}
        for r in rows
    ]



