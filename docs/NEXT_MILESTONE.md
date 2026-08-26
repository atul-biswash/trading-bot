# Next milestone — M5g

Written at M5f's rotation. This file is the **only task authority** the next
session has: anything not carried here is lost, and the rotation that rewrites
it is what destroys it. A rule living only in this file is one rewrite from
gone — the `phase_5_` shape, one step inside the repository.

---

## Before M5g starts — the namespace

**M5g's finding IDs are `M5g-001`, `M5g-002`, … — three digits, zero-padded,
per-milestone.** Not letters: M5d needed 90 identifiers and M5c exhausted a
26-letter namespace mid-milestone, so the two-character letter extension does
not apply here.

**M5f's namespace is CLOSED at `M5f-097`.** Its numbered commits ran
`M5f-001`–`M5f-084` with no gap and no duplicate, verified over
`milestone/M5e..HEAD`; rotation added `M5f-085` onward. Do not reuse an M5f
identifier, and do not file an M5g finding under `M5f-` because it concerns
M5f's subject matter — an ID names the entry a reader should open.

---

## THE CARRIED RISK — read this before anything else

**M5f built the executor and did NOT retire the composition risk.** It made it
larger.

The older prose said *"nothing constructs a `Position` in `src/`"* and drew
from that the conclusion that seven reconciler components had never run against
a real position. **The premise is now false** — `OrderExecutor._open_position`
constructs one. **The conclusion still holds, for a different reason: nothing
has RUN.**

Never exercised in series against a venue, and now more than seven:

| Component | Landed |
|---|---|
| `classify_protection` | M5e |
| `reconcile_open_positions` | M5e |
| `resolve_unresolved_legs` | M5e |
| `ReconciliationDriver` | M5e |
| the L-leg reservation | M5e |
| `ACTIVE`'s admission to `_TRUSTED_PROTECTION` | M5e |
| `RefusalStage.POSITION_STALE` | M5e |
| `build_placement` | M5f `3407b91` |
| `DispatchBudget` | M5f `cd7348a` |
| `resolve_placement` | M5f `3438180` |
| `OrderExecutor` dispatch, position construction, Option-4 resolution | M5f `8ca878e` |

**The first live position exercises all of them at once.** Each is pinned by
tests over fabricated inputs; **what nothing covers is their composition**, and
no test can retire that — a test that composed them would be testing fakes in
series, which is what already exists.

**This is the single most important fact about the tree's current state.** It
belongs at the top of any M5g scope discussion.

---

## What M5f left — the state of the tree

A run can now place an order. The chain is:

```
candle -> reconciler (subscriber 0)
       -> executor's Option-4 resolution (subscriber 1)
       -> engine's hook (registered in start())
            -> strategy -> RiskManager.evaluate
            -> IntentLogger.record
            -> OrderExecutor.dispatch
```

`OrderExecutor.dispatch` refuses `CLOSE` by name, refuses the unprotected
branch, refuses while a placement is pending, refuses on an exhausted budget
and refuses a client-side failure immediately. Otherwise it builds an OTOCO or
OTO request seeded from `candle.close_time`, marks a `PendingPlacement`, places
under per-call bounds, and on success records a `Position` at
`ProtectionState.UNKNOWN` and debits its cost.

**Nothing has run this.** No `main.py` invocation has dispatched anything.

---

## The project owner's outstanding rulings — ask precisely

Three rulings are made and implemented, recorded so they are not re-litigated:

1. **"Resolver lands in its own isolated commit."** — landed `3438180`.
2. **"Execute Question 4 (non-filling limit test) to establish venue write
   validity."** — executed 2026-08-21.
3. **"Fail-closed on UNRESOLVED states for Ruling 2."** — implemented
   `8ca878e`, annotated into `CLAUDE.md` at `107178f` and into Q-C §8 at
   `bdf12c4`.

**What he has NOT ruled** is the UNRULED list below. Each names the decision,
not the milestone, so the next session can ask one question rather than
re-deriving the option set.

---

## UNRULED — reserved to the project owner

### U1. `NOT_PLACED`: re-place, or drop? — `M5f-061`, `M5f-064`

`CLAUDE.md`'s locked rule says *"Not found ⇒ nothing rests; re-place at the
same generation."* The executor deletes the record and re-places nothing, so a
signal whose placement is reported not-found is dropped — logged at ERROR as
`dispatch_missed` since `b5cadea`, so it is countable, but gone.

**`NOT_PLACED` is an INFERENCE, not an observation**, and that is what makes
this hard. It covers at least three venue states: the request never arrived; it
arrived and was rejected at submission; or a list WAS created and is absent
from the enumeration. The executor cannot distinguish them.

**What narrows it, measured at M5f:** the enumeration discards its OLDEST
entries when saturated (`limit=3` returned the newest three), and the resolver
only ever asks about a list created on the current or previous bar. So the
third state is bounded by DIRECTION rather than by headroom — the window
discards from the end the resolver never reads.

**And strategies are edge-triggered**, so a dropped signal is not deferred, it
is gone: the strategy will not re-emit.

*Arming condition, in caller terms:* **whoever writes the first `CLOSE`
dispatch or the first live-run change to `OrderExecutor.__call__`.** It is not
armed by a milestone; it is armed by the next hand that edits that branch.

### U2. The venue-refusal half of e3-narrow — `M5f-083`

Client-side refusals now create no pending record (`59cf256`). Venue refusals
still do, and still spend a resolver call next bar rediscovering what the
exception already said. That half is deliberately unruled because it rests on
`CLAUDE.md`'s *"a 429 is rejected pre-acceptance"*, which is REASONING rather
than measurement.

**The measurement that would settle it:** a rate-limited placement, shown by
enumeration afterwards to have created no order list. Needs a venue write and a
rate limit, so it is not obtainable read-only.

*Arming condition, in caller terms:* **whoever next edits `dispatch`'s except
chain.**

### U3. Whether to consume `orderReports` — `M5f-038`

**The PREMISE is settled and the DECISION is not.** MEASURED 2026-08-21: the
placement response carries `orderReports` with Q-C §7's complete compare set —
`status`, `executedQty`, `origQty`, `price`, `origQuoteOrderQty`,
`timeInForce`, `type`, `side`, `expiryReason`, `workingTime` — at no extra
call.

**The cost of consuming it**, unchanged: `OrderList` would hold two leg
representations, or two types would exist for one concept, with the richer one
available from exactly one endpoint.

*Arming condition, in caller terms:* **the placement site in `OrderExecutor`**,
which is the only thing that holds a placement response.

### U4. The per-call share — `M5f-009`

The "three-call `CLOSE`" is false; measured worst cases are OTOCO **5**, OTO
**4**, unprotected **1**, recovery-bearing entry **3**. Whether the confirm step
queries all three legs or only the two protective ones decides 5 against 4, and
that is the owner's. Annotated at twelve sites by `7aa8f59` and once in
`M5_NUMBERS.md`, which states *"This one annotation covers every site in this
document"* — **do not annotate it again; a duplicate is permanent.**

*Arming condition, in caller terms:* **whoever first sets a value for
`timeout_s`/`attempts` from config** rather than passing the derived bounds.

### U5. `BinanceRequestException`'s representation — `M5f-072`

It carries **no code**, and MEASURED from the library it is raised only AFTER a
2xx, when the body will not parse. For a placement that means the venue
ACCEPTED and we cannot read what it said — it leans toward LANDED. `code=None`
therefore reads as "client-side" to anyone trusting the `:param` line, which is
wrong in the dangerous direction. Representing it needs a state `int | None`
cannot express.

*Arming condition, in caller terms:* **whoever first branches on
`ExchangeAPIError.code` in production.** Nothing does today — measured, the only
`.code` reader in `src/` is `_ApiRule.keys_on`, which reads a rule's key.

### U6. Whether `OrderExecutor` implements the `OrderExecutor` port

`core/interfaces.py` declares an `OrderExecutor` port taking an `OrderRequest`,
which describes one of three placement outcomes. The class does not implement
it. Left open at M5f deliberately.

*Arming condition, in caller terms:* **whoever needs to substitute the executor
 — the paper simulator, most likely.**

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Dead: one definition, zero readers. Its comment claims a consumer that does not
exist. **It now also anchors the `7aa8f59` annotation**, so removing it orphans
or deletes an annotation, which annotate-never-delete forbids. That makes the
deletion a precedent decision rather than a cleanup.

*Arming condition, in caller terms:* **whoever next edits `config/models.py`'s
coherence block.**

---

## UNMEASURED — and two of these are unreachable without a venue write

### M1. The `allOrderList` default page size — `M5f-066`, `M5f-068`

**UNREACHABLE READ-ONLY. Do not re-attempt a read-only probe for this.** The
account holds 14 lists; a `limit` above the default returns the same 14, so the
ceiling cannot be observed without exceeding it, which needs hundreds of
placements. Bounded below at >= 14.

**What IS measured, and it is the part that mattered:** the window discards its
OLDEST entries, so S3 is bounded by direction. That survives the page size
staying unmeasured.

### M2. Whether terminated lists count against `MAX_NUM_ORDER_LISTS`

**UNREACHABLE READ-ONLY. Two probes have now failed to reach it.** Measured:
`MAX_NUM_ORDER_LISTS = 20`; the account holds 14 lists, **all `ALL_DONE`**, and
0 not-`ALL_DONE`. If the ceiling counts live lists the headroom is 20; if it
counts every list ever created it is 6. Neither probe approached the boundary.

**Do not state a headroom figure.** `M5f-067` records a rotation stating "6 of
20" as fact, which silently answered this question in prose. The honest answer
is that it is open.

### M3. Q-C §8's fourth row — placed, working leg filled, pendings live

**REASONED, NOT MEASURED — needs a fill.** It is the row in which a re-place
opens a second unprotected entry, and it is the whole grounds for the
fail-closed ruling. Obtaining it requires an order that actually executes.

### M4. S5 — a filled list whose protection has since triggered — `M5f-037`

Terminal, reads `ALL_DONE`, and is indistinguishable by `get_all_order_lists`
from the FOK-expired case — so it maps to `PLACED_TERMINAL`, which asserts no
position was opened. Separating it needs a per-leg `executedQty`, which that
endpoint does not carry, so it costs a per-leg point query and reintroduces the
M5c-K ambiguity R13 routes around.

### M5. `PendingPlacement` is unpersisted — `M5f-087`

**The one failure fail-closed structurally cannot bound.** It is a plain
in-process dict. A process death between an ambiguous write and the next
candle-handler invocation loses the only record that a list may be resting, and
`reconcile_open_positions` iterates `portfolio.open_positions`, which has no
position for it. Every other orphan M5f closed is bounded by the record
surviving to the next bar; this one is bounded by the process surviving.

*Its likelihood is UNMEASURED.* Persisting it is a design decision and
`persistence/` is a stub.

---

## DEFERRED — known, decided not to act, each with why

- **`ExchangeAPIError`'s docstring enumerates "Two `src/` sites" and there are
  twenty** — `M5f-071`, `M5f-077`. Most of the eighteen are client-side and
  consistent with its spirit, which is why the error is invisible. A docstring
  count is its own subject.
- **`code == 0` is the library's sentinel for an unparseable non-2xx body** —
  `M5f-078`. MEASURED: `BinanceAPIException.__init__` sets `self.code = 0`
  before parsing. `418409f` now forwards it as though it were a venue code.
  Binance has no code 0, so it functions as a sentinel, and nothing in the tree
  records that.
- **`CLAUDE.md` says the mapping targets an order-list request for "three of
  the four branches"; the code and Q-C §2 both say TWO** — `M5f-020`. **Still
  uncorrected**: excluded from rotation 2/C by its own authorisation and 2/D
  was `docs/`-only. It needs a home.
- **`test_ids.py`'s comment gives a false rationale** — `M5f-073`. Its
  assertion is correct for its subject; the analogy to
  `BinanceRequestException` is false, because a venue DID answer there.
- **A stale claim propagated into a test docstring** — `M5f-030`.
- **`_REASON_UNPROTECTED` is emitted from two sites** — `M5f-053`. A
  redundancy, not a wrong signal: both sites genuinely are the unprotected
  branch. Closing it means deleting a defensive branch to make a test
  discriminate.
- **`_matched_list_id`'s multiplicity guard is pinned by nothing** —
  `M5f-063`. Found by predicting a zero. Not hypothetical — a census measured
  one id mapping to three lists — but unreachable today, since
  `resolve_placement` returns `PLACED_LIVE` only when exactly one match is
  live.
- **`install` and `install-dev` bypass `$(PYTHON)`** — `M5f-033`. Arguably
  worse than `cov`'s, because they *create* the environment mismatch.
- **`model_copy(update=...)` skips the model validator of every frozen domain
  type** — `M5f-002`. All four `src/` call sites are unexploitable because each
  re-checks more strictly. The mechanism is open and this tree's idiom walks
  into it.
- **A test passes for a different reason than its name states** — `M5f-088`.
  `test_the_portfolio_is_a_boot_snapshot` passed at M4a because nothing could
  mutate the portfolio; it passes now because the fake refuses the placement.

---

## Process debt with no instrument — carried, unchanged

- **A justification going stale because nothing at its site re-checks the fact
  it rests on** — `M5f-011`. Three instances.
- **A `src/` docstring outliving its fact** — `M5f-029`, `M5f-086`. **Eleven
  instances across two milestones.** Of how each was found: one by someone
  looking, two by reading adjacent code, one by a wrong mutation prediction,
  six by a rotation audit. **The only systematic finder is the rotation, once a
  milestone.**
- **A stale ENUMERATION is a distinct pattern and is NOT greppable** —
  `M5f-091`. A stale claim asserts something false and can be searched for; an
  enumeration STOPS EARLY and no phrase finds it. Instances: a boot-order list
  ending at step 10, a subscriber paragraph naming subscriber zero only, two
  architecture trees listing two files under `execution/` where there are
  seven, and a count of an enumeration that drifts twice over. **A rotation
  must READ every structural list against the tree.**
- **An open item declared in a commit message has no route into the task
  list** — `M5f-042`. Both of `CLAUDE.md`'s checks read commit messages and
  run the other direction. **This file is the route, and this rewrite is the
  only thing that exercises it.**
- **Nothing reconciles a mid-turn fix against a queued authorisation** —
  `M5f-056`. `M5e-090`'s mode 3 between turns rather than between milestones.
- **The rotation convention for milestone paragraphs is written nowhere** —
  `M5f-092`. Recovered by `git log -S`: rotation RE-TENSES and SCOPES the
  previous milestone's paragraph. One prior instance, `46da8ae`.
- **No vocabulary for a measurement that upgrades confidence without moving a
  number** — `M5f-097`.
- **A check in the same command chain as the action it gates is not a gate** —
  `M5f-094`. Distinct from the pipe rule: there the verdict cannot be read;
  here it was read, too late.

---

## Carried from earlier milestones — still open, unchanged

- **Finding I** — refuse a symbol whose tick is coarse relative to
  `max_entry_slippage`. `tick / price > max_entry_slippage`, against a live
  price, at BOOT rather than per-signal. *Arming condition, in caller terms:*
  `_prime_pairs`, which exists — the check is armed now and merely unreachable
  on BTCUSDT/ETHUSDT.
- **Finding L** — `Portfolio(realised_pnl=...)` with `pnl_date=None` makes
  `realised_today` return zero, so a booked loss reads as zero. Permissive
  direction.
- **Collapse the multi-statement writes** — `advance_trailing_stop` and
  `record_realised_pnl` each write twice, and `CLAUDE.md` makes collapsing them
  a prerequisite for any `Position` model validator.
- **The trailing milestone** — `advance_trailing_stop` has zero call sites in
  `src/` and is `trailing_stop`'s only writer. The blocking question is
  unchanged: *does the trailing level rest at the venue, or does it not exist?*
- **Q-C §7's site-3 defect** — deferred at M5d; needs a `ProtectionState`
  member no writer exists for.
- **Q-B site 4's escalation half** — `M5f-096`. **BLOCKED, not stale.**
  `CRITICAL` needs a halt flag on `Portfolio` that does not exist, and N-cycle
  promotion needs cross-pass state the driver refused to hold. Both decisions
  are correct and they conflict. *Arming condition, in caller terms:* the halt
  flag's first writer.
- **`max_position_staleness_s`, `reconcile_deadline_s`,
  `dispatch_deadline_s`** and the other PLACEHOLDER numbers in
  `M5_NUMBERS.md` — every mark stands. M5f's placement timings changed no
  number.

---

## M5g — a PROPOSAL, not a decision

**The reviewer proposes, the project owner sets scope.** What the tree argues
for, and what is genuinely uncertain:

**The strongest candidate is a first live run on Testnet** — because the
carried risk above cannot be reduced any other way. Every component is pinned
in isolation and their composition is covered by nothing, and that gap widens
with each milestone that adds a component without running them together. A
single supervised run against Testnet, on a pair configured to produce a
signal, would exercise the whole chain once.

**What makes that a venue-write decision and therefore his:** it dispatches a
real order under the bot's own control, rather than under a probe's five
structural guards. It is a different act from every probe M5f ran.

**The obvious alternative is `SignalAction.CLOSE`** — the executor refuses it
by name today, so a strategy that owns its exits cannot exit. Q-C §4b specifies
the close path and it is unbuilt. This is more code and less risk than a live
run, and it does not reduce the carried risk at all.

**What I am unsure of, stated rather than resolved:**

- Whether a first live run should precede `CLOSE`. Running before `CLOSE`
  exists means a position that opens cannot be closed by the bot — only by
  hand at the venue. That may be acceptable for a single supervised run, or
  disqualifying; I do not know which he considers it.
- Whether U1 must be ruled before any live run. A dropped trade is visible now
  (`dispatch_missed` at ERROR), so the answer may be that it can wait.
- Whether M3's fill measurement should be sought deliberately — a small
  marketable order placed to fill — or waited for. It is the last unmeasured
  row in the re-place table and the grounds for a ruling already made.

---

## Where M5e's item numbers went — four test docstrings cite them

**This rewrite renumbered the queue, and four citations in `tests/` name the
old numbers.** `M5f-044` predicted exactly this: the items may not be
renumbered, nothing enforces it, and **a renumbering breaks no test and fails
no gate** — the citations are prose, so they rot silently. Rotation had to
renumber anyway, because carrying M5e's scheme forward would mean holes where
items discharged and numbers designed for a different queue.

So the mapping is written here instead, which is the cheapest thing that keeps
the citations followable:

| Cited as | Where it is now |
|---|---|
| `test_binance_client.py` — *"item 9"*, the `get_symbol_info` cache assertion | **DISCHARGED** at `cc1feb5`. The refusal exists; `_cached_symbol_info` reads the cache and raises `SymbolInfoNotPrimedError` rather than fetching. No open item remains. |
| `test_reconciliation_pass.py` — *"item 13"*, what the last-call reservation costs | Carried above as part of the reconciler's carried risk; the reservation itself is unchanged and still reserves what the first unresolved position needs. |
| `test_risk_manager.py` — *"item 14"*, the staleness refusal | The REFUSAL half landed at M5e (`RefusalStage.POSITION_STALE`). The ESCALATION half is carried above under Q-B site 4, **BLOCKED** on the halt flag. |
| `test_risk_manager.py` — *"P2"*, no method on the widened port may go uncalled | Honoured at M5f: `get_all_order_lists` landed with `resolve_placement` (`3438180`) and the two placement methods with the executor (`8ca878e`). Finding GG's rule, unchanged. |

**The lesson is the mechanism, not the mapping.** A citation by POSITION — a
line number, an item number — into a document that is rewritten or annotated on
a schedule is a pointer with no owner. `CLAUDE.md` already rules that a
document is cited by CONTENT for exactly this reason. **A test docstring citing
an item number is the same defect one layer out**, and the fix is for the
citation to quote what it relies on rather than where it sits.

---

## The rotation's own procedure — read `CLAUDE.md`, not this

`CLAUDE.md` holds the rotation steps and the extraction commands. Two things
that bit M5f and are worth knowing before the next one:

- **The extraction's base is the `milestone/<name>` TAG**, not a SHA from a
  commit table. `milestone/M5d` and `milestone/M5e` are both on origin;
  `milestone/M5f` must be pushed separately, since `git push` does not carry
  tags.
- **Run the extraction BEFORE writing the `PHASE_HISTORY` entry** — once the
  entry's table lands, the base moves and the blocks fall out of range.
