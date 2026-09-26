# Next milestone — M5l

Struck and repaired at M5k's rotation, in its first part. Every item below was
re-verified by content against `ae8c914`; anything M5k closed is reduced to one
index line naming the resolving commit and its findings, and its full text
lives in git history and in `docs/PHASE_HISTORY.md`'s M5k entry. M5l's scope,
priorities and new carried items are the rotation's second part. **This is the
single home for live open items.**

---

## Before M5l starts — the namespace

**IDs are `M5l-NNN`: three digits, zero-padded, starting at `M5l-001`.** Not
letters. `CLAUDE.md` prescribes the digit form in its rescued rule 2; this
paragraph is carried forward so that a reader of this file meets it first.
**A rotation that rewrites this file must carry this paragraph forward.**

**M5k's range is closed by the tag `milestone/M5k`**, applied to the closing
commit of M5k's rotation, and its count is read with one command rather than
written here, once that tag exists:

```
.venv\Scripts\python.exe scripts/check_findings.py milestone/M5j..milestone/M5k M5k
```

It prints the declared, distinct and maximum ids, and every duplicate, gap,
id cited but never declared, and commit with no block. The M5l namespace is to
be confirmed empty by the same tool, over `milestone/M5k..HEAD`, before
`M5l-001` is written.

> **THE M5i RESERVED BLOCK IS STILL RESERVED.** `M5i-068`, `M5i-071` and
> `M5i-073` are cited in the tree and declared nowhere. That is deliberate and
> the extractors report it every time as `cited-not-declared`; it is not a
> defect to be closed by inventing declarations for them.

> **AND THREE MORE M5i IDS ARE UNRECORDED ANYWHERE (`M5k-018`).**
> `scripts/check_findings.py` reports the M5i range's gaps as 68 through 73.
> The reserved block accounts for three of them; `M5i-069`, `M5i-070` and
> `M5i-072` appear in no commit message and no tracked file, and no document
> mentions them. They are not to be invented either.

---

## THE CENTRAL FACT — read this before anything else

**Nothing M5k added is shown to have run as committed, and the bot records
nothing that could show it.** Measured against the capture
`trading_bot.m5k-close-20260925T182818Z.log`, SHA-256
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`, taken at
M5k's close; `docs/RUN_LEDGER.md` §19 holds its census:

- **No line logged by code as committed at or after `651d334` is shown to
  exist.** Eight booking lines carry `fee=0E-8 fee_asset=USDT`, a key no commit
  before `651d334` writes. The first is at `2026-09-24T10:38:02Z`, seven hours
  before that commit existed, while the reflog held HEAD at `e511e6d`: the fee
  settlement ran from uncommitted code (`M5k-123`). No line carries
  `quote_total_source`, which every booking line writes from `c5dd7d5`, and
  none of the six events M5k added appears.
- **The bot records no commit** (`M5k-132`). Its startup banner is ASCII art
  and a mode line, and no line in any capture names a commit, a version or a
  dirty tree. `CLAUDE.md`'s deployment doctrine rules that this change, and
  marks the banner NOT YET IMPLEMENTED.
- **`RefusalStage.POSITION_STALE` fired once**, at `2026-09-24T19:25:00Z`
  (`M5k-124`) — the first time in any capture.
- **No run was writing when the capture was taken.** The bytes it adds to the
  previous capture hold six runs, every one ending in `engine_stopped` after a
  `SIGINT`; its last line is `pid=23236`'s, at `2026-09-25T16:16:10Z`.
  `pid=24772`, still appending when M5j's rotation wrote this section, last
  logged at `2026-09-19T09:42:02Z` and records no `engine_stopped`.

**The standard of evidence M5j set still holds.** A claim derived from a
capture names its digest in the sentence that makes it, or it cannot age
visibly.

---

## RESOLVED AT M5k — one index line each

Each item's full text is in git history and in `docs/PHASE_HISTORY.md`'s M5k
entry. An item resolved only in part is indexed here AND carried below with its
residue and its condition.

- **Priority 1 / A5, the DIVERGED exit-booking gap** — resolved in code at
  `3e444f0` (`M5k-004`–`M5k-009`): a diverged pass with no fill escalates at
  `CRITICAL` instead of continuing. The residue is carried as A5.
- **Priority 2, a gate-count self-verification helper** — resolved at
  `2109bee` (`M5k-011`, `M5k-013`–`M5k-020`): `scripts/check_gate_counts.py`.
- **Priority 4, the accounting architecture pass** — resolved for EXIT fees at
  `45ffe31`, `9f3deb1`, `f1c5af7` and `651d334` (`M5k-021`–`M5k-035`,
  `M5k-049`–`M5k-064`). The ENTRY half stays under `CLAUDE.md`'s live-trading
  block and is carried as A1.
- **A1, commission never reaching the ledger** — resolved for EXIT commission
  at `651d334` (`M5k-094`, annotated here at `222bdf4`). The entry half is
  carried as A1.
- **A4, `venue_time` on an `exit_booked` line** — resolved at `651d334`, after
  the rename at `f1c5af7`; the booking line's `filled_at` and
  `order_created_at` are pinned by test (`M5k-067`).
- **F1, the driver retrying a permanent fee refusal** — resolved at `d253cd5`
  by R2 with rulings A and B (`M5k-078`).
- **F2, a restart after a deferred settlement** — closed as MEASURED at
  `db73b63` (`M5k-065`): the restored close is released unbooked at `CRITICAL`,
  and the restart neither re-enters the retention nor books.
- **`M5i-104`, the named test's unguarded unpack** — resolved at `c5dd7d5`
  (`M5k-113`). The sweep is carried.
- **`M5i-109`, two stale sentences in a test docstring** — resolved at
  `c5dd7d5`, whose rewrite of the test removed the docstring; recorded in that
  commit's arming audit.

---

## CARRIED FROM M5k'S PRIORITIES

### 3. Regularising the arming conditions

Done at M5j's rotation for this file, and widened at M5k's by `CLAUDE.md`'s
rule g, under which the audit reads every document that carries a condition.
**Two conditions are left unparsed deliberately**, one in this file -- Q-C §3's
leg set -- and one in `docs/QB_ESCALATION.md` -- the halt flag's first writer.
Closing either needs a ruling rather than an edit. See the note under **Arming
conditions** below, which carries the measured registers.

---

## Arming conditions — the registers, with two deliberate exceptions

`scripts/check_arming_conditions.py` keeps a parsed and an unparsed register and
**exits non-zero while the unparsed register is non-empty**. Under `CLAUDE.md`'s
rule g it is run on every document that carries a condition. MEASURED at M5k's
rotation, on the tree this commit leaves:

| document | candidates | parsed | unparsed |
|---|---:|---:|---:|
| `docs/NEXT_MILESTONE.md` | 20 | 19 | 1 |
| `CLAUDE.md` | 2 | 2 | 0 |
| `docs/QB_ESCALATION.md` | 1 | 0 | 1 |
| `docs/QC_PROTECTIVE_ORDERS.md` | 0 | 0 | 0 |

At M5j's rotation the tool read 22 candidates here, 15 parsed and 7 unparsed,
every failure for the same reason: the bold span named no backticked symbol.

**Six were regularised by naming the site they actually guard**, leaving 22
candidates, **21 parsed and 1 unparsed**. Their targets were derived from the
tree rather than invented: the two persistence closures are `_persist_pending`
and `_persist_ledger` in `engine/modes.py`; the classifier branch is `_refine`
in `execution/reconciliation.py`; the executor's substitutes are
`paper/simulator.py` and `backtesting/engine.py`; the unobserved-surface table
is produced by `scripts/run_census.py`; and the two conditions reading *"whoever
next edits that test"* name tests the surrounding prose already identifies, so
the real node ids are used.

**ONE IS LEFT UNPARSED IN THIS FILE ON PURPOSE, AND ONE IN
`docs/QB_ESCALATION.md`, AND THAT IS THE CORRECT OUTCOME.** Corrected at M5k's
rotation: this heading read *"ONE IS LEFT UNPARSED"* while priority 3 above
read *"Two conditions are left unparsed deliberately"*, and the file
contradicted itself. Measured across every document the audit reads, both are
true of different scopes: one here, one in Q-B. The trailing-stop block guards
Q-C §3's leg set — a **contract document section**,
not a Python symbol. The honest target is `docs/QC_PROTECTIVE_ORDERS.md` §3,
and backticking that path *would* satisfy the parser; it is left as it stands by
ruling, because writing a path in to please a tool is writing for the tool.
Q-B's condition names *"the halt flag's first writer"*, a writer that does not
exist; its marker was normalised at M5k's rotation so the tool finds it, and it
is accepted unparsed by ruling for the same reason.

**So a non-zero exit is expected and is not a defect to regularise around.** The
checker is reporting that two conditions, one per document, guard something its
schema cannot express — which is the register doing its job. Widening the parser to accept a
caller-phrase with no symbol is the alternative, and it is the owner's call.

---

## THE MODE-3 RECORD — what M5k's rotation pass found

`CLAUDE.md`'s failure mode 3 is a condition that FIRES and nothing notices.
M5k's rotation read every condition against every M5k commit that edited its
named site. What it found is recorded here and not re-litigated:

- **A5 and `M5i-065` fired UNAUDITED at `3e444f0`.** That commit edited
  `_book_exits` -- row 4, the diverged escalation -- and its body carries no
  arming-condition audit. It is the commit that closed A5's code gap.
- **`M5i-065` fired UNAUDITED again at `f1c5af7`**, which edited the booking
  line inside `_book_exits`. Its audit named A4, A5 and A6 and not `M5i-065`.
- **`M5i-095` arguably fired at `3e444f0`**, whose
  `test_the_escalation_books_nothing_and_saves_nothing` asserts
  `portfolio.ledger is None` -- portfolio state -- to show that nothing was
  booked.

Every other firing in M5k was audited in the body of the commit that caused
it: U7 at `e511e6d`, A1 at `193a5b9`, and A4, A5, A6, F1, F2, `M5i-065`,
`M5i-095`, `M5i-104` and `M5i-109` at the commits their audits name.

**The instrument, and why it was not `git log -L`.** Which commits edited a
named function was measured by comparing that function's exact source
segment, extracted with `ast`, at every M5k commit and at its parent. `git log
-L` was tried first and missed an edit: its regex-range form did not report
`f1c5af7`'s change to `_book_exits`, and with `--no-patch` it printed nothing
at all. An instrument that under-reports firings produces exactly the silence
mode 3 describes.

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

Carried. **Its condition was repaired at M5k's rotation, because it was
spent.** It read *"whoever first sets `timeout_s`/`attempts` from config"*,
and that FIRST had already happened before M5k: the fee commit's audit
recorded it as `ReconciliationBudget.from_config`. A first that has happened
can never fire again, so the item could only ever read as waiting. The item is
about the DISPATCH per-call share, so the condition now names the one function
that derives it.

*Arming condition:* **whoever next edits `DispatchBudget.bounds_for_next_call` in `execution/dispatch_budget.py`.**

### U5. `BinanceRequestException`'s representation — `M5f-072`, `M5h-360`

Carried, unfired.

### U6. Whether `OrderExecutor` implements the `OrderExecutor` port

Carried, unfired.

*Arming condition:* **whoever writes `paper/simulator.py` or
`backtesting/engine.py`** — the two substitutes for the executor, neither of
which exists beyond a docstring stub.

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Carried. It FIRED at M5k's `e511e6d`, which edited the coherence block to count
settlement, and was REAFFIRMED there: `_CLOSE_SEQUENCE_CALLS` is not deleted,
because deleting it depends on the unruled five-versus-four confirm-step
question its own comment names.

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

---

## CARRIED FROM M5j

### A1. ENTRY commission never reaches the ledger, and `to_order` discards the fee report

**The EXIT half is resolved and indexed above**: since `651d334` every booking
site books net of the fee `get_my_trades` settles. **What is carried is the
residue.** ENTRY commission reaches the ledger at no site, by the project
owner's ruling R-a, so the ledger is net of exit fees and gross of entry fees;
and `to_order` in `exchange/models.py` still does not read the venue's `fills`
report, so any `fills` array a response carries is discarded at the mapper.
Netting the entry fee out of base quantity is the subject of
`CLAUDE.md`'s live-trading block, which it waits on. The condition below
watches `to_order` alone, and `193a5b9`, the first commit to edit it,
REAFFIRMED it.

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
status.

The condition's second disjunct, *"or whoever adds the first non-bot writer to
a live account"*, was removed at M5k's rotation: it named an event, not a
caller, and the event had already occurred, on 2026-09-17, when M5j recorded
an order list cancelled and its base sold by orders this bot did not place.

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

### A5. Position-level `DIVERGED` has never been observed in production — the residue of `M5j-011`

**The code gap is closed and indexed above**: since `3e444f0` a pass whose
position-level verdict is `DIVERGED` and whose legs reported no fill escalates
at `CRITICAL`, `exit_unbookable`, instead of continuing. **What is carried is
the evidence gap.** In `trading_bot.m5k-close-20260925T182818Z.log`, SHA-256
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`,
`diverged=1` occurs 28 times, all between `2026-08-27 04:07:02` and `04:38:02`
and so before the identifier-space fix `3970968`, and `exit_unbookable` occurs
zero times: the escalation has never run. `M5k-005` measured why the hazard has
not fired either: every line on which a requested leg did not rest also carried
a sibling fill clause, so booking took the fill branch. **A sibling is not a
mechanism.**

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

*Arming condition:* **whoever next edits `_report`'s warning text in `execution/reconciliation_driver.py`, or the booking line: `_log_booked` in that file or `execution/booking_line.py`.**

> **ANNOTATED BY 3b-2a: `classify_bookability` now reads `A > P > C > Q`**, by
> the project owner's Decision 1; Q still refuses until 3b-2b. This item's
> point is unchanged -- none of the four facts is a fill price -- and the
> condition above is REAFFIRMED: `_report`'s warning text and `_book_exits`'s
> booking line are untouched.

> **THE CONDITION WAS RE-POINTED AT M5k's ROTATION, BECAUSE ITS SITE MOVED.** It
> read *"whoever next edits `_report`'s warning text or `_book_exits`'s booking
> line"*. The booking line left `_book_exits` at `651d334` for `_log_booked`,
> and from `a534b31` its fields come from `execution/booking_line.py`
> (`settlement_fields`, then `quote_total_fields`). A condition naming the old
> site could no longer fire on an edit to the line it exists for. The item's
> point is unchanged.

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

### `M5i-104`. Unguarded unpacks turn kills into crashes — the sweep, now 18 sites

**The named test is resolved and indexed above.** A single-element tuple
unpack of log records with no prior length assertion fails at `ValueError`, a
crash, where a mutation removing the record should fail an assertion; `CLAUDE.md`'s
rule i now prescribes the remedy. **The sweep is carried, and it has grown from
the 12 sites M5i counted to 18.** MEASURED at `ae8c914`, with the instrument
stated: lines matching `^\s*\(\s*\w+\s*,\s*\)\s*=` under `tests/` whose
right-hand side reads log records (`_records(` or `caplog`), with no `assert
len(` in the three lines before -- 16 in `tests/unit/test_executor.py` and 2 in
`tests/unit/test_reconciliation_driver.py`. How M5i counted its 12 is not
recorded, so the two figures are not the same instrument.

*Arming condition:* **whoever next edits
`test_a_partial_fill_with_no_cost_basis_still_goes_naked`, or runs a survey
whose predicted killers include it.**

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
Re-measured at M5k's rotation, at `ae8c914`: `grep -c 'getMessage()'` over
`tests/unit/test_executor.py` counts **6** lines. The instrument behind the
earlier 7 is not recorded, so the difference is not established as a change.

**Why that is not reassurance:** a message is safe while its call site serves
ONE outcome, and nothing enforces that property.

---

## UNMEASURED — venue facts nothing in the tree can supply

**Provenance: re-derived at M5k's rotation from the frozen capture
`trading_bot.m5k-close-20260925T182818Z.log`, whose SHA-256 is
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`** —
5,074,996 bytes, 26,126 lines, of which every earlier capture in the evidence
directory is a byte-exact prefix. The digest is named here because these
figures move whenever the bot runs. X1, X2a and X3 below are records of M5j's
closures and keep M5j's figures.

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

### X2b. `HALT` has never occurred — zero across 163 close plans

**CARRIED, and the sole remaining unobserved venue fact.** Re-measured against
the capture named above: `decision=halt` is **zero** (`grep -c`), and the
denominator is `event=close_planned` **163** (`scripts/run_census.py`),
reconciling as `decision=sell` 162 plus `decision=already_closed` 1. **The
denominator moved from 75 at M5j's close to 163 at M5k's**, which is why it is
quoted with its capture rather than bare.

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
| order lists placed | **185** | `event=order_placed`, `scripts/run_census.py` |
| complete exits | **165** (154 `close_booked` + 11 `exit_booked`) | `scripts/run_census.py` on each |
| close plans | **163** | `event=close_planned`, `scripts/run_census.py` |
| `decision=halt` | **0** | `grep -c 'decision=halt'` |
| clauses naming a filled leg `TP` | **3** | both classifier forms: `leg TP reports FILLED with`, and `leg TP reports <status> with <qty> executed` at a non-zero quantity |
| clauses naming a filled leg `SL` | **164** (146 + 18) | the same two forms for `SL` |
| log events DEFINED in `src/` | **39** (37 `_EVENT_*`, 2 public `EVENT_*`) | module-level string constants, by `ast`; `_WS_EVENT_*` excluded |
| of those, absent from the capture | **22** | `event=<value>` absent |
| of those, added at M5k | **6** | the six below, every one absent |
| `RefusalStage` members defined | **14** | the enum body |
| of those, unobserved | **8** | per-member `stage=<value>` absent |

**The instrument was re-validated before it was trusted.** Run on M5j's capture,
SHA-256 `bfc8ffddc494f288e710df00918507c7027bcfe538096def4d32172ed2af8d3d`, the
same script returns M5j's own figures: `TP` 1, `SL` 162 (144 + 18), and 9
unobserved `RefusalStage` members. The "both classifier forms" in M5j's rows are
therefore `reports FILLED with` and a non-`FILLED` status reported with a
non-zero executed quantity -- the 18 are order 300642's `EXPIRED` leg.

**What moved since M5j's close, and why.** The defined-events row rose from 34
to 39: M5k added `exit_settlement_held`, `exit_quote_totals_disagree`,
`close_settlement_deferred`, `exit_settlement_deferred`, `exit_unbookable` and
`venue_quote_total_unavailable`, and removed `close_sold_unpriced`. Two of the
six are public `EVENT_*` constants in `execution/booking_line.py`, which M5j's
`_EVENT_*` instrument would not have seen (`M5k-127`); the instrument is widened
here. `engine_stopped`, absent at M5j's
close because its process predated the marker, is now observed 8 times, so the
row that subtracted it is gone. `POSITION_STALE` left the unobserved stages
(`M5k-124`).

**The websocket constants are excluded deliberately.** `_WS_EVENT_TYPE`,
`_WS_EVENT_KLINE` and `_WS_EVENT_ERROR` in `exchange/websocket_client.py` match
a pattern looking for `_EVENT_` but are wire-protocol keys of Binance's stream
payload, not log events.

*Arming condition:* **whoever next runs `scripts/run_census.py` against a newer
capture**, which is the tool that produces every figure in this table.

---

## THE GATE BASELINE

Measured at M5k's rotation, at `ae8c914`, on this credentialed machine:

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  129 files already formatted
mypy                                   Success: no issues found in 79 source files
pytest                                 1822 passed, 1 skipped
```

**`1822 passed, 1 skipped` is MEASURED.** `1819 passed, 4 skipped` is **DERIVED**
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
- **Step 5 — verify the tag RESOLVES**, never merely that it exists. At M5j's
  rotation `milestone/M5j` was created pointing one commit short of the closing
  commit, and `git tag -l` reported success throughout.
- **An arming condition names its CALLER, not an event** — and it is now audited
  at COMMIT time, not only here. `M5h-352` is why.
- **The findings count is read, never written:**
  `.venv\Scripts\python.exe scripts/check_findings.py <range> <namespace>`, over
  the milestone's tagged range once the tag exists. It prints the declared,
  distinct and maximum ids, and every duplicate, gap, id cited but never
  declared, and commit with no block.
- **Step 2's count sites:** `scripts/check_gate_counts.py`, run TWICE, outgoing
  figures first -- `CLAUDE.md`'s rule l, and `M5k-125` is why.

> **DO NOT MOVE A RULE INTO THIS FILE.** Step 3 rewrites it every rotation. At
> M5i's rotation `CLAUDE.md` was found asserting that the grep-the-digits rule
> and its inverse *"both live in `docs/NEXT_MILESTONE.md`'s process section"* —
> and they did not, because a previous rotation had rewritten the file out from
> under the claim. That is the third time a rule has been lost this way. Rules
> live in `CLAUDE.md`; this file holds items, not doctrine.
