# The S6 research log

An observation log. Every entry is added, none is edited: a result later found wrong is annotated by a
later entry. `docs/research/PROTOCOL.md` is the protocol; the entries under `docs/research/entries/` are
the machine-checked half of this log, one JSON file per read. **The denominator of S7's multiple-testing
judgement is the 216 variants PROTOCOL.md section 5 declares, and the number of candidates actually read
out of sample is the number of entries here with `status` `read`.**

## Entry 1 -- S5, the baseline: a full-history read of a non-candidate configuration (P113 C1, R-BT)

Recorded **before any run exists**, as R-BT requires.

| | |
|---|---|
| what | the committed `config.yaml` as it stands: `sma_crossover` `fast_period` 20 and `slow_period` 50, BTCUSDT 1m and ETHUSDT 5m, jointly (R-Y) |
| window | `[2017-08-17, 2026-10-01)`, **the whole history, out-of-sample window included** |
| arms | stop slippage 0.05%, 0.66% and 1.20%; 1.20% is the gate arm (R-B2) |
| what it is | **a non-candidate configuration.** Its timeframes are 1m and 5m and no S6 candidate has either, so its read of the out-of-sample window is not a candidate's read (PROTOCOL.md section 8) |
| what it reports | in-sample and out-of-sample figures **separately**, at the boundary `2024-01-01` (R-BT); the whole-history figures beside them |
| the prediction on record | `docs/NEXT_MILESTONE.md` S5: the census predicts a negative number; S5 confirms or refutes it |
| entry file | `docs/research/entries/s5-baseline.json`, of kind `baseline`, committed with the guard that reads it |
| status | pending: no run exists |

## Entry 2 -- S5, the baseline: READ (P115 C1, R-BT, R-BW, R-BX)

Entry 1's `status` was true of the instant it wrote it and is left as written. **From the three runs below the baseline entry is read**: the whole history, the out-of-sample window included, has been
read by this configuration at three stop-slippage arms.

| | |
|---|---|
| what was read | the committed `config.yaml` (SHA-256 `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`) at deployment clone `67b7563de683cb64f500f0a0d2264f93e7f9089e`, `[2017-08-17, 2026-10-01)`, protocol entry `s5-baseline`, kind `baseline`, window class `straddling` |
| runs | `20261014T070004816981Z-6b9d3b8c7f89` (0.05%), `20261014T104541570489Z-e5111d9f08f7` (0.66%), `20261014T155450267068Z-52e1f0448bc4` (1.20%); the report is `s5_report.txt`, SHA-256 `6b73bc8bb9bbdc339c3c81d6ef46a36ceb144703436931f76429756fa7e02bb1`; `docs/RUN_LEDGER.md` section 50 holds the digests and the figures |
| a candidate's read? | **no.** A non-candidate configuration, as Entry 1 recorded (PROTOCOL.md section 8), and R-BX rules it is not an S6 candidate. It is not one of the 216 variants of PROTOCOL.md section 5 |
| in sample | 47,358 trades, net P&L -9390.12 / -9520.56 / -9612.50 USDT, gross -2970.52 / -3695.81 / -4251.89, equity 10,000 to 609.85 / 479.42 / 387.48 at 0.05 / 0.66 / 1.20% |
| out of sample | equity 609.85 / 479.42 / 387.48 to 255.46 / 255.21 / 255.11; 23.73 / 46.26 / 65.22% of 20,242 BUY signals refused as `size_not_tradeable`. **R-BW: this window's section starts from the in-sample loss, not from 10,000 USDT, so it is not comparable with S7's thresholds, and S5's S7 preview is recorded as a preview only.** |
| the prediction on record | confirmed: the number the census predicted negative is negative in every arm, gross and net (R-BX) |
| what the read cannot be used for | selecting, tuning or rejecting any S6 candidate: the window it read is the window S7 reserves, so any choice made from these figures is a choice made after seeing it |
| status | **read**. The machine-checked file `docs/research/entries/s5-baseline.json` stays `pending`, because `tests/unit/test_main_protocol.py` asserts it, so marking it read is a code-and-test commit left to the owner; until then a fresh clone's guard would still allow a second read of the baseline |

## Entry 3 -- S5, the baseline: the entry file marked read (P116 C1, R-BY)

Entry 2 recorded the read and left the machine-checked file `pending`, because a test asserted it. **R-BY ruled the assertion overturned.** `docs/research/entries/s5-baseline.json` is now `status`
`read`, and its `oos.records` carry, per arm, the run directory and the SHA-256 of its `run.json`:

| arm | run | `run.json` SHA-256 |
|---|---|---|
| 0.05 | `20261014T070004816981Z-6b9d3b8c7f89` | `36b7b1a6f09c34b2fc7ac03006b676eced720d30bba67021202cb9e71fa51a61` |
| 0.66 | `20261014T104541570489Z-e5111d9f08f7` | `c4f4fe39065cbc071e69ac00668b642ecf26386a294c3d3637abccfe475d7c0a` |
| 1.20 | `20261014T155450267068Z-52e1f0448bc4` | `8837f2d074354e3382b7017e228364551e893978648bec265dd4931773a93e47` |

**From a clone of this commit the guard refuses a second read of the baseline at any arm**, as `already_read`, with no state outside git. The digests were recomputed from share-mode copies of the run records on the day they were
written here and agree with `docs/RUN_LEDGER.md` section 50.

## Entry 4 -- S6: the protocol amended, the tooling built, nothing run (P117 C1 to C8, R-CA to R-CJ)

No variant has been run and no candidate has been read. What changed, for a reader arriving later.

| | |
|---|---|
| the protocol | amendment 2 (`66f64ce`), before any S6 run: selection on **per-trade returns** (R-CB), a run whose per-bar drawdown exceeds **0.95** is ruined and ineligible, the balance stays 10,000 (R-CC), at least **250** in-sample trades (R-CD), the **1.20%** arm only for selection (R-CE), walk-forward **reported not gated** over four anchored folds, 2020 to 2023 (R-CF), all **216** variants run and counted, 1d included (R-CG), S7 passes only if **both** profit factors, in returns and in USDT, are at least 1.3 (R-CJ) |
| the freeze | `scripts/s6_select.py` writes one selection file, committed unedited with its SHA-256 recorded here, and one pending entry per candidate; the entries are pushed before any out-of-sample read, and the guard refuses a digest with no entry |
| the denominator | 216 variants declared. P116 measured that by buy-edge count at most 97 can reach 100 in-sample trades and 69 can reach 232; at 250 and by the replay in which only the strategy's CLOSE exits, 42; three of the twelve cells (1d `sma_crossover` off and on, 1d `rsi` on) cannot reach even 100. The number of candidates is therefore expected to be well under twelve; **it is not known until the sweep is read** |
| the tooling | `backtesting/selection.py` and `scripts/s6_select.py`, `scripts/s6_sweep.py` (resumable, parallel only after R-CH's check), `backtesting/gate.py` and `scripts/s7_gate.py` (a refusal withholds every verdict); `docs/RUN_LEDGER.md` section 51 holds the build record and the surveys' digests |
| two rules the tooling adds | `PROTOCOL.md` is byte-stable from the first sweep run to S7 (a run made under another digest is skipped by the selection and refused by the gate); nothing untracked is written into a clone |
| the owner's steps | O1 to O6, with a CHECK each, in `docs/NEXT_MILESTONE.md` (the P117 C8 block) |
| status | **tooling built; no S6 run exists.** The baseline entry stays `read` (Entry 3) |

## Entry 5 -- S6: two variants ruled ineligible, and the figures that were seen (P119 C1, R-CM to R-CQ, amendment 3)

Recorded **before any S6 run exists**, and decided, in the owner's words, *"before any in-sample result exists and without regard to those figures"*.

| | |
|---|---|
| the ruling (R-CM) | *"The two variants the rehearsal read in the reserved window, sma_crossover at 4h at the 10/50 grid point with the trend filter off and on, are ineligible for selection. They are still swept and counted in S7's variant denominator. The research log records that their figures for 2024-01-01 to 2025-04-01 were seen, by what, and where."* |
| the two variants | `sma_crossover`, 4h, `fast_period` 10, `slow_period` 50, the trend filter off; and the same with `trend_filter_period` 200 (the filter on). Two of the 216; the other 214 are untouched |
| what changed | `docs/research/PROTOCOL.md` amendment 3: section 6 step 3 condition d, and `selection.ineligible_variants` in the declaration. They are still run by the sweep and counted: the denominator is 216 |
| seen by | **the implementer, an AI coding assistant (Claude), through the P118 rehearsal script `scripts/s6_rehearsal.py` and a scan script, and by nothing else.** Not the bot, not the owner's runs, not S5 |
| seen where | **throwaway worktrees outside the repository** (`F:\trading bot\scratch\p118\rehearsal\`), removed with their records; the console outputs and per-hop logs are kept in `F:\trading bot\scratch\p118\`. The figures are in the message of commit `d198631` (`M5m-447`) and in `docs/RUN_LEDGER.md` section 52 |
| over what | `2024-01-01` to `2025-04-01`, for those two variants only, in the **narrowed** protocol of the rehearsal, whose own boundary (2025-01-01) the engine took for the boundary; the real protocol's out-of-sample window starts 2024-01-01 |

**What was seen, exactly.**

| Read | Window | Arms | Figures |
|---|---|---|---|
| rehearsal run 1, the in-sample sweep of the narrowed protocol | `[2023-12-01, 2025-01-01)` | 1.20% | unfiltered: 61 trades, return profit factor 0.476882; filtered: 31 trades, 0.466729 (the selection report of that run) |
| rehearsal run 1, out of sample | `[2025-01-01, 2025-04-01)` | 0.05, 0.66, 1.20% | unfiltered: 15 trades, return profit factor 0.6352 / 0.4233 / 0.2958, regime net -49.30 (sideways); filtered: 2 trades, profit factor 0 at all three, regime net -13.27 |
| rehearsal run 2, out of sample | `[2024-01-01, 2024-04-01)` | 0.05, 0.66, 1.20% | unfiltered: 11 trades, 2.4008 / 1.5973 / 1.1151, regime net +3.19 (rising); filtered: 7 trades, 1.5623 / 1.0445 / 0.7313, regime net -5.76 |
| the quarter scan, single quarters of 2024 | `2024-04-01` to `2025-01-01`, three quarters | 1.20% | net result, unfiltered / filtered: 2024 Q2 -40.43 / -16.24; 2024 Q3 -52.15 / -19.90; 2024 Q4 -27.48 / -13.87 (the scan's 2024 Q1 row, +3.19 / -5.76, repeats run 2) |

**What was not seen.** Any bar or figure at or after `2025-04-01`; any other variant; the 0.05% and 0.66% arms for 2024 Q2 to Q4; the trade logs themselves (the figures above are the reports' totals). The S5 baseline's whole-history read (Entry 2) is a different configuration.

**What follows from it, and what does not.** The two variants cannot be a candidate however they rank in-sample, so no candidate of S6 is one whose out-of-sample figures anyone had seen before its read. Their figures are not used to rule on any other variant, and the ruling was made without them. **A foreseen S7 verdict on a variant is a reason to rule it out of selection, which is what R-CM does; it is not a reason to change S7.** The rehearsal script refuses, from `d198631`, any window that ends after the real boundary (R-CN), and its default window is the year 2020.

**The other four rulings of amendment 3** (R-CN to R-CQ) govern code, tools and the owner's steps and are recorded in `PROTOCOL.md` section 10.

## Candidate entries

None yet. No variant has been run.
