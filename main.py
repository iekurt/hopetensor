from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request

from fastapi.responses import HTMLResponse


from pydantic import BaseModel, Field, ValidationError

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
    meta: Dict[str, Any] = Field(default_factory=dict)  # avoid mutable default


# -------------------------
# Helpers (adapter)
# -------------------------
def _call_reasoning_node(text: str) -> Dict[str, Any]:
    """
    Adapter layer:
    - If your real reasoning node API exists, call it here.
    - Otherwise fallback to a deterministic placeholder response.
    """
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

    return {"result": f"[fallback] Received: {text}", "engine": "fallback"}


def _decode_json_bytes(raw: bytes) -> Dict[str, Any]:
    """
    Robust JSON decoder:
    - Prefers UTF-8
    - If PowerShell/clients send UTF-16LE/BE (common with Windows PS 5.1),
      detect BOM or try UTF-16 decoding safely.
    """
    if not raw:
        raise ValueError("Empty body")

    # BOM-based detection
    if raw.startswith(b"\xff\xfe"):  # UTF-16 LE BOM
        s = raw.decode("utf-16le")
        return json.loads(s)
    if raw.startswith(b"\xfe\xff"):  # UTF-16 BE BOM
        s = raw.decode("utf-16be")
        return json.loads(s)
    if raw.startswith(b"\xef\xbb\xbf"):  # UTF-8 BOM
        s = raw.decode("utf-8-sig")
        return json.loads(s)

    # Try UTF-8 first (standard for JSON)
    try:
        s = raw.decode("utf-8")
        return json.loads(s)
    except Exception:
        pass

    # Try UTF-16 as a fallback (PowerShell 5.1 sometimes sends UTF-16LE without BOM)
    try:
        s = raw.decode("utf-16")
        return json.loads(s)
    except Exception as e:
        raise ValueError(f"Unable to decode JSON body: {e}") from e


# -------------------------
# Routes
# -------------------------

@app.get("/", response_class=HTMLResponse)
def root():
    return """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Hopetensor Demo</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e5e7eb;
      padding: 40px;
    }
    h1 { color: #38bdf8; }
    textarea {
      width: 100%;
      height: 100px;
      margin-top: 10px;
      background: #020617;
      color: #e5e7eb;
      border: 1px solid #334155;
      padding: 10px;
    }
    button {
      margin-top: 10px;
      padding: 10px 20px;
      background: #38bdf8;
      border: none;
      cursor: pointer;
      font-weight: bold;
    }
    pre {
      margin-top: 20px;
      background: #020617;
      padding: 15px;
      border: 1px solid #334155;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>

<h1>Hopetensor Reasoning Node</h1>
<p>Live demo – lightweight reasoning API node.</p>

<textarea id="input">generate a two sentence response</textarea>
<br>
<button onclick="run()">Run Reasoning</button>

<pre id="output">Waiting for input...</pre>

<script>
async function run() {
  const text = document.getElementById("input").value;
  const res = await fetch("/reason", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: text })
  });
  const data = await res.json();
  document.getElementById("output").textContent =
    JSON.stringify(data, null, 2);
}
</script>

</body>
</html>
"""



@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"service": APP_NAME, "version": APP_VERSION}


@app.post("/reason", response_model=ReasonResponse)
async def reason(request: Request):
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    # Parse JSON robustly (handles UTF-8 and UTF-16 bodies)
    try:
        raw = await request.body()
        data = _decode_json_bytes(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Validate against Pydantic model
    try:
        req = ReasonRequest.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())

    # Debug log (safe and scoped)
    print("REQ_TEXT_RAW:", req.text)

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
        resp.meta.update({"pid": os.getpid(), "ts": int(time.time())})

    return resp
