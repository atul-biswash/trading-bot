# S4 correction P130: R-DP, the break test is the trust set

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It **supersedes R-DO's break test only** (the sentence *"It breaks at the first later pass of the same process whose reported position count equals the open-position inventory at that instant ... and whose states contain no unknown count."*, quoted in `docs/S4_CORRECTION_P129.md` section 1). `docs/S4_CORRECTION_P128.md` and `docs/S4_CORRECTION_P129.md` are **not edited**. **Everything else in R-DM and R-DO stands:** the start condition, the rule that a pass covering fewer positions than the inventory breaks nothing, the end (the breaking pass or, when the run does not break, the last log line of the process), the exclusion geometry applied to both sides, the union with the frozen `down_intervals`, and the open interval closed at `M`. R-DK, R-DL and R-DN stand. The primary result is untouched: R-DK says it runs at the stop exactly as frozen, and R-DP is applied by E2 only (R-DL).

It is committed **before the E2 wrapper's predictions and code are written** and while the run's stop `M` = `2026-11-01T00:00:00Z` is still in the future, so before any S4 backtest figure exists.

## 1. The ruling, verbatim

The project owner's ruling of M5m P130.

> **R-DP**  An R-DO run breaks only at a pass of the same process whose reported position count equals the open-position inventory at that instant and whose every reported state is in the trusted set of core/portfolio.py _TRUSTED_PROTECTION at 45547f1 (active, absent_by_design). Any other state, named or not, is untrusted and breaks nothing. Everything else in R-DM and R-DO stands. Ruled after the P130 step-0 source read and the scratch variant (sha256 747d68659e9710aedfa9e5ecec7c7c9463c54d23f0c9effa2a1dcdb633aa5d6a), which changed no episode or kept count, and before any S4 backtest figure exists.

## 2. The grounds: what the source says, DOCUMENTED

P130's step 0 asked whether a position in the `diverged` state can contribute to a `committed_risk_unknown` refusal, and said to halt if it can. **It can, and the session halted.** The chain, by file and line at `33d6765`:

| Link | Where |
|---|---|
| the trusted set is `ABSENT_BY_DESIGN` and `ACTIVE` and nothing else | `src/trading_bot/core/portfolio.py:98`, `_TRUSTED_PROTECTION = frozenset({ProtectionState.ABSENT_BY_DESIGN, ProtectionState.ACTIVE})` |
| a position whose protection is outside it counts uncomputable | `core/portfolio.py:1143`, `if stop is None or mark is None or position.protection not in _TRUSTED_PROTECTION: uncomputable += 1` |
| an uncomputable count refuses every entry while stops are on | `src/trading_bot/risk/manager.py:421-428`, `if uncomputable and self._config.stop_loss.enabled:` then `refuse(..., stage=RefusalStage.COMMITTED_RISK_UNKNOWN)` |
| the reconciler produces `DIVERGED` | `src/trading_bot/execution/reconciliation.py:359, 367, 397` |
| and writes the assessment's state onto the position | `execution/reconciliation.py:691` (`record_partial_reconciliation(protection=assessment.state)`) and `:700` (`record_reconciliation(protection=assessment.state, at=now)`) |
| the enum says the three added members default untrusted on purpose | `src/trading_bot/core/enums.py:261-267` |

So R-DO's *"no unknown count"* treated `diverged` as healthy while the bot refused entries on it. The capture agrees: BTCUSDT read `diverged=1` on 2026-10-11 while a BUY was refused at `committed_risk_unknown` at `16:21:00Z`.

**The check P130's resumption added, DOCUMENTED:** a `diverged` pass emits the `reconciliation_untrusted` line R-DM's start condition requires. `src/trading_bot/execution/reconciliation_driver.py:492-508` builds the list of positions whose `assessment.state not in _TRUSTED_PROTECTION` and logs `event=reconciliation_untrusted` for them, so every state outside the trusted set, `diverged` and `pending` included, emits it, and **a pure `diverged` latch can start an episode.** Measured agreement: the 43 `diverged=1` passes of the capture each carried an untrusted line. The `states` field of the pass line is the same module writing each state's lowercase `.value` (`reconciliation_driver.py:479` and `:488`), which is why the trusted set can be compared to it by name.

**The trusted set is the same at `45547f1` and at HEAD:** `core/portfolio.py` holds the one line above at both, which is what R-DP names.

## 3. The scratch variant, MEASURED

`scratch\p130\measure3_variant.py` (SHA-256 `38c187cce8b0443ed0a1666ad0f3f793fa256162bc80bbb805f01ff363bcfd32`) is P129's `measure3.py` with one condition added, no `diverged` count, on the same capture (`F:\trading bot\scratch\s4\2026-10-23\190521Z-capture.log`, SHA-256 `ea58a17b59f309f5c8963a9c95d7005ca7612813c09dd61475707ff4913feaed`); its output is SHA-256 `747d68659e9710aedfa9e5ecec7c7c9463c54d23f0c9effa2a1dcdb633aa5d6a`. Against P129's table:

| | P129 (R-DO) | The variant (R-DP's effect on this capture) |
|---|---|---|
| episodes | 2026-10-11 `16:00:01Z` to `16:54:00Z`; 2026-10-13 `02:59:02Z` to `06:54:01Z`; 2026-10-21 `13:11:00Z` to `2026-10-23T08:05:33Z` | identical, to the second |
| live entries kept, of 164 | 161 frozen, 160 union | 161 frozen, 160 union |
| passes that broke a run and carried an untrusted line | 43 (all `diverged=1`) | **0** |
| runs of any length | 61 | 18 |

R-DP therefore changes **no episode and no kept count on this capture**, and closes the hole P129 section 4 (1) recorded: a lone-position `diverged` latch is no longer cut into one-pass runs. It does not touch P129 section 4 (2), the break's lag behind the clearing (2 m 59 s and one entry in the 2026-10-11 case), which R-DP leaves as it was.

## 4. What it asks of the E2 wrapper

The wrapper **derives the trusted set by importing `_TRUSTED_PROTECTION`**, not by restating it, so the rule follows the code that refuses entries; run with the S4 clone's interpreter it is the set at `45547f1`. A pass whose `states` field is absent or unreadable breaks nothing, since R-DP trusts only what it can read. The wrapper's own tests pin each of these, including a lone-position `diverged` latch (no break), a `pending` state (no break) and a full-coverage all-active pass (break).
