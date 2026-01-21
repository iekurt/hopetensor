# ============================================================
# HOPEtensor — Core Routes (FORMAT LOCKED, PLAIN TEXT)
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

# ---------------- TEXT UTIL ----------------

def _clean_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())

def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    # Simple sentence splitter (good enough for TR/EN mixed)
    parts = re.split(r"(?<=[.!?])\s+|\n+", t)
    parts = [p.strip() for p in parts if p and p.strip()]
    return parts

def _strip_leading_instruction(text: str) -> str:
    """
    If the UI prepends instruction lines (Shorten/Explain...), remove them
    so we summarize ONLY the user's real content.
    We do this by cutting everything before a marker like "Text:" or "TEXT:".
    If no marker, we just keep as-is.
    """
    t = (text or "").strip()
    if not t:
        return t

    # common markers
    markers = ["TEXT:", "Text:", "Metin:", "METİN:", "CONTENT:", "Content:"]
    for m in markers:
        idx = t.find(m)
        if idx != -1:
            return t[idx + len(m):].strip()

    # also handle "...\n\n" instruction blocks
    # if there's a large instruction header, keep the last big block
    chunks = re.split(r"\n\s*\n", t)
    if len(chunks) >= 2:
        # assume last chunk is the actual content
        return chunks[-1].strip()

    return t

# ---------------- SUMMARIZERS (LLM-FREE, DETERMINISTIC) ----------------

def _shorten_text(user_text: str, max_sentences: int = 3, max_chars: int = 600) -> str:
    """
    Real shortening:
    - take first N meaningful sentences
    - clamp length
    """
    t = _clean_spaces(user_text)
    if not t:
        return "—"

    sents = _split_sentences(t)
    if not sents:
        out = t
    else:
        out = " ".join(sents[:max_sentences]).strip()

    out = _clean_spaces(out)
    if len(out) > max_chars:
        out = out[:max_chars].rstrip() + "…"
    return out if out else "—"

def _five_points(user_text: str) -> list[str]:
    """
    Real 5 points:
    - prefer sentences
    - if not enough, chunk text
    - always return 5 strings
    """
    t = _clean_spaces(user_text)
    if not t:
        return ["—", "—", "—", "—", "—"]

    sents = _split_sentences(t)
    points: list[str] = []

    # take up to 5 short sentences as points
    for s in sents:
        s2 = _clean_spaces(s)
        if not s2:
            continue
        # keep each point short-ish
        if len(s2) > 220:
            s2 = s2[:220].rstrip() + "…"
        points.append(s2)
        if len(points) == 5:
            break

    # if still not enough, chunk remaining text
    if len(points) < 5:
        # chunk the whole text into pieces
        chunk_len = max(60, len(t) // 5)
        chunks = [t[i:i+chunk_len].strip() for i in range(0, len(t), chunk_len)]
        for c in chunks:
            c2 = _clean_spaces(c)
            if c2 and c2 not in points:
                points.append(c2 if len(c2) <= 220 else c2[:220].rstrip() + "…")
            if len(points) == 5:
                break

    while len(points) < 5:
        points.append("—")

    return points[:5]

# ---------------- OUTPUT FORMAT (YOUR REQUEST: header + immediate result) ----------------

def _format_short(text: str) -> str:
    # “laf olsun ama hemen akabinde sonuç gelsin”
    return f"Shortened:\n{text}"

def _format_five(points: list[str]) -> str:
    lines = ["5-Point Summary:"]
    for i, p in enumerate(points, 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)

# ---------------- ROUTES ----------------

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

        raw_in = payload.get("text", "") or ""
        mode = (payload.get("mode") or "short").strip().lower()
        trace = bool(payload.get("trace", False))

        # summarize only the user's actual content, not the UI instruction header
        user_text = _strip_leading_instruction(raw_in)

        if mode == "five":
            pts = _five_points(user_text)
            result = _format_five(pts)
        else:
            short = _shorten_text(user_text, max_sentences=3, max_chars=600)
            result = _format_short(short)

        resp: Dict[str, Any] = {
            "ok": True,
            "request_id": request_id,
            "result": result,
            "took_ms": int((time.time() - t0) * 1000),
        }

        if trace:
            resp["meta"] = {
                "mode": mode,
                "chars_in": len(raw_in),
                "chars_used": len(user_text),
                "chars_out": len(result),
                "deploy": DEPLOY_STAMP,
            }

        return resp
