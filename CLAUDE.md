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

**A `Money` field has TWO guards, and the line above shows one.** The second is
pydantic's own `allow_inf_nan=False` default for `Decimal`, which rejects
`Decimal("NaN")`, `Decimal("Infinity")` and `Decimal("-Infinity")` *after*
`_reject_float` has passed them — measured, all three raise. It is load-bearing
rather than incidental: `Portfolio.record_realised_pnl` already depends on it in
those words, *"the assignment raises on a non-finite result — `Money` rejects
those independently of the float guard"*, which is half of what makes a failed
accrual leave the ledger untouched. A reader who knows only `_reject_float`
would think a non-finite total lands silently.

**"`int` and `str` pass through" is true of a `Money` FIELD and false of `Money`
ARITHMETIC**, and the two are one line apart in practice. At the field both
convert exactly, as stated. In arithmetic `int` still works — `Decimal("2") * 5`
is `Decimal("10")` — but `str` raises, and with a message that points at the
wrong thing: `can't multiply sequence by non-int of type 'decimal.Decimal'`,
because Python read the `str` as a sequence to repeat. Note the neighbouring
hazard that makes this worth stating: `"5.5" * 2` **succeeds**, silently, as
string repetition.

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
  core/          models · enums · interfaces (ports) · portfolio · assessment
                 · exceptions
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

### `__all__` declares importability, not authorship

**A module's `__all__` says what a caller may import from it, not where the type
was defined.** A type stays in a module's `__all__` while that module binds the
name and holds the code producing or consuming it; `__module__` is the authority
on where it lives.

So a type may legitimately appear in **two** `__all__` lists — one because it is
defined there, one because it is that package's public surface — and neither is a
duplicate to be tidied away. `ProtectiveLevels` is the worked example: it is
defined in `core/models.py` and re-exported by `risk/rules.py`, which is still
where the code that computes it lives.

The rule matters because the tempting reading is the opposite one — that `__all__`
tracks definitions — and acting on it deletes a name a caller is importing. Settled
at M5b commit 6 (`e99f3a7`) when `ProtectiveLevels` moved.

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
  `EntryIntent` or `ExitIntent`; `None` with a `reason` is a normal, expected
  answer. (This read `TradeIntent` until M5b commit 9 split the type; the name
  is corrected here rather than the seam changing.)

### A composition root closes what it hands over — injected or not

Adapters below a root close only what they **built**:
`BufferedMarketDataProvider` keys teardown on `owns_client = client is None`,
because an injected object belongs to its caller. A composition root **is** that
caller and has no caller of its own, so it **inverts** that convention and closes
the client unconditionally. Without the inversion an injected client is closed by
nobody — on the success path *and* on the path where the stream fails to build.

**This binds every root, not just `live_system`.** The two not yet written are
`paper/simulator.py` and `backtesting/engine.py`, and their author will read
`owns_client`, conclude that injected means not-ours, and leak a live aiohttp
session on every boot — silently, because a leaked session fails no test. Read
the rule here, not the convention one layer down.

Two mechanics make the inversion safe, and both are load-bearing rather than
incidental. Teardown is **nested, not one `finally`** — one scope per object,
opened immediately after that object is bound, so a boot that fails at step 2
cannot raise `UnboundLocalError` over the real error, and the ordering is
structural instead of remembered. And `close()`/`stop()` must be **idempotent**,
which they already have to be: `AsyncClient.create` calls `close_connection()`
in its own `except` before re-raising.

Stated in `engine/modes.py`'s module docstring, under *"Ownership: this root
closes the client unconditionally"*; this is the authority's copy of it.

### Lifecycle methods are idempotent — `track`, `start`, `stop`

Every lifecycle method may be called more than once; the second call is a no-op,
never an error. The rule is about *the second call*, not about "no side effects":
`start` genuinely does work the first time, and what it may not do is fail,
duplicate that work, or leave the object worse than the first call left it.

It is **consumed** by `live_system`, whose nested teardown reaches
`provider.stop()` on a path where `engine.stop()` has already stopped it —
*"Safe to reach twice, every `stop()` on this path is documented idempotent"*.
The root's correctness therefore rests on a promise made in other files, and
until now in no central one.

**The contract is spelled three ways across nine sites, and that is the reason it
belongs here rather than in a docstring.**

| Spelling | Sites |
|---|---|
| `Idempotent.` | `MarketDataProvider.stop` (the port), `BufferedMarketDataProvider.track` / `.start`, `TradingEngine.start`, `BinanceMarketDataStream.start`, `setup_logging` |
| `Safe to call any time.` | `BufferedMarketDataProvider.stop`, `TradingEngine.stop` |
| `Safe to call more than once and even if start was never called.` | `BinanceMarketDataStream.stop` |

**A grep for `Idempotent` finds six of the nine and misses `TradingEngine.stop`** —
one of the two methods the root's double-teardown actually depends on. Anyone
checking whether the contract holds before relying on it would have concluded it
does not.

Two consequences. **A new lifecycle method inherits the obligation** — a
`reconciler.stop()` that raises on a second call breaks teardown, not itself. And
**a root may not paper over double-teardown with a "did I already stop?" flag**:
that is a second source of truth for a fact the object already owns, and it goes
stale the moment anything else calls `stop()`.

### Handler isolation is THREE layers, not one

The `TradingEngine.on_signal` bullet above names the layer nearest the decision
path. It is the last of three, and every layer isolates for the same reason: a
buggy subscriber must not be able to kill the feed the rest of the bot depends
on.

| Layer | Isolator | Subscribers |
|---|---|---|
| stream | `BinanceMarketDataStream._dispatch` | the provider's per-pair handler |
| provider | `BufferedMarketDataProvider._notify` | the engine's candle hook |
| engine | `TradingEngine._emit` | signal handlers |

**Naming all three matters now, and specifically the middle one.** M5's
reconciliation driver is a candle subscriber, not a signal subscriber — it has to
be, because reconciliation runs over *every* open position on *any* pair's candle
while `on_signal` skips quiet bars. So it attaches to `_notify`, the layer the
authority did not mention, and a driver written on the assumption that the
engine's isolation covered it would be relying on a guarantee from the wrong
seam.

**Isolation contains a failure; it does not report one, at any layer.** The
consecutive-failure counter is fed from `_evaluate` only, so a permanently broken
subscriber at *any* of the three produces a traceback every bar forever and
quarantines nothing — which is why M4a's chained signal handler is written never
to raise, and why the reconciliation driver must be written the same way. Making
that visible rather than merely contained is Q-A's, and Q-A is blocked on soak
data.

---

## Locked decisions — do not re-litigate without an explicit reason

**Ordering inside a multi-write method**
- **The fallible step precedes the irreversible one, in every method that writes
  more than one field.** Everything that can raise runs first, so a failure leaves
  the object exactly as it was; only then are the writes committed. Stated on
  `Portfolio.open_position` and `close_position`, but it binds every multi-write
  method rather than those two: `record_realised_pnl` was the second instance
  (M5b commits 2 and 3) and will not be the last.

  The failure it prevents is a **half-applied** write, which is worse than a
  refused one because nothing reports it. `record_realised_pnl` committed the day
  roll before the accrual that could fail, so a failed accrual destroyed the
  previous day's realised facts and zeroed a new day nothing was booked into.

  Note the interaction with `validate_assignment=True`, because it is what makes
  the ordering observable rather than merely tidy: each assignment re-validates,
  so a method that writes twice is briefly observable between the two writes. That
  is why `Position` may not carry a `model_validator` while
  `advance_trailing_stop` writes twice, and why collapsing those writes is a
  prerequisite rather than a cleanup.

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
- **Nobody mutates anybody else's frame, and the two halves of that are stated in
  different files.** `get_dataframe` returns `frame.copy()`, which is what makes
  its *"callers may mutate the result freely"* true — a strategy may add indicator
  columns in place without corrupting the buffer, and the buffer is the shared
  state the whole single-threaded design rests on. Going the other way, **every
  function in `indicators/` is pure: the caller's input is never mutated**, and
  the output carries the input index unchanged.

  Together they mean an indicator can be fed a strategy's own Series, or another
  indicator's output, or a slice of the frame, without anyone needing to know who
  else holds a reference. Break either half and the failure is a wrong *number* on
  a later bar in a different component — no exception, no test failure, and
  nothing to grep for.

  The cost is the copy, per pair per bar, on a bounded buffer. It is paid
  deliberately and is not to be optimised away in favour of a documented
  "please don't mutate this": the whole point is that the guarantee does not
  depend on every future caller having read the docstring.
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

**Enums, and which way an unclassified member should fall**
- **Each enum takes the defaulting direction whose WRONG ANSWER IS THE CHEAP
  ONE.** M5a set two in opposite directions on purpose, and read side by side they
  look inconsistent unless the generating rule is stated. `OrderStatus.is_open` is
  a **blacklist** of terminal states, so a member nobody has classified defaults to
  *open* and being wrong costs one wasted round trip against the reserved
  reconciliation floor; as a whitelist it defaulted to *closed*, which stops a
  reconciler watching an order still working at the venue.
  `_TRUSTED_PROTECTION` is a **whitelist**, so an unclassified `ProtectionState`
  defaults to *untrusted*; trusting it by default would make committed risk
  **understate** and let an entry through on the strength of protection that does
  not exist. The two failure directions are not comparable, which is why this is a
  decision per field rather than a house preference.
- **`EXPIRED_IN_MATCH`'s classification is UNMEASURED and sits on the open side.**
  Nothing in this tree defines it and neither does `python-binance`. It looks
  terminal, and "it looks terminal" is the whole of the case for it. **Moving it
  requires a measurement, not an argument from its name.**
- **An enum member is not written until something writes it.** `ProtectionState`
  shipped with **two** members — `ABSENT_BY_DESIGN` and `UNKNOWN` — while Q-C names
  five; `PENDING`, `ACTIVE` and `DIVERGED` land with the milestones that first
  assign them. The reason is the *field*, not the enum: `Position.protection` is
  the one field whose wrong value is **silent**, because `ABSENT_BY_DESIGN` is the
  off-switch for the divergence detector on that position. An unwritten member is
  a plausible-looking value within reach of whoever is nearest a construction site
  and needs something to type. Adding a member later is additive and moves no
  fixture; removing one already assigned somewhere is not.

**Risk**
- Rounding **down** to `step_size` for quantities (`ROUND_DOWN`). Rounding up can
  overspend a balance and get the order rejected — or filled.
- **`_enforce` REJECTS an off-tick `stop_price`; it does not round it.** The
  asymmetry with `price` is deliberate. `price` is legitimately *derived* at
  dispatch — an entry limit from a candle close and a slippage multiplier — so
  putting it on the tick is part of constructing it. `stop_price` **arrives**
  tick-rounded from `risk/rules.py` by contract, toward its reference, direction
  chosen per level; an off-tick one means an upstream broke that contract.
  Rounding it would use `ROUND_DOWN`, and on a long's `STOP_LOSS` the trigger sits
  *below* its reference, so rounding down moves it **away** from entry and the
  realised stop distance **grows** — an unbooked breach of `risk_per_trade`
  arriving through the component that exists to catch exactly that. Rounding by
  inferred direction was rejected too: it would make the dispatch adapter read
  *risk semantics* off `OrderType` and side, and what a level means is risk's
  business. Note this **converts** the defect rather than closing it — `_enforce`
  detects that an upstream failed to protect the trigger; it does not protect it.
- **The independent last line of defence must not be WEAKER than the sizing it
  re-checks.** `_enforce` read raw `LOT_SIZE` while sizing used the **effective**
  filters, so a quantity the sizer would have refused could pass the guard meant
  to catch it — the two agreed only by coincidence on symbols where
  `MARKET_LOT_SIZE` does not bind. It also skipped the notional check whenever
  `price is None`, which is every stop-type order, and that is the wrong half to
  skip: the exchange evaluates `stopPrice × quantity`, and a stop below the entry
  carries the *smaller* notional and is the leg rejected first. A plain `MARKET`
  order remains unchecked and is documented as such — there is no client-side
  price to multiply.
- Exchange filters are applied **in sizing**, not deferred to execution:
  `BinanceClient._enforce` signals violations by *raising*, and "too small to
  trade" is routine, not exceptional. `_enforce` stays as an independent last
  line of defence.
- "No trade" is a **frozen value object carrying its reason**, never a bare
  `Decimal(0)`, `None`, or an exception. See `SizingDecision`. Protective results
  follow suit: frozen, `Money`-typed `ProtectiveLevels` / `TrailingStopUpdate` /
  `ExitDecision`.
- `equity` means **total portfolio value in quote currency**, not free balance.
  A caller must *separately* confirm free balance covers the resulting order; that
  clause lives on the `size_position` port docstring and is repeated here because
  it is the half people drop.
- **The daily-loss limit counts committed risk, not only realised loss, and the
  basis is mark-to-stop.** An account 4% down realised, holding a position whose
  resting stop commits another 2%, is not "4% down" for the purposes of a 5% cap.
  A limit that counts only money already gone breaks its own promise
  **structurally** — it permits opening position N+1 while position N's committed
  loss is unbooked — and it does so on a perfect feed, not merely under polling.
  Polling widens that window; this closes it and the pre-existing one together.

  The check compares `realised_today(now) + Σ min(0, (binding_stop − mark) ×
  quantity)` against the threshold. **Mark-to-stop, never entry-to-stop.**
  Entry-to-stop would drag a third basis — position-lifetime, possibly spanning
  days — into a comparison that already has two, and would count the
  entry-to-mark portion once on the left while the mark-based equity already
  counts it as `limit_percent` of itself on the right. That overlap is
  `1 + limit_percent`, not `2×`; the reason to reject entry-to-stop is basis
  coherence, not magnitude. Mark-to-stop leaves both left-hand terms "from today /
  from now" and the entry-to-mark portion counted exactly once, as the scale
  effect the M3 approximation already documents.

  **`realised_pnl` is untouched and still holds realised facts only.** The
  committed term lives in the *check*, not in the ledger — which is what keeps the
  ledger matching an exchange statement.

  **`binding_stop` is selected exactly as `should_exit` selects it** —
  `max(stop_loss, trailing_stop)` for a long, `min` for a short. Reading
  `position.stop_loss` directly would compute a trailed position's committed risk
  off a level that is no longer operative, and it would **overstate**, refusing
  entries for risk that is not there. Two components disagreeing about which stop
  protects a position is the defect M4b existed to remove.

  > **SUPERSEDED at M5b commit 13 — the paragraph above is correct about its
  > mechanism and wrong about this system.** It holds only if the trailing level
  > is operative, and it landed before the design that would have made it so.
  > Nothing places or amends an order for a trailing level: Q-C §3 fixes the list
  > at three legs and none is a trailing leg, Q-C §5 retains the fields "pending
  > the trailing milestone", and `advance_trailing_stop` is `trailing_stop`'s only
  > writer in `src/` and has no caller. A trailed position whose process dies is
  > protected at `stop_loss`, not at the trail.
  >
  > **The rule is now: committed risk prices off what RESTS AT THE VENUE.**
  > `_binding_stop` returns `position.stop_loss`. The resting set is a consequence
  > of Q-C §3's three legs rather than a preference, so venue-side trailing becomes
  > eligible later without re-opening this. Measured: `sl=88, tr=95, mark=100,
  > qty=10` booked `-50` where what rests gives `-120` — a 58% understatement,
  > under a config shaped like the shipped one.
  >
  > **What SURVIVES:** the last sentence. Two components disagreeing about which
  > stop protects a position is still the defect to avoid — and `should_exit` still
  > preferring the trail is not such a disagreement, because the two answer
  > different questions. `should_exit` asks whether to exit **now**;
  > `_binding_stop` asks what happens if the bot **stops running**. Only the second
  > is what committed risk means, and a test pins the asymmetry so it is not
  > "fixed" into consistency.
- **An uncomputable committed risk is a refusal, not a zero — and the
  discriminator is `stop_loss.enabled`.** A position with no computable stop
  contributes `0` to the sum, which tells the limit check that an *unprotected*
  position carries *no forward risk* — the exact inverse of the truth. So
  `committed_risk` returns the sum **and** the count of positions it could not
  price, and a non-zero count refuses entries, in the shape `NO_MARK_PRICE`
  already has: an inability to compute, refusing before the limits are consulted.

  Scoped by `stop_loss.enabled`, because the two states are not the same fact.
  Stops **on** and a position without one is a divergence, and refusing is
  correct — and it cannot clear, so it escalates (`docs/QB_ESCALATION.md`, site 5).
  Stops **off** and the operator has declared they own their exits via
  `SignalAction.CLOSE` — a style Q-C deliberately preserved — so the check degrades
  to realised-only, documented, and honest *because the operator opted out*. Same
  discriminator already locked for the sub-tick case: `stop_loss.enabled`
  distinguishes "stops are off" from "no level fits right now".

  > **This claim was FALSE when written and was restored true at M5b commit 12 —
  > by making its counterexample unreachable, not by amending the prose above.**
  > `RiskConfig(stop_loss.enabled=False, trailing_stop.enabled=True)` loaded, and a
  > position carrying only a trailing stop priced committed risk off it: measured
  > `total=-50, uncomputable=0`, so the check did **not** degrade to realised-only
  > and `COMMITTED_RISK_UNKNOWN` did not fire either, because nothing was
  > uncomputable.
  >
  > Commit 12 added a **fourth** check to `_check_protective_coverage` refusing a
  > trailing stop with no stop-loss, so that configuration can no longer be built
  > and the sentence above is true again. Both-disabled stays reachable — the check
  > keys on the trailing stop *with* no stop-loss, never on the absence of a stop
  > alone. It is reachable only once take-profit is also disabled, since the third
  > check fires first, so an operator meets two refusals in sequence.
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
  equity → `_approve` → ATR → levels → stop gate → size → affordability → intent.
  (Nine steps, and `_approve` is private: the public `approve` was deleted at M5b
  commit 8 when the port widened to carry `evaluate`.)
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
- **An intent is not an `OrderRequest`** — no take-profit field, and
  `stop_price` there means "this order's trigger". Mapping intent → orders is
  execution's job. Under Q-C the target of that mapping is an **order-list
  request** for three of the four branches; `OrderRequest` expresses only the
  neither-enabled single `LIMIT`, for which M5a gave it the `time_in_force` field
  it lacked. The request's own field wins over `order_request_to_params`'
  keyword, which stays as the fallback for requests that state nothing — so a
  working `LIMIT` leg that must be `FOK` says so itself. (This bullet read
  `TradeIntent` until M5b commit 9 deleted that type; the argument is about the
  intent family and is unchanged by the split described immediately below.)
- **`TradeIntent` splits into `EntryIntent` and `ExitIntent`; it does not fork a
  field.** Under Q-C an entry carries `entry_limit` — a derived, marketable limit
  — while a `CLOSE` dispatches `MARKET` and has no limit price at all. One field
  cannot carry both, and a field that means different things by `side` makes
  `_check_invariants` conditional on `side`, which is an invariant somebody
  eventually inverts.

  `EntryIntent`: `symbol`, `side=BUY`, `quantity`, `reference_price` (the candle
  close), `entry_limit`, and `levels` — **required**, because the four-way
  placement branch reads `levels.stop_loss is None` / `levels.take_profit is None`
  to route, and "neither enabled" is still a `ProtectiveLevels` with both absent
  and a `basis` saying why. `ExitIntent`: `symbol`, `side=SELL`, `quantity`,
  `reference_price`.

  Invariants. `EntryIntent`: `quantity > 0`; `entry_limit > 0`;
  `reference_price > 0`; **`entry_limit >= reference_price`**;
  `levels.symbol == symbol`; **`levels.entry_price == entry_limit`**;
  `side is OrderSide.BUY`. `ExitIntent`: `quantity > 0`; `reference_price > 0`;
  `side is OrderSide.SELL`.

  `entry_limit >= reference_price` is new and earns its place: it makes Q-C §4's
  slippage *direction* a property of the type, unfakeable independently of
  whatever constraint `max_entry_slippage` carries in config. It is the one thing
  that could silently invert.

  The cost is a union `RiskAssessment.intent` that every consumer must narrow.
  There is exactly one consumer today, so the cost is paid once, at its cheapest.
  Dropping the intent from the `CLOSE` path was rejected: `RiskAssessment`'s
  validator binds `approved` to `intent is not None`, and `approved` is locked as
  the only authoritative field.
- **The log line follows the split.** On an entry, `entry` is the `entry_limit` —
  the price actually sent — and a sibling `reference` carries the candle close, so
  the applied slippage is visible in one record instead of inferred from two. On
  an exit there is **no `entry` field at all** — absent, not null, per the schema
  rule — and `order_type="MARKET"` says so, because "at what price" is genuinely
  unknown until it fills. A field that would have to lie is omitted. `order_type`
  is present on **both** branches, and that is what makes the absent `entry`
  legible: `MARKET` says *why* there is no price, so a reader is not left
  inferring absence from absence.

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
  JUDGEMENT about payoff shape, not a measurement.** Nothing downstream is unable
  to compute it and the exchange would accept it; this bot accepted it until M5a
  added the refusal to `_check_protective_coverage`, whose message names the
  opinion as ours in those words. Both-disabled stays reachable with a boot
  warning. The refusal keys on take-profit **with** no stop, never on the absence
  of a stop alone — `SignalAction.CLOSE` exists so a strategy can own its exits.
- **Reconciliation is keyed off what was REQUESTED, never off what is absent**,
  and compares only fields that round-trip. `contingencyType` never says
  `"OTOCO"`, so shape comes from leg count or our own IDs.
- **`translate_binance_error` must match message text, not code.** `-2010` and
  `-2011` each carry several meanings, and `-2010 'Duplicate order sent.'` is a
  *success* signal under deterministic client order IDs.
- **`assessment.decision.rule is None` means "the limits passed", NOT
  "approved".** `RiskAssessment` has no `rule` field at all; the rule is reached
  through `decision`, and is doubly optional — `decision` may be `None`, and
  even when present `rule` may be. **Five refusal paths carry a decision with
  `approved=True` and `rule=None`**: an unmanaged holding, the ATR bridge, an
  unplaceable stop, the sizer, and affordability, all of which refuse *after* the
  limits passed. Branching on rule presence reads all five as approvals.
  **`RiskAssessment.approved` is the only authoritative field** — its validator
  binds it to `intent is not None`, so the two cannot drift.
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
- **`Position.protection` is required and non-nullable — no default.** The
  tempting default is `ABSENT_BY_DESIGN`, on the grounds that it keeps one
  `Position` shape for the whole milestone and is immediately reachable under a
  both-disabled config. Reject it: `ABSENT_BY_DESIGN` asserts "no protection is
  expected here", and that assertion is the **off-switch for the divergence
  detector** on that position. A `Position` built by a path that forgot the field
  would be one the reconciler has been instructed to ignore, and the instruction
  came from nobody. A default should be the value most likely to be *noticed* when
  wrong; this is the value least likely to be.

  Same reasoning as `RiskAssessment.stage`, one notch stronger. `stage` is
  *required but nullable* because "no stage" is a real state; `protection` has a
  member for every real state, so it is required and non-nullable — and a new
  construction site cannot forget it, because it will not construct. `Position` is
  constructed nowhere in `src/` today, so the whole bill is fixtures.

  **Do not add a `model_validator` to `Position` in M5** — not even to enforce
  "`ABSENT_BY_DESIGN` implies both levels absent". `Position` carries
  `validate_assignment=True`, so a `mode="after"` validator re-runs on *every*
  assignment and would observe the intermediate state between
  `advance_trailing_stop`'s two writes. The prescribed fix — collapse those writes
  into one method on `Position` — has to land first, and it is not M5's.
- **Requested protective levels are immutable ONCE SET, not immutable after
  entry.** The distinction is load-bearing. Reconciliation is keyed off what was
  *requested*; a position with nothing requested gives it nothing to compare, so
  the reconciler is **structurally silent** on it and no amount of budget or
  cadence resolves the state. Such a position also refuses every entry,
  portfolio-wide, permanently.

  So a position that has *never* had a requested stop is outside the immutability
  rule's premise, and protection may be **re-requested** through the same
  next-generation machinery Q-C §7 specifies for unprotected divergence. A level
  that *has* been set stays immutable. `trailing_stop` is explicitly outside this
  rule in both directions — it is rewritten every bar by design.

  Where detectable at boot it is refused at boot, before any socket, in the family
  of the five existing root refusals. Where it is not, it escalates as a terminal
  `CRITICAL` — see `docs/QB_ESCALATION.md`, site 5.
- **Pre-existing base holdings are counted toward equity and never adopted as
  positions.** Not adopting at all is unsafe — `has_position` would be `False`
  regardless of what the account holds, so a `BUY` passes `ALREADY_IN_POSITION`
  and pyramids onto a manual holding, sized against an equity that excludes it.
  Adopting fully manufactures the stopless-position state at every boot and means
  the bot eventually sells an asset a human bought. So: count them, refuse entries
  on their symbol, never construct a `Position`. `CLOSE` then finds none and
  returns `NOTHING_TO_CLOSE`, so "the bot never sells it" is enforced by the
  existing code path rather than a new guard. Materiality is `min_notional` —
  a holding too small to sell is dust. The snapshot is taken at boot **before any
  `Position` exists**, which is what stops `equity` double-counting bot-owned base.
  See `docs/QC_PROTECTIVE_ORDERS.md` §5b.

**Execution**
- **The signal handler may perform I/O; it may not perform *unbounded* I/O.** The
  old rule was "no I/O", it lived in one docstring in `engine/modes.py`, and it was
  the consequence stated as the prohibition: handlers are awaited sequentially from
  `_on_candle`, itself awaited from the provider's `_notify` on the stream's
  dispatch task, so handler latency is charged directly to the candle pipeline.
  M4a's handler was I/O-free because it had nothing to do. M5's places orders. The
  invariant that survives is **the candle pipeline must never be blocked by latency
  we do not bound ourselves** — a budget, not an abstinence.

  Dispatch stays **inline**. A bounded queue with a single consumer was rejected:
  it makes `Portfolio` writable from a task that is not the one reading it, and the
  first bug that buys is a **duplicate entry** — signal enqueued, not yet placed,
  next bar's `BUY` sees `has_position` false and enqueues a second. That is a money
  bug traded for a data bug (a missed bar, which the buffer already tolerates and
  already logs). Fire-and-forget was rejected outright: unbounded tasks, no
  ordering, no backpressure, exceptions parked in objects nobody awaits.
- **A budget may refuse to BEGIN work. It must never abandon a write in flight.**
  A placement that runs past its share overruns; the overrun is charged to the next
  invocation's dispatch share. Abandoning a submission mid-flight produces a state
  nobody can read.
- **Reconciliation holds a reserved floor; dispatch cannot borrow from it.** The
  budget splits `B_dispatch + B_recon`, and the skip rule points at dispatch:
  **between skipping a placement and skipping a reconciliation, skip the
  placement.** A skipped placement is a missed trade — a refusal, a value, logged,
  with a reason. A skipped reconciliation is a ledger drifting from reality *while
  the bot keeps trading on it*, and its three dangerous readers are equity
  (overstated ⇒ sizes too large **and** the daily-loss threshold too generous),
  realised P&L (the loss unbooked) and cooldown (never started after a stop-out).
  The floor is what stops a `CLOSE`-emitting strategy from starving reconciliation:
  `CLOSE` is ungateable by design, costs three round trips, and would otherwise
  hold the whole budget every bar.
- **The dispatch deadline is its own field, not `exchange.requests_timeout_s`.** On
  the shipped `config.yaml` a three-call `CLOSE` at the general 10-second timeout is
  30s, and two pairs closing on the same minute is 60s — the entire bar, before
  reconciliation has run. **The field bounds the whole dispatch sequence — worst
  case that three-call `CLOSE` — and is the only configured number; the per-call
  share is derived from it, not set.** On the shipped `config.yaml` the coherence
  constraint admits `D <= 10.5s`, whose derived per-call share is ~3.5s. It is that
  *derived* figure that is roughly a third of the general timeout, never the field
  itself — read the two as one and the per-call deadline lands near 1.1s, below
  plausible venue round-trip, which manufactures the ambiguous write the budget
  exists to prevent. The arithmetic that fixes it is enforced at config load: see
  `docs/M5_NUMBERS.md`.
- **A timed-out write is resolved by query, never by retry.**
  `BaseExchangeClient._call` already narrows placement to `idempotent=False`,
  retrying only `RateLimitError` — a 429 is rejected pre-acceptance, and an
  order-list submission is refused as a unit, so nothing partial survives one. A
  **connection** timeout is different: the placement may have landed. Mark it
  unknown and **query the IDs we would have sent**, which Q-C §6 makes derivable at
  generation 0 by pure computation, no persistence, no I/O. This is that scheme's
  first real use and the reason it was designed that way.

  Found ⇒ it placed; reconcile. Not found ⇒ nothing rests; re-place at the **same**
  generation. Query failed ⇒ re-place anyway, because a duplicate lands as
  `-2010 'Duplicate order sent.'`, which Q-C §8 classifies as a **success signal**.
  The re-place is idempotent *by the venue*, not by us.

  **That guarantee is MEASURED for a duplicate client order ID and UNMEASURED for a
  duplicate order *list*.** The recovery path's classifier depends on it. Settled by
  a rejection — resubmit an accepted list's exact parameters and read the error —
  and that measurement is M5c's, not a soak question.
- **Dispatch carries its own retry budget, supplied per call, not per client.**
  `retry_attempts=4` with `wait_exponential(multiplier=0.5, max=8.0)` can spend ~14s
  inside one call, and under an inline handler that is charged to the pipeline. A
  retry policy is a property of what is being asked, not of who is asking, and one
  client should not need a twin to say "this one is a write on the hot path".
- **Fills are observed by polling, and the trigger is deliberately not the
  position's own bar.** Reconciliation runs over **every** open position on **any**
  pair's candle, so staleness is bounded by the *shortest* configured timeframe
  rather than the slowest position's. Passes are deduplicated by
  `last_reconciled_at` — a position is re-read only once its stamp is older than the
  shortest timeframe — so two pairs closing on the same minute pay for one pass, not
  two. Positions are visited **oldest stamp first**, so a pass cut short by the
  budget always advances the stalest one instead of starving a fixed tail.

  A user-data stream is the correct successor and is deliberately deferred: a
  listen-key lifecycle, a second socket with its own reconnect story, and a **worse**
  failure mode than polling — a silently dead stream leaves us believing we are
  current, where polling's staleness is at least bounded by its own cadence. It
  would not remove the reconciler either; boot and divergence still need it.
- **There is no static staleness guarantee — only what `last_reconciled_at`
  reports.** The shortest timeframe is a floor, not a bound: add the query's own
  latency, add every bar the budget skipped, add every bar that never arrived
  because the feed dropped and the buffer does not backfill. So the decision path
  **reads the stamp** rather than trusting the cadence: an open position staler than
  `risk.max_position_staleness_s` refuses new entries under its own `RefusalStage` —
  not because a limit fired, but because the ledger is not current enough for the
  limits to mean anything. That refusal is also what frees the budget the reconciler
  needs, so the system oscillates — trade, go stale, refuse, reconcile, trade —
  rather than wedging.

  The same check runs in the per-candle reconciliation driver, which fires on quiet
  bars where nothing evaluates. There the response is escalation, not refusal: a bot
  that is not trading is not harmed by staleness, but "an unmonitored open position
  and no alarm" is the state an operator most needs told.
- **An exit must always be permitted — that rule governs *limits*, not
  venue-state uncertainty.** A limit that could trap an open position would be a
  risk rule that creates risk, which is why no limit gates a `CLOSE`. It does
  **not** require dispatching a sell whose outcome the bot cannot determine:
  under Q-C §4b a failed confirming query means "do NOT sell", and suppressing
  that symbol's exits is refusing to act on unknown state, not a limit. The two
  read as a contradiction unless the scope is stated, so it is stated here. See
  `docs/QB_ESCALATION.md`, Class E.

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
- **A fence buys layout, not line length.** `# fmt: off` suppresses the
  **formatter**; `E501` is a **lint** rule and is untouched by it. So a fenced
  wire fixture cannot fence itself a long row — a payload line copied verbatim
  from an API response will still fail `ruff check` at 100 characters, and the
  fence will not say so until the gate does. **Hand-lay each row across several
  lines inside the fence** (one dict per row, keys grouped as the wire groups
  them) and **never reach for `# noqa` to keep a wire row on one line**: the
  suppression rule is not relaxed for fixtures, and the reason to fence is that
  the *grouping* mirrors the contract, which survives wrapping perfectly well.

  > **CORRECTED at M5b's rotation: the enforcement half is FALSE.** `E501` is in
  > `pyproject.toml`'s `ignore` list (`"E501", # line length is the formatter's
  > job`), so a long row does **not** fail `ruff check`. Measured: a 146-character
  > line passes, exit 0. Inside a `# fmt: off` fence nothing objects to it at all —
  > the formatter is suppressed and the lint rule is off.
  >
  > **What SURVIVES is everything except that sentence**, and it survives on its
  > original reasoning rather than on enforcement: hand-lay each row anyway,
  > because the *grouping* is what mirrors the contract, and that is the whole
  > reason to fence. Do not reach for `# noqa` — now for the stronger reason that
  > it would suppress nothing. The `# fmt: off`-is-not-a-lint-suppression
  > distinction is still true and still worth knowing; only its worked consequence
  > was wrong.
  >
  > Note what this means for the gate: **line length is enforced by
  > `ruff format --check`, not by `ruff check`.** The formatter rewraps what it
  > can, and a fenced region is exactly where it cannot — so a fence is the one
  > place in this tree where an over-long line survives all four gate steps.
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
ruff format --check src tests scripts  85 files already formatted
mypy                                   Success: no issues found in 59 source files
pytest                                 775 passed, 3 skipped
                                       (778 passed with Testnet credentials present)
```

**The gate's output is not a function of the tree alone — this is a property,
not a footnote.** It varies by **credentials** and by **network state**.

*Credentials.* The three integration tests are `skipif(not HAS_CREDENTIALS)`, so
the *same commit* reports:

- `778 passed` on a machine with Binance Testnet credentials in `.env`
- `775 passed, 3 skipped` on a machine without them

**Both are honestly green.** A fresh clone, a new contributor, or the first CI
runner will see 775 and must not read it as a regression against a documented
778. Quote the count with its condition, never bare.

Only the `778` is measured here; `775` is `778` minus the three `skipif`-gated
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
output was read. The unit suite is deterministic at 775, so **treat a lone
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

**This rule has an inverse, and the two must be applied together.** Grepping the
digits guards against *missing* a site; the inverse guards against *hitting one
that is not a count*. Both live in `docs/NEXT_MILESTONE.md`'s process section, as
a pair, because a rule and its inverse kept in separate documents is how one of
them gets applied alone — which is exactly what nearly happened at M5b's
rotation.

**What each gate covers** — one boundary, stated once, and it is now deliberate
everywhere:

| Gate | Scope | Files |
|---|---|---|
| `ruff check` / `ruff format --check` | `src tests scripts` | 85 |
| `mypy` | `files = ["src/trading_bot", "scripts"]` | 59 |
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

### Three harness traps, and each one hides its own evidence

They belong together because they share a failure mode: the tool reports
*something*, so nothing looks broken, and the missing part is what you needed.

1. **`addopts` already carries `-q`, so `pytest -q` is `-qq` — and `-qq`
   suppresses the summary line entirely.** Not shortens: removes. You get the
   progress dots and no `N passed`. **Witnessed, repeatedly, during M5b:** several
   `pytest ... -q | grep -E "passed|failed"` calls in that session returned
   nothing at all and read as a hung or empty run, when the suite had passed. Run
   the suite bare and let `addopts` supply the one `-q` it already has.
2. **Run `ruff` and `mypy` from the project root**, or their configuration is not
   the project's. Measured: `risk/manager.py` is clean from the root and reports
   **15 `E501` errors** under default configuration, because this project sets
   `line-length = 100` and ignores `E501`. The *mechanism* by which a wrong
   working directory loses the config is not measured here and is not asserted —
   what is measured is that the two configurations disagree loudly on a file that
   is clean under ours.
3. **`tests/unit/test_modes.py` imports its fixtures from
   `tests/unit/test_risk_manager.py`.** An import-time break in the latter fails
   both files, so a traceback naming `test_modes.py` may have nothing to do with
   it. Nothing else in `tests/` couples two modules this way.

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

### Name the test that pins each argument, and flag the ones with none

**For every argument a report or a design note makes, name the test that pins it,
and flag any argument that has none.** The flag is the point rather than the
coverage: an unpinned argument is not a defect, but an unpinned argument nobody
noticed is one waiting to happen — it reads as settled while nothing holds it.

Adopted at M5b commit 9 and used in every report after. It pays twice. It
separates *this is measured* from *this is reasoned*, which is the distinction
this project's contracts are built on. And it surfaces the arguments that are
**unpinnable** rather than merely unpinned — an absence proved by grep, a
property that cannot fire until a milestone that does not exist — which are worth
knowing about precisely because no future test will ever appear to cover them.

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
2. Update this file **and `README.md` in the same commit** — "Current state", any
   new locked decision, and the baseline numbers taken from a **fresh gate run**
   (never a remembered count). The counts live in *four* places across the two
   files, and they are one atomic fact about one gate run: splitting them leaves a
   window in which the repo disagrees with itself, which is the drift the
   "grep for the NUMBER" warning below exists to prevent.
3. Rewrite `docs/NEXT_MILESTONE.md` for the next milestone, carrying forward any
   open items that are still open. This is the single home for live open items.
4. **Re-read the contracts under `docs/` for prose this milestone superseded.**
   `QC_PROTECTIVE_ORDERS.md`, `QB_ESCALATION.md` and `M5_NUMBERS.md` are *decided
   documents*, not logs: a later decision can invalidate a paragraph in one of them
   and nothing will prompt a re-read, because the milestone that superseded it was
   editing different files. **Annotate, never delete** — record what was superseded
   *and what survived*, since the two are rarely the same.

   This is the step the M5-0 rotation missed. Q-C §9 still specified
   `TradeIntent.price` changing meaning after D3 had split the type, and §1 still
   carried an instruction that had already been executed. A reader arriving cold at
   either would have built something nothing adopted.

There is no separate workflow document; these four steps are the procedure, and
they live here because this is the only file loaded into every session. Docs that
must be remembered to be read are how the four drifts found in the M3 audit got
in.

### What rotation compiles FROM — a finding lands at its commit, not at rotation

M5b's closing rule, quoted from `docs/PHASE_HISTORY.md`: **"A finding destined for
`PHASE_HISTORY.md` is written there at the commit that produced it — not carried
to rotation. Rotation *compiles*; it must not be a finding's first contact with
disk."**

That entry nearly proved its own point by losing four of its findings. T, CC, EE
and GG were generated in Phase 1 reports, never folded into a commit message, and
therefore existed **only in chat** — one closed window from being irrecoverable.

**The obligation attaches to the two-phase artefacts, and it is written here
rather than left to a prompt.** Every Phase 1 report ends with a findings block,
each finding carrying an **ID** and a **MEASURED / REASONED / UNMEASURED** mark.
Every Phase 2 authorisation names **which finding lands in which commit message**.
A rule that depends on an assistant remembering it is the `phase_5_` shape
described below: build reasoning living outside the repo, invisible to every gate,
grep and review.

The commit message carries the block as the **last section of the body, before any
trailer**, in one of two shapes:

```
Findings: none
```

```
Findings:
- <ID> -- <one line>. <MEASURED | REASONED | UNMEASURED>.
```

**`Findings: none` is mandatory, never an absent section.** An absent section is
indistinguishable from a forgotten one, which is M5b's failure exactly. This is
the same decision already locked for `RiskAssessment.stage` — *required but
nullable, no default, so every construction site says something and an approval
says `None` deliberately* — one notch weaker, because there a validator enforces
it and here nothing does.

**The probe hole, closed explicitly.** A scratchpad probe changes no file and
produces no commit, so *"the commit that produced it"* has no referent — and the
milestones with the most probe-derived findings are exactly the ones where this
matters. **A probe's findings land in the docs commit that records the
measurement, and the Phase 2 authorisation for that probe names that commit in
advance.** Without this clause, probe findings fall through the same hole M5b's
four fell through, and they do it while looking compliant.

**This is a DISCIPLINE attached to the Phase 1 / Phase 2 artefacts, not an
enforced check. Nothing fails when it is skipped.** `.gitmessage` at the
repository root pre-fills the block and is a **convenience, not enforcement**: it
applies only to commits written through the editor, never to `git commit -m` or
`-F`, and it does nothing until someone runs `git config commit.template
.gitmessage`, which is per-machine config rather than tracked state.

A `commit-msg` hook was **rejected**, and not for being unavailable. It enforces
the block's *shape* and never its *truth* — `Findings: none` on a commit that
produced four is invisible to it. Its installation is local config too
(`core.hooksPath`), `--no-verify` bypasses it, a probe gives it no referent, and a
hook that aborts a commit produces a commit its author believes landed and did
not. That last failure is worse than the one it prevents.

**Rotation reads the blocks with one command.** Its base is the previous
milestone's closing SHA — the last row of that milestone's commit table in
`docs/PHASE_HISTORY.md` — **looked up, never hardcoded here**, because a SHA
written into this file is a count site by another name and would go stale the way
the documented counts do:

```bash
git log "$(sed -n 's/^| [0-9]* | `\([0-9a-f]*\)`.*/\1/p' docs/PHASE_HISTORY.md | tail -1)..HEAD" --format='@@@%h %s%n%b' | awk '/^@@@/{h=substr($0,4);p=0;next} /^Findings:/{print "";print h;p=1} p'
```

It prints nothing when no commit in the range carries a block. That is the state
every range was in before this rule, so an empty result means "not looked" as
readily as "no findings" — read it against `git log --oneline` over the same
range rather than alone.

**The Claude.ai Project knowledge is a fourth drift surface, and nothing audits
it.** It is outside the repo, so no gate, grep or review touches it —
`MILESTONE_WORKFLOW.md` was referenced there for months while existing nowhere in
the tree. **This file is the authority.** Project knowledge should *point at* it,
not restate it; anything restated there will eventually contradict the code, and
the contradiction will be invisible from inside the repo.

**Second instance, and it is worse than the first: `phase_5_`.** It was four
milestones stale — announcing "Next: M4a" and reporting `pytest 569` — and it was
the **first artefact each session read**, so every session began from a wrong
milestone and a wrong count. No gate, grep or review in this project could see
it; it was found only because a rotation went looking for the artefact by name
and discovered it was not in the tree at all. Deleted from project knowledge at
M5b's rotation.

Two instances is the point. `MILESTONE_WORKFLOW.md` was a *dangling pointer* —
harmless if never followed. `phase_5_` was **stale content presented as current**,
which is the failure mode that actually misleads, and the one this surface will
keep producing as long as anything is restated there.

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
site. **Five** conditions refuse the boot before any socket exists — a duplicate
symbol, an unprimeable symbol, a missing quote asset, a mode with no composition
root, and an empty enabled-pair set.

The five are **not homogeneous**, which is what got the count written as four:
four raise `ConfigError` inside `engine/modes.py`, while the unprimeable symbol
**propagates** out of `client.get_symbol_info` and is documented only on
`_prime_pairs`. Counting the `raise ConfigError` sites therefore finds four and
misses the one that is not a refusal this file writes.

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

**M5-0 is complete: the decisions that gate every M5 milestone are made and
written down.** M5 is six milestones, not one. D1 (dispatch stays inline, with a
per-call deadline, a per-bar budget and a reserved reconciliation floor), D2 (fills
observed by polling over every position on any candle; committed risk on a
mark-to-stop basis), D3 (`TradeIntent` splits into `EntryIntent` / `ExitIntent`)
and D4 (the safety numbers) are locked above. **Q-B** is settled in
`docs/QB_ESCALATION.md`: `CRITICAL` means a log line and a halt flag and nothing
else, across five binding sites in three categories.
`docs/M5_NUMBERS.md` holds the six numbers with their provenance and status;
`docs/QC_PROTECTIVE_ORDERS.md` gained §5b, settling that pre-existing holdings are
counted toward equity and never adopted as positions.

**The only `src/` change was to the gate's own invocation.** `scripts/check.py`
now refuses to run from an interpreter that cannot import this checkout's
`trading_bot` — the third time the gate was correct and the way it was invoked was
not.

**`alpha` is measured-but-not-derived**, which is why `M5_NUMBERS.md` carries a
BOUNDED status beside MEASURED and PLACEHOLDER. Worst pipeline overhead is 2.9% of
the shortest bar and no bar was missed across 90 minutes, so jitter is not the
binding term in the coherence constraint. The composed decision path costs ~2 ms
warm and 10²ms on its first execution in a process.

**M5a is complete: the vocabulary exists, and nothing in it performs I/O.**

*Config.* `RiskConfig` gained the five M5 safety fields —
`max_entry_slippage`, `price_band_margin`, `max_position_staleness_s`,
`dispatch_deadline_s`, `reconcile_deadline_s`. **Five of the six numbers in
`M5_NUMBERS.md` are PLACEHOLDER — NOT MEASURED**, and both the docstrings and
`config.yaml` say so in those words, so an operator cannot mistake a rationale
for a sample. Their types are not uniform, and the split is the money rule
applied field by field: the two that will multiply money are `Decimal`, the three
durations compared against clocks stay `float`. `AppConfig` gained the coherence
validator — `P_sim × D + N_max × T_recon <= alpha × T_min`, per candle-handler
invocation — which refuses a dispatch budget that cannot fit the shortest bar.
The shipped defaults pass with margin (`2 × 9.0 + 3 × 3.0 = 27.0` against `30.0`);
a third 1-minute pair takes it to 36.0 and is refused, which makes an added pair
a decision rather than a silent degradation. `_check_protective_coverage` gained
its third check: a take-profit with no stop is now **refused at load**.

*Domain.* `ProtectionState` in `core/enums.py`, with **two** members and a
docstring saying the omission of the other three is a decision. `Position` gained
`entry_bar_time`, `protection` (required, non-nullable), `order_list_id` and
`last_reconciled_at`. `Portfolio` gained `ge=0` on `free_quote`, `open_position` /
`close_position`, the unmanaged-holdings boot snapshot, and the mark-to-stop
committed-risk term. `OrderStatus` gained `PENDING_NEW` and `EXPIRED_IN_MATCH`,
and **`is_open` inverted from a whitelist of open states to a blacklist of
terminal ones**, so a future member defaults to OPEN. `SymbolInfo` models
`PERCENT_PRICE_BY_SIDE`, `MAX_NUM_ALGO_ORDERS` and `MAX_NUM_ORDER_LISTS`.
`Order` gained `order_list_id` and `stop_price`; `OrderRequest` gained
`time_in_force`.

*Exchange.* Three `_enforce` fixes, each its own commit: it now reads the
**effective** lot filters rather than raw `LOT_SIZE`, checks notional against a
stop-type order's **trigger** rather than skipping it, and **rejects** an off-tick
`stop_price` rather than rounding it — rounding would use `ROUND_DOWN`, which on a
long's stop moves the trigger *away* from entry and grows the realised stop
distance. `FilterRejectedError` exists, with one local raiser and no translator
until error parsing lands.

*The warm-up was dropped, not deferred.* `07d9309` corrected the figure that
motivated it from 14% to 4.6% of the constraint ceiling — the 14% read the
constraint table's per-call column as `D` — and it did not survive re-adjudication
on the corrected number. If it returns it belongs to the milestone that pays the
cost on a real order, not to boot-time code whose only purpose is timing.

**Still nothing places an order.** `IntentLogger` remains the terminal
collaborator; `execution/` is still a pair of stubs.

**M5b is complete, in commits 0 through 13, and it added no I/O.** Both of its
prerequisites — the **mutation-on-read** in the portfolio's lazy day-roll, and
the requirement that the widened port not leave a path able to approve an entry
whose committed risk is unknown — were met before the port moved. `TradeIntent`
split into `EntryIntent` / `ExitIntent`, the assessment family moved to
`core/assessment.py`, the `RiskManager` port widened to carry `evaluate` and the
public `approve` was deleted, `entry_limit` became a derived marketable limit
under `ROUND_CEILING`, and `derive_entry_limit` joined the package surface.

Two tail commits closed defects found while measuring those: a trailing stop with
no stop-loss is now refused at config load, and **committed risk prices off what
rests at the venue** rather than off a trailing level that rests nowhere.

The gate as M5b left it, at `4926705`: `ruff check` clean, 85 files formatted,
mypy clean over 59 source files, 778 passed credentialed. **Those four figures
are pinned to that commit and are not a live count** — like the D3 and M4a
illustrations in the count-coupling section, they record a past run and are not
to be updated by a later gate.

**Q-A** stays unscheduled: its thresholds need soak data and nothing has
dispatched an order yet, so the `collaborator_failed` lines it would be
calibrated from do not exist. See `docs/NEXT_MILESTONE.md`.
