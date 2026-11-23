# Next time (owner's wish list, not built yet)

Pick-up list for the next session. Remove an item when it ships (and add its Training mission, see CLAUDE.md).

## Owner to-dos (after exams)
1. Restart the laptop, then send `/update` on Telegram (check: `/installapp` replies with the app link).
2. `/installapp` -> install the newest phone app (Play Protect off for a minute, then back on).
3. Phone: say "setup" -> ALLOW NEXT, including "Location: all the time".
4. `/gemini` (fast mode) and `/email` (Gmail).
5. Try "show me my map" and Training Mode.

## Standing rule from the owner: JARVIS and the agents repair and upgrade themselves EVERY NIGHT
- **Nightly self-repair (fully automatic):** systems check of everything (version, phone link, location, Telegram,
  Gemini, email, calendar, voice, mic, disk, jobs); fix what it can (restart the phone link, retry the update,
  clear stuck jobs, re-index files); morning one-liner only if something still needs the owner.
- **Nightly self-upgrade:** (a) automatic: pull the newest version, tune each agent from the day's feedback
  (team_tuneup), learn new rules from corrections, refresh prompts and memories; (b) new abilities the agents write
  for themselves are tested in a sandbox and switched on automatically when safe and low-risk; anything that touches
  money, messages to people, shell access or security still waits for the owner's yes. Every change is logged and can
  be undone ("Protocol Zero").
- **Access control (owner said yes):** clearance levels L1-L5, voice ID for sensitive commands, face ID owner mode on
  the laptop, per-agent autonomy dial, Protocol Zero kill switch, "what did you do without me" audit log, intruder
  alert.
- **Named protocols:** create by voice ("Create Exam Protocol: ...") and run ("Initiate Exam Protocol").

## Chosen for the next build (owner picked these)
- **JARVIS learns new skills by itself:** "Jarvis, learn to track my parcels" -> writes the new tool, tests it in a
  sandbox, shows it, adds it after the owner's yes.
- **Agents run whole projects for days:** multi-day missions (e.g. PEPPER plans the Tan wedding) with a live mission
  timeline on the HUD and approval checkpoints.
- **Life simulator:** "what if I skip gym and take 2 more gigs?" -> 4-week projection of energy, grades, money,
  stress as a holo chart.
- **Instant local brain:** small on-laptop model for sub-second replies (works offline); big brain for hard ones.
- **Throw windows between devices:** swipe a laptop window to the phone, flick the phone at the laptop.
- **Smart day planner:** rebuilds the day around travel time (MRT/bus/drive), rain, MRT delays and energy; moves
  flexible tasks, warns about clashes, and nudges "leave in 10 min" (builds on route planning + leave-now alerts).

## GPS upgrades chosen (owner picked these)
- **Smart leave alerts 2.0:** compare live location vs the next event's place; "you're at Bugis, the wedding is at
  Raffles in 25 min, leave now, MRT is fastest" (build on butler.leave_now_check + explore + chatter limits).
- **Steps & distance from GPS:** daily km walked from the location history; STEVE celebrates streaks.
- **Gym auto-check-in:** arrive at the saved gym -> STEVE starts the workout log; leave -> asks what you trained
  (location_magic already prompts on leaving; add the start + the log flow).
- **Routine detective:** learn usual arrival times (campus, gym, home); flag unusual days kindly; weekly insights.
- **Venue scout mode:** at a hall/hotel, PEPPER pulls past events there, capacity, notes and crew contacts.

## Aesthetics chosen (owner picked these; keep the neon techy look)
- **Living map:** Explorer map tint follows time of day (golden sunset, neon night) and real rain.
- **Cinematic transitions:** "suit-up" panel wipe + sound when opening Holo Lab, the map, agent rooms.
- **Glass panels:** frosted-glass cards with subtle depth/parallax (mouse on laptop, tilt on phone).
- **Theme designer:** pick any neon colour; HUD, map and phone app recolour to match.
- **Sound design pack:** richer UI sounds, holo whooshes, per-agent message chimes.

## Automation chosen
- **Bill alerts:** read "payment due / bill / statement ready" emails (email only, never bank apps; amounts masked
  as usual) -> reminder 3 days before the due date + on the day; monthly list of upcoming bills for VERONICA.
- **Receipts -> spending:** receipt/order emails logged as spending automatically (merchant, amount, category).
- **Subscription price changes:** spot "your price is changing" emails -> "it went up by $3" alert.
- **Payday mode:** salary/payout email -> savings goal reminder + weekly budget reset (VERONICA).
- **Refund tracker:** "refund initiated" emails tracked until the "refund completed" one arrives; nudge if late.
- **Parcel tracker:** shipping emails (Shopee, Lazada, Amazon, couriers) -> HUD delivery card, "out for delivery
  today" alert, delivered tick.
- **Gym auto-log:** GPS gym visits logged as workouts automatically; STEVE's weekly plan adjusts.
  (All money items read email only, never bank or finance apps.)

## Scanners & visuals chosen (only the NEW parts; base modes already exist in web/vision.html + jarvis/vision.py)
- **Food scanner+:** Meal mode exists -> add a neon macro overlay (protein/carbs/fat rings) and auto-log to STEVE.
- **Outfit scanner+:** Outfit mode exists -> add wardrobe memory (items seen, when worn, suggestions from owned clothes).
- **Document scanner+:** reading exists -> add clean PDF output (crop/contrast) and auto-create events/tasks from dates.
- **Price scanner (new):** point at a product -> name it -> compare via phone_shop links (Shopee/Lazada/Amazon).
- **Venue scanner (new, Shaabaz):** AR measuring grid + capacity estimate + layout overlay, linked to the floor planner.
- **Hologram projector+:** gestures already open/close/switch Holo views -> add grab-to-spin, pinch-to-zoom,
  point-to-select and a full-screen projector mode.
- (Object ID already built: Vision "Scan"/"Ask" with labels; nothing to add.)

## Ideas offered, not built yet
1. Auto car mode when the phone connects to the car's Bluetooth (reads messages aloud).
2. Deal watch: daily Shopee/Shein price checks, alert on a price drop.
3. Shared clipboard both ways (copy on the phone, paste on the laptop and back).
4. "Continue on laptop": whatever the phone is reading opens on the laptop.
5. Auto-lock the laptop when the phone walks away.
6. Phone wind-down at bedtime (dim, Do Not Disturb, TikTok limit nudge).
7. Missed calls summary ("who called me?", needs call-log access).
8. Instagram/TikTok autopilot: post an approved story or reel with a written caption.
9. Faster first words in fast mode: stream Gemini replies so speech starts before the whole answer is ready.
