# Next milestone — M5m

*Rotated at M5l's close (P98). This is the single home for live open items. Rules do
not live here: they are in `CLAUDE.md`, including its **Standing authorities for
commits**. Every item below is either carried from M5l with its arming condition and
its annotations, or indexed as resolved with the commits that resolved it.*

> **ANNOTATED WHEN M5m's SCOPE WAS DECIDED: *"Every item below is either carried from
> M5l … or indexed as resolved"* IS NO LONGER TRUE.** The section immediately below,
> *M5m — VALIDATE A STRATEGY BEFORE ANYTHING ELSE*, is new and carries M5m's own items,
> S0 to S7. **What survives:** every item after it is carried or indexed exactly as the
> sentence says, and none of them is edited by the commit that wrote that section.

## M5m — VALIDATE A STRATEGY BEFORE ANYTHING ELSE

**DECIDED BY THE PROJECT OWNER, in a review session after M5l's close.** The owner's
instruction, verbatim: *"rewrite the next milestone based on your suggestion"*. The
suggestion it adopts was the reviewer's, given in that session, and it is restated here
rather than quoted so that every figure in it carries its instrument:

1. stop engine work, except a defect found by a run;
2. build the minimal backtester next, with fees, and prove it against Testnet trades;
3. test slower strategies on it over two or more years of data;
4. treat live readiness — N6, U9, U10 — as conditional on step 3 passing.

**THIS OVERTURNS ONE RULING AND NO OTHER.** P98's order, *"the items that block live
trading come first"*, is superseded for M5m: those items are **deferred, not dropped**,
and each keeps its text and its arming condition below. The live-trading block is
untouched — `refuse_live_trading` does not change in M5m, and N6's two preconditions
still stand exactly as written. Nothing here rules U10's own discrepancy either; it is
deferred with the item.

### Why the order changed — the evidence, each figure with its capture

**The engine is no longer the binding constraint; the strategy is.** M5l's observation
run booked six round trips equal to the venue's fills to the last digit (section 26 of
`docs/RUN_LEDGER.md`, capture SHA-256
`023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb`). In the same
section, the end store (SHA-256
`d2d83eed081bb14ae00469d39bd136b58d989bee80f601f0aed9d9dbe9f1c2d4`) holds
`lifetime_realised = -451.25366810` USDT over the days rolled since 2026-09-10, gross of
entry fees, with every commission in every capture at `0.00000000`.

**A per-trade census of an owner-supplied capture**, `trading_bot.log`, SHA-256
`641778e50a42ca44101b28b9ce342431352544bca9855711d3164bba24fc32b4`, last record
`2026-09-24T03:58:40Z`. Its figures are **MEASURED by an untracked reviewer script**, so
they are not reproducible from this tree until S0 lands:

- 157 bookings from 2026-09-04 to 2026-09-24, each matched to its `order_placed` line:
  147 by the strategy's `CLOSE`, 10 by a protective leg. Realised **-157.7217** USDT
  gross; win rate 35.0%; profit factor 0.78.
- Per-trade return on the entry quote total: mean **-0.0553%**, standard deviation
  1.0475%, 95% interval **[-0.2192%, +0.1085%]**. The 147 strategy closes alone: mean
  **+0.0049%**.
- At an assumed 0.1% commission per side, the net mean is -0.2553% per trade, t = -3.05
  under an independence assumption. **The upper end of the gross interval does not cover
  a 0.15% round trip.**
- Seven `SL` legs filled 0.03% to 4.21% beyond their triggers; the worst moved a 2% stop
  to a -6.13% exit.

> **ANNOTATED AT M5m P99 (C4): THE FIGURES ABOVE ARE SUPERSEDED AND UNREPRODUCIBLE, AND
> THE CENSUS OF RECORD IS THE TOOL'S OUTPUT ON THE M5k CAPTURE.** They were taken by an
> untracked script over the capture `trading_bot.log`, SHA-256
> `641778e50a42ca44101b28b9ce342431352544bca9855711d3164bba24fc32b4`, which is not on
> disk (S0's annotation above), so nothing here can be recomputed from the tree. By the
> owner's ruling (b), the census of record is `scripts/trade_census.py` (`cf64d90`) run on
> `trading_bot.m5k-close-20260925T182818Z.log`, SHA-256
> `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`; its output is
> section 27 of `docs/RUN_LEDGER.md`, verbatim. **Every figure that differs between the
> two**, and the cause, in the owner's words *"the difference is itself a finding"*:
>
> | Figure | Untracked census | Census of record (165 bookings, to `2026-09-25T14:05:02Z`) | Tool, `--until 2026-09-24T03:58:40Z` |
> |---|---|---|---|
> | Bookings | 157 | **165** | 157 |
> | By `CLOSE` / by a protective leg | 147 / 10 | **154 / 11** | 147 / 10 |
> | Protective legs, `SL` / `TP` | 7 `SL` named; `TP` not stated | **8 / 3** | 7 / 3 |
> | Realised, gross | -157.7217 | **-192.0271** | -157.7217 |
> | Win rate | 35.0% | **34.5%** (57 of 165) | 35.0% (55 of 157) |
> | Profit factor | 0.78 | **0.75** | 0.78 |
> | Per-trade return, mean | -0.0553% | **-0.0641%** | -0.0553% |
> | Per-trade return, standard deviation | 1.0475% | **1.0368%** | 1.0475% |
> | 95% interval | [-0.2192%, +0.1085%] | **[-0.2223%, +0.0941%]** | [-0.2192%, +0.1085%] |
> | The strategy's closes alone, mean | +0.0049% | **+0.0050%** (154 closes) | +0.0049% (147) |
> | Net mean at 0.1% a side | -0.2553% | **-0.2641%** | -0.2553% |
> | t of the net mean | -3.05 | **-3.27** | -3.05 |
> | Stop-loss slippage beyond the trigger | seven legs, 0.03% to 4.21% | **eight legs, 0.0291% to 4.2121%** | seven, 0.0291% to 4.2121% |
> | Its median | *0.66%, as S2 states it* | **0.6419%** | 0.6646% |
> | Worst stop-loss exit | *"a 2% stop to a -6.13% exit"* | **-6.1279% from the entry limit, a 2.0000% stop** | the same |
>
> **The cause, MEASURED by the right-hand column.** Every untracked figure is reproduced to
> the digit by the tool over the untracked census's own window, so the two instruments
> agree and the method is the same. **Every difference in the middle column is the eight
> bookings after the window**: lines 25815 to 26122 of the capture, `2026-09-24T10:38:02Z`
> to `2026-09-25T14:05:02Z`, seven `CLOSE` and one `SL` leg, realised -34.3054 in all,
> which is the whole of -192.0271 less -157.7217. The two captures are not the same file;
> the M5k capture is longer. **That the untracked census's capture is a prefix of this one
> is REASONED**, from the tool's reproducing every figure the untracked census states over
> the prefix window; nothing could be compared line by line.
>
> **One figure is worded differently from what it measured.** The untracked *"-6.13%
> exit"* is the exit PRICE's move from the placement's entry limit, `-6.1279%`, which a 2%
> stop and a 4.2121% slip give: `(1 - 0.02) x (1 - 0.042121) - 1`. The REALISED return of
> that booking on its booked entry total is `-6.0340%`, and the tool prints both.
>
> **FLAGGED FOR THE OWNER, NOT ADOPTED: S2's 0.66% default and S7's 0.66% pass level rest
> on a median that is 0.6646% over the window's seven legs and 0.6419% over the census of
> record's eight.** The one added leg slipped 0.0465% and moved the median by 0.0227
> points, which is how sensitive a median of eight values is to a ninth: the range across
> the eight is 0.0291% to 4.2121%. Per the owner's ruling, the default is not changed by
> this commit, and S7's levels (0.05% and 0.66%) stand as ruled.

**REASONED from those figures, and it is the whole argument:** the execution path books
what the venue does, and what the venue does with this strategy's orders is lose money
once fees exist. Lifting the live block on this strategy would make that loss real.
Engine work cannot change it, and N6, U9 and U10 matter only once there is a strategy
worth taking live.

### Exit criterion — the milestone ends in a DECISION, not in code

M5m closes when S7 records one of two outcomes:

- **PASS** — a strategy meets every S7 threshold out of sample. N6, U9 and U10 become
  the next milestone's scope, in the P98 order.
- **FAIL** — none does. The live block stays, and the owner rules the project's
  direction. **A FAIL is a legitimate outcome, not a defect to engineer around.**

### The items, in order

**S0. Reproduce the census with a tracked script.** A read-only tool under `scripts/`
that takes a log path and prints, per booking and in total, the figures above, matching
each `close_booked`, `exit_booked` and `boot_exit_booked` line to its `order_placed` line.
It refuses a path under `logs/`, as `scripts/run_census.py` does. **Acceptance: on the
capture `641778e5…` it reproduces every figure in the census to the digit.** Until then
those figures stay an untracked script's output and must be quoted as such. Two facts
the reviewer's script had to handle: lines before 2026-09-09 carry local time with no
zone, so durations are taken from `entry_bar_time` and `candle_time`; and booking days
are attributed by booking time, as `Portfolio` attributes them, never by candle time.

*Arming condition:* **whoever next renames `_EVENT_CLOSE_BOOKED` or `_EVENT_PLACED` in `execution/executor.py`, `_EVENT_BOOKED` in `execution/reconciliation_driver.py`, or `_EVENT_EXIT_BOOKED` in `engine/modes.py` — the four lines S0 parses.**

> **ANNOTATED AT M5m P99 (AMENDMENT 2), BY THE OWNER'S RULING (b): S0's ACCEPTANCE
> CLAUSE IS REPLACED, BECAUSE THE CAPTURE IT NAMES IS NOT ON DISK.** *"Acceptance: on
> the capture `641778e5…` it reproduces every figure in the census to the digit"*
> cannot be met. MEASURED at P99: the SHA-256 of every `*.log` over 1 MB under
> `F:\trading bot\files\binance-trading-bot` (ten files, `m5j-evidence\` and `logs\`
> among them) and of every `.log` or `.txt` over 1 MB under the user's Downloads,
> Desktop and Documents to depth 3 was computed, and none begins `641778e5`. The
> owner's ruling, verbatim:
>
> "(b) not found: S0's acceptance becomes reproducing the tool's figures on the M5k
> capture trading_bot.m5k-close-20260925T182818Z.log (SHA-256 3f7f551c…). Record its
> output as the census of record. Annotate the untracked figures in NEXT_MILESTONE as
> superseded and unreproducible, citing their SHA. List every figure that differs
> between the two, as the difference is itself a finding. A figure that moves S2's
> defaults (the 0.66% median stop slippage) is flagged for the owner, not adopted."
>
> The capture is on disk with its full digest verified at P99,
> `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`, the digest
> section 19 of `docs/RUN_LEDGER.md` records for it. **What survives:** the rest of
> S0, including the two facts its tool had to handle and its arming condition. The
> untracked figures above stay quoted as an untracked script's output until the commit
> that lands S0's output annotates them.

> **ANNOTATED AT M5m P99 (C4): S0 IS DONE, AND ITS REPLACED ACCEPTANCE IS MET.**
> `scripts/trade_census.py` landed at `cf64d90` and its tests at `27b8724`: 96 cases, and a
> mutation survey of 24 mutations on the final bytes in a disposable worktree, each killing
> exactly the tests predicted (`M5m-016`). The ruling (b) acceptance, the tool's figures
> on `trading_bot.m5k-close-20260925T182818Z.log`, is section 27 of `docs/RUN_LEDGER.md`,
> verbatim, and the untracked figures are annotated beside the census above. Beyond
> (b): over the capture's first 157 bookings, `--until 2026-09-24T03:58:40Z`, the tool
> prints every figure the untracked census states (`M5m-010`).
>
> **What S4 reads against, REASONED by substituting the census of record for "the
> census" and not a new ruling:** a per-trade gross mean inside [-0.2223%, +0.0941%]
> and a trade count within 10% of 165, which is 149 to 181 (10% of 165 is 16.5).
> **What survives:** S0's text and its arming condition, unchanged.

> **ANNOTATED AT M5m P101 (C0), BY THE OWNER'S RULINGS R-A AND R-E OF P100:** S0 is
> accepted on the window reproduction, and the README's scripts list may be corrected.
> The rulings, verbatim:
>
> R-A: "S0 is accepted on the window reproduction over capture 3f7f551c... to
> 2026-09-24T03:58:40Z. The prefix relation to 641778e5... is REASONED unless P100
> measures it."
>
> R-E: "README.md's scripts list may be corrected for release_position.py and
> normalize_ledger_exponents.py (M5m-013) in the next docs commit."
>
> **What stops being true:** nothing in S0's text. The annotation above that made the
> M5k capture's output the replacement acceptance is met by exactly this reading: the
> window reproduction is the acceptance, and R-A's own condition, *"unless P100
> measures it"*, did not come true, because P100 had no path to `641778e5...` and
> measured nothing about the prefix relation (`M5m-027`), so it stays REASONED.
> R-E is carried out in this commit: `README.md`'s architecture tree now names
> `release_position.py` and `normalize_ledger_exponents.py`. **What survives:** S0's
> text, its arming condition and every annotation above.

**S1. Historical klines, downloaded and stored.** Fill `scripts/download_data.py` and
`data/historical.py` — both docstring-only today. MEASURED: `ExchangeClient.get_klines`
in `core/interfaces.py` takes `limit` and no start time, so a date-ranged download needs
either a widened port or a script-side client; **that choice is S1's design question,
and U12 names the same port change**, so whichever lands first settles both. Store per
symbol and timeframe under `backtesting.data_dir`, idempotent on re-run, with gaps
reported rather than filled. At least two years of BTCUSDT and ETHUSDT at 1m, 5m, 1h,
4h and 1d. Data comes from **mainnet** public klines, which need no key; Testnet's book
is not mainnet's, and only mainnet history is long enough.

*Arming condition:* **whoever next edits `main` in `scripts/download_data.py` or adds a start time to `ExchangeClient.get_klines` in `core/interfaces.py`.**

> **ANNOTATED AT M5m P99, BY THE OWNER'S RULINGS: THREE SENTENCES OF S1 NO LONGER
> DESCRIBE ITS SCOPE.** The rulings, verbatim:
>
> "S1 also downloads Testnet klines for every window the census covers. S4 calibrates
> on Testnet klines; S5 to S7 run on mainnet klines."
>
> "The history is all available mainnet history for BTCUSDT and ETHUSDT, not two
> years. S7's trade count is over the whole out-of-sample window and may pool both
> pairs for one candidate."
>
> "A script-side public client, GET only and keyless. ExchangeClient.get_klines is
> unchanged in M5m."
>
> **What stops being true:** *"At least two years of BTCUSDT and ETHUSDT"*, which
> becomes all the history the venue's public klines hold; *"Data comes from
> **mainnet** public klines"* as S1's only source, since Testnet klines are now
> downloaded as well, for S4 alone; and the sentence naming *"a widened port or a
> script-side client"* as an open choice, which the third ruling closes in favour of
> the script. **U12 is NOT settled by it**: the port is unchanged, so `get_klines`
> still takes `limit` and no start time and U12 stays open exactly as written.
> **What survives:** the per-symbol, per-timeframe store, idempotence on re-run, gaps
> reported rather than filled, and the timeframes listed.

> **ANNOTATED AT M5m P101 (C0), BY THE OWNER'S RULINGS R-G AND R-H:** S1 stores monthly
> archive files only, and the Testnet path leaves S1. The rulings, verbatim:
>
> R-G: "S1 stores monthly archive files only, from each series' first month through
> 2026-09, the last complete month. No daily files. The Testnet REST path is not built
> in S1; it belongs to S4, after B2 is measured."
>
> R-H: "The download of the monthly zips and their CHECKSUM files from
> data.binance.vision for BTCUSDT and ETHUSDT at 1m, 5m, 1h, 4h and 1d is authorised,
> once, in commit C4."
>
> **What stops being true:** the first ruling quoted in the annotation above, *"S1 also
> downloads Testnet klines for every window the census covers"*, and that annotation's
> *"since Testnet klines are now downloaded as well, for S4 alone"*: S1 downloads no
> Testnet klines, and the unmeasured question of what Testnet retains (`M5m-032`) is
> S4's to answer first. The source is the venue's bulk archive, which P100 measured
> (`M5m-028` to `M5m-031`); the keyless REST path stays available to S4. **What
> survives:** the script-side keyless client in `Q1` for whatever S4 builds, the port
> and U12 untouched, the per-symbol and per-timeframe store under
> `backtesting.data_dir`, idempotence on re-run, and gaps reported rather than filled.

> **ANNOTATED AT M5m P101 (C3): S1'S ARMING CONDITION'S FIRST HALF HAS FIRED AND THIS
> COMMIT DISCHARGES IT.** The condition reads *"whoever next edits `main` in
> `scripts/download_data.py`"*, and C3 replaces that file's stub with the downloader
> (`scripts/download_data.py`, tests in `tests/unit/test_download_data.py`), over
> `trading_bot.data.historical` from C1 and C2. Its `main` is now `sys.exit(run(...))`;
> `run` takes `--through` (required), `--symbols`, `--intervals`, `--data-dir` and
> `--dry-run`, stores monthly files only and is idempotent, with no Testnet and no
> REST path (R-G). **The second half, *"adds a start time to
> `ExchangeClient.get_klines`"*, has NOT fired and is REAFFIRMED:** the port is
> unchanged, and `U12` stays open exactly as written. **What survives:** the item's
> store, idempotence and gaps-reported rules, which the downloader and
> `HistoricalStore.coverage` now implement. **What is still to come:** the download
> itself, authorised once in C4 (R-H), whose record is `docs/RUN_LEDGER.md` section 28.

> **ANNOTATED AT M5m P101 (C4): THE DOWNLOAD WAS MADE AND IS INCOMPLETE, SO *"What is
> still to come: the download itself"* IS PAST AND ITS GOAL IS NOT MET.** The 1,100
> monthly zips were listed and 980 were stored, each verified against its venue
> checksum; **120 were refused** by the importer's close-time rule (a row's close time
> must equal its open time plus the interval less one millisecond), none for a checksum or
> a transport fault. The two daily series are complete; 1m, 5m and 1h lack 14 months each
> and 4h lacks 18, for both symbols, and `rows + missing == grid` holds exactly on all ten
> series. The refused shapes are in `docs/RUN_LEDGER.md` section 28. **AN OWNER DECISION
> IS NEEDED BEFORE S2 CAN RELY ON THIS DATA:** relax the rule, normalise the close time,
> quarantine the irregular rows as gaps, or keep refusing; the first three change code R-F
> surveyed and need the zips fetched again, which R-H's *"once"* does not cover. Until it
> is made, 14 of 110 months of the minute-scale series are absent. **What survives:** the
> store's layout, idempotence (a re-run fetches only the 120 absent months), gaps reported
> and never filled, and the arming condition's discharge above.

**S2. The backtest engine, on the live decision path.** Fill `backtesting/engine.py`.
**It drives the same `Strategy.generate_signal` and the same `RiskManager.evaluate`**,
the manager taking an injected `Clock` and a provider over historical bars — the M4
seams exist for exactly this, and *"a signal leaves the strategy complete, so backtest
and live share one code path"*. Fill model, each item a parameter with the stated
default:

- **Entry:** fills at the intent's `entry_limit` only if the next bar trades through it,
  else the `FOK` is refused, as live.
- **Protection:** triggered **intrabar** from the bar's high and low, which Q-C names as
  this design's largest cost (`docs/QC_PROTECTIVE_ORDERS.md`). When one bar touches both,
  **the stop wins**, as `should_exit` already decides. Stop slippage beyond the trigger is
  a parameter, defaulting to the census's median of **0.66%** (the fourth of the seven
  measured legs; same untracked script, so S0 confirms it), and never zero.
- **`CLOSE`:** a `MARKET` sell at the next bar's open plus slippage.
- **Fees:** charged on both legs at `backtesting.fee_percent`, quote-denominated in the
  ledger, per the denomination invariant.

**The money rule binds here.** `BacktestConfig.fee_percent` and `slippage_percent` are
`float` today and are multiplied by money for the first time in S2, so S2 is where they
become `Decimal`, at config load, per *"a config field becomes `Decimal` at the milestone
that first multiplies it by money"*.

*Arming condition:* **whoever next edits `_cmd_backtest` in `main.py` or `BacktestConfig` in `config/models.py`.**

> **ANNOTATED AT M5m P99, BY THE OWNER'S RULINGS: S2's ENTRY AND PROTECTION BULLETS
> ARE SHARPENED, AND ONE SENTENCE IN EACH IS REPLACED.** The rulings, verbatim:
>
> "The entry fills at the next bar's open plus slippage, only if that price is at or
> below entry_limit; otherwise it is refused, as the live FOK is. It never fills later
> in the bar."
>
> "Slippage is charged on both protective legs, the take-profit included, because
> both are market orders once triggered."
>
> **What stops being true:** the Entry bullet's *"fills at the intent's `entry_limit`
> only if the next bar trades through it"*, which is replaced by the first ruling: the
> fill price is the next bar's open plus slippage, never `entry_limit` itself and
> never a later price inside the bar. And the Protection bullet's *"Stop slippage
> beyond the trigger is a parameter"*, which read as a stop-only charge: it is charged
> on the take-profit leg as well. **What survives:** the intrabar trigger from the
> bar's high and low, *"the stop wins"* when one bar touches both, the `CLOSE` and
> Fees bullets, and the money-rule paragraph. **The default of 0.66% rests on a figure
> that is unreproducible** (S0's annotation above), and S7's annotation below says how
> it is used: every candidate is reported at 0.05% and at 0.66%.
>
> **ANNOTATED AT M5m P99 (C4): *"the fourth of the seven measured legs; same untracked
> script, so S0 confirms it"* IS NOT WHAT S0 MEASURED ON THE CENSUS OF RECORD, AND IS
> FLAGGED FOR THE OWNER.** Over the window's seven legs the tool's median is `0.6646%`,
> which is the fourth of seven and rounds to `0.66%`. Over the census of record's eight
> legs it is `0.6419%`, the mean of the fourth and fifth (`docs/RUN_LEDGER.md` section 27).
> Nothing is adopted: the default and S7's pass level stay at `0.66%` as ruled, and the
> flag with its reading is under the census paragraph above.

>
> **ANNOTATED AT M5m P101 (C0), BY THE OWNER'S RULINGS R-B (P100) AND R-B2 (P101):
> THE DEFAULT IS 1.20%, AND R-B'S WORD "CONSERVATIVE" IS ANNOTATED, NOT DELETED.** The
> rulings, verbatim:
>
> R-B: "S2's stop-slippage default stays 0.66%, which is conservative against the census
> of record's 0.6419%. S2 also reports, for information and not as a gate, one arm at
> the mean of the census of record's SL-leg slippages."
>
> R-B2: "R-B's word 'conservative' holds against the median only (M5m-034). S7 passes
> only at a stop slippage of 1.20%, the mean of the census of record's eight SL legs
> rounded up. Results at 0.05% and 0.66% are reported for information. S2's default
> parameter is 1.20%. The slippage parameter applies to both protective legs, as P99
> ruled."
>
> **What stops being true:** this item's *"defaulting to the census's median of
> **0.66%**"*; the first S2 annotation's *"it is used: every candidate is reported at
> 0.05% and at 0.66%"*; the C4 annotation's *"the default and S7's pass level stay at
> `0.66%` as ruled"*; and R-B's own *"stays 0.66%"* and its information arm. The
> default is **1.20%**, and the arm at the mean is now the gate, not an extra.
> **R-B's "conservative"** stays standing as the owner's word and is annotated by
> `M5m-034`, MEASURED: the mean of the census of record's eight SL slippages is
> 1.1986% (the tool, `docs/RUN_LEDGER.md` section 27), 4 of the 8 legs exceed 0.66%,
> and the median 0.6419% is the only figure it holds against. **What survives:** the
> intrabar trigger, *"the stop wins"*, the `CLOSE` and Fees bullets, the money-rule
> paragraph and P99's entry ruling.

**S3. Metrics.** Fill `backtesting/metrics.py`: trades, net and gross P&L, fees paid,
win rate, average win and loss, profit factor, maximum drawdown on the equity curve,
daily Sharpe and Sortino ratios, exposure, and holding period. Each figure is `Decimal`
where it is money and states its denominator.

*Arming condition:* **whoever next edits `backtesting/metrics.py`.**

**S4. Calibration against the venue — the backtester's own acceptance test.** Replay
the strategy over the windows the bot actually traded on Testnet, from S1's data, and
compare trade by trade with S0's census. **The backtester is trusted only if its
per-trade gross mean falls inside the census's 95% interval and its trade count is within
10% of the census's.** Divergence is diagnosed, never tuned away: an entry the backtester
takes and the bot did not is a finding about one of them.

*Arming condition:* **whoever next edits the fill model in `backtesting/engine.py`.**

> **ANNOTATED AT M5m P99: *"from S1's data"* NOW NAMES TESTNET KLINES.** By the owner's
> ruling quoted under S1, *"S4 calibrates on Testnet klines"*, for the windows the
> census covers; S5 to S7 run on mainnet klines. **What survives:** the acceptance test
> as written, the per-trade gross mean inside the census's 95% interval and a trade
> count within 10% of the census's, and *"Divergence is diagnosed, never tuned away"*.
> **Which census:** the one S0's annotation above makes the census of record, and not
> the untracked figures it supersedes.

>
> **ANNOTATED AT M5m P101 (C0), BY THE OWNER'S RULINGS R-C (P100) AND R-C2 (P101): S4
> READS AGAINST THE CENSUS OF RECORD, AND HAS A SECOND TEST.** The rulings, verbatim:
>
> R-C: "S4 reads against the census of record (M5m-021 adopted). S4 additionally
> requires that at least 80% of the census's entries are reproduced on the same symbol
> and entry bar, and that every unmatched entry on either side is listed and
> diagnosed."
>
> R-C2: "S4's denominator is the 165 booked entries of the census of record. The 20
> placements the venue did not fill are a second test: S4 reports how many the
> backtester also refuses, and lists and diagnoses every disagreement."
>
> **What stops being true:** the S0 annotation's *"What S4 reads against, REASONED by
> substituting the census of record for 'the census' and not a new ruling"*: it is now
> the owner's ruling (`M5m-021` adopted). **What S4 therefore requires, in full:** the
> per-trade gross mean inside [-0.2223%, +0.0941%]; a trade count within 10% of 165,
> which is 149 to 181; at least 80% of the 165 booked entries (132 of them)
> reproduced on the same symbol and entry bar; every unmatched entry on either side
> listed and diagnosed; and, as the second test, how many of the 20 unfilled
> placements (`M5m-035`) the backtester also refuses. **What survives:** *"Divergence
> is diagnosed, never tuned away"* and the arming condition. S4 depends on Testnet
> klines, whose retention is UNMEASURED (`M5m-032`).

**S5. The baseline — the shipped strategy, honestly.** `sma_crossover` 20/50 on BTCUSDT
1m and ETHUSDT 5m, the committed config, over the full history, net of fees. This is the
number the census predicts to be negative; S5 confirms or refutes it on two years rather
than twenty days.

*Arming condition:* **whoever next edits `strategy` in `config.yaml`.**

> **ANNOTATED AT M5m P99: *"on two years rather than twenty days"* IS NO LONGER THE
> SPAN.** The owner ruled the history to be all available mainnet history for BTCUSDT
> and ETHUSDT (S1's annotation above). **What survives:** the item, and the
> prediction it states, which S5 confirms or refutes.

**S6. Research, under a protocol fixed before the first result is seen.**

- **Split:** the oldest 70% of the history is in-sample, the newest 30% is out-of-sample
  and **is read once per candidate**; walk-forward over the in-sample window for any
  parameter that is fitted.
- **Candidates:** the two shipped strategies at 1h, 4h and 1d; each with a trend filter
  (for example, long only above a 200-period average); and any new strategy, each one a
  registry entry under `strategies/` with its own tests, as today.
- **Every variant tried is recorded**, with its parameters and its in-sample result, in a
  research log under `docs/`. That list is the denominator a multiple-testing judgement
  needs, and a variant tried and not recorded is the one that makes an out-of-sample pass
  meaningless.

*Arming condition:* **whoever next registers a strategy with `register_strategy` in `strategies/registry.py`.**

**S7. The decision gate.** A candidate PASSES only if, **out of sample and net of fees and
S2's stop slippage**, all of these hold:

- profit factor ≥ **1.3**;
- at least **100** trades;
- maximum drawdown no worse than **20%** of the capital it was sized against;
- a positive net result in at least two of the three regimes the owner labels in the
  history — rising, falling, sideways.

The thresholds are the reviewer's proposal and **the owner may rule them before S6
starts, never after a result is seen.** S7's outcome, the candidate, its figures and the
research log's variant count are recorded in `docs/PHASE_HISTORY.md` at M5m's close.

*Arming condition:* **whoever next edits `refuse_live_trading` in `config/settings.py`.**

> **ANNOTATED AT M5m P99, BY THE OWNER'S RULINGS: S7's THRESHOLDS ARE RULED, WITH TWO
> ADDITIONS.** The rulings, verbatim:
>
> "Every candidate is reported at 0.05% and 0.66% stop slippage; it passes only at
> 0.66%. The regime labels are date ranges fixed in the research log before S6's first
> run."
>
> "The history is all available mainnet history for BTCUSDT and ETHUSDT, not two
> years. S7's trade count is over the whole out-of-sample window and may pool both
> pairs for one candidate."
>
> Q3, in the owner's words and unquoted: the thresholds as amended above.
>
> **What stops being true:** *"The thresholds are the reviewer's proposal and the
> owner may rule them before S6 starts"*, since the owner has ruled them: the four
> thresholds above stand as amended here. And *"the three regimes the owner labels in
> the history"* is made exact: the labels are date ranges, written into the research
> log before S6's first run. **What survives:** every threshold's figure, the
> out-of-sample and net-of-fees conditions, and the recording of S7's outcome in
> `docs/PHASE_HISTORY.md` at M5m's close.

>
> **ANNOTATED AT M5m P101 (C0), BY THE OWNER'S RULINGS R-D (P100) AND R-B2 (P101): THE
> PASS LEVEL IS 1.20%.** The rulings, verbatim:
>
> R-D: "S7's thresholds are adopted as proposed: PF >= 1.3, >= 100 trades, drawdown <=
> 20%, positive net in at least two of the three regimes."
>
> R-B2, in part: "S7 passes only at a stop slippage of 1.20%, the mean of the census of
> record's eight SL legs rounded up. Results at 0.05% and 0.66% are reported for
> information."
>
> **What stops being true:** the first S7 annotation's *"Every candidate is reported at
> 0.05% and 0.66% stop slippage; it passes only at 0.66%"* (a P99 ruling, verbatim
> above): a candidate is reported at 0.05%, 0.66% and 1.20%, and **passes only at
> 1.20%**, the first two being for information. **What survives:** every threshold's
> figure, which R-D adopts as proposed; the regime labels as date ranges fixed in the
> research log before S6's first run; the pooling of both pairs; and the recording of
> S7's outcome in `docs/PHASE_HISTORY.md`.

### What M5m does NOT do

- **No engine work beyond defects.** A defect a run surfaces is fixed under the usual
  rules; nothing else in `execution/`, `exchange/` or `engine/` moves. The carried items
  below are carried, not worked.
- **N6, U9 and U10 are deferred to the milestone after a PASS.** Their text and arming
  conditions are unchanged.
- **No paper simulator.** `paper/simulator.py` stays a stub: Testnet already plays that
  part, and S4 is what ties the backtester to it.
- **The Testnet bot may keep running as a soak.** Its runs are recorded in
  `docs/RUN_LEDGER.md` as before. They are evidence about the engine and no longer about
  the strategy; S5 is that.

### Questions for the owner, before S2

- **Q1.** S1's port question: widen `ExchangeClient.get_klines` with a start time, or
  download through a client in the script?
- **Q2.** Whether `backtesting/` and S6's research scripts carry the full two-phase and
  mutation-survey discipline, or a lighter one. **Not ruled here** — `CLAUDE.md` holds the
  rules and this file may not move one. Research code changes no money and can be
  rewritten; the reviewer's recommendation is the gate plus unit tests, with mutation
  surveys reserved for S2's fill model, the one component whose error is silent.
- **Q3.** S7's thresholds, if they are to differ from the proposal above.

> **ANNOTATED AT M5m P99: Q1, Q2 AND Q3 ARE RULED BY THE OWNER, AND THE HEADING'S
> *"before S2"* IS MET.** The rulings, verbatim:
>
> Q1: "A script-side public client, GET only and keyless. ExchangeClient.get_klines is
> unchanged in M5m."
>
> Q2: "The gate and unit tests for all M5m code. Mutation surveys for S2's fill model
> and S3's metrics."
>
> Q3, in the owner's words and unquoted: the thresholds as amended above.
>
> **What stops being true:** Q2's *"Not ruled here"*. It is ruled, and it is the
> reviewer's recommendation as the owner adopted it; `CLAUDE.md` is not amended by it,
> and the survey discipline it names is the one `CLAUDE.md` already holds. **What
> survives:** the questions as the record of what was asked.

>
> **ANNOTATED AT M5m P101 (C0), BY THE OWNER'S RULING R-F: Q2's SURVEY SCOPE IS
> EXTENDED BY TWO FUNCTIONS.** The ruling, verbatim:
>
> R-F: "The time-unit normaliser and the gap detector in data/historical.py get a
> targeted mutation survey under CLAUDE.md's procedure. Nothing else in S1 is surveyed
> (Q2)."
>
> **What stops being true:** Q2's *"Mutation surveys for S2's fill model and S3's
> metrics"* as the whole of the surveyed set. It is now those two and, from S1, the
> time-unit normaliser and the gap detector, the two silent-failure sites `M5m-038`
> named. **What survives:** the gate and unit tests for all M5m code, and no other S1
> code surveyed.

---

## M5m's SCOPE — NOT DECIDED; reserved to the project owner

> **ANNOTATED WHEN M5m's SCOPE WAS DECIDED: THIS SECTION'S HEADING AND ITS FIRST TWO
> PARAGRAPHS ARE NO LONGER TRUE.** The scope is decided, by the owner, in the section
> above, and P98's order — *"the items that block live trading come first"* — is
> superseded for M5m: N6, U9 and U10 are deferred to the milestone after S7 passes.
> **What survives:** the list below as an inventory of the carried candidates, each
> with its condition; the U10 discrepancy, unruled and deferred with its item; and the
> closing sentence, that M5m's scope is not a fix for anything M5l's run found.

**The rotation does not choose M5m's scope.** It lists the candidates, each carried
below with its condition, and orders them only where the owner has already ruled an
order or the tree decides one.

**The owner's order for the first three, ruled at P98: the items that block live
trading come first.**

1. **N6 -- base-asset quantity netting in the entry sizing and placement pipeline**,
   with entry-fee deduction (A1). One of the two preconditions the owner's M5k ruling
   names for lifting the live-trading block. Nothing in `src/` nets a fee out of a
   quantity.
2. **U9 -- how the non-zero fee capture on a live-quoted venue is to be met.** The
   other precondition. Every commission in every capture is `0.00000000`, M5l's
   observation run included (`docs/RUN_LEDGER.md` section 26).
3. **U10 -- the QC review of the protective order type before live trading**, from
   the stop-loss that filled about 4.2 percent beyond its trigger (`M5l-170`).
   **A DISCREPANCY FOR THE OWNER:** P98 lists U10 among the items that block live
   trading, and the tree records the opposite. The owner's P87 ruling, quoted at N6
   below, says the review *"is not a gate by the owner's ruling; it is marked for QC
   before live trading"*. Both cannot stand, and the owner is the one who rules
   which.

**The rest, in no order the rotation has the right to give:**

- **Rulings the owner holds:** U7 with P-3n (does the confirm step query three legs or
  two, five calls against four); U11 and U12, deferred under the P91 rulings; U0 to U6
  and U8, carried from earlier milestones.
- **Work, each with its condition:** P-3i's request weight (needs the port to carry
  response headers); P-3m's starvation and churn; K4, the cause of the 229 s stall
  (`M5l-198`); K5, the natural-gap rate of a pair other than BTCUSDT or ETHUSDT
  (`M5l-202`, ruled at P98); `M5i-104`'s sweep, 17 sites; K3, four pre-existing false
  sentences in `src/` and `tests/`; K1 and K2, the residues of P-3k.
- **Carried small items:** N1 to N5, A1 to A3, A5, A6, `M5i-065`, `M5i-095`,
  `M5i-126` and the `_go_naked` family's fourth candidate.
- **Blocked:** the trailing-stop milestone, on Q-C section 3's leg set.

**What M5m's scope is NOT: a fix for anything M5l's observation run found.** It found
nothing to fix. See *M5l's CLOSE* below.

---

## Before M5m starts — the namespace

**IDs are `M5m-NNN`: three digits, zero-padded, starting at `M5m-001`.** Not letters.
`CLAUDE.md` prescribes the digit form in its rescued rule 2; this paragraph is carried
forward so that a reader of this file meets it first. **A rotation that rewrites this
file must carry this paragraph forward.**

**M5l's range is closed by the tag `milestone/M5l`**, applied to the closing commit of
M5l's rotation, and its count is read with one command and never written here:

```
.venv\Scripts\python.exe scripts/check_findings.py milestone/M5k..milestone/M5l M5l
```

The M5m namespace is to be confirmed empty by the same tool, over
`milestone/M5l..HEAD`, before `M5m-001` is written. **A tag is a ref and `git push`
does not carry it**: the owner pushes `milestone/M5l` as its own act.

> **THE M5i RESERVED BLOCK IS STILL RESERVED.** `M5i-068`, `M5i-071` and `M5i-073` are
> cited in the tree and declared nowhere. That is deliberate and the extractors report
> it every time as `cited-not-declared`; it is not a defect to be closed by inventing
> declarations for them.

> **AND THREE MORE M5i IDS ARE UNRECORDED ANYWHERE (`M5k-018`).**
> `scripts/check_findings.py` reports the M5i range's gaps as 68 through 73. The
> reserved block accounts for three of them; `M5i-069`, `M5i-070` and `M5i-072` appear
> in no commit message and no tracked file, and no document mentions them. They are not
> to be invented either.

> **`9f364dd` IS BLOCKLESS, KNOWN AND DECLARED (`M5l-031`).**
> `scripts/check_findings.py` reports `blockless commits : [9f364dd]` on every run over
> a range that contains it, and exits non-zero for it. It is the owner's commit
> *"config: operator settings for testnet runs"*, pushed during P58 with no `Findings:`
> block; pushed, so it cannot be amended. **It belongs to M5l's range and not to M5m's**:
> a run over `milestone/M5l..HEAD` will not list it. That is deliberate to leave
> standing; it is not a defect to be closed by rewriting history or by inventing a block.

> **ANNOTATED AT M5m P99: THE NAMESPACE WAS NOT EMPTY, AND ONE MORE KNOWN COMMIT HAS NO
> BLOCK.** *"The M5m namespace is to be confirmed empty by the same tool, over
> `milestone/M5l..HEAD`, before `M5m-001` is written"* was run at P99 and read
> `declared : 3`, `max : 3`, no gap, no duplicate and nothing cited and undeclared:
> `70690c1` (*"docs(next): M5m decided -- validate a strategy before anything else"*)
> declares `M5m-001` to `M5m-003`. **The owner ruled that numbering continues at
> `M5m-004`**, and the first commit after it, `c0d0948`, declares `M5m-004`.
>
> **`934eb45` IS BLOCKLESS, KNOWN AND DECLARED.** MEASURED at P99:
> `scripts/check_findings.py milestone/M5l..HEAD M5m` reports
> `blockless commits : [934eb45]`, and no other. It is the merge of the owner's PR
> #2 (*"Merge pull request #2 from atul-biswash/claude/keen-sagan-ehal28"*), carries
> no `Findings:` block, and is pushed, so it cannot be amended. **`70690c1` is NOT
> blockless**, though the owner's P99 amendment allowed for it: it carries a block, and
> its git author is `Claude`, the owner having merged it. Like `9f364dd` above,
> `934eb45` is to be left standing; the extractor exits non-zero over any range that
> contains it, and that is not a defect to be closed by rewriting history or by
> inventing a block. Unlike `9f364dd`, it **belongs to M5m's range**, so every M5m
> run will list it.

---

## THE CENTRAL FACT — read this before anything else

**M5l showed the committed code running, end to end, and found nothing wrong in it.
That is evidence about six round trips on one pair, and it is not evidence about live
trading.** Against the capture
`trading_bot.m5l-observation-run-pid24980.log`, SHA-256
`023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb`, from a deployment
clone of the pushed commit `51a5f27` (`docs/RUN_LEDGER.md` section 26):

- **What it established.** 8.356 h; six BTCUSDT round trips, each booked with its
  `entry_quote_total` at exponent -8 and equal to the venue's fills by GET; a ledger
  chained from the normaliser's output to the end store with no difference to the last
  digit; and none of the feed-health events, with the venue's own klines showing no
  missing interval.
- **What it did not.** Every commission it saw is `0.00000000`, so no non-zero fee was
  ever netted outside a test and the live gate's fee capture is unmet. No protective
  leg filled, ETHUSDT never opened a position, and nothing restarted. The feed-health
  emitters were quiet because nothing happened to them, which measures no false positive
  and not a firing.
- **The live-trading block stands.** `refuse_live_trading` is unchanged, and N6's two
  preconditions are exactly what remains. P-3k's gate was satisfied by the owner at P87.

**The standard of evidence still holds**, and it lives in `CLAUDE.md`: *"A CAPTURE-BOUND
CLAIM CARRIES ITS DIGEST INLINE, IN THE SENTENCE."*

---

## M5l's CLOSE — the milestone, its run, and the owner's rulings at the rotation

**The tag.** `milestone/M5l`, an annotated tag at the closing commit of this rotation,
created and verified to resolve there. The first M5l commit is `fdf8d7b`; the last is the
closing commit, which `docs/PHASE_HISTORY.md`'s M5l entry names as *"this commit"* and
which carries the entry's own count. **The findings count is read with
`scripts/check_findings.py milestone/M5k..milestone/M5l M5l` and is not written here.**
`docs/PHASE_HISTORY.md` holds the milestone's build log; `docs/RUN_LEDGER.md` holds its
runs, the last of them section 26.

**The owner's rulings at the rotation, P98, as the prompt named them:**

- *"M5l-255 resolved by M5l-209."* The 15 ledger figures at exponent -10 are explained by
  `M5l-209`'s measurement: the entry term was `average_price x quantity`, and 103 of the
  106 booking lines it replayed were single-price entries at price exponent -2, which
  times a quantity at exponent -8 is -10; the exponent -24 bookings were entries filled
  across 6 to 8 price levels. So the origin that `docs/RUN_LEDGER.md` section 26 left
  UNMEASURED is accounted for by the cause C48 removed. The replay is MEASURED and the
  exponent arithmetic is REASONED from it.
- *"M5l-202 left open with the arming condition 'whoever next enables a pair other than
  BTCUSDT or ETHUSDT measures its natural-gap rate before trading it'."* Carried as K5.
- *"The OBS note lines are dropped from the run sheet."* `arm_notes.txt` held no `OBS
  launch` or `OBS stop` line after the observation run (`M5l-256`), and the sheet no
  longer asks for them. The start of a run is recorded from its `boot_provenance` line.
- *"Every standing authority moves into CLAUDE.md (M5l-244)."* Done at `810eaa3`; the
  section here is a pointer.

**The observation run, as recorded at P97 (C56)**, carried here verbatim from the scope
section it was annotated into:

> **ANNOTATED AT M5l P97 (C56): THE OBSERVATION RUN AT `51a5f27` IS RECORDED, AND
> NO OBSERVATION NEEDS A RULING BEFORE THE ROTATION.** From a deployment clone of
> the pushed commit, `F:\trading bot\deploy\51a5f2711a09`, pid 24980 ran
> `2026-10-03T20:08:24Z` to `2026-10-04T04:29:50Z` (8.356 h from engine start to
> `engine_stopped clean_shutdown=True`), after the owner's normaliser apply at
> `20:08:10Z`. `docs/RUN_LEDGER.md` section 26 holds the record, each figure beside its
> read, against the log whose SHA-256 is
> `023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb`. **What it
> measured:** six strategy-driven BTCUSDT round trips, six `close_booked` lines, each
> with `entry_quote_total` present, `realised` at exponent -8 and equal in value and
> exponent to the venue's fills by GET (6 of 6, `M5l-253`); a ledger chained from the
> normaliser's `after` to the end store with no difference to the last digit
> (`M5l-254`); the account's USDT up by exactly the six `realised` summed, 0.78557830;
> 7 `WARNING`s all accounted for and no `ERROR` or `CRITICAL`; and, on the committed
> pairs, none of `bars_gap_detected`, `buy_refused_bars_gap`, `bars_contiguous_again`,
> any watchdog line or `stream_transient_error` (`M5l-250`, `M5l-251`, `M5l-252`).
>
> **What it did NOT measure, so the quiet is not a pass for those emitters.** Those
> events are silent because nothing happened to emit them: the venue's own klines by GET
> show no missing interval and no zero-trade bar in the window on either pair, so
> `M5l-202`'s question (does Binance omit a kline for an interval with no trades)
> was not exercised and stays UNMEASURED for an illiquid pair, and `M5l-198`, the cause
> of the 229 s stall, stays UNMEASURED because nothing stalled. No protective leg
> filled, ETHUSDT never opened a position, nothing restarted, and the boot resolved no
> record, so the paths P-3k built ran only in the earlier A1 and A4 arms.
>
> **Two process points, neither a defect in the tree.** The start record was written
> after the log was read, the shape `M5l-051` named, and `arm_notes.txt` holds no
> `OBS launch` or `OBS stop` line (`M5l-256`). **The owner's choices, none of them
> blocking the rotation:** whether to measure `M5l-202` deliberately on a thin
> Testnet pair; whether to chase the origin of the 15 ledger figures that sat at
> exponent -10 (`M5l-255`); and whether the run sheet's two note lines are worth
> keeping given they were not written. **What survives:** the rest of this section.
> `decision=halt` stays unobserved: all 6 of this run's close plans read `decision=sell`.
> The table below keeps its own denominators against its own captures, and this run's
> are not summed into them.

> **ANNOTATED AT M5l P98 (R7): THREE OF THE OWNER'S CHOICES LISTED ABOVE ARE NOW RULED.** *Whether to measure `M5l-202` deliberately on a thin Testnet pair*: ruled as K5's condition, that a pair other than BTCUSDT or ETHUSDT is measured before it is traded. *Whether to chase the origin of the 15 ledger figures at exponent -10*: moot, `M5l-255` being resolved by `M5l-209` (above). *Whether the run sheet's two note lines are worth keeping*: ruled, they are dropped. **What survives:** every measurement above.

---

## THE OWNER'S RULINGS RECORDED INSIDE THE STRUCK ITEMS, VERBATIM

Seven paragraphs in the items this rotation strikes were the ONLY place in the tree where an owner's ruling stood in the owner's own words (`M5l-099`, `M5l-116` and `M5l-208` are what happens to a ruling held only as reported speech). They are lifted here **unchanged**, from `docs/NEXT_MILESTONE.md` at `9fc8b8d`, so that none of them lives only in git history. The rest of the struck items' text, their annotations and designs, is in git history at that commit.

> **THE OWNER'S P-3 ORDER, ruled at M5l P76 (C27).** The work runs in this
> order:
>
> 1. **P-3k**, design first. The design decides where P-3b's retry state
>    lives and whether `Position` carries P-3h's entry quote total.
> 2. **P-3g.**
> 3. **P-3o, merged with P-3i and with P-3m's deferral log**, using sketch
>    (a): `max_calls = max(max_open_positions, L + 1)`.
> 4. **P-3l.**
> 5. The remaining SILENT and DOC items, in P75's order: P-3e, P-3d with
>    P-3j, P-3a with P-3b, P-3c, P-3h, then P-3f. P-3n is not in this list,
>    because it goes to U7 (below).
>
> **Merges of the work, not of the entries:**
>
> - P-3a with P-3b: the same `_settle`, and one design for the Q path's
>   refusal lines and its bound.
> - P-3d with P-3j: the same hold-to-stale path. P-3j's end-to-end test is the
>   natural test for P-3d's new line.
> - P-3n into U7: it is a ruling, not code.
>
> Each entry keeps its text and its arming condition until the work that
> resolves it lands.

> **RECORDED AT M5l P93 (C47): THE OWNER'S Q12, VERBATIM, CONFIRMED BY THE OWNER
> AT P78. THIS RESOLVES `M5l-208`.** P92 found that no tracked file and no
> commit body held the text of the question P78 confirmed with *"Q12 and Q13
> confirmed"*, so the ruling existed only as reported speech. Its text, as the
> owner supplied it at P93:
>
> *"12. In-memory homes for P-3b and P-3h. P-3b's retry count: a memory-only
> field on Position beside settlement_hold, since the driver stays stateless
> (M5e). P-3h's entry quote total: a memory-only field on Position, set by the
> dispatch GET and the boot GET. Neither is recorded. Confirm."*
>
> It is the same ruling as P-3k's R2, *"The record holds only requested
> values. ... P-3b's retry count lives in memory and resets on restart."*, and
> is cited by content and by this record, never by the bare label. **What it
> governs:** `Position.failed_settlement_passes` (C47) and, in C48, the entry
> quote total. Neither is in `store.PositionRecord`.

> **P-3k IS CLOSED, BY THE OWNER'S RULING AT M5l P87 (C38) -- THE FIRST
> SENTENCE'S GATE, *"stays closed until the supervised run's arms A1, A2 and
> A4 are recorded"*, IS DISCHARGED.** The ruling, verbatim: *"The P-3k gate is
> satisfied: A1 (hard kill, restore), A2 (protective fill while down, booked at
> boot) and A4 (protection cancelled while down, R3 sells once) passed on the
> supervised Testnet run of 2026-10-01/02, A1 and A2 at d1074c6 and A4 at
> 5e22bc6. A2's Ctrl+C stop does not change the path it tests. P-3k no longer
> blocks live trading. The fee-capture and base-asset-netting gates remain, so
> live trading stays blocked."* The arms are recorded in `docs/RUN_LEDGER.md`
> section 25 (`M5l-168`, `M5l-169`). **What survives:** the item's history and
> every annotation beneath it, the *"Live trading additionally stays blocked
> until an open position survives a restart"* ruling at P76 as the record of
> what the gate was, and **live trading itself, which stays blocked by N6's two
> remaining preconditions** -- the non-zero fee capture and base-asset
> netting. Closing P-3k lifts one of three gates and none of the code block:
> `refuse_live_trading` is unchanged.

> **THE OWNER'S RULING, VERBATIM, M5l P76 (C27):** *"Live trading
> additionally stays blocked until an open position survives a restart,
> clean or by power cut, with its protective fills booked to the ledger."*
> Until P76 the tree recorded this gate only as the owner's addition at P61,
> in reported speech (`M5l-099`). The ruling also states what lifting it
> requires: survival of both a clean restart and a power cut, AND the
> protective fills booked.

- **Deployment, verbatim:** "No deployment or supervised run may use any
  commit from 131f1c9 up to C32b's: records are written from C30, and boot
  reads them only from C32, so each boot's first save erases them (today's
  behaviour, not a regression)."
  > ANNOTATED AT M5l P81 (C32a): *"each boot's first save erases them"* is
  > no longer true of a record not beside a pending close; the boot now
  > restores or drops it. The restriction itself stands, through C32b.
- **The accepted residual, verbatim:** "One kill during one ambiguous
  placement write loses that position's durability (M5l-110); accepted by the
  owner at P78 (Q2(b))." The ambiguous-placement path, `_persist_dropping`, is
  unchanged by C30.

**A POSITION RECORD BESIDE A PENDING CLOSE -- the owner's rulings, P81
amendment 1.**

- *Interim, C32a, verbatim:* "a position record whose symbol has a pending
  CLOSE record is neither classified nor restored. It is left out of the
  classifier's input, and boot's save does not carry it, which is today's
  behaviour. Site B handles the close as today."
- *Final design, for C32b, verbatim:* "For a close record beside a position
  record, read the close's sell by the client id in the close record:"
  - "FILLED: settle at boot. On success, book ledger-only (I7), satisfying
    Q13. On FeeUnresolvable, keep a held record with no Position (Q5(b),
    M5l-112). Remove the close record either way."
  - "Absent, or terminal and unfilled, with the legs CANCELED and base >=
    quantity: RestoreAndClose, dropping the close record, so exactly one sell
    goes out."
  - "List live: Restore; the close record's fate is decided in P82 after STEP
    0 reads Site B."
  - "Anything else: RefuseBoot."
  - "The two restart tests' assertions change once, in C32b."
- Why it was needed (`M5l-126`): the bot's own close cancels the protective
  legs by design, so the classifier reads that list as `Gone` or
  `RestoreAndClose`, and Q13 collides with Q5(b) on the same disk shape.

**Not a gate on live trading**, by the project owner's ruling at P65.

> **THE OWNER'S RULING, VERBATIM, M5l P76 (C27):** *"The market-data outage
> is not a gate on live trading, because venue-side protection remains in
> force through it."* Until P76 the tree recorded the P65 ruling above only
> in reported speech (`M5l-099`).

---

## RESOLVED AT M5l -- one index line each

Each item's full text is in git history at `9fc8b8d` and in `docs/PHASE_HISTORY.md`'s M5l entry. An item resolved only in part is indexed here AND carried below with its residue and its condition: P-3i and P-3m, whose resolved halves are `4c2e55c` (C43) and `b29a658` (C42); and P-3n, which is a ruling and not code.

- **P-1, startup provenance** -- resolved by `fdf8d7b`, `ac1162d`, `d74f78b`, `f8898de` and `63d4615`, with `c2cab79` (every refusal names its cause); the accepted verdict is logged on the boot of each of the four deployment clones whose logs were read (`06089d5`, `d1074c6`, `5e22bc6` and `51a5f27`). Findings: `M5l-001` to `M5l-032`, the provenance design.
- **P-2, staleness against the reconciliation dedup interval** -- CLOSED by the owner's re-ruled text at P74, `5721a5c`, after `25dbc61`, `5d6f115`, `517348f`, `6e7c9f2`, `4a094c5`, `f20e839`, `90355df`, `cf37cda`, `9f188c4`, `40a9e67` and `127be9a`. Findings: `M5l-056` to `M5l-097`, the staleness bound and its derivation.
- **P-3a, a failed supply reported as a failed settlement** -- resolved at `441b5b2` (C47). Findings: `M5k-107`, `M5l-211`, `M5l-212`.
- **P-3b, the driver's unbounded re-refusal** -- resolved at `441b5b2` (C47): an unreadable settlement is held after five failed passes, and a restart is that hold's only retry. Findings: `M5k-104`, `M5l-098`, `M5l-211` to `M5l-213`, `M5l-216`, `M5l-220`.
- **P-3c, a `require_bookable` raise after the sell** -- resolved at `bf6f9a8` (C53, Site A) and `51a5f27` (C55, Site B): held, one `CRITICAL`, never counted as a failed read. Findings: `M5k-110`, `M5l-239`, `M5l-240`, `M5l-245` to `M5l-247`.
- **P-3d, a held position's silent refusal text** -- resolved at `e3ff798` (C51). Findings: `M5k-083`, `M5l-235`, `M5l-236`.
- **P-3e, a close labelled BOOKED that wrote nothing** -- resolved at `cdc6c2e` (C50) and, for its wording, `51a5f27` (C55). Findings: `M5k-073`, `M5l-232` to `M5l-234`, `M5l-248`.
- **P-3f, eleven tests tripping the disagreement warning** -- resolved at `b5975ff` (C52); the item's own figures were stale. Findings: `M5k-111`, `M5l-237`, `M5l-238`.
- **P-3g, a pair quoted outside the base currency** -- resolved at `0c1a802` (C40): the boot refuses it. Findings: `M5k-102`, `M5l-179` to `M5l-181`.
- **P-3h, four realised figures at exponent -24** -- resolved at `4341c5c` (C48, the cause and the fix) and `f9e606e` (C49, the normaliser). The active store carried 5 figures at -24 and 15 at -10 and was normalised losslessly at the owner's apply on 2026-10-03T20:08:10Z, recorded at `7489581`; the -10 figures are accounted for by `M5l-209`, by the owner's P98 ruling. Findings: `M5k-121`, `M5l-100`, `M5l-209`, `M5l-210`, `M5l-214`, `M5l-222` to `M5l-229`, `M5l-255`.
- **P-3j, no end-to-end test drives a hold to stale** -- resolved at `e3ff798` (C51). Findings: `M5k-090`, `M5l-235`, `M5l-236`.
- **P-3k, a restart orphans an ordinary open position** -- CLOSED by the owner's ruling at P87 (`8403673`, C38), its arms A1, A2 and A4 recorded in `docs/RUN_LEDGER.md` section 25. Built in `131f1c9`, `4b57f34`, `989edfc`, `f7ebce9`, `5a2307c`, `fa06d77`, `a14aa6c`, `4f2cc49`, `2081389`, `cde0fb0`, `e4004ab`, `d1074c6`, `244aa6b`, `d95cb5e`, `5e22bc6` and `5709b04`. Residues are carried as K1 and K2, and the deferred items as U11 and U12. Findings: `M5l-044`, `M5l-045`, `M5l-102` to `M5l-175`.
- **P-3l, a market-data outage stops reconciliation** -- CLOSED as reported, measured and guarded, by `a519d9e` (C44, gap detection), `68ffa47` (C45, the watchdog) and `1046a01` (C46, transient errors), the stopped reconciliation accepted under P76. Carried: K4 (the stall's cause), K5 (the natural-gap rate), U11 and U12. Findings: `M5l-055` to `M5l-063`, `M5l-196` to `M5l-207`.
- **P-3o, the call cap is the position limit** -- resolved at `31281fa` (C41): the cap is `max(max_open_positions, L + 1)`. Findings: `M5l-086`, `M5l-087`, `M5l-101`, `M5l-183`, `M5l-184`.

---

## NEW CARRIED ITEMS, AT M5l's CLOSE

Each is the residue of an M5l item that was closed in the main and left something
standing, written once here so that its condition outlives the item it came from.

### K1. The store's save and the instance lock have two reusers

`scripts/release_position.py` and `scripts/normalize_ledger_exponents.py` each read the
store through `store.load`, write it through `store.save`, and take the bot's
non-blocking instance lock for the whole operation. **The lock is resolved against the
working directory, so a tool excludes the bot of the clone it is run from and no other**
(`M5l-155`): a store changed from a different clone than the one running the bot is not
protected. `store.save` always writes the current schema, so saving a store written by
an older build upgrades it as well, which is why the normaliser refuses another schema
(`M5l-228`). Carried from P-3k's release-tool item and P-3h's normaliser item, which are
indexed below.

*Arming condition:* **whoever next edits `store.save` or `PersistedState` in `persistence/store.py`, or the instance lock's path handling in `utils/instance_lock.py`, which `scripts/release_position.py` and `scripts/normalize_ledger_exponents.py` reuse.**

### K2. What P-3k leaves standing

P-3k is closed by the owner's ruling at P87, and three things it records stay true:

- **R3's synthetic `CLOSE` is attempted once per symbol, on its first candle** (`M5l-137`).
  If the executor refuses it, the position stays restored and `UNKNOWN`, every entry is
  refused, and nothing retries it; the strategy's own `CLOSE` path is still open. Not
  ruled; chosen to avoid a refusal line on every candle. REASONED.
- **R3's "base held" is read from the account balance** (`M5l-125`), which cannot tell the
  position's base from a manual holding of the same asset. With both protective legs
  cancelled and a human holding at least the quantity, `RestoreAndClose` sells it. A
  consequence of Q4(b) as ruled; the operator rule is in `CLAUDE.md`'s deployment
  procedure. Its first priced instance is `M5l-164`, the ETHUSDT takeover that cost
  `-6.91308000` USDT outside the ledger.
- ***"Only a restart forgets"*** in `executor.py` under U2's Reading A is still true: the
  unconfirmed placement's durable record is dropped on purpose.

*Arming condition:* **whoever next changes what `PersistedState` in `persistence/store.py` persists, or `_snapshot_unmanaged_holdings` or `_snapshot_live_order_lists` in `engine/modes.py`, which are `live_system`'s boot reconciliation.**

### K3. Four pre-existing false sentences in `src/` and `tests/`, reported and not edited

Declared, each made false by something other than the commit that found it, and left
standing because the rotation that records them is documents only. Nothing here is a
control defect; each describes the tree wrongly.

- **`engine/modes.py`, `_snapshot_live_order_lists`' block message** says the position
  *"was lost when the previous process ended"* (`M5l-159`). After P-3k that is true only
  of a live list with no record.
- **`tests/unit/test_reconciliation_pass.py`,
  `test_a_budget_below_one_plus_l_cannot_complete_the_position`'s docstring** says
  `max_open_positions >= L + 1` is *"a config relation nothing validates"* (`M5l-188`).
  False since C20b, and since C41 the call cap is `max(max_open_positions, L + 1)` so the
  relation is not a configuration constraint at all.
- **`execution/booking_line.py`'s header**, *"ONE FIELD SET FOR THREE EMITTERS"*
  (`M5l-226`): the boot's `boot_exit_booked` line also consumes `settlement_fields`, so
  there are four, and the census test covers the executor and the driver only.
- **`execution/dispatch_budget.py`'s module docstring**, *"The only latency samples in
  existence are six `get_open_orders` reads"* (`M5l-263`). `M5l-039`'s 300
  reconciliation-call samples exist from P59. The same claim was fixed in two other
  docstrings and missed in this one.

*Arming condition:* **whoever next edits `_snapshot_live_order_lists` in `engine/modes.py`, `settlement_fields` in `execution/booking_line.py`, `DispatchBudget` in `execution/dispatch_budget.py`, or `test_a_budget_below_one_plus_l_cannot_complete_the_position` in `tests/unit/test_reconciliation_pass.py`.**

### K4. The cause of the 229 s stall is UNMEASURED (`M5l-198`)

At `13:53Z` on 2026-09-27 the bot's disconnect warning came 229 s after the library's
first error. The consumer's own code does not stall between the library error and the
warning (`M5l-196`, measured by probe: a blocked handler produces a delay equal to the
block), and at 13:53:00 the handler chain should not have blocked and the log holds no
line from it. **What held the consumer is unmeasured.** `FeedWatchdog`'s lag and
slow-chain lines are the instrument built for it (`M5l-203`), and **M5l's observation run
produced none**: 0 `event_loop_lagging` and 0 `handler_chain_slow` over 8.356 h, because
nothing stalled (`docs/RUN_LEDGER.md` section 26). So the instrument is built, quiet on a
healthy feed, and has not yet caught an occurrence. UNMEASURED.

*Arming condition:* **whoever next edits `FeedWatchdog` in `data/watchdog.py`, or `_run` in `exchange/websocket_client.py`.**

### K5. The natural-gap rate of a pair other than BTCUSDT or ETHUSDT (`M5l-202`)

**Left open, by the project owner's ruling at P98**, with this condition, verbatim:
*"whoever next enables a pair other than BTCUSDT or ETHUSDT measures its natural-gap rate
before trading it."* Whether Binance omits a kline for an interval with no trades is
UNMEASURED. On an illiquid pair the gap detector would read a quiet interval as a gap and
the guard would refuse `BUY`s for a window. **Measured for the committed pairs only:**
BTCUSDT/1m and ETHUSDT/5m had no missing interval and no zero-trade bar over 8.356 h,
and the detector logged 0 gaps (`M5l-251`, `docs/RUN_LEDGER.md` section 26), so the
omission behaviour was never exercised.

*Arming condition:* **whoever next enables a pair other than BTCUSDT or ETHUSDT in `enabled_pairs` in `config.yaml` measures its natural-gap rate before trading it.**


> **ANNOTATED AT M5m P101 (C0): *"Whether Binance omits a kline for an interval with no
> trades is UNMEASURED"* IS NOW MEASURED FOR ONE PAIR, ON THE ARCHIVE.** `M5m-031`:
> `BTCUSDT-1m-2017-08` holds 21,360 bars over 21,360 minutes, of which 6,974 carry zero
> volume and zero trades, so the archive does NOT omit an interval with no trades, and a
> gap on the grid there means absence rather than a quiet market. **What survives:**
> everything else here. It is one pair, one month and the bulk archive, not the live
> REST feed or any other pair, so the condition and its demand that a new pair's
> natural-gap rate be measured before it is traded stand unchanged.

### K6. `scripts/trade_census.py` infers the protective leg from the price, though a label is present (`M5m-025`)

**Carried as an item, not done now, by the project owner's ruling R-I at M5m P101,
verbatim:** *"M5m-025's leg-label reading in scripts/trade_census.py is carried as an
item, not done now."* MEASURED over the census of record: none of the 11 protective
bookings carries a `leg=` label, so the tool infers SL or TP from whether the exit's
average price is below or above the entry's; the reconciler's preceding line, `leg SL|TP
reports FILLED with <quantity> executed`, names the leg for all 11 and agrees with the
inference on all 11 (8 SL and 3 TP). Reading that line as the label would make the
classification a fact and not a rule; it would also make a mismatch between the two a
finding. The tool does not read it.

*Arming condition:* **whoever next edits `_leg` in `scripts/trade_census.py`.**

---

## CARRIED FROM M5l'S PRIORITIES

### P-3i. Settlement runs outside the driver's call count (`M5k-060`)

`remainder = self._budget.max_calls - len(assessments)` covers the pass and
the point queries only, so a phase may make up to `max_calls` plus one call
per bookable exit. The coherence check's third term reserves the time; nothing
in `src/` tracks request weight. MEASURED.

*Arming condition:* **whoever next edits `ReconciliationBudget` in `execution/reconciliation_driver.py`.**

> **PARTLY RESOLVED AT M5l P89 (C43): THE CALL COUNT IS NOW REPORTED, THE
> REQUEST WEIGHT IS NOT, AND THE ARMING CONDITION FIRED AND IS DISCHARGED FOR
> THE COUNT.** *"A phase may make up to `max_calls` plus one call per bookable
> exit"* stays true: settlement is still outside `max_calls`, and nothing
> changed its budget. What changed is that it is said. A phase that made a
> settlement fetch logs `reconciliation_phase_calls` at `INFO` with
> `pass_calls`, `point_queries`, `settlements` and `max_calls`, so the overrun
> is their sum against the cap. `point_queries` is derived from the legs the
> resolver left unresolved (the pass line's `queries` field is the remainder, not
> work, `M5g-085`) and is absent when the resolver failed. This is ACCOUNTING
> and LOGGING; no budget semantics moved, so H6 did not fire for the count.
>
> **WHAT STAYS OPEN: *"nothing in `src/` tracks request weight"* is still
> true, and it is not closable by logging.** The port returns no response
> headers, so a call is counted and never weighed, and a per-endpoint weight
> table would be the venue's documentation and not a measurement. Counting
> weight needs the port to carry what the venue reports, which is new
> semantics and the owner's. Nothing here weighs a call.
>
> **ARMING AUDIT AT C43, by content.** C43 edits `ReconciliationDriver.__call__`,
> `_book_exits` and the `ReconciliationBudget.max_calls` comment. Fired and
> REAFFIRMED, each unaffected because the edit is a counter and a log: P-3a's
> *"the Q branch of `_book_exits`"* (the counter is incremented there, and the
> branch's logic is unchanged); the A5 evidence-gap item's *"`_book_exits` or
> `_refine`"*; `M5i-065`'s *"the orphan guard or its caller in `_book_exits`"*
> (the guard is untouched); and the trigger item's
> *"`ReconciliationDriver.__call__`"* (what triggers a pass is unchanged).
> Not fired: P-3b's, which names `_settle`, not edited. Reported, not made
> false by C43: the A5 item's *"`exit_unbookable` occurs zero times: the
> escalation has never run"* is false of the 2026-10-01/02 supervised run, which
> logged it on passes of both of A4's runs, the failed one and the one that
> passed (`docs/RUN_LEDGER.md` section 25).

### P-3m. A call-cap deferral logs nothing (`M5l-075`)

When the per-pass call cap stops before a due position, that position is not
read and nothing says so. A pass that read one of two due positions logs
`positions=1 queries=2`, exactly like a pass with one position, so no capture
can count a deferral. MEASURED (code, and both captures). It matters more
since `M5l-081`: a healthy position can be deferred on consecutive bars once
three positions are open and one has absent legs, and the only trace of that
would be a staleness refusal.

> **ADDED AT M5l (P71, C22): TWO MORE SHAPES THAT LEAVE THE SAME SILENCE.**
>
> - **Starvation (`M5l-085`, `M5l-086`).** A healthy neighbour went unread
>   for 6 bars, its stamp age rising 120, 181, 242, 303, 364, 425 s. That
>   happened in two cases: when the other position's point queries failed
>   at `max_calls = 3`, and when `max_calls = 2` was below `L + 1`. The
>   second case is now refused at config load (`90355df`, P-3o). The first
>   is not.
> - **Churn (`M5l-088`, `M5l-089`).** A position opening on a freed slot is
>   unstamped, so it sorts first. With an unresolved list, it defers the
>   healthy position again. MEASURED: at `n = 3`, a healthy stamp reached
>   242 s after three consecutive deferrals.
>
> Neither shape logs a deferral. In the measured runs, the deferral left a
> trace only once the stamp passed the bound, as a `position_stale`
> refusal. The `committed_risk_unknown` refusals before that point name the
> untrusted position, not the deferral.

*Arming condition:* **whoever next edits the call cap in `reconcile_open_positions` in `execution/reconciliation.py`, or `_report` in `execution/reconciliation_driver.py`.**

> **PARTLY RESOLVED AT M5l P89 (C42): *"A call-cap deferral logs nothing"* IS NO
> LONGER TRUE, AND THE ARMING CONDITION ABOVE FIRED AND IS DISCHARGED FOR THE
> LOG.** At the break in `reconcile_open_positions`, every due position the
> cap leaves unread is logged at `INFO` as `reconciliation_deferred`, one line
> each, with `symbol`, `reason=call_cap`, `calls_used` and `max_calls`. So a
> pass that read one of two due positions no longer reads like a pass with one
> position, and a capture can count deferrals. Pinned by
> `test_a_call_cap_deferral_is_logged_with_the_calls_used`, three positions
> with the middle one diverged, whose third is the one logged.
>
> **WHAT STAYS OPEN, logged rather than fixed:** the **starvation** shape
> (`M5l-085`, `M5l-086`) and the **churn** shape (`M5l-088`, `M5l-089`) from
> the P71 addition above. Both now leave this line, and the deferral is no
> longer visible only as a `position_stale` refusal; neither is prevented. The
> first of the starvation cases, a neighbour's failing point queries at
> `max_calls = 3`, is not closed by the cap's decoupling at C41 either. **What
> survives:** the item, for those two shapes, and the arming condition for
> `_report`.

### P-3n. Is the confirm-step question ruled? (`M5l-077`) -- FOR THE OWNER

U7 below calls the five-versus-four confirm-step question *"unruled"*.
`config.yaml`'s comment on `dispatch_deadline_s` says *"RULED at M5h: the
confirm step queries the TWO PROTECTIVE LEGS ONLY, so a full close is FOUR
calls"*. MEASURED: the two disagree. Which one stands decides whether
`_CLOSE_SEQUENCE_CALLS` can go, and that is U7's subject.

> **ADDED AT M5l P76 (C27): WHAT `docs/PHASE_HISTORY.md`'s M5h ENTRY SAYS,
> next to U7's *"the unruled five-versus-four confirm-step question"*.**
> Quoted verbatim; nothing is ruled here.
>
> - The M5h commit table, row 31: *"| 31 | `f6ec6d1` | The close is four
>   calls, and there is no per-call share |"*
> - The M5h prose: *"Q-C §4b's cancel → confirm → sell, built as specified:
>   one cancel collapses the list, the confirming query re-reads per leg
>   because it must see a leg that filled *during* the cancel, and the sell
>   is `MARKET` under a derivable close id so a timed-out sell is resolvable
>   by asking."*
>
> The build log says the close is four calls, and so does `config.yaml`'s
> comment. U7 calls the question unruled. The prose says "per leg" without
> saying which legs. **For the owner:** whether the M5h text is the ruling
> U7 lacks. P-3n merges into U7 (the P-3 order above).

*Arming condition:* **whoever next edits `_CLOSE_SEQUENCE_CALLS` in `config/models.py`, or rules on U7.**

---

## OTHER NEW CARRIED ITEMS, AT M5k's CLOSE

### N1. A held-then-released trade leaves no record across a restart

F2's successor. A position is not persisted, so a restart releases a hold,
and a close deferred before a restart is released unbooked after it
(`M5k-065`). The trade is then in the ledger only if an operator entered it by
hand, and nothing on disk records that it was ever held or deferred.

> **ANNOTATED AT M5l P79 (C30): *"A position is not persisted"* IS NO LONGER
> TRUE OF THE FILE.** From C30 a held position keeps its record in
> `data/state.json` (the owner's Q5(b)). **What survives:** nothing reads the
> record until C32 and each boot's first save erases it, so a restart still
> releases the hold and a deferred close is still released unbooked; and the
> record carries no hold, so nothing on disk records that it was held.
> REAFFIRMED at C30, which edits `_persist_pending`.
>
> **ANNOTATED AT M5l P81 (C32a): "nothing reads the record until C32" IS NO
> LONGER TRUE, and "a restart still releases the hold" is true only of a
> hold with a pending close.** A position held by the reconciler has no
> close record: at boot its filled exit classifies `BookExit` and, until
> C32b, REFUSES the boot rather than releasing the hold (`M5l-130`). A hold
> or a deferred close beside a pending close record is left out by the
> owner's interim ruling, so that restart still releases it unbooked.
>
> **ANNOTATED AT M5l P82 (C32b-1): the reconciler-held case no longer
> refuses the boot.** Its filled exit re-holds at boot: the record is kept
> with no position and the symbol blocked (Q5(b)), so the hold now SURVIVES
> the restart rather than refusing it or being released.
>
> **ANNOTATED AT M5l P82 (C32b-3): "A hold or a deferred close beside a
> pending close record is left out by the owner's interim ruling, so that
> restart still releases it unbooked" IS NO LONGER TRUE.** Boot reads the
> close's sell beside the position's record. A filled sell is booked
> ledger-only, or held with its record kept (Q5(b)), and the close record is
> removed either way, so such a restart neither releases nor drops it unbooked.
> **What survives:** the item, and a close with no position record beside it,
> which is still released on its first candle.
>
> **ANNOTATED AT M5l P83 (C33): THE ITEM'S HEADLINE IS ANSWERED.** *"A
> held-then-released trade leaves no record across a restart"*: a held exit
> now keeps its record across a restart (Q5(b)) and is released only by an
> operator with `scripts/release_position.py`, whose line in `logs/release.log`
> is the record that it was. **What survives:** nothing on disk records WHY a
> position was held, since the record carries requested values only; the hold
> is re-derived from the venue's fills at each boot.

*Arming condition:* **whoever next edits `PendingCloseRecord` in `persistence/store.py` or `_persist_pending` in `engine/modes.py`.**

### N2. Whether Testnet takes fees in BNB -- UNMEASURED

Every commission in every capture is `0.00000000`, so the BNB setting has
never been observed to matter. It decides which asset an entry fee arrives in,
which is the question entry-fee netting must answer first.

*Arming condition:* **whoever next edits `calculate_position_size` in `risk/position_sizing.py` or `build_placement` in `execution/placement.py` to net an entry fee.**

### N3. How soon `myTrades` returns a fill -- UNMEASURED

The only `myTrades` captures were read long after their fills, so nothing
measures the delay between a fill and its appearance there. That delay
decides how often Site A defers a settlement it could have read a moment later.

*Arming condition:* **whoever next edits `_settle` or `_defer_settlement` in `execution/executor.py`.**

### N4. `_dec` launders a float past `Money` (`M5k-025`)

`_dec` is `Decimal(str(value))`, so a float routed through it reaches a
`Money` field as a `Decimal`, and `_reject_float` never fires on the wire path
of any mapper that uses it. The scope was ratified by the owner: declared, not
fixed. MEASURED.

*Arming condition:* **whoever next edits `_dec` or `_opt_dec` in `exchange/models.py`.**

### N5. Q-B's halt-flag condition may be stranded (`M5k-140`)

Its caller is the halt flag's first writer, and the owner ratified `CRITICAL`
without a halt flag (`M5k-006`), so that writer may never exist -- `CLAUDE.md`'s
failure mode 2. Whether it is stranded is decided by whoever writes a halt, or
rewrites the condition. REASONED.

*Arming condition:* **whoever first adds a halt field to `Portfolio` in `core/portfolio.py`, or whoever next edits the halt-flag condition in `docs/QB_ESCALATION.md`.**

### N6. Lifting the live-trading block

The owner's ruling above names its two preconditions:
- a non-zero fee capture empirically established on a live-quoted venue;
- base-asset quantity netting fully implemented in the entry sizing pipeline.

Neither exists. `CLAUDE.md`'s own live-block condition, on `Settings.__init__`
and `_cmd_run`, still governs the mode resolution; this item governs the work
the lift waits on.

**A third gate stands beside the two, added by the owner at P61:** the restart
gap, P-3k -- an open position that a restart leaves unowned. It carries its own
arming condition there, and the condition below does not watch it.

> **ANNOTATED AT M5l P87 (C38): THE THIRD GATE IS CLOSED, AND TWO STAND.** The
> owner ruled P-3k satisfied at P87 (quoted verbatim at P-3k above): *"P-3k no
> longer blocks live trading. The fee-capture and base-asset-netting gates
> remain, so live trading stays blocked."* **N6's two preconditions, listed
> above, are exactly what remains, and neither exists.** A protective
> stop-loss order type review, marked at P87 (`M5l-170`), is not a gate by the
> owner's ruling; it is marked for QC before live trading.

*Arming condition:* **whoever next edits `calculate_position_size` in `risk/position_sizing.py` or `build_placement` in `execution/placement.py`.**

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
- **Priority 3, regularising the arming conditions** — done at M5j's rotation for this
  file and widened at M5k's by `CLAUDE.md`'s rule that the audit reads every document that
  carries a condition; the registers are re-measured at every rotation, and M5l's are
  below. The two unparsed candidates it names are kept by ruling.

---

## Arming conditions — the registers, with two deliberate exceptions

`scripts/check_arming_conditions.py` keeps a parsed and an unparsed register and
**exits non-zero while the unparsed register is non-empty**. Under `CLAUDE.md`'s
*"AMENDED AT M5k's ROTATION, BY ANNOTATION: THE AUDIT READS EVERY DOCUMENT THAT CARRIES AN ARMING CONDITION"*
it is run on every document that carries a condition. **MEASURED at M5l's rotation, on
the tree this commit leaves** (`scripts/check_arming_conditions.py`, one run per document,
P98):

| document | candidates | parsed | unparsed | exit |
|---|---:|---:|---:|---:|
| `docs/NEXT_MILESTONE.md` | 38 | 37 | 1 | 1 |
| `CLAUDE.md` | 2 | 2 | 0 | 0 |
| `docs/QB_ESCALATION.md` | 1 | 0 | 1 | 1 |
| `docs/QC_PROTECTIVE_ORDERS.md` | 0 | 0 | 0 | 0 |
| `docs/M5_NUMBERS.md` | 0 | 0 | 0 | 0 |
| `README.md` | 0 | 0 | 0 | 0 |
| `docs/RUN_LEDGER.md` | 0 | 0 | 0 | 0 |
| `docs/PHASE_HISTORY.md` | 0 | 0 | 0 | 0 |

**The first four rows are the four documents M5k's table read, and they are unchanged in
count**, but `docs/NEXT_MILESTONE.md`'s 38 is not M5k's 38: the conditions of the struck
M5l items retired with them, and K1 to K5 and U9 to U12 were added. **Every new
condition parses**, `M5l-202`'s included, which is the owner's wording verbatim with its
site named, `enabled_pairs` in `config.yaml`. The four rows below the first four are
new in this table: those documents carry no condition and the checker reads none. The
two unparsed candidates are the two that M5k left unparsed deliberately, Q-C section 3's
leg set here and the halt flag's first writer in `docs/QB_ESCALATION.md`, and the exit
code of 1 for each is the register doing its job, as the paragraphs below record.

**Two labels that said "MEASURED at M5k's rotation" were re-measured, and neither moved.**
`CLAUDE.md`'s *"MEASURED at M5k's rotation: this machine's `.venv` lists
`binance-trading-bot 0.1.0` as editable at this repository's path"*: `pip list` still
lists it, `pip show` gives *"Editable project location"* as this repository, and run from
`C:\Users\User\AppData\Local\Temp` the interpreter still resolves
`trading_bot.__file__` to this repository's `src/trading_bot/__init__.py`. That sentence is
in `CLAUDE.md`'s locked text, which the annotation authority excludes, so it is recorded
here and not annotated there. And W6's `getMessage()` count, below. The third label, THE
GATE BASELINE, was re-measured in R7.


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

## THE MODE-3 RECORD — what M5l's rotation pass found

`CLAUDE.md`'s failure mode 3 is a condition that FIRES and nothing notices, and its
rotation procedure asks only that the rotation LOOK. M5l's rotation looked the way M5k's
did, with the same instrument, over **the 65 M5l commits from `fdf8d7b` to `7489581`**
(the rotation's own commits edit documents only): for each condition the carried file
lists, the exact source segment of each `def` or `class` it names, extracted with `ast`,
compared at the commit and at its parent. The script is `p98_firings.py`, beside
`p98_events.py` in `F:\trading bot\deploy\arm_tools`; it reads the register with
`scripts/check_arming_conditions.py` and not by hand.

**What it measured.** 39 conditions were read (37 parsed in this file and 2 in
`CLAUDE.md`; Q-C section 3's candidate is unparsed by design) and **32 are measurable**
by this instrument. The other seven name nothing that is a `def` or `class`: K5 (`enabled_pairs`, a config
key), P-3n and U7 (`_CLOSE_SEQUENCE_CALLS`, a constant), U6 (`paper/simulator.py` and
`backtesting/engine.py`, files that are still stubs), A3 (a document,
`docs/PHASE_HISTORY.md`), `M5i-126` (`_UNREAD_OUTPUT`, a constant) and the census item
(`scripts/run_census.py`, a script). **Four more are measurable in part**, one of their
names resolving and another not: U11's `provider.on_candle` (an attribute), A6's
`_log_booked`, `M5i-104`'s `caplog.records` and `CLAUDE.md`'s `TradingMode.LIVE` (an enum
member). **54 firings occur across the 32**, a firing being a commit that changed any
resolved symbol's source. **41 of the 54** name the symbol in the commit
message or in the lines the commit added to this file, which is the cheapest honest test of
an audit and a proxy for one. **13 do not**, and they were read by content:

- **Four are P-3k's own implementation**, `5a2307c`, `fa06d77`, `a14aa6c` and `2081389`
  (C32a to C32b-3). They edit `live_system`, which the condition names only as a
  description of the two snapshot functions it guards, and at C32a they edit
  `_snapshot_unmanaged_holdings` and `_snapshot_live_order_lists` themselves. They ARE the
  work the condition guards, and the item records it.
- **Two are a class named where a method is meant.** `cdc6c2e` (C50) edits
  `Portfolio.close_position`; N5's condition is *"whoever first adds a halt field to
  `Portfolio`"* and `M5i-095`'s is a test asserting over `Portfolio`. No halt field was
  added and no such test written, so neither fired in substance.
- **Six are U3's, and two are real.** U3's condition is *"the placement site in
  `OrderExecutor`"*, and the class is named. Four of the six edit other methods, by their
  diffs: `2081389` (`_resolve_close` and two others), `cdc6c2e` (`_book_resolved_close`),
  `bf6f9a8` and `51a5f27` (the close-sequence guards). **`989edfc` (C30) edits
  `dispatch`**, whose placement success path it reordered, **and `4341c5c` (C48) edits
  `dispatch`, `_open_position` and `_entry_fill_price`**, the placement caller, and U3 was
  recorded as *"Carried, unfired"*: see its annotation.
- **One is U0's, and it is real.** `fa06d77` (C32b-1) changed what both persistence
  closures write, and the item recorded the firings at C30 and C32a and not this one: see
  its annotation.

**So the pass found three real firings of two conditions that nothing recorded**, U0 at
C32b-1 and U3 at C30 and at C48, all REAFFIRMED by content in their annotations. That is
the mode-3 shape again, and in the cheap direction: none moved the thing its item is about.

**What the instrument cannot see**, stated so the record is not read as complete. It
resolves a name to the first `def` or `class` of that name in the module, so a name shared
by two methods reads as one. It cannot see a constant, a key, an attribute or a document.
The checker lists descriptive symbols as if they were sites (`live_system`,
`TradingMode.LIVE`, `caplog.records`), and a class named in place of a method fires on any
edit to the class. The "names the symbol" test is a proxy for an audit and not an audit. A
firing the instrument reports as named may still have been judged wrongly; one it
reports as unnamed may have been judged well.

---

## THE M5k RECORD, carried — what M5k's rotation pass found

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

### U9. OPEN OWNER RULING: how the fee-capture gate is met -- added at M5l (P68)

How the gate *"a non-zero fee capture empirically established on a
live-quoted venue"* is met, given Testnet commission is zero on every fill
(`M5l-054`):
- (i) a read-only mainnet key fetching existing trades;
- (ii) one minimum-size mainnet order, under its own ruling;
- (iii) rewording the gate.

It is N6's first precondition. MEASURED: every commission in every capture
this tree holds is `0.00000000`, including the six fills of M5l's evidence
run, so no Testnet run can meet it as worded.

*Arming condition:* **whoever next edits `refuse_live_trading` in `config/settings.py`, or rules on N6's first precondition.**

### U11. DEFERRED: reconciliation on a timer, independent of candles -- ruled at M5l P91 (pin 2)

P-3l's stopped reconciliation is reported and not repaired. A timer that ran the
reconciler at the dedup interval, whether or not a candle arrived, would repair
it, and it is **deferred by the owner's P91 ruling.** It would amend locked text,
quoted here so a later author sees what the work costs:
- *"Reconciliation runs, on any pair's candle, over every open position not held
  under ruling A."* (the P74 re-ruling, `CLAUDE.md`, *Fills are observed by
  polling*);
- *"the driver still has to be a candle subscriber, because it still reconciles
  every UNHELD position on any pair's candle while `on_signal` skips quiet
  bars."* (the ruling A annotation under *Handler isolation is THREE layers*);
- and it runs into *"A bounded queue with a single consumer was rejected: it
  makes `Portfolio` writable from a task that is not the one reading it, and the
  first bug that buys is a **duplicate entry**"* (*Execution*, *Dispatch stays
  inline*), because a pass writes `Position` state and books exits. It would
  need a serialisation rule against `_notify`.
It would also fail visibly and recover nothing if REST is down with the socket
(`M5l-201`).

*Arming condition:* **whoever next edits `ReconciliationDriver.__call__` in `execution/reconciliation_driver.py` to be called from anywhere but `provider.on_candle`, or lifts the P76 acceptance.**

### U12. DEFERRED: REST backfill after a gap -- ruled at M5l P91 (pin 4)

C44 detects a gap and refuses a BUY across it; the missing bars are never
fetched. A backfill would close the gap rather than guard it, and it is
**deferred by the owner's P91 ruling.** Facts for whoever builds it: it must run
before the first post-gap bar is appended, because `_append` drops
`open_time < last`; `ExchangeClient.get_klines` takes `limit` and no start time,
so a backfill reads the latest N bars and merges; and it makes a REST call on the
candle path. Locked text it touches: *"The invariant that survives is **the
candle pipeline must never be blocked by latency we do not bound ourselves** — a
budget, not an abstinence"* (*Execution*), so it needs its own bound and a place
in the coherence budget; and *"add every bar that never arrived because the feed
dropped and the buffer does not backfill"* (*There is no static staleness
guarantee*), which it would make false.

*Arming condition:* **whoever next edits `_record_gap_if_any` in `data/market_data.py` to fetch bars, or adds a start time to `ExchangeClient.get_klines` in `core/interfaces.py`.**

### U10. OWNER ITEM: QC review of the protective order type before live trading -- added at M5l (P88)

QC review of the protective order type before live trading: `STOP_LOSS`
guarantees the exit, not the price; measured 4.2% beyond the stop on Testnet
(P87's finding, `M5l-170`, `docs/RUN_LEDGER.md` section 25): a stop at
83214.72 filled at 79800.00 and 79749.94. Q-C section 3 fixed the leg types
(`STOP_LOSS`, `TAKE_PROFIT`, a `LIMIT`+`FOK` working leg); whether a
`STOP_LOSS_LIMIT` or another type bounds the price, and what it costs in
exits that do not fill, is the review's question and is not decided here. Not a
gate by the owner's P87 ruling: marked for review before live trading.

*Arming condition:* **whoever next edits `build_placement` in `execution/placement.py`, which fixes the protective leg types, or rules on N6's preconditions.**

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

**FIRED AT M5l P79 (C30) AND REAFFIRMED.** C30 adds `positions` to what both
closures write, read live from `portfolio.open_positions`. It does not touch
the pending slice: `_persist_ledger` still writes `pending=persisted.pending`.

**FIRED AGAIN AT M5l P81 (C32a) AND REAFFIRMED.** Neither closure is
edited, but what `_persist_ledger` writes changes: `persisted` is now seeded
from the boot's own save when there was one, so after a boot that settled
restored placements it does not write them back (`M5l-128`). The carry itself,
`pending=persisted.pending`, is unchanged.

> **FIRED AT M5l P78 (C32b-1, `fa06d77`) AND NEVER RECORDED UNTIL P98 (R4); REAFFIRMED
> BY CONTENT.** `p98_firings.py` found it: both closures' `positions=` argument now reads
> `(*held_records, *_position_records(portfolio.open_positions, reported=unrecorded))`,
> where the records boot HELD (Q5(b)) have no `Position` and so *"ride every save"*. That
> changes what `_persist_pending` and `_persist_ledger` write, which is this condition's
> subject, and the item recorded the firings at C30 and C32a and not this one. **What
> survives:** the carry itself, `pending=persisted.pending`, is untouched, and the held
> records are positions and not pending placements. REAFFIRMED. See THE MODE-3 RECORD.

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

> **ANNOTATED AT M5l P98 (R4): *"Carried, unfired"* IS FALSE, AND THE CONDITION BELOW
> FIRED TWICE IN M5L (`p98_firings.py`); REAFFIRMED BY CONTENT.** `989edfc` (C30)
> reordered `dispatch`'s placement success path, so a raise after a successful placement
> keeps the pending record (`M5l-120`), and `4341c5c` (C48) edited `dispatch`,
> `_open_position` and `_entry_fill_price` to carry the entry order's own quote total.
> Neither commit's body or annotations names U3. **What survives, and it is the question
> this item asks:** whether to consume `orderReports` from the placement response. C48's
> total comes from the entry order's GET (`get_order`), the same call as the entry price,
> and nothing reads `orderReports`. The other four `OrderExecutor` firings in the
> instrument's list edit the close sequence and are not the placement site.

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
`CLAUDE.md`'s live-trading block, which it waits on. Until M5k's rotation the
condition below watched `to_order` alone, and `193a5b9`, the first commit to
edit it, REAFFIRMED it; it now watches the entry-sizing sites.

*Arming condition:* **whoever next edits `calculate_position_size` in `risk/position_sizing.py` or `build_placement` in `execution/placement.py`** —
the entry-sizing and placement sites where an entry fee would first be netted.

The condition was re-pointed at M5k's rotation. It read *"whoever next edits
`to_order` in `exchange/models.py` — the single site where the venue's
commission is discarded, and the first site any fee must cross"*. Exit fees no
longer cross `to_order`: they cross `get_my_trades`, and `settle_exit` sums
them. The residue this item carries is the entry half, which waits on sizing
and placement rather than on the mapper.

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

> **FIRED AT M5l P98 (R6) AND REAFFIRMED.** The M5l entry in `docs/PHASE_HISTORY.md` was
> written by the closing commit, which is the caller the condition names. Its headline and its
> opening paragraphs state only what the entry does not later annotate: they give the
> milestone's shape and its counts, and every claim in them is repeated, with its finding, below
> and is not corrected there. **The reserved question stands and is the owner's:** the M5h and
> M5i entries' headlines are unchanged, and no remedy is proposed.

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

> **ANNOTATED AT M5l P98 (R5): *"the escalation has never run"* IS FALSE, AND SO IS THE
> HEADING FOR A DELIBERATE ARM (`M5l-195`, PRE-EXISTING, found by P-3k's run and left
> unannotated until now).** The count of zero is true of the capture named above and of no
> other. `exit_unbookable` was logged at `CRITICAL` in P-3k's supervised run:
> `docs/RUN_LEDGER.md` section 25 records it for ETHUSDT on every pass of 2026-10-01
> until `18:36:04Z` (the A4 failure, list 401075, pid 16748) and once for BTCUSDT at
> `2026-10-02T12:02:00Z` (the A4 re-run, pid 12472, `state=diverged`), where it is one of
> the sheet's expected lines. So the position-level `DIVERGED` verdict and the escalation
> HAVE run in production, **under a deliberate arm**: the owner's cancel script removed the
> position's protection and the bot was restarted. **What survives:** `M5k-005`'s
> observation that every organic line on which a requested leg did not rest also carried a
> sibling fill clause, and that a sibling is not a mechanism, so no UNARMED divergence has
> been observed. The arming condition below is unchanged.

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
the project owner at M5i, and unchanged in logic since: re-indented at
`651d334`, when `_book_exits`'s loop moved under a `try`. MEASURED at M5k's
rotation: the guard's lines differ in `git diff 651d334^ 651d334 --
src/trading_bot/execution/reconciliation_driver.py` and in no line under `git
diff -w` over the same range and path. This read *"untouched since"* until
then.

*Arming condition:* **whoever next edits the orphan guard or its caller in
`_book_exits`.**

> **FIRED AT M5l P94 (C50) AND REAFFIRMED: THE GUARD'S TEXT CHANGED, ITS LOGIC
> DID NOT.** The `ValueError`'s message said *"booking it would silently no-op"*,
> true while `close_position` returned `Decimal(0)` for a symbol it did not hold
> and false once it raises `PositionNotHeldError`; it now says *"booking it
> would raise PositionNotHeldError or book a different position than the one
> assessed"*, the second clause being the case the guard's identity check also
> covers. The docstring's *"would return `Decimal(0)` and look like a clean
> no-op"* is corrected the same way. The item's *"unchanged in logic since"*
> still holds: the condition, the raise and its type are as they were
> (`M5l-234`).

### `M5i-095`. Two tests reach the mutated point and assert only portfolio state

A survey predicted 9 kills and observed 6. The three that did not fire assert
`ledger is None`, `free_quote` and a record count — **identical whether booking
never ran or ran and failed**, because the write raises before it commits.

*Arming condition:* **whoever next writes a test asserting over `Portfolio`
state to distinguish two booking outcomes.** The state cannot separate them;
only the label can.

### `M5i-104`. Unguarded unpacks turn kills into crashes — the sweep, now 17 sites

**The named test is resolved and indexed above.** A single-element tuple
unpack of log records with no prior length assertion fails at `ValueError`, a
crash, where a mutation removing the record should fail an assertion; `CLAUDE.md`'s
*"READ A LOG FIELD THROUGH `vars(record).get(key)`, AND ASSERT A LENGTH BEFORE INDEXING -- NEVER TUPLE-UNPACK"*
now prescribes the remedy. **The sweep is carried, and it has grown from
the 12 sites M5i counted to 18.** MEASURED at `ae8c914`, with the instrument
stated: lines matching `^\s*\(\s*\w+\s*,\s*\)\s*=` under `tests/` whose
right-hand side reads log records (`_records(` or `caplog`), with no `assert
len(` in the three lines before -- 16 in `tests/unit/test_executor.py` and 2 in
`tests/unit/test_reconciliation_driver.py`. How M5i counted its 12 is not
recorded, so the two figures are not the same instrument.

*Arming condition:* **whoever next writes or edits a single-element unpack of `_records` in `tests/unit/test_executor.py`, or of `caplog.records` in `tests/unit/test_reconciliation_driver.py`.**

> **FIRED AT M5l P94 (C54) AND REAFFIRMED, WITH THE SWEEP ONE SITE SHORTER.** The
> owner's P94 ruling rewrote the unpack in
> `test_a_deferred_close_is_kept_through_bar_five_and_dropped_at_bar_six`
> (`M5l-217`, the two parametrised rows `transport` and `empty`) as a length
> assertion, and read its fields through `vars(record).get`. **Measured on the
> final bytes, C47's `m10` (the executor's drop one read late) went from 5 kills
> and 2 crashes to 7 kills and 0 crashes**: both formerly-crashing rows now fail as
> `AssertionError`, where they raised `ValueError` from the unpack. **The
> instrument is the one the item states** -- lines matching
> `^\s*\(\s*\w+\s*,\s*\)\s*=` -- and it now finds **15 in
> `tests/unit/test_executor.py` and 2 in `tests/unit/test_reconciliation_driver.py`,
> 17 where it found 18** (16 and 2). The sweep is carried, not finished: nothing
> here claims the other 17 sites crash a mutation, only that the pattern that
> crashed these two is still present at them.
>
> The same commit made `M5l-231`'s fix: C49's idempotence test asserts the log
> EXISTS before reading it, and C49's `m10` went from 5 kills and 1 crash to 6
> kills and 0 crashes. **C50 to C53 wrote no unpack** -- every log assertion in
> them asserts a length first -- so this condition did not fire for them.

The condition was re-pointed at M5k's rotation. It read *"whoever next edits
`test_a_partial_fill_with_no_cost_basis_still_goes_naked`, or runs a survey
whose predicted killers include it"*, which names a test already resolved
while the item carries a sweep of 18 others. The two helpers are where those
sites read: 16 unpack `_records(...)` in `test_executor.py`, and 2 unpack a
comprehension over `caplog.records` in `test_reconciliation_driver.py`, which
has no `_records` helper.

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

**Re-measured at M5l's rotation (P98), at `e531822`**: the same `grep -c
'getMessage()'` over `tests/unit/test_executor.py` still counts **6** lines, so the count
has not moved since M5k's rotation.

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

> **ANNOTATED AT M5l P98 (R7): `decision=halt` IS STILL ZERO ACROSS THE FOUR M5l-ERA
> CAPTURES, 16 CLOSE PLANS IN ALL.** By `p98_events.py`, counting `event=close_planned` and
> `decision=halt` in each: the evidence run `c1471d3c...` 3 and 0, the `d1074c6` clone's log
> `bcf01bb1...` 3 and 0, the `5e22bc6` clone's log `85e1c643...` 4 and 0, and the observation
> run `023c72a1...` 6 and 0. They are separate runs and not an extension of the capture above, so
> the 16 is not added to its 163.

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
| log events DEFINED in `src/` | **61** (59 `_EVENT_*`, 2 public `EVENT_*`) | module-level string constants, by `ast`; `_WS_EVENT_*` excluded |
| of those, absent from the capture | **23** | `event=<value>` absent |
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

**What moved at M5l P-1, corrected in place because both rows count the
tree.** `boot_provenance`, `_EVENT_BOOT_PROVENANCE` in `main.py` from
`f8898de`, is the one event added, taking the defined row from 39 to 40
(re-counted by grep for module-level `_EVENT_*` and `EVENT_*` assignments: 38
and 2). It is absent from the capture above, which predates it, so the absent
row moves from 22 to 23 by the same instrument and the observed remainder is
unchanged at 17. No capture was re-read; every other row is the capture's and
is untouched.

> **ANNOTATED AT M5l P98 (R7): THE DEFINED-EVENTS ROW COUNTS THE TREE AND IS CORRECTED
> IN PLACE, FROM 40 TO 61. THE CAPTURE-SCOPED ROWS ARE NOT TOUCHED.** The instrument is
> the one the table states: module-level string constants named `_EVENT_*` or `EVENT_*`,
> read by `ast` over `src/trading_bot`, `_WS_EVENT_*` excluded. It finds **61, 59
> `_EVENT_*` and 2 public `EVENT_*`**, which is the 40 of P-1 and 21 added since. **The
> instrument is blind to an event logged from a string literal**: `bars_gap_detected`, in
> `data/market_data.py`, is one, so by a literal-aware count the events defined are 62.
>
> **What M5l's captures observed**, by `event=<value>` over four of them: the
> evidence run (SHA-256 `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`),
> the P-3k clones' logs at `d1074c6` (`bcf01bb15b54c08e1db6b6049c680b49ba3177406ce7c0bed7191b0d14825cf3`)
> and at `5e22bc6` (`85e1c64391089b1f425ae0efe3954aa705a271d2369ac4bab85ad425871c71bb`), and the
> observation run (`023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb`). **Of
> the 61, 19 occur in at least one of the four and 42 in none.** These are four separate
> runs and not an extension of the M5k capture this table measures, so the 42 is not
> comparable with the table's own 23: the denominators differ and so do the captures.
> The 42 absent from all four: `bars_contiguous_again`, `boot_live_list_unconfigured_symbol`,
> `boot_position_dropped`, `boot_position_gone`, `boot_symbol_blocked`,
> `buy_refused_bars_gap`, `close_abandoned_after_cancel`, `close_book_failed`,
> `close_position_naked`, `close_record_resolved`, `close_sell_unconfirmed`,
> `close_settlement_deferred`, `close_sold_unbooked`, `close_unbookable_held`,
> `collaborator_failed`, `debit_from_requested_limit`, `dispatch_missed`,
> `entry_fill_absent`, `event_loop_lagging`, `event_loop_recovered`, `exit_book_refused`,
> `exit_booked`, `exit_quote_totals_disagree`, `exit_settlement_deferred`,
> `exit_settlement_held`, `feed_resumed`, `feed_silent`, `feed_silent_critical`,
> `handler_chain_recovered`, `handler_chain_slow`, `ledger_unwritable`,
> `order_list_id_not_numeric`, `placement_ambiguous`, `placement_resolved`,
> `placement_unresolved`, `position_record_skipped`, `reconciliation_deferred`,
> `reconciliation_phase_calls`, `reconciliation_phase_failed`, `settlement_timeout_held`,
> `stream_transient_error` and `venue_quote_total_unavailable`. Two of them,
> `placement_ambiguous` and `placement_resolved`, were observed on 2026-08-27 (X3 below),
> in a capture none of the four extends. **`RefusalStage` is not re-censused here.**

**The websocket constants are excluded deliberately.** `_WS_EVENT_TYPE`,
`_WS_EVENT_KLINE` and `_WS_EVENT_ERROR` in `exchange/websocket_client.py` match
a pattern looking for `_EVENT_` but are wire-protocol keys of Binance's stream
payload, not log events.

*Arming condition:* **whoever next runs `scripts/run_census.py` against a newer
capture**, which is the tool that produces every figure in this table.

> **FIRED AT M5l (P64), AND REAFFIRMED.** The tool was run against the capture
> of pid 21520's log, SHA-256
> `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`. That
> is another log, from the deployment clone, and not an extension of the
> capture this table measures, so no row here is re-derived. Every row stays
> scoped to its digest. That capture's own answers are in `docs/RUN_LEDGER.md`
> §23: `boot_provenance` observed, the other 22 absent events and all 8
> stages not, and 3 close plans, all `decision=sell`. The condition stands for
> the next capture that extends this one.
>
> **FIRED AGAIN AT M5l P98 (R7), AND REAFFIRMED.** `scripts/run_census.py` was run against a
> copy of the observation run's log, SHA-256
> `023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb`, frozen in the evidence
> directory. It agrees with P97's own counts (237 lines for pid 24980, 211 event records, ten
> event names). That is another run's log and not an extension of the capture this table
> measures, so no capture-scoped row is re-derived; the one row that counts the tree, the
> defined events, is corrected in place and annotated above. The condition stands for the next
> capture that extends M5k's.

---

## THE GATE BASELINE

Measured at M5l's rotation, at `9fc8b8d`, on this credentialed machine, by
`scripts/check.py` run bare to a file:

```
ruff check src tests scripts           All checks passed!
ruff format --check src tests scripts  142 files already formatted
mypy                                   Success: no issues found in 84 source files
pytest                                 2148 passed, 1 skipped
```

**`2148 passed, 1 skipped` is MEASURED.** `2145 passed, 4 skipped` is **DERIVED**
-- that run minus the three `skipif(not HAS_CREDENTIALS)` integration tests, one in
each integration module and re-counted at this rotation, which move from the passed
column to the skipped one. It has not been observed on this machine and must not be
quoted as though it had.

The lone skip in the credentialed run is **not** an integration test:
`tests/unit/test_logger.py` skips one case on Windows because `time.tzset` is
POSIX-only.

---

## BLOCKED — the trailing-stop milestone

Unchanged from M5h.

*Arming condition:* **whoever amends Q-C §3's leg set.**

---

## Standing authorities for commits -- MOVED TO `CLAUDE.md` AT M5l P98

The section that stood here from P78b to P98 -- the standing docstring authority, the
annotation authority with its pre-existing-false-text rule and its QB and QC widening, the
ruled-overturn authority, the S6 standing rule as superseded at P82, the rule that a prompt's
list of files never narrows the standing authority, and the script-edit rule -- is now in
`CLAUDE.md`'s **Standing authorities for commits** section, verbatim, by the project owner's
ruling at P98 (`M5l-244`). **Read it there.** It was moved because this file is rewritten at
every rotation, and a rule kept here is lost at the next one.

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
  figures first -- `CLAUDE.md`'s *"AT M5k's ROTATION: `scripts/check_gate_counts.py` RUNS TWICE, OUTGOING FIGURES FIRST"*,
  and `M5k-125` is why.

> **DO NOT MOVE A RULE INTO THIS FILE.** Step 3 rewrites it every rotation. At
> M5i's rotation `CLAUDE.md` was found asserting that the grep-the-digits rule
> and its inverse *"both live in `docs/NEXT_MILESTONE.md`'s process section"* —
> and they did not, because a previous rotation had rewritten the file out from
> under the claim. That is the third time a rule has been lost this way. Rules
> live in `CLAUDE.md`; this file holds items, not doctrine.
