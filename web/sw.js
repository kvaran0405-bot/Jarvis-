// Makes JARVIS installable as a phone app. Pages load from the network (always live); the app shell is cached
// only so the app opens with a friendly message when the laptop is offline.
const CACHE = "jarvis-shell-v1";
const SHELL = ["/command-centre.html", "/call.html", "/login.html", "/icon-192.png", "/manifest.webmanifest"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {})); self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/")) return;   // live data: never cached
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && SHELL.includes(url.pathname)) { const copy = r.clone(); caches.open(CACHE).then(c => c.put(url.pathname, copy)); }
    return r;
  }).catch(() => caches.match(url.pathname).then(r => r || new Response(
    "<body style='background:#07090d;color:#ffd23f;font-family:sans-serif;display:grid;place-items:center;height:100vh;text-align:center'>" +
    "<div><h2>JARVIS is offline</h2><p style='color:#8a95a7'>Your laptop is off, asleep, or not connected to Tailscale.</p></div></body>",
    {headers: {"Content-Type": "text/html"}}))));
});
