"""OKX perpetual swap funding rate client.

API reference:
  GET https://www.okx.com/api/v5/public/funding-rate?instId=<BTC-USDT-SWAP>

OKX publishes funding every **8 hours** (00:00, 08:00, 16:00 UTC).
The ``fundingRate`` field gives the *current* funding rate for the next
settlement.  We fetch each symbol individually (no public bulk endpoint
for funding rates).
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

_BASE_URL = "https://www.okx.com"
_INTERVAL_HOURS = 8.0


class OKXClient:
    """Fetch perpetual swap funding rates from OKX."""

    name = "okx"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_single(self, inst_id: str) -> Optional[dict]:
        """Fetch funding rate for one instrument."""
        url = f"{_BASE_URL}/api/v5/public/funding-rate"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, params={"instId": inst_id})
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data", [])
        return items[0] if items else None

    def fetch_funding_rates(
        self, symbol_map: dict[str, str]
    ) -> list[FundingRateResult]:
        """Fetch funding rates for the given symbols.

        Parameters
        ----------
        symbol_map:
            ``{coingecko_symbol: okx_inst_id}``

        Returns
        -------
        list[FundingRateResult]
        """
        results: list[FundingRateResult] = []
        for cg_sym, inst_id in symbol_map.items():
            try:
                item = self._fetch_single(inst_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("OKX: failed to fetch %s: %s", inst_id, exc)
                continue
            if item is None:
                logger.debug("OKX: no data for %s.", inst_id)
                continue

            try:
                native_rate = float(item["fundingRate"])
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("OKX: could not parse rate for %s: %s", inst_id, exc)
                continue

            funding_8h = normalize_to_8h(native_rate, self.name)
            ts_ms = item.get("fundingTime")
            timestamp: Optional[datetime] = None
            if ts_ms is not None:
                try:
                    timestamp = datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
                except (ValueError, OSError):
                    pass

            results.append(
                FundingRateResult(
                    exchange=self.name,
                    symbol=inst_id,
                    coingecko_symbol=cg_sym,
                    native_rate=native_rate,
                    native_interval_hours=_INTERVAL_HOURS,
                    funding_8h=funding_8h,
                    timestamp=timestamp,
                )
            )
        return results
