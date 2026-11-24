# JARVIS in the cloud, 24/7, free (#7)

Your laptop is off most of the day, so JARVIS's main brain moves to a small always-on computer in the cloud. Oracle
Cloud's **Always Free** tier gives you one for $0, for good. The laptop becomes JARVIS's **satellite**: when it's
on, the cloud JARVIS uses it for laptop-only jobs (its screen, files, apps, approved commands, lecture recording).
Telegram, the night shift, reminders, routines and the phone link run in the cloud all the time.

Everything travels over your own private **Tailscale** network: your phone, laptop and the cloud server can see each
other, and nobody else can. Your keys go from the laptop to the server over that private network and never touch
GitHub.

## 1. Get the free server (about 15 minutes, once)

1. Go to **cloud.oracle.com/free** and sign up.
   - Choose **Singapore** as your home region.
   - They ask for a card to check you're a real person. Always Free resources cost nothing. Never click
     "Upgrade to paid".
2. In the Oracle console, go to **Compute → Instances → Create instance** and set:
   - **Image:** Ubuntu 24.04 (Canonical).
   - **Shape:** Ampere, VM.Standard.A1.Flex, 2 OCPUs and 12 GB memory. That's inside the free allowance. If it says
     "out of capacity", try 1 OCPU and 6 GB, or try again later.
   - **SSH keys:** "Generate a key pair" and **download the private key**. Keep it safe.
3. Click **Create**. When it's running, copy its **Public IP address**.

## 2. Put the server on your Tailscale network (2 minutes, once)

On the laptop, open **PowerShell**, then:

```
ssh -i C:\path\to\the-key-you-downloaded.key ubuntu@PUBLIC_IP
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh --hostname jarvis-cloud
```

It prints a link. Open it and log in with the **same Tailscale account** as your phone and laptop. Type `exit`.

## 3. Move JARVIS (one double-click)

On the laptop, double-click **`cloud-move.bat`** in the JARVIS folder and type `jarvis-cloud`. It does five things:

1. backs up your memory, tasks, clients and settings
2. copies JARVIS to the server over Tailscale
3. installs it there as an always-on service (a few minutes the first time)
4. makes this laptop the satellite
5. tells your phone app the new address. It switches by itself; no setup needed on the phone.

Then close JARVIS on the laptop and run `start.bat` again. It now opens the cloud dashboard and keeps the laptop
linked as the satellite.

## What changes

- JARVIS answers on Telegram and the phone app **even when the laptop is off**.
- Laptop-only requests ("take a screenshot of my laptop", "open Spotify on the laptop") work when the laptop is on.
  When it's off, JARVIS says so and offers to do it when it's back.
- The phone's solo mode still covers you when there's no internet at all.
- **Brain:** your free Gemini key works in the cloud straight away. To use your Claude subscription there too:
  `ssh ubuntu@jarvis-cloud`, then `curl -fsSL https://claude.ai/install.sh | bash`, then `claude` and log in.

## Good to know

- Oracle can reclaim Always Free servers that sit almost idle for a week. JARVIS keeps it busy enough with its
  regular jobs. If it's ever reclaimed, run steps 1 to 3 again; your memory is in the laptop's backups.
- **Update the cloud JARVIS:** run `cloud-move.bat` again (it keeps your data), or send `update` on Telegram.
- **Move back to the laptop:** set `JARVIS_ROLE=laptop` in `.env`, run `start.bat`, and set the phone app's address
  back to the laptop.
