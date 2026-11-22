package os.jarvis.app;

import android.accessibilityservice.AccessibilityService;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/**
 * Phone autopilot: carries out steps the owner approved (open an app, tap a button by its text, type, scroll, back,
 * home). It only acts on steps sent by JARVIS after a yes, and refuses to touch bank or finance apps.
 */
public class JarvisAccessibility extends AccessibilityService {
    static volatile JarvisAccessibility instance;

    @Override protected void onServiceConnected() { instance = this; }
    @Override public void onAccessibilityEvent(AccessibilityEvent e) {}
    @Override public void onInterrupt() {}
    @Override public boolean onUnbind(Intent i) { instance = null; return super.onUnbind(i); }

    private String foreground() {
        AccessibilityNodeInfo r = getRootInActiveWindow();
        return r == null || r.getPackageName() == null ? "" : r.getPackageName().toString();
    }

    String runSteps(JSONArray steps) {
        if (steps == null) return "no steps";
        StringBuilder log = new StringBuilder();
        for (int i = 0; i < steps.length(); i++) {
            JSONObject s = steps.optJSONObject(i);
            if (s == null) continue;
            if (Net.isFinance(foreground())) return log + " stopped: finance app on screen";
            String a = s.optString("action"), r;
            try { r = step(a, s); } catch (Exception e) { r = "failed: " + e.getMessage(); }
            log.append(i + 1).append(". ").append(a).append(": ").append(r).append("; ");
            if (r.startsWith("failed") || r.startsWith("refused")) break;
            sleep(900);
        }
        return log.toString();
    }

    private String step(String a, JSONObject s) {
        switch (a) {
            case "open_app": return openApp(s.optString("app"));
            case "tap_text": return tap(s.optString("text"));
            case "type_text": return type(s.optString("text"));
            case "scroll_down": return scroll(true);
            case "scroll_up": return scroll(false);
            case "back": return performGlobalAction(GLOBAL_ACTION_BACK) ? "ok" : "failed";
            case "home": return performGlobalAction(GLOBAL_ACTION_HOME) ? "ok" : "failed";
            case "wait": sleep(Math.min(8000, Math.max(300, s.optInt("ms", 1500)))); return "ok";
            default: return "failed: unknown action";
        }
    }

    private String openApp(String name) {
        if (Net.isFinance(name)) return "refused: finance app";
        PackageManager pm = getPackageManager();
        Intent main = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> apps = pm.queryIntentActivities(main, 0);
        String want = name.toLowerCase().trim();
        ResolveInfo best = null;
        for (ResolveInfo ri : apps) {
            String label = String.valueOf(ri.loadLabel(pm)).toLowerCase(), pkg = ri.activityInfo.packageName.toLowerCase();
            if (label.equals(want) || pkg.equals(want)) { best = ri; break; }
            if (best == null && (label.contains(want) || pkg.contains(want))) best = ri;
        }
        if (best == null) return "failed: no app called " + name;
        if (Net.isFinance(best.activityInfo.packageName) || Net.isFinance(String.valueOf(best.loadLabel(pm))))
            return "refused: finance app";
        Intent launch = pm.getLaunchIntentForPackage(best.activityInfo.packageName);
        if (launch == null) return "failed: can't open " + name;
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        startActivity(launch);
        sleep(1800);
        return "opened " + best.loadLabel(pm);
    }

    private String tap(String text) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return "failed: nothing on screen";
        List<AccessibilityNodeInfo> hits = root.findAccessibilityNodeInfosByText(text);
        for (AccessibilityNodeInfo n : hits) {
            AccessibilityNodeInfo c = n;
            while (c != null && !c.isClickable()) c = c.getParent();
            if (c != null && c.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return "tapped " + text;
        }
        return "failed: no '" + text + "' to tap";
    }

    private String type(String text) {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null) return "failed: nothing on screen";
        AccessibilityNodeInfo f = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        if (f == null || !f.isEditable()) f = firstEditable(root);
        if (f == null) return "failed: no text box";
        Bundle args = new Bundle();
        args.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text);
        f.performAction(AccessibilityNodeInfo.ACTION_FOCUS);
        return f.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args) ? "typed" : "failed: couldn't type";
    }

    private AccessibilityNodeInfo firstEditable(AccessibilityNodeInfo n) {
        if (n == null) return null;
        if (n.isEditable()) return n;
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo r = firstEditable(n.getChild(i));
            if (r != null) return r;
        }
        return null;
    }

    private String scroll(boolean down) {
        AccessibilityNodeInfo n = firstScrollable(getRootInActiveWindow());
        if (n == null) return "failed: nothing to scroll";
        return n.performAction(down ? AccessibilityNodeInfo.ACTION_SCROLL_FORWARD : AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)
                ? "scrolled" : "failed: couldn't scroll";
    }

    private AccessibilityNodeInfo firstScrollable(AccessibilityNodeInfo n) {
        if (n == null) return null;
        if (n.isScrollable()) return n;
        for (int i = 0; i < n.getChildCount(); i++) {
            AccessibilityNodeInfo r = firstScrollable(n.getChild(i));
            if (r != null) return r;
        }
        return null;
    }

    private static void sleep(long ms) { try { Thread.sleep(ms); } catch (InterruptedException ignored) {} }
}
