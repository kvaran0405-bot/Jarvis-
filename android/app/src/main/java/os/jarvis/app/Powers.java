package os.jarvis.app;

import android.Manifest;
import android.app.AppOpsManager;
import android.app.SearchManager;
import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.ContentUris;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.media.AudioManager;
import android.net.Uri;
import android.os.Build;
import android.os.Process;
import android.provider.AlarmClock;
import android.provider.ContactsContract;
import android.provider.MediaStore;
import android.provider.Settings;
import android.util.Base64;
import android.view.KeyEvent;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.List;
import java.util.Map;

/**
 * Things JARVIS can do on the phone when asked: call, contacts, alarms, timers, torch, volume, music, open apps and
 * links, camera, maps, email drafts, screen time and the latest photo. Bank and finance apps are always off limits,
 * and JARVIS never sends, buys or pays: it opens things ready for the owner to tap.
 */
final class Powers {
    private Powers() {}

    private static String start(Context c, Intent i, String ok) {
        try { c.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); return ok; }
        catch (Exception e) { return "couldn't: " + e.getMessage(); }
    }

    private static boolean has(Context c, String perm) {
        return c.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED;
    }

    // ------------------------------------------------------------ people
    static String contacts(Context c, String name) {
        if (!has(c, Manifest.permission.READ_CONTACTS)) return "needs contacts permission (open the JARVIS app and allow it)";
        JSONArray out = new JSONArray();
        String[] cols = {ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER};
        try (Cursor cur = c.getContentResolver().query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI, cols,
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " LIKE ?", new String[]{"%" + name + "%"},
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " ASC")) {
            while (cur != null && cur.moveToNext() && out.length() < 8) {
                JSONObject o = new JSONObject();
                o.put("name", cur.getString(0)); o.put("number", cur.getString(1)); out.put(o);
            }
        } catch (Exception e) { return "couldn't read contacts: " + e.getMessage(); }
        return out.toString();
    }

    static String call(Context c, String number, String name) {
        if ((number == null || number.isEmpty()) && name != null && !name.isEmpty()) {
            try {
                JSONArray found = new JSONArray(contacts(c, name));
                if (found.length() == 0) return "no contact called " + name;
                number = found.getJSONObject(0).getString("number");
                name = found.getJSONObject(0).getString("name");
            } catch (Exception e) { return contacts(c, name); }
        }
        if (number == null || number.isEmpty()) return "no number";
        Uri tel = Uri.parse("tel:" + Uri.encode(number));
        if (has(c, Manifest.permission.CALL_PHONE)) return start(c, new Intent(Intent.ACTION_CALL, tel), "calling " + (name.isEmpty() ? number : name));
        return start(c, new Intent(Intent.ACTION_DIAL, tel), "dialler open for " + (name.isEmpty() ? number : name) + " (tap call)");
    }

    static String email(Context c, String to, String subject, String body) {
        Intent i = new Intent(Intent.ACTION_SENDTO, Uri.parse("mailto:" + Uri.encode(to == null ? "" : to)));
        i.putExtra(Intent.EXTRA_SUBJECT, subject); i.putExtra(Intent.EXTRA_TEXT, body);
        return start(c, i, "email draft open, ready for you to send");
    }

    // ------------------------------------------------------------ time
    static String alarm(Context c, int hour, int minute, String label) {
        Intent i = new Intent(AlarmClock.ACTION_SET_ALARM).putExtra(AlarmClock.EXTRA_HOUR, hour)
                .putExtra(AlarmClock.EXTRA_MINUTES, minute).putExtra(AlarmClock.EXTRA_SKIP_UI, true);
        if (label != null && !label.isEmpty()) i.putExtra(AlarmClock.EXTRA_MESSAGE, label);
        return start(c, i, String.format("alarm set for %02d:%02d", hour, minute));
    }

    static String timer(Context c, int seconds, String label) {
        Intent i = new Intent(AlarmClock.ACTION_SET_TIMER).putExtra(AlarmClock.EXTRA_LENGTH, Math.max(1, seconds))
                .putExtra(AlarmClock.EXTRA_SKIP_UI, true);
        if (label != null && !label.isEmpty()) i.putExtra(AlarmClock.EXTRA_MESSAGE, label);
        return start(c, i, "timer started for " + seconds + " seconds");
    }

    // ------------------------------------------------------------ hardware
    static String torch(Context c, boolean on) {
        try {
            CameraManager cm = c.getSystemService(CameraManager.class);
            for (String id : cm.getCameraIdList()) {
                Boolean flash = cm.getCameraCharacteristics(id).get(CameraCharacteristics.FLASH_INFO_AVAILABLE);
                if (Boolean.TRUE.equals(flash)) { cm.setTorchMode(id, on); return on ? "torch on" : "torch off"; }
            }
            return "no torch on this phone";
        } catch (Exception e) { return "couldn't: " + e.getMessage(); }
    }

    static String volume(Context c, int level) {
        AudioManager am = c.getSystemService(AudioManager.class);
        int max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
        am.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(Math.max(0, Math.min(100, level)) * max / 100f), AudioManager.FLAG_SHOW_UI);
        return "media volume " + level + "%";
    }

    static String media(Context c, String action) {
        int key;
        switch (action) {
            case "play": key = KeyEvent.KEYCODE_MEDIA_PLAY; break;
            case "pause": key = KeyEvent.KEYCODE_MEDIA_PAUSE; break;
            case "next": key = KeyEvent.KEYCODE_MEDIA_NEXT; break;
            case "previous": case "prev": key = KeyEvent.KEYCODE_MEDIA_PREVIOUS; break;
            default: key = KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE;
        }
        AudioManager am = c.getSystemService(AudioManager.class);
        am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN, key));
        am.dispatchMediaKeyEvent(new KeyEvent(KeyEvent.ACTION_UP, key));
        return "music: " + action;
    }

    /** Play a song, artist or playlist: in a named app (Spotify, YouTube Music, YouTube) or the default music app. */
    static String play(Context c, String query, String app) {
        String a = app == null ? "" : app.toLowerCase();
        if (a.contains("youtube") && !a.contains("music"))
            return link(c, "https://www.youtube.com/results?search_query=" + Uri.encode(query));
        Intent i = new Intent(MediaStore.INTENT_ACTION_MEDIA_PLAY_FROM_SEARCH).putExtra(SearchManager.QUERY, query)
                .putExtra(MediaStore.EXTRA_MEDIA_FOCUS, "vnd.android.cursor.item/*");
        if (a.contains("spotify")) i.setPackage("com.spotify.music");
        else if (a.contains("youtube")) i.setPackage("com.google.android.apps.youtube.music");
        String r = start(c, i, "playing " + query);
        if (r.startsWith("couldn't") && a.contains("spotify")) return link(c, "spotify:search:" + Uri.encode(query));
        if (r.startsWith("couldn't")) return link(c, "https://music.youtube.com/search?q=" + Uri.encode(query));
        return r;
    }

    // ------------------------------------------------------------ apps and links
    static String openApp(Context c, String name) {
        if (name == null || name.isEmpty()) return "which app?";
        if (Net.isFinance(name)) return "bank and finance apps are off limits";
        PackageManager pm = c.getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        String want = name.toLowerCase().trim();
        ResolveInfo best = null;
        for (ResolveInfo ri : pm.queryIntentActivities(main, 0)) {
            String label = String.valueOf(ri.loadLabel(pm)).toLowerCase(), pkg = ri.activityInfo.packageName.toLowerCase();
            if (Net.isFinance(pkg) || Net.isFinance(label)) continue;
            if (label.equals(want) || pkg.equals(want)) { best = ri; break; }
            if (best == null && (label.contains(want) || pkg.contains(want.replace(" ", "")))) best = ri;
        }
        if (best == null) return "no app called " + name;
        Intent launch = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
        return launch == null ? "can't open " + name : start(c, launch, "opened " + best.loadLabel(pm));
    }

    /** Open a web link; apps that own the link (YouTube, Shopee, Shein, Lazada, Maps...) open it themselves. */
    static String link(Context c, String url) {
        if (url == null || url.isEmpty()) return "no link";
        if (Net.isFinance(url)) return "bank and finance links are off limits";
        return start(c, new Intent(Intent.ACTION_VIEW, Uri.parse(url)), "opened " + url);
    }

    static String camera(Context c, boolean video) {
        return start(c, new Intent(video ? MediaStore.INTENT_ACTION_VIDEO_CAMERA : MediaStore.INTENT_ACTION_STILL_IMAGE_CAMERA),
                video ? "video camera open" : "camera open");
    }

    static String navigate(Context c, String to, String mode) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=" + Uri.encode(to) + "&mode=" + mode));
        i.setPackage("com.google.android.apps.maps");
        String r = start(c, i, "navigating to " + to);
        return r.startsWith("couldn't") ? link(c, "https://www.google.com/maps/dir/?api=1&destination=" + Uri.encode(to)) : r;
    }

    // ------------------------------------------------------------ screen time
    static boolean usageGranted(Context c) {
        AppOpsManager ops = c.getSystemService(AppOpsManager.class);
        int mode = Build.VERSION.SDK_INT >= 29
                ? ops.unsafeCheckOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.getPackageName())
                : ops.checkOpNoThrow(AppOpsManager.OPSTR_GET_USAGE_STATS, Process.myUid(), c.getPackageName());
        return mode == AppOpsManager.MODE_ALLOWED;
    }

    static String screenTime(Context c) {
        if (!usageGranted(c)) {
            start(c, new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS), "");
            return "needs usage access: I opened the setting on the phone (turn JARVIS on)";
        }
        Calendar day = Calendar.getInstance();
        day.set(Calendar.HOUR_OF_DAY, 0); day.set(Calendar.MINUTE, 0); day.set(Calendar.SECOND, 0);
        UsageStatsManager um = c.getSystemService(UsageStatsManager.class);
        Map<String, UsageStats> stats = um.queryAndAggregateUsageStats(day.getTimeInMillis(), System.currentTimeMillis());
        List<UsageStats> list = new ArrayList<>(stats.values());
        list.sort((a, b) -> Long.compare(b.getTotalTimeInForeground(), a.getTotalTimeInForeground()));
        PackageManager pm = c.getPackageManager();
        JSONArray out = new JSONArray();
        long total = 0;
        try {
            for (UsageStats u : list) {
                long mins = u.getTotalTimeInForeground() / 60000;
                if (mins < 1 || u.getPackageName().equals(c.getPackageName())) continue;
                String label;
                try { ApplicationInfo ai = pm.getApplicationInfo(u.getPackageName(), 0); label = String.valueOf(pm.getApplicationLabel(ai)); }
                catch (Exception e) { label = u.getPackageName(); }
                if (label.toLowerCase().contains("launcher") || label.toLowerCase().contains("system ui")) continue;
                total += mins;
                if (out.length() < 10) { JSONObject o = new JSONObject(); o.put("app", label); o.put("minutes", mins); out.put(o); }
            }
            JSONObject r = new JSONObject(); r.put("total_minutes", total); r.put("apps", out);
            return r.toString();
        } catch (Exception e) { return "couldn't: " + e.getMessage(); }
    }

    // ------------------------------------------------------------ photo sorter: new photos -> laptop albums
    static String uploadPhotos(Context c, long sinceSec, int limit) {
        String perm = Build.VERSION.SDK_INT >= 33 ? "android.permission.READ_MEDIA_IMAGES" : Manifest.permission.READ_EXTERNAL_STORAGE;
        if (!has(c, perm)) return "needs photos permission";
        String[] cols = {MediaStore.Images.Media._ID, MediaStore.Images.Media.DISPLAY_NAME, MediaStore.Images.Media.DATE_ADDED};
        int sent = 0;
        try (Cursor cur = c.getContentResolver().query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cols,
                MediaStore.Images.Media.DATE_ADDED + " > ?", new String[]{String.valueOf(sinceSec)},
                MediaStore.Images.Media.DATE_ADDED + " ASC")) {
            while (cur != null && cur.moveToNext() && sent < limit) {
                String name = cur.getString(1);
                long added = cur.getLong(2);
                if (name == null || Net.isFinance(name)) continue;
                Uri uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cur.getLong(0));
                String data = jpeg(c, uri, 1280);
                if (data == null) continue;
                JSONObject body = new JSONObject();
                body.put("name", name); body.put("image", data); body.put("sort", true); body.put("taken", added);
                Net.call(c, "/api/phone/photo", body.toString(), 30000);
                sent++;
            }
        } catch (Exception e) { return "sent " + sent + ", then: " + e.getMessage(); }
        return "sent " + sent;
    }

    private static String jpeg(Context c, Uri uri, int max) {
        try {
            Bitmap bmp;
            try (InputStream in = c.getContentResolver().openInputStream(uri)) { bmp = BitmapFactory.decodeStream(in); }
            if (bmp == null) return null;
            float scale = Math.min(1f, (float) max / Math.max(bmp.getWidth(), bmp.getHeight()));
            if (scale < 1f) bmp = Bitmap.createScaledBitmap(bmp, Math.round(bmp.getWidth() * scale), Math.round(bmp.getHeight() * scale), true);
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            bmp.compress(Bitmap.CompressFormat.JPEG, 80, out);
            return "data:image/jpeg;base64," + Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP);
        } catch (Exception e) { return null; }
    }

    // ------------------------------------------------------------ latest photo -> laptop
    static String latestPhoto(Context c) {
        String perm = Build.VERSION.SDK_INT >= 33 ? "android.permission.READ_MEDIA_IMAGES" : Manifest.permission.READ_EXTERNAL_STORAGE;
        if (!has(c, perm)) return "needs photos permission (open the JARVIS app and allow it)";
        String[] cols = {MediaStore.Images.Media._ID, MediaStore.Images.Media.DISPLAY_NAME};
        try (Cursor cur = c.getContentResolver().query(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cols, null, null,
                MediaStore.Images.Media.DATE_ADDED + " DESC")) {
            if (cur == null || !cur.moveToFirst()) return "no photos";
            Uri uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, cur.getLong(0));
            String name = cur.getString(1);
            if (Net.isFinance(name)) return "that looks private, so I left it";
            Bitmap bmp;
            try (InputStream in = c.getContentResolver().openInputStream(uri)) { bmp = BitmapFactory.decodeStream(in); }
            if (bmp == null) return "couldn't read the photo";
            float scale = Math.min(1f, 1280f / Math.max(bmp.getWidth(), bmp.getHeight()));
            if (scale < 1f) bmp = Bitmap.createScaledBitmap(bmp, Math.round(bmp.getWidth() * scale), Math.round(bmp.getHeight() * scale), true);
            ByteArrayOutputStream jpg = new ByteArrayOutputStream();
            bmp.compress(Bitmap.CompressFormat.JPEG, 80, jpg);
            JSONObject body = new JSONObject();
            body.put("name", name);
            body.put("image", "data:image/jpeg;base64," + Base64.encodeToString(jpg.toByteArray(), Base64.NO_WRAP));
            return new JSONObject(Net.call(c, "/api/phone/photo", body.toString(), 30000)).optString("path", "uploaded");
        } catch (Exception e) { return "couldn't: " + e.getMessage(); }
    }
}
