"""Tests for funding rate normalization."""

from __future__ import annotations

import pytest

from funding_rate_monitor.normalization import (
    EXCHANGE_INTERVAL_HOURS,
    normalize_to_8h,
)


class TestNormalizeTo8h:
    def test_binance_passthrough(self) -> None:
        """Binance rates are already 8h – should be unchanged."""
        rate = 0.0001
        assert normalize_to_8h(rate, "binance") == pytest.approx(0.0001)

    def test_okx_passthrough(self) -> None:
        """OKX rates are 8h – should be unchanged."""
        rate = 0.0002
        assert normalize_to_8h(rate, "okx") == pytest.approx(0.0002)

    def test_hyperliquid_multiplied_by_8(self) -> None:
        """Hyperliquid is 1h interval – multiply by 8."""
        rate = 0.00005  # per hour
        expected = 0.00005 * 8
        assert normalize_to_8h(rate, "hyperliquid") == pytest.approx(expected)

    def test_lighter_passthrough(self) -> None:
        rate = 0.0003
        assert normalize_to_8h(rate, "lighter") == pytest.approx(0.0003)

    def test_edgex_passthrough(self) -> None:
        rate = -0.0001
        assert normalize_to_8h(rate, "edgex") == pytest.approx(-0.0001)

    def test_negative_rate_preserved(self) -> None:
        """Negative rates (longs paid) should remain negative after norm."""
        rate = -0.00005
        result = normalize_to_8h(rate, "hyperliquid")
        assert result < 0
        assert result == pytest.approx(-0.0004)

    def test_zero_rate(self) -> None:
        for exchange in EXCHANGE_INTERVAL_HOURS:
            assert normalize_to_8h(0.0, exchange) == pytest.approx(0.0)

    def test_unknown_exchange_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown exchange"):
            normalize_to_8h(0.0001, "bybit")

    def test_case_insensitive(self) -> None:
        """Exchange names should be matched case-insensitively."""
        assert normalize_to_8h(0.0001, "BINANCE") == pytest.approx(0.0001)
        assert normalize_to_8h(0.0001, "Hyperliquid") == pytest.approx(0.0008)

    @pytest.mark.parametrize("exchange,interval", list(EXCHANGE_INTERVAL_HOURS.items()))
    def test_all_known_exchanges_defined(self, exchange: str, interval: float) -> None:
        """All exchanges in EXCHANGE_INTERVAL_HOURS should normalise without error."""
        result = normalize_to_8h(0.0001, exchange)
        expected = 0.0001 * (8.0 / interval)
        assert result == pytest.approx(expected)
