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

**The bot places orders, books what they realise net of the venue's exit fee,
and has done both against a real venue.** Live trading is refused at every entry
point until entry fees are netted out of position quantities; Testnet is the
only venue it will connect to.

| Area | State |
|---|---|
| Config, typed domain, `Decimal`-safe money | ✅ built |
| Binance Spot REST adapter (balances, symbol info, ticker, klines, orders, order lists) | ✅ built |
| WebSocket kline streaming with auto-reconnect | ✅ built |
| Market-data provider (REST seed + rolling buffer + float64 frame) | ✅ built |
| Indicators (SMA, EMA, RSI, MACD, Bollinger, ATR) and strategies | ✅ built |
| Risk: sizing, protective levels, limits, `RiskManager` | ✅ built |
| Composition root wiring the whole decision path | ✅ built |
| Reconciler — reads what rests at the venue and records it | ✅ built, **has run against real positions** |
| Order execution — entry, protection, and the discretionary close | ✅ built |
| Realised P&L reaching the ledger, and surviving a restart | ✅ built |
| Crash-survivable store for pending records and the ledger | ✅ built |
| Backtesting, paper simulator, notifications | ⛔ stubs |

`python -m trading_bot run` connects to Testnet and runs
data → strategy → risk → execution end to end. It seeds a portfolio from your
balance, primes each pair's exchange filters, restores the ledger and any
unresolved records from disk, and logs every signal's outcome as a structured
`risk_refused` or `intent_dispatched` line. **The executor is chained after
`IntentLogger` rather than replacing it**, so the logger still records every
assessment, approved or refused.

An entry goes out as **one order-list call** carrying the working leg and its
protection together — there is no client-side/exchange split. A `CLOSE` cancels
the list, re-queries each leg (because a leg can fill *during* the cancel), sells
`MARKET`, and books the exit at the venue's own quote total. A sell whose outcome
is never learned keeps its record and is re-observed on the next candle.

**What has NOT happened is the thing to keep in view.** Supervised runs have
taken **165 complete exits** — 154 `close_booked`, 11 `exit_booked` — across
185 order lists, and the log that records them is gitignored.
`docs/RUN_LEDGER.md` holds the census, with the command behind each figure and
the digest of the capture it came from. **The paths added at M5k are not shown
to have run**: no booking line in any capture carries `quote_total_source`,
which every booking line writes from M5k's last commit, and none of the
milestone's other new events appears. The fee settlement did run, eight times,
and every fee it read was zero. **A take-profit has filled three times** — on
2026-09-18, 2026-09-19 and 2026-09-21. **One of the three close-plan outcomes —
`HALT` — has never occurred**, zero across 163 close plans. `ALREADY_CLOSED`
occurred once, on 2026-09-15; the ambiguous-placement recovery ran on
2026-08-27; and the staleness refusal fired once, on 2026-09-24. Those figures
are measured against a capture whose SHA-256 is
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528` — events by
`scripts/run_census.py`, the rest by `grep -c` — and they move whenever the bot
runs. See `docs/NEXT_MILESTONE.md`.

Eleven files are docstring-only placeholders: `execution/order_manager`,
`paper/simulator`, `persistence/database`, `persistence/models`,
`notifications/`, `backtesting/`, `data/historical`, `data/repository`. Note
`persistence/store.py` is **not** among them — it is built and in use; only the
SQLAlchemy-shaped pair beside it are stubs. Check before assuming behaviour;
`backtest` exits with "not implemented yet".

**At M5-0's close, where protective orders would rest had been decided and
written down** — `docs/QC_PROTECTIVE_ORDERS.md` — but not implemented. That
contract was what M5 was to build, across six milestones: the vocabulary first,
then the entry reference, the adapter, the ledger, dispatch, and the
discretionary close. Only the fifth could cause a fill.

**By M5c's close M5a, M5b and M5c were complete, and not one of them had
placed an order.** M5a built
the vocabulary — the five safety fields on `RiskConfig`, of which **five of the
six numbers were placeholders that had not been measured** and said so in those
words, because a rationale is not a sample — plus a config-load refusal for a
dispatch budget that cannot fit the shortest bar, and three fixes to `_enforce`.
M5b split the trade intent and widened the risk port.

**M5c specified the adapter surface and did not build it, and that distinction
was the honest headline at its close.** It set out to build the order-list
methods, the request mapper and the client-order-ID scheme; at M5c's close none
of those existed. What it produced
instead was the Binance error classifier — six families dispatched from a rule
table, every classified error from then on carrying the exchange's own code — and four
Testnet probes that turned assumptions into measurements: the 36-character
client-order-ID limit, the insufficient-balance message, the fact that cancelling
one leg of an order list collapses the whole list, and the rule that **a client
order ID is unique only against live orders, because a terminal order's ID is
released**. The first probe concluded the opposite of that last one and was
corrected by a later arm; both readings are on the record.

**M5d built the surface M5c specified, and placed exactly one order to prove
it.** By M5d's close the adapter mapped a protective entry end to end —
request type, filter enforcement per leg, parameter mapper, placement call,
response mapper — plus
the deterministic client-order-ID scheme the recovery path depends on. A single
Testnet OTOCO was placed and cancelled within seconds: the venue accepted 15 of
16 parameters straight from our own mapper and honoured every generated ID
byte-for-byte, and the same order answered the milestone's best open question by
showing that pending protective legs **are** visible while still `PENDING_NEW`.
Balances were identical before and after.

**At M5d's close it still did not trade.** The port declaration and its first
caller were to land together at M5e — they landed at M5f — because nothing yet
called a placement method and declaring an interface nobody uses is the failure
this project had already paid for once.

So M5e started from a fully specified surface and an empty `execution/`. That
was a better position than it sounds — every parameter set and error meaning it
needed had been measured rather than assumed — but it was not progress toward a
fill.

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
never cause an accidental live connection. `--mode live` is blocked by
architectural invariant (CLAUDE.md): it is refused before any setting is read,
exit `1`, and `--confirm-live` confirms nothing. Exit codes: `0` ok, `1`
exchange error or live refused, `2` config error.

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
ruff format --check src tests scripts  129 files already formatted
mypy                                   Success: no issues found in 79 source files
pytest                                 1819 passed, 4 skipped
                                       (1822 passed, 1 skipped with Testnet credentials)
```

### How to read that output — it has two honest forms

**The gate's output is not a function of the tree alone.** It varies by two
things, and both are expected:

- **Credentials.** The three integration tests are skipped without Binance Testnet
  keys. The *same commit* reports `1819 passed, 4 skipped` on a machine without
  them and `1822 passed, 1 skipped` on a machine with them. **Both are green.** A
  fresh clone seeing 1819 is not looking at a regression — quote the count with its
  condition, never bare. The skipped column never reaches zero: one unit test skips
  on Windows because `time.tzset` is POSIX-only, which is the lone skip in the
  credentialed run and the fourth in the uncredentialed one.
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
  core/          models · enums · interfaces (ports) · portfolio · assessment
                 · exceptions
  config/        settings · pydantic config models
  exchange/      base · binance_client · models (mappers) · websocket_client
                 · ids
  data/          market_data · historical† · repository†
  indicators/    hand-written TA functions
  strategies/    base · registry · helpers · examples/
  engine/        live_engine · modes (composition root)
  risk/          manager · rules · position_sizing
  execution/     executor · placement · dispatch_budget · resolution
                 · reconciliation · reconciliation_driver · close_plan
                 · bookability · booking_line · order_manager†
  backtesting/   engine† · portfolio† · metrics†
  paper/         simulator†
  persistence/   store · database† · models†
  notifications/ base† · telegram†
  utils/         logger · helpers · instance_lock
scripts/         check.py (the gate) · check_testnet.py · download_data.py
                 · check_findings.py · check_gate_counts.py
                 · check_arming_conditions.py · run_census.py
                 · mutation_survey.py · abc_double_census.py
                 · cancel_testnet_order_list.py · clear_testnet_holdings.py
                 · probe_x1.py
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
