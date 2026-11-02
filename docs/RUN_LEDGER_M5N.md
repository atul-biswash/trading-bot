R-EE  This file holds the M5n ledger sections written on branch m5n (ee8d485..2c32af0), with their original numbers. Any reference to 'RUN_LEDGER section N' in a commit of ee8d485..m5n, or in an M5n document (docs/M5N_CHARTER_DRAFT.md, docs/M5N_PREREGISTRATION.md), means section N of this file. docs/RUN_LEDGER.md keeps main's sections. Ruled at the M5n merge because both branches numbered sections 74 to 82; the pre-registration's text and digest are unchanged.

## 74. M5n N2a: P140's halts and the predictions for the 4h and 1d bar aggregation and its venue verification, before any code (P140 C2, R-T, R-DQ, R-DT)

An observation log, so this section only adds. P140 builds the aggregation of the 1m store into 4h and 1d bars and a script that compares them with the venue's klines over `[2017-08-17, 2024-01-01)`. It runs on branch `m5n`, from `main` at `ee8d485`. Under R-DQ clause (1) this section is committed BEFORE any code or test is drafted, in scratch or in the repository. The only reading done before it was of the source (`src/trading_bot/data/historical.py`), of the store's directory listing and of its `MANIFEST.jsonl` files (row counts and times, no bar value), which the clause allows. **Everything here decides nothing about S4, and no return, P&L, equity or metric is computed.**

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| `git status` not clean | `git status --porcelain` | empty |
| HEAD is not `ee8d485` before branching | `git rev-parse --short HEAD` | `ee8d485`, then `git switch -c m5n` |
| a command would write under `deploy\45547f107715`, the rehearsal clone or the canonical store | every command in the plan | none: the store is opened by `HistoricalStore`, which "only reads" (`historical.py` `HistoricalStore` docstring); raw responses go to scratch |
| a request sends a key or targets anything but public mainnet `/api/v3/klines` | the script's one URL | `https://api.binance.com/api/v3/klines`, `symbol`, `interval`, `startTime`, `endTime`, `limit` only; no header, no signature |
| a bar at or after `2024-01-01T00:00:00Z` is read from the store or the venue | the store's `candles(start, end)` skips a month file whose first instant is at or after `end` (`historical.py` `_stream`, `first_ms >= end_ms`), and the venue request ends at `2023-12-31T23:59:59.999Z` | the store's `coverage()` is NOT used, because it reads every month; the manifest listing above printed 2017 to 2023 rows only, and no `IRREGULAR.jsonl` line after 2017-12 was printed |
| anything computes a return, P&L, equity or metric | the aggregation and the comparison | none: bars, minute counts and equality only |

### What the store holds, from its manifests (read-only, counts and times only)

Both pairs have a 1m series from `2017-08-17T04:00:00Z` (`first_open_time_ms` `1502942400000`) in 110 monthly files to 2026-09. Over the months before 2024-01, `MANIFEST.jsonl`'s `rows` against the grid of minutes gives **30164 missing minutes for BTCUSDT and 30165 for ETHUSDT, in 25 months each**, and the shortfall is the same month by month but for one minute in 2020-12. Two months dominate: **2017-12 is short by 20477 minutes (14.2 days) and 2018-02 by 3260 (2.3 days)**; the other 23 months are short by between 60 and 705 minutes. The same arithmetic gives 3321916 stored 1m rows for BTCUSDT before 2024 and 3321915 for ETHUSDT. The grid has `2328` UTC days from 2017-08-17 to 2023-12-31, so `13968` 4h boundaries from 2017-08-17 `00:00`; the first stored minute is `04:00`, so the first 4h bucket (`00:00`) has no stored minute at all and the first 1d bucket has 240 of 1440.

### Definitions used by the predictions

A bucket is **complete** when all of its minutes (1440 for 1d, 240 for 4h) are stored, **incomplete** when between one and all-but-one are, and **absent** when none is stored; the aggregator emits complete and incomplete buckets and never an absent one. A venue bar with no emitted bucket is **venue-only**, an emitted bucket with no venue bar **aggregator-only**. Equality is `Decimal` equality of open, high, low, close and base volume.

### The predictions

| | Prediction |
|---|---|
| a | **Every complete bucket equals the venue's bar in open, high, low, close and base volume: zero mismatches among complete buckets**, for both pairs and both timeframes. REASONED: the venue builds a 4h or 1d bar from the same trades as its 1m bars, the open is the first 1m open, the close the last 1m close, and the volume is a sum of 8-decimal figures, exact in `Decimal`. What would falsify it: a venue revision of old bars that the archive does not carry, or the store's normalisation of its registered rows (BTCUSDT's `IRREGULAR.jsonl` holds 21618 lines of registered or quarantined rows, the first two of them `one_ms_late`) changing a bucket's first open |
| b | **Every mismatch lies in a bucket with fewer than all its minutes stored** (incomplete, or venue-only where none is stored). Not predicted either way: whether an incomplete bucket mismatches. The lean is that **most incomplete buckets still equal the venue's**, because a minute the exchange did not trade in (or was down for) is also absent from its 4h and 1d bar, so the aggregate of the stored minutes is the venue's bar; the exceptions would be buckets whose missing minutes the venue's longer bars do include. UNMEASURED |
| c | **Counts per pair, for the stop to score** (the manifest gives missing minutes and not their positions, so these are estimates from outage lengths): BTCUSDT 1d **about 33 incomplete** (range 25 to 45) and **about 14 absent** (11 to 20); BTCUSDT 4h **about 50 incomplete** (35 to 70) and **about 105 absent** (90 to 130). ETHUSDT within 3 of BTCUSDT in each. The incomplete count is the 1m outage edges and the 23 smaller outages; the absent count is nearly all inside 2017-12's 14.2-day hole (13 or 14 days, 85 or 86 4h buckets) and 2018-02's 2.3 days |
| c2 | **Venue-only buckets:** the lean (about 60%) is that the venue HAS klines across most of 2017-12's hole, because a 14-day exchange outage did not happen and a monthly archive file short by a round 14.2 days looks like the archive's gap and not the exchange's. If so the venue-only count is about 13 to 14 (1d) and 80 to 86 (4h) per pair, concentrated in 2017-12, and they are the bulk of the unpaired buckets. If instead the venue has none there, venue-only is 0. UNMEASURED either way, and it does not touch a, b or d |
| d | **Boundaries:** every venue open time is a multiple of `86400000` ms (1d) or `14400000` ms (4h), and every aggregated bucket opens on the same grid, so the UTC `00:00` boundary for 1d and `00, 04, 08, 12, 16, 20` for 4h hold; **off-grid open times: 0** on both sides |
| e | **Requests:** BTCUSDT and ETHUSDT each need 3 requests at `limit=1000` for 1d (2328 bars) and 14 for 4h (13968), **34 in all**; every one answers HTTP 200, none is rate-limited, none returns a bar with an open time at or after `1704067200000`, and the saved raw responses number 34 with a SHA-256 each. UNMEASURED for the host: it is `api.binance.com`, which the owner read keyless on 2026-10-24 (the `exchangeInfo` of section 3 of the charter), and a region block would answer 451 and halt the run |
| f | **The store is read only up to 2023-12:** the reader is called with `end = 2024-01-01T00:00:00Z`, and a test with a fake store asserts that no month at or after 2024-01 is opened. In the run, the months read are the 77 from 2017-08 to 2023-12 |
| g | The aggregation of about 3.32 million 1m bars per pair takes **under 15 minutes in all** (the store builds a validated `Candle` per row), and memory stays flat because the reader streams |
| h | The script prints counts and a capped mismatch list only: buckets compared, equal, mismatched by field, incomplete, absent-venue, aggregator-only and venue-only per pair and timeframe, and at most 50 mismatch rows with their values. It prints no price or volume outside that list |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. A code or test commit passes the full bare gate before it is made (R-DQ clause 2). Predictions for the mutation survey of the new tests are written after the tests exist and committed before the survey runs, as at section 73.

## 75. M5n N2a: the run of scripts/n2_verify_bars.py, the scoring of section 74, and what the mismatches are (P140 C7, R-T)

An observation log, so this section only adds. The script ran once, from the development tree's venv, on branch `m5n` at `9061a1c` (`scripts/n2_verify_bars.py` SHA-256 `2ab94ea4647079a8879f401c7f2593d2583a85c15b93369fc9a08c0a4d57105b`, `src/trading_bot/data/aggregation.py` `096d5abd7d907dc426f11996b82be98f113e4a06b47144dae6a364f9ce2f5d7b`), with `--out "F:\trading bot\scratch\p140\n2_responses"`, from `2026-10-24T10:12:44Z` (the time before the launch) to a finish before `10:14:54Z`: **exit 0, about two minutes, 34 requests, none refused, none rate-limited, no response holding a bar at or after `2024-01-01`** (the script would have stopped with an error). The venue was `https://api.binance.com/api/v3/klines` only, keyless. Nothing was written under `deploy\45547f107715`, the rehearsal clone or the store. The result file is `n2_result.txt`, SHA-256 `55cc0907266c4d9d21583263a280fa85375643d7d2b305404942d51891ab6d6e`; the 34 raw responses are in `n2_responses` with their digests in `responses.sha256`, SHA-256 `c3d099e59f77ef74c96b03179cba0d00050f0099792f92fa4e353d8c28de93fb`. **No return, P&L, equity or metric was computed.**

### The counts the script printed (venue bars are the venue's own, aggregated buckets are those with at least one stored minute)

| Series | Requests | Venue | Aggregated (complete / incomplete) | Compared | Equal | Mismatched | Mismatched in a complete bucket | Mismatched in an incomplete bucket | Incomplete that still equal | Venue-only | Aggregator-only | Off-grid venue |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1d | 3 | 2328 | 2314 (2280 / 34) | 2314 | 2237 | 77 | **73** | 4 | 30 | 14 | 0 | 0 |
| BTCUSDT 4h | 14 | 13951 | 13861 (13812 / 49) | 13861 | 13713 | 148 | **143** | 5 | 44 | 90 | 0 | 0 |
| ETHUSDT 1d | 3 | 2328 | 2314 (2280 / 34) | 2314 | 2220 | 94 | **90** | 4 | 30 | 14 | 0 | 0 |
| ETHUSDT 4h | 14 | 13951 | 13861 (13812 / 49) | 13861 | 13674 | 187 | **181** | 6 | 43 | 90 | 0 | 0 |

Mismatched buckets by field (a bucket can differ in several): BTCUSDT 1d open 29, high 0, low 2, close 1, volume 50; BTCUSDT 4h open 95, high 3, low 6, close 2, volume 55; ETHUSDT 1d open 46, high 1, low 2, close 1, volume 50; ETHUSDT 4h open 135, high 10, low 14, close 2, volume 54. The mismatch list held 558 rows and the first 50 were printed, all of them BTCUSDT 1d (the list runs by series and then by time), so the rest of it is in the saved result only by count. Venue-only runs, both pairs: 1d **2017-12-05 to 2017-12-17 (13 days)** and **2018-02-09 (1 day)**; 4h **2017-09-06 16:00 (1 bucket)**, **2017-12-04 08:00 to 2017-12-18 04:00 (84 buckets)** and **2018-02-09 08:00 to 2018-02-10 00:00 (5 buckets)**. The venue has no 4h bar for 17 of the 13968 grid slots (the first, `2017-08-17 00:00`, and 16 more) and none of those has an aggregated bucket either; it has a 1d bar for all 2328 days.

### Section 74's predictions, scored

| | Prediction | Result |
|---|---|---|
| a | Every complete bucket equals the venue's bar in all five fields | **FALSE.** 73 of 2280 complete BTCUSDT 1d buckets (3.2%), 143 of 13812 4h (1.0%), 90 of 2280 ETHUSDT 1d (3.9%) and 181 of 13812 4h (1.3%) differ. Diagnosed below |
| b | Every mismatch lies in a bucket with missing minutes | **FALSE** for the same buckets: 487 of the 506 mismatched buckets that were paired are complete. The lean that most incomplete buckets still equal the venue's **HELD**: 30 of 34 (BTCUSDT 1d), 44 of 49 (4h), 30 of 34 and 43 of 49 (ETHUSDT) |
| c | Incomplete about 33 (1d, range 25 to 45) and 50 (4h, 35 to 70) per pair; absent about 14 (11 to 20) and 105 (90 to 130); ETHUSDT within 3 of BTCUSDT | **HELD.** Incomplete 34 and 49 for both pairs; absent buckets (no stored minute) 14 (1d) and 106 (4h, 13967 less 13861, the first slot excluded); ETHUSDT equal to BTCUSDT |
| c2 | The venue has klines across most of 2017-12's hole (lean 60%): venue-only about 13 to 14 (1d) and 80 to 86 (4h) in 2017-12 | **HELD.** 13 days and 84 4h buckets, plus 2018-02-09 (1 day, 5 4h buckets) and one 4h bucket on 2017-09-06. The archive's hole is the archive's and not the exchange's |
| d | Boundaries: every venue open time and every bucket on the 00:00 (1d) and 00/04/08/12/16/20 (4h) grid | **HELD.** Off-grid venue open times 0; the aggregator is on the grid by construction (tested) |
| e | 34 requests, all HTTP 200, none at or after `1704067200000`, 34 saved responses with a SHA-256 each | **HELD.** 3 + 14 + 3 + 14; 34 responses and a 34-line digest list |
| f | The store is read only up to 2023-12 | **HELD by construction and not observed**: the script prints no month count; the end is passed to the store, which skips later month files (pinned by `test_no_month_file_at_or_after_end_is_opened`), and the diagnosis below passed the same end |
| g | Under 15 minutes in all | **HELD:** about two minutes |
| h | Counts and a capped mismatch list, no price outside it | **HELD** |

### What the mismatches are (read-only diagnosis, `scratch\p140\diagnose.py` SHA-256 `ee21477c82a02ba98ff99577c1f2c3f605c13d8e17538cbefd463971cfe8dbe4`, output `diagnose_out.txt` SHA-256 `dbe873c40b5806d813c24fe842c815ce2ea42198ed42760ddc2748881ca22c68`)

It re-read the saved responses and the store over the same window and counted, for the complete buckets only, how the differences relate to **zero-volume minutes**, which the store holds as filler bars (the module docstring of `historical.py`: the venue stores an empty minute as a bar with zero volume and zero trades). It printed counts and no price.

| Complete buckets | Open differs | ... of which the first minute has zero volume | Open differs with a traded first minute | High or low differs | ... with a zero-volume minute in the bucket | Volume differs | ... venue larger | ... venue smaller |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1d | 27 | 27 | **0** | 0 | | 46 | 46 | 0 |
| BTCUSDT 4h | 92 | 92 | **0** | 6 | 5 | 51 | 51 | 0 |
| ETHUSDT 1d | 44 | 44 | **0** | 0 | | 46 | 46 | 0 |
| ETHUSDT 4h | 131 | 131 | **0** | 19 | 19 | 50 | 50 | 0 |

**Every complete-bucket open mismatch is a bucket whose first minute traded nothing**, and none has a traded first minute. Where the first minute is a filler bar, the bucket's open is that filler's open (the previous close) in the aggregation and the first trade's price at the venue; of the complete buckets with a zero-volume first minute the open still differs in 27 of 32 (BTCUSDT 1d), 92 of 116 (4h), 44 of 51 and 131 of 160, and equals the venue's in the rest, where the filler's price happens to be the first traded one. Highs and lows differ in 6 and 19 4h buckets, 24 of 25 with a zero-volume minute inside, which fits a filler's price lying outside the traded range. **Volumes differ by the venue being larger in every case and smaller in none** (46, 51, 46 and 50 buckets), which a filler cannot explain and which fits trades that reached the venue's longer bars and not its 1m bars; only 2, 2, 3 and 3 of those buckets hold a zero-volume minute. REASONED for the mechanism, MEASURED for every count above; **the mechanism is not tested here**: no aggregation over traded minutes only was run.

### What follows, and what does not

1. **The aggregation as committed (C3) is not the venue's bar for about 1 to 4 percent of complete buckets**, and a candidate strategy built on it would differ from one built on the venue's bars exactly when the bucket opens on an untraded minute. This is N2's finding, not a defect in C3's tests: the module does what its docstring says.
2. **Two repairs are open and neither is made here.** An aggregation that takes the open, high and low over traded minutes only (and keeps the close and the minute counts) would, if the mechanism above is right, remove the open and most of the high and low differences; it needs its own predictions and tests. The volume difference has no repair on the 1m store: the venue's longer bars hold trades its 1m bars do not, always more and never less. The alternative is to take 4h and 1d bars from the store's own `4h` and `1d` archive series, which exist for both pairs; whether they equal the venue's was **not** measured here.
3. **The venue-only buckets are all in two archive holes** (2017-12 and 2018-02) and one 4h slot: a bar the venue has and the 1m archive cannot reproduce.
4. R-DT clause 3 was held: the run printed bar-verification counts; the diagnosis counted zero-volume minutes and the sign of a volume difference and computed no return or metric.

## 76. M5n N2a: the predictions for the mutation survey of the aggregation and verification tests, before it is run (P140 C8, R-T, R-DQ)

An observation log, so this section only adds. P140 proves that the 95 tests of C4 and C6 bite: 58 in `tests/unit/test_aggregation.py` against `src/trading_bot/data/aggregation.py`, and 37 in `tests/unit/test_n2_verify_bars.py` against `scripts/n2_verify_bars.py`. **This section is committed before the survey is run**, with the predicted kills of every mutation and the tests predicted to be killed by none. **Everything here decides nothing about S4 or about the choice section 75 leaves open.**

### The method

The P117 harness as P136 used it (`survey.py` SHA-256 `cd2eb339e4fdf65d361482cccf0511ee3fd28a495fd90815cd5b3b357ed3202a`, `p116_hook.py` `febedd0bf7a8fee6a9fe3ac2462975d917ee5e31f5e1daf2acb57f7d378e2a8d`): a detached worktree outside the repository, at the commit that carries this section, with the copied files shown SHA-256-equal; the import location of `trading_bot` and `tests` proven by a pytest session hook before any result counts; an unmutated baseline first, predicted green at **58 passed** for the aggregation file and **37 passed** for the script file; every mutation byte-exact, asserted to match exactly once, restored from an out-of-tree snapshot in a `finally` and shown SHA-equal; and the worktree removed afterwards. It is two runs, one spec per source file (`survey_a.json` `97872ba67521b728cafb79bbfa03c26051dfbd62c14b3f01d84624c3759f291a`, `survey_v.json` `70fba3e7ea4c8f217d794a81ea85b74b250e63268d93791b5873125050b6e139`, written by `make_spec.py` `9f1e032a9c68b97f8a3641117d9457d3dd728091601b643cb530b3de392eaf52` from the tables below), and **each run executes only the mutated file's own tests**. The tests of `test_n2_verify_bars.py` also pass through `aggregation.py`, so a mutation of the aggregator would fail some of them as well; that cross-file reach is **not** part of this survey and is not predicted.

A kill is a failure present under the mutation and absent at baseline, by the three exception types of `M5i-115`. A mutation that kills **more** than predicted is recorded (MORE); one that kills **fewer** halts the survey until each missing kill is explained (FEWER). The tests were read for expressiveness and for the assertion looking before the predictions were written, and the notes below say where a fixture cannot express a mutation.

### Totals

**30 mutations of the aggregation module with 170 predicted kills and 48 of the script with 78**, 78 mutations and 248 predicted kills in all. Seven mutations are predicted to be killed by **nothing**, and each is declared: **a01** is equivalent (an equal high is copied over an equal high, and tests compare by value); **v05** (the response size cap), **v35** (a run list cut to one run, no test has more than one run), **v40** (the refusal exit status, the tests compare against the constant and never the literal 2) and **v45** (only a `VerifyError` caught by `main`; the one error-exit test raises a `VerifyError`) are **unpinned**, not equivalent; **v08** (the non-list check) is **inexpressible by its fixture**, since the one non-list body is a dict that the next check refuses anyway; and **v17** (`<` for `<=` on an equal open time) is unpinned, since the only out-of-order fixture runs backwards.

**Tests predicted to be killed by no mutation:** in the aggregation file **3** of 58: `TestTheValues::test_empty_input_gives_no_bars` (no mutation touches the empty stream), and the `1w` and empty-string cases of `test_a_timeframe_other_than_4h_and_1d_is_refused` (refused by any membership test, so the one mutation that widens it lets them through unkilled). In the script file **4** of 37: `TestTheRequests::test_the_only_url_is_the_klines_endpoint_with_five_parameters_and_no_key` (the set of query keys is not changed by any mutation in the table, only their values), the `{"code": -1}` case of `test_a_response_that_is_not_klines_is_an_error` (a dict body fails the row check even when the list check is removed), `TestEvidenceIsKept::test_the_digest_list_is_written_even_when_a_later_request_fails` (no mutation breaks the `finally`) and `TestRefusals::test_a_new_or_empty_out_directory_is_accepted` (no mutation makes a fresh directory refused).

**Where a prediction is most likely to be wrong, named in advance:** a10 (every minute its own bucket) and a12 (the last bucket never flushed) have the largest predicted sets, 26 and 38, and each is a count of tests that reach the mutated line; v19 (the venue's bars never kept) reaches 13 and excludes D5, which passes by accident because zero compared buckets also means zero mismatches; v31 is predicted to be killed by W1 alone because U4's fixture makes the on-grid count equal the off-grid count by coincidence (one venue bar of each).

The codes in the tables are keyed to test ids at the end of the section.

### Predicted kills, `src/trading_bot/data/aggregation.py` against `tests/unit/test_aggregation.py`

| Mutation | The break | Predicted kills (tests/unit/test_aggregation.py) |
|---|---|---|
| a01 | a new high replaces the old on >= (an equal high is copied) | none |
| a02 | the high keeps the LOWEST high | V1, V2, V5, P3 |
| a03 | the low keeps the HIGHEST low | V1, V2, V5, P4 |
| a04 | the close is never updated, so it stays the first minute's | V1, V2, V5, P1, P3, P7, S1 |
| a05 | the volume is the last minute's and not the sum | V1, V3, V5, P1, S2 |
| a06 | the present count is never incremented | V1, V5, P1, P2, P3, P5, P6, S1, S2 |
| a07 | minutes_missing is the present count | V1, V5, P1, P2, P3, P5, P6, S1, S2 |
| a08 | close_time is the next bucket's first millisecond | Gclose[4h], Gclose[1d] |
| a09 | open_time is one millisecond late | G4h[0-0-0], G4h[3-59-0], G4h[4-0-4], G4h[7-59-4], G4h[8-0-8], G4h[11-59-8], G4h[12-0-12], G4h[15-59-12], G4h[16-0-16], G4h[19-59-16], G4h[20-0-20], G4h[23-59-20], G1dmid, G1dmin, P5, P6, P8, S1, S4, S6 |
| a10 | every minute is its own bucket (grid of one minute) | G4h[3-59-0], G4h[7-59-4], G4h[11-59-8], G4h[15-59-12], G4h[19-59-16], G4h[23-59-20], G1dmid, G1dmin, Gclose[4h], Gclose[1d], V1, V2, V3, V5, P1, P2, P3, P4, P5, P6, P7, P8, S1, S2, S4, S6 |
| a11 | a later bucket is folded into the current one (<= for ==) | G1dmid, V5, P6, P7, P8, S1, S2 |
| a12 | the last bucket is never flushed | G4h[0-0-0], G4h[3-59-0], G4h[4-0-4], G4h[7-59-4], G4h[8-0-8], G4h[11-59-8], G4h[12-0-12], G4h[15-59-12], G4h[16-0-16], G4h[19-59-16], G4h[20-0-20], G4h[23-59-20], G1dmid, G1dmin, Gclose[4h], Gclose[1d], V1, V2, V3, V4, V5, P1, P2, P3, P4, P5, P6, P7, P8, B[4h-BTCUSDT], B[4h-ETHUSDT], B[1d-BTCUSDT], B[1d-ETHUSDT], S1, S2, S3, S4, S6 |
| a13 | a candle that is not 1m is accepted | I1 |
| a14 | a second symbol is accepted | B2 |
| a15 | an open off the minute grid is accepted | I4 |
| a16 | a repeated minute is accepted (< for <=) | I3 |
| a17 | the ordering check is removed | I2, I3 |
| a18 | any stored interval is an aggregated timeframe | I5[1m], I5[5m], I5[1h], S8 |
| a19 | a naive instant is not refused by the aggregator | S7 |
| a20 | the grid check on start and end is removed | S5[0], S5[1], S5[2], S7 |
| a21 | the store is asked for an empty range | S1, S2, S3, S4, S6 |
| a22 | the store is asked for 40 days beyond end | S4 |
| a23 | the store is always asked for BTCUSDT | S3 |
| a24 | the bar is not frozen | T2 |
| a25 | the open is not a Money field | T1 |
| a26 | complete is true for one missing minute (<= 1) | T3, P1 |
| a27 | the bucket's open is its first minute's close | V1, V2, P1, P2, P7 |
| a28 | the bar's symbol is always BTCUSDT | B[4h-ETHUSDT], B[1d-ETHUSDT], S3 |
| a29 | the bar's timeframe is always 4h | B[1d-BTCUSDT], B[1d-ETHUSDT] |
| a30 | 1h is an aggregated timeframe | Gtf, I5[1h], S8 |

### Predicted kills, `scripts/n2_verify_bars.py` against `tests/unit/test_n2_verify_bars.py`

| Mutation | The break | Predicted kills (tests/unit/test_n2_verify_bars.py) |
|---|---|---|
| v01 | any https URL is accepted | F1 |
| v02 | a key header is sent | F2 |
| v03 | an HTTP error returns an empty page | F3 |
| v04 | a transport failure returns an empty page | F4 |
| v05 | the response size cap is removed | none |
| v06 | endTime is one millisecond past the window | R2 |
| v07 | the page limit is always 1000 | R3, R4 |
| v08 | a non-list response is not refused at its own check | none |
| v09 | a short kline row is not refused at its own check | R7[[[1, 2]]] |
| v10 | a non-integer open time is not refused | R7[[["x", "1", "1", "1", "1", "1"]]] |
| v11 | a figure that is not a decimal escapes as InvalidOperation | R8 |
| v12 | a body that is not JSON escapes as a JSON error | R7[not json] |
| v13 | the next page starts at the last open and not after it | R3, R4, E1 |
| v14 | a short page does not end the series | R4, P-1 |
| v15 | the pause is taken before every request | R4 |
| v16 | a bar at or after the window end is accepted | R5 |
| v17 | an equal open time is accepted (< for <=) | none |
| v18 | the ordering check is removed | R6 |
| v19 | the venue's bars are never kept | W1, W2, D1, D2, D3, D4, U1, U2, U4, R3, P-1, P-2, P-3 |
| v20 | the pairing iterates the aggregator's buckets | U2, P-2 |
| v21 | compared counts two per pair | W1, W2, D1, U1, U2 |
| v22 | figures are compared as strings | D5 |
| v23 | incomplete_equal counts the complete ones | D4 |
| v24 | complete and incomplete mismatches are swapped | D1, D3 |
| v25 | a field is counted twice | D1, D2, D3 |
| v26 | a mismatch row carries 0 minutes missing | D3 |
| v27 | a mismatch row has the two values swapped | D1, D3 |
| v28 | complete counts the incomplete buckets | W1, D3, D4 |
| v29 | the aggregator-only runs are built from the venue-only buckets | U2 |
| v30 | the venue-only runs are built from the aggregator-only buckets | U1, P-3 |
| v31 | off-grid counts the on-grid venue opens | W1 |
| v32 | a run joins only buckets two widths apart | U3, P-3 |
| v33 | a run counts two per bucket after the first | U3, P-3 |
| v34 | the mismatch list prints 51 rows | P-2 |
| v35 | a run list is cut to one run | none |
| v36 | a timestamp has a space for the T | P-3 |
| v37 | an out directory under logs is accepted | X1 |
| v38 | an out directory inside the store is accepted | X2 |
| v39 | an out directory that holds files is accepted | X3, X5 |
| v40 | the refusal exit status is 3 | none |
| v41 | the digest list holds the SHA-256 of the name | E1 |
| v42 | a raw response is not written | E1 |
| v43 | main always writes to stdout | X5, P-1, P-2, P-3, P-4 |
| v44 | a fetch error exits 0 | P-4 |
| v45 | only a VerifyError is caught by main | none |
| v46 | the window starts a day late | R2 |
| v47 | the window ends a day late | R2, R5 |
| v48 | the timeframes run 4h before 1d | W2 |

### The test key (every code the tables use)

| Code | Test |
|---|---|
| B2 | `TestBothPairs::test_two_symbols_in_one_stream_are_refused` |
| B[1d-BTCUSDT] | `TestBothPairs::test_the_symbol_and_timeframe_are_carried_onto_the_bar[1d-BTCUSDT]` |
| B[1d-ETHUSDT] | `TestBothPairs::test_the_symbol_and_timeframe_are_carried_onto_the_bar[1d-ETHUSDT]` |
| B[4h-BTCUSDT] | `TestBothPairs::test_the_symbol_and_timeframe_are_carried_onto_the_bar[4h-BTCUSDT]` |
| B[4h-ETHUSDT] | `TestBothPairs::test_the_symbol_and_timeframe_are_carried_onto_the_bar[4h-ETHUSDT]` |
| D1 | `TestADifferenceIsCountedByFieldAndByCompleteness::test_a_wrong_high_in_a_complete_bucket_is_a_complete_mismatch` |
| D2 | `TestADifferenceIsCountedByFieldAndByCompleteness::test_two_wrong_fields_in_one_bucket_are_one_mismatched_bucket_and_two_field_counts` |
| D3 | `TestADifferenceIsCountedByFieldAndByCompleteness::test_a_missing_minute_that_changes_the_volume_is_an_incomplete_mismatch` |
| D4 | `TestADifferenceIsCountedByFieldAndByCompleteness::test_an_incomplete_bucket_that_still_equals_the_venue_is_counted_as_such` |
| D5 | `TestADifferenceIsCountedByFieldAndByCompleteness::test_figures_are_compared_as_decimals_not_as_strings` |
| E1 | `TestEvidenceIsKept::test_every_raw_response_is_saved_with_its_sha256` |
| F1 | `TestFetchUrl::test_a_url_outside_the_klines_endpoint_is_refused_before_any_request` |
| F2 | `TestFetchUrl::test_the_request_carries_no_key_and_no_header_but_a_user_agent` |
| F3 | `TestFetchUrl::test_a_rate_limit_is_an_error_and_not_retried` |
| F4 | `TestFetchUrl::test_a_transport_failure_is_an_error` |
| G1dmid | `TestTheGrid::test_the_minute_before_midnight_and_the_midnight_minute_are_two_1d_buckets` |
| G1dmin | `TestTheGrid::test_a_1d_bucket_opens_at_00_utc_whatever_the_minute_inside_it` |
| G4h[0-0-0] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[0-0-0]` |
| G4h[11-59-8] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[11-59-8]` |
| G4h[12-0-12] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[12-0-12]` |
| G4h[15-59-12] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[15-59-12]` |
| G4h[16-0-16] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[16-0-16]` |
| G4h[19-59-16] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[19-59-16]` |
| G4h[20-0-20] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[20-0-20]` |
| G4h[23-59-20] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[23-59-20]` |
| G4h[3-59-0] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[3-59-0]` |
| G4h[4-0-4] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[4-0-4]` |
| G4h[7-59-4] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[7-59-4]` |
| G4h[8-0-8] | `TestTheGrid::test_a_4h_bucket_opens_on_00_04_08_12_16_or_20_utc[8-0-8]` |
| Gclose[1d] | `TestTheGrid::test_close_time_is_the_last_millisecond_of_the_bucket[1d-closes1]` |
| Gclose[4h] | `TestTheGrid::test_close_time_is_the_last_millisecond_of_the_bucket[4h-closes0]` |
| Gtf | `TestTheGrid::test_only_4h_and_1d_are_aggregated` |
| I1 | `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_candle_that_is_not_a_1m_bar_is_refused` |
| I2 | `TestInputThatCannotBeAggregatedWithoutGuessing::test_open_times_must_increase` |
| I3 | `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_repeated_minute_is_refused_not_added_twice` |
| I4 | `TestInputThatCannotBeAggregatedWithoutGuessing::test_an_open_time_off_the_minute_is_refused` |
| I5[1h] | `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[1h]` |
| I5[1m] | `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[1m]` |
| I5[5m] | `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[5m]` |
| P-1 | `TestWhatIsPrinted::test_a_clean_run_prints_counts_and_no_price_or_volume` |
| P-2 | `TestWhatIsPrinted::test_the_mismatch_list_is_capped_at_fifty_rows` |
| P-3 | `TestWhatIsPrinted::test_runs_of_unpaired_buckets_are_printed_with_their_times_and_count` |
| P-4 | `TestWhatIsPrinted::test_a_fetch_error_is_an_error_exit_and_prints_no_result` |
| P1 | `TestGapsAreReportedAndNeverFilled::test_one_missing_interior_minute_is_counted_and_the_bucket_is_incomplete` |
| P2 | `TestGapsAreReportedAndNeverFilled::test_a_missing_first_minute_makes_the_second_minute_the_open` |
| P3 | `TestGapsAreReportedAndNeverFilled::test_a_missing_last_minute_makes_the_one_before_the_close` |
| P4 | `TestGapsAreReportedAndNeverFilled::test_the_missing_minute_that_held_the_extreme_is_not_replaced` |
| P5 | `TestGapsAreReportedAndNeverFilled::test_a_stream_that_starts_mid_day_has_a_first_day_missing_the_earlier_minutes` |
| P6 | `TestGapsAreReportedAndNeverFilled::test_a_bucket_with_no_stored_minute_is_not_emitted_and_nothing_stands_in_for_it` |
| P7 | `TestGapsAreReportedAndNeverFilled::test_the_bar_after_a_gap_starts_from_its_own_first_minute` |
| P8 | `TestGapsAreReportedAndNeverFilled::test_a_whole_missing_day_inside_a_run_of_days_gives_no_bar_for_it` |
| R2 | `TestTheRequests::test_the_first_request_starts_at_2017_08_17_and_every_one_ends_before_2024` |
| R3 | `TestTheRequests::test_a_page_full_to_the_limit_is_followed_by_the_next_from_the_last_open` |
| R4 | `TestTheRequests::test_requests_are_paced_by_the_pause_and_not_before_the_first` |
| R5 | `TestTheRequests::test_a_bar_at_or_after_the_window_end_is_an_error_not_a_row` |
| R6 | `TestTheRequests::test_open_times_that_do_not_increase_are_an_error` |
| R7[[["x", "1", "1", "1", "1", "1"]]] | `TestTheRequests::test_a_response_that_is_not_klines_is_an_error[[["x", "1", "1", "1", "1", "1"]]]` |
| R7[[[1, 2]]] | `TestTheRequests::test_a_response_that_is_not_klines_is_an_error[[[1, 2]]]` |
| R7[not json] | `TestTheRequests::test_a_response_that_is_not_klines_is_an_error[not json]` |
| R8 | `TestTheRequests::test_a_figure_that_is_not_a_decimal_is_an_error` |
| S1 | `TestAgainstARealStore::test_a_month_file_boundary_ends_one_bucket_and_starts_the_next` |
| S2 | `TestAgainstARealStore::test_a_whole_day_in_a_month_file_is_one_complete_1d_bar_and_six_4h_bars` |
| S3 | `TestAgainstARealStore::test_the_symbol_is_the_one_asked_for` |
| S4 | `TestAgainstARealStore::test_no_month_file_at_or_after_end_is_opened` |
| S5[0] | `TestAgainstARealStore::test_a_range_off_the_1d_grid_is_refused_at_the_call[start0-end0]` |
| S5[1] | `TestAgainstARealStore::test_a_range_off_the_1d_grid_is_refused_at_the_call[start1-end1]` |
| S5[2] | `TestAgainstARealStore::test_a_range_off_the_1d_grid_is_refused_at_the_call[start2-end2]` |
| S6 | `TestAgainstARealStore::test_a_range_on_the_4h_grid_but_not_the_1d_grid_is_accepted_for_4h` |
| S7 | `TestAgainstARealStore::test_a_naive_start_or_end_is_refused_at_the_call` |
| S8 | `TestAgainstARealStore::test_an_unaggregated_timeframe_is_refused_at_the_call` |
| T1 | `TestTheBarType::test_a_float_figure_is_refused` |
| T2 | `TestTheBarType::test_the_bar_is_frozen` |
| T3 | `TestTheBarType::test_complete_follows_the_missing_count` |
| U1 | `TestBucketsOnlyOneSideHas::test_a_venue_bar_with_no_stored_minute_is_venue_only` |
| U2 | `TestBucketsOnlyOneSideHas::test_a_stored_bucket_the_venue_lacks_is_aggregator_only` |
| U3 | `TestBucketsOnlyOneSideHas::test_consecutive_unpaired_buckets_are_one_run_and_a_break_starts_another` |
| U4 | `TestBucketsOnlyOneSideHas::test_a_venue_open_off_the_grid_is_counted` |
| V1 | `TestTheValues::test_a_full_4h_bucket_has_the_first_open_the_last_close_the_extremes_and_the_sum` |
| V2 | `TestTheValues::test_open_and_close_are_the_first_and_last_minute_not_the_extremes` |
| V3 | `TestTheValues::test_a_volume_is_an_exact_decimal_sum` |
| V4 | `TestTheValues::test_every_figure_is_a_decimal` |
| V5 | `TestTheValues::test_a_day_equals_the_fold_of_its_six_4h_buckets` |
| W1 | `TestAWholeDayThatAgrees::test_every_bucket_is_complete_and_equal` |
| W2 | `TestAWholeDayThatAgrees::test_both_pairs_and_both_timeframes_are_run_in_order` |
| X1 | `TestRefusals::test_an_out_directory_under_logs_is_refused` |
| X2 | `TestRefusals::test_an_out_directory_inside_the_store_is_refused` |
| X3 | `TestRefusals::test_an_out_directory_that_already_holds_files_is_refused` |
| X5 | `TestRefusals::test_a_second_run_into_the_same_directory_is_refused_and_overwrites_nothing` |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. The survey runs on the tree that carries this section, and its results are appended as section 77. The order of this prompt's remaining commits: this section; the survey and its results; the counts and the lists the new files falsify (`CLAUDE.md` and `README.md`), each with the gate figures of a fresh gate run.

## 77. M5n N2a: the mutation survey of the aggregation and verification tests, scored against section 76 (P140 C9, R-T)

An observation log, so this section only adds. The survey ran as section 76 describes, in two detached worktrees outside the repository at `62ebd00` (the commit that carries section 76), one per source file, each running only that file's own tests; the baselines were green (`58 passed in 1.11s; failing: []` and `37 passed in 2.03s; failing: []`), the import location of `trading_bot` and `tests` was proven inside each worktree before any result counted, every restore was shown SHA-equal and each run ended with *all copied files are intact*. The outputs are `survey_a_out.txt` SHA-256 `b5460d95d381c2261d675006722762f537b19027327695e71ba27bf96bf9e3f0` and `survey_v_out.txt` SHA-256 `047d72ac99ca0fa39e0afb9ca004b92688e0df2c24ed67a573524b6940b102f3`.

### The totals

| | Mutations | MATCH | MORE | FEWER | Predicted kills | Observed kills |
|---|---|---|---|---|---|---|
| `aggregation.py` | 30 | 30 | 0 | 0 | 170 | 170 |
| `n2_verify_bars.py` | 48 | 47 | 1 | 0 | 78 | 79 |
| both | 78 | 77 | 1 | 0 | 248 | 249 |

### Every mutation, predicted and observed

| Mutation | Predicted | Killed | Verdict |
|---|---|---|---|
| a01 | 0 | 0 | MATCH |
| a02 | 4 | 4 | MATCH |
| a03 | 4 | 4 | MATCH |
| a04 | 7 | 7 | MATCH |
| a05 | 5 | 5 | MATCH |
| a06 | 9 | 9 | MATCH |
| a07 | 9 | 9 | MATCH |
| a08 | 2 | 2 | MATCH |
| a09 | 20 | 20 | MATCH |
| a10 | 26 | 26 | MATCH |
| a11 | 7 | 7 | MATCH |
| a12 | 38 | 38 | MATCH |
| a13 | 1 | 1 | MATCH |
| a14 | 1 | 1 | MATCH |
| a15 | 1 | 1 | MATCH |
| a16 | 1 | 1 | MATCH |
| a17 | 2 | 2 | MATCH |
| a18 | 4 | 4 | MATCH |
| a19 | 1 | 1 | MATCH |
| a20 | 4 | 4 | MATCH |
| a21 | 5 | 5 | MATCH |
| a22 | 1 | 1 | MATCH |
| a23 | 1 | 1 | MATCH |
| a24 | 1 | 1 | MATCH |
| a25 | 1 | 1 | MATCH |
| a26 | 2 | 2 | MATCH |
| a27 | 5 | 5 | MATCH |
| a28 | 3 | 3 | MATCH |
| a29 | 2 | 2 | MATCH |
| a30 | 3 | 3 | MATCH |
| v01 | 1 | 1 | MATCH |
| v02 | 1 | 1 | MATCH |
| v03 | 1 | 1 | MATCH |
| v04 | 1 | 1 | MATCH |
| v05 | 0 | 0 | MATCH |
| v06 | 1 | 1 | MATCH |
| v07 | 2 | 2 | MATCH |
| v08 | 0 | 0 | MATCH |
| v09 | 1 | 1 | MATCH |
| v10 | 1 | 1 | MATCH |
| v11 | 1 | 1 | MATCH |
| v12 | 1 | 1 | MATCH |
| v13 | 3 | 3 | MATCH |
| v14 | 2 | 2 | MATCH |
| v15 | 1 | 1 | MATCH |
| v16 | 1 | 1 | MATCH |
| v17 | 0 | 0 | MATCH |
| v18 | 1 | 1 | MATCH |
| v19 | 13 | 13 | MATCH |
| v20 | 2 | 2 | MATCH |
| v21 | 5 | 5 | MATCH |
| v22 | 1 | 1 | MATCH |
| v23 | 1 | 1 | MATCH |
| v24 | 2 | 2 | MATCH |
| v25 | 3 | 3 | MATCH |
| v26 | 1 | 1 | MATCH |
| v27 | 2 | 2 | MATCH |
| v28 | 3 | 3 | MATCH |
| v29 | 1 | 1 | MATCH |
| v30 | 2 | 2 | MATCH |
| v31 | 1 | 1 | MATCH |
| v32 | 2 | 2 | MATCH |
| v33 | 2 | 2 | MATCH |
| v34 | 1 | 1 | MATCH |
| v35 | 0 | 0 | MATCH |
| v36 | 1 | 1 | MATCH |
| v37 | 1 | 1 | MATCH |
| v38 | 1 | 1 | MATCH |
| v39 | 2 | 2 | MATCH |
| v40 | 0 | 0 | MATCH |
| v41 | 1 | 1 | MATCH |
| v42 | 1 | 1 | MATCH |
| v43 | 5 | 5 | MATCH |
| v44 | 1 | 1 | MATCH |
| v45 | 0 | 0 | MATCH |
| v46 | 1 | 2 | MORE |
| v47 | 2 | 2 | MATCH |
| v48 | 1 | 1 | MATCH |

### Where the survey and the prediction differ

- **v46** killed beyond the prediction: `TestTheRequests::test_a_page_full_to_the_limit_is_followed_by_the_next_from_the_last_open`

**The one MORE, diagnosed (a reach error, recorded and not a violation).** v46 (the window starting a day late) was predicted to be killed by R2 alone and was killed by R3 as well. R3, `test_a_page_full_to_the_limit_is_followed_by_the_next_from_the_last_open`, asserts that the first 4h request starts at `WINDOW_START_MS` before it asserts the following ones, so it reads the constant the mutation moves; the prediction reasoned from what R3 is for (pagination) and not from what it reaches, the error `CLAUDE.md` names under *Reason from what a thing reaches*. The extra kill is real coverage. No mutation was killed by fewer tests than predicted and the survey did not halt.

### Tests killed by no mutation

`test_aggregation.py`: **3 of 58**: `TestTheValues::test_empty_input_gives_no_bars`; `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[1w]`; `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[]`

`test_n2_verify_bars.py`: **4 of 37**: `TestTheRequests::test_the_only_url_is_the_klines_endpoint_with_five_parameters_and_no_key`; `TestTheRequests::test_a_response_that_is_not_klines_is_an_error[{"code": -1}]`; `TestEvidenceIsKept::test_the_digest_list_is_written_even_when_a_later_request_fails`; `TestRefusals::test_a_new_or_empty_out_directory_is_accepted`

Section 76 predicted 3 and 4. The scripts that made these results are in `scratch\p140`: `make_spec.py`, `build77.py` (this text).

## 78. M5n N2b: P141's halts and the predictions for the archive 4h and 1d series, the traded-minute consistency mode and the volume gap, before any code (P141 C2, R-T, R-DQ, R-DT)

An observation log, so this section only adds. P141 follows R-DV (`docs/M5N_CHARTER_DRAFT.md` section 14): the decision bars are the venue's native 4h and 1d klines as held in the canonical store's archive series, checked against P140's saved API responses; the aggregation from the 1m store is kept as a consistency check under a traded-minute rule. Under R-DQ clause (1) this section is committed BEFORE any code or test is drafted. The only reading done first was of the source (`src/trading_bot/data/historical.py`, `src/trading_bot/data/aggregation.py`, `scripts/n2_verify_bars.py`) and of the `MANIFEST.jsonl` files (row counts and times, no bar value). **Everything here decides nothing about S4, and no return, P&L, equity or metric is computed.**

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| not on `m5n`, `git status` not clean, HEAD is not `2882fae` | `git branch --show-current`, `git status --porcelain`, `git rev-parse --short HEAD` | `m5n`, empty, `2882fae` (then `e14ce80` after C1, the charter commit) |
| a command would write under `deploy\45547f107715`, the rehearsal clone or the canonical store | every command in the plan | none: the store is opened by `HistoricalStore`, which only reads; output goes to scratch |
| any venue request | the plan | none: the check reads P140's saved responses by digest (`scratch\p140\n2_responses`, `responses.sha256` SHA-256 `c3d099e59f77ef74c96b03179cba0d00050f0099792f92fa4e353d8c28de93fb`) and has no fetcher |
| any bar at or after `2024-01-01T00:00:00Z` read | the reader is called with `end = 2024-01-01T00:00:00Z`, and the store opens no month file beginning at or after it | no bar was read; the manifests (metadata, no bar value) were parsed whole and the lines of 2024-01 and later were discarded unused |
| the canonical store holds no archive 4h or 1d series for a pair | `data/historical/<pair>/4h` and `/1d` | **both series exist for both pairs**, 110 month files each from 2017-08 to 2026-09 |
| anything computes a return, P&L, equity or metric | the plan | none: bars, minute counts, equality and bands of a volume difference only |

### What the archive series hold, from their manifests (counts and times only)

For months before 2024-01, `MANIFEST.jsonl` gives **2328 rows for the 1d series of each pair** (from `2017-08-17T00:00:00Z`, so every UTC day) and **13950 rows for the 4h series of each pair** (from `2017-08-17T04:00:00Z`), with 0 quarantined rows in either, 0 registered rows in the 1d series and 19 registered (kept verbatim, with a close time that is not the regular one) in each 4h series. P140's API responses held 2328 1d bars and **13951** 4h bars per pair, so the 4h archive holds **one fewer** than the API.

**The store's 1m rows carry no trade count.** `Row` in `historical.py` has seven fields (`open_time_ms`, `open`, `high`, `low`, `close`, `volume`, `close_time_ms`) and the stored CSV header is `open_time_ms,open,high,low,close,volume,close_time_ms`; the archive's number-of-trades column is read at ingest and not kept. So R-DV's fallback applies: **a traded minute is a minute with nonzero volume.**

### The predictions

| | Prediction |
|---|---|
| a | **The archive 1d series equals P140's API 1d responses in open, high, low, close and base volume for every one of the 2328 buckets of each pair** (0 mismatches, 0 archive-only, 0 API-only). REASONED, lean about 65%: both come from the venue's own longer bars, and P140's volume gap was between the venue's longer bars and the 1m rows. **The 4h series: 13950 archive buckets against 13951 API buckets per pair, so exactly one API-only bucket and no archive-only bucket**, the lean (60%) being that it is the slot `2017-09-06 16:00`, the one 4h slot P140 found the venue had and the 1m store did not; and 0 mismatches among the 13950 compared. If there are mismatches the lean is that they are in volume and in 2017 and 2018. UNMEASURED |
| b | **Under the traded-minute rule the aggregation's open, high, low and close equal the venue's for every complete bucket, with one expected exception.** P140's diagnosis found one complete bucket (BTCUSDT 4h) whose high or low differed with no zero-volume minute inside it, which no traded-minute rule can repair, so the prediction is: residual open, high, low or close mismatches among complete buckets **BTCUSDT 1d 0, 4h 1 (plus or minus 1); ETHUSDT 1d 0, 4h 0 (plus or minus 1); open mismatches 0 and close mismatches 0 everywhere.** Complete buckets with no traded minute at all (undefined under the rule): **0 expected, at most 3** per series. The 4h and 1d rows themselves are unaffected, the volume still being the sum of every stored minute. REASONED from P140's counts (24 of 25 complete 4h high or low mismatches had a zero-volume minute inside, and every open mismatch had a zero-volume first minute) |
| c | **Volume: the venue's is larger in the same complete buckets as P140 and smaller in none**, namely 46 (BTCUSDT 1d), 51 (4h), 46 (ETHUSDT 1d) and 50 (4h), against the venue's longer bars as the API and the archive both give them. Of those buckets the **median relative difference (venue minus aggregated, over the venue's) is about 0.002%** (range 0.0005% to 0.01%) and the **maximum about 1%** (range 0.5% to 3%), read from the dozen differences P140 printed (a few parts in a hundred thousand for most, 0.13% for one, 1.0% for 2018-03-04). The bands of step 5, per pair and timeframe, predicted for BTCUSDT 1d: **0: about 2234 of 2280 complete buckets; up to 0.01%: about 30; up to 0.1%: about 12; up to 1%: about 3; over 1%: 1 (or 2)**; the other three series within a factor of two of that shape, with 4h holding more of its count in the first band. UNMEASURED |
| d | **The store's 1m rows carry no trade count** (seven fields, no trades column), so the traded minute is a minute with nonzero volume. **PREDICTED TRUE, from the schema, and not in doubt.** The consistency mode is therefore keyed on volume, and a bucket whose minutes all have zero volume has no open, high, low or close under the rule |
| e | The checks and the consistency run read the saved responses and the store only: **no request is made** (there is no fetcher in the script), every one of the 34 saved responses matches its line in `responses.sha256` (a mismatch refuses the run), and the whole run takes **under 10 minutes** |
| f | The output is counts and two capped lists (at most 50 archive-against-API mismatch rows, and the buckets that fail the consistency check, capped likewise); the volume bands carry no price |

### What is built, and in what order

An addition to `src/trading_bot/data/aggregation.py` (a traded-minute aggregation beside the existing one, which is not changed), with its tests in a new file; then `scripts/n2_archive_check.py`, which does steps 3, 4's run and 5, with its tests in a new file; each code and test commit gated bare before it is made. The run follows, then the survey of the new tests with its predictions committed first, then the counts.

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. A code or test commit passes the full bare gate before it is made (R-DQ clause 2).

## 79. M5n N2b: the archive check run, the scoring of section 78, and what the decision bars are (P141 C8, R-T)

An observation log, so this section only adds. `scripts/n2_archive_check.py` ran once at `m5n` `f43acc0` (SHA-256 of the script is that of the committed file) with `--responses "F:\trading bot\scratch\p140\n2_responses"`, from `2026-10-24T11:17:37Z` to `11:19:20Z`: **exit 0, 1 minute 43 seconds, no request** (the script has no fetcher), all **34 saved responses matching `responses.sha256`** (SHA-256 of the list `c3d099e59f77ef74c96b03179cba0d00050f0099792f92fa4e353d8c28de93fb`, the same as section 75's). Nothing was written under `deploy\45547f107715`, the rehearsal clone or the store; no bar at or after `2024-01-01` was read. The output is `archive_check_out.txt`, SHA-256 `39bf6aeec2d4a5ed6e4c8715111e2da4528f970e29a285a567e5c7c8e01dcda0`. **No return, P&L, equity or metric was computed.**

### Table A: the archive series against the saved API responses

| Series | Archive | API | Compared | Equal | Mismatched | open | high | low | close | volume | Archive-only | API-only |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1d | 2328 | 2328 | 2328 | 2318 | 10 | 0 | 0 | 0 | 0 | 10 | 0 | 0 |
| BTCUSDT 4h | 13950 | 13951 | 13950 | 13939 | 11 | 0 | 0 | 0 | 0 | 11 | 0 | 1 |
| ETHUSDT 1d | 2328 | 2328 | 2328 | 2319 | 9 | 0 | 0 | 0 | 0 | 9 | 0 | 0 |
| ETHUSDT 4h | 13950 | 13951 | 13950 | 13940 | 10 | 0 | 0 | 1 | 0 | 10 | 0 | 1 |

The one API-only bucket in each 4h series is `2017-09-06T16:00:00Z`. The mismatch list holds **41 rows (40 volume rows and one ETHUSDT 4h low, `2021-01-11T08:00:00Z`, archive `1063` against API `1049.01`)**, so none was cut by the cap of 50. Every mismatching volume has the **API's larger than the archive's**; the buckets lie between `2018-11-26` and `2021-12-27`.

### Table B: the traded-minute aggregation against the archive series (R-DV)

| Series | Archive | Aggregated | Complete / incomplete | No traded minute | Consistent | Failed | open | high | low | close | Failed complete | Failed incomplete | Archive-only |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1d | 2328 | 2314 | 2280 / 34 | 0 | 2311 | 3 | 2 | 0 | 2 | 1 | **0** | 3 | 14 |
| BTCUSDT 4h | 13950 | 13861 | 13812 / 49 | 0 | 13856 | 5 | 2 | 1 | 3 | 2 | **1** | 4 | 89 |
| ETHUSDT 1d | 2328 | 2314 | 2280 / 34 | 0 | 2311 | 3 | 2 | 1 | 2 | 1 | **0** | 3 | 14 |
| ETHUSDT 4h | 13950 | 13861 | 13812 / 49 | 0 | 13857 | 4 | 2 | 2 | 2 | 2 | **0** | 4 | 89 |

The failing buckets (15) are listed in the output with their times and fields and no price. **Fourteen are incomplete buckets at the edges of the archive's 1m holes** (`2017-12-04`, `2017-12-18`, `2018-02-10` in the 1d series and their 4h buckets, and the 4h bucket `2020-12-21T12:00:00Z`), where minutes the 1m store lacks are in the venue's bar. **One is complete: BTCUSDT 4h `2021-04-22T00:00:00Z`, field `low`, 240 traded minutes, 0 missing.** The aggregator has no bucket the archive lacks.

### Table C: the volume gap on the complete buckets (archive volume against the sum of the 1m rows)

| Series | Complete paired | Equal | Larger up to 0.01% | up to 0.1% | up to 1% | over 1% | Archive smaller | Median | Max |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1d | 2280 | 2241 | 28 | 6 | 2 | 2 | 1 | 0.003562% | 4.379802% |
| BTCUSDT 4h | 13812 | 13770 | 15 | 17 | 6 | 3 | 1 | 0.013775% | 14.663466% |
| ETHUSDT 1d | 2280 | 2241 | 26 | 9 | 2 | 1 | 1 | 0.003641% | 4.746397% |
| ETHUSDT 4h | 13812 | 13770 | 17 | 16 | 5 | 3 | 1 | 0.023834% | 16.347276% |

A read-only look at where the large gaps are (`scratch\p141\diagnose_gap.py` SHA-256 `bf20761a73253eaa8dd77ce6b0fb23a2113488243cfe0888e493b0b49bff4dd9`, output `diagnose_gap_out.txt` `f168e2e822dd961c7173be24bf4326bb1d3fb9dfbe3a9e1f4d688200be7b68a6`, dates and relative sizes only): the buckets over 1%, and the one with the archive smaller, are `2018-03-04` (archive larger, 1.0% in 1d and 7.4% to 8.5% in 4h), **`2021-01-21` (archive SMALLER than the 1m sum, 2.4% in 1d and 11% in 4h at 08:00)** and `2021-04-22` and `2021-04-23` (archive larger, 4.4% to 4.7% in 1d and 14.7% to 16.3% in 4h on the 23rd). Nothing in the tree says what happened on those days.

### Section 78's predictions, scored

| | Prediction | Result |
|---|---|---|
| a | The archive 1d equals the API in all five fields in all 2328 buckets; the 4h has exactly one API-only bucket (lean: `2017-09-06 16:00`), no archive-only and 0 mismatches; if there are mismatches, in volume and in 2017 and 2018 | **The set part HELD** (2328 against 2328; 4h API-only 1 at `2017-09-06T16:00:00Z`, archive-only 0). **The 0-mismatch part is FALSE:** 10, 11, 9 and 10 buckets differ, all in volume but one ETHUSDT 4h low, and the API's volume is the larger in every one. The lean about 2017 and 2018 was **wrong**: they lie between 2018-11 and 2021-12 |
| b | Under the traded-minute rule the open, high, low and close equal the venue's for every complete bucket except about one (BTCUSDT 4h, plus or minus 1); open and close mismatches 0 everywhere; complete buckets with no traded minute 0 (at most 3) | **HELD, to the bucket.** Failed complete: BTCUSDT 1d 0, 4h **1**, ETHUSDT 1d 0, 4h 0; open and close mismatches in complete buckets 0; no traded-minute-less bucket in any series |
| c | The venue's volume is larger in the same complete buckets as P140 and smaller in none; median about 0.002% (0.0005% to 0.01%), maximum about 1% (0.5% to 3%); BTCUSDT 1d bands about 2234 / 30 / 12 / 3 / 1 or 2 | **Partly FALSE.** The decision bars' volume is larger than the 1m sum in 38 BTCUSDT 1d buckets (P140's API figure was 46) and **smaller in one per series (`2021-01-21`)**, so "smaller in none" fails. Median **held for 1d** (0.0036%) and **missed for 4h** (0.0138% and 0.0238%, above the range). **The maximum missed everywhere** (4.4% to 16.3%, against about 1%). Bands for BTCUSDT 1d: 2241 / 28 / 6 / 2 / 2: the first, second, fourth and fifth held, the third (12) was twice the observed 6 |
| d | The store's 1m rows carry no trade count, so a traded minute is a minute with nonzero volume | **HELD** (the schema; the aggregation was keyed on volume and 0 buckets lacked a traded minute) |
| e | No request; every one of the 34 saved responses matches its digest; under 10 minutes | **HELD.** 1 minute 43 seconds |
| f | Counts and two capped lists, no price in the volume bands | **HELD.** 41 mismatch rows and 15 failing buckets, both under the cap; the failing-bucket list carries no price |

### What follows, and what does not

1. **R-DV's check passes in the sense the ruling needs, with its exceptions listed.** Every complete bucket's open, high, low and close under the traded-minute rule equals the archive series' except one (BTCUSDT 4h `2021-04-22T00:00:00Z`, low), and the other failures are incomplete buckets whose minutes the 1m store lacks. How N4 treats the 15 is for N4 to rule, as R-DV says.
2. **The "venue's native bar" has two volumes.** The archive series and the API agree on every open, high, low and close (one ETHUSDT 4h low excepted) and disagree on volume in about 0.4% of buckets, the API's the larger; and the 1m rows' sum differs from the archive's volume in about 1.7% of complete 1d buckets. Which volume is the decision bar's is not ruled; R-DV names the archive series, which is what Tables B and C use. A strategy that uses volume (the charter's candidates are trend and breakout on price, not volume) would meet the question; one that does not is untouched by it.
3. **The aggregation's plain version is now superseded for prices** by the traded-minute version; the plain one stays, because section 75 and its tests are about it.

## 80. M5n N2b: the predictions for the mutation survey of the traded-minute and archive-check tests, and for the re-run of the aggregation survey, before they are run (P141 C9, R-T, R-DQ)

An observation log, so this section only adds. P141 proves that the 76 tests of C5 and C7 bite (38 in `tests/unit/test_aggregation_traded.py` against the traded-minute code in `src/trading_bot/data/aggregation.py`, and 38 in `tests/unit/test_n2_archive_check.py` against `scripts/n2_archive_check.py`), and re-runs section 76's 30 aggregation mutations because C3 and C4 changed `aggregation.py`'s body (`M5n-032`). **This section is committed before any of the three surveys is run.** Everything here decides nothing about S4.

### The method

As section 76: the P117 harness (`survey.py` SHA-256 `cd2eb339e4fdf65d361482cccf0511ee3fd28a495fd90815cd5b3b357ed3202a`, `p116_hook.py` `febedd0bf7a8fee6a9fe3ac2462975d917ee5e31f5e1daf2acb57f7d378e2a8d`) in a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven before any result counts, an unmutated baseline predicted green, every mutation byte-exact with one match asserted and every restore shown SHA-equal, the worktrees removed afterwards. Three runs, one spec each, each executing only the mutated file's own tests: `survey_a2.json` (the 30 mutations of section 76 against the 58 tests of `test_aggregation.py`; baseline predicted **58 passed**), `survey_t.json` (29 against the 38 tests of `test_aggregation_traded.py`; **38 passed**) and `survey_c.json` (35 against the 38 tests of `test_n2_archive_check.py`; **38 passed**). The specs are written by `scratch\p141\make_spec2.py` from the tables below, and an anchor that occurs more than once in the file is extended to the left, line by line, until it occurs once. The tests of `test_aggregation_traded.py` also pass through the shared helpers (`_checked_stream`, `_width_ms`, `_epoch_ms`, `_require_grid`), so the T run mutates those too; the old tests' reach into the traded code, and `test_n2_archive_check.py`'s into `aggregation.py`, are not predicted.

A kill is a failure present under the mutation and absent at baseline, by the three exception types of `M5i-115`. More than predicted is recorded (MORE); fewer halts the survey (FEWER). The tests were read for expressiveness and for the assertion looking before the predictions were written.

### Totals

**A2: 30 mutations, 170 predicted kills, section 76's table unchanged** (the old tests call only `aggregate_bars`, whose behaviour C3 did not change). The re-anchored mutations differ from section 76's only in where the text now lives: `a10` is the `yield` in `_checked_stream`, `a12` is the final `if current is not None:` of `aggregate_bars`, and the others keep their line and gain context. **T: 29 mutations, 128 predicted kills. C: 35 mutations, 51 predicted kills.** 94 mutations and 349 predicted kills in all.

**Mutations predicted to be killed by nothing, five:** `a01` is equivalent, as in section 76. `c31` (only a `CheckError` caught by `main`), `c32` (the API-only runs not printed), `c34` (the failing-bucket list printing 51 rows) and `c35` (two decimals on a percentage) are **unpinned**: no test refuses a run through a `VerifyError`, an `AggregationError` or an `OSError` by way of `main`, none asserts a run line in the printed output, none has more than 50 failing buckets, and no test renders section C of a real report.

**Tests predicted to be killed by no mutation:** the aggregation file **3 of 58**, as in section 76. In `test_aggregation_traded.py` **3 of 38**: the `1w` and empty-string cases of the timeframe refusal (any membership test refuses them) and `test_empty_input_gives_no_bars` (no mutation touches an empty stream). In `test_n2_archive_check.py` **2 of 38**: `test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[9999.00000000-bands0]` (the equal case returns before the band is chosen, and no mutation of the table changes that path) and `test_the_script_has_no_fetcher_and_no_network_parameter` (a property of the signature, which no mutation in the table changes). The test that no 2024-01 file is opened is predicted to be killed only incidentally, by `c11`, because it asserts an equal count after the run; no mutation of the table removes the window end itself, which the script takes from `n2_verify_bars.py`.

**Where a prediction is most likely to be wrong, named in advance:** `t30` (every minute its own bucket, 18 kills) and `t21` (the last traded bucket never flushed, 23) are counts of the tests that reach the mutated line; `t01` (a filler counted as traded, 11) rests on which tests have a filler whose price differs from the trade next to it; `c24` (the sign test, 7) rests on the volume-gap tests all having a gap above zero except one; and `c21` (volume among the consistency fields, 3) rests on the volumes of an incomplete bucket never equalling the archive's in the fixtures.

The codes in the T and C tables are keyed to test ids at the end of the section; the A2 table is section 76's, to which its codes belong.

### A2: the 30 mutations of section 76, re-anchored, predictions as in section 76

(See section 76's table for the break and the predicted kills of `a01` to `a30`, which are unchanged.)

### T: predicted kills, `src/trading_bot/data/aggregation.py` against `tests/unit/test_aggregation_traded.py`


| Mutation | The break | Predicted kills (tests/unit/test_aggregation_traded.py) |
|---|---|---|
| t01 | a filler minute counts as traded | T4, T5, T7, T8, T9, T11, T12, T16, T22, T23, T33 |
| t03 | the close stays the first traded minute's | T1, T22, T23 |
| t04 | the high keeps the LOWEST traded high | T1, T9, T10, T22, T23 |
| t05 | the low keeps the HIGHEST traded low | T1, T9, T10, T22, T23 |
| t06 | open, high and low restart at every traded minute | T1, T9, T22, T23 |
| t07 | the volume is the last minute's and not the sum | T2, T22, T23 |
| t08 | the present count is never incremented | T2, T4, T11, T16, T22, T23, T33 |
| t09 | minutes_missing is the present count | T2, T11, T16 |
| t10 | a traded minute counts twice | T2, T4, T7, T16, T22, T23, T33 |
| t11 | close_time is the next bucket's first millisecond | T18, T19, T20, T21 |
| t12 | open_time is one millisecond late | T17, T18, T19, T20, T21, T35 |
| t13 | a bar with no traded minute may carry a price | T13 |
| t14 | a bar with a traded minute may lack a price | T14 |
| t15 | the open is not a Money field | T15 |
| t16 | the store reader does not check the grid | T36, T37, T38 |
| t17 | the store is asked for 40 days beyond end | T35 |
| t18 | the store is always asked for BTCUSDT | T34 |
| t19 | the store is asked for an empty range | T33, T34, T35 |
| t21 | the last traded bucket is never flushed | T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T16, T17, T18, T19, T20, T21, T22, T23, T33, T34, T35 |
| t22 | a later bucket is folded into the current one | T12, T17, T18, T19, T22, T23 |
| t23 | any stored interval is an aggregated timeframe | T28, T29, T38 |
| t24 | a candle that is not 1m is accepted | T24 |
| t25 | a second symbol is accepted | T26 |
| t26 | an open off the minute grid is accepted | T27 |
| t27 | the ordering check is removed | T25 |
| t28 | the grid check on start and end is removed | T36, T37, T38 |
| t29 | a naive instant is not refused by the aggregator | T38 |
| t30 | every minute is its own bucket | T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11, T12, T16, T17, T22, T23, T33, T35 |
| t31 | the previous open time is never remembered | T25 |

### C: predicted kills, `scripts/n2_archive_check.py` against `tests/unit/test_n2_archive_check.py`

| Mutation | The break | Predicted kills (tests/unit/test_n2_archive_check.py) |
|---|---|---|
| c01 | a missing digest list is not checked for | K28 |
| c02 | a malformed digest line is not refused | K29 |
| c03 | the response files and the list may disagree | K26, K27 |
| c04 | a response is not checked against its digest | K25 |
| c06 | open times out of order are accepted | K31 |
| c07 | a bar at or after the window end is accepted | K30 |
| c08 | the list digest is that of nothing | K3 |
| c09 | the file count is one too many | K3 |
| c11 | equal counts two per bar in the archive comparison | K1, K4, K7, K8, K33, K35 |
| c12 | a field is counted twice in the archive comparison | K4, K5 |
| c13 | a field is counted twice in the consistency check | K9 |
| c14 | archive-only counts the API-only bars | K7, K8 |
| c15 | the API-only runs are built from the archive-only bars | K7 |
| c16 | the archive-only runs are built from the API-only bars | K8 |
| c17 | a bucket with no traded minute is not counted | K13 |
| c18 | consistent counts two per bucket | K1, K2 |
| c19 | failed complete and incomplete are swapped | K9, K12 |
| c20 | every bucket counts as complete | K11 |
| c21 | volume is one of the consistency fields | K10, K11, K12 |
| c22 | the first band edge is 0.02% | K17, K18 |
| c23 | a gap on a band edge falls in the next band | K16, K19 |
| c24 | a gap above zero is counted as smaller | K16, K17, K18, K19, K20, K21, K22 |
| c25 | the median is a tenth of the percentage | K23 |
| c26 | an incomplete bucket is in the volume gap | K24 |
| c28 | a series with no saved response is not refused | K32 |
| c30 | a refused run exits 0 | K38 |
| c31 | only a CheckError is caught by main | none |
| c32 | the API-only runs are not printed | none |
| c33 | the archive mismatch list prints 51 rows | K37 |
| c34 | the failing-bucket list prints 51 rows | none |
| c35 | the volume percentages print two decimals | none |
| c38 | figures are compared as strings in the archive comparison | K6 |
| c39 | aggregator-only counts the archive-only buckets | K14 |
| c40 | the failing-bucket list inverts complete | K36 |
| c37 | the consistency fields lack the high | K9 |

### The test key (every code the T and C tables use)

| Code | Test |
|---|---|
| K1 | `TestADayThatAgreesEverywhere::test_the_archive_equals_the_api_and_the_aggregation_is_consistent` |
| K2 | `TestADayThatAgreesEverywhere::test_a_zero_volume_first_minute_is_consistent_under_the_traded_rule` |
| K3 | `TestADayThatAgreesEverywhere::test_the_list_digest_and_file_count_are_reported` |
| K4 | `TestArchiveAgainstTheApi::test_a_wrong_field_is_counted_by_field_and_listed_with_both_values` |
| K5 | `TestArchiveAgainstTheApi::test_two_wrong_fields_are_one_mismatched_bar_and_two_field_counts` |
| K6 | `TestArchiveAgainstTheApi::test_figures_are_compared_as_decimals_not_as_strings` |
| K7 | `TestArchiveAgainstTheApi::test_a_bar_only_the_api_has_is_api_only_and_a_run` |
| K8 | `TestArchiveAgainstTheApi::test_a_bar_only_the_archive_has_is_archive_only` |
| K9 | `TestTheTradedMinuteConsistencyCheck::test_a_price_the_archive_has_differently_fails_the_bucket_and_is_listed_without_a_price` |
| K10 | `TestTheTradedMinuteConsistencyCheck::test_a_volume_difference_is_not_a_consistency_failure` |
| K11 | `TestTheTradedMinuteConsistencyCheck::test_an_incomplete_bucket_with_the_right_prices_is_consistent` |
| K12 | `TestTheTradedMinuteConsistencyCheck::test_an_incomplete_bucket_whose_extreme_minute_is_missing_fails_and_says_so` |
| K13 | `TestTheTradedMinuteConsistencyCheck::test_a_bucket_with_no_traded_minute_is_counted_and_not_checked` |
| K14 | `TestTheTradedMinuteConsistencyCheck::test_buckets_only_one_side_has_are_counted` |
| K16 | `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10000.00000000-bands1]` |
| K17 | `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10000.10000000-bands2]` |
| K18 | `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10001.00000000-bands3]` |
| K19 | `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10100.00000000-bands4]` |
| K20 | `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10101.00000000-bands5]` |
| K21 | `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[20000.00000000-bands6]` |
| K22 | `TestTheVolumeGap::test_the_archive_being_smaller_is_counted_apart_from_the_bands` |
| K23 | `TestTheVolumeGap::test_the_median_and_maximum_are_percentages_of_the_archive_volume` |
| K24 | `TestTheVolumeGap::test_an_incomplete_bucket_is_left_out_of_the_gap` |
| K25 | `TestTheSavedEvidenceIsChecked::test_a_response_that_no_longer_matches_its_digest_refuses_the_run` |
| K26 | `TestTheSavedEvidenceIsChecked::test_a_json_file_the_list_does_not_name_refuses_the_run` |
| K27 | `TestTheSavedEvidenceIsChecked::test_a_listed_file_that_is_missing_refuses_the_run` |
| K28 | `TestTheSavedEvidenceIsChecked::test_a_missing_digest_list_refuses_the_run` |
| K29 | `TestTheSavedEvidenceIsChecked::test_a_malformed_digest_line_refuses_the_run` |
| K30 | `TestTheSavedEvidenceIsChecked::test_a_bar_at_or_after_the_window_end_refuses_the_run` |
| K31 | `TestTheSavedEvidenceIsChecked::test_open_times_out_of_order_refuse_the_run` |
| K32 | `TestTheSavedEvidenceIsChecked::test_a_series_with_no_saved_response_refuses_the_run` |
| K33 | `TestNothingAtOrAfterTheWindowEndIsRead::test_files_of_2024_01_that_no_longer_match_their_hash_are_never_opened` |
| K35 | `TestWhatIsPrintedAndWhatIsNotAsked::test_a_clean_run_prints_the_three_reports_and_no_price` |
| K36 | `TestWhatIsPrintedAndWhatIsNotAsked::test_the_failing_bucket_list_has_times_and_fields_and_no_price` |
| K37 | `TestWhatIsPrintedAndWhatIsNotAsked::test_the_mismatch_list_is_capped_at_fifty_rows` |
| K38 | `TestWhatIsPrintedAndWhatIsNotAsked::test_a_refused_run_is_an_error_exit_and_prints_no_report` |
| T1 | `TestABucketInWhichEveryMinuteTraded::test_it_equals_the_plain_aggregation_in_the_four_prices` |
| T2 | `TestABucketInWhichEveryMinuteTraded::test_the_counts_and_the_volume` |
| T3 | `TestABucketInWhichEveryMinuteTraded::test_every_figure_is_a_decimal` |
| T4 | `TestAZeroTradeFirstMinute::test_the_open_is_the_first_traded_minutes_not_the_fillers` |
| T5 | `TestAZeroTradeFirstMinute::test_the_plain_aggregation_takes_the_fillers_open_and_that_is_the_difference` |
| T6 | `TestAZeroTradeFirstMinute::test_a_filler_whose_price_is_the_first_trade_changes_nothing` |
| T7 | `TestAZeroTradeLastMinute::test_the_close_is_the_last_traded_minutes` |
| T8 | `TestAZeroTradeLastMinute::test_a_filler_close_that_differs_is_not_taken` |
| T9 | `TestAZeroTradeExtreme::test_a_fillers_high_and_low_do_not_widen_the_bucket` |
| T10 | `TestAZeroTradeExtreme::test_a_traded_extreme_is_kept` |
| T11 | `TestABucketWithNoTradedMinute::test_it_has_no_prices_a_volume_of_zero_and_is_still_complete` |
| T12 | `TestABucketWithNoTradedMinute::test_it_is_emitted_and_not_skipped_or_priced_from_a_neighbour` |
| T13 | `TestABucketWithNoTradedMinute::test_a_bar_with_no_traded_minute_cannot_carry_a_price` |
| T14 | `TestABucketWithNoTradedMinute::test_a_bar_with_a_traded_minute_must_carry_all_four_prices` |
| T15 | `TestABucketWithNoTradedMinute::test_a_float_price_is_refused` |
| T16 | `TestGapsAreStillReportedAndNeverFilled::test_a_missing_minute_is_counted_beside_a_filler` |
| T17 | `TestGapsAreStillReportedAndNeverFilled::test_a_bucket_with_no_stored_minute_is_not_emitted` |
| T18 | `TestBothPairsAndBothTimeframes::test_the_symbol_timeframe_and_grid_are_the_plain_aggregations[4h-BTCUSDT]` |
| T19 | `TestBothPairsAndBothTimeframes::test_the_symbol_timeframe_and_grid_are_the_plain_aggregations[4h-ETHUSDT]` |
| T20 | `TestBothPairsAndBothTimeframes::test_the_symbol_timeframe_and_grid_are_the_plain_aggregations[1d-BTCUSDT]` |
| T21 | `TestBothPairsAndBothTimeframes::test_the_symbol_timeframe_and_grid_are_the_plain_aggregations[1d-ETHUSDT]` |
| T22 | `TestBothPairsAndBothTimeframes::test_a_day_equals_the_fold_of_its_six_4h_buckets_with_a_filler_first[BTCUSDT]` |
| T23 | `TestBothPairsAndBothTimeframes::test_a_day_equals_the_fold_of_its_six_4h_buckets_with_a_filler_first[ETHUSDT]` |
| T24 | `TestTheStreamChecksAreTheSame::test_a_candle_that_is_not_a_1m_bar_is_refused` |
| T25 | `TestTheStreamChecksAreTheSame::test_open_times_must_increase` |
| T26 | `TestTheStreamChecksAreTheSame::test_two_symbols_are_refused` |
| T27 | `TestTheStreamChecksAreTheSame::test_an_open_time_off_the_minute_is_refused` |
| T28 | `TestTheStreamChecksAreTheSame::test_a_timeframe_other_than_4h_and_1d_is_refused[1m]` |
| T29 | `TestTheStreamChecksAreTheSame::test_a_timeframe_other_than_4h_and_1d_is_refused[1h]` |
| T33 | `TestAgainstARealStore::test_a_filler_first_minute_is_skipped_for_the_open_and_counted_for_the_volume` |
| T34 | `TestAgainstARealStore::test_the_symbol_is_the_one_asked_for` |
| T35 | `TestAgainstARealStore::test_no_month_file_at_or_after_end_is_opened` |
| T36 | `TestAgainstARealStore::test_a_range_off_the_grid_is_refused_at_the_call[start0-end0]` |
| T37 | `TestAgainstARealStore::test_a_range_off_the_grid_is_refused_at_the_call[start1-end1]` |
| T38 | `TestAgainstARealStore::test_a_naive_instant_and_an_unaggregated_timeframe_are_refused_at_the_call` |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. The surveys run on the tree that carries this section, and their results are appended as section 81. The order of the remaining commits: this section; the three surveys and their results; the counts and the lists the new files falsify (`CLAUDE.md` and `README.md`).

## 81. M5n N2b: the mutation surveys of the traded-minute and archive-check tests, and the re-run of the aggregation survey, scored against section 80 (P141 C10, R-T)

An observation log, so this section only adds. The surveys ran as section 80 describes, in three detached worktrees outside the repository at `6666f4f` (the commit that carries section 80), one per spec, each running only the mutated file's own tests. Baselines: `a2` 58 passed in 1.00s; failing: []; `t` 38 passed in 0.88s; failing: []; `c` 38 passed in 4.52s; failing: []. The import location of `trading_bot` and `tests` was proven inside each worktree before any result counted, every restore was shown SHA-equal and each run ended with *all copied files are intact*. Outputs, SHA-256: `survey_a2_out.txt` `e4ff014f12abde2fad20e1d0e4bcf32cfcec6e9849d8486e81d92285eb8733c6`; `survey_t_out.txt` `a456a4b4b2d0d71fa0f872647ef74fab0d8a9a40c5eb2fdce594397d649fcf79`; `survey_c_out.txt` `9130f2983d43ae06713ac8d32e484845023639e6694bd2620bb48aaf3df0bb74`. Specs: `survey_a2.json` `8461b25bfb352388ec22f327f37850b420ef61d8772ad0954d3bb3e66cfb6eb9`; `survey_t.json` `13b26c509b3164b4bdded032ad9ccd5dfb03092fc0a369d7d43dd64e58896e13`; `survey_c.json` `62c637014d737c9ccf6478b2923dc628f82cb34c08499c39ee2f233aca180956`; `make_spec2.py` `d010dcafc5ba89b36694fa1e7b5c3842be6adb566a41ce34bf4af1c8cd446caa`.

### The totals

| Survey | Mutations | MATCH | MORE | FEWER | Predicted kills | Observed kills |
|---|---|---|---|---|---|---|
| `aggregation.py` against `test_aggregation.py` (section 76's 30, re-anchored) | 30 | 30 | 0 | 0 | 170 | 170 |
| `aggregation.py` traded-minute code against `test_aggregation_traded.py` | 29 | 29 | 0 | 0 | 128 | 128 |
| `n2_archive_check.py` against `test_n2_archive_check.py` | 35 | 33 | 2 | 0 | 51 | 63 |
| all three | 94 | 92 | 2 | 0 | 349 | 361 |

### Every mutation, `aggregation.py` against `test_aggregation.py` (section 76's 30, re-anchored)

| Mutation | Predicted | Killed | Verdict |
|---|---|---|---|
| a01 | 0 | 0 | MATCH |
| a02 | 4 | 4 | MATCH |
| a03 | 4 | 4 | MATCH |
| a04 | 7 | 7 | MATCH |
| a05 | 5 | 5 | MATCH |
| a06 | 9 | 9 | MATCH |
| a07 | 9 | 9 | MATCH |
| a08 | 2 | 2 | MATCH |
| a09 | 20 | 20 | MATCH |
| a10 | 26 | 26 | MATCH |
| a11 | 7 | 7 | MATCH |
| a12 | 38 | 38 | MATCH |
| a13 | 1 | 1 | MATCH |
| a14 | 1 | 1 | MATCH |
| a15 | 1 | 1 | MATCH |
| a16 | 1 | 1 | MATCH |
| a17 | 2 | 2 | MATCH |
| a18 | 4 | 4 | MATCH |
| a19 | 1 | 1 | MATCH |
| a20 | 4 | 4 | MATCH |
| a21 | 5 | 5 | MATCH |
| a22 | 1 | 1 | MATCH |
| a23 | 1 | 1 | MATCH |
| a24 | 1 | 1 | MATCH |
| a25 | 1 | 1 | MATCH |
| a26 | 2 | 2 | MATCH |
| a27 | 5 | 5 | MATCH |
| a28 | 3 | 3 | MATCH |
| a29 | 2 | 2 | MATCH |
| a30 | 3 | 3 | MATCH |

### Every mutation, `aggregation.py` traded-minute code against `test_aggregation_traded.py`

| Mutation | Predicted | Killed | Verdict |
|---|---|---|---|
| t01 | 11 | 11 | MATCH |
| t03 | 3 | 3 | MATCH |
| t04 | 5 | 5 | MATCH |
| t05 | 5 | 5 | MATCH |
| t06 | 4 | 4 | MATCH |
| t07 | 3 | 3 | MATCH |
| t08 | 7 | 7 | MATCH |
| t09 | 3 | 3 | MATCH |
| t10 | 7 | 7 | MATCH |
| t11 | 4 | 4 | MATCH |
| t12 | 6 | 6 | MATCH |
| t13 | 1 | 1 | MATCH |
| t14 | 1 | 1 | MATCH |
| t15 | 1 | 1 | MATCH |
| t16 | 3 | 3 | MATCH |
| t17 | 1 | 1 | MATCH |
| t18 | 1 | 1 | MATCH |
| t19 | 3 | 3 | MATCH |
| t21 | 23 | 23 | MATCH |
| t22 | 6 | 6 | MATCH |
| t23 | 3 | 3 | MATCH |
| t24 | 1 | 1 | MATCH |
| t25 | 1 | 1 | MATCH |
| t26 | 1 | 1 | MATCH |
| t27 | 1 | 1 | MATCH |
| t28 | 3 | 3 | MATCH |
| t29 | 1 | 1 | MATCH |
| t30 | 18 | 18 | MATCH |
| t31 | 1 | 1 | MATCH |

### Every mutation, `n2_archive_check.py` against `test_n2_archive_check.py`

| Mutation | Predicted | Killed | Verdict |
|---|---|---|---|
| c01 | 1 | 1 | MATCH |
| c02 | 1 | 1 | MATCH |
| c03 | 2 | 2 | MATCH |
| c04 | 1 | 2 | MORE |
| c06 | 1 | 1 | MATCH |
| c07 | 1 | 1 | MATCH |
| c08 | 1 | 1 | MATCH |
| c09 | 1 | 1 | MATCH |
| c11 | 6 | 6 | MATCH |
| c12 | 2 | 2 | MATCH |
| c13 | 1 | 1 | MATCH |
| c14 | 2 | 2 | MATCH |
| c15 | 1 | 1 | MATCH |
| c16 | 1 | 1 | MATCH |
| c17 | 1 | 1 | MATCH |
| c18 | 2 | 2 | MATCH |
| c19 | 2 | 2 | MATCH |
| c20 | 1 | 1 | MATCH |
| c21 | 3 | 14 | MORE |
| c22 | 2 | 2 | MATCH |
| c23 | 2 | 2 | MATCH |
| c24 | 7 | 7 | MATCH |
| c25 | 1 | 1 | MATCH |
| c26 | 1 | 1 | MATCH |
| c28 | 1 | 1 | MATCH |
| c30 | 1 | 1 | MATCH |
| c31 | 0 | 0 | MATCH |
| c32 | 0 | 0 | MATCH |
| c33 | 1 | 1 | MATCH |
| c34 | 0 | 0 | MATCH |
| c35 | 0 | 0 | MATCH |
| c38 | 1 | 1 | MATCH |
| c39 | 1 | 1 | MATCH |
| c40 | 1 | 1 | MATCH |
| c37 | 1 | 1 | MATCH |

### Where the surveys and the predictions differ

- **c04** killed beyond the prediction: `TestWhatIsPrintedAndWhatIsNotAsked::test_a_refused_run_is_an_error_exit_and_prints_no_report`
- **c21** killed beyond the prediction: `TestTheVolumeGap::test_an_incomplete_bucket_is_left_out_of_the_gap`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10000.00000000-bands1]`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10000.10000000-bands2]`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10001.00000000-bands3]`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10100.00000000-bands4]`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[10101.00000000-bands5]`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[20000.00000000-bands6]`; `TestTheVolumeGap::test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[9999.00000000-bands0]`; `TestTheVolumeGap::test_the_archive_being_smaller_is_counted_apart_from_the_bands`; `TestTheVolumeGap::test_the_median_and_maximum_are_percentages_of_the_archive_volume`; `TestWhatIsPrintedAndWhatIsNotAsked::test_the_failing_bucket_list_has_times_and_fields_and_no_price`

**The two MORE, diagnosed (reach errors, recorded and not violations; no mutation was killed by fewer tests than predicted, and no survey halted).**

- **c04** (a response not checked against its digest) was predicted to be killed by `test_a_response_that_no_longer_matches_its_digest_refuses_the_run` alone and was killed also by `test_a_refused_run_is_an_error_exit_and_prints_no_report`, which tampers with a response in the same way and asserts the error exit. The prediction named the test whose title says digest and not the one that reaches the check by another route: reasoning from what a test is for.
- **c21** (volume added to the consistency fields) was predicted to be killed by three tests and was killed by 14. The mutation lets the loop name `volume`, and the tally that follows is `dict.fromkeys(PRICE_FIELDS, 0)`, so `by_field["volume"] += 1` raises `KeyError`. Every test whose fixture has a volume that differs between the aggregation and the archive series therefore crashes in the consistency check, which is every volume-gap test (the fixtures are built to differ) and, through the 4h series staged beside the 1d one, all seven band cases including the equal one. The prediction traced the three tests that assert on the failing fields and not the line after the comprehension that indexes a dict by what it returns. A crash is a kill by the exception types of `M5i-115`, and these are `KeyError`s inside the code under test, which the harness counts as failures present under the mutation.
- **A consequence for the abstentions:** `test_the_archive_being_larger_lands_in_the_band_its_relative_difference_names[9999.00000000-bands0]` was predicted to be killed by no mutation and was killed by `c21`'s crash, so that abstention was an incidental kill and not a test that bites its own path. Section 80's other abstentions held.

### Tests killed by no mutation

`aggregation.py` against `test_aggregation.py` (section 76's 30, re-anchored): **3 of 58**: `TestTheValues::test_empty_input_gives_no_bars`; `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[1w]`; `TestInputThatCannotBeAggregatedWithoutGuessing::test_a_timeframe_other_than_4h_and_1d_is_refused[]`

`aggregation.py` traded-minute code against `test_aggregation_traded.py`: **3 of 38**: `TestTheStreamChecksAreTheSame::test_a_timeframe_other_than_4h_and_1d_is_refused[1w]`; `TestTheStreamChecksAreTheSame::test_a_timeframe_other_than_4h_and_1d_is_refused[]`; `TestTheStreamChecksAreTheSame::test_empty_input_gives_no_bars`

`n2_archive_check.py` against `test_n2_archive_check.py`: **1 of 38**: `TestWhatIsPrintedAndWhatIsNotAsked::test_the_script_has_no_fetcher_and_no_network_parameter`

Section 80 predicted 3, 3 and 2. The scripts that made these results are in `scratch\p141`: `make_spec2.py`, `build81.py` (this text).

## 82. M5n N3: P142's halts and the predictions for the indicators, the six candidates and their entry-event counts, before any code (P142 C2, R-T, R-DQ, R-DT)

An observation log, so this section only adds. P142 builds N3 under R-DX, R-DY, R-DZ and R-DT-3b (`docs/M5N_CHARTER_DRAFT.md` section 15): six long-only candidates on the archive decision series, no volume, every indicator window gap-free, and a script that counts entry events. Under R-DQ clause (1) this section is committed BEFORE any code or test is drafted, in scratch or in the repository. The only reading done first was of the source (`indicators/indicators.py`, `strategies/base.py`, `registry.py`, `helpers.py`, `examples/sma_crossover.py`, `config/models.py`) and of the `MANIFEST.jsonl` row counts already quoted in section 78. **No archive bar was read, and nothing here decides anything about S4.**

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| not on `m5n`, `git status` not clean, HEAD is not `f840e98` | `git branch --show-current`, `git status --porcelain`, `git rev-parse --short HEAD` | `m5n`, empty, `f840e98` (then `e942e4f` after C1, the charter commit) |
| a command would write under `deploy\45547f107715`, the rehearsal clone or the canonical store, or touch `config.yaml` or `config.s4.yaml` | every command in the plan | none: the count script reads the store through `HistoricalStore`, which only reads, and `config.s4.yaml` was read only as a committed blob (`git cat-file -p HEAD:config.s4.yaml`) to learn the file's shape |
| any venue request | the plan | none: the script has no fetcher |
| any bar at or after `2024-01-01T00:00:00Z` read | the reader is called with `end = 2024-01-01T00:00:00Z` | no bar read yet |
| anything computes a return, P&L, equity, exit or metric | the plan | none: a candidate answers whether a condition became true on a bar, and the script counts those answers |
| a candidate needs a volume input | R-DY's six definitions | none: they read close, high, low (C1, C2, C4), two SMAs of the close (C3), the close with a high, a low and a close for the ATR (C5), and the close (C6) |

### What is built, and which indicators are reused

**Reused unchanged from `indicators/indicators.py`: `sma` (C3), `ema` and `atr` (C5), and `true_range`, which `atr` calls.** Their NaN contract (leading `NaN` for warm-up, a value at `period - 1` for `sma` and `ema`, the first `atr` at position `period`) is what the gap rule leans on. **New, in a module of their own (`indicators/breakout.py`), because `indicators.py` documents a leading-NaN table that a new function would have to join: `donchian_high` (the highest high of the prior `period` bars, not including the current one), `keltner_upper` (EMA plus a multiple of the Wilder ATR, composed from the two reused functions) and `momentum` (a series minus itself `period` bars earlier).**

A gap-free-window helper (`strategies/m5n/gaps.py`) takes the decision series' index and the timeframe's width and answers the two questions R-DZ needs: whether the last *n* rows are consecutive bars, and where the gap-free run that ends at the last row begins. Four strategy modules register six names: one Donchian implementation under `donchian_1d_20`, `donchian_1d_55` and `donchian_4h_20`, and one module each for `sma_cross_1d_50_200`, `keltner_4h_20_2` and `tsmom_1d_90`. Each reads open, high, low and close from the frame, ignores a volume column, takes `Signal.price` and `Signal.timestamp` from the candle, emits `BUY` and never `CLOSE`, and accepts one research parameter, `enforce_gaps` (default `True`), which switches R-DZ off so that its effect can be counted; nothing live uses it. A `config.m5n.yaml` for research names a backtest of `[2017-08-17, 2024-01-01)`, `fee_percent` 0.10, and enables no stop, no take-profit, no notification and no live mode.

### Definitions the predictions use

An **entry event** is a bar on which the candidate's condition is true and was false on the bar before (the edge; reading 1 of charter section 15); the bar before must itself be answerable, so an event needs the indicator window plus one bar. **Warm-up at the start of a series is not a gap and is not counted as a suppression.** A **suppression** is a bar on which the ungated candidate (`enforce_gaps=False`, the same rows read as if consecutive and the recursive indicators run over the whole history) has an entry event and the gated one has none; a **gated-only** event is the converse, which is possible only for C5 because its EMA and ATR are seeded again after a gap. All counts are upper bounds on trades, which need N4's trailing exit and the one-position rule.

### The predictions

| | Prediction |
|---|---|
| a | **Entry events over `[2017-08-17, 2024-01-01)`, per pair (BTCUSDT, ETHUSDT), estimate and range.** C1 `donchian_1d_20`: **115 (85 to 150)** and **120 (90 to 155)**; C2 `donchian_1d_55`: **70 (50 to 95)** and **72 (50 to 95)**; C3 `sma_cross_1d_50_200`: **5 (3 to 8)** and **6 (3 to 9)**; C4 `donchian_4h_20`: **880 (740 to 1030)** and **900 (760 to 1050)**; C5 `keltner_4h_20_2`: **450 (300 to 620)** and **480 (310 to 650)**; C6 `tsmom_1d_90`: **25 (15 to 40)** and **27 (15 to 42)**. REASONED from the share of bars on which each condition holds (about 9% for a 20-bar breakout of the highs, 5.5% for 55, about 5% of 4h closes above a 2-ATR channel, 55% of days with positive 90-day momentum) divided by the mean length of a run of true bars (1.5 to 2.2); UNMEASURED. The 4h counts are about seven times the 1d counts because the series has six bars a day; the SMA cross is the sparsest by an order of magnitude |
| b | **Entry events a gap suppresses: C1, C2, C3 and C6 none, in either pair** (the archive 1d series has all 2328 days). **C4: about 18 per pair (8 to 30); C5: about 11 per pair (4 to 20).** The archive 4h series has 13950 bars against 13967 possible slots from `2017-08-17T04:00`, so 17 missing slots; the same slots in both pairs is the lean, since the venue's outages and the one API-only bucket of section 79 are not pair-specific. A missing bar blocks the 22 following bars for C4 (the 20 prior bars, the current and the previous) and about 22 for C5 (the run must again hold an ATR and its previous value), and the events per bar are about 0.063 and 0.036, so about 1.4 and 0.8 events per isolated gap. **Gated-only events: none for C1 to C4 and C6; C5 at most 6 per pair** |
| c | **Indicators reused unchanged: `sma`, `ema`, `atr` and, inside it, `true_range`. New: `donchian_high`, `keltner_upper`, `momentum`.** No indicator in `indicators.py` is edited |
| d | The count script **prints counts only**: per candidate and pair the entry events, the R-DZ suppressions and gated-only events, and per timeframe and pair the number of missing decision slots (**1d: 0 in both pairs; 4h: 17 in both**); no price, no timestamp list and no return. It makes no request, reads `[2017-08-17, 2024-01-01)` only, and runs in **under 10 minutes** (the archive series are 2328 and 13950 bars per pair and each candidate is evaluated once per bar, with and without the gap rule) |
| e | The warm-up of the first event is the window plus one: C1 22 bars, C2 57, C3 201, C4 22, C5 22 after the first gap-free run begins, C6 92; **no event is counted inside a candidate's warm-up** |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. A code or test commit passes the full bare gate before it is made (R-DQ clause 2). The commits that follow: the indicators and the gap helper with their tests; the six candidates with theirs; the research config with its test; the count script with its tests; the run; the survey predictions; the survey; the counts.

## 83. M5n N3: the entry-event counts over the in-sample archive, scored against section 82 (P142 C12, R-T, R-DQ, R-DT-3a)

An observation log, so this section only adds. `scripts/n3_entry_counts.py` (`daf8320`, tests `67560d2`) was run ONCE on the canonical store, on `m5n` with a clean tree at `67560d2`: `python scripts/n3_entry_counts.py`, no argument, so the window is the committed `[2017-08-17, 2024-01-01)`. It started at `2026-10-24T18:36:34Z` by the machine's UTC clock and ended at `18:39:41Z`: **3 min 6 s of wall time, exit 0, standard error empty**. The output below is the whole of it, saved outside the repository as `scratch\p142\n3_counts_output.txt`; **its SHA-256 is `909c2f9b3747b0ca2c8e7eaaf969e437a468be87e39c9f49a4717430d96a6eea`**, and every count quoted in this section is a count in that output. It is counts only: no price, no timestamp list and no return. **Every event count is an UPPER BOUND on trades**: a trade needs N4's trailing exit and the one-position-per-pair rule, neither of which exists yet. Nothing here decides anything about S4.

### Halts, checked before the run

| Halt | Observed |
|---|---|
| not on `m5n`, `git status` not clean | `m5n`; empty `git status --short` |
| a command would write under `deploy\45547f107715`, the rehearsal clone or the canonical store, or touch `config.yaml` or `config.s4.yaml` | the one command writes its output to a file under `scratch\`; the script opens no file for writing (pinned by `test_it_opens_nothing_for_writing`) and `HistoricalStore` only reads |
| any venue request | none: the script has no fetcher (pinned by `test_it_reads_through_the_store_and_has_no_fetcher`) |
| any bar at or after `2024-01-01T00:00:00Z` read | the store is asked for `end = 2024-01-01T00:00:00Z` and opens no month file at or after it; a month file past the boundary that is not a month file is never opened (pinned by `test_a_month_at_or_after_the_boundary_is_never_opened`) |
| anything computes a return, P&L, equity, exit or metric | none: a candidate answers whether a condition became true on a bar, and the script counts those answers |
| a candidate needs a volume input | none: a replaced volume column changes no count (pinned by `test_a_volume_that_differs_changes_nothing`) |

### The output

```
N3 entry-event counts. Each is an UPPER BOUND on trades: a trade needs N4's trailing exit
and the one-position-per-pair rule. An event is an edge (true now, false on the bar before).

series             bars  slots  missing  gap_runs
BTCUSDT 1d         2328   2328        0         0
ETHUSDT 1d         2328   2328        0         0
BTCUSDT 4h        13950  13967       17         9
ETHUSDT 4h        13950  13967       17         9

candidate               pair        events  no_rdz  suppressed  gated_only
C1 donchian_1d_20       BTCUSDT        104     104           0           0
C1 donchian_1d_20       ETHUSDT        104     104           0           0
C2 donchian_1d_55       BTCUSDT         73      73           0           0
C2 donchian_1d_55       ETHUSDT         68      68           0           0
C3 sma_cross_1d_50_200  BTCUSDT          6       6           0           0
C3 sma_cross_1d_50_200  ETHUSDT          6       6           0           0
C4 donchian_4h_20       BTCUSDT        538     542           4           0
C4 donchian_4h_20       ETHUSDT        546     551           5           0
C5 keltner_4h_20_2      BTCUSDT        293     293           2           2
C5 keltner_4h_20_2      ETHUSDT        291     288           0           3
C6 tsmom_1d_90          BTCUSDT         45      45           0           0
C6 tsmom_1d_90          ETHUSDT         40      40           0           0
```

On every row `events = no_rdz - suppressed + gated_only` (538 = 542 - 4, 293 = 293 - 2 + 2, 291 = 288 + 3), which is also pinned on the test store.

### Section 82's predictions, scored

**(a) Entry events per pair, against the stated range.** Seven of the twelve are inside their range and five are outside it, all five in the direction of the trouble they were reasoned from.

| Candidate | Pair | Predicted (range) | Observed | Against the estimate | Verdict |
|---|---|---|---|---|---|
| C1 `donchian_1d_20` | BTCUSDT | 115 (85 to 150) | 104 | -10% | inside |
| C1 | ETHUSDT | 120 (90 to 155) | 104 | -13% | inside |
| C2 `donchian_1d_55` | BTCUSDT | 70 (50 to 95) | 73 | +4% | inside |
| C2 | ETHUSDT | 72 (50 to 95) | 68 | -6% | inside |
| C3 `sma_cross_1d_50_200` | BTCUSDT | 5 (3 to 8) | 6 | +1 | inside |
| C3 | ETHUSDT | 6 (3 to 9) | 6 | 0 | inside |
| C4 `donchian_4h_20` | BTCUSDT | 880 (740 to 1030) | 538 | -39% | **OUTSIDE, 202 under the range** |
| C4 | ETHUSDT | 900 (760 to 1050) | 546 | -39% | **OUTSIDE, 214 under the range** |
| C5 `keltner_4h_20_2` | BTCUSDT | 450 (300 to 620) | 293 | -35% | **OUTSIDE, 7 under the range** |
| C5 | ETHUSDT | 480 (310 to 650) | 291 | -39% | **OUTSIDE, 19 under the range** |
| C6 `tsmom_1d_90` | BTCUSDT | 25 (15 to 40) | 45 | +80% | **OUTSIDE, 5 over the range** |
| C6 | ETHUSDT | 27 (15 to 42) | 40 | +48% | inside |

Also predicted in (a): the 4h counts are about seven times the 1d counts. **Observed: C4 is 5.2 times C1** (538 against 104) and C5 is 2.8 times C1, so the statement holds for neither 4h candidate, while the SMA cross is the sparsest, as predicted: 6 against 40 to 546 for the others, 6.7 to 91 times fewer.

**(b) Suppressions and gated-only events.**

| Prediction | Observed | Verdict |
|---|---|---|
| C1, C2, C3, C6: no suppression in either pair | 0 in all eight rows | MATCH |
| C4: about 18 per pair (8 to 30) | 4 (BTCUSDT) and 5 (ETHUSDT) | **OUTSIDE, 4 and 3 under the range** |
| C5: about 11 per pair (4 to 20) | 2 (BTCUSDT) and 0 (ETHUSDT) | **OUTSIDE, 2 and 4 under the range** |
| gated-only: none for C1 to C4 and C6 | 0 in all ten rows | MATCH |
| gated-only: C5 at most 6 per pair | 2 and 3 | inside |
| missing decision slots: 1d none in either pair; 4h 17 in both | 0 and 0; 17 and 17 | MATCH, exact |
| the lean that the same slots are missing in both pairs | both 4h series show 13950 bars, 17 missing slots and 9 gap runs | consistent with it; the counts do not prove the slots are the same |

**(c) Indicators.** Reused unchanged: `sma`, `ema`, `atr` and `true_range` inside it. New: `donchian_high`, `keltner_upper` and `momentum`, in `indicators/breakout.py`. MEASURED at `67560d2` against `ee8d485`: `git diff --quiet ee8d485 HEAD -- src/trading_bot/indicators/indicators.py` reports no change, and `indicators/__init__.py` gains four lines of exports. MATCH.

**(d) The script.** Prints counts only: yes. Makes no request: yes. Reads `[2017-08-17, 2024-01-01)` only: yes. Runs in under 10 minutes: **3 min 6 s**. MATCH.

**(e) Warm-up.** No event is counted inside a candidate's warm-up: it holds by construction (the script evaluates a bar only when the history holds the candidate's `warmup_period` rows, and each candidate returns no signal on fewer than its window) and the output cannot show it. It is not a measurement of the run.

### Diagnoses, where a prediction missed

None of these is a rerun: the script was run once, as P142 item 5 says, so each diagnosis uses the printed counts and the arithmetic on them, and is labelled for what it rests on.

* **C4 and C5 came in 35 to 39% under their estimates, and the estimate's driver was the wrong one.** Section 82 reasoned the 4h counts from the share of 4h bars on which each condition holds (about 9% for a 20-bar breakout, about 5% above a 2-ATR channel) divided by a run length. DERIVED from the printed counts: C4 fires on 538 of 13950 bars, 3.9%, against the 6.3% to 6.5% per bar the prediction's estimates imply, and C5 on 2.1% against about 3.2% to 3.4%. The share of bars on which the condition holds is not printed and was not measured; what is measured is that the edge rate is about 60% of the one predicted. The 9% and the 5% were estimates and were not measured. A 20-bar window at 4h spans 3.3 days and not 20, and a close that clears the highs of the last 3.3 days is a weaker event than one that clears the last 20 days, but it also repeats in clusters, so the edge count falls where the share does not. REASONED, not measured.
* **C6 on BTCUSDT came in 80% over.** 45 events in 2328 days is one rising edge of the 90-day change per 52 days; the prediction's 25 assumed a longer mean cycle. A 90-day change that hovers near zero crosses it several times, and the strict `> 0` after `<= 0` counts each crossing. REASONED.
* **Suppressions were 4 and 5 against about 18 for C4, and 2 and 0 against about 11 for C5.** Two causes are in the printed counts. First, the 17 missing 4h slots lie in **9 gap runs**, not 17 isolated gaps, and the prediction blocked 22 following bars per slot where a run blocks them once: 9 runs at the observed C4 rate give 9 x 22 x 0.0386 = 7.6, against 14.4 for 17 gaps at the same rate, so the run count alone halves the estimate. Second, the observed 4 and 5 sit under even the 7.6, which fits a suppressed event needing the ungated reading to have one on the same bar and the gaps lying where there was little to suppress; which gaps those are is not printed, and the output carries no timestamp by design. REASONED for the second cause.
* **C5 has events only its re-seeding creates, as section 82 allowed: 2 on BTCUSDT and 3 on ETHUSDT.** On ETHUSDT it has three and suppresses none, so the gap rule ADDS 3 events there (291 against 288). A recursive indicator seeded again after a gap carries a different EMA and ATR than the one carried across it, and the difference can put a close over the band on a bar where the unbroken series does not. MEASURED as a count; the cause is REASONED.

### What these counts are, and are not

They are the number of times each rule, as ruled, said "enter" over the in-sample window, bar by bar, with the gap rule on. **They are not trades**, which need the one-position-per-pair rule (a candidate that is long cannot enter again) and N4's trailing exit; the counts bound the trades from above and nothing yet says by how much. They make no statement about any return. **C3 has 6 events per pair in 6.4 years**, which is a count of trades the gate will have to work with at most, per pair; whether a rule that sparse can be judged at all is for the owner and not decided here.

## 84. M5n N3: the predictions for the mutation survey of the N3 tests, before it is run (P142 C13, R-T, R-DQ)

An observation log, so this section only adds. P142 proves that the 218 tests it added bite: 26 in `tests/unit/test_indicators_breakout.py` against `src/trading_bot/indicators/breakout.py`, 42 in `tests/unit/test_m5n_gaps.py` against `src/trading_bot/strategies/m5n/gaps.py`, 89 in `tests/unit/test_m5n_strategies.py` against `base.py` and the four candidate modules (and one against the live registry's source), 49 in `tests/unit/test_n3_entry_counts.py` against `scripts/n3_entry_counts.py`, and 12 in `tests/unit/test_config_m5n.py` against `config.m5n.yaml`. **This section is committed before any of the five surveys is run.** Everything here decides nothing about S4.

### The method

As sections 76 and 80: the P117 harness (`survey.py` SHA-256 `cd2eb339e4fdf65d361482cccf0511ee3fd28a495fd90815cd5b3b357ed3202a`, `p116_hook.py` `febedd0bf7a8fee6a9fe3ac2462975d917ee5e31f5e1daf2acb57f7d378e2a8d`, both unchanged from section 80) in a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven before any result counts, an unmutated baseline predicted green, every mutation byte-exact with exactly one match asserted and every restore shown SHA-equal, the worktrees removed afterwards. Five runs, one spec each, each executing only the mutated files' own tests. The specs and these tables are one program's output (`scratch\p142\make_spec.py`), so the table cannot differ from the spec; the spec files' SHA-256 are `survey_b.json` `a747c7a03948db4807715d910e9f743e92e794dcbb78e1c0c546db509f96f217`, `survey_g.json` `e325a70e10d7620ffd1d15f10b2078ae5e24e5d017477c18fcae0f883edf6651`, `survey_s.json` `accc2ec70b79ad4af50acf10131ccbf3fe098ea939e0487143519b067a84da06`, `survey_n.json` `ef8563ef1006bbaa76e79d75c5a9758d2e440290812a764a7731d685434ba3bd` and `survey_y.json` `b2514bf684825bb19be2d8da0b71d4ad4af883478b5058909710687a391d1192`.

**What the harness counts, and what this section counts.** The harness reports every test that fails under a mutation, whatever it raised, and prints the exception types beside the verdict. A kill, by `M5i-115`, is a failure by `AssertionError` or `Failed`; an error raised by the code under test, or by a fixture, is a crash. Every mutation here is built to fail by an assertion, with two declared exceptions that fail by a crash and are counted in the predicted set because the harness counts them: `n45` (the last report row is dropped, so `N12` fails by a `KeyError` reading it) and `y22` (a mode the loader refuses, so every test that loads the file fails by the loader's `ValidationError`). A MORE is recorded and a FEWER halts the run, as before.

A mutation is predicted to fail a test only after the test's fixture was read for whether it can express the mutation and its assertion for whether it looks at what the mutation moves; the predictions below were written from the test sources, not from a run. **The one execution on mutated text before this commit** loaded the 22 mutated config texts through `AppConfig`, to learn which of them the loader still accepts (all but `y22`, which is meant to be refused); no test was run on any mutated tree.

### Totals

| Survey | Mutated file(s) | Tests | Mutations | Predicted failures | Mutations predicted to fail nothing |
|---|---|---|---|---|---|
| B | `indicators/breakout.py` | 26 | 25 | 47 | 3 |
| G | `strategies/m5n/gaps.py` | 42 | 20 | 98 | 0 |
| S | `base.py`, `donchian.py`, `sma_cross.py`, `tsmom.py`, `keltner.py`, `registry.py` | 89 | 45 | 282 | 5 |
| N | `scripts/n3_entry_counts.py` | 49 | 45 | 123 | 10 |
| Y | `config.m5n.yaml` | 12 | 22 | 29 | 2 |
| all five | | 218 | 157 | 579 | 20 |

**Mutations predicted to fail nothing, 20, each for a stated reason.** They are not omissions: each names a property that the tests do not pin, or an equivalent mutation, and a MORE on any of them is a finding.

| Mutation | Why no test is predicted to fail |
|---|---|
| m05 | `Series.diff(n)` is `series - series.shift(n)`: equivalent |
| m06 | momentum's index is asserted nowhere (B14 reads the name and dtype only), though Donchian's and Keltner's are |
| k07 | `atr` repeats the alignment check, so skipping Keltner's own leaves the refusal in B23 in place |
| s11 | the `timeframe` metadata value is asserted nowhere; the type check in S43 to S48 reads its type only |
| s12 | a recursive window as the last 22 rows is not told from the run, because every Keltner fixture is flat before the spike and an EMA and a Wilder ATR over flat bars do not depend on how many bars were read |
| s13 | the ungated window as the whole frame: every ungated fixture holds exactly the window or reads only its last rows |
| d09 | the Donchian `donchian_high` metadata of the previous bar equals the current bar's in every fixture (both are 10.0) |
| k05 | no Keltner fixture puts a close exactly on the band, which is not a round number |
| n08 | the store never serves a bar outside the window, so the guard that refuses one is never reached |
| n10 | the slots round down, not up: every fixture's first bar and `end` lie on the grid |
| n16, n17 | evaluating warm-up bars, and handing every candidate the whole prefix, change no count (they only cost time) |
| n23 | the signal's price and time come from the candle and no count reads them |
| n30 | the order of the series rows is read nowhere (the tests parse rows into a dictionary) |
| n32, n37 | `--start` is exercised by no test except as a refusal, so narrowing it, and its default's day, are unpinned |
| n39 | only `StoredFileError` is raised in the tests; the base class is never needed |
| n43 | the type check on a built strategy is never reached with a non-candidate |
| y20, y21 | the initial balance and the placeholder sizing fraction are asserted nowhere |

### Tests predicted to be killed by no mutation, and why

Ten of 218. In each the abstention is declared here, in advance, and a failure on any of them is a MORE.

| Test | Why no mutation in these tables fails it |
|---|---|
| B9 (a non-numeric series is refused) | the refusal is `_numeric_float`'s, in `indicators.py`, outside this survey's mutated file; removing it from `donchian_high` would raise pandas' own `DataError`, an escape and not a failure by assertion |
| B23 (misaligned indices are refused) | `atr` repeats the alignment check (`k07`) |
| S1 (the six names are registered) | the only way to fail it is a mutation that unregisters a name, which makes `create_strategy` raise inside the test: a crash, and none is in these tables |
| N5 and N38 (BTCUSDT C5 counts and trimming) | C5's rows are equal to C4's on the fixtures (both fire on the spike bar and not on the bar after), so no mutation of the counting separates them; only the order test, N48, tells the names apart (`n44`) |
| N9 and N42 (ETHUSDT C3 counts and trimming) | the expected count is zero in both readings; a mutation can only change a zero by inventing events, and none here does |
| N21 (the report is reproducible) | no mutation introduces non-determinism |
| N22 (a replaced volume column changes nothing) | the script's independence of volume rests on the candidates' own volume tests (S40 to S42, S63, S64, S75, S76, S86, S87); no mutation of the script reads a volume |
| N29 (check_window needs timezone-aware bounds) | removing the check makes the comparison raise `TypeError`, an escape and not a `ValueError` |

### Where a prediction is most likely to be wrong, named in advance

* **`s12` and S85.** S85 asserts that a gated Keltner band after a gap equals, with `==`, the band of the run alone. Under `s12` the window is 22 rows and not 40, over flat bars. Both give the same figures in exact arithmetic; whether pandas' recursive mean gives them to the last bit after 2 steps and after 20 is not known. The prediction is no failure; S85 failing would be a MORE and would be the one place the fixtures do tell the two windows apart.
* **`s14` (38) and `s15` (35)** are counts of the tests that reach a one-row change in the window; `s15` leaves S28 to S30 and S34 to S36 out because their frames hold a row more than the window needs.
* **`n19` (18) and `n18` (2).** `n18` predicts only N3 and N36, because the only event that sits on the first evaluable bar is BTCUSDT C3's, bar 200 against a warm-up of 201.
* **`b06` (B8) and `m04` (B15).** `b06` rests on pandas refusing a rolling window of 0 with a message that does not contain the test's pattern, or accepting it; either fails B8, and a different exception type would escape.
* **`s09` and `s17`.** Both rest on `Signal` accepting `CLOSE` and a strength of 0.5.
* **`k03` (8)** rests on the multiplier-3 band lying above every fixture's close, including S83's.
* **`y22`.** Ten tests fail by the loader's error, and C5 and C6, which read the file's text and never load it, are the two that do not.

### B: predicted failures, `src/trading_bot/indicators/breakout.py` against `tests/unit/test_indicators_breakout.py`

| Mutation | The break | Predicted failures (tests/unit/test_indicators_breakout.py) |
|---|---|---|
| b01 | the Donchian window includes the current bar (shift 0) | B1, B2, B3, B4, B5, B7 |
| b02 | the Donchian window takes the minimum, not the maximum | B1, B3, B4, B7 |
| b03 | the Donchian window accepts a partial window | B1, B3, B4 |
| b04 | the Donchian series is named without its period | B6 |
| b05 | the Donchian index is replaced by a range | B6 |
| b06 | the Donchian period is not checked | B8 |
| m01 | the momentum lag is one bar short | B10, B11, B12, B13 |
| m02 | the momentum sign is reversed | B10, B11, B12, B13 |
| m03 | the momentum series is named without its period | B14 |
| m04 | the momentum period is not checked | B15 |
| m05 | momentum is pandas' diff (an equivalent mutation) | none |
| m06 | the momentum index is replaced by a range (its index is asserted nowhere) | none |
| k01 | the Keltner EMA period is not checked | B22 |
| k02 | the Keltner ATR period is not checked | B22 |
| k03 | a zero or NaN multiplier is accepted | B22 |
| k04 | the multiplier is ignored | B16, B19, B20 |
| k05 | the EMA runs over the ATR period | B17, B20 |
| k06 | the ATR runs over the EMA period | B17, B20 |
| k07 | the alignment check is skipped (atr repeats it) | none |
| k08 | the Keltner series is named without its multiplier | B21 |
| k09 | the Keltner index is replaced by a range | B20, B21 |
| k10 | the band carries a constant offset | B16, B18, B19, B20 |
| v01 | momentum gains a volume parameter | B25 |
| v02 | keltner_upper gains a volume parameter | B24, B25 |
| e01 | momentum is dropped from __all__ | B26 |

### G: predicted failures, `src/trading_bot/strategies/m5n/gaps.py` against `tests/unit/test_m5n_gaps.py`

| Mutation | The break | Predicted failures (tests/unit/test_m5n_gaps.py) |
|---|---|---|
| g01 | the 4h width is one millisecond long | G1, G2, G4, G10, G12, G24, G31, G33, G39 |
| g02 | the 1d width is one millisecond long | G1, G3, G5, G11, G13, G25, G32, G34, G40 |
| g03 | the two widths are swapped | G1, G2, G3, G4, G5, G10, G11, G12, G13, G24, G25, G31, G32, G33, G34, G39, G40 |
| g04 | zero bars is not refused | G22, G23 |
| g05 | exactly the rows asked for are too few | G4, G5, G24, G25 |
| g06 | the tail is one row too long | G2, G3, G10, G11, G12, G13, G14, G15 |
| g07 | any consecutive pair makes a tail gap-free | G8, G9, G12, G13, G14, G15, G16, G17, G18, G19 |
| g08 | a step of at most one width is consecutive | G16, G17, G24 |
| g09 | a short frame is not checked for its timeframe | G30 |
| g10 | the run starts at the row before the last gap | G33, G34, G35, G36, G39, G40 |
| g11 | the run starts after the first gap | G33, G34 |
| g12 | a frame without a gap loses its first row | G31, G32 |
| g13 | the run is read from the spaced pairs, not the broken ones | G31, G32, G33, G34, G35, G36, G39, G40 |
| g14 | a repeated open time counts as spaced in the run | G39, G40 |
| g15 | an hourly frame is a decision timeframe | G1, G27, G30 |
| g16 | the refusal does not say a decision timeframe | G26, G27, G28, G29 |
| g17 | the tail writes into its input | G20, G21 |
| g18 | the run writes into its input | G41, G42 |
| g19 | too few rows are not refused | G6, G7 |
| g20 | a frame of one row loses it | G37, G38 |

### S: predicted failures, the candidates against `tests/unit/test_m5n_strategies.py`

| Mutation | The break | Predicted failures (tests/unit/test_m5n_strategies.py) |
|---|---|---|
| s01 | enforce_gaps is not checked to be a bool | S9 |
| s02 | the enforce_gaps attribute is always on | S34, S35, S36, S61, S73, S84 |
| s03 | the warm-up is one bar short of the window | S3, S4, S5, S6, S7, S8 |
| s04 | a candle of another timeframe is accepted | S49, S50, S51, S65, S89 |
| s05 | the refusal names the candle's timeframe as the candidate's | S65, S89 |
| s06 | a condition that is false still signals | S13, S14, S15, S19, S20, S21, S22, S23, S24, S28, S29, S30, S56, S57, S58, S59, S68, S69, S70, S71, S78, S79, S80, S81 |
| s07 | the timestamp is the bar's open time | S43, S44, S45, S46, S47, S48 |
| s08 | the price is the candle's low | S10, S11, S12, S43, S44, S45, S46, S47, S48 |
| s09 | the action is CLOSE | S10, S11, S12, S55, S66, S77 |
| s10 | the strategy metadata carries the timeframe | S43, S44, S45, S46, S47, S48 |
| s11 | the timeframe metadata carries the name (asserted nowhere) | none |
| s12 | a recursive window is the last window_bars rows | none |
| s13 | the ungated window is the whole frame | none |
| s14 | the gated window is one row short | S10, S11, S12, S16, S17, S18, S25, S26, S27, S28, S29, S30, S31, S32, S33, S37, S38, S39, S40, S41, S42, S43, S44, S45, S46, S47, S48, S55, S59, S62, S63, S64, S66, S67, S71, S74, S75, S76 |
| s15 | the gated window is one row long | S10, S11, S12, S16, S17, S18, S25, S26, S27, S31, S32, S33, S37, S38, S39, S40, S41, S42, S43, S44, S45, S46, S47, S48, S55, S59, S62, S63, S64, S66, S67, S71, S74, S75, S76 |
| s16 | the missing-column message drops the repr quotes | S52, S53, S54, S88 |
| s17 | the signal's strength is one half | S43, S44, S45, S46, S47, S48 |
| s18 | the live registry's source mentions the research package | S2 |
| d01 | the Donchian window is period + 1 rows | S3, S4, S6, S10, S11, S12, S16, S17, S18, S25, S26, S27, S28, S29, S30, S31, S32, S33, S34, S35, S36, S37, S38, S39, S40, S41, S42, S43, S44, S45, S46, S47, S48 |
| d02 | a close equal to the highest high signals | S13, S14, S15 |
| d03 | a previous close equal to its threshold counts as above | S25, S26, S27 |
| d04 | the Donchian entry is level-triggered | S22, S23, S24, S28, S29, S30 |
| d05 | the Donchian threshold is built from the closes | S10, S11, S12, S13, S14, S15, S19, S20, S21, S25, S26, S27, S52, S53, S54 |
| d06 | donchian_1d_55 looks back 50 bars | S4, S11, S32, S35 |
| d07 | donchian_1d_20 looks back 15 bars | S3, S10, S31, S34 |
| d08 | donchian_4h_20 looks back 15 bars | S6, S12, S33, S36 |
| d09 | the donchian_high metadata is the previous bar's (equal in the fixtures) | none |
| c01 | the fast average is a 49-bar one | S55 |
| c02 | the slow average is a 199-bar one | S5, S55, S60 |
| c03 | the cross is read the wrong way round | S55, S59, S61, S62, S63, S64 |
| c04 | the SMA window is the slow period, not one more | S5 |
| c05 | the fast_sma metadata is the previous bar's | S55 |
| t01 | the momentum lookback is 89 bars | S8, S72 |
| t02 | momentum must rise above 1 | S66, S67, S69, S71, S73, S74, S75, S76 |
| t03 | momentum must rise from below -1 | S66, S71, S73, S74, S75, S76 |
| t04 | the momentum metadata is the previous bar's | S66 |
| t05 | the prev_momentum metadata is the current bar's | S66, S67 |
| k01 | the Keltner EMA period is 19 | S77, S78 |
| k02 | the Keltner ATR period is 19 | S7, S77, S78, S82 |
| k03 | the Keltner multiplier is 3 | S77, S78, S81, S83, S84, S85, S86, S87 |
| k04 | the Keltner high and low are swapped | S77, S78, S79 |
| k05 | a close equal to the Keltner band signals (the band is never equal in the fixtures) | none |
| k06 | the Keltner entry is level-triggered | S80, S81 |
| k07 | the Keltner low is the close | S77, S78, S79, S88 |
| k08 | the Keltner window is the ATR period + 1 rows | S7 |

### N: predicted failures, `scripts/n3_entry_counts.py` against `tests/unit/test_n3_entry_counts.py`

| Mutation | The break | Predicted failures (tests/unit/test_n3_entry_counts.py) |
|---|---|---|
| n01 | a start before the window is accepted | N23 |
| n02 | an end after the window is accepted | N24, N25, N30 |
| n03 | an empty or reversed window is accepted | N26, N27 |
| n04 | the refusal does not name R-DT | N30 |
| n05 | the window ends on 2024-01-02 | N24, N25, N30, N49 |
| n06 | the window starts on 2017-08-16 | N23, N49 |
| n07 | load_series does not check the window | N30 |
| n08 | a served bar outside the window is not refused | none |
| n09 | an empty series reports one bar | N17 |
| n10 | the slots are rounded down (the grid is aligned in every fixture) | none |
| n11 | the missing slots are the slots plus the bars | N15, N16, N18, N28, N31 |
| n12 | the gap runs count the consecutive steps | N15, N16, N18, N28, N31 |
| n13 | the bars are one more than stored | N15, N16, N18, N28, N31 |
| n14 | the slots use the daily width | N15, N16 |
| n15 | the candidate is built without the gap flag | N7, N8, N10, N11, N12, N40, N41, N43, N44, N45 |
| n16 | every bar is evaluated, warm-up included | none |
| n17 | every candidate is handed the whole prefix | none |
| n18 | the view is one row longer than the window | N3, N36 |
| n19 | the view is one row shorter than the window | N1, N2, N3, N4, N6, N7, N8, N10, N12, N34, N35, N36, N37, N39, N40, N41, N43, N45 |
| n20 | the events are the ungated ones | N7, N8, N10, N11, N12, N14, N40, N41, N43, N44, N45 |
| n21 | the suppressions are the gated-only events | N7, N8, N10, N11, N12, N14 |
| n22 | the gated-only events are the suppressions | N7, N8, N10, N11, N12, N14 |
| n23 | the signal is built on the previous candle | none |
| n24 | the report does not say upper bound | N20 |
| n25 | the events and no-rule columns are swapped | N7, N8, N10, N11, N12, N14 |
| n26 | the slots and missing columns are swapped | N15, N16, N28, N31 |
| n27 | the report prints a decimal number | N19 |
| n28 | the report prints a time of day | N19 |
| n29 | a series with no bars is not refused | N32 |
| n30 | the series rows run pair first (order is read nowhere) | none |
| n31 | a narrowed window is read whole | N28 |
| n32 | a narrowed start is read whole (--start is narrowed nowhere) | none |
| n33 | a refused window exits 1 | N23, N24, N25, N26, N27 |
| n34 | an unreadable store exits 2 | N32, N33 |
| n35 | the refusal message says denied | N23, N24, N25, N26, N27 |
| n36 | the unreadable message says broken | N32, N33 |
| n37 | the default start is 2017-08-18 (--start is exercised nowhere) | none |
| n38 | the default end is 2023-12-31 | N15, N16, N31 |
| n39 | only a StoredFileError is caught by main | none |
| n40 | the first two candidates swap their names | N48 |
| n41 | the source mentions a download | N46 |
| n42 | the source opens a file for writing | N47 |
| n43 | a non-candidate strategy is accepted | none |
| n44 | candidates C4 and C5 swap their names (their counts are equal on the fixtures) | N48 |
| n45 | the last report row is dropped (N12 then fails by a KeyError, a crash) | N12, N13 |

### Y: predicted failures, `config.m5n.yaml` against `tests/unit/test_config_m5n.py`

| Mutation | The break | Predicted failures (tests/unit/test_config_m5n.py) |
|---|---|---|
| y01 | the mode is testnet | C2 |
| y02 | the stop-loss is enabled | C3 |
| y03 | the stop-loss and the take-profit are enabled | C3 |
| y04 | the stop-loss and the trailing stop are enabled | C3 |
| y05 | Telegram is enabled | C4 |
| y06 | the log file is enabled | C4 |
| y07 | a comment names an api_key | C5 |
| y08 | the mode line ends in a carriage return | C6 |
| y09 | ETHUSDT is disabled | C7 |
| y10 | BTCUSDT decides on 4h | C7 |
| y11 | the window starts on 2017-08-18 | C8 |
| y12 | the window ends on 2024-01-02 | C8 |
| y13 | the fee is 0.075 | C9 |
| y14 | the slippage is 0.10 | C10 |
| y15 | the stop slippage is 1.00 | C10 |
| y16 | the data directory is the testnet one | C11 |
| y17 | the filters are testnet's | C11 |
| y18 | the strategy is the live SMA crossover | C12 |
| y19 | the strategy is not registered | C12 |
| y20 | the initial balance is 5000 (asserted nowhere) | none |
| y21 | the placeholder sizing fraction is 0.05 (asserted nowhere) | none |
| y22 | the mode is not a mode (the loader refuses the file) | C1, C2, C3, C4, C7, C8, C9, C10, C11, C12 |

### The test key (every code the tables use)

The codes are the tests of each file in collection order, B1 to B26, G1 to G42, S1 to S89, N1 to N49 and C1 to C12, and the specs carry the full node-id suffix.

| Code | Test |
|---|---|
| B1 | `TestDonchianHigh::test_it_is_the_highest_high_of_the_prior_bars` |
| B2 | `TestDonchianHigh::test_the_current_bar_is_not_in_its_own_window` |
| B3 | `TestDonchianHigh::test_the_first_period_values_are_nan_and_the_next_is_not` |
| B4 | `TestDonchianHigh::test_a_window_holding_a_nan_gives_nan` |
| B5 | `TestDonchianHigh::test_a_period_of_one_is_the_previous_high` |
| B6 | `TestDonchianHigh::test_the_input_is_not_mutated_and_the_index_and_dtype_are_kept` |
| B7 | `TestDonchianHigh::test_integer_input_gives_floats` |
| B8 | `TestDonchianHigh::test_a_period_below_one_is_refused` |
| B10 | `TestMomentum::test_it_is_the_series_minus_itself_period_bars_earlier` |
| B11 | `TestMomentum::test_a_period_of_one_is_the_first_difference` |
| B12 | `TestMomentum::test_a_flat_series_has_zero_momentum_and_a_falling_one_negative` |
| B13 | `TestMomentum::test_a_nan_input_gives_nan_where_it_is_read` |
| B14 | `TestMomentum::test_the_input_is_not_mutated_and_the_name_and_dtype_are_set` |
| B15 | `TestMomentum::test_a_period_below_one_is_refused` |
| B16 | `TestKeltnerUpper::test_a_constant_range_gives_the_close_plus_two_ranges` |
| B17 | `TestKeltnerUpper::test_the_first_value_lands_at_the_longer_of_the_two_warm_ups` |
| B18 | `TestKeltnerUpper::test_a_flat_market_has_a_band_equal_to_the_ema` |
| B19 | `TestKeltnerUpper::test_a_breakout_bar_is_worked_from_the_wilder_atr_and_the_ema` |
| B20 | `TestKeltnerUpper::test_it_is_the_existing_ema_plus_the_multiple_of_the_existing_atr` |
| B21 | `TestKeltnerUpper::test_the_input_is_not_mutated_and_the_name_and_index_are_set` |
| B22 | `TestKeltnerUpper::test_a_period_below_one_or_a_multiplier_not_above_zero_is_refused` |
| B24 | `TestKeltnerUpper::test_it_takes_no_volume` |
| B25 | `TestTheModuleReadsNoVolume::test_no_function_here_has_a_volume_parameter` |
| B26 | `TestTheModuleReadsNoVolume::test_the_three_functions_are_exported_from_the_package` |
| C1 | `TestItEnablesNothingLive::test_it_loads_under_the_real_config_model` |
| C2 | `TestItEnablesNothingLive::test_the_mode_is_backtest` |
| C3 | `TestItEnablesNothingLive::test_no_protective_order_is_enabled` |
| C4 | `TestItEnablesNothingLive::test_no_notification_and_no_log_file` |
| C5 | `TestItEnablesNothingLive::test_it_carries_no_secret` |
| C6 | `TestItEnablesNothingLive::test_the_file_is_lf_only` |
| C7 | `TestThePairsAndTheWindow::test_the_pairs_are_btcusdt_and_ethusdt_daily_and_enabled` |
| C8 | `TestThePairsAndTheWindow::test_the_window_is_the_in_sample_span_ending_at_the_boundary` |
| C9 | `TestThePairsAndTheWindow::test_the_fee_is_ten_basis_points_per_side_as_a_decimal` |
| C10 | `TestThePairsAndTheWindow::test_the_slippage_figures_are_the_shipped_ones` |
| C11 | `TestThePairsAndTheWindow::test_the_data_directory_is_the_mainnet_archive` |
| C12 | `TestTheStrategyIsACandidate::test_it_names_one_of_the_six` |
| G1 | `TestTheWidths::test_they_equal_the_stores_interval_widths` |
| G2 | `TestGapFreeTail::test_consecutive_bars_give_the_last_rows[4h]` |
| G3 | `TestGapFreeTail::test_consecutive_bars_give_the_last_rows[1d]` |
| G4 | `TestGapFreeTail::test_exactly_the_rows_asked_for_are_enough[4h]` |
| G5 | `TestGapFreeTail::test_exactly_the_rows_asked_for_are_enough[1d]` |
| G6 | `TestGapFreeTail::test_fewer_rows_than_asked_for_give_none[4h]` |
| G7 | `TestGapFreeTail::test_fewer_rows_than_asked_for_give_none[1d]` |
| G8 | `TestGapFreeTail::test_a_missing_bar_inside_the_tail_gives_none[4h]` |
| G9 | `TestGapFreeTail::test_a_missing_bar_inside_the_tail_gives_none[1d]` |
| G10 | `TestGapFreeTail::test_a_missing_bar_before_the_tail_gives_the_tail[4h]` |
| G11 | `TestGapFreeTail::test_a_missing_bar_before_the_tail_gives_the_tail[1d]` |
| G12 | `TestGapFreeTail::test_a_gap_exactly_at_the_tails_first_row_is_inside_it[4h]` |
| G13 | `TestGapFreeTail::test_a_gap_exactly_at_the_tails_first_row_is_inside_it[1d]` |
| G14 | `TestGapFreeTail::test_one_row_is_always_gap_free[4h]` |
| G15 | `TestGapFreeTail::test_one_row_is_always_gap_free[1d]` |
| G16 | `TestGapFreeTail::test_a_repeated_open_time_is_a_gap[4h]` |
| G17 | `TestGapFreeTail::test_a_repeated_open_time_is_a_gap[1d]` |
| G18 | `TestGapFreeTail::test_an_out_of_order_row_is_a_gap[4h]` |
| G19 | `TestGapFreeTail::test_an_out_of_order_row_is_a_gap[1d]` |
| G20 | `TestGapFreeTail::test_the_input_is_not_mutated[4h]` |
| G21 | `TestGapFreeTail::test_the_input_is_not_mutated[1d]` |
| G22 | `TestGapFreeTail::test_zero_bars_is_refused[4h]` |
| G23 | `TestGapFreeTail::test_zero_bars_is_refused[1d]` |
| G24 | `TestTheWidthIsThatOfTheTimeframe::test_four_hour_bars_are_consecutive_in_a_4h_frame_and_gaps_in_a_1d_frame` |
| G25 | `TestTheWidthIsThatOfTheTimeframe::test_daily_bars_are_consecutive_in_a_1d_frame_and_gaps_in_a_4h_frame` |
| G26 | `TestTheWidthIsThatOfTheTimeframe::test_another_timeframe_is_refused[1m]` |
| G27 | `TestTheWidthIsThatOfTheTimeframe::test_another_timeframe_is_refused[1h]` |
| G28 | `TestTheWidthIsThatOfTheTimeframe::test_another_timeframe_is_refused[1w]` |
| G29 | `TestTheWidthIsThatOfTheTimeframe::test_another_timeframe_is_refused[]` |
| G30 | `TestTheWidthIsThatOfTheTimeframe::test_another_timeframe_is_refused_even_for_a_frame_too_short_to_have_a_gap` |
| G31 | `TestGapFreeRun::test_no_gap_gives_the_whole_frame[4h]` |
| G32 | `TestGapFreeRun::test_no_gap_gives_the_whole_frame[1d]` |
| G33 | `TestGapFreeRun::test_the_run_starts_after_the_last_gap[4h]` |
| G34 | `TestGapFreeRun::test_the_run_starts_after_the_last_gap[1d]` |
| G35 | `TestGapFreeRun::test_a_last_row_that_follows_a_gap_is_a_run_of_one[4h]` |
| G36 | `TestGapFreeRun::test_a_last_row_that_follows_a_gap_is_a_run_of_one[1d]` |
| G37 | `TestGapFreeRun::test_an_empty_or_one_row_frame_is_returned_as_it_is[4h]` |
| G38 | `TestGapFreeRun::test_an_empty_or_one_row_frame_is_returned_as_it_is[1d]` |
| G39 | `TestGapFreeRun::test_a_repeated_open_time_ends_the_run_before_it[4h]` |
| G40 | `TestGapFreeRun::test_a_repeated_open_time_ends_the_run_before_it[1d]` |
| G41 | `TestGapFreeRun::test_the_input_is_not_mutated[4h]` |
| G42 | `TestGapFreeRun::test_the_input_is_not_mutated[1d]` |
| N1 | `TestTheCounts::test_a_pair_without_a_gap_counts_the_hand_worked_events[C1-expected0]` |
| N2 | `TestTheCounts::test_a_pair_without_a_gap_counts_the_hand_worked_events[C2-expected1]` |
| N3 | `TestTheCounts::test_a_pair_without_a_gap_counts_the_hand_worked_events[C3-expected2]` |
| N4 | `TestTheCounts::test_a_pair_without_a_gap_counts_the_hand_worked_events[C4-expected3]` |
| N6 | `TestTheCounts::test_a_pair_without_a_gap_counts_the_hand_worked_events[C6-expected5]` |
| N7 | `TestTheCounts::test_a_missing_bar_suppresses_the_events_whose_window_holds_it[C1-expected0]` |
| N8 | `TestTheCounts::test_a_missing_bar_suppresses_the_events_whose_window_holds_it[C2-expected1]` |
| N10 | `TestTheCounts::test_a_missing_bar_suppresses_the_events_whose_window_holds_it[C4-expected3]` |
| N11 | `TestTheCounts::test_a_missing_bar_suppresses_the_events_whose_window_holds_it[C5-expected4]` |
| N12 | `TestTheCounts::test_a_missing_bar_suppresses_the_events_whose_window_holds_it[C6-expected5]` |
| N13 | `TestTheCounts::test_every_candidate_and_pair_has_a_row` |
| N14 | `TestTheCounts::test_the_events_are_the_ungated_events_less_the_suppressed_plus_the_gated_only` |
| N15 | `TestTheSeriesFacts::test_a_series_without_a_gap_has_no_missing_slots` |
| N16 | `TestTheSeriesFacts::test_a_missing_bar_is_one_missing_slot_and_one_gap_run` |
| N17 | `TestTheSeriesFacts::test_an_empty_series_has_nothing` |
| N18 | `TestTheSeriesFacts::test_a_missing_last_bar_counts_as_a_missing_slot` |
| N19 | `TestWhatIsPrinted::test_counts_only_no_price_no_time_and_no_return` |
| N20 | `TestWhatIsPrinted::test_it_says_the_counts_are_upper_bounds_on_trades` |
| N23 | `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[args0]` |
| N24 | `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[args1]` |
| N25 | `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[args2]` |
| N26 | `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[args3]` |
| N27 | `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[args4]` |
| N28 | `TestTheWindow::test_the_window_may_narrow` |
| N30 | `TestTheWindow::test_load_series_refuses_a_window_past_the_boundary` |
| N31 | `TestTheWindow::test_a_month_at_or_after_the_boundary_is_never_opened` |
| N32 | `TestWhenTheStoreCannotBeRead::test_an_absent_store_is_exit_one` |
| N33 | `TestWhenTheStoreCannotBeRead::test_a_month_that_no_longer_matches_its_manifest_is_exit_one` |
| N34 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[BTCUSDT-C1-donchian_1d_20-1d]` |
| N35 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[BTCUSDT-C2-donchian_1d_55-1d]` |
| N36 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[BTCUSDT-C3-sma_cross_1d_50_200-1d]` |
| N37 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[BTCUSDT-C4-donchian_4h_20-4h]` |
| N39 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[BTCUSDT-C6-tsmom_1d_90-1d]` |
| N40 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[ETHUSDT-C1-donchian_1d_20-1d]` |
| N41 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[ETHUSDT-C2-donchian_1d_55-1d]` |
| N43 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[ETHUSDT-C4-donchian_4h_20-4h]` |
| N44 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[ETHUSDT-C5-keltner_4h_20_2-4h]` |
| N45 | `TestTrimmingTheViewChangesNothing::test_the_counts_equal_those_of_the_whole_prefix[ETHUSDT-C6-tsmom_1d_90-1d]` |
| N46 | `TestTheScriptIsReadOnlyAndOffline::test_it_reads_through_the_store_and_has_no_fetcher` |
| N47 | `TestTheScriptIsReadOnlyAndOffline::test_it_opens_nothing_for_writing` |
| N48 | `TestTheScriptIsReadOnlyAndOffline::test_the_candidates_are_the_six_in_r_dys_order` |
| N49 | `TestTheScriptIsReadOnlyAndOffline::test_the_window_constants_are_the_committed_ones` |
| S2 | `TestTheSixAreRegisteredAndIndependent::test_they_are_listed_once_imported_and_the_registry_does_not_import_them` |
| S3 | `TestTheSixAreRegisteredAndIndependent::test_the_warmup_is_the_window_the_edge_reads[donchian_1d_20-22]` |
| S4 | `TestTheSixAreRegisteredAndIndependent::test_the_warmup_is_the_window_the_edge_reads[donchian_1d_55-57]` |
| S5 | `TestTheSixAreRegisteredAndIndependent::test_the_warmup_is_the_window_the_edge_reads[sma_cross_1d_50_200-201]` |
| S6 | `TestTheSixAreRegisteredAndIndependent::test_the_warmup_is_the_window_the_edge_reads[donchian_4h_20-22]` |
| S7 | `TestTheSixAreRegisteredAndIndependent::test_the_warmup_is_the_window_the_edge_reads[keltner_4h_20_2-22]` |
| S8 | `TestTheSixAreRegisteredAndIndependent::test_the_warmup_is_the_window_the_edge_reads[tsmom_1d_90-92]` |
| S9 | `TestTheSixAreRegisteredAndIndependent::test_gap_enforcement_defaults_on_and_must_be_a_bool` |
| S10 | `TestDonchian::test_a_close_above_the_prior_highs_fires_on_that_bar[donchian_1d_20-1d-20]` |
| S11 | `TestDonchian::test_a_close_above_the_prior_highs_fires_on_that_bar[donchian_1d_55-1d-55]` |
| S12 | `TestDonchian::test_a_close_above_the_prior_highs_fires_on_that_bar[donchian_4h_20-4h-20]` |
| S13 | `TestDonchian::test_a_close_equal_to_the_highest_high_does_not[donchian_1d_20-1d-20]` |
| S14 | `TestDonchian::test_a_close_equal_to_the_highest_high_does_not[donchian_1d_55-1d-55]` |
| S15 | `TestDonchian::test_a_close_equal_to_the_highest_high_does_not[donchian_4h_20-4h-20]` |
| S16 | `TestDonchian::test_one_tick_above_does[donchian_1d_20-1d-20]` |
| S17 | `TestDonchian::test_one_tick_above_does[donchian_1d_55-1d-55]` |
| S18 | `TestDonchian::test_one_tick_above_does[donchian_4h_20-4h-20]` |
| S19 | `TestDonchian::test_a_close_below_does_not[donchian_1d_20-1d-20]` |
| S20 | `TestDonchian::test_a_close_below_does_not[donchian_1d_55-1d-55]` |
| S21 | `TestDonchian::test_a_close_below_does_not[donchian_4h_20-4h-20]` |
| S22 | `TestDonchian::test_a_run_of_new_highs_signals_once_not_on_every_bar[donchian_1d_20-1d-20]` |
| S23 | `TestDonchian::test_a_run_of_new_highs_signals_once_not_on_every_bar[donchian_1d_55-1d-55]` |
| S24 | `TestDonchian::test_a_run_of_new_highs_signals_once_not_on_every_bar[donchian_4h_20-4h-20]` |
| S25 | `TestDonchian::test_a_previous_close_equal_to_its_threshold_counts_as_not_above[donchian_1d_20-1d-20]` |
| S26 | `TestDonchian::test_a_previous_close_equal_to_its_threshold_counts_as_not_above[donchian_1d_55-1d-55]` |
| S27 | `TestDonchian::test_a_previous_close_equal_to_its_threshold_counts_as_not_above[donchian_4h_20-4h-20]` |
| S28 | `TestDonchian::test_it_fires_on_the_crossing_bar_and_on_no_other[donchian_1d_20-1d-20]` |
| S29 | `TestDonchian::test_it_fires_on_the_crossing_bar_and_on_no_other[donchian_1d_55-1d-55]` |
| S30 | `TestDonchian::test_it_fires_on_the_crossing_bar_and_on_no_other[donchian_4h_20-4h-20]` |
| S31 | `TestDonchian::test_fewer_rows_than_the_window_give_no_signal[donchian_1d_20-1d-20]` |
| S32 | `TestDonchian::test_fewer_rows_than_the_window_give_no_signal[donchian_1d_55-1d-55]` |
| S33 | `TestDonchian::test_fewer_rows_than_the_window_give_no_signal[donchian_4h_20-4h-20]` |
| S34 | `TestDonchian::test_a_missing_bar_inside_the_window_gives_no_signal_until_the_window_is_clean[donchian_1d_20-1d-20]` |
| S35 | `TestDonchian::test_a_missing_bar_inside_the_window_gives_no_signal_until_the_window_is_clean[donchian_1d_55-1d-55]` |
| S36 | `TestDonchian::test_a_missing_bar_inside_the_window_gives_no_signal_until_the_window_is_clean[donchian_4h_20-4h-20]` |
| S37 | `TestDonchian::test_a_missing_bar_before_the_window_does_not_matter[donchian_1d_20-1d-20]` |
| S38 | `TestDonchian::test_a_missing_bar_before_the_window_does_not_matter[donchian_1d_55-1d-55]` |
| S39 | `TestDonchian::test_a_missing_bar_before_the_window_does_not_matter[donchian_4h_20-4h-20]` |
| S40 | `TestDonchian::test_the_volume_column_changes_nothing[donchian_1d_20-1d-20]` |
| S41 | `TestDonchian::test_the_volume_column_changes_nothing[donchian_1d_55-1d-55]` |
| S42 | `TestDonchian::test_the_volume_column_changes_nothing[donchian_4h_20-4h-20]` |
| S43 | `TestDonchian::test_the_signal_carries_the_pair_the_candle_price_and_the_close_time[BTCUSDT-donchian_1d_20-1d-20]` |
| S44 | `TestDonchian::test_the_signal_carries_the_pair_the_candle_price_and_the_close_time[BTCUSDT-donchian_1d_55-1d-55]` |
| S45 | `TestDonchian::test_the_signal_carries_the_pair_the_candle_price_and_the_close_time[BTCUSDT-donchian_4h_20-4h-20]` |
| S46 | `TestDonchian::test_the_signal_carries_the_pair_the_candle_price_and_the_close_time[ETHUSDT-donchian_1d_20-1d-20]` |
| S47 | `TestDonchian::test_the_signal_carries_the_pair_the_candle_price_and_the_close_time[ETHUSDT-donchian_1d_55-1d-55]` |
| S48 | `TestDonchian::test_the_signal_carries_the_pair_the_candle_price_and_the_close_time[ETHUSDT-donchian_4h_20-4h-20]` |
| S49 | `TestDonchian::test_a_candle_of_another_timeframe_is_refused[donchian_1d_20-1d-20]` |
| S50 | `TestDonchian::test_a_candle_of_another_timeframe_is_refused[donchian_1d_55-1d-55]` |
| S51 | `TestDonchian::test_a_candle_of_another_timeframe_is_refused[donchian_4h_20-4h-20]` |
| S52 | `TestDonchian::test_a_frame_with_no_high_column_is_a_data_error[donchian_1d_20-1d-20]` |
| S53 | `TestDonchian::test_a_frame_with_no_high_column_is_a_data_error[donchian_1d_55-1d-55]` |
| S54 | `TestDonchian::test_a_frame_with_no_high_column_is_a_data_error[donchian_4h_20-4h-20]` |
| S55 | `TestSmaCross::test_the_fast_average_crossing_above_the_slow_fires_on_that_bar` |
| S56 | `TestSmaCross::test_equal_averages_on_both_bars_do_not_fire` |
| S57 | `TestSmaCross::test_a_fast_average_already_above_does_not_fire_again` |
| S58 | `TestSmaCross::test_a_fast_average_below_and_staying_below_does_not_fire` |
| S59 | `TestSmaCross::test_it_fires_on_the_crossing_bar_and_on_no_other` |
| S60 | `TestSmaCross::test_fewer_than_slow_plus_one_rows_give_no_signal` |
| S61 | `TestSmaCross::test_a_missing_bar_inside_the_window_gives_no_signal` |
| S62 | `TestSmaCross::test_a_missing_bar_before_the_window_does_not_matter` |
| S63 | `TestSmaCross::test_both_pairs_and_the_volume_column[BTCUSDT]` |
| S64 | `TestSmaCross::test_both_pairs_and_the_volume_column[ETHUSDT]` |
| S65 | `TestSmaCross::test_a_4h_candle_is_refused` |
| S66 | `TestTsmom::test_momentum_turning_from_zero_to_positive_fires` |
| S67 | `TestTsmom::test_momentum_turning_from_negative_to_positive_fires` |
| S68 | `TestTsmom::test_a_close_equal_to_the_close_90_bars_earlier_does_not_fire` |
| S69 | `TestTsmom::test_momentum_already_positive_does_not_fire_again` |
| S70 | `TestTsmom::test_negative_momentum_does_not_fire` |
| S71 | `TestTsmom::test_it_fires_on_the_crossing_bar_and_on_no_other` |
| S72 | `TestTsmom::test_fewer_than_lookback_plus_two_rows_give_no_signal` |
| S73 | `TestTsmom::test_a_missing_bar_inside_the_window_gives_no_signal` |
| S74 | `TestTsmom::test_a_missing_bar_before_the_window_does_not_matter` |
| S75 | `TestTsmom::test_both_pairs_and_the_volume_column[BTCUSDT]` |
| S76 | `TestTsmom::test_both_pairs_and_the_volume_column[ETHUSDT]` |
| S77 | `TestKeltner::test_a_close_above_the_band_fires_with_the_hand_worked_band` |
| S78 | `TestKeltner::test_the_band_sits_between_a_close_that_fails_and_one_that_passes` |
| S79 | `TestKeltner::test_a_close_inside_the_band_does_not_fire` |
| S80 | `TestKeltner::test_a_close_already_above_does_not_fire_again` |
| S81 | `TestKeltner::test_it_fires_on_the_crossing_bar_and_on_no_other` |
| S82 | `TestKeltner::test_a_run_of_21_bars_has_no_previous_band_so_no_signal` |
| S83 | `TestKeltner::test_a_run_of_22_bars_is_enough` |
| S84 | `TestKeltner::test_a_gap_leaves_a_short_run_and_no_signal_until_it_is_long_enough` |
| S85 | `TestKeltner::test_after_a_gap_the_band_is_the_one_the_run_alone_would_give` |
| S86 | `TestKeltner::test_both_pairs_and_the_volume_column[BTCUSDT]` |
| S87 | `TestKeltner::test_both_pairs_and_the_volume_column[ETHUSDT]` |
| S88 | `TestKeltner::test_a_frame_with_no_low_column_is_a_data_error` |
| S89 | `TestKeltner::test_a_1d_candle_is_refused` |

## 85. M5n N3: the mutation survey of the N3 tests, scored against section 84 (P142 C15, R-T)

An observation log, so this section only adds. The five surveys ran as section 84 describes, in detached worktrees outside the repository at `6e416a2` (the commit that carries section 84), one per spec, starting at `2026-10-24T18:57:40Z` by the machine's UTC clock, each running only the mutated files' own tests, with the harness of section 80 unchanged (`survey.py` and `p116_hook.py`, SHA-256 as quoted there). Every baseline was green (B 26 passed, G 42, S 89, N 49, Y 12), the import location of `trading_bot` and `tests` was printed inside the worktree before any result, every restore was SHA-equal, and the worktrees were removed afterwards (`git worktree list` shows the main worktree only). Two things differ from the plan and are described below: the N survey **halted at `n15`** (a FEWER) and was resumed after the diagnosis, and its trimming tests were then changed by `f911ef0` and the four mutations they serve re-run. Nothing here decides anything about S4.

### Totals

On the first pass over the 157 mutations, **154 MATCH, 2 MORE and 1 FEWER**; after the diagnosis of the FEWER, the corrected test and a re-run of `n15` on the final bytes, **155 MATCH and 2 MORE, 0 FEWER**. Predicted failures 579; observed 588, the difference being the nine of the two MORE (`s15` three, `c04` six).

| Survey | Mutated against | Mutations | Predicted failures | Observed | First pass MATCH / MORE / FEWER | MATCH at the end |
|---|---|---|---|---|---|---|
| B | `indicators/breakout.py` against `test_indicators_breakout.py` | 25 | 47 | 47 | 25 / 0 / 0 | 25 |
| G | `strategies/m5n/gaps.py` against `test_m5n_gaps.py` | 20 | 98 | 98 | 20 / 0 / 0 | 20 |
| S | the candidates against `test_m5n_strategies.py` | 45 | 282 | 291 | 43 / 2 / 0 | 43 |
| N | `scripts/n3_entry_counts.py` against `test_n3_entry_counts.py` | 45 | 123 | 123 | 44 / 0 / 1 | 45 |
| Y | `config.m5n.yaml` against `test_config_m5n.py` | 22 | 29 | 29 | 22 / 0 / 0 | 22 |

**The declared abstentions held exactly.** Section 84 named ten tests that no mutation in the tables would fail, with a reason for each: B9, B23, S1, N5, N9, N21, N22, N29, N38 and N42. Across the 157 mutations the tests that never failed are those ten and no others. **The 20 mutations predicted to fail nothing failed nothing.** That includes `s12` and the exact-equality test S85, which section 84 named as the likeliest to disagree: a 22-row recursive window gave the same band to the last bit.

**One more test is killed by a crash and by nothing else, which section 84 predicted and counted.** C1 (the file loads under the real model) fails only under `y22`, by the loader's `ValidationError`, which `M5i-115` classes as a crash and not a kill. So by that rule 11 of the 218 tests are not killed by an assertion under any mutation: the ten above and C1.

**Three more failures are crashes and not kills, and only two of them were declared.** `n45` (N12, by a `KeyError`) and `y22` (ten tests, by the loader) were predicted as crashes. **`n14` (N15 and N16) and `n31` (N28) were predicted as failures and fail by a `KeyError` as well**: the test helper that parses the printed series rows matches non-negative integers, and these two mutations print a negative missing-slot count (for example -305 and -1), so the row is not found. The harness counts them, and the predictions were right as sets and wrong as to type. N15, N16 and N28 are still killed by assertion, by `n11`, `n12`, `n13` and `n26`.

### The three misses, diagnosed

* **`s15` (the gated window one row long): MORE, 38 observed against 35.** The three extra are S52 to S54, the Donchian tests for a frame with no `high` column. Their frames hold exactly `period + 2` rows, so with a window of `period + 3` the gated reading returns no window and `evaluate`, which is where the column is read and refused, is never reached: no `DataError`, and `pytest.raises` fails. Section 84 listed S28 to S30 and S34 to S36 as sparing and did not trace the data-error tests through the same fixtures. A reach error; the extra kills are real coverage.
* **`c04` (the SMA window `SLOW` and not `SLOW + 1`): MORE, 7 observed against 1.** Predicted: S5 (the warm-up). Observed: S5 and also S55, S59, S61, S62, S63 and S64, every SMA test that expects a signal. A 200-row window holds one `SMA(200)` value, so the previous bar's is `NaN`, `last_two` returns nothing, and the candidate **never fires**. Section 84 reasoned the opposite ("behaviourally equal") and was wrong in the direction that matters least: the warm-up property is pinned behaviourally as well as by S5, and `crossed_above` needing a previous slow average is what pins it. REASONED, then MEASURED.
* **`n15` (the script's `_strategy` builds the candidate without the gap flag): FEWER, 5 observed against 10, and the survey HALTED.** The missing kills were N40, N41, N43, N44 and N45, the ETHUSDT trimming tests. Diagnosis, before anything was resumed: those tests compare the script's counts with `prefix_events`, and `prefix_events` built its strategies through `n3._strategy`, the function the mutation changes; both sides lost the flag together and agreed. It is the oracle sharing the seam under test. The survey was resumed with `n16` to `n45` on the unchanged tests (`survey_n2.json`, 30 mutations, all MATCH), then `f911ef0` made the helper build through the registry (no assertion changed), and **`n15`, `n18`, `n19` and `n20`, the four mutations whose killers include the trimming tests, were re-run at `f911ef0`: all four MATCH, `n15` at 10 observed against 10 predicted**. The full bare gate was green on that commit (4916 passed, 1 skipped).

### What the survey leaves unpinned, and does not fix

Section 84's twenty "fails nothing" mutations are each a property no test holds, and the survey confirmed every one. Seven are equivalent or redundant (`m05`, `k07`, `s13`, `n08`, `n10`, `n16`, `n17`); thirteen are real gaps that a test could close: `m06` (momentum's index), `s11` (the timeframe metadata), `s12` (a recursive window as the last 22 rows), `d09` (the `donchian_high` metadata of the previous bar), `k05` (a close exactly on the Keltner band), `n23` (the candle behind the signal), `n30` (row order), `n32` and `n37` (`--start`), `n39` (the exception base class), `n43` (the candidate type check), `y20` and `y21` (the initial balance and the placeholder sizing fraction). None of them is needed by N3 or N4, and none is closed here.

### Every mutation

#### B: `indicators/breakout.py` against `test_indicators_breakout.py`

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| b01 | the Donchian window includes the current bar (shift 0) | 6 | 6 | MATCH |
| b02 | the Donchian window takes the minimum, not the maximum | 4 | 4 | MATCH |
| b03 | the Donchian window accepts a partial window | 3 | 3 | MATCH |
| b04 | the Donchian series is named without its period | 1 | 1 | MATCH |
| b05 | the Donchian index is replaced by a range | 1 | 1 | MATCH |
| b06 | the Donchian period is not checked | 1 | 1 | MATCH |
| m01 | the momentum lag is one bar short | 4 | 4 | MATCH |
| m02 | the momentum sign is reversed | 4 | 4 | MATCH |
| m03 | the momentum series is named without its period | 1 | 1 | MATCH |
| m04 | the momentum period is not checked | 1 | 1 | MATCH |
| m05 | momentum is pandas' diff (an equivalent mutation) | 0 | 0 | MATCH |
| m06 | the momentum index is replaced by a range (its index is asserted nowhere) | 0 | 0 | MATCH |
| k01 | the Keltner EMA period is 19 | 1 | 1 | MATCH |
| k02 | the Keltner ATR period is 19 | 1 | 1 | MATCH |
| k03 | the Keltner multiplier is 3 | 1 | 1 | MATCH |
| k04 | the Keltner high and low are swapped | 3 | 3 | MATCH |
| k05 | a close equal to the Keltner band signals (the band is never equal in the fixtures) | 2 | 2 | MATCH |
| k06 | the Keltner entry is level-triggered | 2 | 2 | MATCH |
| k07 | the Keltner low is the close | 0 | 0 | MATCH |
| k08 | the Keltner window is the ATR period + 1 rows | 1 | 1 | MATCH |
| k09 | the Keltner index is replaced by a range | 2 | 2 | MATCH |
| k10 | the band carries a constant offset | 4 | 4 | MATCH |
| v01 | momentum gains a volume parameter | 1 | 1 | MATCH |
| v02 | keltner_upper gains a volume parameter | 2 | 2 | MATCH |
| e01 | momentum is dropped from __all__ | 1 | 1 | MATCH |

#### G: `strategies/m5n/gaps.py` against `test_m5n_gaps.py`

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| g01 | the 4h width is one millisecond long | 9 | 9 | MATCH |
| g02 | the 1d width is one millisecond long | 9 | 9 | MATCH |
| g03 | the two widths are swapped | 17 | 17 | MATCH |
| g04 | zero bars is not refused | 2 | 2 | MATCH |
| g05 | exactly the rows asked for are too few | 4 | 4 | MATCH |
| g06 | the tail is one row too long | 8 | 8 | MATCH |
| g07 | any consecutive pair makes a tail gap-free | 10 | 10 | MATCH |
| g08 | a step of at most one width is consecutive | 3 | 3 | MATCH |
| g09 | a short frame is not checked for its timeframe | 1 | 1 | MATCH |
| g10 | the run starts at the row before the last gap | 6 | 6 | MATCH |
| g11 | the run starts after the first gap | 2 | 2 | MATCH |
| g12 | a frame without a gap loses its first row | 2 | 2 | MATCH |
| g13 | the run is read from the spaced pairs, not the broken ones | 8 | 8 | MATCH |
| g14 | a repeated open time counts as spaced in the run | 2 | 2 | MATCH |
| g15 | an hourly frame is a decision timeframe | 3 | 3 | MATCH |
| g16 | the refusal does not say a decision timeframe | 4 | 4 | MATCH |
| g17 | the tail writes into its input | 2 | 2 | MATCH |
| g18 | the run writes into its input | 2 | 2 | MATCH |
| g19 | too few rows are not refused | 2 | 2 | MATCH |
| g20 | a frame of one row loses it | 2 | 2 | MATCH |

#### S: the candidates against `test_m5n_strategies.py`

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| s01 | enforce_gaps is not checked to be a bool | 1 | 1 | MATCH |
| s02 | the enforce_gaps attribute is always on | 6 | 6 | MATCH |
| s03 | the warm-up is one bar short of the window | 6 | 6 | MATCH |
| s04 | a candle of another timeframe is accepted | 5 | 5 | MATCH |
| s05 | the refusal names the candle's timeframe as the candidate's | 2 | 2 | MATCH |
| s06 | a condition that is false still signals | 24 | 24 | MATCH |
| s07 | the timestamp is the bar's open time | 6 | 6 | MATCH |
| s08 | the price is the candle's low | 9 | 9 | MATCH |
| s09 | the action is CLOSE | 6 | 6 | MATCH |
| s10 | the strategy metadata carries the timeframe | 6 | 6 | MATCH |
| s11 | the timeframe metadata carries the name (asserted nowhere) | 0 | 0 | MATCH |
| s12 | a recursive window is the last window_bars rows | 0 | 0 | MATCH |
| s13 | the ungated window is the whole frame | 0 | 0 | MATCH |
| s14 | the gated window is one row short | 38 | 38 | MATCH |
| s15 | the gated window is one row long | 35 | 38 | MORE (see the diagnosis) |
| s16 | the missing-column message drops the repr quotes | 4 | 4 | MATCH |
| s17 | the signal's strength is one half | 6 | 6 | MATCH |
| s18 | the live registry's source mentions the research package | 1 | 1 | MATCH |
| d01 | the Donchian window is period + 1 rows | 33 | 33 | MATCH |
| d02 | a close equal to the highest high signals | 3 | 3 | MATCH |
| d03 | a previous close equal to its threshold counts as above | 3 | 3 | MATCH |
| d04 | the Donchian entry is level-triggered | 6 | 6 | MATCH |
| d05 | the Donchian threshold is built from the closes | 15 | 15 | MATCH |
| d06 | donchian_1d_55 looks back 50 bars | 4 | 4 | MATCH |
| d07 | donchian_1d_20 looks back 15 bars | 4 | 4 | MATCH |
| d08 | donchian_4h_20 looks back 15 bars | 4 | 4 | MATCH |
| d09 | the donchian_high metadata is the previous bar's (equal in the fixtures) | 0 | 0 | MATCH |
| c01 | the fast average is a 49-bar one | 1 | 1 | MATCH |
| c02 | the slow average is a 199-bar one | 3 | 3 | MATCH |
| c03 | the cross is read the wrong way round | 6 | 6 | MATCH |
| c04 | the SMA window is the slow period, not one more | 1 | 7 | MORE (see the diagnosis) |
| c05 | the fast_sma metadata is the previous bar's | 1 | 1 | MATCH |
| t01 | the momentum lookback is 89 bars | 2 | 2 | MATCH |
| t02 | momentum must rise above 1 | 8 | 8 | MATCH |
| t03 | momentum must rise from below -1 | 6 | 6 | MATCH |
| t04 | the momentum metadata is the previous bar's | 1 | 1 | MATCH |
| t05 | the prev_momentum metadata is the current bar's | 2 | 2 | MATCH |
| k01 | the Keltner EMA period is 19 | 2 | 2 | MATCH |
| k02 | the Keltner ATR period is 19 | 4 | 4 | MATCH |
| k03 | the Keltner multiplier is 3 | 8 | 8 | MATCH |
| k04 | the Keltner high and low are swapped | 3 | 3 | MATCH |
| k05 | a close equal to the Keltner band signals (the band is never equal in the fixtures) | 0 | 0 | MATCH |
| k06 | the Keltner entry is level-triggered | 2 | 2 | MATCH |
| k07 | the Keltner low is the close | 4 | 4 | MATCH |
| k08 | the Keltner window is the ATR period + 1 rows | 1 | 1 | MATCH |

#### N: `scripts/n3_entry_counts.py` against `test_n3_entry_counts.py`

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| n01 | a start before the window is accepted | 1 | 1 | MATCH |
| n02 | an end after the window is accepted | 3 | 3 | MATCH |
| n03 | an empty or reversed window is accepted | 2 | 2 | MATCH |
| n04 | the refusal does not name R-DT | 1 | 1 | MATCH |
| n05 | the window ends on 2024-01-02 | 4 | 4 | MATCH |
| n06 | the window starts on 2017-08-16 | 2 | 2 | MATCH |
| n07 | load_series does not check the window | 1 | 1 | MATCH |
| n08 | a served bar outside the window is not refused | 0 | 0 | MATCH |
| n09 | an empty series reports one bar | 1 | 1 | MATCH |
| n10 | the slots are rounded down (the grid is aligned in every fixture) | 0 | 0 | MATCH |
| n11 | the missing slots are the slots plus the bars | 5 | 5 | MATCH |
| n12 | the gap runs count the consecutive steps | 5 | 5 | MATCH |
| n13 | the bars are one more than stored | 5 | 5 | MATCH |
| n14 | the slots use the daily width | 2 | 2 | MATCH; crash: KeyError |
| n15 | the candidate is built without the gap flag | 10 | 10 | FEWER on the first run, then MATCH (see the diagnosis) |
| n16 | every bar is evaluated, warm-up included | 0 | 0 | MATCH |
| n17 | every candidate is handed the whole prefix | 0 | 0 | MATCH |
| n18 | the view is one row longer than the window | 2 | 2 | MATCH |
| n19 | the view is one row shorter than the window | 18 | 18 | MATCH |
| n20 | the events are the ungated ones | 11 | 11 | MATCH |
| n21 | the suppressions are the gated-only events | 6 | 6 | MATCH |
| n22 | the gated-only events are the suppressions | 6 | 6 | MATCH |
| n23 | the signal is built on the previous candle | 0 | 0 | MATCH |
| n24 | the report does not say upper bound | 1 | 1 | MATCH |
| n25 | the events and no-rule columns are swapped | 6 | 6 | MATCH |
| n26 | the slots and missing columns are swapped | 4 | 4 | MATCH |
| n27 | the report prints a decimal number | 1 | 1 | MATCH |
| n28 | the report prints a time of day | 1 | 1 | MATCH |
| n29 | a series with no bars is not refused | 1 | 1 | MATCH |
| n30 | the series rows run pair first (order is read nowhere) | 0 | 0 | MATCH |
| n31 | a narrowed window is read whole | 1 | 1 | MATCH; crash: KeyError |
| n32 | a narrowed start is read whole (--start is narrowed nowhere) | 0 | 0 | MATCH |
| n33 | a refused window exits 1 | 5 | 5 | MATCH |
| n34 | an unreadable store exits 2 | 2 | 2 | MATCH |
| n35 | the refusal message says denied | 5 | 5 | MATCH |
| n36 | the unreadable message says broken | 2 | 2 | MATCH |
| n37 | the default start is 2017-08-18 (--start is exercised nowhere) | 0 | 0 | MATCH |
| n38 | the default end is 2023-12-31 | 3 | 3 | MATCH |
| n39 | only a StoredFileError is caught by main | 0 | 0 | MATCH |
| n40 | the first two candidates swap their names | 1 | 1 | MATCH |
| n41 | the source mentions a download | 1 | 1 | MATCH |
| n42 | the source opens a file for writing | 1 | 1 | MATCH |
| n43 | a non-candidate strategy is accepted | 0 | 0 | MATCH |
| n44 | candidates C4 and C5 swap their names (their counts are equal on the fixtures) | 1 | 1 | MATCH |
| n45 | the last report row is dropped (N12 then fails by a KeyError, a crash) | 2 | 2 | MATCH; crash: KeyError |

#### Y: `config.m5n.yaml` against `test_config_m5n.py`

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| y01 | the mode is testnet | 1 | 1 | MATCH |
| y02 | the stop-loss is enabled | 1 | 1 | MATCH |
| y03 | the stop-loss and the take-profit are enabled | 1 | 1 | MATCH |
| y04 | the stop-loss and the trailing stop are enabled | 1 | 1 | MATCH |
| y05 | Telegram is enabled | 1 | 1 | MATCH |
| y06 | the log file is enabled | 1 | 1 | MATCH |
| y07 | a comment names an api_key | 1 | 1 | MATCH |
| y08 | the mode line ends in a carriage return | 1 | 1 | MATCH |
| y09 | ETHUSDT is disabled | 1 | 1 | MATCH |
| y10 | BTCUSDT decides on 4h | 1 | 1 | MATCH |
| y11 | the window starts on 2017-08-18 | 1 | 1 | MATCH |
| y12 | the window ends on 2024-01-02 | 1 | 1 | MATCH |
| y13 | the fee is 0.075 | 1 | 1 | MATCH |
| y14 | the slippage is 0.10 | 1 | 1 | MATCH |
| y15 | the stop slippage is 1.00 | 1 | 1 | MATCH |
| y16 | the data directory is the testnet one | 1 | 1 | MATCH |
| y17 | the filters are testnet's | 1 | 1 | MATCH |
| y18 | the strategy is the live SMA crossover | 1 | 1 | MATCH |
| y19 | the strategy is not registered | 1 | 1 | MATCH |
| y20 | the initial balance is 5000 (asserted nowhere) | 0 | 0 | MATCH |
| y21 | the placeholder sizing fraction is 0.05 (asserted nowhere) | 0 | 0 | MATCH |
| y22 | the mode is not a mode (the loader refuses the file) | 10 | 10 | MATCH; crash: ValidationError |

## 86. M5n N4a: P143's halts and the predictions for the D1 trail as a pure function, before any code (P143 C3, R-T, R-DQ, R-DT, R-EA)

An observation log, so this section only adds. P143 builds N4a: the D1 trail of R-EA (`docs/M5N_CHARTER_DRAFT.md` section 16) as a pure function. Under R-DQ clause (1) this section is committed BEFORE any code or test is drafted, in scratch or in the repository. Everything below is hand arithmetic from the figures stated in it. **No recorded bar was read, no backtest was run, and nothing here decides anything about S4.**

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| not on `m5n`, `git status` not clean, HEAD is not `70980c6` | `git branch --show-current`, `git status --porcelain`, `git rev-parse --short HEAD` | `m5n`, empty, `70980c6` (then `bf602b1` and `febf0b4` after the two charter commits) |
| a command would write under `deploy\45547f107715`, the rehearsal clone or the canonical store, or touch `config.yaml` or `config.s4.yaml` | every command in the plan | none: the module takes bars as an argument and has no store access |
| any venue request | the plan | none: three public documentation pages on `developers.binance.com` were read (charter section 3); no API endpoint, key or order was touched |
| any recorded bar is read | the plan | none: every fixture is a literal |
| any existing backtester, fill-model or risk module changes behaviour | the plan | none: the module is a new file that nothing imports, and `fill_model.py`, `engine.py`, `simulated_executor.py` and `risk/` are not edited |

### What is built

`src/trading_bot/backtesting/d1_trail.py`, a new module that nothing imports, with no I/O, no clock and no store: `trigger_price(peak, delta_bps)`, and `resolve_trail(*, entry_time, entry_price, delta_bps, stop_slippage_percent, bars)` returning a frozen `TrailOutcome` of `status` (`OPEN` or `EXITED`), `exit_minute`, `exit_price`, `gap` and `peak`. Money is `Decimal` throughout (`Candle` carries `Money`), the delta is an integer in basis points that the caller has already clamped and rounded (D1), the slippage is a whole percent in the fill model's convention (1.20 is 1.20%), and a `float`, a `bool` for the delta or a naive instant is refused. The rules are R-EA's, with the six readings of charter section 16: the trigger is `peak x (1 - delta / 10000)`; the peak starts at the entry fill price; the entry minute tests its low against the trigger from the fill price and counts neither its high nor its open; each later bar first tests its open against the trigger in force before it (at or below is a gap: the fill is the open less the slippage and the peak does not take that bar's high), otherwise takes its high into the peak and tests its low against the recomputed trigger (at or below triggers, at the trigger less the slippage). The first exit ends the walk. A path that ends first is `OPEN` with the peak so far; an empty path is `OPEN` with the fill price as the peak.

### The fixtures and the predictions

Minute 0 is `2023-01-01T00:00Z`, the fill is inside it, and the exit minute is the open time of the bar on which the exit happens. Bars are open / high / low / close. Slippage is a whole percent, so 1.00 multiplies by 0.99 and 1.20 by 0.988. A trigger is `peak x (1 - delta / 10000)`.

| Fixture | Fill, delta bps, slippage % | Bars (minute: O/H/L/C) | Trigger at the exit | Exit minute | Exit price | Gap flag | Peak at exit |
|---|---|---|---|---|---|---|---|
| A monotone rise, then a fall through the trigger | 100, 500, 1.00 | 0: 100/101/100/101; 1: 101/103/101/103; 2: 103/105/103/105; 3: 105/108/105/108; 4: 108/108/100/101; 5: 101/200/100/150 | 108 x 0.95 = 102.60 | 4 | 102.60 x 0.99 = **101.5740** | no | 108 |
| B a fall in the entry minute | 100, 500, 1.20 | 0: 100/100/94/95 | 100 x 0.95 = 95.00 | 0 | 95 x 0.988 = **93.860** | no | 100 |
| B2 the entry minute opens below the trigger and its high is ignored | 100, 500, 1.20 | 0: 90/101/90/100 | 95.00 (the high of 101 does not count) | 0 | 95 x 0.988 = **93.860** | no | 100 |
| C a high and a low in one minute that trigger only if the low came first | 100, 500, 1.00 | 0: 100/100/100/100; 1: 100/110/99/105 | 110 x 0.95 = 104.50 | 1 | 104.50 x 0.99 = **103.4550** | no | 110 |
| D a gap open below the trigger | 100, 500, 1.20 | 0: 100/104/100/104; 1: 104/106/104/106; 2: 99/100/98/98 | before minute 2: 106 x 0.95 = 100.70; the open 99 is below it | 2 | 99 x 0.988 = **97.812** (the open, not the trigger) | **yes** | 106 |
| D2 a gap bar's high does not enter the peak | 100, 500, 1.20 | as D, with minute 2: 99/120/98/110 | 100.70 | 2 | **97.812** | **yes** | 106 (not 120) |
| E a bar whose low touches the trigger exactly | 100, 500, 1.00 | 0: 100/100/100/100; 1: 100/100/95/96 | 100 x 0.95 = 95.00 | 1 | 95 x 0.99 = **94.0500** | no | 100 |
| E2 a bar that opens exactly at the trigger | 100, 500, 1.00 | 0: 100/100/100/100; 1: 95/96/95/95 | 95.00; the open equals it | 1 | 95 x 0.99 = **94.0500** | **yes** | 100 |
| E3 a low one cent above the trigger | 100, 500, 1.00 | 0: 100/100/100/100; 1: 100/100/95.01/96 | 95.00 | none: **OPEN** | none | no | 100 |
| F delta 10 | 1000, 10, 1.00 | 0: 1000/1000/999.5/999.8; 1: 999.8/1000.5/999/999.2 | 1000.5 x 0.999 = 999.4995 | 1 | 999.4995 x 0.99 = **989.504505** | no | 1000.5 |
| G delta 2000 | 50, 2000, 1.20 | 0: 50/52/49/51; 1: 51/60/51/59; 2: 59/59/47/48 | 60 x 0.80 = 48.00 | 2 | 48 x 0.988 = **47.424** | no | 60 |
| H the path ends with the position open | 100, 500, 1.00 | 0: 100/101/100/101; 1: 101/102/100.5/101 | 102 x 0.95 = 96.90 (the entry minute's high of 101 did not count) | none: **OPEN** | none | no | 102 |
| I an empty path | 100, 500, 1.00 | none | none | none: **OPEN** | none | no | 100 |
| J the peak never moves down | 100, 500, 1.00 | 0: 100/100/100/100; 1: 100/104/100/104; 2: 104/102/101/101 | 104 x 0.95 = 98.80 | none: **OPEN** | none | no | 104 |
| K the FAQ's own example | 45500, 700, 0 | 0: 45500/45500/45500/45500; 1: 45500/45500/42315/42400 | 45500 x 0.93 = **42315** | 1 | **42315** (slippage 0) | no | 45500 |

`trigger_price(Decimal(45500), 700)` is exactly 42315, and `trigger_price(Decimal(100), 10)` is 99.9 and `trigger_price(Decimal(100), 2000)` is 80.

**The gap flag is predicted set on exactly three fixtures: D, D2 and E2.** It is clear on B2 (the entry minute's open predates the fill, so it is never a gap), on C (the bar opened above the trigger in force before it and only the recomputed trigger caught the low), on E (a low at the trigger is not an open at it), and on every other fixture. D and D2 differ only in the gap bar's high, so they pin that the peak at exit is 106 and not 120; E and E2 give the same exit price and differ only in the flag.

**Refusals, each predicted to raise `ValueError` (a `TypeError` for a wrong type):** a delta that is zero, negative, 10000 or more, a `bool` or a `float`; a slippage that is negative, 100 or more, or a `float`; an entry price that is not positive or is a `float`; a naive entry time; a bar that is not a `1m` bar; bars whose open times do not strictly increase; a first bar whose minute does not contain the entry time. A path that continues after the exit (fixture A's minute 5, with a high of 200) changes nothing.

**Where a prediction is most likely to be wrong, named in advance:** C and D2, because each rests on the order of two operations inside one bar (the peak takes the high before the low is tested; the gap test uses the trigger before the high is applied), and the code's order is easy to write the other way round; and F, because its figure carries nine significant digits and the multiplication order of two `Decimal` factors can move a trailing digit.

> **ANNOTATED AT M5n P144 (C3, R-EB): THE MODULE THIS SECTION DESCRIBES NO LONGER COUNTS ONLY THE FILL PRICE IN THE ENTRY MINUTE.** The paragraph under *What is built*, *"the entry minute tests its low against the trigger from the fill price and counts neither its high nor its open"*, and two rows of the fixture table are true of the P143 module and false of the tree: **B2** (*"the high of 101 does not count"*, exit **93.860**, peak 100) and **H** (*"the entry minute's high of 101 did not count"*, a trigger of 96.90). Under R-EB (`docs/M5N_CHARTER_DRAFT.md` section 17) the entry minute's high counts toward the peak before that minute's low is tested, so B2 exits at 95.95 x 0.988 = **94.7986** with peak **101**, and H's trigger is 102 x 0.95 = 96.90 either way because its next bar's high is the larger (so H's outcome, OPEN with peak 102, is unchanged). Fixtures A, C, D, D2, E, E2, E3, F, G, I, J and K are unchanged. Sections 87 and 88 scored the P143 module and stay standing as that record; their `m10` (*"the entry minute's high counts toward the peak"*) now names what the module does. **What survives:** the trigger, the gap rule, the order of a bar's open, high and low, the slippage and the exit conventions of this section, and that the entry minute has no gap case.

### The commits that follow

The module and its tests (one file each, the gate run bare before each); the survey predictions, committed before the survey; the survey and its results; the counts. Findings begin at `M5n-076` and are gapless.

## 87. M5n N4a: the predictions for the mutation survey of the D1 trail tests, before it is run (P143 C6, R-T, R-DQ)

An observation log, so this section only adds. P143 proves that the 54 tests of `tests/unit/test_d1_trail.py` (C5) bite, against the module `src/trading_bot/backtesting/d1_trail.py` (C4). **This section is committed before the survey is run.** Everything here decides nothing about S4.

### The method

As sections 76, 80 and 84: the P117 harness (`survey.py` SHA-256 `cd2eb339e4fdf65d361482cccf0511ee3fd28a495fd90815cd5b3b357ed3202a`, `p116_hook.py` `febedd0bf7a8fee6a9fe3ac2462975d917ee5e31f5e1daf2acb57f7d378e2a8d`, both unchanged from section 80) in a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven before any result counts, an unmutated baseline predicted green, every mutation byte-exact with exactly one match asserted and every restore shown SHA-equal, the worktree removed afterwards. One spec, `survey_d.json` (SHA-256 `d38de9d7f989c5a3ce51680beccdeb02042366a40b6faead794e27a745fb56cc`), generated by the same program as the table below, so the two cannot differ. The test file was read for expressiveness and for whether each assertion looks at what a mutation moves before any prediction was written, and no test was run on a mutated tree. The harness counts every failing test, whatever it raised, and prints the exception types; a kill by `M5i-115` is a failure by `AssertionError` or `Failed`. A MORE is recorded and a FEWER halts the survey.

### Totals

**49 mutations and 112 predicted failures.**

**Mutations predicted to fail nothing, two.** `m13` (the entry minute's low must be strictly below the trigger) is unpinned: no fixture has the entry minute's low exactly at the trigger, so the equality reading of charter section 16 (reading 1) is held only for later bars (`m12` is killed). `m31` (`resolve_trail` skips its own delta check) is equivalent under these tests, because `trigger_price` repeats the check on the first bar and every test that passes a bad delta also passes a bar.

**Tests predicted to be killed by no mutation, six of 54, each declared in advance with its reason.**

| Test | Why no mutation in the table fails it |
|---|---|
| D8 (the bars after the exit change nothing) | the walk ends at a `return`, which no one-line mutation turns into a continuation; D9 holds the laziness |
| D14 (a low above the old trigger alone leaves the position open) | it is the contrapositive of D13, and it fails only under a mutation that makes the exit more eager at a level between the two triggers, which none here does |
| D19 (a low one cent above the trigger leaves the position open) | it fails only under a mutation that adds a tolerance to the comparison, which none here does (`m01` lowers the trigger and so leaves it open) |
| D23 (an empty path is open at the fill price) | `m37` returns the fill price as the peak, which on an empty path is the peak anyway |
| D50 (every figure is a Decimal) | `Money` coerces on construction, so no one-line mutation hands back another type |
| D54 (the same arguments give the same answer) | it fails only under non-determinism, which no mutation introduces |

**Failures that are crashes and not kills, predicted and counted** because the harness counts them: D44 under `m17` (a `TypeError` comparing a naive and an aware time), D12 under `m19` (a `ValueError` where the test expects none), D6 and D26 under `m21` (an `AttributeError` on a `float`), D6, D29 and D34 under `m22` (a `decimal.InvalidOperation` comparing a NaN; D30 under it is an assertion), D25 under `m25` (a `ValueError` where the test expects none), D39 under `m32` (a `TypeError`) and D9 under `m43` (a `StopIteration` from an exhausted iterator).

**Where a prediction is most likely to be wrong, named in advance.** `m22`, because the exception a NaN comparison raises, and the order in which two checks meet it, is the Python behaviour least certain from reading; `m08` and `m10`, because each is traced across several bars and one fixture (H, which was meant to pin the entry minute's high) is predicted NOT to fail under `m10` since its next bar's high is the larger; `m01`, with 12 predicted failures that depend on which fixtures sit within one basis point of an equality; and `m21`, whose first failure is a different exception from the one the test names.

### Predicted failures

| Mutation | The break | Predicted failures (tests/unit/test_d1_trail.py) |
|---|---|---|
| m01 | the trigger is one basis point lower than the delta says | D1, D2, D3, D7, D10, D11, D13, D17, D18, D20, D21, D25 |
| m02 | the slippage is charged in the seller's favour | D7, D10, D11, D13, D15, D16, D17, D18, D20, D21 |
| m03 | the slippage is not charged | D7, D10, D11, D13, D15, D16, D17, D18, D20, D21 |
| m04 | a gapped open is not recognised | D15, D16, D18 |
| m05 | an open exactly at the trigger is not a gap | D18 |
| m06 | a gapped open fills at the trigger and not at the open | D15, D16 |
| m07 | a gapped open is reported as no gap | D15, D16, D18 |
| m08 | the bar's high is applied before the gap test | D13, D16 |
| m09 | the peak never takes a high after the entry | D7, D9, D13, D15, D16, D20, D21, D22, D24 |
| m10 | the entry minute's high counts toward the peak | D11 |
| m11 | an exit in the entry minute is reported as a gap | D10, D11 |
| m12 | a later low must be strictly below the trigger | D17, D25 |
| m13 | the entry minute's low must be strictly below the trigger | none |
| m14 | a repeated minute is allowed | D42 |
| m15 | the strict increase of the minutes is not checked | D42, D43 |
| m16 | a bar that is not a 1m bar is accepted | D41 |
| m17 | a bar's naive open time is not checked | D44 |
| m18 | an entry time at the end of the first minute is inside it | D40 |
| m19 | an entry time at the start of the first minute is outside it | D12 |
| m20 | the entry time is not checked against the first bar | D40 |
| m21 | a float is not refused as a Decimal | D6, D26 |
| m22 | a non-finite Decimal is not refused | D6, D29, D30, D34 |
| m23 | an entry price that is not positive is not refused | D27, D28 |
| m24 | a slippage of 100 percent is accepted | D32 |
| m25 | a slippage of zero is refused | D25 |
| m26 | the slippage range is not checked | D31, D32, D33 |
| m27 | a bool is accepted as a delta | D5, D38 |
| m28 | the largest delta is 10000 | D4, D37 |
| m29 | a delta of zero is accepted | D4, D35 |
| m49 | a delta of minus ten is accepted | D4, D35, D36 |
| m30 | trigger_price does not check the delta | D4, D5 |
| m31 | resolve_trail does not check the delta (trigger_price repeats it) | none |
| m32 | a naive entry time is not checked | D39 |
| m33 | an exited outcome without its minute and price is accepted | D46 |
| m34 | an open outcome with a gap flag is accepted | D47 |
| m35 | the outcome is not frozen | D49 |
| m36 | the peak is a plain Decimal and not Money | D48 |
| m37 | an open outcome reports the fill price as its peak | D22, D24 |
| m38 | an exit in the entry minute is stamped with the entry time | D10 |
| m39 | an exit in the entry minute is priced at the low | D10, D11 |
| m40 | a later exit is priced at the low and not at the trigger | D7, D13, D20, D21 |
| m41 | a gapped bar's high enters the reported peak | D16 |
| m42 | the trigger is not recomputed after the high | D13, D20 |
| m43 | the bars are read to the end before the walk | D9 |
| m44 | the module imports logging | D51 |
| m45 | the docstring names a call to the wall clock | D52 |
| m46 | the module carries a comment | D53 |
| m47 | the first minute lasts two minutes | D40 |
| m48 | a missing minute is refused | D45 |

### The test key (every code the table uses)

The codes are the tests of `tests/unit/test_d1_trail.py` in collection order, D1 to D54, and the spec carries the full node-id suffix.

| Code | Test |
|---|---|
| D1 | `TestTheTriggerPrice::test_the_faqs_own_example` |
| D2 | `TestTheTriggerPrice::test_the_two_bounds_of_the_clamp` |
| D3 | `TestTheTriggerPrice::test_it_is_exact_to_the_last_digit` |
| D4 | `TestTheTriggerPrice::test_a_delta_that_cannot_make_a_trigger_is_refused` |
| D5 | `TestTheTriggerPrice::test_a_delta_that_is_not_an_int_is_refused` |
| D6 | `TestTheTriggerPrice::test_a_peak_that_is_a_float_or_not_positive_is_refused` |
| D7 | `TestAMonotoneRiseThenAFall::test_it_exits_through_the_trigger_of_the_last_peak` |
| D9 | `TestAMonotoneRiseThenAFall::test_the_walk_does_not_advance_the_iterator_past_the_exit` |
| D10 | `TestTheEntryMinute::test_a_fall_in_the_entry_minute_exits_at_the_trigger_from_the_fill` |
| D11 | `TestTheEntryMinute::test_an_entry_minute_that_opens_below_the_trigger_is_not_a_gap` |
| D12 | `TestTheEntryMinute::test_an_entry_time_on_the_minute_boundary_is_inside_that_minute` |
| D13 | `TestHighAndLowInOneMinute::test_a_new_peak_and_a_low_below_its_trigger_exits` |
| D15 | `TestAGapOpenBelowTheTrigger::test_the_fill_is_the_open_less_the_slippage_and_the_flag_is_set` |
| D16 | `TestAGapOpenBelowTheTrigger::test_the_gap_bars_high_does_not_enter_the_peak` |
| D17 | `TestTheTriggerExactly::test_a_low_that_touches_the_trigger_exits_and_is_not_a_gap` |
| D18 | `TestTheTriggerExactly::test_an_open_exactly_at_the_trigger_is_a_gap_at_the_same_price` |
| D20 | `TestTheTwoBoundsOfTheClamp::test_a_delta_of_ten_basis_points` |
| D21 | `TestTheTwoBoundsOfTheClamp::test_a_delta_of_two_thousand_basis_points` |
| D22 | `TestAPathThatEndsOpen::test_the_peak_is_the_highest_high_after_the_entry_minute` |
| D24 | `TestAPathThatEndsOpen::test_the_peak_never_moves_down` |
| D25 | `TestTheFaqsOwnExample::test_a_700_bips_trail_from_45500_exits_at_42315` |
| D26 | `TestRefusals::test_a_float_among_the_money_figures_is_a_type_error` |
| D27 | `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[0]` |
| D28 | `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[-1]` |
| D29 | `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[NaN]` |
| D30 | `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[Infinity]` |
| D31 | `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[-0.01]` |
| D32 | `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[100]` |
| D33 | `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[150]` |
| D34 | `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[NaN]` |
| D35 | `TestRefusals::test_a_delta_out_of_range_is_refused[0]` |
| D36 | `TestRefusals::test_a_delta_out_of_range_is_refused[-5]` |
| D37 | `TestRefusals::test_a_delta_out_of_range_is_refused[10000]` |
| D38 | `TestRefusals::test_a_delta_that_is_a_bool_is_refused` |
| D39 | `TestRefusals::test_a_naive_entry_time_is_refused` |
| D40 | `TestRefusals::test_an_entry_time_outside_the_first_bars_minute_is_refused` |
| D41 | `TestRefusals::test_a_bar_that_is_not_a_one_minute_bar_is_refused` |
| D42 | `TestRefusals::test_a_repeated_minute_is_refused` |
| D43 | `TestRefusals::test_a_minute_out_of_order_is_refused` |
| D44 | `TestRefusals::test_a_bar_with_a_naive_open_time_is_refused` |
| D45 | `TestRefusals::test_a_missing_minute_is_not_detected_here` |
| D46 | `TestTheOutcomeShape::test_an_exited_outcome_needs_its_minute_and_price` |
| D47 | `TestTheOutcomeShape::test_an_open_outcome_carries_neither_and_no_gap` |
| D48 | `TestTheOutcomeShape::test_a_float_price_is_refused_by_the_money_guard` |
| D49 | `TestTheOutcomeShape::test_the_outcome_is_frozen` |
| D51 | `TestThePurity::test_the_module_imports_no_clock_no_store_and_no_io` |
| D52 | `TestThePurity::test_it_reads_no_wall_clock` |
| D53 | `TestThePurity::test_it_has_no_comment` |

## 88. M5n N4a: the mutation survey of the D1 trail tests, scored against section 87 (P143 C7, R-T)

An observation log, so this section only adds. The survey ran as section 87 describes, in one detached worktree outside the repository at `5d4512a` (the commit that carries section 87), starting at `2026-10-24T21:27:38Z` by the machine's UTC clock, with the harness of section 80 unchanged (`survey.py` and `p116_hook.py`, SHA-256 as quoted there). The baseline was green (54 passed), the import location of `trading_bot` and `tests` was printed inside the worktree before any result, every restore was SHA-equal, and the worktree was removed afterwards (`git worktree list` shows the main worktree only). The survey was not halted. Nothing here decides anything about S4.

### Totals

**49 mutations: 48 MATCH, 1 MORE, 0 FEWER. Predicted failures 112, observed 113**, the one more being `m09`'s. The two mutations predicted to fail nothing (`m13`, `m31`) failed nothing.

**The declared abstentions held, bar one.** Section 87 named six tests that no mutation would fail. Five never failed under any of the 49: D8, D14, D19, D23 and D54. The sixth, **D50 (every figure is a Decimal), failed under `m09`**, which is the MORE.

**Eight more tests are killed only by crashes**, never by an assertion, so by `M5i-115` they are not killed: D6, D12, D26, D29, D34, D39, D44 and D45. Seven were predicted as crashes (D6, D26, D29, D34 by `m21` and `m22`; D12 by `m19`; D39 by `m32`; D44 by `m17`), and one was not: **D45 (a missing minute is not detected here) fails under `m48` by the `ValueError` the mutation makes it raise**, which is a "must not raise" test failing by letting the exception escape, the shape `CLAUDE.md` names; section 87 predicted the failure and not its type. D9 is killed by `m43` with a `StopIteration` and also by `m09` by an assertion, and D25 is killed by `m25` with a `ValueError` and also by `m01` and `m12` by assertions, so both stand. So 13 of the 54 tests are killed by no assertion under any mutation here: the five that never fail and the eight above.

### The miss, diagnosed

* **`m09` (the peak never takes a high after the entry): MORE, 10 observed against 9.** The extra is D50. Section 87 said no one-line mutation hands back another type, and that is true of a figure; it missed that D50 asserts `type(out.exit_price) is Decimal` on fixture A's outcome, and under `m09` that walk never exits, so `exit_price` is `None` and the assertion fails. A reach error: the test is downstream of any mutation that changes whether fixture A exits.

### What the harness's type line did not say

The harness prints an `exception types` line per mutation by scanning for names ending in `Error`, `Failed` or `Exception`. It therefore reported **nothing beyond `AssertionError` for `m22`**, whose three crashes are `decimal.InvalidOperation`, and nothing for `m43`, whose crash is `StopIteration`: neither name ends in a word it scans for. The crash column below was read from each mutation's own pytest output, not from that line. A crash that reads as an assertion is a false kill, the direction this file names as the cheaper one to catch, and it was caught only because section 87 had predicted the types.

### What the survey leaves unpinned, and does not fix

`m13` is the one real gap: no fixture has the entry minute's low exactly at the trigger. The five tests that never fail and the eight that only crash are each the contrapositive of a test that does bite, or a "raises" or "must not raise" test that no one-line mutation can make fail by an assertion. None is needed by N4b, and none is closed here.

### Every mutation

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| m01 | the trigger is one basis point lower than the delta says | 12 | 12 | MATCH |
| m02 | the slippage is charged in the seller's favour | 10 | 10 | MATCH |
| m03 | the slippage is not charged | 10 | 10 | MATCH |
| m04 | a gapped open is not recognised | 3 | 3 | MATCH |
| m05 | an open exactly at the trigger is not a gap | 1 | 1 | MATCH |
| m06 | a gapped open fills at the trigger and not at the open | 2 | 2 | MATCH |
| m07 | a gapped open is reported as no gap | 3 | 3 | MATCH |
| m08 | the bar's high is applied before the gap test | 2 | 2 | MATCH |
| m09 | the peak never takes a high after the entry | 9 | 10 | MORE (see the diagnosis) |
| m10 | the entry minute's high counts toward the peak | 1 | 1 | MATCH |
| m11 | an exit in the entry minute is reported as a gap | 2 | 2 | MATCH |
| m12 | a later low must be strictly below the trigger | 2 | 2 | MATCH |
| m13 | the entry minute's low must be strictly below the trigger | 0 | 0 | MATCH |
| m14 | a repeated minute is allowed | 1 | 1 | MATCH |
| m15 | the strict increase of the minutes is not checked | 2 | 2 | MATCH |
| m16 | a bar that is not a 1m bar is accepted | 1 | 1 | MATCH |
| m17 | a bar's naive open time is not checked | 1 | 1 | MATCH; crash: TypeError |
| m18 | an entry time at the end of the first minute is inside it | 1 | 1 | MATCH |
| m19 | an entry time at the start of the first minute is outside it | 1 | 1 | MATCH; crash: ValueError |
| m20 | the entry time is not checked against the first bar | 1 | 1 | MATCH |
| m21 | a float is not refused as a Decimal | 2 | 2 | MATCH; crash: AttributeError |
| m22 | a non-finite Decimal is not refused | 4 | 4 | MATCH; crash: decimal.InvalidOperation |
| m23 | an entry price that is not positive is not refused | 2 | 2 | MATCH |
| m24 | a slippage of 100 percent is accepted | 1 | 1 | MATCH |
| m25 | a slippage of zero is refused | 1 | 1 | MATCH; crash: ValueError |
| m26 | the slippage range is not checked | 3 | 3 | MATCH |
| m27 | a bool is accepted as a delta | 2 | 2 | MATCH |
| m28 | the largest delta is 10000 | 2 | 2 | MATCH |
| m29 | a delta of zero is accepted | 2 | 2 | MATCH |
| m49 | a delta of minus ten is accepted | 3 | 3 | MATCH |
| m30 | trigger_price does not check the delta | 2 | 2 | MATCH |
| m31 | resolve_trail does not check the delta (trigger_price repeats it) | 0 | 0 | MATCH |
| m32 | a naive entry time is not checked | 1 | 1 | MATCH; crash: TypeError |
| m33 | an exited outcome without its minute and price is accepted | 1 | 1 | MATCH |
| m34 | an open outcome with a gap flag is accepted | 1 | 1 | MATCH |
| m35 | the outcome is not frozen | 1 | 1 | MATCH |
| m36 | the peak is a plain Decimal and not Money | 1 | 1 | MATCH |
| m37 | an open outcome reports the fill price as its peak | 2 | 2 | MATCH |
| m38 | an exit in the entry minute is stamped with the entry time | 1 | 1 | MATCH |
| m39 | an exit in the entry minute is priced at the low | 2 | 2 | MATCH |
| m40 | a later exit is priced at the low and not at the trigger | 4 | 4 | MATCH |
| m41 | a gapped bar's high enters the reported peak | 1 | 1 | MATCH |
| m42 | the trigger is not recomputed after the high | 2 | 2 | MATCH |
| m43 | the bars are read to the end before the walk | 1 | 1 | MATCH; crash: StopIteration |
| m44 | the module imports logging | 1 | 1 | MATCH |
| m45 | the docstring names a call to the wall clock | 1 | 1 | MATCH |
| m46 | the module carries a comment | 1 | 1 | MATCH |
| m47 | the first minute lasts two minutes | 1 | 1 | MATCH |
| m48 | a missing minute is refused | 1 | 1 | MATCH; crash: ValueError |

## 89. M5n N4b: P144's halts, the step 2 answers and the predictions for the counts-only run, before any code (P144 C2, R-T, R-DQ, R-DT-3d, R-EB)

An observation log, so this section only adds. P144 builds N4b: the D1 trail (`resolve_trail`, section 86) wired into the backtester replay, and one counts-only run of the six candidates over `[2017-08-17, 2024-01-01)`. Under R-DQ clause (1) this section is committed BEFORE any code or test is drafted, in scratch or in the repository. **No recorded bar was read, no backtest was run, and nothing here decides anything about S4.** Every figure below is a hand estimate from the N3 counts of section 83 and from what the market did, remembered and not looked up; none was measured, and the ranges are wide for that reason.

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| not on `m5n`, `git status` not clean, HEAD is not `275ffaf` | `git branch --show-current`, `git status --porcelain`, `git rev-parse --short HEAD` | `m5n`, empty, `275ffaf` (then `944a705` after the charter commit) |
| a command would write under `deploy\45547f107715`, the rehearsal clone or the canonical store, or touch `config.yaml` or `config.s4.yaml` | every command in the plan | none: the count run opens nothing for writing; `HistoricalStore` only reads. `config.yaml` is blob `99b0edd`, `config.s4.yaml` SHA-256 `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594`, neither touched |
| any venue request | the plan | none: `ReplayClient` refuses every call but `get_klines`, and the run never builds a real client |
| any bar at or after `2024-01-01T00:00:00Z` is read | the plan | none yet; the run's window end is the committed boundary and the store opens no month file at or after it, as `scripts/n3_entry_counts.py` does (section 83) |
| any existing strategy's backtest path changes behaviour | the plan | none by construction: the new executor is chosen only for a strategy that declares the D1 exit, and a regression test, in a later commit, pins that every other strategy takes `SimulatedExecutor` |
| any output, log or file the count run produces contains a price, P&L, return, equity, balance or realised figure | the plan | the script prints a fixed schema of integers and passes every line through the scan before it prints (a later commit) |
| the count run would write a run record or trade file | `backtesting/engine.py` | it cannot: `write_run` is the only writer of `run.json` and `trades.csv`, and `BacktestSystem.run` returns an in-memory `BacktestResult` and writes nothing. The script does not call `write_run` |

### Step 2: the answers the prompt asked for, read-only

**P143's six readings of R-EA, each marked under R-EB**, are in `docs/M5N_CHARTER_DRAFT.md` section 17 (`944a705`): 1 complies, **2 is corrected** (the entry minute's high now counts toward the peak before that minute's low is tested), 3 complies, 4 complies, 5 complies (not an R-EB case, flagged), 6 complies.

**The entry tolerance `config.s4.yaml` uses** is `risk.max_entry_slippage: 0.001` (line 79, *"(exact) 0.1%, a FRACTION not a percent"*). It is also the `RiskConfig` default, so `config.m5n.yaml`, which does not set it, already inherits the same 0.001. The entry limit is therefore the signal-bar close x 1.001 under the existing `FOK` model.

**`config.m5n.yaml`'s risk values:** `position_sizing.method: fixed_fraction` with `fraction: 0.02` (a placeholder, per the file's own comment); `stop_loss`, `take_profit` and `trailing_stop` all `enabled: false`; `max_position_staleness_s: 259200.0`. Everything else is the default: `max_open_positions: 3`, `max_daily_loss_percent: 5.0`, `cooldown_minutes: 15` (which the simulation never starts). The backtest block: initial balance 10000, fee 0.10 percent, entry slippage 0.05 percent, stop slippage 1.20 percent. The two pairs are BTCUSDT and ETHUSDT, both on `1d`; the script changes the pair timeframes and the strategy per candidate in memory and edits no file.

**Whether the backtester can run with no run record, no trade file and no P&L log line: yes, so no HALT.** (a) `write_run` is the only writer of a run record or trade file, and `BacktestSystem.run` returns a `BacktestResult` in memory. (b) The `INFO` records that carry a balance, a price or a size (`Backtest ready ... free` and `IntentLogger`'s `risk_refused` and `intent_dispatched`) are emitted only at `INFO`, and a process that has not configured logging reports `WARNING` and above. The script configures none and attaches an in-memory handler to the root logger at `WARNING`, whose records the scan reads. (c) The `WARNING` records the executor can emit carry a symbol and no figure. (d) `_describe` computes metrics internally and the script prints none of them.

### What is built, and the decisions the executing session makes

* **The delta is computed where the signal is made.** `M5nStrategy.generate_signal` adds `trail_delta_bps` (an `int`) and `trail_clamp` (`"none"`, `"upper"` or `"lower"`) to the signal's metadata, from the Wilder ATR(20) of the gap-free run that ends at the decision bar (the R-DZ run, as for the recursive indicators), through `risk.rules._atr_to_decimal`, the named float-to-Decimal boundary: `floor(10000 x 3 x ATR / close)` clamped to `[10, 2000]`, close being the signal bar's. A signal is "fixed at signal time" because it is made then. A candidate that cannot form the ATR returns no signal; every candidate's window is at least 22 rows, so this is predicted never to happen, and it is pinned.
* **A strategy declares its exit.** `BaseStrategy.declares_d1_exit` is `False`; `M5nStrategy` sets it `True`. The engine chooses the executor from the registered strategy class: `D1Executor` for a declaring one, `SimulatedExecutor` for every other. The regression test pins that all the registry's strategies take the old path and that the old path's trade-log digest is unchanged.
* **`D1Executor` is a drop-in for `SimulatedExecutor`**: the same `dispatch` and `__call__` and `finish`, the same `trades`, `attempts` and `counts`, the same unchanged `RiskManager` and `Portfolio`. An approved entry fills on the next decision bar at the open plus the entry slippage if that is within the entry limit (the existing `fill_entry`, unchanged). The fill's instant is the open of that bar's first TRADED 1m minute (a minute with nonzero volume, section 80 and R-DV), the position's `stop_loss` is `fill x (1 - delta / 10000)` (what the unchanged `RiskManager` prices committed risk from), and `resolve_trail` walks the traded 1m minutes from there, read through `HistoricalStore.candles` and bounded at the window end. Because every candidate emits `BUY` and never `CLOSE`, the exit is a function of the path alone, so the walk is done once at fill time and the exit is **scheduled**, not discovered: a heap of exits keyed by the exit minute, booked at that minute's open plus one minute, in time order across both pairs, before any decision bar whose nominal end is at or after it is evaluated. A decision never sees an exit that is in its future.
* **A gap in the 1m path while a position is open** is skipped over: the walk reads the traded minutes it is given, so a fall inside the gap meets the gap rule at the next traded open, the worse exit (R-EB, section 17 reading 6).
* **The script** (`scripts/n4_trade_counts.py`) runs the six candidates, one backtest each over both pairs, and prints, per candidate and pair, the fixed schema of R-DT-3d and nothing else. **It prints entry outcomes beside the refusal counts** (filled, refused by the `FOK`, expired, unaffordable) because a trade count without them cannot be reconciled with the signal count; that is a reading of "refusal counts by stage" the owner may overrule, and it adds no figure of money. It prints refusal counts by `RefusalStage` and does not split `LIMIT_REFUSED` by rule.

### The definitions the predictions use

* **signals**: `BUY` signals the strategy emitted in the window, refused or not. **trades**: closed round trips. **OPEN at end**: filled and not exited when the path ends at `2024-01-01`. **clamp**: a signal whose raw delta fell outside `[10, 2000]`, counted per signal. **median delta**: the median of the signals' final (clamped) delta, in basis points.
* A signal is, in order, refused by the risk manager at some stage; or approved and queued; a queued entry then FILLS, is REFUSED by the `FOK`, EXPIRES (no next slot, or the data ended) or is UNAFFORDABLE. So **signals = refusals (all stages) + filled + `FOK`-refused + expired + unaffordable**, and **filled = trades + OPEN at end**.

### The predictions

Hand estimates. The signal count is the N3 event count of section 83; the backtest sees the same bars through a 1000-bar buffer, which the recursive indicators forget to well under any comparison's resolution, so **signals are predicted to equal the N3 counts within 2, and within 6 for C5**.

| Candidate | Pair | Signals (N3) | Trades (range) | OPEN at end | Upper clamps (range) | Median delta bps (range) | `FOK` refused | `LIMIT_REFUSED` |
|---|---|---|---|---|---|---|---|---|
| C1 `donchian_1d_20` | BTCUSDT | 104 | 46 (32 to 62) | 1 | 5 (1 to 12) | 1100 (900 to 1350) | 1 | 56 |
| C1 | ETHUSDT | 104 | 46 (32 to 62) | 1 | 18 (8 to 32) | 1450 (1150 to 1800) | 1 | 56 |
| C2 `donchian_1d_55` | BTCUSDT | 73 | 40 (28 to 52) | 1 | 3 (0 to 9) | 1100 (900 to 1400) | 1 | 31 |
| C2 | ETHUSDT | 68 | 38 (26 to 50) | 1 | 12 (4 to 22) | 1500 (1200 to 1850) | 1 | 28 |
| C3 `sma_cross_1d_50_200` | BTCUSDT | 6 | 6 (5 to 6) | 0 | 0 (0 to 1) | 1000 (750 to 1300) | 0 | 0 |
| C3 | ETHUSDT | 6 | 6 (5 to 6) | 0 | 0 (0 to 2) | 1350 (1000 to 1800) | 0 | 0 |
| C4 `donchian_4h_20` | BTCUSDT | 538 | 255 (190 to 330) | 0 | 0 (0 to 1) | 470 (370 to 600) | 5 | 278 |
| C4 | ETHUSDT | 546 | 255 (190 to 330) | 0 | 0 (0 to 1) | 620 (500 to 800) | 5 | 286 |
| C5 `keltner_4h_20_2` | BTCUSDT | 293 | 175 (120 to 225) | 0 | 0 (0 to 1) | 480 (380 to 620) | 3 | 115 |
| C5 | ETHUSDT | 291 | 175 (120 to 225) | 0 | 0 (0 to 1) | 640 (510 to 820) | 3 | 113 |
| C6 `tsmom_1d_90` | BTCUSDT | 45 | 41 (33 to 45) | 1 | 2 (0 to 6) | 1000 (800 to 1300) | 1 | 2 |
| C6 | ETHUSDT | 40 | 35 (28 to 40) | 1 | 4 (0 to 10) | 1350 (1050 to 1750) | 1 | 3 |

`LIMIT_REFUSED` is the arithmetic of the identity above with 0 expired: signals less trades, OPEN and `FOK` refusals. **Every other stage is predicted 0 in all twelve cells:** `UNKNOWN_PAIR`, `NO_REFERENCE_PRICE`, `NO_MARK_PRICE`, `POSITION_STALE`, `SIZE_NOT_TRADEABLE`, `UNAFFORDABLE`, `NOTHING_TO_CLOSE`, `UNSUPPORTED_ACTION`, and the three stages that need a stop to be enabled (`ATR_UNAVAILABLE`, `STOP_UNPLACEABLE`, `COMMITTED_RISK_UNKNOWN`). Expired entries are predicted 0 for the four 1d candidates and 0 to 2 per pair for C4 and C5 (an entry settled into one of the 17 missing 4h slots, or the last bar). Lower clamps are predicted 0 everywhere.

**By candidate, the totals that carry the prediction.** Trades: C1 92, C2 78, C3 12, C4 510, C5 350, C6 76 (all pairs). OPEN at end: 6 across the twelve cells (range 3 to 10), all from the 1d family; the 4h candidates are predicted flat at the end of 2023 and that is the least certain call here. Upper clamps: 1d candidates only, concentrated on ETHUSDT and in the late-2017 to early-2018 run and early 2021, where a 20-day ATR is over 6.67 percent of the close.

**Structural predictions, each near-certain.** Trades are at most the N3 bound in every cell and **strictly below it in ten of twelve**; C3 is predicted to meet its bound (6 and 6), because a golden cross while the previous position is still open cannot happen under a 3-ATR trail, so it is the one cell in which "below the bound" is not predicted. No clamp is a lower clamp. The scan passes and prints `CLEAN`. No halt fires. The run's wall time is predicted under 40 minutes in all and under 15 minutes for any one candidate.

**Where a prediction is most likely to be wrong, named in advance:**

* **The trade counts of C1, C2, C4 and C5**, because they rest on one number I have not measured, the share of time a 3-ATR trail leaves a pair long. I assumed 55 to 60 percent of the time for the 4h family and 45 to 50 percent for the 1d breakouts, and the predicted trades are the events not blocked by that. If the share is 30 percent the 4h trade counts are about 400 and the `LIMIT_REFUSED` counts about 130; if it is 80 percent they are about 180 and 360.
* **`LIMIT_REFUSED` in the 1d family may exceed the in-position arithmetic.** The unchanged risk manager prices committed risk from `Position.stop_loss`, the INITIAL stop, which is never trailed. A position that has gained several fold carries committed risk of about `2 percent x (mark / fill - 0.9)` of equity, and two such positions can reach the 5 percent daily-loss threshold in 2020 and 2021, refusing an entry of the other pair under the same stage name. The stage count cannot show it. I predict it fires in few or no signals; if `LIMIT_REFUSED` exceeds the identity by more than a handful in C1 or C2, this is the first suspect, and it would be an artefact of the placeholder sizing and not a property of the candidate.
* **The median deltas**, which are ATR-over-price levels I remember and did not compute; a factor of 1.3 either way is inside the stated ranges.
* **OPEN at end for the 4h candidates**, which turns on where a handful of late-December entries stand on the last bar.
* **The `FOK` refusals**, a rare event in a liquid pair that the early, thin USDT history may raise.

### The commits that follow

The code and its tests (the gate run bare before each, the order: the entry-minute fix and the m13 test, the survey harness fix, the strategy's delta and declaration, the executor, the engine selection, the script); the survey predictions, committed before the survey; the one count run; the scoring section; the survey results; the gate counts. Findings begin at `M5n-090` and are gapless; `M5n-090` is in the charter commit.

## 90. M5n N4b: the counts-only run of the six candidates, and section 89's predictions scored (P144 C10, R-T, R-DQ, R-DT-3d)

An observation log, so this section only adds. `scripts/n4_trade_counts.py` (`fbef8be`, with its tests) was run ONCE: `python scripts/n4_trade_counts.py`, no argument, on `m5n` with a clean tree at `fbef8be`, so the config is the committed `config.m5n.yaml` (SHA-256 `3b85f23b1ce531ce224fe2cbe6378b2b7b77e25be45c0f288df2ff06f594fe9d`), the store is `data/historical`, and the window is the committed `[2017-08-17, 2024-01-01)`. Standard output went to `scratch\p144\n4_counts_output.txt` and standard error to `n4_counts_stderr.txt`. It started at `2026-10-25T05:21:52Z` by the machine's UTC clock and ended at `05:27:13Z`: **5 min 21 s of wall time, exit 0, and standard error empty (0 bytes)**. Nothing was written under `deploy\45547f107715`, the rehearsal clone or the canonical store, `config.yaml` is still blob `99b0edd005ff5f452681fc554dcc2271d2e6687e` and `config.s4.yaml` still SHA-256 `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594`, no venue was asked for anything, and no bar at or after `2024-01-01T00:00:00Z` was read (the 1m path is bounded at the window end, pinned by `test_no_series_is_asked_for_past_the_window_end` and `test_a_trigger_after_the_window_end_is_never_read`). **Nothing here decides anything about S4.**

**The digests of the output.** The file as the shell wrote it, with the Windows line endings the redirection produced, has SHA-256 `feba211b4d6426f0f00d545182c28b34d3d1fb13494a6e69570da4d2ac978d6f`. The script's own last line, `output_sha256=51a92ebb6ebf662fe78c3bb87d89d62ab194edfad5ba2f39338d43e012d2c54a`, is the SHA-256 of every line before it joined with LF, and it was re-derived outside the script from the file with CRLF turned to LF and agrees. **The two differ only by the line endings**, and the output below is the LF form. **The scan's verdict is `CLEAN`: 50 output lines, each in the grammar, none with a forbidden word, a decimal point or an integer over 99,999, and 36 log records kept at WARNING and above, none flagged.** No run record and no trade file was written; `write_run` is never called.

### The output

```
N4b trade counts (R-DT-3d outputs only)
window [2017-08-17, 2024-01-01)
candidate C1 donchian_1d_20 (1d)
  run complete=yes problems=0
  BTCUSDT signals=104 trades=34 open_at_end=0 entries_filled=34 fok_refused=3 expired=2 unaffordable=0 clamp_upper=5 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=65 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT delta_bps n=104 p10=885 p25=980 p50=1289 p75=1591 p90=1806 min=613 max=2000
  ETHUSDT signals=104 trades=41 open_at_end=0 entries_filled=41 fok_refused=1 expired=0 unaffordable=0 clamp_upper=22 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=62 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT delta_bps n=104 p10=1067 p25=1400 p50=1627 p75=1926 p90=2000 min=759 max=2000
candidate C2 donchian_1d_55 (1d)
  run complete=yes problems=0
  BTCUSDT signals=73 trades=25 open_at_end=0 entries_filled=25 fok_refused=6 expired=2 unaffordable=0 clamp_upper=3 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=40 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT delta_bps n=73 p10=885 p25=1006 p50=1283 p75=1521 p90=1766 min=648 max=2000
  ETHUSDT signals=68 trades=28 open_at_end=0 entries_filled=28 fok_refused=2 expired=0 unaffordable=0 clamp_upper=10 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=38 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT delta_bps n=68 p10=1030 p25=1362 p50=1598 p75=1834 p90=2000 min=849 max=2000
candidate C3 sma_cross_1d_50_200 (1d)
  run complete=yes problems=0
  BTCUSDT signals=6 trades=6 open_at_end=0 entries_filled=6 fok_refused=0 expired=0 unaffordable=0 clamp_upper=0 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=0 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT delta_bps n=6 p10=883 p25=901 p50=980 p75=1557 p90=1815 min=883 max=1815
  ETHUSDT signals=6 trades=6 open_at_end=0 entries_filled=6 fok_refused=0 expired=0 unaffordable=0 clamp_upper=1 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=0 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT delta_bps n=6 p10=1165 p25=1350 p50=1517 p75=1924 p90=2000 min=1165 max=2000
candidate C4 donchian_4h_20 (4h)
  run complete=yes problems=0
  BTCUSDT signals=538 trades=216 open_at_end=0 entries_filled=216 fok_refused=4 expired=0 unaffordable=0 clamp_upper=3 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=318 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT delta_bps n=538 p10=308 p25=410 p50=557 p75=738 p90=994 min=153 max=2000
  ETHUSDT signals=546 trades=217 open_at_end=0 entries_filled=217 fok_refused=14 expired=3 unaffordable=0 clamp_upper=4 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=312 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT delta_bps n=546 p10=416 p25=542 p50=692 p75=872 p90=1169 min=208 max=2000
candidate C5 keltner_4h_20_2 (4h)
  run complete=yes problems=0
  BTCUSDT signals=293 trades=149 open_at_end=0 entries_filled=149 fok_refused=2 expired=0 unaffordable=0 clamp_upper=0 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=142 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT delta_bps n=293 p10=283 p25=405 p50=528 p75=696 p90=862 min=154 max=1615
  ETHUSDT signals=291 trades=148 open_at_end=0 entries_filled=148 fok_refused=9 expired=1 unaffordable=0 clamp_upper=0 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=133 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT delta_bps n=291 p10=394 p25=512 p50=670 p75=849 p90=1079 min=253 max=1866
candidate C6 tsmom_1d_90 (1d)
  run complete=yes problems=0
  BTCUSDT signals=45 trades=23 open_at_end=0 entries_filled=23 fok_refused=3 expired=0 unaffordable=0 clamp_upper=4 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=19 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT delta_bps n=45 p10=771 p25=872 p50=1243 p75=1540 p90=1939 min=679 max=2000
  ETHUSDT signals=40 trades=19 open_at_end=0 entries_filled=19 fok_refused=1 expired=0 unaffordable=0 clamp_upper=12 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=20 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT delta_bps n=40 p10=898 p25=1210 p50=1494 p75=2000 p90=2000 min=722 max=2000
scan verdict=CLEAN output_lines=50 log_records=36
output_sha256=51a92ebb6ebf662fe78c3bb87d89d62ab194edfad5ba2f39338d43e012d2c54a
```

### Section 89's predictions, scored

**(a) Structural predictions.** Signals equal the N3 entry-event counts of section 83 **exactly in all twelve cells** (predicted within 2, and within 6 for C5): 104/104, 73/68, 6/6, 538/546, 293/291 and 45/40. Trades are at most the N3 bound in every cell and **strictly below it in ten of twelve**, C3 meeting its bound in both pairs (6 and 6) as predicted. No clamp is a lower clamp. Every refusal stage but `limit_refused` is 0 in all twelve cells. The identity `signals = refusals + trades + OPEN + FOK-refused + expired + unaffordable` holds exactly in all twelve (for example BTCUSDT C1: 104 = 65 + 34 + 0 + 3 + 2). The scan passes. No halt fired. Wall time was 5 min 21 s in all, against a prediction of under 40 minutes and under 15 for any one candidate.

**(b) Per cell.** "Inside" means inside the range section 89 stated.

| Candidate | Pair | Trades predicted (range) | Observed | OPEN at end (pred / obs) | Upper clamps predicted (range) | Observed | Median delta predicted (range) | Observed |
|---|---|---|---|---|---|---|---|---|
| C1 | BTCUSDT | 46 (32 to 62) | 34 inside | 1 / 0 | 5 (1 to 12) | 5 inside | 1100 (900 to 1350) | 1289 inside |
| C1 | ETHUSDT | 46 (32 to 62) | 41 inside | 1 / 0 | 18 (8 to 32) | 22 inside | 1450 (1150 to 1800) | 1627 inside |
| C2 | BTCUSDT | 40 (28 to 52) | 25 **under the range** | 1 / 0 | 3 (0 to 9) | 3 inside | 1100 (900 to 1400) | 1283 inside |
| C2 | ETHUSDT | 38 (26 to 50) | 28 inside | 1 / 0 | 12 (4 to 22) | 10 inside | 1500 (1200 to 1850) | 1598 inside |
| C3 | BTCUSDT | 6 (5 to 6) | 6 inside | 0 / 0 | 0 (0 to 1) | 0 inside | 1000 (750 to 1300) | 980 inside |
| C3 | ETHUSDT | 6 (5 to 6) | 6 inside | 0 / 0 | 0 (0 to 2) | 1 inside | 1350 (1000 to 1800) | 1517 inside |
| C4 | BTCUSDT | 255 (190 to 330) | 216 inside | 0 / 0 | 0 (0 to 1) | 3 **over the range** | 470 (370 to 600) | 557 inside |
| C4 | ETHUSDT | 255 (190 to 330) | 217 inside | 0 / 0 | 0 (0 to 1) | 4 **over the range** | 620 (500 to 800) | 692 inside |
| C5 | BTCUSDT | 175 (120 to 225) | 149 inside | 0 / 0 | 0 (0 to 1) | 0 inside | 480 (380 to 620) | 528 inside |
| C5 | ETHUSDT | 175 (120 to 225) | 148 inside | 0 / 0 | 0 (0 to 1) | 0 inside | 640 (510 to 820) | 670 inside |
| C6 | BTCUSDT | 41 (33 to 45) | 23 **under the range** | 1 / 0 | 2 (0 to 6) | 4 inside | 1000 (800 to 1300) | 1243 inside |
| C6 | ETHUSDT | 35 (28 to 40) | 19 **under the range** | 1 / 0 | 4 (0 to 10) | 12 **over the range** | 1350 (1050 to 1750) | 1494 inside |

**Totals.** Trades were predicted at 1118 and observed at **912** (C1 75, C2 53, C3 12, C4 433, C5 297, C6 42, against 92, 78, 12, 510, 350 and 76). **Trades: 9 of 12 inside their range. Upper clamps: 9 of 12 inside. Median deltas: 12 of 12 inside, eleven of them above their estimate by 5% to 24% and C3 BTCUSDT 2% below.** OPEN at the end: **6 of 12 right, all six of them the predicted zeros**; the six predicted ones were all zero, and the total was predicted at 6 (3 to 10) and is **0**.

**(c) The entry outcomes and the stage count.** Predicted `FOK` refusals were 0 to 5 a cell and are 0 to 14: BTCUSDT 3, 6, 0, 4, 2, 3 and ETHUSDT 1, 2, 0, 14, 9, 1 for C1 to C6. Predicted expired entries were 0 for the 1d candidates and 0 to 2 for C4 and C5, and are **2 for C1 and C2 on BTCUSDT** (1d, where the archive series has no missing slot) and 3 for C4 and 1 for C5 on ETHUSDT. `limit_refused` follows from the identity above and is above its estimate in every cell where trades fell short of it.

### Diagnoses

None of these is a rerun: the script was run once, as P144 item 5 says. The one thing run after it is named in the last diagnosis.

* **The trades fell short of the estimate for the 1d candidates, and the cause is the same as the medians'.** The share of time a 3-ATR trail leaves a pair long, the number section 89 named as its likeliest error, was too small: eleven of the twelve median deltas are above their estimates (a 1d BTCUSDT breakout carries about 12.8% against the 11% assumed, an ETHUSDT one 16%), a wider trail holds longer, and a position held longer blocks more events (`limit_refused` 65 against 56). REASONED from the counts and the estimates; the share itself is not printed and was not measured.
* **No cell ended with a position open, where six were predicted.** Section 89 reasoned that late-2023 entries would still be in a rising market on the last bar. They were not: the deltas are set by the ATR AT the entry, and in the quiet autumn of 2023 they were small. **MEASURED once, by a diagnostic and not by the run:** for C3 the BTCUSDT position entered on 2023-10-31 exited by a touch on 2023-12-11 and the ETHUSDT one entered on 2023-11-22 exited by a touch on 2023-12-18, each before the last bar (2023-12-31). That the other ten cells ended flat for the same reason is REASONED and not looked at.
* **The 4h upper clamps (3 and 4, predicted 0 or 1) and C6's ETHUSDT clamps (12, predicted at most 10)** say the 20-bar ATR reaches 6.7% of the close more often than estimated: on the 4h series in the 2017 to 2018 spikes, on the 1d in the early 2021 run. REASONED; the dates were not printed.
* **The `FOK` refusals are far above the estimate on the 4h candidates (ETHUSDT C4 14, C5 9)** and the two expired entries on each of the 1d BTCUSDT candidates C1 and C2 are unexplained. Section 89 named the thin early USDT history as a reason for the former; the count cannot say which bars refused or expired. UNMEASURED.
* **`limit_refused` cannot be split.** It equals signals less trades, `FOK` refusals and expired entries in every cell, so no refusal beyond a position already being held is NEEDED to explain it, but the by-stage count cannot show whether any of the 65, 62, 40 and so on was the daily-loss limit pricing a not-yet-trailed stop (`M5n-091`). That stays REASONED. Splitting by rule is a refusal count outside R-DT-3d's list and was not printed.

> **ANNOTATED AT P145 (C7): *"That stays REASONED"* IS NO LONGER TRUE OF `M5n-091`, AND IT WAS TRUE OF N4b's RUN.** R-DT-3e puts the refusing rule's name in the counts, and section 94 prints them for the N5 run: `daily_loss_halt` refused 174 of 1,152 signals in 9 of 12 cells, with 3 net trades lost. **What survives:** this bullet's account of N4b, which printed no rule (the N4b rule counts are not recoverable, and the figure `limit_refused` is unchanged). REASONED, not measured: N4b's 2-percent-of-equity notional commits about 0.02 x (gain + delta) of equity to the same untrailed stop, which reaches the 5-percent threshold only after a gain of over 200 percent, so N4b's halt could fire on a rare run and not on the scale N5's does; and the REASONED attribution of each N5 halt to the committed term on the untrailed stop, which section 94 keeps as REASONED.
* **A diagnostic run after the count run printed dates and not counts.** To explain the zero OPEN count, `scratch\p144\diag_open.py` ran the C3 backtest in the same way and printed, for its twelve trades, the entry date, the exit instant, `touch` or `gap` and a gap flag, and the two last decision-bar dates. It contains no price, return, equity, balance or realised figure and it persisted nothing in the repository, but **it is an output the R-DT-3d list does not name, and the owner may rule on it.** It was not repeated.

### What these counts are, and are not

They are the number of times each rule, as ruled, said "enter" over the in-sample window and what the D1 trail, the entry limit and the unchanged risk manager did with it. **They are not a verdict on any candidate**: no return, equity or P&L was printed, and the simulation's own figures were kept in memory and discarded. The counts do not say whether a candidate is profitable; they say how many round trips each produced, which is the number a later gate has to work with. **C3 has 6 trades per pair in 6.4 years**, 12 in all.

## 91. M5n N4b: the predictions for the arming audit of the N4b code, before it is run (P144 C11, R-T, R-DQ)

An observation log, so this section only adds. P144 proves that the tests written for N4b bite: the 215 tests of `tests/unit/test_d1_trail.py`, `test_m5n_trail.py`, `test_d1_executor.py`, `test_backtest_d1.py` and `test_n4_trade_counts.py`, against the code of `d1_trail.py` (the R-EB entry minute only), `strategies/m5n/trail.py` and `base.py`, `strategies/base.py`, `d1_executor.py`, `engine.py` (`uses_d1_executor` and the executor choice) and `scripts/n4_trade_counts.py`. **This section is committed before the survey is run.** It decides nothing about S4.

### The method, and the harness that is new

The harness is the repository's `scripts/worktree_survey.py` with `scripts/survey_hook.py` (`92e63e3`, tested), which replaces the scratch harness of sections 76 to 88 and **fixes `M5n-088`**: the class of every failing test now comes from the live exception in a pytest hook and is printed beside it, so a crash named `decimal.InvalidOperation` or `StopIteration` is a crash and says so; a kill is an assertion, an unmet `pytest.raises`, `pytest.fail` or `SystemExit` by `mutation_survey.classify_failure`. The survey runs in one detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` is proven inside the worktree before any result counts, an unmutated baseline is predicted green (215 passed), every mutation is byte-exact with exactly one match, asserted both when the spec was generated and when it runs, every restore is shown SHA-equal, and the worktree is removed afterwards. The spec is `survey_n4.json` (SHA-256 `1de3cc4e5749a138921c6f7dc32789dbc9b03e4a13e76ffce5de9e2fef399c02`), generated by the same program as the table below, so the two cannot differ; the test list is the `pytest --collect-only` of the five files at `009b354` (215 node ids). A MORE is recorded and a FEWER halts the survey. No test was run on a mutated tree.

### Totals

**55 mutations and 174 predicted failures.** The predictions come from reading each test's fixture and assertion, not its name (`M5h`): the question for each was what the mutated line changes in the test's own world and whether anything in the test reads it.

**Mutations predicted to fail nothing, two.** `n08` (twenty rows pass the length guard) is equivalent: the indicator returns NaN on twenty rows and the NaN guard returns `None`. `n35` (the exits due by a bar's open are not booked first) is equivalent for every run this repository makes, because with one timeframe for every pair the previous callback's end-of-bar booking and the booking inside the entry settlement book the same exits; it would matter for mixed timeframes, which no candidate uses.

**Tests predicted to be killed by no mutation: 102 of 215.** By file: `test_d1_trail.py` 53 of 58 (the module was surveyed at P143 with 49 mutations, sections 87 and 88; this survey re-mutates only the entry-minute lines R-EB changed, five tests); `test_m5n_trail.py` 13 (the per-candidate window checks, the contrapositive of tests that do bite, the frame-unchanged test, the metadata-key test); `test_d1_executor.py` 7 (the three non-integer-delta cases that `n53` kills are counted as killed; the rest are the Dispatcher port check, the key-agreement test, determinism, the wall-clock grep and the recovered-gap, overlapping-positions and missing-slot tests, which no mutation here reaches); `test_backtest_d1.py` 2 (the two "run is complete and the cash identity holds" tests, which the simulated executor may also pass under `n38`); `test_n4_trade_counts.py` 27, most of them the scan's accept and refuse rows, which are guarded twice (the grammar and then the vocabulary or the integer bound), so removing either guard leaves the row refused by the other. **That double guard is why a one-line mutation of either cannot fail them, and it is declared here as an abstention and not as coverage.**

**Failures that are crashes and not kills, predicted and counted** because the harness counts every failing test: `n09` (both tests, a `ValueError` from the Decimal boundary where the test expects `None`), `n10` (the zero case, `decimal.DivisionByZero` where the test expects `ValueError`), `n12` (an `AttributeError` on `None`), `n38` (the two overlap tests, a `KeyError` on a trade that is not there, and the gap-with-a-fall test, a `ValueError` at its unpack), and `n43` and `n47` (the hash test, a `ValueError` at its unpack of an empty output). **Each is a test the mutation fails by a crash and not by an assertion, so by `M5i-115` it is not credited as a kill.**

**Where a prediction is most likely to be wrong, named in advance.**

* `n04`, because a third test (`test_the_distance_is_taken_from_the_signal_bars_close`) fails under round-half-up only if the fraction of its raw distance is at least a half, and I did not work that fraction; it is left out of the prediction.
* `n38`, the widest reach: 16 predicted of the tests that run `backtest_system`, with the two "complete and the cash identity holds" tests left out because the simulated executor may well pass them; a MORE there is the likely result.
* `n43` and `n47`, because they rest on what the script does when it is refused or cannot find its store: both are predicted to leave standard output empty, which makes `test_two_runs_print_the_same_bytes` and `test_the_output_has_no_decimal_point_and_no_money_word` PASS under them (an empty output is the same twice and has no decimal point), and `n47` rests on the survey's worktree not holding a `data/historical` directory.
* `n23`, because the two limit-refusal tests are predicted to fail by a different stage name (`POSITION_STALE` for `LIMIT_REFUSED`) when no position is ever stamped, which I derived from the risk manager's rule that an unstamped position is maximally stale and did not run.
* `n16`, where the backtest tests are predicted to pass because the same exits are booked a callback later with the same booking times; the executor tests are predicted to fail by the exits that are due inside the entry bar.
* `n27`, with 20 predicted failures, of which 14 are the stage-parametrised cases; a miscount there is one of the other six.

### Predicted failures

| Mutation | The break | Predicted failures | Tests |
|---|---|---|---|
| n01 | the entry minute's high is not part of the peak (R-EB reverted) | 5 | N11, N12, N14, N15, N99 |
| n02 | the entry minute's low must be strictly below the trigger | 2 | N13, N14 |
| n03 | the multiple is 2, not 3 | 10 | N59, N60, N61, N62, N63, N64, N65, N75, N76, N80 |
| n04 | the raw distance rounds half up instead of down | 2 | N60, N61 |
| n05 | a distance exactly at the lower bound is a clamp | 1 | N65 |
| n06 | a distance exactly at the upper bound is a clamp | 1 | N63 |
| n07 | a lower clamp is not reported as one | 4 | N66, N67, N77, N165 |
| n08 | twenty rows are enough for the ATR guard | 0 | none |
| n09 | a non-finite ATR is not refused | 2 | N69, N70 |
| n10 | a close of zero is not refused | 1 | N73 |
| n11 | the ATR reads the whole frame, not the gap-free run | 1 | N81 |
| n12 | a missing distance does not stop the signal | 1 | N82 |
| n13 | the signal always says the distance was not clamped | 2 | N165, N166 |
| n14 | the M5n candidates stop declaring the D1 exit | 8 | N89, N90, N91, N92, N93, N94, N165, N166 |
| n15 | every strategy declares the D1 exit | 4 | N95, N96, N149, N150 |
| n16 | the exits due by the end of the bar are booked only up to its open | 7 | N98, N99, N100, N101, N103, N104, N109 |
| n17 | an exit due exactly at the clock waits | 1 | N101 |
| n18 | an exit is booked at the open of its minute, not its end | 8 | N98, N99, N100, N101, N102, N104, N155, N156 |
| n19 | a zero-volume minute is walked as a trade | 2 | N112, N113 |
| n20 | a first traded minute at the next bar's open still fills | 1 | N113 |
| n21 | the initial stop sits twice the trail below the fill | 4 | N119, N98, N155, N156 |
| n22 | a stamped position is untrusted | 2 | N120, N106 |
| n23 | no position is ever stamped | 5 | N120, N121, N106, N159, N160 |
| n24 | a trail exit is reported as a CLOSE | 1 | N98 |
| n25 | the deltas are not kept | 3 | N122, N138, N167 |
| n26 | an upper clamp is counted as a lower one | 2 | N122, N166 |
| n27 | no refusal is tallied by stage | 20 | N123, N124, N125, N126, N127, N128, N129, N130, N131, N132, N133, N134, N135, N136, N122, N137, N138, N159, N160, N167 |
| n28 | a bool is accepted as the delta | 1 | N142 |
| n29 | an approved exit is ignored and not refused | 1 | N143 |
| n30 | a second entry replaces a pending one | 1 | N118 |
| n31 | finish books nothing | 1 | N108 |
| n32 | a gap in the decision bars is read the wrong way round | 2 | N111, N163 |
| n33 | a gapped exit is not flagged | 4 | N109, N155, N156, N163 |
| n34 | the reported trigger is the exit price | 3 | N98, N99, N109 |
| n35 | the exits due by the bar's open are not booked first | 0 | none |
| n36 | the 1m path is read past the window end | 2 | N107, N151 |
| n37 | a mix of declaring and other strategies is allowed | 1 | N152 |
| n38 | the executor is chosen the wrong way round | 16 | N148, N149, N150, N151, N155, N156, N157, N158, N159, N160, N161, N162, N163, N164, N165, N166 |
| n39 | the D1 executor's window ends a day late | 1 | N151 |
| n40 | the vocabulary of forbidden words is not applied to the output | 3 | N193, N194, N195 |
| n41 | a four-digit integer in a log record is not a figure | 1 | N207 |
| n42 | timestamps are not removed before the log scan | 1 | N202 |
| n43 | a window that starts exactly at the committed start is refused | 11 | N167, N168, N171, N172, N173, N174, N176, N212, N213, N214, N187 |
| n44 | an empty window is accepted | 1 | N184 |
| n45 | the hash does not cover the verdict line | 1 | N168 |
| n46 | an incomplete run exits zero | 1 | N176 |
| n47 | the store named on the command line is ignored | 10 | N167, N168, N171, N172, N173, N174, N175, N176, N212, N213 |
| n48 | the quantile rank rounds down instead of up | 2 | N177, N179 |
| n49 | the root logger's own handlers are left in place | 1 | N174 |
| n50 | an unaffordable entry is counted as a refused one | 1 | N117 |
| n51 | a FOK refusal is counted as an expiry | 1 | N114 |
| n52 | finish leaves no record of the entry it expires | 1 | N116 |
| n53 | any delta is accepted | 4 | N139, N140, N141, N142 |
| n54 | the committed window starts a day late | 1 | N180 |
| n55 | C1 is a different candidate | 1 | N181 |

### The test key (every code the table uses)

The codes are the tests in collection order, N1 to N215.

| Code | Test |
|---|---|
| N1 | `d1_trail`: `TestTheTriggerPrice::test_the_faqs_own_example` |
| N2 | `d1_trail`: `TestTheTriggerPrice::test_the_two_bounds_of_the_clamp` |
| N3 | `d1_trail`: `TestTheTriggerPrice::test_it_is_exact_to_the_last_digit` |
| N4 | `d1_trail`: `TestTheTriggerPrice::test_a_delta_that_cannot_make_a_trigger_is_refused` |
| N5 | `d1_trail`: `TestTheTriggerPrice::test_a_delta_that_is_not_an_int_is_refused` |
| N6 | `d1_trail`: `TestTheTriggerPrice::test_a_peak_that_is_a_float_or_not_positive_is_refused` |
| N7 | `d1_trail`: `TestAMonotoneRiseThenAFall::test_it_exits_through_the_trigger_of_the_last_peak` |
| N8 | `d1_trail`: `TestAMonotoneRiseThenAFall::test_the_bars_after_the_exit_change_nothing` |
| N9 | `d1_trail`: `TestAMonotoneRiseThenAFall::test_the_walk_does_not_advance_the_iterator_past_the_exit` |
| N10 | `d1_trail`: `TestTheEntryMinute::test_a_fall_in_the_entry_minute_exits_at_the_trigger_from_the_fill` |
| N11 | `d1_trail`: `TestTheEntryMinute::test_an_entry_minute_that_opens_below_the_trigger_is_not_a_gap` |
| N12 | `d1_trail`: `TestTheEntryMinute::test_the_entry_minutes_high_counts_toward_the_peak` |
| N13 | `d1_trail`: `TestTheEntryMinute::test_an_entry_minute_low_exactly_at_the_trigger_triggers` |
| N14 | `d1_trail`: `TestTheEntryMinute::test_an_entry_minute_low_exactly_at_the_trigger_of_its_own_high_triggers` |
| N15 | `d1_trail`: `TestTheEntryMinute::test_an_entry_minute_low_one_cent_above_the_trigger_leaves_the_position_open` |
| N16 | `d1_trail`: `TestTheEntryMinute::test_an_entry_time_on_the_minute_boundary_is_inside_that_minute` |
| N17 | `d1_trail`: `TestHighAndLowInOneMinute::test_a_new_peak_and_a_low_below_its_trigger_exits` |
| N18 | `d1_trail`: `TestHighAndLowInOneMinute::test_the_same_low_does_not_exit_while_it_is_above_the_old_trigger_alone` |
| N19 | `d1_trail`: `TestAGapOpenBelowTheTrigger::test_the_fill_is_the_open_less_the_slippage_and_the_flag_is_set` |
| N20 | `d1_trail`: `TestAGapOpenBelowTheTrigger::test_the_gap_bars_high_does_not_enter_the_peak` |
| N21 | `d1_trail`: `TestTheTriggerExactly::test_a_low_that_touches_the_trigger_exits_and_is_not_a_gap` |
| N22 | `d1_trail`: `TestTheTriggerExactly::test_an_open_exactly_at_the_trigger_is_a_gap_at_the_same_price` |
| N23 | `d1_trail`: `TestTheTriggerExactly::test_a_low_one_cent_above_the_trigger_leaves_the_position_open` |
| N24 | `d1_trail`: `TestTheTwoBoundsOfTheClamp::test_a_delta_of_ten_basis_points` |
| N25 | `d1_trail`: `TestTheTwoBoundsOfTheClamp::test_a_delta_of_two_thousand_basis_points` |
| N26 | `d1_trail`: `TestAPathThatEndsOpen::test_the_peak_is_the_highest_high_from_the_entry_minute_on` |
| N27 | `d1_trail`: `TestAPathThatEndsOpen::test_an_empty_path_is_open_at_the_fill_price` |
| N28 | `d1_trail`: `TestAPathThatEndsOpen::test_the_peak_never_moves_down` |
| N29 | `d1_trail`: `TestTheFaqsOwnExample::test_a_700_bips_trail_from_45500_exits_at_42315` |
| N30 | `d1_trail`: `TestRefusals::test_a_float_among_the_money_figures_is_a_type_error` |
| N31 | `d1_trail`: `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[0]` |
| N32 | `d1_trail`: `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[-1]` |
| N33 | `d1_trail`: `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[NaN]` |
| N34 | `d1_trail`: `TestRefusals::test_an_entry_price_that_is_not_positive_and_finite_is_refused[Infinity]` |
| N35 | `d1_trail`: `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[-0.01]` |
| N36 | `d1_trail`: `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[100]` |
| N37 | `d1_trail`: `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[150]` |
| N38 | `d1_trail`: `TestRefusals::test_a_slippage_outside_zero_to_below_one_hundred_is_refused[NaN]` |
| N39 | `d1_trail`: `TestRefusals::test_a_delta_out_of_range_is_refused[0]` |
| N40 | `d1_trail`: `TestRefusals::test_a_delta_out_of_range_is_refused[-5]` |
| N41 | `d1_trail`: `TestRefusals::test_a_delta_out_of_range_is_refused[10000]` |
| N42 | `d1_trail`: `TestRefusals::test_a_delta_that_is_a_bool_is_refused` |
| N43 | `d1_trail`: `TestRefusals::test_a_naive_entry_time_is_refused` |
| N44 | `d1_trail`: `TestRefusals::test_an_entry_time_outside_the_first_bars_minute_is_refused` |
| N45 | `d1_trail`: `TestRefusals::test_a_bar_that_is_not_a_one_minute_bar_is_refused` |
| N46 | `d1_trail`: `TestRefusals::test_a_repeated_minute_is_refused` |
| N47 | `d1_trail`: `TestRefusals::test_a_minute_out_of_order_is_refused` |
| N48 | `d1_trail`: `TestRefusals::test_a_bar_with_a_naive_open_time_is_refused` |
| N49 | `d1_trail`: `TestRefusals::test_a_missing_minute_is_not_detected_here` |
| N50 | `d1_trail`: `TestTheOutcomeShape::test_an_exited_outcome_needs_its_minute_and_price` |
| N51 | `d1_trail`: `TestTheOutcomeShape::test_an_open_outcome_carries_neither_and_no_gap` |
| N52 | `d1_trail`: `TestTheOutcomeShape::test_a_float_price_is_refused_by_the_money_guard` |
| N53 | `d1_trail`: `TestTheOutcomeShape::test_the_outcome_is_frozen` |
| N54 | `d1_trail`: `TestTheOutcomeShape::test_every_figure_is_a_decimal` |
| N55 | `d1_trail`: `TestThePurity::test_the_module_imports_no_clock_no_store_and_no_io` |
| N56 | `d1_trail`: `TestThePurity::test_it_reads_no_wall_clock` |
| N57 | `d1_trail`: `TestThePurity::test_it_has_no_comment` |
| N58 | `d1_trail`: `TestThePurity::test_the_same_arguments_give_the_same_answer` |
| N59 | `m5n_trail`: `TestTheArithmetic::test_it_is_ten_thousand_times_three_atr_over_the_close` |
| N60 | `m5n_trail`: `TestTheArithmetic::test_it_rounds_down` |
| N61 | `m5n_trail`: `TestTheArithmetic::test_it_floors_and_does_not_round_to_nearest` |
| N62 | `m5n_trail`: `TestTheArithmetic::test_it_uses_the_close_it_is_given` |
| N63 | `m5n_trail`: `TestTheArithmetic::test_the_upper_bound_is_not_a_clamp` |
| N64 | `m5n_trail`: `TestTheArithmetic::test_above_the_upper_bound_clamps_to_it` |
| N65 | `m5n_trail`: `TestTheArithmetic::test_the_lower_bound_is_not_a_clamp` |
| N66 | `m5n_trail`: `TestTheArithmetic::test_below_the_lower_bound_clamps_to_it` |
| N67 | `m5n_trail`: `TestTheArithmetic::test_a_zero_atr_clamps_to_the_lower_bound` |
| N68 | `m5n_trail`: `TestTheArithmetic::test_the_result_is_a_plain_int` |
| N69 | `m5n_trail`: `TestWhatItRefuses::test_a_nan_atr_is_no_distance` |
| N70 | `m5n_trail`: `TestWhatItRefuses::test_an_infinite_atr_is_no_distance` |
| N71 | `m5n_trail`: `TestWhatItRefuses::test_twenty_rows_cannot_form_an_atr_of_twenty` |
| N72 | `m5n_trail`: `TestWhatItRefuses::test_twenty_one_rows_can` |
| N73 | `m5n_trail`: `TestWhatItRefuses::test_a_close_that_is_not_positive_is_refused[0]` |
| N74 | `m5n_trail`: `TestWhatItRefuses::test_a_close_that_is_not_positive_is_refused[-1]` |
| N75 | `m5n_trail`: `TestTheRealIndicator::test_a_constant_range_gives_that_range` |
| N76 | `m5n_trail`: `TestTheRealIndicator::test_a_wide_range_clamps_high` |
| N77 | `m5n_trail`: `TestTheRealIndicator::test_a_narrow_range_clamps_low` |
| N78 | `m5n_trail`: `TestTheRealIndicator::test_the_input_frame_is_not_changed` |
| N79 | `m5n_trail`: `TestTheSignalCarriesIt::test_a_donchian_breakout_carries_the_distance_of_its_own_frame` |
| N80 | `m5n_trail`: `TestTheSignalCarriesIt::test_the_distance_is_taken_from_the_signal_bars_close` |
| N81 | `m5n_trail`: `TestTheSignalCarriesIt::test_the_gap_free_run_feeds_the_atr_and_not_the_rows_before_a_gap` |
| N82 | `m5n_trail`: `TestTheSignalCarriesIt::test_a_signal_without_a_distance_is_no_signal` |
| N83 | `m5n_trail`: `TestEveryCandidateCanFormTheDistance::test_its_window_holds_enough_rows_for_the_atr[donchian_1d_20]` |
| N84 | `m5n_trail`: `TestEveryCandidateCanFormTheDistance::test_its_window_holds_enough_rows_for_the_atr[donchian_1d_55]` |
| N85 | `m5n_trail`: `TestEveryCandidateCanFormTheDistance::test_its_window_holds_enough_rows_for_the_atr[sma_cross_1d_50_200]` |
| N86 | `m5n_trail`: `TestEveryCandidateCanFormTheDistance::test_its_window_holds_enough_rows_for_the_atr[donchian_4h_20]` |
| N87 | `m5n_trail`: `TestEveryCandidateCanFormTheDistance::test_its_window_holds_enough_rows_for_the_atr[keltner_4h_20_2]` |
| N88 | `m5n_trail`: `TestEveryCandidateCanFormTheDistance::test_its_window_holds_enough_rows_for_the_atr[tsmom_1d_90]` |
| N89 | `m5n_trail`: `TestTheDeclaration::test_each_m5n_candidate_declares_the_d1_exit[donchian_1d_20]` |
| N90 | `m5n_trail`: `TestTheDeclaration::test_each_m5n_candidate_declares_the_d1_exit[donchian_1d_55]` |
| N91 | `m5n_trail`: `TestTheDeclaration::test_each_m5n_candidate_declares_the_d1_exit[sma_cross_1d_50_200]` |
| N92 | `m5n_trail`: `TestTheDeclaration::test_each_m5n_candidate_declares_the_d1_exit[donchian_4h_20]` |
| N93 | `m5n_trail`: `TestTheDeclaration::test_each_m5n_candidate_declares_the_d1_exit[keltner_4h_20_2]` |
| N94 | `m5n_trail`: `TestTheDeclaration::test_each_m5n_candidate_declares_the_d1_exit[tsmom_1d_90]` |
| N95 | `m5n_trail`: `TestTheDeclaration::test_the_base_class_does_not` |
| N96 | `m5n_trail`: `TestTheDeclaration::test_no_other_registered_strategy_declares_it` |
| N97 | `m5n_trail`: `TestTheDeclaration::test_the_metadata_keys_are_the_ones_the_executor_reads` |
| N98 | `d1_executor`: `TestTheExitInTheEntryBar::test_a_trail_that_triggers_in_the_entry_bar_is_booked_in_that_callback` |
| N99 | `d1_executor`: `TestTheExitInTheEntryBar::test_the_entry_minutes_high_counts_toward_the_peak` |
| N100 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_after_the_bar_is_not_booked_until_the_clock_reaches_it` |
| N101 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_at_exactly_the_clock_is_booked` |
| N102 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_one_minute_past_the_clock_waits` |
| N103 | `d1_executor`: `TestTheExitIsScheduled::test_the_exit_is_booked_before_a_signal_on_the_next_bar_can_see_it` |
| N104 | `d1_executor`: `TestTheExitIsScheduled::test_two_pairs_book_in_time_order_not_in_callback_order` |
| N105 | `d1_executor`: `TestTheExitIsScheduled::test_overlapping_positions_hold_one_ledger` |
| N106 | `d1_executor`: `TestAPositionThatNeverTriggers::test_it_stays_open_at_the_end` |
| N107 | `d1_executor`: `TestAPositionThatNeverTriggers::test_a_trigger_after_the_window_end_is_never_read` |
| N108 | `d1_executor`: `TestAPositionThatNeverTriggers::test_finish_is_idempotent` |
| N109 | `d1_executor`: `TestAGapInTheMinutePath::test_a_fall_inside_the_gap_exits_at_the_next_traded_open` |
| N110 | `d1_executor`: `TestAGapInTheMinutePath::test_a_gap_that_recovers_leaves_the_position_open` |
| N111 | `d1_executor`: `TestAGapInTheMinutePath::test_a_decision_bar_gap_flags_the_trade` |
| N112 | `d1_executor`: `TestZeroVolumeMinutes::test_a_filler_minute_is_not_a_trade_and_is_not_walked` |
| N113 | `d1_executor`: `TestZeroVolumeMinutes::test_a_bar_with_no_traded_minute_cannot_fill` |
| N114 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_open_above_the_limit_is_refused` |
| N115 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_a_missing_next_slot_expires_the_entry` |
| N116 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_entry_the_data_ends_on_expires` |
| N117 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_entry_the_ledger_cannot_pay_for_is_unaffordable` |
| N118 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_a_second_entry_while_one_is_pending_is_ignored` |
| N119 | `d1_executor`: `TestThePositionItOpens::test_the_initial_stop_is_the_fill_less_the_trail` |
| N120 | `d1_executor`: `TestThePositionItOpens::test_it_is_stamped_active_at_the_simulated_instant` |
| N121 | `d1_executor`: `TestThePositionItOpens::test_a_position_on_another_pair_is_stamped_on_every_bar` |
| N122 | `d1_executor`: `TestTheTally::test_every_signal_is_counted_with_its_delta_and_clamp` |
| N123 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unknown_pair]` |
| N124 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[no_reference_price]` |
| N125 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[nothing_to_close]` |
| N126 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unsupported_action]` |
| N127 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[no_mark_price]` |
| N128 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[position_stale]` |
| N129 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[committed_risk_unknown]` |
| N130 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[limit_refused]` |
| N131 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[live_order_list]` |
| N132 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unmanaged_holding]` |
| N133 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[atr_unavailable]` |
| N134 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[stop_unplaceable]` |
| N135 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[size_not_tradeable]` |
| N136 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unaffordable]` |
| N137 | `d1_executor`: `TestTheTally::test_pairs_are_tallied_apart` |
| N138 | `d1_executor`: `TestTheTally::test_the_snapshot_is_a_copy` |
| N139 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[None]` |
| N140 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[500.0]` |
| N141 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[500]` |
| N142 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[True]` |
| N143 | `d1_executor`: `TestWhatItRefusesToDispatch::test_an_approved_exit_raises` |
| N144 | `d1_executor`: `TestTheContract::test_it_satisfies_the_dispatcher_port` |
| N145 | `d1_executor`: `TestTheContract::test_the_metadata_keys_are_the_ones_the_strategies_write` |
| N146 | `d1_executor`: `TestTheContract::test_two_runs_of_the_same_history_give_the_same_trade_log` |
| N147 | `d1_executor`: `TestTheContract::test_the_module_reads_no_wall_clock` |
| N148 | `backtest_d1`: `TestTheChoice::test_a_strategy_that_declares_the_exit_takes_the_d1_executor` |
| N149 | `backtest_d1`: `TestTheChoice::test_a_strategy_that_does_not_takes_the_simulated_executor_and_its_digest_holds` |
| N150 | `backtest_d1`: `TestTheChoice::test_the_old_path_holds_on_two_pairs_too` |
| N151 | `backtest_d1`: `TestTheChoice::test_no_series_is_asked_for_past_the_window_end` |
| N152 | `backtest_d1`: `TestTheChoice::test_a_mix_of_declaring_and_other_strategies_is_refused` |
| N153 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_run_is_complete_and_the_cash_identity_holds[4h]` |
| N154 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_run_is_complete_and_the_cash_identity_holds[1d]` |
| N155 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_each_pair_books_its_own_exit_at_the_hand_worked_price[4h]` |
| N156 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_each_pair_books_its_own_exit_at_the_hand_worked_price[1d]` |
| N157 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_positions_overlap_and_the_earlier_exit_is_booked_first[4h]` |
| N158 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_positions_overlap_and_the_earlier_exit_is_booked_first[1d]` |
| N159 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_a_signal_while_in_position_is_a_limit_refusal[4h]` |
| N160 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_a_signal_while_in_position_is_a_limit_refusal[1d]` |
| N161 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_second_entry_is_still_open_at_the_end[4h]` |
| N162 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_second_entry_is_still_open_at_the_end[1d]` |
| N163 | `backtest_d1`: `TestAGapWhilePositionsAreOpen::test_a_missing_decision_bar_and_minutes_with_a_fall_exit_at_the_next_open` |
| N164 | `backtest_d1`: `TestAGapWhilePositionsAreOpen::test_the_same_gap_without_a_fall_leaves_the_position_open` |
| N165 | `backtest_d1`: `TestTheRealCandidate::test_a_quiet_breakout_clamps_to_the_lower_bound_and_stays_open` |
| N166 | `backtest_d1`: `TestTheRealCandidate::test_a_wild_breakout_clamps_to_the_upper_bound` |
| N167 | `n4_trade_counts`: `TestTheRun::test_the_output_is_exactly_the_schema` |
| N168 | `n4_trade_counts`: `TestTheRun::test_the_last_line_is_the_hash_of_every_line_before_it` |
| N169 | `n4_trade_counts`: `TestTheRun::test_the_output_has_no_decimal_point_and_no_money_word` |
| N170 | `n4_trade_counts`: `TestTheRun::test_two_runs_print_the_same_bytes` |
| N171 | `n4_trade_counts`: `TestTheRun::test_it_writes_no_run_record_and_no_trade_file` |
| N172 | `n4_trade_counts`: `TestTheRun::test_it_opens_no_file_for_writing` |
| N173 | `n4_trade_counts`: `TestTheRun::test_nothing_the_run_logs_reaches_a_handler_or_a_terminal` |
| N174 | `n4_trade_counts`: `TestTheRun::test_a_warning_logged_during_the_run_is_kept_and_counted_and_never_shown` |
| N175 | `n4_trade_counts`: `TestTheRun::test_a_narrower_window_is_accepted_and_named` |
| N176 | `n4_trade_counts`: `TestTheRun::test_a_run_that_is_not_complete_says_so_and_exits_one` |
| N177 | `n4_trade_counts`: `TestTheQuantiles::test_nearest_rank_on_ten_values` |
| N178 | `n4_trade_counts`: `TestTheQuantiles::test_a_single_value_is_every_quantile` |
| N179 | `n4_trade_counts`: `TestTheQuantiles::test_the_line_sorts_its_values_and_prints_the_extremes` |
| N180 | `n4_trade_counts`: `TestTheWindow::test_the_constants_are_the_committed_ones` |
| N181 | `n4_trade_counts`: `TestTheWindow::test_the_candidates_are_the_six_in_r_dys_order` |
| N182 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv0]` |
| N183 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv1]` |
| N184 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv2]` |
| N185 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv3]` |
| N186 | `n4_trade_counts`: `TestTheWindow::test_a_naive_window_is_refused` |
| N187 | `n4_trade_counts`: `TestTheWindow::test_the_whole_committed_window_is_accepted` |
| N188 | `n4_trade_counts`: `TestTheScan::test_the_lines_the_schema_makes_pass` |
| N189 | `n4_trade_counts`: `TestTheScan::test_a_stage_named_for_a_price_is_a_stage_and_not_a_figure` |
| N190 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1.5 trades=1 open_at_end=0 entries_filled=1 fok_refused=0 expired=0 unaffordable=0 clamp_upper=0 clamp_lower=0]` |
| N191 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT mean_return=1]` |
| N192 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT delta_bps n=1 p10=100000 p25=1 p50=1 p75=1 p90=1 min=1 max=1]` |
| N193 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 price_1d (1d)]` |
| N194 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 realised_1d (1d)]` |
| N195 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 donchian_1d_20 (1d) equity]` |
| N196 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  run complete=yes problems=0 ]` |
| N197 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[]` |
| N198 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[window [2017-08-17, 2024-01-01) caf\xe9]` |
| N199 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT balance 42000]` |
| N200 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[output_sha256=XYZ]` |
| N201 | `n4_trade_counts`: `TestTheScan::test_the_count_is_per_line` |
| N202 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[BTCUSDT/4h: 1 bar(s) missing between 2017-09-06T16:00:00+00:00 and 2017-09-06T20:00:00+00:00]` |
| N203 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[Entry for ETHUSDT ignored: an entry is pending or a position is held]` |
| N204 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[stream handler failed for BTCUSDT 4h]` |
| N205 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[Risk approved BTCUSDT: 2.00330000 at 98.10000000]` |
| N206 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[free quote 10000.5]` |
| N207 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[filled at 42000]` |
| N208 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[balance is low]` |
| N209 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[the realised total moved]` |
| N210 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[cost $5]` |
| N211 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[price 100]` |
| N212 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_a_line_the_grammar_refuses_is_not_printed` |
| N213 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_a_log_record_that_carries_a_figure_fails_the_scan_and_is_not_printed` |
| N214 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_an_exception_is_reported_by_class_and_place_and_never_by_message` |
| N215 | `n4_trade_counts`: `TestTheScript::test_it_has_no_fetcher_and_never_writes` |

## 92. M5n N4b: the arming-audit survey of the N4b code, scored against section 91 (P144 C12, R-T)

An observation log, so this section only adds. The survey ran as section 91 describes, with the repository's `scripts/worktree_survey.py` and `scripts/survey_hook.py` (`92e63e3`), in a detached worktree outside the repository at `836c21d` (the commit that carries section 91), the import location of `trading_bot` and `tests` printed inside the worktree before any result, an unmutated baseline of 215 passed in 13.27 s, every restore SHA-equal, and `git worktree list` showing the main worktree only afterwards. **It halted once, at `n40`, on a FEWER, and was resumed after the missing kill was explained**: the first run was `n01` to `n40` (`2026-10-25T05:35:27Z` to `05:44:50Z`, exit 1), the second `n41` to `n55` from the same commit with a spec that is the committed one cut at `n41` (`survey_n4_rest.json`, SHA-256 `866c84bbd0ed0ee52085d8c13581ec76c4c66692ce162c0827ab32cd769e5bbf`; the committed spec's is `1de3cc4e5749a138921c6f7dc32789dbc9b03e4a13e76ffce5de9e2fef399c02`) and its own worktree and baseline (`05:45:13Z` to `05:48:50Z`, exit 0). Nothing here decides anything about S4.

### Totals

**55 mutations: 49 MATCH, 5 MORE, 1 FEWER. Predicted failures 174, observed 188.** The five MOREs are `n04`, `n23`, `n25`, `n38` and `n53`; the FEWER is `n40`. The two mutations predicted to fail nothing (`n08`, `n35`) failed nothing.

**Tests killed by no mutation: 103 of 215, against 102 predicted.** The one more is the FEWER's: the `equity` row of the scan test (see the diagnosis). By file, 53 of `test_d1_trail.py` (surveyed at P143), 13 of `test_m5n_trail.py`, 7 of `test_d1_executor.py`, 2 of `test_backtest_d1.py` and 28 of `test_n4_trade_counts.py`; the declared reasons in section 91 stand.

**Seven tests are killed only by crashes and not by an assertion**, so by `M5i-115` they are not killed: the two overlap tests (`KeyError`, under `n38`), `test_a_signal_without_a_distance_is_no_signal` (`AttributeError`, under `n12`), the two non-finite-ATR tests (`ValueError`, under `n09`), the zero-close case (`decimal.DivisionByZero`, under `n10`) and `test_the_whole_committed_window_is_accepted` (`n4_trade_counts.WindowError`, under `n43`, where it is a must-not-raise test that raises). Six of the seven were predicted as crashes; the seventh was predicted to fail and not as a crash. **Every other test that any mutation failed was failed by an assertion at least once**: 105 of the 112.

### The miss that halted the survey

* **`n40` (the vocabulary of forbidden words is not applied to the output): FEWER, 2 observed against 3 predicted.** The test missing is `test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 donchian_1d_20 (1d) equity]`. Section 91 reasoned that the row reached the vocabulary check. It does not: its extra word `equity` after the closing bracket makes it fail the GRAMMAR (the candidate line is a full match of `candidate C[1-6] name (tf)`), so it is counted by the first guard and the vocabulary guard is never consulted. The other two rows (`price_1d`, `realised_1d`) fit the grammar and are killed. So the mutation DID load and the missing kill is a wrong prediction about reach, not an absent mutation: the survey was resumed. **That row pins the grammar and not the vocabulary**, which is one more test killed by none, and it was a prediction made from the row's text and not from the grammar's `fullmatch`.

### The MOREs, diagnosed

Each is a reach error, and the extra kills are real coverage.

* **`n04` (round half up): 3 observed against 2.** The extra is `test_below_the_lower_bound_clamps_to_it` (0.01 over 31): its raw distance is 9.68, which rounds up to 10 and is then not a clamp, so the expected LOWER becomes NONE. Section 91 named the third test as the likely miss but guessed the wrong one.
* **`n23` (no position is ever stamped): 6 observed against 5.** The extra is `test_the_output_is_exactly_the_schema`: the counts script's own test world holds the same two positions, so its `limit_refused` line becomes `position_stale`. Section 91 listed the two backtest limit tests and not the script's.
* **`n25` (the deltas are not kept): 5 observed against 3.** The extra two are the real-candidate tests, which assert `tally.deltas == [10]` and `== [2000]`.
* **`n38` (the executor chosen the wrong way round): 26 observed against 16.** The extra ten are the counts script's tests that run its world: with the simulated executor the script raises its own "did not take the D1 executor" error, exits 2 and prints nothing, so nine tests fail by an assertion on the exit code or the output and `test_the_last_line_is_the_hash_of_every_line_before_it` fails by a `ValueError` at its unpack. Section 91 named only `test_backtest_d1.py` as downstream of the choice and missed the script, which is downstream of it too.
* **`n53` (any delta is accepted): 5 observed against 4.** The extra is `test_a_run_that_is_not_complete_says_so_and_exits_one`, which fails by a `TypeError`: with the integer check gone, the broken strategy's delta of `None` reaches the output's `sorted` and the run raises where it should say the run is incomplete. A crash, and a real consequence of the check.

### What the survey leaves unpinned, and does not fix

The 103 tests killed by no mutation are, by file, the same families as section 91 declared: the 53 `d1_trail` tests surveyed at P143, the per-candidate window checks, the key-agreement, determinism, port and wall-clock tests, and the scan's accepted and refused rows, which are guarded twice. **Two things are worth knowing rather than fixing here.** The `equity` row pins the grammar and not the vocabulary (above). And the seven crash-only tests are each a "raises" or "must not raise" test that no one-line mutation can make fail by an assertion; none is needed by N4b's counts.

### Every mutation

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| n01 | the entry minute's high is not part of the peak (R-EB reverted) | 5 | 5 | MATCH |
| n02 | the entry minute's low must be strictly below the trigger | 2 | 2 | MATCH |
| n03 | the multiple is 2, not 3 | 10 | 10 | MATCH |
| n04 | the raw distance rounds half up instead of down | 2 | 3 | MORE (see the diagnosis) |
| n05 | a distance exactly at the lower bound is a clamp | 1 | 1 | MATCH |
| n06 | a distance exactly at the upper bound is a clamp | 1 | 1 | MATCH |
| n07 | a lower clamp is not reported as one | 4 | 4 | MATCH |
| n08 | twenty rows are enough for the ATR guard | 0 | 0 | MATCH |
| n09 | a non-finite ATR is not refused | 2 | 2 | MATCH; crash: ValueError |
| n10 | a close of zero is not refused | 1 | 1 | MATCH; crash: decimal.DivisionByZero |
| n11 | the ATR reads the whole frame, not the gap-free run | 1 | 1 | MATCH |
| n12 | a missing distance does not stop the signal | 1 | 1 | MATCH; crash: AttributeError |
| n13 | the signal always says the distance was not clamped | 2 | 2 | MATCH |
| n14 | the M5n candidates stop declaring the D1 exit | 8 | 8 | MATCH |
| n15 | every strategy declares the D1 exit | 4 | 4 | MATCH |
| n16 | the exits due by the end of the bar are booked only up to its open | 7 | 7 | MATCH |
| n17 | an exit due exactly at the clock waits | 1 | 1 | MATCH |
| n18 | an exit is booked at the open of its minute, not its end | 8 | 8 | MATCH |
| n19 | a zero-volume minute is walked as a trade | 2 | 2 | MATCH |
| n20 | a first traded minute at the next bar's open still fills | 1 | 1 | MATCH |
| n21 | the initial stop sits twice the trail below the fill | 4 | 4 | MATCH |
| n22 | a stamped position is untrusted | 2 | 2 | MATCH |
| n23 | no position is ever stamped | 5 | 6 | MORE (see the diagnosis) |
| n24 | a trail exit is reported as a CLOSE | 1 | 1 | MATCH |
| n25 | the deltas are not kept | 3 | 5 | MORE (see the diagnosis) |
| n26 | an upper clamp is counted as a lower one | 2 | 2 | MATCH |
| n27 | no refusal is tallied by stage | 20 | 20 | MATCH |
| n28 | a bool is accepted as the delta | 1 | 1 | MATCH |
| n29 | an approved exit is ignored and not refused | 1 | 1 | MATCH |
| n30 | a second entry replaces a pending one | 1 | 1 | MATCH |
| n31 | finish books nothing | 1 | 1 | MATCH |
| n32 | a gap in the decision bars is read the wrong way round | 2 | 2 | MATCH |
| n33 | a gapped exit is not flagged | 4 | 4 | MATCH |
| n34 | the reported trigger is the exit price | 3 | 3 | MATCH |
| n35 | the exits due by the bar's open are not booked first | 0 | 0 | MATCH |
| n36 | the 1m path is read past the window end | 2 | 2 | MATCH |
| n37 | a mix of declaring and other strategies is allowed | 1 | 1 | MATCH |
| n38 | the executor is chosen the wrong way round | 16 | 26 | MORE (see the diagnosis); crash: KeyError, ValueError |
| n39 | the D1 executor's window ends a day late | 1 | 1 | MATCH |
| n40 | the vocabulary of forbidden words is not applied to the output | 3 | 2 | FEWER (see the diagnosis); the survey halted here and resumed |
| n41 | a four-digit integer in a log record is not a figure | 1 | 1 | MATCH |
| n42 | timestamps are not removed before the log scan | 1 | 1 | MATCH |
| n43 | a window that starts exactly at the committed start is refused | 11 | 11 | MATCH; crash: ValueError, n4_trade_counts.WindowError |
| n44 | an empty window is accepted | 1 | 1 | MATCH |
| n45 | the hash does not cover the verdict line | 1 | 1 | MATCH |
| n46 | an incomplete run exits zero | 1 | 1 | MATCH |
| n47 | the store named on the command line is ignored | 10 | 10 | MATCH; crash: ValueError |
| n48 | the quantile rank rounds down instead of up | 2 | 2 | MATCH |
| n49 | the root logger's own handlers are left in place | 1 | 1 | MATCH |
| n50 | an unaffordable entry is counted as a refused one | 1 | 1 | MATCH |
| n51 | a FOK refusal is counted as an expiry | 1 | 1 | MATCH |
| n52 | finish leaves no record of the entry it expires | 1 | 1 | MATCH |
| n53 | any delta is accepted | 4 | 5 | MORE (see the diagnosis); crash: TypeError |
| n54 | the committed window starts a day late | 1 | 1 | MATCH |
| n55 | C1 is a different candidate | 1 | 1 | MATCH |

## 93. M5n N5: how the unchanged RiskManager sizes, and the predictions for the N5 count run, before any code (P145 C2, R-T, R-DQ)

An observation log, so this section only adds. P145 item 2 is a read, and item 3 is the predictions; both are committed before any code, test or script is drafted. HEAD is `b6759a1` (the charter commit of P145), on `m5n`, `main` at `ee8d485`. Nothing here decides anything about S4, and no run has been made.

### Item 2a. How the RiskManager sizes when `stop_loss` is enabled (MEASURED, by reading `src/trading_bot/risk/`)

`RiskManager.evaluate` (`manager.py:272`) is the composed path, with the signature `evaluate(self, signal, *, portfolio)`: **it has no parameter for a supplied stop.** The stop reaches the sizer only through the manager's own config:

1. `stop_loss = self._config.stop_loss` (`manager.py:471`). The `atr` type reads the manager's own ATR (`manager.py:473-482`); the `percent` type needs nothing else.
2. `entry_limit = derive_entry_limit(price, max_slippage=self._config.max_entry_slippage, tick_size=...)` (`manager.py:487-491`; `rules.py:317-349`): the signal close widened by `max_entry_slippage` and rounded UP to the tick.
3. `compute_protective_levels(... entry_price=entry_limit, stop_loss=stop_loss ...)` (`manager.py:493-501`) calls `stop_loss_level` (`rules.py:253-276`), whose distance is `entry_price * config.percent / 100` for `percent` (`rules.py:241-242`) and `atr_multiplier * ATR` for `atr` (`rules.py:243-249`). The level is rounded TOWARD the entry, which for a long's stop is `ROUND_CEILING` (`rules.py:181-203`), and is `None` when the distance is sub-tick.
4. The stop gate (`manager.py:507-514`): `stop_loss.enabled` with no placeable level is a refusal at `STOP_UNPLACEABLE`.
5. `self.size_position(signal, equity=equity, price=entry_limit, stop_price=levels.stop_loss)` (`manager.py:519-521`; the method is `manager.py:236-269`), then `calculate_position_size` (`position_sizing.py:196-288`). For `risk_per_trade` (`position_sizing.py:179-191`) the quantity is `equity * risk_fraction / |entry - stop|` (`size_by_risk_per_trade`, `position_sizing.py:135-163`, the division at `:163`). It is then capped at `max_position_size_percent` of equity (`position_sizing.py:246-249`), rounded DOWN to the effective step (`:253`), and refused if under `min_qty` (`:271`) or if the notional at `min(price, stop)` is under `min_notional` (`:276-281`). `equity` is `portfolio.equity(marks)`, the total portfolio value (`manager.py:430`).
6. Affordability (`manager.py:534-543`): `cost = quantity * entry_limit`, and `cost > portfolio.free_quote` is a REFUSAL at `RefusalStage.UNAFFORDABLE`. **It does not shrink the quantity.**
7. `config/models.py:507-515` refuses `risk_per_trade` while `stop_loss.enabled` is false, which is the placeholder note in `config.m5n.yaml`.

**What this means for the N5 decisions.** Three things are true of the unchanged class and the owner's wording should be read against them.

* *The stop is `entry_limit x (1 - delta / 10000)` at the tick, not `fill x (1 - delta / 10000)`.* The manager sizes at the signal bar, before any fill exists, so the basis is the entry limit (the close widened by 0.1 percent), exactly as the prompt's "per the existing RiskManager definition" says. The executor's `Position.stop_loss` stays `fill x (1 - delta / 10000)` (N4b), which is what committed risk prices from. The two differ by the entry slippage and a tick.
* *"Notional is capped by the free quote balance" is a refusal, not a cap.* The manager refuses at `UNAFFORDABLE` (item 6) and the executor refuses again at fill time (`entries_unaffordable`, `d1_executor.py:337-338`). The only thing that SHRINKS a notional is `max_position_size_percent`.
* *`max_position_size_percent` defaults to 20 and applies.* The prompt says every other setting stays at its default, so the 1-percent risk is capped at 20 percent of equity: **it binds whenever `delta < 500` bps** (1 percent / 5 percent = 20 percent). On the 1d candidates it rarely binds (the lowest delta in section 90 is 613); on C4 and C5 it binds on roughly a fifth to a half of entries (the p25 of the delta is 405 to 542 bps and the p50 is 528 to 692). The counts do not show it (a capped size is not on the R-DT-3d or R-DT-3e list), so how often it binds is UNMEASURED and stays so.

**The HALT clause, read.** "The RiskManager cannot size from a supplied initial stop without a code change" is not met, on this reading: `RiskManager` is a class over a frozen config, it holds no state beyond config, provider, pairs and clock, and its `percent` stop is exactly a stop supplied as a distance. A manager whose `stop_loss.percent` is `delta / 100`, an exact `Decimal` for every integer delta from 10 to 2000, sizes from the clamped trail. **The wiring is therefore a subclass of `RiskManager` that overrides nothing in the base class's code: it keeps one unchanged base manager per delta (config copied with `stop_loss.percent = delta / 100`) and `evaluate` delegates to the one for the signal's `trail_delta_bps`.** It is chosen only on the D1 path, next to the D1 executor. If the owner reads the HALT clause as requiring that `evaluate` itself accept a supplied stop, that is a code change to the manager and N5 stops here; this is flagged for that ruling and nothing is built on the other reading until the code step, which comes after these predictions.

### Item 2b. The `config.m5n.yaml` keys that change

| Key | Now | N5 |
|---|---|---|
| `risk.position_sizing.method` | `fixed_fraction` | `risk_per_trade` |
| `risk.position_sizing.fraction` | `0.02` | removed (unused by the new method) |
| `risk.position_sizing.risk_per_trade` | absent (default `0.01`, `config/models.py:178`) | `0.01`, written out |
| `risk.stop_loss.enabled` | `false` | `true` |
| `risk.stop_loss.type` / `percent` | absent (defaults `percent`, `2.0`) | `percent`, `20.0`: a placeholder that the D1 risk manager replaces with each signal's delta; 20.0 is the upper clamp, so a failure to replace it would show as a clamp-sized stop and not as a 2 percent one |

`take_profit.enabled` and `trailing_stop.enabled` stay `false`, and `max_position_staleness_s` stays `259200.0`. **The file loads with these**, checked in memory with no file written: `protective_legs` becomes 1 and the reconciliation call cap stays 3, so the coherence validators are unmoved.

### Item 2c. Every RiskManager setting that applies, with its value

All read from `RiskConfig` and its limits, `config/models.py`, with the N5 file's own values.

| Setting | Value | Where | Note |
|---|---|---|---|
| `position_sizing.method` | `risk_per_trade` | set in the file | |
| `position_sizing.risk_per_trade` | `0.01` | `models.py:178`, written out | 1 percent of equity |
| `stop_loss` | enabled, `percent`, placeholder `20.0` | set in the file | replaced per signal |
| `take_profit.enabled` | `false` | set in the file | default is `true` (`models.py:206`) |
| `trailing_stop.enabled` | `false` | default (`models.py:220`) | |
| `limits.max_open_positions` | `3` | default (`models.py:238`) | two pairs are enabled, so it cannot bind |
| `limits.max_daily_loss_percent` | `5.0` | default (`models.py:239`) | realised today plus committed risk |
| `limits.max_position_size_percent` | `20` | default (`models.py:240`) | binds below 500 bps |
| `limits.cooldown_minutes` | `15` | default (`models.py:241`) | **never started in a backtest**: `Portfolio.start_cooldown` has no caller on the backtest path (`simulated_executor.py:60` says so; the D1 executor calls `close_position` and nothing else), so no cooldown refusal can occur |
| `max_entry_slippage` | `0.001` | default (`models.py:284`) | equal to `config.s4.yaml`'s |
| `max_position_staleness_s` | `259200.0` | set in the file | the executor stamps every held position on every bar |
| `price_band_margin` | `0.02` | default (`models.py:296`) | REASONED to be unread on the backtest path (it prices a venue band at dispatch) |

### Item 3. The predictions (R-T, R-DQ), committed before any code

**What the rules do, so the predictions can be checked against the reasoning.** `_approve` (`manager.py:159-233`) checks, in this order, `NO_EQUITY`, `DAILY_LOSS_HALT`, `ALREADY_IN_POSITION`, `COOLDOWN`, `MAX_OPEN_POSITIONS`. **`DAILY_LOSS_HALT` is checked BEFORE `ALREADY_IN_POSITION`**, so while the halt holds, a signal on a pair that is held is counted as the halt and not as a position already held; the by-rule split is not "held versus not held". The halt fires when `realised_today + committed <= -5 percent of equity now`, and `committed` is the sum over open positions of `min(0, (stop - mark) x quantity)` with `stop` the executor's untrailed `Position.stop_loss` (`portfolio.py:1112-1149`). With risk sized at 1 percent, a position whose mark is `g` above its entry and whose delta is `d` commits about `1 percent x (1 + g / d)` of equity, so one position alone reaches 5 percent when it has gained about four deltas (60 percent at a 1500 bps trail) and two positions reach it when the sums of `g / d` reach about 3. **That is M5n-091**: the stop is never trailed, so a large winner commits a large amount of risk to a stop far below the mark.

**Structural predictions (the ones I am most sure of).**

1. **Signals, clamps and delta quantiles are identical to section 90 in all twelve cells**, to the digit (a strategy's output does not depend on the risk manager, and neither do its deltas).
2. **The identity holds exactly in every cell:** signals = sum of refusals + trades + OPEN-at-end + FOK-refused + expired + unaffordable (the executor's).
3. **Every stage other than `limit_refused` is 0 in all twelve cells**, so the by-rule split of `limit_refused` is the whole of the refusals: `unaffordable` (both the manager's stage and the executor's), `size_not_tradeable`, `stop_unplaceable`, `committed_risk_unknown`, `position_stale`, `atr_unavailable`, `live_order_list` and `unmanaged_holding` are all 0.
4. **By rule, `cooldown`, `max_open_positions`, `no_equity` and `no_mark_price` are 0 in all twelve cells**; only `daily_loss_halt` and `already_in_position` are non-zero.
5. **OPEN at the end is 0 in all twelve cells**, as at N4b (a trade's entry minute and trail are unchanged by sizing).
6. **The scan is CLEAN, with 74 output lines** (the 50 of N4b plus two new lines per pair, 24) **and 36 log records** at WARNING and above (nothing in the risk manager logs above INFO; the `IntentLogger` logs a refusal at INFO, which the script's root-logger handling drops).
7. The old-path digests `77421e42...9d10` and `3626ae33...6a6d` stay byte-identical, and the whole-run wall time stays under 15 minutes (predicted 5 to 8).

**Per cell.** The N4b columns are section 90's. "Halt" is `daily_loss_halt`, "AIP" is `already_in_position`; FOK and expired are predicted at section 90's values except where a trade lost to the halt takes its FOK or expiry with it, which I do not predict and leave inside the range. Each row satisfies the identity.

| Candidate | Pair | Signals | N4b trades | Trades N5 (range) | Halt (range) | AIP | FOK | Expired | Unaffordable |
|---|---|---|---|---|---|---|---|---|---|
| C1 | BTCUSDT | 104 | 34 | 31 (26 to 35) | 20 (8 to 35) | 48 | 3 | 2 | 0 |
| C1 | ETHUSDT | 104 | 41 | 37 (31 to 41) | 18 (6 to 32) | 48 | 1 | 0 | 0 |
| C2 | BTCUSDT | 73 | 25 | 23 (19 to 25) | 12 (4 to 22) | 30 | 6 | 2 | 0 |
| C2 | ETHUSDT | 68 | 28 | 26 (22 to 28) | 10 (3 to 20) | 30 | 2 | 0 | 0 |
| C3 | BTCUSDT | 6 | 6 | 5 (3 to 6) | 1 (0 to 3) | 0 | 0 | 0 | 0 |
| C3 | ETHUSDT | 6 | 6 | 5 (3 to 6) | 1 (0 to 3) | 0 | 0 | 0 | 0 |
| C4 | BTCUSDT | 538 | 216 | 205 (175 to 220) | 25 (5 to 60) | 304 | 4 | 0 | 0 |
| C4 | ETHUSDT | 546 | 217 | 205 (175 to 220) | 30 (6 to 70) | 294 | 14 | 3 | 0 |
| C5 | BTCUSDT | 293 | 149 | 144 (125 to 150) | 12 (2 to 35) | 135 | 2 | 0 | 0 |
| C5 | ETHUSDT | 291 | 148 | 143 (125 to 150) | 14 (2 to 40) | 124 | 9 | 1 | 0 |
| C6 | BTCUSDT | 45 | 23 | 21 (17 to 23) | 9 (2 to 18) | 12 | 3 | 0 | 0 |
| C6 | ETHUSDT | 40 | 19 | 17 (14 to 19) | 7 (1 to 15) | 15 | 1 | 0 | 0 |

**Totals.** Trades 862 (790 to 910), against 912 at N4b. `daily_loss_halt` 159 in all (50 to 350). `already_in_position` 1,040 by the rows above, so the two rules together are 1,199, against section 90's `limit_refused` total of 1,149 (the 50 more are the trades predicted lost). **`daily_loss_halt` is non-zero in at least 10 of the 12 cells** (the two C3 cells carry the doubt, at 0 to 3 each).

**The expected dominant rule: `already_in_position`, in 10 of 12 cells** (all but the two C3 cells, where it is 0), **with `daily_loss_halt` second everywhere it is non-zero.** `daily_loss_halt` is expected to exceed `already_in_position` in no cell; the cell where it is closest is C6 BTCUSDT (9 against 12).

**What the halt count settles, and what it cannot (M5n-091).** A non-zero `daily_loss_halt` means the rule fired. Realised loss alone cannot reach 5 percent of equity: a stopped-out position loses about 1 percent (the risk) plus at most 0.28 percent more (the 1.2 percent stop slippage and the exit fee on a notional capped at 20 percent), so two stop-outs inside one UTC day cost about 2.6 percent (REASONED). So every halt needs the committed term, which prices the executor's UNTRAILED stop against the mark, and a non-zero count answers M5n-091 in the affirmative: the daily-loss limit does refuse entries on the strength of a stop the executor never trails. The count cannot say how much of any one halt was the committed term, and it does not say the limit is wrong; whether to settle it differently is the pre-registration's, with the counts in view (the N5 decisions).

**The places a prediction is most likely wrong, named in advance.**

* *The halt counts.* They rest on how long a trend holds a winner far above its stop, which I estimated from the shape of the deltas and not from any count; the ranges are wide on purpose, and the 1d cells could be well above (a bull run holds one position for months at a mark many deltas above the stop, so all of its signals and the other pair's become halts). If the halt is 2 to 3 times my figure, the trades fall with it.
* *The trade counts.* A trade lost to the halt frees later same-pair signals that were `already_in_position`, which can add trades; I predicted a net loss of 1 to 11 per cell and did not model the knock-on.
* *C3.* Six signals a cell and one trend can hold the other pair for months; 0 to 3 halts a cell and 3 to 6 trades.
* *`unaffordable`.* Predicted 0 everywhere because a 20 percent cap leaves free cash above any notional unless another position's mark has run above about 80 percent of equity; a bull run could do that once.
* *The 4h halts.* Sizing is capped at 20 percent of equity below 500 bps, which lowers the committed risk of a 4h position, so I put them at a few percent of refusals; the range is wide.

### The findings this section carries

See the commit message. In short, the manager has no supplied-stop parameter (the percent route is the wiring); its affordability step refuses where the owner's wording says caps; the 20 percent position cap applies and binds below 500 bps; `daily_loss_halt` is checked before `already_in_position`; and the cooldown cannot occur in a backtest.

## 94. M5n N5: the counts-only run with 1-percent risk sizing, section 93's predictions scored, and M5n-091 resolved (P145 C7, R-T, R-DQ, R-DT-3d, R-DT-3e)

An observation log, so this section only adds. `scripts/n4_trade_counts.py` (`0a17f02`, with its tests) was run ONCE: `python scripts/n4_trade_counts.py`, no argument, on `m5n` with a clean tree at `1eb0858`, so the config is the committed `config.m5n.yaml` (SHA-256 `c35bea158e6001c56b49c36f31df79ab1d9bb66ffbba50b9d07a89b87a7bec00`, N5 sizing), the store is `data/historical`, and the window is the committed `[2017-08-17, 2024-01-01)`. Standard output went to `scratch\p145\n5_counts_output.txt` and standard error to `n5_counts_stderr.txt`. It started at `2026-10-25T09:48:06Z` by the machine's UTC clock and ended at `09:53:58Z`: **5 min 52 s of wall time, exit 0, and standard error empty (0 bytes)**. Nothing was written under `deploy\45547f107715`, the rehearsal clone or the canonical store, `config.yaml` is still blob `99b0edd005ff5f452681fc554dcc2271d2e6687e` and `config.s4.yaml` still SHA-256 `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594` (both printed by the halt check at the start of the same command), no venue was asked for anything, and no bar at or after `2024-01-01T00:00:00Z` was read (the 1m path is bounded at the window end, as at N4b). **Nothing here decides anything about S4.**

**The digests of the output.** The file as the shell wrote it, with the Windows line endings the redirection produced (76 carriage returns), has SHA-256 `1b338412dab8796e0ca96b688662fa5d1f6493713ebbe66d5417c10c5abe67b0`; with CRLF turned to LF it is `75d37a1a67bd31a3334220929f572cd52a18de3450b4ff2a5f41d9eaa5c734d1`. The script's own last line, `output_sha256=85f55f5710c8eaa7c6fb2fec7b390b85753edf12d1d6a648a1061f27d126933f`, is the SHA-256 of every line before it joined with LF, and it was re-derived outside the script (`scratch\p145\score_n5.py`) and agrees. **The scan's verdict is `CLEAN`: 74 output lines, each in the grammar, none with a forbidden word, a decimal point or an integer over 99,999, and 36 log records kept at WARNING and above, none flagged.** No run record and no trade file was written.

**A procedural slip, recorded.** The halt check (branch, clean tree, HEAD, the two config digests, worktrees, the time) and the run were issued in one command, which is the shape `M5f-094` says is not a gate: the check's verdict was read, but after the run had been started. The check's printed output, read afterwards, shows every condition held (`m5n`, clean, `1eb0858`, the digests above, one worktree), so the result stands. The next run's checks are their own invocation.

### The output

```
N5 trade counts (R-DT-3d and R-DT-3e outputs only)
window [2017-08-17, 2024-01-01)
candidate C1 donchian_1d_20 (1d)
  run complete=yes problems=0
  BTCUSDT signals=104 trades=34 open_at_end=0 clamp_upper=5 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=65 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=16 already_in_position=49 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=34 fok_refused=3 expired=2 unaffordable=0
  BTCUSDT delta_bps n=104 p10=885 p25=980 p50=1289 p75=1591 p90=1806 min=613 max=2000
  ETHUSDT signals=104 trades=41 open_at_end=0 clamp_upper=22 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=62 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=19 already_in_position=43 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=41 fok_refused=1 expired=0 unaffordable=0
  ETHUSDT delta_bps n=104 p10=1067 p25=1400 p50=1627 p75=1926 p90=2000 min=759 max=2000
candidate C2 donchian_1d_55 (1d)
  run complete=yes problems=0
  BTCUSDT signals=73 trades=25 open_at_end=0 clamp_upper=3 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=40 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=6 already_in_position=34 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=25 fok_refused=6 expired=2 unaffordable=0
  BTCUSDT delta_bps n=73 p10=885 p25=1006 p50=1283 p75=1521 p90=1766 min=648 max=2000
  ETHUSDT signals=68 trades=28 open_at_end=0 clamp_upper=10 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=38 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=7 already_in_position=31 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=28 fok_refused=2 expired=0 unaffordable=0
  ETHUSDT delta_bps n=68 p10=1030 p25=1362 p50=1598 p75=1834 p90=2000 min=849 max=2000
candidate C3 sma_cross_1d_50_200 (1d)
  run complete=yes problems=0
  BTCUSDT signals=6 trades=6 open_at_end=0 clamp_upper=0 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=0 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=0 already_in_position=0 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=6 fok_refused=0 expired=0 unaffordable=0
  BTCUSDT delta_bps n=6 p10=883 p25=901 p50=980 p75=1557 p90=1815 min=883 max=1815
  ETHUSDT signals=6 trades=6 open_at_end=0 clamp_upper=1 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=0 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=0 already_in_position=0 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=6 fok_refused=0 expired=0 unaffordable=0
  ETHUSDT delta_bps n=6 p10=1165 p25=1350 p50=1517 p75=1924 p90=2000 min=1165 max=2000
candidate C4 donchian_4h_20 (4h)
  run complete=yes problems=0
  BTCUSDT signals=538 trades=216 open_at_end=0 clamp_upper=3 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=318 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=42 already_in_position=276 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=216 fok_refused=4 expired=0 unaffordable=0
  BTCUSDT delta_bps n=538 p10=308 p25=410 p50=557 p75=738 p90=994 min=153 max=2000
  ETHUSDT signals=546 trades=215 open_at_end=0 clamp_upper=4 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=314 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=53 already_in_position=261 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=215 fok_refused=14 expired=3 unaffordable=0
  ETHUSDT delta_bps n=546 p10=416 p25=542 p50=692 p75=872 p90=1169 min=208 max=2000
candidate C5 keltner_4h_20_2 (4h)
  run complete=yes problems=0
  BTCUSDT signals=293 trades=149 open_at_end=0 clamp_upper=0 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=142 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=14 already_in_position=128 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=149 fok_refused=2 expired=0 unaffordable=0
  BTCUSDT delta_bps n=293 p10=283 p25=405 p50=528 p75=696 p90=862 min=154 max=1615
  ETHUSDT signals=291 trades=147 open_at_end=0 clamp_upper=0 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=134 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=16 already_in_position=118 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=147 fok_refused=9 expired=1 unaffordable=0
  ETHUSDT delta_bps n=291 p10=394 p25=512 p50=670 p75=849 p90=1079 min=253 max=1866
candidate C6 tsmom_1d_90 (1d)
  run complete=yes problems=0
  BTCUSDT signals=45 trades=23 open_at_end=0 clamp_upper=4 clamp_lower=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=19 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=0 already_in_position=19 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=23 fok_refused=3 expired=0 unaffordable=0
  BTCUSDT delta_bps n=45 p10=771 p25=872 p50=1243 p75=1540 p90=1939 min=679 max=2000
  ETHUSDT signals=40 trades=19 open_at_end=0 clamp_upper=12 clamp_lower=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=20 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=1 already_in_position=19 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=19 fok_refused=1 expired=0 unaffordable=0
  ETHUSDT delta_bps n=40 p10=898 p25=1210 p50=1494 p75=2000 p90=2000 min=722 max=2000
scan verdict=CLEAN output_lines=74 log_records=36
output_sha256=85f55f5710c8eaa7c6fb2fec7b390b85753edf12d1d6a648a1061f27d126933f
```

### Section 93's predictions, scored

**(a) Structural predictions.** All seven held except one.

1. **Signals, clamps and delta quantiles are identical to section 90 in all twelve cells, to the digit: HELD** (compared by `score_n5.py` against the block in section 90).
2. **The identity holds in all twelve cells: HELD.** For example BTCUSDT C1: 104 = 65 (16 + 49) + 34 + 0 + 3 + 2.
3. **Every stage but `limit_refused` is 0 in all twelve cells: HELD,** so the by-rule split is the whole of the refusals, and the rules sum to the stage in every cell (`score_n5.py`).
4. **Only `daily_loss_halt` and `already_in_position` are non-zero among the rules: HELD.** `cooldown`, `max_open_positions`, `no_equity` and `no_mark_price` are 0 in all twelve.
5. **OPEN at the end is 0 in all twelve cells: HELD.**
6. **The scan is CLEAN with 74 output lines and 36 log records: HELD, both figures exact.**
7. **The old-path digests hold and the wall time is under 15 minutes: HELD** (the digests by `test_a_strategy_that_does_not_takes_the_simulated_executor_and_its_digest_holds` and its two-pair sibling in every gate of this milestone; 5 min 52 s against a predicted 5 to 8).

**Unaffordable was predicted 0 everywhere: HELD,** both the manager's stage and the executor's outcome. Whether the 20-percent position cap bound is not in the output and stays UNMEASURED.

**(b) Per cell.** "Inside" means inside the range section 93 stated.

| Candidate | Pair | N4b trades | Trades predicted (range) | Observed | Halt predicted (range) | Observed | AIP predicted | Observed |
|---|---|---|---|---|---|---|---|---|
| C1 | BTCUSDT | 34 | 31 (26 to 35) | 34 inside | 20 (8 to 35) | 16 inside | 48 | 49 |
| C1 | ETHUSDT | 41 | 37 (31 to 41) | 41 inside | 18 (6 to 32) | 19 inside | 48 | 43 |
| C2 | BTCUSDT | 25 | 23 (19 to 25) | 25 inside | 12 (4 to 22) | 6 inside | 30 | 34 |
| C2 | ETHUSDT | 28 | 26 (22 to 28) | 28 inside | 10 (3 to 20) | 7 inside | 30 | 31 |
| C3 | BTCUSDT | 6 | 5 (3 to 6) | 6 inside | 1 (0 to 3) | 0 inside | 0 | 0 |
| C3 | ETHUSDT | 6 | 5 (3 to 6) | 6 inside | 1 (0 to 3) | 0 inside | 0 | 0 |
| C4 | BTCUSDT | 216 | 205 (175 to 220) | 216 inside | 25 (5 to 60) | 42 inside | 304 | 276 |
| C4 | ETHUSDT | 217 | 205 (175 to 220) | 215 inside | 30 (6 to 70) | 53 inside | 294 | 261 |
| C5 | BTCUSDT | 149 | 144 (125 to 150) | 149 inside | 12 (2 to 35) | 14 inside | 135 | 128 |
| C5 | ETHUSDT | 148 | 143 (125 to 150) | 147 inside | 14 (2 to 40) | 16 inside | 124 | 118 |
| C6 | BTCUSDT | 23 | 21 (17 to 23) | 23 inside | 9 (2 to 18) | 0 **under the range** | 12 | 19 |
| C6 | ETHUSDT | 19 | 17 (14 to 19) | 19 inside | 7 (1 to 15) | 1 inside (the edge) | 15 | 19 |

**Totals.** Trades were predicted at 862 (790 to 910) and are **909**, against 912 at N4b: **12 of 12 cells inside their range, and the observed figure is at or above the predicted point in all twelve.** `daily_loss_halt` was predicted at 159 (50 to 350) and is **174: 11 of 12 cells inside.** `already_in_position` was predicted at 1,040 and is **978**. The two rules together are **1,152**, which is section 90's `limit_refused` total of 1,149 plus the 3 trades that did not happen.

**The expected dominant rule: HELD.** `already_in_position` is the largest rule in all ten cells where either fires, and `daily_loss_halt` is second wherever it is non-zero and exceeds it in no cell. The two C3 cells have no refusal of either kind.

**Two predictions missed.** **`daily_loss_halt` is non-zero in 9 of the 12 cells, where 10 or more were predicted:** the zeros are both C3 cells (predicted 0 to 3, the doubt section 93 named) and **C6 BTCUSDT, which was predicted at 9 (2 to 18) and is 0.** And **the trades fell by 3, where 50 were predicted** (1 to 11 a cell): C4 ETHUSDT by 2 and C5 ETHUSDT by 1, and the other ten cells did not move.

### M5n-091, resolved

`M5n-091` asked whether the daily-loss limit, pricing a stop the executor never trails, was refusing entries in section 90's `limit_refused` counts. **It was, and it is now measured: `daily_loss_halt` refused 174 of the 1,152 signals the limits refused (15.1 percent), in 9 of the 12 cells, and it is the second rule everywhere it fires.** The attribution to the untrailed stop is REASONED, not measured, and rests on section 93's bound: realised loss alone cannot reach 5 percent of equity at 1 percent risk on two pairs (about 1.3 percent a stopped-out trade, so about 2.6 percent in one UTC day), so every halt needed the committed term, which prices the executor's untrailed `Position.stop_loss` against the mark. The synthetic world of `test_a_winner_on_an_untrailed_stop_halts_every_entry_including_its_own_pair` shows the mechanism with nothing realised. What the counts do not say is how much of any one halt was the committed term.

**What the halt changed is small, and that is the finding that matters for the pre-registration.** Net of everything, **the halts cost 3 trades out of 912** (C4 ETHUSDT 217 to 215, C5 ETHUSDT 148 to 147): the other 171 halted signals fell where the position was held or would have been refused as `already_in_position` anyway. That is a net figure; a halted signal that would have been a trade and a later one that became a trade because of it cancel inside it, and the counts cannot separate them. FOK-refused (45) and expired (8) entries are unchanged from section 90 in total, so `M5n-111` and `M5n-112` are neither helped nor worsened by N5.

### Diagnoses

* **The halt is larger than predicted on 4h and smaller on 1d.** C4 and C5 halted 42, 53, 14 and 16 against 25, 30, 12 and 14; C1, C2 and C6 halted 16, 19, 6, 7, 0 and 1 against 20, 18, 12, 10, 9 and 7. Section 93 reasoned that the 20-percent position cap lowers a 4h position's committed risk and put the 4h halts low. The cap evidently does not stop a 4h winner from sitting many deltas above its untrailed stop in the 2017 and 2021 runs, where a 4h trade can hold for weeks. REASONED from the counts; the dates and the marks are not printed and were not looked at.
* **C6 BTCUSDT at 0.** Its 19 refused signals are all `already_in_position`. A time-series-momentum entry on BTCUSDT may be held through trends that never reach about four deltas above the stop, or its held spans may not overlap the other pair's. UNMEASURED, and not diagnosed further, because the diagnostic would print a date or a mark outside R-DT-3e's list.
* **The trade losses were over-predicted for a reason worth keeping.** Section 93 expected a halted entry to cost its trade. The counts say a halt rarely cost an entry: a signal on a flat pair is halted only while the OTHER pair sits far above its stop, and net of any knock-on that happened on 3 signals in 912. Which halted signals were held-pair signals and which were flat-pair signals is not printed; REASONED from the net figure, not measured.
* **The owner's clamp note counts signals, not trades.** The charter's clamp note reads *"C1 ETHUSDT, 22 of 41 trades at 2000 bps"*. The line printed here and in section 90 is `ETHUSDT signals=104 trades=41 ... clamp_upper=22`: **22 of 104 SIGNALS were clamped**, and how many of the 41 entered trades were is not printed (a clamp count by entered trade is not on the R-DT-3d or R-DT-3e list). The note's conclusion, that the upper clamp binds often on ETHUSDT 1d, stands on 22 of 104; its fraction does not. The pre-registration should quote it from the line.

### What these counts are, and are not

They are the number of times each rule, as ruled, said "enter" over the in-sample window, the number of times the unchanged risk manager refused it and under which rule, and what the executor did with the rest. **They are not a verdict on any candidate**: no return, equity or P&L was printed, and the simulation's own figures were kept in memory and discarded. A limit that dominates refusals is, by the N5 decisions, settled in the pre-registration with these counts in view and not tuned here; on these counts it is `already_in_position`, which is structural (this system does not add to a position) and not a limit anyone would tune, and the daily-loss halt, which is a limit, accounts for 15 percent of the refusals and 3 trades.

## 95. M5n N5: the predictions for the arming audit of the N5 code, before it is run (P145 C8, R-T, R-DQ)

An observation log, so this section only adds. P145 proves that the tests written for N5 bite: the 191 tests of `tests/unit/test_d1_risk.py`, `test_d1_executor.py`, `test_backtest_d1.py`, `test_n4_trade_counts.py` and `test_config_m5n.py`, against the code of `backtesting/d1_risk.py` (new), the executor choice in `backtesting/engine.py`, the tally by rule in `backtesting/d1_executor.py`, `scripts/n4_trade_counts.py` and `config.m5n.yaml`. **This section is committed before the survey is run.** It decides nothing about S4.

### The method

The harness is the repository's `scripts/worktree_survey.py` with `scripts/survey_hook.py`, as in section 91: a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven inside it before any result counts, an unmutated baseline predicted green (191 passed), every mutation byte-exact with exactly one match, asserted both when the spec was generated and when it runs, every restore shown SHA-equal, and the worktree removed afterwards. A MORE is recorded and a FEWER halts the survey. The spec is `survey_n5.json` (SHA-256 `056f32d60c29a7101ba94afd4859352e992a7d4321f63ac14d7116835ea0176c`), generated by the same program as the table below, so the two cannot differ; the test list is the `pytest --collect-only` of the five files at `9431958` (191 node ids). The three config mutations that change a file the tests load were also loaded in memory under the real `AppConfig` when the spec was generated, so the prediction that one loads and another does not is a measurement of the loader and not a guess. No test was run on a mutated tree.

### Totals

**27 mutations and 89 predicted failures.** The predictions come from reading each test's fixture and assertion, not its name (`M5h`).

**Mutations predicted to fail nothing, four.**

* `q02` (a non-BUY signal with an integer delta is delegated to a per-delta manager) is equivalent: the exit path of the base class reads no stop, so a `CLOSE` gives the same assessment under either manager.
* `q03` (a signal is delegated while stops are off) is equivalent: the per-delta copy keeps `enabled=false`, so it is the base manager.
* `q17` (the outcomes line swaps the FOK-refused and expired counts) is **unobservable in the tests, and that is a hole and not an equivalence**: no test world has a non-zero FOK-refused or expired entry, so the swap prints the same zeros. It is declared here and is not closed by this section.
* `q27` (the placeholder percent is 2.0) is deliberately pinned by no test, because nothing may depend on the placeholder's value; `q08` below is what shows that no test reads a stop the file supplies.

**Tests predicted to be killed by no mutation: 131 of 191.** By file: `test_d1_risk.py` 9 of 27, `test_d1_executor.py` 54 of 61, `test_backtest_d1.py` 17 of 25, `test_n4_trade_counts.py` 49 of 64 and `test_config_m5n.py` 2 of 14. They are accounted for by family, because an undeclared pass is indistinguishable from coverage:

* **`test_d1_risk.py`, nine.** `test_no_equity` and `test_no_mark_price` pin that the BASE rule still refuses, which no mutation of the delegate reaches; the other seven pin what is left to the base class and are spared by the equivalent mutations or by a weaker one: `test_it_overrides_evaluate_and_nothing_else_of_the_base` (a structural test no one-line mutation of a method body changes), `test_a_signal_without_a_delta_is_evaluated_by_the_base_configuration`, the `"1000"` and `1000.0` rows of `test_only_an_integer_delta_is_a_delta` (`q01` swaps `type(...) is` for `isinstance`, and among `True`, a string and a float only `True` is an `int`), `test_a_non_buy_is_evaluated_by_the_base_class` (`q02` is equivalent), `test_with_stops_off_it_is_the_base_manager_exactly` (`q03` is equivalent) and the `-5` row of the raises test (`q04` moves the bound to `< 0`, which still raises for `-5`).
* **`test_d1_executor.py`, 54, `test_backtest_d1.py`, 17, and `test_n4_trade_counts.py`, 49.** These are the tests written for N4b, surveyed at P144 against the code before N5 (section 92), plus the new tests whose subject no mutation here reaches: the scan's refused rows and its accepted rows, which are guarded twice (the grammar and then the vocabulary or the integer bound), so that removing either guard leaves each row refused by the other; the four rule labels that hold no forbidden word (`no_mark_price` is also a stage and stays exempt, and `already_in_position`, `cooldown` and `max_open_positions` hold none), which `q15` therefore spares; the quantile, window and no-writer tests; and the world tests that compare no value `q18` to `q22` change. In `test_backtest_d1.py` the exceptions are the D1 worlds that run with stops off, for which the delegating manager is the base manager.
* **`test_config_m5n.py`, two.** The secret and line-ending tests read text and bytes and no setting.

**Failures that are crashes and not kills, predicted and counted** (the harness counts every failing test): all twelve of `q24`, each a `ValidationError` raised by the loader inside `loaded()` and not an assertion. **A crash is not a kill under `M5i-115`,** so `q24` credits no test with biting; `q23`, `q25` and `q26` are the config mutations that kill by assertion, and `q25` and `q26` are the ones the assertion changed at P145's commit C6 has to be killed through (the ruled-overturn authority's *"the mutation survey still kills through it"*).

**Where a prediction is most likely to be wrong, named in advance.**

* `q10`, the wall clock in a per-delta manager. It rests on the default staleness bound (180 s, `config/models.py:353`, MEASURED) being far smaller than the gap between the tests' fixed instant, 2026-07-25, and this machine's date; if the bound is wider, or if a day roll on a wall-clock ledger raises where I expect it to roll, the set changes. The tests with no open position, no cooldown and no realised figure are predicted to pass because they read no clock; `no_mark_price` is checked before staleness.
* `q15`, the rule names left unexempt. 13 tests are predicted, and the two I left out on reasoning rather than a run are `test_two_runs_print_the_same_bytes` (an all-FAILED output is the same twice) and `test_the_output_has_no_decimal_point_and_no_money_word` (the one-line FAILED verdict holds no money word).
* `q05`, where I worked the sizing of `test_a_size_the_free_quote_cannot_pay_for_is_refused_at_unaffordable` by hand and predicted that it PASSES (the 20-percent cap still leaves a cost far above the free quote), and that `test_the_lower_clamp_is_cut_by_the_position_cap` in the backtest passes (a tenth-sized stop at delta 10 is still under the cap).
* `q08`, where `test_the_loss_at_the_stop_is_at_most_one_percent_of_equity_when_the_cap_is_slack` is predicted to PASS although every stop is wrong: it is **risk-normalised**, so for any single stop the loss is one percent. That is a test that cannot see the width of the stop, and it is declared here.
* `q09`, where the delta-2000 world and the rule worlds are predicted to pass because the plain manager's placeholder is 20.0.
* `q26`, a take-profit in the file, predicted to load (two protective legs, call cap still 3), which the in-memory load confirmed.

### Predicted failures

| Mutation | The break | Predicted failures | Tests |
|---|---|---|---|
| q01 | a bool counts as an integer delta (isinstance in place of the exact type) | 1 | N20 |
| q02 | a non-BUY signal with an integer delta is evaluated by a per-delta manager as well | 0 | none |
| q03 | a signal is delegated to a per-delta manager while stops are off | 0 | none |
| q04 | a delta of zero is not refused | 1 | N25 |
| q05 | the percent is delta / 1000, a tenth of the trail | 10 | N1, N2, N3, N4, N5, N6, N7, N9, N94, N95 |
| q06 | the file's stop type is kept, so an ATR file sizes from an ATR stop | 1 | N6 |
| q07 | no per-delta manager is kept | 1 | N27 |
| q08 | the per-delta manager is built over the unchanged config, so every stop is the file's placeholder | 7 | N2, N3, N5, N6, N7, N94, N96 |
| q09 | the D1 path is built a plain manager and every other path a D1 manager | 5 | N89, N90, N91, N94, N96 |
| q10 | a per-delta manager reads the wall clock and not the injected one | 10 | N8, N9, N11, N12, N13, N14, N15, N16, N98, N99 |
| q11 | no rule is ever tallied | 10 | N67, N68, N69, N70, N71, N72, N77, N98, N99, N114 |
| q12 | a rule is tallied only under the limit_refused stage, so no_mark_price loses its rule | 1 | N67 |
| q13 | the snapshot hands out the live rules dict | 1 | N77 |
| q14 | a rule's count is set to one and not added to | 6 | N67, N68, N69, N70, N71, N72 |
| q15 | rule names are not exempt from the forbidden-word scan | 13 | N114, N115, N118, N119, N120, N121, N122, N123, N135, N138, N139, N174, N175 |
| q16 | the grammar accepts a rules line with no count | 1 | N152 |
| q17 | the outcomes line swaps the FOK-refused and expired counts | 0 | none |
| q18 | every rule count is printed as zero | 1 | N114 |
| q19 | the filled outcome prints the trade count | 1 | N114 |
| q20 | the FOK-refused outcome counts the filled entries | 1 | N114 |
| q21 | the last rule is not printed | 1 | N114 |
| q22 | the rules are printed in reverse of the enum's order | 2 | N114, N143 |
| q23 | the file risks 2 percent of equity | 1 | N181 |
| q24 | the stop is disabled while risk_per_trade sizing is on, which the config refuses at load | 12 | N178, N179, N180, N181, N182, N183, N186, N187, N188, N189, N190, N191 |
| q25 | a trailing stop is enabled | 1 | N180 |
| q26 | a take-profit is enabled | 1 | N180 |
| q27 | the placeholder percent is 2.0 | 0 | none |

### The test key (every code the table uses)

The codes are the tests in collection order, N1 to N191.

| Code | Test |
|---|---|
| N1 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_upper_bound_risks_one_percent_at_a_stop_twenty_percent_below` |
| N2 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_a_middle_trail` |
| N3 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_lower_bound_is_cut_by_the_twenty_percent_position_cap` |
| N4 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_loss_at_the_stop_is_at_most_one_percent_of_equity_when_the_cap_is_slack` |
| N5 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_stop_is_the_signals_delta_and_not_the_placeholder` |
| N6 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_stop_type_in_the_file_does_not_matter` |
| N7 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_a_delta_is_an_exact_decimal_percent` |
| N8 | `d1_risk`: `TestTheQuoteBalanceRefusesAndDoesNotShrink::test_a_size_the_free_quote_cannot_pay_for_is_refused_at_unaffordable` |
| N9 | `d1_risk`: `TestTheQuoteBalanceRefusesAndDoesNotShrink::test_the_same_size_is_approved_when_the_cash_is_there` |
| N10 | `d1_risk`: `TestEveryRuleStillRefuses::test_no_equity` |
| N11 | `d1_risk`: `TestEveryRuleStillRefuses::test_daily_loss_halt_from_realised_loss` |
| N12 | `d1_risk`: `TestEveryRuleStillRefuses::test_daily_loss_halt_from_committed_risk_alone_on_an_untrailed_stop` |
| N13 | `d1_risk`: `TestEveryRuleStillRefuses::test_the_halt_is_checked_before_already_in_position` |
| N14 | `d1_risk`: `TestEveryRuleStillRefuses::test_already_in_position` |
| N15 | `d1_risk`: `TestEveryRuleStillRefuses::test_cooldown` |
| N16 | `d1_risk`: `TestEveryRuleStillRefuses::test_max_open_positions` |
| N17 | `d1_risk`: `TestEveryRuleStillRefuses::test_no_mark_price` |
| N18 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_it_overrides_evaluate_and_nothing_else_of_the_base` |
| N19 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_signal_without_a_delta_is_evaluated_by_the_base_configuration` |
| N20 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_only_an_integer_delta_is_a_delta[True]` |
| N21 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_only_an_integer_delta_is_a_delta[1000]` |
| N22 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_only_an_integer_delta_is_a_delta[1000.0]` |
| N23 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_non_buy_is_evaluated_by_the_base_class` |
| N24 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_with_stops_off_it_is_the_base_manager_exactly` |
| N25 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_delta_that_is_not_a_distance_raises[0]` |
| N26 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_delta_that_is_not_a_distance_raises[-5]` |
| N27 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_one_manager_is_kept_per_delta` |
| N28 | `d1_executor`: `TestTheExitInTheEntryBar::test_a_trail_that_triggers_in_the_entry_bar_is_booked_in_that_callback` |
| N29 | `d1_executor`: `TestTheExitInTheEntryBar::test_the_entry_minutes_high_counts_toward_the_peak` |
| N30 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_after_the_bar_is_not_booked_until_the_clock_reaches_it` |
| N31 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_at_exactly_the_clock_is_booked` |
| N32 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_one_minute_past_the_clock_waits` |
| N33 | `d1_executor`: `TestTheExitIsScheduled::test_the_exit_is_booked_before_a_signal_on_the_next_bar_can_see_it` |
| N34 | `d1_executor`: `TestTheExitIsScheduled::test_two_pairs_book_in_time_order_not_in_callback_order` |
| N35 | `d1_executor`: `TestTheExitIsScheduled::test_overlapping_positions_hold_one_ledger` |
| N36 | `d1_executor`: `TestAPositionThatNeverTriggers::test_it_stays_open_at_the_end` |
| N37 | `d1_executor`: `TestAPositionThatNeverTriggers::test_a_trigger_after_the_window_end_is_never_read` |
| N38 | `d1_executor`: `TestAPositionThatNeverTriggers::test_finish_is_idempotent` |
| N39 | `d1_executor`: `TestAGapInTheMinutePath::test_a_fall_inside_the_gap_exits_at_the_next_traded_open` |
| N40 | `d1_executor`: `TestAGapInTheMinutePath::test_a_gap_that_recovers_leaves_the_position_open` |
| N41 | `d1_executor`: `TestAGapInTheMinutePath::test_a_decision_bar_gap_flags_the_trade` |
| N42 | `d1_executor`: `TestZeroVolumeMinutes::test_a_filler_minute_is_not_a_trade_and_is_not_walked` |
| N43 | `d1_executor`: `TestZeroVolumeMinutes::test_a_bar_with_no_traded_minute_cannot_fill` |
| N44 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_open_above_the_limit_is_refused` |
| N45 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_a_missing_next_slot_expires_the_entry` |
| N46 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_entry_the_data_ends_on_expires` |
| N47 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_entry_the_ledger_cannot_pay_for_is_unaffordable` |
| N48 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_a_second_entry_while_one_is_pending_is_ignored` |
| N49 | `d1_executor`: `TestThePositionItOpens::test_the_initial_stop_is_the_fill_less_the_trail` |
| N50 | `d1_executor`: `TestThePositionItOpens::test_it_is_stamped_active_at_the_simulated_instant` |
| N51 | `d1_executor`: `TestThePositionItOpens::test_a_position_on_another_pair_is_stamped_on_every_bar` |
| N52 | `d1_executor`: `TestTheTally::test_every_signal_is_counted_with_its_delta_and_clamp` |
| N53 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unknown_pair]` |
| N54 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[no_reference_price]` |
| N55 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[nothing_to_close]` |
| N56 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unsupported_action]` |
| N57 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[no_mark_price]` |
| N58 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[position_stale]` |
| N59 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[committed_risk_unknown]` |
| N60 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[limit_refused]` |
| N61 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[live_order_list]` |
| N62 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unmanaged_holding]` |
| N63 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[atr_unavailable]` |
| N64 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[stop_unplaceable]` |
| N65 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[size_not_tradeable]` |
| N66 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unaffordable]` |
| N67 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[no_mark_price]` |
| N68 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[no_equity]` |
| N69 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[daily_loss_halt]` |
| N70 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[already_in_position]` |
| N71 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[cooldown]` |
| N72 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[max_open_positions]` |
| N73 | `d1_executor`: `TestTheTally::test_a_refusal_after_the_limits_carries_no_rule[size_not_tradeable]` |
| N74 | `d1_executor`: `TestTheTally::test_a_refusal_after_the_limits_carries_no_rule[unaffordable]` |
| N75 | `d1_executor`: `TestTheTally::test_a_refusal_with_no_decision_carries_no_rule` |
| N76 | `d1_executor`: `TestTheTally::test_an_approved_entry_adds_no_rule` |
| N77 | `d1_executor`: `TestTheTally::test_rules_are_tallied_per_pair_and_the_snapshot_is_a_copy` |
| N78 | `d1_executor`: `TestTheTally::test_pairs_are_tallied_apart` |
| N79 | `d1_executor`: `TestTheTally::test_the_snapshot_is_a_copy` |
| N80 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[None]` |
| N81 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[500.0]` |
| N82 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[500]` |
| N83 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[True]` |
| N84 | `d1_executor`: `TestWhatItRefusesToDispatch::test_an_approved_exit_raises` |
| N85 | `d1_executor`: `TestTheContract::test_it_satisfies_the_dispatcher_port` |
| N86 | `d1_executor`: `TestTheContract::test_the_metadata_keys_are_the_ones_the_strategies_write` |
| N87 | `d1_executor`: `TestTheContract::test_two_runs_of_the_same_history_give_the_same_trade_log` |
| N88 | `d1_executor`: `TestTheContract::test_the_module_reads_no_wall_clock` |
| N89 | `backtest_d1`: `TestTheChoice::test_a_strategy_that_declares_the_exit_takes_the_d1_executor` |
| N90 | `backtest_d1`: `TestTheChoice::test_a_strategy_that_does_not_takes_the_simulated_executor_and_its_digest_holds` |
| N91 | `backtest_d1`: `TestTheChoice::test_the_old_path_holds_on_two_pairs_too` |
| N92 | `backtest_d1`: `TestTheChoice::test_no_series_is_asked_for_past_the_window_end` |
| N93 | `backtest_d1`: `TestTheChoice::test_a_mix_of_declaring_and_other_strategies_is_refused` |
| N94 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_a_trail_of_1000_risks_one_percent` |
| N95 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_upper_clamp_sizes_from_a_twenty_percent_stop` |
| N96 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_lower_clamp_is_cut_by_the_position_cap` |
| N97 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_same_world_without_n5_is_sized_by_the_fixed_fraction` |
| N98 | `backtest_d1`: `TestRefusalsByRuleThroughTheWholeChain::test_a_second_signal_while_held_is_already_in_position` |
| N99 | `backtest_d1`: `TestRefusalsByRuleThroughTheWholeChain::test_a_winner_on_an_untrailed_stop_halts_every_entry_including_its_own_pair` |
| N100 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_run_is_complete_and_the_cash_identity_holds[4h]` |
| N101 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_run_is_complete_and_the_cash_identity_holds[1d]` |
| N102 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_each_pair_books_its_own_exit_at_the_hand_worked_price[4h]` |
| N103 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_each_pair_books_its_own_exit_at_the_hand_worked_price[1d]` |
| N104 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_positions_overlap_and_the_earlier_exit_is_booked_first[4h]` |
| N105 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_positions_overlap_and_the_earlier_exit_is_booked_first[1d]` |
| N106 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_a_signal_while_in_position_is_a_limit_refusal[4h]` |
| N107 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_a_signal_while_in_position_is_a_limit_refusal[1d]` |
| N108 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_second_entry_is_still_open_at_the_end[4h]` |
| N109 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_second_entry_is_still_open_at_the_end[1d]` |
| N110 | `backtest_d1`: `TestAGapWhilePositionsAreOpen::test_a_missing_decision_bar_and_minutes_with_a_fall_exit_at_the_next_open` |
| N111 | `backtest_d1`: `TestAGapWhilePositionsAreOpen::test_the_same_gap_without_a_fall_leaves_the_position_open` |
| N112 | `backtest_d1`: `TestTheRealCandidate::test_a_quiet_breakout_clamps_to_the_lower_bound_and_stays_open` |
| N113 | `backtest_d1`: `TestTheRealCandidate::test_a_wild_breakout_clamps_to_the_upper_bound` |
| N114 | `n4_trade_counts`: `TestTheRun::test_the_output_is_exactly_the_schema` |
| N115 | `n4_trade_counts`: `TestTheRun::test_the_last_line_is_the_hash_of_every_line_before_it` |
| N116 | `n4_trade_counts`: `TestTheRun::test_the_output_has_no_decimal_point_and_no_money_word` |
| N117 | `n4_trade_counts`: `TestTheRun::test_two_runs_print_the_same_bytes` |
| N118 | `n4_trade_counts`: `TestTheRun::test_it_writes_no_run_record_and_no_trade_file` |
| N119 | `n4_trade_counts`: `TestTheRun::test_it_opens_no_file_for_writing` |
| N120 | `n4_trade_counts`: `TestTheRun::test_nothing_the_run_logs_reaches_a_handler_or_a_terminal` |
| N121 | `n4_trade_counts`: `TestTheRun::test_a_warning_logged_during_the_run_is_kept_and_counted_and_never_shown` |
| N122 | `n4_trade_counts`: `TestTheRun::test_a_narrower_window_is_accepted_and_named` |
| N123 | `n4_trade_counts`: `TestTheRun::test_a_run_that_is_not_complete_says_so_and_exits_one` |
| N124 | `n4_trade_counts`: `TestTheQuantiles::test_nearest_rank_on_ten_values` |
| N125 | `n4_trade_counts`: `TestTheQuantiles::test_a_single_value_is_every_quantile` |
| N126 | `n4_trade_counts`: `TestTheQuantiles::test_the_line_sorts_its_values_and_prints_the_extremes` |
| N127 | `n4_trade_counts`: `TestTheWindow::test_the_constants_are_the_committed_ones` |
| N128 | `n4_trade_counts`: `TestTheWindow::test_the_candidates_are_the_six_in_r_dys_order` |
| N129 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv0]` |
| N130 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv1]` |
| N131 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv2]` |
| N132 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv3]` |
| N133 | `n4_trade_counts`: `TestTheWindow::test_a_naive_window_is_refused` |
| N134 | `n4_trade_counts`: `TestTheWindow::test_the_whole_committed_window_is_accepted` |
| N135 | `n4_trade_counts`: `TestTheScan::test_the_lines_the_schema_makes_pass` |
| N136 | `n4_trade_counts`: `TestTheScan::test_a_stage_named_for_a_price_is_a_stage_and_not_a_figure` |
| N137 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[no_mark_price]` |
| N138 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[no_equity]` |
| N139 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[daily_loss_halt]` |
| N140 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[already_in_position]` |
| N141 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[cooldown]` |
| N142 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[max_open_positions]` |
| N143 | `n4_trade_counts`: `TestTheScan::test_the_rule_names_are_the_risk_managers` |
| N144 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1.5 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0]` |
| N145 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules loss=1]` |
| N146 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules daily_loss=1]` |
| N147 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules daily_loss_halt=1.5]` |
| N148 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules daily_loss_halt=100000]` |
| N149 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules equity=1]` |
| N150 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT entry_outcomes filled=1 fok_refused=0 expired=0 unaffordable=0 fee=1]` |
| N151 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT entry_outcomes filled=1 fok_refused=0]` |
| N152 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules]` |
| N153 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT mean_return=1]` |
| N154 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT delta_bps n=1 p10=100000 p25=1 p50=1 p75=1 p90=1 min=1 max=1]` |
| N155 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 price_1d (1d)]` |
| N156 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 realised_1d (1d)]` |
| N157 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 donchian_1d_20 (1d) equity]` |
| N158 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  run complete=yes problems=0 ]` |
| N159 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[]` |
| N160 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[window [2017-08-17, 2024-01-01) caf\xe9]` |
| N161 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT balance 42000]` |
| N162 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[output_sha256=XYZ]` |
| N163 | `n4_trade_counts`: `TestTheScan::test_the_count_is_per_line` |
| N164 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[BTCUSDT/4h: 1 bar(s) missing between 2017-09-06T16:00:00+00:00 and 2017-09-06T20:00:00+00:00]` |
| N165 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[Entry for ETHUSDT ignored: an entry is pending or a position is held]` |
| N166 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[stream handler failed for BTCUSDT 4h]` |
| N167 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[Risk approved BTCUSDT: 2.00330000 at 98.10000000]` |
| N168 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[free quote 10000.5]` |
| N169 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[filled at 42000]` |
| N170 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[balance is low]` |
| N171 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[the realised total moved]` |
| N172 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[cost $5]` |
| N173 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[price 100]` |
| N174 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_a_line_the_grammar_refuses_is_not_printed` |
| N175 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_a_log_record_that_carries_a_figure_fails_the_scan_and_is_not_printed` |
| N176 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_an_exception_is_reported_by_class_and_place_and_never_by_message` |
| N177 | `n4_trade_counts`: `TestTheScript::test_it_has_no_fetcher_and_never_writes` |
| N178 | `config_m5n`: `TestItEnablesNothingLive::test_it_loads_under_the_real_config_model` |
| N179 | `config_m5n`: `TestItEnablesNothingLive::test_the_mode_is_backtest` |
| N180 | `config_m5n`: `TestItEnablesNothingLive::test_no_target_and_no_trailing_percent_is_enabled_and_the_stop_is_for_sizing_only` |
| N181 | `config_m5n`: `TestItEnablesNothingLive::test_the_sizing_is_one_percent_risked_at_the_stop` |
| N182 | `config_m5n`: `TestItEnablesNothingLive::test_every_other_risk_setting_is_a_default` |
| N183 | `config_m5n`: `TestItEnablesNothingLive::test_no_notification_and_no_log_file` |
| N184 | `config_m5n`: `TestItEnablesNothingLive::test_it_carries_no_secret` |
| N185 | `config_m5n`: `TestItEnablesNothingLive::test_the_file_is_lf_only` |
| N186 | `config_m5n`: `TestThePairsAndTheWindow::test_the_pairs_are_btcusdt_and_ethusdt_daily_and_enabled` |
| N187 | `config_m5n`: `TestThePairsAndTheWindow::test_the_window_is_the_in_sample_span_ending_at_the_boundary` |
| N188 | `config_m5n`: `TestThePairsAndTheWindow::test_the_fee_is_ten_basis_points_per_side_as_a_decimal` |
| N189 | `config_m5n`: `TestThePairsAndTheWindow::test_the_slippage_figures_are_the_shipped_ones` |
| N190 | `config_m5n`: `TestThePairsAndTheWindow::test_the_data_directory_is_the_mainnet_archive` |
| N191 | `config_m5n`: `TestTheStrategyIsACandidate::test_it_names_one_of_the_six` |


## 96. M5n N5: the arming-audit survey of the N5 code, scored against section 95 (P145 C9, R-T)

An observation log, so this section only adds. The survey ran as section 95 describes, with the repository's `scripts/worktree_survey.py` and `scripts/survey_hook.py`, in a detached worktree outside the repository (`scratch\p145\wt_survey`) at `1ffed99` (the commit that carries section 95), the import location of `trading_bot` and `tests` printed inside the worktree before any result (`...\wt_survey\src\trading_bot\__init__.py` and `...\wt_survey\tests\__init__.py`), an unmutated baseline of **191 passed in 14.40 s**, every restore shown SHA-equal, every copied file intact afterwards, and `git worktree list` showing the main worktree only. It ran once, `2026-10-25T10:02:25Z` to `10:09:34Z` (7 min 9 s), exit 0, standard error empty, from the committed spec (`survey_n5.json`, SHA-256 as section 95 records it). Nothing here decides anything about S4.

### Totals

**27 mutations: 27 MATCH, 0 MORE, 0 FEWER. Predicted failures 89, observed 89.** The four mutations predicted to fail nothing (`q02`, `q03`, `q17`, `q27`) failed nothing. No halt fired.

**Tests killed by no mutation: 131 of 191, exactly as predicted.** 60 distinct tests failed under at least one mutation, and **10 of them fail only by a crash and not by an assertion**: ten of `q24`'s twelve, each a `pydantic_core.ValidationError` raised by the loader inside `loaded()` (the two it shares with `q23`, `q25` and `q26` are also killed by an assertion). By `M5i-115` those ten are not credited as kills, so **50 tests were killed by an assertion at least once and 141 were not**: the 131 and the ten. By file, the unkilled counts are the ones section 95 gave (9, 54, 17, 49 and 2), and the survey adds nothing to them.

**A clean sweep is not evidence the tests are good, and the reason is worth stating.** Every prediction was made after the tests were written and from their fixtures, which section 91's `M5e-051` says is the case in which the prediction is least independent of the result. The two things that make this survey more than a transcript of the tests are the ones section 95 declared before it ran: the equivalents (`q02`, `q03`) and the holes (`q17`, `q27`), which the survey confirmed rather than closed.

### What the survey leaves unpinned, and does not fix

* **`q17` is a hole, and it is the one that matters for N5's own output.** Swapping the `fok_refused` and `expired` fields of the entry-outcomes line fails no test, because no test world has a non-zero FOK-refused or expired entry. The N5 run printed 45 FOK-refused and 8 expired entries (section 94); the executor's own entry-outcome tests (`TestAnEntryThatDoesNotFill`, not re-read for this section) stand behind how the two are counted, but the script's mapping of them onto the printed line is pinned for `filled` (`q19`) and for `fok_refused` only as a mislabelled field (`q20`, which reads the filled count), and for `expired` and `unaffordable` by nothing. A test world with one FOK-refused and one expired entry would close it. It was not written here, because a test added after the survey is a test the survey did not see.
* **`q08` shows the loss-at-the-stop test cannot see the width of a stop** (section 95's `M5n-146`), and `q08` is the only mutation in this survey that hands every signal the same stop; the tests that kill it are the ones that assert a stop level or a quantity.
* **`q27`: nothing depends on the placeholder percent of 20.0**, which is what the file's comment says and what the survey now shows.

### The ruled-overturn authority, discharged

The assertion changed at P145's commit C6, in `test_config_m5n.py`, is killed by assertion through `q25` (a trailing stop enabled) and `q26` (a take-profit enabled), and the file's new sizing test by `q23`. The owner's condition, *"the mutation survey still kills through it"*, is met.

### Every mutation

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| q01 | a bool counts as an integer delta (isinstance in place of the exact type) | 1 | 1 | MATCH |
| q02 | a non-BUY signal with an integer delta is evaluated by a per-delta manager as well | 0 | 0 | MATCH |
| q03 | a signal is delegated to a per-delta manager while stops are off | 0 | 0 | MATCH |
| q04 | a delta of zero is not refused | 1 | 1 | MATCH |
| q05 | the percent is delta / 1000, a tenth of the trail | 10 | 10 | MATCH |
| q06 | the file's stop type is kept, so an ATR file sizes from an ATR stop | 1 | 1 | MATCH |
| q07 | no per-delta manager is kept | 1 | 1 | MATCH |
| q08 | the per-delta manager is built over the unchanged config, so every stop is the file's placeholder | 7 | 7 | MATCH |
| q09 | the D1 path is built a plain manager and every other path a D1 manager | 5 | 5 | MATCH |
| q10 | a per-delta manager reads the wall clock and not the injected one | 10 | 10 | MATCH |
| q11 | no rule is ever tallied | 10 | 10 | MATCH |
| q12 | a rule is tallied only under the limit_refused stage, so no_mark_price loses its rule | 1 | 1 | MATCH |
| q13 | the snapshot hands out the live rules dict | 1 | 1 | MATCH |
| q14 | a rule's count is set to one and not added to | 6 | 6 | MATCH |
| q15 | rule names are not exempt from the forbidden-word scan | 13 | 13 | MATCH |
| q16 | the grammar accepts a rules line with no count | 1 | 1 | MATCH |
| q17 | the outcomes line swaps the FOK-refused and expired counts | 0 | 0 | MATCH |
| q18 | every rule count is printed as zero | 1 | 1 | MATCH |
| q19 | the filled outcome prints the trade count | 1 | 1 | MATCH |
| q20 | the FOK-refused outcome counts the filled entries | 1 | 1 | MATCH |
| q21 | the last rule is not printed | 1 | 1 | MATCH |
| q22 | the rules are printed in reverse of the enum's order | 2 | 2 | MATCH |
| q23 | the file risks 2 percent of equity | 1 | 1 | MATCH |
| q24 | the stop is disabled while risk_per_trade sizing is on, which the config refuses at load | 12 | 12 | MATCH; crash: ValidationError |
| q25 | a trailing stop is enabled | 1 | 1 | MATCH |
| q26 | a take-profit is enabled | 1 | 1 | MATCH |
| q27 | the placeholder percent is 2.0 | 0 | 0 | MATCH |


## 97. M5n P146: what a RiskManager keeps after construction, and the predictions for the cap-binding count, before any code (P146 C2, R-T, R-DQ)

An observation log, so this section only adds. HEAD is `06fa1f8` (the charter commit of P146), on `m5n`, `main` at `ee8d485`. P146 item 1 is a read and item 3 is the predictions; both are committed before any code, test or script of P146 is drafted. Nothing here decides anything about S4, and no run has been made.

### Item 1. Every attribute `RiskManager`, or anything `evaluate` calls, sets or mutates after construction (MEASURED, by reading `src/` and by an AST pass over the called `Portfolio` methods)

**`RiskManager` itself: four attributes, all assigned in `__init__`, none after.** `self._config` (`manager.py:153`), `self._provider` (`:154`), `self._pairs` (`:155`, a `dict` copy of the mapping given) and `self._clock` (`:156`). A grep of `manager.py` for any other assignment to a `self` attribute, an augmented assignment, a subscript assignment, a mutating method call on one (`append`, `add`, `update`, `pop`, `clear`, `setdefault`, `extend`, `remove`, `discard`), `global`, `nonlocal`, `setattr`, `lru_cache` and `cache` finds exactly those four lines and nothing else.

| What `evaluate` calls | Where | Mutates state that outlives the call? |
|---|---|---|
| `_mark_prices`, `_last_close` | `manager.py:717`, `:741` | No: a local `dict` and `list` |
| `_stale_positions` | `manager.py:674` | No: a local `list` |
| `_approve` | `manager.py:159-233` | No: reads limits, calls the `Portfolio` reads below |
| `_atr_value` | `manager.py:753` | No, on the manager; it reads the provider (`is_ready`, `get_dataframe`), whose `get_dataframe` memoises the PROVIDER's own `_frames[key]` (`market_data.py:390-404`). **Not reached on the D1 path**: it runs only for `stop_loss.type='atr'` (`manager.py:473`), and every D1 stop is `percent` |
| `size_position` | `manager.py:236-269` | No: delegates to `calculate_position_size` |
| `derive_entry_limit`, `compute_protective_levels` and its callees `stop_loss_level`, `take_profit_level`, `_protective_level`, `_atr_to_decimal` | `rules.py:317`, `:352`, `:253`, `:279`, `:192`, `:215` | No: pure functions, no module-level state (grep for `global`, `nonlocal`, caches and module-level collections in `rules.py` and `position_sizing.py` finds none) |
| `calculate_position_size` | `position_sizing.py:196` | No: pure |
| `Portfolio.open_positions`, `position_count`, `has_position`, `has_unmanaged_holding`, `is_blocked` | `portfolio.py:485`, `:490`, `:494`, `:499`, `:503` | No (AST: no attribute or subscript assignment, no mutating call) |
| `Portfolio.marked_symbols` | `portfolio.py:512` | Only the locals `seen` and `symbols` (`:523-524`) |
| `Portfolio.equity`, `realised_today`, `committed_risk` (with `_binding_stop`), `daily_loss_exceeded`, `in_cooldown`, `cooldown_expiry` | `portfolio.py:874`, `:933`, `:1112` (`:1071`), `:1151`, `:1210`, `:1206` | No. `realised_today` is *"derived, never assigned"*: a ledger whose date is stale reads as zero without being rewritten |
| `_log.info` | `manager.py:557` | Logging only; no decision reads it |

**Not called by `evaluate`, and the only writers in the class:** `check_exit` (`manager.py:607`) and `advance_trailing_stop` (`:615`), which write the `Position`; the second has zero call sites in `src/` (the comment at `manager.py:637` says so) and the first is not on the D1 path, whose exits are scheduled.

**Does a `D1RiskManager`'s per-delta instance diverge in any state that affects a decision? No.** The instances share the provider and the clock (the same objects), hold a `dict` copy of the pairs whose values are the same frozen `PairContext`s (`assessment.py:43`, `_Frozen`) over frozen `SymbolInfo`s (`models.py:232`), and take the `Portfolio` as a per-call argument. They differ in `_config.stop_loss` alone, which is the input they exist to vary. `D1RiskManager`'s own `_by_delta` is a cache of managers, and a miss builds an equivalent one, so it cannot change a decision.

**Two caveats, both about convention and not about state.** (1) The config models are `validate_assignment` and are **not frozen** (`config/models.py:63`: `extra="forbid", populate_by_name=True, validate_assignment=True`), and `model_copy(update=...)` is shallow, so a per-delta config shares every sub-object but `stop_loss` with the base config; that is safe because nothing in `src/` assigns to a config (the comment at `config/models.py:58-62` says so), which is a convention. (2) The cap count of item 3 reads the sizing reason, because the unchanged manager exposes no flag for it; see the prediction section.

### Item 3. The predictions (R-T, R-DQ), committed before any code

**What is counted.** The entries whose size was limited by `max_position_size_percent` (R-DT-3f): of the entries the executor queues (an approved entry, before its fill outcome), those whose sizing reason says the quantity was *"capped at"* the percent of equity. The unchanged manager caps when the quantity the method asked for exceeds `equity x 20 / 100 / entry_limit` (`position_sizing.py:246-249`). At 1 percent risk that is when the stop distance is under 5 percent of the entry limit, which is a delta of 500 bps or below (a delta of exactly 500 rounds its stop toward the entry on the tick, shrinks the distance, and binds). The count is a tally and changes no decision.

**Structural predictions.**

1. **Every 1d cell is 0.** The lowest delta over every SIGNAL of the 1d candidates is 613 (C1 BTCUSDT), 648 (C2), 883 (C3), 679 (C6 BTCUSDT) and 722 or more elsewhere, section 90's `min=`, all above 500, so no entry of C1, C2, C3 or C6 can be capped. (This is near-certain, not a statistic.)
2. **Trades are unchanged from section 94 in all twelve cells (909 in all),** and so are the FOK-refused, expired, `daily_loss_halt` and `already_in_position` counts and every line of the output except the signals lines, which differ only by the appended field. The count adds a tally to the executor and a field to the script and changes no decision.
3. **The scan is CLEAN with 74 output lines and 36 log records,** the old-path digests hold, and the wall time is 5 to 8 minutes.
4. **In each cell the count is at most the entries queued** (filled, FOK-refused, expired and unaffordable together): C4 BTCUSDT 220, C4 ETHUSDT 232, C5 BTCUSDT 151, C5 ETHUSDT 157.

**The cap-binding counts for the four 4h cells.** Estimated from section 90's delta quantiles, by interpolating the fraction of SIGNALS at or below 500 bps (C4 BTCUSDT about 40 percent, C4 ETHUSDT about 20 percent, C5 BTCUSDT about 44 percent, C5 ETHUSDT about 24 percent), nudged up because an entry can only be queued while the pair is flat, which skews entries toward quieter markets and so toward smaller deltas.

| Candidate | Pair | Entries queued | Capped predicted (range) |
|---|---|---|---|
| C1, C2, C3, C6 | both pairs | 25 to 41 each | 0 (0 to 0) |
| C4 | BTCUSDT | 220 | 92 (70 to 130) |
| C4 | ETHUSDT | 232 | 51 (35 to 80) |
| C5 | BTCUSDT | 151 | 69 (50 to 95) |
| C5 | ETHUSDT | 157 | 39 (25 to 60) |

**Total: 251 (180 to 365).** The four 1d candidates' 8 cells are predicted at 0 exactly.

**The places a prediction is most likely wrong, named in advance.** The 4h counts, all four: the quantile interpolation treats the signals' deltas as if they were the entries', and an entry's delta is drawn from the pair's flat periods only. If the skew is larger than I allowed, C4 BTCUSDT could reach the top of its range; if the entries were drawn uniformly, it would be near 90. The sizing-reason route is the other risk: if the marker is absent from an approved sizing reason, every cell reads 0, which the tests of the code step are written to refuse.

### The findings this section carries

See the commit message. In short, nothing in `RiskManager` holds per-instance state that evaluate changes, the cap count has to read the sizing reason because the unchanged manager exposes no flag, and the prediction for the 1d cells is exact while the 4h ones are interpolated.

## 98. M5n P146: the counts-only run with the capped-entry count, section 97's predictions scored (P146 C5, R-T, R-DQ, R-DT-3d to R-DT-3f)

An observation log, so this section only adds. `scripts/n4_trade_counts.py` (`d0b47f1`, with its tests) was run ONCE: `python scripts/n4_trade_counts.py`, no argument, on `m5n` with a clean tree at `d0b47f1`, so the config is the committed `config.m5n.yaml` (SHA-256 `c35bea158e6001c56b49c36f31df79ab1d9bb66ffbba50b9d07a89b87a7bec00`, unchanged since section 94), the store is `data/historical`, and the window is the committed `[2017-08-17, 2024-01-01)`. The halt check (branch, clean tree, HEAD, the two config digests, worktrees, the time) was its own invocation and was read before the run was issued. Standard output went to `scratch\p146\p146_counts_output.txt` and standard error to `p146_counts_stderr.txt`. It started at `2026-10-25T10:49:43Z` by the machine's UTC clock and ended at `10:54:48Z`: **5 min 5 s of wall time, exit 0, and standard error empty (0 bytes)**. Nothing was written under `deploy\45547f107715`, the rehearsal clone or the canonical store, `config.yaml` is still blob `99b0edd005ff5f452681fc554dcc2271d2e6687e` and `config.s4.yaml` still SHA-256 `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594`, no venue was asked for anything, and no bar at or after `2024-01-01T00:00:00Z` was read. **Nothing here decides anything about S4.**

**The digests of the output.** The file as the shell wrote it, with the Windows line endings the redirection produced (76 carriage returns), has SHA-256 `96426e4f3798a8be455a09048ecaf4c667a08a80edd5b4861d1764dac674315b`; with CRLF turned to LF it is `dec72cf4d2a0397332b59f914aa91864f7920e65d13c9eed80a6ae80126789a2`. The script's own last line, `output_sha256=09f272a6958dc9c7218cfc166d5546e7cb7c071dc01a040daeae1671a0c08138`, is the SHA-256 of every line before it joined with LF, re-derived outside the script (`scratch\p146\score_p146.py`), and agrees. **The scan's verdict is `CLEAN`: 74 output lines, each in the grammar, none with a forbidden word, a decimal point or an integer over 99,999, and 36 log records kept at WARNING and above, none flagged.** No run record and no trade file was written.

### The output

```
N5 trade counts (R-DT-3d to R-DT-3f outputs only)
window [2017-08-17, 2024-01-01)
candidate C1 donchian_1d_20 (1d)
  run complete=yes problems=0
  BTCUSDT signals=104 trades=34 open_at_end=0 clamp_upper=5 clamp_lower=0 size_capped=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=65 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=16 already_in_position=49 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=34 fok_refused=3 expired=2 unaffordable=0
  BTCUSDT delta_bps n=104 p10=885 p25=980 p50=1289 p75=1591 p90=1806 min=613 max=2000
  ETHUSDT signals=104 trades=41 open_at_end=0 clamp_upper=22 clamp_lower=0 size_capped=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=62 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=19 already_in_position=43 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=41 fok_refused=1 expired=0 unaffordable=0
  ETHUSDT delta_bps n=104 p10=1067 p25=1400 p50=1627 p75=1926 p90=2000 min=759 max=2000
candidate C2 donchian_1d_55 (1d)
  run complete=yes problems=0
  BTCUSDT signals=73 trades=25 open_at_end=0 clamp_upper=3 clamp_lower=0 size_capped=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=40 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=6 already_in_position=34 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=25 fok_refused=6 expired=2 unaffordable=0
  BTCUSDT delta_bps n=73 p10=885 p25=1006 p50=1283 p75=1521 p90=1766 min=648 max=2000
  ETHUSDT signals=68 trades=28 open_at_end=0 clamp_upper=10 clamp_lower=0 size_capped=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=38 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=7 already_in_position=31 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=28 fok_refused=2 expired=0 unaffordable=0
  ETHUSDT delta_bps n=68 p10=1030 p25=1362 p50=1598 p75=1834 p90=2000 min=849 max=2000
candidate C3 sma_cross_1d_50_200 (1d)
  run complete=yes problems=0
  BTCUSDT signals=6 trades=6 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=0 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=0 already_in_position=0 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=6 fok_refused=0 expired=0 unaffordable=0
  BTCUSDT delta_bps n=6 p10=883 p25=901 p50=980 p75=1557 p90=1815 min=883 max=1815
  ETHUSDT signals=6 trades=6 open_at_end=0 clamp_upper=1 clamp_lower=0 size_capped=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=0 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=0 already_in_position=0 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=6 fok_refused=0 expired=0 unaffordable=0
  ETHUSDT delta_bps n=6 p10=1165 p25=1350 p50=1517 p75=1924 p90=2000 min=1165 max=2000
candidate C4 donchian_4h_20 (4h)
  run complete=yes problems=0
  BTCUSDT signals=538 trades=216 open_at_end=0 clamp_upper=3 clamp_lower=0 size_capped=101
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=318 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=42 already_in_position=276 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=216 fok_refused=4 expired=0 unaffordable=0
  BTCUSDT delta_bps n=538 p10=308 p25=410 p50=557 p75=738 p90=994 min=153 max=2000
  ETHUSDT signals=546 trades=215 open_at_end=0 clamp_upper=4 clamp_lower=0 size_capped=45
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=314 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=53 already_in_position=261 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=215 fok_refused=14 expired=3 unaffordable=0
  ETHUSDT delta_bps n=546 p10=416 p25=542 p50=692 p75=872 p90=1169 min=208 max=2000
candidate C5 keltner_4h_20_2 (4h)
  run complete=yes problems=0
  BTCUSDT signals=293 trades=149 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=71
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=142 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=14 already_in_position=128 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=149 fok_refused=2 expired=0 unaffordable=0
  BTCUSDT delta_bps n=293 p10=283 p25=405 p50=528 p75=696 p90=862 min=154 max=1615
  ETHUSDT signals=291 trades=147 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=39
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=134 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=16 already_in_position=118 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=147 fok_refused=9 expired=1 unaffordable=0
  ETHUSDT delta_bps n=291 p10=394 p25=512 p50=670 p75=849 p90=1079 min=253 max=1866
candidate C6 tsmom_1d_90 (1d)
  run complete=yes problems=0
  BTCUSDT signals=45 trades=23 open_at_end=0 clamp_upper=4 clamp_lower=0 size_capped=0
  BTCUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=19 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  BTCUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=0 already_in_position=19 cooldown=0 max_open_positions=0
  BTCUSDT entry_outcomes filled=23 fok_refused=3 expired=0 unaffordable=0
  BTCUSDT delta_bps n=45 p10=771 p25=872 p50=1243 p75=1540 p90=1939 min=679 max=2000
  ETHUSDT signals=40 trades=19 open_at_end=0 clamp_upper=12 clamp_lower=0 size_capped=0
  ETHUSDT refusals unknown_pair=0 no_reference_price=0 nothing_to_close=0 unsupported_action=0 no_mark_price=0 position_stale=0 committed_risk_unknown=0 limit_refused=20 live_order_list=0 unmanaged_holding=0 atr_unavailable=0 stop_unplaceable=0 size_not_tradeable=0 unaffordable=0
  ETHUSDT rules no_mark_price=0 no_equity=0 daily_loss_halt=1 already_in_position=19 cooldown=0 max_open_positions=0
  ETHUSDT entry_outcomes filled=19 fok_refused=1 expired=0 unaffordable=0
  ETHUSDT delta_bps n=40 p10=898 p25=1210 p50=1494 p75=2000 p90=2000 min=722 max=2000
scan verdict=CLEAN output_lines=74 log_records=36
output_sha256=09f272a6958dc9c7218cfc166d5546e7cb7c071dc01a040daeae1671a0c08138
```

### Section 97's predictions, scored

**(a) Structural predictions.** All four held, and one clause I did not state is a miss.

1. **Every 1d cell is 0: HELD,** all eight (C1, C2, C3 and C6, both pairs).
2. **Trades, FOK-refused, expired, `daily_loss_halt`, `already_in_position` and every line but the signals lines are identical to section 94: HELD, with one miss of mine.** `score_n5`-style comparison (`score_p146.py`) of the two outputs, line by line, finds exactly two lines that differ other than by the appended field: **the header line, which now reads `R-DT-3d to R-DT-3f outputs only`, and the hash line.** Section 97 predicted "every line of the output except the signals lines" and forgot that the header names the rulings the output answers to; the change was made in the code step, for honesty, and the prediction did not account for it. The 12 signals lines are equal to section 94's up to the appended `size_capped=`. The trades are 909 in all, as before.
3. **The scan is CLEAN with 74 output lines and 36 log records, the old-path digests hold and the wall time is 5 to 8 minutes: HELD** (5 min 5 s).
4. **In each cell the count is at most the entries queued: HELD** (queued: C4 BTCUSDT 220, C4 ETHUSDT 232, C5 BTCUSDT 151, C5 ETHUSDT 157, from the entry-outcomes lines).

**(b) The cap-binding counts.**

| Candidate | Pair | Entries queued | Predicted (range) | Observed | Share of queued |
|---|---|---|---|---|---|
| C1, C2, C3, C6 | both pairs | 6 to 42 | 0 (0 to 0) | 0 in all eight | 0 |
| C4 | BTCUSDT | 220 | 92 (70 to 130) | **101 inside** | 45.9% |
| C4 | ETHUSDT | 232 | 51 (35 to 80) | **45 inside** | 19.4% |
| C5 | BTCUSDT | 151 | 69 (50 to 95) | **71 inside** | 47.0% |
| C5 | ETHUSDT | 157 | 39 (25 to 60) | **39 inside, exact** | 24.8% |

**Total: 256, against 251 predicted (180 to 365): inside, and 12 of 12 cells inside their ranges.** Section 97 estimated the share of SIGNALS at or below 500 bps from section 90's delta quantiles at about 40, 20, 44 and 24 percent; the shares of ENTRIES are 45.9, 19.4, 47.0 and 24.8. So the interpolation was close, the skew toward quieter markets I allowed for was small for BTCUSDT (about 6 points) and absent for ETHUSDT, and the 4h candidates cut roughly **a third of all their entries (146 of 452 on C4, 32 percent; 110 of 308 on C5, 36 percent)** at the 20-percent position cap. That is the finding this count exists to give: on the 4h candidates the sizing is capped, not risk-sized, for a fifth to a half of the entries, so their realised risk per trade is below the 1 percent N5 names. On the 1d candidates it is never so.

### Diagnoses

* **The only miss is the header,** and it is mine: a prediction that lists "every line but X" must list the lines that name their own rulings.
* **What the count does not say.** It says an entry's size was limited, not by how much: `requested_quantity` is on the sizing and is not printed, and a ratio of requested to final would be a size, outside R-DT-3f's list. How far below 1 percent a capped entry's risk fell is therefore UNMEASURED.
* **The closed hole is not scored here.** Section 96's `q17` (a swap of the FOK-refused and expired fields) was predicted killed by the new tests (`M5n-159`, REASONED); the re-survey that follows measures it.

### What these counts are, and are not

They are the number of entries the cap limited, per candidate and pair, over the in-sample window, beside the counts of sections 90 and 94 which they leave unchanged. **They are not a verdict on any candidate**: no return, equity or P&L was printed, and the simulation's own figures were kept in memory and discarded.

## 99. M5n P146: the predictions for the re-survey of the outcomes line and the capped-entry count, before it is run (P146 C6, R-T, R-DQ)

An observation log, so this section only adds. P146 re-surveys two things: the swap of the FOK-refused and expired fields of the entry-outcomes line, which failed no test at section 96 (`q17`, `M5n-149`), and the new capped-entry count with the state pins of P146 step 1. It runs the 205 tests of `tests/unit/test_d1_risk.py`, `test_d1_executor.py`, `test_backtest_d1.py` and `test_n4_trade_counts.py` against 16 one-site mutations. **This section is committed before the survey is run.** It decides nothing about S4.

### The method

The harness is the repository's `scripts/worktree_survey.py` with `scripts/survey_hook.py`, as in sections 91 and 95: a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven inside it before any result counts, an unmutated baseline predicted green (205 passed), every mutation byte-exact with exactly one match, asserted both when the spec was generated and when it runs, every restore shown SHA-equal, and the worktree removed afterwards. A MORE is recorded and a FEWER halts the survey. The spec is `survey_p146.json` (SHA-256 `e3d238f0086094c46b925fac83c775822e18cc71c76f0b5e6245d6f2c31949e7`), generated by the same program as the table below, with the test list from `pytest --collect-only` at `d031654` (205 node ids). Two mutations (`s15`, `s16`) mutate the UNCHANGED `risk/manager.py` inside the disposable worktree, which is what the standing rule allows and the only way to ask whether the state pins would catch a future change to the class the owner's acceptance rests on; the repository's copy is not touched. No test was run on a mutated tree.

### Totals

**16 mutations and 63 predicted failures.** The predictions come from reading each test's fixture and assertion, not its name (`M5h`).

**One mutation is predicted to fail nothing, and one pair of tests is predicted blind to two others.**

* `s09` (the grammar accepts a capped count of up to nine digits) fails nothing, because the integer bound of 99,999 still refuses the row: it is guarded twice, the shape section 91 named for the scan.
* **`s07` and `s08` (the signal count printed or read as the capped count) are predicted NOT to be killed by the delta-10 world or by the cap-count test, and that is a hole in the new tests, declared here and not closed.** In that world all six signals are queued and all six are capped, so signals, queued entries and capped entries are the same number and the tests cannot tell them apart. `s07` and `s08` are killed only where the two numbers differ: the schema world (3 signals, 0 capped) and the delta-1000 world (6 signals, 0 capped), and for `s08` the mapping test (20 signals, 6 capped).
* `s01` is the mutation this survey exists for. It is predicted killed by the two outcomes worlds and the mapping test, and **NOT by the schema world**, whose FOK-refused and expired counts are still zero, so the schema world remains blind to the swap and the closing of the hole is carried by the three new tests alone.

**Tests killed by no mutation of this survey: 183 of 205.** By file: `test_d1_risk.py` 28 of 32, `test_d1_executor.py` 63 of 71, `test_backtest_d1.py` 25 of 29 and `test_n4_trade_counts.py` 67 of 73. **This is the number for THIS survey's 16 mutations and is not a whole-suite figure:** the tests of the delegating manager, the executor and the script that are not about the cap or the outcomes line were surveyed at sections 92 and 96 and are not re-mutated here, so a test absent from every set below is not thereby blind.

**Where a prediction is most likely to be wrong, named in advance.**

* `s11` (every sized entry is counted), 10 failures. It leans on the schema world: its `FixedD1` strategy runs under fixed-fraction sizing, whose sizing reason exists and holds no marker, so the mutation counts its two BTCUSDT and one ETHUSDT queued entries and prints `size_capped=2` and `1`. If a fixed-fraction approval carries no sizing, the schema world passes and the figure is 9.
* `s05` and `s06`, 4 each, which put the schema world in the set: the first because the schema world's BTCUSDT fills twice and so prints `fok_refused=2`, the second because it has 2 fills and 1 trade.
* `s14` (the marker is not the sizer's), 9: it is the one that makes the real sizer's text and the executor's constant disagree, and it is predicted killed in the risk file (2), the executor file (3), the chain (2) and the script's worlds (2).
* `s15` and `s16`, 2 each: both are predicted killed by the two state-pin tests and by nothing else in the four files, since no other test inspects a manager's attributes or its pairs mapping.

### Predicted failures

| Mutation | The break | Predicted failures | Tests |
|---|---|---|---|
| s01 | the outcomes line swaps the FOK-refused and expired counts (section 96's q17) | 3 | N133, N134, N136 |
| s02 | the unaffordable outcome prints the expired count | 3 | N133, N134, N136 |
| s03 | the expired outcome counts the FOK-refused entries | 3 | N133, N134, N136 |
| s04 | the unaffordable outcome counts the expired entries | 3 | N133, N134, N136 |
| s05 | the FOK-refused outcome counts the filled entries | 4 | N137, N133, N134, N136 |
| s06 | the filled outcome prints the trade count | 4 | N137, N133, N134, N136 |
| s07 | the signals line prints the signal count as the capped count | 2 | N137, N134 |
| s08 | the pair's capped count is read from the signal count | 3 | N137, N134, N136 |
| s09 | the grammar accepts a capped count of up to nine digits | 0 | none |
| s10 | the grammar makes the capped count optional | 1 | N170 |
| s11 | every sized, queued entry is counted as capped | 10 | N83, N84, N85, N86, N87, N91, N114, N115, N134, N137 |
| s12 | a capped entry counts twice | 7 | N82, N90, N91, N112, N113, N133, N135 |
| s13 | the tally snapshot reports no capped entry | 7 | N82, N90, N91, N112, N113, N133, N135 |
| s14 | the marker is not the one the sizer writes | 9 | N82, N90, N91, N28, N30, N112, N113, N133, N135 |
| s15 | evaluate records the last symbol on the manager, a new attribute | 2 | N31, N32 |
| s16 | evaluate writes into the manager's pairs mapping | 2 | N31, N32 |

### The test key (every code the table uses)

The codes are the tests in collection order, N1 to N205.

| Code | Test |
|---|---|
| N1 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_upper_bound_risks_one_percent_at_a_stop_twenty_percent_below` |
| N2 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_a_middle_trail` |
| N3 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_lower_bound_is_cut_by_the_twenty_percent_position_cap` |
| N4 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_loss_at_the_stop_is_at_most_one_percent_of_equity_when_the_cap_is_slack` |
| N5 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_stop_is_the_signals_delta_and_not_the_placeholder` |
| N6 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_the_stop_type_in_the_file_does_not_matter` |
| N7 | `d1_risk`: `TestOnePercentAtTheClampedTrail::test_a_delta_is_an_exact_decimal_percent` |
| N8 | `d1_risk`: `TestTheQuoteBalanceRefusesAndDoesNotShrink::test_a_size_the_free_quote_cannot_pay_for_is_refused_at_unaffordable` |
| N9 | `d1_risk`: `TestTheQuoteBalanceRefusesAndDoesNotShrink::test_the_same_size_is_approved_when_the_cash_is_there` |
| N10 | `d1_risk`: `TestEveryRuleStillRefuses::test_no_equity` |
| N11 | `d1_risk`: `TestEveryRuleStillRefuses::test_daily_loss_halt_from_realised_loss` |
| N12 | `d1_risk`: `TestEveryRuleStillRefuses::test_daily_loss_halt_from_committed_risk_alone_on_an_untrailed_stop` |
| N13 | `d1_risk`: `TestEveryRuleStillRefuses::test_the_halt_is_checked_before_already_in_position` |
| N14 | `d1_risk`: `TestEveryRuleStillRefuses::test_already_in_position` |
| N15 | `d1_risk`: `TestEveryRuleStillRefuses::test_cooldown` |
| N16 | `d1_risk`: `TestEveryRuleStillRefuses::test_max_open_positions` |
| N17 | `d1_risk`: `TestEveryRuleStillRefuses::test_no_mark_price` |
| N18 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_it_overrides_evaluate_and_nothing_else_of_the_base` |
| N19 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_signal_without_a_delta_is_evaluated_by_the_base_configuration` |
| N20 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_only_an_integer_delta_is_a_delta[True]` |
| N21 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_only_an_integer_delta_is_a_delta[1000]` |
| N22 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_only_an_integer_delta_is_a_delta[1000.0]` |
| N23 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_non_buy_is_evaluated_by_the_base_class` |
| N24 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_with_stops_off_it_is_the_base_manager_exactly` |
| N25 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_delta_that_is_not_a_distance_raises[0]` |
| N26 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_a_delta_that_is_not_a_distance_raises[-5]` |
| N27 | `d1_risk`: `TestWhatItLeavesToTheBaseClass::test_one_manager_is_kept_per_delta` |
| N28 | `d1_risk`: `TestTheCapMarkerIsTheManagersOwn::test_the_marker_is_in_the_reason_when_the_cap_binds` |
| N29 | `d1_risk`: `TestTheCapMarkerIsTheManagersOwn::test_the_marker_is_absent_when_it_does_not` |
| N30 | `d1_risk`: `TestTheCapMarkerIsTheManagersOwn::test_a_delta_of_exactly_five_hundred_binds_on_the_tick` |
| N31 | `d1_risk`: `TestTheManagersHoldNoStateThatEvaluateChanges::test_a_plain_manager_changes_nothing_across_every_kind_of_verdict` |
| N32 | `d1_risk`: `TestTheManagersHoldNoStateThatEvaluateChanges::test_the_per_delta_instances_differ_only_in_the_stop` |
| N33 | `d1_executor`: `TestTheExitInTheEntryBar::test_a_trail_that_triggers_in_the_entry_bar_is_booked_in_that_callback` |
| N34 | `d1_executor`: `TestTheExitInTheEntryBar::test_the_entry_minutes_high_counts_toward_the_peak` |
| N35 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_after_the_bar_is_not_booked_until_the_clock_reaches_it` |
| N36 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_at_exactly_the_clock_is_booked` |
| N37 | `d1_executor`: `TestTheExitIsScheduled::test_an_exit_one_minute_past_the_clock_waits` |
| N38 | `d1_executor`: `TestTheExitIsScheduled::test_the_exit_is_booked_before_a_signal_on_the_next_bar_can_see_it` |
| N39 | `d1_executor`: `TestTheExitIsScheduled::test_two_pairs_book_in_time_order_not_in_callback_order` |
| N40 | `d1_executor`: `TestTheExitIsScheduled::test_overlapping_positions_hold_one_ledger` |
| N41 | `d1_executor`: `TestAPositionThatNeverTriggers::test_it_stays_open_at_the_end` |
| N42 | `d1_executor`: `TestAPositionThatNeverTriggers::test_a_trigger_after_the_window_end_is_never_read` |
| N43 | `d1_executor`: `TestAPositionThatNeverTriggers::test_finish_is_idempotent` |
| N44 | `d1_executor`: `TestAGapInTheMinutePath::test_a_fall_inside_the_gap_exits_at_the_next_traded_open` |
| N45 | `d1_executor`: `TestAGapInTheMinutePath::test_a_gap_that_recovers_leaves_the_position_open` |
| N46 | `d1_executor`: `TestAGapInTheMinutePath::test_a_decision_bar_gap_flags_the_trade` |
| N47 | `d1_executor`: `TestZeroVolumeMinutes::test_a_filler_minute_is_not_a_trade_and_is_not_walked` |
| N48 | `d1_executor`: `TestZeroVolumeMinutes::test_a_bar_with_no_traded_minute_cannot_fill` |
| N49 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_open_above_the_limit_is_refused` |
| N50 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_a_missing_next_slot_expires_the_entry` |
| N51 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_entry_the_data_ends_on_expires` |
| N52 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_an_entry_the_ledger_cannot_pay_for_is_unaffordable` |
| N53 | `d1_executor`: `TestAnEntryThatDoesNotFill::test_a_second_entry_while_one_is_pending_is_ignored` |
| N54 | `d1_executor`: `TestThePositionItOpens::test_the_initial_stop_is_the_fill_less_the_trail` |
| N55 | `d1_executor`: `TestThePositionItOpens::test_it_is_stamped_active_at_the_simulated_instant` |
| N56 | `d1_executor`: `TestThePositionItOpens::test_a_position_on_another_pair_is_stamped_on_every_bar` |
| N57 | `d1_executor`: `TestTheTally::test_every_signal_is_counted_with_its_delta_and_clamp` |
| N58 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unknown_pair]` |
| N59 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[no_reference_price]` |
| N60 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[nothing_to_close]` |
| N61 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unsupported_action]` |
| N62 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[no_mark_price]` |
| N63 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[position_stale]` |
| N64 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[committed_risk_unknown]` |
| N65 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[limit_refused]` |
| N66 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[live_order_list]` |
| N67 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unmanaged_holding]` |
| N68 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[atr_unavailable]` |
| N69 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[stop_unplaceable]` |
| N70 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[size_not_tradeable]` |
| N71 | `d1_executor`: `TestTheTally::test_a_refusal_from_each_stage_is_counted_under_that_stage[unaffordable]` |
| N72 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[no_mark_price]` |
| N73 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[no_equity]` |
| N74 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[daily_loss_halt]` |
| N75 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[already_in_position]` |
| N76 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[cooldown]` |
| N77 | `d1_executor`: `TestTheTally::test_a_refusal_is_counted_under_the_rule_that_fired[max_open_positions]` |
| N78 | `d1_executor`: `TestTheTally::test_a_refusal_after_the_limits_carries_no_rule[size_not_tradeable]` |
| N79 | `d1_executor`: `TestTheTally::test_a_refusal_after_the_limits_carries_no_rule[unaffordable]` |
| N80 | `d1_executor`: `TestTheTally::test_a_refusal_with_no_decision_carries_no_rule` |
| N81 | `d1_executor`: `TestTheTally::test_an_approved_entry_adds_no_rule` |
| N82 | `d1_executor`: `TestTheTally::test_a_queued_entry_whose_size_the_cap_limited_is_counted` |
| N83 | `d1_executor`: `TestTheTally::test_a_size_the_cap_did_not_limit_is_not_counted` |
| N84 | `d1_executor`: `TestTheTally::test_a_reworded_reason_is_not_the_marker[risk_per_trade, limited to 20% of equity: 0.5 at 100.10]` |
| N85 | `d1_executor`: `TestTheTally::test_a_reworded_reason_is_not_the_marker[risk_per_trade; capped at 20% of equity: 0.5 at 100.10]` |
| N86 | `d1_executor`: `TestTheTally::test_a_reworded_reason_is_not_the_marker[capped: 0.5 at 100.10]` |
| N87 | `d1_executor`: `TestTheTally::test_a_reworded_reason_is_not_the_marker[risk_per_trade, uncapped at 20% of equity: 0.5 at 100.10]` |
| N88 | `d1_executor`: `TestTheTally::test_an_approved_entry_with_no_sizing_is_not_counted` |
| N89 | `d1_executor`: `TestTheTally::test_a_refusal_carrying_a_capped_sizing_is_not_an_entry` |
| N90 | `d1_executor`: `TestTheTally::test_an_entry_ignored_for_a_pending_one_is_not_counted` |
| N91 | `d1_executor`: `TestTheTally::test_the_cap_count_is_per_pair_and_the_snapshot_is_a_copy` |
| N92 | `d1_executor`: `TestTheTally::test_rules_are_tallied_per_pair_and_the_snapshot_is_a_copy` |
| N93 | `d1_executor`: `TestTheTally::test_pairs_are_tallied_apart` |
| N94 | `d1_executor`: `TestTheTally::test_the_snapshot_is_a_copy` |
| N95 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[None]` |
| N96 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[500.0]` |
| N97 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[500]` |
| N98 | `d1_executor`: `TestWhatItRefusesToDispatch::test_a_signal_without_an_integer_delta_raises[True]` |
| N99 | `d1_executor`: `TestWhatItRefusesToDispatch::test_an_approved_exit_raises` |
| N100 | `d1_executor`: `TestTheContract::test_it_satisfies_the_dispatcher_port` |
| N101 | `d1_executor`: `TestTheContract::test_the_metadata_keys_are_the_ones_the_strategies_write` |
| N102 | `d1_executor`: `TestTheContract::test_two_runs_of_the_same_history_give_the_same_trade_log` |
| N103 | `d1_executor`: `TestTheContract::test_the_module_reads_no_wall_clock` |
| N104 | `backtest_d1`: `TestTheChoice::test_a_strategy_that_declares_the_exit_takes_the_d1_executor` |
| N105 | `backtest_d1`: `TestTheChoice::test_a_strategy_that_does_not_takes_the_simulated_executor_and_its_digest_holds` |
| N106 | `backtest_d1`: `TestTheChoice::test_the_old_path_holds_on_two_pairs_too` |
| N107 | `backtest_d1`: `TestTheChoice::test_no_series_is_asked_for_past_the_window_end` |
| N108 | `backtest_d1`: `TestTheChoice::test_a_mix_of_declaring_and_other_strategies_is_refused` |
| N109 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_a_trail_of_1000_risks_one_percent` |
| N110 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_upper_clamp_sizes_from_a_twenty_percent_stop` |
| N111 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_lower_clamp_is_cut_by_the_position_cap` |
| N112 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_tally_counts_an_entry_only_when_the_cap_limited_its_size[10-1]` |
| N113 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_tally_counts_an_entry_only_when_the_cap_limited_its_size[500-1]` |
| N114 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_tally_counts_an_entry_only_when_the_cap_limited_its_size[501-0]` |
| N115 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_tally_counts_an_entry_only_when_the_cap_limited_its_size[1000-0]` |
| N116 | `backtest_d1`: `TestN5SizingThroughTheWholeChain::test_the_same_world_without_n5_is_sized_by_the_fixed_fraction` |
| N117 | `backtest_d1`: `TestRefusalsByRuleThroughTheWholeChain::test_a_second_signal_while_held_is_already_in_position` |
| N118 | `backtest_d1`: `TestRefusalsByRuleThroughTheWholeChain::test_a_winner_on_an_untrailed_stop_halts_every_entry_including_its_own_pair` |
| N119 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_run_is_complete_and_the_cash_identity_holds[4h]` |
| N120 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_run_is_complete_and_the_cash_identity_holds[1d]` |
| N121 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_each_pair_books_its_own_exit_at_the_hand_worked_price[4h]` |
| N122 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_each_pair_books_its_own_exit_at_the_hand_worked_price[1d]` |
| N123 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_positions_overlap_and_the_earlier_exit_is_booked_first[4h]` |
| N124 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_positions_overlap_and_the_earlier_exit_is_booked_first[1d]` |
| N125 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_a_signal_while_in_position_is_a_limit_refusal[4h]` |
| N126 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_a_signal_while_in_position_is_a_limit_refusal[1d]` |
| N127 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_second_entry_is_still_open_at_the_end[4h]` |
| N128 | `backtest_d1`: `TestBothPairsOnBothTimeframes::test_the_second_entry_is_still_open_at_the_end[1d]` |
| N129 | `backtest_d1`: `TestAGapWhilePositionsAreOpen::test_a_missing_decision_bar_and_minutes_with_a_fall_exit_at_the_next_open` |
| N130 | `backtest_d1`: `TestAGapWhilePositionsAreOpen::test_the_same_gap_without_a_fall_leaves_the_position_open` |
| N131 | `backtest_d1`: `TestTheRealCandidate::test_a_quiet_breakout_clamps_to_the_lower_bound_and_stays_open` |
| N132 | `backtest_d1`: `TestTheRealCandidate::test_a_wild_breakout_clamps_to_the_upper_bound` |
| N133 | `n4_trade_counts`: `TestEveryEntryOutcomeIsPrintedUnderItsOwnName::test_filled_fok_refused_and_expired_are_distinct_and_in_their_fields[10-6]` |
| N134 | `n4_trade_counts`: `TestEveryEntryOutcomeIsPrintedUnderItsOwnName::test_filled_fok_refused_and_expired_are_distinct_and_in_their_fields[1000-0]` |
| N135 | `n4_trade_counts`: `TestEveryEntryOutcomeIsPrintedUnderItsOwnName::test_the_cap_count_is_the_entries_queued_and_not_the_signals_or_the_fills` |
| N136 | `n4_trade_counts`: `TestEveryEntryOutcomeIsPrintedUnderItsOwnName::test_the_outcomes_map_to_the_executors_results_by_pair` |
| N137 | `n4_trade_counts`: `TestTheRun::test_the_output_is_exactly_the_schema` |
| N138 | `n4_trade_counts`: `TestTheRun::test_the_last_line_is_the_hash_of_every_line_before_it` |
| N139 | `n4_trade_counts`: `TestTheRun::test_the_output_has_no_decimal_point_and_no_money_word` |
| N140 | `n4_trade_counts`: `TestTheRun::test_two_runs_print_the_same_bytes` |
| N141 | `n4_trade_counts`: `TestTheRun::test_it_writes_no_run_record_and_no_trade_file` |
| N142 | `n4_trade_counts`: `TestTheRun::test_it_opens_no_file_for_writing` |
| N143 | `n4_trade_counts`: `TestTheRun::test_nothing_the_run_logs_reaches_a_handler_or_a_terminal` |
| N144 | `n4_trade_counts`: `TestTheRun::test_a_warning_logged_during_the_run_is_kept_and_counted_and_never_shown` |
| N145 | `n4_trade_counts`: `TestTheRun::test_a_narrower_window_is_accepted_and_named` |
| N146 | `n4_trade_counts`: `TestTheRun::test_a_run_that_is_not_complete_says_so_and_exits_one` |
| N147 | `n4_trade_counts`: `TestTheQuantiles::test_nearest_rank_on_ten_values` |
| N148 | `n4_trade_counts`: `TestTheQuantiles::test_a_single_value_is_every_quantile` |
| N149 | `n4_trade_counts`: `TestTheQuantiles::test_the_line_sorts_its_values_and_prints_the_extremes` |
| N150 | `n4_trade_counts`: `TestTheWindow::test_the_constants_are_the_committed_ones` |
| N151 | `n4_trade_counts`: `TestTheWindow::test_the_candidates_are_the_six_in_r_dys_order` |
| N152 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv0]` |
| N153 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv1]` |
| N154 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv2]` |
| N155 | `n4_trade_counts`: `TestTheWindow::test_a_window_outside_the_committed_one_is_refused_before_the_store_is_opened[argv3]` |
| N156 | `n4_trade_counts`: `TestTheWindow::test_a_naive_window_is_refused` |
| N157 | `n4_trade_counts`: `TestTheWindow::test_the_whole_committed_window_is_accepted` |
| N158 | `n4_trade_counts`: `TestTheScan::test_the_lines_the_schema_makes_pass` |
| N159 | `n4_trade_counts`: `TestTheScan::test_a_stage_named_for_a_price_is_a_stage_and_not_a_figure` |
| N160 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[no_mark_price]` |
| N161 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[no_equity]` |
| N162 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[daily_loss_halt]` |
| N163 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[already_in_position]` |
| N164 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[cooldown]` |
| N165 | `n4_trade_counts`: `TestTheScan::test_every_rule_name_is_a_label_and_not_a_figure[max_open_positions]` |
| N166 | `n4_trade_counts`: `TestTheScan::test_the_rule_names_are_the_risk_managers` |
| N167 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1.5 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=0]` |
| N168 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=1.5]` |
| N169 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=100000]` |
| N170 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0]` |
| N171 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 size_capped=]` |
| N172 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT signals=1 trades=1 open_at_end=0 clamp_upper=0 clamp_lower=0 capped=1]` |
| N173 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules loss=1]` |
| N174 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules daily_loss=1]` |
| N175 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules daily_loss_halt=1.5]` |
| N176 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules daily_loss_halt=100000]` |
| N177 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules equity=1]` |
| N178 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT entry_outcomes filled=1 fok_refused=0 expired=0 unaffordable=0 fee=1]` |
| N179 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT entry_outcomes filled=1 fok_refused=0]` |
| N180 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT rules]` |
| N181 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT mean_return=1]` |
| N182 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT delta_bps n=1 p10=100000 p25=1 p50=1 p75=1 p90=1 min=1 max=1]` |
| N183 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 price_1d (1d)]` |
| N184 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 realised_1d (1d)]` |
| N185 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[candidate C1 donchian_1d_20 (1d) equity]` |
| N186 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  run complete=yes problems=0 ]` |
| N187 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[]` |
| N188 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[window [2017-08-17, 2024-01-01) caf\xe9]` |
| N189 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[  BTCUSDT balance 42000]` |
| N190 | `n4_trade_counts`: `TestTheScan::test_a_line_outside_the_grammar_or_with_a_figure_is_counted[output_sha256=XYZ]` |
| N191 | `n4_trade_counts`: `TestTheScan::test_the_count_is_per_line` |
| N192 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[BTCUSDT/4h: 1 bar(s) missing between 2017-09-06T16:00:00+00:00 and 2017-09-06T20:00:00+00:00]` |
| N193 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[Entry for ETHUSDT ignored: an entry is pending or a position is held]` |
| N194 | `n4_trade_counts`: `TestTheScan::test_an_ordinary_log_message_passes[stream handler failed for BTCUSDT 4h]` |
| N195 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[Risk approved BTCUSDT: 2.00330000 at 98.10000000]` |
| N196 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[free quote 10000.5]` |
| N197 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[filled at 42000]` |
| N198 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[balance is low]` |
| N199 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[the realised total moved]` |
| N200 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[cost $5]` |
| N201 | `n4_trade_counts`: `TestTheScan::test_a_message_that_carries_a_figure_or_a_money_word_is_flagged[price 100]` |
| N202 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_a_line_the_grammar_refuses_is_not_printed` |
| N203 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_a_log_record_that_carries_a_figure_fails_the_scan_and_is_not_printed` |
| N204 | `n4_trade_counts`: `TestAForbiddenFigureNeverReachesTheOutput::test_an_exception_is_reported_by_class_and_place_and_never_by_message` |
| N205 | `n4_trade_counts`: `TestTheScript::test_it_has_no_fetcher_and_never_writes` |


## 100. M5n P146: the re-survey of the outcomes line and the capped-entry count, scored against section 99 (P146 C7, R-T)

An observation log, so this section only adds. The survey ran as section 99 describes, with the repository's `scripts/worktree_survey.py` and `scripts/survey_hook.py`, in a detached worktree outside the repository (`scratch\p146\wt_survey`) at `24bf718` (the commit that carries section 99), the import location of `trading_bot` and `tests` printed inside the worktree before any result, an unmutated baseline of **205 passed in 15.53 s**, every restore shown SHA-equal, every copied file intact afterwards, and `git worktree list` showing the main worktree only. It ran once, `2026-10-25T10:58:32Z` to `11:03:02Z` (4 min 30 s), exit 0, standard error empty, from the committed spec (`survey_p146.json`, SHA-256 as section 99 records it). Nothing here decides anything about S4.

### Totals

**16 mutations: 16 MATCH, 0 MORE, 0 FEWER. Predicted failures 63, observed 63.** The one mutation predicted to fail nothing (`s09`) failed nothing. No halt fired, and **every failure is a kill by an assertion: there is no crash**, so nothing in this survey is credited by a crash. 22 distinct tests failed under at least one mutation, and 183 of the 205 failed under none of these 16, which is this survey's number and not a whole-suite one (section 99).

### The hole of M5n-149 is closed, and the survey measures it

**`s01`, the swap of the FOK-refused and expired fields that failed no test at section 96, is now killed by exactly the three tests section 99 predicted** (the two outcomes worlds and the mapping test), **and not by the schema world,** whose counts for both fields are still zero: that world remains blind to the swap and the three new tests carry the closing alone. The same three kill `s02` (unaffordable printed as expired), `s03` and `s04` (the expired and unaffordable outcomes read from the wrong result), so **the four fields of the outcomes line are each now pinned by a test that gives them distinct non-zero values** (`filled` 5 or 1, `fok_refused` 2, `expired` 3, `unaffordable` 4 in the mapping test). `s05` and `s06` (FOK-refused counting the filled entries, filled printing the trade count) are killed by those and by the schema world, as predicted, four each.

### The capped-entry count

* `s11` (every sized entry counted as capped) 10, `s12` (counted twice) 7, `s13` (the snapshot reports none) 7 and `s14` (a marker the sizer does not write) 9 all failed exactly the tests predicted, across the executor, the chain through the real manager and sizer, and the script's worlds. **`s14` is the one that ties the executor's constant to the sizer's own text:** it is killed in the risk file by the two canary tests that call the real sizer, which is the pin on the text contract of `M5n-155`.
* **`s07` and `s08` (the signal count printed or read as the capped count) are killed by exactly the tests section 99 predicted and by NO test of the delta-10 world or the cap-count test,** as declared: in that world all six signals are queued and capped, so the numbers coincide. **The hole of `M5n-166` stands:** a world with queued entries that are not all capped, and signals that are not all queued, would close it. It was not written, because a test added after the survey is a test the survey did not see.
* `s09` (the grammar widened to nine digits) fails nothing: the integer bound still refuses the oversized row, which is guarded twice. `s10` (the capped count optional) is killed by the one row that omits it.

### The state pins, aimed at the unchanged class

**`s15` (evaluate writes a new attribute on the manager) and `s16` (evaluate writes into the pairs mapping) are each killed by the two state-pin tests and by nothing else,** as predicted. The mutations were made to `risk/manager.py` in the disposable worktree only; the repository's copy is untouched. So **the tests behind the owner's acceptance of `D1RiskManager` do catch a future change to `RiskManager` that gives it per-instance state `evaluate` writes** (an attribute, or a write to the mapping), which is the condition the acceptance is made under. What they cannot catch is a write of an unchanged value to the shared config (the config dump is equal) and a write to a shared object that the tests do not compare; both are REASONED, not surveyed.

### Every mutation

| Mutation | The break | Predicted | Observed | Verdict |
|---|---|---|---|---|
| s01 | the outcomes line swaps the FOK-refused and expired counts (section 96's q17) | 3 | 3 | MATCH |
| s02 | the unaffordable outcome prints the expired count | 3 | 3 | MATCH |
| s03 | the expired outcome counts the FOK-refused entries | 3 | 3 | MATCH |
| s04 | the unaffordable outcome counts the expired entries | 3 | 3 | MATCH |
| s05 | the FOK-refused outcome counts the filled entries | 4 | 4 | MATCH |
| s06 | the filled outcome prints the trade count | 4 | 4 | MATCH |
| s07 | the signals line prints the signal count as the capped count | 2 | 2 | MATCH |
| s08 | the pair's capped count is read from the signal count | 3 | 3 | MATCH |
| s09 | the grammar accepts a capped count of up to nine digits | 0 | 0 | MATCH |
| s10 | the grammar makes the capped count optional | 1 | 1 | MATCH |
| s11 | every sized, queued entry is counted as capped | 10 | 10 | MATCH |
| s12 | a capped entry counts twice | 7 | 7 | MATCH |
| s13 | the tally snapshot reports no capped entry | 7 | 7 | MATCH |
| s14 | the marker is not the one the sizer writes | 9 | 9 | MATCH |
| s15 | evaluate records the last symbol on the manager, a new attribute | 2 | 2 | MATCH |
| s16 | evaluate writes into the manager's pairs mapping | 2 | 2 | MATCH |


## 101. M5n N6: what metrics.py does, the design of the estimator module, and the hand-worked values of its fixtures, before any code (P148 C2, R-T, R-DQ)

An observation log, so this section only adds. HEAD is `73a7abe` (the charter commit of P148), on `m5n`, `main` at `ee8d485`, and the pre-registration's SHA-256 is still `e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e`. P148 item 2 is a read and item 3 is the predictions; both are committed before any code, test or script of N6 is drafted. **No recorded bar was read and no backtest was run**: every number below comes from a synthetic fixture, and the derivation script (`scratch\p148\derive_fixtures.py`) uses exact `Decimal` arithmetic and `math.erf`, so it shares no code with the module it predicts. Nothing here decides anything about S4.

### Item 2. What `metrics.py` builds, against pre-registration section 1 and reading (1) (MEASURED, by reading)

* **The Sharpe formula equals reading (1) exactly.** `sharpe_ratio` (`metrics.py:449-459`) returns the mean of the daily returns over their sample standard deviation with `n - 1` (`:455-456`), times `sqrt(365)` (`_annualiser`, `:445-446`, with `DAYS_PER_YEAR = 365` at `:93`), with no risk-free rate; it is `None` below two days (`:452`) or at a zero standard deviation (`:457`).
* **The daily series equals section 1 under two conditions, and differs in three ways.** `EquityCurve.observe` (`metrics.py:333-355`) records the equity after every bar of any pair and keeps the LAST sample of each UTC day (`self._daily[(at - _MICROSECOND).date()] = equity`, `:355`, so a sample exactly at 00:00 belongs to the day it closes); `daily_returns` (`:423-442`) divides each day's close by the previous day's, the first by the initial balance (`previous = summary.initial`, `:434`), and carries a day with no sample forward (`closes.get(day, previous)`, `:438`). The equity itself is the engine's `_EquityProbe` (`engine.py:191-225`): cash plus every held symbol marked at the last close the provider holds, exact `Decimal`. So it equals section 1's "equity at each UTC 00:00, positions marked at the 1d archive close" **when** the last sample of the day is at the day's last bar (the 4h bar that closes at 00:00 shares its close with the 1d bar of that minute), **and** when the series starts at the span's first midnight with a flat book at the initial balance. **It differs in:** (1) it is `Decimal` where reading (4) fixes float64 estimators; (2) it returns `None` where the pre-registration needs a refusal ("must refuse, not divide"), so a caller can ignore the answer; (3) it carries a missing day forward as a zero return, which manufactures a flat day where the data had none.
* **The answer to the prompt's question: they are equal where it matters and N6 does not reuse the path.** The M5n-173 note allows reusing it with a proving test, or implementing its own. N6 implements its own pure module in float64 (reading (4)), takes its input as equity marks at consecutive UTC midnights rather than an `EquitySummary` (which is coupled to the engine's per-bar loop), refuses where `metrics.py` returns `None` or carries forward, and **proves the equality by a parity test**: the same marks through `EquityCurve` -> `daily_returns` -> `sharpe_ratio` and through the new module agree to a relative 1e-12.

### The design (what is built, and what was decided where the prompt is silent)

One pure module, `src/trading_bot/backtesting/sharpe_stats.py`: no file, no store, no clock, no network; `numpy` for the bootstrap only; the `Decimal` to `float` conversion happens in one place, `daily_series`, as the quotient of two exact `Decimal` marks. All functions raise `ValueError` (or `TypeError` for a `float` money input) rather than return a number they cannot stand behind.

| Function | Contract |
|---|---|
| `daily_series(marks)` | `marks` is a sequence of `(datetime, Decimal)`, each at 00:00:00 UTC, timezone-aware, on consecutive days, equity positive. Returns the daily net returns as `float`, one fewer than the marks. **A missing, repeated or backward day, a non-midnight, a naive datetime or a non-positive equity is refused** (decision, `M5n-184`). A day with the same equity is a return of exactly 0.0. |
| `sharpe(returns, annualise=True)` | Mean over the sample standard deviation (`ddof` 1), times `sqrt(365)` when annualised. **Refuses** fewer than two returns and a series whose values are all equal (decided by `min == max`, because the mean of identical floats need not be exact and a rounding residue would otherwise divide). |
| `skewness_kurtosis(returns)` | Moment estimators about the sample mean, divided by `n` (population moments), skewness `m3 / m2^1.5` and **non-excess** kurtosis `m4 / m2^2` (reading (1); the estimator is the executing session's choice, `M5n-180`). Refuses below two returns and a zero variance. |
| `stationary_bootstrap_bounds(returns, *, p, resamples, seed)` | Politis-Romano, as reading (2): a start uniform on `[0, T)`, then at each step a new uniform start with probability `p` and otherwise the next index, wrapping circularly; `numpy.random.default_rng(seed)`; the annualised Sharpe recomputed per resample; returns the 5th percentile, the 2.5th percentile and the mean of the bootstrap Sharpe ratios (numpy's linear interpolation, `M5n-185`). The draw order and a fixed batch of 250 resamples are part of the algorithm, so the result is a function of `(returns, p, resamples, seed)` alone. **Refuses** `p` outside `(0, 1]`, fewer than two returns, `resamples < 1`, and a resample with zero variance. |
| `deflated_sharpe(sr, srs, t, skew, kurt, n)` | Reading (3), with `SR0 = 0` for `n = 1` (the inverse normal of 0 is undefined, and no deflation is the definition, so the DSR is the probabilistic Sharpe ratio). **Refuses** `len(srs) != n`, `t < 2`, `n < 1`, and a non-positive `1 - g3 SR + (g4 - 1) / 4 SR^2`. The Sharpe ratios, skewness and kurtosis are daily and unannualised. |
| `fee_telemetry(gross, fees, trades, *, entry_notional)` | `Decimal` throughout. Returns `net = gross - fees`, `fee_share = fees / |gross|` with its numerator and denominator beside it, `fees_per_trade = fees / trades` and `fee_bps = fees / entry_notional x 10,000`. **Refuses** `gross == 0`, `trades < 1`, a non-positive `entry_notional`, negative fees and a `float` input. **The fourth argument is added by this session** (`M5n-183`). |
| `buy_and_hold_marks(a, b, *, initial)` | Equal-weight, bought once at the first mark and held, no fee and no rebalance; the marks of the two series must be at the same instants; returns equity marks that `daily_series` takes. |

### Item 3. The hand-worked values (R-T, R-DQ), committed before any code

**F1, a constant series.** Ten returns of 0.01 (and ten of 0.0): `sharpe` **refuses** with `ValueError` (the sample sd is 0). The same refusal for `skewness_kurtosis`.

**F2, a known small series.** Marks `1000`, `1010.00`, `999.9000`, `1019.898000`, `1019.898000`, `1030.09698000`, which are the exact returns `0.01, -0.01, 0.02, 0, 0.01`. Mean `0.006`, sample variance `0.000130` (squared deviations `1.6e-5, 2.56e-4, 1.96e-4, 3.6e-5, 1.6e-5`, sum `5.2e-4`, over 4), sd `0.011401754250991380`. **Daily Sharpe `0.5262348115842175`; annualised `10.053701958827061`.** The fourth return is exactly `0.0`.

**F3, the moments.** The series `1, 2, 3, 4, 10`: mean 4, `m2 = 10`, `m3 = 36`, `m4 = 278.8`; **skewness `36 / 10^1.5 = 1.1384199576606166`, non-excess kurtosis `2.788`**.

**D1, N = 1 (SR0 = 0, so the DSR is the PSR).** `sr = 0.1`, `T = 101`, `g3 = 0`, `g4 = 3`: `z = 0.1 x 10 / sqrt(1.005) = 0.9975093361076329`, **DSR `0.8407413278013518`**; the same value with `srs = [0.1]`.

**D2, N = 6.** `srs = [0.02, 0.03, 0.04, 0.05, 0.06, 0.07]`: `V = 0.00035`, `PhiInv(1 - 1/6) = 0.9674215661017014`, `PhiInv(1 - 1/(6e)) = 1.5438425504501443`, **`SR0 = 0.024323406913442605`**. For `sr = 0.07`, `T = 2300`, `g3 = -0.5`, `g4 = 6`: **DSR `0.9840796754055363`**; for `sr = 0.05`, the same other inputs: **`0.8876609553599609`**.

**D4, N = 2.** `srs = [0.01, 0.03]`: `V = 0.0002`, the first inverse-normal term is `PhiInv(0.5) = 0`, `PhiInv(1 - 1/(2e)) = 0.9004525966377899`, **`SR0 = 0.007350450569975128`**; for `sr = 0.03`, `T = 500`, `g3 = 0`, `g4 = 3`: **DSR `0.6935150938004597`**.

**D5, monotone in SR.** With `g3 = 0`, `g4 = 3`, `T = 1000` and the six Sharpe ratios of D2, the DSR is strictly increasing over `sr = 0.00, 0.01, ..., 0.20`, from `0.22100929595628976` to `0.9999999807825788`. (Analytically, the derivative's sign is that of `1 + SR x SR0 / 2`, positive for non-negative `SR` and `SR0`.)

**F7, fee telemetry.** `gross 500`, `fees 50`, `trades 10`, `entry_notional 20000`: **net `450`, fee share `0.1` (50 over 500), fees per trade `5`, fee bps `25`**. With `gross -200`, `fees 20`: net `-220`, share `0.1` (over `|gross|`, the prompt's form; the charter's section 6 reports the share only when gross is positive, `M5n-183`). `gross 0`: **refuses**.

**F8, buy and hold.** Initial 1000, `A = 100, 110, 99` and `B = 50, 50, 60`: marks **`1000, 1050, 1095`**, returns **`0.05` and `0.0428571428571...` (3/70)**.

**The bootstrap has no hand-worked value; its predictions are properties.** (1) The same inputs and seed give bit-identical bounds; a different seed gives different ones. (2) The bounds order `p2_5 <= p5 <= mean` on a positive-mean, a negative-mean and an autocorrelated fixture. (3) With `p = 1` (a block length of 1) the distribution matches an independent iid bootstrap (a per-resample loop with its own generator, `scratch\p148\derive_bootstrap.py`) to within a mean difference of 0.15 and a standard-deviation ratio in `[0.97, 1.03]` at 20,000 resamples of a 60-day series; the reference measured 0.023 and 0.995 for two iid runs. (4) On a series of long runs (30 days up, 30 days down, four times) the `p = 1/20` bootstrap has a larger Sharpe spread than `p = 1`: the reference measured a ratio of 2.5, and the test asserts above 1.5. (5) The in-sample lower bound is the 5th percentile and the out-of-sample one the 2.5th, never swapped.

**Parity with `metrics.py` (the M5n-173 note).** The marks of F2 pushed through `EquityCurve` (samples at each midnight, which `:355` assigns to the day just ended), `daily_returns` and `sharpe_ratio` give the same annualised Sharpe as `sharpe(daily_series(marks))`, to a relative 1e-12.

**Refusals, each predicted to raise `ValueError`:** a missing day, a repeated day, a mark not at midnight, a naive datetime, a non-positive equity, fewer than two marks; `p = 0`, `p = 1.5`, `resamples = 0`, a one-return series; `n = 0`, `len(srs) != n`, `t = 1`, a non-positive DSR denominator; `trades = 0`, a non-positive notional, negative fees; and a `float` handed to `fee_telemetry`, which raises `TypeError`.

### The findings this section carries

See the commit message. In short: `metrics.py`'s formula equals reading (1) and its daily series equals section 1 under two conditions, N6 builds its own module and proves the parity by test, the fee-telemetry signature needs a notional the prompt did not give, and several choices the readings leave open are recorded where made.

## 102. M5n N6: the predictions for the survey of the estimator module, before it is run (P148 C4, R-T, R-DQ)

An observation log, so this section only adds. P148 surveys `src/trading_bot/backtesting/sharpe_stats.py` (commit `58ad896`) against the 92 tests of `tests/unit/test_sharpe_stats.py`. It runs once, after this section is committed. **No recorded bar is read and no backtest is run**: the survey mutates one new pure module and runs synthetic fixtures. Nothing here decides anything about S4.

### The method

The harness is the repository's `scripts/worktree_survey.py` with `scripts/survey_hook.py`, as in sections 91, 95 and 99: a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven inside it before any result counts, an unmutated baseline **predicted green at 92 passed**, every mutation byte-exact with exactly one match, asserted both when the spec was generated and when it runs, every restore shown SHA-equal, and the worktree removed afterwards. A MORE is recorded and a FEWER halts the survey. The spec is `survey_p148.json` (SHA-256 `56059b19594a0bc5dbdd1ad0a63f7b9f1368ef361c94c36da7ce03701b02e8da`), generated by the same program as the tables below, with the test list from `pytest --collect-only` at `58ad896` (92 node ids). The source and tests are not edited by the survey; the mutations exist only in the worktree.

**Where a mutation's outcome depends on a float, a seed or a numpy internal, the test is left out of the prediction and named below.** A test wrongly included is a FEWER and halts the survey; a test wrongly left out is a MORE and is recorded, so the cheap error is the one made on purpose.

### Totals

**60 mutations and 123 predicted failures** (92 tests). The predictions come from reading each test's fixture and assertion, not its name (`M5h`). **Tests killed by no mutation of this survey: 25 of 92.** That is the number for THIS survey's 60 mutations and not a whole-suite figure: most of the 25 are the refusal tests of a branch no mutation here weakened (for example the `-1` and `nan` rows of a boundary whose `0.0` row is mutated), and `test_the_euler_mascheroni_constant`, which no mutation moves because the constant is not mutated.

**Eight mutations are predicted to fail nothing: m13, m14, m15, m19, m20, m36, m50, m60.** Each is a hole or an equivalence declared in advance:

* `m15` (the first position is not forced to restart) is an **equivalent mutant**: position 0 has `last = 0` whether or not it restarts, because `numpy.where(restart, positions, 0)` is 0 there anyway, so the line `restart[:, 0] = True` is dead code (`M5n-190`).
* `m20` (the resamples drawn 100 at a time instead of 250) fails nothing because **no test pins the draw stream**. The module and `M5n-185` say the batch is part of the algorithm, and every statistical test is indifferent to it (`M5n-191`).
* `m36` (a variance term of exactly zero accepted), `m50` (a microsecond off midnight accepted) and `m60` (a zero first close accepted) are boundaries **no fixture sits on** (`M5n-192`). `m36` and `m60` would divide by zero.
* `m13` (the median reported as the mean), `m14` (the spread with `ddof` 1) and `m19` (the last day never a start) are statistical statements the tests make only within tolerances: 0.15 on the mean, 0.97 to 1.03 on the spread, and for `m19` a rotation is still a permutation so the vanishing-restart test is blind to the start's range.

**Where a prediction is most likely to be wrong, named in advance.**

* `m05` (the no-variance refusal disabled), 6 failures. The seventh test it could move, the bootstrap's constant-series test, is **excluded**: it then meets the per-resample refusal, whose message carries the same words, if numpy's `std` of identical floats is exactly zero. A MORE of one is expected if the `std` is not zero.
* `m17` (the wrap modulo `T - 1`) and `m19`: both can move the `p = 1` iid test by more than its 0.15 tolerance on this fixture, because the last day is never drawn or the first is doubled. Neither is predicted to; a MORE of one is possible.
* `m16` (no wrap), 9 failures, **all crashes** (`IndexError`) and so no kill under `M5i-115`: a mutation that is detected only by the code failing and not by a test asserting is worth knowing about.
* `m12` (the percentiles swapped), 4: the three ordering tests and the iid test; the vanishing-restart test cannot tell the two apart because every resample is equal.
* `m18` (a restart with probability 1 - p), 4, and `m23` (p = 1 refused), 3: the iid test and the widening test are predicted to fail in both; at `p = 0.05` the first mutation is near-iid, which the ordering and sign tests cannot tell from blocks.
* The DSR mutations `m26` to `m28`: the two-trial tests are blind to the first inverse-normal term's weight, because `PhiInv(0.5) = 0` (`m26`), and the more-trials test is an ordering that survives a rescaling of both expected maxima (`m28`).

**Classes.** The mutations expected to fail by a crash and not an assertion are `m16` (nine `IndexError`), `m23` (the iid and widening tests), `m25` (`ZeroDivisionError`), `m27` (the two-trial `ValueError` from the inverse normal), `m35`, `m43`, `m45`, `m46`, `m48`, and most of `m05`. The survey reports kill and crash separately and the score will say how many of the 123 were kills.

### Predicted failures

| Mutation | The break | Predicted failures | Tests |
|---|---|---|---|
| m01 | the Sharpe's variance divides by n (ddof 0) instead of n - 1 | 4 | T18, T20, T16, T40 |
| m02 | the annualisation uses 366 days | 5 | T18, T19, T16, T40, T41 |
| m03 | the Sharpe is never annualised | 4 | T18, T19, T16, T40 |
| m04 | the Sharpe divides by the variance, not the standard deviation | 4 | T18, T20, T16, T40 |
| m05 | the no-variance refusal is disabled | 6 | T21, T22, T23, T24, T25, T33 |
| m06 | a one-return series is no longer refused for its length | 2 | T27, T49 |
| m07 | a two-dimensional input is accepted | 1 | T29 |
| m08 | a non-finite return is accepted | 1 | T28 |
| m09 | the skewness divides by m2 squared | 1 | T30 |
| m10 | the kurtosis is the excess kurtosis | 2 | T30, T32 |
| m11 | the second moment divides by n - 1 | 2 | T30, T32 |
| m12 | the in-sample and out-of-sample percentiles are swapped | 4 | T37, T38, T39, T42 |
| m13 | the reported mean is the median | 0 | none |
| m14 | the reported spread uses ddof 1 | 0 | none |
| m15 | the first position is not forced to restart | 0 | none |
| m16 | a block that runs past the end does not wrap | 9 | T37, T38, T39, T40, T41, T43, T34, T35, T36 |
| m17 | the wrap is modulo T - 1 | 1 | T41 |
| m18 | a restart happens with probability 1 - p | 4 | T41, T42, T43, T51 |
| m19 | the last day is never a start | 0 | none |
| m20 | the resamples are drawn 100 at a time | 0 | none |
| m21 | the seed type is not checked | 1 | T52 |
| m22 | a restart probability of zero is accepted | 1 | T44 |
| m23 | a restart probability of one is refused | 3 | T42, T43, T51 |
| m24 | zero resamples is accepted | 1 | T48 |
| m25 | the expected maximum is computed for one trial too | 3 | T53, T54, T66 |
| m26 | the first inverse-normal term is weighted gamma, not 1 - gamma | 3 | T55, T58, T60 |
| m27 | the second inverse-normal argument is 1 - e/n | 6 | T55, T56, T58, T59, T60, T61 |
| m28 | the trials' variance divides by N, not N - 1 | 5 | T55, T56, T58, T59, T60 |
| m29 | the skewness term has the wrong sign | 2 | T58, T66 |
| m30 | the kurtosis term uses kurt - 3 (the excess form) with the non-excess constant | 4 | T53, T58, T59, T60 |
| m31 | the scaling is sqrt(T), not sqrt(T - 1) | 4 | T53, T58, T59, T60 |
| m32 | the probability is that of the opposite tail | 5 | T53, T58, T59, T60, T61 |
| m33 | the Sharpe-list length is not checked against n | 1 | T64 |
| m34 | one observation is accepted | 1 | T65 |
| m35 | a trial count of zero is accepted | 1 | T62 |
| m36 | a variance term of exactly zero is accepted | 0 | none |
| m37 | the Sharpe list is not checked for finiteness | 1 | T70 |
| m38 | net adds the fees | 2 | T71, T73 |
| m39 | the share is over the signed gross | 1 | T73 |
| m40 | the reported absolute gross and the share are over the signed gross | 1 | T73 |
| m41 | the fee per trade divides by trades + 1 | 1 | T71 |
| m42 | a basis point is a thousandth | 1 | T71 |
| m43 | a zero gross is accepted | 1 | T74 |
| m44 | negative fees are accepted | 1 | T80 |
| m45 | zero trades is accepted | 1 | T76 |
| m46 | a zero notional is accepted | 1 | T78 |
| m47 | a float passes the Decimal gate | 5 | T15, T81, T82, T83, T92 |
| m48 | a non-finite Decimal is accepted | 1 | T14 |
| m49 | a non-UTC offset is accepted | 1 | T11 |
| m50 | the microsecond is not part of midnight | 0 | none |
| m51 | a gap of more than one day is accepted | 1 | T6 |
| m52 | the return is the growth factor, not the return | 5 | T1, T3, T16, T17, T87 |
| m53 | a zero equity is accepted | 1 | T12 |
| m54 | one mark is accepted and yields no return | 1 | T5 |
| m55 | a third of the capital buys each asset | 1 | T86 |
| m56 | the second asset is normalised by the first asset's first close | 2 | T86, T87 |
| m57 | series marked at different instants are accepted | 1 | T89 |
| m58 | series of different length are left to zip | 1 | T88 |
| m59 | a zero initial capital is accepted | 1 | T91 |
| m60 | a zero first close is accepted | 0 | none |

### Declared abstentions and expected classes

| Mutation | Declared abstentions and expected classes |
|---|---|
| m01 | the annualiser test compares annualised to daily, and both move together |
| m02 | the p = 1 comparison against the iid reference tolerates a 0.14 percent rescaling of the Sharpe |
| m04 | the annualiser test compares annualised to daily, and both move together |
| m05 | the bootstrap's constant-series test may still pass: it then meets the resample refusal, which carries the same words, if numpy's std of identical floats is exactly zero; excluded from the prediction for that reason. Most of the six fail by ZeroDivisionError, a crash |
| m06 | it meets the no-variance refusal instead, whose message does not match 'at least two' |
| m09 | the symmetric series has m3 = 0, so any divisor gives zero skew |
| m11 | the symmetric series has m3 = 0, so it is unmoved |
| m12 | the vanishing-p test has every resample equal, so it cannot tell the two percentiles apart |
| m13 | the bounds ordering holds for the median too, and the sign test and the iid tolerance on the mean (0.15) are looser than the mean-median gap of a near-symmetric distribution |
| m14 | the difference is one part in 40,000 of the spread, far inside the 0.97 to 1.03 tolerance |
| m15 | an EQUIVALENT mutation: position 0 has last = 0 whether or not it restarts, so the line is dead code (a finding) |
| m16 | all nine fail by IndexError, a crash and not a kill; the p = 1 tests never continue a block, so the iid test and the no-variance test pass |
| m17 | possible MORE: the p = 1 iid test, which then never draws the last day and doubles the first, and may move by more than its tolerance; excluded because it depends on the fixture |
| m18 | at p = 0.05 the mutation is near-iid, which the ordering and sign tests cannot tell from blocks |
| m19 | a rotation is still a permutation, so the vanishing-p test is blind to the start's range; the iid test may move by more than 0.15 on this fixture (possible MORE) |
| m20 | NO TEST PINS THE DRAW STREAM: the module docstring and M5n-185 say the batch is part of the algorithm, and every statistical test is indifferent to it (a finding) |
| m23 | the first two fail by ValueError raised in the test body, a crash |
| m25 | all three fail by ZeroDivisionError (a variance over zero degrees of freedom), a crash |
| m26 | the two-trial case has PhiInv(0.5) = 0 in that term, so every two-trial test is blind to its weight |
| m27 | the two-trial tests fail by ValueError from inv_cdf (1 - e/2 is negative), a crash |
| m28 | the more-trials test is an ordering and survives a rescaling of both expected maxima |
| m29 | every other DSR fixture has zero skewness |
| m30 | the non-positive test still refuses (-1 under the mutation) and the ordering test is unmoved |
| m32 | the ignores-the-list test compares two calls with each other and is unmoved |
| m35 | it fails by ZeroDivisionError, a crash; the -1 case is still refused |
| m36 | NO TEST HAS A VARIANCE TERM OF EXACTLY ZERO; the mutation would then divide by zero (a finding) |
| m37 | the sr, skew and kurt cases are still refused |
| m38 | the numerators test does not read net |
| m39 | every positive-gross fixture gives the same share |
| m43 | it fails by decimal.DivisionByZero, a crash |
| m45 | it fails by decimal.DivisionByZero, a crash; -3 is still refused |
| m46 | it fails by decimal.DivisionByZero, a crash; -1 is still refused |
| m48 | it fails by decimal.InvalidOperation from the comparison with zero, a crash |
| m49 | the naive test still refuses |
| m50 | the off-midnight fixture is four hours late; no test has a mark a microsecond off (a finding) |
| m51 | the repeated and backward fixtures are still refused |
| m52 | the type-and-length test is unmoved |
| m53 | -5 is still refused |
| m55 | the returns test is a ratio of marks and the scaling cancels |
| m58 | zip(strict=True) still raises, with a message that does not match |
| m60 | no test has a zero FIRST close; the mutation would then divide by zero (a finding) |

### Key to the test codes

| Code | Test |
|---|---|
| T1 | `TestDailySeries::test_the_marks_become_the_exact_daily_returns` |
| T2 | `TestDailySeries::test_the_result_is_float_one_shorter_than_the_marks` |
| T3 | `TestDailySeries::test_a_day_with_no_position_and_no_change_is_a_zero_return` |
| T4 | `TestDailySeries::test_fewer_than_two_marks_is_refused[0]` |
| T5 | `TestDailySeries::test_fewer_than_two_marks_is_refused[1]` |
| T6 | `TestDailySeries::test_a_missing_day_is_refused_not_carried_forward` |
| T7 | `TestDailySeries::test_a_repeated_day_is_refused` |
| T8 | `TestDailySeries::test_a_backward_day_is_refused` |
| T9 | `TestDailySeries::test_a_mark_off_midnight_is_refused` |
| T10 | `TestDailySeries::test_a_naive_datetime_is_refused` |
| T11 | `TestDailySeries::test_a_non_utc_offset_is_refused` |
| T12 | `TestDailySeries::test_a_non_positive_equity_is_refused[0]` |
| T13 | `TestDailySeries::test_a_non_positive_equity_is_refused[-5]` |
| T14 | `TestDailySeries::test_a_non_finite_equity_is_refused` |
| T15 | `TestDailySeries::test_a_float_equity_is_the_leak_the_money_rule_stops` |
| T16 | `TestParityWithMetrics::test_the_f2_marks_give_the_same_annualised_sharpe_both_ways` |
| T17 | `TestParityWithMetrics::test_the_daily_returns_agree_too` |
| T18 | `TestSharpe::test_the_known_small_series_by_hand` |
| T19 | `TestSharpe::test_the_annualiser_is_the_square_root_of_365` |
| T20 | `TestSharpe::test_the_standard_deviation_is_the_sample_one` |
| T21 | `TestSharpe::test_a_constant_series_refuses_rather_than_divides[0.01]` |
| T22 | `TestSharpe::test_a_constant_series_refuses_rather_than_divides[0.0]` |
| T23 | `TestSharpe::test_a_constant_series_refuses_rather_than_divides[0.1]` |
| T24 | `TestSharpe::test_a_constant_series_refuses_rather_than_divides[-0.003]` |
| T25 | `TestSharpe::test_a_constant_series_whose_float_mean_is_inexact_still_refuses` |
| T26 | `TestSharpe::test_fewer_than_two_returns_refuses[returns0]` |
| T27 | `TestSharpe::test_fewer_than_two_returns_refuses[returns1]` |
| T28 | `TestSharpe::test_a_non_finite_return_refuses` |
| T29 | `TestSharpe::test_a_two_dimensional_input_refuses` |
| T30 | `TestMoments::test_skewness_and_non_excess_kurtosis_by_hand` |
| T31 | `TestMoments::test_a_symmetric_series_has_no_skew` |
| T32 | `TestMoments::test_a_two_point_series_has_kurtosis_one` |
| T33 | `TestMoments::test_a_constant_series_refuses` |
| T34 | `TestStationaryBootstrap::test_the_same_inputs_and_seed_give_identical_bounds` |
| T35 | `TestStationaryBootstrap::test_a_different_seed_gives_different_bounds` |
| T36 | `TestStationaryBootstrap::test_the_result_does_not_depend_on_the_input_container` |
| T37 | `TestStationaryBootstrap::test_the_bounds_order_2_5th_below_5th_below_the_mean[positive]` |
| T38 | `TestStationaryBootstrap::test_the_bounds_order_2_5th_below_5th_below_the_mean[negative]` |
| T39 | `TestStationaryBootstrap::test_the_bounds_order_2_5th_below_5th_below_the_mean[runs]` |
| T40 | `TestStationaryBootstrap::test_the_bootstrap_mean_has_the_sign_of_the_sample_sharpe` |
| T41 | `TestStationaryBootstrap::test_a_vanishing_restart_probability_rotates_the_whole_series` |
| T42 | `TestStationaryBootstrap::test_a_block_length_of_one_matches_an_independent_iid_bootstrap` |
| T43 | `TestStationaryBootstrap::test_blocks_widen_the_distribution_of_an_autocorrelated_series` |
| T44 | `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[0.0]` |
| T45 | `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[-0.1]` |
| T46 | `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[1.5]` |
| T47 | `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[nan]` |
| T48 | `TestStationaryBootstrap::test_zero_resamples_refuses` |
| T49 | `TestStationaryBootstrap::test_a_one_return_series_refuses` |
| T50 | `TestStationaryBootstrap::test_a_constant_series_refuses` |
| T51 | `TestStationaryBootstrap::test_a_resample_with_no_variance_refuses` |
| T52 | `TestStationaryBootstrap::test_a_float_seed_refuses` |
| T53 | `TestDeflatedSharpe::test_one_trial_has_no_deflation_so_it_is_the_probabilistic_sharpe_ratio` |
| T54 | `TestDeflatedSharpe::test_one_trial_ignores_what_the_single_sharpe_list_says_beyond_its_length` |
| T55 | `TestDeflatedSharpe::test_the_expected_maximum_for_six_trials_by_hand` |
| T56 | `TestDeflatedSharpe::test_the_expected_maximum_for_two_trials_by_hand` |
| T57 | `TestDeflatedSharpe::test_the_euler_mascheroni_constant` |
| T58 | `TestDeflatedSharpe::test_six_trials_with_skew_and_fat_tails_by_hand` |
| T59 | `TestDeflatedSharpe::test_two_trials_by_hand` |
| T60 | `TestDeflatedSharpe::test_it_is_strictly_increasing_in_the_sharpe_for_a_symmetric_case` |
| T61 | `TestDeflatedSharpe::test_more_trials_deflate_the_same_sharpe` |
| T62 | `TestDeflatedSharpe::test_a_trial_count_below_one_refuses[0]` |
| T63 | `TestDeflatedSharpe::test_a_trial_count_below_one_refuses[-1]` |
| T64 | `TestDeflatedSharpe::test_a_sharpe_list_not_matching_n_refuses` |
| T65 | `TestDeflatedSharpe::test_fewer_than_two_observations_refuses` |
| T66 | `TestDeflatedSharpe::test_a_non_positive_variance_term_refuses` |
| T67 | `TestDeflatedSharpe::test_a_non_finite_input_refuses[sr]` |
| T68 | `TestDeflatedSharpe::test_a_non_finite_input_refuses[skew]` |
| T69 | `TestDeflatedSharpe::test_a_non_finite_input_refuses[kurt]` |
| T70 | `TestDeflatedSharpe::test_a_non_finite_input_refuses[srs]` |
| T71 | `TestFeeTelemetry::test_net_share_per_trade_and_basis_points_by_hand` |
| T72 | `TestFeeTelemetry::test_the_numerators_and_denominators_are_reported_beside_each_ratio` |
| T73 | `TestFeeTelemetry::test_the_share_is_over_the_absolute_gross` |
| T74 | `TestFeeTelemetry::test_a_zero_gross_refuses` |
| T75 | `TestFeeTelemetry::test_zero_fees_are_a_zero_share` |
| T76 | `TestFeeTelemetry::test_fewer_than_one_trade_refuses[0]` |
| T77 | `TestFeeTelemetry::test_fewer_than_one_trade_refuses[-3]` |
| T78 | `TestFeeTelemetry::test_a_non_positive_notional_refuses[notional0]` |
| T79 | `TestFeeTelemetry::test_a_non_positive_notional_refuses[notional1]` |
| T80 | `TestFeeTelemetry::test_negative_fees_refuse` |
| T81 | `TestFeeTelemetry::test_a_float_figure_is_refused[gross]` |
| T82 | `TestFeeTelemetry::test_a_float_figure_is_refused[fees]` |
| T83 | `TestFeeTelemetry::test_a_float_figure_is_refused[notional]` |
| T84 | `TestFeeTelemetry::test_a_non_int_trade_count_is_refused` |
| T85 | `TestFeeTelemetry::test_a_boolean_trade_count_is_refused` |
| T86 | `TestBuyAndHold::test_equal_weight_marks_by_hand` |
| T87 | `TestBuyAndHold::test_its_daily_returns_by_hand` |
| T88 | `TestBuyAndHold::test_series_of_different_length_refuse` |
| T89 | `TestBuyAndHold::test_series_marked_at_different_instants_refuse` |
| T90 | `TestBuyAndHold::test_a_non_positive_close_refuses` |
| T91 | `TestBuyAndHold::test_a_non_positive_initial_refuses` |
| T92 | `TestBuyAndHold::test_a_float_close_is_refused` |

### The findings this section carries

See the commit message. In short: the first-position line of the bootstrap is dead code, nothing pins the draw stream, and three boundaries have no fixture on them.

## 103. M5n N6: the scored result of the estimator module's survey (P148 C5, R-T)

An observation log, so this section only adds. The survey section 102 predicted ran twice, because it HALTED at `m18`. Both runs used the repository's `scripts/worktree_survey.py` and `scripts/survey_hook.py` in a detached worktree outside the repository (`scratch\p148\wt_survey`) at `abb8827`, the commit that carries section 102, with the import location of `trading_bot` and `tests` printed inside the worktree before any result, an unmutated baseline of **92 passed** (2.21 s, then 1.23 s), every restore shown SHA-equal, every copied file intact afterwards, and `git worktree list` showing the main worktree only after each. Nothing here decides anything about S4. No recorded bar was read and no backtest was run.

* **Run 1**, `2026-10-25T14:02:37Z` to `14:03:22Z`, from the committed spec (`survey_p148.json`, SHA-256 `56059b19594a0bc5dbdd1ad0a63f7b9f1368ef361c94c36da7ce03701b02e8da`), exit 1, standard error empty: `m01` to `m17` scored, **`m18` HALTED the survey with a FEWER**.
* **Run 2**, `2026-10-25T14:03:49Z` to `14:05:09Z`, from `survey_p148_rest.json` (SHA-256 `dab849a1d7518af947551de5976d752c50d9183992d361b206610aea48f60009`), exit 0, standard error empty: `m19` to `m60`. It holds the 42 entries of the committed spec from `m19` on, **byte-for-byte, with no prediction changed**; it was written only because the harness stops at a FEWER, and `m18` was NOT re-run or re-predicted.

### Result

**60 mutations scored: 56 MATCH, 3 MORE (`m05`, `m17`, `m19`), 1 FEWER (`m18`).** 123 failures were predicted and 125 observed; **94 were kills and 31 crashes** (`M5i-115`). The three MOREs are each a test section 102 named in advance as possible and left out of the prediction on purpose (`m05` the bootstrap's constant-series test, `m17` and `m19` the `p = 1` iid test); a MORE is recorded and none is a surprise. The crashes are `ZeroDivisionError` 10, `IndexError` 10, `ValueError` 3, `statistics.StatisticsError` 3, `decimal.DivisionByZero` 3, `TypeError` 1 and `decimal.InvalidOperation` 1.

### The FEWER at `m18`, and why the prediction was wrong (REASONED, for a MEASURED halt)

`m18` changes `rng.random((batch, t)) < p` to `> p`, so a restart happens with probability `1 - p`. Section 102 predicted four failures: the vanishing-restart test, the iid test, the widening test and the no-variance test. Three failed. **The widening test did not.** It runs the bootstrap twice, at `p = 1/20` and at `p = 1.0`, and asserts the first run's spread is more than 1.5 times the second's. Section 102 reasoned about the first arm only, which becomes near-iid under the mutation. **The `p = 1.0` arm is mutated too:** `random > 1.0` is never true, so no position restarts, every resample is a rotation of the whole series, every resample has the sample Sharpe, and that arm's spread is float noise near zero. The ratio is then enormous and the assertion `> 1.5` holds. The prediction was correct for the mutation described and wrong for the mutation applied, which is the error `M5h` names, reasoning from what a test is for and not from what it reaches; and the fact that this test passes under a mutation that turns the ordinary bootstrap into a rotation shows the widening test is satisfied by a ratio of anything large, not by blocks in particular. Also, the vanishing-restart test failed by a `ValueError` crash and not an assertion: at `p = 1e-12` the mutation restarts almost everywhere, so a resample of five values has no variance (`M5n-193`).

### Scored table

| Mutation | The break | Predicted | Observed | Verdict | Kills | Crashes |
|---|---|---|---|---|---|---|
| m01 | the Sharpe's variance divides by n (ddof 0) instead of n - 1 | 4 | 4 | MATCH | 4 | 0 |
| m02 | the annualisation uses 366 days | 5 | 5 | MATCH | 5 | 0 |
| m03 | the Sharpe is never annualised | 4 | 4 | MATCH | 4 | 0 |
| m04 | the Sharpe divides by the variance, not the standard deviation | 4 | 4 | MATCH | 4 | 0 |
| m05 | the no-variance refusal is disabled | 6 | 7 | MORE | 1 | 6 |
| m06 | a one-return series is no longer refused for its length | 2 | 2 | MATCH | 2 | 0 |
| m07 | a two-dimensional input is accepted | 1 | 1 | MATCH | 0 | 1 |
| m08 | a non-finite return is accepted | 1 | 1 | MATCH | 1 | 0 |
| m09 | the skewness divides by m2 squared | 1 | 1 | MATCH | 1 | 0 |
| m10 | the kurtosis is the excess kurtosis | 2 | 2 | MATCH | 2 | 0 |
| m11 | the second moment divides by n - 1 | 2 | 2 | MATCH | 2 | 0 |
| m12 | the in-sample and out-of-sample percentiles are swapped | 4 | 4 | MATCH | 4 | 0 |
| m13 | the reported mean is the median | 0 | 0 | MATCH | 0 | 0 |
| m14 | the reported spread uses ddof 1 | 0 | 0 | MATCH | 0 | 0 |
| m15 | the first position is not forced to restart | 0 | 0 | MATCH | 0 | 0 |
| m16 | a block that runs past the end does not wrap | 9 | 9 | MATCH | 0 | 9 |
| m17 | the wrap is modulo T - 1 | 1 | 2 | MORE | 2 | 0 |
| m18 | a restart happens with probability 1 - p | 4 | 3 | FEWER | 2 | 1 |
| m19 | the last day is never a start | 0 | 1 | MORE | 1 | 0 |
| m20 | the resamples are drawn 100 at a time | 0 | 0 | MATCH | 0 | 0 |
| m21 | the seed type is not checked | 1 | 1 | MATCH | 1 | 0 |
| m22 | a restart probability of zero is accepted | 1 | 1 | MATCH | 1 | 0 |
| m23 | a restart probability of one is refused | 3 | 3 | MATCH | 1 | 2 |
| m24 | zero resamples is accepted | 1 | 1 | MATCH | 0 | 1 |
| m25 | the expected maximum is computed for one trial too | 3 | 3 | MATCH | 0 | 3 |
| m26 | the first inverse-normal term is weighted gamma, not 1 - gamma | 3 | 3 | MATCH | 3 | 0 |
| m27 | the second inverse-normal argument is 1 - e/n | 6 | 6 | MATCH | 3 | 3 |
| m28 | the trials' variance divides by N, not N - 1 | 5 | 5 | MATCH | 5 | 0 |
| m29 | the skewness term has the wrong sign | 2 | 2 | MATCH | 2 | 0 |
| m30 | the kurtosis term uses kurt - 3 (the excess form) with the non-excess constant | 4 | 4 | MATCH | 4 | 0 |
| m31 | the scaling is sqrt(T), not sqrt(T - 1) | 4 | 4 | MATCH | 4 | 0 |
| m32 | the probability is that of the opposite tail | 5 | 5 | MATCH | 5 | 0 |
| m33 | the Sharpe-list length is not checked against n | 1 | 1 | MATCH | 1 | 0 |
| m34 | one observation is accepted | 1 | 1 | MATCH | 1 | 0 |
| m35 | a trial count of zero is accepted | 1 | 1 | MATCH | 0 | 1 |
| m36 | a variance term of exactly zero is accepted | 0 | 0 | MATCH | 0 | 0 |
| m37 | the Sharpe list is not checked for finiteness | 1 | 1 | MATCH | 1 | 0 |
| m38 | net adds the fees | 2 | 2 | MATCH | 2 | 0 |
| m39 | the share is over the signed gross | 1 | 1 | MATCH | 1 | 0 |
| m40 | the reported absolute gross and the share are over the signed gross | 1 | 1 | MATCH | 1 | 0 |
| m41 | the fee per trade divides by trades + 1 | 1 | 1 | MATCH | 1 | 0 |
| m42 | a basis point is a thousandth | 1 | 1 | MATCH | 1 | 0 |
| m43 | a zero gross is accepted | 1 | 1 | MATCH | 0 | 1 |
| m44 | negative fees are accepted | 1 | 1 | MATCH | 1 | 0 |
| m45 | zero trades is accepted | 1 | 1 | MATCH | 0 | 1 |
| m46 | a zero notional is accepted | 1 | 1 | MATCH | 0 | 1 |
| m47 | a float passes the Decimal gate | 5 | 5 | MATCH | 5 | 0 |
| m48 | a non-finite Decimal is accepted | 1 | 1 | MATCH | 0 | 1 |
| m49 | a non-UTC offset is accepted | 1 | 1 | MATCH | 1 | 0 |
| m50 | the microsecond is not part of midnight | 0 | 0 | MATCH | 0 | 0 |
| m51 | a gap of more than one day is accepted | 1 | 1 | MATCH | 1 | 0 |
| m52 | the return is the growth factor, not the return | 5 | 5 | MATCH | 5 | 0 |
| m53 | a zero equity is accepted | 1 | 1 | MATCH | 1 | 0 |
| m54 | one mark is accepted and yields no return | 1 | 1 | MATCH | 1 | 0 |
| m55 | a third of the capital buys each asset | 1 | 1 | MATCH | 1 | 0 |
| m56 | the second asset is normalised by the first asset's first close | 2 | 2 | MATCH | 2 | 0 |
| m57 | series marked at different instants are accepted | 1 | 1 | MATCH | 1 | 0 |
| m58 | series of different length are left to zip | 1 | 1 | MATCH | 1 | 0 |
| m59 | a zero initial capital is accepted | 1 | 1 | MATCH | 1 | 0 |
| m60 | a zero first close is accepted | 0 | 0 | MATCH | 0 | 0 |

### Tests that fail under none of the 60 mutations: 24 of 92

This is the number for THIS survey's mutations and not a whole-suite figure. Most are the refusal tests of a branch no mutation here weakened, or a `-1`, `nan` or `-3` row beside a mutated `0` row. The list, for the record:

* `TestBuyAndHold::test_a_non_positive_close_refuses`
* `TestDailySeries::test_a_backward_day_is_refused`
* `TestDailySeries::test_a_mark_off_midnight_is_refused`
* `TestDailySeries::test_a_naive_datetime_is_refused`
* `TestDailySeries::test_a_non_positive_equity_is_refused[-5]`
* `TestDailySeries::test_a_repeated_day_is_refused`
* `TestDailySeries::test_fewer_than_two_marks_is_refused[0]`
* `TestDailySeries::test_the_result_is_float_one_shorter_than_the_marks`
* `TestDeflatedSharpe::test_a_non_finite_input_refuses[kurt]`
* `TestDeflatedSharpe::test_a_non_finite_input_refuses[skew]`
* `TestDeflatedSharpe::test_a_non_finite_input_refuses[sr]`
* `TestDeflatedSharpe::test_a_trial_count_below_one_refuses[-1]`
* `TestDeflatedSharpe::test_the_euler_mascheroni_constant`
* `TestFeeTelemetry::test_a_boolean_trade_count_is_refused`
* `TestFeeTelemetry::test_a_non_int_trade_count_is_refused`
* `TestFeeTelemetry::test_a_non_positive_notional_refuses[notional1]`
* `TestFeeTelemetry::test_fewer_than_one_trade_refuses[-3]`
* `TestFeeTelemetry::test_the_numerators_and_denominators_are_reported_beside_each_ratio`
* `TestFeeTelemetry::test_zero_fees_are_a_zero_share`
* `TestMoments::test_a_symmetric_series_has_no_skew`
* `TestSharpe::test_fewer_than_two_returns_refuses[returns0]`
* `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[-0.1]`
* `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[1.5]`
* `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[nan]`

**Only 50 of the 92 tests were ever killed by an assertion; 18 more fail only by crash**, and a crash is a test that did not look (`M5i-115`). The clearest case is `m16`: removing the wrap fails nine tests, all by `IndexError`, so a wrap error that does not crash is caught only by the vanishing-restart test, as `m17` shows (`m17`: the wrap modulo `T - 1` is killed by two tests and no others).

### What the survey confirmed of section 102's holes

`m15` (an equivalent mutant: `restart[:, 0] = True` is dead code), `m20` (no test pins the draw stream), `m36`, `m50` and `m60` (a variance term of exactly zero, a microsecond off midnight, a zero first close) each fail **nothing**, as predicted, and `m13` and `m14` too. **None of them is closed in this commit**: changing the module or its tests after the survey would be a change nobody had surveyed, and which of them to close is the owner's. Two class predictions were wrong and are noted without effect on the sets: `m07` was predicted a kill and is a `TypeError` crash (`float()` of an array), and `m27`'s two-trial failures are `statistics.StatisticsError` and not `ValueError`.

### The findings this section carries

See the commit message.

## 104. M5n N7: the predictions for the estimator module's changes and the runner, before any code (P149 C2, R-T, R-DQ)

An observation log, so this section only adds. HEAD is `918ca98` (the charter commit of P149), on `m5n`, `main` at `ee8d485`, and the pre-registration's SHA-256 is still `e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e`. P149 step 2 asks for three predictions, and they are committed here before any code, test or script of P149 is drafted. **No recorded bar was read and no backtest was run on recorded data.** Every figure below was derived by scripts in `scratch\p149` (`derive_golden.py`, `derive_worlds.py`, `derive_e1.py`, `derive_e1_judge.py`, `render_w5.py`) that import neither the estimator module nor the runner: statistics are computed in 60-digit `Decimal` from the exact `Decimal` returns, Phi and its inverse by `math.erf` and a bisection, percentiles by hand, and the bootstrap by a plain per-resample loop. **What those scripts share with the module is the numpy generator and the order of its draws** (per batch of 250 resamples, `integers(0, T, size=(batch, T))` and then `random((batch, T))`), because that stream is what a golden value pins.

### What is built (the design the predictions are about)

* **`sharpe_stats.py` (item 3a).** The line `restart[:, 0] = True` is deleted (it is dead code, `M5n-190`, confirmed by the P148 survey's `m15`). A golden-value test pins the bootstrap's stream, which closes `m20` (`M5n-191`). `daily_series` accepts one form of mark and refuses all others, with tests at 23:59:59.999, 00:00:00.000001 and 00:00:00 exactly, which closes `m50` (`M5n-192`). **One defect found while predicting is fixed in the same commit** (`M5n-200`): the bootstrap decides a resample has no variance by `deviation == 0.0`, and numpy's standard deviation of three equal floats is not always zero (`np.std([0.1, 0.1, 0.1], ddof=1)` is `1.6996749443881478e-17`, measured here, a fact about numpy and not about the module), so a constant non-zero resample would give a Sharpe near 1e16 where it must refuse. It becomes `min == max` over the resample, as `_require_spread` already does for the series.
* **`scripts/n7_evaluate.py` (item 3b).** The N0 guard first, then the evaluation. The pure core is `judge(runs, *, floors, resamples, seed, p)` over `CandidateRun` values (label, name, timeframe, closed trades, open at end, gross, fees, entry notional, daily marks); it applies pre-registration sections 5 to 8 and knows nothing of the backtester, so its worlds are written as returns. `compute_start` finds the first UTC day on which every candidate's indicators are defined for both pairs: the UTC day of the latest, over candidate and pair, of the open time of the first decision bar that ends a gap-free run of the strategy's `warmup_period` bars (`M5n-206`). `run_candidate` runs one candidate through `backtest_system` on the D1 path over `[start, 2024-01-01)` and samples equity at each UTC midnight with its own candle subscriber; the sensitivities re-run it with other costs; the context is the equal-weight buy and hold. `main` writes one result file, refusing to overwrite one, and prints the report and the file's SHA-256.
* **Constants the runner pins, each read from the pre-registration and pinned by a test:** floors `1d` 30 in sample and 12 out of sample, `4h` 120 and 48; bootstrap `p = 1/20`, 10,000 resamples, seed 20261025; DSR threshold 0.95 with `N` the number of candidates (6); the in-sample span ending `2024-01-01`; fee 0.10 and stop slippage 1.20 percent for the verdict; the sensitivities `fee_0.075` (fee 0.075), `slip_0.66` and `slip_0.10` (stop slippage 0.66 and 0.10).
* **Readings recorded where they are made.** The 4h candidates are marked at the 4h bar that closes at 00:00, whose close is the 1d archive close of that day (REASONED, and unchecked until N7, `M5n-207`); the buy and hold buys at the open of the first day, so no bar before the span is needed (`M5n-202`); a candidate whose daily returns have no variance has no Sharpe and the run refuses (`M5n-203`); a bootstrap that refuses fails gate (b) and is printed `n/a` (`M5n-204`); the telemetry counts closed round trips only (`M5n-205`).

### Prediction 1. The golden bootstrap bounds

The fixture is 24 typed daily returns (`0.012, -0.007, 0.004, 0.009, -0.011, 0.015, 0.002, -0.004, 0.008, 0.006, -0.009, 0.013, 0.001, -0.002, 0.010, -0.006, 0.005, 0.011, -0.008, 0.003, 0.007, -0.001, 0.009, -0.005`), whose sample Sharpe is `6.413997967427307` annualised, with the pre-registered `p = 1/20` and seed. **G1 and G2 are the tests** (tolerance a relative 1e-9); G1's 600 resamples straddle three batches (250, 250, 100), so the batch size is part of the value.

| Row | p | Resamples | Seed | Batch | p5 | p2_5 | mean | std |
|---|---|---|---|---|---|---|---|---|
| G1 | 0.05 | 600 | 20261025 | 250 | `4.927886866519763` | `4.439440781578283` | `6.458913293099271` | `0.9760475595174631` |
| G2 | 0.05 | 10000 | 20261025 | 250 | `4.838931764884872` | `4.471253881083067` | `6.439681460048089` | `0.9555063041823855` |
| G3 (not a test: the stream a batch of 100 would draw) | 0.05 | 600 | 20261025 | 100 | `4.81097837508935` | `4.399061271556962` | `6.4141602214840665` | `0.9164827387133547` |

**G3 is what `m20` (a batch of 100) would draw:** its `p5` differs from G1's by 0.117, so the golden test kills `m20`. The same stream is checked at 10,000 resamples (G2) because that is the pre-registered count.

### Prediction 2. The one accepted form of mark

`daily_series(marks)` accepts a sequence of at least two marks, each **a `tuple` of exactly two items `(at, equity)`**, where `type(at) is datetime`, `at.tzinfo is datetime.timezone.utc`, `at` is exactly 00:00:00.000000, `type(equity) is Decimal`, finite and above zero, on consecutive days. It refuses everything else, as follows.

| Input | Refused with |
|---|---|
| fewer than two marks | `ValueError` |
| an element that is not a `tuple` (a list, a `namedtuple`) | `TypeError` |
| a tuple of length other than 2 | `TypeError` |
| `at` not exactly a `datetime` (a `date`, a `pandas.Timestamp`, a `str`, an `int`) | `TypeError` |
| a naive `datetime` | `ValueError` |
| a `tzinfo` that is not `timezone.utc` (+02:00, `ZoneInfo("UTC")`, `timezone(timedelta(0), "Z")`) | `ValueError` |
| `at` = 23:59:59.999 (the day before) | `ValueError` |
| `at` = 00:00:00.000001 | `ValueError` |
| `at` = 00:00:00 exactly | **accepted** |
| `equity` not exactly a `Decimal` (a `float`, an `int`, a `str`, a `bool`, a `numpy.float64`) | `TypeError` |
| a `Decimal` `NaN` or infinity | `ValueError` |
| an equity of zero or below | `ValueError` |
| a missing, repeated or backward day | `ValueError` |

This is stricter than the P148 module in two ways, both intended: an `int` equity is refused (it was accepted), and a `tzinfo` that is merely zero-offset but is not `timezone.utc` is refused (it was accepted).

### Prediction 3. The N0 guard

`check_n0_guard(root)` runs before anything is opened, in this order, and refuses with `GuardError`; `main` prints `refused: <code>: <message>` to standard error and exits 2. Every code has a test that builds a throwaway git repository and breaks one condition: `git_unavailable` (no `git` on the path), `charter_unreadable` (no repository, or no charter at HEAD), `tag_missing` (condition a), `n0_line_missing`, `n0_line_duplicated`, `n0_commit_unknown`, `n0_commit_not_ancestor` (condition b), and `digest_line_missing`, `digest_line_duplicated`, `digest_file_unreadable`, `digest_mismatch` (condition c; the mismatch test runs once for each of the three files). Beside them: a repository satisfying all three is accepted; a short hash of 7 characters is accepted; HEAD itself as the N0 commit is accepted; an annotated tag is accepted; a line that appears only in the working copy of the charter is `n0_line_missing`; a line with trailing text or upper-case hexadecimal is `n0_line_missing`; `main` refuses before it reads the config or the store. The guard run against THIS repository must refuse with `tag_missing`, since no `milestone/M5m` tag exists; that is checked by hand in the report and is not a test, because the tag will one day exist.

### Prediction 4. The runner on fixture worlds

**The judge worlds.** Each has three candidates (`C1` and `C2` on `1d` with floor 5, `C4` on `4h` with floor 8), 40 daily returns built from an 8-return pattern repeated five times, marks built in exact `Decimal` from 10,000 and quantised to 8 places at every step, the bootstrap at 400 resamples (p = 0.05, seed 20261025) and the deflated Sharpe at `N = 3`. The patterns: `S1` `0.012, -0.004, 0.009, 0.015, -0.002, 0.011, 0.007, -0.005`; `S2` `0.010, -0.004, 0.008, 0.012, -0.003, 0.009, 0.006, -0.005`; `N1` `0.010, -0.011, 0.008, -0.009, 0.006, -0.007, 0.004, -0.005`; `N2` `0.011, -0.010, 0.009, -0.008, 0.007, -0.006, 0.005, -0.004`.

**W1, no candidate passes** (patterns N1, N2, N1; trades 9, 7, 10).

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 9 | 5 | 40 | -1.205218 | -2.299758 | 0.217170 | FAILED (bootstrap, dsr) |
| C2 | 1d | 7 | 5 | 40 | 1.205218 | 0.168780 | 0.502399 | FAILED (dsr) |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.217170 | FAILED (bootstrap, dsr) |

Verdict: **FAIL**.

**W2, one passes** (S1, N2, N1; trades 9, 7, 10).

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 9 | 5 | 40 | 13.768603 | 12.398619 | 0.977629 | PASS |
| C2 | 1d | 7 | 5 | 40 | 1.205218 | 0.168780 | 0.032369 | FAILED (dsr) |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.004209 | FAILED (bootstrap, dsr) |

Verdict: **SELECTED** C1.

**W3, a tie in Sharpe broken by more trades** (S1, S1, N1; trades 9, 6, 10): the two identical series tie exactly, and the section 7 rule picks the one with more trades.

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 9 | 5 | 40 | 13.768603 | 12.398619 | 0.968362 | PASS |
| C2 | 1d | 6 | 5 | 40 | 13.768603 | 12.398619 | 0.968362 | PASS |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.002528 | FAILED (bootstrap, dsr) |

Verdict: **SELECTED** C1.

**W3b, a tie that section 7 does not break** (S1, S1, N1; trades 9, 9, 10): the verdict is INDETERMINATE and the run exits 1; no candidate is selected by an invented rule (`M5n-208`).

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 9 | 5 | 40 | 13.768603 | 12.398619 | 0.968362 | PASS |
| C2 | 1d | 9 | 5 | 40 | 13.768603 | 12.398619 | 0.968362 | PASS |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.002528 | FAILED (bootstrap, dsr) |

Verdict: **INDETERMINATE** ['C1', 'C2'].

**W4, a floor failure** (S1, S1, N1; trades 4, 7, 10): `C1` has the same Sharpe as `C2` and the lower trade count and is below its floor, so it is excluded and `C2` is selected.

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 4 | 5 | 40 | 13.768603 | 12.398619 | 0.968362 | EXCLUDED (below floor) |
| C2 | 1d | 7 | 5 | 40 | 13.768603 | 12.398619 | 0.968362 | PASS |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.002528 | FAILED (bootstrap, dsr) |

Verdict: **SELECTED** C2.

**W5, a sensitivity that would flip a gate and must not change the verdict.** Base (S2, N2, N1; trades 9, 7, 10), and the sensitivity `fee_0.075` (S2, S1, N1), in which `C2` would pass and `C1` would fail the deflated Sharpe gate because the trial variance moved.

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 9 | 5 | 40 | 11.956331 | 10.659343 | 0.959230 | PASS |
| C2 | 1d | 7 | 5 | 40 | 1.205218 | 0.168780 | 0.059473 | FAILED (dsr) |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.009462 | FAILED (bootstrap, dsr) |

Verdict: **SELECTED** C1.

| Candidate | Timeframe | Trades | Floor | Days | Sharpe (annual) | Bootstrap p5 | DSR | Status |
|---|---|---|---|---|---|---|---|---|
| C1 | 1d | 9 | 5 | 40 | 11.956331 | 10.659343 | 0.926813 | FAILED (dsr) |
| C2 | 1d | 7 | 5 | 40 | 13.768603 | 12.398619 | 0.975828 | PASS |
| C4 | 4h | 10 | 8 | 40 | -1.205218 | -2.299758 | 0.003773 | FAILED (bootstrap, dsr) |

Verdict: **SELECTED** C2.

**The report the runner prints for W5, in full**, with the telemetry supplied as typed (`C1` 9 trades, gross 500, fees 50, entry notional 20,000; `C2` 7 trades, gross -200, fees 20, notional 8,000; `C4` 10 trades, gross 0, fees 10, notional 1,000), the window `[2024-03-01, 2024-04-10)`, and the context taken from the marks of pattern `N2`. The fee telemetry comes first, before any Sharpe. The format: key=value in a fixed order, the share and the basis points `n/a` when their denominator is zero or there is no trade, the flag `gross<=0` when the gross is zero or negative and `no_trades` when there is none.

```
N7 in-sample evaluation (pre-registration sections 5 to 8)
window [2024-03-01, 2024-04-10)
fee telemetry (telemetry only, never a criterion)
  C1 trades=9 gross=500 fees=50 net=450 entry_notional=20000 fee_share=0.100000 fee_bps=25.0000
  C2 trades=7 gross=-200 fees=20 net=-220 entry_notional=8000 fee_share=0.100000 fee_bps=25.0000 flag=gross<=0
  C4 trades=10 gross=0 fees=10 net=-10 entry_notional=1000 fee_share=n/a fee_bps=100.0000 flag=gross<=0
candidates (bootstrap p=0.05 resamples=400 seed=20261025; deflated Sharpe trials=3)
  C1 1d trades=9 floor=5 days=40 sharpe_annual=11.956331 boot_p5=10.659343 dsr=0.959230 status=PASS
  C2 1d trades=7 floor=5 days=40 sharpe_annual=1.205218 boot_p5=0.168780 dsr=0.059473 status=FAILED (dsr)
  C4 4h trades=10 floor=8 days=40 sharpe_annual=-1.205218 boot_p5=-2.299758 dsr=0.009462 status=FAILED (bootstrap, dsr)
verdict SELECTED C1
sensitivity fee_0.075 would_select=C2 flips=2
  flip C1 dsr pass->fail
  flip C2 dsr fail->pass
context buy_and_hold sharpe_annual=1.205218 days=40
```

**The end-to-end world E1.** Two scripted 1d candidates on BTCUSDT and ETHUSDT over `2024-03-01` to `2024-03-04` (three days of 1m bars), N5 sizing, the real fill model, floors patched to one closed trade, bootstrap 400, `N = 2`. `C1` buys BTCUSDT on the bar of 2024-03-01 (entry at the next open, 100.05; quantity 19.98001, the cap-bound figure `tests/unit/test_backtest_d1.py` pins) and a minute at 90 gaps through the 500-bps trail, selling at 90 x 0.988 = 88.92. `C2` buys ETHUSDT the same way and holds it while the price steps to 102 and then 104. The start day is `2024-03-01` for both pairs and both candidates (`warmup_period` is 1). Base costs:

* `C1`: 1 closed trade, 0 open; gross `-222.37751130`, fees `3.77562248970`, entry notional `1999.0000005`; marks at 03-01, 03-02, 03-03, 03-04 of `10000`, `10000`, `9773.84686621030`, `9773.84686621030`.
* `C2`: 0 closed trades, 1 open at the end; gross 0, fees 0; marks `10000`, `10000`, `10036.9620194995`, `10076.9220394995` (the open position is marked, not closed).
* No mark is carried forward (`carried_marks` 0). The context (buy and hold, 5,000 in each pair at the 100 open): marks 10000, 10000, 10100, 10200, annual Sharpe `22.059704`, 3 days.

| Candidate | Closed trades | Days | Sharpe (annual) | Bootstrap p5 | DSR (N = 2) | Status |
|---|---|---|---|---|---|---|
| C1 | 1 | 3 | -11.030261 | n/a (a resample has no variance) | 0.015562 | FAILED (bootstrap, dsr) |
| C2 | 0 | 3 | 22.015038 | 22.015038 | 0.698856 | EXCLUDED (below floor) |

Verdict: **FAIL at N7** (no candidate passes; `C1` meets its floor and fails both gates, `C2` is excluded as below the floor with its one position still open). `C1`'s bootstrap refuses because a resample of its three returns (0, -0.0226, 0) is all zeros, which is the case of `M5n-204`. **The sensitivities change nothing here:** all three print `flips=0` and `would_select=none`. Their figures for `C1`: `fee_0.075` gross `-222.37751130`, fees `2.8317168672750`, final mark `9774.7907718327250`; `slip_0.66` gross `-212.667226440`, fees `3.785332774560`, final mark `9783.547440785440`; `slip_0.10` gross `-202.59730140`, fees `3.79540269960`, final mark `9793.60729590040`. The `C2` marks under `fee_0.075` are `10037.461769499625` and `10077.421789499625`, and under the two slippage sensitivities they equal the base marks (a held position meets no stop).

**What each prediction does not cover, in advance.** The judge worlds do not touch the backtester and E1 touches the judge only through three returns, so E1 cannot show the bootstrap or the deflated Sharpe at a realistic length; the worlds W1 to W5 do, and they cannot show the marking. The 4h marking (`M5n-207`) and the start-day rule on a series with gaps are covered by no world here, and are the first things the survey that follows should ask about.

### The findings this section carries

See the commit message.

## 105. M5n N7: the predictions for the survey of the estimator module's closed holes and of the runner, before it is run (P149 C7, R-T, R-DQ)

An observation log, so this section only adds. P149 re-surveys the three holes of section 103 that it closes in `src/trading_bot/backtesting/sharpe_stats.py` (`m15`, `m20`, `m50`; section 103's `m36` and `m60` stay open and unclosed) and the new mark form and bootstrap guard of `05678b6`, and surveys `scripts/n7_evaluate.py` (`C4`, tests at `C5`). It runs once, after this section is committed. **No recorded bar is read and no backtest is run on recorded data**: the mutations are of two files and the tests are fixtures. Nothing here decides anything about S4.

### The method

The harness is the repository's `scripts/worktree_survey.py` with `scripts/survey_hook.py`, as in sections 91, 95, 99 and 102: a detached worktree outside the repository at the commit that carries this section, the import location of `trading_bot` and `tests` proven inside it before any result counts, an unmutated baseline predicted green, every mutation byte-exact with exactly one match, asserted both when the specs were generated and when they run, every restore shown SHA-equal, and the worktree removed afterwards. A MORE is recorded and a FEWER halts the survey; **after a FEWER is explained the survey resumes at the next mutation with its committed predictions unchanged** (charter section 22, the survey practice the owner ruled at P149). There are two specs, because the two files have different tests to run. **Spec a** (`survey_a_p149.json`, SHA-256 `0eadd4fb9d7861679a0dc6fd8801628d42bd0b21139afa639f33d25e022b96f5`) holds the 13 mutations of `sharpe_stats.py` and runs both test files, baseline predicted **231 passed**. **Spec b** (`survey_b_p149.json`, SHA-256 `32e2a519a38801e58149a66a85cceaea4884bdf8641b35cceafafc0ce9b812b2`) holds the 49 mutations of the runner and runs `tests/unit/test_n7_evaluate.py`, baseline predicted **105 passed**. Both come from the same program as the tables below, with the test list from `pytest --collect-only` at the commit before this one (231 node ids). Every anchor was asserted to match exactly once when they were generated. No test was run on a mutated tree. The survey worktree holds no `data` directory, which is why a runner mutated to skip its guard (`b12`) finds nothing to read.

**Where a prediction rested on a float, a seed or a numpy internal, the test is left out of the prediction and named below**: a test wrongly included is a FEWER and halts the survey, a test wrongly left out is a MORE and is recorded, so the cheap error is the one made on purpose.

### Totals

**62 mutations and 147 predicted failures.** The predictions come from enumerating every test that reaches the mutated point and asking of each whether its fixture can express the mutation and whether its assertion looks at what it moves (`M5h`, `M5e-079`); several were traced twice, and **`b15` was re-derived from 5 failures to 8 on a second pass** (the W5 sensitivity's `C1` has a deflated Sharpe of 0.93, between the two gates, so the flips and the report move too).

**13 mutations are predicted to fail nothing: a01, a02, b10, b11, b14, b30, b34, b35, b36, b37, b38, b48, b49.** Each is declared with its reason in the notes beneath the table. Two are the **equivalent mutants of `m15`**: the deleted line `restart[:, 0] = True` and its opposite are both no-ops, so putting either back must fail nothing, which is the proof that deleting it changed no behaviour. The other eleven are **holes in the new tests, declared in advance**: a digest line with text after its hash (`b10`), a tag looked up by bare name (`b11`), an INDETERMINATE verdict's exit code (`b14`), the check that a trade's books add up (`b30`), an incomplete run (`b34`), the buy and hold's choice of the open or the close (`b35`), the probe's midnight test on a 4h candidate (`b36`), the canonical order of the result file's keys (`b37`), the precision its floats are rounded to (`b38`), and the min and max of two pairs' or two candidates' first defined days (`b48`, `b49`). None is closed by this survey: a change to the runner after it would be a change nobody had surveyed, and the runner is frozen by digest.

**Where a prediction is most likely to be wrong, named in advance.**

* `b26` (a run of exactly the warm-up is not yet defined), 13 failures. Four are the unit tests of the start day. Nine are world E1, because moving the start to 2024-03-02 leaves `C1` with no signal, so its returns have no variance and `evaluate` refuses at the fixture of eight tests and `main` returns 1 in the ninth. If a refusal is caught somewhere I did not read, the count is lower.
* `b15` (the deflated Sharpe gate at 0.5), 8, and `b21` (only pass-to-fail is a flip), 3: both depend on the W5 sensitivity's numbers, which are the independent derivation's.
* `a03` (a batch of 100) and `b42`, `b43` (the seed, the block probability): they move every bootstrap figure of the W worlds, and **world E1's judgement test is left out of all three predictions**, because `C2`'s lower bound on three returns equals its sample Sharpe whenever fewer than 5 percent of its resamples restart, and a changed stream may change that. A MORE of one is possible.
* `b09` (the N0 line need only begin as the form does), 2: the upper-case line is matched too if the upper-cased hash happens to start with seven digits, about one run in thirty.
* `b27` (the last midnight has no mark), 7, and `b24` (no-trade candidates not given their line), 3: the second fails three tests by a crash and not an assertion.

**Classes.** The mutations expected to fail by a crash and not an assertion are `a06`, `a09`, `a10` (most of it), `b13`, `b24` and `b29`. The survey reports kill and crash separately and the score will say how many of the 147 were kills.

### Predicted failures

| Mutation | The break | Predicted failures | Tests |
|---|---|---|---|
| a01 | the deleted line is put back as it was (m15's equivalent mutant, re-surveyed) | 0 | none |
| a02 | the first position is forced NOT to restart (m15 as it was surveyed) | 0 | none |
| a03 | the resamples are drawn 100 at a time (m20, re-surveyed) | 9 | U186, U187, U1, U2, U3, U4, U5, U6, U29 |
| a04 | the microsecond is not part of midnight (m50, re-surveyed) | 1 | U123 |
| a05 | a subclass of tuple is a tuple | 1 | U136 |
| a06 | a tuple longer than two is not refused for its length | 1 | U139 |
| a07 | a subclass of datetime is a datetime | 1 | U128 |
| a08 | any zone with a zero offset is UTC | 1 | U133 |
| a09 | an int, and so a bool, is an equity | 2 | U141, U143 |
| a10 | a non-finite Decimal is accepted | 4 | U145, U146, U147, U119 |
| a11 | a zero equity is accepted | 1 | U117 |
| a12 | the no-variance guard is the standard deviation being exactly zero again (M5n-200) | 1 | U190 |
| a13 | only a naive datetime is refused for its zone | 2 | U132, U133 |
| b01 | the tag is not required | 3 | U64, U65, U93 |
| b02 | two 'N0 complete' lines are accepted | 1 | U73 |
| b03 | the N0 commit need not be an ancestor of HEAD | 1 | U76 |
| b04 | git's 'not an ancestor' is read as an ancestor | 1 | U76 |
| b05 | a digest recorded twice is accepted | 3 | U80, U81, U82 |
| b06 | a file that does not match its digest is accepted | 3 | U83, U84, U85 |
| b07 | only the first frozen file is checked | 9 | U78, U79, U81, U82, U84, U85, U87, U88, U89 |
| b08 | the charter is read from the working copy, in text mode | 2 | U74, U63 |
| b09 | the N0 line need only begin as the form does | 2 | U67, U63 |
| b10 | a digest line need only begin as the form does | 0 | none |
| b11 | the tag is looked up by its bare name, which a branch of that name would also satisfy | 0 | none |
| b12 | main does not call the guard | 2 | U94, U95 |
| b13 | an existing result file is not refused | 1 | U105 |
| b14 | an INDETERMINATE verdict exits 0 | 0 | none |
| b15 | the deflated Sharpe gate is 0.5 | 8 | U19, U1, U7, U13, U14, U27, U29, U40 |
| b16 | a floor is met only above it | 2 | U18, U101 |
| b17 | a candidate below its floor is judged on its gates alone | 3 | U5, U17, U101 |
| b18 | ties are decided by the Sharpe alone | 2 | U9, U15 |
| b19 | a tie section 7 does not break selects the first | 2 | U10, U16 |
| b20 | a sensitivity that would select nothing says n/a | 2 | U30, U102 |
| b21 | only a gate that turns from pass to fail is a flip | 3 | U27, U29, U40 |
| b22 | a gross of exactly zero is not flagged | 3 | U34, U29, U36 |
| b23 | the basis points of a zero-gross candidate are a thousandth, not a ten-thousandth | 2 | U34, U29 |
| b24 | a candidate with no trade is not given the no-trade line | 3 | U35, U104, U105 |
| b25 | net adds the fees | 4 | U32, U33, U29, U104 |
| b26 | a run of exactly the warm-up is not yet defined | 13 | U49, U50, U51, U54, U97, U98, U99, U100, U101, U102, U103, U104, U105 |
| b27 | the last midnight has no mark | 7 | U56, U57, U58, U99, U100, U101, U102 |
| b28 | a carried midnight is counted twice | 1 | U57 |
| b29 | a trade's gross omits what it cost | 9 | U97, U98, U99, U100, U101, U102, U103, U104, U105 |
| b30 | the check that a trade's books add up to the ledger's realised figure is removed | 0 | none |
| b31 | an open position is not counted | 1 | U100 |
| b32 | a sensitivity does not change the fee | 1 | U102 |
| b33 | a sensitivity does not change the stop slippage | 1 | U102 |
| b34 | an incomplete run is judged anyway | 0 | none |
| b35 | the buy and hold buys at the first day's close | 0 | none |
| b36 | the equity probe samples every bar, not only those ending at midnight | 0 | none |
| b37 | the result file's keys are not sorted | 0 | none |
| b38 | floats in the result file are rounded to six places | 0 | none |
| b39 | money is written as str, with the exponent the fill model gave it | 1 | U104 |
| b40 | C3 decides on 4h | 1 | U45 |
| b41 | the 1d floor is 31 | 1 | U41 |
| b42 | the bootstrap seed is 20261026 | 8 | U42, U1, U2, U3, U4, U5, U6, U29 |
| b43 | the expected block length is 10 days | 8 | U42, U1, U2, U3, U4, U5, U6, U29 |
| b44 | 5,000 resamples | 1 | U42 |
| b45 | the in-sample span ends a day late | 1 | U43 |
| b46 | the sensitivities are run at the base costs | 1 | U102 |
| b47 | the runner's own digest is not one of those the guard checks | 6 | U79, U82, U85, U88, U89, U47 |
| b48 | a candidate starts on the earlier pair's first defined day | 0 | none |
| b49 | the span starts on the earliest candidate's first defined day | 0 | none |

### Declared abstentions, classes and reservations

| Mutation | Declared abstentions, classes and reservations |
|---|---|
| a01 | position 0 has last = 0 whether or not it restarts, so the line changes nothing: the deletion is behaviour-preserving |
| a02 | the same reason as a01 |
| a03 | the batch-size test sets the batch itself and so passes; world E1's judgement test is left out of the prediction because C2's bootstrap bound on three returns may or may not move with the stream (a possible MORE) |
| a06 | it fails by ValueError from the unpacking, a crash; the one-item tuple is still refused |
| a09 | both fail by AttributeError (an int has no is_finite), a crash |
| a10 | NaN fails by decimal.InvalidOperation (a crash); Infinity is not refused at all; minus Infinity is refused as not positive, with a message that does not match |
| a12 | the zeros-and-0.01 test still refuses, because an all-zero resample has an exactly zero deviation |
| a13 | the +02:00 mark is then refused as not one day after the first, with a message that does not match |
| b09 | the upper-case line is matched only if the upper-cased hash happens to start with seven digits, about one run in thirty (a possible MORE) |
| b10 | no test has a digest line with text after its hash; the 64 hexadecimal characters are the end of every fixture line (a hole) |
| b11 | no test has a branch named milestone/M5m (a hole) |
| b12 | the survey worktree holds no data directory, so a main that runs finds nothing to read |
| b13 | it fails by FileExistsError from the exclusive open, a crash |
| b14 | no test drives main to an INDETERMINATE verdict (a hole) |
| b15 | W1's C2 has a deflated Sharpe of 0.50 and the W5 sensitivity's C1 has 0.93, both between the two gates |
| b16 | E1's floor is one closed trade and C1 has exactly one |
| b17 | W4's verdict still selects C2, because C1 has fewer trades |
| b24 | all three fail by decimal.InvalidOperation (0 / 0), a crash |
| b26 | the start moves to 2024-03-02, so C1 sees no signal, its returns have no variance and the evaluation refuses: the eight E1 tests fail at their fixture and main returns 1 |
| b29 | the book no longer adds up, so the evaluation refuses (RunnerError) and the E1 fixture fails, a crash |
| b30 | no fixture trade fails to add up (a hole) |
| b34 | no fixture world is incomplete (a hole) |
| b35 | world E1's first day opens and closes at 100 on both pairs, so the two cannot be told apart (a hole) |
| b36 | every E1 bar is a 1d bar and ends at midnight; no world has a 4h candidate (the 4h marking, M5n-207, is unexercised) |
| b37 | the document is built in one order in every run, so the digest is stable without sorting; nothing pins that the order is canonical (a hole) |
| b38 | the test asserts the value equals its own rounding to ten places, which a six-place rounding also satisfies (a hole) |
| b42 | world E1's judgement test is left out because C2's bound on three returns may not move with the seed (a possible MORE) |
| b43 | the same reservation as b42 about world E1 |
| b44 | every world passes its resample count explicitly or has it patched |
| b48 | both pairs of world E1 are defined on the same day (a hole) |
| b49 | both candidates of world E1 are defined on the same day (a hole) |

### Key to the test codes

| Code | Test |
|---|---|
| U1 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_every_candidate_matches_the_independent_derivation[W1]` |
| U2 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_every_candidate_matches_the_independent_derivation[W2]` |
| U3 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_every_candidate_matches_the_independent_derivation[W3]` |
| U4 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_every_candidate_matches_the_independent_derivation[W3b]` |
| U5 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_every_candidate_matches_the_independent_derivation[W4]` |
| U6 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_every_candidate_matches_the_independent_derivation[W5]` |
| U7 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_verdict_matches_the_derivation[W1]` |
| U8 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_verdict_matches_the_derivation[W2]` |
| U9 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_verdict_matches_the_derivation[W3]` |
| U10 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_verdict_matches_the_derivation[W3b]` |
| U11 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_verdict_matches_the_derivation[W4]` |
| U12 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_verdict_matches_the_derivation[W5]` |
| U13 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_w1_no_candidate_passes_so_the_run_fails_at_n7` |
| U14 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_w1_a_candidate_can_clear_the_bootstrap_and_fail_the_deflated_sharpe` |
| U15 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_w3_a_tie_in_sharpe_goes_to_the_candidate_with_more_trades` |
| U16 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_w3b_a_tie_section_7_does_not_break_is_indeterminate_and_selects_nothing` |
| U17 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_w4_a_candidate_below_its_floor_is_excluded_though_it_ties_the_winner` |
| U18 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_a_floor_is_met_at_exactly_the_floor_and_not_below` |
| U19 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_deflated_sharpe_gate_is_strictly_above_0_95` |
| U20 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_a_candidate_with_no_variance_has_no_sharpe_and_the_run_refuses` |
| U21 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_a_bootstrap_that_refuses_fails_the_gate_and_is_recorded` |
| U22 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_the_trial_count_is_the_number_of_runs` |
| U23 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_nothing_to_judge_is_refused` |
| U24 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_invalid_bootstrap_settings_are_refused_before_any_work[0.0-10]` |
| U25 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_invalid_bootstrap_settings_are_refused_before_any_work[1.5-10]` |
| U26 | `test_n7_evaluate.py`: `TestTheJudgeWorlds::test_invalid_bootstrap_settings_are_refused_before_any_work[0.05-0]` |
| U27 | `test_n7_evaluate.py`: `TestTheSensitivityThatFlipsAGateAndDecidesNothing::test_the_flips_are_listed_in_candidate_then_gate_order` |
| U28 | `test_n7_evaluate.py`: `TestTheSensitivityThatFlipsAGateAndDecidesNothing::test_the_sensitivity_would_select_another_candidate_and_the_verdict_does_not_change` |
| U29 | `test_n7_evaluate.py`: `TestTheSensitivityThatFlipsAGateAndDecidesNothing::test_the_whole_report_is_the_predicted_text_with_the_fee_telemetry_first` |
| U30 | `test_n7_evaluate.py`: `TestTheSensitivityThatFlipsAGateAndDecidesNothing::test_would_select_names_none_and_indeterminate_too` |
| U31 | `test_n7_evaluate.py`: `TestTheSensitivityThatFlipsAGateAndDecidesNothing::test_a_sensitivity_listing_other_candidates_cannot_be_compared` |
| U32 | `test_n7_evaluate.py`: `TestFeeTelemetry::test_a_positive_gross_gives_both_ratios_and_no_flag` |
| U33 | `test_n7_evaluate.py`: `TestFeeTelemetry::test_a_negative_gross_is_over_its_absolute_value_and_flagged` |
| U34 | `test_n7_evaluate.py`: `TestFeeTelemetry::test_a_zero_gross_has_no_share_but_has_basis_points_and_is_flagged` |
| U35 | `test_n7_evaluate.py`: `TestFeeTelemetry::test_no_trade_has_no_ratio_and_says_so` |
| U36 | `test_n7_evaluate.py`: `TestFeeTelemetry::test_the_report_prints_n_a_where_a_ratio_is_undefined` |
| U37 | `test_n7_evaluate.py`: `TestTheResultFile::test_the_document_is_canonical_ascii_json_ending_in_one_line_feed` |
| U38 | `test_n7_evaluate.py`: `TestTheResultFile::test_money_is_a_string_and_a_float_is_rounded_to_ten_places` |
| U39 | `test_n7_evaluate.py`: `TestTheResultFile::test_the_same_evaluation_gives_the_same_bytes_and_so_the_same_digest` |
| U40 | `test_n7_evaluate.py`: `TestTheResultFile::test_the_document_records_the_sensitivities_and_what_they_would_select` |
| U41 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_floors_are_section_5` |
| U42 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_bootstrap_is_section_6_b` |
| U43 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_span_ends_on_2024_01_01_and_the_archive_begins_on_2017_08_17` |
| U44 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_costs_are_section_3` |
| U45 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_candidates_are_the_six_of_r_dy_and_all_are_registered` |
| U46 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_every_candidate_window_holds_the_atr_the_trail_needs` |
| U47 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_frozen_paths_and_the_tag` |
| U48 | `test_n7_evaluate.py`: `TestTheConstantsAreThePreRegistrations::test_the_guard_reads_the_repository_this_script_lives_in` |
| U49 | `test_n7_evaluate.py`: `TestTheStartDay::test_a_run_of_enough_consecutive_bars_ends_at_the_first_defined_bar` |
| U50 | `test_n7_evaluate.py`: `TestTheStartDay::test_one_bar_is_defined_at_the_first_bar` |
| U51 | `test_n7_evaluate.py`: `TestTheStartDay::test_a_gap_restarts_the_count` |
| U52 | `test_n7_evaluate.py`: `TestTheStartDay::test_a_repeated_open_time_restarts_the_count` |
| U53 | `test_n7_evaluate.py`: `TestTheStartDay::test_a_series_too_short_is_never_defined` |
| U54 | `test_n7_evaluate.py`: `TestTheStartDay::test_a_4h_series_counts_four_hour_bars` |
| U55 | `test_n7_evaluate.py`: `TestTheStartDay::test_an_empty_series_is_never_defined` |
| U56 | `test_n7_evaluate.py`: `TestAssembleMarks::test_the_start_is_the_initial_balance_and_each_midnight_is_its_sample` |
| U57 | `test_n7_evaluate.py`: `TestAssembleMarks::test_a_midnight_nobody_sampled_carries_the_previous_mark_and_is_counted` |
| U58 | `test_n7_evaluate.py`: `TestAssembleMarks::test_the_marks_are_of_the_one_form_the_estimator_accepts` |
| U59 | `test_n7_evaluate.py`: `TestTheGuardAccepts::test_a_repository_that_satisfies_all_three_conditions` |
| U60 | `test_n7_evaluate.py`: `TestTheGuardAccepts::test_an_annotated_tag` |
| U61 | `test_n7_evaluate.py`: `TestTheGuardAccepts::test_a_seven_character_hash` |
| U62 | `test_n7_evaluate.py`: `TestTheGuardAccepts::test_a_commit_is_its_own_ancestor` |
| U63 | `test_n7_evaluate.py`: `TestTheGuardAccepts::test_a_charter_with_crlf_line_endings_is_not_read_as_a_match` |
| U64 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionA::test_no_tag` |
| U65 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionA::test_a_tag_of_another_name` |
| U66 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_no_line` |
| U67 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_not_exactly_the_form[trailing-text]` |
| U68 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_not_exactly_the_form[upper-case]` |
| U69 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_not_exactly_the_form[placeholder]` |
| U70 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_not_exactly_the_form[six-characters]` |
| U71 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_not_exactly_the_form[quoted]` |
| U72 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_not_exactly_the_form[lower-case-words]` |
| U73 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_two_lines` |
| U74 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_line_that_is_only_in_the_working_copy` |
| U75 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_commit_the_repository_does_not_have` |
| U76 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionB::test_a_commit_that_is_not_an_ancestor_of_head` |
| U77 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_missing_digest_line_for_each_file[docs/M5N_PREREGISTRATION.md]` |
| U78 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_missing_digest_line_for_each_file[src/trading_bot/backtesting/sharpe_stats.py]` |
| U79 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_missing_digest_line_for_each_file[scripts/n7_evaluate.py]` |
| U80 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_repeated_digest_line_for_each_file[docs/M5N_PREREGISTRATION.md]` |
| U81 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_repeated_digest_line_for_each_file[src/trading_bot/backtesting/sharpe_stats.py]` |
| U82 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_repeated_digest_line_for_each_file[scripts/n7_evaluate.py]` |
| U83 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_an_edited_file_for_each_of_the_three[docs/M5N_PREREGISTRATION.md]` |
| U84 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_an_edited_file_for_each_of_the_three[src/trading_bot/backtesting/sharpe_stats.py]` |
| U85 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_an_edited_file_for_each_of_the_three[scripts/n7_evaluate.py]` |
| U86 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_file_that_is_gone_for_each_of_the_three[docs/M5N_PREREGISTRATION.md]` |
| U87 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_file_that_is_gone_for_each_of_the_three[src/trading_bot/backtesting/sharpe_stats.py]` |
| U88 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_file_that_is_gone_for_each_of_the_three[scripts/n7_evaluate.py]` |
| U89 | `test_n7_evaluate.py`: `TestTheGuardRefusesConditionC::test_a_digest_of_the_wrong_length_is_not_a_digest_line` |
| U90 | `test_n7_evaluate.py`: `TestTheGuardFailsClosed::test_a_directory_that_is_not_a_repository` |
| U91 | `test_n7_evaluate.py`: `TestTheGuardFailsClosed::test_a_repository_without_the_charter_at_head` |
| U92 | `test_n7_evaluate.py`: `TestTheGuardFailsClosed::test_no_git_on_the_path` |
| U93 | `test_n7_evaluate.py`: `TestTheGuardFailsClosed::test_conditions_are_checked_in_the_owners_order_after_the_charter_is_read` |
| U94 | `test_n7_evaluate.py`: `TestMainRunsTheGuardFirstAndHasNoOverride::test_main_refuses_before_it_reads_a_config_or_a_store` |
| U95 | `test_n7_evaluate.py`: `TestMainRunsTheGuardFirstAndHasNoOverride::test_there_is_no_flag_and_no_environment_variable_that_skips_it` |
| U96 | `test_n7_evaluate.py`: `TestMainRunsTheGuardFirstAndHasNoOverride::test_the_only_options_are_config_data_dir_and_out` |
| U97 | `test_n7_evaluate.py`: `TestWorldE1::test_the_span_starts_on_the_first_day_every_indicator_is_defined` |
| U98 | `test_n7_evaluate.py`: `TestWorldE1::test_c1_closes_one_trade_at_the_gapped_open_and_its_books_are_the_hand_arithmetic` |
| U99 | `test_n7_evaluate.py`: `TestWorldE1::test_c1_marks_are_flat_until_the_position_is_booked_at_the_next_midnight` |
| U100 | `test_n7_evaluate.py`: `TestWorldE1::test_c2_holds_an_open_position_that_is_marked_and_not_counted_as_a_trade` |
| U101 | `test_n7_evaluate.py`: `TestWorldE1::test_the_judgement_is_the_derivations` |
| U102 | `test_n7_evaluate.py`: `TestWorldE1::test_the_sensitivities_run_at_their_own_costs_and_flip_nothing` |
| U103 | `test_n7_evaluate.py`: `TestWorldE1::test_the_context_is_the_equal_weight_buy_and_hold` |
| U104 | `test_n7_evaluate.py`: `TestWorldE1::test_the_report_puts_the_fee_telemetry_first` |
| U105 | `test_n7_evaluate.py`: `TestMainOnTheFixtureWorldWithTheGuardSatisfied::test_it_writes_one_result_file_prints_its_digest_and_refuses_a_second_run` |
| U106 | `test_sharpe_stats.py`: `TestDailySeries::test_the_marks_become_the_exact_daily_returns` |
| U107 | `test_sharpe_stats.py`: `TestDailySeries::test_the_result_is_float_one_shorter_than_the_marks` |
| U108 | `test_sharpe_stats.py`: `TestDailySeries::test_a_day_with_no_position_and_no_change_is_a_zero_return` |
| U109 | `test_sharpe_stats.py`: `TestDailySeries::test_fewer_than_two_marks_is_refused[0]` |
| U110 | `test_sharpe_stats.py`: `TestDailySeries::test_fewer_than_two_marks_is_refused[1]` |
| U111 | `test_sharpe_stats.py`: `TestDailySeries::test_a_missing_day_is_refused_not_carried_forward` |
| U112 | `test_sharpe_stats.py`: `TestDailySeries::test_a_repeated_day_is_refused` |
| U113 | `test_sharpe_stats.py`: `TestDailySeries::test_a_backward_day_is_refused` |
| U114 | `test_sharpe_stats.py`: `TestDailySeries::test_a_mark_off_midnight_is_refused` |
| U115 | `test_sharpe_stats.py`: `TestDailySeries::test_a_naive_datetime_is_refused` |
| U116 | `test_sharpe_stats.py`: `TestDailySeries::test_a_non_utc_offset_is_refused` |
| U117 | `test_sharpe_stats.py`: `TestDailySeries::test_a_non_positive_equity_is_refused[0]` |
| U118 | `test_sharpe_stats.py`: `TestDailySeries::test_a_non_positive_equity_is_refused[-5]` |
| U119 | `test_sharpe_stats.py`: `TestDailySeries::test_a_non_finite_equity_is_refused` |
| U120 | `test_sharpe_stats.py`: `TestDailySeries::test_a_float_equity_is_the_leak_the_money_rule_stops` |
| U121 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_midnight_exactly_is_accepted` |
| U122 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_one_millisecond_before_midnight_is_refused` |
| U123 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_one_microsecond_after_midnight_is_refused` |
| U124 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_any_later_instant_in_the_day_is_refused[second]` |
| U125 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_any_later_instant_in_the_day_is_refused[minute]` |
| U126 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_any_later_instant_in_the_day_is_refused[hour]` |
| U127 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_instant_that_is_not_exactly_a_datetime_is_refused[date]` |
| U128 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_instant_that_is_not_exactly_a_datetime_is_refused[timestamp]` |
| U129 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_instant_that_is_not_exactly_a_datetime_is_refused[str]` |
| U130 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_instant_that_is_not_exactly_a_datetime_is_refused[int]` |
| U131 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_zone_that_is_not_timezone_utc_is_refused[naive]` |
| U132 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_zone_that_is_not_timezone_utc_is_refused[plus-two]` |
| U133 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_zone_that_is_not_timezone_utc_is_refused[named-zero-offset]` |
| U134 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_timezone_utc_itself_is_the_accepted_zone` |
| U135 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_element_that_is_not_a_plain_tuple_is_refused[list]` |
| U136 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_element_that_is_not_a_plain_tuple_is_refused[namedtuple]` |
| U137 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_element_that_is_not_a_plain_tuple_is_refused[dict]` |
| U138 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_tuple_of_the_wrong_length_is_refused[one]` |
| U139 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_tuple_of_the_wrong_length_is_refused[three]` |
| U140 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_equity_that_is_not_exactly_a_decimal_is_refused[float]` |
| U141 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_equity_that_is_not_exactly_a_decimal_is_refused[int]` |
| U142 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_equity_that_is_not_exactly_a_decimal_is_refused[str]` |
| U143 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_equity_that_is_not_exactly_a_decimal_is_refused[bool]` |
| U144 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_an_equity_that_is_not_exactly_a_decimal_is_refused[numpy-float64]` |
| U145 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_decimal_that_is_not_finite_is_refused[equity0]` |
| U146 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_decimal_that_is_not_finite_is_refused[equity1]` |
| U147 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_decimal_that_is_not_finite_is_refused[equity2]` |
| U148 | `test_sharpe_stats.py`: `TestTheOneAcceptedFormOfMark::test_a_refusal_names_the_mark_that_broke_the_form` |
| U149 | `test_sharpe_stats.py`: `TestParityWithMetrics::test_the_f2_marks_give_the_same_annualised_sharpe_both_ways` |
| U150 | `test_sharpe_stats.py`: `TestParityWithMetrics::test_the_daily_returns_agree_too` |
| U151 | `test_sharpe_stats.py`: `TestSharpe::test_the_known_small_series_by_hand` |
| U152 | `test_sharpe_stats.py`: `TestSharpe::test_the_annualiser_is_the_square_root_of_365` |
| U153 | `test_sharpe_stats.py`: `TestSharpe::test_the_standard_deviation_is_the_sample_one` |
| U154 | `test_sharpe_stats.py`: `TestSharpe::test_a_constant_series_refuses_rather_than_divides[0.01]` |
| U155 | `test_sharpe_stats.py`: `TestSharpe::test_a_constant_series_refuses_rather_than_divides[0.0]` |
| U156 | `test_sharpe_stats.py`: `TestSharpe::test_a_constant_series_refuses_rather_than_divides[0.1]` |
| U157 | `test_sharpe_stats.py`: `TestSharpe::test_a_constant_series_refuses_rather_than_divides[-0.003]` |
| U158 | `test_sharpe_stats.py`: `TestSharpe::test_a_constant_series_whose_float_mean_is_inexact_still_refuses` |
| U159 | `test_sharpe_stats.py`: `TestSharpe::test_fewer_than_two_returns_refuses[returns0]` |
| U160 | `test_sharpe_stats.py`: `TestSharpe::test_fewer_than_two_returns_refuses[returns1]` |
| U161 | `test_sharpe_stats.py`: `TestSharpe::test_a_non_finite_return_refuses` |
| U162 | `test_sharpe_stats.py`: `TestSharpe::test_a_two_dimensional_input_refuses` |
| U163 | `test_sharpe_stats.py`: `TestMoments::test_skewness_and_non_excess_kurtosis_by_hand` |
| U164 | `test_sharpe_stats.py`: `TestMoments::test_a_symmetric_series_has_no_skew` |
| U165 | `test_sharpe_stats.py`: `TestMoments::test_a_two_point_series_has_kurtosis_one` |
| U166 | `test_sharpe_stats.py`: `TestMoments::test_a_constant_series_refuses` |
| U167 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_the_same_inputs_and_seed_give_identical_bounds` |
| U168 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_different_seed_gives_different_bounds` |
| U169 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_the_result_does_not_depend_on_the_input_container` |
| U170 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_the_bounds_order_2_5th_below_5th_below_the_mean[positive]` |
| U171 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_the_bounds_order_2_5th_below_5th_below_the_mean[negative]` |
| U172 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_the_bounds_order_2_5th_below_5th_below_the_mean[runs]` |
| U173 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_the_bootstrap_mean_has_the_sign_of_the_sample_sharpe` |
| U174 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_vanishing_restart_probability_rotates_the_whole_series` |
| U175 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_block_length_of_one_matches_an_independent_iid_bootstrap` |
| U176 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_blocks_widen_the_distribution_of_an_autocorrelated_series` |
| U177 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[0.0]` |
| U178 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[-0.1]` |
| U179 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[1.5]` |
| U180 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_restart_probability_outside_the_unit_interval_refuses[nan]` |
| U181 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_zero_resamples_refuses` |
| U182 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_one_return_series_refuses` |
| U183 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_constant_series_refuses` |
| U184 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_resample_with_no_variance_refuses` |
| U185 | `test_sharpe_stats.py`: `TestStationaryBootstrap::test_a_float_seed_refuses` |
| U186 | `test_sharpe_stats.py`: `TestTheBootstrapStreamIsPinned::test_g1_six_hundred_resamples_across_three_batches` |
| U187 | `test_sharpe_stats.py`: `TestTheBootstrapStreamIsPinned::test_g2_the_pre_registered_ten_thousand_resamples` |
| U188 | `test_sharpe_stats.py`: `TestTheBootstrapStreamIsPinned::test_the_batch_size_is_part_of_the_value` |
| U189 | `test_sharpe_stats.py`: `TestTheBootstrapStreamIsPinned::test_the_sample_sharpe_the_fixture_has` |
| U190 | `test_sharpe_stats.py`: `TestTheBootstrapStreamIsPinned::test_a_constant_resample_of_non_zero_returns_refuses` |
| U191 | `test_sharpe_stats.py`: `TestTheBootstrapStreamIsPinned::test_numpy_does_give_a_non_zero_std_for_three_equal_floats` |
| U192 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_one_trial_has_no_deflation_so_it_is_the_probabilistic_sharpe_ratio` |
| U193 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_one_trial_ignores_what_the_single_sharpe_list_says_beyond_its_length` |
| U194 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_the_expected_maximum_for_six_trials_by_hand` |
| U195 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_the_expected_maximum_for_two_trials_by_hand` |
| U196 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_the_euler_mascheroni_constant` |
| U197 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_six_trials_with_skew_and_fat_tails_by_hand` |
| U198 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_two_trials_by_hand` |
| U199 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_it_is_strictly_increasing_in_the_sharpe_for_a_symmetric_case` |
| U200 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_more_trials_deflate_the_same_sharpe` |
| U201 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_trial_count_below_one_refuses[0]` |
| U202 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_trial_count_below_one_refuses[-1]` |
| U203 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_sharpe_list_not_matching_n_refuses` |
| U204 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_fewer_than_two_observations_refuses` |
| U205 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_non_positive_variance_term_refuses` |
| U206 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_non_finite_input_refuses[sr]` |
| U207 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_non_finite_input_refuses[skew]` |
| U208 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_non_finite_input_refuses[kurt]` |
| U209 | `test_sharpe_stats.py`: `TestDeflatedSharpe::test_a_non_finite_input_refuses[srs]` |
| U210 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_net_share_per_trade_and_basis_points_by_hand` |
| U211 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_the_numerators_and_denominators_are_reported_beside_each_ratio` |
| U212 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_the_share_is_over_the_absolute_gross` |
| U213 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_zero_gross_refuses` |
| U214 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_zero_fees_are_a_zero_share` |
| U215 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_fewer_than_one_trade_refuses[0]` |
| U216 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_fewer_than_one_trade_refuses[-3]` |
| U217 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_non_positive_notional_refuses[notional0]` |
| U218 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_non_positive_notional_refuses[notional1]` |
| U219 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_negative_fees_refuse` |
| U220 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_float_figure_is_refused[gross]` |
| U221 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_float_figure_is_refused[fees]` |
| U222 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_float_figure_is_refused[notional]` |
| U223 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_non_int_trade_count_is_refused` |
| U224 | `test_sharpe_stats.py`: `TestFeeTelemetry::test_a_boolean_trade_count_is_refused` |
| U225 | `test_sharpe_stats.py`: `TestBuyAndHold::test_equal_weight_marks_by_hand` |
| U226 | `test_sharpe_stats.py`: `TestBuyAndHold::test_its_daily_returns_by_hand` |
| U227 | `test_sharpe_stats.py`: `TestBuyAndHold::test_series_of_different_length_refuse` |
| U228 | `test_sharpe_stats.py`: `TestBuyAndHold::test_series_marked_at_different_instants_refuse` |
| U229 | `test_sharpe_stats.py`: `TestBuyAndHold::test_a_non_positive_close_refuses` |
| U230 | `test_sharpe_stats.py`: `TestBuyAndHold::test_a_non_positive_initial_refuses` |
| U231 | `test_sharpe_stats.py`: `TestBuyAndHold::test_a_float_close_is_refused` |

### The findings this section carries

See the commit message. In short: eleven holes in the new tests are declared before they are measured, and the m15 equivalence is to be demonstrated by putting the line back.

## 106. M5n N7: the scored result of the survey of the estimator module and the N7 runner (P149 C9, R-T)

An observation log, so this section only adds. The survey section 105 predicted ran in a detached worktree outside the repository (`scratch\p149\wt_survey`) at `5cb0d55`, the commit that carries section 105, with the repository's `scripts/worktree_survey.py` and `scripts/survey_hook.py`, the import location of `trading_bot` and `tests` printed inside the worktree before any result, an unmutated baseline each time (231 passed for spec a, 105 for spec b), every restore shown SHA-equal, and `git worktree list` showing the main worktree only after each. Nothing here decides anything about S4. No recorded bar was read and no backtest was run on recorded data.

### The runs, and why there are eight of them

**The machine was out of committed memory for most of the survey, and for a reason this project caused.** MEASURED at the time: `Committed Bytes` 56,983 MB against a `Commit Limit` of 57,238 MB, free physical memory 1.1 GB. The cause was **821 `git fsmonitor--daemon` processes**, about 30 GB of commit, found by listing the processes: Git for Windows switches `core.fsmonitor` on in its system config (`C:/Program Files/Git/etc/gitconfig`), and every `add` or `commit` in one of the throwaway repositories the guard tests build started a daemon that outlived the repository and the test, so each gate run since `b5deb42` left about sixty. Killed (headroom rose to 15 GB), and fixed in the tests by `-c core.fsmonitor=false` (`M5n-223`, with the commit that carries it). The surveyed tests are the committed ones, which lack the flag, so runs `b1` to `b4` set `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false` in the survey's environment. **Results taken while the memory was exhausted are not results**: a pytest subprocess died silently, raised `MemoryError` while formatting a traceback, or could not start `git`. Those are recorded as such and the mutations re-run.

| Run | Spec | UTC | Exit | What it gave |
|---|---|---|---|---|
| `a1` | `survey_a_p149.json` (SHA-256 `0eadd4fb9d7861679a0dc6fd8801628d42bd0b21139afa639f33d25e022b96f5`) | `2026-10-25T16:40:58Z` to `2026-10-25T16:46:21Z` | 1 | `a01` to `a06` and `a09` valid. `a07` and `a08` showed MOREs made of crashes in the guard tests' own `git` calls (`CalledProcessError`, `OSError`, 29 of them for `a08`): **environmental, not reach**, and re-run. HALTED at `a10`: pytest exited 3, so no verdict. |
| `a2` (first attempt) | `survey_a2_p149.json` | `2026-10-25T17:51:05Z` to `17:51:26Z` | 2 | No result: the unmutated baseline did not run (exit 2). Kept as `survey_a2_failed_out.txt`. |
| `a2` | `survey_a2_p149.json` (`a07`, `a08`, `a10` to `a13`; SHA-256 `4322d84ea5a7d912ca92983742ab7ffe2c34bb0cf8d07e06bc367885125c686a`) | `2026-10-25T17:55:09Z` to `2026-10-25T17:56:31Z` | 1 | `a07` MATCH. `a08` MORE, again one `git` crash in the main test. HALTED at `a10` with **FEWER, 0 of 4 observed**: explained below. |
| `a3` | `survey_a3_p149.json` (`a08`, `a10` to `a13`; SHA-256 `9848a79bc543b41d0584596750247276513788d1b9b24281970409435d7b5d1e`) | `2026-10-25T18:33:49Z` to `2026-10-25T18:44:41Z` | 0 | `a08`, `a10`, `a11`, `a12` MATCH; `a13` MORE. |
| `b1` | `survey_b_p149.json` (SHA-256 `32e2a519a38801e58149a66a85cceaea4884bdf8641b35cceafafc0ce9b812b2`) | `2026-10-25T19:05:24Z` to `2026-10-25T19:14:24Z` | 1 | `b01` to `b25`; HALTED at `b26`, FEWER. |
| `b2` | `survey_b2_p149.json` (`b27` to `b29`; SHA-256 `b7b99d12b46729e95eb3716b6db8b446dcda6cc35700f5bf3b222f18d7c01f7f`) | `2026-10-25T19:15:27Z` to `2026-10-25T19:16:44Z` | 1 | `b27`, `b28` MATCH; HALTED at `b29`, FEWER. |
| `b3` | `survey_b3_p149.json` (`b30` to `b49`; SHA-256 `98e454e773aa61bc2354171d13736ab5ee841f474e05ce39c45b1fef49d15cab`) | `2026-10-25T19:16:46Z` to `2026-10-25T19:22:46Z` | 1 | `b30` to `b46`; HALTED at `b47`, FEWER. |
| `b4` | `survey_b4_p149.json` (`b48`, `b49`; SHA-256 `372816df124c28608dc62cdc13199488b83df1baa6ea669dfdee86caf8f106d9`) | `2026-10-25T19:23:32Z` to `2026-10-25T19:24:30Z` | 0 | `b48`, `b49` MATCH. |

Every spec after the first holds entries of the committed one byte for byte, with no prediction changed (the charter's survey practice, section 22); each FEWER stays on record beside its explanation. Standard error is empty for every run but the failed `a2` attempt, whose one line says the unmutated baseline is not green.

### Result

**62 mutations scored: 55 MATCH, 4 MORE (`a13`, `b15`, `b19`, `b43`), 3 FEWER (`b26`, `b29`, `b47`).** 147 failures were predicted and 133 observed; **124 were kills and 9 were crashes** (`AttributeError` 2, `FileExistsError` 1, `ValueError` 1, `decimal.InvalidOperation` 5). **All thirteen mutations predicted to fail nothing failed nothing** (`a01`, `a02`, `b10`, `b11`, `b14`, `b30`, `b34`, `b35`, `b36`, `b37`, `b38`, `b48`, `b49`), so the eleven holes of section 105 are confirmed, and the two equivalent mutants `a01` and `a02` prove that deleting `restart[:, 0] = True` changed no behaviour.

**The three holes of section 103 that P149 closed are closed.** `a03` (the batch of 100, `m20`) is killed by the two golden-value tests, the six judge-world tests that compare a bootstrap bound and the W5 report test (nine failures, predicted nine); `a04` (the microsecond, `m50`) is killed by the 00:00:00.000001 test alone; `a01` and `a02` (`m15`) fail nothing.

### The three FEWERs, each explained

* **`b26` (13 predicted, 5 observed) and `b29` (9 predicted, 1 observed): the eight tests of world E1 were not counted, and the reason is the harness and not the mutation.** Both mutations make `evaluate` raise before the E1 world is built, so the eight tests that share its module-scoped fixture **error at setup**, and `worktree_survey.py` keeps only failures `when == "call"` (line 324). The raw pytest output shows the errors; the survey does not count them as kills. The prediction counted a setup error as a failure and the harness does not (`M5n-226`). The call-phase tests of both mutations failed as predicted.
* **`b47` (6 predicted, 2 observed): the guard tests were parametrised over the runner's own `FROZEN_PATHS`.** With the third path removed from that tuple the four tests that would have noticed it were never generated, so they could not fail. The constants test and the wrong-length test did (`M5n-227`). **The tests are now parametrised over their own literal list of the three paths**, in the commit that carries the fsmonitor fix; that change is unsurveyed.
* **`a10` (4 predicted, 0 observed), in run `a2`: environmental, and reproduced by hand.** The raw output ends in a `MemoryError` raised inside pytest's traceback formatter. Reproduced by hand in a throwaway worktree with the mutation applied: `NaN` raises `decimal.InvalidOperation`, `Infinity` is accepted, `-Infinity` is refused as not positive, and the four tests fail, which is the prediction. Re-run in `a3` with memory available: MATCH, 4 of 4 (`M5n-228`).

### The four MOREs

All four are tests that use a world the prediction did not trace. `a13` (only a naive datetime refused for its zone) also fails the older `test_a_non_utc_offset_is_refused`. `b15` (the gate at 0.5) and `b19` (a tie selects the first) each also fail `test_would_select_names_none_and_indeterminate_too`, which builds its verdicts from worlds W1 and W3b. `b43` (the block probability 1/10) fails three more tests than predicted: W1's test that its `C2` clears the bootstrap, and the two tests that list the W5 sensitivity's flips, because a different block length turns over a bootstrap gate there as well as moving the bounds. A MORE is a reach error and the extra kills are real coverage (`M5n-229`).

### Tests the survey could and could not see

231 tests ran. **75 were killed by an assertion, 6 fail only by crash, and 150 failed under none of these 62 mutations.** That last figure is for THIS survey's mutations and is not a whole-suite figure: the survey mutated the mark form, the bootstrap guard and the runner, and the tests of the fee-telemetry arithmetic of `sharpe_stats.py`, the moments, the Sharpe and the deflated Sharpe ratio were surveyed at section 103. By file, tests that failed under no mutation here: `test_sharpe_stats.py` 109 of 126, `test_n7_evaluate.py` 41 of 105.

### Scored table

| Mutation | The break | Predicted | Observed | Verdict | Kills | Crashes | Run |
|---|---|---|---|---|---|---|---|
| a01 | the deleted line is put back as it was (m15's equivalent mutant, re-surveyed) | 0 | 0 | MATCH | 0 | 0 | a1 |
| a02 | the first position is forced NOT to restart (m15 as it was surveyed) | 0 | 0 | MATCH | 0 | 0 | a1 |
| a03 | the resamples are drawn 100 at a time (m20, re-surveyed) | 9 | 9 | MATCH | 9 | 0 | a1 |
| a04 | the microsecond is not part of midnight (m50, re-surveyed) | 1 | 1 | MATCH | 1 | 0 | a1 |
| a05 | a subclass of tuple is a tuple | 1 | 1 | MATCH | 1 | 0 | a1 |
| a06 | a tuple longer than two is not refused for its length | 1 | 1 | MATCH | 0 | 1 | a1 |
| a07 | a subclass of datetime is a datetime | 1 | 1 | MATCH | 1 | 0 | a2 |
| a08 | any zone with a zero offset is UTC | 1 | 1 | MATCH | 1 | 0 | a3 |
| a09 | an int, and so a bool, is an equity | 2 | 2 | MATCH | 0 | 2 | a1 |
| a10 | a non-finite Decimal is accepted | 4 | 4 | MATCH | 2 | 2 | a3 |
| a11 | a zero equity is accepted | 1 | 1 | MATCH | 1 | 0 | a3 |
| a12 | the no-variance guard is the standard deviation being exactly zero again (M5n-200) | 1 | 1 | MATCH | 1 | 0 | a3 |
| a13 | only a naive datetime is refused for its zone | 2 | 3 | MORE | 3 | 0 | a3 |
| b01 | the tag is not required | 3 | 3 | MATCH | 3 | 0 | b1 |
| b02 | two 'N0 complete' lines are accepted | 1 | 1 | MATCH | 1 | 0 | b1 |
| b03 | the N0 commit need not be an ancestor of HEAD | 1 | 1 | MATCH | 1 | 0 | b1 |
| b04 | git's 'not an ancestor' is read as an ancestor | 1 | 1 | MATCH | 1 | 0 | b1 |
| b05 | a digest recorded twice is accepted | 3 | 3 | MATCH | 3 | 0 | b1 |
| b06 | a file that does not match its digest is accepted | 3 | 3 | MATCH | 3 | 0 | b1 |
| b07 | only the first frozen file is checked | 9 | 9 | MATCH | 9 | 0 | b1 |
| b08 | the charter is read from the working copy, in text mode | 2 | 2 | MATCH | 2 | 0 | b1 |
| b09 | the N0 line need only begin as the form does | 2 | 2 | MATCH | 2 | 0 | b1 |
| b10 | a digest line need only begin as the form does | 0 | 0 | MATCH | 0 | 0 | b1 |
| b11 | the tag is looked up by its bare name, which a branch of that name would also satisfy | 0 | 0 | MATCH | 0 | 0 | b1 |
| b12 | main does not call the guard | 2 | 2 | MATCH | 2 | 0 | b1 |
| b13 | an existing result file is not refused | 1 | 1 | MATCH | 0 | 1 | b1 |
| b14 | an INDETERMINATE verdict exits 0 | 0 | 0 | MATCH | 0 | 0 | b1 |
| b15 | the deflated Sharpe gate is 0.5 | 8 | 9 | MORE | 9 | 0 | b1 |
| b16 | a floor is met only above it | 2 | 2 | MATCH | 2 | 0 | b1 |
| b17 | a candidate below its floor is judged on its gates alone | 3 | 3 | MATCH | 3 | 0 | b1 |
| b18 | ties are decided by the Sharpe alone | 2 | 2 | MATCH | 2 | 0 | b1 |
| b19 | a tie section 7 does not break selects the first | 2 | 3 | MORE | 3 | 0 | b1 |
| b20 | a sensitivity that would select nothing says n/a | 2 | 2 | MATCH | 2 | 0 | b1 |
| b21 | only a gate that turns from pass to fail is a flip | 3 | 3 | MATCH | 3 | 0 | b1 |
| b22 | a gross of exactly zero is not flagged | 3 | 3 | MATCH | 3 | 0 | b1 |
| b23 | the basis points of a zero-gross candidate are a thousandth, not a ten-thousandth | 2 | 2 | MATCH | 2 | 0 | b1 |
| b24 | a candidate with no trade is not given the no-trade line | 3 | 3 | MATCH | 0 | 3 | b1 |
| b25 | net adds the fees | 4 | 4 | MATCH | 4 | 0 | b1 |
| b26 | a run of exactly the warm-up is not yet defined | 13 | 5 | FEWER | 5 | 0 | b1 |
| b27 | the last midnight has no mark | 7 | 7 | MATCH | 7 | 0 | b2 |
| b28 | a carried midnight is counted twice | 1 | 1 | MATCH | 1 | 0 | b2 |
| b29 | a trade's gross omits what it cost | 9 | 1 | FEWER | 1 | 0 | b2 |
| b30 | the check that a trade's books add up to the ledger's realised figure is removed | 0 | 0 | MATCH | 0 | 0 | b3 |
| b31 | an open position is not counted | 1 | 1 | MATCH | 1 | 0 | b3 |
| b32 | a sensitivity does not change the fee | 1 | 1 | MATCH | 1 | 0 | b3 |
| b33 | a sensitivity does not change the stop slippage | 1 | 1 | MATCH | 1 | 0 | b3 |
| b34 | an incomplete run is judged anyway | 0 | 0 | MATCH | 0 | 0 | b3 |
| b35 | the buy and hold buys at the first day's close | 0 | 0 | MATCH | 0 | 0 | b3 |
| b36 | the equity probe samples every bar, not only those ending at midnight | 0 | 0 | MATCH | 0 | 0 | b3 |
| b37 | the result file's keys are not sorted | 0 | 0 | MATCH | 0 | 0 | b3 |
| b38 | floats in the result file are rounded to six places | 0 | 0 | MATCH | 0 | 0 | b3 |
| b39 | money is written as str, with the exponent the fill model gave it | 1 | 1 | MATCH | 1 | 0 | b3 |
| b40 | C3 decides on 4h | 1 | 1 | MATCH | 1 | 0 | b3 |
| b41 | the 1d floor is 31 | 1 | 1 | MATCH | 1 | 0 | b3 |
| b42 | the bootstrap seed is 20261026 | 8 | 8 | MATCH | 8 | 0 | b3 |
| b43 | the expected block length is 10 days | 8 | 11 | MORE | 11 | 0 | b3 |
| b44 | 5,000 resamples | 1 | 1 | MATCH | 1 | 0 | b3 |
| b45 | the in-sample span ends a day late | 1 | 1 | MATCH | 1 | 0 | b3 |
| b46 | the sensitivities are run at the base costs | 1 | 1 | MATCH | 1 | 0 | b3 |
| b47 | the runner's own digest is not one of those the guard checks | 6 | 2 | FEWER | 2 | 0 | b3 |
| b48 | a candidate starts on the earlier pair's first defined day | 0 | 0 | MATCH | 0 | 0 | b4 |
| b49 | the span starts on the earliest candidate's first defined day | 0 | 0 | MATCH | 0 | 0 | b4 |

### The findings this section carries

See the commit message.

## 107. M5n P156: the classification of the eleven open runner holes, and the plan that closes the VERDICT ones with its predictions, before any code (P156 C2, R-T, R-DQ, R-EG)

An observation log, so this section only adds. This is section 107 of `docs/RUN_LEDGER_M5N.md`, the first written under R-EG (charter section 27), and a citation of it names this file. Under R-DQ clause (1) it is committed BEFORE any test or code is drafted. Read-only: the sources read were this ledger's sections 105 and 106, `scripts/n7_evaluate.py` at `8c5d9ec` (unchanged since its own commit `57588ee`, and so since section 105's survey at `5cb0d55`) and the test files that cover it. No recorded bar was read and nothing was run on recorded data. **Nothing here decides anything about S4.**

### 1. Halts, checked first

| Halt | Check | Observed |
|---|---|---|
| not on `main`, tree not clean, HEAD not `8c5d9ec` | `git branch --show-current`, `git status --porcelain`, `git rev-parse` | `main`, empty, `8c5d9ec` (then `28e8a77` after C1, the charter commit) |
| the pre-registration's digest differs | `sha256sum` | equal `e6187480...d45e`; `sharpe_stats.py` `2b55991c...dda82` and `n7_evaluate.py` `1f307de6...dcfff` equal their charter section 23 lines |
| a command reads recorded bars or runs on recorded data | every command in the plan | none: the survey below mutates source files in a throwaway worktree and runs unit tests on generated fixtures |
| free committed memory is below 20 percent before a survey spec starts | `Win32_OperatingSystem.FreeVirtualMemory` over `TotalVirtualMemorySize` (the commit limit) | **46.9 percent free** at the time of writing (16,288 of 34,710 MB), free physical 2,160 MB; measured again before each spec |
| stray `git fsmonitor--daemon` processes | `Get-CimInstance Win32_Process` on `git.exe` | two, 8 MB each, one per working repository (`core.fsmonitor` is `true` in the system config): not the leak of section 106. The survey sets `core.fsmonitor=false` for every git subprocess through `GIT_CONFIG_COUNT`, as the charter's survey-resources rule requires |

### 2. The classification

VERDICT means the hole could change a gate result, the selection, a verdict label or the exit code; REPORT means it could change context or telemetry only. The eleven are the mutations section 106 scored as failing nothing, less the two equivalent mutants (`a01`, `a02`). Sites are `scripts/n7_evaluate.py` lines at `8c5d9ec`.

| Hole | The break (section 105) | Site | Class | Reason |
|---|---|---|---|---|
| `b10` | a digest line need only begin as the form does | `_DIGEST_LINE.fullmatch`, line 233 | **VERDICT** | a charter line the guard must refuse (text after the hash) would be accepted, or counted as a second digest, so a run proceeds where the guard exits 2; P156's re-freeze depends on a superseded line not being counted |
| `b11` | the tag is looked up by its bare name | `refs/tags/` lookup, line 212 | **VERDICT** | a branch named `milestone/M5m` would satisfy condition (a), so a run proceeds where the guard exits 2 |
| `b14` | an INDETERMINATE verdict exits 0 | `main`, line 970 | **VERDICT** | the exit code of a tie section 7 does not break; the docstring fixes it at 1 |
| `b30` | the check that a trade's books add up is removed | `trade_books`, line 789 | **VERDICT** | borderline, classed VERDICT: the books feed only the telemetry, but the check compares them with the ledger's own realised figure, which equity (and so every mark) is built from; without it a run whose two sources disagree issues a verdict instead of exiting 1 |
| `b34` | an incomplete run is judged anyway | `run_candidate`, line 828 | **VERDICT** | an ERROR record or an unserved bar means the marks are not the run's; the gates read the marks |
| `b36` | the equity probe samples every bar | `_MidnightProbe`, line 751 | **VERDICT** | the **4h midnight marking**: for a 4h candidate (C4, C5) the mark of each date would be the equity after the date's last bar, about 20 hours after midnight, so every daily return, and so every gate, moves; no test has a 4h candidate |
| `b48` | a candidate starts on the earlier pair's first defined day | `max(days)`, line 731 | **VERDICT** | the span start, hence which days enter every return series |
| `b49` | the span starts on the earliest candidate's first defined day | `max(first.values())`, line 884 | **VERDICT** | the span start for all six: C3's SMA(200) is the latest to be defined (201 bars against 22 for C1, C4 and C5, section 82), so the earliest-day reading starts the span months early and adds days of zero return for C3 and every other candidate to every return series |
| `b35` | the buy and hold buys at the first day's close | `bars[0].open`, line 868 | REPORT | section 10's context, "never a criterion": it is printed beside the verdict and read by no gate |
| `b37` | the result file's keys are not sorted | `canonical_json`, line 675 | REPORT | the order of keys in a file written after the judgement; the content and every gate are unchanged |
| `b38` | floats in the result file are rounded to six places | `_rounded`, line 568 | REPORT | the gates are decided on unrounded values before the document is built, and the file records each gate's boolean |

**Eight VERDICT, three REPORT.** The 4h midnight marking (`b36`) and the INDETERMINATE exit code (`b14`) are both VERDICT.

### 3. What each VERDICT hole needs, and the sites already do it

At every one of the eight sites the code already does what the runner's docstring and the pre-registration say: `fullmatch`, `refs/tags/`, `return 1` for INDETERMINATE, the books check, the `complete` check, the midnight filter, `max` twice. **So each hole is closed by a test, and no change to `scripts/n7_evaluate.py` or `sharpe_stats.py` is expected** (REASONED from reading the sites; a test that finds otherwise changes the code under the re-freeze rule, and this plan then changes). INDETERMINATE and "no verdict" both exit 1 by the docstring ("1 a run was incomplete or the verdict is INDETERMINATE"); that is a documented overlap, not a hole, and the tests below pin both.

### 4. The closing plan and its predictions (provisional until the tests exist, M5e-051)

All tests go in `tests/unit/test_n7_evaluate.py`; the 4h world needs `tests/unit/d1_world.py` to build a 1d series beside a 4h one (the context reads the 1d archive), a backward-compatible extension. "T" numbers name the tests.

| T | Test (class, name) | Closes | How it fails under the mutation |
|---|---|---|---|
| T1 | `TestTheDigestLineIsTheWholeLine::test_a_digest_line_with_text_after_its_hash_is_not_a_digest_line[path]` (3) | b10 | the line with text after its hash is accepted as the path's digest, so the guard does not refuse `digest_line_missing` |
| T2 | `::test_a_superseded_line_with_text_after_its_hash_is_not_a_second_digest[path]` (3) | b10 | a clean line plus the same line with " (superseded)" counts twice, so the guard refuses `digest_line_duplicated` where it must accept |
| T3 | `::test_a_superseded_line_with_a_prefix_is_not_a_digest_line[path]` (3) | b10b | the convention P156 uses (`superseded: ` before the form): a `search` finds it and counts twice |
| T4 | `TestTheTagIsATag::test_a_branch_of_the_tags_name_is_not_the_tag` | b11 | a branch `milestone/M5m` and no tag: the bare name resolves, so the guard does not refuse `tag_missing` |
| T6 | `TestTheExitCodes::test_indeterminate_exits_1_and_selects_nothing` | b14 | `main` over an INDETERMINATE judgement (world W3b) returns 0 |
| T7 | `::test_a_selected_verdict_exits_0` | none (pins the other side) | passes under every mutation |
| T8 | `::test_a_fail_at_n7_exits_0` | b14b | a FAIL (world W1) returns 1 |
| T9 | `::test_a_run_with_no_verdict_exits_1_and_writes_nothing` | none (pins the overlap) | a `RunnerError` from `evaluate` returns 1, prints "no verdict" and writes no file |
| T10 | `TestTradeBooks::test_a_trade_whose_books_do_not_add_up_is_refused` | b30 | a trade whose `realised` is one unit off its gross less fees is summed instead of refused |
| T11 | `::test_trades_that_add_up_are_summed` | none | passes under every mutation |
| T12 | `TestAnIncompleteRun::test_an_incomplete_run_is_refused_not_judged` | b34 | the world with a strategy whose signals forget the trail (`BrokenD1`) returns marks instead of raising `RunnerError` |
| T13 | `TestTheMidnightProbe::test_only_a_bar_that_ends_at_midnight_is_sampled` | b36 | a stub system and a day of six 4h bars: the five bars that do not end at midnight are sampled |
| T14 | `::test_a_4h_candidate_is_marked_at_the_bar_that_closes_at_midnight` | b36 | a real 4h world (world E2): the marks must be collinear with the prices at the 4h closes ending at midnight; they are not when each date takes its last bar's equity |
| T15 | `TestTheStartDay::test_a_candidate_starts_on_the_later_pairs_first_defined_day` | b48 | BTCUSDT's 1d series begins on day 0 and ETHUSDT's on day 2; the earlier day is returned |
| T16a | `::test_the_span_starts_on_the_latest_candidates_first_defined_day` | b49 | `evaluate` over two candidates whose first defined days differ (stubbed seams) reports the earlier day as the window start |
| T16b | `::test_every_run_is_handed_that_start` | b49 | the `start_date` handed to every `run_candidate` is the earlier day |

**The survey after the code** (section 108 re-derives these at the green baseline and is committed before it runs): the eight VERDICT mutations plus `b10b` and `b14b`, and P149 C8's re-parametrisation of the guard tests, which section 106 left unsurveyed: removing each of the three `FROZEN_PATHS` entries in turn (`b47a`, `b47b`, and `b47` as section 105 had it).

| Mutation | The break | Predicted failures (provisional) |
|---|---|---|
| `b10` | `_DIGEST_LINE.fullmatch` becomes `.match` | **6**: T1 and T2, three paths each |
| `b10b` | `.fullmatch` becomes `.search` | **9**: T1, T2 and T3, three paths each |
| `b11` | the tag lookup drops `refs/tags/` | **1**: T4 |
| `b14` | `main` returns 0 whatever the outcome | **1**: T6. T7 and T8 expect 0 and still get 0; T9's exit 1 is returned from the error branch, above the line mutated |
| `b14b` | `main` returns 1 unless SELECTED | **2**: T8 and `test_it_writes_one_result_file_prints_its_digest_and_refuses_a_second_run` (E1 ends in FAIL and asserts 0) |
| `b30` | the books check is removed | **1**: T10 |
| `b34` | the `complete` check is removed | **1**: T12 |
| `b36` | the midnight filter is removed | **2**: T13, T14 |
| `b48` | `max(days)` becomes `min(days)` | **1**: T15 |
| `b49` | `max(first.values())` becomes `min(first.values())` | **2**: T16a, T16b |
| `b47a` | the pre-registration is removed from `FROZEN_PATHS` | **5**: the four per-file guard tests for it, and the constants test |
| `b47b` | `sharpe_stats.py` is removed | **5**: the same four for it, and the constants test |
| `b47` | `n7_evaluate.py` is removed | **6**: the four per-file tests, the wrong-length test, and the constants test (section 105 predicted these six and saw two, because the tests were generated from the mutated tuple) |

**Declared abstentions.** Under `b10` T3 passes (a prefix stops a `match`) and the older wrong-length test passes (`abc123` is not 64 hex digits, whichever pattern reads it). Under `b14` T7, T8 and T9 pass. Every 1d test passes under `b36`, because every 1d bar ends at midnight. World E1 passes under `b48` and `b49`, because both of its pairs and both of its candidates are defined on the same day. T11 and T7 pass under every mutation, by design. No test is expected to crash.

### 5. What stays open (REPORT), listed

`b35` (the buy and hold buys at the first day's close or the open: no world separates them), `b37` (the result file's key order: nothing pins that it is sorted) and `b38` (the precision of the floats in the result file: the test compares a value with its own ten-place rounding, which a six-place rounding also satisfies). All three are left open as the owner's P156 instruction says, and carried.

### 6. The re-freeze and the direct digest check

No change to a frozen file is planned, so the re-freeze of charter section 27's rule is **not due unless a test changes a frozen file**. The guard's digest check is not a function of its own: it is the last loop of `check_n0_guard`, after the tag and the N0 line. Calling it directly therefore takes either a refactor of the frozen runner (not warranted by any hole) or a throwaway clone whose charter carries a synthetic N0 line, which reaches the real digest loop in the real code. The verification uses the clone, and also reads the charter's digest lines at `HEAD` with the guard's own `_DIGEST_LINE` pattern.

### 7. The findings this section carries

See the commit message.

## 108. M5n P156: the closing tests exist, and the binding predictions for the survey of the VERDICT mutations and the guard's re-parametrisation, before it is run (P156 C7, R-T, R-DQ, R-EG)

An observation log, so this section only adds; a citation names its file (R-EG). Section 107 planned these tests and was committed first (`2df308c`); they are `50a114d`, 25 tests that pass on the unmutated runner, and under M5e-051 a prediction made before the tests existed is invalidated by writing them, so this section re-derives every count at the green baseline and **binds** them. The survey runs only after this section is committed. No recorded bar is read and nothing runs on recorded data: the survey mutates `scripts/n7_evaluate.py` in a throwaway worktree and runs `tests/unit/test_n7_evaluate.py` on generated fixtures. **Nothing here decides anything about S4.**

### 1. Halts, checked before this section was written

| Halt | Check | Observed |
|---|---|---|
| not on `main`, tree not clean, HEAD not the commit the prompt names | `git branch --show-current`, `git status --porcelain`, `git rev-parse` | `main`, empty, `5854581` (the prompt named `c49c6b7`; `50a114d` and `5854581` are P156's own two commits since) |
| a frozen file differs | `sha256sum` | equal: the pre-registration `e6187480...d45e`, `sharpe_stats.py` `2b55991c...dda82`, `n7_evaluate.py` `1f307de6...dcfff` |
| a closure needs a change to `n7_evaluate.py` or `sharpe_stats.py` | the green baseline of `50a114d` | **none**: all 25 tests pass on the unchanged runner, the 4h world among them |
| free committed memory below 20 percent before a survey spec starts | `Win32_OperatingSystem` | 39.3 percent free (13,635 of 34,710 MB) before the daemons below were stopped, 41.4 percent after; measured again before each spec |
| stray `git fsmonitor--daemon` processes | `Get-CimInstance Win32_Process` | **18**, 142.8 MB of working set together, left since the two daemons seen at the start of P156 (by its two full gate runs and its runs of the test file; which of them is not established); stopped. Not section 106's 30 GB, but the same kind of leak (see section 4) |
| the survey's git environment | the shell | `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false` for every command that starts a survey, so the worktree and every test repository run with `core.fsmonitor=false` |

### 2. What changed from section 107's provisional counts

Two, each from reading the tests as written. `b48` is 2, not 1, because T15 runs once for each pair being the late one (the owner's ruling allows this correction). The three `FROZEN_PATHS` removals are 6, 6 and 7, not 5, 5 and 6, because T1 (a digest line with text after its hash) also reaches the tuple: it drops the path's clean line, so a guard that no longer checks that path accepts the charter and the test's `pytest.raises` is unmet. Every other count stands.

### 3. The binding predictions

Short ids are `Class::test[param]`. "T" numbers are section 107's. A kill here is an assertion or an unmet `pytest.raises`; no crash is predicted.

| Mutation | The break (`scripts/n7_evaluate.py`) | Predicted failures | Which |
|---|---|---|---|
| `b10` | `_DIGEST_LINE.fullmatch(line)` becomes `.match(line)` | **6** | T1 for each of the three paths, T2 for each of the three |
| `b10b` | `.fullmatch` becomes `.search` | **9** | T1, T2 and T3 for each of the three paths |
| `b11` | `refs/tags/{MILESTONE_TAG}` becomes `{MILESTONE_TAG}` | **1** | T4 |
| `b14` | `main` ends `return 0` | **1** | T6 |
| `b14b` | `main` ends `return 0 if ... == "SELECTED" else 1` | **2** | T8, and the E1 main test (a FAIL asserted to exit 0) |
| `b30` | the books check (two lines) is removed | **1** | T10 |
| `b34` | the `complete` check (four lines) is removed | **1** | T12 |
| `b36` | the midnight filter (two lines) is removed | **2** | T13, T14 |
| `b48` | `max(days)` becomes `min(days)` | **2** | T15 for the BTCUSDT-late and the ETHUSDT-late case |
| `b49` | `max(first.values())` becomes `min(first.values())` | **2** | T16a, T16b |
| `b47a` | the pre-registration is removed from `FROZEN_PATHS` | **6** | the four per-file guard tests for it (missing, repeated, edited, gone), T1 for it, and the constants test |
| `b47b` | `sharpe_stats.py` is removed | **6** | the same six for it |
| `b47` | `n7_evaluate.py` is removed | **7** | the four per-file tests, T1, the wrong-length test and the constants test for it |

**46 failures are predicted over the 13 mutations** (6 + 9 + 1 + 1 + 2 + 1 + 1 + 2 + 2 + 2 + 6 + 6 + 7).

**Declared abstentions.** Under `b10` T3 passes (a prefix stops a `match`) and the older wrong-length test passes (`abc123` is not 64 hexadecimal digits whichever pattern reads it). Under `b10b` the wrong-length test passes. Under `b11` `test_no_tag`, `test_a_tag_of_another_name` and the order test pass, because no branch of that name exists in them. Under `b14` T7 and T8 still get exit 0 and T9's exit 1 comes from the error branch above the line. Under `b14b` the INDETERMINATE and SELECTED exits are unchanged. Under `b30` the sums test and every E1 and E2 test pass: their books add up. Under `b36` the 1d probe test and every 1d world pass, because every 1d bar ends at midnight. Under `b48` and `b49` worlds E1 and E2 pass, because their pairs and candidates are defined on the same day. Under the three `FROZEN_PATHS` removals the per-file tests of the paths that stay pass, and T2 and T3 pass (acceptance is the outcome either way).

**Where a prediction is most likely to be wrong, named in advance.** `b34`: T12 is a kill only if the BrokenD1 run, with its `complete` check gone, returns a run; if the mutated run raised anything else T12 would crash, not be killed. `b14b`: the E1 main test is counted because E1 ends in FAIL and the test asserts exit 0; if its judgement were SELECTED the count would be 1. `b36`: T14's line fits the marks exactly because the position's quantity is constant, and a rounding in the fill model would break an exact equality in the unmutated tree, which the green baseline excludes.

### 4. The two specs, and the leak

`survey_a_p156.json` (SHA-256 `628e6156cee4c362d0f3b1b895034c0f73295657a762c93a6b26acfdd4469c56`): `b10`, `b10b`, `b11`, `b47a`, `b47b`, `b47`. `survey_b_p156.json` (SHA-256 `d0bdae785fb3ed2a8e337726aec5d8ee5e3d33c82ee548871a3199be9f0f01ed`): `b14`, `b14b`, `b30`, `b34`, `b36`, `b48`, `b49`. Both are built by `scratch\p156\build_specs.py` (the session scratchpad), which asserts every anchor matches the committed runner exactly once, and both run `tests/unit/test_n7_evaluate.py` only.

**The leak is still there.** Two test modules start git repositories without `core.fsmonitor=false`: `tests/unit/test_s6_rehearsal.py` and `tests/unit/test_worktree_survey.py` (a grep for `fsmonitor` finds 0 mentions in each, against 2 in `test_n7_evaluate.py` and 4 in `test_provenance.py`). They are the likely source of the 18 daemons (not shown: the daemons carry no repository name). They are outside this prompt's scope and are reported, not changed; the daemons are small here, and are stopped after each gate run.

### 5. The findings this section carries

See the commit message.

## 109. M5n P156: the scored result of the survey of the VERDICT mutations and the guard's re-parametrisation, and the direct digest check (P156 C8, R-T)

An observation log, so this section only adds; a citation names its file (R-EG). The survey section 108 predicted ran in two detached worktrees outside the repository, one per spec, at `40f1c6c` (the commit that carries section 108), with the repository's `scripts/worktree_survey.py`. Each run printed where `trading_bot` and `tests` were imported from before any result counted (inside its worktree), took an unmutated baseline (**130 passed, no failure**, both times), applied each mutation byte-exact with exactly one match, restored it with the SHA shown equal, showed every copied file intact, and left `git worktree list` with the main worktree only. The environment carried `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false`. Both exited 0 and standard error was empty for both (0 bytes). No recorded bar was read and nothing ran on recorded data. **Nothing here decides anything about S4.**

### 1. The runs

| Run | Spec | Mutations | Exit | Memory before |
|---|---|---|---|---|
| `a` | `survey_a_p156.json` (SHA-256 `628e6156cee4c362d0f3b1b895034c0f73295657a762c93a6b26acfdd4469c56`) | `b10`, `b10b`, `b11`, `b47a`, `b47b`, `b47` | 0 | 40.2 percent free committed (13,964 of 34,710 MB); one git daemon |
| `b` | `survey_b_p156.json` (SHA-256 `d0bdae785fb3ed2a8e337726aec5d8ee5e3d33c82ee548871a3199be9f0f01ed`) | `b14`, `b14b`, `b30`, `b34`, `b36`, `b48`, `b49` | 0 | 40.3 percent free (13,980 MB) after stopping the leftover daemons; none running |

Neither run needed a second attempt. Both specs are the ones section 108 recorded, unedited.

### 2. The result

**13 mutations scored: 13 MATCH, 0 MORE, 0 FEWER. 46 failures were predicted and 46 observed, 46 kills and 0 crashes.** Every declared abstention held (the tests named as passing passed).

| Mutation | The break | Predicted | Observed | Verdict | Kills | Crashes |
|---|---|---|---|---|---|---|
| `b10` | a digest line need only begin as the form does (`match`) | 6 | 6 | MATCH | 6 | 0 |
| `b10b` | the form is found anywhere in a line (`search`) | 9 | 9 | MATCH | 9 | 0 |
| `b11` | the tag is looked up by its bare name | 1 | 1 | MATCH | 1 | 0 |
| `b14` | `main` always returns 0 | 1 | 1 | MATCH | 1 | 0 |
| `b14b` | `main` returns 1 unless SELECTED | 2 | 2 | MATCH | 2 | 0 |
| `b30` | the books check is removed | 1 | 1 | MATCH | 1 | 0 |
| `b34` | the incomplete-run check is removed | 1 | 1 | MATCH | 1 | 0 |
| `b36` | the equity probe samples every bar | 2 | 2 | MATCH | 2 | 0 |
| `b48` | a candidate starts on the earlier pair's first defined day | 2 | 2 | MATCH | 2 | 0 |
| `b49` | the span starts on the earliest candidate's first defined day | 2 | 2 | MATCH | 2 | 0 |
| `b47a` | the pre-registration leaves `FROZEN_PATHS` | 6 | 6 | MATCH | 6 | 0 |
| `b47b` | `sharpe_stats.py` leaves `FROZEN_PATHS` | 6 | 6 | MATCH | 6 | 0 |
| `b47` | `n7_evaluate.py` leaves `FROZEN_PATHS` | 7 | 7 | MATCH | 7 | 0 |

**What this shows.** Each of the eight VERDICT holes of section 105 is closed: a mutation that was predicted to fail nothing in section 105 now fails the test planned for it, and only that. The 4h midnight marking (`b36`) is killed by a stub test and by the whole chain on a real 4h world; the INDETERMINATE exit code (`b14`) by a test through `main`; the guard's digest-line pattern (`b10`, `b10b`) in the two ways P156's `superseded:` convention depends on. **P149 C8's re-parametrisation, which section 106 left unsurveyed, is now surveyed:** with any one of the three paths removed from `FROZEN_PATHS` the four per-file guard tests for that path are generated and fail, six or seven failures where section 105 had seen two for the third path. The two counts that differed from section 107 (`b48` 2, the removals 6, 6 and 7) were the ones section 108 re-derived and bound, and they held. No prediction was wrong in either direction, which is the case section 96 warns is not evidence the tests are good: the predictions were made after the tests were written (M5e-051), so the agreement is a check of the tracing and of the mutations' reach, not of the tests' independence.

### 3. The three REPORT holes, still open

`b35`, `b37` and `b38` (section 107, section 5) are untouched and carried: no test separates the buy and hold's open from its close, pins the result file's key order, or distinguishes a six-place rounding from a ten-place one. They change context and the shape of a file written after the judgement, not a gate, the selection, a label or an exit code.

### 4. The direct digest check, and why there is no re-freeze

**No frozen file changed.** `scripts/n7_evaluate.py`, `src/trading_bot/backtesting/sharpe_stats.py` and `docs/M5N_PREREGISTRATION.md` hash at `HEAD` to the three values of the charter's section 23, so the re-freeze of charter section 27's rule was not due, no digest line was superseded, and the charter's section 23 holds the only guard-shaped digest lines, exactly three.

**The check was run directly.** `scratch\p156\direct_digest_check.py` (the session scratchpad) did two things with no recorded bar and no venue call. It read `HEAD`'s charter with `git show` and matched it with the runner's own `_DIGEST_LINE` pattern: each of the three paths has **one** line, equal to the SHA-256 of that file at `HEAD`; the charter holds **3** guard-shaped lines and **0** N0-shaped lines. It then cloned the repository to a path outside it, committed a synthetic N0 line in the clone only, and called the runner's real `check_n0_guard` on the clone, which reached its digest loop: **accepted** (the tag resolved to `a31c81b`, one N0 line, three digest lines, three file hashes). A second commit repeating one digest line made it **refuse `digest_line_duplicated`**, so the check is live. The clone held no junction and was removed.

### 5. The findings this section carries

See the commit message.

## 110. M5n P157: N0 recorded, and the predictions for N7's one run, made before it exists (P157 C2, R-T)

An observation log, so this section only adds; a citation names its file (R-EG). It is committed BEFORE `scripts/n7_evaluate.py` runs, and no M5n return has been computed or read: the predictions below are made from the pre-registration, the charter and the strategies' source, never from a bar of the in-sample span.

### 1. State at the prediction

| Fact | Value | How it was checked |
|---|---|---|
| Branch, HEAD, status | `main`, clean; HEAD `29ef8f1e40918d2a3bfd2f44ee9ef15e07f4c98c` (the commit that writes the N0 line; its parent is `e0d1f8d`) | `git branch --show-current`, `git status --short` empty before this section |
| `docs/M5N_PREREGISTRATION.md` SHA-256 | `e6187480b6af7da1349ab280a6bb74f7219d4a7cded4217574e6247d5f54d45e` | equal to the prompt's and to the charter's digest line |
| `src/trading_bot/backtesting/sharpe_stats.py` SHA-256 | `2b55991c0207fc2938e6f03b33e0b9cfec3754d486af7002d5adee4ee88dda82` | same |
| `scripts/n7_evaluate.py` SHA-256 | `1f307de67f5aebd7af39a3d8fb5cd22a78d9fa671cfdf5353b894beacbadcfff` | same |
| The N0 line | `N0 complete: S4 result recorded at ddf3593199a463cd00c200b731c94b254ada1001`, one line, in charter section 28 | `ddf3593` resolves to those 40 characters and is an ancestor of HEAD |
| The guard, called end to end | `check_n0_guard(Path("."))` on `29ef8f1`: **ACCEPTED** | the runner's own function, no mock; it reads the charter from `HEAD`, resolves `refs/tags/milestone/M5m`, finds the one N0 line and the three digest lines and compares each with the file |

The owner's N0 text, recorded in the charter and quoted here so this section is self-contained: *"N0 recorded: R-DT clause 3 ends; M5n returns may now be computed and read. The re-freeze window is closed: no frozen M5n file changes from here. A run of N7 counts when its result file is written; a crash before that is not a run and may be repeated, and is recorded."*

### 2. The architect's predictions, verbatim

> (1) C3 is excluded by its in-sample floor (12 trades against 30). (2) No candidate passes all three in-sample gates; probability about 0.65. (3) If one passes, it is a 1d Donchian, C1 or C2. (4) Both 4h candidates, C4 and C5, have negative in-sample annualised net daily Sharpe at 1.20 percent stop slippage. (5) At least one 1d candidate has positive in-sample annualised net daily Sharpe.

Read against the runner so each can be scored without a judgement call: "all three in-sample gates" are the floor, the bootstrap bound (the 5th percentile of the annualised net daily Sharpe above 0) and the deflated Sharpe (above 0.95 at N = 6); the "12 trades" and the sign of a Sharpe are the in-sample figures of the result file; (3) is scored only if (2) fails; (4) needs a negative figure for both C4 and C5, so one non-negative figure falsifies it; (5) is scored on any of C1, C2, C3, C6 having a positive annualised net daily Sharpe, whatever its floor verdict.

### 3. My own predictions (the assistant's, labelled as mine; not the architect's)

All of them are REASONED from the source and the pre-registration, or from general knowledge of how such strategies behave on two large crypto pairs; none rests on a figure I have seen of this span.

| ID | Prediction | Confidence | Scored by |
|---|---|---|---|
| A1 | **The common evaluation start is 2018-03-05 (UTC).** C3 binds: its `window_bars` is `SLOW + 1` = 201 (`strategies/m5n/sma_cross.py`), so the first defined 1d bar is the 201st of an unbroken run; the archive's 1d files begin at `2017-08` for both pairs (file names only, no bar read) and the first Binance spot 1d bar is 2017-08-17, so 201 bars end on 2018-03-05. Every other candidate starts earlier (C6 92 bars, C2 57, C1 22; the 4h candidates 22 and 20 bars of four hours). A missing day in either pair's early 1d series restarts the run (R-DZ), so the date can only move **later**, never earlier. | 0.55 for the exact date; 0.95 that it is not before 2018-03-05; 0.9 that it is C3's | `common_start` in the result file, and which candidate's `first_defined` equals it |
| A2 | **C3 is below its floor of 30 trades.** Agrees with the architect's (1); I add that the count lies between 8 and 16. | 0.9 (below floor); 0.7 (8 to 16) | C3's in-sample trade count |
| A3 | **No candidate is SELECTED; the verdict is "no pass" and the exit code is 0.** Slightly above the architect's 0.65, because the DSR at N = 6 and a 5th-percentile bound on roughly 5.8 years of daily returns are two further gates behind the floor, and a strategy with a 1.2 percent stop slippage is penalised on every stopped trade. | 0.72 | the selection field and the exit code |
| A4 | **If one passes, it is C2 (`donchian_1d_55`) rather than C1,** the longer window having fewer, larger trades and so a smaller fee and slippage share. Weaker than the architect's (3), which allows either. | 0.5 given a pass | the selected label |
| A5 | **C4 and C5 both have a negative annualised net daily Sharpe,** as the architect says, and I hold the stronger statement that at least one of them has a **fee share above 40 percent of gross** or a non-positive gross (the `gross<=0` flag). | 0.75 for both negative; 0.7 for the fee share | the two Sharpe figures; the fee telemetry |
| A6 | **At least two of C1, C2, C6 have a positive annualised net daily Sharpe,** stronger than the architect's (5). Trend following on BTC and ETH from March 2018 to December 2023 includes the 2020 to 2021 run and the 2018 to 2019 drawdown. | 0.7 for two or more; 0.9 for at least one | the 1d Sharpe figures |
| A7 | **No candidate has a bootstrap 5th-percentile bound above 0 together with a DSR above 0.95,** which is A3 stated by gate. I expect the bootstrap bound to be the weaker gate (negative for every candidate whose annualised net daily Sharpe is below about 0.8) and the DSR to be the binding one for any candidate that clears it. | 0.75 | the two gate verdicts per candidate |
| A8 | **Buy and hold over the common span has a positive annualised daily Sharpe for the BTC and ETH context,** as a context figure only; no gate reads it. | 0.9 | the buy-and-hold block |
| A9 | **The sensitivities (fee 0.075, stop slippage 0.66 and 0.10 percent) change no gate verdict that the base run settled,** each a figure and not a verdict (R-DY). If a sensitivity flips a candidate's gate it is recorded and changes nothing. | 0.7 | the sensitivity block |
| A10 | **The run exits 0 and finishes in under 20 minutes of wall time** (six candidates, each a replay of about 5.8 years of stored 1d or 4h bars through the unchanged provider and engine, plus 10,000 bootstrap resamples each). An INDETERMINATE (exit 1) is possible only on a tie the selection rule does not break and I give it 0.03; a refusal (exit 2) after the guard accepted I give 0.03; a crash before the result file exists, 0.05. | 0.8 for exit 0 and under 20 minutes | the exit code and the wall time |

**Three places a prediction is most likely wrong, named in advance.** A1's date, if the early archive has a missing 1d bar for either pair (it can only move later, and I did not look: reading the early bars to check would be a read of the in-sample span before the predictions are committed). A3 and A7, because they rest on how the DSR at N = 6 compares with the bootstrap bound, which depends on the skew and kurtosis of the daily returns I have not seen. A10's wall time, which depends on the replay's speed on this machine and which the stray `git fsmonitor` daemons and the free memory can move; the memory is measured before the run and recorded.

### 4. What the run will be, fixed here before it starts

One run: `scripts/n7_evaluate.py --out data/n7/n7_result_P157.json` with the project venv's interpreter (`.venv\Scripts\python.exe`), standard output to `data/n7/n7_stdout_P157.txt` and standard error to `data/n7/n7_stderr_P157.txt` by redirection to files, never a pipe, under `GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=false`, after the free committed memory is measured at 20 percent or more and the stray `git fsmonitor--daemon` processes are stopped. `data/*` is gitignored, so the three files are local; section 111 records each one's SHA-256 and states the result from the file by script, and no figure is typed by hand. If the process dies before the result file exists, that is not a run (N0's text): it is repeated on the same frozen bytes and the crash is recorded here in section 111 with its exit code and its standard error. A second run after a result file exists is refused by the runner (`result_exists`).

### 5. The findings this section carries

See the commit message.
