"""Cloud JARVIS + laptop satellite: laptop jobs go to the laptop when it's on, and a clear answer when it's off."""
import threading
import time

from jarvis import satellite
from jarvis.tools import ToolContext, execute


def _ctx(server):
    return ToolContext(server.store, server.bus, server.settings, server.engine, "JARVIS", 0, False)


def test_laptop_tools_wait_for_the_satellite(monkeypatch):
    from jarvis import server
    monkeypatch.setenv("JARVIS_ROLE", "cloud")
    server.store.set("sat:last_seen", "")
    out, err = execute("laptop_status", _ctx(server), {})
    assert err and "laptop is off" in out

    def laptop():   # the satellite: checks in, does the job, answers
        for _ in range(40):
            for j in satellite.checkin(server.store):
                satellite.done(server.store, j["id"], '{"output": "{\\"battery_pct\\": 77}", "error": false}', True)
                return
            time.sleep(.1)
    satellite.checkin(server.store)   # the laptop is online
    threading.Thread(target=laptop, daemon=True).start()
    out, err = execute("laptop_status", _ctx(server), {})
    assert not err and "77" in out


def test_other_tools_and_laptop_role_unchanged(monkeypatch):
    from jarvis import server
    monkeypatch.setenv("JARVIS_ROLE", "laptop")
    out, err = execute("get_datetime", _ctx(server), {})
    assert not err
    assert satellite.role() == "laptop"
    monkeypatch.setenv("JARVIS_ROLE", "nonsense")
    assert satellite.role() == "laptop"


def test_endpoints_need_the_token(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from jarvis import server
    monkeypatch.setenv("JARVIS_SATELLITE_TOKEN", "s3cret-token")
    with pytest.raises(HTTPException):
        server.satellite_poll({}, x_jarvis_satellite="wrong")
    assert "jobs" in server.satellite_poll({}, x_jarvis_satellite="s3cret-token")
