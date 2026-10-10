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

> **ANNOTATED AT M5m P103 (C3), BY THE OWNER'S RULING R-O: THE OPTION LIST ABOVE IS NO
> LONGER COMPLETE, AND THE DOWNLOADER NO LONGER DISCARDS WHAT IT FETCHES.** *"`run` takes
> `--through` (required), `--symbols`, `--intervals`, `--data-dir` and `--dry-run`"* gains
> `--offline`: the months are those whose zips are on disk and every request is refused.
> The downloader keeps each zip and its `.CHECKSUM` under `<data-dir>/_zips/<SYMBOL>/<interval>/`
> once verified against that checksum, reads it back from there to ingest it, and does not
> fetch a zip already on disk that equals its checksum. The 980 zips C4 downloaded were not
> kept, since this ruling came after, so they are not on disk and are not fetched again
> (R-O). **S1's arming condition is AUDITED, not fired a second time:** C3 edits
> `scripts/download_data.py` but not its `main`, and the first half stays discharged as
> annotated above. The second half, a start time on `ExchangeClient.get_klines`, has NOT
> fired: the port is unchanged, and `U12` is REAFFIRMED open exactly as written. **What
> survives:** everything in the two annotations above except the option list.

> **ANNOTATED AT M5m P103 (C4), BY THE OWNER'S RULINGS R-L TO R-O: S1'S STORE IS COMPLETE,
> AND THE P101 C4 ANNOTATION'S OPEN DECISION IS ANSWERED.** The rulings, verbatim:
>
> R-L: "A row whose open_time is on the interval grid and whose close_time is after its
> open_time is stored verbatim. Its close irregularity, if it has one, is registered with
> its shape: short bar, one millisecond late, or whole-second. Zero-trade short bars are
> kept. The 8 one-millisecond-late rows are not repaired. A row whose open_time is off the
> grid, or whose close_time is not after its open_time, is quarantined: it is not stored,
> and its raw line, shape and source are recorded. No stored value is altered."
>
> R-M: "Every row is checked against I1 to I4 at ingest and classified. A month is never
> refused for a row of a known class. A row that breaks an invariant in a way no known
> class covers refuses its month and is reported. Checksum, transport and structural
> failures refuse the month, as before."
>
> R-N: "Quarantined spans are not backfilled from REST. They remain gaps, reported with
> kind 'quarantined', and archive omissions are reported with kind 'omitted'."
>
> R-O: "The 120 zips under F:\trading bot\scratch\p102 are copied into
> data/historical/_zips/ and SHA-verified against their CHECKSUM files there. From now on
> the downloader keeps every zip under that path and ingests from disk. The 980 stored
> months are not downloaded again; they are re-verified under the new rule from their
> stored CSVs and manifest rows."
>
> **What stops being true:** the P101 C4 annotation's *"AN OWNER DECISION IS NEEDED BEFORE
> S2 CAN RELY ON THIS DATA"* and its option list, which R-L chose among (store the
> on-grid rows verbatim and register the irregularity, quarantine the rest); its *"Until it
> is made, 14 of 110 months of the minute-scale series are absent"*, since all 110 months of
> every series are now present; and its *"a re-run fetches only the 120 absent months"*,
> since none is absent. **The store is complete
> under R-L to R-O**: all 1,100 months stored, 124 rows registered (110 short bars, 8
> one-millisecond-late, 6 whole-second), 21,603, 242 and 44 rows quarantined per symbol at
> 1m, 5m and 1h, `rows + missing == grid` exactly on all ten series, and 0 problems from the
> deep re-check of every stored row. The per-series table, the registry and quarantine totals,
> every quarantined span and the manifest and registry digests are in `docs/RUN_LEDGER.md`
> section 29. **S1's arming condition is AUDITED, not fired:** C4 edits no `main` and no
> start time is added to `ExchangeClient.get_klines`, and `U12` is REAFFIRMED open exactly
> as written. **What survives:** the store's layout, idempotence, gaps reported and never
> filled, and the C3 annotation's kept zips and `--offline`. The 980 zips C4 of P101
> downloaded are still not on disk (`M5m-106`), which R-O accepts.

> **ANNOTATED AT M5m P105 (C0), BY THE OWNER'S RULINGS R-Q, R-R AND R-S (P104): THE 980
> ZIPS ARE NOW ON DISK, `M5m-089` IS AFFIRMED, AND `M5m-107` STAYS UNSURVEYED.** The
> rulings, verbatim:
>
> R-Q: "M5m-089 is affirmed: a month whose rows are all quarantined is refused."
>
> R-R: "The 980 monthly zips not on disk may be fetched once into data/historical/_zips/
> and verified against their CHECKSUM files. Each is re-ingested into a scratch store
> outside the tree, and its CSV bytes are compared with the stored CSV. The stored store
> is not written."
>
> R-S: "M5m-107 stays unsurveyed: a wrong reuse skip leaves a month absent, which verify
> reports."
>
> **What stops being true:** the annotation above's last sentence, *"The 980 zips C4 of
> P101 downloaded are still not on disk (`M5m-106`), which R-O accepts"*, and the C3
> annotation's *"so they are not on disk and are not fetched again (R-O)"*. R-R authorised
> one fetch and P104 made it: all 1,100 zips and 1,100 `.CHECKSUM` files are under
> `data/historical/_zips/` (563,599,382 bytes of zips and 96,800 of checksums), and the
> 980 were re-ingested into a scratch store outside the tree with every CSV and every
> manifest entry equal to the stored one. The record is `docs/RUN_LEDGER.md` section 30.
> **What survives:** `M5m-106` as what was observed when it was written; R-O, which the
> fetch used; the rule that a month whose every row is quarantined is refused, now
> affirmed by R-Q and so no longer a question for the owner; and `M5m-107`, whose reuse
> and offline logic stays outside R-F's survey scope. **S1's arming condition is AUDITED,
> not fired:** P104 edited no `main` in `scripts/download_data.py` and added no start
> time to `ExchangeClient.get_klines`, and `U12` is REAFFIRMED open as written.

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

> **ANNOTATED AT M5m P105 (C1): S2'S ARMING CONDITION FIRED, AND THE MONEY-RULE PARAGRAPH
> ABOVE IS DISCHARGED.** C1 edits `BacktestConfig` in `config/models.py`, the first half of
> the condition's two sites. *"`BacktestConfig.fee_percent` and `slippage_percent` are
> `float` today"* is false from this commit: `fee_percent`, `slippage_percent`,
> `initial_balance` and a new `stop_slippage_percent` (default `1.20`, R-B2) are `Decimal`
> from load, and the window dates are `date`s read as UTC, half-open `[start_date,
> end_date)`, refused when empty or reversed, with `window_start` and `window_end` as
> timezone-aware datetimes for the store (38 tests in `tests/unit/test_backtest_config.py`).
> **S2 stays open and the condition's other site is not yet touched:** `_cmd_backtest` in
> `main.py` is unedited, so the condition fires again at the commit that wires it; the
> replay, the fill model, the simulated executor and the root are unbuilt. **What
> survives:** the Fees bullet as qualified by R-W(c), and `M5m-036`: the tracked
> `config.yaml` window, 2024-01-01 to 2024-06-30, still loads (181 days) and is not edited,
> because it is the owner's file; S2 sets the real window per run.

> **ANNOTATED AT M5m P105 (C3): R-Z IS CARRIED OUT, AND THE FILTERS A BACKTEST SIZES WITH
> NOW COME FROM FOUR STORED FILES.** `scripts/download_exchange_info.py` made the four
> authorised GETs once (BTCUSDT and ETHUSDT, mainnet and Testnet) and
> `trading_bot.backtesting.exchange_info` stores each response raw with its SHA-256 under
> `data/historical/_exchange_info/<environment>/`, refuses to overwrite one, and loads one by
> verifying the digest and then handing the symbol's entry to the live `to_symbol_info`. The
> digests are in `docs/RUN_LEDGER.md` section 31, because `data/*` is not in git. **What
> stops being true:** nothing in S2's text; `M5m-128` (the cost of applying today's filters
> to history is UNMEASURED) is unchanged, since a snapshot is today's filters and nothing in
> it dates a past day. **What it shows:** the venue's `PERCENT_PRICE_BY_SIDE` band is no
> longer the symmetric 2 / 0.5 the repository recorded on 2026-08-08, on either environment
> (`M5m-142`); a backtest is not affected, since the band filters an order list's prices at
> submission and the fill model does not model it, but the band is part of what a snapshot
> records.

> **ANNOTATED AT M5m P110 (C3): THE ENVIRONMENT IS NOW A CONFIG KEY, AND S4's SNAPSHOT IS READ
> FROM THE TESTNET STORE'S OWN ROOT.** `BacktestConfig.exchange_info_environment` (`mainnet` or
> `testnet`, default `mainnet`) is passed by `_cmd_backtest` to `run_backtest`, which until now
> defaulted to mainnet whatever the config said. `load_snapshot` reads
> `<data_dir>/_exchange_info/<environment>/`, so a run whose `data_dir` is `data/historical_testnet`
> (`config.s4.yaml`) looks for its Testnet snapshots there and **not** in
> `data/historical/_exchange_info/testnet/`, where P105 stored them. **What stops being true:** the
> sentence above that the files live under `data/historical/_exchange_info/<environment>/` is true of
> a run with the default `data_dir` and not of S4's. **What the S4 run needs:** the two Testnet
> `.json` files and their `.sha256` copied byte for byte into
> `data/historical_testnet/_exchange_info/testnet/`, shown SHA-256-equal, which the launch checklist
> and `docs/S4_PREREGISTRATION.md` do. **What survives:** R-Z, entire: backtests load filters only
> from a stored file, which is never overwritten, and the digests in `docs/RUN_LEDGER.md` section 31.

> **ANNOTATED AT M5m P105 (C4): THE REPLAY HARNESS IS BUILT, AND R-P1'S GAP RULE IS PINNED
> ON THE UNCHANGED LIVE PATH.** `trading_bot.backtesting.replay` adds `ReplayClient`, which
> answers the provider's one REST call, `get_klines`, from the store and refuses every other
> venue method, and `ReplayStream`, which delivers stored bars to the handler the provider
> subscribed, merged across pairs by nominal close time (ties to the pair subscribed first) with
> the simulated instant, `now()`, set to a bar's open time plus its timeframe before its
> handlers run. `BufferedMarketDataProvider`, `TradingEngine` and `HistoricalStore` are not
> edited. Forty-seven tests in `tests/unit/test_replay.py`, over stores built through the real
> `ingest_zip`, show that the engine's gap guard refuses the same `BUY`s across an omitted gap
> and across a quarantined span (the guard cannot tell them apart, which the store can), that a
> registered short bar causes no gap and gets its signal, and that a subscriber finds the
> candle already in the buffer. **What this leaves open:** the simulated executor, the fill
> model and the root, which are the second half of S2. **The arming condition naming
> `_record_gap_if_any` in `data/market_data.py` is AUDITED, not fired:** the provider is
> untouched and no start time is added to `ExchangeClient.get_klines`.

> **ANNOTATED AT M5m P105 (C5): THE FILL MODEL IS BUILT, AS PURE FUNCTIONS, AND IT LIVES IN
> `backtesting/fill_model.py` AND NOT IN `backtesting/engine.py`.** `FillParameters` carries the
> three percents (fee 0.1, entry and `CLOSE` slippage 0.05, stop slippage 1.20), `Decimal` and
> checked, with `from_config` reading a `BacktestConfig`. `fill_entry` fills at the next bar's open
> plus slippage iff that is at or below the entry limit, refuses it otherwise, and expires it when
> the next slot is missing (R-W(d)); `book_entry` folds the entry fee into the quote total and
> returns it separately (R-W(c)); `fill_protective` triggers the stop on the low and the
> take-profit on the high, lets the stop win on one bar, fills a stop at its trigger or at an open
> already through it (R-P1, R-W(b)) and a take-profit at its trigger, both less the stop slippage
> (R-W(a)), never at a better open; `fill_close` sells at the open less the entry slippage; and
> `book_exit` returns the gross, the fee on the gross and the net. 85 hand-computed tests in
> `tests/unit/test_fill_model.py`, including one that holds the stop-wins rule to the live
> `risk.rules.should_exit` on seven bars and one that books a round trip through the real
> `Portfolio` to -1.711437. The module has no clock, no float and no I/O, and tests assert each.
> **What this leaves open:** the simulated executor, which sequences these functions (which bar
> `fill_entry` is handed, when a `CLOSE` queues, what a refused or expired entry leaves in the
> portfolio) and wires them to `Portfolio`, and the root. **What stops being true:** two
> sentences of earlier annotations, each true when written. The C1 annotation's *"the replay, the
> fill model, the simulated executor and the root are unbuilt"* (the replay since C4, the fill
> model now), and the C4 annotation's *"What this leaves open: the simulated executor, the fill
> model and the root"*, which is now the simulated executor and the root. Nothing in S2's own
> text. `engine.py` stays a stub, and S4's arming condition is annotated below where the model
> actually lives (`M5m-131`).

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

> **ANNOTATED AT M5m P103 (C4), BY THE OWNER'S RULING R-P: A QUESTION S2 INHERITS FROM
> S1'S STORE, RECORDED AND NOT RULED.** The ruling, verbatim:
>
> R-P: "Recorded as an S2 question, not ruled: what a backtest does with a window
> containing a gap, a quarantined span or a registered short bar."
>
> **The question, with what the store now lets S2 ask.** `HistoricalStore.coverage` reports
> every gap with its kind (`omitted`: the archive holds no row for the bar; `quarantined`:
> the archive held a row for it that failed R-L's grid or close-after-open test and was not
> stored), and `HistoricalStore.registry` lists the 124 stored rows whose close time is
> irregular, each with its shape. So S2 can tell a window apart by what it contains. What is
> NOT decided, and is the owner's: whether a backtest window that contains a gap or a
> quarantined span is refused, split at it, or run across it with the missing bars simply
> absent; whether a registered short bar is treated as a normal bar or as one whose close is
> earlier than its slot, which matters to a fill model that triggers intrabar; and whether
> the answer differs by kind. The store carries the facts and takes no position. **Nothing in
> S2's items above is changed by this.**

> **ANNOTATED AT M5m P105 (C0), BY THE OWNER'S RULINGS R-P1 (P104) AND R-T TO R-Z (P105):
> R-P IS RULED, AND S2'S GAP HANDLING, EXECUTOR SEAM, FILL READINGS, COOLDOWN, RUN SHAPE
> AND FILTERS ARE SETTLED.** The rulings, verbatim:
>
> R-P1: "A backtest refuses a BUY whose strategy warm-up window contains a gap of either
> kind, as the live gap guard does. A position open across a gap is not closed by it. On
> the first bar after the gap, a stop the open has gapped through fills at the open less
> the stop slippage, and a take-profit the open has gapped through fills at its trigger.
> Registered short bars are ordinary bars. Every trade that touches a gap or a registered
> short bar is reported."
>
> R-T: "Every prediction whose observation is reported is written to a file in the
> scratch directory before the command runs. The report quotes it from that file, with
> the file's path and SHA-256."
>
> R-U: "U6 is resolved. The unused ABC OrderExecutor in core/interfaces.py is replaced by
> a Dispatcher Protocol declaring dispatch(signal, assessment, candle) and
> __call__(candle). _build_signal_handler takes a Dispatcher."
>
> R-V: "The incremental frame (M5m-122) is not built in M5m. If S5's measured runtime
> makes it necessary, it returns as its own Phase 1 with a survey."
>
> R-W: "(a) A take-profit fills at its trigger less the stop slippage. (b) The gap-through
> rule applies on every bar. (c) The entry fee is charged in quote and folded into the
> entry quote total for booking; it is also recorded separately in the trade log, and S3
> sums it. The base-asset reality is N6's and is deferred. (d) An entry expires when its
> next slot is missing; a CLOSE queues to the first bar after the gap. The double count
> of stop slippage at a gapped-through open is accepted as a bias against the strategy
> and is documented."
>
> R-X: "The backtest applies no cooldown, at parity with live (M5m-125). The dead
> cooldown_minutes is carried as item K6 for the milestone after a PASS, with an arming
> condition naming Portfolio.start_cooldown."
>
> R-Y: "S5 is one joint run of the committed config. S6 and S7 runs are joint per
> candidate, with per-pair breakdowns reported."
>
> R-Z: "One keyless exchangeInfo GET per symbol, on mainnet and on Testnet, is
> authorised. The raw response is stored with its SHA-256, and backtests load filters
> only from the stored file."
>
> **What stops being true:** the annotation above's heading, *"RECORDED AND NOT RULED"*,
> and its *"What is NOT decided, and is the owner's"* paragraph, which R-P1 rules; its
> last sentence, *"Nothing in S2's items above is changed by this"*, since R-P1 adds the
> gap rules to the Entry, Protection and `CLOSE` bullets (a BUY is refused over a gap, a
> position is not closed by one, a stop or take-profit gapped through fills as above);
> the `CLOSE` bullet's *"a `MARKET` sell at the next bar's open plus slippage"*, which
> R-W(d) qualifies, since a `CLOSE` queues to the first bar after a gap; the Entry
> bullet's *"else the `FOK` is refused"*, which R-W(d) extends to an entry whose next slot
> is missing; and the Fees bullet's *"charged on both legs ... quote-denominated in the
> ledger"*, which R-W(c) makes exact: the entry fee is folded into the entry quote total
> and recorded separately in the trade log. **The double count at a gapped-through open
> is documented, not removed:** a stop that the open has gapped through fills at the open
> less the stop slippage, and that slippage is itself the stop's, so the gap and the
> slippage both count against the strategy (R-W, last sentence). **What U6 now says:** it
> is resolved by R-U, and `core/interfaces.py` is edited at C2 of P105; the item below
> is annotated there. **What R-V leaves:** the P104 measurement (`M5m-121`) that a full
> run costs about 2.0 ms a bar stands, and the incremental frame is not built; S5's
> measured runtime decides whether it returns as its own Phase 1. **What survives:** the
> intrabar trigger, *"the stop wins"*, the stop-slippage default of 1.20% on both
> protective legs (R-B2), the entry rule of P99, the money-rule paragraph, and the
> arming condition. **K7** (below, under the K items) carries the dead cooldown: the
> owner named it K6 in R-X, but K6 is `scripts/trade_census.py`'s item (`M5m-025`), so it
> is K7 here and the collision is `M5m-134`.

> **ANNOTATED AT M5m P106 (C1), BY THE OWNER'S RULINGS R-AA TO R-AE: THE SECOND HALF OF S2
> IS RULED.** The rulings, verbatim:
>
> R-AA: "The simulated executor fills intent.quantity and never re-sizes. An entry is
> handed the bar whose open_time is the signal bar's open_time plus one interval; if that
> slot is missing the entry expires. Protection is active from the entry bar's open, so
> the stop and the take-profit act on the entry bar's high and low. A CLOSE queued over a
> gap leaves protection in force; on the first bar after the gap the stop's gap-through
> check runs before the CLOSE. After every pass, each open position's protection is ACTIVE
> when protective legs were requested and ABSENT_BY_DESIGN when none were, and every open
> position is stamped on every pair's candle. Position.opened_at is the entry bar's
> open_time; exits are booked at the bar's nominal end."
>
> R-AB: "Simulated fill prices are not rounded to the tick. No slippage cap is applied; the
> double count at a gapped-through open remains the documented bias."
>
> R-AC: "R-X's cooldown item is K7, because K6 was already allocated (R-I). R-X otherwise
> stands."
>
> R-AD: "Before any other commit, the cause of the M18 extra kill in
> test_download_zips.py is measured. If it is the wall-clock zip timestamp, the test
> fixture pins ZipInfo.date_time. No production code changes for it."
>
> R-AE: "One backtest smoke run is authorised: the committed config, BTCUSDT 1m and
> ETHUSDT 5m, 2024-03-01 to 2024-04-01, run twice."
>
> **What stops being true:** the P105 C5 annotation's *"What this leaves open: the simulated
> executor, which sequences these functions (which bar `fill_entry` is handed, when a `CLOSE`
> queues, what a refused or expired entry leaves in the portfolio)"*, since R-AA rules the
> bar (the signal bar's open plus one interval), the queue (over a gap, with protection in
> force and the post-gap stop check before the `CLOSE`) and what a pass leaves behind (an
> `ACTIVE` or `ABSENT_BY_DESIGN` protection and a fresh stamp on every open position). Only
> the wiring and the root remain open from that sentence. `fill_model.py`'s module
> docstring said *"Rounding to the tick is a refinement nobody has ruled"*, which R-AB
> rules; C1 corrects that sentence, under the standing docstring authority, with the
> module's AST unchanged once its docstrings are removed. **R-AD is carried out** at
> `41a621a`: the cause was the wall-clock zip timestamp (`M5m-162`), and
> `tests/unit/test_download_zips.py` now pins it. **What R-AA leaves to be proved by tests,
> not assumed:** that a stop can fire on the entry bar itself, which `M5m-158` had left
> undecided, and that parity with the live booking identity holds through the unchanged
> `Portfolio`. **What survives:** every earlier S2 ruling, the intrabar trigger, *"the stop
> wins"*, the stop-slippage default of 1.20%, and the arming conditions. **R-AC settles the
> cooldown item's name as K7** (annotated there), and the architect's account of how the
> collision arose is `M5m-161`.

> **ANNOTATED AT M5m P106 (C2): THE SIMULATED EXECUTOR IS BUILT, AND EACH SENTENCE OF R-AA IS
> PROVED BY A TEST.** `trading_bot.backtesting.simulated_executor.SimulatedExecutor` satisfies
> `Dispatcher` and sequences `fill_model.py` against the unchanged `Portfolio`. `dispatch` records an
> approved entry or `CLOSE` and fills nothing; `__call__` runs first on every bar of every pair and,
> in order, observes the bar (a jump in open time is a gap, a close earlier than the slot a
> registered short bar), settles a pending entry against the bar one interval after the signal bar
> (or expires it, R-W(d)), settles the pair's position against the bar, and stamps every open
> position of every pair `ACTIVE` or `ABSENT_BY_DESIGN` with the simulated instant. Protection is
> active from the entry bar's open, so a stop or target acts on the entry bar's own high and low;
> an exit is booked at the bar's nominal end; `Position.opened_at` is the entry bar's open time;
> `intent.quantity` is filled as sized and never re-sized. The booking identity is the live one:
> `realised = exit total - entry quote total - exit fee`, the entry fee inside the quote total
> (R-W(c)). 50 hand-computed tests in `tests/unit/test_simulated_executor.py`, and a Q2 mutation
> survey of 33 mutations (the commit message carries the table).
>
> **Two readings of R-AA that the owner may wish to overrule, stated so a result is not read as
> free of them.** (1) A `CLOSE` queued on bar `t` sells at the open of bar `t + 1` with NO
> protective test first, because live cancels the protective legs before it sells; R-AA's
> gap-through check before the `CLOSE` is run only on a bar that FOLLOWED A GAP, as its text says.
> (2) On that bar only the STOP's gap-through check runs first, as R-AA names it; a take-profit the
> open gapped over is not tested, so the `CLOSE` sells at that open less 0.05%, which is better for
> the strategy than the target's own fill at its trigger less 1.20%. A bias in the strategy's
> favour, pinned by a test.
>
> **What stops being true:** the P106 C1 annotation's *"What R-AA leaves to be proved by tests, not
> assumed: that a stop can fire on the entry bar itself ... and that parity with the live booking
> identity holds through the unchanged `Portfolio`"*: both are proved. `M5m-158`'s *"whether a stop
> may fire on the entry bar's own low is the simulated executor's sequencing and not decided here"*
> is decided by R-AA. **What survives:** the wiring and the root, which are C4 and C5, and the smoke
> run, C6.

> **ANNOTATED AT M5m P106 (C4): THE BACKTEST ROOT IS BUILT.** `backtest_system` in
> `backtesting/engine.py` assembles the collaborators `live_system` assembles (the buffered
> provider, the trading engine, the risk manager, the intent logger and the one signal handler)
> and swaps three: a `ReplayClient` for the REST seed, a `ReplayStream` for the feed and the
> `SimulatedExecutor` for the order placer. The risk manager reads the replay's simulated instant.
> No venue call is possible and no credential is read. It follows `CLAUDE.md`'s root rule: the
> client is closed unconditionally by the outermost scope, the provider is built with
> `owns_client=False`, and the scopes nest. **The executor registers on the provider before the
> engine does**, so it meets each bar first; that order is also what hands an entry the bar after
> its signal bar (R-AA), and `test_the_executor_is_registered_ahead_of_the_engine` pins it
> (`M5m-171` is answered).
>
> **A run that raised is not a result.** The provider, the engine and the signal handler each
> isolate a failing subscriber, so a run could finish with fills silently skipped. The system
> counts every record logged at ERROR or above while it runs and the stream's own handler
> failures, and `BacktestResult.complete` is true only if neither occurred, every pair served at
> least one bar, and the cash identity holds exactly: `initial + realised - the quote total of
> every open position = free quote`.
>
> **The run record (P104 B7)** is JSON plus `trades.csv`, written by `write_run` into a new
> directory that is never overwritten. It names the code that ran, the config's digest, the
> digests of every series' manifest and registry and of the `exchangeInfo` files, the resolved
> window, every fill parameter, the strategy, the library versions, what each pair served, the
> executor's counts, the entries by result, the results (trades, flagged trades, realised, fees,
> the cash residual, the trade-log digest) and the problems. `record_digest` is the SHA-256 of
> the record without its `wall_clock` block: two runs of one history return the same one.
> 32 tests in `tests/unit/test_backtest_engine.py` over a real store built through `ingest_zip`
> (`tests/unit/backtest_world.py`), the determinism test among them, and a Q2 survey of 17
> mutations (the commit message carries the table).
>
> **Arming audit.** U6 was resolved and struck at P105 C2, so its condition, *"whoever writes
> `paper/simulator.py` or `backtesting/engine.py`"*, arms nothing; this commit writes
> `engine.py` and fires nothing. S4's condition, *"whoever next edits the fill model in
> `backtesting/engine.py`"*, names a file that now exists and still holds no fill model, which
> is in `fill_model.py`; **REAFFIRMED**, with the line-742 condition, because the calibration
> run has not happened. S2's own condition, `_cmd_backtest` or `BacktestConfig`, is not
> touched here and fires at C5.
>
> **What stops being true:** the P105 C5 annotation's *"`engine.py` stays a stub"* and its S4
> note that `backtesting/engine.py` *"is still a docstring-only stub"*, each true when written;
> `CLAUDE.md`'s and `README.md`'s `engine†` and `README.md`'s count of ten docstring-only files,
> now nine (corrected in place); and `CLAUDE.md`'s *"The two not yet written are
> `paper/simulator.py` and `backtesting/engine.py`"* (annotated there). **What survives:**
> `_cmd_backtest` still exits "not implemented yet" until C5, and the smoke run is C6.

> **ANNOTATED AT M5m P106 (C5): THE `backtest` COMMAND IS WIRED, AND S2'S ARMING CONDITION
> FIRED.** `_cmd_backtest` in `main.py` resolves the window (the flags laid over the
> configured one and re-validated, so a reversed or empty window is refused as it would be at
> load), runs `run_backtest`, writes the run record into a new directory
> `<data_dir>/../backtests/<UTC microseconds>-<trade-log digest>` and returns 0 for a result
> and 1 for a run that is not one. The flags are `--start`, `--end` (`YYYY-MM-DD`, UTC,
> half-open as the config's) and `--symbols`; the record names the RESOLVED window and the
> pairs actually replayed, not the configured ones. The stamp carries microseconds because
> the first draft's did not: two runs of one history inside a second named one directory and
> `write_run` raised `FileExistsError`, which `main` does not catch (`M5m-176`). 15 tests in
> `tests/unit/test_main_backtest.py` and a Q2 survey of 8 mutations (the commit message
> carries the table). `data/backtests/` falls under the existing `data/*` ignore, so a run
> leaves the checkout clean.
>
> **Arming audit.** S2's condition, *"whoever next edits `_cmd_backtest` in `main.py` or
> `BacktestConfig` in `config/models.py`"*, fires on `_cmd_backtest`. **REAFFIRMED, to be
> retired by C6:** the item's content (the engine on the live decision path with the stated
> fill model, the money-rule conversion, the command) is built, and what remains is the
> smoke run, which is C6 and is what closes S2. `BacktestConfig` is not edited here.
>
> **One existing test's SETUP changed, and no assertion did.**
> `test_refused_provenance_does_not_gate_other_subcommands` in `tests/unit/test_main.py`
> asserted `main([..., "backtest"]) == 0`, which encoded the stub's exit. MEASURED against a
> copy of the HEAD test: it fails with `assert 1 == 0` once the command is real, because the
> test's config has no stored history. Its subject is that a refused provenance does not gate
> the subcommand, not the replay, so the test now stubs `cli._cmd_backtest` to return 0 and
> every assertion is as it was. No named ruling overturns that assertion, so this is reported
> for the owner and not taken under the ruled-overturn authority (`M5m-177`).
>
> **What stops being true:** `README.md`'s *"Not a backtester yet"*, its `# not implemented
> yet` command comment, its *"`backtest` exits with 'not implemented yet'"* and its roadmap
> row *"Backtesting, paper simulator, notifications | stubs"*, each corrected in place; and
> this annotation's own predecessor above, *"`_cmd_backtest` still exits 'not implemented
> yet' until C5"*, true when written. **What survives:** the smoke run (C6) and S3's metrics.

> **ANNOTATED AT M5m P106 (C6): THE SMOKE RUN IS MADE, AND S2 IS BUILT.** R-AE's run was made
> twice, from `d5bff58` with a clean tree, and is recorded in `docs/RUN_LEDGER.md` section 32:
> both runs complete with no problem and no ERROR record; 53,568 bars served; 628 entries
> queued, 628 filled, none refused by `FOK`, none expired; 626 trades booked and two positions
> open at the end; the two trade-log digests equal
> (`5350070f7a9eeea27f8f8e63ddc765110a9b66bd3e06881e9dfdd657c313ba36`), the two `trades.csv`
> byte-equal and the two records equal outside `wall_clock`; every one of the 626 rows
> satisfies `realised = exit total - entry total - exit fee`; no gap and no short bar. An
> independent pandas derivation over the stored files agreed on the bar counts and on the 628
> up-crosses. **118.8 s and 118.3 s a run, 2,218 and 2,209 us a bar**, inside `M5m-121`'s
> 1,987 to 2,279, so the projection for S5's joint baseline stands. This is a test of the
> machine and not a result: 113 of the 626 trades won and realised was -384.31 USDT with 244.85
> USDT of fees, and nothing here is a statement about the strategy.
>
> **S2's arming condition is RESOLVED and retired here.** C5 REAFFIRMED it until the smoke
> run: both of its sites have been edited (`BacktestConfig` at P105 C1, `_cmd_backtest` at C5),
> the money-rule conversion is discharged, and the item's content is built and has run. **S2
> is closed.** Nothing in the register changes: the condition was parsed in S2's own text,
> which stands as the record.
>
> **Three things for the owner, none of them changed here.** (1) **The backtest writes into
> the bot's own log** (`M5m-179`): 6,308 lines in two runs, including `intent_dispatched` and
> `engine_stopped clean_shutdown=False`, which a census over `logs/trading_bot.log` would count
> as the bot's; whether it should log to its own file is a ruling. (2) The runs were made from
> the development tree on an EDITABLE install, so the record cannot name the running code
> beyond a clean checkout at `d5bff58` (`M5m-182`); S5 to S7 are the runs whose provenance
> matters, and a deployment clone with its own non-editable venv would need the stored history
> copied in, since `data/*` is not in git. (3) One of the 17 `nothing_to_close` refusals per
> run is unexplained (`M5m-183`).
>
> **What stops being true:** the C5 annotation's *"REAFFIRMED, to be retired by C6"*, and
> `README.md`'s *"has not yet been run over a real window"* and *"not yet run over a real
> window"* (corrected in place). **What survives:** S3 (metrics) is next and unbuilt, S4's
> calibration, and every earlier S2 ruling.

> **ANNOTATED AT M5m P107 (C0), BY THE OWNER'S RULINGS R-AF TO R-AL: THE BACKTEST'S LOG, ITS
> PROVENANCE, S3'S DEFINITIONS AND THE TESTNET KLINE QUESTION ARE RULED.** The rulings,
> verbatim:
>
> R-AF: "M5m-177's setup change is ratified; its test keeps its subject and no assertion
> moved. S2's retirement at C6 is ratified."
>
> R-AG: "A backtest logs only to a file in its own run directory, never to
> logs/trading_bot.log."
>
> R-AH: "Every run record carries the boot_provenance verdict and its fields. A run used as
> evidence for S4 to S7 comes from a deployment clone, with the verdict accepted."
>
> R-AI: "Regimes are labelled per calendar quarter by BTCUSDT's quarterly return: above +15%
> rising, below -15% falling, otherwise sideways. The labels are computed once from the
> store, committed in a file with its digest, and fixed before S6."
>
> R-AJ: "Maximum drawdown is the largest peak-to-trough decline of mark-to-market equity,
> sampled at every bar of any pair, as a fraction of the running peak. It is computed in the
> loop, exactly. Daily closing equity is recorded for Sharpe and Sortino, annualised over 365
> days."
>
> R-AK: "The per-trade return and its 95% interval are computed exactly as
> scripts/trade_census.py computes them (z = 1.96, sample sd, return on the entry quote
> total), and parity is proven by test on a shared set of trades."
>
> R-AL: "Testnet kline availability for S4 is measured now, read-only: the earliest BTCUSDT
> and ETHUSDT 1m and 5m kline Testnet returns, and whether 2026-09-04 to 2026-09-25 is
> retrievable in full."
>
> **R-AL is carried out in this commit, and the answer is NO** (`docs/RUN_LEDGER.md` section
> 33, `M5m-187`): Testnet returns klines only from `2026-10-07T10:30Z`, for all four series,
> and none of the 30,240 one-minute or 6,048 five-minute bars of the window exists there. So
> **S1's annotation *"the unmeasured question of what Testnet retains (`M5m-032`) is S4's to
> answer first"* is answered** (about two days), and **S4's calibration against the Testnet
> trades of 2026-09-04 to 2026-09-25 cannot take its klines from the Testnet REST path.**
> That is an open question for the owner, not decided here: the bars those trades saw are
> gone from the venue, and the store holds mainnet bars only.
>
> **The smoke run's three open items are each ruled or explained.** (1) The shared log: R-AG,
> which P107's C1 carries out. (2) The editable install: R-AH, which P107's C2 carries out. (3) `M5m-183`, the refusal P106 could not
> explain, is **explained** (`M5m-184`, `M5m-185`): it is the legitimate death cross of
> ETHUSDT at `2024-03-05T08:04`, refused because an extra `CLOSE` at `03:34:59.999` had already
> closed the position, and that extra `CLOSE` is the strategy treating an exact tie of the
> two averages as a cross, decided by floating-point noise that depends on the buffer's
> length. It is not the owner's hypothesis of a down-cross before any up-cross. **What stops
> being true:** the P106 C6 annotation's *"One of the 17 `nothing_to_close` refusals per run
> is unexplained (`M5m-183`)"* and its two other *"for the owner"* items as open; and the S1
> annotation named above. **What survives:** every S2 ruling, S3's list, and the arming
> conditions.

> **ANNOTATED AT M5m P109 (C3), BY THE OWNER'S RULINGS R-AQ AND R-AX: THE TIE IS FIXED, AND
> `sma` IS WINDOW-ONLY.** `indicators.sma` no longer uses pandas' `rolling().mean()`, whose
> running sum made the last digit of a window depend on every row ahead of it. Each window is
> now summed along its own row of a contiguous block and divided once, so a value is the same
> bits whatever the buffer holds before the window; tested against buffer starts, against the
> whole series and against chunk boundaries, and reproduced on the M5m-184 bar from 120 real
> closes, where `rolling` flips with the buffer and `sma` does not (`tests/unit/test_sma_window_only.py`).
> No tie tolerance is added (R-AX), so a decimal tie of the two averages is still decided by the
> float64 rounding of each window, now the same rounding in every buffer. **What stops being
> true:** the paragraph above's *"decided by floating-point noise that depends on the buffer's
> length"* (true of the code until this commit, false after it); RUN_LEDGER section 33's S0d,
> *"Nothing was changed ... and the question is the owner's"* (ruled by R-AQ); and its account
> that the averages tie *"mathematically and the floats differ in the last digit"*, which
> P108 C1 corrected: the DECIMAL closes tie (both 3627.774), while the float64 closes sum to
> averages 9.09e-15 apart. **What survives:** `M5m-183`'s explanation of the 17th refusal, the
> one extra `CLOSE` at `03:34:59.999` as the cause, and the arming conditions. The census of the
> other indicators (P108 C3) stands: `ema`, `macd`, `rsi`, `atr` are recursive and
> `bollinger_bands` still uses `rolling`; none is read by a live strategy.

> **ANNOTATED AT M5m P107 (C1): R-AG IS CARRIED OUT -- A BACKTEST LOGS ONLY TO A FILE IN ITS
> OWN RUN DIRECTORY.** For the `backtest` command `main` switches the config's file sink off
> and attaches `DeferredFileHandler` (`utils/logger.py`), which holds every record from the
> banner on. `_cmd_backtest` validates the window and the symbols first, so a refusal leaves
> no directory and no file; then it makes `<stamp>-running`, opens `backtest.log` in it (mode
> `x`, so no log is appended to) and the handler writes the held records and every later one.
> The run record is written beside it, the log is closed and the directory is renamed to
> `<stamp>-<trade-log digest>`; a run that raises is renamed `<stamp>-failed` and keeps its log
> with the error in it. The console sink is unchanged, since R-AG names files. Pinned by
> `tests/unit/test_main_backtest.py::TestTheLogStaysInTheRunDirectory` (a control arm proves
> the config does write `logs/trading_bot.log` for `strategies`, so the untouched file is not
> merely untouched because logging is off) and 11 tests of the handler. **What stops being
> true:** the P106 C5 annotation's *"writes the run record into a new directory"* as a
> statement that the directory is made after the run; it is now made before it and renamed.
> `write_run` gained `existing=` for this, and `select_pairs` in `backtesting/engine.py` is
> public so the command can refuse an unenabled symbol before it makes anything. **What
> survives:** the directory's final name, the record, `trades.csv`, and the console output.

> **ANNOTATED AT M5m P107 (C2): R-AH IS CARRIED OUT -- EVERY RUN RECORD CARRIES THE
> `boot_provenance` VERDICT AND ITS FIELDS.** The record has a new `provenance` block holding
> every field of the boot line (`verdict`, `refusal_reasons`, `install_kind`, `code_commit`,
> `code_intact`, `checkout_commit`, `checkout_dirty`, `commits_agree`, `config_tracked` and the
> rest), and `RUN_RECORD_SCHEMA` is 2. `main` hands the very `Provenance` it logged at boot to the
> run, so the block IS that line and not a second collection. A source of facts with no verdict
> (a test's injected facts) is recorded as `unrecorded`, never as `accepted`. The short `code`
> block is kept, as the subset of those fields it always was. The block is inside
> `record_digest`, so a record's digest now changes with its verdict. **What it does and does
> not do:** a backtest is still not refused on a refused verdict, since it touches no venue,
> store or lock; R-AH's second sentence, *"a run used as evidence for S4 to S7 comes from a
> deployment clone, with the verdict accepted"*, is an operator rule that this record makes
> checkable by reading `provenance.verdict`, and nothing enforces it. **What stops being true:**
> the P106 C6 annotation's *"the runs were made from the development tree on an EDITABLE
> install, so the record cannot name the running code beyond a clean checkout"* as a defect of
> the record: its fields were there and the verdict was not, and both are now. The smoke runs
> of P106 (schema 1) carry no `provenance` block and stay as they were.

> **ANNOTATED AT M5m P107 (C4a, C4b): R-AI IS CARRIED OUT -- THE REGIME LABELS ARE COMPUTED,
> COMMITTED WITH THEIR DIGEST, AND FIXED.** `scripts/regime_labels.py` (C4a) read BTCUSDT's
> daily bars from the store once, through the hash-verifying `HistoricalStore`, and wrote
> `docs/REGIME_LABELS.json` and `docs/REGIME_LABELS.json.sha256` (C4b): **37 calendar quarters,
> 2017Q3 to 2026Q3; 36 labelled** (13 rising, 7 falling, 16 sideways) **and 1 partial**
> (2017Q3, which begins 2017-08-17 and so carries no label). The file's SHA-256 is
> `6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72`, the digest of the store's
> `BTCUSDT/1d/MANIFEST.jsonl` it was read from is
> `39247bf6d4a3281a1de88f367f316bdf6fd94de276a9f8ba03ca830930a1ce04`, and the script's `--check`
> re-derives both from the store and refuses nothing it finds equal. The script refuses to write
> over either file (exit 2), and `tests/unit/test_regime_labels_committed.py` fails if the labels
> are edited by hand. **They are fixed before S6**: a different label set is a new file and a new
> ruling, not an edit.
>
> **The definitions R-AI leaves open were chosen, and are the owner's to overrule (`M5m-194`):**
> UTC calendar quarters, half-open; the return `close_last / open_first - 1` over the daily
> bars; a quarter is labelled only if the store holds one daily bar for every day of it; and the
> thresholds are strict and decided by exact comparison, not by a rounded quotient. A trade
> whose quarter is partial, or outside the table, has no regime; the metrics report it as
> `unlabelled`, and S7's *"positive net in at least two of the three regimes"* counts the three
> regimes only.
>
> **What stops being true:** the S7 annotations' *"the regime labels are date ranges fixed in the
> research log before S6's first run"* (P99, restated at P101): the labels are quarter labels
> in `docs/REGIME_LABELS.json`, which is the fixing, and no research-log entry is needed to
> make them so. The "date ranges" survive as the quarters' `[start, end)`. **What survives:**
> every S7 threshold, the 1.20% pass level, the joint run and the recording of the outcome.

**S3. Metrics.** Fill `backtesting/metrics.py`: trades, net and gross P&L, fees paid,
win rate, average win and loss, profit factor, maximum drawdown on the equity curve,
daily Sharpe and Sortino ratios, exposure, and holding period. Each figure is `Decimal`
where it is money and states its denominator.

*Arming condition:* **whoever next edits `backtesting/metrics.py`.**

> **ANNOTATED AT M5m P107 (C5): S3'S ARMING CONDITION FIRED, AND `backtesting/metrics.py` IS
> BUILT -- THE PURE HALF.** The stub is now `EquityCurve` (the per-bar accumulator),
> `compute_metrics` and the functions under it, with 62 tests in `tests/unit/test_metrics.py`.
> **REAFFIRMED, to be retired by C6:** the item is not complete until the root samples the
> portfolio in its loop and writes the metrics into the record, which is C6, and until the Q2
> survey has run on it. What is built, with the definitions the rulings leave open (`M5m-200`):
> net P&L is the sum of `realised` (net of both fees) and gross is `exit_gross - entry_notional`,
> with `gross - fees - net` carried as a residual that must be zero; a win is net realised above
> zero; profit factor is wins over absolute losses, net and gross; the per-trade return and its
> interval are `scripts/trade_census.py`'s, proven equal on 40 shared trades through the census's
> own parser; the maximum drawdown (R-AJ) is kept as the (peak, trough) pair with the largest
> fraction and decided by cross-multiplication, so no rounded quotient picks the maximum; Sharpe
> and Sortino are over daily closing equity, carried forward over empty days, times `sqrt(365)`,
> checked against closed forms `sqrt(1095)/6` and `sqrt(1095)/3`; exposure is the union of the
> trades' holding intervals and of the positions still open; and the breakdowns are by pair and by
> regime, a trade in a partial quarter being `unlabelled`. Every figure states its denominator in
> the record. **What stops being true:** nothing in S3's text; the README's *"metrics are not
> built"* is corrected in place.

> **ANNOTATED AT M5m P107 (C6): S3 IS WIRED INTO THE ROOT, AND R-AJ'S LOOP IS BUILT.**
> `backtest_system` registers `_EquityProbe` on the provider right after the executor, so after
> EVERY bar of EVERY pair, with that bar's fills already in the portfolio, it marks every held
> symbol at the provider's last close (exact `Decimal`) and calls `EquityCurve.observe`; a missing
> mark makes `Portfolio.equity` raise and the run incomplete rather than guess one. The record
> (schema 3) gains `quote_asset`, `equity` (the curve's summary: initial and final equity, the
> worst-decline pair with its times, the daily closes, the positions still open and the span),
> `metrics` (S3's figures, each with its denominator, whole and by pair and by regime) and
> `regime_labels` (the digest of the label file, or `null`). A fee identity that fails (`gross -
> entry fees - exit fees - net`) is a problem that makes the run not a result. `backtest` reads
> `docs/REGIME_LABELS.json` from the launch directory and refuses, before it makes a directory, a
> file that does not match its digest file; an absent file is a warning and no regime breakdown.
> The recorded metrics are recomputable from `trades.csv` and the record's `equity` block alone
> (tested to exact equality), which is how C7 recomputes the smoke run's. **What stops being
> true:** the P106 C4 annotation's list of what the record names, which now also names the
> equity, the metrics and the label digest; and README's *"it has no metrics"* and *"the metrics
> are built, not yet wired into the run"*, corrected in place. **S3's arming condition stays
> REAFFIRMED** until the Q2 survey of `metrics.py` has run, and is retired by the commit that
> records it.

> **ANNOTATED AT M5m P107 (C6b): THE Q2 SURVEY OF `metrics.py` HAS RUN, AND S3'S ARMING CONDITION
> IS RESOLVED AND RETIRED HERE.** Thirty mutations, in a disposable detached worktree outside the
> repository, predictions written first (`F:\trading bot\scratch\p107\predictions_survey.txt`),
> an unmutated baseline of 3147 passed and 4 skipped there, the import location proven in all 30
> full-suite sessions, every restore byte-identical, and the worktree removed. **Predicted 59
> kills; observed 98, none fewer.** Twenty-six mutations matched their predicted sets exactly;
> four killed more (Q02, Q18, Q29, Q30), each through a run-level test in
> `test_backtest_metrics.py`, `test_backtest_engine.py` or `test_main_backtest.py`, which is real
> coverage. The two declared equivalents survived, as predicted: touching exposure intervals
> merged or added (Q11) and the drawdown comparison by 28-digit quotient (Q16; `M5m-207`).
> Preparing the survey found and fixed three tests that would have mis-scored it (`M5m-208`,
> `M5m-209`, `M5m-210`). **S3 is closed.** Nothing in the register changes: the condition was
> parsed in S3's own text, which stands as the record. **What stops being true:** the C6
> annotation's *"S3's arming condition stays REAFFIRMED until the Q2 survey of `metrics.py` has
> run"*. **What survives:** C7's recomputation of the smoke run, and Q2's survey of S2's fill
> model, which ran at P106.

> **ANNOTATED AT M5m P107 (C7): THE SMOKE RUN ON THE C6 CODE HAS BEEN MADE AND ITS METRICS
> RECOMPUTED EXACTLY, SO P107's S3 WORK IS COMPLETE.** One run, the committed config over March
> 2024, from `c5e11f1` on the editable install: exit 0, trade log and `trades.csv` byte-equal to
> P106's, the metrics block equal to `compute_metrics` over `trades.csv` and the record's `equity`
> block with the committed labels, and three figures (net P&L, win rate with the profit factor,
> maximum drawdown) plus the daily Sharpe confirmed by hand; `docs/RUN_LEDGER.md` section 35.
> The run is a check of the machine and not evidence for S4 to S7 (R-AH: its verdict is
> `refused`). Two predictions missed and are recorded: the runtime, 145.4 s against a ceiling of
> 137 s, which the equity probe (0.48 s) does not explain and nothing yet does (`M5m-216`), and
> the drawdown band (`M5m-217`). **What stops being true:** the C6b annotation's *"What survives:
> C7's recomputation of the smoke run"* (done), and README's *"smoke-run once"* and *"run only
> once"* (corrected in place). **What survives:** S4's calibration, the single remaining S item
> before S5, and the runtime question, which matters to S5's joint baseline estimate of 3.2 to
> 3.7 hours: at 2,715 us a bar the same 53,568 bars cost 145 s, not 119 s.

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

> **ANNOTATED AT M5m P105 (C0), BY THE OWNER'S RULING R-Z: S4 LOADS ITS FILTERS FROM A
> STORED TESTNET SNAPSHOT.** R-Z, verbatim and quoted under S2 above: *"One keyless
> exchangeInfo GET per symbol, on mainnet and on Testnet, is authorised. The raw response
> is stored with its SHA-256, and backtests load filters only from the stored file."* So
> S4's replay of the windows the bot traded on Testnet reads the Testnet snapshot of
> `BTCUSDT` and `ETHUSDT`, and S5 to S7 read the mainnet one; a backtest never asks the
> venue for filters. **What stops being true:** nothing in S4's text. **What it adds:**
> the arming condition's named site, *"the fill model in `backtesting/engine.py`"*, is
> moved by P105's C5 to `backtesting/fill_model.py` and the simulated executor's
> sequencing, and C5 annotates the condition there (`M5m-131`).

> **ANNOTATED AT M5m P105 (C5), AS C0 PROMISED: S4's ARMING CONDITION NOW NAMES THE FILL MODEL
> WHERE IT LIVES.** The condition above, *"whoever next edits the fill model in
> `backtesting/engine.py`"*, names a file that holds no fill model: C5 wrote the model in
> `backtesting/fill_model.py`, and `backtesting/engine.py` is still a docstring-only stub. The line
> above stays standing, and the condition for S4 is also this one, which the arming register reads
> as its own:
>
> *Arming condition:* **whoever next edits `backtesting/fill_model.py`, or the simulated executor's sequencing of an entry, a protective fill or a `CLOSE` in `backtesting/`.**
>
> **Why the executor is named.** The model is price-only. Which bar an entry is handed, whether
> a `CLOSE` queues to the first bar after a gap, what an expired entry leaves in the portfolio
> and what a stop that fires on the entry bar does are decided by the caller, and a wrong
> sequence books a plausible trade at a wrong figure exactly as a wrong price does
> (`M5m-131`). **What survives:** S4's acceptance test as written, *"Divergence is diagnosed,
> never tuned away"*, and the census of record.

> **ANNOTATED AT M5m P109 (C1), BY THE OWNER'S RULINGS R-AM TO R-BB: S4 IS MEASURED BY A FRESH
> TESTNET RUN WHOSE KLINES WE RECORD OURSELVES.** The rulings, verbatim. R-AM to R-AU were ruled in
> P108 and R-AV to R-BB in P109.
>
> R-AM: "S4 is measured by option (c). The census of record's window, 2026-09-04 to 2026-09-25, is
> unmeasurable in retrospect, because Testnet's kline history now begins 2026-10-07 (P107 S0f). The
> census of record stays the evidence for M5m's premise and is no longer S4's comparison set."
>
> R-AN: "A keyless recorder stores Testnet 1m and 5m klines for the configured pairs, in the
> archive's normalised format with a manifest, under a store root separate from the mainnet store.
> It runs at least daily and backfills from its last stored bar, so a power cut or a venue reset
> cannot take a recorded window with it."
>
> R-AO: "S4's acceptance is pre-registered in a committed file before the run starts: the fixed
> start instant, the stop rule, R-C's figures (entries reproduced on the same symbol and entry bar,
> at least 80%; the backtester's per-trade gross mean inside the run's census interval; the trade
> count within 10%) and R-C2's refusal comparison, with the backtest's parameters for the
> comparison. Nothing in it changes after the start."
>
> R-AP: "The S4 run uses a deployment clone of a pushed commit, the committed config and Testnet,
> under the deployment procedure, and is recorded in RUN_LEDGER.md. Every restart during it,
> including one after a power cut, is recorded and is part of the evidence."
>
> R-AQ: "The exact-tie dependence of an indicator on buffer length (M5m-184, M5m-185) is a defect
> against CLAUDE.md's stateless-recomputation rule. It is fixed, and the fix pushed, before the S4
> run starts."
>
> R-AR: "A backtest run record carries evidence_eligible, true only when the provenance verdict is
> accepted. Every S4 to S7 comparison or decision refuses a record whose evidence_eligible is
> false."
>
> R-AS: "During a backtest the console carries WARNING and above; the full log goes to the run
> directory's file."
>
> R-AT: "M5m-194 and M5m-200 are ratified: a trade in a partial quarter belongs to no regime, and
> S7's regime test counts complete quarters only."
>
> R-AU: "The stale 0.5x-2x band text (P107 S0b) is annotated in docs/M5_NUMBERS.md and
> docs/QC_PROTECTIVE_ORDERS.md and corrected in the config/models.py comment. The test fixture is
> left as data."
>
> R-AV: "Clearing the Testnet BTC and ETH holdings with scripts/clear_testnet_holdings.py is
> authorised once, in P110, before the pre-registration commit. Equity is about 95,190 with or
> without it, because pre-existing holdings count toward equity; the clearing only unblocks
> entries."
>
> R-AW: "The recorder commits come immediately after the docs commit. The recorder runs from its own
> clone of a pushed commit, outside F:\trading bot\deploy, with no .env. It is keyless and touches
> no account, so the one-runnable-clone check over F:\trading bot\deploy is unchanged."
>
> R-AX: "No tie tolerance is added. sma becomes the window-only computation of P108 C2. A tolerance
> is strategy research and belongs to S6 if anywhere."
>
> R-AY: "The S4 run stops at the first UTC midnight that is at least T0 plus 21 days and has at least
> 150 bookings since T0, with a cap at T0 plus 35 days. At the cap S4 is evaluated if at least 100
> bookings exist; otherwise it is not measured, and a new pre-registration is required. T0 is the
> boot_provenance instant of the S4 clone's first boot, which must come after the pre-registration
> commit."
>
> R-AZ: "A venue reset during the run ends the run at the reset. S4 is evaluated on the bookings
> before it if there are at least 100; otherwise the run restarts under a new pre-registration."
>
> R-BA: "R-C2 is diagnostic: every refusal disagreement is listed and diagnosed, and it is not a
> separate gate. Its effect is gated through R-C's trade-count test."
>
> R-BB: "The pre-registration states the predicted entry notional at the post-clear equity and the
> census of record's median entry quote total. If they differ by more than 2x, the owner reviews
> before launch."
>
> **What stops being true:**
> - S4's own text, *"Replay the strategy over the windows the bot actually traded on Testnet ...
>   and compare trade by trade with S0's census"*, and the P99 annotation's *"S4 calibrates on
>   Testnet klines, for the windows the census covers"*: the comparison set is the fresh run's
>   (R-AM), not the census of record's.
> - The P101 annotation's figures as S4's gates, the per-trade gross mean inside
>   [-0.2223%, +0.0941%] and a trade count of 149 to 181: R-C's tests stand, but against
>   **the run's own** census interval and **the run's own** booked count (R-AO). The census of
>   record stays the evidence for M5m's premise. The 80% reproduction test is unchanged.
> - R-C2's *"a second test"*: it is diagnostic and not a separate gate (R-BA), and its effect
>   is gated through the trade-count test.
> - *"S4 depends on Testnet klines, whose retention is UNMEASURED (`M5m-032`)"*: measured
>   (`docs/RUN_LEDGER.md` section 33, S0f, and section 36): history begins 2026-10-07T10:30Z and
>   had not rolled between two readings an hour apart.
> - **T0 is not a pre-registered calendar instant** (R-AY): it is the `boot_provenance` instant of
>   the S4 clone's first boot, after the pre-registration commit. P108's draft fixed it at a UTC
>   midnight; that draft is superseded where it differs.
>
> **What survives:** *"Divergence is diagnosed, never tuned away"*, R-C's 80% reproduction test,
> R-B2's 1.20% stop slippage as the gate arm, the Testnet `exchangeInfo` snapshot (R-Z), and the
> arming condition. **Where each ruling is carried out:** R-AN in the recorder commits (P109 C2),
> R-AQ and R-AX in C3, R-AR and R-AS in C4, R-AU in this commit, R-AV in P110, and R-AO, R-AY,
> R-AZ, R-BA and R-BB in the pre-registration commit.

> **ANNOTATED AT M5m P109 (C4): R-AR AND R-AS ARE CARRIED OUT.** *R-AR.* A run record
> (schema 4) carries `evidence_eligible`, true only when `provenance.verdict` reads `accepted`
> (`backtesting/evidence.py`, written by `run_backtest`, part of the record digest). The one door
> is `load_eligible_record(path)` for a file and `require_evidence_eligible(record)` for a record in
> hand; both refuse a false, absent or non-boolean flag with `EvidenceRefusedError`, naming the verdict
> and its refusal reasons, so every record before schema 4 (the P106 and P107 smoke runs included) is
> refused. `tests/unit/test_backtest_evidence.py` reads every module under `src/` and `scripts/` and
> fails if one names `run.json` (or `RUN_RECORD_NAME`) without calling the door; the three modules
> allowed to name it are the ones that write or report its path (`engine.py`, `main.py`,
> `evidence.py`), and adding a fourth is a visible edit to a list in that test. *R-AS.* `backtest`
> raises the console handler (named `trading_bot.console` by `setup_logging`) to WARNING and leaves
> every other handler and the root level alone, so the run's file still holds everything. **One
> thing chosen, the owner's to overrule:** `_cmd_backtest` prints one plain line on completion,
> `backtest complete: N trade(s); record <path>`, which is not a log record, because a run that logs
> nothing above WARNING would otherwise say nothing. **What stops being true:** the P107 C1
> annotation's *"The console sink is unchanged, since R-AG names files"*; the P107 C6 annotation's
> record, described as schema 3, which is now schema 4; and `M5m-191` and `M5m-193` as open (the
> console, and R-AH's second sentence, which R-AR enforces for every consumer that goes through the
> door). **What survives:** R-AH, R-AG and everything else those annotations state. **What is still
> unenforced, and is not a defect of this commit:** a consumer that does not exist yet. The door
> exists for S4's comparison tool and S5 to S7's to call, and the census will fail the first of them
> that does not.

> **ANNOTATED AT M5m P110 (C2), BY THE OWNER'S RULINGS R-BC TO R-BH.** The rulings, verbatim:
>
> R-BC: "M5m-250 is fixed where it lives. If the truncation is in scripts/mutation_survey.py, it is fixed with a test that fails on the old code. Every saved M5m survey log is re-parsed under the fix, and any kill set or abstention that changes is recorded as a finding."
>
> R-BD: "The false rich docstring in utils/logger.py (M5m-255) is corrected under the standing docstring authority."
>
> R-BE: "A backtest prints figures, not a verdict. The judgement line (M5m-256) is removed."
>
> R-BF: "main.py comes under the evidence census (M5m-257)."
>
> R-BG: "M5m-251 is carried as an item: bollinger_bands is converted to the window-only form before any S6 candidate that uses it runs. Its arming condition names bollinger_bands and register_strategy."
>
> R-BH: "The clearing under R-AV happens only if R-BB's comparison, measured first, is within 2x. Otherwise P110 halts before the clearing, for the owner."
>
> **Where each is carried out.** R-BC in P110 C1 (`summary_node_ids` in `scripts/mutation_survey.py`; the re-parse is `docs/RUN_LEDGER.md` section 38: 0 kill sets and 0 abstentions changed in 12 distinct logs, and the mechanism was a reason suffix kept on an id, not a truncated id). R-BD, R-BE, R-BF and R-BG in this commit. R-BH was applied first: `docs/RUN_LEDGER.md` section 38 holds R-BB's comparison, 1.0522 and 1.0523, within 2x, so the clearing is C5.
>
> **What stops being true:**
> - The P109 C4 annotation's *"One thing chosen, the owner's to overrule: `_cmd_backtest` prints one plain line on completion"*: the owner has overruled it (R-BE). The line is gone, and a backtest's console carries only WARNING and above; the run's figures are in its record and in `backtest.log`, whose `Backtest complete` line now names the run directory.
> - That annotation's *"the three modules allowed to name it are the ones that write or report its path (`engine.py`, `main.py`, `evidence.py`)"*: from R-BF `main.py` is not listed, does not name the record, and must call the door if it ever reads one. The census lists two modules, `engine.py` and `evidence.py`, and `test_main_is_not_a_listed_writer` says so.
> - `M5m-250`'s *"truncates a long node id at the first ' - '"*: the id is whole and carries pytest's reason (`docs/RUN_LEDGER.md` section 38, S0a).
> - `utils/logger.py`'s *"`rich` is NOT installed in this environment"* (`M5m-255`): `rich==15.0.0` is a pinned runtime dependency and is installed.
> - `M5m-256` and `M5m-257` as open: R-BE and R-BF close them. `M5m-251` stays a finding and is item K8.
>
> **What survives:** R-AR and R-AS entire, and the census's two writers. A backtest's exit status is unchanged: 0 for a result, 1 for a run that is not one.

> **ANNOTATED AT M5m P110 (C4a): THE EVIDENCE CENSUS HAS A REAL CONSUMER.** `scripts/s4_compare.py`
> names the run record and reads it through `load_eligible_record`; each live `boot_provenance` line is
> judged by `is_evidence_eligible` and passed to `require_evidence_eligible`. **What stops being true:**
> the P109 C4 annotation's *"What is still unenforced ...: a consumer that does not exist yet"*, and
> `M5m-253`'s *"no S4 to S7 consumer exists to be pinned"*: one exists, and
> `test_the_real_s4_consumer_is_scanned_names_the_record_and_calls_the_door` pins that the scan
> reaches it. **What survives:** the scan is still synthetic for every consumer that is not this one, and
> a consumer that reads the record by another route (a path built from a string the scan does not see)
> is still not caught.

> **ANNOTATED AT M5m P110 (C5): R-AV IS CARRIED OUT.** The Testnet BTC and ETH holdings were cleared once, from
> the active deployment clone, after R-BB's comparison (R-BH) measured 1.0522 and 1.0523: two market sells,
> both `FILLED`, BTC 0 and ETH 0 afterwards, and the account's free USDT **95,170.91** (`docs/RUN_LEDGER.md`
> section 40). **What stops being true:** R-AV's *"Equity is about 95,190 with or without it"*, which is right
> to 19 dollars (the account held exactly 10,000.00 USDT, 1 BTC and 1 ETH before: 95,170.92 at the clearing's
> marks) but was a figure for the equity and not for the free USDT; `config.s4.yaml`'s `initial_balance` read
> `95190.0` and is now `95170.91`, the measured free USDT. The P108 draft's "the clearing fixes `<USDT>`" is what
> happened. **What survives:** everything else in R-AV, and the Testnet snapshots copied beside the recorded
> klines (section 40) for the C3 annotation's *"What the S4 run needs"*.

> **ANNOTATED AT M5m P110 (C6): THE PRE-REGISTRATION IS WRITTEN.** `docs/S4_PREREGISTRATION.md` carries out R-AO,
> R-AY, R-AZ, R-BA and R-BB, which the P109 C1 annotation assigned to *"the pre-registration commit"*: the stop
> rule and cap, the interruptions and the reset rule, the backtest's parameters with their digests, the acceptance
> tests A to C and the diagnosis D (diagnostic, not a gate), and R-BB's comparison at the measured 95,170.91
> (ratios 1.0518 to 1.0521). **What stops being true:** that annotation's *"R-AO, R-AY, R-AZ, R-BA and R-BB in the
> pre-registration commit"* as a future event, and P108's draft where it differs (a calendar `T0`, a whole-midnight
> window start, a `[OWNER: 0]` cap on `unexplained`). **What the owner may overrule before the push:** seven lines
> marked `CHOSEN` in the file, listed in `docs/RUN_LEDGER.md` section 41. **What survives:** *"Divergence is
> diagnosed, never tuned away"*, R-C's three tests as the gate, and R-AY's definition of `T0`, narrowed to the first
> `run` boot by one `CHOSEN` line. Nothing is launched by this commit.

> **ANNOTATED AT M5m P111 (C1): THE OWNER RATIFIED THE SEVEN `CHOSEN` LINES AND RULED R-BJ AND R-BK.** Recorded here
> and not in `docs/S4_PREREGISTRATION.md`, which stays frozen. The rulings, verbatim:
>
> R-BI: "The seven CHOSEN lines in docs/S4_PREREGISTRATION.md are ratified as written. Line 4: the live equity at W differs from the T0 balance by what was booked between T0 and W; R-C's figures are returns on the entry quote total, so the difference does not enter them, and it is accepted. Line 7: an unexplained disagreement is not a separate gate, and it counts against R-C's 80% match."
>
> R-BJ: "A difference between the WebSocket bars the bot trades on and the REST bars the recorder stores is an accepted risk of S4. It appears among the unexplained disagreements, and it is not separately measured in M5m."
>
> R-BK: "The S4 capture must contain every log record from T0 to the stop. If the configured log rotation cannot hold the run's predicted volume twice over, P111 halts for the owner before launch."
>
> **Where each is carried out.** R-BI: nothing in the pre-registration changes. This commit contains
> `docs/S4_PREREGISTRATION.md` unchanged, SHA-256 `49e4fdbba55a5f407d8db130ebdc6cf68fc13813a101ab7849e4740050c6566f`,
> so a clone of this commit satisfies its `T0` clause (the first `run` boot of a clone of a commit that contains the
> file). R-BK: P111's Step 1, `docs/RUN_LEDGER.md` section 42. The configured rotation holds 62,914,560 bytes (the
> active file and five backups of 10,485,760), the predicted volume of the 35-day cap is 5.2 to 8.3 MB at every
> measured rate and 17.9 MB at a structural bound, and the capacity is at least 1.75 times twice the volume in every
> case, so P111 did not halt. R-BJ: no instrument is added.
>
> **What stops being true:**
> - The C6 annotation's *"What the owner may overrule before the push: seven lines marked `CHOSEN` in the file"*, and
>   its *"R-AY's definition of `T0`, narrowed to the first `run` boot by one `CHOSEN` line"* as an open choice: R-BI
>   ratified all seven as written. The `CHOSEN` marks stay in the pre-registration, which is not edited; read them as
>   ratified. `docs/RUN_LEDGER.md` section 41's *"The seven lines the owner may overrule before the push"* is the same.
>
> **A reading R-BJ needs, which this commit does not decide (`M5m-290`).** R-BJ says the WebSocket-against-REST
> difference *"appears among the unexplained disagreements"*. The shipped `scripts/s4_compare.py` (SHA-256
> `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08`, frozen by the pre-registration) and the
> pre-registration's D list a cause `bar differs` ahead of `unexplained`: a disagreement on a bar whose recorded
> close differs from the close the live signal logged as its reference is tallied as `bar differs`, and only a
> disagreement with no such difference is `unexplained` (`_input_cause`). So a WebSocket-against-REST close
> difference that decides a signal is reported under `bar differs` wherever the live reference was logged. Neither
> count is a gate, and test C counts every unmatched entry whatever its cause, so A, B, C and the verdict are the
> same either way. If the owner means such cases to be called `unexplained`, that is a change to the frozen script
> and file, not a reading of them.
>
> **R-BK's other half: one capture file (`M5m-292`).** `scripts/s4_compare.py --capture` takes one file, and the
> launch checklist's daily freeze copies the active `logs\trading_bot.log`. The whole run stays in that one file
> while its average rate over 840 h is under 12,483 bytes an hour (10,485,760 / 840). Every measured rate is under
> it (the highest is 9,827); the structural bound (21,347) is over it, and there one rollover would put the first
> records in `logs\trading_bot.log.1`. No record is lost by that, since five backups are kept; the cost is that the
> capture is then two files and the comparison cannot read it until they are reassembled. The appearance of
> `trading_bot.log.1` is the signal, and the checklist's weekly log-size check (3.6) is where it would be seen.
> **What survives:** R-AY to R-BB and the pre-registration entire.

**S5. The baseline — the shipped strategy, honestly.** `sma_crossover` 20/50 on BTCUSDT
1m and ETHUSDT 5m, the committed config, over the full history, net of fees. This is the
number the census predicts to be negative; S5 confirms or refutes it on two years rather
than twenty days.

*Arming condition:* **whoever next edits `strategy` in `config.yaml`.**

> **ANNOTATED AT M5m P99: *"on two years rather than twenty days"* IS NO LONGER THE
> SPAN.** The owner ruled the history to be all available mainnet history for BTCUSDT
> and ETHUSDT (S1's annotation above). **What survives:** the item, and the
> prediction it states, which S5 confirms or refutes.

> **ANNOTATED AT M5m P105 (C0), BY THE OWNER'S RULING R-Y: S5 IS ONE JOINT RUN.** R-Y,
> verbatim and quoted under S2 above: *"S5 is one joint run of the committed config. S6
> and S7 runs are joint per candidate, with per-pair breakdowns reported."* So S5 is a
> single run of `BTCUSDT` at 1m and `ETHUSDT` at 5m through one portfolio, with the
> committed `max_open_positions`, one equity and one daily-loss limit, and not two runs
> added. **What stops being true:** nothing in S5's text, which already says *"on
> BTCUSDT 1m and ETHUSDT 5m, the committed config"*; the annotation settles that this is
> one portfolio. **What it implies, measured by P104 (`M5m-121`):** about 5.7 million bars
> in one process, 3.2 to 3.7 h at the current per-bar cost and once per stop-slippage
> level reported.

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

> **ANNOTATED AT M5m P105 (C0), BY THE OWNER'S RULING R-Y: S7'S POOLING IS A JOINT RUN
> WITH PER-PAIR BREAKDOWNS.** The S7 annotation above says the trade count *"may pool both
> pairs for one candidate"*. R-Y (quoted under S2) rules the run shape: *"S6 and S7 runs
> are joint per candidate, with per-pair breakdowns reported."* **What stops being
> true:** the word *"may"* in that sentence, since a candidate is run jointly and its
> trade count is over the joint run. **What survives:** every threshold, the pass level
> of 1.20%, the regime labels and the recording of the outcome; and the per-pair
> breakdowns are reported beside the joint figure, not instead of it.

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

### K7. `cooldown_minutes` is dead: `Portfolio.start_cooldown` has no caller (`M5m-125`)

**Carried as an item, not done now, by the project owner's ruling R-X at M5m P105,
verbatim:** *"The backtest applies no cooldown, at parity with live (M5m-125). The dead
cooldown_minutes is carried as item K6 for the milestone after a PASS, with an arming
condition naming Portfolio.start_cooldown."* **The owner called it K6, and K6 is taken:**
it is `scripts/trade_census.py`'s item above (`M5m-025`), so this one is K7 and the
collision is `M5m-134`; cite either by its content. MEASURED at P104 (`M5m-125`):
`Portfolio.start_cooldown` is defined in `core/portfolio.py`, and a grep of every `.py`
file in the repository for `start_cooldown` and `cooldown_until` finds the definition and
the field in `core/portfolio.py`, one mention in `persistence/store.py`, and calls only in
`tests/unit/test_risk_manager.py`. `src/` never calls it, so `risk.limits.cooldown_minutes`
(15 in the committed config, commented as a *"per-symbol pause after a stop-out"*) is never
applied live, while `in_cooldown` is read on every entry by `_approve`. The backtest is at
parity: it applies no cooldown either (R-X), and a backtest result is therefore a result
for a bot that re-enters at once after a stop-out. Deferred to the milestone after a PASS.

*Arming condition:* **whoever next edits `Portfolio.start_cooldown` in `core/portfolio.py`, or gives it a caller.**

> **ANNOTATED AT M5m P106 (C1), BY THE OWNER'S RULING R-AC: THE NAME K7 IS RATIFIED.** R-AC,
> verbatim: *"R-X's cooldown item is K7, because K6 was already allocated (R-I). R-X
> otherwise stands."* **What stops being true:** the paragraph above reads as the
> implementer's departure from R-X's text (*"The owner called it K6, and K6 is taken"*); from
> R-AC it is the owner's own naming, and R-X's *"item K6"* is read as K7. **What survives:**
> everything else in R-X, which R-AC says stands: the backtest applies no cooldown, at
> parity with live (`M5m-125`), and the item waits for the milestone after a PASS, with the
> arming condition above. The collision stays recorded as `M5m-134`, and the architect's
> account of its class is `M5m-161`.

### K8. `bollinger_bands` is still a rolling computation (`M5m-251`)

**Carried as an item, not done now, by the project owner's ruling R-BG at M5m P110,
verbatim:** *"M5m-251 is carried as an item: bollinger_bands is converted to the window-only
form before any S6 candidate that uses it runs. Its arming condition names bollinger_bands
and register_strategy."* MEASURED at P109 (`M5m-251`): `bollinger_bands` in
`indicators/indicators.py` still uses `rolling().mean()` and `rolling().std()`, so its values
depend on the buffer's start by up to 4.8e-13 relative on every bar, and its middle band
equals `sma` only to `assert_series_equal`'s tolerance. `sma` was made window-only at P109 C3
(R-AQ, R-AX) because a live strategy reads it and an exact tie decides an edge; no live strategy
reads `bollinger_bands`, so nothing fails today. The conversion is the same shape as `sma`'s:
contiguous window blocks summed along an axis, with bitwise tests; the standard deviation
needs its own derivation (REASONED: pandas' rolling standard deviation keeps running sums too,
which is the dependence on the rows ahead of the window that `sma`'s fix removed). **The order is the owner's: the conversion lands before any S6
candidate that uses `bollinger_bands` runs.**

*Arming condition:* **whoever next edits `bollinger_bands` in `indicators/indicators.py`, or calls `register_strategy` with a strategy that reads it.**

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

> **RESOLVED AT M5m P105 (C2), AND STRUCK.** The abstract `OrderExecutor` is removed from
> `core/interfaces.py` and a `Dispatcher` Protocol declaring `dispatch(signal, assessment,
> candle)` and `__call__(candle)` stands in its place; `_build_signal_handler` in
> `engine/modes.py` takes a `Dispatcher | None`; the live `OrderExecutor` satisfies it
> structurally and a simulated executor can. Twelve tests in `tests/unit/test_dispatcher.py`
> pin it (the ABC is gone, both members are coroutines with the live parameter names, the live
> class satisfies the Protocol without subclassing it, a class with either member missing or
> with only the dead `execute` does not, and the signal handler passes the exact objects to any
> dispatcher). No existing assertion changed. **The answer to the item's question was no, as
> the annotation below records, and the arming condition is retired:** *"whoever writes
> `paper/simulator.py` or `backtesting/engine.py`"* no longer arms a question, since the
> question is resolved. `_BootCloser` in `engine/modes.py` still types its executor as the
> live class; it calls only `dispatch`, and R-U names `_build_signal_handler` alone.
>
> **ANNOTATED AT M5m P105 (C0), BY THE OWNER'S RULING R-U: THE QUESTION IS ANSWERED AND
> THE ITEM IS RESOLVED AT C2.** P104 measured the answer (`M5m-124`): the live
> `OrderExecutor` in `execution/executor.py` does not subclass the abstract
> `OrderExecutor` in `core/interfaces.py`, which declares `execute(request: OrderRequest)
> -> Order` and has no implementer and no user in `src/`; the live seam is `dispatch(signal,
> assessment, candle)` with `__call__(candle)`. R-U, verbatim: *"U6 is resolved. The unused
> ABC OrderExecutor in core/interfaces.py is replaced by a Dispatcher Protocol declaring
> dispatch(signal, assessment, candle) and __call__(candle). _build_signal_handler takes a
> Dispatcher."* **What stops being true:** *"Carried, unfired"*, once C2 lands; C2 strikes
> this item. **The arming condition is AUDITED, not fired, by C0:** no file under
> `backtesting/` is written by this commit.

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
