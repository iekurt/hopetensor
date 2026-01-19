async function j(url, payload) {
  const r = await fetch(url, payload ? {
    method: "POST",
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: JSON.stringify(payload)
  } : {});
  const t = await r.text();
  try { return JSON.stringify(JSON.parse(t), null, 2); } catch { return t; }
}

const out = document.getElementById("out");
document.getElementById("btnHealth").onclick = async () => out.textContent = await j("/health");
document.getElementById("btnReason").onclick = async () => {
  const text = document.getElementById("text").value || "Merhaba";
  out.textContent = await j("/reason", { text, trace: true });
};
