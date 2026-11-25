package os.jarvis.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * New e-mail or WhatsApp message? JARVIS tells you straight away, without being asked: a short spoken summary that
 * says what matters and what doesn't ("Important: your interview with Grab moved to 3pm. Also two promos, nothing
 * urgent."), plus the same summary as a notification. Messages that arrive together are summed up together.
 * Quiet when the phone is on silent or vibrate, during calls, and at night (11pm to 7am): then it's notification only.
 * Bank apps and one-time codes never get here (Solo.secret). Say "stop announcing" / "announce messages" to toggle.
 */
final class Announcer {
    private Announcer() {}

    static final Set<String> EMAIL = new HashSet<>(Arrays.asList("com.google.android.gm", "com.microsoft.office.outlook",
            "com.yahoo.mobile.client.android.mail", "com.samsung.android.email.provider", "com.android.email", "com.coloros.email",
            "com.oplus.email", "ch.protonmail.android", "me.proton.android.mail", "com.google.android.gm.lite"));
    static final Set<String> CHAT = new HashSet<>(Arrays.asList("com.whatsapp", "com.whatsapp.w4b"));
    static final String CHANNEL = "jarvis_announce";

    private static final Handler ui = new Handler(Looper.getMainLooper());
    private static final List<JSONObject> batch = new ArrayList<>();
    private static final Map<String, Long> seen = new HashMap<>();
    private static TextToSpeech tts;
    private static boolean ttsReady = false;

    static boolean on(Context c) { return c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getBoolean("announce", true); }
    static void set(Context c, boolean v) { c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).edit().putBoolean("announce", v).apply(); }

    /** A notification arrived (already checked: not a bank app, not a code). */
    static void heard(Context c, String pkg, String title, String text) {
        boolean email = EMAIL.contains(pkg), chat = CHAT.contains(pkg);
        if ((!email && !chat) || !on(c)) return;
        if (title == null || text == null || text.trim().isEmpty()) return;
        String key = pkg + "|" + title + "|" + text;
        long now = System.currentTimeMillis();
        synchronized (batch) {
            Long t = seen.get(key);
            if (t != null && now - t < 30 * 60_000L) return;   // apps re-post the same notification
            seen.put(key, now);
            if (seen.size() > 300) seen.clear();
            try {
                String body = Solo.mask(text);
                batch.add(new JSONObject().put("kind", email ? "email" : "whatsapp").put("from", Solo.mask(title))
                        .put("text", body.length() > 600 ? body.substring(0, 600) : body));
            } catch (Exception ignored) { return; }
        }
        Context app = c.getApplicationContext();
        ui.removeCallbacksAndMessages(Announcer.class);
        ui.postAtTime(() -> flush(app), Announcer.class, android.os.SystemClock.uptimeMillis() + 3500);   // gather a burst
        warm(app);
    }

    private static void flush(Context c) {
        JSONArray items = new JSONArray();
        synchronized (batch) { for (JSONObject o : batch) items.put(o); batch.clear(); }
        if (items.length() == 0) return;
        new Thread(() -> {
            String say = null;
            try { say = SoloBrain.announce(c, items.toString()); } catch (Exception ignored) {}
            if (say == null || say.trim().isEmpty()) say = plain(items);
            final String line = say.trim();
            notifyText(c, line);
            if (quietNow(c)) return;
            ui.post(() -> speak(c, line));
        }).start();
    }

    /** Without the brain (no key / no internet): a plain line. */
    static String plain(JSONArray items) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < items.length() && i < 3; i++) {
            JSONObject o = items.optJSONObject(i);
            if (o == null) continue;
            String from = o.optString("from").split("[<(]")[0].trim(), text = o.optString("text");
            if (text.length() > 90) text = text.substring(0, 90);
            b.append(o.optString("kind").equals("email") ? "New email from " : "WhatsApp from ").append(from).append(": ").append(text).append(". ");
        }
        if (items.length() > 3) b.append("And ").append(items.length() - 3).append(" more.");
        return b.toString();
    }

    static boolean quietNow(Context c) {
        try {
            AudioManager am = c.getSystemService(AudioManager.class);
            if (am.getRingerMode() != AudioManager.RINGER_MODE_NORMAL) return true;   // silent or vibrate: notification only
            if (am.getMode() != AudioManager.MODE_NORMAL) return true;                // on a call
        } catch (Exception ignored) {}
        int h = Calendar.getInstance().get(Calendar.HOUR_OF_DAY);
        return h >= 23 || h < 7;
    }

    private static void warm(Context c) {
        if (tts != null) return;
        tts = new TextToSpeech(c, s -> ttsReady = s == TextToSpeech.SUCCESS);
    }

    private static void speak(Context c, String text) {
        warm(c);
        if (!ttsReady) { ui.postDelayed(() -> { if (ttsReady) speak(c, text); }, 1500); return; }
        AudioManager am = c.getSystemService(AudioManager.class);
        AudioAttributes aa = new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build();
        AudioFocusRequest focus = new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK).setAudioAttributes(aa).build();
        try { am.requestAudioFocus(focus); } catch (Exception ignored) {}   // music dips while JARVIS talks
        tts.setAudioAttributes(aa);
        android.speech.tts.Voice v = Voices.pick(tts, "JARVIS", true);
        if (v != null) tts.setVoice(v); else tts.setLanguage(Locale.UK);
        tts.setPitch(Voices.pitch("JARVIS"));
        tts.setSpeechRate(Voices.rate("JARVIS"));
        tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
            @Override public void onStart(String id) { }
            @Override public void onDone(String id) { try { am.abandonAudioFocusRequest(focus); } catch (Exception ignored) {} }
            @Override public void onError(String id) { onDone(id); }
        });
        Bundle p = new Bundle();
        p.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, 1f);
        tts.speak(text, TextToSpeech.QUEUE_ADD, p, "ann" + System.nanoTime());
    }

    private static void notifyText(Context c, String text) {
        try {
            NotificationManager nm = c.getSystemService(NotificationManager.class);
            if (nm.getNotificationChannel(CHANNEL) == null)
                nm.createNotificationChannel(new NotificationChannel(CHANNEL, "JARVIS tells you (emails, WhatsApp)", NotificationManager.IMPORTANCE_DEFAULT));
            PendingIntent open = PendingIntent.getActivity(c, 7350, new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            PendingIntent mute = PendingIntent.getBroadcast(c, 7351, new Intent(c, Mute.class), PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
            Notification n = new Notification.Builder(c, CHANNEL).setSmallIcon(android.R.drawable.ic_dialog_email)
                    .setContentTitle("JARVIS").setContentText(text).setStyle(new Notification.BigTextStyle().bigText(text))
                    .setContentIntent(open).setAutoCancel(true).setOnlyAlertOnce(true)
                    .addAction(new Notification.Action.Builder(null, "🔇 Stop announcing", mute).build()).build();
            nm.notify(7352, n);
        } catch (Exception ignored) {}
    }

    /** The "Stop announcing" button on the notification. */
    public static class Mute extends BroadcastReceiver {
        @Override public void onReceive(Context c, Intent i) {
            set(c, false);
            try { c.getSystemService(NotificationManager.class).cancel(7352); } catch (Exception ignored) {}
            android.widget.Toast.makeText(c, "JARVIS won't announce messages. Say \"announce messages\" to turn it back on.", android.widget.Toast.LENGTH_LONG).show();
        }
    }
}
