# S4 correction P150a: R-EC, the resource fence, and R-ED, the resource-fault windows

**A new file, as `docs/S4_PREREGISTRATION.md` requires of any change after the run started (R-AO).** It adds two rulings of the project owner. **R-EC** is a rule about the machine that runs the S4 bot and changes nothing the pre-registration freezes. **R-ED** adds a listing to the stop report; it **changes no frozen label, figure, tool or digest**, as its own text says.

It is committed while the run's stop `M` = `2026-11-01T00:00:00Z` is still in the future, so before any S4 backtest figure exists, which is what R-ED's last sentence requires.

## 1. The rulings, verbatim

The project owner's rulings of M5m P150a.

> **R-EC**  Until the S4 stop, no mutation survey or parallel test run is made on the machine running the S4 bot; a single bare gate is allowed. P149's survey exhausted committed memory and a MemoryError reached pid 20100 at 2026-10-25T17:51:25Z. The missing resource fence when R-DT authorised concurrent work is architect-owned.

> **R-ED**  A resource-fault window runs from a fault line (MemoryError, websocket drop, failed reconciliation pass) to the next successful reconciliation pass or reconnect. At the stop, every disagreement of the primary, E1 and E2 whose entry bar lies in such a window is listed with the window beside it. Nothing is excluded, no frozen label or figure changes, and the windows are those measured in RUN_LEDGER. Ruled before any S4 backtest figure exists.

## 2. Where each is carried out

- **R-EC** binds every session on this machine until the stop. P150a obeyed it: no survey and no parallel test run was started, and the one gate is bare and single (`docs/RUN_LEDGER.md` section 75). It does not name the earlier work that exhausted memory; `docs/RUN_LEDGER.md` section 106 on branch `m5n` records P149's survey and its environmental failures, and the ruling's attribution of the MemoryError to it is the owner's.
- **R-ED** is carried out by `docs/RUN_LEDGER.md` section 75, which measures the windows of the capture whose SHA-256 is `07464736fb840a996387b728caec5b86912daeade2c3843a134223827a987a65` (32 windows, 3,344 s, 15 of them in pid 20100), and by `docs/S4_STOP_RUNBOOK.md` step 8, which gains the listing as its sixth required item. **The windows after that capture** are measured the same way in a later ledger section before the stop, and the stop report carries both.

## 3. What the measurement says about the fault the ruling names, MEASURED

`docs/RUN_LEDGER.md` section 75 reads the capture and finds, of the premise that the 31 pid 20100 reconciliation-pass tracebacks cluster in the squeeze, that **it is wrong**: they lie between `2026-10-24T04:39:03Z` and `2026-10-25T13:13:01Z`, ending in request timeouts and one DNS failure, none a MemoryError. The MemoryError is a single `asyncio` record at `2026-10-25T17:51:25Z` with a websocket drop in the same second, and no failed pass in or after it. **R-ED needs no change for this**, because it names a failed reconciliation pass as a fault line in its own right and the 14 network windows are windows under it. The consequence for the stop report is size: 32 windows, not one.

## 4. The operational reading, the executing session's and not the ruling's

Nothing here binds beyond the ruling. It fixes the words the stop report needs, so the listing is not improvised, and each point is a reading the owner may overrule.

1. **Merging.** Overlapping windows are merged into one, as section 75 does; a disagreement is listed once, with the merged window.
2. **The end of a window** is the earlier of the next successful `event=reconciliation_pass` line and the stream's own `event=feed_resumed` line, because no pass runs while no position is held and a reconnect is not itself logged (the library "is reconnecting itself"). Section 75's column "end taken from" says which.
3. **"Entry bar lies in a window"** is read as: the disagreement's `signal_close`, which the frozen tool prints and which is the close of the entry's signal bar, falls in the closed interval from the window's start to its end. The window is listed beside the disagreement as `start to end`, in UTC.
4. **The windows are the ledger's.** A disagreement whose entry bar lies outside every window is not listed; this is a filter on what is listed, not an exclusion from the comparison, and it moves no figure.
5. **No tool computes this listing as of P150a.** The three disagreement lists and the ledger's window tables are the inputs, and the join is by hand unless a script is written first under R-DQ (predictions committed before the code). Whether to write one is for the owner to decide; with 32 windows and three disagreement lists, a tool would be checkable where a by-hand join is not.

## 5. An observation the ruling does not carry, MEASURED, for the owner

`docs/RUN_LEDGER.md` section 75, section 3: in the eight websocket drops that left a hole, the first lost BTCUSDT 1m bar closed **0 to 31 seconds before the logged fault line** (31, 21, 6, 8, 0, 15, 20 and 13 s), because a dead socket is logged when its keepalive times out. A window that starts at the fault line therefore starts after the first lost bar, and an entry whose signal bar closed in the minute before a fault line is not in the window as R-ED defines it. **This is recorded and changes nothing in R-ED**: widening the start (for example by 60 s) is a ruling, the owner's, and the pid 20100 drop at `17:51:25Z` left no hole at all (no `bars_gap_detected`), so the question is about the eight that did.
