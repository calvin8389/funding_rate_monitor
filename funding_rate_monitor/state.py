"""Cooldown / de-dup state storage backed by a local JSON file.

State schema (JSON)::

    {
        "<exchange>:<symbol>": "<ISO-8601 last-alert-timestamp>"
    }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CooldownState:
    """Persist last-alert timestamps to avoid duplicate Telegram messages."""

    def __init__(self, state_file: str = "cooldown_state.json") -> None:
        self._path = Path(state_file)
        self._data: dict[str, str] = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_on_cooldown(self, exchange: str, symbol: str, cooldown_minutes: int) -> bool:
        """Return True if an alert was sent recently and is still on cooldown."""
        key = self._key(exchange, symbol)
        last_str = self._data.get(key)
        if last_str is None:
            return False
        try:
            last = datetime.fromisoformat(last_str)
        except ValueError:
            return False
        now = datetime.now(tz=timezone.utc)
        elapsed_minutes = (now - last).total_seconds() / 60.0
        return elapsed_minutes < cooldown_minutes

    def record_alert(self, exchange: str, symbol: str) -> None:
        """Record that an alert was just sent for exchange+symbol."""
        key = self._key(exchange, symbol)
        self._data[key] = datetime.now(tz=timezone.utc).isoformat()
        self._save()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _key(exchange: str, symbol: str) -> str:
        return f"{exchange.lower()}:{symbol.upper()}"

    def _load(self) -> dict[str, str]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open() as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load state file %s: %s", self._path, exc)
            return {}

    def _save(self) -> None:
        try:
            with self._path.open("w") as fh:
                json.dump(self._data, fh, indent=2)
        except OSError as exc:
            logger.warning("Could not save state file %s: %s", self._path, exc)
