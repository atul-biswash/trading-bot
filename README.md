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

## Features

- Secure Binance Spot connectivity with **Testnet, Live, Paper, and Backtest** modes (Testnet is the default).
- Real-time market data over WebSockets.
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
httpx · Docker · pytest · ruff · mypy.

## Project structure

```
binance-trading-bot/
├── src/trading_bot/
│   ├── main.py            # CLI entry point (run / backtest / strategies)
│   ├── config/            # Typed settings: .env secrets + config.yaml
│   ├── core/              # Domain: enums, models, interfaces, exceptions
│   ├── exchange/          # Binance REST + WebSocket adapters
│   ├── data/              # Market-data provider, historical loader, repository
│   ├── strategies/        # Strategy base, registry/factory, example strategies
│   ├── indicators/        # Technical-indicator functions (pandas/NumPy, in-house)
│   ├── risk/              # Risk manager, position sizing, exit rules
│   ├── execution/         # Order executor + lifecycle manager
│   ├── engine/            # Orchestration loop and mode wiring
│   ├── backtesting/       # Backtest engine, portfolio, metrics
│   ├── paper/             # Paper-trading simulator
│   ├── notifications/     # Notifier base + Telegram
│   ├── persistence/       # SQLAlchemy engine + ORM models
│   └── utils/             # Logging setup + pure helpers
├── tests/                 # unit/ and integration/ suites
├── scripts/               # Operational scripts (e.g. download_data.py)
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

## Getting started

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
```

## Running

```bash
python -m trading_bot run                 # mode from config.yaml (testnet)
python -m trading_bot run --mode paper    # paper trading (no orders sent)
python -m trading_bot backtest            # historical replay
```

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
- In Testnet mode, testnet-specific keys are used and fall back to the primary keys if unset.

## Development

```bash
make lint      # ruff
make type      # mypy (strict)
make test      # pytest
make cov       # pytest with coverage
make check     # lint + type + test
```

## Roadmap (build phases)

1. **Scaffolding** — structure, config, logging, domain models, interfaces, tests. ✅ *(current)*
2. Binance connectivity (REST client, Testnet/Live).
3. WebSocket market-data streaming.
4. Indicators + concrete strategies.
5. Risk management (sizing + exit rules).
6. Order execution + lifecycle.
7. Engine orchestration (live/testnet/paper loop).
8. Backtesting engine + metrics.
9. Persistence (SQLAlchemy) + Telegram notifications.
10. Hardening: reconnection, monitoring, optional FastAPI health/metrics.

## License

MIT (placeholder — add a `LICENSE` file).
