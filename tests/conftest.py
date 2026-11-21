import pytest


@pytest.fixture(autouse=True)
def no_real_brains(monkeypatch):
    """Tests must never call a real AI (Claude Code, API or Gemini)."""
    from jarvis import brain
    monkeypatch.setattr(brain, "claude_cli", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    from jarvis.config import settings
    monkeypatch.setattr(settings, "gemini_key", "")
