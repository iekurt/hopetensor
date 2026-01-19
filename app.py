# ============================================================
# HOPEtensor — Reasoning Infrastructure
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-19
# License       : Proprietary / HOPE Ecosystem
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"
# ============================================================

import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

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
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>HOPEtensor — Reasoning Node</title>

  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b0f14;
      --panel: rgba(255,255,255,0.04);
      --panel2: rgba(0,0,0,0.35);
      --border: rgba(255,255,255,0.12);
      --text: #e8eef6;
      --muted: rgba(232,238,246,0.72);
      --link: #93c5fd;
      --focus: rgba(147,197,253,0.55);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: var(--bg);
      color: var(--text);
    }}

    a {{ color: var(--link); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    .wrap {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 48px 20px 64px;
    }}

    .badge {{
      display:inline-flex;
      gap:10px;
      align-items:center;
      padding: 8px 12px;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: var(--panel);
      font-size: 13px;
    }}

    h1 {{
      margin: 18px 0 8px;
      font-size: 40px;
      letter-spacing: .2px;
    }}

    .sub {{
      margin: 0 0 20px;
      color: var(--muted);
      line-height: 1.4;
    }}

    .row {{
      display:grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 14px;
    }}

    @media (max-width: 900px) {{
      .row {{ grid-template-columns: 1fr; }}
    }}

    .card {{
      border: 1px solid var(--border);
      background: var(--panel);
      border-radius: 18px;
      padding: 16px;
      backdrop-filter: blur(6px);
    }}

    .k {{
      color: var(--muted);
      font-size: 12.5px;
      margin-bottom: 8px;
    }}

    textarea {{
      width: 100%;
      min-height: 220px;
      resize: vertical;
      padding: 14px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(0,0,0,0.25);
      color: var(--text);
      font-size: 15px;
      line-height: 1.4;
      outline: none;
    }}

    textarea:focus {{
      border-color: var(--focus);
      box-shadow: 0 0 0 3px rgba(147,197,253,0.15);
    }}

    .btns {{
      display:flex;
      gap: 10px;
      margin-top: 12px;
      flex-wrap: wrap;
    }}

    button {{
      padding: 10px 16px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.14);
      background: rgba(255,255,255,0.06);
      color: var(--text);
      cursor:pointer;
      font-size: 14.5px;
    }}

    button:hover {{
      background: rgba(255,255,255,0.10);
    }}

    pre {{
      margin: 0;
      padding: 14px;
      border-radius: 14px;
      background: var(--panel2);
      border: 1px solid rgba(255,255,255,0.10);
      overflow: auto;
      font-size: 12.5px;
      line-height: 1.45;
      white-space: pre-wrap;
    }}
  </style>
</head>

<body>
  <div class="wrap">
    <div class="badge">
      HOPEtensor · v{APP_VERSION} · DEPLOY: {DEPLOY_STAMP}
    </div>

    <h1>HOPEtensor Reasoning Node</h1>
    <p class="sub">
      Conscience-aware reasoning API.<br/>
      <strong>Author:</strong> Erhan (master) ·
      <strong>Digital Twin:</strong> Vicdan ·
      Proprietary / HOPE Ecosystem
    </p>

    <div class="row">
      <div class="card">
        <div class="k">Prompt</div>
        <textarea id="text" placeholder="Buraya uzun uzun yaz..."></textarea>

        <div class="btns">
          <button onclick="doReason()">Reason</button>
          <button onclick="doHealth()">Health</button>
        </div>

        <div class="k" style="margin-top:12px">Output</div>
        <pre id="out">ready</pre>
      </div>

      <div class="card">
        <div class="k">/signature</div>
        <pre id="sig">loading...</pre>

        <div class="k" style="margin-top:12px">Quick links</div>
        <p>
          <a href="/health" target="_blank">/health</a> ·
          <a href="/signature" target="_blank">/signature</a> ·
          <a href="/docs" target="_blank">/docs</a>
        </p>
      </div>
    </div>
  </div>

  <script>
    async function call(url, payload) {{
      const r = await fetch(url, payload ? {{
        method: "POST",
        headers: {{ "Content-Type": "application/json; charset=utf-8" }},
        body: JSON.stringify(payload)
      }} : {{}});
      const t = await r.text();
      try {{ return JSON.stringify(JSON.parse(t), null, 2); }}
      catch {{ return t; }}
    }}

    async function doReason() {{
      const text = document.getElementById("text").value || "";
      document.getElementById("out").innerText =
        await call("/reason", {{ text, trace: true }});
    }}

    async function doHealth() {{
      document.getElementById("out").innerText =
        await call("/health");
    }}

    fetch("/signature")
      .then(r => r.json())
      .then(s => {{
        document.getElementById("sig").innerText =
          JSON.stringify(s, null, 2);
      }})
      .catch(() => {{
        document.getElementById("sig").innerText = "signature load failed";
      }});
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
