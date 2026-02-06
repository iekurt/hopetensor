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
body{margin:0;padding:36px;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:#0b0f14;color:#e8eef6}
.links a{color:#93c5fd;margin-right:12px;text-decoration:none;font-size:13px}
.signature{margin-top:12px;padding:12px;background:#020617;border:1px solid #374151;border-radius:8px;white-space:pre-wrap;font-size:12px;line-height:1.4}
textarea{width:100%;min-height:220px;margin-top:16px;padding:14px;font-size:16px;background:#111827;color:#e8eef6;border:1px solid #374151;border-radius:8px}
.btns{margin-top:12px;display:flex;gap:10px;flex-wrap:wrap}
button{padding:10px 16px;background:#1f2933;color:#e8eef6;border:1px solid #374151;border-radius:8px;cursor:pointer}
pre{margin-top:18px;padding:16px;background:#020617;border:1px solid #374151;border-radius:8px;white-space:pre-wrap;line-height:1.55;min-height:140px}
</style>
</head>
<body>

<h2 style="margin:0">HOPEtensor</h2>
<div class="links">
  <a href="/health" target="_blank">/health</a>
  <a href="/docs" target="_blank">/docs</a>
  <a href="/signature" target="_blank">/signature</a>
</div>

<div id="sig" class="signature">loading signature…</div>

<textarea id="text" placeholder="Paste text here…"></textarea>

<div class="btns">
  <button onclick="run('short')">Shorten & Explain</button>
  <button onclick="run('five')">5-Point Summary</button>
</div>

<pre id="out">ready</pre>

<script>
async function loadSig(){
  const r = await fetch("/signature");
  document.getElementById("sig").innerText = await r.text();
}
loadSig();

async function run(mode){
  const text = document.getElementById("text").value || "";
  const payloadText = "TEXT:\\n" + text; // IMPORTANT: core summarizes only after TEXT:

  const r = await fetch("/reason", {
    method:"POST",
    headers:{ "Content-Type":"application/json; charset=utf-8" },
    body: JSON.stringify({ text: payloadText, mode: mode, trace: true })
  });

  const data = await r.json();
  document.getElementById("out").innerText = data.result || "—";
}
</script>

</body>
</html>
'''

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML)

from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}



