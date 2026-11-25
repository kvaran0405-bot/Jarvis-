package os.jarvis.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * The app updates itself, so the owner never has to download and install it again by hand.
 * About once an hour (when the app opens or the background brain ticks) it checks the public GitHub release; if there's a newer build it
 * downloads it and installs it. After the first one, Android lets JARVIS update itself silently (Android 12+);
 * otherwise a single "Update" tap is all it takes.
 */
public final class AppUpdate {
    static final String LATEST = "https://api.github.com/repos/kvaran0405-bot/Jarvis-/releases/latest";
    static final String CHANNEL = "jarvis_update";
    private static volatile boolean busy = false;

    private AppUpdate() {}

    private static SharedPreferences p(Context c) { return c.getSharedPreferences("jarvis_update", Context.MODE_PRIVATE); }

    static int installed(Context c) {
        try {
            PackageInfo pi = c.getPackageManager().getPackageInfo(c.getPackageName(), 0);
            return (int) (Build.VERSION.SDK_INT >= 28 ? pi.getLongVersionCode() : pi.versionCode);
        } catch (Exception e) { return 0; }
    }

    /** Check now if `force`, otherwise at most once an hour. Runs in the background. */
    static void check(Context c, boolean force) {
        Context app = c.getApplicationContext();
        long now = System.currentTimeMillis();
        if (busy || (!force && now - p(app).getLong("checked", 0) < 3600_000L)) return;
        busy = true;
        p(app).edit().putLong("checked", now).apply();
        new Thread(() -> {
            try { run(app, force); } catch (Exception ignored) {} finally { busy = false; }
        }).start();
    }

    private static void run(Context c, boolean force) throws Exception {
        JSONObject rel = new JSONObject(get(LATEST));
        String tag = rel.optString("tag_name");               // jarvis-app-v123  (123 = the build number = versionCode)
        int latest = Integer.parseInt(tag.replaceAll("\\D+", "").isEmpty() ? "0" : tag.replaceAll("\\D+", ""));
        if (latest <= installed(c)) {
            if (force) say(c, "JARVIS is up to date", "You're on the newest app (v1.0." + installed(c) + ").", null);
            return;
        }
        if (!force && p(c).getInt("failed", 0) == latest) return;   // don't retry a build that wouldn't install
        String apk = null;
        JSONArray assets = rel.optJSONArray("assets");
        for (int i = 0; assets != null && i < assets.length(); i++) {
            JSONObject a = assets.getJSONObject(i);
            if (a.optString("name").endsWith(".apk")) { apk = a.optString("browser_download_url"); break; }
        }
        if (apk == null) return;
        install(c, apk, latest);
    }

    private static void install(Context c, String url, int version) throws Exception {
        PackageInstaller pi = c.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams sp = new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        sp.setAppPackageName(c.getPackageName());
        if (Build.VERSION.SDK_INT >= 31) sp.setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_NOT_REQUIRED);
        int id = pi.createSession(sp);
        try (PackageInstaller.Session s = pi.openSession(id)) {
            HttpURLConnection h = open(url);
            try (InputStream in = h.getInputStream(); OutputStream out = s.openWrite("jarvis.apk", 0, -1)) {
                byte[] buf = new byte[64 * 1024];
                for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
                s.fsync(out);
            } finally { h.disconnect(); }
            Intent done = new Intent(c, Result.class).putExtra("version", version);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
            s.commit(PendingIntent.getBroadcast(c, 7341, done, flags).getIntentSender());
        } catch (Exception e) {
            try { pi.abandonSession(id); } catch (Exception ignored) {}
            throw e;
        }
    }

    /** What Android says about the install. */
    public static class Result extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) {
            int status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
            int version = i.getIntExtra("version", 0);
            if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
                Intent confirm = i.getParcelableExtra(Intent.EXTRA_INTENT);
                if (confirm == null) return;
                confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                if (MainActivity.visible) { try { c.startActivity(confirm); return; } catch (Exception ignored) {} }
                say(c, "⬆ JARVIS update ready", "Tap to install the new app (v1.0." + version + "). One tap, no downloading.",
                        PendingIntent.getActivity(c, 7342, confirm, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
            } else if (status == PackageInstaller.STATUS_SUCCESS) {
                say(c, "✓ JARVIS updated", "Now on v1.0." + version + ".", null);
            } else if (status != PackageInstaller.STATUS_FAILURE_ABORTED) {
                p(c).edit().putInt("failed", version).apply();
                String why = String.valueOf(i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
                say(c, "JARVIS update didn't install", status == PackageInstaller.STATUS_FAILURE_CONFLICT
                        ? "This build was signed with a different key, so Android won't install it over the old one." : why, null);
            }
        }
    }

    /** After an update the app is restarted: bring the link and reminders back straight away. */
    public static class Replaced extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) {
            if (!Intent.ACTION_MY_PACKAGE_REPLACED.equals(i.getAction())) return;
            try { JarvisLink.start(c); } catch (Exception ignored) {}
            try { Solo.rescheduleAll(c); } catch (Exception ignored) {}
        }
    }

    static void say(Context c, String title, String text, PendingIntent tap) {
        try {
            NotificationManager nm = c.getSystemService(NotificationManager.class);
            if (nm.getNotificationChannel(CHANNEL) == null)
                nm.createNotificationChannel(new NotificationChannel(CHANNEL, "App updates", NotificationManager.IMPORTANCE_DEFAULT));
            Notification.Builder b = new Notification.Builder(c, CHANNEL).setSmallIcon(android.R.drawable.stat_sys_download_done)
                    .setContentTitle(title).setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text)).setAutoCancel(true);
            if (tap != null) b.setContentIntent(tap);
            nm.notify(7343, b.build());
        } catch (Exception ignored) {}
    }

    private static HttpURLConnection open(String url) throws Exception {
        HttpURLConnection h = (HttpURLConnection) new URL(url).openConnection();
        h.setConnectTimeout(20000); h.setReadTimeout(60000); h.setInstanceFollowRedirects(true);
        h.setRequestProperty("User-Agent", "jarvis-app");
        h.setRequestProperty("Accept", "application/vnd.github+json, application/octet-stream");
        return h;
    }

    private static String get(String url) throws Exception {
        HttpURLConnection h = open(url);
        try (InputStream in = h.getInputStream()) {
            ByteArrayOutputStream b = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            for (int n; (n = in.read(buf)) > 0; ) b.write(buf, 0, n);
            return b.toString(StandardCharsets.UTF_8.name());
        } finally { h.disconnect(); }
    }
}
