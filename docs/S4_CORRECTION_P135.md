# S4 correction P135: R-DS, the interval of the R-DR wick annotation

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It **supersedes R-DR's interval clause only**, the words *"while the live position was open"* in `docs/S4_CORRECTION_P134.md` section 1, and with them the executing session's operational reading of that clause in the same file's section 5, item 1 (the interval from the live entry's `order_placed` line to the exit's booking line, and *"no live position"* for a backtest-only entry), which was recorded there as a gap in the ruling and not as a decision. **Everything else in R-DR stands**: the 3% threshold and its sensitivity, the counts by cause, that it recomputes no A, B or C figure, is not an exploratory analysis under R-DL, excludes nothing and changes no verdict. It supersedes nothing in the pre-registration or in the P128, P129 or P130 correction files, and it edits none of them.

It is committed while the run's stop `M` = `2026-11-01T00:00:00Z` is still in the future, so before any S4 backtest figure exists, and before the tool it specifies is drafted (R-DQ).

## 1. The ruling, verbatim

The project owner's ruling of M5m P135.

> **R-DS**  The R-DR interval is: for a matched entry, the union of the live and the backtest holding periods; for a backtest-only entry, the backtest holding period; for a live-only entry, the live holding period. A holding period runs from the entry bar's open to the exit bar's close, or to M if the position is open at M. Everything else in R-DR stands. Ruled after P134 and before any S4 backtest figure exists.

## 2. Why the interval changed, MEASURED

R-DR's *"the live position"* has no meaning for a backtest-only entry, and a backtest-only entry is exactly where a wick the live bot never sat through can decide the disagreement. `docs/S4_CORRECTION_P134.md` section 5 named the gap and left it to the owner; R-DS is the owner's answer. For a matched entry whose exits differ, the union is what shows a wick in either side's holding period, which is the case R-DR was ruled for: ETHUSDT list `218102`, held 40 minutes live (`22:00:01Z` to `22:40:03Z`) while the backtest is expected to leave it at the `22:30` wick (`docs/RUN_LEDGER.md` section 70, `M5m-675`).

## 3. The operational reading, the executing session's and not the ruling's

Nothing here binds beyond the ruling. It fixes the words the tool needs, so the stop report is not improvised, and each point is a reading the owner may overrule.

1. **The interval is half open**, `[entry bar open, exit bar close)`, and a 1m bar of the entry's pair is **inside it when its open time is at or after the interval's start and before its end**. A bar opening exactly at the interval's end is outside; a bar opening exactly at its start is inside.
2. **The entry bar's open** is the live or backtest entry's own `entry_bar_open`, the signal bar's close plus one millisecond on the live side and the `entry_bar_open` column on the backtest side. The bars are the pair's own timeframe (1m for BTCUSDT, 5m for ETHUSDT in the S4 config); the wide-bar test reads the **1m** series of the pair, which is the recorded Testnet series.
3. **The exit bar's close** is, on the backtest side, the `exit_bar_open` column plus the pair's timeframe (the file's own `exit_time` column, which equals it in the first two rows of the P131 rehearsal's file, the only rows read). On the live side it is, for a strategy `CLOSE`, the booking's candle time, the signal bar's close, plus one millisecond; for a protective-leg fill it is the close of the pair's timeframe bar that contains the fill instant. **The second of those is a choice**: the ruling's *"exit bar"* names no bar for an exit that happens inside one.
4. **A position open at M** is one with no exit instant on the side in question; its interval runs to M, which the tool takes to be its `--window-end`. For E1, whose window ends before M, that is E1's own end, and E1's list contains no entry that opens after it.
5. **The threshold** is R-DR's strict inequality, `(high - low) / open >= 3%`, on a 1m bar with a positive open; 2.999% is not wide.

## 4. A premise corrected

P134's predictions (a) and (c), that the stop legs of lists `218102`, `183218` and `71012` were `STOP_LOSS_LIMIT` legs, **assumed stop-limit legs, and that assumption was the architect's**; the legs are market-type `STOP_LOSS` (`docs/RUN_LEDGER.md` section 71, `M5m-677`): both order-list mappers at `45547f1` send `STOP_LOSS` with a stop price and no limit key. P134's prompt also refers to a U10 *"market STOP_LOSS"* suggestion that carried the same assumption; that wording is not in the tree (`docs/NEXT_MILESTONE.md`'s U10 item says the legs are `STOP_LOSS` and asks whether a `STOP_LOSS_LIMIT` would bound the price), so the premise error recorded here is the one that is, the predictions. Recorded as architect-owned (`M5m-684`).

## 5. Section 3 ratified as the operational rule, at P136

P136's prompt states that `M5m-683` is ratified as the operational exit-bar rule. **The ruling's own words were not supplied**, only that statement, so this section records it as stated and does not quote it (the same limit `M5m-665` records for R-DQ before its text was written down). What it ratifies is the content of section 3 above and of `M5m-683`: the half-open interval over 1m bar opens, the entry bar's open from each side's own `entry_bar_open`, the backtest's exit bar close as `exit_bar_open` plus the pair's timeframe, the live strategy `CLOSE`'s as the booking's candle time plus a millisecond, the live protective-leg fill's as the close of the epoch-aligned pair-timeframe bar that contains the fill, an exit-less side read as open at M with M the tool's `--window-end`, and the strict `>= 3%` bound. **The one point section 3 flagged as a choice, the leg fill's exit bar, is now the rule.** The tool implements it (`scripts/s4_wick_annotate.py`, `live_exit_close`), and `tests/unit/test_s4_wick_annotate.py` pins it for a 5m pair (`TestTheFiveMinuteExitBar`, `M5m-695`). Nothing in sections 1 to 4 is edited.
