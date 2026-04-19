"""Exchange client sub-package.

Each module exposes a ``FundingRateResult`` dataclass and a client class
with a ``fetch_funding_rates(symbols)`` method.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FundingRateResult:
    """Standardised funding-rate result from any exchange."""

    exchange: str
    symbol: str  # Exchange-native ticker
    coingecko_symbol: str  # Lower-case CoinGecko symbol
    native_rate: float  # As a fraction (e.g. 0.0001 = 0.01 %)
    native_interval_hours: float  # Hours of the native funding interval
    funding_8h: float  # 8h-normalised rate as a fraction
    timestamp: Optional[object] = None  # datetime, may be None
