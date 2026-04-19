"""Edgex perpetual funding rate client.

Edgex (edgex.exchange) is a decentralised perpetuals exchange.

Public API:
  GET https://pro.edgex.exchange/api/v1/public/market/funding-rate-history
  Params: contractId=<id>, pageSize=1, pageIndex=0

A secondary endpoint lists all contracts:
  GET https://pro.edgex.exchange/api/v1/public/market/contract-info

The funding interval on Edgex is **8 hours**.

If the API is unreachable this client logs a warning and returns an
empty result set (best-effort).
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

_BASE_URL = "https://pro.edgex.exchange"
_INTERVAL_HOURS = 8.0


class EdgexClient:
    """Fetch perpetual funding rates from Edgex (best-effort)."""

    name = "edgex"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout
        self._contract_map: dict[str, str] = {}  # symbol → contractId

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_contract_info(self) -> list[dict]:
        url = f"{_BASE_URL}/api/v1/public/market/contract-info"
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        return data.get("data", {}).get("contractList", [])

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_funding_rate(self, contract_id: str) -> Optional[float]:
        url = f"{_BASE_URL}/api/v1/public/market/funding-rate-history"
        params = {"contractId": contract_id, "pageSize": 1, "pageIndex": 0}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        items = data.get("data", {}).get("fundingRateList", [])
        if not items:
            return None
        return float(items[0].get("fundingRate", 0))

    def _ensure_contract_map(self) -> None:
        """Lazily populate the symbol→contractId map."""
        if self._contract_map:
            return
        try:
            contracts = self._fetch_contract_info()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Edgex: could not fetch contract info: %s", exc)
            return
        for c in contracts:
            sym = c.get("contractName", "").upper()
            cid = str(c.get("contractId", ""))
            if sym and cid:
                self._contract_map[sym] = cid

    def fetch_funding_rates(
        self, symbol_map: dict[str, str]
    ) -> list[FundingRateResult]:
        """Fetch funding rates for the given symbols.

        Parameters
        ----------
        symbol_map:
            ``{coingecko_symbol: edgex_ticker}``
            e.g. ``{"btc": "BTC-USDT"}``

        Returns
        -------
        list[FundingRateResult]
            Empty list if the API is unavailable.
        """
        self._ensure_contract_map()
        if not self._contract_map:
            logger.warning("Edgex: no contract info available – skipping.")
            return []

        results: list[FundingRateResult] = []
        for cg_sym, ticker in symbol_map.items():
            contract_id = self._contract_map.get(ticker.upper())
            if contract_id is None:
                logger.debug("Edgex: ticker %s not found in contract map.", ticker)
                continue
            try:
                native_rate = self._fetch_funding_rate(contract_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("Edgex: failed to fetch rate for %s: %s", ticker, exc)
                continue
            if native_rate is None:
                continue

            funding_8h = normalize_to_8h(native_rate, self.name)
            results.append(
                FundingRateResult(
                    exchange=self.name,
                    symbol=ticker.upper(),
                    coingecko_symbol=cg_sym,
                    native_rate=native_rate,
                    native_interval_hours=_INTERVAL_HOURS,
                    funding_8h=funding_8h,
                    timestamp=datetime.now(tz=timezone.utc),
                )
            )
        return results
