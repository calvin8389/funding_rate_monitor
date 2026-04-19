"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    # Threshold as a percentage (0.01 means 0.01 %).
    threshold_pct: float = field(
        default_factory=lambda: float(os.environ.get("THRESHOLD_PCT", "0.01"))
    )
    top_n: int = field(
        default_factory=lambda: int(os.environ.get("TOP_N", "20"))
    )
    # Minimum minutes between repeated alerts for the same exchange+symbol.
    cooldown_minutes: int = field(
        default_factory=lambda: int(os.environ.get("COOLDOWN_MINUTES", "60"))
    )
    # Optional comma-separated list of exchanges to enable (default: all).
    enable_exchanges: Optional[list[str]] = field(default=None)
    # Path to the cooldown state file.
    state_file: str = field(
        default_factory=lambda: os.environ.get("STATE_FILE", "cooldown_state.json")
    )

    def __post_init__(self) -> None:
        raw = os.environ.get("ENABLE_EXCHANGES", "")
        if raw:
            self.enable_exchanges = [e.strip().lower() for e in raw.split(",") if e.strip()]

    @property
    def threshold_fraction(self) -> float:
        """Return threshold as a fraction (e.g. 0.0001 for 0.01%)."""
        return self.threshold_pct / 100.0
