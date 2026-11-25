"""ZEUS's job hunt: find, rank, one-tap apply, and e-mail applications only on the owner's SEND ALL."""
from types import SimpleNamespace

from jarvis import jobs
from jarvis.store import Store

ALERT = """<html><body>
<a href="https://www.jobstreet.com.sg/job/81234567?ref=alert">Marketing Executive</a><div>ACME Pte Ltd</div><div>Central Region</div>
<a href="https://sg.linkedin.com/comm/jobs/view/3999?trk=x">Event Coordinator</a><div>Big Events Co</div>
<a href="https://www.jobstreet.com.sg/unsubscribe">Unsubscribe</a><a href="https://www.jobstreet.com.sg/job/1">View all jobs</a>
</body></html>"""


def test_job_alert_emails_become_jobs():
    got = jobs.from_alert_html(ALERT, "JobStreet")
    titles = [j["title"] for j in got]
    assert titles == ["Marketing Executive", "Event Coordinator"]
    assert got[0]["company"] == "ACME Pte Ltd" and "jobstreet" in got[0]["url"]


def test_apply_email_only_when_the_ad_asks():
    assert jobs._apply_email("Interested applicants please send your CV to hr@acme.sg by Friday") == "hr@acme.sg"
    assert jobs._apply_email("Questions? no-reply@acme.sg") == ""


def test_hunt_rank_queue_and_mark(monkeypatch, tmp_path):
    st = Store(":memory:")
    monkeypatch.setattr(jobs, "CAREER", tmp_path)
    (tmp_path / "resume.txt").write_text("Events and marketing: ran events for 300 guests, social media, Canva, team of 30")
    st.set("jobs:prefs", '{"roles": ["marketing executive"]}')
    monkeypatch.setattr(jobs, "from_mcf", lambda q, n=60: [
        {"source": "MyCareersFuture", "title": "Marketing Executive", "company": "ACME", "url": "https://mcf/job/1",
         "descr": "social media marketing events canva", "apply_email": "hr@acme.sg"},
        {"source": "MyCareersFuture", "title": "Senior Software Engineer", "company": "Tech", "url": "https://mcf/job/2", "descr": "kubernetes golang"}])
    monkeypatch.setattr(jobs, "from_alert_mail", lambda days=3: jobs.from_alert_html(ALERT, "JobStreet"))
    monkeypatch.setattr(jobs, "llm", lambda *a, **k: "")
    out = jobs.hunt(st)
    assert out["added"] == 4 and jobs.hunt(st)["added"] == 0          # never twice
    q = jobs.queue(st)
    assert q[0]["title"] == "Marketing Executive" and q[-1]["title"] == "Senior Software Engineer"   # best fit first
    assert "Marketing Executive" in jobs.prep(st, q[0]["id"])["cover"]
    assert jobs.mark(st, q[0]["id"], "applied")["today"] == 1
    assert st.list_applications("applied")[0]["role"] == "Marketing Executive"   # into ZEUS's tracker


def test_email_applications_need_the_send_all_tap(monkeypatch, tmp_path):
    from jarvis import channels as ch
    st = Store(":memory:")
    monkeypatch.setattr(jobs, "CAREER", tmp_path)
    (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4 cv")
    (tmp_path / "resume.txt").write_text("events")
    monkeypatch.setattr(jobs, "llm", lambda *a, **k: "")
    jobs.add_job(st, {"source": "MCF", "title": "Event Coordinator", "company": "Big Events", "url": "u", "apply_email": "hr@big.sg", "descr": "events"})
    jid = st.query("SELECT id FROM jobs")[0]["id"]
    assert st.query("SELECT COUNT(*) AS n FROM outbox")[0]["n"] == 0   # nothing goes out by itself
    sent = []
    monkeypatch.setattr(ch, "email_ready", lambda: True)
    monkeypatch.setattr(ch, "deliver", lambda store, bus, msg: sent.append(msg) or True)
    out = jobs.send_all(st, SimpleNamespace(publish=lambda e: None), [jid])
    assert out["sent"] == 1 and sent[0]["recipient"] == "hr@big.sg" and sent[0]["attachment"].endswith("resume.pdf")


def test_zeus_has_the_hunt():
    from jarvis.agents import AGENTS
    assert {"job_prefs", "job_hunt", "job_queue"} <= set(AGENTS["ZEUS"].tools)
