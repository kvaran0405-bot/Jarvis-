package os.jarvis.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.RemoteInput;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * WhatsApp smart replies. When a WhatsApp message arrives, its notification text goes to JARVIS on the laptop,
 * which suggests up to three replies. JARVIS shows them as a notification with "Send" buttons; tapping one answers
 * through WhatsApp's own notification reply (exactly like replying from the notification shade). Nothing is ever
 * sent without that tap, and group chats are ignored.
 */
public class SmartReplies extends NotificationListenerService {
    static final String CHANNEL = "jarvis_replies";
    static final Map<String, Notification.Action> REPLY_ACTIONS = new HashMap<>();
    private static final Map<String, Long> RECENT = new HashMap<>();

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        String pkg = sbn.getPackageName();
        if (pkg.equals(getPackageName()) || Net.isFinance(pkg) || sbn.isOngoing()) return;   // never bank apps
        Notification n = sbn.getNotification();
        if ((n.flags & Notification.FLAG_GROUP_SUMMARY) != 0) return;
        boolean messaging = java.util.Arrays.asList(MESSAGING).contains(pkg);
        if (!messaging) { forward(pkg, n); return; }
        Bundle ex = n.extras;
        if (ex.getBoolean(Notification.EXTRA_IS_GROUP_CONVERSATION, false)) return;
        CharSequence title = ex.getCharSequence(Notification.EXTRA_TITLE);
        CharSequence text = ex.getCharSequence(Notification.EXTRA_TEXT);
        if (title == null || text == null) return;
        String sender = title.toString(), body = text.toString();
        if (body.matches("^\\d+ new messages?$") || sender.equals("WhatsApp") || sender.toLowerCase().contains("jarvis")) return;

        Notification.Action reply = null;
        if (n.actions != null) {
            for (Notification.Action a : n.actions) {
                if (a.getRemoteInputs() != null && a.getRemoteInputs().length > 0) { reply = a; break; }
            }
        }
        if (reply == null) return;

        String key = sender + "\n" + body;
        long now = System.currentTimeMillis();
        synchronized (RECENT) {
            Long seen = RECENT.get(key);
            if (seen != null && now - seen < 10 * 60 * 1000) return;   // WhatsApp re-posts the same notification
            RECENT.put(key, now);
            if (RECENT.size() > 200) RECENT.clear();
        }
        final Notification.Action action = reply;
        new Thread(() -> suggest(pkg, sender, body, action)).start();
    }

    static final String[] MESSAGING = {"com.whatsapp", "com.whatsapp.w4b", "org.telegram.messenger", "com.instagram.android",
            "com.google.android.apps.messaging", "com.android.mms", "com.coloros.mms", "com.facebook.orca"};

    /** Any other app's notification: sent to the notification brain (no replies). Bank apps never get here. */
    private void forward(String pkg, Notification n) {
        CharSequence t = n.extras.getCharSequence(Notification.EXTRA_TITLE), x = n.extras.getCharSequence(Notification.EXTRA_TEXT);
        if (t == null || x == null || Net.isFinance(String.valueOf(t)) || Net.isFinance(String.valueOf(x))) return;
        Solo.noteSeen(this, pkg, String.valueOf(t), String.valueOf(x));   // for "what did I miss?", even with the laptop off
        String key = pkg + t + x;
        long now = System.currentTimeMillis();
        synchronized (RECENT) { Long seen = RECENT.get(key); if (seen != null && now - seen < 10 * 60 * 1000) return; RECENT.put(key, now); }
        new Thread(() -> {
            try {
                JSONObject req = new JSONObject();
                req.put("app", pkg); req.put("sender", String.valueOf(t)); req.put("text", String.valueOf(x)); req.put("group", false);
                Net.call(this, "/api/phone/notification", req.toString(), 20000);
            } catch (Exception ignored) {}
        }).start();
    }

    private void suggest(String pkg, String sender, String body, Notification.Action action) {
        SharedPreferences p = getSharedPreferences("jarvis", MODE_PRIVATE);
        String base = p.getString("url", null), token = p.getString("device_token", null);
        if (base == null || token == null) return;
        try {
            HttpURLConnection c = (HttpURLConnection) new URL(base + "/api/phone/notification").openConnection();
            c.setRequestMethod("POST");
            c.setConnectTimeout(8000);
            c.setReadTimeout(45000);
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "application/json");
            c.setRequestProperty("X-Jarvis-Device", token);
            JSONObject req = new JSONObject();
            req.put("app", pkg);
            req.put("sender", sender);
            req.put("text", body);
            try (OutputStream o = c.getOutputStream()) { o.write(req.toString().getBytes(StandardCharsets.UTF_8)); }
            if (c.getResponseCode() != 200) return;
            String out;
            try (InputStream in = c.getInputStream()) {
                java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
                byte[] chunk = new byte[4096];
                for (int r; (r = in.read(chunk)) != -1; ) buf.write(chunk, 0, r);
                out = buf.toString("UTF-8");
            }
            JSONArray replies = new JSONObject(out).optJSONArray("replies");
            if (replies == null || replies.length() == 0) return;
            show(sender, body, replies, action);
        } catch (Exception ignored) {
            // laptop asleep or offline: no suggestions this time
        }
    }

    private void show(String sender, String body, JSONArray replies, Notification.Action action) throws Exception {
        NotificationManager nm = getSystemService(NotificationManager.class);
        ensureChannel(this);
        int id = (sender + body).hashCode();
        String key = String.valueOf(id);
        synchronized (REPLY_ACTIONS) { REPLY_ACTIONS.put(key, action); }
        StringBuilder big = new StringBuilder(body).append("\n");
        Notification.Builder b = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.sym_action_chat)
                .setContentTitle("💬 " + sender + " · JARVIS suggests")
                .setContentText(body)
                .setAutoCancel(true);
        String[] letters = {"A", "B", "C"};
        for (int i = 0; i < replies.length() && i < 3; i++) {
            String r = replies.getString(i);
            big.append("\n").append(letters[i]).append(") ").append(r);
            Intent tap = new Intent(this, ReplyReceiver.class)
                    .putExtra("key", key).putExtra("text", r).putExtra("id", id);
            PendingIntent pi = PendingIntent.getBroadcast(this, id * 4 + i, tap,
                    PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            b.addAction(new Notification.Action.Builder(null, "Send " + letters[i], pi).build());
        }
        b.setStyle(new Notification.BigTextStyle().bigText(big.toString()));
        nm.notify(id, b.build());
    }

    static void ensureChannel(Context ctx) {
        NotificationManager nm = ctx.getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "WhatsApp smart replies",
                    NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("Replies JARVIS suggests for your WhatsApp messages");
            nm.createNotificationChannel(ch);
        }
    }

    /** "Send A/B/C" tapped: answer through WhatsApp's own notification reply. */
    public static class ReplyReceiver extends BroadcastReceiver {
        @Override
        public void onReceive(Context ctx, Intent intent) {
            String key = intent.getStringExtra("key"), text = intent.getStringExtra("text");
            Notification.Action action;
            synchronized (REPLY_ACTIONS) { action = REPLY_ACTIONS.remove(key); }
            ctx.getSystemService(NotificationManager.class).cancel(intent.getIntExtra("id", 0));
            if (action == null || text == null) {
                Toast.makeText(ctx, "That message expired - open WhatsApp to reply", Toast.LENGTH_SHORT).show();
                return;
            }
            try {
                RemoteInput[] inputs = action.getRemoteInputs();
                Bundle results = new Bundle();
                for (RemoteInput ri : inputs) results.putCharSequence(ri.getResultKey(), text);
                Intent fill = new Intent();
                RemoteInput.addResultsToIntent(inputs, fill, results);
                action.actionIntent.send(ctx, 0, fill);
                Toast.makeText(ctx, "Sent: " + text, Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                Toast.makeText(ctx, "Couldn't send - open WhatsApp to reply", Toast.LENGTH_SHORT).show();
            }
        }
    }
}
