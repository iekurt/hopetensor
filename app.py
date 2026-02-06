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
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

APP_NAME = os.getenv("APP_NAME", "hopetensor")
ENGINE = os.getenv("ENGINE", "fallback")
VERSION = os.getenv("VERSION", "0.1.0")

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


def _generate_result_text(prompt: str) -> str:
    prompt = prompt.strip()
    if not prompt:
        return ""
    return f"[ok] Received: {prompt}"


# -----------------------------
# Routes
# -----------------------------
@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return SIGNATURE_TXT


# index compatibility (so /index or /index.html won't 404)
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
# SDK: base_url=".../v1" then POST "{base_url}/tasks" => /v1/tasks
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
        "mode": "v1-shim",
        "client_did": payload.client_did,
        "output": {"type": "chat", "text": out},
        "meta": {"engine": ENGINE, "ts_ms": _now_ms()},
    }


@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"ok": False, "detail": exc.detail},
    )
