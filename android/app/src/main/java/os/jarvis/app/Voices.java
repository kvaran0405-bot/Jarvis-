package os.jarvis.app;

import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * The backup cast: when the premium (Gemini) voices aren't available (free allowance used up, no internet), each agent
 * still gets their own voice from the phone's built-in Google voices, never the default one: a British man for JARVIS,
 * a low warm American woman for PEPPER, and so on. Works fully offline with the "local" voices.
 */
final class Voices {
    private Voices() {}

    /** locales (best first), voice codes known to fit (Google TTS names like en-gb-x-rjs-network), pitch, speed. */
    private static final class Part {
        final String[] locales, codes; final float pitch, rate;
        Part(String[] l, String[] c, float p, float r) { locales = l; codes = c; pitch = p; rate = r; }
    }

    private static final String[] GB = {"en-GB"}, US = {"en-US"}, AU = {"en-AU", "en-GB"}, IN = {"en-IN", "en-GB"};
    // Google voice codes: en-GB men rjs gbb gbd, women gba gbc gbg; en-US men iol iom tpd, women iob iog tpc tpf sfg;
    // en-AU men aub aud, women aua auc; en-IN men end, women ahp ene.
    private static final Map<String, Part> CAST = new HashMap<>();
    static {
        CAST.put("JARVIS",   new Part(GB, new String[]{"rjs", "gbd", "gbb"}, 0.88f, 0.95f));   // the butler
        CAST.put("FRIDAY",   new Part(AU, new String[]{"aua", "auc", "gbg"}, 1.08f, 1.06f));   // quick, cheeky
        CAST.put("PEPPER",   new Part(US, new String[]{"tpc", "sfg", "iog"}, 0.90f, 0.93f));   // low, warm, velvety
        CAST.put("VERONICA", new Part(US, new String[]{"iog", "tpf", "iob"}, 0.86f, 0.95f));   // smoky
        CAST.put("EDITH",    new Part(GB, new String[]{"gbc", "gba", "gbg"}, 0.92f, 0.97f));   // silky, low
        CAST.put("ATHENA",   new Part(GB, new String[]{"gba", "gbg", "gbc"}, 0.98f, 0.95f));   // wise, smooth
        CAST.put("ZEUS",     new Part(US, new String[]{"iom", "iol", "tpd"}, 0.75f, 1.00f));   // booming
        CAST.put("HERALD",   new Part(GB, new String[]{"gbd", "gbb", "rjs"}, 0.98f, 1.00f));   // diplomat
        CAST.put("STEVE",    new Part(US, new String[]{"tpd", "iol", "iom"}, 1.00f, 1.02f));   // earnest
        CAST.put("BANNER",   new Part(US, new String[]{"iol", "tpd", "iom"}, 0.92f, 0.88f));   // gentle, slow
        CAST.put("SENTINEL", new Part(US, new String[]{"iom", "tpd", "iol"}, 0.72f, 0.92f));   // gravel
        CAST.put("ORACLE",   new Part(AU, new String[]{"aud", "aub", "gbd"}, 0.90f, 0.96f));   // calm analyst
        CAST.put("GUEST",    CAST.get("JARVIS"));
    }
    private static final String[] WOMEN = {"gba", "gbc", "gbg", "iob", "iog", "tpc", "tpf", "sfg", "aua", "auc", "ahp", "ene"};

    static float pitch(String agent) { return part(agent).pitch; }
    static float rate(String agent) { return part(agent).rate; }
    private static Part part(String agent) {
        Part p = agent == null ? null : CAST.get(agent.toUpperCase(Locale.ROOT));
        return p != null ? p : CAST.get("JARVIS");
    }

    private static final Map<String, Voice> chosen = new HashMap<>();

    /** The best installed voice for this agent (network quality when online, otherwise the on-phone one). */
    static Voice pick(TextToSpeech tts, String agent, boolean online) {
        String key = (agent == null ? "JARVIS" : agent.toUpperCase(Locale.ROOT)) + online;
        if (chosen.containsKey(key)) return chosen.get(key);
        Part p = part(agent);
        boolean wantWoman = isWoman(p.codes[0]);
        Voice best = null; int bestScore = Integer.MIN_VALUE;
        Set<Voice> all;
        try { all = tts.getVoices(); } catch (Exception e) { all = null; }
        if (all != null) for (Voice v : all) {
            String tag = v.getLocale().toLanguageTag(), name = v.getName().toLowerCase(Locale.ROOT);
            int li = -1;
            for (int i = 0; i < p.locales.length; i++) if (tag.equalsIgnoreCase(p.locales[i])) { li = i; break; }
            if (li < 0) continue;
            if (v.getFeatures() != null && v.getFeatures().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)) continue;
            if (v.isNetworkConnectionRequired() && !online) continue;
            int s = 100 - li * 40 + v.getQuality() / 10 + (v.isNetworkConnectionRequired() ? 15 : 0);
            for (int i = 0; i < p.codes.length; i++) if (name.contains("-x-" + p.codes[i])) { s += 60 - i * 10; break; }
            String code = name.contains("-x-") ? name.substring(name.indexOf("-x-") + 3).split("-")[0] : "";
            if (!code.isEmpty() && isWoman(code) != wantWoman) s -= 80;   // never the wrong voice for the character
            if (s > bestScore) { bestScore = s; best = v; }
        }
        chosen.put(key, best);
        return best;
    }

    private static boolean isWoman(String code) {
        for (String w : WOMEN) if (w.equals(code)) return true;
        return false;
    }
}
