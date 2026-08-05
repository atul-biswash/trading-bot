# M5 — the safety numbers

Six numbers M5 introduces, each with what it protects against, what a wrong
value costs in each direction, how it is measured, and **whether it has been
measured yet**.

This is a separate document rather than a `CLAUDE.md` section because these
numbers are *expected to be revised* — two have post-soak re-derivations already
scheduled. `CLAUDE.md` is meant to be stable; `docs/PHASE_HISTORY.md` is
append-only and never restates current state. A file of numbers-with-provenance
that will change fits neither, and splitting it across both guarantees drift.

## Status legend

Every number below is marked one of:

- **MEASURED** — a provenance line names the sample, the date and the method.
- **PLACEHOLDER — NOT MEASURED** — a working value with a stated rationale and
  **no sample behind it**. It must not be quoted as though it were measured, and
  it must not ship to LIVE without its measurement.

**Four of six are placeholders.** That is the honest state at M5-0 and it is
written this way so a later reader cannot mistake a rationale for a sample.

---

## 1. `risk.max_entry_slippage`

**Type:** `Decimal`, `gt=0`, and **upper-bounded**. A value of `0.5` would place
a buy limit 50% above the close — inside `PERCENT_PRICE_BY_SIDE`'s 2x ceiling and
filling against anything. The bound is what stops the config expressing "market
order in disguise".

**Protects against:** paying an unbounded price for immediacy. The marketable
limit is the mechanism; this is the bound. Without it the alternative is `MARKET`,
whose fill price is set by the book rather than by us.

**Too tight costs:** missed entries, quietly. Under `FOK` a limit that cannot fill
*entirely* at or better expires — whole list, all legs, zero residue (MEASURED,
Q-C). On a thin book or a fast bar most signals become `entry_unfilled` lines and
the bot looks healthy while never trading.

**Too loose costs:** three things, and note which it is **not**. It does *not*
break the risk budget — Q-C §4 sizes at `entry_limit`, so realised entry-to-stop
distance <= planned. It costs (i) a take-profit computed from a higher entry, so
the target is less reachable; (ii) more quote consumed than the reference implied,
eating `free_quote`; and (iii) at the extreme, collision with
`PERCENT_PRICE_BY_SIDE` — a working price far above the 5-minute average is itself
band-refusable, so too-loose fails as a **whole-list rejection**, not gracefully.

**Measurement — read-only, no order, no fill.** Sample the distance from a bar's
close to the best ask **immediately after that close**, over the configured pairs
and timeframes. That distribution is the answer; pick the quantile you are willing
to miss.

**Provenance:** *(to be written when measured)*
`max_entry_slippage = X: the Nth percentile of close-to-ask on <pairs> over <N>
bars, measured <date> on Testnet.`

**Status: PLACEHOLDER — NOT MEASURED.**

---

## 2. The `PERCENT_PRICE_BY_SIDE` band margin

**Protects against:** a whole-list rejection at submission. The band is 0.5x–2x of
the 5-minute average, enforced at submission, and a violation refuses the **entire
list** (MEASURED, Q-C S4) — so a take-profit that drifts outside kills the entry
and the stop with it. The margin buffers the average *moving* between the moment
levels are computed (bar close) and the moment the exchange evaluates them
(submission).

**Too tight costs:** the pre-check passes and the exchange refuses anyway. One
refused signal, logged, `FilterRejectedError` naming the filter. **Observable and
free.**

**Too loose costs:** refusing signals the exchange would have accepted — silent
lost edge, refused at a stage an operator reads as a *risk* decision when it was a
guess about a moving average.

**The asymmetry sets the direction, and it is the design conclusion, not a
footnote: prefer too tight.** Because the exchange enforces the band itself, and
because a violation is a clean whole-list rejection rather than a partial anything,
the margin should be **small — biased toward letting the exchange be the judge**.
The pre-check exists to make a refusal legible and to save a round trip, not to be
the authority. That is also why the check sits at dispatch rather than in
`evaluate`.

**Measurement — read-only, with two corrections to the obvious method.**

1. **The interval is not the bar.** The quantity is drift over *bar close ->
   submission*, sub-second-to-seconds, dominated by our own latency. Sampling at
   bar-close cadence measures a minute of drift and yields a margin an order of
   magnitude too loose. Read `avgPrice` at bar close, read again after a delay
   equal to measured placement latency, record the difference.
2. **The series must be verified first.** Q-C treats the `avgPrice` endpoint's
   number and the number the filter is evaluated against as the same. Nothing
   establishes that, and the whole pre-check rests on it. Settled by a
   **rejection**: place a pending price just inside and just outside the band
   computed from `avgPrice` and see whether the boundary lands where predicted.
   **M5c, no fill.** This is a prior question to how large the margin should be.

**Status: PLACEHOLDER — NOT MEASURED**, and blocked behind the series check.

---

## 3. `alpha` — the pipeline headroom factor

**Not a config field.** It is the constant in the coherence constraint below.

**Protects against:** the candle pipeline falling behind and never recovering.
Handler work is inline on the stream dispatch task; when handler time approaches
the bar interval, a bar closing mid-handler is missed, and the buffer does not
backfill. The damage outlives the hole: the ATR bridge's second gate exists because
a gap re-masks to NaN long after warmup, so one missing bar can disable ATR stops
on that pair for `atr_period` bars afterwards.

**Too tight costs — and the cost is sharper than over-conservatism.** The boot
check refuses configurations that would work, so an operator lowers
`max_open_positions` or lengthens their shortest timeframe for a hazard that is not
there. Worse: a small `alpha` forces the dispatch deadline down, and a deadline
below real venue latency **times out a placement that in fact placed** — the
ambiguous write, the most expensive failure on the dispatch path. **A too-tight
`alpha` manufactures the exact failure it exists to prevent.**

**Too loose costs:** saturation. Jitter drops bars, *silently* — `_append` logs a
debug line for a non-advancing candle, but a candle that never arrives produces no
line at all, because nothing arrives to log it.

**Measurement — read-only, no exchange call, available today.** Both halves come
from the existing candle path:

- **Arrival lateness:** per candle, record `wall_clock_arrival - candle.close_time`
  — socket latency, event-loop scheduling and current handler cost together.
- **Current handler baseline:** time `_emit` end to end. Today that is strategy
  evaluation plus `IntentLogger`, sub-millisecond, which establishes that the whole
  budget is available to M5's new work.

Set `alpha` so `(1 - alpha) x T_min` comfortably exceeds the p99 of arrival
lateness. If arrivals land within ~200 ms of close on a 60 s bar, `alpha = 0.5` is
enormously conservative and 0.8 would be defensible; a fat tail pushes it down.

**This measurement is a PREREQUISITE OF M5a, not an item inside it**, because
`alpha` is an input to the boot refusal M5a builds, and a guessed `alpha` becomes a
config refusal operators hit for a reason nobody measured. It is also strictly
easier now and gets harder later: today the handler baseline is clean, and after
M5e arrival lateness is confounded by the very dispatch work `alpha` budgets for.
Measuring it after soak measures the wrong quantity.

**It must be measured from a scratchpad script, never by instrumenting `src/`.**
A file added under `scripts/` moves the documented `ruff format` and `mypy` counts;
instrumenting `_notify` makes a docs-only milestone a code milestone. Register a
throwaway subscriber through the public `on_candle` port — which exists precisely
so a second consumer needs no core change — record the numbers, discard the script.
And verify the tree afterwards by **checksum, not `git status`**: status sees only
tracked files, and this project's own history has a sweep that left `src/` modified
on disk and was caught by md5.

**Working value: `alpha = 0.5`.**

**Status: PLACEHOLDER — NOT MEASURED.**

**Provenance:** *(to be written when measured)*
`alpha = X: p99 candle arrival lateness across <pairs> over <N> bars was Y ms,
measured <date> on Testnet; (1 - alpha) x T_min leaves K x that tail.`

---

## 4. `risk.max_position_staleness`

**Protects against:** trading on a ledger that no longer describes reality.
Concretely, the three dangerous readers: equity overstated => sizes too large
**and** the daily-loss threshold too generous; the realised loss unbooked; and
`start_cooldown` never called, so "do not re-enter what just stopped you out" is
silently off.

**Too tight costs two things, and the second is the one that matters.** It fires on
a healthy system, so entries are refused constantly. And because the refusal is what
frees budget, a too-tight value makes the refuse-reconcile-trade oscillation the
*normal operating mode* rather than a safety valve. That destroys its signal value:
an operator who sees the staleness line every bar stops reading it, and it is then
unavailable as a warning when it means something.

**Too loose costs:** the window in which a stop can have fired and the bot can still
open a *new* position — sized off overstated equity, with no cooldown, against a
daily-loss threshold that has not heard about the loss.

**Measurement — half is available now, half is not, and the split is stated rather
than blurred.**

- **Now, read-only:** the reconciliation round-trip distribution (`T_recon`) — poll
  a read endpoint on a timer and record latency. Sets the floor precisely.
- **Now, no exchange at all:** the **skip rate** — how often the budget would have
  skipped reconciliation — simulable from the `alpha` sample plus the arithmetic
  below, with nothing dispatching.
- **Not without fills:** how long a stop actually rests before triggering, which is
  what decides what staleness *costs* in practice. Soak quantity; after M5e.

Set it before M5e from the measurable half — `floor = p99(T_recon) + T_min`, times a
headroom multiplier chosen from the simulated skip rate — and **re-derive it after
soak**. The re-derivation is expected, not a surprise.

**Working value: `3 x T_min` (180 s on the shipped config).** That multiplier is a
**policy choice** — "two consecutive budget skips are normal" — not a measurement.
The floor on the shipped config is `60 s + T_recon`, so any value at or below ~63 s
fires on a healthy system.

**Status: PLACEHOLDER — NOT MEASURED.**

---

## 5. `risk.dispatch_deadline_s`

**Protects against:** an inline handler holding the candle pipeline for the length
of a venue stall. Bounds the whole dispatch sequence, not one call.

**Too tight costs:** a timed-out placement that in fact placed — the ambiguous
write. Recoverable (query by derived IDs, `-2010` as the venue-side idempotence
net), but it is the most expensive path in the system and the recovery leans on an
**unmeasured** classification for order lists.

**Too loose costs:** it fails the coherence constraint below, or passes it by
forcing `max_open_positions` down.

**It must be its own field.** `exchange.requests_timeout_s = 10` is a per-call
timeout for reads; a three-call `CLOSE` sequence at that value is 30 s, and two
pairs closing on the same minute is 60 s — the entire bar, before reconciliation
runs. **Roughly a third of `requests_timeout_s` is the right order of magnitude on
the shipped config**, and the constraint below is what fixes it.

**Measurement:** the placement round-trip distribution on Testnet, read-only for
the query half; the write half is measurable from M5c's expiring placements, which
are real submissions that cannot fill.

**Status: PLACEHOLDER — NOT MEASURED**; derivable from the constraint once
`T_recon` and `alpha` are.

---

## 6. `risk.reconcile_deadline_s`

**Protects against:** one slow position query consuming the reconciliation floor
and starving the rest of the pass.

**Too tight costs:** positions repeatedly time out and their stamps never advance,
which drives the staleness refusal — the safety valve firing for a reason unrelated
to staleness.

**Too loose costs:** with `max_open_positions` positions to visit, the pass will not
fit in its floor, and oldest-first iteration degrades from "graceful" to "only ever
reaches the oldest one".

**Measurement:** `v3_get_order_list` latency distribution against Testnet. Read-only,
no order.

**Working value: 3 s.**

**Status: PLACEHOLDER — NOT MEASURED.**

---

## The coherence constraint

Per **candle-handler invocation** — the right unit, because two pairs whose bars
coincide produce two back-to-back invocations, each with a full budget:

```
P_sim x D  +  N_max x T_recon  <=  alpha x T_min
```

| Symbol | Meaning | Source |
|---|---|---|
| `D` | `risk.dispatch_deadline_s` — the whole sequence, worst case the 3-call `CLOSE` | config |
| `T_recon` | `risk.reconcile_deadline_s` — one `v3_get_order_list` per position | config |
| `N_max` | `risk.limits.max_open_positions` | config |
| `P_sim` | enabled pairs whose bars can close in the same instant; worst case, all of them | derived from `trading.pairs` |
| `T_min` | shortest enabled timeframe, via `timeframe_to_ms` | derived from `trading.pairs` |
| `alpha` | headroom factor, §3 | constant |

Reconciliation does **not** carry `P_sim`, because passes are deduplicated by
`last_reconciled_at`: the second invocation on a coinciding minute finds every stamp
fresh and does nothing. Dispatch does, because two pairs can each emit a signal on
the same minute.

### Worked, on the shipped `config.yaml`

`pairs` = BTCUSDT/**1m**, ETHUSDT/**5m**, both enabled => `T_min = 60 s`,
`P_sim = 2` (they coincide every fifth minute). `max_open_positions = 3`.
`alpha = 0.5` => budget 30 s.

| `T_recon` | Reconciliation (N=3) | Left for dispatch | `D` (P=2) | Per call in a 3-call CLOSE |
|---|---|---|---|---|
| 2 s | 6 s | 24 s | 12.0 s | 4.0 s |
| **3 s** | **9 s** | **21 s** | **10.5 s** | **3.5 s** |
| 5 s | 15 s | 15 s | 7.5 s | 2.5 s |

### Where it is enforced

An `AppConfig` `model_validator(mode="after")` — **not** `RiskConfig`, which cannot
see `trading.pairs`. Pure, runs at config load, costs no round trip, fails before any
client exists: the same posture as `_pair_timeframes`' duplicate-symbol refusal.
`config/models.py` importing `timeframe_to_ms` from `utils/helpers` opens no cycle.

### The refusal message

```
risk.dispatch_deadline_s = 10.0 x 2 pair(s) that can close simultaneously,
plus risk.reconcile_deadline_s = 3.0 x limits.max_open_positions = 3,
is 29.0s. That exceeds 50% of the shortest enabled timeframe
(BTCUSDT/1m = 60s, budget 30.0s).

The signal handler runs inline on the candle pipeline, so a bar closing
while it is still working is missed and never backfilled -- and a gap
re-masks ATR to NaN long after warmup, disabling ATR stops on that pair.

Lower risk.dispatch_deadline_s, lower risk.limits.max_open_positions, or
configure a longer shortest timeframe in config.yaml.
```
