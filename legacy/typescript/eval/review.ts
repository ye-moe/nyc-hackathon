// Human verification of labels. Agents pre-label; a person has the final say.
//
//   bun run review -- --by "Myra"     then open http://localhost:4321
//
// Shows each listing with its current label and both blind agent labels.
// Disagreements come first. Keys: 1/2/3 pick a label, Enter accepts the
// suggested one, Backspace goes back. Every save writes `label`,
// `verified_by`, and `verified_at` straight into the source .jsonl.

import { existsSync } from "node:fs";

const args = process.argv.slice(2);
const by = args[args.indexOf("--by") + 1];
if (!args.includes("--by") || !by) {
  console.error('usage: bun run review -- --by "Your Name"');
  process.exit(1);
}
const PORT = Number(process.env.PORT ?? 4321);
const FILES = ["data/labeled/dev.jsonl", "data/labeled/holdout.jsonl", "data/labeled/holdout_v2.jsonl"].filter(existsSync);
const AGENTS = { A: "data/labeled/agent/labeler_A.jsonl", B: "data/labeled/agent/labeler_B.jsonl" };

const readJsonl = async (p: string) => existsSync(p)
  ? (await Bun.file(p).text()).trim().split("\n").filter(Boolean).map((l) => JSON.parse(l)) : [];

async function queue() {
  const agent: Record<string, Record<string, any>> = {};
  for (const [k, p] of Object.entries(AGENTS)) for (const r of await readJsonl(p)) (agent[r.id] ??= {})[k] = r;
  const items = [];
  for (const file of FILES) {
    for (const r of await readJsonl(file)) {
      const a = agent[r.id] ?? {};
      const votes = [r.label, a.A?.label, a.B?.label].filter(Boolean);
      const disagree = new Set(votes).size > 1;
      const minConf = Math.min(a.A?.confidence ?? 1, a.B?.confidence ?? 1);
      items.push({ file, row: r, A: a.A, B: a.B, disagree, minConf });
    }
  }
  // Unverified first; among those, disagreements, then least-confident agent calls.
  return items.sort((x, y) =>
    Number(!!x.row.verified_by) - Number(!!y.row.verified_by) ||
    Number(y.disagree) - Number(x.disagree) || x.minConf - y.minConf);
}

async function save(file: string, id: string, label: string) {
  if (!FILES.includes(file) || !["violation", "needs_review", "no_issue_found"].includes(label)) throw new Error("bad request");
  const rows = await readJsonl(file);
  const r = rows.find((x) => x.id === id);
  if (!r) throw new Error("unknown id");
  if (r.label !== label) r.previous_label = r.label;
  Object.assign(r, { label, verified_by: by, verified_at: new Date().toISOString() });
  await Bun.write(file, rows.map((x) => JSON.stringify(x)).join("\n") + "\n");
}

Bun.serve({
  port: PORT,
  hostname: "127.0.0.1",
  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === "/api/queue") return Response.json(await queue());
    if (url.pathname === "/api/save" && req.method === "POST") {
      const { file, id, label } = await req.json();
      try { await save(file, id, label); return Response.json({ ok: true }); }
      catch (e) { return Response.json({ ok: false, error: String(e) }, { status: 400 }); }
    }
    return new Response(PAGE.replace("__BY__", JSON.stringify(by)), { headers: { "content-type": "text/html; charset=utf-8" } });
  },
});
console.log(`label review for ${by}: http://localhost:${PORT}`);

const PAGE = /* html */ `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Label review</title>
<style>
:root{--bg:#fafafa;--fg:#111;--muted:#666;--card:#fff;--line:#ddd;--v:#b3261e;--r:#8a5a00;--n:#1e6b34;--focus:#1a56db}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--muted:#aaa;--card:#1c1c1c;--line:#333;--v:#ff8a80;--r:#ffcc66;--n:#8fd19e;--focus:#8ab4ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.5 system-ui,sans-serif}
main{max-width:860px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;justify-content:space-between;align-items:baseline;gap:12px;flex-wrap:wrap}
.bar{height:6px;background:var(--line);border-radius:3px;margin:8px 0 20px}.bar>div{height:100%;background:var(--focus);border-radius:3px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:20px}
.text{font-size:1.2rem;white-space:pre-wrap;margin:8px 0 16px}
.meta{color:var(--muted);font-size:.9rem}.tag{display:inline-block;font-size:.8rem;padding:1px 8px;border-radius:10px;border:1px solid var(--line);margin-left:6px}
.dis{border-color:var(--v);color:var(--v)}
.votes{display:grid;gap:10px;margin:12px 0}.vote{border-left:4px solid var(--line);padding:4px 10px}
.violation{color:var(--v);border-color:var(--v)}.needs_review{color:var(--r);border-color:var(--r)}.no_issue_found{color:var(--n);border-color:var(--n)}
.vote .why{color:var(--fg);font-size:.95rem}
.btns{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}
button{font:inherit;padding:14px 8px;border-radius:8px;border:2px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
button:hover,button:focus-visible{outline:3px solid var(--focus);outline-offset:1px}
button.suggest{border-width:3px}button kbd{display:block;font-size:.8rem;color:var(--muted)}
.nav{display:flex;justify-content:space-between;margin-top:14px}.nav button{padding:8px 14px}
.done{text-align:center;padding:40px}
</style></head><body><main>
<header><h1 style="margin:0;font-size:1.2rem">Label review</h1><span class="meta" id="stat"></span></header>
<div class="bar"><div id="prog" style="width:0"></div></div>
<div id="app" aria-live="polite"></div>
</main><script>
const BY = __BY__, L = ["violation","needs_review","no_issue_found"];
let items = [], i = 0;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
async function load(){ items = await (await fetch("/api/queue")).json(); i = items.findIndex(x => !x.row.verified_by); if (i < 0) i = items.length; render(); }
function suggestion(it){ const v=[it.row.label,it.A?.label,it.B?.label].filter(Boolean); const c={}; v.forEach(x=>c[x]=(c[x]||0)+1); return Object.entries(c).sort((a,b)=>b[1]-a[1])[0][0]; }
function render(){
  const done = items.filter(x => x.row.verified_by).length;
  document.getElementById("stat").textContent = done + " / " + items.length + " verified · reviewer: " + BY;
  document.getElementById("prog").style.width = (100*done/items.length) + "%";
  const app = document.getElementById("app");
  if (i >= items.length) { app.innerHTML = '<div class="card done"><h2>All labels verified.</h2><p>Run <code>bun run eval</code> for the numbers.</p></div>'; return; }
  const it = items[i], s = suggestion(it), h = it.row.hints || {};
  const vote = (who, lbl, why, conf) => lbl ? '<div class="vote '+lbl+'"><b>'+who+'</b>: <span class="'+lbl+'">'+lbl+'</span>'+(conf!=null?' <span class="meta">('+Math.round(conf*100)+'% sure)</span>':'')+(why?'<div class="why">'+esc(why)+'</div>':'')+'</div>' : '';
  app.innerHTML = '<div class="card">' +
    '<div class="meta">'+esc(it.row.id)+' · '+esc(it.file.split("/").pop())+(h.monthly_rent?' · $'+h.monthly_rent+'/mo':'')+(h.bedrooms!=null?' · '+h.bedrooms+'BR':'')+
      (it.disagree?'<span class="tag dis">labels disagree</span>':'')+(it.row.verified_by?'<span class="tag">verified by '+esc(it.row.verified_by)+'</span>':'')+'</div>' +
    '<div class="text" lang="">'+esc(it.row.text)+'</div>' +
    '<div class="votes">' + vote("Current label", it.row.label, it.row.note) + vote("Agent A", it.A?.label, it.A?.rationale, it.A?.confidence) + vote("Agent B", it.B?.label, it.B?.rationale, it.B?.confidence) + '</div>' +
    '<div class="btns">' + L.map((l,k) => '<button class="'+l+(l===s?' suggest':'')+'" data-l="'+l+'">'+l.replace(/_/g," ")+'<kbd>'+(k+1)+(l===s?' · Enter':'')+'</kbd></button>').join("") + '</div>' +
    '<div class="nav"><button id="back">← Back</button><button id="skip">Skip →</button></div></div>';
  app.querySelectorAll("[data-l]").forEach(b => b.onclick = () => pick(b.dataset.l));
  document.getElementById("back").onclick = () => { i = Math.max(0, i-1); render(); };
  document.getElementById("skip").onclick = () => { i++; render(); };
}
let saving = false;
async function pick(label){
  if (saving) return;               // one save at a time; ignore extra presses
  saving = true;
  try { await save(label); } finally { saving = false; }
}
async function save(label){
  const it = items[i];
  const r = await fetch("/api/save", {method:"POST", body: JSON.stringify({file: it.file, id: it.row.id, label})});
  if (!r.ok) { alert("Save failed: " + (await r.json()).error); return; }
  it.row.label = label; it.row.verified_by = BY; i++; render();
}
addEventListener("keydown", e => {
  if (i >= items.length || e.repeat) return;   // a held-down key must not label a whole queue
  if (e.target.tagName === "BUTTON" && e.key === "Enter") return; // the button's own click handles it
  if (e.key >= "1" && e.key <= "3") pick(L[+e.key-1]);
  else if (e.key === "Enter") pick(suggestion(items[i]));
  else if (e.key === "Backspace") { i = Math.max(0, i-1); render(); }
});
load();
</script></body></html>`;
