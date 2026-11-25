"""ZEUS's job hunt: as many good applications a day as possible, with the least effort from the owner.

1. Hunt: fresh jobs every morning from MyCareersFuture (public job search) and from the owner's own job-alert e-mails
   (JobStreet, LinkedIn, Indeed, Glassdoor, MyCareersFuture alerts in Gmail).
2. Rank: each job is scored against the owner's resume and preferences (fit %, one line on why).
3. Prepare: a short tailored cover letter per job (from the resume only, never invented facts).
4. Apply: the Job Hunt screen shows one job at a time. ⚡ APPLY copies the cover letter and opens the job, the owner
   pastes and submits, the next job slides in. Target: 50 a day.
   Jobs that take applications by e-mail are sent by JARVIS with the CV attached, only after the owner taps SEND ALL.
LinkedIn and JobStreet don't allow bots to submit applications (accounts get banned), so the final tap there is the
owner's. Everything else is done for them.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from .config import ROOT, settings

CAREER = ROOT / "data" / "career"
DAILY_TARGET = 50


# ---------------------------------------------------------------- the owner's profile
def prefs(store) -> dict:
    try:
        p = json.loads(store.get("jobs:prefs") or "{}")
    except ValueError:
        p = {}
    return {"roles": p.get("roles") or [], "locations": p.get("locations") or ["Singapore"], "min_salary": p.get("min_salary") or 0,
            "types": p.get("types") or ["full time", "part time", "contract", "internship"], "avoid": p.get("avoid") or [],
            "daily_target": p.get("daily_target") or DAILY_TARGET}


def resume_path() -> Path | None:
    for name in ("resume.pdf", "resume.docx"):
        if (CAREER / name).exists():
            return CAREER / name
    return None


def resume_text() -> str:
    t = CAREER / "resume.txt"
    return t.read_text(encoding="utf-8", errors="ignore") if t.exists() else ""


def save_resume(src: Path) -> str:
    """Keep the owner's CV (from Telegram or the laptop) and read its text for matching and letters."""
    CAREER.mkdir(parents=True, exist_ok=True)
    dest = CAREER / ("resume" + (src.suffix.lower() or ".pdf"))
    dest.write_bytes(src.read_bytes())
    text = ""
    if dest.suffix == ".pdf":
        try:
            from pypdf import PdfReader
            text = "\n".join((pg.extract_text() or "") for pg in PdfReader(str(dest)).pages)
        except Exception:  # noqa: BLE001
            text = ""
    elif dest.suffix == ".docx":
        try:
            import zipfile
            xml = zipfile.ZipFile(dest).read("word/document.xml").decode("utf-8", "ignore")
            text = re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
        except Exception:  # noqa: BLE001
            text = ""
    (CAREER / "resume.txt").write_text(text[:40000], encoding="utf-8")
    return text


# ---------------------------------------------------------------- the job list
def _ensure(store) -> None:
    store.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT UNIQUE, source TEXT, title TEXT, company TEXT, location TEXT,
        salary TEXT, url TEXT, apply_email TEXT DEFAULT '', descr TEXT DEFAULT '', posted TEXT, fit INTEGER DEFAULT 0,
        why TEXT DEFAULT '', status TEXT DEFAULT 'new', cover TEXT DEFAULT '', created TEXT, acted TEXT)""")


def _key(title: str, company: str, url: str) -> str:
    base = (re.sub(r"\W+", " ", f"{title} {company}").lower().strip() or url)
    return hashlib.sha1(base.encode()).hexdigest()[:20]


def add_job(store, j: dict) -> bool:
    _ensure(store)
    if not j.get("title") or not (j.get("url") or j.get("apply_email")):
        return False
    from .scam import check
    if check(f"{j['title']} {j.get('company', '')} {j.get('descr', '')}")["scam"]:
        return False   # "earn $300 a day liking videos" is not a job
    key = _key(j["title"], j.get("company", ""), j.get("url", ""))
    try:
        store.execute("INSERT INTO jobs (key, source, title, company, location, salary, url, apply_email, descr, posted, created) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (key, j.get("source", ""), j["title"][:140], (j.get("company") or "")[:100], (j.get("location") or "")[:80],
                       (j.get("salary") or "")[:60], j.get("url", ""), j.get("apply_email", ""), (j.get("descr") or "")[:4000],
                       j.get("posted") or "", datetime.now(settings.tz).isoformat(timespec="minutes")))
        return True
    except Exception:  # noqa: BLE001  (already have it)
        return False


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _apply_email(text: str) -> str:
    """An e-mail address the ad asks applications to be sent to (not a no-reply one)."""
    for m in EMAIL_RE.finditer(text or ""):
        e = m.group(0).rstrip(".")
        ctx = text[max(0, m.start() - 120):m.start()].lower()
        if not re.search(r"no-?reply|donotreply|example\.com", e, re.I) and re.search(r"(send|email|e-mail|apply|cv|resume|application)", ctx):
            return e
    return ""


# ---------------------------------------------------------------- sources
def from_mcf(query: str, limit: int = 60) -> list[dict]:
    """MyCareersFuture (Singapore's public job board) search, newest first."""
    body = json.dumps({"sessionId": "", "search": query, "sortBy": ["new_posting_date"]}).encode()
    req = urllib.request.Request(f"https://api.mycareersfuture.gov.sg/v2/search?limit={min(limit, 100)}&page=0", data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 JARVIS"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.loads(r.read())
    out = []
    for it in data.get("results", []):
        sal = it.get("salary") or {}
        lo, hi = sal.get("minimum"), sal.get("maximum")
        descr = re.sub(r"<[^>]+>", " ", it.get("description") or "")
        meta = it.get("metadata") or {}
        out.append({"source": "MyCareersFuture", "title": it.get("title", ""), "company": (it.get("postedCompany") or {}).get("name", ""),
                    "location": "Singapore", "salary": f"${lo:,}–${hi:,}/mth" if lo and hi else "",
                    "url": meta.get("jobDetailsUrl") or f"https://www.mycareersfuture.gov.sg/job/{it.get('uuid', '')}",
                    "descr": re.sub(r"\s+", " ", descr)[:3000], "apply_email": _apply_email(descr),
                    "posted": meta.get("newPostingDate") or meta.get("createdAt") or ""})
    return out


ALERT_LINK = re.compile(r"""<a[^>]+href=["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)
JOB_URL = re.compile(r"(jobstreet\.[a-z.]+/[^\s\"']*job|linkedin\.com/(?:comm/)?jobs/view|indeed\.[a-z.]+/(?:rc/clk|viewjob|pagead)|"
                     r"mycareersfuture\.gov\.sg/job|glassdoor\.[a-z.]+/(?:job-listing|partner/jobListing)|fastjobs\.sg/[^\s\"']*job)", re.I)


def from_alert_html(html: str, source: str) -> list[dict]:
    """Jobs listed in a job-alert e-mail (JobStreet, LinkedIn, Indeed...)."""
    out, seen = [], set()
    for href, inner in ALERT_LINK.findall(html or ""):
        href = href.replace("&amp;", "&")
        if not JOB_URL.search(href):
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if len(title) < 4 or len(title) > 120 or re.search(r"^(view|apply|see|more|unsubscribe|search)\b", title, re.I) or title in seen:
            continue
        seen.add(title)
        tail = re.sub(r"<[^>]+>", "\n", html[html.find(inner) + len(inner):][:600])
        bits = [b.strip() for b in tail.split("\n") if b.strip() and len(b.strip()) < 80][:3]
        out.append({"source": source, "title": title, "company": bits[0] if bits else "", "location": bits[1] if len(bits) > 1 else "",
                    "url": href, "descr": " · ".join(bits)})
    return out


def from_alert_mail(days: int = 3) -> list[dict]:
    from . import channels as ch
    if not ch.email_read_ready():
        return []
    out = []
    for m in ch.job_alert_mail(days):
        src = next((n for n in ("JobStreet", "LinkedIn", "Indeed", "Glassdoor", "MyCareersFuture", "FastJobs")
                    if n.lower() in (m.get("from", "") + m.get("subject", "")).lower()), "Job alert")
        out += from_alert_html(m.get("html", ""), src)
    return out


# ---------------------------------------------------------------- ranking
WORD = re.compile(r"[a-z][a-z+#.\-]{2,}")
STOP = set("the and for with you your our are will this that from have has not but all can job role work team "
           "years year experience able skills ability good strong including such other within per must well".split())


def quick_fit(job: dict, cv: str, p: dict) -> int:
    """A fast score from the resume and preferences (the brain refines the top ones)."""
    cvw = {w for w in WORD.findall(cv.lower()) if w not in STOP}
    jw = [w for w in WORD.findall(f"{job['title']} {job.get('descr', '')}".lower()) if w not in STOP]
    overlap = len(cvw & set(jw)) / max(8, len(set(jw))) if cvw else 0
    title = job["title"].lower()
    role_hit = any(r.lower() in title for r in p["roles"]) or any(w in title for r in p["roles"] for w in r.lower().split() if len(w) > 3)
    score = 35 + overlap * 70 + (25 if role_hit else 0)
    if any(a.lower() in f"{title} {job.get('company', '')}".lower() for a in p["avoid"]):
        score -= 60
    if re.search(r"\b(senior|sr\.?|lead|principal|head of|director|manager)\b", title) and not re.search(r"\b(senior|manager|lead)\b", cv.lower()):
        score -= 15
    return max(0, min(99, round(score)))


def llm(prompt: str, max_tokens: int = 700) -> str:
    """The quickest free brain available (Gemini), for scoring and letters."""
    from . import brains
    if not settings.gemini_key:
        return ""
    try:
        d = brains._gemini_call({"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                                 "generationConfig": {"temperature": .5, "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}}})
        return "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"]).strip()
    except Exception:  # noqa: BLE001
        return ""


def rank(store, limit: int = 80) -> int:
    """Score new jobs: quick score for all, then the brain's fit % and a reason for the best ones."""
    _ensure(store)
    cv, p = resume_text(), prefs(store)
    rows = store.query("SELECT * FROM jobs WHERE status = 'new' AND fit = 0 ORDER BY id DESC LIMIT 400")
    for r in rows:
        store.execute("UPDATE jobs SET fit = ? WHERE id = ?", (quick_fit(r, cv, p), r["id"]))
    top = store.query("SELECT id, title, company, descr FROM jobs WHERE status = 'new' AND why = '' ORDER BY fit DESC LIMIT ?", (limit,))
    if not cv or not top:
        return len(rows)
    for i in range(0, len(top), 20):
        batch = top[i:i + 20]
        listing = "\n".join(f"{r['id']}. {r['title']} at {r['company']}: {(r['descr'] or '')[:400]}" for r in batch)
        out = llm("You are a sharp career coach. Score how well this candidate fits each job (0-100, be honest: "
                  "requirements they clearly lack lower the score) and give a 10-word reason.\n"
                  f"Candidate resume:\n{cv[:5000]}\nWanted roles: {', '.join(p['roles']) or 'open'}\n\nJobs:\n{listing}\n\n"
                  'Reply with JSON only: [{"id": 1, "fit": 80, "why": "..."}]', 1500)
        try:
            for x in json.loads(out[out.find("["):out.rfind("]") + 1]):
                store.execute("UPDATE jobs SET fit = ?, why = ? WHERE id = ?", (int(x["fit"]), str(x.get("why", ""))[:120], int(x["id"])))
        except Exception:  # noqa: BLE001
            pass
    return len(rows)


# ---------------------------------------------------------------- the hunt
def hunt(store, bus=None) -> dict:
    """Find fresh jobs, add the new ones, rank them."""
    _ensure(store)
    p, added, errors = prefs(store), 0, []
    queries = p["roles"] or _roles_from_cv()
    for q in queries[:6]:
        try:
            for j in from_mcf(q, 60):
                added += add_job(store, j)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"MyCareersFuture: {str(exc)[:80]}")
    try:
        for j in from_alert_mail(3):
            added += add_job(store, j)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"job alerts: {str(exc)[:80]}")
    rank(store)
    # old untouched jobs fade out after 3 weeks
    store.execute("UPDATE jobs SET status = 'expired' WHERE status = 'new' AND created < ?",
                  ((datetime.now(settings.tz) - timedelta(days=21)).isoformat(),))
    store.set("jobs:hunted", datetime.now(settings.tz).isoformat(timespec="minutes"))
    if bus:
        bus.publish({"type": "data", "what": "jobs"})
    return {"added": added, "ready": len(queue(store, 200)), "errors": errors, "queries": queries[:6]}


def _roles_from_cv() -> list[str]:
    cv = resume_text()
    if not cv:
        return ["executive", "assistant", "coordinator"]
    out = llm("From this resume, list the 5 job titles (short search terms, e.g. 'marketing executive') this person "
              f"should search for in Singapore, most likely to get hired first. One per line, nothing else.\n\n{cv[:5000]}", 120)
    roles = [re.sub(r"^[\-\d.\s]+", "", x).strip() for x in out.splitlines() if x.strip()][:5]
    return roles or ["executive", "assistant", "coordinator"]


def queue(store, n: int = 60) -> list[dict]:
    _ensure(store)
    p = prefs(store)
    rows = store.query("SELECT * FROM jobs WHERE status IN ('new', 'saved') ORDER BY status = 'saved' DESC, fit DESC, id DESC LIMIT ?", (n * 2,))
    return [r for r in rows if not any(a.lower() in f"{r['title']} {r['company']}".lower() for a in p["avoid"])][:n]


def today_count(store) -> int:
    _ensure(store)
    start = datetime.now(settings.tz).date().isoformat()
    return store.query("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('applied', 'emailed') AND acted >= ?", (start,))[0]["n"]


# ---------------------------------------------------------------- per job: the letter, and applying
def prep(store, job_id: int) -> dict:
    """The tailored cover letter for one job (made once, kept)."""
    _ensure(store)
    rows = store.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if not rows:
        return {"error": "no such job"}
    j = rows[0]
    if j["cover"]:
        return {"cover": j["cover"]}
    cv, owner = resume_text(), settings.owner_name or ""
    letter = llm("Write a short, confident cover letter (120-170 words) for this job, in plain text, from the candidate. "
                 "Use ONLY facts from the resume (never invent experience, grades or skills). Open with why this role, "
                 "then 2 specific matches between the resume and the job, then a one-line close. No placeholders like [Company]. "
                 f"Sign off with the candidate's name from the resume.\n\nJob: {j['title']} at {j['company']}\n{(j['descr'] or '')[:2500]}\n\n"
                 f"Resume:\n{cv[:5000]}", 450) if cv else ""
    if not letter:
        letter = (f"Dear Hiring Team,\n\nI'm excited to apply for the {j['title']} role{' at ' + j['company'] if j['company'] else ''}. "
                  "My experience and skills, detailed in my attached resume, match what you're looking for, and I'm ready to "
                  "contribute from day one. I'd welcome the chance to discuss how I can help your team.\n\n"
                  f"Thank you for your time,\n{owner}")
    store.execute("UPDATE jobs SET cover = ? WHERE id = ?", (letter, job_id))
    return {"cover": letter}


def mark(store, job_id: int, status: str) -> dict:
    _ensure(store)
    if status not in ("applied", "skipped", "saved", "new", "emailed"):
        return {"error": "bad status"}
    store.execute("UPDATE jobs SET status = ?, acted = ? WHERE id = ?", (status, datetime.now(settings.tz).isoformat(timespec="minutes"), job_id))
    if status == "applied":   # into ZEUS's applications tracker, with a follow-up a week later
        j = store.query("SELECT title, company, url FROM jobs WHERE id = ?", (job_id,))[0]
        store.add_application(j["company"] or "?", j["title"], "applied", j["url"],
                              f"Follow up {(datetime.now(settings.tz) + timedelta(days=7)).strftime('%d %b')} if no reply")
    return {"ok": True, "today": today_count(store)}


def email_ready(store) -> list[dict]:
    _ensure(store)
    return store.query("SELECT id, title, company, apply_email, fit FROM jobs WHERE status IN ('new', 'saved') AND apply_email != '' "
                       "AND fit >= 45 ORDER BY fit DESC LIMIT 25")


def send_all(store, bus, ids: list[int]) -> dict:
    """The owner tapped SEND ALL: e-mail these applications with the CV attached (this tap is their yes)."""
    from . import channels as ch
    if not ch.email_ready():
        return {"error": "E-mail sending isn't set up yet (/email on Telegram)."}
    cv = resume_path()
    if not cv:
        return {"error": "Send ZEUS your resume first (a PDF on Telegram, caption 'resume')."}
    sent, failed = 0, []
    for jid in ids:
        rows = store.query("SELECT * FROM jobs WHERE id = ? AND apply_email != ''", (jid,))
        if not rows:
            continue
        j = rows[0]
        letter = prep(store, jid)["cover"]
        mid = store.queue_message("email", j["apply_email"], letter, "ZEUS", subject=f"Application: {j['title']}"[:120],
                                  recipient_name=j["company"] or j["apply_email"], reason="job application (owner tapped SEND ALL)",
                                  status="approved", attachment=str(cv))
        ok = ch.deliver(store, bus, store.get_message(mid))
        if ok:
            sent += 1
            mark(store, jid, "emailed")
            store.add_application(j["company"] or "?", j["title"], "applied", j["url"] or f"mailto:{j['apply_email']}",
                                  "Emailed with CV. Follow up in a week.")
        else:
            failed.append(j["title"])
    if bus:
        bus.publish({"type": "data", "what": "jobs"})
    return {"sent": sent, "failed": failed, "today": today_count(store)}


def followups(store, days: int = 7) -> list[dict]:
    """E-mailed applications with no reply after a week: time for a polite follow-up (once)."""
    _ensure(store)
    cut = (datetime.now(settings.tz) - timedelta(days=days)).isoformat()
    return store.query("SELECT id, title, company, apply_email, acted FROM jobs WHERE status = 'emailed' AND acted <= ? "
                       "AND apply_email != '' ORDER BY acted LIMIT 30", (cut,))


def followup_text(j: dict) -> str:
    name = settings.owner_name or ""
    when = (j.get("acted") or "")[:10]
    return (f"Dear Hiring Team,\n\nI hope you're well. I applied for the {j['title']} role"
            + (f" on {datetime.fromisoformat(when).strftime('%d %B')}" if when else "")
            + " and wanted to follow up, as I remain very interested in the position and in contributing to "
            + (j['company'] or "your team") + ". I'd be glad to share anything else that would help, or to arrange a "
            "short call at your convenience.\n\nThank you for your time,\n" + name)


def send_followups(store, bus, ids: list[int]) -> dict:
    """The owner tapped SEND ALL on follow-ups (that tap is their yes)."""
    from . import channels as ch
    if not ch.email_ready():
        return {"error": "E-mail sending isn't set up yet (/email on Telegram)."}
    sent = 0
    for jid in ids:
        rows = store.query("SELECT * FROM jobs WHERE id = ? AND status = 'emailed'", (jid,))
        if not rows:
            continue
        j = rows[0]
        mid = store.queue_message("email", j["apply_email"], followup_text(j), "ZEUS", subject=f"Following up: {j['title']} application"[:120],
                                  recipient_name=j["company"] or j["apply_email"], reason="job follow-up (owner tapped SEND ALL)", status="approved")
        if ch.deliver(store, bus, store.get_message(mid)):
            sent += 1
            store.execute("UPDATE jobs SET status = 'followed', acted = ? WHERE id = ?", (datetime.now(settings.tz).isoformat(timespec="minutes"), jid))
    if bus:
        bus.publish({"type": "data", "what": "jobs"})
    return {"sent": sent}


def morning(store, bus) -> None:
    """07:50: hunt quietly. ZEUS reports what he found in the boss's daily briefing (boardroom.py)."""
    hunt(store, bus)


# ---------------------------------------------------------------- ZEUS's tools
from .tools import ToolContext, tool  # noqa: E402

_LIST = {"type": "array", "items": {"type": "string"}}


@tool("job_prefs", "Set what jobs the owner wants: roles (search terms like 'marketing executive', 'event coordinator'), "
      "locations, min_salary (SGD/month), types (full time, part time, contract, internship), avoid (companies or words "
      "to skip), daily_target (applications a day). Only pass what changed.",
      {"roles": _LIST, "locations": _LIST, "min_salary": {"type": "integer"}, "types": _LIST, "avoid": _LIST, "daily_target": {"type": "integer"}})
def job_prefs(ctx: ToolContext, **changes) -> dict:
    p = prefs(ctx.store)
    p.update({k: v for k, v in changes.items() if v not in (None, "", [])})
    ctx.store.set("jobs:prefs", json.dumps(p))
    return {"prefs": p, "resume_on_file": bool(resume_text())}


@tool("job_hunt", "Find fresh jobs now (MyCareersFuture + the owner's job-alert e-mails from JobStreet, LinkedIn, Indeed), "
      "rank them against the resume and line them up on the JOB HUNT screen. Returns how many are ready.", {})
def job_hunt(ctx: ToolContext) -> dict:
    out = hunt(ctx.store, ctx.bus)
    out["top"] = [{"title": j["title"], "company": j["company"], "fit": j["fit"], "why": j["why"]} for j in queue(ctx.store, 8)]
    out["applied_today"] = today_count(ctx.store)
    out["screen"] = "Tell the owner: open 🎯 JOB HUNT (phone home screen or /jobs.html) and tap APPLY on each."
    return out


@tool("job_queue", "The lined-up jobs (best fit first) and how many applications were done today.", {"limit": {"type": "integer"}})
def job_queue(ctx: ToolContext, limit: int = 15) -> dict:
    return {"applied_today": today_count(ctx.store), "target": prefs(ctx.store)["daily_target"],
            "jobs": [{k: j[k] for k in ("id", "title", "company", "salary", "fit", "why", "source", "status")} for j in queue(ctx.store, limit)],
            "can_email": len(email_ready(ctx.store))}
