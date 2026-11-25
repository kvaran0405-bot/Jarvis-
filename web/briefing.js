/* The boardroom: the first time JARVIS opens each day, the team reports in. Each agent's card lights up while
   they speak in their own voice. Used by the phone (home.html, solo.html) and the laptop (command-centre.html).
   JarvisBriefing.check(speak)  -> asks the laptop for today's briefing (only the first screen to open gets it)
   JarvisBriefing.play(lines, speak) -> shows and speaks [{agent, text}]; speak(agent, text) returns a promise. */
(() => {
const COL = {JARVIS: "#ffd23f", FRIDAY: "#ff5fa2", PEPPER: "#ffb347", ATHENA: "#b06bff", ZEUS: "#ffb020", HERALD: "#b06bff",
  STEVE: "#ff7a3d", VERONICA: "#ff4f7b", BANNER: "#2de0c0", EDITH: "#5fd8ff", SENTINEL: "#ff4d5e", ORACLE: "#5fd8ff"};
const ROLE = {JARVIS: "CHIEF OF STAFF", VERONICA: "FINANCE", ZEUS: "CAREER", HERALD: "COMMS", ATHENA: "STUDIES", PEPPER: "OPERATIONS",
  FRIDAY: "OPERATIONS", STEVE: "FITNESS", BANNER: "HEALTH", EDITH: "SYSTEMS", SENTINEL: "SECURITY", ORACLE: "INTEL"};
const css = document.createElement("style");
css.textContent = `#jbrief{position:fixed;inset:0;z-index:9000;display:flex;align-items:center;justify-content:center;padding:max(16px,env(safe-area-inset-top)) 16px max(16px,env(safe-area-inset-bottom));
  background:radial-gradient(circle at 50% 30%,rgba(16,26,40,.92),rgba(2,4,8,.97));backdrop-filter:blur(6px);opacity:0;transition:opacity .5s;font-family:"JetBrains Mono",monospace}
#jbrief.on{opacity:1}
#jbrief .in{width:min(640px,100%);max-height:100%;overflow:auto;display:grid;gap:10px}
#jbrief .hd{display:flex;align-items:center;gap:10px;margin-bottom:4px}
#jbrief .hd b{flex:1;font:900 clamp(11px,3.4vw,14px) Orbitron,sans-serif;letter-spacing:.3em;color:#ffd23f;text-shadow:0 0 16px #ffd23f88}
#jbrief .hd small{display:block;font:700 9px Orbitron,sans-serif;letter-spacing:.22em;color:#6d7a8c;margin-top:4px;text-shadow:none}
#jbrief .x{font:700 10px Orbitron,sans-serif;letter-spacing:.16em;color:#9fb0c3;border:1px solid #2a3544;background:none;border-radius:999px;padding:8px 12px;cursor:pointer}
#jbrief .rp{display:flex;gap:12px;align-items:flex-start;padding:12px 14px;border-radius:14px;border:1px solid rgba(255,255,255,.07);background:rgba(8,14,22,.7);
  opacity:.28;transform:translateY(8px);transition:opacity .4s,transform .4s,border-color .4s,box-shadow .4s}
#jbrief .rp.seen{opacity:.75;transform:none}
#jbrief .rp.now{opacity:1;transform:none;border-color:var(--c);box-shadow:0 0 0 1px var(--c),0 0 28px color-mix(in srgb,var(--c) 35%,transparent)}
#jbrief .av{flex:none;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font:900 13px Orbitron,sans-serif;color:#02040a;background:var(--c);box-shadow:0 0 14px var(--c)}
#jbrief .rp.now .av{animation:jbp 1s ease-in-out infinite}
@keyframes jbp{50%{box-shadow:0 0 26px var(--c),0 0 4px #fff}}
#jbrief .who{font:900 10px Orbitron,sans-serif;letter-spacing:.2em;color:var(--c)}
#jbrief .who i{font-style:normal;color:#6d7a8c;font-weight:700;margin-left:6px;letter-spacing:.16em}
#jbrief .tx{font-size:13px;line-height:1.5;color:#e8eef5;margin-top:3px}
#jbrief .go{justify-self:center;margin-top:6px;font:900 12px Orbitron,sans-serif;letter-spacing:.24em;color:#02040a;background:#ffd23f;border:0;border-radius:999px;padding:14px 22px;cursor:pointer;box-shadow:0 0 30px #ffd23f77}`;
document.head.appendChild(css);

let box = null, stopped = false;
function close(){ stopped = true; if (!box) return; box.classList.remove("on"); const b = box; box = null; setTimeout(() => b.remove(), 500); try { window.stopSpeaking?.(); } catch {} }
function render(lines){
  box?.remove(); box = document.createElement("div"); box.id = "jbrief";
  const d = new Date(), day = d.toLocaleDateString(undefined, {weekday: "long", day: "numeric", month: "long"}).toUpperCase();
  box.innerHTML = `<div class="in"><div class="hd"><b>🏢 DAILY BRIEFING<small>${day} · YOUR TEAM REPORTING</small></b><button class="x">✕ CLOSE</button></div>
    ${lines.map((l, i) => `<div class="rp" data-i="${i}" style="--c:${COL[l.agent] || "#5fd8ff"}"><div class="av">${l.agent[0]}</div><div><div class="who">${l.agent}<i>${ROLE[l.agent] || ""}</i></div><div class="tx"></div></div></div>`).join("")}</div>`;
  lines.forEach((l, i) => { box.querySelector(`[data-i="${i}"] .tx`).textContent = l.text; });
  box.querySelector(".x").onclick = close;
  document.body.appendChild(box); requestAnimationFrame(() => box && box.classList.add("on"));
  return box;
}
async function play(lines, speak){
  if (!lines || !lines.length) return;
  stopped = false; const b = render(lines);
  // a browser may block sound until you tap once: then the briefing waits for that tap
  const needTap = !window.JarvisNative && navigator.userActivation && !navigator.userActivation.hasBeenActive;
  if (needTap){ await new Promise(res => { const g = document.createElement("button"); g.className = "go"; g.textContent = "▶ HEAR THE BRIEFING"; b.querySelector(".in").appendChild(g);
    g.onclick = () => { g.remove(); res(); }; }); }
  for (let i = 0; i < lines.length && !stopped; i++){
    const el = b.querySelector(`[data-i="${i}"]`); b.querySelectorAll(".rp.now").forEach(x => { x.classList.remove("now"); x.classList.add("seen"); });
    el.classList.add("now"); el.scrollIntoView({block: "nearest", behavior: "smooth"});
    try { await Promise.race([speak(lines[i].agent, lines[i].text), new Promise(r => setTimeout(r, 4000 + lines[i].text.length * 95))]); } catch {}
    await new Promise(r => setTimeout(r, 250));
  }
  if (!stopped){ b.querySelectorAll(".rp").forEach(x => { x.classList.remove("now"); x.classList.add("seen"); }); setTimeout(() => { if (box === b) close(); }, 9000); }
}
async function check(speak, base = ""){
  try { const d = await (await fetch(base + "/api/briefing?first=1", {cache: "no-store"})).json(); if (d.new) await play(d.lines, speak); return d; } catch { return null; }
}
async function again(speak, base = ""){
  try { const d = await (await fetch(base + "/api/briefing", {cache: "no-store"})).json(); await play(d.lines, speak); return d; } catch { return null; }
}
window.JarvisBriefing = {check, play, again, close, BRIEF_RE: /^(?:hey |ok )?(?:jarvis[, ]*)?(?:give me |play )?(?:my |the |today'?s )?(?:daily )?(?:briefing|brief me|team (?:report|update)s?|status report|reports?|morning report)\??$/i};
})();
