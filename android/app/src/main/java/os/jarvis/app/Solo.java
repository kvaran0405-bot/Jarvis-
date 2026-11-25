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
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

/**
 * Solo JARVIS: lets the phone be JARVIS by itself while the laptop is off or far away.
 *
 * - While the laptop is reachable, keeps a "solo pack" (memories, tasks, events, places, reminders, the team) and the
 *   free keys the phone's own brain needs. Keys stay in this app's private storage and are only ever added to
 *   requests going to their own services (Google Gemini, OneMap, LTA). The page never sees them.
 * - Whatever the phone does alone (things to remember, tasks, reminders, notes, the conversation) is queued here and
 *   sent back to the laptop the next time it answers.
 * - Reminders ring on the phone by themselves. The laptop's own reminders are also kept here as a backup and only
 *   ring on the phone when the laptop hasn't been reachable for a while (no double alerts).
 */
final class Solo {
    private Solo() {}

    static final String PREFS = "jarvis_solo";
    static volatile long lastOk = 0, lastFail = 0;   // last time the laptop answered / didn't (set by JarvisLink)
    private static long lastPack = 0;

    static boolean laptopUp() { return System.currentTimeMillis() - lastOk < 90_000L && lastOk >= lastFail; }

    /** The laptop has clearly been unreachable just now: skip waiting for it and open the phone's own JARVIS. */
    static boolean laptopDown() {
        return lastFail > lastOk && System.currentTimeMillis() - lastFail < 3 * 60_000L;
    }

    private static SharedPreferences p(Context c) { return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    // ------------------------------------------------------------ while linked: refresh the pack, send the queue
    static void whileLinked(Context c) {
        lastOk = System.currentTimeMillis();
        flush(c);
        if (System.currentTimeMillis() - lastPack > 20 * 60_000L) refresh(c);
    }

    static void refresh(Context c) {
        try {
            JSONObject r = new JSONObject(Net.call(c, "/api/phone/solo", null, 20000));
            JSONObject pack = r.optJSONObject("pack"), keys = r.optJSONObject("keys");
            SharedPreferences.Editor e = p(c).edit();
            if (pack != null) e.putString("pack", pack.toString());
            if (keys != null) e.putString("keys", keys.toString());
            e.apply();
            lastPack = System.currentTimeMillis();
            if (pack != null) backupReminders(c, pack.optJSONArray("reminders"));
        } catch (Exception ignored) { return; }
        try {   // the newest solo page, so "update" on the laptop updates the phone's own JARVIS too
            String page = Net.call(c, "/api/phone/solo-page", null, 20000);
            if (page.contains("SOLO-JARVIS")) {
                try (FileOutputStream o = new FileOutputStream(new File(c.getFilesDir(), "solo.html"))) {
                    o.write(page.getBytes(StandardCharsets.UTF_8));
                }
            }
        } catch (Exception ignored) {}
    }

    static String pageUrl(Context c) {
        File f = new File(c.getFilesDir(), "solo.html");
        return f.exists() ? Uri.fromFile(f).toString() : "file:///android_asset/solo.html";
    }

    /** The pack for the page, without the keys (just whether each is there). */
    static String packForPage(Context c) {
        try {
            JSONObject pack = new JSONObject(p(c).getString("pack", "{}"));
            JSONObject k = keys(c);
            JSONObject has = new JSONObject();
            has.put("gemini", !k.optString("gemini").isEmpty());
            has.put("lta", !k.optString("lta").isEmpty());
            has.put("onemap", !k.optString("onemap_email").isEmpty());
            pack.put("has", has);
            pack.put("model", k.optString("gemini_model", "gemini-flash-latest"));
            pack.put("queued", outbox(c).length());
            return pack.toString();
        } catch (Exception e) { return "{}"; }
    }

    private static JSONObject keys(Context c) {
        try { return new JSONObject(p(c).getString("keys", "{}")); } catch (Exception e) { return new JSONObject(); }
    }

    // ------------------------------------------------------------ the queue back to the laptop
    static synchronized JSONArray outbox(Context c) {
        try { return new JSONArray(p(c).getString("outbox", "[]")); } catch (Exception e) { return new JSONArray(); }
    }

    static synchronized void save(Context c, String itemJson) {
        try {
            JSONArray a = outbox(c);
            JSONObject it = new JSONObject(itemJson);
            if (!it.has("uid")) it.put("uid", Long.toString(System.nanoTime(), 36));
            a.put(it);
            while (a.length() > 2000) a.remove(0);
            p(c).edit().putString("outbox", a.toString()).apply();
        } catch (Exception ignored) {}
    }

    static void flush(Context c) {
        JSONArray a = outbox(c);
        if (a.length() == 0) return;
        try {
            JSONObject body = new JSONObject();
            body.put("items", a);
            Net.call(c, "/api/phone/solo-sync", body.toString(), 20000);
            synchronized (Solo.class) {   // drop only what was sent; anything queued meanwhile stays
                JSONArray now = outbox(c), keep = new JSONArray();
                for (int i = a.length(); i < now.length(); i++) keep.put(now.get(i));
                p(c).edit().putString("outbox", keep.toString()).apply();
            }
        } catch (Exception ignored) {}
    }

    // ------------------------------------------------------------ the phone's own internet calls (keys added here)
    static String[] fetch(Context c, String url, String method, String headersJson, String body) {
        try {
            URL u = new URL(url);
            String host = u.getHost();
            if (!"https".equals(u.getProtocol())) return new String[]{"0", "https only"};
            if (Net.isFinance(url)) return new String[]{"0", "bank and finance sites are off limits"};
            HttpURLConnection conn = (HttpURLConnection) u.openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(45000);
            conn.setRequestProperty("User-Agent", "JARVIS personal assistant (phone)");
            if (headersJson != null && !headersJson.isEmpty()) {
                JSONObject h = new JSONObject(headersJson);
                for (Iterator<String> it = h.keys(); it.hasNext(); ) { String k = it.next(); conn.setRequestProperty(k, h.getString(k)); }
            }
            JSONObject k = keys(c);
            if (host.equals("generativelanguage.googleapis.com")) conn.setRequestProperty("x-goog-api-key", k.optString("gemini"));
            if (host.equals("datamall2.mytransport.sg")) conn.setRequestProperty("AccountKey", k.optString("lta"));
            if (host.equals("www.onemap.gov.sg") && url.contains("/routingsvc/")) conn.setRequestProperty("Authorization", onemapToken(c));
            if (body != null && !body.isEmpty() && !"GET".equals(method)) {
                conn.setRequestMethod(method == null || method.isEmpty() ? "POST" : method);
                conn.setDoOutput(true);
                if (conn.getRequestProperty("Content-Type") == null) conn.setRequestProperty("Content-Type", "application/json");
                try (OutputStream o = conn.getOutputStream()) { o.write(body.getBytes(StandardCharsets.UTF_8)); }
            }
            int code = conn.getResponseCode();
            InputStream in = code < 400 ? conn.getInputStream() : conn.getErrorStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            if (in != null) try (InputStream i = in) { byte[] b = new byte[8192]; for (int r; (r = i.read(b)) != -1; ) buf.write(b, 0, r); }
            return new String[]{Integer.toString(code), buf.toString("UTF-8")};
        } catch (Exception e) {
            return new String[]{"0", String.valueOf(e.getMessage())};
        }
    }

    private static String onemapToken(Context c) {
        SharedPreferences sp = p(c);
        if (System.currentTimeMillis() < sp.getLong("onemap_until", 0)) return sp.getString("onemap_token", "");
        try {
            JSONObject k = keys(c), body = new JSONObject();
            if (k.optString("onemap_email").isEmpty()) return "";
            body.put("email", k.optString("onemap_email"));
            body.put("password", k.optString("onemap_password"));
            HttpURLConnection conn = (HttpURLConnection) new URL("https://www.onemap.gov.sg/api/auth/post/getToken").openConnection();
            conn.setRequestMethod("POST"); conn.setDoOutput(true); conn.setConnectTimeout(10000); conn.setReadTimeout(15000);
            conn.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = conn.getOutputStream()) { o.write(body.toString().getBytes(StandardCharsets.UTF_8)); }
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            try (InputStream i = conn.getInputStream()) { byte[] b = new byte[4096]; for (int r; (r = i.read(b)) != -1; ) buf.write(b, 0, r); }
            String tok = new JSONObject(buf.toString("UTF-8")).optString("access_token");
            sp.edit().putString("onemap_token", tok).putLong("onemap_until", System.currentTimeMillis() + 60 * 60_000L * 60).apply();
            return tok;
        } catch (Exception e) { return ""; }
    }

    // ------------------------------------------------------------ reminders that ring on the phone by itself
    static String remind(Context c, String uid, long atMillis, String text, boolean backup) {
        if (atMillis < System.currentTimeMillis() - 60_000L) return "that time has passed";
        try {
            JSONObject all = new JSONObject(p(c).getString("alarms", "{}"));
            all.put(uid, new JSONObject().put("at", atMillis).put("text", text).put("backup", backup));
            p(c).edit().putString("alarms", all.toString()).apply();
        } catch (Exception ignored) {}
        set(c, uid, atMillis, text, backup);
        return "reminder set";
    }

    private static void set(Context c, String uid, long atMillis, String text, boolean backup) {
        AlarmManager am = c.getSystemService(AlarmManager.class);
        Intent i = new Intent(c, Ring.class).putExtra("uid", uid).putExtra("text", text).putExtra("backup", backup);
        PendingIntent pi = PendingIntent.getBroadcast(c, uid.hashCode(), i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        try {
            if (android.os.Build.VERSION.SDK_INT < 31 || am.canScheduleExactAlarms())
                am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, atMillis, pi);
            else am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, atMillis, pi);   // within a few minutes
        } catch (SecurityException e) {
            am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, atMillis, pi);
        }
    }

    static boolean exactAllowed(Context c) {
        return android.os.Build.VERSION.SDK_INT < 31 || c.getSystemService(AlarmManager.class).canScheduleExactAlarms();
    }

    private static void backupReminders(Context c, JSONArray rs) {
        if (rs == null) return;
        try {
            JSONObject all = new JSONObject(p(c).getString("alarms", "{}"));
            for (Iterator<String> it = all.keys(); it.hasNext(); ) {   // laptop reminders that were cancelled there
                String k = it.next();
                if (k.startsWith("laptop-") && all.getJSONObject(k).optBoolean("backup")) it.remove();
            }
            p(c).edit().putString("alarms", all.toString()).apply();
            for (int i = 0; i < rs.length(); i++) {
                JSONObject r = rs.getJSONObject(i);
                long at = java.time.OffsetDateTime.parse(r.getString("at")).toInstant().toEpochMilli();
                remind(c, "laptop-" + r.optInt("id"), at, r.optString("text"), true);
            }
        } catch (Exception ignored) {}
    }

    /** After a restart, put the phone's reminders back. */
    static void rescheduleAll(Context c) {
        try {
            JSONObject all = new JSONObject(p(c).getString("alarms", "{}"));
            for (Iterator<String> it = all.keys(); it.hasNext(); ) {
                String k = it.next(); JSONObject a = all.getJSONObject(k);
                if (a.optLong("at") > System.currentTimeMillis()) set(c, k, a.optLong("at"), a.optString("text"), a.optBoolean("backup"));
            }
        } catch (Exception ignored) {}
    }

    // ------------------------------------------------------------ shared by the solo page and the background brain
    static String location(Context c) {
        try {
            android.location.LocationManager lm = c.getSystemService(android.location.LocationManager.class);
            android.location.Location best = null;
            for (String pr : lm.getProviders(true)) {
                android.location.Location l = lm.getLastKnownLocation(pr);
                if (l != null && (best == null || l.getTime() > best.getTime())) best = l;
            }
            if (best == null) return "";
            return new JSONObject().put("lat", best.getLatitude()).put("lon", best.getLongitude()).put("accuracy", best.getAccuracy())
                    .put("speed", best.hasSpeed() ? best.getSpeed() : -1).put("age", (System.currentTimeMillis() - best.getTime()) / 1000).toString();
        } catch (Exception e) { return ""; }
    }

    /** Today's steps and the places the phone went (for the night review and "how was my day"). */
    static String day(Context c) {
        try {
            JSONObject o = new JSONObject();
            o.put("steps", JarvisLink.stepsToday);
            JSONArray pts = new JSONArray();
            synchronized (JarvisLink.TODAY) { for (double[] q : JarvisLink.TODAY) pts.put(new JSONArray().put(q[0]).put(q[1]).put(q[2])); }
            o.put("points", pts);
            return o.toString();
        } catch (Exception e) { return "{}"; }
    }

    /** Notifications from the last day (never bank apps, never codes), for "what did I miss?". */
    static boolean secret(String app, String title, String text) {
        return Net.isFinance(app) || Net.isFinance(title) || Net.isFinance(text)
                || text.matches("(?is).*\\b(otp|one[- ]time|verification|passcode|security code|pin)\\b.*")
                || text.matches("(?s).*\\b\\d{4,8}\\b.*(code|otp).*");
    }

    static void noteSeen(Context c, String app, String title, String text) {
        if (secret(app, title, text)) return;
        try {
            try { app = String.valueOf(c.getPackageManager().getApplicationLabel(c.getPackageManager().getApplicationInfo(app, 0))); } catch (Exception ignored) {}
            synchronized (Solo.class) {
                JSONArray a = new JSONArray(p(c).getString("notes", "[]")), keep = new JSONArray();
                long cut = System.currentTimeMillis() - 24 * 3600_000L;
                for (int i = 0; i < a.length(); i++) if (a.getJSONObject(i).optLong("t") > cut) keep.put(a.get(i));
                keep.put(new JSONObject().put("t", System.currentTimeMillis()).put("app", app).put("title", title).put("text", text.length() > 300 ? text.substring(0, 300) : text));
                while (keep.length() > 300) keep.remove(0);
                p(c).edit().putString("notes", keep.toString()).apply();
            }
        } catch (Exception ignored) {}
    }

    /** The day's notifications plus whatever is still in the shade (caught even if it arrived before JARVIS started). */
    static String notes(Context c) {
        try {
            JSONArray a = new JSONArray(p(c).getString("notes", "[]"));
            java.util.HashSet<String> have = new java.util.HashSet<>();
            for (int i = 0; i < a.length(); i++) { JSONObject o = a.getJSONObject(i); have.add(o.optString("app") + o.optString("title") + o.optString("text")); }
            JSONArray now = SmartReplies.active(c);
            for (int i = 0; i < now.length(); i++) { JSONObject o = now.getJSONObject(i); if (have.add(o.optString("app") + o.optString("title") + o.optString("text"))) a.put(o); }
            return a.toString();
        } catch (Exception e) { return p(c).getString("notes", "[]"); }
    }

    /** Is Notification access on for JARVIS? Without it JARVIS can't see Gmail or anything else. */
    static boolean notesAccess(Context c) {
        String on = android.provider.Settings.Secure.getString(c.getContentResolver(), "enabled_notification_listeners");
        return on != null && on.contains(c.getPackageName());
    }

    /** Phone powers: the same ones the laptop can ask for. Bank and finance apps stay off limits (Powers checks). */
    static String power(Context ctx, String kind, String argsJson) {
        try {
            JSONObject c = new JSONObject(argsJson == null || argsJson.isEmpty() ? "{}" : argsJson);
            switch (kind) {
                case "call": return Powers.call(ctx, c.optString("number"), c.optString("name"));
                case "contacts": return Powers.contacts(ctx, c.optString("name"));
                case "alarm": return Powers.alarm(ctx, c.optInt("hour"), c.optInt("minute"), c.optString("label"));
                case "timer": return Powers.timer(ctx, c.optInt("seconds", 60), c.optString("label"));
                case "torch": return Powers.torch(ctx, c.optBoolean("on", true));
                case "volume": return Powers.volume(ctx, c.optInt("level", 50));
                case "media": return Powers.media(ctx, c.optString("action", "toggle"));
                case "play": return Powers.play(ctx, c.optString("query"), c.optString("app"));
                case "app": return Powers.openApp(ctx, c.optString("name"));
                case "link": return Powers.link(ctx, c.optString("url"));
                case "camera": return Powers.camera(ctx, c.optBoolean("video"));
                case "email": return Powers.email(ctx, c.optString("to"), c.optString("subject"), c.optString("body"));
                case "screentime": return Powers.screenTime(ctx);
                default: return "unknown";
            }
        } catch (Exception e) { return "couldn't: " + e.getMessage(); }
    }

    /** A reminder is due. A backup copy of a laptop reminder rings only if the laptop is out of reach. */
    public static class Ring extends BroadcastReceiver {
        @Override
        public void onReceive(Context c, Intent i) {
            String uid = i.getStringExtra("uid"), text = i.getStringExtra("text");
            try {
                JSONObject all = new JSONObject(p(c).getString("alarms", "{}"));
                all.remove(uid);
                p(c).edit().putString("alarms", all.toString()).apply();
            } catch (Exception ignored) {}
            if (i.getBooleanExtra("backup", false) && System.currentTimeMillis() - lastOk < 10 * 60_000L) return;
            JarvisLink.channels(c);
            Intent open = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent pi = PendingIntent.getActivity(c, uid == null ? 0 : uid.hashCode(), open,
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification n = new Notification.Builder(c, JarvisLink.URGENT)
                    .setSmallIcon(android.R.drawable.ic_lock_idle_alarm)
                    .setContentTitle("⏰ JARVIS reminder").setContentText(text)
                    .setStyle(new Notification.BigTextStyle().bigText(text))
                    .setColor(Color.parseColor("#FFD23F")).setContentIntent(pi).setAutoCancel(true).build();
            c.getSystemService(NotificationManager.class).notify(uid == null ? 77 : uid.hashCode(), n);
        }
    }
}
