# JARVIS OS

A personal multi-agent system powered by Claude. JARVIS runs your personal life, career and academics as a
team of 11 AI agents. They take orders by voice, text or Telegram from your phone, send e-mails for you,
read and sort your inbox, control your laptop and Android phone, run routines you set up, work through
queued tasks overnight, and send you daily reports.

![command centre](docs/command-centre.png)

## The team

| Agent | Role | What it does |
|---|---|---|
| **JARVIS** | Prime Orchestrator | Takes your orders, keeps tasks, calendar and goals in order, and delegates to the specialists |
| **FRIDAY** | Daily Intelligence | Morning brief, evening report, weekly review |
| **ORACLE** | Research | Web research, comparisons, decisions, saved as notes |
| **ATHENA** | Academics | Assignments, exam prep, study plans, revision blocks, study material |
| **ZEUS** | Career | Job and internship pipeline, CV and cover-letter drafts, interview prep |
| **HERALD** | Comms & Inbox | Reads new e-mail, replies for you, turns requests into tasks |
| **STEVE** | Fitness & Habits | Workouts, routines, habit tracking |
| **VERONICA** | Finance | Spending log, budgets, savings |
| **BANNER** | Wellbeing | Sleep, stress and burnout watch |
| **EDITH** | Devices & Automation | Controls your laptop and phone, handles files, builds routines |
| **SENTINEL** | Deadline Watch | Scans every few hours for overdue or at-risk work and raises alerts |

## Autopilot (what runs while you rest)

| When | Who | Job |
|---|---|---|
| 07:00 daily | FRIDAY | **Morning brief**: schedule, top 3 priorities, deadlines, overnight results |
| Every 3 h | SENTINEL | **Deadline watch**: fixes what it can and alerts you only when needed |
| 21:00 daily | FRIDAY | **Evening report**: what got done, what slipped, plan for tomorrow |
| 02:00 daily | JARVIS | **Night shift**: every task with an agent assignee gets done autonomously |
| Every 60 min | HERALD | **Inbox sweep**: new e-mail → tasks, replies, urgent alerts |
| Your choice | Any agent | **Your own routines**, e.g. "every weekday at 6am send me a quote and my top 3 on Telegram" |
| Sun 18:00 | JARVIS | **Weekly review** across life, career and academics |

All times can be changed in `.env`. Reports show up in the dashboard and, if you set them up, arrive by
**Telegram** and/or **e-mail**.

To queue work for the night, just say it, e.g. *"Oracle, research the best laptops for ML under $1200 tonight"*
or *"Athena, make me a 2-week revision plan for my calculus exam on Dec 3"*. JARVIS creates the task, assigns it
to the right agent, and the result is in your morning brief.

## Your agents think; you say yes or no

Agents use their own judgment on everything. They keep your tasks, notes and study blocks up to date themselves,
and when something needs your say-so they **propose** it:

> 💡 **SENTINEL**: Ask Dr. Okafor for a 2-day extension
> Why: assignment 3 is due tomorrow and you have two exams.
> **[✅ Yes, do it] [❌ No]**

Answer however you like: tap the button, or just **say it**. The dashboard reads new proposals out loud and
then listens for your answer, no wake word needed: *"Yeah, go ahead"*, *"Nah, leave it"*, *"Send the second
one"*. The same works by Telegram voice note or text. Saying yes to a proposal also approves the messages
written in it, so you're never asked twice. Morning briefs, evening reports and the deadline watch all end
with a few proposals to make your day go better.

Your agents are also your friends. Chat about your day, vent, ask random things. They remember what matters to
you, ask how the exam went, and keep you company at 2 a.m.

## Email briefings, Stark-style

When a new e-mail arrives, HERALD briefs you on Telegram, in any language:

> 📨 **Prof. Martin — Présentation du projet** · 🌐 Translated from French
> Prof. Martin would like you to present the group project Monday at 10, Sir, and wants a yes by Friday.
> **A) Accept** · **B) Ask for Wednesday** · **C) Decline politely**

Tap a reply and it is sent in the sender's language, threaded under their e-mail. Or text `reply 7: your own
words`. You can also ask any time: *"Herald, what does my latest email say?"*. HERALD writes down which replies
you pick in its own notebook and learns your style.

## Every agent has its own brain

Each agent has its own **personality**, its own **conversation**, its own **private notebook** (what it has learned
about how you like things done in its area), and optionally its own **AI model**. Set those in `.env`, for example
`JARVIS_MODEL_HERALD=sonnet` for smarter e-mail replies, or `JARVIS_BRAIN_STEVE=gemini` to run the fitness coach
for free.

## Brains, and the pause switch

JARVIS can think with three different brains:

| Brain | Cost | Notes |
|---|---|---|
| `pro`: your Claude Pro/Max plan, via Claude Code | no extra cost | Shares your plan's usage limits with your own Claude chats |
| `gemini`: Google Gemini free tier | free | Backup and saver mode. On the free tier Google may use what you send to improve its products |
| `api`: Anthropic API key | pay as you go | No plan limits |

To use your plan, install Claude Code once. In PowerShell: `irm https://claude.ai/install.ps1 | iex`. Then run
`claude` once and log in with your Claude account. Set `JARVIS_BRAIN=pro` in `.env`.

If you add a free `GEMINI_API_KEY`, routines run on Gemini, and JARVIS switches to Gemini automatically when your
Claude plan hits its limit.

**Pause any time so JARVIS doesn't use up your Claude plan.** Use any of these:
- the **⏸ Pause** button in the dashboard (1 h / 3 h / 8 h / until you resume)
- Telegram: `/pause`, `pause for 3 hours`, `/resume`, `/status`, `/saver`
- voice: *"Jarvis, pause"* … *"Jarvis, resume"*

While paused, JARVIS makes **no AI calls at all**. Routines wait, and messages you already approved still go out.
**Saver mode** (`/saver` or 🔋) keeps JARVIS working on free Gemini only and never touches your Claude plan.

## Quick start

1. Get an API key at <https://console.anthropic.com>.
2. Run:
   ```bash
   ./start.sh          # macOS / Linux
   start.bat           # Windows
   ```
   The first run creates `.env` and `profile.md`. Put your `ANTHROPIC_API_KEY` in `.env`, set your name and timezone,
   then run it again.
3. Fill in `profile.md` (your courses, career goals, habits, routine). Every agent reads it.
4. The command centre opens at <http://127.0.0.1:7334/command-centre.html?autostart=true>. Click **Engage Protocol**
   and the agents report in.

Keep the program running for the autopilot to work. On a laptop, leave it plugged in with sleep turned off,
or run it on a small always-on machine or VPS.

### Updating

JARVIS updates itself every night at 04:10 if there's a newer version (turn off with `JARVIS_AUTO_UPDATE=off`).
To update right now, text **update** to your JARVIS bot on Telegram. That's it. The laptop downloads the newest version, restarts, and
texts you "✅ Updated" with what changed. Open pages on the laptop and phone reload themselves onto the new version
(they wait if someone is talking or a call is on). If the phone app itself ever changes, JARVIS sends you the
download link. Your `.env`, profile and memory are kept.

You can also double-click **update** in the JARVIS folder, or press *Update* in the dashboard's Autopilot tab. The
first time, it installs Git and may ask you to sign in to GitHub in the browser.

### Terminal use
```bash
python -m jarvis ask "What's on my plate this week?"
python -m jarvis ask --agent ZEUS "Find 5 remote junior backend roles and track them"
python -m jarvis job morning_brief       # run any routine now
python -m jarvis agents
```

## Like in the movie: agents that talk

- **Natural voices, free:** every agent has its own neural voice. JARVIS is British, FRIDAY is Irish, and the others
  have their own. With an ElevenLabs key you get premium voices instead; if the voice service is unreachable,
  your computer's own voices take over.
- **VoiceStudio (free, open source, on your laptop):** install [VoiceStudio](https://github.com/debpalash/VoiceStudio)
  (Windows installer, about 10 GB, no graphics card needed) and keep it open. JARVIS then uses it automatically:
  each agent gets a voice designed from a description (JARVIS: "male, middle-aged, British accent"; FRIDAY: "female,
  young adult, Irish accent"…), fixed with a seed so it never changes, and moods become **real laughs, sighs and
  "hmm"s**. You can also design or record a voice in VoiceStudio and assign it: `JARVIS_VS_VOICE_JARVIS=<name>`.
  On a laptop without a graphics card it's slower; if a line takes longer than `JARVIS_VOICESTUDIO_TIMEOUT`
  seconds, JARVIS uses the online voice for that line instead.
- **They speak up on their own:** the morning brief, reminders, new ideas for your yes/no, email briefings
  and urgent alerts are **said out loud** in the JARVIS window as they happen, and arrive as **Telegram voice
  notes** on your phone. At night (quiet hours) they stay silent unless something is critical.
- **Always-on JARVIS window:** `start.bat` opens JARVIS in its own app window that can talk without a click and
  turns hands-free listening on, so you can just say *"Jarvis, …"* from across the room. Allow the microphone once
  and it remembers. With `install-autostart.bat`, it's there every time you log in.

## Talk to JARVIS (voice)

- **Hands-free:** click **👂 Hands-free** in the dashboard (Chrome or Edge), then just speak:
  *"Jarvis, what's on my plate today?"*, *"Friday, read me my brief"*, *"Edith, open Spotify"*.
  Say only *"Jarvis"* and it answers *"Yes, Sir?"* and waits for your order.
- **Push to talk:** click 🎙 or press **Ctrl+Space**. **Esc** stops it talking.
- **Fast replies:** answers are streamed and spoken sentence by sentence, so JARVIS starts talking before it has
  finished thinking. Spoken orders use a quicker thinking setting and get short spoken answers.
  `JARVIS_FAST_MODE=on` makes replies ~2.5x faster again, at double the cost.
- **From your phone:** send a **voice note** to your Telegram bot. It is transcribed on your laptop (free, private)
  and JARVIS replies with text, plus a voice note if ElevenLabs voices are on.

## Control JARVIS from your phone (Telegram)

Text your JARVIS bot on Telegram from anywhere:

- `What's on my plate today?`
- `Email Dr. Okafor asking for the CSC 301 slides`
- `Send me a screenshot of my laptop`
- `Remind me at 5pm to submit the form`
- `ZEUS, find 5 remote internships tonight`
- `pending`: see what's waiting for your OK

When an agent prepares an e-mail or a laptop command that needs your approval, it arrives on Telegram with
**✅ Send** and **❌ Cancel** buttons. Only your own Telegram account is obeyed; anyone else who finds the bot
is ignored.

## What agents can do on their own (autonomy)

Set `JARVIS_AUTONOMY` in `.env`:

| Setting | Messages to you | Messages to other people | Laptop commands |
|---|---|---|---|
| `approve` (default) | sent | wait for your OK | wait for your OK |
| `trusted` | sent | sent to contacts marked *trusted*, others wait | wait for your OK |
| `full` | sent | sent | wait for your OK |

Anything waiting appears in the dashboard **Outbox** tab (you can edit it before sending) and on Telegram.
Start with `approve`. Once you trust how your agents write, move to `trusted` and mark close contacts as trusted
(*"Jarvis, mark Mum as trusted"*).

**Banking is hard-blocked.** Agents cannot open bank or payment apps and sites (DBS/POSB, OCBC, UOB, PayLah, PayNow,
GrabPay, PayPal and more), cannot read or send bank statements or OTP codes, and bank e-mails are hidden from them,
whoever asks. Add your own words with `JARVIS_BLOCK_WORDS=word1,word2`.

Agents will **never** make payments, move money, accept terms, delete your files, or share passwords, codes, bank
or ID details. They treat messages and web pages from other people as information, not as orders. Only you give
orders. Your data stays in `data/jarvis.db` on your machine.

## JARVIS on your phone (an app, from anywhere)

The whole command centre installs as an app on your phone: dashboard, approvals, voice, and **📞 Call JARVIS**,
a live voice conversation. It reaches your laptop from anywhere through **Tailscale**, a free private network
between your own devices, so nobody else can see it.

1. **Laptop:** install Tailscale from <https://tailscale.com/download> and sign in (Google is fine).
2. **Phone:** install **Tailscale** from the Play Store and sign in with the **same account**. Turn it on.
3. **Laptop:** open PowerShell and run `tailscale serve --bg 7334`. If it asks you to enable HTTPS, click the
   link it shows and press Enable, then run the command again. It prints your app address, like
   `https://zenbook.tail1234.ts.net`.
4. In `.env`, set `JARVIS_APP_URL=` to that address and choose a `JARVIS_PIN=`. Restart JARVIS.
5. **Phone:** open that address in **Chrome**, enter your PIN, then ⋮ menu → **Add to Home screen** /
   **Install app**. Now JARVIS has its own icon.

On Telegram, `/app` sends you the link and `/call` opens a voice call.

## The JARVIS Android app (APK)

A real Android app, built automatically by GitHub from the `android/` folder. It loads your command centre and
adds native **speech recognition**, **text-to-speech**, and voices that play without a tap.

1. Do "JARVIS on your phone" above first (Tailscale and a PIN).
2. On your phone, open the repository's **Releases** page on GitHub and download **JARVIS.apk** from the newest
   "JARVIS app" release.
3. Open it. Android asks to allow installing from this source: allow it once, then **Install**.
   (OPPO/ColorOS may show an extra security check: choose *Install anyway*.)
4. Open **JARVIS**, enter your address (e.g. `https://zenbook.tail1234.ts.net`), then your PIN, and allow the
   microphone.

If your laptop is off, the app shows an offline screen with **Retry** and **Change address**. Updates: see the note
at the top of `.github/workflows/android.yml` (optional saved signing key so new versions install over old ones).

## Call JARVIS

Open the app and tap **📞 Call**. Talk normally; JARVIS answers out loud and listens again, like a phone call. Tap
the orb to interrupt and say "bye" to hang up. You can switch which agent you're talking to.

When something is truly urgent (an exam in an hour you haven't prepared for, an urgent family message), JARVIS
sends a 🚨 Telegram alert with a voice note and says it out loud on the laptop. At night (`JARVIS_QUIET_HOURS`)
it stays silent unless the alert is critical.

## Setup and training

- **Setup** (`/access.html`, or say "setup"): every permission for the phone and laptop in one list. Keep tapping
  **ALLOW NEXT**; each one ticks off when you come back. If Android greys out Autopilot or Smart replies, tap
  "App settings", then ⋮ and "Allow restricted settings".
- **Training mode** opens when JARVIS starts: hands-on missions for every feature (drop a document, group call, Holo
  Lab, phone powers...). Each ticks off when it actually works. Skip one, skip all, or "don't show on start"; say
  "tutorial" to bring it back.
- **Hearing you properly:** JARVIS listens in Singapore English (en-SG) on the laptop, the phone and calls, so local
  accents and names come through. On the laptop, 🎙 push-to-talk records a noise-reduced clip that stops when you stop
  talking, and the laptop's own speech engine understands it with JARVIS's vocabulary (agent names, Shaabaz, Kaplan,
  your places). If it isn't sure, JARVIS says "Sorry Sir, say that again?" and listens once more, never silence.
  On the phone it waits through short pauses and picks the guess that matches JARVIS's names. Choose the laptop
  engine size with `JARVIS_HEAR_MODEL` (default small; base is lighter, medium is stronger).
- **Voices that sound human:** every agent has an attitude in their voice (JARVIS dry, FRIDAY playful, PEPPER warm,
  ZEUS fired up, VERONICA sarcastic, BANNER gentle, SENTINEL stern…). Each sentence gets its own delivery: questions
  lift, exclamations brighten, "…" trails off, and there are real breaths between sentences. JARVIS also hears the
  feeling in the words (sorry → concerned, congrats → proud, hurry → urgent), and everyone speaks softer late at
  night. Laughs, sighs and gasps are acted out. With the free Gemini key (`/gemini`) the agents get full acting
  direction (breaths, hesitations, emphasis). With no internet, a natural offline voice on the laptop takes over
  (installs itself; check "Natural offline voice" on the setup page).
- **Says Singapore names properly:** Tampines, Bukit Timah, Punggol, Shaabaz, MRT and more are spoken right (the
  screen keeps the real spelling). Teach new ones: "Jarvis, pronounce Kamal as Kah-mahl". JARVIS also wakes your
  speakers or Bluetooth headphones a moment before talking, so the first word isn't swallowed.
- **Voice typing anywhere (laptop):** hold **Right Alt** (or the **Copilot key** ✦, or Right Ctrl), talk, let go: JARVIS types it into whatever app has the
  cursor. Start with "Jarvis, ..." to give an order instead. Understood on the laptop itself; never types into
  banking windows. Change the key with `JARVIS_DICTATE_KEY` (auto, ralt, copilot, rctrl, f8, f9, capslock) or `JARVIS_DICTATE=off`.
- **Phone app:** send **/installapp** to your bot on Telegram: you get a one-tap download of the newest app and the
  3 install steps (Play Protect off for a minute, install, Play Protect back on).
- **Fast mode:** send **/gemini** to your bot on Telegram to add a free Gemini key (your message is deleted at once,
  the key is tested, fast mode switches on). "Fast mode on/off" any time; the dashboard shows ⚡FAST. If Gemini
  stumbles, the main brain answers instead.
- **Email:** send **/email** to your bot on Telegram: it sends the link for a Gmail app password, you reply with your
  address and the 16 letters, and it deletes your message, checks it with Gmail, saves it and restarts. Or, on the
  setup page, enter your Gmail address and a Gmail app password (the page links to Google's
  page for making one; it needs 2-Step Verification). JARVIS checks it works, saves it on the laptop, and restarts.
- **JARVIS just knows (live awareness):** before every reply, every agent automatically gets where you are now,
  where you've been today, hours at each place this week (worked out from GPS), your next event, phone battery,
  last night's screen time and any urgent messages. You never have to tell it. Ask "how many hours was I at the gym
  this week?". Guests never see any of it.
- **Friends who notice (location chat):** when you've been somewhere for 5+ minutes, the agent who fits the area
  texts you a tip, e.g. FRIDAY for food, STEVE for nature walks, ATHENA for heritage, HERALD for views and nights
  out ("Hi Sir, I see you're at City Hall! Lau Pa Sat is 8 minutes away..."). Never at home, driving, in quiet hours
  or focus; once per area a day, max 4 a day. "Location chat off/on".
- **Navigation inside JARVIS (no Google Maps):** "take me to Odeon Towers", "how do I get to Jewel by 18:30", or type
  in "Where to, Sir?" on the map. You get walk, bus/MRT, Grab (with a price range) and drive, timed for the usual
  traffic and the rain, plus a leave-by time; the route glows on JARVIS's map with turn-by-turn steps, and ▶ START
  gives live navigation with JARVIS speaking the turns. Places come from OneMap (free, official Singapore map);
  routes from the free OpenStreetMap routing servers. Bus/MRT times and Grab prices are estimates.
- **Real bus & MRT (free):** send **/onemap** (free OneMap account) and **/lta** (free LTA DataMall key) on Telegram.
  Then routes show the real journey: walk to the stop, bus number with **live arrivals** ("next 3, 14 min"), MRT line
  and changes, fare, arrival time, and exactly **when to leave** to catch the bus. MRT trains have no public live feed,
  so JARVIS shows the usual frequency. "Leave now" alerts use the same.
- **Your day, glowing:** 📅 MY DAY on the map replays where you went (colour = time of day) with steps (the phone's
  step counter), km walked, km travelled, time moving and places. When you set off somewhere, JARVIS asks where
  you're heading ("trip questions off" to stop). "Leave now" alerts use your live location, traffic, rain, and
  bus/MRT vs Grab options.
- **Explorer map** (`/map.html`, or say "show me my map"; works on the phone too): a dark street map where the places
  you've been glow and the rest stays in shadow, 40 Singapore side quests (food, nature, heritage, views, night) that
  unlock when you visit, and your route for the day. Tap a quest → + ADD TO ROUTE → ROUTE opens Google Maps.
  Map tiles: © OpenStreetMap contributors © CARTO.
  **Live location & history:** works over Wi-Fi or mobile data as long as Tailscale is on on the phone. The map shows
  a live blue dot and today's path; ask "where was I yesterday at 3pm?" or "where did I go today?". When the phone
  is offline it keeps the points and sends them later. History is kept 120 days, on your laptop only.
  For the trail to keep recording in the background, allow location **all the time** (setup → "Location: all the
  time"). Your location only ever goes to your own laptop.
- **Your map and route:** every place your phone has been lights up on the Singapore holo map (stored on the laptop
  only). Say "plan my route" for today's stops in order, drawn on the map, with Google Maps directions sent to your
  phone, or "plan a route to Orchard, then Tampines Mall".
- **Photo sorter:** every night the phone sends new photos to the laptop and JARVIS files them into
  Pictures/JARVIS Albums (Receipts, Notes & Slides, Event Setups, Food, People, Places...). Ask "find my Uniqlo
  receipt". Photos of cards, IDs or passwords are thrown away. Turn off with `JARVIS_PHOTO_SORT=off`.

## Phone powers

Just ask, by voice or text: "call Mum", "wake me at 6:30", "timer 10 minutes", "torch on", "play Coldplay on Spotify",
"pause the music", "find lo-fi on YouTube", "search Shopee for black sneakers", "open Gmail", "take me to Changi",
"what's on my phone screen?", "what's in my last photo?", "how long was I on Instagram today?".
JARVIS opens things ready for you: it never sends, buys or pays by itself, and bank and finance apps stay off limits.
Screen time needs "Usage access" (JARVIS opens that setting the first time you ask).

## Bank notifications (read-only)

VERONICA reads your bank's **transaction alert e-mails** (turn on e-mail alerts in your bank's app) and sends a
**weekly money report** on Sundays: every transaction, totals, anything unusual. Card and account numbers are
masked to the last 4 digits. OTP / PIN / password e-mails are never shown to any agent, and agents still can't
open bank apps or sites or move money.

## JARVIS Mark III

**Floating orb:** a glowing JARVIS sphere stays on top of every app, on the laptop (starts with JARVIS) and the
phone (Autopilot tab → Floating orb). Click or tap to talk, drag it anywhere, right-click or long-press for more.

**Interactive HUD:** tap an agent for their live status, poke the reactor, hover for readouts. Also: suit themes
("Jarvis, stealth mode"), guest mode, the Stark Expo demo, birthday mode, a boot film on start, and interface sounds
(✦ FX).

**Holo Lab (🌐 Holo):** "show me my week / Shaabaz / body / money / Singapore / diagnostics / trophies". The Body
view is a neon front-and-back muscle map from your logged workouts, with a 3D hologram one tap away. 19 trophies
unlock automatically.

**Butler:**
- Leave-now alerts with rain advice, and mission briefings on big days.
- The Stark Daily newspaper every morning, plus before-you-ask suggestions.
- Water and posture nudges, groceries and expiry dates.
- "Where is…" searches everything JARVIS knows.

**Laptop command:**
- Windows, media, volume and brightness by voice; saved workspaces.
- Folder tidy and bulk rename (preview first).
- PowerPoint and Excel files made for you; "what's on my screen?".
- Screenshots get a "Read it?" offer; hand gestures through the webcam (✋ Gestures).

**Phone app v2:**
- Reactor home with tap-to-talk and hands-free mode; Vision (camera with AR labels, meal and outfit checks).
- Car mode, find my phone, shared clipboard, location magic, smart replies for every messaging app.
- Phone autopilot (after your yes), share to JARVIS, quick tile, home widget.
- Hand calls over from the laptop, and use the phone as a remote for the laptop screen.

**Shaabaz Studio:**
- Floor planner (2D and 3D, auto layout from room size and guests).
- Mood-board PDFs, portfolio website, brand kit and QR business card.
- `python -m jarvis backup` / `restore`. See docs/SELLING.md for turning JARVIS into a product.

## JARVIS Mark IV: the team comes alive

**Emotion and voices**
- Agents laugh, sigh, gasp and whisper. Write it in a reply as `[laughs]` or `[sighs]`; the voice acts it out and the reactor reacts.
- **Gemini voices:** if `GEMINI_API_KEY` is set, each agent gets their own expressive Google voice. If Google says no
  (limits or preview rules), JARVIS falls back to the free voices on its own. Turn it off with `JARVIS_GEMINI_VOICES=off`.

**Friendships (bonds)**
- Every agent has a bond level, from 1 (New) to 10. It grows when you talk, say thanks, approve their ideas and
  celebrate together. Look for the ♥ badge on each card.
- **Double-click a card (long-press on the phone)** to open that agent's room. It shows unlocks, shared memories,
  their diary, gifts they made you, what they think of the team, and their favourites.
- Unlocks: level 2 nicknames, 3 running gags, 4 surprise voice notes, 5 gifts, and more after that.
- Agents have daily moods that follow your life. SENTINEL is grumpy when tasks are overdue; STEVE is pumped after the gym.
- Try "good morning team", "good night Friday", or "Friday, call me Dragon".
- A weekly thank-you note (Saturday) comes from the agent you worked with most.

**Team life**
- **Group call:** say "team, what should I do this weekend?" or "group call about the Tan wedding", or press 🎙 Team.
  Agents talk to you and to each other, each in their own voice. This also works on Telegram and during a phone call.
- **Team dinner:** every Friday at 20:30, or say "team dinner" any time. It's banter, roasts and a toast.
- **Surprise voice notes:** up to 2 a week, sent by a close friend (level 4+).
- **Diaries:** agents write a private entry every Sunday. Read them in their rooms.
- **Gifts** from friends at level 5+: playlists, neon phone wallpapers and cards (Saturday).
- **Team photo:** right-click 🎙 Team, or open it from any room. Closer friends stand in front.

**Interactive and style**
- **Drag and drop:** drag a task onto an agent to hand it over. Drag a file (PDF, Word, PowerPoint, text or an image)
  onto the reactor or an agent, and they read it and tell you what matters.
- **Desk AR** (`/ar.html` on the phone, or say "open desk AR"): your day, tasks, team and goals float around your
  desk over the camera. Turn the phone to look around.
- **Seasonal skins** appear on their own: Deepavali, Lunar New Year, Hari Raya, National Day, Christmas, New Year
  and your birthday. You can say "seasonal skins off", or "preview the Christmas skin".

## Your crew of friends

- **Evening check-in (21:30):** FRIDAY, JARVIS or BANNER texts you about your day; just reply. They log your mood
  and one good thing, and notice patterns. **Sunday heart-to-heart** with BANNER, plus a nudge to see friends.
- **"I can't sleep"** gets BANNER keeping you company. **"Hype me up"** gets a ZEUS pep talk. **"Be real with me"**
  gets the honest version.
- Birthdays and anniversaries ("Jarvis, Mum's birthday is 12 March") come up in the morning brief with gift ideas.
- Confetti and a proud line when you finish an assignment, confirm a gig or keep a gym streak.
- Monthly life report with grades per area and your best moments. Letters to future you.

## Study

- **Ask my files:** "Athena, what did week 5 say about WACC?" She searches your Documents, OneDrive, Desktop and
  Downloads (PDF, Word, PowerPoint, text) and names the file and slide.
- **Exam mode:** "Athena, FIN302 exam is 3 Dec 9am, topics hedging and NPV" gives you a countdown, a revision plan
  and a daily quiz at 19:30.
- **Read-aloud:** "Read this to me" sends an article or your notes to your phone as audio.
- **Photos:** send a poster, a slide, a receipt or a business card to Telegram and JARVIS files it.

## Stark protocols

- **"Suit up for 50 minutes on the essay"**: focus mode. Non-urgent announcements wait, and a banner counts down.
- **"Clean slate protocol"** moves today's leftovers to tomorrow. **"House party protocol"** runs event-day checks.
  **"War room"** gets a spoken briefing from PEPPER, ATHENA, ZEUS, VERONICA and SENTINEL.
- **"What should I do now?"** gets the one best next thing.

## WhatsApp smart replies (phone app)

In the JARVIS app: Autopilot → **WhatsApp smart replies → turn on**, and allow JARVIS in *Notification access*.
When a WhatsApp message arrives, a JARVIS notification offers up to 3 replies with **Send A/B/C** buttons.
Tapping one replies through WhatsApp's own notification reply. Nothing is sent without your tap, and group chats
are ignored.

## JARVIS in the cloud, 24/7, free (#7)

JARVIS's main brain can live on a free always-on server (Oracle Cloud's Always Free tier), so Telegram, the night
shift, reminders and the phone link keep running with the laptop off. The laptop becomes the cloud's **satellite**
and does the laptop-only jobs (screen, files, apps, approved commands) whenever it's on.

Setup is about 15 minutes once: follow **[docs/CLOUD.md](docs/CLOUD.md)**, then double-click `cloud-move.bat`. It
moves your memory and settings over your private Tailscale network and switches the phone app over by itself.

## Predictive JARVIS (#69)

JARVIS learns your routines from the phone's location history (the last 6 weeks): a trip between two of your places
at about the same time, on the same weekday at least twice (or on 3+ weekdays). About 15 minutes before one, if
you're at the starting place, he speaks up first with the live way there:

> "You usually head to the gym around 18:10 on Tuesdays, Sir. Bus 15 is 4 minutes out: leave by 18:06."

He nudges once per routine per day, never in quiet hours or focus mode, and also from the phone when the laptop is
off. Ask "what are my routines?", or say "routine nudges off" or "routine nudges on".

## Holo Hands (#44, #46, #47, #48)

**Smooth and reliable:**
- The hand tracking runs in its own background thread, on the graphics chip where possible, so the hologram and
  menus stay smooth even while it's working.
- It only looks at new camera frames, in a lighter size.
- Your hand is smoothed and slightly predicted, so the cursor doesn't jitter or lag behind.
- It's more forgiving in dim rooms and at an angle.
- A small readout under the title shows the tracking rate, plus "SHOW ME YOUR HAND" when it can't see one.

- **Holo Hands:** open it from the phone's **🖐 HOLO HANDS** or the laptop's **🖐 Holo Hands**. The camera fills the
  screen and a neon skeleton follows your hand. Two ring menus float beside you: **OPEN** (Holo Lab, Sims, Trailer,
  Map) and **MODEL** (the core, a globe, a body figure, a crystal).
  - Point at a button and **pinch**, or hold your finger there for a moment, to choose.
  - **Pinch the hologram** to grab and spin it.
  - **Pinch with both hands** to make it bigger or smaller.
  - **Swipe** an open hand to switch models.
- **It works on the laptop webcam and the phone's front camera (#46).** Hand tracking runs on the device and the
  picture never leaves it. It needs the internet the first time to load. With no camera, your finger or mouse works
  the same way.
- **Throw it (#47):** flick a grabbed hologram upwards, or tap **⇪**, and it flies to your other screen, which
  catches it. In the phone's Holo Lab, **⇪ TO LAPTOP** sends what you're looking at to the laptop.
- **Living notifications (#48):** your phone's notifications fly onto the laptop as hologram cards, never bank apps
  and never codes. Swipe one away with the mouse or a hand swipe (✋ Gestures), or click it to catch up.

## More 3D (#15, #16, #17, #26)

- **Tilt to look (#15):** in the Holo Lab and Holo Sims, tilt the phone and the hologram shifts like a real 3D
  object.
- **Hologram on your table (#16):** tap **📷 AR** and the camera becomes the background. The hologram floats over
  your desk and stays put as you move the phone around.
- **Your day in 3D (#17):** Holo Lab → Singapore shows today's real path as a glowing light trail, cyan in the
  morning, through gold, to pink at night. A comet replays your day, with your step count.
- **Live wallpaper (#26):** the JARVIS core breathes on your home screen, with orbiting arcs, drifting particles
  and a ripple where you touch, in your suit colour. It only animates while you can see it. Set it from the phone's
  setup page (Live wallpaper).

## The 3D core (#18)

The glowing core on the phone, in solo mode and on the laptop dashboard is now a living 3D hologram of about 12,000
particles:

- **Idle:** it breathes.
- **Listening:** it ripples inward in cyan.
- **Thinking:** it swirls purple.
- **Speaking:** it pulses with JARVIS's actual voice, throwing sparks on loud words.

It takes each agent's colour and your suit theme. On a device without 3D graphics, the classic reactor shows instead.

## The trailer: show off (#8 to #14), version 3

A 3D film starring you, with an original soundtrack that's made live: drums, bass, arpeggios, risers, braams, and
a silence before every drop. There are no copyrighted tracks, so you can post it.

**Version 3 is rebuilt so that the voice drives the edit.** Every line JARVIS says is loaded before the film starts
(a progress bar shows "Warming up the voices… 3/9"). Each line's real length decides how long its shot lasts, and
the cut lands on the next beat after the line finishes. Nothing is cut off or runs late.

- **Titles match the voice word for word.** He says "And I never work alone." and that's the title.
- **Captions light up word by word** as each line is spoken (karaoke style), on a dark band so they're always readable.
- **The music ducks** under the voice.

**Smooth on phones too:**
- The particles move on the graphics chip.
- The 3D and the titles are two layers, with no copying every frame.
- Glowing titles are drawn once, not every frame.
- Quality adapts by itself (resolution, then particle count) to hold a smooth frame rate.

**The voice:**
- With the laptop: JARVIS's real voice, the cinematic Gemini one, always the same voice for a character.
- On the phone alone: the Gemini voice through your free key. Each line is remembered on the phone, so it costs
  nothing the second time.
- If Google's free allowance is used up: each agent's own backup voice.

**The film:**
- a data-rain cold open that fades up, then a drop where the J.A.R.V.I.S logo slams in with a shockwave ("Just A
  Rather Very Intelligent System")
- a montage: "I listen." (the core), "I learn." (your city with light trails), "I plan." (life sims), "I protect."
  (a body scan), "And I never work alone." (the team flying in), "Wherever you go, I go." (phone ⇄ laptop ⇄ cloud
  data beams), and your photos ("This is your story.") or "I run the numbers."
- stats on the beat, warp speed, and a slow-motion "And when you need me most..."
- a charge-up, then the final drop: **STARRING** with your name in particles. JARVIS says it.
- the end card "I'm always online, Sir." (with your dedication), then a post-credits scene with FRIDAY

**Options:**
- **The look:** bloom glow, chromatic aberration that pumps with the kick, glitch slices, camera shake, film grain
  and widescreen bars.
- **Styles:** ⚡ EPIC (gold, 120 BPM), 🔥 HYPE (neon magenta, 140 BPM), 🖤 NOIR (silver and red, 96 BPM).
- **Cuts:** 🎬 FULL (about a minute) or 📱 REEL (about 45 seconds, always vertical 9:16, for Instagram and TikTok).
- **Make it yours:** add up to 6 of your photos (they appear as floating holograms) and a dedication ("for Mum"),
  which JARVIS says at the end.
- **⬇ PLAY & SAVE VIDEO** records it, and the laptop sends it to your phone on Telegram, ready to post.
- **Updates by itself on the phone:** it's refreshed from the laptop, or from GitHub when the laptop is away, with
  no reinstall.

- It only shows safe-to-share things: counts, places (home shows as "HQ") and the team. Never messages, tasks or
  money.
- **Phone:** tap **🎬 SHOW OFF** (works with the laptop off too). **Laptop:** say "show off mode".

Also: pages open and close with a holographic iris (#13), and the app opens with a 2-second boot sequence (#14).

## The phone is the full JARVIS

- **The team:** start with a name ("Friday, …", "Zeus, …") and that agent answers in their own voice, on the laptop
  and in the phone app (solo mode too).
- **Premium voices with the laptop off:** with your Gemini key, the phone speaks in the team's own Gemini voices.
  If Google is busy, the phone's voice takes over.
- **Holo Lab without the laptop:** 🌐 HOLO LAB in solo mode opens your holograms from the phone's offline copy.
- **Your day, glowing:** ✨ MY DAY draws today's trail (cyan in the morning, through gold, to pink at night) with your
  steps, distance and places. It works with the laptop off.
- **Steps on the body hologram:** Holo Lab → Body. Your legs light up with today's steps, and a ring of light at your
  feet shows the count.
- **Point and explain:** 📷 EXPLAIN opens the camera with a JARVIS vision HUD. Explain, translate, read it out, or ask
  anything about what you're pointing at. Saying "what is this?" opens it too.
- **Guest mode:** 🎭 GUEST in solo mode, or "guest mode on" anywhere. JARVIS charms your friends and keeps everything
  private.
- **Suit themes on the phone:** REMOTE → SUIT on the phone sets the theme for both screens. Solo mode uses it too.

## Bank apps and the autopilot

DBS/POSB digibank and other bank apps refuse to run while **any** app has Android's Accessibility switched on, and
JARVIS's autopilot uses it. JARVIS never touches bank or finance apps, but the bank can't know that. So the moment
you open a bank or finance app, the autopilot **switches itself off** and leaves a notification. Close and reopen the
bank app and it works. Turn autopilot back on from that notification, or the phone setup page, when you want it.

## Faster replies, and talking like a real conversation

- **Instant answers:** "what time is it", "what's next", "my tasks", "how many steps", "phone battery", "weather",
  "where am I", "hi Jarvis" and "thanks" are answered from JARVIS's own data in a blink, with no AI round trip
  (laptop, phone app and Telegram).
- **Quick model for spoken questions:** voice questions go to the fastest Claude model, kept warm
  (`JARVIS_VOICE_MODEL`, default `haiku`; set `sonnet` for more depth). With your Gemini key in fast mode, spoken
  questions skip Gemini's silent thinking step.
- **Speaks while writing:** the first sentence is spoken as soon as it's written, on the laptop and the phone,
  including questions asked on the phone.
- **Cut in (#21):** start talking while JARVIS is speaking and he stops and listens. Echo cancelling keeps his own
  voice from triggering it. Turn it off with `localStorage["jarvis-bargein"] = "off"` in the browser.
- **Keep talking (#22):** after he answers, you have 8 seconds for a follow-up without saying "Jarvis" or tapping.

## The phone works all night, screen off

The phone's JARVIS keeps working with the screen off. It wakes about every 10 minutes even in deep sleep, and
every couple of minutes while the phone is in use. When the laptop has been unreachable for 3 minutes, the phone:

- **answers your Telegram messages and voice notes** (replies start with 📱). When the laptop is back it takes the
  bot over again, and nothing is answered twice.
- **sends the morning brief** at your usual time and a **night review** at 22:30 (steps, places, tomorrow's first plan).
- **speaks up first:** "Time to go, Sir" before your next plan (with the bus or Grab), and "Rain on the way".

Always, laptop or not:

- **bus alerts:** stand at a stop and the next buses there pop up, live (needs `/lta` once).
- **"What did I miss?"** sums up your notifications, never bank apps and never codes.

**Nightly self-check:** at 03:40 JARVIS checks the database, disk, phone link, the phone's offline copy, Telegram,
Gemini and hearing. It fixes what it safely can, and messages you only if something needs you. Say "system check"
any time.

Keep "Background" allowed on the phone's setup page, or Android may pause JARVIS while you sleep.

## Holograms everywhere (laptop and phone)

- **🌐 HOLO LAB** (phone home screen, or 🌐 Holo on the laptop): your week, Shaabaz, body, money, Singapore,
  diagnostics and trophies as 3D holograms. Drag to spin, pinch to zoom.
- **🧪 HOLO SIMS** (phone home screen, 🧪 Sims on the laptop, or 🧪 HOLO SIMS in solo mode): 8 live 3D what-if
  simulations with sliders and a time scrubber: life, gig pricing, wedding guest flow, meal plan to body, exam
  predictor, tomorrow played, money future, and wedding day run. They're built into the phone app too, so they work
  with the laptop off. For now they run on sample numbers; your own data comes next.

## ZEUS's job hunt: 50 applications a day

ZEUS lines up the jobs, matches them to you and writes the letters. You just tap.

1. **Every morning at 7:50** (and again after lunch) ZEUS finds fresh jobs:
   - MyCareersFuture's public job search, for the roles you want.
   - Your own job-alert emails from JobStreet, LinkedIn, Indeed, Glassdoor and FastJobs. Switch alerts on in each
     app: more alerts means more jobs.
2. **He ranks them against your resume:** a fit %, plus one line on why you fit. Best first. Things you said to avoid
   are dropped.
3. **He writes a short cover letter for each job**, using only what's in your resume.
4. **🎯 JOB HUNT** (on the phone's home screen, or `/jobs.html`) shows one job at a time:
   - **⚡ APPLY** (or swipe right) copies the letter, opens the job (the JobStreet or LinkedIn app if installed),
     logs it in ZEUS's tracker with a follow-up reminder a week later, and slides in the next one.
   - **✕ SKIP** (swipe left) and **★ LATER** are there too, with UNDO for 4 seconds.
   - A ring counts today's applications against your target (50).
5. **Email applications go out by themselves when you say so.** Jobs whose ad says "send your CV to hr@…" appear in
   **📧 REVIEW & SEND ALL**. One tap sends every one with its own cover letter and your CV attached. That tap is your
   yes: nothing is sent without it.

**Get started:**
- Send your CV as a PDF (or Word file) to the JARVIS bot on Telegram with the caption **resume**. ZEUS reads it and
  starts hunting.
- Tell him what you want: "ZEUS, I want marketing or events roles, at least $2,800, no sales", or "50 a day".

**Why you still tap Submit on JobStreet and LinkedIn:** both ban accounts that apply with bots, and losing your
account would hurt your chances. So ZEUS does everything up to that tap. MyCareersFuture needs Singpass, so that one's
yours too.

## VERONICA's books: your monthly P&L from bank alerts

Turn on email alerts in your bank apps (DBS/POSB, OCBC, UOB, Citi, Trust, GXS, PayLah, GrabPay, PayPal, Revolut,
YouTrip...). From then on VERONICA keeps your books by herself. Every hour she reads the new alert emails in Gmail
and books each one as a transaction:
- **Money in** ("You have received SGD 2,000.00": salary, transfers, refunds)
- **Money out** ("A transaction of SGD 45.90 ... at GRAB*FOOD"), with the merchant and a category: food, groceries,
  transport (Grab rides, Gojek, MRT), clothes, shopping, subscriptions, bills, entertainment, health, education,
  travel, grooming, transfers or other

**Getting your P&L:**
- Ask "VERONICA, what's my P&L?" (or "how much did I spend on Grab this month?") for money in, money out by
  category with %, the net ("you kept 24%"), top spots, biggest buys, vs last month, and your pace for the month.
- **On the 1st** of every month she sends last month's P&L to Telegram, puts it on the dashboard and says the headline.
- **Holo Lab → Money** shows it in 3D: money in, out and net on top, a glowing column per category.
- **On the phone with the laptop off:** "what's my P&L?" works from the last sync.

**Teaching her:** "VERONICA, Koufu is food" or "Uncle Tan is rent". She remembers it and fixes that month's entries.
Cash spends you mention ("I spent $12 on lunch in cash") are logged too.

**Safe by design:**
- Only emails from banks and payment services are read.
- One-time codes are never read, and declined or failed transactions and statements aren't counted.
- Transfers between your own accounts don't count as spending.
- Card and account numbers are never stored, only the amount, merchant, category and bank name.
- JARVIS still can't open bank apps or sites, and never moves money.
- Needs: `/email` sent to the bot once (Gmail with an app password).

## JARVIS tells you first: emails and WhatsApp

You don't have to ask. When an email or a WhatsApp message arrives on the phone, JARVIS says it out loud within a
few seconds, as your filter. Things that arrive together are summed up together. For example:

> "Sir, Grab replied about your interview: it's moved to 3pm Friday. Plus two promos, nothing urgent."

- **What gets flagged:** deadlines, interviews and jobs, school or work, bills, family, and anything that needs a reply.
- **What gets lumped together:** promos, newsletters and automated mail, in a few words.
- **Every time:** the same summary also appears as a notification, with a **🔇 Stop announcing** button.
- **Quiet:** when the phone is on silent or vibrate, during a call, and from 11pm to 7am, it's a notification only.
- **Voice commands:** "stop announcing" / "announce messages" to switch it, and "what was that?" to hear it again.
- **What's included:** emails (Gmail, Outlook and others) and WhatsApp direct chats. Telegram and group chats aren't
  announced.
- **Nothing is "hidden" any more:**
  - Every email is read and summed up.
  - Only real one-time codes (OTPs, PINs with a code) are kept out.
  - Bank emails come through as masked alerts (card and account numbers show only the last 4 digits).
  - Bank apps' own notifications stay off limits.
  - Before, any email that just mentioned a word like "bank", "pin" or "boost" was hidden.
- **Gmail tip:** in Gmail → Settings → your account → Notifications, choose **All**, so every email makes a
  notification JARVIS can hear.
- **Needs:** Notification access for JARVIS (setup page: "Smart replies & notifications").

**Hearing you right:**
- JARVIS now uses Google's own speech recogniser, the same one as Gboard voice typing, instead of the phone maker's.
- It's given the team's names and yours as hints.
- When the recogniser isn't sure, JARVIS's brain sees its other guesses and goes with what you most likely meant.

## The phone app updates itself

You never have to download and install the app again. About once an hour (and whenever you open it) the app checks
the latest GitHub release and, if there's a newer build, downloads and installs it by itself. On Android 12 and later
this is silent after the first self-update; the first time (or on phones that insist) you get a notification:
**tap Update, done**. Say "update app" to check right now. Allow it once on the setup page (**Self-updates** →
"Install unknown apps" for JARVIS). Most changes don't even need that: the screens and the phone's own JARVIS brain
(solo mode) are refreshed from the laptop automatically.

**One-time set-up (needed for this to work):** Android only installs a new version over the old one if both are
signed with the same key. Double-click **app-signing.bat** on the laptop (or run `python -m jarvis signing-key`):
it makes a permanent key (backup in `~/JARVIS/Signing`, never in the repository) and walks you through adding the two
GitHub secrets (`JARVIS_KEYSTORE_B64`, `JARVIS_KEYSTORE_PASSWORD`). Install the next build by hand one last time
(uninstall the old app first); from then on it updates itself.

## Solo JARVIS: the phone works without the laptop

When the laptop is off, asleep, in your bag or in another country, the phone app becomes JARVIS by itself, over
Wi-Fi or mobile data. It switches on its own (within about 8 seconds of the laptop not answering, and also mid-use:
if the laptop disappears while its page is open, the phone takes over and answers what you just said) and shows a
**📱 SOLO** badge. When the laptop is back, tap **💻 LAPTOP IS BACK · SWITCH**.

What works on the phone alone:

- **Talking:** tap the core or use 👂 Hands-free. It thinks with your free Gemini key straight from the phone, and
  knows your memories, tasks, calendar (2 weeks ahead), saved places and the team.
- **Reminders** ring on the phone on time, even with no signal. Your laptop's own reminders are copied to the phone
  as a backup and only ring there if the laptop is unreachable, so you never get two.
- **Directions** on a glowing map inside JARVIS, with when to leave, walk and drive times and the Grab price. In
  Singapore you also get real bus and MRT journeys with live bus arrivals (after `/onemap` and `/lta`). Overseas it
  uses OpenStreetMap.
- **Weather, where am I, web look-ups, notes, tasks, calendar.**
- **Phone powers:** call, alarm, timer, torch, volume, music, open apps, camera, email drafts. Banks and finance apps
  stay off limits, and it never messages anyone by itself.

- **A normal conversation:** after JARVIS answers, the mic opens by itself for 8 seconds, so just keep talking (no
  tapping). Say "that's all" or "bye" to end it, or tap the core to cut JARVIS off. It also stops listening about
  a second after you stop talking, and answers easy things (time, date, next plan, tasks, steps, thanks) instantly
  on the phone. Longer replies start speaking after the first sentence is voiced.
- **Cinematic voices:** every agent has their own accent, attitude and emotion (JARVIS the dry British butler,
  FRIDAY the cheeky Irish one, PEPPER low and velvety, VERONICA smoky film-noir, EDITH a silky spy-movie handler...),
  softer late at night. Same cast on the laptop and the phone.
- **What did I miss / any emails?** JARVIS reads the phone's notifications, Gmail included (sender, subject and
  preview), plus messages, and sums them up. Bank apps and codes are never kept. This needs **Notification access**
  for JARVIS (Settings → Notifications → Device & app notifications); if it's off, JARVIS opens that page for you.
  To read your whole inbox (not just notifications) send `/email` to the bot once.

Everything it does alone (things to remember, tasks, events, notes, reminders and the conversation) syncs back to
the laptop the next time it's on, so both stay the same JARVIS.

How it keeps up to date: whenever the laptop is reachable, the app copies a "solo pack" (what JARVIS knows plus the
free keys its brain needs) every 20 minutes. The keys live only in the app's private storage and are only sent to
their own services (Google, OneMap, LTA). Without a Gemini key it runs in basic mode (reminders, directions,
weather, calls, apps, tasks). Send `/gemini` once for full conversations.

What still needs the laptop: anything on the laptop itself (its files, screen and apps), the night shift, and the
Telegram bot.

## Talk from your phone, one voice answers

Your phone's mic hears you much better than the laptop's, so use it as JARVIS's ears:

- **Phone app:** tap the reactor and talk (or turn on 👂 Hands-free and start with "Jarvis…").
- **Telegram:** send a voice note to your JARVIS bot.

Every reply shows on **both** the phone and the laptop, but only **one** of them reads it out, so two JARVISes
never talk over each other. The **laptop talks by default**. Switch it with:

- the **💻 LAPTOP TALKS / 🔊 PHONE TALKS** button at the top of the phone app,
- the **🔊 Voice** button on the laptop (it shows 📱 Phone speaks when the phone has the voice),
- or say **"speak on my phone"**, **"speak on the laptop"**, or **"mute both"**.

Telegram voice notes follow the same switch: a voice note back when the phone talks, read aloud by the laptop
otherwise (the text always comes to Telegram).

**Hearing:** with your free Gemini key (`/gemini` on Telegram), voice notes and the laptop's 🎙 are written down by
Google's speech model, which knows Singapore English and your names and places. If Google can't be reached,
the laptop's own engine takes over, so it never goes silent. `JARVIS_GEMINI_HEARING=off` keeps all hearing on
the laptop only.

## Stark mode

- **Snap twice** (or clap twice) near the laptop and JARVIS answers "Yes Sir?" and listens. If you've been away 3+ hours, he
  gives you the welcome-home briefing instead. Snaps are picked out by their crisp "tick", so talking and music
  don't trigger it (`JARVIS_CLAP_SENSITIVITY` above 1 makes it more eager, below 1 calmer). Say **"Jarvis, I'm home"** for the same briefing any time.
- **Wake-up:** the morning brief includes the weather (rain timing too), and can open your music
  (`JARVIS_WAKE_MUSIC`).
- **Job hunter:** every night at 01:30 ZEUS searches for new roles that fit your profile, tracks the best few,
  writes cover letters for the top 2 and asks you one yes/no in the morning.
- **VoiceStudio voices:** if VoiceStudio is running, briefings and voice notes use its emotional voices. If your
  laptop is too slow for live chat, live replies automatically use the quick voices.

## Lecture & meeting recorder (ATHENA)

Say **"Jarvis, record this lecture"** (or tap **● Record on laptop** in the Autopilot tab), and **"stop recording"**
at the end. The laptop transcribes it for free (nothing leaves the laptop), then ATHENA writes study notes:
summary, key points with timestamps, exam hints, to-dos and self-test questions. To-dos become tasks, dates
become calendar events, and the notes arrive on Telegram with the full transcript.

Recorded on your phone instead? Send the audio file to your Telegram bot (up to 20 MB, caption it with the title),
or upload any size in the app: Autopilot → Lectures → **Upload recording**. Ask later: *"Athena, what did the
FIN302 lecture say about hedging?"*

## Google Calendar sync

Open the dashboard → Autopilot → Google Calendar → **set up**, and follow the 6 steps (about 5 minutes, once):
you paste a small script into your own Google account and give JARVIS its link. No Google Cloud project and no
passwords. After that JARVIS reads your real calendar every 10 minutes, and events the agents add appear on your
phone's Google Calendar.

## Business kit (PEPPER, for Shaabaz Weddings & Events)

Copy `business.example.md` to `business.md` and fill in your packages and prices. Then:
- *"Pepper, new enquiry: Priya, wedding 14 Feb, 300 pax at Raffles, budget 15k"* logs the client with a next step.
- *"Pepper, quote Priya the gold package plus a photo booth"* makes a PDF quotation (sent to your phone); she
  offers to e-mail it to the client, and you approve first.
- *"Pepper, Priya confirmed"* builds the planning checklist as dated tasks and puts the event on your calendar.
- Client enquiries in your inbox are passed to PEPPER automatically, with ready replies to tap.

## Setting up the extras

**E-mail (Gmail).** Turn on 2-Step Verification on your Google account, then create an App Password at
<https://myaccount.google.com/apppasswords>. In `.env`, set `JARVIS_SMTP_USER` to your Gmail address,
`JARVIS_SMTP_PASSWORD` to the 16-letter app password, and `JARVIS_REPORT_EMAIL_TO` to your address.

**Telegram (your phone remote).** In Telegram, open **@BotFather**, send `/newbot`, choose a name and a
username ending in `bot`. Copy the token it gives you into `JARVIS_TELEGRAM_BOT_TOKEN` in `.env`. Start JARVIS,
open your new bot in Telegram and send `/start <code>`. The code is shown in the black window and in the
dashboard's Autopilot tab. That links the bot to you only.

**WhatsApp (off, not recommended).** A bridge for your personal WhatsApp exists in `bridge/`, but it uses an
unofficial link that WhatsApp can ban numbers for. It stays off unless you set `JARVIS_WHATSAPP=on`.

**Android phone control (optional).** Phone and laptop on the same Wi-Fi. Install Android platform-tools (ADB)
from <https://developer.android.com/tools/releases/platform-tools>. On the phone: Settings → About phone → tap
*Build number* 7 times → Developer options → **Wireless debugging** → **Pair device with pairing code**, then on
the laptop run `adb pair <ip>:<port>` with that code. Put the IP:port shown under *Wireless debugging* into
`JARVIS_PHONE_ADB`. EDITH can then check battery, open apps and websites, and take screenshots of the phone.

**Custom voices.** Every agent has its own voice. Free: click **🎚 Voices** in the dashboard and choose a voice,
pitch and speed per agent from the voices on your computer. Premium: put an `ELEVENLABS_API_KEY` in `.env`
(from <https://elevenlabs.io>) and each agent speaks with its own realistic AI voice. Swap any of them with
`JARVIS_VOICE_<AGENT>=<voice id>`, including a voice you cloned yourself. Spoken lines are cached, so the
boot roll-call only costs credits the first time.

**Start automatically (Windows).** Double-click `install-autostart.bat` once and JARVIS starts every time you
log in.

**Laptop control** works out of the box. EDITH can open apps and sites, take screenshots, find, read and send files,
lock the screen, and save documents in `~/JARVIS`. Terminal commands always ask you first.

## Layout

```
jarvis/
  agents.py     the agent roster (roles, colours, tools, effort)
  engine.py     Claude tool-use loop, delegation, chat memory
  tools.py      records: tasks, calendar, notes, goals, habits, career, money, reports
  actions.py    real-world tools: WhatsApp, e-mail, contacts, routines, laptop and phone control
  channels.py   e-mail (IMAP/SMTP), WhatsApp bridge client, outbox approval policy
  devices.py    laptop and Android (ADB) control
  scheduler.py  autopilot: briefs, reports, watchdog, night shift
  server.py     API + live event stream for the dashboard
  store.py      SQLite storage
  notify.py     report delivery (Telegram, e-mail)
  telegram.py   Telegram bot: remote control, approvals with buttons
  guard.py      banking block, OTP filter, number masking
  brain.py      brain choice (Claude plan / API / Gemini) and the pause switch
  brains.py     Claude Code and Gemini brains
  voice.py      agent voices: free natural voices (edge-tts) or ElevenLabs
  stt.py        speech-to-text for voice notes (faster-whisper, runs locally)
bridge/                   optional WhatsApp bridge (off by default)
web/command-centre.html   the HUD dashboard (voice in/out, live activity, Outbox approvals)
web/call.html             📞 live voice call with JARVIS (phone app)
tests/                    offline tests (pytest)
```
