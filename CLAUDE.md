# Binance Spot Trading Bot

Production-grade automated Binance Spot trading bot in Python. **Treat this as
software that will eventually manage real money.** Every design decision
prioritises correctness, safety and robustness over speed of development.

Detailed build history: `docs/PHASE_HISTORY.md`
Current task: `docs/NEXT_MILESTONE.md`
Protective-order contract: `docs/QC_PROTECTIVE_ORDERS.md`

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

**The log sink is a third edge, and it is safe.** `JsonFormatter` serialises via
`json.dumps(payload, default=str)`, so a `Decimal` reaches a JSON log line as a
**string** — `"50.000"`, exact, never a JSON number and never a float. A bare
`json.dumps(Decimal(...))` would raise `TypeError`; `default=str` is what catches
it. Any downstream consumer must therefore parse those fields back as `Decimal`,
never as a number.

The sharp edge: `default=str` is a **catch-all**, not a money-aware hook. Any
object it does not recognise lands as its `repr` rather than failing, so passing
a non-plain value through `extra=` produces a plausible-looking log line and no
error. That is the same convention-not-enforcement shape as the `metadata` rule
below — the type does not stop you, only the discipline does.

**Structured fields reach both sinks, and that took work.** `PlainFormatter`
appends `extra=` fields as logfmt (`key=value`, quoted when the value contains
whitespace, `=` or a quote) using `str()`, matching the JSON path's
`default=str` — so a `Decimal` renders `50.000` identically in text and JSON.
Before it, text mode **silently dropped** every structured field while JSON kept
them: same call site, lossy output, no error. There are **three** plain sinks,
not two — `RichHandler`, the `StreamHandler` used when `rich` is missing, and
the file handler.

**The `Decimal` agreement does not extend to enums — pass `.value`.** The two
sinks render a `str, Enum` member *differently*, and neither one errors:
`json.dumps` sees a `str` subclass and emits the underlying value (`"BUY"`),
while `PlainFormatter` calls `str()` and gets `"SignalAction.BUY"`. Same call
site, same field, two answers — the exact asymmetry the `PlainFormatter` work
above closed for the general case, reopened by the `str, Enum` decision (`UP042`)
that keeps `str(member)` qualified. So `extra=` takes `signal.action.value`,
never `signal.action`. Verified in
`tests/unit/test_modes.py::TestLogSchema::test_enums_cross_as_values_so_both_sinks_agree`,
which asserts against both formatters rather than trusting either.

The same reasoning applies to a `datetime`: `default=str` would carry it, but
`extra=` passes an explicit `.isoformat()` rather than leaning on the catch-all.

**The rule, stated positively rather than as a list of patched cases: only
`str`, `int`, `float`, `bool`, `None` and `Decimal` may cross `extra=`
unconverted.** Everything else is converted at the call site — an enum by
`.value`, a `datetime` by `.isoformat()`, an exception by `type(exc).__name__`
and `str(exc)`. The whitelist is the point: `default=str` is a catch-all, so an
unlisted type produces a plausible line rather than an error, and the *only*
signal that something is wrong is the two sinks quietly disagreeing. Note this
is the same admissible set as `Signal.metadata` minus the reason they differ —
`metadata` forbids `Decimal` because it is persisted, `extra=` requires it
because it is money.

**`extra=` field names are validated — enforced, not convention.**
`Logger.makeRecord` raises at the *call site*:
`KeyError: "Attempt to overwrite 'name' in LogRecord"`. The reserved set is every
`LogRecord` attribute plus `message` and `asctime`, and it contains plausible
field names — `module`, `name`, `process`, `thread`, `msg`, `args`, `levelname`.
This is one of the few things in this area the runtime enforces rather than the
discipline. Note `message`/`asctime` are *not* on a fresh record:
`logging.Formatter.format` assigns them while rendering, so any code diffing a
post-format record against a fresh one must add them back or it will report the
log message as a caller-supplied field.

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
  engine/        live_engine · modes (composition root)
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
- **`metadata` values are enforced plain `int`/`float`/`str`/`bool`/`None`** by
  `_reject_exotic_metadata`, matched on **exact type** rather than `isinstance`.
  It gets persisted and logged, and a NumPy scalar would serialise to a repr
  like `np.float64(1.5)` rather than failing. Note this is the *opposite*
  discrimination from `_reject_float`: there the whole `float` family is
  rejected so `isinstance` is right; here `float` is allowed and
  `numpy.float64` is not, and no `isinstance` test separates them. Exact-type
  matching also rejects every NumPy scalar without `core/` naming NumPy.

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
- **Client-side exit evaluation is fed the closed candle's `close`**, never its
  high/low — triggering on a price the bar has already left is optimistic in
  backtest and dishonest live. `check_exit` / `advance_trailing_stop` live on the
  manager; *driving* them from the candle subscription is execution's job, because
  an exit check is per-candle-per-position and `on_signal` skips quiet bars.

  **Q-C re-scoped this rule; it did not repeal it.** It governs *client-side*
  evaluation, where the bot chooses when to act. A protective order resting at the
  exchange triggers **intrabar**, and that fill is not a client decision — so the
  close-only rule does not describe it and must not be applied to it. The
  consequence is recorded rather than hidden: `backtesting/` must model intrabar
  triggering to keep backtest and live on one code path, and that is the largest
  cost Q-C carries. See `docs/QC_PROTECTIVE_ORDERS.md`.
- **`TradeIntent` is not an `OrderRequest`** — no take-profit field, and
  `stop_price` there means "this order's trigger". Mapping intent → orders is
  execution's job.

**Protective orders (Q-C — full reasoning in `docs/QC_PROTECTIVE_ORDERS.md`)**
- **Entry and protection are placed in one order-list call.** No client-side /
  exchange split. Protection is *accepted* atomically with the entry; acceptance
  is **not** activation, and the fill path is unmeasured.
- **Leg types are fixed:** working `LIMIT`+`FOK`, below `STOP_LOSS`, above
  `TAKE_PROFIT` — all three stop-market or marketable, none post-only.
  `LIMIT_MAKER` was rejected for an activation-rejection mode whose blast radius
  on the sibling stop is unmeasured.
- **The placement shape branches four ways and the branch is irreducible.**
  `PERCENT_PRICE_BY_SIDE` refuses a whole list at submission, so a "never fills"
  dummy leg to force one shape is impossible.
- **Take-profit without a stop is refused at config load, and that refusal is a
  JUDGEMENT about payoff shape, not a measurement.** The code accepts it today and
  so would the exchange. Both-disabled stays reachable with a boot warning.
- **Reconciliation is keyed off what was REQUESTED, never off what is absent**,
  and compares only fields that round-trip. `contingencyType` never says
  `"OTOCO"`, so shape comes from leg count or our own IDs.
- **`translate_binance_error` must match message text, not code.** `-2010` and
  `-2011` each carry several meanings, and `-2010 'Duplicate order sent.'` is a
  *success* signal under deterministic client order IDs.
- **`assessment.decision.rule is None` means "the limits passed", NOT
  "approved".** `RiskAssessment` has no `rule` field at all; the rule is reached
  through `decision`, and is doubly optional — `decision` may be `None`, and
  even when present `rule` may be. **Four refusal paths carry a decision with
  `approved=True` and `rule=None`**: the ATR bridge, an unplaceable stop, the
  sizer, and affordability, all of which refuse *after* the limits passed.
  Branching on rule presence reads all four as approvals. **`RiskAssessment.
  approved` is the only authoritative field** — its validator binds it to
  `intent is not None`, so the two cannot drift.
- **`evaluate` reports where it stopped; nothing infers it.**
  `RiskAssessment.stage` is a `RefusalStage` (in `core/enums.py`, beside
  `RiskRule`), set at the site that refuses. **Required but nullable** — no
  default, so every construction site says something and an approval says `None`
  deliberately. The validator mirrors `RiskDecision`'s, on the **opposite axis**:
  `approved != (stage is None)` — present on a refusal, like `rule`, and
  therefore inverted against `intent` directly above it. Adding a refusal path
  cannot forget a stage, because the parameter is required.
- **The stage vocabulary is deliberately coarser than `RiskRule`.**
  `LIMIT_REFUSED` covers all five limit rules: the stage says *where* evaluation
  stopped, `decision.rule` says *which* limit fired, and the decision is
  populated at that site. Splitting it would duplicate `RiskRule` into a second
  hand-synced vocabulary. `NO_MARK_PRICE` is separate because it refuses
  *before* the limits are consulted — an inability to compute equity, not a
  verdict. **There is no `UNCLASSIFIED`**: every member is reachable, and an
  unreachable one invites defensive branching and becomes a lazy default for the
  next refusal added. The logger's `stage is None` branch is mypy narrowing plus
  a health check, logged at `ERROR` against a fixed literal — never raised or
  asserted, because `IntentLogger` runs inside the handler that must not raise.

**Dependencies**
- **`python-binance`**, not the official Binance connector — built-in Testnet
  support, mature async/websocket managers, order helpers.
- **`pandas-ta` is NOT used and must not be reintroduced.** The 0.3.x line was
  pulled from PyPI; 0.4.x forces a heavyweight `numba`/LLVM dependency plus
  pinned NumPy/pandas — fragile for software that manages money. Indicators are
  small hand-written unit-tested functions in `indicators/`.
- `requirements.txt` is the single runtime dependency source; dev tools in
  `requirements-dev.txt`. **16 direct dependencies, every one pinned `==`**, in
  three labelled categories:

  | Category | Runtime | Dev |
  |---|---|---|
  | Pinned — imported by `src/` or `scripts/` | 8 | 7 |
  | Pinned — not imported, but executed on a gated path | 1 (`python-dotenv`) | 1 (`freezegun`) |
  | Floored, deliberately | 0 | 0 |

  The middle category is load-bearing and was got wrong once: **"nothing imports
  it" is not sufficient grounds for deletion.** `python-dotenv` is executed
  whenever `Secrets()` is built; `freezegun` is used as a `@freeze_time`
  decorator with no bare package import.

- **For a test-only dependency, "used" has three surfaces** — an import
  statement, a **decorator**, and a **fixture name in a test signature**. The
  third takes no import and no decorator, so grepping the package name misses it
  entirely. Check all three before deleting.

- Pins encode a **verified** version, not a working one: `pydantic`, `pandas` and
  `numpy` carry line comments saying so, because the `Money` guard *is* pydantic
  validation and the float64 leak path *is* `numpy.float64` being a `float`
  subclass. Raising one of those is never routine hygiene. Transitive
  dependencies still float — see the open items.

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

**Never pipe `check.py`.** A shell pipeline's exit status is the *last* stage's
unless `set -o pipefail` is in force, so `python scripts/check.py | tail` reports
`tail`'s success no matter what the gate did. This has masked a non-zero exit
**twice** in this project: once hiding a `SIM108` finding in `check.py` itself,
once hiding a failing test. Both times the truncated output also discarded the
diagnostic that named the cause. Run it bare, let it print its own summary, and
read its own exit code.

The four steps, and what each reports when green:

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  83 files already formatted
mypy                                   Success: no issues found in 58 source files
pytest                                 647 passed, 3 skipped
                                       (650 passed with Testnet credentials present)
```

**The gate's output is not a function of the tree alone — this is a property,
not a footnote.** It varies by **credentials** and by **network state**.

*Credentials.* The three integration tests are `skipif(not HAS_CREDENTIALS)`, so
the *same commit* reports:

- `650 passed` on a machine with Binance Testnet credentials in `.env`
- `647 passed, 3 skipped` on a machine without them

**Both are honestly green.** A fresh clone, a new contributor, or the first CI
runner will see 647 and must not read it as a regression against a documented
650. Quote the count with its condition, never bare.

Only the `650` is measured here; `647` is `650` minus the three `skipif`-gated
integration tests. Say which is which rather than presenting both as observed.

*Network.* The integration tests make live calls to Binance Testnet and two of
them wait on a real 1-minute bar, so they can fail for reasons that have nothing
to do with the tree. **One such flake was found and fixed:**
`test_testnet_provider_seeds_history_and_extends_it_live` asserted the first live
candle is always a *new* bar, but when the REST seed's last bar is the same bar
the stream then closes, `_append` replaces it in place instead — so the frame
grows by 0, not 1. The production behaviour was correct and the assertion was
wrong; it now asserts the invariant common to both paths. See
`docs/PHASE_HISTORY.md`.

It went unidentified for several sessions because the run that first hit it was
piped through `tail`, which discarded pytest's summary, and was re-run before the
output was read. The unit suite is deterministic at 647, so **treat a lone
failure in a full run as suspect-integration, and read the output before
re-running.** `addopts` carries `-ra`, so the summary is always printed — it only
has to be allowed to reach the terminal.

**Count coupling — a known drift trigger with nothing enforcing it.** Each
documented number appears in **both** `CLAUDE.md` and `README.md`, updated by
hand. Which ones move depends on **what kind of file changed**, not on how big
the commit is:

| Change | `ruff format` | `mypy` | `pytest` |
|---|---|---|---|
| `tests/` file **added** | moves | **no** — `tests/` is outside mypy by policy | moves if it adds test functions |
| `src/` or `scripts/` file **added** | moves | moves | no |
| `src/` file **modified** | no | no | no |

In practice a `src/` file never arrives alone here — it arrives with its tests —
so a typical `src/` commit moves all three. Two counter-examples worth knowing,
both **historical illustrations whose figures are deliberately not updated**:
**D3**, one `src/` file *modified*, so `ruff format` held at 82 and `mypy` at 58
while `pytest` moved 554 → 569; and **M4a**, which filled the pre-existing
`engine/modes.py` stub — already counted by both gates — so `mypy` held at 58
and `ruff format` moved only for the one new test file.

**Grep for the NUMBER, not for the lines you remember.** `ruff format` and
`mypy` each appear in **three** places, not two: the fenced gate output above,
the gate-scope table below, and `README.md`. A pre-commit pass that checks the
two obvious ones leaves the scope table stale — the exact drift this section
exists to prevent. Searching for the digits also surfaces the historical
examples in the paragraph above; those are prose about a past commit and must be
left alone, which is easy to tell apart and impossible to notice if the grep
never ran.

**What each gate covers** — one boundary, stated once, and it is now deliberate
everywhere:

| Gate | Scope | Files |
|---|---|---|
| `ruff check` / `ruff format --check` | `src tests scripts` | 83 |
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

**Select log records by logger name, never by position.** `caplog.at_level`
lowers the capture *handler*'s level globally, not just the named logger's, so
any collaborator that logs on its own lands in the same buffer whenever an
earlier test has left the root level low. `assert len(caplog.records) == 1`
therefore passes for a file run alone and fails in the full suite — it did, for
two tests, because `RiskManager.evaluate` emits its own `INFO` line. Filter with
`[r for r in caplog.records if r.name == ...]`.

### Mutation-testing an anti-rot test

**"The test passes" and "the test bites" are different claims, and only the
second is worth anything for a test whose job is to catch drift.** Where a test
exists because two places must stay in agreement — the stage ladder against
`RiskManager.evaluate` is the worked example — prove it by breaking the code and
watching the *intended* test fail:

1. Apply one mutation. Run the suite.
2. Confirm the test that fails is the one meant to, **and that it reports the
   wrong value** — a wrong stage, not an `AttributeError` or a collection error.
   A crash means the mutation broke something else on the way and the assertion
   was never reached; that is not coverage.
3. **Restore in a `finally`, from a `shutil.copy2` byte copy, and verify by
   md5.**

Step 3 is written that emphatically because both halves failed here. A sweep
script that restored *after* printing crashed mid-run on a console encoding
error and **left `src/` mutated on disk**; it was caught only by the next
command's checksum. Its replacement restored via `read_text`/`write_text`, which
round-trips newlines and produced a byte mismatch against this LF-pinned tree —
content-identical, checksum-different, and indistinguishable from a real
corruption until diffed. Never restore by re-reading and re-writing.

Coverage found this way comes in three kinds, and they are not equivalent: an
assertion that catches the mutation; an *implication* that makes an ordinary
case double as the check (where one condition strictly implies another, the
normal test already pins the order); and enforcement by Python itself (swapping
a null-guard that also binds the name yields `NameError`). Only the first is
something a future edit can delete by accident.

### A discovery loop's budget must EXCEED the unknown it is discovering

An attempt cap on a schema-derivation walk is not a safety margin — it is a
guess about the answer. A walk that reveals **one field per round trip** needs a
budget larger than the field count, and the field count is precisely what the
walk exists to discover, so a cap chosen in advance can silently become the
finding instead of the endpoint's behaviour.

Q-C paid for this. The OTO schema walk was capped at 8 and needed 10: it stopped
having learned eight parameter names and **nothing about whether the shape is
accepted**, which was the actual question. The cap had to be raised and the walk
resumed from the derived set — one extra round trip, and a report whose headline
was "UNRESOLVED at the cap" rather than an answer.

Two rules follow. **Stopping at the cap is right; exceeding it silently is not** —
a walk that quietly runs long has stopped being a measurement with a stated cost.
And **report the cap as a possible cause** whenever a walk terminates on it, so
"the budget ran out" is never mistaken for "the endpoint refused".

**There is a fourth answer, and it is "do not write the test":
order-independence.** Before pinning an order, check that the two conditions can
both hold. `size_not_tradeable` and `unaffordable` look like an obvious adjacent
pair, and are not: `not is_tradeable` implies `quantity == 0` implies
`cost == 0`, so for any non-negative balance the two guards are **mutually
exclusive** and swapping them is unobservable rather than merely hard to
observe. A test that bit would need a state the exchange cannot produce, and
would then fail on a harmless refactor while pinning nothing. Recorded in
`docs/PHASE_HISTORY.md` (M4b, findings iii/iv) so it is not re-derived and
written next time.

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
M3 (risk manager + `Portfolio`) complete, followed by a **pre-M4 hardening pass**
(see `docs/PHASE_HISTORY.md`) that moved the quality gate into
`scripts/check.py`, pinned every direct dependency, deleted six unused ones, made
`extra=` fields reach the text log sink, and closed the last three
convention-only guards — `Position` assignment, config immutability, and
`Signal.metadata`.

**M4a is complete: the decision path is wired.** `engine/modes.py` — a
docstring-only stub since Phase 1 — is now the composition root.
`live_system(settings)` is an `@asynccontextmanager` that builds the REST
client, primes a `PairContext` per distinct symbol, seeds a `Portfolio` from
`get_balances()`, then the provider, engine, `RiskManager` and `IntentLogger`,
registers **one** signal handler, and tears the whole thing down in three nested
scopes. `main.py` drives it with `async with`; that is the only production call
site. Four conditions refuse the boot before any socket exists — a duplicate
symbol, an unprimeable symbol, a missing quote asset, and a mode with no
composition root — plus an empty enabled-pair set.

**Nothing places an order.** `IntentLogger` is the terminal collaborator and it
logs: three events (`risk_refused`, `intent_dispatched`, `collaborator_failed`)
with a fixed field set each, absent fields absent rather than null. It is
deliberately not called `Executor` and not in `execution/` — claiming that stub
would make the stub inventory lie.

**M4b is complete: the stage moved into the domain.** `RefusalStage` now lives
in `core/enums.py` beside `RiskRule` — the direction was forced, since `engine/`
imports `risk/` and so `risk/` cannot import `engine/`. `RiskManager.evaluate`
sets `RiskAssessment.stage` at each of the twelve construction sites, and
`modes._refusal_stage` — which re-derived `evaluate`'s control flow in a second
file to label the log line — is deleted. `UNCLASSIFIED` left with it.
`RiskAssessment` itself did **not** move; that collided with the port question,
which Q-C has now decided (see below).

Done in three commits: a byte-identical mechanical move, then the field and its
invariant, then the deletion. The redundant ladder was kept for exactly one
commit so its answer could be compared against the new field across all ten
paths before being removed. The new ordering test is mutation-proved.

**Two sizing bugs were fixed before Q-C's design**, both independent of where
protection rests. `calculate_position_size` measured `min_notional` at the entry
price only, while Binance evaluates `stopPrice * quantity` for an algo order too —
so a stop resting below the entry carries the smaller notional and is the leg the
exchange rejects. Observed live, not deduced: a Testnet probe took `-1013 Filter
failure: NOTIONAL` on exactly that. No signature change was needed; `stop_price`
was already a parameter and the check simply ignored it. Separately,
`MARKET_LOT_SIZE` is now modelled — optional per symbol, with `effective_step_size`
/ `effective_min_qty` taking the stricter of it and `LOT_SIZE`, because whether it
binds a *triggered* stop is stated by neither the library nor `exchangeInfo`.

**Q-C is complete, and it is a written contract rather than code.**
`docs/QC_PROTECTIVE_ORDERS.md` decides where the protective levels live: entry
and protection go out in **one order-list call**, there is no client-side /
exchange split, and `check_exit` is demoted from actor to divergence monitor. It
was run as **two independent proposals** — one written here from the tree and the
probe record, one written in chat — then compared, with four disagreements pinned
and adjudicated. The schemas, forbidden fields, error-code overloads and
read-back asymmetries it relies on were measured across ten Testnet probe steps,
and every claim in the note is marked MEASURED, DOCUMENTED or UNMEASURED. Q-D was
folded in as a decision: the port widens and `RiskAssessment` moves with it.

**Still nothing places an order.** `IntentLogger` remains the terminal
collaborator; `execution/` is still a pair of stubs.

Next: **M5**, order dispatch — it implements Q-C's contract and is where the bot
first places an order. **Q-A** stays unscheduled: its thresholds need soak data
and nothing has dispatched an order yet, so the `collaborator_failed` lines it
would be calibrated from do not exist. **Q-B**, escalation policy, is settled at
the start of M5 because Q-C leans on it in three places. See
`docs/NEXT_MILESTONE.md`.
