# Binance Spot Trading Bot

A modular, testnet-first automated trading bot for Binance Spot, built with clean
architecture and SOLID principles.

> ⚠️ **Risk & disclaimer.** This is educational software provided **as-is, with no
> warranty**. Automated trading of cryptocurrency carries a substantial risk of
> financial loss, including the total loss of funds. Nothing here is financial
> advice. **Default to Testnet, validate thoroughly with backtests and paper
> trading, and never trade money you cannot afford to lose.** You are solely
> responsible for any use of this software and for complying with the laws and
> exchange terms that apply to you.

---

## Status

**Version 0.1.0 — Phase 3 complete.** Python **3.12+**.

What works today, verified against Binance **Testnet**:

- Typed configuration (`.env` + `config.yaml`) and the `Decimal`-safe domain model.
- **Async Binance Spot REST adapter** — balances, symbol info, ticker, klines,
  create/cancel/query orders — with retry, rate-limit handling, and
  exchange-filter compliance.
- **Live WebSocket kline streaming** that delivers closed candles 24/7, with
  capped-exponential backoff and unbounded reconnection.
- **Market-data provider** that seeds REST history, maintains a bounded rolling
  buffer per pair, and exposes a time-ordered `float64` OHLCV DataFrame.
- **Trading engine** that evaluates a strategy on every bar close, gated by the
  strategy's warmup period, with per-pair failure containment.

`python -m trading_bot run` connects to Testnet and exercises the whole
data → strategy → signal path end to end.

> **The bot cannot place an order yet.** Strategies are still stubs (Phase 4), so
> every pair quarantines after its configured error budget; risk management,
> order execution, persistence, and notifications are not built. Per-feature
> status is tracked in the [Roadmap](#roadmap-build-phases).

## Features

*Target feature set — see the [Roadmap](#roadmap-build-phases) for what is built
today versus planned.*

- Secure Binance Spot connectivity with **Testnet, Live, Paper, and Backtest** modes (Testnet is the default).
- Real-time market data over WebSockets, with automatic reconnection.
- Pluggable, registry-based **strategies** selected from config.
- Comprehensive **risk management**: position sizing, stop-loss, take-profit, trailing stop, max daily loss, max open positions, per-symbol cooldown.
- Multiple trading pairs and timeframes.
- **Backtesting** engine and **paper-trading** simulator that reuse the live strategy/risk code.
- Configuration split between `.env` (secrets) and `config.yaml` (behaviour).
- Structured logging of every signal, trade, error, and system event.
- Telegram notifications.
- SQLite persistence (upgradeable to Postgres by changing one URL).
- Dockerised, type-hinted, and tested with `pytest`.

## Tech stack

Python 3.12+ · python-binance · pandas / NumPy · pydantic · SQLAlchemy ·
httpx · tenacity · Docker · pytest · ruff · mypy.

## Project structure

```
binance-trading-bot/
├── src/trading_bot/
│   ├── main.py            # CLI entry point (run / backtest / strategies)
│   ├── config/            # Typed settings: .env secrets + config.yaml
│   ├── core/              # Domain: enums, models, interfaces, exceptions
│   ├── exchange/          # Binance REST adapter + WebSocket kline stream
│   ├── data/              # Market-data provider · historical loader (stub) · repository (stub)
│   ├── strategies/        # Strategy base + registry/factory · example strategies (stubs)
│   ├── indicators/        # Technical indicators: SMA, EMA, RSI, MACD, Bollinger, ATR
│   ├── risk/              # Risk manager, position sizing, exit rules (stubs)
│   ├── execution/         # Order executor + lifecycle manager (stubs)
│   ├── engine/            # Bar-close orchestration · mode wiring (stub)
│   ├── backtesting/       # Backtest engine, portfolio, metrics
│   ├── paper/             # Paper-trading simulator
│   ├── notifications/     # Notifier base + Telegram
│   ├── persistence/       # SQLAlchemy engine + ORM models
│   └── utils/             # Logging setup + pure helpers
├── tests/                 # unit/ and integration/ suites
├── scripts/               # Operational scripts (check_testnet.py, download_data.py)
├── data/                  # Local DB + historical data (gitignored)
├── logs/                  # Log files (gitignored)
├── config.yaml            # Non-secret runtime configuration
├── .env.example           # Template for secrets — copy to .env
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Dev/test dependencies
├── pyproject.toml         # Packaging + ruff/mypy/pytest config
├── Dockerfile             # Multi-stage, non-root runtime image
├── docker-compose.yml     # Service definition with volumes + env_file
└── Makefile               # Common developer commands
```

### Why this layout

Each folder maps to one architectural layer with a single responsibility, and
dependencies point **inward** toward `core`. `core` defines the domain models and
the abstract interfaces (ports); every outward layer (exchange, notifications,
persistence, strategies) implements those interfaces. Because higher-level code
depends only on the abstractions in `core.interfaces`, any implementation can be
swapped or mocked without changing its callers — which is what keeps the code
testable and lets the *same* strategy and risk logic run identically across
backtest, paper, and live modes.

The exchange layer is a concrete example of this. `core.interfaces.ExchangeClient`
is the port; `exchange.binance_client.BinanceClient` is the adapter. All Binance
JSON is converted to domain models by the pure functions in `exchange.models`, and
every call is routed through a shared retry/error-translation helper so callers
only ever see domain exceptions (`RateLimitError`, `OrderError`, …), never raw
library or transport errors.

### The `Decimal` → `float` boundary

Money is `Decimal` throughout the domain — never `float`, so no accounting value
is ever subject to binary rounding. Indicator maths, however, runs on NumPy,
which has no Decimal fast path. `data/market_data.py` is the **single, deliberate
place** that conversion happens, and it is one-directional: the rolling buffer
stores full-precision `Candle` objects and only the derived DataFrame is
`float64`. Strategies read the `float` frame; risk and execution read prices back
through `MarketDataProvider.last_candle()`, which still returns `Decimal`.

## Getting started

### Using make (Linux / macOS)

```bash
# 1. Create and activate a virtual environment
make venv && source .venv/bin/activate

# 2. Install dependencies (+ the package, editable)
make install-dev

# 3. Configure secrets
cp .env.example .env         # then edit .env with your keys
#    - Testnet keys (free): https://testnet.binance.vision/

# 4. Review behaviour in config.yaml (mode defaults to: testnet)

# 5. Sanity-check the setup
make test
python -m trading_bot strategies

# 6. Verify live connectivity against Binance Testnet (read-only)
python scripts/check_testnet.py
```

### Windows (PowerShell), without make

```powershell
# 1. Create and activate a virtual environment (Python 3.12+)
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies (+ the package, editable)
pip install -r requirements-dev.txt
pip install -e .

# 3. Configure secrets, then edit .env with your keys
copy .env.example .env

# 4. Sanity-check the setup
pytest
python scripts\check_testnet.py
```

## Verifying exchange connectivity

`scripts/check_testnet.py` confirms your API keys are wired correctly and that the
REST adapter can reach the exchange. It performs **read-only** calls only (ping,
balances, ticker) and never places an order.

```bash
python scripts/check_testnet.py                 # Testnet (default)
python scripts/check_testnet.py --symbol ETHUSDT
python scripts/check_testnet.py --mode live --confirm-live   # Live requires explicit opt-in
```

For safety the script takes its mode **only** from `--mode` (default `testnet`),
deliberately ignoring the mode in `config.yaml`/`BOT_MODE` so a stray `live` there
can never cause an accidental live connection; `--mode live` additionally requires
`--confirm-live`. Exit codes: `0` success, `1` exchange error, `2` configuration
error (e.g. missing keys).

Expected output (Testnet):

```
Connecting to Binance TESTNET ...
  ping: OK
  balances: N asset(s) with a non-zero balance
    ...
  BTCUSDT last=... bid=... ask=...
All checks passed.
```

## Using the exchange adapter

The adapter is async and dependency-injects a configured client via
`BinanceClient.create(settings)`. Money is `Decimal` end-to-end. With the default
`enforce_filters=True`, order price/quantity are rounded down to the symbol's
tick/step and sub-minimum orders are rejected **before** any network call — so
invalid requests never reach Binance.

```python
import asyncio
from decimal import Decimal

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import OrderSide, OrderType
from trading_bot.core.models import OrderRequest
from trading_bot.exchange import BinanceClient


async def main() -> None:
    settings = get_settings()  # mode comes from config.yaml (default: testnet)

    async with await BinanceClient.create(settings) as client:
        # --- Market data ---
        ticker = await client.get_ticker("BTCUSDT")
        print("BTCUSDT last:", ticker.last)

        candles = await client.get_klines("BTCUSDT", "1m", limit=100)
        # The most recent candle may still be forming (is_closed == False).
        print("closed candles:", sum(c.is_closed for c in candles))

        # --- Account ---
        balances = await client.get_balances()
        print("non-zero assets:", sum(1 for b in balances if b.total > 0))

        # --- Place a filter-compliant LIMIT order on Testnet ---
        request = OrderRequest(
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        order = await client.create_order(request)
        print("order:", order.order_id, order.status.value)

        # Or validate against the exchange without placing it:
        # await client.validate_order(request)


asyncio.run(main())
```

> Live trading uses the same code path but requires `mode: live` (or `BOT_MODE=live`)
> **and** live API keys. Start on Testnet and promote deliberately.

## Streaming market data and running the engine

`BufferedMarketDataProvider` bridges REST history and the live WebSocket into the
DataFrame strategies consume. `TradingEngine` sits on top and evaluates a strategy
each time a bar closes — it does not poll.

```python
import asyncio

from trading_bot.config.settings import get_settings
from trading_bot.data.market_data import BufferedMarketDataProvider
from trading_bot.engine.live_engine import TradingEngine


async def main() -> None:
    settings = get_settings()  # mode from config.yaml (default: testnet)

    # --- Market data on its own -------------------------------------------
    provider = await BufferedMarketDataProvider.create(settings)  # tracks enabled pairs
    await provider.start()  # seeds history, then goes live
    try:
        df = provider.get_dataframe("BTCUSDT", "1m")
        print(df.shape, df.index.tz, df["close"].dtype)  # (499, 5) UTC float64

        # Money keeps full precision behind the float frame:
        print(provider.last_candle("BTCUSDT", "1m").close)  # Decimal('...')
        print(provider.is_ready("BTCUSDT", "1m", warmup_period=50))  # True
    finally:
        await provider.stop()

    # --- Or let the engine drive it ---------------------------------------
    engine = await TradingEngine.create(settings)  # builds provider + per-pair strategies

    async def on_signal(signal) -> None:
        print("signal:", signal.action.value, signal.symbol, signal.reason)

    engine.on_signal(on_signal)  # risk + execution attach here in later phases
    await engine.run()  # runs until SIGINT/SIGTERM or engine.request_stop()


asyncio.run(main())
```

Relevant `config.yaml` knobs:

```yaml
data:
  history_limit: 500        # candles seeded per pair at startup (Binance max: 1000/call)
  buffer_size: 1000         # rolling in-memory bars per pair (must be >= history_limit)

engine:
  reconnect_max_retries: 0  # 0 = reconnect forever (recommended for 24/7)
  max_strategy_errors: 5    # consecutive failures before a pair is quarantined
```

If a strategy's `warmup_period` exceeds `data.history_limit`, the engine warns at
startup and that pair stays silent until enough bars have closed live.

## Running the bot

```bash
python -m trading_bot run                 # mode from config.yaml (testnet)
python -m trading_bot run --mode paper    # paper trading (no orders sent)
python -m trading_bot backtest            # historical replay
python -m trading_bot strategies          # list registered strategies
```

> **What `run` does today.** It connects to Testnet, seeds history, streams live
> candles, and evaluates strategies on each bar close. Because strategies are
> still stubs, each pair logs a failure and is quarantined after
> `engine.max_strategy_errors` bars — that is the expected Phase 3 output. Stop
> with Ctrl-C; SIGINT/SIGTERM both trigger a graceful shutdown that closes the
> WebSocket and REST connections. `backtest` remains unimplemented.

### With Docker

```bash
cp .env.example .env         # fill in values
make docker-build
make docker-up               # runs the bot; logs/ and data/ are mounted
```

## Configuration model

- **`.env`** — secrets only (API keys, Telegram token). Never committed.
- **`config.yaml`** — everything else (mode, pairs, strategy params, risk limits, logging, database).
- An optional `BOT_MODE` env var overrides `mode` in `config.yaml`.
- In Testnet mode, testnet-specific keys (`BINANCE_TESTNET_API_KEY` / `..._SECRET`) are used and fall back to the primary keys if unset.
- Secrets are read from environment variables and, additionally, from a local `.env` file; they are never written to logs.

## Development

```bash
make lint      # ruff
make type      # mypy (strict)
make test      # pytest (offline; integration deselected)
make cov       # pytest with coverage
make check     # lint + type + test
```

On Windows without make, run the tools directly, e.g. `ruff check src tests`,
`mypy`, `pytest`. New code is developed under `mypy --strict` and `ruff`
(`E, F, I, N, UP, B, C4, SIM, RUF`), and every module built so far
(`exchange/`, `data/`, `engine/`, `config/`, `core/`, `utils/`) passes both.

Both tools currently report a stable set of findings on **deliberate, locked
patterns** in earlier scaffolding — `str`+`Enum` bases, `timezone.utc` (kept in
preference to the `datetime.UTC` alias), quoted forward references, and pydantic
`default_factory` under an unpinned newer mypy. Those are known and unchanged;
the working rule is that new work adds **zero net findings**. Adding
`plugins = ["pydantic.mypy"]` to `[tool.mypy]` clears the `default_factory`
group if you would rather fix than freeze them.

### Tests

The default suite is **hermetic and offline** — unit tests inject a mock exchange,
so `make test` (and plain `pytest`) never touch the network. Integration tests are
marked `integration` and excluded from the default run.

```bash
pytest                        # offline unit tests (integration auto-skips)
pytest -m "not integration"   # explicitly exclude integration
pytest -m integration         # opt-in: live read-only check against Testnet
```

**Running the integration test.** Its skip-guard checks the **process
environment** (`BINANCE_TESTNET_API_KEY` / `..._SECRET`, or the primary keys). If
your keys live only in `.env`, the app and `scripts/check_testnet.py` will still
pick them up and connect — but the integration test will **skip**, because a bare
`.env` is not exported to the process environment. To actually run it, export the
keys for the session:

```powershell
# PowerShell
$env:BINANCE_TESTNET_API_KEY="your_testnet_key"
$env:BINANCE_TESTNET_API_SECRET="your_testnet_secret"
pytest -m integration
```

```bash
# bash
export BINANCE_TESTNET_API_KEY="your_testnet_key"
export BINANCE_TESTNET_API_SECRET="your_testnet_secret"
pytest -m integration
```

The integration tests never place an order. There are three, all opt-in:

| Test | What it does |
| --- | --- |
| `test_testnet_integration.py` | Read-only REST calls (ping, balances, ticker). |
| `test_ws_stream_integration.py` | Subscribes to a live kline stream, waits for one closed candle. |
| `test_market_data_integration.py` | Seeds real history, then waits for a live candle to extend the frame. |

The two streaming tests wait on a 1-minute bar, so each can take up to a minute.

## Roadmap (build phases)

1. **Scaffolding** — structure, config, logging, domain models, interfaces, tests. ✅
2. **Binance connectivity** — async REST adapter (balances, symbol info, ticker, klines, orders), `Decimal`-safe response mapping, retry + rate-limit handling, exchange-filter compliance, Testnet/Live. ✅
3. **Market data + engine skeleton** — WebSocket kline streaming with auto-reconnect, the rolling-buffer market-data provider (`Decimal`→`float` boundary), and the bar-close trading engine with warmup gating and failure containment. ✅
4. Indicators + concrete strategies. ⬅️ *next*
5. Risk management (sizing + exit rules).
6. Order execution + lifecycle — the first phase in which the bot can place an order.
7. Engine completion: wire risk + execution into the loop, paper-trading mode.
8. Backtesting engine + metrics.
9. Persistence (SQLAlchemy) + Telegram notifications.
10. Hardening: gap backfill, staleness watchdog, monitoring, optional FastAPI health/metrics.

Phase 3 delivered the orchestration skeleton earlier than originally planned
(it was item 7), because the market-data provider needed a consumer to be
verifiable end to end. Item 7 is now about filling that skeleton in.

## License

MIT — declared in `pyproject.toml`. A `LICENSE` file is not yet present in the
repository; add the standard MIT text as `LICENSE` before publishing.
