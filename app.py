# ============================================================
# HOPEtensor — Minimal UI (Plain Text, No JSON on Screen)
#
# Author       : Erhan (master)
# Digital Twin : Vicdan
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

  <style>
    body {
      margin: 0;
      padding: 40px;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
      background: #0b0f14;
      color: #e8eef6;
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
      margin-top: 20px;
      padding: 16px;
      background: #020617;
      border: 1px solid #374151;
      border-radius: 8px;
      white-space: pre-wrap;
      line-height: 1.5;
    }
  </style>
</head>

<body>

<h2>HOPEtensor</h2>

<textarea id="text" placeholder="Write your text here..."></textarea>

<div class="btns">
  <button onclick="runShort()">Shorten & Explain</button>
  <button onclick="runFive()">5-Point Summary</button>
</div>

<pre id="out">ready</pre>

<script>
async function callReason(prompt) {
  const r = await fetch("/reason", {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify({
      text: prompt,
      trace: false
    })
  });
  return await r.json();
}

async function runShort() {
  const text = document.getElementById("text").value || "";
  const instruction =
    "Shorten and explain the following text in simple, clear language. " +
    "Plain text only.\\n\\n";
  const data = await callReason(instruction + text);
  document.getElementById("out").innerText =
    data.result || data.text || "No meaningful output.";
}

async function runFive() {
  const text = document.getElementById("text").value || "";
  const instruction =
    "Summarize the following text into at most 5 bullet points. " +
    "Each bullet must be one short sentence. Plain text only.\\n\\n";
  const data = await callReason(instruction + text);
  document.getElementById("out").innerText =
    data.result || data.text || "No meaningful output.";
}
</script>

</body>
</html>
'''


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)
