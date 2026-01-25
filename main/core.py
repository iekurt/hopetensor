# ============================================================
# HOPEtensor — Core Routes (REAL SUMMARY, FORMAT LOCKED)
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# ============================================================

from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi.responses import PlainTextResponse

APP_NAME = "HOPEtensor"
APP_VERSION = os.getenv("APP_VERSION", "0.1.0")

DEPLOY_STAMP = (
    os.getenv("RENDER_GIT_COMMIT")
    or os.getenv("GIT_COMMIT")
    or datetime.utcnow().isoformat() + "Z"
)

# ----------------- helpers -----------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", t)
    return [p.strip() for p in parts if p and p.strip()]

def _extract_user_text(raw: str) -> str:
    """
    We ONLY summarize what comes after TEXT:
    This prevents summarizing UI instructions.
    """
    raw = raw or ""
    idx = raw.find("TEXT:")
    if idx != -1:
        return raw[idx + len("TEXT:"):].strip()
    # fallback: last block
    chunks = re.split(r"\n\s*\n", raw.strip())
    return chunks[-1].strip() if chunks else raw.strip()

def _shorten(user_text: str) -> str:
    t = _clean(user_text)
    if not t:
        return "—"
    s = _split_sentences(t)
    if not s:
        return t[:600].rstrip() + ("…" if len(t) > 600 else "")
    out = " ".join(s[:2]).strip()  # REAL shorten: first 2 sentences
    if len(out) > 600:
        out = out[:600].rstrip() + "…"
    return out if out else "—"

def _five_points(user_text: str) -> list[str]:
    t = _clean(user_text)
    if not t:
        return ["—"] * 5

    s = _split_sentences(t)
    pts = []
    for x in s:
        if len(pts) == 5:
            break
        pts.append(_clean(x)[:220] + ("…" if len(_clean(x)) > 220 else ""))

    while len(pts) < 5:
        pts.append("—")

    return pts

# ----------------- routes -----------------

def fastapi_routes(app) -> None:

    @app.get("/health", response_class=PlainTextResponse)
    def health() -> str:
        return (
            "HOPEtensor — HEALTH OK\n"
            f"Version : {APP_VERSION}\n"
            f"Deploy  : {DEPLOY_STAMP}\n"
            f"Time    : {int(time.time())}\n"
        )

    @app.get("/signature", response_class=PlainTextResponse)
    def signature() -> str:
        return (
            "HOPEtensor — Reasoning Infrastructure\n"
            "\n"
            "Author        : Erhan (master)\n"
            "Digital Twin  : Vicdan\n"
            f"Version       : {APP_VERSION}\n"
            f"Deploy        : {DEPLOY_STAMP}\n"
            "License       : Proprietary / HOPE Ecosystem\n"
            "\n"
            "\"Yurtta barış, Cihanda barış\"\n"
            "\"In GOD We HOPE\"\n"
        )

    @app.post("/reason")
    async def reason(payload: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.time()
        request_id = str(uuid.uuid4())

        raw_in = (payload.get("text") or "")
        mode = (payload.get("mode") or "short").strip().lower()
        trace = bool(payload.get("trace", False))

        user_text = _extract_user_text(raw_in)

        if mode == "five":
            pts = _five_points(user_text)
            result = "5-Point Summary:\n" + "\n".join(f"{i+1}. {pts[i]}" for i in range(5))
        else:
            result = "Shortened:\n" + _shorten(user_text)

        resp: Dict[str, Any] = {
            "ok": True,
            "request_id": request_id,
            "result": result,
            "took_ms": int((time.time() - t0) * 1000),
        }

        if trace:
            resp["meta"] = {
                "mode": mode,
                "engine": "deterministic_summary_v1",
                "deploy": DEPLOY_STAMP,
                "chars_used": len(user_text),
            }

        return resp
