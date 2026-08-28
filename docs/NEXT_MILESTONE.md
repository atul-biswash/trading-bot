# Next milestone — M5h

Written at M5g's rotation. This file is the **only task authority** the next
session has: anything not carried here is lost, and the rotation that rewrites
it is what destroys it.

**M5g's rotation nearly proved that.** Step C found **four** rules living only
in this file — the finding-ID scheme, the milestone-paragraph re-tensing
convention, `M5f-091`'s "a rotation must READ every structural list against the
tree", and `M5f-094`'s "a check in the same command chain as the action it gates
is not a gate". Two of them were found only because the audit looked for the
*general case* rather than for the two items it had been told about. All four
now live in `CLAUDE.md`.

**So: rules belong in `CLAUDE.md`. This file holds open items and nothing
else.** If a future rotation finds a rule here, that is the defect, not the
rewrite.

---

## Before M5h starts — the namespace

**M5h's finding IDs are `M5h-001`, `M5h-002`, …** — the scheme is now stated in
`CLAUDE.md`'s rotation procedure rather than here, which is why this section is
three lines instead of fifteen.

**M5g's namespace is CLOSED at `M5g-134`**, verified over `milestone/M5f..HEAD`:
134 declarations, 134 unique, `M5g-001`–`M5g-134`, no gap and no duplicate. Do
not reuse an M5g identifier.

---

## THE CENTRAL FACT — read this before anything else

**M5g ran the bot four times. It placed three order lists, one of them filled
and was closed by the venue's stop-loss, the account realised
`-35.38691640` USDT — and NOTHING IN `src/` BOOKED IT.**

The mechanism, measured:

- `Portfolio.record_realised_pnl` has **exactly one call site**, inside
  `Portfolio.close_position`.
- `Portfolio.close_position` has **zero callers** in `src/`.
- So `realised_pnl`, the `free_quote` credit and the `del positions[...]` are
  **all unreachable**. The ledger can be opened and never closed.
- `realised_today` therefore returns `Decimal(0)` permanently, and the
  daily-loss check's expression is `realised_today(now) + committed`. **Its
  realised term is structurally dead: no number of stop-outs can move it.** It
  is a committed-risk limit wearing a daily-loss limit's name.

**The same gap swallows a take-profit fill and a manual exit at the venue** —
the classifier and `_refine` branch on `status is FILLED or filled_quantity > 0`
for every non-working leg, so all three land identically.

**What DOES happen** when a fill is seen: the leg classifies `UNKNOWN`, that is
written to `Position.protection`, a warning is logged, and committed risk
becomes uncomputable so further entries are refused. The bot halts — by the
wrong mechanism, for a wrong stated reason, and only in-process. **A restart
heals the balance sheet and erases the income statement**: equity is re-read
from the venue at boot, realised P&L is not, because nothing ever wrote it.

---

## THE CARRIED RISK — two of eleven, not eleven

M5f's entry listed eleven components never exercised in series against a venue.
Four runs have now exercised **nine**. Re-derived from the log:

| Component | Verdict |
|---|---|
| `classify_protection` | RAN — 81 passes `active=1` (run 2), 9 `unknown=1` (run 3) |
| `reconcile_open_positions` | RAN |
| `ReconciliationDriver` | RAN |
| `ACTIVE`'s admission to `_TRUSTED_PROTECTION` | RAN |
| `build_placement` | RAN — OTOCO, three placements |
| `DispatchBudget` | RAN |
| `OrderExecutor` dispatch + `Position` construction | RAN |
| `resolve_unresolved_legs` | RAN — run 3, 18 point queries |
| the L-leg reservation | RAN — spent to its exact limit, 2 of 2 |
| **`resolve_placement` / the executor's Option-4 resolution** | **NEVER RUN** |
| **`RefusalStage.POSITION_STALE`** | **NEVER RUN** |

**What would exercise the remaining two.**

- `resolve_placement` needs an **ambiguous placement** — a connection timeout
  on a write, so the executor cannot tell whether the list landed. Zero
  `placement_ambiguous` events across four runs. It cannot be provoked without
  either a fault injection seam or luck.
- `POSITION_STALE` needs a position whose stamp ages past
  `max_position_staleness_s` (180 s). Measured over run 2's 81 passes,
  inter-pass gaps were 60, 61, 119, 120 and 121 s — worst stamp age 121 s
  against a 180 s threshold. **The reconciler keeps it fresh by design, so the
  guard only fires when the pass itself stops running**, which no run has done.

*Arming condition, in caller terms:* neither is armed by a caller. Both are
armed by a **fault** the tree cannot currently produce on demand, and that is
the honest statement of why four runs did not reach them.

---

## What M5g left — the state of the tree

**Four runs, and two of them were nearly sealed out of the milestone.**

| Run | PID | Window | Outcome |
|---|---|---|---|
| 1 | *(pre-PID)* | ends 08-27 04:38 | dispatched; 28 passes read `diverged=1` — the D2 defect |
| 2 | 29608 | 08-27 17:10–19:19 | dispatched, filled, 81 passes `active=1`; exited by hand |
| 3 | 12008 | 08-27 23:15–23:29 | **dispatched, filled, stop-loss triggered, `-35.38691640` USDT** |
| 4 | 22484 | 08-28 03:23–03:44 | booted under the collapsed boot line; no dispatch |

Runs 3 and 4 happened between sessions and **no report in the milestone knew of
them** until a rotation step enumerated the log's pids and got three where it
expected one. Their entire record was `logs/trading_bot.log`, which is
gitignored.

**Confirmed by the runs:** D2's fix (81 passes `active=1` against the first
run's 28 `diverged=1`, which were the identifier-space defect and not
divergence); B2 and V2; the instance lock and the PID field; and the
excluded-holdings collapse — 501 boot lines became one, `excluded_count=501`, on
the same account.

**The account at M5g's close:** 17 order lists, all `ALL_DONE`; zero open
orders; BTC and ETH dust; USDT `91125.78688060`. Nothing rests.

---

## M5H'S SCOPE — ruled by the PROJECT OWNER

**Three pieces, and the ordering is forced rather than preferred.**

### 1. PERSISTENCE, first

`persistence/` is a stub, and it is implicated in **four** separate findings:

- `PendingPlacement` is an in-process dict, so a crash between an ambiguous
  write and the next candle loses the only record that a list may be resting
  (M5, below).
- A `Position` orphaned by a process death is invisible to
  `reconcile_open_positions`, which iterates `portfolio.open_positions`.
- B3 adoption is unavailable — nothing can re-adopt what a previous process
  held.
- **The unbooked realised loss above**: even a correct booking evaporates on
  restart without it.

### 2. EXIT BOOKING, on top of it

**Why the order is forced, not preferred:** booking without persistence yields a
daily-loss halt that resets every time the operator restarts the bot. That is
worse than no halt, because it **looks like a control**. Run 4 demonstrated the
amnesia empirically — it booted with the post-loss balance and no knowledge that
a trade had occurred.

**The first step is a measurement, not code.** See the exit-price item under
UNMEASURED.

**And the smallest change is wrong.** Booking at the requested trigger price
needs no measurement and under-reports the loss: run 3's trigger implies
`36.45` where the account moved `35.39`, and in a gapping market the gap grows.
A risk control may not err permissively.

### 3. `SignalAction.CLOSE`, after

The executor refuses `CLOSE` by name, so the bot cannot choose to exit. Run 2
demonstrated the cost: the strategy signalled CLOSE, BUY, CLOSE after entry —
a full round trip in its own view — while the ledger held one position
throughout. Strategies are edge-triggered, so those exits are gone rather than
deferred. Q-C §4b specifies the close path and it is unbuilt.

### Optional and independent

**M2's deliberate measurement** — whether terminated lists count against
`MAX_NUM_ORDER_LISTS` — on a **throwaway Testnet account**, so the answer is
bought rather than met at boot on this one. See M2 below.

---

## UNRULED — reserved to the project owner

None was armed by M5g: every arming condition below names a caller, and M5g
edited none of them.

### U1. `NOT_PLACED`: re-place, or drop? — `M5f-061`, `M5f-064`

`CLAUDE.md`'s locked rule says *"Not found ⇒ nothing rests; re-place at the same
generation."* The executor deletes the record and re-places nothing, so a signal
reported not-found is dropped — logged at ERROR as `dispatch_missed`, so
countable, but gone. **`NOT_PLACED` is an INFERENCE**, covering at least three
venue states the executor cannot distinguish. Strategies are edge-triggered, so
a dropped signal is gone rather than deferred.

*Arming condition, in caller terms:* **whoever writes the first `CLOSE` dispatch
or the first live-run change to `OrderExecutor.__call__`.** M5h's piece 3 is
that caller.

### U2. The venue-refusal half of e3-narrow — `M5f-083`

Client-side refusals create no pending record (`59cf256`). Venue refusals still
do, and still spend a resolver call next bar rediscovering what the exception
already said. Unruled because it rests on *"a 429 is rejected pre-acceptance"*,
which is REASONING rather than measurement.

*Arming condition:* **whoever next edits `dispatch`'s except chain.**

### U3. Whether to consume `orderReports` — `M5f-038`

**The premise is settled and the decision is not.** MEASURED: the placement
response carries `orderReports` with Q-C §7's complete compare set at no extra
call. The cost is that `OrderList` would hold two leg representations, or two
types would exist for one concept.

*Arming condition:* **the placement site in `OrderExecutor`**, the only thing
holding a placement response.

### U4. The per-call share — `M5f-009`

Measured worst cases are OTOCO **5**, OTO **4**, unprotected **1**,
recovery-bearing entry **3**. Whether the confirm step queries all three legs or
only the two protective ones decides 5 against 4. Annotated at twelve sites;
**do not annotate it again — a duplicate is permanent.**

*Arming condition:* **whoever first sets `timeout_s`/`attempts` from config**
rather than passing the derived bounds.

### U5. `BinanceRequestException`'s representation — `M5f-072`

It carries **no code**, and is raised only AFTER a 2xx when the body will not
parse — so for a placement it leans toward LANDED. `code=None` reads as
"client-side" to anyone trusting the `:param` line, which is wrong in the
dangerous direction.

*Arming condition:* **whoever first branches on `ExchangeAPIError.code` in
production.** Still nothing does.

### U6. Whether `OrderExecutor` implements the `OrderExecutor` port

`core/interfaces.py` declares a port taking an `OrderRequest`, describing one of
three placement outcomes. The class does not implement it.

*Arming condition:* **whoever needs to substitute the executor** — the paper
simulator, most likely.

### U7. Deleting `_CLOSE_SEQUENCE_CALLS` — `M5f-010`, `M5f-018`

Dead: one definition, zero readers, and its comment claims a consumer that does
not exist. It **anchors the `7aa8f59` annotation**, so removing it orphans or
deletes an annotation, which annotate-never-delete forbids. A precedent
decision, not a cleanup.

*Arming condition:* **whoever next edits `config/models.py`'s coherence block.**

---

## UNMEASURED

### X1. Does a triggered stop carry `average_price`? — `M5g-123`, `M5g-124`

**The first step of M5h's piece 2, and it is one observation.**

`Order` **already carries** `average_price`; `to_order` derives it as
`cummulativeQuoteQty / executedQty`. It has **zero readers in `src/`**, and
`_refine` — the one function that sees a protective leg fill — reads `status`
and `filled_quantity` and discards it.

So the question is narrow: **on a leg the venue TRIGGERED, does it populate
`cummulativeQuoteQty`, so `average_price` is non-`None`?** DOCUMENTED that
`GET /api/v3/order` returns the field; never observed here for a triggered leg,
and run 3 could not answer it because nothing read it.

*Arming condition, in caller terms:* **the next run that fills** — it needs a
live stop the venue triggers. The question is recorded in `_refine`'s own
docstring so it survives this file's next rewrite.

### M1. The `allOrderList` default page size — `M5f-066`, `M5f-068`

**UNREACHABLE READ-ONLY. Do not re-attempt a read-only probe.** A `limit` above
the default returns the same set, so the ceiling cannot be observed without
exceeding it. Bounded below at >= 17.

### M2. Whether terminated lists count against `MAX_NUM_ORDER_LISTS`

Measured: `MAX_NUM_ORDER_LISTS = 20`. The account now holds **17 lists, all
terminal**, up from 14 at M5f. **The count moved without anyone deciding to move
it, and it CANNOT BE REDUCED** — the venue's spot order-list surface is three
creates, one cancel of a *live* list, and three reads. There is no endpoint that
deletes history.

**Do not state a headroom figure** (`M5f-067` records a rotation stating "6 of
20" as fact). If terminal lists count, the boundary is near; if only live ones
do, it is far. Q-C already names the worse reading: *"one symbol on a 1-minute
bar reaches 20 in twenty minutes and fails at submission for a reason no code
path anticipates."*

*Arming condition:* **the next dispatching run**, whether or not anyone intends
it. This is the only item that arms by inaction. M5h's optional piece buys the
answer on a throwaway account instead.

### M3. Q-C §8's fourth row — placed, working leg filled, pendings live

**The state occurred TWICE and the row is still unmeasured** — the arming
condition fired and nothing noticed, which is failure mode 3 of the
arming-condition rules in `CLAUDE.md`. It is the row in which a re-place opens a
second unprotected entry, and the grounds for the fail-closed ruling. Obtaining
it needs a re-place attempted in that state, which no run did.

*Arming condition:* **whoever edits the recovery branch** — the same caller as
U1.

### M4. S5 — a filled list whose protection has since triggered — `M5f-037`

**Run 3 produced this state, and the reconciler handled it better than M4
feared.** M4 says separating it from the FOK-expired case *"needs a per-leg
`executedQty`"*; run 3's resolver produced exactly that, reporting
`executedQty 0.02257000` on the SL and `EXPIRED` on the TP via point queries.

**What remains unmeasured is narrower:** `resolve_placement`'s
`PLACED_TERMINAL` path, which has still never run.

### M5. `PendingPlacement` is unpersisted — `M5f-087`

**The one failure fail-closed structurally cannot bound.** A plain in-process
dict; a process death between an ambiguous write and the next candle loses the
only record that a list may be resting. **Now inside M5h's piece 1.**

---

## DEFERRED — known, decided not to act, each with why

- **`ExchangeAPIError`'s docstring enumerates "Two `src/` sites" and there are
  twenty** — `M5f-071`, `M5f-077`. Verified still saying two. Most of the
  eighteen are client-side and consistent with its spirit.
- **`code == 0` is the library's sentinel for an unparseable non-2xx body** —
  `M5f-078`. `418409f` forwards it as though it were a venue code. Binance has
  no code 0, and nothing in the tree records that.
- **`CLAUDE.md` says the mapping targets an order-list request for "three of the
  four branches"; the code and Q-C §2 both say TWO** — `M5f-020`. **Verified
  still uncorrected** at M5g's close, having been excluded from three
  consecutive rotations by their own scoping. It needs a home.
- **`test_ids.py`'s comment gives a false rationale** — `M5f-073`.
- **A stale claim propagated into a test docstring** — `M5f-030`.
- **`_REASON_UNPROTECTED` is emitted from two sites** — `M5f-053`. A redundancy,
  not a wrong signal.
- **`_matched_list_id`'s multiplicity guard is pinned by nothing** — `M5f-063`.
- **`install` and `install-dev` bypass `$(PYTHON)`** — `M5f-033`.
- **`model_copy(update=...)` skips the model validator of every frozen domain
  type** — `M5f-002`.
- **A test passes for a different reason than its name states** — `M5f-088`.
- **`reconciliation_pass`'s `queries=` field reports budget HEADROOM, not work
  done** — `M5g-085`, `M5g-116`. It is `max_calls - len(assessments)`, constant
  at 2 across every pass of both runs. **In run 2 it read 2 while zero queries
  were made; in run 3 it read 2 while exactly two were made** — accidentally
  correct, which inspection cannot catch.
- **The log records no fill price and no balance** — `M5g-087`. `order_placed`
  logs the LIMIT sent, never the fill. Run 3's realised loss is derivable only
  from two console readings, not from the artefact.
- **Testnet charges NO commission** — `M5g-082`. The entry debit was exactly
  `quantity x price`. `config.yaml` carries `fee_percent: 0.1` for `backtesting`
  and `paper_trading`; **whoever writes M5h's exit booking cannot validate a fee
  model here**, and must not read a clean Testnet round trip as evidence it
  works.

---

## Process debt with no instrument — carried

- **A justification going stale because nothing at its site re-checks the fact
  it rests on** — `M5f-011`. The rule is in `CLAUDE.md`; the debt is that
  instances keep arriving.
- **A `src/` docstring outliving its fact** — `M5f-029`, `M5f-086`. Eleven
  instances across two milestones. **The only systematic finder is the rotation,
  once a milestone.**
- **An open item declared in a commit message has no route into the task list**
  — `M5f-042`. Both of `CLAUDE.md`'s checks read commit messages and run the
  other direction. **This file is the route, and this rewrite is the only thing
  that exercises it.**
- **Nothing reconciles a mid-turn fix against a queued authorisation** —
  `M5f-056`.
- **No vocabulary for a measurement that upgrades confidence without moving a
  number** — `M5f-097`.
- **NOTHING NOTICES THAT A RUN HAPPENED** — `M5g-108`, `M5g-112`, `M5g-134`.
  `logs/trading_bot.log` is gitignored, the bot writes nowhere else, and a
  run's findings reach disk only if somebody looks. Two supervised runs were
  nearly sealed out of this milestone. The log rotates at `backup_count: 5`, so
  a longer deployment discards the evidence and any later check reports clean.
  **Recorded as a drift surface in `CLAUDE.md`; no mechanism is proposed, and
  that is the project owner's.**

---

## Carried from earlier milestones — still open

- **Finding I** — refuse a symbol whose tick is coarse relative to
  `max_entry_slippage`, at BOOT. *Arming condition:* `_prime_pairs`, which
  exists — armed now, merely unreachable on BTCUSDT/ETHUSDT.
- **Finding L** — `Portfolio(realised_pnl=...)` with `pnl_date=None` makes
  `realised_today` return zero, so a booked loss reads as zero. **Directly
  relevant to M5h's piece 2**: it is a second route to the same silence the
  central fact above describes.
- **Collapse the multi-statement writes** — `advance_trailing_stop` and
  `record_realised_pnl` each write twice; `CLAUDE.md` makes collapsing them a
  prerequisite for any `Position` model validator.
- **The trailing milestone** — `advance_trailing_stop` has zero call sites and
  is `trailing_stop`'s only writer. The blocking question is unchanged: *does
  the trailing level rest at the venue, or does it not exist?*
- **Q-C §7's site-3 defect** — needs a `ProtectionState` member no writer exists
  for.
- **Q-B site 4's escalation half** — `M5f-096`. **BLOCKED, not stale.**
  `CRITICAL` needs a halt flag on `Portfolio` that does not exist; N-cycle
  promotion needs cross-pass state the driver refused to hold. *Arming
  condition:* the halt flag's first writer.
- **The PLACEHOLDER numbers in `M5_NUMBERS.md`** — every mark stands. M5g moved
  none. Two annotations were added (the slippage observation, the staleness
  margin) and both explicitly decline to move their mark.

---

## Where the item numbers went — four test docstrings still cite them

Unchanged from M5f's rotation and **verified still present in `tests/`**. The
mapping is repeated because the citations are prose and rot silently.

| Cited as | Where it is now |
|---|---|
| `test_binance_client.py` — *"item 9"* | **DISCHARGED** at `cc1feb5`. |
| `test_reconciliation_pass.py` — *"item 13"*, the last-call reservation | The reservation **RAN** in run 3, spent to its exact limit. Carried above in the carried-risk table. |
| `test_risk_manager.py` — *"item 14"*, the staleness refusal | The REFUSAL landed at M5e and **has still never fired**. The ESCALATION half is BLOCKED under Q-B site 4. |
| `test_risk_manager.py` — *"P2"*, no port method may go uncalled | Honoured at M5f. Finding GG's rule, unchanged. |

**The lesson is the mechanism, not the mapping**, and `CLAUDE.md` already rules
that a document is cited by CONTENT for exactly this reason.

---

## The rotation's own procedure — read `CLAUDE.md`, not this

`CLAUDE.md` holds the steps, the extraction commands, the tag convention and the
rules rescued from this file at M5g. Nothing about the procedure is duplicated
here, deliberately: that duplication is what made the last rewrite dangerous.
