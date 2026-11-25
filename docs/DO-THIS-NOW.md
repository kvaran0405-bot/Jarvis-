# Do this now: get everything updated (about 40 minutes, once)

Do it in order. After step 5, tell Claude **"done"** and wait for the "new app is ready" message before step 6.

## A. On the laptop (about 15 min)
1. **Update JARVIS:** laptop on and JARVIS running. Text **update** to your JARVIS bot on Telegram and wait for
   "Updated". (Or double-click `update.bat` in the JARVIS folder.)
2. **Link Gmail:** text **/email** to the bot and follow its steps. It needs a Gmail *app password*:
   Google Account → Security → turn on 2-Step Verification → search "App passwords" → create one called JARVIS →
   paste it into the bot. (The bot deletes the message with the password.)
3. **Your resume for ZEUS:** send your CV as a PDF to the bot with the caption **resume**.
4. **Tell ZEUS what you want:** text the bot, e.g. *"ZEUS, I want marketing or events roles, at least $2,800,
   no sales"*.
5. **Permanent app key (so the app updates itself from now on):**
   - Sign in to github.com in your browser as **kvaran0405-bot**.
   - Double-click **app-signing.bat** in the JARVIS folder. A black window opens.
   - It opens GitHub's "New secret" page. Name: `JARVIS_KEYSTORE_B64`, then click in the big Secret box, press
     **Ctrl+V**, then **Add secret**. Press **Enter** in the black window.
   - Click **New repository secret** again. Name: `JARVIS_KEYSTORE_PASSWORD`, then **Ctrl+V**, then **Add secret**.
     Press **Enter** in the black window.
   - Tell Claude **"done"**. Claude builds the app with your permanent key and tells you when it's ready.

## B. On the phone (about 10 min, after Claude says the app is ready)
6. **Remove the old app** (it has a throwaway key): Settings → Apps → JARVIS → Uninstall. *Last time ever.*
7. **Install the new one:** text **/installapp** to the bot, tap the link, install. If asked, allow installing
   from Telegram/Chrome, and tap "Install anyway" if Play Protect asks.
8. **Open JARVIS with the laptop on** (home Wi-Fi). On the setup page tap **ALLOW** on everything:
   notifications, microphone & camera, location *all the time*, **Smart replies & notifications** (notification
   access), battery *unrestricted*, exact alarms, and **Self-updates** (install unknown apps for JARVIS).
   This first open also copies your keys, voices and voice pack onto the phone.
9. *(Optional)* **Autopilot:** Settings → Additional settings → Accessibility → Downloaded apps → **JARVIS
   autopilot** → On. If it's greyed out: Settings → Apps → JARVIS → ⋮ → *Allow restricted settings*, then try
   again. (It switches itself off when a bank app opens; that's normal.)

## C. Your other apps (about 10 min)
10. **Gmail app:** ☰ → Settings → your account → Notifications → **All** (so JARVIS hears every email).
11. **Bank apps:** turn on **email alerts** for card transactions and incoming money (DBS/POSB: digibank →
    Settings → Notifications/Alerts → Email). This feeds VERONICA's P&L.
12. **Job alerts:** in JobStreet, LinkedIn and Indeed, create **daily email job alerts** for your roles. Every
    alert feeds ZEUS's JOB HUNT list.
13. **Steam:** Steam → your profile → Edit Profile → Privacy → set Profile and Game details to **Public**. Then text
    the bot: *"ORACLE, my Steam is steamcommunity.com/id/YOURNAME"*.

## D. Check it works (2 min)
14. **Laptop:** open the dashboard and press **Ctrl+Shift+R** once. Say **"briefing"** and the team reports in.
15. **Phone:** tap **🎯 JOB HUNT**. Ask **"what's my P&L?"**.
16. **In a few weeks:** say **"VERONICA, set my budgets"** (she bases them on last month).

## After this: everything updates itself
- **Laptop JARVIS:** checks every hour and updates itself within the hour of a new version, never while you're
  talking to it (about a minute's restart; open pages reload by themselves).
- **Phone app:** checks every hour and installs new versions itself (after the first time, usually silently; at
  most a single "Update" tap on a notification).
- **Phone brain, voices and trailer:** refresh from the laptop, or from GitHub when the laptop is off.
- You never type "update" again (it still works if you want it right now).
