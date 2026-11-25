"""VERONICA's money tracker: your bank and card alert e-mails become a monthly P&L.

Every bank / payment alert in Gmail ("A transaction of SGD 45.90 was made ... at GRAB*FOOD", "You have received
SGD 2,000.00 ...") becomes one transaction: amount, money in or out, merchant and a category (food, transport,
clothes...). VERONICA then gives the monthly P&L: money in, money out by category, and what's left.

Read-only and safe: only e-mails from banks and payment services are read, one-time codes are never read, account and
card numbers are never stored (only amount, merchant, category, bank name). JARVIS still can't open bank apps or sites,
and never moves money. Teach a category once ("VERONICA, Koufu is food") and it sticks.
"""
from __future__ import annotations

import email.utils
import json
import re
from datetime import date, datetime, timedelta

from .config import settings
from .guard import blocked, has_code

# ---------------------------------------------------------------- reading one alert
_NUM = r"([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
AMOUNT_RE = re.compile(rf"(?:SGD|S\$|USD|US\$|\$)\s?{_NUM}(?!\d)", re.I)
NOT_THE_AMOUNT = re.compile(r"(balance|limit|available|minimum|outstanding|statement)[^.$]{0,25}$", re.I)
IN_RE = re.compile(r"\b(credited|received|deposit(?:ed)?|incoming|salary|payroll|refund(?:ed)?|reversal|cashback|"
                   r"sent you|paid you|has been paid to you|inward|into your account|transfer(?:red)? to you)\b", re.I)
OUT_RE = re.compile(r"\b(debited|charged|spent|transaction of|purchase|payment (?:made|of|to)|you(?:'ve| have)? paid|"
                    r"paid to|withdrawn|withdrawal|transferred|you sent|bill payment|giro|deducted|card transaction|"
                    r"transaction alert|was made)\b", re.I)
SKIP_RE = re.compile(r"\b(declined|unsuccessful|not successful|failed|was not processed|cancelled|e-?statement is ready|"
                     r"statement is now available|minimum payment due|payment due)\b", re.I)
OWN_RE = re.compile(r"\b(own account|between your (?:own )?accounts|to your (?:own )?(?:dbs|posb|ocbc|uob|savings|account))\b", re.I)
MERCHANT_RES = [re.compile(p, re.I) for p in (
    r"\bat\s+([A-Za-z0-9*&'.@/\- ]{2,40}?)(?=\s+on\s|\s+for\s|\s*[.,;(]|\s+using|\s+with|\s*$)",
    r"\bto\s+([A-Za-z0-9*&'.@/\- ]{2,40}?)(?=\s+on\s|\s+via\s|\s+for\s|\s*[.,;(]|\s+from|\s*$)",
    r"\bfrom\s+([A-Za-z0-9*&'.@/\- ]{2,40}?)(?=\s+on\s|\s+via\s|\s+to\s|\s*[.,;(]|\s*$)",
    r"\bmerchant(?: name)?\s*[:\-]\s*([^\n.,]{2,40})",
    r"\b(?:description|to|recipient|payee)\s*[:\-]\s*([^\n.,]{2,40})",
)]
_JUNK_MERCHANT = re.compile(r"^(your|you|the|a|an|account|card|this|our|us|sgd|s\$|\$|•+|\d+)\b", re.I)


def parse_alert(subject: str, body: str) -> dict | None:
    """One bank alert -> {amount (signed: + in, - out), merchant, own_transfer}. None if it isn't a transaction."""
    text = re.sub(r"\s+", " ", f"{subject or ''}. {body or ''}")[:3000]
    if has_code(text) or SKIP_RE.search(text):
        return None
    amount = None
    for m in AMOUNT_RE.finditer(text):
        if NOT_THE_AMOUNT.search(text[max(0, m.start() - 40):m.start()]):
            continue   # "available balance: $3,000" is not the transaction
        amount = float(m.group(1).replace(",", ""))
        break
    if not amount:
        return None
    # table-style alerts (DBS/POSB PayNow, FAST, transfers): "From: <you> A/C ending 1234   To: <someone>"
    own = r"[^:]{0,40}?\b(?:a/?c|acct|account|card)\b[^:]{0,12}?\bending\b"
    field = lambda name: re.search(rf"\b{name}\s*:\s*([^:(]{{2,40}}?)(?=\s*\(|\s+(?:if|from|to|date|amount|ref\w*)\b|\s*$)", text, re.I)
    merchant = ""
    if re.search(rf"\bfrom\s*:{own}", text, re.I):
        sign, f = -1, field("to")
        merchant = f.group(1).strip() if f else ""
    elif re.search(rf"\bto\s*:{own}", text, re.I):
        sign, f = 1, field("from")
        merchant = f.group(1).strip() if f else ""
    else:
        inn, out = IN_RE.search(text), OUT_RE.search(text)
        if inn and (not out or inn.start() < out.start()):
            sign = 1
        elif out:
            sign = -1
        else:
            return None   # an amount but no clue which way: not a transaction alert
    if merchant and not _JUNK_MERCHANT.match(merchant) and not re.search(r"\d{4,}", merchant):
        return {"amount": round(sign * amount, 2), "merchant": merchant[:40], "own_transfer": bool(OWN_RE.search(text))}
    merchant = ""
    for rx in MERCHANT_RES:
        for mm in rx.finditer(text):
            cand = mm.group(1).strip(" -*.")
            if len(cand) >= 2 and not _JUNK_MERCHANT.match(cand) and not re.search(r"\d{4,}", cand):
                merchant = cand
                break
        if merchant:
            break
    return {"amount": round(sign * amount, 2), "merchant": merchant[:40], "own_transfer": bool(OWN_RE.search(text))}


# ---------------------------------------------------------------- categories
CATEGORIES = [   # first match wins; checked against the merchant, then the whole alert
    ("food", ["grabfood", "grab food", "foodpanda", "deliveroo", "mcdonald", "kfc", "burger king", "subway", "starbucks",
              "coffee", "kopi", "toast box", "ya kun", "koufu", "kopitiam", "food republic", "foodfare", "food court",
              "restaurant", "cafe", "café", "bakery", "bbq", "sushi", "ramen", "pizza", "mala", "chicken rice", "hawker",
              "bistro", "jollibee", "mos burger", "popeyes", "gong cha", "liho", "koi the", "chagee", "playmade",
              "each a cup", "mr bean", "old chang kee", "din tai fung", "texas chicken", "nando", "astons", "saizeriya",
              "pastamania", "4fingers", "fish & co", "bengawan", "prata", "bubble tea", "dessert", "canteen", "eatery"]),
    ("groceries", ["fairprice", "ntuc", "cold storage", "giant", "sheng siong", "don don donki", "donki", "prime supermarket",
                   "grabmart", "redmart", "7-eleven", "7 eleven", "cheers", "mustafa", "supermarket"]),
    ("transport", ["gojek", "tada", "ryde", "comfort", "cdg", "zig", "ez-link", "ezlink", "simplygo", "transitlink",
                   "smrt", "sbs transit", "bus/mrt", "taxi", "shell", "esso", "spc", "caltex", "parking", "grab"]),
    ("clothes", ["uniqlo", "zara", "h&m", "h & m", "cotton on", "pull&bear", "bershka", "shein", "nike", "adidas",
                 "puma", "new balance", "charles & keith", "pedro", "love bonito", "mango", "under armour", "asos",
                 "zalora", "foot locker", "skechers", "levi", "apparel", "fashion", "clothing", "converse", "vans",
                 "lululemon", "gu ", "muji"]),
    ("shopping", ["shopee", "lazada", "amazon", "taobao", "qoo10", "temu", "aliexpress", "ikea", "courts", "harvey norman",
                  "best denki", "challenger", "daiso", "popular", "kinokuniya", "typo", "miniso"]),
    ("subscriptions", ["netflix", "spotify", "apple.com", "itunes", "youtube", "disney", "icloud", "chatgpt", "openai",
                       "anthropic", "claude", "microsoft", "adobe", "canva", "prime video", "google storage", "google one"]),
    ("bills", ["singtel", "starhub", "m1 ", "m1limited", "circles", "giga", "simba", "sp services", "sp group",
               "town council", "insurance", "aia", "prudential", "great eastern", "income insurance", "iras", "hdb",
               "rent", "conservancy"]),
    ("entertainment", ["golden village", "gv ", "shaw", "cathay", "cinema", "steam", "playstation", "nintendo", "xbox",
                       "klook", "sistic", "ticketmaster", "concert", "bowling", "arcade", "timezone", "karaoke", "ktv"]),
    ("health", ["guardian", "watsons", "unity", "clinic", "pharmacy", "polyclinic", "hospital", "dental", "gym",
                "fitness", "activesg", "anytime fitness", "physio"]),
    ("education", ["smu", "nus", "ntu", "suss", "udemy", "coursera", "tuition", "school"]),
    ("travel", ["singapore airlines", "scoot", "jetstar", "airasia", "agoda", "booking.com", "airbnb", "expedia",
                "trip.com", "hotel", "changi", "klm", "emirates", "cathay pacific"]),
    ("haircut & grooming", ["barber", "salon", "hair", "nail", "spa"]),
]
INCOME_CATEGORIES = [("salary", ["salary", "payroll", "sal ", "wages", "pay from"]),
                     ("refund", ["refund", "reversal", "cashback", "rebate"])]


def rules(store) -> dict:
    try:
        return json.loads(store.get("money:rules") or "{}")
    except ValueError:
        return {}


def categorize(store, merchant: str, text: str, amount: float) -> str:
    norm = lambda x: re.sub(r"[*_]+|\s+", " ", (x or "").lower())   # "GRAB*FOOD" -> "grab food"
    m, t = norm(merchant), norm(text)
    for key, cat in rules(store).items():   # what the owner taught VERONICA comes first
        if key in m or (key and key in t):
            return cat
    if amount > 0:
        for cat, words in INCOME_CATEGORIES:
            if any(w in t for w in words):
                return cat
        return "income"
    for hay in (m, t):
        for cat, words in CATEGORIES:
            if any(w in hay for w in words):
                if cat == "transport" and re.search(r"grab\s*\*?\s*(food|mart)", hay):
                    continue
                return cat
    if re.search(r"\bpaynow\b|\bpaylah\b|\btransfer", t):
        return "transfers"
    return "other"


# ---------------------------------------------------------------- syncing from the inbox
def _ensure(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS bank_seen (key TEXT PRIMARY KEY, tx_id INTEGER, created TEXT)")


def _day_of(hdr: str) -> str:
    try:
        return email.utils.parsedate_to_datetime(hdr).astimezone(settings.tz).date().isoformat()
    except Exception:  # noqa: BLE001
        return datetime.now(settings.tz).date().isoformat()


def bank_name(sender: str) -> str:
    s = (sender or "").lower()
    for n in ("posb", "dbs", "ocbc", "uob", "citi", "hsbc", "maybank", "standard chartered", "trust", "gxs", "maribank",
              "revolut", "youtrip", "paypal", "grabpay", "paylah", "wise"):
        if n in s:
            return n.upper() if len(n) <= 4 else n.title()
    return email.utils.parseaddr(sender or "")[0][:20] or "Bank"


def add(store, day: str, amount: float, category: str, note: str, key: str) -> int | None:
    _ensure(store)
    if store.query("SELECT 1 FROM bank_seen WHERE key = ?", (key,)):
        return None
    tx = store.log_transaction(day, amount, category, note) if amount else 0
    store.execute("INSERT INTO bank_seen (key, tx_id, created) VALUES (?,?,?)", (key, tx, datetime.now(settings.tz).isoformat()))
    return tx


def sync(store, days: int = 40) -> dict:
    """Read new bank alert e-mails into the ledger. Safe to run often: each e-mail is only counted once."""
    from . import channels as ch
    if not ch.email_read_ready():
        return {"error": "E-mail reading isn't set up yet (send /email to the bot once).", "added": 0}
    _ensure(store)
    added, seen = [], {r["key"] for r in store.query("SELECT key FROM bank_seen")}
    for m in ch.bank_mail(days, skip=seen):
        key = f"mail:{m['uid']}:{(m.get('message_id') or '')[:60]}"
        if key in seen or not blocked(m.get("from")):   # only e-mails from banks and payment services
            continue
        p = parse_alert(m.get("subject", ""), m.get("body", ""))
        if not p or p["own_transfer"]:
            add(store, _day_of(m.get("date")), 0, "", "", key)   # remember it, but it isn't spending or income
            continue
        cat = categorize(store, p["merchant"], f"{m.get('subject', '')} {m.get('body', '')[:600]}", p["amount"])
        note = f"{p['merchant'] or ('received' if p['amount'] > 0 else 'payment')} · {bank_name(m.get('from'))} (alert)"
        if add(store, _day_of(m.get("date")), p["amount"], cat, note, key):
            added.append({"day": _day_of(m.get("date")), "amount": p["amount"], "category": cat, "merchant": p["merchant"]})
    store.set("money:synced", datetime.now(settings.tz).isoformat(timespec="minutes"))
    return {"added": len(added), "new": added[-10:]}


# ---------------------------------------------------------------- the monthly P&L
def _month_range(month: str) -> tuple[str, str]:
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), m % 12 + 1, 1)
    return start.isoformat(), end.isoformat()


def report(store, month: str | None = None) -> dict:
    today = datetime.now(settings.tz).date()
    month = month or today.strftime("%Y-%m")
    a, b = _month_range(month)
    rows = store.query("SELECT day, amount, category, note FROM transactions WHERE day >= ? AND day < ? ORDER BY day", (a, b))
    income = [r for r in rows if r["amount"] > 0]
    spend = [r for r in rows if r["amount"] < 0]
    tin, tout = round(sum(r["amount"] for r in income), 2), round(-sum(r["amount"] for r in spend), 2)
    by, inc_by, merch = {}, {}, {}
    for r in spend:
        c = by.setdefault(r["category"], {"category": r["category"], "amount": 0.0, "count": 0})
        c["amount"] += -r["amount"]
        c["count"] += 1
        name = (r["note"] or "").split(" · ")[0].strip() or r["category"]
        merch[name] = merch.get(name, 0) + -r["amount"]
    for r in income:
        inc_by[r["category"]] = round(inc_by.get(r["category"], 0) + r["amount"], 2)
    cats = sorted(by.values(), key=lambda c: -c["amount"])
    for c in cats:
        c["amount"] = round(c["amount"], 2)
        c["pct"] = round(c["amount"] / tout * 100) if tout else 0
    prev = (date.fromisoformat(a) - timedelta(days=1)).strftime("%Y-%m")
    pa, pb = _month_range(prev)
    prow = store.query("SELECT SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END) AS out, "
                       "SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) AS inn FROM transactions WHERE day >= ? AND day < ?", (pa, pb))[0]
    days_in = (date.fromisoformat(b) - date.fromisoformat(a)).days
    elapsed = min(days_in, (today - date.fromisoformat(a)).days + 1) if month == today.strftime("%Y-%m") else days_in
    return {
        "month": month, "income": tin, "spent": tout, "net": round(tin - tout, 2),
        "saved_pct": round((tin - tout) / tin * 100) if tin else None,
        "income_by": inc_by, "by_category": cats,
        "top_merchants": [{"merchant": k, "amount": round(v, 2)} for k, v in sorted(merch.items(), key=lambda x: -x[1])[:6]],
        "biggest": sorted(({"day": r["day"], "amount": -r["amount"], "what": r["note"]} for r in spend), key=lambda x: -x["amount"])[:5],
        "last_month": {"month": prev, "spent": round(prow["out"] or 0, 2), "income": round(prow["inn"] or 0, 2)},
        "pace_full_month": round(tout / elapsed * days_in, 2) if elapsed and month == today.strftime("%Y-%m") else None,
        "transactions": len(rows), "synced": store.get("money:synced"),
    }


ICONS = {"food": "🍜", "groceries": "🛒", "transport": "🚗", "clothes": "👕", "shopping": "🛍", "subscriptions": "📺",
         "bills": "🧾", "entertainment": "🎬", "health": "💊", "education": "🎓", "travel": "✈️", "transfers": "🔁",
         "haircut & grooming": "💈", "other": "•", "salary": "💼", "income": "💰", "refund": "↩️"}


def text(r: dict) -> str:
    """The P&L as a message."""
    mname = datetime.strptime(r["month"], "%Y-%m").strftime("%B %Y")
    sign = "+" if r["net"] >= 0 else "−"
    lines = [f"📊 VERONICA · {mname} P&L", ""]
    lines.append(f"💰 Money in:  ${r['income']:,.2f}" + (" (" + ", ".join(f"{k} ${v:,.0f}" for k, v in r["income_by"].items()) + ")" if r["income_by"] else ""))
    lines.append(f"💸 Money out: ${r['spent']:,.2f}")
    lines.append(f"📈 Net:       {sign}${abs(r['net']):,.2f}" + (f" · you kept {r['saved_pct']}%" if r["saved_pct"] is not None and r["net"] >= 0 else ""))
    if r["by_category"]:
        lines += ["", "Where it went:"]
        lines += [f"{ICONS.get(c['category'], '•')} {c['category'].title()}: ${c['amount']:,.2f} ({c['pct']}%) · {c['count']}×" for c in r["by_category"]]
    if r["top_merchants"]:
        lines += ["", "Top spots: " + ", ".join(f"{t['merchant']} ${t['amount']:,.0f}" for t in r["top_merchants"][:4])]
    lm = r["last_month"]
    if lm["spent"]:
        diff = r["spent"] - lm["spent"]
        lines.append(f"vs last month: {'+' if diff >= 0 else '−'}${abs(diff):,.0f} spending")
    if r["pace_full_month"]:
        lines.append(f"At this pace: about ${r['pace_full_month']:,.0f} by month end.")
    return "\n".join(lines)


def spoken(r: dict) -> str:
    """One line in VERONICA's voice."""
    if not r["transactions"]:
        return "Nothing in the books yet this month, darling. Either you're a saint or the bank alerts aren't reaching me."
    top = r["by_category"][0] if r["by_category"] else None
    net = (f"you're up ${r['net']:,.0f}" if r["net"] >= 0 else f"you're down ${-r['net']:,.0f}")
    return (f"${r['income']:,.0f} in, ${r['spent']:,.0f} out, so {net}."
            + (f" Biggest drain: {top['category']}, ${top['amount']:,.0f}." if top else ""))


def monthly(store, bus) -> None:
    """On the 1st: last month's P&L to Telegram, the dashboard and out loud."""
    today = datetime.now(settings.tz).date()
    if today.day != 1 or store.get("money:last_monthly") == today.isoformat():
        return
    store.set("money:last_monthly", today.isoformat())
    try:
        sync(store)
    except Exception:  # noqa: BLE001
        pass
    r = report(store, (today - timedelta(days=1)).strftime("%Y-%m"))
    if not r["transactions"]:
        return
    from .speech import announce
    from .notify import notify_owner
    body = text(r)
    subs = subscriptions(store)
    if subs:
        body += (f"\n\n🔁 Subscriptions: ${sum(x['monthly'] for x in subs):,.2f}/month: "
                 + ", ".join(f"{x['merchant']} ${x['monthly']:,.2f}" for x in subs[:8]) + ". Still using all of them?")
    rid = store.save_report("money", "VERONICA", body.splitlines()[0], body)
    bus.publish({"type": "report", "id": rid, "agent": "VERONICA", "title": body.splitlines()[0], "kind": "money"})
    notify_owner(body.splitlines()[0], body)
    announce(bus, "VERONICA", "Last month's books are closed. " + spoken(r))


# ---------------------------------------------------------------- budgets: a heads-up at 80% and 100%
def budgets(store) -> dict:
    try:
        return {k: float(v) for k, v in json.loads(store.get("money:budgets") or "{}").items()}
    except ValueError:
        return {}


def budget_status(store) -> list[dict]:
    b = budgets(store)
    if not b:
        return []
    r = report(store)
    spent = {c["category"]: c["amount"] for c in r["by_category"]}
    out = [{"category": k, "budget": v, "spent": round(spent.get(k, 0), 2), "pct": round(spent.get(k, 0) / v * 100) if v else 0}
           for k, v in b.items()]
    if "total" in b:
        out = [o for o in out if o["category"] != "total"] + [{"category": "total", "budget": b["total"], "spent": r["spent"],
                                                                "pct": round(r["spent"] / b["total"] * 100) if b["total"] else 0}]
    return sorted(out, key=lambda o: -o["pct"])


def budget_check(store, bus) -> list[str]:
    """After each sync: VERONICA speaks up once when a category passes 80%, and again at 100%."""
    month, said = datetime.now(settings.tz).strftime("%Y-%m"), []
    days_left = (date.fromisoformat(_month_range(month)[1]) - datetime.now(settings.tz).date()).days
    for o in budget_status(store):
        for level in (100, 80):
            key = f"money:budget_alert:{month}:{o['category']}:{level}"
            if o["pct"] >= level and not store.get(key):
                store.set(key, "1")
                what = "your whole budget" if o["category"] == "total" else o["category"]
                msg = (f"{what.title()} is at ${o['spent']:,.0f} of ${o['budget']:,.0f}" + (" and over budget" if level == 100 else f" ({o['pct']}%)")
                       + f", with {days_left} day{'s' if days_left != 1 else ''} to go this month.")
                said.append(msg)
                from .notify import notify_owner
                from .speech import announce
                notify_owner("💸 VERONICA: budget", msg, short=True)
                announce(bus, "VERONICA", ("[scoffs] " if level == 100 else "") + msg)
                break
    return said


# ---------------------------------------------------------------- subscriptions: what keeps charging you
SUB_WORDS = ["netflix", "spotify", "apple.com", "itunes", "youtube", "disney", "icloud", "chatgpt", "openai", "claude", "anthropic",
             "microsoft", "adobe", "canva", "prime", "google one", "google storage", "gym", "fitness", "singtel", "starhub",
             "circles", "giga", "simba", "m1", "patreon", "xbox", "playstation", "nintendo", "steam", "crunchyroll", "viu", "hbo"]


def subscriptions(store, months: int = 4) -> list[dict]:
    """Charges that repeat month after month (or come from known subscription services)."""
    since = (datetime.now(settings.tz).date().replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1).isoformat()
    rows = store.query("SELECT day, amount, note, category FROM transactions WHERE amount < 0 AND day >= ?", (since,))
    by = {}
    for r in rows:
        name = (r["note"] or "").split(" · ")[0].strip()
        key = re.sub(r"[^a-z]", "", name.lower())[:14]
        if not key:
            continue
        by.setdefault(key, {"merchant": name, "rows": []})["rows"].append(r)
    out = []
    for g in by.values():
        amts = [-r["amount"] for r in g["rows"]]
        months_seen = {r["day"][:7] for r in g["rows"]}
        typical = sorted(amts)[len(amts) // 2]
        steady = len(months_seen) >= 2 and all(abs(a - typical) <= max(2, typical * .2) for a in amts)
        known = any(w in g["merchant"].lower() for w in SUB_WORDS) or g["rows"][0]["category"] == "subscriptions"
        if (steady and len(g["rows"]) <= len(months_seen) + 1) or known:
            out.append({"merchant": g["merchant"], "monthly": round(typical, 2), "months": len(months_seen),
                        "last": max(r["day"] for r in g["rows"])})
    return sorted(out, key=lambda x: -x["monthly"])


# ---------------------------------------------------------------- VERONICA's tools
from .tools import ToolContext, tool  # noqa: E402

_M = {"type": "string", "description": "YYYY-MM (default this month)"}


@tool("money_report", "The owner's monthly P&L from their bank alert e-mails (plus anything logged by hand): money in "
      "(salary, transfers), money out by category with %, net, top merchants, biggest buys, vs last month, and the pace "
      "for this month. Syncs new bank alerts first. Use for 'how much did I spend', 'my P&L', 'where's my money going'.",
      {"month": _M})
def money_report(ctx: ToolContext, month: str = "") -> dict:
    try:
        s = sync(ctx.store)
    except Exception as exc:  # noqa: BLE001
        s = {"error": str(exc)[:120]}
    r = report(ctx.store, month or None)
    return {**r, "as_text": text(r), "sync": s}


@tool("money_transactions", "The individual transactions for a month (optionally one category), newest first.",
      {"month": _M, "category": {"type": "string"}})
def money_transactions(ctx: ToolContext, month: str = "", category: str = "") -> list:
    a, b = _month_range(month or datetime.now(settings.tz).strftime("%Y-%m"))
    rows = ctx.store.query("SELECT id, day, amount, category, note FROM transactions WHERE day >= ? AND day < ?"
                           + (" AND category = ?" if category else "") + " ORDER BY day DESC, id DESC LIMIT 200",
                           (a, b, category.lower()) if category else (a, b))
    return rows


@tool("money_budget", "Set monthly budgets per category (e.g. food 400, transport 150, total 1500). auto=true sets them "
      "from last month's spending (+10%, rounded). VERONICA warns at 80% and 100%.",
      {"category": {"type": "string"}, "amount": {"type": "number"}, "auto": {"type": "boolean"}})
def money_budget(ctx: ToolContext, category: str = "", amount: float = 0, auto: bool = False) -> dict:
    b = budgets(ctx.store)
    if auto:
        prev = report(ctx.store, (datetime.now(settings.tz).date().replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))
        for c in prev["by_category"]:
            if c["category"] not in ("transfers", "other"):
                b[c["category"]] = float(round(c["amount"] * 1.1 / 10 + .5) * 10)
    elif category:
        if amount and amount > 0:
            b[category.lower()] = float(amount)
        else:
            b.pop(category.lower(), None)
    ctx.store.set("money:budgets", json.dumps(b))
    return {"budgets": b, "status": budget_status(ctx.store)}


@tool("money_subscriptions", "Everything that keeps charging the owner monthly (from the books), with the monthly total. "
      "Ask which ones they still use; they cancel, you never do.", {})
def money_subscriptions(ctx: ToolContext) -> dict:
    subs = subscriptions(ctx.store)
    return {"subscriptions": subs, "monthly_total": round(sum(x["monthly"] for x in subs), 2)}


@tool("money_categorize", "Teach VERONICA a category for a merchant or word (e.g. 'koufu' -> food, 'uncle tan' -> rent). "
      "It's remembered for the future and fixes this month's matching transactions too.",
      {"merchant": {"type": "string"}, "category": {"type": "string"}}, ["merchant", "category"])
def money_categorize(ctx: ToolContext, merchant: str, category: str) -> dict:
    key, cat = merchant.strip().lower(), category.strip().lower()
    r = rules(ctx.store)
    r[key] = cat
    ctx.store.set("money:rules", json.dumps(r))
    n = 0
    for row in ctx.store.query("SELECT id, note FROM transactions WHERE lower(note) LIKE ?", (f"%{key}%",)):
        ctx.store.execute("UPDATE transactions SET category = ? WHERE id = ?", (cat, row["id"]))
        n += 1
    return {"rule": {key: cat}, "updated": n}
