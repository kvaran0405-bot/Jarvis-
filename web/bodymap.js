/* Body map: a clear front + back muscle chart coloured by this week's training (like a fitness app).
   Muscle outlines: body-muscles by Ivan Vulović (Apache-2.0), SVG path data only - see web/vendor/body-muscles-*.txt */
(() => {
const GROUP_OF = id => {
  const rules = [["chest", /^chest/], ["shoulders", /^shoulder|^deltoid/], ["traps", /^traps/], ["lats", /^lats/],
    ["lower_back", /^lower-back/], ["biceps", /^biceps/], ["triceps", /^triceps/], ["forearms", /^forearm/],
    ["abs", /^abs/], ["obliques", /^obliques|^serratus/], ["glutes", /^gluteus/], ["quads", /^quads|^adductors|^hip-flexor/],
    ["hamstrings", /^hamstrings/], ["calves", /^calves|^tibialis/]];
  const r = rules.find(([, re]) => re.test(id)); return r ? r[0] : null;
};
const NICE = {chest: "Chest", shoulders: "Shoulders", traps: "Traps", lats: "Lats", lower_back: "Lower back", biceps: "Biceps",
  triceps: "Triceps", forearms: "Forearms", abs: "Abs", obliques: "Obliques", glutes: "Glutes", quads: "Quads",
  hamstrings: "Hamstrings", calves: "Calves"};
const heat = v => {   // rested dark glass -> neon yellow -> neon orange -> neon red-pink
  if(v <= .02) return "#121a24";
  const stops = [[0, [255, 236, 60]], [.5, [255, 120, 0]], [1, [255, 30, 80]]];
  const i = v < .5 ? 0 : 1, [a, ca] = stops[i], [b, cb] = stops[i + 1], k = (v - a) / (b - a);
  return `rgb(${ca.map((c, j) => Math.round(c + (cb[j] - c) * k)).join(",")})`;
};
let MAP = null;
async function load(){ if(!MAP) MAP = await (await fetch("/vendor/body-map.json")).json(); return MAP; }

const css = document.createElement("style");
css.textContent = `
.bmap{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(220px,1fr);gap:22px;align-items:center;width:min(1100px,94vw);max-height:86vh;color:#dce7f2;font-family:"JetBrains Mono",monospace}
@media (max-width:760px){.bmap{grid-template-columns:1fr;gap:12px;max-height:none}}
.bmap h3{margin:0 0 4px;font:700 13px Orbitron,sans-serif;letter-spacing:.28em;color:#ff8a1f}
.bmap .sub{font-size:12px;color:#8a95a7;margin-bottom:10px}
.bmap svg{width:100%;height:auto;max-height:74vh;display:block}
.bmap path{stroke:rgba(70,200,255,.35);stroke-width:.16;transition:fill .4s,filter .2s;cursor:pointer}
.bmap path.base{fill:#0d131b;stroke:rgba(70,200,255,.2)}
.bmap path.on{stroke:#fff6d0;stroke-width:.22;filter:url(#neon);animation:neonpulse 2.2s ease-in-out infinite}
.bmap path.on:nth-of-type(3n){animation-delay:.4s}.bmap path.on:nth-of-type(3n+1){animation-delay:.9s}
@keyframes neonpulse{0%,100%{opacity:1}50%{opacity:.78}}
.bmap path:hover{filter:url(#neon) brightness(1.4)}
@media (prefers-reduced-motion:reduce){.bmap path.on{animation:none}}
.bmap .cap{font:700 2px Orbitron,sans-serif;letter-spacing:.3px;fill:#8a95a7;text-anchor:middle}
.bmap .list{display:grid;gap:7px;overflow:auto;max-height:74vh;padding-right:4px}
.bmap .row{display:grid;grid-template-columns:92px 1fr 44px;gap:8px;align-items:center;font-size:12px}
.bmap .row .bar{height:8px;background:#1c2430;border-radius:4px;overflow:hidden}
.bmap .row .bar i{display:block;height:100%;border-radius:4px}
.bmap .row .pct{text-align:right;font-variant-numeric:tabular-nums;color:#c9d3e0}
.bmap .row.rest{opacity:.55}
.bmap .legend{display:flex;align-items:center;gap:8px;font-size:11px;color:#8a95a7;margin-top:10px}
.bmap .legend span{flex:1;height:8px;border-radius:4px;background:linear-gradient(90deg,#121a24,#ffec3c,#ff7800,#ff1e50);box-shadow:0 0 10px rgba(255,120,0,.5)}
.bmap .row .bar i{box-shadow:0 0 8px currentColor}
.bmap .tip{position:fixed;pointer-events:none;background:rgba(7,9,13,.95);border:1px solid #ff8a1f;padding:5px 8px;font-size:12px;z-index:60;display:none}
.bmap .credit{font-size:9px;color:#4b5666;margin-top:8px}`;
document.head.appendChild(css);

async function render(container, muscles, opts = {}){
  const map = await load(), m = muscles || {};
  const paths = map.muscles.map(r => { const g = GROUP_OF(r.id), v = g ? (m[g] || 0) : 0;
    return `<path d="${r.d}" class="${g ? (v > .02 ? "on" : "") : "base"}" style="${g ? `fill:${heat(v)}` : ""}" data-n="${r.name}" data-g="${g || ""}"></path>`; }).join("");
  const rows = Object.keys(NICE).map(k => [k, m[k] || 0]).sort((a, b) => b[1] - a[1]);
  const worked = rows.filter(([, v]) => v > .02).length;
  container.innerHTML = `<div class="bmap">
    <div><svg viewBox="${map.viewBox}" role="img" aria-label="Front and back muscle map"><defs>
      <filter id="neon" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur in="SourceGraphic" stdDeviation=".9" result="b1"/>
        <feGaussianBlur in="SourceGraphic" stdDeviation=".35" result="b2"/><feMerge><feMergeNode in="b1"/><feMergeNode in="b1"/><feMergeNode in="b2"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>${paths}
      <text class="cap" x="17.5" y="92.6">FRONT</text><text class="cap" x="54.5" y="92.6">BACK</text></svg></div>
    <div><h3>BODY MAP</h3><div class="sub">${worked} of ${rows.length} muscle groups trained in the last 7 days${opts.subtitle ? " · " + opts.subtitle : ""}</div>
      <div class="list">${rows.map(([k, v]) => `<div class="row ${v > .02 ? "" : "rest"}"><span>${NICE[k]}</span><span class="bar"><i style="width:${Math.max(2, v * 100)}%;background:${heat(Math.max(v, .03))};color:${heat(Math.max(v, .03))}"></i></span><span class="pct">${v > .02 ? Math.round(v * 100) + "%" : "rested"}</span></div>`).join("")}</div>
      <div class="legend">rested<span></span>max</div>
      <div class="credit">Muscle outlines: body-muscles (Apache-2.0)</div></div>
    <div class="tip"></div></div>`;
  const tip = container.querySelector(".tip");
  container.querySelectorAll("path").forEach(p => {
    p.addEventListener("pointermove", e => { const g = p.dataset.g; tip.style.display = "block"; tip.style.left = e.clientX + 12 + "px"; tip.style.top = e.clientY + 12 + "px";
      tip.textContent = g ? `${p.dataset.n} · ${(m[g] || 0) > .02 ? Math.round(m[g] * 100) + "% this week" : "rested"}` : p.dataset.n; });
    p.addEventListener("pointerleave", () => tip.style.display = "none");
  });
}
window.BodyMap = {render, groupOf: GROUP_OF};
})();
