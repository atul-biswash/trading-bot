# Current milestone — M5c: the adapter surface and the first order

**M5 is six milestones, not one.** M5-0 (decisions), M5a (the vocabulary) and M5b
(the intent split and the widened port) are complete. **M5c is the first
milestone in this project that can place an order**, which changes what a mistake
costs: everything before it was recoverable by editing a file.

Read first: `docs/QC_PROTECTIVE_ORDERS.md` §3 (leg types and full parameter
sets), §6 (client order IDs), §8 (errors) and §4b (the discretionary close path);
`docs/M5_NUMBERS.md`; `docs/QB_ESCALATION.md`. The decisions themselves are
locked in `CLAUDE.md`; this file is the task list and the single home for live
open items.

---

## Closed by M5b — recorded so they are not re-raised

- **P1 — `Portfolio` mutates on read.** Met before the port moved. `realised_today`
  now derives the day by comparing `pnl_date` rather than assigning it, and both
  false docstrings are corrected. Commits 0 and 1.
- **P2 — the widened port must not admit an entry whose committed risk is
  unknown.** Met at commit 8, when `evaluate` joined the port and `approve` was
  deleted rather than widened.
- **The port's second false clause** — `approve`'s *"pure function of its
  arguments and the clock"*. Folded into commit 8 as planned; the method it
  described no longer exists.
- **`NO_MARK_PRICE`'s two divergent reason strings — closed by CONSTRUCTION, not
  by reconciliation.** Deleting `approve` removed one of the two speakers, and
  the **richer** message was preserved by choice: one site remains,
  `risk/manager.py:344`, carrying *"equity is unknown, so no limit can be
  checked"*. **Its scheduling label was wrong** — planned as "M5b commit 6", it
  closed at commit 8.
- **`engine/modes.py`'s "No I/O." handler docstring** — replaced by the bounded-I/O
  rule. **Its scheduling label was wrong too** — planned as "M5b commit 7", it
  landed at commit 5 (`7cdeb40`).

**The two wrong labels are kept rather than silently corrected, because they are
evidence about how the plan drifted.** Both items landed; neither landed where
the plan said. The numbering diverged at the very first reshaping and no document
noticed — `e99f3a7`'s own message calls it "M5b commit 6, mechanical" while this
file's plan called commit **1** the mechanical move. A plan that renumbers itself
silently is one whose labels cannot be used to check whether an item landed.

---

## What M5c delivers

Each item carries its **arming condition** — the event that turns it from latent
into live — because several of these are harmless today and dangerous the moment
something else lands.

### 1. Finding I and Finding X, together

They edit the same code — `live_system`'s priming loop — and splitting them means
touching it twice.

**Finding I — refuse a symbol whose tick is coarse relative to the configured
slippage.** `entry_limit` is derived under `ROUND_CEILING`, so it may exceed
`reference_price × (1 + max_entry_slippage)` by up to one tick, and
`max_entry_slippage` is therefore not an enforceable ceiling where `tick / price`
approaches it. Measured on the configured pairs: BTCUSDT `1.557e-7`, ETHUSDT
`5.303e-6`, both four orders of magnitude below the `1e-3` bound, so the excess
is immaterial *there*. At a 0.10 price on a 0.01 tick the realised slippage is
**10% against a 0.1% bound**.

The check is `tick / price > max_entry_slippage`, against a **live** price —
`PRICE_FILTER.maxPrice` is not a market price — and it is a **boot** refusal, not
a per-signal one: a per-signal check fires every bar on a symbol that can never
satisfy it. It belongs at boot because the tick is not known until `exchangeInfo`
is read.

*Arming condition:* a cheap symbol with a coarse tick is configured. Not reachable
on BTCUSDT or ETHUSDT.

**Finding X — the boot calls `get_balances()` twice, unmemoised.**
`engine/modes.py:449` in `_seed_portfolio` and `:509` for the unmanaged-holdings
snapshot. `get_symbol_info` is memoised per client instance; `get_balances` is
not, so the boot pays two round trips for one fact and the two snapshots can
disagree if a balance changes between them.

*Arming condition:* already live — it is two calls today. The disagreement window
matters more once positions exist.

### 2. The trailing milestone — undesigned, unassigned, unscheduled

Q-C §5 defers the whole trailing design to "the trailing milestone".
`CLAUDE.md` assigns *driving* `check_exit` / `advance_trailing_stop` to execution.
**The two disagree about which milestone owns it, and nothing schedules either.**

What exists: `update_trailing_stop` (pure), `RiskManager.advance_trailing_stop`
(writes the level onto the position), `should_exit` (reads it). What does not
exist: any caller. `advance_trailing_stop` is `trailing_stop`'s **only** writer
in `src/` and has no call site, so no production position can carry a trailing
level today.

*Arming condition:* whatever first drives the per-candle exit loop. Until then
every trailing test exercises code nothing calls.

### 3. Finding L — `realised_pnl` set with no `pnl_date`

`Portfolio(free_quote=…, realised_pnl=D("-77"))` leaves `pnl_date=None`, and
`realised_today` then returns `Decimal(0)`: a booked loss reads as zero. **The
direction is permissive** — the loss is hidden from the daily-loss check, which
permits entries an account is halted for.

**No validator can enforce the pairing while `record_realised_pnl` writes twice.**
Measured: adding the obvious `model_validator` produces **21 test failures**, and
it breaks the very first accrual — `record_realised_pnl` assigns `realised_pnl`
at one statement and `pnl_date` at the next, so with `validate_assignment=True`
the object is briefly in exactly the invalid state the validator forbids. Both
`mode="before"` and `mode="after"` re-run on assignment, so neither placement
escapes it.

**Prescribed shape: make the pair a single value object**, so the two fields
cannot be set independently and the invalid state is unrepresentable rather than
merely rejected.

*Arming condition:* **`persistence/` landing.** Today `src/` constructs
`Portfolio` in exactly one place (`modes.py:443`), passing only `quote_asset` and
`free_quote`, and no test constructs the invalid pair. A restore-from-disk path
that rehydrates `realised_pnl` without its date is precisely the shape that arms
it.

### 4. Collapse the multi-statement writes on `Position` and `Portfolio`

L's precondition, and already `CLAUDE.md`'s prescription for `Position`:
`advance_trailing_stop` writes `highest_price`/`lowest_price` and then
`trailing_stop`, and `record_realised_pnl` writes `realised_pnl` and then
`pnl_date`. Under `validate_assignment=True` each is observable mid-write, which
is why neither model may carry a cross-field `model_validator` today.

*Arming condition:* none — this is a precondition, not a defect. It blocks item 3
and the `ABSENT_BY_DESIGN`-implies-both-levels-absent invariant.

### 5. Not M5c's, and explicitly not closed

**Q-C §7's site-3 defect remains M5d's.** A position whose *requested* stop was
found not to be resting still prices committed risk off that stop, because that
level is non-`None` by definition — that is how the divergence was detected.
**M5b commit 13 did not close it.** Commit 13 closed the sibling defect: the
level *selected* was a trailing level that rests nowhere. Same consequence,
different cause, different discriminator — §7's is `ProtectionState`, commit 13's
was level selection. Fixing either leaves the other.

---

## Observations carried into the open items — states, not decisions

Recorded because they are known and unresolved. **None is a rule**, and none
should be written into `CLAUDE.md` as one.

- **W — 25 `type: ignore` sites across nine test files, and not all are the
  sanctioned kind.** `CLAUDE.md` sanctions one use: documenting a deliberate
  violation under test, such as passing a `float` where `Money` is expected. That
  covers the `[misc]` and `[arg-type]` cases. It does not obviously cover the
  `[method-assign]` and `[attr-defined]` monkeypatching in `test_main_shutdown.py`
  and `test_config.py`. `tests/` is outside mypy, so every one of them is inert as
  far as the gate is concerned — which is why the inventory grew without anything
  reporting it. **Undecided:** whether the sanctioned-use clause should widen to
  name monkeypatching, or the monkeypatching should change shape.

- **Three private `_Frozen` copies** — `core/assessment.py:39`,
  `core/models.py:124`, `risk/rules.py:121`. A shared public base was named at
  M5b commit 7 as the right long-term answer and deliberately deferred: it makes
  a base class part of the public surface, which is a decision about the domain
  layer rather than a tidy-up. The count is **unchanged at three** across M5b —
  `risk/manager.py`'s copy was deleted when the assessment family moved, and
  `core/assessment.py` gained one.

- **AA — `risk/__init__.py` re-exports 20 names and NOTHING imports the package
  surface.** Measured: no `from trading_bot.risk import …` anywhere in `src/`,
  `tests/` or `scripts/`; every consumer imports from the submodules.
  **Its own figure drifted while it sat here** — recorded as 18 when first
  observed, it is 20 now, because commit 9's `EntryIntent`/`ExitIntent` split
  added one net and commit 11's `derive_entry_limit` added another. An
  observation about an unused surface grew by 11% without anyone touching the
  question.

  **The remedy is deliberately NOT recorded.** Nobody has established whether the
  package surface is intended API for a future consumer, and deleting 20
  re-exports on the strength of "nothing imports them today" is the kind of
  cleanup that is only obviously right until someone needed one.

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

  **First-hand evidence that the refusal works, from M5b's rotation:** the guard
  fired on an assistant-issued `python scripts/check.py 2>&1 | tail -12` and
  printed its own instructions instead of running. So the refusal is exercised
  and correct. **It still says nothing about `make`** — that path remains
  unmeasured, and this evidence must not be read as covering it.

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

  **THE INVERSE HAZARD, and it belongs beside this one rather than in another
  document.** Grepping the digits guards against *missing* a count site. The
  inverse guards against *hitting one that is not a count* — because a prose
  commit can plant digits that a later count commit sweeps up.

  M5b's rotation is the worked example, and it nearly fired. The corrections pass
  wrote **"a 58% understatement"** into `CLAUDE.md`'s `_binding_stop` annotation;
  the counts commit that followed substituted `58 → 59` for mypy's file count. A
  digit-wide substitution would have rewritten a measured figure into a fabricated
  one — inside an annotation whose whole subject is a measurement. It survived
  only because the count sites were edited **by surrounding context rather than by
  pattern**.

  Note that the ordering *created* the exposure. Corrections-before-additions is
  right, and it is right for a reason unrelated to this: a new rule written into a
  document that still contains false statements inherits their credibility. The
  cost of that ordering is that the prose pass runs first and can plant the
  hazard the count pass then walks into. So the two rules are a pair — grep the
  digits, then edit by context — and `CLAUDE.md`'s count-coupling section carries
  a pointer here saying so, because a rule and its inverse kept in separate
  documents is how one of them gets applied alone.

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
