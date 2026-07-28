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

**Version 0.1.0 — Phases 1–4 complete; Phase 5 (risk) through M3.** Python **3.12+**.

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
- **Hand-written indicators** (SMA, EMA, RSI, MACD, Bollinger, ATR) and two real
  strategies (SMA crossover, RSI), edge-triggered and stateless.
- **Risk management** — position sizing, protective stop-loss / take-profit /
  trailing-stop levels, and a risk manager that turns a signal into an approved,
  sized, protected `TradeIntent` against portfolio limits.

`python -m trading_bot run` connects to Testnet and exercises the whole
data → strategy → signal path end to end, emitting real signals.

> **The bot cannot place an order yet.** The risk layer produces a complete
> `TradeIntent`, but nothing dispatches it: order execution, persistence and
> notifications are still stubs, and the risk manager is not yet wired into the
> engine's signal handler. That wiring is Phase 5 M4, and order dispatch is M5.
> Per-feature status is tracked in the [Roadmap](#roadmap-build-phases).

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
│   ├── core/              # Domain: enums, models, portfolio, interfaces, exceptions
│   ├── exchange/          # Binance REST adapter + WebSocket kline stream
│   ├── data/              # Market-data provider · historical loader (stub) · repository (stub)
│   ├── strategies/        # Strategy base + registry/factory · SMA crossover, RSI
│   ├── indicators/        # Technical indicators: SMA, EMA, RSI, MACD, Bollinger, ATR
│   ├── risk/              # Risk manager, position sizing, protective exit rules
│   ├── execution/         # Order executor + lifecycle manager (stubs)
│   ├── engine/            # Bar-close orchestration · mode wiring (stub)
│   ├── backtesting/       # Backtest engine, portfolio, metrics (stubs)
│   ├── paper/             # Paper-trading simulator (stub)
│   ├── notifications/     # Notifier base + Telegram (stubs)
│   ├── persistence/       # SQLAlchemy engine + ORM models (stubs)
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

    engine.on_signal(on_signal)  # RiskManager.evaluate attaches here in M4
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

## Risk: from a signal to a sized, protected intent

`RiskManager` is the component that decides whether a signal becomes a trade. It
holds configuration, a market-data reference, per-pair exchange filters and a
clock — and performs **no I/O**, so it is entirely testable with plain numbers.
Account state lives separately on `Portfolio` and is passed in per call.

```python
from decimal import Decimal

from trading_bot.core.portfolio import Portfolio
from trading_bot.risk import PairContext, RiskManager

# Filters are primed once at startup rather than fetched per signal.
info = await client.get_symbol_info("BTCUSDT")
manager = RiskManager(
    config=settings.config.risk,
    provider=provider,
    pairs={"BTCUSDT": PairContext(timeframe="1m", symbol_info=info)},
)

portfolio = Portfolio(free_quote=Decimal("10000"))
assessment = manager.evaluate(signal, portfolio=portfolio)

if assessment.approved:
    intent = assessment.intent            # quantity, side, price, protective levels
    print(intent.quantity, intent.levels.stop_loss, intent.levels.take_profit)
else:
    print("no trade:", assessment.reason)  # always says which rule refused, and why
```

The decision runs in a fixed order — limits → ATR → protective levels → sizing →
affordability — because each step depends on the one before it. Every refusal is
a **returned value carrying its reason**, never an exception and never a silent
zero: "the account is too small for this symbol", "the daily-loss cap is hit",
"no stop fits on the tick this bar" are all routine answers, and an operator has
to be able to tell them apart. With `risk_per_trade` sizing the quantity is
chosen so the loss at the *realised* (post-rounding) stop never exceeds the
configured fraction of equity.

> Nothing here places an order — `evaluate` returns an intent. Mapping that
> intent onto an entry order plus its protective orders is Phase 5 M5.

## Running the bot

```bash
python -m trading_bot run                 # mode from config.yaml (testnet)
python -m trading_bot run --mode paper    # paper trading (no orders sent)
python -m trading_bot backtest            # historical replay
python -m trading_bot strategies          # list registered strategies
```

> **What `run` does today.** It connects to Testnet, seeds history, streams live
> candles, evaluates strategies on each bar close, and **logs the signals they
> produce**. It does not size, vet or place anything: the risk manager is built
> and tested but not yet attached to `engine.on_signal`, which is Phase 5 M4.
> Stop with Ctrl-C; SIGINT/SIGTERM both trigger a graceful shutdown that closes
> the WebSocket and REST connections. `backtest` remains unimplemented.

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
`mypy`, `pytest`. Code is developed under `mypy --strict` and `ruff`
(`E, F, I, N, UP, B, C4, SIM, RUF`).

**Both tools report a hard zero.** This is a gate, not a baseline to diff
against — any new finding is a regression:

```
pytest                      # 510 passed  (507 unit + 3 opt-in Testnet integration)
pytest -m "not integration" # 507 passed  — use this for fast iteration
mypy                        # Success: no issues found in 55 source files
ruff check src tests        # All checks passed!
```

Zero is not reached by suppression: `type: ignore` appears nowhere in `src/`.
The two project-wide `ruff` ignores that do exist (`UP017` for `timezone.utc`,
`UP042` for `str`+`Enum`) are deliberate style decisions documented with their
reasoning in `pyproject.toml`, not silenced defects.

Note `ruff format` is **not** a gate, and some files are not formatter-clean.
Run it deliberately in its own commit if you want to close that gap — check what
it does to hand-laid data tables in tests first.

### Tests

Unit tests are **hermetic**: no network, no real time, scripted fakes, and
injectable seams (the `sleep` used by retry/backoff, and the `Clock` the
time-dependent risk rules read). Money assertions are exact `Decimal`
comparisons — never a float tolerance, because a result that is merely *close*
is a bug, and a tolerant test cannot detect the float leak the domain exists to
prevent.

```bash
pytest                        # everything, including integration if keys are present
pytest -m "not integration"   # offline only — use this for fast iteration
pytest -m integration         # just the live read-only checks against Testnet
```

**Running the integration tests.** The skip-guard reads credentials through the
application's own `Secrets` object, so keys in **`.env` are enough** — they do
not need to be exported to the process environment. With keys present, plain
`pytest` runs them (the two streaming tests each wait on a 1-minute bar, so the
full run takes ~90s); without keys, they skip with an explanatory reason.

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
4. **Indicators + concrete strategies** — hand-written SMA, EMA, RSI, MACD, Bollinger and ATR (warmup expressed as leading `NaN`), plus edge-triggered SMA-crossover and RSI strategies. ✅
5. **Risk management** — position sizing (M1 ✅), protective stop-loss / take-profit / trailing-stop rules (M2 ✅), the risk manager + portfolio that compose them into a `TradeIntent` (M3 ✅), then the composition root that wires it into the engine behind a log-only executor (M4 ⬅️ *next*), then order execution + lifecycle (M5) — the milestone in which the bot can first place an order.
6. Engine completion: wire risk + execution into the loop, paper-trading mode.
7. Backtesting engine + metrics.
8. Persistence (SQLAlchemy) + Telegram notifications.
9. Hardening: gap backfill, staleness watchdog, monitoring, optional FastAPI health/metrics.

Phase 3 delivered the orchestration skeleton earlier than originally planned
(it was a later item), because the market-data provider needed a consumer to be
verifiable end to end. Phase 5 M4 is now about filling that skeleton in.

## License

MIT — declared in `pyproject.toml`. A `LICENSE` file is not yet present in the
repository; add the standard MIT text as `LICENSE` before publishing.
