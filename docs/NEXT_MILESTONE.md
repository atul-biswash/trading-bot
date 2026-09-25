# Next milestone — M5k

Written at M5j's rotation. **This is the single home for live open items.**
Every item below was verified present in the tree at `4e30a25`; anything M5j
closed has been struck rather than carried, and the strikes are listed so the
removal is auditable rather than silent.

---

## Before M5k starts — the namespace

**IDs are `M5k-NNN`: three digits, zero-padded, starting at `M5k-001`.** Not
letters. `CLAUDE.md` still describes an `M5d-A` scheme it has never used and
carries an annotation saying so; the digit convention is the real one and this
line is the only place it is prescribed, which is exactly the `phase_5_` shape
one step inside the repository. **A rotation that rewrites this file must carry
this paragraph forward.**

M5j allocated **50** ids, `M5j-001` through `M5j-050`, contiguous with no gaps
and no duplicates, and every commit in the range carries a findings block.
Verified at rotation by the documented extractor. The `M5k` namespace was
confirmed empty by the same extractor before this file was written, so
`M5k-001` is free.

> **THE M5i RESERVED BLOCK IS STILL RESERVED.** `M5i-068`, `M5i-071` and
> `M5i-073` are cited in the tree and declared nowhere. That is deliberate and
> the extractors report it every time as `cited-not-declared`; it is not a
> defect to be closed by inventing declarations for them.

---

## THE CENTRAL FACT — read this before anything else

**The bot has been running, and for three milestones nothing in the repository
was pointed at the evidence.** M5j began by testing M5i's closing sentence —
*"nothing has run"* — and it was false. `docs/RUN_LEDGER.md` now holds the
census, with the command behind each figure and the digest of the capture it
came from.

**What that changes for M5k is the standard of evidence, not the backlog.** A
claim derived from a capture names its digest in the sentence that makes it, or
it cannot age visibly — a sentence written three days before its own
falsification said *"still true"* and named no bytes.

**A run was in flight while this rotation was written.** `pid=24772` was still
appending, position active, and the process predates the commit that added the
clean-shutdown marker — so `event=engine_stopped` reads zero and will until the
next restart. That is the marker's absence recording the process's age rather
than an unexercised path.

---

## M5k's PRIORITIES, IN THE OWNER'S RULED ORDER

### 1. The DIVERGED exit-booking gap — A5, `M5j-011`

**The highest-value item and the one with the most design left in it.**
`_book_exits` treats a `None` `ExitFill` as row 4, the ordinary healthy pass,
and `continue`s silently. A pass whose only terminal leg is `DIVERGED` therefore
books nothing, keeps a `Position` describing base the account may no longer
hold, and refuses entries portfolio-wide with nothing stating why the ledger and
the account have parted.

**A5 at the precision this rotation reached, and the two halves must not be read
as one observation.** The **per-leg** `DIVERGED` branch HAS run: on 2026-09-18
the `SL` leg reported `EXPIRED` and took it. **Position-level `DIVERGED` remains
UNOBSERVED in production.** Re-derived against the capture whose SHA-256 is
`bfc8ffddc494f288e710df00918507c7027bcfe538096def4d32172ed2af8d3d`, every
`states=` value the reconciler has ever reported:

| `states=` | count |
|---|---:|
| `active=1` | 2849 |
| `active=2` | 1261 |
| `unknown=1` | 160 |
| `diverged=1` | **28** |
| `active=1,unknown=1` | 3 |

**All 28 `diverged=1` records fall between `2026-08-27 04:07:02` and
`04:38:02`; the identifier-space fix `3970968` is authored `05:47:28Z` the same
day; zero follow it.** On 2026-09-18 the position-level assessment was
`unknown=1`, because the sibling `TP` leg reported a fill and that branch returns
first.

**What it forecloses.** Row 4 carries two meanings today — *no leg reported a
fill* and *a leg is terminal and unpriced* — and `ExitFill`'s own docstring makes
that separation load-bearing. Booking from a `DIVERGED` leg would need a price
the venue never gave, which is the `NO_QUOTE_TOTAL` path, so the honest options
are **escalate** or **refuse loudly**, not book.

> **ANNOTATED BY 3b-2b: the `NO_QUOTE_TOTAL` path now BOOKS**, from the sum of
> the order's own fills (the 3b ruling), so it is no longer an example of not
> booking. The conclusion stands on its own ground: a `DIVERGED` leg reported
> no fill, so it has no fills to sum.

### 2. A gate-count self-verification helper

The 18 count sites are maintained by hand across two files and nothing checks
them against a gate run. **It would be its own first customer**: one new
`scripts/` module and its test move `ruff format` by two and `mypy` by one.

**What it forecloses.** It can verify the sites agree with a run; it cannot
distinguish a count site from a coincidental digit. Four hits in `CLAUDE.md` are
not gate figures — a coincidental `118` in grep prose, a `+74.11` money bound, a
`118` explicitly marked not-a-gate-figure, and a Q-C `:118` line citation — and
a helper treating every digit as a site would demand edits to all four. The
inverse rule stays human judgement.

### 3. Regularising the arming conditions

Partly done at this rotation; see the note under **Arming conditions** below.
**Two conditions are left unparsed deliberately** and closing them needs a
ruling rather than an edit.

### 4. The accounting architecture pass

The largest, and it **unblocks** the others rather than the reverse — A1, A4's
rename and the true fill time all wait on it. It touches
`exchange/models.py`, `core/models.py`, `execution/reconciliation.py` and
`core/interfaces.py`, **two of which are the port**. The denomination invariant
and the two-of-three rejection are locked in `CLAUDE.md` and bind whoever does
it.

---

## Arming conditions — regularised, with two deliberate exceptions

`scripts/check_arming_conditions.py` keeps a parsed and an unparsed register and
**exits non-zero while the unparsed register is non-empty**. At this rotation's
start it read 22 candidates, 15 parsed and 7 unparsed, every failure for the
same reason: the bold span named no backticked symbol.

**Six were regularised by naming the site they actually guard**, leaving 22
candidates, **21 parsed and 1 unparsed**. Their targets were derived from the
tree rather than invented: the two persistence closures are `_persist_pending`
and `_persist_ledger` in `engine/modes.py`; the classifier branch is `_refine`
in `execution/reconciliation.py`; the executor's substitutes are
`paper/simulator.py` and `backtesting/engine.py`; the unobserved-surface table
is produced by `scripts/run_census.py`; and the two conditions reading *"whoever
next edits that test"* name tests the surrounding prose already identifies, so
the real node ids are used.

**ONE IS LEFT UNPARSED ON PURPOSE, AND THAT IS THE CORRECT OUTCOME.** The
trailing-stop block guards Q-C §3's leg set — a **contract document section**,
not a Python symbol. The honest target is `docs/QC_PROTECTIVE_ORDERS.md` §3,
and backticking that path *would* satisfy the parser; it is left as it stands by
ruling, because writing a path in to please a tool is writing for the tool.

**So a non-zero exit is expected and is not a defect to regularise around.** The
checker is reporting that one condition guards something its schema cannot
express — which is the register doing its job. Widening the parser to accept a
caller-phrase with no symbol is the alternative, and it is the owner's call.

---

## UNRULED — reserved to the project owner

### U8. The harness: refuse, or report? — `M5i-096`

`scripts/mutation_survey.py` prints `target is tracked and clean` or `target has
uncommitted edits` and **proceeds either way**. `describe_vcs_state` computes the
fact; nothing acts on it.

**A dirty target is the NORMAL case and that is why it is advisory.** Surveying
the committed version would measure the *previous* commit, which is not the
thing under review. A harness that refused here would have refused every survey
M5i actually ran.

**What makes it a question rather than a settled no:** `M5i-084`'s rule is
satisfied by the out-of-tree snapshot, which exists whatever git says, so
refusal would buy nothing the snapshot does not already provide. The argument
for refusing is different — that a survey against uncommitted work has no
recoverable baseline in the repository if the snapshot is also lost.

*Arming condition:* **whoever next changes `describe_vcs_state` or the block in
`main` that prints its result.** Refusal is one `if` at that call site and the
fact is already computed.

### U0. `_persist_ledger`'s `pending=persisted.pending` — carried, untouched

Unchanged from M5h. M5j touched no persistence code at all, so this condition
did not fire.

*Arming condition:* **whoever next changes what `_persist_pending` or
`_persist_ledger` writes in `engine/modes.py`.** A docstring correction is not
that.

### U1. `NOT_PLACED`: re-place, or drop? — `M5f-061`, `M5f-064`

Carried, unfired.

*Arming condition:* **whoever writes the first live-run change to
`resolve_placement`'s verdict handling.**

### U2. The venue-refusal half of e3-narrow — `M5f-083`

Carried, unfired. M5j edited no `except` chain.

*Arming condition:* **whoever next edits `dispatch`'s except chain** — not
`_sell_and_book`'s, which is a different chain the item excludes in its own
words.

### U3. Whether to consume `orderReports` — `M5f-038`

Carried, unfired.

*Arming condition:* **the placement site in `OrderExecutor`.**

### U4. The per-call share — `M5f-009`

Carried, unfired.

*Arming condition:* **whoever first sets `timeout_s`/`attempts` from config.**

### U5. `BinanceRequestException`'s representation — `M5f-072`, `M5h-360`

Carried, unfired.

### U6. Whether `OrderExecutor` implements the `OrderExecutor` port

Carried, unfired.

*Arming condition:* **whoever writes `paper/simulator.py` or
`backtesting/engine.py`** — the two substitutes for the executor, neither of
which exists beyond a docstring stub.

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Carried, unfired. M5j did not touch `config/models.py` at all.

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

---

## CARRIED FROM M5j

### A1. Commission never reaches the ledger, and the gap is at the port

**The wiring inside `core/portfolio.py` is COMPLETE**, on both limbs — `fee` is
declared and consumed on four lines, two per limb. **The defect is that no
commission figure ever arrives to pass.** `commission` occurs zero times in
`src/`; `commissionAsset` zero times anywhere. `to_order` in
`exchange/models.py` reads sixteen distinct wire keys and `fills` is not among
them, so the venue's own fee report is discarded at the mapper.

**The three call sites are not alike**: `_book_close` holds the whole `Order`,
`_book_resolved_close` holds only a total, and `_book_exits` holds an
`ExitFill`. **Site three reads `get_order` point queries, whose responses carry
no fills array**, so it needs `myTrades` — a **new port method**, not a wider
one.

**Three rulings are locked in `CLAUDE.md`**: the denomination invariant, the
rejection of the two-of-three fix on ledger-comparability grounds, and the
prohibition on `fee=Decimal(0)` as an interim stub.

> **ANNOTATED PER `M5k-094`: THE HEADING IS HALF STALE.** Since `651d334`,
> whose subject begins `feat(accounting): exits book net of the venue's own
> fee`, every EXIT's commission reaches the ledger: all three booking sites
> call `close_position(..., fee=settlement.fee)` on the fills `get_my_trades`
> returns -- the new port method this item names as the remedy. **What
> survives:** ENTRY commission still never reaches the ledger, by the project
> owner's ruling R-a, and `to_order` still discards the venue's `fills`
> report; the ledger is net of exit fees and gross of entry fees. **The
> condition below watches `to_order` alone**, and the exit half was
> discharged by a route it does not name, so it never fired. `193a5b9`, the
> first commit to edit `to_order`, REAFFIRMED it.

*Arming condition:* **whoever next edits `to_order` in `exchange/models.py`** —
the single site where the venue's commission is discarded, and the first site
any fee must cross.

### A2. A manual action and a venue-triggered fill are indistinguishable

A leg `CANCELED` with `filled_quantity == 0` fails the fill branch, fails the
is-open branch, and falls to `ProtectionState.DIVERGED` with `ExitFill` `None`.
The two facts *a protective leg was cancelled by someone else* and *a protective
leg diverged* present identically, because the only fields the classifier reads
are status and executed quantity.

*Arming condition:* **whoever next edits `_refine` in
`execution/reconciliation.py`**, the per-leg branch that reads a leg's terminal
status, or whoever adds the first non-bot writer to a live account.

### A3. Two build-log headlines carry a claim their own annotation corrects

**Reserved to the project owner. No edit is proposed.** The M5h and M5i entries
in `docs/PHASE_HISTORY.md` each open on a claim the same entry annotates as
false much further down, so a reader of either intro alone gets the false
version. **A second annotation is not the remedy** — `CLAUDE.md` states that a
duplicate annotation is permanent — and the plausible alternatives each cost
something a build log protects.

*Arming condition:* **whoever next appends a milestone entry to
`docs/PHASE_HISTORY.md`** — the rotation's step 1 author, who is the first
caller that must decide whether a new entry's headline may state a claim the
entry will later annotate.

### A4. `venue_time` on an `exit_booked` line is the leg's CREATION time

`_exit_fill` assigns `venue_time=order.created_at`, and `to_order` derives that
as `_first_ms(raw, "transactTime", "time", "updateTime")`. It is **neither a
client-side clock nor the matching-engine execution time**, which lives in
`myTrades.time` and does not cross this port.

**The falsifying arithmetic needs no appeal to the code.** A booking line
carried `venue_time=2026-09-18T13:29:00.594000+00:00` while the placement line
for the same order list is stamped `13:29:02Z` — the value precedes the
placement by 1.4 seconds, and a fill cannot precede the placement that created
the order. A second instance: the 2026-09-15 booking at `23:39:02Z` carries
`venue_time=22:40:00.521Z`, 59 minutes earlier.

**The field is persisted**, so any holding period, detection latency or
fill-time ordering computed from it is wrong by the position's whole lifetime.
**The doctrine is locked in `CLAUDE.md`; the rename and the true fill time are
scoped to priority 4.**

*Arming condition:* **whoever next reads `ExitFill.venue_time` for anything
other than display.**

> **RESOLVED BY THE FEE COMMIT.** The condition fired and is discharged: the
> field is renamed `ExitFill.order_created_at`, the true fill time is
> fetched from `myTrades` and logged as `filled_at` on every booking line,
> and the `venue_time` key is gone from `exit_booked`. **"Persisted" is
> aligned** with the project owner's ruling: it meant durable execution
> logging, never `data/state.json`, where the field never was.
>
> **The rename itself landed one commit earlier**, in the preparatory commit
> whose subject begins `feat(exchange): fetch fills by order id`, which fired
> this condition and REAFFIRMED it rather than resolving it. What only the
> fee commit supplies is `filled_at` -- the latest `myTrades.time` among the
> exit order's fills -- so the fee commit is the one that resolves A4.

### A5. `M5j-011`'s DIVERGED branch RAN — OBSERVED-ADJACENT, not observed

See priority 1 above for the measured distribution. The branch was exercised and
**the hazard did not fire**: booking survived only because the sibling `TP` leg
took the fill branch and carried an `ExitFill`. **A sibling is not a mechanism.**

*Arming condition:* **whoever next edits `_book_exits` in
`execution/reconciliation_driver.py` or `_refine` in
`execution/reconciliation.py`** — the two callers that would have to agree on
what an absent `ExitFill` means.

### A6. Two adjacent lines read as a booking overriding a refusal — NOT a control defect

A warning and a booking landed one second apart on 2026-09-18. Derived from the
code they are **two calls, not one decision path**: `ReconciliationDriver.__call__`
calls `_report` and then, separately, `_book_exits`, with no value passing
between them. The warning refuses to *interpret the protection state*;
`classify_bookability` reads four facts in the order `A > Q > P > C` and **none
is a fill price**. **The remedy is wording, not control flow.**

*Arming condition:* **whoever next edits `_report`'s warning text or
`_book_exits`'s booking line.**

> **ANNOTATED BY 3b-2a: `classify_bookability` now reads `A > P > C > Q`**, by
> the project owner's Decision 1; Q still refuses until 3b-2b. This item's
> point is unchanged -- none of the four facts is a fill price -- and the
> condition above is REAFFIRMED: `_report`'s warning text and `_book_exits`'s
> booking line are untouched.

---

## OPENED BY THE FEE COMMIT

### F1. HIGH -- the driver retries a permanent fee refusal on every pass

**The reconciliation driver retries a non-Incomplete `FeeUnresolvableError`
on every due pass, with no bound and no terminal outcome.** `_settle` in
`execution/reconciliation_driver.py` catches it around `settle_exit`, logs
`exit_book_refused` at WARNING and skips. The position survives with
untrusted protection, so `COMMITTED_RISK_UNKNOWN` keeps entries refused
PORTFOLIO-WIDE for as long as the position lives, and the next due pass
fetches the same fills and refuses again. The condition cannot cure itself:
it is a fee in an asset this ledger cannot subtract, or a fill that is not a
sell.

**The executor drops the same condition at CRITICAL after one bar.** The sell
site defers it like every settlement failure, and on the next bar
`_resolve_close` takes its `fee_unresolvable` branch and drops the position
unbooked. Two sites, two outcomes, one fact. **It needs one ruled terminal
outcome for both sites.**

REASONED from the code. Pinned for ONE pass only, by
`test_a_settlement_the_ledger_refuses_skips_and_keeps_the_position[foreign_fee]`;
no test drives the repetition.

*Arming condition:* **whoever next edits `_settle` in
`execution/reconciliation_driver.py` or the `fee_unresolvable` branch of
`_resolve_close`.**

> **RESOLVED BY THE CLOSING COMMIT (2), by the project owner's ruling R2 with
> rulings A and B.** One terminal outcome at both sites: a non-Incomplete
> `FeeUnresolvableError` -- a fee in an asset this ledger cannot subtract, or
> a fill that is not a sell, now the subclasses `FeeAssetUnresolvableError`
> and `NonSellFillError` -- is fetched ONCE, logged ONCE at CRITICAL as
> `exit_settlement_held`, and HELD: the position is kept, its protection
> written `UNKNOWN`, and marked `Position.settlement_hold`, in memory. The
> driver no longer reconciles a held position at all (ruling A), so there is
> no second fetch and no repeating refusal; the executor keeps its close
> record and skips it before any venue call, and the retention count leaves
> it. A `CLOSE` for a held position is refused (ruling B). The
> `fee_unresolvable` drop and its text are gone, and the one-pass pin named
> above, `...[foreign_fee]`, is replaced by
> `test_an_unbookable_settlement_is_held_after_one_fetch`, which drives the
> second pass. Entries stay refused portfolio-wide throughout, as
> `COMMITTED_RISK_UNKNOWN` and then `POSITION_STALE`. **What did NOT change:**
> a restart releases the hold, because positions are not persisted, and the
> outcome then converges on the unbooked drop -- the trade is in the ledger
> only if an operator entered it by hand.

### F2. A restart after a deferred settlement -- UNMEASURED until the tests-only commit

A close whose settlement is deferred keeps its pending record, and the store
persists it as a `PendingCloseRecord`: `kind`, `symbol`, `entry_bar_time`,
`generation` and `quantity`. It carries no deferral count and no settlement,
because the retention tracker is in-memory by ruling. After a restart there
is no `Position`, so the resolution is predicted to classify the fill
`POSITION_ABSENT` and drop the record unbooked at CRITICAL with the released
text, making no settlement fetch and leaving the tracker empty -- provided
another pair is tradeable, since a config whose every pair is excluded is
refused at boot before the first candle.

**That prediction is REASONED.** The nearest test,
`test_no_position_in_memory_drops_unbooked_and_leaves_the_ledger_absent`,
seeds `_pending` on a fresh executor. Nothing drives defer, persist through
the real store, restore through a fresh root and resolve. **UNMEASURED until
the tests-only commit that follows the fee commit.**

*Arming condition:* **whoever next edits the restart branch of
`_resolve_close` or the store's `PendingCloseRecord`.**

---

## CARRIED FROM M5i

### `M5i-065`. The orphan guard raises silently

`reconciliation_driver`'s orphan guard raises and nothing reports it. Pinned to
the project owner at M5i and untouched since.

*Arming condition:* **whoever next edits the orphan guard or its caller in
`_book_exits`.**

### `M5i-095`. Two tests reach the mutated point and assert only portfolio state

A survey predicted 9 kills and observed 6. The three that did not fire assert
`ledger is None`, `free_quote` and a record count — **identical whether booking
never ran or ran and failed**, because the write raises before it commits.

*Arming condition:* **whoever next writes a test asserting over `Portfolio`
state to distinguish two booking outcomes.** The state cannot separate them;
only the label can.

### `M5i-104`. An unguarded unpack turns a kill into a crash

`test_a_partial_fill_with_no_cost_basis_still_goes_naked` does
`(naked,) = _records(...)` with no prior non-emptiness assertion, so a mutation
removing that record fails it at `ValueError` rather than at an assertion.
**A 12-site sweep of the same pattern is deferred.**

*Arming condition:* **whoever next edits
`test_a_partial_fill_with_no_cost_basis_still_goes_naked`, or runs a survey
whose predicted killers include it.**

> **RESOLVED FOR THE NAMED TEST BY 3b-2b; THE SWEEP STAYS DEFERRED.** The
> condition fired both ways: the test was edited, and 3b-2b's ordering survey
> predicted it among its killers. Its unpack is now a length assertion
> followed by indexing, and under the four orderings that put C ahead of P it
> failed as `AssertionError` -- a kill, MEASURED. The 12-site sweep is untouched.

### `M5i-126`. A substring assertion pins wherever its anchor occurs

`test_the_refusal_names_the_cause_the_remedy_and_the_opt_out` asserts three
substrings against a whole refusal message, and **all three are satisfied by the
opening paragraph alone**. A mutation replacing the entire remedy block killed
nothing.

*Arming condition:* **whoever next edits `_UNREAD_OUTPUT` or that test.**

### The `_go_naked` family's fourth candidate

`_go_naked`'s message says the position is *"UNPROTECTED and still open"*. That
is false at the abandoned-after-cancel caller under `ALREADY_CLOSED`, where the
venue closed the position for us. Three members of this family have already been
split off for exactly this reason (`_go_naked_retaining`, `_sold_unbooked`,
`_sold_unpriced`); this would be the fourth.

> **ANNOTATED BY 3b-2: `_sold_unpriced` IS REMOVED, by the project owner's
> Decision 2** -- *"Deprecate and remove `_sold_unpriced`."* The family has two
> split-off members, not three, and a fourth would be the third. Its branch's
> inputs now go elsewhere: a partial fill to `_go_naked`, whose "still open" is
> TRUE there; a cost-basis-less one to `_sold_unbooked`; an unpriced whole fill
> to the fetch, then booking, a hold or the deferral. The false sentence this
> item names is untouched.

**THE FALSE SENTENCE HAS NOT BEEN EMITTED — MEASURED.** Three instruments agree
at zero: the rendered text `UNPROTECTED`, the structured field
`event=close_naked`, and `event=close_abandoned`, the branch that reaches it
under `ALREADY_CLOSED`.

**That is a statement about the past, not a clearance.** The branch remains
unexercised and the message remains wrong at that caller. A path that has not
run is not a path shown to be correct.

*Arming condition:* **whoever next edits the abandoned-after-cancel branch in
`_execute_close`**, which is the only caller that can reach it.

### `M5i-109`. Two stale sentences in A1's docstring

`test_a_complete_fill_the_venue_never_priced_reaches_the_naked_guard` names its
sibling as `..._is_reported_as_partial_today`, which was renamed, and says *"the
three tail exits"* where there are now four.

*Arming condition:* **whoever next edits
`test_a_complete_fill_the_venue_never_priced_reaches_the_naked_guard`.**

> **RESOLVED BY 3b-2b.** The condition fired and is discharged: the test is
> rewritten as
> `test_a_complete_fill_the_venue_never_priced_books_from_its_fills_after_the_requery`,
> because the `_sold_unpriced` branch it pinned was removed by the project
> owner's Decision 2, and both stale sentences went with the old docstring.

---

## DECLARED TEST WEAKNESSES — known, and none is a defect

### W1. Two mutations, one failure set — `M5h-356`, `M5h-370`

Standing. `M5i-095` is a further instance.

### W2. A guard conditional on a neighbouring number — `M5h-357`

Standing.

### W3. A test that pins the numbers, not the behaviour — `M5h-354`

Standing.

### W4. An end-state assertion cannot see *when* — `M5h-366`

Standing.

### W6. Format strings in `executor.py` — `M5i-015`

**The number moved and the weakness did not.** `getMessage()` assertions in
`test_executor.py` went from **0** before M5i commit 1 to **7**. The `_log.*`
call sites that serve one outcome each remain unpinned by construction.

**Why that is not reassurance:** a message is safe while its call site serves
ONE outcome, and nothing enforces that property.

---

## UNMEASURED — venue facts nothing in the tree can supply

**Provenance: re-derived at M5j's rotation from a frozen capture whose SHA-256
is `bfc8ffddc494f288e710df00918507c7027bcfe538096def4d32172ed2af8d3d`** —
4,252,169 bytes, 22,127 lines, of which every earlier capture in this milestone
is a byte-exact prefix. The digest is named here because these figures move
whenever the bot runs, and three of them moved inside M5j alone.

### X1. A take-profit HAS filled — OBSERVED, and STRUCK at `3ea87d8`

**Closed by M5j.** Observed 2026-09-18: **1** clause naming a filled `TP` leg
against **162** naming a filled `SL` leg, the `SL` figure re-measured and
unmoved. BTCUSDT, `order_list_id=171948`, booked at `15:21:02Z` for
`realised=63.0300952000` **GROSS** — `fee` was `Decimal(0)`, per A1. Detection
took **119 seconds**, from the last pass reporting `active` to the pass that
found the fill.

### X2a. `ALREADY_CLOSED` — OBSERVED, and STRUCK at `0992fa3`

**Closed by M5j.** `decision=already_closed`, `2026-09-15T23:38:02Z`,
`pid=26952`, BTCUSDT. It read as unobserved for two milestones because the
search matched the enum's member name where the log carries its `.value`.

### X2b. `HALT` has never occurred — zero across 75 close plans

**CARRIED, and the sole remaining unobserved venue fact.** Re-measured against
the capture named above: `decision=halt` is **zero**, and the denominator
reconciles as `decision=sell` 74 plus `decision=already_closed` 1. **The
denominator moved three times inside one milestone** — 65, then 69, then 75 —
which is why it is quoted with its capture rather than bare.

### X3. `resolve_placement` has never run — STRUCK at `0992fa3`

**Closed by M5j.** Falsified by the event pair `placement_ambiguous` at
`2026-08-27 04:06:02` followed by `placement_resolved outcome=placed_live` at
`04:07:02`. Order list `255471` is named inside the resolution's reason and is
an **artefact** of the falsification rather than its instrument.

### The unobserved surface is far larger than these items

X2b is the one remaining unobserved **venue fact**. It is **not** the remaining
unobserved branch.

| Figure | Value | Instrument |
|---|---|---|
| order lists placed | **94** | `grep -c 'event=order_placed'` |
| complete exits | **73** (66 `close_booked` + 7 `exit_booked`) | `grep -c` on each |
| close plans | **75** | `grep -c 'event=close_planned'` |
| `decision=halt` | **0** | `grep -c 'decision=halt'` |
| clauses naming a filled leg `TP` | **1** | both classifier forms |
| clauses naming a filled leg `SL` | **162** | the same pattern for `SL` |
| log events DEFINED in `src/` | **34** | `_EVENT_*` constants, `_WS_EVENT_*` excluded |
| of those, absent from the capture | **18** | per-constant `grep -c`, zero |
| of those, NEVER emitted by an exercised path | **17** | the 18 above, less `engine_stopped` |
| `RefusalStage` members defined | **14** | the enum body |
| of those, unobserved | **9** | per-member `grep -c`, zero |

**`engine_stopped` is absent because the capture predates it, not because a path
went unexercised** — the running process booted before the commit that added the
marker. Both rows are printed because the instrument read the right property at
the wrong instant, which is the failure `CLAUDE.md`'s instrument-time rule names.

**The websocket constants are excluded deliberately.** `_WS_EVENT_TYPE`,
`_WS_EVENT_KLINE` and `_WS_EVENT_ERROR` in `exchange/websocket_client.py` match
a pattern looking for `_EVENT_` but are wire-protocol keys of Binance's stream
payload, not log events.

*Arming condition:* **whoever next runs `scripts/run_census.py` against a newer
capture**, which is the tool that produces every figure in this table.

---

## THE GATE BASELINE

Measured by this rotation's own run, on this credentialed machine:

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  122 files already formatted
mypy                                   Success: no issues found in 76 source files
pytest                                 1661 passed, 1 skipped
```

**`1661 passed, 1 skipped` is MEASURED.** `1658 passed, 4 skipped` is **DERIVED**
— that run minus the three `skipif(not HAS_CREDENTIALS)` integration tests,
which move from the passed column to the skipped one. It has not been observed
on this machine and must not be quoted as though it had.

The lone skip in the credentialed run is **not** an integration test:
`tests/unit/test_logger.py` skips one case on Windows because `time.tzset` is
POSIX-only.

---

## BLOCKED — the trailing-stop milestone

Unchanged from M5h.

*Arming condition:* **whoever amends Q-C §3's leg set.**

---

## The rotation's own procedure — read `CLAUDE.md`, not this

The five steps live in `CLAUDE.md`'s **Git workflow** section and that file is
the authority. Recorded here only as pointers:

- **Step 4 — re-read the contracts under `docs/`** for prose the milestone
  superseded. It is the step most easily skipped, because the milestone that
  invalidates a paragraph is always editing a different file. **At M5j's
  rotation it found a sentence in `docs/QB_ESCALATION.md` that had been false
  since M5f** — three rotations had run this step over that file and none caught
  it, while the same claim in `docs/QC_PROTECTIVE_ORDERS.md` was annotated at
  M5h.
- **Step 5 — verify the tag RESOLVES**, never merely that it exists. At this
  rotation `milestone/M5j` was created pointing one commit short of the closing
  commit, and `git tag -l` reported success throughout.
- **An arming condition names its CALLER, not an event** — and it is now audited
  at COMMIT time, not only here. `M5h-352` is why.

> **DO NOT MOVE A RULE INTO THIS FILE.** Step 3 rewrites it every rotation. At
> M5i's rotation `CLAUDE.md` was found asserting that the grep-the-digits rule
> and its inverse *"both live in `docs/NEXT_MILESTONE.md`'s process section"* —
> and they did not, because a previous rotation had rewritten the file out from
> under the claim. That is the third time a rule has been lost this way. Rules
> live in `CLAUDE.md`; this file holds items, not doctrine.
