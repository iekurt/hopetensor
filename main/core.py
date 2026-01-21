# ============================================================
# HOPEtensor — Core Routes (FORMAT LOCKED /reason)
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-21
# License       : Proprietary / HOPE Ecosystem
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"
# ============================================================

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

APP_NAME = "HOPEtensor"
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

DEPLOY_STAMP = (
    os.getenv("RENDER_GIT_COMMIT")
    or os.getenv("GIT_COMMIT")
    or datetime.utcnow().isoformat() + "Z"
)


# -----------------------------
# FORMAT LOCKS
# -----------------------------

def _clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    # basic sentence split
    parts = re.split(r"(?<=[.!?])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def _enforce_short(text: str, max_chars: int = 600) -> str:
    t = _clean_whitespace(text)
    if not t:
        return "—"
    if len(t) > max_chars:
        t = t[:max_chars].rstrip() + "…"
    return t


def _enforce_five_points(text: str) -> str:
    """
    Always returns exactly 5 numbered points.
    If fewer points exist, fills with '—'.
    If more, truncates to 5.
    """
    if not (text or "").strip():
        return "1. —\n2. —\n3. —\n4. —\n5. —"

    # Try to extract bullet-ish lines first
    raw_lines = re.split(r"\n+|•|\t| - | — |- ", text)
    lines = [l.strip() for l in raw_lines if l.strip()]

    # If not enough, use sentences
    if len(lines) < 5:
        lines = _split_sentences(text)

    # If still not enough, fall back to chunks
    if len(lines) < 5:
        t = _clean_whitespace(text)
        if t:
            # chunk roughly into 5 parts
            chunk_len = max(1, len(t) // 5)
            lines = [t[i:i+chunk_len].strip() for i in range(0, len(t), chunk_len)]
            lines = [l for l in lines if l]

    lines = lines[:5]
    while len(lines) < 5:
        lines.append("—")

    return "\n".join([f"{i+1}. {lines[i]}" for i in range(5)])


# -----------------------------
# "LLM" GENERATION (stub)
# -----------------------------

def llm_generate(prompt: str) -> str:
    """
    Replace this function with your real LLM call.
    For now it returns a sensible, deterministic transformation
    so results are NOT "random nonsense".
    """
    p = (prompt or "").strip()
    if not p:
        return ""

    # If user pasted big text, we keep it safe and concise by default.
    # This is intentionally conservative.
    return p


# -----------------------------
# ROUTES
# -----------------------------

def fastapi_routes(app) -> None:
    """
    Attach HOPEtensor routes to any FastAPI app.
    """

    @app.get("/health")
    def health() -> Dict[str, Any]:
        return {
            "ok": True,
            "service": APP_NAME,
            "version": APP_VERSION,
            "deploy": DEPLOY_STAMP,
            "ts": int(time.time()),
        }

    @app.get("/signature")
    def signature() -> Dict[str, Any]:
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "deploy": DEPLOY_STAMP,
            "author": "Erhan (master)",
            "digital_twin": "Vicdan",
            "motto_1": "Yurtta barış, Cihanda barış",
            "motto_2": "In GOD We HOPE",
            "license": "Proprietary / HOPE Ecosystem",
        }

    @app.post("/reason")
    async def reason(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        FORMAT-LOCKED endpoint.

        Input JSON:
          {
            "text": "...",
            "mode": "short" | "five",
            "trace": true|false
          }

        Output JSON:
          { "ok": true, "result": "<plain text>", ...optional meta }
        """
        t0 = time.time()
        request_id = str(uuid.uuid4())

        text = payload.get("text", "")
        mode = (payload.get("mode") or "short").strip().lower()
        trace = bool(payload.get("trace", False))

        # 1) generate raw output (LLM or stub)
        raw = llm_generate(text)

        # 2) apply FORMAT LOCK
        if mode == "five":
            result = _enforce_five_points(raw)
        else:
            # default to short
            result = _enforce_short(raw, max_chars=600)

        took_ms = int((time.time() - t0) * 1000)

        resp: Dict[str, Any] = {
            "ok": True,
            "request_id": request_id,
            "result": result,
            "took_ms": took_ms,
        }

        if trace:
            resp["meta"] = {
                "mode": mode,
                "chars_in": len(text or ""),
                "chars_out": len(result or ""),
                "engine": "stub_llm_generate",
                "deploy": DEPLOY_STAMP,
            }

        return resp
