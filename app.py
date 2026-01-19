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

  <title>HOPEtensor</title>
</head>

<body>
  <main>
    <h1>HOPEtensor</h1>
    <pre id="sig">loading...</pre>
  </main>

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
