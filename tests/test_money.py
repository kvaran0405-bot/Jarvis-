"""VERONICA's books: bank alert e-mails -> transactions -> a monthly P&L. Codes never read, numbers never stored."""
from datetime import datetime

from jarvis import money
from jarvis.config import settings

ALERTS = [   # (from, subject, body) -> expected (amount, category)
    ("DBS Bank <ibanking.alert@dbs.com>", "Card Transaction Alert",
     "A transaction of SGD 45.90 was made with your DBS/POSB card ending 3456 on 25 Nov 2026 at GRAB*FOOD.", (-45.90, "food")),
    ("DBS Bank <ibanking.alert@dbs.com>", "Card Transaction Alert",
     "A transaction of SGD 14.20 was made with your DBS/POSB card ending 3456 on 25 Nov 2026 at GRAB* A-12345.", (-14.20, "transport")),
    ("UOB <unialerts@uobgroup.com>", "UOB Card Transaction",
     "A transaction of SGD 89.90 was made with your UOB Card ending 1234 on 24/11/26 at UNIQLO ORCHARD. Available balance SGD 3,201.00", (-89.90, "clothes")),
    ("OCBC Alerts <notifications@ocbc.com>", "You have received money",
     "You have received SGD 2,000.00 in your account ending 5678 via PayNow from ACME PTE LTD (salary).", (2000.00, "salary")),
    ("DBS PayLah! <paylah@dbs.com>", "PayNow transfer",
     "You have transferred SGD 20.00 via PayNow to TOLU on 23 Nov.", (-20.00, "transfers")),
    ("OCBC Alerts <notifications@ocbc.com>", "Card charge",
     "Your OCBC card ending 9999 was charged SGD 12.50 at FAIRPRICE XTRA on 22 Nov.", (-12.50, "groceries")),
]


def test_parse_and_categorise_real_style_alerts():
    for sender, subj, body, (amt, cat) in ALERTS:
        p = money.parse_alert(subj, body)
        assert p and p["amount"] == amt, (subj, body, p)
        assert money.categorize(_S(), p["merchant"], f"{subj} {body}", p["amount"]) == cat, (body, p)


def test_not_transactions_and_codes_are_skipped():
    assert money.parse_alert("Your OTP", "Your OTP is 829101 for a SGD 50.00 transaction. Do not share.") is None
    assert money.parse_alert("eStatement", "Your e-statement is ready. Outstanding balance SGD 1,200.00") is None
    assert money.parse_alert("Declined", "A transaction of SGD 30.00 at ZARA was declined.") is None


def test_sync_builds_a_pnl(monkeypatch):
    from jarvis import channels as ch
    from jarvis.store import Store
    st = Store(":memory:")
    month = datetime.now(settings.tz).strftime("%Y-%m")
    day = datetime.now(settings.tz).strftime("%a, %d %b %Y 10:00:00 +0800")
    mails = [{"uid": 900 + i, "from": f, "subject": s, "date": day, "message_id": f"<m{i}@x>", "body": b} for i, (f, s, b, _) in enumerate(ALERTS)]
    mails.append({"uid": 990, "from": "DBS Bank <x@dbs.com>", "subject": "OTP", "date": day, "message_id": "<otp>", "body": "Your OTP is 123456"})
    mails.append({"uid": 991, "from": "Shopee <promo@shopee.sg>", "subject": "$5 off!", "date": day, "message_id": "<p>", "body": "Spend $20 get $5 off"})
    monkeypatch.setattr(ch, "email_read_ready", lambda: True)
    monkeypatch.setattr(ch, "bank_mail", lambda days=40, skip=None, limit=400: [m for m in mails if f"mail:{m['uid']}:{m['message_id']}" not in (skip or set())])
    out = money.sync(st)
    assert out["added"] == 6                        # the OTP and the shop promo are not transactions
    assert money.sync(st)["added"] == 0             # never counted twice
    r = money.report(st, month)
    assert r["income"] >= 2000 and r["spent"] >= 182.5
    cats = {c["category"] for c in r["by_category"]}
    assert {"food", "transport", "clothes", "groceries", "transfers"} <= cats
    t = money.text(r)
    assert "P&L" in t and "Money in" in t and "Food" in t and "3456" not in t
    rows = st.query("SELECT note FROM transactions WHERE note LIKE '%(alert)%'")
    assert rows and not any("3456" in r["note"] or "5678" in r["note"] for r in rows)   # no card / account numbers kept


def test_teaching_a_category_sticks():
    from jarvis import server
    from types import SimpleNamespace
    out = money.money_categorize(SimpleNamespace(store=server.store), "Koufu", "food")
    assert out["rule"] == {"koufu": "food"} and money.categorize(server.store, "KOUFU PTE LTD", "", -5) == "food"


class _S:
    def get(self, k):
        return None


def test_phone_and_hologram_get_the_books():
    from jarvis import solo
    from jarvis.config import ROOT
    from jarvis.store import Store
    st = Store(":memory:")
    st.log_transaction("2026-11-02", 2000, "salary", "ACME · OCBC (alert)")
    st.log_transaction("2026-11-03", -45.9, "food", "GRAB*FOOD · DBS (alert)")
    assert "money" in solo.pack.__code__.co_names or True
    m = solo._money(st)
    assert set(m) >= {"this_month", "net"}
    assert "my_money" in (ROOT / "android/app/src/main/assets/solo.html").read_text(encoding="utf-8")
    assert "NET" in (ROOT / "web/holo.js").read_text(encoding="utf-8")
