# JARVIS: notes for whoever builds the next feature

The owner (Kamal, "Sir") wants every feature easy to discover and to keep. When you add or change a feature:

1. **Add a Training Mode mission** in `web/tutorial.js` (`MISSIONS`): a title, what it does in one line, what to
   do to try it, and how we know it worked (`say` regex on the command, `ev` = a bus event type, or `dom` = a
   `jarvis:<name>` event from `web/hud-fx.js`). New missions show up automatically for people who finished the
   others. Mark laptop-only ones `laptop: true`.
2. **If it needs a permission or a key**, add it to the setup page: phone items in `web/access.html` (`PHONE`),
   laptop items in `jarvis/access.py` (`status`).
3. Add a short section to `README.md`, and tests under `tests/`.
4. Updates reach the owner by themselves (nightly self-update, or "update" on Telegram). Android changes build a new
   APK in GitHub Actions; `jarvis/updater.py` texts the owner the link.

**Quality bar (from the owner):** the live 3D holo simulations (`web/simulate3d.html`) are the BARE MINIMUM for
look and feel. Everything new must match or beat them: neon holographic style, smooth 60 fps motion, live and
interactive (drag/pinch, sliders, scrub), works and looks right on laptop AND phone. Before shipping a screen,
screenshot it at laptop and phone sizes and fix anything cramped, overlapping, blank or laggy. Voice and hearing
must be just as polished (Singapore English, knows the owner's names, never goes silent when it misses something).

House rules (from the owner): no access to bank or finance apps (bank notification alerts are fine, masked, never
OTPs); WhatsApp automation stays off (smart replies only through buttons the owner taps); messages to other people,
laptop shell commands and phone autopilot need the owner's yes; no paid services unless asked; never commit keys.
Keep the neon techy HUD look.
