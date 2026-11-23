// Live updates: when JARVIS on the laptop is updated, open pages (laptop and phone) reload onto the new version,
// waiting until nothing is being said and no call is running.
(function () {
  let first = null;
  const busy = () => (typeof inCall !== "undefined" && inCall) || (typeof speaking !== "undefined" && speaking > 0)
    || !!document.querySelector("#orb.speak") || (document.activeElement && /INPUT|TEXTAREA/.test(document.activeElement.tagName) && document.activeElement.value);
  async function check() {
    try {
      const r = await fetch("/api/version", { cache: "no-store" }); if (!r.ok) return;
      const v = (await r.json()).version;
      if (first === null) first = v;
      else if (v !== first && !busy()) location.reload();
    } catch (e) { /* laptop restarting: try again shortly */ }
  }
  check(); setInterval(check, 20000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) check(); });
})();
// Inside the JARVIS Android app, Android's web view has no speech recognition or speech synthesis.
// This fills both in with the app's native ones (window.JarvisNative), so the pages work unchanged.
(function () {
  const N = window.JarvisNative;
  if (!N) return;

  // ---------------------------------------------------------------- speech recognition
  if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
    let active = null;
    window.__jarvisSR = {
      emit(type, text, isFinal) {
        const r = active; if (!r) return;
        if (type === "start") { r.onstart && r.onstart(); return; }
        if (type === "result") {
          const alt = [{ transcript: text, confidence: 1 }];
          alt.isFinal = !!isFinal;
          r.onresult && r.onresult({ results: [alt], resultIndex: 0 });
          return;
        }
        if (type === "error") { r.onerror && r.onerror({ error: text }); return; }
        if (type === "end") { active = null; r.onend && r.onend(); }
      },
    };
    class NativeRecognition {
      constructor() { this.lang = "en-US"; this.continuous = false; this.interimResults = true; }
      start() { active = this; N.listen(this.lang || "en-US", !!this.interimResults); }
      stop() { N.stopListening(); }
      abort() { N.abortListening(); }
    }
    window.SpeechRecognition = NativeRecognition;
    window.webkitSpeechRecognition = NativeRecognition;
  }

  // ---------------------------------------------------------------- speech synthesis (fallback voice)
  if (!("speechSynthesis" in window)) {
    const waiting = {};
    let n = 0;
    window.__jarvisTTS = { done(id) { const u = waiting[id]; delete waiting[id]; u && u.onend && u.onend(); } };
    window.SpeechSynthesisUtterance = function (text) { this.text = text; this.pitch = 1; this.rate = 1; this.voice = null; };
    window.speechSynthesis = {
      speak(u) { const id = "u" + (++n); waiting[id] = u; N.speak(id, String(u.text || ""), u.pitch || 1, u.rate || 1); },
      cancel() { N.stopSpeaking(); Object.keys(waiting).forEach(id => window.__jarvisTTS.done(id)); },
      getVoices() { return []; },
      onvoiceschanged: null,
    };
  }

  window.JARVIS_APP = true;
})();
