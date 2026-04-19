"""Funding rate normalization utilities.

Each exchange publishes funding rates on different intervals:

| Exchange     | Native interval | Normalization factor |
|--------------|-----------------|----------------------|
| Binance      | 8 hours         | 1×  (already 8h)     |
| OKX          | 8 hours         | 1×  (already 8h)     |
| Hyperliquid  | 1 hour          | 8×  (multiply by 8)  |
| Lighter      | 8 hours         | 1×  (already 8h)     |
| Edgex        | 8 hours         | 1×  (already 8h)     |

All rates are expressed as fractions (0.0001 = 0.01%).
After normalisation the returned value is the "per-8h equivalent".
"""

from __future__ import annotations

# Hours in each exchange's native funding interval.
EXCHANGE_INTERVAL_HOURS: dict[str, float] = {
    "binance": 8.0,
    "okx": 8.0,
    "hyperliquid": 1.0,
    "lighter": 8.0,
    "edgex": 8.0,
}

_TARGET_HOURS = 8.0


def normalize_to_8h(rate: float, exchange: str) -> float:
    """Convert a native funding rate to its 8-hour equivalent.

    Parameters
    ----------
    rate:
        Native funding rate as a fraction (e.g. 0.0001 for 0.01 %).
    exchange:
        Exchange name (lower-case).  Must be a key in
        :data:`EXCHANGE_INTERVAL_HOURS`.

    Returns
    -------
    float
        8-hour equivalent funding rate as a fraction.

    Raises
    ------
    ValueError
        If ``exchange`` is not recognised.
    """
    interval = EXCHANGE_INTERVAL_HOURS.get(exchange.lower())
    if interval is None:
        raise ValueError(
            f"Unknown exchange '{exchange}'. "
            f"Known exchanges: {list(EXCHANGE_INTERVAL_HOURS)}"
        )
    factor = _TARGET_HOURS / interval
    return rate * factor
