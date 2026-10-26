# S4 correction P150b: R-ED-1, the window start, and the listing

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It **amends R-ED's window start** and **ratifies P150a's operational reading** of R-ED in the two points the ruling names. `docs/S4_CORRECTION_P150A.md` is not edited; this file reads beside it. It changes no frozen label, figure, tool or digest, and R-ED stays reporting-only.

It is committed while the run's stop `M` = `2026-11-01T00:00:00Z` is still in the future, so before any S4 backtest figure exists, which R-ED-1's last sentence requires.

## 1. The rulings, verbatim

The project owner's rulings of M5m P150b.

> **R-ED-1**  An R-ED window starts 60 seconds before its fault line, because a dead socket is logged only when its keepalive times out and P150a measured the first lost bar closing up to 31 seconds before the fault line (RUN_LEDGER section 75). Overlapping windows merge, and a window ends at the earlier of the next successful reconciliation pass and feed_resumed (P150a's reading, ratified). R-ED stays reporting-only. Ruled before any S4 backtest figure exists.

> **Listing**  At the stop, R-ED's listing is a by-hand join made twice, independently, with the two compared and any difference resolved before the report. No script is built before the stop (R-EC).

> **ARCHITECT-OWNED**  P150a's prediction (a), that the 31 failed passes cluster in the memory squeeze, came from the architect's framing; they were network timeouts and one DNS failure, from 2026-10-24T04:39:03Z to 2026-10-25T13:13:01Z.

## 2. What each does to `docs/S4_CORRECTION_P150A.md`

- **R-ED-1 amends R-ED's window start only.** R-ED said a window runs from the fault line; it now runs from 60 seconds before it. The end is unchanged (the next successful reconciliation pass, or the stream's own `feed_resumed` if that comes first), and the rest of R-ED stands: every disagreement of the primary, E1 and E2 whose entry bar lies in a window is listed with the window beside it, nothing is excluded, and no frozen label or figure changes.
- **It ratifies two points of P150a's section 4**: point 1 (overlapping windows merge) and point 2 (the end of a window is the earlier of the next successful pass and `feed_resumed`). Merging is done after the start moves, so two windows whose widened starts now overlap one before them merge (section 75's windows 20 to 22 do, `docs/RUN_LEDGER.md` section 76).
- **It does not rule on points 3 and 4 of that section**, which stay the executing session's readings and overrulable: "entry bar lies in a window" is the disagreement's `signal_close` in the closed interval from the window's start to its end (the start now being R-ED-1's), and a disagreement outside every window is not listed, which is a filter on what is listed and not an exclusion from the comparison.
- **The Listing ruling replaces point 5** of that section, which left open whether to write a tool. There is none before the stop: the join is by hand, made twice independently, the two compared and every difference resolved before the report. The report says that it was done twice and how many differences there were.
- **P150a's section 5**, the observation that the first lost bar can close before the fault line, is answered by R-ED-1 and is left as written.

## 3. The windows, re-started

`docs/RUN_LEDGER.md` section 75 is not edited. Section 76 re-starts each of its windows at R-ED-1's start and re-merges them (30 windows, from 32). Section 75's windows after the capture of `2026-10-26T03:49:46Z` are to be measured the same way before the stop, with R-ED-1's start from the outset.

## 4. The premise, corrected for the record

P150a's prediction (a) took the architect's framing that the 31 failed passes cluster in the memory squeeze. The capture shows they were request timeouts and one DNS failure between `2026-10-24T04:39:03Z` and `2026-10-25T13:13:01Z` (`docs/RUN_LEDGER.md` section 75, section 1). The error was the architect's and the ledger already records the prediction as falsified.
