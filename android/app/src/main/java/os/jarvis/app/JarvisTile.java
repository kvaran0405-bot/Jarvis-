package os.jarvis.app;

import android.app.PendingIntent;
import android.content.Intent;
import android.os.Build;
import android.service.quicksettings.Tile;
import android.service.quicksettings.TileService;

/** "JARVIS" button in the swipe-down quick settings: tap it and JARVIS listens. */
public class JarvisTile extends TileService {
    @Override
    public void onStartListening() {
        Tile t = getQsTile();
        if (t != null) { t.setState(Tile.STATE_ACTIVE); t.setLabel("JARVIS"); t.updateTile(); }
    }

    @Override
    public void onClick() {
        Intent i = new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP)
                .putExtra("jarvis_action", "talk");
        if (Build.VERSION.SDK_INT >= 34) {
            startActivityAndCollapse(PendingIntent.getActivity(this, 9, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        } else {
            startActivityAndCollapse(i);
        }
    }
}
