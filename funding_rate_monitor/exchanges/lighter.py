"""Lighter perpetual funding rate client.

Lighter (lighter.xyz) is an on-chain perpetuals DEX on ZKsync Era.

Public API:
  GET https://mainnet.zklighter.elliot.ai/api/v1/orderbook/list

The public REST endpoint returns market information including the
current ``funding_rate`` for each market.  The funding interval on
Lighter is **8 hours**.

If the endpoint is unreachable or returns unexpected data this client
logs a warning and returns an empty result set (best-effort).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from funding_rate_monitor.exchanges import FundingRateResult
from funding_rate_monitor.normalization import normalize_to_8h

logger = logging.getLogger(__name__)

_BASE_URL = "https://mainnet.zklighter.elliot.ai"
_INTERVAL_HOURS = 8.0


class LighterClient:
    """Fetch perpetual funding rates from Lighter (best-effort)."""

    name = "lighter"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_markets(self) -> list[dict]:
        """Fetch all markets from the Lighter public API."""
        url = f"{_BASE_URL}/api/v1/orderbook/list"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        # The API returns {"orderbooks": [...]} or just a list.
        if isinstance(data, dict):
            return data.get("orderbooks", [])
        return data  # type: ignore[return-value]

    def fetch_funding_rates(
        self, symbol_map: dict[str, str]
    ) -> list[FundingRateResult]:
        """Fetch funding rates for the given symbols.

        Parameters
        ----------
        symbol_map:
            ``{coingecko_symbol: lighter_market_symbol}``
            e.g. ``{"btc": "BTC-USDC"}``

        Returns
        -------
        list[FundingRateResult]
            Empty list if the API is unavailable.
        """
        try:
            markets = self._fetch_markets()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Lighter: API unavailable (%s) – skipping exchange.", exc
            )
            return []

        # Build lookup by market symbol (case-insensitive).
        market_lookup: dict[str, dict] = {
            m.get("symbol", "").upper(): m for m in markets
        }

        results: list[FundingRateResult] = []
        for cg_sym, mkt_sym in symbol_map.items():
            item = market_lookup.get(mkt_sym.upper())
            if item is None:
                logger.debug("Lighter: market %s not found.", mkt_sym)
                continue
            try:
                native_rate = float(item["funding_rate"])
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug(
                    "Lighter: could not parse funding_rate for %s: %s", mkt_sym, exc
                )
                continue

            funding_8h = normalize_to_8h(native_rate, self.name)
            results.append(
                FundingRateResult(
                    exchange=self.name,
                    symbol=mkt_sym.upper(),
                    coingecko_symbol=cg_sym,
                    native_rate=native_rate,
                    native_interval_hours=_INTERVAL_HOURS,
                    funding_8h=funding_8h,
                    timestamp=datetime.now(tz=timezone.utc),
                )
            )
        return results
