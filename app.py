# ============================================================
# HOPEtensor — Minimal Plain-Text UI (No JSON output)
#
# Author       : Erhan (master)
# Digital Twin : Vicdan
# ============================================================

import os
from datetime import datetime

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from main.core import fastapi_routes, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)

DEPLOY_STAMP = (
    os.getenv("RENDER_GIT_COMMIT")
    or os.getenv("GIT_COMMIT")
    or datetime.utcnow().isoformat() + "Z"
)

INDEX_HTML = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HOPEtensor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{
      margin: 0;
      padding: 36px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: #0b0f14;
      color: #e8eef6;
    }}
    .top {{
      display:flex; gap:10px; align-items:center; flex-wrap:wrap;
      margin-bottom: 12px;
      opacity: .9;
      font-size: 13px;
    }}
    textarea {{
      width: 100%;
      min-height: 220px;
      padding: 14px;
      font-size: 16px;
      background: #111827;
      color: #e8eef6;
      border: 1px solid #374151;
      border-radius: 10px;
      outline: none;
      resize: vertical;
      line-height: 1.4;
    }}
    textarea:focus {{
      border-color: rgba(147,197,253,0.55);
      box-shadow: 0 0 0 3px rgba(147,197,253,0.15);
    }}
    .btns {{
      margin-top: 12px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    button {{
      padding: 10px 16px;
      font-size: 15px;
      background: #1f2933;
      color: #e8eef6;
      border: 1px solid #374151;
      border-radius: 10px;
      cursor: pointer;
    }}
    button:hover {{ background: #273343; }}
    pre {{
      margin-top: 18px;
      padding: 16px;
      background: #020617;
      border: 1px solid #374151;
      border-radius: 10px;
      white-space: pre-wrap;
      line-height: 1.5;
      min-height: 140px;
    }}
    .muted {{ opacity: .7; }}
  </style>
</head>
<body>

<div class="top">
  <div><strong>HOPEtensor</strong></div>
  <div class="muted">v{APP_VERSION}</div>
  <div class="muted">deploy: {DEPLOY_STAMP}</div>
</div>

<textarea id="text" placeholder="Paste text here..."></textarea>

<div class="btns">
  <button onclick="run('short')">Shorten & Explain</button>
  <button onclick="run('five')">5-Point Summary</button>
</div>

<pre id="out">ready</pre>

<script>
async function run(mode) {{
  const text = document.getElementById("text").value || "";
  const r = await fetch("/plain?mode=" + encodeURIComponent(mode), {{
    method: "POST",
    headers: {{ "Content-Type": "text/plain; charset=utf-8" }},
    body: text
  }});
  document.getElementById("out").innerText = await r.text();
}}
</script>

</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)


def _extract_text(obj) -> str:
    """
    Try hard to extract a sensible plain-text answer from /reason JSON.
    We avoid showing JSON to the user.
    """
    if obj is None:
        return ""

    # common cases
    if isinstance(obj, str):
        return obj

    if isinstance(obj, dict):
        # most likely field names
        for k in ("result", "text", "answer", "output", "message"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

        # sometimes nested
        for k in ("data", "payload", "response"):
            v = obj.get(k)
            t = _extract_text(v)
            if t.strip():
                return t.strip()

        # fallback: stringify minimal
        return ""

    # list/other
    return ""


@app.post("/plain", response_class=PlainTextResponse)
async def plain(
    text: str,
    mode: str = Query(default="short", pattern="^(short|five)$"),
):
    """
    Wrapper around /reason:
    - Takes plain text input
    - Calls internal /reason
    - Returns ONLY plain text (no JSON)
    - Forces the model toward meaningful, constrained outputs
    """
    raw = (text or "").strip()
    if not raw:
        return "Please paste some text first."

    if mode == "five":
        instruction = (
            "Summarize the text below into AT MOST 5 bullet points.\n"
            "Each bullet must be 1 short sentence.\n"
            "Plain text only. No JSON. No extra commentary.\n\n"
            "TEXT:\n"
        )
    else:
        instruction = (
            "Shorten and explain the text below in simple, clear English.\n"
            "Keep it concise. Plain text only. No JSON. No extra commentary.\n\n"
            "TEXT:\n"
        )

    # We call our own /reason endpoint in-memory (no network).
    # This keeps your existing reasoning engine intact.
    payload = {"text": instruction + raw, "trace": False}

    async with httpx.AsyncClient(app=app, base_url="http://hopetensor.local") as client:
        r = await client.post("/reason", json=payload)
        try:
            data = r.json()
        except Exception:
            # if /reason ever returns non-json, just return its text
            return (r.text or "").strip() or "No response."

    out = _extract_text(data).strip()

    # If the engine returns empty/odd structure, provide a safe fallback
    if not out:
        # last attempt: maybe the whole json contains something useful
        out = str(data).strip()
        if not out:
            out = "No meaningful output produced."

    # Final cleanup to keep it plain and readable
    return out.replace("\r\n", "\n").strip()
