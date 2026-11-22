/* JARVIS Mark III interactive HUD layer.
   Sits on top of the command centre without changing its look: voice-reactive sphere, poke-able core, agents that
   answer when tapped, hover readouts, sounds, film subtitles, edge glow, tilt, agent reactions, idle chatter,
   suit themes, guest mode, birthday mode, the cinematic boot and the Stark Expo demo. */
(() => {
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const wait = ms => new Promise(r => setTimeout(r, ms));
const pick = a => a[Math.floor(Math.random() * a.length)];

// ------------------------------------------------------------------ styles
const css = document.createElement("style");
css.textContent = `
#hudEdge{position:fixed;inset:0;pointer-events:none;z-index:4;box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--c) 55%,transparent),inset 0 0 calc(20px + var(--amp,0)*60px) calc(var(--amp,0)*14px) color-mix(in srgb,var(--c) 45%,transparent);opacity:calc(.35 + var(--amp,0)*.65);transition:box-shadow .08s}
.orb .glow{transform:scale(calc(1 + var(--amp,0)*.42))}
.orb .ring{opacity:calc(.7 + var(--amp,0)*.3)}
.orb{cursor:pointer;touch-action:none}
.orb .ripple{position:absolute;inset:30%;border-radius:50%;border:2px solid var(--c);animation:ripple .7s ease-out forwards;pointer-events:none}
@keyframes ripple{to{inset:-30%;opacity:0}}
#hudSub{position:absolute;left:50%;transform:translateX(-50%);bottom:12px;width:min(720px,94%);text-align:center;pointer-events:none;z-index:3;
  font:600 15px/1.45 "JetBrains Mono",monospace;color:#fff;text-shadow:0 2px 8px #000,0 0 2px #000;opacity:0;transition:opacity .35s}
#hudSub.on{opacity:1}
#hudSub b{display:block;font:700 9px Orbitron,sans-serif;letter-spacing:.3em;margin-bottom:3px}
#core{position:relative}
#hudTip{position:fixed;z-index:30;pointer-events:none;background:rgba(7,9,13,.94);border:1px solid var(--tc,#ffd23f);padding:7px 10px;max-width:260px;font:12px/1.45 "JetBrains Mono",monospace;color:#dce7f2;opacity:0;transition:opacity .15s;box-shadow:0 0 18px color-mix(in srgb,var(--tc,#ffd23f) 25%,transparent)}
#hudTip.on{opacity:1}
#hudTip b{display:block;font:700 9px Orbitron,sans-serif;letter-spacing:.2em;color:var(--tc,#ffd23f);margin-bottom:3px}
.card{position:relative;transform-style:preserve-3d;transition:transform .2s,opacity .4s,box-shadow .4s}
.card:hover{opacity:1;transform:translateY(-2px)}
.card.working{animation:presence 1.4s ease-in-out infinite}
@keyframes presence{50%{box-shadow:0 0 26px color-mix(in srgb,var(--ac) 55%,transparent)}}
.card .zap{position:absolute;inset:0;border:1px solid var(--ac);animation:zap .6s ease-out forwards;pointer-events:none}
@keyframes zap{from{opacity:1;transform:scale(1)}to{opacity:0;transform:scale(1.25)}}
.hudReact{position:absolute;left:50%;bottom:calc(100% + 6px);transform:translateX(-50%);white-space:nowrap;background:rgba(7,9,13,.95);border:1px solid var(--ac);color:#fff;font:600 10px "JetBrains Mono",monospace;padding:3px 7px;z-index:5;animation:pop 2.6s ease forwards;pointer-events:none}
@keyframes pop{0%{opacity:0;transform:translate(-50%,6px)}12%{opacity:1;transform:translate(-50%,0)}80%{opacity:1}100%{opacity:0}}
#hudAmbient{position:absolute;left:0;top:-22px;font:500 10px "JetBrains Mono",monospace;color:var(--muted);opacity:0;transition:opacity .6s;pointer-events:none;white-space:nowrap;overflow:hidden;max-width:100%}
#hudAmbient.on{opacity:.75}
#log{position:relative}
.glitch{animation:hglitch .32s steps(3)}
@keyframes hglitch{0%{transform:translate(2px,-1px);filter:hue-rotate(35deg) saturate(1.6)}50%{transform:translate(-2px,1px)}100%{transform:none;filter:none}}
aside{transition:transform .25s ease-out}
#cmd{caret-color:var(--c)}
#bar input:focus{box-shadow:0 2px 0 0 var(--c),0 0 18px -6px var(--c)}
body[data-hud-theme] header .brand b,body[data-hud-theme] .tabs button.on,body[data-hud-theme] #bar button,body[data-hud-theme] .btn{color:var(--chrome)}
body[data-hud-theme] .tabs button.on{border-bottom-color:var(--chrome)}
body[data-hud-theme]{--line:color-mix(in srgb,var(--chrome) 22%,#1a212c)}
body.guest aside .pane,body.guest #log{filter:blur(9px);pointer-events:none;user-select:none}
body.guest aside::before{content:"GUEST MODE · PRIVATE PANELS HIDDEN";position:sticky;top:0;display:block;z-index:2;text-align:center;padding:10px;font:700 9px Orbitron,sans-serif;letter-spacing:.25em;color:#5fd8ff;background:rgba(7,9,13,.9)}
body.guest #mtabs{display:none!important}
#hudBday{display:none;position:fixed;top:52px;left:50%;transform:translateX(-50%);z-index:17;font:900 12px Orbitron,sans-serif;letter-spacing:.35em;color:#000;background:linear-gradient(90deg,#ffd23f,#ff9f3d,#ffd23f);padding:7px 18px;box-shadow:0 0 30px rgba(255,210,63,.5)}
body.birthday #hudBday{display:block}
#hudBoot{position:fixed;inset:0;z-index:40;background:#03050a;display:grid;place-items:center;transition:opacity 1s}
#hudBoot.gone{opacity:0;pointer-events:none}
#hudBoot .box{width:min(560px,90%);display:grid;gap:14px}
#hudBoot .ttl{font:900 clamp(22px,4vw,34px) Orbitron,sans-serif;letter-spacing:.3em;color:#ffd23f;text-shadow:0 0 24px rgba(255,210,63,.6)}
#hudBoot pre{margin:0;font:500 12px/1.8 "JetBrains Mono",monospace;color:#5fd8ff;white-space:pre-wrap;min-height:170px}
#hudBoot pre .ok{color:#3dff8b}
#hudBoot .scanl{position:absolute;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,#5fd8ff,transparent);animation:scanl 1.6s linear infinite;opacity:.6}
@keyframes scanl{from{top:0}to{top:100%}}
#hudExpo{position:fixed;inset:auto 0 18% 0;z-index:16;text-align:center;pointer-events:none;font:900 clamp(18px,3.2vw,36px) Orbitron,sans-serif;letter-spacing:.25em;color:var(--c);text-shadow:0 0 30px var(--c);opacity:0;transition:opacity .5s}
#hudExpo.on{opacity:1}
#fxBtn{cursor:pointer}
#hudToast{position:fixed;right:max(16px,env(safe-area-inset-right));bottom:90px;z-index:26;max-width:300px;background:rgba(7,9,13,.96);border:1px solid var(--tc,#2de0c0);border-left:3px solid var(--tc,#2de0c0);padding:10px 12px;font:12px/1.5 "JetBrains Mono",monospace;color:#dce7f2;transform:translateX(120%);transition:transform .45s cubic-bezier(.2,.9,.2,1)}
#hudToast.on{transform:none}
#hudToast b{display:block;font:700 9px Orbitron,sans-serif;letter-spacing:.2em;color:var(--tc,#2de0c0);margin-bottom:3px}
#hudDossier{position:fixed;inset:0;z-index:38;background:rgba(2,4,7,.92);display:none;place-items:center;padding:16px}
#hudDossier.on{display:grid}
#hudDossier .file{width:min(640px,100%);background:#0b1118;border:1px solid #2a3646;padding:22px 24px;position:relative;box-shadow:0 30px 80px rgba(0,0,0,.6)}
#hudDossier .stamp{position:absolute;right:18px;top:14px;font:900 12px Orbitron,sans-serif;letter-spacing:.25em;color:#ff4d5e;border:2px solid #ff4d5e;padding:4px 8px;transform:rotate(6deg);opacity:.85}
#hudDossier .k{font:700 10px Orbitron,sans-serif;letter-spacing:.3em;color:#8a95a7}
#hudDossier pre{white-space:pre-wrap;font:500 14px/1.7 "JetBrains Mono",monospace;color:#e6edf5;margin:12px 0 0;min-height:120px}
#hudDossier button{margin-top:14px;background:none;border:1px solid #ffd23f;color:#ffd23f;font:700 11px Orbitron,sans-serif;letter-spacing:.25em;padding:10px 18px;cursor:pointer}
@media (prefers-reduced-motion:reduce){.card.working,.glitch,#hudBoot .scanl{animation:none}}
`;
document.head.appendChild(css);
document.body.insertAdjacentHTML("beforeend", `<div id="hudToast"></div><div id="hudDossier"><div class="file"><span class="stamp">CLASSIFIED</span><div class="k">FOR SIR'S EYES ONLY · MISSION DOSSIER</div><pre></pre><button>ACKNOWLEDGED</button></div></div><div id="hudEdge"></div><div id="hudTip"></div><div id="hudBday">HAPPY BIRTHDAY SIR</div><div id="hudExpo"></div>`);
$("#core")?.insertAdjacentHTML("beforeend", `<div id="hudSub" aria-live="polite"></div>`);
$("#log")?.insertAdjacentHTML("afterbegin", `<div id="hudAmbient"></div>`);
const setAmp = v => document.documentElement.style.setProperty("--amp", Math.max(0, Math.min(1, v)).toFixed(3));

// ------------------------------------------------------------------ sound effects (made on the fly)
let AC = null;
const fxOn = () => { try { return localStorage.getItem("jarvis-sfx") !== "off"; } catch { return true; } };
function ctx(){ if(!AC){ try { AC = new (window.AudioContext || window.webkitAudioContext)(); } catch {} } if(AC?.state === "suspended") AC.resume().catch(() => {}); return AC; }
function tone(f, d = .1, type = "sine", vol = .035, slide = 1, delay = 0){
  const a = ctx(); if(!a || !fxOn()) return; const t = a.currentTime + delay, o = a.createOscillator(), g = a.createGain();
  o.type = type; o.frequency.setValueAtTime(f, t); o.frequency.exponentialRampToValueAtTime(Math.max(20, f * slide), t + d);
  g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(vol, t + .008); g.gain.exponentialRampToValueAtTime(.0001, t + d);
  o.connect(g); g.connect(a.destination); o.start(t); o.stop(t + d + .03);
}
function noise(d = .45, from = 400, to = 3200, vol = .12){
  const a = ctx(); if(!a || !fxOn()) return; const t = a.currentTime, b = a.createBuffer(1, a.sampleRate * d, a.sampleRate), ch = b.getChannelData(0);
  for(let i = 0; i < ch.length; i++) ch[i] = (Math.random() * 2 - 1) * (1 - i / ch.length);
  const s = a.createBufferSource(), f = a.createBiquadFilter(), g = a.createGain(); f.type = "bandpass"; f.Q.value = 1.8;
  f.frequency.setValueAtTime(from, t); f.frequency.exponentialRampToValueAtTime(to, t + d * .8); g.gain.value = vol;
  s.buffer = b; s.connect(f); f.connect(g); g.connect(a.destination); s.start(t);
}
const SFX = {
  click(){ tone(1600, .045, "square", .015, 1.3); }, hover(){ tone(2600, .025, "sine", .006); },
  send(){ tone(520, .14, "triangle", .035, 2.2); }, arrive(){ tone(880, .08, "sine", .03); tone(1320, .11, "sine", .025, 1, .07); },
  whoosh(){ noise(.4, 300, 2600, .08); }, lock(){ tone(900, .06, "sine", .04); tone(1350, .09, "sine", .04, 1, .07); },
  done(){ [523, 659, 784].forEach((f, i) => tone(f, .35, "sine", .03, 1, i * .07)); },
  alert(){ tone(740, .18, "sawtooth", .03); tone(520, .22, "sawtooth", .03, 1, .2); },
  poke(){ tone(300, .25, "sine", .06, 3); tone(1800, .06, "square", .012, 1, .05); },
  boom(){ tone(70, .9, "sine", .22, .5); tone(140, .5, "triangle", .05, .5); },
  boot(){ [220, 330, 440, 660, 880].forEach((f, i) => tone(f, .9, "sine", .045, 1.5, i * .12)); },
};
window.HUD_SFX = SFX;
document.addEventListener("pointerdown", () => ctx(), {once: true});

// FX toggle next to the voice button
const vb = $("#voiceBtn");
if(vb){ vb.insertAdjacentHTML("afterend", `<button class="pill hud" id="fxBtn" title="Interface sounds on/off">${fxOn() ? "✦ FX" : "✧ FX"}</button>`);
  $("#fxBtn").onclick = () => { try { localStorage.setItem("jarvis-sfx", fxOn() ? "off" : "on"); } catch {} $("#fxBtn").textContent = fxOn() ? "✦ FX" : "✧ FX"; SFX.click(); }; }

// ------------------------------------------------------------------ voice-reactive sphere + subtitles
let ampTimer = null, analyser = null, buf = null;
function speakStart(clip, audio){
  const sub = $("#hudSub"), color = window.AGENTS?.[clip.agent]?.color || "#ffd23f";
  const raw = String(clip.text), emo = (raw.match(/\[(laughs|chuckles|giggles|sighs|groans|gasps|scoffs|hums)\]/i) || [])[1];
  const shown = raw.replace(/\[(laughs|chuckles|giggles|sighs|groans|gasps|scoffs|hums)\]\s*/gi, (m, e) => `(${e.toLowerCase()}) `).replace(/\[\w+\]\s*/g, "");
  if(sub){ sub.innerHTML = `<b style="color:${color}">${esc(clip.agent)}</b>${esc(shown.slice(0, 220))}`; sub.classList.add("on"); }
  if(emo) emote(emo.toLowerCase());
  cancelAnimationFrame(ampTimer); analyser = null;
  if(audio && AC && AC.state === "running"){   // never reroute audio through a context that isn't allowed to play
    try { const a = AC; const src = a.createMediaElementSource(audio); analyser = a.createAnalyser(); analyser.fftSize = 512;
      buf = new Uint8Array(analyser.fftSize); src.connect(analyser); analyser.connect(a.destination); } catch { analyser = null; }
  }
  const loop = () => {
    let v;
    if(analyser){ analyser.getByteTimeDomainData(buf); let s = 0; for(const x of buf){ const d = (x - 128) / 128; s += d * d; } v = Math.sqrt(s / buf.length) * 4.2; }
    else v = .35 + Math.random() * .45 * (Math.sin(performance.now() / 90) * .5 + .5);   // computer voice: no audio to measure
    setAmp(v); ampTimer = requestAnimationFrame(loop);
  };
  if(!reduce) loop();
}
// the reactor reacts to sounds: ripple on a laugh, dim on a sigh, flicker on a gasp
function emote(e){
  const orb = $("#orb"); if(!orb || reduce) return;
  if(e === "laughs" || e === "chuckles" || e === "giggles"){ for(let i = 0; i < (e === "laughs" ? 3 : 1); i++) setTimeout(() => {
    orb.insertAdjacentHTML("beforeend", `<span class="ripple"></span>`); setTimeout(() => orb.querySelector(".ripple")?.remove(), 750); }, i * 180); }
  if(e === "sighs" || e === "groans"){ orb.animate([{filter: "brightness(1)"}, {filter: "brightness(.45)"}, {filter: "brightness(1)"}], {duration: 1400, easing: "ease-in-out"}); }
  if(e === "gasps"){ orb.animate([{transform: "scale(1)"}, {transform: "scale(1.18)"}, {transform: "scale(1)"}], {duration: 380}); glitch(orb); }
  if(e === "scoffs" || e === "hums"){ orb.animate([{transform: "translateX(0)"}, {transform: "translateX(-4px)"}, {transform: "translateX(3px)"}, {transform: "translateX(0)"}], {duration: 300}); }
}
function speakEnd(){
  cancelAnimationFrame(ampTimer); setAmp(0);
  clearTimeout(window._subT); window._subT = setTimeout(() => $("#hudSub")?.classList.remove("on"), 1400);
}

// ------------------------------------------------------------------ poke the core, drag to spin the globe
const orbEl = $("#orb");
if(orbEl){
  let down = null, spin = 0;
  orbEl.addEventListener("pointerdown", e => { down = {x: e.clientX, moved: false}; orbEl.setPointerCapture(e.pointerId); });
  orbEl.addEventListener("pointermove", e => { if(!down) return; const dx = e.clientX - down.x; if(Math.abs(dx) > 4) down.moved = true;
    if(down.moved){ spin += dx * .8; down.x = e.clientX; const g = $("#globe"); if(g) g.style.transform = `rotate(${spin}deg)`; } });
  orbEl.addEventListener("pointerup", () => { if(down && !down.moved){
      orbEl.insertAdjacentHTML("beforeend", `<span class="ripple"></span>`); setTimeout(() => orbEl.querySelector(".ripple")?.remove(), 750);
      SFX.poke(); fetch("/api/poke", {method: "POST"}).catch(() => {}); }
    else if(down) SFX.whoosh();
    down = null; });
}

// ------------------------------------------------------------------ agents: tap to hear them, hover for a readout
let QUIPS = {}, quipsAt = 0;
async function quips(){ if(Date.now() - quipsAt > 20000){ try { QUIPS = await (await fetch("/api/quips")).json(); quipsAt = Date.now(); } catch {} } return QUIPS; }
const tip = $("#hudTip");
function showTip(el, title, text, color){ tip.style.setProperty("--tc", color); tip.innerHTML = `<b>${esc(title)}</b>${esc(text)}`;
  const r = el.getBoundingClientRect(); tip.style.left = Math.min(innerWidth - 270, Math.max(8, r.left)) + "px"; tip.style.top = (r.bottom + 8) + "px"; tip.classList.add("on"); }
const hideTip = () => tip.classList.remove("on");
function wireCards(){
  document.querySelectorAll(".card").forEach(c => {
    if(c.dataset.fx) return; c.dataset.fx = 1; const n = c.dataset.a;
    c.addEventListener("mouseenter", async () => { SFX.hover(); const q = await quips(); if(c.matches(":hover")) showTip(c, `${n} · ${window.AGENTS?.[n]?.title || ""}`, q[n] || "Standing by.", window.AGENTS?.[n]?.color); });
    c.addEventListener("mouseleave", hideTip);
    c.addEventListener("click", async () => {
      SFX.click(); hideTip(); c.insertAdjacentHTML("beforeend", `<span class="zap"></span>`); setTimeout(() => c.querySelector(".zap")?.remove(), 650);
      const q = await quips(); const line = q[n] || "Standing by, Sir.";
      window.logLine?.(n, line, "reply"); window.queueSpeech?.(n, line);
    });
  });
}
new MutationObserver(wireCards).observe(document.body, {childList: true, subtree: true});
wireCards();

// ------------------------------------------------------------------ the agents react to each other
const REACT = {
  PEPPER: [["VERONICA", "ka-ching 💰"], ["JARVIS", "splendid"]], STEVE: [["BANNER", "proud of you 💪"], ["FRIDAY", "beast mode!"]],
  ZEUS: [["FRIDAY", "ooh, go on!"], ["PEPPER", "network that"]], ATHENA: [["JARVIS", "very good"], ["ORACLE", "noted 📚"]],
  HERALD: [["PEPPER", "a client? 👀"], ["JARVIS", "on it"]], SENTINEL: [["JARVIS", "noted"], ["BANNER", "deep breaths"]],
  VERONICA: [["PEPPER", "budget ok?"], ["STEVE", "skip the bubble tea"]], ORACLE: [["ATHENA", "fascinating"], ["ZEUS", "useful"]],
  EDITH: [["JARVIS", "tidy work"]], BANNER: [["STEVE", "rest day earned"]], FRIDAY: [["JARVIS", "nicely put"]], JARVIS: [["FRIDAY", "show-off 😏"]],
};
let lastReact = 0;
function react(agent){
  if(Date.now() - lastReact < 4000 || !REACT[agent]) return; lastReact = Date.now();
  const [who, line] = pick(REACT[agent]); const card = document.getElementById("card-" + who); if(!card) return;
  card.insertAdjacentHTML("beforeend", `<span class="hudReact">${esc(line)}</span>`); setTimeout(() => card.querySelector(".hudReact")?.remove(), 2700);
  SFX.hover();
}

// ------------------------------------------------------------------ idle chatter: the lab feels alive
const CHATTER = ["FRIDAY → STEVE: did he actually go to the gym today?", "VERONICA → PEPPER: tell me that quote has margin.",
  "SENTINEL: perimeter scan complete. Nothing to report.", "ORACLE → ATHENA: found a better source for week 6.",
  "JARVIS: running diagnostics. All nominal.", "BANNER → everyone: he slept six hours. Be gentle.",
  "ZEUS → FRIDAY: three new roles tonight. I can feel it.", "EDITH: laptop at a comfortable 41°.",
  "HERALD: inbox quiet. Suspiciously quiet.", "PEPPER → JARVIS: remind me to chase Nexus at ten.",
  "STEVE → BANNER: legs day tomorrow, no excuses.", "FRIDAY: who keeps leaving tabs open?"];
let lastActive = Date.now(), chatterT = 0;
["pointermove", "keydown", "pointerdown"].forEach(e => addEventListener(e, () => { lastActive = Date.now(); $("#hudAmbient")?.classList.remove("on"); }, {passive: true}));
setInterval(() => {
  const amb = $("#hudAmbient"); if(!amb || document.hidden) return;
  if(Date.now() - lastActive > 90000 && Date.now() - chatterT > 14000){ chatterT = Date.now(); amb.textContent = pick(CHATTER); amb.classList.add("on");
    setTimeout(() => amb.classList.remove("on"), 7000); }
}, 3000);

// ------------------------------------------------------------------ glass tilt + glitch transitions
const aside = document.querySelector("aside");
if(aside && matchMedia("(pointer: fine)").matches && !reduce){
  addEventListener("pointermove", e => { const x = e.clientX / innerWidth - .5, y = e.clientY / innerHeight - .5;
    aside.style.transform = `perspective(1400px) rotateY(${(-x * 3).toFixed(2)}deg) rotateX(${(y * 1.5).toFixed(2)}deg)`; }, {passive: true});
}
function glitch(el){ if(!el || reduce) return; el.classList.remove("glitch"); void el.offsetWidth; el.classList.add("glitch"); }
document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => { SFX.whoosh(); glitch(aside); }));

// ------------------------------------------------------------------ themes, guest mode, birthday
function applyTheme(name, accent){
  if(!name || name === "classic" || !accent){ delete document.body.dataset.hudTheme; document.body.style.removeProperty("--chrome"); return; }
  document.body.dataset.hudTheme = name; document.body.style.setProperty("--chrome", accent);
}
function applyGuest(on){ document.body.classList.toggle("guest", !!on); }
async function syncHud(){
  try { const o = await (await fetch("/api/orb")).json(); applyTheme(o.theme, o.accent); applyGuest(o.guest);
    document.body.classList.toggle("birthday", !!o.birthday); if(o.birthday && !window._bdayT) window._bdayT = setInterval(() => window.confetti?.(), 90000); } catch {}
}
syncHud();

// ------------------------------------------------------------------ living HUD: time of day and real weather
(function living(){
  const tint = () => { const h = new Date().getHours();
    const c = h < 6 ? "rgba(40,60,140,.10)" : h < 11 ? "rgba(95,216,255,.06)" : h < 17 ? "rgba(255,255,255,.02)" : h < 21 ? "rgba(255,140,40,.07)" : "rgba(255,90,40,.06)";
    document.documentElement.style.setProperty("--daytint", c); };
  const st = document.createElement("style");
  st.textContent = `body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;background:var(--daytint,transparent);transition:background 3s}#hudRain{position:fixed;inset:0;pointer-events:none;z-index:1;opacity:.35}`;
  document.head.appendChild(st); tint(); setInterval(tint, 300000);
  let raining = false; const cv = document.createElement("canvas"); cv.id = "hudRain"; document.body.appendChild(cv); const x = cv.getContext("2d");
  const drops = Array.from({length: 90}, () => ({x: Math.random(), y: Math.random(), v: .6 + Math.random() * .8}));
  async function check(){ try { const g = await (await fetch("/api/greet")).json(); const hrs = g.weather?.today?.rainy_hours, now = new Date().getHours();
    raining = Array.isArray(hrs) && hrs.some(h => Math.abs(parseInt(h) - now) <= 0); } catch {} }
  check(); setInterval(check, 900000);
  (function frame(){ cv.width = innerWidth; cv.height = innerHeight; if(raining && !reduce){ x.strokeStyle = "rgba(150,200,255,.6)"; x.lineWidth = 1;
      drops.forEach(d => { d.y += d.v * .012; if(d.y > 1){ d.y = 0; d.x = Math.random(); } x.beginPath(); x.moveTo(d.x * cv.width, d.y * cv.height); x.lineTo(d.x * cv.width - 3, d.y * cv.height + 12); x.stroke(); }); }
    setTimeout(() => requestAnimationFrame(frame), raining ? 30 : 2000); })();
})();

// ------------------------------------------------------------------ events from JARVIS
function onEvent(ev){
  if(ev.type === "activity" && ev.agent && ev.agent !== "YOU" && ["job", "report", "reply"].includes(ev.kind)) react(ev.agent);
  if(ev.type === "delta_end") SFX.arrive();
  if(ev.type === "celebrate") SFX.done();
  if(ev.type === "alert") SFX.alert();
  if(ev.type === "status" && ev.state === "working") SFX.hover();
  if(ev.type === "theme"){ SFX.boom(); glitch(document.querySelector("main")); applyTheme(ev.theme, ev.accent); }
  if(ev.type === "guest"){ SFX.whoosh(); applyGuest(ev.on); }
  if(ev.type === "expo") expo();
  if(ev.type === "holo" && window.HOLO && !(window.HOLO.isOpen() && window.HOLO.view() === ev.view)) window.HOLO.open(ev.view);
  lastActive = Date.now();
}
document.getElementById("bar")?.addEventListener("submit", () => SFX.send());

// ------------------------------------------------------------------ cinematic boot (start-up and laptop wake)
async function boot(short = false){
  const ov = document.createElement("div"); ov.id = "hudBoot";
  ov.innerHTML = `<div class="scanl"></div><div class="box"><div class="ttl">J.A.R.V.I.S.</div><pre id="bootPre"></pre></div>`;
  document.body.appendChild(ov); SFX.boot();
  let greet = {text: "Good day Sir. All systems are yours."};
  const gp = fetch("/api/greet").then(r => r.json()).then(g => greet = g).catch(() => {});
  const pre = ov.querySelector("pre"), line = async (t, ok) => { pre.innerHTML += `> ${esc(t)}${ok ? ` <span class="ok">[OK]</span>` : ""}\n`; SFX.click(); await wait(reduce ? 0 : short ? 160 : 300); };
  await line(short ? "Waking from standby" : "Initialising neural core", true);
  await line("Arc reactor online", true);
  await line("Laptop · phone · Telegram link", true);
  await gp;
  const w = greet.weather?.today; if(w) await line(`Weather: ${Math.round(w.max_c)}°, ${w.sky}`);
  await line(`Agents ${(window.ORDER || []).length}/${(window.ORDER || []).length} reporting`, true);
  ov.classList.add("gone"); setTimeout(() => ov.remove(), 1100);
  for(const n of (window.ORDER || [])){ window.setCard?.(n, "online"); const c = document.getElementById("card-" + n);
    if(c){ c.insertAdjacentHTML("beforeend", `<span class="zap"></span>`); setTimeout(() => c.querySelector(".zap")?.remove(), 650); } SFX.hover(); await wait(reduce ? 0 : 70); }
  if(greet.birthday){ document.body.classList.add("birthday"); window.confetti?.(); }
  window.focus?.("JARVIS");
  window.logLine?.("JARVIS", greet.text, "reply");
  await window.queueSpeech?.("JARVIS", greet.text);
}
// laptop lid opened after a while: run the short boot again
let beat = Date.now();
setInterval(() => { const gap = Date.now() - beat; beat = Date.now();
  if(gap > 120000 && new URLSearchParams(location.search).get("kiosk") === "1" && !document.hidden) boot(true); }, 5000);

// ------------------------------------------------------------------ Stark Expo: the show-off demo
let expoOn = false;
async function expo(){
  if(expoOn) return; expoOn = true; const big = $("#hudExpo"), banner = async (t, ms = 2200) => { big.textContent = t; big.classList.add("on"); await wait(ms); big.classList.remove("on"); await wait(300); };
  SFX.boom(); await banner("STARK EXPO");
  const intro = {JARVIS: "I run the show. Twelve agents, one laptop, one very lucky owner.", FRIDAY: "I'm the morning brief and the evening report. I also roast him.",
    PEPPER: "I run his events business. Quotes, crew, invoices. Margins are my love language.", ATHENA: "Lectures in, study notes out. I make exams survivable.",
    ZEUS: "Every night I hunt jobs while he sleeps.", SENTINEL: "I watch the deadlines. Nothing gets past me.", STEVE: "Gym coach. Streaks are sacred.",
    VERONICA: "Money. Every dollar has a job.", BANNER: "I look after his sleep and stress. Someone has to."};
  for(const [n, t] of Object.entries(intro)){ if(!window.AGENTS?.[n]) continue; window.focus?.(n);
    SFX.lock(); window.logLine?.(n, t, "reply"); await window.queueSpeech?.(n, t); await wait(250); }
  SFX.alert(); window.redAlert?.(); await banner("RED ALERT · DEMO", 1800);
  applyTheme("ironheart", "#ff4d5e"); SFX.boom(); await wait(1500); applyTheme("wakanda", "#b06bff"); SFX.boom(); await wait(1500); syncHud();
  window.confetti?.(); SFX.done(); window.focus?.("JARVIS");
  await window.queueSpeech?.("JARVIS", "And that, ladies and gentlemen, is JARVIS. Thank you, you've been a wonderful audience.");
  await banner("THANK YOU"); expoOn = false;
}

// ------------------------------------------------------------------ toasts, mission dossier, presence
function toast(agent, text, ms = 7000){
  const t = $("#hudToast"); if(!t) return; t.style.setProperty("--tc", window.AGENTS?.[agent]?.color || "#2de0c0");
  t.innerHTML = `<b>${esc(agent)}</b>${esc(text)}`; t.classList.add("on"); SFX.arrive(); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), ms);
}
async function dossier(text){
  const d = $("#hudDossier"), pre = d.querySelector("pre"); pre.textContent = ""; d.classList.add("on"); SFX.boom();
  d.querySelector("button").onclick = () => { d.classList.remove("on"); SFX.click(); };
  const clean = String(text).replace(/\[\w+\]\s*/g, "").replace(/[#*_`]/g, "");
  for(let i = 0; i < clean.length; i += 3){ pre.textContent = clean.slice(0, i + 3); if(i % 30 === 0) SFX.click(); await wait(reduce ? 0 : 14); }
}
let presenceAt = 0;
["pointermove", "keydown"].forEach(e => addEventListener(e, () => { if(Date.now() - presenceAt > 60000){ presenceAt = Date.now(); fetch("/api/presence", {method: "POST"}).catch(() => {}); } }, {passive: true}));
const _onEvent = onEvent;
function onEvent2(ev){
  _onEvent(ev);
  if(ev.type === "nudge"){ toast(ev.agent || "BANNER", ev.text); }
  if(ev.type === "mission"){ dossier(ev.text); }
  if(ev.type === "home_arrival" && new URLSearchParams(location.search).get("kiosk") === "1") window.sendCommand?.("I'm home", "JARVIS", true);
  if(ev.type === "remote"){
    const V = ["week", "business", "body", "money", "singapore", "diagnostics", "trophies"], H = window.HOLO;
    if(ev.action === "holo") H?.open(ev.view || "week");
    if(ev.action === "holo_close") H?.close();
    if(ev.action === "expo") expo();
    if(ev.action === "stop") window.stopSpeaking?.();
    if((ev.action === "holo_next" || ev.action === "holo_prev") && H){ const i = Math.max(0, V.indexOf(H.isOpen() ? H.view() : "week"));
      H.open(V[(i + (ev.action === "holo_next" ? 1 : V.length - 1)) % V.length]); }
  }
  if(ev.type === "screenshot"){
    const t = $("#hudToast"); if(!t) return; t.style.setProperty("--tc", "#5fd8ff");
    t.innerHTML = `<b>EDITH · NEW SCREENSHOT</b>${esc(ev.name)}<div style="display:flex;gap:6px;margin-top:8px"><button class="btn" id="shotGo">Read it</button><button class="btn no" id="shotNo">Ignore</button></div>`;
    t.classList.add("on"); SFX.arrive(); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 20000);
    $("#shotNo").onclick = () => t.classList.remove("on");
    $("#shotGo").onclick = async () => { $("#shotGo").textContent = "Reading…";
      try { const r = await (await fetch("/api/screenshot/analyse", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({path: ev.path})})).json();
        t.classList.remove("on"); window.queueSpeech?.("JARVIS", r.reply || r.detail || "Done."); } catch { t.classList.remove("on"); } };
  }
}

window.HUDFX = {speakStart, speakEnd, onEvent: onEvent2, boot, expo, sfx: SFX, toast, dossier};
})();
