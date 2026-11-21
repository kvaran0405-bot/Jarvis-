// JARVIS WhatsApp bridge: links your personal WhatsApp (like WhatsApp Web) and exposes a small local API
// that only JARVIS on this computer can use. Messages you send to your own "Message yourself" chat are
// forwarded to JARVIS as orders; JARVIS replies there with a 🤖 prefix.
//
//   First run: a QR code appears. On your phone: WhatsApp > Settings > Linked devices > Link a device.
const fs = require("fs");
const path = require("path");
const http = require("http");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");

// Read ../.env (same settings file JARVIS uses)
const envFile = path.join(__dirname, "..", ".env");
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m && !line.trim().startsWith("#") && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/\s+#.*$/, "").replace(/^['"]|['"]$/g, "");
  }
}
const TOKEN = process.env.JARVIS_BRIDGE_TOKEN || "";
const PORT = Number((process.env.JARVIS_WHATSAPP_BRIDGE || "http://127.0.0.1:7335").split(":").pop()) || 7335;
const JARVIS = `http://127.0.0.1:${process.env.JARVIS_PORT || 7334}`;
if (!TOKEN) { console.error("Set JARVIS_BRIDGE_TOKEN in .env first (any long random text)."); process.exit(1); }

let ready = false;
const selfIds = new Set();
const BOT_PREFIX = "🤖";

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: path.join(__dirname, ".session") }),
  puppeteer: { headless: true, args: ["--no-sandbox", "--disable-setuid-sandbox"] },
});

client.on("qr", qr => {
  console.log("\nScan this with your phone: WhatsApp > Settings > Linked devices > Link a device\n");
  qrcode.generate(qr, { small: true });
});
client.on("authenticated", () => console.log("WhatsApp: logged in"));
client.on("auth_failure", m => console.error("WhatsApp: login failed -", m));
client.on("disconnected", r => { ready = false; console.error("WhatsApp: disconnected -", r); });
client.on("ready", async () => {
  selfIds.add(client.info.wid._serialized);
  try {
    const [ids] = await client.getContactLidAndPhone([client.info.wid._serialized]);
    if (ids && ids.lid) selfIds.add(ids.lid);
  } catch (_) { /* older WhatsApp accounts have no LID */ }
  ready = true;
  console.log(`WhatsApp: ready as ${client.info.pushname} (${client.info.wid.user}). Bridge on 127.0.0.1:${PORT}`);
});

// Orders from the owner: anything typed in your own "Message yourself" chat.
client.on("message_create", async msg => {
  try {
    if (!msg.fromMe || !selfIds.has(msg.to) || !msg.body || msg.body.startsWith(BOT_PREFIX)) return;
    await fetch(`${JARVIS}/api/whatsapp/incoming`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Jarvis-Token": TOKEN },
      body: JSON.stringify({ text: msg.body }),
    });
  } catch (e) { console.error("Could not reach JARVIS:", e.message); }
});

async function chatIdFor(number) {
  const digits = String(number).replace(/\D/g, "");
  if (selfIds.has(`${digits}@c.us`)) return `${digits}@c.us`;
  const id = await client.getNumberId(digits);
  if (!id) throw new Error(`${digits} is not on WhatsApp`);
  return id._serialized;
}

function summary(m) {
  return { from_me: m.fromMe, author: m.author || m.from, type: m.type, timestamp: m.timestamp,
           content: m.hasMedia && !m.body ? `[${m.type}]` : m.body };
}

async function handle(req, url, body) {
  if (url.pathname === "/status") return { ready, me: ready ? client.info.wid.user : null };
  if (!ready) throw Object.assign(new Error("WhatsApp is not ready yet"), { code: 503 });
  if (req.method === "POST" && url.pathname === "/send") {
    const id = await chatIdFor(body.to);
    const sent = await client.sendMessage(id, String(body.text || ""));
    return { ok: true, id: sent.id._serialized };
  }
  if (req.method === "POST" && url.pathname === "/send-file") {
    const id = await chatIdFor(body.to);
    const media = MessageMedia.fromFilePath(body.path);
    await client.sendMessage(id, media, { caption: body.caption || "" });
    return { ok: true };
  }
  if (url.pathname === "/chats") {
    const limit = Number(url.searchParams.get("limit") || 15);
    const unread = url.searchParams.get("unread") === "1";
    let chats = (await client.getChats()).filter(c => !selfIds.has(c.id._serialized) && !c.archived);
    if (unread) chats = chats.filter(c => c.unreadCount > 0);
    return chats.slice(0, limit).map(c => ({
      chat_id: c.id._serialized, name: c.name, is_group: c.isGroup, unread: c.unreadCount, timestamp: c.timestamp,
      last_message: c.lastMessage ? summary(c.lastMessage) : null,
    }));
  }
  if (url.pathname === "/messages") {
    const chat = await client.getChatById(url.searchParams.get("chat"));
    const msgs = await chat.fetchMessages({ limit: Number(url.searchParams.get("limit") || 20) });
    return { chat: chat.name, messages: msgs.map(summary) };
  }
  throw Object.assign(new Error("not found"), { code: 404 });
}

http.createServer((req, res) => {
  const reply = (code, data) => { res.writeHead(code, { "Content-Type": "application/json" }); res.end(JSON.stringify(data)); };
  if (req.headers["x-jarvis-token"] !== TOKEN) return reply(403, { error: "bad token" });
  let raw = "";
  req.on("data", c => { raw += c; if (raw.length > 5e6) req.destroy(); });
  req.on("end", async () => {
    try {
      const url = new URL(req.url, "http://localhost");
      reply(200, await handle(req, url, raw ? JSON.parse(raw) : {}));
    } catch (e) { reply(e.code || 500, { error: e.message }); }
  });
}).listen(PORT, "127.0.0.1");

client.initialize().catch(e => console.error("WhatsApp failed to start:", e.message));
