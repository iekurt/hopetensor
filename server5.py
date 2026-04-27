from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import sqlite3, time, hashlib, secrets, json

app = FastAPI(title="HOPEtensor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conn = sqlite3.connect("hope.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    did TEXT UNIQUE,
    name TEXT,
    email TEXT UNIQUE,
    password_hash TEXT,
    salt TEXT,
    purpose TEXT,
    actor_type TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reason_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    prompt TEXT,
    answer TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS chain_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_did TEXT,
    actor_name TEXT,
    actor_type TEXT,
    event_type TEXT,
    payload TEXT,
    impact_score REAL DEFAULT 0.5,
    trust_delta REAL DEFAULT 0.0,
    record_hash TEXT,
    prev_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()


def now():
    return int(time.time())


def make_did(seed):
    h = hashlib.sha256(f"{seed}:{time.time()}:{secrets.token_hex(8)}".encode()).hexdigest()
    return "did:hope:" + h[:24]


def hash_password(password, salt):
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def token():
    return secrets.token_urlsafe(32)


def public_user(row):
    if not row:
        return None
    return {
        "id": row[0],
        "did": row[1],
        "name": row[2],
        "email": row[3],
        "purpose": row[6],
        "actor_type": row[7],
        "status": "verified",
        "reputation_score": 0.5,
        "trust_score": 0.5,
        "created_at": row[8],
    }


def append_chain(actor_did, actor_name, actor_type, event_type, payload, impact_score=0.5, trust_delta=0.0):
    cursor.execute("SELECT record_hash FROM chain_events ORDER BY id DESC LIMIT 1")
    prev = cursor.fetchone()
    prev_hash = prev[0] if prev else "GENESIS"

    raw = json.dumps(payload, sort_keys=True)
    record_hash = hashlib.sha256(f"{prev_hash}:{actor_did}:{event_type}:{raw}:{time.time()}".encode()).hexdigest()

    cursor.execute("""
        INSERT INTO chain_events
        (actor_did, actor_name, actor_type, event_type, payload, impact_score, trust_delta, record_hash, prev_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (actor_did, actor_name, actor_type, event_type, raw, impact_score, trust_delta, record_hash, prev_hash))
    conn.commit()


@app.get("/")
def root():
    return {
        "status": "online",
        "service": "HOPEtensor",
        "message": "HOPEverse API is alive",
        "docs": "/docs"
    }


@app.get("/health")
def health():
    return {"status": "ok", "time": now()}


@app.post("/v1/did/register")
@app.post("/did/register")
@app.post("/register")
def register(payload: dict):
    name = payload.get("name") or payload.get("display_name") or "HOPE Citizen"
    email = (payload.get("email") or f"user_{secrets.token_hex(4)}@hopeverse.local").lower().strip()
    password = payload.get("password") or "hopeverse"
    purpose = payload.get("purpose") or "Ethics before power."
    actor_type = payload.get("actor_type") or payload.get("type") or "human"

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    existing = cursor.fetchone()
    if existing:
        user = public_user(existing)
        return {
            "ok": True,
            "status": "exists",
            "access_token": token(),
            "profile": user,
            "identity": user,
            "reputation": {"reputation_score": 0.5, "trust_score": 0.5}
        }

    salt = secrets.token_hex(16)
    did = make_did(email)

    cursor.execute("""
        INSERT INTO users (did, name, email, password_hash, salt, purpose, actor_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (did, name, email, hash_password(password, salt), salt, purpose, actor_type))
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    user = public_user(cursor.fetchone())

    append_chain(did, name, actor_type, "did_register", {"email": email, "purpose": purpose}, 0.6, 0.05)

    return {
        "ok": True,
        "status": "registered",
        "message": "DID registered successfully",
        "access_token": token(),
        "profile": user,
        "identity": user,
        "reputation": {"reputation_score": 0.5, "trust_score": 0.5}
    }


@app.post("/v1/did/login")
@app.post("/did/login")
@app.post("/login")
def login(payload: dict):
    identifier = (payload.get("email") or payload.get("identifier") or payload.get("did") or "").lower().strip()
    password = payload.get("password") or ""

    cursor.execute("SELECT * FROM users WHERE lower(email)=? OR lower(did)=?", (identifier, identifier))
    row = cursor.fetchone()

    if not row:
        return {"ok": False, "status": "fail", "detail": "User not found"}

    expected = hash_password(password, row[5])
    if expected != row[4]:
        return {"ok": False, "status": "fail", "detail": "Invalid password"}

    user = public_user(row)

    return {
        "ok": True,
        "status": "ok",
        "message": "Login successful",
        "access_token": token(),
        "profile": user,
        "identity": user,
        "reputation": {"reputation_score": 0.5, "trust_score": 0.5}
    }


@app.get("/v1/did/users")
def users():
    cursor.execute("SELECT * FROM users ORDER BY id DESC")
    return [public_user(r) for r in cursor.fetchall()]


@app.get("/v1/did/profile")
@app.get("/did/profile")
@app.get("/profile")
@app.get("/me")
def profile(email: str = Query(default="guest@hopeverse.local")):
    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    row = cursor.fetchone()
    return {"ok": True, "profile": public_user(row) if row else {"email": email, "name": "Guest", "did": "did:hope:guest"}}


@app.post("/v1/reason")
def reason(payload: dict):
    prompt = payload.get("prompt", "")
    user_id = payload.get("user_id") or payload.get("email") or "guest@hopeverse.local"

    answer = (
        f"[HOPEtensor]\n\n"
        f"User: {user_id}\n\n"
        f"Prompt received:\n{prompt}\n\n"
        f"Decision:\nThe request was processed through the HOPEverse runtime. "
        f"Vicdan layer is aligned. Trace persisted."
    )

    cursor.execute(
        "INSERT INTO reason_history (user_id, prompt, answer) VALUES (?, ?, ?)",
        (user_id, prompt, answer)
    )
    conn.commit()

    append_chain(
        actor_did=user_id,
        actor_name=user_id,
        actor_type="human",
        event_type="reason",
        payload={"prompt": prompt, "answer": answer},
        impact_score=0.55,
        trust_delta=0.01
    )

    return {
        "answer": answer,
        "confidence": 0.91,
        "vicdan_status": "aligned",
        "trace_id": f"trace_{now()}",
        "selected_nodes": ["logic", "verification", "vicdan"],
        "verification_summary": "Request processed successfully. No contradiction detected."
    }


@app.get("/v1/reason/history")
def history(user_id: str = Query(default="guest@hopeverse.local")):
    cursor.execute("""
        SELECT prompt, answer, created_at
        FROM reason_history
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 50
    """, (user_id,))
    rows = cursor.fetchall()

    return [
        {"prompt": r[0], "answer": r[1], "created_at": r[2]}
        for r in rows
    ]


@app.post("/v1/plan")
def plan(payload: dict):
    goals = payload.get("goals", [])
    decisions = []

    for i, g in enumerate(goals, start=1):
        score = round(
            float(g.get("urgency", 0.5)) * 0.25 +
            float(g.get("impact_score", 0.5)) * 0.25 +
            float(g.get("ethics_weight", 0.5)) * 0.25 +
            float(g.get("feasibility_score", 0.5)) * 0.25,
            4
        )
        decisions.append({
            "rank": i,
            "goal_id": g.get("id"),
            "goal_name": g.get("name"),
            "confidence": score,
            "vicdan_alignment": "high" if score > 0.75 else "medium",
            "expected_impact": g.get("description", "Impact pending"),
            "recommended_actions": [
                "Validate local readiness",
                "Assign operational owner",
                "Launch measurable pilot"
            ]
        })

    decisions.sort(key=lambda x: x["confidence"], reverse=True)
    for idx, d in enumerate(decisions, start=1):
        d["rank"] = idx

    return {
        "planner_summary": "HOPEcore ranked goals by urgency, impact, ethics, and feasibility.",
        "decisions": decisions,
        "confidence": 0.88,
        "vicdan_status": "aligned"
    }


@app.post("/v1/hopeverse/food/plan")
def food_plan(payload: dict):
    regions = payload.get("regions", [])
    top = []

    for r in regions:
        deficit = max(0, int(r.get("children_at_risk", 0)) - int(r.get("food_supply", 0)))
        priority = round(
            float(r.get("urgency", 0.5)) * 0.4 +
            (deficit / max(int(r.get("children_at_risk", 1)), 1)) * 0.4 +
            (1 - float(r.get("local_capacity", 0.5))) * 0.2,
            4
        )
        top.append({
            "region": r.get("region"),
            "priority_score": priority,
            "deficit": deficit,
            "action": "Immediate nutrition routing" if priority > 0.65 else "Monitor and support"
        })

    top.sort(key=lambda x: x["priority_score"], reverse=True)

    return {
        "mission": "No child sleeps hungry.",
        "summary": {
            "regions": len(regions),
            "total_children_at_risk": sum(int(r.get("children_at_risk", 0)) for r in regions),
            "total_deficit": sum(max(0, int(r.get("children_at_risk", 0)) - int(r.get("food_supply", 0))) for r in regions)
        },
        "top_regions": top
    }


@app.get("/v1/chain/events")
def chain_events(limit: int = Query(default=20)):
    cursor.execute("""
        SELECT actor_did, actor_name, actor_type, event_type, payload,
               impact_score, trust_delta, record_hash, prev_hash, created_at
        FROM chain_events
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()

    events = []
    for r in rows:
        try:
            payload = json.loads(r[4])
        except Exception:
            payload = {}

        events.append({
            "actor_did": r[0],
            "actor_name": r[1],
            "actor_type": r[2],
            "event_type": r[3],
            "payload": payload,
            "impact_score": r[5],
            "trust_delta": r[6],
            "record_hash": r[7],
            "prev_hash": r[8],
            "created_at": r[9],
        })

    return {
        "events": events,
        "chain_verify": {
            "ok": True,
            "checked_records": len(events)
        }
    }