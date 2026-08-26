# Binance Spot Trading Bot

An automated trading bot for **Binance Spot**, built as production-grade software
rather than a script: clean architecture, exact decimal money, a hard-zero quality
gate, and every design decision written down with its reasoning.

> ⚠️ **Risk & disclaimer.** This is educational software provided **as-is, with no
> warranty**. Automated trading of cryptocurrency carries a substantial risk of
> financial loss, including the total loss of funds. Nothing here is financial
> advice. **Default to Testnet, validate thoroughly, and never trade money you
> cannot afford to lose.** You are solely responsible for any use of this software
> and for complying with the laws and exchange terms that apply to you.

---

## What it is

A single-account, bar-close trading bot for Binance Spot. It streams closed
candles over WebSocket, evaluates a strategy on each bar close, sizes and vets the
resulting signal against configured risk limits, and produces an approved, sized,
protected intent to trade.

Python **3.12+**. Testnet is the default in every mode, example and script.

## What it deliberately does **not** do

Reading this list first will save you time if it is not the tool you want.

- **No futures, no margin, no leverage, no shorting.** Spot only, long only.
  `SignalAction.SELL` exists in the domain and is unreachable — on spot it would
  mean opening a short.
- **No high-frequency or tick-level trading.** It reacts at bar close and nowhere
  else. The fastest useful timeframe is minutes.
- **No pyramiding or averaging down.** One position per symbol, enforced.
- **No portfolio optimiser, no ML, no signal blending.** One strategy per pair,
  selected from config.
- **No hosted UI or web dashboard.** CLI and structured logs.
- **Not a backtester yet** — see build state below.

## Build state — read this before running it

**The bot cannot place an order yet.** This is the honest headline.

| Area | State |
|---|---|
| Config, typed domain, `Decimal`-safe money | ✅ built |
| Binance Spot REST adapter (balances, symbol info, ticker, klines, orders) | ✅ built |
| WebSocket kline streaming with auto-reconnect | ✅ built |
| Market-data provider (REST seed + rolling buffer + float64 frame) | ✅ built |
| Indicators (SMA, EMA, RSI, MACD, Bollinger, ATR) and strategies | ✅ built |
| Risk: sizing, protective levels, limits, `RiskManager` | ✅ built |
| Composition root wiring the whole decision path | ✅ built |
| Reconciler — reads what rests at the venue and records it | ✅ built, **never run against a real position** |
| **Order execution** | ⛔ **stub — M5 in progress** |
| Backtesting, paper simulator, persistence, notifications | ⛔ stubs |

`python -m trading_bot run` connects to Testnet and exercises
data → strategy → risk end to end. It seeds a portfolio from your balance, primes
each pair's exchange filters, and logs every signal's outcome as a structured
`risk_refused` or `intent_dispatched` line. **The executor is chained after
`IntentLogger` and it places orders** — the logger still records every
assessment, approved or refused, because the executor was chained after it
rather than replacing it.

**A reconciler now runs on every candle, and it has nothing to reconcile.** It
reads the venue's open orders per symbol, compares them against what each
position requested, records a verdict, and refuses new entries while the ledger
is not current. But **nothing constructs a position** — that is the executor's
job and the executor is a stub — so the pass visits an empty list on every bar.
It ships before the first order deliberately: with no trusted protection state,
the first position opened would have refused every entry after it.

Eleven files are docstring-only placeholders: `execution/order_manager`,
`paper/simulator`, `persistence/`, `notifications/`, `backtesting/`,
`data/historical`, `data/repository`. Check before assuming behaviour;
`backtest` exits with "not implemented yet".

**Where protective orders will rest has been decided and written down** —
`docs/QC_PROTECTIVE_ORDERS.md` — but not implemented. That contract is what M5
builds, across six milestones: the vocabulary first, then the entry reference,
the adapter, the ledger, dispatch, and the discretionary close. Only the fifth
can cause a fill.

**M5a, M5b and M5c are complete, and not one of them placed an order.** M5a built
the vocabulary — the five safety fields on `RiskConfig`, of which **five of the
six numbers are placeholders that have not been measured** and say so in those
words, because a rationale is not a sample — plus a config-load refusal for a
dispatch budget that cannot fit the shortest bar, and three fixes to `_enforce`.
M5b split the trade intent and widened the risk port.

**M5c specified the adapter surface and did not build it, and that distinction is
the honest headline.** It set out to build the order-list methods, the request
mapper and the client-order-ID scheme; none of those exist. What it produced
instead is the Binance error classifier — six families dispatched from a rule
table, every classified error now carrying the exchange's own code — and four
Testnet probes that turned assumptions into measurements: the 36-character
client-order-ID limit, the insufficient-balance message, the fact that cancelling
one leg of an order list collapses the whole list, and the rule that **a client
order ID is unique only against live orders, because a terminal order's ID is
released**. The first probe concluded the opposite of that last one and was
corrected by a later arm; both readings are on the record.

**M5d built the surface M5c specified, and placed exactly one order to prove
it.** The adapter now maps a protective entry end to end — request type, filter
enforcement per leg, parameter mapper, placement call, response mapper — plus
the deterministic client-order-ID scheme the recovery path depends on. A single
Testnet OTOCO was placed and cancelled within seconds: the venue accepted 15 of
16 parameters straight from our own mapper and honoured every generated ID
byte-for-byte, and the same order answered the milestone's best open question by
showing that pending protective legs **are** visible while still `PENDING_NEW`.
Balances were identical before and after.

**It still does not trade.** The port declaration and its first caller land
together at M5e, because nothing yet calls a placement method and declaring an
interface nobody uses is the failure this project has already paid for once.

So the next milestone starts from a fully specified surface and an empty
`execution/`. That is a better position than it sounds — every parameter set and
error meaning it needs is now measured rather than assumed — but it is not
progress toward a fill.

## Install

### Linux / macOS

```bash
make venv && source .venv/bin/activate
make install-dev
cp .env.example .env          # then add your keys
```

### Windows (PowerShell)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
pip install -e .
copy .env.example .env
```

Free Testnet keys: <https://testnet.binance.vision/>. Put them in
`BINANCE_TESTNET_API_KEY` / `BINANCE_TESTNET_API_SECRET`.

Secrets live in `.env` and never in `config.yaml`. Behaviour lives in
`config.yaml` and never in `.env`. `mode` defaults to `testnet`.

## Run

```bash
python scripts/check_testnet.py     # read-only connectivity check; places no order
python -m trading_bot strategies    # list registered strategies
python -m trading_bot run           # mode from config.yaml (testnet)
python -m trading_bot run --mode paper
python -m trading_bot backtest      # not implemented yet
```

`check_testnet.py` takes its mode **only** from `--mode` (default `testnet`),
deliberately ignoring `config.yaml` and `BOT_MODE`, so a stray `live` there can
never cause an accidental live connection. `--mode live` additionally requires
`--confirm-live`. Exit codes: `0` ok, `1` exchange error, `2` config error.

`run` stops cleanly on Ctrl-C; SIGINT and SIGTERM both close the WebSocket and
REST connections.

## The quality gate

```bash
python scripts/check.py
```

`scripts/check.py` **is** the gate — `ruff check` → `ruff format --check` → `mypy`
→ `pytest`, in that order. `make check` is a one-line delegation to it. All four
report a **hard zero**: this is a gate, not a baseline to diff against, and any
new finding is a regression.

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  92 files already formatted
mypy                                   Success: no issues found in 62 source files
pytest                                 1043 passed, 3 skipped
                                       (1046 = 1043 + 3 with Testnet credentials)
```

### How to read that output — it has two honest forms

**The gate's output is not a function of the tree alone.** It varies by two
things, and both are expected:

- **Credentials.** The three integration tests are skipped without Binance Testnet
  keys. The *same commit* reports `1043 passed, 3 skipped` on a machine without
  them and `1046 passed` on a machine with them. **Both are green.** A fresh clone
  seeing 1043 is not looking at a regression — quote the count with its condition,
  never bare.
- **Network.** Those three tests make live read-only calls to Testnet and two wait
  on a real 1-minute bar, so a full run takes ~90s longer and can fail for reasons
  unrelated to your change. The unit suite is deterministic; **treat a lone failure
  in a full run as suspect-integration and read the output before re-running.**

**Never pipe the gate.** A shell pipeline's exit status is the last stage's unless
`set -o pipefail`, so `python scripts/check.py | tail` reports `tail`'s success no
matter what the gate did — and truncates the diagnostic naming the failure. This
has masked a non-zero exit twice in this project. Run it bare and read its own
exit code.

Zero is not reached by suppression: `type: ignore` appears nowhere in `src/`. The
two project-wide `ruff` ignores that exist (`UP017` for `timezone.utc`, `UP042`
for `str`+`Enum`) are deliberate style decisions documented with their reasoning
in `pyproject.toml`.

### Tests

```bash
pytest                        # everything, including integration if keys are present
pytest -m "not integration"   # offline only — use this for fast iteration
pytest -m integration         # just the live read-only checks
```

Unit tests are **hermetic**: no network, no real time, scripted fakes, injectable
seams. Money assertions are exact `Decimal` comparisons — never a float tolerance,
because a result that is merely *close* is a bug, and a tolerant test cannot detect
the float leak the domain exists to prevent.

The three integration tests are opt-in, read-only, and **never place an order**.
Their skip-guard reads credentials through the application's own `Secrets` object,
so keys in `.env` are enough — they need not be exported.

## Docs map

| File | What it is | When to read it |
|---|---|---|
| `CLAUDE.md` | **The authority.** Architecture, locked decisions, the money rule, the gate, the workflow. | Before changing anything |
| `docs/NEXT_MILESTONE.md` | The current task and the single home for live open items | Starting work |
| `docs/PHASE_HISTORY.md` | Append-only build log: what each milestone decided and *why*, including alternatives rejected | Asking "why is it like this?" |
| `docs/QC_PROTECTIVE_ORDERS.md` | The protective-order contract M5 implements: where protection rests, the placement shapes, the identity scheme | Working on execution |
| `docs/QB_ESCALATION.md` | What `CRITICAL` does, its binding sites, and which can clear on their own | Handling failure paths |
| `docs/M5_NUMBERS.md` | The safety numbers, each with its cost-if-wrong and its measurement status | Choosing or changing a threshold |
| `PROJECT_KNOWLEDGE.md` | Orientation for a reviewer with no repository access | Reviewing from outside |

Precedence, when they disagree: **the code wins over `CLAUDE.md`, and `CLAUDE.md`
wins over everything else.**

## Design in one page

**Money is `Decimal` in the domain, never `float`** — enforced by a pydantic
validator that rejects `float` (and `numpy.float64`, which is a `float` subclass
and the realistic leak path), not merely documented. There is exactly **one**
`Decimal`→`float` boundary, in the data layer, because indicator maths runs on
NumPy: the rolling buffer keeps full-precision candles and only the derived
DataFrame is `float64`. Anything needing a price takes it from the candle.

**Clean architecture, dependencies pointing inward.** `core/` holds domain models
and abstract ports; every outer layer implements them. `core.interfaces.ExchangeClient`
is the port and `exchange.binance_client.BinanceClient` is the adapter — all
Binance JSON is converted by pure mapper functions, and every call is routed
through one retry/error-translation helper, so callers see domain exceptions and
never raw library or transport errors.

**Refusals are values, not exceptions.** "The account is too small for this
symbol", "the daily-loss cap is hit", "no stop fits on the tick this bar" are
routine answers on a path that runs every bar, and each is a frozen object
carrying its reason and the stage it stopped at. An operator must be able to tell
them apart, and a raise on a routine market state would print a traceback every
bar forever.

**Strategies are edge-triggered and stateless.** A cross fires on the transition
bar and is silent while the condition persists — otherwise execution places a
duplicate order every bar. State is recomputed from the buffer rather than held on
`self`, so behaviour is identical after a restart, after a reconnect redelivers a
corrected bar, and in backtest.

## Project layout

```
src/trading_bot/
  main.py        CLI entry point (run · backtest · strategies)
  core/          models · enums · interfaces (ports) · portfolio · exceptions
  config/        settings · pydantic config models
  exchange/      base · binance_client · models (mappers) · websocket_client
  data/          market_data · historical† · repository†
  indicators/    hand-written TA functions
  strategies/    base · registry · helpers · examples/
  engine/        live_engine · modes (composition root)
  risk/          manager · rules · position_sizing
  execution/     executor · placement · dispatch_budget · resolution
                 · reconciliation · reconciliation_driver · order_manager†
  backtesting/   engine† · portfolio† · metrics†
  paper/         simulator†
  persistence/   database† · models†
  notifications/ base† · telegram†
  utils/         logger · helpers
scripts/         check.py (the gate) · check_testnet.py · download_data.py
tests/           unit/ · integration/
```

† docstring-only stub.

## Docker

```bash
cp .env.example .env
make docker-build
make docker-up          # logs/ and data/ are mounted
```

## Tech stack

Python 3.12+ · python-binance · pandas / NumPy · pydantic · SQLAlchemy ·
Docker · pytest · ruff · mypy. Sixteen direct dependencies, every one pinned `==`.

## License

MIT — declared in `pyproject.toml`. A `LICENSE` file is not yet present; add the
standard MIT text before publishing.
