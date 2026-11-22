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
                    if (hasMic()) request.grant(request.getResources());
                    else { pendingWebPermission = request; askMic(); }
                });
            }
        });

        if (!hasMic()) askMic();
        tts = new TextToSpeech(this, status -> {
            ttsReady = status == TextToSpeech.SUCCESS;
            if (ttsReady) tts.setLanguage(Locale.UK);
        });

        if (savedInstanceState != null) web.restoreState(savedInstanceState);
        else openHome();
    }

    // ------------------------------------------------------------------ navigation
    private String address() {
        return getSharedPreferences(PREFS, MODE_PRIVATE).getString("url", null);
    }

    private void openHome() {
        String a = address();
        if (a == null || a.isEmpty()) web.loadUrl("file:///android_asset/setup.html");
        else web.loadUrl(a + "/command-centre.html");
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
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

    private void askMic() {
        requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] results) {
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
                            if (r != null && !r.isEmpty()) emitSpeech("result", r.get(0), true);
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
                i.putExtra(RecognizerIntent.EXTRA_LANGUAGE, lang == null || lang.isEmpty() ? "en-US" : lang);
                i.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, partial);
                i.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1);
                i.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getPackageName());
                try { recognizer.startListening(i); }
                catch (Exception e) { emitSpeech("error", "aborted", true); emitSpeech("end", "", true); }
            });
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
