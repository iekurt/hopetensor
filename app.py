# app.py
# HOPEtensor — Decentralized AI Node (Hybrid: local + forward)
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Version       : 0.2.0
# License       : Proprietary / HOPE Ecosystem
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"

from __future__ import annotations

import os
import time
import uuid
import json
import random
import platform
from typing import Any, Dict, Optional, List, Tuple

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

# -----------------------------
# Config
# -----------------------------
APP_NAME = os.getenv("APP_NAME", "hopetensor")
VERSION = os.getenv("VERSION", "0.2.0")

# Signature
SIGNATURE_TXT = "\n".join(
    [
        "HOPEtensor — Decentralized AI Node",
        "",
        "Author        : Erhan (master)",
        "Digital Twin  : Vicdan",
        f"Version       : {VERSION}",
        f"Deploy        : {os.getenv('RENDER_GIT_COMMIT', os.getenv('GIT_COMMIT', 'dev'))}",
        "License       : Proprietary / HOPE Ecosystem",
        "",
        "\"Yurtta barış, Cihanda barış\"",
        "\"In GOD We HOPE\"",
        "",
    ]
)

# Local engine (OpenAI-compatible; can be OpenAI or any compatible gateway)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "20"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "256"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))
OPENAI_SYSTEM = os.getenv(
    "OPENAI_SYSTEM",
    "You are Vicdan, a helpful, concise assistant. Reply in Turkish unless asked otherwise.",
)

# Peer forwarding (Decentralized)
# Comma-separated: "https://node-a.onrender.com,https://node-b.onrender.com"
PEER_URLS: List[str] = [u.strip().rstrip("/") for u in os.getenv("PEER_URLS", "").split(",") if u.strip()]

# Routing modes:
# - local_first: try local engine, if fail -> peers
# - peer_first: try peers, if all fail -> local
# - hybrid: maybe forward (probabilistic) + local fallback
ROUTING_MODE = os.getenv("ROUTING_MODE", "hybrid").strip().lower()

# In hybrid mode, probability to attempt peer(s) first
FORWARD_PROB = float(os.getenv("FORWARD_PROB", "0.50"))

# How many peers to try (random sample from PEER_URLS)
PEER_FANOUT = int(os.getenv("PEER_FANOUT", "2"))

# Timeouts for peer calls
PEER_TIMEOUT_S = float(os.getenv("PEER_TIMEOUT_S", "12"))

# -----------------------------
# FastAPI
# -----------------------------
app = FastAPI(title="HOPEtensor", version=VERSION)

# -----------------------------
# Models
# -----------------------------
class ReasonIn(BaseModel):
    text: str = Field(..., min_length=1)
    trace: bool = True


class V1TaskIn(BaseModel):
    client_did: Optional[str] = None
    task: Dict[str, Any]


# -----------------------------
# Helpers
# -----------------------------
def _now_ms() -> int:
    return int(time.time() * 1000)


def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    try:
        return json.dumps(x, ensure_ascii=False)
    except Exception:
        return str(x)


def _extract_text_from_v1_task(payload: V1TaskIn) -> str:
    task = payload.task or {}
    inputs = task.get("inputs") or {}

    messages = inputs.get("messages") or []
    if isinstance(messages, list) and messages:
        last = messages[-1] or {}
        if isinstance(last, dict):
            return _safe_str(last.get("content")).strip()

    return _safe_str(inputs.get("text")).strip()


def _fallback(prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt:
        return ""
    return f"[fallback] Received: {prompt}"


def _openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY missing")

    url = f"{OPENAI_BASE_URL}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": OPENAI_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": OPENAI_MAX_TOKENS,
        "temperature": OPENAI_TEMPERATURE,
    }

    r = requests.post(url, headers=headers, json=body, timeout=OPENAI_TIMEOUT_S)
    r.raise_for_status()
    data = r.json()
    return (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()


def _peer_candidates() -> List[str]:
    if not PEER_URLS:
        return []
    if PEER_FANOUT <= 0 or PEER_FANOUT >= len(PEER_URLS):
        urls = PEER_URLS[:]
        random.shuffle(urls)
        return urls
    return random.sample(PEER_URLS, k=PEER_FANOUT)


def _call_peer_v1_tasks(peer_base: str, payload: V1TaskIn) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Calls peer /v1/tasks with the SAME payload.
    Returns: (ok, peer_url, response_json)
    """
    url = f"{peer_base}/v1/tasks"
    try:
        r = requests.post(url, json=payload.model_dump(), timeout=PEER_TIMEOUT_S)
        # If peer responds but not ok, still parse json
        data = {}
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text}

        if r.status_code >= 400:
            return False, peer_base, {"http": r.status_code, "data": data}

        # Expect peer returns {"ok": True, ...}
        if isinstance(data, dict) and data.get("ok") is True:
            return True, peer_base, data

        return False, peer_base, {"http": r.status_code, "data": data}
    except Exception as e:
        return False, peer_base, {"error": str(e)}


def _route_and_generate(prompt: str, v1_payload: Optional[V1TaskIn] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Returns (text_output, meta)
    """
    meta: Dict[str, Any] = {
        "routing_mode": ROUTING_MODE,
        "peers_configured": len(PEER_URLS),
        "local_llm_enabled": bool(OPENAI_API_KEY),
        "ts_ms": _now_ms(),
    }

    # Decide order
    peers = _peer_candidates()
    do_peer_first = False

    if ROUTING_MODE == "peer_first":
        do_peer_first = True
    elif ROUTING_MODE == "local_first":
        do_peer_first = False
    else:
        # hybrid
        do_peer_first = (random.random() < FORWARD_PROB) and bool(peers)

    meta["peer_first"] = do_peer_first
    meta["peer_candidates"] = peers

    # Helper: run local
    def run_local() -> Tuple[bool, str, Dict[str, Any]]:
        if OPENAI_API_KEY:
            try:
                out = _openai_chat(prompt)
                return True, out, {"engine": "local_llm", "model": OPENAI_MODEL, "base_url": OPENAI_BASE_URL}
            except Exception as e:
                return False, "", {"engine": "local_llm", "error": str(e)}
        # No local engine configured -> fallback
        return True, _fallback(prompt), {"engine": "fallback"}

    # Helper: run peers
    def run_peers() -> Tuple[bool, str, Dict[str, Any]]:
        if not peers or v1_payload is None:
            return False, "", {"engine": "peers", "error": "no peers or missing v1 payload"}
        for p in peers:
            ok, peer_url, data = _call_peer_v1_tasks(p, v1_payload)
            if ok:
                # Try to extract output text from peer schema
                text = ""
                if isinstance(data, dict):
                    out = data.get("output") or {}
                    if isinstance(out, dict):
                        text = _safe_str(out.get("text")).strip()
                if not text:
                    text = _safe_str(data)

                return True, text, {"engine": "peer", "peer": peer_url}
        return False, "", {"engine": "peers", "error": "all peers failed"}

    # Execute based on order
    if do_peer_first:
        okp, outp, mp = run_peers()
        meta["peer_result"] = mp
        if okp and outp:
            return outp, meta

        okl, outl, ml = run_local()
        meta["local_result"] = ml
        return outl, meta
    else:
        okl, outl, ml = run_local()
        meta["local_result"] = ml
        if okl and outl:
            return outl, meta

        okp, outp, mp = run_peers()
        meta["peer_result"] = mp
        if okp and outp:
            return outp, meta

        # Last resort
        meta["engine"] = "fallback_last"
        return _fallback(prompt), meta


# -----------------------------
# Routes
# -----------------------------
@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return SIGNATURE_TXT


@app.get("/index", response_class=PlainTextResponse)
def index() -> str:
    return SIGNATURE_TXT


@app.get("/index.html", response_class=PlainTextResponse)
def index_html() -> str:
    return SIGNATURE_TXT


@app.get("/signature", response_class=PlainTextResponse)
def signature() -> str:
    return SIGNATURE_TXT


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "app": APP_NAME,
        "version": VERSION,
        "ts_ms": _now_ms(),
        "python": platform.python_version(),
        "routing": {
            "mode": ROUTING_MODE,
            "forward_prob": FORWARD_PROB,
            "peer_fanout": PEER_FANOUT,
            "peer_timeout_s": PEER_TIMEOUT_S,
            "peers": PEER_URLS,
        },
        "local_engine": {
            "enabled": bool(OPENAI_API_KEY),
            "base_url": OPENAI_BASE_URL,
            "model": OPENAI_MODEL,
            "timeout_s": OPENAI_TIMEOUT_S,
        },
    }


@app.post("/reason")
async def reason(payload: ReasonIn) -> Dict[str, Any]:
    t0 = _now_ms()
    request_id = str(uuid.uuid4())

    text_out, meta = _route_and_generate(payload.text)

    took = _now_ms() - t0
    return {
        "request_id": request_id,
        "ok": True,
        "result": text_out,
        "took_ms": took,
        "meta": meta | {"trace": bool(payload.trace)},
    }


@app.post("/v1/tasks")
async def v1_create_task(payload: V1TaskIn) -> Dict[str, Any]:
    t0 = _now_ms()
    request_id = str(uuid.uuid4())

    text = _extract_text_from_v1_task(payload)
    if not text:
        raise HTTPException(status_code=400, detail="missing task.inputs.messages[].content (or task.inputs.text)")

    out, meta = _route_and_generate(text, v1_payload=payload)
    took = _now_ms() - t0

    return {
        "ok": True,
        "request_id": request_id,
        "took_ms": took,
        "mode": "v1-hybrid",
        "client_did": payload.client_did,
        "output": {"type": "chat", "text": out},
        "meta": meta,
    }


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})
