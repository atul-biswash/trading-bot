# Q-B — what CRITICAL does

Q-C leans on "CRITICAL, halt entries" in three places and never says what either
half means. R5 added a fourth site and S1 a fifth. This is that decision.

## 1. What CRITICAL does

Three things, and only three, because the obvious fourth is a stub:

1. **A log line at `CRITICAL`**, with a fixed field set per the `extra=` schema
   discipline: `event`, `symbol`, `site`, `category`, `detail`, and — where one
   exists — `order_list_id`. Enums cross as `.value`, timestamps as `isoformat()`.
2. **A halt flag on `Portfolio`.** State lives on `Portfolio`; policy lives in
   `RiskManager`. A halt is state, and `Portfolio` already carries a per-day halt
   in all but name (`realised_pnl` driving `DAILY_LOSS_HALT`), so an operational
   halt is the same shape rather than a new concept.
3. **Nothing else.** `notifications/` is a pair of stubs and is deliberately out
   of M5's scope: a notifier that raises inside a handler that must not raise is
   its own failure class, and wiring one in the milestone that first sends orders
   stacks two novel risks. **CRITICAL in M5 means "a log line and a halt", and an
   operator who is not reading logs will not learn about it.** Written plainly so
   nobody assumes otherwise.

### The halt does not survive a restart, and there is no mechanism in M5 to make it

`Portfolio` is in-memory and per-run; `persistence/` is a stub and is deliberately
deferred. So a restart clears every halt.

For sites 3 and 4 that is acceptable, because **boot reconciliation re-detects the
condition** — the divergence is still there, the stale stamp is still stale.

For **site 2 it is a hole**: a partial fill on a protective leg is recorded nowhere
durable, so a restart forgets it and the bot resumes trading against a quantity it
does not know. Stated as a known limitation of M5, not as a design.

For **site 5 it is subtler and worth spelling out.** Positions are not persisted
either, so on restart `positions` is empty and site 5's condition *cannot fire* —
there is no `Position` to lack a stop. What the next run sees instead is a base
holding it did not open, which is the **unmanaged-holding** state (see the
boot-adoption decision in `QC_PROTECTIVE_ORDERS.md`). So site 5's two reachable
routes — a `stop_loss.enabled` flip between runs, and the placement-unknown state —
are **within-run only** under M5.

That does not weaken site 5's argument; it sharpens what "terminal" means.
**Terminal = nothing the bot can do *while running* resolves it.** A restart
"resolves" it by forgetting, which is amnesia rather than resolution — and the
unmanaged-holding state it lands in is the honest description of what is actually
known afterwards.

## 2. The five binding sites

Three categories, not two. The distinction is **what can clear it**.

| # | Site | Origin | Category |
|---|---|---|---|
| 1 | Cancel failed for any reason other than `-2011`; venue state unknown. Do not sell; leave protection in place | Q-C §4b | **Resolvable by observation** |
| 2 | A protective leg executed *partially*. Do not sell | Q-C §4b | **Terminal** |
| 3 | Unprotected divergence; re-place at the next generation **failed**. Do not auto-close | Q-C §7 | **Terminal** |
| 4 | Staleness exceeded, detected in the per-candle driver on a quiet bar | R5 | **Self-clearing** |
| 5 | An open position has no computable stop while `stop_loss.enabled` is true | S1 | **Terminal** |

**Self-clearing (4).** The refusal frees the budget the reconciler needs, so the
condition resolves on its own. Escalate at a *distinct* marker and promote to
terminal only if it fails to clear within N reconciliation cycles. Escalating a
self-clearing condition at the same level as a terminal one is how a `CRITICAL`
line stops being read.

**Resolvable by observation (1).** The halt persists until a query succeeds. Retry
the query on the reconciliation cadence; it costs one round trip against the
reserved floor.

**Terminal (2, 3, 5).** Nothing the bot can do. Requires an operator. Site 5 is the
sharpest of the three: reconciliation is **structurally silent** on a position with
nothing requested — Q-C §7 keys divergence off what was *requested*, so there is
nothing to compare — which means no amount of budget, cadence or patience resolves
it. Its only automatic remedy is a strategy `CLOSE` on that symbol, which may never
come.

### Site 5 against the unmanaged-holding refusal — distinct, deliberately

Both gate entries and both concern a symbol whose protection story is incomplete.
They were designed two turns apart and were checked against each other before
either was written down. They must not converge:

| | Site 5 | Unmanaged holding |
|---|---|---|
| `RefusalStage` | `COMMITTED_RISK_UNKNOWN` | `UNMANAGED_HOLDING` |
| Scope | **Portfolio-wide** — the committed-risk sum is unknown, so no daily-loss limit can be checked (`NO_MARK_PRICE`'s shape) | **Per-symbol** — the ledger is intact |
| Clears | Never, within a run | Never within a run; across a restart, once the operator sells |
| Escalation | **`CRITICAL`, terminal** | **Boot `WARNING`, once** |

**The escalation asymmetry is load-bearing.** An unmanaged holding is an ordinary,
benign state of a shared account and will be true on many boots. If it escalated at
`CRITICAL` it would train an operator to skim `CRITICAL` lines, and site 5 — the one
condition that genuinely cannot resolve — would be read as noise. That is the
failure this document's three-category split exists to prevent, applied here between
two refusals rather than within one.

Message text, written so neither can be mistaken for the other:

- `COMMITTED_RISK_UNKNOWN` — *"BTCUSDT holds an open position with no computable
  stop while risk.stop_loss.enabled is true. Committed risk cannot be summed, so no
  daily-loss limit can be checked and all entries are refused. **Nothing in this
  process will resolve this**; see docs/QB_ESCALATION.md site 5."*
- `UNMANAGED_HOLDING` — *"BTCUSDT: the account held 0.5 BTC at boot that this bot
  did not open. It is counted toward equity and **the bot will not trade or sell
  it**. Entries on BTCUSDT are excluded while it remains."*

The first says nothing will fix it. The second says the holding is yours and the bot
is standing off.

## 3. Halt entries, keep exits — the failure classes

`CLOSE` traverses the same handler chain as an entry and is ungateable by the locked
rule that an exit must always be permitted. Five classes follow, and the first and
third change the design.

**Class A — the halt does not stop what caused it.** Site 1 fires because a cancel
failed and the venue state is unknown. The halt gates *entries*. So the next bar's
`CLOSE` on that symbol re-enters cancel -> query -> sell, the sequence that just
failed, and will likely fail again — three round trips per bar, indefinitely.
**Consequence: site 1 needs a per-symbol *exit* suppression distinct from the
portfolio-wide entry halt.** A halt that leaves the failing path running is not a
halt.

**Class B — budget starvation under a halt.** Halted entries cost zero dispatch, so
budget is free — but a failing exit sequence (Class A) consumes it at three round
trips a bar. **Contained by the reserved `B_recon` floor**, and this is the case that
justifies the floor most directly: without it, the reconciliation that would clear
site 1 is starved by the exits that site 1 keeps retrying.

**Class C — portfolio-wide halt for a per-symbol cause.** Sites 1, 2, 3 and 5 are
each about one position. For sites 2 and 5 the *committed-risk sum* is genuinely
unknown, so portfolio-wide is correct — the same logic as `NO_MARK_PRICE`. For
**site 1 the ledger is intact**; only that symbol's venue state is unknown.
**Consequence: site 1 halts that symbol, not the portfolio.** Halting everything for
a failed cancel is overreach and trains an operator to override the halt.

**OPEN — site 3's halt scope is unassigned, and this note does not assign it.** The
paragraph above names sites 1, 2, 3 and 5 in its premise, then gives portfolio-wide
to 2 and 5 and per-symbol to 1, and never returns to 3. Both readings are available
from its own reasoning and neither is obviously right:

- **Per-symbol, like site 1** — the ledger is intact. Realised P&L, equity and the
  position's recorded size are not in doubt; what failed is one symbol's protection
  failing to re-place.
- **Portfolio-wide, like site 5** — the position is unprotected, so its committed
  risk is not truthfully computable, and the committed-risk sum that gates every
  entry is wrong portfolio-wide rather than on that symbol alone.

**Marked for adjudication.** See the open defect in `QC_PROTECTIVE_ORDERS.md` §7,
which is the same fact seen from the other document: under site 3 the position's
requested `stop_loss` is non-`None`, so the committed-risk sum prices a level known
not to rest. Whether that makes the state per-symbol or portfolio-wide is exactly
the question left open here.

> **Still open after M5a, and M5a shipped evidence bearing on it rather than an
> answer.** `COMMITTED_RISK_UNKNOWN` now exists as a `RefusalStage` and refuses
> **portfolio-wide**, before the limits are consulted, whenever
> `Portfolio.committed_risk` reports any position it could not price. So the
> *mechanism* a portfolio-wide reading of site 3 would use is built and behaves as
> Class C's second bullet describes.
>
> **That is not an adjudication and must not be read as one.** Nothing in `src/`
> assigns `Position.protection` yet, so site 3's state cannot arise and the shipped
> refusal has never seen it. What M5a settled is narrower and worth having: the
> refusal is scoped by `stop_loss.enabled`, so "stops are off" and "no computable
> stop while stops are on" are already distinguished — which is a discriminator any
> answer to this question will need, whichever way it goes.
>
> **What survives unchanged:** the question, both readings, and the reason neither
> is obviously right. The natural moment to settle it is M5d, when the reconciler
> that produces the state is written.

**Class D — the halt is a ratchet toward flat.** Entries stop, exits continue, so the
book only shrinks. That is intended, and worth stating so it is not mistaken for a
bug: a halted bot converges on flat and then idles.

**Class E — selling against unknown protection.** Under site 1 the *confirming query*
is the step that is failing, and Q-C §4b is explicit that the query — not the cancel
response — is what decides whether to sell, because `-2011` cannot distinguish
"already cancelled" from "already filled" and the two demand opposite actions. So
under site 1 a `CLOSE` **cannot be safely executed**, which is Class A's suppression
seen from the other side.

### The locked rule this appears to violate, and why it does not

> *"An exit must always be permitted — a limit that could trap an open position would
> be a risk rule that creates risk."*

That lock governs **risk limits**: a policy refusing a legitimate action. Suppressing
an exit because we cannot determine what we hold is not a limit — it is refusing to
act on unknown state, which is what Q-C §4b already mandates in the same breath
("Do NOT sell"). The lock is not violated; it is out of scope.

`CLAUDE.md` says so on the bullet itself, because the next reader will land on
exactly this and read a contradiction.

## 4. Clearing a halt

| Category | Cleared by |
|---|---|
| Self-clearing (4) | Reconciliation catching up; automatic |
| Resolvable by observation (1) | A successful query on the reconciliation cadence |
| Terminal (2, 3, 5) | Operator action. In M5 that means a restart, plus boot re-detection — **except site 2**, which a restart forgets, and **site 5**, which a restart converts into an unmanaged holding rather than resolving (§1) |
