/* Hand gestures through the laptop webcam (MediaPipe, runs in the browser; nothing is uploaded).
   ✋ open palm (hold) = stop talking / close   👍 = yes   👎 = no   ☝ pointing up = talk   ✌ = Holo Lab
   👋 swipe left / right = next / previous view   🤟 = a surprise.   Toggle with the ✋ button. */
(() => {
const $ = s => document.querySelector(s);
const VER = "0.10.14";
let on = false, video = null, rec = null, raf = 0, last = {name: "", since: 0, fired: 0}, track = [];

const css = document.createElement("style");
css.textContent = `#gestCam{position:fixed;left:max(14px,env(safe-area-inset-left));bottom:84px;width:168px;height:126px;z-index:27;border:1px solid #5fd8ff;box-shadow:0 0 18px rgba(95,216,255,.35);background:#000;display:none;overflow:hidden}
#gestCam.on{display:block}#gestCam video{width:100%;height:100%;object-fit:cover;transform:scaleX(-1);opacity:.75}
#gestCam b{position:absolute;left:6px;top:4px;font:700 8px Orbitron,sans-serif;letter-spacing:.2em;color:#5fd8ff}
#gestCam span{position:absolute;left:0;right:0;bottom:4px;text-align:center;font:700 11px Orbitron,sans-serif;letter-spacing:.12em;color:#ffd23f;text-shadow:0 0 8px #000}`;
document.head.appendChild(css);
document.body.insertAdjacentHTML("beforeend", `<div id="gestCam" aria-hidden="true"><video playsinline muted></video><b>GESTURES</b><span id="gestSeen"></span></div>`);
const btn = document.createElement("button"); btn.className = "pill hud"; btn.id = "gestBtn"; btn.title = "Control JARVIS with hand gestures (webcam)"; btn.textContent = "✋ Gestures";
$("#holoBtn")?.after(btn);

const flash = t => { $("#gestSeen").textContent = t; setTimeout(() => { if($("#gestSeen").textContent === t) $("#gestSeen").textContent = ""; }, 1500); };
const say = (text, agent = "JARVIS") => window.sendCommand?.(text, agent, true);
const ACTIONS = {
  Open_Palm: () => { window.stopSpeaking?.(); window.HOLO?.isOpen() && window.HOLO.close(); $("#modal") && ($("#modal").style.display = "none"); flash("STOP"); },
  Thumb_Up: () => { say("yes"); flash("YES"); },
  Thumb_Down: () => { say("no"); flash("NO"); },
  Pointing_Up: () => { window.jarvisTalk?.(); flash("LISTENING"); },
  Victory: () => { window.HOLO?.isOpen() ? window.HOLO.close() : window.HOLO?.open("week"); flash("HOLO"); },
  ILoveYou: () => { window.confetti?.(); window.queueSpeech?.("JARVIS", "Love you too, Sir. In a strictly professional capacity."); flash("🤟"); },
};
const HOLD = {Open_Palm: 600, Thumb_Up: 700, Thumb_Down: 700, Pointing_Up: 700, Victory: 700, ILoveYou: 700};
const VIEWS = ["week", "business", "body", "money", "singapore", "diagnostics", "trophies"];

function swipe(dir){
  if(window.HOLO?.isOpen()){ const i = VIEWS.indexOf(window.HOLO.view()); window.HOLO.open(VIEWS[(i + (dir > 0 ? 1 : VIEWS.length - 1)) % VIEWS.length]); }
  else { const tabs = [...document.querySelectorAll(".tabs button")], i = tabs.findIndex(b => b.classList.contains("on"));
    tabs[(i + (dir > 0 ? 1 : tabs.length - 1)) % tabs.length]?.click(); }
  flash(dir > 0 ? "▶ NEXT" : "◀ BACK"); window.HUD_SFX?.whoosh?.();
}

async function startGestures(){
  try {
    const vision = await import(`https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VER}/vision_bundle.mjs`);
    const files = await vision.FilesetResolver.forVisionTasks(`https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VER}/wasm`);
    rec = await vision.GestureRecognizer.createFromOptions(files, {baseOptions: {modelAssetPath:
      "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task", delegate: "GPU"},
      runningMode: "VIDEO", numHands: 1});
    video = $("#gestCam video"); video.srcObject = await navigator.mediaDevices.getUserMedia({video: {width: 320, height: 240}});
    await video.play(); $("#gestCam").classList.add("on"); on = true; btn.classList.add("hot"); loop();
    window.logLine?.("EDITH", "Gestures on: ✋ stop · 👍 yes · 👎 no · ☝ talk · ✌ holo · swipe to switch views", "system");
  } catch(err){ window.logLine?.("EDITH", "Gestures couldn't start: " + (err.message || err) + " (needs the webcam and internet the first time).", "error"); stopGestures(); }
}
function stopGestures(){ on = false; cancelAnimationFrame(raf); btn.classList.remove("hot"); $("#gestCam").classList.remove("on");
  video?.srcObject?.getTracks().forEach(t => t.stop()); }
function loop(){
  if(!on) return;
  const now = performance.now();
  if(video.readyState >= 2){
    const r = rec.recognizeForVideo(video, now);
    const g = r.gestures?.[0]?.[0], hand = r.landmarks?.[0];
    const name = g && g.score > .6 ? g.categoryName : "None";
    if(hand){ track.push({t: now, x: 1 - hand[0].x}); track = track.filter(p => now - p.t < 450);
      const dx = track.length > 4 ? track[track.length - 1].x - track[0].x : 0;
      if(Math.abs(dx) > .28 && now - last.fired > 900 && name !== "Open_Palm"){ last.fired = now; track = []; swipe(dx > 0 ? 1 : -1); } }
    else track = [];
    if(name !== last.name){ last.name = name; last.since = now; }
    else if(ACTIONS[name] && now - last.since > HOLD[name] && now - last.fired > 1500){ last.fired = now; ACTIONS[name](); window.HUD_SFX?.lock?.(); }
  }
  raf = requestAnimationFrame(loop);
}
btn.onclick = () => on ? stopGestures() : startGestures();
window.Gestures = {start: startGestures, stop: stopGestures};
})();
