# Next milestone — M5j

Written at M5i's rotation. **This is the single home for live open items.**
Every item below was verified present in the tree at `812f9b2`; anything M5i
closed has been struck rather than carried, and the strikes are listed so the
removal is auditable rather than silent.

---

## Before M5j starts — the namespace

**IDs are `M5j-NNN`: three digits, zero-padded, starting at `M5j-001`.** Not
letters. `CLAUDE.md` still describes an `M5d-A` scheme it has never used and
carries an annotation saying so; the digit convention is the real one and this
line is the only place it is prescribed, which is exactly the `phase_5_` shape
one step inside the repository. **A rotation that rewrites this file must carry
this paragraph forward.**

M5i allocated **130** ids, `M5i-001` through `M5i-136`, with gaps at `068`–`073`
— the project owner's reserved block, and nothing else. No duplicates, and every
commit in the range carries a findings block. Verified at rotation by both
documented extractors, which agreed on every field.

> **THE RESERVED BLOCK IS STILL RESERVED.** `M5i-068`, `M5i-071` and `M5i-073`
> are cited in the tree and declared nowhere. That is deliberate and the
> extractors report it every time as `cited-not-declared`; it is not a defect to
> be closed by inventing declarations for them.

---

## THE CENTRAL FACT — read this before anything else

M5i closed `M5h-371` and made the close-resolution label a **consequence** of
the write rather than a prediction of it. It unified three copies of the
bookability criterion into one predicate. It corrected prose that had outlived
what it described. And it rebuilt the mutation harness so that it now implements
the contract its own docstring had always stated.

**NONE OF THAT IS THE CENTRAL FACT. This is: the paths M5i added have not run,
and the runs that did happen were recorded only in a gitignored file.** See
`docs/RUN_LEDGER.md`, which holds the census: 47 distinct pids, 3 substantial
runs inside the M5i window and 2 more after its close.

Every path M5i **added** is exercised by fabricated fixtures, exactly as at
M5h's close — and **M5i added two emitters to paths no venue has ever exercised**
(`_sold_unpriced`, and the fourth close-resolution outcome). The composition
risk M5f made reachable and M5g partly retired is **larger again**, for the
second milestone running.

The uncomfortable shape of that: three milestones have now improved the code
that handles states no venue has produced. Each improvement is correct as far as
anything here can tell, and "as far as anything here can tell" is a fixture
written by the same hand that wrote the branch.

---

## STRUCK AT THIS ROTATION — closed by M5i

- **`M5h-371`: a CRITICAL could say `filled_and_booked` while nothing was
  booked.** CLOSED. `_resolve_close` selects its `_CloseResolutionText` from
  `_book_resolved_close`'s **return value**, in the `finally`, beside the write.
  A fourth outcome, `_RESOLVED_BOOK_FAILED`, exists because reusing the released
  text would have swapped a label that lies about the ledger for one that lies
  about the position. Pinned by
  `test_a_booking_that_failed_is_not_labelled_booked`, which asserts the write
  was ATTEMPTED and the label agrees with it — either alone is weak.

- **W5 / `M5i-019`: a structural property no behavioural test can hold.**
  CLOSED, **and not in the form it was predicted**. The item said only an
  `IfExp` count could hold it and that the architect had declined that test as
  brittle. The suite holds it now by a different instrument:
  `test_the_renderer_no_longer_discriminates` (zero `IfExp` in the renderer) and
  `test_exactly_two_functions_name_a_resolution_text` (the selection-site
  census). `M5i-060` measured *why* the predicted form was wrong — the `IfExp`
  count went 2 to 1 legitimately, because a three-way nested ternary is two
  nodes and the two-way replacement is one. **The count was the wrong proxy for
  the thing being protected**, which is the more useful half of this strike.

- **`M5h-352`: the 43.5s comment in `_sell_and_book`.** CLOSED at `812f9b2`.
  The comment now states the bound on the path it is actually about — 10.0s
  against `D = 9.0`, with no retry at all — and says why `CLAUDE.md` needs no
  correction.

  **Record what this one cost, because it is the origin of a new rule.** Its
  arming condition read *"whoever next edits `_sell_and_book`"*. **Eight M5i
  commits edited that file and one rewrote that method**, adding a branch to it.
  Nothing noticed. That is `CLAUDE.md`'s mode 3 — the condition fires and
  nothing looks — and it was found by the rotation pass, which is the only thing
  that has ever found one. `CLAUDE.md` now carries the remedy: **an arming
  condition is audited at COMMIT time by any commit touching its named site**,
  and resolved or explicitly reaffirmed there.

---

## UNRULED — reserved to the project owner

### U8. The harness: refuse, or report? — `M5i-096`, and new at this rotation

`scripts/mutation_survey.py` prints `target is tracked and clean` or `target has
uncommitted edits` and **proceeds either way**. `describe_vcs_state` computes the
fact; nothing acts on it.

**A dirty target is the NORMAL case and that is why it is advisory.** M5i's
commits A and B both surveyed uncommitted edits, and had to — surveying the
committed version would measure the *previous* commit, which is not the thing
under review. A harness that refused here would have refused every survey the
milestone actually ran.

**What makes it a question rather than a settled no:** `M5i-084`'s rule is
satisfied by the out-of-tree snapshot, which exists whatever git says, so
refusal would buy nothing the snapshot does not already provide. The argument
for refusing is different — that a survey against uncommitted work has no
recoverable baseline in the repository if the snapshot is also lost.

*Arming condition:* **whoever next changes `describe_vcs_state` or the block in
`main` that prints its result.** Refusal is one `if` at that call site and the
fact is already computed.

### U0. `_persist_ledger`'s `pending=persisted.pending` — carried, untouched

Unchanged from M5h. M5i modified `store.py` only in a **docstring**
(`M5i-024` — a paragraph claiming nothing wrote a `DayRecord`, false since the
commit that added one), so this condition did not fire.

*Arming condition:* **whoever next changes what either persistence closure
writes.** A docstring correction is not that.

### U1. `NOT_PLACED`: re-place, or drop? — `M5f-061`, `M5f-064`

Carried, unfired.

*Arming condition:* **whoever writes the first live-run change to
`resolve_placement`'s verdict handling.**

### U2. The venue-refusal half of e3-narrow — `M5f-083`

Carried, unfired. M5i edited `_sell_and_book`'s tail, which is a *different*
`except` chain — the item's own text already excludes it in those words.

*Arming condition:* **whoever next edits `dispatch`'s except chain** — B1 edited
`_sell_and_book`'s, not this one, and so did M5i.

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

*Arming condition:* **whoever needs to substitute the executor** — the paper
simulator or the backtest engine, neither of which exists.

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Carried, unfired. M5i did not touch `config/models.py` at all.

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

---

## NEW AT M5j

### A1. Commission never reaches the ledger, and the gap is at the port

**The wiring inside `core/portfolio.py` is COMPLETE**, on both limbs. `fee` is
declared `fee: Decimal = Decimal(0)` and consumed on **four** lines, two per
limb:

```python
            pnl = self._realised_from_total(position, exit_quote_total) - fee
            proceeds = self.free_quote + exit_quote_total - fee
```
```python
            pnl = position.unrealized_pnl(exit_price) - fee
            proceeds = self.free_quote + position.quantity * exit_price - fee
```

Nothing in that file needs to change. **The defect is that no commission figure
ever arrives to pass.**

**COMMISSION DOES NOT CROSS THE PORT.** `commission` occurs **zero** times in
`src/`; its only occurrence in the whole code tree is an unread wire fixture in
`tests/unit/test_exchange_mappers.py`. `commissionAsset` occurs **zero** times
anywhere in the repository. `to_order` in `exchange/models.py` is the sole
venue-to-domain mapper and reads **16** distinct wire keys — counting the three
timestamp candidates `_first_ms` tries — and `fills` is not among them. The
venue's own fee report is discarded at the wire boundary, silently, because a
dict key nobody reads raises nothing. `Order` carries no commission field,
`ExitFill` carries four fields and none is a fee, and every port method returns
`Order`, so nothing fee-shaped can cross by construction.

**The three call sites are `_book_close` and `_book_resolved_close` in
`executor.py`, and `_book_exits` in `reconciliation_driver.py`.** They are not
alike: `_book_close` holds the whole `Order`, `_book_resolved_close` holds only
a `total`, and `_book_exits` holds an `ExitFill`. A single uniform fix does not
exist across them. `_sell_and_book` is **not** a call site — it is the enclosing
path that calls `_book_close`, and naming it as one located the defect a layer
too high.

**WHICH FILES WOULD HAVE TO CHANGE:** `exchange/models.py`, so `to_order` reads
the fee; `core/models.py`, so `Order` can carry it; `execution/reconciliation.py`,
overturning `ExitFill`'s stated four-field ruling; and `core/interfaces.py`,
because the port's contract widens with `Order`. **Two of those are the port.**

**SITE 3 NEEDS A NEW ENDPOINT, NOT A WIDER ONE.** `_book_exits` reads
`get_order` point queries. In this tree's own fixtures `fills` appears only on
create-order payloads; the query-shaped fixture carries no `fills` key at all.
So a fully widened `Order` still leaves that site with nothing to read, and
reaching a fee there needs `myTrades` — **a new port method**, not a wider one.

**THE DENOMINATION INVARIANT, RULED BY THE PROJECT OWNER: a fee crosses a
boundary only as an amount paired with its asset, never as a bare `Decimal`.**
Binance charges commission in the quote asset, the base asset or BNB. Both
subtractions above are quote-denominated and both operands are `Decimal`, so
subtracting a BNB fee from a USDT P&L succeeds silently and the type system
cannot catch it. This tree cannot tell which asset a commission is in, because
it has never captured the field. See `CLAUDE.md`'s money section, where the
invariant is stated.

**THE TWO-OF-THREE FIX IS REJECTED, ON LEDGER-COMPARABILITY GROUNDS.** Wiring
the two sites that could reach a fee and leaving the third would make the ledger
net of fees on some closes and gross on others, with no reader able to tell
which without knowing the close path. A ledger whose purpose is to match an
exchange statement cannot be net in part.

**RECLASSIFIED: this is an architectural accounting item, not a wiring
omission.** The name it carried — an omission at three call sites — located it
in the wrong layer and made it look one commit deep.

**THREADING `fee=Decimal(0)` AS AN INTERIM STUB IS FORBIDDEN.** It changes no
behaviour, passes the gate unchanged, and retires the finding that names the
defect while leaving the defect exactly where it is.

**Invisible on Testnet and systematic on live money.** Commission was
`0.00000000` on both trades of order list `137501`. Binance Spot live charges a
maker/taker fee on every fill, so every realised figure would overstate profit
and understate loss by that fee, on every trade, with nothing reporting it.

*Arming condition:* **whoever next edits `to_order` in `exchange/models.py`** —
the single site where the venue's commission is discarded, and the first site
any fee must cross. No caller downstream of it can be written to pass a fee
until it does.

### A2. A manual action and a venue-triggered fill are indistinguishable

MEASURED by content, not speculated. `reconciliation.py`'s per-leg refinement
branches in this order:

```python
    if order.status is OrderStatus.FILLED or order.filled_quantity > 0:
        return (ProtectionState.UNKNOWN, "... reports {status} with {n} executed ...", _exit_fill(order))
    if order.status.is_open:
        return (ProtectionState.UNKNOWN, "... is INSTRUMENT DISAGREEMENT ...", None)
    return (ProtectionState.DIVERGED, "... was requested and does not rest: the point query reports {status}", None)
```

A leg that is `CANCELED` with `filled_quantity == 0` fails the first branch (no
fill), fails the second (`CANCELED` is terminal, so `is_open` is false), and
falls to the third: **`ProtectionState.DIVERGED`, with `ExitFill` `None`.**

**Had the bot been running on 2026-09-17 at 10:15Z it would have classified that
position `DIVERGED`, booked nothing** — `exit_fill is None` is `_book_exits`'
row 4, the silent healthy-pass row — **and kept a `Position` describing base the
account no longer held**, while `DIVERGED` sat outside `_TRUSTED_PROTECTION` and
refused every entry portfolio-wide.

The two facts *a protective leg was cancelled by someone else* and *a protective
leg diverged* present identically, because the only fields the classifier reads
are status and executed quantity and both are the same in either case.

*Arming condition:* **whoever next writes a classifier branch that reads a leg's
terminal status, or whoever adds the first non-bot writer to a live account.**

### A3. Two build-log headlines carry a claim their own annotation corrects

**Reserved to the project owner. No edit is proposed and none should be made
without a ruling.**

Two entries in `docs/PHASE_HISTORY.md` open on a claim that the same entry
annotates as false much further down:

* the M5h entry, whose opening reads that **almost every path built there has
  never run against a venue**, where an annotation in the same entry records
  that the close path it built ran in production 27 times before that close;
* the M5i entry, whose opening reads that **nothing has run, and that milestone
  added two more emitters to paths no venue has ever exercised**, where an
  annotation in the same entry records 3 substantial runs inside the M5i window
  and 2 more after its close.

**A reader of either intro alone gets the false version**, because the
correction is roughly 180 and 90 lines below it and nothing at the headline
points down to it.

**A SECOND ANNOTATION IS NOT THE REMEDY.** `CLAUDE.md` states it directly:

> **VERIFY THE TARGET IS PRESENT, BY CONTENT, BEFORE ANNOTATING — a duplicate
> annotation is PERMANENT.**

Both entries already carry an annotation of exactly this claim, so a second one
could not later be removed and the tree would keep two blocks saying the same
thing — leaving every future reader to work out whether the duplication means
two findings or one mistake. **The plausible remedies each cost something a
build log is supposed to protect**: a forward pointer at the headline edits a
sentence written in the tense it was decided, and moving the annotation upward
re-orders an entry. Which cost is acceptable is a judgement about the log's
purpose, and it is the owner's.

**`docs/PHASE_HISTORY.md` was outside this milestone's fence lift**, so this
item records the problem rather than acting on it. That is why it is written
here and not there.

*Arming condition:* **whoever next appends a milestone entry to
`docs/PHASE_HISTORY.md`** — the rotation's step 1 author, who is the first
caller that must decide whether a new entry's headline may state a claim the
entry will later annotate.

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
never ran or ran and failed**, because the write raises before it commits. This
is W1's shape and the second measured instance of the dual-sided expressiveness
rule, now annotated in `CLAUDE.md`.

*Arming condition:* **whoever next writes a test asserting over `Portfolio`
state to distinguish two booking outcomes.** The state cannot separate them;
only the label can.

### `M5i-104`. An unguarded unpack turns a kill into a crash

`test_a_partial_fill_with_no_cost_basis_still_goes_naked` does
`(naked,) = _records(...)` with no prior non-emptiness assertion, so a mutation
removing that record fails it at `ValueError` rather than at an assertion —
scored as a crash by the discriminator, and correctly so. **A 12-site sweep of
the same pattern is deferred**; M5i guarded only what it touched.

*Arming condition:* **whoever next edits that test, or runs a survey whose
predicted killers include it.**

### `M5i-126`. A substring assertion pins wherever its anchor occurs

`test_the_refusal_names_the_cause_the_remedy_and_the_opt_out` asserts three
substrings against a whole refusal message, and **all three are satisfied by the
opening paragraph alone**. Two thirds of what its name claims is unheld, and a
mutation replacing the entire remedy block killed nothing. **Not fixed at M5i** —
it was a fifth change against an authorised set of four sites plus one named
test, and an instrument edited outside its authorisation is `M5i-071`'s shape.

*Arming condition:* **whoever next edits `_UNREAD_OUTPUT` or that test.**

### The `_go_naked` family's fourth candidate

`_go_naked`'s message says the position is *"UNPROTECTED and still open"*. That
is false at the abandoned-after-cancel caller under `ALREADY_CLOSED`, where the
venue closed the position for us — the call site's own comment concedes it in
those words. Three members of this family have already been split off for
exactly this reason (`_go_naked_retaining`, `_sold_unbooked`, `_sold_unpriced`);
this would be the fourth.

**THE FALSE SENTENCE HAS NOT BEEN EMITTED — MEASURED, WHERE THIS WAS PREVIOUSLY
INFERRED.** Against the frozen capture whose digest section 2 of
`docs/RUN_LEDGER.md` states, three instruments agree: the rendered message text
`UNPROTECTED` occurs **0** times, `event=close_naked` — the structured field on
that same emission — occurs **0** times, and `event=close_abandoned`, the branch
that reaches it under `ALREADY_CLOSED`, occurs **0** times.

**That is a statement about the past, not a clearance.** The branch remains
unexercised, the message remains wrong at that caller, and this item stays
carried. A path that has not run is not a path shown to be correct.

> **THE PREMISE THIS ITEM CARRIED IS FALSE, AND THE CONCLUSION IS UNAFFECTED.**
> It read *"`ALREADY_CLOSED` has never occurred — see X2 — so the false sentence
> has never been emitted."* Both clauses failed at M5j. `ALREADY_CLOSED` **did**
> occur, at `2026-09-15T23:38:02Z`, and **`X2` no longer exists** — M5j split it
> into X2a and X2b, so the cross-reference dangles.
>
> **The occurrence never reached this branch.** It was refused at close-plan
> time — `event=close_planned decision=already_closed`, then
> `event=dispatch_refused` with `refused_as=close_already_closed` — so
> `_execute_close` was never entered and `_go_naked` was never called. The
> conclusion survived its premise by luck of routing, not by design.
>
> **An item whose premise fails while its conclusion holds is the shape most
> likely to be struck by mistake**, because the obvious reading of a false
> premise is that the item is spent. It is not.

*Arming condition:* **whoever next edits the abandoned-after-cancel branch in
`_execute_close`**, which is the only caller that can reach it.

### `M5i-109`. Two stale sentences in A1's docstring

`test_a_complete_fill_the_venue_never_priced_reaches_the_naked_guard` names its
sibling as `..._is_reported_as_partial_today`, which commit B renamed, and says
*"the three tail exits"* where there are now four. Both were introduced by M5i's
own commits and neither was fixed: the authorised edit to A1 was one line.

*Arming condition:* **whoever next edits that test.**

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

### W6. Format strings in `executor.py` — `M5i-015`, with a moved number

**The number moved and the weakness did not.** `getMessage()` assertions in
`test_executor.py` went from **0** before M5i commit 1 to **7** now. The
`_log.*` call sites that serve one outcome each remain unpinned by construction.

**Why that is not reassurance, restated because the number improving invites
the opposite reading:** a message is safe while its call site serves ONE
outcome, and nothing enforces that property. M5i added `_sold_unpriced`, a new
single-outcome site, and the exposure is identical to every other.

---

## UNMEASURED — venue facts nothing in the tree can supply

**Provenance: re-derived at M5j from a frozen capture whose digest
`docs/RUN_LEDGER.md` states.** Runs did occur between rotations; the evidence
existed and was sitting in the gitignored file — `CLAUDE.md`'s fifth drift
surface behaving exactly as described, on this paragraph. The counts below are
from that capture, by the commands the ledger prints.

### X1. No take-profit has ever filled — 82 placements, 62 closes

**Carried, and sharpened.** MEASURED: zero clauses of either form naming a
filled `TP` leg, against 162 naming a filled `SL` leg. The instrument reads a
classifier reason naming leg `TP` and a fill; it returns nothing.

Note what nearly looked like an observation and is not: order list `137501`'s
take-profit leg reached `CANCELED` with `executedQty 0.00000000` — a
take-profit terminating **without** filling. That trade is not an X1
observation.

### X2a. `ALREADY_CLOSED` — OBSERVED once, and this item is STRUCK

`decision=already_closed`, `2026-09-15T23:38:02Z`, `pid=26952`, BTCUSDT: the
stop leg had executed in full, the close plan refused the sell, and the next
pass booked the exit. It behaved correctly end to end.

**Why it read as unobserved for two milestones:** the search matched the enum's
member name `ALREADY_CLOSED` where the log carries its `.value`,
`already_closed`. A case-sensitive search returns 0 over the whole capture.

### X2b. `HALT` has never occurred — 65 close plans

**Carried.** MEASURED: `decision=halt` is zero across every close plan the
capture holds. This is what keeps the `_go_naked` fourth-candidate item above
unmeasured rather than urgent.

### X3. `resolve_placement` has never run — STRUCK

Falsified at M5j-PRE-2 and not re-argued: `placement_ambiguous` at
`2026-08-27 04:06:02` followed by `placement_resolved outcome=placed_live` a
minute later.

**The common shape:** each is a branch the tree can only reach through a
fixture, on a path where a fixture is a model of the venue rather than an
observation of it. **M5i added two more such branches.**

### The unobserved surface is far larger than these items, and both numbers belong here

X1 and X2b are the remaining unobserved **venue facts**, and that framing is
unchanged — they are things the venue would have to do, which nothing in the
tree can supply. They are **not** the remaining unobserved branches, and reading
them as such understates the position by an order of magnitude.

Measured against the frozen capture whose digest section 2 of
`docs/RUN_LEDGER.md` states, with the instrument beside each figure:

| Figure | Value | Instrument |
|---|---|---|
| clauses naming a filled leg `TP` | **0** | `grep -cE 'leg TP reports (status )?[A-Z]'`, both classifier forms |
| clauses naming a filled leg `SL` | **162** | the same pattern for `SL` |
| `decision=halt` | **0** | `grep -c 'decision=halt'` |
| close plans | **65** | `grep -c 'event=close_planned'` |
| log events DEFINED in `src/` | **33** | `_EVENT_*` constants, `_WS_EVENT_*` excluded |
| of those, NEVER emitted | **17** | `grep -c "event=<name>"` per constant, zero |
| `RefusalStage` members defined | **14** | the enum body |
| of those, unobserved | **9** | `grep -c "stage=<value>"` per member, zero |

The close plans reconcile: `decision=sell` 64 plus `decision=already_closed` 1
is 65, so of `CloseAction`'s three members exactly one — `HALT` — is unobserved.

**The websocket constants are excluded deliberately.** `_WS_EVENT_TYPE = "e"`,
`_WS_EVENT_KLINE = "kline"` and `_WS_EVENT_ERROR = "error"` in
`exchange/websocket_client.py` match a pattern looking for `_EVENT_` but are
**wire-protocol keys of Binance's stream payload, not log events**. Counting
them inflates the defined total and reports three events as never emitted that
were never log events at all. A first pass here did exactly that.

**What the 17 contain is the point.** The entire close-failure family has never
fired — `close_abandoned_after_cancel`, `close_book_failed`, `close_cancel_failed`,
`close_cancel_already_terminal`, `close_position_naked`, `close_sell_unconfirmed`,
`close_sold_unbooked`, `close_sold_unpriced`, `close_record_resolved` — along
with `placement_unresolved`, the fail-closed branch M5f's ruling created, and
`collaborator_failed`, whose absence is why Q-A stays uncalibratable.

*Arming condition:* **whoever next writes a test asserting that a branch is
unobserved, or a rotation compiling this section.** Both need the number rather
than the two items, and both are the first callers that cannot proceed without
it.

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
  invalidates a paragraph is always editing a different file.
- **An arming condition names its CALLER, not an event** — and it is now audited
  at COMMIT time, not only here. `M5h-352` is why.

> **DO NOT MOVE A RULE INTO THIS FILE.** Step 3 rewrites it every rotation. At
> M5i's rotation `CLAUDE.md` was found asserting that the grep-the-digits rule
> and its inverse *"both live in `docs/NEXT_MILESTONE.md`'s process section"* —
> and they did not, because a previous rotation had rewritten the file out from
> under the claim. That is the third time a rule has been lost this way. Rules
> live in `CLAUDE.md`; this file holds items, not doctrine.
