from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

APP_NAME = "hopetensor-demo-api"
APP_VERSION = "0.1.0"

app = FastAPI(title=APP_NAME, version=APP_VERSION)


# -------------------------
# Models
# -------------------------
class ReasonRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to reason about")
    trace: bool = Field(False, description="Return extra debug/trace data")


class ReasonResponse(BaseModel):
    request_id: str
    ok: bool
    result: str
    took_ms: int
    meta: Dict[str, Any] = {}


# -------------------------
# Helpers (adapter)
# -------------------------
def _call_reasoning_node(text: str) -> Dict[str, Any]:
    """
    Adapter layer:
    - If your real reasoning node API exists, call it here.
    - Otherwise fallback to a deterministic placeholder response.
    """
    # Try a few common patterns without assuming your internal structure
    try:
        # Example: reasoning_node.core.think(text) -> str
        from reasoning_node.core import think  # type: ignore

        out = think(text)
        return {"result": str(out), "engine": "reasoning_node.core.think"}
    except Exception:
        pass

    try:
        # Example: reasoning_node.run(text) -> str
        import reasoning_node  # type: ignore

        if hasattr(reasoning_node, "run") and callable(reasoning_node.run):
            out = reasoning_node.run(text)
            return {"result": str(out), "engine": "reasoning_node.run"}
    except Exception:
        pass

    # Fallback
    return {
        "result": f"[fallback] Received: {text}",
        "engine": "fallback",
    }


# -------------------------
# Routes
# -------------------------
@app.get("/")
def root():
    return {"service": APP_NAME, "version": APP_VERSION}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"service": APP_NAME, "version": APP_VERSION}


@app.post("/reason", response_model=ReasonResponse)
def reason(req: ReasonRequest):
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    payload = _call_reasoning_node(req.text)

    took_ms = int((time.perf_counter() - t0) * 1000)
    resp = ReasonResponse(
        request_id=request_id,
        ok=True,
        result=payload["result"],
        took_ms=took_ms,
        meta={"engine": payload.get("engine", "unknown")},
    )

    if req.trace:
        resp.meta.update(
            {
                "pid": os.getpid(),
                "ts": int(time.time()),
            }
        )

    return resp
