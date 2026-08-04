# Phase History

What was built, and the reasoning that is not obvious from the code. Read this
when you need to know *why* something is shaped the way it is. `CLAUDE.md` holds
the rules; this holds the record.

---

## Phase 1 — Scaffolding

`config/` (settings + pydantic config models), `core/` (models, enums,
interfaces/ports, exceptions), `utils/` (logger, helpers), the strategy registry,
and test scaffolding.

`core/interfaces.py` defines the abstract ports every outer layer implements.
`Position` was scaffolded with `stop_loss`, `take_profit`, `trailing_stop`,
`highest_price` and `lowest_price` fields — the trailing-stop high-water mark
therefore already has a home, which is why the risk rules can stay pure.

---

## Phase 2 — Binance REST connectivity

- `exchange/models.py` — pure mappers plus `translate_binance_error`, which
  converts Binance error codes into the project's exception hierarchy.
- `exchange/base.py` — `BaseExchangeClient`: tenacity retry + error translation,
  **injectable sleep** (so retry logic is testable without real delay), and a
  symbol-info cache.
- `exchange/binance_client.py` — `BinanceClient` over `AsyncClient`, with
  `enforce_filters` and an async `create(settings)` factory.
- `scripts/check_testnet.py` — connectivity smoke check. `scripts/download_data.py`
  landed alongside it as the historical-kline fetcher the backtesting phase will
  use; it is not exercised by any phase built so far.

`_enforce` **raises** `OrderError` on `min_qty` / `min_notional` violations. That
raising behaviour is load-bearing for the risk layer's design (see Phase 5 M1).

---

## Phase 3 — Market data

**M1–M2** — `exchange/websocket_client.py` (`BinanceMarketDataStream`): a 24/7
closed-candle feed with a Protocol-based testability seam, capped-exponential
backoff with equal jitter, and per-handler exception isolation so one bad
subscriber cannot kill the stream.

**M3** — `data/market_data.py` (`BufferedMarketDataProvider`). Seeds
`DataConfig.history_limit` candles per pair over REST, then appends live closed
candles into a `deque(maxlen=buffer_size)`. A single append gate enforces
*closed candles only, strictly increasing `open_time`*. It **appends before it
notifies**, so a candle handed to a subscriber is already `buffer[-1]`.
`last_candle()` returns full-precision `Decimal`. This is the one deliberate
`Decimal`→`float` boundary in the system.

**M4** — `engine/live_engine.py` (`TradingEngine`): evaluates on bar close, one
strategy instance per pair, a readiness gate, and three isolation layers —
strategy exception contained → consecutive-failure quarantine at
`engine.max_strategy_errors` (any success resets the counter) → signal-handler
exceptions isolated. `on_signal()` is the seam where risk and execution attach.
`main.py` wires `python -m trading_bot run`.

---

## Phase 4 — Indicators and real strategies

**M1** — `indicators/indicators.py`: hand-written SMA, EMA, RSI, MACD, Bollinger,
ATR, plus public `true_range`. Pure functions, Series in → Series out. Warmup is
expressed as leading `NaN`, per function — never zero, never back-filled.

**M2** — `SmaCrossoverStrategy` and `RsiStrategy` became real. Edge-triggered,
stateless, `BUY`/`CLOSE` only, with `warmup_period` derived from the indicator
NaN contract (`slow+1`, `period+2`). `python -m trading_bot run` now emits real
signals on Testnet instead of quarantining every pair.

Port change: `generate_signal(symbol, candles, *, last_candle: Candle)` — the
strategy copies an exact `Decimal` instead of rebuilding one from the float
frame, and stamps `Signal.timestamp` from `candle.close_time`.

**M2 follow-ups** — the `Money` type began enforcing `Decimal` on all money
fields (33 of them at the time; floats and `numpy.float64` raise rather than
coerce). The count has grown with every phase since — it is recorded here as a
fact about *this* milestone, not a running total, and is deliberately not
restated anywhere in this document.
`SignalAction.HOLD` was removed; `StrategyConfigError` was added to name the
accepted parameters when `config.yaml` has a typo.

---

## Phase 5 M1 — Position sizing

`risk/position_sizing.py`: three pure functions plus an orchestrator.

```python
def size_by_fixed_fraction(*, equity, price, fraction) -> Decimal
def size_by_fixed_amount(*, price, amount) -> Decimal
def size_by_risk_per_trade(*, equity, entry_price, stop_price, risk_fraction) -> Decimal

def calculate_position_size(*, symbol_info, equity, price, sizing, limits,
                            stop_price=None) -> SizingDecision
```

Pipeline: **dispatch → cap at `max_position_size_percent` → round DOWN to
`step_size` → verify `min_qty` and `min_notional`.** The order matters — each
step can only reduce the previous one, which is what lets `SizingDecision` assert
`quantity <= requested_quantity`.

Decisions and their reasoning:

- **`float`→`Decimal` at config load, via pydantic.** Pydantic converts using the
  value's shortest repr, so YAML's `0.02` becomes `Decimal("0.02")`, not the
  binary expansion `Decimal(0.02)` gives. Rejected alternatives: converting at
  each use site (DRY violation, easy to forget) and a parallel "risk parameters"
  value object (permanent sync risk with the config model).
- **Rounding down, applied last.** Rounding up can overspend free balance.
  Applied after the cap so neither the configured size nor the cap can be
  exceeded by the rounding itself.
- **Filters applied in sizing.** `_enforce` raises, and "too small to trade" is
  routine on a small account — routing it through an exception would mean
  exception-as-control-flow on every signal. A raw untradeable quantity is also a
  lie in the domain: logs, notifications and the paper simulator would all
  display a number that cannot exist.
- **`SizingDecision` instead of `Decimal(0)` / `None` / raise.** A bare `None`
  loses the reason and forces the caller to re-derive it; `Decimal(0)` is
  silently carried forward by arithmetic. The wrapper makes zero safe because a
  caller cannot reach `.quantity` without seeing `.reason`. Validators enforce
  `quantity >= 0`, non-empty `reason`, and `quantity <= requested_quantity` —
  making "sizing never rounds up" a property of the type.
- **`strength` is unused, structurally.** The pure sizing functions never receive
  a `Signal`, so nothing can multiply a position size by it.
- **`equity` = total portfolio value in quote currency**, not free balance —
  otherwise position sizes shrink as capital deploys, which is not what "2% per
  trade" means. The caller must separately confirm free balance covers the order.

49 tests in `tests/unit/test_position_sizing.py`, exact `Decimal` assertions.

---

## Tooling cleanup milestone

The project had carried a "frozen baseline" of 17 mypy errors and 31 ruff
findings, verified by diffing finding *lists* rather than counts. That was
retired.

- **10 of the 17 mypy errors were false positives** — the pydantic mypy plugin
  was not enabled. Adding `plugins = ["pydantic.mypy"]` cleared all of them.
- **22 ruff findings were project-wide style decisions** (`UP017` `timezone.utc`,
  `UP042` `str, Enum`) and moved into `ignore` with their rationale written
  alongside. `N818` on `RiskLimitExceeded` got a *line-level* `noqa` instead of a
  global ignore, so the rule stays live for future exception classes.
- **The rest were genuine defects**, all small: redundant quoted annotations in
  `registry.py` (the file already had `from __future__ import annotations`), an
  `E402` where an import had drifted below a helper, a dead `noqa`, an unsorted
  `__all__`, `asyncio.TimeoutError`, and four missing annotations.

**Integration credential gate fixed.** The gate read `os.environ` directly, but
credentials live in `.env`, which pydantic-settings loads into `Secrets` at call
time and never exports to the environment. Three integration tests had therefore
been silently skipping since Phase 2 while reporting a specific, wrong reason.
`tests/integration/credentials.py` now asks `Secrets()`, and checks key *and*
secret as a pair. All three tests pass against the real Testnet.

**Line endings pinned.** The tree was a mix of CRLF and LF, which meant patches
authored on Linux failed byte-verification on Windows even when they applied
correctly. `.gitattributes` (`* text=auto eol=lf`) plus a one-time normalisation
of 29 files retired the old "preserve each file's existing line endings" rule.

Result: **373 passed · mypy 0 · ruff 0.**

---

## Phase 5 M2 — Protective exit rules

`risk/rules.py`: pure functions that compute a position's protective levels and
decide when it should exit. Also the six `StopLossConfig` / `TakeProfitConfig` /
`TrailingStopConfig` percent-and-multiplier fields converted `float`→`Decimal`
(the milestone that first multiplies them by money), a directional `round_to_tick`
helper, and a `RiskConfig` load-time coherence validator.

```python
def stop_loss_level(*, side, entry_price, config, tick_size, atr_value=None) -> Decimal | None
def take_profit_level(*, side, entry_price, config, tick_size, stop_distance=None) -> Decimal | None
def compute_protective_levels(*, symbol, side, entry_price, stop_loss, take_profit,
                              tick_size, atr_value=None) -> ProtectiveLevels
def update_trailing_stop(*, side, entry_price, price, high_water, existing_stop,
                         config, tick_size) -> TrailingStopUpdate
def should_exit(*, position, price) -> ExitDecision | None
```

Decisions and their reasoning:

- **A stop rounds toward its reference; a take-profit rounds toward entry.**
  `round_price`'s unconditional `ROUND_DOWN` is correct for at most one side of a
  level — a long stop rounded *down* (away from entry) widens the realised stop
  past what `risk_per_trade` sizing divided by, silently breaching the risk
  budget. So every level rounds so its realised distance can only *shrink*: the
  initial stop toward entry, the trailing stop toward the high-water mark, the
  take-profit toward entry (reward never overstated). One helper, `_round_toward`,
  over a new `round_to_tick(rounding=...)`; `round_price` is left untouched
  because order dispatch relies on its `ROUND_DOWN`. Modes are
  `ROUND_CEILING` / `ROUND_FLOOR` (prices are strictly positive). *Rejected:*
  rounding the trailing stop *away* from price — it lets realised give-back exceed
  the configured `trail_percent`, the mirror of the risk-budget breach, so it
  folds under the same "toward the reference" rule instead.

- **`_atr_to_decimal` is the second `float`→`Decimal` boundary** (the first is
  config load). `atr()` is float64; a stop price is `Money`, which rejects
  `float` / `numpy.float64`. The conversion is `Decimal(str(float(x)))` — the
  shortest round-tripping repr, the same principle config load uses, not the
  binary expansion `Decimal(x)` injects. It stays **private to `rules.py`**: a
  public `float`→`Decimal` converter is a Money-guard-defeating tool, and the ATR
  value is the one runtime statistic that legitimately needs one. The residual
  float error is orders of magnitude below the tick, which the directional
  rounding then dominates — a precision funnel, not a leak.

- **`rules.py` takes a scalar ATR value, not a DataFrame** — keeps pandas out of
  the risk layer and every test a plain-`Decimal` call. Intended M3 bridge: the
  manager holds a `MarketDataProvider` reference and passes `atr(...).iloc[-1]`.
  *Rejected:* ATR in `Signal.metadata` (the strategy would own a *risk*-config
  period, and metadata is deliberately non-load-bearing) and a changed port
  (over-engineering for one indicator).

- **Order is stop → realised distance → size (M1) → take-profit**, enforced by
  the types: `take_profit_level` requires `stop_distance` for an `rr` target, so
  it cannot be computed before the stop.

- **The trailing stop is the only stateful rule and is kept pure.** Its
  high-water mark lives on `Position` (`highest_price` / `lowest_price`);
  `update_trailing_stop` returns the new mark and level for the caller to store.
  Monotonicity — `max` for a long, `min` for a short — makes "never moves against
  the position" a property of the code, not a comment.

- **A sub-tick protective distance is representable, not an error.** When the
  configured distance is below one tick, rounding toward the reference collapses
  the level onto it; `_protective_level` returns `None` ("no placeable level this
  bar") and the reason lands in `ProtectiveLevels.basis`. An ATR distance can go
  sub-tick simply because volatility went quiet — transient and self-healing —
  and this path runs on *every* signal. This *overruled* an initial design that
  raised. Genuinely incoherent *inputs* still raise:
  non-positive price, non-finite ATR, and negative ATR (impossible by
  construction). A zero ATR is the extreme of the quiet-market state and flows to
  a `None` stop.

  > **Corrected in M3.** As written at the time, this bullet justified itself by
  > saying a raise "would reach the engine's consecutive-failure quarantine and
  > disable a healthy pair". That was wrong, and wrong in the direction that
  > matters: quarantine counts **strategy** failures only —
  > `TradingEngine._record_failure` is reached from `_evaluate` and nowhere else
  > — while these rules run under a *signal handler*, whose exceptions `_emit`
  > catches, logs and steps over. A raise here would therefore not disable the
  > pair loudly; it would log a traceback every bar while the bot went on looking
  > healthy. The decision stands, but on a **stronger** premise than it was made
  > on: the alternative was never "loud shutdown", it was "silent bleeding". The
  > Phase 3 M4 entry above already described the three isolation layers
  > correctly; only this bullet drew the wrong inference from them.

- **Frozen, `Money`-typed result objects** — `ProtectiveLevels`,
  `TrailingStopUpdate`, `ExitDecision` — mirror `SizingDecision`: "no level built
  from a float" is structural, and both "disabled" and "no placeable level" stay
  representable. The primitive `stop_loss_level` / `take_profit_level` return a
  bare `Decimal | None`; the reason is composed once, in the orchestrator.

- **`should_exit` is the pure predicate; acting on it is M3.** It returns which
  rule fired (an `ExitReason`, richer than a bool) — an operator must know whether
  a stop, a trailing stop or a target closed the position. A stop beats the
  take-profit when a single price triggers both, reported at the stop level (the
  worst fill). It evaluates a *single* price, so M3 decides deliberately whether
  to feed the bar's close or its high/low.

- **`RiskConfig` gains a load-time coherence validator.** An `rr` take-profit or
  `risk_per_trade` sizing with `stop_loss.enabled = False` multiplies a stop
  distance a disabled stop never produces; the validator rejects both at startup
  instead of on the first signal hours later. The runtime raises in `rules` /
  `position_sizing` stay as defence in depth — a caller can bypass config.

75 tests in `tests/unit/test_risk_rules.py` (plus config-coherence and
`round_to_tick` tests), exact `Decimal` assertions.

---

## Phase 5 M3 — Risk manager and portfolio

`core/portfolio.py` (`Portfolio`), `core/models.py` (`RiskDecision`),
`core/enums.py` (`RiskRule`), and `risk/manager.py` — the concrete `RiskManager`
that composes M1 and M2 into the live decision path. Also
`max_daily_loss_percent` converted `float`→`Decimal` (the milestone that first
multiplies it by money).

```python
class RiskManager:
    def approve(self, signal, *, portfolio) -> RiskDecision          # port
    def size_position(self, signal, *, equity, price,
                      stop_price=None) -> SizingDecision             # port
    def evaluate(self, signal, *, portfolio) -> RiskAssessment       # the composed path
    def check_exit(self, position, candle) -> ExitDecision | None
    def advance_trailing_stop(self, position, candle) -> TrailingStopUpdate | None
```

The pipeline: **preconditions → equity → approve → ATR → levels → stop gate →
size → affordability → intent.** The order is forced, not chosen —
`risk_per_trade` sizes from the stop distance, an `rr` take-profit multiplies the
same distance, and an ATR stop needs a statistic that does not exist during
warmup.

Decisions and their reasoning:

- **State lives on `Portfolio`; policy lives on `RiskManager`.** The manager owns
  configuration, a market-data reference, per-pair exchange filters and a clock;
  the account state it reasons about arrives per call. That keeps the manager
  reconstructible after a restart, gives persistence one object to serialise
  instead of reaching into a risk component, and lets backtest and paper reuse
  one ledger. *Rejected:* holding positions and the limit ledger on the manager —
  it makes the manager stateful, un-restartable, and forces a second ledger for
  backtest.

- **`Portfolio` is mutable, and lives in `core/`.** Mutable by the rule that
  already makes `Position` mutable: value objects are frozen, things that
  accumulate over a run's life are not. A frozen per-signal snapshot would also
  have nowhere to record "cooldown started at T", which is a write. It lives in
  `core/` because `core/interfaces.py` must reference it, and `core/` is the
  innermost layer.

- **`validate_assignment=True` on `Portfolio` — and then on `Position`.** Plain
  pydantic models validate at *construction only*, so `portfolio.free_quote = 1.5`
  would slip a binary float past the `Money` guard on a mutable model. Adding it
  to `Portfolio` exposed that `Position` — mutable since Phase 1, and the one
  domain object written to on **every bar** — had the same hole, so it was closed
  in the same milestone. The leak path there is concrete rather than theoretical:
  the trailing stop is advanced from NumPy-derived market data, and
  `numpy.float64` is a `float` subclass. Guarding birth but not mutation had
  protected the less exposed half.

  An audit of every pydantic model in the package found `Position` was the only
  unguarded one in `core/`. Five `config/models.py` classes are also unguarded on
  assignment, and were deliberately left that way: their fields are plain
  `Decimal` rather than `Money`, and config is **loaded once from YAML and never
  mutated at runtime**, so there is no write for a guard to intercept. (An earlier
  draft of this reasoning claimed a corrupted config field would "fail loudly at
  the first `Decimal * float`". That is false and was not the reason: `Decimal`
  compares against `float` silently, and `update_trailing_stop` consumes
  `activation_percent` by comparison — `move_pct < config.activation_percent` —
  which would not raise. Immutability after load is the whole argument.)

- **Where a cross-field invariant would go, if one is ever needed.**
  `advance_trailing_stop` writes `highest_price` and `trailing_stop` in two
  statements, so with `validate_assignment` on, a future
  `model_validator(mode="after")` on `Position` would fire against the
  intermediate state. The recorded fix is to collapse those writes into a single
  method **on `Position`**, not to relax the validator to tolerate the halfway
  state — an invariant that accepts the halfway position is not an invariant, and
  a tolerant one would also accept a trailing stop that had genuinely drifted from
  its high-water mark.

- **Nothing in `Portfolio` reads a clock.** Every time-dependent method takes
  `now` explicitly; only the manager holds the injected `Clock`. That keeps the
  ledger a pure function of its inputs and makes the daily-loss and cooldown
  tests hermetic with no patching. Naive `datetime`s are rejected rather than
  assumed UTC — guessing a timezone is how a day boundary silently moves by
  hours.

- **`equity(marks)` takes mark prices per call.** Holding a `MarketDataProvider`
  on `Portfolio` would be an import cycle (`core.interfaces` imports the module)
  and would hide I/O behind an attribute read. A missing mark *raises* — equity
  is the denominator of every sizing and daily-loss decision, so defaulting to
  the entry price or to zero would silently misstate it. The manager checks
  first and converts the condition into a `RiskRule.NO_MARK_PRICE` refusal, so
  the raise stays a contract violation rather than a market state.

- **The daily-loss threshold is a percentage of *current* equity.** A deliberate
  approximation with a known direction: after a 5% loss equity is 95% of where it
  started, so a 5% cap sits at 4.75% of the original and the halt fires
  marginally **early**. Early is the correct direction for a loss limit.
  *Rejected:* exact start-of-day equity — it requires the ledger to be handed
  mark prices at the day roll, which can fall when no signal is in flight, and
  the alternative approximation errs *late*. The day rolls **lazily**, on read as
  well as on write: a scheduled reset would leave a bot that trades nothing
  overnight carrying yesterday's halt into a new day with nothing to poke it.

- **`approve` returns `RiskDecision`, not `bool`** — the port changed. Same rule
  `SizingDecision` and `ProtectiveLevels` already follow: "no trade" is a frozen
  object carrying its reason. A `False` cannot tell an operator whether the
  account is halted for the day or merely at its position cap, and those demand
  different responses. A validator ties `approved` to `rule is None`, so a
  refusal must name the rule that fired. This is what retired the self-removing
  `# type: ignore[no-untyped-def]` on the unannotated `portfolio` parameter,
  exactly as designed — `type: ignore` now appears nowhere in `src/`.

- **`RiskRule` names only what `approve` evaluates** (six members, including
  `NO_MARK_PRICE` and `NO_EQUITY` — both genuinely "do not trade" policies). The
  other refusals on the path — no signal price, unknown pair, ATR not ready, no
  placeable stop, unaffordable, too small to trade — carry a reason *string*.
  *Rejected:* an enum member per refusal. `SizingDecision` already sets the
  precedent: several distinct rejection causes, one `reason` string, no enum.

- **The manager performs no I/O; `SymbolInfo` is injected.** This was the friction
  the milestone plan did not anticipate: the port's `size_position` is
  synchronous and has no `symbol_info` parameter, while
  `calculate_position_size` requires one and `ExchangeClient.get_symbol_info` is
  a coroutine. Filters (and the pair's timeframe) arrive as a
  `Mapping[str, PairContext]` primed by the composition root. An unknown symbol
  then fails at boot rather than on the first signal hours later, and a unit test
  builds a manager from a plain dict with no fake exchange client at all.
  *Rejected:* an async `evaluate` awaiting `get_symbol_info` per signal (hides
  network I/O in the hot path and breaks `risk/`'s "no I/O" promise), and
  changing the port to pass `symbol_info` into `size_position` (a wider port
  change to solve a wiring problem).

- **Every refusal is a value; nothing on the path raises for a market
  condition.** Worth recording precisely, because M2's reasoning was based on a
  false premise: the engine does **not** quarantine a raising signal handler.
  `_record_failure` is reached only from `_evaluate`, so quarantine counts
  *strategy* failures; handler exceptions are caught in `_emit`, logged, and
  isolated. A raise here would therefore print a traceback on every bar forever
  rather than disabling the pair. Weaker consequence, same conclusion.

- **A stop that is enabled but not placeable this bar skips the entry — for
  *every* sizing method.** Only `risk_per_trade` consumes the stop numerically,
  so the narrow fix would have been to refuse just that method. But the operator
  asked for a stop; entering unprotected under `fixed_fraction` contradicts the
  instruction just as plainly, and the state is transient (M2's sub-tick case).
  `stop_loss.enabled` is what separates "stops are off, deliberately" from "no
  level fits the tick right now". This gate is also what keeps a `None` stop away
  from `calculate_position_size`'s contract check, which raises by design.

- **The ATR bridge needs two gates, not one.** `is_ready(atr_period + 1)` —
  because true range is undefined on the first bar — checked *before* the frame
  is built, so warmup costs nothing. Then `isfinite` on the scalar, because bar
  count alone is **not** sufficient: `_seeded_recursive_mean` re-masks NaN inputs
  after the seed, so a single bad tick yields a NaN long after warmup has passed.
  ATR is computed only when `stop_loss.type is ATR`, so a percent stop never
  inherits the warmup gate. When no ATR is available the signal is refused.
  *Rejected:* falling back to a percent stop (silently substitutes a different
  risk model for the configured one) and entering unprotected (breaks
  `risk_per_trade` outright).

- **`TradeIntent` is deliberately not an `OrderRequest`.** That type has no
  take-profit field, and its `stop_price` means "the trigger price of this
  order", not "the protective stop guarding this entry" — expressing an entry
  plus its two protective levels as one `OrderRequest` would be a lie execution
  would have to un-learn. Mapping an intent to an entry order plus protective
  orders is execution's job, where `_enforce` re-checks immediately before
  dispatch.

- **`TradeIntent` and `RiskAssessment` live in `risk/`, not `core/`.**
  `TradeIntent` embeds `ProtectiveLevels`, which lives in `risk/rules.py`, and
  `core/` must not import from `risk/`. Keeping the composed `evaluate` *off* the
  port avoids dragging `ProtectiveLevels` into `core/` for no benefit — the port
  keeps its two methods and the composition root wires the concrete manager to
  `on_signal`. `RiskAssessment` carries the component results (`decision`,
  `levels`, `sizing`) so an operator can see *where* a signal stopped without
  parsing the reason string.

- **A `CLOSE` bypasses the limits entirely.** An exit is not a new risk, and a
  limit that could trap an open position would be a risk rule that *creates*
  risk. Quantity is whatever is held; no sizing, no protective levels.

- **Exits are defined here and driven by execution.** This *overrules* the
  earlier note that "acting on `should_exit` is M3". An exit check is
  per-candle-per-position, but `on_signal` fires only when a strategy has an
  opinion — wiring exits into the signal path would skip every quiet bar, which
  is precisely the set of bars a stop exists for. The correct seam is the candle
  subscription, and acting means sending a closing order. So M3 ships the
  methods; the execution milestone subscribes.

- **Both exit methods are fed the closed candle's `close`, not its high/low.** On
  a close-driven engine the bot reacts at bar close and would fill near it; using
  the bar's low for a long stop would claim a fill at a price that has already
  gone — optimistic in backtest and dishonest live. Real protective orders rest
  at the exchange and fill intrabar; this path is the fallback, and `close` makes
  it trigger late, never early.

50 tests in `tests/unit/test_risk_manager.py`. Hermetic with no patching at all:
injected clock, scripted fake provider, filters as a plain dict — which is what
the no-I/O design buys. Both time-dependent rules are driven *through* their
boundary rather than only inside it.

Two tests exist in their current form because the first draft passed for the
wrong reason:

- The ATR-gap test NaNs the final bar's **high**, not its close. True range
  compares against the *previous* close, so a NaN close does not poison its own
  bar — the original version left ATR finite, approved the signal, and proved
  nothing. It now fails without the `isfinite` check.
- The sub-tick stop is asserted across all three sizing methods. A test of
  `risk_per_trade` alone would not have shown that `fixed_fraction` and
  `fixed_amount` also decline to enter unprotected.

---

## Phase 5 — pre-M4 hardening pass

Not a milestone: no `NEXT_MILESTONE.md` ever scoped it, so unlike M1–M3 this
entry is **reconstructed from the fourteen commits** between the M3 rotation
(`b4b2e47`) and `d13fd58`. It began as an audit of `CLAUDE.md` and
`PHASE_HISTORY.md` against the tree and turned into a sequence of small fixes,
each of which surfaced the next.

The through-line worth carrying: **every finding here was something a gate
reported and nobody read, or something asserted repeatedly without being
checked.** None of it was hard to discover once looked at.

### The gate moved into Python

`make check` had been the documented gate for five phases and had **never once
been executed as written** — `make` is not installed on the development machine,
so only its individual commands, retyped by hand, had ever run. The definition
moved to `scripts/check.py`; the Makefile targets became one-line delegations so
there is one definition rather than two that drift.

- Every step runs as `sys.executable -m <tool>`, so the checks cannot silently
  execute in a different Python earlier on `PATH`. That `ruff` resolves this way
  was verified rather than assumed — it is a Rust binary and the `__main__` shim
  was worth confirming.
- **Five negative controls**, because a gate that cannot fail is worse than no
  gate. Each violation was introduced, run, reverted: `ruff check` (unused
  import), `ruff format` (redundant split), `mypy` (untyped def), `pytest`
  (flipped `Decimal`), and — the one that matters — **two simultaneously**. An
  accumulator that broke early or got overwritten would still exit non-zero and
  still look correct under the four single-violation probes.
- **`check.py` returns its own exit code**, never a subprocess's verbatim, proven
  by a pytest collection error: pytest exits 2, `check.py` exits 1.
- **Two deliberate divergences from `make`**, both named so neither reads as an
  accident: run-all by default (`--fail-fast` restores halting), and delegated
  `make lint` no longer halting between `ruff check` and `ruff format --check`.
- Writing the controls exposed a **`SIM108` finding in `check.py` itself** — the
  gate caught its own author. It had been misread as passing because
  `ruff check <file> | tail -1` printed a fixes hint rather than
  `All checks passed!`.

### `| tail` — the defect that hid two others

A shell pipeline's exit status is the **last stage's** unless `set -o pipefail`,
so `python scripts/check.py | tail` reports `tail`'s success regardless of what
the gate did. This masked a non-zero exit **twice**: the `SIM108` finding above,
and a failing test.

The second cost is worse than the first. `addopts` already carried `-ra`, so
pytest **was** printing a summary naming the failing test — the truncation
discarded it, and the run was repeated before the output was read. The test has
never been identified. **Rule: never pipe `check.py`.**

### Dependency register — six deletions and one false entry

`httpx`, `SQLAlchemy`, `aiosqlite`, `fastapi`, `uvicorn` and `respx` were deleted
after verifying each was unimported across `src/`, `scripts/` and `tests/`.

**`freezegun` was not deleted, and the register was wrong about it.** It is
imported at `tests/unit/test_binance_client.py:18` and used as `@freeze_time` at
lines 174 and 186. The claim that it was unused had been carried in the
`requirements-dev.txt` comment since the pinning commit (`ffd6fe6`), repeated in
the `NEXT_MILESTONE` open item, and repeated again in the session handoff notes —
asserted three times, checked zero. Nobody grepped for `freeze_time`, because the
package name and the imported name differ.

`ruff` would have flagged a genuinely unused *import* as `F401`. **The gate
reading green should itself have been the clue** that "declared but unused" could
not be true of something imported.

The generalisation, now in `CLAUDE.md`: for a test-only dependency, "used" has
**three surfaces** — an import statement, a **decorator**, and a **fixture name in
a test signature**. The third needs neither an import nor a decorator, so
grepping the package name cannot see it. `respx` was re-checked against exactly
that surface (`respx_mock`: 0 hits) before deletion.

*Rejected:* treating the register as authoritative. It is a claim to re-verify,
not a fact to act on.

### `extra=` was silently dropped in text mode

Structured fields attached via `logger.info(..., extra={...})` were merged into
JSON output and discarded in text output — same call site, lossy result, no
error. Text is the default (`logging.file.json` is false), so M4's seven-field
intent line would have vanished in the default configuration while appearing to
work.

`PlainFormatter` appends them as logfmt, using `str()` to match the JSON sink's
`default=str`, so a `Decimal` renders identically in both. The empirical pass
found **three** plain sinks, not two: `RichHandler` (which carried *no* formatter
at all and renders its own columns), the `StreamHandler` used when `rich` is
missing, and the file handler.

**The required empty-`extra=` test failed on its first run**, and its cause is
the durable lesson: `logging.Formatter.format` **mutates the record**, assigning
`message` and `asctime` while rendering. "Surplus fields" is therefore only
meaningful **relative to a point in the format lifecycle** — a set computed from a
fresh record is correct before `super().format()` and wrong after it. Every plain
line the bot emits would have gained `message="..." asctime="..."`.

Resolved by **converging on `Logger.makeRecord`'s own guard** — the reserved set
is now every `LogRecord` attribute plus those two, which is exactly what the
stdlib refuses to let `extra=` overwrite — rather than special-casing the two
names at the formatter. Both ends of the contract now agree by construction.

Verified by byte-comparison captured before the change and re-run after: six
captures, zero differing. **First test coverage `utils/logger.py` has ever had**,
which is how the silent drop survived this long.

### `Position` — already closed, coverage completed

The assignment guard was reported as an open hole by the project-knowledge
document. **It was not:** `bd73a8d` closed it earlier in the same sequence, and
the document predated that commit. Verified empirically before touching anything.

What *was* incomplete was the coverage: three of seven `Money` fields sampled for
`float`, one for `numpy.float64`. Now all seven against both — and the field list
is **derived from `Position.model_fields`** by a test that fails if a `Money`
field is added without being covered, so the parametrised tests cannot fall
behind the type they guard.

### Config models — the guard that broke nothing

`validate_assignment=True` added to `config/models.py`'s base. **Nothing broke,
which is the finding**: it means the "config is loaded once and never mutated"
convention was true. The only two mutation sites in the tree both assign
`settings.mode`, and `Settings` is a plain class, not a pydantic model.

**The benefit is narrower than first assumed, and the tests say so.** Config
fields are plain `Decimal`, **not** `Money`, so assignment *coerces* rather than
rejecting — and coerces the safe way: `config.activation_percent = 0.1` yields
`Decimal("0.1")`, not `Decimal(0.1)`'s `0.1000000000000000055…`. So the guard
buys **shortest-repr conversion at the boundary, constraint enforcement (`gt=0`)
and typo rejection on assignment** — *not* float rejection. A first draft of the
test asserted a `ValidationError` and had to be corrected once measured.

That matters because the convention is load-bearing: without the guard a float
would simply be stored as a `float`, and `move_pct < config.activation_percent`
would compare against the binary expansion **silently**, since `Decimal < float`
does not raise.

### `Signal.metadata` — enforced by exact type, not `isinstance`

The "plain `int`/`float`/`str`" rule was convention only; the field is
`dict[str, object]` and nothing checked it. The hazard had sharpened: with the
log sink's `default=str`, a NumPy scalar no longer fails at serialisation — it
lands in a log line and in persistence as the repr `np.float64(1.5)`. The failure
moved from loud-at-write to quiet-forever.

**The mechanism deliberately differs from the `Money` guard**, and the asymmetry
is the point:

* `_reject_float` rejects the whole `float` family, so `isinstance` is exactly
  right there — `numpy.float64` is a subclass and is caught for free.
* `metadata` must **accept** `float` and **reject** `numpy.float64`, and no
  `isinstance` test separates them. Measured:
  `isinstance(np.float64(1.5), float)` is `True` while
  `type(np.float64(1.5)) is float` is `False`.

Same principle, necessarily different operator, pinned by a test asserting both
halves of that trap — if NumPy ever stops subclassing `float`, it flips and the
guard can be simplified.

Exact typing also **rejects every NumPy scalar without `core/` importing, or even
naming, NumPy**, which is what decided it over any hand-rolled detector: the
innermost layer stays free of the data stack. `bool` is listed explicitly because
`type(True) is int` is `False`, making its admission a decision rather than an
accident. Keys need no check — pydantic already rejects a non-`str` key from the
annotation.

`helpers.py`'s `float()` coercion was **kept**, measured as load-bearing rather
than redundant: `last_two` returns plain `float` where raw `iloc` yields
`float64`. Boundary conversion and domain enforcement are the two halves;
removing either turns a clean conversion into an error at every strategy that
reads an indicator.

---

## Phase 5 M4a — the composition root and the observable intent stream

`RiskManager.evaluate` had been complete as a library since M3 and was reachable
from nothing: `main.py` registered no `on_signal` handler, and no `Portfolio` or
`PairContext` was constructed anywhere outside tests. This milestone fills
`engine/modes.py` — a docstring-only stub since Phase 1 — with `live_system()`,
the async context manager that assembles the LIVE/TESTNET collaborators.

Nothing dispatches an order. The terminal collaborator is `IntentLogger`, named
for what it does. Calling it `Executor`, or putting it in `execution/`, would
have made the stub inventory claim something that does not exist.

### The provider-ownership fork

Three options were on the table for who builds the `MarketDataProvider` that
both the engine and the risk manager need.

**A — take it back off the engine after `TradingEngine.create`.** Dead twice
over. `_provider` is private (`live_engine.py:84`) with no property and no
accessor; and even granted one, the provider cannot supply what the root
actually needs, because priming `PairContext` requires `get_symbol_info` on the
*client*, which the provider holds privately one level further down.

**B — build the provider in the root and inject it.** Chosen. The seams already
existed: `TradingEngine.create(settings, *, provider=...)` and
`BufferedMarketDataProvider.create(settings, *, client=...)`. **B changed zero
production signatures** — the only new parameter anywhere is `stream=` on the
root's own new function, and that is new API, not a modification.

**C — bypass `create` and construct `TradingEngine(...)` directly.** Rejected:
`create` is where one strategy instance per pair is built from the registry, so
bypassing it duplicates that assembly in a second place. The one-instance-per-
pair decision would then have two homes and could drift in one.

### The ownership rule this settled

**The root owns anything shared between two collaborators, or requiring
teardown.** Applied:

- **Provider — shared** (engine and `RiskManager`), so the root owns it.
- **Client — shared** (boot-time priming and the provider) **and** needs
  `close()`, so the root owns it on both counts.
- **Stream — provider-only, no independent teardown**, so it stays inside
  `provider.create` and is never named in the root except as an injection seam
  for tests.

### Teardown, and why three scopes rather than two

`owns_client = client is None` (`market_data.py:203`), so under injection the
provider closes the client on **neither** path: not on success (`:293`) and not
when the stream fails to build (`:211`). The root's `finally` is therefore the
only close, and it closes **unconditionally** — inverting the `owns_client`
convention deliberately. That convention protects a *caller* holding a
long-lived client; this root has no caller. `close()` is idempotent, and has to
be already: `AsyncClient.create` calls `close_connection()` in its own `except`
before re-raising, so an existing path already depends on it.

Nesting rather than one `finally`, because a single `finally` naming `engine`
raises `UnboundLocalError` when the boot fails at step 2, 3 or 4 — masking the
real error with a bookkeeping one. Two scopes were specified; **three were
built.** `TradingEngine.create` can still raise on a bad strategy name, and by
that point the provider's stream owns a second `AsyncClient`
(`websocket_client.py:122`) that nothing else on that path would close. The
middle scope exists for that window alone.

### Checked, not a defect: the stream's second `AsyncClient` does not leak

The window above prompted a full trace of that client's lifecycle, and the
answer is that it is closed. `BinanceMarketDataStream.stop()` calls
`self._source.aclose()` at `websocket_client.py:250` **unconditionally** —
outside the `if task is not None` guard — and `aclose` is
`self._client.close_connection()` (`:137`). So `stop()` releases it whether or
not `start()` was ever called.

Verified rather than read: a counting fake `AsyncClient` driven through the real
chain (`engine.stop -> provider.stop -> stream.stop -> source.aclose ->
close_connection`) shows one close, and a step-5 boot failure driven through
`live_system` with a *real* stream shows one close of the stream's client and
one of the REST client. **The provider-scope `finally` is what closes that
window** — without it the source would be dropped with a live aiohttp session.

One genuine window remains and is unreachable; it is recorded in
`NEXT_MILESTONE.md` rather than here, because its guard lives in another file.

### The portfolio seeds from the exchange

`get_balances()`, not config. `Balance.free` is already `Money`, parsed by
`_dec` as `Decimal(str(...))` over the wire *string*, so no new float boundary
opens. The config route is dead twice over: both `initial_balance` fields are
`float`, **and** both belong to backtest/paper rather than to a live account.

`Portfolio()` at zero was not an option. `_approve` refuses `NO_EQUITY` at
`manager.py:279` when equity is not strictly positive, so a zero-seeded
portfolio would have shipped an observable path only ever observed refusing —
the milestone would have demonstrated nothing but its own first guard.

Both sides of the quote-asset match are upper-cased in the root, and the
normalised form is what lands on `Portfolio.quote_asset` because refusal
messages interpolate it (`manager.py:464`). A mirroring validator was added to
`TradingConfig.base_currency` in a separate commit — defence in depth, not the
fix: `_seed_portfolio` has to be correct standing alone.

### The duplicate-symbol defect

`RiskManager` keys its pair contexts by **symbol alone**, with the timeframe
inside the value; the engine keys by `(symbol, timeframe)`. Config permits
`BTCUSDT/1m` and `BTCUSDT/5m` together, and the obvious dict comprehension drops
one — last write wins, no error. The manager would then compute ATR for *both*
engine pairs off whichever timeframe survived: wrong stops, silently, on a green
gate. It cannot fire on today's `config.yaml`; nothing prevented the edit that
fires it.

Refused at boot, naming the symbol and both timeframes. The check is pure and
runs before any network call, so a config mistake costs no round trip.

Three further boot refusals were built on the same principle — an unprimeable
symbol, a quote asset absent from `get_balances` (absent, not zero: that call
returns every asset including zeros, so zero is a valid non-refusing state), and
a mode with no composition root. A fifth was added afterwards for an empty
enabled-pair set; `TradingEngine.start` already rejected it, but with a bare
`ValueError` — not a `TradingBotError` — several steps later, with a client and
a socket already open. That guard was left in place; the root simply refuses
earlier and names `config.yaml`.

### Why a stage vocabulary exists at all

`RiskAssessment` has no `rule` field. The rule is reached through
`assessment.decision.rule`, and it is **doubly optional**: `decision` may be
`None`, and even when present `rule` may be `None`.

The trap: **four refusal paths carry a decision whose `approved` is `True` and
whose `rule` is `None`** — the ATR bridge, the unplaceable stop, the sizer, and
affordability, all of which refuse *after* the limits passed. Branching on rule
presence reads all four as approvals. `RiskAssessment.approved` is the only
authoritative field, bound to `intent is not None` by its validator.

`RefusalStage` therefore lives in `modes.py` rather than in the domain. The
manager has no stage vocabulary yet, and choosing one before an operator has
read any of these labels would be designing the enum backwards. M4a proves the
vocabulary; M4b moves it inward.

`UNCLASSIFIED` is a **defect signal, not a category** — reachable only once the
ladder has drifted from `evaluate` — so it logs at `ERROR` while ordinary
refusals log at `INFO`.

### The two log sinks disagree about enums

Found while designing the schema, and it is the same shape as the asymmetry the
pre-M4 pass closed for structured fields generally. `json.dumps` sees a
`str, Enum` member as a `str` subclass and emits the underlying value (`"BUY"`);
`PlainFormatter` calls `str()` and gets `"SignalAction.BUY"`. **Same call site,
same field, two answers, no error either side.** It is a direct consequence of
the `str, Enum` decision (`UP042`) that keeps `str(member)` qualified.

So `extra=` takes `.value`, never the member — and a `datetime` takes an
explicit `.isoformat()` rather than leaning on `default=str`. The rule
generalises: only `Decimal`, `str`, `int`, `float`, `bool` and `None` may cross
unconverted.

### Two test findings, both of which cost something

**A passing test is not a biting test.** The ten-path stage test drives the real
`evaluate` down each refusal branch — but it proves each branch is *reachable*,
not that the ladder is *ordered*. A mutation that reordered two checks passed
all ten cases, because each case satisfies exactly one row's condition; pinning
an ordering needs an input that trips two rows at once.

A full adjacent-pair sweep followed, all ten constraints swapped in turn. Two
needed new tests (an unknown symbol *with no price*; a `CLOSE` *with no price*).
**Six were already pinned by implication** — where the earlier condition
strictly implies the later one, the ordinary case *is* the ordering test: a
`CLOSE` is necessarily "not BUY", a `RiskDecision` carrying a rule is
necessarily `approved=False` (its own validator forces it), a limit refusal
necessarily has `levels=None`. **Two are enforced by Python, not by tests**: the
`decision`/`sizing` null-guards also bind those names, so swapping them yields
`NameError`. Real coverage, different mechanism, and worth distinguishing.

**A test green alone and red in the suite.** `_emit_one` asserted
`len(caplog.records) == 1`. `caplog.at_level` lowers the capture *handler*'s
level globally, so `RiskManager.evaluate`'s own "Risk approved" `INFO` line
landed in the same buffer whenever an earlier test had left the root level low.
Two tests passed in isolation and failed in the full run. Records are now
selected by logger name. This is the "a green run only proves the path it took"
rule applying to the test harness itself.

---

## Phase 5 M4b — the stage moves into the domain

M4a shipped knowingly with the refusal label produced *outside* the code that
refuses: `modes._refusal_stage` re-derived `RiskManager.evaluate`'s control flow
in a second file. Four of the ten refusals return every component as `None` —
unknown pair, unusable price, `SELL`, nothing-to-close — so they were separable
only by their position in that sequence, plus the `Signal` and the root's own
`pairs` mapping. Adding a refusal path, or reordering two checks, mislabelled a
log line with nothing else failing anywhere.

That was the right call for M4a and the wrong state to keep. Choosing a stage
vocabulary before an operator had read a single one of these labels would have
been designing the enum backwards; M4a's job was to prove the vocabulary against
real refusals, and it did. M4b moves it inward.

### Done in three commits, deliberately

The move, the field, and the deletion are three separate commits because the
first is mechanical and the other two are not. `git diff` is the review surface
here, and a semantic change buried in a 30-line transplant is a change nobody
reviews. The mechanical commit carries the docstring **byte-identically**,
forward reference to `_refusal_stage` and all, so it reads as a pure move; the
docstring is rewritten two commits later when the thing it refers to is gone.
Each commit was independently green.

### Where the enum went, and why the direction was forced

`core/enums.py`, beside `RiskRule`. Not a preference: `engine/` imports `risk/`,
so `risk/` cannot import `engine/`, and once `RiskAssessment` carries a field of
this type the enum cannot stay in `modes.py`. `core/` is the only place both
layers already see.

**`RiskAssessment` itself did not move.** It stays in `risk/manager.py`. Moving
it collides with the port question — `evaluate` is still class-only while the
port declares `size_position` and `approve` — and that should be settled once,
with execution visible as a second consumer, rather than twice. So M4b's "into
the domain" resolved to *two different destinations*: the enum moved, the model
did not.

### All ten labels survived, one-to-one

No merges and no splits. Two looked mergeable and are not:

**`limit_refused` stays coarse over its five `RiskRule` values.** The stage says
*where* evaluation stopped; `decision.rule` says *which* limit fired, and the
decision is populated at that exact site, so nothing is lost by not splitting.
Splitting would duplicate `RiskRule` into a second vocabulary kept in sync by
hand — the precise failure mode this milestone exists to remove, reintroduced
one layer down.

**`no_mark_price` stays separate from `limit_refused`.** It refuses
structurally *before* `_approve` is called: it is an inability to compute
equity, not a limit's verdict. It is also the one point where the stage and rule
vocabularies genuinely coincide, which is what makes it look mergeable.

### `UNCLASSIFIED` did not enter the domain

It was moved in the mechanical commit — a verbatim move means verbatim — and
deleted in the third. Once the stage is set at the site that refuses, it is
unreachable: `RiskAssessment`'s validator binds a refusal to naming a stage, so
there is no valid object that lacks one. An unreachable enum member is not free.
It invites defensive branching on a state the domain forbids, and it sits there
as a plausible default for whoever adds the next refusal path — which is exactly
how a vocabulary stops meaning anything.

The `ERROR`-level signal it carried survives as a **local guard in the logger**,
not a category: `stage is None` on a refusal logs at `ERROR` against a fixed
literal (`_STAGE_UNSET`), with no enum member behind it. mypy needs the branch
regardless — it cannot derive `stage is not None` from `intent is None`, because
that link is a runtime validator — so the narrowing and the health check are the
same three lines. It is logged rather than raised or asserted, and the code says
why: `IntentLogger` runs inside the signal handler, which must never raise, and
`assert` would additionally vanish under `-O`. Without that comment the next
reader "simplifies" it into a raise.

### The invariant mirrors `RiskDecision`, on the opposite axis

`stage: RefusalStage | None`, **required but nullable** — no default, so every
construction site says something and an approval says `None` deliberately rather
than by omission. The check extends the existing `_check_invariants` rather than
adding a second validator:

```python
if self.approved != (self.stage is None):
```

Note the polarity. `stage` follows `rule`'s axis — present on a refusal — and so
reads *inverted* against `intent` two lines above it, which is present on an
approval. Getting this backwards inverts the invariant while leaving most tests
green, so it was checked directly rather than inferred: both illegal
combinations raise, and an omitted `stage` is a pydantic `missing`, not a
silent `None`.

Twelve sites name a stage: the nine `refuse()` calls, the direct
`RiskAssessment(...)` construction in `_exit_assessment` that sits outside
`evaluate`'s scope *and* outside its local helper, and the two approvals. A
second nested helper also named `refuse`, inside `_approve` and returning
`RiskDecision`, is not on this path and was left alone.

### The redundant ladder was kept for exactly one commit

Commit 2 left `_refusal_stage` in place and added
`assert assessment.stage is expected` **alongside** its existing assertion, so
the derived label and the reported one were compared across all ten paths. They
agreed. That is what licensed the deletion: without the added line, a green
commit 2 would have corroborated nothing, because the ladder test never read the
new field.

### The ordering tests, and one that was withdrawn

The order of the checks is still load-bearing — it decides which stage an input
satisfying two guards reports — it is simply no longer duplicated. A single-guard
input cannot detect a reorder, so each ordering test supplies an input that trips
two.

Three carried over from M4a and gained a fourth: **`limit_refused` ahead of
`atr_unavailable`**, witnessed by a BUY on a symbol already held (tripping
`ALREADY_IN_POSITION`) whose ATR window is one bar short. `decision` is assigned
before both guards, so the swapped source still compiles and the test reports a
wrong *value* rather than crashing — which is why this pair and not
`no_mark_price ↔ limit_refused`, where equity is computed between the guards and
the mutation would crash on the way.

Mutation-proved rather than assumed: one guard swap, full suite, **exactly one
failure — the intended test, reporting
`<RefusalStage.ATR_UNAVAILABLE> is <RefusalStage.LIMIT_REFUSED>`** — 636 others
passing, restored from a `shutil.copy2` byte copy in a `finally` and verified by
md5. The failure repr also showed `decision` still carrying
`rule=ALREADY_IN_POSITION`, confirming both guards genuinely held rather than
the test passing for an unrelated reason.

**A fifth ordering test was planned, written into the milestone brief, and then
withdrawn** — see finding (iii).

### The approval half was pinned in a follow-up, not during M4b

M4b pinned the refusal half ten ways and the approval half not at all. The
omission was deliberate at the time and wrong: a test asserting an approval
reports no stage was written during the milestone and withdrawn to hold the
agreed count, on the reasoning that `TestLogSchema` already asserted
`"stage" not in fields` for an approved entry.

That reasoning does not survive inspection. **That assertion is downstream of
`IntentLogger`'s early return**, which handles the approval branch without ever
reading `stage`, so it passes regardless of what the domain does. It cannot fail
if the approval half of the invariant breaks. The follow-up added the test back.

It also took **two** tests, not one, because there were two claims hiding behind
one sentence:

* `test_an_approval_reports_no_stage` (`TestEvaluate`) drives a real `evaluate`
  approval and asserts `stage is None`. This pins **`evaluate`'s behaviour**.
* `test_a_risk_assessment_stage_must_agree_with_its_verdict` (`TestMoneyGuard`,
  beside the two `RiskDecision` siblings it mirrors) constructs directly and
  asserts both illegal combinations raise. This pins **the validator**.

Neither implies the other, and the first alone leaves the validator deletable
with a green suite — verified by deleting the clause and watching exactly the
second test fail while the first passed.

The direct-construction test could not quite mirror its `RiskDecision` siblings,
for two reasons worth recording. `stage` is **required** while `rule` carries a
default, so the refusal direction must pass `None` explicitly — omitting it
raises pydantic's own `missing` and never reaches the validator. And the
approval direction needs a real `TradeIntent`, because `_check_invariants` binds
`intent` to `approved` first and would otherwise refuse for the wrong reason,
passing the test on the wrong error.

**`_exit_assessment`'s approval site remains unpinned.** It is a second,
independent `stage=None` construction and can drift alone; its fixture shape
differs enough that covering it is a separate piece of work rather than a rider.
Recorded rather than covered.

### One test legitimately died

`test_an_assessment_with_no_decision_past_the_preconditions_is_a_defect` and
`test_the_defect_signal_logs_louder_than_an_ordinary_refusal` were the only two
that hand-built an assessment rather than driving `evaluate`, and their subject
was the ladder's desync with `evaluate`. That subject has no referent once the
stage is set at source. Deleting them removes the **only** test of the `ERROR`
path — recorded here as honest rather than as a gap: the path is unreachable
from any valid `RiskAssessment`, so a test for it would have to construct an
object the validator forbids, which tests the test and not the code.

### Findings recorded, not fixed

**(i) `NO_MARK_PRICE` is constructed twice, with different reason text.**
`approve` (`manager.py`) says "…; equity is unknown, so no limit can be checked";
`evaluate` says only "cannot value open position(s) …". The two never meet at
runtime because `evaluate` bypasses the public `approve` entirely — it calls
`_mark_prices` then `_approve` directly. Not fixed in M4b: it is the one place
the stage and rule vocabularies coincide, and collapsing it is a decision about
the port, which belongs with M5.

**(ii) The deleted ladder read the *root's* `pairs` mapping while `evaluate`
reads `self._pairs`.** `live_system` passes the same object to both, so they
agreed — but that agreement was a wiring fact, not a type-level one, and nothing
linked the two files. Deleting the ladder removed the coupling rather than
documenting it.

**(iii) `size_not_tradeable ↔ unaffordable` is order-INDEPENDENT, not merely
unpinned.** This was going to be the ordering test, and the reasoning that
killed it is worth keeping so nobody re-derives it. `is_tradeable` is
`quantity > 0` and the validator forbids a negative quantity, so
`not is_tradeable` implies `quantity == 0` implies `cost == 0`; the affordability
guard is `cost > free_quote`. For any `free_quote >= 0` the two conditions are
**mutually exclusive** — guard 9 firing means guard 10 cannot. Swapping them is
not merely hard to observe, it is unobservable in every reachable state. A test
that bit would need a negative `free_quote`, and would then fail on a harmless
refactor while pinning nothing real. Not written.

**(iv) That independence rests on an unenforced domain invariant.**
`Portfolio.free_quote` carries no `ge=0` constraint (`core/portfolio.py`). A
negative free quote is nonsense for spot, and is unreachable today only because
the portfolio is seeded from exchange balance strings. The constraint was
deliberately **not** added in M4b — it is a domain change with its own blast
radius, not a rider on an observability milestone.

### Two adjacent pairs remain unpinned

`unsupported_action ↔ no_mark_price` and `no_mark_price ↔ limit_refused`.
Pre-existing debt that this milestone illuminates rather than creates, and
deliberately not addressed: the second is the one where a swap crashes rather
than mislabels, so a test there would assert on an exception type and prove
something other than ordering.

### Shipped, and what follows it

M4b and its follow-up are pushed. The gate closes the milestone at **639 passed
with Testnet credentials present** (636 + the three `skipif`-gated integration
tests), `ruff` clean, `ruff format` 83, `mypy` 58.

**The next milestone is Q-C, not Q-A.** Q-A was the obvious successor and cannot
be taken: its thresholds must come from soak data that cannot exist until
something dispatches an order, so it is blocked behind M5 — while Q-C, which
decides where the protective levels actually rest, blocks M5 in turn.

## Phase 5 Q-C — where the protective levels live

Decide-and-document. The output is a written contract,
`docs/QC_PROTECTIVE_ORDERS.md`, and no line of `src/` changed. M5 implements
against it.

### The question, and why it blocked M5

Every executor design assumes an answer to "which protective levels rest at the
exchange and which stay client-side", whether or not it says so. The answer
decides what `create_order` is called with and how many times, what the
unprotected window between an entry fill and its stop actually is, what
order-status tracking has to track, and what `Portfolio` write-back reconciles
against. Settled afterwards, the executor gets rewritten rather than extended.

### Two independent proposals, and where they diverged

This milestone was run as two proposals rather than one. A design was written
from the tree and the probe record on the assistant side, and a second was
written in chat; they were then compared and the disagreements pinned for
adjudication. The method was deliberate — a single proposal is checked only for
internal consistency, while two are checked against each other.

They agreed on the core: one order-list call, no split, protection accepted
atomically with the entry, client-side `check_exit` demoted from actor to
divergence monitor, deterministic client order IDs, and reconciliation keyed off
queries rather than cached state.

They diverged on four points, and the chat-side position won each:

**(i) The take-profit leg type.** The assistant proposed `LIMIT_MAKER`,
principally because it is free against the `MAX_NUM_ALGO_ORDERS` ceiling
(measured: eight consecutive `LIMIT_MAKER` orders never tripped it, while a stop
does) and earns maker rather than taker fees. The chat-side position was
`TAKE_PROFIT`, on the grounds that the algo-ceiling advantage had already been
downgraded as a constraint and the case therefore reduced to fees, while
`LIMIT_MAKER` is post-only and carries a rejection mode at activation whose blast
radius on the sibling stop is unmeasured. Choosing the measured failure mode over
the unmeasured one on the protective path won.

**(ii) Escalating on "entry FILLED, pendings PENDING_NEW".** The assistant's
reconciliation table had this as a `CRITICAL` — "impossible if placement
succeeded". It is not impossible; Binance documents it as the normal post-fill
response requiring a re-query, and under `FOK` it is the expected success path.
The row would have fired `CRITICAL` on every successful trade. Removed, replaced
by a re-query with a bounded deadline.

**(iii) The unprotected-divergence trigger.** The assistant keyed it on absence —
"position open, zero legs resting". Under a both-disabled configuration that
fires `CRITICAL` every candle forever. Re-keyed onto requested-and-absent, which
is what divergence actually means, and `ProtectionState` gained
`ABSENT_BY_DESIGN` so a deliberate absence is representable.

**(iv) Identity collisions on re-placement.** The assistant's ID scheme was
derived purely from `(symbol, entry_bar_time)`, which collides with itself the
moment protection is re-placed after a divergence — returning `-2010 'Duplicate
order sent.'`, which is measured. A generation segment was added, and with it the
honest restatement of the guarantee: generation 0 is derivable by pure
computation, anything above it is exchange-recoverable but not derivable.

### The above-leg decision REVERSED under S4's evidence

Worth recording because the reversal ran the other way to (i) and was driven by a
measurement rather than by argument. The chat-side position began as
`LIMIT_MAKER`-with-reservations. Probe S4 then placed a pending price outside
`PERCENT_PRICE_BY_SIDE`'s upper bound and had the request refused at submission
with `-1013`, the whole list rejected, nothing reaching `PENDING_NEW`. That
finding hardened the preference for avoiding an unmeasured activation-time
rejection on a leg whose failure takes the entire list with it, and the position
moved to `TAKE_PROFIT`.

A supporting argument offered at the time — that a one-price leg beats a
two-price leg — was raised in review and **withdrawn**: `LIMIT_MAKER` and
`TAKE_PROFIT` each carry exactly one price, so it distinguishes neither from the
other and rules out only `TAKE_PROFIT_LIMIT`. The decision rests on the post-only
rejection mode alone. It is recorded as withdrawn rather than quietly dropped,
because a document of record carrying a reason that does not hold is worse than
one carrying fewer reasons.

### TP-only is refused, and the refusal is a judgement

`stop_loss.enabled` and `take_profit.enabled` are independent today, and all four
combinations are reachable — verified by running the real `RiskConfig` and
`compute_protective_levels` across the grid rather than by reading them. The only
existing coupling refuses `take_profit.type='rr'` and
`position_sizing.method='risk_per_trade'` when the stop is disabled, because both
multiply a stop distance that a disabled stop never produces. Nothing couples the
two `enabled` flags.

Take-profit-without-stop will be refused, in `RiskConfig`, because it is uniquely
adversely shaped: winners truncated at the target, losers unbounded — the inverse
of what a risk overlay is for — and under exchange-resting protection the
favourable exit survives a crash while the unfavourable one does not. Nothing is
lost, since a wide `stop_loss.percent` expresses the same intent and names the
tolerance.

**This is a JUDGEMENT about payoff shape, not a measurement.** The code accepts
the configuration today and so would the exchange. It is written down as a
judgement so a later reader does not mistake it for something the venue enforces.

Both-disabled stays reachable with a boot warning, because `SignalAction.CLOSE`
exists precisely so a strategy can own its exits, and refusing it would be the
risk layer prohibiting a legitimate strategy style rather than managing risk.

### A locked decision re-scoped rather than repealed

`CLAUDE.md` locks "exit evaluation is fed the closed candle's `close`, never its
high/low". That is correct for a client-side stop and wrong for an
exchange-resting one, which triggers intrabar. Rather than leave two
contradicting statements in the same file, the rule was re-scoped to govern
*client-side* exit evaluation only. The consequence is recorded and not hidden:
`backtesting/` must model intrabar triggering, which is materially harder than
the close-only model, and it is the largest cost this design carries.

### The discretionary close path, and why its order is forced

A `CLOSE` signal against a position with resting protection cannot be dispatched
as a bare sell: the discretionary sell and a protective leg triggering moments
later would both complete, and the second sells base no longer held. The sequence
is cancel, confirm, sell.

Sell-then-cancel was rejected. It leaves a window in which the position is flat
and a protective leg is still live, which can produce a sell against a zero
balance; cancel-then-sell leaves a window in which the position is open and
unprotected, between two calls the client is actively making.
Unprotected-and-known beat protected-against-nothing.

Confirmation is by query and never by the cancel response, because `-2011` cannot
distinguish "already cancelled" from "already filled" and the two demand opposite
actions — sell, or record an exit that has already happened. The query reads
`executedQty` rather than `status` for the same reason.

### The probe record

Ten steps against Binance Spot Testnet, every one guarded by five structural
conditions: mode, credential identity by hash, `client.testnet`, and the
per-request resolved URI — never `client.API_URL`, which reports the production
host even under `testnet=True`. Every cell used a working price 30% below market
so nothing could fill, and the account total was identical at the start and end
of every step after the first.

**MEASURED:** the OTOCO 16-parameter and OTO 13-parameter schemas and the
forbidden-field sets each rejects with `-1106`; `MARKET` refused as a working type
(`-1159`) and `LIMIT` refused in the pending-above slot (`-1158`); `FOK` and `IOC`
both accepted with every leg expiring and zero residue; `PERCENT_PRICE_BY_SIDE`
enforced at submission and refusing the whole list; `contingencyType` reading
`"OTO"` on both shapes and never `"OTOCO"`; `listClientOrderId` returning `null`
in the placement response while correct on read-back; leg IDs honoured
byte-for-byte on both shapes; `expiryReason` distinguishing
`UNFILLED_FOK_ORDER_EXPIRED` from `OTO_PHASE_ONE_EXPIRED`; the overloaded meanings
of `-2010` and `-2011`; and read-back not round-tripping the request.

**DOCUMENTED, not measured:** the post-fill window in which the entry reads
`FILLED` while pendings still read `PENDING_NEW`.

**UNMEASURED, and recorded as such:** everything on the fill path, because no
probe ever filled a working leg. That includes the `PENDING_NEW` to `NEW`
transition, pending-leg partial fills, `LIMIT_MAKER`'s activation-rejection blast
radius, `TAKE_PROFIT`'s algo-slot cost, and whether `MARKET_LOT_SIZE` or
`NOTIONAL.applyMinToMarket` bind a triggered stop-type order. The last matters
most: both protective legs are stop-markets, so if it binds, it binds on
everything.

### A probe-discipline finding, paid for in a round trip

The OTO schema walk was capped at eight attempts. It needed ten. A discovery loop
that reveals one field per round trip needs a budget **exceeding** the field
count — and the field count is the unknown being discovered, so a cap chosen in
advance can silently become the finding rather than the endpoint's behaviour. The
walk stopped at the cap having learned eight field names and nothing about
acceptance; the cap was raised and the walk resumed from the derived set. Stopping
at the cap rather than exceeding it silently was right; setting it by guess was
not.

### Q-D folded in

`RiskAssessment` and the `RiskManager` port were deferred from M4b on the grounds
that the question needed a second consumer visible. This design supplies one: a
reconciler, plus `check_exit` changing role from actor to monitor. The port widens
to expose the composed path and `RiskAssessment` moves with it. Implementation is
M5's, not Q-C's.

---

## Known open items

**Live open items are tracked in `docs/NEXT_MILESTONE.md`, not here.**

This file is a build log: it records what each milestone decided and why, in the
tense it was decided. An open-items list is the opposite — it is current state,
and current state kept in two places drifts. It did: this section carried
"~16 files are formatter-dirty" while the real number had moved to 19, and
listed the `Position` assignment guard as outstanding after it had been closed.
Both were found by an audit rather than by reading, which is the argument for
keeping one copy.
