# M5n charter: volatility-scaled trend and breakout research on 4h and 1d bars

**STATUS: DRAFT, until M5m closes.** Written at P138, with HEAD at `8c3bc5c`, while S4 is still running. Nothing in it was a ruling except the text quoted in section 1, until P139 recorded the rulings of sections 3 and 11 and adopted R-DT (section 12); everything else is the executing session's proposal, marked PROPOSED, REASONED, UNMEASURED or OWNER where it is the owner's to fill. It edits no other file: not `docs/research/PROTOCOL.md`, not `docs/NEXT_MILESTONE.md`, no frozen S4 file and no code, and it reads no bar in `[2024-01-01, 2026-10-01)`. When M5m closes, the owner either ratifies this file (the DRAFT line is then replaced by a ruling and a date, in a commit of its own) or supersedes it.

**Amended at P139 (HEAD `543d379`).** The owner ruled D1 to D4 and the two open points of section 11 and adopted R-DT; sections 3, 11 and 12 record them. Sections 5, 7 and 13, the ordering note after the item table and the item table's N1, N2, N4, N5, N6 and N9 rows are corrected in place where those rulings made their text false, and each correction is listed in the commit message. **The DRAFT marker stays until M5m closes.**

**Amended at P140 on branch `m5n` (main at `ee8d485`).** Section 13 records the N2 venue-read authorisation, the cap of 6, the fee (pending confirmation), the step-6 procedure (drafted at N1), the order change (trade counts move from N2 to N3) and that R-DU's text was not supplied; sections 4, 11 and 14 and the N1, N2 and N3 rows and the ordering note are corrected where the order change made them false.

Marks used below follow the repository's: MEASURED (observed in this tree or a capture), REASONED (derived, not observed), DOCUMENTED (rests on a stated source), UNMEASURED (named so that nobody infers it).

## 1. The owner decision, verbatim

> "Continue into M5n (Volatility-Scaled Trend & Breakout Research on 4h/1d) with the live-trading block kept armed, ATR-scaled trailing stops replacing the fixed 2%/4% 1m-scale brackets, timeframe-scaled minimum trade floors, fee-share telemetry reported up front, and M5m-510 discharged before touching the unread [2024-01-01, 2026-10-01) out-of-sample window."

Four commitments follow from it besides the live block, in its order: ATR-scaled trailing stops in place of the fixed brackets; timeframe-scaled minimum trade floors; fee-share telemetry reported first in every report; and `M5m-510` discharged before any out-of-sample read.

## 2. Objective and non-goals

**Objective.** Find out, by a procedure fixed before it is run, whether a small set of volatility-scaled trend and breakout strategies on 4h and 1d bars has an edge that survives fees, a trade-count floor and one untouched out-of-sample read. The deliverable is a PASS or FAIL decision with its evidence, not a strategy to deploy. A FAIL is a complete result.

**Non-goals, each a fence:**

1. **No live trading.** `refuse_live_trading` and the live-trading block in `CLAUDE.md` stay armed and unedited. Entry-fee deduction and base-quantity netting stay unbuilt, and nothing in M5n builds them.
2. **No change to the live engine, executor, reconciler, risk manager or any `src/` path that the running bot loads.** Research code lives in `backtesting/`, `scripts/` and `docs/research/`. N9 is a design note and writes no code.
3. **No out-of-sample read before a single pre-registered candidate exists** (section 8), and none before `M5m-510` is discharged (section 9).
4. **No new venue write.** Venue reads happen only where an item names them (N2's kline verification) and only when the owner authorises that item.
5. **No edit of a frozen S4 file** or of the S4 pre-registration and correction files.

## 3. Decisions D1 to D4

**Ratified at P139 (HEAD `543d379`).** The draft first written at P138 carried no rulings: the prompt's field for them was an unfilled placeholder and defined only D1 (`M5m-706`, ARCHITECT-OWNED), and the draft's guess at what D2 to D4 meant was a different list from the owner's. **The guess is withdrawn.** The owner's rulings, as the P139 prompt states them:

> **D1** venue trailingDelta sized k x ATR / price at entry, resolved on the 1m path in the backtester.
> **D2** daily-return Sharpe with a stationary block bootstrap, timeframe-scaled trade floors as an admissibility gate.
> **D3** BTCUSDT and ETHUSDT only.
> **D4** code now, alongside S4 (overriding the architect's recommendation), under R-DT.

**D4 is an owner override of the architect's recommendation**, and is recorded as one. The recommendation was not to write M5n code while S4 runs; the owner ruled otherwise, and R-DT (section 12) is the condition on which the override stands.

**D1's rules, and the venue facts they rest on.** The owner read the public `exchangeInfo` on 2026-10-24, with no keys, for both `api.binance.com` and `testnet.binance.vision`. For BTCUSDT and ETHUSDT on both, the `TRAILING_DELTA` filter reads `minTrailingAboveDelta` 10, `maxTrailingAboveDelta` 2000, `minTrailingBelowDelta` 10 and `maxTrailingBelowDelta` 2000, in basis points (MEASURED, by the owner's read; this session did not repeat it and made no venue call). D1's rules, verbatim:

> **D1 rules** The trail is k x ATR / price at entry, converted to integer basis points by rounding down, and clamped to [10, 2000]; a clamp is counted in telemetry, and position size uses the clamped distance. The exit is a single trailing STOP_LOSS sell, not an OCO, with no take-profit unless a later ruling adds one. The backtester resolves the trail on the 1m path, updating the peak with each 1m high before testing that bar's low against it. The venue's activation semantics (with and without stopPrice) are read from the Binance API documentation at N4 and cited there before they are modelled.

**k is not fixed here.** It is chosen at N3 or N7, under R-DT and under the pre-registration of N1, never after a result on the window. Two readings the rules leave open are noted so nobody settles them by accident: the "price at entry" is the entry order's fill price in the backtest and its reference price in sizing, and the ATR is that of the candidate's own timeframe at the entry bar's close. Both are N4's to state and pin.

**The remaining commitments of section 1 are not renumbered.** Fee-share telemetry first in every report (section 6, N6) and the discharge of `M5m-510` before any out-of-sample read (section 9, N1) stand as commitments of the owner decision of section 1, not as D-numbered rulings. Trade floors enter D2 as an admissibility gate: a candidate below its timeframe's floor is not admissible, and the report says NOT MEASURED.

## 4. The power statement (REASONED, to be measured at N2)

The out-of-sample window is `[2024-01-01, 2026-10-01)`, which is 2.75 years. The statement below is derived, not observed, and it assumes the daily returns of a candidate behave as independent draws with finite variance; crypto returns have fat tails, volatility clustering and some autocorrelation, all of which make the real test weaker than this arithmetic (`M5m-705`).

- **Primary metric:** the annualised Sharpe ratio of daily returns (daily equity marked at `00:00:00Z`, returns taken on that series, annualised by the square root of 365). The null is Sharpe = 0.
- **Confirmation at t = 2.** Against that null the t-statistic is Sharpe x sqrt(years), so t = 2 needs Sharpe >= 2 / sqrt(2.75) = **1.21**. That is the least annualised Sharpe the window can confirm at t = 2: **roughly 1.2.**
- **A candidate whose true Sharpe is exactly 1.21 passes that test about half the time**, because the expected t-statistic is then exactly 2. For 80% power the expected t must be about 2.84, which needs a true Sharpe of about **1.71**. A real but modest edge (true Sharpe 0.5 to 1.0) is therefore not confirmable on this window; the single read can say PASS only for a strong edge, and a FAIL on it is weak evidence against a modest one.
- **Consequence for the design:** the window is a confirmation of a candidate chosen in sample, not a discovery tool; the in-sample stage (N7) carries the selection, and its selection power is bounded by the number of candidates tried (multiple testing), which is why the set is small and fixed (N3).
- **Trade floors are a gate, not a statistic.** A Sharpe from a handful of trades measures nothing, so a candidate below its timeframe's floor is reported NOT MEASURED, not FAIL and not PASS. The floors scale with the timeframe because a 1d strategy makes fewer decisions per year than a 4h one. **Their values are UNMEASURED:** N3 counts the trades each candidate makes in sample (moved from N2, section 13) and the floors are proposed from those counts; where they are pinned is OPEN (section 13 point 6), and they are pinned before any candidate is evaluated.

## 5. Dependency on the S4 result

S4 compares the backtester against what the live bot booked over `[W, M)`. M5n relies on the same backtester and fill model, now with a trailing exit and 4h and 1d bars, so what S4 says about the fill model bears on how much weight M5n's costs and fills can carry. The charter proposes the following; each branch is the owner's to rule when S4's result exists (`docs/S4_STOP_RUNBOOK.md`, step 9, is where the result is written).

| S4 outcome | What M5n does (PROPOSED) |
|---|---|
| **PASS** | Proceed with the backtester's fill model as validated for the 1m scale. N4 extends it to a trailing exit and states that the trailing path is not itself validated by S4. |
| **FAIL (fill-model cause)** | N0 records the cause. N4's code, which D4 and R-DT allow to be written on branch `m5n` during S4, is not merged into `main` until the fill-model defect is fixed and the code revised against it, or the owner rules that M5n's results are reported with that defect named and bounded. |
| **FAIL (latch-caused)**, per R-DK | The fill model is neither impugned nor demonstrated. Proceed as for PASS, with the latch named in every report that leans on the backtester's fills, and with E1 and E2 as the figures that bear on it. |
| **NOT MEASURED** (fewer than 100 bookings at the cap) | Fidelity is not demonstrated. Proceed only if the owner rules so; every M5n report then carries "fill model unvalidated at S4". |

The owner decision of section 1 already says to continue into M5n. These branches say what continuing means under each result, not whether to continue.

## 6. Fee telemetry definitions

Reported first in every M5n report, before any Sharpe, return or drawdown. All figures are in the quote asset and exact (`Decimal`); a ratio is rendered with its numerator and denominator beside it. The fee rate is the one `docs/research/PROTOCOL.md` section 3 states and is not restated here.

| Name | Definition |
|---|---|
| `round_trip_fee` | Entry notional x fee rate + exit notional x fee rate, per trade. Both sides are charged in the backtest; the live ledger is gross of entry fees (ruling R-a), so a backtest-to-ledger comparison names that gap. |
| `gross_pnl` | Exit proceeds less entry cost, before any fee. |
| `fee_share` | Sum of `round_trip_fee` over sum of `gross_pnl`, reported only when the gross sum is positive; otherwise the line reads `n/a (gross <= 0)` and the fee total is still printed. A fee share above 100% means the strategy loses money net of fees whatever its gross edge. |
| `fee_bps_per_trade` | `round_trip_fee` / entry notional, in basis points. The least average gross move per trade that breaks even. |
| `breakeven_gross_bps` | Mean of `fee_bps_per_trade`, set against the candidate's mean gross move per trade in basis points. |
| `turnover` | Sum of entry and exit notional over mean equity, per year. |
| `mean_hold_bars` | Mean holding period in bars of the candidate's own timeframe. |
| `trade_count` | Count of closed round trips, beside the timeframe's floor and a PASS/BELOW-FLOOR word. |

Slippage is a separate, named line, never folded into the fee. **UNMEASURED:** whether the fee rate PROTOCOL fixes is the rate a 4h or 1d strategy pays on the venue's own tiers.

## 7. Bar construction and its verification

4h and 1d bars are built from the 1m store, never fetched as the research series.

- **Construction (PROPOSED):** UTC-aligned buckets (4h at `00, 04, 08, 12, 16, 20`; 1d at `00:00:00Z`). Open = the first 1m open, high = the maximum 1m high, low = the minimum 1m low, close = the last 1m close, volume and quote volume = sums, all `Decimal`, no rounding. A bucket missing any of its 1m bars is **flagged and excluded**, never filled and never interpolated, and the count of excluded buckets is reported per symbol and timeframe.
- **Verification:** against the venue's own 4h and 1d klines, exact equality on open, high, low, close and volume, mismatches listed in full, not summarised. This is a venue read (public klines) and is N2's only one, run only when the owner authorises it.
- **The verification must not read the out-of-sample window.** Comparing bars in `[2024-01-01, 2026-10-01)` against venue klines is a read of those bars. So N2 verifies on an in-sample span only, the construction code is frozen by digest before N8, and at N8 the out-of-sample bars are built by that frozen code and checked as part of the single read, with a mismatch reported and not repaired. **Ruled at P139 (section 11):** bar verification is in sample only, and the out-of-sample check is part of N8's single read. The venue read itself is still authorised per item, at N2.
- **UNMEASURED:** the extent of the 1m store, the span of its gaps, and which store N2 builds from. N2's first act is to name the store and its digest.

## 8. The out-of-sample single-read rule (PROPOSED)

1. **One candidate.** A single candidate, with its parameters, is pre-registered before the window's first bar is read: its declaration is hashed, and the freeze entry (PROTOCOL section 6 step 6, as amendment 4 rules it) is pushed before the read.
2. **One run.** The candidate is run once on the window. The result is reported whatever it is: PASS, FAIL or NOT MEASURED (below the floor). No parameter, bar construction, fee or fill change follows the read.
3. **Every access counts.** Any tool reading any bar in the window, including the bar verification of section 7, a descriptive statistic or a plot, is a read, and each is recorded in a read ledger (who, what, when, which bars) before the next. A read nobody recorded is a breach, not a convenience.
4. **No second read of the same window for a different candidate.** A second candidate would need a new window, which does not exist, so the window is spent by the first read.
5. **The window's bars are never opened by an exploratory script.** Anything in `scripts/` that takes a date range refuses a range that overlaps the window unless it is the N8 runner.

## 9. M5n discharges M5m-510 by PROTOCOL amendment 4

`M5m-510` (`docs/NEXT_MILESTONE.md`, carried at P121) records that `docs/research/PROTOCOL.md` section 6 step 6 describes a step ruling R-CV leaves uncarried, and its arming condition is: whoever next makes an out-of-sample read of the reserved window, or edits PROTOCOL.md, **asks the owner first** whether step 6 stands, is amended or is superseded for that read.

The charter's route is **PROTOCOL amendment 4**, a commit that edits PROTOCOL.md, names the section and the reason, and precedes every run it could affect (PROTOCOL section 10). The amendment series so far is 1 (P113), 2 (P117) and 3 (P119), so the next is 4. It is **written after M5m closes** (N1), not here, because this draft must not touch PROTOCOL.md, and because the arming condition requires asking the owner before the edit; that question is asked at N1 and again at any out-of-sample read.

## 10. Items

Each item ends with exit evidence and HALT conditions. Every item also halts on a dirty tree, on HEAD not being the commit its prompt names, on any write under `deploy\45547f107715`, and on a frozen file differing from its digest. An item that would touch a venue or the window states so and waits for the owner.

| Item | Scope | Exit evidence | HALT |
|---|---|---|---|
| **N0** M5m close-out and S4 result intake | Read S4's result (step 9 of the runbook), record which section 5 branch applies, close M5m's open items, and tag the milestone. | The branch of section 5 named with the S4 figures beside it; `milestone/M5m` resolves to the closing commit; the carried items listed. | S4's result is absent or NOT MEASURED without an owner ruling on section 5. |
| **N1** PROTOCOL amendment 4 and the M5n pre-registration template | Discharge `M5m-510`; fix the candidate set's size cap, the trade floors (from the counts N3 measures; where they are pinned is OPEN, section 13 point 6), the primary metric (D2: daily-return Sharpe), the stationary block-bootstrap's block-length rule, the fee telemetry, the read ledger and the rule by which k (D1) is chosen. **The amendment (or the item that pins them) states that the floors were pinned after the trade counts were seen**, and what those counts were, so nobody reads them as set blind. | The amendment committed; the template committed; the owner's answer on step 6 quoted verbatim; the counts the floors rest on named. | The owner has not answered `M5m-510`'s question; any N2 to N8 run exists before the amendment. |
| **N2** 4h and 1d bars from the 1m store, verified (N2a, P140; the trade counts moved to N3, section 13) | Build the bars (section 7); verify against the venue's public mainnet klines on an in-sample span, `[2017-08-17, 2024-01-01)`. BTCUSDT and ETHUSDT only (D3). **Under R-DT clause 3 N2 prints bar-verification results and nothing else on recorded data, and persists no trade list carrying prices; it computes no return, P&L, equity or metric until N0 records the S4 result.** | The store named by digest; the bar-construction code frozen by digest; zero mismatches or the full list; incomplete-bucket counts. The power statement (section 4) is re-derived from the measured daily-return variance **after N0, not in N2**, because computing that variance is computing a return on recorded data. | Any bar read in `[2024-01-01, 2026-10-01)`; the venue read is not authorised; a mismatch the construction cannot explain; any figure other than a count or a verification result printed or stored from recorded data before N0. |
| **N3** Indicators and a fixed, small set of candidates | Hand-written ATR, channel and trend indicators (no `pandas-ta`); the candidate set (volatility-scaled trend, breakout), its parameters and its size fixed by N1's cap (ruled at P140: 6). **The in-sample trade counts per candidate and timeframe are measured here** (moved from N2, section 13), so the floors can be set from a measurement; where they are pinned is OPEN (section 13 point 6), and until the owner extends R-DT clause 3 no count is printed on recorded data. | The set listed with its parameters and a digest; indicator tests pass; the NaN warm-up contract holds; no more than 6 candidates. | A candidate is added after N1; an indicator mutates its input. |
| **N4** ATR trailing exit in the backtester, per D1, resolved on the 1m path | The D1 rules of section 3, as ruled: a single trailing `STOP_LOSS` sell (no OCO, no take-profit), the trail in integer basis points from k x ATR / price at entry, rounded down and clamped to [10, 2000], clamps counted in telemetry, sizing from the clamped distance. The backtester updates the peak with each 1m high **before** testing that bar's low against the trail, so a trail is hit intrabar as it would rest at a venue. (This replaces the P138 draft's bar-close update of the stop level, which was not the ruled mechanism.) **First act: read the Binance API documentation for `trailingDelta` activation with and without `stopPrice`, and cite it in the item's commit before anything is modelled.** Fill conventions follow `backtesting/fill_model.py`, read first. | The activation semantics cited from the documentation, each claim marked DOCUMENTED; a trail that the 1m path crosses fills at the trigger or at the gapped open, per the fill model; tests for the high-before-low order on one bar, the clamp at both bounds and its count, round-down of the basis points, sizing from the clamped distance, and a never-moves-against rule; exercised on synthetic fixtures only until N0 (R-DT clause 3); the live engine untouched. | The change needs a `src/` path the live bot loads; S4 branch FAIL (fill-model cause) is open at the time of any merge into `main`; the documentation does not settle an activation case the model needs. |
| **N5** ATR risk-based sizing and the trade floors | Quantity from risk per trade over the **clamped** trailing distance (D1 rules), rounded down to the step; the floors of N1 as a gate that yields NOT MEASURED. | Sizing tests with exact `Decimal` assertions; a candidate below its floor reported NOT MEASURED in a test. | A float enters a money path. |
| **N6** Metrics | Daily-return Sharpe, a stationary block bootstrap of it (D2; the block-length rule from N1), and the fee telemetry of section 6, first in the report. | The metric functions pinned by tests against hand-computed values; the telemetry table rendered first. | The bootstrap's block rule is chosen after a result is seen. |
| **N7** In-sample walk-forward, selection and the S6-style null check | Walk-forward over in-sample only; select by N1's rule; run the null machinery of `scripts/s7_null.py`, adapted, to price the multiple testing. | The selection recorded before the null is run; the null's output committed; one candidate named, or none. | Any window bar read; a selection changed after the null. |
| **N8** A single OOS read of one pre-registered candidate | Section 8 entire. | The freeze entry pushed first; one run; the read ledger; the result with its fee telemetry first. | Section 8 is not satisfiable; M5m-510 is open; the freeze is unpushed. |
| **N9** Live-path design note only | How an ATR trail would rest at the venue (`trailingDelta` mapping, D1). **Testnet supports `TRAILING_DELTA` with the same bounds as mainnet (owner read of 2026-10-24, section 3), so the note needs no Testnet caveat for the filter itself.** That is a statement about the filter, not about an order: whether Testnet accepts a trailing `STOP_LOSS` and how it activates stay UNMEASURED until an order is placed, which is not this item. No implementation, no venue call. | A note under `docs/` marking each claim DOCUMENTED, REASONED or UNMEASURED. | Any code for it; any claim that Testnet accepts or activates a trailing order without a measurement. |

N0 and N1 are sequential and gate everything else. N2 gates N3 to N7. N8 needs a candidate from N7. N9 is independent and may be written any time after N0. **N2's bar verification is the one run on recorded data that R-DT clause 3 allows before N0.** **These orderings govern runs on recorded data.** Under D4 and R-DT the code of N2 to N6 may be written on branch `m5n` while S4 runs and is exercised on synthetic fixtures only until N0 records the S4 result; nothing from it merges into `main` before the `milestone/M5m` tag.

## 11. The owner's points, answered at P139 and still open

The P138 draft listed five points the owner had to answer before ratification. Their state:

| Point | State |
|---|---|
| 1. D1 to D4 | **Answered**, section 3. D4 is an owner override of the architect's recommendation. |
| 2. Which section 5 branch applies | **Open** until S4's result exists; N0 records it. |
| 3a. Does the N8 bar check count as part of the single read | **Answered:** bar verification is in sample only, and the out-of-sample check is part of N8's single read. |
| 3b. Is N2's venue read authorised | **Answered at P140** (section 13 point 2): public mainnet `/api/v3/klines`, keyless, `[2017-08-17, 2024-01-01)`. |
| 4. Candidate cap, fee rate for 4h and 1d, `M5m-510`'s step 6 | **Cap answered at P140: 6. Fee: 0.10% per side taker, PENDING OWNER CONFIRMATION.** Step 6 is drafted from source at N1. The bootstrap is ruled (D2: stationary block bootstrap); its block-length rule is N1's. |
| 5. Trade floors | **Answered, then reopened at P140:** measured as counts and pinned after the counts were seen. The counts moved from N2 to N3, so *pinned at N1* can no longer hold as written; where they are pinned is OPEN (section 13 point 6). No value is stated in this file. |

## 12. R-DT: M5n code during S4

The owner's rule, adopted at P139, verbatim:

> **R-DT** M5n code may proceed during S4 only if: (1) it changes no pre-registration frozen file, neither P137-frozen tool, nothing under deploy\45547f107715 and nothing in the rehearsal clone; (2) it is committed on branch m5n and merged into main only after the milestone/M5m tag, by a merge commit carrying a Findings block; (3) until N0 records the S4 result, it is exercised on synthetic fixtures only, and nothing computes or prints a return, P&L, equity or metric on recorded data, except that N2 may print trade counts and bar-verification results and persists no trade list carrying prices; (4) no bar in [2024-01-01, 2026-10-01) is read; (5) its findings use the M5n-NNN namespace.

Readings the executing session records so they are not settled by accident. Each is the owner's to overrule.

1. **R-DT governs M5n code.** This charter and its later amendments are documents and are committed on `main` as M5m documents, with `M5m-NNN` findings, until the owner rules otherwise. The first `M5n-NNN` finding is declared by the first commit on `m5n`.
2. **The P137-frozen tools** are `scripts/s4_latch_compare.py` and `scripts/s4_wick_annotate.py`; their digests are in `docs/S4_STOP_RUNBOOK.md`. Clause 1 also keeps `scripts/s4_compare.py`, `scripts/trade_census.py` and `config.s4.yaml` unchanged, which the S4 pre-registration already requires.
3. **Clause 3's exception is for counts and verification results.** N2 may print a count of trades, a count of excluded buckets and a bar-verification result; a mean, a variance, a drawdown or a price per trade is not one of those.
4. **Clause 2 needs a tag that does not exist yet.** `milestone/M5m` is created at M5m's rotation (CLAUDE.md, rotation step 5), so nothing from `m5n` merges before that.

**The findings namespace needs no tool change (read-only check at P139).** `scripts/check_findings.py` takes the id prefix as its second argument and builds both its citation pattern (`M5n-\d{3}`) and its declaration pattern (`^- (M5n-\d{3}) -- `) from it, so each invocation audits one prefix's declared, distinct, duplicate, gap and cited-not-declared figures alone, and an `M5n` run counts nothing that an `M5m` run counts. Run over `milestone/M5l..HEAD` with prefix `M5n` it reports 0 declared, no gap and no duplicate, which is the correct state before the first finding. Two properties to know when it is used for M5n: the prefix is **one per invocation**, so M5n is audited by its own run; and its **blockless check is range-wide and ignores the prefix**, so every commit in the range must carry a Findings block, which is why clause 2 requires the merge commit to carry one (the owner's `934eb45` is the one blockless commit in the `M5l` range and fails any run over it). For a range that starts at the M5m tag, the invocation is `check_findings.py milestone/M5m..m5n M5n` before the merge and `milestone/M5m..HEAD M5n` after it. No item N0a is therefore added.

## 13. Rulings recorded at P140: R-DU, the N2 venue read, the cap, the fee, step 6 and the order change

Recorded on branch `m5n` at P140 (main at `ee8d485`). Each item says what the P140 prompt gave and what it did not.

1. **R-DU (the S4 outcome branches): the ruling's text was NOT supplied.** The P140 prompt names R-DU and its subject, the S4 outcome branches (section 5), and asks for it *verbatim*, but the prompt does not contain it. This file therefore records that R-DU exists and what it is about, and does not quote it, the limit `M5m-683` and `M5m-699` record for rulings whose words did not arrive. Section 5's table is still the P138 PROPOSED text and is **not** stated to be R-DU's. **OWNER: supply R-DU's text; it is added here verbatim, in a commit of its own, and section 5 is then corrected against it.** (`M5n-002`, ARCHITECT-OWNED, MEASURED against the prompt.)
2. **The N2 venue read is authorised**, for exactly this: public mainnet `GET /api/v3/klines`, keyless, for `[2017-08-17, 2024-01-01)`, through `scripts/n2_verify_bars.py`, rate-limited, with the raw responses and their SHA-256 saved to scratch. It sends no key and targets nothing else. This answers section 11 point 3b.
3. **The candidate cap is 6** (N1). This answers the cap in section 11 point 4.
4. **The fee is 0.10% per side, taker, PENDING OWNER CONFIRMATION.** It is recorded as the working figure and is not pinned; N1 pins it once confirmed. The rest of section 11 point 4 (`M5m-510`'s step 6) is below.
5. **`M5m-510`'s step-6 procedure** is *"drafted from source at N1"*: the prompt supplies no text for it, so none is recorded here. N1 drafts it from `docs/research/PROTOCOL.md` section 6 and asks the owner whether step 6 stands, is amended or is superseded.
6. **The order change: the trade counts move from N2 to N3.** Trade counts need candidates, and candidates exist at N3, so N2 is now the bars and their venue verification (this slice is called N2a) and the counts are N3's. Two consequences the move leaves unanswered, and which are the owner's: **(a)** section 11 point 5 says the floors are *pinned at N1 after the counts were seen*, but N1 precedes N3, so the counts do not exist when N1 runs; where the floors are pinned is OPEN. **(b)** R-DT clause 3's exception names *N2* printing trade counts; with the counts at N3 the exception's wording does not reach them until the owner extends it, so **until then N3 prints no count on recorded data either**, and the clause is unedited because it is the owner's verbatim text.
7. **Branch and documents.** This amendment is committed on `m5n`, as the prompt says, and not on `main`; reading 1 of section 12 (charter documents commit on `main`) is superseded for this commit by that instruction. The first `M5n-NNN` finding is declared here.

## 14. What this draft does not do

It reads no bar in the reserved window and no 1m bar at all; it makes no venue call and runs no backtest; it fixes no number that a measurement should fix; it does not decide S4; and it does not touch the live-trading block. Its estimate of power is arithmetic, and the first thing done with it, after N0 records the S4 result, is to check it against the data.
