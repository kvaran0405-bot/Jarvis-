package os.jarvis.app;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/** Home-screen widget: the next thing on your day, what JARVIS handled, and a tap to talk. */
public class JarvisWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) {
        String next = c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getString("widget_next", "Tap to talk to JARVIS");
        int handled = c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getInt("widget_handled", 0);
        int waiting = c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getInt("widget_waiting", 0);
        for (int id : ids) m.updateAppWidget(id, views(c, next, handled, waiting));
        JarvisLink.start(c);
    }

    static RemoteViews views(Context c, String next, int handled, int waiting) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
        v.setTextViewText(R.id.w_next, next);
        v.setTextViewText(R.id.w_stats, handled + " handled · " + waiting + " waiting");
        Intent talk = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                .putExtra("jarvis_action", "talk");
        v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(c, 11, talk,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        return v;
    }

    static void update(Context c, String next, int handled, int waiting) {
        c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).edit().putString("widget_next", next)
                .putInt("widget_handled", handled).putInt("widget_waiting", waiting).apply();
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, JarvisWidget.class));
        for (int id : ids) m.updateAppWidget(id, views(c, next, handled, waiting));
    }
}
