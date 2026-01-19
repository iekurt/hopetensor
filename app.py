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
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from main.core import fastapi_routes, APP_NAME, APP_VERSION


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)

# DEPLOY DAMGASI: Bu değişmiyorsa, yeni deploy gelmiyor demektir.
DEPLOY_STAMP = (
    os.getenv("RENDER_GIT_COMMIT")
    or os.getenv("GIT_COMMIT")
    or datetime.utcnow().isoformat() + "Z"
)

# --- STATIC MOUNT (404'ü bitiren satır) ---
# static klasörü yoksa bile deploy kırılmasın diye oluşturuyoruz
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Eğer style.css / app.js yoksa, en azından boş dönmesin diye otomatik minimal dosya yaz
STYLE_PATH = STATIC_DIR / "style.css"
APPJS_PATH = STATIC_DIR / "app.js"

if not STYLE_PATH.exists():
    STYLE_PATH.write_text(
        """
:root{color-scheme:dark}
body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;background:#0b0f14;color:#e8eef6}
.wrap{max-width:1040px;margin:0 auto;padding:48px 20px 64px}
.badge{display:inline-flex;gap:10px;align-items:center;padding:8px 12px;border:1px solid rgba(255,255,255,.12);border-radius:999px;background:rgba(255,255,255,.04);font-size:13px}
h1{margin:18px 0 8px;font-size:40px}
.sub{margin:0 0 16px;color:rgba(232,238,246,.78)}
.card{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);border-radius:18px;padding:16px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:900px){.row{grid-template-columns:1fr}}
pre{margin:0;padding:14px;border-radius:14px;background:rgba(0,0,0,.35);border:1px solid rgba(255,255,255,.10);overflow:auto;font-size:12.5px;line-height:1.45;white-space:pre-wrap}
.k{color:rgba(232,238,246,.6)}
.controls{display:flex;gap:10px;align-items:center;margin:12px 0;flex-wrap:wrap}
input{flex:1;min-width:240px;padding:10px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(0,0,0,.25);color:#e8eef6}
button{padding:10px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);color:#e8eef6;cursor:pointer}
a{color:#93c5fd}
""".strip(),
        encoding="utf-8",
    )

if not APPJS_PATH.exists():
    APPJS_PATH.write_text(
        r"""
async function callJson(url, payload) {
  const init = payload ? {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload)
  } : {};
  const r = await fetch(url, init);
  const t = await r.text();
  try { return JSON.stringify(JSON.parse(t), null, 2); } catch { return t; }
}

const out = document.getElementById("out");
const sig = document.getElementById("sig");
const ds = document.getElementById("ds");

document.getElementById("btnHealth").onclick = async () => {
  out.textContent = await callJson("/health");
};

document.getElementById("btnReason").onclick = async () => {
  const text = document.getElementById("text").value || "Merhaba HOPEtensor";
  out.textContent = await callJson("/reason", { text, trace: true });
};

fetch("/signature")
  .then(r => r.json())
  .then(s => { window.HOPETENSOR_SIGNATURE = s; sig.textContent = JSON.stringify(s, null, 2); })
  .catch(() => { sig.textContent = "signature load failed"; });

""".strip(),
        encoding="utf-8",
    )


INDEX_HTML = f"""<!doctype html>
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
 <link rel="stylesheet" href="/static/style.css?v=20260119">
</head>

<body>
  <div class="wrap">
    <div class="badge">HOPEtensor · v{APP_VERSION} · DEPLOY: <span id="ds">{DEPLOY_STAMP}</span></div>
    <h1>HOPEtensor Reasoning Node</h1>
    <p class="sub">
      Lightweight reasoning API node.<br/>
      <strong>Author:</strong> Erhan (master) · <strong>Digital Twin:</strong> Vicdan · <span class="k">License:</span> Proprietary / HOPE Ecosystem
    </p>

    <div class="row">
      <div class="card">
        <div class="k">Reason UI</div>

        <div class="controls">
          <input id="text" placeholder="Bir şey yaz..." />
          <button id="btnReason">Reason</button>
          <button id="btnHealth">Health</button>
        </div>

        <div class="k">Output</div>
        <pre id="out">ready</pre>
      </div>

      <div class="card">
        <div class="k">/signature</div>
        <pre id="sig">loading...</pre>

        <div class="k" style="margin-top:12px">Quick links</div>
        <p>
          <a href="/health" target="_blank" rel="noreferrer">/health</a> ·
          <a href="/signature" target="_blank" rel="noreferrer">/signature</a> ·
          <a href="/docs" target="_blank" rel="noreferrer">/docs</a>
        </p>
      </div>
    </div>
  </div>

  <script src="/static/app.js?v=20260119"></script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
