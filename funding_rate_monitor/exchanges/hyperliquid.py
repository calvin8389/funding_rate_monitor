"""Hyperliquid perpetual funding rate client.

API reference (public, no auth required):
  POST https://api.hyperliquid.xyz/info
  Body: {"type": "metaAndAssetCtxs"}

Hyperliquid publishes funding on a **1-hour** interval.
The ``funding`` field in the asset context is the *current hourly* rate.
We normalise to 8h by multiplying by 8.
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

_BASE_URL = "https://api.hyperliquid.xyz"
_INTERVAL_HOURS = 1.0


class HyperliquidClient:
    """Fetch perpetual funding rates from Hyperliquid."""

    name = "hyperliquid"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_meta_and_ctxs(self) -> tuple[list[dict], list[dict]]:
        """Fetch metadata and asset contexts (bulk endpoint)."""
        url = f"{_BASE_URL}/info"
        payload = {"type": "metaAndAssetCtxs"}
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        # Response is [universe_meta, asset_ctxs]
        meta = data[0].get("universe", [])
        ctxs = data[1] if len(data) > 1 else []
        return meta, ctxs

    def fetch_funding_rates(
        self, symbol_map: dict[str, str]
    ) -> list[FundingRateResult]:
        """Fetch funding rates for the given symbols.

        Parameters
        ----------
        symbol_map:
            ``{coingecko_symbol: hyperliquid_coin_name}``
            Hyperliquid uses short coin names (e.g. ``BTC``, ``ETH``).

        Returns
        -------
        list[FundingRateResult]
        """
        try:
            meta, ctxs = self._fetch_meta_and_ctxs()
        except Exception as exc:  # noqa: BLE001
            logger.error("Hyperliquid: failed to fetch data: %s", exc)
            return []

        # Build lookup: coin_name → funding_rate
        coin_funding: dict[str, float] = {}
        for asset_meta, ctx in zip(meta, ctxs):
            coin = asset_meta.get("name", "")
            try:
                rate = float(ctx.get("funding", 0))
            except (ValueError, TypeError):
                continue
            coin_funding[coin.upper()] = rate

        results: list[FundingRateResult] = []
        for cg_sym, coin_name in symbol_map.items():
            rate = coin_funding.get(coin_name.upper())
            if rate is None:
                logger.debug("Hyperliquid: symbol %s not found.", coin_name)
                continue

            funding_8h = normalize_to_8h(rate, self.name)
            results.append(
                FundingRateResult(
                    exchange=self.name,
                    symbol=coin_name.upper(),
                    coingecko_symbol=cg_sym,
                    native_rate=rate,
                    native_interval_hours=_INTERVAL_HOURS,
                    funding_8h=funding_8h,
                    timestamp=datetime.now(tz=timezone.utc),
                )
            )
        return results
