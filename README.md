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
- **Voice typing anywhere (laptop):** hold **Right Alt** (or the **Copilot key** ✦, or Right Ctrl), talk, let go: JARVIS types it into whatever app has the
  cursor. Start with "Jarvis, ..." to give an order instead. Understood on the laptop itself; never types into
  banking windows. Change the key with `JARVIS_DICTATE_KEY` (auto, ralt, copilot, rctrl, f8, f9, capslock) or `JARVIS_DICTATE=off`.
- **Email:** on the setup page, enter your Gmail address and a Gmail app password (the page links to Google's
  page for making one; it needs 2-Step Verification). JARVIS checks it works, saves it on the laptop, and restarts.
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

## Stark mode

- **Clap twice** near the laptop and JARVIS answers "Yes Sir?" and listens. If you've been away 3+ hours, he
  gives you the welcome-home briefing instead. Say **"Jarvis, I'm home"** for the same briefing any time.
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
