# M5n charter: volatility-scaled trend and breakout research on 4h and 1d bars

**STATUS: DRAFT, until M5m closes.** Written at P138, with HEAD at `8c3bc5c`, while S4 is still running. Nothing in it is a ruling except the text quoted in section 1; everything else is the executing session's proposal, marked PROPOSED, REASONED, UNMEASURED or OWNER where it is the owner's to fill. It edits no other file: not `docs/research/PROTOCOL.md`, not `docs/NEXT_MILESTONE.md`, no frozen S4 file and no code, and it reads no bar in `[2024-01-01, 2026-10-01)`. When M5m closes, the owner either ratifies this file (the DRAFT line is then replaced by a ruling and a date, in a commit of its own) or supersedes it.

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

The prompt that asked for this draft says *"Owner rulings on D1-D4: <OWNER: accept all / overrides>"*. **That field was an unfilled placeholder, and the prompt does not define D2, D3 or D4.** The only tie it makes is that N4's ATR trailing exit is resolved *"per D1"*. So this draft does not invent rulings and does not assign content to D2 to D4 as though it were known (`M5m-706`, ARCHITECT-OWNED, MEASURED against the prompt's text).

What it does is list the four commitments of section 1 as the probable content, and say which is tied:

| Probable label | Commitment | Tied by the prompt? | Where it lands |
|---|---|---|---|
| D1 | ATR-scaled trailing stop replaces the fixed 2%/4% brackets, resolved on the 1m path | **Yes**, N4 says "per D1" | N4, N5 |
| D2? | Minimum trade floors scale with the timeframe | No | N2 measures, N1 pins, N5 and N7 gate |
| D3? | Fee-share telemetry is reported first in every report | No | section 6, N6 |
| D4? | `M5m-510` is discharged before any out-of-sample read | No | section 9, N1 |

The labels D2 to D4 in that table are REASONED and unconfirmed. **OWNER: confirm the mapping, or supply the rulings, before this draft is ratified.** Where the owner's rulings differ from the commitments above, the rulings win and this section is rewritten.

## 4. The power statement (REASONED, to be measured at N2)

The out-of-sample window is `[2024-01-01, 2026-10-01)`, which is 2.75 years. The statement below is derived, not observed, and it assumes the daily returns of a candidate behave as independent draws with finite variance; crypto returns have fat tails, volatility clustering and some autocorrelation, all of which make the real test weaker than this arithmetic (`M5m-705`).

- **Primary metric:** the annualised Sharpe ratio of daily returns (daily equity marked at `00:00:00Z`, returns taken on that series, annualised by the square root of 365). The null is Sharpe = 0.
- **Confirmation at t = 2.** Against that null the t-statistic is Sharpe x sqrt(years), so t = 2 needs Sharpe >= 2 / sqrt(2.75) = **1.21**. That is the least annualised Sharpe the window can confirm at t = 2: **roughly 1.2.**
- **A candidate whose true Sharpe is exactly 1.21 passes that test about half the time**, because the expected t-statistic is then exactly 2. For 80% power the expected t must be about 2.84, which needs a true Sharpe of about **1.71**. A real but modest edge (true Sharpe 0.5 to 1.0) is therefore not confirmable on this window; the single read can say PASS only for a strong edge, and a FAIL on it is weak evidence against a modest one.
- **Consequence for the design:** the window is a confirmation of a candidate chosen in sample, not a discovery tool; the in-sample stage (N7) carries the selection, and its selection power is bounded by the number of candidates tried (multiple testing), which is why the set is small and fixed (N3).
- **Trade floors are a gate, not a statistic.** A Sharpe from a handful of trades measures nothing, so a candidate below its timeframe's floor is reported NOT MEASURED, not FAIL and not PASS. The floors scale with the timeframe because a 1d strategy makes fewer decisions per year than a 4h one. **Their values are UNMEASURED:** N2 counts the trades each candidate family makes in sample and proposes them; N1 pins them before any candidate is evaluated.

## 5. Dependency on the S4 result

S4 compares the backtester against what the live bot booked over `[W, M)`. M5n relies on the same backtester and fill model, now with a trailing exit and 4h and 1d bars, so what S4 says about the fill model bears on how much weight M5n's costs and fills can carry. The charter proposes the following; each branch is the owner's to rule when S4's result exists (`docs/S4_STOP_RUNBOOK.md`, step 9, is where the result is written).

| S4 outcome | What M5n does (PROPOSED) |
|---|---|
| **PASS** | Proceed with the backtester's fill model as validated for the 1m scale. N4 extends it to a trailing exit and states that the trailing path is not itself validated by S4. |
| **FAIL (fill-model cause)** | N0 records the cause. N4 does not start until the fill-model defect is fixed or the owner rules that M5n's results are reported with that defect named and bounded. |
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
- **The verification must not read the out-of-sample window.** Comparing bars in `[2024-01-01, 2026-10-01)` against venue klines is a read of those bars. So N2 verifies on an in-sample span only, the construction code is frozen by digest before N8, and at N8 the out-of-sample bars are built by that frozen code and checked as part of the single read, with a mismatch reported and not repaired. **OWNER: confirm that the N8 check counts as part of the one read** (it does on the reading above; the alternative is no check on the window at all).
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
| **N1** PROTOCOL amendment 4 and the M5n pre-registration template | Discharge `M5m-510`; fix the candidate set's size cap, the trade floors (from N2), the primary metric, the block-bootstrap rule, the fee telemetry and the read ledger. | The amendment committed; the template committed; the owner's answer on step 6 quoted verbatim. | The owner has not answered `M5m-510`'s question; any N2 to N8 run exists before the amendment. |
| **N2** 4h and 1d bars from the 1m store, verified, plus a trade-count measurement in sample | Build the bars (section 7); verify against venue klines on an in-sample span; count the trades each candidate family makes in sample so the floors are set from a measurement. | The store named by digest; the bar-construction code frozen by digest; zero mismatches or the full list; excluded-bucket counts; trade counts per family and timeframe; the power statement (section 4) re-derived from the measured daily-return variance. | Any bar read in `[2024-01-01, 2026-10-01)`; the venue read is not authorised; a mismatch the construction cannot explain. |
| **N3** Indicators and a fixed, small set of candidates | Hand-written ATR, channel and trend indicators (no `pandas-ta`); the candidate set (volatility-scaled trend, breakout), its parameters and its size fixed by N1's cap (PROPOSED: no more than single digits). | The set listed with its parameters and a digest; indicator tests pass; the NaN warm-up contract holds. | A candidate is added after N1; an indicator mutates its input. |
| **N4** ATR trailing exit in the backtester, per D1, resolved on the 1m path | The stop level updates only at the candidate's bar close from closed-bar data (causal); the trigger is tested against each 1m bar inside the next bar, so a stop is hit intrabar as it would rest at a venue. Fill conventions follow `backtesting/fill_model.py`, read first. | A stop that the 1m path crosses fills at the stop or at the gapped open, per the fill model; tests for causality, intrabar trigger, gap-through and a never-moves-against rule; the live engine untouched. | The change needs a `src/` path the live bot loads; S4 branch FAIL (fill-model cause) is open. |
| **N5** ATR risk-based sizing and the trade floors | Quantity from risk per trade over the ATR stop distance, rounded down to the step; the floors of N1 as a gate that yields NOT MEASURED. | Sizing tests with exact `Decimal` assertions; a candidate below its floor reported NOT MEASURED in a test. | A float enters a money path. |
| **N6** Metrics | Daily-return Sharpe, a block bootstrap of it (block length rule from N1), and the fee telemetry of section 6, first in the report. | The metric functions pinned by tests against hand-computed values; the telemetry table rendered first. | The bootstrap's block rule is chosen after a result is seen. |
| **N7** In-sample walk-forward, selection and the S6-style null check | Walk-forward over in-sample only; select by N1's rule; run the null machinery of `scripts/s7_null.py`, adapted, to price the multiple testing. | The selection recorded before the null is run; the null's output committed; one candidate named, or none. | Any window bar read; a selection changed after the null. |
| **N8** A single OOS read of one pre-registered candidate | Section 8 entire. | The freeze entry pushed first; one run; the read ledger; the result with its fee telemetry first. | Section 8 is not satisfiable; M5m-510 is open; the freeze is unpushed. |
| **N9** Live-path design note only | How an ATR trail would rest at the venue (`trailingDelta` mapping) and whether Testnet supports it. No implementation, no venue call. | A note under `docs/` marking each claim DOCUMENTED, REASONED or UNMEASURED. | Any code for it; any claim that Testnet supports it without a measurement. |

N0 and N1 are sequential and gate everything else. N2 gates N3 to N7. N8 needs a candidate from N7. N9 is independent and may be written any time after N0.

## 11. Points the owner must answer before this draft is ratified

1. **D1 to D4:** the rulings, or confirmation of the mapping in section 3.
2. **Section 5:** which branch applies when S4's result exists.
3. **Section 7:** whether the N8 bar check counts as part of the single read, and whether N2's venue read is authorised.
4. **N1:** the candidate cap, the fee rate for 4h and 1d, the block-bootstrap rule, and whether `M5m-510`'s step 6 stands, is amended or is superseded.
5. **Trade floors:** none is stated here; N2 measures, N1 pins.

## 12. What this draft does not do

It reads no bar in the reserved window and no 1m bar at all; it makes no venue call and runs no backtest; it fixes no number that a measurement should fix; it does not decide S4; and it does not touch the live-trading block. Its estimate of power is arithmetic, and the first thing N2 does with it is check it against the data.
