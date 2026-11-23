package os.jarvis.app;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.PermissionRequest;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Locale;

/**
 * JARVIS for Android: the JARVIS command centre (served by your laptop, reached through Tailscale) in a native
 * shell that adds what Android's web view lacks: speech recognition (Android's own recogniser), text-to-speech,
 * microphone permission, and audio that plays without a tap.
 */
public class MainActivity extends Activity {
    private static final int REQ_MIC = 42;
    private static final int REQ_FILE = 43;
    private ValueCallback<Uri[]> fileCallback;
    private static final String PREFS = "jarvis";

    private WebView web;
    private SpeechRecognizer recognizer;
    private TextToSpeech tts;
    private boolean ttsReady = false;
    private PermissionRequest pendingWebPermission;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#07090D"));
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);   // JARVIS may speak without a tap
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        s.setUserAgentString(s.getUserAgentString() + " JarvisApp/1");

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, true);

        web.addJavascriptInterface(new Bridge(), "JarvisNative");

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri url = request.getUrl();
                String home = address();
                boolean inside = url.getScheme() != null && url.getScheme().startsWith("http")
                        && home != null && url.getHost() != null && home.contains(url.getHost());
                if (inside || "file".equals(url.getScheme())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, url)); } catch (Exception ignored) { }
                return true;   // links to other sites open in the normal browser
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) {
                    String why = error.getDescription() == null ? "" : error.getDescription().toString();
                    view.loadUrl("file:///android_asset/offline.html?why=" + Uri.encode(why));
                }
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onPermissionRequest(PermissionRequest request) {
                ui.post(() -> {
                    boolean wantsCam = java.util.Arrays.asList(request.getResources()).contains(PermissionRequest.RESOURCE_VIDEO_CAPTURE);
                    if (hasMic() && (!wantsCam || hasCamera())) request.grant(request.getResources());
                    else { pendingWebPermission = request; askMic(); }
                });
            }

            @Override   // <input type="file">: upload a lecture recording from the phone
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), REQ_FILE);
                } catch (Exception e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        if (!hasMic()) askMic(); else askPowersOnce();
        tts = new TextToSpeech(this, status -> {
            ttsReady = status == TextToSpeech.SUCCESS;
            if (ttsReady) tts.setLanguage(Locale.UK);
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else openHome();
        if (getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("orb_on", false) && FloatingOrb.canShow(this)) {
            startForegroundService(new Intent(this, FloatingOrb.class));
        }
        handleOrbIntent(getIntent());
        JarvisLink.start(this);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        handleOrbIntent(intent);
    }

    /** Taps on the orb, the tile, the widget and notifications arrive here, and things shared from other apps. */
    private void handleOrbIntent(Intent intent) {
        if (intent == null) return;
        String a0 = address();
        if (Intent.ACTION_SEND.equals(intent.getAction()) && a0 != null) { handleShare(intent); intent.setAction(null); return; }
        String url = intent.getStringExtra("jarvis_url");
        if (url != null && a0 != null) { intent.removeExtra("jarvis_url"); web.loadUrl(a0 + (url.startsWith("/") ? url : "/home.html")); return; }
        String act = intent.getStringExtra("jarvis_action");
        if (act == null) return;
        intent.removeExtra("jarvis_action");
        String a = address();
        if (a == null) return;
        if (act.equals("call")) { web.loadUrl(a + "/call.html"); return; }
        if (act.equals("open")) { web.loadUrl(a + "/home.html"); return; }
        if (act.equals("talk")) {
            String cur = web.getUrl();
            if (cur == null || !cur.startsWith(a)) web.loadUrl(a + "/home.html?talk=1");
            else ui.postDelayed(() -> web.evaluateJavascript("window.jarvisTalk ? jarvisTalk() : 0", null), 600);
        }
    }

    /** Something shared to JARVIS from another app: a link, some text or a photo. */
    private void handleShare(Intent intent) {
        String text = intent.getStringExtra(Intent.EXTRA_TEXT);
        Uri img = intent.getParcelableExtra(Intent.EXTRA_STREAM);
        web.loadUrl(address() + "/home.html");
        new Thread(() -> {
            String reply;
            try {
                JSONObject body = new JSONObject();
                if (text != null) body.put("text", text);
                if (img != null) {
                    android.graphics.Bitmap bm = android.graphics.BitmapFactory.decodeStream(getContentResolver().openInputStream(img));
                    if (bm != null) {
                        float k = Math.min(1f, 1280f / Math.max(bm.getWidth(), bm.getHeight()));
                        bm = android.graphics.Bitmap.createScaledBitmap(bm, Math.round(bm.getWidth() * k), Math.round(bm.getHeight() * k), true);
                        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
                        bm.compress(android.graphics.Bitmap.CompressFormat.JPEG, 82, out);
                        body.put("image", "data:image/jpeg;base64," + android.util.Base64.encodeToString(out.toByteArray(), android.util.Base64.NO_WRAP));
                    }
                }
                reply = new JSONObject(Net.call(this, "/api/phone/share", body.toString(), 120000)).optString("reply", "Done, Sir.");
            } catch (Exception e) {
                reply = "I couldn't reach your laptop to handle that, Sir.";
            }
            String q = JSONObject.quote(reply);
            ui.postDelayed(() -> web.evaluateJavascript("window.show && show('JARVIS'," + q + "); window.speak && speak('JARVIS'," + q + ")", null), 400);
        }).start();
    }

    // ------------------------------------------------------------------ navigation
    private String address() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getString("url", null);
    }

    private void openHome() {
        String a = address();
        if (a == null || a.isEmpty()) web.loadUrl("file:///android_asset/setup.html");
        else web.loadUrl(a + "/home.html");
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onActivityResult(int code, int result, Intent data) {
        super.onActivityResult(code, result, data);
        if (code != REQ_FILE || fileCallback == null) return;
        fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
        fileCallback = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onResume() {
        super.onResume();
        js("window.onNativeResume && window.onNativeResume()");   // the setup page re-checks what's allowed
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onDestroy() {
        if (recognizer != null) recognizer.destroy();
        if (tts != null) tts.shutdown();
        web.destroy();
        super.onDestroy();
    }

    // ------------------------------------------------------------------ microphone permission
    private boolean hasMic() {
        return checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    private boolean hasCamera() {
        return checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED;
    }

    private void askMic() {
        requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO, Manifest.permission.CAMERA}, REQ_MIC);
    }

    /** Ask once for everything JARVIS can use on the phone (each is optional; JARVIS works without any of them). */
    private void askPowersOnce() {
        java.util.List<String> want = new java.util.ArrayList<>();
        String[] perms = android.os.Build.VERSION.SDK_INT >= 33
                ? new String[]{"android.permission.POST_NOTIFICATIONS", Manifest.permission.READ_CONTACTS,
                               Manifest.permission.CALL_PHONE, "android.permission.READ_MEDIA_IMAGES"}
                : new String[]{Manifest.permission.READ_CONTACTS, Manifest.permission.CALL_PHONE,
                               Manifest.permission.READ_EXTERNAL_STORAGE};
        for (String p : perms) if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) want.add(p);
        if (!want.isEmpty() && !getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("asked_powers", false)) {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("asked_powers", true).apply();
            requestPermissions(want.toArray(new String[0]), 44);
        }
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
        if (code == REQ_MIC) ui.postDelayed(this::askPowersOnce, 400);
        if (code == 45) {   // location granted: restart the link so it starts reporting places
            stopService(new Intent(this, JarvisLink.class));
            JarvisLink.start(this);
            return;
        }
        if (code != REQ_MIC) return;
        if (pendingWebPermission != null) {
            if (hasMic()) pendingWebPermission.grant(pendingWebPermission.getResources());
            else pendingWebPermission.deny();
            pendingWebPermission = null;
        }
    }

    // ------------------------------------------------------------------ talking to the page
    private void js(String code) {
        ui.post(() -> web.evaluateJavascript(code, null));
    }

    private void emitSpeech(String type, String text, boolean isFinal) {
        js("window.__jarvisSR && window.__jarvisSR.emit(" + JSONObject.quote(type) + ","
                + JSONObject.quote(text == null ? "" : text) + "," + isFinal + ")");
    }

    private static String errorName(int code) {
        switch (code) {
            case SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS: return "not-allowed";
            case SpeechRecognizer.ERROR_NO_MATCH:
            case SpeechRecognizer.ERROR_SPEECH_TIMEOUT: return "no-speech";
            case SpeechRecognizer.ERROR_NETWORK:
            case SpeechRecognizer.ERROR_NETWORK_TIMEOUT:
            case SpeechRecognizer.ERROR_SERVER: return "network";
            case SpeechRecognizer.ERROR_AUDIO: return "audio-capture";
            case SpeechRecognizer.ERROR_RECOGNIZER_BUSY: return "busy";
            default: return "aborted";
        }
    }

    /** Methods the JARVIS pages call as window.JarvisNative.* (they run on a background thread). */
    private class Bridge {
        @JavascriptInterface
        public boolean canFloat() { return FloatingOrb.canShow(MainActivity.this); }

        @JavascriptInterface
        public boolean orbOn() { return getSharedPreferences(PREFS, MODE_PRIVATE).getBoolean("orb_on", false); }

        @JavascriptInterface
        public void showOrb(boolean on) {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putBoolean("orb_on", on).apply();
            ui.post(() -> {
                if (!on) { stopService(new Intent(MainActivity.this, FloatingOrb.class)); return; }
                if (!FloatingOrb.canShow(MainActivity.this)) {
                    startActivity(new Intent(android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:" + getPackageName())));
                    return;
                }
                startForegroundService(new Intent(MainActivity.this, FloatingOrb.class));
            });
        }

        @JavascriptInterface
        public void setDeviceToken(String token) {
            getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString("device_token", token).apply();
            JarvisLink.start(MainActivity.this);
        }

        @JavascriptInterface
        public boolean hasLocation() {
            return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface
        public void askLocation() {
            ui.post(() -> requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION}, 45));
        }

        @JavascriptInterface
        public boolean hasLocationAlways() {
            return android.os.Build.VERSION.SDK_INT < 29
                    || checkSelfPermission("android.permission.ACCESS_BACKGROUND_LOCATION") == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface
        public void askLocationAlways() {
            // Android shows its own page here: pick "Allow all the time"
            ui.post(() -> {
                if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(new String[]{Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION}, 45);
                } else if (android.os.Build.VERSION.SDK_INT >= 29) {
                    requestPermissions(new String[]{"android.permission.ACCESS_BACKGROUND_LOCATION"}, 45);
                }
            });
        }

        @JavascriptInterface
        public boolean hasAutopilot() { return JarvisAccessibility.instance != null; }

        @JavascriptInterface
        public void openAutopilotSettings() {
            ui.post(() -> startActivity(new Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        }

        @JavascriptInterface
        public boolean hasUsageAccess() { return JarvisLink.usageGranted(MainActivity.this); }

        @JavascriptInterface
        public void openUsageSettings() {
            ui.post(() -> startActivity(new Intent(android.provider.Settings.ACTION_USAGE_ACCESS_SETTINGS)));
        }

        @JavascriptInterface
        public void askPowers() {
            ui.post(() -> requestPermissions(new String[]{Manifest.permission.READ_CONTACTS, Manifest.permission.CALL_PHONE,
                    android.os.Build.VERSION.SDK_INT >= 33 ? "android.permission.READ_MEDIA_IMAGES"
                            : Manifest.permission.READ_EXTERNAL_STORAGE}, 46));
        }

        @JavascriptInterface
        public boolean hasDndAccess() {
            return getSystemService(android.app.NotificationManager.class).isNotificationPolicyAccessGranted();
        }

        @JavascriptInterface
        public void openDndSettings() {
            ui.post(() -> startActivity(new Intent(android.provider.Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS)));
        }

        // ---- one-tap setup page (/access.html): check and ask for everything
        @JavascriptInterface
        public boolean hasMicCam() { return hasMic() && hasCamera(); }

        @JavascriptInterface
        public void askMicCam() { ui.post(MainActivity.this::askMic); }

        @JavascriptInterface
        public boolean hasPowers() {
            String photos = android.os.Build.VERSION.SDK_INT >= 33 ? "android.permission.READ_MEDIA_IMAGES" : Manifest.permission.READ_EXTERNAL_STORAGE;
            for (String p : new String[]{Manifest.permission.READ_CONTACTS, Manifest.permission.CALL_PHONE, photos})
                if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) return false;
            return true;
        }

        @JavascriptInterface
        public boolean hasNotifyPermission() {
            return android.os.Build.VERSION.SDK_INT < 33
                    || checkSelfPermission("android.permission.POST_NOTIFICATIONS") == PackageManager.PERMISSION_GRANTED;
        }

        @JavascriptInterface
        public void askNotifyPermission() {
            if (android.os.Build.VERSION.SDK_INT >= 33)
                ui.post(() -> requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"}, 47));
        }

        @JavascriptInterface
        public boolean hasBatteryFree() {
            return getSystemService(android.os.PowerManager.class).isIgnoringBatteryOptimizations(getPackageName());
        }

        @JavascriptInterface
        public void askBatteryFree() {
            ui.post(() -> {
                try {
                    startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                            Uri.parse("package:" + getPackageName())));
                } catch (Exception e) {
                    startActivity(new Intent(android.provider.Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                }
            });
        }

        @JavascriptInterface
        public void openAppSettings() {
            ui.post(() -> startActivity(new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:" + getPackageName()))));
        }

        @JavascriptInterface
        public int appVersion() {
            try { return (int) getPackageManager().getPackageInfo(getPackageName(), 0).getLongVersionCode(); }
            catch (Exception e) { return 0; }
        }

        @JavascriptInterface
        public boolean hasNotificationAccess() {
            String on = android.provider.Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
            return on != null && on.contains(getPackageName());
        }

        @JavascriptInterface
        public void openNotificationAccess() {
            ui.post(() -> startActivity(new Intent("android.settings.ACTION_NOTIFICATION_LISTENER_SETTINGS")));
        }

        @JavascriptInterface
        public boolean speechAvailable() {
            return SpeechRecognizer.isRecognitionAvailable(MainActivity.this);
        }

        @JavascriptInterface
        public void listen(String lang, boolean partial) {
            ui.post(() -> {
                if (!hasMic()) { askMic(); emitSpeech("error", "not-allowed", true); emitSpeech("end", "", true); return; }
                if (recognizer == null) {
                    recognizer = SpeechRecognizer.createSpeechRecognizer(MainActivity.this);
                    recognizer.setRecognitionListener(new RecognitionListener() {
                        @Override public void onReadyForSpeech(Bundle b) { emitSpeech("start", "", false); }
                        @Override public void onBeginningOfSpeech() { }
                        @Override public void onRmsChanged(float v) { }
                        @Override public void onBufferReceived(byte[] bytes) { }
                        @Override public void onEndOfSpeech() { }
                        @Override public void onEvent(int t, Bundle b) { }

                        @Override public void onPartialResults(Bundle b) {
                            ArrayList<String> r = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                            if (r != null && !r.isEmpty() && !r.get(0).isEmpty()) emitSpeech("result", r.get(0), false);
                        }

                        @Override public void onResults(Bundle b) {
                            ArrayList<String> r = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                            if (r != null && !r.isEmpty()) emitSpeech("result", bestGuess(r), true);
                            else emitSpeech("error", "no-match", true);
                            emitSpeech("end", "", true);
                        }

                        @Override public void onError(int error) {
                            emitSpeech("error", errorName(error), true);
                            emitSpeech("end", "", true);
                        }
                    });
                }
                Intent i = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
                i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
                // Singapore English understands local accents and names much better than American English
                String use = lang == null || lang.isEmpty() || lang.equals("en-US") ? "en-SG" : lang;
                i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, use);
                i.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, use);
                i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, partial);
                i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5);   // several guesses: pick the one that fits JARVIS
                // don't cut the owner off at a short pause
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1800L);
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1500L);
                i.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1200L);
                i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getPackageName());
                try { recognizer.startListening(i); }
                catch (Exception e) { emitSpeech("error", "aborted", true); emitSpeech("end", "", true); }
            });
        }

        /** Of the recogniser's guesses, prefer one that names JARVIS or an agent (they're often misheard). */
        private String bestGuess(ArrayList<String> r) {
            String[] names = {"jarvis", "friday", "oracle", "athena", "zeus", "herald", "pepper", "steve", "veronica",
                    "banner", "edith", "sentinel", "shaabaz"};
            for (String g : r) { String l = g.toLowerCase(); for (String n : names) if (l.contains(n)) return g; }
            return r.get(0);
        }

        @JavascriptInterface
        public void stopListening() { ui.post(() -> { if (recognizer != null) recognizer.stopListening(); }); }

        @JavascriptInterface
        public void abortListening() { ui.post(() -> { if (recognizer != null) recognizer.cancel(); }); }

        @JavascriptInterface
        public boolean ttsAvailable() { return ttsReady; }

        @JavascriptInterface
        public void speak(String id, String text, float pitch, float rate) {
            if (!ttsReady) { js("window.__jarvisTTS && window.__jarvisTTS.done(" + JSONObject.quote(id) + ")"); return; }
            tts.setPitch(Math.max(0.1f, pitch));
            tts.setSpeechRate(Math.max(0.3f, rate));
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String u) { }
                @Override public void onDone(String u) { js("window.__jarvisTTS && window.__jarvisTTS.done(" + JSONObject.quote(u) + ")"); }
                @Override public void onError(String u) { onDone(u); }
            });
            tts.speak(text, TextToSpeech.QUEUE_ADD, null, id);
        }

        @JavascriptInterface
        public void stopSpeaking() { if (tts != null) tts.stop(); }

        @JavascriptInterface
        public void keepAwake(boolean on) {
            ui.post(() -> {
                if (on) getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                else getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
            });
        }

        @JavascriptInterface
        public void setAddress(String url) {
            String clean = url == null ? "" : url.trim().replaceAll("/+$", "");
            if (!clean.isEmpty() && !clean.startsWith("http")) clean = "https://" + clean;
            SharedPreferences.Editor e = getSharedPreferences(PREFS, MODE_PRIVATE).edit();
            e.putString("url", clean).apply();
            ui.post(MainActivity.this::openHome);
        }

        @JavascriptInterface
        public String getAddress() { String a = address(); return a == null ? "" : a; }

        @JavascriptInterface
        public void retry() { ui.post(MainActivity.this::openHome); }

        @JavascriptInterface
        public void changeAddress() { ui.post(() -> web.loadUrl("file:///android_asset/setup.html")); }
    }
}
