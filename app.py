# app.py
# HOPEtensor — Reasoning Infrastructure
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Version       : 0.1.0
# License       : Proprietary / HOPE Ecosystem
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"

from __future__ import annotations

import os
import time
import uuid
import platform
from typing import Any, Dict, Optional, List

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

APP_NAME = os.getenv("APP_NAME", "hopetensor")
ENGINE = os.getenv("ENGINE", "openai" if os.getenv("OPENAI_API_KEY") else "fallback")
VERSION = os.getenv("VERSION", "0.1.0")

# --- OpenAI-compatible settings (works with OpenAI OR any OpenAI-compatible gateway) ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "20"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "256"))
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))

# Plain-text signature (NOT JSON)
SIGNATURE_TXT = "\n".join(
    [
        "HOPEtensor — Reasoning Infrastructure",
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
    return str(x)


def _extract_text_from_v1_task(payload: V1TaskIn) -> str:
    task = payload.task or {}
    inputs = task.get("inputs") or {}

    messages = inputs.get("messages") or []
    if isinstance(messages, list) and messages:
        last = messages[-1] or {}
        if isinstance(last, dict):
            return _safe_str(last.get("content"))

    return _safe_str(inputs.get("text"))


def _fallback(prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt:
        return ""
    return f"[ok] Received: {prompt}"


def _openai_chat(prompt: str, system: str = "You are Vicdan, a helpful, concise assistant.") -> str:
    """
    OpenAI-compatible Chat Completions call.
    Works with OpenAI or any compatible gateway by setting OPENAI_BASE_URL.
    """
    url = f"{OPENAI_BASE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": OPENAI_MAX_TOKENS,
        "temperature": OPENAI_TEMPERATURE,
    }

    r = requests.post(url, headers=headers, json=body, timeout=OPENAI_TIMEOUT_S)
    r.raise_for_status()
    data = r.json()

    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        # If provider returns slightly different schema
        return _safe_str(data)


def _generate_result_text(prompt: str) -> str:
    """
    Real LLM if OPENAI_API_KEY is present; otherwise fallback.
    """
    prompt = prompt.strip()
    if not prompt:
        return ""

    if OPENAI_API_KEY:
        try:
            return _openai_chat(prompt)
        except Exception as e:
            # fail-safe: never crash the node
            return f"[fallback-after-llm-error] {_safe_str(e)} | prompt: {prompt}"

    return _fallback(prompt)


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
        "engine": ENGINE,
        "ts_ms": _now_ms(),
        "python": platform.python_version(),
        "llm": {
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

    out = _generate_result_text(payload.text)
    took = _now_ms() - t0

    return {
        "request_id": request_id,
        "ok": True,
        "result": out,
        "took_ms": took,
        "meta": {"engine": ENGINE, "ts_ms": _now_ms(), "trace": bool(payload.trace)},
    }


# ---- HOPEChain SDK compatibility shim ----
@app.post("/v1/tasks")
async def v1_create_task(payload: V1TaskIn) -> Dict[str, Any]:
    t0 = _now_ms()
    request_id = str(uuid.uuid4())

    text = _extract_text_from_v1_task(payload)
    if not text.strip():
        raise HTTPException(
            status_code=400,
            detail="missing task.inputs.messages[].content (or task.inputs.text)",
        )

    out = _generate_result_text(text)
    took = _now_ms() - t0

    return {
        "ok": True,
        "request_id": request_id,
        "took_ms": took,
        "mode": "v1-llm",
        "client_did": payload.client_did,
        "output": {"type": "chat", "text": out},
        "meta": {"engine": ENGINE, "ts_ms": _now_ms(), "model": OPENAI_MODEL if OPENAI_API_KEY else "fallback"},
    }


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})
