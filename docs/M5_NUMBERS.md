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

- **MEASURED** — a provenance line names the sample, the date and the method, and
  the value is derived from it.
- **BOUNDED** — a measurement exists and constrains what the value must clear, but
  **does not derive it**. The value is a policy choice made with that headroom in
  view. Both halves are recorded deliberately: a later reader must be able to see
  that the number is a choice *and* that re-running the measurement will not tell
  them what to change it to.
- **PLACEHOLDER — NOT MEASURED** — a rationale and **no sample behind it**. It must
  not be quoted as though it were measured, and must not ship to LIVE without its
  measurement.

**Five placeholders, one bounded.** That is the honest state at M5-0 and it is
written this way so a later reader cannot mistake a rationale for a sample, or a
policy choice for a derivation.

There are deliberately only three statuses. A fourth was drafted for
`dispatch_deadline_s` on the grounds that the coherence constraint *derives* it —
and withdrawn: the constraint narrows it but cannot produce it, because `alpha` is
a policy choice and `T_recon` is itself unmeasured, so what falls out is a
consequence of two other choices rather than a derivation from data. §5 also
carries its own measurement plan, which the withdrawn status flatly contradicted. A
status that houses exactly one entry, and that entry measurable, is a label rather
than a category.

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

**The five minutes are MEASURED, promoted from DOCUMENTED.** The filter states its
own interval: `avgPriceMins` arrives on the `PERCENT_PRICE_BY_SIDE` payload as a
JSON number, value `5`, on **both** configured symbols. So does the band itself —
`bidMultiplierUp` / `askMultiplierUp` `"2"` and `bidMultiplierDown` /
`askMultiplierDown` `"0.5"`, four fields rather than the two "0.5x–2x" implies.
*Provenance: `GET /api/v3/exchangeInfo` via `get_symbol_info`, Binance Spot
**TESTNET**, BTCUSDT and ETHUSDT, 2026-08-08, read-only, no order placed.* The
same `avgPriceMins: 5` appears on `NOTIONAL`.

**This changes nothing about §2's status, and the distinction is the point:
measuring the INTERVAL did not measure the SERIES.** What is now measured is *how
many minutes* of average the filter uses. What remains unestablished is *which
number* it averages — specifically whether the `avgPrice` endpoint's value is the
value the filter is evaluated against, which is the prior question in the
measurement plan below and the thing the whole pre-check rests on. A margin still
cannot be derived from this. The status stays **PLACEHOLDER**.

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

**Working value: `alpha = 0.5`. Status: BOUNDED.**

**Provenance.** TESTNET, shipped `config.yaml` pairs, 2026-08-06 09:14–10:44,
90 minutes, **108 records — 90 BTCUSDT/1m + 18 ETHUSDT/5m, exactly the expected
count, so NO BAR WAS MISSED.** That last fact is a second result hiding inside the
first, and it is the direct empirical answer to the question alpha exists to
guard: the pipeline kept up for the whole window, on the shipped configuration,
with nothing dropped.

Worst observed pipeline overhead was 1258.4 ms arrival lateness + 485.7 ms handler
= **1744.1 ms against a 60 000 ms bar, 2.9% of `T_min`**. Arrival lateness was
**stationary** across three equal thirds (p90 997 / 1212 / 1017 ms; maxima within
8% of each other). `alpha = 0.5` leaves 30 s of headroom against that worst case —
a **17x margin**.

**So jitter is not the binding term in the R2 constraint**, and `0.5` is a *policy*
choice rather than a derivation. Raising alpha does not buy headroom; it relocates
the constraint onto venue latency, which this probe does not sample. At
`alpha = 0.95` the constraint would admit `D ~ 24 s` — an 8 s per-call deadline
inside a three-call `CLOSE`, which is essentially the general
`exchange.requests_timeout_s` that §5 exists to reject.

Measurement method: two probes registered through the public `on_candle` port,
bracketing the engine's handler in registration order, so its duration is measured
without instrumenting it. Validated against an injected known answer immediately
before sampling.

---

## 4. `risk.max_position_staleness_s`

> **Renamed at M5a — the document follows the code.** This section was written as
> `max_position_staleness`; the field shipped as **`max_position_staleness_s`**,
> because every other duration in `config.yaml` carries its unit and a duration
> field that omits one is precisely the ambiguity that produced the
> `dispatch_deadline_s` conflation four commits were spent correcting. **The
> working value below is now the shipped default**, and everything else in this
> section — the measurement split, the too-tight/too-loose costs, the status —
> survives unchanged.

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

**Shipped at M5a as `180.0`.** Its meaning is coupled to the shortest enabled
timeframe and its type is not: an operator who lengthens their shortest bar must
raise this by hand and **nothing checks it**. That asymmetry is deliberate rather
than an omission — a value that fires on a healthy system trains an operator to
skim the line, which is the worse failure direction, and it is then unavailable as
a warning when it means something.

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
runs. **Roughly a third of `requests_timeout_s` is the right order of magnitude for
the derived per-call share on the shipped config**, and the constraint below is what
fixes it.

**Definitional, stated once so the two figures cannot be collapsed again.**
`risk.dispatch_deadline_s` — `D` — is the deadline for the **whole dispatch
sequence**, worst case the three-call `CLOSE`, and it is the only configured number.
The **per-call** figure is *derived*: `D` divided by the call count of the longest
sequence, which is what the constraint table's rightmost column reports. On the
shipped config the constraint admits `D <= 10.5 s`, whose derived per-call share is
3.5 s. The sentence above describes that derived per-call figure (~3.3 s against a
10 s general timeout); it has never described `D`. Reading it as `D` gives ~1.1 s per
call inside a three-call `CLOSE` — below plausible venue round-trip, which is the
ambiguous write, manufactured by the budget that exists to prevent it.

**A first-execution cost of order 100–500 ms is paid inside the first dispatch,
and it is an additive term in this budget.** Measured on TESTNET: the composed
decision path costs **~2 ms in steady state** — six full executions across two
runs at 1.2–2.4 ms, statistically indistinguishable from bars producing no signal
at all — but its *first* execution in a process costs far more. Two runs: 485.7 ms
on the first approved signal in one, 29.3 ms in the other with a further 229.1 ms
landing on the first candle instead. **The order of magnitude is stable; the split
and the size are not**, so this is recorded as a range and not a number.

Under M5e the first approved signal is also the first *order*, so this is paid on
top of venue latency, inside `dispatch_deadline_s`, **once per process**. Against
`D = 10.5 s` — the **ceiling** the constraint admits on the shipped config, not a
shipped default — a 485 ms excursion is **4.6%** of the whole dispatch budget spent
before the first byte reaches Binance, and it is larger at any admissible default:
**4.9% at 10.0, 5.4% at 9.0**. Run 2's `evaluate`-attributable 29.3 ms is 0.3% at the
ceiling. What the sample gives is a range from a fraction of a percent to five
percent, not a single figure.

The remedy is **not** to inflate `D`. `D` is not free: the constraint multiplies it
by `P_sim` and trades it against `N_max x T_recon` under a fixed `alpha x T_min`,
so covering a once-per-process cost by widening `D` permanently taxes every
subsequent bar. **The composed path is warmed at boot instead — an M5a decision** —
and the warm-up is timed and logged at boot as its anti-rot measure, because
boot-time code that exists only for timing rots silently and the failure is
invisible until the cost reappears on a real order.

What the evidence does **not** establish is *which* one-off cost this is. First-call
tz-database load in `_roll_day`, `decimal` context materialisation, a lazily
resolved import, or a GC pause coinciding with that bar are not separable without
instrumenting `evaluate` itself. Eliminated by the data: pandas/NumPy frame
building (every bar does it), the logging sink (a refused signal reached
`IntentLogger` in 2.0 ms, 62 bars earlier), and ATR warm-up (a percent stop never
calls it). **"One-off, cause unresolved"** is the honest statement.

**Measurement:** the placement round-trip distribution on Testnet, read-only for
the query half; the write half is measurable from M5c's expiring placements, which
are real submissions that cannot fill.

**Status: PLACEHOLDER — NOT MEASURED.** The coherence constraint below narrows it
but does not produce it — `alpha` is a policy choice and `T_recon` is itself
unmeasured — so the plan above is what settles it, with the cold-path term as an
empirical input.

> **Correction — `D` was mis-cited against its own table. Added at M5a-doc.**
> This section previously read: *"At `D ~ 3.5 s` from the constraint table, a 485 ms
> excursion is 14% of the whole dispatch budget."* The constraint table's `D` column
> reads **10.5 s** on the shipped row; **3.5 s is that row's "per call in a 3-call
> CLOSE" column.** The arithmetic was right for the number quoted
> (485 / 3500 = 14%) and the symbol was wrong.
>
> **Corrected: 485 ms is 4.6% of the constraint ceiling, not 14%** — 4.9% at a 10.0
> default, 5.4% at 9.0, and 0.3% for run 2's 29.3 ms.
>
> **This weakens the motivating fact for warming the composed path at boot, and the
> weakening is stated rather than absorbed.** The case rested on a once-per-process
> excursion consuming a seventh of the dispatch budget; on the corrected number it
> consumes about a twentieth. Taken with the bound recorded below — the warm-up
> removes ~11% of the one-off in one of the two runs — the empirical case is
> materially smaller than it reads.
>
> **What survives:** `D` is not free. The constraint multiplies it by `P_sim` and
> trades it against `N_max x T_recon` under a fixed `alpha x T_min`, so inflating
> `D` to cover a once-per-process cost still permanently taxes every bar. That
> argument never depended on the size of the excursion and is untouched.
>
> **What is now open:** whether a 4.6%-worst-case, partly-unattributed one-off
> justifies boot-time machinery that must be maintained and can rot. The warm-up is
> recorded in `CLAUDE.md`'s **Current state** and sequenced in
> `docs/NEXT_MILESTONE.md`; it is **not** in `CLAUDE.md`'s Locked decisions. It is
> not reopened by this commit, and is to be adjudicated on the corrected number.

> **Bound on what the warm-up removes — added at M5a-doc, not a resolution.**
> The first-execution paragraph says the one-off "is paid inside the first
> dispatch." That is true of run 1 and false of run 2, by this section's own
> numbers. The warm-up removes only the portion attributable to `evaluate`:
> **485.7 ms of 485.7 ms (~100%) in run 1, and 29.3 ms of 258.4 ms (~11%) in
> run 2.** The residual — 229.1 ms landing on the first *candle* rather than on the
> first approved signal — is **unattributed**. It is not inside `evaluate`, so no
> warm-up of the composed path reaches it, and the four-candidate list above does
> not separate it.
>
> **What survives unchanged:** the one-off is real, is once per process, is an
> additive term in this budget, and inflating `D` is still the wrong remedy for it.
> **What is now bounded rather than asserted:** how much of it the warm-up actually
> removes — between ~11% and ~100%, on a sample of two. The cause remains unknown
> and this note does not resolve it.

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

> **THE CALL THIS NUMBER IS BUDGETED FROM CANNOT RETURN WHAT RECONCILIATION
> NEEDS, and the correction runs CHEAPER rather than dearer.** Annotated at
> M5d; the working value is untouched, because what changes is the call it
> prices, not the latency of that call.
>
> `T_recon` is defined below as "one `v3_get_order_list` per position".
> **MEASURED at M5d: that endpoint returns each leg as an identity triple** --
> `{symbol, orderId, clientOrderId}`, no `status`, no `executedQty`, no
> `origQty`, no prices. Q-C §7's compare set is not in it, at any cost.
>
> **`get_open_orders` is where the compare set lives**, and it returns full
> order objects for **all three legs including pendings in `PENDING_NEW`**
> (MEASURED at M5d against a live OTOCO). Crucially it is keyed by **symbol**,
> not by position, and §6's `tb1-` prefix separates our legs from everyone
> else's in the result.
>
> **So the per-position term is the wrong shape.** One call per SYMBOL is
> amortised across every position on that symbol, where `N_max x T_recon`
> charges one call per POSITION. On the shipped `config.yaml` -- two symbols,
> `max_open_positions = 3` -- the constraint currently reserves for three calls
> where two suffice, so the coherence budget has headroom nobody has spent.
>
> **A mid-milestone finding briefly proposed the opposite** -- one list query
> plus one per-order query per leg, four calls per position -- and it was
> wrong: it measured correctly that the read-back is the wrong endpoint and
> then priced the wrong replacement. Recorded because the erroneous figure is
> the more alarming one, and a reader meeting it first should know it was
> superseded by measurement rather than by preference.
>
> **NOT re-derived here.** Restating the constraint needs the reconciler's real
> shape -- how many symbols it visits per pass, and whether a pass is
> per-symbol or per-position -- which is the milestone that builds it. What
> this annotation fixes is the DEFINITION the number is attached to, so the
> next derivation does not start from a call that cannot answer.

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

> **BUILT at M5a as `_check_dispatch_budget_fits_the_bar`, exactly as specified
> here, plus two things this section did not anticipate.**
>
> **`alpha` lives as a module constant beside the validator, not as a config
> field.** §3 sets its value but never says where it should live. It is a property
> of the pipeline's headroom policy, not of an operator's account, so exposing it
> would invite tuning the safety margin rather than the thing breaching it. Its
> docstring carries the word **BOUNDED** and points back at §3, because BOUNDED is
> the one status a reader must not read as MEASURED.
>
> **An empty enabled-pair list is VACUOUSLY SATISFIED and returns early — this is
> not an oversight and must not be "fixed" into a refusal.** There is no pipeline
> to overrun and `T_min` is undefined rather than zero. `engine.modes.live_system`
> already refuses an empty enabled-pair set *at boot*, with a message about the
> operational consequence; refusing here too would give one configuration two
> different errors depending on which check ran first, and would move a boot
> refusal into config load where `main.py` reports it on a different stream.
>
> It is also the case that would have broken the suite: `tests/conftest.py` writes
> no `trading:` key at all, so `pairs` falls to its default empty list on **every**
> config-loading test, and a naive `min()` over enabled pairs raises on all of
> them.

### The refusal message

Worked with **`dispatch_deadline_s = 11.0`**, chosen *because it breaches*: it
illustrates the refusal and is **not a proposed default**.

> **The default is no longer open — M5a shipped `9.0`.** This paragraph used to
> end *"The shipped default is an open decision this document does not settle."*
> It is settled: `9.0` sits **1.5 s under the 10.5 s ceiling** the constraint
> admits on the shipped pair list, and its derived per-call share is `3.0 s`. The
> `11.0` above stays exactly as written — it is the *breaching* example, its whole
> job is to be refused, and replacing it with the shipped value would make the
> worked message one that is never emitted, which is the defect this section was
> rewritten to fix in the first place.
>
> **What survives:** everything else here, including that `D` is the whole-sequence
> deadline and `3.0 s` is derived from it rather than configured. **The message
> below is now the text the code actually emits** — verified by a test that asserts
> each of its four inputs appears — rather than a specification of one.

```
risk.dispatch_deadline_s = 11.0 x 2 pair(s) that can close simultaneously,
plus risk.reconcile_deadline_s = 3.0 x limits.max_open_positions = 3,
is 31.0s. That exceeds 50% of the shortest enabled timeframe
(BTCUSDT/1m = 60s, budget 30.0s).

The signal handler runs inline on the candle pipeline, so a bar closing
while it is still working is missed and never backfilled -- and a gap
re-masks ATR to NaN long after warmup, disabling ATR stops on that pair.

Lower risk.dispatch_deadline_s, lower risk.limits.max_open_positions, or
configure a longer shortest timeframe in config.yaml.
```

The previous worked example used `10.0`, giving `2 x 10.0 + 3 x 3.0 = 29.0s` against
a 30.0s budget; the constraint is `<=`, so 29.0 passes and the message would never
have been emitted for its own numbers.
