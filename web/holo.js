/* JARVIS Holo Lab: full-screen 3D holograms of your life. "Jarvis, show me my week / Shaabaz / my body / money /
   Singapore / diagnostics / trophies". Drag to spin, scroll or pinch to zoom. Also the idle screensaver in the
   always-on JARVIS window. Uses the bundled three.js (web/vendor), so it works offline. */
(() => {
const VIEWS = [["week", "Week"], ["business", "Shaabaz"], ["body", "Body"], ["money", "Money"], ["singapore", "Singapore"],
               ["diagnostics", "Diagnostics"], ["trophies", "Trophies"]];
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let THREE = null, root = null, renderer, scene, camera, group, data = null, view = "week", raf = 0, open = false, tour = null;
let yaw = 0, pitch = 0, zoom = 1, drag = null, labels = [], t0 = performance.now(), animators = [];

function loadThree(){
  if(window.THREE) return Promise.resolve(window.THREE);
  return new Promise((res, rej) => { const s = document.createElement("script"); s.src = "/vendor/three.min.js"; s.onload = () => res(window.THREE); s.onerror = rej; document.head.appendChild(s); });
}

const css = document.createElement("style");
css.textContent = `
#holo{position:fixed;inset:0;z-index:35;background:radial-gradient(1200px 700px at 50% 45%,rgba(14,28,42,.97),rgba(3,5,9,.99) 70%);display:none;opacity:0;transition:opacity .45s}
#holo.on{display:block;opacity:1}
#holo canvas{position:absolute;inset:0;width:100%;height:100%;touch-action:none}
#holo .hbar{position:absolute;left:0;right:0;top:0;display:flex;align-items:center;gap:8px;padding:12px max(14px,env(safe-area-inset-right));z-index:2;flex-wrap:wrap}
#holo .ttl{font:700 12px Orbitron,sans-serif;letter-spacing:.3em;color:var(--c,#ffd23f);margin-right:auto}
#holo .hbar button{background:rgba(10,17,26,.75);color:#c9d3e0;border:1px solid rgba(95,216,255,.25);font:600 10px Orbitron,sans-serif;letter-spacing:.14em;text-transform:uppercase;padding:8px 10px;cursor:pointer}
#holo .hbar button.on{color:var(--c,#ffd23f);border-color:var(--c,#ffd23f);box-shadow:0 0 12px color-mix(in srgb,var(--c,#ffd23f) 30%,transparent)}
#holo .hbar .x{font-size:13px;padding:6px 11px}
#holo .lbl{position:absolute;transform:translate(-50%,-130%);white-space:nowrap;font:600 10px Orbitron,sans-serif;letter-spacing:.12em;color:var(--lc,#fff);text-shadow:0 0 8px var(--lc,#fff);pointer-events:none;z-index:1}
#holo .lbl small{display:block;text-align:center;font:500 10px "JetBrains Mono",monospace;letter-spacing:0;color:#8a95a7;text-shadow:none}
#holo .hint{position:absolute;bottom:max(14px,env(safe-area-inset-bottom));left:0;right:0;text-align:center;font:500 10px "JetBrains Mono",monospace;color:#5d6878;letter-spacing:.12em;z-index:2}
#holo .scan{position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(255,255,255,.02) 0 1px,transparent 1px 3px)}
@media (max-width:700px){#holo .hbar button{padding:7px 7px;font-size:9px}#holo .ttl{flex-basis:100%}}`;
document.head.appendChild(css);

function build(){
  root = document.createElement("div"); root.id = "holo";
  root.innerHTML = `<canvas></canvas><div class="scan"></div><div class="labels"></div>
    <div class="hbar"><span class="ttl">HOLO LAB</span>${VIEWS.map(([k, n]) => `<button data-v="${k}">${n}</button>`).join("")}<button class="x" aria-label="Close">✕</button></div>
    <div class="hint">DRAG TO SPIN · SCROLL / PINCH TO ZOOM · ESC TO CLOSE</div>`;
  document.body.appendChild(root);
  const cv = root.querySelector("canvas");
  renderer = new THREE.WebGLRenderer({canvas: cv, antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  scene = new THREE.Scene(); scene.fog = new THREE.FogExp2(0x03060a, .025);
  camera = new THREE.PerspectiveCamera(50, 1, .1, 500);
  // dust + floor
  const n = 900, p = new Float32Array(n * 3);
  for(let i = 0; i < n; i++){ const r = 25 + Math.random() * 70, a = Math.random() * 6.283; p.set([Math.cos(a) * r, (Math.random() - .5) * 60, Math.sin(a) * r], i * 3); }
  const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(p, 3));
  scene.add(new THREE.Points(g, new THREE.PointsMaterial({color: 0x6fa8d8, size: .15, transparent: true, opacity: .5})));
  const grid = new THREE.GridHelper(80, 40, 0x1b4a66, 0x0c2030); grid.position.y = -6; grid.material.transparent = true; grid.material.opacity = .3; scene.add(grid);
  root.querySelectorAll("[data-v]").forEach(b => b.onclick = () => { stopTour(); show(b.dataset.v, true); });
  root.querySelector(".x").onclick = close;
  cv.addEventListener("pointerdown", e => { stopTour(); drag = {x: e.clientX, y: e.clientY}; cv.setPointerCapture(e.pointerId); });
  cv.addEventListener("pointermove", e => { if(!drag) return; yaw += (e.clientX - drag.x) * .006; pitch = Math.max(-.7, Math.min(.7, pitch + (e.clientY - drag.y) * .004)); drag = {x: e.clientX, y: e.clientY}; });
  cv.addEventListener("pointerup", () => drag = null);
  cv.addEventListener("wheel", e => { e.preventDefault(); zoom = Math.max(.5, Math.min(1.8, zoom * (1 + e.deltaY * .001))); }, {passive: false});
  let pinch = 0; cv.addEventListener("touchmove", e => { if(e.touches.length === 2){ const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); if(pinch) zoom = Math.max(.5, Math.min(1.8, zoom * pinch / d)); pinch = d; } }, {passive: true});
  cv.addEventListener("touchend", () => pinch = 0);
  addEventListener("keydown", e => { if(e.key === "Escape" && open) close(); });
  addEventListener("resize", size);
}
function size(){ if(!renderer) return; renderer.setSize(innerWidth, innerHeight, false); camera.aspect = innerWidth / innerHeight; camera.fov = innerWidth < 700 ? 66 : 50; camera.updateProjectionMatrix(); }

// ------------------------------------------------------------------ helpers
const C = c => new THREE.Color(c);
function mat(color, op = .85, wire = false){ return new THREE.MeshBasicMaterial({color: C(color), transparent: true, opacity: op, wireframe: wire, blending: THREE.AdditiveBlending, depthWrite: false}); }
let GLOW = null;
function glow(color, s, op = .8){
  if(!GLOW){ const c = document.createElement("canvas"); c.width = c.height = 128; const x = c.getContext("2d"), g = x.createRadialGradient(64,64,0,64,64,64);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(.25, "rgba(255,255,255,.5)"); g.addColorStop(1, "rgba(255,255,255,0)"); x.fillStyle = g; x.fillRect(0,0,128,128); GLOW = new THREE.CanvasTexture(c); }
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: GLOW, color: C(color), transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false})); sp.scale.set(s, s, 1); return sp;
}
function ring(r, t, color, op = .8, arc = Math.PI * 2){ return new THREE.Mesh(new THREE.TorusGeometry(r, t, 8, Math.max(12, Math.round(96 * arc / 6.283)), arc), mat(color, op)); }
function label(obj, html, color){ const el = document.createElement("div"); el.className = "lbl"; el.style.setProperty("--lc", color); el.innerHTML = html; root.querySelector(".labels").appendChild(el); labels.push({obj, el}); }
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function clear(){
  if(group){ scene.remove(group); group.traverse(o => { o.geometry?.dispose?.(); o.material?.dispose?.(); }); }
  labels.forEach(l => l.el.remove()); labels = []; animators = [];
  group = new THREE.Group(); scene.add(group);
}

// ------------------------------------------------------------------ the views
const CAM = {week: [10, 5, 14], business: [0, 12, 17], body: [0, 1.5, 11], money: [0, 7, 15], singapore: [0, 13, 12], diagnostics: [0, 0, 16], trophies: [0, 10, 17]};
const BUILD = {
  week(){
    const R = 4.6;
    data.days.forEach((d, i) => {
      const y = (3 - i) * 1.2, floor = new THREE.Group(); floor.position.y = y; group.add(floor);
      const plate = new THREE.Mesh(new THREE.CylinderGeometry(R, R, .03, 64, 1, true), mat("#5fd8ff", .08)); floor.add(plate);
      const edge = ring(R, .015, i === 0 ? "#ffd23f" : "#5fd8ff", .55); edge.rotation.x = Math.PI / 2; floor.add(edge);
      const tag = new THREE.Object3D(); tag.position.set(-R - 1.1, 0, 0); floor.add(tag); label(tag, i === 0 ? "TODAY" : d, i === 0 ? "#ffd23f" : "#8a95a7");
      let n = 0;
      data.week.filter(e => e.day === i).forEach(e => {
        const a0 = e.start / 24 * Math.PI * 2 - Math.PI / 2, al = Math.max(.08, e.dur / 24 * Math.PI * 2);
        const arc = ring(R, .17, e.color, .95, al); arc.rotation.x = Math.PI / 2; arc.rotation.z = -a0 - al; floor.add(arc);
        if(n++ < 2){ const p = new THREE.Object3D(); p.position.set(Math.cos(a0 + al / 2) * R, .3, Math.sin(a0 + al / 2) * R); floor.add(p);
          label(p, `${esc(e.title.slice(0, 26))}<small>${String(Math.floor(e.start)).padStart(2, "0")}:${String(Math.round(e.start % 1 * 60)).padStart(2, "0")}</small>`, e.color); }
      });
    });
    group.add(new THREE.Mesh(new THREE.CylinderGeometry(.05, .05, 9, 8), mat("#ffd23f", .6)));
    animators.push((t, dt) => group.rotation.y += dt * .12);
  },
  business(){
    const sun = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 24), mat("#e8b04b", .9)); group.add(sun, glow("#e8b04b", 8, .7));
    const active = data.gigs.filter(g => g.status !== "done"), total = active.reduce((s, g) => s + g.value, 0);
    const st = new THREE.Object3D(); st.position.y = 1.5; group.add(st); label(st, `SHAABAZ<small>$${Math.round(total).toLocaleString()} in play</small>`, "#e8b04b");
    const COL = {enquiry: "#5fd8ff", quoted: "#ffcc3d", confirmed: "#3dff9a", done: "#7d8899"};
    const gigs = data.gigs.length ? data.gigs : [];
    gigs.slice(0, 18).forEach((g, i) => {
      const r = 3 + (g.days == null ? 9 : Math.min(10, Math.max(0, g.days) / 9)) + i * .15, size = .25 + Math.min(1, g.value / 20000) * .75, col = COL[g.status] || "#5fd8ff";
      const path = ring(r, .01, col, .25); path.rotation.x = Math.PI / 2; group.add(path);
      const p = new THREE.Group(); p.add(new THREE.Mesh(new THREE.SphereGeometry(size, 18, 18), mat(col, .85)), glow(col, size * 4, .55)); group.add(p);
      const a0 = i * 2.39; label(p, `${esc(g.client)}<small>${g.value ? "$" + Math.round(g.value).toLocaleString() + " · " : ""}${g.status}${g.days != null ? " · " + (g.days >= 0 ? g.days + "d" : "done") : ""}</small>`, col);
      animators.push((t) => { const a = a0 + t * (.5 / r); p.position.set(Math.cos(a) * r, Math.sin(a * 1.3) * .4, Math.sin(a) * r); });
    });
    if(!gigs.length){ const e = new THREE.Object3D(); e.position.set(0, -2, 0); group.add(e); label(e, `NO CLIENTS YET<small>"Pepper, new enquiry: …"</small>`, "#5fd8ff"); }
    animators.push((t, dt) => group.rotation.y += dt * .03);
  },
  body(){
    const m = data.muscles, heat = v => C("#5fd8ff").lerp(C("#ff7a3d"), Math.min(1, v * 1.4));
    const part = (geo, x, y, z, key, rx = 0) => { const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({color: heat(m[key] || 0), transparent: true, opacity: .22 + (m[key] || 0) * .55, blending: THREE.AdditiveBlending, depthWrite: false}));
      mesh.position.set(x, y, z); mesh.rotation.x = rx; group.add(mesh); const w = new THREE.Mesh(geo, mat("#5fd8ff", .35, true)); w.position.copy(mesh.position); w.rotation.x = rx; group.add(w); return mesh; };
    part(new THREE.SphereGeometry(.55, 16, 12), 0, 3.3, 0, "none");
    part(new THREE.BoxGeometry(1.8, 1.1, .5), 0, 2.05, .12, "chest"); part(new THREE.BoxGeometry(1.8, 1.1, .4), 0, 2.05, -.3, "back");
    part(new THREE.BoxGeometry(1.4, 1.0, .7), 0, .95, 0, "core");
    [-1.15, 1.15].forEach(x => { part(new THREE.SphereGeometry(.38, 12, 10), x, 2.45, 0, "shoulders");
      part(new THREE.CylinderGeometry(.22, .18, 1.6, 10), x * 1.05, 1.45, 0, "arms"); part(new THREE.CylinderGeometry(.3, .22, 2.2, 10), x * .45, -1.2, 0, "legs"); });
    Object.entries(m).forEach(([k, v], i) => { const o = new THREE.Object3D(); o.position.set(i % 2 ? 3.2 : -3.2, 3 - Math.floor(i / 2) * 1.5, 0); group.add(o);
      label(o, `${k.toUpperCase()}<small>${Math.round(v * 100)}% this week</small>`, v > .15 ? "#ff7a3d" : "#5fd8ff"); });
    animators.push((t, dt) => group.rotation.y += dt * .35);
  },
  money(){
    const sp = data.spending.slice().sort((a, b) => b.amount - a.amount).slice(0, 8), max = Math.max(1, ...sp.map(s => s.amount));
    const COLS = ["#ff4f7b", "#ffcc3d", "#5fd8ff", "#3dff9a", "#b06bff", "#ff7a3d", "#2de0c0", "#e8b04b"];
    const src = new THREE.Mesh(new THREE.SphereGeometry(.7, 20, 20), mat("#ffffff", .8)); src.position.y = 4.5;
    const sg = glow("#ff4f7b", 4, .5); sg.position.y = 4.5; group.add(src, sg);
    const top = new THREE.Object3D(); top.position.y = 5.6; group.add(top);
    label(top, `THIS MONTH<small>$${Math.round(sp.reduce((s, x) => s + x.amount, 0)).toLocaleString()} spent${data.income ? " · $" + Math.round(data.income).toLocaleString() + " in" : ""}</small>`, "#ff4f7b");
    sp.forEach((s, i) => {
      const a = i / Math.max(1, sp.length) * Math.PI * 2, x = Math.cos(a) * 5, z = Math.sin(a) * 5, h = .3 + s.amount / max * 3, col = COLS[i % COLS.length];
      const pool = new THREE.Mesh(new THREE.CylinderGeometry(.9, .9, h, 24, 1, true), mat(col, .3)); pool.position.set(x, -4 + h / 2, z); group.add(pool);
      const lid = ring(.9, .03, col, .9); lid.rotation.x = Math.PI / 2; lid.position.set(x, -4 + h, z); group.add(lid);
      label(lid, `${esc(s.category)}<small>$${Math.round(s.amount).toLocaleString()}</small>`, col);
      const N = 26, pts = new Float32Array(N * 3), g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      const dots = new THREE.Points(g, new THREE.PointsMaterial({color: C(col), size: .16, transparent: true, opacity: .9, blending: THREE.AdditiveBlending, depthWrite: false})); group.add(dots);
      animators.push(t => { for(let k = 0; k < N; k++){ const f = ((t * .35 + k / N) % 1); pts[k * 3] = x * f; pts[k * 3 + 1] = 4.5 - (8.5 - (3 - h)) * f + Math.sin(f * 3.14) * 1.2; pts[k * 3 + 2] = z * f; }
        g.attributes.position.needsUpdate = true; });
    });
    if(!sp.length){ const e = new THREE.Object3D(); e.position.y = 0; group.add(e); label(e, `NO SPENDING LOGGED<small>"I spent $12 on lunch"</small>`, "#5fd8ff"); }
    animators.push((t, dt) => group.rotation.y += dt * .08);
  },
  singapore(){
    const k = 40, P = ([lon, lat]) => new THREE.Vector3((lon - 103.82) * k, 0, -(lat - 1.355) * k);
    const pts = data.outline.map(P); pts.push(pts[0]);
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({color: C("#5fd8ff"), transparent: true, opacity: .85}));
    group.add(line);
    const shape = new THREE.Shape(data.outline.map(([lon, lat]) => new THREE.Vector2((lon - 103.82) * k, (lat - 1.355) * k)));
    const land = new THREE.Mesh(new THREE.ShapeGeometry(shape), mat("#5fd8ff", .06)); land.rotation.x = -Math.PI / 2; group.add(land);
    const today = new Set(data.today_places.map(p => p.place)), explored = new Set(data.explored);
    Object.entries(data.landmarks).forEach(([name, [lat, lon]]) => {
      const v = P([lon, lat]), isT = today.has(name), isE = explored.has(name), col = isT ? "#5fd8ff" : isE ? "#ffd23f" : "#3a4656";
      const h = isT ? 3 : isE ? 1.4 : .4, pin = new THREE.Mesh(new THREE.CylinderGeometry(.05, .05, h, 6), mat(col, isT || isE ? .9 : .5));
      pin.position.set(v.x, h / 2, v.z); group.add(pin);
      const dot = glow(col, isT ? 2.4 : isE ? 1.4 : .6, isT || isE ? .9 : .4); dot.position.set(v.x, h, v.z); group.add(dot);
      if(isT || isE){ const p = new THREE.Object3D(); p.position.set(v.x, h, v.z); group.add(p);
        const ev = data.today_places.find(x => x.place === name); label(p, `${esc(name)}${ev ? `<small>${esc(ev.title.slice(0, 22))} · ${ev.time}</small>` : ""}`, col); }
      if(isT) animators.push(t => dot.scale.setScalar(2.4 * (1 + Math.sin(t * 4) * .25)));
    });
    const c = new THREE.Object3D(); c.position.set(0, 4, 0); group.add(c); label(c, `SINGAPORE<small>${explored.size} explored · ${today.size} today</small>`, "#ffd23f");
    animators.push((t, dt) => group.rotation.y += dt * .05);
  },
  diagnostics(){
    data.diagnostics.forEach((d, i) => {
      const r = 1.7 + i * .72, bg = ring(r, .04, d.color, .12), fg = ring(r, .09, d.color, .95, Math.max(.02, Math.PI * 2 * d.value));
      bg.rotation.z = fg.rotation.z = Math.PI / 2; group.add(bg, fg);
      const p = new THREE.Object3D(); p.position.set(0, r + .02, .2); group.add(p); label(p, `${d.label} · ${Math.round(d.value * 100)}%`, d.color);
      fg.scale.setScalar(.001); animators.push(t => fg.scale.setScalar(Math.min(1, t * 1.5 - i * .08) > 0 ? Math.min(1, t * 1.5 - i * .08) : .001));
    });
    const core = new THREE.Mesh(new THREE.IcosahedronGeometry(.95, 1), mat("#ffffff", .45, true)); group.add(core, glow("#5fd8ff", 4, .5));
    animators.push((t, dt) => { core.rotation.y += dt * .6; core.rotation.x += dt * .25; group.rotation.y = Math.sin(t * .3) * .35; });
  },
  trophies(){
    const list = data.trophies, cols = 5;
    list.forEach((t, i) => {
      const x = (i % cols - (cols - 1) / 2) * 3, z = -Math.floor(i / cols) * 3.4 + 4, on = !!t.unlocked, col = on ? t.color : "#3a4656";
      const ped = new THREE.Mesh(new THREE.CylinderGeometry(.6, .7, .5, 6), mat(col, on ? .35 : .15)); ped.position.set(x, -1, z); group.add(ped);
      const tro = new THREE.Mesh(new THREE.OctahedronGeometry(on ? .55 : .4), mat(col, on ? .95 : .35, !on)); tro.position.set(x, .2, z); group.add(tro);
      if(on){ const g = glow(col, 2.4, .6); g.position.copy(tro.position); group.add(g); }
      const p = new THREE.Object3D(); p.position.set(x, .9, z); group.add(p);
      label(p, `${esc(t.title)}<small>${on ? "unlocked" : t.progress + " / " + t.target}</small>`, on ? t.color : "#8a95a7");
      animators.push((tt, dt) => { tro.rotation.y += dt * (on ? 1.2 : .3); tro.position.y = .2 + Math.sin(tt * 2 + i) * .1; });
    });
  },
};

function show(v, speak){
  view = BUILD[v] ? v : "week"; yaw = 0; pitch = 0; zoom = 1; clear(); t0 = performance.now();
  try { BUILD[view](); } catch(err){ console.error(err); }
  root.querySelectorAll("[data-v]").forEach(b => b.classList.toggle("on", b.dataset.v === view));
  window.HUD_SFX?.whoosh?.();
  if(speak && window.sendCommand) window.sendCommand(`show me ${view === "business" ? "Shaabaz" : view}`, "JARVIS", true);
}

function frame(now){
  if(!open) return;
  const t = (now - t0) / 1000, dt = Math.min(.05, (now - (frame.last || now)) / 1000); frame.last = now;
  if(!reduce) animators.forEach(f => f(t, dt));
  const base = new THREE.Vector3(...CAM[view]).multiplyScalar(zoom), sph = new THREE.Spherical().setFromVector3(base);
  sph.theta += yaw; sph.phi = Math.max(.15, Math.min(Math.PI - .15, sph.phi - pitch));
  const target = new THREE.Vector3().setFromSpherical(sph); camera.position.lerp(target, Math.min(1, dt * 3)); camera.lookAt(0, view === "body" ? 1.3 : 0, 0);
  renderer.render(scene, camera);
  const v = new THREE.Vector3();
  labels.forEach(L => { L.obj.getWorldPosition(v); v.project(camera); const vis = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    L.el.style.display = vis ? "" : "none"; if(vis){ L.el.style.left = (v.x * .5 + .5) * innerWidth + "px"; L.el.style.top = (-v.y * .5 + .5) * innerHeight + "px"; } });
  raf = requestAnimationFrame(frame);
}

async function openHolo(v = "week", opts = {}){
  try { THREE = await loadThree(); } catch { window.logLine?.("JARVIS", "The 3D engine couldn't load.", "error"); return; }
  if(!root) build();
  try { data = await (await fetch("/api/holo")).json(); } catch { return; }
  size(); root.classList.add("on"); open = true; camera.position.set(0, 30, 60);
  show(v, !!opts.speak); cancelAnimationFrame(raf); raf = requestAnimationFrame(frame);
}
function close(){ open = false; stopTour(); cancelAnimationFrame(raf); root?.classList.remove("on"); window.HUD_SFX?.whoosh?.(); }

// ------------------------------------------------------------------ screensaver tour in the JARVIS window
function startTour(){ let i = 0; openHolo(VIEWS[0][0]); tour = setInterval(() => { i = (i + 1) % VIEWS.length; if(open) show(VIEWS[i][0]); }, 18000); }
function stopTour(){ if(tour){ clearInterval(tour); tour = null; } }
let idleAt = Date.now();
["pointermove", "keydown", "pointerdown", "wheel"].forEach(e => addEventListener(e, () => { idleAt = Date.now(); if(tour){ close(); } }, {passive: true}));
setInterval(() => {
  const kiosk = new URLSearchParams(location.search).get("kiosk") === "1";
  if(kiosk && !open && !document.hidden && Date.now() - idleAt > 180000 && !document.querySelector("#orb.speak")) startTour();
}, 10000);

window.HOLO = {open: openHolo, close, tour: startTour, isOpen: () => open, view: () => view};
})();
