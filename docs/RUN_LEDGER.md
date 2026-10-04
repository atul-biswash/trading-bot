# Run ledger — what the log recorded, and what it could not

## 1. What this file is, and the two things it is not

This file is a record of observations taken from `logs/trading_bot.log` between
2026-07-23 and 2026-09-17. Every figure in it was produced by a command that is
printed beside it and can be re-run.

**This file asserts no rule.** Rules for this project live in `CLAUDE.md`, and a
reader looking for one is served by going there rather than by reading anything
here as prescriptive. Nothing below tells anyone what to do; the sentences are
past-tense statements about bytes that existed at a stated time with a stated
digest.

**This file corrects no sentence in an external authority document, and edits no
prior committed file.** Several statements in this repository's
other documents bear on the evidence recorded here. Those statements are left
exactly as they were written, unamended, and the question of what should happen
to them is reserved to the project owner. This file edits none of them. It
names a finding only where a later section records an observation that bears on
it, and even there it amends nothing — section 14 is add-only, and the commit
that added it removed no line.

**A third property worth stating, since it is what keeps the first two
enforceable:** the measurements here were taken by an assistant under
instruction, and the judgement calls they bear on — whether a document is wrong,
whether a leg filled, whether anything should be run again — were reserved at
the time of writing and remain so.

> **ANNOTATED AT M5l (P63): TWO SENTENCES ABOVE DO NOT DESCRIBE SECTIONS 21
> AND 22.** *"This file is a record of observations taken from
> `logs/trading_bot.log` between 2026-07-23 and 2026-09-17"*: section 21's
> run writes to `F:\trading bot\deploy\06089d5e01cb\logs\trading_bot.log` and
> section 22's to the retired clone's own log, not to this repository's, and
> the date range already ended short of sections 15 to 20. *"Every figure in it
> was produced by a command that is printed beside it"*: section 21's start
> fields are copied from the run's `boot_provenance` line, as the project
> owner supplied them, and no command produced them. **What survives:** the
> file still asserts no rule and corrects no other document, and every other
> figure in sections 21 and 22 carries its instrument.
>
> **AND SECTION 23 (P64).** Its capture is of the deployment clone's log,
> not of `logs/trading_bot.log`, and it is dated 2026-09-27. Every figure
> there carries its command.

---

## 2. The artefact and its digest

The source is `logs/trading_bot.log`. **It is gitignored, and it rotates**
(`max_bytes: 10_485_760`, `backup_count: 5` in `config.yaml`), so a future
reader may hold a file that shares a name with this one and shares nothing
else.

Every figure below was derived from a single frozen capture:

| Property | Value |
|---|---|
| capture | `trading_bot.final-20260917T185851Z.log` |
| taken | 2026-09-17T18:58:51Z, after the writing process had exited |
| bytes | 4,089,853 |
| lines | 21,209 |
| **SHA-256** | **`0E6B673E16671152A4E08CA6CC8390E7B72EA8B75C3E7303FA0C16B4E04D223E`** |

**A reader holding a different digest holds a different file, and the figures
below describe that reader's file only by coincidence.** OBSERVED.

The capture was verified byte-identical, over its first 3,966,645 bytes, to an
earlier frozen copy taken at 2026-09-17T06:30Z
(SHA-256 `9B4D98F741B2D29D27BC3BADCF9E227AE3F97D04CCF960FE3DD1C1B915A4C915`), and
byte-identical over its first 4,085,931 bytes to an intermediate capture taken
at 2026-09-17T18:39:00Z
(SHA-256 `4B88118A64F884190AC85F22DCD9046F23CBD0E11B5CAC06C43FF70140347C32`).
Each is therefore a strict extension of the one before it: the file was appended
to and at no point rewritten or rotated across the observation period. OBSERVED.

The log itself is absent from this repository and remains so. What is recorded
here is derived tables, plus two quoted lines in section 7.

---

## 3. The instrument and its boundary

The census keys on the `pid=` field that each log record carries.

```bash
LOG="<the capture named in section 2>"
grep -n 'pid=' "$LOG" | head -1
grep -n 'pid=' "$LOG" | head -1 | cut -d: -f1 | awk '{print $1-1}'
grep -oE 'pid=[0-9]+' "$LOG" | sort -u | wc -l
```

| Property | Value | |
|---|---|---|
| first line carrying `pid=` | line 13,995, `2026-08-27 17:10:37` | OBSERVED |
| lines preceding it | 13,994 | OBSERVED |
| distinct pids in the capture | 47 | OBSERVED |

The field was introduced by commit `041d54c`, *"feat(engine): one instance per
checkout, and a PID on every record"* (2026-08-27 13:16 +0600). Records written
before that carry no process identifier of any kind.

**Which milestone windows this instrument can see:**

| Window | Visibility |
|---|---|
| pre-M5f, M5d, M5e, M5f | UNMEASURABLE — no `pid=` field existed |
| **M5g** | **PARTIAL** — the window opened 2026-08-26 05:38:02Z and the field began 2026-08-27 17:10:37Z, leaving ~35.5 h unseen. Every M5g figure below is a LOWER BOUND |
| M5h, M5i, post-M5i | fully measurable |

The 2026-08-27 evidence quoted in section 7 falls inside M5g's unseen interval
and carries no `pid=`, so it is dated but unattributed to a numbered run.

---

## 4. The timezone caveat, and why it is immaterial here

The capture changed timestamp format partway through. Records up to line 18,983
use a space form (`2026-09-09 07:36:02`); from line 18,984 they use ISO-8601
with an explicit `Z` (`2026-09-09T21:05:49Z`). The `Z` form is UTC by
construction. **The space form's zone is UNMEASURED**, and the transition falls
between two different runs about 13.5 h apart, so the offset cannot be recovered
from the transition itself.

Milestone boundaries come from `git log -1 --format='%aI'` on each
`milestone/<name>^{commit}`, and are expressed here in UTC:

| Tag | Author time | UTC |
|---|---|---|
| `milestone/M5f` | 2026-08-26 11:38:02 +0600 | 2026-08-26 05:38:02Z |
| `milestone/M5g` | 2026-08-28 14:07:55 +0600 | 2026-08-28 08:07:55Z |
| `milestone/M5h` | 2026-09-12 01:37:17 +0600 | 2026-09-11 19:37:17Z |
| `milestone/M5i` | 2026-09-17 04:32:58 +0600 | 2026-09-16 22:32:58Z |

```bash
for t in M5f M5g M5h M5i; do
  git --no-pager log -1 --format='%ai' "milestone/$t^{commit}"
  git --no-pager log -1 --format='%aI' "milestone/$t^{commit}"
done
```

Both boundaries that fall inside the space-form region (M5f's and M5g's) sit far
from any run's first record. Interleaving each pid's first record with the four
boundaries shows the gaps:

```bash
awk 'match($0,/pid=[0-9]+/){ p=substr($0,RSTART+4,RLENGTH-4);
     t=substr($0,1,19); gsub(/T/," ",t); gsub(/Z/,"",t);
     if(!(p in f)) f[p]=t } END{ for(p in f) printf "PID %s %s\n", f[p], p }' "$LOG" | sort -k2,3
```

The nearest pid on either side of the M5g boundary
is 22484, first seen 2026-08-28 03:23:55, and 18552, first seen
2026-08-28 21:09:06 — **a minimum gap of 7 h 01 m**, which exceeds the largest
error a wrong timezone reading could introduce (6 h). The window assignment in
section 5 is therefore invariant under either reading of the space form.
DERIVED.

Both boundaries that fall inside the `Z` region (M5h's and M5i's) are compared
against timestamps that are UTC by construction, so no ambiguity arises there.

---

## 5. Per-milestone run census

```bash
awk 'match($0,/pid=[0-9]+/){ p=substr($0,RSTART+4,RLENGTH-4);
     t=substr($0,1,19); gsub(/T/," ",t); gsub(/Z/,"",t);
     if(!(p in f)) f[p]=t; n[p]++ } END{ for(p in f) print f[p]"|"p"|"n[p] }' "$LOG" \
| sort | awk -F'|' '
  { t=$1;p=$2;c=$3+0;
    if      (t < "2026-08-26 05:38:02") w="pre-M5f";
    else if (t < "2026-08-28 08:07:55") w="M5g";
    else if (t < "2026-09-11 19:37:17") w="M5h";
    else if (t < "2026-09-16 22:32:58") w="M5i";
    else                                 w="post-M5i";
    pid[w]++; if(c>=100){big[w]++; lst[w]=lst[w]" "p"("c")"} }
  END{split("pre-M5f M5g M5h M5i post-M5i",o," ");
      for(i=1;i<=5;i++){k=o[i];printf "%-9s pids=%-3d substantial=%-3d %s\n",k,pid[k]+0,big[k]+0,lst[k]}}'
```

A run is keyed by its pid and placed in the window containing its **first**
record. "Substantial" means 100 or more log lines, which separates a working
session from a boot that exited within seconds.

| Window | pids | substantial | the substantial runs (pid, lines) |
|---|---|---|---|
| pre-M5f | 0 | 0 | — (UNMEASURABLE, section 3) |
| **M5g** | 3 | **2** | `29608` (603), `12008` (531) — **LOWER BOUND** |
| **M5h** | 36 | **12** | `18552` (130), `23120` (202), `19112` (164), `27088` (147), `25700` (310), `27304` (485), `25916` (122), `3636` (354), `29776` (361), `6540` (519), `25800` (230), `7888` (300) |
| **M5i** | 6 | **3** | `28856` (134), `26952` (322), `13712` (425) |
| **post-M5i** | 2 | **1** | `7296` (345) |

OBSERVED. The four windows partition all 47 pids (3 + 36 + 6 + 2 = 47), so the
partition is exhaustive.

Nine of the 47 pids emitted only `probe_x1_*` events and are runs of
`scripts/probe_x1.py` rather than of the bot: `4900`, `5916`, `8620`, `9996`,
`16596`, `23604`, `31488`, `33076`, `44388`, each 3 lines. All nine fall in the
M5h window.

---

## 6. Per-window event counts

```bash
awk '{ t=substr($0,1,19); gsub(/T/," ",t); gsub(/Z/,"",t);
       if (t ~ /^2[0-9]{3}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$/) last=t; else t=last;
       if (t=="") next;
       if      (t < "2026-08-26 05:38:02") w="preM5f";
       else if (t < "2026-08-28 08:07:55") w="M5g";
       else if (t < "2026-09-11 19:37:17") w="M5h";
       else if (t < "2026-09-16 22:32:58") w="M5i";
       else                                 w="postM5i";
       if (match($0,/event=[a-z0-9_]+/)) { e=substr($0,RSTART+6,RLENGTH-6); c[w"|"e]++; tot[e]++ } }
 END{ for (k in c) { split(k,a,"|"); print a[1], a[2], c[k] } }' "$LOG"
```

The `last=t` carry-forward is load-bearing: a record whose body spans several
lines — an exception traceback — puts its `event=` token on a line that carries
no timestamp of its own. See section 13.

| event | preM5f | M5g | M5h | M5i | postM5i | TOTAL |
|---|---|---|---|---|---|---|
| `order_placed` | 0 | 3 | 44 | 21 | 14 | **82** |
| `close_booked` | 0 | 0 | 27 | 17 | 12 | **56** |
| `exit_booked` | 0 | 0 | 3 | 2 | 1 | **6** |
| `exit_book_refused` | 0 | 0 | 18 | 0 | 0 | **18** |
| `reconciliation_phase_failed` | 0 | 0 | 4 | 0 | 5 | **9** |
| `placement_ambiguous` | 0 | 1 | 0 | 0 | 0 | **1** |
| `placement_resolved` | 0 | 1 | 0 | 0 | 0 | **1** |
| `boot_symbol_blocked` | 0 | 0 | 12 | 1 | 1 | **14** |

OBSERVED. Each row's cells sum to its total, and each total matches the
whole-capture census below. That reconciliation is what surfaced the binner
defect recorded in section 13.

**Whole-capture event totals**, from a pattern that admits digits:

```bash
grep -oE 'event=[a-z0-9_]+' "$LOG" | sort | uniq -c | sort -rn
```

| count | event | | count | event |
|---|---|---|---|---|
| 3693 | `reconciliation_pass` | | 36 | `boot_assets_excluded` |
| 190 | `reconciliation_untrusted` | | 18 | `probe_x1_leg` |
| 177 | `intent_dispatched` | | 18 | `exit_book_refused` |
| 118 | `risk_refused` | | 14 | `boot_symbol_blocked` |
| 82 | `order_placed` | | 9 | `reconciliation_phase_failed` |
| 65 | `close_planned` | | 9 | `probe_x1_summary` |
| 56 | `close_window_open` | | 6 | `exit_booked` |
| 56 | `close_booked` | | 1 | `placement_resolved` |
| 36 | `dispatch_refused` | | 1 | `placement_ambiguous` |

OBSERVED. Eighteen distinct event names appear. The tree defines 33 event-name
constants under `src/`, so 17 of them are absent from the whole capture; the two
`probe_x1_*` names come from `scripts/probe_x1.py` rather than from `src/`.

---

## 7. The 2026-08-27 evidence

Two records, 60 seconds apart, both from `trading_bot.execution.executor`. They
are quoted in full because they are the only occurrence of either event name in
21,209 lines:

```
2026-08-27 04:06:02 | WARNING  | trading_bot.execution.executor | Placement outcome unknown; resolution deferred to the next bar event=placement_ambiguous symbol=BTCUSDT error_type=DuplicateOrderError error="Duplicate order sent." entry_bar_time=2026-08-26T22:05:59.999000+00:00

2026-08-27 04:07:02 | INFO     | trading_bot.execution.executor | Placement resolved event=placement_resolved symbol=BTCUSDT outcome=placed_live reason="tb1-BTCUSDT-1787781959999-0-L is working as order list 255471 (EXECUTING); at most one live list may hold an id, so this one is unambiguous among the 1 matched"
```

```bash
grep -nE 'event=placement_(ambiguous|resolved)' "$LOG"
```

An extract of the surrounding half hour was preserved out of tree as
`x3-evidence-2026-08-27T0350-0420.log`, 111,826 bytes, 561 lines, SHA-256
`CDCC6258383D21F323A2080704135A9519B39CB0F817A000880504B14084C2CD`, whose own
figures come from `wc -c`, `wc -l` and `sha256sum` on that extract.

Four independent properties bear on what produced these lines, each measured:

1. **One emitter each.** `_EVENT_AMBIGUOUS = "placement_ambiguous"` and
   `_EVENT_RESOLVED = "placement_resolved"` are defined at
   `src/trading_bot/execution/executor.py:148` and `:149`, and each is used at
   exactly one site — `:1171` and `:966` respectively.
2. **The resolved emitter sits downstream of a returned verdict.** Its `extra=`
   reads `verdict.outcome.value` and `verdict.reason`, and in that method
   `verdict` is bound at a single place, `verdict = await resolve_placement(...)`
   at `:802`, whose exception path performs `continue` rather than falling
   through.
3. **`resolve_placement` predates the lines by six days**, introduced by
   `3438180`, *"feat(execution): resolve a placement whose outcome we did not
   see"*, 2026-08-21 15:37:08 +0600.
4. **`scripts/probe_x1.py` did not yet exist**, having been introduced by
   `c5e54ce` on 2026-08-29 01:35:20 +0600, and it imports neither the executor
   nor the composition root.

The loggers present in the preserved half hour were
`trading_bot.engine.modes` (506 lines), `trading_bot.execution.reconciliation_driver`
(32), `trading_bot.engine.live_engine` (7), `trading_bot.main` (3),
`trading_bot.execution.executor` (3), `trading_bot.risk.manager` (2) and
`trading_bot.data.market_data` (2). OBSERVED.

---

## 8. What the census cannot see

- **Runs predating 2026-08-27 17:10:37Z.** 13,994 lines carry no process
  identifier, so the runs that wrote them cannot be counted or separated.
  M5g's figures are lower bounds and the M5d, M5e and M5f windows are blank for
  this reason rather than because they were quiet.
- **Runs whose records have rotated out.** The file rotates at 10 MiB with five
  backups. The capture is 3.9 MiB and no rotation had occurred by 2026-09-17,
  but a longer deployment discards the oldest records and a census taken then
  would report a clean early history because the evidence had gone.
- **Bare resting orders on unconfigured symbols — CLOSED at
  2026-09-17T19:00Z.** A venue read earlier that day covered order lists
  account-wide and open orders for BTCUSDT and ETHUSDT only, which left a single
  order resting on one of the other 499 held assets outside both instruments. A
  later read called `get_open_orders` with the symbol argument omitted — the
  account-wide form — and it returned **zero** resting orders:

  ```bash
  # BinanceClient.get_open_orders(symbol=None) omits the symbol parameter
  resting orders: 0
  ```

  The gap this bullet recorded was measured shut.
- **Partially locked assets.** The same read printed `locked` for three named
  assets and for a 20-row alphabetical sample. An asset holding both free and
  locked balance, outside that sample, is invisible to it. The account-wide
  count of fully-locked assets was 0, which bounds the fully-locked case and
  leaves the partial case open.

  **BOUNDED BY THE BULLET ABOVE UNDER ONE UNMEASURED PREMISE, AND NOT CLOSED.**
  If an asset's `locked` balance arises only from an order resting at the venue,
  then zero resting orders account-wide at 2026-09-17T19:00Z leaves nothing to
  reserve a balance, and the partial case is empty at that instant. **That
  premise is a statement about the venue and is measured nowhere in this tree**,
  and the reading that closed the bullet above read *orders*, not *balances*.
  Note also that the read this bullet describes is the earlier one; the
  account-wide order read came later the same day.

  **AND THE RECORDED CASE IS UNMEASURABLE IN RETROSPECT, WHICH IS STRONGER THAN
  UNMEASURED.** A `get_balances` read taken at any later date measures `locked`
  **at that later date**. What this bullet records is a blind spot at
  2026-09-17T19:00Z, and no present read is evidence about that instant: the
  balances have moved, and nothing in this tree preserved the per-asset `locked`
  column as it stood. So the direct instrument would settle the **current**
  state and cannot settle the **recorded** one. This bullet is not one
  derivation away from closure; it is closed to measurement altogether, and it
  stays open as the honest record of that.
- **Which leg of an order list filled.** Section 12.
- **What a run intended.** The log records what happened, and a record of why a
  run was started, by whom, and under what configuration exists nowhere the
  census reads.

---

## 9. Runs already recorded in commit bodies

A partial census of this kind already exists, scattered through commit messages,
and it stopped.

```bash
git --no-pager log --all --format='%B' > msgs.txt
grep -oE 'Run [0-9]+: pid [0-9]+' msgs.txt | sort -u
git --no-pager log --all --grep="Run [0-9]*: pid" --extended-regexp --format='%h %ai %s'
```

Commit `864259a`, *"docs: four lifecycles recovered, and an account that
reconciles to zero"* (2026-09-02 10:53:58 +0600), names three runs by pid:

```
Run 6: pid 23120
Run 7: pid 19112
Run 8: pid 22508
```

Comparing each of the capture's 47 pids against the whole commit-message corpus:

```bash
grep -oE 'pid=[0-9]+' "$LOG" | sed 's/pid=//' | sort -u > pids.txt
named=0; unnamed=0
for p in $(cat pids.txt); do
  if grep -qE "(^|[^0-9])$p([^0-9]|$)" msgs.txt; then named=$((named+1)); else unnamed=$((unnamed+1)); fi
done
echo "named=$named unnamed=$unnamed"
```

| Measure | Value | |
|---|---|---|
| distinct pids in the capture | 47 | OBSERVED |
| named in at least one commit body | 14 | OBSERVED |
| **named nowhere in git history** | **33** | OBSERVED |

The last enumeration of this kind covers a run that began 2026-09-01. Every run
after it — including all twelve substantial M5h runs, all three M5i runs and
both post-M5i runs — appears in no commit message.

**The instrument matters more than the number here.** A pattern matching
`pid=<digits>` returns 3 named and 44 unnamed; commit bodies write the form
`pid 19112` with a space, so that pattern reads a narrower property than the
question asks. The figures above come from a digit-bounded bare-number match,
and each of its 14 hits was inspected and found to be a genuine naming.

---

## 10. Reproduction

Every table above comes from one of the commands printed beside it, run against
the capture identified in section 2. The commands assume `$LOG` is set to that
file and use only `grep`, `awk`, `sed`, `sort`, `uniq`, `wc` and `git`.

A reader reproducing them starts by confirming the digest:

```bash
sha256sum "$LOG"   # 0E6B673E16671152A4E08CA6CC8390E7B72EA8B75C3E7303FA0C16B4E04D223E
wc -c < "$LOG"     # 4089853
wc -l < "$LOG"     # 21209
```

A different digest gives a different file, and the tables above describe the
file named in section 2 alone.

---

## 11. The 2026-09-17 run and its close-out

Two runs began after M5i's closing commit (2026-09-16 22:32:58Z).

| | `pid=23348` | `pid=7296` |
|---|---|---|
| first record | 2026-09-17T07:53:33Z | 2026-09-17T10:15:46Z |
| last record | 2026-09-17T10:03:55Z | 2026-09-17T18:55:47Z |
| span | 2 h 10 m 22 s | **8 h 40 m 01 s** |
| lines | 77 | 345 |
| stop reason | `Received SIGINT; shutting down gracefully`, then `Trading engine stopped` | same pair, 1 second apart |

OBSERVED. Both runs ended on a signal rather than on a fault, and both terminator
lines are present for each.

```
2026-09-17T18:55:46Z | INFO | pid=7296 | __main__                       | Received SIGINT; shutting down gracefully
2026-09-17T18:55:47Z | INFO | pid=7296 | trading_bot.engine.live_engine | Trading engine stopped
```

**At boot, `pid=23348` refused to trade one of its configured symbols**, naming
an order list from the preceding run:

```
2026-09-17T07:53:41Z | ERROR | pid=23348 | trading_bot.engine.modes | ETHUSDT is BLOCKED: a live order list of ours is working at the venue event=boot_symbol_blocked symbol=ETHUSDT order_list_id=137501 list_client_order_id=tb1-ETHUSDT-1789603799999-0-L list_order_status=EXECUTING
```

`pid=7296`, booting at 10:15:55Z, emitted no such line, so list 137501 had left
a live status between those two boots. Section 12 records what is known and
unknown about it.

### The day's trading

```bash
grep -E '^2026-09-17T' "$LOG" | grep -c 'event=order_placed'
grep -E '^2026-09-17T' "$LOG" | grep -E 'event=(close_booked|exit_booked)' \
  | grep -oE 'realised=-?[0-9.]+' | sed 's/realised=//' \
  | awk '{s+=$1; n++} END{printf "n=%d  sum=%.10f\n", n, s}'
```

| Measure | Value | |
|---|---|---|
| placements dated 2026-09-17 | 13 | OBSERVED |
| bookings dated 2026-09-17 | 13 | OBSERVED |
| of those, the bot's own CLOSE sequence (`close_booked`) | 12 | OBSERVED |
| of those, venue-triggered protective fills (`exit_booked`) | **1** | OBSERVED |

The thirteen booked figures, in order:

| time | event | symbol | realised |
|---|---|---|---|
| 00:59:03Z | `close_booked` | BTCUSDT | `+12.0990515000` |
| 02:01:02Z | `close_booked` | BTCUSDT | `-6.6394436000` |
| 03:58:03Z | `close_booked` | BTCUSDT | `-0.3781562000` |
| 08:49:02Z | `close_booked` | BTCUSDT | `-0.0444096000` |
| 09:48:03Z | `close_booked` | BTCUSDT | `+2.1219380000` |
| 11:36:03Z | `close_booked` | BTCUSDT | `-2.986832000` |
| **12:33:01Z** | **`exit_booked`** | BTCUSDT | **`-45.3230836000`** |
| 13:05:02Z | `close_booked` | BTCUSDT | `-0.3928204000` |
| 14:51:03Z | `close_booked` | BTCUSDT | `+1.9167894000` |
| 16:26:02Z | `close_booked` | BTCUSDT | `+2.3790460000` |
| 17:49:02Z | `close_booked` | BTCUSDT | `-5.672835000` |
| 18:42:03Z | `close_booked` | BTCUSDT | `-4.1372898000` |
| 18:45:02Z | `close_booked` | ETHUSDT | `-11.5669810000` |

Their sum is `-58.6250263000` over 13 records. OBSERVED.

`data/state.json`, captured at 2026-09-17T18:58:51Z
(587 bytes, SHA-256
`8AFF1EB6E82369C92112A17DB73767890F43DE235814BC3DBFFBF7EF01CCBD37`), held:

```json
"ledger": { "pnl_date": "2026-09-17", "realised_pnl": "-58.6250263000", "trades_count": 13 }
```

**The log's thirteen per-booking fields and the persisted ledger agree to the
last digit, on both the total and the count.** They are independent instruments
and disagreement was available on every record. OBSERVED.

The final two bookings closed both positions the run was holding, so the run
ended flat by its own action rather than by intervention.

### The venue, read once at ~19:00Z

```bash
.venv/Scripts/python.exe scripts/check_testnet.py   # testnet by default
```

A read-only connectivity check (`scripts/check_testnet.py`, whose venue calls
are `ping`, `get_balances`, `get_ticker`, `get_symbol_info`, `get_open_orders`
and `get_all_order_lists`) reported:

| Measure | Value |
|---|---|
| BTC | free `0E-8`, locked `0E-8`, total `0E-8` |
| ETH | free `0E-8`, locked `0E-8`, total `0E-8` |
| USDT | free `90335.58219840` |
| assets with a non-zero balance | 500 |
| of those, fully locked (`free` exactly zero) | **0** |
| open orders, BTCUSDT | **0** |
| open orders, ETHUSDT | **0** |
| order lists on the account | **43** |
| of those, `ALL_DONE` | **43** |
| of those, outside a terminal status | **0** |

OBSERVED. The account was flat.

### The 43-against-43 reconciliation

The venue's order-list id space reset during the observation period: the log
shows ids climbing to `484960` on 2026-09-09 06:06:01 and then restarting at
`8294` on 2026-09-09T22:40:02Z. `get_all_order_lists` returns lists since that
reset, which accounts for the gap between 82 lifetime placements and 43 lists on
the account.

```bash
awk '$1>="2026-09-09T22:40"' "$LOG" | grep 'event=order_placed' \
  | grep -oE 'order_list_id=[0-9]+' | sort -u | wc -l
```

| Measure | Value | |
|---|---|---|
| distinct list ids in the log at or after the reset | **43** | OBSERVED |
| order lists the venue reported | **43** | OBSERVED |
| lists the venue showed as live | 0 | OBSERVED |
| lists in the log that the venue did not hold | 0 | DERIVED |
| lists at the venue that the log did not explain | 0 | DERIVED |

The 43 ids, ascending: `8294 8760 9936 10645 12313 12934 26590 27053 83587
83797 85355 85901 87096 119335 119822 120493 121803 122743 122870 123832 124521
125335 125398 125457 134254 134506 134858 135272 136112 137078 137501 138136
138727 142291 142467 143866 144448 144754 145043 146039 147648 150303 152132`.

**A second cross-check over an interval whose ends were both observed.** An
earlier venue read at ~06:30Z on the same day reported **33** order lists. The
log records exactly **10** placements between that read and the later one. The
later read reported **43**. `33 + 10 = 43`. Disagreement was available and did
not occur. DERIVED.

---

## 12. The unsettled leg of order list 137501

**The indeterminacy is the finding.** What follows records the bound and the
instrument that would close it; it takes no position on which leg filled.

### What the log holds

Two records in 21,209 lines name this list:

```
2026-09-17T00:10:02Z | INFO  | pid=13712 | trading_bot.execution.executor | Order list placed event=order_placed symbol=ETHUSDT quantity=0.74550000 entry=2424.85000000 stop_loss=2376.36000000 order_list_id=137501 list_client_order_id=tb1-ETHUSDT-1789603799999-0-L entry_bar_time=2026-09-17T00:09:59.999000+00:00

2026-09-17T07:53:41Z | ERROR | pid=23348 | trading_bot.engine.modes | ETHUSDT is BLOCKED: a live order list of ours is working at the venue event=boot_symbol_blocked symbol=ETHUSDT order_list_id=137501 list_client_order_id=tb1-ETHUSDT-1789603799999-0-L list_order_status=EXECUTING
```

The take-profit trigger appears one second before the placement, on the risk
manager's own line:

```
2026-09-17T00:10:01Z | INFO | pid=13712 | trading_bot.risk.manager | Risk approved ETHUSDT: 0.74550000 at 2424.85000000 (LONG @ 2424.85000000: stop-loss percent 2376.36000000, take-profit percent 2521.84000000)
```

| Field | Value | |
|---|---|---|
| quantity | `0.74550000` | OBSERVED |
| entry limit | `2424.85000000` | OBSERVED |
| stop-loss trigger | `2376.36000000` | OBSERVED |
| take-profit trigger | `2521.84000000` | OBSERVED |
| live at | 2026-09-17T07:53:41Z | OBSERVED |
| absent from the boot check at | 2026-09-17T10:15:55Z | OBSERVED |

Both triggers reconcile against `config.yaml` (`stop_loss.percent: 2.0`,
`take_profit.percent: 4.0`) applied to the entry limit and rounded toward the
reference: `2424.85 x 0.98 = 2376.353` and `2424.85 x 1.04 = 2521.844`. The
sibling position placed later the same day reconciles the same way
(`2474.29 x 0.98 -> 2424.81`, `2474.29 x 1.04 -> 2573.26`), which is a second
confirmation of the model. DERIVED.

### The bound

`Portfolio._realised_from_total` computes, for a long, `realised = gross −
entry_fill_price x quantity`. `entry_fill_price` was not logged; back-solving
the same day's completed trades as `(quote_total − realised) / quantity`:

```bash
awk '/event=order_placed/ && /symbol=BTCUSDT/ && /^2026-09-17T/ {
       match($0,/quantity=[0-9.]+/); q=substr($0,RSTART+9,RLENGTH-9);
       match($0,/ entry=[0-9.]+/);  e=substr($0,RSTART+7,RLENGTH-7);
       n++; Q[n]=q+0; E[n]=e+0; next }
     /event=close_booked/ && /^2026-09-17T/ {
       match($0,/quote_total=[0-9.]+/); t=substr($0,RSTART+12,RLENGTH-12);
       match($0,/realised=-?[0-9.]+/);  r=substr($0,RSTART+9,RLENGTH-9);
       m++; T[m]=t+0; R[m]=r+0; next }
     END{ for(i=1;i<=m && i<=n;i++) printf "fill/limit=%.6f\n", ((T[i]-R[i])/Q[i])/E[i] }' "$LOG"
```

gives
`fill / limit = 0.999001` on five records, matching
`max_entry_slippage: 0.001`, so `entry_fill_price ≈ 2424.85 / 1.001 ≈
2422.4276` and the cost basis is `≈ 1805.92`.

That command pairs placements to closes by position, and one of the day's exits
was an `exit_booked` rather than a `close_booked`, which shifts the pairing and
produces two rows (`1.019552`, `0.979177`) that are artefacts of the pairing
rather than measurements. The figure above rests on the five consistent rows
only.

| Hypothesis | gross | realised |
|---|---|---|
| the stop leg filled | `2376.36 x 0.74550 ≈ 1771.58` | **`≈ −34.34`** |
| the take-profit leg filled | `2521.84 x 0.74550 ≈ 1880.03` | **`≈ +74.11`** |

DERIVED, and both figures are computed from *triggers* rather than from fills. A
stop-market order fills at whatever the book offers; a comparable divergence of
about 1 USDT was measured on an earlier trade, so each figure carries roughly
that uncertainty.

**The spread is ≈ 108.45 USDT.** Today's persisted `realised_pnl` of
`-58.6250263000` omits this trade entirely, as does `lifetime_realised`
(`-209.601849800000000000000000`, which equals the sum of the four days in
`daily_history` and excludes the open day).

### Why the log cannot settle it

Searching the capture for an ETHUSDT price observation between 07:53:41Z and
10:15:56Z returns two `Seeded ETHUSDT/5m with 499 closed candle(s)` lines and
two engine-started lines, none carrying a price. The one bracketing figure is
that at 12:30:00Z the ETHUSDT reference was `2474.29`, above the entry and below
the take-profit, which is consistent with either hypothesis. **Nothing in the
capture discriminates the two legs.** OBSERVED.

The venue read described in section 11 also leaves it open:
`get_all_order_lists` returns a list-level status and carries no per-order
status, executed quantity or price, and the script prints per-list detail only
for lists outside a terminal status, so list 137501 appears in that output only
as one of 43 counted `ALL_DONE` rows.

### What would settle it

`ExchangeClient.get_order(symbol, *, order_id=None, client_order_id=None, ...)`
is a point query and a read. Its docstring records the property that makes it the
right instrument:

> **A POINT QUERY IS A DIFFERENT INSTRUMENT FROM ENUMERATION**, and a
> reconciler needs both. MEASURED: immediately after a cancel,
> `get_own_open_orders` returned nothing while this endpoint still reported the
> order as `CANCELED`. Absence from an enumeration says only "it does not rest";
> never-placed, cancelled and filled are indistinguishable from there, and only
> this separates them.

The two identifiers it would take are derivable by computation from the client
id root already in the log: `tb1-ETHUSDT-1789603799999-0-SL` and
`tb1-ETHUSDT-1789603799999-0-TP`.

Two tracked scripts reach that method. `scripts/cancel_testnet_order_list.py`
calls it, and that script also cancels. `scripts/probe_x1.py` calls it and is
read-only against the venue, while writing to `logs/trading_bot.log` through the
bot's own `setup_logging`, which would extend the artefact this file describes.

**As of 2026-09-17T19:00Z the leg was unsettled, and the decision about
settling it was reserved to the project owner.**

---

## 13. Instrument defects recorded during this measurement

Each of these produced a wrong figure that looked like a right one. They are
recorded because the defect generalises further than the number it spoiled.

**1. A timestamp prefix read as a timestamp on every line.** A window filter of
the shape `substr($0,1,20) > "2026-09-17T04:08:58Z"` treats the first 20
characters of every line as a timestamp. On a traceback continuation line those
characters are source text such as `trading_bot.core.exc`, which compares
greater than any digit string, so **every multi-line record in the whole file
passed the filter** regardless of its date. It read *"does this line's first 20
characters sort after the boundary"* where the question was *"was this record
written after the boundary"*. It reported 9 `reconciliation_phase_failed`
records in a window holding 5. Caught by reconciling per-window row sums against
the whole-capture totals, which disagreed. The remedy is the `last=t`
carry-forward in section 6.

**2. An event pattern that excluded digits.** `grep -oE 'event=[a-z_]+'`
truncates `probe_x1_leg` and `probe_x1_summary` at the digit, fabricating a
single event name `probe_x` with a count of 27 that no emitter produces. It read
*"the longest run of lowercase letters and underscores after `event=`"* where the
question was *"the event name"*. Caught by comparing the distinct-name set from
that pattern against one from `[a-z0-9_]+`. Every other event name in the tree is
digit-free, so no other count was affected.

**3. Searches for an enum's member NAME where the log carries its `.value`.**
The tree defines 18 enums with 82 members, and 12 of those enums have a value
that differs from the member name. `CloseAction.ALREADY_CLOSED` reaches the log
as `already_closed`; `OrderListLeg.TAKE_PROFIT` reaches it as `TP`. A
case-sensitive search for `ALREADY_CLOSED` returns 0 over the whole capture while
the value occurs; a search for `TAKE_PROFIT` finds `OrderType.TAKE_PROFIT` text
and cannot reach a leg label at all. It read *"does this identifier appear"* where
the question was *"did this condition occur"*. Caught by censusing every enum
member's value from source and re-running each search against the value column.
A sweep of every emission site in `src/` found that the tree itself passes
`.value` at every site, so the defect lived in the searches rather than in the
code.

**4. Window boundaries at date granularity.** Cutting windows on the first ten
characters of a timestamp places a run that began seven hours after a tag in the
window the tag closed. It read *"which calendar day"* where the question was
*"which side of this commit"*. Caught by interleaving each pid's first timestamp
with the four boundaries and reading the gaps.

**5. Window boundaries in the wrong timezone.** Milestone tags carry `+0600`
author times; recent log records carry UTC. Comparing one against the other
without conversion moved 4 placements and 3 closes from the post-M5i window into
M5i. It read *"is this local-clock string less than that local-clock string"*
where the question was *"which happened first"*. Caught by re-running the census
with `git log --format='%aI'` converted to UTC and observing that cells moved
while totals held. Section 6's table uses the converted boundaries.

**6. A numeric pattern over a field whose values were not uniformly numeric.**
Extracting
`order_list_id=[0-9]+` returned 81 distinct values across 82 placement records,
which reads as a duplicated id. The oldest record predates commit `3970968` and
carries a client order id under that key, so the pattern skipped it. It read
*"digits following the key"* where the question was *"the value of the key"*.
Caught by locating the supposed duplicate and finding a schema change instead.

**The property they share** is that each returned a plausible number from a
pattern that read something adjacent to the question, and each was caught by a
second derivation that could have disagreed. Four of the six were caught by a
reconciliation rather than by inspection; two were caught by a prediction that
the output contradicted. None was caught by reading the command.

---

## 14. Order list 137501 settled: neither leg filled

Section 12 records the leg as unsettled as of 2026-09-17T19:00Z. That sentence
is true at its stated time and is left exactly as it stands. This section is an
addition beside it, not a correction of it: a later read-only settlement was
taken, and what follows is what it observed.

### What the capture shows, and what it cannot

The list is named in **2** of the capture's 21,209 lines — the placement at
`2026-09-17T00:10:02Z` and the boot block at `2026-09-17T07:53:41Z`, both
already quoted in section 12. Nothing else in the file names it.

The capture does, however, bracket the interval, and that is new here:

| Observation | Value |
|---|---|
| last record of `pid=23348` | `2026-09-17T10:03:55Z`, `Trading engine stopped` |
| first record of `pid=7296` | `2026-09-17T10:15:46Z` |
| records stamped between those two | **0** |

**No bot process was running between those stamps.** The silence across the
interval is therefore not a logging gap within a live run; there was no run.
OBSERVED.

```bash
grep -c '^2026-09-17T10:' "$LOG"          # 10
grep -n  '^2026-09-17T10:' "$LOG"         # 10:03:53, 10:03:55, then 10:15:46 onward
grep -n  '137501' "$LOG"                  # 2 records
```

A second, independent capture-side observation bears on the same interval. The
boot at `2026-09-17T07:53:41Z` emitted `event=boot_symbol_blocked symbol=ETHUSDT
order_list_id=137501`. The next boot, whose composition root reported ready at
`2026-09-17T10:15:55Z`, emitted **no** `boot_symbol_blocked` for ETHUSDT. The
list was no longer live at that second boot. OBSERVED.

### What the settlement read observed

The settlement was a read-only venue query recorded in commit
`0992fa33fa929c70df3f6a9b502aa8ca8327022c`, whose body is the source for the
lines below and can be re-read with `git log -1 0992fa3`:

| Observation | Value |
|---|---|
| both protective legs | `CANCELED`, `executedQty` zero |
| cancelled at | `2026-09-17T10:15:06.904Z` |
| the position's close | a `MARKET` sell, `9.345 s` later |
| that order's `orderListId` | `-1` — outside any list |
| that order's client id | outside `exchange/ids.py`'s scheme |
| commission, both trades | `0.00000000` |

**NEITHER LEG FILLED.** The take-profit leg reached `CANCELED` having executed
nothing, and so did the stop leg.

### Figures deliberately omitted

The realised figure for this position, the exit order's numeric id, its client
order id as a string, the entry fill price and both quote totals were observed
during the settlement read. **They are not restated here, because none of them
can be re-derived from the capture this file is built on or from any tracked
file** — the capture holds no record of the interval, and no tracked file holds
the venue response. Recording a number this file cannot reproduce would break
the property stated in section 10, that every figure comes from a command
printed beside it.

### What this bears on

**Section 8's bullet *"Which leg of an order list filled"* is answered for this
list: neither did.** That bullet is left standing, unedited, as a true record of
what the census could see — the census still cannot see which leg of a list
filled, and it took a venue read rather than the log to settle this one.

**The bound stated in finding `M5j-007` is falsified.** That finding bounded the
list's realised figure at one of two values, on an enumeration with exactly two
members: the stop leg filled, or the take-profit leg filled. Neither did. The
outcome fell outside the enumerated set rather than at an unexpected point
inside it, so the bound fails by its hypothesis space and not by its arithmetic.
The finding is left exactly as written; this section neither edits nor amends
it.

**Finding `M5j-008` asked which leg filled and marked itself UNMEASURED.** The
question carries a false presupposition — that one of the two legs filled — so
it has no answer rather than an unmeasured one.

### Attribution

**Who ran the cancel and the sell is unrecorded in this tree.** The orders
carry no identifier this repository issued, and the interval holds no log line
because no bot process was running. This file names no actor and takes no
position on which one acted.

---

## 15. A take-profit leg filled, on 2026-09-18

Sections 1 to 14 were derived from the capture section 2 identifies. This
section is derived from a **later, larger capture**, identified here in full,
and the two are continuous.

### The capture

| Property | Value |
|---|---|
| path | `F:\trading bot\files\binance-trading-bot\m5j-evidence\trading_bot.x1-20260918T175500Z.log` |
| taken | 2026-09-18T17:55Z, **while a writer held the file** |
| bytes | 4,180,801 |
| lines | 21,781 |
| **SHA-256** | **`bbdeb1787ac0caf5782229391ef6cf5931a046193d8b6fef078ef3941121e182`** |

**The read was share-mode.** The source was opened `FileMode::Open`,
`FileAccess::Read`, `FileShare::ReadWrite`, so the running writer kept its
handle throughout; the source was left unmoved, untruncated, unrenamed and
unlocked. A digest identifies this capture rather than `logs/trading_bot.log`,
which had already grown by the time the digest was taken.

### Continuity with section 2

The capture section 2 names is a **byte-exact prefix** of this one:

```bash
head -c 4089853 "$NEW" | sha256sum
  # 0e6b673e16671152a4e08ca6cc8390e7b72ea8b75c3e7303fa0c16b4e04d223e
sha256sum "$OLD"
  # 0e6b673e16671152a4e08ca6cc8390e7b72ea8b75c3e7303fa0c16b4e04d223e
```

Identical, so no rotation and no truncation intervened, and `logs/` held no
rotated sibling. This capture adds 90,948 bytes and 572 lines on top of it.
OBSERVED.

### The lifecycle

| Observation | Value |
|---|---|
| placed | `2026-09-18T13:29:02Z` |
| `order_list_id` | `171948` |
| `list_client_order_id` | `tb1-BTCUSDT-1789738139999-0-L` |
| `entry_bar_time` | `2026-09-18T13:28:59.999000+00:00` |
| quantity | `0.02308000` |
| entry | `78253.23000000` |
| stop-loss trigger | `76688.17000000` |
| discovered | `2026-09-18T15:21:02Z` |
| exit `order_id` | `3612839` |
| `quote_total` | `1867.31048000` |
| `realised` | `63.0300952000` |

The classifier resolved the two protective legs differently in the same pass:
the `SL` leg reported `EXPIRED` and did not rest, and the `TP` leg reported
`FILLED` with `0.02308000` executed.

**The leg was this bot's own.** `ProtectionState.ACTIVE` is returned only when
each leg's client order id equals the one `exchange/ids.py` derives, so the
passes reporting `active` up to 15:19:03Z establish it, and the point query
that found the fill was keyed on that same derived id. MEASURED. No actor
outside this repository is implicated, and none is named.

### The detection window

| Observation | Value |
|---|---|
| last pass reporting `active` | `2026-09-18T15:19:03Z` |
| pass that discovered the fill | `2026-09-18T15:21:02Z` |
| interval | **119 seconds** |

A leg resting in the open-orders enumeration has not filled, so the fill fell
inside that interval and was found by the next pass.

### `venue_time` is the leg's creation time

The `exit_booked` line carries `venue_time=2026-09-18T13:29:00.594000+00:00`.
**That is `order.created_at`, and it is not the fill time.** The arithmetic
settles it without appeal to the code: the value precedes this repository's own
placement line at `13:29:02Z` by 1.4 seconds, and a fill cannot precede the
placement that created the order.

**The fill time is UNMEASURED.** The capture bounds it to the 119-second window
above and holds nothing finer. An interval computed from `venue_time` to the
booking measures the position's lifetime rather than any latency.

### The realised figure is GROSS

`realised=63.0300952000` was booked with `fee` at `Decimal(0)`, because the
venue's commission does not reach the ledger: `to_order` reads 16 distinct wire
keys and `fills` is not among them, so the figure the venue reported is
discarded at the mapper. What the commission was on this trade is unmeasured
here, and no figure for it is stated.

### What this section is

An observation, in the shape of every section above it. Checked against the
banner in section 1 — *"**This file asserts no rule.** Rules for this project
live in `CLAUDE.md`, and a reader looking for one is served by going there
rather than by reading anything here as prescriptive."* Nothing above
prescribes anything; the sentences are past-tense statements about bytes that
existed at a stated time with a stated digest.

## 16. The capture M5j's rotation read, recorded at M5k's

Sections 16 to 19 were added at M5k's rotation. Every capture named in them is
in `F:\trading bot\files\binance-trading-bot\m5j-evidence`, outside the
repository, and every figure is a `grep -c` over the capture it names unless
the sentence says otherwise.

**The scope sentences at the top of this file describe sections 1 to 14.**
Section 1's *"between 2026-07-23 and 2026-09-17"* and section 2's *"Every
figure below was derived from a single frozen capture"* were true of those
sections when written. Section 15 and these four each name their own capture,
and together they carry the record to `2026-09-25T16:16:10Z`. This is added
rather than written into sections 1 and 2, because this file is added to and
never annotated.

### The capture

| Property | Value |
|---|---|
| file | `trading_bot.m5k-20260919T000000Z.log` |
| bytes | 4,252,169 |
| lines | 22,127 |
| **SHA-256** | **`bfc8ffddc494f288e710df00918507c7027bcfe538096def4d32172ed2af8d3d`** |

`docs/NEXT_MILESTONE.md`, `docs/QB_ESCALATION.md`, `docs/QC_PROTECTIVE_ORDERS.md`
and `CLAUDE.md` all cite this digest as the capture M5j's rotation measured
against. Until this section this file did not name it.

### Continuity

The capture section 15 names is a byte-exact prefix of this one:
`head -c 4180801` of `trading_bot.m5k-20260919T000000Z.log` hashes to
`bbdeb1787ac0caf5782229391ef6cf5931a046193d8b6fef078ef3941121e182`. This
capture adds **71,368 bytes and 346 lines**. OBSERVED.

### What the added bytes hold

One pid, the run section 15 described as in flight:

| pid | first line | last line | lines | `engine_stopped` |
|---|---|---|---:|---:|
| 24772 | `2026-09-18T17:56:00Z` | `2026-09-19T04:01:01Z` | 346 | 0 |

In the added bytes: 6 `order_placed`, 6 `close_planned` (all 6
`decision=sell`), 6 `close_booked`, 0 `exit_booked`, 0 `decision=halt`, 0
`stage=position_stale`, 0 `collaborator_failed`, 0
`reconciliation_phase_failed`, 0 `diverged=1`, 0 `exit_book_refused`.

### Whole-capture figures, with this digest

94 `order_placed`; 75 `close_planned`, of which 74 `decision=sell`, 1
`decision=already_closed` and **0 `decision=halt`**; 66 `close_booked` and 7
`exit_booked`; 18 `exit_book_refused`; 11 `reconciliation_phase_failed`; 28
`diverged=1`; 0 `engine_stopped`; 0 `stage=position_stale`; 0
`collaborator_failed`. A search for the literal `leg TP reports FILLED` returns
**1** line and `leg SL reports FILLED` returns **144**. The second is not the
figure `162` quoted elsewhere for filled `SL` clauses: that one was counted
over both of the classifier's clause forms, and this is one form only.

### An earlier capture this file never named

`trading_bot.live-20260917T182829Z.log`, 4,084,785 bytes, SHA-256
`d0219fb3cecc9e9280b6df780b1d2b27331da3a61694cbfbc18dfe381a2bece4`, is a
byte-exact prefix of the capture section 2 names: `head -c 4084785` of
`trading_bot.final-20260917T185851Z.log` hashes to its digest. It holds no byte
that capture does not, so it adds no observation; it is named so the evidence
directory has no unrecorded log. OBSERVED.

## 17. The capture of 2026-09-23

### The capture

| Property | Value |
|---|---|
| file | `trading_bot.p2a5-20260923T064334Z.log` |
| bytes | 4,885,745 |
| lines | 25,202 |
| **SHA-256** | **`e747b3e80ce3be4f76da41da7262ef19adacfc3c34b0fcb739b4055dc44c2589`** |

M5k's commit bodies and `CLAUDE.md`'s protective-orders section cite this
digest. Until this section this file did not name it.

### Continuity

`head -c 4252169` of this capture hashes to
`bfc8ffddc494f288e710df00918507c7027bcfe538096def4d32172ed2af8d3d`, so the
capture section 16 names is a byte-exact prefix. This one adds **633,576 bytes
and 3,075 lines**. OBSERVED.

### The runs in the added bytes

| pid | first line | last line | lines | `engine_stopped` |
|---|---|---|---:|---:|
| 24772 | `2026-09-19T04:03:00Z` | `2026-09-19T09:42:02Z` | 235 | 0 |
| 25080 | `2026-09-19T13:43:57Z` | `2026-09-19T22:26:46Z` | 275 | 1 |
| 16216 | `2026-09-20T00:02:56Z` | `2026-09-22T04:36:00Z` | 1,940 | 1 |
| 20408 | `2026-09-22T17:24:32Z` | `2026-09-23T06:20:02Z` | 525 | 0 |

**Why pid 24772 ended without `engine_stopped` is not established.** Its last
line is at `09:42:02Z` and nothing after it names that pid. The process began
before the commit that added the marker, as `docs/NEXT_MILESTONE.md` recorded at
M5j, which accounts for the absence of the marker and says nothing about how
the process ended.

**Pid 20408 had not logged `engine_stopped` when this capture was taken.**
Section 19 shows it did so at `06:55:21Z`, after a `SIGINT`, twelve minutes
after this capture's instant.

**The commit deployed for any of these runs is not established.** Nothing in a
log line names a commit.

### Counts in the added bytes

69 `order_placed`; 67 `close_planned`, all 67 `decision=sell`; 67
`close_booked`; 3 `exit_booked`; 1 `reconciliation_phase_failed`; 0
`decision=halt`; 0 `stage=position_stale`; 0 `collaborator_failed`; 0 new
`exit_book_refused`; 0 new `diverged=1`. `leg TP reports FILLED` rises from 1
line to **3**, and `leg SL reports FILLED` from 144 to 145.

The three `exit_booked` lines:

| time | pid | symbol | `order_id` | `quote_total` | `realised` |
|---|---|---|---|---|---|
| `2026-09-19T07:15:01Z` | 24772 | ETHUSDT | 3281823 | `1907.84362700` | `100.8738890000` |
| `2026-09-20T15:30:01Z` | 16216 | BTCUSDT | 4293356 | `1727.82571360` | `-80.39116640` |
| `2026-09-21T09:40:01Z` | 16216 | BTCUSDT | 4559541 | `1882.62346720` | `75.164021600000000000000000` |

**Order 4559541's `realised` carries exponent -24**, where the other two carry
-10 and -8. Its cause is UNMEASURED. It is not unique: the same exponent occurs
on three other booking lines across the capture chain, and section 19 lists all
four against the newest capture.

### Whole-capture figures, with this digest

163 `order_placed`; 142 `close_planned`, of which 141 `decision=sell`, 1
`decision=already_closed` and **0 `decision=halt`**; 133 `close_booked` and 10
`exit_booked`; 18 `exit_book_refused`; 12 `reconciliation_phase_failed`; 28
`diverged=1`; 2 `engine_stopped`; 0 `stage=position_stale`; 0
`collaborator_failed`. `scripts/run_census.py` over this capture reports 51
distinct pids, 22 substantial.

### Order 300642, recorded nowhere in the tree until now

Every one of the capture's **18** `exit_book_refused` lines names ETHUSDT and
`order_id=300642`, all written by `pid=7888` between `2026-09-10T03:36:02Z` and
`04:03:02Z`, each giving the reason *"the fill is partial -- 0.36230000
executed against a position of 0.73290000 -- so it is not booked and the
position keeps its untrusted protection"*. The reconciliation line of the first
such pass reads *"ETHUSDT leg SL reports EXPIRED with 0.36230000 executed"*, and
its `TP` sibling *"was requested and does not rest: the point query reports
EXPIRED"*. The same 18 lines are in section 2's capture.

**What order 300642 was is not established.** No line carries the leg's
`origQty`, so the capture cannot say whether the stop-loss leg was sized at the
position and executed half of it, or was sized at the executed figure. No
ETHUSDT `myTrades` capture exists. `docs/QC_PROTECTIVE_ORDERS.md` §10 carries
the same observation against its unmeasured pending-leg partial fill.

## 18. The two `myTrades` captures

These are JSON reads of the venue's own trade records, not log captures. They
are recorded here because they measure things this file had left open.

### `my_trades_btcusdt.json`

| Property | Value |
|---|---|
| bytes | 106,307 |
| **SHA-256** | **`111d1c15a3c5fff56148f172bfbcbec85baf5aabe2128f34fb622cafe5463970`** |
| file modified | `2026-09-23T11:31:55Z` |
| records | 306, every one BTCUSDT, one key set of 13 keys |
| fill times | `2026-09-09T21:05:39.248Z` to `2026-09-23T11:17:01.969Z` |
| orders | 215 distinct, 11 with more than one fill |
| commission asset | `BTC` on 128 of 128 buyer fills; `USDT` on 178 of 178 seller fills |
| commission | `0.00000000` on all 306 |

How and when the venue was read is not recorded in the file; the modification
time is the filesystem's, and M5k's commit bodies are what cite the digest.

**It settles section 15's unmeasured fill time.** Order 3612839 appears once:
`orderListId` 171948, a seller fill, `price` `80906.00000000`, `qty`
`0.02308000`, `quoteQty` `1867.31048000`, `commission` `0.00000000` `USDT`,
`time` `1789744858864`, which is **`2026-09-18T15:20:58.864Z`**. Section 15
bounded the fill to the 119 seconds between the last pass reporting `active` at
`15:19:03Z` and the pass that found it at `15:21:02Z`, and called the time
UNMEASURED. It is now measured, and the fill fell **3.136 seconds** before the
pass that discovered it. The quote quantity equals section 15's `quote_total`.
And because the commission was zero, section 15's `realised=63.0300952000`,
booked GROSS, is also the net figure for that trade. Section 15 stays as
written: it recorded what the log held.

### `my_trades_btcusdt_order_4293356.json`

| Property | Value |
|---|---|
| bytes | 8,027 |
| **SHA-256** | **`b02a4ef6385f0c188496f265ba487302bb15929dc9061077e741ac3977062a1b`** |
| file modified | `2026-09-23T17:14:56Z` |
| records | 23, all order 4293356, all BTCUSDT seller fills |
| fill time | `2026-09-20T15:29:11.293Z` on all 23 |
| commission | `0.00000000` `USDT` on all 23 |
| summed `qty` | `0.02243000` |
| summed `quoteQty` | `1727.82571360` |

The summed quote quantity equals, by value and by exponent, the `quote_total`
of the `exit_booked` line section 17 lists for this order at
`2026-09-20T15:30:01Z`. The same 23 fills are present in the 306-record capture
above.

## 19. The capture taken at M5k's close

### The capture

| Property | Value |
|---|---|
| file | `trading_bot.m5k-close-20260925T182818Z.log` |
| taken | `2026-09-25T18:28:18Z` |
| bytes | 5,074,996 |
| lines | 26,126 |
| **SHA-256** | **`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`** |

**The read was share-mode**, like section 15's: the source was opened
`FileMode.Open`, `FileAccess.Read`, `FileShare.ReadWrite`, and copied whole.
Nothing was written to it, truncated or moved. The source,
`logs/trading_bot.log`, was last modified at `2026-09-25T16:16:10Z` by the
filesystem's own time, and its size was 5,074,996 bytes both at an earlier
metadata read during M5k's rotation and at the copy, so no writer appended to
it between the two.

### Continuity

`head -c 4885745` of this capture hashes to
`e747b3e80ce3be4f76da41da7262ef19adacfc3c34b0fcb739b4055dc44c2589`, so the
capture section 17 names is a byte-exact prefix. This one adds **189,251
bytes and 924 lines**, of which 30 carry no pid: five start-up banners of six
lines each. OBSERVED.

### The runs in the added bytes

| pid | first line | last line | lines | `engine_stopped` |
|---|---|---|---:|---:|
| 20408 | `2026-09-23T06:55:17Z` | `2026-09-23T06:55:21Z` | 2 | 1 |
| 17260 | `2026-09-23T08:24:39Z` | `2026-09-23T16:13:00Z` | 183 | 1 |
| 25024 | `2026-09-23T18:02:34Z` | `2026-09-24T03:58:40Z` | 374 | 1 |
| 24572 | `2026-09-24T09:52:53Z` | `2026-09-24T12:49:02Z` | 108 | 1 |
| 23540 | `2026-09-24T12:49:36Z` | `2026-09-25T07:49:25Z` | 185 | 1 |
| 23236 | `2026-09-25T09:06:36Z` | `2026-09-25T16:16:10Z` | 42 | 1 |

`Received SIGINT` appears **6** times in the added bytes, and every run in them
logged `engine_stopped`. Pid 20408's first line here is its `SIGINT`. **No run
was writing at this capture's instant**: the last line is pid 23236's
`engine_stopped`.

### Counts in the added bytes

22 `order_placed`; 21 `close_planned`, all 21 `decision=sell`; 21
`close_booked`; 1 `exit_booked`; 0 `decision=halt`; 0 `collaborator_failed`; 0
`reconciliation_phase_failed`; and **1 `stage=position_stale`**.

**`RefusalStage.POSITION_STALE` fired, for the first time in any capture this
file names.** `2026-09-24T19:25:00Z`, `pid=23540`: an ETHUSDT `BUY` on 5m
refused with *"1 open position(s) have not been fully reconciled within 180.0s
(BTCUSDT); the ledger is not current enough for any limit to mean anything"*.
Every earlier capture here counts it at zero.

### M5k's events and keys, by content

| Searched for | Lines in the added bytes |
|---|---:|
| `exit_settlement_held` | 0 |
| `exit_quote_totals_disagree` | 0 |
| `close_settlement_deferred` | 0 |
| `exit_settlement_deferred` | 0 |
| `settlement_timeout` | 0 |
| `venue_quote_total_unavailable` | 0 |
| `quote_total_source` | 0 |
| booking lines carrying `fee=` and `fee_asset=` | **8** of 22 |

The 22 booking lines split by pid, with no pid mixed:

| pid | booking lines | carry `fee` and `fee_asset` | first | last |
|---|---:|---|---|---|
| 17260 | 7 | no | `2026-09-23T09:40:03Z` | `2026-09-23T15:38:02Z` |
| 25024 | 7 | no | `2026-09-23T20:11:02Z` | `2026-09-24T03:22:02Z` |
| 24572 | 3 | yes | `2026-09-24T10:38:02Z` | `2026-09-24T12:43:03Z` |
| 23540 | 4 | yes | `2026-09-24T18:30:04Z` | `2026-09-25T06:45:03Z` |
| 23236 | 1 (`exit_booked`) | yes | `2026-09-25T14:05:02Z` | `2026-09-25T14:05:02Z` |

Every one of the eight carries `fee=0E-8 fee_asset=USDT fills=1` and a
`filled_at`. The seven `close_booked` lines carry no `order_created_at`; the
one `exit_booked` does.

### Whether code at or after `651d334` wrote any of it

**Yes, by the key, and the eight lines above are the evidence.** `651d334` is
the commit whose subject begins `feat(accounting): exits book net of the
venue's own fee`. `git grep -c '"fee_asset"'` over `src/` finds nothing at
`milestone/M5j`, at `e511e6d` or at `f1c5af7` -- the commit before `651d334` --
and finds 2 sites in `execution/executor.py` and 1 in
`execution/reconciliation_driver.py` at `651d334`. So no commit before it
writes that key, and the first line carrying it is:

```
2026-09-24T10:38:02Z | INFO     | pid=24572 | trading_bot.execution.executor | Closed BTCUSDT event=close_booked symbol=BTCUSDT order_id=5979512 quantity=0.02172000 quote_total=1808.51905800 fee=0E-8 fee_asset=USDT fills=1 filled_at=2026-09-24T10:38:02.370000+00:00 realised=-0.9667572000 candle_time=2026-09-24T10:37:59.999000+00:00
```

**And that line precedes the commit.** `651d334`'s committer date is
`2026-09-24T23:46:41+06:00`, which is `17:46:41Z`, seven hours after the line.
The repository's reflog shows HEAD at `e511e6d`, committed `09:29:07Z`, from
then until `f1c5af7` at `17:35:53Z`, with no commit between. So pid 24572's
three fee-bearing lines were written by code that **no commit then in this
repository contained** -- code from a working tree, not from a commit. OBSERVED
from the line times, the committer dates and the reflog. Pid 23540 began at
`12:49:36Z`, also before `651d334` existed, and its four lines were written
after it. That its code is what it loaded at start is REASONED, from Python
importing its modules once at start, and not measured.

**No line in the added bytes needs code at or after `c5dd7d5`.** From that
commit every booking line spreads `quote_total_fields`, which writes
`quote_total_source` beside `quote_total` on each of the three booking emitters.
No added line carries it, and none of M5k's other six events appears.

**So M5k's code, as committed, is not shown to have run.** The fee settlement
ran, from uncommitted code for at least one process, on eight bookings whose fee
was zero every time. No hold, deferral, fills supply, disagreement warning,
settlement timeout or negative-total warning is recorded anywhere in this
capture. **Which commit, if any, each run deployed is not established.**

### The realised exponent, across the chain

Booking lines' `realised` carries exponent -10 on 140 lines, -9 on 11, -8 on 10
and **-24 on 4**, counted over the whole of this capture. The four at -24:

| time | pid | event | `order_id` | `realised` |
|---|---|---|---|---|
| `2026-09-10T03:34:04Z` | 7888 | `close_booked` | 327933 | `5.201974900000000000000000` |
| `2026-09-20T18:02:02Z` | 16216 | `close_booked` | 4347037 | `-5.235144100000000000000000` |
| `2026-09-21T09:40:01Z` | 16216 | `exit_booked` | 4559541 | `75.164021600000000000000000` |
| `2026-09-23T22:37:03Z` | 25024 | `close_booked` | 5731709 | `1.673428400000000000000000` |

Each has seven significant decimal places followed by zeros to the 24th. The
cause is UNMEASURED.

### `scripts/run_census.py` over this capture

56 distinct pids, 26 substantial; 185 `order_placed`, 163 `close_planned`, 154
`close_booked`, 11 `exit_booked`, 18 `exit_book_refused`, 12
`reconciliation_phase_failed`, 8 `engine_stopped`, 0 `collaborator_failed`.
Whole-capture `decision=halt` is **0** of 163 close plans (162 `decision=sell`,
1 `decision=already_closed`).

### What sections 16 to 19 are

Observations, like every section above them: past-tense statements about bytes
with a stated digest, and no rule.

## 20. The project owner's accounts, at M5k's close

Sections 17 and 19 wrote three facts as *not established*, because no log line
can establish them. The project owner supplied accounts at M5k's rotation. They
are recorded here verbatim and attributed. **Each is the owner's account; no
log in this file measures it**, and nothing here upgrades it to an observation.

### Pid 24772, which ended without `engine_stopped` (section 17)

Section 17: *"Why pid 24772 ended without `engine_stopped` is not
established."* The owner's account:

> "Ceased without an exit record due to an ungraceful process kill (external
> terminal termination / system kill event) rather than an intercepted
> `SIGINT`."

What the capture shows is consistent with that and does not measure it:
pid 24772's last line is at `2026-09-19T09:42:02Z`, no line after it names the
pid, and no `Received SIGINT` line precedes that end.

### Order 300642 (section 17)

Section 17: *"What order 300642 was is not established."* The owner's account:

> "Historical Testnet test artifact from prior test probe sequences,
> pre-dating M5k's wire model and booking metadata schema."

The 18 refusals naming it, recorded in section 17, are dated 2026-09-10,
before M5k's first commit.

### The run at M5k's close (section 19)

Section 19: *"Which commit, if any, each run deployed is not established."* The
owner's account:

> "The current background run is not executing committed M5k code (evidenced
> by zero `quote_total_source` emissions). It will be terminated and replaced
> with a clean run pinned to M5k's closing release tag."

**It does not establish which commit any run deployed**, and section 19's
statement stands for the six runs it lists. The evidence the account cites is
section 19's own count of zero `quote_total_source` lines. **One measurement
belongs beside it, of metadata only:** at `2026-09-26T08:28:38Z`
`logs/trading_bot.log` was 5,074,996 bytes, last written `2026-09-25T16:16:10Z`
-- byte-for-byte the length section 19's capture copied. So no process has
written to that log since section 19's last line, and "the current background
run" is not a run this file has seen. Whether a run is writing elsewhere is not
established here.

### What this section is

The owner's accounts, attributed, beside what the log does and does not show.
No rule, and no observation promoted beyond what its instrument read.

## 21. M5l's evidence run: the start record

`docs/NEXT_MILESTONE.md`: *"`docs/RUN_LEDGER.md` records its start -- the
commit, the config's digest and the UTC instant -- before its evidence is
read."* This section is that record. The deviation below says what was read
before it was committed.

### The start fields

The project owner's figures, copied from the run's `boot_provenance` line.

| Field | Value |
|---|---|
| UTC instant | `2026-09-27T13:30:56Z` |
| pid | `21520` |
| code_commit | `06089d5e01cb88f5f4b7b3833d2c87684714ea74` |
| config_sha256 | `5e75b97a8270e4a7ec503b1adc1d0dd7e78fc537b3213b08c990d518dda0503d` |
| clone | `F:\trading bot\deploy\06089d5e01cb`, the only unretired deployment clone for this account |
| log | `F:\trading bot\deploy\06089d5e01cb\logs\trading_bot.log` |

The clone was built at P62 by `CLAUDE.md`'s deployment procedure, steps 1 to
8, from GitHub at `06089d5`, with its own venv and a VCS install whose
`direct_url.json` records `commit_id` `06089d5e01cb88f5f4b7b3833d2c87684714ea74`.
Its log also holds a dry boot of `strategies`, `pid=22088` at
`2026-09-27T13:24:21Z`, `verdict=accepted`, which placed nothing and is not
this run. The previous clone was retired first; section 22 records it.

### The store

| Property | Value | Instrument |
|---|---|---|
| source | the development tree's `data/state.json` | |
| source SHA-256 | `A7F459CCC605021DD5CA9F7F70A9A77FE11879646D99B845C8B2919C438377F6` | `Get-FileHash -Algorithm SHA256` |
| copy in the clone | `data/state.json`, SHA-256 equal to the source | the same |
| retired development copy | `data/state.json.retired-20260927T132301Z`, same SHA-256 | the same |

The retired clone's store has the same SHA-256, so every store this account
has had since `2026-09-26T10:03:03Z` held the same bytes.

### The objectives

Quoted from `docs/NEXT_MILESTONE.md`'s evidence-first paragraph, as it stood
at `06089d5`:

> "**The milestone's shape is EVIDENCE-FIRST.** M5k's code is not shown to have
> run as committed -- see THE CENTRAL FACT below. So M5l's first run on known
> code executes from a deployment checkout of a pushed commit, per that
> doctrine. `docs/RUN_LEDGER.md` records its start -- the commit, the config's
> digest and the UTC instant -- before its evidence is read. Its census then
> answers, against the unobserved-surface table below, which of the 22 log
> events and the 8 `RefusalStage` members never observed at M5k's close it
> exercises. No such run has started as this is written."

The paragraph names no stop criterion. Its "22 log events" is 23 by the table
it points to, which counts `boot_provenance` since P-1.

> **ANNOTATED AT P64: THE SENTENCE ABOVE MISREADS THE PARAGRAPH.** The
> paragraph counts events *"never observed at M5k's close"*, and at that close
> 22 was right, because `boot_provenance` did not exist until `f8898de`. The
> table's 23 includes that one event, added after the close. Both figures are
> correct in their own scope, and section 23's census reports against all 23.

### The deviation

**This record was not committed before the run's log was read.** At about
`2026-09-27T13:35:37Z`, on the owner's request for a status check, the last
eight lines of the run's log were read. They held the `BUY` signal on
BTCUSDT at `13:34:01Z`, the placement of order list `333832`
(`tb1-BTCUSDT-1790516039999-0-L`), and a `reconciliation_pass` at `13:35:01Z`
reading `states="active=1"`. The run's `boot_provenance` line was read at the
same time for its instant. The start fields above come from that boot line
and are unaffected: the line was written at the run's start and nothing read
afterwards can change it. No census of the run has been taken.

> **ANNOTATED AT P64: *"No census of the run has been taken"* IS NO LONGER
> TRUE.** It was taken after the end record below, and section 23 holds it.

### The end record

Recorded before any census of the run.

| Field | Value | Instrument |
|---|---|---|
| stop instant | `2026-09-27T16:53:22Z`, `SIGINT` | the project owner |
| flat at stop | yes: the last close booked at `16:43:03Z`, order `7007486`, and nothing was entered after it | the project owner |
| log bytes | 23,625, last written `2026-09-27T16:53:23Z` | `Get-Item` |
| log lines | 115 in all; 101 carry `pid=21520` | `Get-Content` count; `pid=21520` match |
| log SHA-256 | `C1471D3C3B61A1F765B339BFC83AF549C71BBB92821310F158C8B4FF85BC089F` | `Get-FileHash -Algorithm SHA256` |
| `engine_stopped clean_shutdown=True` for pid 21520 | present, once | `Select-String` |

The log's last line, verbatim:

```
2026-09-27T16:53:23Z | INFO     | pid=21520 | trading_bot.engine.live_engine | Trading engine stopped event=engine_stopped clean_shutdown=True
```

The owner states the run was flat at stop, so no position was left for
`docs/NEXT_MILESTONE.md` P-3k's restart gap. That state is the owner's
account; this record does not measure it.

### What this section is

A start record, a statement of what was read before it, and the end record.
No rule, and no figure from the run's evidence beyond the log's own size,
digest and last line.

## 22. The retired clone's runs, and the owner's manual actions -- RECORDED AFTER THE FACT

Everything here happened before this section was written, and none of it had a
start record. The runs were read at P62, before the clone was retired.

### The retired clone

| Property | Value | Instrument |
|---|---|---|
| path | `F:\trading bot\deploy\bot.retired-20260927T132030Z`, renamed at P62 from `F:\trading bot\deploy\bot` | `Rename-Item`, then `Test-Path` on both names |
| HEAD | `9f364ddd5391da5cbb63a7bb0e8892bbbe39b3b3`, detached, BEFORE `c2cab79` (C4) | `git -C <clone> rev-parse HEAD` |
| log SHA-256 | `9D13F525CA44B4B8CFEDC0F287AD98E4099AADE1A17A8831E49263B73450EDE6`, 46 lines, equal before and after the rename | `Get-FileHash -Algorithm SHA256`; `Get-Content` count |
| store SHA-256 | `A7F459CCC605021DD5CA9F7F70A9A77FE11879646D99B845C8B2919C438377F6` | `Get-FileHash -Algorithm SHA256` |

Every `boot_provenance` line in that log reads `verdict=accepted
install_kind=vcs code_commit=9f364ddd5391da5cbb63a7bb0e8892bbbe39b3b3
code_intact=true code_files_checked=68 checkout_dirty=false
commits_agree=true
config_sha256=5e75b97a8270e4a7ec503b1adc1d0dd7e78fc537b3213b08c990d518dda0503d
config_tracked=true`.

### The runs in its log

| pid | first line | last line | what it did |
|---|---|---|---|
| 22740 | `2026-09-27T03:47:17Z` | `2026-09-27T03:47:17Z` | a `boot_provenance` line only |
| 20112 | `2026-09-27T03:48:09Z` | `2026-09-27T03:48:26Z` | `run`; at `03:48:14Z` `boot_symbol_blocked` for BTCUSDT, `order_list_id=317428`, `list_order_status=EXECUTING`; `Received SIGINT` at `03:48:24Z`, `engine_stopped clean_shutdown=True` |
| 12808 | `2026-09-27T03:50:32Z` | `2026-09-27T04:16:20Z` | `run`; at `03:50:35Z` 0.02151000 BTC found as an unmanaged holding; a BTCUSDT `BUY` refused at `unmanaged_holding` at `04:10:00Z`; no order placed; `Received SIGINT` at `04:16:18Z`, `engine_stopped clean_shutdown=True` |

Instrument: `Select-String -Pattern 'pid=<pid> '` over the retired log, first
and last match. The first line of pids 20112 and 12808 is the banner, one
second before their `boot_provenance` line.

### The owner's manual actions

**The cancel of list 317428's legs at `2026-09-27T03:50:23.068Z`** (`M5l-044`).
The retired log brackets it from presence: the list was `EXECUTING` at
`03:48:14Z` (pid 20112), no bot process wrote between `03:48:26Z` and
`03:50:32Z`, and at `03:50:35Z` pid 12808 found the base as an unmanaged
holding. **Who cancelled it, and with what tool, is not confirmed by the owner
as of this section**, and nothing here attributes it.

> **ANNOTATED AT P64: THE OWNER HAS NOW ATTRIBUTED IT (`M5l-052`).** The
> owner's answer at P64 was option A: the owner cancelled it, with
> `scripts/cancel_testnet_order_list.py`, the tree's only list-cancelling
> tool. That script writes nothing to any log, so this is the owner's account
> and no log measures it. The bracket above is consistent with it. That
> `M5l-044` "attributes the sale and not the cancel" was true of the answer
> it had; this is the attribution it lacked.

**The sale, orderId 6943472**, which the owner attributed at P61 to
`scripts/clear_testnet_holdings.py --symbol BTCUSDT --execute`. Read at P62 by
`get_order` and `get_my_trades`: `SELL` `MARKET`, `FILLED`, 0.02151000 at
`2026-09-27T12:51:43.253Z`, client id prefixed `x-HNA2TXFJ`, one fill, trade
1822758, price 84,971.00, quote 1,827.72621000, commission 0.00000000 `USDT`.

### What this section is

Runs and actions recorded after they happened, with the instrument beside each
figure. No rule, and no attribution the owner has not given.

## 23. M5l's evidence run: the census and the venue cross-check

### The capture

| Property | Value |
|---|---|
| file | `trading_bot.m5l-evidence-run-pid21520.log`, in the evidence directory beside section 19's capture |
| source | `F:\trading bot\deploy\06089d5e01cb\logs\trading_bot.log` |
| taken | `2026-09-27T16:59:56Z`, the file's creation time |
| bytes | 23,625 |
| lines | 115 |
| **SHA-256** | **`c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f`** |

The read was share-mode (`FileShare.ReadWrite`) and the copy was made whole,
with `FileMode.CreateNew`. The source's SHA-256 before the copy and the
capture's after it are equal, and both equal section 21's end record. So the
log did not change between the end record and the census. **This capture is
not a continuation of section 19's**: it is another log, so no prefix
relation exists or is claimed.

### The census tool

Command, from the repository root:

```
.venv/Scripts/python.exe scripts/run_census.py "F:/trading bot/files/binance-trading-bot/m5j-evidence/trading_bot.m5l-evidence-run-pid21520.log"
```

Output, verbatim, exit 0:

```
==========================================================================
CAPTURE
==========================================================================
  path   : F:\trading bot\files\binance-trading-bot\m5j-evidence\trading_bot.m5l-evidence-run-pid21520.log
  bytes  : 23625
  lines  : 115
  sha256 : c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f

==========================================================================
PID CENSUS  [sha256 c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f]
==========================================================================
  distinct pids          : 2
  substantial (>= 100 lines): 1
  first line carrying pid= : 2026-09-27T13:24:21Z | INFO     | pid=22088 | trading_bot.main | 

==========================================================================
PER-PID LINE COUNTS  [sha256 c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f]
==========================================================================
  pid=21520    lines=101     substantial
  pid=22088    lines=2       

==========================================================================
PER-EVENT TOTALS  [sha256 c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f]
==========================================================================
  58      reconciliation_pass
  6       intent_dispatched
  3       close_booked
  3       close_planned
  3       close_window_open
  3       order_placed
  2       boot_provenance
  1       boot_assets_excluded
  1       engine_stopped

==========================================================================
TOTALS  [sha256 c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f]
==========================================================================
  distinct events   : 9
  event records     : 80
  distinct pids     : 2
  substantial runs  : 1
```

**Pid 21520 alone.** Pid 22088 is P62's dry boot. Its 2 lines are a banner
and one `boot_provenance`. So pid 21520 accounts for every per-event total
above except one `boot_provenance`: `reconciliation_pass` 58,
`intent_dispatched` 6 (3 `BUY`, 3 `CLOSE`), `order_placed` 3, `close_planned`
3, `close_window_open` 3, `close_booked` 3, `boot_provenance` 1,
`boot_assets_excluded` 1, `engine_stopped` 1. Instrument: `Select-String`
for `| pid=21520 |`, then `event=(\w+)` grouped. The run logged no
`risk_refused`, no `stage=`, no `exit_booked` and no
`reconciliation_untrusted` line (`Select-String`, count 0 each). Every one of
its 58 passes reads `positions=1 calls=1 queries=2 states="active=1"`.

### The trades

| list | entry leg filled | protective legs | close | sell order | realised |
|---|---|---|---|---|---|
| `333832` | `13:34:00.953Z`, 0.02126000 at 85,064.74 | both `CANCELED`, 0 executed | death cross, `14:30:01Z` | `6970269` at 84,723.53 | `-7.2541246000` |
| `334985` | `15:33:04.691Z`, 0.02138000 at 84,594.01 | both `CANCELED`, 0 executed | death cross, `15:44:01Z` | `6991638` at 84,486.68 | `-2.2947154000` |
| `335369` | `16:15:00.934Z`, 0.02139000 at 84,564.00 | both `CANCELED`, 0 executed | death cross, `16:43:01Z` | `7007486` at 84,450.02 | `-2.43803220` |

Realised is copied from each `close_booked` line. Everything else is from the
venue cross-check below. All three exits came from the bot's own `CLOSE`
sequence, and no protective leg filled. Each `close_planned` reads
`decision=sell`, with `elapsed_s` of 0.297809, 0.831214 and 0.323905.

### The objectives

Against the evidence-first paragraph section 21 quotes, and against the rows
P62 named as reachable under this configuration:

| Objective or row | Result | Evidence |
|---|---|---|
| a first run on known code, from a deployment checkout of a pushed commit | OBSERVED | pid 21520's `boot_provenance`, section 21: `verdict=accepted`, `code_commit=06089d5e01cb88f5f4b7b3833d2c87684714ea74`, `checkout_dirty=false`, `commits_agree=true` |
| its start recorded before its evidence is read | NOT MET | section 21's deviation (`M5l-051`) |
| M5k's code, as committed, running | OBSERVED (`M5l-053`) | three `close_booked` lines carrying `quote_total_source=venue`, e.g. `2026-09-27T14:30:03Z \| INFO \| pid=21520 \| trading_bot.execution.executor \| Closed BTCUSDT event=close_booked symbol=BTCUSDT quote_total=1801.22224780 quote_total_source=venue realised=-7.2541246000 order_id=6970269 quantity=0.02126000 fee=0E-8 fee_asset=USDT fills=1 filled_at=2026-09-27T14:30:01.888000+00:00 order_created_at=2026-09-27T14:30:01.888000+00:00 candle_time=2026-09-27T14:29:59.999000+00:00` |
| of the 23 events absent at M5k's close (22 then defined, plus `boot_provenance`): `boot_provenance` | OBSERVED | the line above |
| the other 22 | NOT OBSERVED | not among the census's events |
| `close_settlement_deferred`, `close_record_resolved` | NOT OBSERVED | each sell's settlement read succeeded on its first attempt, so there was no deferral and nothing to resolve |
| `exit_settlement_deferred` | NOT OBSERVED | no protective leg filled, so the driver booked no exit |
| `close_cancel_already_terminal` | NOT OBSERVED | each cancel found its list live: every `close_planned` reads `sl_status=NEW` and `tp_status=NEW` |
| `entry_fill_absent`, `debit_from_requested_limit` | NOT OBSERVED | each entry leg filled |
| the six events M5k added | NOT OBSERVED | none is in the census; no fee in a foreign asset, no disagreeing totals, no missing quote total, no protective fill |
| the 8 unobserved `RefusalStage` members | NOT OBSERVED, all 8 | the run refused nothing: 0 `risk_refused` and 0 `stage=` lines |
| `decision=halt` | NOT OBSERVED | 3 `close_planned`, all `decision=sell` |

### WARNING, ERROR and CRITICAL

Pid 21520 logged 5 `WARNING`, 4 `ERROR` and 0 `CRITICAL` lines. Instrument:
`Select-String` for `\| <LEVEL>\s+\|` over pid 21520's lines. All nine,
grouped:

- `WARNING`, 1: `2026-09-27T13:31:00Z | WARNING  | pid=21520 | trading_bot.engine.modes | 499 asset(s) are EXCLUDED FROM EQUITY -- no enabled USDT pair prices them, so equity is UNDERSTATED by their combined value, which cannot be computed here. Set logging.level to DEBUG for the per-asset list. event=boot_assets_excluded excluded_count=499 quote_asset=USDT`
- `WARNING`, 3, one per close, differing only in list, quantity and time: `2026-09-27T14:30:01Z | WARNING  | pid=21520 | trading_bot.execution.executor | Cancelling protection to close BTCUSDT; the position is unprotected from here event=close_window_open symbol=BTCUSDT venue_order_list_id=333832 quantity=0.02126000 candle_time=2026-09-27T14:29:59.999000+00:00`; then `334985` at `15:44:02Z` and `335369` at `16:43:01Z`.
- The stream outage, 4 `ERROR` and 1 `WARNING`:
  - `2026-09-27T13:53:03Z | ERROR    | pid=21520 | binance.ws.reconnecting_websocket | ConnectionClosedError (sent 1011 (internal error) keepalive ping timeout; no close frame received)`
  - `2026-09-27T13:53:03Z | ERROR    | pid=21520 | binance.ws.reconnecting_websocket | BinanceWebsocketClosed (Connection closed. Reconnecting...)`
  - `2026-09-27T13:53:04Z | ERROR    | pid=21520 | binance.ws.reconnecting_websocket | Failed to connect to websocket: [Errno 11001] getaddrinfo failed`
  - `2026-09-27T13:56:52Z | ERROR    | pid=21520 | binance.ws.reconnecting_websocket | Unknown exception: BinanceWebsocketQueueOverflow (Message queue size 100 exceeded maximum 100)`
  - `2026-09-27T13:56:52Z | WARNING  | pid=21520 | trading_bot.exchange.websocket_client | Market-data stream disconnected (ConnectionClosedError); reconnecting in 4.6s (attempt 1)`

### The reconciliation cadence, and the outage (`M5l-055`, `M5l-056`)

The run held a position in three windows: `13:34Z`–`14:30Z`, `15:33Z`–`15:44Z`
and `16:15Z`–`16:43Z`. Within them the gaps between consecutive passes were
about 60 s 21 times and about 120 s 33 times, plus one gap of 300 s.
Instrument: pass timestamps from `event=reconciliation_pass` lines,
differenced, gaps up to 400 s bucketed. The two longer gaps, 3,841 s and
1,861 s, are flat periods with nothing due.

**The 300 s gap is the outage**: from `13:52:01Z` to `13:57:01Z`, while list
`333832` was open. No line of any kind was logged between `13:53:04Z` and
`13:56:52Z`, and passes resumed at `13:57:01Z`. 300 s exceeds
`risk.max_position_staleness_s = 180.0`. No refusal followed, because no signal
arrived in the window, and no escalation line exists to follow it. The
2026-09-17 gap was 184 s; this one is 300 s.

> **ANNOTATED AT M5l (P68, C19): *"No refusal followed, because no signal
> arrived in the window"* IMPLIES A REFUSAL WAS POSSIBLE, AND IT WAS NOT
> (`M5l-068`).** The staleness guard reads the stamp only in `evaluate`, on
> a candle, after the reconciler has run on it. No candle arrived in the
> window, so nothing could be evaluated. When candles resumed, the
> reconciler refreshed the stamp before any read. The 2026-09-17 gap probably
> differs in kind: `docs/M5_NUMBERS.md` §4 records it as a connection-failure
> cluster between successful passes, and a pass can only fail if a candle
> triggered it (REASONED). **What survives:** every measurement in this
> paragraph.

**The 120 s gaps are the dedup comparison.** `_is_due` in
`execution/reconciliation.py` returns `now - position.last_reconciled_at >
dedup_interval`, a strict comparison against 60 s. Two consecutive candle
arrivals are about 60 s apart either way, so roughly half fall on the "not
yet due" side and the pass waits a second bar. That mechanism is REASONED from
the code; the distribution is MEASURED.

### The outage, measured further at P65 (`M5l-060` to `M5l-064`)

Read from this section's capture and from the code: the tree at `ac07ebb`,
and python-binance 1.0.37's `binance/ws/reconnecting_websocket.py`.

**The bars that closed between `13:52:01Z` and `13:57:01Z`:**

| pair | bar close | state | basis |
|---|---|---|---|
| BTCUSDT/1m | `13:52:59.999Z` | UNMEASURED | It would arrive before the `13:53:03Z` error. If dispatched, the position was not yet due (last stamp `13:52:01Z`, strict `>` 60 s) and the strategy signalled nothing, so it leaves no line either way. |
| BTCUSDT/1m | `13:53:59.999Z`, `13:54:59.999Z`, `13:55:59.999Z` | never received, never backfilled | Any of them, dispatched, would find the position due and log a pass; none is logged before `13:57:01Z`. The provider's docstring: *"Gaps are not backfilled."* |
| ETHUSDT/5m | `13:54:59.999Z` | never received, never backfilled | the same basis |
| BTCUSDT/1m | `13:56:59.999Z` | received live | the `13:57:01Z` pass; no other bar closes that minute |

REASONED from the code and from the pass lines on each side (`M5l-062`).
There is also no pass at `13:56:52Z`, when the consumer resumed, so it
dispatched no closed candle before it raised.

**ATR was not re-masked, because it was not computed.** The configuration's
stops are `percent`, and the ATR bridge runs only for `stop_loss.type='atr'`
(`risk/manager.py`, the `ATR_UNAVAILABLE` branch). A missed bar would not have
re-masked it either:
- the provider omits the bar's row rather than inserting NaN;
- `true_range` takes `close.shift(1)`, a row shift, so each range is taken
  against the previous row's close;
- `sma` uses `values.rolling(period)`, an integer window, so it counts rows,
  not time.

**So the SMA(50) behind the `14:30:01Z` death cross that closed list 333832
spanned the missing bars**: 50 rows over about 53 or 54 minutes, and nothing
detected it (`M5l-063`). The coherence validator's refusal text says *"a gap
re-masks ATR to NaN long after warmup"* (`config/models.py`). That is true of
a NaN value in the series and not of a missed bar, which leaves no NaN
(`M5l-064`).

> **ANNOTATED AT M5l (P68, C16): THE REFUSAL TEXT NO LONGER SAYS THAT.** C16
> replaced it with *"A lost bar leaves no NaN to warn anyone: the indicators
> count rows, not time, so SMA and ATR silently span the gap."* It also
> replaced *"is missed"* with the queue, which holds a late bar until it is
> handled (`M5l-073`). **What survives:** everything this section measured.

**The delay from the library's first error to the bot's warning is 229 s**,
from `13:53:03Z` to `13:56:52Z`. MEASURED.
- **Its cause in code.** The library logs each transient error itself and
  pushes an error dict onto the queue its kline messages share. The branch is
  commented *"reports errors and continue loop"*. The bot learns of a
  disconnect only when `_run` in `exchange/websocket_client.py` dequeues such
  a dict, and it raises on the first one it reads.
- **What the warning shows.** It names `ConnectionClosedError`, which is the
  dict pushed at `13:53:03Z`. So the consumer read nothing from `13:53:03Z`
  to `13:56:52Z` (REASONED).
- **What held it is UNMEASURED.** The library logged one failed connect, at
  `13:53:04Z`, and no further attempt, though its retry schedule logs every
  failure. By `13:56:52Z` it had enqueued 100 messages, so it had reconnected
  and was receiving while the consumer did not drain (`M5l-060`).

**What `BinanceWebsocketQueueOverflow` drops**, from the library source:
1. The read loop raises it when a received message finds the queue at 100, so
   that message is never enqueued.
2. The exception falls to the loop's broad handler, commented *"reports errors
   and break the loop"*. It logs `Unknown exception`, pushes one error dict and
   breaks, so nothing more is read from that socket.
3. The bot then dequeues in order, raises on the first error dict it meets and
   leaves the socket's context. Every message queued behind that dict is
   discarded with the socket, and the provider backfills none of them
   (`M5l-061`).

### The venue cross-check (GET only)

Read after the run stopped, from the clone's root with the clone's
interpreter and `.env`. The calls: `v3_get_order_list` for each list;
`get_order` and `get_my_trades` for each leg and each sell.

| order | client id | side / type | status | executed | fill price | quote | commission |
|---|---|---|---|---|---|---|---|
| `6954831` | `tb1-BTCUSDT-1790516039999-0-W` | BUY `LIMIT` | `FILLED` | 0.02126000 | 85,064.74 | 1,808.47637240 | 0.00000000 BTC |
| `6954832` | `…-0-SL` | SELL `STOP_LOSS` | `CANCELED` | 0 | | | |
| `6954833` | `…-0-TP` | SELL `TAKE_PROFIT` | `CANCELED` | 0 | | | |
| `6970269` | `tb1-BTCUSDT-1790516039999-0-CL` | SELL `MARKET` | `FILLED` | 0.02126000 | 84,723.53 | 1,801.22224780 | 0.00000000 USDT |
| `6989029` | `tb1-BTCUSDT-1790523179999-0-W` | BUY `LIMIT` | `FILLED` | 0.02138000 | 84,594.01 | 1,808.61993380 | 0.00000000 BTC |
| `6989030` | `…-0-SL` | SELL `STOP_LOSS` | `CANCELED` | 0 | | | |
| `6989031` | `…-0-TP` | SELL `TAKE_PROFIT` | `CANCELED` | 0 | | | |
| `6991638` | `tb1-BTCUSDT-1790523179999-0-CL` | SELL `MARKET` | `FILLED` | 0.02138000 | 84,486.68 | 1,806.32521840 | 0.00000000 USDT |
| `6999320` | `tb1-BTCUSDT-1790525699999-0-W` | BUY `LIMIT` | `FILLED` | 0.02139000 | 84,564.00 | 1,808.82396000 | 0.00000000 BTC |
| `6999321` | `…-0-SL` | SELL `STOP_LOSS` | `CANCELED` | 0 | | | |
| `6999322` | `…-0-TP` | SELL `TAKE_PROFIT` | `CANCELED` | 0 | | | |
| `7007486` | `tb1-BTCUSDT-1790525699999-0-CL` | SELL `MARKET` | `FILLED` | 0.02139000 | 84,450.02 | 1,806.38592780 | 0.00000000 USDT |

All three lists read `listOrderStatus=ALL_DONE`, `listStatusType=ALL_DONE`
and `contingencyType=OTO`, with three orders each. Every order had at most one
fill.

**No commission was non-zero.** All six fills, the three buys in BTC and the
three sells in USDT, carry `0.00000000`. So this run cannot satisfy the
live-trading precondition *"a non-zero fee capture empirically established on
a live-quoted venue"*.

**Every booked close reconciles exactly, in `Decimal`** (`M5l-054`). For each
close: the sell's summed `quoteQty` equals `close_booked`'s `quote_total`,
and equals the sell's `cummulativeQuoteQty`. Its summed `qty` equals the
entry's and the logged `quantity`. Its summed commission, `0E-8`, equals the
logged `fee`. And `sell quote - sell fee - entry quote` equals the logged
`realised` by value: `-7.25412460`, `-2.29471540` and `-2.43803220` against
the logged `-7.2541246000`, `-2.2947154000` and `-2.43803220`. The first two
differ only in exponent. The three total **`-11.98687220`** USDT, gross of
entry fees, which were zero.

### What this section is

A census of one frozen capture and a read of the venue, each figure beside
its instrument. No rule. The objectives' results are observations, and what
they mean for the milestone is reserved.

## 24. P-3k's supervised run: the template (NOT YET RUN)

> **ANNOTATED AT M5l P85 (C37): THE RUN HAS BEGUN, AND THE HEADING'S
> *"NOT YET RUN"* IS NO LONGER TRUE.** Section 25 records it. This section is
> left as the template it was; what it holds is still the arms' expected lines.

**This section is a TEMPLATE, written at M5l P83 (C33), and holds no
observation.** Every `<...>` below is filled when the run happens, from the
run's own log and the venue's own answers, never from memory. The live-trading
gate that P-3k carries stays closed until the arms **A1, A2 and A4** are
recorded here (`docs/NEXT_MILESTONE.md`, P-3k). The arms and their expected
lines are P77 S7's, corrected to the events the tree emits (see the notes
after the table).

### The start record

Recorded before any evidence is read, from the run's `boot_provenance` line.

| Field | Value |
|---|---|
| UTC instant | `<...>` |
| pid | `<...>` (the venv interpreter's, `M5l-040`) |
| code_commit | `<...>` |
| config_sha256 | `<...>` |
| clone | `<...>` |
| log | `<clone>\logs\trading_bot.log` |
| store at start | `<SHA-256 of data/state.json>` and its `"schema"` |

The run follows `CLAUDE.md`'s deployment procedure in full, including the C33
additions: the store copied from the ACTIVE deployment clone, and the schema
comparison made before the first boot.

### Before each restart, read only

The leg states of the list under test, the relevant `myTrades` fills, and the
SHA-256 of `data/state.json`. Kill with `taskkill /F /PID <interpreter pid>`.

### The arms

| Arm | Action | Expected lines after the restart |
|---|---|---|
| A1 | Hard kill with a live list | `boot_provenance`; `boot_position_restored` for the symbol; no `boot_symbol_blocked` for it; then, at the first candle, `reconciliation_pass` with `states="active=1"` |
| A2 | Hard kill, and the stop fills while down | `boot_exit_booked` with `leg=SL`, `quote_total_source=venue`, `fee_asset=USDT`, `filled_at=<t>` and `booked_day=<the fill's UTC day>`; no `boot_position_restored` for it; `boot_positions_resolved` with `booked=1` |
| A3 | As A2 with the take-profit, only if the market provides it | `boot_exit_booked` with `leg=TP` |
| A4 | Hard kill, then cancel the list with `scripts/cancel_testnet_order_list.py` | `boot_position_unprotected` at `CRITICAL`, naming `scripts/release_position.py`; then, on that symbol's first candle, the executor's close path: `close_planned`, the answer to the list's cancel, one MARKET sell, and `close_booked` |
| A5 | Hard kill, cancel the list, and sell the base with `scripts/clear_testnet_holdings.py` | `boot_position_gone` at `CRITICAL`, and no order sent |
| A6 | Restart onto a config with the pair disabled | Exit 1, with a refusal naming the pair and our list id and the release command. The config must be committed and pushed to pass the provenance check, so this arm needs its own deployment commit |
| A7 | Ctrl+C with a live list | As A1 |

**Two corrections to P77 S7's expected lines** (`M5l-158`). It listed
`list_order_status=EXECUTING` on `boot_position_restored` and `site=boot` on
`close_booked`; neither field exists on those emitters, so the lines above omit
them, and the live state of the list is read from the venue instead. The
`site=boot` field does exist on `exit_settlement_held`, which a boot hold emits.

### A4 also records the venue's answer to cancelling an ALL_DONE list (`M5l-141`)

R3's sale rests on that cancel answering `OrderNotFoundError`, and no capture
holds the answer. Record it VERBATIM from the log: either the
`close_cancel_already_terminal` line, or the `close_cancel_failed` line's
`error_type` and `error`.

| Field | Value |
|---|---|
| line | `<verbatim>` |
| `error_type` / `error`, if it failed | `<verbatim>` |
| the venue's code and message | `<verbatim>` |
| consequence | `<the sale went out, or nothing was sold and the position stayed UNKNOWN>` |

### Per arm, record

| Field | A1 | A2 | A4 |
|---|---|---|---|
| kill instant and pid | `<...>` | `<...>` | `<...>` |
| our list id and the venue's | `<...>` | `<...>` | `<...>` |
| leg states read, before the restart | `<...>` | `<...>` | `<...>` |
| the fills read | `<...>` | `<...>` | `<...>` |
| the boot lines, verbatim | `<...>` | `<...>` | `<...>` |
| the store's SHA-256 and realised figures, before and after | `<...>` | `<...>` | `<...>` |
| the day each booking was attributed to | `<...>` | `<...>` | `<...>` |

### What the run decides

A1, A2 and A4 recorded, each beside its instrument, is the condition the P-3k
gate names. It is the project owner's to judge whether they are met. A3, A5, A6
and A7 are recorded when they are run and gate nothing.

## 25. P-3k's supervised run, as far as it has gone (A1 and A4 run, A2 in the log)

**Recorded at M5l P85 (C37), from the deployment clone's own files only** --
`logs\trading_bot.log`, `logs\release.log` and `F:\trading bot\deploy\arm_notes.txt`
-- read and never written, plus one GET-only read of the venue for the
operator's manual sale. The clone is `F:\trading bot\deploy\d1074c646cf6`, at
`d1074c646cf6f8c27cc5791d57cdbf80e28b2163`, the commit before C35, so **the
code under test is the code that failed A4** and carries no fix for it.
Section 24 is the template this fills; it is left standing.

### The capture

| File | Bytes read | SHA-256 |
|---|---|---|
| `logs\trading_bot.log` | 195 lines, last line `2026-10-02T07:00:03Z`, pid 3608 | `b9d3b1947353d850b50aa19a4d11655c75eb29373e01e934a69e0b8ecee096fb` |
| `logs\release.log` | 1 line | `cb754301e3cb1c3b17b698b6d7653f6e9e2a86e17c11b768a601efc17ebdf9da` |
| `F:\trading bot\deploy\arm_notes.txt` | 8 lines | `26d946285ebee81177f664e3077b5eb8392f700bdade16dd34365758d636b7aa` |

Every figure below is a claim about those bytes. The clone's `data\state.json`
was not read; the stores' SHA-256 are quoted only from `release.log`.

### The start records, one per launch

All six are `boot_provenance verdict=accepted`, `install_kind=vcs`,
`code_commit=d1074c646cf6f8c27cc5791d57cdbf80e28b2163`, `code_intact=true`
over 69 files, `checkout_dirty=false`, `commits_agree=true`,
`config_tracked=true`, `config_sha256=f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`,
clone `F:\trading bot\deploy\d1074c646cf6`.

| pid | boot_provenance | what it did |
|---|---|---|
| 19772 | `2026-10-01T06:03:57Z` | a banner and the provenance line only; no `Starting in` line, nothing else after the provenance line |
| 22308 | `2026-10-01T16:34:46Z` | the run's first live process: placed BTCUSDT list 400545 at `17:14:04Z` and ETHUSDT list 401075 at `17:45:03Z`; last line `17:57:03Z`, no `engine_stopped` |
| 14396 | `2026-10-01T17:58:40Z` | A1's restart; closed BTCUSDT by the strategy at `18:08:06Z`; last line `18:22:03Z`, no `engine_stopped` |
| 16748 | `2026-10-01T18:27:16Z` | A4; `Received SIGINT` at `18:37:44Z`, `engine_stopped clean_shutdown=True` |
| 21844 | `2026-10-01T19:47:46Z` | after the operator's release; placed BTCUSDT list 402643 at `20:06:04Z`; `Received SIGINT` at `20:07:29Z`, `engine_stopped clean_shutdown=True` |
| 3608 | `2026-10-02T06:49:59Z` | A2's restart; booked BTCUSDT's stop at boot; opened and closed BTCUSDT list 410028 (`07:00:03Z`); last line `07:00:03Z` |

Instrument: `grep "pid=<pid> "`, first and last match, over the capture above.

**THE DEVIATION, `M5l-051`'s shape again.** The `arm_notes.txt` appends were
made after the console had been seen, so the start records above were not
written before the evidence was read. Its eight lines are `boot_provenance`
lines copied from the log: pid 22308 twice, 14396, 16748 once each, 21844
three times and 3608 once, and **none for 19772**. The duplicates are copies
of one line and add nothing; the table above is built from the log.

### A1 -- PASS (hard kill with live lists): both positions restored

Pid 22308 had two live lists and was killed: no `engine_stopped`, last line
`17:57:03Z`, the next process's first line `17:58:39Z`. Pid 14396 then logged
`boot_position_restored` for **both** BTCUSDT (list 400545, entry fill
84434.02, quote total 1803.51066720) and ETHUSDT (list 401075, entry fill
2708.48, quote total 1803.84768000) at `17:58:51Z`, and
`boot_positions_resolved records=2 restored=2 booked=0 held=0 dropped=0
gone=0`. `boot_symbol_blocked` occurs on **0** lines of the capture. The first
reconciliation pass after the restart, `17:59:03Z`, reads
`positions=2 states="active=2"`.

**The balance reconciles exactly (`free_quote`).** Pid 22308's composition root
read `90276.07127200` USDT free; pid 14396's read `86668.71292480`:

    90276.07127200 - 1803.51066720 - 1803.84768000 = 86668.71292480

the two restored positions' own entry quote totals, to the last digit.

**The restored BTC position then closed normally, by the strategy, at runtime:**
`Signal CLOSE BTCUSDT` at `18:08:04Z`, `close_planned` (sell, both legs `NEW`,
nothing executed), `close_window_open`, and `close_booked` at `18:08:06Z`,
`quote_total=1810.43023920 quote_total_source=venue realised=6.9195720000
fee=0E-8 fee_asset=USDT`. Pid 16748's boot then reads `88479.14316400` free,
which is `86668.71292480 + 1810.43023920` exactly.

The leg states and fills read before the restart, and the store's SHA-256
before it, are **NOT RECORDED**: `arm_notes.txt` carries only provenance lines.

### A4 -- FAIL: the venue's answer to cancelling an ALL_DONE list was not mapped (`M5l-161`)

The operator cancelled ETHUSDT's list 401075 by hand between pid 14396's last
line (`18:22:03Z`) and pid 16748's first (`18:27:16Z`), with
`scripts/cancel_testnet_order_list.py`, which writes no log. Pid 16748's boot
then read both legs `CANCELED` with nothing executed and logged, at `18:27:21Z`,
`boot_position_unprotected` at `CRITICAL`, naming `scripts/release_position.py`
and R3 (*"It is SOLD on this symbol's first candle (R3)"*). That half of the
arm's expected lines is met.

**On the symbol's first candle the sale did not go out.** Verbatim:

    2026-10-01T18:30:03Z | INFO | pid=16748 | trading_bot.execution.executor | Close planned for ETHUSDT: sell event=close_planned symbol=ETHUSDT decision=sell detail="no protective leg executed across 2 leg(s); the position is still open and the sell may be dispatched" reads=2 ... sl_status=CANCELED sl_executed=0E-8 tp_status=CANCELED tp_executed=0E-8
    2026-10-01T18:30:03Z | WARNING | pid=16748 | trading_bot.execution.executor | Cancelling protection to close ETHUSDT; the position is unprotected from here event=close_window_open symbol=ETHUSDT venue_order_list_id=401075 quantity=0.66600000 candle_time=2026-10-01T18:29:59.999000+00:00
    2026-10-01T18:30:03Z | ERROR | pid=16748 | trading_bot.exchange.models | Unclassified message for Binance code -2011: 'Unknown order list sent.'. A rule keys on this code but no pattern matched, so it falls through to a generic error -- the wording may have changed at the venue.
    2026-10-01T18:30:03Z | CRITICAL | pid=16748 | trading_bot.execution.executor | Cancel failed for ETHUSDT; the venue state is unknown and nothing was sold event=close_cancel_failed symbol=ETHUSDT venue_order_list_id=401075 error_type=OrderError error="Unknown order list sent." candle_time=2026-10-01T18:29:59.999000+00:00
    2026-10-01T18:30:03Z | WARNING | pid=16748 | trading_bot.execution.executor | Dispatch refused event=dispatch_refused symbol=ETHUSDT action=CLOSE reason=close_cancel_failed candle_time=2026-10-01T18:29:59.999000+00:00

Section 24's table for `M5l-141`, filled:

| Field | Value |
|---|---|
| line | the `close_cancel_failed` line above |
| `error_type` / `error` | `OrderError` / `Unknown order list sent.` |
| the venue's code and message | `-2011`, `Unknown order list sent.` (Testnet, `2026-10-01T18:30:03Z`, list 401075, ETHUSDT, `ALL_DONE`) |
| consequence | nothing was sold; the position stayed restored and UNKNOWN |

**`M5l-141` is resolved as measured, and it fell in the direction it said it
would**: the cancel failed at `CRITICAL`, the close record was released and
nothing was sold. No `close_cancel_already_terminal` line occurs in the
capture (0). From C35 (`244aa6b`) `-2011 'Unknown order list sent.'` maps to
`OrderNotFoundError`. The reconciliation driver then logged `exit_unbookable`
at `CRITICAL` for the position on every pass until `18:36:04Z`, and pid 16748
was stopped by SIGINT at `18:37:44Z`.

### The operator's release and the manual ETHUSDT sale

`release.log`, one line, verbatim:

    2026-10-01T19:42:12.206768+00:00 released symbol=ETHUSDT removed=[position:tb1-ETHUSDT-1790876699999-0-L] store_sha256_before=49a9abe83399ebdaa149a719c215d528eeac45d3614a2c71c484bc1afe0955fe store_sha256_after=f4e631831969af080adfd908c5fc56c7e77b773e00eff2c674153818fe313e3c

The operator then sold the 0.66600000 ETH by hand: **orderId 7612414**, read
by GET (`get_order`, `get_my_trades`; nothing written) on 2026-10-02: `SELL`
`MARKET`, `FILLED`, 0.66600000 of 0.66600000, created and filled
`2026-10-01T19:42:33.184Z` (21 seconds after the release), client id
`x-HNA2TXFJ1a420cdaae8c37cf5b5118` (the library's own prefix, as the
`clear_testnet_holdings.py` sale at section 22), one fill, trade 534559,
price 2698.10000000, quote 1796.93460000, commission `0E-8` `USDT`. The
entry order read by its derived client id `tb1-ETHUSDT-1790876699999-0-W`:
orderId 7583838, `BUY` `LIMIT` `FILLED`, one fill, trade 532417, price
2708.48000000, quote 1803.84768000, commission `0E-8` `ETH`.

**The balance confirms the sale independently.** Pid 21844's root read
`90276.07776400` free, which is pid 16748's `88479.14316400` plus the sale's
`1796.93460000` exactly.

### The operator-takeover cost (`M5l-164`, under `M5l-125`)

**That round trip is outside the ledger.** The position's record was
released before the sale, so no `close_position` ran and `realised_today`
never saw it. From the venue's own fills:

    proceeds        1796.93460000
    entry cost     -1803.84768000
    round trip         -6.91308000 USDT   (exit fee 0E-8 USDT; entry fee 0E-8 ETH)

so **the daily-loss figure for 2026-10-01 understates that day's realised loss
by 6.91308000 USDT.** Against the one booking the capture holds for that day,
BTCUSDT's `realised=6.9195720000`, the account's realised result for the day
is `+0.0064920000`, where the ledger reads `+6.9195720000`. The ledger is
gross of entry fees by ruling and both commissions here are zero, so the figure
carries no fee term. This is `M5l-125`'s rule working as written -- the
operator acts at the venue, releases the record, and what the bot never booked
is the operator's to account for -- and this is its first priced instance.
It is MEASURED from the fills, and the 2026-10-01 total is a statement about
this capture only: the clone's store was not read.

### A2 -- the log already holds the arm's line (pending the owner's judgement)

P85 listed A2 as pending. **The capture holds A2's expected line**, so it is
recorded here and the judgement is left to the owner. Pid 21844 placed
BTCUSDT list 402643 at `20:06:04Z`, and was stopped at `20:07:29Z` --
**by SIGINT, `engine_stopped clean_shutdown=True`, not by a hard kill**, which
is a deviation from the arm as written. The stop filled while the bot was
down. Pid 3608's boot, `2026-10-02T06:50:10Z`, logged, verbatim in its
fields:

    event=boot_exit_booked symbol=BTCUSDT list_client_order_id=tb1-BTCUSDT-1790885159999-0-L leg=SL quote_total=1695.60837380 quote_total_source=venue order_id=8539100 quantity=0.02126000 fee=0E-8 fee_asset=USDT fills=2 filled_at=2026-10-02T05:25:58.122000+00:00 order_created_at=2026-10-01T20:06:01.530000+00:00 realised=-107.8378826000 booked_day=2026-10-02

and `boot_positions_resolved records=1 restored=0 booked=1 held=0 dropped=0
gone=0`. Against section 24's expected line: `leg=SL`, `quote_total_source=venue`,
`fee_asset=USDT`, `filled_at` and `booked_day=2026-10-02` -- the fill's UTC day,
not the boot's day nor the placement's -- are all present; there is no
`boot_position_restored` for BTCUSDT in pid 3608; `booked=1`.

**The balance is consistent with the booking.** Pid 21844's root read
`90276.07776400` free, before it spent the position's entry cost, and pid
3608's read `90168.23988140`, after the stop's `1695.60837380` came back:

    90276.07776400 - 90168.23988140 = 107.83788260

which is the booked `realised=-107.8378826000` to the digit. That holds only if
nothing else moved the quote balance between the two reads; the venue's
entry fill for list 402643 was not read, so the entry cost is implied by the
arithmetic and not observed.

The leg states and fills read before the restart, and the store's SHA-256, are
**NOT RECORDED** (`arm_notes.txt` carries only provenance lines). Pid 3608 then
traded normally: BTCUSDT list 410028 at `06:57:03Z`, `close_booked` at
`07:00:03Z` with `realised=-0.991718400`.

### What this section decides

**Nothing.** A1 and A4 are recorded and A2's line is recorded; whether the
P-3k gate's condition is met is the owner's to judge. A4 failed, and its cause
is fixed by C35, so **the gate stays closed** until A4 is re-run on the commit
carrying C35. A1's and A2's evidence from `d1074c6` stands, because neither
path cancels an order list: A1 restores records and reconciles, and A2 books an
exit the venue already filled, and the answer C35 changed is the answer to a
list cancel, made only by the close path.

> **ANNOTATED AT M5l P87 (C38): THE PARAGRAPH ABOVE IS SUPERSEDED, AND SO IS
> THIS SECTION'S HEADING.** *"Nothing"* and *"the gate stays closed"* were
> true when written. A4 has since been re-run on the commit carrying C35 and
> passed, and the owner has ruled on the gate: see *"A4 re-run at 5e22bc6"*
> and *"The owner's ruling"* below. The heading's *"A2 in the log"* is
> resolved there too (`M5l-166`). **What survives:** every figure recorded
> above, and the reasoning that A1's and A2's `d1074c6` evidence stands
> because neither path cancels a list.

### A4 re-run at 5e22bc6 -- PASS (`M5l-168`)

**Recorded at M5l P87 (C38), from the new deployment clone's own files only,
read while no Python process ran** (`F:\trading bot\deploy\5e22bc6a33ed`, at
`5e22bc6a33ed2d1500a9ed52a12ed5232459b8c0`, built at P86): `logs\trading_bot.log`,
193 lines, SHA-256
`85e1c64391089b1f425ae0efe3954aa705a271d2369ac4bab85ad425871c71bb`, last line
`2026-10-02T12:05:10Z`; and `F:\trading bot\deploy\arm_notes.txt`. Every figure
below is a claim about those bytes. The clone's store was not read.

**The launch.** `boot_provenance verdict=accepted` for pid 11844 at
`2026-10-02T07:28:32Z`, `install_kind=vcs`,
`code_commit=5e22bc6a33ed2d1500a9ed52a12ed5232459b8c0`, `code_intact=true`
over 69 files, `commits_agree=true`, `config_sha256=f9e0d737...82a0`,
`config_tracked=true`; `Starting in TESTNET mode`; and
`Composition root ready: 2 pair(s), 90167.24816300 USDT free`, the figure P86's
pre-flight read. Before it, pids 21660 and 6324 are P86's two dry boots of
`strategies` (`07:19:20Z`, `07:19:28Z`), `boot_provenance` lines only.

**The position under test.** BTCUSDT, `order_list_id=413202`,
`list_client_order_id=tb1-BTCUSDT-1790939579999-0-L`, quantity 0.02083000,
placed `2026-10-02T11:13:03Z`. Pid 11844 had already made three BTCUSDT round
trips that session, each closed by the strategy: lists 410982
(`realised=4.6440308000`), 412180 (`-1.7751860000`) and 412886
(`-3.6098390000`).

**The kill.** Pid 11844's last line is `2026-10-02T11:54:04Z`, a
`reconciliation_pass ... states="active=1"`, with no `engine_stopped`; pid
12472's first line is `12:01:05Z`. So the process was hard-killed in that
interval, bracketed from presence on both sides. The cancel of list 413202 is
not in the log either, because `scripts/cancel_testnet_order_list.py` writes
none; the relaunch's own lines show both legs `CANCELED`.

**The relaunch and the sale, verbatim**, pid 12472 (`Seeded` and
`Market-data provider` lines omitted; nothing else between these lines was):

    2026-10-02T12:01:05Z | INFO | pid=12472 | __main__ | Startup provenance accepted event=boot_provenance verdict=accepted refusal_reasons=none unknown_reasons=none install_kind=vcs code_commit=5e22bc6a33ed2d1500a9ed52a12ed5232459b8c0 code_intact=true code_files_checked=69 ... checkout_dirty=false dirty_count=0 dirty_paths=none commits_agree=true ... config_sha256=f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0 config_tracked=true python_version=3.12.10 package_version=0.1.0
    2026-10-02T12:01:05Z | INFO | pid=12472 | __main__ | Starting in TESTNET mode
    2026-10-02T12:01:10Z | CRITICAL | pid=12472 | trading_bot.engine.modes | BTCUSDT: restored a position whose protection is GONE -- both protective legs were cancelled unexecuted and its base is still held. It is SOLD on this symbol's first candle (R3). If you acted on this symbol by hand, release its record before restarting: python scripts/release_position.py --symbol <SYMBOL>. event=boot_position_unprotected symbol=BTCUSDT list_client_order_id=tb1-BTCUSDT-1790939579999-0-L order_list_id=413202 quantity=0.02083000 base_free=0.02083000
    2026-10-02T12:01:10Z | INFO | pid=12472 | trading_bot.engine.modes | Boot resolved 1 restored record(s): 1 restored, 0 booked, 0 held, 0 dropped, 0 gone event=boot_positions_resolved records=1 pending_placements=0 restored=1 booked=0 held=0 dropped=0 gone=0
    2026-10-02T12:01:10Z | WARNING | pid=12472 | trading_bot.engine.modes | 499 asset(s) are EXCLUDED FROM EQUITY -- no enabled USDT pair prices them, so equity is UNDERSTATED by their combined value, which cannot be computed here. Set logging.level to DEBUG for the per-asset list. event=boot_assets_excluded excluded_count=499 quote_asset=USDT
    2026-10-02T12:01:10Z | INFO | pid=12472 | trading_bot.engine.modes | Composition root ready: 2 pair(s), 88365.38039520 USDT free
    2026-10-02T12:01:11Z | INFO | pid=12472 | trading_bot.engine.live_engine | Trading engine started: BTCUSDT/1m, ETHUSDT/5m
    2026-10-02T12:02:00Z | INFO | pid=12472 | trading_bot.execution.reconciliation_driver | Reconciled 1 position(s) event=reconciliation_pass positions=1 calls=1 queries=2 states="diverged=1"
    2026-10-02T12:02:00Z | WARNING | pid=12472 | trading_bot.execution.reconciliation_driver | 1 position(s) carry protection this bot does not trust event=reconciliation_untrusted count=1 symbols=BTCUSDT detail="BTCUSDT leg SL was requested and does not rest: the point query reports CANCELED; BTCUSDT leg TP was requested and does not rest: the point query reports CANCELED"
    2026-10-02T12:02:00Z | CRITICAL | pid=12472 | trading_bot.execution.reconciliation_driver | BTCUSDT has no protection resting and no fill to book; the ledger and the account may have parted event=exit_unbookable symbol=BTCUSDT state=diverged quantity=0.02083000 venue_order_list_id=413202 reason="BTCUSDT leg SL was requested and does not rest: the point query reports CANCELED; BTCUSDT leg TP was requested and does not rest: the point query reports CANCELED" resolution="OPERATOR ONLY: no leg reported a fill, so there is nothing to price and nothing is booked. The position is retained and stays untrusted, so entries are refused portfolio-wide until it is reconciled by hand."
    2026-10-02T12:02:01Z | INFO | pid=12472 | trading_bot.execution.executor | Close planned for BTCUSDT: sell event=close_planned symbol=BTCUSDT decision=sell detail="no protective leg executed across 2 leg(s); the position is still open and the sell may be dispatched" reads=2 elapsed_s=0.830626 refused_as=close_sell_reserved candle_time=2026-10-02T12:01:59.999000+00:00 list_client_order_id=tb1-BTCUSDT-1790939579999-0-L sl_status=CANCELED sl_executed=0E-8 tp_status=CANCELED tp_executed=0E-8
    2026-10-02T12:02:01Z | WARNING | pid=12472 | trading_bot.execution.executor | Cancelling protection to close BTCUSDT; the position is unprotected from here event=close_window_open symbol=BTCUSDT venue_order_list_id=413202 quantity=0.02083000 candle_time=2026-10-02T12:01:59.999000+00:00
    2026-10-02T12:02:02Z | INFO | pid=12472 | trading_bot.execution.executor | Order list for BTCUSDT was already terminal at cancel event=close_cancel_already_terminal symbol=BTCUSDT venue_order_list_id=413202 candle_time=2026-10-02T12:01:59.999000+00:00
    2026-10-02T12:02:03Z | INFO | pid=12472 | trading_bot.execution.executor | Closed BTCUSDT event=close_booked symbol=BTCUSDT quote_total=1798.54552000 quote_total_source=venue realised=-2.5812536000 order_id=8756208 quantity=0.02083000 fee=0E-8 fee_asset=USDT fills=1 filled_at=2026-10-02T12:02:03.122000+00:00 order_created_at=2026-10-02T12:02:03.122000+00:00 candle_time=2026-10-02T12:01:59.999000+00:00
    2026-10-02T12:03:00Z | INFO | pid=12472 | trading_bot.engine.live_engine | Signal CLOSE BTCUSDT (death cross: SMA(20)=86467.766 crossed below SMA(50)=86471.894) from sma_crossover

**The `nothing_to_close` refusal, verbatim**, follows it:

    2026-10-02T12:03:00Z | INFO | pid=12472 | trading_bot.engine.modes | Risk refused BTCUSDT at nothing_to_close event=risk_refused symbol=BTCUSDT timeframe=1m action=CLOSE signal_ts=2026-10-02T12:02:59.999000+00:00 stage=nothing_to_close reason="nothing to close: no open position in BTCUSDT"

then `2026-10-02T12:05:08Z | INFO | pid=12472 | __main__ | Received SIGINT;
shutting down gracefully` and `12:05:10Z ... Trading engine stopped
event=engine_stopped clean_shutdown=True`.

**Against the sheet's expected lines** (`F:\trading bot\deploy\arm_tools\A4_sheet.md`
section 9): every one is present, in the order listed. **The absences are
counted over the same 193 lines:** `Unclassified message` 0,
`close_cancel_failed` 0, `dispatch_refused` 0, `boot_symbol_blocked` 0;
`close_cancel_already_terminal` 1, `exit_unbookable` 1, `CRITICAL` 2 (the
boot's and the exit's).

**The booking reconciles twice.** The realised figure is the exit's quote total
less the entry's:

    1798.54552000 - 1801.12677360 = -2.58125360

and the entry's `1801.12677360` is the owner's figure; the log alone gives it
back as `1798.54552000 + 2.5812536000`, so it is a consequence of the booking
line, not an independent read. The balance is independent. Pid 11844's
root read `90167.24816300` free at `07:28:35Z`; adding its three closed round
trips and subtracting this position's entry cost gives

    90167.24816300 + 4.6440308 - 1.775186 - 3.609839 - 1801.1267736 = 88365.3803952

which is pid 12472's `88365.38039520` at `12:01:10Z`, to the digit.

**What this measures, and the venue fact that matters.** On the real venue a
restored position whose list was cancelled while the bot was down was sold
once, by R3, on the first candle after the relaunch, and booked. The cancel
the close path made on that list was answered by the mapped `-2011 'Unknown
order list sent.'` and read as the benign `OrderNotFoundError`: the line
`close_cancel_already_terminal`, not `close_cancel_failed`. This is C35
(`244aa6b`) confirmed against the venue, and it closes the loop `M5l-141` and
`M5l-161` opened.

### The owner's ruling, and A2 (`M5l-169`)

The owner's ruling at M5l P87, recorded verbatim:

> *"The P-3k gate is satisfied: A1 (hard kill, restore), A2 (protective fill
> while down, booked at boot) and A4 (protection cancelled while down, R3 sells
> once) passed on the supervised Testnet run of 2026-10-01/02, A1 and A2 at
> d1074c6 and A4 at 5e22bc6. A2's Ctrl+C stop does not change the path it
> tests. P-3k no longer blocks live trading. The fee-capture and base-asset-
> netting gates remain, so live trading stays blocked."*

**So A2 is PASS by the owner's ruling, and `M5l-166` is resolved**: the
`boot_exit_booked leg=SL` line recorded above stands as A2's evidence, the
stop before it having been SIGINT and not a hard kill. This ledger records
the ruling; it does not judge it.

### The deviations from the written procedure, and what the run left behind

- **The `arm_notes.txt` appends came late** (`M5l-167`'s shape, again,
  `M5l-174`). The file now holds ten lines, the two new ones being
  `boot_provenance` lines for pid 11844 (`07:28:32Z`) and pid 12472
  (`12:01:05Z`); the file's modification time, `12:01:17.9Z`, is 12 seconds
  after the relaunch. **None of the sheet's pre-launch lines is in it**, so no
  store SHA-256 was recorded before either launch, and the owner reports that
  one append landed before a relaunch and recorded the previous launch. The
  file cannot show which, because its earlier modification times are
  overwritten; the owner's account is recorded as the owner's.
- **P86 installed with the old build's frozen dependencies as constraints**
  (`M5l-172`). `pip install -c <constraints> "binance-trading-bot @
  git+file:///...@5e22bc6..."`, the constraints being `pip freeze` of the
  retired clone less its own project line, 38 lines. This is not in
  `CLAUDE.md`'s written procedure, which installs without constraints and so
  lets the transitive dependencies float. MEASURED: the new venv's `pip freeze`
  differs from the old one's in one line, the project's own commit. The
  written procedure is unchanged by this entry.
- **P86's H4 outcome** (`M5l-171`). P86 reported *"no Python process at the
  start"* while the old clone's pid 3608 logged `Received SIGINT` at
  `2026-10-02T07:14:06Z`. **That is timing, not a defective check.** P86's H4
  command was issued at `2026-10-02T07:15:32Z`, from the session transcript's
  own timestamp, 86 seconds after the stop (`engine_stopped` at `07:14:08Z`),
  and the next command's `date -u` read `07:15:48Z`. And the check was tested
  directly at P87: a scratch script run by a venv interpreter under a path
  containing a space, with the venv built from the same Store interpreter as
  the clones, was found by `Get-CimInstance Win32_Process` filtered on
  `Name -match 'python'` and by `Get-Process -Name python*, py*`, which listed
  **two** processes -- the venv's `python.exe`, parent 22632, and its child
  `python3.12.exe` -- and by a filter on the command line. So the check sees a
  bot of this tree; it saw none because none was running.
- **The old clone's extra round trip before its stop.** Pid 3608, after
  booking A2's stop at boot, opened BTCUSDT list 410028 (`06:57:03Z`) and
  closed it (`07:00:03Z`, `realised=-0.991718400`), and stopped at
  `07:14:06Z` by SIGINT. So the store P86 copied (`3B6EE9A3...5B40D`) held
  ledger day 2026-10-02 at `-108.8296010000`, not the `-107.8378826000` the
  P86 prompt expected. The new clone's store was loaded at P86 and read the
  former.
- **The old clone's directory** is now `d1074c646cf6.retired-20261002T072802Z`,
  by the owner. P86 could not rename it: a Windows Terminal window opened with
  `-d` on it held the directory open, and a directory a shell is inside cannot
  be renamed (`M5l-173`). Its `.venv` had already been renamed to
  `.venv.disabled`. At P87 the only directory under `F:\trading bot\deploy`
  holding `.venv\Scripts\python.exe` is `5e22bc6a33ed`.

### The tools' SHA-256, as read at P87

| File | SHA-256 |
|---|---|
| `F:\trading bot\deploy\arm_tools\read_state.py` | `fd0548d4f57dabb1a2e5c855b29ae6c3e09cd69edaaf0284be4dd459b854bcd5` |
| `F:\trading bot\deploy\arm_tools\preflight.py` | `b35992dc30ab461a51613a92f3387f7cb80baef41a4044ac10b30211cbdcad64` |
| `F:\trading bot\deploy\arm_tools\A4_sheet.md` | `a587a43efdb1512ccdaab4e18d9b3e187c1c20f4e7ba413bd9c61dd7ae7fde4e` |
| `F:\trading bot\deploy\arm_notes.txt` (10 lines) | `e31a74e657151b0465bcf1bae7665ef8ad48ba1bae7733ad6136f6170eb2e5d7` |

`read_state.py` is the helper P84 wrote and P86 left unchanged.

### The stop-loss fill that A2 booked (`M5l-170`)

A2's booking line records a stop that filled far from its trigger. BTCUSDT list
402643's stop was requested at `83214.72` (`order_placed` `stop_loss=83214.72`,
pid 21844, `20:06:04Z`). It filled at `2026-10-02T05:25:58.122Z` in two fills,
at `79800.00` and `79749.94` by the owner's account of the venue's fills, which
are not in the log. The log's own figures are consistent with them:
`quantity=0.02126000` and `quote_total=1695.60837380` give an average of
79755.803, between the two, and the two prices fit a split of 0.00249 and
0.01877 of the 0.02126.

    stop 83214.72 against 79800.00      4.10% below the trigger
    stop 83214.72 against 79749.94      4.16% below the trigger
    stop 83214.72 against the average   4.16% below the trigger

So the fill is **about 4.2% beyond the stop**. The loss booked is
`-107.8378826000`; at the stop itself it would have been about `-36.1`
(`0.02126 x (84912.97 - 83214.72)`, from the entry limit, which is the order's
price and not its fill). **`STOP_LOSS` guarantees the exit and not the
price**: it triggers a market order, which takes what the book gives.
`CLAUDE.md` already says it of booking at the requested stop price -- *"a
stop-market fills at whatever the book gives"* -- and this is that statement on
a real fill, the largest loss recorded in this section. **It is marked for a QC
review of the protective order type before live trading.** No type is chosen
here.

### What this section decides (P87)

**Nothing beyond what the owner's ruling above states.** A1, A2 and A4 are
recorded, each beside its instrument; the owner has ruled the P-3k gate
satisfied; the fee-capture and base-asset-netting gates remain.

## 26. M5l's observation run at 51a5f27: the start record, the census and the venue cross-check

Recorded at M5l P97 (C56), from the clone `F:\trading bot\deploy\51a5f2711a09` after
the owner stopped the bot. **THE START RECORD BELOW IS WRITTEN AFTER THE LOG WAS
READ**, which is the shape `M5l-051` recorded for the first evidence run: P96's
run sheet asked for the start to be noted in `arm_notes.txt` and no `OBS launch`
line was written, and no commit recorded the start before P97 read the log. The
figures in it are the log's own `boot_provenance` line, so the record is accurate
and its timing is not what the doctrine asks (`M5l-256`).

An observation log, so this section only adds. Every figure sits beside the command
or read that produced it. **Every count states its instrument**, because 249, 251
and 252 are all correct line counts of the same file.

### The start record (taken from the log's `boot_provenance` line, pid 24980)

| Field | Value |
|---|---|
| `code_commit` | `51a5f2711a0984697a915b192bb481f65949567f` |
| `checkout_commit`, `commits_agree` | the same, `true` |
| `config_sha256` | `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0` |
| `config_tracked`, `checkout_dirty`, `code_intact` | `true`, `false`, `true` over 70 files |
| `verdict` | `accepted`, `install_kind=vcs` |
| UTC instant | `2026-10-03T20:08:25Z` (process banner `20:08:24Z`) |
| pid, clone | 24980, `F:\trading bot\deploy\51a5f2711a09` |
| interpreter | Python 3.12.10, package 0.1.0, module under the clone's own `.venv` |

Instrument: `Select-String -Path logs\trading_bot.log -Pattern 'boot_provenance'`,
read at P97. P96's dry boot of `strategies` left an identical line under **pid
10720** at `2026-10-03T19:58:03Z`, which is excluded throughout.

### The capture

Read at P97 with `Get-FileHash` (SHA-256, lowercase) after a check that no Python
process was running (`Get-CimInstance Win32_Process`, 0 found).

| File | SHA-256 | Size and lines |
|---|---|---|
| `logs\trading_bot.log` | `023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb` | 53021 bytes; 251 newline characters (`wc -l`), 249 non-empty lines (`Measure-Object -Line`), 252 elements of `split("\n")`; CRLF endings, 251 CR |
| `logs\normalize.log` | `7c834cbeb765e2380b0b86c922ba57a0949ee2cb6d044e735f3890c411a95930` | 253 bytes, 1 line |
| `data\state.json` (END of run) | `d2d83eed081bb14ae00469d39bd136b58d989bee80f601f0aed9d9dbe9f1c2d4` | 1926 bytes |
| `F:\trading bot\deploy\arm_notes.txt` | `828c91f5568af47f5d388769a2b31de40fa23bd06de711df6a0bdaa9e8f2640c` | 11 lines; ONE is this run's: the `boot_provenance` line, pid 24980 |

The log carries 237 records tagged `pid=24980` (`p97_reads.py`, lines containing
`| pid=24980 |`): 230 `INFO` and 7 `WARNING`, no `ERROR`, no `CRITICAL`. The other
15 elements of the 252 are 2 records tagged pid 10720 (the dry boot's banner start and
provenance line) and 13 untagged ones: 12 banner continuation lines, 6 per boot, and the
trailing empty element. Reads left the store and the log
unchanged: `Get-FileHash` before and after each read, equal.

The tools, as read at P97 (`Get-FileHash`), all under `F:\trading bot\deploy\arm_tools`:

| File | SHA-256 |
|---|---|
| `read_ledger.py` | `fe44c15a5e88b3e77bd657931fb925ca598b2ea37a8eb3cc8949a74a75737534` |
| `p97_reads.py` | `1f11761c6a9e59037fd96b540313474a07969127843eefa1303a52285b169724` |
| `p97_ledger.py` | `c7d537a82d1eb008e418fc68eba1a99b356b838d26defd593ec0d5a276f82b9f` |
| `observation_sheet.md` | `d7a4c68f948949c3f112264489d5321b826288fd7b953f0472c2ed7bd0d7a2f4` |

`p97_reads.py` is GET only (`get_order`, `get_my_trades`, raw `get_klines`) and
`p97_ledger.py` is offline on copies. Neither prints a key.

### (a) The launch

**One launch, pid 24980**, and no restart. Its boot printed no `boot_positions_resolved`
line, and the store it booted from held no position or pending record (below).
It ended as the owner asked: `2026-10-04T04:29:49Z` `Received SIGINT; shutting down
gracefully`, then `2026-10-04T04:29:50Z`
`Trading engine stopped event=engine_stopped clean_shutdown=True`.

- Run length, first record to last: `20:08:24Z` to `04:29:50Z` = 30086 s (8 h 21 m 26 s).
- Engine started `20:08:29Z`, stopped `04:29:50Z` = **30081 s = 8.356 h**, the
  denominator for every rate below.
- **The owner's stop instant.** P97's prompt carried the placeholder
  `<<< UTC instant from the owner >>>` unfilled, and `arm_notes.txt` holds no
  `OBS stop` line, so the stop is the log's own `04:29:49Z` (`M5l-256`).
- **Flat at stop: confirmed, three ways, none of them the owner's read.** The
  last `close_booked` is `04:11:02Z` and no `order_placed` follows it; the end
  store holds `positions=0 pending=0` (`read_ledger.py`); and a GET read at
  `2026-10-04T04:35:52Z` (`preflight.py`, **a read of that instant and of no
  other**) shows `open_orders=0 live_lists=0` and base `0E-8` free and locked on
  both symbols.

### (b) The normaliser, and both SHAs chained

`logs\normalize.log`, verbatim:

    2026-10-03T20:08:10.511157+00:00 normalised store=data\state.json values_changed=20 store_sha256_before=710db3ae0a695f0d65e652d899aff6cd528dea4bad709a1b7fc906eb32c93d3f store_sha256_after=7755930768628f15c692f15654b259e3e44fa0d810b0eb49f124a1e478c6de21

- **`before` equals P96's copied store.** P96 recorded `710DB3AE...C93D3F` for the
  retired clone's `state.json` and for its copy into the new clone, SHA-256-equal
  (`Get-FileHash`). `p97_ledger.py` hashed the retired clone's file again at P97
  and printed `equals normaliser 'before': True`.
- **`after` is the store the run booted from, REPRODUCED rather than read.** The
  start store no longer exists as a file: the bot rewrote it. `p97_ledger.py`
  copied the retired clone's store to a temp directory, ran the normaliser's own
  `normalise_state` and `store.save` on the copy, and the result's SHA-256 is
  `7755930768628f15c692f15654b259e3e44fa0d810b0eb49f124a1e478c6de21`, **equal to
  the logged `after`**, with `changes=20`. So the chain is
  `710db3ae... -> 7755930768... -> d2d83eed...` (the end store).
- The apply came 15 s before the launch: `20:08:10Z` against the banner at
  `20:08:24Z`. `P96`'s dry run had measured the same 20 values and no refusal.

### (c) Natural gaps (`M5l-202`)

| Event, counted over the whole log | BTCUSDT/1m | ETHUSDT/5m |
|---|---|---|
| `bars_gap_detected` | 0 | 0 |
| `buy_refused_bars_gap` | 0 | 0 |
| `bars_contiguous_again` | 0 | 0 |
| `missing_bars` (sum) | 0 | 0 |

Instrument: `p97_reads.py`, `sum(1 for ln in lines if pattern in ln)` over the 252
elements of the log, each pattern 0. **The rate is 0 events per symbol per hour of
run time (0 in 8.356 h for each symbol).** The detector is armed in this build:
`_append` in `data/market_data.py` logs `bars_gap_detected` at `WARNING` when a
bar's `open_time` is more than one timeframe after the last, and every `WARNING`
in this log is accounted for under (g).

**An absence is argued here from presence, as the doctrine asks.** The bot's own
log has no per-bar line, so on its own it cannot say bars arrived. The positive
record is the venue's: `p97_reads.py` read the klines by GET over the run window
(raw `get_klines`, `startTime=2026-10-03T20:08Z`, `endTime=2026-10-04T04:30Z`):

| Pair | Bars returned | First open | Last open | Expected between | Missing | Bars with zero trades |
|---|---|---|---|---|---|---|
| BTCUSDT/1m | 503 | `20:08:00Z` | `04:30:00Z` | 503 | **0** | **0** |
| ETHUSDT/5m | 101 | `20:10:00Z` | `04:30:00Z` | 101 | **0** | **0** |

(Field 8 of each kline, the trade count, read as the zero-trade test.) So over this
window the venue omitted no interval on either committed pair, and the detector
agrees with it.

**What this does NOT measure, and it is `M5l-202`'s own question.** `M5l-202` asks
whether Binance omits a kline for an interval with NO trades. Neither pair had one,
so the omission behaviour was **not exercised**, and for an illiquid pair it stays
UNMEASURED. What is measured is the committed pairs' natural-gap rate over 8.356 h:
zero.

### (d) The watchdog

Every pattern counted over the whole log, 0: `feed_silent`, `feed_silent_critical`,
`feed_resumed`, `event_loop_lagging`, `event_loop_recovered`, `handler_chain_slow`,
`handler_chain_recovered`. **No heartbeat, lag, slow-chain or episode line exists, and
so no recovery line.** `FeedWatchdog` is armed and started by `live_system` in this
build (`engine/modes.py`), and its events are `WARNING` or `INFO` or `CRITICAL`; the
log's only 7 `WARNING`s are accounted for under (g). **This is the watchdog being
QUIET on a healthy feed, which is a measurement of no false positive over 8.356 h,
and not a measurement that it fires.** `M5l-198`, the cause of the 229 s stall, is
unmeasured by this run: nothing stalled.

### (e) The stream

`stream_transient_error`: 0. `disconnect`: 0 and `reconnect`: 0 as substrings of any
line. In `exchange/websocket_client.py` `_run` a disconnect logs
`Market-data stream disconnected (...); reconnecting` at `WARNING`, a transient
library error logs `stream_transient_error` at `WARNING`, and giving up logs at
`ERROR`, so each would be among the 7 `WARNING`s or the 0 `ERROR`s counted under
(g). The venue's klines in (c) show the feed delivered every interval it was asked
for.

### (f) Every booking line

Six `close_booked`, all `BTCUSDT`, all `quote_total_source=venue`, `fee=0E-8
fee_asset=USDT`, `fills=1`. **No `boot_exit_booked`, no `exit_booked`** (the driver's
line), no other booking event: counts 0. All six were the strategy's own `CLOSE`
sequence, a `MARKET` sell after the protective list was cancelled; no protective leg
filled and ETHUSDT never opened a position (its only two mentions are the seed and
engine-start lines).

`p97_reads.py` re-read each from the venue by GET: the entry order by its derived
client id (`client_order_id(symbol, entry_bar_time, WORKING, generation=0)`) with
`get_order` and `get_my_trades`, the exit by the line's `order_id` with the same two
calls. Recomputed in `Decimal`: `realised = exit fills quote sum - entry fills quote
sum - exit fee in USDT`.

| # | Booked (UTC) | Exit order | Entry order | Exit quote total | Entry quote total | `realised` (log) | Exponent | Recomputed | Equal |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `2026-10-03T23:10:02Z` | 9104494 | 9092733 | 1801.99760000 | 1800.89229260 | 1.10530740 | -8 | 1.10530740 | yes |
| 2 | `2026-10-03T23:43:02Z` | 9108003 | 9107931 | 1800.97528320 | 1800.97549560 | -0.00021240 | -8 | -0.00021240 | yes |
| 3 | `2026-10-04T00:02:03Z` | 9110852 | 9108610 | 1800.59976000 | 1800.77690160 | -0.17714160 | -8 | -0.17714160 | yes |
| 4 | `2026-10-04T00:45:02Z` | 9116405 | 9111083 | 1800.38998150 | 1801.11074000 | -0.72075850 | -8 | -0.72075850 | yes |
| 5 | `2026-10-04T02:45:03Z` | 9130054 | 9123245 | 1802.00000000 | 1801.46577500 | 0.53422500 | -8 | 0.53422500 | yes |
| 6 | `2026-10-04T04:11:02Z` | 9138444 | 9133358 | 1800.80651410 | 1800.76235570 | 0.04415840 | -8 | 0.04415840 | yes |

- **`entry_quote_total` present on 6 of 6**, and equal in value AND exponent to the
  venue's entry fills sum and to the entry order's `cummulativeQuoteQty` (each entry
  one fill). The exit total equals the exit fills sum and the order's total, 6 of 6.
- **No mismatch.** The logged `quantity` equals the fills' quantity on every line
  and each close's `list_client_order_id` matches its placement.
- **Fees.** Every exit fee is `0E-8 USDT`; every entry fill's commission is
  `0E-8 BTC`, so the six lines carry no non-zero fee and **the base-quantity
  netting question is again not exercised** (`M5l-054`'s observation, repeated).
- Sum of the six logged `realised`: **0.78557830**; sum of the six recomputed: the
  same.
- **The account moved by that figure.** The boot's `Composition root ready` line
  reads `90163.92591520 USDT free` (`20:08:28Z`) and the GET at `04:35:52Z` reads
  `USDT free=90164.71149350`. The difference is **+0.78557830**, to the last digit.
  It is exact equality, so it also says no other cash moved on the account in the
  interval, a one-writer assumption this agreement supports and does not prove.

### (g) Every WARNING, ERROR and CRITICAL not covered above

7 `WARNING`, 0 `ERROR`, 0 `CRITICAL` (`p97_reads.py`, records tagged `pid=24980`).
Under the cap of 60, all shown, grouped:

- **1 x** `2026-10-03T20:08:28Z | WARNING  | pid=24980 | trading_bot.engine.modes | 499 asset(s) are EXCLUDED FROM EQUITY -- no enabled USDT pair prices them, so equity is UNDERSTATED by their combined value, which cannot be computed here. Set logging.level to DEBUG for the per-asset list. event=boot_assets_excluded excluded_count=499 quote_asset=USDT`
- **6 x** `Cancelling protection to close BTCUSDT; the position is unprotected from here event=close_window_open symbol=BTCUSDT venue_order_list_id=<id> quantity=<q> candle_time=<t>`, the close sequence's expected warning, one per close: `23:10:00Z` list 435000 `0.02126000`; `23:43:01Z` 436087 `0.02124000`; `00:02:01Z` 436135 `0.02124000`; `00:45:01Z` 436245 `0.02123000`; `02:45:01Z` 437119 `0.02125000`; `04:11:01Z` 437929 `0.02123000`.

The other events, `INFO`, by count (`p97_reads.py`): `reconciliation_pass` 170,
`intent_dispatched` 12 (6 `BUY`, 6 `CLOSE`), `order_placed` 6, `close_planned` 6,
`close_booked` 6, `risk_refused` 1 (`2026-10-03T20:46:00Z`, a `CLOSE` signal with
`nothing_to_close`), `boot_provenance` 1, `engine_stopped` 1. **All 170 passes read
`positions=1 calls=1 queries=2 states="active=1"`** (`Select-String` count 170 of 170),
the first `2026-10-03T21:39:00Z`, the last `2026-10-04T04:10:01Z`.

### (h) Ledger reconciliation

`p97_ledger.py`, offline on copies; the end store unchanged after it
(`Get-FileHash`, `d2d83eed...`).

| Figure | Start (reproduced) | After the six bookings, expected | End store | Equal |
|---|---|---|---|---|
| `ledger.pnl_date` | 2026-10-02 | 2026-10-04 | 2026-10-04 | yes |
| `ledger.realised_pnl` | -112.15184880 | -0.31951670 | -0.31951670 | yes, exponent -8 |
| `ledger.trades_count` | 6 | 4 | 4 | yes |
| `lifetime_realised` | -340.20691430 | -451.25366810 | -451.25366810 | yes, exponent -8 |
| `daily_history` rows | 18 | 20 | 20 | yes |
| `daily_history[2026-10-02]` | absent | -112.15184880, 6 trades | -112.15184880, 6 trades | yes |
| `daily_history[2026-10-03]` | absent | 1.10509500, 2 trades | 1.10509500, 2 trades | yes |
| positions, pending | 0, 0 | 0, 0 | 0, 0 | yes |

**The day rolls, shown.** The ledger rolls LAZILY, at the first booking after
midnight, not at midnight:

    first booking 2026-10-03T23:10:02Z  rolls 10-02 -> 10-03: history[10-02] = -112.15184880, 6 trades
      bookings 1.10530740 and -0.00021240 on 10-03: ledger 1.10509500, 2 trades
    first booking 2026-10-04T00:02:03Z  rolls 10-03 -> 10-04: history[10-03] = 1.10509500, 2 trades
      bookings -0.17714160, -0.72075850, 0.53422500, 0.04415840 on 10-04: ledger -0.31951670, 4 trades

- **`lifetime_realised` moves at a ROLL, not at a booking, and a first expectation
  of this section was wrong about it** (`M5l-254`). Adding the six bookings to the
  start lifetime predicts `-339.42133600`; the store holds `-451.25366810`. The
  difference, `-111.04675380`, is `-112.15184880 + 1.10509500`: the two days that
  rolled. `Portfolio.record_realised_pnl` adds the OUTGOING day to the lifetime when
  it rolls (`lifetime = (self.lifetime_realised or Decimal(0)) +
  outgoing.realised_pnl`) and the field's own comment says it is *"realised P&L
  across every day that has rolled"*. The store behaved as documented; the
  expectation was wrong. The start lifetime is itself the sum of the 18 history rows:
  `Decimal` sum of the retired store's `daily_history[*].realised` = `-340.206914300000000000000000`,
  equal to its `lifetime_realised` by value, so the open day is never in it.
- **Raw JSON, start against end:** exactly eight paths differ, the two new
  `daily_history` rows (four paths), `ledger.pnl_date`, `ledger.realised_pnl`,
  `ledger.trades_count` and `lifetime_realised`. Every one of the 18 start history
  rows is identical in value and exponent in the end store.
- **Every decimal-looking string in the end file is at exponent -8** (22 of 22:
  `read_ledger.py` counts 22 and `p97_ledger.py` tests every one at -8). At the start, 20 of the 20 were at -24 (5) or -10 (15).
- **Difference, to the last digit: none.**

### What was measured of `M5l-229`

The active store DID carry exponent -24, and more. In the store copied at P96
(`710DB3AE...C93D3F`, schema 2, read by `read_ledger.py`): **5 figures at -24** (the
`2026-09-10`, `-09-20`, `-09-21` and `-09-23` rows and `lifetime_realised`) and **15
at -10** (14 history rows and the open day's `realised_pnl`). The normaliser's dry
run, from the new clone's root without `--apply`, would have changed all 20, refused
none, exited 0 and left the file's SHA unchanged (P96). The owner's `--apply` changed
20 values (`values_changed=20`), each equal in value, and the chain above proves the
file the bot booted from. **Lossless: the end store's history rows and every figure
the run did not touch are equal to the start's by value and exponent.**

**What stays UNMEASURED: where the 15 figures at -10 come from** (`M5l-255`). `C48`
and `C49` explain -24, and `P-3h` names -10, -9 and -8 as the other exponents seen,
without a cause. All six of this run's bookings are at -8, so for these six the
current code writes -8; why earlier days were at -10 is not read here.

> **ANNOTATED AT M5l P98 (R7): *"What stays UNMEASURED: where the 15 figures at -10
> come from"* IS NO LONGER TRUE (`M5l-255` IS RESOLVED, BY THE PROJECT OWNER'S RULING).**
> The ruling, as the P98 prompt named it: *"M5l-255 resolved by M5l-209."* `M5l-209`
> measured that the entry term was `average_price x quantity` and that 103 of the 106
> booking lines a replay covered were single-price entries at price exponent -2; with a
> quantity at exponent -8 the product is at -10, and a day's `realised` that held such a
> booking carried -10. The replay is MEASURED and the exponent arithmetic is REASONED
> from it: no store's -10 figure was traced booking by booking. **What survives:** the
> measurements above, and that all six of this run's bookings are at -8, which is what
> C48's `exit total - entry total` form gives.
>
> **One more figure in this section has moved.** The run sheet's SHA-256 in the tools
> table is the sheet *as read at P97*, and stays true of that instant. The sheet was edited
> at P98, the `OBS launch` and `OBS stop` note lines dropped by the owner's ruling, and its
> SHA-256 is now `9bc79a47f43613a1460e0be1ef7cbc9e9333304a80d7b70862c74c733d681374`.

### What this section decides (P97)

**Nothing.** It records a clean run of the committed code at `51a5f27`: 8.356 h, six
strategy-driven round trips, every booking equal to the venue's fills, the ledger
chained from the normaliser's `after` to the end store with no difference, and none of
the feed-health events observed. It does not show that those events fire, and it does
not exercise a protective-leg fill, a restart, a held position or an ETHUSDT position.
