# S4 correction P129: R-DO, the end of a latch run

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It **supersedes one sentence of R-DM** (its `End` sentence, quoted in `docs/S4_CORRECTION_P128.md` section 1) **and defines the words "unbroken run" that R-DM left open.** It does not edit `docs/S4_CORRECTION_P128.md`, which stands as the record of what was ruled and measured at P128, and it supersedes nothing in the pre-registration. **R-DK, R-DL and R-DN stand as written, and so does the rest of R-DM:** the start condition, the exclusion geometry applied to both sides, the application to every episode in `[W, M)` including 2026-10-13, and the union with the frozen `down_intervals`. This file is never edited after its commit.

It is committed while the run's stop `M` = `2026-11-01T00:00:00Z` is still in the future and **before any S4 backtest figure exists.** The primary result is untouched: R-DK says it runs at the stop exactly as frozen, and R-DO is applied by E2 only (R-DL).

## 1. The ruling, verbatim

The project owner's ruling of M5m P129.

> **R-DO**  A run is the sequence of reconciliation passes from R-DM's start line. It breaks at the first later pass of the same process whose reported position count equals the open-position inventory at that instant (placements less bookings, from the log alone) and whose states contain no unknown count. A pass covering fewer positions than the inventory breaks nothing. End = the timestamp of the breaking pass or, if the run does not break, the last log line of the process in which it began. Everything else in R-DM stands. Ruled after P128's live-side counts and before any S4 backtest figure exists.

**What it replaces.** R-DM's `End = timestamp of the last log line of the process in which the run began. If that process has not stopped by capture end, the interval is open and closed at M.` becomes R-DO's end: the breaking pass, or, when the run does not break, the process's last line. R-DM's next sentence, about a process that has not stopped by capture end (*"the interval is open and closed at M"*), is not replaced by R-DO and stands. **What it ratifies.** P128's file (section 2) recorded a coverage rule that was the executing session's and awaited the owner. R-DO is the owner's wording of that idea. The two differ in how they ask the question (R-DO does not ask whether the symbol is named, and tests for an `unknown` count rather than for an untrusted line), and **on this capture they give identical episodes and identical excluded entries** (section 3), which is a fact about this capture and not a proof that they agree.

## 2. How R-DO was applied, and the two places it needed a reading

`scratch\p129\measure3.py` (SHA-256 `cf0c4a11f5927a3a89bf871b6af3fd9539bd12c528bcf8b7b745978529ccd82c`), a copy of P128's script with R-DO's run logic added; its output is `measure3_out.txt` (SHA-256 `eb4f49ab34b42c4fced3af9c0642828485d88c80737512b35c7a459e4821c7b6`). It reads the capture and writes nothing.

* **The inventory** is the set of symbols with an `order_placed` and no later `close_booked` or `exit_booked` in the same process, in file order, as in P128. A position restored at boot, or one that closed through a path that books nothing, is not in it. Where it is short, a pass's `positions=N` exceeds it and nothing breaks, so the error is toward longer runs.
* **A pass that carries an untrusted line is attached to its own pass** by nearest stamp within 15 seconds (all 2,016 untrusted lines attach; none is an orphan). A pass that both breaks a run and carries an untrusted line ends the run and starts the next at that line. **That happened 43 times in the capture, all with `states="diverged=1"`** (section 4).

## 3. The measurements

The capture is `F:\trading bot\scratch\s4\2026-10-23\190521Z-capture.log`, 3,877,171 bytes, SHA-256 `ea58a17b59f309f5c8963a9c95d7005ca7612813c09dd61475707ff4913feaed`: the 18:48:39Z freeze plus 2,660 bytes, all of pid 20100 (its first 3,874,511 bytes equal that freeze). Read-only.

### 3.1 P128's episode table under R-DO, MEASURED

| Episode | R-DM as ruled at P128 | R-DO | Change |
|---|---|---|---|
| BTCUSDT 2026-10-11, pid 16076 | `2026-10-11T16:00:01Z` to `2026-10-12T04:17:43Z`, 12 h 17 m 42 s | `16:00:01Z` to **`16:54:00Z`**, **53 m 59 s**, broken by the pass `positions=2 states="active=2"` | **-11 h 23 m 43 s** |
| ETHUSDT 2026-10-13, pid 22304 | `02:59:02Z` to `06:54:01Z`, 3 h 54 m 59 s | the same; never broken, ends at the process's last line | none |
| BTCUSDT 2026-10-21, pid 14600 | `13:11:00Z` to `2026-10-23T08:05:33Z`, 1 d 18 h 54 m 33 s | the same; never broken, ends at the clean stop | none |

Untrusted passes, `committed_risk_unknown` BUY refusals and `close_halted` lines inside each are P128's (46, 171, 1,704; 1, 2, 36; 0, 0, 66). None is open. Total latch time under R-DO: **1.9886 days** (0.0375 + 0.1632 + 1.7879), against 2.46 days under R-DM's end rule (12.295 + 3.916 + 42.909 hours).

### 3.2 Live entries kept, of the 164 opening in `[2026-10-11, 2026-10-22)`, MEASURED

| Rule | Excluded | Kept |
|---|---|---|
| frozen `down_intervals` | 3 | **161** |
| R-DM as ruled at P128, alone | 8 | 156 |
| R-DM as ruled at P128, unioned with the frozen | 11 | **153** |
| R-DO, alone | 1 | 163 |
| R-DO, unioned with the frozen | 4 | **160** |

R-DO's union excludes **one entry the frozen rule keeps**, the BTCUSDT entry whose signal bar closed at `2026-10-11T16:52:59.999Z`; the other seven entries R-DM's end rule excluded (signal bars from `17:22:59Z` on the 11th to `02:15:59Z` on the 12th) are no longer excluded. The P128 coverage rule with a break excludes the same four and no other.

### 3.3 The frozen rules now that a successor exists, MEASURED

With pid 20100 in the capture the frozen `down_intervals` returns **8** intervals, the new one **`2026-10-23T08:05:33Z` to `19:04:05Z`** (pid 14600's last line to pid 20100's first line, 10 h 58 m 32 s: pid 20100 has logged no pass, and the function takes such a process to have resumed at its first line), and `s4_explore.py`'s corrected rule **5**, the new one ending **`19:05:00Z`**, pid 20100's first closed candle. Both will end at pid 20100's first `reconciliation_pass` once one is logged, and neither is final. The new frozen interval begins at the instant the 2026-10-21 R-DO interval ends, so the union is one span of `13:11:00Z` to `19:04:05Z`.

### 3.4 Pid 20100, MEASURED

11 stamped lines, from `2026-10-23T19:04:05Z` to `19:05:00Z`: **0 `reconciliation_pass`, 0 `reconciliation_untrusted`**, because no position is open. Its `boot_provenance` line reads `verdict=accepted`, `install_kind=vcs`, `code_intact=true` over 77 files, `code_commit` and `checkout_commit` both `45547f10771543b41db42e1cbcb8b5a0a9cf1776`, `checkout_dirty=false`, `commits_agree=true`, `config_tracked=true`, `config_sha256=f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`; then `Composition root ready: 2 pair(s), 93448.52773900 USDT free` and `Trading engine started: BTCUSDT/1m, ETHUSDT/5m` at `19:04:10Z`. Its last line is an ETHUSDT `CLOSE` refused as `nothing_to_close` at `19:05:00Z`.

## 4. What R-DO costs, MEASURED

1. **`diverged` counts as healthy.** R-DO breaks a run at a full-coverage pass with no `unknown` count, and a position the reconciler has marked `diverged` is not `unknown`. On a lone position that is a break at every such pass: **43 passes in the capture** (pid 25352: 38, on 2026-10-15 from `04:23:01Z`; pid 5224: 5), each ending a run and starting the next. None lies in a qualifying episode: they are on 2026-10-15 and 2026-10-19, in runs that held no refusal. **A latch that is `diverged` on a single position would be cut into one-pass runs, and a refusal would count only if it landed inside one of them.** The 2026-10-11 episode is `diverged` on one of two positions, and R-DO keeps it unbroken only because the inventory holds both.
2. **The break lags the clearing.** The last pass that named BTCUSDT untrusted in the 2026-10-11 episode is `16:51:01Z`; R-DO breaks at `16:54:00Z`, the first pass that covered both positions, **2 m 59 s later**, and one live entry opened inside that gap (`16:52:59.999Z` signal bar, placed after the last pass that named BTCUSDT untrusted) is excluded. It is the one entry by which R-DO's union keeps 160 and not 161.
3. **The 2026-10-11 result depends on the inventory.** It holds ETHUSDT and BTCUSDT; if either were missing, the passes with `positions=1` would equal it and break the run at the first.

## 5. B recomputed with all three episodes, REASONED

The latch interval under R-DO is 1.9886 days. The backtester trades through it and the live bot did not, so on the **primary** (which excludes only the frozen downtime) each backtest entry in it is a surplus; test B divides by the live entries kept, so it holds only if `N_live >= 10 x the surplus`. The live side keeps 161 entries so far under the frozen rule, and 8.205 days remain from `2026-10-23T19:05:00Z` to `M`.

| Rate (a day) | Surplus | `N_live` needed | Projected final `N_live` (161 + rate x 8.205) | Margin |
|---|---|---|---|---|
| whole-span 15.55 | 30.9 | 309 | 289 | **-6.7%** |
| uptime 19.40 | 38.6 | 386 | 320 | **-17.0%** |
| mixed: whole-span surplus, uptime future | 30.9 | 309 | 320 | +3.6% |

Each consistent rate falls short, and a mixed rate has no basis, since the future live rate and the surplus are both the rate at which the strategy fires. **B on the primary is likely to fail**, and that is a prediction about a backtest nobody has run: it assumes the backtester trades at the live rate, that the live bot runs from `19:05Z` to `M` with no further outage or latch, and that the backtest's own count in the unaffected days equals live's. R-DK records such a failure as `FAIL (latch-caused)`. **E2 excludes the latch intervals on both sides, so its B-figure has no latch surplus** (and, per P128 section 5, is still not a clean calibration).

## 6. What this leaves for the E2 wrapper

R-DO is the ratification P128 section 5 asked for, so the wrapper's first precondition is met. **Still open:** the `13:09` BTCUSDT entry's label from a venue read (`M5m-596`); the 43 `diverged` passes and the 2 m 59 s lag of section 4, which the wrapper must implement as R-DO is written and which the owner may want to know price E2; the open-interval fallback at `M`; and the wrapper being committed and tested before any S4 backtest figure exists. The restart is recorded in `docs/RUN_LEDGER.md` section 67.
