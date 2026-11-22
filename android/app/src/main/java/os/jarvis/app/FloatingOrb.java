package os.jarvis.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.PixelFormat;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.provider.Settings;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * The floating JARVIS orb on the phone: a glowing reactor that stays on top of every app.
 * Tap: talk to JARVIS. Drag: move it. Long-press: quick actions. It pulses in the speaking agent's colour.
 * Runs as a foreground service, so its notification doubles as a live JARVIS card on the lock screen.
 */
public class FloatingOrb extends Service {
    static final String CHANNEL = "jarvis_orb";
    private WindowManager wm;
    private OrbView orb;
    private LinearLayout menu;
    private WindowManager.LayoutParams lp;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private volatile boolean running = true;
    private volatile int color = Color.parseColor("#FFD23F");
    private volatile boolean speaking = false, paused = false;

    public static boolean canShow(Context c) {
        return Build.VERSION.SDK_INT < 23 || Settings.canDrawOverlays(c);
    }

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        startAsForeground();
        if (!canShow(this)) { stopSelf(); return; }
        wm = (WindowManager) getSystemService(WINDOW_SERVICE);
        orb = new OrbView(this);
        int size = dp(64);
        lp = new WindowManager.LayoutParams(size, size,
                Build.VERSION.SDK_INT >= 26 ? WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY : WindowManager.LayoutParams.TYPE_PHONE,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT);
        lp.gravity = Gravity.TOP | Gravity.START;
        SharedPreferences p = getSharedPreferences("jarvis", MODE_PRIVATE);
        lp.x = p.getInt("orb_x", getResources().getDisplayMetrics().widthPixels - size - dp(12));
        lp.y = p.getInt("orb_y", dp(260));
        wm.addView(orb, lp);
        orb.setOnTouchListener(new Drag());
        new Thread(this::poll).start();
    }

    private void startAsForeground() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "JARVIS orb", NotificationManager.IMPORTANCE_MIN);
            ch.setDescription("Keeps the floating JARVIS orb on screen");
            nm.createNotificationChannel(ch);
        }
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        Notification n = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.presence_audio_online)
                .setContentTitle("JARVIS is here")
                .setContentText("Tap the orb to talk · long-press for more")
                .setContentIntent(open).setOngoing(true).build();
        if (Build.VERSION.SDK_INT >= 34) startForeground(7, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(7, n);
    }

    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    // ------------------------------------------------------------ touch: tap / drag / long-press
    private class Drag implements View.OnTouchListener {
        float sx, sy; int ox, oy; boolean moved; long down;
        final Runnable longPress = () -> { if (!moved) toggleMenu(); moved = true; };
        @Override public boolean onTouch(View v, MotionEvent e) {
            switch (e.getAction()) {
                case MotionEvent.ACTION_DOWN:
                    sx = e.getRawX(); sy = e.getRawY(); ox = lp.x; oy = lp.y; moved = false; down = System.currentTimeMillis();
                    ui.postDelayed(longPress, 550); return true;
                case MotionEvent.ACTION_MOVE:
                    if (Math.abs(e.getRawX() - sx) > dp(6) || Math.abs(e.getRawY() - sy) > dp(6)) {
                        if (!moved) ui.removeCallbacks(longPress);
                        moved = true; lp.x = ox + (int) (e.getRawX() - sx); lp.y = oy + (int) (e.getRawY() - sy);
                        wm.updateViewLayout(orb, lp);
                    }
                    return true;
                case MotionEvent.ACTION_UP:
                    ui.removeCallbacks(longPress);
                    if (moved) getSharedPreferences("jarvis", MODE_PRIVATE).edit().putInt("orb_x", lp.x).putInt("orb_y", lp.y).apply();
                    else if (System.currentTimeMillis() - down < 550) talk();
                    return true;
            }
            return false;
        }
    }

    private void talk() {
        closeMenu();
        Intent i = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                .putExtra("jarvis_action", "talk");
        startActivity(i);
    }

    private void toggleMenu() {
        if (menu != null) { closeMenu(); return; }
        menu = new LinearLayout(this);
        menu.setOrientation(LinearLayout.VERTICAL);
        menu.setBackgroundColor(Color.parseColor("#EE0A111A"));
        menu.setPadding(dp(6), dp(6), dp(6), dp(6));
        String[][] items = {{"📞  Call", "call"}, {"🛡  Focus 50 min", "focus"}, {"🔴  Record / stop", "record"},
                {"📋  Brief me", "brief"}, {"🖥  Open JARVIS", "open"}, {"🙈  Hide orb", "hide"}};
        for (String[] it : items) {
            TextView t = new TextView(this);
            t.setText(it[0]); t.setTextColor(Color.parseColor("#DCE7F2")); t.setTextSize(15);
            t.setPadding(dp(12), dp(10), dp(18), dp(10));
            final String act = it[1];
            t.setOnClickListener(v -> { closeMenu(); menuAction(act); });
            menu.addView(t);
        }
        WindowManager.LayoutParams mp = new WindowManager.LayoutParams(
                WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT, lp.type,
                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH,
                PixelFormat.TRANSLUCENT);
        mp.gravity = Gravity.TOP | Gravity.START;
        int w = getResources().getDisplayMetrics().widthPixels;
        mp.x = lp.x > w / 2 ? Math.max(0, lp.x - dp(190)) : lp.x + dp(70);
        mp.y = lp.y;
        menu.setOnTouchListener((v, e) -> { if (e.getAction() == MotionEvent.ACTION_OUTSIDE) closeMenu(); return false; });
        wm.addView(menu, mp);
    }

    private void closeMenu() { if (menu != null) { try { wm.removeView(menu); } catch (Exception ignored) {} menu = null; } }

    private void menuAction(String act) {
        if (act.equals("hide")) {
            getSharedPreferences("jarvis", MODE_PRIVATE).edit().putBoolean("orb_on", false).apply();
            stopSelf(); return;
        }
        if (act.equals("open") || act.equals("call")) {
            Intent i = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                    .putExtra("jarvis_action", act);
            startActivity(i); return;
        }
        new Thread(() -> {
            try {
                JSONObject req = new JSONObject(); req.put("action", act);
                JSONObject out = new JSONObject(http("/api/orb/action", req.toString()));
                String say = out.optString("say", "Done.");
                ui.post(() -> Toast.makeText(this, "JARVIS: " + say, Toast.LENGTH_LONG).show());
            } catch (Exception e) {
                ui.post(() -> Toast.makeText(this, "JARVIS can't reach your laptop", Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    // ------------------------------------------------------------ live state from the laptop
    private String http(String path, String body) throws Exception {
        SharedPreferences p = getSharedPreferences("jarvis", MODE_PRIVATE);
        String base = p.getString("url", null), token = p.getString("device_token", "");
        if (base == null) throw new Exception("no address");
        HttpURLConnection c = (HttpURLConnection) new URL(base + path).openConnection();
        c.setConnectTimeout(5000); c.setReadTimeout(30000);
        c.setRequestProperty("X-Jarvis-Device", token);
        if (body != null) {
            c.setRequestMethod("POST"); c.setDoOutput(true); c.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = c.getOutputStream()) { o.write(body.getBytes(StandardCharsets.UTF_8)); }
        }
        try (InputStream in = c.getInputStream()) {
            java.io.ByteArrayOutputStream buf = new java.io.ByteArrayOutputStream();
            byte[] b = new byte[4096];
            for (int r; (r = in.read(b)) != -1; ) buf.write(b, 0, r);
            return buf.toString("UTF-8");
        }
    }

    private void poll() {
        while (running) {
            try {
                JSONObject st = new JSONObject(http("/api/orb", null));
                color = Color.parseColor(st.optString("color", "#FFD23F"));
                speaking = st.optBoolean("speaking", false);
                paused = "paused".equals(st.optString("mode"));
            } catch (Exception e) {
                paused = true;   // laptop asleep or offline: the orb dims
            }
            try { Thread.sleep(speaking ? 700 : 2500); } catch (InterruptedException ignored) { return; }
        }
    }

    @Override
    public void onDestroy() {
        running = false;
        closeMenu();
        if (orb != null) try { wm.removeView(orb); } catch (Exception ignored) {}
        super.onDestroy();
    }

    // ------------------------------------------------------------ the reactor drawing
    private class OrbView extends View {
        final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        final long t0 = System.currentTimeMillis();
        OrbView(Context c) { super(c); }

        @Override protected void onDraw(Canvas c) {
            float t = (System.currentTimeMillis() - t0) / 1000f, w = getWidth(), m = w / 2f;
            int col = paused ? Color.parseColor("#56606E") : color;
            float amp = speaking ? (float) (0.55 + 0.45 * Math.sin(t * 9) * (0.6 + Math.random() * 0.4))
                                 : (float) ((0.5 + 0.5 * Math.sin(t * 2.4)) * 0.35);
            p.setShader(null); p.setStyle(Paint.Style.FILL); p.setColor(Color.parseColor("#E605080D"));
            c.drawCircle(m, m, m - 2, p);
            float core = w * (0.16f + amp * 0.08f);
            p.setShader(new RadialGradient(m, m, core * 2.2f, new int[]{Color.WHITE, col, Color.TRANSPARENT},
                    new float[]{0f, 0.35f, 1f}, Shader.TileMode.CLAMP));
            c.drawCircle(m, m, core * 2.2f, p);
            p.setShader(null); p.setStyle(Paint.Style.STROKE); p.setStrokeCap(Paint.Cap.ROUND);
            float spin = t * (speaking ? 220 : 70);
            float[][] rings = {{0.30f, 3, 1, 150, 255}, {0.38f, 2, -1.4f, 110, 170}, {0.45f, 2, 0.7f, 70, 120}};
            for (float[] r : rings) {
                p.setColor(col); p.setAlpha((int) r[4]); p.setStrokeWidth(r[1] * getResources().getDisplayMetrics().density * 0.8f);
                float rad = w * r[0];
                c.drawArc(new RectF(m - rad, m - rad, m + rad, m + rad), spin * r[2] % 360, r[3], false, p);
            }
            p.setAlpha(255);
            postInvalidateOnAnimation();
        }
    }
}
