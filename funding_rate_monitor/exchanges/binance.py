"""Binance USDT-M perpetual futures funding rate client.

API reference:
  GET https://fapi.binance.com/fapi/v1/fundingRate
  GET https://fapi.binance.com/fapi/v1/premiumIndex  (next predicted rate)

Binance publishes funding every **8 hours** (00:00, 08:00, 16:00 UTC).
The ``fundingRate`` field in the ``premiumIndex`` endpoint gives the
*next* predicted rate; the historical endpoint gives settled rates.
We use the ``premiumIndex`` endpoint to get the current/predicted rate
for each symbol in a single bulk call.
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

_BASE_URL = "https://fapi.binance.com"
_INTERVAL_HOURS = 8.0


class BinanceClient:
    """Fetch perpetual funding rates from Binance USDT-M futures."""

    name = "binance"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_premium_index(self) -> list[dict]:
        """Fetch the premium index for ALL symbols (bulk endpoint)."""
        url = f"{_BASE_URL}/fapi/v1/premiumIndex"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()

    def fetch_funding_rates(
        self, symbol_map: dict[str, str]
    ) -> list[FundingRateResult]:
        """Fetch funding rates for the given symbols.

        Parameters
        ----------
        symbol_map:
            ``{coingecko_symbol: binance_ticker}``

        Returns
        -------
        list[FundingRateResult]
            One entry per symbol that was found on Binance.
        """
        try:
            raw = self._fetch_premium_index()
        except Exception as exc:  # noqa: BLE001
            logger.error("Binance: failed to fetch premium index: %s", exc)
            return []

        # Build a lookup by Binance symbol.
        by_ticker: dict[str, dict] = {item["symbol"]: item for item in raw}
        results: list[FundingRateResult] = []

        for cg_sym, ticker in symbol_map.items():
            item = by_ticker.get(ticker)
            if item is None:
                logger.debug("Binance: symbol %s not found.", ticker)
                continue
            try:
                native_rate = float(item["lastFundingRate"])
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Binance: could not parse rate for %s: %s", ticker, exc)
                continue

            funding_8h = normalize_to_8h(native_rate, self.name)
            ts_ms = item.get("time")
            timestamp: Optional[datetime] = None
            if ts_ms is not None:
                timestamp = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)

            results.append(
                FundingRateResult(
                    exchange=self.name,
                    symbol=ticker,
                    coingecko_symbol=cg_sym,
                    native_rate=native_rate,
                    native_interval_hours=_INTERVAL_HOURS,
                    funding_8h=funding_8h,
                    timestamp=timestamp,
                )
            )

        return results
