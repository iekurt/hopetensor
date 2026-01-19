# ============================================================
# HOPEtensor — Minimal Reasoning Interface
#
# Author       : Erhan (master)
# Digital Twin : Vicdan
# ============================================================

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

from main.core import fastapi_routes, APP_NAME, APP_VERSION

app = FastAPI(title=APP_NAME, version=APP_VERSION)
fastapi_routes(app)


INDEX_HTML = """
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
  <button onclick="run('short')">Shorten & Explain</button>
  <button onclick="run('five')">5-Point Summary</button>
</div>

<pre id="out">ready</pre>

<script>
async function run(mode) {
  const text = document.getElementById("text").value;
  const r = await fetch("/simple?mode=" + mode, {
    method: "POST",
    headers: { "Content-Type": "text/plain; charset=utf-8" },
    body: text
  });
  document.getElementById("out").innerText = await r.text();
}
</script>

</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)


@app.post("/simple", response_class=PlainTextResponse)
async def simple_reason(text: str, mode: str = "short"):
    """
    OUTPUT RULES:
    - Plain text only
    - No JSON
    - No formatting noise
    """

    if mode == "five":
        instruction = """
Take the text below and:
- Simplify it
- Summarize it in at most 5 bullet points
- Each bullet should be 1–2 short sentences
- Output plain text only
"""
    else:
        instruction = """
Take the text below and:
- Shorten it
- Explain it in simple, clear language
- Remove unnecessary details
- Output plain text only
"""

    prompt = f"""{instruction}

Text:
{text}
"""
    return prompt.strip()
