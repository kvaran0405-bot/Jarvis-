package os.jarvis.app;

import android.content.Context;
import android.content.SharedPreferences;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Small HTTP helper for the app's background parts: talks to the laptop with the phone's device token. */
final class Net {
    private Net() {}

    static String base(Context c) {
        return c.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getString("url", null);
    }

    static boolean linked(Context c) {
        SharedPreferences p = c.getSharedPreferences("jarvis", Context.MODE_PRIVATE);
        return p.getString("url", null) != null && p.getString("device_token", null) != null;
    }

    /** GET when body is null, else POST JSON. Throws on network errors or non-200 answers. */
    static String call(Context c, String path, String body, int readTimeoutMs) throws Exception {
        SharedPreferences p = c.getSharedPreferences("jarvis", Context.MODE_PRIVATE);
        String base = p.getString("url", null), token = p.getString("device_token", "");
        if (base == null) throw new Exception("no address");
        HttpURLConnection conn = (HttpURLConnection) new URL(base + path).openConnection();
        conn.setConnectTimeout(6000);
        conn.setReadTimeout(readTimeoutMs);
        conn.setRequestProperty("X-Jarvis-Device", token);
        if (body != null) {
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            try (OutputStream o = conn.getOutputStream()) { o.write(body.getBytes(StandardCharsets.UTF_8)); }
        }
        int code = conn.getResponseCode();
        if (code != 200) throw new Exception("HTTP " + code);
        try (InputStream in = conn.getInputStream()) {
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] b = new byte[8192];
            for (int r; (r = in.read(b)) != -1; ) buf.write(b, 0, r);
            return buf.toString("UTF-8");
        }
    }

    /** Bank and finance apps: JARVIS never reads, forwards or touches them. */
    static boolean isFinance(String pkgOrName) {
        if (pkgOrName == null) return false;
        String s = pkgOrName.toLowerCase();
        String[] words = {"bank", "dbs", "posb", "ocbc", "uob", "paylah", "maybank", "hsbc", "citi", "standardchartered",
                "scb", "trust", "revolut", "youtrip", "wise", "paypal", "grabpay", "wallet", "pay.", ".pay", "nets",
                "singlife", "moomoo", "tiger", "syfe", "endowus", "stashaway", "crypto", "binance", "coinbase", "otp"};
        for (String w : words) if (s.contains(w)) return true;
        return false;
    }
}
