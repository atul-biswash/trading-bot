# Current milestone — M5b: the intent split and the widened port

**M5 is six milestones, not one.** M5-0 (decisions) and M5a (the vocabulary) are
complete. M5b is the second that changes `src/`, and — like M5a — it adds no I/O.
Nothing in it can place an order.

Read first: `docs/QC_PROTECTIVE_ORDERS.md` §4 and §9 (the entry reference and the
port), `docs/M5_NUMBERS.md` §1 (`max_entry_slippage`), `docs/QB_ESCALATION.md`.
The decisions themselves are locked in `CLAUDE.md`; this file is the task list and
the single home for live open items.

---

## Prerequisites — TWO, and NEITHER IS MET

M5a's equivalent section read *"Prerequisite, already met"*. This one does not.
Both live here rather than among the open items below, and the placement is
deliberate: **M5b moves the very port that carries them.** Filed as open items
they read as advisory, and the whole point is that they are not.

### P1 — `Portfolio` mutates on read, and two docstrings say it does not

**Confirmed by execution**, not inferred:

```
before:  realised_pnl=-500  pnl_date=2026-08-07
  -> daily_loss_exceeded(limit_percent=5, equity=10000,
                         now=2026-08-08T00:01Z, marks={})  -> False
after :  realised_pnl=0     pnl_date=2026-08-08
```

`daily_loss_exceeded` → `realised_today` → `_roll_day`, which **assigns**
`realised_pnl` and `pnl_date` when the UTC day turns. A documented read performs
a write.

**Two statements of the false clause, and both travel into `core/` when the port
moves:**

| File | Text |
|---|---|
| `core/interfaces.py` (`RiskManager.approve`) | *"It is read, never mutated: recording an entry or an exit belongs to whoever actually places the order."* |
| `core/portfolio.py` (`Portfolio`) | *"The risk manager only ever reads it; the mutators below are called by execution when an order actually fills."* |

**What is NOT wrong, stated so the fix does not overshoot.** `_roll_day` honours
the no-clock rule — the turn is driven by the caller's `now`, never by a wall
clock — and lazy rolling is itself correct: a bot that trades nothing overnight
would otherwise carry yesterday's halt into a new day with nothing to poke it.
Every individual site looks right. What is wrong is that **a lazy accrual mutates
on read**, it fires **once per UTC day** on the **first evaluation after
midnight**, and that evaluation is on the path deciding whether the bot may open a
position. A suite whose fixtures all sit inside one day never sees it.

**Why it must be settled BEFORE the mechanical move, not after.** The likely
resolution is behavioural — an explicit `roll_day(now)` called once per candle,
with the read paths made genuinely read-only — and that touches the callers of
`realised_today` / `daily_loss_exceeded`, which sit among exactly the construction
sites the move relocates. Settling it first is one edit; settling it after is the
same edit applied across a moved file plus a second review of the move itself.

So it is **commit 0**, and it may change behaviour.

### P2 — the widened port must not admit an entry whose committed risk is unknown

`evaluate` refuses under `COMMITTED_RISK_UNKNOWN` when
`portfolio.committed_risk(marks)` reports positions it could not price and
`stop_loss.enabled` is true. **The port's `approve` does not.** It computes
`marks`, delegates to `_approve`, and `_approve` consults `daily_loss_exceeded`
and never `committed_risk` — so a caller reaching `approve` can be told
`approved=True` for an entry whose committed risk is unknown. That is the exact
inversion the refusal exists to prevent: an unprotected position reported as
carrying no forward risk.

It is latent today because `approve` has **zero production callers** — which is
also why M5a declined to give `COMMITTED_RISK_UNKNOWN` a `RiskRule` twin, on the
grounds that the widened port replaces `approve` this milestone. **That reasoning
is only sound if M5b actually closes the gap.**

**Binding requirement, not a task: when the port widens, no method on it may
approve an entry whose committed risk is unknown.** Three ways to satisfy it, and
choosing between them is M5b's:

1. `approve` gains the check (and `COMMITTED_RISK_UNKNOWN` gains its `RiskRule`
   twin after all, eroding the stated property that `NO_MARK_PRICE` is the single
   place the two vocabularies coincide);
2. `approve` leaves the port entirely, so `evaluate` is the only entry point;
3. `approve` becomes private to `RiskManager`, off the port but still callable
   internally.

Option 2 is the cheapest to reason about and the most disruptive to the port's
shape. **Do not default to it silently** — whichever is chosen, record why.

---

## What M5b delivers

Commit 0 is the prerequisite above. The rest, in order:

| # | Commit | Kind |
|---|---|---|
| 0 | **Settle P1** — `roll_day` made explicit; read paths made read-only; both docstrings corrected | **semantic, may change behaviour** |
| 1 | Move `RiskAssessment`, the `TradeIntent` family and `PairContext` to `core/` | **mechanical — byte-identical, its own commit** |
| 2 | Widen the `RiskManager` port: `evaluate` joins it; **resolve P2**; correct the false purity clause (see below) | semantic |
| 3 | `TradeIntent` → `EntryIntent` + `ExitIntent`, with the invariants locked in `CLAUDE.md` | semantic |
| 4 | `entry_limit` derived from `reference_price` and `max_entry_slippage` | semantic |
| 5 | `IntentLogger` narrows the union; the log line follows the split | semantic |
| 6 | Collapse `NO_MARK_PRICE`'s two divergent reason strings *(M5a carryover)* | semantic |
| 7 | `engine/modes.py`'s handler docstring: "No I/O" → the bounded-I/O rule *(M5a carryover)* | correction, `src/` |

**Commit 1 is mechanical and must not carry anything else.** The move is the one
change in this milestone a reviewer can verify by checksum rather than by reading.

**`entry_limit >= reference_price` is the invariant that earns its place.** It
makes Q-C §4's slippage *direction* a property of the type, unfakeable
independently of whatever bound `max_entry_slippage` carries in config. It is the
one thing here that could silently invert.

**The log line follows the split.** On an entry, `entry` is the `entry_limit` —
the price actually sent — and a sibling `reference` carries the candle close, so
applied slippage is visible in one record. On an exit there is **no `entry` field
at all** (absent, not null, per the schema rule) and `order_type="MARKET"` says
why: the price is genuinely unknown until it fills.

### Folded into commit 2 — the port's second false clause

Distinct from P1 and settled by wording alone, so it is a task rather than a
prerequisite. `RiskManager.approve`'s port docstring claims it *"stays a pure
function of its arguments and the clock."* It is not: the concrete `approve` calls
`_mark_prices(portfolio)`, which reads `self._provider.last_candle(...)` — a
collaborator injected at construction, not an argument, and one whose value
changes bar to bar. Correct it where the port is being edited anyway; do not open
a separate commit for a sentence.

---

## Closed by M5a's rotation — recorded so they are not re-raised

- **`OrderStatus.is_open`'s direction.** Decided: a blacklist of terminal states.
  The window closed as predicted when `PENDING_NEW` landed.
- **The four items absorbed into M5a's scope** — `free_quote` `ge=0`,
  `_exit_assessment`'s missing test, and `_enforce`'s `min_notional` /
  effective-filter blindness. **Two others were absorbed and did NOT land; they
  are carried below rather than allowed to vanish**, which is the hazard an
  absorbed item creates.
- **The `PHASE_HISTORY` debt from `7c1af17`** — discharged in the M5a entry.
- **S3's salvage, both halves.** The `src/` docstring pass produced four
  promotions, all landed. Two were *undercounted by the plan and corrected by
  reading the code*: idempotence is nine sites in three spellings, not six, and
  handler isolation is three layers, not two.
- **The line-ending note.** Re-measured 2026-08-09 with the instrument validated
  against a known non-zero answer and a negative control: **105 tracked files,
  zero CR bytes.** The note is updated with today's measurement and the
  overstating index line is corrected. The cause of the change from the
  2026-08-02 mixed state is **undetermined and was not reconstructed**.

---

## Open items — carried forward, none scheduled

**Q-A — the per-collaborator failure counter. Still unschedulable, and that is
the finding.** Its thresholds need soak data that cannot exist until something
dispatches an order, so it is blocked behind M5. Two things about it are already
settled: **automatic removal of a failing handler stays REJECTED** — disabling a
broken executor converts "orders are failing" into "orders are not being
attempted" while positions are open — and the shape M4a left is unchanged.
`TradingEngine._emit` catches per handler and logs, but the engine's
consecutive-failure counter is fed only from `_evaluate`, so a permanently broken
handler produces a traceback every bar forever and no pair is ever quarantined.
M4a's chained handler mitigates this by never raising; the counter would make it
visible rather than merely contained. **M5a widened its scope without changing
it:** the same gap exists at all *three* isolation layers, not just the engine's.

### Carried from M5a's scope, absorbed but not landed

- **`NO_MARK_PRICE` still has two divergent reason strings.** `approve` says
  *"cannot value open position(s) X; equity is unknown, so no limit can be
  checked"*; `evaluate` says *"cannot value open position(s) X"*. One condition,
  two texts, and an operator correlating logs cannot tell they are the same thing.
  Scheduled as M5b commit 6.
- **`engine/modes.py`'s handler docstring still reads "No I/O."** M5-0 superseded
  that rule with a bounded-I/O one — *the handler may perform I/O; it may not
  perform unbounded I/O* — and `CLAUDE.md` carries the replacement. A `src/`
  docstring contradicting the authority, which the M5a rotation could not fix
  because it allowed no `src/` changes outside the gate. Scheduled as M5b
  commit 7.

### Exchange behaviour still unresolved

- **`MARKET_LOT_SIZE` and `NOTIONAL.applyMinToMarket` on a *triggered* stop-type
  order — NARROWED, still UNRESOLVED.** What survives is a question about the
  **word**, not about the payload: does "market" mean an order submitted with
  `type=MARKET`, or any order that *executes* at market, including a triggered
  `STOP_LOSS`? Nothing states it, and settling it needs Binance's published spot
  documentation or a test that requires a stop to actually trigger — an
  irreversible fill.

  `applyMinToMarket` is **present, machine-readable and `true`** on both
  configured symbols, alongside `applyMaxToMarket: false`, `maxNotional` and
  `avgPriceMins: 5`. *Provenance: `GET /api/v3/exchangeInfo`, TESTNET, BTCUSDT and
  ETHUSDT, 2026-08-08, read-only.* So the minimum **does** apply to market orders;
  the payload was never silent about that, only about what counts as one.

  Sizing takes the stricter of `LOT_SIZE` and `MARKET_LOT_SIZE` rather than
  guessing, and M5a extended the same treatment to `_enforce`. On both configured
  symbols the market filter reports zeroed min/step, so the conservatism currently
  costs nothing; it is there for the symbol nobody has checked. **Under Q-C both
  protective legs are stop-markets, so if this binds, it binds on everything.**

- **`MAX_NUM_ORDER_LISTS = 20`, now modelled but still unread.** Measured on both
  configured symbols alongside `MAX_NUM_ALGO_ORDERS = 5` *(same provenance as
  above)*, and M5a put both on `SymbolInfo`. Q-C §3 counts algo slots carefully —
  a protected position costs 2 of 5 — and never counts **list** slots, though
  under Q-C every protected position **is** an order list.

  It cannot bind at `limits.max_open_positions = 3`, so this is not urgent. What
  makes it worth carrying is that **whether terminated lists age out of the count
  is UNKNOWN, and must not be assumed in either direction.** If the ceiling counts
  only live lists, 20 is unreachable here. If it counts lists created in some
  window, a bot trading one symbol on a 1-minute bar reaches 20 in twenty minutes
  and then fails at submission for a reason no code path anticipates.

- **`MarketLotSize.max_qty` is parsed but not read.** The "0 means no constraint"
  convention is per-field, not filter-wide: both Testnet and mainnet report a real
  `maxQty` beside zeroed min/step, so applying one rule to all three would either
  discard a live maximum or refuse every trade. Nothing enforces a maximum
  quantity today and `max_position_size_percent` already bounds size from above.
  Carried for fidelity to the wire and tested through the mapper.

- **The 36-character client-order-ID limit is ASSUMED, not measured.** It was
  asserted in a probe report and never verified. Q-C's ID scheme reaches it at
  generation >= 100 on a 12-character symbol. One deliberately over-long rejected
  request would settle it, free, and it is not a blocker.

- **A duplicate order *LIST* is UNMEASURED where a duplicate order *ID* is
  measured.** Q-C §8 classifies `-2010 'Duplicate order sent.'` as a *success*
  signal, and the timed-out-write recovery path depends on it. That guarantee is
  measured for a duplicate client order ID and **not** for a duplicate list.
  Settled by resubmitting an accepted list's exact parameters and reading the
  error — a rejection, so it costs nothing. **This is M5c's, not a soak question.**

### Risk and refusal-path debt

- **Two adjacent refusal-guard pairs remain unpinned by an ordering test:**
  `unsupported_action` against `no_mark_price`, and `no_mark_price` against
  `limit_refused`. The second is the one where a swap crashes rather than
  mislabels — equity is computed between the guards — so a test there would assert
  on an exception type and prove something other than ordering. Pre-existing debt
  that M4b illuminated rather than created. **M5a added two guards to this
  sequence** (`COMMITTED_RISK_UNKNOWN` before the limits, `UNMANAGED_HOLDING`
  after them) and pinned them through `_STAGE_CASES`; the two pairs above are
  unchanged.

- **`size_not_tradeable` against `unaffordable` is order-INDEPENDENT, a different
  claim from the entry above and not to be collapsed into it.** Those two are
  *unpinned*; this one is *unpinnable*. `is_tradeable` is `quantity > 0` and a
  negative quantity is forbidden, so `not is_tradeable` implies `cost == 0`, and
  the affordability guard is `cost > free_quote` — for any non-negative balance
  the two conditions are mutually exclusive and swapping the guards is
  unobservable in every reachable state. A test that bit would need a negative
  `free_quote` and would then fail on a harmless refactor while pinning nothing
  real.

- **`Position.protection`'s half of the committed-risk test is FIXTURE-ONLY.**
  Nothing in `src/` populates it until the reconciler exists, so today the
  operative condition is the absent stop level. A position whose requested stop
  was found *not* to be resting still prices committed risk off that stop —
  understating it, on the one position the system knows to be unprotected. Latent,
  because the reconciler that would produce the state does not exist. M5a built
  the signature that will not have to change when it is closed; **closing it is
  M5d's.** See `docs/QC_PROTECTIVE_ORDERS.md` §7.

- **QB §3 Class C names sites 1, 2, 3 and 5 in its premise and never returns to
  3.** Both readings are transcribed from Class C's own reasoning — the ledger is
  intact, which argues per-symbol like site 1; the position is unprotected, which
  argues portfolio-wide like site 5 — and the question is marked for adjudication.
  Unchanged by M5a.

### Environment and CLI

- **PAPER mode reaches Binance *mainnet* with empty credentials. Contained by
  M4a, not fixed.** This contradicts "Testnet is the default everywhere", so it is
  recorded rather than left in the code to be rediscovered.

  Two lines make it happen, each defensible alone: `Settings.binance_credentials`
  raises only when `mode.is_live_connection`, so PAPER and BACKTEST get `("", "")`
  back instead of an error; `BinanceClient.create` sets `testnet` from
  `settings.mode is TradingMode.TESTNET`, which is `False` for PAPER — so the
  adapter points at `api.binance.com`. `main.py` gates its own credential check on
  the same property, so nothing upstream catches it. Before M4a,
  `run --mode paper` opened an *unauthenticated mainnet* connection and streamed
  live production prices. Read-only, no order path — but a live-environment
  connection the mode name says should not exist.

  **M4a contains it:** `live_system` refuses a non-`is_live_connection` mode as
  its first statement, before any client is constructed. The underlying defect is
  untouched — anything building a `BinanceClient` outside the composition root
  still gets a mainnet client in PAPER mode.

  The real fix is a decision, not a patch: either PAPER resolves `testnet=True`
  (live prices from Testnet, which is what "live prices, no orders sent" almost
  certainly meant), or `binance_credentials()` refuses every mode that constructs
  a client. It belongs with `paper/simulator.py`, the milestone that gives PAPER a
  composition root of its own — **which is now also the milestone that must apply
  `CLAUDE.md`'s composition-root ownership rule**, promoted at M5a's rotation
  precisely because nothing told that author the root closes what it hands over.

- **A leak window in `BinanceMarketDataStream.create`, unreachable only because
  another file forbids it.** `create` awaits `_BinanceSocketSource.create` — which
  builds a **second** `AsyncClient` — and *then* calls `cls(...)`. If that
  constructor raises, the source is dropped without `aclose()`, leaking a live
  aiohttp session. Its three `ValueError`s are unreachable **only** because
  `config/models.py` rejects those values at load: `reconnect_backoff_s`
  `Field(gt=0)`, `reconnect_max_retries` `Field(ge=0)`, and `_check_backoff_bounds`
  for `max < base`, with `validate_assignment=True` closing the assignment path.

  **The coupling is cross-module and nothing links the two files.** Relaxing a
  config constraint, or constructing the stream from anything other than
  `EngineConfig`, opens the window silently. The smallest correct fix belongs in
  `websocket_client.py` rather than the composition root, which cannot see the
  source:

  ```python
  source = await _BinanceSocketSource.create(settings)
  try:
      return cls(source, ...)
  except Exception:
      await source.aclose()
      raise
  ```

  Not a live defect. Recorded because the reason it is safe lives nowhere near the
  code that is safe. For contrast, that second `AsyncClient` is otherwise closed
  correctly: `stream.stop()` calls `source.aclose()` unconditionally, outside the
  task guard, so it releases whether or not `start()` was ever called.

- **`main.py`'s two error paths disagree about which stream they write to.** One
  uses `log.error`, which reaches the console handler — **stdout** via
  `RichHandler`. The other uses `print(..., file=sys.stderr)`. So a configuration
  file that fails to *load* reports on stderr, while every `TradingBotError` after
  that — including all five M4a boot refusals — reports on stdout. An operator
  running `bot run 2>errors.log` captures nothing; one running `1>/dev/null` loses
  every refusal message. It also means the refusal text disappears entirely under
  `logging.console: false`. Small and self-contained, but a behaviour change to
  the CLI's contract, so it wants its own commit.

- **`make check` has never been executed through `make` on this machine.** `make`
  is not installed. The four delegating recipes are tab-indented (verified) and
  the gate itself no longer depends on `make`, but `$(PYTHON)` expansion and
  recipe execution remain unexercised. Needs one run where `make` exists.
  **Newly relevant:** the gate now refuses a piped stdout, and whether `make`
  hands a recipe a pipe or an inherited descriptor has not been measured here.
  Measure it in the same run rather than assuming.

- **`make cov` and `make format` do not honour `$(PYTHON)`.** They call bare
  `pytest` / `ruff`, so `make PYTHON=... cov` silently uses a different
  interpreter than `make PYTHON=... check` would. Outside the gate, so left alone;
  inconsistent, so recorded.

- **The `logging.file.json` flag controls console *and* file together.** There is
  no way to have a pretty console and a JSON file. Roughly three lines in
  `_console_handler` to separate; deliberately out of scope so far.

### Process and dependencies

- **Nothing enforces that the *prose* still describes the current plan.** The
  rotation procedure has been widened — `README.md` joined step 2, and a fourth
  step re-reads the contracts — but **the fix is a discipline, not a mechanism**,
  and discipline is what failed the first time. What would actually catch it is
  hard to automate honestly: "does this paragraph still describe the plan" is not
  greppable, and a check that fired on every superseded-looking sentence would be
  ignored within a milestone. The cheapest real improvement is probably a
  convention that a superseding decision names the contract section it supersedes,
  so the annotation becomes a lookup rather than a re-read.

  **M5a's rotation is weak evidence that the fourth step works** — it caught four
  stale `CLAUDE.md` claims and annotated eight contract sections — but it is one
  data point taken by the person who wrote the step.

- **Nothing enforces the documented counts.** They are updated by hand and have
  drifted within a single session more than once. `ruff format` and `mypy` each
  appear in **three** places: the fenced gate output in `CLAUDE.md`, the
  gate-scope table in `CLAUDE.md`, and `README.md`. **M5a's rotation is a live
  example of why grepping the digits matters rather than editing remembered
  lines:** neither of those two numbers moved, so the only sites needing an edit
  were pytest's — and a pass that had updated "the lines I changed" would have
  been correct by luck. Worth a check that reads the numbers from a live run, but
  it must not become a gate that fails for a reason unrelated to the code.

- **`ruff` and `mypy` are unpinned while every runtime dependency is pinned
  `==`.** `requirements-dev.txt` floats the two tools that *produce the numbers
  the gate reports*. A pin in this project encodes a **verified** version, not a
  working one — `pydantic`, `pandas` and `numpy` carry line comments saying so —
  and by that standard these two have a stronger claim than most: a `ruff` minor
  release can change `ruff format`'s output and turn the gate red on a tree
  nobody touched, and a `mypy` release can add a check that fails a file it
  passed yesterday. Either failure looks like a regression in the code and is
  not one.

  Deliberately not fixed in passing: pinning them changes what a fresh
  `pip install -r requirements-dev.txt` produces for every contributor, and it
  wants the same decision as `pip-compile` below rather than a separate one.

- **Transitive dependencies still float.** The direct layer is pinned exactly;
  `websockets` / `aiohttp` under `python-binance` and friends resolve freely.
  `pydantic` pins `pydantic-core` exactly, so the `Money` guard's engine *is*
  locked; `pandas` constrains `numpy` only as `>=1.26.0`, so the float64 leak path
  is pinned by **our** direct line and would be exposed if that line were relaxed.
  The proper fix is `pip-compile` with hashes over a `requirements.in` — deferred
  because it changes the install procedure for every contributor and the Docker
  build, and wants its own decision.
