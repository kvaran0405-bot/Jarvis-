"""Configuration: read from environment variables (and an optional .env file)."""
from __future__ import annotations

import os
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
        key, value = key.strip(), value.strip().strip('"').strip("'")
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

    @property
    def tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except Exception:
            return ZoneInfo("UTC")

    @property
    def has_llm(self) -> bool:
        return bool(_env("ANTHROPIC_API_KEY") or _env("ANTHROPIC_AUTH_TOKEN") or _env("ANTHROPIC_PROFILE")
                    or (Path.home() / ".config" / "anthropic").exists())

    def profile(self) -> str:
        if self.profile_path.exists():
            return self.profile_path.read_text(encoding="utf-8").strip()
        return ""


settings = Settings()
