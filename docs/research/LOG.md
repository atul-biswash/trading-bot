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

## Candidate entries

None yet. No variant has been run.
