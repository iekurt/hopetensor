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

import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from main.core import fastapi_routes, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)

# DEPLOY DAMGASI: Bu değişmiyorsa, yeni deploy gelmiyor demektir.
DEPLOY_STAMP = os.getenv("RENDER_GIT_COMMIT") or os.getenv("GIT_COMMIT") or datetime.utcnow().isoformat() + "Z"

INDEX_HTML = f"""<!-- ============================================================
HOPEtensor — Reasoning Infrastructure

Author        : Erhan (master)
Digital Twin  : Vicdan
Date          : 2026-01-19
License       : Proprietary / HOPE Ecosystem

This file is part of the HOPEtensor core reasoning system.
Designed to serve humanity with conscience-aware AI.

"Yurtta barış, Cihanda barış"
"In GOD We HOPE"
============================================================ -->
<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <meta name="application-name" content="HOPEtensor" />
  <meta name="brand" content="HOPEtensor" />
  <meta name="author" content="Erhan (master)" />
  <meta name="digital-twin" content="Vicdan" />
  <meta name="version" content="{APP_VERSION}" />
  <meta name="license" content="Proprietary / HOPE Ecosystem" />
  <meta name="motto-1" content="Yurtta barış, Cihanda barış" />
  <meta name="motto-2" content="In GOD We HOPE" />

  <title>HOPEtensor — Reasoning Node</title>

  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: #0b0f14;
      color: #e8eef6;
    }}
    .wrap {{ max-width: 1040px; margin: 0 auto; padding: 48px 20px 64px; }}
    .badge {{
      display: inline-flex; gap: 10px; align-items: center;
      padding: 8px 12px; border: 1px solid rgba(255,255,255,0.12);
      border-radius: 999px; background: rgba(255,255,255,0.04);
      font-size: 13px;
    }}
    h1 {{ margin: 18px 0 8px; font-size: 40px; }}
    .sub {{ margin: 0 0 16px; color: rgba(232,238,246,0.78); }}
    pre {{
      margin: 0; padding: 14px; border-radius: 14px;
      background: rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.10);
      overflow: auto; font-size: 12.5px; line-height: 1.45;
    }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
    @media (max-width: 900px) {{ .row {{ grid-template-columns: 1fr; }} }}
    .card {{ border: 1px solid rgba(255,255,255,0.12); background: rgba(255,255,255,0.04); border-radius: 18px; padding: 16px; }}
    .k {{ color: rgba(232,238,246,0.6); }}
  </style>
</head>

<body>
  <div class="wrap">
    <div class="badge">LIVE · HOPEtensor · v{APP_VERSION} · DEPLOY: <span id="ds">{DEPLOY_STAMP}</span></div>
    <h1>HOPEtensor Reasoning Node</h1>
    <p class="sub">
      Live demo — lightweight reasoning API node.<br/>
      <strong>Author:</strong> Erhan (master) · <strong>Digital Twin:</strong> Vicdan · <span class="k">License:</span> Proprietary / HOPE Ecosystem
    </p>

    <div class="row">
      <div class="card">
        <div class="k">/signature</div>
        <pre id="sig">loading...</pre>
      </div>
      <div class="card">
        <div class="k">Quick links</div>
        <p>
          <a href="/health" target="_blank" rel="noreferrer">/health</a> ·
          <a href="/signature" target="_blank" rel="noreferrer">/signature</a> ·
          <a href="/docs" target="_blank" rel="noreferrer">/docs</a>
        </p>
      </div>
    </div>
  </div>

  <script>
    fetch("/signature")
      .then(r => r.json())
      .then(s => {{
        window.HOPETENSOR_SIGNATURE = s;
        document.getElementById("sig").innerText = JSON.stringify(s, null, 2);
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
