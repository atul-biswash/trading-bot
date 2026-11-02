# S6 research protocol -- fixed before any S5 run exists (M5m P113 C1)

This file is the protocol of M5m's S5 and S6, committed **before the first S5 run and before any
candidate has a result**. It is a decided document: after it is committed it changes only by a new
commit that says what it changes, **and never after a result it could affect is seen** (section 10).
The rulings it carries out are quoted in `docs/NEXT_MILESTONE.md` (the P113 C1 annotation); this file
restates none of them.

**What is ruled and what is drafted.** The owner ruled: the boundary (R-BP), the trend filter (R-BS),
the families (sma_crossover and rsi at 1h, 4h and 1d, each with and without the filter), the protocol's
timing and S5's treatment (R-BT), the joint runs (R-Y), the three slippage arms with 1.20% as the gate
(R-B2), the regime labels (R-AI, R-AT) and S7's thresholds (R-D). **Drafted here, and the owner's to
overrule before the push** (nothing runs until it is pushed): the parameter grids (section 5) and the
entry file's shape (section 8). Each is marked DRAFTED where it appears. **Amendment 2 (section 10, P117)
replaced the draft of the selection rule, the walk-forward report and the in-sample trade minimum
(section 6) by the owner's rulings R-CB to R-CF, and added S7's two profit factors (section 7); R-CG
runs and counts all 216 variants of section 5. Amendment 3 (section 10, P119) rules two of the 216
ineligible for selection (R-CM), and records R-CN to R-CQ. Amendment 4 (section 10, P154) replaces section 6 step 6 by what the code does, and points to M5n's pre-registration.**

## 1. The history and the two windows (R-BP)

| | |
|---|---|
| stored history, BTCUSDT and ETHUSDT, all five intervals | `2017-08-17T04:00Z` to `2026-10-01T00:00Z` exclusive (P112 Phase 1, `p1_store_out.txt`, SHA-256 `cb0c8b9d552d2c920f72cc8bbfcc215825b1cf0970f3c7cf56cceaf95fbd52df`; `docs/RUN_LEDGER.md` section 44) |
| in-sample window | `[2017-08-17, 2024-01-01)`: 69.87% of the span |
| out-of-sample window | `[2024-01-01, 2026-10-01)`: 1,004 days, 30.13% of the span |
| the boundary | `2024-01-01T00:00Z`, ruled by the owner (R-BP). The exact 70% instant would be `2024-01-05T10:48:00Z`; the owner chose the quarter boundary so that no quarter is split |

A backtest window is a pair of whole UTC dates, half-open (`[start_date, end_date)`). A run **touches the
out-of-sample window** if its `end_date` is after `2024-01-01`; **a window that straddles the boundary is
out-of-sample and is refused unless it is exactly the declared out-of-sample window** (section 8).

## 2. The out-of-sample quarters and their labels (R-AI, R-AT, R-BP)

The labels are `docs/REGIME_LABELS.json`, SHA-256
`6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72` (its `.sha256` file agrees). A regime is
the label of the quarter holding a trade's entry bar. The eleven quarters of the out-of-sample window are
complete in the store, none is partial, and their labels are these:

| quarter | start | end (exclusive) | return | regime |
|---|---|---|---|---|
| 2024Q1 | 2024-01-01 | 2024-04-01 | 0.685761 | rising |
| 2024Q2 | 2024-04-01 | 2024-07-01 | -0.119360 | sideways |
| 2024Q3 | 2024-07-01 | 2024-10-01 | 0.008851 | sideways |
| 2024Q4 | 2024-10-01 | 2025-01-01 | 0.477650 | rising |
| 2025Q1 | 2025-01-01 | 2025-04-01 | -0.117829 | sideways |
| 2025Q2 | 2025-04-01 | 2025-07-01 | 0.297959 | rising |
| 2025Q3 | 2025-07-01 | 2025-10-01 | 0.064420 | sideways |
| 2025Q4 | 2025-10-01 | 2026-01-01 | -0.231486 | falling |
| 2026Q1 | 2026-01-01 | 2026-04-01 | -0.220926 | falling |
| 2026Q2 | 2026-04-01 | 2026-07-01 | -0.141464 | sideways |
| 2026Q3 | 2026-07-01 | 2026-10-01 | 0.426422 | rising |

**Out of sample: 4 rising, 5 sideways, 2 falling.** Every regime has at least two quarters, and **the two
falling quarters are consecutive** (2025Q4 and 2026Q1): S7's "positive net in at least two of the three
regimes" has, for the falling regime, one downturn counted twice. The in-sample window holds 26 quarters:
9 rising, 11 sideways, 5 falling and one partial (2017Q3, which has no label and whose trades belong to no
regime). S7's regime test counts labelled quarters only (R-AT).

## 3. The slippage arms and the costs (R-B2)

Every run is made at **three stop-slippage arms: 0.05%, 0.66% and 1.20%**. 1.20% is the gate arm, the mean
of the census of record's eight SL legs rounded up; the other two are for information. Every other cost is
the committed `config.yaml`'s: fee 0.1%, entry slippage 0.05%, initial balance 10,000 USDT. A run's arm
is its `--stop-slippage` (R-BR) and is written into its record.

## 4. The runs are joint (R-Y)

A candidate is run on **BTCUSDT and ETHUSDT together, at one timeframe**, through one portfolio with the
committed `max_open_positions`, one equity and one daily-loss limit, with per-pair breakdowns reported
beside the joint figure. S5's baseline is the committed config as it stands: BTCUSDT 1m and ETHUSDT 5m.

## 5. The candidate families and every parameter grid (DRAFTED)

A **variant** is a family, a timeframe, a filter setting and one point of the family's grid. The
denominator a multiple-testing judgement needs is **the number of variants declared here, and it is
fixed by this section**: 216.

| family | strategy | grid | points | timeframes | filter | variants |
|---|---|---|---|---|---|---|
| `sma_crossover` | `sma_crossover` | `fast_period` in {10, 20, 30} x `slow_period` in {50, 100, 200} | 9 | 1h, 4h, 1d | off, on | 9 x 3 x 2 = 54 |
| `rsi` | `rsi` | `period` in {7, 14, 21} x `oversold` in {20, 25, 30} x `overbought` in {70, 75, 80} | 27 | 1h, 4h, 1d | off, on | 27 x 3 x 2 = 162 |

Every grid contains the strategy's shipped parameters (`sma_crossover` 20/50, `rsi` 14, 30, 70), so the
two shipped strategies are variants and not extras. **The filter (R-BS) is: a `BUY` is taken only when the
bar's close is above its 200-period simple moving average; a `CLOSE` is never filtered.** It is the strategy
parameter `trend_filter_period` = 200; "off" is the parameter absent. The simple moving average is the
window-only form, so the filter has no dependence on where the buffer starts (P112 `p1_warmup_out.txt`:
`sma(200)` differed on 0 of 300 end bars at every buffer length from 200 up).

**A variant outside this table is not a candidate.** A new family, a new timeframe or a parameter off the
grid needs a protocol amendment committed first (section 10), and it adds its own variants to the
denominator.

## 6. Selection and the walk-forward report (R-CB to R-CG, amendment 2)

There are twelve **cells**: a family, a timeframe and a filter setting. For each cell:

1. **Every grid point is run**, all 216 variants of section 5 with the 1d family included (R-CG), **once
   over the in-sample window `[2017-08-17, 2024-01-01)` at the 1.20% arm only** (R-CE), jointly (section 4).
   The 0.05% and 0.66% arms run only in a candidate's out-of-sample read (section 7). `scripts/s6_sweep.py`
   makes the runs, and every run's record names its variant (section 8); the selection reads those records
   and nothing else.
2. **The statistic is the return profit factor (R-CB).** A trade's *return* is its net realised result
   divided by its entry quote total (the basis of R-AK). A point's **return profit factor** is the sum of
   its positive returns over the absolute sum of its negative returns, over every trade of its in-sample
   run. A run with no losing trade has none (the quotient is undefined) and is ineligible. The profit
   factor in USDT is recorded beside it and **never selects**: on a compounding path it weights the early
   trades by the equity they were sized from (P116 measured the first two years of S5 carrying 56.4% of
   the absolute net result).
3. **A point is eligible** only if all of these hold, and the reason it is not is recorded:
   a. **not ruined (R-CC):** its run's per-bar maximum drawdown (R-AJ, the record's `max_drawdown`) is at
      most **0.95**; a run above it is *ruined* and ineligible. The initial balance stays 10,000 USDT:
      the untradeable-equity floor of a 2% entry is at most 312.29 USDT over the stored history (P116),
      so no run within a 95% drawdown can have met it;
   b. **at least 250 in-sample trades (R-CD)**, the run's trade count, both pairs together;
   c. its return profit factor is defined;
   d. **it is not ruled ineligible (R-CM, amendment 3):** the two variants `sma_crossover` at 4h with
      `fast_period` 10 and `slow_period` 50, the trend filter off and on, are ineligible **whatever their
      figures**. They are still run and still counted among the 216 (section 5); they are never a cell's
      candidate and never a walk-forward fold's pick. The declaration's `ineligible_variants` holds them.
4. **The cell's candidate is the eligible point with the highest return profit factor.** A tie to six
   decimal places goes to the point that comes first in the order `protocol.variants()` yields, which is
   the grids' declared order. A cell with no eligible point has no candidate; that is recorded in the
   research log, and nothing of it is read out of sample. **Every cell with a candidate is read**: no
   candidate is dropped, and none is added, after the selection, by the walk-forward report or by anything
   else. Nothing is chosen by looking at the out-of-sample window.
5. **Walk-forward: reported, not gated (R-CF).** Four anchored folds, for Y = 2020, 2021, 2022 and 2023:
   *training* is the trades whose entry bar opens in `[2017-08-17, Y-01-01)` and *testing* is those whose
   entry bar opens in `[Y-01-01, (Y+1)-01-01)`. In each fold the rule of steps 2 to 4 picks a point from the
   training trades alone, with the same 250-trade minimum (not scaled to the shorter window; the number of
   eligible points is printed so a reader sees what the fold had to choose from). The ruin test of step 3a
   cannot use a per-bar figure for a part of a run, so a fold uses the **daily-close drawdown** of the run's
   equity over the training window, which can only under-detect the per-bar figure and is labelled as such.
   Per cell the report prints, for each fold: the point picked (or none) with the count of eligible
   points, its forward return profit factor and trades in year Y, and whether it is the cell's candidate;
   and per cell how many folds have a forward return profit factor above 1. **It is computed from each
   point's single continuous run, split by entry time**: the account state, the equity and the open-position
   limit carry across the splits, so a forward figure approximates a re-run, and the report says so. It
   removes no candidate, adds none and ranks nothing.
6. **The freeze (the candidate's parameters are fixed before its first out-of-sample read).**
   Line numbers in this step are those at commit a31c81b; where they differ, the named functions govern. It is two
   acts, and only the first is always done.

   *The selection (always).* `scripts/s6_select.py --out FILE` writes **one selection file**, as JSON Lines, one
   record a line (R-CU): a record per variant with its figures and its reasons, a record per cell with its chosen
   point, the walk-forward report and the skipped directories (`backtesting/selection.py:100`, `:926-927`). It is
   created exclusively and refuses to overwrite, computes nothing over an incomplete sweep, and reads no
   out-of-sample record (`scripts/s6_select.py:5-20`, `:113-121`). The owner commits it **unedited**, with the
   SHA-256 the script prints (`:125`) recorded in the research log.

   *The entry (only to bind a read).* An entry is `docs/research/entries/<id>.json` (`protocol.py:93`). It exists to
   bind one out-of-sample read of one candidate and is committed only when such a read is to be made: **a selection
   with no read to follow has no entry** (R-CV: "No entry is committed, since entries exist only to bind a read."),
   and S6's selection was committed with none. When a read is to be made the entry is committed with `status`
   `pending` and no `oos` block, bound to the candidate by its **candidate digest** (the strategy, its parameters,
   the pairs and timeframe, the costs and the config's digest; `backtesting/candidate.py:160`), listing the three
   arms and carrying a `selection` block: the variant, the in-sample run and the SHA-256 of its `run.json`, the two
   profit factors, the trade count and the selection file's SHA-256 (`backtesting/selection.py:952-980`).
   `s6_select.py --entries-dir DIR`, with `--out`, writes one such entry per candidate (`scripts/s6_select.py:21-23`,
   `:75-76`). The entry is pushed before any read, and a `status` is `pending` or `read` and nothing else, a `read`
   entry having an `oos` block and a `pending` one having none (`protocol.py:482-483`, `:504-508`). One malformed
   entry refuses the whole load, because the entry it hides might be the one that says a candidate was read
   (`:539-557`).

   *What a read must clear.* The out-of-sample window is read only by a run that clears `check_run`
   (`protocol.py:697-789`), in this order: a provenance verdict of `accepted`, so a clone of a pushed commit
   (`:725-731`); an entry carrying the run's candidate digest (`NO_ENTRY`, `:732-740`); for a candidate entry, a point
   of a declared family's grid (`NOT_A_GRID_POINT`, `:744-751`); exactly the declared window (`WRONG_WINDOW`,
   `:761-766`); exactly the declared arms (`ARMS_MISMATCH`, `ARM_NOT_DECLARED`, `:767-776`); an entry that is
   `pending` with no `oos` block (`ALREADY_READ`, `:777-782`); and no completed record of that candidate at that arm
   in this clone (`LOCAL_PRIOR_READ`, `:783-788`). A parameter changed after the freeze is a different digest and has
   no entry. A window wholly in sample needs none (`:719-722`).

   *After the read.* The three arms are read, then `scripts/s6_mark_read.py` (R-CP) verifies each record through the
   evidence door and rewrites the entry as `read`, with `oos.records` holding each arm's run directory and the
   SHA-256 of its `run.json` (`backtesting/readmark.py:1-14`); it refuses an entry already read (`:192-195`). The
   gate re-checks every record against its entry, and the variant against the entry's `selection` block
   (`backtesting/gate.py:302-318`).

**What is pre-declared and what is chosen.** Pre-declared, in this file before the first S6 run: the
families, timeframes and grids (section 5), the filter, the window and its boundary, the arm and the cost
settings, the statistic and its tie-break, the eligibility rules and their numbers (0.95 and 250), the
fold dates, S7's thresholds, and the freeze procedure. **Chosen by the data, mechanically**: the winning
point of each cell (at most twelve), and the point each fold picks (a report). Nothing is chosen by a person
after the data is seen, and the selection file is the committed record of what was chosen.

## 7. The out-of-sample read

Each candidate is read **once**, as **three runs, one per arm**, over exactly
`[2024-01-01, 2026-10-01)`. **A second read of a candidate is refused** (section 8). The twelve candidates
therefore cost at most 36 out-of-sample runs (fewer when a cell has no candidate, section 6 step 4). S7's
figures and its decision are recorded in `docs/PHASE_HISTORY.md` at M5m's close, with the variant count
of section 5, which is **216 whatever the selection left** (R-CG).

**S7's tests (R-D, R-B2, R-CJ), applied to the 1.20% record of a candidate and to no other.** A candidate
PASSES only if all of these hold, out of sample, net of fees and of the arm's stop slippage:

- **both profit factors are at least 1.3: the one from per-trade returns and the one in USDT (R-CJ).**
  Both are printed. The return profit factor is section 6 step 2's; the USDT one is the record's
  `profit_factor_net`, over the run's trades from the fresh 10,000 USDT;
- at least **100 trades**;
- the per-bar maximum drawdown (R-AJ) is at most **0.20**;
- a positive net result in at least **two of the three regimes**, counting complete quarters only (R-AT).

The 0.05% and 0.66% records are printed for information and decide nothing. **An out-of-sample figure used
for S7 comes only from a run whose window starts at 2024-01-01 with the configured initial balance
(R-BW)**, and `scripts/s7_gate.py` refuses a record that does not.

## 8. How the protocol is enforced (R-BT, S6's "read once per candidate")

`src/trading_bot/backtesting/protocol.py` reads the declaration below, and the `backtest` command refuses
before it makes a run directory when any of these holds:

- the window touches the out-of-sample window and the run's provenance verdict is not `accepted` (an
  out-of-sample read comes only from a deployment clone of a pushed commit);
- the window touches the out-of-sample window and no entry under `docs/research/entries/` carries the
  run's **candidate digest** (a digest of the effective settings that define a candidate: the config's
  digest, the strategy and its parameters, the pairs and timeframes, the costs other than the stop-slippage
  arm, and the stored-`exchangeInfo` environment);
- the entry's kind is `candidate` and the candidate is not a point of a declared family's grid;
- the window is not exactly the declared out-of-sample window (a candidate) or the declared full-history
  window (the S5 baseline);
- the run's stop-slippage arm is not one the entry lists, or the entry already carries an `oos` block (the
  candidate has been read), or this clone already holds a record of that candidate and arm that touched
  the out-of-sample window.

**An entry** is a JSON file `docs/research/entries/<id>.json`, committed **before** the read and committed
again with its `oos` block after it. The sequence for a candidate: commit the entry with `status` `pending`
and its in-sample evidence; push; clone; run the three arms; commit the entry again with `status` `read` and
the three record digests. A clone of any later commit then refuses a second read, with no state outside git.
A candidate's entry also carries a `selection` block holding the evidence of section 6 step 6; the guard
reads the fields above and ignores that block, so it is the record of why the candidate was chosen and binds
nothing.

**S5 (R-BT).** S5 is recorded in the research log (`docs/research/LOG.md`) as **a full-history read of a
non-candidate configuration**: the committed config, `sma_crossover` 20/50 on BTCUSDT 1m and ETHUSDT 5m,
over `[2017-08-17, 2026-10-01)`, at the three arms. It has a baseline entry of kind `baseline`. It is not
a candidate read, because its timeframes (1m and 5m) are not a candidate's (1h, 4h, 1d). **S5's report gives
the in-sample and the out-of-sample figures separately, at the boundary of section 1.**

**M5n (amendment 4).** M5n's pre-registration is `docs/M5N_PREREGISTRATION.md` (committed at `ede21a3`, SHA-256
`e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e`). It pins M5n's unit, evaluation span, costs, risk
settings, trade floors, in-sample gate, selection, no-pass rule and single out-of-sample read. This protocol carries the
slot for it and none of its values (R-DW), so the floors and every other number are read from that file and are not
restated here. The declared families of section 5 are `sma_crossover` and `rsi`, so the guard above treats a candidate
of any other strategy as `NOT_A_GRID_POINT` (`protocol.py:744-751`).
M5n's one read is bound by amendment 4's rule in section 10, not by this guard.

## 9. What is not claimed

- The guard cannot see a run made outside a clone of a pushed commit; such a record is not evidence
  (R-AR) and the out-of-sample window is refused to it outright.
- The walk-forward figures are an approximation (section 6, step 5): one continuous run split by entry
  time, and a daily-close drawdown standing for the per-bar one inside a fold.
- The selection statistic is a per-trade return, so it does not see how large each trade was; S7 also
  requires the profit factor in USDT, and the two can disagree (P116 measured 0.2724 against 0.3007 on S5).
- The 250-trade minimum is a constant-rate argument: S7's 100 trades over 1,004 days is about 232 over the
  2,328 in-sample days, and a candidate's out-of-sample trade count is not guaranteed by it.
- A per-bar out-of-sample drawdown (R-AJ) cannot be derived from a full-history record; the S5 report
  gives a daily-close drawdown for each window, labelled as such.
- The grids (section 5) and the entry file's shape (section 8) are the reviewer's draft until the owner
  has read them; the selection rule, the walk-forward report and the trade minimum are the owner's
  (amendment 2).

## 10. Amendments

An amendment is a commit that edits this file, names the section and the reason, and **precedes every run
it could affect**. A run made before an amendment is not re-read under it. Nothing here is amended after
a result of an affected family is seen: the family is closed instead, and the log records that.

**Amendment 1 (P113 C3, section 11, before any run).** The declaration gains `costs` (section 3's fee,
entry slippage and initial balance) and `exchange_info_environment`, so that the guard checks a candidate's
costs mechanically instead of leaving them to the entry's author. No family, grid, boundary, arm or rule
changes, and no run exists that it could affect.

**Amendment 2 (P117 C1; sections 6, 7, 9 and 11 and the intro; before any S6 run).** The owner's rulings,
verbatim:

- R-CA: "The 'allowed at each arm' test's in-memory reset of the entry to pending (P116 C1) is ratified: its assertions are unchanged."
- R-CB: "S6 selects on per-trade returns, not on USDT P&L."
- R-CC: "A run whose per-bar maximum drawdown exceeds 0.95 is ruined and ineligible for selection. The initial balance stays at the configured 10,000."
- R-CD: "A variant is eligible for selection only with at least 250 in-sample trades."
- R-CE: "Selection uses the 1.20% stop-slippage arm only. The 0.05% and 0.66% arms run only in a candidate's out-of-sample read."
- R-CF: "Walk-forward is reported, not gated: four anchored folds, training on [2017-08-17, Y) and testing on calendar year Y, for Y = 2020 to 2023."
- R-CG: "All 216 declared variants, the 1d family included, are run and counted in S7's variant denominator."
- R-CH: "Sweep workers may run in parallel, provided the sweep first runs one variant serially and in parallel and the two trade-log digests are equal; otherwise it runs serially."
- R-CI: "The entries-directory test assertions select entries by id. That overturn is authorised under this ruling."
- R-CJ: "S7's profit factor test passes only if both profit factors are at least 1.3: the one from per-trade returns and the one in USDT. Both are printed."

*What it changes.* Section 6 read the draft *"A point is eligible if its in-sample run has at least 100
trades"* and *"the highest net profit factor"* (in USDT, by the record's `profit_factor_net`) and made
walk-forward a per-cell log line; they are now the rules of section 6 steps 2 to 5, with the ruin test (R-CC).
`min_in_sample_trades` is 250, where it was 100. Section 7 gains S7's two profit factors (R-CJ). R-CA, R-CH
and R-CI govern code and tests, not this file, and are recorded here so the protocol holds every ruling that
shaped S6's machinery. *What it does not change:* the families, grids, filter, boundary, arms, costs, joint
runs, the read-once guard and S5's baseline. No S6 run exists that it could affect. The S5 records carry
the earlier protocol digest and are not re-read under this amendment.

**Amendment 3 (P119 C1; sections 6, 10 and 11 and the declaration's `selection` block; before any S6 run).**
The owner's rulings, verbatim:

- R-CM: "The two variants the rehearsal read in the reserved window, sma_crossover at 4h at the 10/50 grid point with the trend filter off and on, are ineligible for selection. They are still swept and counted in S7's variant denominator. The research log records that their figures for 2024-01-01 to 2025-04-01 were seen, by what, and where. This is decided before any in-sample result exists and without regard to those figures."
- R-CN: "No rehearsal, probe or test reads any bar at or after 2024-01-01T00:00Z, except an out-of-sample read under a committed entry. The rehearsal script refuses such a window."
- R-CO: "A junction is removed only with cmd /c rmdir. No recursive copy or delete (cp -r, rm -rf, Remove-Item -Recurse, Copy-Item -Recurse) is run on a directory that holds a junction, by hand or by script."
- R-CP: "Entries are marked read by scripts/s6_mark_read.py (owner step O7). It verifies each out-of-sample record through the evidence door and writes the three record digests into the entry; it refuses an entry already read, a record that fails the door, and a set other than exactly the three declared arms."
- R-CQ: "A sweep whose check lost a worker and then recovered the variant prints the loss and the recovery, and reports COMPLETE when every variant has a sealed record (M5m-445)."

*What it changes.* Section 6 step 3 gains condition d, and the declaration's `selection` block gains the key
`ineligible_variants`, a list of the two variants of R-CM, each with its `ruling`; `scripts/s6_select.py` and
`backtesting/selection.py` honour it, and refuse a block whose list names a point that is not declared or names
one twice. The protocol's digest changes with this commit, and **this file does not change again until S7**.
*What it does not change:* the families, grids (so the 216 and S7's denominator), filter, boundary, arms,
costs, joint runs, the eligibility numbers 0.95 and 250, the read-once guard and S5's baseline. R-CN to R-CQ
govern code, tools and the owner's steps, not this file, and are recorded here, as R-CA, R-CH and R-CI were, so
that the protocol holds every ruling that shaped S6's machinery. The figures R-CM refers to are recorded in
`docs/research/LOG.md` (Entry 5). No S6 run exists that this amendment could affect.

**Amendment 4 (P154; sections 6, 8 and 10 and the intro; before any M5n out-of-sample read, and after S7 was recorded
FAIL).** The owner's rulings, verbatim:

- R-CV (the sentence that bears on step 6): "No entry is committed, since entries exist only to bind a read."
- R-DW: "The trade floors are pinned in the M5n pre-registration, written after N3's counts and before N7, and it
  states that the counts were seen. PROTOCOL amendment 4 (N1) carries the rule's slot, not its values."

*What it changes.* Section 6 step 6 read as though a `pending` entry per candidate were an unconditional part of the
freeze; it is the freeze's second act, committed only to bind a read, and step 6 now says what
`scripts/s6_select.py`, `backtesting/protocol.py`, `backtesting/readmark.py` and `backtesting/gate.py` do, with the
lines they do it on. That discharges `M5m-510`. Section 8 gains the paragraph that points to
`docs/M5N_PREREGISTRATION.md`. *What it does not change:* the declaration of section 11, so the families, the 216
variants, the boundary, the arms, the costs, the eligibility numbers 0.95 and 250, S7's thresholds and the read-once
guard are as they were; S5's baseline entry; the selection committed at `bdd95e4`. The protocol's digest changes with
this commit (it is the SHA-256 of the file's text, `protocol.py:440`), and the records that carry the earlier digest
(`docs/research/selection.jsonl`, `s7_null.json`, `s7_null.txt` and S5's records) are not re-read under it. No M5m run
exists that this amendment could affect: S7 is recorded FAIL with no S7 candidate read out of sample (R-CV).

*How M5n's read is bound.* M5n's single out-of-sample read is governed by docs/M5N_PREREGISTRATION.md and is made only
by M5n's N8 runner, never through check_run, whose declared families do not include M5n's. It reads exactly one
candidate, once, and the N8 runner keeps its own read ledger and refuses a second M5n read. The window is not
untouched: S5's baseline read all of it by design (window class straddling), and the M5m rehearsal and quarter scan
read parts of 2024 and early 2025 (M5m-447). No M5n candidate family has been read on it. After M5n's read, the window
is retired from candidate confirmation for every later milestone, which confirms on a forward window instead.

## 11. The machine-readable declaration

`protocol.py` reads only what is between the markers, and of that only the keys it knows. The test
`test_the_declaration_matches_the_tables` pins that its families give the 216 variants of section 5.
The `selection` and `s7` blocks (amendment 2) are not read by `protocol.py`, which ignores them; the
selection and gate modules of the S6 tooling (P117 C3 and C7) read them and refuse a block that is missing
or mistyped. The `selection` block's `ineligible_variants` (amendment 3) is read by the selection module,
which refuses a variant in it that is not a declared point.

<!-- protocol-json:begin -->
```json
{
  "protocol_schema": 1,
  "history": {"start": "2017-08-17", "end_exclusive": "2026-10-01"},
  "boundary": "2024-01-01",
  "regime_labels_sha256": "6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72",
  "arms_stop_slippage_percent": ["0.05", "0.66", "1.20"],
  "gate_arm": "1.20",
  "filter": {"param": "trend_filter_period", "value": 200},
  "min_in_sample_trades": 250,
  "selection": {
    "statistic": "return_profit_factor",
    "arm": "1.20",
    "ruin_max_drawdown": "0.95",
    "tie_places": 6,
    "walk_forward": {"train_start": "2017-08-17", "test_years": [2020, 2021, 2022, 2023]},
    "ineligible_variants": [
      {"family": "sma_crossover", "timeframe": "4h", "filtered": false,
       "params": {"fast_period": "10", "slow_period": "50"}, "ruling": "R-CM"},
      {"family": "sma_crossover", "timeframe": "4h", "filtered": true,
       "params": {"fast_period": "10", "slow_period": "50", "trend_filter_period": "200"}, "ruling": "R-CM"}
    ]
  },
  "s7": {
    "profit_factor_min": "1.3",
    "trades_min": 100,
    "max_drawdown_max": "0.20",
    "regimes_positive_min": 2
  },
  "pairs": ["BTCUSDT", "ETHUSDT"],
  "costs": {"fee_percent": "0.1", "slippage_percent": "0.05", "initial_balance": "10000"},
  "exchange_info_environment": "mainnet",
  "families": [
    {
      "id": "sma_crossover",
      "strategy": "sma_crossover",
      "timeframes": ["1h", "4h", "1d"],
      "grid": {"fast_period": [10, 20, 30], "slow_period": [50, 100, 200]}
    },
    {
      "id": "rsi",
      "strategy": "rsi",
      "timeframes": ["1h", "4h", "1d"],
      "grid": {"period": [7, 14, 21], "oversold": [20, 25, 30], "overbought": [70, 75, 80]}
    }
  ],
  "baselines": [
    {
      "id": "s5-baseline",
      "strategy": "sma_crossover",
      "params": {"fast_period": 20, "slow_period": 50},
      "pairs": [["BTCUSDT", "1m"], ["ETHUSDT", "5m"]],
      "window": {"start": "2017-08-17", "end_exclusive": "2026-10-01"}
    }
  ]
}
```
<!-- protocol-json:end -->
