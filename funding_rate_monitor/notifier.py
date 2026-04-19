"""Telegram notifier.

Sends alerts when a funding rate exceeds the configured threshold.
Uses the Bot API ``sendMessage`` method with Markdown formatting.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"


def format_alert_message(
    exchange: str,
    symbol: str,
    funding_8h: float,
    native_rate: float,
    native_interval_hours: float,
    timestamp: Optional[datetime] = None,
) -> str:
    """Format a Telegram alert message.

    Parameters
    ----------
    exchange:
        Exchange name.
    symbol:
        Perpetual symbol (e.g. ``BTCUSDT``).
    funding_8h:
        8-hour normalised funding rate as a fraction.
    native_rate:
        Original (native-interval) funding rate as a fraction.
    native_interval_hours:
        Length of the native funding interval in hours.
    timestamp:
        Alert time (UTC); defaults to *now*.

    Returns
    -------
    str
        Markdown-formatted message ready to send to Telegram.
    """
    if timestamp is None:
        timestamp = datetime.now(tz=timezone.utc)

    direction = "🟢 Long pays Short" if funding_8h >= 0 else "🔴 Short pays Long"
    ts_str = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")

    return (
        f"⚠️ *Funding Rate Alert*\n"
        f"Exchange: `{exchange}`\n"
        f"Symbol: `{symbol}`\n"
        f"8h normalised: `{funding_8h * 100:.4f}%`\n"
        f"Native ({native_interval_hours:.0f}h): `{native_rate * 100:.4f}%`\n"
        f"{direction}\n"
        f"Time: `{ts_str}`"
    )


class TelegramNotifier:
    """Send Telegram messages via the Bot API."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._base_url = f"{_TELEGRAM_API_BASE}/bot{bot_token}"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def send_message(self, text: str) -> None:
        """Send a Markdown message to the configured chat.

        Raises
        ------
        httpx.HTTPError
            On network or API errors after all retries are exhausted.
        """
        url = f"{self._base_url}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json()
            if not result.get("ok"):
                raise httpx.HTTPStatusError(
                    f"Telegram API error: {result}",
                    request=resp.request,
                    response=resp,
                )
            logger.debug("Telegram message sent successfully.")

    def send_alert(
        self,
        exchange: str,
        symbol: str,
        funding_8h: float,
        native_rate: float,
        native_interval_hours: float,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Format and send a funding-rate alert."""
        text = format_alert_message(
            exchange=exchange,
            symbol=symbol,
            funding_8h=funding_8h,
            native_rate=native_rate,
            native_interval_hours=native_interval_hours,
            timestamp=timestamp,
        )
        try:
            self.send_message(text)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to send Telegram alert for %s %s: %s",
                exchange,
                symbol,
                exc,
            )
