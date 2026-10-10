# S4 pre-registration

**Committed before the S4 run starts. Nothing in it changes after the start (R-AO).** A correction after the
start is a NEW file that says what it supersedes; this one is never edited. This file records the measurements
that exist when it is committed (the clearing, the digests, the sizing comparison) and states, in advance, what
will be computed from the run and what each figure is held against.

## 1. Authority

R-AM, R-AN, R-AO, R-AP, R-AQ, R-AR, R-AS, R-AU, R-AV, R-AW, R-AX, R-AY, R-AZ, R-BA and R-BB, R-B2 and R-C, as
quoted in `docs/NEXT_MILESTONE.md`. This file restates none of them. Where it chooses a value they leave open it
says so in a line beginning `CHOSEN`, and those lines are the owner's to overrule BEFORE this commit is pushed.

## 2. What is measured

Whether the backtester agrees with the venue (Testnet): one live run of the committed bot, and one backtest of
the same window over klines recorded from the same venue. It is a statement about the backtester and says
nothing about the strategy's profit. A pass licenses S5 to S7.

## 3. The live run

| item | value |
|---|---|
| start instant `T0` | **the `boot_provenance` instant of the S4 clone's first boot, after this file's commit (R-AY).** `CHOSEN`: the boot is the first `run` of a clone of a commit that contains this file, so the verification boot the launch checklist makes with `strategies` (which also logs a `boot_provenance` line) does not start the clock. `T0` is read from that `run` line and recorded in `docs/RUN_LEDGER.md` before anything else is read. It is not a calendar date chosen here. |
| code | the commit whose tree contains this file, run from a deployment clone of that pushed commit, non-editable venv, `boot_provenance verdict=accepted` (R-AP, R-AH) |
| config | `config.yaml` at that commit, SHA-256 `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0` (unchanged since `9f364dd`) |
| pairs | BTCUSDT 1m and ETHUSDT 5m, as configured |
| account | Binance Spot Testnet. The BTC and ETH holdings were cleared by the owner-authorised clearing of R-AV (`docs/RUN_LEDGER.md` section 40). Free USDT after it: **95,170.91** (read from the venue at 2026-10-10T04:46:19Z). |
| ledger | `data/state.json` copied from the active deployment clone: SHA-256 `1f91fc4335a3d62899ae9ba430aa6abd41a6f4468a0605ba5b252143f7677396` as read when this file was written; schema 2; 0 position records, 0 pending, 0 held. The launch checklist reads it again, and a different digest is recorded, not hidden. |

### Stop rule (R-AY)

The run stops at the FIRST UTC midnight `M` at which BOTH hold: (1) `M` is at least `T0` plus 21 days, and (2) at
least **150** bookings have been made since `T0` (a booking is an `event=close_booked`, `exit_booked` or
`boot_exit_booked` line, counted by `scripts/trade_census.py` over a frozen capture). The cap is `T0` plus 35 days:
at the cap the run stops, and S4 is evaluated if at least 100 bookings exist and is otherwise NOT MEASURED and
needs a new pre-registration. The stop is graceful (`engine_stopped clean_shutdown=True`); a position open at the
stop is left to its protective legs and is excluded from both sides.

**Prediction, recorded for later reading, not a gate.** The census of record booked 165 entries in 21 days,
7.86 a day. At that rate the 150th booking falls on day 19.1 and the first qualifying midnight is the one on or
after day 21, so the run is predicted to stop 21 to 22 days after `T0`. A Testnet market in a different regime may
book at another rate; the cap and the 100-booking floor are what bound the cost of being wrong.

### Interruptions (R-AP, R-AZ)

Every restart, including one after a power cut, is recorded in `docs/RUN_LEDGER.md` within the hour, with its
`boot_provenance` line, its reason and `git status --porcelain`. **A bot-down interval** is the span from the last
log line of one process to the first `reconciliation_pass` of the next (`scripts/s4_compare.py` computes it from
the capture). The comparison EXCLUDES, on both sides, every entry whose signal bar closed inside an interval or in
the two bars after it, and lists them. **A Testnet reset ends the run at the reset (R-AZ):** the evidence is the
bookings before it if there are at least 100, and otherwise the run restarts under a new pre-registration. What
counts as a reset is a discontinuity in the account (the balance or the order history) or the recorder's overlap
check failing; either is checked daily by the launch checklist.

## 4. The comparison window

R-AY makes `T0` an arbitrary instant, and a backtest replays whole UTC dates. So the comparison window is
`[W, M)` where **`W` is the first UTC midnight at or after `T0`** and `M` is the stop midnight. Both sides are cut
to entries whose entry bar opens in it. `CHOSEN`.

A live position opened before `W` and still held at `W` makes the live bot refuse a signal the backtest, which
starts flat at `W`, takes. That is the window's edge and not a disagreement between the models, and
`scripts/s4_compare.py` names it as its own cause, `window-edge`. `CHOSEN`: it is an addition to the closed list
of causes below that the owner may strike.

The bookings counted for the stop rule are those since `T0`; the figures of section 7 are over `[W, M)`. The two
counts are different on purpose and both are reported.

## 5. The recorded klines (R-AN, R-AW)

Store root `data/historical_testnet`, separate from the mainnet store, written by `scripts/record_testnet_klines.py`
(library `966be69`, script `4019d68`) running from its own clone of a pushed commit outside `F:\trading bot\deploy`,
with no `.env`. The comparison REFUSES to count a series unless the store verifies clean over the window and its
500 bars of history (`scripts/record_testnet_klines.py --verify-only` reads 0 problems) and the gaps the recorder
reported are listed. A gap inside the window is not filled: a backtest `BUY` the replay refuses because its warm-up
spans a gap is a `recorded-gap` disagreement.

## 6. The backtest (the parameters, R-AO)

Run from a deployment clone of the same commit:
`python -m trading_bot --config config.s4.yaml backtest --start W --end M`. The record must carry
`evidence_eligible: true` (R-AR); `scripts/s4_compare.py` refuses it otherwise.

| parameter | gate value | why |
|---|---|---|
| window | `[W, M)` UTC, whole midnights | section 4 |
| history seed | `data.history_limit` 500 closed bars per series before `W`, from the Testnet store | the live REST seed |
| `data_dir` | `data/historical_testnet` | the recorded Testnet bars |
| `exchange_info_environment` | `testnet` | filters from the stored Testnet snapshot: `BTCUSDT.json` SHA-256 `40e24c66110ba645ef49ca595618321fdbe2a36f9eab9638eea564dd8b797dc7`, `ETHUSDT.json` SHA-256 `87e5095e0e177267d7fe039b8ce1925c8e07903a0f64211c2b948f82705777cc`, copied byte for byte into `data/historical_testnet/_exchange_info/testnet/` |
| `initial_balance` | **95,170.91**, the free USDT at the start of the live run | so the 2% sizing starts from the same equity |
| `fee_percent` | **0** | Testnet commission is 0 on every fill measured |
| `slippage_percent` (entry, `CLOSE`) | **0.05** | the shipped default |
| `stop_slippage_percent` (both protective legs) | **1.20** | R-B2: the census of record's stop-loss mean, rounded up |
| strategy, risk, limits, pairs | `config.yaml` verbatim | `config.s4.yaml` differs from it only under `backtesting:`, pinned by `tests/unit/test_config_s4.py`. `config.s4.yaml` SHA-256 `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594` |

`CHOSEN`: the backtest starts at `W` with the same `initial_balance` the live run started with at `T0`, so the
live equity at `W` differs by whatever the live bot realised in between, and the sizing of every later entry
differs by that proportion. The comparison is on the entry, the exit and the percentage return, not on the
notional, and this is the one place the two runs' accounts differ by construction.

`CHOSEN`: any other backtest of this window (stop slippage 0.05 or 0.66, or the run's own mean) is exploratory, is run from
its own config file with its own digest, is reported beside the gate and decides nothing: using the run's own
mean as a gate would tune the test on its own answer.

## 7. The acceptance tests (R-C, R-BA)

`N_live` is the live bookings with an entry in `[W, M)` after the exclusions of section 3, `N_bt` the backtest's.
`scripts/s4_compare.py` prints these figures and no verdict; the decision is made here.

| test | held when |
|---|---|
| **A. gross mean** | the backtester's per-trade mean return (`realised / entry quote total`) is inside the live run's 95% interval, the mean plus or minus 1.96 standard errors of the live per-trade returns over the same entries |
| **B. count** | `abs(N_bt - N_live) <= 0.10 * N_live` |
| **C. reproduction** | at least 80% of the live booked entries are matched by a backtest entry on the same symbol and entry bar |

**S4 PASSES when A, B and C hold on eligible inputs. It FAILS when any of them fails on eligible inputs. It is
NOT MEASURED when an input is ineligible, the cap or a reset left fewer bookings than section 3 requires, or the
recorded store has a gap that touches more than 5% of the live entries (`CHOSEN`).**

**D. Diagnosis (required of the report, not a gate).** Every entry that only one side has, every matched pair
whose exits differ, and every live placement with no booking in the capture is listed with exactly one cause from
this closed list: `recorded-gap` | `bar differs` | `exact-decimal tie` | `window-edge` | `risk refusal differs` |
`fok-unfilled` | `fill-model` | `unexplained`. The precedence among the input causes is the tool's, stated in its
code: a missing bar, then a recorded close that differs from the close the live signal logged, then an exact tie
of the two averages. `bot-down interval` is not a cause on this list: those entries are excluded and listed apart.
**R-C2's refusal comparison is diagnostic and not a separate gate (R-BA)**; its effect is gated through test B.
`unexplained` is reported with its count and decides nothing (`CHOSEN`); a FAIL with unexplained disagreements is
undiagnosed, and S5 does not start until it is diagnosed. *Divergence is diagnosed, never tuned away.*

## 8. R-BB: the entry notional at the post-clear equity, against the census of record

Rule (`config.yaml`): `position_sizing.method: fixed_fraction`, `fraction: 0.02`,
`limits.max_position_size_percent: 20.0`. Through the real `calculate_position_size`, with the stored Testnet
filters and the last recorded closes (BTCUSDT 82,372.02, ETHUSDT 2,478.84): at equity 95,190 (R-AV's figure) the
notional is **1,903.6174** for BTCUSDT (0.02311) and **1,903.7491** for ETHUSDT (0.768); at the measured free USDT
**95,170.91** it is **1,902.7937** (0.02310) for BTCUSDT and **1,903.2534** (0.7678) for ETHUSDT. The census of record's median entry quote
total (`scripts/trade_census.py` on the M5k capture, SHA-256
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`) is **1,809.1410** for BTCUSDT (140 entries) and
**1,809.1747** for ETHUSDT (25). The ratios are **1.0518 and 1.0520**, within the 2x the owner set (`docs/RUN_LEDGER.md`
section 38), so no review is required by R-BB; the owner reads this section before launch regardless.

## 9. Inputs frozen by digest

This file (by the commit that contains it); `scripts/s4_compare.py` SHA-256 `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08`; `scripts/trade_census.py`
SHA-256 `926bdd4674d7fe9fa418fb5e8b67f3d089012255ba8f478492a043fbbe35d9bb`; `config.yaml` and `config.s4.yaml` as
above; the two Testnet `exchangeInfo` snapshots as above; `docs/REGIME_LABELS.json` SHA-256
`6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72` (not used by S4, listed so the record names
it); the commit SHA of the run clone, taken from its `boot_provenance` line.

## 10. What the run needs that this file cannot supply

The recorder must be running before the S4 clone's first boot and must have covered `[T0 - 500 bars, M)`; a gap in
that is a `recorded-gap`, not a missing input. The pushed commit containing this file must be built into the run
clone by the launch checklist, and `T0` is its first boot. Both are owner steps and neither is taken here.
