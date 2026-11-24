/* The JARVIS core (#18): thousands of glowing particles that breathe when idle, ripple inward when listening, swirl
   purple when thinking, and pulse with his actual voice when speaking. Mount it anywhere:
     const core = JarvisCore.mount(element, {read: () => ({state, amp, color})});
   `read` is asked every frame; JarvisCore.attachAudio(audioElement) makes it follow a real voice clip.
   Falls back silently (returns null) where WebGL isn't available, so the old 2D reactor stays. */
(() => {
const NOISE = `vec3 mod289(vec3 x){return x-floor(x*(1./289.))*289.;} vec4 mod289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 permute(vec4 x){return mod289(((x*34.)+1.)*x);} vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){const vec2 C=vec2(1./6.,1./3.);const vec4 D=vec4(0.,.5,1.,2.);vec3 i=floor(v+dot(v,C.yyy));vec3 x0=v-i+dot(i,C.xxx);
vec3 g=step(x0.yzx,x0.xyz);vec3 l=1.-g;vec3 i1=min(g.xyz,l.zxy);vec3 i2=max(g.xyz,l.zxy);vec3 x1=x0-i1+C.xxx;vec3 x2=x0-i2+C.yyy;vec3 x3=x0-D.yyy;
i=mod289(i);vec4 p=permute(permute(permute(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
float n_=.142857142857;vec3 ns=n_*D.wyz-D.xzx;vec4 j=p-49.*floor(p*ns.z*ns.z);vec4 x_=floor(j*ns.z);vec4 y_=floor(j-7.*x_);
vec4 x=x_*ns.x+ns.yyyy;vec4 y=y_*ns.x+ns.yyyy;vec4 h=1.-abs(x)-abs(y);vec4 b0=vec4(x.xy,y.xy);vec4 b1=vec4(x.zw,y.zw);
vec4 s0=floor(b0)*2.+1.;vec4 s1=floor(b1)*2.+1.;vec4 sh=-step(h,vec4(0.));vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy;vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
vec3 p0=vec3(a0.xy,h.x);vec3 p1=vec3(a0.zw,h.y);vec3 p2=vec3(a1.xy,h.z);vec3 p3=vec3(a1.zw,h.w);
vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);m=m*m;return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));}`;

let AC = null, analyser = null, buf = null;
function attachAudio(el){
  try {
    AC = AC || new (window.AudioContext || window.webkitAudioContext)(); AC.resume?.();
    if (AC.state !== "running") return;   // never risk muting his voice: without running audio, the core imitates speech instead
    if (!analyser){ analyser = AC.createAnalyser(); analyser.fftSize = 256; buf = new Uint8Array(analyser.frequencyBinCount); analyser.connect(AC.destination); }
    if (el.__core) return; el.__core = true;
    AC.createMediaElementSource(el).connect(analyser);
  } catch {}
}
function liveAmp(){
  if (!analyser) return null; analyser.getByteFrequencyData(buf); let s = 0, lo = 0, hi = 0;
  for (let i = 0; i < buf.length; i++){ s += buf[i]; if (i < 12) lo += buf[i]; else if (i > 40) hi += buf[i]; }
  const a = s / buf.length / 90; return a > .02 ? {a: Math.min(1, a), lo: Math.min(1, lo / 12 / 170), hi: Math.min(1, hi / (buf.length - 40) / 70)} : null;
}

function mount(el, opts = {}){
  const THREE = window.THREE; if (!THREE) return null;
  const cv = document.createElement("canvas"); cv.className = "core3d"; cv.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
  let R; try { R = new THREE.WebGLRenderer({canvas: cv, antialias: true, alpha: true}); } catch { return null; }
  el.appendChild(cv);
  const small = Math.min(innerWidth, innerHeight) < 700 || /Android|iPhone/i.test(navigator.userAgent);
  R.setPixelRatio(Math.min(devicePixelRatio || 1, small ? 1.75 : 2)); R.setClearColor(0, 0);
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(45, 1, .1, 100);
  const U = {t: {value: 0}, amp: {value: 0}, low: {value: 0}, high: {value: 0}, swirl: {value: 0}, pull: {value: 0},
             col: {value: new THREE.Color("#ffd23f")}, col2: {value: new THREE.Color("#5fd8ff")}, px: {value: R.getPixelRatio()}};
  function shell(n, radius, size, layer){
    const pos = new Float32Array(n * 3), rnd = new Float32Array(n), ga = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++){ const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = ga * i; pos.set([Math.cos(th) * r, y, Math.sin(th) * r], i * 3); rnd[i] = Math.random(); }
    const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(pos, 3)); g.setAttribute("rnd", new THREE.BufferAttribute(rnd, 1));
    const m = new THREE.ShaderMaterial({uniforms: {...U, R: {value: radius}, S: {value: size}, L: {value: layer}}, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: NOISE + `
        uniform float t, amp, low, high, swirl, pull, R, S, L, px; attribute float rnd; varying float vA;
        void main(){ vec3 p = position; float a = swirl * (1.2 + L) * t * .6 + swirl * p.y * 2.; p.xz = mat2(cos(a), -sin(a), sin(a), cos(a)) * p.xz;
          float n = snoise(p * (1.6 + L * .8) + vec3(0., t * (.25 + amp * .9), t * .1)), n2 = snoise(p * 4.5 + t * (.6 + high * 2.));
          float r = R * (1. + n * (.06 + amp * .32 + low * .22) + n2 * high * .1 - pull * .18 * (.5 + .5 * sin(t * 6. - length(p.xy) * 8.)));
          r += L * amp * rnd * .9; vec4 mv = modelViewMatrix * vec4(p * r, 1.); gl_Position = projectionMatrix * mv;
          gl_PointSize = S * px * (1. + amp * 1.2 + rnd * .6) * (10. / -mv.z); vA = .35 + .65 * smoothstep(-.3, .8, n); }`,
      fragmentShader: `uniform vec3 col, col2; uniform float L, amp; varying float vA;
        void main(){ vec2 d = gl_PointCoord - .5; float f = smoothstep(.5, 0., length(d)); f *= f;
          vec3 c = mix(col2, col, clamp(vA + amp * .5 - L * .35, 0., 1.)); c = mix(c, vec3(1.), pow(f, 6.) * .6);
          gl_FragColor = vec4(c, f * vA * (L > .5 ? .35 + amp * .5 : .9)); }`});
    const pts = new THREE.Points(g, m); scene.add(pts); return pts;
  }
  const core = shell(small ? 8000 : 12000, 2.2, 2.2, 0), halo = shell(small ? 2500 : 4000, 2.9, 1.6, 1);
  const tex = (() => { const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d"), gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(.25, "rgba(255,255,255,.55)"); gr.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c); })();
  const heart = new THREE.Sprite(new THREE.SpriteMaterial({map: tex, color: 0xffd23f, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false})); heart.scale.set(3.2, 3.2, 1); scene.add(heart);
  const rings = [[3.5, .012, [1.1, .3, 0], 1.4, .9], [4, .006, [-.5, .8, .2], -.9, .55], [4.45, .02, [.2, -.4, .9], .55, .8]].map(([r, w, rot, sp, op], k) => {
    const grp = new THREE.Group(); grp.rotation.set(...rot);
    const arc = new THREE.Mesh(new THREE.TorusGeometry(r, w * 3, 6, 160, Math.PI * (1.1 + k * .25)), new THREE.MeshBasicMaterial({color: 0xffd23f, transparent: true, opacity: op, blending: THREE.AdditiveBlending, depthWrite: false}));
    grp.add(arc); scene.add(grp); return {arc, sp}; });
  const target = new THREE.Color("#ffd23f"), target2 = new THREE.Color("#5fd8ff");
  let amp = 0, low = 0, high = 0, swirl = 0, pull = 0, last = performance.now(), alive = true, yaw = 0, fake = 0;
  function size(){ const r = el.getBoundingClientRect(), s = Math.max(40, Math.min(r.width, r.height)); R.setSize(r.width, r.height, false); cam.aspect = r.width / Math.max(1, r.height); cam.updateProjectionMatrix(); }
  const ro = window.ResizeObserver ? new ResizeObserver(size) : null; ro?.observe(el); size();
  function frame(now){
    if (!alive) return;
    const dt = Math.max(0, Math.min(.05, (now - last) / 1000)); last = now; const t = now / 1000;
    const st = (opts.read && opts.read()) || {}, state = st.state || "idle";
    target.set(state === "listen" ? "#5fd8ff" : state === "think" ? "#b06bff" : (st.color || "#ffd23f")); target2.set(state === "think" ? "#b06bff" : "#5fd8ff");
    let a = 0, lo = 0, hi = 0; const live = state === "speak" ? liveAmp() : null;
    if (live){ a = live.a; lo = live.lo; hi = live.hi; }
    else if (state === "speak"){ if (st.amp != null) a = st.amp; else { fake += dt * 9; a = .35 + .3 * Math.abs(Math.sin(fake)) * (.6 + .4 * Math.sin(fake * 2.7)); } lo = a * (.6 + .4 * Math.sin(t * 17)); hi = a * (.5 + .5 * Math.sin(t * 31 + 1)); }
    const want = state === "idle" ? .05 + .03 * Math.sin(t * 1.6) : state === "listen" ? .12 : state === "think" ? .18 : 0;
    amp += (Math.max(a, want) - amp) * Math.min(1, dt * 14); low += (lo - low) * Math.min(1, dt * 10); high += (hi - high) * Math.min(1, dt * 12);
    swirl += ((state === "think" ? 1 : .08) - swirl) * dt * 2; pull += ((state === "listen" ? 1 : 0) - pull) * dt * 3;
    U.t.value = t; U.amp.value = amp; U.low.value = low; U.high.value = high; U.swirl.value = swirl; U.pull.value = pull;
    U.col.value.lerp(target, Math.min(1, dt * 3)); U.col2.value.lerp(target2, Math.min(1, dt * 3));
    [core, halo].forEach(o => { o.material.uniforms.col.value.copy(U.col.value); o.material.uniforms.col2.value.copy(U.col2.value); });
    core.rotation.y += dt * (.15 + swirl * .6); halo.rotation.y -= dt * (.08 + swirl * .3);
    heart.material.color.copy(U.col.value); heart.scale.setScalar(2.6 + amp * 3.2 + Math.sin(t * 2) * .15);
    rings.forEach(r => { r.arc.rotation.z += dt * r.sp * (1 + amp * 3 + swirl * 2); r.arc.material.color.copy(U.col.value); });
    yaw += dt * .06; const d = (opts.distance || 12.5) * Math.max(1, .9 / cam.aspect);
    cam.position.set(d * Math.sin(yaw) * Math.cos(.15), d * Math.sin(.15), d * Math.cos(yaw) * Math.cos(.15)); cam.lookAt(0, 0, 0);
    if (!document.hidden) R.render(scene, cam);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  return {canvas: cv, destroy(){ alive = false; ro?.disconnect(); cv.remove(); R.dispose(); }};
}
window.JarvisCore = {mount, attachAudio};
})();
