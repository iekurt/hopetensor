
# main/core.py
# ============================================================
# HOPETENSOR — Reasoning Infrastructure
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-19
# License       : Proprietary / HOPE Ecosystem
#
# This file is part of the Hopetensor core reasoning system.
# Designed to serve humanity with conscience-aware AI.
#
# "Yurtta barış, Cihanda barış"
# "In GOD we HOPE"
# ============================================================

"""
Main Core – Hopetensor
Uygulamanın merkez bootstrap + routing katmanı
"""

from __future__ import annotations
import time
import uuid
from typing import Dict, Any

# reasoning engine (fallback dahil)
from reasoning_node.core import reason as reasoning_reason


APP_NAME = "hopetensor"
APP_VERSION = "0.1.0"


def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "ts": int(time.time()),
    }


def build_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "request_id": payload.get("request_id") or str(uuid.uuid4()),
        "text": payload.get("text", ""),
        "trace": bool(payload.get("trace", False)),
        "meta": payload.get("meta", {}),
    }


def process(payload: Dict[str, Any]) -> Dict[str, Any]:
    req = build_request(payload)
    start = time.time()

    result = reasoning_reason(
        text=req["text"],
        trace=req["trace"],
        meta=req["meta"],
    )

    took_ms = int((time.time() - start) * 1000)

    return {
        "request_id": req["request_id"],
        "ok": True,
        "result": result,
        "took_ms": took_ms,
    }


# FastAPI entegrasyonu için opsiyonel hook
def fastapi_routes(app):
    from fastapi import Body

    @app.get("/health")
    def _health():
        return health()

    @app.post("/reason")
    def _reason(payload: Dict[str, Any] = Body(...)):
        return process(payload)


# CLI / local test
if __name__ == "__main__":
    sample = {
        "text": "Merhaba hopetensor, 2 cümlelik bir çıktı üret",
        "trace": True,
    }
    print(process(sample))

