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

> **ANNOTATED AT M5m P109 (C3): `sma` NO LONGER USES `values.rolling(period)`.** It is the
> window-only mean of R-AQ (`indicators.sma`), which also counts rows, not time, so the finding
> stands: its window still spans a gap. Only the bullet's mechanism changed. `ema`, `rsi` and `atr`
> are unchanged.

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

> **ANNOTATED AT M5m P109 (C3): THIS BULLET'S TWO CLAIMS ARE NO LONGER TRUE.** *"Nothing was
> changed ... and the question is the owner's"*: the owner ruled it (R-AQ, R-AX) and `sma` is now
> window-only, so the strategy's recomputation is identical at every buffer length. And the
> mechanism's *"the tie is mathematical and the floats differ in the last digit"* was corrected
> at P108 C1 (section 36): it is the DECIMAL closes that tie, the float64 closes' averages being
> 9.09e-15 apart. **What survives:** the probe's measurements as taken (`rolling` at 1,000, 831
> and 543 rows) and the cause named: pandas' running sum.

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

## 35. M5m S3: the smoke backtest on the C6 code, its metrics recomputed and hand-checked (P107 C7)

Recorded at M5m P107 (C7). An observation log, so this section only adds. **One backtest was
run: the committed config, BTCUSDT 1m and ETHUSDT 5m, 2024-03-01 to 2024-04-01, from the
repository root on the editable development install, as R-AE authorised for S2 and P107's C7
extends to a fresh run on the C6 code.** It is a check of the machine and is **not evidence for
S4 to S7** (R-AH): the record's own verdict is `refused`. The P106 runs of section 32 predate the
equity loop, which is why this run was needed.

### What was run

- **Code:** `HEAD` `c5e11f1589dea0f9239eca584915ce0c87c8e956`, `git status --porcelain` empty
  before and after, `config.yaml` SHA-256
  `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0` (equal to the committed blob).
  `trading_bot.__file__` resolved to this checkout's `src` before the run. The record's
  `provenance` names `install_kind=editable`, `code_commit=unknown`, `verdict=refused`.
- **Command:** `python -m trading_bot backtest --start 2024-03-01 --end 2024-04-01`, stdout to
  `smoke_c7.out`. **Exit status 0.** pid 2020; Windows `2026-10-09T17:53:31Z` to `17:55:58Z`; the
  record's clock `17:53:32.675Z` to `17:55:58.097Z`, **`wall_seconds` 145.421**.
- **Record:** `data/backtests/20261009T175332605801Z-5350070f7a9e/` with `run.json` (schema 3,
  14,978 bytes), `trades.csv` (239,657 bytes) and **`backtest.log` (751,361 bytes), the run's own
  log (R-AG)**. `data/*` is ignored by git, so the digests below are the record.

### Result

| fact | this run | section 32 (P106) |
|---|---|---|
| exit status / `problems` / `error_log_records.count` / handler failures | 0 / none / 0 / 0 | 0 / none / 0 / 0 |
| bars served, BTCUSDT 1m / ETHUSDT 5m | 44,640 / 8,928 | same |
| BUY entries queued / filled / refused / expired / unaffordable | 628 / 628 / 0 / 0 / 0 | same |
| CLOSE queued / refused by risk | 610 / 17 | same |
| trades (BTCUSDT / ETHUSDT); exits close / stop_loss / take_profit | 626 (522 / 104); 610 / 8 / 8 | same |
| entry fees / exit fees (USDT) | 122.494434554672850 / 122.354975506698450 | same |
| realised total / final free quote (USDT) | -384.308458035771300 / 9231.414198714929200 | same |
| cash identity residual; fee residual | `0E-21`; `0E-21` | `0E-21`; (none) |
| trade-log SHA-256 | `5350070f7a9eeea27f8f8e63ddc765110a9b66bd3e06881e9dfdd657c313ba36` | identical |
| `trades.csv` SHA-256 | `bd1d6991e9b11a63fa5e980f8724dd19b89603a37a24b540ea3f208d1ac630a3` | identical |
| `run.json` SHA-256 | `7c98ee33dbb75335c317b99f394e8b6c39d7bb9d455f635c08b707c1a06d7ad1` | differs (schema 3) |
| `wall_seconds` | **145.421** (2,715 us a bar) | 118.8 / 118.3 (2,218 / 2,209) |

**The equity loop moved no decision.** The trade log and `trades.csv` are byte-equal to P106's,
so the probe that samples the portfolio after every bar changed no fill, no entry and no exit.

**The new blocks.** `equity.samples` 53,568, one per bar of either pair; `initial` 10000.0 and
`final` 9615.612479714929200 (the free quote 9231.414198714929200 plus the two open positions at
their last closes, 384.198281, both open since 2024-03-31T22:07 and 23:40); `regime_labels` is
`6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72`, equal to the committed file's
digest. The metrics, **a check of the machine and not a statement about the strategy**: 113 wins
and 513 losses, win rate 0.18051, net P&L -384.308458035771300 (equal to the results block's
`realised_total`), gross P&L -139.459048, fees paid 244.849410, profit factor 0.28540 net and
0.60117 gross, per-trade return mean -0.31330% with a 95% interval of [-0.36804%, -0.25855%] on
n = 626, mean holding 4,405.8 s and median 2,640 s, exposure 0.75712, **maximum drawdown 0.038566
(385.684 from 10000.678 at 2024-03-01T00:30 to 9614.994 at 2024-03-31T22:19)**, 31 daily returns,
Sharpe -28.968 and Sortino -16.150. All 626 trades are in `rising` (2024Q1), none in the other
buckets. The Sharpe's magnitude is an artefact of 31 near-identical negative days.

### The recomputation, exactly (the C7 requirement)

`analyse_c7.py` (a scratchpad script) read `trades.csv` with `load_trades_csv`, the record's
`equity` block with `EquitySummary.from_record`, and the committed `docs/REGIME_LABELS.json` with
`RegimeTable.from_file`, ran `compute_metrics`, and compared the whole `to_record()` with the
record's `metrics` block: **equal, key for key, every string.** The label digest the table read
equals the one the record names.

### The hand check of three figures (arithmetic that does not call `metrics.py`)

| figure | by hand, from `trades.csv` and the `equity` block | the record |
|---|---|---|
| net P&L | the sum of the 626 `realised` column values: **-384.308458035771300** | `-384.308458035771300000000` |
| win rate and net profit factor | 113 rows above zero, 513 below, none at zero; 113 / 626 = **0.18051118...**; sum of wins over the absolute sum of losses = **0.28539630...** | `0.1805111821086261980830670927`, `0.2853963036967771668025737949` |
| maximum drawdown | (10000.677902199 - 9614.994026143412200) / 10000.677902199 = **0.0385657732...**, the amount 385.683876055587800 | `0.03856577322331135819122204939` and `385.683876055587800000000` |

A fourth, the daily Sharpe, was also recomputed by hand from the 31 daily closes (carried
forward, sample sd, times the square root of 365) and agrees to every digit: **-28.96786294...**.
The drawdown check reads its pair from the record's own `equity` block, so it verifies the
arithmetic and not the pair's identity; what bounds the pair from outside is that the drawdown
0.038566 is not below the closed-trade loss on the initial balance, 384.308 / 10000 = 0.038431,
which it must not be when final equity is below the initial.

### Against the predictions (`F:\trading bot\scratch\p107\predictions_c7.txt`)

SHA-256 `0b0a417d0f4a2adfeb346fe4b3e0539c643053a00586e5adfbe9ced4f24a56a0`, **amended before the
run** (the file before the amendment had SHA-256
`fe239e9ff8c2e440ec7850a0dff4a35d896f8efd7317a22e18ec6e9c9912e9b8`). The amendment corrected item 1:
`main` logs the boot line at ERROR when the verdict is refused, so `backtest.log` was predicted to
hold exactly one ERROR record, the `boot_provenance` line, and it does (1 ERROR record, that line;
`error_log_records.count` 0, as the tally starts after it). **Eleven of thirteen items held**, among
them the digests, every count, the label bucket, the recomputation, the hand check and the
unchanged bot log (`logs/trading_bot.log` 6,604,109 bytes with SHA-256
`8b460ba1223f1f4e6a80a72a5f861e36eb3d4dc2de609e404e716d9de69e5e41`, equal before and after).
**Two missed, and both are recorded rather than adjusted:** item 5 predicted 118.8 s to 137 s and
the run took **145.4 s** (+22.4%); item 10 predicted a maximum drawdown of 0.04 to 0.06 and it is
**0.038566**, just under the band (the prediction's own floor, 0.0384, held).

### The runtime, diagnosed as far as it can be without another run (`M5m-216`)

The equity probe cannot account for it. A microbenchmark (`bench_probe_c7.py`, no run) of one
`_EquityProbe` call with two positions open took 9.0 us, 53,568 calls in 0.48 s, 0.3% of the
run. The remaining 26 s a run over P106's is **not explained**: the candidates are the file
handler C0 added (751,361 bytes written), the rest of C1 to C6, and the machine, and one run
cannot separate them. The console sink still carries the whole log (1,114,317 bytes on stdout, as
P106's 1,114,155).

> **ANNOTATED AT M5m P109 (C4): THE CONSOLE NO LONGER CARRIES THE WHOLE LOG.** R-AS: during a backtest
> the console carries WARNING and above and the run directory's `backtest.log` carries everything;
> this run's console output was 1,114,317 bytes, and from C4 a run's is its warnings and one result
> line. **What survives:** this section's measurements, which are of the run as it was made, and the
> runtime question, which a quieter console may or may not touch and which nothing here measures.

### Digests of the C7 instruments and outputs (SHA-256)

| file | sha256 |
|---|---|
| `predictions_c7.txt` (under `F:\trading bot\scratch\p107\`), after the amendment | `0b0a417d0f4a2adfeb346fe4b3e0539c643053a00586e5adfbe9ced4f24a56a0` |
| `smoke_c7.out` (1,114,317 bytes) | `3300af12b0700746433de6db0c98f61741da67c7f85dbe964ec4755b834048ae` |
| `analyse_c7.out` (5,604 bytes) | `4ed8d8575a27c8f657e17d442722fd8e0931ecb4823c888811fca2c24271c14e` |
| `analyse_c7.py` (the scratchpad) | `231b7a5b16d72cf3086b9730fb0e8fc47ec02d98c30fb1d20ac2d8b1388fc22c` |
| `bench_probe_c7.out` | `ce843e4b2d5e89a12088e72b85cd79ab09f1459a02a3af319c1db0be950f4302` |
| `bench_probe_c7.py` (the scratchpad) | `f47e0826d29b8197ea22e9e20b6d5ea24aae3944471f56aa0f38724cbd140bb1` |
| `run.json` of the run | `7c98ee33dbb75335c317b99f394e8b6c39d7bb9d455f635c08b707c1a06d7ad1` |
| `backtest.log` of the run (751,361 bytes) | `639f2a82d2f9bcc6f2322d1f362efc172febf193bd2f3b5c32745910f1f35a94` |

## 36. M5m S4: P108 Phase 1's measurements -- the account, the snapshot, the retention, the klines weight, the tie and the indicators

Recorded at M5m P109 (C1). An observation log, so this section only adds. P108 was a Phase 1: it
changed nothing in the tree and launched nothing, and everything below was read on
**2026-10-09** with `HEAD` at `df3dd214353ac8dd4f66b3da19fe0f06a43687fd` (equal to `origin/main`).
Predictions: `F:\trading bot\scratch\p108\predictions_p108_halts_and_partA.txt`, SHA-256
`977ec0bbcf60225de2e72d081b279ace7266a03243224fa711f8dce67143c70d`, written before any of it ran.
**All six halts held**: HEAD as predicted; `origin/main` equal to HEAD with 0 ahead (the "or" branch of
the prediction: the owner had pushed); the tree clean; ping `200` at `2026-10-09T18:07:21Z`; the gate
173 / 92 / 3150 passed, 1 skipped in `gate_h5.txt` (SHA-256
`3227ed73792e2cd4d3139cc6667966af8835e075fdddd2a52898369dc8354476`); the findings audit M5m-001 to
M5m-219, gapless, blockless `[934eb45]`.

### A1 -- the active deployment clone and its store

`F:\trading bot\deploy\51a5f2711a09` is the only directory under `deploy` with a runnable
`.venv\Scripts\python.exe`; its `HEAD` is `51a5f2711a0984697a915b192bb481f65949567f` with a clean tree.
`data/state.json` (2,010 bytes, SHA-256 `1f91fc4335a3d62899ae9ba430aa6abd41a6f4468a0605ba5b252143f7677396`,
schema 2) holds **`"positions": []` and `"pending": []`**: no position record, no pending placement and
no held record. Its ledger is 21 days of `daily_history` (2026-09-10 to 2026-10-04), today's ledger
(`pnl_date` 2026-10-05, `realised_pnl` 3.95683720, 3 trades) and `lifetime_realised` -432.76307650. The
last run ended `2026-10-05T05:07:02Z` with *"Received SIGINT; shutting down gracefully"* and
`engine_stopped clean_shutdown=True` at `05:07:03Z`. `logs/.bot.lock` holds the text `27224`, a stale
pid, which does not matter: the lock is an OS-level file lock. **Predicted zero records, and it held.**
After a venue reset a record would meet the first row of `restoration.py`'s decision table, *"no list
carries our id"*, and refuse the boot; there is none, so no release step is needed.

### A2 -- the account (`scripts/check_testnet.py`, read-only, from that clone)

`a2_check_testnet.txt` (2,519 bytes, SHA-256
`0710776a276789144580e1437edbbb938cb50304cb29ae84b275151889478ab8`), `2026-10-09T18:11:29Z`:
**517 assets** with a non-zero balance; **BTC free 1.00000000, ETH free 1.00000000, USDT free
10000.00000000**; BTCUSDT last 82,702.01, ETHUSDT last 2,487.92. **Both holdings are reported
*"BLOCKS entries"*** (82,702 and 2,487.92 against `min_notional` 5), so a bot started on this account
dispatches nothing under `RefusalStage.UNMANAGED_HOLDING`. **0 open orders** on either symbol and
**0 order lists** on the account; the store names none, so none of its lists exists at the venue.
Equity counts the holdings, so it is about 95,190 with or without the clearing (R-AV).

### A3 -- `exchangeInfo`, Testnet, against the P105 C3 snapshot

Two keyless GETs, `2026-10-09T18:12:29Z`. Every one of the eleven filters of BTCUSDT and ETHUSDT equals
the stored snapshot's, and so does every non-filter field and every top-level field: **no difference**.
The whole-file digests differ only through `serverTime` (04:37:33 on 10-08 against 18:12:29 on 10-09):
BTCUSDT `d7e7a91e4689a300de60aa28a383723826f624e1fd15b4fe626a41504fb16cd9` now against
`40e24c66110ba645ef49ca595618321fdbe2a36f9eab9638eea564dd8b797dc7` stored (both 2,239 bytes); ETHUSDT
`4959f3e25caccc73206c7c105add2ba34efffb48c7b465f23ffe741226d50762` against
`87e5095e0e177267d7fe039b8ce1925c8e07903a0f64211c2b948f82705777cc` (both 2,240 bytes). The band is
still **1.2 / 0.5 / 2 / 0.8**. The response carries `rateLimits`: `REQUEST_WEIGHT` 6000 a minute.

### A4 -- Testnet kline retention, two readings an hour apart

| reading | server time (UTC) | earliest 1m open, BTCUSDT and ETHUSDT | earliest 5m open |
|---|---|---|---|
| 1 | 2026-10-09T18:12:27Z | 2026-10-07T10:32:00Z | 2026-10-07T10:30:00Z |
| 2 | 2026-10-09T19:13:06Z | 2026-10-07T10:32:00Z | 2026-10-07T10:30:00Z |

Sixty minutes and 39 seconds apart; **the window did not roll**, and the earliest bar is the one S0f
(section 33) read. Predicted for both, and held. History therefore begins at the venue's reset and is
not a rolling window of a few days; REASONED, from two readings.

### B1 -- the klines request weight, from the `x-mbx-used-weight-1m` header

`ping` 1; `klines limit=1` 2; `klines limit=1000` 2; `klines limit=1000&startTime=0` 2. **Weight 2
whatever the limit**, 164,246 bytes for 1000 one-minute rows.

### C1 -- the M5m-184 bar, reproduced (`c1_tie.out`)

ETHUSDT 5m, the bar opening `2024-03-05T03:30:00Z`, the repository's own `sma`, `crossed_below` and
`last_two` over the stored closes, the buffer the last N bars up to that bar:

| N | 1000 | 900 | 831 | 700 | 543 | 400 | 300 | 200 | 120 | 80 | 60 | 52 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `crossed_below` | True | True | False | True | False | True | False | True | False | False | True | True |

The slow SMA at the bar is `3627.7740000000003` or `3627.7739999999994`, and the fast `3627.774` or
`3627.7740000000003`, according to N. **The averages are not equal in float64 either**: summed exactly
over the float64 closes, fast minus slow is -9.09e-15 at the bar, so it is the DECIMAL closes that tie
(both 3627.774). The cause is pandas' `rolling().mean()`, a running sum that depends on what preceded
the window.

### C2 -- the window-only mean (`c2_fix.out`, `c2b_signals.out`, `c2c_nocopy.out`)

Per (series, period): the number of end bars, of 60 tried against 12 buffer lengths, whose last value
is not bitwise the same across the lengths. **The current `sma`: 44 / 50 (full-float walk), 48 / 44
(0.01-tick walk), 52 / 51 (plateaus) and 40 / 44 (25 NaNs), for periods 20 / 50. A window-only mean
(`sliding_window_view`, made C-contiguous, summed along each window, divided by the period): 0 in
all 480 cells**, and bitwise equal to the whole-series value in 1,200 further checks. `math.fsum` per
window and a last-`period+1`-rows slice were also 0. The contiguous copy is not load-bearing on
numpy 2.5.1: four variants (copy or view, sum or mean) gave 0 buffer-dependent ends in 800 cases and
identical values. Cost, `sma(20)` and `sma(50)` over 1,000 rows, median microseconds: current 283.9,
window-only 138.1, tail slice 381.7, `fsum` 6,278.6. **Over March 2024** (44,640 BTCUSDT 1m bars and
8,928 ETHUSDT 5m bars, the buffer the last 1000 closes): the window-only mean changes **0** decisions
on BTCUSDT and **1** on ETHUSDT, the `CLOSE` at `03:30` (current: 105 BUY and 105 CLOSE; window-only:
105 and 104). A 1e-12 relative tie tolerance would add one `BUY` at `03:35`; it is not adopted (R-AX).

### C3 -- the buffer start's effect on every indicator (`c3_census.out`)

ETHUSDT 5m, March 2024, 8,928 end bars, buffers of 1000, 831, 543 and 500 rows:

| indicator | bars whose value differs | worst relative difference |
|---|---|---|
| `sma(20)`, `sma(50)` (rolling) | 4,407, 5,309 | 2.8e-16, 2.9e-16 |
| `ema(20)` | 0 | 0 |
| `macd` line, signal | 0, 118 | 0, 2.3e-12 |
| `rsi(14)` | 2,194 | 8.9e-16 |
| `atr(14)` | 1,603 | 8.4e-16 |
| `bollinger_bands` upper | 8,928 | 4.8e-13 |

`stop = close - 2 x ATR(14)`, rounded to the 0.01 tick, differed in **0 of 8,928 bars** between any two
of the buffer lengths. `(13/14)^500` is 8.1e-17. With short buffers ATR does move: 3.7e-2 at 60 rows,
2.1e-3 at 100, 1.6e-6 at 200 and 1.5e-9 at 300, against `(13/14)^(n-14)`.

### Digests of the P108 instruments and outputs (SHA-256)

| file (under `F:\trading bot\scratch\p108\` unless a scripts row) | sha256 |
|---|---|
| `predictions_p108_halts_and_partA.txt` | `977ec0bbcf60225de2e72d081b279ace7266a03243224fa711f8dce67143c70d` |
| `gate_h5.txt` | `3227ed73792e2cd4d3139cc6667966af8835e075fdddd2a52898369dc8354476` |
| `a2_check_testnet.txt` | `0710776a276789144580e1437edbbb938cb50304cb29ae84b275151889478ab8` |
| `a3_testnet_BTCUSDT.json` | `d7e7a91e4689a300de60aa28a383723826f624e1fd15b4fe626a41504fb16cd9` |
| `a3_testnet_ETHUSDT.json` | `4959f3e25caccc73206c7c105add2ba34efffb48c7b465f23ffe741226d50762` |
| `a4_reading1.json` | `fd82c45b61d8087e5d1ffcc7c7384ba8b83f36ca45801ce205351eef75c2fe00` |
| `a4_reading2.json` | `ada3f304f0e660bf830460e8aab48bdabcccbd25790971340e92c424a4978ec9` |
| `b1_weight.out` | `0481dc67d069d5f7b5f966ff0d1c86ee926ebfa08b7d7ac8143326c1bdfc4195` |
| `c1_tie.out` | `fa0e8175032f3700431db4a29da2989db4854a2acd20b28a26297f5801718388` |
| `c2_fix.out` | `e9f1d7743b82fb2f8f022b34fa1ac017040613e0fcc56855187d55852b8d12b6` |
| `c2b_signals.out` | `1e41bebaff561a2e8677c12b94972be27599cfb20cfe58d60132f8a428fcc937` |
| `c2c_nocopy.out` | `4f01e03735dad05ad8a9a166e9b2b9f9e158c8d5d5084fea85a4d0399661e90d` |
| `c3_census.out` | `481b68ec05cf4fe3b530de5b80e3f8a6276f503483910b31e519a028ee6b838c` |
| `draft_S4_PREREGISTRATION.md` (a draft; the committed file will differ where R-AY to R-BB rule) | `538413c19494f1a5bef4cc0456444b57c0104b24da0d9eab19a27afef1f53cfd` |
| `draft_launch_checklist.ps1.txt` | `877d21dee26b4c717dbc1769b09a97dfa356103470c30edbdca9d9b1733e4f43` |
| `p108_a3_a4.py` (the scratchpad; a comment was edited after reading 1) | `3e7433e41ee9056d63b4ff973c5b3c7b0ebeeb3ac4c3bdddea3a813cefa21d17` |
| `p108_c1_tie.py` | `b0c387992ae81f228bb86b08f10517d53f43171bbadf569876b237edeb4a3ed2` |
| `p108_c2_fix.py` | `b4869822efe02e006843f2c9830b847116c958e2dfc159215fa01a2ca49644d6` |
| `p108_c2b_signals.py` | `630f5e2c6607d72c86ae6c8ac9af6d0a3670026b979adf5daa249746d5594263` |
| `p108_c2c_nocopy.py` | `776ef391a7ff4dfb87b8c70e430726d6173a3c3fd0989eae5f0c0b5581792c15` |
| `p108_c3_census.py` | `b2047dc9327735ab456124a7fded29d279f059721ad8ae1d18a8f923f5f7cd05` |
| `p108_weight.py` | `e60733a2a5f4fa217276b21cd095cff90df403552df21849efae253ab837f079` |

Process slips in P108, recorded: two empty shell heredocs (no content, nothing written), and one
duplicate keyless klines pass at `2026-10-09T19:13:04Z` whose result file was deleted.

## 37. M5m S4: the Testnet kline recorder's first run (P109 C2b, R-AN)

Recorded at M5m P109 (C2b). An observation log, so this section only adds. **`scripts/record_testnet_klines.py`
was run once against Testnet, then once more at once.** It is a keyless, read-only capture, not the bot: no key
was read, no account touched, and it ran from the development tree on its editable install, so the entry names
`commit` `unknown`. It wrote `data/historical_testnet/` (ignored by git), which is the first real capture of the
history Testnet holds since its reset, and a backup of it against the next reset. **It is not the S4 store**:
the owner's recorder clone (R-AW) keeps its own, and may start from a byte-equal copy of this one.

### What was run

- **Code:** the script as it stood before its commit, SHA-256
  `872d5ab9e0b58b44cca9c38a68ee737b0acee6f600bbf81a2c30895dee88e16e`, and the scheduler definition
  `scripts/recorder_task.xml`, `8094cc8ef516e0cfcb9035f07aef7dd9fd6927b5482793a8ae00bd130f742574`; both were
  re-hashed after the runs and are unchanged. The commit that follows holds these bytes.
- **Run 1:** `2026-10-09T19:46:00Z` to `19:46:05Z` (5 s), server time `1791575161247` ms, **exit 0**, output in
  `recorder_run1.txt`. **Run 2:** `19:46:26Z`, exit 0, `recorder_run2.txt`.
- **Requests, run 1:** one `/api/v3/time` and ten `/api/v3/klines` pages (the 1m series four pages each, the 5m
  one), 11 GETs and a request weight of 21 against the venue's 6000 a minute (M5m-224); no overlap request,
  because the store was empty.

### Result

| series | bars stored | first open (UTC) | last open (UTC) | pages | forming skipped | gaps | month file SHA-256 |
|---|---|---|---|---|---|---|---|
| BTCUSDT 1m | 3,434 | 2026-10-07T10:32 | 2026-10-09T19:45 | 4 (1000, 1000, 1000, 434) | 0 | 0 | `f26e669fd3b0592e4e2e6bb62d5421d0839d125dcbbcfac70ca06553c60881fb` |
| BTCUSDT 5m | 687 | 2026-10-07T10:30 | 2026-10-09T19:40 | 1 (688) | 1 | 0 | `3ecce7f7d5aa4e4053adf5f780ce12e100c40a84f1dd87c6f43ca0d017d16f09` |
| ETHUSDT 1m | 3,434 | 2026-10-07T10:32 | 2026-10-09T19:45 | 4 (1000, 1000, 1000, 435) | 1 | 0 | `a10ef0187e667dc777324b75a1a2d1f844d96c72345aa86eba7cfb0a17f34fee` |
| ETHUSDT 5m | 687 | 2026-10-07T10:30 | 2026-10-09T19:40 | 1 (688) | 1 | 0 | `c2995d447a19f516a875fa0b898a6013b9b95f6c984f06f5d40520913ca52fca` |

**8,242 bars, no gap, nothing quarantined and nothing registered.** The manifests' first open times are
`1791369120000` (1m) and `1791369000000` (5m). The deep check, `--verify-only` (every stored row re-validated
under the ingest rule), read **0 problems** in all four series, before and after run 2. Each series has one
`MANIFEST.jsonl` line and one `RECORDER.jsonl` event per run (`recorded`, then `nothing_new`); the manifest
digests are `ece78dba...3549` (BTCUSDT 1m), `51fec67a...3219` (BTCUSDT 5m), `4c92646b...01b4` (ETHUSDT 1m)
and `7b174e9a...96a2` (ETHUSDT 5m), each over a file that run 2 left byte-equal. **Run 2 added 0 bars** to every
series and changed no month file (the four SHA-256 above were re-derived and the `diff` was empty). A first
data row, BTCUSDT 1m: `1791369120000,83732.02000000,83732.02000000,83732.02000000,83732.02000000,0.00006000,1791369179999`;
the last stored: `1791575100000,82410.30000000,82410.30000000,82372.00000000,82372.02000000,0.03679000,1791575159999`.
The prices are Testnet's, where BTC is about 82,400 and not mainnet's.

### Against the predictions (`F:\trading bot\scratch\p109\predictions_c2b_first_run.txt`)

SHA-256 `407897805f1403d79236baa81f04d63300a6016c18ab8e8c628148f2a7d774d1`, written before the run.
**The row counts held to the bar**: 3,434 and 687 per series, 8,242 in all, from the first opens A4 read twice. So
did the page counts (4 and 1), the 11 GETs and the weight of 21, the absence of gaps and irregular bars, the
one month file and one event per series, the manifest first opens, the clean deep check, and the idempotence of
run 2 (predicted "+0 or +1": it was +0, run 2 having started in the same minute). **One detail was wrong**
(`M5m-243`): *"forming_skipped is 1 in every series"*: BTCUSDT 1m reports 0 in run 1, because at `19:46:00Z`
the venue had not yet returned the bar opening `19:46`; the other three, and all four in run 2, report 1.

### Digests of the C2b outputs (SHA-256)

| file (under `F:\trading bot\scratch\p109\`) | sha256 |
|---|---|
| `predictions_c2b_first_run.txt` | `407897805f1403d79236baa81f04d63300a6016c18ab8e8c628148f2a7d774d1` |
| `recorder_run1.txt` | `31e6d7d564246937e6c4d84afe3c3c2c619bf4ae49894e945ff0c23a39fa1e71` |
| `recorder_run2.txt` | `b34f0aee070e3810476e857701cb9bdc09273d2cf3364f75c2f4a964cc1d34d9` |

## 38. M5m S4: P110's Step 0 and C1 -- the halts, R-BB's comparison, and the survey ids re-parsed (R-BC)

Observations of 2026-10-10, taken with the working tree at `524d53a`. Scratch directory
`F:\trading bot\scratch\p110\`. Every prediction below was written to a file before the measurement it
predicts (R-T).

### The halt conditions (predictions: `predictions_halts.txt`, SHA-256 `8d6707f10e14a90304eb3fb134670b58bcc7b71cd4c38cc4fa27cddd98e2b0b8`)

| halt | predicted | observed |
|---|---|---|
| H1 `git rev-parse HEAD` | `524d53a9e1cb9bd3b09db9885faeedcea23bf418` | the same |
| H2 `origin/main`, `origin/main..HEAD` | `524d53a` and 0 if pushed, else `df3dd21` and 5 (about 60% for the first) | `524d53a9e1cb9bd3b09db9885faeedcea23bf418` and **0**: the owner has pushed |
| H3 `git status --porcelain` | empty | empty |
| H4 keyless Testnet ping | 200 | 200 at `2026-10-10T03:48:14Z`, and 200 again at `03:57:18Z` after H5 |
| H5 `scripts/check.py`, bare to a file | 180 files / 95 source files / 3273 passed, 1 skipped, exit 0 | exactly that, 499.20 s of pytest, exit 0 (`gate_h5.txt`, SHA-256 `bf7c430be93c5fc2ba254f9d9e1452d38a341fe60a78e991e239b04a86c8b660`) |
| H6 `check_findings.py milestone/M5l..HEAD M5m` | `M5m-001` to `M5m-257`, gapless, blockless `[934eb45]` | declared 257, distinct 257, no gap, no duplicate, nothing cited and not declared, blockless `[934eb45]`, exit 1 for that commit only |
| H7 `data/historical_testnet` verifies clean | clean; the owner's task has NOT run (two `RECORDER.jsonl` lines per series) | 4 series, 0 gaps, **0 problems**; two lines per series; `F:\trading bot\recorder` does not exist, so **no recorder is running and the store has not grown since `2026-10-09T19:45Z`** |

### S0a: where `M5m-250`'s ids come from

`scripts/mutation_survey.py`, `run_suite`, the nested `ids()` (before C1): `line.split(" ", 1)[1].strip()` for
every short-summary line that starts with `FAILED ` or `ERROR ` and contains `::`. **It does not truncate
anything.** It keeps everything after the word, which includes pytest's own `- <reason>` suffix, and pytest
trims that suffix to the terminal width (80 under capture) with `...`; pytest never trims the node id (and,
when the id alone fills the line, prints no reason at all). So `M5m-250`'s *"truncates a long node id at the
first ' - '"* names the wrong mechanism: **the id is whole and carries a reason**. Its consequence stands (a
predicted name can look unobserved because the row holding it has a suffix). Annotated here and not amended,
because a finding later found imprecise is annotated.

Also measured: on pytest 9.1.1 a test file outside the rootdir is printed with an EMPTY file part,
`FAILED ::test_a - assert 2 == 1`, so the harness's self-tests that run a probe in `tmp_path` get ids that
begin `::`.

### C1: the fix, failing first (`c1_failing_first.txt`, SHA-256 `dc8c04776c08dce250a18988ffa8bbe8bad5b608aa954f76569c5173e27b8ccd`)

Five new tests in `tests/unit/test_mutation_survey.py`, run BEFORE the fix: **5 failed**, the real-pytest one at
its assertion (`AssertionError: ::test_the_answer_is_one - assert 2 == 1`, the old id with its reason) and the
four pure ones with `AttributeError` (`summary_node_ids` did not exist). After the fix the file reads 19 passed
(`c1_after.txt`, `87e0f12f292e2be799a12b683ae910852c00bbbff0ab931ff24c80f99db23869`). The fix is
`summary_node_ids` and `_node_id_of`: the id ends at the first ` - ` outside square brackets.

### C1: every saved M5m survey log re-parsed (`reparse_out.txt`, SHA-256 `2b89ee7d47b44cf415c7d826cbc55f309919e33f1c103c646d0449d05a4e7a9d`)

`reparse_logs.py` (scratchpad) reads each log's mutation blocks, takes every `FAILED` line as the OLD parser
kept it, runs the NEW parser over the same text, and compares per block the verdict the log states (killed,
crashed, abstained), the line count, the distinct-id count, and the log's own `raw FAILED` figure. It asserts
that every new id is the old line cut at its own ` - `. Sixteen files were found: three under
`F:\trading bot\scratch\` and thirteen in the session scratchpad, of which `survey_s.log` is byte-equal to
`p109/survey_sma.log`, `survey_c5.log` to `p105/survey_c5.log`, and `survey_c4.log.bak` to `survey_c4.log`, and
`survey_s0.log` holds no verdict block. Twelve distinct logs hold verdicts:

| log | SHA-256 | blocks | failed lines | lines carrying a suffix | abstained | survivors | kill sets changed |
|---|---|---|---|---|---|---|---|
| `p105/survey_c5.log` (`fill_model.py`) | `607fe4e7cba4fa4fcb974ba9025ce2048fb97087cedd4157589c1f00be3d4ced` | 42 | 141 | 0 | 0 | 1 | **0** |
| `p106/survey_sim.log` (simulated executor) | `ca16f0d0c3a521edb7a0519f48e62d6c86a7dbb82a339603eff1e0c4ce53ec99` | 33 | 111 | 0 | 0 | 2 | **0** |
| `p109/survey_sma.log` (`indicators.py`) | `34da38775718866d538eef435658dd15f6e44c604d32a2056b7fe9cc0c22631d` | 15 | 120 | **11** | 0 | 4 | **0** |
| `survey_c1.log` | `79a23e368ad74fbf31e76a4f2de213a4327c39725bdcc35dfdbd03f1b0da67a4` | 39 | 222 | 0 | 0 | 0 | **0** |
| `survey_c2.log` | `855b91deebe966b81b11b894a5403ca4b019d25c2c274ddfd40faf835e57a9e6` | 19 | 107 | 0 | 0 | 0 | **0** |
| `survey_c4.log` | `59671265115163d4de5d26b765c33cb077fc6f8db0dfa4899aa977c8641dab16` | 17 | 23 | 0 | 0 | 0 | **0** |
| `survey_c5p.log` | `f4c3c39896107bae1106dc7d2419b623f0c3df5500d02a8af9544cd1d896e477` | 8 | 21 | 0 | 0 | 0 | **0** |
| `survey_hist.log` | `7b45693a50392f60750817af14b215174a6a951be82029e0d53f62f597971b40` | 29 | 124 | 0 | 0 | 0 | **0** |
| `survey_hist_run1.log` | `2c5e3da00af47ed97536c50f09733c39ab12fe715ea48cf4c99126efbbfdf6d5` | 29 | 124 | 0 | 0 | 0 | **0** |
| `survey_q2.log` | `b9097140dfc993d3ea51c2624733f9014e3114df175412de48166547dae5d281` | 30 | 98 | 0 | 0 | 2 | **0** |
| `survey_sim_rerun.log` | `04295a3bdef516efe4e62d1cfc03e1ebca181ed84c1170f41953bb079e9ddbe0` | 2 | 5 | 0 | 0 | 0 | **0** |

**No kill set and no abstention changes in any log**, as predicted (`predictions_c1.txt`, SHA-256
`45c280e57fc43f636f3b55b8514dc767fcbbb2f1d228e134b48c6753323bdd4c`). The reason is structural: a block's
kill count and its abstention are the in-process hook's and `exit_code`'s, and the parser only supplied the
printed ids and `outcome.failed`. **Only the `indicators.py` survey (P109) had any suffix, 11 lines of 120**,
and the cause is the width: pytest prints a reason only when the line leaves room for one, which it does for
the short test names in `test_indicators.py` and does not for the long ones in the other eleven logs. That
is why `M5m-250` was met in P109 and in none of the earlier surveys. The logs' own `raw FAILED` figure equals
the number of `FAILED` lines in every block.

The logs were not all of M5m's surveys: P106 C4's and C5p's specs (`spec_c4.json`, `spec_c5p.json`) have logs in
the scratchpad (`survey_c4.log`, `survey_c5p.log`, in the table), and **no log was found for any survey run
before P105**; a survey whose output was not saved cannot be re-parsed.

### S0b: R-BB's comparison, measured before any venue write (predictions: `predictions_s0b.txt`)

The configured rule, from `config.yaml` at `HEAD`: `risk.position_sizing.method: fixed_fraction`, `fraction: 0.02`,
`limits.max_position_size_percent: 20.0`. Through the real `calculate_position_size`, with the stored Testnet
`exchangeInfo` filters, **equity 95,190 (R-AV's figure; NOT read from the venue in this step, which is a
signed call)** and the last recorded closes (BTCUSDT 82,372.02, ETHUSDT 2,478.84):

| symbol | step | quantity | predicted entry notional | census of record: entries | median entry quote total | predicted / median |
|---|---|---|---|---|---|---|
| BTCUSDT | 0.00001 | 0.02311 | **1,903.6174** | 140 | **1,809.1410** (range 1,769.17 to 1,813.86) | **1.0522** |
| ETHUSDT | 0.0001 | 0.768 | **1,903.7491** | 25 | **1,809.1747** (range 1,805.55 to 1,814.07) | **1.0523** |

**Within 2x, so R-BH's halt does not fire.** The prediction held: both notionals 1,903.6 and 1,903.7 (2% of
95,190 is 1,903.80 less a remainder under one lot) and a ratio inside 0.9 to 1.3. The census of record is
`scripts/trade_census.py` on the M5k capture, SHA-256
`3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`: 165 bookings, 140 + 25 entries with a known
entry quote total. The two medians are 1,809.1, which is 2% of an equity of about 90,460 at September's prices; the
5.2% difference is the ratio of 95,190 to about 90,460 (REASONED: the September equity is inferred from the
median and is not a recorded figure), and the sizing rule is the same.

### Digests of the Step 0 and C1 outputs (SHA-256)

| file (under `F:\trading bot\scratch\p110\`) | sha256 |
|---|---|
| `predictions_halts.txt` | `8d6707f10e14a90304eb3fb134670b58bcc7b71cd4c38cc4fa27cddd98e2b0b8` |
| `gate_h5.txt` | `bf7c430be93c5fc2ba254f9d9e1452d38a341fe60a78e991e239b04a86c8b660` |
| `predictions_s0b.txt` | `b812ff43514eab76815dc13c011e552b799c13d0f5618e4a735444073e7848b1` |
| `s0b_out.txt` | `fc3a715e1042ea33581561eb74bd8f1fbdba0b08994e5b8b1e24698fd7e7eaf5` |
| `census_of_record.txt` | `4afcd91f01d1b4e4f6c57602e533a39af544efb0d6f3fe514d996c958732bfc9` |
| `predictions_c1.txt` | `45c280e57fc43f636f3b55b8514dc767fcbbb2f1d228e134b48c6753323bdd4c` |
| `c1_failing_first.txt` | `dc8c04776c08dce250a18988ffa8bbe8bad5b608aa954f76569c5173e27b8ccd` |
| `c1_after.txt` | `87e0f12f292e2be799a12b683ae910852c00bbbff0ab931ff24c80f99db23869` |
| `reparse_out.txt` | `2b89ee7d47b44cf415c7d826cbc55f309919e33f1c103c646d0449d05a4e7a9d` |

## 39. M5m S4: the mutation survey of `scripts/s4_compare.py` (P110 C4b)

Taken 2026-10-10, over the final bytes of `scripts/s4_compare.py` (SHA-256
`b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08`, 1,093 lines) and
`tests/unit/test_s4_compare.py` (SHA-256 `89c806969ed07125082c88b4703d0c8c54053ab185c904317382f7a81c7b772b`, 75 test
ids), in a detached worktree of `a18f1b4` at `F:\trading bot\scratch\p110\wt_s4`, outside the repository, with
those two files copied in and shown SHA-256-equal. The formatter had run before the first mutation and nothing was
re-laid-out after it.

**The path.** The test modules that reach the mutated module, measured by `grep -rln s4_compare` over `src`,
`scripts` and `tests`: `tests/unit/test_s4_compare.py` imports it; nothing imports it transitively;
`tests/unit/test_backtest_evidence.py` reads its source with `ast`. The survey runs those two modules (119 ids,
`PYTEST_ADDOPTS`), which is every test that can move.

**The proof of where it ran.** A session plugin recorded, for the unmutated baseline and for each of the 23
mutated runs, where `trading_bot`, `s4_compare`, `tests` and the working directory resolved: 23 rows, 0 outside the
worktree (`import_proof_s4.jsonl`). The baseline read **119 passed** (`baseline_s4.txt`). All 23 restores were
verified by byte identity, and the worktree was removed afterwards (`git worktree list` shows the main worktree only).

**The result against the prediction** (`predictions_survey_s4.txt`, SHA-256
`01e02b26d5a8c54e388b07dca2c498f66509a66ac985bda5b600d60639d14711`, written after the tests existed and before the
survey ran): 23 mutations, 42 kills predicted and 50 observed, **no predicted kill missing**, 0 crashes, 0
abstentions of a mutation. Twenty-two mutations killed exactly the tests predicted. **S24** (a one-minute timeframe
of six seconds) was predicted as a lower bound of 2 and killed 10: the extra 8 are the series checks and the
`diagnose` tests that build a real store (`test_a_complete_series_has_no_gap`,
`test_a_live_entry_the_backtest_never_signalled_on_a_tie_is_a_tie`,
`test_a_recorded_close_that_differs_from_the_live_reference_outranks_a_tie`,
`test_a_signal_nothing_explains_is_unexplained_and_says_why`, `test_a_tie_at_the_bar_before_the_signal_bar_counts`,
`test_averages_that_differ_at_both_bars_are_no_tie`, `test_equal_exact_averages_at_the_signal_bar_are_a_tie`,
`test_the_recorded_close_is_the_signal_bars_and_a_missing_bar_has_none`), a reach error in the direction the rule
records and does not halt on.

**Two weaknesses the survey found BEFORE running, by the prediction exercise, and fixed in the tests**
(`M5m-275`): the return-definition test summed a +1% and a -1% backtest return to a mean of zero, which a return
left as a fraction also gives, so a mutation removing the x 100 would have survived it (its second row is now over
150, mean -0.5); and nothing pinned the backtest window's upper bound or a window of no length, so two mutations
would have survived (`test_backtest_entries_outside_the_window_are_dropped_at_both_ends` and
`test_a_window_with_no_length_is_refused_too` were added). **Declared abstentions that are limits and not defects:**
the census test `test_the_real_s4_consumer_is_scanned_names_the_record_and_calls_the_door` cannot tell the two
doors apart (removing either leaves the other's call), and a mutation of one denominator is not seen by the report
test whose two counts are equal.

| file (under `F:\trading bot\scratch\p110\`) | sha256 |
|---|---|
| `predictions_survey_s4.txt` | `01e02b26d5a8c54e388b07dca2c498f66509a66ac985bda5b600d60639d14711` |
| `spec_s4.json` | `e593c60643e0f0f5123f76dd0f5bbeeae634280868f6aca66a0bcdda943cb855` |
| `pred_s4.json` | `8af90a5be1597888f475abde03f446d5fcd92e3bf33e71af697aeab34cd36ba9` |
| `baseline_s4.txt` | `e4cadee7e2588a0f9110b15bb08a22ea83a0dc2f3a2869443d24b839aacaf316` |
| `survey_s4.log` | `aed69053dc1017f7bd6ed9fd5b0a411f647665710abb83916f815c6301392c0c` |
| `compare_s4_out.txt` | `05043b08324de6e0180d5308ef4de46afdce15e65771565a8a996f3908f39cd3` |
| `import_proof_s4.jsonl` | `82f84b39b005b857223fbe8800f622a4561ccdf18ecb997c2f8d24a9174472f1` |

## 40. M5m S4: the Testnet clearing of R-AV, and the account before and after (P110 C5)

The owner's R-AV, verbatim: *"Clearing the Testnet BTC and ETH holdings with scripts/clear_testnet_holdings.py is
authorised once, in P110, before the pre-registration commit. Equity is about 95,190 with or without it, because
pre-existing holdings count toward equity; the clearing only unblocks entries."* R-BH made it conditional on R-BB's
comparison being within 2x, which section 38 measured first (1.0522 and 1.0523). Predictions:
`predictions_c5.txt`, SHA-256 `7334425b17094117564adccc64605ea496c572890a925baa64be68c923a08fe3`, written before any
venue call. Every call below was made from the active deployment clone `F:\trading bot\deploy\51a5f2711a09` (commit
`51a5f27`, its own venv, the Testnet key slots only), after a process listing showed no python process and exactly one
clone holding a venv.

| step | call | UTC | result |
|---|---|---|---|
| 1 | `scripts/check_testnet.py --symbol BTCUSDT --candidates BTCUSDT,ETHUSDT` (reads only) | before 04:45 | `ping: OK`; 517 assets with a balance; **BTC free 1.00000000, ETH free 1.00000000, USDT free 10000.00000000**, none locked; BTCUSDT last 82,676.00 and ETHUSDT last 2,494.92; both holdings `BLOCKS entries`; 0 open orders; 0 order lists |
| 2 | `scripts/clear_testnet_holdings.py --symbol BTCUSDT --symbol ETHUSDT` (dry run: `create_test_order`, places nothing) | before 04:45:53 | both sells validated at the venue, remainder 0 |
| 3 | the same with `--execute` (**the one venue write**) | 04:45:53 to 04:45:59 | `SOLD: status=FILLED executedQty=1.00000000 orderId=1066790` (BTCUSDT) and `orderId=946252` (ETHUSDT); balances after BTC 0, ETH 0 |
| 4 | `scripts/check_testnet.py` again | 04:46:19 | **BTC 0, ETH 0, USDT free 95170.91000000**, none locked; both holdings `DUST (does not block)`; 0 open orders; 0 order lists |

**Against the prediction.** The after-state matched: both holdings below one lot (they are zero), two filled orders, free
USDT about 95,190 within 300 (it is **95,170.91**, 19.09 below the owner's figure). **One figure was wrong**: the
prediction put USDT free before the clearing at about 10,300 to 10,400, from the equity less the two holdings priced at
the boot snapshot's marks; it was **exactly 10,000.00**. The account is a fresh Testnet reset (10,000 USDT, 1 BTC,
1 ETH and hundreds of faucet assets), so R-AV's "about 95,190" was 10,000 + 82,676 + 2,494.92 = 95,170.92 at the
clearing's marks, and the cleared USDT is **95,170.91**: the two market sells took the balance from 10,000.00 by
85,170.91, a figure to the cent for 1.0 BTC and 1.0 ETH, which is what a fee of zero gives (`M5m-281`; REASONED,
because the sells' own fills and commissions were not read in this step, only the balances before and after).

**What this fixes.** `config.s4.yaml`'s `initial_balance` is `95170.91` from this commit (it read `95190.0`, S0b's
figure), the live account's free USDT at the start of the run if nothing trades before it. Its SHA-256 is
`0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594`. R-BB's comparison recomputed through the real sizer at
95,170.91 (`s0b_post_clear.txt`): at the recorded closes BTCUSDT 1,902.7937 and ETHUSDT 1,903.2534, at the venue's last
prices 1,903.2015 and 1,903.3745; ratios to the census of record's medians **1.0518 to 1.0521**, within 2x.

**The Testnet snapshots were copied beside the recorded klines**, byte for byte, into
`data/historical_testnet/_exchange_info/testnet/`: `BTCUSDT.json` `40e24c66...97dc7`, `ETHUSDT.json` `87e5095e...777cc`
and their `.sha256` files (`d1bdd4fb...9e29` and `809d70aa...1388`), the four shown equal to the P105 originals by
`sha256sum`, and `scripts/record_testnet_klines.py --verify-only` still read 0 problems in all four series afterwards.

**A smoke backtest of `config.s4.yaml`**, made once from the development tree over 2026-10-08 (the day with a full
day of recorded bars), only to show the wiring: record `data/backtests/20261010T044654815300Z-5ef7d3a2370c`, `run.json`
SHA-256 `50fe54101abf8e93ce07ca95d8e138133310576361f1a7027b157809d596ffd6`, `trades.csv`
`e5f146b7de8efc27fd139567e436d15834f3ad29613d4fe1eb6b57be5375c6f1`. It read `exchange_info` environment `testnet`
with the two snapshot digests above, fee 0, `initial_balance` 95190.0 (the value before this commit), 19 trades, 1,440
BTCUSDT 1m bars and 288 ETHUSDT 5m bars served, no problem, and `evidence_eligible` **false** with verdict `refused` (an
editable install: a development tree is never evidence). **It is not evidence for anything and decides nothing**;
19 trades in a day against the census of record's 7.86 booked a day is a difference of regime, window and tree that
this run cannot attribute.

| file (under `F:\trading bot\scratch\p110\`) | sha256 |
|---|---|
| `predictions_c5.txt` | `7334425b17094117564adccc64605ea496c572890a925baa64be68c923a08fe3` |
| `c5_before_check_testnet.txt` | `91f369b5112f549a187cdeff162a2c76fd7f766fae06e8c3746d0de309446a60` |
| `c5_dry_run.txt` | `555d4a9115fd22bd4aaa346bc7153b10bc07b9fa0c49c391a24f27775d45de74` |
| `c5_execute.txt` | `b7d0955744ce48e871c64c5ec7e697199aeedd5bf2b5f118f5e5e19096fa7865` |
| `c5_after_check_testnet.txt` | `d38652b01ca6008e2c65db932df773ee4552e44f3fc670ebd4a55a5b28edf1cc` |
| `s0b_post_clear.txt` | `366a725ecc414cb577c885161451819bd5a8840d84ddc37d03454deadedb71b9` |

## 41. M5m S4: the pre-registration, as committed (P110 C6)

`docs/S4_PREREGISTRATION.md`, 155 lines, SHA-256 `49e4fdbba55a5f407d8db130ebdc6cf68fc13813a101ab7849e4740050c6566f`
in the tree this commit leaves. It states what R-AO, R-AY, R-AZ, R-BA and R-BB require and nothing the run can change.
**The inputs it freezes, by digest, as read when it was written:**

| input | SHA-256 |
|---|---|
| `config.yaml` | `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0` |
| `config.s4.yaml` | `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594` |
| `scripts/s4_compare.py` | `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08` |
| `scripts/trade_census.py` | `926bdd4674d7fe9fa418fb5e8b67f3d089012255ba8f478492a043fbbe35d9bb` |
| Testnet `BTCUSDT.json` (exchangeInfo) | `40e24c66110ba645ef49ca595618321fdbe2a36f9eab9638eea564dd8b797dc7` |
| Testnet `ETHUSDT.json` (exchangeInfo) | `87e5095e0e177267d7fe039b8ce1925c8e07903a0f64211c2b948f82705777cc` |
| `docs/REGIME_LABELS.json` | `6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72` |
| the active clone's `data/state.json` (schema 2, 0 positions, 0 pending) | `1f91fc4335a3d62899ae9ba430aa6abd41a6f4468a0605ba5b252143f7677396` |
| the census of record's capture (`trading_bot.m5k-close-20260925T182818Z.log`) | `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528` |

**The seven lines the owner may overrule before the push**, each marked `CHOSEN` in the file: the comparison window
`[W, M)` with `W` the first UTC midnight at or after `T0`; `window-edge` as a cause beyond P108's closed list; `T0` as the
first `run` boot rather than any boot (the launch checklist's `strategies` verification also logs a `boot_provenance`
line); `unexplained` reported and not gated; NOT MEASURED when a recorded gap touches more than 5% of the live entries;
the backtest starting at `W` with the balance the live run had at `T0`; and any other backtest of the window being
exploratory.

> **ANNOTATED AT P111 (section 42): the owner ratified all seven as written (R-BI).** The paragraph above is the record of
> what was open when the file was committed.

## 42. M5m S4: P111 -- the halts, the log rotation against the run's volume (R-BK), and the owner's rulings R-BI to R-BK

Recorded at P111 (C1). An observation log, so this section only adds. The rulings are quoted in `docs/NEXT_MILESTONE.md`
(the P111 C1 annotation). **`docs/S4_PREREGISTRATION.md` is in this commit unchanged**: SHA-256
`49e4fdbba55a5f407d8db130ebdc6cf68fc13813a101ab7849e4740050c6566f`, read from the working file with `sha256sum` before the
commit and from `git show HEAD:docs/S4_PREREGISTRATION.md` after it, and the commit's numstat does not list it.

### The halt conditions (predictions: `F:\trading bot\scratch\p111\predictions_halts.txt`, SHA-256 `ddb1c11de6e2c9b9ed25e716d6c2c8c9d0473ec7b72ff2267687c333cde34a94`)

| Halt | Predicted | Observed |
|---|---|---|
| H1 `git rev-parse HEAD` | `e248a736663ecca045af3a72b02e23a8361af122` | the same |
| H2 `origin/main`, `git rev-list --count origin/main..HEAD` | `e248a73` and `0` if the owner has pushed, else `524d53a` and `7` (the prediction file leaned to the second) | `e248a73` and `0`: **the owner has pushed** |
| H3 `git status --porcelain` | empty | empty |
| H4 `scripts/check.py`, bare to a file | 183 / 96 / 3371 passed, 1 skipped | the same, exit 0, 187.3 s (pytest 185.57 s); Testnet ping 200 at `2026-10-10T05:06:23Z` and at `05:09:49Z` |
| H5 `scripts/check_findings.py milestone/M5l..HEAD M5m` | `M5m-001` to `M5m-288`, gapless, blockless `[934eb45]` only | 288 declared, 288 distinct, no duplicate, no gap, cited-not-declared none, blockless `[934eb45]`; exit 1 for that commit alone, as before |
| H6 the recorder | `F:\trading bot\recorder` does not exist | it does not (`Test-Path` False); `Get-ScheduledTaskInfo -TaskName tb-recorder`: "The system cannot find the file specified"; `F:\trading bot` holds `deploy`, `files` and `scratch` |

The gate's file is `F:\trading bot\scratch\p111\gate_h4.txt`, SHA-256 `ee5e91b3a5b5142d573c8f59f478dba308933cb616088ce0821baa29418fa443`.
**The first H4 invocation measured nothing**: it was run with the system `python`, and the gate's interpreter guard refused
("this interpreter is not the one that would measure this tree"), exit 1. The same command with `.venv/Scripts/python.exe`
is the one above. The H2 fetch was `git fetch origin main`, read only.

### Step 1a: the configuration that governs the deployment clone's log

`config.yaml` at `HEAD` (SHA-256 `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`, the digest the observation run's
`boot_provenance` line recorded, section 26) lines 193 to 201:

    logging:
      level: INFO
      console: true
      file:
        enabled: true
        path: logs/trading_bot.log
        max_bytes: 10485760       # 10 MB
        backup_count: 5
        json: false               # true -> structured JSON lines

`src/trading_bot/utils/logger.py`, `setup_logging`, lines 239 to 247: `RotatingFileHandler(path, maxBytes=config.file.max_bytes,
backupCount=config.file.backup_count, encoding="utf-8")`. The rotation's total capacity is the active file and five
backups: 6 x 10,485,760 = **62,914,560 bytes**; one file holds 10,485,760. The deployment clone's `config.yaml` is the committed one (a
launch from a modified config is refused), so this is the rotation S4 runs under.

### Step 1b: the growth, MEASURED (predictions: `predictions_step1.txt`, SHA-256 `34f07455d446a576a17e6f771b2934bc1becc6b6570198ca10941aa9632f58a3`)

Instrument: `F:\trading bot\scratch\p111\measure_logs.py` (SHA-256 `c9c42a5dbf898b2ae81c247eee5e2f5835697b99d0be9f35a93b5b27780affd3`),
read only, over the frozen copies in `F:\trading bot\files\binance-trading-bot\m5j-evidence\`. A rate is the bytes of a pid's tagged lines (CRLF
counted as written) over the hours from its first to its last record. Untagged lines are 544 bytes per boot (the banner). The whole-file rate divides
the file's size by the same hours and is what the prediction file used.

| Capture | SHA-256 | Pid and run | Tagged bytes | Hours | Tagged B/h | Whole-file B/h |
|---|---|---|---|---|---|---|
| `trading_bot.m5l-observation-run-pid24980.log` (53,021 bytes) | `023c72a1870eb4f770f837b82173cf9bc7e8339b196231a290e60c28bb7944eb` | 24980, `2026-10-03T20:08:24Z` to `2026-10-04T04:29:50Z`, section 26 | 51,646 | 8.357 | **6,180** | 6,344 |
| `trading_bot.m5l-evidence-run-pid21520.log` (23,625 bytes) | `c1471d3c3b61a1f765b339bfc83af549c71bbb92821310f158c8b4ff85bc089f` | 21520, `2026-09-27T13:30:56Z` to `16:53:23Z`, section 21 | 22,234 | 3.374 | **6,589** | 7,002 |
| `trading_bot.m5k-close-20260925T182818Z.log` (5,074,996 bytes) | `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528` | 16 pids with 20 or more records, 193.8 h in all | 1,314,213 | 193.8 | pooled **6,783** | |

In the third capture the highest single pid is 7888 at **9,827** B/h and the longest is pid 16216, 52.6 h at 7,780 B/h. Every one of the older
captures also holds about 3.7 MB of untagged lines from before the `pid=` field began on `2026-08-27`; they are ignored. A `reconciliation_pass` line
is **192.0 bytes** in both runs (`calc_step1.py`: 170 lines, 32,640 bytes, in the observation run; 58 lines, 11,136 bytes, in the evidence run), and it is
logged once per pass, only while a position is open: 170 passes in 8.357 h is 20 an hour, against the 60 an hour a one-minute bar allows. Five earlier
captures were also measured, and every pid in them is a pid of the third capture (read from the output, not assumed), so they add no rate:
`trading_bot.live-20260917T182829Z.log` `d0219fb3cecc9e9280b6df780b1d2b27331da3a61694cbfbc18dfe381a2bece4`,
`trading_bot.live-20260917T183900Z.log` `4b88118a64f884190ac85f22dcd9046f23cbd0e11b5cac06c43ff70140347c32`,
`trading_bot.final-20260917T185851Z.log` `0e6b673e16671152a4e08ca6cc8390e7b72ea8b75c3e7303fa0c16b4e04d223e`,
`trading_bot.x1-20260918T175500Z.log` `bbdeb1787ac0caf5782229391ef6cf5931a046193d8b6fef078ef3941121e182` and
`trading_bot.p2a5-20260923T064334Z.log` `e747b3e80ce3be4f76da41da7262ef19adacfc3c34b0fcb739b4055dc44c2589`. The measure's whole output is
`measure_logs_out.txt` (SHA-256 `1fc0d7396422c561c36eedcf256ad9c91723924c17cf4b2c667e1bd7de4d69c4`) and `measure_logs_busy_out.txt`
(`c254d27a2e21468b284a299a30b50c6d67e916ff34777540fca653452bff9270`).

### Step 1c: the volume of a 35-day run against the capacity (`calc_step1.py`, SHA-256 `8ec470fd9e5681c9545af5d564f0148c870821f27740b4d8401d8477f91d3a09`;
output `calc_step1_out.txt`, `52492666b2c4f9ad8900334c5ce0ee6bc5eb6440a6f755184e6ddb42f777a82e`)

840 h is the cap (R-AY); the 21-day minimum is 504 h, 60% of each figure.

| Rate used | B/h | Volume over 840 h | Capacity / 2 x volume | One file / volume | Rollovers at 10 MiB |
|---|---|---|---|---|---|
| observation run, tagged | 6,180 | 5,191,036 | 6.06 | 2.02 | 0 |
| evidence run, tagged | 6,589 | 5,535,162 | 5.68 | 1.89 | 0 |
| pooled, older pids | 6,783 | 5,697,610 | 5.52 | 1.84 | 0 |
| highest single pid seen | 9,827 | 8,254,905 | 3.81 | 1.27 | 0 |
| structural: 60 pass lines an hour (192.0 bytes) on top of the highest seen | 21,347 | 17,931,705 | **1.75** | 0.58 | 1 |

The structural row is a bound and not a measurement: a position open for the whole run, which no capture shows, plus the highest rate any pid
logged (which already contains some pass lines, so the sum double counts them). The capacity holds twice the volume at a rate up to **37,449 B/h**.
It does not model a failure state: a handler that raises a traceback every bar has no bound in lines, and the run would be stopped and
investigated before it mattered.

### Step 1d: the decision

**Capacity is at least twice the predicted volume in every row, the smallest margin being 1.75 times over twice the volume, so P111 does not halt on R-BK.**
The owner's options 1d lists (a daily freeze of every rotated file with a reassembly; `s4_compare.py` accepting several captures in order;
a larger rotation in `config.yaml`) are not needed and none was chosen. **One further fact, for the owner and not a halt:** `scripts/s4_compare.py --capture`
takes one file (`add_argument("--capture", type=Path, required=True)`), and the whole run stays in the one active file only while its average rate is
under 12,483 B/h over 840 h (10,485,760 / 840). Every measured rate is under it; the structural bound is over it.

### Against the predictions (`predictions_step1.txt`)

| Predicted | Observed |
|---|---|
| capacity 62,914,560; one file 10,485,760 | the same |
| observation run about 6,300 B/h; evidence run about 7,000 | 6,344 and 7,002 on the whole-file basis (6,180 and 6,589 tagged) |
| the 2026-09-17 capture's busy rate **15,000 to 40,000 B/h** | **WRONG**: no pid in any capture is above 9,827 B/h. The 2026-09-17 pids sit at 7,328 to 8,715. The prediction took a day of 13 trades to mean a much louder log; the older code logged about as much per hour |
| a pass line of about 230 bytes | **WRONG**: 192.0 bytes |
| 35-day volume 5.3 to 5.9 MB at the quiet rates | 5.19 to 5.70 MB tagged, 5.33 to 5.88 MB whole-file |
| the structural worst case about 17 MB, margin about 1.8x over twice the volume | 17.93 MB, 1.75 |
| the whole run in one file at the quiet rate, margin about 1.9x | 1.84 to 2.02 |
| P111 does not halt | it does not |

### The C5 line count (`ceaaa9b`)

`ceaaa9b`'s message says *"Numstat: 3 paths, 68 changed lines (RUN_LEDGER.md 57, NEXT_MILESTONE.md 10, config.s4.yaml 1/1)"*. `git diff --numstat
ceaaa9b^ ceaaa9b -- . ':(exclude)config.yaml'` reads `1 1 config.s4.yaml`, `10 0 docs/NEXT_MILESTONE.md`, `57 0 docs/RUN_LEDGER.md`: 69, the 1/1 having been
counted as one. The commit is not amended; this is the record (`M5m-289`).

### Digests of the P111 instruments and outputs (SHA-256)

| File | SHA-256 |
|---|---|
| `predictions_halts.txt` | `ddb1c11de6e2c9b9ed25e716d6c2c8c9d0473ec7b72ff2267687c333cde34a94` |
| `predictions_step1.txt` | `34f07455d446a576a17e6f771b2934bc1becc6b6570198ca10941aa9632f58a3` |
| `predictions_c1.txt` | `30986333e262c236342890b3629ce161f4f1a4ad6d2788ce2221b308f7836262` |
| `gate_h4.txt` | `ee5e91b3a5b5142d573c8f59f478dba308933cb616088ce0821baa29418fa443` |
| `measure_logs.py` | `c9c42a5dbf898b2ae81c247eee5e2f5835697b99d0be9f35a93b5b27780affd3` |
| `measure_logs_out.txt` | `1fc0d7396422c561c36eedcf256ad9c91723924c17cf4b2c667e1bd7de4d69c4` |
| `measure_logs_busy_out.txt` | `c254d27a2e21468b284a299a30b50c6d67e916ff34777540fca653452bff9270` |
| `calc_step1.py` | `8ec470fd9e5681c9545af5d564f0148c870821f27740b4d8401d8477f91d3a09` |
| `calc_step1_out.txt` | `52492666b2c4f9ad8900334c5ce0ee6bc5eb6440a6f755184e6ddb42f777a82e` |

## 43. M5m S4: the launch -- the start record, the recorder, the retirement of `51a5f2711a09`, and what the first hours show (P112 C1)

Recorded at P112 (C1), after the launch. An observation log, so this section only adds. **The start record was written after the bot was
launched, as the checklist's step 1.10 says it must be**, and the figures marked *owner* are the owner's as stated in the P112 prompt;
the figures marked *measured* were read at P112 from the places named. Nothing in `F:\trading bot\deploy\45547f107715` was opened for
writing or run: its log was read through a share-mode copy (`FileShare.ReadWrite`, source opened `FileAccess.Read`), its `state.json`
and `.env` were not read, and no process of it was touched.

### The start record

| Field | Value | Source |
|---|---|---|
| `T0` | `2026-10-10T06:05:20Z`, the `run` boot's `boot_provenance` line | *measured*, log line 24 of the copy; *owner* agrees |
| pid, launcher | 16076, parent 13976 (`CreationDate` `12:05:19` local, UTC+6, i.e. `06:05:19Z`) | *measured*, `Win32_Process`, read at `2026-10-10T08:46Z` or after |
| `code_commit`, `checkout_commit` | `45547f10771543b41db42e1cbcb8b5a0a9cf1776`, both, `commits_agree=true` | *measured*, the boot line |
| `config_sha256` | `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`, `config_tracked=true` | *measured*; equals `config.yaml` at `HEAD` (section 42) |
| `verdict`, `install_kind`, `code_intact` | `accepted`, `vcs`, `true` over 77 files; `checkout_dirty=false` | *measured* |
| free USDT | `95170.91` | *measured*, the log's `Composition root ready: 2 pair(s), 95170.91000000 USDT free`; *owner* |
| `data/state.json` | `1F91FC43...7396` | *owner*. The pre-registration records `1f91fc4335a3d62899ae9ba430aa6abd41a6f4468a0605ba5b252143f7677396`; the clone's file was not re-read |
| Python | 3.12.10, package 0.1.0 (the boot line's `python_version`, `package_version`) | *measured*. The Microsoft Store build, launched from a non-elevated window (`IsInRole Administrator` False), and the clock offset `-0.228 s` against `time.windows.com` at `2026-10-10T06:04:37Z`: *owner* |
| `W` | `2026-10-11T00:00:00Z`, the first UTC midnight at or after `T0` | derived |
| earliest stop | `2026-11-01T00:00:00Z`, the first UTC midnight at or after `T0` + 21 days (`2026-10-31T06:05:20Z`) | derived |
| cap | `2026-11-14T06:05:20Z`, `T0` + 35 days | derived |

The log's first 100 lines hold **three** `boot_provenance` lines, all `verdict=accepted`: pid 27460 at `05:58:02Z` and pid 27176 at `05:58:16Z`,
each only a banner and that line (the `strategies` verification boots of step 1.4; the log does not say which subcommand booted), and the `run` boot above.
The engine started at `06:05:24Z` (`Trading engine started: BTCUSDT/1m, ETHUSDT/5m`), 4 s after `T0`, seeded with 499 closed candles per series.

### The recorder, and the retirement of `51a5f2711a09`

| Fact | Value | Source |
|---|---|---|
| recorder clone | `F:\trading bot\recorder\45547f107715`, the only entry under `F:\trading bot\recorder` | *measured*, `Get-ChildItem` |
| task | `tb-recorder`, principal `User`, `S4U`, `Limited`; action `...\45547f107715\.venv\Scripts\python.exe scripts\record_testnet_klines.py --root data\historical_testnet`, working directory the clone | *measured*, `Get-ScheduledTask` |
| first scheduled run | `2026-10-10T05:52:29Z`, result 0 | *owner* |
| latest run | `LastRunTime` `12:05:01 PM` local = `06:05:01Z`, `LastTaskResult` 0, next `6:05:00 PM` local = `12:05:00Z`, 0 missed runs | *measured*, `Get-ScheduledTaskInfo`, read at about `08:46Z` |
| the retired clone | `51a5f2711a09.retired-20261010T060037Z`, `.venv.disabled` present, no `.venv\Scripts\python.exe` | *measured* |
| the one runnable venv | `45547f107715` alone (`Test-Path` True; every other directory under `deploy` False) | *measured* |
| recorder's first run in the clone | added 588 bars (1m) and 117 (5m) per symbol, exactly the grid since the last stored bar | *owner* |

### What the first hours show (a copy of the log taken at `2026-10-10T08:45:57Z`)

The copy is `F:\trading bot\scratch\p112\s4_log_copy_h5.log`, 19,778 bytes, 100 lines, SHA-256
`57abddd4914b6b1414f9f992ae01699a5b31da4cd2c3f970a38b2bb077a7771d`. It is a reading of the first 2 h 40 m and is **not an S4 result**: the
capture S4 reads is the frozen log at the stop.

| Fact | Value |
|---|---|
| records by pid | 78 pid 16076, 2 pid 27176, 2 pid 27460, and the banner's untagged lines |
| levels | 3 `WARNING` (`boot_assets_excluded` 514 assets, `close_window_open`, `reconciliation_untrusted`), no `ERROR`, no `CRITICAL` |
| events | 47 `reconciliation_pass`, 3 `risk_refused`, 3 `intent_dispatched`, 2 `order_placed`, 1 `close_booked`, 1 `exit_booked`; no `engine_stopped` |
| first `reconciliation_pass` | `06:48:00Z`, 42 min 40 s after `T0` and 59 s after the first order list (`06:47:01Z`) |
| trade 1 | BTCUSDT list 34993 placed `06:47:01Z`, closed by the bot's own `CLOSE` (death cross) `07:06:03Z`, `close_booked` `realised=-2.38611150` on `entry_quote_total=1900.90191150` (-0.1255%) |
| trade 2 | BTCUSDT list 35415 placed `07:46:01Z`, entry 82,850.77, stop 81,193.76 (1.99999% below the entry); the stop leg filled `08:28:40.621Z` in 3 fills, `quote_total=1625.00953000` for 0.02297000 BTC, an average of **70,744.86** (exact `Decimal` division, below), `exit_booked` `08:29:02Z` `realised=-276.17165970`, `fee=0E-8 fee_asset=USDT` |

Trade 2's average fill is **12.869% below the stop's trigger** and 14.612% below the entry, a return of -14.526% on the entry quote total, against the
1.20% stop slippage S5 and S7 are specified at (R-B2). The arithmetic is exact `Decimal`: `1625.00953000 / 0.02297000`, the stop `81193.76`, the
entry `82850.77`. It is one fill. It is recorded as an observation (`M5m-302`) and decides nothing in S4, whose tests read the frozen capture.

`scripts/s4_compare.py`'s own `down_intervals`, run over the copy (`run_down_intervals.py`, output `down_intervals_out.txt`), returns two intervals:
pid 27460 to pid 27176, `05:58:02Z` to `05:58:16Z` (0.2 min), and pid 27176 to pid 16076, `05:58:17Z` to `06:48:00Z` (**49.7 min**), the second ending at
the run's first `reconciliation_pass` and not at its boot. Both lie before `W`. See `M5m-301`.

### The R-BJ and R-BM rulings

Quoted in `docs/NEXT_MILESTONE.md` (the P112 C1 annotation). R-BL: a WebSocket-against-REST difference is tallied as `bar differs`, and no frozen file changes.
R-BM: if the active log rolls over, the capture is the rotated files concatenated oldest first (`trading_bot.log.5` ... `.1`, then `trading_bot.log`), each frozen with
its SHA-256, the concatenation's SHA-256 being the capture's digest; the daily freeze copies every `trading_bot.log*` file.

### Digests of the P112 instruments and outputs (SHA-256)

| File | SHA-256 |
|---|---|
| `predictions_halts.txt` | `36308498a45108e4a7f3ef78181df38fb725e95f8a67f0e4347d94c3e6f87c6d` |
| `predictions_c1.txt` | `0b4587e3b786a6d96731e5793c69d4b1c1d07614ffdb148f9247f0e6d67867de` |
| `gate_h3.txt` | `c084b952ec7aa21b57e06198ad7a0718f495e521ee5c5657d347a4c7790bbbc8` |
| `s4_log_copy_h5.log` | `57abddd4914b6b1414f9f992ae01699a5b31da4cd2c3f970a38b2bb077a7771d` |
| `run_down_intervals.py` | `882acc49d032f60694feb2e28506e9dd689bcacbe632ce646ddb3feac2b28996` |
| `down_intervals_out.txt` | `2a1d21e3c9159c7d79fc28c6bbcbcfaed47024fa6ea9649ac877e7fbfaae340d` |

## 44. M5m S5/S6: P113's halts, and the Phase 1 measurements whose findings are declared at P113 C1

Recorded at P113 (C1). An observation log, so this section only adds. P112's Phase 1 was read only and produced no commit, so its probe
findings (`M5m-303` to `M5m-312`) are declared in the commit that records their measurements, which is this one, and their instruments are listed here.

### The halt conditions (predictions: `F:\trading bot\scratch\p113\predictions_halts.txt`, SHA-256 `2665860f92038b6342e80d3534e59e18349224f6ef056363efb40482fb9359d5`)

| Halt | Predicted | Observed |
|---|---|---|
| H1 `HEAD`, `origin/main` | `af51911` for `HEAD`; `origin/main` `af51911` if pushed, else `45547f1` (the file leaned to pushed) | both `af5191155d72e9a8ebf3e5bc5e035e5c5e3b2296`: **the owner has pushed** |
| H2 `git status --porcelain` | empty | empty |
| H3 `scripts/check.py`, bare to a file | 183 / 96 / 3371 passed, 1 skipped | the same, exit 0, 222.5 s (pytest 215.30 s); Testnet ping 200 at `2026-10-10T09:12:06Z` and `09:15:49Z`; `gate_h3.txt` SHA-256 `a175a8b3b3ae2a939c1e4b902e8154c9ff912f1820c672d92c3a5e08337b7d66` |
| H4 `scripts/check_findings.py milestone/M5l..HEAD M5m` | `M5m-001` to `M5m-302`, gapless, blockless `[934eb45]` | 302 declared, 302 distinct, no duplicate, no gap, cited-not-declared none, blockless `[934eb45]` |

### The P112 Phase 1 instruments and outputs (SHA-256), under `F:\trading bot\scratch\p112\`

| File | SHA-256 |
|---|---|
| `predictions_phase1.txt` | `34b36db3ab9336655157a7050ec4960af3b687be601572753f53f3d3452581ee` |
| `p1_store.py` | `b48b2088d1815b4c00b345da53538b875101d205d2ab95b881a9846a46ff9f01` |
| `p1_store_out.txt` | `cb0c8b9d552d2c920f72cc8bbfcc215825b1cf0970f3c7cf56cceaf95fbd52df` |
| `p1_warmup.py` | `4fa57353724d737314f548d57fed05391a30890fd4abd82da1080101cde913b2` |
| `p1_warmup_out.txt` | `ebef21cb3916a3e71a36f644fe8df0705538d41b189ebcfb30c99fc674851257` |

### The research protocol, as committed

`docs/research/PROTOCOL.md`, SHA-256 `4f1e31fe8e800d5d6948599fdcbc405a7d736097a94167cdaeaec06824472cdd`, and `docs/research/LOG.md`, SHA-256
`95b2f3cfb0e557e202632768212154a250fae8f5b87997884d4f7c1613dae438`, in the tree this commit leaves. The protocol declares 216 variants (54 `sma_crossover`,
162 `rsi`), the out-of-sample window `[2024-01-01, 2026-10-01)` with its eleven labelled quarters (4 rising, 5 sideways, 2 falling), and the
labels file's digest `6f78922b649c3a6592776721b20dacf80d34067506ce49e700c53d0b683c0e72`. Items the owner has not ruled and may overrule before the push are
marked DRAFTED in the file: the grids, the selection rule and the walk-forward report, the in-sample trade minimum and the entry file's shape.

## 45. M5m S5/S6: the committed config at every timeframe, and what the override layer therefore does (P113 C2b)

Recorded at P113 (C2b). An observation log, so this section only adds. R-BR's `--timeframe` has to produce a config that `AppConfig` accepts. The committed
`config.yaml` (SHA-256 `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`) was loaded, dumped, every pair's timeframe replaced, and re-validated
(`probe_override_validate.py`, SHA-256 `1971032046b1c44b1ba9f89ef5f331e5207f4cdc3a1bf54047240d0ca0478434`; output `probe_override_validate_out.txt`, SHA-256
`467547ef563a93770f60739b799fa8b4e3b6dbd0634b1dfe9f0717fcf5fce6e5`, both under `F:\trading bot\scratch\p113\`). The round trip itself is lossless (`again == config` True).

| timeframe of every pair | the validator, with `risk.max_position_staleness_s` 180 | the floor it names |
|---|---|---|
| 1m | valid | (below 180) |
| 5m | refused | 756 s: (1 + 0.5 + 1) x 300 + 1.0 + 5 |
| 1h | refused | 9,006 s |
| 4h | refused | 36,006 s |
| 1d | refused | 216,006 s |

The committed 180 s passes only because the shortest timeframe is 1m. The override layer therefore raises the bound, **only when the validator refuses it**, to the round value its own message
recommends, `(3 + k) x T` with `k = min(max_open_positions, enabled pairs) - 1 = 1`: **1,200 s at 5m, 14,400 s at 1h, 57,600 s at 4h and 345,600 s at 1d** (`tests/unit/test_backtest_overrides.py`
pins all four, and that 1m is left at 180). A backtest stamps every open position on every bar of every pair (`simulated_executor.py`, step 4), so the bound never acts in a backtest; the raised value
is in the run record's `effective.risk` and in both digests.

**A float for an integer period.** `--param fast_period=4.0` builds `SmaCrossoverStrategy` and then every bar raises `TypeError: 'float' object cannot be interpreted as an integer` inside
`_window_mean`; the engine counted six ERROR records and quarantined `BTCUSDT/1h` after five consecutive failures, so the run ended having traded nothing (seen in a test run during C2b, the output
not kept). The override layer now refuses a non-integer for a parameter whose constructor annotation is `int`; a float for a float threshold (`oversold=30` and `30.0`) is accepted and is one candidate.

| file | SHA-256 |
|---|---|
| `predictions_c2a.txt` | `2f4d329f6698734a4c1916f8c0bb4ef3762f68d1e1123b2b25efd969a184c7af` |
| `predictions_c2b.txt` | `f91700449d8df77b6b570b6f0970df2423ba9694b7587ad90a856b2bf1a9c435` |
| `gate_c2a.txt` | `2ab29fb36ae72db176646ed760086aae748788c7c6d134d595015633cba953ab` |
| `gate_c2b.txt` | `0e79faebd0e9bb5624fcdf3ed5d365cc18182ea754cfe68fee45d90b112931cc` |

## 46. M5m S4: the run's interruptions to 2026-10-14, and the state it was left in (P113, R-BN)

Recorded at P113, after the fact. An observation log, so this section only adds. R-BN, verbatim: *"Every restart during S4 is recorded."* The owner told the reviewer that they had forgotten the bot
was running and powered the PC off; this section is what the S4 log and the operating system's own System event log show, in UTC. **Nothing in `F:\trading bot\deploy\45547f107715` was opened for writing, run or
changed**: the log was read through a share-mode copy, the clone's `.env` and `state.json` were not read, and no venue write was made. The Testnet account was read once, by `scripts/check_testnet.py` from the
development tree (GET only; it places no order).

### What was read

| Item | Value |
|---|---|
| the log copy | `F:\trading bot\scratch\p113\s4_log_copy_after_shutdown.log`, 648,252 bytes, 2,738 lines, SHA-256 `19314c80c0b38700555eb1d7bc2ba532515d7ab314eb9fad776a3a9f68538ed6`, taken shortly after `2026-10-14T04:00Z` |
| the source | `logs\trading_bot.log` last written `2026-10-13T07:00:48Z`; `.bot.lock` last written `07:00:45Z`; no `trading_bot.log.1`, so the log has not rotated (R-BM does not apply) |
| the System log | `Get-WinEvent` ids 12, 13, 41, 42, 107, 109, 1074, 6005, 6006, 6008, 6013 from `2026-10-12T00:00Z`; the machine's clock is UTC+6 |
| the Testnet account | `check_testnet_after_shutdown.txt`, SHA-256 `e258a81331aa024d6a130f00b3dc63b954c1865b7599d10285711f7bb777065b`, read after the log copy on `2026-10-14` |

### The timeline (UTC)

| Instant | Event | Source |
|---|---|---|
| `2026-10-10T06:05:20Z` | pid 16076 boots (`T0`, section 43); the engine starts `06:05:24Z` | log |
| `2026-10-12T04:17:41Z` | `Received SIGINT; shutting down gracefully`; `04:17:43Z` `engine_stopped clean_shutdown=True` (pid 16076 ran 46.206 h) | log |
| `04:20:57Z` to `04:21:07Z` | the owner powers the PC off (event 1074, then 13) | System log |
| `10:44:33Z` to `10:45:49Z` | the machine starts and is powered off again 69 s later | System log |
| `18:10:57Z` | the machine starts | System log |
| `19:17:35Z` | **pid 22304 boots** (a restart: 14 h 59 m 52 s after the stop); its boot line is `verdict=accepted`; the engine starts `19:17:49Z`; free USDT `94,857.78263310`; its first `reconciliation_pass` is `19:20:01Z`, a restored position | log |
| `2026-10-13T06:54:01Z` | **pid 22304's last record** (an `exit_book_refused` WARNING on ETHUSDT) | log |
| `06:55:31Z` to `06:55:40Z` | **the owner powers the PC off while pid 22304 runs** (event 1074 "Other (Unplanned)", then 13). There is no `SIGINT` line and no `engine_stopped` for pid 22304: **the close was ungraceful, 1 min 30 s after its last record** | log, System log |
| `06:59:09Z` | the machine starts | System log |
| `07:00:36Z` | **pid 3444 boots**; `07:00:48Z` it **refuses** (ERROR): *"1 restored record(s) cannot be resolved at boot ... ETHUSDT, order list tb1-ETHUSDT-1791858599999-0-L: a leg is partly executed; list 71012 ALL_DONE: W FILLED 0.76400000/0.76400000, SL EXPIRED 0.07560000/0.76400000, TP EXPIRED 0E-8/0.76400000 ... Nothing on disk was changed."* | log |
| `07:02:57Z` to `07:03:03Z` | the owner powers the PC off again (event 1074, 13) | System log |
| `18:04:11Z` | the machine starts | System log |
| `22:29:09Z` to `22:32:18Z` | **Windows restarts the machine twice by itself** (event 1074, `MoUsoCoreWorker.exe` "Service pack (Planned)", then `TrustedInstaller.exe` "Upgrade (Planned)"); it is up from `22:32:18Z` | System log |
| `2026-10-14T04:00Z` | no `python` process of `trading_bot` exists (`Win32_Process`); **no bot has run since `07:00:48Z` on 10-13** | `Win32_Process` |

### The bot-down intervals, as the frozen `scripts/s4_compare.py` computes them

`down_intervals` over the copy (`run_down_intervals.py`, `down_intervals_after_shutdown_out.txt`) returns four. Two are the `strategies` verification boots of the launch (`05:58:02Z` to `05:58:16Z`, and
`05:58:17Z` to `06:48:00Z`, M5m-301). **`04:17:43Z` to `19:20:01Z` on 10-12 (902.3 min, 15.04 h)** is the first restart. **`06:54:01Z` to `07:00:35Z` on 10-13 (6.6 min)** is the second: the refused boot is a process, so the
interval ends at the refusal's first line and not at any resumption. The outage that follows is not an interval yet; it will be measured from the refused boot's last line, `07:00:48Z`, to the next process's first
`reconciliation_pass`. The OS had the machine off from `06:55:40Z`, so the log's own last line understates the outage by 1 min 39 s at its start.

### What the log shows besides the shutdown

- **The ETHUSDT stop leg filled 0.0756 of 0.764 ETH and expired.** Order list 71012 was placed `2026-10-13T02:30:02Z` (0.764 at 2,483.25, stop 2,433.59). From `02:59:02Z` every reconciliation pass reported *"leg SL reports
  EXPIRED with 0.07560000 executed"* and refused to book it (*"the fill is partial"*, order 1867449): **171 refusals** over 3 h 55 m, the last at `06:54:01Z`. The remainder, 0.6884 ETH, was never sold.
- **A MARKET sell on BTCUSDT filled partially on 2026-10-11.** `close_position_naked` (CRITICAL) at `16:00:02Z`, `reason=close_partial_fill`, 0.02279 BTC, list 51703, then 29 `exit_unbookable` CRITICAL lines to
  `16:51:01Z`; the strategy's next `CLOSE` at `16:52:00Z` followed and the lines stop.
- **Network.** 8 ERROR records: a failed reconciliation pass on BTCUSDT/1m at `2026-10-11T03:37:02Z`, WebSocket drops at `03:59:31Z` (keepalive ping timeout; `getaddrinfo failed`) and `13:29:21Z`, and the refusal above.
- **Counts:** 43 order lists placed (34 BTCUSDT, 9 ETHUSDT), 40 `close_booked` and 2 `exit_booked`, so **42 bookings** (38 in pid 16076, 4 in pid 22304) in 57.81 h of uptime: **17.4 a day while up**, against the
  pre-registration's census-of-record rate of 7.86; 444 WARNING, 8 ERROR, 30 CRITICAL records.

### The state it was left in, for the owner

| Fact | Value |
|---|---|
| ETH | free `0.68840000` (= 0.764 - 0.0756), locked 0, about 1,729.65 USDT at the last price 2,512.57; `check_testnet.py`: *"unmanaged holding ... BLOCKS entries"* |
| BTC | 0 |
| USDT | free `93,139.88439310` (the run started with 95,170.91) |
| the bot's record | the store holds an ETHUSDT record that boot refuses; releasing it needs `scripts/release_position.py --symbol ETHUSDT --preview`, run from the S4 clone with the bot stopped, **after** the ETH is resolved at the venue |
| the recorder | `--verify-only` over `2026-10-07T10:32Z` to `2026-10-14T00:04Z`: 1m 9,453 bars and 5m 1,891 bars on both symbols, **0 gaps, 0 problems**; `tb-recorder` last ran `06:05:01 AM` local (`00:05Z`), result 0; so there is no sign of a Testnet reset (R-AZ) and the shutdowns cost no recorded data |
| the pre-registration clock | unchanged: the cap `2026-11-14T06:05:20Z`, the earliest stop `2026-11-01T00:00Z`; downtime is excluded on both sides and never moves them |

**What the reviewer did not do**, because each is a venue write or the owner's: sell the ETH, release the record, restart the bot, or add the two partial fills to U10 (R-BO covers the price excursion only).

| File (under `F:\trading bot\scratch\p113\` unless named) | SHA-256 |
|---|---|
| `predictions_s4_record.txt` | `67f0682c0b5c02619c7f4a04275ad50624c6fdcab180ba3df37bb82db4b6391a` |
| `run_down_intervals.py` | `bac8a66f68fe7aebb4f13032ffed7bcd8f4ce65e6fe6eb2e95d7a9d8d5b2f075` |
| `down_intervals_after_shutdown_out.txt` | `58136c29f17fe4d8c775ba0ce3c8b0d6ac77bac0c5da04cf5bcc9dba5b9c2369` |
| `restore_c2b.py` (C2b's script edit, reported in its message) | `b29e1e98d009861c8786bd5a9eeb1a8d64a6a4b8744d9b189e91b3dc99196760` |
| `msg_c2b.txt` | `2181bbaf7f72678d2e53823e69ba4a401299bf13e9c4abbf66f0d267c470f71c` |

## 47. M5m S5/S6: the Q2 mutation survey of the research-protocol guard, and what its harness taught (P113 C4)

Recorded here as an observation of 2026-10-14; the table of results is in the message of `478a746`.

- **Where.** A detached worktree at `caa75cb` under `F:\trading bot\scratch\p113\survey\wt_c4`, outside the repository, with the ten C4 files copied in and shown SHA-256-equal; removed afterwards
  (`git worktree list` shows the main worktree only). The harness was the worktree's own `scripts/mutation_survey.py`.
- **The import location was proven on every outermost session** by a pytest plugin (`survey_probe.py`) that raises if `trading_bot`, `tests` or `trading_bot.backtesting.protocol` resolve outside the worktree. The
  first two baselines failed four `tests/unit/test_mutation_survey.py` tests with pytest exit 3: that file starts pytest sessions of its own, which inherit `PYTEST_ADDOPTS` and `PYTHONPATH`, set
  `PYTEST_CURRENT_TEST` and **import the development tree even inside a worktree** (`probe.log` and `probe2.log` show their `trading_bot` resolving to `F:\trading bot\files\...\src`). Those nested sessions test throwaway
  targets and are not the survey's; the probe now judges only a session without `PYTEST_CURRENT_TEST` (`M5m-325`).
- **The unmutated baseline in the worktree, no `.env`:** 3703 passed, 4 skipped, exit 0, in 122.01 s (`baseline3.txt`).
- **Seventeen mutations, 2026-10-14T04:51:29Z to 05:27:40Z: 49 kills predicted and 49 observed, every killing test the one named in the predictions, no crash, no abstention that was not declared.** The twelve in
  `protocol.py` killed 3, 3, 3, 8, 5, 3, 4, 3, 2, 1, 4 and 2; the four in `main.py` 1, 2, 0 (equivalent, `H3`) and 2; the one in `engine.py` 3.

| File (under `F:\trading bot\scratch\p113\` unless named) | SHA-256 |
|---|---|
| `predictions_c4_survey.txt` | `7c7798ddbbd493d2c38beaeae32edc67cba338e1a0739f8a103459d913e7a0d6` |
| `survey\spec_protocol.json` | `aec5c9ad73ba55110e8f8341b7f89296205606ef3691deb5b5ff5c1863a5f1aa` |
| `survey\spec_main.json` | `6f06396b5a9998ae6c66e41c51ee98cb230ee9ebd93078325cb484ed2787880b` |
| `survey\spec_engine.json` | `06d7d17c708cee19c846cdd4e7a84a7f2469ea88862c9fa70cfab025c9d881cf` |
| `survey\survey_probe.py` | `4900f3425f1952ae56bf8e1c6c101014fa8c5456f9761d8195f925d7d982729d` |
| `survey\baseline3.txt` | `5ef55420eef92913cb33dca3c0d0dfe10d8c33c57f966281cab0729899b5cd98` |
| `survey\result_protocol.txt` | `25a7b042bfcac28798c5e429af8f76409efd0593c60e5e545f37404c2a6f1375` |
| `survey\result_main.txt` | `e71e469882c26427621fd092a93da37827d62faf248ae431cad931d2e943180d` |
| `survey\result_engine.txt` | `f8f5ac388d605e900343dfaa98a61ad6e387e6d01f29d7fda1686128a337f650` |

## 48. M5m S5/S6: the canonical frozen mainnet store, copied, verified and write-protected (P113 C7, R-BQ)

R-BQ, as the owner ruled it: backtest clones read the mainnet store through a directory junction to ONE canonical frozen store, with an ACL denying write and delete. This section records that store. It is
an observation of 2026-10-14, 10:55 to 11:20 local (04:55 to 05:20Z); predictions were written before the copy (`predictions_c7.txt`, SHA-256
`6a9790e94ec675f115d34de6e11838355b687d92c704bbe7819ba2e7d8cb050e`).

**Where and what.** `F:\trading bot\store\mainnet-historical`, copied by `robocopy /E /COPY:DAT` from `data\historical` of the development tree: `BTCUSDT` (559 files, 558.76 MB), `ETHUSDT` (559 files,
538.11 MB) and `_exchange_info` (8 files, 15.1 KB; both the `mainnet` and the `testnet` snapshots, of which a backtest reads only the environment its config names). **`_zips` (542 MB of downloaded archives) is not
copied**: a backtest never reads it. The development store's root `.gitkeep` is not copied. In total **1,126 files, 1,150,169,679 bytes, 1,100 CSV months**, the S5 series holding 5,725,299 rows (BTCUSDT 1m 4,767,676 +
ETHUSDT 5m 957,623).

**Verified, by a read-only tool run on the source and on the copy (`store_check.py`, SHA-256 `2a5b5530f525b69485f13141db1d73692760cb418203d1be4c7defa581827592`):**

| Check | Source (`data\historical`) | Canonical copy | After the ACL |
|---|---|---|---|
| files, excluding `_zips` | 1,127 (the 1,126 and `.gitkeep`) | 1,126 | 1,126 |
| CSV months hashed against their manifest's `csv_sha256` | 1,100 of 1,100 | 1,100 of 1,100 | 1,100 of 1,100 |
| mismatched / missing / extra | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `HistoricalStore.verify` problems over the 10 series | 0 | 0 | 0 |
| snapshots against their `.sha256` | 4 of 4 | 4 of 4 | 4 of 4 |
| inventory digest (SHA-256 of every `path size sha256` line) | `e010765d...4799` (with `.gitkeep`) | `6167e1693a486e6666686cda6cd5082d41320dd39af74bac88bbb64c81a3e116` | the same |

The copy's per-file inventory (`c7_canonical_inventory.jsonl`, 1,126 lines of path, size and SHA-256) is **equal** to the source's inventory minus `.gitkeep`, by a dictionary comparison, and the inventory taken after
the ACL is byte-identical to the one taken before it (SHA-256 `2e152a5d9527d705d7c8e1c42070894fd31d477aff5e0b87631ff89263248018` for both).

**The descriptive files' digests** (the manifests and registries a month is held to, and the snapshots a backtest sizes with; identical in the source and the copy):

| SHA-256 | File under the store root |
|---|---|
| `39247bf6d4a3281a1de88f367f316bdf6fd94de276a9f8ba03ca830930a1ce04` | `BTCUSDT/1d/MANIFEST.jsonl` |
| `4f549ffedaf7ed55596a389b028fc71db620d3c687d53a8a56a351ab3e34887d` | `BTCUSDT/1h/MANIFEST.jsonl` |
| `16e1919645f100937f2894d5467954b9c4d2ad38d2b9732d1d552745364de1f8` | `BTCUSDT/1m/MANIFEST.jsonl` |
| `5351a4ce959a9b81a490af2f674fc05e44e549241596eed977159a5f244383ce` | `BTCUSDT/4h/MANIFEST.jsonl` |
| `6e748f83f6378121a07b5dba0ff8d71f4821626bceb2242b6ef2b4691acff4f5` | `BTCUSDT/5m/MANIFEST.jsonl` |
| `e456846220ef3ffb47107769a391082ab4404d7fc884f657a00f367616d54645` | `ETHUSDT/1d/MANIFEST.jsonl` |
| `71d0f1e99ef2bcc68a042e4866e5df7345e36034adb047c0a90789e67dc907b2` | `ETHUSDT/1h/MANIFEST.jsonl` |
| `1cdca7c3f0d28fa7688146f632aed6aad787364e7a37f911f67a46933bbba5d9` | `ETHUSDT/1m/MANIFEST.jsonl` |
| `f650f94bdf4c4bb5545efe1ff62d525f3d70584ccb9aba3e4182874b05aedb82` | `ETHUSDT/4h/MANIFEST.jsonl` |
| `e9b879dffe0932ccf7f717c81276656f1fe21fd398a6a5164f72b6451dbaf1e6` | `ETHUSDT/5m/MANIFEST.jsonl` |
| `db69e0ba89c12c9dc2e4d9a071ca6413c9016cd71d6ed8cd2c12a6a16f8ae4d3` | `BTCUSDT/1h/IRREGULAR.jsonl` |
| `496b2fd52dbac04af2b7b79e1358965389063b78ac2c75f67d0800e26919d8f7` | `BTCUSDT/1m/IRREGULAR.jsonl` |
| `7c4ee9c601d1188f0dc9ec5436233e9391bd0c266156313d87c916d5656f7b9f` | `BTCUSDT/4h/IRREGULAR.jsonl` |
| `0cb2068f6e53ea73e645a1729a76f6e00be6c681a51c7f948cbe79cff3f2b1d1` | `BTCUSDT/5m/IRREGULAR.jsonl` |
| `ffeb425a48ab489a5de14ecb74bafe56023c7c48fe222492952d85a519dcd8a5` | `ETHUSDT/1h/IRREGULAR.jsonl` |
| `13b340b18a72b143cbc344ea22042f87602192e539c702e78b2d1b2f395e62de` | `ETHUSDT/1m/IRREGULAR.jsonl` |
| `e81691cbb703c68c0c6fb43c73447ba91a945f056512130230386f0b7b8ebf6c` | `ETHUSDT/4h/IRREGULAR.jsonl` |
| `76e237f0c3d23ff3ff08ef581cfe007f595add2c8ee5536d4e00fe8fa7b51f8d` | `ETHUSDT/5m/IRREGULAR.jsonl` |
| `9cf9d5446e7f83508b445a825d2cf776276a8f528ca9313c04e92eeb3d5c0591` | `_exchange_info/mainnet/BTCUSDT.json` |
| `9dc83b78736d16fa790cf559aac0c90a15c902498b257e77aa743fbc0dd037fe` | `_exchange_info/mainnet/BTCUSDT.json.sha256` |
| `55c2038ade11928a9e7d27f776bebe37c563ce346682daaf251ea1881090db75` | `_exchange_info/mainnet/ETHUSDT.json` |
| `ec7e35182c2a900afdcf739d244528d504c5e82db8bca70ec31ec2d38d51b9c4` | `_exchange_info/mainnet/ETHUSDT.json.sha256` |
| `40e24c66110ba645ef49ca595618321fdbe2a36f9eab9638eea564dd8b797dc7` | `_exchange_info/testnet/BTCUSDT.json` |
| `d1bdd4fb10bcbf3ba7efb6001f4296d64757f66420c3fe5f230a0ee709186e29` | `_exchange_info/testnet/BTCUSDT.json.sha256` |
| `87e5095e0e177267d7fe039b8ce1925c8e07903a0f64211c2b948f82705777cc` | `_exchange_info/testnet/ETHUSDT.json` |
| `809d70aa9228553b1b59e5d1379eef8736b3df219df5bd3eb2bf97ffffd81388` | `_exchange_info/testnet/ETHUSDT.json.sha256` |

**The ACL.** One entry on the root, inheritable to every file and folder under it: **DENY** to `ATUL\User` (SID `S-1-5-21-1869652020-2349085804-1297793637-1001`) of `WriteData, AppendData,
WriteExtendedAttributes, WriteAttributes, Delete, DeleteSubdirectoriesAndFiles` (SDDL mask `0x10156`). Read, execute, `ReadPermissions` and `Synchronize` are not denied, so the store can be read, hashed and walked.
The inherited entry is present on a nested CSV (`D;ID;DCLCRPDTCRSD`) and on a nested directory (`D;OICIID;DCLCRPDTCRSD`). **MEASURED, with the tests run on 2026-10-14:**

| Attempt | Result |
|---|---|
| create a file in the root | `UnauthorizedAccessException` |
| create a directory in the root | `UnauthorizedAccessException` |
| append to a CSV | `UnauthorizedAccessException` |
| overwrite a CSV | `UnauthorizedAccessException` |
| delete a CSV | `UnauthorizedAccessException` |
| rename a CSV | `UnauthorizedAccessException` |
| delete a directory tree (`_exchange_info\testnet`) | `UnauthorizedAccessException` |
| read and hash a CSV | works; SHA-256 `3568FA29A6AD762CD43E9C7E3210418D65FE43B2B681BF8D67BD0F16BF461CBE` before and after |
| the probe file and the probe directory | neither exists afterwards; 8 snapshot files intact |

**Two things the first attempt taught, because the first ACL was wrong.** (1) `icacls ... /deny "User:(OI)(CI)(W,D,DC)"` also made every file UNREADABLE, by its owner too (`Get-FileHash`: *"Access to the path
... is denied"*): icacls's simple right `W` includes `SYNCHRONIZE`, and a .NET or Python open of a file for reading asks for it (SDDL mask `0x110156` against the right one's `0x10156`). (2) `icacls ... /remove:d User` by
BARE NAME printed *"Successfully processed 1 files"* and removed NOTHING (the deny entry was still there, and the specific-rights re-add merged into it); removing by SID worked. The ACE was then set through
.NET's `FileSystemAccessRule`, naming the rights explicitly, and the tests above were run on that. **The canonical store was never writable by this process between the copy and the freeze beyond the copy itself.**

**Read through a junction, as a backtest clone will** (`junction_check.py`, SHA-256 `0d76b28025689d0384207420086e5eba85395f34a0d9beef9ac1ad873fc36501`): `cmd /c mklink /J` from a scratch directory to the canonical
store; `HistoricalStore.verify` for BTCUSDT and ETHUSDT at 1d and 4h returned no problem, and 10,080 BTCUSDT 1m bars were streamed for `2024-03-01` to `2024-03-08` (7 days x 1,440); `is_junction` true. The junction was
removed with `cmd /c rmdir` and the canonical store was shown intact afterwards (1,126 files). `Remove-Item` on a path of this layout is blocked by the session's tool guard, which is left alone: the junction test above
is the only deletion a junction ever needed.

**To lift the freeze (owner only):** `icacls "F:\trading bot\store\mainnet-historical" /remove:d "*S-1-5-21-1869652020-2349085804-1297793637-1001"`. **Nothing in this tree changes the store after the freeze**, and a
backtest clone reads it and writes only to its own `data\backtests` beside its junction.

**The development store is untouched** (`data\historical`: no deny entry; the inventory was taken before the copy and the copy changed nothing in it), and the S4 clone `F:\trading bot\deploy\45547f107715` was not opened.

| File (under `F:\trading bot\scratch\p113\` unless named) | SHA-256 |
|---|---|
| `predictions_c7.txt` | `6a9790e94ec675f115d34de6e11838355b687d92c704bbe7819ba2e7d8cb050e` |
| `store_check.py` | `2a5b5530f525b69485f13141db1d73692760cb418203d1be4c7defa581827592` |
| `junction_check.py` | `0d76b28025689d0384207420086e5eba85395f34a0d9beef9ac1ad873fc36501` |
| `c7_source_inventory.jsonl` (1,127 lines, with `.gitkeep`) | `af3b9fae07d94f984e16d3f3f3668433cd391ac439a01e0f982fcc5b9dd778f8` |
| `c7_source_check.txt` | `ddcea3d7d8e7d25d9c81604dde8a2539455a783e3e10753535f81be0497f3b25` |
| `c7_canonical_inventory.jsonl` (1,126 lines) | `2e152a5d9527d705d7c8e1c42070894fd31d477aff5e0b87631ff89263248018` |
| `c7_canonical_check.txt` | `cee3b439c74259b323c06b1e1316371a1d6ca2001c467f1281c0fe69c118e46b` |
| `c7_canonical_inventory_after_acl.jsonl` | `2e152a5d9527d705d7c8e1c42070894fd31d477aff5e0b87631ff89263248018` |
| `c7_canonical_check_after_acl.txt` | `cee3b439c74259b323c06b1e1316371a1d6ca2001c467f1281c0fe69c118e46b` |

## 49. M5m S4: the interruption resolved by the owner, and the run restarted as pid 25352 (P114 C1, R-BU and R-BV, R-BN)

Section 46 left the S4 run stopped, with 0.6884 ETH held and an ETHUSDT record that boot refused. This section is what happened next, read on `2026-10-14` from `06:38Z` to `06:45Z`. The S4 clone
`F:\trading bot\deploy\45547f107715` was NOT opened for writing and nothing in it was touched but one share-mode copy of its log; no venue write was made; the Testnet key was used for GET calls only.

**What the owner did (R-BU, verbatim in `docs/NEXT_MILESTONE.md`).** Three steps, in this order: (1) `scripts/clear_testnet_holdings.py --symbol ETHUSDT --execute` sold the 0.6884 ETH; (2) `scripts/release_position.py`
released the ETHUSDT record at `2026-10-14T06:33:40Z`; (3) the bot restarted as pid 25352 at `2026-10-14T06:34:33Z`. The owner's console outputs for the three steps were not handed to this session; what is recorded
below for step 1 is what the venue says, read independently, and for step 3 what the S4 log says.

**Step 1, as the venue records it** (`h5_read.py`, GET only, at `2026-10-14T06:42:28Z`; ETHUSDT order history, 36 orders of which 9 are MARKET SELLs; this is the latest):

| Field | Value |
|---|---|
| order id | `2272092`, client id `x-HNA2TXFJddcecaa79e3ab314575c01` (the library's default prefix, not this bot's `tb1-` scheme) |
| time | `2026-10-14T06:32:11.472Z`, one minute 29 s before the release and 2 min 22 s before the restart |
| status | `FILLED` |
| `origQty` / `executedQty` | `0.68840000` / `0.68840000` |
| `cummulativeQuoteQty` | `1723.64345600` USDT |
| fills | 1: price `2503.84000000`, qty `0.68840000`, quote `1723.64345600`, commission `0.00000000` USDT |
| last ETHUSDT price at the read | `2504.60000000`, so the fill was 0.030% below it |
| balances after | ETH free `0.00000000` locked `0.00000000`; BTC 0; USDT free `94863.52784910` locked `0` |

The remainder that the stop leg (order `1867449`, list 71012) never sold was therefore sold whole, in one fill, near the last price, with no commission on the venue's own record. **The sale is outside the ledger by design:
S4 counts this entry as unbooked (R-BU).**

**Step 2, the release's store digests**, as the owner gave them and abbreviated: before `7995924d...8988`, after `7e5c4d42...dd7c`. They are the two SHA-256 figures `scripts/release_position.py` appends to
`logs/release.log` in the clone; **that file and `data/state.json` were not read here**, because this task touches nothing else in the clone, so the full digests are not in this tree. A digest that differs before and after
is what a release that removed a record would produce, and is all the abbreviated figures show.

**Step 3, the restart record (R-BN).** From a share-mode copy of the S4 log taken at `2026-10-14T06:42:43Z` (650,432 bytes, SHA-256 `3af6327d3cae1616a0882dff9f9d1f331cc9706a74470d1db1271ba6a50ae5da`):

| Fact | Value |
|---|---|
| pid / first line | `25352`, `2026-10-14T06:34:32Z` (the banner); `boot_provenance` at `06:34:33Z` |
| verdict | `accepted`, `install_kind=vcs`, `code_intact=true` over 77 files, `checkout_dirty=false`, `commits_agree=true`, `config_tracked=true` |
| `code_commit` | `45547f10771543b41db42e1cbcb8b5a0a9cf1776` -- the same as pids 27460, 27176, 16076, 22304 and 3444 (this is the S4 clone's commit, not the development tree's HEAD) |
| `config_sha256` | `f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0` -- the same on all six boots |
| composition root | ready at `06:34:36Z`, 2 pairs, **94863.52784910 USDT free**, 514 assets excluded from equity (the pre-existing warning) |
| engine | started at `06:34:37Z`: BTCUSDT/1m, ETHUSDT/5m |
| refusal | none: the one match for "refus" in pid 25352's lines is the field `refusal_reasons=none` |
| the ETHUSDT record | not mentioned: the boot that refused it was pid 3444 at `2026-10-13T07:00:48Z`, and pid 25352 does not |

At the copy pid 25352 had been up 8 min 11 s and had written 9 lines.

**H6: the down time, from the frozen `scripts/s4_compare.py`'s `down_intervals` over that copy** (`run_down_intervals.py`, the frozen function imported and not edited; 2,753 lines by Python's `splitlines`):

| Interval | From | To | Minutes |
|---|---|---|---|
| pid 27460 to pid 27176 | `2026-10-10T05:58:02Z` | `05:58:16Z` | 0.2 |
| pid 27176 to pid 16076 | `2026-10-10T05:58:17Z` | `06:48:00Z` | 49.7 |
| pid 16076 to pid 22304 | `2026-10-12T04:17:43Z` | `19:20:01Z` | 902.3 |
| pid 22304 to pid 3444 | `2026-10-13T06:54:01Z` | `07:00:35Z` | 6.6 |
| pid 3444 to pid 25352 | `2026-10-13T07:00:48Z` | `2026-10-14T06:34:32Z` | 1,413.7 |

**The run was down from `2026-10-13T06:54:01Z` (pid 22304's last line, the owner's power-off) to `2026-10-14T06:34:37Z` (pid 25352's engine start): 23 h 40 m 36 s, 1,420.6 minutes.** The frozen function reports it as TWO
intervals, 6.6 and 1,413.7 minutes (1,420.3 together), because pid 3444, the boot that refused, is a process whose 13 seconds of life (`07:00:35Z` to `07:00:48Z`) it counts as up, and because it ends an interval at the
next pid's FIRST line (`06:34:32Z`) and not at its engine start. **The prediction written before this read said the function's figure "extends past 06:34:37Z", and it does not**: it ends five seconds before. The first
interval row's pid 27460 and 27176 are the pre-launch boots of `2026-10-10`, recorded in section 43.

The pre-registration clock is unchanged: downtime is excluded on both sides and never moves the cap (`2026-11-14T06:05:20Z`) or the earliest stop (`2026-11-01T00:00Z`).

| File (under `F:\trading bot\scratch\p114\` unless named) | SHA-256 |
|---|---|
| `predictions_halts.txt` | `fcea143c6641a219a45748839b00cc67b8b96b706f2ddf9fb9fc3ce768f99456` |
| `predictions_c1.txt` | `151792f1463476637939507688823229ed3edca6ff165865453d4ba99b282792` |
| `gate_h3.txt` | `10c0155ede6e9cc05bdf9ded62ffd1022edc6fb1c8c9439f90a376b7fed5ae5c` |
| `findings_h4.txt` | `a97820ec15c549decda5ad2f00fdb61dd3f505bdf12d693f0c4ab6b7c218be8c` |
| `h5_read.py` | `373401ce05ee0a35a47871aafdb12e7bb3dee02968817c1b9c448bc885bb37ad` |
| `h5_out.txt` | `cf14597a8592ee61790e9d9d421e0480aae5a20326f98b06388b13e8ffce195a` |
| `s4_log_copy_06h45.log` | `3af6327d3cae1616a0882dff9f9d1f331cc9706a74470d1db1271ba6a50ae5da` |
| `h6_down_intervals.txt` | `3251da9278513a953a3388b60a9b057524e934ca2f094df27dea62a2b1696116` |

## 50. M5m S5: the baseline's runs and report, the sizing floor, and the frozen function's rule (P115 C1, R-BW, R-BX)

Read on `2026-10-14` to `2026-10-15` from COPIES, made share-mode, of the five run directories and the report in `F:\trading bot\backtest\67b7563de683` (the S5 clone), which is read only; nothing was written there. The S4
clone was not touched and no venue call of any kind was made. Predictions: `predictions_halts.txt` (SHA-256 `e64abc611dffde0b18f276ea471adaf921f02599fc67e75bd18bad3c52b02b76`, before any halt or measurement) and
`predictions_c1.txt` (SHA-256 `7e7a746e982a094024fde98acc639b643291361d36ccfeb61c37dd85eeb9cef2`, before the documents).

### The clone and its runs

The clone is a deployment clone of `67b7563de683cb64f500f0a0d2264f93e7f9089e`, with its own venv and a VCS install. Its `boot_provenance` line, from the 0.05 arm's log at `2026-10-14T07:00:04Z` (pid 24584), reads
`verdict=accepted`, `install_kind=vcs`, `code_intact=true` over 80 files, `code_commit=67b7563de683cb64f500f0a0d2264f93e7f9089e`, `checkout_dirty=false`, `commits_agree=true`,
`config_sha256=f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`, `config_tracked=true`, Python 3.12.10. Every record below carries `schema 6`, `evidence_eligible` true, empty `problems`, and a `protocol` block
(`entry_id` `s5-baseline`, `kind` `baseline`, `window_class` `straddling`, `protocol_sha256` `79dfc4fde9707101e83f26ba258d3380714d68d4eb6079f9bbdc745bf5b0d032`).

| Directory | What | Started to finished (UTC) | Wall | Trades | `run.json` SHA-256 | Trade-log digest the record carries (its directory name's suffix is this digest's first 12 characters; it is NOT the SHA-256 of `trades.csv`, which is in the Files table) |
|---|---|---|---|---|---|---|
| `20261014T065931721605Z-d2f44e62cf89` | smoke run, `2017-08-17` to `2017-08-20`, arm 1.20, `in_sample`, no entry needed | `06:59:31` to `06:59:42` | 10.56 s | 57 | `3629ef038e2d14ac5c7e98b0ee26edc27b00a552b2379a29f676a61f318093af` | `d2f44e62cf89c2ea7346a18e74163fd293c49d259521e2a74bbb349c72c700be` |
| `20261014T070004816981Z-6b9d3b8c7f89` | **Arm 1, stop slippage 0.05%**, `[2017-08-17, 2026-10-01)` | `07:00:04` to `10:41:27` | 13,282.98 s = 3.69 h | 62,796 | `36b7b1a6f09c34b2fc7ac03006b676eced720d30bba67021202cb9e71fa51a61` | `6b9d3b8c7f893b4b0307d20f48340e89138fc16b501494d9dc66e865870d968d` |
| `20261014T104541570489Z-e5111d9f08f7` | **Arm 2, 0.66%** | `10:45:41` to `14:17:54` | 12,733.30 s = 3.54 h | 58,237 | `c4f4fe39065cbc071e69ac00668b642ecf26386a294c3d3637abccfe475d7c0a` | `e5111d9f08f7fedcc874d6a43c61c54a68b2233c9270598ee872011b0ec1bb97` |
| `20261014T154834857585Z-failed` | **the aborted Arm 3 attempt**: `backtest.log` only, **no `run.json`** | `15:48:34` to `15:50:40` | 126 s | none | none | none |
| `20261014T155450267068Z-52e1f0448bc4` | **Arm 3, 1.20%** (the committed config, no flag) | `15:54:50` to `19:44:38` | 13,788.22 s = 3.83 h | 54,399 | `8837f2d074354e3382b7017e228364551e893978648bec265dd4931773a93e47` | `52e1f0448bc48e8263950fbc766db5652429e544c3957f63d4bfdbfbed3489df` |

**The aborted attempt (pid 17436).** Its log shows the boot, `Backtest ready` at `15:48:34Z`, simulated time reaching `2017-09-15T03:54:59Z`, then `Trading engine stopped event=engine_stopped clean_shutdown=False` and
`ERROR ... Backtest aborted: KeyboardInterrupt` at `15:50:40Z`: the owner's Ctrl+C. **That is 126 seconds after the start, not the 35 the prompt of P115 states**; the directory was sealed `-failed` by the command and holds
no record, so the guard did not count it (`local_reads` reads `run.json` only) and the arm was rerun six minutes later. The three arms ran sequentially, as M5m-339 replaced the parallel option.

**The report.** `s5_report.txt`, 34,176 bytes, written `2026-10-15 01:45:41` local = `2026-10-14T19:45:41Z`, one minute after Arm 3 finished, SHA-256 `6b73bc8bb9bbdc339c3c81d6ef46a36ceb144703436931f76429756fa7e02bb1`.
**It is UTF-16LE with a byte-order mark**, because the step that wrote it redirected a native command's output in Windows PowerShell 5.1; it reads as text only when decoded as UTF-16, and a `grep` or `Select-String`
for `PASS` over it would find nothing whether or not the word were there.

### The report's figures, in sample and out of sample, as printed

| | 0.05% | 0.66% | 1.20% |
|---|---|---|---|
| in sample: trades / net P&L / gross P&L | 47,358 / -9390.12 / -2970.52 | 47,358 / -9520.56 / -3695.81 | 47,358 / -9612.50 / -4251.89 |
| in sample: profit factor net / gross | 0.3779 / 0.7040 | 0.3360 / 0.6213 | 0.3007 / 0.5542 |
| in sample: net per-trade return, mean (95% interval) | -0.2961% (-0.3034, -0.2888) | -0.3219% | -0.3446% |
| in sample: equity from 10,000 to | 609.85 | 479.42 | 387.48 |
| **out of sample (a straddling run's section): equity from / to** | 609.85 / 255.46 | 479.42 / 255.21 | 387.48 / 255.11 |
| out of sample: trades / net P&L / profit factor net | 15,438 / -354.42 / 0.2721 | 10,879 / -224.23 / 0.2711 | 7,041 / -132.38 / 0.2634 |
| out of sample: max drawdown of DAILY CLOSES | 0.5811 | 0.4677 | 0.3416 |
| whole run: per-bar max drawdown (R-AJ) | 0.9745 | 0.9745 | 0.9745 |
| **S7 PREVIEW, recorded under R-BW as not S7's figures:** regimes with net P&L > 0 | 0 of 3 | 0 of 3 | 0 of 3 |

### P115 Step 1: measurements over the copies, each against its prediction

**1a. The sizing floor** (`step1a.py`, SHA-256 `89ca9d9189263715b38969e723935521d5195ceb953957473a30dec517093396`; output `step1a_out.txt`, `b24f7ea890b3e59d695d0777e9bc3ba40ca471ed26db318eb8d45f639d426090`). Every risk-stage refusal in the
logs is one of two: a `CLOSE` refused `nothing_to_close` (no entry; in sample 1,312 BTC and 1,597 ETH, the same in every arm) and a `BUY` refused `size_not_tradeable`, whose reason reads *"no trade (fixed_fraction): notional
# at # below min_notional #"*. There is no in-sample `size_not_tradeable`. The other entry losses are the 876 fill-time FOK refusals the executor counts (`entries_refused`, price above the limit), found as BUY intents with no
trade row (877 in Arm 1: the 876 and the one ETHUSDT position still open at the end), and the 41 `buy_refused_bars_gap` events, all before the boundary (none in the window). **The out-of-sample BUY signals number 20,242 in
every arm** (approved plus refused at the sizer, a check that the three logs agree).

| Quarter | 0.05%: approved / refused / quarter-end equity | 0.66% | 1.20% |
|---|---|---|---|
| 2024Q1 | 1850 / 0 / 551.54 | 1850 / 0 / 431.84 | 1850 / 0 / 348.10 |
| 2024Q2 | 1866 / 0 / 494.60 | 1866 / 0 / 386.65 | 1866 / 0 / 311.41 |
| 2024Q3 | 1851 / 0 / 447.00 | 1851 / 0 / 348.30 | 1772 / 79 / 281.71 |
| 2024Q4 | 1832 / 0 / 405.92 | 1832 / 0 / 315.68 | 850 / 982 / 268.41 |
| 2025Q1 | 1777 / 0 / 367.18 | 1564 / 213 / 288.23 | 500 / 1277 / 259.46 |
| 2025Q2 | 1818 / 0 / 331.91 | 1260 / 558 / 267.56 | 148 / 1670 / 256.26 |
| 2025Q3 | 1839 / 0 / 300.21 | 202 / 1637 / 264.22 | 15 / 1824 / 255.96 |
| 2025Q4 | 1624 / 244 / 272.10 | 250 / 1618 / 259.05 | 22 / 1846 / 255.48 |
| 2026Q1 | 603 / 1234 / 262.01 | 104 / 1733 / 257.38 | 8 / 1829 / 255.34 |
| 2026Q2 | 278 / 1557 / 256.80 | 79 / 1756 / 255.48 | 9 / 1826 / 255.13 |
| 2026Q3 | 101 / 1768 / 255.46 | 21 / 1848 / 255.21 | 1 / 1868 / 255.11 |
| total | 15,439 / 4,803 (23.73%) | 10,879 / 9,363 (46.26%) | 7,041 / 13,201 (65.22%) |

"Approved" counts BUY intents dispatched; the refused column is `size_not_tradeable`. First refusal: **Arm 3 `2024-09-19T14:11:59Z`** (BTCUSDT, notional 4.95858 at 61,982.25), **Arm 2 `2025-01-31T21:42:59Z`** (4.9980825 at
99,961.65), **Arm 1 `2025-10-02T20:14:59Z`** (4.7354008 at 118,385.02). The lowest daily-close equity in any arm is **255.11** (Arm 3, `2026-09-25`), so no arm's account ever closed a day below 250. **The floor is price-dependent
and above 250** (`step1a_floor.py`, `5ea68c0cfcefa266d60e801271478a4fc4ac41824afdaf1edee04ea7893bae14`, output `db70d590472604e97499bf510e70e9f84e6b2c16a353523ae5f2c272c20f445e`): the BTCUSDT lot step is 0.00001 and the minimum
notional 5, so a 2% entry is untradeable below `ceil(5 / (price x 0.00001)) x 0.00001 x price / 0.02` of equity, which is 295.96, 299.88 and 278.92 at the three first refusals, 270.00 at a price of 60,000 and 250.72 at a 2017
price of 4,322.71. The refused notionals are 4, 5 and 8 lots of 0.00001. Trades kept being entered after the first refusal (2,569, 2,868 and 1,708 in the three arms), small ones, while the equity decayed toward the floor.

**1b. Gross against net, in sample** (`step1bc.py`, SHA-256 `24fc7e1b5f2f6d503fe6f93cfd165aafb5a4b5a6b9ba2973b75541f3c8cc74e7`; output `step1bc_out.txt`, `cafe96a858a08b2548554a7fffe40e7ec7905736a89a01181061d1e7247a4097`).
The instrument is proved against the report: Arm 1's in-sample net mean -0.2961% with the interval (-0.3034, -0.2888) over 47,358 trades is the report's own. A trade's gross result is `exit_gross - entry_notional`, its net result
`realised`, and a return is the result over the entry quote total in percent.

| In sample | 0.05% | 0.66% | 1.20% |
|---|---|---|---|
| gross win rate | 24.97% (11,825) | 24.97% (11,825) | 24.97% (11,825) |
| net win rate | 15.37% (7,279) | 15.37% (7,279) | 15.37% (7,279) |
| gross mean return (95% interval) | -0.0964% (-0.1037, -0.0891) | -0.1222% (-0.1293, -0.1150) | -0.1450% (-0.1521, -0.1379) |
| net mean return | -0.2961% | -0.3219% | -0.3446% |
| gross P&L / net P&L | -2970.52 / -9390.12 | -3695.81 / -9520.56 | -4251.89 / -9612.50 |
| profit factor gross / net | 0.7040 / 0.3779 | 0.6213 / 0.3360 | 0.5542 / 0.3007 |

The three arms hold the SAME 47,358 trades: symbol, signal bar, entry bar, exit bar, exit kind and exit time are equal row for row, and the entry price too; the quantity differs in 47,350 rows (the equity paths differ) and so do the
exit prices. **The census of record** (the capture whose SHA-256 is `3f7f551cf5c20d62e38cbe789a297f1db0d1871a99388d88e3f3f0f6db797528`, section 19 of this ledger: 165 Testnet bookings in 21 days) gives, gross of fees: all bookings win rate
34.5%, mean -0.0641% (95% interval -0.2223%, +0.0941%), profit factor 0.75; strategy `CLOSE`s only (154) win rate 35.1%, mean +0.0050% (-0.0602%, +0.0702%), profit factor 1.04; protective legs only (11) win rate 27.3%, mean
-1.0320%. The backtest's `CLOSE`-only in-sample figures are a gross win rate of 24.13% and a mean of -0.1301% (-0.1349, -0.1253), below the census interval's lower end of -0.0602%; the backtest charges 0.05% slippage on each
side of a trade, which would account for about 0.10 of that 0.13 and is a reasoned attribution, not a measured one.

**1c. Exits in sample by kind** (the same script and output; the counts and the `CLOSE` figures are equal in all three arms):

| Exit kind | Count (share) | Net mean return, 0.05% / 0.66% / 1.20% | Gross mean, same order |
|---|---|---|---|
| `close` | 45,370 (95.80%) | -0.3298% / -0.3298% / -0.3298% | -0.1301% / -0.1301% / -0.1301% |
| `stop_loss` | 1,109 (2.34%) | -2.1676% / -2.7647% / -3.2932% | -1.9698% / -2.5674% / -3.0965% |
| `take_profit` | 879 (1.86%) | +3.8020% / +3.1685% / +2.6077% | +4.0058% / +3.3717% / +2.8103% |

No stop was a winner (0 of 1,109) and every take-profit was (879 of 879). The take-profit mean falls as the arm's slippage rises, as it must: `stop_slippage_percent` applies to both protective legs (the committed config's own
comment).

**1d. The frozen `down_intervals`** (`scripts/s4_compare.py` line 536, `resumed = first_pass.get(after, first[after])`), over section 49's log copy (SHA-256 `3af6327d3cae1616a0882dff9f9d1f331cc9706a74470d1db1271ba6a50ae5da`):

| pid | first line | first `reconciliation_pass` | last line | the interval before it ends at |
|---|---|---|---|---|
| 27460 | `2026-10-10T05:58:02Z` | none | `05:58:02Z` | its first line |
| 27176 | `05:58:16Z` | none | `05:58:17Z` | its first line |
| 16076 | `06:05:20Z` | `06:48:00Z` | `2026-10-12T04:17:43Z` | **its first pass**, 42 min after its first line |
| 22304 | `2026-10-12T19:17:35Z` | `19:20:01Z` | `2026-10-13T06:54:01Z` | **its first pass**, 2 min 26 s after its first line |
| 3444 | `2026-10-13T07:00:35Z` | none | `07:00:48Z` | its first line |
| 25352 | `2026-10-14T06:34:32Z` | none at the copy | `06:34:37Z` at the copy | its first line, at the copy |

**The rule the code applies: an interval ends at the next process's first reconciliation pass if it logged one, and at its first line if it did not.** It is in the function's docstring too. **`M5m-301`'s text** (the commit
message of `af51911`) named the pass branch and its REASONED effect after a restart with no open position, and omitted the first-line branch: it was incomplete, not wrong, and the 49.7-minute and 902.3-minute intervals it
and sections 43 and 46 describe are the pass branch at work. **Section 49's sentence** that the function "ends an interval at the next pid's FIRST line" described the no-pass branch alone, true of pid 25352 at the copy
because it had no position to reconcile; **the interval it quotes, ending `06:34:32Z`, will end at pid 25352's first pass in any later copy** (not re-run: the S4 log was not touched). The P114 H6 prediction that the figure
"extends past 06:34:37Z" was therefore the effect of a pass the process had not yet logged.

### Files

| File (under `F:\trading bot\scratch\p115\` unless named) | SHA-256 |
|---|---|
| `predictions_halts.txt` | `e64abc611dffde0b18f276ea471adaf921f02599fc67e75bd18bad3c52b02b76` |
| `predictions_c1.txt` | `7e7a746e982a094024fde98acc639b643291361d36ccfeb61c37dd85eeb9cef2` |
| `gate_h3.txt` | `54d2933a064e4b9c5a715077e8ce1d512bd94aaef4534a884789355d03cde3ef` |
| `findings_h4.txt` | `5f18db4c6f794c085d9dbc954ad4a7de9dd065da601e98494553c09473ac0b4c` |
| `s5_report.txt` (UTF-16LE) | `6b73bc8bb9bbdc339c3c81d6ef46a36ceb144703436931f76429756fa7e02bb1` |
| `runs\...\backtest.log`, Arm 1 / Arm 2 / Arm 3 / aborted / smoke | `970168f8dc4f94a4a4279c483bef2accc544a3b19861cc418577deb692d0c1b1` / `db0ef80810bc5a6c977d82d85bb5055951eb843f71e21a5f08d805ed9307bf21` / `9b897b70690baf8a0366526971f543ea18160991b6368251d3d1ea68a95df930` / `6f78642cf83eab166828608c16fde14e773024e993192942cf9c8ddd525d3925` / `61768a1ea3deba91b5cec444d35f254a0ace6fbee7280d51064c77d9755ea10e` |
| `runs\...\trades.csv`, Arm 1 / Arm 2 / Arm 3 | `1f8fc37c7df5b5534fa97529b73a28bd9f5186c5e125b9730ab80aad891f648b` / `d35838a74ee2faf915da4988a3a05dcecccc681ac2ee38fc7132911ff3fafb97` / `4c54d6e6a89c41c3a710383a71182860fcdbcc74cf3f574aec6be278ee53b1c8` |

## 51. M5m S6/S7: Phase 1's measurements (P116) and the tooling built to carry S6 out (P117 C8)

Read only on the canonical store (`F:\trading bot\store\mainnet-historical`) and on the share-mode copies of S5's runs; no run was made, no record was written, no venue call. The S4 clone and the S5 clone
were not touched. Every scratch file below is under `F:\trading bot\scratch\p116\` (the measurements) or `p117\` (the build).

### Part 1. What P116 measured

| Measurement | Result | File, SHA-256 |
|---|---|---|
| The untradeable-equity floor of a 2% entry, BTCUSDT and ETHUSDT at 1h, 4h and 1d, in and out of sample | at most **312.29 USDT** of equity over the stored history (BTCUSDT near 124,918), 281.19 in sample; ETHUSDT at most 272.70. The configured 10,000 survives a 95% drawdown with 500 left; the floor binds past a 96.9% drawdown (97.2% in sample) | `p1_floor_out.txt` `a861f1239ec03462770194cb4e367ddb98087842b644db748a0341034788923c` |
| Entry counts of the 216 variants, in sample, from the repository's own indicators and the strategy helpers' crossing definitions | by buy-edge count 97 of 216 can reach 100 entries (78 by a replay in which only the strategy's CLOSE exits), 69 reach 232 (43); three of twelve cells (1d `sma_crossover` off and on, 1d `rsi` on) cannot reach 100; at 1d only 6 of 72 reach 100 and none 232 | `p1_signals_out.txt` `0ed4ad6717f941bc4044740b6f3afa4d12aa7126e2cb93a83b260887744edb68`, `p1_variant_counts.csv` `a156ba6844cdf091b55f32c84fadf2b63b0cd246116f22c502b950572c2ce07d` |
| The vectorised counts against the REAL strategies on the engine's 1000-row buffer | 0 BUY and 0 CLOSE mismatches over 5 variants of 3,000 bars (BTCUSDT 1h, bars 1000 to 4000) | the same file |
| `generate_signal` per call on a 1000-row buffer | `sma_crossover` 603 to 771 microseconds, `rsi` 1,901 to 2,099 | the same file |
| S5 Arm 3's net profit factor in USDT against on per-trade returns, in sample | 0.3007 against 0.2724; the mean entry quote total falls from 182.33 (2017) to 9.70 (2023) and 2017 and 2018 carry 56.4% of the absolute net result | `p1_thresholds_out.txt` `5a7d4302b4a776a23d15dde91857114c71d16e6559750db6a86f19525f3b10eb` |
| The window ratio | 1,004 out-of-sample days to 2,328 in-sample: 100 out-of-sample trades is about 232 in sample at a constant rate | the same file |
| All 216 variants through `build_overrides`, `apply_overrides`, `effective_settings` and the guard | 216 of 216 return as themselves, 216 distinct candidate digests, both pairs at the variant's timeframe, balance 10,000; the timeframe override sets `risk.max_position_staleness_s` to 14,400, 57,600 and 345,600 s at 1h, 4h and 1d | `p1_roundtrip_out.txt` `d2548217b54d5bfea1afe2346ac0481e54666505a370190f2a9b6766ccca4d40` |

The per-bar cost at 1h, 4h and 1d is DERIVED and not measured, because measuring it needs a run that writes a record: S5's engine spent 2.408 ms a bar (13,788.218 s over 5,725,299 bars), so about 1.8 ms is not
the strategy. Derived single-process time: about 10.2 h for the 216 in-sample runs at one arm, 30.6 h at three, up to 1.8 h for 36 out-of-sample runs. Peak memory, parallel speed-up and the effect of trade
density are UNMEASURED; the owner's timing probe (O2, `scripts/s6_sweep.py --probe`) measures the first and the sweep's first minutes the others.

### Part 2. What P117 built, in the order it was committed

| Commit | What | Gate after it (ruff format / mypy / pytest passed) | Survey |
|---|---|---|---|
| `66f64ce` C1 | `PROTOCOL.md` amendment 2: R-CA to R-CJ verbatim, the return profit factor and its tie-break, the ruin rule (0.95), the 250-trade minimum, the walk-forward report, the freeze, S7's two profit factors; `min_in_sample_trades` 250 | 196 / 100 / 3791 | 3 mutations, 1 + 1 + 0 kills, as predicted (`survey_c1_out.txt` `aecd27a3deabadd854cf439147dca9197185d6e1fa30eb2bbde5a86d3ba94779`) |
| `8bee34c` C2 | R-CI: the baseline tests select the entry by id | 196 / 100 / 3791 | 4 mutations over two specs, all as predicted (`survey_c2a_out.txt` `6ed4f8787a53c788505d11916da873ea4fb354e18cb6f21be9116fb57bdc0bfa`, `survey_c2b_out.txt` `ec043fc6afbdf84f446f26233bb3ddb02d793278a5c01cd540c2945175cd6c16`) |
| `35d6b38` C3a, `d96045b` C3b | `backtesting/selection.py` (split: 1,880 lines would exceed the ceiling), 99 tests | 199 / 101 / 3844, then 200 / 101 / 3890 | 14 mutations, 35 of 35 predicted kills (`survey_c3b_out.txt` `eee2aedad5357ad6f5dd3591f60040196b057960604f64291be0fd05f44bd889`) |
| `119b25c` C4 | `scripts/s6_select.py`, 18 tests | 202 / 102 / 3908 | none asked |
| `6b26c97` C5 | `scripts/s6_sweep.py`, 30 tests, the `-running` rule in `read_run` | 205 / 103 / 3940 | 5 mutations of R-CH's check and the order, 9 predicted, 10 observed (`survey_c5_out.txt` `33ec22cddcc861b9dfd252bbc21308ab9c2ccf37ceb7d5cb9fab382c9e6793cf`) |
| `9fd2e2e` C6 | the CLI pin: the engine's own in-sample record names its variant and reads back through `read_run` | 205 / 103 / 3943 | none asked |
| `4dc445a` C7a, `8e17898` C7b | `backtesting/gate.py` and `scripts/s7_gate.py`, 106 tests | 208 / 104 / 4034, then 210 / 105 / 4049 | 27 mutations, all as predicted (`survey_c7_out.txt` `508de21237d9f50cd76f2e1ab00b953ac24cd407492342235dcb0034d48c04df`) |
| `a417700` C7c | the probe times both strategies; the selection refuses another protocol digest | 210 / 105 / 4052 | 2 mutations, as predicted (`survey_c7c_out.txt` `60464fe9426cd20d1bbd3ba6a620ae029da1243513ca8dfc26e908cdc86bc46e`) |

Credentialed gate throughout (the venue answered 200); the uncredentialed figure is DERIVED as three fewer passed. **The chain sweep, selection, entries, out-of-sample reads and gate has never run as one**:
each hop is tested against fixtures, and two faults (C7c) sat on the seams between hops.

## 52. M5m S6/S7: the rehearsal of the whole chain, in a throwaway worktree (P118, R-CK, R-CL)

Read on `2026-10-15` from files under `F:\trading bot\scratch\p118\` (outside the repository) and from the run directories of throwaway worktrees that no longer exist. **Nothing from the rehearsal is committed to `docs/research/`, `docs/research/PROTOCOL.md` was not edited, no S6 record exists outside a throwaway worktree, the S4 run and the S5 clone were not touched, and no venue call of any kind was made** (the `backtest` command asks for no credential, and an existing test pins it). The development tree's `git status --porcelain` was empty at H2 and after every commit. The canonical store held 1,126 files and 1.1 GB before and after every cleanup.

The owner's rulings, verbatim. **R-CK:** *"M5m-376, M5m-377, M5m-385 and M5m-405 are ratified as implemented."* **R-CL:** *"Before any S6 run, the whole chain is rehearsed end to end over a narrowed protocol, with the real engine, in a throwaway worktree: sweep, selection, entry writing, out-of-sample runs at all three arms, and the S7 gate, in both a passing and a failing case. Nothing from the rehearsal is committed to docs/research/."* The prompt's constraints, verbatim: *"You do not push; the owner does. No S6 record is written anywhere outside a throwaway worktree. The S4 run is live and the S5 clone is read only: touch neither. No venue write. docs/research/PROTOCOL.md is not edited: if the rehearsal shows it must change, HALT and report."* **The rehearsal showed no need to change PROTOCOL.md.**

### The halts, against their predictions

Predictions were written to `predictions_halts.txt` (SHA-256 `ae306c9aec1a754a94ab14225f54fbf8d30bdded6efb57832e4e36d8e854f71d`) before any halt ran.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `9d6d519`; the owner has NOT pushed P117, so `origin/main` is `09d697d`, 0 behind, 11 ahead | **WRONG.** The owner had pushed: HEAD and `origin/main` are both `9d6d519`. (The prompt's own conditional, "`9d6d519` for both if the owner has pushed", held.) |
| H2, `git status --porcelain` | empty | empty |
| H3, the gate, bare, to a file | ruff clean, 210 files, mypy 105, pytest 4052 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `248228e8b72db05ff189d802e0ef9bc385ae391c6f49069c75ee5b24d99a3547`) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 430, distinct 430, max 430, no duplicate, no gap, no cited-not-declared, blockless `934eb45`, exit 1 | as predicted |

### The feasibility probe, before any script existed

A throwaway worktree at `9d6d519`, with its own `.venv`, `pip install -r requirements.txt` (about 49 s), a non-editable install by commit from the worktree's own path (`git+file:///F:/trading%20bot/...@<sha>`, about 25 s) and a junction to `F:\trading bot\store\mainnet-historical`, booted `strategies` with `verdict=accepted`, `install_kind=vcs`, `commits_agree=true` and a clean `git status`. **A commit made inside the detached worktree could be installed by its new SHA, but only with `pip install --force-reinstall --no-deps`: a plain `pip install` of the new commit into a venv that already holds the package exited 0 and kept the OLD commit, and the boot then read `verdict=refused`, `commits_agree=false`** (`M5m-438`). The owner's step O5 builds a NEW clone and a new venv and is not exposed. The probe's worktree was removed and the store counted: 1,126 files before and after.

### Every invocation, in order

`python -u scripts/s6_rehearsal.py --root F:\trading bot\scratch\p118\rehearsal --store F:\trading bot\store\mainnet-historical` with the flags shown. Windows are in sample start / boundary / out-of-sample end. "Matched" counts hops that did what the predictions file (`predictions_rehearsal.txt`, SHA-256 `b0ad872df6115ffe350c778f0d8136ef50452d69316e7c24cdad0848376148ac`, and its addendum `97dfae0a892f07b1fb195f498e1dd27b2d7de21dbdf71f673d5aff3dfe3abc77`) said.

| Invocation | Window | Code (HEAD) | Result | `hops.jsonl` SHA-256 |
|---|---|---|---|---|
| run 1 (no label; `--case both` reached the pass case only) | 2023-12-01 / 2025-01-01 / 2025-04-01 | `2f44ae2` (C1b) | 46 of 47 hops matched. Hop 47, the gate: both candidates FAIL (the quarter is labelled sideways and both lose in it). **DATA**, predicted as possible | `3d4e96116650dc87afabd07fadab04673b153c3a287f47909a644e4a31f1910c` (copied before its `--clean-only`) |
| run 2, `run2-q1-2024` | 2022-12-01 / 2024-01-01 / 2024-04-01 | `62c21ae` plus the uncommitted `--window` flag | 46 of 47. Hop 47: the unfiltered candidate PASS (+3.19), the filtered FAIL (-5.76). **DATA** | `c3b0bde69f2426308953d5e676c8373c79aa3077e89bf5db30fed48077aeaff1` |
| run 3, `run3-q1-2021` | 2019-12-01 / 2021-01-01 / 2021-04-01 | `62c21ae` plus the same flag | 10 of 11. **Hop 11, the sweep: SEAM FAULT**, two backtest workers read one stamp (`93e98e7`, `M5m-444`) | `9f07f2b1b6bb415715d0afa70165735d2e56fd6bfa4e075b10fe324a24334512` |
| run 4, `run4-q1-2021` | the same | `93e98e7` (C2b) | 46 of 47. Hop 47: both FAIL (regime nets -16.82 and -22.00). **DATA** | `db1282481bbc1a12f2d845af843be94dd06feed108cc24313b21431988764235` |
| run 5, `run5-q1-2023` | 2021-12-01 / 2023-01-01 / 2023-04-01 | `93e98e7` | 46 of 47. Hop 47: both FAIL (-15.34 and -30.88). **DATA** | `474d7e33f7ed1894d2209633c7f1a11d2f31bd26b35c8ca779c35d3ff1932698` |
| the quarter scan, `scan` | 28 single quarters, 2018 Q1 to 2024 Q4, all in sample of a boundary at 2025-01-01 | `93e98e7` | 70 hops, each a backtest or a setup or cleanup step, all matched. **It read 2024 quarters, which the REAL protocol reserves** (`M5m-447`) | output `scan_quarters_out.txt`, SHA-256 `175ec0ec1003d89449e02607e8971ab7314cf4041c6fba583828fd6758e53451` |
| `final1` | 2018-12-01 / 2020-01-01 / 2020-04-01 (the C2c default) | `d198631` (C2c) | 46 of 47. Hop 47: unfiltered PASS (9 trades, 2.7437), filtered FAIL: four winners and no loser, so its profit factor is undefined and the gate fails closed (`M5m-451`). **DATA** | `3131d78719cb6d3b19bbeece6e48e34b7e0a5f2bf6a5f58cfd5517aeba4e659e` |
| run 6, `run6-y2020`, `--case pass --window 2018-12-01 2020-01-01 2021-01-01` | 2018-12-01 / 2020-01-01 / 2021-01-01 | `d198631` | **51 of 51 matched**, cleanup included. Both PASS | `f5384ec6d97ca53f74e1004a296608b8479222a350286195566bc0ae360c08b1` |
| **`final2`, the final run, no `--window`, both cases** | the C2d default, the same as run 6 | **`da094f8` (C2d)** | **102 of 102 hops matched, 51 in each case, cleanup included** | pass `592dce40982369ccc0b61608cfd8dbddf4333b38328bd670255eb4c6d34a7c78`; fail `3b0964bb56efc169523d25d41ad3554cc05411ae24d6bf00d813c4666fc777eb` |

Every kept worktree was removed by the script's own `--clean-only` (hops 48 to 51 of its case, numbered after the run's from C2a on). Console output of each invocation: `rehearsal_run1.txt` `23580b4f9e7ea13ebb79808eb84b0f586c94edc0e461637f98a9ec43c562edb8`, `rehearsal_run2.txt` `53541c68d186e209c87d12b08e5335d4359ed8d3215cb5805defdabf38a8d553`, `rehearsal_run3.txt` `669f30bcbe50803f77de7f5d3bbd11047a7a42cb6043897dadcb5d2232de41be`, `rehearsal_run4.txt` `c5de73115cb0393345a3993e202cb6b8d782e14f3fb08120817b04ff2809321a`, `rehearsal_run5.txt` `1ea4528df1e09195df840055b8a5fd774e2089a1df9ce6684ee3ca204c4f4b44`, `rehearsal_run6.txt` `51fdb9e312c59576bb77f52ad8c925291edcc9ee6946c5dd0c329c4bc33f54a0`, `rehearsal_final1.txt` `307bb4a9a5350ab1881cda2c9534929563c3dca121f0d601b250e1ca853e83a8`, `rehearsal_final2.txt` `649a4018315f066ad293cc9483dc605d17e18387bdafa360d0ad9ea70318f75b`.

### What is a fault and what is data

**Two seam faults, each fixed in its own commit with a test that fails on the old code.** (1) **`93e98e7`, `main.py`:** the `backtest` command named its working directory by a microsecond stamp, the Windows clock ticks coarser than that, and two workers started together (R-CH's own parallel check) read one stamp; the loser died on `FileExistsError` after its guard, exit 1, no record (`M5m-444`). A run claims its directory with an atomic `mkdir` and, if it loses, reads the clock again. (2) **`62c21ae`, the rehearsal script:** its hops were numbered from 1 whatever the case's directory held, so a `--clean-only` after a run repeated the run's first four numbers; nothing was overwritten (`M5m-441` corrects what I first thought). **One fact about the owner's steps, no fault in the repository:** a plain reinstall of a new commit into a venv that holds the package keeps the old commit (`M5m-438`).

**Five stops on DATA, none a fault.** The pass case's verdict is a property of the window, as the predictions file said, and the thresholds were never touched in any run. Runs 1, 4 and 5 stopped because both narrowed candidates lose in the window; run 2 and `final1` stopped because one candidate passed and one did not (`final1`: no loser). Run 6 and `final2` use a whole year because the gate needs a losing trade and a positive regime. `docs/research/PROTOCOL.md` was never edited.

### The final run, `final2`, at `da094f8`

Predictions: `predictions_final_run.txt` (SHA-256 `aedbcba78c1e4a661423b527fce869988a2c55f9338da908a34556ceb9982bc1`) and `predictions_c2d.txt` (SHA-256 `97c2854bace1dcf4f20a56178904cc79d433e173635a3a385142f3728183342f`), both before the run. Every hop matched, and the gate hop's revised prediction held: **pass case, `S7 SUMMARY: 2 of 2 candidates read PASS`; fail case, `S7 SUMMARY: 0 of 2 candidates read PASS`.** The in-sample trade-log digest of the unfiltered variant, `a1ad2dc2009e`, is the same in `final1`, `run6-y2020` and `final2`: three worktrees, three processes, one digest.

The sweep reported, in both cases, `variants declared 2; with a sealed evidence-eligible record 2`, `parallel check: the trade-log digests are equal`, exactly one DUPLICATED line (the check's probe variant) and `COMPLETE`, with no FAILED line. The selection reported `cells with a candidate 2 of 2`: the unfiltered cell, 57 in-sample trades, return profit factor 0.364063; the filtered cell, 22 trades, 0.473241.

**S7, pass case (thresholds lowered inside the narrowed protocol to profit factor 0.0001, 1 trade, drawdown 0.9999, 1 regime), gate arm 1.20, out of sample the whole of 2020:**

| Candidate | Trades | Return profit factor | USDT profit factor | Max drawdown (per bar) | Regime net P&L | Verdict |
|---|---|---|---|---|---|---|
| unfiltered | 53 | 1.035753 (2.270546 at 0.05, 1.493289 at 0.66) | 1.034942 | 0.004822 | rising -18.22, falling 0, sideways +23.16 | PASS |
| filtered | 36 | 1.042873 (2.301779 at 0.05, 1.507719 at 0.66) | 1.042095 | 0.003593 | rising -16.64, falling 0, sideways +20.84 | PASS |

**S7, fail case (the REAL thresholds: both profit factors at least 1.3, 100 trades, drawdown 0.20, 2 of 3 regimes):** both candidates FAIL with `NOT MET` on both profit factors (1.035753 and 1.042873; 1.034942 and 1.042095 in USDT), on the trades (53 and 36 against 100) and on the regimes (1 of 3); the drawdown test is met. The fail case's verdict, 0 of 2, was predicted.

**The two refusals, in both cases, were the real guard's:** the second read of an (entry, arm) printed `[local_prior_read] this clone already holds a completed record of entry 's6-sma_crossover-4h-off' at stop slippage 0.05% over the out-of-sample window; a candidate is read once per arm.` and exited 1; the read of an entry marked `read` printed `[already_read] entry 's6-sma_crossover-4h-off' has been read out of sample already (status 'read'); a candidate is read once.` and exited 1; each left the run directory list unchanged and the checkout clean. Hop times: 210.0 s (pass) and 204.1 s (fail), of which `pip install -r requirements.txt` is about 45 s and each of the three reinstalls about 13 s.

**Per-hop record, pass case** (`hops.jsonl` SHA-256 `592dce40982369ccc0b61608cfd8dbddf4333b38328bd670255eb4c6d34a7c78`; every row matched its prediction; "-" is a check made by the script, not a command):

| No. | Hop | Exit | Output SHA-256 | Seconds |
|---|---|---|---|---|
| 1 | `worktree-add` | 0 | `304ca28547d648feb37aac30737aa23058717135260b95c58df00625c4e6fc4d` | 0.2 |
| 2 | `venv` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 6.8 |
| 3 | `pip-requirements` | 0 | `7ab92d00f5f3912c95159ec91d366f4b0a709edcc4960a11596b2eee555abcf9` | 47.0 |
| 4 | `junction` | 0 | `12b14454ef481a6310e30f77ae6cfa861901dd8d96f7de6065367817ecd6cf9a` | 0.0 |
| 5 | `add-narrowed-protocol` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 6 | `commit-narrowed-protocol` | 0 | `cba34de9fa3330cbead9b275e0e77527814864975072f22fdfdc6477c8caf52e` | 0.1 |
| 7 | `install-by-commit` | 0 | `cc06c80a7a0fac128e7ffe5aff7ba11e9b7ec1cc66090bb8de80717b9f9e4704` | 14.1 |
| 8 | `boot-after-narrowing` | 0 | `b7b1153fe0668f32673d79969529555aec5113ea82ae41aca87f4b8aba4b7933` | 5.2 |
| 9 | `boot-after-narrowing-provenance` | - | `b7b1153fe0668f32673d79969529555aec5113ea82ae41aca87f4b8aba4b7933` | 0.0 |
| 10 | `boot-after-narrowing-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 11 | `sweep` | 0 | `6546455a2684e0fede35d714d066cb3a298bb445282340d9263f87c86ad358dc` | 32.8 |
| 12 | `status-after-sweep` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 13 | `select-report` | 0 | `6ac3bb33fefdcce79b9390c67eed7c6a45f6a3e6ecafbd4c673abc3e0c364725` | 0.3 |
| 14 | `select-has-candidates` | - | `6ac3bb33fefdcce79b9390c67eed7c6a45f6a3e6ecafbd4c673abc3e0c364725` | 0.0 |
| 15 | `status-after-report` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 16 | `select-write` | 0 | `21f211176f9bfd3034f6f03209286fee355dec6203b0ad9dbe2c2aab52d53bbd` | 0.3 |
| 17 | `select-entries-match-report` | - | `21f211176f9bfd3034f6f03209286fee355dec6203b0ad9dbe2c2aab52d53bbd` | 0.0 |
| 18 | `status-lists-the-new-files` | 0 | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 19 | `status-holds-only-the-new-files` | - | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 20 | `add-selection` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 21 | `commit-selection` | 0 | `cafa0d2b9eda5ce36b0dec302082905f2e17d49377dcef518671f6cb63969279` | 0.2 |
| 22 | `install-at-entries` | 0 | `fcf0dbc68387a1e0ea0143faed189c3e335f684ee58a79957425b42ff3fd76dd` | 13.0 |
| 23 | `boot-at-entries` | 0 | `0bace2daae5e64893256cea2670365287e156bd6cfdef63ccc2715762d513fa4` | 1.0 |
| 24 | `boot-at-entries-provenance` | - | `0bace2daae5e64893256cea2670365287e156bd6cfdef63ccc2715762d513fa4` | 0.0 |
| 25 | `boot-at-entries-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 26 | `oos-s6-sma_crossover-4h-off-0.05` | 0 | `35218cbaa9da34ed6bf3a9d043b5c365206629483e3eadadcebbded1b31ff976` | 12.2 |
| 27 | `oos-s6-sma_crossover-4h-off-0.66` | 0 | `d03d12eeb66d0087ef83e0b4a7525e3be00fc1f41498f30118cf90017066b977` | 12.1 |
| 28 | `oos-s6-sma_crossover-4h-off-1.20` | 0 | `8144feaef9934aec61dfccfd17d972b4d6168eccc104de33c5a7392d61d9e869` | 12.0 |
| 29 | `oos-s6-sma_crossover-4h-on-0.05` | 0 | `cf1100ec9dff461c6cfeeb0e0e8ad81cd2c386dec39091da00cc65d30ca050f9` | 11.2 |
| 30 | `oos-s6-sma_crossover-4h-on-0.66` | 0 | `7e59223252eed99eedf722fabfda7b80e5038981f9f7aa67aa4ce52b75315e43` | 10.9 |
| 31 | `oos-s6-sma_crossover-4h-on-1.20` | 0 | `0687b27b237166d41e935bcc8115bd1835cfd4130a711e6f3e9bbee7a30b73c2` | 10.8 |
| 32 | `oos-records-s6-sma_crossover-4h-off` | - | `48b5657dcf2fc9c226a503cdfbbd55de4bf60302bb6bf7d9fe0f5f75e6fea02a` | 0.0 |
| 33 | `oos-records-s6-sma_crossover-4h-on` | - | `94c0b65e269c2cebf7b0ae9bdda440c7d3f863af3989b1aa69731108aeb58249` | 0.0 |
| 34 | `status-after-oos` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 35 | `second-read-same-arm` | 1 | `884285efd24382518dd47b8d6b5a582b884d7818b8e51f84b3c5ad6a22c06ebe` | 1.3 |
| 36 | `second-read-left-no-run` | - | `c3ce7e1ac8e17912fa2dcd3445930bb258328b51cf6263f8f6cf98af2fc96556` | 0.0 |
| 37 | `status-after-refusal` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 38 | `entries-marked-read` | - | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 39 | `add-read` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 40 | `commit-read` | 0 | `acc52bbf6bd2552760446d70b0f06830c25b1db6876db11ba7561e6b2bb3a76f` | 0.2 |
| 41 | `install-at-read` | 0 | `c8d47213eac9474009d10597bb59634c35c8edab496fc6978da9af1af9859166` | 12.8 |
| 42 | `boot-at-read` | 0 | `1cea6d18d3bcc127313e39d36bf43165a4650c87489e9b8d7eea6915f9e8fa96` | 1.0 |
| 43 | `boot-at-read-provenance` | - | `1cea6d18d3bcc127313e39d36bf43165a4650c87489e9b8d7eea6915f9e8fa96` | 0.0 |
| 44 | `boot-at-read-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 45 | `read-after-read` | 1 | `be1032a5e138ba963184e322152d2a83c841cfe3add3b041f6e5a6a3b3970a28` | 1.6 |
| 46 | `read-after-read-left-no-run` | - | `c3ce7e1ac8e17912fa2dcd3445930bb258328b51cf6263f8f6cf98af2fc96556` | 0.0 |
| 47 | `s7-gate` | 0 | `04141203527f33c17a03b6206da858c3981366cfdea5b3cc5c079934cd29d8b7` | 0.3 |
| 48 | `junction-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 49 | `junction-gone` | - | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 50 | `worktree-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 1.8 |
| 51 | `store-untouched` | - | `29eedcfc6ede3629c7bcb2b601fbefe3f8bed550701e1cb9def5c64bf59448d5` | 0.0 |

**Per-hop record, fail case** (`hops.jsonl` SHA-256 `3b0964bb56efc169523d25d41ad3554cc05411ae24d6bf00d813c4666fc777eb`):

| No. | Hop | Exit | Output SHA-256 | Seconds |
|---|---|---|---|---|
| 1 | `worktree-add` | 0 | `304ca28547d648feb37aac30737aa23058717135260b95c58df00625c4e6fc4d` | 0.2 |
| 2 | `venv` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 6.7 |
| 3 | `pip-requirements` | 0 | `7ab92d00f5f3912c95159ec91d366f4b0a709edcc4960a11596b2eee555abcf9` | 44.5 |
| 4 | `junction` | 0 | `a407994e863c263f4f24641d6943d603042ab0481eef8d7c641f900daa5965ba` | 0.0 |
| 5 | `add-narrowed-protocol` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 6 | `commit-narrowed-protocol` | 0 | `086f1e2e6ef97425c8b6e112669dbce424886e2c49fc2d01b0bd188fcdc91c21` | 0.2 |
| 7 | `install-by-commit` | 0 | `9d4c02d8ac7e4cc3a047ef4aaaa9438e166d9cc9cb4b79ae730cf5a9145ea7e4` | 14.2 |
| 8 | `boot-after-narrowing` | 0 | `abddb58e5c7a2a2b67d22280399a18c824e6342f04efc62ac67d454c66ce4a69` | 5.2 |
| 9 | `boot-after-narrowing-provenance` | - | `abddb58e5c7a2a2b67d22280399a18c824e6342f04efc62ac67d454c66ce4a69` | 0.0 |
| 10 | `boot-after-narrowing-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 11 | `sweep` | 0 | `fdd63c0c086aa11abffee189327ac1c1bc619a3173f7e75882b55053cfb26cfc` | 30.8 |
| 12 | `status-after-sweep` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 13 | `select-report` | 0 | `768f1bf76284d84f79b098fc5d7daf8fa4b2a957ce73984eb75c3e2477c819d2` | 0.3 |
| 14 | `select-has-candidates` | - | `768f1bf76284d84f79b098fc5d7daf8fa4b2a957ce73984eb75c3e2477c819d2` | 0.0 |
| 15 | `status-after-report` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 16 | `select-write` | 0 | `4e406ee0bf9a134ce927266ff6a9512a6357baa510ef054710ba14087f739e3b` | 0.2 |
| 17 | `select-entries-match-report` | - | `4e406ee0bf9a134ce927266ff6a9512a6357baa510ef054710ba14087f739e3b` | 0.0 |
| 18 | `status-lists-the-new-files` | 0 | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 19 | `status-holds-only-the-new-files` | - | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 20 | `add-selection` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.2 |
| 21 | `commit-selection` | 0 | `a26d44a9fe8414e95afaa0b94c472658c6b84aabed5fa1ba80aecde75bc2848c` | 0.2 |
| 22 | `install-at-entries` | 0 | `de35dd520fe39aac0b5ae5e5309f6179f2d0d4a5b91f6f0d537a1c63732ddf7d` | 12.8 |
| 23 | `boot-at-entries` | 0 | `f11458215cee6778aa08dac1d158c34b2753771bce986993af7c1d2d120b330c` | 1.0 |
| 24 | `boot-at-entries-provenance` | - | `f11458215cee6778aa08dac1d158c34b2753771bce986993af7c1d2d120b330c` | 0.0 |
| 25 | `boot-at-entries-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 26 | `oos-s6-sma_crossover-4h-off-0.05` | 0 | `996a24f3fc442e6bda12b9f2deb22b4680c5649c9c7e9491d74ec1da83154aa7` | 11.2 |
| 27 | `oos-s6-sma_crossover-4h-off-0.66` | 0 | `da07dd232da082aad83ee4d55ad15847a469b445be4710d028ee0c8c099dc7cc` | 11.0 |
| 28 | `oos-s6-sma_crossover-4h-off-1.20` | 0 | `be8b81a8a9bae06567e675cdbd744f94e942e28bbd5b559072ab887c60b39766` | 11.1 |
| 29 | `oos-s6-sma_crossover-4h-on-0.05` | 0 | `0ed1a67180f22fd33658bd05771ded1717ee172751ddc952d4940d1feae89f39` | 11.1 |
| 30 | `oos-s6-sma_crossover-4h-on-0.66` | 0 | `6e73f1cbf7993265e88492c7393ad87dfb944623b01c6451e89f75e7149e5752` | 11.3 |
| 31 | `oos-s6-sma_crossover-4h-on-1.20` | 0 | `2c240ba8f1e2c11638f520fb481d72b7e375ab2933f6e596454d90a3fd8f23fe` | 12.1 |
| 32 | `oos-records-s6-sma_crossover-4h-off` | - | `174d1f507c507487630a5cfc371aaa17e6233ba1e7031b05d5c3545ba592c9c0` | 0.0 |
| 33 | `oos-records-s6-sma_crossover-4h-on` | - | `eb4d0b3818040070f7fd9f7b46a88041c142dfde72e8a132de1f154b5ae104d6` | 0.0 |
| 34 | `status-after-oos` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 35 | `second-read-same-arm` | 1 | `47fc6e7e2942daac6f1be053e3284fe3bebaf4f286d8e59a0e0e6b389bd8876d` | 1.4 |
| 36 | `second-read-left-no-run` | - | `c53263b2ab3b7f49676ee48febec4ba2f3845295e0dc69bd54da2c1b78e2d03e` | 0.0 |
| 37 | `status-after-refusal` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 38 | `entries-marked-read` | - | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 39 | `add-read` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 40 | `commit-read` | 0 | `b523b596c61edb3b7a547a9ea2d92da9889e042d62e6bf68570c7614f5eb79af` | 0.2 |
| 41 | `install-at-read` | 0 | `94d1790ddaaecc3b86c4dd9cf53eb34000c367d9da98516b3f65c3d584b6809a` | 13.1 |
| 42 | `boot-at-read` | 0 | `5ac14f4212dbe8eb9f611b9badeddd30044268aa791347593e15740ef4f7edac` | 1.0 |
| 43 | `boot-at-read-provenance` | - | `5ac14f4212dbe8eb9f611b9badeddd30044268aa791347593e15740ef4f7edac` | 0.0 |
| 44 | `boot-at-read-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 45 | `read-after-read` | 1 | `715233be65afac2bc8bfa1b14c05a4194095a24366b9d8d4c8d08698ccae957c` | 1.6 |
| 46 | `read-after-read-left-no-run` | - | `c53263b2ab3b7f49676ee48febec4ba2f3845295e0dc69bd54da2c1b78e2d03e` | 0.0 |
| 47 | `s7-gate` | 0 | `64928fba643abb1482819de1f8f418871e258c7fde54d09a0c80b6d4b52e7aa7` | 0.3 |
| 48 | `junction-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 49 | `junction-gone` | - | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 50 | `worktree-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 1.9 |
| 51 | `store-untouched` | - | `29eedcfc6ede3629c7bcb2b601fbefe3f8bed550701e1cb9def5c64bf59448d5` | 0.0 |

### What the rehearsal did NOT cover

It used a `git worktree` where the owner clones from GitHub (O1); it ran the selection inside the clone where O4 runs it from the development checkout against `$CLONE\data\backtests`; it reinstalled in the SAME venv at the entries commit where O5 builds a NEW clone and venv; it used 2 workers where O3 uses 8; and its protocol had two variants, one timeframe and one family where S6 has 216 variants, three timeframes and two families (no 1h run, so no 1h memory or time figure, no `rsi`, no `--probe`, no kill and resume, no 12-cell selection with empty cells, no four-fold walk-forward). **None of O1 to O6's PowerShell was executed by the rehearsal.** After it, the glue of O6 (the entries read with `ConvertFrom-Json`, the argument array, the skip test and the table) and of O2 (the manifest read line by line) was run in PowerShell 5.1 against HAND-WRITTEN sample entries, records and manifest lines (`scratch/p118/o6glue/`): O6's argument array equals `oos_argv`'s command line for the same entry, the skip test skips arm `1.2` when asked for `1.20`, and the table prints; O2's line prints. **No tool marks an entry `read` (there is no O7);** the rehearsal does it inside `s6_rehearsal.py` (`mark_read`).

> **ANNOTATED AT M5m P119 (C4a): the sentence just above is a record of what the rehearsal of P118 did, and it is no longer true of the script.** *"No tool marks an entry `read` (there is no O7)"* has been false since
> `4a8ec1a` (`scripts/s6_mark_read.py`), and from C4a the rehearsal drives that tool and holds no `mark_read` of its own. The run of P118 is unchanged by it; the re-run at the new HEAD is section 53.

### The quarter scan

Not a result of S6: single quarters of the two narrowed variants at the 1.20 arm, run to choose a rehearsal window. Output SHA-256 `175ec0ec1003d89449e02607e8971ab7314cf4041c6fba583828fd6758e53451`. **It also read 2024 Q1 to Q4, which the real protocol reserves for S7 (`M5m-447`).**

| Quarter | Unfiltered: trades, net | Filtered: trades, net |
|---|---|---|
| 2018-01-01 to 2018-04-01 | trades 5 net -21.11 | trades 1 net -6.64 |
| 2018-04-01 to 2018-07-01 | trades 12 net -19.92 | trades 3 net +3.99 |
| 2018-07-01 to 2018-10-01 | trades 11 net -25.62 | trades 3 net -19.93 |
| 2018-10-01 to 2019-01-01 | trades 13 net -51.84 | trades 5 net -15.39 |
| 2019-01-01 to 2019-04-01 | trades 11 net -42.33 | trades 6 net -20.96 |
| 2019-04-01 to 2019-07-01 | trades 9 net -0.65 | trades 3 net +3.74 |
| 2019-07-01 to 2019-10-01 | trades 12 net -32.28 | trades 3 net +3.75 |
| 2019-10-01 to 2020-01-01 | trades 20 net -69.99 | trades 9 net -32.79 |
| 2020-01-01 to 2020-04-01 | trades 9 net +23.16 | trades 4 net +20.84 |
| 2020-04-01 to 2020-07-01 | trades 14 net -21.97 | trades 12 net -32.34 |
| 2020-07-01 to 2020-10-01 | trades 14 net +8.78 | trades 6 net +19.33 |
| 2020-10-01 to 2021-01-01 | trades 14 net -3.53 | trades 14 net -3.53 |
| 2021-01-01 to 2021-04-01 | trades 15 net -16.82 | trades 14 net -22.00 |
| 2021-04-01 to 2021-07-01 | trades 16 net -23.39 | trades 6 net +7.51 |
| 2021-07-01 to 2021-10-01 | trades 15 net -52.16 | trades 8 net -17.65 |
| 2021-10-01 to 2022-01-01 | trades 19 net -48.59 | trades 7 net -34.62 |
| 2022-01-01 to 2022-04-01 | trades 14 net -62.39 | trades 6 net -16.16 |
| 2022-04-01 to 2022-07-01 | trades 19 net -78.53 | trades 2 net -5.32 |
| 2022-07-01 to 2022-10-01 | trades 14 net -33.74 | trades 7 net -22.79 |
| 2022-10-01 to 2023-01-01 | trades 18 net -87.67 | trades 8 net -53.01 |
| 2023-01-01 to 2023-04-01 | trades 13 net -15.34 | trades 10 net -30.88 |
| 2023-04-01 to 2023-07-01 | trades 18 net -26.72 | trades 7 net -34.61 |
| 2023-07-01 to 2023-10-01 | trades 15 net -26.82 | trades 3 net -8.09 |
| 2023-10-01 to 2024-01-01 | trades 11 net -25.70 | trades 10 net -19.07 |
| 2024-01-01 to 2024-04-01 | trades 11 net +3.19 | trades 7 net -5.76 |
| 2024-04-01 to 2024-07-01 | trades 14 net -40.43 | trades 5 net -16.24 |
| 2024-07-01 to 2024-10-01 | trades 15 net -52.15 | trades 3 net -19.90 |
| 2024-10-01 to 2025-01-01 | trades 16 net -27.48 | trades 11 net -13.87 |

### The disclosure (`M5m-447`)

The narrowed protocol's boundary did not stop the engine reading the REAL protocol's out-of-sample period, because the guard judges against the protocol it is given; the two narrowed candidates are real grid points. Run 1 (2025 Q1, three arms, and an in-sample sweep over 2023-12-01 to 2025-01-01), run 2 (2024 Q1, three arms) and the scan (2024 Q1 to Q4, 1.20 arm) read 2024-01-01 to 2025-04-01 for `sma_crossover` 4h, 10/50, filter off and on. The figures seen are in `M5m-447` (commit `d198631`). **Every record was made in a throwaway worktree and is gone; no entry exists and no S6 run was made; the information is known to the implementer.** From `d198631` the script refuses a window that ends after the real boundary, whatever the narrowed boundary is. Whether the disclosure matters, and what to do about it, is the owner's to rule.

### The commits

`7f86953` (C1a, the narrowed protocol and the pure helpers), `2f44ae2` (C1b, the orchestration), `62c21ae` (C2a, the label and the numbering), `93e98e7` (C2b, the stamp collision in `main.py`), `d198631` (C2c, `--window` and the refusal of a real-out-of-sample window), `da094f8` (C2d, the default window), and this section's commit (C3). Gates: C1a 4078, C1b 4120, C2a 4122, C2b 4124, C2c 4133, C2d 4133 passed and 1 skipped, ruff format 212, mypy 106, each credentialed and bare to a file (`gate_c1a.txt` `c87234487d6c25d7f6ccec0cff1f78ccdcd24eaa216efc7e1ad342697b557871`, `gate_c1b.txt` `bbd42e0a789751f5c8f7af3dc648181a4abb3128a960327ef10b83232ad6fe40`, `gate_c2a.txt` `cde12ffd098716afd72bffe10491f257baf0a3f8304ca120e54a52291042ab12`, `gate_c2b.txt` `190b9865c9ab88caf66f00accf1dca50e37d9fdb26dd25e7c28b8acbaa3ff0e8`, `gate_c2c.txt` `eafdedba0bc99ede8ffd316228b638264967af4b7c59000e78e8f59157508333`, `gate_c2d.txt` `4e3af8a8181b7509a4885ed44f3d17b5a6189389130ececdae443795e14c0888`). Surveys (every mutation predicted in a file first): C1b 12 mutations / 25 kills (`d4f8c5fa1e9b8802594ac5d8964189d92dff3e7fd7751d3a3c17262bc42f8c0a`), C2a 4 / 8 after one HALT (`985b06e48eec64a831d12bc483d4163d9bece8760db1cc7ec17152d9ff49d1fa`, then `45df92a348d5ed4cec477cb9e956aaeafea57cbd4d47e158497cf66264e9e6b7`), C2b 4 / 6 (`7927baa872505472efcab3edaea393f9c288e915bd29fc0d5c942c170f21cb7b`), C2c 5 / 19 (`9fcd209273df74247f66418a4358c8fae4e288c810955a62b1479e7ef0727982`), C2d 2 / 8 (`e4c769479d3ae9d94f6a8f6d94b0755832d8fe2505c1027619c20c720146446e`). Findings `M5m-431` to `M5m-452` were declared in those commits, and `M5m-453` onward in this one.

## 53. M5m S6/S7: the rehearsal re-run with step O7 driven through the tool, at 365d767 (P119 C4, R-CP, R-CQ)

Read on `2026-10-15` from files under `F:\trading bot\scratch\p119\` (outside the repository) and from the run directories of throwaway worktrees that no longer exist. **Nothing from the re-run is committed to `docs/research/`, `docs/research/PROTOCOL.md` was not edited by it (amendment 3 was C1, `a03d5c9`, before any run), no S6 record exists outside a throwaway worktree, the S4 and S5 clones were not touched, and no venue write was made.** **R-CN held: every window of this run lies before 2024-01-01** (in sample 2018-12-01 to 2020-01-01, out of sample the whole of 2020), and the script refuses any other. The canonical store held **1,126 files before and after**, counted by `find` before the run and by the script's own `store-untouched` hop at the end of each case (`1126 -> 1126`).

The owner's rulings, verbatim. **R-CN:** *"No rehearsal, probe or test reads any bar at or after 2024-01-01T00:00Z, except an out-of-sample read under a committed entry. The rehearsal script refuses such a window."* **R-CO:** *"A junction is removed only with cmd /c rmdir. No recursive copy or delete (cp -r, rm -rf, Remove-Item -Recurse, Copy-Item -Recurse) is run on a directory that holds a junction, by hand or by script."* **R-CP:** *"Entries are marked read by scripts/s6_mark_read.py (owner step O7). It verifies each out-of-sample record through the evidence door and writes the three record digests into the entry; it refuses an entry already read, a record that fails the door, and a set other than exactly the three declared arms."* **R-CQ:** *"A sweep whose check lost a worker and then recovered the variant prints the loss and the recovery, and reports COMPLETE when every variant has a sealed record (M5m-445)."* R-CM is in `docs/research/PROTOCOL.md` amendment 3.

### The halts, against their predictions

Predictions were written to `predictions_halts.txt` (SHA-256 `38d792e283fffdcf9937e610b884e3415e8635e94e40c1ef6aedb0055a6572d7`) before any halt ran.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `7fec073`; the owner HAS pushed, so `origin/main` is `7fec073`, 0 ahead (else `9d6d519`, 7 ahead) | **WRONG, for the second prompt running** (`M5m-459`): `git ls-remote origin refs/heads/main` read `9d6d519`, the prompt's alternative |
| H2, `git status --porcelain` | empty | read as predicted at the time; **its output was not kept in a file**, so no digest exists |
| H3, the gate, bare, to a file | ruff clean, 212 files, mypy 106, pytest 4133 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `1f059bc05445ec0ef2b2fa29e50d1fb7755d0c8ed227e3f46205e823ad7fc4f2`) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 457, distinct 457, max 457, no duplicate, no gap, no cited-not-declared, blockless `934eb45`, exit 1 | read as predicted at the time; **its output was not kept in a file**. At this section's run the same command reads declared 475, distinct 475, max 475, no duplicate, no gap, no cited-not-declared, blockless `934eb45`, exit 1 (`findings_c4b.txt`, SHA-256 `0abf470505204752fc145a85d671c779912c29139ae0097b8332911d4f073cd6`) |

### The commits before the run

`a03d5c9` (C1: amendment 3, selection honouring R-CM), `4a8ec1a` (C2: `scripts/s6_mark_read.py` and `backtesting/readmark.py`), `13c780e` (C3: R-CQ in `scripts/s6_sweep.py`) and **`365d767` (C4a: the rehearsal drives O7 through the tool)**. The re-run is at `365d767`, committed and clean, with the gate green (4188 passed, 1 skipped; `gate_c4a.txt`, SHA-256 `788d78ccc7b99df115046483bae88c06c69024bbcbae138945cdefacc498cff0`).

### The invocation

`python -u scripts/s6_rehearsal.py --root F:\trading bot\scratch\p119\rehearsal --store F:\trading bot\store\mainnet-historical --label p119-final`, no `--window`, `--case both`, from the development checkout. Predictions: `predictions_c4b_run.txt` (SHA-256 `06c9fde70705eb12c20cbbd9c21d10eb1ea03943e6da65d796ba2045e4023f5e`), written before the run, with the hop count (56 a case) taken from the test double over the same script. Console output `rehearsal_p119_final.txt`, SHA-256 `99a883e493ff1e1cf690ff159dd9214fe48b9b22d7d89820d1df821512209a04`.

**Result: 112 of 112 hops matched their predictions, 56 in each case, cleanup included. It stopped on nothing, on the first run from the start, with no seam fault.** `git worktree list` afterwards shows the development checkout and the survey worktree of C4a only (removed with this section's commit); both rehearsal worktrees were removed by the script, junction first.

| Case | `hops.jsonl` SHA-256 | S7 SUMMARY |
|---|---|---|
| pass | `acb01db19c2e16e4ffe2bbfa62e3c0cbbf6f70d7d2a672214c2bba4f3a54a2dc` | `2 of 2 candidates read PASS` |
| fail | `37d652810e1e54b10a66e3321d25ec8f816dfafbb9038856653770f69f47586b` | `0 of 2 candidates read PASS` |

### What the re-run showed about step O7, which is its purpose

**The tool met real records for the first time here and the double did not mislead.** Hop 33, `s6_mark_read.py --backtests data/backtests --dry-run`, read the six real out-of-sample records through the evidence door and printed, for each of the two entries, `entry <id>: would be marked read` and one line per arm of the form `arm 0.05  <run directory> record sha256 <digest>`, then `dry run: nothing was written`; exit 0, and `git status --porcelain` empty afterwards (hop 34). Hop 38, the same without `--dry-run`, exit 0, printed `marked read` for both and the closing `next: git add docs/research/entries; commit; push; rebuild the clone; scripts/s7_gate.py`; hop 39 shows exactly two lines, ` M docs/research/entries/s6-sma_crossover-4h-off.json` and ` M docs/research/entries/s6-sma_crossover-4h-on.json`; hop 41 read both entries back as `read` with a record at each of the three arms. After the commit and the reinstall at it (hop 44, 13.2 s) and an accepted boot (hops 45 to 47), **hop 48 ran the tool a second time and it exited 2 with `REFUSED: entry 's6-sma_crossover-4h-off' is already read (status 'read'); a candidate is read once`**, leaving the status clean (hop 49). The backtest command's own refusal of a read entry followed (hop 50: exit 1, `[already_read] entry 's6-sma_crossover-4h-off' has been read out of sample already (status 'read'); a candidate is read once.`), and neither refusal left a run directory.

**The sweep (R-CQ).** In both cases hop 11 printed `variants declared 2; with a sealed evidence-eligible record 2`, `parallel check: the trade-log digests are equal`, exactly one `DUPLICATED` line (the check's probe variant) and `COMPLETE`, with **no `LOST`, `RECOVERED` or `FAILED` line**: the stamp collision was fixed at `93e98e7`, so the check lost no worker. **R-CQ's report path was therefore NOT exercised by this run** (`UNMEASURED` against a real lost worker); it is pinned by `tests/unit/test_s6_sweep.py` over a worker lost once (`crash_once`), which fails on the old script.

**The selection** reported `cells with a candidate 2 of 2` and, in the narrowed protocol, `ruled ineligible by the owner (R-CM), still run and counted: 0`: the rehearsal's narrowing clears R-CM's list, because the two narrowed variants ARE the two the owner ruled ineligible and a rehearsal that honoured the ruling would have no candidate to read. R-CM's effect on a selection is pinned by `tests/unit/test_selection_ruling.py` and not by this run.

**The gate figures are identical to `final2`'s (section 52), as predicted:** same data and same code paths, different run directories and digests. Pass case, gate arm 1.20, out of sample the whole of 2020:

| Candidate | Trades | Return profit factor | USDT profit factor | Max drawdown (per bar) | Regime net P&L | Verdict |
|---|---|---|---|---|---|---|
| unfiltered | 53 | 1.035753 (2.270546 at 0.05, 1.493289 at 0.66) | 1.034942 | 0.004822 | rising -18.22, falling 0, sideways +23.16 | PASS |
| filtered | 36 | 1.042873 (2.301779 at 0.05, 1.507719 at 0.66) | 1.042095 | 0.003593 | rising -16.64, falling 0, sideways +20.84 | PASS |

Fail case (the real thresholds): both FAIL with `NOT MET` on both profit factors (against 1.3), on the trades (53 and 36 against 100) and on the regimes (1 of 3 against 2). The selection's in-sample cells were 57 trades at return profit factor 0.364063 and 22 trades at 0.473241, unchanged.

**Per-hop record, pass case** (`hops.jsonl` SHA-256 `acb01db19c2e16e4ffe2bbfa62e3c0cbbf6f70d7d2a672214c2bba4f3a54a2dc`; every row matched its prediction; "-" is a check made by the script, not a command):

| No. | Hop | Exit | Output SHA-256 | Seconds |
|---|---|---|---|---|
| 1 | `worktree-add` | 0 | `d463b0af786b9adaea5c22170e9d4fcc76072abe7eb9fe5f3845c05af2b4d1e2` | 0.2 |
| 2 | `venv` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 7.2 |
| 3 | `pip-requirements` | 0 | `7ab92d00f5f3912c95159ec91d366f4b0a709edcc4960a11596b2eee555abcf9` | 48.5 |
| 4 | `junction` | 0 | `9faf89b257fd48d5001d068027c7951d91525a5f4b1c85daa933fa493f0adb88` | 0.0 |
| 5 | `add-narrowed-protocol` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 6 | `commit-narrowed-protocol` | 0 | `1845e218069efe94d9e39e24d1ac3eae23b5a87118be41bb3a1cf750fab2e9ae` | 0.2 |
| 7 | `install-by-commit` | 0 | `e556c5b23656b8a45110cc206cea22321fa0f51d1ce937936f6dbf1b28683ee7` | 27.8 |
| 8 | `boot-after-narrowing` | 0 | `1bb4cfca053afc022206d3b9ecb4ff6085954323509992d87f05f698c0b5604a` | 4.6 |
| 9 | `boot-after-narrowing-provenance` | - | `1bb4cfca053afc022206d3b9ecb4ff6085954323509992d87f05f698c0b5604a` | 0.0 |
| 10 | `boot-after-narrowing-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 11 | `sweep` | 0 | `abde299b7dfe97558546d2f0d0c1894863c46fbbe40e76497c4b306d92ef52e3` | 24.9 |
| 12 | `status-after-sweep` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 13 | `select-report` | 0 | `b2629abdd2f831eea86682769554a17caecde0a0430ee6136bb95674df751361` | 0.3 |
| 14 | `select-has-candidates` | - | `b2629abdd2f831eea86682769554a17caecde0a0430ee6136bb95674df751361` | 0.0 |
| 15 | `status-after-report` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 16 | `select-write` | 0 | `e060f173fb232c3adbe5911c3066d04c1de72cfe2083f5885c988a7f422941fd` | 0.2 |
| 17 | `select-entries-match-report` | - | `e060f173fb232c3adbe5911c3066d04c1de72cfe2083f5885c988a7f422941fd` | 0.0 |
| 18 | `status-lists-the-new-files` | 0 | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 19 | `status-holds-only-the-new-files` | - | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 20 | `add-selection` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 21 | `commit-selection` | 0 | `1aa9549566b7887902eaa227bdcffaf510d34857e98737b3969e88506e9595bb` | 0.3 |
| 22 | `install-at-entries` | 0 | `1580e27460cb9d7606ebee966fb9d1cb3260d9601fd56e51b1e41f47d0d11ca3` | 12.6 |
| 23 | `boot-at-entries` | 0 | `d3e51298e929354405fae1030e76c992bf6a61a726827b82ca5a8cabb922cc55` | 0.9 |
| 24 | `boot-at-entries-provenance` | - | `d3e51298e929354405fae1030e76c992bf6a61a726827b82ca5a8cabb922cc55` | 0.0 |
| 25 | `boot-at-entries-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 26 | `oos-s6-sma_crossover-4h-off-0.05` | 0 | `ccc5a9acc7b56e101bb9b9c13203796213e40b97c05899fc528cc2c97313044a` | 10.7 |
| 27 | `oos-s6-sma_crossover-4h-off-0.66` | 0 | `a85e1f1b3ad178a0e93c214748dce1379c3b94a09f4129aaa1a9d11ccd1fdb3e` | 10.2 |
| 28 | `oos-s6-sma_crossover-4h-off-1.20` | 0 | `4ad7035be4d2a38355a8edda2c766e3d6181be822b19f35f759b1b895176e8d3` | 10.1 |
| 29 | `oos-s6-sma_crossover-4h-on-0.05` | 0 | `75d69be1574122762d75c3853b50065ba91d2c0661687690dc71fb7b5f587cab` | 10.1 |
| 30 | `oos-s6-sma_crossover-4h-on-0.66` | 0 | `91a69ec8eb9fa698f97d9c5fb2b24463e3723e728f9535678a0bc1955056f287` | 10.2 |
| 31 | `oos-s6-sma_crossover-4h-on-1.20` | 0 | `b86894df93b009bc4c8f830d10b49e538b7024eba4f5dd2f1e992004d0a34d9d` | 10.0 |
| 32 | `status-after-oos` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 33 | `mark-read-dry-run` | 0 | `12c8672fa28a0db0dba32f55129e613ac46d1fa65d5e9c40124ea4844651748b` | 0.3 |
| 34 | `status-after-dry-run` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 35 | `second-read-same-arm` | 1 | `c98540b9b0cf07f814250372a1efe86cd45db3f04567a6d66bc7bf01a50fc795` | 1.6 |
| 36 | `second-read-left-no-run` | - | `641929ebca87dfd8ad6da8b367220f46238182a96f1b35c521f8a4e62b9b1a77` | 0.0 |
| 37 | `status-after-refusal` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 38 | `mark-read` | 0 | `5e9315a1ae50a9808df286a177956ea36f1bebbe6fb5a0ff3b2a2be30de78966` | 0.3 |
| 39 | `status-after-marking` | 0 | `aec441f9be760f7de9530ffad7dedeebb911e068abd111e2e04fcfadaebc860c` | 0.0 |
| 40 | `status-holds-only-the-marked-entries` | - | `aec441f9be760f7de9530ffad7dedeebb911e068abd111e2e04fcfadaebc860c` | 0.0 |
| 41 | `entries-are-read-with-the-declared-arms` | - | `8974dc5860c67d9751214d404bc6738c5e4aefc448c8df4fb4ec24313fb37021` | 0.0 |
| 42 | `add-read` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 43 | `commit-read` | 0 | `d68b61aa6d360e96a5acc4f7ad72ef4a4518831530cdd569c9b164912aed69fd` | 0.2 |
| 44 | `install-at-read` | 0 | `57648bf92ecbc6227f0dd7f0ff04ca349cf049491270cb448a0c10a0038dcac9` | 13.2 |
| 45 | `boot-at-read` | 0 | `3c0b1a44ce89ada09fda36309a9dbcc508acd49dbd1b6195afab7b94a720515a` | 1.0 |
| 46 | `boot-at-read-provenance` | - | `3c0b1a44ce89ada09fda36309a9dbcc508acd49dbd1b6195afab7b94a720515a` | 0.0 |
| 47 | `boot-at-read-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 48 | `mark-read-again` | 2 | `b8f834f06777a92772edbb7eef9585d42ac05e571e9b4960b9ec03cf518049a6` | 0.3 |
| 49 | `status-after-second-marking` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 50 | `read-after-read` | 1 | `a8f356a4c9d05fc9d5126d7a60bcddc2138faa3f76a84c007b907d507205698f` | 1.6 |
| 51 | `read-after-read-left-no-run` | - | `641929ebca87dfd8ad6da8b367220f46238182a96f1b35c521f8a4e62b9b1a77` | 0.0 |
| 52 | `s7-gate` | 0 | `185d123cf32d80a10190c4a153084bd1aec989de731665dc80ab52f538355e38` | 0.3 |
| 53 | `junction-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 54 | `junction-gone` | - | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 55 | `worktree-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 1.8 |
| 56 | `store-untouched` | - | `29eedcfc6ede3629c7bcb2b601fbefe3f8bed550701e1cb9def5c64bf59448d5` | 0.0 |

**Per-hop record, fail case** (`hops.jsonl` SHA-256 `37d652810e1e54b10a66e3321d25ec8f816dfafbb9038856653770f69f47586b`):

| No. | Hop | Exit | Output SHA-256 | Seconds |
|---|---|---|---|---|
| 1 | `worktree-add` | 0 | `d463b0af786b9adaea5c22170e9d4fcc76072abe7eb9fe5f3845c05af2b4d1e2` | 0.2 |
| 2 | `venv` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 6.6 |
| 3 | `pip-requirements` | 0 | `7ab92d00f5f3912c95159ec91d366f4b0a709edcc4960a11596b2eee555abcf9` | 43.0 |
| 4 | `junction` | 0 | `0c6d60214eba6b8f6767cae3b36ad97f83958c7a4b31e5a793269cb7f134c286` | 0.0 |
| 5 | `add-narrowed-protocol` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 6 | `commit-narrowed-protocol` | 0 | `3f757aaee7c5026de0aef7f7833b9c9e4ae8f0c64c987ad9ff30d9ff8512c3b2` | 0.2 |
| 7 | `install-by-commit` | 0 | `6c445e73cd42fac4a3f059b563a0f7cc50d3035c15ba63dfca2edc93e5fc8f0d` | 13.8 |
| 8 | `boot-after-narrowing` | 0 | `c194bd23e8506eb12ad96a44550488680a41718d4395ec23597ee157d5fa566c` | 5.1 |
| 9 | `boot-after-narrowing-provenance` | - | `c194bd23e8506eb12ad96a44550488680a41718d4395ec23597ee157d5fa566c` | 0.0 |
| 10 | `boot-after-narrowing-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 11 | `sweep` | 0 | `962b72709a3bcdf8466d4d94ffcbd5892f47bc41f19517cb7c7053c8c323ee6a` | 26.3 |
| 12 | `status-after-sweep` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 13 | `select-report` | 0 | `833903279b485986f555aad4013d8b4513117c788558c10067ae7f2a3107e8cd` | 0.3 |
| 14 | `select-has-candidates` | - | `833903279b485986f555aad4013d8b4513117c788558c10067ae7f2a3107e8cd` | 0.0 |
| 15 | `status-after-report` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 16 | `select-write` | 0 | `43fbfbe57fa6364c0d9413b2b840772227d98ce6e16663738445317ae31e6b16` | 0.3 |
| 17 | `select-entries-match-report` | - | `43fbfbe57fa6364c0d9413b2b840772227d98ce6e16663738445317ae31e6b16` | 0.0 |
| 18 | `status-lists-the-new-files` | 0 | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 19 | `status-holds-only-the-new-files` | - | `718e506bb213d6b0c0791ac7e91efd8ab6e74be6dc557b27c1fd117ca765cd86` | 0.0 |
| 20 | `add-selection` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 21 | `commit-selection` | 0 | `d45fcc270d2635a7097caaeaf5701ed00ff3834031fd8d38de3b40618f798f1f` | 0.2 |
| 22 | `install-at-entries` | 0 | `d5a1b0f90be90581e9060821c107f4d211e23cc0a9d6249295d256cd6e3df21f` | 13.0 |
| 23 | `boot-at-entries` | 0 | `a2b5067f452c50b382fa8fca6b07caf8c06803bec9be973cff2aacc18fbc10ec` | 1.0 |
| 24 | `boot-at-entries-provenance` | - | `a2b5067f452c50b382fa8fca6b07caf8c06803bec9be973cff2aacc18fbc10ec` | 0.0 |
| 25 | `boot-at-entries-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 26 | `oos-s6-sma_crossover-4h-off-0.05` | 0 | `694a0c5c1a0d7bdb63fff1ec5a90b4baee9aa2d40e41390f3b4df6cb6798a282` | 10.9 |
| 27 | `oos-s6-sma_crossover-4h-off-0.66` | 0 | `e062d6161f3188d1da394f6532371195e8b7827fc2413c55d81c591a32bcb713` | 10.7 |
| 28 | `oos-s6-sma_crossover-4h-off-1.20` | 0 | `4d9487c695d26fd0bce1260a90ecc68ae67d4804a3ccc70b369e86dfc8f965f5` | 10.7 |
| 29 | `oos-s6-sma_crossover-4h-on-0.05` | 0 | `c639317ff4bd5196a09f2a19264b9c44f382d7aa0908d4fc9fcfba82b0c604e5` | 10.7 |
| 30 | `oos-s6-sma_crossover-4h-on-0.66` | 0 | `3538737afb00928c90f4fd3e00e99f1dd88f8fdb8a87859f57494744f673b829` | 10.8 |
| 31 | `oos-s6-sma_crossover-4h-on-1.20` | 0 | `7596338f6798e232495a49aaa4ad5ee88be420a2f588644610ea0418a16961f8` | 10.8 |
| 32 | `status-after-oos` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 33 | `mark-read-dry-run` | 0 | `9a192de1e085ac9da3e9e7358b95da9b97803aaae5df6c35f9aa56b68613ab6b` | 0.3 |
| 34 | `status-after-dry-run` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 35 | `second-read-same-arm` | 1 | `edb1ed76c4b45069fe55bf8fb416596f2d93c12b65145b2e282e0314f7bf94b1` | 1.4 |
| 36 | `second-read-left-no-run` | - | `f014c7d8ef70c896077a9e1f2dd28ef582d88764bac6840c4dbe27332d03e530` | 0.0 |
| 37 | `status-after-refusal` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 38 | `mark-read` | 0 | `1b3646e137f736b47cd6aef59c8455fe0a7b744db9e7a6055233671e8ecb3f75` | 0.3 |
| 39 | `status-after-marking` | 0 | `aec441f9be760f7de9530ffad7dedeebb911e068abd111e2e04fcfadaebc860c` | 0.0 |
| 40 | `status-holds-only-the-marked-entries` | - | `aec441f9be760f7de9530ffad7dedeebb911e068abd111e2e04fcfadaebc860c` | 0.0 |
| 41 | `entries-are-read-with-the-declared-arms` | - | `0da0bc7365335864d96abc9db8c883f4240bc2dec2a7541afd078c4668340103` | 0.0 |
| 42 | `add-read` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.1 |
| 43 | `commit-read` | 0 | `def45f459e013aa2d3287e0a9ec943d4ae3fcf78394aacafead8972eee062f03` | 0.2 |
| 44 | `install-at-read` | 0 | `8684306317864f7329a7d1fb0d394cf964aa4555c177774ce2a51e790c894473` | 12.9 |
| 45 | `boot-at-read` | 0 | `413babfc9acbad1ffe27de296b7e37bbd236905fa21543c649063a32fabf651e` | 1.0 |
| 46 | `boot-at-read-provenance` | - | `413babfc9acbad1ffe27de296b7e37bbd236905fa21543c649063a32fabf651e` | 0.0 |
| 47 | `boot-at-read-status` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 48 | `mark-read-again` | 2 | `b8f834f06777a92772edbb7eef9585d42ac05e571e9b4960b9ec03cf518049a6` | 0.3 |
| 49 | `status-after-second-marking` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 50 | `read-after-read` | 1 | `f94a6d03fd17c451bad31cc5d93131ab22217c2419e9bf0ddd23e91c713dea7e` | 1.6 |
| 51 | `read-after-read-left-no-run` | - | `f014c7d8ef70c896077a9e1f2dd28ef582d88764bac6840c4dbe27332d03e530` | 0.0 |
| 52 | `s7-gate` | 0 | `e73e0df829340289f467018d00a9add07c8fe755e43a5aa6714fad8e63212094` | 0.3 |
| 53 | `junction-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 54 | `junction-gone` | - | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 0.0 |
| 55 | `worktree-remove` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | 1.8 |
| 56 | `store-untouched` | - | `29eedcfc6ede3629c7bcb2b601fbefe3f8bed550701e1cb9def5c64bf59448d5` | 0.0 |

### What this re-run did NOT cover

Everything section 52 lists still holds: a `git worktree` where the owner clones from GitHub (O1); the selection run inside the clone; one venv moved to the entries commit and then to the marking commit where the owner builds a NEW clone for O5 and reinstalls in the O5 clone for O7; 2 workers where O3 uses 8; 2 variants where S6 has 216, so no 1h run, no 12-cell selection with empty cells and no four-fold walk-forward. **None of the PowerShell of O1 to O7 and the gate was executed**; the rehearsal runs the same commands as argument arrays from Python (`docs/NEXT_MILESTONE.md`, the P119 C5 block, states exactly which lines were and were not run). **It also did not exercise `git push`**, which the owner runs in O7.

## 54. M5m S6: the sweep, O1 to O3, as its manifest and records show it, the report-only selection, and the null of R-CM's two variants (P120 Step 1, R-CR, R-CS)

Read on `2026-10-15` from files under `F:\trading bot\scratch\p120\` (outside the repository), from the sweep clone `F:\trading bot\backtest\cf474214a539` **read only** (it was read with the development tree's interpreter and `-B`, so no bytecode was written there; its `git status --porcelain` read empty before and after, and no file outside `.git`, `.venv` and the `data\historical` junction is newer than its manifest, by `find -newer`; `git status` may refresh `.git/index`, which this section does not claim otherwise), and from the development tree. The S4 clone was copied in share mode (section 55) and not otherwise touched; the S5 clone was not read. No venue write was made and `docs/research/PROTOCOL.md` was not edited.

The owner's rulings, verbatim. **R-CR:** *"O7 and the S7 gate run from the development tree, reading the clones' run records by path, as O4 does. No commit is made and nothing is pushed from any clone. O5 still builds a clone at the entries commit, because the guard reads the committed entry there."* **R-CS:** *"Before any out-of-sample read, the chance that a strategy with no edge passes all four S7 tests is computed for the actual candidate count, by a committed script whose method is stated in its commit. It informs the reading of S7's result and does not gate it."* **R-CT:** *"The S4 restart of 2026-10-15 is recorded under R-BN: pid 5224, booted 2026-10-15T11:16:55Z, the open ETHUSDT position restored from order list 99221 and reconciled active from the first pass at 11:18:00Z."*

### The halts, against their predictions

Predictions were written to `predictions_halts.txt` (SHA-256 `224725f6ede1ae7f0fe7135f036f45ed53e8e9f2dfe0a3c7b99411e945a483ee`) before any halt ran, each halt its own invocation.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | both `cf47421` | as predicted: HEAD `cf47421`, `git ls-remote origin refs/heads/main` `cf474214a539035736e1cec4414d422ab9a378f6` |
| H2, `git status --porcelain` | empty in the development tree and in the sweep clone | as predicted, 0 lines in each; the clone's HEAD is `cf474214a539035736e1cec4414d422ab9a378f6` |
| H3, the gate, bare, to a file | 216 files, mypy 108, 4188 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `d0ba49b615bc80bcec866e15ac61c3127da7b885c035ab7540087efa5cd561ac`; 369.11 s) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 484, distinct 484, max 484, no duplicate, no gap, no cited-not-declared, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `73c803d1fc2c0ed011a91703dc8fa266bd2f09a5a354636a50fa180360b8cca3`) |
| H5, the sweep's records | the prompt's figures; I added a possible third duplicate pair (the check's variant) | the prompt's figures, and **my third pair did not occur**: 222 directories; 4 ending `-running`; 218 sealed; 216 points, 216 distinct variant keys, 0 missing, 0 conflicts; **2 duplicate pairs, each with one trade-log digest** (`sma_crossover` 1d 10/100: `20261015T111115663748Z-9d84a0843e63` and `...111125362814Z-...`; `sma_crossover` 1d 20/50: `...111354871030Z-530c03a09f23` and `...111405404034Z-...`); 4 skipped, all `not_sealed`, none holding a `run.json`; the points hold 57,581 trades in all (`h5_out.txt`, SHA-256 `9c294f48ea08ea707bf555bd8e00924011378ebf43d55db7f72cab59a22f06fe`) |

### O1, as far as a read-only look shows it

HEAD `cf474214a539035736e1cec4414d422ab9a378f6` (committer date `2026-10-15T16:39:11+06:00`), the checkout clean, `data\historical` a `Junction` to `F:\trading bot\store\mainnet-historical`, the venv's `version = 3.12.10`, and `docs/research/PROTOCOL.md` byte-identical to the development tree's (SHA-256 `fc11efaeb28902d455f82cf9cc9a1d1b3a286fb1bdd680750ced435738e34547` in both), which is O4's comparison. The clone has no `s6-*.json` entry, as it must not at this point. **Not re-run, because it would write into the clone:** the `boot_provenance` check of O1.

### O2 and O3, from the manifest

`data\s6_sweep_manifest.jsonl`, SHA-256 `88b5c8d0c3534ed69c4d8223c5e7a590d28a177a1c75ccd23cb7eea3ba385515`: 448 events, 222 `launch` and 218 `finish`, every `finish` with `returncode` 0, no `FAILED`, no worker lost and recovered. Predictions: `predictions_step1.txt` (SHA-256 `b80409fdefd385c063e0d53bbfcc4dce8a696a14a9cde231899eadcd96faa65d`), written before the manifest was analysed (`manifest_1b.py`, output SHA-256 `7e5269c31d8956fe79d30ee520a3fc83fe1bb8c0e1b35a8b969139287c8aa575`).

| Segment | From (UTC) | To | Length | What it was |
|---|---|---|---|---|
| 0 | 10:52:59.9 | 11:08:28.4 | 0:15:28.5 | O2, `--probe`: six serial runs, `sweep_end complete false` |
| gap | | | 0:02:46.0 | |
| 1 | 11:11:14.4 | 11:13:48.2 | 0:02:33.9 | O3 at `workers 4`, `to_run 210`; R-CH's check at 11:11:34.4 (digests equal, variant `sma_crossover` 1d 10/100); **`interrupted` at 11:13:48.2, four workers terminated (pids 13096, 8324, 11504, 11560)** |
| gap | | | 0:00:05.4 | |
| 2 | 11:13:53.6 | 13:23:53.4 | 2:09:59.8 | O3 at `workers 8`, `to_run 208`, `with_a_run 8`; the check again at 11:14:18.1 (digests equal, variant `sma_crossover` 1d 20/50); `sweep_end complete true`, `duplicates 2`, `failed []` |

**Wall time, first start to last finish: 2:30:49.8** (the first `launch` event to the last `finish`; the last event, `sweep_end`, is 3.8 s later). The owner's derived figure for O3 was 1.3 to 2 hours at 8 workers; the 8-worker segment was 2:10:00. The four terminated workers are the four `-running` directories, stamped within 40 ms of one another at 11:11:35.9Z; they never reached a `finish`, and their variants were run again by segment 2. **Worker time:** 63,087.4 s in all (17.52 h), of which 206 finishes at 8 workers were 17.25 h in a 2.167 h segment, an average of 7.96 workers running: the pool was full throughout.

**O2's six probe runs (one worker, serial), with the owner's bar counts (1h 111,394; 4h 27,900; 1d 4,656):**

| Variant (first of its family and timeframe) | Seconds | ms a bar |
|---|---|---|
| `rsi` 1h | 455.0 | 4.08 |
| `rsi` 4h | 105.6 | 3.78 |
| `rsi` 1d | 18.6 | 4.00 |
| `sma_crossover` 1h | 274.5 | 2.46 |
| `sma_crossover` 4h | 64.1 | 2.30 |
| `sma_crossover` 1d | 10.0 | 2.15 |

These are the figures the owner's probe measured (`sma_crossover` 2.15 to 2.46, `rsi` 3.78 to 4.08 ms a bar), to the digit. **The per-bar cost of the full sweep at 8 workers**, medians with the range in brackets, seconds and then ms a bar, and the ratio of the median to the probe's figure for the same family and timeframe:

| Family, timeframe | n | Seconds, median [min, max] | ms a bar, median [min, max] | Ratio to the probe |
|---|---|---|---|---|
| `sma_crossover` 1h | 17 | 533.0 [513.9, 559.7] | 4.78 [4.61, 5.02] | 1.94 |
| `sma_crossover` 4h | 17 | 128.6 [124.9, 131.6] | 4.61 [4.48, 4.72] | 2.00 |
| `sma_crossover` 1d | 13 | 18.1 [13.2, 18.5] | 3.90 [2.83, 3.98] | 1.81 (boot-dominated) |
| `rsi` 1h | 53 | 743.3 [677.7, 795.0] | 6.67 [6.08, 7.14] | 1.63 |
| `rsi` 4h | 53 | 188.2 [178.8, 194.3] | 6.74 [6.41, 6.97] | 1.78 |
| `rsi` 1d | 53 | 27.9 [26.1, 30.2] | 5.99 [5.61, 6.48] | 1.50 (boot-dominated) |

**Against the predictions.** The wall time (2.0 to 2.8 h predicted) and the `rsi` ratios (1.0 to 2.0 predicted) held. The `sma_crossover` ratios were predicted at 2.0 or under and the maxima exceed it slightly (5.02 against 2.46 is 2.04; 4h 4.72 against 2.30 is 2.05): a small miss at the top of the range, not at the median. **Eight workers cost about twice the probe's time per bar for `sma_crossover` and 1.6 to 1.8 times for `rsi`**, so the 3.3 GB the owner reported available was not the binding term (REASONED: no worker failed, and the pool stayed full), and contention is the likelier cost. Peak memory was not recorded.

**A derived time for O6, UNMEASURED:** O6 runs three arms for each candidate over 2024-01-01 to 2026-10-01, about 48,200 1h bars and 12,050 4h bars across both pairs. At the probe's serial rates, the six candidates of the selection below come to about 118 s (`sma_crossover` 1h), 196 s (`rsi` 1h), 28 s (`sma_crossover` 4h) and 45 s (`rsi` 4h) a run, so 2 x 3 x 118 + 2 x 3 x 196 + 3 x 28 + 3 x 45 is about 2,100 s, **about 35 minutes plus the 3 s boot of 18 runs**.

### Step 1c: the report-only selection over the sweep clone's records

`python scripts/s6_select.py --backtests "F:\trading bot\backtest\cf474214a539\data\backtests"` from the development tree, writing nothing (output `select_report.txt`, SHA-256 `0a92e6ff4f63f787b7a2e030287d66e3849bf0463b74c20a6d5879beb19ebef6`, 3.9 s): **`variants declared 216; with a run 216; duplicated 2; skipped directories 4`**. So each duplicate pair counts as one run (the first by directory name stands, and the digests are equal, so either gives the same trades) and the four `-running` directories are listed `SKIPPED ... not_sealed` and are never read as a point. No duplicate decides a selection; the prediction held.

**Cells with a candidate: 6 of 12.** Predicted before the run (`predictions_c3.txt`, SHA-256 `b333a967a1bc77f932e9717768192ccfbfa9ee7a9cc83f6ce445e5b5bd2a6206`): 7, range 6 to 8. It is inside the range and one under the point. The six: `sma_crossover` 1h filter off and on, `sma_crossover` 4h filter off, `rsi` 1h filter off and on, `rsi` 4h filter off. The six without one are the four 1d cells, `sma_crossover` 4h filter on and `rsi` 4h filter on.

**Every candidate loses money in sample, and by a wide margin.** The selection statistic is the return profit factor at the 1.20 arm, and the six candidates' are 0.482, 0.516, 0.387, 0.413, 0.426 and 0.359 (USDT profit factors 0.482, 0.518, 0.386, 0.410, 0.426 and 0.355), on 682, 469, 298, 2,738, 777 and 854 trades. **No eligible point of any cell has a statistic at or above 1, because each candidate is the maximum of its cell's eligible points and the six cells without a candidate have none; and every cell's walk-forward reads `folds with a forward return PF above 1: 0 of 4`.** S7 asks for 1.3 on both profit factors. This is data, not a fault, and it is recorded here before any out-of-sample read.

**R-CM's two variants are not selected, and the ruling changed one cell** (`rcm_show.py`, output SHA-256 `ebf2546577786d0d8ee64d59ef593196f3c71ec83bf9854554e45135c3eedf52`, which re-runs the selection with and without the ruling):

| Variant | Trades | Return PF | Max drawdown | Reasons with R-CM | Reasons without it |
|---|---|---|---|---|---|
| `sma_crossover` 4h 10/50, filter off | 358 | 0.439566 | 0.0771 | `ruled_ineligible` | none |
| `sma_crossover` 4h 10/50, filter on (200) | 172 | 0.483397 | 0.0357 | `too_few_trades`, `ruled_ineligible` | `too_few_trades` |

**Without the ruling the `sma_crossover` 4h filter-off cell would have picked 10/50 (0.4396); with it, 30/50 (0.3872), a lower statistic.** The other five candidate cells are the same either way, no ruled variant is a candidate or any fold's pick, and the filtered 4h variant was ineligible for too few trades whatever the ruling. So the ruling removed no cell and moved one candidate, as predicted.

### What this section does not cover

The memory of 8 workers; the clone's `boot_provenance` (it would write); and any statement about S4 or S5, which are in section 55 and in the earlier sections.

**Annotation (P120 C1): a sentence of section 53 is no longer a description of the owner's procedure.** Section 53's last paragraph says the rehearsal differed from the owner's steps in *"one venv moved to the entries commit and then to the marking commit where the owner builds a NEW clone for O5 and reinstalls in the O5 clone for O7"*. That was O7 as `docs/NEXT_MILESTONE.md` wrote it at P119 C5. Under R-CR (above) nothing is committed, pushed or reinstalled in a clone, and O7 and the gate run in the development tree; the P120 C1 block in that file says so. Section 53 stands as the record of what the rehearsal ran.

## 55. M5m S4: the restart of 2026-10-15, pid 5224 (P120 Step 1a, R-CT, R-BN)

Recorded at P120, after the fact, from a share-mode copy of the S4 log taken between `2026-10-15T14:02:01Z` (its last line) and `14:04:42Z` (`F:\trading bot\deploy\45547f107715\logs\trading_bot.log`, 915,555 bytes, SHA-256 `fc47a9c0ab95e9b2984152783eec3b8aece271cee27f7d1b32b1015e6d7ae767`, 3,862 lines by `splitlines`). The S4 clone was only read. An observation log, so this section only adds. R-CT, verbatim: *"The S4 restart of 2026-10-15 is recorded under R-BN: pid 5224, booted 2026-10-15T11:16:55Z, the open ETHUSDT position restored from order list 99221 and reconciled active from the first pass at 11:18:00Z."* Predictions: `predictions_step1.txt`, section 1a.

| Fact | Value |
|---|---|
| the previous process | pid `25352` (booted `2026-10-14T06:34:32Z`, section 49). **Its last line is `2026-10-15T08:23:00Z`, a `reconciliation_pass` (`positions=1 ... states="active=1"`).** There is no `engine_stopped` line and no shutdown marker: pid 16076's `Trading engine stopped event=engine_stopped clean_shutdown=True` at `2026-10-12T04:17:43Z` is the only one in the log |
| the line before the restart | `2026-10-15T08:21:02Z`, pid 25352 booked the BTCUSDT close (`quote_total=1892.12781030 quote_total_source=venue entry_quote_total=1887.91278610 realised=4.21502420 fee=0E-8 fee_asset=USDT fills=2`, `order_id=2890963`), leaving one position, the ETHUSDT one placed at `08:10:01Z` (`order_list_id=99221`, `quantity=0.79710000 entry=2371.40000000 stop_loss=2323.98000000`) |
| the down span | **last line of pid 25352 `08:23:00Z` to first line of pid 5224 `11:16:54Z`: 2:53:54.** By the frozen `scripts/s4_compare.py` `down_intervals` (imported, not edited; `run_down_intervals.py`, output SHA-256 `d52c92b046445108625faaf780b144bed9140d143eeed5c8d7955798f258852c`): **`2026-10-15T08:23:00+00:00` to `2026-10-15T11:18:00+00:00`, 175.00 minutes**, the second end being the first reconciliation pass of pid 5224. Adjacent lines 3706 and 3707 of the copy are those two, so no line of any pid lies between |
| how it stopped | **UNMEASURED beyond the machine's own record.** The bot wrote no stop marker. The Windows System log shows `Kernel-Power` 41, *"The system has rebooted without cleanly shutting down first"*, and `EventLog` 6008, *"The previous system shutdown at 1:52:34 PM on 10/15/2026 was unexpected"*, both at `2026-10-15T10:22:31Z` to `10:22:52Z` with the OS booting at `10:22:31Z`; `BugcheckCode` 0, `SleepInProgress` 0. The machine's time zone is UTC+6, so the 6008's *1:52:34 PM* is `07:52:34Z`, which the bot's own lines up to `08:23:00Z` contradict: it is a periodically written last-alive stamp and not the instant of the stop, and it is used here only for *unexpected*. The bot ended with an unclean reboot of the machine at some time after `08:23:00Z`; **the next reconciliation pass was due at about `08:24:00Z` and there is none, so the stop lies between `08:23:00Z` and about `08:24:00Z`** (argued from the presence of the passes, one a minute, on both sides) |
| the OS and pid 5224 | the OS booted at `10:22:31Z`; pid 5224 wrote its first line 54 minutes later |
| pid / first line | `5224`, `2026-10-15T11:16:54Z` (the banner); `boot_provenance` at `11:16:55Z` |
| verdict | `accepted`, `install_kind=vcs`, `code_commit=45547f10771543b41db42e1cbcb8b5a0a9cf1776` (the S4 clone's commit, the same as every earlier pid in the log), `code_intact=true` over 77 files |
| composition root | ready at `11:17:10Z`, 2 pairs, **92623.52676550 USDT free**, 514 assets excluded from equity (the pre-existing warning) |
| the restore | `11:17:10Z`, `ETHUSDT: restored the open position from the store, UNKNOWN until reconciled event=boot_position_restored symbol=ETHUSDT source=position list_client_order_id=tb1-ETHUSDT-1792051799999-0-L order_list_id=99221 entry_fill_price=2369.03 entry_quote_total=1888.35...`; then `Boot resolved 1 restored record(s): 1 restored, 0 booked, 0 held, 0 dropped, 0 gone event=boot_positions_resolved records=1 pending_placements=0 restored=1 booked=0 held=0 dropped=0 gone=0` |
| engine | started at `11:17:11Z`: BTCUSDT/1m, ETHUSDT/5m (499 candles seeded each) |
| the first pass | **`2026-10-15T11:18:00Z`, `Reconciled 1 position(s) event=reconciliation_pass positions=1 calls=1 queries=2 states="active=1"`**, and `active=1` on every pass the copy holds to `14:02:01Z` |

**Against the prediction.** The boot, the restore, the first pass at `11:18:00Z` and `active=1` were predicted and held. **The down span was not**: it was predicted under ten minutes, and it is 2:53:54 (175.00 minutes by the frozen function), with no shutdown marker, because the machine itself went down uncleanly. The position was open at the venue throughout, under the order list placed at `08:10:01Z`; it rested protected for the whole span and was found `active` by the first pass after the restart. Nothing in S4's comparison is edited (R-BN): the frozen `down_intervals` excludes this interval from both sides.

Every restart of S4 recorded so far, for the owner's count: pids 27460, 27176, 16076, 22304, 3444, 25352 and now 5224, the six intervals between them being those in the frozen function's output (0.23, 49.72, 902.30, 6.57, 1451.20 and 175.00 minutes).

## 56. M5m S6/S7: the selection in the line-per-record format, S7 recorded as FAIL without a read, and the S4 restart corrected (P121, R-CU, R-CV, R-CW)

Read on `2026-10-15` from files under `F:\trading bot\scratch\p121\` (outside the repository), from the sweep clone `F:\trading bot\backtest\cf474214a539` (**read only**, as at P120), and from the committed files. An observation log, so this section only adds. No venue write was made, the S4 clone was not read at P121 (its restart facts are P120's section 55), and `docs/research/PROTOCOL.md` was not edited. The owner's rulings R-CU, R-CV and R-CW are quoted verbatim in `docs/research/LOG.md` Entry 6 and in `docs/NEXT_MILESTONE.md` (the P121 C3 block).

### The halts, against their predictions

Predictions: `predictions_halts.txt`, SHA-256 `5fc8f742c2ed8984998a69022b7e203f057669cc37829457fadd21ead3a0f344`, written before any halt ran, each halt its own invocation.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `b5f7547`; the owner HAS pushed, so `origin/main` `b5f7547` too (the alternative: `cf47421`, 3 ahead) | **WRONG, for the fourth prompt running** (`M5m-504`): HEAD `b5f7547`, `git ls-remote origin refs/heads/main` read `cf474214a539035736e1cec4414d422ab9a378f6`, the three P120 commits unpushed |
| H2, `git status --porcelain` | the seven untracked files of P120's C3 and nothing else | as predicted: `selection.json` and six `s6-*.json` entries, nothing else |
| H3, the gate, bare, to a file | 218 files, mypy 109, 4234 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `68e88a458d53be4ca45fbf50f4ae76fb66e6fd6fb968dd5a05770e79781f5a56`) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 500, distinct 500, max 500, no duplicate, no gap, no cited-not-declared, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `d74211f3eea97813c3506a61d3de40ef1024169f9a6f2d108b944e4956e3dc06`) |

The seven untracked files were then deleted from the working tree (they had never been committed); copies are in `F:\trading bot\scratch\p121\p120_selection\`, `selection.json` with SHA-256 `aa44b4f0148353748577b16caf6e6c8a0319beb68f47b89a1a4b1411da9fc912`.

### R-CU: the same picks in a different format

`scripts/s6_select.py` was re-run over the sweep clone's records into the scratch directory and compared with P120's output by `compare_selection.py` (output `compare_out.txt`, SHA-256 `d5eaa2d37da2a74077d0b3b083303cc236ae3e73d4c17c09a9602c4b6bc871e1`; commit `2e00dcc`):

| Check | Result |
|---|---|
| the printed report against P120's report-only text | identical, 118 lines |
| the 235 records against `selection_lines()` of P120's document with `selection_schema` 2 | identical; only the schema number differs from P120's file |
| the 6 picks, each with its run directory, record SHA-256 and candidate digest | identical (listed in the message of `2e00dcc`) |
| the 216 variants' record digests | identical |
| the file | 134,915 bytes, 235 lines, longest line 2,483 bytes, SHA-256 `586fcfd6f30e844290c547742c56110ad37654b020e22c7f11a2a4cd02fbad89` |

Predictions `predictions_c1.txt` (SHA-256 `7958a80b2af5e4cd70787d0efcb4392b757056549369586c7e9fea3abb926b8d`): 235 lines, 110 to 150 KB, longest line under 3,000 bytes, report and records identical: all held. The tool's survey: `survey_c1_out.txt`, SHA-256 `8aa8ddeb47798b7f0a7b21d39e163f1556da55c0c72f2a93e4155968905ea1f8`, 10 mutations, 14 kills against 13 predicted. `2e00dcc` is the format and `bdd95e4` is the file, committed unedited as `docs/research/selection.jsonl`, with no entry (R-CV). Both gates read 4244 passed and 1 skipped (`gate_c1.txt` SHA-256 `ef935439bdc33bc49d27660ebd236baa88b29669960e09b0b0458f351157cd4b`, `gate_c2.txt` SHA-256 `cab4539038b8dff79f5d65b84ca2ab7c5d6e9a2b13a2beeecf5d828ddafcb6be`).

### S7 recorded as FAIL, and what the record rests on

R-CV rules S7 a FAIL without reading the reserved window. The record is in `docs/research/LOG.md` Entry 6 with the six candidates' in-sample figures (return profit factor 0.359 to 0.516, USDT profit factor 0.355 to 0.518, 298 to 2,738 trades, per-bar drawdown 0.074 to 0.471), their walk-forward folds (0 of 4 above 1 for every candidate; two candidates have folds with no eligible point in training) and their null pass probabilities (0.0000 to 0.0739; family-wise 0.143 if independent, 0.074 to 0.150 whatever the dependence), all from the committed `selection.jsonl` and `s7_null.json`.

**The reserved window is unread for every variant except two cases.** The two variants R-CM names (Entry 5 records exactly what was seen, to `2025-04-01`) and S5's baseline configuration, which is not one of the 216 and read the whole history (Entries 1 to 3). **Evidence:** in the sweep clone all 218 sealed directories are in-sample point runs and the selection lists no run as `not_in_sample`; no out-of-sample record of any of the 216 variants exists in it. **UNMEASURED:** the other clones' records were not re-read at P121; the claim for them rests on the owner's rulings and on the ledger's earlier sections, which record a read of the real reserved window only for the two variants of R-CM (section 52) and for S5's baseline (sections 50 and earlier).

### The owner's steps O5 to O7 and the gate: not taken

O5 (the clone at the entries commit), O6 (the out-of-sample reads), O7 (marking the entries read) and the gate (`s7_gate.py`) were never run: no entry is committed, no clone was built at an entries commit, and no out-of-sample record exists. `docs/NEXT_MILESTONE.md` annotates the steps as not taken by R-CV.

### The S4 restart of 2026-10-15, corrected to the measurement (P120 Step 1a)

R-CT's wording, *"pid 5224, booted 2026-10-15T11:16:55Z, the open ETHUSDT position restored from order list 99221 and reconciled active from the first pass at 11:18:00Z"*, is the owner's and stands as the ruling. Its *"booted ... 11:16:55Z"* is the `boot_provenance` line; the measurement from the share-mode copy of the S4 log (section 55, SHA-256 `fc47a9c0ab95e9b2984152783eec3b8aece271cee27f7d1b32b1015e6d7ae767`) is:

| Fact | Measured |
|---|---|
| the previous process | pid `25352`; its last line `2026-10-15T08:23:00Z`, a `reconciliation_pass`; no stop marker |
| why it stopped | the machine rebooted without cleanly shutting down (Windows System log, `Kernel-Power` 41 and `EventLog` 6008, OS boot at `2026-10-15T10:22:31Z`); the cause of the reboot is not measured |
| pid 5224 | first line `2026-10-15T11:16:54Z` (the banner), `boot_provenance` at `11:16:55Z`, restore at `11:17:10Z`, first pass `11:18:00Z` with `active=1` |
| the down span | `08:23:00Z` to `11:16:54Z`, 2:53:54; 175.00 minutes by the frozen `down_intervals` |

Section 55 already carries this; the correction is to the shorthand, which gave the provenance instant as the boot and omitted the previous stop.

## 57. M5m S4 and S6: T0 corrected, the selection file's name, and the daily check (P122, R-CX, R-CY, R-CZ)

An observation log, so this section adds and annotates nothing above it. The rulings are quoted verbatim in `docs/NEXT_MILESTONE.md`'s P122 C1 block (R-CX, R-CY, R-CZ).

### Halts

`predictions_halts.txt`, SHA-256 `390540a87a9446d73475f382856178cee65005ba9cd242b29044cf14fceed775`. **It records a lapse (`M5m-513`):** H1 was run in the same invocation that made the scratch directory, before the file existed, so H1's
prediction is not independent of its observation. H2 to H4 were predicted before they ran.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | `f9c06a4` for HEAD; `origin/main` `f9c06a4` if pushed, else `cf47421` and 6 ahead (the prompt's own) | HEAD `f9c06a40671536a24df8d3a67ba59657125561d3`, `origin/main` the same: the owner has pushed (NOT independent, see above) |
| H2, `git status --porcelain` | empty | empty |
| H3, the gate, bare, to a file | 218 files, mypy 109, 4244 passed and 1 skipped, exit 0 | as predicted: 4244 passed, 1 skipped in 326.59 s, 339.5 s total (`gate_h3.txt`, SHA-256 `b502e2e59a40648aaefcee58148d19a8d3c5014925641c77705f94830dbdee5a`) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 512, distinct 512, max 512, no duplicate, no gap, no cited-not-declared, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `2c8d469a46bbc0a3d95eb655215880db026fc4079192597d5f1110ed66b2cc91`) |

### T0, measured (`M5m-514`)

The S4 clone's log was copied by a share-mode read (the writer still has the file open) to `F:\trading bot\scratch\p122\explore\trading_bot.log`: 1,068,775 bytes, 4,646 CR bytes (the log is CRLF), SHA-256 `53b1b2e6a73c6595e0a66f2e91de00fae3edd069664dac0ef7545d63c4b6cf08`.

| instrument | result |
|---|---|
| `event=boot_provenance` lines | 7: pids 27460 (`2026-10-10T05:58:02Z`), 27176 (`05:58:17Z`), 16076 (`06:05:20Z`), 22304 (`2026-10-12T19:17:36Z`), 3444 (`2026-10-13T07:00:36Z`), 25352 (`2026-10-14T06:34:33Z`), 5224 (`2026-10-15T11:16:55Z`), all `verdict=accepted` |
| lines `Starting in TESTNET mode` (the line `_cmd_run` logs and `_cmd_strategies` does not) | 5: pids 16076, 22304, 3444, 25352, 5224; **none for 27460 or 27176** (a Python count over the bytes of lines carrying `pid=27460 `, `pid=27176 ` and `pid=16076 `: 0, 0, 1) |
| the first run boot | pid 16076, `2026-10-10T06:05:20Z` = **T0** (R-AY, the ratified CHOSEN line 1; R-CX) |
| the cap | T0 + 35 days = `2026-11-14T06:05:20Z` |
| the earliest stop | the first UTC midnight at or after T0 + 21 days (`2026-10-31T06:05:20Z`) = `2026-11-01T00:00:00Z` |

So `docs/NEXT_MILESTONE.md`'s P121 C3 block and `docs/research/LOG.md` Entry 6 were wrong to derive T0 as `2026-10-10T05:58:02Z`: that is the `strategies` verification boot. The earliest stop they gave was right and the cap was 7 minutes 18 seconds early.
Both are annotated (the NEXT_MILESTONE block and a note at the end of LOG.md). The pid 3444 boot at `2026-10-13T07:00:36Z` logged an `ERROR` at `07:00:48Z` that a restored record cannot be resolved at boot, so the bot refused; it is a run boot by the instrument above (it logged `Starting in TESTNET mode`) and is listed as one.

### The selection file's name (R-CY, `M5m-515`)

`git grep -n -E "selection\.json\b"` over the tracked tree, before this prompt's commits: `docs/NEXT_MILESTONE.md` 4 lines (three in the P117 C8 block's O4, one in the P121 C3 block, which names the old name on purpose), `docs/RUN_LEDGER.md` 2 lines (section 56), `scripts/s6_rehearsal.py` 2,
`tests/unit/test_s6_rehearsal.py` 3, `tests/unit/test_s6_select.py` 3. **`docs/research/PROTOCOL.md`, `CLAUDE.md` and `README.md` hold none.** The documents are annotated (NEXT_MILESTONE's O4 commands, by the P122 C1 block; the two ledger lines are records and stand); the script and its tests are C2.

### What this prompt builds

`scripts/s4_daily.py` (R-CZ) is C3, and its first run against the live S4 run is C4, whose output and digests are recorded in a section of their own.

## 58. M5m S4: the first run of scripts/s4_daily.py against the live run, 2026-10-16T06:10:03Z (P122 C4, R-CZ)

An observation log, so this section adds and annotates nothing above it. The tool is `scripts/s4_daily.py` (C3a `8bd39b4`, C3b `fd79692`; section 57 called its commit C3, and it landed as two because the script with its tests passed 1,500 lines); it was run once, from the repository root, with the development
venv's interpreter, against the S4 clone `F:\trading bot\deploy\45547f107715` (pid 5224, running since `2026-10-15T11:16:55Z`).

### The command, and the one the owner runs daily

```
.venv\Scripts\python.exe scripts\s4_daily.py
```

Run from `F:\trading bot\files\binance-trading-bot\binance-trading-bot`. It takes no argument, writes under `F:\trading bot\scratch\s4\<UTC date>\` and prints the report. Exit status 0 for a report, 2 for a refusal
(a destination inside a clone, a missing log directory, a rerun in the same second).

### Predictions

`predictions_c4.txt`, SHA-256 `ea359eb9665e2c08bdaf9205e94bf7ee8d83b9e1a48cd05ba4df3ecb9a3eb4fc`, written before the first run.

| Figure | Predicted | Observed |
|---|---|---|
| exit status | 0 | 0, and nothing on stderr |
| files frozen | one: `trading_bot.log` (the bot has not rotated); the capture byte-equal to it | one file, 1,076,545 bytes, `daa6f508de83aa8cdcd7f4c916e2caa34a78f05d62f395beb97c4c123af35007`; `cmp` shows the capture byte-equal to the frozen log; no file outside the capture and no changed-set warning |
| bot process | last pid 5224, alive, launcher `[3444]` | as predicted |
| the log's last line | 0 to 2 minutes 59 seconds old | `2026-10-16T06:10:00Z`, 3 seconds before now |
| recorder task | last run `2026-10-16T06:05:0xZ`, result 0, next run `12:05:00Z`, 0 missed | last run `06:05:01Z`, result 0, next run `12:05:00Z`, missed runs 0 |
| newest bars | the 1m series open `06:04:00Z`, the 5m series `06:00:00Z`, four series in the order BTC 1m, BTC 5m, ETH 1m, ETH 5m | as predicted, each closed 5 min 03 s before now |
| boots at or after T0 | 5, all run boots; 16076, 22304, 3444, 25352, 5224 at the instants of the baseline; the strategies boots 27460 and 27176 not listed | as predicted; all `verdict=accepted`; a clean stop marker for 16076 only |
| T0 from the log | `2026-10-10T06:05:20Z`, pid 16076, equal to the ruled T0 | as predicted |
| bookings since T0 | 83 to 87, anomalies 0, none before T0, raw count equal to the census | **84** (79 `close_booked`, 5 `exit_booked`, 0 `boot_exit_booked`), anomalies 0, none before T0, none unzoned, raw 84 |
| stop arithmetic | about 6.0 days, 83 to 87 against 150, earliest stop `2026-11-01T00:00:00Z`, cap `2026-11-14T06:05:20Z`, every condition "no" | 6d 00h 04m 43s (6.003 d), 84 against 150 (short by 66), earliest stop `2026-11-01T00:00:00Z`, cap `2026-11-14T06:05:20Z`, next midnight `2026-10-17T00:00:00Z`, every condition "no" |

Every figure fell inside its prediction. Two facts the prediction did not state: pid 22304's last line is
`2026-10-13T06:54:01Z` (no stop marker), and the booking split is 79 and 5 (the baseline copy of 05:27Z held 78 and 5, so one close booked in the 43 minutes since).

### The report, verbatim

```
s4_daily  now 2026-10-16T06:10:03Z  T0 2026-10-10T06:05:20Z  clone F:\trading bot\deploy\45547f107715

== freeze (R-BM) ==
directory  : F:\trading bot\scratch\s4\2026-10-16
  daa6f508de83aa8cdcd7f4c916e2caa34a78f05d62f395beb97c4c123af35007     1076545  trading_bot.log  ->  061003Z-trading_bot.log
capture    : 061003Z-capture.log  1076545 bytes
capture sha256 : daa6f508de83aa8cdcd7f4c916e2caa34a78f05d62f395beb97c4c123af35007

== bot process ==
last pid in the log : 5224
that pid alive as a '-m trading_bot run' process : yes
launcher pids for this clone : [3444]
log's last line : 2026-10-16T06:10:00Z (capture line 4683), 0d 00h 00m 03s before now

== recorder ==
task tb-recorder: last run 2026-10-16T06:05:01Z, last result 0 (extended, or already current), next run 2026-10-16T12:05:00Z, missed runs 0
  BTCUSDT 1m: newest bar opens 2026-10-16T06:04:00Z, closed 0d 00h 05m 03s before now
  BTCUSDT 5m: newest bar opens 2026-10-16T06:00:00Z, closed 0d 00h 05m 03s before now
  ETHUSDT 1m: newest bar opens 2026-10-16T06:04:00Z, closed 0d 00h 05m 03s before now
  ETHUSDT 5m: newest bar opens 2026-10-16T06:00:00Z, closed 0d 00h 05m 03s before now

== boots since T0 ==
T0 from the log (first run boot) : 2026-10-10T06:05:20Z  pid 16076  = the ruled T0
boots at or after T0 : 5 (5 run)
  2026-10-10T06:05:20Z  pid 16076  verdict=accepted  run boot  last line 2026-10-12T04:17:43Z  clean stop marker yes
  2026-10-12T19:17:36Z  pid 22304  verdict=accepted  run boot  last line 2026-10-13T06:54:01Z  clean stop marker no
  2026-10-13T07:00:36Z  pid 3444  verdict=accepted  run boot  last line 2026-10-13T07:00:48Z  clean stop marker no
  2026-10-14T06:34:33Z  pid 25352  verdict=accepted  run boot  last line 2026-10-15T08:23:00Z  clean stop marker no
  2026-10-15T11:16:55Z  pid 5224  verdict=accepted  run boot  last line 2026-10-16T06:10:00Z  clean stop marker no

== bookings since T0 (scripts/trade_census.py over the capture) ==
bookings since T0 : 84
  close_booked : 79
  exit_booked : 5
booking event lines since T0 (raw count of the three events) : 84
bookings before T0 : 0   unzoned stamps : 0
census anomalies : 0

== stop rule arithmetic (R-AY), not a verdict ==
days since T0 : 6d 00h 04m 43s  (6.003 d)
bookings since T0 : 84 against 150  (short by 66)
earliest stop : 2026-11-01T00:00:00Z  (first UTC midnight at or after T0 + 21 d)
cap : 2026-11-14T06:05:20Z  (T0 + 35 d; evaluated at the cap if at least 100 bookings)
next UTC midnight : 2026-10-17T00:00:00Z
bookings >= 150 now : no
now at or after the earliest stop : no
next UTC midnight at or after the earliest stop : no
both conditions met at the next UTC midnight on the bookings so far : no
now at or after the cap : no
bookings >= 100 now (the cap's floor) : no
```

### Digests, and the cross-check

Under `F:\trading bot\scratch\s4\2026-10-16\`, each name carrying the invocation's time (`061003Z`):

| file | SHA-256 |
|---|---|
| `061003Z-trading_bot.log` (the frozen copy) | `daa6f508de83aa8cdcd7f4c916e2caa34a78f05d62f395beb97c4c123af35007` |
| `061003Z-capture.log` (the capture) | `daa6f508de83aa8cdcd7f4c916e2caa34a78f05d62f395beb97c4c123af35007` |
| `061003Z-SHA256SUMS.txt` | lists the two lines above; 198 bytes |
| `061003Z-report.txt` (the report, LF) | `dc2f76fc1af5f4ac40a5b8a9959de48e3425cb6dc128aef31b0382a663a02c9d` |
| `scratch\p122\c4_run.txt` (the console output, CRLF from the redirect) | `59f353f50584788889530aead27804a897abfb14bcd359b38b39484d65afd436` |

`scripts/trade_census.py` over the capture (`scratch\p122\c4_census.txt`, SHA-256 `bdadc472d93f4408dd2410c79df4831e213b80a5f219c3b6d60c9766dd173361`): exit 0, 4,683 lines, 86 placements, **84 bookings**, 0 anomalies, 84 of 84
matched to a placement, 2 placements never booked, no quantity differing from its placement. The census's 84 equals the report's 84 and the raw count of the three events.

The S4 clone was read and nothing in it written: the log by a read of its bytes, the process list and the task by two read-only queries, the recorder store by reading its newest CSV; the only files created are
under `scratch\s4`. After the run the clone's `logs` directory still has the mtime `2026-10-14 12:33:40 +0600` it had before it and the same four entries (`.bot.lock` at `2026-10-15 17:17:06`, `.gitkeep`,
`release.log` at `2026-10-14 12:33:40`, and `trading_bot.log`, the bot's own), so no file was created or removed there (a read of the directory, taken after the run and compared with the listing taken at the start of P122). The bot's own log shows its pass at 06:10:00Z, three seconds before the tool's "now".

## 59. M5m S4: P123's halts, and the facts the stop runbook rests on (P123 C1, R-DB, R-DC)

An observation log, so this section only adds. The runbook is `docs/S4_STOP_RUNBOOK.md`; the rulings are quoted verbatim in `docs/NEXT_MILESTONE.md`'s P123 C1 block.

### Halts

`predictions_halts.txt`, SHA-256 `5bb0d87048e03a86738d106e495e94345eadef799e1ca410dbb145c6fc72b631`, written BEFORE any halt ran (P122's H1 was not, and `M5m-513` recorded it).

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `ac07c44`; `origin/main` `ac07c44` if pushed, else `f9c06a4` and 5 ahead | HEAD `ac07c444b088618db45faca6af07b0925aae429a`, `origin/main` `f9c06a40671536a24df8d3a67ba59657125561d3`: the owner has not pushed, and HEAD is 5 ahead (the prompt's own alternative) |
| H2, `git status --porcelain` | empty | empty |
| H3, the gate, bare, to a file | 222 files, mypy 110, 4311 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `f52cd55901d42a00399207db367cd5137380816be34b48ffee8c21feec8a00db`; 4311 passed, 1 skipped in 262.31 s) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 535, gapless, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `247b7dcd7c13d23d2641dc0120f6ca736ebe08cacb34b2f9686f10d54369222a`) |

### The S4 commit against `HEAD`, which decides where the backtest clone is built

MEASURED with `git show <rev>:<path> | sha256sum` and `git diff --stat 45547f1 HEAD -- src`. At `45547f1` and at `HEAD` these are byte-identical (the first 16 hex): `scripts/s4_compare.py` `b8afa603f3b52687`,
`scripts/trade_census.py` `926bdd4674d7fe9f`, `scripts/run_census.py` `e8ce9d55e39183ac`, `config.s4.yaml` `0f170baefb7b41c8`, `config.yaml` `f9e0d73743667c19`, `docs/S4_PREREGISTRATION.md` `49e4fdbba55a5f40`.
`src/` is NOT: 13 files, 3,524 insertions and 53 deletions (`backtesting/candidate.py`, `engine.py`, `evidence.py`, `gate.py`, `overrides.py`, `protocol.py`, `readmark.py`, `selection.py`, `config/settings.py`, `main.py` and the
two strategies and their helpers), among them `478a746` (the research-protocol guard and schema 6) and `79ae42f` (the trend filter). So the backtest clone is built at `45547f10771543b41db42e1cbcb8b5a0a9cf1776`.

### What no run has executed (the runbook's table, in brief)

`grep -n -- '--config' docs/RUN_LEDGER.md` finds no line: no run record names the `--config config.s4.yaml backtest` invocation, and the only backtest of that config is section 40's one-day smoke from the development tree
(`evidence_eligible` false). No ledger section runs `scripts/s4_compare.py --run`. So an eligible backtest of the Testnet store from a vcs clone, and `s4_compare.py` on real inputs, have never been executed
(`M5m-539`). The build of a backtest clone at `45547f1`, `store_check.py` on a Testnet store, and the stop of a bot whose log has rotated are executed in related forms only.

### Instruments

`F:\trading bot\scratch\p113\store_check.py` has SHA-256 `2a5b5530f525b69485f13141db1d73692760cb418203d1be4c7defa581827592` today, equal to section 48's. It tolerates a store with only two intervals (it prints `NO MANIFEST` and continues) by
reading its source; it has not been run on one.

## 60. M5m S4: the first run of scripts/s4_explore.py on a fresh copy of the S4 log, and the comparable-count arithmetic (P123 C3, R-DC)

An observation log, so this section only adds. The tool is `scripts/s4_explore.py` (`d05e8cb`); its output is **exploratory under the ratified CHOSEN line 5 and never replaces `scripts/s4_compare.py`'s result**
(R-DC). The S4 clone was read through `scripts/s4_daily.py`'s share-mode freeze and nothing in it was written; the run is still going (pid 5224), so there is no `M` and the window is whole days up to the last
midnight before the copy.

### The copy and the command

`scripts/s4_daily.py` at `2026-10-16T06:52:14Z` (exit 0, nothing on stderr; `c3_s4_daily.txt`, SHA-256 `fb37084eff5c23dad2bfd16254edc8893b79ad1a972c467ea817a64cbcd5915f`) froze the log to
`F:\trading bot\scratch\s4\2026-10-16\065214Z-trading_bot.log`, 1,083,342 bytes, 4,717 lines, SHA-256 **`3cde3e026c372ca7e90fbb1753f762f48c85fc627ef66ca4cd72a8945c2a2c7d`**, byte-identical to the capture
(`065214Z-capture.log`, the same digest); its last line is `2026-10-16T06:51:01Z`. (The directory also holds a freeze at `061946Z`, which this prompt did not make.) Then:

```
.venv\Scripts\python.exe scripts\s4_explore.py "F:\trading bot\scratch\s4\2026-10-16\065214Z-capture.log" --window-start 2026-10-11T00:00:00Z --window-end 2026-10-16T00:00:00Z
```

Exit 0, nothing on stderr (`c3_explore.txt`, SHA-256 `c1407f3c0a0a541fb7b4667c99b8ab4dfcd51bf2e541b110d5f3f1e8694800fe`, CRLF from the redirect; `065214Z-capture.log` unchanged by it). The header's `sha256` equals the freeze's.

### Predictions against the output

`predictions_c3.txt`, SHA-256 `03ed3832883178ddf3801c800e247a8a55a919c3f9638183945d62c772231b85`, written before the run.

| Figure | Predicted | Observed |
|---|---|---|
| processes; trading processes | 7; 4 (16076, 22304, 25352, 5224) | 7; 4, with first closed candles `2026-10-10T06:06:00Z`, `2026-10-12T19:18:00Z`, `2026-10-14T06:35:00Z`, `2026-10-15T11:18:00Z`, exactly as predicted |
| frozen rule, intervals | 6: 0:00:14, 0:49:43, 15:02:18, 0:06:34, 24:11:12, 2:55:00 | **6, the same six to the second** |
| **frozen rule, total excluded time** | 43:05:01; 42:15:04 inside the window | **43:05:01; 42:15:04** |
| corrected rule, intervals | 3: 15:00:17, 23:40:59 (the refused boot 3444 inside it), 2:55:00 | **3, the same three to the second** |
| **corrected rule, total excluded time** | 41:36:16, all inside the window | **41:36:16, all inside** |
| entries whose entry bar opens in the window | 57 (range 57 to 59) | **58** (0 bookings with no matched placement) |
| **entries excluded, frozen rule** | 2: BTCUSDT signals closing `10-12T19:18:59.999` and `10-14T07:10:59.999` | **2, those two** |
| **entries excluded, corrected rule** | 1: the `10-12T19:18:59.999` entry | **1, that one** |
| both / only frozen / only corrected | 1 / 1 / 0 | 1 / 1 / 0 |
| bookings made in the window (booking time) | 57 (16 + 6 + 1 + 15 + 19 by date) | **57** |
| bookings minus excluded; against 100 | frozen 55, corrected 56, below 100 | **55 and 56, below 100** |
| entries minus excluded; against 100 | frozen 55 to 57, corrected 56 to 58, below 100 | **56 and 57, below 100** |

Every interval and every count was predicted to the second and the unit; the one miss is the entries figure, **58 against a point estimate of 57** (inside the stated 57 to 59): the baseline's 59 placements in the
window and "2 never booked" in the whole capture left it open which side of the window those two fell.

### The output, verbatim

```
==========================================================================
EXPLORATORY (the ratified CHOSEN line 5): never replaces scripts/s4_compare.py's result
==========================================================================
  capture : F:\trading bot\scratch\s4\2026-10-16\065214Z-capture.log
  bytes   : 1083342
  lines   : 4717
  sha256  : 3cde3e026c372ca7e90fbb1753f762f48c85fc627ef66ca4cd72a8945c2a2c7d
  window  : [2026-10-11T00:00:00Z, 2026-10-16T00:00:00Z)

PROCESSES (7), ordered by first line
  pid 27460  first 2026-10-10T05:58:02Z  last 2026-10-10T05:58:02Z  engine started none (not a trading process)  first pass none  first closed candle none  clean stop no
  pid 27176  first 2026-10-10T05:58:16Z  last 2026-10-10T05:58:17Z  engine started none (not a trading process)  first pass none  first closed candle none  clean stop no
  pid 16076  first 2026-10-10T06:05:20Z  last 2026-10-12T04:17:43Z  engine started 2026-10-10T06:05:24Z  first pass 2026-10-10T06:48:00Z  first closed candle 2026-10-10T06:06:00Z  clean stop yes
  pid 22304  first 2026-10-12T19:17:35Z  last 2026-10-13T06:54:01Z  engine started 2026-10-12T19:17:49Z  first pass 2026-10-12T19:20:01Z  first closed candle 2026-10-12T19:18:00Z  clean stop no
  pid 3444   first 2026-10-13T07:00:35Z  last 2026-10-13T07:00:48Z  engine started none (not a trading process)  first pass none  first closed candle none  clean stop no
  pid 25352  first 2026-10-14T06:34:32Z  last 2026-10-15T08:23:00Z  engine started 2026-10-14T06:34:37Z  first pass 2026-10-14T07:12:00Z  first closed candle 2026-10-14T06:35:00Z  clean stop no
  pid 5224   first 2026-10-15T11:16:54Z  last 2026-10-16T06:51:01Z  engine started 2026-10-15T11:17:11Z  first pass 2026-10-15T11:18:00Z  first closed candle 2026-10-15T11:18:00Z  clean stop no

EXCLUDED INTERVALS
frozen rule (down_intervals, imported): 6 interval(s), total 43:05:01, inside the window 42:15:04
  2026-10-10T05:58:02Z -> 2026-10-10T05:58:16Z  0:00:14  pid 27460 -> pid 27176
  2026-10-10T05:58:17Z -> 2026-10-10T06:48:00Z  0:49:43  pid 27176 -> pid 16076
  2026-10-12T04:17:43Z -> 2026-10-12T19:20:01Z  15:02:18  pid 16076 -> pid 22304
  2026-10-13T06:54:01Z -> 2026-10-13T07:00:35Z  0:06:34  pid 22304 -> pid 3444
  2026-10-13T07:00:48Z -> 2026-10-14T07:12:00Z  24:11:12  pid 3444 -> pid 25352
  2026-10-15T08:23:00Z -> 2026-10-15T11:18:00Z  2:55:00  pid 25352 -> pid 5224
corrected rule (R-DC): 3 interval(s), total 41:36:16, inside the window 41:36:16
  2026-10-12T04:17:43Z -> 2026-10-12T19:18:00Z  15:00:17  pid 16076 -> pid 22304
  2026-10-13T06:54:01Z -> 2026-10-14T06:35:00Z  23:40:59  pid 22304 -> pid 25352
  2026-10-15T08:23:00Z -> 2026-10-15T11:18:00Z  2:55:00  pid 25352 -> pid 5224

ENTRIES whose entry bar opens in the window: 58 (bookings with no matched placement: 0)
  excluded under the frozen rule    : 2, kept 56
  excluded under the corrected rule : 1, kept 57
  excluded under both               : 1
  only under the frozen rule        : 1
  only under the corrected rule     : 0
  (each rule adds the 2 bars after an interval; the live side only)
    BTCUSDT  signal bar closes 2026-10-12T19:18:59Z  excluded under: frozen and corrected
    BTCUSDT  signal bar closes 2026-10-14T07:10:59Z  excluded under: frozen

COUNT ARITHMETIC against R-AZ's floor of 100 (facts, not a verdict)
  bookings made in the window (booking time)  : 57
  entries in the window                       : 58
  frozen rule: excluded 2
    bookings in the window - excluded       : 55  (below 100)
    entries in the window - excluded        : 56  (below 100)
  corrected rule: excluded 1
    bookings in the window - excluded       : 56  (below 100)
    entries in the window - excluded        : 57  (below 100)
```

### The comparable-count arithmetic, beside R-AZ's 100

The S4 run is still going and `M` is not set, so every count here is to a date and none is a result. Bookings by booking time on the frozen capture (`grep` over `065214Z-capture.log` for the three booking events): 19 on
`2026-10-10` (before `W`), **57 in `[2026-10-11, 2026-10-16)`**, 8 on `2026-10-16` so far; 84 in all, which equals `s4_daily.py`'s and `trade_census.py`'s count. So bookings since `W` to the copy are 84 - 19 = **65**.

| Count | Frozen rule | Corrected rule |
|---|---|---|
| bookings in `[W, 2026-10-16)` | 57 | 57 |
| minus entries excluded in the window | 2 | 1 |
| **comparable bookings in the whole days** | **55** | **56** |
| bookings since `W` to the copy (65) minus the same excluded entries | **63** | **64** |
| against R-AZ's 100 | below by 45 and 37 | below by 44 and 36 |

R-AZ's floor of 100 is the figure under which a reset or the cap leaves S4 NOT MEASURED; **neither has occurred**, and the stop is R-AY's (the first UTC midnight at least 21 days after `T0` with at least 150 bookings), not
the floor's. At the rate the capture shows, 65 bookings in 5.286 days since `W` (12.3 a day), the comparable count would pass 100 in about 3 days if nothing changed (REASONED; one rate, and the entries to be excluded can
only grow). The two excluded entries are both inside the whole-day window; the second (`10-14T07:10:59`) is excluded by the frozen rule only because it takes the first `reconciliation_pass` of the restarted bot as its
resume, and that pass came 37 minutes after the bot had begun trading (the corrected rule resumes at the first closed candle, `06:35:00`).

### Digests (SHA-256)

| File (under `F:\trading bot\scratch\p123\` unless named) | SHA-256 |
|---|---|
| `predictions_c3.txt` | `03ed3832883178ddf3801c800e247a8a55a919c3f9638183945d62c772231b85` |
| `c3_s4_daily.txt` | `fb37084eff5c23dad2bfd16254edc8893b79ad1a972c467ea817a64cbcd5915f` |
| `c3_explore.txt` | `c1407f3c0a0a541fb7b4667c99b8ab4dfcd51bf2e541b110d5f3f1e8694800fe` |
| `F:\trading bot\scratch\s4\2026-10-16\065214Z-capture.log` | `3cde3e026c372ca7e90fbb1753f762f48c85fc627ef66ca4cd72a8945c2a2c7d` |

## 61. M5m S4: P124's halts, and the tracked store checker shown equal to the scratch one (P124 C1, R-DD, R-DE)

An observation log, so this section only adds. The rulings are quoted verbatim in `docs/NEXT_MILESTONE.md`'s P124 C1 block.

### Halts

`predictions_halts.txt`, SHA-256 `dd67475b0e512b3f66cf05c6b5e061d187bbe4c1ecad93902ec721b00ab7cf91`, written before any halt ran.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `66bfc9b`; `origin/main` `66bfc9b` if pushed, else `f9c06a4` and 8 ahead | HEAD `66bfc9b4a9126cd0898d2e75b35629d299ae1ade`, `origin/main` **`ac07c444b088618db45faca6af07b0925aae429a`**: neither branch of the prediction. The owner pushed through P122's last commit and not P123's three, so HEAD is 3 ahead (`M5m-553`) |
| H2, `git status --porcelain` | empty | empty |
| H3, the gate, bare, to a file | 224 files, mypy 111, 4342 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `949446632e230e6a6e1b683c6a707a1e77a2bbdd19444e3132146d39f67781b4`; 280.89 s) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 552, gapless, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `81c9239832a7dcb701e3d16e5d27218789a043719a802974fadff291d69562df`) |

### `scripts/store_check.py` against the P113 scratch script

The tracked script is `scripts/store_check.py`, SHA-256 `fbba98e583362058b732df05e2d77343f29a945f30006b47d0ca920e21a18241`, tested by `tests/unit/test_store_check.py` (SHA-256
`817dbc750c9bdcccc84435f2820b17743abdde8ea0db45e2dce2416d61204995`, 20 tests). The scratch script is `F:\trading bot\scratch\p113\store_check.py`, SHA-256 `2a5b5530f525b69485f13141db1d73692760cb418203d1be4c7defa581827592`, unchanged
since section 48. Both were run with the development venv's interpreter on the same root, each with its own inventory file, stdout redirected to a file (`cmp` is the instrument; the SHA-256 is of the file):

| Root | Exit (scratch, tracked) | stdout, both | inventory file, both |
|---|---|---|---|
| `F:\trading bot\store\mainnet-historical` (the frozen mainnet store: 1,126 files, 1,100 CSV months, 1,150,169,679 bytes) | 0, 0 | `cmp` equal; `070795048548af4a08e99c2e30bfafd2ee995d557ccc145f789d2a5becb4d46a` | `cmp` equal; `2e152a5d9527d705d7c8e1c42070894fd31d477aff5e0b87631ff89263248018` |
| `F:\trading bot\scratch\p124\testnet_copy`, a `robocopy /E /COPY:DAT` copy of the recorder's `data\historical_testnet` taken at about `10:22Z` (17 files, 4 CSV months, 3,040,820 bytes) | 0, 0 | `cmp` equal; `43fc38755e865a3f9c620424cb705e0ad1f7af18f083e62a16b0405c22a160bf` | `cmp` equal; `aa575482cd4074fd5362391a394a876634899cb606933061003a2cf2f2944b88` |

Both outputs carry the same facts as before. **Mainnet:** `inventory sha256` `6167e1693a486e6666686cda6cd5082d41320dd39af74bac88bbb64c81a3e116` and the inventory file `2e152a52...8018`, **the two figures section 48 recorded**, so the frozen
store is as it was on 2026-10-14; 10 manifests, 0 mismatched, 0 missing or extra, 0 verify problems, 4 snapshots checked and 0 mismatched. **Testnet copy:** `inventory sha256`
`87628ed360fd88b91376e648f06b9d6328bd3dbe3d34b12e60928a4b28c1eb2f`; `NO MANIFEST` for `BTCUSDT` and `ETHUSDT` at `1h`, `4h` and `1d` (six lines); 4 manifests; rows `BTCUSDT 1m` 12,693 and `ETHUSDT 5m` 2,539; 0 mismatched, 0 missing or extra;
0 verify problems; 2 snapshots checked, 0 mismatched. **So the question section 48 left open is answered: on a Testnet-shaped store the checker exits 0.**

**A first attempt compared two empty outputs and proved nothing** (`M5m-554`). Run from Git Bash, `robocopy ... /E ...` was rewritten to `E:/` by the shell's path conversion (`ERROR : Invalid Parameter #3 : "E:/"`, exit 16, nothing copied), and the two
scripts then agreed about an empty directory (`files (no _zips) : 0`). The copy was redone from PowerShell, where it copied 17 files (exit 1, files copied), and the comparison above is of that. Any `robocopy` line of the runbook is for PowerShell.

The tracked script was formatted after the first mainnet run had started, so the first tracked mainnet output was made from pre-format bytes; both runs were repeated on the final bytes (`fbba98e5...8241`) and the figures above are of those.

### The survey of the tracked script

`predictions_c1.txt`, SHA-256 `127fc8b0cd9e5b210a5c0a5593743b60ecaebe7fdb25f5105975a29128d7523d`, written before the survey. **The first run halted** (`survey_c1_out_halted_at_s8.txt`, SHA-256
`9fddbc75d1d69abda988d9d07cbf0d4aa1391be243405a881bfa5ca1b6f1f207`): mutation s3 (the hash updates with the first 1000 bytes of each block) killed 7 where 1 was predicted, because the script compares its own hash of every month file
with the manifest's; and s8 (the exit status ignores "extra") killed 0 where 1 was predicted, because the store's own `verify` also flags an unlisted month, so "extra" was redundant in that test. The test now gives the checker a
`verify` that finds nothing. `predictions_c1_rerun.txt` (SHA-256 `302bc23d0915d8304c874521816045bb581afac576b4c20e51c71c92f1e6d37f`) records the amended predictions before the re-run, which killed 23 of 23 predicted over 11 mutations
(`survey_c1_out.txt`, SHA-256 `57a0a65347b3eaa678202846303998592f5ff8ebaa1c616c9bfa7eae5a1c8724`). Not mutated: dropping "missing" from the exit status, which is unobservable because a listed-but-absent month is also a mismatch.

## 62. M5m S4: Appendix A of the stop runbook, executed over the whole day 2026-10-11 (P124 C2, R-DF)

An observation log, so this section only adds. R-DF, quoted verbatim in `docs/NEXT_MILESTONE.md`'s P124 C1 block, orders the rehearsal. **Every figure of the comparison below is EXPLORATORY under the ratified CHOSEN line 5, was
produced to run the procedure and not to measure S4, and decides nothing.** The S4 clone `F:\trading bot\deploy\45547f107715` was read only through `scripts/s4_daily.py`'s share-mode freeze; the recorder clone's store was read
(copied) and not written; no venue call was made. The window is `[2026-10-11T00:00:00Z, 2026-10-12T00:00:00Z)`, `$M` = `2026-10-12`, one whole day inside `[W, now)` with no restart of the S4 bot in it.

### Every step, its command, its exit code, and its prediction

`predictions_c2.txt`, SHA-256 `49c8796047aeb39cc09160cea189f35ec25a9fad366621c5644d359cd736e00b`, written before step 1. The clone was `F:\trading bot\scratch\p124\bt45547f107715`. Commands were run from PowerShell as the runbook
gives them, stdout to files under `F:\trading bot\scratch\p124\c2\` where the runbook redirects.

| # | Runbook step | Command (abridged) | Predicted | Observed |
|---|---|---|---|---|
| 1 | 6a | `git clone https://github.com/atul-biswash/trading-bot.git $BT` | exit 0 | exit 0 (`Test-Path $BT` False before) |
| 2 | 6a | `git -C $BT checkout --detach 45547f10771543b41db42e1cbcb8b5a0a9cf1776` | exit 0, `rev-parse` the SHA, status empty | exit 0; `rev-parse HEAD` `45547f10771543b41db42e1cbcb8b5a0a9cf1776`; `status --porcelain` empty |
| 3 | 6a | `python -m venv "$BT\.venv"` (the WindowsApps Python 3.12) | exit 0 | exit 0 |
| 4 | 6a | `pip freeze` of the sweep clone's venv, minus the bot, to a constraints file | exit 0, about 60 lines | exit 0, **38 lines** (a miss: the pins are fewer than I guessed) |
| 5 | 6a | `pip install -c <constraints> "binance-trading-bot @ git+file:///F:/trading%20bot/scratch/p124/bt45547f107715@<SHA>"` | exit 0, under 5 minutes | exit 0 (`pip_install.txt`, SHA-256 `816d34288c464b307a9e674fc9f0da92797892dfa7240d4c4d4f516a74e231eb`; not timed); `Successfully built binance-trading-bot`, 39 packages installed |
| 5 | 6a CHECKS | `python --version`; `Test-Path .env`; `Get-FileHash config.s4.yaml`; `git status --porcelain` | `3.12.10`; False; `0F170BAE...2594`; empty | `Python 3.12.10`; False; `0F170BAEFB7B41C87D9F3BC5220A484CE9FA20B0A62758E15CB485E9B0712594`; empty |
| 6 | 6a boot | `python -m trading_bot strategies` | one `boot_provenance` line, `accepted`, `vcs`, intact, commit equal, clean, agree, tracked | **as predicted, but the CHECK as the runbook wrote it could not show it:** `... 2>&1 \| Select-String boot_provenance` printed only `Startup provenance accepted event=boot_provenance`, the console wrapping the record at its width. Redirected to a file (`boot_strategies.txt`, SHA-256 `cae0719c21e650867135ee7380cea056c1b61963d9a29adf0d9ccc100a4a786b`) it reads `verdict=accepted refusal_reasons=none unknown_reasons=none install_kind=vcs code_commit=45547f10771543b41db42e1cbcb8b5a0a9cf1776 code_intact=true code_files_checked=77 checkout_dirty=false dirty_count=0 dirty_paths=none commits_agree=true ... config_tracked=true`. The runbook's step 6 is corrected (`M5m-560`) |
| 7 | 5 / 6b | `robocopy $RSTORE "$BT\data\historical_testnet" /E /COPY:DAT` (a COPY, no junction: R-DF) | exit 1, 17 files | exit 1; 17 of 17 files copied, 9 dirs, 2.89 MB, 0 failed |
| 7 | 5 | tracked `store_check.py` on the source and on the copy | both exit 0; inventory digests equal; 0 problems | both exit 0; `inventory sha256` **`87628ed360fd88b91376e648f06b9d6328bd3dbe3d34b12e60928a4b28c1eb2f` on both**; the two inventory files equal by `Get-FileHash` (`AA575482CD4074FD5362391A394A876634899CB606933061003A2CF2F2944B88`); 4 manifests, 0 mismatched, 0 missing or extra, 0 verify problems, 2 snapshots 0 mismatched (`store_check_recorder.txt` `b1a470279d53ef55110a3966773ae2d465c2c377c13f657d0bafb454a1a82f29`, `store_check_copy.txt` `6cbac938aaa91c1a0dcba28a4b5562762475100b93615c8c65878e7999eab9ac`) |
| 7 | 5 | `record_testnet_klines.py --root data\historical_testnet --verify-only` from the clone | exit 0 | exit 0: BTCUSDT 1m and ETHUSDT 1m 12,693 bars, both 5m 2,539 bars, `2026-10-07T10:32Z..2026-10-16T06:04Z` (1m) and `10:30Z..06:00Z` (5m), 0 gaps, 0 problems; `git status --porcelain` empty; `data\historical_testnet` is a plain directory (`LinkType` empty) |
| 8 | 7 | `python -m trading_bot --config config.s4.yaml backtest --start 2026-10-11 --end 2026-10-12` | exit 0, under 5 minutes, one run directory with three files, `"evidence_eligible": true`, status clean, 12 to 24 trades | **exit 0 in 7 s**; one run directory `20261016T104047945768Z-e00274595855` holding `backtest.log` (26,769 bytes), `run.json` (12,724) and `trades.csv` (6,915); `"evidence_eligible": true,`; `git status --porcelain` empty; 19 trade rows; nothing on the console |
| 9 | 3 | `scripts\s4_daily.py` | exit 0, a new capture | exit 0; capture `104103Z-capture.log`, 1,122,775 bytes, SHA-256 `0f14f8223b4396179fab44dd0d4d09cec57a5a21b6d1e35492ee0db852112957`; 88 bookings since T0 (predicted 90 to 100: a miss low; the log had grown by 4) |
| 10 | 8 | `trade_census.py` over the capture; `s4_compare.py --run $RUN --capture $CAPTURE --window-start ...T00:00:00Z --window-end ...T00:00:00Z --store "$BT\data\historical_testnet"` | exit 0 and 0; no verdict | **exit 0 and 0**; the census: 90 placements, 88 bookings, 0 anomalies, 88 of 88 matched, 2 placements never booked (`trade_census.txt` `68d9b7d1eaa4a5c679e39d5641b3ecaaa8a3e6be729e86ee9722b6d5d123e587`); the compare below (`s4_compare.txt` `8311279bd03e4154ab98d07475b2dbca3399f8a11f0a962a78eb0638232f30a2`) |
| 11 | removal | a reparse-point scan of the clone; `Remove-Item -Recurse -Force $BT` | no junction; exit ok; `Test-Path` False | the scan listed **no reparse point**; `data\` holds `backtests`, `historical_testnet` and `.gitkeep`, none a link; the delete printed no error; `Test-Path $BT` False; `git worktree list` shows the main worktree only |

### The day's figures, EXPLORATORY (`s4_compare.txt`, verbatim)

```
==========================================================================
S4 COMPARISON -- figures only
==========================================================================
  window (entry bar open) : [2026-10-11T00:00:00+00:00, 2026-10-12T00:00:00+00:00)
  capture sha256          : 0f14f8223b4396179fab44dd0d4d09cec57a5a21b6d1e35492ee0db852112957
  run.json sha256         : a86a123dcc3c76438ae43d217be6b62188d0503a6874c598ed26e0af456808d6
  trades.csv sha256       : 855f7ffe00df06814fb9c7803bca3bc80febe3fda39646f6ed6b27f5c371c222
  record schema           : 4
  recorded series         : F:\trading bot\scratch\p124\bt45547f107715\data\historical_testnet

ELIGIBILITY (R-AR)
  backtest run record     : evidence_eligible true
  live boot line       8   : pid 27460 verdict accepted (refusal reasons none)
  live boot line      16   : pid 27176 verdict accepted (refusal reasons none)
  live boot line      24   : pid 16076 verdict accepted (refusal reasons none)
  live boot line    1966   : pid 22304 verdict accepted (refusal reasons none)
  live boot line    2734   : pid 3444 verdict accepted (refusal reasons none)
  live boot line    2746   : pid 25352 verdict accepted (refusal reasons none)
  live boot line    3714   : pid 5224 verdict accepted (refusal reasons none)

R-C FIGURES
  live entries booked          : 18
  backtest entries             : 19
  reproduced on symbol and bar : 16 of 18 = 88.89%
  live per-trade mean (n=18)  : -0.1013%  95% interval [-0.5228%, 0.3201%]
  backtest per-trade mean (n=19) : -0.3804%  position against that interval: inside
  trade counts                 : 19 against 18, difference 1 = 5.56% of live
  live bookings with no placement (not keyable): 0

LIVE ONLY (2)
  ETHUSDT entry bar 2026-10-11T23:30:00+00:00 qty 0.74770000 exit SL at 2448.828043332887521733315501 realised -65.29810400
  BTCUSDT entry bar 2026-10-11T23:52:00+00:00 qty 0.02263000 exit CLOSE at 83854 realised 1.71648550

BACKTEST ONLY (3)
  BTCUSDT entry bar 2026-10-11T04:32:00+00:00 price 82990.134330000000 exit close at 83032.482990000000 realised 0.97063128720000000000
  BTCUSDT entry bar 2026-10-11T13:37:00+00:00 price 83133.105780000000 exit close at 83052.462995000000 realised -1.84430049295000000000
  BTCUSDT entry bar 2026-10-11T16:21:00+00:00 price 83860.129110000000 exit stop_loss at 81237.31200000000 realised -59.45926388370000000000

BOT DOWNTIME (R-AP)
  pid 27460 -> pid 27176: 2026-10-10T05:58:02+00:00 to 2026-10-10T05:58:16+00:00
  pid 27176 -> pid 16076: 2026-10-10T05:58:17+00:00 to 2026-10-10T06:48:00+00:00
  pid 16076 -> pid 22304: 2026-10-12T04:17:43+00:00 to 2026-10-12T19:20:01+00:00
  pid 22304 -> pid 3444: 2026-10-13T06:54:01+00:00 to 2026-10-13T07:00:35+00:00
  pid 3444 -> pid 25352: 2026-10-13T07:00:48+00:00 to 2026-10-14T07:12:00+00:00
  pid 25352 -> pid 5224: 2026-10-15T08:23:00+00:00 to 2026-10-15T11:18:00+00:00
  excluded on both sides (0): signal bar closed in or within 2 bars after an interval

LIVE PLACEMENTS WITH NO BOOKING IN THE CAPTURE (0) -- R-BA, reported

DISAGREEMENTS (6), one cause each from the closed list
  recorded-gap          : 0
  bar differs           : 0
  exact-decimal tie     : 0
  window-edge           : 0
  risk refusal differs  : 1
  fok-unfilled          : 0
  fill-model            : 3
  unexplained           : 2
  [fill-model] live only ETHUSDT signal bar 2026-10-11T23:29:59.999000+00:00: the backtest dispatched and did not fill
  [fill-model] live only BTCUSDT signal bar 2026-10-11T23:51:59.999000+00:00: the backtest dispatched and did not fill
  [unexplained] backtest only BTCUSDT signal bar 2026-10-11T04:31:59.999000+00:00: no recorded input explains it
  [unexplained] backtest only BTCUSDT signal bar 2026-10-11T13:36:59.999000+00:00: no recorded input explains it
  [risk refusal differs] backtest only BTCUSDT signal bar 2026-10-11T16:20:59.999000+00:00: the live bot refused at committed_risk_unknown; the backtest filled
  [fill-model] different exit BTCUSDT signal bar 2026-10-11T15:29:59.999000+00:00: live CLOSE at 83948.56, backtest stop_loss at 80610.84096000000
```

Against the predictions: live entries booked **18** (predicted 16 to 18), backtest entries **19** (12 to 24), reproduced **88.89%** (30% to 90%, near its top), downtime exclusions **0**, exit 0, no verdict line. Read against the pre-registration's
section 7 only to show what the arithmetic looks like, and NOT as S4's result: the count difference, 1 = 5.56% of live, is inside 10%; the backtest mean is inside the live interval; the reproduction is above 80%; two disagreements are
`unexplained` (which section 7 says decide nothing but leave a FAIL undiagnosed). One day with 18 trades is a sample on which none of that is a finding about the backtester.

### What the rehearsal found about the procedure (the point of it)

1. **The step 6 boot CHECK could not show what it claimed** (step 6 above): corrected in the runbook, `M5m-560`.
2. **Everything else ran as written**: the clone, the constraints from the sweep clone's venv, the non-editable install by commit, the boot `accepted` at `45547f1`, the copy and its hash comparison, `--verify-only`, an eligible backtest of
   `config.s4.yaml` in 7 seconds (about 2.5 minutes for 21 days, derived), the freeze, the census and `s4_compare.py`.
3. **The run record did not outlive the clone**: R-DF orders the clone removed, and the run directory was inside it. Its `run.json` and `trades.csv` digests are above and in `s4_compare.txt`, and the figures are in this section, but the
   files are gone. For the stop itself the runbook's step 7 keeps the run in the backtest clone, which step 9 says to record and which is NOT removed by the runbook (`M5m-561`).
4. The step 5 `robocopy` was run from PowerShell; from Git Bash it fails (`M5m-554`).

### Digests (SHA-256; under `F:\trading bot\scratch\p124\` unless named)

| File | SHA-256 |
|---|---|
| `predictions_c2.txt` | `49c8796047aeb39cc09160cea189f35ec25a9fad366621c5644d359cd736e00b` |
| `pip_install.txt` | `816d34288c464b307a9e674fc9f0da92797892dfa7240d4c4d4f516a74e231eb` |
| `boot_strategies.txt` | `cae0719c21e650867135ee7380cea056c1b61963d9a29adf0d9ccc100a4a786b` |
| `c2\s4_daily_freeze.txt` | `a0fae8d0e366bbd40d5666e2cf45b12deec6836c915363b4388bc36a04f5b578` |
| `F:\trading bot\scratch\s4\2026-10-16\104103Z-capture.log` | `0f14f8223b4396179fab44dd0d4d09cec57a5a21b6d1e35492ee0db852112957` |
| `c2\trade_census.txt` | `68d9b7d1eaa4a5c679e39d5641b3ecaaa8a3e6be729e86ee9722b6d5d123e587` |
| `c2\s4_compare.txt` | `8311279bd03e4154ab98d07475b2dbca3399f8a11f0a962a78eb0638232f30a2` |
| `c2\inventory_recorder.jsonl` and `c2\inventory_copy.jsonl` | `aa575482cd4074fd5362391a394a876634899cb606933061003a2cf2f2944b88` (both) |
| the backtest's `run.json` / `trades.csv` (deleted with the clone) | `a86a123dcc3c76438ae43d217be6b62188d0503a6874c598ed26e0af456808d6` / `855f7ffe00df06814fb9c7803bca3bc80febe3fda39646f6ed6b27f5c371c222` |

## 63. M5m S4: P125's halts, the runbook's redirects converted (R-DH) and the evidence-archive step tested (R-DG) (P125 C1)

An observation log, so this section only adds. The rulings are quoted verbatim in `docs/NEXT_MILESTONE.md`'s P125 C1 block. Nothing here wrote to a clone, to the venue or to `F:\trading bot\evidence`; every test below
ran on stand-ins under `F:\trading bot\scratch\p125\` and read, never wrote, the inputs.

### Halts

`predictions_halts.txt`, SHA-256 `570998a37a0a68443559d0d24a10d6a2a717638676838f2f358e4674c90ed2f2`, written before any halt ran.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `cef23c7`; `origin/main` `cef23c7` if pushed, else `ac07c44` and 5 ahead | **both `cef23c7acc3c32cd6875539a4eb165d77a569621`**: the owner has pushed (the first H1 this milestone predicted right) |
| H2, `git status --porcelain` | empty | empty |
| H3, the gate, bare, to a file | 226 files, mypy 112, 4362 passed and 1 skipped, exit 0 | as predicted (`gate_h3.txt`, SHA-256 `9d893d626ab1d0d5dba168f7aadf50129fbb05ab31f1ed6025ad3a567506ab19`; 268.98 s) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 564, gapless, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `a91c5915884fc2f70909ab356d61ca50375f9e2a7653e0eb5a73d8dbfe7c446c`) |

### Every `>` in the runbook's command blocks, kept or converted

Found by reading each ```` ```powershell ```` block of `docs/S4_STOP_RUNBOOK.md` at `cef23c7` for the character `>` (a Python scan of the blocks, not a grep of the file, so prose is out of it). Ten lines held one; nine were redirects, and **every one
of the nine is converted**, because every one writes a file that a later step reads (a `Select-String`, a ledger digest, a comparison, or a person reading it back into the record), and the rule is the owner's. Line numbers are at `cef23c7`:

| Line | Command | Output file | Verdict |
|---|---|---|---|
| 109 | `check_testnet.py ... > "$OUT\check_testnet_after_stop.txt"` | read into the ledger | **converted** to `\| Out-File -Encoding ascii` |
| 129 | `s4_daily.py > "$OUT\s4_daily_final.txt"` | read by the `Select-String` on the next lines | **converted** |
| 180 | `s4_daily.py > "$OUT\s4_daily_after_recorder.txt"` | read by a `Select-String` | **converted** |
| 206 | `store_check.py ... > "$OUT\store_check_recorder.txt"` | read by a `Select-String` | **converted** |
| 208 | `store_check.py ... > "$OUT\store_check_frozen.txt"` | read by the same `Select-String` | **converted** |
| 264 | `trading_bot strategies > "$OUT\boot_strategies.txt"` | read by a `Select-String` | **converted** |
| 338 | `trade_census.py > "$OUT\trade_census.txt"` | read into the ledger | **converted** |
| 340 | `s4_compare.py ... > "$OUT\s4_compare.txt"` | read by the owner and by the ledger | **converted** |
| 372 | `s4_explore.py ... > "$OUT\s4_explore.txt"` | read into the ledger | **converted** |
| 137 | `$CAPTURE = '...\<the UTC date>\<HHMMSS>Z-capture.log'` | none | **kept: the angle brackets are a placeholder, not a redirect** |

Also kept, with the reason: the one `Set-Content "$env:TEMP\s4_constraints.txt" -Encoding ascii` (step 6) is already an explicit ASCII write and needs no change; the `2>&1` that appears in the step 6 correction is prose describing a form no longer used; the files the scripts
write themselves (`store_check.py`'s and `s4_daily.py`'s outputs) are written by Python with explicit encodings. After the edit the same scan finds one `>` in a command block, line 144's placeholder, and eleven `Out-File -Encoding ascii` lines: the nine conversions and the two
`SHA256SUMS-*.txt` manifests of step 8a.

### The conversion, measured

Run from PowerShell with the development venv's interpreter, `... | Out-File -Encoding ascii <file>` (the `\|` form the runbook now holds), then the files read as bytes (`cmp_outputs.py`, `cmp_outputs2.py`):

| Command, on | The earlier output it is compared with | Result |
|---|---|---|
| `trade_census.py` over `104103Z-capture.log` | P124's `>` output (`c2\trade_census.txt`: begins `EF BB BF`, 3 non-ASCII bytes) | the new file has **0 non-ASCII bytes, no byte order mark, 168 lines, the longest 165 characters (not wrapped), and equals the old file line for line**; `Set-Content -Encoding ascii` gives the same bytes as `Out-File` (SHA-256 `a2fd21fe40c1013fb1061bac3081356e16be7888a0b9d978ebda272d4f0be01e` for both) |
| `store_check.py` over the Testnet copy | P124's `out_testnet_tracked.txt` | **byte-identical** (`43fc38755e865a3f9c620424cb705e0ad1f7af18f083e62a16b0405c22a160bf`) |
| `s4_explore.py` over `065214Z-capture.log` | P123's `c3_explore.txt` | **byte-identical** (`c1407f3c0a0a541fb7b4667c99b8ab4dfcd51bf2e541b110d5f3f1e8694800fe`), 50 lines, the longest 194 characters |
| a native command that prints `x` and exits 3, piped to `Out-File` | the exit status | `$LASTEXITCODE` reads **3** after the pipe, the file holds `x` and a line ending (3 bytes) |

Not run in the new form, because only the form is new and their outputs are ASCII: `s4_daily.py` (it also freezes the log), `s4_compare.py` (its run directory was removed at P124), `check_testnet.py` (a venue read) and the boot command (it needs a clone). The runbook's table says so.

### The archive step (R-DG), tested

The command block of step 8a was extracted from the runbook by `extract_8a.py` (SHA-256 `f3a7ae8815e4ff5f9115d57d213c72ea46179257f46dd473e1cd224d4f5a7079` for the script it wrote, `step8a_test.ps1`), with only its first line replaced
(`$ARCH` pointed at `F:\trading bot\scratch\p125\archive_test2` instead of `F:\trading bot\evidence\s4`) and two stand-in lines prepended (`$RUN` a sweep clone's run directory, `20261016...fe368b366f84`, 3 files); the other 16 lines ran **verbatim**,
with `powershell -File`. Result: `Test-Path` printed `False`; both `robocopy` exits were 1 (files copied); `run files: 3 / 3` and `capture files: 16 / 16`; **both `Compare-Object` printed nothing**; the manifests exist, ASCII with no byte order mark
(`SHA256SUMS-run.txt` `0fd92f7f18476c3f10fa5155bb3fa942fe2c8f9018f125af47739b97e9a5cf57`, `SHA256SUMS-captures.txt` `2a8acff6399569cf441ad324d77365c04d02095fa181e6abcb32904c817b4806`). A first test of the same commands in a different directory (`archive_test`)
then **had a byte added to a copied `trades.csv`, and `Compare-Object` printed both hashes with `=>` and `<=`** (the negative control). `F:\trading bot\evidence` was not created or written.

### The install procedure (R-DH)

Named in step 6: `pip install -c <constraints> "binance-trading-bot @ git+file:///<clone>@<SHA>"`, non-editable, with the constraints written by `pip freeze` of the sweep clone's venv in ASCII; measured by section 62 (its steps 4 and 5) and, at other SHAs, by sections 21, 26 and 52.

### The runbook's status table

Rows changed: `s4_daily.py with a redirect` (E) becomes `s4_daily.py piped to Out-File -Encoding ascii` (N: only the pipe is new). Rows added: the `Out-File` pipe for `trade_census.py`, `store_check.py` and `s4_explore.py` (E, this section); the same pipe for `s4_compare.py`,
`check_testnet.py` and the boot (N); step 8a's `robocopy` and `Compare-Object` on stand-ins (E, this section); step 8a on the S4 evidence (N: it does not exist yet).

### Digests (SHA-256; under `F:\trading bot\scratch\p125\`)

| File | SHA-256 |
|---|---|
| `predictions_halts.txt` | `570998a37a0a68443559d0d24a10d6a2a717638676838f2f358e4674c90ed2f2` |
| `gate_h3.txt` | `9d893d626ab1d0d5dba168f7aadf50129fbb05ab31f1ed6025ad3a567506ab19` |
| `findings_h4.txt` | `a91c5915884fc2f70909ab356d61ca50375f9e2a7653e0eb5a73d8dbfe7c446c` |
| `t\census_ascii.txt` and `t\census_setcontent.txt` | `a2fd21fe40c1013fb1061bac3081356e16be7888a0b9d978ebda272d4f0be01e` (both) |
| `t\store_check_ascii.txt` | `43fc38755e865a3f9c620424cb705e0ad1f7af18f083e62a16b0405c22a160bf` |
| `t\explore_ascii.txt` | `c1407f3c0a0a541fb7b4667c99b8ab4dfcd51bf2e541b110d5f3f1e8694800fe` |
| `t\exit3.txt` | `b35e09fa2ced9ebcad9d16336fb961146fe34bfbebc562679da85f8a314c9dca` |
| `step8a_test.ps1` | `f3a7ae8815e4ff5f9115d57d213c72ea46179257f46dd473e1cd224d4f5a7079` |
| `archive_test2\SHA256SUMS-run.txt` | `0fd92f7f18476c3f10fa5155bb3fa942fe2c8f9018f125af47739b97e9a5cf57` |
| `archive_test2\SHA256SUMS-captures.txt` | `2a8acff6399569cf441ad324d77365c04d02095fa181e6abcb32904c817b4806` |

## 64. M5m S4: P126's halts and R-DJ, every program whose output the runbook writes with `Out-File -Encoding ascii` shown to print only ASCII (P126 C2)

An observation log, so this section only adds. The rulings R-DI and R-DJ are quoted verbatim in `docs/NEXT_MILESTONE.md`'s P126 block. Nothing here wrote to the venue, to a deployment or recorder clone, to the S4 backtest clone or to
`F:\trading bot\evidence`. R-DJ's runs used the Appendix A rehearsal clone `F:\trading bot\scratch\p126\bt45547f107715` (built at `45547f1`, `pip install -c`, exit 0; `pip_install.txt`, SHA-256
`5e06d552aad9c40e0331c547554f70af58b5552dcc3fe6ccd227a81b60479811`), the development tree, a fixture and the Testnet read-only. The one side effect is that `s4_daily.py` froze the live log twice more under `scratch\s4\2026-10-16` (a
read of the deployment clone's log in share mode, written to scratch; the runbook's step 3 does the same).

### Halts

`predictions_halts.txt`, SHA-256 `7c8b97f309c8cd77c9f32e1eb58f987194290700f7f6252385d5224e7aa01a7e`, written before any halt ran.

| Halt | Predicted | Observed |
|---|---|---|
| H1, HEAD and `origin/main` | HEAD `df82ebe`; `origin/main` `df82ebe` if pushed, else `cef23c7` and 1 ahead | the else-branch: `origin/main` `cef23c7`, HEAD `df82ebe`, 1 ahead (the owner had not pushed P125's commit) |
| H2, `git status --porcelain` | empty | empty |
| H3, the gate, bare, to a file | 226 files, mypy 112, 4362 passed and 1 skipped, exit 0; the integration flake recurring about 1 run in 6 | as predicted and no flake (`gate_h3.txt`, SHA-256 `1dc3308e1c0c478515698c89b9e58982ce79fd43d1de9894d3043b6136680f7a`; 268.61 s) |
| H4, `check_findings.py milestone/M5l..HEAD M5m` | declared 571, gapless, blockless `934eb45`, exit 1 | as predicted (`findings_h4.txt`, SHA-256 `570718b45204f7ad143a222b71cc78c16a3f37933e8069e083a349a118044f9c`) |

C1 (R-DI) is its own commit and its message holds its measurements; this section is C2's.

### The static check: the text each program can print, read from its source

`static_ascii.py` (SHA-256 `b8506ba0c1dbb326534bb541e1dde9c1164007635217145118ce690b67ca6ab7`) parses each source with `ast` and checks every string constant that is not a docstring, f-string literal parts included, for a character above 127 and for a `?`.
Its output is `static_ascii_out.txt` (SHA-256 `8d59c00df8616c35ec9a8cdca2f0109d48f9b4ec414712bd3f189ab20bd390b8`). Predictions: `predictions_c2.txt`, SHA-256 `96e1e51db226f83d2fc8f9de75963e4f1021e6355fdf0cc9aebad49fc9bf4a66`.

| Program (with the modules whose text it prints) | String constants outside docstrings | Non-ASCII constants | `?` constants |
|---|---|---|---|
| `s4_daily.py` (+ `run_census.py`, `trade_census.py`) | 247 + 63 + 222 | **0** | the two regexes at `trade_census.py:85, 86` and the label `LEG/?` at `trade_census.py:593` |
| `s4_compare.py` (+ the same, + `backtesting/evidence.py`) | 294 + 63 + 222 + 43 | **0** | one regex at `s4_compare.py:459`, and the same three |
| `check_testnet.py` | 142 | **0** | none |
| the boot (`main.py`, `provenance.py`, `logger.py`, `registry.py`), at the tree and at `45547f1` | 92 / 71 + 144 + 33 + 10 | **0** at both | none |
| `trade_census.py`, `store_check.py`, `s4_explore.py` (R-DH's other three) | 222; 70; 110 (+ the modules above) | **0** | the same regexes, and `s4_explore.py:67` |

A `?` is printed only as `LEG/?`, the label `trade_census.py` gives a booking whose leg it cannot name; the regexes are never printed. Non-ASCII characters exist in `main.py` (2), `registry.py` (1) and `check_testnet.py` (1) but only inside
comments or docstrings, which the static check excludes and which are not output.

**What the static check does NOT cover, named so it is not read as covered:** dynamic text. The boot line prints `module_file`, `checkout_root`, `config_path` and `dirty_paths`, which are filesystem paths; `check_testnet.py` prints the venue's
asset names; the refusal paths print exception and OS error text. Any of these would carry a non-ASCII character if the path, the venue's name or the OS message did. None did here (below), and this machine's paths in the runbook are ASCII, but
no run can show a program unable to print one. That is the finding (`M5m-579`).

### The runs, each in the runbook's exact form

The form: `<command> | Out-File -Encoding ascii <file>` from Windows PowerShell 5.1, with `$LASTEXITCODE` read at once. The first set is `c2\`, the second (`c2b\`, run afterwards to record the exit status the first set did not keep)
is `rerun_exit.ps1` (SHA-256 `6f95193c42d6394b20faa4c1b8c097bde1714beab0da142f43fa3a986a33ac87`), with `exits.txt` (SHA-256 `b7c8c219c1fd6d6d4300e8187f4f61c6a3ae8c39b98f698c422b8d4e5a52e345`). The bytes are checked by `check_bytes.py`
(SHA-256 `de5179c615c3d4099fb650c0479cbee97d4e5eebdf325f0cd378ccef69646ed4`): bytes above 127, a byte order mark, the count of `?`, and the line-ending shape; and where a raw UTF-8 capture of the same command exists (the same command with
Python's stdout forced to UTF-8 and read as bytes, so nothing converted it), the `?` count of the file against the raw text's, so a `?` the pipe made would show as file `?` above raw `?`.

| Program, form | Exit | Bytes | Above 127 | BOM | `?` | Raw capture |
|---|---|---|---|---|---|---|
| the boot, `Set-Location $BT` then `& $PY -m trading_bot strategies \| Out-File ...` (`c2\boot_from_clone.txt`, SHA-256 `60a43b8d70e6a4b687279762f9ac62399de1fe186d0e2ff95b45ed86714b4661`) | 0 | 2,401 | 0 | no | 0 | raw (`boot_from_clone_raw_utf8.txt`, SHA-256 `597b779ea061ee4183464e96b001f8bc5c0587805e8052f94bf6f59b0d625ea6`): 0 non-ASCII, 0 `?`, 2,401 characters |
| `s4_compare.py` through its real command line over a fixture (`c2\s4_compare_fixture.txt`, SHA-256 `9adce1637cf4f53056a608147e91b212e50bbddb6cecd7d088d8f2d1228fe0f3`) | 0 | 2,151 | 0 | no | 0 | **byte-identical** to the raw UTF-8 capture (same SHA-256), and to the second run's file; equal line for line |
| `check_testnet.py --symbol BTCUSDT --candidates BTCUSDT,ETHUSDT`, read only (`c2\check_testnet_after_stop.txt`, SHA-256 `153765dd63b77a5049ded34955562c7274c0ec314a96721ad5334c809d21717d`) | 0 | 3,061 | 0 | no | 0 | raw (SHA-256 `5120f8be146835695f33eb25cb2ac79f2c37269b6d96d70116f52d15ab30c71e`): 0 non-ASCII, 0 `?`, 3,061 characters |
| `s4_daily.py` (`c2\s4_daily_final.txt`, SHA-256 `3f49cf7b407ebddcac9c31754d0e908223afb26975b5b13ecac03f62c5a936a0`) | 0 | 2,793 | 0 | no | 0 | none taken (its text includes the time of the run) |
| the second set, `c2b\`: the boot, `s4_compare.py`, `s4_daily.py`, `check_testnet.py` | 0, 0, 0, 0 | 2,401; 2,151; 2,793; 3,061 | 0 each | no | 0 each | `s4_compare.txt` SHA-256 `9adce1637cf4f53056a608147e91b212e50bbddb6cecd7d088d8f2d1228fe0f3`, the first set's again; the others differ in a timestamp only and have the first set's sizes |

Every file is CRLF throughout (the pipe's line ending; 32, 46, 55 and 50 lines for the four), as section 63 found for the other three programs. The fixture is `make_fixture.py` (SHA-256 `76c427e088c208c81105a9bf790b87995bd42b99f39117a84a9dea76e3b3045a`):
a capture (`fixture\live.log`, SHA-256 `948fe74cbf028d5c4663b4c1a0b52616ab5b0691ed25710fcccdab8c95ac2403`) and a run directory (`run.json` SHA-256 `b4be1194d0815230b1376d759ce4facde890a81f536356e97123145b619e02b6`, `trades.csv` SHA-256
`660637e5275f21a94d6227df34d647abec119e5d6b3248b6ae37f1b5a3e5639e`) in the shapes `tests/unit/test_s4_compare.py` builds, and the Testnet store copy of P124 as `--store`. **Nothing in it is S4 data**; its comparison prints one `[unexplained]` disagreement
and one excluded entry because it was built to.

**The negative control, so a clean result could have been otherwise.** A native command printing `caf` and an e-acute, piped to `Out-File -Encoding ascii`, gave the bytes `63 61 66 3F 20 6F 6B 0D 0A` (`caf? ok`, `c2\control_nonascii.txt`, SHA-256
`f6d931df2f54a542d401cb973f9c82a43022798eee322825b958608f500c099e`), while its UTF-8 capture held `63 61 66 C3 A9 ...` (`control_nonascii_raw_utf8.txt`, SHA-256 `f725395bead49e38b7bf844fe91972d828aaaa942d8696b6a06939efaf151c67`). So the pipe does turn a
non-ASCII character into `?`, the check above would have counted it as a `?` above the raw capture's, and the zeros are a measurement.

### A defect the runs found: the boot is read from the clone

The runbook's step 6 CHECK ran the boot without saying from which directory. The boot reads the LAUNCH directory's config and checkout. Run from the development tree with the clone's interpreter (`c2\boot_from_dev.txt`, SHA-256
`3c458612c9a31c44f15ec851e5e5bdc9c49b8121ee687be36a34621dfdad88c8`) it printed `verdict=refused`, `refusal_reasons=checkout_dirty=true;...;commits_agree=false;...`, `checkout_root` the DEVELOPMENT tree, `checkout_commit` `df82ebe` against `code_commit`
`45547f1`, `dirty_count=5` and the development tree's `config_path`. I had predicted exactly this (a different `config_path` and `checkout_root` and a verdict that is not `accepted`). Run from the clone it printed `verdict=accepted`, `install_kind=vcs`,
`code_intact=true` over 77 files. Corrected in the runbook: `Set-Location $BT` precedes the boot line, with a note (`M5m-578`). Both files hold only ASCII bytes and no `?`.

### Prediction against observation

| Prediction (`predictions_c2.txt`) | Observed |
|---|---|
| R1 the boot from the clone: exit 0, 0 above 127, 0 `?`, accepted over 77 files; from the development tree a different verdict | as predicted, both |
| R2 `s4_daily.py`: exit 0, 0 above 127, 0 `?` | as predicted |
| R3 `s4_compare.py` over a fixture: exit 0, 0 above 127, 0 `?`, equal to the raw capture | as predicted; byte-identical, not only line for line |
| R4 `check_testnet.py`: exit 0, **about 516 asset lines**, 0 above 127, 0 `?`, raw counts 0 and 0 | exit 0, 0, 0 and raw 0 and 0 as predicted; **the line count was wrong**: the output is 55 lines, with 27 `free=` lines, because the program prints a bounded listing of 517 non-zero balances (`balances: 517 asset(s) with a non-zero balance`) and not one line per asset. A wrong figure in the prediction, not in the result |
| the gate for C2: 228 files, mypy 112, 4373 passed and 1 skipped, exit 0; numstat about 130 | recorded in the commit message |

### What this shows, and what it does not

For the four programs the runbook pipes into `Out-File -Encoding ascii` and not covered by section 63, on these inputs: every output file is pure ASCII, has no byte order mark and no `?`, and equals the raw UTF-8 text where one was taken; every command exited 0; and the
static check finds no non-ASCII character in any string a program prints. The runbook's table rows for these are E.
It does **not** show that a different input cannot print one: a path, an exception message, an asset name or an OS error is text the programs echo and the source cannot bound. The practical bound is that the runbook's paths, the clone's, the venue's
current asset names and this machine's messages are ASCII. If an S4 output ever shows a `?` where text was expected, compare it with a raw capture as `check_bytes.py` does before reading the file as evidence. No frozen file was changed.

### Digests of this section's other files

`static_ascii.py`, `check_bytes.py`, `make_fixture.py`, `rerun_exit.ps1` and `runbook_edit.py` (SHA-256 `a66a485d36dfe9e286e1435357fff74dc1acfeec8f0bd2278a0c55f109791968`) are under `F:\trading bot\scratch\p126\`; `runbook_edit.py` is the script that edited the runbook (four
sites, one asserted match each, LF kept).

## 65. M5m S4: P128's halts and the predictions written before any measurement (P128 C1, R-T)

An observation log, so this section only adds. P128 is a docs-only prompt: the S4 correction rulings R-DK to R-DN, their measurements and their records. This section is committed BEFORE any measurement of the 2026-10-23 capture, as the prompt requires (R-T). The rulings themselves are quoted verbatim in `docs/S4_CORRECTION_P128.md` (C2), and the file name was the owner's answer to a halt (below).

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| `git status` not clean | `git status --porcelain` | empty |
| HEAD differs from `<HEAD>` | the prompt's `<HEAD>` was an unfilled placeholder | HEAD `d6c1c5a84e8361fa54e55f02239183e4fba7dc2f`, equal to `origin/main`; unchanged since P126 C2, the last commit this session made. **The check could not be run as written and was read as "nothing has moved since P126"; the owner is asked to confirm** |
| a command would write under `deploy\45547f107715` or call the venue | every command below | none does: the only access to `deploy\` was a directory listing of `logs\` (names, sizes, write times; no file opened), and no socket was opened |
| a frozen file differs from its pre-registered digest | `Get-FileHash` | `scripts/s4_compare.py` `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08` and `scripts/trade_census.py` `926bdd4674d7fe9fa418fb5e8b67f3d089012255ba8f478492a043fbbe35d9bb` equal the pre-registration's section 9; `config.s4.yaml` `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594` equals its section 6; `docs/S4_PREREGISTRATION.md`, `docs/research/PROTOCOL.md` and `scripts/run_census.py` are unmodified from HEAD (the tree is clean; the pre-registration pins no digest for the last) |
| the reserved window would be read | the reserved window is S7's research window, 2024-01-01 to 2025-04-01 (`docs/research/PROTOCOL.md`) | nothing in P128 reads it |
| **no R-AO naming convention for a correction file** (the prompt's own halt) | grep of `docs/`, `docs/research/` and the git history for a correction file or a naming rule | **FOUND NONE.** R-AO and the pre-registration's header require only "a NEW file that says what it supersedes"; no earlier correction file exists. **The prompt's halt applied and the session stopped to ask.** The owner answered: `docs/S4_CORRECTION_P128.md` |
| the owner's stated cause of the `08:05:33Z` stop | the prompt's field was the placeholder `<OWNER FILLS IN>` | **NOT SUPPLIED.** The owner, asked how to record it, expressed no preference; section 66 therefore records "not supplied in P128" and does not guess |
| R-DM's terms | "unbroken run" and "followed by" have no stated limits | the owner ruled the reading: **an unbroken run is consecutive `reconciliation_untrusted` passes for one symbol with no pass between them that reports that symbol's position active; "followed by" means a refusal logged while that run is still unbroken.** Recorded in the correction file as a reading of R-DM, not a change to it |

The bare gate before any commit (`gate_before.txt`, SHA-256 `f3393bd90a21bcdbe7b5f25c02649434ec9269c764602ad291a04a87c7e1e4f5`): ruff check clean, 228 files formatted, mypy 112 source files, 4373 passed and 1 skipped, exit 0, 485.66 s, the tree still clean afterwards.

The capture is `F:\trading bot\scratch\s4\2026-10-23\184839Z-capture.log`, 3,874,511 bytes, SHA-256 `c8fc92ad14babb4569e080b273ca3bd338208d58acb2a21394d076155419a0dc`: the size and digest both equal the prompt's. **An observation the prompt did not ask for:** the deploy clone's `logs\` directory shows `release.log` written at 2026-10-24 00:56:48 and `trading_bot.log` and `.bot.lock` at 01:05 (the machine's local time, which is UTC+6 by the earlier freezes' file times), after the capture was frozen. That suggests the owner released a record and the bot ran again; **no file was opened and nothing is concluded**, and R-DN says a restart is recorded in a later prompt, after it has happened.

### The predictions

Written before the capture was parsed for episodes. **They are not blind, and the record says so:** P127 read the 2026-10-22 capture for the 2026-10-11, 2026-10-13 and 2026-10-21 episodes, and the code of `down_intervals` and `s4_explore.py`. Items (a) and (b) rest on that read and on the ratified reading of R-DM; items (c) and (d) rest on the source. Where the executing session disagrees with the prompt's wording, both are written.

| | The prompt's prediction | The executing session's prediction, and why |
|---|---|---|
| a | exactly two episodes satisfy R-DM (ETH 2026-10-13, BTC 2026-10-21) | **two or three, with two the most likely (about 55%).** The two are certain to be there. The third candidate is the 2026-10-11 BTCUSDT episode, see (b) |
| b | the 2026-10-11 `committed_risk_unknown` lines do not satisfy R-DM's start condition | **about 40% that this holds.** P127 saw `reconciliation_untrusted` at `16:00:01Z` and `16:20:01Z` and a `committed_risk_unknown` BUY refusal at `16:21:00Z`, with 29 `exit_unbookable` lines to `16:51:01Z` (section 46). P127's listing printed only lines whose text changed, so passes between those two may also carry the untrusted line. If they do, the run is unbroken across the refusal and the episode SATISFIES the start condition. What can break it is one `states="active=1"` pass line logged at `16:20:01Z` after the untrusted line, which the reading counts. The measurement decides |
| c | the ETH episode from R-DM's start to its process's last line is shorter than 24 hours and lies mostly inside the frozen `down_intervals` | **the first clause true, the second false.** The ETH run starts about `02:59Z` on 2026-10-13 and ends at pid 22304's last line, `06:54:01Z`: about 3 h 55 m, under 24 h. **R-DM ends the interval at the process's last line, which is where the frozen interval begins** (`2026-10-13T06:54:01Z -> 07:00:35Z`, P127's `s4_explore.py` run on the 2026-10-22 capture). The two touch and do not overlap, so I predict the share inside the frozen intervals is **0, and the union is the R-DM span plus the frozen ones**. The frozen exclusion's two-bar tail adds nothing to the overlap, since both tails lie after the same boundary |
| d | the frozen `down_intervals` rule, applied to a capture whose last process has stopped with no successor, produces an interval open to the end of the capture | **false: it produces no interval at all.** `down_intervals` builds intervals only from `pairwise(order)` of consecutive processes, so a last process with no successor yields none; `s4_explore.py`'s corrected rule is the same `pairwise`. I predict the frozen rule prints the same 7 intervals as for the 2026-10-22 capture (the last ending `2026-10-20T09:38:01Z`) and the corrected rule the same 4, with **nothing from `2026-10-23T08:05:33Z` to the end of the capture**, and no process after pid 14600 in this capture. This is also why R-DM carries its own end rule |

The executing session adds the predictions for the measurements of step 3, with their reasons:

| | Prediction |
|---|---|
| e | **BTC episode:** start `2026-10-21T13:11:00Z` (the first untrusted pass, under the ratified reading), end `2026-10-23T08:05:33Z` (the clean-stop line, if it is pid 14600's last), about 42 h 54 m; closed, not open, since the process stopped inside the capture |
| f | **refusals in that episode:** `committed_risk_unknown` BUY refusals about **30** (21 to `2026-10-22T19:04Z` at 0.70 an hour, plus 13 h more; range 26 to 34); `close_halted` lines about **58** (40 to `17:55:01Z` on the 22nd at 1.3 an hour, plus the same 13 h; range 50 to 66, two lines per refused CLOSE) |
| g | **protective-leg exits:** 12 booked (`exit_booked`) and 2 partial-expired (orders 1867449 and 5431129), so **2 of 14**, unchanged from the 2026-10-22 capture because no position has booked since `2026-10-21T19:20:05Z` |
| h | **entries per day in uptime:** about **18** (the seven full days 2026-10-14 to 2026-10-20 booked 16, 19, 21, 19, 20, 17 and 19, mean 18.7; the window's 164 over about 8.9 days of uptime is 18.4); the whole-window figure of 15.6 includes the outages |
| i | **B's denominator, from the frozen source:** `figures_of` divides `abs(N_bt - N_live)` by `N_live`, where `N_live` is the number of live entries **kept after** `exclude_downtime`, not the booked count and not `N_bt` |
| j | **log growth while latched:** about **0.98 MB a day** (the capture grew by 529,661 bytes between the 2026-10-22 and 2026-10-23 freezes, over the 13 hours from `2026-10-22T19:05Z` to the stop at `08:05:33Z`) |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. Items (b) and (c) are the two where the prompt and the executing session differ, and the section that records the measurements (section 66) states which of the two was right.

## 66. M5m S4: the clean stop of pid 14600 at 2026-10-23T08:05:33Z, the latch on order 5431129, and what P128 measured (P128 C3)

An observation log, so this section only adds. The rulings (R-DK to R-DN), the owner's three answers and the full measurements are in `docs/S4_CORRECTION_P128.md` (commit `b3d4f8b`); the predictions are in section 65 (commit `7f63985`). This section records the events themselves. **No restart is recorded here**: R-DN says one is recorded in a later prompt, after it has happened, and none is recorded in the capture below. Every citation of a capture line is by timestamp, not by line number (`M5m-582`).

The capture is `F:\trading bot\scratch\s4\2026-10-23\184839Z-capture.log`, 3,874,511 bytes, SHA-256 `c8fc92ad14babb4569e080b273ca3bd338208d58acb2a21394d076155419a0dc`, the owner's `s4_daily.py` freeze of 2026-10-23T18:48:39Z.

### The stop

| When (UTC) | Process | Line |
|---|---|---|
| `2026-10-23T08:05:30Z` | pid 14600 | `Received SIGINT; shutting down gracefully` (`trading_bot.main`) |
| `2026-10-23T08:05:33Z` | pid 14600 | `Trading engine stopped event=engine_stopped clean_shutdown=True` (`trading_bot.engine.live_engine`), **the last line of the process and of the capture** |

It has the shape of the two earlier clean stops: `2026-10-12T04:17:41Z` SIGINT then `04:17:43Z` stopped (pid 16076), and `2026-10-20T01:34:42Z` SIGINT then `01:34:44Z` stopped (pid 5224). **The cause the owner stated for this stop is NOT SUPPLIED**: the prompt's field was the unfilled placeholder `<OWNER FILLS IN>` and the owner expressed no preference when asked how to record it. The log shows that a SIGINT was delivered and nothing about who sent it or why. The owner may add the cause in a later section.

**The log did not grow after the stop.** The owner's freeze of `2026-10-23T08:05:51Z` (`080551Z-capture.log`) and the freeze of `18:48:39Z` have the same SHA-256, `c8fc92ad14babb4569e080b273ca3bd338208d58acb2a21394d076155419a0dc`, so nothing was logged for the 10 h 43 m between them, and pid 14600 is the last process in the capture. The same directory holds a third freeze, `190521Z-capture.log`, 171 bytes, written at `2026-10-24 01:05` local time; **it was not opened** (P128 reads the one capture it names, and a successor process is the restart R-DN reserves for a later prompt), and neither was any file under the deploy clone.

### The latch on order 5431129 (list 183218)

| | |
|---|---|
| placed | `2026-10-21T13:09:00Z`, BTCUSDT, 0.02233000 at a limit of 83833.77000000, stop 82157.10000000, `entry_bar_time` `13:08:59.999Z` (`event=order_placed`; the list id occurs once in the capture, on that line) |
| first untrusted pass | `2026-10-21T13:11:00Z`, `states="active=1,unknown=1"`: *"BTCUSDT leg SL reports EXPIRED with 0.01041000 executed; the fill PRICE is unmeasured, so this state is refused rather than interpreted; BTCUSDT leg TP was NOT YET QUERIED -- the point-query budget was exhausted before reaching it"* |
| the state it stayed in | SL `EXPIRED`, `0.01041000` of `0.02233000` executed (**46.6%**); TP `EXPIRED`, `0E-8` executed (the first `close_planned` that read both, at `13:37:59.999Z`, says `sl_status=EXPIRED sl_executed=0.01041000 tp_status=EXPIRED tp_executed=0E-8`) |
| what the bot did | `exit_book_refused` for order 5431129 **1,702 times**, from `2026-10-21T13:11:00Z` to `2026-10-23T08:04:02Z`; BTCUSDT named in 1,704 `reconciliation_untrusted` lines over the same span; the position never booked |
| `CLOSE` signals | 33 refused as `close_halted`, the first (`close_planned decision=halt`, *"A partially executed protective leg is UNMEASURED (Q-C section 10) and is never sold against"*) at `2026-10-21T13:37:59.999Z`'s candle, the last `close_halted` line at `2026-10-23T07:05:01Z` |
| `BUY` signals | 36 refused at `committed_risk_unknown` (32 BTCUSDT, 4 ETHUSDT), the first at `2026-10-21T13:57:00Z`, the last at `2026-10-23T07:10:01Z`; **no order list was placed after `13:09:00Z`** |
| the other position | ETHUSDT's last open position booked normally at `2026-10-21T19:20:05Z` (`close_booked` order 4857803); after it BTCUSDT was the only position and the passes read `states="unknown=1"`, as the last one, at `2026-10-23T08:04:02Z`, does |
| the residual | 0.02233000 less 0.01041000 is **0.01192000 BTC** that the ledger holds and the bot would not sell. **That figure is by subtraction; no venue read of the balance was made** (UNMEASURED at the venue) |

The earlier latch of the same kind is ETHUSDT order 1867449 (list 71012), `2026-10-13`, recorded in sections 46 and 49: stop leg 0.0756 of 0.764 executed, a run of 3 h 54 m 59 s of untrusted passes from `02:59:02Z` to pid 22304's last line at `06:54:01Z` with 2 `committed_risk_unknown` refusals, a boot that refused over the record at `07:00:48Z`, and a restart at `2026-10-14T06:34:32Z`.

### What P128 measured, in one table

The three episodes R-DM finds under the owner's reading, and how the predictions fared. The correction file has every column.

| Episode | R-DM interval | Duration | BUY refusals | Predicted by the prompt |
|---|---|---|---|---|
| BTCUSDT 2026-10-11 (a `CLOSE` sell that executed partly) | `2026-10-11T16:00:01Z` to `2026-10-12T04:17:43Z` | 12 h 17 m 42 s, of which 11 h 26 m 42 s after the last evidence | 1 | **not an episode: wrong** |
| ETHUSDT 2026-10-13 (order 1867449) | `2026-10-13T02:59:02Z` to `06:54:01Z` | 3 h 54 m 59 s | 2 | an episode: right; "mostly inside the frozen intervals": **wrong** (overlap 0) |
| BTCUSDT 2026-10-21 (order 5431129) | `2026-10-21T13:11:00Z` to `2026-10-23T08:05:33Z` | 1 d 18 h 54 m 33 s | 36 | an episode: right |

Prediction (a), **exactly two episodes, was wrong: three**; (b), the 2026-10-11 lines do not qualify, was wrong; (d), the frozen `down_intervals` yields an interval open to the capture's end, was wrong: **it yields none**, and so does `s4_explore.py`'s corrected rule (7 and 4 intervals, nothing after the stop). **Section 65 said this section would state which of the prompt and the executing session was right where they differed, (b) and (c): the executing session was.** It had put about 40% on (b) holding and predicted (c)'s second clause false from the source; both outcomes went its way. Its own other predictions are scored in the correction file, section 4.

### Digests of this section's files

`measure.py` (the first, wrong implementation) `ccc208ec2e480d4b8bea76168dc59d5c354588d0d5aee8c3aa8bfdf72ded706a`, output `2d95a2e6d3c682ad74aa96ee234e7d2feb34beb4c9b9b179338544d4f731fb2b`; `measure2.py` `bca989083897e285264801e5a48f19f45d2a1a8d29783addb66a808b053d78e9`, output `4e8c3952f968c5fc155469fb24a562a8dbb216c600666749d0974d1627ff0d4b`; the `s4_explore.py` run over this capture, `5d261aadccf28578d20c969f865db4ba55604ae454ac5d2069b81ae3130f70b4`, all under `F:\trading bot\scratch\p128\`.

## 67. M5m S4: the owner's restart of 2026-10-23 and boot #7 (pid 20100), with the predictions made before the capture was parsed (P129 C1, then C3)

An observation log, so this section only adds. P129 is a docs-only prompt: R-DO, the P128 episode table re-measured under it, and the record of the restart that P128 left for a later prompt (R-DN). This section is begun in C1 with the halts and the predictions, committed BEFORE any measurement of the capture (R-T), and completed in C3 with the restart's facts; nothing in what C1 writes is altered by C3. R-DO itself is in `docs/S4_CORRECTION_P129.md` (C2).

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| `git status` not clean | `git status --porcelain` | empty |
| HEAD is not `0586f48` | `git rev-parse HEAD` | `0586f48033a68dbb112794efef3dea74e5bcc08d`, the P128 C4 commit; P128's four commits `7f63985`, `b3d4f8b`, `4e1bef9`, `0586f48` are unpushed, as the prompt says |
| a command would write under `deploy\45547f107715` or call the venue | every command in this prompt | none does. The one access to the deploy clone is the share-mode COPY of `logs\release.log` into scratch that the prompt names (C3): a read, written elsewhere. No socket is opened |
| a frozen file differs from its digest | `Get-FileHash` | `scripts/s4_compare.py` `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08`, `scripts/trade_census.py` `926bdd4674d7fe9fa418fb5e8b67f3d089012255ba8f478492a043fbbe35d9bb`, `config.s4.yaml` `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594` and `docs/S4_PREREGISTRATION.md` `49e4fdbba55a5f407d8db130ebdc6cf68fc13813a101ab7849e4740050c6566f` are unchanged; `docs/S4_CORRECTION_P128.md` is `36327c4abc2900b80f2961541e25d9e5da727fd08a1c6352ef2ac5056b05daa6` and is not edited |
| the capture's size or SHA-256 differs | `Get-Item` and `Get-FileHash` | `F:\trading bot\scratch\s4\2026-10-23\190521Z-capture.log` is **3,877,171 bytes**, SHA-256 `ea58a17b59f309f5c8963a9c95d7005ca7612813c09dd61475707ff4913feaed`, both equal to the prompt's |

The bare gate before any commit (`gate_before.txt`, SHA-256 `a3db21aaed79cb42f98ee9ae5c46955341a4f752c2f4833831449eb12d05ee29`): ruff check clean, 228 files formatted, mypy 112 source files, 4373 passed and 1 skipped, exit 0, 329.64 s, the tree still clean afterwards.

**No placeholder was left unfilled this time**, and the stop cause is the owner's own words, recorded in C3.

### A correction to section 66, found by the halt check

Section 66, and the C3 commit message of P128, say the freeze `190521Z-capture.log` was **171 bytes** and "tiny". **That was wrong.** The directory listing P128 read was cut to a column range (`cut -c30-120`) that dropped the leading digits of each size, so `3,877,171` read as `171` and `3,874,511` as `511`. The capture is 3,877,171 bytes: 2,660 bytes longer than the `18:48:39Z` freeze (3,874,511), which is the log of the process that booted after the stop. Section 66 stands as the record of what P128 believed; this annotation says what is true. **What survives:** every other figure in section 66, each of which came from a script and not from that listing, and the finding it was attached to (`M5m-607`): the file was not opened in P128. `M5m-610` records the error.

### The predictions

Written before the capture was parsed. **They are not blind, and the record says so:** the halt check above read the capture's size and SHA-256; P128 read the 2026-10-23 capture up to the stop; and R-DO's wording was taken from P128's own script. Where the executing session disagrees with the prompt's wording, both are written.

| | The prompt's prediction | The executing session's prediction, and why |
|---|---|---|
| a | under R-DO the 2026-10-11 BTCUSDT episode ends at `2026-10-11T16:54:00Z`, duration 53 m 59 s | **the same, about 80%.** The first pass after the run's start that reported as many positions as the inventory holds and carried no `unknown` count is the `16:54:00Z` pass (`positions=2`, `states="active=2"`), P128's table. What can move it is the inventory: it is built from placements and bookings, and the 2026-10-11 position closed through a path that books nothing, so the inventory may still hold it |
| b | the ETHUSDT 2026-10-13 and BTCUSDT 2026-10-21 episodes are unchanged from P128 | **unchanged, about 75%.** R-DO breaks a run on `positions` equal to the inventory and no `unknown` count in the states, and does not ask whether the symbol is named. It differs from P128's rule there. A pass in either episode that covered every position and read `diverged` rather than `unknown` would now break it |
| c | the R-DO union keeps 161 of the 164 live entries in `[2026-10-11, 2026-10-22)`, the same as the frozen rule | **160, one fewer, about 65%.** The BTCUSDT entry whose signal bar closed at `2026-10-11T16:52:59.999Z` is the first of the eight P128 found in R-DM's tail. It lies before `16:54:00Z`, so it is INSIDE the R-DO interval, and the exclusion adds two bars after it. Frozen 3 plus that 1 is 4 excluded, 160 kept. The other seven of P128's eight fall after `16:54:00Z` and are no longer excluded |
| d | pid 20100 has logged no `reconciliation_untrusted` line | **true, about 90%,** and in fact no `reconciliation_pass` line either: the release removed the BTCUSDT record, no position is open, and a pass is logged only while one is. The capture holds only about 75 seconds of the process |

The executing session adds:

| | Prediction |
|---|---|
| e | **Boot #7:** the first lines of pid 20100 in the capture are the banner and a `boot_provenance` line with `verdict=accepted`, `install_kind=vcs`, `code_intact=true`, `code_commit=45547f10771543b41db42e1cbcb8b5a0a9cf1776`, `checkout_dirty=false`, `commits_agree=true`, `config_tracked=true` and `config_sha256=f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`, then `Trading engine started: BTCUSDT/1m, ETHUSDT/5m`. The first `boot_provenance` stamp is `2026-10-23T19:04:06Z`, as the prompt says |
| f | **The 2,660 added bytes are all pid 20100's.** No line of any earlier process is added: the earlier part of the file is byte-identical to the `18:48:39Z` freeze |
| g | **`release.log`** (550 bytes at the time of P128's listing) names BTCUSDT, the time `2026-10-23T18:56:48Z` and both store digests the prompt gives (`5d2c4cc3...` then `18d97b07...`), and nothing about the sale, which is outside the ledger by design |
| h | **B recomputed with all three episodes** (the latch days: 1.788 d for 2026-10-21, 0.163 d for 2026-10-13, 0.037 d for 2026-10-11 under R-DO, 1.988 d in all): surplus 30.9 at the whole-span rate and 38.6 at the uptime rate, so `N_live` must reach 309 and 386. With the same rate used for the live entries still to come (8.2 days from `19:05Z` on the 23rd to `M`), the final kept count is about 288 and 320: **FAIL at both rates when each rate is used consistently, by 7% and 17%.** At the whole-span surplus with the uptime rate for the future (309 against 320) it is a narrow pass; a mixed rate has no basis. I therefore agree with "likely FAIL" and do not agree with a flat "FAIL at both" |

| i | **The downtime after the stop, from the source of the two rules:** `down_intervals` takes a process that has logged no pass to have resumed at its FIRST LINE ("never longer than the evidence supports"), so with pid 20100 present and no pass of it in the capture the frozen rule returns **8 intervals**, the new one running from `2026-10-23T08:05:33Z` to pid 20100's first line, about `19:04:0xZ`; and `s4_explore.py`'s corrected rule returns **5**, the new one ending at pid 20100's first closed candle, `2026-10-23T19:05:00Z`. Both grow when the first pass is logged, to that pass |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. Items (a) to (d) are the prompt's, with (c) the one where the executing session disagrees on the number.

### The restart, every fact cited by timestamp or digest (completed in P129 C3)

The capture is `F:\trading bot\scratch\s4\2026-10-23\190521Z-capture.log`, 3,877,171 bytes, SHA-256 `ea58a17b59f309f5c8963a9c95d7005ca7612813c09dd61475707ff4913feaed`: the `18:48:39Z` freeze (3,874,511 bytes) plus 2,660 bytes that are all pid 20100's. **What is the owner's word and what is the log's is marked on each row**; nothing marked owner-reported was observed here, and no venue call was made.

| When (UTC) | Event | Source |
|---|---|---|
| `2026-10-23T08:05:30Z` and `08:05:33Z` | pid 14600: `Received SIGINT; shutting down gracefully`, then `Trading engine stopped event=engine_stopped clean_shutdown=True`, its last line | the capture (section 66) |
| (before the restart) | **the stop's cause, in the owner's words: *"my pc was up for a long time so wanted to give it some rest ."*** The log shows the SIGINT and not this | owner-reported (the P129 prompt) |
| between `08:05:33Z` and `18:56:48Z`; the time is not stated | **a venue sale: order 6268354, 0.01192000 BTC, FILLED.** Outside the ledger by design (R-DN); it is in the owner's terminal output and not in the capture. **It is the quantity section 66 computed by subtraction as the unsold remainder of order 5431129** (0.02233000 less 0.01041000), which that section marked UNMEASURED at the venue; it is now owner-reported FILLED for the same figure, and still not read from the venue here | owner-reported |
| `2026-10-23T18:56:48.017798Z` | `release_position` for BTCUSDT removed `position:tb1-BTCUSDT-1792588139999-0-L`; store SHA-256 `5d2c4cc38158c592c345435aff2d13ba8ac93978ebc69a72d8c0df98a500fa22` before and `18d97b07946e9045b3e26190c3aa372a1af3f9678644cb61272a057c833978ee` after. **The removed id is list 183218's:** the `order_placed` line of `2026-10-21T13:09:00Z` carries `list_client_order_id=tb1-BTCUSDT-1792588139999-0-L` | `release.log`, read by share-mode copy (below); the digests equal the owner's |
| `2026-10-23T19:04:05Z` | pid 20100's first line (the banner) | the capture |
| `19:04:06Z` | `Startup provenance accepted event=boot_provenance`: `verdict=accepted`, `refusal_reasons=none`, `unknown_reasons=none`, `install_kind=vcs`, `code_commit=45547f10771543b41db42e1cbcb8b5a0a9cf1776`, `code_intact=true` over 77 files, `module_file` and `checkout_root` under `F:\trading bot\deploy\45547f107715`, `checkout_commit` the same commit, `checkout_dirty=false`, `commits_agree=true`, `config_tracked=true`, `config_sha256=f9e0d73743667c195c93775c7997116b1c37f56db361fdd84582ba57d8fa82a0`; then `Starting in TESTNET mode` | the capture |
| `19:04:09Z` | `514 asset(s) are EXCLUDED FROM EQUITY` (`event=boot_assets_excluded`); `Composition root ready: 2 pair(s), 93448.52773900 USDT free` | the capture |
| `19:04:09Z` and `19:04:10Z` | `Seeded BTCUSDT/1m with 499 closed candle(s)`, `Seeded ETHUSDT/5m with 499 closed candle(s)`, `Market-data provider started for 2 pair(s)`, `Trading engine started: BTCUSDT/1m, ETHUSDT/5m` | the capture |
| `19:05:00Z` | the capture's last stamped line: `Signal CLOSE ETHUSDT (death cross ...)` and its refusal as `nothing_to_close` (`signal_ts=2026-10-23T19:04:59.999000+00:00`) | the capture |

**Boot #7** counts the `run` boots from `T0`: pids 16076, 22304, 3444 (the refused boot of 2026-10-13), 25352, 5224, 14600 and 20100. The capture holds nine `boot_provenance` lines, the two non-trading boots of 2026-10-10 (pids 27460 and 27176) among them. Pid 20100 has **11 stamped lines, no `reconciliation_pass` and no `reconciliation_untrusted` line**, because no position is open and a pass is logged only while one is. It is 75 seconds of a process still running at the freeze: no stop, no pass, no booking.

**`release.log`.** Read by a share-mode copy, `[System.IO.FileStream]` opened with `FileShare.ReadWrite` and copied to `scratch\p129\release.log.copy`: 550 bytes, SHA-256 `385222100d8f4f5be412bad01d67a61176832e9c49643b9cb04225a8d733de92`, equal in length to the source, whose last write was `2026-10-24 00:56:48` local time (UTC+6, which is `18:56:48Z`, the record's own stamp). Nothing was written under `deploy\`. It holds **two records, not one**: the BTCUSDT release above and an earlier one, **`2026-10-14T06:33:40.530828Z`, ETHUSDT, removing `position:tb1-ETHUSDT-1791858599999-0-L`** (list 71012's id), store SHA-256 `7995924d1a486448c761ca64e92819339ab2b8d884e4046be16fc85c190c8988` before and `7e5c4d4210eece898fdbb1a4cca596a13380b002fc51b3ba0f6747dce311dd7c` after, **52 seconds before pid 25352's first line** at `06:34:32Z`. That is the resolution of the 2026-10-13 episode (sections 46 and 49), so the earlier episode ended the same way as this one.

**The downtime.** It starts at **`2026-10-23T08:05:33Z`**, pid 14600's last line, and ends by the frozen rule at **the first `reconciliation_pass` of pid 20100, which is not yet logged in this capture.** Until a pass is logged `down_intervals` takes the process to have resumed at its first line, so it returns `2026-10-23T08:05:33Z -> 19:04:05Z` (10 h 58 m 32 s) now, and `s4_explore.py`'s corrected rule `-> 19:05:00Z`, pid 20100's first closed candle. **A pass is logged only while a position is open, so the frozen interval will not end at `19:05Z`: it grows to the first pass, which is the first entry's, and over-excludes the hours in which the bot was trading flat.** That is the property R-DC measured on earlier restarts and is not new. From the stop to the release is 10 h 51 m 15 s, and from the release to pid 20100's first line 7 m 17 s.

### The predictions scored (section 67, commit `ed750f6`)

| | Predicted | Observed |
|---|---|---|
| a | the 2026-10-11 episode ends at `16:54:00Z`, 53 m 59 s (the prompt; the executing session about 80%) | **right**: `16:54:00Z`, 53 m 59 s |
| b | the ETHUSDT and 2026-10-21 episodes are unchanged (the prompt; about 75%) | **right**: identical starts, ends and counts |
| c | 161 kept (the prompt); **160** (the executing session, about 65%) | **160. The prompt was wrong, the executing session right.** The BTCUSDT entry with signal bar `2026-10-11T16:52:59.999Z` is inside R-DO's interval |
| d | no `reconciliation_untrusted` line in pid 20100 (the prompt); and no pass (the executing session) | **right on both**: 0 and 0 |
| e | the `boot_provenance` fields and the engine-started line | **every field as predicted**; the stamp `19:04:06Z` as the prompt says |
| f | the 2,660 added bytes are pid 20100's; the earlier bytes equal the `18:48:39Z` freeze | **right**: the first 3,874,511 bytes are equal |
| g | `release.log` names BTCUSDT, `18:56:48Z` and both digests | **right, and it holds a second record I had not predicted** (the 2026-10-14 ETHUSDT release) |
| h | B recomputed fails at both rates when each is used consistently, and a mixed rate is a narrow pass | **as predicted**: 289 against 309 (-6.7%), 320 against 386 (-17.0%), mixed 320 against 309 (+3.6%) |
| i | 8 frozen intervals, the new one ending at pid 20100's first line; 5 corrected, the new one ending at its first closed candle | **right**: `19:04:05Z` and `19:05:00Z` |

None of the executing session's predictions missed, and the prompt's (c) did (161 against 160). That is not a measure of skill: (a), (b), (e), (f) and (i) were read off P128's script, the source and the halt check.

### Resolved: the size of the freeze section 66 called "171 bytes"

`Get-Item` at the halt check: 3,877,171 bytes, SHA-256 `ea58a17b59f309f5c8963a9c95d7005ca7612813c09dd61475707ff4913feaed`. Section 66 and the P128 C3 message are annotated in the first half of this section and not edited.

### Digests of this section's files

`measure3.py` `cf0c4a11f5927a3a89bf871b6af3fd9539bd12c528bcf8b7b745978529ccd82c`, its output `eb4f49ab34b42c4fced3af9c0642828485d88c80737512b35c7a459e4821c7b6`, `release.log.copy` `385222100d8f4f5be412bad01d67a61176832e9c49643b9cb04225a8d733de92`, `gate_before.txt` `a3db21aaed79cb42f98ee9ae5c46955341a4f752c2f4833831449eb12d05ee29`, all under `F:\trading bot\scratch\p129\`.

## 68. M5m S4: P130's halts, the step-0 halt, and the predictions for the E2 wrapper (P130 C2, R-T)

An observation log, so this section only adds. P130 builds `scripts/s4_latch_compare.py`, the E2 wrapper of R-DL, with fixture tests, and runs no S4 backtest. This section is committed BEFORE the wrapper and its tests are committed (R-T), and is completed in a later commit with the arming audit and the predictions scored. The rulings are in `docs/S4_CORRECTION_P128.md`, `docs/S4_CORRECTION_P129.md` and `docs/S4_CORRECTION_P130.md` (commit `3fd0ef5`, R-DP).

### Halts, checked before anything was written

| Halt | Check | Observed |
|---|---|---|
| `git status` not clean | `git status --porcelain` | empty |
| HEAD is not `33d6765` | `git rev-parse HEAD` | `33d6765ad4aea2e055d80259c75b0e268020e8ca`, P129's last commit; P129's four commits and P128's four are unpushed |
| a command would write under `deploy\45547f107715` or call the venue | every command | none does; nothing under `deploy\` was opened and no socket was opened |
| a frozen file differs from its digest | `Get-FileHash` | `scripts/s4_compare.py` `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08`, `scripts/trade_census.py` `926bdd4674d7fe9fa418fb5e8b67f3d089012255ba8f478492a043fbbe35d9bb`, `config.s4.yaml` `0f170baefb7b41c87d9f3bc5220a484ce9fa20b0a62758e15cb485e9b0712594`, `docs/S4_PREREGISTRATION.md` `49e4fdbba55a5f407d8db130ebdc6cf68fc13813a101ab7849e4740050c6566f`, `docs/S4_CORRECTION_P128.md` `36327c4abc2900b80f2961541e25d9e5da727fd08a1c6352ef2ac5056b05daa6` and `docs/S4_CORRECTION_P129.md` `90291607c9a768f6dfd1018eee1ecfc1ff7af8b385ded7e6f020dd4285d4ee1d` are unchanged |
| a step would run a backtest over the Testnet store or any part of `[W, M)` | the plan | none does; the wrapper is tested on synthetic fixtures only, and the one run on real data (below) reads the owner's frozen capture and no backtest |
| **step 0 finds R-DO inconsistent with the source** | `core/portfolio.py:98`, `:1143`, `risk/manager.py:421-428`, `execution/reconciliation.py:691`, `:700` | **FIRED, and the session halted.** A `diverged` position counts uncomputable and refuses entries, which R-DO's "no unknown count" did not. The owner ruled R-DP (Option A); `docs/S4_CORRECTION_P130.md` records the file-and-line list, DOCUMENTED, and the added check that a diverged pass emits the `reconciliation_untrusted` line R-DM's start needs (`reconciliation_driver.py:492-508`) |

The bare gate before any commit (`gate_before.txt`, SHA-256 `7a2f1119e7704d9563d3b3b08143f1d58ef0b6835a2a06238b638fb58e1cc9c0`): ruff check clean, 228 files formatted, mypy 112 source files, 4373 passed and 1 skipped, exit 0, 287.50 s.

### What was done before this section was committed, and why the predictions are not blind

**The wrapper and its tests were drafted in a scratch tree (`scratch\p130\dev\`) while the gate ran, and the draft's tests were run (88 passed) before this commit.** The order the prompt sets is predictions, then code; the draft was written before the predictions were, so this session did not keep it. The draft is not committed here and nothing in the repository carries it yet. It means each of (a) to (d) below was already checked by a test in the draft, (b) in particular by a fixture built from P129's own stamps, and that the predictions on the real capture (f) to (h) were made with the draft's logic in mind. The digests of the draft as it stood: `s4_latch_compare.py` `959770ab8d343ec0cf7b1b639a38180a8171d88ce3b760ddc621ec94d749bde6`, `test_s4_latch_compare.py` `1c33c78bab8a6b92fbaf09b2ab414cd633838a736f8b7214f33e7d300a454a87`. What the draft has NOT done is run on the real capture, and the mutation survey that proves the tests bite has not been run: (f) to (h) and the survey are still predictions in the strict sense.

### The predictions

| | Prediction |
|---|---|
| a | the 13:09 fixture (an entry filled and never booked, with the live position open across a latch that starts after the entry's signal bar) is labelled **`fok-unfilled`** by the frozen `diagnose`, with the evidence *"the live bot placed and nothing was booked"*, and E2 does not exclude it |
| b | on a synthetic log reproducing the three P129 episodes from P129's own stamps, the wrapper's intervals equal the P129 R-DO table **to the second**: `2026-10-11T16:00:01Z` to `16:54:00Z`, `2026-10-13T02:59:02Z` to `06:54:01Z`, `2026-10-21T13:11:00Z` to `2026-10-23T08:05:33Z` |
| c | a pass that covers fewer positions than the inventory breaks no run |
| d | the union with the frozen `down_intervals` merges a latch and the downtime that abuts it into one interval |
| e | under R-DP the P129 episode table and the kept counts (161 under the frozen rule, 160 under the union) are unchanged, and no lone-position `diverged` pass breaks a run |
| f | the wrapper's `latch_episodes` run on the real capture (`190521Z-capture.log`) returns **exactly** P129's three episodes, with the same starts and ends to the second and the same end kinds; the `refusals` it reports are the sum of the `committed_risk_unknown` and the `close_halted` refusals inside each, **1, 2 and 69** (36 and 33 for the last) |
| g | the union of those episodes with the frozen intervals has **9** intervals: the 8 frozen ones plus 3 latches, less the 2 merges that abut (the 2026-10-13 latch with the frozen interval that begins at `06:54:01Z`, and the 2026-10-21 latch with the frozen interval that begins at `08:05:33Z`); the 2026-10-11 latch ends at `16:54:00Z`, hours before the frozen interval that begins `2026-10-12T04:17:43Z`, so it stays alone |
| h | `exclude_downtime` over that union leaves **160** of the 164 live entries in `[2026-10-11, 2026-10-22)` |
| i | each of the wrapper's tests fails against a deliberately broken scratch copy of the wrapper that names its break; the survey is run in a disposable worktree outside the repository after the tests are committed, and its predictions are written before it runs |
| j | **the restart's first entry is excluded under the frozen rule** (REASONED, to be measured at the stop): a pass is logged only while a position is open, so `down_intervals` ends the interval after pid 14600's stop at pid 20100's first `reconciliation_pass`, which is the first entry's, logged after the entry fills; that entry's signal bar closed before the pass, so it falls in the interval and is excluded, together with every flat hour before it |

### The prediction rule in force

A prediction that comes out wrong in either direction is recorded as a finding with its reach diagnosed; none is changed after the fact. (j) cannot be scored on the 2026-10-23 capture, since pid 20100 had logged no pass in it.

### Completion (P130 C12): the arming audit, the predictions scored, and the process disclosures

Added in the commit that completes this section; nothing above is edited. The commits of P130, in order: `3fd0ef5` (R-DP), `e4e12a4` (this section's predictions), `c254740` (the wrapper), `8a570fd`, `4714d11`, `a923f63` and `4062ccb` (the tests, C4 to C7), `5a7891c` (C8, the wrapper calls the evidence door itself), `21358d2` (C9, the counts), `cc82563` (C10, runbook step 7b) and `7451d01` (C11, NEXT_MILESTONE), then the commit that carries this text.

#### The predictions scored

| | Result | Where |
|---|---|---|
| a | **held.** The 13:09 fixture is labelled `fok-unfilled` by the frozen `diagnose` with *"the live bot placed and nothing was booked"*, and E2 does not exclude it | `TestTheThirteenOhNineEntry` (3 tests), `M5m-637`, `M5m-638` |
| b | **held.** The synthetic log built from P129's stamps gives the three intervals of P129's R-DO table to the second, with its durations and end kinds | `TestTheP129Table` (4 tests), `M5m-637` |
| c | **held.** A pass that covers fewer positions than the inventory breaks no run | `TestCoverageWithTwoPositions`, `TestWhenAPassBreaksARun`, `M5m-637` |
| d | **held.** A latch and the downtime that abuts it become one interval | `TestTheUnion` (6 tests), `M5m-637` |
| e | **held**, on the real capture: the same three episodes, 161 kept under the frozen rule and 160 under the union, and no lone-position `diverged` pass breaks a run (105 `diverged` passes, 45 of them on a lone position, `can_break` false for all) | `M5m-632`, `M5m-633` |
| f | **held.** `latch_episodes` on `190521Z-capture.log` returns P129's three episodes to the second, with refusals 1, 2 and 69 | `M5m-632` |
| g | **held.** The union has 9 intervals | `M5m-632` |
| h | **held.** 160 of the 164 live entries are kept | `M5m-632` |
| i | **held, with one test declared unreachable and one halt, explained.** 89 of the 90 tests fail under at least one of 60 mutations, each break named below; 57 mutations killed exactly the predicted set, 2 killed more (recorded, not changed) and 1 killed fewer, which halted the survey until it was explained (`r05`, below) | the tables below, `M5m-649`, `M5m-650`, `M5m-651` |
| j | **not scored.** Pid 20100 had logged no pass in the 2026-10-23 capture, so the restart's first entry cannot be tested until the stop | `M5m-631` |

#### The survey, and how it was run

Every mutation is one byte-exact replacement with exactly one match, asserted by the spec writer (`make_spec.py`, `make_spec2.py`) and again by the harness, run in a detached worktree OUTSIDE the repository (`F:\trading bot\scratch\p130\wt`), with the import location proven by a pytest session hook before any result counted (`trading_bot` and `tests` both resolved inside the worktree), an unmutated baseline in the worktree before the first mutation (90 passed in rounds 1 and 2, 149 passed in round 3 with `test_backtest_evidence.py` added), and every restore shown SHA-256-equal (60 of 60 `restored; sha equal to before = True`, none False). The worktree was removed after each run; `git worktree list` showed the main worktree only. The harness is `survey.py` (SHA-256 `cd2eb339e4fdf65d361482cccf0511ee3fd28a495fd90815cd5b3b357ed3202a`) with the hook `p116_hook.py` (`febedd0bf7a8fee6a9fe3ac2462975d917ee5e31f5e1daf2acb57f7d378e2a8d`). A mutation of the frozen `s4_compare.py` (`r13`, `r24`) was made in the worktree only; the repository's copy kept its digest `b8afa603f3b52687aeb8f62f4d6340d77fd31b893261a12022794965e5c3af08`.

| Round | Predictions written to | Outputs | Worktree at | Mutations |
|---|---|---|---|---|
| 1 | `survey_spec.json` `c329892216517398ddb33365a04ff3aa3539c00b74e98e542005f6a8a5b87239` (`make_spec.py` `af8100df560c4b17e251f1747d17e24670f44ce2065a01d9b994ada5a9694842`) | `survey_out.txt` `e22eb86dbc5cf6d26bf60480c9317739e0df8cf5e465c11e4e2f00327a420f50` | `4714d11` (tests as of C5) | 38: 36 MATCH, 2 MORE |
| 2 | `survey_spec2.json` `ff20a826a4fa9acf565eeeab1bd707142503027da06ca1f729acfff1db72a9a6` (`make_spec2.py` `fff115cd59b84c4b116a04cfe48ffd1a861cebaf9084a97df4698882110a8f6c`), written before it ran and not changed | `survey_out2.txt` `3357fc436e211d1151e7ca06bdf10ccd4e24201f2da984cdb83d4a742f88a2c0` (`r01` to `r05`, halted at `r05`) and `survey_out2b.txt` `726094a927f678f67fa824a883f2dd704d35faf799a6ffa7f65b50b6b2ed8d36` (`r06` to `r25`, from `survey_spec2b.json` `6ce6389cd7463ef8312b19966de32cc76badab0b6d912726e1c03806d4dbd972`, the same entries) | `4062ccb` | 21: 20 MATCH, 1 FEWER |
| 3 | `survey_spec3.json` `ac998123fe7f2400593330a6499320a2788b0e7388d71796b8957c6d4656c2ce` | `survey_out3.txt` `2f4d02b4e6c7ff55f76924fc101b5cfa6efe39f3a6292db9e4c966049efa7eba` | `4062ccb` plus the uncommitted C8 edit | 1: 1 MATCH |

Round 1 ran on a tree whose tests were those of C5; C6 and C7 later changed three tests (the help test and the two attach tests), and round 1 killed none of those three, so every kill the audit credits to them comes from round 2.

**The three mutations that did not match.**

- `m02-the-old-r-do-break-test` predicted 7, killed 9 (MORE). The mutation restores R-DO's break test (a pass breaks unless it names `unknown`). The two extra kills are the positive controls `test_a_lone_absent_by_design_position_does_break` and `test_the_same_lone_position_reported_active_does_break`: their episodes are built from `diverged` passes before the trusted one, and the old rule breaks the run at the first `diverged` pass, so the episode ends earlier than the test asserts. The prediction counted the tests about the state set and not the fixtures that route through it; the extra kills are real coverage and a reach error. Recorded.
- `m32-two-passes-counted-for-one` predicted 5, killed 6 (MORE). The mutation counts each pass twice in an episode's pass count. The extra kill is `test_a_pass_covering_fewer_positions_than_the_inventory_breaks_nothing`, which asserts the episode's pass count as well as its end and was not on the prediction list; a reach error, and real coverage. Recorded.
- **`r05-unknown-counts-as-trusted` predicted 13, killed 12 (FEWER), and the survey halted as the rule requires.** The missing kill is `TestALatchEndedByACleanStop::test_a_stop_that_was_not_clean_is_not_a_stop`. The cause is in `latch_episodes`: a run can break only at a LATER pass (`current is not None and can_break(candidate)`), and that test has a single pass, which starts the run and has no later pass to break it, so no mutation of `can_break` can reach it. The test's subject is the clean-stop line, not the trust set, and the prediction listed it by reading the fixture's `unknown=1` rather than tracing the loop; that is `M5m-649`. It is a prediction error of fixture reach, not a gap in the tests, and no test was changed for it. The remaining 16 mutations of the round were run from the same prediction record (`survey_spec2b.json`) in a fresh worktree.

#### The mutations, with the break each names

| Round | Mutation (the break, in its label) | Predicted | Killed | Verdict |
|---|---|---|---|---|
| 1 | `m01-no-inventory-equality` | 11 | 11 | MATCH |
| 1 | `m02-the-old-r-do-break-test` | 7 | 9 | MORE |
| 1 | `m03-trusted-set-restated` | 1 | 1 | MATCH |
| 1 | `m04-trusted-set-loses-absent-by-design` | 5 | 5 | MATCH |
| 1 | `m05-stopped-means-clean-only` | 5 | 5 | MATCH |
| 1 | `m06-open-interval-ends-at-last-line` | 7 | 7 | MATCH |
| 1 | `m07-abutting-intervals-not-merged` | 2 | 2 | MATCH |
| 1 | `m08-merge-end-is-the-later-intervals` | 1 | 1 | MATCH |
| 1 | `m09-backtest-side-not-excluded` | 2 | 2 | MATCH |
| 1 | `m10-union-ignores-the-frozen-downtime` | 1 | 1 | MATCH |
| 1 | `m11-union-ignores-the-latches` | 3 | 3 | MATCH |
| 1 | `m12-every-line-is-a-refusal` | 7 | 7 | MATCH |
| 1 | `m13-start-at-the-pass-not-the-line` | 1 | 1 | MATCH |
| 1 | `m14-attach-window-too-wide` | 1 | 1 | MATCH |
| 1 | `m15-attach-the-first-pass-not-the-nearest` | 1 | 1 | MATCH |
| 1 | `m16-a-booking-adds-to-the-inventory` | 4 | 4 | MATCH |
| 1 | `m17-boot-exit-booking-ignored` | 1 | 1 | MATCH |
| 1 | `m18-exit-booking-ignored` | 1 | 1 | MATCH |
| 1 | `m19-one-inventory-for-all-processes` | 1 | 1 | MATCH |
| 1 | `m20-a-pass-covering-nothing-can-break` | 1 | 1 | MATCH |
| 1 | `m22-a-verdict-word-in-the-header` | 1 | 1 | MATCH |
| 1 | `m23-the-header-loses-its-name` | 1 | 1 | MATCH |
| 1 | `m24-the-live-boots-skip-the-door` | 2 | 2 | MATCH |
| 1 | `m25-the-logs-path-is-read` | 1 | 1 | MATCH |
| 1 | `m26-an-inverted-window-is-accepted` | 1 | 1 | MATCH |
| 1 | `m27-an-input-error-exits-as-a-refusal` | 1 | 1 | MATCH |
| 1 | `m29-any-stop-is-a-clean-stop` | 1 | 1 | MATCH |
| 1 | `m30-episodes-in-reverse-order` | 5 | 5 | MATCH |
| 1 | `m31-the-symbols-are-not-collected` | 3 | 3 | MATCH |
| 1 | `m32-two-passes-counted-for-one` | 5 | 6 | MORE |
| 1 | `m33-no-upper-bound-on-the-refusal-window` | 1 | 1 | MATCH |
| 1 | `m34-no-lower-bound-on-the-refusal-window` | 1 | 1 | MATCH |
| 1 | `m35-a-refusal-of-any-process-counts` | 1 | 1 | MATCH |
| 1 | `m36-the-hours-are-rounded-to-hundredths` | 1 | 1 | MATCH |
| 1 | `m37-unfilled-uses-the-frozen-intervals-only` | 1 | 1 | MATCH |
| 1 | `m41-the-trusted-set-is-not-printed` | 1 | 1 | MATCH |
| 1 | `m42-the-rulings-line-is-dropped` | 1 | 1 | MATCH |
| 1 | `m43-close-halted-does-not-qualify` | 4 | 4 | MATCH |
| 2 | `r01-the-count-is-off-by-one` | 1 | 1 | MATCH |
| 2 | `r02-a-missing-field-is-empty-not-none` | 2 | 2 | MATCH |
| 2 | `r03-the-parser-accepts-anything` | 5 | 5 | MATCH |
| 2 | `r04-no-pass-ever-breaks` | 14 | 14 | MATCH |
| 2 | `r05-unknown-counts-as-trusted` | 13 | 12 | FEWER |
| 2 | `r06-a-line-need-not-carry-a-pid` | 1 | 1 | MATCH |
| 2 | `r07-a-line-never-attaches-to-an-earlier-pass` | 4 | 4 | MATCH |
| 2 | `r08-the-last-line-is-remembered-not-the-first` | 1 | 1 | MATCH |
| 2 | `r11-passes-of-every-process-are-candidates` | 2 | 2 | MATCH |
| 2 | `r13-the-frozen-label-is-fill-model` | 2 | 2 | MATCH |
| 2 | `r14-an-extra-line-after-the-frozen-report` | 2 | 2 | MATCH |
| 2 | `r15-the-frozen-figures-are-not-printed` | 4 | 4 | MATCH |
| 2 | `r16-the-diagnosis-is-not-printed` | 6 | 6 | MATCH |
| 2 | `r17-the-record-need-not-name-its-pairs` | 1 | 1 | MATCH |
| 2 | `r18-the-wrapper-has-a-diagnose-of-its-own` | 1 | 1 | MATCH |
| 2 | `r19-the-wrapper-adds-an-argument` | 1 | 1 | MATCH |
| 2 | `r20-an-evidence-refusal-is-not-caught` | 3 | 3 | MATCH |
| 2 | `r21-only-abutting-intervals-merge` | 2 | 2 | MATCH |
| 2 | `r22-the-intervals-are-not-sorted` | 2 | 2 | MATCH |
| 2 | `r24-the-frozen-exclusion-line-is-reworded` | 4 | 4 | MATCH |
| 2 | `r25-an-untrusted-line-in-a-process-with-no-pass-is-not-skipped` | 1 | 1 | MATCH |
| 3 | `s01-the-wrapper-never-calls-the-door-itself` | 1 | 1 | MATCH |

#### The arming audit, by test

Each of the 90 tests, the number of mutations (of 60) that make it fail, and the first three breaks that do. A test shown against NO break is the one exception, declared after the table.

| Test | Failing mutations | First three breaks |
|---|---|---|
| `TestTheTrustedSet::test_it_is_the_value_names_of_the_whitelist_the_portfolio_refuses_entries_by` | 1 | `m04-trusted-set-loses-absent-by-design` |
| `TestTheTrustedSet::test_it_is_imported_and_never_restated_in_the_script` | 4 | `m02-the-old-r-do-break-test`, `m03-trusted-set-restated`, `m04-trusted-set-loses-absent-by-design` (+1) |
| `TestStates::test_the_field_reads_as_name_and_count_pairs` | 1 | `r01-the-count-is-off-by-one` |
| `TestStates::test_an_absent_empty_or_unreadable_field_is_none_and_never_trusted[]` | 1 | `r03-the-parser-accepts-anything` |
| `TestStates::test_an_absent_empty_or_unreadable_field_is_none_and_never_trusted[active]` | 1 | `r03-the-parser-accepts-anything` |
| `TestStates::test_an_absent_empty_or_unreadable_field_is_none_and_never_trusted[active=x]` | 1 | `r03-the-parser-accepts-anything` |
| `TestStates::test_an_absent_empty_or_unreadable_field_is_none_and_never_trusted[=1]` | 1 | `r03-the-parser-accepts-anything` |
| `TestStates::test_an_absent_empty_or_unreadable_field_is_none_and_never_trusted[active=1,]` | 1 | `r03-the-parser-accepts-anything` |
| `TestStates::test_a_line_without_the_field_is_none` | 1 | `r02-a-missing-field-is-empty-not-none` |
| `TestWhenAPassBreaksARun::test_a_full_coverage_all_active_pass_breaks` | 1 | `r04-no-pass-ever-breaks` |
| `TestWhenAPassBreaksARun::test_a_lone_position_reported_active_breaks` | 1 | `r04-no-pass-ever-breaks` |
| `TestWhenAPassBreaksARun::test_an_absent_by_design_position_is_trusted_and_breaks` | 2 | `m04-trusted-set-loses-absent-by-design`, `r04-no-pass-ever-breaks` |
| `TestWhenAPassBreaksARun::test_a_pass_covering_fewer_positions_than_the_inventory_breaks_nothing` | 1 | `m01-no-inventory-equality` |
| `TestWhenAPassBreaksARun::test_a_pass_reporting_more_positions_than_the_inventory_holds_breaks_nothing` | 1 | `m01-no-inventory-equality` |
| `TestWhenAPassBreaksARun::test_an_unknown_count_among_trusted_ones_breaks_nothing` | 1 | `r05-unknown-counts-as-trusted` |
| `TestWhenAPassBreaksARun::test_any_state_outside_the_trusted_set_named_or_not_breaks_nothing[diverged=1]` | 1 | `m02-the-old-r-do-break-test` |
| `TestWhenAPassBreaksARun::test_any_state_outside_the_trusted_set_named_or_not_breaks_nothing[pending=1]` | 1 | `m02-the-old-r-do-break-test` |
| `TestWhenAPassBreaksARun::test_any_state_outside_the_trusted_set_named_or_not_breaks_nothing[unknown=1]` | 1 | `r05-unknown-counts-as-trusted` |
| `TestWhenAPassBreaksARun::test_any_state_outside_the_trusted_set_named_or_not_breaks_nothing[unheard_of=1]` | 1 | `m02-the-old-r-do-break-test` |
| `TestWhenAPassBreaksARun::test_a_trusted_and_an_untrusted_state_together_break_nothing` | 1 | `m02-the-old-r-do-break-test` |
| `TestWhenAPassBreaksARun::test_a_pass_with_no_readable_states_breaks_nothing` | 1 | `r02-a-missing-field-is-empty-not-none` |
| `TestWhenAPassBreaksARun::test_a_pass_covering_nothing_breaks_nothing` | 1 | `m20-a-pass-covering-nothing-can-break` |
| `TestWhenAPassBreaksARun::test_the_trusted_set_can_be_handed_in` | 1 | `r04-no-pass-ever-breaks` |
| `TestTheInventory::test_a_placement_adds_the_symbol_and_a_booking_removes_it` | 1 | `m16-a-booking-adds-to-the-inventory` |
| `TestTheInventory::test_an_exit_booking_and_a_boot_booking_remove_it_too[exit_booked]` | 2 | `m16-a-booking-adds-to-the-inventory`, `m18-exit-booking-ignored` |
| `TestTheInventory::test_an_exit_booking_and_a_boot_booking_remove_it_too[boot_exit_booked]` | 2 | `m16-a-booking-adds-to-the-inventory`, `m17-boot-exit-booking-ignored` |
| `TestTheInventory::test_each_process_keeps_its_own_inventory` | 1 | `m19-one-inventory-for-all-processes` |
| `TestTheInventory::test_a_line_without_a_pid_or_a_stamp_is_not_a_row` | 1 | `r06-a-line-need-not-carry-a-pid` |
| `TestAttachingUntrustedLines::test_a_line_goes_to_the_nearest_pass_of_its_own_process` | 2 | `r07-a-line-never-attaches-to-an-earlier-pass`, `r11-passes-of-every-process-are-candidates` |
| `TestAttachingUntrustedLines::test_a_line_before_its_pass_is_attached_as_well_as_one_after` | 1 | `r07-a-line-never-attaches-to-an-earlier-pass` |
| `TestAttachingUntrustedLines::test_among_several_passes_the_nearest_in_time_is_chosen` | 1 | `m15-attach-the-first-pass-not-the-nearest` |
| `TestAttachingUntrustedLines::test_the_first_line_of_a_pass_is_remembered` | 2 | `r07-a-line-never-attaches-to-an-earlier-pass`, `r08-the-last-line-is-remembered-not-the-first` |
| `TestAttachingUntrustedLines::test_a_line_with_no_pass_within_fifteen_seconds_is_dropped` | 2 | `m14-attach-window-too-wide`, `r11-passes-of-every-process-are-candidates` |
| `TestASelfClearingLatch::test_it_ends_at_the_pass_that_covered_every_position_and_found_them_all_trusted` | 2 | `m01-no-inventory-equality`, `r04-no-pass-ever-breaks` |
| `TestASelfClearingLatch::test_it_counts_its_untrusted_passes_and_its_refusals` | 4 | `m01-no-inventory-equality`, `m12-every-line-is-a-refusal`, `m31-the-symbols-are-not-collected` (+1) |
| `TestASelfClearingLatch::test_a_pass_covering_fewer_positions_than_the_inventory_breaks_nothing` | 3 | `m01-no-inventory-equality`, `m06-open-interval-ends-at-last-line`, `m32-two-passes-counted-for-one` |
| `TestASelfClearingLatch::test_the_start_is_the_first_untrusted_line_and_not_the_pass_before_it` | 2 | `m13-start-at-the-pass-not-the-line`, `r07-a-line-never-attaches-to-an-earlier-pass` |
| `TestALatchEndedByTheProcess::test_with_a_successor_it_ends_at_the_last_line_of_the_process` | 3 | `m05-stopped-means-clean-only`, `m31-the-symbols-are-not-collected`, `r05-unknown-counts-as-trusted` |
| `TestALatchEndedByTheProcess::test_a_second_untrusted_symbol_in_the_run_is_named` | 1 | `m31-the-symbols-are-not-collected` |
| `TestALatchEndedByACleanStop::test_it_ends_at_the_clean_stop_though_no_process_follows` | 2 | `m43-close-halted-does-not-qualify`, `r05-unknown-counts-as-trusted` |
| `TestALatchEndedByACleanStop::test_a_stop_that_was_not_clean_is_not_a_stop` | 3 | `m06-open-interval-ends-at-last-line`, `m29-any-stop-is-a-clean-stop`, `m43-close-halted-does-not-qualify` |
| `TestALatchOpenAtTheCaptureEnd::test_the_interval_is_open_and_closed_at_the_window_end` | 1 | `m06-open-interval-ends-at-last-line` |
| `TestALatchOpenAtTheCaptureEnd::test_it_is_closed_at_whatever_m_the_caller_names` | 1 | `m06-open-interval-ends-at-last-line` |
| `TestWhatIsAnEpisode::test_a_run_with_no_refusal_inside_it_is_not_an_episode` | 1 | `m12-every-line-is-a-refusal` |
| `TestWhatIsAnEpisode::test_a_refusal_after_the_run_broke_does_not_count` | 3 | `m12-every-line-is-a-refusal`, `m33-no-upper-bound-on-the-refusal-window`, `r04-no-pass-ever-breaks` |
| `TestWhatIsAnEpisode::test_a_refusal_before_the_run_started_does_not_count` | 2 | `m12-every-line-is-a-refusal`, `m34-no-lower-bound-on-the-refusal-window` |
| `TestWhatIsAnEpisode::test_a_refusal_in_another_process_does_not_count` | 2 | `m12-every-line-is-a-refusal`, `m35-a-refusal-of-any-process-counts` |
| `TestWhatIsAnEpisode::test_a_close_halted_refusal_qualifies_as_well_as_a_committed_risk_one` | 1 | `m43-close-halted-does-not-qualify` |
| `TestWhatIsAnEpisode::test_an_untrusted_line_with_no_pass_near_it_starts_nothing` | 1 | `r25-an-untrusted-line-in-a-process-with-no-pass-is-not-skipped` |
| `TestWhatIsAnEpisode::test_after_a_break_a_new_run_can_start_and_qualify_on_its_own` | 2 | `m30-episodes-in-reverse-order`, `r04-no-pass-ever-breaks` |
| `TestAUntrustedStateOnALonePosition::test_every_pass_is_inside_one_unbroken_run_that_ends_with_the_process[diverged=1]` | 2 | `m02-the-old-r-do-break-test`, `m32-two-passes-counted-for-one` |
| `TestAUntrustedStateOnALonePosition::test_every_pass_is_inside_one_unbroken_run_that_ends_with_the_process[pending=1]` | 2 | `m02-the-old-r-do-break-test`, `m32-two-passes-counted-for-one` |
| `TestAUntrustedStateOnALonePosition::test_every_pass_is_inside_one_unbroken_run_that_ends_with_the_process[unknown=1]` | 2 | `m32-two-passes-counted-for-one`, `r05-unknown-counts-as-trusted` |
| `TestAUntrustedStateOnALonePosition::test_the_same_lone_position_reported_active_does_break` | 2 | `m02-the-old-r-do-break-test`, `r04-no-pass-ever-breaks` |
| `TestAUntrustedStateOnALonePosition::test_a_lone_absent_by_design_position_does_break` | 3 | `m02-the-old-r-do-break-test`, `m04-trusted-set-loses-absent-by-design`, `r04-no-pass-ever-breaks` |
| `TestCoverageWithTwoPositions::test_a_pass_that_handled_only_the_other_position_breaks_nothing` | 2 | `m01-no-inventory-equality`, `m06-open-interval-ends-at-last-line` |
| `TestCoverageWithTwoPositions::test_a_pass_that_covered_both_and_found_both_trusted_breaks` | 1 | `r04-no-pass-ever-breaks` |
| `TestCoverageWithTwoPositions::test_a_pass_that_covered_both_and_found_one_unknown_does_not` | 2 | `m06-open-interval-ends-at-last-line`, `r05-unknown-counts-as-trusted` |
| `TestCoverageWithTwoPositions::test_a_booking_shrinks_the_inventory_so_a_single_position_pass_then_covers_it` | 2 | `m16-a-booking-adds-to-the-inventory`, `r04-no-pass-ever-breaks` |
| `TestCoverageWithTwoPositions::test_positions_restored_at_boot_and_unseen_by_the_inventory_break_nothing` | 2 | `m01-no-inventory-equality`, `m06-open-interval-ends-at-last-line` |
| `TestTheP129Table::test_the_intervals_equal_the_p129_r_do_table_to_the_second` | 5 | `m01-no-inventory-equality`, `m05-stopped-means-clean-only`, `m30-episodes-in-reverse-order` (+2) |
| `TestTheP129Table::test_the_durations_are_p129s` | 5 | `m01-no-inventory-equality`, `m05-stopped-means-clean-only`, `m30-episodes-in-reverse-order` (+2) |
| `TestTheP129Table::test_how_each_one_ends` | 5 | `m01-no-inventory-equality`, `m05-stopped-means-clean-only`, `m30-episodes-in-reverse-order` (+2) |
| `TestTheP129Table::test_the_refusals_each_one_holds` | 4 | `m01-no-inventory-equality`, `m12-every-line-is-a-refusal`, `m30-episodes-in-reverse-order` (+1) |
| `TestTheUnion::test_an_interval_that_abuts_another_is_merged_into_one` | 1 | `m07-abutting-intervals-not-merged` |
| `TestTheUnion::test_overlapping_intervals_are_merged` | 1 | `r21-only-abutting-intervals-merge` |
| `TestTheUnion::test_an_interval_inside_another_is_absorbed` | 2 | `m08-merge-end-is-the-later-intervals`, `r21-only-abutting-intervals-merge` |
| `TestTheUnion::test_intervals_with_a_gap_stay_apart_and_come_out_sorted` | 1 | `r22-the-intervals-are-not-sorted` |
| `TestTheUnion::test_nothing_in_is_nothing_out` | 0 | **none** |
| `TestTheUnion::test_a_latch_and_the_downtime_that_follows_it_in_a_real_log_become_one` | 4 | `m05-stopped-means-clean-only`, `m07-abutting-intervals-not-merged`, `r05-unknown-counts-as-trusted` (+1) |
| `TestExclusionOnBothSides::test_the_wrapper_drops_the_entries_the_latch_covers_from_both_sides_and_lists_them` | 7 | `m11-union-ignores-the-latches`, `m12-every-line-is-a-refusal`, `m32-two-passes-counted-for-one` (+4) |
| `TestExclusionOnBothSides::test_a_placement_inside_a_latch_is_not_listed_as_unfilled_but_is_by_the_frozen_tool` | 3 | `m11-union-ignores-the-latches`, `m37-unfilled-uses-the-frozen-intervals-only`, `r16-the-diagnosis-is-not-printed` |
| `TestExclusionOnBothSides::test_the_frozen_tool_on_the_same_inputs_excludes_nothing` | 1 | `r24-the-frozen-exclusion-line-is-reworded` |
| `TestExclusionOnBothSides::test_the_figures_follow_the_exclusion` | 3 | `m09-backtest-side-not-excluded`, `m11-union-ignores-the-latches`, `r15-the-frozen-figures-are-not-printed` |
| `TestTheThirteenOhNineEntry::test_the_frozen_diagnosis_labels_a_filled_entry_that_was_never_booked_fok_unfilled` | 1 | `r13-the-frozen-label-is-fill-model` |
| `TestTheThirteenOhNineEntry::test_the_latch_starts_after_the_entrys_signal_bar_so_e2_does_not_exclude_it` | 3 | `r13-the-frozen-label-is-fill-model`, `r16-the-diagnosis-is-not-printed`, `r24-the-frozen-exclusion-line-is-reworded` |
| `TestTheThirteenOhNineEntry::test_the_wrapper_adds_no_label_of_its_own` | 1 | `r18-the-wrapper-has-a-diagnose-of-its-own` |
| `TestTheReport::test_it_is_headed_as_exploratory_and_names_the_rulings_and_the_trusted_set` | 4 | `m04-trusted-set-loses-absent-by-design`, `m23-the-header-loses-its-name`, `m41-the-trusted-set-is-not-printed` (+1) |
| `TestTheReport::test_it_prints_the_three_figures_and_every_cause_count` | 2 | `r15-the-frozen-figures-are-not-printed`, `r16-the-diagnosis-is-not-printed` |
| `TestTheReport::test_no_verdict_word_appears` | 1 | `m22-a-verdict-word-in-the-header` |
| `TestTheReport::test_with_no_latch_it_ends_with_exactly_the_frozen_report` | 3 | `r14-an-extra-line-after-the-frozen-report`, `r15-the-frozen-figures-are-not-printed`, `r16-the-diagnosis-is-not-printed` |
| `TestTheReport::test_with_only_downtime_and_no_latch_the_exclusion_is_the_frozen_one` | 6 | `m09-backtest-side-not-excluded`, `m10-union-ignores-the-frozen-downtime`, `r14-an-extra-line-after-the-frozen-report` (+3) |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_backtest_record_that_is_not_evidence_is_refused_before_any_figure` | 1 | `r20-an-evidence-refusal-is-not-caught` |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_refused_boot_refuses_the_live_run` | 2 | `m24-the-live-boots-skip-the-door`, `r20-an-evidence-refusal-is-not-caught` |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_capture_with_no_boot_line_is_refused` | 2 | `m24-the-live-boots-skip-the-door`, `r20-an-evidence-refusal-is-not-caught` |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_capture_under_a_logs_directory_is_never_read` | 1 | `m25-the-logs-path-is-read` |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_window_that_ends_before_it_starts_is_refused` | 1 | `m26-an-inverted-window-is-accepted` |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_trades_csv_that_disagrees_with_the_record_is_an_input_error` | 1 | `m27-an-input-error-exits-as-a-refusal` |
| `TestTheInputsAreTheFrozenToolsOwn::test_a_record_with_no_pairs_is_an_input_error_and_not_a_default` | 1 | `r17-the-record-need-not-name-its-pairs` |
| `TestTheInputsAreTheFrozenToolsOwn::test_the_arguments_are_the_frozen_parsers_with_only_the_name_changed` | 1 | `r19-the-wrapper-adds-an-argument` |

#### The one declared exception

**`TestTheUnion::test_nothing_in_is_nothing_out` fails under no mutation, and the exception is declared rather than forced.** It asserts that `merge_intervals` of an empty sequence is empty. Every natural break of `merge_intervals` (an unsorted input, a merge that needs an exact abutment, the wrong end kept) leaves an empty input empty, and a mutant that invents an interval from nothing is not a mistake anyone would make, so a test of the empty case is a guard against a regression that has no ordinary form. It stays as a pin of the empty case and is counted as unarmed. (`M5m-650`)

Equivalent mutants declared, because their break cannot change an outcome: the direct `require_evidence_eligible` call added at C8 duplicates the refusal `load_backtest` has already made (round 3), so no wrapper test can fail on its removal, and only the repository's scan of scripts for an unguarded run record does (killed, 1 of 1).

#### Process disclosures

- **Five commits left the gate red.** C3 to C7 were each gated with `ruff` and the file's own tests, and the wrapper named the run record without calling the evidence door itself, which `tests/unit/test_backtest_evidence.py` refuses; the full gate was first run after C7 and read one failure, fixed at C8 (`5a7891c`). The summary figures C9 records come from the green gate on that tree: 230 files formatted, mypy over 113 source files, 4463 passed and 1 skipped credentialed (`M5m-644`).
- **C6's message misstates its numstat.** It says 12 lines added and 4 removed; `git diff --numstat` of the commit reads 12 and 3. C7's message records the difference and C6's is not edited.
- **The predictions of this section were written after a draft of the wrapper and its tests existed** (88 passed in scratch), which the subsection headed *What was done before this section was committed* above discloses (`M5m-630`); the survey's predictions were written before the survey ran, in each round's spec file, whose digest is above.
