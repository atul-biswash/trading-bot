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

## 27. M5m S0: the trade census of record, and how it differs from the untracked census

Recorded at M5m P99 (C4), after the commit that landed `scripts/trade_census.py`
(`cf64d90`). An observation log, so this section only adds. **Every figure states its
instrument**, and every figure of the census of record comes from the one command below,
run on the one capture.

### Why this census, and not the one `docs/NEXT_MILESTONE.md` quotes

That file's per-trade census was taken by an untracked reviewer script over an
owner-supplied capture, `trading_bot.log`, SHA-256
`641778e50a42ca44101b28b9ce342431352544bca9855711d3164bba24fc32b4`, last record
`2026-09-24T03:58:40Z`. **That capture is not on disk** (the search is recorded under S0's
annotation there, `M5m-006`), so S0's acceptance, *"on the capture `641778e5…` it
reproduces every figure in the census to the digit"*, could not be run. The owner ruled
at P99, amendment 2, (b), that S0's acceptance becomes reproducing the tool's figures on
the M5k capture and that its output is the census of record; the ruling is quoted
verbatim under S0 in `docs/NEXT_MILESTONE.md`.

### The instrument and the capture

| Item | Value |
|---|---|
| Tool | `scripts/trade_census.py` at `cf64d90`, SHA-256 `926bdd4674d7fe9fa418fb5e8b67f3d089012255ba8f478492a043fbbe35d9bb` |
| Command, from the repository root | `.venv\Scripts\python.exe scripts\trade_census.py "F:\trading bot\files\binance-trading-bot\m5j-evidence\trading_bot.m5k-close-20260925T182818Z.log"` |
| Capture | `trading_bot.m5k-close-20260925T182818Z.log`, SHA-256 `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528` (the digest section 19 records), 5,074,996 bytes, 26,126 lines |
| Instrument for the figures | the tool's own output, redirected to a file by git-bash `>`; exit status 0; 260 lines. Python on this machine writes a redirected stdout with CRLF line endings; the output below is embedded with LF, and with nothing else changed |
| Reads | the tool opens the capture read-only and writes nothing; the capture's SHA-256 was recomputed with `sha256sum` at P99 after the runs and equals the digest above |

### The census of record: the tool's output, verbatim

```
==========================================================================
CAPTURE
==========================================================================
  path   : F:\trading bot\files\binance-trading-bot\m5j-evidence\trading_bot.m5k-close-20260925T182818Z.log
  bytes  : 5074996
  lines  : 26126
  sha256 : 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528
  naive-stamp offset : 6:00:00 from 20 naive lines, 20 agreeing
  placements : 185
  bookings   : 165
  anomalies  : 0
  bookings matched to a placement : 165 of 165
  placements never booked          : 20
  quantity differs from its placement : 0

==========================================================================
PER BOOKING  [sha256 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528]
==========================================================================
     1 line 16963  2026-09-04T09:23:02Z ETHUSDT  LEG/SL  held    n/a qty 0.72200000 realised     -46.3007 return   -2.5541% placement line 16704
     2 line 17109  2026-09-04T12:47:02Z BTCUSDT  LEG/SL  held    n/a qty 0.02240000 realised     -34.9848 return   -1.9305% placement line 16639
     3 line 17215  2026-09-04T21:46:02Z BTCUSDT  LEG/SL  held    n/a qty 0.02268000 realised     -54.5552 return   -3.0131% placement line 17143
     4 line 17798  2026-09-06T00:15:03Z ETHUSDT  CLOSE   held   150m qty 0.72670000 realised      -6.9909 return   -0.3862% placement line 17694
     5 line 17830  2026-09-06T00:51:03Z BTCUSDT  CLOSE   held    81m qty 0.02268000 realised       1.4531 return    0.0803% placement line 17764
     6 line 17897  2026-09-06T02:14:03Z BTCUSDT  CLOSE   held    68m qty 0.02265000 realised       0.9817 return    0.0542% placement line 17845
     7 line 17985  2026-09-06T04:16:03Z BTCUSDT  CLOSE   held    61m qty 0.02265000 realised       1.1078 return    0.0612% placement line 17941
     8 line 18156  2026-09-06T19:10:01Z BTCUSDT  CLOSE   held    99m qty 0.02271000 realised       4.3848 return    0.2423% placement line 18076
     9 line 18242  2026-09-06T21:09:03Z BTCUSDT  CLOSE   held    46m qty 0.02265000 realised       0.8122 return    0.0449% placement line 18207
    10 line 18268  2026-09-06T21:37:02Z BTCUSDT  CLOSE   held    25m qty 0.02263000 realised      -1.9077 return   -0.1054% placement line 18248
    11 line 18387  2026-09-07T00:17:03Z BTCUSDT  CLOSE   held    97m qty 0.02264000 realised       7.0974 return    0.3921% placement line 18316
    12 line 18457  2026-09-07T02:00:03Z ETHUSDT  CLOSE   held   500m qty 0.72600000 realised       7.8118 return    0.4316% placement line 18086
    13 line 18488  2026-09-07T03:06:03Z BTCUSDT  CLOSE   held    38m qty 0.02263000 realised      -1.2648 return   -0.0699% placement line 18461
    14 line 18510  2026-09-07T04:15:03Z ETHUSDT  CLOSE   held    20m qty 0.72420000 realised      -1.7960 return   -0.0992% placement line 18492
    15 line 18530  2026-09-07T04:41:04Z BTCUSDT  CLOSE   held    17m qty 0.02271000 realised      -1.3524 return   -0.0747% placement line 18514
    16 line 18583  2026-09-07T06:00:02Z BTCUSDT  CLOSE   held    68m qty 0.02271000 realised       1.6735 return    0.0925% placement line 18534
    17 line 18628  2026-09-07T19:26:02Z BTCUSDT  CLOSE   held    30m qty 0.02285000 realised      -0.0500 return   -0.0028% placement line 18603
    18 line 18663  2026-09-07T20:13:03Z BTCUSDT  CLOSE   held    41m qty 0.02284000 realised      -0.7768 return   -0.0429% placement line 18632
    19 line 18710  2026-09-08T20:48:02Z BTCUSDT  CLOSE   held    37m qty 0.02305000 realised       0.1381 return    0.0076% placement line 18683
    20 line 18742  2026-09-08T21:38:02Z BTCUSDT  CLOSE   held    35m qty 0.02304000 realised      -2.0280 return   -0.1120% placement line 18714
    21 line 18853  2026-09-08T22:43:02Z BTCUSDT  CLOSE   held    29m qty 0.02306000 realised       0.4815 return    0.0266% placement line 18746
    22 line 18885  2026-09-08T23:20:02Z BTCUSDT  CLOSE   held    25m qty 0.02305000 realised      -1.3994 return   -0.0773% placement line 18857
    23 line 18976  2026-09-09T01:26:03Z BTCUSDT  CLOSE   held    80m qty 0.02304000 realised       2.2782 return    0.1259% placement line 18919
    24 line 19027  2026-09-09T23:08:03Z BTCUSDT  CLOSE   held    28m qty 0.02324000 realised       1.8178 return    0.1002% placement line 19003
    25 line 19091  2026-09-10T00:30:04Z BTCUSDT  CLOSE   held    81m qty 0.02321000 realised       3.7821 return    0.2085% placement line 19031
    26 line 19139  2026-09-10T01:33:03Z BTCUSDT  CLOSE   held    23m qty 0.02313000 realised      -6.4877 return   -0.3577% placement line 19120
    27 line 19198  2026-09-10T02:50:05Z ETHUSDT  CLOSE   held   145m qty 0.73480000 realised       3.8136 return    0.2102% placement line 19082
    28 line 19235  2026-09-10T03:34:04Z BTCUSDT  CLOSE   held    55m qty 0.02319000 realised       5.2020 return    0.2868% placement line 19186
    29 line 19338  2026-09-10T21:16:04Z BTCUSDT  CLOSE   held     4m qty 0.02343000 realised      -1.3123 return   -0.0725% placement line 19330
    30 line 19355  2026-09-10T22:32:04Z BTCUSDT  CLOSE   held     8m qty 0.02347000 realised      -2.1125 return   -0.1167% placement line 19344
    31 line 19401  2026-09-14T09:22:03Z BTCUSDT  CLOSE   held     4m qty 0.02332000 realised      -0.6066 return   -0.0335% placement line 19393
    32 line 19444  2026-09-14T10:26:03Z BTCUSDT  CLOSE   held    50m qty 0.02328000 realised       3.9855 return    0.2200% placement line 19405
    33 line 19456  2026-09-14T11:48:03Z BTCUSDT  CLOSE   held     4m qty 0.02327000 realised      -0.7235 return   -0.0399% placement line 19448
    34 line 19488  2026-09-14T12:52:03Z BTCUSDT  CLOSE   held    36m qty 0.02326000 realised      -3.1966 return   -0.1765% placement line 19460
    35 line 19582  2026-09-15T19:46:03Z BTCUSDT  CLOSE   held    20m qty 0.02378000 realised      -5.2865 return   -0.2919% placement line 19564
    36 line 19603  2026-09-15T20:23:02Z BTCUSDT  CLOSE   held    19m qty 0.02379000 realised      -5.5347 return   -0.3057% placement line 19586
    37 line 19611  2026-09-15T20:59:02Z BTCUSDT  LEG/SL  held    n/a qty 0.02383000 realised     -38.9497 return   -2.1517% placement line 19607
    38 line 19661  2026-09-15T23:39:02Z BTCUSDT  LEG/SL  held    n/a qty 0.02393000 realised    -109.1912 return   -6.0340% placement line 19617
    39 line 19712  2026-09-16T01:01:04Z BTCUSDT  CLOSE   held    48m qty 0.02386000 realised       1.2419 return    0.0687% placement line 19675
    40 line 19746  2026-09-16T01:41:03Z BTCUSDT  CLOSE   held    14m qty 0.02382000 realised      -8.0652 return   -0.4461% placement line 19731
    41 line 19770  2026-09-16T02:10:03Z ETHUSDT  CLOSE   held   125m qty 0.75220000 realised      -7.8229 return   -0.4328% placement line 19665
    42 line 19813  2026-09-16T03:10:02Z BTCUSDT  CLOSE   held    51m qty 0.02385000 realised       1.1472 return    0.0635% placement line 19774
    43 line 19824  2026-09-16T03:21:02Z BTCUSDT  CLOSE   held     1m qty 0.02377000 realised       0.5900 return    0.0326% placement line 19817
    44 line 19847  2026-09-16T03:40:01Z BTCUSDT  CLOSE   held    15m qty 0.02377000 realised      -5.4773 return   -0.3031% placement line 19828
    45 line 19931  2026-09-16T18:40:02Z BTCUSDT  CLOSE   held    33m qty 0.02369000 realised     -10.6299 return   -0.5886% placement line 19900
    46 line 19968  2026-09-16T19:26:02Z BTCUSDT  CLOSE   held    17m qty 0.02377000 realised     -14.8553 return   -0.8224% placement line 19952
    47 line 20027  2026-09-16T20:43:01Z BTCUSDT  CLOSE   held    54m qty 0.02373000 realised      -1.3768 return   -0.0762% placement line 19987
    48 line 20063  2026-09-16T21:24:02Z BTCUSDT  CLOSE   held    10m qty 0.02373000 realised      -0.3987 return   -0.0221% placement line 20051
    49 line 20097  2026-09-16T22:15:02Z ETHUSDT  CLOSE   held   225m qty 0.74940000 realised      -7.3366 return   -0.4063% placement line 19919
    50 line 20173  2026-09-17T00:59:03Z BTCUSDT  CLOSE   held   104m qty 0.02381000 realised      12.0991 return    0.6700% placement line 20101
    51 line 20223  2026-09-17T02:01:02Z BTCUSDT  CLOSE   held    32m qty 0.02356000 realised      -6.6394 return   -0.3677% placement line 20197
    52 line 20305  2026-09-17T03:58:03Z BTCUSDT  CLOSE   held    74m qty 0.02362000 realised      -0.3782 return   -0.0209% placement line 20253
    53 line 20347  2026-09-17T08:49:02Z BTCUSDT  CLOSE   held    15m qty 0.02313000 realised      -0.0444 return   -0.0025% placement line 20332
    54 line 20394  2026-09-17T09:48:03Z BTCUSDT  CLOSE   held    58m qty 0.02314000 realised       2.1219 return    0.1199% placement line 20351
    55 line 20439  2026-09-17T11:36:03Z BTCUSDT  CLOSE   held    32m qty 0.02363000 realised      -2.9868 return   -0.1654% placement line 20414
    56 line 20464  2026-09-17T12:33:01Z BTCUSDT  LEG/SL  held    n/a qty 0.02360000 realised     -45.3231 return   -2.5095% placement line 20443
    57 line 20496  2026-09-17T13:05:02Z BTCUSDT  CLOSE   held    13m qty 0.02348000 realised      -0.3928 return   -0.0218% placement line 20482
    58 line 21037  2026-09-17T14:51:03Z BTCUSDT  CLOSE   held    47m qty 0.02358000 realised       1.9168 return    0.1062% placement line 20536
    59 line 21104  2026-09-17T16:26:02Z BTCUSDT  CLOSE   held    47m qty 0.02355000 realised       2.3790 return    0.1318% placement line 21070
    60 line 21160  2026-09-17T17:49:02Z BTCUSDT  CLOSE   held    46m qty 0.02349000 realised      -5.6728 return   -0.3143% placement line 21129
    61 line 21200  2026-09-17T18:42:03Z BTCUSDT  CLOSE   held    16m qty 0.02351000 realised      -4.1373 return   -0.2293% placement line 21186
    62 line 21207  2026-09-17T18:45:02Z ETHUSDT  CLOSE   held   375m qty 0.73070000 realised     -11.5670 return   -0.6404% placement line 20460
    63 line 21422  2026-09-18T09:37:04Z BTCUSDT  CLOSE   held   149m qty 0.02322000 realised       8.0994 return    0.4489% placement line 21227
    64 line 21471  2026-09-18T11:12:03Z BTCUSDT  CLOSE   held    65m qty 0.02309000 realised      -1.6315 return   -0.0903% placement line 21426
    65 line 21498  2026-09-18T13:05:03Z BTCUSDT  CLOSE   held    25m qty 0.02309000 realised      -3.0673 return   -0.1699% placement line 21477
    66 line 21673  2026-09-18T15:21:02Z BTCUSDT  LEG/TP  held    n/a qty 0.02308000 realised      63.0301 return    3.4934% placement line 21502
    67 line 21744  2026-09-18T16:55:02Z BTCUSDT  CLOSE   held    40m qty 0.02232000 realised      -0.6265 return   -0.0347% placement line 21713
    68 line 21874  2026-09-18T20:09:02Z BTCUSDT  CLOSE   held   133m qty 0.02234000 realised       3.6235 return    0.2006% placement line 21786
    69 line 21974  2026-09-18T22:38:04Z BTCUSDT  CLOSE   held   104m qty 0.02228000 realised      -0.1707 return   -0.0094% placement line 21905
    70 line 21987  2026-09-18T22:50:02Z ETHUSDT  CLOSE   held   535m qty 0.70570000 realised      42.6172 return    2.3599% placement line 21523
    71 line 21998  2026-09-18T23:22:02Z BTCUSDT  CLOSE   held     3m qty 0.02227000 realised      -0.5127 return   -0.0284% placement line 21991
    72 line 22047  2026-09-19T01:22:03Z BTCUSDT  CLOSE   held    62m qty 0.02229000 realised       2.3404 return    0.1295% placement line 22002
    73 line 22086  2026-09-19T02:50:02Z BTCUSDT  CLOSE   held    51m qty 0.02223000 realised       0.9114 return    0.0504% placement line 22051
    74 line 22157  2026-09-19T04:32:02Z BTCUSDT  CLOSE   held    20m qty 0.02225000 realised      -2.8927 return   -0.1601% placement line 22138
    75 line 22214  2026-09-19T05:48:02Z BTCUSDT  CLOSE   held    37m qty 0.02228000 realised      -1.4444 return   -0.0800% placement line 22186
    76 line 22276  2026-09-19T07:15:01Z ETHUSDT  LEG/TP  held    n/a qty 0.68870000 realised     100.8739 return    5.5825% placement line 22090
    77 line 22297  2026-09-19T07:41:03Z BTCUSDT  CLOSE   held    57m qty 0.02228000 realised      -0.4882 return   -0.0270% placement line 22254
    78 line 22362  2026-09-19T09:42:02Z BTCUSDT  CLOSE   held    93m qty 0.02228000 realised       2.1837 return    0.1207% placement line 22301
    79 line 22468  2026-09-19T16:05:03Z BTCUSDT  CLOSE   held   130m qty 0.02224000 realised       4.1364 return    0.2286% placement line 22380
    80 line 22514  2026-09-19T17:04:03Z BTCUSDT  CLOSE   held    40m qty 0.02211000 realised      -1.0122 return   -0.0559% placement line 22484
    81 line 22588  2026-09-19T18:55:03Z ETHUSDT  CLOSE   held   215m qty 0.68500000 realised      -2.6030 return   -0.1439% placement line 22437
    82 line 22599  2026-09-19T19:04:05Z BTCUSDT  CLOSE   held    24m qty 0.02219000 realised      -1.3316 return   -0.0736% placement line 22574
    83 line 22618  2026-09-19T20:29:04Z BTCUSDT  CLOSE   held    18m qty 0.02222000 realised      -2.8093 return   -0.1553% placement line 22603
    84 line 22641  2026-09-19T22:16:02Z BTCUSDT  CLOSE   held    22m qty 0.02230000 realised      -1.0392 return   -0.0575% placement line 22622
    85 line 22689  2026-09-20T01:08:02Z BTCUSDT  CLOSE   held    38m qty 0.02224000 realised      -1.3560 return   -0.0750% placement line 22661
    86 line 22709  2026-09-20T02:27:02Z BTCUSDT  CLOSE   held    14m qty 0.02229000 realised      -3.1652 return   -0.1750% placement line 22695
    87 line 22721  2026-09-20T03:43:02Z BTCUSDT  CLOSE   held     4m qty 0.02251000 realised      -0.7660 return   -0.0424% placement line 22713
    88 line 22747  2026-09-20T04:25:02Z BTCUSDT  CLOSE   held    28m qty 0.02247000 realised      -1.4055 return   -0.0777% placement line 22725
    89 line 22757  2026-09-20T04:46:02Z BTCUSDT  CLOSE   held     2m qty 0.02249000 realised      -0.1961 return   -0.0108% placement line 22751
    90 line 22794  2026-09-20T05:52:02Z BTCUSDT  CLOSE   held    46m qty 0.02247000 realised       0.6017 return    0.0333% placement line 22761
    91 line 22808  2026-09-20T06:36:02Z BTCUSDT  CLOSE   held     8m qty 0.02247000 realised      -1.4399 return   -0.0796% placement line 22798
    92 line 22832  2026-09-20T07:51:02Z BTCUSDT  CLOSE   held    21m qty 0.02249000 realised      -1.4299 return   -0.0791% placement line 22812
    93 line 22863  2026-09-20T08:39:02Z BTCUSDT  CLOSE   held    35m qty 0.02249000 realised      -1.7095 return   -0.0945% placement line 22836
    94 line 22909  2026-09-20T10:11:03Z BTCUSDT  CLOSE   held    48m qty 0.02250000 realised      -0.0898 return   -0.0050% placement line 22867
    95 line 22951  2026-09-20T11:15:02Z ETHUSDT  CLOSE   held   110m qty 0.70090000 realised      -6.0558 return   -0.3348% placement line 22872
    96 line 22998  2026-09-20T12:23:03Z BTCUSDT  CLOSE   held    60m qty 0.02250000 realised       1.4317 return    0.0792% placement line 22955
    97 line 23035  2026-09-20T13:38:03Z BTCUSDT  CLOSE   held    37m qty 0.02246000 realised      -1.1852 return   -0.0655% placement line 23007
    98 line 23075  2026-09-20T14:27:03Z BTCUSDT  CLOSE   held    29m qty 0.02245000 realised      -0.1100 return   -0.0061% placement line 23052
    99 line 23122  2026-09-20T15:30:01Z BTCUSDT  LEG/SL  held    n/a qty 0.02243000 realised     -80.3912 return   -4.4459% placement line 23092
   100 line 23200  2026-09-20T17:17:02Z BTCUSDT  CLOSE   held    87m qty 0.02234000 realised       8.0268 return    0.4441% placement line 23140
   101 line 23238  2026-09-20T18:02:02Z BTCUSDT  CLOSE   held    17m qty 0.02221000 realised      -5.2351 return   -0.2897% placement line 23221
   102 line 23283  2026-09-20T18:54:02Z BTCUSDT  CLOSE   held    21m qty 0.02224000 realised      -4.0564 return   -0.2245% placement line 23262
   103 line 23340  2026-09-20T20:13:02Z BTCUSDT  CLOSE   held    38m qty 0.02224000 realised      -2.3650 return   -0.1309% placement line 23313
   104 line 23349  2026-09-20T20:20:02Z ETHUSDT  CLOSE   held   440m qty 0.70100000 realised      36.1015 return    1.9960% placement line 23002
   105 line 23393  2026-09-20T21:35:02Z ETHUSDT  CLOSE   held    55m qty 0.68590000 realised      -6.5641 return   -0.3631% placement line 23353
   106 line 23470  2026-09-20T23:18:03Z BTCUSDT  CLOSE   held    92m qty 0.02235000 realised       7.2380 return    0.4004% placement line 23397
   107 line 23540  2026-09-21T00:59:02Z BTCUSDT  CLOSE   held    97m qty 0.02225000 realised       8.2621 return    0.4570% placement line 23477
   108 line 23572  2026-09-21T01:35:02Z BTCUSDT  CLOSE   held    17m qty 0.02212000 realised      -8.8982 return   -0.4921% placement line 23556
   109 line 23624  2026-09-21T02:48:02Z BTCUSDT  CLOSE   held    27m qty 0.02219000 realised      -4.9708 return   -0.2749% placement line 23603
   110 line 23639  2026-09-21T03:05:01Z ETHUSDT  CLOSE   held   255m qty 0.68480000 realised      19.8318 return    1.0972% placement line 23443
   111 line 23683  2026-09-21T04:04:01Z BTCUSDT  CLOSE   held    54m qty 0.02223000 realised       1.2378 return    0.0685% placement line 23643
   112 line 23709  2026-09-21T05:15:02Z BTCUSDT  CLOSE   held    28m qty 0.02220000 realised      -2.0730 return   -0.1147% placement line 23687
   113 line 23745  2026-09-21T06:06:02Z BTCUSDT  CLOSE   held    37m qty 0.02215000 realised       0.7690 return    0.0425% placement line 23713
   114 line 23783  2026-09-21T06:49:03Z BTCUSDT  CLOSE   held    30m qty 0.02210000 realised      -1.5141 return   -0.0838% placement line 23758
   115 line 23817  2026-09-21T07:35:01Z ETHUSDT  CLOSE   held   110m qty 0.67740000 realised     -13.1890 return   -0.7295% placement line 23727
   116 line 23888  2026-09-21T09:40:01Z BTCUSDT  LEG/TP  held    n/a qty 0.02212000 realised      75.1640 return    4.1585% placement line 23821
   117 line 24035  2026-09-21T13:20:01Z BTCUSDT  CLOSE   held   131m qty 0.02140000 realised      13.6078 return    0.7521% placement line 23950
   118 line 24132  2026-09-21T15:34:02Z BTCUSDT  CLOSE   held   102m qty 0.02111000 realised       3.6628 return    0.2024% placement line 24060
   119 line 24163  2026-09-21T16:08:02Z BTCUSDT  CLOSE   held    10m qty 0.02106000 realised      -4.2162 return   -0.2330% placement line 24151
   120 line 24222  2026-09-21T17:28:03Z BTCUSDT  CLOSE   held    39m qty 0.02105000 realised      -1.7655 return   -0.0976% placement line 24192
   121 line 24275  2026-09-21T18:40:02Z ETHUSDT  CLOSE   held   595m qty 0.66950000 realised      33.4616 return    1.8506% placement line 23852
   122 line 24282  2026-09-21T18:43:02Z BTCUSDT  CLOSE   held    31m qty 0.02104000 realised      -0.7015 return   -0.0388% placement line 24253
   123 line 24370  2026-09-21T20:57:02Z BTCUSDT  CLOSE   held   119m qty 0.02103000 realised      19.8721 return    1.0982% placement line 24286
   124 line 24416  2026-09-21T22:01:02Z BTCUSDT  CLOSE   held    17m qty 0.02085000 realised      -4.4475 return   -0.2457% placement line 24401
   125 line 24487  2026-09-21T23:38:03Z BTCUSDT  CLOSE   held    27m qty 0.02090000 realised      -3.6241 return   -0.2002% placement line 24463
   126 line 24505  2026-09-22T00:00:01Z ETHUSDT  CLOSE   held   275m qty 0.65480000 realised       7.8576 return    0.4341% placement line 24307
   127 line 24522  2026-09-22T00:13:02Z BTCUSDT  CLOSE   held    12m qty 0.02091000 realised      -3.1158 return   -0.1721% placement line 24509
   128 line 24557  2026-09-22T03:08:02Z BTCUSDT  CLOSE   held    37m qty 0.02112000 realised      -2.4022 return   -0.1327% placement line 24530
   129 line 24587  2026-09-22T04:31:01Z BTCUSDT  CLOSE   held    32m qty 0.02114000 realised      -1.7390 return   -0.0961% placement line 24561
   130 line 24763  2026-09-22T19:38:01Z BTCUSDT  CLOSE   held    41m qty 0.02092000 realised      -4.4970 return   -0.2485% placement line 24733
   131 line 24822  2026-09-22T21:00:03Z BTCUSDT  CLOSE   held    28m qty 0.02099000 realised       0.3959 return    0.0219% placement line 24799
   132 line 24835  2026-09-22T21:15:03Z ETHUSDT  CLOSE   held   200m qty 0.65730000 realised      -3.8189 return   -0.2110% placement line 24607
   133 line 24847  2026-09-22T21:57:02Z BTCUSDT  CLOSE   held     6m qty 0.02097000 realised      -0.5607 return   -0.0310% placement line 24839
   134 line 24857  2026-09-22T22:03:03Z BTCUSDT  CLOSE   held     1m qty 0.02098000 realised      -2.2470 return   -0.1242% placement line 24851
   135 line 24883  2026-09-22T23:05:02Z BTCUSDT  CLOSE   held    28m qty 0.02099000 realised      -0.4880 return   -0.0270% placement line 24861
   136 line 24913  2026-09-22T23:37:03Z BTCUSDT  CLOSE   held    28m qty 0.02094000 realised      -5.1894 return   -0.2867% placement line 24887
   137 line 24973  2026-09-23T01:02:03Z BTCUSDT  CLOSE   held    51m qty 0.02098000 realised       5.0350 return    0.2783% placement line 24938
   138 line 25008  2026-09-23T01:40:03Z BTCUSDT  CLOSE   held    36m qty 0.02089000 realised      -4.1648 return   -0.2302% placement line 24978
   139 line 25061  2026-09-23T02:50:03Z ETHUSDT  CLOSE   held   205m qty 0.65540000 realised      -1.2715 return   -0.0703% placement line 24901
   140 line 25071  2026-09-23T02:59:03Z BTCUSDT  CLOSE   held    40m qty 0.02093000 realised       1.4521 return    0.0803% placement line 25037
   141 line 25110  2026-09-23T04:06:03Z BTCUSDT  CLOSE   held    43m qty 0.02088000 realised      -0.5095 return   -0.0282% placement line 25075
   142 line 25155  2026-09-23T05:07:02Z BTCUSDT  CLOSE   held    49m qty 0.02085000 realised       1.7908 return    0.0989% placement line 25121
   143 line 25202  2026-09-23T06:20:02Z ETHUSDT  CLOSE   held   165m qty 0.65410000 realised      -4.9908 return   -0.2758% placement line 25087
   144 line 25238  2026-09-23T09:40:03Z BTCUSDT  CLOSE   held    13m qty 0.02105000 realised      -3.4215 return   -0.1891% placement line 25224
   145 line 25254  2026-09-23T10:24:04Z BTCUSDT  CLOSE   held    10m qty 0.02108000 realised      -3.1569 return   -0.1745% placement line 25242
   146 line 25283  2026-09-23T11:17:02Z BTCUSDT  CLOSE   held    30m qty 0.02107000 realised      -3.1660 return   -0.1749% placement line 25258
   147 line 25303  2026-09-23T12:17:03Z BTCUSDT  CLOSE   held    17m qty 0.02113000 realised      -3.6758 return   -0.2031% placement line 25287
   148 line 25321  2026-09-23T12:58:04Z BTCUSDT  CLOSE   held    11m qty 0.02116000 realised      -1.7231 return   -0.0952% placement line 25307
   149 line 25355  2026-09-23T14:12:02Z BTCUSDT  CLOSE   held    42m qty 0.02115000 realised     -12.7936 return   -0.7071% placement line 25325
   150 line 25391  2026-09-23T15:38:02Z BTCUSDT  CLOSE   held    41m qty 0.02143000 realised      -1.9278 return   -0.1066% placement line 25359
   151 line 25473  2026-09-23T20:11:02Z BTCUSDT  CLOSE   held    77m qty 0.02145000 realised       0.4575 return    0.0253% placement line 25413
   152 line 25514  2026-09-23T20:59:03Z BTCUSDT  CLOSE   held     9m qty 0.02146000 realised      -1.8374 return   -0.1016% placement line 25502
   153 line 25587  2026-09-23T22:37:03Z BTCUSDT  CLOSE   held    75m qty 0.02144000 realised       1.6734 return    0.0925% placement line 25534
   154 line 25623  2026-09-23T23:20:03Z BTCUSDT  CLOSE   held    24m qty 0.02139000 realised      -2.6487 return   -0.1464% placement line 25602
   155 line 25721  2026-09-24T01:40:04Z ETHUSDT  CLOSE   held   395m qty 0.67860000 realised      12.5812 return    0.6954% placement line 25425
   156 line 25727  2026-09-24T01:42:03Z BTCUSDT  CLOSE   held     4m qty 0.02145000 realised      -2.8127 return   -0.1554% placement line 25714
   157 line 25771  2026-09-24T03:22:02Z BTCUSDT  CLOSE   held    51m qty 0.02149000 realised       0.2529 return    0.0140% placement line 25731
   158 line 25815  2026-09-24T10:38:02Z BTCUSDT  CLOSE   held    28m qty 0.02172000 realised      -0.9668 return   -0.0534% placement line 25791
   159 line 25857  2026-09-24T11:38:03Z BTCUSDT  CLOSE   held    55m qty 0.02169000 realised       1.3866 return    0.0766% placement line 25819
   160 line 25885  2026-09-24T12:43:03Z BTCUSDT  CLOSE   held    26m qty 0.02165000 realised      -0.7365 return   -0.0407% placement line 25861
   161 line 25957  2026-09-24T18:30:04Z ETHUSDT  CLOSE   held   315m qty 0.68110000 realised      18.6758 return    1.0321% placement line 25905
   162 line 26036  2026-09-25T02:50:03Z ETHUSDT  CLOSE   held   160m qty 0.67090000 realised     -11.5663 return   -0.6392% placement line 26009
   163 line 26065  2026-09-25T05:45:02Z BTCUSDT  CLOSE   held   825m qty 0.02144000 realised      -3.4688 return   -0.1917% placement line 25931
   164 line 26076  2026-09-25T06:45:03Z ETHUSDT  CLOSE   held    15m qty 0.67590000 realised      -2.3994 return   -0.1326% placement line 26069
   165 line 26122  2026-09-25T14:05:02Z BTCUSDT  LEG/SL  held   168m qty 0.02124000 realised     -35.2299 return   -1.9476% placement line 26096

==========================================================================
TOTALS  [sha256 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528]
==========================================================================
  closes by CLOSE: 154   by a protective leg: 11 (SL 8, TP 3, unclassified 0)
  ALL BOOKINGS
    bookings            : 165
    realised gross      : -192.0271 USDT
    win rate            : 34.5% (57 of 165)
    profit factor       : 0.75
    per-trade return n  : 165
    mean                : -0.0641%
    std dev (n - 1)     : 1.0368%
    95% interval        : [-0.2223%, 0.0941%]
    net mean at 0.1% a side : -0.2641%
    t of the net mean   : -3.27
  STRATEGY CLOSES ONLY
    bookings            : 154
    realised gross      : 13.8306 USDT
    win rate            : 35.1% (54 of 154)
    profit factor       : 1.04
    per-trade return n  : 154
    mean                : 0.0050%
    std dev (n - 1)     : 0.4129%
    95% interval        : [-0.0602%, 0.0702%]
    net mean at 0.1% a side : -0.1950%
    t of the net mean   : -5.86
  PROTECTIVE LEGS ONLY
    bookings            : 11
    realised gross      : -205.8577 USDT
    win rate            : 27.3% (3 of 11)
    profit factor       : 0.54
    per-trade return n  : 11
    mean                : -1.0320%
    std dev (n - 1)     : 3.7306%
    95% interval        : [-3.2366%, 1.1726%]
    net mean at 0.1% a side : -1.2320%
    t of the net mean   : -1.10

==========================================================================
STOP-LOSS SLIPPAGE  [sha256 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528]
==========================================================================
  stop-loss legs      : 8 (8 with a matched placement)
  filled beyond trigger: 8
  beyond-trigger slippage: min 0.0291%, median 0.6419%, max 4.2121%
  worst stop-loss exit: line 19661, exit -6.1279% from the placement's entry limit against a stop 2.0000% below it; realised return -6.0340% of the booked entry total
  per leg (slippage is beyond the trigger, positive = worse than the stop):
    line 16963  ETHUSDT  stop 2463.01000000 exit 2446.64156094 slippage 0.6646% stop distance 1.9998% exit move -2.6511%
    line 17109  BTCUSDT  stop 79363.71000000 exit 79340.64000000 slippage 0.0291% stop distance 2.0000% exit move -2.0285%
    line 17215  BTCUSDT  stop 78329.27000000 exit 77428.20826720 slippage 1.1504% stop distance 2.0000% exit move -3.1273%
    line 19611  BTCUSDT  stop 74516.09000000 exit 74326.37819136 slippage 0.2546% stop distance 2.0000% exit move -2.2495%
    line 19661  BTCUSDT  stop 74182.22000000 exit 71057.58000000 slippage 4.2121% stop distance 2.0000% exit move -6.1279%
    line 20464  BTCUSDT  stop 75071.23000000 exit 74606.30035593 slippage 0.6193% stop distance 2.0000% exit move -2.6069%
    line 23122  BTCUSDT  stop 79098.39000000 exit 77031.90876505 slippage 2.6125% stop distance 2.0000% exit move -4.5603%
    line 26122  BTCUSDT  stop 83545.95000000 exit 83507.14000000 slippage 0.0465% stop distance 2.0000% exit move -2.0455%

==========================================================================
PER BOOKING DAY (UTC, by booking time)  [sha256 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528]
==========================================================================
  2026-09-04   bookings   3  realised    -135.8407
  2026-09-06   bookings   7  realised      -0.1589
  2026-09-07   bookings   8  realised      11.3427
  2026-09-08   bookings   4  realised      -2.8078
  2026-09-09   bookings   2  realised       4.0960
  2026-09-10   bookings   6  realised       2.8851
  2026-09-14   bookings   4  realised      -0.5411
  2026-09-15   bookings   4  realised    -158.9621
  2026-09-16   bookings  11  realised     -52.9837
  2026-09-17   bookings  13  realised     -58.6250
  2026-09-18   bookings   9  realised     111.3616
  2026-09-19   bookings  13  realised      96.8253
  2026-09-20   bookings  22  realised     -64.1208
  2026-09-21   bookings  19  realised     130.4692
  2026-09-22   bookings  11  realised     -15.8044
  2026-09-23   bookings  18  realised     -34.8785
  2026-09-24   bookings   7  realised      28.3806
  2026-09-25   bookings   4  realised     -52.6645
```

### The same tool over the untracked census's window

`--until 2026-09-24T03:58:40Z` is the untracked census's last record. Exit status 0.
The header, the totals and the stop-loss section, verbatim; the per-booking and per-day
sections are omitted here and are the first 157 rows of the table above:

```
==========================================================================
CAPTURE
==========================================================================
  path   : F:\trading bot\files\binance-trading-bot\m5j-evidence\trading_bot.m5k-close-20260925T182818Z.log
  bytes  : 5074996
  lines  : 26126
  sha256 : 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528
  naive-stamp offset : 6:00:00 from 20 naive lines, 20 agreeing
  placements : 185
  bookings   : 165
  anomalies  : 0
  restricted to bookings at or before 2026-09-24T03:58:40Z : kept 157, excluded 8
  bookings matched to a placement : 157 of 157
  placements never booked          : 20
  quantity differs from its placement : 0

==========================================================================
TOTALS  [sha256 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528]
==========================================================================
  closes by CLOSE: 147   by a protective leg: 10 (SL 7, TP 3, unclassified 0)
  ALL BOOKINGS
    bookings            : 157
    realised gross      : -157.7217 USDT
    win rate            : 35.0% (55 of 157)
    profit factor       : 0.78
    per-trade return n  : 157
    mean                : -0.0553%
    std dev (n - 1)     : 1.0475%
    95% interval        : [-0.2192%, 0.1085%]
    net mean at 0.1% a side : -0.2553%
    t of the net mean   : -3.05
  STRATEGY CLOSES ONLY
    bookings            : 147
    realised gross      : 12.9060 USDT
    win rate            : 35.4% (52 of 147)
    profit factor       : 1.04
    per-trade return n  : 147
    mean                : 0.0049%
    std dev (n - 1)     : 0.4100%
    95% interval        : [-0.0614%, 0.0712%]
    net mean at 0.1% a side : -0.1951%
    t of the net mean   : -5.77
  PROTECTIVE LEGS ONLY
    bookings            : 10
    realised gross      : -170.6278 USDT
    win rate            : 30.0% (3 of 10)
    profit factor       : 0.58
    per-trade return n  : 10
    mean                : -0.9404%
    std dev (n - 1)     : 3.9193%
    95% interval        : [-3.3697%, 1.4888%]
    net mean at 0.1% a side : -1.1404%
    t of the net mean   : -0.92

==========================================================================
STOP-LOSS SLIPPAGE  [sha256 3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528]
==========================================================================
  stop-loss legs      : 7 (7 with a matched placement)
  filled beyond trigger: 7
  beyond-trigger slippage: min 0.0291%, median 0.6646%, max 4.2121%
  worst stop-loss exit: line 19661, exit -6.1279% from the placement's entry limit against a stop 2.0000% below it; realised return -6.0340% of the booked entry total
  per leg (slippage is beyond the trigger, positive = worse than the stop):
    line 16963  ETHUSDT  stop 2463.01000000 exit 2446.64156094 slippage 0.6646% stop distance 1.9998% exit move -2.6511%
    line 17109  BTCUSDT  stop 79363.71000000 exit 79340.64000000 slippage 0.0291% stop distance 2.0000% exit move -2.0285%
    line 17215  BTCUSDT  stop 78329.27000000 exit 77428.20826720 slippage 1.1504% stop distance 2.0000% exit move -3.1273%
    line 19611  BTCUSDT  stop 74516.09000000 exit 74326.37819136 slippage 0.2546% stop distance 2.0000% exit move -2.2495%
    line 19661  BTCUSDT  stop 74182.22000000 exit 71057.58000000 slippage 4.2121% stop distance 2.0000% exit move -6.1279%
    line 20464  BTCUSDT  stop 75071.23000000 exit 74606.30035593 slippage 0.6193% stop distance 2.0000% exit move -2.6069%
    line 23122  BTCUSDT  stop 79098.39000000 exit 77031.90876505 slippage 2.6125% stop distance 2.0000% exit move -4.5603%
```

### What this section decides

**Nothing.** It records one tool's output on one capture and the comparison with a census
whose capture cannot be read. The differences are tabulated and diagnosed in
`docs/NEXT_MILESTONE.md` beside S0, where the untracked figures are annotated; the stop
slippage median that S2's default rests on is flagged for the owner there and is not
adopted.

## 28. M5m S1: the monthly archive download (C4), 980 of 1,100 months stored, 120 refused

Recorded at M5m P101 (C4). An observation log, so this section only adds. **The download
that R-H authorised once was made, and it did not finish the job it was authorised to do:
the importer refused 120 of the 1,100 months on its close-time rule.** Nothing was
fetched twice and nothing was altered after the run. The ruling that is needed is stated at
the end, and this section does not make it.

### What was run

- **Code:** `scripts/download_data.py` and `trading_bot.data.historical` at `8aa1514`
  (`HEAD` when the run started), launched from the development tree: this run fetches
  public archive files and touches no venue account, store or lock, so the deployment-clone
  doctrine, which governs `run`, is not engaged.
- **Command, from the repository root:** `python scripts/download_data.py --through 2026-09`
  with the defaults, `--symbols BTCUSDT ETHUSDT`, `--intervals 1m 5m 1h 4h 1d` and
  `--data-dir data/historical`. Its stdout went to a scratchpad file, not under `logs/`.
- **Window (UTC):** started `2026-10-07T19:20:24Z`, exit recorded at `2026-10-07T19:45:05Z`,
  24 min 41 s. Exit status **1**.
- **Dry-run before it (`2026-10-07T19:17:27Z`, exit 0, nothing written):** the archive
  listed **110 months for each of the ten series, 1,100 zips**, as predicted. It was also
  what exposed the host-check defect fixed at `8aa1514` (`M5m-060`).
- **Hosts:** `s3-ap-northeast-1.amazonaws.com/data.binance.vision` for the listing and
  `data.binance.vision` for each `.CHECKSUM` and zip. No other host was asked.

### Result, by instrument

Counts of the run's own output lines (`stored ...` and `FAILED ...`): **980 stored, 120
failed**. Every one of the 120 is an `ArchiveFormatError`; the count of
`ChecksumMismatchError`, `DownloadError` and `OSError` lines is **0**. So every one of
the 980 stored months was verified against its venue `.CHECKSUM` before a byte was
parsed (that is `ingest_zip`'s first act), and no download failed in transport.

| series | listed | stored | refused | rows stored | gaps | missing | grid | rows + missing |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1m | 110 | 96 | 14 | 4,185,052 | 26 | 612,788 | 4,797,840 | 4,797,840 |
| BTCUSDT 5m | 110 | 96 | 14 | 837,011 | 25 | 122,557 | 959,568 | 959,568 |
| BTCUSDT 1h | 110 | 96 | 14 | 69,754 | 25 | 10,210 | 79,964 | 79,964 |
| BTCUSDT 4h | 110 | 92 | 18 | 16,714 | 16 | 3,277 | 19,991 | 19,991 |
| BTCUSDT 1d | 110 | 110 | 0 | 3,332 | 0 | 0 | 3,332 | 3,332 |
| ETHUSDT 1m | 110 | 96 | 14 | 4,185,052 | 26 | 612,788 | 4,797,840 | 4,797,840 |
| ETHUSDT 5m | 110 | 96 | 14 | 837,011 | 25 | 122,557 | 959,568 | 959,568 |
| ETHUSDT 1h | 110 | 96 | 14 | 69,754 | 25 | 10,210 | 79,964 | 79,964 |
| ETHUSDT 4h | 110 | 92 | 18 | 16,714 | 16 | 3,277 | 19,991 | 19,991 |
| ETHUSDT 1d | 110 | 110 | 0 | 3,332 | 0 | 0 | 3,332 | 3,332 |

Instrument for rows, gaps, missing and grid: `HistoricalStore.coverage(..., until=
2026-10-01T00:00Z)` run by a scratchpad script over the stored directory, **and the grid recomputed independently** as whole bars from the first stored open time to
`2026-10-01T00:00Z` by `datetime` arithmetic, not by `grid_size`. The two agree on all ten
series, and **`rows + missing == grid` holds exactly on all ten**; `BTCUSDT 1m`'s grid is
4,797,840, as predicted before the run. `check_stored` reports **0 problems** on every
series. Totals: **980 files, 995,246,501 CSV bytes, 10,223,726 rows, 184 gaps, 1,497,664
missing bars.** The two daily series are complete from their first bar
(`2017-08-17T00:00Z`) to `2026-09-30T00:00Z` with no gap. The first bar of every other
series is `2017-08-17T04:00Z`, the last `2026-09-30T23:59Z` (1m), `23:55Z` (5m),
`23:00Z` (1h) and `20:00Z` (4h).

Manifest SHA-256, per series (`MANIFEST.jsonl`, the instrument being `hashlib.sha256` of
its bytes): BTCUSDT 1m `8ec0675429d54b2b2dcf2ae132e636f7db52f0681e39a9d4afe281df52e57944`,
5m `1b915796e89768b46592d56f7ad4d3a52abcd4ed59197649c28389d9a07c968c`, 1h
`489f19ff3925aab3b32bb7d9c692f6ffdb6f3fa65682ed6986cc9e80c2653760`, 4h
`0250de6ffed7e1ef9c19011b87964949aade645cf51d5432f5c48d80fb0d6281`, 1d
`39247bf6d4a3281a1de88f367f316bdf6fd94de276a9f8ba03ca830930a1ce04`; ETHUSDT 1m
`07c3f5725ae7ed394053d7cd88157922bf007a8f2a2e98b91481bdc818f5b835`, 5m
`2615cc985e37095a6db3b11103606c8dd7ceeb9c0a76f8315ed6fc308fa0327f`, 1h
`dcb442d7d1b4c6daa3b7515bdab232eccf6fd36c802c92c0b45bcdb22165f24c`, 4h
`7c003d460e8b2c917d53cdfe4d9d8b02a64b93c90acf2005ec500beedbebbdbb`, 1d
`e456846220ef3ffb47107769a391082ab4404d7fc884f657a00f367616d54645`.

### The 120 refusals

**Refused months, by series.** 1m, 5m and 1h, for BTCUSDT and ETHUSDT alike (the lists are
identical): `2017-09 2017-12 2018-01 2018-02 2018-07 2019-06 2020-02 2020-03 2020-12 2021-02
2021-04 2021-08 2021-12 2023-03`. 4h, for both: `2017-09 2018-01 2018-06 2018-07 2018-10
2018-11 2019-03 2019-05 2019-08 2019-11 2020-02 2020-04 2020-06 2020-12 2021-02 2021-04
2021-08 2021-09`. 1d: none.

**What the rule refused.** `normalise_archive` requires every row's close time to equal
its open time plus the interval less one millisecond. Each refusal names the first row
that broke it, and the 120 first-breaking rows fall in four shapes (instrument: the
difference `close - (open + interval - 1)` of each refusal message):

| shape | refusals | months | difference |
|---|---|---|---|
| close inside the bar: a short bar | 100 | 23 months from 2017-12 to 2023-03 | -13,054,448 ms to a few ms short |
| close one millisecond late, equal to the next open | 8 | 2017-09 | +1 ms |
| close before the bar's own open | 6 | 2020-12 | -4,359,478 ms to -1,299,471 ms |
| close at whole-second precision, ms part `000` | 6 | 2021-08 | -999 ms |

**REASONED, not measured: the short bars belong to the venue's maintenance windows.** The
stored series also hold intra-month gaps of hours (for example `2018-06-26T02:00Z` to
`12:00Z`, 600 missing 1-minute bars, in a month that was stored), so the archive does omit
bars around such events, and a bar that was open when one began could plausibly have been
closed early. Nothing here checked a venue notice, and the 4h series refuses
`2018-06`, `2018-10` and `2018-11`, months the 1m series stored. The counts above are the
classification of all 120 refusal lines by a scratchpad script, with 0 unparsed; no row
of the archive is reproduced here.

**What is NOT known (`M5m-066`).** A refusal reports the first bad row only, so how many
rows of each refused file break the rule, and whether any of them also break the open-time
grid, is **unmeasured**. The zips were not kept after parsing, so answering it needs the
files again.

### The stored series are not complete, and the gap list does not say why

`HistoricalStore.coverage` reports a refused month as a gap, because its bars are absent.
So the 184 gaps mix two different facts: **months the archive holds and the importer
refused** (the whole-month and multi-month runs), and **bars the archive itself omits
inside a stored month** (the short runs of hours). The report cannot tell them apart and
was not built to (`M5m-067`). Nothing was filled.

### What this section decides

**Nothing.** The rule that refused these months is the importer's own design, which the
owner approved in P100 and which R-F surveyed (mutations U5 to U7); it did its job, which
is to refuse what it cannot vouch for and say so. Whether to **relax it** (accept a close
time that falls inside the bar), **normalise** (derive `open + interval - 1` and record
that the archive said otherwise), **quarantine** the irregular rows as gaps, or **keep
refusing** and treat those months as missing is the owner's. Any of the first three
changes surveyed code and needs the zips again, which is a second download that R-H, in
its word *"once"*, does not cover. See `docs/NEXT_MILESTONE.md` under S1.

## 29. M5m S1: the 120 refused months ingested from disk under the row-classification rule (P103 C4)

Recorded at M5m P103 (C4). An observation log, so this section only adds; section 28 still
describes what the run of `2026-10-07` found, and nothing in it is altered. **The store is
now complete under the owner's rulings R-L to R-O: all 110 months of every one of the ten
series are present.** No request was made to any host: the 120 zips were the ones P102
fetched into scratch (R-J) and C4 copied (R-O), and the ingest ran with `--offline`.

### What was run

- **Code:** `scripts/download_data.py` and `trading_bot.data.historical` at `e236162`
  (`HEAD` when the run started, C1 to C3 of P103 committed, the tree clean), launched from
  the development tree for the reason section 28 gives: public archive files only, no venue
  account, store or lock.
- **Zips:** the 120 zips and 120 `.CHECKSUM` files of `F:\trading bot\scratch\p102\zips` were
  copied, refusing to overwrite, into `data/historical/_zips/<SYMBOL>/<interval>/`, and each
  zip was verified against its CHECKSUM at the destination by a separate script: **120 zips,
  71,708,741 bytes, 120 verified**. The directory holds 71,719,301 bytes with the checksum
  files. `data/*` is ignored by git (`.gitignore:37`), which covers `_zips`.
- **Command, from the repository root:** `python scripts/download_data.py --through 2026-09
  --offline --intervals 1m 5m 1h 4h` (the daily series had no refused month, so it is not
  named; offline mode reports a note and exits 1 for a series with nothing on disk to plan
  from). Stdout went to a scratchpad file.
- **Window (UTC):** `2026-10-08T03:11:41Z` to `03:12:29Z`, **48 s**, exit status **0**.
- **Result, per symbol and interval:** listed, stored, skipped 0, failed **0**, fetched **0**,
  reused all. BTCUSDT and ETHUSDT alike: 1m 14 stored, 5m 14, 1h 14, 4h 18; **120 months
  stored, none failed.**
- **The 980 stored months were not downloaded again.** Before the ingest they were
  re-verified under the new rule from their stored CSVs and manifest rows
  (`HistoricalStore.verify`, every row re-checked): **0 problems on all 980, 76.4 s.** After
  the ingest the same call over the whole store (`2026-10-08T03:12:41Z` to `03:14:03Z`, 81.1 s
  in the script's own clock) reports **0 problems on all 1,100 months**, and
  `check_stored` without the row re-check reports 0 as well. **The 980 old manifest lines are
  byte-identical** before and after, in the same order, on every series (96, 96, 96, 92 and
  110 lines per symbol; the new lines were appended). Instrument: `state_before.json` and
  `state_after.json` written by a scratchpad script, compared line by line.

### Result, by series

Instrument: `HistoricalStore.coverage(..., until=2026-10-01T00:00Z)`, as in section 28.
`rows + missing == grid` holds exactly on all ten series.

| series | months | rows stored | missing bars | of which omitted | of which quarantined | grid | registered rows | quarantined rows |
|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1m | 110 | 4,767,676 | 30,164 | 8,562 | 21,602 | 4,797,840 | 15 | 21,603 |
| BTCUSDT 5m | 110 | 957,623 | 1,945 | 1,703 | 242 | 959,568 | 15 | 242 |
| BTCUSDT 1h | 110 | 79,793 | 171 | 127 | 44 | 79,964 | 13 | 44 |
| BTCUSDT 4h | 110 | 19,974 | 17 | 17 | 0 | 19,991 | 19 | 0 |
| BTCUSDT 1d | 110 | 3,332 | 0 | 0 | 0 | 3,332 | 0 | 0 |
| ETHUSDT 1m | 110 | 4,767,675 | 30,165 | 8,563 | 21,602 | 4,797,840 | 15 | 21,603 |
| ETHUSDT 5m | 110 | 957,623 | 1,945 | 1,703 | 242 | 959,568 | 15 | 242 |
| ETHUSDT 1h | 110 | 79,793 | 171 | 127 | 44 | 79,964 | 13 | 44 |
| ETHUSDT 4h | 110 | 19,974 | 17 | 17 | 0 | 19,991 | 19 | 0 |
| ETHUSDT 1d | 110 | 3,332 | 0 | 0 | 0 | 3,332 | 0 | 0 |

**Every figure above was predicted before the run and matched**, including the one-row
difference between the two symbols' 1m series (4,767,676 and 4,767,675), which is the
omitted bar at one minute of `2020-12-21`: BTCUSDT's missing bar is `14:09Z` and ETHUSDT's
is `14:08Z`, each beside a quarantined row (below). `omitted + quarantined == missing` on
every series. The gap count of `find_gaps` was **184** at section 28 and is **204** now
(33, 32, 28, 9 and 0 per symbol for 1m, 5m, 1h, 4h and 1d): the 4h series fell from 16
gaps to 9 as its 18 absent months arrived, and the minute-scale series gained the
irregularities inside the months that arrived. With the kinds split, `kinded_gaps` is
37, 35, 30, 9 and 0 per symbol.

### The registry: rows stored with their close irregularity registered

**124 registered rows in all, 62 per symbol:** 110 short bars, 8 one-millisecond-late rows
and 6 whole-second rows. Per symbol and interval (short / one ms late / whole second): 1m
13 / 1 / 1, 5m 13 / 1 / 1, 1h 11 / 1 / 1, 4h 18 / 1 / 0. **Nothing was altered:** every
registered row is stored verbatim, the zero-trade short bars included, and the 8
one-millisecond-late rows (4 per symbol, the month `2017-09`) are not repaired (R-L). Each
registry line carries the month, the line number in the archive file, the shape, the open
time, the raw line and the source URL. Instrument: the registry sidecars read by a
scratchpad script.

### The quarantine: rows not stored

**Quarantined per symbol:** 1m 21,603 rows (21,602 off the interval grid, 1 whose close is
not after its open), 5m 242 (241 and 1), 1h 44 (43 and 1), 4h 0, 1d 0. The single
close-not-after-open row of each series is the flat bar of `2020-12-21` in the month
`2020-12` (BTCUSDT 1m at `1608559740000`, line 29650; ETHUSDT 1m at `1608559680000`, line
29649; the 5m and 1h rows at `14:05Z` and `14:00Z` for both). Each quarantined row's raw
line, shape and source is in the registry, and none is stored.

**Every quarantined span, as a run of missing bars of kind `quarantined` (R-N: not backfilled
from REST). A span is `[start, end)`, `end` being the open of the next bar present.**

| series | start (UTC) | end (UTC) | bars |
|---|---|---|---|
| BTCUSDT and ETHUSDT 1m | 2017-12-04T06:01:00Z | 2017-12-18T10:01:00Z | 20,400 |
| BTCUSDT and ETHUSDT 1m | 2018-02-09T09:59:00Z | 2018-02-10T06:00:00Z | 1,201 |
| BTCUSDT 1m | 2020-12-21T14:09:00Z | 2020-12-21T14:10:00Z | 1 |
| ETHUSDT 1m | 2020-12-21T14:08:00Z | 2020-12-21T14:09:00Z | 1 |
| BTCUSDT and ETHUSDT 5m | 2018-02-09T09:55:00Z | 2018-02-10T06:00:00Z | 241 |
| BTCUSDT and ETHUSDT 5m | 2020-12-21T14:05:00Z | 2020-12-21T14:10:00Z | 1 |
| BTCUSDT and ETHUSDT 1h | 2018-02-09T09:00:00Z | 2018-02-11T04:00:00Z | 43 |
| BTCUSDT and ETHUSDT 1h | 2020-12-21T14:00:00Z | 2020-12-21T15:00:00Z | 1 |

The 4h and 1d series have none. The 1m spans total 20,400 + 1,201 + 1 = 21,602 bars. The
two long spans are the months `2017-12` and `2018-02`, in which the archive's minute file
carries rows whose open times are not on the minute grid; the 5m and 1h series show the same
`2018-02` window. **REASONED, not measured here:** P102 gave these shapes in its census;
this section records only what the store now holds. Instrument: the `kinded_gaps` of
`coverage`, read by `c4_state.py`.

### The hashes of the store after the ingest

`MANIFEST.jsonl` and `IRREGULAR.jsonl` per series, SHA-256 of the file's bytes
(`hashlib.sha256`); the 1d series has no registry.

| series | manifest | registry |
|---|---|---|
| BTCUSDT 1m | `16e1919645f100937f2894d5467954b9c4d2ad38d2b9732d1d552745364de1f8` | `496b2fd52dbac04af2b7b79e1358965389063b78ac2c75f67d0800e26919d8f7` |
| BTCUSDT 5m | `6e748f83f6378121a07b5dba0ff8d71f4821626bceb2242b6ef2b4691acff4f5` | `0cb2068f6e53ea73e645a1729a76f6e00be6c681a51c7f948cbe79cff3f2b1d1` |
| BTCUSDT 1h | `4f549ffedaf7ed55596a389b028fc71db620d3c687d53a8a56a351ab3e34887d` | `db69e0ba89c12c9dc2e4d9a071ca6413c9016cd71d6ed8cd2c12a6a16f8ae4d3` |
| BTCUSDT 4h | `5351a4ce959a9b81a490af2f674fc05e44e549241596eed977159a5f244383ce` | `7c4ee9c601d1188f0dc9ec5436233e9391bd0c266156313d87c916d5656f7b9f` |
| BTCUSDT 1d | `39247bf6d4a3281a1de88f367f316bdf6fd94de276a9f8ba03ca830930a1ce04` | none |
| ETHUSDT 1m | `1cdca7c3f0d28fa7688146f632aed6aad787364e7a37f911f67a46933bbba5d9` | `13b340b18a72b143cbc344ea22042f87602192e539c702e78b2d1b2f395e62de` |
| ETHUSDT 5m | `e9b879dffe0932ccf7f717c81276656f1fe21fd398a6a5164f72b6451dbaf1e6` | `76e237f0c3d23ff3ff08ef581cfe007f595add2c8ee5536d4e00fe8fa7b51f8d` |
| ETHUSDT 1h | `71d0f1e99ef2bcc68a042e4866e5df7345e36034adb047c0a90789e67dc907b2` | `ffeb425a48ab489a5de14ecb74bafe56023c7c48fe222492952d85a519dcd8a5` |
| ETHUSDT 4h | `f650f94bdf4c4bb5545efe1ff62d525f3d70584ccb9aba3e4182874b05aedb82` | `e81691cbb703c68c0c6fb43c73447ba91a945f056512130230386f0b7b8ebf6c` |
| ETHUSDT 1d | `e456846220ef3ffb47107769a391082ab4404d7fc884f657a00f367616d54645` | none |

The two 1d manifest digests equal section 28's, as they must: no 1d line was added.

### What this section decides, and what it leaves open

**Nothing is decided here.** It records that the store the rulings R-L to R-O describe now
exists and verifies clean. **Open, and recorded as a question for S2 (R-P) and not ruled:**
what a backtest does with a window containing a gap, a quarantined span or a registered
short bar. Two shapes are not ruled by R-L to R-O and are noted for the owner: a month whose
every row is quarantined is refused by the importer (`M5m-089`), and none of the 120 months
was such a month.

## 30. M5m S1: the P104 evidence -- the census against the store (A1), the 980 zips fetched and re-ingested (A2), the registry against the raw zips (A3)

Recorded at M5m P105 (C0), from P104's Phase 1, which changed nothing in the tree. An
observation log, so this section only adds; section 29 stands as the record of what P103's
C4 found. Everything below was run from the development tree at `92b493a`, which touched no
venue account, store or lock; the instruments are scratch scripts under
`F:\trading bot\scratch\p104\`, each named with its SHA-256 at the end of the section.

### A1. Why the store's omitted counts exceed the census's

**The prediction record.** There was no prediction file. P103's C4 figures were written in
the session's context summary at `2026-10-08T03:11:15Z`, 26 s before the ingest began
(`03:11:41Z`), and the omitted counts in them were derived by subtraction from the row and
quarantine predictions, so they could not disagree with the grid identity (`M5m-116`). The
figures, as predicted and as observed in section 29: omitted 8,562 (BTCUSDT 1m) and 8,563
(ETHUSDT 1m), 1,703 at 5m, 127 at 1h, 17 at 4h, 0 at 1d; quarantined 21,602, 242, 44, 0, 0.
All matched.

**The rule** (`classify_gaps`, `trading_bot/data/historical.py`): a missing bar's slot
`[slot, slot + interval)` is `QUARANTINED` if a row that was set aside opened inside it,
and `OMITTED` otherwise; a set-aside row that opened in a slot a stored bar already holds
is in no gap. Equivalently, a slot is omitted exactly when no row of the archive, stored or
not, has an open time that floors into it.

**The census's figure differs by construction** (`M5m-117`). P102's census counted, between
consecutive open times of the full population, `spacing // step - 1` bars. Where a run of
off-grid rows ends with an open fractionally inside its slot, that division floors, and the
run loses the bar it ends in. Recomputed from the stored CSVs plus the registry's quarantined
opens (`a1_edges.py`), the census's method gives its published figures exactly and the slot
rule gives the store's:

| series | census method | slot rule (the store) | pairs where they differ |
|---|---|---|---|
| BTCUSDT 1m | 8,560 | 8,562 | `2017-12-18T10:00:20.799Z` to `10:14:00.000Z` (census 12, slots 13); `2018-02-10T05:59:14.789Z` to `06:15:00.000Z` (14, 15) |
| ETHUSDT 1m | 8,561 | 8,563 | `2017-12-18T10:00:20.810Z` to `10:14:00.000Z` (12, 13); `2018-02-10T05:59:14.800Z` to `06:15:00.000Z` (14, 15) |
| 5m, each | 1,702 | 1,703 | `2018-02-10T05:58:14.789Z` (BTCUSDT) and `.800Z` (ETHUSDT) to `06:15:00.000Z` (2, 3) |
| 1h, each | 127 | 127 | none |
| 4h, each | 17 | 17 | none |

The explanation given before the run, that a shifted row sat in an already-held slot, was
wrong, and so was the statement that the 5m figure matched the census exactly; the table
is what was measured. Instrument: `a1_edges.py`, output `a1_edges.txt`.

### A2. The 980 zips fetched, verified, re-ingested and compared (R-R)

- **Authority:** the owner's R-R, quoted in `docs/NEXT_MILESTONE.md` under S1.
- **What was run:** `a2_fetch.py`, which calls the downloader's own `obtain` for the 110
  months of each series' manifest. The `.CHECKSUM` is fetched first, the zip is fetched and
  verified against it before anything is written, and a zip already on disk that equals
  its checksum is reused. Hosts: `data.binance.vision` only; no listing was requested.
  Window (UTC): `2026-10-08T03:30:10Z` to `03:54:52Z`, 1,481.8 s by the script's own clock.
  Result: **fetched 980, reused 120, failed 0, 491,890,641 bytes fetched.**
- **What is on disk now:** 1,100 zips of 563,599,382 bytes and 1,100 `.CHECKSUM` files of
  96,800 bytes under `data/historical/_zips/<SYMBOL>/<interval>/`, 563,696,182 bytes in
  all (the 120 from P102 were 71,708,741 of the zip bytes).
- **The comparison:** `a2_compare.py` re-ingested every month, from its kept zip and its
  kept `.CHECKSUM`, with `ingest_zip` into a scratch store at
  `F:\trading bot\scratch\p104\store_scratch`, outside the repository (asserted by the
  script), then compared the scratch CSV bytes with the stored CSV and the scratch manifest
  entry with the stored one field by field. 327.3 s.

| group | months | CSV bytes identical | manifest entry equal | failed |
|---|---|---|---|---|
| stored before P103's C4 | 980 | 980 | 980 | 0 |
| ingested by P103's C4 | 120 | 120 | 120 | 0 |

  Every manifest entry carries `zip_sha256`, so the archive's zips are byte-identical to
  those of P101's download and P103's; the venue changed nothing in the interval
  (`M5m-118`).
- **The stored store was not written.** Its digest, taken by `store_digest.py` before the
  fetch (`2026-10-08T03:29:58Z`) and after the comparison (`04:01:57Z`), is identical, and
  the scratch store's digest, taken at P105 by `store_digest_path.py`, equals it too, in
  every series (the manifests are written sorted by month, so the scratch manifests are
  byte-identical to the real ones). Per series, the instrument being the SHA-256 over each
  file's name and SHA-256 in name order:

| series | files | bytes | sha256 |
|---|---|---|---|
| BTCUSDT 1m | 112 | 479,729,886 | `d38f6cc530b46e7fbb2761bcbb842c6e6cb191b70a351fd147ff03086344eeb5` |
| BTCUSDT 5m | 112 | 95,572,842 | `54b66f30b6d51b4f014a7d16927a73b364fe323d83e7bfeb158cc399534a41f2` |
| BTCUSDT 1h | 112 | 8,118,959 | `41ebb7082e439b9c5fe4d69390a36d7f1163ed2c78aff440dfb257894e1502c8` |
| BTCUSDT 4h | 112 | 2,088,014 | `cb78c47c43e571b02308acf42ca4705c5d0a687159bf89ced5a94f47b389cbe7` |
| BTCUSDT 1d | 111 | 394,722 | `0a1ef88bfb685b99f0a91840b62e179cc128cf3de316a4333ca22669b39c39b8` |
| ETHUSDT 1m | 112 | 461,957,138 | `ef349037ecf4b1620aa0fc9819cd234700eec96a75f4da4f5c998573db93c8ea` |
| ETHUSDT 5m | 112 | 92,067,004 | `dc87cd85ab2976b4847782b25488acdf03dad807950eb15c42de4fcb20f5112b` |
| ETHUSDT 1h | 112 | 7,827,621 | `100e018dddbcddddfaed17e7b1c5118cef35c004e21731a7eafcad27dc890a4d` |
| ETHUSDT 4h | 112 | 2,015,470 | `2d9cc3fa08cb5b522f5b5823fd2232542a361953b676ffab17f122b8b77f0c05` |
| ETHUSDT 1d | 111 | 382,543 | `7657ceb2eb8388c2b374e571f87453d9d0114e079ed88776b927c0bd13a0823e` |
| **store** | **1,118** | **1,150,154,199** | `2ff390f2039e780b156492c14648570cdd6f493268a56b54510bdb30cf6cab5e` |

  The 112 files of a minute-scale series are 110 CSVs, `MANIFEST.jsonl` and `IRREGULAR.jsonl`;
  a daily series has no registry.
- **The kept zips, per series**, the instrument being `sha256sum *.zip` over the series'
  directory, piped to `sha256sum`: BTCUSDT 1m `398bfff0c9fd963e032af7432062a90483d907f8c54fff191a0b524ffc69317a`,
  5m `89472ad2016f585119d1c1109f2a6494a827cccc24d896b9e954967d7e2f4dd3`, 1h
  `a1f0d602e60df6378025e0598bfef99076d3f44d026bc41512837f0b88c59b73`, 4h
  `c70fc3198b9b28d34ecd01591ddf246a4a1637f44d2b0ab716590a9135e0a36e`, 1d
  `1d794e3f652f723578818ef41ee415b814aac68456da161ebca7d5fbe2f5921b`; ETHUSDT 1m
  `18437a35a5f75f0adc7509a89dd0b1c635ce4d1fbefc07be88918e8655ea5281`, 5m
  `c8f196bf0c999db5675e96dd6b407f6c45ddd82cb3c05d04fea56692003a0908`, 1h
  `624536b97e794ffd31cd62c80a0dc1f57b68d4fa3b0f9002ca56aa476c212672`, 4h
  `0765ed54c35b690bcef9f923d099ab4c33ee5213c829c37ec783adf5e6e03d23`, 1d
  `ce7c9a69919d75cd639a04796eca53897dd5d9d5b01e7c690cd10be60a916c30`.

### A3. The registry against the raw zips, row by row

`a3_registry.py` does not import the importer's classifier. For each of the 1,100 zips it
checks the zip against its kept checksum, then re-derives every row's shape from its raw
line (open and close as 13-digit milliseconds or 16-digit microseconds divided by 1,000; off
the grid, then close not after open, then the offset of the close from `open + interval - 1`).

- **Registered rows:** 124 of 124 registry lines are found verbatim in their source zips at
  the line the registry names, with `raw` equal to the archive line, the shape re-derived to
  the same value, the `source_url` equal to the manifest's, and a stored row with that open
  time whose prices, volume and normalised close equal the raw line's. By shape: 110 short
  bars, 8 one-millisecond-late rows, 6 whole-second rows. Every quarantined line has no stored
  row with its open time.
- **Completeness, in both directions:** 1,100 zips and 11,700,573 rows read; **43,902
  irregular rows found independently, 43,902 registry lines, 0 found and not registered, 0
  registered and not found.** The registry holds 124 registered lines and 43,778 quarantined
  (43,772 off the grid and 6 whose close is not after their open). No row has a close more
  than one millisecond after its slot's end, and no short bar at an offset of -999 ms lacks a
  whole-second close, so the re-derived rules and the importer's agree on every row.
- **0 problems.** 22.1 s. (`M5m-119`.) The re-derivation shares the importer's rule order, so
  this checks the code against the data and not the rule against the venue.

### The other P104 measurements, for their digests

P104's B-part measurements are design evidence and are declared as findings
(`M5m-121`, `M5m-122`, `M5m-127`, `M5m-128`); their instruments and outputs are listed below
so that each figure can be traced to the bytes that produced it. The timings were taken on
`BTCUSDT` 1m for March 2024 (44,640 bars) while the A2 fetch was running.

### Digests of the instruments and outputs (SHA-256)

| file (under `F:\trading bot\scratch\p104\`) | sha256 |
|---|---|
| `a1_edges.py` | `e38db5c1f525ee927f17014107eb81069d8200425981c6dddb153ec945e46d56` |
| `a1_edges.txt` | `cfbafb04fb41665b619b432d8bea07ba6eed8ba709d27ebfcb85afa7715b11d7` |
| `a2_fetch.py` | `e614ddc00ffa6809aec64f0c0272c530fd63025a509d58c4f48afe7803281781` |
| `a2_fetch.txt` | `67109fab1ee69de7fd8c4a58652a6e3c69a9f378ecfb606dbf9eea5734ec9670` |
| `a2_fetch_times.txt` | `f98d57b12f19677a7cb14a9b8ee6ac2a11e3be6bf5922ccda40ec1c89d005e99` |
| `a2_compare.py` | `bcd19b3bc181b1f5d11532d9610a543174743c570d331bec8f5bb60cb5b2e065` |
| `a2_compare.txt` | `5d6f6969a0700c8a414c093cf06bf1f0b6da91b21ea078c91c68c78cc50ca42b` |
| `a3_registry.py` | `16eb7ab8809fd260f44cdff37a797d4e31e2bd44b623b307f8a04ad12bd607c5` |
| `a3_out.txt` | `7097d351df4fc6aadbc2bca277bb4010fdc119febf206b02e2e355a4a5f1587e` |
| `store_digest.py` | `a1fab169aa2bac581aef531e632158ff9185e5a35ab5200a940c7d288f3ef29b` |
| `digest_before.txt` | `91d8fbdb0210b1d428b193610b0859c065a1cc3af2d49b22e9783924fb4619b5` |
| `digest_after.txt` | `aea9431f04ec65c008c6290c29b51c08684f30c632ec69b25b76d07d5c1a39aa` |
| `find_pred.py` | `ae1f6522b6e1f6460cc37778edf2241e5a81dfa4ad8dcc223b16cbe8d46fd906` |
| `b5_timing.py` | `056204172e7207f6aefe975c34bfce8c2487fd1cdb96bb6c84211f23175fa9ec` |
| `b5_fast.py` | `bf218a6f138e465daf56fc322f4a557fe9f777d446e0136abfdbe4b89a7d70be` |
| `b5_parts_btc1m.txt` | `22240055f959aefe7e552c17a9b27442b13974b5357980bb32188daf3f08af68` |
| `b6_intrabar.py` | `8dcdd77b1069f443445083c00f51926356b802d5d9046265c68f4f04c3fa0897` |
| `b6_out.txt` | `3168e54bec2d3805b5e75cab14b881e167876e12a51404c1ef24005eb61dac6b` |
| `b4_sensitivity.py` | `c3e433b07b286d35c0e54671a89a8441dea30f0a97406fd9e1c8f720f128b785` |
| `b4_out.txt` | `9815c73b8e1ff871c0f08a011f9eb3dc22215fe8c0f9a7c0bf9a60569f9ef3fd` |

P105's own prediction files, under `F:\trading bot\scratch\p105\` (R-T):
`predictions_halts.txt` `a6f15afff91c81bf3c2d05b69f0f7a9f0fe36963672d8b4dfb14884286d7a8ae`
and `predictions_c0.txt` `d59bacc38ad414df6885750e2666517327e9c0f839b941d533f79bfd5a6c12b0`.
Their observations are `gate_h5.txt` and `digest_scratch_store.txt` in the same directory.

## 31. M5m S2: the four `exchangeInfo` snapshots, mainnet and Testnet (P105 C3)

Recorded at M5m P105 (C3). An observation log, so this section only adds. **The four GETs
the owner's R-Z authorised were made, once each, by `scripts/download_exchange_info.py`,
and stored raw with their SHA-256.** The record of what was stored is this section's digests:
`data/*` is ignored by git, so the files themselves are not in any commit.

### What was run

- **Authority:** R-Z, quoted in `docs/NEXT_MILESTONE.md` under S2: *"One keyless
  exchangeInfo GET per symbol, on mainnet and on Testnet, is authorised. The raw response is
  stored with its SHA-256, and backtests load filters only from the stored file."*
- **Code:** `scripts/download_exchange_info.py` and `trading_bot.backtesting.exchange_info`
  as committed by P105's C3, launched from the development tree with `HEAD` at `b1ffaa7` and
  the C3 files not yet committed. It touches no venue account, store or lock.
- **Command, from the repository root:** `python scripts/download_exchange_info.py`, with the
  defaults: `--symbols BTCUSDT ETHUSDT`, `--environments mainnet testnet`, `--data-dir
  data/historical`. Stdout went to a scratch file.
- **Window (UTC):** `2026-10-08T04:37:31Z` to `04:37:33Z`. Exit status **0**.
- **Requests:** four, in the order below, each a GET with no key and no header but a
  user agent, to `<host>/api/v3/exchangeInfo?symbol=<SYMBOL>` on `api.binance.com` (mainnet)
  and `testnet.binance.vision`. No retry: the script has none.

### Result

| environment | symbol | bytes | `serverTime` (UTC) | sha256 of the stored response |
|---|---|---|---|---|
| mainnet | BTCUSDT | 5,349 | 04:37:32.647 | `9cf9d5446e7f83508b445a825d2cf776276a8f528ca9313c04e92eeb3d5c0591` |
| mainnet | ETHUSDT | 5,336 | 04:37:32.871 | `55c2038ade11928a9e7d27f776bebe37c563ce346682daaf251ea1881090db75` |
| testnet | BTCUSDT | 2,239 | 04:37:33.175 | `40e24c66110ba645ef49ca595618321fdbe2a36f9eab9638eea564dd8b797dc7` |
| testnet | ETHUSDT | 2,240 | 04:37:33.439 | `87e5095e0e177267d7fe039b8ce1925c8e07903a0f64211c2b948f82705777cc` |

Each digest was re-derived with `sha256sum` over the stored file and equals the sidecar
`<SYMBOL>.json.sha256` beside it and the figure the script printed. Stored under
`data/historical/_exchange_info/<environment>/<SYMBOL>.json`.

**What the live mapper reads from them** (`load_snapshot`, which hands the symbol's entry to
`to_symbol_info`), the same on both environments except where marked:

| symbol | tick | step | min qty | min notional | market lot max qty (mainnet / testnet) |
|---|---|---|---|---|---|
| BTCUSDT | 0.01 | 0.00001 | 0.00001 | 5 | 147.44396091 / 133.97193096 |
| ETHUSDT | 0.01 | 0.0001 | 0.0001 | 5 | 2766.56983598 / 2823.18581380 |

`MAX_NUM_ALGO_ORDERS` is 5 and `MAX_NUM_ORDER_LISTS` 20 on all four. `PERCENT_PRICE_BY_SIDE`
is the same on all four: **bid up 1.2, bid down 0.5, ask up 2, ask down 0.8**, over 5
minutes. Both quote assets are USDT and every status is `TRADING`. The filter types present
are the eleven the repository's recorded fixture lists.

### Against the predictions (`F:\trading bot\scratch\p105\predictions_c3.txt`)

SHA-256 `2cca55db5ca989bc97234d7a466eb510642e616a00028de240598d70bfdaebae`, written before the
first request of any kind to either endpoint. **G1, G2, G3, G4, G6 and G7 held.** **G5 was
wrong on two counts** (`M5m-142`): it predicted Testnet's band to be the recorded 2 / 0.5 /
2 / 0.5, and mainnet's to differ (5 / 0.2). Testnet's is 1.2 / 0.5 / 2 / 0.8, and mainnet's is
identical to it. Against the repository's recorded Testnet BTCUSDT fixture
(`tests/unit/test_exchange_mappers.py`, `SYMBOL_FULL_TESTNET`), nine of its eleven filters are
identical; the two that differ are `MARKET_LOT_SIZE.maxQty` (141.67845966 then, 133.97193096
now, which moves with the market) and `PERCENT_PRICE_BY_SIDE`. The band the fixture and
`docs/M5_NUMBERS.md` (section 2, *"Provenance: ... TESTNET, BTCUSDT and ETHUSDT, 2026-08-08"*)
record as symmetric has since changed to an asymmetric one; the dated provenance there stays
true of 2026-08-08.

### Digests of the C3 instruments and outputs (SHA-256)

| file (under `F:\trading bot\scratch\p105\`) | sha256 |
|---|---|
| `predictions_c3.txt` | `2cca55db5ca989bc97234d7a466eb510642e616a00028de240598d70bfdaebae` |
| `get_out.txt` | `d44d1e85ecb5c5be8f996567dc2a9164672eea3ee926af4d7048096b02c14aaa` |
| `get_times.txt` | `d52271cff770e3db0fce37baeb2e76a629f7c323a5d2f7725133df7c1d39069d` |
| `observe_c3.py` | `7d45205cf2955698eb2f0fda11d52e366f480e059f1d32cc78c8dcba07899211` |
| `observe_c3.txt` | `b096ba98d33ef07873f2e54bdd95464030b511cceca0d2d0635282f2a5675300` |

## 32. M5m S2: the smoke backtest, March 2024, run twice (P106 C6)

Recorded at M5m P106 (C6). An observation log, so this section only adds. **One backtest
smoke run was made, twice, as the owner's R-AE authorised: the committed config, BTCUSDT 1m
and ETHUSDT 5m, 2024-03-01 to 2024-04-01.** It is a test of the machine and not a result about
the strategy: no metric exists yet (S3), the sample is one month, and the parameters are the
config's.

### What was run

- **Authority:** R-AE, quoted in `docs/NEXT_MILESTONE.md` under S2: *"One backtest smoke
  run is authorised: the committed config, BTCUSDT 1m and ETHUSDT 5m, 2024-03-01 to
  2024-04-01, run twice."*
- **Code:** the repository root at `d5bff58eb52ec081ae76b9406bee7dbc80d5f33d`, tree clean,
  `config.yaml` clean with SHA-256
  `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0` (equal to the committed
  blob). **The install is EDITABLE**, so the record names `install_kind=editable`,
  `code_commit=unknown`, `commits_agree=unknown`, and the only identification of the running
  code is `checkout_commit` and `checkout_dirty=false`. `trading_bot.__file__` was shown to
  resolve to this checkout's `src` before the first run. The deployment-clone doctrine in
  `CLAUDE.md` governs `run`, which a backtest is not (no venue, no credential, no store or
  lock); it is noted here and not worked around (`M5m-182`).
- **Command, twice in sequence, from the repository root:** `python -m trading_bot backtest
  --start 2024-03-01 --end 2024-04-01`, stdout to scratch files. **Exit status 0 both times.**
- **Windows (UTC):** run 1 `2026-10-08T20:18:42Z` to `20:20:42Z`; run 2 `20:20:42Z` to
  `20:22:42Z`. The record's own clock: `wall_seconds` **118.797** and **118.328**.
- **Records:** `data/backtests/20261008T202042586929Z-5350070f7a9e/` and
  `data/backtests/20261008T202242653936Z-5350070f7a9e/`, each `run.json` (3,860 bytes) and
  `trades.csv` (239,657 bytes). `data/*` is ignored by git, so the digests below are the record.

### Result

| fact | run 1 | run 2 |
|---|---|---|
| exit status | 0 | 0 |
| `problems` / ERROR records / stream handler failures | none / 0 / 0 | none / 0 / 0 |
| bars served, BTCUSDT 1m / ETHUSDT 5m | 44,640 / 8,928 | 44,640 / 8,928 |
| first / last open, BTCUSDT | 2024-03-01T00:00 / 2024-03-31T23:59 | same |
| last open, ETHUSDT | 2024-03-31T23:55 | same |
| gaps seen / short bars seen | 0 / 0 | 0 / 0 |
| BUY entries queued / filled / refused by FOK / expired / unaffordable | 628 / 628 / 0 / 0 / 0 | same |
| CLOSE queued / refused `nothing_to_close` | 610 / 17 | same |
| trades booked | 626 (BTCUSDT 522, ETHUSDT 104) | 626 |
| exits by reason | close 610, stop_loss 8, take_profit 8 | same |
| open at the end | BTCUSDT, ETHUSDT | same |
| entry fees / exit fees (USDT) | 122.494434554672850 / 122.354975506698450 | same |
| realised total (USDT) | -384.308458035771300 | same |
| final free quote (USDT) | 9231.414198714929200 | same |
| cash identity residual | `0E-21` (zero) | `0E-21` |
| trades spanning a gap / a short bar | 0 / 0 | 0 / 0 |
| trade-log SHA-256 | `5350070f7a9eeea27f8f8e63ddc765110a9b66bd3e06881e9dfdd657c313ba36` | identical |
| `trades.csv` SHA-256 | `bd1d6991e9b11a63fa5e980f8724dd19b89603a37a24b540ea3f208d1ac630a3` | identical |
| `run.json` SHA-256 | `a5fced2beaad0c7b7d3dfa184d4af4fa794891240e195cc4e533a16c71cd4e37` | `e360eb2a4455d52ebd9862a027f7332d34e83c202c8756265e550af866b11a83` |

**Determinism, three ways:** the two trade-log digests are equal; the two `trades.csv` files
are byte-equal; and the two records are equal in every key but `wall_clock` (the two `run.json`
digests differ only there). **The booking identity, recomputed from `trades.csv`:** for all
626 rows, `realised = exit_gross - entry_quote_total - exit_fee` holds exactly, and the sum of
`realised` equals the record's `realised_total`. **Reconciled with the signals:** 628 queued
entries, 626 trades and 2 positions open at the end; 1,255 dispatches are 628 BUYs and 627
CLOSEs, of which 610 queued and 17 were refused `nothing_to_close`. **Sixteen of the 17 are
explained** by the 16 stop-loss and take-profit exits, each followed by the down-cross `CLOSE`
that found nothing to close. **The 17th is not**: the refusals run from `2024-03-05T08:04` to
`2024-03-27T14:49`, none before a pair's first BUY (`2024-03-01T00:24` and `00:39`), and the
log line carries no more than the reason (`M5m-183`). 113 of 626 trades won.

**The independent derivation agreed.** `derive_c6.py` read the stored CSVs with pandas and
nothing else: 44,640 and 8,928 bars in the window, no irregular step in either, and SMA(20/50)
up-crosses of **523** and **105**, which sum to the **628** queued entries. Its down-crosses
sum to 626, the trade count.

**Runtime against P104.** `M5m-121` measured 1,987 us per bar through the real provider,
engine and strategy, and 2,279 with `risk.evaluate`, projecting 106 to 122 s for 53,568 bars.
Measured: **118.8 s and 118.3 s, 2,218 and 2,209 us per bar**, inside the projection and
within 0.4% of each other. The projected 3.2 to 3.7 h for S5's joint baseline stands; R-V's
incremental frame is not triggered by this run.

### Against the predictions (`F:\trading bot\scratch\p106\predictions_c6.txt`)

SHA-256 `4f1845f8e5b397a74e18706b8dbfe3936d311187e042607e5d0f1ab27bf4447d`, written before the
first run. **Nine of its ten items held** (completion, equal digests, the bar counts and
bounds, the signal and entry ranges, the exit mix, the booking identity, the flags, the
runtime, the provenance, the clean checkout). **Item 3 was half wrong** (`M5m-180`): it
predicted that no series has a registry, and both do (`registry_sha256` is
`496b2fd52dbac04af2b7b79e1358965389063b78ac2c75f67d0800e26919d8f7` for BTCUSDT 1m and
`76e237f0c3d23ff3ff08ef581cfe007f595add2c8ee5536d4e00fe8fa7b51f8d` for ETHUSDT 5m); what held
is that none of its lines falls in the window, with 0 registered and 0 quarantined there.

### A side effect the owner should know about (`M5m-179`)

`main` calls `setup_logging`, so **the backtest wrote into `logs/trading_bot.log`, the file the
live bot writes and the census tools read.** MEASURED: 6,308 lines were appended between
`2026-10-08T20:18:42Z` and `20:22:42Z`, from pids 17472 and 21884: 2,476 `intent_dispatched`
and 34 `risk_refused` lines (the simulated signals, whose `signal_ts` is in March 2024), two
`engine_stopped` lines with `clean_shutdown=False`, and two `ERROR` `boot_provenance` lines
reading `verdict=refused` (that verdict gates `run` only, and the run's own ERROR tally was not
yet counting when they were written). Nothing in those lines says they are not the bot's.
`scripts/run_census.py` and any future log census would count them. **Nothing was changed
here;** whether a backtest should log to its own file is the owner's, and until then a
census over `logs/trading_bot.log` after 2026-10-08T20:18:42Z must exclude these two pids.

### Digests of the C6 instruments and outputs (SHA-256)

| file | sha256 |
|---|---|
| `predictions_c6.txt` (under `F:\trading bot\scratch\p106\`) | `4f1845f8e5b397a74e18706b8dbfe3936d311187e042607e5d0f1ab27bf4447d` |
| `derive_c6.py` (the scratchpad) | `58642cb36303d9dd7fa6859aed35ed33f7349ba85e73df9ed69fe1a552203895` |
| `analyse_c6.py` (the scratchpad) | `e211bcd72fafe07e073050835f9d1e01880b2f755799e8d81a8b93ea91119529` |
| `smoke_run1.out` (1,114,155 bytes) | `f96b2ccb7a4ae7e0c61042cf95dbf7026b5518531508c8dbfa8f2416c6dbae66` |
| `smoke_run2.out` (1,114,155 bytes) | `81d2e5c695e76de198f8f2e1fadcfb17d99ef323df3073dae401cd7e94dc32f9` |

## 33. M5m S2/S3: P107's Step 0 -- the spun-off task, the band, the refusal, the flake rate and the Testnet klines

Recorded at M5m P107 (C0). An observation log, so this section only adds. Six read-only
checks, S0a to S0f, made on `2026-10-09` with `HEAD` at `778e9b3`. Predictions:
`F:\trading bot\scratch\p107\predictions_step0.txt`, SHA-256
`b96560fc354952d9a90d59357c918a29bb239a862ff6e7ebe61d02752d102382`, written before any of
them ran. **The halts H1 to H6 all held**: `HEAD` `778e9b3d0373dbcf290ab4e8e216ffb854d3842e`;
`origin/main` `dbbffadd375ee2257fd231ae32f4fec5f20c3ffd` with 6 commits ahead (the owner has
pushed through `dbbffad` and not since); `git status --porcelain` empty; the Testnet ping `200`
at `2026-10-09T04:13:29Z`; the gate 165 files, mypy 90, `2977 passed, 1 skipped` in 146.45 s
(`gate_h5.txt`, SHA-256 `90805274f37316780a15a1ceca2f94b510b7280cc0fad740f1ca8491e8892e2e`);
`check_findings.py` `max 183`, no duplicate, no gap, nothing cited and not declared, blockless
`[934eb45]`.

### S0a, S0b and C0's cause -- P106's own results, quoted

These three were made at P106 and are quoted from that session's tool results (the transcript
`883c8675-3e61-486c-93c1-fb48f9743422.jsonl`) and from `41a621a`'s message.

- **S0a, the *"spun-off task"* of `M5m-155`.** `git worktree list` showed the main worktree
  alone, `F:/trading bot/files/binance-trading-bot/binance-trading-bot  dbbffad [main]`. Branches:
  `claude/zen-mclean-9d3c40`, `main`, `phase5-m3-risk-manager`. The first of those is an
  ancestor of `main` (*"ancestor of main"*), tip `d1074c6`, dated 2026-10-01. `.claude/worktrees`
  holds one directory, `codebase-orientation-b2e0ca`, dated Jul 24. The session list answered
  *"No reachable agents -- no other Claude session is running on this machine right now"*.
  So **no spun-off task was running or could write to the tree**, and none had.
- **S0b, the `PERCENT_PRICE_BY_SIDE` band.** A grep of `src/`, `config.yaml` and the config
  coherence checks found **no hard-coded band multiplier**. The band is read from the venue
  only, at `to_symbol_info` in `src/trading_bot/exchange/models.py` lines 418 to 425
  (`bidMultiplierUp`, `bidMultiplierDown`, `askMultiplierUp`, `askMultiplierDown`,
  `avgPriceMins`); `price_band_margin` is a `Decimal` config field defaulting to `0.02`. **The
  pre-existing false text P106 listed:** `docs/M5_NUMBERS.md` section 2 (*"The band is 0.5x-2x of
  the 5-minute average"*, *"four fields rather than the two '0.5x-2x' implies"*);
  `docs/QC_PROTECTIVE_ORDERS.md` line 42 (*"pending price to 0.5x-2x of the 5-minute
  average"*); the comment at `src/trading_bot/config/models.py` line 270 (*"measured
  `PERCENT_PRICE_BY_SIDE` band is 0.5x-2x of a 5-minute average"*); and the fixtures
  `SYMBOL_FULL_TESTNET` in `tests/unit/test_exchange_mappers.py` and the 2 / 0.5 assertions at
  `tests/unit/test_exchange_info.py` lines 90 and 91. The measured band is **1.2 / 0.5 / 2 / 0.8**
  (section 31).
- **C0's measured cause (R-AD, `41a621a`).** *"It is the wall-clock timestamp"*: *"ZipFile.writestr
  given a str name stamps time.localtime(time.time()) into the member header at 2-second
  resolution, so zip_of() returned different bytes for the same month in different ticks."* With
  zipfile's clock four seconds apart the body of
  `test_one_that_does_not_match_its_checksum_is_fetched_and_replaced` returned code 1 naming
  `ChecksumMismatchError`; the unit suite under a clock-moving plugin read *"2 failed, 2873
  passed, 1 skipped"* before the fix and *"2877 passed, 1 skipped, none failed"* after.
  Evidence at `F:\trading bot\scratch\p106\`: `repro_c0_before.txt`, `repro_c0_after.txt`,
  `shim_c0_before.txt`, `shim_c0_after.txt`.

### S0c -- the heredoc after C5 ran BEFORE the commit, and nothing was amended

Predicted before. The shell command that fixed one count in `msg_c5.txt` ("Four sites unpacked"
to "Five sites unpacked") was the first statement of the SAME command that ran `git commit -F`,
so it ran to completion first: the message file's mtime is `2026-10-09 02:15:57.730 +0600` and the
commit is stamped `02:15:58 +0600`. **`d5bff58eb52ec081ae76b9406bee7dbc80d5f33d` was not
amended**: the reflog holds one `commit:` entry for it and none reads `(amend)` among the
twelve newest, and the committed message equals `msg_c5.txt` byte for byte once git's trailing
newline is set aside (7,437 bytes in the file, 7,438 in git), with `Five sites unpacked` present
and `Four sites unpacked` absent. (The whole reflog holds ten `amend` entries, all older.)

### S0d -- `M5m-183`, the 17th refusal, found by bar and explained

Predicted: the owner's hypothesis, a down-cross with no position before any up-cross, **false**,
and a 60 / 40 split between a visible-in-the-trade-log cause and a signal-count difference. **The
cause was neither as stated, and the mechanism is not in the trade log.**

- **Pairing, from the run's own log (pid 21884) and its `trades.csv`:** 628 BUYs dispatched,
  610 CLOSEs queued, 17 CLOSEs refused `nothing_to_close`; 16 stop-loss and take-profit exits.
  **Sixteen refusals follow a stop or target. One does not**, ETHUSDT `2024-03-05T08:04:59.999`,
  whose previous exit is a plain `close` at `03:40`.
- **The log holds one more CLOSE than the strategy's rules give.** `s0d_diff.py` derives every
  signal with the repository's own `sma`, `crossed_above` and `crossed_below` over the stored
  closes and compares: BUY 105 / 105 and 523 / 523; CLOSE BTCUSDT 522 / 522; **CLOSE ETHUSDT 104
  derived against 105 logged**, the one extra at **`2024-03-05T03:34:59.999`**, a bar that rose
  (closes 3643.50 then 3653.08). That `CLOSE` was executed: the position opened by the BUY of
  `2024-03-04T23:09:59.999` was sold at the next open and booked at `03:40`. The `08:04` signal
  is therefore the **legitimate** death cross, refused because nothing was left to close.
- **The mechanism, by probing the real replay at three window starts** (`s0d_probe.py`, the
  committed config, ETHUSDT only, wrapping `generate_signal` without changing it). At the `03:30`
  bar the two averages are the same number: SMA(20) = SMA(50) = 3627.774. With the window
  starting `2024-03-01` (a 1,000-row buffer) the pairs are fast `(3627.5645000000004,
  3627.774)` and slow `(3627.2309999999998, 3627.7740000000003)`, so `fast < slow` by 4.5e-13,
  `crossed_below` fires and the reason reads *"death cross: SMA(20)=3627.774 crossed below
  SMA(50)=3627.774"*. Started `2024-03-04` (831 rows) the same bar reads fast `3627.7740000000003`
  against slow `3627.7739999999994`, and started `2024-03-05` (543 rows) the same: **no signal**.
  An exact tie of the two averages is decided by floating-point noise, and the noise depends on
  how many rows precede the bar. My earlier count of bars with `fast == slow` exactly (0) missed
  it for the same reason: the tie is mathematical and the floats differ in the last digit.
- **What this says beyond the one trade.** The strategy's *"stateless recomputation ... identical
  after a restart"* does not hold at a tie, and this is a property of the live path too: the buffer
  after a restart is seeded to a different length. Nothing was changed (the strategy and the
  indicator are not this prompt's), and the question is the owner's. `M5m-184`, `M5m-185`.

### S0e -- the survey test file, 50 bare runs

Predicted 0 failures. **Observed 0 failures in 50**, every run `14 passed` in 3.71 s to 4.30 s,
each to its own file under `F:\trading bot\scratch\p107\s0e\` (the exit codes are in
`codes.txt`, SHA-256 `d9fb2c38cc12a5791c3cb3a3b86d1a63a255a0a18087c9b52b1af51f49f6050a`). The two
failures `M5m-168` recorded at P106 happened while heavy pytest work ran beside them and were not
reproduced alone (6 of 6, then 2 of 2); 50 more clean runs do not establish the cause, and they
were not made under load. **The cause stays UNMEASURED, and there is no flake to fix** (`M5m-186`).

### S0f -- R-AL: Testnet kline availability, read-only

Predicted, wrongly: earliest on or before `2026-08-01` and the window retrievable in full. **13
GETs** (`/api/v3/time` and `/api/v3/klines`, keyless, no header but a user agent) between
`2026-10-09T04:23:16Z` and `04:23:22Z`, by `s0f_testnet_klines.py`, SHA-256
`31cd1c18ba61c714669605be0c6e709a783fcbb53c32e9ef4c26b92fcb2fe9b2`; result
`s0f_result.json`, SHA-256 `a8119bdc65996ae62e7619296331ecf7e50b6dc017920ff330a45d83d9466283`.

| series | earliest open Testnet returns | latest open | bars returned for `[2026-09-04, 2026-09-25)` | expected |
|---|---|---|---|---|
| BTCUSDT 1m | `2026-10-07T10:32:00Z` | `2026-10-09T04:23:00Z` | 0 | 30,240 |
| BTCUSDT 5m | `2026-10-07T10:30:00Z` | `2026-10-09T04:20:00Z` | 0 | 6,048 |
| ETHUSDT 1m | `2026-10-07T10:32:00Z` | `2026-10-09T04:23:00Z` | 0 | 30,240 |
| ETHUSDT 5m | `2026-10-07T10:30:00Z` | `2026-10-09T04:20:00Z` | 0 | 6,048 |

**The window is not retrievable in any part.** Testnet holds about two days of history, from
`2026-10-07T10:30Z`; REASONED that the venue reset its Testnet then, since the bot's own orders
ran there from August and September and nothing before the 7th survives. The `M5m-032`
question, *what Testnet retains*, is answered, and the Testnet trades of 2026-09-04 to
2026-09-25 that S0's census holds have no Testnet klines to be replayed over (`M5m-187`).

### Digests of the Step 0 instruments and outputs (SHA-256)

| file | sha256 |
|---|---|
| `predictions_step0.txt` (under `F:\trading bot\scratch\p107\`) | `b96560fc354952d9a90d59357c918a29bb239a862ff6e7ebe61d02752d102382` |
| `s0d_refusals.py` (the scratchpad) | `88c47d81e55d2defeaad817a8961cc4181393239b8fa1d5ca5e40b419a3c6f94` |
| `s0d_tie.py` | `0d92587a573ac4fe8aab84b501e9a0ffd8a4182b4cf2ed17f2f0eafadaf1e09f` |
| `s0d_diff.py` | `58a167a1b16958fd95d466392f563beb7f750d77697d5855c88cca82b57caa03` |
| `s0d_probe.py` | `c0f85e83aefc0cc994b88a74d9a1cc4268648026713bfba97198162d94daafde` |

## 34. M5m S3: the quarterly regime labels, computed once from the store (P107 C4, R-AI)

Recorded at M5m P107 (C4b). An observation log, so this section only adds. **The labels the
owner's R-AI ordered were computed, once, on `2026-10-09`**, by `scripts/regime_labels.py` as
committed at `13297bb` (C4a), launched from the development tree with `HEAD` at `13297bb`:
`PYTHONPATH=src python scripts/regime_labels.py`, exit 0, over `data/historical`. It reads
BTCUSDT's daily bars through `HistoricalStore.candles`, which hashes each month file as it reads
it, and writes the two files below with mode `x`.

### What was written

| file | sha256 |
|---|---|
| `docs/REGIME_LABELS.json` (475 lines) | `6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72` |
| `docs/REGIME_LABELS.json.sha256` | records the line above in `sha256sum` format |
| the store's `BTCUSDT/1d/MANIFEST.jsonl` it was read from | `39247bf6d4a3281a1de88f367f316bdf6fd94de276a9f8ba03ca830930a1ce04` |

Source: 3,332 daily bars, `2017-08-17T00:00Z` to `2026-09-30T00:00Z`, 110 monthly files. **Result:
37 quarters, 2017Q3 to 2026Q3, 36 labelled and 1 partial** (2017Q3, 45 of 92 days: the history
begins 2017-08-17). Labelled: **rising 13, falling 7, sideways 16**. `--check` re-derived both
files from the store and found them equal (exit 0); a second write was refused (exit 2) and
changed nothing (`regime_run1.txt`, SHA-256
`01b73765efd48b74c2e445abd90d430a49e0370948069238722675272a3084f6`, holds the first run's output).

| regime | quarters |
|---|---|
| rising | 2017Q4 2019Q2 2020Q2 2020Q3 2020Q4 2021Q1 2021Q3 2023Q1 2023Q4 2024Q1 2024Q4 2025Q2 2026Q3 |
| falling | 2018Q1 2018Q4 2019Q3 2021Q2 2022Q2 2025Q4 2026Q1 |
| sideways | 2018Q2 2018Q3 2019Q1 2019Q4 2020Q1 2021Q4 2022Q1 2022Q3 2022Q4 2023Q2 2023Q3 2024Q2 2024Q3 2025Q1 2025Q3 2026Q2 |
| partial | 2017Q3 |

The quarters nearest a threshold, all sideways: **2022Q4 -14.83%**, **2026Q2 -14.15%**,
**2019Q4 -13.21%**, **2024Q2 -11.94%** and 2025Q1 -11.78%. The nearest to a rising threshold is 2020Q3 at
+17.9%, which is rising. **2022Q4 is 0.17 points from the falling line**: it opened at 19,422.61
and closed at 16,542.40 against a bound of 19,422.61 x 0.85 = 16,509.2185, so it is sideways by
33.18 USDT, and a rounded quotient could not have moved it. No other quarter is within a point of
a line.

### Against the predictions (`F:\trading bot\scratch\p107\predictions_c4_labels.txt`)

SHA-256 `c000d278df4f834b92889d1cb560d2d9b15e97e9516a3074e094be89157f9c1e`, written before the
script first ran. **The four counts held to the point predictions** (37 quarters, 1 partial,
rising 13, falling 7, sideways 16), and so did the behaviour (second write exit 2, `--check` equal).
**One detail was wrong** (`M5m-197`): the prediction expected 2024Q2 near the -15% line from
memory of prices; it is -11.94%. The prediction gave no labels for 2025Q4 to 2026Q3, which turned
out falling, falling, sideways, rising.

### Digests of the C4 instruments and outputs (SHA-256)

| file | sha256 |
|---|---|
| `predictions_c4_labels.txt` (under `F:\trading bot\scratch\p107\`) | `c000d278df4f834b92889d1cb560d2d9b15e97e9516a3074e094be89157f9c1e` |
| `predictions_c4_gate.txt` | `0eba899057b4a7b69892a8ce2a8bdaff9c36b459e11093d538d1cde6b87e704d` |
| `regime_run1.txt` | `01b73765efd48b74c2e445abd90d430a49e0370948069238722675272a3084f6` |
