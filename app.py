# ============================================================
# HOPEtensor — Plain Reasoning Interface
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Purpose       : Simple, ethical, human-centered reasoning
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"
# ============================================================

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from main.core import fastapi_routes, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)


INDEX_HTML = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>HOPEtensor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />

  <style>
    body {
      margin: 0;
      padding: 36px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: #0b0f14;
      color: #e8eef6;
    }
    .header {
      margin-bottom: 18px;
    }
    .title {
      font-size: 22px;
      font-weight: 600;
    }
    .desc {
      margin-top: 6px;
      font-size: 14px;
      opacity: .8;
      line-height: 1.45;
    }
    .links {
      margin-top: 8px;
      font-size: 13px;
    }
    .links a {
      color: #93c5fd;
      text-decoration: none;
      margin-right: 12px;
    }
    textarea {
      width: 100%;
      min-height: 220px;
      padding: 14px;
      font-size: 16px;
      background: #111827;
      color: #e8eef6;
      border: 1px solid #374151;
      border-radius: 8px;
      line-height: 1.4;
    }
    .btns {
      margin-top: 12px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    button {
      padding: 10px 16px;
      font-size: 15px;
      background: #1f2933;
      color: #e8eef6;
      border: 1px solid #374151;
      border-radius: 8px;
      cursor: pointer;
    }
    pre {
      margin-top: 18px;
      padding: 16px;
      background: #020617;
      border: 1px solid #374151;
      border-radius: 8px;
      white-space: pre-wrap;
      line-height: 1.55;
      min-height: 140px;
    }
    .signature {
      margin-top: 22px;
      font-size: 12px;
      opacity: .7;
      line-height: 1.4;
    }
  </style>
</head>

<body>

<div class="header">
  <div class="title">HOPEtensor</div>
  <div class="desc">
    A minimal reasoning interface.<br/>
    Designed to shorten, clarify and summarize text<br/>
    without noise, ego or unnecessary complexity.
  </div>
  <div class="links">
    <a href="/health" target="_blank">/health</a>
    <a href="/docs" target="_blank">/docs</a>
    <a href="/signature" target="_blank">/signature</a>
  </div>
</div>

<textarea id="text" placeholder="Paste or write text here..."></textarea>

<div class="btns">
  <button onclick="runShort()">Shorten & Explain</button>
  <button onclick="runFive()">5-Point Summary</button>
</div>

<pre id="out">ready</pre>

<div class="signature">
  HOPEtensor — Ethics before power.<br/>
  Human-centered. Conscience-aware. Purpose-driven.
</div>

<script>
async function callReason(prompt) {
  const r = await fetch("/reason", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({ text: prompt, trace: false })
  });
  return await r.json();
}

function normalizeFivePoints(text) {
  // split lines, clean, enforce exactly 5 points
  let lines = text
    .split(/\\n|•|\\-/)
    .map(l => l.trim())
    .filter(l => l.length > 0);

  if (lines.length > 5) lines = lines.slice(0, 5);
  while (lines.length < 5) {
    lines.push("—");
  }

  return lines.map((l, i) => (i + 1) + ". " + l).join("\\n");
}

async function runShort() {
  const text = document.getElementById("text").value || "";
  const instruction =
    "Shorten and explain the following text in simple, clear English. " +
    "Keep it concise. Plain text only.\\n\\n";

  const data = await callReason(instruction + text);
  document.getElementById("out").innerText =
    data.result || data.text || "No meaningful output.";
}

async function runFive() {
  const text = document.getElementById("text").value || "";
  const instruction =
    "Summarize the following text into exactly 5 key points. " +
    "Each point must be one short sentence. Plain text only.\\n\\n";

  const data = await callReason(instruction + text);
  const raw = data.result || data.text || "";
  document.getElementById("out").innerText = normalizeFivePoints(raw);
}
</script>

</body>
</html>
'''


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
