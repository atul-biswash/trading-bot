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

## Candidate entries

None yet. No variant has been run.
