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
overrule before the push** (nothing runs until it is pushed): the parameter grids (section 5), the
selection rule and the walk-forward report (section 6), the in-sample trade minimum, and the entry file's
shape (section 8). Each is marked DRAFTED where it appears.

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

## 6. Selection and the walk-forward report (DRAFTED)

There are twelve **cells**: a family, a timeframe and a filter setting. For each cell:

1. Every grid point is run once over the **in-sample window** at the **1.20% arm**, jointly (section 4).
2. A point is **eligible** if its in-sample run has at least **100 trades**. A cell with no eligible point
   has no candidate; that is recorded in the research log and nothing of it is read out of sample.
3. **The cell's candidate is the eligible point with the highest net profit factor** over the whole
   in-sample window at 1.20%. A tie to six decimal places goes to the point whose parameter tuple comes
   first in the grid's declared order. Nothing is chosen by looking at the out-of-sample window.
4. **Walk-forward (a report, not a second selection).** For the four anchored training windows ending
   `2020-01-01`, `2021-01-01`, `2022-01-01` and `2023-01-01`, the same rule picks a point from the trades
   whose entry is before the end, and that point's trades in the following calendar year give its forward
   figure. All of it is computed from each point's single in-sample run, split by entry time: the account
   state, the equity and the open-position limit carry across the splits, so a forward figure is an
   approximation of a re-run and is reported as one. Per cell the log records the chosen point, its
   forward net profit factor for each of 2020 to 2023, and how many of the four are above 1.

## 7. The out-of-sample read

Each candidate is read **once**, as **three runs, one per arm**, over exactly
`[2024-01-01, 2026-10-01)`. **A second read of a candidate is refused** (section 8). The twelve candidates
therefore cost at most 36 out-of-sample runs. S7's figures and its decision are recorded in
`docs/PHASE_HISTORY.md` at M5m's close, with the variant count of section 5.

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

**S5 (R-BT).** S5 is recorded in the research log (`docs/research/LOG.md`) as **a full-history read of a
non-candidate configuration**: the committed config, `sma_crossover` 20/50 on BTCUSDT 1m and ETHUSDT 5m,
over `[2017-08-17, 2026-10-01)`, at the three arms. It has a baseline entry of kind `baseline`. It is not
a candidate read, because its timeframes (1m and 5m) are not a candidate's (1h, 4h, 1d). **S5's report gives
the in-sample and the out-of-sample figures separately, at the boundary of section 1.**

## 9. What is not claimed

- The guard cannot see a run made outside a clone of a pushed commit; such a record is not evidence
  (R-AR) and the out-of-sample window is refused to it outright.
- The walk-forward figures are an approximation (section 6, step 4).
- A per-bar out-of-sample drawdown (R-AJ) cannot be derived from a full-history record; the S5 report
  gives a daily-close drawdown for each window, labelled as such.
- The grids, the selection rule and the 100-trade minimum are the reviewer's draft until the owner has
  read them.

## 10. Amendments

An amendment is a commit that edits this file, names the section and the reason, and **precedes every run
it could affect**. A run made before an amendment is not re-read under it. Nothing here is amended after
a result of an affected family is seen: the family is closed instead, and the log records that.

**Amendment 1 (P113 C3, section 11, before any run).** The declaration gains `costs` (section 3's fee,
entry slippage and initial balance) and `exchange_info_environment`, so that the guard checks a candidate's
costs mechanically instead of leaving them to the entry's author. No family, grid, boundary, arm or rule
changes, and no run exists that it could affect.

## 11. The machine-readable declaration

`protocol.py` reads only what is between the markers. The test `test_the_declaration_matches_the_tables`
pins that its families give the 216 variants of section 5.

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
  "min_in_sample_trades": 100,
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
