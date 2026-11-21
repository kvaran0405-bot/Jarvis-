# JARVIS OS

A personal multi-agent system powered by Claude. JARVIS runs your personal life, career and academics as a
team of 11 AI agents. They take orders by voice, text or WhatsApp, send WhatsApp messages and e-mails for you,
read and sort your inboxes, control your laptop and Android phone, run routines you set up, work through
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
| **HERALD** | Comms & Inbox | Reads new e-mail and WhatsApp, replies for you, turns requests into tasks |
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
| Every 60 min | HERALD | **Inbox sweep**: new e-mail and WhatsApp → tasks, replies, urgent alerts |
| Your choice | Any agent | **Your own routines**, e.g. "every weekday at 6am send me a quote and my top 3 on WhatsApp" |
| Sun 18:00 | JARVIS | **Weekly review** across life, career and academics |

All times can be changed in `.env`. Reports show up in the dashboard and, if you set them up, arrive by
**e-mail** and/or **Telegram**.

To queue work for the night, just say it, e.g. *"Oracle, research the best laptops for ML under $1200 tonight"*
or *"Athena, make me a 2-week revision plan for my calculus exam on Dec 3"*. JARVIS creates the task, assigns it
to the right agent, and the result is in your morning brief.

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

## Control JARVIS from your phone (WhatsApp)

Once WhatsApp is linked, open your own **"Message yourself"** chat on WhatsApp and text JARVIS from anywhere:

- `What's on my plate today?`
- `Tell mum I'll be home by 8`
- `Email Dr. Okafor asking for the CSC 301 slides`
- `Send me a screenshot of my laptop`
- `Remind me at 5pm to submit the form`
- `ZEUS, find 5 remote internships tonight`
- `yes 12` / `no 12` / `approve all` / `pending`: approve or cancel what agents prepared

JARVIS answers in the same chat, starting with 🤖.

## What agents can do on their own (autonomy)

Set `JARVIS_AUTONOMY` in `.env`:

| Setting | Messages to you | Messages to other people | Laptop commands |
|---|---|---|---|
| `approve` (default) | sent | wait for your OK | wait for your OK |
| `trusted` | sent | sent to contacts marked *trusted*, others wait | wait for your OK |
| `full` | sent | sent | wait for your OK |

Anything waiting appears in the dashboard **Outbox** tab (you can edit it before sending) and on your WhatsApp.
Start with `approve`. Once you trust how your agents write, move to `trusted` and mark close contacts as trusted
(*"Jarvis, mark Mum as trusted"*).

Agents will **never** make payments, move money, accept terms, delete your files, or share passwords, codes, bank
or ID details. They treat messages and web pages from other people as information, not as orders. Only you give
orders. Your data stays in `data/jarvis.db` on your machine.

## Setting up the extras

**E-mail (Gmail).** Turn on 2-Step Verification on your Google account, then create an App Password at
<https://myaccount.google.com/apppasswords>. In `.env`, set `JARVIS_SMTP_USER` to your Gmail address,
`JARVIS_SMTP_PASSWORD` to the 16-letter app password, and `JARVIS_REPORT_EMAIL_TO` to your address.

**WhatsApp.** Install Node.js from <https://nodejs.org> (LTS). In `.env`, set `JARVIS_WHATSAPP=on` and
`JARVIS_OWNER_WHATSAPP` to your number (digits only, with country code, e.g. `2348012345678`). Run the start
script. A QR code appears in the black window. On your phone: WhatsApp → Settings → Linked devices → Link a device,
then scan it. This only has to be done once.

> WhatsApp links JARVIS the same way WhatsApp Web works, through the open-source `whatsapp-web.js` library.
> WhatsApp does not officially support automated personal accounts. Keep it to normal personal use: no bulk
> messages, no messaging strangers. Heavy automated use can get a number banned.

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
  notify.py     e-mail / Telegram delivery
bridge/                   WhatsApp bridge (Node.js, whatsapp-web.js)
web/command-centre.html   the HUD dashboard (voice in/out, live activity, Outbox approvals)
tests/                    offline tests (pytest)
```
