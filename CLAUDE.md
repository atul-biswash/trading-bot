# Binance Spot Trading Bot

Production-grade automated Binance Spot trading bot in Python. **Treat this as
software that will eventually manage real money.** Every design decision
prioritises correctness, safety and robustness over speed of development.

Detailed build history: `docs/PHASE_HISTORY.md`
Current task: `docs/NEXT_MILESTONE.md`

---

## Working method — non-negotiable

1. **One milestone at a time.** Finish and verify before moving on. If a task is
   too large, split it and do the first part only.
2. **Design before code.** Explain the approach, why it was chosen, and the
   alternatives — then stop and wait for my confirmation before implementing.
   If you see a better architecture than the one I proposed, say so first.
3. **Verify empirically.** Introspect the real code before relying on any API,
   shape or contract. Never assume a signature. Confirm the green baseline
   *before* changing anything.
4. **Never skip testing. Never trade code quality for speed.**
5. End every milestone with: summary of work, next recommended step, potential
   improvements — then stop for confirmation.

Standards: Clean Architecture, SOLID, DRY, KISS, PEP 8, full type hints, proper
exception handling. No hardcoded secrets — `.env` for secrets, `config.yaml` for
behaviour.

---

## The money rule — the single most important invariant

**Money is `Decimal` in the domain, never `float`.** Enforced, not documented:

```python
Money = Annotated[Decimal, BeforeValidator(_reject_float)]   # core/models.py
```

Every price, quantity and balance field uses it. Constructing one from a `float`
raises `ValidationError`. `numpy.float64` is caught by the same check — it is a
`float` subclass and is what `DataFrame.iloc` returns, which is the realistic
leak path. `int` and `str` pass through because both convert exactly.

`Decimal * float` raises `TypeError`, so any config value used in money
arithmetic needs a deliberate conversion boundary.

**There is exactly one `Decimal`→`float` boundary**, in the data layer:
`BufferedMarketDataProvider.get_dataframe()` produces float64 OHLCV because
indicator maths runs on NumPy. `last_candle()` returns full `Decimal` precision.
Anything needing a price takes it from the candle, never the frame.

**The `float`→`Decimal` boundaries are two, both named and singular.** The
primary is config load, done once by pydantic — *a config field becomes `Decimal`
at the milestone that first multiplies it by money **or compares it against
money**.* Comparison is the same boundary crossing as multiplication, minus the
warning: `Decimal * float` raises `TypeError`, so that crossing announces itself,
but `Decimal < float` is silent and decides against
`0.1000000000000000055…` rather than the `0.1` written in `config.yaml`. A field
consumed only by comparison would never trigger its own conversion. The second is
`risk/rules.py::_atr_to_decimal`, for the ATR value: a runtime float64 market
statistic (indicator maths runs on NumPy) that a stop price needs as `Decimal`.
Both are single, tested functions using the shortest-repr form — never scatter
`Decimal(str(x))` ad-hoc through business logic. Note the deliberate asymmetry:
these edges are where a float is *allowed* to become a Decimal; the domain is
where it is forbidden.

---

## Architecture

Clean Architecture. `core/` holds domain models and abstract ports; outer layers
implement them and depend inward only.

Files marked † are **docstring-only stubs**. Check before assuming behaviour.

```
src/trading_bot/
  main.py        CLI entry point (run · backtest · strategies)
  core/          models · enums · interfaces (ports) · portfolio · exceptions
  config/        settings · pydantic config models
  exchange/      base · binance_client · models (mappers) · websocket_client
  data/          market_data · historical† · repository†
  indicators/    hand-written TA functions
  strategies/    base · registry · helpers · examples/
  engine/        live_engine · modes†
  risk/          manager · rules · position_sizing
  execution/     executor† · order_manager†
  backtesting/   engine† · portfolio† · metrics†
  paper/         simulator†
  persistence/   database† · models†
  notifications/ base† · telegram†
  utils/         logger · helpers
scripts/         check_testnet.py · download_data.py
```

### Key seams

- **`MarketDataProvider`** — `get_dataframe(symbol, timeframe)` (float64 OHLCV,
  tz-aware UTC `DatetimeIndex` named `open_time`), `last_candle` (Decimal),
  `is_ready`, `on_candle`. It **appends before it notifies**, so a candle handed
  to a subscriber is already `buffer[-1]`.
- **`Strategy.generate_signal(symbol, candles, *, last_candle: Candle)`** — the
  frame is for indicator maths; `last_candle` is the only admissible source for
  `Signal.price` and `Signal.timestamp`.
- **`TradingEngine.on_signal(handler)`** — where risk and execution attach. The
  engine does **not** enrich signals; a signal leaves the strategy complete, so
  backtest and live share one code path. Handlers are isolated: one that raises
  is logged and cannot stop the others or the feed.
- **`RiskManager.evaluate(signal, *, portfolio) -> RiskAssessment`** — the seam
  execution picks up. `assessment.intent` is the approved, sized, protected
  `TradeIntent`; `None` with a `reason` is a normal, expected answer.

---

## Locked decisions — do not re-litigate without an explicit reason

**Domain**
- Value objects are **frozen** pydantic models; `Position` is mutable by design.
- `core/` imports pandas only under `TYPE_CHECKING`. Outer layers import normally.
- `SignalAction` is `BUY | SELL | CLOSE`. **There is no `HOLD`** —
  `generate_signal` returning `None` is the only "no opinion". `SELL` means "open
  a short" and is unreachable on spot, so strategies emit `BUY`/`CLOSE` only.

**Strategies**
- **Edge-triggered, not level-triggered.** A cross fires on the transition bar
  and is silent while the condition persists, or execution places a duplicate
  order every bar.
- **Stateless recomputation** from the buffer, never state on `self`. Identical
  after a restart, after a reconnect re-delivers a corrected bar, and in backtest.
- `warmup_period` is **derived from the indicator NaN contract**, never guessed.
  Indicators express warmup as leading `NaN` — never zero, never back-filled.
- **Insufficient data is not an error.** Short input returns all-`NaN` / `None`;
  raising would count toward the engine's quarantine and disable a pair that
  only needed more candles.
- `strength` stays `1.0` unless there is a defensible measure. A fabricated
  confidence that a later layer might multiply a position size by is worse than
  an honest constant; diagnostics go in `metadata` instead.
- `metadata` values must be plain `int`/`float`/`str` — it gets persisted, and
  NumPy scalars leak into logs and break serialisation.

**Risk**
- Rounding **down** to `step_size` for quantities (`ROUND_DOWN`). Rounding up can
  overspend a balance and get the order rejected — or filled.
- Exchange filters are applied **in sizing**, not deferred to execution:
  `BinanceClient._enforce` signals violations by *raising*, and "too small to
  trade" is routine, not exceptional. `_enforce` stays as an independent last
  line of defence.
- "No trade" is a **frozen value object carrying its reason**, never a bare
  `Decimal(0)`, `None`, or an exception. See `SizingDecision`. Protective results
  follow suit: frozen, `Money`-typed `ProtectiveLevels` / `TrailingStopUpdate` /
  `ExitDecision`.
- `equity` means **total portfolio value in quote currency**, not free balance.
- **A protective level rounds toward its reference** so its realised distance can
  only shrink — the initial stop toward entry (realised loss ≤ the
  `risk_per_trade` budget), the trailing stop toward the high-water mark, the
  take-profit toward entry. Uses `round_to_tick` (`ROUND_CEILING` / `ROUND_FLOOR`);
  `round_price` keeps `ROUND_DOWN` for order dispatch.
- **A sub-tick protective distance is representable, not a raise** — the level is
  `None` with its reason in `ProtectiveLevels.basis`. A stop can go sub-tick from
  a quiet market (transient) and the path runs every signal, so a raise would log
  a traceback on every bar forever. (It would *not* quarantine the pair: the
  engine counts **strategy** failures only — handler exceptions are caught and
  isolated in `_emit`.) Only incoherent *inputs* raise (non-positive price,
  non-finite or negative ATR).
- **The trailing stop is pure**: its high-water mark lives on `Position`;
  `update_trailing_stop` returns the new level, and `max` / `min` make "never
  moves against the position" a code property. `should_exit` is a pure predicate
  returning which rule fired (a stop beats the take-profit on one price).
- **State is `Portfolio`; policy is `RiskManager`.** The manager holds config, a
  market-data reference, injected per-pair filters (`PairContext`) and an
  injected `Clock`, performs **no I/O**, and takes the portfolio per call.
  `Portfolio` is mutable with `validate_assignment=True` and never reads a clock —
  every time-dependent method takes `now`, and a naive `datetime` raises.
- **The manager's order of operations is forced, not chosen:** preconditions →
  equity → `approve` → ATR → levels → stop gate → size → affordability → intent.
- **A stop that is enabled but not placeable this bar skips the entry — for every
  sizing method**, not just `risk_per_trade`. The operator asked for a stop; the
  state is transient. `stop_loss.enabled` distinguishes "stops are off" from "no
  level fits the tick right now".
- **The ATR bridge gates twice**: `is_ready(atr_period + 1)` before building the
  frame, then `isfinite` on the scalar — bar count alone is not sufficient,
  because a bad tick re-masks to NaN long after warmup. No ATR ⇒ refuse the
  signal; never fall back to a percent stop.
- **Exit evaluation is fed the closed candle's `close`**, never its high/low —
  triggering on a price the bar has already left is optimistic in backtest and
  dishonest live. `check_exit` / `advance_trailing_stop` live on the manager;
  *driving* them from the candle subscription is execution's job, because an exit
  check is per-candle-per-position and `on_signal` skips quiet bars.
- **`TradeIntent` is not an `OrderRequest`** — no take-profit field, and
  `stop_price` there means "this order's trigger". Mapping intent → orders is
  execution's job.

**Dependencies**
- **`python-binance`**, not the official Binance connector — built-in Testnet
  support, mature async/websocket managers, order helpers.
- **`pandas-ta` is NOT used and must not be reintroduced.** The 0.3.x line was
  pulled from PyPI; 0.4.x forces a heavyweight `numba`/LLVM dependency plus
  pinned NumPy/pandas — fragile for software that manages money. Indicators are
  small hand-written unit-tested functions in `indicators/`.
- `requirements.txt` is the single runtime dependency source; dev tools in
  `requirements-dev.txt`. **23 direct dependencies, in three categories:**

  | | Runtime | Dev | Rule |
  |---|---|---|---|
  | **Pinned `==`** | 8 | 7 | `src/` imports it, or a gate executes it |
  | **Deliberately floored** | 1 | 0 | `python-dotenv` — unimported but genuinely required, pulled in by `pydantic-settings` |
  | **Unused, pending deletion** | 5 | 2 | `httpx`, `SQLAlchemy`, `aiosqlite`, `fastapi`, `uvicorn`; `freezegun`, `respx` |

  Pinning the unused ones would assert a commitment the project has not made to
  dependencies it may drop. Pins encode a **verified** version, not a working
  one: `pydantic`, `pandas` and `numpy` carry line comments saying so, because
  the `Money` guard *is* pydantic validation and the float64 leak path *is*
  `numpy.float64` being a `float` subclass. Raising one of those is never
  routine hygiene. Transitive dependencies still float — see the open items.

**Style**
- `timezone.utc` — do **not** switch to the `datetime.UTC` alias (`UP017` is
  suppressed project-wide for this reason).
- Enums are `str, Enum`, not `StrEnum` (`UP042` suppressed deliberately:
  `StrEnum` changes `str(member)` from `"OrderSide.BUY"` to `"BUY"`, which would
  alter logs and persisted strings).
- No quoted annotations in new code (files carry `from __future__ import annotations`).
- New exception classes end in `Error`. `zip()` always takes `strict=`. Never
  use `l` as a variable name.
- **All files are LF**, pinned by `.gitattributes`. Write LF.
- `ruff format` is a gate (`make check`). It runs over `src tests scripts` — the
  same paths as `ruff check` — so a formatting failure surfaces in seconds,
  before pytest.
- `# fmt: off` / `# fmt: on` fences hand-laid data tables. It only works at
  **statement boundaries** — it does *not* protect a table inside a
  `@pytest.mark.parametrize` argument list. Define such tables at module level
  and reference them from `parametrize` (`_STOP_ROUNDING_CASES` is the worked
  example).
- **Fence only where layout is the sole carrier of a correspondence to an
  external contract.** Six fenced fixtures across five files:

  | File | Fixture | Contract it mirrors |
  |---|---|---|
  | `test_binance_client.py` | `KLINE_1`/`KLINE_2` | Binance REST positional kline array |
  | `test_exchange_mappers.py` | `KLINE_1`/`KLINE_2` | same |
  | `test_exchange_mappers.py` | `WS_KLINE_CLOSED`/`WS_KLINE_FORMING` | WS single-letter kline schema |
  | `test_websocket_client.py` | `_kline_event` | same |
  | `test_helpers.py` | paired rounding assertions | the two rounding directions, read side by side |
  | `test_risk_rules.py` | `_STOP_ROUNDING_CASES` | tick/percent case grid |

  Each keeps the raw wire shape deliberately: the mapper under test is what
  turns position into meaning, so a fixture that already knew the field names
  would test the helper with itself. Each carries a comment naming its columns
  in schema order.

  **Declined, and recorded as declined rather than missed:** `ORDER_LIMIT_NEW`,
  the `fields` tuple, `ERROR_SENTINEL`, and an aligned trailing comment on a
  `FakeSocket` argument. Their layout is convenient, not load-bearing. Spending
  the mechanism on those would blunt the signal that a fence means something.

**Config & safety**
- **Testnet is the default everywhere.** Live trading requires explicit
  confirmation. Every example defaults to Testnet.

---

## Quality gates — hard zero

```bash
python scripts/check.py     # THE GATE — all four steps, in this order
python scripts/check.py lint   # ruff check + ruff format --check
python scripts/check.py type   # mypy
python scripts/check.py test   # pytest
```

`scripts/check.py` **is** the gate; `make check` is a one-line delegation to it,
as are `make lint` / `type` / `test`. The definition lives in Python because
`make` is not installed on every development machine — a Makefile-native gate is
one that cannot be run where the work happens, and for five phases it never was.

The four steps, and what each reports when green:

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  81 files already formatted
mypy                                   Success: no issues found in 58 source files
pytest                                 514 passed, 3 skipped
                                       (517 passed with Testnet credentials present)
```

**The test count is not a function of the tree alone.** The three integration
tests are `skipif(not HAS_CREDENTIALS)`, so a machine with `.env` credentials
reports `517 passed` and one without reports `514 passed, 3 skipped`. Both are
green. Quote the count with its condition, never bare.

**What each gate covers** — one boundary, stated once, and it is now deliberate
everywhere:

| Gate | Scope | Files |
|---|---|---|
| `ruff check` / `ruff format --check` | `src tests scripts` | 81 |
| `mypy` | `files = ["src/trading_bot", "scripts"]` | 58 |
| `pytest` | `tests/` (`testpaths`) | — |

`tests/` sits outside mypy **by policy** (see below). `scripts/` was outside all
three until it was brought in — an accident of the path list rather than a
decision, and the one that mattered most, since `check_testnet.py` connects to
Binance with real credentials. Note mypy uses `files`, not `packages`: the two
keys are mutually exclusive and mypy errors if both are set.

**mypy and ruff must report ZERO.** This is a hard gate, not a baseline to diff
against. Any new finding is a regression.

Do **not** reach zero by adding `noqa` or `type: ignore`. Fix the code. If a
suppression is genuinely warranted, make it *self-removing* and justify it in a
comment. The worked example is now closed: `RiskManager.approve` carried
`# type: ignore[no-untyped-def]` on its unannotated `portfolio` until M3 typed
it, at which point `warn_unused_ignores` forced the deletion. **`type: ignore`
now appears nowhere in `src/`** — keep it that way.

Note `mypy` covers `files = ["src/trading_bot", "scripts"]`, so `tests/` is *not*
type-checked. A `# type: ignore` in a test is inert as far as the gate is
concerned; use one only to document a deliberate violation under test (passing a
`float` where `Money` is expected), never to silence a weakly-typed helper.

The 3 integration tests are read-only against Binance **Testnet**, never place an
order, and are gated by `tests/integration/credentials.py` (which reads through
`Secrets()`, so `.env` works — not just environment variables).

---

## Testing style

Unit tests are hermetic: no network, no real time, scripted fakes, injectable
seams — injected `sleep` for retry/backoff, injected `Clock` for the
time-dependent risk rules (daily-loss roll, cooldown expiry). `asyncio_mode=auto`.
Exact `Decimal` assertions in money code — no float tolerance, because a result
that is merely *close* is a bug and a tolerant test cannot detect the float leak
the domain exists to prevent.

---

## Git workflow

Commit at each verified milestone, never mid-milestone. Before committing, all
three gates must be green. Write the *why* in the commit body, not just the what.

I review via `git diff` — so keep mechanical changes (formatting, line endings,
renames) in **separate commits** from semantic ones. Never mix them.

**Docs rotation, at the end of every milestone:**

1. Append the milestone to `docs/PHASE_HISTORY.md` — decisions and *why*,
   including alternatives rejected. It is a build log written in the tense it was
   decided: never restate current state there, and never renumber past entries.
2. Update this file — "Current state", the baseline numbers in "Quality gates"
   taken from a **fresh `make check`** (never a remembered count), and any new
   locked decision.
3. Rewrite `docs/NEXT_MILESTONE.md` for the next milestone, carrying forward any
   open items that are still open. This is the single home for live open items.

There is no separate workflow document; these three steps are the procedure, and
they live here because this is the only file loaded into every session. Docs that
must be remembered to be read are how the four drifts found in the M3 audit got
in.

**The Claude.ai Project knowledge is a fourth drift surface, and nothing audits
it.** It is outside the repo, so no gate, grep or review touches it —
`MILESTONE_WORKFLOW.md` was referenced there for months while existing nowhere in
the tree. **This file is the authority.** Project knowledge should *point at* it,
not restate it; anything restated there will eventually contradict the code, and
the contradiction will be invisible from inside the repo.

---

## Current state

Phases 1–4 complete. Phase 5 M1 (position sizing), M2 (protective exit rules) and
M3 (risk manager + `Portfolio`) complete. Tooling cleanup complete.

The decision path is complete **as a library**: `RiskManager.evaluate` turns a
signal into an approved, sized, protected `TradeIntent`. It is **not wired** —
`main.py` registers no `on_signal` handler, so `python -m trading_bot run` still
only logs signals, and nothing constructs a `Portfolio` or primes a
`PairContext`. Building that composition root and making the intent stream
observable is M4; placing an order is M5. See `docs/NEXT_MILESTONE.md`.
