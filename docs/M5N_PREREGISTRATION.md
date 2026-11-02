# M5n pre-registration

## 1. Unit

Each candidate (C1 to C6, R-DY) is one portfolio trading BTCUSDT and ETHUSDT together. It yields one daily net return series: equity, including cash and open positions marked at the venue's 1d archive close, at each UTC 00:00. Annualisation uses 365 days.

## 2. Evaluation span

In sample: from the first UTC day on which every candidate's indicators are defined for both pairs (computed by the code and recorded at N7) to 2024-01-01T00:00:00Z. All six candidates share that start. Days without a position are zero-return days and count. Open positions at the in-sample end are marked, not closed. Out of sample: [2024-01-01, 2026-10-01). Indicators are warmed on in-sample bars, and the book starts flat.

## 3. Costs

Fees 0.10 percent per side, taker. Stop slippage 1.20 percent, with gap-through per R-P1/R-W and R-EA. Verdicts use these values only. Sensitivities, reported and never deciding: fees 0.075 percent; slippage 0.66 and 0.10 percent.

## 4. Risk

1 percent of equity per trade at the initial stop (N5); max_position_size_percent 20, which bound about a third of 4h entries in sample (C4 146 of 452, C5 110 of 308; M5n-162), so those entries risk under 1 percent; max_daily_loss_percent 5 on entry-time stops (halt note, M5n-139); every other RiskManager default unchanged. The 20 percent cap is the live risk policy and is kept with the counts in view.

## 5. Trade floors

(R-DW; the in-sample counts at RUN_LEDGER sections 94 and 98 were seen before these were set). 1d candidates: at least 30 in-sample trades across both pairs and at least 12 out of sample. 4h candidates: at least 120 in sample and 48 out of sample. On the measured counts this excludes C3 (12 trades) in sample.

## 6. In-sample gate (N7)

A candidate passes if all hold: (a) it meets its in-sample floor; (b) the stationary-bootstrap (Politis-Romano) 95 percent percentile lower bound of its annualised net daily Sharpe is above 0, using expected block length 20 days, 10000 resamples and seed 20261025; (c) its deflated Sharpe ratio (Bailey and Lopez de Prado, 2014) exceeds 0.95, with N = 6 trials (all six candidates, C3 included), the trial variance taken from the six in-sample Sharpe ratios, and the candidate's own skewness and kurtosis. No parameter is fitted, so there is no walk-forward; this supersedes the charter's N7 wording "walk-forward" and "S6-style null check".

## 7. Selection

Among passing candidates, the one with the highest in-sample annualised net daily Sharpe is selected. Ties are broken by more in-sample trades.

## 8. No pass

If no candidate passes, M5n records FAIL at N7 and the out-of-sample window stays unread.

## 9. Out of sample (N8)

One read of the selected candidate only. Bars are first verified against the venue's klines (R-DV, as part of this read). Verdict: CONFIRMED if the stationary-bootstrap two-sided 95 percent percentile lower bound of its annualised net daily Sharpe is above 0, with the section 6 settings; otherwise NOT CONFIRMED. The out-of-sample floor is checked first: below it, the verdict is NOT CONFIRMED (insufficient trades). The Sharpe's sign is reported beside the verdict as a diagnostic.

## 10. Context, never a criterion

The equal-weight buy-and-hold BTCUSDT and ETHUSDT daily Sharpe over the same spans, with the same marking.

## 11. S4 dependency

R-DU applies unchanged.

## 12. Fixed items

D1 to D4, R-DV, R-DX, R-DY, R-DZ, R-EA, R-EB and the N4b and N5 decisions, as in docs/M5N_CHARTER_DRAFT.md at this commit. Any change after this file's commit is an amendment in a new file and makes affected results exploratory.
