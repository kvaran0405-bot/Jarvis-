"""The trailer starring the owner: safe-to-share data only, and exported videos are kept and sent to the phone."""
import json

from jarvis import trailer


def test_data_is_safe_to_show_friends():
    from jarvis import server
    st = server.store
    st.add_task("Secret task: call the bank about the loan")
    st.remember("Sir's PIN hint is his cat's name")
    st.set("places:saved", json.dumps({"home": [1.353, 103.944], "smu": [1.2966, 103.8502]}))
    d = trailer.data(st)
    blob = json.dumps(d)
    assert "Secret task" not in blob and "PIN hint" not in blob and "loan" not in blob
    names = [p["name"] for p in d["places"]]
    assert "HQ" in names and "HOME" not in names and "SMU" in names   # home is shown as "HQ", never by its name
    assert {"steps_week", "tasks_done_week", "memories"} <= set(d["stats"]) and d["team"]


def test_video_is_kept_and_sent(monkeypatch, tmp_path):
    from jarvis import telegram
    monkeypatch.setattr(trailer, "ROOT", tmp_path)
    monkeypatch.setattr(trailer, "_to_mp4", lambda src: None)
    sent = []
    monkeypatch.setattr(telegram, "enabled", lambda: True)
    monkeypatch.setattr(telegram, "chat_id", lambda: "1")
    monkeypatch.setattr(telegram, "api_file", lambda method, field, path, **k: sent.append((method, path)))
    out = trailer.save_video(b"\x1aE\xdf\xa3fake-webm", "webm")
    assert out["sent"] and sent[0][0] == "sendDocument" and out["path"].endswith(".webm")
    assert (tmp_path / "data" / "trailers").is_dir()


def test_phrases_open_the_trailer():
    from jarvis import server
    for p in ["show off mode", "play the trailer", "Jarvis, play my trailer", "show me the cinematics"]:
        assert server.CINEMA_RE.match(server.natural(p)), p
