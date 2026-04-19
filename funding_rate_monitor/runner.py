"""Main runner: orchestrates fetching, threshold checking, and alerting."""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from funding_rate_monitor.config import Config
from funding_rate_monitor.exchanges import FundingRateResult
from funding_rate_monitor.exchanges.binance import BinanceClient
from funding_rate_monitor.exchanges.edgex import EdgexClient
from funding_rate_monitor.exchanges.hyperliquid import HyperliquidClient
from funding_rate_monitor.exchanges.lighter import LighterClient
from funding_rate_monitor.exchanges.okx import OKXClient
from funding_rate_monitor.notifier import TelegramNotifier
from funding_rate_monitor.normalization import EXCHANGE_INTERVAL_HOURS
from funding_rate_monitor.state import CooldownState
from funding_rate_monitor.universe import fetch_top_n_symbols, map_symbols_for_exchange

logger = logging.getLogger(__name__)

_ALL_EXCHANGES = ["binance", "okx", "hyperliquid", "lighter", "edgex"]


@runtime_checkable
class ExchangeClient(Protocol):
    name: str

    def fetch_funding_rates(self, symbol_map: dict[str, str]) -> list[FundingRateResult]:
        ...


def _build_clients(enabled: Optional[list[str]]) -> dict[str, ExchangeClient]:
    clients: dict[str, object] = {
        "binance": BinanceClient(),
        "okx": OKXClient(),
        "hyperliquid": HyperliquidClient(),
        "lighter": LighterClient(),
        "edgex": EdgexClient(),
    }
    if enabled is not None:
        clients = {k: v for k, v in clients.items() if k in enabled}
    return clients


def run(cfg: Optional[Config] = None) -> list[FundingRateResult]:
    """Fetch funding rates, check thresholds, and send Telegram alerts.

    Parameters
    ----------
    cfg:
        Configuration; created from environment variables if not provided.

    Returns
    -------
    list[FundingRateResult]
        All results that exceeded the threshold (for testing/logging).
    """
    if cfg is None:
        cfg = Config()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # --- 1. Determine universe ---
    logger.info("Fetching top-%d symbols by market cap from CoinGecko…", cfg.top_n)
    try:
        symbols = fetch_top_n_symbols(top_n=cfg.top_n)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to fetch universe from CoinGecko: %s", exc)
        return []
    logger.info("Universe: %s", symbols)

    # --- 2. Build exchange clients ---
    clients = _build_clients(cfg.enable_exchanges)
    logger.info("Active exchanges: %s", list(clients))

    # --- 3. Fetch funding rates ---
    all_results: list[FundingRateResult] = []
    for exchange_name, client in clients.items():
        try:
            symbol_map = map_symbols_for_exchange(symbols, exchange_name)
        except ValueError as exc:
            logger.warning("Skipping exchange %s: %s", exchange_name, exc)
            continue
        logger.info("Fetching %s funding rates…", exchange_name)
        try:
            results = client.fetch_funding_rates(symbol_map)
        except Exception as exc:  # noqa: BLE001
            logger.error("Exchange %s failed: %s", exchange_name, exc)
            continue
        logger.info("%s: received %d results.", exchange_name, len(results))
        all_results.extend(results)

    # --- 4. Threshold check + alert ---
    if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
        logger.warning(
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set – alerts disabled."
        )
        notifier = None
    else:
        notifier = TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id)

    state = CooldownState(cfg.state_file)
    triggered: list[FundingRateResult] = []

    for result in all_results:
        if abs(result.funding_8h) <= cfg.threshold_fraction:
            continue
        if state.is_on_cooldown(result.exchange, result.symbol, cfg.cooldown_minutes):
            logger.info(
                "Cooldown active for %s %s – skipping alert.",
                result.exchange,
                result.symbol,
            )
            continue

        logger.info(
            "ALERT: %s %s funding_8h=%.4f%% (threshold=%.4f%%)",
            result.exchange,
            result.symbol,
            result.funding_8h * 100,
            cfg.threshold_pct,
        )
        triggered.append(result)
        state.record_alert(result.exchange, result.symbol)

        if notifier is not None:
            notifier.send_alert(
                exchange=result.exchange,
                symbol=result.symbol,
                funding_8h=result.funding_8h,
                native_rate=result.native_rate,
                native_interval_hours=result.native_interval_hours,
                timestamp=result.timestamp,  # type: ignore[arg-type]
            )

    logger.info(
        "Run complete. %d/%d results exceeded threshold.",
        len(triggered),
        len(all_results),
    )
    return triggered
