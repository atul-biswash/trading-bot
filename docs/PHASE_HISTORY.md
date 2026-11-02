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

## Phase 5 M5-0 — the decisions before dispatch

Decide-and-document, in Q-C's shape: the output is written decisions, and no line
of `src/` changed except a fix to the gate's own invocation. M5a implements
against it.

### Why a decisions-only milestone existed at all

M5 was scoped as one milestone and split into six after the design pass. Four
questions turned out to gate every one of them — where dispatch runs, how fills
are observed, what a `TradeIntent` means once entry and protection go out
together, and what the safety numbers are — and each had consequences in more than
one milestone. Deciding them inside M5a would have meant deciding them while
writing code that assumed an answer.

### D1 — the handler chain, and a rule that was never where it was thought to be

The chained signal handler was believed locked to "no I/O". It was not. `CLAUDE.md`
had one `no I/O` and it was scoped to `RiskManager`; the repo-resident
`PROJECT_KNOWLEDGE.md` had none; `PHASE_HISTORY`'s M4a entry had none. The rule
existed in exactly one place in the repository — the docstring of
`_build_signal_handler`. So M5 was codifying an unenforced convention rather than
re-scoping a locked decision, which is the lighter of the two, and the honest move
was to promote the real invariant while changing what it says.

"No I/O" was the consequence stated as the prohibition. M4a's handler was I/O-free
because it had nothing to do; M5's places orders. What survives is *the candle
pipeline must never be blocked by latency we do not bound ourselves* — a budget,
not an abstinence.

Dispatch stays inline. A bounded queue with a single consumer was rejected: it
makes `Portfolio` writable from a task that is not the one reading it, and the
first bug that buys is a **duplicate entry** — signal enqueued, not yet placed,
next bar's `BUY` sees `has_position` false and enqueues a second. A money bug
traded for a data bug the buffer already tolerates. Fire-and-forget was rejected
outright.

Two rules inverted while being drafted in their final voice. A budget may refuse to
BEGIN work but must never abandon a write in flight; and **between skipping a
placement and skipping a reconciliation, skip the placement**. The first draft had
that backwards — it protected the write and sacrificed the observation, when the
observation is what makes every subsequent write safe. A skipped placement is a
missed trade; a skipped reconciliation is a ledger drifting from reality while the
bot keeps trading on it.

### D2 — observing fills, and a limit that broke its own promise

Fills are observed by polling, over every open position on any pair's candle, so
staleness is bounded by the shortest configured timeframe rather than the slowest
position's. A user-data stream is the correct successor and was deferred: it has a
**worse** failure mode than polling, since a silently dead stream leaves us
believing we are current.

The sharp half was the daily-loss limit. M3 locked its approximation on the
grounds that a loss limit must err EARLY; polling makes the realised loss land
late. Rather than accept bounded lateness, the check now counts committed risk —
and the basis was got wrong first. Entry-to-stop was drafted and rejected: it drags
a third basis, position-lifetime, into a comparison that already has two, and the
overlap with mark-based equity is `1 + limit_percent` (about 1.05x), not 2x. The
reason to reject it is **basis coherence, not magnitude**. Mark-to-stop leaves both
left-hand terms "from today / from now". `realised_pnl` stays a record of realised
facts; the committed term lives in the check, which is what keeps the ledger
matching an exchange statement.

An uncomputable committed risk refuses rather than contributing zero — a position
with no stop carries unbounded forward risk, and zero is the exact inverse of the
truth. Scoped by `stop_loss.enabled`, reusing the discriminator already locked for
the sub-tick case, so a `CLOSE`-owning strategy is not prohibited.

### D3 — the intent splits rather than forking a field

Under Q-C an entry carries a derived `entry_limit` and a `CLOSE` dispatches
`MARKET` with no limit price at all. One field cannot carry both. Forking by side
was rejected because it makes `_check_invariants` conditional on `side`, which is
an invariant somebody eventually inverts. Dropping the intent from the `CLOSE` path
was rejected because `RiskAssessment`'s validator binds `approved` to
`intent is not None`.

The split makes `levels` **required** on an entry — the four-way placement branch
reads it to route — and adds `entry_limit >= reference_price`, which makes Q-C's
slippage direction a property of the type rather than a config constraint.

### Q-B, and what writing the mechanism down changed

Q-C leaned on "CRITICAL, halt entries" in three places and defined neither half.
Drafting the mechanism changed the design three times over the argument that
preceded it:

The sites split **three** ways, not two — self-clearing, resolvable by observation,
terminal. Escalating all five at one level would make the CRITICAL line unreadable
within a day, destroying it as a signal for the one site that genuinely cannot
resolve.

Site 1 halts the **symbol**, not the portfolio: the ledger is intact, only that
symbol's venue state is unknown, and halting everything for a failed cancel trains
an operator to override the halt.

Site 1 must also suppress **exits** on that symbol. The halt gates entries and
`CLOSE` is ungateable, so the next bar re-enters the same three-round-trip sequence
that just failed, indefinitely. That appears to violate "an exit must always be
permitted" and does not: the lock governs risk *limits*, while this is refusing to
act on unknown state, which Q-C §4b already mandates in the same breath.

CRITICAL means a log line and a halt flag, and nothing else. `notifications/` is a
stub and stayed out: a notifier that raises inside a handler that must not raise is
its own failure class.

### The second document, and a rule attributed to a file that never held it

`PROJECT_KNOWLEDGE.md` exists twice — a 237-line version tracked in the repo, and a
751-line version one directory above it, outside the git root. They are an original
and a deliberate rewrite; the rewrite is newer, is committed, and drops the twelve
sections that restated `CLAUDE.md`, which is what its own standing warning
forbids.

The `no I/O` rule lived in the out-of-repo §7. Its §9, "Locked decisions", was
diffed against `CLAUDE.md` and is **clean** — 20 rules, none absent — because its
header defers to `CLAUDE.md` and it never claimed completeness. That is the
finding: **look at the sections that state rules, not the one that curates them.**
The salvage was originally scoped to §9 and would have returned a clean result and
the wrong conclusion.

### The method findings, which will be harder to reconstruct than the decisions

**Pre-registering what would change your mind.** Before drafting the deliverables
in their final voice, a prediction was recorded of which ones would move and why.
It named `QB_ESCALATION.md` as highest risk and was right — three design changes
came out of writing it. It also predicted a signature ripple in the mark-to-stop
work that did **not** materialise, and saying so afterwards is the half that makes
the exercise worth anything. Drafting a rule in its final voice is a different test
from arguing for it.

**A design already accepted still had a defect in it.** PRE-1 checked two refusals
against each other that had been designed two turns apart and separately approved.
Measuring unmanaged base holdings from raw balances would have double-counted base
held by the bot's own positions in `equity`, and mislabelled `ALREADY_IN_POSITION`
as `UNMANAGED_HOLDING`. The fix was a timing argument rather than arithmetic — take
the snapshot at boot, before any `Position` exists — and it forced a correction to
an already-accepted claim: the refusal does not clear within a run, only across a
restart.

**A measurement was accepted, argued from, and written into the authority
document, and it was an artefact.** `git cat-file blob | grep -c $'\r'` was used to
show every blob in the tree was CRLF. `$'\r'` did not survive as a carriage return
in that shell, so the matcher matched every line. The tell was in the reported
table and both reader and writer went past it: the CR count equalled the total line
count in five heterogeneous files — a ratio of exactly 1.000, five times. A
contradicting reading from `cat -A` was then explained away with an invented
mixed-tree story instead of being resolved by re-measuring. The false claim reached
`CLAUDE.md`, replaced a true statement about the tree with a false one, and
declared a correct diagnosis in the mutation-testing section unverifiable. It was
reverted.

The rule that follows: **run an instrument against a case with a known answer
before trusting its output.** Counting CRs in a file known to be CRLF would have
caught it in seconds. Two instruments disagreeing is a stop condition, not
something to narrate around. It was applied immediately afterwards — the alpha
probe ships a `selftest` that injects a known lateness and a known handler delay
and asserts the probe reports both, run immediately before each sample rather than
once and reused.

**A document created to stop numbers drifting from their provenance shipped with a
false count.** `M5_NUMBERS.md`'s status legend read "Four of six are placeholders"
while all six entries read `PLACEHOLDER — NOT MEASURED`. It was false when written,
in the milestone that wrote it, in the one document whose entire purpose is keeping
a number attached to its evidence — and neither writer nor reviewer caught it until
the next turn's edit forced a read of the status lines. It is the sharpest
available illustration of why "nothing enforces the documented counts" is still an
open item: the counts that drift are not only the gate's.

**Venue-down was separated from tree-broken by asking the venue, not by re-running
the suite.** Three integration tests failed together; a direct request to
`testnet.binance.vision/api/v3/ping` returned 502 while `api.binance.com` returned
200, which located the fault outside the tree in one call. A 90-minute poll then
returned 502 ninety times out of ninety, and **uniform failure licensed stopping
rather than continuing** — the decision was brought back rather than absorbed by
waiting longer. This is the same family as the `| tail` incidents: the gate was
correct, and the thing that needed reading was not the gate.

### The gate's own invocation, fixed

`python scripts/check.py` resolved through PATH to an interpreter that had never
heard of this project, and reported four FAILs in 0.2s. It failed loudly only
because that interpreter happened to carry none of the four tools; had it carried
any, the gate would have reported PASS against the wrong environment with a
byte-identical summary block. That is the third time the gate was correct and its
invocation was not.

The guard keys on whether the interpreter can import **this checkout's**
`trading_bot` — deliberately not a location test, since "am I in a venv" passes any
venv and "is my prefix under the repo" refuses a legitimate CI runner or container.
Verified empirically in both directions rather than asserted.

### The alpha measurement, and the number it did not produce

Taken through the public `on_candle` port with two probes bracketing the engine's
handler, so its duration was measured without instrumenting it. 108 records over 90
minutes — exactly the expected count, so no bar was missed, which is itself the
direct answer to the question alpha guards.

Worst pipeline overhead 1744.1 ms against a 60000 ms bar, stationary across three
thirds. **The measurement bounds alpha and does not derive it**, which the
two-state status legend could not express, so a third state was added. Raising
alpha was refused on the record: it does not buy headroom, it relocates the
constraint onto venue latency the probe never sampled.

A 485.7 ms handler outlier was **not** treated as a p99. The six largest values
were 2.6, 2.7, 2.9, 2.9, 3.7 and 485.7 — one point 130x above the next is not a
tail, and the distribution is bimodal rather than heavy-tailed. Correlating against
the run log placed it on the only bar in the sample that ran the full composed
path.

Settling that at n=1 would have been guessing between two very different answers —
a once-per-process warm-up cost, or half a second on every order. A second
experiment substituted faster strategy periods against a **scratchpad** config,
leaving the composed path after the signal byte-identical, and converted an
unbounded wait for a natural crossover into 25 minutes at n=6. Executions two
through six cost 1.2–2.4 ms, indistinguishable from bars producing no signal.
Cold-start confirmed; "half a second every time" refuted.

What the experiment could **not** separate was pre-declared before it ran — tz
database load, decimal context, a lazy import, or a GC pause — and remains
unresolved. Declaring that in advance is what makes "one-off, cause unresolved"
credible rather than evasive.

---

## Phase 5 M5a — the vocabulary

The first M5 milestone to change `src/`, and deliberately the one with no I/O in
it. Config fields, `ProtectionState`, the widened `Position` and `Portfolio`, the
exchange filters nobody had modelled, and the coherence refusal. Sixteen commits,
plus this rotation.

### The rejections, which are most of what is worth recording

**The composed-path warm-up — dropped, and the number that justified it was
wrong.** `NEXT_MILESTONE` sequenced it explicitly last, on the argument that every
construction site the boot path touches is one this milestone changes. What
removed it was not the sequencing but `07d9309`: M5_NUMBERS §5 read *"at `D ≈ 3.5s`
a 485 ms excursion is 14% of the whole dispatch budget"*, and 3.5 s is the
constraint table's **per-call** column while `D` on that row is 10.5 s. The
arithmetic was right for the number quoted and the symbol was wrong, so the real
figure is **4.6%**, roughly a third the size. The warm-up was to be adjudicated on
4.6% and did not survive it. What survives unchanged is the underlying
measurement: the composed path costs ~2 ms warm and 10²ms on its first execution
in a process. If the warm-up returns it returns as dispatch's, at the milestone
that pays the cost on a real order — not as boot-time code whose only purpose is
timing, which rots invisibly because nothing fails when it stops being true.

**Plan commit 8 — the scoped relocation of `_seed_portfolio` — rejected on the
tree rather than on taste.** The idea was to move the portfolio seed later in the
boot so unmanaged holdings could be priced from the candle buffer instead of over
REST. It cannot work, and the reason is three calls deep:
`BufferedMarketDataProvider.create` only calls `track()`, which is
`setdefault(deque(maxlen=…))` — an **empty** deque. History is seeded in `start()`,
which `TradingEngine.start()` calls, which `main.py` calls *after* `live_system`
has yielded. So `last_candle` returns nothing at **every** point inside the
composition root, and the relocation would have moved the snapshot from one place
with no marks to another place with no marks. Replaced by one read-only
`get_ticker` per candidate asset: a round trip, and it keeps the whole step ahead
of any socket, where the other four boot refusals already live.

**`ProtectionState`'s complete-now member set — rejected. Two members, not five.**
Q-C names `PENDING`, `ACTIVE` and `DIVERGED` alongside `ABSENT_BY_DESIGN` and
`UNKNOWN`, and writing all five would have been one commit instead of several
later. The reason not to is the **field**, not the enum. `Position.protection` is
the one field whose wrong value is *silent*: `ABSENT_BY_DESIGN` asserts "no
protection is expected here", which is the off-switch for the divergence detector
on that position. An unwritten member is a plausible-looking value sitting within
reach of whoever is nearest a construction site and needs something to type. Only
the two states reachable today shipped — one forced by the order-list contract
(without it a both-disabled configuration reads as permanent divergence), one by
the locked rule that a timed-out write is marked unknown and resolved by querying
the IDs we would have sent. Adding a member later is additive and moves no
fixture; removing one already assigned somewhere is not.

**`EXPIRED_IN_MATCH` on the terminal side — rejected, and the rejection is about
evidence, not about the name.** It looks obviously terminal. Nothing in this tree
defines it and neither does `python-binance`, so "obviously" is the whole of the
case for it. Under the blacklist `is_open` became in the same commit, an
unmeasured member takes the side whose error costs one wasted round trip against
the reserved reconciliation floor, rather than the side whose error stops a
reconciler watching an order still working at the venue. **Moving it requires a
measurement, not an argument from its name**, and `core/enums.py` says so rather
than presenting the placement as settled.

### `is_open` inverted from a whitelist to a blacklist, in the window before it had a consumer

`is_open` was `self in (NEW, PARTIALLY_FILLED)` with `is_closed` its negation, so
every future member defaulted to CLOSED — the expensive default, because a status
nobody thought about is exactly the one nobody writes a test for. The property had
**zero production consumers**, measured: the only references anywhere were four
per-member assertions in `test_enums.py`, every other `is_open`/`is_closed` in the
tree belonging to `Position` or `Candle`, which are different names that happen to
share a spelling. That window was what made the direction free to change, and
adding `PENDING_NEW` is what closed it — Q-C §1 puts every protective leg in that
state from placement until the working order fills.

One existing member flipped: `PENDING_CANCEL` now reads open, which is more
correct, since a cancel in flight leaves the order on the book where it can still
fill. **No existing test covered it** — all four assertions passed under both
definitions, and a suite that passes either way is not covering the semantics.

### Two directions chosen in one milestone, deliberately opposite

`OrderStatus.is_open` became a **blacklist** of terminal states so an
unclassified member defaults to open. `_TRUSTED_PROTECTION` was written as a
**whitelist** so an unclassified `ProtectionState` defaults to untrusted. Read
side by side these look inconsistent; the rule that produces both is that each
field takes the direction whose **wrong answer is the cheap one**. For `is_open`,
wrongly-closed stops a reconciler watching a live order and wrongly-open costs a
round trip. For protection, wrongly-trusted makes committed risk *understate* and
lets an entry through on the strength of protection that does not exist.

### Mark-to-stop, on basis coherence rather than magnitude

The daily-loss check already compares two quantities: realised P&L from the start
of today to now, and a percentage of equity as of now. The committed term
`(binding_stop − mark)` measures from now forward, so the comparison stays at two
bases. Entry-to-stop would introduce a third window that can span days, and would
double-count — not by a factor of two: the entry-to-mark move is already
unrealised P&L, so `equity(now)` has reduced the threshold by `limit_percent` of
it on the right, and entry-to-stop would put the same move on the left at full
weight. The overlap is `1 + limit_percent`. **Magnitude was not the argument;
basis coherence was.**

`binding_stop` takes `should_exit`'s tie-break — `max` for a long, `min` for a
short — over the stops that are **present**, not the stops that have **triggered**.
That distinction is the one thing here that would have failed silently: reusing
`should_exit`'s candidate set literally returns `None` for every healthy position
and reports committed risk of zero, the exact inversion the uncomputable count
exists to prevent.

### The unmanaged-holding refusal is placed after the limits, and the placement is the decision

`NO_MARK_PRICE` and `COMMITTED_RISK_UNKNOWN` refuse **before** the limits because
they are inabilities to compute. Under an unmanaged holding the ledger is
**intact** — nothing is uncomputable, one symbol is simply not ours to trade — so
placing it beside them would assert the opposite in the structure of the code. It
refuses after `_approve`, which keeps `_approve`'s documented order untouched
while still carrying its own stage. "The bot never sells it" is then enforced by
the **existing** path rather than a new guard: no `Position` is constructed, so
`_exit_assessment` finds none and returns `NOTHING_TO_CLOSE`.

`total` and `free` answer different questions and both are used. Equity asks what
the account **owns**, so the recorded quantity is `total`. Materiality asks whether
this is **dust**, and Q-C defines dust by *sellability*, so only `free` clears the
threshold. Q-C is silent on this and the next reader will assume the two agree.

### The take-profit-only refusal, and an order that would have made a check dead

Refused because the payoff shape is adversely lopsided, **not** because anything
cannot compute it — the exchange accepts it and so did this bot until now. The
message names the opinion as ours, and a test asserts that it does, because an
operator reading the refusal as an exchange constraint will go looking for a
filter that does not exist.

Order matters between the first and third checks: `rr`-with-no-stop is a **strict
subset** of take-profit-with-no-stop, so checked second it would be unreachable.
That subsumption also made the first check's *remedy* wrong rather than merely
narrow — it advised switching to `take_profit.type='percent'`, which is now
refused too.

### What the coherence validator taught about the suite

`P_sim × D + N_max × T_recon <= alpha × T_min`, on `AppConfig` because two of the
five terms come from `trading.pairs`. **The empty-pairs case would have broken the
whole suite** and was found four turns before the commit: `tests/conftest.py`
writes no `trading:` key, so `pairs` falls to its default empty list on every
config-loading test, and a naive `min()` raises on all of them. The guard returns
early — vacuously satisfied, no pipeline to overrun, `T_min` undefined rather than
zero — and refusing there instead was rejected because `live_system` already
refuses an empty enabled-pair set at boot, so one configuration would produce two
different errors depending on which check ran first.

`alpha` lives as a module constant beside its only consumer rather than as a
config field: it is a property of the pipeline's headroom policy, not of an
operator's account.

### `_enforce` was weaker than the sizing it exists to re-check

Three fixes, deliberately separate commits. It rounded to `LOT_SIZE.stepSize`
while sizing used the **effective** filters, so the independent last line of
defence could pass a quantity the sizer would have refused — the two agreed only
by coincidence on symbols where `MARKET_LOT_SIZE` does not bind. It ran the
notional check only `if price is not None`, so every stop-type order went
unchecked, and that is the wrong half to skip: the exchange evaluates
`stopPrice × quantity`, and a stop below the entry carries the *smaller* notional
and is the leg rejected first. Observed live, not deduced — a Testnet probe took
`-1013 Filter failure: NOTIONAL` on exactly that shape.

The third landed a commit later than the other two because **the obvious fix was
wrong**. `_enforce` passed `stop_price` through un-rounded; rounding it like
`price` would use `ROUND_DOWN`, and on a long's `STOP_LOSS` the trigger sits
*below* its reference, so rounding down moves it **away** from entry and the
realised stop distance grows — an unbooked breach of `risk_per_trade` arriving
through the component that exists to catch exactly that. Rounding by inferred
direction was rejected too: it would make the dispatch adapter read *risk
semantics* off `OrderType` and side, and what a level means is risk's business.
So it **rejects**. Stated plainly in the commit and worth repeating: this
*converts* the defect rather than closing it — `_enforce` still does not defend
the trigger, it detects that someone upstream failed to.

### The eleven-filter fixture, and what a fence does not buy

The `exchangeInfo` fixture keeps the whole eleven-filter array in wire order
rather than reducing to the four the mapper reads. Reducing it is precisely what
hid `LOT_SIZE.maxQty` and `NOTIONAL.applyMinToMarket` from this suite for five
phases: a fixture trimmed to what the mapper consumes cannot show what the mapper
ignores.

Writing it produced a rule the authority lacked. It was first laid one filter per
line, as the wire presents it, held in shape by seven `# noqa: E501`
suppressions — in a tranche whose constraints said no `noqa`, written immediately
after being told so. **`# fmt: off` suppresses the formatter; `E501` is a lint
rule and is untouched by it.** The fence had felt like permission for the whole
layout and is permission for part of it.

### The rotation

`scripts/check.py` gained a second invocation guard: it refuses a run whose
stdout is a pipe. `isatty()` was rejected on measurement rather than taste — on
this machine it is false for a pipe, for `> gate.log` under both cmd.exe and
git-bash, *and* for the harness the work is done through, so a guard on it would
refuse a file redirect, which launders nothing and truncates nothing.
`stat.S_ISFIFO` discriminates, verified on real descriptors under both shells.
The guard cannot repair `$?` — under `| tail` the refusal's own status is
laundered too — and the docstring says so; what it buys is that the run does not
happen and the operator gets a refusal instead of a plausible summary.

**The superseded reading owed to this file from `7c1af17`.** `CLAUDE.md`'s
Execution bullet read *"It is roughly a third of the general timeout."* That
described the **derived per-call share** (~3.3 s against the 10 s general timeout)
and **not the field**, which bounds the whole dispatch sequence — worst case the
three-call `CLOSE`. `M5_NUMBERS` §5 said whole-sequence in its first line and in
its constraint table's symbol row, so the authority was the file disagreeing with
the contract. Recorded here because `CLAUDE.md` carries no annotation blocks by
house style, so the correction landed as prose and the old reading went into a
commit body — and a commit message is loaded into no future session.

**The salvage's `src/` docstring half closed with four promotions**, and two of
them were *undercounted by the plan and corrected by reading the code*. Lifecycle
idempotence was filed as six sites and is nine, in three spellings — a grep for
`Idempotent` misses `TradingEngine.stop`, one of the two methods the root's
double-teardown depends on. Handler isolation was filed as two layers and is
three; `_notify`'s own docstring says it mirrors the stream's, and the stream has
one. Both tables are in `CLAUDE.md` rather than a sentence, because in both cases
the sentence is what was wrong.

**Two items absorbed into M5a's scope did not land, and are carried deliberately
rather than allowed to vanish.** An absorbed item is removed from the open-items
list by the rotation, so an absorbed-but-undone item disappears without ever being
closed — that is the hazard, and it is the reason both are named in
`NEXT_MILESTONE` as M5b's: `NO_MARK_PRICE`'s two divergent reason strings, and
`engine/modes.py`'s handler docstring still reading *"No I/O"* after M5-0
superseded that rule with a bounded-I/O one.

---

## Phase 5 M5b — the intent split and the widened port

The second M5 milestone to change `src/`, and the second with no I/O in it.
`TradeIntent` split, the assessment family moved to `core/`, the port widened to
carry `evaluate`, and `entry_limit` became a derived price. Commits 0 through 13,
plus **six** rotation commits.

> **CORRECTED at M5c (finding MM). This read "plus five rotation commits", and
> six landed.** The sixth is `8d76c6a`, added to the list below. Measured:
> `4926705..e0f94fa~1` -- the range as it stood immediately before M5c's first
> commit -- contains six.
>
> **The cause is structural and is worth more than the correction.** A rotation
> cannot count itself, because the count is written before the commit that
> writes it exists. `8d76c6a` is the commit that wrote this entry, so at the
> moment this sentence was typed there were five and the sixth was the act of
> typing it. Every rotation that states its own commit count will be short by at
> least one for the same reason, and it will look like carelessness rather than
> like arithmetic.
>
> **UNFIXED, and deliberately not fixed here.** The remedy -- the milestone's
> commit table and count completed by the FINAL rotation commit, the only one
> that can see all the others -- is a change to the rotation procedure, so it
> belongs in `CLAUDE.md` and not in this build log. Named, left.

**Planned as commits 0 through 7 and closed at commits 0 through 13.** The delta
is not a slippage figure, and recording it as one would hide what happened. Six
commits were unplanned — **2, 3, 4, 11, 12, 13** — and four planned ones changed
shape: planned 0 split into 0 and 1; planned 1 split into 6 and 7; planned 5 was
folded into 9; planned 6 closed by construction at 8.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 0 | `9472e30` | P1's read path: `realised_today` derives the day instead of assigning it (finding J) |
| 1 | `37a9ee1` | The ledger's day comparison tests lateness, not difference — a `now` moved backwards no longer reads as a new day |
| 2 | `7e5cd5c` | `close_position` writes nothing until everything fallible has run (finding K) |
| 3 | `5adefc0` | `record_realised_pnl` commits the roll only once the accrual can succeed — the same discipline, second instance |
| 4 | `fd00af4` | The daily-loss message reports the basis the predicate uses (finding N), and `_approve`'s approval reason with it (finding V) |
| 5 | `7cdeb40` | `modes.py`'s docstrings describe the tree they are in — the "No I/O." handler clause superseded by the bounded-I/O rule |
| 6 | `e99f3a7` | `ProtectiveLevels` moves to `core/models.py`; the `__all__` policy settled; finding BB discharged |
| 7 | `d1c11df` | The assessment family moves to `core/assessment.py`, closing the import cycle |
| 8 | `8f0c5ee` | The port carries `evaluate` and `approve` is **deleted**; P2 resolved; `NO_MARK_PRICE`'s divergence closed by construction |
| 9 | `43fe377` | `TradeIntent` splits into `EntryIntent` / `ExitIntent`; the log line follows the split |
| 10 | `dcf4a93` | `entry_limit` derived from `max_entry_slippage` under `ROUND_CEILING` (finding A) |
| 11 | `dfd1a4d` | `derive_entry_limit` joins the package surface — the one exception to commit 6's policy |
| 12 | `8f8c2f3` | A trailing stop with no stop-loss is refused at load (finding U) |
| 13 | `4926705` | Committed risk prices off what rests at the venue (row 2) |

Rotation, corrections before additions: `dacec7b` (the statements M5b made
false), `6343f2e` (the counts, alone), `f342847` (three `src/` docstrings),
`f24dce9` (the rules M5b produced), `a84e400` (`NEXT_MILESTONE` rewritten for
M5c), and `8d76c6a` (this entry itself).

> **`8d76c6a` added at M5c (finding MM); the other five are unchanged.** It is
> last because it is the commit that wrote this list, which is exactly why it
> was absent -- see the correction above. Recorded here rather than left to be
> inferred from `git log`, because this list is what a reader checks the count
> against.

### Six additions, and where they came from

Every one came from a Phase 1 report finding something the prompt did not name.
That is the milestone's characteristic result and the argument for the
report-before-implement shape: **J** (the day-roll's mutation on read), **K's
real scope** (the ordering discipline binds every multi-write method, not the one
named), **N** (the daily-loss message reporting a basis the predicate does not
use), **row 2** (committed risk priced off a level that rests nowhere), **Q-C §4's
`ROUND_FLOOR` contradiction**, and **Finding U** (a trailing stop with no
stop-loss falsifying a locked claim).

Finding U qualifies by the same test as the others: found while investigating
something else, measured rather than supposed, and producing a contradiction with
a locked claim that no gate step would surface.

### Build reasoning

**T — a commit changed another method's justification without touching it.**
Commit 0 silently made `_roll_day` single-use: two callers before, one after.
That is what made commit 3's inlining a simplification rather than a
duplication. Discoverable only by grepping, and nothing in the diff of either
commit says so.

**CC — the import-proof set was insufficient for a commit that adds a module.**
The four-entry-point set passed against a counterfactual tree *without* commit 6,
supporting the wrong conclusion that the cycle was not exercised. The new module
is itself an entry point; adding `trading_bot.core.assessment` produced the
`ImportError` that justified the commit. **A defect in the instrument, not in the
tree** — the same shape as the line-ending measurement at M5a, where the
instrument had to be validated against a known non-zero answer before its zero
could be believed.

**EE — `ruff` config discovery is CWD-dependent, and that is where A3's second
trap came from.** `--stdin-filename` resolves relative to the CWD, so from the
scratchpad no `pyproject.toml` is found and ruff falls back to line-length 88
instead of the project's 100 — producing a large reformat diff that vanished when
the same command ran from the project root.

**GG — `approve` was dead production code for two milestones.** From M4b to
commit 8 it had zero callers in `src/` and `scripts/`, with `evaluate` bypassing
it via `self._approve`. The M4b entry above notes the bypass; nothing tracked
that a **port** method sat with no production caller across two milestones,
accumulating the P2 gap that made deleting it a prerequisite rather than a
tidy-up.

**II — pydantic's smart union preserves an exact instance, and the falsifier is
four edits, not two.** Measured across a sixteen-cell matrix over
`from_attributes`, `revalidate_instances`, the side check, annotation order and
union mode: exactly one cell coerces, and it needs all of `from_attributes=True`,
`ExitIntent`'s side check removed, the union reordered, and
`union_mode="left_to_right"`. While an `EntryIntent` remains a valid
`EntryIntent`, no configuration change makes it validate as anything else. This
replaced two earlier and wrong accounts of the same property.

**L's finding (iii) — two documents disagree about who owns the trailing
milestone.** Q-C §5 defers the design to "the trailing milestone"; `CLAUDE.md`
assigns the *driving* of `check_exit` / `advance_trailing_stop` to execution.
`NEXT_MILESTONE` schedules neither. Carried to M5c with its arming condition.

### The prediction instrument, and its three failure modes

Predicting the gate counts before running it was worth more in its disagreements
than in its agreements. **The three failures were different in kind and are kept
distinct**, because collapsing them into "the prediction was wrong sometimes"
loses the only useful part:

1. **A corrected expectation** (commit 8) — the figure moved because the *change
   set* moved. Not an error in the instrument.
2. **A miscount of an authorised set** (commit 9) — the change set was fixed and
   the arithmetic over it was wrong, by one parametrized case.
3. **A miscount inherited from a report** (commit 10) — a Phase 1 report summed
   its own five-row table as seven cases when it enumerated eight, and the
   ruling that followed inherited the figure without re-deriving it.

The third is the instructive one: a wrong number passed from implementer to
reviewer and back, and was caught only by the run. Its mirror image occurred at
the corrections pass, where a figure travelled the other way — see below.

### Plan drift, recorded because the labels stopped being usable

Two scheduling labels in `NEXT_MILESTONE` were wrong by the end.
`NO_MARK_PRICE` was planned as "M5b commit 6" and closed at commit 8;
`modes.py`'s "No I/O." docstring was planned as "commit 7" and landed at commit
5. Both items landed; neither landed where the plan said.

The numbering diverged at the very first reshaping and **no document noticed**:
`e99f3a7`'s own message calls it *"M5b commit 6, mechanical"* while the plan
called commit **1** the mechanical move. A plan that renumbers itself silently is
one whose labels cannot be used to check whether an item landed, which is what
they exist for.

Related, and introduced by the reviewer rather than the implementer: `CLAUDE.md`
acquired *"M5b is complete, in thirteen commits"* during the **corrections**
pass. The commits are numbered 0 through 13, so the cardinal was an off-by-one on
a zero-indexed sequence. It was caught because the number was verified rather
than transcribed, and it is why the ordinal form is now the rule. **A pass whose
subject is false statements can introduce one.**

### The rule this entry exists to record

**A finding destined for `PHASE_HISTORY.md` is written there at the commit that
produced it — not carried to rotation.** Rotation *compiles*; it must not be a
finding's first contact with disk.

This entry nearly proved the point by losing four of its own findings. T, CC, EE
and GG were generated in Phase 1 reports, never folded into a commit message, and
therefore existed **only in chat**. Across M5b's sessions the only findings that
reached the tree are the ones a commit message happened to name — U, V, BB, A and
II survived for exactly that reason. T, CC, EE and GG survived solely because the
conversation was still open when rotation ran, and writing them here required the
reviewer to supply them back from context that no tool in this project can read.

**That is the same drift class as `phase_5_`** — build reasoning living outside
the repo, invisible to every gate, grep and review — and unlike `phase_5_` it has
now cost something: a rotation commit blocked, and four findings one closed
window away from being irrecoverable.

### A third class of protected digit

`f24dce9` introduced `569` into `CLAUDE.md` for the first time outside the D3 and
M4a illustrations, quoting the stale count `phase_5_` reported. It is historical
prose and must not be swept up by a future count pass — which is governed by the
rule the same rotation wrote: **edit count sites by surrounding context, never by
digit pattern.**

The rule's first test was the commit that wrote it. The corrections pass wrote
*"a 58% understatement"* into the `_binding_stop` annotation, and the counts
commit that followed substituted `58 → 59` for mypy's file count. A digit-wide
substitution would have rewritten a measured figure into a fabricated one, inside
an annotation whose entire subject is a measurement. It survived because the
count sites were edited by context. The pair — grep the digits, then edit by
context — is recorded together in `NEXT_MILESTONE`'s process section, with a
pointer from `CLAUDE.md`.

---

## Phase 5 M5c — the milestone that bought certainty and no code

M5c set out to build the adapter surface. **It did not.** Its own Phase 1 put the
weight on the order-list port methods, the request type and mapper, and the Q-C
§6 ID scheme; none of the three exists. What landed instead is the Q-C §8 error
classifier and four Testnet probes. **Twenty-one numbered commits, plus five
rotation commits — this one included.**

That gap is the entry's headline rather than a footnote, because M5c's own scope
confusion started the same way: the heading of `NEXT_MILESTONE` promised "the
adapter surface and the first order" while its delivery list contained neither,
and the first Phase 1 report had to answer *which reading the tree supports*
before any work could begin.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `8b7c688` | Findings land at their commit; `.gitmessage` and the clause that says it enforces nothing |
| 2 | `5afbe5c` | The finding-line shape is ASCII, matching every commit message in the tree |
| 3 | `505efcd` | Trailing is UNASSIGNABLE with its blocking question named; M5c stops at the adapter surface |
| 4 | `a7cf5e8` | The amend window; IDs allocated on disk; a precondition is a check, not a sentence |
| 5 | `5215350` | M5b's rotation count corrected from five to six (finding MM) |
| 6 | `3d0b251` | The gate's pipe guard has a documented override, and presence is the trigger |
| 7 | `0e793fa` | The ASCII rule is a propagation boundary, not a file rule |
| 8 | `36f5d2f` | Finding IDs name their milestone from M5d; a baseline states its instrument |
| 9 | `240353c` | The flat-sequence ruling falsified by exhaustion, annotated not rewritten |
| 10 | `9c47858` | The duplicate order-list probe recorded — **and its central claim was wrong** |
| 11 | `5aba5c7` | ID uniqueness is live-only; the recovery rule stands; `9c47858` corrected |
| 12 | `6d19c58` | The classifier dispatches from a rule table (mechanical, zero behaviour change) |
| 13 | `d7abd85` | `-2010` splits into duplicate and insufficient-balance on message text |
| 14 | `975d863` | `-2011` → `OrderNotFoundError` |
| 15 | `c42cbf7` | `-1013` → `FilterRejectedError` with the filter name captured |
| 16 | `15907d4` | `-1100` → `MalformedRequestError`, the one family outside `OrderError` |
| 17 | `2498bee` | The contract group → `ContractViolationError`; `-1128` deliberately unclassified |
| 18 | `6979b1d` | `-1111` unclassified and its code survives |
| 19 | `1715b37` | The hierarchy pass: every classified venue error carries its code |
| 20 | `bfafae0` | `InsufficientBalanceError` is an `OrderError`; M5c-AJ's remedy |
| 21 | `6502acf` | The rules M5c produced, counted rather than quoted |

Rotation: `efcc5e3` (Current state), `6cee268` (the counts, alone), `bc45b45`
(`README`'s build state), `5660924` (`NEXT_MILESTONE` rewritten for M5d), **and
this commit**, which records the milestone.

### The rotation fix, and the version that does not work

MM's cause is structural: **a rotation cannot count itself, because the count is
written before the commit that writes it exists.** M5b's entry said "five" and six
had landed.

**The fix carried for six turns — "the commit table and count are completed by the
FINAL rotation commit" — does not work, and the wrong fix is part of the
finding.** Any commit that writes the count is uncounted by it, so moving the
write to the last commit moves the defect with it.

What makes the real fix small is that **the table was never the problem.** M5b's
table covered the *numbered* commits; the rotation commits lived in prose below
it. MM was entirely a prose defect. So:

> **The `PHASE_HISTORY` entry is the final rotation commit, and it counts itself
> deliberately: it writes N *including* itself, and names the last commit as
> "this commit" rather than by SHA — because a commit cannot know its own SHA
> before it exists.**

This entry is the first to do it: five rotation commits, four with SHAs and one
named as itself.

**WW's coupling rule lands with it, because this entry creates the next
instance as it is written.** A count and its list are a *coupled pair*, hand-synced
and unenforced, and a milestone entry contains two of them — the numbered count
against the table, and the rotation count against the rotation list. At M5b the
first held and the second drifted. **Self-reference predicts which side drifts:**
not the longer list, not the older one, but the one whose subject is the rotation
writing it.

### The order of rotation is now load-bearing, and NN(3) is why

The extractor's base is `tail -1` of the last commit table. **The moment this
entry lands, that base jumps from `4926705` to `6502acf`** and every block this
entry compiles falls out of range. So the extractor was run *before* this commit
was written — 25 blocks, 59 findings across 31 commits — and the entry written
from what it returned.

That is a workaround, not a fix. NN's remedy is carried to M5d unruled.

### What the probes bought, including the one that was wrong

Four Testnet probes, all read-only or self-cancelling, none filling.

**The duplicate order-list probe concluded the opposite of the truth, and the
correction is the most instructive result of the milestone.** Arms 1–9 resubmitted
an accepted list's byte-identical parameters and were accepted every time, so
`9c47858` recorded that order lists are not deduplicated and annotated
`CLAUDE.md`'s timed-out-write recovery as falsified. Arms 10–11 then measured the
**live** case directly: a list confirmed `EXECUTING` by read-back, resubmitted
byte-identical, returned `-2010` HTTP 400 `"Duplicate order sent."`

**The rule is: a client order ID is unique against LIVE orders only; a terminal
order's ID is released and immediately reusable** — identically for single orders
and for lists. Q-C §8's classification holds and the recovery rule **stands as
written**.

**The defect was in the arm set's design, not in any measurement it made.** Every
one of the nine arms sampled a terminated original, and ID-release and
absence-of-deduplication predict identical results in that state — including both
control arms built to isolate *which field* was keyed, which isolated the wrong
axis. The discriminating arm was a plain single order, which the original design
did not contain.

Also measured: the 36-character client-order-ID limit and its regex
`^[a-zA-Z0-9-_]{1,36}$`, where a *length* violation is reported as "Illegal
characters found"; the insufficient-balance message, byte-identical for a BUY
exceeding quote and a SELL exceeding base; and that **cancelling one leg of an OTO
collapses the whole list**, so §4b's cancel step is one call rather than three.

### The classifier, and the pass that made it coherent

Six families landed one per commit — class, branch and test together — on a rule
table introduced by a mechanical commit that changed no behaviour and was proved
so by the eleven existing translation tests passing untouched.

**The hierarchy pass is the part M5d will feel.** Decided one at a time, each
family was locally sound; seen together, two defects were visible that no single
diff contained. **Six of seven classified outcomes discarded the exchange's code
while the unclassified fallthrough kept it** — so the better we classified, the
less machine-readable identity survived. And **there was no way to catch "our bug"
as a class**, because `MalformedRequestError` and `ContractViolationError` had
`ExchangeError` as their nearest common ancestor. Both were fixed as one
principle: `ExchangeAPIError` means the exchange returned an error response and
carries its identifier, and every classified venue error descends from it.

**Three inherited classifications were found, all the same shape** — a value
placed by a commit that argued nothing, inheriting the intent of the container it
sat in: `-1111` inside `_ORDER_REJECT_CODES` from a commit whose entire message
is "phase 2"; the reject set's own membership; and
`InsufficientBalanceError`'s placement outside `OrderError`. What found all three
was asking one question per member rather than reading the collection.

### What the mutation discipline learned about itself

The reject-set mutation ran at 8, 11, 11, 11 and then, at the hierarchy pass,
predicted 18 and observed 14. **The reasoning was never wrong: the intended
variant gives exactly 18.** The anchor had been restructured, the harness
re-anchored a few lines lower — inside the rule loop rather than ahead of it —
and the prediction carried across unchanged.

So **a re-anchored mutation is a new mutation**, and **anchor drift is invisible to
a checksum by construction**, since both anchors produce a file that differs from
baseline. M5c-M's own remedy — assert the mutated md5 differs — proves that *a*
mutation applied, not that *the* mutation applied. Both rules are now in
`CLAUDE.md`, and this milestone's later proofs print their mutated line.

**A rule distilled from a finding can outrun it.** C4 marked an ancestry-only
assertion "documentation, not coverage" and wrote that it "pins nothing"; the
follow-on excluded it from a mutation's expected failure set on that basis and
observed three failures against two. It bit. An ancestry-only assertion is blind
to a *sideways* move and **not** to a move *out* of the base — weak, not inert —
and the docstring was corrected rather than left.

### The findings discipline, measured

**59 findings across 21 numbered commits, and every commit carried a block**,
including the two that carried `Findings: none`. That is the rule landed at
`8b7c688` surviving its own milestone end to end, against M5b having lost four
findings to exactly the gap it closes.

It is also a measurement of the mechanism rather than a fact about the milestone:
**59 is more than twice the flat scheme's entire remaining capacity when M5c
began.** The sequence exhausted twice — once at `ZZ`, discovered *at* exhaustion
with a ruling already written that could not be satisfied, and once in the `M5c-`
namespace, caught at 22 of 26 with three commits still to run. The difference
between those two is the whole value of the lesson.

### Do not tidy these

Four annotations read as untidy and are the record's value: `9c47858`'s corrected
claims; the flat-sequence ruling annotated as falsified by exhaustion; `M5c-B`,
annotated by `M5c-H` rather than amended; and `M5c-AO`'s docstring correction.
Each records a belief that was held, acted on, and then measured false. A log that
shows only the corrected view teaches nothing about how it was reached.


## Phase 5 M5d — the adapter surface, and one order to prove it

M5d built what M5c specified. Eleven numbered commits, **84 findings, every
commit carrying a block**, and one Testnet order placed and cancelled. The
milestone's headline is not the code — it is that **three of the eleven commits
exist because a measurement contradicted something already written**, twice
against code shipped one commit earlier.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `33ae65d` | `close()` routes through `_call`; the last method bypassing error translation |
| 2 | `4866719` | Site 3 characterised — the incoherent pair pinned as it behaves today |
| 3 | `51f0304` | Site 3 deferred with its obstacle named; the `~14s` annotated |
| 4 | `0c15377` | The `tb1-` ID scheme, and a guard the venue's own message cannot give |
| 5 | `c4bad0e` | OTOCO/OTO request types; the four `-1106` fields unrepresentable |
| 6 | `4f1b2bb` | Both parameter mappers, and a list-ID form §6 never defined |
| 7 | `43411d6` | Per-leg filter enforcement; all three prices rejected off-tick |
| 8 | `d646994` | The response mapper — **built on an assumed key** |
| 9 | `227d1f1` | That key measured wrong and fixed against a captured payload |
| 10 | `4df4565` | `create_otoco_order_list` / `create_oto_order_list` |
| 11 | `237256b` | `get_order_list` and the prefix enumeration helper |

Rotation: `3652e4a` (CLAUDE corrections), `f93bd85` (Q-C), `4ebbdd0` (`T_recon`,
alone), `ae2ee38` (the method rules), `62f89d1` (the counts, alone), `46da8ae`
(build state), `9f5ed54` (`NEXT_MILESTONE`), **and this commit** — seven
rotation commits, six with SHAs and one named as itself, because a commit cannot
know its own SHA before it exists.

### What measurement cost, and what it bought

**A probe falsified code shipped one commit earlier.** `d646994` read the
order-list leg array under `orderReports`, assumed from the general Binance
schema because *nothing in this repository had ever captured an order-list
payload*. Against the real read-back it mapped **zero legs from a three-leg
response, without raising** — and a test asserting the empty result **defended
the defect**, because its composed fixture omitted the leg array entirely and so
agreed with a wrong mapper on an input that could not tell them apart.

Two blindnesses, independently insufficient, agreeing on the wrong answer. That
is the shape worth carrying: either alone would have been caught by the other.

**The fix is scoped, not unified.** `orderReports` is a measured *absence* from
the read-back and an assumption about the placement response — and probe 2 later
measured that the placement response carries **both** arrays. So the original
assumption was right about one endpoint and wrong about the other, and refusing
to merge them was right for the right reason.

**One order settled the milestone's best open question.** A live OTOCO — working
leg `LIMIT`+`GTC` 25% below market, both pendings gated by OTO phase one —
showed `get_open_orders` returning **all three legs, pendings in `PENDING_NEW`**.
A recovery path asking *does anything rest* therefore sees protection that has
not activated. It also validated the whole chain: **15 of 16 parameters came
from our own mapper** and the venue accepted every one, honouring all four
generated IDs byte-for-byte. Balances identical before and after; one cancel
collapsed the list, verified per-leg rather than assumed.

**The claim it does NOT support is one sentence away.** What was measured is
`PENDING_NEW` *before* a fill. Q-C §7 describes pendings after the working leg
*fills*, and that transition is still unmeasured.

### The deferral, and why it is not the third repetition

Q-C §7's site-3 defect was scheduled for M5d and **deferred again** — but with
the obstacle named and dated rather than left implicit, which is what let it be
rescheduled twice before.

Closing it needs a trusted state a *coherently protected* position can hold. The
only trusted member is `ABSENT_BY_DESIGN`, which the fix must disqualify, and
the replacement is `ACTIVE` — a member `CLAUDE.md` forbids creating before a
writer exists. Attempting it anyway was measured: **0 of 16 `(protection, level)`
pairings would reach the pricing arm**, so `MAX_OPEN_POSITIONS`,
`ALREADY_IN_POSITION` and affordability would be shadowed portfolio-wide behind
`COMMITTED_RISK_UNKNOWN` **in production**, and `4926705`'s anti-rot test would
be retired.

The arming condition and the enabling condition are **the same event** — the
reconciler's milestone — which is why deferring costs nothing.

### What the method learned about itself

**Checking fixture expressiveness before predicting changed the tests, twice.**
A test cannot fail on a mutation its fixture cannot express, and that is a
property of the *input*, not the subject — so a test named for the very thing
being mutated abstains if its input already conforms. Both times, the check
produced a better test rather than merely a better prediction.

**A mutation anchor written against pre-format source is invalid**, because the
gate *rewrites* source. M5d's harness asserted the anchor count and aborted with
the tree restored, so the rule surfaced as a **refusal to run** rather than as a
confident wrong number explained afterwards. That is the one method change that
is mechanised rather than remembered.

**An agreement is evidence only when disagreement was possible.** The list-ID
suffix `-L` was chosen at commit 6 and had already been sent by M5c's probe. The
match is not confirmation: the second derivation could not have been
contradicted by the first, because it did not know of it.

**Two justifications went stale one commit apart**, both true when written and
both embedded where nothing re-checks their premise. A justification resting on
a distant invariant should name that invariant at its own site.

### Three of my own claims were wrong, and are on the record

The opening Phase 1 argued `get_open_orders` was *structurally blind to
`executedQty`*, reasoning from "returns open orders only" to "cannot carry
execution state". The returned objects carry it; §6's prefix argument was sound
and the objection was not. A mid-milestone finding then measured correctly that
the list read-back is the wrong endpoint and **priced the wrong replacement**,
proposing four calls per position where the answer is one per symbol — the
correction runs *cheaper*. And commit 11 called `get_order_list` "the only view
of a terminated list" when probe 1 had already measured two others.

All three are annotated rather than amended, per the rule that a finding later
found wrong is corrected in a subsequent block.

### The findings discipline, measured

**84 findings across 11 commits, every commit carrying a block**, no gaps and no
duplicates — verified from `git log` with an explicit range rather than from the
extractor, whose base is the previous milestone's last *numbered* commit and
therefore also returns that milestone's rotation commits.

**Finding IDs are allocated by SUBJECT, not chronology.** Commits 2 and 3 landed
together and their IDs interleave — `M5d-011` and `M5d-015`–`017` in one,
`M5d-008`–`010` and `M5d-012`–`014` in the other. The union is complete, but a
reader reconstructing chronology from IDs will get it wrong: **the log is the
only chronology.**

### Do not tidy these

The two-blindness test correction; the `orderReports` assumption being right for
one endpoint and wrong for another; the `T_recon` figure that was wrong in the
alarming direction before measurement made it cheaper; and the three annotated
claims of mine above. Each records a belief held, acted on, and then measured
false — which is what the log is for.


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

---

## Annotation — 2026-08-14, from M5e: the extraction procedure could not have worked

**Appended, not inserted.** M5d's entry is untouched. This file is written in the
tense a thing was decided, so editing a closed entry would erase the fact that
the belief was held — and the belief here was reasonable, which is the part worth
keeping.

**What is annotated, by content.** M5d's entry says *"84 findings across 11
commits, every commit carrying a block, no gaps and no duplicates — verified from
`git log` with an explicit range rather than from the extractor, whose base is
the previous milestone's last numbered commit and therefore also returns that
milestone's rotation commits."* And `CLAUDE.md`'s extraction procedure says *"It
prints nothing when no commit in the range carries a block … so an empty result
means 'not looked' as readily as 'no findings'."*

**The count claim is CORRECT and is not corrected here.** Re-measured over
`e2ecb80..237256b`: exactly 84 distinct IDs, `M5d-001` through `M5d-084`, no gap
and no duplicate. Scoped to the eleven numbered commits — which is how the
sentence scopes itself — it holds exactly.

Four things it did not say. Each measured at M5e, before any of M5e's own work.

**1. The failure mode is a plausible SUBSET, not an empty result.** Run today
exactly as written, the base resolves to `237256b` — M5d's *own* last numbered
commit — and the command reaches **8 of the milestone's 19 commits and 1 of its
85 declared blocks**. The output is well-formed: seven `Findings: none` lines and
one complete block. The procedure's stated hazard is an empty result that might
mean "not looked"; the actual hazard is a full-looking result that is missing
four fifths of the milestone, and nothing in it invites distrust.

**2. The base can NEVER be correct, and that is structural rather than a slip.**
The procedure asks for *"the previous milestone's closing SHA — the last row of
that milestone's commit table"*, and those are two different commits by
construction: **a commit cannot write its own SHA into its own table.** This file
already says so, in M5d's own rotation rule — the entry *"names the last one as
'this commit' rather than by SHA, because a commit cannot know its own SHA before
it exists."* So the table's last row necessarily *precedes* the closing commit.
Measured: for M5c the last row was `6502acf` against a closing SHA of `e2ecb80`,
**5 commits apart**; for M5d, `237256b` against `2378199`, **8 apart**. There is
no moment at which the lookup returns the commit the sentence names.

**3. Three IDs are unreachable at any range, for two distinct reasons.**
`M5d-086` exists only in a *document* body — `docs/NEXT_MILESTONE.md` — and in no
commit message, so the defect is the **source**, not the range, and no `A..B`
reaches it. `M5d-085` and `M5d-088` are in commit *bodies* but sit **ahead of the
`Findings:` line the awk begins printing at**, so the **print window** excludes
them even when the range is right. Two different holes, neither closed by fixing
the anchor.

**4. `M5d-085` and `M5d-088` are cited as authority and declared nowhere on
disk.** Both are invoked as settled findings — `f93bd85`: *"both were verified
present by content first, because a duplicate annotation is permanent
(M5d-085)"* and *"this milestone invalidated its own line numbers twice
(M5d-088)"*; `3652e4a`: *"per M5d-085: a duplicate annotation is permanent."*
**Both of those commits declare `Findings: none`.** Neither ID appears in any
`Findings:` block in the range, and neither appears anywhere in the tree. The
mandatory-`none` rule was satisfied and the finding was still lost, because the
declaration went into prose above the block.

**The two are NOT symmetric, and the asymmetry was checked rather than assumed.**
`M5d-088`'s substance survives as `CLAUDE.md`'s *"CITE A DOCUMENT BY CONTENT,
NEVER BY LINE NUMBER"*, with its measured evidence intact. `M5d-085`'s does not
appear anywhere: searched `CLAUDE.md`, every file under `docs/` and `README.md`
for *duplicate annotation*, *annotating twice*, *already annotated*, *verified
present*, *verify … present*, *present by content* and *annotate … twice* — zero
hits — then widened to bare *permanent* and bare *duplicate*, whose every hit is
about failure counters, refusals, divergence, `__all__`, `RiskRule` or the
order-list probe. So one citation points at a rule a reader can find, and the
other points at nothing. It is re-landed later in this same M5e block **from the
citation alone**; the original declaration is unrecoverable, the amend window
being closed (`git rev-list --left-right --count @{u}...HEAD` reads `0	0`).

**Ruled by the reviewer under delegation, not by the project owner.**
---

## Phase 5 M5e — the reconciler, and the trust it earned

M5e built the reconciler and then made the risk layer depend on it. **26
commits including this one — 22 numbered and four of rotation — and 95
findings, every commit carrying a block.** The milestone's headline is not any
component: it is that **the whole subsystem is inert**, and the first live
position will exercise seven of its parts against reality simultaneously.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `18b41be` | A finding count that matched no measurement, dropped |
| 2 | `8123ff6` | What M5d's entry could not have known, appended |
| 3 | `15ff98e` | The extraction anchor becomes a tag, and gains a second check |
| 4 | `4ddd16b` | The rule M5d cited and never wrote down, re-landed |
| 5 | `0d0266b` | The ID scheme this file prescribes has never been used |
| 6 | `497cc38` | The rotation checklist gains the tag it was told to rely on |
| 7 | `75bd7ae` | A cancel response names the order in `origClientOrderId` |
| 8 | `5b54f9e` | A per-call bound on transport time and attempt count |
| 9 | `53b3039` | Arming conditions name their caller, and four new items |
| 10 | `17ff858` | The two reads the reconciler and R13 need |
| 11 | `0ffde89` | Protection classified from what rests, purely |
| 12 | `e93300d` | The working leg is the entry, not protection |
| 13 | `22d3248` | The enumeration returns orders, not parsed pairs |
| 14 | `db3db37` | The reconciliation pass, and the port that lets it exist |
| 15 | `bfe92be` | An absent leg resolved by point query |
| 16 | `e382629` | The precedence fold made exhaustive, checked by mypy |
| 17 | `d4885c1` | The pass and the resolver take their budgets |
| 18 | `ab62861` | The driver, and the numbers it spends |
| 19 | `f51f5d4` | Reserve what the first unresolved position needs |
| 20 | `b11d208` | `ACTIVE` admitted to the trust whitelist |
| 21 | `8db6dd1` | An entry refused while the ledger is not current |
| 22 | `d0aecc3` | The method rules M5e earned, landed before rotation |

Four rotation commits follow: `4a5d34c` annotated the decided contracts,
`4d28a5d` wrote the current state and the counts, `470b47b` rewrote
`NEXT_MILESTONE.md` for M5f, and **this commit** is the entry. The count above
includes it, because a rotation that writes its count before its final commit
exists is off by one — the defect finding MM recorded, whose only real fix is to
count itself and name the last one in words.

### The whole subsystem is inert, and that is the milestone's finding

`grep -rn "Position(" src/` returns **one hit**: the class definition in
`core/models.py`. Nothing in `src/` constructs a `Position`. So **seven
components have never run against a real position** — `classify_protection`,
`resolve_unresolved_legs`, `reconcile_open_positions`, `ReconciliationDriver`,
the L-leg reservation, `ACTIVE`'s membership in `_TRUSTED_PROTECTION`, and
`RefusalStage.POSITION_STALE`.

Every one is pinned by tests over fabricated positions, and the tests are not
the weak part: they include mutation surveys with predicted failure sets, and
one measured trace of a livelock closing. **What nothing covers is the
composition.** The first position the executor opens is read by the driver on
the next candle, classified, possibly resolved, stamped or deliberately not
stamped, trusted or not, and priced or refused — seven decisions in sequence,
each individually pinned, none ever having run in series against a venue.

This is stated as a **risk carried into M5f**, not as a defect. Building the
reconciler before the first order was correct and remains correct: with only
untrusted protection states, the first position opened would have refused every
entry after it, portfolio-wide. The cost of that ordering is precisely this —
that the safety machinery is unexercised at the moment it first matters.

### What was decided

**The reservation reserves what the first unresolved position needs, not one
call.** Reserving a single call left a livelock: resolution is all-or-nothing,
so one reserved call re-queries the same first leg forever, a two-leg position
never completes, never gets stamped, sorts first forever, and the healthy
positions behind it are never read. Measured, then closed, then measured again
— the fix was traced cycle by cycle against the real functions before it was
written, and the trace is in `NEXT_MILESTONE.md` item 13. **The closure is
scoped to `max_calls >= L + 1`**, which is arithmetic rather than a weakness:
completing an `L`-leg position costs one enumeration plus `L` queries.

**`ACTIVE` was admitted to `_TRUSTED_PROTECTION`, and it is the one member that
may be.** Every other state is trusted or not on the strength of what nobody
checked; `ACTIVE` is returned only when every requested leg was found resting at
the venue, at its trigger, for the quantity, under the list id, with nothing
executed. It is the only member whose truth is measured. What it unblocks is
trading, not a defect — left untrusted, a correctly protected position refuses
every entry portfolio-wide.

**The executor must construct every `Position` with `ProtectionState.UNKNOWN`.**
A constraint on a caller that does not exist, ruled so that the reserved
question about `last_reconciled_at is None` collapses: unstamped implies
`UNKNOWN` implies untrusted implies uncomputable, so all three readings coincide
and the choice becomes a label. It also keeps stamping-at-construction adoptable
later, where the opposite ruling would have required a measurement that requires
a dispatch.

**`RefusalStage.POSITION_STALE` refuses while the ledger is not current**, ahead
of the committed-risk guard because it names the cause where that names the
consequence. It is **ungated by `stop_loss.enabled`** where its neighbour is
gated, and that is the milestone's only behaviour change: the opt-out is about
committed risk, while staleness is about whether `has_position` describes
reality.

### What was rejected

**Reserving one call unconditionally** — free-looking, and it produced the
livelock. **Reserving for every unresolved position** — it shrinks the pass
until it reads almost nothing; completing them one at a time is what makes
progress monotone. **Stamping at construction** — honest only if the executor
observes venue state, which needs `orderReports`, whose shape is UNMEASURED and
whose measurement needs a dispatch. **Gating staleness on `stop_loss.enabled`**
— consistent with its neighbour, and wrong, because a `CLOSE`-owning operator
still needs `has_position` correct. **A driver that remembers position state** —
it becomes a second source of truth for a fact the position already owns, and
refusing it is what blocks Q-B site 4's N-cycle counter.

### Three things the method itself learned

**A mutation must be verified to MEAN what its name says.** A mutation named
"the guard placed after `committed_risk`" was applied by emptying the guard's
input. A guard whose input is emptied never fires; a guard moved later fires
later. Every mechanical safeguard passed — the anchor matched once, the checksum
changed, the content printed — and the experiment was still not the one
predicted.

**Mechanising an enumeration makes it auditable, not correct.** An AST pass over
the test modules missed four tests and invented one. It was still worth writing:
a tool that is wrong legibly can be corrected, while eyeballing is wrong
invisibly.

**A prediction made before the tests exist is invalidated by writing them.**
Two consecutive commits missed for that cause before it was named. Predict at
report time, re-derive at the green baseline, and let the re-derivation bind.

### The extraction procedure's first live use, and how it was checked

This rotation is the first to run the tag-anchored extractor K3 rebuilt. It
reached **22 of 22** commits, all carrying blocks, and the cited-but-not-declared
cross-check returned empty.

**Neither of those alone would establish anything, and the composition is the
point.** `M5e-001` measured that the predecessor could return a *well-formed
subset* with nothing signalling distrust — so a plausible output needs a check
that could have distinguished it.

- **ID density** — the declared identifiers ran `001` to the maximum with **no
  gaps** — rules out a missed *middle* commit, since a skipped block takes its
  identifiers with it.
- **Header parity** — commits emitting a header equalled commits in range,
  cross-checked against `git rev-list --count` — rules out a truncated *tail*,
  which would read as perfectly dense with a lower maximum.

Density alone is blind to truncation; parity alone is blind to a hole. Together
they close both, and that is why both are recorded.

The cross-check's empty result is a **pass rather than a vacuum**: thirteen
identifiers are cited in commit prose outside any block in this range, so the
diff had real input and found every one of them declared. A second run against
`docs/`, `CLAUDE.md` and `README.md` found no identifier living only in a
document body — `M5d-086`'s class did not recur.

**What none of it catches** is a rule stated with no identifier at all. One
reached this milestone that way, carried by memory rather than by the queue.

### The historical figures in this entry

**26 commits, 95 findings, and the gate at `470b47b` — `ruff check` clean, 92
files formatted, mypy clean over 62 source files, 1046 passed credentialed.**
These are HISTORICAL and must never move, exactly like the `4926705`-pinned trio
in `CLAUDE.md`. A later rotation grepping the digits will meet them; they are
facts about this milestone's close, not counts to update.

**Ruled by the reviewer under delegation, not by the project owner.**

---

## Phase 5 M5f — the executor, and the risk it did not retire

M5f built the first code path in `src/` that places an order. **26 commits
including this one — 19 numbered and seven of rotation — and 106 findings,
every commit carrying a block.** The milestone's headline is not the executor.
It is that **M5f made the composition risk REACHABLE without retiring it**: the
older premise — nothing constructs a `Position` — is now false, while its
conclusion holds unchanged, because nothing has RUN.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `3407b91` | An intent mapped to the placement shape it needs |
| 2 | `7aa8f59` | The three-call `CLOSE` annotated, which counts steps as calls |
| 3 | `cd7348a` | A dispatch sequence bounded by deadline, not call count |
| 4 | `0c43b32` | Two `src/` docstrings that outlived their facts |
| 5 | `276e1ee` | The boot reads balances once and shares the snapshot |
| 6 | `03eccac` | The socket source closed if the stream constructor raises |
| 7 | `0500e52` | Two more `src/` docstrings that outlived their facts |
| 8 | `dce6165` | `cov` and `format` routed through `$(PYTHON)` |
| 9 | `3438180` | A placement whose outcome we did not see, resolved |
| 10 | `ae34b59` | M5f's state written into the tree before the context cleared |
| 11 | `cc1feb5` | A dispatch refused whose symbol filters were never primed |
| 12 | `8ca878e` | The executor, and the first code path that places an order |
| 13 | `16857e3` | The executor's log lines say which outcome they are |
| 14 | `0c10a38` | The position a resolved placement proves exists, recorded |
| 15 | `b5cadea` | A missed dispatch is not a successful resolution |
| 16 | `eb8ffe9` | The window probe landed, and a figure that answered an open question |
| 17 | `418409f` | The venue code carried on the three routes that hold one |
| 18 | `bc3d42e` | A marker distinguishing a client-side refusal from a venue response |
| 19 | `59cf256` | A refusal that sent nothing has nothing to resolve |

Seven rotation commits follow: `a28a464`, `107178f`, `954bb0e` (amended from
`c8fe7a4`), `bdf12c4`, `ef215bc`, `f52f161`, and **this commit**, which cannot
name its own SHA.

### The milestone's finding: the risk grew

M5e's entry recorded that the whole reconciliation subsystem was inert and that
the first live position would exercise seven of its parts at once. M5f made
that reachable and added four more parts to it — `build_placement`,
`DispatchBudget`, `resolve_placement`, and the executor's own dispatch,
position construction and Option-4 resolution.

**Nothing has run any of it.** Every component is pinned by tests over
fabricated inputs, and what remains uncovered is their composition — which no
test can retire, because a test composing them would be composing fakes, and
that already exists.

### What was decided

**The project owner ruled four things**, and they are his rather than the
reviewer's: that the resolver lands in its own isolated commit; that the
non-filling limit test be executed to establish venue write validity; that the
recovery is **fail-closed on `UNRESOLVED`**; and that e3-narrow ships at full
scope, so a client-side refusal creates no pending record. He also approved the
`CLAUDE.md` annotation text landed at `107178f`.

**The reviewer ruled, under delegation:** that `PendingPlacement` carries the
requested economics (R23); that the `PLACED_LIVE` branch does what the success
path does, including the debit (R24); that `NOT_PLACED` is untouched pending
his ruling (R25); that `entry_bar_time` is forwarded from the candle rather
than taken from `Signal.timestamp`; that the two dispatch-site refusals live at
dispatch rather than at config load; and that the client-side marker takes the
D-prime shape rather than F, because F may require port surface the reviewer
cannot authorise.

**Measured against a venue, read-only and write, on Testnet.** Six OTOCO
placements timed at 452.4, 471.2, 182.6, 181.7, 451.8 and 454.1 ms against
`allOrderList` reads at 189.9, 459.9, 450.1, 184.1, 182.3 and 196.3 ms — the
same bimodal shape, so **a placement costs what a read costs**. `orderReports`
was found present in the placement response carrying Q-C section 7's whole
compare set. And the enumeration window **discards its oldest entries**, which
bounds the resolver's exposure by direction rather than by headroom.

### What was rejected

A boot-time refusal of the unprotected configuration, dropped by the owner
after the reviewer's own halt found six tests asserting that configuration is
reachable — two of them declaring it locked. Retaining a failure classification
on `PendingPlacement`, held rather than ruled, because e3-narrow delivers its
purpose by recording less. And a mixin on the existing exception classes, which
is unimplementable: the same class arrives from both sides.

### DO NOT TIDY THESE — beliefs held, acted on, and then measured false

Each was reasonable when held, and the record of holding it is the point.

- **The three-call `CLOSE`.** Six documents and one constant asserted it.
  Measured worst cases are OTOCO 5, OTO 4, unprotected 1, recovery-bearing
  entry 3 — the claim counted Q-C section 4b's three STEPS as three CALLS.
- **The resolution path was believed complete.** It deleted its pending record
  on every outcome and acted on none of them, so a placement confirmed to have
  LANDED left a live list with no `Position` and no debit — unbounded, because
  nothing retried. Found while drafting an annotation about the branch beside
  it.
- **"The classifier breaks a contract its own docstring publishes."** The
  `:param` line reads that way; the paragraph directly above it explicitly
  weakens the guarantee. Half a docstring was quoted in a report whose whole
  purpose was to decide whether that field could be relied on.
- **"`MAX_NUM_ORDER_LISTS` headroom is now 6 of 20."** It subtracted a query's
  result from an open-list ceiling, and in doing so silently answered a
  question this project's own open items forbid answering.
- **The five pre-dispatch families were assumed separable by type.** Three of
  them share a class with venue refusals, so a type-based split would have
  marked a venue refusal as never-sent — the one error direction the ruling
  forbade.

### Three things the method itself learned

**A mutation that fails nothing is a hole in the code, not an uninteresting
result.** Two of them found genuinely unpinned sites this milestone, and a
third — predicted as a zero and confirmed — showed a guard redundant with its
own defensive branch.

**A crash is not a zero.** One mutation produced an MRO conflict, nothing
collected, and the harness read zero failures against a prediction of one. The
harness now flags a missing pytest summary as INVALID rather than recording it.

**A check in the same command chain as the action it gates is not a gate.** A
commit message's ASCII verification printed its verdict and then ran `git
commit` in the same chain, so the number arrived alongside a commit that
already existed. Distinct from the pipe rule: there the verdict cannot be read;
here it was read, too late.

### The historical figures in this entry

**26 commits, 106 findings, and the gate at this commit's parent `f52f161` —
`ruff check` clean, 99 files formatted, mypy clean over 65 source files, 1168
passed credentialed.** These are HISTORICAL and must never move, exactly like
the `470b47b` and `4926705` figures above. A later rotation grepping the digits
will meet them; they are facts about this milestone's close, not counts to
update.

**Ruled by the reviewer under delegation, except where the project owner is
named above.**

---

## Phase 5 M5g — the milestone that ran the bot, and found what running costs

M5g was scoped as one supervised Testnet run. It became **four runs, a defect
hunt, three operator scripts and a rotation that had to be suspended
mid-flight.** **21 commits including this one — 17 numbered and four of
rotation — and 144 findings, every commit carrying a block.** The milestone's
headline is not that the bot ran. It is that **running it revealed a defect
1184 passing tests and a strict type gate could not see, and then a second one
that no test could ever have seen**: the venue closed a position and the ledger
did not notice.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `47039f5` | The read-only probe answers the account precondition |
| 2 | `f2fb5bd` | Whether any candidate pair escapes the holding refusal |
| 3 | `00d527c` | `equity`'s docstring omitted a term its body sums |
| 4 | `c6acdfc` | `MARKET_LOT_SIZE` measured, which decides a one-pass clear |
| 5 | `48bfcba` | A Testnet-only clearer, with its guards under test |
| 6 | `50691b3` | The configuration of the first supervised run, committed |
| 7 | `3970968` | **D2**: protection classified from the leg's own id |
| 8 | `28a151b` | A parser for the list-level client order id |
| 9 | `b81eb1c` | **B2 and V2**: a symbol whose own order list still works |
| 10 | `041d54c` | **D1 and D5**: one instance per checkout, a PID per record |
| 11 | `f6af2b0` | A Testnet-only canceller, built cold against a clean account |
| 12 | `92c59d6` | What the second run measured, and what it falsified |
| 13 | `1d299a6` | `TradingEngine.stop` is idempotent, where only `start` was |
| 14 | `ffdfcf0` | The lifecycle family's last guard, and the count it moves |
| 15 | `7f8db8d` | The excluded-holdings flood collapsed to one summary line |
| 16 | `3d96495` | The cut-off inventory: four runs, not one |
| 17 | `ae4eb43` | The exit-price measurement armed where the exit is seen |

Rotation: `c304b5d` (step A, the canceller's falsified coverage claim),
`8f1cb1a` (step C, `CLAUDE.md` and `README.md`), `4f08741` (step D,
`NEXT_MILESTONE` rewritten for M5h), **and this commit**, which records the
milestone. **Step B — the contracts re-read — was measured and produced no
commit**, which is the correct outcome for a step whose targets were all
already annotated.

### The four runs, and the two that were nearly lost

The bot ran four times. **Two of them happened between sessions and no report
in the milestone knew of them** until a rotation step enumerated the log's pids
and got three where it expected one. Their entire record was
`logs/trading_bot.log`, which is gitignored, and the rotation would otherwise
have sealed them out of the milestone.

That is a fifth drift surface, and it is worse than the four already recorded:
those hold **stale claims**, which a reader can disagree with. This one holds
**no claim at all**. The failure is silence rather than error.

### D2 — the defect that made the bot single-shot

`classify_protection` compared the venue's numeric `orderListId` against our
derived `tb1-` client order id. Both operands are `str | None`, so **mypy
strict cannot see it and 1184 tests passed over it.** Every correctly protected
position read `DIVERGED`, which is untrusted, which makes committed risk
uncomputable, which refuses every entry portfolio-wide. The bot could open one
position and never a second.

Only a live run surfaced it, and only because the reconciler reported on
protection that was demonstrably correct. Fixed at `3970968` by comparing the
leg's own client id to the one `client_order_id()` derives, and confirmed over
**81 consecutive passes reading `active=1`** against the first run's 28
consecutive `diverged=1`.

The fixtures were the accomplice: one constant, `LIST_ID = "91590"`, supplied
both the venue value and the requested id across three test modules. **A test
cannot fail on a mutation its input cannot express.** They now use visibly
different shapes per identifier space.

### What else the runs confirmed

**B2 and V2** (`b81eb1c`): a live order list of ours on an enabled symbol
blocks that symbol at boot under `RefusalStage.LIVE_ORDER_LIST`, and if every
enabled symbol is blocked the boot exits rather than idling. Run 4 emitted
nothing from the scan, which is the pass condition — and, recorded honestly, is
a near-vacuous confirmation: on an account with no live lists the loop
`continue`s before the parser, so no input could have produced a different
result.

**D1 and D5** (`041d54c`): an OS-level instance lock acquired before the client
is constructed, and `pid=` on every record. The lock has no success log line, so
the file's PID bytes are its only proof — and it is a single slot with no
history, so the measurement had to be taken live or not at all.

**The excluded-holdings collapse** (`7f8db8d`): run 2 put 501 identical warnings
into a 609-line log — 82.3% of the run, and 501 of its 503 WARNING lines — so a
B2 block line would have sat among them at an adjacent level. Run 4 booted under
the collapsed code and logged **one** line carrying `excluded_count=501`, with a
total WARNING count of 1.

**Nine of eleven carried-risk components have now run.** `resolve_placement` and
`RefusalStage.POSITION_STALE` have not, after four runs, and neither is armed by
a caller: one needs an ambiguous placement, the other needs the reconciliation
pass to stop running.

> **ANNOTATED at M5j.** `resolve_placement` HAS run, and it ran before this
> entry was written: `placement_ambiguous` at `2026-08-27 04:06:02`, then
> `placement_resolved outcome=placed_live` a minute later. It reads as
> unobserved here because the lines carry no `pid=` field — that field begins at
> `2026-08-27 17:10:37`, and the M5g window opens some 35 hours earlier, so no
> pid census can enumerate this milestone's runs. **"Four runs" is therefore
> UNMEASURED rather than wrong**, in either direction, and "the bot ran four
> times" elsewhere in this entry inherits the same limit.
> `RefusalStage.POSITION_STALE` has still not fired. See `docs/RUN_LEDGER.md`.

### The headline, and it is a thing M5g did NOT do

**Run 3 took the project's first complete trade. The venue triggered the
stop-loss. The account realised `-35.38691640` USDT, and nothing in `src/`
booked it.**

- `Portfolio.record_realised_pnl` has **exactly one call site**, inside
  `Portfolio.close_position`.
- `Portfolio.close_position` has **zero callers**.
- So the credit, the deletion and the accrual are all unreachable. **The ledger
  can be opened and never closed.**
- `realised_today` therefore returns `Decimal(0)` permanently, and the
  daily-loss check's realised term is structurally dead. **It is a
  committed-risk limit wearing a daily-loss limit's name.**

The reconciler saw it on nine consecutive passes and did the only thing it
knows: classified `UNKNOWN`, logged, and refused further entries. The bot halted
— by the wrong mechanism, for a wrong stated reason, and only in-process.
**A restart heals the balance sheet and erases the income statement**: equity is
re-read from the venue at boot, realised P&L is not, because nothing ever wrote
it. Run 4 proved it by booting with the post-loss balance and no knowledge a
trade had occurred.

The same gap swallows a take-profit fill and a manual exit at the venue.
M5h's scope — persistence, then exit booking, then `CLOSE` — was ruled by the
project owner on this evidence, and the ordering is forced: booking without
persistence yields a halt that resets on restart and *looks* like a control.

### The process record

**The heredoc rule failed twice more after being written into the tree.** The
section recording it diagnosed three earlier failures as the `phase_5_` shape —
the instruction *"had lived only in prompts"* — which implies that writing it
down would end them. It was written down. `M5g-046` is the fourth and the first
where damage **landed**: a Python heredoc wrote 1148 and 476 CR bytes into two
LF-pinned fixture files, and **`git diff` hid it** because the index normalises.
`M5g-106` is the fifth, in a task whose own prompt forbade heredocs in capitals.
The rule was deliberately not restated a sixth time; what was recorded instead
is the evidence about the remedy.

**The rescue sweep found four rules living only in `NEXT_MILESTONE.md`** — the
finding-ID scheme, the milestone-paragraph re-tensing convention, `M5f-091` and
`M5f-094` — where the rotation expected two. The extra two were found only
because the audit looked for the general case rather than for named items, and
step D's rewrite would have destroyed them.

**And the instrument used to check for missing rules itself failed**, in the
direction that manufactures work: two case-sensitive `grep -F` calls reported
rules absent from `CLAUDE.md` that were present, one in capitals and one under
different wording.

### Two mislabelled observables, recorded because both are still live

**`reconciliation_pass`'s `queries=` field reports budget HEADROOM, not work
done.** It is `max_calls - len(assessments)`, constant at 2 across every pass of
both runs. In run 2 it read 2 while **zero** queries were made; in run 3 it read
2 while **exactly two** were made. A field that is accidentally correct is more
dangerous than one plainly wrong, because inspection cannot catch it.

**The log records no fill price and no balance.** `order_placed` logs the LIMIT
that was sent, never the fill. Run 3's realised loss is derivable only from two
console readings taken by hand — the bot's own record cannot answer *"what did I
pay?"*.

### The historical figures in this entry

**21 commits, 144 findings, and the gate at this commit's parent `4f08741` —
`ruff check` clean, 105 files formatted, mypy clean over 68 source files, 1273
passed credentialed.** These are HISTORICAL and must never move, exactly like
the `f52f161`, `470b47b` and `4926705` figures above. A later rotation grepping
the digits will meet them; they are facts about this milestone's close, not
counts to update.

**M5h's scope was ruled by the project owner. Everything else here was ruled by
the reviewer under delegation.**

## Phase 5 M5h — the milestone that closed the ledger

M5g ended on a sentence: *"a restart heals the balance sheet and erases the
income statement."* M5h was scoped to make that false. **53 commits including
this one — 52 numbered and one of rotation — and 375 findings, every commit
carrying a block.** The headline is that the income statement now survives a
restart. The thing worth carrying forward is narrower and less comfortable:
**almost every path built here has never run against a venue**, and the
milestone added more of them than it retired.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `4604b25` | Correct two stale counts -- the M5g namespace and the stage table |
| 2 | `aaa5c2c` | The M5h survey -- what five read-only tasks measured |
| 3 | `956d8d4` | Run 5, the account after it, and six findings restated |
| 4 | `c5e54ce` | A read-only probe that asks X1 of both legs, not one |
| 5 | `c60d38b` | X1 answered, and the decomposition that corrects M5h-039 |
| 6 | `785cfc5` | Rewrite two stubs that promise SQLAlchemy |
| 7 | `5db4921` | A crash-survivable store for what the venue cannot answer |
| 8 | `75d2282` | The wiring that is blocked, and three rulings for it |
| 9 | `79bf4ed` | Pin that the two pending types carry the same fields |
| 10 | `f21ccaa` | An extractor that cannot see prose, and a check that counts |
| 11 | `ae0687b` | What the extractor could not see, and what it never counted |
| 12 | `864259a` | Four lifecycles recovered, and an account that reconciles to zero |
| 13 | `6ad9162` | Wire the pending record, with the root as sole owner |
| 14 | `7642655` | The store gains a reader, and a corrupt one refuses the boot |
| 15 | `7c0c95f` | A duplicate symbol is corruption, and a docstring catches up |
| 16 | `bd0c1e7` | The domain carries the venue's own quote total |
| 17 | `1163111` | The deletion goes last, so a failed accrual can be retried |
| 18 | `01b4844` | The ledger becomes one value, so a total cannot outrun its day |
| 19 | `2e23ce3` | The ledger is restored at boot, and its reader finally exists |
| 20 | `36193ca` | A position records the price it actually filled at |
| 21 | `8aa66eb` | The working leg's fill price is queried at open |
| 22 | `31fc12d` | Debit what the venue charged, not what we asked for |
| 23 | `c33013a` | An expired entry leg opens no position and moves no money |
| 24 | `b911ce0` | A protective fill is carried back, not discarded |
| 25 | `e26a304` | The root gains a second writer, for the ledger |
| 26 | `8744b52` | An exit's worth arrives as a total, not as a quotient |
| 27 | `4abab15` | A venue fill reaches the ledger, for the first time |
| 28 | `9588502` | A discretionary close sell becomes addressable by name |
| 29 | `a1567cf` | A pending close becomes representable, in one keyspace |
| 30 | `9845aba` | Q-C section 4b's confirming query becomes a pure decision |
| 31 | `f6ec6d1` | The close is four calls, and there is no per-call share |
| 32 | `3ef95b7` | A CLOSE is planned and reported, and still refused |
| 33 | `bae0163` | A position carries the venue's list id, and says which is which |
| 34 | `ac6d3e2` | A CLOSE cancels, confirms, sells and books |
| 35 | `919a18b` | A pending write carries the live ledger, not a boot snapshot |
| 36 | `89aac10` | Every timestamp is UTC, and now says so |
| 37 | `b7f1624` | The store can hold a day's history and a lifetime total |
| 38 | `db601be` | The day roll preserves the day it overwrites |
| 39 | `e1083bf` | The root carries the day history in both directions |
| 40 | `7b9be6b` | The pending-close skip is reachable, and correct |
| 41 | `fbe25df` | A mutation survey that proves WHICH mutation ran |
| 42 | `c820030` | Count the ABC stand-ins mypy cannot see |
| 43 | `3909a7e` | The survey read log lines as collection errors |
| 44 | `27b65b9` | The boot gate sees a pending record, not only a blocked one |
| 45 | `22e2304` | The boot refusal is for a pending CLOSE, not any pending record |
| 46 | `3452360` | A restored close is resolved, reported and let go |
| 47 | `b3e5dc7` | An unconfirmed close keeps its position and stops entries |
| 48 | `a11ed7a` | Untracked inventory is the third thing that stops a symbol |
| 49 | `21ad51e` | The survey decoded pytest output with the console codepage |
| 50 | `d77cd60` | The transport timeout is pinned inside the dispatch deadline |
| 51 | `cf6c807` | An unconfirmed close sell is retained, not declared failed |
| 52 | `ff9cc66` | A resolved close is booked when the position is in memory |

Rotation: **this commit**, which records the milestone, carries the gate counts
to all four sites, rewrites `NEXT_MILESTONE.md` for M5i, and annotates Q-C §4b
and Q-B — one rotation commit rather than M5g's four, because the milestone's
`src/` work was already settled when it began.

### What was built, and why in that order

**Persistence first, because nothing else could be trusted without it.** A
crash-survivable store landed before any consumer: a reader that refuses a
corrupt file at boot rather than starting on a guess, one keyspace shared by the
pending placement and the pending close, and the ledger carried out and back with
a day's history and a lifetime total. The order was forced — booking an exit into
a ledger that could not survive a restart would have produced a figure that
looked right until the next boot.

**Then the exit booking.** `Portfolio.close_position` had exactly zero callers at
M5g's close and `record_realised_pnl` had exactly one call site, inside it — so
the accrual path was structurally dead. It now has **three** live producers: a
venue-triggered protective fill carried back through reconciliation, the bot's
own `CLOSE` sequence, and a close confirmed a bar after an ambiguous dispatch.

**Then `SignalAction.CLOSE`.** Q-C §4b's cancel → confirm → sell, built as
specified: one cancel collapses the list, the confirming query re-reads per leg
because it must see a leg that filled *during* the cancel, and the sell is
`MARKET` under a derivable close id so a timed-out sell is resolvable by asking.

### The decisions, and the alternatives rejected

**An exit's worth arrives as the venue's own quote total, never a quotient.**
Rejected: deriving it from `average_price × quantity`, which is the smallest
change and reintroduces exactly the error the exchange's own accounting does not
have. `CLAUDE.md` already recorded a stop booked at its trigger under-reporting
137.36 of 241.15 USDT; the domain gained `filled_quote_quantity` rather than a
multiplication.

**A partial fill books nothing and fails closed.** Rejected: booking the partial.
`close_position` deletes the whole entry and credits one total, so there is no way
to express "0.3 of 0.5 sold" — booking it would delete a position whose base is
still at the venue. The residual is named rather than hidden: `Position.quantity`
is then overstated and this design cannot correct it.

**A timed-out sell RETAINS its record rather than declaring failure.** Rejected:
the previous behaviour, which released the record and told an operator to sell
the base by hand. That instruction is destructive when the sell may already have
filled. The predicate is deliberately WIDE — `ClientRefusalError` releases,
everything else retains — because retention is single-shot and over-retaining
costs one query, while under-retaining discards the only handle on a position
that may be live. Rejected as unavailable: a precise predicate, because
`ExchangeAPIError` is produced both by a venue rejection and by an unreadable
2xx, and no type separates them.

**A confirmed fill is BOOKED when the position is still in memory, reversing a
C5c ruling.** R2 said the resolution books nothing. Its grounds were that after a
restart there is no `Position` and the record carries no `entry_price`, so the
figure was *unreconstructable* — an engineering constraint, not a policy of
forfeiting valid accounting. In process both are present. The restart case is
unchanged, and `_drop_position_unbooked`'s docstring was rewritten rather than
left asserting a reason that had become false.

**The transport timeout is documented and pinned, not clamped.** Rejected:
shortening it to fit the deadline — which would make the abandoned-but-landed
case *more* likely, not less, since nothing cancels an in-flight request.

### What measurement overturned

**The `MARKET` sell is the only unbounded venue write in `src/`, and the cause is
the PORT.** `ExchangeClient.create_order` takes a request and nothing else where
the adapter accepts `timeout_s` and `attempts`, so the sell cannot be handed the
budget its own call site computes. Three of four venue-writing call sites pass
bounds; the fourth is the write.

**The `43.5 s` figure carried through this milestone reproduces arithmetically
and measures the wrong path.** `4 × 10.0 + 3.5` is correct for four consecutive
rate limits. On a write, retries are narrowed to `RateLimitError`, and a
connection timeout is `ExchangeConnectionError` — so it takes **one** attempt and
the real bound is `10.0 s` against `D = 9.0`. The mismatch survives any reduction
in `retry_attempts`, which the 43.5 framing would have hidden: anyone "fixing" it
by cutting retries would have left it intact with a 4.3× smaller number to show.

**A per-request `aiohttp` timeout REPLACES the session default rather than
overlaying it**, so the library's `sock_connect=30` is discarded and the bare
number becomes the only bound — safe at 10 only because 10 is stricter than the
30 it displaced.

### The method findings — three, and they are the milestone's durable output

They are stated in full in `CLAUDE.md`; recorded here as what was learned and
when.

**Reasoning from what a thing is FOR rather than what it REACHES** cost four
wrong predictions, each a plausible inference from purpose. The narrowing that
makes it checkable: *when a call site is constrained, the constraint lives in the
type it calls through.* It also **worked** once applied — B1's U1 was traced from
6 to 5 before running, by asking whether a fixture could express the mutation
rather than whether its name matched.

**A string enumerator cannot read assertion polarity**, so a test proving a
dangerous sentence is *absent* scores as pinning it present. Measured at
`22e2304`: the AST set over-counts by reaching guards sharing an exception, the
string set over-counts by ignoring polarity, and `B ⊆ A` was a fact about the
tree that day rather than a property of either instrument.

**A tool's output is evidence only where a prediction made it falsifiable.** Four
instrument defects were corrected and **not one was found by reading the tool** —
each was found because a prediction disagreed with what the tool reported. Three
err in the same direction, and it is the expensive one: **a false abstention
reports tests as blind when they bit.**

### What did NOT happen, stated as plainly as what did

**Nothing ran.** No supervised run took place in M5h; the four runs this entry
reasons about are M5g's. So the close path, the booking, the retention and the
resolution are exercised by fabricated fixtures only, and the composition risk is
**larger** at this close than at the last.

Three venue facts remain unobserved after ~25 trades and 33 closes: **no
take-profit has ever filled**, `ALREADY_CLOSED` and `HALT` have never occurred in
a real close, and `resolve_placement` has never run. Each is a branch reachable
only through a fixture, on a path where a fixture models the venue rather than
observing it.

> **ANNOTATED at M5j, and the two paragraphs above are wrong in different ways.**
>
> **"Nothing ran" is FALSE.** MEASURED over a frozen capture of
> `logs/trading_bot.log`: **12 substantial runs fall in the M5h window**, and
> the close path this milestone built ran in production **27 times before M5h
> closed**, first at `2026-09-06 06:15:03`. So "the close path, the booking, the
> retention and the resolution are exercised by fabricated fixtures only" is
> false of this close, and the composition claim that rests on it does not hold
> in the form stated.
>
> **Of the three venue facts, two were true here and one was not.** No
> take-profit had ever filled — true then and true now. `ALREADY_CLOSED` and
> `HALT` had never occurred — **true at this close**, since `ALREADY_CLOSED`
> first occurred on `2026-09-15T23:38:02Z`, three days later.
> **`resolve_placement` had run**, on 2026-08-27, before this close.
>
> **"~25 trades and 33 closes" is UNMEASURED** — its instrument is unstated. The
> log's nearest equivalents at this close are **47 placements and 30 closes**,
> of which 27 were the bot's own CLOSE sequence and 3 were venue-triggered
> protective fills. See `docs/RUN_LEDGER.md`.

**One defect is left standing deliberately and is M5i's highest-value item.**
`_resolve_close` computes its log's `outcome` in the `try` and performs the
booking in the `finally`, so a `CRITICAL` can report `filled_and_booked` while
nothing was booked — measured, mutation V2 killed four tests on the ledger and
none on the label. It is a false marker on a line that now tells an operator
*not* to enter the trade by hand.

### The historical figures in this entry

**53 commits, 375 findings, and the gate at this commit's parent `ff9cc66` —
`ruff check` clean, 114 files formatted, mypy clean over 73 source files, 1585
passed with 1 skipped, credentialed.** These are HISTORICAL and must never move,
exactly like the `f52f161`, `470b47b`, `4926705` and `4f08741` figures above. A
later rotation grepping the digits will meet them; they are facts about this
milestone's close, not counts to update.

**M5h's scope and rulings 1–5 were ruled by the project owner. Everything else
here was ruled by the reviewer under delegation.**

---

## Phase 5 M5i — one criterion, one label, and a harness that means what it says

M5h ended having built a close path nothing had exercised. M5i was scoped to
retire the debts that path had accumulated rather than to add to it. **16
commits including this one — 15 numbered and one of rotation — and 130 findings
declared across `M5i-001`–`M5i-136`, every commit carrying a block.** The
headline is that three copies of one criterion became one, and that a CRITICAL
can no longer claim a booking that did not happen. The thing worth carrying
forward is the same sentence M5h closed on, and it has got worse rather than
better: **nothing has run, and this milestone added two more emitters to paths
no venue has ever exercised.**

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `2a9d454` | The close-resolution line's three fields become one value |
| 2 | `743fb86` | Three docstrings that denied what the code now does |
| 3 | `24d0a7c` | A position with no cost basis is released, not booked |
| 4 | `13d96c5` | A completed sell with no cost basis is dropped, not held |
| 5 | `539f9b2` | The close-resolution label follows the write, not the plan |
| 6 | `61919ce` | Pin the booking ladder's order before (ii) reorders it |
| 7 | `08bb4b6` | One bookability predicate, with no callers yet |
| 8 | `0d90730` | An unparseable mutant aborts the survey, never abstains |
| 9 | `6669b6f` | The bookability criterion now exists once |
| 10 | `8a751cc` | The unconfirmed close no longer claims nothing was sold |
| 11 | `58db482` | A complete fill the venue never priced is not a partial |
| 12 | `0835213` | The mutation survey refuses a piped stdout |
| 13 | `d2a9cf3` | The survey tells a kill from a crash, and proves it |
| 14 | `08711a7` | The gate stops recommending a remedy it refuses |
| 15 | `812f9b2` | Two comments that outlived what they described |

One rotation commit follows: **this commit**, which writes the gate counts from
one fresh run, records nine method rules, re-baselines
`docs/NEXT_MILESTONE.md` for M5j and adds this entry.

### What M5i did

**`M5h-371` is closed, and the fix was structural rather than verbal.**
`_resolve_close` used to compute its label inside the `try` from
`total is not None` — the *intention* to book — and emit it after a `finally`
that might have failed. The label is now selected from `_book_resolved_close`'s
**return value**, in the `finally`, beside the write. A fourth outcome exists
because reusing the released text would have swapped a label that lies about the
ledger for one that lies about the position; commit 5's body records that trade
being refused.

**One criterion where there were three.** `execution/bookability.py` holds
`classify_bookability`: a pure predicate over four facts in one canonical order,
`A > Q > P > C`, returning a frozen verdict that carries its own reason.
`_bookable_total`, `_sell_and_book` and `reconciliation_driver`'s row ladder each
ask it. The three retired copies asked the same question in three different
orders, and that ordering difference was a real defect rather than untidiness —
a partial fill with no cost basis answers differently depending on which fact is
tested first.

**The instrument for that unification is two tests, not one, and the reason is
worth keeping.** A census holds the predicate-site count at ONE; a second test
holds that all three callers CONSUME it. The census matches
`entry_fill_price is None` comparisons, so a call site that deleted its check and
routed nowhere has none either — **a count of one is equally reachable by
rewiring and by deleting**, and only the second test separates them.

**The log prose now says what the code does.** A complete fill the venue never
priced is no longer reported as `close_partial_fill` beside an instruction to
sell base that is already gone — it has its own emitter, its own reason code and
its own event name, because an operator filtering on the old one must not find
it. The unconfirmed branch no longer claims "nothing was sold" on a path that
cannot know it.

**And the mutation harness implements the contract its own docstring stated.**
It refuses a piped stdout, reusing `check.py`'s decision by import rather than by
copy. It takes an out-of-tree snapshot before the first byte moves, keeps it when
a restore fails, and raises rather than returning on a mismatch. And it tells a
kill from a crash by reading the real exception class through a
`pytest_runtest_makereport` hookwrapper — because at this repository's node-id
lengths pytest's short summary is truncated away entirely under capture, and a
bare `assert x == y` renders with no type name in it at all.

**The harness's acceptance test is the part worth copying.** Its justification is
that it agrees with classifications a human had already made, so it was run
against all of them: commit A's D4 reproduced *"2 KILLED (raw FAILED: 4), 2
CRASHED"* against a hand result of raw 4 / classified 2, and the guard commit's
two mutations reproduced 4 and 2. Commit A's D4 was **not expressible at HEAD** —
commit 11 split the fused exit it depended on — so it was run in a `git worktree`
at `8a751cc` with the new harness copied in. A harness change validated only
against the current tree cannot be checked against the results that motivated it.

### What M5i did NOT do, stated as plainly as the above

**Nothing has run.** No supervised run took place in M5i. Every path it touched
is exercised by fabricated fixtures only, exactly as at M5h's close — and M5i
**added two emitters** (`_sold_unpriced`, and the fourth close-resolution
outcome) to paths no venue has ever exercised. The composition risk is therefore
larger at this close than at the last, for the second milestone running.

The three unobserved venue facts stand, unchanged and not re-derived:
**no take-profit has ever filled**; **`ALREADY_CLOSED` and `HALT` have never
occurred**; **`resolve_placement` has never run**. Each is a branch the tree can
reach only through a fixture, on a path where a fixture is a model of the venue
rather than an observation of it.

> **ANNOTATED at M5j. The premise is false; the conclusion about COMPOSITION
> survives.**
>
> **"Nothing has run" is FALSE.** MEASURED: **3 substantial runs fall in the M5i
> window**, and **2 more followed this close**, one of them trading for 8 h 40 m
> and booking 13 trades that reconcile to the persisted ledger at full
> precision. The capture is 21,209 lines across 47 distinct pids;
> `docs/RUN_LEDGER.md` holds the census, the command behind each figure and the
> digest of the file they came from.
>
> **What survives is the part this entry cared about**: the paths M5i *added* —
> `_sold_unpriced` and the fourth close-resolution outcome — have still not run,
> so the composition risk is real and unretired. Only the sweeping premise was
> wrong.
>
> **The three venue facts, re-measured.** No take-profit has ever filled —
> **carried**, zero fill clauses naming leg `TP` against 162 naming leg `SL`,
> and sharpened by a take-profit leg that reached `CANCELED` having executed
> nothing. `HALT` has never occurred — **carried**, zero across 65 close plans.
> **`ALREADY_CLOSED` occurred once**, on `2026-09-15T23:38:02Z`, **inside this
> milestone's own window** and two days before this close.
> **`resolve_placement` ran** on 2026-08-27.
>
> **The instrument that missed two of those, because it generalises.** The
> searches matched an enum's MEMBER NAME where the log carries its `.value` —
> `ALREADY_CLOSED` against `already_closed`, `TAKE_PROFIT` against the leg label
> `TP`. Twelve of eighteen enums in this tree carry a value differing from the
> name, and a sweep of every emission site in `src/` found the tree passes
> `.value` at every one: the defect was in the searches, never in the code.
>
> **The count of findings in this entry is untouched and is correct.** "130
> findings declared across `M5i-001`–`M5i-136`, every commit carrying a block"
> matches the documented extractor exactly, and it disagrees with
> `NEXT_MILESTONE.md`'s "132 ids" — this entry is the one that is right.

The uncomfortable shape, recorded because three milestones have now had it:
every improvement above is correct as far as anything here can tell, and "as far
as anything here can tell" is a fixture written by the same hand that wrote the
branch.

### What the milestone learned about its own instruments

Six instrument defects were corrected, and **not one was found by reading the
tool** — each was found because a prediction made in advance disagreed with what
the tool reported. A staged copy of `src/` could not shadow the real one, because
`pyproject.toml`'s `pythonpath` is prepended ahead of `PYTHONPATH`, and the
survey measured zero failures while reporting nothing wrong. A no-op mutation
passed the very verification it was written to break. A hand classifier
regex-scraped rendered text and reported an exception type of `assert`. A fence
script reused from the previous commit cried breach on the one file the new
commit was authorised to edit. A fake stdout served only `fileno` and crashed the
fixture before its own assertion. And a findings tabulation counted citations as
declarations, producing a plausible duplicate list from a clean tree.

**The rule that came out of it is the one about arming conditions.**
`M5h-352`'s read *"whoever next edits `_sell_and_book`"*; eight M5i commits
edited that file and one rewrote that method, and nothing noticed until the
rotation. `CLAUDE.md` now requires the audit at COMMIT time.

### The historical figures in this entry

**16 commits, 130 findings, and the gate at this commit's parent `812f9b2` —
`ruff check` clean, 118 files formatted, mypy clean over 74 source files, 1642
passed with 1 skipped, credentialed.** These are HISTORICAL and must never move,
exactly like the `f52f161`, `470b47b`, `4926705`, `4f08741` and `ff9cc66`
figures above. A later rotation grepping the digits will meet them; they are
facts about this milestone's close, not counts to update.

**M5i's scope and its rulings were the project owner's. Everything else here was
ruled by the reviewer under delegation.**

---

## Phase 5 M5j — the runs that had happened, and the instruments that missed them

M5i closed on the sentence *"nothing has run"*. M5j began by testing it and it
was false. **7 commits including this one — 6 of documents and tools and this
one of rotation — and 45 findings declared across `M5j-001`–`M5j-045`, every
commit carrying a block.** The headline is not any one correction: it is that
the evidence had been sitting in a gitignored file for three milestones and no
instrument in the repository was pointed at it.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `97d5239` | A run ledger for the log the repository cannot see |
| 2 | `0992fa3` | The runs that happened, and the actor the log cannot see |
| 3 | `e549f58` | The leg settled, and a premise that outlived its conclusion |
| 4 | `88db57a` | The fee gap is at the port, and a rule never written down |
| 5 | `3ea87d8` | A take-profit filled, and the timestamp that made it look slow |
| 6 | `ec3df40` | A census that refuses the live log, and a checker that fails closed |
| 7 | this commit | Two decided documents annotated, and this entry |

### What was found by looking at the log

**A frozen capture was taken and given a digest, and everything followed from
that.** The decision worth recording is that a capture is named and hashed
rather than read live: the bot appends while it runs, so two reads a second
apart measure two files and a figure from either is attached to nothing a later
reader can reproduce. `docs/RUN_LEDGER.md` was created to hold the census.

**Three of the four venue facts this project had carried as unobserved were
already false when the milestone opened**, and two of them were missed by the
same instrument defect. The searches matched an enum's MEMBER NAME where the
log carries its `.value` — `ALREADY_CLOSED` against `already_closed`,
`TAKE_PROFIT` against the leg label `TP`. Twelve of eighteen enums in the tree
carry a value differing from the name, and a sweep of every emission site found
the tree passes `.value` everywhere: **the defect was in the searches, never in
the code.**

**X3 was struck first** — `resolve_placement` ran on 2026-08-27, one
`placement_ambiguous` followed a minute later by `placement_resolved
outcome=placed_live`. **X2a was struck next** — `ALREADY_CLOSED` occurred on
2026-09-15T23:38:02Z, inside M5i's own window and two days before its close.
**X1 was struck last, and it was observed rather than re-read**: a take-profit
leg filled on 2026-09-18, MEASURED against the capture whose SHA-256 is
`bbdeb1787ac0caf5782229391ef6cf5931a046193d8b6fef078ef3941121e182` — one clause
naming a filled `TP` leg against 162 naming a filled `SL` leg, the `SL` figure
re-measured and unmoved, so a new event rather than a re-reading.

**`decision=halt` is the sole remaining unobserved venue fact.** Against the
capture this rotation was taken with it is zero across **75** close plans —
`decision=sell` 74 plus `decision=already_closed` 1 — and the denominator is
stated with its capture because it moved three times inside one milestone.

### The accounting item, and the alternatives rejected

**`M5j-012` began as "`close_position` takes `fee` and three call sites omit
it" and ended as an architectural accounting item.** The wiring inside
`core/portfolio.py` is complete on both limbs; what is missing is any figure to
pass. `to_order` reads sixteen distinct wire keys and `fills` is not among
them, so the venue's own commission is discarded at the mapper, and `Order`,
`ExitFill` and every port method are commission-free by construction.

**Three rulings by the project owner, and two rejected alternatives.** The
denomination invariant: a money figure crosses a domain boundary only as an
amount paired with its asset, never as a bare `Decimal`, because both operands
being `Decimal` makes a cross-denomination subtraction succeed silently and the
type system cannot catch it. **The two-of-three fix was REJECTED on
ledger-comparability grounds** — wiring the two sites that could reach a fee and
leaving the third would make the ledger net of fees on some closes and gross on
others, with no reader able to tell which without knowing the close path, and a
ledger whose purpose is to match an exchange statement cannot be net in part.
**Threading `fee=Decimal(0)` as an interim stub was REJECTED outright**: it
changes no behaviour, passes the gate unchanged, and would retire the finding
that names the defect while leaving the defect exactly where it is.

### Two tools, and why they are shaped as they are

**`scripts/run_census.py` mechanises the ledger's own tables and refuses the
live log.** The refusal precedes the is-a-file check, so a path under `logs/`
is rejected before a byte is read; there is no default argument at all. It
prints the digest of what it read beside every figure block rather than once in
a header, because figures are quoted elsewhere and arrive with no instrument
attached.

**`scripts/check_arming_conditions.py` keeps two registers and fails closed.**
The conditions were written as prose before anything read them mechanically,
and measured on the tree at its close: 22 conditions, 16 running past the line
they begin on, at least four opening grammars, and several naming no backticked
symbol at all. **A tool reporting only what it parsed would print a clean run
precisely when its parser was most broken**, so the unparsed register prints
even when empty and a non-empty one exits non-zero. It exits non-zero today by
design.

**The `src/` change was one marker and it was attached, not added.**
`TradingEngine.stop` already emitted its message with no structured field; the
marker enriches that call rather than emitting a second line, and the message
text stays byte-identical because an existing test selects records by that
substring. `clean_shutdown` is read before the method sets the flag itself,
which is what keeps the field a measurement rather than a constant.

**The gate counts advanced with the two scripts and their two test files, and
the measured figures belong to step 2 of this rotation rather than here.** A
prior target of a single-file advance was incompatible with the batch as
scoped, and that was raised as a halt rather than adjusted quietly.

### The doctrines the milestone earned

**An instrument is evidence only for the INSTANT it reads, as well as for the
property it reads.** Neither half had been written down. The distinction it
buys is between unmeasured and **unmeasurable in retrospect** — an unmeasured
case is one derivation away from closure, an unmeasurable one is closed to
measurement altogether and stays open as the honest record of that.

**A capture-bound claim carries its digest inline, in the sentence.** The worked
instance was a sentence written three days earlier that said *"still true"* and
named no bytes; its siblings in the same block that named their capture aged
into the record visibly, and that one simply became wrong.

**Argue a silence from PRESENCE, not from absence.** Bracketing an interval by
the last record of one pid and the first of the next, with no record between
carrying any pid, distinguishes "nothing ran" from "something ran and did not
log". An absence of matching lines cannot.

**And `venue_time` is the venue order record's lifecycle timestamp** — neither a
client-side clock nor the matching-engine execution time. The rename and the
true fill time were scoped to the accounting milestone rather than taken here.

### The errors this milestone made, recorded because they generalise

**A rule was quoted as settled doctrine for several milestones and had never
been committed.** *"An instrument is evidence only for the property it literally
reads"* returned zero hits across `CLAUDE.md`, `README.md` and `docs/`. That is
the `phase_5_` shape in its purest form: a rule governing work while living only
outside the repository.

**A 1h52m detection gap was asserted from `venue_time` without being derived,
and the same two lines disprove it.** The placement stamp sits 1.4 seconds
after the value, and a fill cannot precede the placement that created the
order; the true detection window was 119 seconds. Reasoning from a field's NAME
rather than its CONTENT.

**A long SHA was fabricated past a correct short form.** A closing report gave
`ec3df4055c7d0b39ff1a3bbb2e13bb3b70e4ef5c` where the commit is
`ec3df40a5831847bba3ce120dd93eb927006ff1f`. The short prefix was right and
everything after it was invented. A SHA is taken from `git rev-parse`, never
from a report.

**And a path set was named in an authorisation without being enumerated**, so a
phase opened against a file that does not exist. Deriving the true set was made
the phase's first job rather than a substitution made quietly.

### What this rotation's step 4 found

**Two decided documents carried prose M5j superseded, and one of them had been
false for three milestones.** `QB_ESCALATION.md` stated that nothing in `src/`
assigns `Position.protection`; `OrderExecutor` has constructed a `Position`
since M5f `8ca878e`, and the field is written by two `Position` methods reached
from three call sites in the reconciler and assigned at four sites in the
executor. **Its sibling in `QC_PROTECTIVE_ORDERS.md` said the same thing and was
annotated at M5h's rotation**; this one was missed, and nothing compares two
documents against each other.

**`QC_PROTECTIVE_ORDERS.md`'s re-place table needed care rather than
correction.** Its fourth row is marked REASONED, NOT MEASURED and *"needs a
fill"*; two fills have since occurred and **neither is the fill that row
needs**, which requires a timed-out write whose working leg filled with pendings
still live. The working leg is `LIMIT`+`FOK` and cannot rest. The row was
annotated, not struck.

**And one annotation was re-verified rather than trusted.** Section 7's *"every
instance was our bug rather than a venue divergence"* was the natural casualty
of a milestone in which a protective leg finally filled. Measured again: all 28
`diverged=1` records fall between 04:07:02 and 04:38:02 on 2026-08-27, the
identifier-space fix is authored 05:47:28Z the same day, and zero follow it.
**It survives.**

**M5j's scope and its rulings were the project owner's. Everything else here was
ruled by the reviewer under delegation.**

## Phase 5 M5k — the fee reaches the ledger, and what cannot be booked is held

M5j closed with the accounting item open: `close_position` took a fee and no
fee ever arrived. M5k made the EXIT fee arrive, at all three booking sites in
one commit, and decided what happens to an exit whose settlement the ledger
cannot subtract: it is HELD, in the sense of d253cd5's subject, *"hold an exit
the ledger cannot book"*. The ENTRY fee was not netted, by ruling. **23 commits
including this one -- 17 numbered and 6 of rotation -- and 160 findings
declared across `M5k-001`–`M5k-160`, every commit carrying a block.** Counted
with `git log --oneline "milestone/M5j..HEAD"` and
`scripts/check_findings.py milestone/M5j..HEAD M5k` before this entry was
written, the last commit being this one.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `3e444f0` | A diverged pass with no fill escalated instead of continuing |
| 2 | `2109bee` | The findings extractor became a tracked script, beside a count-site check |
| 3 | `45ffe31` | The `myTrades` wire boundary, modelled against a captured payload |
| 4 | `9f3deb1` | `Fee` and `Trade` in the domain, and the port method that carries them |
| 5 | `8b55785` | Live trading blocked on fee netting; R6 rescoped to speculative queries |
| 6 | `7e8ad65` | Live trading refused at every entry point; testnet keys only |
| 7 | `67f1b81` | The integration credential gate counted the testnet pair only |
| 8 | `e511e6d` | A second close refused while one is pending; settlement counted in the budget |
| 9 | `f1c5af7` | Fills fetched by order id; `ExitFill.venue_time` renamed |
| 10 | `651d334` | Exits booked net of the venue's own fee, at all three sites |
| 11 | `db73b63` | The booking lines pinned, a net fee on disk, and a restart driven |
| 12 | `a534b31` | One settlement field set on every booking line |
| 13 | `d253cd5` | An exit the ledger cannot book held, and no longer reconciled |
| 14 | `f4a82bb` | Three docstrings that still said "every open position" |
| 15 | `193a5b9` | A negative quote total read as absent; a fill without `quoteQty` a venue error |
| 16 | `222bdf4` | Partial and cost basis decided before a missing quote total |
| 17 | `c5dd7d5` | A missing quote total booked from the order's own fills |

**The rotation took six commits, this one included**:
- `eecb22b`, step 4: three contracts annotated, four sections added to
  `RUN_LEDGER.md`, and a capture taken at M5k's close;
- `6ef5aac`, step 2: `CLAUDE.md` and `README.md` at M5k's close, in one
  commit;
- `ae8c914`: the method rules, the deployment doctrine, and a testnet-only
  `.env.example`;
- `4544b3a`, step 3 part 1: `NEXT_MILESTONE.md` struck and repaired;
- `583e480`, step 3 part 2: `NEXT_MILESTONE.md` for M5l;
- this commit, steps 1 and 5: this entry, the two `CLAUDE.md` placeholders,
  the owner's accounts in `RUN_LEDGER.md`, and the tag.

### What was built, in order

**First the gap A5 named, and the tools.** A pass whose position-level verdict
was `DIVERGED` and whose legs reported no fill had been treated as the ordinary
healthy pass; from `3e444f0` it escalated at `CRITICAL`. `2109bee` made the
findings extractor a tracked script, because its only copy had been prose
inside a fence, and added the count-site check.

**Then the fee, from the wire inward.** The `myTrades` record was modelled
against a captured payload (`45ffe31`). The domain gained `Fee`, an amount
inseparable from its asset, and `Trade`, one per fill, and the port gained
`get_my_trades` (`9f3deb1`). The port learned to ask for one order's fills and
the misleading `venue_time` was renamed (`f1c5af7`). Then every booking site
settled the exit order's fills and booked net of the fee, in one commit
(`651d334`); the lines were pinned (`db73b63`) and given one field set
(`a534b31`).

**Around it, the guards the fee made necessary.** Live trading was blocked in
`CLAUDE.md` (`8b55785`) and refused in code at every entry point (`7e8ad65`).
A second `CLOSE` while one was pending was refused, and the budget check
counted the settlement fetch (`e511e6d`).

**Then what a booking cannot settle.** A fee in a foreign asset, or a fill that
is not a sell, was held on the position, no longer reconciled, and its `CLOSE`
refused (`d253cd5`).

**Last, the missing quote total.** A negative `cummulativeQuoteQty` was read as
absent (`193a5b9`); the bookability ladder was reordered so that partial and
cost basis are decided first (`222bdf4`); and an unpriced whole fill was booked
from the sum of its own fills (`c5dd7d5`).

### The decisions, and the alternatives rejected

Rulings are cited by content or by the commit that records them, per
`CLAUDE.md`'s rule k; bare labels are not reused.

- **One `Trade` per fill, aggregation by summing, never dividing** (`9f3deb1`).
  REJECTED: an aggregate per order, which would publish a weighted average price
  -- `quote_quantity / quantity` reached the 28-digit context precision on 10 of
  the 11 multi-fill orders measured (`M5k-031`).
- **`Fee`, one required value** (`9f3deb1`). REJECTED: `fee` beside
  `fee_asset`, two fields that had to agree and could each default to a value
  denominating nothing -- the stub `CLAUDE.md` forbids, made unrepresentable
  rather than discouraged.
- **Money from the venue's raw string, not through `_dec`** (`45ffe31`).
  REJECTED: `_dec`, which launders a float past `Money` (`M5k-025`); its defect
  was declared, not fixed, by the owner's scope ruling.
- **Exit fees only -- the ledger net of exit fees and gross of entry fees**
  (the owner's R-a, recorded at `651d334`). REJECTED: full netting now, because
  entry-fee netting is the live-trading block's own subject.
- **Every booking site or none** (`651d334`), the M5j ruling applied.
  REJECTED again: the two-of-three wiring.
- **The settlement fetch inside an async `_book_exits`** (`651d334`), the
  placement R6's rescope (`8b55785`) had left open.
- **A retained close for five of its own symbol's bars, then dropped at
  `CRITICAL`** (Variant L, N = 5, `651d334`). REJECTED: dropping on the first
  failure, which forfeits a booking the next bar would have read, and retaining
  without bound, which holds a symbol unable to close.
- **An unbookable settlement HELD** (R2 with rulings A and B, as `d253cd5`
  records them). REJECTED: the executor's drop after one bar and the driver's
  retry on every pass -- the two outcomes F1 had found for one fact. Its name
  is `Position.settlement_hold`, `d253cd5`'s PIN-1, chosen over the ruling's
  own `unbookable_fee_mismatch` because "unbookable" already named three other
  things (`M5k-082`).
- **The sibling leg ends with its partner, accepted as observed** (`d253cd5`'s
  PIN-2, Case 1). REJECTED: cancelling siblings in code, on 144 of 148 observed
  expiries and none live (`M5k-080`).
- **The ladder `A > P > C > Q`** (Decision 1, recorded at `222bdf4`).
  REJECTED: `A > Q > P > C`, which spent a venue call before deciding facts
  that make one unnecessary.
- **`_sold_unpriced` removed; a failed supply at the sell defers** (Decision 2,
  recorded at `c5dd7d5`). REJECTED: keeping an unpriced sell, whose line told
  an operator a partial had filled in full (`M5k-096`).
- **A negative total is absent** (Decision 3, recorded at `193a5b9`). REJECTED:
  raising, and booking it -- it would have been credited (`M5k-091`).
- **The live guard at every entry point** (`7e8ad65`). REJECTED: a guard in
  `Settings.__init__` alone, which three entry points bypass by reassigning
  `mode` after construction (`M5k-036`); and a `ConfigError`, which one script
  turns into "Configuration error" and exit 2.
- **`CRITICAL` without a halt flag** (ratified at `3e444f0`, `M5k-006`).
  REJECTED: building the halt flag inside the commit that first needed it.
- **The protection write in row 4 struck** (`3e444f0`). It had been predicted
  inert and was not: the test suite is also a reader (`M5k-008`).
- **Three commits over the 1,500-line guide, each waived by the owner**
  (`M5k-049`, `M5k-054`, `M5k-114`); the rotation's rule h admits none after
  them.

### What measurement overturned

- The library's own `get_my_trades` docstring showed nine keys and omitted
  `orderId`; the venue sent thirteen (`M5k-021`).
- Planned assertions that could not bite: a fixture where `quoteQty` equals
  `price x qty` on every record (`M5k-029`), and a fee of zero on every record
  (`M5k-032`). Measuring the fixture first changed the test both times.
- A write predicted inert was not (`M5k-008`).
- Twenty-one existing tests built a config the new check refused, not twenty
  (`M5k-045`).
- A skip blamed a missing tag when the tool had lost its working directory
  (`M5k-017`).
- A negative total would have booked (`M5k-091`), and a fill without
  `quoteQty` raised `KeyError`, which no settlement handler caught (`M5k-092`).
- A mutation's prediction reached further than its name (`M5k-115`), and
  another missed in both directions (`M5k-074`).

### The method rules adopted at this rotation

The owner approved them in full, at `ae8c914`: the standing clause (a);
mutation surveys only in disposable worktrees, superseding harness trap 4, on
`M5k-123` (b); the formatter before the survey (c); tolerant searches that do
not strip `_` (d); path-limited diffs that never include `config.yaml` (e);
asymmetric prediction misses (f); a commit-time audit of every document that
carries a condition (g); the 1,500-line ceiling, without waivers (h); log
fields read through `vars(record).get` and asserted lengths (i); `DOCUMENTED` as
a fourth mark (j); ruling ids qualified by prompt (k); and the count-site check
run twice, outgoing figures first (l). **The deployment doctrine was ruled
beside them**: the bot is never launched from a development working tree.

### What did NOT happen

- **No committed M5k code was shown to have run.** Eight booking lines carried
  the fee fields, the first written seven hours before `651d334` was committed,
  from code no commit then contained (`M5k-123`); no line carried
  `quote_total_source` (`M5k-132`'s banner records no commit either).
- **Every commission any capture recorded was `0.00000000`**, so net-of-fee
  booking never subtracted a non-zero fee outside a test.
- **Entry fees were not netted, and the live-trading block stood.**
- **Position-level `DIVERGED` was never observed in production**, and neither
  were the six events M5k added.
- **The failure modes M5k catalogued were carried, not closed**: PIN-3 and
  PIN-4 as `c5dd7d5` records them, `M5k-110`, `M5k-083`, `M5k-073`,
  `M5k-111`, `M5k-102`, `M5k-121`, `M5k-060` and `M5k-090`'s limit, carried to
  M5l as its P-3.

### What the rotation's steps found

- **Step 4** (`eecb22b`):
  - M5_NUMBERS's refusal message was false since `e511e6d` (`M5k-116`);
  - QB's "persistence is a stub" was false since M5h (`M5k-117`);
  - QB's halt-flag condition was invisible to the checker (`M5k-118`);
  - §15's fill time was measured (`M5k-119`);
  - order 300642 had been recorded nowhere (`M5k-120`);
  - four realised figures carried exponent -24 (`M5k-121`);
  - five captures were missing from the ledger (`M5k-122`);
  - K1's answer on what ran (`M5k-123`);
  - POSITION_STALE's first firing (`M5k-124`).
- **Step 2** (`6ef5aac`):
  - the count checker was blind at rotation time (`M5k-125`);
  - two false quotations of the tree (`M5k-126`);
  - the census instrument missed two constants (`M5k-127`);
  - ruling ids collided (`M5k-128`);
  - README's headline contradicted itself (`M5k-129`);
  - the architecture trees were stale (`M5k-130`);
  - M5k-006's ruling was unrecorded (`M5k-131`);
  - the bot records no commit (`M5k-132`).
- **The method-rules commit** (`ae8c914`), `M5k-133` to `M5k-142`: trap 4
  superseded, the waivers closed, QB's condition made visible but not parsed,
  the template made testnet-only, and the venv trap.
- **Step 3**, `M5k-143` to `M5k-154` (`4544b3a`, `583e480`):
  - three conditions fired unaudited;
  - a spent condition, an event-named disjunct and a moved site;
  - a self-contradicting priority;
  - the re-measured figures;
  - M5l's scope;
  - the staleness default measured against the check it would face;
  - three repaired conditions and a named caller for Q-B's.
- **Steps 1 and 5** (this commit), `M5k-155` to `M5k-160`:
  - `M5k-149`'s mark annotated;
  - the owner's accounts closing section 17's open items;
  - M5j's POSITION_STALE sentence left standing;
  - the commit count;
  - the owner's third account set beside the log's metadata;
  - M5j's own entry, which undercounted itself by the one rotation commit that
    followed it.

**A3 fired here, and the headline was checked against it.** A3's condition is
*"whoever next appends a milestone entry to `docs/PHASE_HISTORY.md`"*, and the
question it poses is whether a headline states a claim its entry later
annotates. This one does not, read in the tree's own vocabulary: "the fee" is
scoped to the EXIT fee in the entry's first sentence, and "what cannot be
booked" is the phrase of `d253cd5`'s subject and of `CLAUDE.md`'s locked
bullet *"AN EXIT THE LEDGER CANNOT BOOK IS HELD"*. The other unbooked outcomes
-- a sell with no cost basis dropped, a settlement that timed out -- are
separate decisions recorded above, not exceptions to the headline.

### The historical figures in this entry

**Pinned to their commits, not a live count.**
- **At `c5dd7d5`**, the last numbered commit: `ruff format` 129 files, `mypy`
  79 source files, 1822 passed and 1 skipped with Testnet credentials; 115
  findings.
- **At this rotation's gate**: the same 129 / 79 / 1822 passed, 1 skipped,
  credentialed, since the rotation changed no `.py` file; 160 findings.
- The capture the rotation measured is SHA-256
  `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`.

**M5k's scope and its rulings were the project owner's; the method rules were
approved by the owner at the rotation; everything else was ruled by the
architect or by the reviewer under delegation.**


## Phase 5 M5l — the run that proves its own code, a restart that keeps its positions, and a staleness bound a healthy feed can reach

M5k closed on a central fact: nothing it added was shown to have run as committed, and the
bot recorded nothing that could show it (`M5k-123`, `M5k-132`). M5l's scope was the owner's
three priorities -- startup provenance, the staleness bound against the reconciliation dedup
interval, and the silent and unhedged failure modes M5k catalogued -- and its shape was
evidence-first: the runs it recorded were made from deployment clones of pushed commits. **74 commits including this one -- 65 numbered and 9 of rotation -- and 280
findings declared across `M5l-001`-`M5l-280`, every commit but the owner's blockless
`9f364dd` carrying a block.** Counted with `git rev-list --count milestone/M5k..HEAD`,
`scripts/check_findings.py milestone/M5k..HEAD M5l` and the display command before this entry
was written, which read 73 commits and 277 declared with no gap and no duplicate; this commit,
the last, adds itself and its three.

### The commits

| # | SHA | What it closed |
|---|---|---|
| 1 | `fdf8d7b` | feat(config): settings carry the loaded config's path and digest |
| 2 | `ac1162d` | feat(provenance): read the launch checkout through a bounded git |
| 3 | `d74f78b` | feat(provenance): classify the install, verify RECORD, decide the verdict |
| 4 | `f8898de` | feat(main): log startup provenance on every boot and refuse an unproven run |
| 5 | `63d4615` | feat(provenance): a module RECORD does not list is not intact |
| 6 | `5cac7ae` | docs: startup provenance landed -- the doctrine's banner, and P-1 resolved |
| 7 | `9f364dd` | config: operator settings for testnet runs |
| 8 | `c2cab79` | fix(provenance): every refusal names its cause; unknown means unknown |
| 9 | `bf2e44d` | docs(readme): the utils/ list names provenance |
| 10 | `1f4a718` | docs: the owner's committed config -- tracked, clean, and inside the budget at 2.3 |
| 11 | `b84e7b9` | docs: the deployment procedure, and reconciliation latency measured |
| 12 | `06089d5` | docs(next): a restart orphans an open position, gated before live |
| 13 | `71b591a` | docs(ledger): M5l's evidence run, and the runs before it |
| 14 | `639870f` | docs: the deployment-clone runs, annotated where they made text false |
| 15 | `bee5fe5` | docs(ledger): the evidence run's end record, before its census |
| 16 | `ac07ebb` | docs: M5l's evidence run -- census, venue cross-check, and what it made false |
| 17 | `9a131a6` | docs(readme): what M5l's evidence run and the live gates made false |
| 18 | `f2182a6` | docs: P-3l, the outage measured, and what P-2's design must meet |
| 19 | `25dbc61` | fix(config): the coherence check adds exactly |
| 20 | `5d6f115` | fix(config): the coherence refusal prints exact figures and true words |
| 21 | `517348f` | test(reconciliation): pin the dedup boundary |
| 22 | `6e7c9f2` | docs(src): docstrings that said what the samples and the stamp no longer do |
| 23 | `4a094c5` | docs: P-2's items resolved or held, and what STEP 0 measured |
| 24 | `f20e839` | feat(config): a staleness bound a healthy feed can reach is refused at load |
| 25 | `90355df` | feat(config): a position cap that cannot complete one position is refused at load |
| 26 | `cf37cda` | docs: P-2 resolved item by item, and an unstamped position said by case |
| 27 | `9f188c4` | docs: the staleness default is ruled kept; P-2 stays open on one clause |
| 28 | `40a9e67` | docs: P-2's locked text held back on a bound missing its precondition |
| 29 | `127be9a` | docs(src): churn adds deferrals beyond n - 1, with no bound claimed |
| 30 | `5721a5c` | docs: the polling decision re-ruled with its precondition; P-2 closed |
| 31 | `a77e02c` | docs: the P-3 triage rulings, verbatim, and the owner's order |
| 32 | `131f1c9` | feat(store): a record per open position, at schema 2 |
| 33 | `4b57f34` | feat(portfolio): restore a position, and book an exit made while down |
| 34 | `989edfc` | feat(persistence): each save carries a record per open position |
| 35 | `f7ebce9` | feat(execution): a pure boot classifier for restored records |
| 36 | `5a2307c` | feat(boot): resolve the store's records at boot |
| 37 | `fa06d77` | feat(boot): book an exit that filled while down, or hold its record |
| 38 | `a14aa6c` | feat(boot): restore and sell a position whose protection is gone |
| 39 | `4f2cc49` | fix(exchange): -2013 maps to OrderNotFoundError |
| 40 | `2081389` | feat(boot): a close beside a position record is read, booked or sold once |
| 41 | `cde0fb0` | test(execution): a raise after a placed list keeps its pending record |
| 42 | `e4004ab` | feat(scripts): release one symbol's records from the store |
| 43 | `d1074c6` | docs: P-3k's text corrected, the deployment procedure and a run template |
| 44 | `244aa6b` | fix(exchange): -2011 'Unknown order list sent.' maps to OrderNotFoundError |
| 45 | `d95cb5e` | fix(scripts): the cancel script's warning says what the boot now does |
| 46 | `5e22bc6` | docs: record the P-3k supervised run so far, and the ETH takeover cost |
| 47 | `8403673` | docs: A4 passed at 5e22bc6; P-3k's gate closed by the owner's ruling |
| 48 | `5709b04` | docs: annotate the closed P-3k gate, catalogue the stop-loss review |
| 49 | `0c1a802` | fix(boot): an enabled pair quoted outside the portfolio's asset refuses the boot |
| 50 | `31281fa` | feat(reconciliation): the call cap is max(N, L + 1), not the position limit |
| 51 | `b29a658` | feat(reconciliation): a call-cap deferral is logged, one line per position |
| 52 | `4c2e55c` | feat(reconciliation): a phase reports the calls it spent, settlement included |
| 53 | `a519d9e` | feat(data): a missing bar is detected, and a BUY is refused while the window spans it |
| 54 | `68ffa47` | feat(data): a watchdog reports a silent pair, a lagging loop and a slow handler chain |
| 55 | `1046a01` | feat(exchange): the library's transient errors are read past, and P-3l is closed |
| 56 | `441b5b2` | feat(reconciliation): an unreadable settlement is held after five failed passes |
| 57 | `4341c5c` | feat(accounting): realised is the exit total less the entry's own quote total |
| 58 | `f9e606e` | feat(scripts): a one-off that normalises the ledger's exponents, losslessly or not at all |
| 59 | `cdc6c2e` | fix(portfolio): closing a symbol the ledger does not hold raises, and is never reported booked |
| 60 | `e3ff798` | feat(risk): the stale refusal names a held position, and a test drives one end to end |
| 61 | `b5975ff` | test(executor): exit_quote_totals_disagree fires only in the tests that intend it |
| 62 | `bf6f9a8` | fix(executor): a booking guard that refuses a filled sell holds the position and says so |
| 63 | `b430ea4` | test(executor): the two weak tests detect as assertions, and the N = 5 annotation is recorded |
| 64 | `51a5f27` | fix(executor): Site B holds an unbookable close as Site A does, and the "position survives" wording is true |
| 65 | `7489581` | docs(run-ledger): M5l's observation run at 51a5f27, its census and its venue cross-check |

**The rotation took nine commits, this one included**, in the order the procedure's step 1
being written last requires:
- `810eaa3`: the standing authorities moved into `CLAUDE.md`, verbatim, by the owner's ruling;
- `456d38b`: the 18 gate-count lines in `CLAUDE.md` and `README.md`, from a fresh run;
- `ad24ace`: five letter-only rule citations replaced by quotations;
- `9fc8b8d`: pre-existing false text swept, 23 candidates by content;
- `d8724dd`, `6937c89`, `e531822`: `NEXT_MILESTONE.md` rotated to M5m in three parts, because
  the whole is 1,999 changed lines and the ceiling admits no waiver;
- `5bd8575`: the arming registers re-run and the mode-3 pass;
- this commit, steps 1, 2 and 5: this entry, the "Current state" paragraphs in `CLAUDE.md`
  and `README.md`, and the tag.

### What was built, in order

**First the proof (`fdf8d7b`, `ac1162d`, `d74f78b`, `f8898de`, `63d4615`, `c2cab79`).**
Settings gained the loaded config's resolved path and the digest of the bytes parsed. A
bounded git reads the LAUNCH checkout, with timeouts that survive a grandchild holding the
output pipe (`M5l-014`) and a Windows resolver that will not run a decoy `git` from the
working directory (`M5l-018`, `M5l-022`). The running code's commit is not asked of git but of
pip's own record: the install is classified from PEP 610's `direct_url.json` and its `RECORD`
verified file by file, a `.py` the record does not list refusing (`M5l-004`, `M5l-017`,
`M5l-026`, `M5l-028`). `main` logs `boot_provenance` on every boot and refuses `run` unless
every condition holds, and from `c2cab79` every refusal names its cause and an unknown is a
refusal reason and never a pass.

**Then the first run on known code (`b84e7b9`, `06089d5`, `71b591a`, `639870f`, `bee5fe5`,
`ac07ebb`, `9a131a6`, `f2182a6`).** The deployment procedure was written and built, 300
reconciliation-call latencies were measured (`M5l-039`), and the evidence run, pid 21520 at
`06089d5`, wrote three `close_booked` lines carrying `quote_total_source=venue` that
reconcile exactly against the venue's fills (`M5l-053`, `M5l-054`). It also lived through a
market-data outage in which the bot's disconnect warning came 229 s after the library's first
error and no reconciliation pass ran for 300 s (`M5l-055`, `M5l-060` to `M5l-063`), which
became P-3l.

**P-2, the staleness bound (`25dbc61`, `5d6f115`, `517348f`, `6e7c9f2`, `4a094c5`, `f20e839`,
`90355df`, `cf37cda`, `9f188c4`, `40a9e67`, `127be9a`, `5721a5c`).** The coherence check
adds exactly, a bound a healthy feed cannot reach is refused at load, the strict `>` of
`_is_due` is pinned, and the locked polling decision is annotated with the owner's re-ruled
text and its precondition rather than rewritten.

**P-3k, a restart that keeps its positions (`a77e02c`, `131f1c9`, `4b57f34`, `989edfc`,
`f7ebce9`, `5a2307c`, `fa06d77`, `a14aa6c`, `4f2cc49`, `2081389`, `cde0fb0`, `e4004ab`,
`d1074c6`, `244aa6b`, `d95cb5e`, `5e22bc6`, `8403673`, `5709b04`).** Every open position keeps
a record in `data/state.json` at schema 2; a pure classifier reads each at boot against the
venue; a position restores, a fill made while down books ledger-only, a protection that is
gone sells once, a close beside a record is read, and an exit the ledger cannot book keeps a
held record with no `Position`. `scripts/release_position.py` releases one by hand. The first
supervised run failed A4 on a venue answer nothing mapped (`M5l-161`), the mapping landed
(`244aa6b`), A4 passed at `5e22bc6`, and the owner closed the gate at P87.

**The rest of P-3, one commit each (`0c1a802`, `31281fa`, `b29a658`, `4c2e55c`, `a519d9e`,
`68ffa47`, `1046a01`, `441b5b2`, `4341c5c`, `f9e606e`, `cdc6c2e`, `e3ff798`, `b5975ff`,
`bf6f9a8`, `b430ea4`, `51a5f27`).** A pair quoted outside the base currency refuses the boot;
the call cap is `max(N, L + 1)`; a call-cap deferral and a phase's calls are logged; a missing
bar is detected and a `BUY` refused while the window spans it; a watchdog reports a silent
pair, a lagging loop and a slow chain; the library's transient stream errors are read past; an
unreadable settlement is held after five failed passes; realised is the exit total less the
entry's own quote total, and a one-off normalises the persisted exponents losslessly; closing a
symbol the ledger does not hold raises; the stale refusal names a held position; a booking
guard that refuses a filled sell holds the position, at Site A and then at Site B.

**Last, the observation run (`7489581`).** 8.356 h from a deployment clone of `51a5f27`: six
round trips, every booking equal to the venue's fills by GET, the ledger chained from the
normaliser's output to the end store to the last digit, and none of the feed-health events
(`docs/RUN_LEDGER.md` section 26).

### The decisions, and the alternatives rejected

- **The running code's commit comes from pip's record, not from git.** A runtime `git` read
  against a package installed into a venv inside a checkout reported that checkout's later
  `HEAD` as clean while the installed code was older (`M5l-005`), and a non-editable install
  outside any checkout reaches no `.git` at all (`M5l-006`). So git answers the launch
  checkout and the record answers the running code, and the boot line says whether they agree.
- **P-2 kept the strict `>` and annotated the locked text, and kept the 180 s default as the
  owner's policy choice.** Changing the comparison to `>=`, or deduplicating against a shorter
  interval, was the alternative; the floor is derived and refused at load instead
  (`M5l-069`, `M5l-084`), and the default's status stays PLACEHOLDER because keeping a value
  does not measure it.
- **The call cap is `max(max_open_positions, L + 1)`, sketch (a).** Of the owner's three
  sketches only (b), `n * (1 + L)`, failed the committed coherence budget, 36.4 s against
  30.0 s (`M5l-101`).
- **A position record holds requested values only, and a hold is re-derived at boot from the
  venue's immutable fills.** Persisting the hold and the retry count was the alternative the
  owner's Q12 ruled out (the text is in `docs/NEXT_MILESTONE.md` at `9fc8b8d` and lifted in
  that file's rulings section). A held record has no `Position` (Q5(b)), because a restored
  one would overstate equity (`M5l-112`); "start empty and adopt" is unavailable at HEAD
  (`M5l-037`).
- **The synthetic `CLOSE` at boot sells once, and a failed venue read refuses the boot.**
  Reading a generic API error as an absent order would restore a position beside a sell that
  may have filled (`M5l-148`).
- **P-3l reports and does not repair.** The watchdog acts on nothing (`M5l-203`); a REST
  backfill and a timer-driven pass were catalogued as deferred U12 and U11 (`M5l-207`), so
  the stopped reconciliation is accepted under the owner's P76 and not fixed.
- **The entry's own quote total is memory-only on `Position`**, set from the one entry GET,
  and realised is the exit total less it. The alternative was to keep multiplying a 28-digit
  quotient (`M5l-209`, `M5l-210`); persisting the total was ruled out with the hold.
- **The normaliser is lossless or it refuses.** It never rounds a figure that would lose a
  digit and it refuses a store at another schema, because `store.save` would upgrade it as well
  (`M5l-227`, `M5l-228`).
- **Site B holds as Site A does, through one hold with a `site` argument and not a copy.** A
  pre-sell guard was impossible, because the verdict is built from the sell's own results
  (`M5l-239`, `M5l-245`).

### What measurement overturned

- **`D <= 10.5 s`**, stated in `CLAUDE.md` and four places in `M5_NUMBERS.md`, had been false
  since the settlement term: varying only `dispatch_deadline_s`, 9.25 s is accepted and 9.26 s
  refused (`M5l-034`).
- **P-2's first item**, that a bound between one and two intervals refuses a healthy system,
  was wrong (`M5l-066`, `M5l-067`), and the polling decision's *"at least bounded by its own
  cadence"* was false (`M5l-097`). The deferral count is `k <= n - 1` without churn and
  reached `n + 1` with it (`M5l-084`, `M5l-088`, `M5l-092`).
- **`-2013` did not reach `OrderNotFoundError`** (`M5l-138`), and **`-2011 'Unknown order list
  sent.'` was unmapped**, which failed A4 on the real venue (`M5l-161`).
- **P-3h's "the cause is UNMEASURED"** was already false and is now measured: four bookings
  filled across 6 to 8 price levels (`M5l-100`, `M5l-209`).
- **A stop-loss filled about 4.2 percent beyond its trigger** (`M5l-170`), which is why the
  protective order type is marked for review before live trading.
- **The A5 item's "the escalation has never run"** was false of the supervised run
  (`M5l-195`), and **two documents' text on the P-3k gate** still read closed after the owner
  had ruled it satisfied (`M5l-175`).
- **The 229 s stall's cause is not the consumer's own code** (`M5l-196`), which narrows it
  and measures nothing more (`M5l-198`).
- **A first expectation of the observation run's ledger was wrong**: `lifetime_realised`
  moves when a day rolls and not when a booking is made (`M5l-254`).

### What did NOT happen

- **Live trading was not enabled and was not brought closer.** Every commission any M5l capture
  records is `0.00000000`, the observation run's included, so the fee capture is unmet and no
  non-zero fee was ever netted outside a test; base-quantity netting is unbuilt. The two gates
  the owner's M5k ruling names are the ones that remain, and `refuse_live_trading` is unchanged.
- **No protective leg filled in the observation run**, ETHUSDT never opened a position and
  nothing restarted in it, so the emitters M5l added for feed health were quiet and are shown
  to raise no false alarm, not to fire (`M5l-252`).
- **Whether Binance omits a kline for an interval with no trades** was not measured, since
  neither committed pair had a zero-trade bar (`M5l-202`, `M5l-251`), and the stall's cause
  (`M5l-198`) is still unmeasured.
- **A timer-driven reconciliation, a REST backfill, the confirm-step ruling (five calls or
  four), the request weight and the trailing-stop milestone** were not done; each is carried
  with its condition.

### What the rotation's steps found

- **Step 1** (`810eaa3`): the seven standing authorities, the owner's rulings and the records of
  them, lived in the one file the rotation rewrites; they now stand in `CLAUDE.md` verbatim
  (`M5l-244`, `M5l-257`).
- **Step 2** (`456d38b`): the 18 gate-count lines had not moved since before M5l while the
  suite grew from 1956 to 2010 to 2148 passed (`M5l-124`, `M5l-160`, `M5l-258`).
- **R3** (`ad24ace`): five rule citations by bare letter became quotations. `M5l-013` turned out
  to be part wrong, because the lettered list had been in this file since `31f03d4`
  (`M5l-259`, `M5l-260`).
- **R5** (`9fc8b8d`): 23 declared false or unedited sentences were checked by content, 8 already
  fixed, 8 already annotated, 2 not false text, 2 annotated, and 3 carried because they live in
  `src/` or `tests/`, plus one new one in `dispatch_budget.py` (`M5l-261` to `M5l-264`).
- **Step 3** (`d8724dd`, `6937c89`, `e531822`): the file was 1,999 changed lines, so it was split
  three ways; seven owner rulings that stood only inside struck items were lifted verbatim; and
  the owner's P98 list named U10 a blocker where the owner's P87 ruling says it is not a gate
  (`M5l-265` to `M5l-273`).
- **Step 4 and the mode-3 pass** (`5bd8575`): three real firings of two conditions, U0 and U3, had
  never been recorded; ten of the thirteen firings the instrument could not tie to a commit were
  artifacts of what the condition named (`M5l-274` to `M5l-277`).

### The method rules, keyed

The twelve rules the M5k entry above lists as (a) to (l) are in `CLAUDE.md`, each under the
heading below, so a letter cited in `docs/PHASE_HISTORY.md` can be followed without leaving this
file's pointers. (a) *"ANY TEXT A CHANGE MAKES FALSE IN A FILE IT IS AUTHORISED TO EDIT IS
CORRECTED OR ANNOTATED IN PLACE, AND LISTED"*; (b) *"A MUTATION SURVEY RUNS ONLY IN A
DISPOSABLE WORKTREE OUTSIDE THE REPOSITORY"*; (c) *"AND THE FORMATTER RUNS BEFORE THE SURVEY"*;
(d) *"A SEARCH FOR A SENTENCE A CHANGE MAY FALSIFY TOLERATES EMPHASIS AND LINE BREAKS -- AND DOES
NOT STRIP `_`"*; (e) *"EVERY `git diff` AND `git show` NAMES ITS PATHS"*; (f) *"A MISS IS NOT
SYMMETRIC"*; (g) *"AMENDED AT M5k's ROTATION, BY ANNOTATION: THE AUDIT READS EVERY DOCUMENT
THAT CARRIES AN ARMING CONDITION"*; (h) *"A DIFF OVER 1,500 CHANGED LINES HALTS, AND THE COMMIT
IS SPLIT"*; (i) *"READ A LOG FIELD THROUGH `vars(record).get(key)`, AND ASSERT A LENGTH BEFORE
INDEXING"*; (j) *"`DOCUMENTED` IS A FOURTH MARK"*; (k) *"A RULING ID IS QUALIFIED BY THE PROMPT
THAT GAVE IT"*; (l) *"AT M5k's ROTATION: `scripts/check_gate_counts.py` RUNS TWICE, OUTGOING
FIGURES FIRST"*. Rule (h) was used for the first time as a split at this rotation, where it
turned one file's rotation into three commits of 843, 454 and 780 changed lines.

### The architect's own errors, by class

Counted over the findings declared by this commit's parent, by the sentence each carries: **14
say "Owned by the architect" in so many words, 15 with `M5l-013`, whose text names the architect's
drafts, and 16 with `M5l-059`, shared with the implementer.** By class:
- **A rule cited by a paraphrase or a bare label instead of its text: 2**, `M5l-013` and
  `M5l-027`, the second quoting a ceiling as a total when the ruling counts per commit.
- **An authorisation drawn from testimony and not from a grep, or omitting a file or authority it
  needed: 4**, `M5l-032`, `M5l-079`, `M5l-131` and `M5l-132`, with `M5l-059` shared. The standing
  authorities and the widened file list are the fix.
- **A ruling or draft that changed a pinned test without authorising it, or confirmed a ruling
  without deriving what it collided with: 3**, `M5l-115`, `M5l-126` and `M5l-127`. The
  ruled-overturn authority is the fix.
- **A derivation or draft error caught before any code: 6**, `M5l-074`, `M5l-078`, `M5l-083`,
  `M5l-091`, `M5l-093` and `M5l-095`, each a bound, a comparison or a locked-text draft stated
  without its precondition.
Fourteen of the 280 declared findings own an error of the architect's outright, and each was
caught by a halt or a measurement and not by review of the prompt. One more, `M5l-145`, records a
prediction of the architect's P82 table that the code cannot produce and does not say whose it
was, so it is not counted. The instrument is `grep` over the declared findings' text, so it counts
what a finding SAYS and not what it should have said.

### What carries into M5m

The scope is **not decided**, and the owner's order for the first three is N6, U9 and U10, the
items that block live trading, with a discrepancy the owner holds: P98 lists U10 among them and
the P87 ruling says it is not a gate. Carried, each with its caller-named arming condition, in
`docs/NEXT_MILESTONE.md`: K1 to K5 (the store's two reusers, P-3k's three residues, four
pre-existing false sentences in `src/` and `tests/`, the stall's cause, the natural-gap rate of a
new pair); P-3i's request weight; P-3m's starvation and churn; P-3n with U7, the confirm-step
ruling; N1 to N6; U0 to U12; A1 to A3, A5 and A6; the `M5i` items, with the unpack sweep at 17
sites; W1 to W6; X2b, `HALT` never observed in 16 more close plans; and the blocked trailing-stop
milestone.

### The historical figures in this entry

**Pinned to their commits, not a live count.**
- **At `5bd8575`**, the last commit before this one: `ruff format` 142 files, `mypy` 84 source
  files, 2148 passed and 1 skipped with Testnet credentials (2145 and 4 derived); 277 findings
  and 73 commits.
- **At this rotation's gate**: the same 142 / 84 / 2148 passed, 1 skipped, credentialed, since
  the rotation changed no `.py` file; 280 findings and 74 commits including this one.
- The captures the rotation read are SHA-256 `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`
  (the evidence run), `bcf01bb15b54c08e1db6b6049c680b49ba3177406ce7c0bed7191b0d14825cf3` and
  `85e1c64391089b1f425ae0efe3954aa705a271d2369ac4bab85ad425871c71bb` (the P-3k clones' logs) and
  `023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb` (the observation run).

**M5l's scope, the P-3 order, the P-2 re-ruled text, P-3k's design questions and its gate, the call-cap
sketch, the deferrals, the standing authorities and the P98 rulings were the project owner's;
everything else was ruled by the architect or by the reviewer under delegation.**

## Phase 5 M5m — a strategy that loses, a backtester trusted for what it was tested on, and a live run that measured the engine's own latches

M5m outcome. The shipped 1m SMA-crossover strategy loses gross and net (S5). All six S6 candidates lose in sample. S7 is FAIL by ruling R-CV, with the reserved window unread. S4, the pre-registered live-versus-backtest comparison on Testnet: A PASS, B FAIL (latch-caused), C PASS with 270 of 271 live entries reproduced (99.63 percent). Its four unexplained disagreements are live-feed holes of one or two bars after websocket drops (M5m-761 to M5m-772). The backtester is confirmed as an instrument for entry reproduction and the per-trade mean. Its stop-fill model diverges from Testnet on thin-book wicks: all 7 different exits are R-DR wide=yes. The largest live-versus-backtest divergences are the live engine's own fail-closed protective-leg latches (U10) and feed holes (U12). Live trading stays blocked.

**M5m is complete, in 178 numbered commits and 6 rotation commits (this one included), with 787 findings declared across `M5m-001`–`M5m-787`, every commit but the owner's merge `934eb45` carrying a block.** The owner scoped it: stop engine work, build the minimal backtester, prove it against Testnet trades, and test slower strategies on it, ending in a PASS or FAIL decision and not in code (`docs/NEXT_MILESTONE.md`, the M5m section, kept whole). It ended in FAIL. The milestone's weight is that **the question the project had been avoiding was answered by an instrument built to answer it, with the answer fixed before the instrument ran**: pre-registrations, frozen digests, predictions committed before measurements, and one reserved window never opened.

### The commits

Numbered commits are `milestone/M5l..ddf3593` in order, and include the owner's merge `934eb45` (row 2) and two M5n charter commits (`543d379` and `ee8d485`, P138 and P139) that landed on `main` before M5m closed. Rotation commits follow the table.

| # | Commit | Subject |
|---|---|---|
| 1 | `70690c1` | docs(next): M5m decided -- validate a strategy before anything else |
| 2 | `934eb45` | Merge pull request #2 from atul-biswash/claude/keen-sagan-ehal28 |
| 3 | `c0d0948` | docs(claude): the venue-outage clause |
| 4 | `7a211d8` | docs(next): the owner's M5m P99 rulings on S0 to S7, as annotations |
| 5 | `cf64d90` | feat(scripts): trade_census, a tracked census of every booked trade (M5m S0) |
| 6 | `27b8724` | test(scripts): the trade census's tests, and the mutation survey that proves they bite (M5m S0) |
| 7 | `228a3a4` | docs: the trade census of record, and what separates it from the untracked census (M5m S0) |
| 8 | `dae147f` | docs(next): the owner's P100 and P101 rulings on S0 to S7, M5m-022 to M5m-041 declared, 2244 measured |
| 9 | `5884629` | feat(data): historical.py, the archive's ingest, verify and gap side (M5m S1) |
| 10 | `d559da7` | test(data): the archive ingest's tests, and the R-F mutation survey of the unit and gap code (M5m S1) |
| 11 | `e0613f9` | feat(data): HistoricalStore, the archive's read side, and its tests (M5m S1) |
| 12 | `3ee39eb` | feat(scripts): download_data.py, the monthly archive downloader, and its tests (M5m S1) |
| 13 | `8aa1514` | fix(scripts): the downloader's host check refused its own listing URL (M5m S1) |
| 14 | `b7059ed` | docs(ledger): the monthly archive download, 980 of 1,100 months stored, 120 refused (M5m S1) |
| 15 | `6e106b2` | feat(data): classify every archive row at ingest, and refuse a month only for an unknown shape (M5m S1) |
| 16 | `e7ae2d5` | feat(data): the registry sidecar, the deep re-check and the gap kinds (M5m S1) |
| 17 | `e236162` | feat(scripts): the downloader keeps every zip and ingests from disk (M5m S1) |
| 18 | `92b493a` | docs(ledger): the 120 refused months ingested from disk, the store complete (M5m S1) |
| 19 | `e96babc` | docs: record the P104 and P105 rulings, the P104 evidence and K7 (M5m S2) |
| 20 | `5a48034` | feat(config): BacktestConfig money fields as Decimal, a half-open UTC window (M5m S2) |
| 21 | `b1ffaa7` | refactor(core): a Dispatcher Protocol replaces the unused OrderExecutor ABC (M5m S2, U6) |
| 22 | `7ae7d0f` | feat(backtesting): the exchangeInfo snapshot, fetched once and loaded through the live mapper (M5m S2) |
| 23 | `42243f2` | feat(backtesting): replay stored bars through the unchanged live provider and engine (M5m S2) |
| 24 | `dbbffad` | feat(backtesting): the fill model, as pure functions (M5m S2) |
| 25 | `41a621a` | test(download): pin the zip fixture's member timestamp; the M18 extra kill was the wall clock (P106 C0) |
| 26 | `f58a79e` | docs: record R-AA to R-AE verbatim, ratify K7, correct one docstring (M5m S2, P106 C1) |
| 27 | `14cb8aa` | feat(backtesting): the simulated executor, sequencing the fill model against the live ledger (M5m S2, P106 C2) |
| 28 | `c1d1d87` | feat(backtesting): the backtest root, the live decision path over stored history (M5m S2, P106 C4) |
| 29 | `d5bff58` | feat(main): the backtest command, with window and symbol flags recorded resolved (M5m S2, P106 C5) |
| 30 | `778e9b3` | docs: the R-AE smoke backtest, March 2024, run twice, and S2 closed (M5m S2, P106 C6) |
| 31 | `7f08f56` | docs: record R-AF to R-AL verbatim and Step 0's results, among them the Testnet klines (M5m S2/S3, P107 C0) |
| 32 | `86576e8` | feat(main): a backtest logs only to a file in its own run directory, never to the bot's log (M5m S2, P107 C1, R-AG) |
| 33 | `1a6de2c` | feat(backtesting): every run record carries the boot_provenance verdict and its fields (M5m S2, P107 C2, R-AH) |
| 34 | `13297bb` | feat(backtesting): quarterly regime labels, the module and the script that writes them once (M5m S3, P107 C4a, R-AI) |
| 35 | `f9d0c57` | docs: the quarterly regime labels, committed with their digest and fixed before S6 (M5m S3, P107 C4b, R-AI) |
| 36 | `1cc92ab` | feat(backtesting): the S3 metrics, pure: trades, fees, drawdown, Sharpe, Sortino, exposure, holding, breakdowns (M5m S3, P107 C5) |
| 37 | `6748b94` | feat(backtesting): the root samples equity in its loop and records the S3 metrics (M5m S3, P107 C6, R-AJ) |
| 38 | `c5e11f1` | test(backtesting): the Q2 survey of metrics.py, three tests it would have mis-scored fixed first (M5m S3, P107 C6b) |
| 39 | `df3dd21` | docs(ledger): the smoke backtest on the C6 code, its metrics recomputed exactly and hand-checked (M5m S3, P107 C7) |
| 40 | `c258295` | docs: record R-AM to R-BB, annotate the stale band text (R-AU), and log P108 Phase 1's measurements (M5m S4, P109 C1) |
| 41 | `966be69` | feat(data): the Testnet kline recorder, as a library with an injected fetcher (M5m S4, P109 C2a, R-AN) |
| 42 | `4019d68` | feat(scripts): the Testnet kline recorder script and its scheduler definition, first run recorded (M5m S4, P109 C2b, R-AN, R-AW) |
| 43 | `13bd70e` | fix(indicators): sma is window-only, so a tie no longer depends on the buffer's length (M5m S4, P109 C3, R-AQ, R-AX) |
| 44 | `524d53a` | feat(backtesting): evidence_eligible and the one door that refuses a record that is not evidence; a quiet backtest console (M5m S4, P109 C4, R-AR, R-AS) |
| 45 | `265f902` | fix(scripts): the survey's summary ids are node ids, and every saved M5m survey log re-parsed (M5m S4, P110 C1, R-BC) |
| 46 | `133515b` | docs: R-BC to R-BH recorded; the printed backtest line removed, main.py under the evidence census, the rich docstring corrected, bollinger_bands carried (M5m S4, P110 C2, R-BD, R-BE, R-BF, R-BG) |
| 47 | `9210d38` | feat(config): S4's backtest plumbing -- exchange_info_environment, config.s4.yaml and the test that pins its difference (M5m S4, P110 C3) |
| 48 | `a18f1b4` | feat(scripts): s4_compare.py, the core -- both records through the evidence door, the match key, R-C's three figures, figures and no verdict (M5m S4, P110 C4a) |
| 49 | `6778445` | feat(scripts): s4_compare.py, the diagnosis -- bot downtime excluded on both sides, signal and refusal disagreements with one cause each, ties and gaps from the recorded closes, surveyed (M5m S4, P110 C4b, R-BA) |
| 50 | `ceaaa9b` | docs: the Testnet clearing of R-AV carried out, the account before and after, config.s4.yaml's measured balance and the snapshot copy (M5m S4, P110 C5) |
| 51 | `e248a73` | docs: S4's pre-registration -- the start, the stop, the window, the parameters, the tests and every frozen digest, committed before the run (M5m S4, P110 C6, R-AO, R-AY, R-AZ, R-BA, R-BB) |
| 52 | `45547f1` | docs: the owner's rulings R-BI to R-BK recorded, the log rotation measured against the 35-day run, the pre-registration unchanged (M5m S4, P111 C1) |
| 53 | `af51911` | docs: S4 launched at 2026-10-10T06:05:20Z, the recorder and the retirement recorded, R-BJ corrected by R-BL and the capture's reassembly ruled by R-BM (M5m S4, P112 C1) |
| 54 | `0a5cb54` | docs: the S5/S6 foundation ruled -- R-BN to R-BT recorded, the research protocol with every candidate family and its full grid committed before any S5 run exists, M5m-302 added to U10 (M5m S5/S6, P113 C1) |
| 55 | `d9045c1` | feat(backtesting): the run record carries its effective settings and their digests, and the evidence door refuses a record without them (M5m S5/S6, P113 C2a, R-BR) |
| 56 | `31e9363` | feat(backtesting): --stop-slippage, --strategy, --timeframe and --param on the backtest command, validated before a run directory exists (M5m S5/S6, P113 C2b, R-BR) |
| 57 | `c211359` | docs: S4's interruptions to 2026-10-14 recorded -- an ungraceful close, a refused restart, a held ETH position and a machine that restarts itself (M5m S4, P113, R-BN) |
| 58 | `e5af2df` | feat(backtesting): the research protocol's guard core -- its declaration parsed, its windows classified, its grid and its entries checked (M5m S5/S6, P113 C3a, R-BT) |
| 59 | `caa75cb` | test(backtesting): the research protocol's guard is tested -- every refusal, the order of the checks and the three arms of a candidate (M5m S5/S6, P113 C3b, R-BT) |
| 60 | `478a746` | feat(backtesting): the research-protocol guard runs before any backtest directory exists, and the run record carries what it decided -- schema 6 (M5m S5/S6, P113 C4, R-BT) |
| 61 | `79ae42f` | feat(strategies): an optional trend filter on both shipped strategies -- an entry only while the close is above its SMA (M5m S5/S6, P113 C5, R-BS) |
| 62 | `9aa320b` | feat(scripts): S5's report -- in-sample and out-of-sample figures separately, through the evidence door, and no verdict (M5m S5/S6, P113 C6, R-BT) |
| 63 | `2d37258` | docs: the canonical frozen mainnet store recorded -- copied, verified month by month, write-protected -- and the Q2 survey's evidence (M5m S5/S6, P113 C7, R-BQ) |
| 64 | `67b7563` | docs: the S4 interruption resolved -- the owner's sale and release, the restart as pid 25352, and U10's three Testnet cases (M5m S4, P114 C1, R-BU, R-BV) |
| 65 | `dfb5916` | docs: S5 complete -- the baseline loses in sample gross and net, R-BW and R-BX recorded, the sizing floor and the frozen function's rule measured (M5m S5, P115 C1, R-BW, R-BX) |
| 66 | `09d697d` | test(protocol): the s5-baseline entry is marked read with its three records' digests, and a fresh clone's guard refuses a second read (M5m S5, P116 C1, R-BY, R-BZ) |
| 67 | `66f64ce` | docs(protocol): amendment 2 -- selection on per-trade returns, the ruin and 250-trade rules, the walk-forward report, the freeze and S7's two profit factors (M5m S6, P117 C1, R-CA to R-CJ) |
| 68 | `8bee34c` | test(protocol): the committed-baseline tests select S5's entry by id, so candidate entries can join the directory (M5m S6, P117 C2, R-CI) |
| 69 | `35d6b38` | feat(backtesting): S6's selection -- the return profit factor, the eligibility rules, the tie-break, the ledger and the walk-forward report (M5m S6, P117 C3a, R-CB to R-CG) |
| 70 | `d96045b` | test(backtesting): the selection over 216, the walk-forward, reading a run and the output are tested, and the targeted survey of the statistic, eligibility and tie-break (M5m S6, P117 C3b, R-CB to R-CG) |
| 71 | `119b25c` | feat(scripts): s6_select -- read the in-sample sweep, choose a candidate per cell, print the walk-forward report, write the selection file unedited (M5m S6, P117 C4, R-CB to R-CG) |
| 72 | `6b26c97` | feat(scripts): s6_sweep -- the in-sample sweep, resumable after a power cut, parallel only after R-CH's check, every variant in a manifest (M5m S6, P117 C5, R-CG, R-CH) |
| 73 | `9fd2e2e` | test(protocol): an in-sample run over a grid point names its variant in the record the engine writes, and the selection reads that record back (M5m S6, P117 C6) |
| 74 | `4dc445a` | feat(backtesting): S7's gate -- the five thresholds at the gate arm, both profit factors, and nine refusals, each tested one broken field at a time (M5m S7, P117 C7a, R-CJ, R-BW) |
| 75 | `8e17898` | feat(scripts): s7_gate -- judge every candidate read out of sample, withhold every verdict on any refusal, and the targeted survey of the gate (M5m S7, P117 C7b, R-CJ) |
| 76 | `a417700` | fix(scripts): the sweep's timing probe times both strategies, and the selection refuses a run made under another protocol digest (M5m S6, P117 C7c) |
| 77 | `9d6d519` | docs: the S6 and S7 tooling is recorded -- P116's measurements, the build record, the owner's steps O1 to O6 and the research log (M5m S6/S7, P117 C8) |
| 78 | `7f86953` | feat(scripts): s6_rehearsal -- the narrowed protocol and the pure helpers of the S6/S7 chain rehearsal, split from its orchestration (M5m S6/S7, P118 C1a, R-CL) |
| 79 | `2f44ae2` | feat(scripts): s6_rehearsal -- the rehearsal's orchestration: a throwaway worktree, the real commands hop by hop, each recorded against its prediction (M5m S6/S7, P118 C1b, R-CL) |
| 80 | `62c21ae` | fix(scripts): s6_rehearsal -- an invocation keeps its evidence under its own label, and a cleanup numbers its hops after the run's (M5m S6/S7, P118 C2a) |
| 81 | `93e98e7` | fix(backtest): a run that reads a working-directory stamp a peer already holds takes a later one, instead of dying on FileExistsError (M5m S6, P118 C2b) |
| 82 | `d198631` | feat(scripts): s6_rehearsal -- a --window flag, a default window wholly inside the real in-sample period, and a refusal of any window that reaches the real out-of-sample one (M5m S6/S7, P118 C2c) |
| 83 | `da094f8` | feat(scripts): s6_rehearsal -- the default out-of-sample window is the whole of 2020, because a quarter can give a candidate no losing trade (M5m S6/S7, P118 C2d) |
| 84 | `7fec073` | docs: the rehearsal of the S6/S7 chain is recorded -- the final run with its digests, R-CK and R-CL, the corrected install step O1 and the missing O7 (M5m S6/S7, P118 C3) |
| 85 | `a03d5c9` | docs(research): amendment 3 -- two variants ruled ineligible for selection, R-CM to R-CQ recorded, and the figures that were seen (M5m S6, P119 C1, R-CM) |
| 86 | `4a8ec1a` | feat(scripts): s6_mark_read -- owner step O7, an entry becomes read from its three verified records, all entries or none (M5m S6/S7, P119 C2, R-CP) |
| 87 | `13c780e` | fix(scripts): s6_sweep -- a worker that was lost and whose variant was recovered is reported as lost and recovered, and the sweep reports COMPLETE (M5m S6, P119 C3, R-CQ) |
| 88 | `365d767` | feat(scripts): s6_rehearsal -- owner step O7 is driven through s6_mark_read.py, and the rehearsal holds no marking code of its own (M5m S6/S7, P119 C4a, R-CP) |
| 89 | `708a65f` | docs(ledger): section 53 -- the rehearsal re-run with step O7 driven through s6_mark_read.py, 112 of 112 hops matched, and what it did not cover (M5m S6/S7, P119 C4b, R-CP) |
| 90 | `cf47421` | docs(next-milestone): the owner's steps O1 to O7 and the gate in one place, each with its CHECK, O3's CHECK as R-CQ makes it, and which PowerShell has been run (M5m S6/S7, P119 C5, R-CM to R-CQ) |
| 91 | `0f42027` | docs: the sweep, the S4 restart of 2026-10-15, and O7 and the gate moved to the development tree (M5m S6/S7, P120 C1, R-CR, R-CS, R-CT) |
| 92 | `8621c64` | feat(scripts): s7_null -- the chance that a strategy with no edge passes S7, computed by Monte Carlo from each candidate's own in-sample trades (M5m S6/S7, P120 C4, R-CS) |
| 93 | `b5f7547` | docs(research): the S7 null check's output on the six candidates, and the reading it asks for before O6 (M5m S6/S7, P120 C4, R-CS) |
| 94 | `2e00dcc` | feat(selection): the selection file is JSON Lines, one record a line, and no pick or digest changes (M5m S6, P121 C1, R-CU) |
| 95 | `bdd95e4` | research: the S6 selection, regenerated in the line-per-record format, committed unedited (M5m S6, P121 C2, R-CU, R-CV) |
| 96 | `f9c06a4` | docs: S7 recorded as FAIL without an out-of-sample read, the reserved window unread, O5 to O7 and the gate not taken, and the S4 restart corrected (M5m S6/S7, P121 C3, R-CU, R-CV, R-CW) |
| 97 | `15de39c` | docs: R-CX to R-CZ recorded, P121's T0 corrected to the run boot, the selection file's old name annotated, and M5m-510 carried with its arming condition (M5m S4/S6, P122 C1, R-CX, R-CY, R-CZ) |
| 98 | `4401670` | fix(scripts): the rehearsal names the selection file selection.jsonl, with a test that fails on the old name (M5m S6, P122 C2, R-CY) |
| 99 | `8bd39b4` | feat(scripts): s4_daily -- the owner's read-only daily check of the S4 run, freezing every log file outside every clone, and reporting without a verdict (M5m S4, P122 C3a, R-CZ) |
| 100 | `fd79692` | test(scripts): s4_daily -- the process status, the recorder's store, the two PowerShell seams and the whole report, each pinned by a mutation (M5m S4, P122 C3b, R-CZ) |
| 101 | `ac07c44` | docs: the first run of scripts/s4_daily.py against the live S4 run, 84 bookings and 6.003 days from T0, every figure inside its prediction (M5m S4, P122 C4, R-CZ) |
| 102 | `78e6304` | docs: the S4 stop runbook, nine steps each with its CHECK and the commands no run has executed, and R-DB and R-DC recorded (M5m S4, P123 C1, R-DB, R-DC) |
| 103 | `d05e8cb` | feat(scripts): s4_explore -- S4's excluded intervals under the frozen rule and a corrected one, and the entries each excludes, exploratory and never a replacement for s4_compare (M5m S4, P123 C2, R-DC) |
| 104 | `66bfc9b` | docs: the first run of scripts/s4_explore.py on a fresh copy of the S4 log, 42:15:04 excluded under the frozen rule and 41:36:16 under the corrected, and the comparable-count arithmetic (M5m S4, P123 C3, R-DC) |
| 105 | `97efce3` | feat(scripts): store_check -- the store checker the S4 stop uses, tracked and tested, equal to the scratch one on the mainnet store and on a copy of the recorder's; R-DD, R-DE and R-DF recorded (M5m S4, P124 C1, R-DD, R-DE) |
| 106 | `cef23c7` | docs: Appendix A of the S4 stop runbook executed over 2026-10-11 -- an eligible backtest of config.s4.yaml and s4_compare.py on real inputs, both exit 0, the clone removed; the runbook's N rows made E (M5m S4, P124 C2, R-DF) |
| 107 | `df82ebe` | docs: the S4 runbook archives its evidence before any removal and writes every file a script reads in ASCII, and names its install procedure and the run that measured it (M5m S4, P125 C1, R-DG, R-DH) |
| 108 | `7ec055f` | test(integration): the live market-data test asserts what holds on both paths -- the buffer's last bar is the stream's closed bar, appended or replaced, identical or not (M5m S4, P126 C1, R-DI) |
| 109 | `d6c1c5a` | docs: every program the S4 runbook pipes into Out-File -Encoding ascii is shown to print only ASCII, and the boot is run from the backtest clone (M5m S4, P126 C2, R-DJ) |
| 110 | `7f63985` | docs: P128's halts and the predictions for the S4 latch measurements, written before the 2026-10-23 capture is parsed (M5m S4, P128 C1, R-T) |
| 111 | `b3d4f8b` | docs: the S4 correction file for the latch -- R-DK to R-DN verbatim, the three episodes R-DM finds, and what the measurements say about B (M5m S4, P128 C2, R-DK, R-DL, R-DM, R-DN) |
| 112 | `4e1bef9` | docs: RUN_LEDGER section 66 -- the clean stop of pid 14600 at 2026-10-23T08:05:33Z, the latch on order 5431129, and the P128 episodes (M5m S4, P128 C3) |
| 113 | `0586f48` | docs: NEXT_MILESTONE -- order 5431129 is U10's fourth Testnet case, and P128's rulings with the items they carry (M5m S4, P128 C4) |
| 114 | `ed750f6` | docs: P129's halts, a correction to section 66's capture size, and the predictions for the R-DO measurements, written before the 190521Z capture is parsed (M5m S4, P129 C1, R-T) |
| 115 | `1bd0db7` | docs: the S4 correction file for R-DO -- the end of a latch run, P128's episodes re-measured, and B recomputed with all three (M5m S4, P129 C2, R-DO) |
| 116 | `22e9b3f` | docs: RUN_LEDGER section 67 completed -- the owner's restart of 2026-10-23, boot #7 (pid 20100), the downtime rule, and the predictions scored (M5m S4, P129 C3) |
| 117 | `33d6765` | docs: NEXT_MILESTONE -- R-DO verbatim, what it and the restart resolve of P128's carried items, and the U10 sentence the sale makes false (M5m S4, P129 C4) |
| 118 | `3fd0ef5` | docs: the S4 correction file for R-DP -- the break test is the trust set the bot refuses entries by (M5m S4, P130 C1, R-DP) |
| 119 | `e4e12a4` | docs: P130's halts, the step-0 halt, and the predictions for the E2 wrapper, with a disclosure that a draft already existed (M5m S4, P130 C2, R-T) |
| 120 | `c254740` | feat(scripts): s4_latch_compare -- the E2 wrapper, S4's comparison with the owner's latch intervals excluded as well as downtime, figures only (M5m S4, P130 C3, R-DL, R-DM, R-DO, R-DP) |
| 121 | `8a570fd` | test(scripts): the E2 wrapper on synthetic fixtures -- the episodes, the coverage rule, R-DP, the union, both-sided exclusion and the 13:09 label (M5m S4, P130 C4, R-DL, R-DP) |
| 122 | `4714d11` | test(scripts): the E2 wrapper's tests assert a length before reading an episode, and pin three behaviours the survey plan found unpinned (M5m S4, P130 C5) |
| 123 | `a923f63` | test(scripts): the E2 wrapper's argument test compares its help with the frozen tool's, not only an exit status (M5m S4, P130 C6) |
| 124 | `4062ccb` | test(scripts): two attach tests that could not tell a wrong process from the right one, or failed by a crash, now can (M5m S4, P130 C7) |
| 125 | `5a7891c` | fix(scripts): the E2 wrapper calls the evidence door itself, as the repository's own scan requires (M5m S4, P130 C8) |
| 126 | `21358d2` | docs(counts): the gate figures after the E2 wrapper and its tests -- 230 files formatted, mypy over 113, 4463 credentialed (M5m S4, P130 C9) |
| 127 | `cc82563` | docs(runbook): step 7b, the two exploratory comparisons of R-DL, run after the primary and reported beside it (M5m S4, P130 C10) |
| 128 | `7451d01` | docs(next-milestone): the E2 wrapper's arming condition discharged, R-DP recorded, and the 13:09 entry's fill established (M5m S4, P130 C11) |
| 129 | `7e09636` | docs(ledger): section 68 completed -- the arming audit by test and by mutation, the predictions scored, and P130's process disclosures (M5m S4, P130 C12) |
| 130 | `908fe9f` | docs(ledger): section 69, P131's halts and the predictions for the stop rehearsal of runbook steps 6 to 7b, before any step is run (M5m S4, P131 C1, R-T, R-DQ) |
| 131 | `aead848` | docs(runbook): the step 6 boot CHECK reads the joined record, the 6a time estimate is measured, and steps 6b, 7 and 7b are marked executed for mechanics only (M5m S4, P131 C2) |
| 132 | `0f84d50` | docs(ledger): section 69 completed -- the rehearsal's eighteen commands with exit, wall time and digest, the predictions scored, and what it found (M5m S4, P131 C3, R-DQ) |
| 133 | `7ef7d5b` | docs(next-milestone): R-DQ recorded verbatim, with what it corrects in P131's description of it (M5m S4, P132 C1, R-DQ) |
| 134 | `1176776` | docs(claude): the every-commit gate rule annotated with a pointer to R-DQ (M5m S4, P132 C2, R-DQ) |
| 135 | `7a2981e` | docs(runbook): the step 8 report carries the 13:09 note and R-DK's wording, and the rehearsal clone is retained with a safe junction removal (M5m S4, P132 C3) |
| 136 | `337de24` | docs(ledger): section 70, P133's halts and the predictions for the 2026-10-23 ETHUSDT zero-executed expiry, before any measurement (M5m S4, P133 C1, R-T, R-DQ) |
| 137 | `379b2d8` | docs(ledger): section 70 completed -- list 218102's zero-executed expiry of 2026-10-23, every fact by timestamp, the predictions scored, and the wick it coincides with (M5m S4, P133 C2) |
| 138 | `9ee6b67` | docs(next-milestone): list 218102 added to U10 as a fifth Testnet case, the first with nothing executed and the first cleared without an operator (M5m S4, P133 C3) |
| 139 | `551da8b` | docs(ledger): section 71, P134's halts and the predictions for the stop-leg types of three order lists and the wide-bar threshold sensitivity, before any measurement (M5m S4, P134 C1, R-T, R-DQ) |
| 140 | `eaff03a` | docs(ledger): section 71 completed -- the capture records no stop-leg type for lists 218102, 183218 and 71012, and the wide-bar counts by threshold (M5m S4, P134 C2) |
| 141 | `9d15480` | docs: the S4 correction file for R-DR -- a wick annotation on the stop report's disagreements, with its threshold sensitivity (M5m S4, P134 C3, R-DR) |
| 142 | `7d95de4` | docs(runbook): the step 8 report carries list 218102's expected fill-model disagreement and the required R-DR annotation (M5m S4, P134 C4) |
| 143 | `d2fab1e` | docs: the S4 correction file for R-DS -- the interval of the R-DR wick annotation is the union of the holding periods (M5m S4, P135 C1, R-DS) |
| 144 | `4f757ea` | docs(ledger): section 72, P135's halts and the predictions for scripts/s4_wick_annotate.py, before any code (M5m S4, P135 C2, R-T, R-DQ) |
| 145 | `526002f` | feat(scripts): s4_wick_annotate -- the R-DR/R-DS wick annotation of a disagreement list, for the primary, E1 and E2, figures-free and verdict-free (M5m S4, P135 C3, R-DR, R-DS) |
| 146 | `af9ccc4` | test(scripts): the R-DR/R-DS wick annotation on synthetic fixtures -- the interval of each kind, the half-open edges, the strict 3% bound, the counts by cause and the three analyses against their sources (M5m S4, P135 C4) |
| 147 | `766b1e4` | docs(ledger): section 72, the arming audit's predicted kills for s4_wick_annotate.py, before the survey is run (M5m S4, P135 C5, R-T, R-DQ) |
| 148 | `da3a8b5` | docs(next-milestone): U10 records that the stop legs are market-type and gives the thin-book expiry its reasoned mechanism, with the venue read deferred to after M5m (M5m S4, P135 C6) |
| 149 | `51cd7b4` | docs(runbook): step 8's R-DR annotation is made by scripts/s4_wick_annotate.py -- the by-hand instruction and its "no live position" text replaced by the tool's three commands, each with its CHECK (M5m S4, P135 C7) |
| 150 | `dcb66b7` | docs(counts): the gate figures after the wick-annotation tool and its tests -- 232 files formatted, mypy over 114, 4515 credentialed; the scripts list names the two S4 tools it missed (M5m S4, P135 C8) |
| 151 | `811fd09` | docs(ledger): section 72 completed -- the arming audit's 52 mutations all matched, the four tests no mutation kills, a mechanics check on the real store (M5m S4, P135 C9) |
| 152 | `8043049` | docs(ledger): section 73, P136's halts, the trace of a store read error, and the predictions for closing P135's six test gaps, before any code (M5m S4, P136 C1, R-T, R-DQ) |
| 153 | `e0c3e1a` | fix(scripts): a store that is there and cannot be read refuses the wick annotation run instead of reading as unknown (M5m S4, P136 C2) |
| 154 | `e9aa993` | test(scripts): twelve tests close the wick annotation's six gaps and pin the store-error refusal -- an ETHUSDT 5m end-to-end, the 5m exit-bar close, E2's frozen downtime, a live entry open at M, a naive instant, an extra cause, a store error (M5m S4, P136 C3) |
| 155 | `146f920` | docs(ledger): section 73, the predicted kills for the closed gaps and the re-anchored m43, before the survey is run (M5m S4, P136 C4, R-T, R-DQ) |
| 156 | `bcfc8b4` | docs(counts): the pytest figures after the twelve new wick-annotation tests -- 4527 credentialed (M5m S4, P136 C5) |
| 157 | `33ad5dd` | docs(ledger): section 73 completed -- the six gaps closed, m43 settled, 54 mutations with no FEWER, and the mechanics re-check unchanged (M5m S4, P136 C6) |
| 158 | `e8c820b` | docs: P135's correction file records that its operational exit-bar rule is ratified, with the ruling's words not supplied (M5m S4, P136 C7) |
| 159 | `a2e95fe` | docs: P135's correction file carries the ratification text verbatim under its section 5 (M5m S4, P137 C1) |
| 160 | `8c3bc5c` | docs: the stop runbook freezes the E2 and annotation tools, adds the R-DR counts and the pre-stop latch check (M5m S4, P137 C2) |
| 161 | `543d379` | docs: M5n charter draft, marked DRAFT until M5m closes (M5n, P138 C1) |
| 162 | `ee8d485` | docs: the M5n charter records D1 to D4, R-DT and the owner's two answers; check_findings needs no change (M5n, P139 C1) |
| 163 | `24eab08` | docs(ledger): section 74, P150a's halts and the predictions for the pid 20100 resource fault, before the capture is measured (M5m S4, P150a C1, R-T, R-DQ) |
| 164 | `cda8bfb` | docs(ledger): section 75, latch episode 4, the owner's sale, the release, boot #8 and the pid 20100 resource fault, measured (M5m S4, P150a C2) |
| 165 | `b2bf5e5` | docs: S4 correction P150a records R-EC, the resource fence, and R-ED, the resource-fault windows, verbatim (M5m S4, P150a C3) |
| 166 | `f16107c` | docs: the stop runbook's step 8 requires R-ED's listing as its sixth item (M5m S4, P150a C4) |
| 167 | `7ab3d6c` | docs: order 7022204 is U10's sixth Testnet case (M5m S4, P150a C5) |
| 168 | `9197be3` | docs: S4 correction P150b records R-ED-1, the window start, the listing and the architect-owned premise, verbatim (M5m S4, P150b C1) |
| 169 | `ffdfcf5` | docs(ledger): section 76, section 75's windows re-started under R-ED-1 (M5m S4, P150b C2) |
| 170 | `b8977bd` | docs: the stop runbook's step 8 item 6 cites R-ED-1 for the window start and the twice-made listing (M5m S4, P150b C3) |
| 171 | `5cdf75e` | docs: S4 correction P151 records the ratification of R-ED's points 3 and 4, verbatim (M5m S4, P151 C1) |
| 172 | `297d5fe` | docs(ledger): section 77, the S4 stop's records: the final capture, boots 9 to 11, the latch and fault windows and the restart exclusion, before any backtest (M5m S4, P151 C2, R-DQ) |
| 173 | `f16a3ee` | docs(ledger): section 78, the predictions for the stop's comparison, before the backtest runs (M5m S4, P151 C3, R-T, R-DQ) |
| 174 | `c001f8b` | docs(ledger): section 79, the S4 stop's comparison: steps 5 to 8a, the step 8 report and the predictions scored (M5m S4, P151 C4) |
| 175 | `341da3d` | docs(ledger): section 80, P152's halts and the predictions for diagnosing the four unexplained entries, before any measurement (M5m S4, P152 C1, R-T, R-DQ) |
| 176 | `f1eb625` | docs(ledger): section 81, the four unexplained entries diagnosed, the 2026-10-29 feed gap post hoc, step 9 and the owner's check_testnet (M5m S4, P152 C2) |
| 177 | `a9b780b` | docs: the stop runbook's step 4 CHECK reads "at or after" M minus 1 day, citing P151's finding (M5m S4, P152 C3) |
| 178 | `ddf3593` | docs: the S4 result, the fok-unfilled mislabel record and U13 in NEXT_MILESTONE (M5m S4, P152 C4) |

**Rotation commits (6, this one included).** `e2e5ee2` (QC section 4b: a partly executed stop leg is measured), `6b841fb` (QB Class E fired once), `92763bc` (X2b struck: `decision=halt` occurred 37 times), `0e39631` (ledger section 82: the structural lists, the arming registers, X2b), `8abf2eb` (`NEXT_MILESTONE.md` rotated to M5n: the outcome, the resolved index, the register), and this commit (the build log, `CLAUDE.md`'s Current state, `README.md`, the milestone tag).

### What was built, in order

- **S0, the census.** `scripts/trade_census.py`, tracked and surveyed, replacing an untracked reviewer script: 165 bookings in the census of record, the M5k capture `3f7f551c...`.
- **S1, the archive.** `data/historical.py` (ingest, `HistoricalStore`, gap kinds) and `scripts/download_data.py`: the monthly zips for 1,100 series-months, 980 fetched and 120 ingested from disk, every row classified at ingest and a month refused only for an unknown shape; quarantined spans are never backfilled.
- **S2, the backtester.** `backtesting/`: the live provider and the unchanged engine replayed over stored bars (`replay`, `engine`'s `backtest_system`), a pure `fill_model`, a `simulated_executor` sequencing it against the live ledger, `exchange_info` snapshots, and a `backtest` command that logs only to its own run directory. U6 resolved along the way: a `Dispatcher` Protocol replaced the unused `OrderExecutor` ABC.
- **S3, metrics and regimes.** Pure `metrics.py` (drawdown, Sharpe, Sortino, exposure, breakdowns), equity sampled in the root's loop, and quarterly regime labels fixed once and committed with their digest.
- **S4, the comparison.** A Testnet kline recorder, `evidence_eligible` and the one door that refuses a record that is not evidence, `config.s4.yaml`, `scripts/s4_compare.py` (frozen) and a pre-registration committed before the run. The run: T0 `2026-10-10T06:05:20Z` to the stop `2026-11-01T18:12:18Z`, 11 boots, 313 bookings, four latch episodes. Around it: `s4_daily`, `s4_explore`, `store_check`, the stop runbook (executed in a rehearsal first), the E1 and E2 exploratory comparisons (`s4_latch_compare`), the R-DR wick annotation (`s4_wick_annotate`), and the correction files P128 to P151.
- **S5 and S6, the research protocol.** A guard that classifies windows, grids and entries before any run directory exists (`protocol`, `overrides`, `candidate`, `readmark`), an optional trend filter on both shipped strategies, `s5_report`, the sweep over 216 variants, the selection (`selection`, `s6_sweep`, `s6_select`) and a rehearsal of the whole chain.
- **S7, the gate.** `gate` and `s7_gate`, and `s7_null`, the chance that a strategy with no edge passes. Used once, to record that nothing could.
- **In `src/`, live path.** `sma` became the window-only computation, so a tie no longer depends on the buffer's length (R-AQ, R-AX); `Settings.with_config`; the logger's false rich docstring corrected.

### The decisions, and the alternatives rejected

- **Validate a strategy before any engine work (the owner's instruction).** Rejected: P98's order, the live-blocking items first (N6, U9, U10). They are deferred and not dropped. The reason was MEASURED: the engine booked what the venue did to the strategy's orders, and the venue's answer was a loss once fees exist.
- **The census of record is the tracked tool on the M5k capture.** Rejected: the untracked figures (157 bookings), which the tool reproduces to the digit over their own window. The 8 bookings after it are the whole difference, and "the difference is itself a finding".
- **One code path.** The backtester replays stored bars through the live provider and engine rather than reimplementing the decision path; an incremental frame was not built (R-V), and the backtest applies no cooldown, at parity with a live `cooldown_minutes` that nothing calls (R-X, K7).
- **The gate arm is a 1.20% stop slippage (R-B2).** Rejected: 0.66%, because R-B's "conservative" holds against the median only, and a median of eight values moved by 0.0227 points when a ninth was added.
- **S4 is measured against Testnet, by the owner's option (c), pre-registered with every digest frozen, and the primary is never changed.** Rejected: editing `s4_compare.py` or excluding the latch in the primary (R-BN, R-DK). Latch handling is exploratory, E1 and E2, figures only, and a latch-caused failure is `FAIL (latch-caused)` and never `NOT MEASURED`.
- **Downtime is excluded on both sides and the exclusion is the frozen rule's.** The corrected rule (R-DC, `s4_explore`) is exploratory.
- **Predictions are committed before the measurement and scored as written (R-T, R-DQ).** Rejected: predicting and measuring in one commit. R-DQ adds that no code or test is drafted before the predictions commit about it exists.
- **The research protocol fixes everything before S5 runs.** Every family and its full grid (R-BT); selection on per-trade returns and not USDT (R-CB), with a ruin rule (R-CC), a 250-trade floor (R-CD), the 1.20% arm only (R-CE), walk-forward reported and not gated (R-CF), all 216 variants counted (R-CG), and S7 passing only with both profit factors at least 1.3 (R-CJ). Rejected: selecting on P&L, and gating on walk-forward.
- **S7 is recorded as FAIL without reading the reserved window (R-CV).** Rejected: reading it for the six. Every selected candidate loses in sample on the gate arm (per-trade-return profit factor 0.359 to 0.516, no fold above 1) and each has a null pass probability of 0.0000, so a read could only spend a window that "stays unread for later research".
- **R-ED and R-ED-1, the resource-fault windows.** A window starts 60 s before its fault line, because a dead socket is logged only when its keepalive times out (the first lost bar closed up to 31 s earlier), and the listing is a by-hand join made twice. Rejected: a script before the stop (P150b's Listing ruling, citing R-EC).
- **The four unexplained entries are diagnosed, not relabelled.** The frozen label stays `unexplained`; the diagnosis is a ledger section.

### What measurement overturned

- **The untracked census** (S0): 157 bookings against 165, -157.72 against -192.03 realised.
- **"Conservative"** (R-B2): true against the median only.
- **`decision=halt` has never occurred** (M5j, M5k, and `CLAUDE.md`'s four narrative blocks): 37 of 339 close plans in the S4 capture, the first at `2026-10-21T13:38:02Z` (`M5m-775`).
- **QC section 4b's "a leg executed partially is UNMEASURED":** four occasions and a fifth shape with nothing executed (`M5m-773`).
- **The architect's prediction that the 31 failed passes cluster in the memory squeeze:** they were request timeouts and one DNS failure, a day and more earlier (`M5m-715`, `M5m-730`).
- **Test C's range:** both the architect's (80 to 95) and the executing session's (80 to 92) were exceeded by 99.63%; path dependence was a third of what both predicted (`M5m-759`).
- **`unexplained` meant a model error:** it meant a feed hole the frozen tool's refusal vocabulary cannot read (`M5m-762`, `M5m-764`).
- **The projection that test B is likely to fail (`M5m-617`) held,** and for the cause it named: four latch episodes in 22 days, the third lasting 42.9 hours.

### What did NOT happen

- **No candidate passed anything.** S5's baseline loses gross and net in every arm; the six S6 candidates lose in sample; S7 was recorded as FAIL by ruling, not measured.
- **The reserved window `[2024-01-01, 2026-10-01)` was not read** for any candidate, except the two variants R-CM names and S5's baseline configuration.
- **Live trading is not unblocked.** Every commission in every capture is still `0.00000000`, entry-fee deduction and base-quantity netting are unbuilt, and `refuse_live_trading` is unchanged. A venue `trailingDelta` is chartered for M5n (D1) and not built on `main`.
- **The tag is not pushed, nor the branch, by the rotation;** and the rehearsal clone and the S4 backtest clone are not retired (the owner's).
- **`check_testnet` after the stop was not run by an executing session:** it is the owner's and is recorded as given.

### What the rotation's steps found

- **Step 4, the contracts.** `docs/QC_PROTECTIVE_ORDERS.md` section 4b said a partly executed leg was UNMEASURED; `docs/QB_ESCALATION.md` Class E had never been observed. Both annotated; `docs/M5_NUMBERS.md` held no sentence M5m falsified.
- **Rule 3, the structural lists.** `data/watchdog.py` (M5l's) was named in neither architecture tree. Corrected.
- **The arming registers.** 55 candidates in `docs/NEXT_MILESTONE.md`; of the 54 parsed, 23 name a file M5m changed, and the trace found five consumed by S1 to S3's own work, the E2 condition fired and discharged at P151, two discharged by S4's stop, U6 fired at S2 and struck, and fourteen not fired (`M5m-776`, corrected by `M5m-778`).
- **The sentences made false.** X2b and the four "HALT has never occurred" blocks in `CLAUDE.md` and `README.md`.
- **A count in a finding was wrong,** the executing session's: `M5m-776` said six and thirteen where five and fourteen were meant, and is annotated by `M5m-778` and not amended.

### The method rules, keyed

- **A prediction made before the measurement is a falsifiable statement, and one taken from a prompt is not a fact** (`M5m-715`). Scored as written, by hit and miss, including the ranges the figure beat.
- **A reconstruction is checked by reproducing the numbers the system logged,** to the digit (`M5m-763`): the live buffer rebuilt from the store with the reported holes removed reproduced three logged averages exactly.
- **A fault line is not where the damage starts** (`M5m-719`): the first lost bar closed up to 31 s before the log line.
- **A frozen tool's vocabulary is part of its meaning** (`M5m-764`, K9): `unexplained` read for what the tool cannot see.
- **Two passes by one reader are independent in method and not in reader** (`M5m-756`), and the report says so.
- **A CHECK written as equality about a moving quantity cannot hold** (`M5m-736`, `M5m-769`).
- **Annotate a wrong finding in a later block, never amend it** (`M5m-778`), used on the rotation's own count.
- **A resource fence is the architect's to build and is still missing** (`M5m-783`): R-EC governed one session and lapsed with it.

### The architect's own errors, by class

- **A premise carried untested:** the 31 failed passes (`M5m-715`, `M5m-730`).
- **A label that named two things:** U11 (`M5m-782`); order ids called lists.
- **A draft taken for a ruling:** the M5n charter's first D1 to D4 (`M5m-706`, ARCHITECT-OWNED, recorded in the charter).
- **A count off by one in a finding** (`M5m-776`), the executing session's own, corrected by annotation.

### What carries into M5n

M5n is chartered in `docs/M5N_CHARTER_DRAFT.md` (a draft on `main`; amended through P142 on branch `m5n`, where R-DU branch 1, R-DX, R-DY, R-DZ, R-DT and R-DT-3b are recorded). Carried, each with its status at the close, in the register of `docs/NEXT_MILESTONE.md`: K1 to K9 (K9 new: the frozen tool's blindness to `buy_refused_bars_gap`); P-3i, P-3m, P-3n; N1 to N6; U0 to U5 and U7 to U13 (U6 resolved; U10 at six Testnet cases; U12 a REASONED prerequisite for any 4h or 1d live path; U13 new); A1 to A3, A5, A6; the `M5i` items; W1 to W4 and W6; X1 to X3 all observed; the blocked trailing-stop milestone; and `M5m-510`. **The owner's pending steps:** retire the rehearsal clone (junction first, `cmd /c rmdir`) and, after confirming the archive, the S4 backtest clone. **Live trading stays blocked by exactly the two gates it was, and refused at every entry point.**

### The historical figures in this entry

**Pinned to their commits, not a live count.**
- **At `ddf3593`**, the last numbered commit: `ruff format` 232 files, `mypy` 114 source files, 4527 passed and 1 skipped with Testnet credentials (4524 and 4 derived); 772 findings and 178 commits.
- **At this rotation's gate**: the same 232 / 114 / 4527 passed, 1 skipped, credentialed, since the rotation changed no `.py` file; 787 findings and 184 commits including this one.
- The captures: S4's final, SHA-256 `94201d916846288855d31c37931812c6149c09ed59b140a53af56e3e50b5bae9`; the census of record's, `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`; the S4 run `20261101T183301538998Z-e7ed287be238` (`run.json` `7a3e1b2f6e3f9c51a43cd7d66cc1285dd8e4cb641dc2b7fcf0681dcdabf5279c`).

**M5m's scope, its order, S4's stop rule and every ruling from R-A to R-ED-1, and the ratification of P151, were the project owner's; everything else was ruled by the architect or by the reviewer under delegation.**

## Phase 5 M5n -- a trend and breakout candidate set that does not clear its gates, an estimator pinned before it was read, and a research pause

M5n outcome: FAIL at N7, with no out-of-sample read. Six pre-registered volatility-scaled trend and breakout candidates on 4h and 1d bars (R-DY), with ATR-scaled venue trailing stops (D1), were evaluated once in sample over [2018-03-05, 2024-01-01). None passed all three gates. The nearest, C1 donchian_1d_20, had an annualised net daily Sharpe of 0.7456 and a bootstrap 5th percentile of 0.0945, but a deflated Sharpe ratio of 0.5692 against 0.95, beside a buy-and-hold Sharpe of 0.6436. Both 4h candidates were consumed by costs. The cheap-slippage sensitivity would have selected C5 and decided nothing (R-DY).

The owner's decision on the FAIL, verbatim:

> Owner decision on M5n's N7 FAIL: I choose pure Option 1: Close M5n as FAIL at N7 (no OOS read), pause strategy research, and open the platform/execution reliability hardening milestone (clearing the S4 backlog: U12 REST backfill for feed holes, U10 partially executed protective legs, U13 unbooked trades after venue errors, and the two live-trading blockers: fee capture and base-asset netting). We will not run Option 3 (no exploratory Testnet paper-trading of C1).

The three closing records, verbatim:

> (1) The reserved window [2024-01-01T00:00:00Z, 2026-10-01T00:00:00Z) remains unread by any M5n family, subject to R-EF's limits: prior reads by S5's baseline (all of it, by design) and by the M5m rehearsal and quarter scan (M5m-447), and a public price path. (2) Cumulative multiple-testing trial accounting across milestones (the step 1 ledger: S6's sweep and selection plus M5n's six candidates, with every other source it lists) is carried forward, and any future research deflation must count it. (3) The live-trading block remains armed.

**M5n is complete, in 114 numbered commits and 5 rotation commits (this one included), with 304 findings declared across `M5n-001`-`M5n-304`, every commit carrying a block.** The owner scoped it from the end of M5m: continue into volatility-scaled trend and breakout research on 4h and 1d bars with the live block armed, ATR-scaled trailing stops in place of the fixed brackets, trade floors scaled to the timeframe, fee-share telemetry first in every report, and `M5m-510` discharged before the unread window was touched (`docs/M5N_CHARTER_DRAFT.md`, section 1). It ended in FAIL at N7, and the weight of the milestone is the procedure rather than the verdict: every threshold, cost and estimator was fixed in a file digested before the one run that could have contradicted it, every candidate parameter was recorded first (R-DY, LOG Entry 7), and the run was made once.

### The commits

Numbered commits are `milestone/M5m..041c604` in order, and include the merge of branch `m5n` (`12d9a33`, row 95). The 22 commits between `ee8d485` (the charter's first commit) and the `milestone/M5m` tag belong to M5m's table and declare no M5n finding. Rotation commits follow the table.

| # | Commit | Subject |
|---|---|---|
| 1 | `2e68278` | docs: the M5n charter records the N2 venue read, the cap, the fee, the order change and R-DU's missing text (M5n, P140 C1) |
| 2 | `335041c` | docs(ledger): section 74, P140's halts and the predictions for the 4h and 1d bar aggregation and its venue verification, before any code (M5n N2a, P140 C2, R-T, R-DQ) |
| 3 | `8bf38f7` | feat(data): aggregate the 1m store into 4h and 1d bars, tagged complete or incomplete (M5n N2a, P140 C3) |
| 4 | `015ee29` | test(data): pin the 4h and 1d aggregation on synthetic fixtures and a real month-file store (M5n N2a, P140 C4) |
| 5 | `1b8fccf` | feat(scripts): n2_verify_bars compares the aggregated 4h and 1d bars with the venue's klines over a fixed in-sample window (M5n N2a, P140 C5) |
| 6 | `9061a1c` | test(scripts): pin n2_verify_bars on a fake venue and a real month-file store (M5n N2a, P140 C6) |
| 7 | `b817882` | docs(ledger): section 75, the N2a run, the scoring of section 74 and what the mismatches are (M5n N2a, P140 C7, R-T) |
| 8 | `62ebd00` | docs(ledger): section 76, the predicted kills for the mutation survey of the N2a tests, before it is run (M5n N2a, P140 C8, R-T, R-DQ) |
| 9 | `a4690d5` | docs(ledger): section 77, the mutation survey of the N2a tests scored against section 76 (M5n N2a, P140 C9, R-T) |
| 10 | `2882fae` | docs(counts): the gate figures and the file lists after the N2a module, script and tests (M5n N2a, P140 C10) |
| 11 | `e14ce80` | docs: the M5n charter records R-DU, R-DV, R-DT-3a, R-DW and the confirmed fee verbatim (M5n, P141 C1) |
| 12 | `cf46f8c` | docs(ledger): section 78, P141's halts and the predictions for the archive 4h and 1d series, the traded-minute mode and the volume gap, before any code (M5n N2b, P141 C2, R-T, R-DQ) |
| 13 | `f8f180b` | refactor(data): share the 1m stream checks of the aggregator so a second aggregation can use them (M5n N2b, P141 C3) |
| 14 | `4ff9a73` | feat(data): a traded-minute aggregation beside the plain one, for R-DV's consistency check (M5n N2b, P141 C4) |
| 15 | `8016ffb` | test(data): pin the traded-minute aggregation on synthetic fixtures and a real month-file store (M5n N2b, P141 C5) |
| 16 | `d01d88e` | feat(scripts): n2_archive_check compares the archive series with the saved API responses, checks the traded-minute aggregation and bands the volume gap (M5n N2b, P141 C6) |
| 17 | `f43acc0` | test(scripts): pin n2_archive_check on saved responses and real month-file stores (M5n N2b, P141 C7) |
| 18 | `5b72656` | docs(ledger): section 79, the archive check run, the scoring of section 78 and what the decision bars are (M5n N2b, P141 C8, R-T) |
| 19 | `6666f4f` | docs(ledger): section 80, the predicted kills for the mutation survey of the traded-minute and archive-check tests and for the re-run of the aggregation survey, before they are run (M5n N2b, P141 C9, R-T, R-DQ) |
| 20 | `c942071` | docs(ledger): section 81, the three mutation surveys scored against section 80 (M5n N2b, P141 C10, R-T) |
| 21 | `f840e98` | docs(counts): the gate figures and the scripts list after the traded-minute code, the archive check and their tests (M5n N2b, P141 C11) |
| 22 | `e942e4f` | docs: the M5n charter records R-DX, R-DZ, R-DY and R-DT-3b verbatim (M5n, P142 C1) |
| 23 | `718aeec` | docs(ledger): section 82, P142's halts and the predictions for the indicators, the six candidates and their entry-event counts, before any code (M5n N3, P142 C2, R-T, R-DQ) |
| 24 | `c0b3928` | feat(indicators): donchian_high, keltner_upper and momentum for the M5n candidates (M5n N3, P142 C3) |
| 25 | `b109f33` | test(indicators): pin donchian_high, keltner_upper and momentum on hand-worked values (M5n N3, P142 C4) |
| 26 | `ea86adc` | feat(strategies): the six M5n candidates and the R-DZ gap-free windows (M5n N3, P142 C5) |
| 27 | `0998ce2` | test(strategies): pin the R-DZ gap-free windows (M5n N3, P142 C6) |
| 28 | `cd85621` | test(strategies): pin the six M5n candidates on hand-worked frames (M5n N3, P142 C7) |
| 29 | `0c7d36b` | feat(config): config.m5n.yaml, the research configuration that enables nothing live (M5n N3, P142 C8) |
| 30 | `81b9c14` | test(config): pin config.m5n.yaml as research only (M5n N3, P142 C9) |
| 31 | `daf8320` | feat(scripts): n3_entry_counts.py counts the six candidates' entry events and R-DZ suppressions (M5n N3, P142 C10) |
| 32 | `67560d2` | test(scripts): pin n3_entry_counts.py on hand-worked stores (M5n N3, P142 C11) |
| 33 | `e486efc` | docs(ledger): section 83, the N3 entry-event counts scored against section 82 (M5n N3, P142 C12) |
| 34 | `6e416a2` | docs(ledger): section 84, the predictions for the mutation survey of the N3 tests (M5n N3, P142 C13) |
| 35 | `f911ef0` | test(scripts): the trimming oracle builds its strategies itself (M5n N3, P142 C14) |
| 36 | `184c219` | docs(ledger): section 85, the mutation survey of the N3 tests scored against section 84 (M5n N3, P142 C15) |
| 37 | `70980c6` | docs: the gate figures and the architecture lists after N3 (M5n N3, P142 C16) |
| 38 | `bf602b1` | docs: the M5n charter records C3, R-EA and R-DT-3c verbatim (M5n, P143 C1) |
| 39 | `febf0b4` | docs: the charter cites the Binance documentation D1 required, before the trail is modelled (M5n, P143 C2) |
| 40 | `8af15c1` | docs(ledger): section 86, P143's halts and the predictions for the D1 trail as a pure function, before any code (M5n N4a, P143 C3) |
| 41 | `8356084` | feat(backtesting): d1_trail.py, the D1 trailing stop as a pure function (M5n N4a, P143 C4) |
| 42 | `eeff30b` | test(backtesting): pin the D1 trail on hand-worked bars (M5n N4a, P143 C5) |
| 43 | `5d4512a` | docs(ledger): section 87, the predictions for the mutation survey of the D1 trail tests (M5n N4a, P143 C6) |
| 44 | `15185e1` | docs(ledger): section 88, the mutation survey of the D1 trail tests scored against section 87 (M5n N4a, P143 C7) |
| 45 | `275ffaf` | docs: the gate figures and the architecture list after N4a (M5n N4a, P143 C8) |
| 46 | `944a705` | docs(charter): R-EB, R-DT-3d and the N4b decisions, verbatim, with the six R-EA readings marked (M5n N4b, P144 C1) |
| 47 | `b957011` | docs(ledger): section 89, P144's halts, the step 2 answers and the predictions for the counts-only run (M5n N4b, P144 C2) |
| 48 | `cc02c06` | fix(backtesting): the entry minute's high counts toward the trail's peak, and the equality pin (M5n N4b, P144 C3) |
| 49 | `92e63e3` | feat(scripts): the worktree mutation survey as a tested script, with the real exception class (M5n N4b, P144 C4) |
| 50 | `fec51e4` | feat(strategies): a candidate fixes its D1 trail at the signal and declares its exit (M5n N4b, P144 C5) |
| 51 | `65bae2f` | feat(backtesting): d1_executor.py, the executor for a strategy whose exit is the D1 trail (M5n N4b, P144 C6) |
| 52 | `29e5353` | feat(backtesting): the engine chooses the D1 executor for a strategy that declares the exit, and every other strategy keeps the old one (M5n N4b, P144 C7) |
| 53 | `fbef8be` | feat(scripts): n4_trade_counts.py, the counts-only run of the six candidates, with its forbidden-figure scan (M5n N4b, P144 C8) |
| 54 | `5492d27` | test(scripts): pin the quantile rank and the root logger's handlers in the counts script (M5n N4b, P144 C9) |
| 55 | `009b354` | docs(ledger): section 90, the counts-only run of the six candidates and section 89 scored (M5n N4b, P144 C10) |
| 56 | `836c21d` | docs(ledger): section 91, the predictions for the arming audit of the N4b code (M5n N4b, P144 C11) |
| 57 | `a7fcb0c` | docs(ledger): section 92, the arming-audit survey of the N4b code scored against section 91 (M5n N4b, P144 C12) |
| 58 | `a19c723` | docs: the gate figures and the architecture list after N4b (M5n N4b, P144 C13) |
| 59 | `b6759a1` | docs(charter): R-DT-3e, the tick reading, the N5 decisions and the clamp note, verbatim (M5n N5, P145 C1) |
| 60 | `dd61369` | docs(ledger): section 93, how the RiskManager sizes and the predictions for the N5 count run (M5n N5, P145 C2) |
| 61 | `8473a24` | feat(backtesting): size a D1 entry from the signal's own clamped trail through the unchanged RiskManager (M5n N5, P145 C3) |
| 62 | `a9a18ad` | feat(backtesting): tally each refusal under the rule that fired (M5n N5, P145 C4, R-DT-3e) |
| 63 | `0a17f02` | feat(scripts): print refusals by rule and the four entry outcomes beside them (M5n N5, P145 C5, R-DT-3e) |
| 64 | `1eb0858` | feat(config): config.m5n.yaml sizes 1 percent risked at the initial stop (M5n N5, P145 C6) |
| 65 | `9431958` | docs(ledger): section 94, the N5 counts-only run scored against section 93, and M5n-091 resolved (M5n N5, P145 C7) |
| 66 | `1ffed99` | docs(ledger): section 95, the predictions for the arming audit of the N5 code (M5n N5, P145 C8) |
| 67 | `0cc80e8` | docs(ledger): section 96, the arming-audit survey of the N5 code scored against section 95 (M5n N5, P145 C9) |
| 68 | `4454ea4` | docs: the gate figures and the architecture list after N5 (M5n N5, P145 C10) |
| 69 | `06fa1f8` | docs(charter): R-DT-3f, D1RiskManager, the halt note and the clamp correction, verbatim (M5n P146 C1) |
| 70 | `e58c675` | docs(ledger): section 97, what a RiskManager keeps after construction and the predictions for the cap-binding count (M5n P146 C2) |
| 71 | `819852d` | feat(backtesting): tally the entries whose size the position cap limited (M5n P146 C3, R-DT-3f) |
| 72 | `d0b47f1` | feat(scripts): print the capped-entry count and close the outcomes-line hole (M5n P146 C4, R-DT-3f) |
| 73 | `d031654` | docs(ledger): section 98, the counts-only run with the capped-entry count, scored against section 97 (M5n P146 C5) |
| 74 | `24bf718` | docs(ledger): section 99, the predictions for the re-survey of the outcomes line and the capped-entry count (M5n P146 C6) |
| 75 | `520de35` | docs(ledger): section 100, the re-survey of the outcomes line and the capped-entry count, scored against section 99 (M5n P146 C7) |
| 76 | `cd37d4b` | docs: the gate figures after P146 (M5n P146 C8) |
| 77 | `ede21a3` | docs: the M5n pre-registration, frozen by digest before any metric is read (M5n P147 C1) |
| 78 | `48c4199` | docs(charter): the pre-registration pointer, its SHA-256, and N7 marked superseded (M5n P147 C2) |
| 79 | `73a7abe` | docs(charter): the readings of the pre-registration, the rulings on M5n-178 and the M5n-173 note, verbatim (M5n P148 C1) |
| 80 | `a65dc95` | docs(ledger): section 101, what metrics.py does, the N6 module's design and its fixtures' hand-worked values (M5n P148 C2) |
| 81 | `58ad896` | feat(backtesting): the N6 estimators, pure, on synthetic fixtures only (M5n P148 C3) |
| 82 | `abb8827` | docs(ledger): section 102, the predictions for the survey of the N6 estimator module, before it is run (M5n P148 C4) |
| 83 | `e2de51f` | docs(ledger): section 103, the scored result of the N6 estimator module's survey (M5n P148 C5) |
| 84 | `b7d6407` | docs: the gate figures after P148, and sharpe_stats in the architecture tree (M5n P148 C6) |
| 85 | `918ca98` | docs(charter): the survey practice, the fee telemetry and the N0 guard, verbatim, with four readings (M5n P149 C1) |
| 86 | `2388ae2` | docs(ledger): section 104, the predictions for the estimator changes, the N0 guard and the N7 runner, before any code (M5n P149 C2) |
| 87 | `05678b6` | fix(backtesting): one accepted form of mark, the bootstrap's stream pinned, its dead line gone and its no-variance guard exact (M5n P149 C3) |
| 88 | `57588ee` | feat(scripts): the N7 runner, with the N0 guard first (M5n P149 C4) |
| 89 | `b5deb42` | test(scripts): the N7 runner's guard, judge worlds and end-to-end fixture world (M5n P149 C5) |
| 90 | `d8ed75b` | docs(charter): the three frozen digests of the N7 guard's condition (c) (M5n P149 C6) |
| 91 | `5cb0d55` | docs(ledger): section 105, the predictions for the survey of the estimator module and the N7 runner, before it is run (M5n P149 C7) |
| 92 | `7711771` | test(scripts): the guard tests start no git daemon, and test the frozen paths they list themselves (M5n P149 C8) |
| 93 | `ea3eac9` | docs(ledger): section 106, the scored result of the survey of the estimator module and the N7 runner (M5n P149 C9) |
| 94 | `2c32af0` | docs: the gate figures after P149, and n7_evaluate in the scripts tree (M5n P149 C10) |
| 95 | `12d9a33` | Merge branch 'm5n' into main: the M5n branch (ee8d485..2c32af0) with its ledger sections split out (R-EE, P154) |
| 96 | `4c7afe2` | docs(charter): the M5n charter's DRAFT marker is lifted, R-DU is applied, R-EE and U12 are recorded (P154) |
| 97 | `bfbe166` | docs(research): PROTOCOL amendment 4 -- section 6 step 6 says what the code does, and M5n's one read is bound per candidate (P155, M5m-510) |
| 98 | `e33ff54` | docs(ledger): section 83, the reserved window's reads from the halted P155 run and the audit of what M5n read (P155 C2) |
| 99 | `5dfc1ab` | docs(research): log Entry 7 -- M5n's six candidates are registered, and the S6 register_strategy condition is met by this record (P155) |
| 100 | `4c41c58` | docs(charter): amendment 4 and N1 done, R-EF recorded, and section 8's freeze entry resolved to the N8 runner's ledger (P155) |
| 101 | `f3548d0` | docs(next): M5m-510 is discharged by amendment 4, and the S6 register_strategy condition is recorded as fired and met in part (P155) |
| 102 | `8c5d9ec` | docs(readme): the architecture tree names sharpe_stats and n7_evaluate, and the docs map records the M5n ledger file and step 2's outcome (P155) |
| 103 | `28e8a77` | docs(charter): R-EG, the re-freeze rule, the survey-resources rule and the N1 ruling, recorded verbatim (P156) |
| 104 | `2df308c` | docs(ledger): M5n section 107 -- the eleven runner holes classified, and the plan that closes the VERDICT ones, before any code (P156) |
| 105 | `c49c6b7` | test(scripts): d1_world can store a 1d series beside a 4h one, for the 4h world the midnight-marking test needs (P156) |
| 106 | `50a114d` | test(scripts): close the eight VERDICT holes of the N7 runner's tests -- digest line, tag, exit codes, books, incomplete run, 4h marking, start day (P156) |
| 107 | `5854581` | docs: the documented pytest figure moves to 5519 credentialed and 5516 uncredentialed, after 25 tests were added (P156) |
| 108 | `40f1c6c` | docs(ledger): M5n section 108 -- the binding predictions for the survey of the VERDICT mutations, before it is run (P156) |
| 109 | `e0d1f8d` | docs(ledger): M5n section 109 -- the scored result of the survey of the VERDICT mutations, and the direct digest check (P156) |
| 110 | `29ef8f1` | docs(charter): N0 recorded -- the N0 line names ddf3593, the re-freeze window closes, a run of N7 is defined (P157) |
| 111 | `dbc7c14` | docs(ledger): M5n section 110 -- the predictions for N7's one run, before it is run, and the guard's acceptance on HEAD (P157) |
| 112 | `2b98945` | docs(ledger): M5n section 111 -- the result of N7's one run, rendered from its result file, and the predictions scored (P157) |
| 113 | `6f83ad2` | docs(research): LOG Entry 8 -- the six candidates' in-sample results from N7, and the verdict FAIL (P157) |
| 114 | `041c604` | docs: record the N7 outcome in NEXT_MILESTONE, close M5n-252, carry M5n-274 as a tests-only item (P157) |

**The five rotation commits (P158), the last being this commit:** `cb570dc` (the charter closed), `f40d1e8` (RUN_LEDGER_M5N section 112), `1e3a2d6` (NEXT_MILESTONE rotated to M5o), `390da44` (CLAUDE.md and README) and this commit (the build log), which carries the tag `milestone/M5n`.

### The cumulative trial ledger (closing record 2), by source

This is the owner's "step 1 ledger", read from the committed records and recorded with its commands in `docs/RUN_LEDGER_M5N.md` section 112. Every source ran BTCUSDT and ETHUSDT jointly. "In sample" is `[2017-08-17, 2024-01-01)`, except M5n's, which starts at `2018-03-05`. The counts are DECLARED configurations, not independent trials, and no effective number of trials is estimated.

| # | Source | What was evaluated | Configurations added | Reads of the reserved window | Recorded in |
|---|---|---|---|---|---|
| 1 | S5's baseline | `sma_crossover` 20/50 on BTCUSDT 1m and ETHUSDT 5m at stop slippage 0.05, 0.66 and 1.20 percent (three runs) | **1** | all of it, by design | LOG Entries 1 to 3; RUN_LEDGER section 50 |
| 2 | S6's sweep | all 216 declared variants (54 `sma_crossover`, 162 `rsi`; 1h, 4h, 1d; trend filter off and on) at the 1.20 percent arm | **216** | none | PROTOCOL section 5; LOG Entry 6; RUN_LEDGER sections 54 and 56 |
| 3 | S6's six selected candidates and walk-forward | 6 of 12 cells had an eligible point, all among the 216; four anchored folds 2020 to 2023 inside the same records | 0 | none | LOG Entry 6 |
| 4 | The M5m rehearsal | 2 variants (`sma_crossover` 4h 10/50, filter off and on), both among the 216, in narrowed protocols: 10 invocations, one of them a 28-quarter scan | 0 | yes, for those two: 2024-01-01 to 2025-04-01 (`M5m-447`) | LOG Entry 5; RUN_LEDGER sections 52 and 53 |
| 5 | The M5m smoke backtests | S5's configuration again over 2024-03-01 to 2024-04-01, three runs | 0 | **yes: 2024-03** | RUN_LEDGER sections 32 and 35 |
| 6 | M5n's six at N7 | C1 `donchian_1d_20`, C2 `donchian_1d_55`, C3 `sma_cross_1d_50_200`, C4 `donchian_4h_20`, C5 `keltner_4h_20_2`, C6 `tsmom_1d_90` once at the base costs, plus the three sensitivities as figures | **6** | none | RUN_LEDGER_M5N sections 110 and 111; LOG Entries 7 and 8 |
| 7 | M5n's counts-only runs | the same six, counts only, no price, return or equity | 0 | none | RUN_LEDGER_M5N sections 83, 90, 94 and 98 |
| | **Distinct configurations with an in-sample performance figure** | rows 1, 2 and 6 | **223 = 1 + 216 + 6** | | |

Left out, with reasons: S4's live run and its backtest comparison (after the reserved window, a calibration of the backtester and not a configuration search); the S7 null check (derived from the six S6 candidates' own trades); the one-day smoke of `config.s4.yaml` on 2026-10-08 (S5's configuration, after the window). **N7's deflated Sharpe ratio used N = 6 as the pre-registration fixes, and a future one counts 223** (`M5n-293`). No deflated Sharpe ratio at N = 223 was computed; the direction is REASONED, with its caveat, in RUN_LEDGER_M5N section 112. **Row 5 is a gap in three older lists** (R-EF's prior reads, RUN_LEDGER section 83's table, LOG Entry 6's exceptions), found at this rotation and declared, not edited (`M5n-294`).

### What M5n decided, and why

- **To write code during S4, under a condition (D4, R-DT).** The architect recommended against writing M5n code while S4 ran; the owner overrode it. The condition that makes the override safe is R-DT: code is exercised on synthetic fixtures only, and nothing on recorded data prints or stores a return, P&L, equity or metric until N0 records the S4 result. R-DT-3a to R-DT-3f then allowed counts-only runs (trade counts, clamp counts, refusal counts, capped-entry counts), with a forbidden-figure scan in `scripts/n4_trade_counts.py`. The cost was that the floors had to be set from counts, so the pre-registration says the counts were seen first (R-DW).
- **The decision bars are the venue's archive 4h and 1d series, verified against the venue's own klines (R-DV).** The alternative, aggregating 1m bars into 4h and 1d, was kept as a consistency check rather than as the source: `data/aggregation.py` builds both, tags a bucket complete or incomplete, and the archive check compares them. The mismatches are recorded in RUN_LEDGER_M5N section 75; the 128 `bars_gap_detected` warnings in N7's standard error come from the 4h series, 64 for each pair (section 111).
- **Six candidates, published parameters, no search (R-DY), no volume (R-DX), and a gap rule (R-DZ).** An indicator whose window holds a missing decision bar yields no value, so a hole suppresses entries and is counted instead of being bridged. The denominator of M5n's judgement is therefore 6, and was fixed before any return was computed.
- **The exit is D1: a trailing stop sized k x ATR / price at entry in integer basis points, clamped to [10, 2000], resolved on the 1m path with the peak updated by each minute's high before that minute's low is tested (R-EA).** The venue's `TRAILING_DELTA` bounds were read by the owner on both venues; the documentation was cited before the trail was modelled. A triggered `STOP_LOSS` executes as a MARKET order, so the stop slippage (1.20 percent at the base, 0.66 and 0.10 as figures) is an assumption and not a documented fact. D1 was built **in the backtester only**; no order for a trailing level is placed anywhere, and QC section 3's three-leg set is untouched.
- **The estimators are a daily-return Sharpe, a stationary block bootstrap (Politis-Romano) and a deflated Sharpe ratio (D2, N6).** Walk-forward and the S6-style null check were rejected because no parameter is fitted; the pre-registration supersedes the charter's N7 wording. The module (`backtesting/sharpe_stats.py`), the pre-registration and the runner were frozen by digest, and the survey found eleven open holes in the runner that P156 classified, closing the eight that could change a VERDICT by test before N0.
- **One run, defined.** N0 was recorded as a charter line the runner's guard reads from `HEAD`; after it no frozen file may change (R-EG); a run counts when its result file is written, and a crash before that is not a run. N7 ran once, 1,350 s, and wrote `data/n7/n7_result_P157.json`.
- **PROTOCOL amendment 4 binds M5n's read to one candidate once, by a runner, never through `check_run` or an entry file (N1).** The owner ruled that step 6 is amended and that "unread" means no M5n family was read (R-EF). The architect's first wording, a single-use rule across every path, contradicted the protocol's per-candidate design and was withdrawn, and it is recorded as ARCHITECT-OWNED. The refusal of a second read is code in a runner that was never built.
- **The N7 predictions were committed first and scored afterwards** (RUN_LEDGER_M5N sections 110 and 111). Of the architect's four scored, three held and (4) failed on C5's sign (+0.0817, not negative); of the executing session's ten, five held whole, three held in their headline and failed in a stated detail, one failed on the sensitivities, and one is not scored.

### What the rotation's steps found

- **Step 4, the contracts.** `docs/QC_PROTECTIVE_ORDERS.md`, `docs/QB_ESCALATION.md` and `docs/M5_NUMBERS.md` were searched for `M5n`, `trailingDelta`, `N7`, `strategy research` and `sharpe`; the only hits were the substring "sharp". QC's prose on the trailing milestone (no owner, the three-leg set, `trailing_stop` retained) is unchanged by M5n because D1 never reached a venue. Annotated: nothing (`M5n-304`).
- **Rule 3, the structural lists.** Read against the tree: every directory under `src/trading_bot` and every file under `scripts/` is named in both architecture trees (the `examples/` and `m5n/` directories by name, as before), every dagger stub is still docstring-and-imports only, and `check_gate_counts` agreed at 15 structural sites twice (`M5n-302`).
- **The arming registers.** 60 blocks in `docs/NEXT_MILESTONE.md` after the rotation, 59 parsed and the one unparsed accepted by ruling. M5n's 53 changed files fire three conditions, traced in RUN_LEDGER_M5N section 112: the `M5n-274` condition (not fired), the `backtesting/engine.py` fill-model condition (not fired) and the `PROTOCOL.md` condition (fired at P155 and answered by the owner). The extractor reads a block to the next blank line, which merged two of this rotation's three new conditions until each was given its own block (`M5n-300`).
- **The sentences made false.** The M5m paragraph's "The next milestone is M5n" and "two backtest clones" in `CLAUDE.md` and `README.md`, annotated; three docs-map rows in the README, corrected in place; the charter's ordering note and status line, annotated.
- **The gate,** bare, uncredentialed by environment so that no venue call was possible: 272 files formatted, mypy 135, 5516 passed and 4 skipped, exit 0 (`M5n-296`). Ten stray `git fsmonitor--daemon` processes followed it, because the system `gitconfig` enables `core.fsmonitor`; `M5n-274` is carried with that count.

### The method rules, keyed

- **A list that names a thing's prior uses is a claim about every use, and is audited against the records, not against itself** (`M5n-294`): three lists of the reserved window's prior reads each omitted the same three smoke runs.
- **An instrument that reads a block to a delimiter audits one condition where two share the block** (`M5n-300`), found because the count did not move when two conditions were added.
- **An item named in the owner's text that the charter does not define is recorded as named** (`M5n-292`): N10 has no row, and the tree's other `N10` is a mutation label.

### What carries into M5o

M5o is the platform and execution reliability hardening milestone, chartered from P159. **The owner's five items:** U12 (REST backfill for feed holes), U10 (partially executed protective legs, six Testnet cases), U13 (unbooked trades after venue errors), the fee-capture blocker (every commission in every capture is zero) and the base-asset-netting blocker (every leg and exit is sized from the ordered quantity). **Carried with them,** each in the register of `docs/NEXT_MILESTONE.md` with its current status: `M5n-274` (tests-only), the cumulative trial ledger, `M5n-294`, K1 to K9, P-3i, P-3m, P-3n, N1 to N6, U0 to U5, U7 to U9, U11, A1 to A3, A5, A6, the `M5i` items, W1 to W4 and W6, and the blocked trailing-stop milestone, whose only named consumer the owner's pause removes. **The owner's pending steps:** retire three clones, the S4 deploy clone, the S4 backtest clone and the rehearsal clone, each junction first by `cmd /c rmdir`. **Live trading stays blocked by exactly the two gates it was, and refused at every entry point.**

### The historical figures in this entry

**Pinned to their commits, not a live count.**
- **At `041c604`**, the last numbered commit: 114 numbered commits and 290 findings. `ruff format` 272 files, `mypy` 135 source files, 5516 passed and 4 skipped uncredentialed **measured at P158** (bare gate, exit 0, 347.6 s, output SHA-256 `6a39c5922f22ee73bf6d6cd9f4592c7b35f348993021323a583aea173735bc35`); the credentialed 5519 passed and 1 skipped is the P156 figure, not re-measured because it would call the venue.
- **At this rotation's end**: the same 272 / 135 / 5516 and 4 skipped, since the rotation changed no `.py` file; 304 findings and 119 commits including this one.
- The captures: N7's result file, SHA-256 `c64b98bca78f9c1bd32c4bc80390e0914eab2fb0a34e28655eaf3a42928fb679`, its standard output `8db10f10c3a4da4d4ef4166ef24147d1d1b87bcacabd97ba1235cd9d65154d53` and its standard error `f9d587a3dd05fe5b187fd73392be9b8a066721eda25a05ce1d2e816c0a08f89e`; the frozen digests `docs/M5N_PREREGISTRATION.md` `e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e`, `sharpe_stats.py` `2b55991c0207fc2938e6f03b33e0b9cfec3754d486af7002d5adee4ee88dda82` and `n7_evaluate.py` `1f307de67f5aebd7af39a3d8fb5cd22a78d9fa671cfdf5353b894beacbadcfff`, unchanged across the run.

**M5n's scope, its order, D1 to D4, R-DT to R-EG, amendment 4's ruling, N0, the single run's definition and the decision on its FAIL were the project owner's; everything else was ruled by the architect or by the reviewer under delegation.**
