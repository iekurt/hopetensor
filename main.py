```python
# ============================================================
# HOPETENSOR — Reasoning Infrastructure
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-19
# License       : Proprietary / HOPE Ecosystem
#
# This file is part of the Hopetensor core reasoning system.
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


INDEX_HTML = """<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />

  <meta name="application-name" content="HOPETENSOR" />
  <meta name="author" content="Erhan (master)" />
  <meta name="digital-twin" content="Vicdan" />
  <meta name="date" content="2026-01-19" />
  <meta name="license" content="Proprietary / HOPE Ecosystem" />
  <meta name="motto-1" content="Yurtta barış, Cihanda barış" />
  <meta name="motto-2" content="In GOD We HOPE" />

  <title>HOPETENSOR</title>
</head>

<body>
  <main>
    <h1>HOPETENSOR</h1>
    <p>Author: Erhan (master)</p>
    <p>Digital Twin: Vicdan</p>
    <p>Date: 2026-01-19</p>
    <p>License: Proprietary / HOPE Ecosystem</p>
    <p>"Yurtta barış, Cihanda barış"</p>
    <p>"In GOD We HOPE"</p>
  </main>

  <script>
    window.HOPETENSOR_SIGNATURE = {
      app: "HOPETENSOR",
      author: "Erhan (master)",
      digitalTwin: "Vicdan",
      date: "2026-01-19",
      license: "Proprietary / HOPE Ecosystem",
      mottos: ["Yurtta barış, Cihanda barış", "In GOD We HOPE"]
    };
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
```
