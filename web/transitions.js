/* Cinematic transitions everywhere (#13) and the boot sequence (#14).
   - Every page opens with a holographic iris and scan line; tapping a link closes it the same way before moving on.
   - <script src="transitions.js" data-boot> also plays the 2-second JARVIS boot (reactor ignition, sound, a little
     vibration) the first time the app opens in a session. Tap to skip. */
(() => {
  const me = document.currentScript, wantBoot = me && me.hasAttribute("data-boot");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const accent = () => getComputedStyle(document.documentElement).getPropertyValue("--c").trim() || "#ffd23f";
  const css = document.createElement("style");
  css.textContent = `
  #hx-iris{position:fixed;inset:0;z-index:9998;pointer-events:none;background:#02040a;clip-path:circle(150% at 50% 50%);transition:clip-path .55s cubic-bezier(.7,0,.2,1)}
  #hx-iris.open{clip-path:circle(0% at 50% 50%)}
  #hx-iris.close{clip-path:circle(150% at 50% 50%);transition-duration:.34s}
  #hx-ring{position:fixed;left:50%;top:50%;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;z-index:9999;pointer-events:none;border:2px solid var(--hx,#ffd23f);
    box-shadow:0 0 24px var(--hx,#ffd23f),inset 0 0 18px var(--hx,#ffd23f);opacity:0}
  #hx-ring.go{animation:hxring .6s ease-out}
  @keyframes hxring{0%{opacity:1;transform:scale(1)}100%{opacity:0;transform:scale(160)}}
  #hx-scan{position:fixed;left:0;right:0;height:2px;top:0;z-index:9999;pointer-events:none;background:linear-gradient(90deg,transparent,var(--hx,#ffd23f),transparent);box-shadow:0 0 16px var(--hx,#ffd23f);opacity:0}
  #hx-scan.go{animation:hxscan .7s ease-out}
  @keyframes hxscan{0%{top:0;opacity:1}100%{top:100%;opacity:0}}
  #hx-boot{position:fixed;inset:0;z-index:10000;background:radial-gradient(circle at 50% 45%,#0b1520,#000 70%);display:grid;place-items:center;transition:opacity .5s}
  #hx-boot.done{opacity:0;pointer-events:none}
  #hx-boot canvas{width:min(64vw,300px);height:min(64vw,300px)}
  #hx-boot .t{position:absolute;left:0;right:0;top:calc(50% + min(36vw,170px));text-align:center;font:700 11px Orbitron,sans-serif;letter-spacing:.4em;color:var(--hx,#ffd23f);text-shadow:0 0 12px var(--hx,#ffd23f)}
  #hx-boot .s{position:absolute;left:0;right:0;top:calc(50% + min(36vw,170px) + 24px);text-align:center;font:500 10px "JetBrains Mono",monospace;color:#6d7a8c;letter-spacing:.1em}
  #hx-boot .k{position:absolute;bottom:max(18px,env(safe-area-inset-bottom));left:0;right:0;text-align:center;font:600 9px Orbitron,sans-serif;letter-spacing:.3em;color:#3d4756}`;
  document.head.appendChild(css);
  const el = (id, parent = document.body) => { const d = document.createElement("div"); d.id = id; parent.appendChild(d); return d; };

  function sound(kind){
    try {
      const ac = window.__hxAC || (window.__hxAC = new (window.AudioContext || window.webkitAudioContext)()); ac.resume?.();
      const t = ac.currentTime, g = ac.createGain(), o = ac.createOscillator(); o.connect(g); g.connect(ac.destination);
      if (kind === "boot"){ o.type = "sawtooth"; o.frequency.setValueAtTime(55, t); o.frequency.exponentialRampToValueAtTime(220, t + 1.4);
        g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.12, t + .9); g.gain.exponentialRampToValueAtTime(.0001, t + 2); o.start(t); o.stop(t + 2.1);
        const o2 = ac.createOscillator(), g2 = ac.createGain(); o2.frequency.setValueAtTime(150, t + 1.5); o2.frequency.exponentialRampToValueAtTime(40, t + 1.9);
        g2.gain.setValueAtTime(.0001, t + 1.5); g2.gain.exponentialRampToValueAtTime(.6, t + 1.51); g2.gain.exponentialRampToValueAtTime(.0001, t + 2.1); o2.connect(g2); g2.connect(ac.destination); o2.start(t + 1.5); o2.stop(t + 2.2); }
      else { o.type = "sine"; o.frequency.setValueAtTime(kind === "out" ? 900 : 500, t); o.frequency.exponentialRampToValueAtTime(kind === "out" ? 300 : 1200, t + .25);
        g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.05, t + .03); g.gain.exponentialRampToValueAtTime(.0001, t + .3); o.start(t); o.stop(t + .32); }
    } catch {}
  }
  const buzz = p => { try { (window.JarvisNative?.vibrate ? window.JarvisNative.vibrate(JSON.stringify(p)) : navigator.vibrate?.(p)); } catch {} };

  function reveal(){
    if (reduce) return;
    document.documentElement.style.setProperty("--hx", accent());
    const iris = el("hx-iris"), ring = el("hx-ring"), scan = el("hx-scan");
    requestAnimationFrame(() => requestAnimationFrame(() => { iris.classList.add("open"); ring.classList.add("go"); scan.classList.add("go"); }));
    setTimeout(() => { iris.remove(); }, 700);
  }
  function leave(url){
    if (reduce) return (location.href = url);
    document.documentElement.style.setProperty("--hx", accent());
    const iris = document.getElementById("hx-iris") || el("hx-iris"); iris.className = "open";
    requestAnimationFrame(() => requestAnimationFrame(() => iris.className = "close"));
    sound("out"); buzz(12); setTimeout(() => (location.href = url), 330);
  }
  document.addEventListener("click", e => {
    const a = e.target.closest("a[href]"); if (!a || e.defaultPrevented || a.target || e.metaKey || e.ctrlKey) return;
    const href = a.getAttribute("href"); if (!href || href.startsWith("#") || href.startsWith("javascript:") || a.hasAttribute("download")) return;
    let u; try { u = new URL(href, location.href); } catch { return; }
    if (u.origin !== location.origin && u.protocol !== "file:") return;
    e.preventDefault(); leave(u.href);
  });
  window.HoloTransition = {leave, reveal};

  function boot(){
    let key = "jarvis-booted"; try { if (sessionStorage.getItem(key)) return false; sessionStorage.setItem(key, "1"); } catch {}
    document.documentElement.style.setProperty("--hx", accent());
    const b = el("hx-boot"); b.innerHTML = `<canvas></canvas><div class="t">J.A.R.V.I.S</div><div class="s"></div><div class="k">TAP TO SKIP</div>`;
    const cv = b.querySelector("canvas"), x = cv.getContext("2d"), d = Math.min(devicePixelRatio || 1, 2), S = cv.getBoundingClientRect().width;
    cv.width = cv.height = S * d; x.scale(d, d);
    const lines = ["Calibrating neural core", "Linking phone and laptop", "Loading your day", "All systems online"];
    const t0 = performance.now(), dur = 2300, c = accent(); let raf = 0;
    sound("boot"); buzz([20, 80, 20, 300, 60]);
    (function draw(now){
      const k = Math.min(1, (now - t0) / dur), m = S / 2; x.clearRect(0, 0, S, S); x.lineCap = "round";
      [[.42, 3, 1], [.36, 1.5, -1.6], [.3, 5, .8], [.48, 1, -.6]].forEach(([r, w, sp], i) => { const len = Math.min(1, k * 1.6 - i * .12) * Math.PI * 1.6;
        if (len <= 0) return; x.strokeStyle = c; x.globalAlpha = .9; x.lineWidth = w; x.beginPath(); x.arc(m, m, S * r, now / 1000 * sp, now / 1000 * sp + len); x.stroke(); });
      const g = x.createRadialGradient(m, m, 0, m, m, S * (.08 + k * .2)); g.addColorStop(0, "#fff"); g.addColorStop(.4, c); g.addColorStop(1, "transparent");
      x.globalAlpha = Math.min(1, k * 1.4); x.fillStyle = g; x.beginPath(); x.arc(m, m, S * .3, 0, Math.PI * 2); x.fill(); x.globalAlpha = 1;
      for (let i = 0; i < 12; i++){ if (i / 12 > k * 1.3) break; const a = i / 12 * Math.PI * 2 + now / 2500; x.save(); x.translate(m + Math.cos(a) * S * .2, m + Math.sin(a) * S * .2); x.rotate(a); x.fillStyle = "#5fd8ff"; x.fillRect(-7, -2, 14, 4); x.restore(); }
      b.querySelector(".s").textContent = lines[Math.min(lines.length - 1, Math.floor(k * lines.length))] + (k < 1 ? "…" : "");
      if (k < 1) raf = requestAnimationFrame(draw); else end();
    })(t0);
    let ended = false;
    function end(){ if (ended) return; ended = true; cancelAnimationFrame(raf); b.classList.add("done"); setTimeout(() => b.remove(), 600); }
    b.addEventListener("click", end);
    return true;
  }
  const go = () => { if (!(wantBoot && boot())) reveal(); };
  if (document.body) go(); else addEventListener("DOMContentLoaded", go);
})();
