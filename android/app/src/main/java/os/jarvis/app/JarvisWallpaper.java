package os.jarvis.app;

import android.content.SharedPreferences;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.os.Handler;
import android.os.Looper;
import android.service.wallpaper.WallpaperService;
import android.view.MotionEvent;
import android.view.SurfaceHolder;

import java.util.Random;

/**
 * The JARVIS live wallpaper (#26): the reactor core breathing on your home screen, with orbiting arcs, tick marks,
 * drifting particles and a ripple wherever you touch. It only animates while the home screen is showing, at a
 * battery-friendly frame rate, in the colour of your suit theme.
 */
public class JarvisWallpaper extends WallpaperService {
    @Override public Engine onCreateEngine() { return new Core(); }

    private class Core extends Engine {
        private final Handler h = new Handler(Looper.getMainLooper());
        private final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Random rnd = new Random(7);
        private final float[][] dust = new float[90][4];   // x, y, speed, size
        private boolean visible = false;
        private int w = 1, ht = 1, accent = Color.parseColor("#FFD23F");
        private float touchX = -1, touchY = -1; private long touchAt = 0;
        private final long t0 = System.currentTimeMillis();
        private final Runnable tick = this::draw;

        @Override public void onCreate(SurfaceHolder s) {
            super.onCreate(s); setTouchEventsEnabled(true);
            for (float[] d : dust) { d[0] = rnd.nextFloat(); d[1] = rnd.nextFloat(); d[2] = .0004f + rnd.nextFloat() * .0012f; d[3] = 1 + rnd.nextFloat() * 2.5f; }
        }
        @Override public void onSurfaceChanged(SurfaceHolder s, int f, int width, int height) { w = width; ht = height; draw(); }
        @Override public void onVisibilityChanged(boolean v) {
            visible = v;
            if (v) {
                SharedPreferences sp = getSharedPreferences("jarvis_solo", MODE_PRIVATE);
                try { String c = new org.json.JSONObject(sp.getString("pack", "{}")).optJSONObject("theme").optString("accent", ""); if (!c.isEmpty()) accent = Color.parseColor(c); }
                catch (Exception ignored) {}
                draw();
            } else h.removeCallbacks(tick);
        }
        @Override public void onSurfaceDestroyed(SurfaceHolder s) { visible = false; h.removeCallbacks(tick); super.onSurfaceDestroyed(s); }
        @Override public void onTouchEvent(MotionEvent e) {
            if (e.getAction() == MotionEvent.ACTION_DOWN) { touchX = e.getX(); touchY = e.getY(); touchAt = System.currentTimeMillis(); }
        }

        private int alpha(int c, int a) { return Color.argb(Math.max(0, Math.min(255, a)), Color.red(c), Color.green(c), Color.blue(c)); }

        private void draw() {
            SurfaceHolder s = getSurfaceHolder();
            Canvas c = null;
            try {
                c = s.lockCanvas();
                if (c == null) return;
                float t = (System.currentTimeMillis() - t0) / 1000f, cx = w / 2f, cy = ht * .42f, R = Math.min(w, ht) * .3f;
                float amp = .5f + .5f * (float) Math.sin(t * 1.6);
                p.setShader(new RadialGradient(cx, cy, Math.max(w, ht) * .8f, new int[]{Color.parseColor("#0B1620"), Color.parseColor("#03060A")}, null, Shader.TileMode.CLAMP));
                p.setStyle(Paint.Style.FILL); c.drawRect(0, 0, w, ht, p); p.setShader(null);
                // drifting dust
                for (float[] d : dust) { d[1] -= d[2]; if (d[1] < 0) { d[1] = 1; d[0] = rnd.nextFloat(); }
                    p.setColor(alpha(Color.parseColor("#5FD8FF"), 90)); c.drawCircle(d[0] * w, d[1] * ht, d[3], p); }
                // glow and heart
                p.setShader(new RadialGradient(cx, cy, R * (.55f + amp * .12f), new int[]{Color.WHITE, alpha(accent, 220), alpha(accent, 0)}, new float[]{0, .35f, 1}, Shader.TileMode.CLAMP));
                c.drawCircle(cx, cy, R * (.55f + amp * .12f), p); p.setShader(null);
                // orbiting arcs
                p.setStyle(Paint.Style.STROKE); p.setStrokeCap(Paint.Cap.ROUND);
                float[][] arcs = {{.62f, 7, 1.3f, 250, 255}, {.74f, 3, -.9f, 300, 170}, {.88f, 10, .55f, 200, 230}, {1.02f, 2.5f, -.35f, 130, 120}};
                for (float[] a : arcs) { p.setColor(alpha(accent, (int) a[4])); p.setStrokeWidth(a[1] * (w / 1080f) * 2);
                    float r = R * a[0]; c.drawArc(new RectF(cx - r, cy - r, cx + r, cy + r), (t * a[2] * 57.3f) % 360, a[3], false, p); }
                // tick marks
                p.setColor(Color.parseColor("#5FD8FF")); p.setStrokeWidth(5 * (w / 1080f) * 2);
                for (int i = 0; i < 12; i++) { double ang = i / 12.0 * Math.PI * 2 + t * .4; float r1 = R * .42f, r2 = R * .5f;
                    c.drawLine(cx + (float) Math.cos(ang) * r1, cy + (float) Math.sin(ang) * r1, cx + (float) Math.cos(ang) * r2, cy + (float) Math.sin(ang) * r2, p); }
                // ripple where you touched
                long since = System.currentTimeMillis() - touchAt;
                if (touchX >= 0 && since < 900) { float k = since / 900f; p.setColor(alpha(accent, (int) (220 * (1 - k)))); p.setStrokeWidth(4);
                    c.drawCircle(touchX, touchY, 20 + k * R, p); }
                p.setStyle(Paint.Style.FILL);
                // name plate
                p.setColor(alpha(accent, 200)); p.setTextAlign(Paint.Align.CENTER); p.setTextSize(Math.min(w, ht) * .045f); p.setLetterSpacing(.4f);
                p.setFakeBoldText(true); c.drawText("J.A.R.V.I.S", cx, cy + R * 1.35f, p); p.setFakeBoldText(false);
            } catch (Exception ignored) {
            } finally {
                if (c != null) try { s.unlockCanvasAndPost(c); } catch (Exception ignored) {}
            }
            h.removeCallbacks(tick);
            if (visible) h.postDelayed(tick, 33);   // ~30 fps, only while you can see it
        }
    }
}
