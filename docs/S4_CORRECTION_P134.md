# S4 correction P134: R-DR, a wick annotation on the stop report's disagreements

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It **supersedes nothing**: not the pre-registration, not `docs/S4_CORRECTION_P128.md`, `docs/S4_CORRECTION_P129.md` or `docs/S4_CORRECTION_P130.md`, and not any ruling in them. It **adds a diagnostic**, an annotation on the entries the comparison already lists, and nothing it adds changes how a figure is computed or a verdict is read.

It is committed while the run's stop `M` = `2026-11-01T00:00:00Z` is still in the future, so before any S4 backtest figure exists. The only backtest run since P130 is the P131 rehearsal over `2026-10-08`, which ends before T0 and decides nothing (`docs/RUN_LEDGER.md` section 69).

## 1. The ruling, verbatim

The project owner's ruling of M5m P134.

> **R-DR**  At the stop, every entry in the disagreement lists of the primary, E1 and E2 is annotated with whether a 1m bar of its pair with range (high - low) / open >= 3% occurred while the live position was open, and the counts are reported by cause. It recomputes no A, B or C figure, is not an exploratory analysis under R-DL, and changes no verdict. The 3% threshold was chosen after P133's measurement; its sensitivity is recorded in this file. Ruled before any S4 backtest figure exists.

## 2. The grounds, MEASURED

P133 recorded ETHUSDT list `218102` (placed `2026-10-23T22:00:01Z`), whose stop of `2354.20` the recorded 1m series crossed by 436.05 at the lowest low while both legs read `EXPIRED` with nothing executed, and whose cluster, with six others, begins within about three minutes after a 1m bar of its pair that is 15% or more wide (`docs/RUN_LEDGER.md` section 70, capture SHA-256 `6aae8a36793ed28e38adf4f7b0f8652407cec5d8dcf29e54a79900935d83c55f`; `M5m-671`, `M5m-673`, `M5m-674`). The comparison classifies a live-versus-backtest exit disagreement as `fill-model` without saying whether a wick was present, so a reader of the stop report cannot tell a fill-model difference on a quiet bar from one in a wick. R-DR is the annotation that tells them.

## 3. The threshold, and how it was chosen

**The 3% was chosen after P133's measurement and not before it.** P133's measurement 5 counted bars of 3% or more as an exploratory cut, unpredicted, and the owner's ruling took the same number. It was therefore not fixed in advance of the data, and the owner's text says so. What the file owes the reader in return is its sensitivity, measured at P134 from the store copy (inventory SHA-256 `6b8d8f18777253d67e822787af07c55a30128fb5f479c1c5887b2025dffed449`) over the 19,799 1m bars per pair since T0 (`docs/RUN_LEDGER.md` section 71, `measure2.py` `623335d53030233778251ca61ff100c7ec0f6213a3e79540813c1ec83e916180`):

| Threshold, range >= | BTCUSDT bars | ETHUSDT bars |
|---|---|---|
| 3% | 54 | 16 |
| 5% | 51 | 15 |
| 10% | 46 | 15 |
| 15% | 45 | 15 |

The bars that leave the set as the threshold rises:

| Step | BTCUSDT | ETHUSDT |
|---|---|---|
| 3% to 5% | `2026-10-20T19:44` (3.37%), `2026-10-20T19:59` (3.77%), `2026-10-22T01:38` (4.22%) | `2026-10-20T18:47` (3.71%) |
| 5% to 10% | `2026-10-17T15:36` (7.23%), `2026-10-20T01:30` (5.20%), `2026-10-20T23:01` (6.21%), `2026-10-23T12:26` (6.05%), `2026-10-23T12:27` (7.01%) | none |
| 10% to 15% | `2026-10-19T18:45` (12.97%) | none |

**What the table says about the choice.** Above 5% the ETHUSDT set does not move; the BTCUSDT set loses 5 bars between 5% and 10% and one between 10% and 15%. So 3% admits 8 BTCUSDT bars and 1 ETHUSDT bar that 10% does not, and the 45 BTCUSDT and 15 ETHUSDT bars of 15% or more are in every set. The threshold is therefore a choice about 9 narrow bars out of 70, not about the wicks of section 70, which are all 15% or wider. **A reader who prefers another threshold can apply it without re-running anything**, because the annotation is to report the widest range found while the position was open and not only whether 3% was met (section 5), and the counts by cause can be re-cut from that figure.

## 4. What R-DR does and does not do

- It **annotates**: each entry in the disagreement lists of the primary, E1 and E2 gets a yes or no, and the counts by cause (the frozen causes: recorded-gap, bar differs, exact-decimal tie, window-edge, risk refusal differs, fok-unfilled, fill-model, unexplained) are reported beside the lists.
- It **recomputes no A, B or C figure** (the mean, the count and the reproduction tests of the pre-registration), and it **changes no verdict**: a test that fails or passes does so on the frozen figures.
- It **is not an exploratory analysis under R-DL**. R-DL's two analyses, E1 and E2, change what is excluded or which window is read; this changes neither, and it is therefore reported with the primary, not beside E1 and E2 as a third exploratory run.
- It **excludes nothing** and is not a latch interval (R-DM, R-DO, R-DP): an entry in a wick is still compared.

## 5. The operational reading, the executing session's and not the ruling's

Nothing here binds beyond the ruling. It is recorded so the stop report is not improvised.

1. **"While the live position was open"** is read as the interval from the live entry's `order_placed` line to the exit's booking line, for an entry that has a live position. For an entry with **no live position** (a backtest-only entry), the ruling's own words give no interval; the annotation reads *no live position* for it and the owner may rule whether the backtest's holding period should be used. **That is a gap in the ruling, not a decision of this file.**
2. **The annotation reports the widest range found** in a bar of the entry's pair opening inside the interval, as well as the yes or no at 3%, so the threshold can be re-cut (section 3).
3. **No tool implements it yet.** The annotation needs a small program that reads the capture, the disagreement lists and the frozen store, and a program is code: under R-DQ it is drafted only after its predictions commit exists and it passes the full bare gate before it is committed. It is not built in P134. Until it is, the stop report can carry the annotation only by hand, which is what the runbook's step 8 now says (`M5m-682`).
4. **The case R-DR was ruled for** is ETHUSDT list `218102`: the live bot booked a `CLOSE` at about 2,385.08 at `22:40:03Z` for `-11.36658000`, and the backtest is expected to book a stop-out in the `22:30` wick; the frozen `diagnose` would print that as a `fill-model` disagreement, and R-DR is what lets the stop report say a wick was present when it does (`M5m-675`, REASONED, to be measured at the stop).

## 6. A term this file does not define

P133's prompt asked for *"the expected backtest A-side disagreement for this entry"*. **"A-side" is defined nowhere in the repository**, not in the pre-registration, the correction files, `docs/NEXT_MILESTONE.md` or the scripts; the executing session read it as the live-versus-backtest exit disagreement the frozen `diagnose` prints, and `M5m-675` says so. It could equally have meant the side of the pre-registration's test A, the gross mean (A, B and C are the three tests, as R-DR itself names them), which a backtest stop-out in a wick would move; the two readings agree on the REASONED expectation and differ in what they ask to be measured. It is recorded here as an architect-owned undefined term (`M5m-679`) so that a later reader does not search for a definition that does not exist.
