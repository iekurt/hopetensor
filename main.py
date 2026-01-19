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

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from main.core import fastapi_routes, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)

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
      background: radial-gradient(1200px 600px at 20% 10%, rgba(255,255,255,0.08), transparent 60%),
                  radial-gradient(900px 500px at 80% 20%, rgba(255,255,255,0.06), transparent 55%),
                  #0b0f14;
      color: #e8eef6;
    }}
    .wrap {{ max-width: 1040px; margin: 0 auto; padding: 48px 20px 64px; }}
    .badge {{
      display: inline-flex; gap: 10px; align-items: center;
      padding: 8px 12px; border: 1px solid rgba(255,255,255,0.12);
      border-radius: 999px; background: rgba(255,255,255,0.04);
      font-size: 13px; letter-spacing: 0.2px;
    }}
    .dot {{ width: 8px; height: 8px; border-radius: 50%; background: #7CFFB2; box-shadow: 0 0 18px rgba(124,255,178,0.55); }}
    h1 {{ margin: 18px 0 10px; font-size: 44px; line-height: 1.08; letter-spacing: -0.5px; }}
    .sub {{ margin: 0 0 22px; color: rgba(232,238,246,0.78); font-size: 16px; line-height: 1.5; max-width: 78ch; }}
    .grid {{ display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 16px; margin-top: 20px; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 36px; }} }}
    .card {{
      border: 1px solid rgba(255,255,255,0.12);
      background: rgba(255,255,255,0.04);
      border-radius: 18px; padding: 16px;
      box-shadow: 0 18px 60px rgba(0,0,0,0.35);
    }}
    .card h2 {{ margin: 0 0 10px; font-size: 14px; letter-spacing: 0.3px; text-transform: uppercase; color: rgba(232,238,246,0.7); }}
    .kv {{ display: grid; grid-template-columns: 140px 1fr; gap: 8px 12px; font-size: 14px; }}
    .k {{ color: rgba(232,238,246,0.6); }}
    .v {{ color: rgba(232,238,246,0.92); overflow-wrap: anywhere; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 14px; }}
    a.btn {{
      text-decoration: none; color: #0b0f14; background: #e8eef6;
      padding: 10px 12px; border-radius: 12px; font-weight: 650; font-size: 14px;
    }}
    a.btn.secondary {{
      color: #e8eef6; background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.14);
    }}
    pre {{
      margin: 0; padding: 14px; border-radius: 14px;
      background: rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.10);
      overflow: auto; font-size: 12.5px; line-height: 1.45;
    }}
    .mottos {{ margin-top: 10px; font-size: 13px; color: rgba(232,238,246,0.65); }}
  </style>
</head>

<body>
  <div class="wrap">
    <div class="badge"><span class="dot"></span> LIVE · HOPEtensor Reasoning Node · v{APP_VERSION}</div>

    <h1>HOPEtensor Reasoning Node</h1>
    <p class="sub">
      Live demo — lightweight reasoning API node.
      <br/>
      <strong>Author:</strong> Erhan (master) · <strong>Digital Twin:</strong> Vicdan · <strong>License:</strong> Proprietary / HOPE Ecosystem
    </p>

    <div class="mottos">
      “Yurtta barış, Cihanda barış” · “In GOD We HOPE”
    </div>

    <div class="grid">
      <div class="card">
        <h2>Runtime Signature</h2>
        <pre id="sig">loading...</pre>

        <div class="actions">
          <a class="btn" href="/health" target="_blank" rel="noreferrer">/health</a>
          <a class="btn secondary" href="/signature" target="_blank" rel="noreferrer">/signature</a>
          <a class="btn secondary" href="/docs" target="_blank" rel="noreferrer">/docs</a>
          <a class="btn secondary" href="/openapi.json" target="_blank" rel="noreferrer">/openapi.json</a>
        </div>
      </div>

      <div class="card">
        <h2>Identity</h2>
        <div class="kv">
          <div class="k">Brand</div><div class="v">HOPEtensor</div>
          <div class="k">Author</div><div class="v">Erhan (master)</div>
          <div class="k">Digital Twin</div><div class="v">Vicdan</div>
          <div class="k">Node</div><div class="v">Reasoning API</div>
          <div class="k">Endpoints</div><div class="v">/reason · /health · /signature</div>
        </div>
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
