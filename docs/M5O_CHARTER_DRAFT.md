# M5o charter: platform and execution reliability hardening

**STATUS: DRAFT, until the project owner ratifies it.** Written at P159 on `main`, after the ledger commit `b534cb8` (HEAD at the survey: `0f78bb1`, the `milestone/M5n` tag commit). **Nothing in it is a ruling except the text quoted in section 1.** The items, their order, the tiers and the HALT conditions are the executing session's proposals, REASONED from the survey; section 7 lists the questions that are the owner's and decides none of them. The survey this rests on is `docs/RUN_LEDGER.md` section 84 (findings `M5o-001` to `M5o-019`); every `file:line` there is at `0f78bb1`.

Marks used below follow the repository's: MEASURED (observed in this tree or a capture), REASONED (derived, not observed), DOCUMENTED (rests on a stated source), UNMEASURED (named so that nobody infers it).

## 1. The owner's decision, verbatim

Recorded in `docs/PHASE_HISTORY.md` (the M5n entry), in `docs/NEXT_MILESTONE.md` (*M5o -- what is next*) and in `docs/M5N_CHARTER_DRAFT.md` section 29:

> Owner decision on M5n's N7 FAIL: I choose pure Option 1: Close M5n as FAIL at N7 (no OOS read), pause strategy research, and open the platform/execution reliability hardening milestone (clearing the S4 backlog: U12 REST backfill for feed holes, U10 partially executed protective legs, U13 unbooked trades after venue errors, and the two live-trading blockers: fee capture and base-asset netting). We will not run Option 3 (no exploratory Testnet paper-trading of C1).

**What that fixes, and nothing more (REASONED readings, the owner's to overrule):** five items, named by the owner as U12, U10, U13, fee capture and base-asset netting; strategy research is paused; no Testnet paper run of C1; and the live-trading block stays armed (the P159 prompt states it).

## 2. Objective and non-goals

**Objective.** Make the money path trustworthy before anything else is built on it: every fill the bot books or sizes from is read from the venue's own record, with its fee and the asset the fee is charged in; the candle buffer is repaired rather than only guarded; and the two preconditions the live-trading block names are built as far as a venue without a non-zero commission allows. **M5o builds what the block's preconditions name. It does not lift the block.** Lifting is N6, a separate owner decision.

**Non-goals, each a fence:**

1. **No strategy research.** No candidate, variant or window is evaluated; the reserved window `[2024-01-01, 2026-10-01)` stays unread by every M5n family; the cumulative trial ledger is carried (section 8) and not extended.
2. **No live trading.** `refuse_live_trading`, `LIVE_TRADING_BLOCKED_MESSAGE`, `Settings.binance_credentials` and the mode resolution in `Settings.__init__` and `_cmd_run` stay unedited. The block's arming condition (`CLAUDE.md`: whoever next edits the mode resolution or authorises a run in `TradingMode.LIVE`) is not met by any item below, and an item that would meet it halts.
3. **No change to any frozen S4 or M5n file.** The S4 side, by R-DT (`docs/M5N_CHARTER_DRAFT.md` section 12): the pre-registration and correction files, `scripts/s4_compare.py`, `scripts/s4_latch_compare.py`, `scripts/s4_wick_annotate.py`, `scripts/trade_census.py`, `config.s4.yaml`, everything under `deploy\45547f107715` and the rehearsal clone. The M5n side, by section 23 of that charter: `docs/M5N_PREREGISTRATION.md`, `src/trading_bot/backtesting/sharpe_stats.py` and `scripts/n7_evaluate.py` against their recorded digests. A file this list does not name but whose change alters a result a frozen tool reproduces counts as frozen for this purpose (section 6).
4. **No venue call that an item does not name, and none without the owner's authorisation at that item's start.** The survey itself made none. Reads and writes are named per item in section 4; a keyed read is not treated as lighter than a write for this rule.
5. **No write under any deploy or backtest clone.** The three clones awaiting retirement are the owner's steps (`docs/NEXT_MILESTONE.md`).
6. **No edit of `CLAUDE.md` locked-decision text** except where the owner rules it, as the S6 rule did. Items that would falsify locked text say so (`M5o-016`) and wait.

## 3. What the survey found

Six answers, each cited in `docs/RUN_LEDGER.md` section 84:

| Question | Answer in one line |
|---|---|
| (a) Fill path | The entry is read once by `get_order`, never retried, with no fee and no executed quantity used; a protective-leg fill is seen by reconciliation and settled by one `get_my_trades`; a close sale is a bounded sequence ending in the same settlement. A failed entry read leaves a position with no cost basis, which the close drops unbooked (`close_sold_unbooked`). |
| (b) Fees | The exit fee is captured per fill and netted; the entry fee is captured nowhere; every commission in every capture is zero; BUY commissions arrive in the base asset (128 of 128) and SELL commissions in the quote asset (178 of 178). |
| (c) Netting | One ordered quantity sizes the position, both protective legs, the exit and every comparison; nothing reads or predicts a base-denominated commission; the tree reads no commission rate. |
| (d) U10 | The rule is Q-C section 4b's (*"Treat as `CRITICAL`, halt entries, do not sell"*), enforced at eight sites; the booking blocker is the absent partial-close ledger operation, not fill measurement. |
| (e) U12 | `_append` cannot insert; the only REST read is the seed; a backfill must precede the first post-gap append, must not notify signal handlers and must heal the gap record. |
| (f) Testability | Testnet cannot show a non-zero commission or a hole or a partial expiry on demand; it can show denominations, the REST half of a backfill and, with an owner-authorised write, a base shortfall and an oversized stop. |

**The architect's hypothesis, tested** (*"U13, U10's booking and fee capture share one missing capability, trustworthy fill measurement; base-asset netting depends on fee capture; U12 is independent"*):

| Part | Verdict | Why |
|---|---|---|
| U13 and fee capture share a capability | **Holds**, narrower than stated | Both need a recoverable ENTRY settlement from `get_my_trades`; the exit side has the pattern (`settle_exit`) and the entry side has no twin (`M5o-001`, `M5o-002`, `M5o-018`). |
| U10's booking shares it | **Does not hold** | Partial legs' fills are settleable today (`core/portfolio.py:151-156`); the blockers are a partial-close ledger operation, the remainder policy and the venue's reason (`M5o-006`). |
| Netting depends on fee capture | **Holds in the verifying direction only** | Protection is placed in the entry's own call, so the net quantity is a prediction needing a commission-rate source the tree does not read; capture checks the prediction afterwards (`M5o-004`, `M5o-005`). |
| U12 is independent | **Holds in code, not in four places** | It shares the coherence budget, must keep repaired bars from signal handlers, bears on reconciliation's detection latency, and falsifies locked text (`M5o-010`, `M5o-016`). |
| Left out of the hypothesis | **A second cause of U13** | PIN-1 and R6 send a missing cost basis to a zero-call drop; whether re-reading the entry's fills is settlement or speculation is unruled (`M5o-017`). |

## 4. Items

**Tiers.** T1: Testnet-measurable (a read or an authorised write against the venue turns the claim MEASURED). T2: fixture or recorded-response only (a scripted fake or a captured payload; Testnet cannot produce the case). T3: reasoned (no instrument exists; the claim stays REASONED). An item carries the tier of each of its exit-evidence rows, because most carry two.

**Every item** is delivered in the repository's usual way: design before code and a stop for the owner's confirmation; predictions committed before any code or test is drafted (R-DQ); the bare gate before any commit that touches code or tests; a mutation survey in a disposable worktree; findings in the `M5o-NNN` namespace; and the arming register read for the symbols the item edits (section 6).

| Item | Scope (the owner's label) | Depends on | Venue touch it needs | Tiers |
|---|---|---|---|---|
| **H1** | Entry settlement: a recoverable entry-fill read | none | none beyond the existing `get_my_trades` and `get_order` | T1 happy path, T2 error path |
| **H2** | U13: unbooked trades after venue errors | H1 | none | T2 |
| **H3** | Fee capture: the entry commission and its asset recorded and persisted | H1 | a read of the account's commission rate is H4's, not H3's | T2, with T1 for the denomination only |
| **H4** | Base-asset netting in sizing and placement | H1, H3 | an owner-authorised shortfall probe (a write); a commission-rate read | T2 for arithmetic, T1 for venue behaviour |
| **H5** | U10: partly executed protective legs | none in code; schema coordination with H3 | an owner-authorised read of three terminal orders; optionally an authorised oversized-stop probe | T1 for measurement, T2 for the ledger operation |
| **H6** | U12: REST backfill for feed holes | none in code; shares the coherence budget with H1 | keyless klines with a start time | T1 for the REST half, T2 for the hole |

### H1. Entry settlement: a recoverable entry-fill read

- **Purpose.** The capability the survey found shared. A bounded `get_my_trades` for the working leg's order, summed by addition and never divided, into an entry twin of `ExitSettlement` carrying quantity, quote total, filled-at and the fee per asset, each amount paired with its asset (`Fee`). The read follows the existing `get_order` (`execution/executor.py:1456`) or replaces its role when that read fails. No port change is expected: `get_my_trades` is already declared (`core/interfaces.py:136`). **REASONED:** an entry settlement has one policy difference from `settle_exit`: it must accept a BUY and a base-denominated fee, where `settle_exit` refuses both (`core/portfolio.py:141-150`).
- **Exit evidence.** (1) A test per state of the settlement: fills sum to the executed quantity; no fills; fills short of it; a non-BUY fill; a fee in the base asset, the quote asset and a third asset, each kept paired. (2) A fixture reproducing `M5o-001`'s chain with the first read failing and a retry succeeding. (3) Testnet: on every supervised entry, the settlement's quote total equals `get_order`'s `cummulativeQuoteQty` in value and exponent, the standard `docs/RUN_LEDGER.md` section 26 held for six single-fill entries; **a multi-fill entry is not in that sample and is UNMEASURED.**
- **Tiers.** T1 for the happy path; T2 for the error path.
- **HALT.** The added call changes the dispatch sequence's longest call count, so the derived per-call share changes and `AppConfig`'s coherence check or `docs/M5_NUMBERS.md` stops agreeing with the shipped `config.yaml` (OR-10). Any need for a new port method. Any edit that gives a rung of `classify_bookability` a venue call.

### H2. U13: unbooked trades after venue errors

- **Purpose.** End `close_sold_unbooked` for want of a cost basis: recover it from H1's settlement, under whichever ruling OR-4 gives. **What it must not do:** reorder the ladder `A > P > C > Q` or give `PARTIAL_FILL` a venue call (the owner's Decision 1). The already-dropped trade (list 282240) is Testnet history; whether anything is back-filled is OR-4's.
- **Exit evidence.** (1) A fixture reproducing list 282240's chain (an `ExchangeAPIError` "Internal error" on the entry read, a later death-cross `CLOSE`) ends in a booking carrying its source, not in a drop. (2) The existing refusals still refuse: a partial sell makes zero calls; an unrecoverable basis still drops at CRITICAL. (3) A mutation survey over the new branches, in a disposable worktree outside the repository, with the unmutated baseline and the import location proven.
- **Tiers.** T2: Testnet cannot be asked to fail. A supervised session shows no regression on the happy path.
- **HALT.** A venue call at a rung the owner ruled zero-call, without a ruling. A change to the order of the ladder. The arming condition for U13 fires on any edit to the entry-fill read, the debit estimate in `_open_position`, or `_book_resolved_close` (`docs/NEXT_MILESTONE.md` U13); the commit resolves or reaffirms it.

### H3. Fee capture: the entry commission and its asset

- **Purpose.** Record, on every position, the entry commission and the asset it was charged in, as a `Fee`, persisted, restored at boot, and carried on the booking line. The ledger's entry-side rule follows OR-6. **REASONED, a Phase 1 question and not decided here:** for a base-denominated commission the quote cost basis is already what left the account, so the realised figure is net of it once the quantity sold is the quantity held (H4); the open design question is whether any further ledger subtraction is wanted, and what R-a (*"the ledger is net of exit fees and gross of entry fees"*) becomes.
- **Exit evidence.** (1) Every position, including a restored one, carries an entry fee or an explicit absence with its reason. (2) The persisted record's schema is bumped and a boot reads both the old and the new (the deployment procedure's schema step, `CLAUDE.md` C33 addition 2). (3) Arithmetic tests over derived non-zero commissions: rows of the `myTrades` capture whose SHA-256 is `111d1c15a3c5fff56148f172bfbcbec85baf5aabe2128f34fb622cafe5463970` with an INVENTED commission, labelled as invented in the test. (4) Testnet: the denomination of each new entry's commission (base asset) observed on every supervised entry, its amount zero.
- **Tiers.** T2 for the arithmetic; T1 for the denomination only. **The non-zero evidence the live block names is not obtainable on Testnet** (`M5o-012`), and no exit-evidence row may claim it. Closing the *gate* is U9's (OR-3).
- **HALT.** Any claim that a non-zero fee capture was established. A schema change without the schema step. A subtraction of a base-denominated fee from a quote figure (the denomination invariant). Any edit to `refuse_live_trading` or the mode resolution.

### H4. Base-asset netting in sizing and placement

- **Purpose.** The quantity that sizes the position, both protective legs and the exit is the quantity the account will hold: the ordered quantity less the expected base commission, rounded down to the step. Because protection is placed in the entry's own call (Q-C section 1), the net quantity is a PREDICTION made before any fill; H3's capture verifies it afterwards, and a mismatch has a defined consequence (OR-5, OR-9). The prediction needs a commission rate and the asset it is charged in, which the tree does not read (`M5o-005`).
- **Exit evidence.** (1) Sizing fixtures at several rates (including zero, which must reproduce today's quantities byte for byte) and at an invented non-zero rate: legs never exceed what is held, quantities stay on the step, no `float` crosses. (2) The boot test `free >= record.quantity` (`execution/restoration.py:592`), the classifier's quantity match (`execution/reconciliation.py:365`) and the completeness test (`execution/bookability.py:308`) each agree with the netted quantity. (3) Testnet, authorised: **a shortfall probe** that takes base out of the account between a fill and a trigger by an out-of-band sale, to MEASURE what the venue does with a protective leg and a sell larger than the base held, which `CLAUDE.md` lists as UNMEASURED. Whatever the venue answers is the evidence.
- **Tiers.** T2 for the arithmetic, T1 for the venue behaviour (a write), T3 for whether a BNB commission avoids the deduction (UNMEASURED; no account setting is read in the tree).
- **HALT.** An edit to the four-way placement branch or the leg types (`build_placement`'s arming condition: whoever edits it to place protective legs outside one order list). Any float in the rate path. The shortfall probe without the owner's authorisation, a written account state and a way to restore it. A change that makes zero-rate behaviour differ from today's.

### H5. U10: partly executed protective legs

- **H5a, measurement first.** An owner-authorised read-only GET of orders `1867449`, `5431129` and `7022204`, to see the type each is stored as and why each expired (deferred by P135 to U10); and, if the owner authorises a write, a deliberately oversized stop-market written to the thin Testnet book to reproduce a partial expiry on demand. **UNMEASURED and to be recorded either way:** the Testnet venue keeps only history since its last reset (`M5o-013`), so the three orders may not exist, and "not found" is then the finding. Also in scope: whether a `STOP_LOSS_LIMIT` leg bounds the fill and what it costs in exits that do not fill (U10's question; Q-C section 3 records `STOP_LOSS_LIMIT` as MEASURED at one algo slot, and nothing in the tree records its fill behaviour).
- **H5b, then the ledger and the policy.** A partial-close operation on `Position` and `Portfolio`, and the remainder policy of OR-1. **REASONED design to be tested in Phase 1, not decided:** keep the whole entry cost until the remaining quantity reaches zero, accumulate exit proceeds and fees by addition, and book `sum(proceeds) - entry total - fees` at the last exit. That is exact by summation and contains no quotient; a pro-rated cost basis would be a quotient, which the M5l ruling keeps out of the ledger.
- **Exit evidence.** H5a: the three orders' records, or a recorded not-found. H5b: fixtures reproducing the partial cases (9.9%, 46.6%, 16.6%) and the zero-executed case, each ending as OR-1 rules and with the ledger equal to the venue's fills to the last digit; the enforcement sites of `M5o-007` each have a test that fails when its rule is removed; entries are refused portfolio-wide no longer than OR-1 says.
- **Tiers.** T1 for H5a, subject to reset; T2 for H5b, with a supervised session because a natural partial expiry cannot be scheduled.
- **HALT.** Any path that sells against a partially executed protective leg that is still LIVE (Q-C section 4b stands for the live leg). Any H5b code before OR-1 is ruled. A venue write without authorisation. A `Position` or store schema change not coordinated with H3. The arming condition for U10 fires on any edit to `build_placement` or on a ruling on N6's preconditions (`docs/NEXT_MILESTONE.md` U10).

### H6. U12: REST backfill for feed holes

- **Purpose.** Close a gap rather than guard it. **Constraints from the survey (`M5o-010`):** it runs before the first post-gap `_append`, because older bars are dropped as stale (`data/market_data.py:487-488`); it reads the latest N bars and selects by `open_time` unless the port gains a start time (`core/interfaces.py:53-55`), and the REST read has its own bound and a term in the coherence budget, since it sits on the candle path; repaired bars enter the buffer and **do not** reach signal handlers, or an edge-triggered strategy signals on a cross inside the gap from a stale candle; the gap record is healed, or `bars_since_gap` keeps `BUY` refused; `CLOSE` stays unconditional. A keyless `startTime` klines fetch exists outside the port (`data/kline_recorder.py:201-209`), as a design reference and not a reusable component.
- **Exit evidence.** (1) Fixtures: a stream drop of 1 to k bars produces `bars_gap_detected` and then a contiguous, ordered, duplicate-free buffer; `bars_since_gap` returns `None` or a healed count; no signal is emitted for a repaired bar; a failed REST read leaves today's guard in force and logs it. (2) The coherence validator carries the new term and refuses a config that cannot afford it. (3) Testnet, keyless: a start-time klines read agrees with what the stream delivered for the same bars, over a window containing a natural hole if one occurs. (4) A mutation survey in a disposable worktree.
- **Tiers.** T1 for the REST half; T2 for the hole, which cannot be produced on demand.
- **HALT.** A change to `core/interfaces.py`'s `get_klines` or to `backtesting/replay.py` that alters a result a frozen S4 tool reproduces: the replay client answers the seed only (`backtesting/replay.py:112`), and R-DZ's gap rule makes the same demand of the backtest. Any edit of locked text without a ruling (OR-7). A REST call on the candle path with no bound. The arming condition for U12 fires on any edit to `_record_gap_if_any` that fetches bars or on a start time added to `get_klines` (`docs/NEXT_MILESTONE.md` U12).

## 5. Order and dependencies

The survey supports a partial order and not a total one:

- **H1, then H2 and H3, then H4**: one capability and its three consumers, in the order of what each needs. H4 also needs H3's capture to verify its prediction.
- **H5 and H6 are independent of the H1 chain in code.** H3 and H5 both change persisted `Position` state, so their schema changes are coordinated (OR-8); H1 and H6 both touch the coherence budget, so they are not built at the same time.

**Proposed linear order: H1, H2, H3, H4, H5, H6.** It follows the dependencies and then the owner's own listing order of the blockers. **The one reordering the survey supports:** H6 may move to second place. H3's closing evidence is gated by U9, H4 by the rate source and OR-5, and H5 by OR-1 and the authorisations, while H6 is gated by none of them; if rulings are pending, H6 is the item that can proceed. A reordering is the owner's.

## 6. Standing HALT conditions, every item

Each item also halts, and reports, on:

- a dirty working tree, or HEAD not being the commit its prompt names;
- any write under a deploy or backtest clone, and any frozen file differing from its recorded digest;
- any venue call the item does not name, or a named one the owner has not authorised at that item's start;
- code, a test or a script drafted before its predictions commit exists (R-DQ), or a code or test commit made without the bare gate green on that tree; docs-only commits are exempt;
- a diff over 1,500 changed lines, which is split and never waived;
- a mutation survey run anywhere but a disposable worktree outside the repository, or a result counted before the import location is proven;
- any edit to `CLAUDE.md` locked-decision text outside a ruling, to `refuse_live_trading`, or to the mode resolution;
- an arming condition that names a site the item edits and that the commit has not resolved or explicitly reaffirmed. The three the five items fire, by content: U13's (the entry-fill read, the debit estimate in `_open_position`, `_book_resolved_close`), U12's (`_record_gap_if_any` fetching, a start time on `get_klines`) and U10's (`build_placement`, N6's preconditions); `scripts/check_arming_conditions.py` lists them per document;
- the gate's own caveats: a count quoted with the credentials it was taken under, and never a piped run.

## 7. Open owner rulings, listed and not decided

Each is the owner's. The options are stated as they are known and none is recommended here. The items each blocks are in brackets.

- **OR-1. U10's remainder policy** [H5b]. After a protective leg expires partly executed, the remainder is unprotected and unsold. Under Q-C section 4b the bot halts entries, does not sell and waits for the owner. The three policies named: **sell** the remainder (a MARKET sell of the unexecuted remainder: the leg is terminal, so this is a different state from a close sequence against a live leg, which is a reading to be ruled and not assumed); **re-protect** it (a new order list for the remainder, which needs the generation counter nothing in the tree computes yet, the second-generation re-request of Q-C section 7, and the unmeasured behaviour of re-placement); or **hold** (today's fail-closed behaviour). A sub-question: whether the entry refusal stays portfolio-wide (`COMMITTED_RISK_UNKNOWN`) or is scoped to the symbol; it lasted about 43 hours in case 4.
- **OR-2. U10's gate status** [none blocks; it frames H5]. `docs/NEXT_MILESTONE.md` records that P98 lists U10 among the items that block live trading and the owner's P87 ruling says it is not a gate. Both cannot stand (`M5o-015`).
- **OR-3. How the fee-capture gate is met, and which wording governs** [H3's closing evidence, N6]. U9: a read-only mainnet key fetching existing trades, one minimum-size mainnet order, or rewording the gate. And the gate is worded two ways, *"a non-zero fee capture empirically established on a live-quoted venue"* (N6) against *"entry-fee deduction and base-quantity netting ... implemented in the sizing and placement pipeline"* (`CLAUDE.md`, `config/settings.py:34-39`); whether *capture* and *deduction* are one precondition is unsettled (`M5o-014`). M5o's non-goals exclude live trading and venue writes, so whether any mainnet read is in M5o at all is part of this.
- **OR-4. PIN-1 and R6 against a cost-basis recovery** [H2, H1]. PIN-1 ruled *"zero venue calls"* at the `NO_COST_BASIS` rung and R6 forbids a speculative query for an unbookable exit. Whether re-reading the entry order's fills is settlement accounting or speculation, whether it may be retried across bars and under what bound, and whether the already-dropped trade (list 282240) is back-filled or stays an operator record (`M5o-017`).
- **OR-5. A commission in an asset other than the base or the quote asset** [H3, H4]. Exits refuse a foreign-asset fee and hold the position (R2). For an entry the money rule in `CLAUDE.md` (a fee-aware ledger method enforces `fee_asset == quote_asset` or routes through an explicit converter, and refuses rather than assumes when it can do neither) still binds; a BNB commission cannot be netted from base, and the bot does not know in advance which asset the venue will charge. Refuse the entry, hold after the fill, or require a stated account setting. Also: what a mismatch between the predicted and the captured commission does.
- **OR-6. What happens to R-a** [H3]. *"The ledger is net of exit fees and gross of entry fees"* was ruled partial by fee SIDE on purpose. Once an entry fee is captured, does the ledger become net of both for new trades, and what of the stored history, which stays gross (a ledger partial-net by time rather than by side)?
- **OR-7. Locked text a backfill falsifies** [H6]. One sentence of `CLAUDE.md` (*"add every bar that never arrived because the feed dropped and the buffer does not backfill"*), and a REST call on the candle path under the *"a budget, not an abstinence"* bullet; whether the P91 pin-4 deferral is lifted by the owner's P158 decision alone, and who annotates (`M5o-016`).
- **OR-8. Persisted-state schema** [H3, H5b]. `Position` gains fields in both; whether that is one schema bump or two, and how the deployment procedure's schema step and `scripts/release_position.py` are served.
- **OR-9. The dispatch budget's call count** [H1, H4, H6]. The per-call share is derived by dividing `dispatch_deadline_s` by the longest sequence's call count (`CLAUDE.md`, *The dispatch deadline is its own field*); an added entry call, or a backfill on the candle path, changes the divisor or the coherence sum, and the shipped `D = 9.0` sits 0.25 s under its ceiling (`M5l-034`). Whether `D` or the coherence constants are re-ruled, and who rules them.
- **OR-10. Venue authorisations, per item** [H4, H5a, H5b, H6]. The commission-rate read, the shortfall probe, the read of the three terminal orders and any oversized-stop probe each touch the venue; the owner authorises each at its item's start, with the written account state to restore after a write.

## 8. Carried items

- **`M5n-274`** (tests-only, MEASURED at P156, REASONED as to cause): *"`tests/unit/test_s6_rehearsal.py` and `tests/unit/test_worktree_survey.py` start git repositories without `core.fsmonitor=false`, and stray `git fsmonitor--daemon` processes accumulate"* (18 at P156, two more at P157, ten more after P158's bare gate; `docs/RUN_LEDGER_M5N.md` section 112). The fix touches no `src/` or script. *Arming condition:* **whoever next edits `tests/unit/test_s6_rehearsal.py` or `tests/unit/test_worktree_survey.py`, or next finds a stray daemon before a survey or a run.** Unchanged and not fixed by this draft; P159 ran one bare gate and counts the daemons it leaves in the closing report.
- **The cumulative trial ledger**, carried by the owner's closing record (2): 223 distinct configurations evaluated in sample with a performance figure (S5's baseline 1, S6's sweep 216, M5n's six 6), by source in `docs/RUN_LEDGER_M5N.md` section 112. They are declared configurations and not independent trials; no effective N is estimated. **Any future research deflation must count it.** M5o evaluates no strategy, so it is carried and not touched.

## 9. What ratification does

On the owner's ratification, the DRAFT marker is lifted citing the ruling, the rulings of section 7 that were made are recorded verbatim in a section of this file, the items' order is fixed, and `docs/NEXT_MILESTONE.md` is rewritten for H1 by the rotation procedure. **Until then this file is an input to the owner's decision and is not an instruction to any later session.** The three pieces of pre-existing false text the survey found (`risk/manager.py:532-533`, and the string at `execution/reconciliation.py:322` and `:789`) are reported in the ledger and not edited by this draft; each is corrected by the item that edits its file.
