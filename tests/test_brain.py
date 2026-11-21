"""Brain choice, the pause switch, limit fallback and the Gemini loop - all offline."""
import json

import pytest

from jarvis import brain, brains
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store


@pytest.fixture
def eng(monkeypatch):
    store = Store(":memory:")
    monkeypatch.setattr(settings, "brain", "auto")
    monkeypatch.setattr(settings, "automation_brain", "auto")
    return Engine(store, Bus(store), settings)


def test_pause_resume_saver_phrases(eng, monkeypatch):
    s = eng.store
    monkeypatch.setattr(brain, "ready", lambda b: b in ("pro", "gemini"))
    assert brain.pick(s) == "pro" and brain.pick(s, background=True) == "gemini"  # routines spare your plan
    assert "Paused until" in brain.handle_control(s, "Jarvis, pause for 2 hours")
    assert brain.pick(s) is None and brain.pick(s, background=True) is None
    assert "I'm paused" in eng.run("JARVIS", "hello")
    assert "Saver mode" in brain.handle_control(s, "save my claude")
    assert brain.pick(s) == "gemini"
    assert "Back online" in brain.handle_control(s, "resume")
    assert brain.pick(s) == "pro"
    for not_control in ("pause my spotify playlist", "what's my status on the essay", "remind me to resume work"):
        assert brain.handle_control(s, not_control) is None
    assert brain.handle_control(s, "/pause 30m") and brain.get_mode(s)["until"]


def test_pause_expires(eng):
    brain.set_mode(eng.store, "paused", hours=-1)  # already in the past
    assert brain.get_mode(eng.store)["mode"] == "on"


def test_pro_limit_falls_back_to_gemini(eng, monkeypatch):
    monkeypatch.setattr(brain, "ready", lambda b: b in ("pro", "gemini"))
    used = []

    def fake_think(which, *a, **k):
        used.append(which)
        if which == "pro":
            raise brains.LimitReached("Claude usage limit reached")
        return "answer from gemini"
    monkeypatch.setattr(eng, "_think", fake_think)
    assert eng.run("JARVIS", "hi") == "answer from gemini"
    assert used == ["pro", "gemini"] and brain.pro_limited(eng.store)
    assert brain.pick(eng.store) == "gemini"  # stays on the backup until the limit window passes


def test_gemini_tool_loop(eng, monkeypatch):
    monkeypatch.setattr(settings, "gemini_key", "g")
    sent = []
    replies = iter([
        {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "add_task", "args": {"title": "Read chapter 4", "area": "academic"}},
             "thoughtSignature": "sig123"}]}}]},
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "Added it, Sir."}]}}]},
    ])
    monkeypatch.setattr(brains, "_gemini_call", lambda body, model=None: sent.append(json.loads(json.dumps(body))) or next(replies))
    monkeypatch.setattr(brain, "ready", lambda b: b == "gemini")
    out = eng.run("ATHENA", "add reading chapter 4", chat=True)
    assert out == "Added it, Sir."
    assert eng.store.list_tasks()[0]["title"] == "Read chapter 4"
    second = sent[1]["contents"]
    assert second[1]["parts"][0]["thoughtSignature"] == "sig123"          # model turn sent back verbatim
    assert second[2]["parts"][0]["functionResponse"]["name"] == "add_task"
    decls = sent[0]["tools"][0]["functionDeclarations"]
    assert all("parameters" not in d or d["parameters"]["type"] == "object" for d in decls)


def test_suggested_replies_flow(eng, monkeypatch):
    """HERALD briefs an e-mail with options; the owner taps B on Telegram; the reply goes out threaded."""
    from jarvis import channels as ch
    from jarvis import telegram as tg
    from jarvis.tools import ToolContext, execute
    import jarvis.server as server
    shown, mails = [], []
    monkeypatch.setattr(tg, "ready", lambda: True)
    monkeypatch.setattr(tg, "send", lambda text, buttons=None, to=None: shown.append((text, buttons)))
    monkeypatch.setattr(ch, "email_ready", lambda: True)
    monkeypatch.setattr(ch, "send_email", lambda to, subject, body, reply_to="": mails.append((to, subject, body, reply_to)))
    monkeypatch.setattr(server, "store", eng.store)
    monkeypatch.setattr(server, "bus", eng.bus)
    ctx = ToolContext(eng.store, eng.bus, settings, eng, "HERALD")
    out, err = execute("suggest_replies", ctx, {
        "sender": "prof@univ.fr", "sender_name": "Prof. Martin", "subject": "Projet", "message_id": "<abc@univ.fr>",
        "language": "French", "translation": "Can you present your project on Monday?",
        "gist": "Prof. Martin wants you to present your project on Monday, Sir.",
        "options": [{"label": "Accept", "body": "Oui, avec plaisir."},
                    {"label": "Ask for Wednesday", "body": "Serait-il possible mercredi ?"}]})
    assert not err
    text, buttons = shown[0]
    assert "Translated from French" in text and "B) Ask for Wednesday" in text
    assert buttons[1][0][1] == "rp:1:1" and buttons[-1][0][1] == "ri:1"
    assert server.pick_reply(1, 1) == "✉ Sent to Prof. Martin."
    assert mails == [("prof@univ.fr", "Re: Projet", "Serait-il possible mercredi ?", "<abc@univ.fr>")]
    assert eng.store.get_suggestion(1)["status"] == "sent"
    assert "not open" in server.pick_reply(1, 0)  # can't send twice
    # owner's own words by text
    execute("suggest_replies", ctx, {"sender": "a@b.com", "gist": "x", "options": [{"label": "ok", "body": "ok"}]})
    assert "Sent" in server.handle_owner_message("reply 2: Thanks, see you then!", "Telegram")
    assert mails[-1][2] == "Thanks, see you then!"


def test_agent_notebook_is_private(eng):
    from jarvis.tools import ToolContext, execute
    execute("learn", ToolContext(eng.store, eng.bus, settings, eng, "HERALD"), {"note": "Sir likes short replies"})
    assert "Sir likes short replies" in eng._context_block(eng_agent("HERALD"))
    assert "Sir likes short replies" not in eng._context_block(eng_agent("ZEUS"))


def eng_agent(name):
    from jarvis.agents import AGENTS
    return AGENTS[name]


def test_proposal_yes_runs_plan_with_messages_preapproved(eng, monkeypatch):
    """An agent proposes; owner says yes; the agent's plan runs and its e-mail goes out without a second approval."""
    from jarvis import channels as ch
    from jarvis import telegram as tg
    from jarvis.actions import decide_proposal
    from jarvis.tools import ToolContext, execute
    cards, mails = [], []
    monkeypatch.setattr(tg, "ready", lambda: True)
    monkeypatch.setattr(tg, "send", lambda text, buttons=None, to=None: cards.append((text, buttons)))
    monkeypatch.setattr(ch, "email_ready", lambda: True)
    monkeypatch.setattr(ch, "send_email", lambda to, subject, body, reply_to="": mails.append((to, body)))
    eng.store.add_contact("Dr. Okafor", email="okafor@uni.edu")
    ctx = ToolContext(eng.store, eng.bus, settings, eng, "SENTINEL")
    out, _ = execute("propose", ctx, {"title": "Ask Dr. Okafor for a 2-day extension",
                                      "why": "Assignment 3 is due tomorrow and you have 2 exams",
                                      "plan": "Email Dr. Okafor: 'Could I have until Friday for assignment 3?'"})
    assert '"proposal_id": 1' in out and cards[-1][1][0][0][1] == "pa:1"
    out2, _ = execute("propose", ctx, {"title": "Ask Dr. Okafor for a 2-day extension", "plan": "same"})
    assert "Already proposed" in out2

    def fake_run(agent, prompt, approved=False, **kw):   # JARVIS carries out the approved plan
        assert agent == "JARVIS" and approved and "Carry out exactly this plan" in prompt
        c = ToolContext(eng.store, eng.bus, settings, eng, agent, 0, approved)
        r, _ = execute("send_email", c, {"to": "Dr. Okafor", "subject": "Assignment 3",
                                         "body": "Could I have until Friday for assignment 3?", "reason": "proposal 1"})
        return "Sent the extension request to Dr. Okafor."
    monkeypatch.setattr(eng, "run", fake_run)
    result = decide_proposal(eng, 1, True)
    assert "Sent the extension request" in result
    assert mails == [("okafor@uni.edu", "Could I have until Friday for assignment 3?")]   # no second approval needed
    assert eng.store.get_proposal(1)["status"] == "done"
    assert "isn't waiting" in decide_proposal(eng, 1, True)


def test_proposal_no_is_remembered(eng):
    from jarvis.actions import decide_proposal
    pid = eng.store.add_proposal("STEVE", "Move gym to 6am", "Move the gym block to 06:00")
    assert decide_proposal(eng, pid, False) == "Understood, I'll leave it."
    assert "said no to: Move gym to 6am" in eng.store.agent_notes("STEVE")[0]["note"]


def test_without_approval_email_still_waits(eng, monkeypatch):
    from jarvis.tools import ToolContext, execute
    monkeypatch.setattr(settings, "autonomy", "approve")
    eng.store.add_contact("Tolu", email="tolu@x.com")
    out, _ = execute("send_email", ToolContext(eng.store, eng.bus, settings, eng, "HERALD"),
                     {"to": "Tolu", "subject": "hi", "body": "hi", "reason": "x"})
    assert "approval" in out


def test_natural_answers(eng, monkeypatch):
    from jarvis import answers
    import jarvis.server as server
    monkeypatch.setattr(server, "store", eng.store)
    monkeypatch.setattr(server, "bus", eng.bus)
    for yes in ("yes", "Yeah do it", "sure, thanks", "go ahead jarvis", "OK."):
        assert answers.parse(yes) == ("yes", None), yes
    for no in ("nah", "No thanks", "leave it", "not now"):
        assert answers.parse(no) == ("no", None), no
    assert answers.parse("send the second one") == ("option", 1)
    assert answers.parse("B") == ("option", 1)
    for order in ("yes and also add a task for tomorrow", "no idea what to cook tonight", "book a table"):
        assert answers.parse(order) is None, order

    assert server.answer_naturally("yes") is None   # nothing on file: the agent's own conversation handles it
    # latest open item is an e-mail with reply options: "yes" asks which one, "send B" sends it
    picked = []
    monkeypatch.setattr(server, "pick_reply", lambda sid, opt, custom="": picked.append((sid, opt)) or "sent")
    sid = eng.store.add_suggestion(sender="a@b.c", gist="Tolu asks if you're coming", agent="HERALD",
                                   options=[{"label": "Yes", "body": "Coming!"}, {"label": "No", "body": "Can't, sorry"}])
    assert "Which one" in server.answer_naturally("yeah")
    assert server.answer_naturally("send the second one") == "sent" and picked == [(sid, 1)]
    # a newer proposal becomes the thing "yes" answers
    decided = []
    monkeypatch.setattr(server, "answer_proposal", lambda pid, yes: decided.append((pid, yes)) or "ok")
    import time
    time.sleep(1.1)  # created timestamps have 1-second resolution
    pid = eng.store.add_proposal("STEVE", "Book gym slot", "Add gym 6pm")
    server.answer_naturally("yes please")
    assert decided == [(pid, True)]
