package os.jarvis.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** After the phone restarts, bring the JARVIS link (and the floating orb, if it was on) back. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent i) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(i.getAction())) return;
        JarvisLink.start(c);
        Solo.rescheduleAll(c);   // reminders set on the phone ring after a restart too
        if (c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getBoolean("orb_on", false) && FloatingOrb.canShow(c)) {
            try { c.startForegroundService(new Intent(c, FloatingOrb.class)); } catch (Exception ignored) {}
        }
    }
}
