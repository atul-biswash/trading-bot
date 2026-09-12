# Next milestone — M5i

Written at M5h's rotation. **This is the single home for live open items.**
Every item below was verified present in the tree at `ff9cc66`; anything M5h
closed has been struck rather than carried, and the strikes are listed so the
removal is auditable rather than silent.

---

## Before M5i starts — the namespace

**IDs are `M5i-NNN`: three digits, zero-padded, starting at `M5i-001`.** Not
letters. `CLAUDE.md` still describes an `M5d-A` scheme it has never used and
carries an annotation saying so; the digit convention is the real one and this
line is the only place it is prescribed, which is exactly the `phase_5_` shape
one step inside the repository. **A rotation that rewrites this file must carry
this paragraph forward.**

M5h allocated **375** ids, `M5h-001` through `M5h-375`, with no gap and no
duplicate — verified at rotation by both documented extractors, which agreed.
Capacity is not a concern for a digit namespace; the check is still run.

---

## THE CENTRAL FACT — read this before anything else

M5h opened on a sentence from M5g: *"a restart heals the balance sheet and
erases the income statement."* **That is no longer true, and the closing
statement is in `PHASE_HISTORY.md`'s M5h entry.** The ledger now records venue
fills, the bot's own closes, and closes confirmed a bar after an ambiguous
dispatch; it survives a restart, and it carries the day's history and a lifetime
total both ways across the store.

**What replaces it as the thing to be uneasy about:** the ledger is now written
by three paths and *nothing reconciles the three against an exchange statement*.
M5g's defect was an absence and was visible as one. Its successor is a
disagreement, and a disagreement between three writers is not visible from
inside any of them.

---

## THE HIGHEST-VALUE OPEN ITEM — `M5h-371`

**A CRITICAL can say `filled_and_booked` while nothing was booked.**

In `_resolve_close`, `outcome` is computed inside the `try` from
`total is not None`, and the booking happens in the `finally`. The two are
pinned by *different tests* and **nothing pins that they agree**. MEASURED at
B2's survey: mutation V2 removed the booking action alone and the log still
reported `filled_and_booked` — four tests died on the ledger and not one on the
label.

**Why this ranks above everything else here.** It is a false marker on a
CRITICAL, and this project has already recorded what a false marker costs:
*"A field that is accidentally correct is more dangerous than one that is plainly
wrong, because inspection cannot catch it."* The line now instructs an operator
**not** to enter the trade by hand. If the write silently failed, that
instruction converts a recoverable omission into a permanent one — the operator
is told the ledger has it, and the ledger does not.

*Arming condition, in caller terms:* **whoever next edits `_resolve_close` or
`_log_close_resolved`** — the two are one method apart and either edit puts the
seam in front of them. Nothing else needs to happen first.

*What would close it:* make the label a consequence of the write rather than a
prediction of it, or assert their agreement directly. The shape is not ruled
here.

---

## UNRULED — reserved to the project owner

### U0. `_persist_ledger`'s `pending=persisted.pending` — carried, untouched

At `engine/modes.py:1526`, with the reasoning at `:1477`: the ledger closure
writes the pending set from the **boot snapshot** rather than from live state.
Untouched through eleven M5h commits that each had occasion to change it, by
standing instruction.

*Arming condition:* **whoever next changes what either persistence closure
writes.** M5h did not, deliberately.

### U1. `NOT_PLACED`: re-place, or drop? — `M5f-061`, `M5f-064`

`CLAUDE.md`'s locked rule says *"Not found ⇒ nothing rests; re-place at the same
generation."* The executor deletes the record and re-places nothing, so a signal
reported not-found is dropped — logged at ERROR as `dispatch_missed`, countable
but gone. **`NOT_PLACED` is an INFERENCE** over at least three venue states the
executor cannot distinguish.

*Arming condition:* **whoever writes the first live-run change to
`OrderExecutor.__call__`'s placement branch.** M5h edited `__call__` three times
and each time only the *close* branch, so this stayed unarmed — narrowly.

### U2. The venue-refusal half of e3-narrow — `M5f-083`

Client-side refusals create no pending record. Venue refusals still do.

> **PARTLY SUPERSEDED BY B1, and the surviving half is now sharper.** B1 ruled
> the *close sell's* `except` on exactly this axis: `ClientRefusalError` releases
> the record, everything else retains. So the principle is settled and
> implemented on one path. What remains unruled is the **entry** path's except
> chain, which still records on a venue refusal.

*Arming condition:* **whoever next edits `dispatch`'s except chain** — B1 edited
`_sell_and_book`'s, not this one.

### U3. Whether to consume `orderReports` — `M5f-038`

MEASURED: the placement response carries Q-C §7's complete compare set at no
extra call. The cost is `OrderList` holding two leg representations, or two
types for one concept.

*Arming condition:* **the placement site in `OrderExecutor`**, the only thing
holding a placement response.

### U4. The per-call share — `M5f-009`

Measured worst cases: OTOCO **5**, OTO **4**, unprotected **1**,
recovery-bearing entry **3**. Whether the confirm step queries all three legs or
only the two protective ones decides 5 against 4. Annotated at twelve sites;
**do not annotate it again — a duplicate is permanent.** M5h's `M5_NUMBERS.md`
annotation *names* it as still-unruled without re-annotating it, which is the
distinction to preserve.

*Arming condition:* **whoever first sets `timeout_s`/`attempts` from config**
rather than passing the derived bounds.

### U5. `BinanceRequestException`'s representation — `M5f-072`, now `M5h-360`

It carries **no code**, and is raised only after a 2xx when the body will not
parse — so for a placement it leans toward LANDED. `code=None` reads as
"client-side" to anyone trusting the `:param` line, which is wrong in the
dangerous direction.

> **ITS ARMING CONDITION WAS MIS-SPECIFIED, AND THE ITEM ARMED ANYWAY —
> `M5h-360`.** It read *"whoever first branches on `ExchangeAPIError.code` in
> production"*, and **nothing branches on `.code` yet.** But B1 needed exactly
> this distinction and could not get it: `ExchangeAPIError` is produced BOTH by
> an unclassified venue rejection AND by `BinanceRequestException`'s unreadable
> 2xx, and no predicate over the type separates them. B1 adopted a deliberately
> WIDE predicate and recorded why.
>
> **This is failure mode 1 from `CLAUDE.md`'s rotation rules with a twist worth
> recording: the condition named a real caller that has still not arrived, while
> a DIFFERENT caller — one that needed the distinction and had to work around
> its absence — arrived first and was not covered by the wording.** The lesson
> is not "name a caller" (it did) but that a caller who *routes around* a
> missing answer is as much an arming event as one who consumes it.

*Corrected arming condition:* **the next caller that must distinguish "the venue
rejected this" from "the venue may have accepted this".** B1 was the first; it
is unlikely to be the last.

### U6. Whether `OrderExecutor` implements the `OrderExecutor` port

`core/interfaces.py` declares a port taking an `OrderRequest`. The class does not
implement it.

*Arming condition:* **whoever needs to substitute the executor** — the paper
simulator, most likely.

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Dead: one definition, zero readers, and its comment claims a consumer that does
not exist. It **anchors the `7aa8f59` annotation**, so removing it orphans or
deletes an annotation. A precedent decision, not a cleanup.

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

> **NEARLY ARMED AT M5h AND DELIBERATELY NOT TAKEN.** Commit A added a second
> validator to that very model and left `_CLOSE_SEQUENCE_CALLS` alone, because
> the authorisation was for the envelope and this is a precedent decision. Named
> so the next editor of that block knows the item is sitting there.

---

## DECLARED TEST WEAKNESSES — known, and none is a defect

Each was **declared before the survey that confirmed it**, not discovered after.
They are listed because an undeclared abstention is indistinguishable from
coverage, and after the fact nobody re-examines a green test.

### W1. Two mutations, one failure set — `M5h-356`, `M5h-370`

Twice this milestone a pair of distinct mutations produced **identical** failure
sets, so the suite cannot say which of the two broke:

- `M5h-356`: Commit A's T3 (the tolerance never binds) and T4 (the validator is
  never registered). Both kill the same three tests.
- `M5h-370`: Commit B2's V2 (booking never runs) and V5 (booking runs but writes
  nothing). Both kill the same four.

Acceptable in both cases — each pair is two total failures of one guarantee — but
**a green suite there says the guard binds somehow, not that it binds for the
stated reason.**

### W2. A guard conditional on a neighbouring number — `M5h-357`

`test_a_timeout_above_thirty_is_refused_before_it_can_discard_sock_connect`
pins that the transport envelope catches a >30s timeout **first**, not that the
discarded `sock_connect` is guarded on its own terms. At any
`dispatch_deadline_s` above 29.0 a 31s timeout passes the envelope and reaches
the trap unguarded, and nothing in this tree reads `sock_connect`.

### W3. A test that pins the numbers, not the behaviour — `M5h-354`

`test_the_shipped_values_hold_at_exact_equality` asserts the two shipped values
are 1.0 apart. It does **not** assert the envelope uses that distance — its
assertions read config, never `_TRANSPORT_OVERRUN_TOLERANCE_S` — so it abstains
on both T3 and T4 and bites only the `<=`→`<` mutation.

### W4. An end-state assertion cannot see *when* — `M5h-366`

`test_retention_is_single_shot_on_every_resolution_branch` asserts the lock is
gone after the next candle. A release at *dispatch* time satisfies that exactly
as well as a release at *resolution* time, so it abstains on the predicate
inversion and on the sibling-releases mutation. Expressiveness is a property of
the input; this input cannot distinguish the two timings.

### W5. A structural property no behavioural test can hold — `M5i-019`

`_log_close_resolved` selects `outcome`, `resolution` and `message` from ONE
ternary over `_CloseResolutionText`. Splitting that back into two independent
reads of `booked`/`filled` is **behaviourally identical and kills ZERO tests** —
MEASURED at M5i commit 1, where the two real mutations killed 5 and 4 and this
one kills none.

Only an AST assertion (exactly one `IfExp` in the method) could hold it, and the
architect DECLINED that test as brittle against legitimate refactoring. The
property is therefore held by the docstring and by review, deliberately and on
the record — not by the suite.

**Why it reaches beyond this method:** `M5h-371`'s fix converts that single
expression. If a later hand splits it first, the fix converts one copy and
leaves the other — the two-discriminator state commit 1 existed to remove.

### W6. Every format string in `executor.py` is unpinned — `M5i-015`

MEASURED: before M5i commit 1 there was no `getMessage()`, no `.message` and no
`caplog.text` anywhere in `test_executor.py`. Commit 1 added the first two
message assertions in the module's history; the other 21 `_log.*` call sites
remain unpinned by construction.

**Why only one of the 23 could be wrong, and why that is not reassurance.** An
AST census over all 8 `_log`-bearing modules in `src/` (63 calls) found every
message is a plain constant — correct everywhere a call site serves ONE outcome.
`_log_close_resolved` was the only site in `src/` serving three outcomes from one
call, which is the whole reason it could disagree with itself. **Nothing enforces
that.** A future logger serving two outcomes from one call inherits the identical
exposure with no test to catch it.

---

## STALE PROSE — `M5h-352`

**One comment invites a misreading this milestone measured to be wrong.** In
`_sell_and_book`, the comment ending *"43.5s, which EXCEEDS
`dispatch_deadline_s = 9.0`"* reads as though 43.5s is the bound on the
timeout path. It is not: `idempotent=False` narrows retries to `RateLimitError`,
so a connection timeout takes **one** attempt and the bound is **10.0s**. 43.5s
is reachable only on four consecutive rate limits.

**Cited by content, not by line** — it was at `:1627` when found and is at
`:1645` now, moved by B1 and B2. That drift inside one milestone is the
cite-by-content rule earning its place.

`CLAUDE.md` is **not** wrong here and needs no correction: it states 43.5s as the
worst case for a *write*, names `RateLimitError` as its measurement basis, and
already observes a write exceeds `D` *"with no retry at all."*

*Arming condition:* **whoever next edits `_sell_and_book`.** It was inside the
fence of every M5h task that touched the method.

---

## UNMEASURED — venue facts nothing in the tree can supply

**Provenance, stated plainly: these are counts from M5h's own log analysis, not
re-derived at this rotation.** `logs/trading_bot.log` is gitignored and rotates
at `backup_count: 5`, so the evidence may already be gone — which is
`CLAUDE.md`'s fifth drift surface behaving exactly as described.

### X1. No take-profit has ever filled — ~25 trades

Every completed trade closed by stop-loss or by the bot's own sell. The
take-profit leg has been *placed* many times and *observed resting*; it has never
been observed **executing**. So the `TAKE_PROFIT` branch of every consumer —
classifier, booking, close plan — is exercised only by fabricated fixtures.

### X2. `ALREADY_CLOSED` and `HALT` have never occurred — 33 closes

`plan_close` has three outcomes and 33 real closes produced only `SELL`. The
other two rows are pinned by unit tests over hand-built leg reports and have
never been produced by a venue.

### X3. `PLACED_TERMINAL` has never run

`resolve_placement`'s terminal verdict. `resolve_placement` itself has still not
run after every supervised run to date — it needs an *ambiguous* placement, and
none has occurred.

**The common shape, and it is the reason these are grouped:** each is a branch
the tree can only reach through a fixture, on a path where a fixture is a model
of the venue rather than an observation of it. `CLAUDE.md`'s warning applies
directly — *"a component that could not have failed was not confirmed."*

---

## BLOCKED — the trailing-stop milestone

**Still blocked, and the block is unchanged.** `advance_trailing_stop` has **zero
call sites in `src/`** — verified at this rotation, `risk/manager.py:601`, whose
own comment says so at `:623` — and is `trailing_stop`'s only writer there. So
what it writes is a level nothing places, amends or cancels at the venue.

The blocking question is unchanged: **does the trailing level rest at the venue,
or does it not exist?** Q-C §3 fixes the order list at three legs and none is a
trailing leg. Driving it before that is answered would produce a level no order
rests on — the client-side protection Q-C §1 rejected outright.

*Arming condition:* **whoever amends Q-C §3's leg set.** Not an event, and not a
milestone: a document change by the project owner.

---

## STRUCK AT THIS ROTATION — closed by M5h

Listed so the removal is auditable. `CLAUDE.md`'s mode 3 — *the condition fires
and nothing notices* — is what this section exists to prevent.

- **`M5f-087`: "`PendingPlacement` is unpersisted."** CLOSED. `store.py` carries
  `PendingRecord` and `PendingCloseRecord` and `StoredState.pending` holds both.
  This item had read as open *long after persistence landed*, which is mode 3
  caught by a rotation reading every condition.
- **`M5g`'s "nothing books a venue fill."** CLOSED at `4abab15`.
- **`M5g`'s "`close_position` has zero callers."** CLOSED — two now, and both
  named at each other.
- **`M5h-364`: `_drop_position_unbooked`'s justification false in-process.**
  CLOSED at B2, from both ends: the behaviour books where booking is possible,
  and the prose describes the three cases that now reach it.
- **`M5h-301`: the documented gate counts are stale.** CLOSED at this rotation —
  all four sites written from one fresh run.

---

## The rotation's own procedure — read `CLAUDE.md`, not this

The five steps live in `CLAUDE.md`'s **Git workflow** section and that file is
the authority. Two things it says that this rotation had to act on, recorded
here only as a pointer:

- **Step 4 — re-read the contracts under `docs/`** for prose the milestone
  superseded. It is the step most easily skipped, because the milestone that
  invalidates a paragraph is always editing a different file.
- **An arming condition names its CALLER, not an event** — and see U5 above for
  a case where naming a caller was still not sufficient.
