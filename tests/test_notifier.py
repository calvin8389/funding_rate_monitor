"""Tests for Telegram notifier formatting and sending."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from funding_rate_monitor.notifier import TelegramNotifier, format_alert_message


class TestFormatAlertMessage:
    """Unit tests for format_alert_message helper."""

    def _fixed_ts(self) -> datetime:
        return datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_contains_exchange(self) -> None:
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0, self._fixed_ts())
        assert "binance" in msg

    def test_contains_symbol(self) -> None:
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0, self._fixed_ts())
        assert "BTCUSDT" in msg

    def test_contains_8h_rate(self) -> None:
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0, self._fixed_ts())
        # 0.0002 as percentage is 0.0200%
        assert "0.0200" in msg

    def test_contains_native_rate(self) -> None:
        msg = format_alert_message("hyperliquid", "BTC", 0.0008, 0.0001, 1.0, self._fixed_ts())
        # native 0.0001 → 0.0100%
        assert "0.0100" in msg

    def test_contains_timestamp(self) -> None:
        ts = self._fixed_ts()
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0, ts)
        assert "2024-06-15" in msg
        assert "12:00:00" in msg

    def test_positive_rate_direction_label(self) -> None:
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0, self._fixed_ts())
        assert "Long pays Short" in msg

    def test_negative_rate_direction_label(self) -> None:
        msg = format_alert_message("binance", "BTCUSDT", -0.0002, -0.0002, 8.0, self._fixed_ts())
        assert "Short pays Long" in msg

    def test_default_timestamp_is_utc(self) -> None:
        """When no timestamp is given, the message should still include 'UTC'."""
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0)
        assert "UTC" in msg

    def test_native_interval_shown(self) -> None:
        msg = format_alert_message("hyperliquid", "ETH", 0.0008, 0.0001, 1.0, self._fixed_ts())
        assert "1h" in msg

    def test_markdown_backticks(self) -> None:
        """Key fields should be wrapped in backticks for Markdown formatting."""
        msg = format_alert_message("binance", "BTCUSDT", 0.0002, 0.0002, 8.0, self._fixed_ts())
        assert "`binance`" in msg
        assert "`BTCUSDT`" in msg


class TestTelegramNotifier:
    """Tests for TelegramNotifier.send_message (mocked HTTP)."""

    def _make_notifier(self) -> TelegramNotifier:
        return TelegramNotifier(bot_token="test-token", chat_id="12345")

    def test_send_message_calls_correct_url(self) -> None:
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {}}

        with patch("funding_rate_monitor.notifier.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response

            notifier.send_message("Hello, world!")

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert "test-token" in call_args[0][0]
            assert call_args[1]["json"]["chat_id"] == "12345"
            assert call_args[1]["json"]["text"] == "Hello, world!"
            assert call_args[1]["json"]["parse_mode"] == "Markdown"

    def test_send_message_raises_on_api_error(self) -> None:
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"ok": False, "description": "Unauthorized"}

        with patch("funding_rate_monitor.notifier.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response

            with pytest.raises(Exception):
                notifier.send_message("test")

    def test_send_alert_does_not_raise_on_http_error(self) -> None:
        """send_alert should catch exceptions and log them, not propagate."""
        notifier = self._make_notifier()

        with patch.object(notifier, "send_message", side_effect=Exception("network error")):
            # Should not raise
            notifier.send_alert(
                exchange="binance",
                symbol="BTCUSDT",
                funding_8h=0.0005,
                native_rate=0.0005,
                native_interval_hours=8.0,
            )
