/* JARVIS Holo Lab: full-screen 3D holograms of your life. "Jarvis, show me my week / Shaabaz / my body / money /
   Singapore / diagnostics / trophies". Drag to spin, scroll or pinch to zoom. Also the idle screensaver in the
   always-on JARVIS window. Uses the bundled three.js (web/vendor), so it works offline. */
(() => {
const VIEWS = [["week", "Week"], ["business", "Shaabaz"], ["body", "Body"], ["money", "Money"], ["singapore", "Singapore"],
               ["diagnostics", "Diagnostics"], ["trophies", "Trophies"]];
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
let THREE = null, root = null, renderer, scene, camera, group, data = null, view = "week", raf = 0, open = false, tour = null;
let body3d = false;
let yaw = 0, pitch = 0, zoom = 1, drag = null, labels = [], t0 = performance.now(), animators = [];

function loadThree(){
  if(window.THREE) return Promise.resolve(window.THREE);
  return new Promise((res, rej) => { const s = document.createElement("script"); s.src = (window.HOLO_BASE ?? "/") + "vendor/three.min.js"; s.onload = () => window.THREE ? res(window.THREE) : rej(new Error("no THREE")); s.onerror = rej; document.head.appendChild(s); });
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
#holo .bpanel{position:absolute;inset:64px 0 36px;display:none;place-items:center;z-index:1;overflow:auto;padding:0 max(14px,env(safe-area-inset-right))}
#holo .bpanel.on{display:grid}
#holo .b3d{position:absolute;right:max(14px,env(safe-area-inset-right));bottom:max(40px,env(safe-area-inset-bottom));z-index:2;background:rgba(10,17,26,.75);color:#c9d3e0;border:1px solid rgba(95,216,255,.25);font:600 10px Orbitron,sans-serif;letter-spacing:.14em;padding:8px 10px;cursor:pointer;display:none}
#holo .arcam{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;z-index:0}
#holo.arOn{background:#000}
#holo.arOn canvas{z-index:1}
#holo.arOn .scan{opacity:.4}
#holo .scan{position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(0deg,rgba(255,255,255,.02) 0 1px,transparent 1px 3px)}
@media (max-width:700px){#holo .hbar button{padding:7px 7px;font-size:9px}#holo .ttl{flex-basis:100%}}`;
document.head.appendChild(css);

function build(){
  root = document.createElement("div"); root.id = "holo";
  root.innerHTML = `<canvas></canvas><div class="scan"></div><div class="labels"></div><div class="bpanel"></div><button class="b3d">3D HOLOGRAM</button>
    <div class="hbar"><span class="ttl">HOLO LAB</span>${VIEWS.map(([k, n]) => `<button data-v="${k}">${n}</button>`).join("")}<button class="ar" aria-label="Hologram over your camera">📷 AR</button><button class="x" aria-label="Close">✕</button></div>
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
  root.querySelector(".ar").onclick = toggleAR;
  root.querySelector(".b3d").onclick = () => { body3d = !body3d; show("body"); };
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
const CAM = {week: [10, 5, 14], business: [0, 12, 17], body: [0, 1.2, 10.5], money: [0, 7, 15], singapore: [0, 13, 12], diagnostics: [0, 0, 16], trophies: [0, 10, 17]};
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
    // Anatomical hologram. Muscles are tapered bellies (like real muscle), with their separate heads, sitting on a
    // see-through skin and skeleton. Cool cyan = rested, orange to red = worked this week (from your logged workouts).
    const m0 = data.muscles || {}, m = {...m0}, fig = new THREE.Group(); fig.position.y = -.15; group.add(fig);
    // real steps from the phone light up the legs, and a ring of light at the feet grows with today's count
    const st = data.steps || {}, today = st.today || 0, week = (st.week || []).reduce((a, b) => a + b, 0), walk = Math.min(1, today / 12000);
    if(today){ ["calves", "quads", "hamstrings", "glutes"].forEach((k, i) => m[k] = Math.max(m[k] || 0, walk * (1 - i * .15))); }
    const heat = v => C("#1d8fc0").lerp(C("#ff6a1a"), Math.min(1, v * 1.3)).lerp(C("#ff2a1a"), Math.max(0, v - .75) * 2);
    // a unit muscle belly: thick in the middle, tapering to tendons at both ends
    const prof = []; for(let i = 0; i <= 16; i++){ const t = i / 16; prof.push(new THREE.Vector2(Math.max(.02, Math.pow(Math.sin(Math.PI * t), .72) * .5), t - .5)); }
    const BELLY = new THREE.LatheGeometry(prof, 20), BELLYW = new THREE.LatheGeometry(prof.filter((_, i) => i % 2 === 0), 10);
    const skin = op => new THREE.MeshBasicMaterial({color: C("#5fd8ff"), wireframe: true, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false});
    const muscle = (key, [x, y, z], len, w, depth = .7, [rx, ry, rz] = [0, 0, 0], mirror = true) => {
      (mirror ? [1, -1] : [1]).forEach(side => {
        const v = m[key] || 0, g = new THREE.Group(); g.position.set(x * side, y, z); g.rotation.set(rx, ry * side, rz * side); g.scale.set(w, len, w * depth);
        const fill = new THREE.Mesh(BELLY, new THREE.MeshBasicMaterial({color: heat(v), transparent: true, opacity: .16 + v * .34, blending: THREE.AdditiveBlending, depthWrite: false}));
        const fibre = new THREE.Mesh(BELLYW, new THREE.MeshBasicMaterial({color: v > .15 ? heat(v) : C("#7fe3ff"), wireframe: true, transparent: true, opacity: .14 + v * .22, blending: THREE.AdditiveBlending, depthWrite: false}));
        g.add(fill, fibre); fig.add(g);
        if(v > .15) animators.push(t => fill.material.opacity = (.16 + v * .34) * (.8 + .2 * Math.sin(t * 3 + y * 2)));
      });
    };
    const limb = (p1, p2, r1, r2, op = .1) => { const a3 = new THREE.Vector3(...p1), b3 = new THREE.Vector3(...p2), len = a3.distanceTo(b3);
      const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r2, r1, len, 14, 5, true), skin(op)); mesh.position.copy(a3).add(b3).multiplyScalar(.5);
      mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b3.clone().sub(a3).normalize()); fig.add(mesh); };
    const bone = (pts, op = .3) => fig.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map(p => new THREE.Vector3(...p))), new THREE.LineBasicMaterial({color: C("#9fdcff"), transparent: true, opacity: op})));
    // ---- skin silhouette
    const torsoP = [[.5, .22], [.56, .55], [.47, 1.0], [.5, 1.4], [.63, 1.9], [.74, 2.35], [.7, 2.62], [.42, 2.8], [.2, 2.9]].map(([r, y]) => new THREE.Vector2(r, y));
    const torso = new THREE.Mesh(new THREE.LatheGeometry(torsoP, 22), skin(.09)); torso.scale.z = .6; fig.add(torso);
    const head = new THREE.Mesh(new THREE.SphereGeometry(.42, 16, 12), skin(.3)); head.scale.set(1, 1.2, 1.08); head.position.set(0, 3.42, .02); fig.add(head);
    limb([0, 2.75, 0], [0, 3.1, .02], .21, .17, .2);
    [1, -1].forEach(sd => {
      limb([1.0 * sd, 2.45, 0], [1.16 * sd, 1.45, 0], .22, .16); limb([1.16 * sd, 1.45, 0], [1.3 * sd, .58, .02], .16, .1);
      limb([.33 * sd, .35, 0], [.34 * sd, -1.35, .02], .31, .17); limb([.34 * sd, -1.35, .02], [.33 * sd, -3.72, -.02], .17, .09);
      const hand = new THREE.Mesh(new THREE.SphereGeometry(1, 10, 8), skin(.25)); hand.scale.set(.1, .2, .06); hand.position.set(1.33 * sd, .36, .02); fig.add(hand);
      const foot = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), skin(.25)); foot.scale.set(.12, .07, .3); foot.position.set(.33 * sd, -3.85, .12); fig.add(foot);
    });
    // ---- skeleton
    bone(Array.from({length: 14}, (_, i) => [0, .42 + i * .19, -.24 + Math.sin(i / 2.2) * .05]), .4);
    for(let i = 0; i < 6; i++){ const y = 2.33 - i * .19, r = .48 + Math.sin(i / 5 * Math.PI) * .1;
      bone(Array.from({length: 25}, (_, k) => { const a = -Math.PI * .9 + k / 24 * Math.PI * 1.8; return [Math.sin(a) * r, y - Math.abs(Math.sin(a)) * .08, Math.cos(a) * r * .55 - .03]; }), .18); }
    bone([[-.6, .62, 0], [-.3, .35, .1], [0, .3, .14], [.3, .35, .1], [.6, .62, 0]], .28);
    [1, -1].forEach(sd => bone([[.15 * sd, 2.66, .08], [.95 * sd, 2.58, 0]], .28));
    // ---- chest, shoulders, traps
    muscle("chest", [.32, 2.3, .29], .62, .34, .34, [0, -.25, 1.38]);       // pec, clavicular part
    muscle("chest", [.36, 2.1, .28], .7, .34, .36, [0, -.25, 1.15]);        // pec, sternal part
    muscle("shoulders", [.86, 2.47, .17], .5, .23, .8, [-.35, 0, .45]);     // front delt
    muscle("shoulders", [.99, 2.42, 0], .55, .26, .8, [0, 0, .3]);         // side delt
    muscle("shoulders", [.86, 2.47, -.17], .5, .22, .8, [.35, 0, .45]);     // rear delt
    muscle("traps", [.27, 2.77, -.07], .55, .2, .7, [0, 0, 1.05]);          // upper traps
    muscle("traps", [.18, 2.38, -.3], .62, .24, .4, [0, 0, .35]);           // mid traps
    // ---- core
    [[1.97, .21], [1.72, .21], [1.47, .22], [1.17, .32]].forEach(([y, l]) => muscle("abs", [.12, y, .32], l, .2, .42));
    muscle("obliques", [.45, 1.38, .2], .78, .2, .6, [0, -.3, -.22]);
    [0, 1, 2].forEach(i => muscle("obliques", [.55, 2.02 - i * .17, .18], .22, .1, .6, [0, -.4, 1.15]));   // serratus
    // ---- back
    muscle("lats", [.5, 1.82, -.22], 1.05, .4, .35, [0, .2, .38]);
    muscle("lower_back", [.12, 1.18, -.28], .8, .14, .7);                   // erector spinae
    // ---- arms
    muscle("biceps", [1.09, 1.9, .1], .72, .21, .9, [0, 0, .1]);
    muscle("triceps", [1.13, 1.9, -.13], .78, .2, .9, [0, 0, .1]);          // long head
    muscle("triceps", [1.21, 2.0, -.04], .5, .15, .9, [0, 0, .12]);         // lateral head
    muscle("forearms", [1.2, 1.17, .06], .78, .18, .8, [0, 0, .12]);        // brachioradialis
    muscle("forearms", [1.26, 1.03, -.05], .68, .14, .8, [0, 0, .14]);      // flexors
    // ---- hips and legs
    muscle("glutes", [.27, .5, -.22], .58, .5, .62);                       // gluteus maximus
    muscle("glutes", [.47, .78, -.08], .32, .3, .6, [0, 0, -.4]);            // gluteus medius
    muscle("quads", [.33, -.33, .21], 1.4, .21, .9, [0, 0, -.03]);          // rectus femoris
    muscle("quads", [.48, -.42, .08], 1.3, .23, .85, [0, 0, -.05]);         // vastus lateralis
    muscle("quads", [.21, -.88, .15], .58, .21, .85, [0, 0, .12]);          // vastus medialis (teardrop)
    muscle("quads", [.17, -.18, .02], .95, .16, .8, [0, 0, .12]);           // adductors
    muscle("hamstrings", [.42, -.45, -.15], 1.32, .19, .85, [0, 0, -.03]);  // biceps femoris
    muscle("hamstrings", [.24, -.45, -.16], 1.32, .18, .85, [0, 0, .03]);   // semitendinosus
    muscle("calves", [.26, -2.02, -.13], .78, .19, .9);                     // gastrocnemius, inner head
    muscle("calves", [.41, -2.06, -.12], .72, .17, .9);                     // gastrocnemius, outer head
    muscle("calves", [.33, -2.55, -.1], .72, .19, .8);                      // soleus
    muscle("calves", [.38, -2.3, .11], 1.05, .11, .9);                      // tibialis
    // ---- body-scan beam
    const scan = ring(1.25, .012, "#5fd8ff", .7); scan.rotation.x = Math.PI / 2; fig.add(scan); const sg = glow("#5fd8ff", 2.6, .22); fig.add(sg);
    animators.push(t => { const y = 3.9 - ((t * .42) % 1) * 7.9; scan.position.y = y; sg.position.y = y; scan.scale.setScalar(y > 2.9 ? .45 : y > .25 ? 1 : .55); });
    // ---- labels
    const POS = {chest: [.45, 2.25, .5], shoulders: [1.1, 2.62, .2], traps: [.3, 2.98, -.2], abs: [0, 1.55, .5], obliques: [.62, 1.35, .35],
      lats: [.75, 1.85, -.35], lower_back: [0, 1.0, -.45], biceps: [1.25, 2.0, .35], triceps: [1.35, 1.9, -.35], forearms: [1.42, 1.05, .2],
      glutes: [.3, .5, -.5], quads: [.42, -.25, .45], hamstrings: [.38, -.5, -.45], calves: [.38, -2.15, -.4]};
    Object.entries(m0).filter(([, v]) => v > .15).sort((a2, b2) => b2[1] - a2[1]).slice(0, 6).forEach(([k, v], i) => {   // labels: gym work only
      const o = new THREE.Object3D(); const p = POS[k] || [0, 0, 0]; o.position.set(i % 2 ? -p[0] : p[0], p[1], p[2]); fig.add(o);
      label(o, `${k.replace("_", " ").toUpperCase()}<small>${Math.round(v * 100)}%</small>`, v > .8 ? "#ff5a4a" : "#ff8a3d"); });
    if(today){
      const ring = new THREE.Mesh(new THREE.TorusGeometry(.9 + walk * 1.4, .035, 8, 90), new THREE.MeshBasicMaterial({color: 0x3dff9a, transparent: true, opacity: .85, blending: THREE.AdditiveBlending, depthWrite: false}));
      ring.rotation.x = Math.PI / 2; ring.position.y = -2.75; fig.add(ring);
      const pulse = ring.clone(); pulse.material = ring.material.clone(); fig.add(pulse);
      animators.push(t => { const k = (t * .5) % 1; pulse.scale.setScalar(1 + k * .8); pulse.material.opacity = .6 * (1 - k); });
      const feet = new THREE.Object3D(); feet.position.set(2.3, -2.2, 0); fig.add(feet);
      label(feet, `${today.toLocaleString()} STEPS TODAY<small>${week.toLocaleString()} this week</small>`, "#3dff9a");
    }
    const top = new THREE.Object3D(); top.position.set(0, 4.3, 0); fig.add(top);
    label(top, `BODY SCAN<small>${Object.values(m0).filter(v => v > .15).length} of ${Math.max(14, Object.keys(m0).length)} muscle groups worked this week</small>`, "#5fd8ff");
    animators.push((t, dt) => group.rotation.y += dt * .3);
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
    const rs = ((data.route || {}).stops || []).filter(s => s.lat != null), onRoute = new Set(rs.map(s => s.name));
    Object.entries(data.landmarks).forEach(([name, [lat, lon]]) => {
      const v = P([lon, lat]), isT = today.has(name), isE = explored.has(name), col = isT ? "#5fd8ff" : isE ? "#ffd23f" : "#3a4656";
      const h = isT ? 3 : isE ? 1.4 : .4, pin = new THREE.Mesh(new THREE.CylinderGeometry(.05, .05, h, 6), mat(col, isT || isE ? .9 : .5));
      pin.position.set(v.x, h / 2, v.z); group.add(pin);
      const dot = glow(col, isT ? 2.4 : isE ? 1.4 : .6, isT || isE ? .9 : .4); dot.position.set(v.x, h, v.z); group.add(dot);
      if((isT || isE) && !onRoute.has(name)){ const p = new THREE.Object3D(); p.position.set(v.x, h, v.z); group.add(p);
        const ev = data.today_places.find(x => x.place === name); label(p, `${esc(name)}${ev ? `<small>${esc(ev.title.slice(0, 22))} · ${ev.time}</small>` : ""}`, col); }
      if(isT) animators.push(t => dot.scale.setScalar(2.4 * (1 + Math.sin(t * 4) * .25)));
    });
    // your real trail: every ~300 m square the phone has been in, brighter where you go often
    const tr = data.trail || [];
    if(tr.length){
      const arr = new Float32Array(tr.length * 3);
      tr.forEach(([lat, lon, n], i) => { const v = P([lon, lat]); arr[i * 3] = v.x; arr[i * 3 + 1] = .04 + Math.min(n, 12) * .025; arr[i * 3 + 2] = v.z; });
      const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      const dots = new THREE.Points(g, new THREE.PointsMaterial({color: C("#ffd23f"), size: .2, transparent: true, opacity: .85,
        blending: THREE.AdditiveBlending, depthWrite: false}));
      group.add(dots); animators.push(t => dots.material.opacity = .65 + Math.sin(t * 1.6) * .2);
    }
    // #17 your day in 3D: today's real path as a light trail, cyan in the morning through gold to pink at night,
    // rising a little through the day, with a comet replaying it and the day's steps
    const tp = (data.today_path || []).filter(p => p && p.length >= 3);
    if(tp.length > 1){
      const t0d = tp[0][0], t1d = tp[tp.length - 1][0] || t0d + 1, pts3 = [], cols = [];
      tp.forEach(([ts, lat, lon]) => { const f = (ts - t0d) / Math.max(1, t1d - t0d), v = P([lon, lat]); pts3.push(new THREE.Vector3(v.x, .15 + f * 1.2, v.z));
        const c = new THREE.Color().setHSL(f < .5 ? (.53 - f * 2 * .4) : (.13 - (f - .5) * 2 * .22 + 1) % 1, 1, .6); cols.push(c.r, c.g, c.b); });
      const seg = Math.min(600, pts3.length * 4), rad = 6, tg = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts3), seg, .09, rad, false), tc = [];
      for(let i = 0; i <= seg; i++){ const j = Math.min(tp.length - 1, Math.round(i / seg * (tp.length - 1))); for(let r = 0; r <= rad; r++) tc.push(cols[j * 3], cols[j * 3 + 1], cols[j * 3 + 2]); }
      tg.setAttribute("color", new THREE.Float32BufferAttribute(tc, 3));
      group.add(new THREE.Mesh(tg, new THREE.MeshBasicMaterial({vertexColors: true, transparent: true, opacity: .95, blending: THREE.AdditiveBlending, depthWrite: false})));
      const hg = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts3), seg, .3, rad, false); hg.setAttribute("color", new THREE.Float32BufferAttribute(tc, 3));
      group.add(new THREE.Mesh(hg, new THREE.MeshBasicMaterial({vertexColors: true, transparent: true, opacity: .18, blending: THREE.AdditiveBlending, depthWrite: false})));
      const comet = glow("#ffffff", 1.6, 1); group.add(comet);
      animators.push(t => { const k = ((t / 14) % 1 + 1) % 1, i = Math.max(0, Math.min(pts3.length - 2, Math.floor(k * (pts3.length - 1)))), f = Math.min(1, k * (pts3.length - 1) - i); comet.position.lerpVectors(pts3[i], pts3[i + 1], f); });
      const end = new THREE.Object3D(); end.position.copy(pts3[pts3.length - 1]).add(new THREE.Vector3(0, 1.2, 0)); group.add(end);
      const st = data.steps || {}; label(end, `TODAY${st.today ? `<small>${st.today.toLocaleString()} steps</small>` : ""}`, "#ffffff");
    }
    // today's route: numbered stops joined by an arc, with a light running along it
    rs.forEach((s, i) => { const v = P([s.lon, s.lat]), p = new THREE.Object3D(); p.position.set(v.x, 1.6 + i * 1.1, v.z); group.add(p);
      const stem = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, 1.6 + i * 1.1, 6), mat("#3dff9a", .7)); stem.position.set(v.x, (1.6 + i * 1.1) / 2, v.z); group.add(stem);
      const d = glow("#3dff9a", .9, .95); d.position.set(v.x, .2, v.z); group.add(d);
      label(p, `${i + 1} · ${esc(s.name.slice(0, 22))}${s.time ? `<small>${s.time}</small>` : ""}`, "#3dff9a"); });
    if(rs.length > 1){
      const pts2 = [];
      for(let i = 0; i < rs.length - 1; i++){ const a = P([rs[i].lon, rs[i].lat]), b = P([rs[i + 1].lon, rs[i + 1].lat]);
        for(let j = 0; j <= 24; j++){ const t = j / 24; pts2.push(new THREE.Vector3(a.x + (b.x - a.x) * t, .2 + Math.sin(Math.PI * t) * (1 + a.distanceTo(b) * .15), a.z + (b.z - a.z) * t)); } }
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts2), new THREE.LineBasicMaterial({color: C("#3dff9a"), transparent: true, opacity: .9})));
      const runner = glow("#ffffff", 1.2, 1); group.add(runner);
      animators.push(t => { const n = pts2.length, k2 = ((Math.floor(t * 12) % n) + n) % n; if(pts2[k2]) runner.position.copy(pts2[k2]); });
    }
    const st = data.trail_stats || {};
    const c = new THREE.Object3D(); c.position.set(0, 4, 0); group.add(c);
    label(c, `SINGAPORE<small>${st.squares ? `${st.squares} spots · ${st.km2} km² explored` : `${explored.size} explored`} · ${rs.length ? rs.length + " stops today" : today.size + " today"}</small>`, "#ffd23f");
    animators.push((t, dt) => group.rotation.y += dt * .05);
    // the real street map lives on its own page
    const b = document.createElement("a"); b.href = "/map.html"; b.target = "_blank"; b.className = "lbl";
    b.style.cssText = "position:absolute;left:50%;bottom:64px;transform:translateX(-50%);pointer-events:auto;cursor:pointer;" +
      "padding:10px 18px;border:1px solid #3dff9a;border-radius:20px;color:#3dff9a;background:rgba(3,6,10,.85);" +
      "font:700 11px Orbitron,sans-serif;letter-spacing:.2em;text-decoration:none;box-shadow:0 0 18px #3dff9a55;z-index:5";
    b.textContent = "🗺 OPEN EXPLORER MAP (STREETS + SIDE QUESTS)";
    root.querySelector(".labels").appendChild(b); labels.push({obj: null, el: b});
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
  if(v !== "body") body3d = false;
  view = BUILD[v] ? v : "week"; yaw = 0; pitch = 0; zoom = 1; clear(); t0 = performance.now();
  const panel = root.querySelector(".bpanel"), flat = view === "body" && !body3d && window.BodyMap;
  panel.classList.toggle("on", !!flat); root.querySelector(".b3d").style.display = view === "body" ? "block" : "none";
  root.querySelector(".b3d").textContent = flat ? "3D HOLOGRAM" : "BODY MAP";
  root.querySelector(".hint").textContent = flat ? "HOVER OR TAP A MUSCLE FOR DETAILS · ESC TO CLOSE" : "DRAG TO SPIN · SCROLL / PINCH TO ZOOM · ESC TO CLOSE";
  if(flat) window.BodyMap.render(panel, data.muscles);
  else try { BUILD[view](); } catch(err){ console.error(err); }
  root.querySelectorAll("[data-v]").forEach(b => b.classList.toggle("on", b.dataset.v === view));
  window.HUD_SFX?.whoosh?.();
  if(speak && window.sendCommand) window.sendCommand(`show me ${view === "business" ? "Shaabaz" : view}`, "JARVIS", true);
}

// #15 tilt the phone to look around; #16 AR: the hologram floats over your table through the camera
let tiltX = 0, tiltY = 0, devA = 0, devB = 0, ar = null;
addEventListener("deviceorientation", e => { if(e.gamma == null) return; tiltX = Math.max(-1, Math.min(1, e.gamma / 35)); tiltY = Math.max(-1, Math.min(1, ((e.beta || 0) - 50) / 35)); devA = e.alpha || 0; devB = e.beta || 0; });
async function toggleAR(){
  const btn = root.querySelector(".ar");
  if(ar){ ar.stream.getTracks().forEach(t => t.stop()); ar.video.remove(); ar = null; root.classList.remove("arOn"); btn.textContent = "📷 AR"; return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({video: {facingMode: "environment"}}), video = document.createElement("video");
    video.className = "arcam"; video.playsInline = true; video.muted = true; video.srcObject = stream; root.prepend(video); await video.play().catch(() => {});
    ar = {stream, video, a: devA, b: devB}; root.classList.add("arOn"); btn.textContent = "✕ AR";
  } catch { window.HUDFX?.toast?.("The camera isn't available for AR here"); }
}
function frame(now){
  if(!open) return;
  const t = (now - t0) / 1000, dt = Math.min(.05, (now - (frame.last || now)) / 1000); frame.last = now;
  if(!reduce) animators.forEach(f => f(t, dt));
  const base = new THREE.Vector3(...CAM[view]).multiplyScalar(zoom), sph = new THREE.Spherical().setFromVector3(base);
  let ty = tiltX * .35, tp2 = tiltY * .2;
  if(ar){ let d = devA - ar.a; if(d > 180) d -= 360; if(d < -180) d += 360; ty = -d * Math.PI / 180; tp2 = (devB - ar.b) * Math.PI / 180 * .8; }   // stays put in the room as you move the phone
  sph.theta += yaw + ty; sph.phi = Math.max(.15, Math.min(Math.PI - .15, sph.phi - pitch - tp2));
  const target = new THREE.Vector3().setFromSpherical(sph); camera.position.lerp(target, Math.min(1, dt * 3)); camera.lookAt(0, view === "body" ? .2 : 0, 0);
  renderer.render(scene, camera);
  const v = new THREE.Vector3();
  labels.forEach(L => { if(!L.obj) return; L.obj.getWorldPosition(v); v.project(camera); const vis = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    L.el.style.display = vis ? "" : "none"; if(vis){ L.el.style.left = (v.x * .5 + .5) * innerWidth + "px"; L.el.style.top = (-v.y * .5 + .5) * innerHeight + "px"; } });
  raf = requestAnimationFrame(frame);
}

async function openHolo(v = "week", opts = {}){
  try { THREE = await loadThree(); } catch { window.logLine?.("JARVIS", "The 3D engine couldn't load.", "error"); return; }
  if(!root) build();
  try { data = window.__HOLO_DATA || await (await fetch("/api/holo")).json(); } catch { return; }   // the phone's offline copy when the laptop is off
  size(); root.classList.add("on"); open = true; camera.position.set(0, 30, 60);
  show(v, !!opts.speak); cancelAnimationFrame(raf); raf = requestAnimationFrame(frame);
}
function close(){ if(ar) toggleAR(); open = false; stopTour(); cancelAnimationFrame(raf); root?.classList.remove("on"); window.HUD_SFX?.whoosh?.(); }

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
