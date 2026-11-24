/* Interrupt JARVIS mid-sentence (#21): while he talks, the mic listens for YOUR voice; start talking and he stops
   and listens. Uses the mic's echo cancelling plus an adaptive level, so his own voice through the speakers doesn't
   count. The mic is only open while he speaks (the phone's speech recogniser needs it the rest of the time).
   Turn off with localStorage "jarvis-bargein" = "off". */
window.BargeIn = (() => {
  let stream = null, ac = null, an = null, buf = null, timer = 0, on = false, cb = null, hot = 0, floor = .02, t0 = 0;
  const off = () => { try { return localStorage.getItem("jarvis-bargein") === "off"; } catch { return false; } };
  async function open(){
    if (stream) return true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: false}});
      ac = ac || new (window.AudioContext || window.webkitAudioContext)();
      an = ac.createAnalyser(); an.fftSize = 1024; buf = new Float32Array(an.fftSize);
      ac.createMediaStreamSource(stream).connect(an); ac.resume?.();
      return true;
    } catch { stream = null; return false; }
  }
  function close(){ clearInterval(timer); timer = 0; if (stream){ stream.getTracks().forEach(t => t.stop()); stream = null; } }
  function step(){
    if (!on || !an) return;
    an.getFloatTimeDomainData(buf); let s = 0; for (let i = 0; i < buf.length; i++) s += buf[i] * buf[i];
    const rms = Math.sqrt(s / buf.length), warm = performance.now() - t0 < 450;
    // the floor follows the loudest echo of his own voice (slowly forgetting), so only a louder, closer voice counts
    floor = Math.max(floor * .992, warm ? rms : Math.min(rms, floor * 1.15));
    if (!warm && rms > Math.max(.04, floor * 1.9)) hot++; else hot = Math.max(0, hot - 1);
    if (hot >= 7){ const f = cb; stop(); f && f(); }   // ~200 ms of you talking over him
  }
  async function watch(onBarge){
    if (off() || on) return;
    cb = onBarge; hot = 0; floor = .02; t0 = performance.now(); on = true;
    if (!(await open())){ on = false; return; }
    if (on) timer = setInterval(step, 30);
  }
  function stop(){ on = false; cb = null; close(); }
  return {watch, stop};
})();
