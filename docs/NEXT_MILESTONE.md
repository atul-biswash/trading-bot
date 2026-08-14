# Current milestone — M5e: the first dispatch

**THE RECONCILER SHIPS BEFORE THE FIRST ORDER, and that is a hard precondition
rather than a preference.** It is stated first because every other item here
assumes it.

M5d built the adapter surface: request types, per-leg enforcement, both
parameter mappers, both placement methods, the response mapper and the Q-C §6 ID
scheme. **Nothing calls any of it.** M5e wires it to the decision path — which
means it is the milestone that first sends an order the bot decided to send.

Read first: `docs/QC_PROTECTIVE_ORDERS.md` §4 (entry mechanics), §4b (the
discretionary close), §7 (reconciliation) and §8 (errors and the re-place branch
table); `docs/M5_NUMBERS.md`, whose `T_recon` definition was corrected at M5d's
rotation; `docs/QB_ESCALATION.md`. The decisions are locked in `CLAUDE.md`; this
file is the task list and the single home for live open items.

---

## Before M5e starts — the namespace, settled in advance this time

**M5e's finding namespace is `M5e-001` onward: three digits, zero-padded,
per-milestone, capacity 999.**

Per-milestone rather than carrying, because `CLAUDE.md`'s whole justification
for namespacing is **self-location** — `M5d-053` tells a reader which entry to
open, and a cumulative counter would destroy that. M5d consumed 89 of 999, so
capacity is not a live question and **no extension rule should be invented in
advance**; the two-character letter extension does not apply and lexical and
numeric ordering coincide across the whole range.

This is stated here because it is the obligation that was owed before M5d's
first commit, was not discharged, and cost two turns at the start of the
milestone. It should not be owed again.

---

## The five decisions M5e inherits, with arming conditions

Named rather than rediscovered. Each was a deliberate deferral, not an
oversight.

### 1. The `ExchangeClient` port declaration, with its first caller — `M5d-073`

The ABC is **untouched across all 11 of M5d's commits**, verified by an empty
diff rather than asserted. That was deliberate: finding GG binds a port
declaration to its implementation *and its production caller*, and the only
honest caller for a placement method is an executor. There is not even a
validation caller available — Binance offers **no test endpoint for order
lists** (MEASURED: `create_test_order` and `v3_post_order_test` are
single-order).

Manufacturing a caller would defeat GG while appearing to honour it. So the
declaration lands **with** the executor, in one commit, and the concrete methods
that already exist stop being adapter-only surface at that moment.

*Arming condition:* the executor. **This is the commit GG has been saved for.**

### 2. The per-call retry budget — `M5d-074`

`CLAUDE.md` requires the dispatch retry budget **per call, not per client**, and
`_call` has no per-call retry parameter. The placement methods therefore inherit
`retry_attempts=4`, whose worst case is `4 × requests_timeout_s + 3.5 s` of
backoff = **43.5 s**, against a `dispatch_deadline_s` of **9.0**. A *single*
attempt at the configured timeout is 10 s and already exceeds it.

Adding the parameter belongs at the dispatch site, because that is where the
budget is known. The method docstrings record the gap so it is not inherited
silently.

*Arming condition:* the first dispatch. **It is over budget today and the
methods say so.**

### 3. Whether to consume `orderReports` — `M5d-078`

**The case for.** The placement response is the **only** moment at which the
request and the venue's account of it can be compared without a second call.
After it, every confirmation is against what we *believe* we sent, reconstructed
from derivable IDs. Declining `orderReports` therefore makes the first
confirmation an *inference* rather than an observation, and every later one cost
a call.

**The case against.** Consuming it means `OrderList` holds two leg
representations, or two types exist for one concept — and the richer one is
available from exactly one endpoint, which invites callers to depend on data the
read path cannot supply.

*Arming condition:* M5e's confirmation step, **which is the thing that knows
whether it is call-bound.** The decision is M5e's; the argument is written so it
does not have to be re-derived.

### 4. Whether a filled leg stays visible to `get_open_orders` — `M5d-072`

UNMEASURED, and **a probe question rather than an implementation choice**.
`executedQty` on a *resting* order is a different observation from a *filled*
order appearing at all, and M5d measured only the first.

Nothing built at M5d depends on the answer: `get_own_open_orders` is scoped to
what **rests**, and a filled leg's absence is the correct answer to that
question. It bites only a caller that reads absence as "never existed".

*Arming condition:* a fill. Settling it needs an order that actually executes,
which is an irreversible action and belongs to whoever authorises one.

### 5. `get_order_list` and M5c-K — **RULED, see R13 below**

---

## R13 — the "did it place" query uses `v3_get_all_order_list`

**RULED.** M5e's timed-out-write recovery asks *did it place?* — and it must
**not** ask by our own client order ID.

**Why.** `get_order_list(list_client_order_id=…)` becomes `origClientOrderId` on
the wire, and **M5c-K records that a point query on an ID used twice has an
undefined answer**: the live order, the most recent, or a stale terminal one,
indistinguishable in the payload. That is not a remote corner — **`M5d-013`
measured that generation-0 IDs repeat within one dispatch by construction**,
because the ID is derivable from `(symbol, entry_bar_time)` and every attempt in
one bar derives the same one. The recovery path is precisely where the collision
is reachable.

**`v3_get_all_order_list` returns every list with its ID and status**, letting
the caller disambiguate rather than trusting the venue's choice — measured at
M5d returning all six of M5c's terminal lists, intact, after 1d16h.

**A correction this ruling rests on.** M5d commit 8's message claims
`get_order_list` is *"the only view of a terminated list"*. **It is not** —
`v3_get_all_order_list` and a per-leg `get_order` both show terminated state,
and probe 1 measured both. The claim was made from the endpoints then wired
rather than from the endpoints that exist (`M5d-086`).

**M5c-K stays UNMEASURED and is no longer a blocker**, because under this ruling
nothing load-bearing depends on it. It remains worth settling: one **read-only**
query against an ID that has been used twice, and M5c's probe already created
that condition on Testnet — though `M5d-054` bounds retention only from below,
so the cost is a query plus the risk the condition has aged out.

---

## Closed by M5d — recorded so they are not re-raised

- **The adapter surface exists.** Request types (the four `-1106` fields
  unrepresentable, not rejected), per-leg filter enforcement, both parameter
  mappers, both `BinanceClient` placement methods, the response mapper, and the
  Q-C §6 ID scheme with a guard that separates a LENGTH violation from a
  CHARACTER-CLASS one. Nothing calls any of it — that is M5e's.
- **`close()` routes through `_call`.** It was the only client method that did
  not, so a transport failure at teardown could propagate over the boot error
  that caused it. `idempotent=False`, because the flag means *is a connection
  failure safe to retry*, not *is this operation idempotent*.
- **The leg-array key and the leg type were wrong and are fixed.** The response
  mapper read an assumed key and mapped **zero legs from a three-leg payload
  without raising**; a test asserting the empty result defended it. Both
  corrected against a **captured** payload — the first this repository holds.
- **`get_open_orders` returns pending protective legs in `PENDING_NEW`**, so a
  recovery path asking "does anything rest" sees protection that has not
  activated. MEASURED for a `GTC`-working list; INFERRED for a §3-conformant
  `FOK` one, per arm 10's precedent.
- **The enumeration-versus-point-query question is settled by measurement.**
  `get_open_orders` carries §7's compare set; the list read-back returns
  identity triples and cannot. Enumeration is leg-level, the point query is
  list-level, and the four documents that disagreed were each describing one
  half.
- **The namespace decision was owed and is now discharged** — see the top of
  this file.

---

## Carried forward from M5d's list — unchanged, still open

### 3. NN's remedy — the extraction command's four indistinguishable empties

The rotation extractor returns nothing in four cases and they cannot be told
apart: the lookup matched no row; it matched the *wrong* row; the current
milestone's table has already been appended so `tail -1` has moved on; or the
range genuinely holds no blocks. **Unruled** — the remedy was never decided,
only the defect recorded.

*Arming condition:* the next rotation whose extractor returns empty and someone
must decide whether that means "no findings" or "not looked". **M5c's rotation
ran the extractor before appending its table precisely to avoid case three**,
which is a workaround, not a fix.

### 4. Finding I and Finding X, together

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

### 5. The trailing milestone

> **RULED at M5c. The earlier framing — "undesigned, unassigned, unscheduled" —
> is superseded and the reason is recorded rather than the label changed.** It
> read as an oversight, as though someone had merely forgotten to schedule it.
> It is not: **nothing can own this until a prior question is answered**, and
> assigning a milestone before that answer would be assigning work whose shape
> is undetermined.

**THE BLOCKING QUESTION, and ownership means nothing until it is answered:**
**does the trailing level rest at the venue, or does it not exist?**

**Why it is unassignable.** Under Q-C §3 the order list is **three legs** —
working `LIMIT`+`FOK`, below `STOP_LOSS`, above `TAKE_PROFIT` — and **none of
them is a trailing leg**. So a trailing level today has **no venue
representation**: it is written onto a `Position` in memory and nothing places,
amends or cancels an order for it. An owning milestone would first have to do one
of two things, and both are decisions above its pay grade:

1. **Amend Q-C §3's leg set**, so a trailing level rests at the exchange — which
   reopens a measured contract, and §3's leg types are MEASURED (`MARKET` refused
   as a working type, `-1159`; `LIMIT` refused in the pending-above slot,
   `-1158`). **Not answered here.**
2. **Accept a client-side trailing level** — which **Q-C §1 rejected outright**,
   in these words: *"**Rejected — client-side protection.** Its failure is
   unbounded: a crash, a lost socket or a deploy leaves an open position with
   nothing watching it."*

Option 2 is closed unless §1 is reopened; option 1 is open but is a contract
amendment, not a milestone. That is the whole of why no milestone can pick this
up as written.

What exists: `update_trailing_stop` (pure), `RiskManager.advance_trailing_stop`
(writes the level onto the position), `should_exit` (reads it). What does not
exist: any caller. `advance_trailing_stop` is `trailing_stop`'s **only** writer
in `src/` and has no call site, so no production position can carry a trailing
level today.

*Arming condition:* **the blocking question above, not a milestone.** Until it is
answered every trailing test exercises code nothing calls, and `CLAUDE.md`'s
clause assigning execution the job of *driving* `advance_trailing_stop` assigns
the driving of a method that writes a level nothing places — see the annotation
on that clause.

### 6. Finding L

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

### 7. Collapse the multi-statement

L's precondition, and already `CLAUDE.md`'s prescription for `Position`:
`advance_trailing_stop` writes `highest_price`/`lowest_price` and then
`trailing_stop`, and `record_realised_pnl` writes `realised_pnl` and then
`pnl_date`. Under `validate_assignment=True` each is observable mid-write, which
is why neither model may carry a cross-field `model_validator` today.

*Arming condition:* none — this is a precondition, not a defect. It blocks item 3
and the `ABSENT_BY_DESIGN`-implies-both-levels-absent invariant.

### 8. Q-C section 7's site-3 defect — now M5d's, not deferred again

**Q-C §7's site-3 defect remains M5d's.** A position whose *requested* stop was
found not to be resting still prices committed risk off that stop, because that
level is non-`None` by definition — that is how the divergence was detected.
**M5b commit 13 did not close it.** Commit 13 closed the sibling defect: the
level *selected* was a trailing level that rests nowhere. Same consequence,
different cause, different discriminator — §7's is `ProtectionState`, commit 13's
was level selection. Fixing either leaves the other.

> **DEFERRED at M5d, and the reason is SEPARABILITY, NOT LATENCY — the heading
> above is annotated rather than rewritten, because "now M5d's, not deferred
> again" was a commitment made in good faith and the record of why it could not
> be kept is the useful part.**
>
> **The fix is not separable from the vocabulary it needs.** Closing site 3 means
> the incoherent pair stops being trusted. But `_TRUSTED_PROTECTION` contains
> exactly one member, `ABSENT_BY_DESIGN`, and that member is the *only* route
> into `committed_risk`'s pricing arm — measured over the full space, **0 of 16
> `(protection, level)` pairings reach it once that pair is excluded**, because a
> coherent `ABSENT_BY_DESIGN` position has `stop_loss is None` and is already
> uncomputable. So the fix needs a trusted state a *coherent protected* position
> can hold, which is `ACTIVE`, and `CLAUDE.md` forbids creating an enum member
> before something writes it. **No writer exists until the reconciler.**
>
> **What attempting it anyway would have cost**, stated so this is not re-tried on
> the assumption it was merely unpopular: the pricing arm becomes unreachable;
> `MAX_OPEN_POSITIONS`, `ALREADY_IN_POSITION` and affordability are shadowed
> portfolio-wide behind `COMMITTED_RISK_UNKNOWN` **in production, not only in
> tests**; and `4926705`'s anti-rot test — the one holding the mark-to-stop
> decision in place — is retired. Fourteen tests change, and two of the fixtures
> carry comments explaining that they were written to pass the very gate the fix
> closes.
>
> **What DID land: M5d commit 1a**, a characterisation test pinning the incoherent
> pair as it behaves today, whose docstring says closing site 3 inverts it. The
> defect is now legible rather than merely known.
>
> **This is the THIRD deferral, and what distinguishes it is that the obstacle is
> now named and dated.** M5b deferred it by fixing the sibling defect and saying
> so; M5c deferred it by not reaching it. Both left "why not now" implicit, which
> is what let it be re-scheduled twice as though it were merely unstarted. This
> one names the blocking object (`ACTIVE`), the rule that blocks it (an enum
> member is not written until something writes it), and the milestone that
> unblocks both.
>
> *Arming condition:* **the reconciler's milestone — which is also when the fix
> becomes possible.** Those are the same event, and that coincidence is why
> deferring costs nothing: site 3 cannot arm before the machinery that would let
> it be closed exists. Confirmed from the tree at `4866719`: `Position` is
> constructed nowhere in `src/`, nothing assigns `Position.protection`, and no
> M5d work item creates either.

> **THE RECONCILER IS A HARD PRECONDITION OF THE FIRST DISPATCH, and it lands as
> M5e's OPENING block — before any order.** Recorded here because it is a
> scheduling constraint that three documents now depend on and none stated.
>
> The mechanism, per `M5d-014`: with only two `ProtectionState` members, no
> *coherently* protected position can ever be priced. A real protected position
> would be `ACTIVE`, which does not exist, so pre-reconciler it carries `UNKNOWN`,
> which is untrusted, which makes `uncomputable >= 1`, which under
> `stop_loss.enabled: true` refuses **every** entry portfolio-wide at
> `risk/manager.py:360`. **The first position M5e opens would stop all subsequent
> entries.**
>
> **Ruled as a CONSTRAINT, not a defect — an interlock firing correctly.** The bot
> declining to trade on a ledger it cannot price is the behaviour the
> uncomputable count was built to produce. What it is not is a wedge to be worked
> around: the answer is that the reconciler ships first, not that the interlock
> is loosened.

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

  > **WEAK evidence from M5c's probe, and it does NOT settle this item.** The run
  > created **five order lists on BTCUSDT in roughly two seconds** against the
  > ceiling of 20, with **no rejection**, and `v3_get_open_order_list` returned
  > **zero** immediately afterwards — every list having terminated on its `FOK`
  > working leg. *(TESTNET, 2026-08-12.)*
  >
  > That leans toward the ceiling counting **live** lists only. **It is weak and
  > must not be read as settling it**, for a reason this item states itself: five
  > against twenty does not exercise the boundary. A run that terminated 25 lists
  > and then placed a 26th would; nothing here did. **The instruction above stands
  > unchanged — the question must not be assumed in either direction** — and this
  > note is a data point, not an answer.

- **A client order ID is NOT a unique key across time, and reconciliation is
  keyed by ID. UNMEASURED, and it is M5d's foundation.** Measured at M5c: a
  client order ID is unique against **live** orders only, and a terminal order's
  ID is **released and immediately reusable** — identically for single orders and
  for order lists (`docs/QC_PROTECTIVE_ORDERS.md` §6 and §8).

  The consequence is not a collision at *placement* — that is settled, and the
  generation segment handles the resting case. It is a question about *lookup*.
  Two different orders can carry the same client order ID at different times, and
  `CLAUDE.md` keys reconciliation off **what was requested**, by ID. **Nobody has
  measured what a query by `origClientOrderId` returns when an ID has been used
  twice: the live order, the most recent, or a stale terminal one.** A reconciler
  that reads back the wrong order compares against the wrong truth, and the two
  answers are indistinguishable in the payload.

  **The mitigation is real and it is not an answer.** Q-C §6's scheme embeds
  `entry_bar_time_ms`, so a repeat is only reachable within the *same entry bar* —
  which bounds the collision to a narrow window and makes this a question rather
  than a defect. It does not establish what the query does inside that window.

  *Arming condition:* **the reconciler.** Nothing queries by client order ID
  today. Settled by one **read-only** query against an ID that has been used
  twice — and M5c's probe has already created exactly that condition on Testnet,
  so the measurement costs a single call and no order.

- **`-1128` is DELIBERATELY UNCLASSIFIED, and that is a ruling rather than an
  omission.** M5c's classifier arc classified `-1106`, `-1159` and `-1158` as
  `ContractViolationError`; `-1128` is named beside them in Q-C §8 and is **not**
  classified with them.

  **Why not, and both rejected options are the instructive part.** Classifying it
  with the group is an argument from **adjacency** — it appears next to the other
  three in one sentence of one document, and that is the entire case for it.
  `EXPIRED_IN_MATCH` is already on the record for exactly this shape: *moving it
  requires a measurement, not an argument from its name.* Measuring it first is
  not a request but a **search** — no call is known to provoke `-1128`, forbidden
  fields yield `-1106`, so finding one means guessing invalid parameter
  combinations with no bound on attempts, for a code that has no consumer. That
  is the discovery-loop trap `CLAUDE.md` records from Q-C's schema walk.

  **Nothing is lost by leaving it.** `ExchangeAPIError` carries `code=`, so a
  `-1128` reaches an operator as `-1128` and can be looked up. A test asserts the
  fall-through, so the ruling is enforced rather than merely recorded: adding
  `-1128` to `_CONTRACT_VIOLATION_CODES` fails it.

  *Arming condition:* **the first time a `-1128` is actually observed.** At that
  point there is a message to match and a condition to name, and it joins the
  group — or does not, on its own evidence.

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

  > **MEASURED at M5c and CLOSED — the assumed figure was right.** 36 characters
  > are accepted, 37 rejected with `-1100`, HTTP 400, and the venue states its
  > own rule: `^[a-zA-Z0-9-_]{1,36}$`. The character class is measured with the
  > length, and a LENGTH violation is reported as "Illegal characters found",
  > which is the sharp edge. Kept here rather than deleted because the item
  > recorded a claim that was ASSUMED for two milestones, and that it turned out
  > correct is not the same as its having been known.

- **A duplicate order *LIST* is UNMEASURED where a duplicate order *ID* is
  measured.** Q-C §8 classifies `-2010 'Duplicate order sent.'` as a *success*
  signal, and the timed-out-write recovery path depends on it. That guarantee is
  measured for a duplicate client order ID and **not** for a duplicate list.
  Settled by resubmitting an accepted list's exact parameters and reading the
  error — a rejection, so it costs nothing. **This is M5c's, not a soak question.**

  > **SETTLED at M5c, and the answer was the opposite of the one this item
  > assumed. "A rejection, so it costs nothing" is FALSIFIED — there was no
  > rejection and no error.** The duplicate was **accepted**, and so were both
  > control arms; see `docs/QC_PROTECTIVE_ORDERS.md` §8 for the measurement and
  > `CLAUDE.md`'s timed-out-write annotation for what it costs.
  >
  > **The cost clause was wrong in its mechanism as well as its number.** The run
  > created **five order lists rather than one** — the original, the exact
  > duplicate, two control arms and the accepted 36-character ID test. All five
  > terminated immediately and the account's balances were unchanged end to end,
  > so the probe was in fact harmless — **but it was contained by `FOK`, not by
  > the expected rejection.** A rule that reasons "this probe is free because the
  > venue will refuse it" would have been wrong about *why* it was safe, and would
  > have carried that reasoning to a probe where `FOK` was not in the design.

  > **CORRECTED AGAIN AT M5c, AND THE ANNOTATION ABOVE IS THE ONE THAT WAS
  > WRONG. Now CLOSED.** Arms 1-9 all ran against a *terminated* original and
  > concluded that order lists are not deduplicated. Arms 10-11 measured the
  > live case directly: a list confirmed `EXECUTING` by read-back, resubmitted
  > byte-identical, returned **`-2010` HTTP 400 "Duplicate order sent."** So
  > Q-C §8's classification holds and `CLAUDE.md`'s recovery rule **stands as
  > written**.
  >
  > The rule is **a client order ID is unique against LIVE orders only; a
  > terminal order's ID is released and immediately reusable**, identically for
  > single orders and lists. The defect was in the ARM SET's design, not in any
  > measurement it made: every arm sampled one state, and ID-release and
  > absence-of-deduplication predict identical results in that state.

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
