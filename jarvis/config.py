"""Configuration: read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so we don't need python-dotenv."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if value[:1] in ('"', "'") and value[1:].find(value[0]) != -1:
            value = value[1:1 + value[1:].find(value[0])]       # quoted: take what's inside the quotes
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()  # drop a trailing "   # note"
        os.environ.setdefault(key, value)


_load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    owner_name: str = field(default_factory=lambda: _env("JARVIS_OWNER_NAME", "Sir"))
    timezone: str = field(default_factory=lambda: _env("JARVIS_TIMEZONE", "UTC"))
    model: str = field(default_factory=lambda: _env("JARVIS_MODEL", "claude-opus-5-5"))
    host: str = field(default_factory=lambda: _env("JARVIS_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("JARVIS_PORT", "7334")))
    db_path: Path = field(default_factory=lambda: Path(_env("JARVIS_DB", str(ROOT / "data" / "jarvis.db"))))
    profile_path: Path = field(default_factory=lambda: ROOT / "profile.md")
    schedule_enabled: bool = field(default_factory=lambda: _env("JARVIS_SCHEDULER", "on").lower() != "off")

    # Daily schedule (24h HH:MM, local timezone)
    morning_brief_at: str = field(default_factory=lambda: _env("JARVIS_MORNING_AT", "07:00"))
    evening_report_at: str = field(default_factory=lambda: _env("JARVIS_EVENING_AT", "21:00"))
    night_shift_at: str = field(default_factory=lambda: _env("JARVIS_NIGHT_SHIFT_AT", "02:00"))
    money_weekly_at: str = field(default_factory=lambda: _env("JARVIS_MONEY_WEEKLY_AT", "19:00"))  # Sundays
    weekly_review_at: str = field(default_factory=lambda: _env("JARVIS_WEEKLY_AT", "18:00"))  # Sundays
    watch_every_hours: int = field(default_factory=lambda: int(_env("JARVIS_WATCH_EVERY_HOURS", "3")))

    # Optional notification channels
    smtp_host: str = field(default_factory=lambda: _env("JARVIS_SMTP_HOST"))
    smtp_port: int = field(default_factory=lambda: int(_env("JARVIS_SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: _env("JARVIS_SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("JARVIS_SMTP_PASSWORD"))
    report_email_to: str = field(default_factory=lambda: _env("JARVIS_REPORT_EMAIL_TO"))
    telegram_token: str = field(default_factory=lambda: _env("JARVIS_TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("JARVIS_TELEGRAM_CHAT_ID"))

    # How much agents may do on their own when messaging OTHER people:
    #   approve - every message to someone else waits for your OK (default, safest)
    #   trusted - messages to contacts marked trusted go out automatically, the rest wait
    #   full    - everything goes out automatically
    autonomy: str = field(default_factory=lambda: _env("JARVIS_AUTONOMY", "approve").lower())

    # E-mail account the agents read and send from (Gmail: use an App Password)
    imap_host: str = field(default_factory=lambda: _env("JARVIS_IMAP_HOST"))
    email_signature: str = field(default_factory=lambda: _env("JARVIS_EMAIL_SIGNATURE"))

    # WhatsApp (personal number, via the bridge in bridge/)
    whatsapp_enabled: bool = field(default_factory=lambda: _env("JARVIS_WHATSAPP", "off").lower() == "on")
    whatsapp_bridge_url: str = field(default_factory=lambda: _env("JARVIS_WHATSAPP_BRIDGE", "http://127.0.0.1:7335"))
    # Secret that protects JARVIS's local endpoints (WhatsApp bridge, Claude Code tools). Random if not set.
    bridge_token: str = field(default_factory=lambda: _env("JARVIS_BRIDGE_TOKEN") or secrets.token_hex(16))
    owner_whatsapp: str = field(default_factory=lambda: _env("JARVIS_OWNER_WHATSAPP"))  # your own number

    # Brain: pro (your Claude plan via Claude Code) | api (Anthropic API key) | gemini (free) | auto
    brain: str = field(default_factory=lambda: _env("JARVIS_BRAIN", "auto").lower())
    # Brain for scheduled jobs (briefs, sweeps, night shift). auto = Gemini if set up, to save your Claude plan
    automation_brain: str = field(default_factory=lambda: _env("JARVIS_AUTOMATION_BRAIN", "auto").lower())
    # Claude model when thinking through your plan: sonnet (balanced) | haiku (fastest, lightest on limits) | opus
    pro_model: str = field(default_factory=lambda: _env("JARVIS_PRO_MODEL", "sonnet"))
    # Google Gemini (free tier) - key from https://aistudio.google.com/apikey
    gemini_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("JARVIS_GEMINI_MODEL", "gemini-flash-latest"))

    # Fast mode: Claude Opus 5.5 writes ~2.5x faster at double the price (on/off)
    fast_mode: bool = field(default_factory=lambda: _env("JARVIS_FAST_MODE", "off").lower() == "on")
    # Hands-free wake words (comma separated). Any agent name also works ("Friday, ...").
    wake_words: str = field(default_factory=lambda: _env("JARVIS_WAKE_WORDS", "jarvis,hey jarvis,ok jarvis"))
    # Speech-to-text for Telegram voice notes (runs on your laptop, free): tiny | base | small | medium
    whisper_model: str = field(default_factory=lambda: _env("JARVIS_WHISPER_MODEL", "base"))

    # Premium voices (ElevenLabs). Without a key the dashboard uses your computer's built-in voices.
    elevenlabs_key: str = field(default_factory=lambda: _env("ELEVENLABS_API_KEY"))
    elevenlabs_model: str = field(default_factory=lambda: _env("JARVIS_ELEVENLABS_MODEL", "eleven_flash_v2_5"))

    # How often the inbox sweep runs (minutes); 0 = off
    inbox_sweep_minutes: int = field(default_factory=lambda: int(_env("JARVIS_INBOX_SWEEP_MINUTES", "60")))

    @property
    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("UTC")

    @property
    def has_llm(self) -> bool:
        """True if any brain (Claude plan, Claude API or Gemini) is set up."""
        from . import brain
        return any(brain.ready(b) for b in ("pro", "api", "gemini"))

    def profile(self) -> str:
        if self.profile_path.exists():
            return self.profile_path.read_text(encoding="utf-8").strip()
        return ""


settings = Settings()
