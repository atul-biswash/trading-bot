# Current milestone — M5f: the executor, and the first order

**THE EXECUTOR IS THE MILESTONE EVERY DEFERRAL IN THIS FILE HAS BEEN WAITING
FOR.** Nine carried items name it or something it causes; five name it
literally. It is stated first because the size of that queue is the milestone's
real shape, not the code that dispatches an order.

M5e built the reconciler — a pure classifier, a per-symbol pass, a point-query
resolver, a candle-subscribed driver, the trust admission and the staleness
refusal. **Every piece of it is inert.** Nothing constructs a `Position` in
`src/`, so the first position this milestone opens exercises seven components
against reality simultaneously and for the first time. That is the risk M5f
carries, and no test can retire it in advance.

Read first: `docs/QC_PROTECTIVE_ORDERS.md` §4 (entry mechanics), §4b (the
discretionary close), §6 (the ID scheme), §7 (reconciliation, whose site 3 is
now closed) and §8 (errors and the re-place branch table); `docs/M5_NUMBERS.md`,
whose §4 and §6 were annotated at M5e's rotation; `docs/QB_ESCALATION.md`, whose
site 4 is now split. The decisions are locked in `CLAUDE.md`; this file is the
task list and the single home for live open items.

---

## Before M5f starts — the namespace

**M5f's finding namespace is `M5f-001` onward: three digits, zero-padded,
per-milestone, capacity 999.**

Per-milestone rather than carrying, because `CLAUDE.md`'s whole justification
for namespacing is **self-location** — `M5e-053` tells a reader which entry to
open, and a cumulative counter would destroy that. **M5e consumed 89 of 999**,
which is the first real datum on capacity: the three-digit scheme is not close
to binding, and no extension rule should be invented in advance.

Stated here before the first commit, which is where it belongs — M5d owed this
and did not discharge it, and M5e discharged it and then spent 89 identifiers
without incident.

---

## The executor's inherited queue — nine items, five naming it literally

**This queue has accumulated across four milestones and had never been counted
until M5e's rotation counted it.** Each entry below links to its full section;
this table is the size of the obligation, not a replacement for the reasoning.

| Item | ID | What the executor owes |
|---|---|---|
| 1 | `M5d-073` | Declare the placement methods on `ExchangeClient` **in the same commit** as their production caller — the commit finding GG has been saved for |
| 9 | `M5e-016` | Assert the `get_symbol_info` cache and **refuse to dispatch on a miss** — ruled, recorded, deliberately unimplemented |
| 13 | `M5e-054` | Nothing to build: opening the first position is what makes the reconciler's livelock reachable at all |
| 14b | `M5e-075` | Construct every `Position` with `ProtectionState.UNKNOWN` |
| 14 | `M5e-069` | **Superseded — see the annotation on item 14.** Its condition named the executor for a refusal that landed at M5e |

Four more are armed by what the executor *causes* rather than by the executor
itself: **item 2** (`M5d-074`, the per-call retry budget — "the first
dispatch"), **item 4** (`M5d-072`, whether a filled leg stays visible — needs a
fill), **item 12** (the pipe rule's scope — "the first test that places an
order"), and **item 3** (`M5d-078`, `orderReports` — names a confirmation step
that does not exist).

**A tenth is not on this list and should be**: `QB_ESCALATION.md`'s site 4
escalation half, blocked on a halt flag. Its arming condition names the halt
flag's first writer rather than the executor, and whether that is the same
commit is undecided.

---

## The five decisions M5f inherits, with arming conditions

Named rather than rediscovered. Each was a deliberate deferral, not an
oversight.

> **AN ARMING CONDITION NAMES ITS CALLER, NOT AN EVENT. Added at M5e, after two
> of the five armed earlier than their stated conditions predicted.**
>
> An event-named condition dates the answer by when the *world* will supply it.
> What actually arms a deferred item is the first **caller that cannot proceed
> without it**, and callers are ordered by the design rather than by events. The
> two orderings are not the same, and where they differ the caller always comes
> first — because the design is what decides which component is written next.
>
> Both misses ran in the same direction, which is the one that costs. `M5d-072`
> said *"a fill"* and is needed by the reconciler's classifier, which must decide
> what an absent leg means long before anything fills. `M5d-074` said *"the first
> dispatch"* and is needed by the reconciler, which this file orders **before**
> any dispatch, because `reconcile_deadline_s` bounds a **read**. Each is
> re-stated in caller terms in its own section below; the sections are annotated
> rather than rewritten, and nothing is renumbered.
>
> The rule generalises past these two: an item whose arming condition names an
> event has not been checked against the build order, and the check is cheap —
> ask which component is written next and whether it can be written without the
> answer.
>
> Ruled by the reviewer under delegation, not by the project owner.

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

> **PARTLY LANDED AT M5e's C2, and the arming condition is re-stated. Annotated
> rather than rewritten, because what changed is which half is outstanding.**
>
> **Two sentences above are now false.** *"`_call` has no per-call retry
> parameter"* — it has one, optional, defaulting to the client's value.
> *"The method docstrings record the gap"* — they now record that the budget is
> **expressible and unset**, which is a different statement. The arithmetic is
> untouched and still correct: `4 x requests_timeout_s + 3.5 s` = 43.5 s against
> a `dispatch_deadline_s` of 9.0.
>
> **What is outstanding is the NUMBER, not the mechanism**, and it is carried
> below under the M5e section rather than here.
>
> **Arming condition, in caller terms: the RECONCILER, not the first dispatch.**
> This file already orders the reconciler first — *"THE RECONCILER IS A HARD
> PRECONDITION OF THE FIRST DISPATCH, and it lands as M5e's OPENING block —
> before any order"* — and `reconcile_deadline_s` bounds a **read**. So the first
> caller that must choose an attempt count is a reader, and it exists before
> anything dispatches. Naming the write path dated this item to a milestone
> later than the one that needs it.
>
> Ruled by the reviewer under delegation, not by the project owner.

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

> **NO LONGER BLOCKING ANYTHING. Annotated at M5e's S1, and both sides of the
> argument above survive untouched.**
>
> It became load-bearing for one turn: "stamped at construction" was one of the
> three live readings of `last_reconciled_at is None`, and that reading is
> honest **only** if the executor has observed venue state, which is what
> consuming `orderReports` would supply. So the staleness ruling appeared to
> depend on this one -- whose own arming condition names a confirmation step
> that does not exist, because there is no executor.
>
> **S1 cut that dependency by ruling the other way**: the executor writes
> `ProtectionState.UNKNOWN` at construction, so nothing is trusted until the
> reconciler has seen its protection resting, and no observation is needed at
> construction time at all.
>
> **So this returns to being an OPTIMISATION with a recorded loss** -- one
> saved round trip on the first confirmation -- rather than a prerequisite. The
> asymmetry that decided it: ruling as S1 did leaves this open and adoptable
> later if `orderReports` is ever measured, while ruling the other way would
> have required the measurement first, and the measurement requires a dispatch.

### 4. Whether a filled leg stays visible to `get_open_orders` — `M5d-072`

UNMEASURED, and **a probe question rather than an implementation choice**.
`executedQty` on a *resting* order is a different observation from a *filled*
order appearing at all, and M5d measured only the first.

Nothing built at M5d depends on the answer: `get_own_open_orders` is scoped to
what **rests**, and a filled leg's absence is the correct answer to that
question. It bites only a caller that reads absence as "never existed".

*Arming condition:* a fill. Settling it needs an order that actually executes,
which is an irreversible action and belongs to whoever authorises one.

> **THE MEASUREMENT STILL NEEDS A FILL; THE ITEM NO LONGER WAITS ON ONE.
> Annotated at M5e, and the distinction is the whole of the correction.**
>
> *"a fill"* dates this item by when the answer can be **obtained**. What arms it
> is the first caller that cannot proceed without it, and the paragraph above
> already names that caller without recognising it: *"It bites only a caller
> that reads absence as 'never existed'."* **The reconciler's classifier is
> exactly that caller.** It maps requested levels against resting legs to a
> `ProtectionState`, so it must decide what an ABSENT leg means — and absence is
> shared by never-placed, cancelled and, if the answer is no, filled.
>
> M5e's probe 2 sharpened the question without settling it: after a cancel,
> `get_open_orders` returned `[]` while `v3_get_order` still reported
> `CANCELED`, so enumeration-absence and point-query-status are genuinely
> different instruments. That was measured on a **cancel**. The filled case is
> untouched, and generalising one terminal state to another is the arm-set error
> `M5c-I` records.
>
> **So the classifier must be written to a stated assumption about absence, and
> the assumption named where it is made** — not deferred until a fill happens to
> occur. The probe remains owed and remains an authorised-action question.
>
> Ruled by the reviewer under delegation, not by the project owner.

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

> **PARTLY DISSOLVED, and the part that survives is smaller than it was —
> `M5e-091`.** M5e's rotation was the tag-anchored extractor's **first live
> use** since it replaced the table lookup, and it did not return empty: 22 of
> 22 commits reached, 22 carrying blocks, 84 entries, 83 distinct IDs.
>
> **Two of the four cases are gone by construction.** "The lookup matched no
> row" and "it matched the wrong row" were properties of the `sed`-into-the-table
> anchor; a tag either resolves or is fatal — `fatal: ambiguous argument`,
> exit 128, no output — so neither can produce a quiet empty any more.
>
> **Case three is unchanged and still needs the workaround.** Appending the
> milestone's table row does not move a *tag*, so the tag-anchored form is
> immune to that — but the rotation still runs the extractor before writing the
> entry, now for a different reason: the entry must report the finding count,
> and its own commit changes it.
>
> **Case four is unchanged and undecidable from the output alone.** An empty
> result still cannot distinguish "no findings" from "not looked", and the
> procedure's own text still says to read it against `git log --oneline` over
> the same range.
>
> **What M5e added is a check that could have distinguished a plausible empty
> from a real one**, which is the thing `M5e-001` said was missing. See the
> composition recorded under the rotation's own findings: header parity rules
> out a truncated tail, ID density rules out a missed middle, and neither alone
> suffices.

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

> **CLOSED AT M5e — and by a change no deferral predicted. `M5e-084`.** All
> three deferrals named `ACTIVE` as the prerequisite. What actually closed site
> 3 was the **`DIVERGED` write plus the whitelist's existing untrusted
> default**: a position whose requested stop is found not to rest carries
> `DIVERGED`, which is outside `_TRUSTED_PROTECTION`, so `committed_risk` counts
> it uncomputable and never prices off that stop. No code was written for site 3.
>
> `ACTIVE`'s admission, one commit later, did the **opposite** thing — it
> widened the pricing arm so a *correctly* protected position stops counting
> uncomputable, which is what stops the first live position refusing every entry
> after it. The two changes point in opposite directions and only the first is
> site 3's.
>
> **The transferable part:** a defect deferred behind a named prerequisite can
> be closed by something else entirely, and nothing re-checks the prerequisite
> once it is written down. Three deferrals restated the same blocking object
> without re-deriving whether it was still the blocker.
>
> **UNEXERCISED.** Nothing constructs a `Position`, so no position has carried
> `DIVERGED` outside a test. Closed by construction, unobserved in operation.
> Full annotation in `docs/QC_PROTECTIVE_ORDERS.md` §7.

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

## Carried from M5e's own work — new, and each names its caller

Four items opened by M5e's correction and mechanism commits. Arming conditions
are stated in caller terms per the rule at the head of this file. None of these
prejudges an open ruling.

### 9. `get_symbol_info`'s cache assumption — `M5e-016`

**The one exclusion from the per-call transport bound that sits on a timed
path.** `AsyncClient.get_symbol_info` takes an explicit `symbol` rather than
`**params`, so there is no dict for the channel to ride, and it delegates to the
whole-exchange payload. It is reached from `_enforce` and from both `_prepare_*`
methods, so a cache miss spends an **unbounded** call inside a sequence bounded
by a derived per-call share of 3.0 s.

**Why it is safe today, and why that is not reassuring.** `_prime_pairs` fetches
every configured symbol at boot, and `refresh_symbol_info` has **zero callers in
`src/`**. Both facts live in other files, neither is visible from the adapter,
and either is reversible without anything reporting it.

**RULED: assert the cache and REFUSE to dispatch on a miss.** The asymmetry
decides it rather than a measurement — a spurious refusal is reversible and
costs one missed trade, while an unbounded round trip inside a bounded sequence
manufactures the ambiguous write the budget exists to prevent, and no later edit
un-places an order. That is `CLAUDE.md`'s rule for exactly this shape: *"WHERE A
CONSTRAINT IS UNMEASURED, TAKE THE READING WHOSE WRONG ANSWER IS REVERSIBLE."*

Two alternatives are recorded as rejected rather than unconsidered: lowering the
client-wide timeout bounds it but binds every call including the ones that want
patience; and pre-resolving `SymbolInfo` at the dispatch site removes the lookup
from the timed path but changes what `_prepare_*` takes, which is a wider change
than this ruling needs.

*Arming condition:* **the executor**, as the first caller of `create_order` and
`_prepare_otoco`. **Recorded, deliberately not implemented** — the refusal has
no caller to refuse yet, and adding one now is surface without a caller.

### 10. R13's endpoint has no wrapper and takes no per-call bound

R13 rules that M5e's timed-out-write recovery asks *did it place?* through
`v3_get_all_order_list`, on the grounds that a point query by our own ID has an
undefined answer once an ID has been used twice. **That endpoint is on neither
the `_AsyncBinanceAPI` Protocol nor `BinanceClient`** — enumerated at M5e, and
unchanged since.

**Two consequences, and they are separate.** The widening that adds it must also
give it `timeout_s` and `attempts`, or the recovery path — which runs *inside*
the dispatch budget, at the moment the budget is already known to be under
strain — is the one call in the sequence that nothing bounds. And **C2's stated
justification for budgeting `get_order_list` is superseded**: C2 cited the
timed-out-write recovery role, which R13 had already moved. **Its inclusion
stands on a different footing** — Q-C section 7 keeps it one irreplaceable use,
*"it is a view of a **terminated** list, which distinguishes 'never placed' from
'placed and already gone'"* — so nothing is removed; the reason written down was
the wrong one.

*Arming condition:* **the read-surface widening** — the commit that first
declares a read method on the port for a caller that needs it.

### 11. The per-call bound shipped without its values

C2 shipped the mechanism with **no number anywhere in `src/`**: no config field,
no changed default, no attempt count and no timeout. Both values derive from
`risk.dispatch_deadline_s` and `risk.reconcile_deadline_s`, and `M5_NUMBERS.md`
marks each **PLACEHOLDER -- NOT MEASURED**. Neither status mark is touched here
and no value is proposed.

**What a later derivation must not do, from the only samples that exist.** M5e's
probe 2 timed six `get_open_orders` calls against Testnet: `180.6, 451.6, 446.2,
182.3, 181.9, 452.5` ms. They are **bimodal** — roughly 180 and roughly 450, with
nothing between — on identical requests from one host in one session. **Their
mean of 315.8 ms describes no call that happened**, so a value derived from a
mean would sit in the gap and time out every slow-mode call. **A value must
clear the SLOW mode**, and what decides it is a tail rather than a centre.

**Six samples from one host bound nothing** — not the tail, not another network
path, not a busier venue, and the cause of the bimodality was not instrumented.
This records what the samples forbid, not what they permit.

*Arming condition:* **the reconciler**, which is the first component that spends
a budget, and by the rule above is also what arms `M5d-074`.

> **ARMED AND PARTLY DISCHARGED AT M5e.** The reconciler shipped and its driver
> derives three values from config: `timeout_s = reconcile_deadline_s`,
> `attempts = 1` (forced by `attempts x timeout_s <= T_recon`, since splitting
> the deadline into a per-attempt share is a tail claim six bimodal samples
> cannot support), and a phase-wide call count of `max_open_positions`.
>
> **No number was written into `src/`, and both status marks are untouched.**
> `reconcile_deadline_s` and `max_position_staleness_s` remain PLACEHOLDER — NOT
> MEASURED. What the driver derives, it derives from those placeholders, so the
> arithmetic is enforced on an unmeasured base.
>
> **`M5d-074`'s DISPATCH half is still owed**, and is on the executor's queue:
> `dispatch_deadline_s` has no reader, and the placement methods still inherit
> the client-wide retry policy whose worst case is 43.5 s against a 9.0 s
> deadline.

### 12. The pipe rule's scope, and how close the suite is to it

`CLAUDE.md` scopes the pipe rule to *"ANY COMMAND WHOSE OUTPUT CANNOT BE
REGENERATED"*, and names commands with **side effects** as exactly such
commands. The gate is merely the instance that has a guard.

**The credentialed suite makes real Testnet calls**, and is regenerable **only**
because those three tests are, in `CLAUDE.md`'s words, *"read-only against
Binance **Testnet**, never place an order"*. That is a property of the tests, not
of `pytest`.

**So the moment any test places an order, piping the suite becomes a breach** —
not because the command changed, but because its output stopped being
reproducible. Recorded now because the milestone that would add such a test is
the one being built, and the rule is easiest to apply before the test exists.

*Arming condition:* **the first test that places an order.** No such test exists;
M5e's Testnet work was done from scratchpad probes outside the tree precisely so
that it did not.

### 13. What the last-call reservation costs — `M5e-053`, `M5e-054`, `M5e-055`

The pass reserves its last call for the resolver once a leg comes back
unresolved, and does not stamp a position whose legs it could not all query.
Three costs follow. **None is a defect to fix here**; each is a consequence of
a scheme that was chosen over a strictly worse one, and each is recorded so it
is not rediscovered as a surprise.

**Resolution progress is ALL-OR-NOTHING, not incremental — `M5e-053`,
MEASURED, and it falsifies the 2k-cycle bound this item was drafted around.**
The bound assumed one leg resolved per cycle, so `2k` cycles for `k` positions
holding two legs each. It does not happen. `classify_protection` derives its
`missing` tuple in fixed sorted leg order from the book, every cycle, and
`resolve_unresolved_legs` spends its budget from the front — so with a budget
of one and two absent legs, **the same leg is queried on every cycle and the
second is never reached.** Measured over four cycles: `queried=['0-SL']` each
time, `TP` never. Progress would need per-leg memory, and the stamp — the only
state this scheme keeps — cannot carry it.

So the correct statement is: **either the leftover covers every outstanding leg
in one cycle, or the position never completes.** The leftover is
`max_calls - due`, which is the reservation's one call at saturation and more
when positions are fewer than the cap.

> **The FIRST SENTENCE STANDS; the leftover formula is SUPERSEDED.** Annotated
> rather than edited, because the all-or-nothing finding is what made the fix
> derivable and only its arithmetic moved.
>
> The leftover is no longer `max_calls - due`. Under the L-leg reservation the
> pass stops early, at `len(results) + reserved >= max_calls`, so the leftover
> is `max_calls - len(results)` and is **at least** what the first unresolved
> position needs. All-or-nothing is therefore satisfied rather than worked
> around: the leftover now covers every outstanding leg of one position, and
> that position completes.

**The priority inversion is DELIBERATE — `M5e-054`.** Unresolved positions carry
old or absent stamps, so they sort first and are read before healthy ones.
Verifying suspect protection ahead of re-reading protection already believed
sound is the right order: the suspect one is why the portfolio is refusing.
MEASURED on the shipped shape (`max_calls = 3`, `T_min = 60 s`,
`max_position_staleness_s = 180`) with `k = 2`: the two unresolved positions
consume both spendable calls every cycle, the reservation takes the third, and
**the healthy position is never read at all** — its stamp ages 60, 120, 180,
240 s and exceeds the threshold at the fourth cycle, permanently.

That is contained rather than harmless: an unresolved position is `UNKNOWN`,
which is untrusted, which already refuses every entry portfolio-wide, so the
stale healthy position adds no new refusal. What it does add is a second
condition arriving at the escalation that does not exist yet.

> **RESTATED at M5e's driver commit: this is a LIVELOCK, not a staleness
> bound.** The two readings differ in what they imply. A staleness bound says
> healthy positions are read late; a livelock says reconciliation **permanently
> stops reading them**, because the unresolved positions sort first, consume
> every spendable call, never complete, and therefore never stop sorting first.
> Nothing in the cycle advances. It is reachable from ordinary divergence
> whenever `k >= max_calls - 1` positions are unresolved -- all but one.
>
> **Inert today**: `Position` is constructed nowhere in `src/`, so
> `open_positions` is empty and no pass has anything to livelock over.
>
> *Arming condition, in caller terms:* **the executor**, as the first thing that
> opens a position.
>
> **The cause is the reservation's SHAPE, not the driver's numbers**, and no
> in-constraint derivation dissolves it: the admissible range is
> `max_calls <= max_open_positions`, the driver already takes the maximum, and
> the measured livelock ran at that maximum. The remedy is to reserve what the
> FIRST unresolved position needs -- `L` legs, capping the pass at
> `max_calls - L` -- which completes positions one at a time, keeps
> `P + L <= max_calls` by construction, and terminates in `k` cycles instead of
> never. It does not close `max_open_positions = 1`, where the reserve is zero.
> Scheduled as its own commit after the driver.

> **CLOSED, and the closure is SCOPED to `max_calls >= L + 1`.** MEASURED
> against the real functions on the scenario that produced the livelock -- two
> unresolved two-leg positions and one healthy, `max_calls = 3`, `T_min = 60 s`:
>
> | cycle | read | queried | outcome |
> |---|---|---|---|
> | 1 | `['BTCUSDT']` | `SL`, `TP` | BTCUSDT completes, stamped |
> | 2 | `['ETHUSDT']` | `SL`, `TP` | ETHUSDT completes, stamped |
> | 3 | `['SOLUSDT', 'BTCUSDT']` | `SL` | the healthy position is read |
> | 4 | `['BTCUSDT']` | `SL`, `TP` | BTCUSDT completes again |
>
> Against commit 2's measured baseline of `read=['BTCUSDT','ETHUSDT']` every
> cycle, `queried=['0-SL']` forever, and the healthy position **never read**.
> Cycle 3 also shows the late-discovery case -- BTCUSDT is visited second, so
> its reservation lands after the budget is spent and it does not complete that
> cycle -- and cycle 4 shows it self-correcting, because it stayed unstamped and
> therefore sorted first.
>
> **The scope is arithmetic, not a weakness.** Completing an `L`-leg position
> costs `1 + L` calls: one enumeration to discover it, `L` point queries to
> resolve it. Below that, no scheme respecting `total <= max_calls` can finish
> it. `max_open_positions = 1` is unchanged and stays open under `M5e-055`.

### 13a. The config relation nothing validates -- `M5e-066`

**`max_open_positions >= L + 1`, where `L` is the number of ENABLED protective
levels.** Both enabled gives `L = 2` and needs `3`; a stop alone gives `L = 1`
and needs `2`; neither gives `L = 0` and the relation is vacuous. A take-profit
with no stop is refused at config load, so those are the only three
combinations. **MEASURED**, by building each through `AppConfig.model_validate`.

**The coherence validator cannot catch a violation, and that is the half worth
recording.** It checks `p_sim x dispatch + n_max x reconcile <= budget`, in
which `n_max` carries a positive coefficient -- so **lowering**
`max_open_positions` only loosens the inequality. MEASURED on the shipped
config with both levels enabled: `1`, `2`, `3` and `4` are all ACCEPTED and
only `5` is refused, and it is refused for being too *large*. A config with
`max_open_positions = 2` and both protective levels therefore **boots clean and
fails at the first divergence**, with a position that can never finish
resolving.

That configuration is not one anyone would flag on sight: an operator choosing
`max_open_positions = 2` with both a stop and a take-profit is choosing *more*
caution, and gets a reconciler that cannot complete a position as the reward.

**No validator rule is added here, deliberately.** The relation couples
`risk.limits.max_open_positions` to `risk.stop_loss.enabled` and
`risk.take_profit.enabled` -- three fields across two sections that nothing
relates today -- and inventing that coupling in passing is how a coherence rule
gets written without the reasoning that justifies it. Recording the relation is
what stops it being rediscovered from a live failure.

*Arming condition, in caller terms:* **whoever writes the next coherence rule**,
as the first author with reason to relate those fields.

**`max_open_positions = 1` is a total resolution hole, and its cost reaches a
reserved ruling — `M5e-055`.** With one due position the pass spends the only
call the reservation admits and the remainder is zero, every cycle: the legs
are never queried, so the position is never stamped and `last_reconciled_at`
stays `None` permanently. No reservation scheme closes this — one call cannot
fund two instruments — and alternation would need a discriminator that is a
second reading of position state.

The cost is **not only report quality.** `DIVERGED` is never reached, so §7's
re-placement can never arm; that much is report. But a permanently `None` stamp
lands directly on the reserved ruling about what `None` means for the staleness
refusal, and the three live options do not agree: under **maximally stale** the
position refuses entries portfolio-wide forever and the bot never trades again;
under **exempt until first stamped** and under **stamped at construction** it
does not. **The ruling is not made here**, and this is recorded so that it is
made knowing a legal configuration turns one of its options into a permanent
halt.

*Arming condition:* **the ruling itself**, which the driver's milestone forces.

> **THE RULING IS MADE (S1: `None` is maximally stale), and the paragraph above
> OVERSTATES what it costs.** Annotated rather than rewritten, because the
> mechanism it describes is right and only its consequence was inflated.
>
> *"the position refuses entries portfolio-wide forever and the bot never
> trades again"* attributes to maximally-stale a halt that
> `COMMITTED_RISK_UNKNOWN` **already imposes on the identical set**. The chain
> is structural: unstamped implies `UNKNOWN` — `record_partial_reconciliation`
> is the only writer that leaves the stamp unset, and it is called only on the
> absence branch, which returns `UNKNOWN` — which implies untrusted, which
> implies uncomputable. So under `stop_loss.enabled` those positions were
> already refusing before this guard existed.
>
> What maximally-stale adds at `max_open_positions = 1` is a **better label**,
> not a new halt: the operator reads "the ledger is not current" instead of
> "committed risk is unknown", and the first names something they can act on.
> The one place it adds behaviour is a stop-DISABLED config, where the
> committed-risk gate is off — see item 14c.
>
> The reviewer wrote the overstated framing; it is corrected here rather than
> at its author.

### 14. The staleness refusal is now a HARD PRECONDITION of the first dispatch — `M5e-069`, `M5e-070`

**`ACTIVE` was admitted to `_TRUSTED_PROTECTION`, and that made an
unimplemented guarantee load-bearing.** MEASURED before writing this: the
discriminator in `Portfolio.committed_risk` reads membership in
`_TRUSTED_PROTECTION` and contains **no reference to `last_reconciled_at` or
to staleness**; and `max_position_staleness_s` appears exactly **once** in
`src/`, at its own field declaration in `config/models.py`. **It has no
reader.**

Before the admission that omission was invisible, because every
reconciler-written state was untrusted and a stale one and a fresh one both
counted uncomputable. After it, a position classified `ACTIVE` and never
re-read — a dropped feed, a budget-skipped pass, a pass that raised — **stays
trusted indefinitely** and is priced off a stop that may no longer rest. That
is the understate direction the whitelist's own comment names as the expensive
one, reached not by trusting the wrong state but by trusting the right state
for too long.

**So the staleness refusal joins the reconciler as a hard precondition of the
first dispatch.** The window between this commit and that one is safe for
exactly one reason — nothing constructs a `Position` in `src/`, so no position
can go stale — and **that reason expires at the executor**, which is the same
commit that would first supply a stale one.

*Arming condition, in caller terms:* **the executor**, as the first caller that
can produce a position capable of aging. Not implemented here, deliberately:
the refusal is a risk-layer decision with its own stage, its own reason string
and its own interaction with the reserved `None` ruling, and improvising it
inside a whitelist edit is how a guard lands without the reasoning that
justifies it. `test_membership_says_nothing_about_when_the_protection_was_verified`
in `tests/unit/test_risk_manager.py` characterises the gap, so closing it
inverts a test rather than passing silently.

> **THIS ARMING CONDITION FIRED AND NOTHING NOTICED — `M5e-090`.** The refusal
> it names landed at M5e's S1, three commits after this condition was written,
> **in the same milestone**. The item went on reading as though it were waiting
> for a component that had not been built, while the thing it was waiting for
> had already shipped.
>
> Nothing detected it. The arming-condition discipline has no mechanism that
> watches a condition for its own satisfaction; what found this one was a
> rotation reading every condition in the file in one pass, which happens once a
> milestone. That is the third and newest failure mode of arming conditions, and
> unlike the other two it is not a badly written condition — the condition was
> correct, and correct is not the same as observed. It is recorded as a rule in
> `CLAUDE.md` beside the caller-not-event rule.
>
> **What remains of item 14 is the escalation half only**, whose arming
> condition is the halt flag's first writer, stated below.

> **THE REFUSAL HALF HAS LANDED (S1). The driver's escalation half has not, and
> the reason is a conflict between two correct decisions.**
>
> `RefusalStage.POSITION_STALE` sits between `_mark_prices` and the
> committed-risk guard, reads `risk.max_position_staleness_s`, and treats
> `last_reconciled_at is None` as maximally stale. The clock is read **once**
> per evaluation, hoisted out of `_approve` and placed after the `CLOSE`
> dispatch so the exit path stays clock-free -- which also means staleness, the
> daily-loss roll and cooldown expiry now all measure against one instant
> rather than two readings that could straddle a boundary.
>
> **The escalation half stays deferred.** Q-B section 1 defines `CRITICAL` as a
> log line **and a halt flag on `Portfolio`**, and site 4 additionally requires
> a distinct marker with promotion to terminal after N reconciliation cycles.
> The halt flag does not exist. The N-cycle counter needs cross-pass state,
> which the driver commit **deliberately refused** to hold, on the grounds that
> a driver holding position state becomes a second source of truth for a fact
> the position already owns. **Those two decisions are each correct and they
> conflict**; naming that is the whole of what is recorded here, and resolving
> it is not attempted.
>
> *Arming condition, in caller terms:* **the halt flag's first writer.**

### 14b. CONSTRAINT ON THE EXECUTOR: construct positions `UNKNOWN` — `M5e-075`

**Ruled at S1: the executor writes `ProtectionState.UNKNOWN` when it constructs
a `Position`.** No position is trusted until the reconciler has seen its
protection resting at the venue.

**Grounds.** The error direction is a refusal rather than a mispriced stop: a
position wrongly marked `UNKNOWN` costs entries until the next pass corrects
it, while one wrongly marked `ACTIVE` is priced off a stop nobody confirmed.
And ruling this way **does not foreclose** stamping at construction later, if
`orderReports` is ever measured and shown to carry the compare set; ruling the
other way requires that measurement **first**, and obtaining it requires a
dispatch — see item 3.

It also collapses the reserved `None` question: under this constraint all three
readings of `last_reconciled_at is None` coincide in behaviour, because
unstamped implies `UNKNOWN` implies untrusted implies uncomputable. `None` is
treated as maximally stale, and that is now a **label** decision rather than a
behavioural one — everywhere except the stop-disabled case in item 14c.

*Arming condition, in caller terms:* **the executor**, as the only thing that
will ever construct a `Position`. Nothing enforces this today because nothing
constructs one; it is a constraint on a caller that does not exist yet, which
is exactly why it is written down rather than left to be inferred.

### 14c. The one behaviour change: staleness is UNGATED by `stop_loss.enabled` — `M5e-076`

`COMMITTED_RISK_UNKNOWN` is gated on `stop_loss.enabled`; the staleness guard
ahead of it is not, and **that is the only behaviour change in the commit.**

The opt-out that gate honours is about **committed risk** — the operator has
declared they own their exits via `SignalAction.CLOSE`. Staleness is about
whether `positions`, `position_count` and `has_position` describe reality, and
a `CLOSE`-owning operator still needs `has_position` correct or a `BUY`
pyramids onto a position that closed at the venue.

**The change is narrow, and its narrowness is the reason it is acceptable
rather than merely defensible.** Stops off implies *everything* off — a
take-profit or a trailing stop without a stop is refused at config load — so
such a position requests no protective levels, classifies `ABSENT_BY_DESIGN`,
and is **stamped on the first pass**. The guard therefore fires only once the
pass **stops running**: a dropped feed, a pass that raised, a budget-crowded
cycle. And an operator who has opted out of protective orders is the least
equipped to notice that unaided.

Pinned by `test_the_guard_is_not_gated_on_stop_loss_enabled`, which builds the
only stop-disabled configuration the config layer permits.

### 14a. The arming caveat on the admission itself — `M5e-071`

**"A production path assigns `ACTIVE`" is true; "a production run has assigned
`ACTIVE`" is not.** Six links were enumerated from `main.py`'s
`async with live_system(settings)` through `provider.on_candle(reconciler)`,
`_notify`, the driver, `classify_protection` and
`position.record_reconciliation(protection=assessment.state, at=now)` — every
one in `src/`, none reachable only from tests. But `Position` is constructed
nowhere in `src/`, so the chain runs over an empty list and no run has yet
produced the datum.

**Deferring on that is worse than proceeding, and the asymmetry is the reason
this is recorded rather than left as a doubt.** The run that would supply the
observation is *the executor's first position* — which would be classified
`ACTIVE`, count uncomputable while untrusted, and refuse every subsequent entry
portfolio-wide. So waiting buys one observation at the price of freezing the
portfolio at a single position, at the highest-risk moment in the project,
while the classifier's correctness is already pinned by tests that drive the
real function over the real compare set.

*Arming condition:* **none — this is a closed decision**, recorded so the gap
between "wired" and "exercised" is not rediscovered as a defect.

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

  **M5e's S1 added a third guard and one of each kind — `M5e-077`.**
  `POSITION_STALE` sits between `_mark_prices` and the committed-risk guard.
  Its pair with `COMMITTED_RISK_UNKNOWN` **is pinned**, by
  `test_staleness_refuses_ahead_of_committed_risk_unknown`, on an input the
  pass really produces: a position stamped at some point, later found to have
  an absent leg — `record_partial_reconciliation` writes `UNKNOWN` and leaves
  the existing stamp — and then aged past the bound. That was worth pinning
  precisely because the ordering is the ruling: staleness names the cause where
  committed-risk-unknown names the consequence.

  Its pair with `NO_MARK_PRICE` **is not pinned**, and joins the two above.
  `NO_MARK_PRICE` is deliberately first: "we cannot value your positions at
  all" is more fundamental than "the ledger is not current", and a stale
  position may also be unpriceable. Nothing asserts that order.

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
