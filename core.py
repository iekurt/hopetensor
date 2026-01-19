# ============================================================
# HOPEtensor — Reasoning Infrastructure
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-19
# License       : Proprietary / HOPE Ecosystem
#
# This file is part of the HOPEtensor core reasoning system.
# Designed to serve humanity with conscience-aware AI.
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"
# ============================================================

from __future__ import annotations

import time
import uuid
from typing import Dict, Any

from reasoning_node.core import reason as reasoning_reason
from main.runtime_signature import runtime_signature


APP_NAME = "HOPEtensor"
APP_VERSION = "0.1.0"


def health() -> Dict[str, Any]:
    sig = runtime_signature(APP_VERSION)
    return {
        "ok": True,
        "ts": int(time.time()),
        **sig,
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
        "meta": {
            **runtime_signature(APP_VERSION),
        },
    }


def fastapi_routes(app):
    from fastapi import Body
    from fastapi.responses import JSONResponse

    @app.get("/health", response_class=JSONResponse)
    def _health():
        return health()

    @app.get("/signature", response_class=JSONResponse)
    def _signature():
        return runtime_signature(APP_VERSION)

    @app.post("/reason", response_class=JSONResponse)
    def _reason(payload: Dict[str, Any] = Body(...)):
        return process(payload)


if __name__ == "__main__":
    sample = {
        "text": "Merhaba HOPEtensor, 2 cümlelik bir çıktı üret",
        "trace": True,
    }
    print(process(sample))
