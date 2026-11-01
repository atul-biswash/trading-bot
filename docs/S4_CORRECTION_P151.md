# S4 correction P151: the ratification of R-ED's points 3 and 4

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It records one ratification of the project owner. `docs/S4_CORRECTION_P150A.md` and `docs/S4_CORRECTION_P150B.md` are not edited; this file reads beside them. It changes no frozen label, figure, tool or digest.

It is committed after the run has stopped (the final capture is the one in `docs/RUN_LEDGER.md` section 77) and **before any S4 backtest figure exists**: no backtest has been run when it lands.

## 1. The ratification, verbatim

The project owner's ruling of M5m P151.

> R-ED P150a points 3 and 4 are ratified: signal_close lies in the closed interval, and an entry outside every window is not listed.

## 2. What it settles

`docs/S4_CORRECTION_P150A.md` section 4 gave five points as the executing session's operational reading of R-ED. R-ED-1 (`docs/S4_CORRECTION_P150B.md`) ratified points 1 and 2 and replaced point 5, and named points 3 and 4 as not ruled on. This ruling ratifies them:

- **Point 3.** An entry bar "lies in a window" when the disagreement's `signal_close`, which the frozen tool prints, falls in the **closed** interval from the window's start to its end. The start is R-ED-1's (60 seconds before the fault line) and the end is the earlier of the next successful reconciliation pass and `feed_resumed`.
- **Point 4.** A disagreement whose entry bar lies outside every window is not listed. This is a filter on what the R-ED listing shows and not an exclusion from the comparison: no figure, label or verdict moves.

With the Listing ruling of P150b (a by-hand join made twice, independently, compared, no script before the stop), every part of R-ED's listing is now ruled. Nothing in P150a's section 4 remains an unratified reading.
