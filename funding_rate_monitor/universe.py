"""Top-N market-cap universe using the CoinGecko public API.

Provides:
- A list of top-N symbols by market cap (stablecoins excluded).
- Per-exchange symbol mapping from a CoinGecko base symbol to the
  exchange's perpetual contract ticker.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# CoinGecko public endpoint (no API key required for moderate usage).
_COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Known stablecoins to exclude (case-insensitive symbol match).
STABLECOIN_SYMBOLS: frozenset[str] = frozenset(
    {
        "usdt", "usdc", "dai", "tusd", "fdusd", "usde", "usdd",
        "usdp", "gusd", "busd", "frax", "lusd", "susd", "eurc",
        "crvusd", "pyusd", "usdb", "ageur", "eur", "eurt",
    }
)

# Map from CoinGecko lowercase symbol → exchange perpetual ticker.
# For most exchanges the convention is <SYMBOL>USDT (upper-case).
# Override specific symbols per exchange where the ticker differs.
_BINANCE_OVERRIDES: dict[str, str] = {
    "shib": "1000SHIBUSDT",  # Binance quotes SHIB in 1000 lots
    "pepe": "1000PEPEUSDT",
    "bonk": "1000BONKUSDT",
    "floki": "1000FLOKIUSDT",
}

_OKX_OVERRIDES: dict[str, str] = {
    "shib": "SHIB-USDT-SWAP",
    "pepe": "PEPE-USDT-SWAP",
}

_HYPERLIQUID_OVERRIDES: dict[str, str] = {}

_LIGHTER_OVERRIDES: dict[str, str] = {}

_EDGEX_OVERRIDES: dict[str, str] = {}


def _default_binance(symbol: str) -> str:
    return _BINANCE_OVERRIDES.get(symbol.lower(), f"{symbol.upper()}USDT")


def _default_okx(symbol: str) -> str:
    return _OKX_OVERRIDES.get(symbol.lower(), f"{symbol.upper()}-USDT-SWAP")


def _default_hyperliquid(symbol: str) -> str:
    return _HYPERLIQUID_OVERRIDES.get(symbol.lower(), symbol.upper())


def _default_lighter(symbol: str) -> str:
    return _LIGHTER_OVERRIDES.get(symbol.lower(), f"{symbol.upper()}-USDC")


def _default_edgex(symbol: str) -> str:
    return _EDGEX_OVERRIDES.get(symbol.lower(), f"{symbol.upper()}-USDT")


SYMBOL_MAPPERS: dict[str, Callable[[str], str]] = {
    "binance": _default_binance,
    "okx": _default_okx,
    "hyperliquid": _default_hyperliquid,
    "lighter": _default_lighter,
    "edgex": _default_edgex,
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def fetch_top_n_symbols(top_n: int = 20) -> list[str]:
    """Fetch the top-N crypto symbols by market cap from CoinGecko.

    Stablecoins are excluded automatically.

    Parameters
    ----------
    top_n:
        Desired number of symbols.

    Returns
    -------
    list[str]
        Lower-case CoinGecko symbols in descending market-cap order.
    """
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": min(top_n * 3, 250),  # fetch extra to cover exclusions
        "page": 1,
        "sparkline": "false",
    }
    with httpx.Client(timeout=20) as client:
        resp = client.get(_COINGECKO_URL, params=params)
        resp.raise_for_status()
        coins = resp.json()

    result: list[str] = []
    for coin in coins:
        sym = coin.get("symbol", "").lower()
        if sym in STABLECOIN_SYMBOLS:
            logger.debug("Excluding stablecoin: %s", sym)
            continue
        result.append(sym)
        if len(result) >= top_n:
            break

    if len(result) < top_n:
        logger.warning(
            "Only found %d non-stablecoin symbols (requested %d).",
            len(result),
            top_n,
        )
    return result


def map_symbols_for_exchange(symbols: list[str], exchange: str) -> dict[str, str]:
    """Map CoinGecko symbols to exchange perpetual tickers.

    Parameters
    ----------
    symbols:
        Lower-case CoinGecko symbols.
    exchange:
        Exchange name (lower-case).

    Returns
    -------
    dict[str, str]
        Mapping ``{coingecko_symbol: exchange_ticker}``.
    """
    mapper = SYMBOL_MAPPERS.get(exchange.lower())
    if mapper is None:
        raise ValueError(f"Unknown exchange '{exchange}'.")
    return {sym: mapper(sym) for sym in symbols}
