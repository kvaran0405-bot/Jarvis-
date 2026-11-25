package os.jarvis.app;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Calendar;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * The phone's JARVIS working in the background, screen on or off, when the laptop is out of reach.
 *
 * It runs the same brain as the solo page (an invisible copy of it), so there is one JARVIS, not two. Every ~10
 * minutes (and every couple of minutes while the phone is awake) it:
 * - answers your Telegram messages and voice notes while the laptop is off (the laptop takes the bot back when it
 *   returns; nothing is answered twice),
 * - gives the morning brief and the night review if the laptop can't,
 * - speaks up first: time to leave for your next plan, rain on the way,
 * - and, always: tells you when your buses are coming if you're waiting at a stop.
 */
final class SoloBrain {
    private SoloBrain() {}

    private static WebView view;
    private static volatile boolean ready = false;
    private static final Handler ui = new Handler(Looper.getMainLooper());
    private static final Map<String, CountDownLatch> waits = new ConcurrentHashMap<>();
    private static final Map<String, String> answers = new ConcurrentHashMap<>();
    private static long lastTick = 0, downSince = 0;

    // ------------------------------------------------------------ the invisible brain page
    static void ensure(Context c) {
        if (view != null) return;
        Context app = c.getApplicationContext();
        CountDownLatch made = new CountDownLatch(1);
        ui.post(() -> {
            try {
                view = new WebView(app);
                WebSettings s = view.getSettings();
                s.setJavaScriptEnabled(true);
                s.setDomStorageEnabled(true);
                s.setAllowFileAccess(true);
                view.addJavascriptInterface(new Bridge(app), "JarvisNative");
                view.setWebViewClient(new WebViewClient() {
                    @Override public void onPageFinished(WebView v, String url) { ready = true; }
                });
                view.resumeTimers();
                view.loadUrl(Solo.pageUrl(app) + "?headless=1");
            } catch (Exception ignored) { view = null; }
            made.countDown();
        });
        try { made.await(5, TimeUnit.SECONDS); } catch (InterruptedException ignored) {}
    }

    /** Run a JS function on the brain page and wait for its answer (null if it took too long). */
    private static String call(Context c, String fn, String argsJs, int seconds) {
        ensure(c);
        for (int i = 0; i < 40 && !ready; i++) { try { Thread.sleep(250); } catch (InterruptedException e) { return null; } }
        if (view == null || !ready) return null;
        String id = Long.toString(System.nanoTime(), 36);
        CountDownLatch l = new CountDownLatch(1);
        waits.put(id, l);
        ui.post(() -> view.evaluateJavascript("window." + fn + " && window." + fn + "(" + JSONObject.quote(id) + (argsJs.isEmpty() ? "" : "," + argsJs) + ")", null));
        try { l.await(seconds, TimeUnit.SECONDS); } catch (InterruptedException ignored) {}
        waits.remove(id);
        return answers.remove(id);
    }

    static String ask(Context c, String text, String via) { return call(c, "soloAsk", JSONObject.quote(text) + "," + JSONObject.quote(via), 90); }

    // ------------------------------------------------------------ the heartbeat
    /** Called by the link service while the phone is awake, and by the alarm every ~10 minutes while it sleeps. */
    static void tick(Context c, boolean fromAlarm) {
        long now = System.currentTimeMillis();
        if (!fromAlarm && now - lastTick < 2 * 60_000L) return;
        lastTick = now;
        boolean laptop = probe(c);
        if (laptop) { downSince = 0; Solo.lastOk = now; }
        else { Solo.lastFail = now; if (downSince == 0) downSince = now; }
        boolean solo = !laptop && Net.base(c) != null && now - downSince > 3 * 60_000L;
        if (solo) {
            telegram(c);
            routines(c);
        }
        call(c, "soloWatch", solo ? "true" : "false", 60);   // bus alerts always; leave and rain alerts only in solo
    }

    private static boolean probe(Context c) {
        if (!Net.linked(c)) return false;
        try { Net.call(c, "/api/widget", null, 6000); return true; } catch (Exception e) { return false; }
    }

    static void schedule(Context c) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        PendingIntent pi = PendingIntent.getBroadcast(c, 9090, new Intent(c, Beat.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, android.os.SystemClock.elapsedRealtime() + 10 * 60_000L, pi);
    }

    /** Wakes the phone briefly every ~10 minutes, even in deep sleep, to do the above. */
    public static class Beat extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) {
            schedule(c);
            JarvisLink.start(c);
            PendingResult done = goAsync();
            PowerManager.WakeLock wl = c.getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jarvis:beat");
            wl.acquire(2 * 60_000L);
            new Thread(() -> { try { tick(c, true); } finally { if (wl.isHeld()) wl.release(); done.finish(); } }).start();
        }
    }

    // ------------------------------------------------------------ morning brief and night review when the laptop can't
    private static void routines(Context c) {
        SharedPreferences p = c.getSharedPreferences(Solo.PREFS, Context.MODE_PRIVATE);
        Calendar cal = Calendar.getInstance();
        String day = String.format(java.util.Locale.US, "%tF", cal);
        int mins = cal.get(Calendar.HOUR_OF_DAY) * 60 + cal.get(Calendar.MINUTE);
        int morning = hm(keys(c).optString("morning_at", "07:00"), 7 * 60), night = 22 * 60 + 30;
        if (mins >= morning && mins < morning + 180 && !day.equals(p.getString("did_morning", ""))) {
            String r = call(c, "soloRoutine", "\"morning\"", 90);
            if (r != null) { p.edit().putString("did_morning", day).apply(); deliver(c, "☀ Good morning, Sir", r); }
        }
        if (mins >= night && !day.equals(p.getString("did_night", ""))) {
            String r = call(c, "soloRoutine", "\"night\"", 90);
            if (r != null) { p.edit().putString("did_night", day).apply(); deliver(c, "🌙 Your day, Sir", r); }
        }
    }

    private static int hm(String s, int dflt) {
        try { String[] a = s.split(":"); return Integer.parseInt(a[0].trim()) * 60 + Integer.parseInt(a[1].trim()); } catch (Exception e) { return dflt; }
    }

    private static JSONObject keys(Context c) {
        try { return new JSONObject(c.getSharedPreferences(Solo.PREFS, Context.MODE_PRIVATE).getString("keys", "{}")); } catch (Exception e) { return new JSONObject(); }
    }

    /** A notification on the phone, and the same on Telegram while the phone is running the bot. */
    static void deliver(Context c, String title, String text) {
        notifyOwner(c, title, text, false);
        if (!tgToken(c).isEmpty()) tgSend(c, text);
    }

    static void notifyOwner(Context c, String title, String text, boolean urgent) {
        JarvisLink.channels(c);
        Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int nid = (title + text).hashCode();
        PendingIntent pi = PendingIntent.getActivity(c, nid, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(c, urgent ? JarvisLink.URGENT : JarvisLink.ALERTS)
                .setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text)).setColor(Color.parseColor(urgent ? "#FF3B3B" : "#FFD23F"))
                .setContentIntent(pi).setAutoCancel(true).build();
        c.getSystemService(NotificationManager.class).notify(nid, n);
    }

    // ------------------------------------------------------------ Telegram while the laptop is away
    private static String tgToken(Context c) { return keys(c).optString("telegram_token", ""); }

    private static String tgChat(Context c) { return keys(c).optString("telegram_chat", ""); }

    private static JSONObject tg(Context c, String method, String query, int timeoutMs) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL("https://api.telegram.org/bot" + tgToken(c) + "/" + method + (query.isEmpty() ? "" : "?" + query)).openConnection();
        conn.setConnectTimeout(10000);
        conn.setReadTimeout(timeoutMs);
        try (InputStream in = conn.getResponseCode() < 400 ? conn.getInputStream() : conn.getErrorStream()) { return new JSONObject(read(in)); }
    }

    private static String read(InputStream in) throws Exception {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] b = new byte[8192];
        for (int r; (r = in.read(b)) != -1; ) buf.write(b, 0, r);
        return buf.toString("UTF-8");
    }

    static void tgSend(Context c, String text) {
        try { tg(c, "sendMessage", "chat_id=" + enc(tgChat(c)) + "&text=" + enc(text.length() > 3900 ? text.substring(0, 3900) : text), 20000); } catch (Exception ignored) {}
    }

    private static String enc(String s) { try { return URLEncoder.encode(s, "UTF-8"); } catch (Exception e) { return ""; } }

    private static void telegram(Context c) {
        if (tgToken(c).isEmpty() || tgChat(c).isEmpty()) return;
        SharedPreferences p = c.getSharedPreferences(Solo.PREFS, Context.MODE_PRIVATE);
        try {
            long offset = p.getLong("tg_offset", 0);
            JSONObject r = tg(c, "getUpdates", "timeout=20&offset=" + offset, 30000);
            JSONArray ups = r.optJSONArray("result");
            if (ups == null) return;
            for (int i = 0; i < ups.length(); i++) {
                JSONObject u = ups.getJSONObject(i);
                p.edit().putLong("tg_offset", u.getLong("update_id") + 1).apply();
                JSONObject m = u.optJSONObject("message");
                if (m == null || !tgChat(c).equals(String.valueOf(m.optJSONObject("chat") == null ? "" : m.getJSONObject("chat").opt("id")))) continue;
                String text = m.optString("text", "").trim();
                JSONObject voice = m.optJSONObject("voice");
                if (voice != null) { tgVoice(c, voice); continue; }
                if (text.isEmpty()) continue;
                if (text.matches("(?i)^/?update$|^/installapp$|^/start$")) {
                    tgSend(c, "💻 The laptop's off or asleep right now, Sir, so I'm running on your phone. I'll do that the moment it's back.");
                    continue;
                }
                tg(c, "sendChatAction", "chat_id=" + enc(tgChat(c)) + "&action=typing", 10000);
                String reply = ask(c, text, "telegram");
                tgSend(c, reply == null ? "I'm on your phone (laptop's off) and that took too long, Sir. Try again?" : "📱 " + reply);
            }
        } catch (Exception ignored) {}
    }

    private static void tgVoice(Context c, JSONObject voice) {
        try {
            tg(c, "sendChatAction", "chat_id=" + enc(tgChat(c)) + "&action=typing", 10000);
            JSONObject f = tg(c, "getFile", "file_id=" + enc(voice.getString("file_id")), 20000).getJSONObject("result");
            HttpURLConnection conn = (HttpURLConnection) new URL("https://api.telegram.org/file/bot" + tgToken(c) + "/" + f.getString("file_path")).openConnection();
            conn.setReadTimeout(30000);
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            try (InputStream in = conn.getInputStream()) { byte[] b = new byte[8192]; for (int r; (r = in.read(b)) != -1; ) buf.write(b, 0, r); }
            String b64 = android.util.Base64.encodeToString(buf.toByteArray(), android.util.Base64.NO_WRAP);
            String reply = call(c, "soloHear", JSONObject.quote(b64) + ",\"audio/ogg\"", 120);
            tgSend(c, reply == null ? "🎙 I couldn't make that one out, Sir. Once more?" : reply);
        } catch (Exception e) { tgSend(c, "🎙 I couldn't open that voice note, Sir."); }
    }

    // ------------------------------------------------------------ what the brain page can call (no screen, no mic)
    static final class Bridge {
        private final Context c;
        Bridge(Context c) { this.c = c; }

        @JavascriptInterface public boolean headless() { return true; }
        @JavascriptInterface public String soloPack() { return Solo.packForPage(c); }
        @JavascriptInterface public boolean laptopUp() { return Solo.laptopUp(); }
        @JavascriptInterface public void soloSave(String itemJson) { Solo.save(c, itemJson); }
        @JavascriptInterface public String soloRemind(String uid, double at, String text) { return Solo.remind(c, uid, (long) at, text, false); }
        @JavascriptInterface public boolean exactReminders() { return Solo.exactAllowed(c); }
        @JavascriptInterface public String soloLocation() { return Solo.location(c); }
        @JavascriptInterface public String soloDay() { return Solo.day(c); }
        @JavascriptInterface public String soloNotes() { return Solo.notes(c); }
        @JavascriptInterface public boolean soloNotesAccess() { return Solo.notesAccess(c); }
        @JavascriptInterface public String soloPower(String kind, String args) { return Solo.power(c, kind, args); }
        @JavascriptInterface public void notify(String title, String text, boolean urgent) { notifyOwner(c, title, text, urgent); }
        @JavascriptInterface public boolean telegramOn() { return !tgToken(c).isEmpty(); }
        @JavascriptInterface public void telegram(String text) { new Thread(() -> tgSend(c, text)).start(); }

        @JavascriptInterface
        public void answer(String id, String text) {
            answers.put(id, text == null ? "" : text);
            CountDownLatch l = waits.get(id);
            if (l != null) l.countDown();
        }

        @JavascriptInterface
        public void soloFetch(String id, String url, String method, String headersJson, String body) {
            new Thread(() -> {
                String[] r = Solo.fetch(c, url, method, headersJson, body);
                String js = "window.__soloFetch && window.__soloFetch(" + JSONObject.quote(id) + "," + r[0] + "," + JSONObject.quote(r[1]) + ")";
                ui.post(() -> { if (view != null) view.evaluateJavascript(js, null); });
            }).start();
        }
    }
}
