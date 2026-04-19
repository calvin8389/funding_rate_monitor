"""Tests for the universe module (symbol mapping and stablecoin exclusion)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from funding_rate_monitor.universe import (
    STABLECOIN_SYMBOLS,
    SYMBOL_MAPPERS,
    map_symbols_for_exchange,
)


class TestStablecoinExclusion:
    def test_common_stablecoins_in_exclusion_set(self) -> None:
        for coin in ["usdt", "usdc", "dai", "tusd", "fdusd", "usde"]:
            assert coin in STABLECOIN_SYMBOLS, f"{coin} should be excluded"

    def test_bitcoin_not_excluded(self) -> None:
        assert "btc" not in STABLECOIN_SYMBOLS

    def test_ethereum_not_excluded(self) -> None:
        assert "eth" not in STABLECOIN_SYMBOLS


class TestSymbolMapping:
    def test_binance_default_mapping(self) -> None:
        result = map_symbols_for_exchange(["btc", "eth", "sol"], "binance")
        assert result["btc"] == "BTCUSDT"
        assert result["eth"] == "ETHUSDT"
        assert result["sol"] == "SOLUSDT"

    def test_binance_shib_override(self) -> None:
        result = map_symbols_for_exchange(["shib"], "binance")
        assert result["shib"] == "1000SHIBUSDT"

    def test_binance_pepe_override(self) -> None:
        result = map_symbols_for_exchange(["pepe"], "binance")
        assert result["pepe"] == "1000PEPEUSDT"

    def test_okx_default_mapping(self) -> None:
        result = map_symbols_for_exchange(["btc", "eth"], "okx")
        assert result["btc"] == "BTC-USDT-SWAP"
        assert result["eth"] == "ETH-USDT-SWAP"

    def test_hyperliquid_default_mapping(self) -> None:
        result = map_symbols_for_exchange(["btc", "eth"], "hyperliquid")
        assert result["btc"] == "BTC"
        assert result["eth"] == "ETH"

    def test_lighter_default_mapping(self) -> None:
        result = map_symbols_for_exchange(["btc"], "lighter")
        assert result["btc"] == "BTC-USDC"

    def test_edgex_default_mapping(self) -> None:
        result = map_symbols_for_exchange(["btc"], "edgex")
        assert result["btc"] == "BTC-USDT"

    def test_unknown_exchange_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown exchange"):
            map_symbols_for_exchange(["btc"], "bybit")

    def test_all_configured_exchanges_work(self) -> None:
        symbols = ["btc", "eth", "sol"]
        for exchange in SYMBOL_MAPPERS:
            result = map_symbols_for_exchange(symbols, exchange)
            assert len(result) == 3
            for sym in symbols:
                assert sym in result
                assert isinstance(result[sym], str)
                assert len(result[sym]) > 0

    def test_empty_symbol_list(self) -> None:
        result = map_symbols_for_exchange([], "binance")
        assert result == {}


class TestFetchTopNSymbols:
    """Integration-style tests using a mocked HTTP response."""

    def _mock_coingecko_response(self, symbols: list[str]) -> list[dict]:
        return [
            {"id": s, "symbol": s, "name": s.upper(), "market_cap": 1000 - i}
            for i, s in enumerate(symbols)
        ]

    def test_stablecoins_filtered_out(self) -> None:
        from funding_rate_monitor.universe import fetch_top_n_symbols

        mock_data = self._mock_coingecko_response(
            ["btc", "usdt", "eth", "usdc", "bnb", "sol"]
        )

        with patch("funding_rate_monitor.universe.httpx.Client") as mock_cls:
            mock_resp = mock_cls.return_value.__enter__.return_value.get.return_value
            mock_resp.raise_for_status = lambda: None
            mock_resp.json.return_value = mock_data

            result = fetch_top_n_symbols(top_n=4)

        assert "usdt" not in result
        assert "usdc" not in result
        assert "btc" in result
        assert "eth" in result

    def test_returns_correct_count(self) -> None:
        from funding_rate_monitor.universe import fetch_top_n_symbols

        mock_data = self._mock_coingecko_response(
            ["btc", "eth", "bnb", "sol", "xrp", "ada"]
        )

        with patch("funding_rate_monitor.universe.httpx.Client") as mock_cls:
            mock_resp = mock_cls.return_value.__enter__.return_value.get.return_value
            mock_resp.raise_for_status = lambda: None
            mock_resp.json.return_value = mock_data

            result = fetch_top_n_symbols(top_n=4)

        assert len(result) == 4

    def test_order_preserved(self) -> None:
        from funding_rate_monitor.universe import fetch_top_n_symbols

        mock_data = self._mock_coingecko_response(["btc", "eth", "bnb", "sol"])

        with patch("funding_rate_monitor.universe.httpx.Client") as mock_cls:
            mock_resp = mock_cls.return_value.__enter__.return_value.get.return_value
            mock_resp.raise_for_status = lambda: None
            mock_resp.json.return_value = mock_data

            result = fetch_top_n_symbols(top_n=4)

        assert result == ["btc", "eth", "bnb", "sol"]
