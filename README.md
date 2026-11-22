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

## Bank notifications (read-only)

VERONICA reads your bank's **transaction alert e-mails** (turn on e-mail alerts in your bank's app) and sends a
**weekly money report** on Sundays: every transaction, totals, anything unusual. Card and account numbers are
masked to the last 4 digits. OTP / PIN / password e-mails are never shown to any agent, and agents still can't
open bank apps or sites or move money.

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
