from __future__ import annotations

import os
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_NAME = "hopetensor-demo-api"
APP_VERSION = "0.1.0"

app = FastAPI(title=APP_NAME, version=APP_VERSION)


# -------------------------
# Models
# -------------------------
class ReasonRequest(BaseModel):
    text: str = Field(..., min_length=1)
    trace: bool = False


class ReasonResponse(BaseModel):
    request_id: str
    ok: bool
    result: str
    took_ms: int
    meta: Dict[str, Any] = Field(default_factory=dict)


# -------------------------
# Engine adapter
# -------------------------
def _call_reasoning_node(text: str) -> Dict[str, Any]:
    try:
        from reasoning_node.core import think  # type: ignore

        return {"result": str(think(text)), "engine": "reasoning_node"}
    except Exception:
        return {"result": "[fallback] Received: " + text, "engine": "fallback"}


# -------------------------
# Routes
# -------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    # IMPORTANT: not an f-string (avoids brace escaping issues in CSS/JS)
    html = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Hopetensor Demo</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      background: #0f172a;
      color: #e5e7eb;
      padding: 40px;
      max-width: 980px;
      margin: 0 auto;
    }
    h1 { color: #38bdf8; margin-bottom: 6px; }
    .sub { color: #94a3b8; margin-top: 0; }
    .card {
      background: #020617;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px;
      margin-top: 18px;
    }
    textarea {
      width: 100%;
      height: 110px;
      margin-top: 10px;
      background: #020617;
      color: #e5e7eb;
      border: 1px solid #334155;
      border-radius: 10px;
      padding: 12px;
      box-sizing: border-box;
    }
    button {
      margin-top: 10px;
      padding: 10px 14px;
      background: #38bdf8;
      border: none;
      cursor: pointer;
      font-weight: bold;
      border-radius: 10px;
    }
    button.secondary {
      background: transparent;
      color: #e5e7eb;
      border: 1px solid #334155;
      font-weight: 600;
    }
    .row { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
    .pill {
      display: inline-block;
      padding: 6px 10px;
      border: 1px solid #334155;
      border-radius: 999px;
      color: #94a3b8;
      font-size: 12px;
    }
    pre {
      margin-top: 14px;
      background: #0b1220;
      padding: 14px;
      border: 1px solid #334155;
      border-radius: 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    a { color: #38bdf8; text-decoration: none; }
    code {
      background: #0b1220;
      padding: 2px 6px;
      border-radius: 6px;
      border: 1px solid #334155;
    }
    .muted { color: #94a3b8; }
  </style>
</head>
<body>

  <h1>Hopetensor Reasoning Node</h1>
  <p class="sub">Live demo – lightweight reasoning API node.</p>

  <div class="card">
    <div class="row">
      <span class="pill" id="enginePill">engine: -</span>
      <span class="pill" id="latencyPill">took_ms: -</span>
      <span class="pill" id="reqPill">request_id: -</span>
    </div>

    <p class="muted" style="margin-top:14px; line-height:1.6; max-width: 820px;">
      Enter a prompt and run the node. This page calls <code>POST /reason</code> and prints the result.
    </p>

    <div class="row" style="margin-top: 6px;">
      <button class="secondary" onclick="setPrompt('generate a two sentence response')">2 sentences</button>
      <button class="secondary" onclick="setPrompt('summarize the idea in one paragraph')">Summarize</button>
      <button class="secondary" onclick="setPrompt('explain the concept to a child')">Explain simply</button>
      <button class="secondary" onclick="setPrompt('write 5 bullet points')">Bullets</button>
    </div>

    <textarea id="input">generate a two sentence response</textarea>

    <div class="row">
      <button onclick="run()">Run Reasoning</button>
      <button class="secondary" onclick="toggleRaw()">Toggle raw/result</button>
      <span class="muted" id="status"></span>
    </div>

    <pre id="output">Waiting...</pre>

    <hr style="margin-top:18px; border:0; border-top:1px solid #334155;">
    <p class="muted">
      <a href="/docs">API Docs</a> · <a href="/health">Health</a> · <a href="/version">Version</a>
    </p>

    <pre class="muted" style="margin-top:10px;">curl -X POST https://hopetensor.onrender.com/reason \\
  -H "Content-Type: application/json" \\
  -d '{"text":"generate a response","trace":true}'</pre>
  </div>

<script>
let last = null;
let showRaw = true;

function setPrompt(t) {
  document.getElementById("input").value = t;
}

function toggleRaw() {
  showRaw = !showRaw;
  renderOutput();
}

function renderOutput() {
  const out = document.getElementById("output");
  if (!last) {
    out.textContent = "Waiting...";
    return;
  }
  out.textContent = showRaw ? JSON.stringify(last, null, 2) : (last.result || "");
}

async function run() {
  const status = document.getElementById("status");
  status.textContent = "running...";
  try {
    const text = document.getElementById("input").value;
    const res = await fetch("/reason", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ text: text, trace: true })
    });

    const data = await res.json();
    last = data;

    document.getElementById("enginePill").textContent = "engine: " + ((data.meta && data.meta.engine) ? data.meta.engine : "-");
    document.getElementById("latencyPill").textContent = "took_ms: " + (data.took_ms ?? "-");
    document.getElementById("reqPill").textContent = "request_id: " + (data.request_id ?? "-");

    renderOutput();
    status.textContent = "ok";
  } catch (e) {
    status.textContent = "error";
    document.getElementById("output").textContent = String(e);
  }
}
</script>

</body>
</html>
"""
    return html


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
        resp.meta.update({"pid": os.getpid(), "ts": int(time.time())})

    return resp
