# ============================================================
# HOPEtensor — Core Routes (CLEAN SUMMARY LOGIC)
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

# ------------------------------------------------------------
# BASIC TEXT HELPERS
# ------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]

def _strip_ui_instructions(text: str) -> str:
    """
    UI'nin başa eklediği 'Shorten / Summarize' tarzı talimatları at.
    Gerçek metni al.
    """
    if not text:
        return ""
    markers = ["TEXT:", "Text:", "Metin:", "CONTENT:", "Content:"]
    for m in markers:
        if m in text:
            return text.split(m, 1)[-1].strip()
    # çift satırdan sonrasını al
    chunks = re.split(r"\n\s*\n", text)
    return chunks[-1].strip() if chunks else text.strip()

# ------------------------------------------------------------
# SUMMARY LOGIC (VERY SIMPLE, VERY SAFE)
# ------------------------------------------------------------

def summarize_short(text: str) -> str:
    """
    Gerçek kısaltma:
    - sadece ilk 2–3 anlamlı cümle
    - yorum yok
    """
    t = _clean(text)
    if not t:
        return "—"

    sents = _split_sentences(t)
    if not sents:
        return t

    out = " ".join(sents[:2])  # bilinçli olarak KISA
    return out.strip()

def summarize_five(text: str) -> list[str]:
    """
    Gerçek 5 madde:
    - ilk 5 anlamlı cümle
    - yoksa tekrar ETMEZ, em dash koymaz
    """
    t = _clean(text)
    if not t:
        return ["—", "—", "—", "—", "—"]

    sents = _split_sentences(t)
    points: list[str] = []

    for s in sents:
        if len(points) == 5:
            break
        points.append(s.strip())

    # eğer metin kısa ise, kalanları boş bırak
    while len(points) < 5:
        points.append("—")

    return points

# ------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------

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

        raw_text = payload.get("text", "") or ""
        mode = (payload.get("mode") or "short").lower()
        trace = bool(payload.get("trace", False))

        user_text = _strip_ui_instructions(raw_text)

        if mode == "five":
            pts = summarize_five(user_text)
            result = "5-Point Summary:\n" + "\n".join(
                f"{i+1}. {pts[i]}" for i in range(5)
            )
        else:
            short = summarize_short(user_text)
            result = "Shortened:\n" + short

        resp: Dict[str, Any] = {
            "ok": True,
            "request_id": request_id,
            "result": result,
            "took_ms": int((time.time() - t0) * 1000),
        }

        if trace:
            resp["meta"] = {
                "mode": mode,
                "chars_in": len(raw_text),
                "chars_used": len(user_text),
                "chars_out": len(result),
                "deploy": DEPLOY_STAMP,
            }

        return resp
