"""Phase 6: Shaabaz Studio (event floor plans, mood boards, portfolio site and brand kit) and the platform
(backup & restore, rebrand)."""
from __future__ import annotations

import html
import json
import math
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

from . import devices
from .config import ROOT, settings
from .tools import I, S, ToolContext, tool

N = {"type": "number"}
B = {"type": "boolean"}


# ================================================================== floor plans
ITEM_SIZES = {   # metres (w, h)
    "stage": (6.0, 3.0), "dance_floor": (6.0, 5.0), "buffet": (6.0, 1.2), "bar": (3.0, 1.2), "photo_booth": (2.5, 2.5),
    "entrance": (3.0, 0.6), "dj": (2.0, 1.2), "cake": (1.2, 1.2), "gift_table": (2.4, 0.9), "round_table": (1.8, 1.8),
    "long_table": (2.4, 0.9), "sweetheart": (2.0, 1.0), "registration": (2.4, 0.9)}


def auto_layout(room_w: float, room_l: float, guests: int, style: str = "wedding", seats: int = 10) -> dict:
    """A sensible banquet layout: stage, dance floor, buffet, bar, photo booth, entrance, then round tables in a grid
    that keeps 3 m between table centres and clear walkways."""
    room_w, room_l = max(8.0, float(room_w)), max(8.0, float(room_l))
    items, blocked = [], []

    def put(kind, x, y, label=""):
        w, h = ITEM_SIZES[kind]
        items.append({"type": kind, "x": round(x, 2), "y": round(y, 2), "w": w, "h": h, "label": label or kind.replace("_", " ").title()})
        blocked.append((x - .9, y - .9, x + w + .9, y + h + .9))
    put("stage", room_w / 2 - 3, .5, "Pelamin / stage" if style in ("wedding", "malay", "indian") else "Stage")
    if style in ("wedding", "malay", "indian", "party", "dinner"):
        put("dance_floor", room_w / 2 - 3, 4.2, "Dance floor")
    put("entrance", room_w / 2 - 1.5, room_l - .6, "Entrance")
    put("registration", room_w / 2 - 1.2, room_l - 2.6, "Registration")
    buffets = max(1, math.ceil(guests / 150))
    for i in range(buffets):
        put("buffet", .4, 2.5 + i * 7.5, f"Buffet {i + 1}" if buffets > 1 else "Buffet")
    put("bar", room_w - 3.4, .6, "Drinks")
    put("photo_booth", room_w - 2.9, room_l - 3.4, "Photo booth")
    put("gift_table", .4, room_l - 1.6, "Gifts")
    if style in ("wedding", "malay", "indian"):
        put("cake", room_w / 2 + 3.6, 1.4, "Cake")
    tables_needed = math.ceil(max(0, guests) / max(1, seats))
    pitch, margin, r, clear = 3.0, 1.2, .9, .55
    # greedy packing on a fine grid: closest to the stage first, 3 m between table centres, clear of everything else
    cands, step = [], .25
    yy = 3.8
    while yy <= room_l - 1.5 - r:
        xx = margin + r
        while xx <= room_w - margin - r:
            cands.append((xx, yy))
            xx += step
        yy += step
    cands.sort(key=lambda p: (round(p[1] / pitch), abs(p[0] - room_w / 2)))
    chosen = []

    def free(x, y):
        for bx0, by0, bx1, by1 in blocked:   # blocked rects already include a .9 m walkway
            if bx0 - r - clear + .9 < x < bx1 + r + clear - .9 and by0 - r - clear + .9 < y < by1 + r + clear - .9:
                return False
        return all((x - cx) ** 2 + (y - cy) ** 2 >= pitch ** 2 for cx, cy in chosen)
    for x, y in cands:
        if len(chosen) >= tables_needed:
            break
        if free(x, y):
            chosen.append((x, y))
    chosen.sort(key=lambda p: (p[1], p[0]))
    for n, (x, y) in enumerate(chosen, start=1):
        items.append({"type": "round_table", "x": round(x - r, 2), "y": round(y - r, 2), "w": 1.8, "h": 1.8,
                      "label": "VIP" if n <= 2 else f"T{n}", "seats": seats})
    placed = sum(1 for i in items if i["type"] == "round_table")
    return {"room": [room_w, room_l], "guests": guests, "seats": seats, "style": style, "items": items,
            "tables": placed, "capacity": placed * seats, "fits": placed >= tables_needed,
            "note": "" if placed >= tables_needed else
            f"Only {placed} tables ({placed * seats} guests) fit with comfortable walkways; {guests} needs a bigger room "
            f"or {math.ceil(guests / placed) if placed else '?'} per table."}


@tool("plan_layout", "Make an event floor plan for a gig: room size in metres, guest count and style (wedding | malay | "
      "indian | corporate | party | dinner). Places stage, dance floor, buffet, bar, photo booth, entrance and round "
      "tables with walkways, saves it to the gig and gives the link to open it in 2D/3D and edit.",
      {"gig_id": I, "room_w": N, "room_l": N, "guests": I, "style": S, "seats_per_table": I}, ["room_w", "room_l", "guests"])
def plan_layout(ctx: ToolContext, room_w: float, room_l: float, guests: int, gig_id: int | None = None,
                style: str = "wedding", seats_per_table: int = 10) -> dict:
    lay = auto_layout(room_w, room_l, guests, style, seats_per_table)
    if gig_id:
        gig = ctx.store.get_gig(gig_id)
        if not gig:
            return {"error": f"No gig #{gig_id}"}
        lay["client"] = gig["client"]
        ctx.store.update_gig(gig_id, layout=json.dumps(lay))
    url = f"/planner.html{'?gig=' + str(gig_id) if gig_id else ''}"
    if not gig_id:
        ctx.store.set("studio:last_layout", json.dumps(lay))
    return {"tables": lay["tables"], "capacity": lay["capacity"], "fits": lay["fits"], "note": lay["note"],
            "open": (settings.app_url or f"http://127.0.0.1:{settings.port}") + url}


# ================================================================== mood boards
def _hex(c: str) -> tuple[float, float, float]:
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return (0.8, 0.7, 0.5)


@tool("make_moodboard", "Make a client mood-board and theme proposal PDF for an event: theme name, a short story, "
      "4-6 colours (hex), keywords, and elements (decor, florals, lighting, attire, stationery, food). Sent to the "
      "owner's phone; attach it to an e-mail for the client with send_email.",
      {"client": S, "theme": S, "story": S, "palette": {"type": "array", "items": S},
       "keywords": {"type": "array", "items": S}, "elements": {"type": "array", "items": {"type": "object", "properties": {
           "area": S, "idea": S}, "required": ["area", "idea"]}}, "gig_id": I, "send_to_phone": B},
      ["client", "theme", "palette", "elements"])
def make_moodboard(ctx: ToolContext, client: str, theme: str, palette: list, elements: list, story: str = "",
                   keywords: list | None = None, gig_id: int | None = None, send_to_phone: bool = True) -> dict:
    from .extras import business_details
    from .pdf import MARGIN, PAGE_W, Doc
    biz = business_details()
    name = biz.get("business name", "Shaabaz Weddings & Events")
    cols = [_hex(c) for c in palette[:6]] or [(0.85, 0.7, 0.4)]
    d = Doc()
    d.rect(0, 0, PAGE_W, 842, (0.985, 0.975, 0.96))
    # colour field across the top
    band = (PAGE_W - 2 * MARGIN) / len(cols)
    for i, c in enumerate(cols):
        d.rect(MARGIN + i * band, 842 - 210, band - 4, 150, c)
        d.text(MARGIN + i * band + 6, 842 - 228, "#" + palette[i].strip().lstrip("#").upper(), 8, color=(0.4, 0.4, 0.4))
    d.y = 842 - 250
    d.text(MARGIN, d.y, "MOOD BOARD · " + client.upper(), 9, True, (0.45, 0.35, 0.2))
    d.y -= 30
    d.paragraph(theme, 28, True, color=(0.12, 0.1, 0.08), gap=1.1, serif=True)
    if story:
        d.y -= 2
        d.paragraph(story, 11.5, color=(0.3, 0.28, 0.25), gap=1.5, serif=True)
    if keywords:
        d.y -= 10
        d.paragraph("  ·  ".join(k.upper() for k in keywords[:8]), 9, True, color=(0.55, 0.42, 0.22))
    d.y -= 14
    col_w = (PAGE_W - 2 * MARGIN - 24) / 2
    ys = [d.y, d.y]
    for i, el in enumerate(elements[:10]):
        c = 0 if ys[0] >= ys[1] else 1
        x = MARGIN + c * (col_w + 24)
        d.y = ys[c]
        sw = cols[i % len(cols)]
        d.rect(x, d.y - 16, 10, 10, sw)
        d.text(x + 16, d.y - 15, el["area"].upper(), 8.5, True, (0.35, 0.3, 0.25))
        d.y -= 18
        d.paragraph(el["idea"], 10.5, x=x, width=col_w, color=(0.15, 0.13, 0.11), gap=1.45, serif=True)
        d.y -= 10
        ys[c] = d.y
    d.y = min(ys) - 20
    d.paragraph(f"Prepared by {name}" + (f" · {biz['phone']}" if "phone" in biz else ""), 9, color=(0.45, 0.4, 0.35))
    safe = re.sub(r"[^A-Za-z0-9]+", "-", f"{client}-{theme}").strip("-")[:50]
    path = d.save(devices.WORKSPACE / "Business" / "Mood boards" / f"{safe}.pdf")
    if gig_id:
        g = ctx.store.get_gig(gig_id)
        if g:
            ctx.store.update_gig(gig_id, notes=((g["notes"] or "") + f"\nMood board: {theme}").strip())
    out = {"pdf": str(path)}
    if send_to_phone:
        from .desktop import _to_phone
        out.update(_to_phone(path, True, f"🎨 {client} · {theme}"))
    return out


# ================================================================== portfolio site + brand kit
def _monogram(initials: str, color: str = "#c9a24a") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><circle cx="60" cy="60" r="56" fill="none" '
            f'stroke="{color}" stroke-width="3"/><circle cx="60" cy="60" r="49" fill="none" stroke="{color}" stroke-width="1"/>'
            f'<text x="60" y="73" text-anchor="middle" font-family="Georgia,serif" font-size="40" fill="{color}" '
            f'letter-spacing="2">{html.escape(initials)}</text></svg>')


@tool("build_portfolio", "Build (or refresh) the owner's portfolio website and brand kit from business.md, profile.md "
      "and the events JARVIS has tracked: a polished one-page site (services, packages, events done, testimonials, "
      "contact), a monogram logo, an e-mail signature, and a digital business card with a QR code. Saved in "
      "~/JARVIS/Website and previewable at /site/.",
      {"headline": S, "about": S, "testimonials": {"type": "array", "items": {"type": "object", "properties": {
          "quote": S, "name": S}}}, "accent": S}, [])
def build_portfolio(ctx: ToolContext, headline: str = "", about: str = "", testimonials: list | None = None,
                    accent: str = "#c9a24a") -> dict:
    from .extras import business_details
    biz = business_details()
    name = biz.get("business name", "Shaabaz Weddings & Events")
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", name)[:2]).upper() or "SW"
    done = ctx.store.query("SELECT COUNT(*) AS n FROM gigs WHERE status IN ('done','confirmed')")[0]["n"]
    crew = ctx.store.query("SELECT COUNT(*) AS n FROM crew")[0]["n"]
    bpath = ROOT / "business.md"
    btext = bpath.read_text(encoding="utf-8") if bpath.exists() else ""
    packages = re.findall(r"^\s*-\s*([A-Z][\w &+]+?)\s*-\s*\$?\s*([\d,]+)?\s*-\s*(.+)$", btext, re.M)
    services = re.findall(r"Event types:\s*(.+)", btext)
    owner = settings.owner_name if settings.owner_name.lower() != "sir" else "the founder"
    facts = btext + "\n" + settings.profile()
    m_ev = re.search(r"(\d+)\s*\+?\s*events", facts, re.I)
    m_cr = re.search(r"(\d+)\s*(?:part-?timers|crew)", facts, re.I)
    done = max(done, int(m_ev.group(1)) if m_ev else 0)
    crew = max(crew, int(m_cr.group(1)) if m_cr else 0)
    stats = "".join(f"<div><b>{v}{'+' if plus else ''}</b>{label}</div>" for v, plus, label in
                    ((done, bool(m_ev), "events delivered"), (crew, False, "crew on call")) if v)
    esc = html.escape
    tst = testimonials or []
    out_dir = devices.WORKSPACE / "Website"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "logo.svg").write_text(_monogram(initials, accent), encoding="utf-8")
    contact = [(k.title(), biz[k]) for k in ("phone", "email", "instagram", "website") if k in biz]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(name)}</title><link rel="icon" href="logo.svg">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
<style>:root{{--a:{esc(accent)};--ink:#1d1a16;--bg:#fbf8f3;--mute:#6f675d}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 Inter,system-ui,sans-serif}}
header{{min-height:78vh;display:grid;place-items:center;text-align:center;padding:60px 20px;background:linear-gradient(180deg,#1d1a16,#2b241b);color:#f6efe3}}
header img{{width:96px;margin-bottom:18px}}h1,h2{{font-family:"Cormorant Garamond",Georgia,serif;font-weight:700;margin:0}}h1{{font-size:clamp(38px,7vw,68px);letter-spacing:.02em}}
header p{{max-width:620px;margin:14px auto 0;color:#d9cdb8;font-size:18px}}.cta{{display:inline-block;margin-top:26px;padding:14px 26px;border:1px solid var(--a);color:#f6efe3;text-decoration:none;letter-spacing:.18em;font-size:12px}}
section{{max-width:1040px;margin:0 auto;padding:70px 20px}}h2{{font-size:40px;margin-bottom:18px}}.stats{{display:flex;gap:40px;flex-wrap:wrap}}.stats b{{display:block;font-family:"Cormorant Garamond",serif;font-size:52px;color:var(--a)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}}.card{{border:1px solid #e7dfd2;background:#fff;padding:22px}}.card h3{{margin:0 0 6px;font-family:"Cormorant Garamond",serif;font-size:26px}}
.price{{color:var(--a);font-weight:500}}blockquote{{margin:0;font-family:"Cormorant Garamond",serif;font-size:24px}}blockquote cite{{display:block;font:14px Inter,sans-serif;color:var(--mute);margin-top:10px}}
footer{{background:#1d1a16;color:#d9cdb8;text-align:center;padding:50px 20px}}footer a{{color:#f6efe3}}</style></head><body>
<header><div><img src="logo.svg" alt=""><h1>{esc(name)}</h1><p>{esc(headline or "Weddings and events, planned to the minute and remembered for a lifetime.")}</p>
<a class="cta" href="#contact">PLAN YOUR EVENT</a></div></header>
<section><h2>About</h2><p>{esc(about or f"Founded by {owner}, we plan and run weddings, engagements, birthdays and corporate events across Singapore, with a trained crew who make the day run itself.")}</p>
{f'<div class="stats">{stats}</div>' if stats else ""}</section>
{"<section><h2>What we do</h2><p>" + esc(services[0]) + "</p></section>" if services else ""}
{"<section><h2>Packages</h2><div class='grid'>" + "".join(f"<div class='card'><h3>{esc(p[0])}</h3>" + (f"<div class='price'>from ${esc(p[1])}</div>" if p[1] else "") + f"<p>{esc(p[2])}</p></div>" for p in packages[:6]) + "</div></section>" if packages else ""}
{"<section><h2>Kind words</h2><div class='grid'>" + "".join(f"<div class='card'><blockquote>“{esc(t.get('quote', ''))}”<cite>{esc(t.get('name', ''))}</cite></blockquote></div>" for t in tst[:6]) + "</div></section>" if tst else ""}
<footer id="contact"><h2 style="color:#f6efe3">Let's talk</h2><p>{"<br>".join(f"{esc(k)}: {esc(v)}" for k, v in contact) or "Add your phone and e-mail to business.md"}</p>
<p style="font-size:12px;margin-top:30px">© {datetime.now().year} {esc(name)}</p></footer></body></html>"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    # e-mail signature
    sig = (f'<table style="font-family:Georgia,serif;color:#1d1a16"><tr><td style="padding-right:12px"><img src="logo.svg" width="54"></td>'
           f'<td><b style="font-size:16px">{esc(owner.title())}</b><br><span style="color:{esc(accent)}">{esc(name)}</span><br>'
           + "<br>".join(f'<span style="font:12px Arial;color:#6f675d">{esc(v)}</span>' for _k, v in contact) + "</td></tr></table>")
    (out_dir / "email-signature.html").write_text(sig, encoding="utf-8")
    # digital business card (vCard + QR)
    vcard = "BEGIN:VCARD\nVERSION:3.0\nFN:" + owner.title() + "\nORG:" + name + "\n"
    if "phone" in biz:
        vcard += "TEL:" + biz["phone"] + "\n"
    if "email" in biz:
        vcard += "EMAIL:" + biz["email"] + "\n"
    if "website" in biz:
        vcard += "URL:" + biz["website"] + "\n"
    vcard += "END:VCARD\n"
    (out_dir / "contact.vcf").write_text(vcard, encoding="utf-8")
    qr = ""
    try:
        import segno
        segno.make(vcard, error="m").save(str(out_dir / "card-qr.svg"), scale=6, dark="#1d1a16", light="#fbf8f3")
        qr = str(out_dir / "card-qr.svg")
    except Exception:  # noqa: BLE001 - QR is a bonus
        pass
    return {"site": str(out_dir / "index.html"), "preview": "/site/", "logo": str(out_dir / "logo.svg"),
            "email_signature": str(out_dir / "email-signature.html"), "business_card_qr": qr,
            "packages_found": len(packages),
            "next": "To put it online for free: GitHub Pages or Netlify Drop (drag the Website folder in)."}


# ================================================================== backup & restore
def backup(include_settings: bool = False) -> Path:
    """One zip with everything that makes this JARVIS yours. Settings (.env, with passwords) only when asked."""
    out_dir = devices.WORKSPACE / "Backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"JARVIS-backup-{datetime.now():%Y%m%d-%H%M}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        db = settings.db_path
        if Path(db).exists():
            tmp = out_dir / ".backup.db"
            src, dst = sqlite3.connect(str(db)), sqlite3.connect(str(tmp))
            src.backup(dst)
            src.close()
            dst.close()
            z.write(tmp, "data/jarvis.db")
            tmp.unlink()
        for f in ("profile.md", "business.md", "data/orb.json"):
            if (ROOT / f).exists():
                z.write(ROOT / f, f)
        if include_settings and (ROOT / ".env").exists():
            z.write(ROOT / ".env", ".env")
        z.writestr("README.txt", "JARVIS backup. Restore on a new laptop: install JARVIS, then run\n"
                                 "    python -m jarvis restore <this file>\nwhile JARVIS is stopped.\n")
    return path


def restore(zip_path: str) -> list[str]:
    """Put a backup back in place (the current files are kept as *.before-restore)."""
    allowed = {"data/jarvis.db", "profile.md", "business.md", "data/orb.json", ".env"}
    done = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if name not in allowed:
                continue
            target = ROOT / name if name != "data/jarvis.db" else Path(settings.db_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.replace(target.with_name(target.name + ".before-restore"))
            target.write_bytes(z.read(name))
            done.append(name)
    return done


@tool("backup_jarvis", "Make a backup of everything JARVIS knows (memories, tasks, clients, notes, settings files) "
      "in one zip in ~/JARVIS/Backups, and send it to the owner's phone. include_settings adds .env (contains "
      "passwords: keep that file private).", {"include_settings": B, "send_to_phone": B})
def backup_jarvis(ctx: ToolContext, include_settings: bool = False, send_to_phone: bool = False) -> dict:
    path = backup(include_settings)
    out = {"backup": str(path), "mb": round(path.stat().st_size / 1e6, 2)}
    if send_to_phone and not include_settings:
        from .desktop import _to_phone
        out.update(_to_phone(path, True, "🗄 JARVIS backup"))
    return out
