package os.jarvis.app;

import android.Manifest;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.appwidget.AppWidgetManager;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.graphics.Color;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * The phone link: a quiet background service that checks in with the laptop (every few seconds while the screen is
 * on, about once a minute while it's off), reporting battery, screen and location, and carrying out what the laptop
 * asks: ring (find my phone), silent mode, clipboard, notifications, open a page, and approved autopilot steps.
 * Its notification is the live JARVIS card on the lock screen.
 */
public class JarvisLink extends Service implements LocationListener, android.hardware.SensorEventListener {
    static final String CHANNEL = "jarvis_link", ALERTS = "jarvis_alerts", URGENT = "jarvis_urgent";
    private volatile boolean running = true;
    private volatile Location lastLoc;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private MediaPlayer ringer;
    private long lastWidget = 0;

    static void start(Context c) {
        if (!Net.linked(c)) return;
        try { c.startForegroundService(new Intent(c, JarvisLink.class)); } catch (Exception ignored) {}
    }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        channels(this);
        Notification n = card("JARVIS is linked", "Your laptop and phone are connected.");
        boolean loc = checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        if (Build.VERSION.SDK_INT >= 34) {
            try {   // with location allowed, the link is also a location service so the explorer trail keeps going
                startForeground(8, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
                        | (loc ? ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION : 0));
            } catch (Exception e) {
                startForeground(8, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
            }
        }
        else startForeground(8, n);
        startLocation();
        startSteps();
        try {   // the first unlock of the day = the boss is up (the announcer stays quiet until then)
            registerReceiver(new android.content.BroadcastReceiver() {
                @Override public void onReceive(android.content.Context c, Intent i) { Announcer.unlocked(c); }
            }, new android.content.IntentFilter(Intent.ACTION_USER_PRESENT));
        } catch (Exception ignored) {}
        SoloBrain.schedule(this);   // wakes every ~10 min even with the screen off (Telegram, briefs, alerts when the laptop's away)
        new Thread(this::loop).start();
    }

    @Override public int onStartCommand(Intent i, int flags, int id) { return START_STICKY; }

    static void channels(Context c) {
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CHANNEL) == null)
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "JARVIS link", NotificationManager.IMPORTANCE_MIN));
        if (nm.getNotificationChannel(ALERTS) == null) {
            NotificationChannel a = new NotificationChannel(ALERTS, "JARVIS messages", NotificationManager.IMPORTANCE_HIGH);
            a.enableLights(true); a.setLightColor(Color.parseColor("#FFD23F"));
            nm.createNotificationChannel(a);
        }
        if (nm.getNotificationChannel(URGENT) == null) {
            NotificationChannel u = new NotificationChannel(URGENT, "JARVIS urgent", NotificationManager.IMPORTANCE_HIGH);
            u.enableVibration(true); u.setVibrationPattern(new long[]{0, 300, 150, 300, 150, 600});
            u.enableLights(true); u.setLightColor(Color.RED);
            nm.createNotificationChannel(u);
        }
    }

    private PendingIntent openIntent(String url, int req) {
        Intent i = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (url != null) i.putExtra("jarvis_url", url);
        return PendingIntent.getActivity(this, req, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private Notification card(String title, String text) {
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.presence_online)
                .setContentTitle(title).setContentText(text)
                .setColor(Color.parseColor("#FFD23F"))
                .setContentIntent(openIntent("/home.html", 1)).setOngoing(true).build();
    }

    // ------------------------------------------------------------ location
    private void startLocation() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED
                && checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) return;
        try {
            LocationManager lm = getSystemService(LocationManager.class);
            for (String p : new String[]{LocationManager.NETWORK_PROVIDER, LocationManager.GPS_PROVIDER}) {
                if (lm.isProviderEnabled(p)) {
                    Location l = lm.getLastKnownLocation(p);
                    if (l != null && (lastLoc == null || l.getTime() > lastLoc.getTime())) lastLoc = l;
                    lm.requestLocationUpdates(p, 30_000L, 40f, this, Looper.getMainLooper());
                }
            }
        } catch (SecurityException ignored) {}
    }

    // Location history: points are kept until the laptop has them, so nothing is lost when the phone is offline
    // (no signal, Tailscale off) or the laptop is asleep. At most ~2000 points (several days).
    private final java.util.ArrayDeque<double[]> pending = new java.util.ArrayDeque<>();
    private Location lastKept;

    @Override public void onLocationChanged(Location l) {
        lastLoc = l;
        boolean moved = lastKept == null || l.distanceTo(lastKept) > 60 || l.getTime() - lastKept.getTime() > 5 * 60_000L;
        if (!moved || l.getAccuracy() > 150) return;
        lastKept = l;
        String d = new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(new java.util.Date());
        synchronized (TODAY) {
            if (!d.equals(todayDay)) { TODAY.clear(); todayDay = d; }
            TODAY.addLast(new double[]{l.getTime() / 1000.0, l.getLatitude(), l.getLongitude()});
            while (TODAY.size() > 3000) TODAY.removeFirst();
        }
        synchronized (pending) {
            pending.addLast(new double[]{l.getTime() / 1000.0, l.getLatitude(), l.getLongitude(), l.getAccuracy(), l.hasSpeed() ? l.getSpeed() : -1});
            while (pending.size() > 2000) pending.removeFirst();
        }
    }
    // ------------------------------------------------------------ steps (the phone's own step counter)
    static volatile int stepsToday = -1;
    // today's trail (time, lat, lon), kept on the phone for the night review even when the laptop is off
    static final java.util.ArrayDeque<double[]> TODAY = new java.util.ArrayDeque<>();
    private static String todayDay = "";

    private void startSteps() {
        if (Build.VERSION.SDK_INT >= 29 && checkSelfPermission("android.permission.ACTIVITY_RECOGNITION") != PackageManager.PERMISSION_GRANTED) return;
        try {
            android.hardware.SensorManager sm = getSystemService(android.hardware.SensorManager.class);
            android.hardware.Sensor counter = sm.getDefaultSensor(android.hardware.Sensor.TYPE_STEP_COUNTER);
            if (counter != null) sm.registerListener(this, counter, android.hardware.SensorManager.SENSOR_DELAY_NORMAL);
        } catch (Exception ignored) {}
    }

    @Override public void onSensorChanged(android.hardware.SensorEvent e) {
        // The counter counts since the phone booted; keep a daily baseline (and survive reboots).
        float v = e.values[0];
        android.content.SharedPreferences p = getSharedPreferences("jarvis_steps", MODE_PRIVATE);
        String day = new java.text.SimpleDateFormat("yyyy-MM-dd", java.util.Locale.US).format(new java.util.Date());
        float base = p.getFloat("base", v), last = p.getFloat("last", v), acc = p.getFloat("acc", 0);
        if (!day.equals(p.getString("day", ""))) { base = v; acc = 0; last = v; }
        if (v < last) { acc += last - base; base = 0; }   // the phone restarted
        p.edit().putString("day", day).putFloat("base", base).putFloat("last", v).putFloat("acc", acc).apply();
        stepsToday = Math.round(acc + v - base);
    }

    @Override public void onAccuracyChanged(android.hardware.Sensor s, int a) {}

    @Override public void onProviderEnabled(String p) {}
    @Override public void onProviderDisabled(String p) {}
    @Override public void onStatusChanged(String p, int s, Bundle b) {}

    // ------------------------------------------------------------ check-in loop
    private void loop() {
        while (running) {
            boolean screenOn = getSystemService(PowerManager.class).isInteractive();
            try {
                JSONObject r = new JSONObject();
                BatteryManager bm = getSystemService(BatteryManager.class);
                r.put("battery", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY));
                r.put("charging", bm.isCharging());
                r.put("screen_on", screenOn);
                if (stepsToday >= 0) r.put("steps", stepsToday);
                Location l = lastLoc;
                if (l != null && System.currentTimeMillis() - l.getTime() < 15 * 60_000L) {
                    r.put("lat", l.getLatitude()); r.put("lon", l.getLongitude());
                    r.put("accuracy", l.getAccuracy()); if (l.hasSpeed()) r.put("speed", l.getSpeed());
                }
                int sentPts;
                synchronized (pending) {
                    JSONArray pts = new JSONArray();
                    int n = 0;
                    for (double[] p : pending) {
                        if (n++ >= 300) break;   // a big backlog goes up in chunks
                        pts.put(new JSONArray().put(p[0]).put(p[1]).put(p[2]).put(p[3]).put(p[4]));
                    }
                    sentPts = pts.length();
                    if (sentPts > 0) r.put("points", pts);
                }
                JSONArray cmds = new JSONObject(Net.call(this, "/api/phone/poll", r.toString(), 15000)).optJSONArray("commands");
                synchronized (pending) { for (int i = 0; i < sentPts && !pending.isEmpty(); i++) pending.removeFirst(); }
                if (cmds != null) for (int i = 0; i < cmds.length(); i++) run(cmds.getJSONObject(i));
                Solo.whileLinked(this);   // keep the phone's own JARVIS up to date, send back what it did alone
                if (System.currentTimeMillis() - lastWidget > 60_000L) { lastWidget = System.currentTimeMillis(); refreshCard(); }
            } catch (Exception ignored) {
                Solo.lastFail = System.currentTimeMillis();   // laptop asleep or offline: the phone's own JARVIS takes over
            }
            try { SoloBrain.tick(this, false); } catch (Exception ignored) {}   // at most every 2 minutes
            try { Thread.sleep(screenOn ? 5000 : 60000); } catch (InterruptedException e) { return; }
        }
    }

    private void refreshCard() {
        try {
            JSONObject w = new JSONObject(Net.call(this, "/api/widget", null, 10000));
            String next = w.optString("next", "");
            int waiting = w.optInt("waiting", 0);
            String text = next + (waiting > 0 ? " · " + waiting + " waiting for you" : "");
            getSystemService(NotificationManager.class).notify(8, card("JARVIS · " + w.optInt("handled", 0) + " handled this month", text));
            JarvisWidget.update(this, next, w.optInt("handled", 0), waiting);
        } catch (Exception ignored) {}
    }

    private void done(int id, String result) {
        try {
            JSONObject d = new JSONObject(); d.put("id", id); d.put("result", result);
            Net.call(this, "/api/phone/done", d.toString(), 10000);
        } catch (Exception ignored) {}
    }

    private void run(JSONObject c) {
        int id = c.optInt("id");
        String kind = c.optString("kind");
        switch (kind) {
            case "ring": ring(); done(id, "ringing"); break;
            case "dnd": done(id, silent(c.optBoolean("on", true))); break;
            case "clip":
                ui.post(() -> getSystemService(ClipboardManager.class).setPrimaryClip(ClipData.newPlainText("JARVIS", c.optString("text"))));
                done(id, "copied"); break;
            case "notify":
                notifyOwner(c.optString("title", "JARVIS"), c.optString("text"), c.optString("url", "/home.html"), c.optBoolean("urgent"));
                done(id, "shown"); break;
            case "open":
                Intent o = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                        .putExtra("jarvis_url", c.optString("url", "/home.html"));
                // Android only lets JARVIS pop up by itself while it's on screen or with "display over other apps";
                // otherwise a tap-to-open notification, so it never fails silently.
                if (MainActivity.visible || android.provider.Settings.canDrawOverlays(this)) {
                    try { startActivity(o); done(id, "opened"); break; } catch (Exception ignored) {}
                }
                notifyOwner(c.optString("title", "JARVIS"), c.optString("text", "Tap to open"), c.optString("url", "/home.html"), false);
                done(id, "notified");
                break;
            case "autopilot":
                JarvisAccessibility a = JarvisAccessibility.instance;
                if (a == null) {
                    notifyOwner("JARVIS autopilot is off", "Turn on JARVIS in Settings > Accessibility so I can tap for you.", "/home.html", false);
                    done(id, "autopilot not enabled");
                } else {
                    JSONArray steps = c.optJSONArray("steps");
                    new Thread(() -> done(id, a.runSteps(steps))).start();
                }
                break;
            case "address": {   // JARVIS moved (e.g. to the cloud): use the new address from now on
                String u = c.optString("url", "");
                if (u.startsWith("https://")) { getSharedPreferences("jarvis", MODE_PRIVATE).edit().putString("url", u).apply(); done(id, "switched"); }
                else done(id, "bad address");
                break;
            }
            case "call": done(id, Powers.call(this, c.optString("number"), c.optString("name"))); break;
            case "contacts": done(id, Powers.contacts(this, c.optString("name"))); break;
            case "alarm": done(id, Powers.alarm(this, c.optInt("hour"), c.optInt("minute"), c.optString("label"))); break;
            case "timer": done(id, Powers.timer(this, c.optInt("seconds", 60), c.optString("label"))); break;
            case "torch": done(id, Powers.torch(this, c.optBoolean("on", true))); break;
            case "volume": done(id, Powers.volume(this, c.optInt("level", 50))); break;
            case "media": done(id, Powers.media(this, c.optString("action", "toggle"))); break;
            case "play": done(id, Powers.play(this, c.optString("query"), c.optString("app"))); break;
            case "app": done(id, Powers.openApp(this, c.optString("name"))); break;
            case "link": done(id, Powers.link(this, c.optString("url"))); break;
            case "camera": done(id, Powers.camera(this, c.optBoolean("video"))); break;
            case "navigate": done(id, Powers.navigate(this, c.optString("to"), c.optString("mode", "d"))); break;
            case "email": done(id, Powers.email(this, c.optString("to"), c.optString("subject"), c.optString("body"))); break;
            case "screentime": done(id, Powers.screenTime(this)); break;
            case "screen": {
                JarvisAccessibility acc = JarvisAccessibility.instance;
                done(id, acc == null ? "autopilot is off (turn on JARVIS in Settings > Accessibility)" : acc.readScreen());
                break;
            }
            case "photo": new Thread(() -> done(id, Powers.latestPhoto(this))).start(); break;
            case "photos": new Thread(() -> done(id, Powers.uploadPhotos(this, c.optLong("since"), c.optInt("limit", 40)))).start(); break;
            default: done(id, "unknown command");
        }
    }

    private void notifyOwner(String title, String text, String url, boolean urgent) {
        int nid = (title + text).hashCode();
        Notification n = new Notification.Builder(this, urgent ? URGENT : ALERTS)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title).setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setColor(Color.parseColor(urgent ? "#FF3B3B" : "#FFD23F"))
                .setContentIntent(openIntent(url, nid)).setAutoCancel(true).build();
        getSystemService(NotificationManager.class).notify(nid, n);
    }

    private String silent(boolean on) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm.isNotificationPolicyAccessGranted()) {
            nm.setInterruptionFilter(on ? NotificationManager.INTERRUPTION_FILTER_PRIORITY : NotificationManager.INTERRUPTION_FILTER_ALL);
            return on ? "do not disturb on" : "do not disturb off";
        }
        AudioManager am = getSystemService(AudioManager.class);
        try { am.setRingerMode(on ? AudioManager.RINGER_MODE_VIBRATE : AudioManager.RINGER_MODE_NORMAL); }
        catch (SecurityException e) { return "needs Do Not Disturb access"; }
        return on ? "vibrate only" : "ringer on";
    }

    private void ring() {
        ui.post(() -> {
            try {
                if (ringer != null) { ringer.release(); ringer = null; }
                AudioManager am = getSystemService(AudioManager.class);
                am.setStreamVolume(AudioManager.STREAM_ALARM, am.getStreamMaxVolume(AudioManager.STREAM_ALARM), 0);
                Uri tone = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
                if (tone == null) tone = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE);
                ringer = new MediaPlayer();
                ringer.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
                ringer.setDataSource(this, tone);
                ringer.setLooping(true);
                ringer.prepare();
                ringer.start();
                ui.postDelayed(() -> { if (ringer != null) { ringer.stop(); ringer.release(); ringer = null; } }, 30_000);
                notifyOwner("📍 Here I am!", "JARVIS is ringing your phone. Tap to stop.", "/home.html", true);
            } catch (Exception ignored) {}
        });
    }

    static boolean usageGranted(Context c) { return Powers.usageGranted(c); }

    static void stopRinging() {
        // the ring stops by itself after 30 seconds; opening the app also silences it (see MainActivity.onResume)
    }

    void silenceRinger() {
        ui.post(() -> { if (ringer != null) { ringer.stop(); ringer.release(); ringer = null; } });
    }

    @Override
    public void onDestroy() {
        running = false;
        try { getSystemService(LocationManager.class).removeUpdates(this); } catch (Exception ignored) {}
        if (ringer != null) { ringer.release(); ringer = null; }
        super.onDestroy();
    }
}
