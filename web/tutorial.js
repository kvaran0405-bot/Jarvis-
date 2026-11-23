/* Training mode: every time JARVIS starts, a short hands-on tour. Each mission makes you actually use a feature, and it
   ticks off by itself when it worked. Skip a mission, skip the whole thing, or turn it off from the panel.
   Progress is remembered on this device, so finished missions don't come back (Replay starts over). */
(() => {
const $ = s => document.querySelector(s), esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const store = {get(k, d){ try { return JSON.parse(localStorage.getItem("jarvis-tut-" + k)) ?? d; } catch { return d; } },
               set(k, v){ try { localStorage.setItem("jarvis-tut-" + k, JSON.stringify(v)); } catch {} }};
const phone = !!window.JarvisNative || matchMedia("(max-width: 700px)").matches;
// id, title, what it does, what to do, how we know it worked: {say: regex on what you send} | {ev: SSE type} | {dom: event}
const MISSIONS = [
  {id: "setup", title: "Unlock everything", what: "Give JARVIS all the access it can use, one tap at a time.", todo: "Tap “Open setup”, then keep tapping ALLOW NEXT.", go: "/access.html", dom: "setupdone"},
  {id: "talk", title: "Talk to JARVIS", what: "Push-to-talk: tap 🎙 (or Ctrl+Space) and speak. It waits until you finish.", todo: "Tap 🎙 and say: “What's on my plate today?”", voice: true},
  {id: "wake", title: "Hands-free", what: "Turn on 👂 and just say “Jarvis, …” from across the room. Follow-ups don't need “Jarvis”.", todo: "Turn on 👂 Hands-free, then say “Jarvis, what time is it?”", voice: true, wake: true},
  {id: "drop", title: "Drop a document", what: "Drag any PDF, Word, slides or photo onto the reactor (or an agent) and they read it and tell you what matters.", todo: "Drag any file from your desktop onto the glowing reactor.", dom: "drop", laptop: true},
  {id: "taskdrop", title: "Hand over a task", what: "Drag a task from the Tasks list onto an agent: they take it (and work on it in the night shift).", todo: "Say “add a task: research gym shoes”, then drag it onto ORACLE.", dom: "taskdrop", laptop: true},
  {id: "room", title: "Visit an agent's room", what: "Bond level, shared memories, their diary, gifts, what they think of the team.", todo: "Double-click FRIDAY's card (long-press on the phone).", dom: "room"},
  {id: "greet", title: "Good morning, team", what: "Your agents greet you in their own style (and nicknames once you're close).", todo: "Say or type: “good morning team”", say: /^\s*(good\s*morning|morning|gm|good\s*night|goodnight|gn)\b/i},
  {id: "nick", title: "Give yourself a nickname", what: "Each agent can call you something different.", todo: "Type: “Friday, call me Dragon”", say: /call me\s+\S/i},
  {id: "team", title: "Group call", what: "The whole team on one call, talking to you and each other in their own voices.", todo: "Say: “team, what should I do this weekend?” (or tap 🎙 Team)", ev: "team"},
  {id: "photo", title: "Team photo", what: "A neon group portrait that changes as friendships grow.", todo: "Right-click 🎙 Team (or open any room → 📸 Team photo).", dom: "photo"},
  {id: "holo", title: "Holo Lab", what: "Your week, business, body, money and Singapore as holograms.", todo: "Say: “show me my week”, then “show me my body”.", say: /show me|pull up|display|diagnostics/i},
  {id: "theme", title: "Suit themes", what: "Change the HUD colours.", todo: "Say: “switch to stealth theme” (then “classic” to go back).", ev: "theme"},
  {id: "focus", title: "Suit up (focus)", what: "Focus mode: phone silent, distractions blocked, a countdown on screen.", todo: "Say: “suit up for 25 minutes” (and “stand down focus” to end).", say: /suit up|focus mode|deep work|start focus/i},
  {id: "fast", title: "Fast mode", what: "Every reply comes from the quickest brain (Gemini Flash), with the main brain as backup.", todo: "Send /gemini to your bot on Telegram (free key, 1 minute), then say: “fast mode on”.", say: /fast (voice |reply |replies )?mode (on|off)|turn (on|off) fast/i},
  {id: "season", title: "Seasonal skins", what: "Festive looks appear on their own (Deepavali, CNY, Raya, National Day, Christmas, your birthday).", todo: "Say: “preview the Christmas skin”, then “seasonal skins auto”.", ev: "season"},
  {id: "phone", title: "Phone powers", what: "Calls, alarms, torch, music, YouTube, Shopee/Shein search, maps, screen time, your latest photo.", todo: "Say: “torch on” (then “torch off”) or “wake me at 7”.", say: /torch|flashlight|alarm|wake me|timer|play .+|youtube|shopee|shein|lazada|call \w+|screen time|last photo/i},
  {id: "ar", title: "Desk AR", what: "Your day, tasks and team float around your desk through the phone camera.", todo: "Say: “open desk AR” and hold your phone up.", say: /desk ar|ar desk|spatial desk|ar mode|augmented reality/i},
  {id: "cinema", title: "The showreel", what: "Every cinematic back to back, with sound. Perfect for showing off.", todo: "Say: “show me the cinematics”.", ev: "cinema"},
  {id: "dictate", title: "Voice typing anywhere", what: "Hold Right Alt (or the Copilot key ✦), talk, let go: JARVIS types what you said into any app (Word, email, WhatsApp Web…). Start with “Jarvis, …” to give an order instead.", todo: "Click into the box below (or open Notepad), hold Right Alt (or the Copilot key ✦) and say “testing one two three”, then let go.", ev: "dictated", laptop: true},
  {id: "photos", title: "Photo sorter", what: "Every night your phone's new photos are filed into Pictures › JARVIS Albums (Receipts, Notes & Slides, Event Setups…).", todo: "Say: “find my latest receipt” (or “sort my photos now”).", say: /photo|receipt|album/i},
  {id: "email", title: "Your inbox", what: "JARVIS reads your Gmail: briefings, an inbox sweep for what matters, smart reply drafts (you send).", todo: "Send /email to your JARVIS bot on Telegram and follow the 3 steps, then say: “anything important in my email?”", say: /e-?mail|inbox|gmail/i},
  {id: "route", title: "Your map & route", what: "Every place your phone has been lights up on the Singapore holo map; your day's stops become a route with directions on the phone.", todo: "Say: “plan my route” (or “plan a route to Orchard, then Tampines Mall”).", say: /\broute\b/i},
  {id: "explorer", title: "Explorer map & side quests", what: "A dark street map: places you've been glow, the rest is in shadow. 40 side quests (food, nature, heritage, views, night) unlock when you visit them.", todo: "Say: “show me my map”, tap a ? for a hint, then + ADD TO ROUTE. (On the phone, setup → “Location: all the time” keeps your trail recording.)", say: /\b(map|explorer|side ?quests?)\b/i},
  {id: "update", title: "One-word updates", what: "JARVIS updates itself every night. To update now, text “update” to your bot on Telegram.", todo: "Nothing to do here: tap ✓ Got it.", manual: true},
];
let done = store.get("done", {}), cur = null;
const todo = () => MISSIONS.filter(m => !done[m.id] && !(m.laptop && phone));

const css = document.createElement("style");
css.textContent = `#tut{position:fixed;right:16px;bottom:16px;z-index:60;width:min(360px,calc(100vw - 32px));background:rgba(4,10,18,.95);border:1px solid var(--ac,#ffd23f);
box-shadow:0 0 30px rgba(255,210,63,.18);padding:14px 16px;font:12px/1.55 "JetBrains Mono",monospace;color:#dce7f2;transform:translateY(20px);opacity:0;transition:.35s;pointer-events:none}
@media(max-width:700px){#tut{top:max(10px,env(safe-area-inset-top));bottom:auto}}#tut.on{transform:none;opacity:1;pointer-events:auto}#tut .k{font:700 9px Orbitron,sans-serif;letter-spacing:.25em;color:#8a95a7;display:flex;justify-content:space-between}
#tut h3{margin:6px 0 4px;font:700 13px Orbitron,sans-serif;letter-spacing:.12em;color:var(--ac,#ffd23f)}#tut .do{margin:8px 0;padding:8px 10px;border-left:2px solid var(--ac,#ffd23f);background:rgba(255,210,63,.06);color:#fff}
#tut .bar{height:3px;background:#1a2330;margin-top:8px}#tut .bar i{display:block;height:100%;background:var(--ac,#ffd23f);box-shadow:0 0 8px var(--ac,#ffd23f);transition:width .5s}
#tut .row{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}#tut button,#tut a.b{background:transparent;color:#dce7f2;border:1px solid #2a3646;padding:6px 10px;font:700 9px Orbitron,sans-serif;letter-spacing:.12em;cursor:pointer;text-decoration:none}
#tut button.p,#tut a.b.p{border-color:var(--ac,#ffd23f);color:var(--ac,#ffd23f)}#tut .ok{color:#3dff9a;font-weight:700}
#tut.win{border-color:#3dff9a;box-shadow:0 0 34px rgba(61,255,154,.35)}#tutStart{position:fixed;inset:0;z-index:61;display:grid;place-items:center;background:rgba(3,6,10,.86)}
#tutStart .c{width:min(420px,92vw);border:1px solid var(--ac,#ffd23f);background:#050b13;padding:22px;text-align:center;box-shadow:0 0 40px rgba(255,210,63,.2)}
#tutStart h2{font:700 15px Orbitron,sans-serif;letter-spacing:.3em;color:var(--ac,#ffd23f);margin:0 0 8px}#tutStart p{color:#8a95a7;font-size:12px;line-height:1.6}
#tutStart button{margin:6px 4px 0;padding:10px 16px;background:transparent;border:1px solid #2a3646;color:#dce7f2;font:700 10px Orbitron,sans-serif;letter-spacing:.15em;cursor:pointer}
#tutStart button.p{background:var(--ac,#ffd23f);color:#03060a;border-color:var(--ac,#ffd23f)}`;
document.head.appendChild(css);
document.body.insertAdjacentHTML("beforeend", `<div id="tut"></div>`);
const sfx = () => window.HUDFX?.sfx;

function show(){
  const left = todo(); cur = left[0] || null;
  const total = MISSIONS.filter(m => !(m.laptop && phone)).length, n = total - left.length;
  const box = $("#tut"); box.classList.remove("win");
  if(!cur){ box.innerHTML = `<div class="k"><span>TRAINING COMPLETE</span><span>${n}/${total}</span></div><h3>You know every feature ✓</h3>
    <div class="row"><button class="p" data-a="close">CLOSE</button><button data-a="replay">REPLAY</button></div>`; box.classList.add("on"); bind(); return; }
  box.innerHTML = `<div class="k"><span>TRAINING · MISSION ${n + 1}</span><span>${n}/${total}</span></div>
    <h3>${esc(cur.title)}</h3><div>${esc(cur.what)}</div><div class="do">▸ ${esc(cur.todo)}</div>
    <div class="bar"><i style="width:${Math.round(n / total * 100)}%"></i></div>
    <div class="row">${cur.go ? `<a class="b p" href="${cur.go}" data-go>${cur.goLabel || "OPEN SETUP"}</a>` : ""}${cur.manual ? `<button class="p" data-a="got">✓ GOT IT</button>` : ""}
      <button data-a="skip">SKIP THIS</button><button data-a="close">SKIP TUTORIAL</button><button data-a="off" title="Don't show when JARVIS starts">DON'T SHOW ON START</button></div>`;
  box.classList.add("on"); bind();
}
function bind(){
  $("#tut").querySelectorAll("[data-a]").forEach(b => b.onclick = () => {
    const a = b.dataset.a; sfx()?.click?.();
    if(a === "skip" || a === "got"){ if(a === "got") return complete(cur.id); done[cur.id] = "skipped"; store.set("done", done); show(); }
    if(a === "close") $("#tut").classList.remove("on");
    if(a === "off"){ store.set("autostart", false); $("#tut").classList.remove("on"); window.logLine?.("JARVIS", "Training won't open on start. Say “tutorial” any time to bring it back.", "system"); }
    if(a === "replay"){ done = {}; store.set("done", done); show(); }
  });
}
function complete(id){
  if(done[id] === true) return;
  done[id] = true; store.set("done", done);
  if(!cur || cur.id !== id || !$("#tut").classList.contains("on")) return;
  const box = $("#tut"); box.classList.add("win");
  box.querySelector(".do").innerHTML = `<span class="ok">✓ It works!</span> ${esc(cur.title)} done.`;
  sfx()?.done?.(); window.confetti?.();
  setTimeout(show, 2600);
}
const check = (kind, val) => MISSIONS.forEach(m => {
  if(kind === "say" && m.say && m.say.test(val.text)) complete(m.id);
  if(kind === "say" && m.voice && val.voice && (!m.wake || val.wake)) complete(m.id);
  if(kind === "ev" && m.ev === val) complete(m.id);
  if(kind === "dom" && m.dom === val) complete(m.id);
});

// watch what you do
let lastWake = 0;
const origSend = window.sendCommand;
if(typeof origSend === "function"){
  window.sendCommand = function(text, agent, voice){ check("say", {text: String(text || ""), voice: !!voice, wake: Date.now() - lastWake < 15000 || !!document.querySelector("#hands.rec")}); return origSend.apply(this, arguments); };
}
const form = $("#bar"); form?.addEventListener("submit", () => { const t = $("#cmd")?.value || ""; if(t) check("say", {text: t, voice: false}); }, true);
const hud = window.HUDFX; if(hud?.onEvent){ const o = hud.onEvent; hud.onEvent = ev => { try { if(ev?.type === "tutorial") window.TUTORIAL.on(); else if(ev?.type) check("ev", ev.type); } catch {} return o(ev); }; }
["drop", "taskdrop", "room", "photo"].forEach(n => document.addEventListener("jarvis:" + n, () => check("dom", n)));
if(new URLSearchParams(location.search).get("setup") === "done") check("dom", "setupdone");

window.TUTORIAL = {show, replay(){ done = {}; store.set("done", done); show(); }, on(){ store.set("autostart", true); show(); }};

// every start: a short welcome with Start / Skip
setTimeout(() => {
  if(store.get("autostart", true) === false || new URLSearchParams(location.search).get("kiosk") === "1" && document.hidden) return;
  const left = todo(); if(!left.length) return;
  if(window.HOLO?.isOpen?.()) return;   // don't pop up over the Holo Lab
  document.body.insertAdjacentHTML("beforeend", `<div id="tutStart"><div class="c"><h2>TRAINING MODE</h2>
    <p>${left.length} feature${left.length > 1 ? "s" : ""} to try. Each mission takes a few seconds and ticks off when it works.<br>Next up: <b style="color:#fff">${esc(left[0].title)}</b></p>
    <button class="p" id="tutGo">START</button><button id="tutSkip">SKIP</button><button id="tutNever">DON'T SHOW ON START</button></div></div>`);
  $("#tutGo").onclick = () => { $("#tutStart").remove(); show(); };
  $("#tutSkip").onclick = () => $("#tutStart").remove();
  $("#tutNever").onclick = () => { store.set("autostart", false); $("#tutStart").remove(); };
}, 6500);
})();
