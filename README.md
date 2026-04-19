# Funding Rate Monitor

A Python bot that monitors perpetual futures **funding rates** across multiple exchanges and sends **Telegram alerts** when rates exceed a configurable threshold.

---

## Features

- **Exchanges**: Binance, OKX, Hyperliquid, Lighter, Edgex
- **Universe**: Top-20 non-stablecoin crypto assets by CoinGecko market cap
- **Normalization**: All rates converted to **8-hour equivalent** before comparison
- **Alerts**: Telegram messages when `|funding_8h| > threshold` (default 0.01%)
- **De-duplication**: Per-exchange+symbol cooldown (default 60 min)
- **Scheduling**: GitHub Actions cron (every 15 min) + manual dispatch
- **Resilient**: Retries with exponential back-off via `tenacity`; partial results on failure

---

## Supported Exchanges

| Exchange | Endpoint type | Native interval | Notes |
|---|---|---|---|
| Binance | REST (USDT-M perps) | 8 h | `premiumIndex` bulk endpoint |
| OKX | REST (SWAP) | 8 h | Per-symbol `funding-rate` endpoint |
| Hyperliquid | REST | 1 h | Multiplied by 8 for normalization |
| Lighter | REST (public) | 8 h | Best-effort; skipped if API unreachable |
| Edgex | REST (public) | 8 h | Best-effort; skipped if API unreachable |

---

## Setup

### Prerequisites

- Python 3.10+
- A Telegram bot token and chat ID ([how to create a bot](https://core.telegram.org/bots#botfather))

### Install

```bash
pip install .
```

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Telegram bot token (from BotFather) |
| `TELEGRAM_CHAT_ID` | ✅ | — | Target chat/channel ID |
| `THRESHOLD_PCT` | ❌ | `0.01` | Alert threshold as `%` per 8h (e.g. `0.01` = 0.01%) |
| `TOP_N` | ❌ | `20` | Number of top market-cap symbols to monitor |
| `COOLDOWN_MINUTES` | ❌ | `60` | Minutes between repeated alerts for same exchange+symbol |
| `ENABLE_EXCHANGES` | ❌ | all | Comma-separated list of exchanges to enable (e.g. `binance,okx`) |
| `STATE_FILE` | ❌ | `cooldown_state.json` | Path to the cooldown state JSON file |

### Running locally

```bash
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"

python -m funding_rate_monitor
```

Or via the installed script:

```bash
funding-rate-monitor
```

---

## GitHub Actions Setup

1. **Fork / clone** this repository.
2. Add the following **secrets** in *Settings → Secrets and variables → Actions → Secrets*:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Optionally, add **variables** (not secrets) for non-sensitive config:
   - `THRESHOLD_PCT` (default `0.01`)
   - `TOP_N` (default `20`)
   - `COOLDOWN_MINUTES` (default `60`)
   - `ENABLE_EXCHANGES` (e.g. `binance,okx,hyperliquid`)
4. The workflow in `.github/workflows/funding_rate_monitor.yml` runs automatically every 15 minutes.  You can also trigger it manually via *Actions → Funding Rate Monitor → Run workflow*.

---

## Funding Rate Normalization

All rates are normalized to **8-hour equivalents** before being compared to the threshold.

```
rate_8h = native_rate × (8 / native_interval_hours)
```

| Exchange | Native interval | Factor |
|---|---|---|
| Binance | 8 h | ×1 |
| OKX | 8 h | ×1 |
| Hyperliquid | 1 h | ×8 |
| Lighter | 8 h | ×1 |
| Edgex | 8 h | ×1 |

---

## Telegram Alert Format

```
⚠️ Funding Rate Alert
Exchange: `binance`
Symbol: `BTCUSDT`
8h normalised: `0.0200%`
Native (8h): `0.0200%`
🟢 Long pays Short
Time: `2024-06-15 08:00:00 UTC`
```

---

## Development

### Install dev dependencies

```bash
pip install ".[dev]"
```

### Run tests

```bash
pytest -v
```

### Project structure

```
funding_rate_monitor/
├── __init__.py
├── __main__.py        # CLI entrypoint
├── config.py          # Env-var configuration
├── normalization.py   # 8h rate normalization
├── notifier.py        # Telegram notifier
├── runner.py          # Main orchestration loop
├── state.py           # Cooldown state (JSON file)
├── universe.py        # CoinGecko top-N market cap + symbol mapping
└── exchanges/
    ├── __init__.py    # FundingRateResult dataclass
    ├── binance.py
    ├── okx.py
    ├── hyperliquid.py
    ├── lighter.py
    └── edgex.py
tests/
├── test_normalization.py
├── test_notifier.py
└── test_universe.py
.github/
└── workflows/
    └── funding_rate_monitor.yml
```

---

## Limitations

- **Lighter** and **Edgex** have limited public API documentation.  Clients are best-effort and will skip gracefully if endpoints are unreachable.
- CoinGecko free-tier rate limits (30 req/min) are respected by fetching only once per run.
- The cooldown state file persists between runs via GitHub Actions cache.  On a fresh environment the cache may be empty, which means alerts could fire for all symbols on the first run.
