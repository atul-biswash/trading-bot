# S4 correction P128: the latch

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO). It supersedes NOTHING in the pre-registration: its tests A, B and C, its stop rule, its window, its interruptions and its closed list of causes stand exactly as written, and R-DK below says so in the owner's words. What it adds is a diagnosis of one state the pre-registration did not name, two exploratory analyses that sit beside the primary result, and a definition (R-DM) that only the second of them applies.** This file is never edited after its commit; a correction to it is a new file that says what it supersedes.

The run started at `T0` = `2026-10-10T06:05:20Z` (pid 16076's first line, as `scripts/s4_daily.py` prints it). This file is committed while the run's stop, `M` = `2026-11-01T00:00:00Z`, is still in the future and **before any S4 backtest figure exists**. That ordering is the point of it: R-DL makes any variant proposed after S4 backtest figures exist ineligible.

## 1. The rulings, verbatim

The project owner's rulings of M5m P128. Their text is quoted exactly as the owner wrote it.

> **R-DK**  The pre-registered S4 comparison runs at stop exactly as frozen. Its three figures and verdicts are reported first, with the latch named as the diagnosed cause of any failure. A latch-caused failure is recorded as FAIL (latch-caused), not NOT MEASURED. Nothing below replaces or reinterprets it.
>
> **R-DL**  Exactly two exploratory analyses, reported beside the primary as figures only, with no pass/fail wording. Neither can change R-DK's recorded outcome.
> E1: frozen s4_compare.py with --window-end 2026-10-21T13:09:00Z, on the same backtest and live logs as the primary.
> E2: the P129 wrapper applying R-DM over [W, M).
> Any other variant proposed after S4 backtest figures exist is ineligible but counted (R-CM).
>
> **R-DM**  Latch interval, derived from log lines only. Start = timestamp of the first reconciliation_untrusted line of an unbroken run later followed by at least one close_halted or committed_risk_unknown refusal. End = timestamp of the last log line of the process in which the run began. If that process has not stopped by capture end, the interval is open and closed at M. Exclusion geometry equals the frozen downtime exclusion, applied to both sides. It applies to every episode in [W, M), including 2026-10-13. It is unioned with the frozen down_intervals, and overlaps are merged.
>
> **R-DN**  Restart after a latch is operator-discretionary and recorded under R-BN. No ruling is conditioned on whether it occurs. The venue sale and release_position stay outside the ledger by design.

**What each means in practice.** R-DK: the primary is `scripts/s4_compare.py` run unmodified over `[W, M)` as the pre-registration says, and a failure of test B that the latch caused is a FAIL, labelled `(latch-caused)`. R-DL: E1 is the same frozen script on the same two inputs with only `--window-end 2026-10-21T13:09:00Z`, the entry bar that opened at `13:09:00Z` falling outside because the window is half-open; E2 is a new script, written in P129, not here. R-CM is S7's rule that a variant seen in the reserved window is ineligible for selection and still counted in S7's variant denominator; R-DL cites it for the same treatment of any S4 variant proposed late.

### The owner's answers to the three questions this session had to ask

1. **The file's name** (a halt: R-AO names none): `docs/S4_CORRECTION_P128.md`. No earlier correction file exists, so this is the first.
2. **The reading of R-DM's undefined terms**, selected by the owner from three offered: *"A run is consecutive reconciliation_untrusted passes for one symbol with no pass between them that reports that symbol's position active; 'followed by' means a refusal logged while that run is still unbroken."* It is a reading of R-DM and does not change its text.
3. **The cause of the `2026-10-23T08:05:33Z` stop:** the prompt's field was an unfilled placeholder and the owner expressed no preference when asked. **NOT SUPPLIED**; `docs/RUN_LEDGER.md` section 66 records it so and the owner may add it.

## 2. How the reading was implemented, and where it needed a rule the owner did not state

A `reconciliation_pass` line names no symbol: it gives `positions=N` and `states="active=1,unknown=1"`. So "a pass that reports that symbol's position active" cannot be read off a line. With two positions open the reconciler defers one under the call cap, and a pass that handled only the other symbol (`positions=1 states="active=1"`) says nothing about the deferred one.

**The first implementation broke a symbol's run at every pass that carried no untrusted line for it, and that is wrong:** it split the one 42-hour BTCUSDT latch into nine overlapping episodes, because ETHUSDT-only passes broke BTCUSDT's run (`scratch\p128\measure.py`, SHA-256 `ccc208ec2e480d4b8bea76168dc59d5c354588d0d5aee8c3aa8bfdf72ded706a`; output `measure_out.txt`, SHA-256 `2d95a2e6d3c682ad74aa96ee234e7d2feb34beb4c9b9b179338544d4f731fb2b`).

**The second implementation, whose figures this file reports, uses a COVERAGE RULE that is the executing session's and is for the owner to ratify before P129 builds on it:** a pass is taken to have reported a symbol's position active only when the pass covered every open position (`positions` equal to the number of positions open, counted from `order_placed` opening and `close_booked` or `exit_booked` closing, in file order) and carried no untrusted line for that symbol. Where the count disagrees with `positions=N` the pass proves nothing and does not break a run. The count agrees with `positions=N` on 7,223 of the capture's 8,257 passes, is below it on 526 (presumably positions restored at boot, which the count does not see) and above it on 508 (passes that covered fewer positions than were open), so the rule breaks a run less often than the literal reading would, never more. (`scratch\p128\measure2.py`, SHA-256 `bca989083897e285264801e5a48f19f45d2a1a8d29783addb66a808b053d78e9`; output `measure2_out.txt`, SHA-256 `4e8c3952f968c5fc155469fb24a562a8dbb216c600666749d0974d1627ff0d4b`.)

## 3. The measurements

Every figure is from the frozen capture `F:\trading bot\scratch\s4\2026-10-23\184839Z-capture.log`, 3,874,511 bytes, SHA-256 `c8fc92ad14babb4569e080b273ca3bd338208d58acb2a21394d076155419a0dc`, read-only, by the scripts named above. Each carries its mark.

### 3.1 The episodes under R-DM, MEASURED

**Three episodes satisfy R-DM, not two.** R-DM ends an interval at the last line of the process, so the third is by far the longest per hour of evidence.

| Episode | Start (first untrusted line of the run) | End (the process's last line) | Duration | Run broken at | Untrusted passes | `committed_risk_unknown` BUY refusals | `close_halted` lines (refused CLOSEs) | Last latch evidence | Interval after it |
|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT, 2026-10-11, pid 16076 | `2026-10-11T16:00:01Z` | `2026-10-12T04:17:43Z` (clean stop) | 12 h 17 m 42 s | `2026-10-11T16:54:00Z` | 46 | 1 | 0 (0) | `16:51:01Z` | **11 h 26 m 42 s** |
| ETHUSDT, 2026-10-13, pid 22304 (order 1867449, list 71012) | `2026-10-13T02:59:02Z` | `2026-10-13T06:54:01Z` (no clean stop; successors in the capture) | 3 h 54 m 59 s | never | 171 | 2 | 0 (0) | `06:54:01Z` | 0 |
| BTCUSDT, 2026-10-21, pid 14600 (order 5431129, list 183218) | `2026-10-21T13:11:00Z` | `2026-10-23T08:05:33Z` (clean stop; no successor) | 1 d 18 h 54 m 33 s = 42.91 h | never | 1,704 | 36 | 66 (33) | `08:04:02Z` | 1 m 31 s |

No interval is open: pid 14600 logged `engine_stopped clean_shutdown=True` at `08:05:33Z`, so nothing is closed at `M`.

**The 2026-10-11 episode qualifies, and the prompt predicted it would not.** It is not a stop leg that expired partly: it is the 2026-10-11 BTCUSDT `CLOSE` sell that executed partly (U10's second case). From `16:00:01Z` the position's passes alternate between `states="diverged=1"` for BTCUSDT and `active=1` for ETHUSDT, BTCUSDT is named untrusted on every pass that covers it, one `committed_risk_unknown` BUY is refused at `16:21:00Z` inside the run, and the first pass that provably covered both positions and reported both active is `16:54:00Z` (`states="active=2"`). The run is therefore unbroken across the refusal and R-DM's start condition is met. **R-DM's end rule then carries the interval to the process's last line, `04:17:43Z` the next day: 11 h 26 m 42 s after the last evidence of the latch.** Under R-DM only, 8 live entries (7 BTCUSDT, 1 ETHUSDT, signal bars from `2026-10-11T16:52:59Z` to `2026-10-12T02:15:59Z`) fall in that tail and are excluded on the live side, and the same window excludes the backtest's entries on the other.

Excluded live entries, of the 164 in `[W, M)`: **3 by the frozen rule, 8 by R-DM alone, 11 by the union**, leaving 161, 156 and 153. The 161 the frozen rule keeps therefore includes 8 entries that open inside an R-DM interval.

### 3.2 The frozen rule and the trailing stop, MEASURED

`down_intervals` returns 7 intervals on this capture, the last ending `2026-10-20T09:38:01Z`, and `scripts/s4_explore.py`'s corrected rule returns 4, the same as on the 2026-10-22 capture (output `explore_out.txt`, SHA-256 `5d261aadccf28578d20c969f865db4ba55604ae454ac5d2069b81ae3130f70b4`, window `[2026-10-11, 2026-11-01)`). **Neither gives the span from `2026-10-23T08:05:33Z` to the capture's end an interval**, because both build intervals only from `pairwise` of consecutive processes and pid 14600 has no successor in the capture. A stopped last process, like a latched live one, is invisible to the frozen rule until a successor boots; R-DM's own end rule is what covers the latch up to the stop. Overlap of each R-DM interval with the frozen ones is **0**: the 2026-10-11 and 2026-10-13 intervals end at exactly the instant a frozen interval begins (`2026-10-12T04:17:43Z` and `2026-10-13T06:54:01Z`), so the union is their sum.

### 3.3 Protective-leg exits, MEASURED

Since `T0`: `exit_booked` 12, `boot_exit_booked` 0, and two stop legs that expired partly (orders 1867449 and 5431129): **2 of 14**. In `[W, M)`: 11 booked (10 stop-loss, 1 take-profit) and the same 2, so **2 of 13**; the twelfth `exit_booked` is the 2026-10-10 stop that filled 12.87% beyond its trigger (`M5m-302`), before `W`. No booking has occurred since `2026-10-21T19:20:05Z`, so these counts are the same on the 2026-10-22 capture.

### 3.4 Entries, MEASURED

164 live entries open in `[W, M)`, all before `2026-10-21T13:09:00Z`. The span `[W, 2026-10-21T13:11:00Z)` is 10.549 days; the frozen downtime inside it is 2 d 2 h 18 m 21 s, leaving 8.453 days of uptime. **Entries per day: 15.55 of span, 19.40 of uptime**; the five days wholly outside the frozen intervals before the latch day (`10-11`, `10-16` to `10-19`) booked 18, 21, 19, 20 and 17, mean 19.0.

### 3.5 How test B defines its denominator, MEASURED from the frozen source

`scripts/s4_compare.py`, `main`: `live, backtest, excluded = exclude_downtime(live_in, backtest_in, intervals, timeframes)` then `figures = figures_of(live, backtest, matching)`. `figures_of`: `live_count, backtest_count = len(live), len(backtest)`; `difference = abs(backtest_count - live_count)`; `count_difference_pct = Decimal(difference) / Decimal(live_count) * _HUNDRED`. **The denominator is the number of live entries KEPT after the downtime exclusion**, not the booked count and not `N_bt`, which is the pre-registration's `abs(N_bt - N_live) <= 0.10 * N_live`.

### 3.6 B's arithmetic, REASONED

The latch interval is 1.788 days. The backtester keeps trading through it and the live bot does not, so each entry the backtest takes in it is a surplus that no live entry matches. With the surplus `s`, B holds only if `s <= 0.10 * N_live`, that is **`N_live >= 10 s`**.

| Rate used | Surplus `s` over 1.788 d | `N_live` needed |
|---|---|---|
| the whole span's 15.55 a day | **27.8** | **278** |
| the uptime's 19.40 a day | **34.7** | **347** |

Two consequences. **The surplus depends on which rate it is taken at, and the span's rate under-sizes it by about 7 entries (20%)** because the span includes the frozen outages, which the backtest has none of. **The figure "break-even about 250 live entries" is `9 s`, which is B with `N_bt` in the denominator; B divides by `N_live`, so the break-even is `10 s`.** And B is not lost on these numbers. On the primary (the frozen rule) the live side keeps 161 entries so far, and reaching 278 to 347 takes 117 to 186 more kept entries, which is 6.0 to 9.6 days of uptime at 19.4 a day; on E2's union it keeps 153 and needs 125 to 194, 6.4 to 10.0 days. Against that stand the 8 days from `2026-10-24` to `M`, if the bot ran from the start of them. B is therefore reachable only at the lower surplus and with no further outage or latch. The two shorter episodes add a few more surplus entries on the primary (3 BUYs were refused in them), and the backtest's own count in the unaffected days differs from live's by some amount of its own, which spends part of the 10%. None of this is known until a backtest exists.

### 3.7 Log growth while latched, MEASURED

The capture grew by 529,661 bytes between the 2026-10-22 freeze (last line `2026-10-22T19:04:01Z`) and the stop (`2026-10-23T08:05:33Z`), 13.026 hours: **40,663 bytes an hour, 0.976 MB a day** (0.931 MiB). The same rate holds across the earlier pair, 2026-10-22 `04:57:48Z` to `17:14:00Z`: 501,180 bytes in 12.27 hours, 0.98 MB a day.
## 4. Predictions against the measurements

The predictions are in `docs/RUN_LEDGER.md` section 65 (commit `7f63985`), written before the capture was parsed for episodes. **They were not blind**: P127 had read the 2026-10-22 capture for the episodes and the source of `down_intervals`.

| | The prompt's prediction | The executing session's | Observed |
|---|---|---|---|
| a | exactly two episodes | two or three, two most likely (about 55%) | **three.** The prompt's is wrong; the session's range held and its most likely value did not |
| b | the 2026-10-11 lines do not satisfy R-DM's start condition | about 40% that this holds | **they do satisfy it.** The prompt's is wrong; the session's 40% was the nearer |
| c | the ETH episode is under 24 h and lies mostly inside the frozen intervals | under 24 h; overlap 0 | **3 h 54 m 59 s; overlap 0**, ending at the instant the frozen interval begins. The first clause held, the second was wrong |
| d | the frozen rule yields an interval open to the capture's end | no interval at all | **no interval**: 7 frozen and 4 corrected, nothing after the stop, no process after pid 14600. The prompt's is wrong |
| e | | start `13:11:00Z`, end `08:05:33Z`, about 42 h 54 m | **exact**: 1 d 18 h 54 m 33 s |
| f | | about 30 BUY refusals (26 to 34), about 58 `close_halted` lines (50 to 66) | **36 and 66.** The first is above its range (MORE, diagnosed below), the second at its upper edge |
| g | | 12 booked + 2 partial, 2 of 14 | **as predicted**; and 2 of 13 inside `[W, M)` |
| h | | about 18 a day in uptime | **19.4 (19.0 on whole days)**: MORE by about one. The 18.4 I computed in P127 divided the window's 164 by its whole uptime to `10-22`, a span the entries do not fill, since they stop at the latch |
| i | | the denominator is the kept live count | **as predicted** (3.5) |
| j | | about 0.98 MB a day | **0.976** |

**A prediction that came out wrong in either direction is recorded and not changed.** Prediction f's miss is diagnosed: BUY signals arrive in bursts (golden crosses cluster by regime), so a constant refusal rate fitted to the first 30 hours of the latch under-predicts the last 13 (21 refusals in 29.9 hours, then 15 in 13.0), and the number of refusals is a count of signals the strategy emitted, not of time latched.

## 5. What this leaves for P129's wrapper, and what no wrapper can do

1. **The coverage rule of section 2 needs the owner's ratification** before the wrapper implements it; without it the wrapper falls back to the first, wrong implementation.
2. **R-DM's end rule over-excludes whenever the latch clears before the process ends.** The 2026-10-11 episode excludes 11 h 26 m 42 s after its last evidence, and 8 entries with it. The wrapper must apply R-DM as ruled; the owner may want to know that for this episode the ruling costs 8 of 164 entries (4.9%) in the comparison E2 reports, and that E2 and E1 will not agree on it.
3. **Excluding the interval does not repair what the latch did to the state.** The backtest carries its positions, its equity and its daily-loss window through the latch; the live bot comes out of it with an unbooked partial exit, a residual position sold or not sold by hand, and a different equity (the 2% sizing starts from a different figure). Entries after the interval are therefore compared across two accounts that no longer agree, and the differences show as `risk refusal differs` or `window-edge`-like disagreements that E2's exclusion does not remove. **E2 is not a clean calibration of the backtester; it is the primary less the entries the latch took.** REASONED; nothing measures the size of the effect until a backtest exists.
4. **The `13:09` entry is neither excluded by E2 nor labelled correctly by the frozen tool.** Its signal bar closed at `13:08:59.999Z`, before the interval starts at `13:11:00Z`; the frozen diagnosis labels a backtest entry the live bot placed and did not book `fok-unfilled` (*"the live bot placed and nothing was booked"*), but the position exists in the ledger (`positions=2` at `13:10:00Z`). Whether the working leg filled in full is not read from the venue here. **UNMEASURED**, to be resolved in P129.
5. **A restart is the operator's** (R-DN) and is recorded when it has happened, in a later prompt. The deploy clone's `logs` directory shows writes after this capture was frozen (`docs/RUN_LEDGER.md` section 65); nothing here depends on them and no file in it was opened.

## 6. The figures earlier quoted that this file corrects

Reported by the owner's architect as its own errors, and marked architect-owned. This session re-measured what it could:

* **"161 included latch."** MEASURED: 8 of the 161 entries the frozen rule keeps open inside an R-DM interval (the 2026-10-11 tail), so the figure for the union is 153. It contains no entry that opens after `13:09:00Z` on 2026-10-21, because no live entry does.
* **The test labels.** Reported, not re-derived here.
* **"Surplus under-sized."** MEASURED against section 3.6: 27.8 at the whole-span rate against 34.7 at the uptime rate.
* **"B lost," asserted on an unverified premise.** Section 3.6: B is undecided, not lost, and the break-even is `10 s`, not `9 s`.
