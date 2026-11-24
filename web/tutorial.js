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
  {id: "hearing", title: "Talk like you normally do", what: "JARVIS now listens in Singapore English and knows your names and places. On the laptop, tap 🎙 and just talk: it stops when you stop. If it misses you, it asks you to say it again.", todo: "Tap 🎙 and say: “Pepper, how's the Shaabaz quote for the Tan wedding?”", say: /pepper|shaabaz|tan wedding/i},
  {id: "voices", title: "Hear the team's attitude", what: "Every agent sounds like themselves: JARVIS dry, FRIDAY playful, ZEUS fired up, VERONICA sarcastic, BANNER gentle. Real breaths, laughs and sighs.", todo: "Say: “team, roast my week” and listen to each voice.", ev: "team"},
  {id: "pronounce", title: "Teach JARVIS a name", what: "JARVIS says Singapore names properly (Tampines, Bukit Timah, Shaabaz…). Teach it any name the way you say it.", todo: "Say: “pronounce Kamal as Kah-mahl” (use any name).", say: /pronounce .+ (as|like) /i},
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
  {id: "navigate", title: "Get anywhere, inside JARVIS", what: "Walk, bus/MRT, Grab (with a price range) and drive: times for the current traffic and rain, a leave-by time, and live turn-by-turn spoken by JARVIS. No Google Maps.", todo: "Say: “take me to Odeon Towers” (or type a place in “Where to, Sir?” on the map), then ▶ START.", say: /take me to|navigate to|how (do|can|should) i get to|directions to|route to/i},
  {id: "myday", title: "Your day, glowing", what: "Every night: your route replayed on the map (colour = time of day), steps, km walked, places. JARVIS also asks where you're heading when you set off.", todo: "Open the map → 📅 MY DAY → ▶ REPLAY. Or ask “how many steps did I walk today?”", say: /steps|my day|where did i go/i},
  {id: "explorer", title: "Explorer map & side quests", what: "A dark street map: places you've been glow, the rest is in shadow. 40 side quests (food, nature, heritage, views, night) unlock when you visit them.", todo: "Say: “show me my map”, tap a ? for a hint, then + ADD TO ROUTE. (On the phone, setup → “Location: all the time” keeps your trail recording.)", say: /\b(map|explorer|side ?quests?)\b/i},
  {id: "installapp", title: "Phone app in one tap", what: "Send /installapp to your JARVIS bot on Telegram: it sends the newest phone app with the 3 install steps.", todo: "Nothing to do here: tap ✓ Got it (use /installapp when the phone app updates).", manual: true},
  {id: "gps", title: "Live location & history", what: "Your phone's GPS reaches JARVIS over Wi-Fi or mobile data (keep Tailscale on). Live blue dot and today's path on the map; points saved offline catch up later.", todo: "Ask: “where was I yesterday at 3pm?” or “where did I go today?”", say: /where (was|did) i|where have i been|my (day|path)/i},
  {id: "aware", title: "JARVIS just knows", what: "Every agent automatically knows where you are, where you've been, your hours at each place, your next event and your screen time. No typing needed.", todo: "Ask: “how many hours was I at the gym this week?” or “where am I?”", say: /how (many|much) (hours|time)|where am i/i},
  {id: "chatter", title: "Friends who notice", what: "When you've been somewhere a few minutes (not home), the agent who fits the area texts you a tip: “Hi Sir, I see you're at City Hall! Lau Pa Sat is 8 minutes away…”. Max 4 a day.", todo: "Just go out! (Say “location chat off” or “on” any time.)", say: /location chat (on|off)/i},
  {id: "phonemic", title: "Your phone is the mic", what: "Talk into the JARVIS app on your phone (or send a Telegram voice note): it hears you far better, and the reply shows on BOTH screens. Only one of them talks: the laptop by default. The 💻/🔊 button at the top of the phone app (or 🔊 Voice on the laptop) picks which.", todo: "On the phone app, tap 💻 LAPTOP TALKS to switch it to 🔊 PHONE TALKS (or say “speak on my phone”). Tap again to give the voice back to the laptop.", ev: "speaker"},
  {id: "solo", title: "JARVIS without the laptop", what: "When the laptop is off or far away, the phone app becomes JARVIS by itself over Wi-Fi or mobile data: talk, reminders, directions with live buses, weather, calls, apps, tasks and your calendar. What it does alone syncs back when the laptop is on.", todo: "Open the JARVIS app once while the laptop is on (it copies what it needs). Then try it with the laptop off, or just tap ✓ Got it.", manual: true},
  {id: "nightphone", title: "Your phone, even at night", what: "With the screen off and the laptop shut, the phone's JARVIS still answers your Telegram messages and voice notes, gives the morning brief and night review, and tells you when it's time to leave or rain is coming.", todo: "Nothing to do: keep the app allowed to run in the background (setup page → Background). Tap ✓ Got it.", manual: true},
  {id: "busstop", title: "Your bus, before you ask", what: "Stand at a bus stop and a notification shows the next buses there, live. Or ask: “when's my bus?”", todo: "Next time you're at a stop, look at your notifications (needs /lta once).", manual: true},
  {id: "missed", title: "What did I miss?", what: "JARVIS sums up your notifications (never bank apps, never codes), even with the laptop off.", todo: "Ask: “what did I miss?”", say: /what did i miss|catch me up/i},
  {id: "selfcheck", title: "JARVIS checks himself", what: "Every night JARVIS tests himself, fixes what he can, and only messages you if something needs you.", todo: "Say: “Jarvis, run a system check”", say: /(system|self|health)[ -]?check/i},
  {id: "bargein", title: "Cut in, like a real conversation", what: "Start talking while JARVIS is speaking and he stops and listens. After he answers, just keep talking: no need to say “Jarvis” or tap again for 8 seconds.", todo: "Ask something long (“tell me about my week”), then talk over him.", dom: "bargein"},
  {id: "instant", title: "Instant answers", what: "Everyday questions (time, what's next, my tasks, steps, battery, weather, where am I) come back in a blink, with no thinking delay.", todo: "Ask: “what's next?”", say: /what'?s next|my tasks|how many steps|phone battery/i},
  {id: "phonevision", title: "Point and JARVIS explains", what: "In the phone app with the laptop off, tap 📷 EXPLAIN and point at a menu, a sign, your notes or a gadget: JARVIS explains, translates or reads it out.", todo: "With the laptop off, open the app and tap 📷 EXPLAIN.", manual: true},
  {id: "phoneguest", title: "Show off to friends (guest mode)", what: "Tap 🎭 GUEST (or say “guest mode on”): friends can talk to JARVIS, he's charming, and nothing private comes out.", todo: "Say: “guest mode on”, then “guest mode off”.", say: /guest mode (on|off)/i},
  {id: "phoneteam", title: "The whole team on your phone", what: "Start with a name: “Friday, …”, “Zeus, …”, and that agent answers in their own voice and colour, on the laptop and in the phone app.", todo: "On the phone, say: “Friday, what should I do tonight?”", say: /^\s*(friday|zeus|athena|oracle|steve|veronica|pepper|banner|herald|edith|sentinel)\b/i},
  {id: "stepsbody", title: "Your steps on the body hologram", what: "Holo Lab → Body: your legs light up with today's steps, with a ring of light at your feet.", todo: "Phone home → 🌐 HOLO LAB → BODY.", manual: true},
  {id: "trailer", title: "Show off: your trailer", what: "A beat-synced 3D film starring you: logo drop with a shockwave, a montage of JARVIS's powers, your city, the team, stats on the beat, warp speed, slow motion and a post-credits scene. Pick EPIC, HYPE or NOIR, a 30-second vertical Reel, add your photos and a dedication, then ⬇ save it to post.", todo: "Phone: tap 🎬 SHOW OFF. Laptop: say “show off mode”.", say: /show[- ]?off|trailer|cinematic/i},
  {id: "routines", title: "JARVIS before you ask", what: "JARVIS learns your routines from where you go (home to gym around 18:10 on Tuesdays…) and, about 15 minutes before, tells you the live way there: “Bus 15 is 4 minutes out.” Works with the laptop off too.", todo: "Ask: “what are my routines?” (it needs a couple of weeks of location history).", say: /routines|habits|when do i usually/i},
  {id: "cloud", title: "JARVIS in the cloud, 24/7 (free)", what: "Move JARVIS's brain to a free always-on server: Telegram, the night shift and the phone link run even with the laptop off, and the laptop does laptop jobs whenever it's on.", todo: "Follow docs/CLOUD.md (about 15 minutes, once), then double-click cloud-move.bat.", manual: true, laptop: true},
  {id: "tiltar", title: "Holograms on your table", what: "In the Holo Lab or Holo Sims, tilt your phone to look around a hologram, or tap 📷 AR: the hologram floats over your real table through the camera and stays put as you move.", todo: "Phone: 🌐 HOLO LAB → 📷 AR, and point at your desk.", manual: true},
  {id: "day3d", title: "Your day in 3D", what: "Holo Lab → Singapore: today's real path glows across the island (cyan in the morning, gold, then pink at night) with a comet replaying your day and your steps.", todo: "Say: “show me Singapore” (or 🌐 HOLO LAB → SINGAPORE).", say: /show (me )?singapore|map hologram/i},
  {id: "wallpaper", title: "JARVIS on your home screen", what: "A live wallpaper: the core breathing on your home screen, ripples where you touch, in your suit colour.", todo: "Phone setup page → Live wallpaper → Set wallpaper.", manual: true},
  {id: "snap", title: "Snap to summon", what: "Snap your fingers twice (or clap twice) near the laptop and JARVIS wakes up: “Yes Sir?” and he listens. Talking and music won't set it off.", todo: "Snap twice, about half a second apart, near the laptop.", ev: "wake", laptop: true},
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
["drop", "taskdrop", "room", "photo", "bargein"].forEach(n => document.addEventListener("jarvis:" + n, () => check("dom", n)));
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
