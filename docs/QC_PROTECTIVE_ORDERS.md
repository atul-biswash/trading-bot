# Q-C — Where the protective levels live

**Status:** decide-and-document. No `create_order` in this milestone. Findings are
marked MEASURED (Testnet probe), DOCUMENTED (Binance published docs), or
UNMEASURED.

## 1. Decision

Entry and protection are placed together in one order-list call. There is no
client-side/exchange split.

**Precisely what is atomic.** Protection is *accepted* at the same instant the
entry is accepted — legs sit `PENDING_NEW` from placement (MEASURED). There is no
moment at which the entry exists and protection has not been accepted.
**Acceptance is not activation.** Pending legs carry `workingTime=-1` and become
live only when the working order fills; Binance documents a post-fill window in
which the entry reads `FILLED` while pendings still read `PENDING_NEW`
(DOCUMENTED). Whether a stop would trigger inside that window is UNMEASURED — no
probe ever filled a working leg. "Structurally zero" describes the acceptance gap,
not the activation gap.

`check_exit` is retained and demoted from actor to divergence monitor.

**Rejected — client-side protection.** Its failure is unbounded: a crash, a lost
socket or a deploy leaves an open position with nothing watching it.

**Collision with a locked decision, resolved here.** `CLAUDE.md` locks: *"Exit
evaluation is fed the closed candle's `close`, never its high/low."* That is
correct for a client-side stop and wrong for an exchange-resting one, which
triggers intrabar. The rule is **RE-SCOPED, not repealed**: it governs *client-side
exit evaluation*, where triggering on a price the bar has left is dishonest. A
resting order's fill is not a client decision. Consequence: `backtesting/` must
model intrabar triggering to keep backtest and live on one code path. Both
statements are now reconciled in `CLAUDE.md`, which carries the re-scoping in the
same bullet as the original rule rather than in a second place that could drift
from it.

## 2. Placement shapes

Config toggles `stop_loss.enabled` and `take_profit.enabled` independently, and a
dummy never-filling leg is impossible — `PERCENT_PRICE_BY_SIDE` bounds every
pending price to 0.5x-2x of the 5-minute average, enforced at submission, with a
violation refusing the whole list (MEASURED, S4). The arity branch is irreducible.

| Config | Shape | Endpoint |
|---|---|---|
| stop + TP | OTOCO, 3 legs | `v3_post_order_list_otoco` |
| stop only | OTO, 2 legs | `v3_post_order_list_oto` |
| TP only | refused at config load † | — |
| neither | single order, `LIMIT` + `FOK` | `create_order` |

† **RESOLVED at M5a — the row is now current behaviour.** This dagger previously
read *"Target state, not current behaviour… the refusal lands in M5a"*, and it has.
`RiskConfig._check_protective_coverage` gained a third check and refuses a
take-profit configured with no stop at load, before any client exists.

> **Annotation added at M5a's rotation.** The dagger is kept rather than deleted
> because two things it recorded are still worth reading. First, the refusal
> remains **ours**, not the exchange's — nothing downstream is unable to compute a
> take-profit-only configuration, no filter forbids it, and this bot accepted it
> until M5a. The shipped message names the opinion as ours in those words, and a
> test asserts that it does, because an operator who reads it as an exchange
> constraint will go looking for a filter that does not exist. Second, **the
> refusal keys on take-profit WITH no stop, never on the absence of a stop alone**:
> both-disabled stays reachable with a boot warning, because `SignalAction.CLOSE`
> exists so a strategy can own its exits and that style is deliberately preserved.
>
> One thing this table does not show: an `rr` take-profit with no stop is a
> **strict subset** of this case, so the two checks are ordered — the `rr` check
> runs first, or it would be unreachable and the operator would lose the reason
> their target cannot be computed at all.

The neither-enabled branch uses **the same entry mechanic as every other shape** —
`LIMIT` at `entry_limit`, `FOK`. The entry mechanic is a property of the entry, not
of the protection around it, and the unprotected branch is the one place a
divergent mechanic would be least visible.

**TP-only is refused** in `RiskConfig`, extending the existing coupling validator
(renamed `_check_protective_coverage`, separate commit). Reason: uniquely adversely
shaped — winners truncated, losers unbounded — and under exchange-resting
protection the favourable exit survives a crash while the unfavourable one does
not. Nothing is lost: a wide `stop_loss.percent` expresses the same intent and
names the tolerance, bounded at roughly -50% by the measured band.

**This refusal is a JUDGEMENT about payoff shape, not a measurement.** The code
accepts the configuration today and so would the exchange.

**Neither-enabled stays reachable**, with a boot `WARNING`. `SignalAction.CLOSE`
exists so a strategy can own its exits; portfolio limits still apply.

## 3. Leg types and full parameter sets

| Slot | Type |
|---|---|
| Working | `LIMIT`, `FOK` |
| Below | `STOP_LOSS` (stop-market) |
| Above | `TAKE_PROFIT` (stop-market) |

`MARKET` is refused as a working type (MEASURED, `-1159`). `LIMIT` is refused in the
pending-above slot (MEASURED, `-1158`).

**OTOCO — 16 parameters (MEASURED, T2 accepted):**

```
symbol  listClientOrderId
workingType=LIMIT  workingSide=BUY  workingPrice  workingQuantity
workingTimeInForce=FOK  workingClientOrderId
pendingSide=SELL  pendingQuantity
pendingAboveType=TAKE_PROFIT  pendingAboveStopPrice  pendingAboveClientOrderId
pendingBelowType=STOP_LOSS  pendingBelowStopPrice  pendingBelowClientOrderId
```

Forbidden (`-1106` if sent): `pendingAbovePrice`, `pendingAboveTimeInForce`,
`pendingBelowPrice`, `pendingBelowTimeInForce`.

**OTO — 13 parameters (MEASURED, T1 accepted first attempt):**

```
symbol  listClientOrderId
workingType=LIMIT  workingSide=BUY  workingPrice  workingQuantity
workingTimeInForce=FOK  workingClientOrderId
pendingType=STOP_LOSS  pendingSide=SELL  pendingQuantity  pendingStopPrice
pendingClientOrderId
```

Note the **plain `pending*` prefix**, not OTOCO's `pendingAbove*`/`pendingBelow*`.

**`TAKE_PROFIT` over `LIMIT_MAKER`, on one reason:** `LIMIT_MAKER` is post-only, so
it carries an *additional* rejection mode at activation whose blast radius on the
sibling stop is UNMEASURED. `TAKE_PROFIT` does not. **Both share an unmeasured
activation-time filter exposure** — a triggered stop-type order becomes a market
order, and whether `MARKET_LOT_SIZE` / `NOTIONAL.applyMinToMarket` bind a triggered
order is UNRESOLVED (§10). The asymmetry is one extra mode, not a clean one.

*A "one price versus two" argument was raised in review and WITHDRAWN: both
candidates carry exactly one price (B7 proved `pendingAboveTimeInForce` is
forbidden on `LIMIT_MAKER`). That argument rules out `TAKE_PROFIT_LIMIT` only.*

*Supporting, post-hoc, and NOT a reason the decision rests on: the chosen leg set
(`LIMIT`, `STOP_LOSS`, `TAKE_PROFIT`) is already fully expressible by the existing
`OrderType` enum, whereas `LIMIT_MAKER` would have required adding a member to
`core/`. Noticed after the decision, recorded so the rejected option is not
credited with a cost it did not carry.*

**Algo slots: a protected position costs 2 of 5 per symbol** (`STOP_LOSS` +
`TAKE_PROFIT`), up from 1 under `LIMIT_MAKER`. Cannot bind at one position per
symbol. *`STOP_LOSS_LIMIT`=1 and OCO=1 are MEASURED; `TAKE_PROFIT`'s cost is
INFERRED from it being a stop-type order.*

> **Annotation added at M5a's rotation — the CEILING is now measured; the COST is
> still inferred.** The two halves of "2 of 5" had different statuses and this
> section stated only one of them. `MAX_NUM_ALGO_ORDERS = 5` is now MEASURED and
> modelled on `SymbolInfo` *(`GET /api/v3/exchangeInfo`, TESTNET, BTCUSDT and
> ETHUSDT, 2026-08-08, read-only)*, so the denominator is no longer taken on
> trust. **The numerator is unchanged**: `TAKE_PROFIT` costing one slot remains
> INFERRED from it being a stop-type order, and measuring it needs a placement
> rather than a read.
>
> **A second ceiling on the same object was missing from this section entirely.**
> `MAX_NUM_ORDER_LISTS = 20`, measured in the same call and now also on
> `SymbolInfo`. Under this contract every protected position **is** an order list,
> so lists are a second budget alongside algo slots and §3 counts only the first.
> It cannot bind at `limits.max_open_positions = 3`, so nothing here changes — but
> **whether terminated lists age out of that count is UNKNOWN and must not be
> assumed either way.** If it counts only live lists, 20 is unreachable here; if it
> counts lists created in a window, one symbol on a 1-minute bar reaches 20 in
> twenty minutes and fails at submission for a reason no code path anticipates.
> Carried as an open item in `docs/NEXT_MILESTONE.md`.

**Cost, stated plainly:** risk-per-trade is a PRE-SLIPPAGE guarantee and the
take-profit is a PRE-SLIPPAGE target. Neither is exact.

## 4. Entry mechanics

`entry_limit = round_to_tick(close x (1 + max_entry_slippage), ROUND_FLOOR)` — a
marketable limit. Slippage is bounded by an operator-chosen number, not by the book.

> **SUPERSEDED in its rounding mode only — annotation added at M5b's rotation.**
> Transcribed verbatim from commit `dcf4a93`'s message:
>
> > Section 4's `ROUND_FLOOR` is superseded by `ROUND_CEILING` at M5b commit
> > 10. `ROUND_FLOOR` enforces the configured bound but makes
> > `entry_limit >= reference_price` a property of the feed rather than of the
> > function — an off-grid close produces a limit below the close and a
> > `ValidationError` on the decision path. D3 locked that comparison as a type
> > invariant afterwards, and an invariant contingent on the feed is not one.
> > The cost, stated rather than discovered: `max_entry_slippage` is no longer
> > an enforceable ceiling; the overshoot is bounded by `tick/price`.
> > Everything in section 4's second paragraph survives unchanged.
>
> **The paragraph immediately below this annotation is that second paragraph, and
> it SURVIVES UNCHANGED.** `entry_limit` remains the reference for both the
> protective levels and sizing; commit 10 implemented exactly that, and the
> realised-distance guarantee it states is what the `risk_per_trade` budget rests
> on. Only the rounding mode moved. The derivation now lives in
> `risk.rules.derive_entry_limit`.
>
> One consequence worth recording, because no measurement in this project would
> have caught it: the existing suite **cannot discriminate the two rounding
> modes**. On the default fixture `100.00 x 1.001` is `100.1`, exactly on a 0.01
> tick, so ceiling and floor agree — the whole change set was measured under both
> and produced an identical blast radius. Reading this document is what found the
> contradiction.

**`entry_limit` is the reference for both protective levels and for sizing.** Using
the bar close would let a fill at `entry_limit` produce a realised entry-to-stop
distance larger than the one sizing used — realised risk silently exceeding
configured risk. With `entry_limit`, realised distance <= planned distance.

`FOK` makes a working-leg partial fill impossible, deleting the one question
unmeasurable without a fill. MEASURED: all legs `EXPIRED`, `ALL_DONE`, zero
residue, on both shapes.

**Unfilled entry: log `entry_unfilled`, drop the signal.** No retry, no chase — the
edge was on that bar. The miss is observable at dispatch, not silent.

## 4b. The discretionary close path

A strategy `CLOSE` against a position with resting protection cannot be
dispatched as a bare SELL. On spot, the discretionary sell and a protective leg
triggering moments later would both complete, and the second sells base no longer
held.

**The sequence is cancel → confirm → sell, and the order is forced.**

Sell-then-cancel leaves a window in which the position is flat and a protective
leg is still live. Cancel-then-sell leaves a window in which the position is open
and unprotected. The first window can produce an unintended short-side sell
against a zero balance; the second produces a bounded, monitored exposure between
two calls the client is actively making. **Unprotected-and-known is preferable to
protected-against-nothing**, so cancel goes first.

> **MEASURED at M5c: ONE cancel collapses the whole list.** Cancelling the
> working leg alone auto-cancelled both pending legs; cancels subsequently issued
> for those legs returned `-2011 'Unknown order sent.'`, and the list went to zero
> open on both `get_open_orders` and `v3_get_open_order_list`. *(TESTNET,
> BTCUSDT, 2026-08-12.)*
>
> So the cancel step of cancel → confirm → sell is **one call, not three**, and
> the `-2011` from any redundant per-leg cancel is the benign row of the table
> below rather than a failure. A close path written to drive three cancels to
> success would treat its own normal teardown as two errors.

**Cancel failure is classified, not retried blindly.**

| Outcome | Meaning | Action |
|---|---|---|
| Cancel succeeds | Legs gone | Confirm by query, then SELL |
| `-2011 'Unknown order...'` | Already terminal | **NORMAL** — confirm by query, then act on what the query says |
| Any other failure | Unknown venue state | Do NOT sell. `CRITICAL`, halt entries, leave protection in place |

**"Cancel failed because it already filled" is a normal outcome, not an error.**
A protective leg that filled between the bar close and the cancel has already
closed the position — the correct response is to record that exit, not to sell
again. This is why confirmation is by **query**, never by the cancel response:
`-2011` alone cannot distinguish "already cancelled" from "already filled", and
the two demand opposite actions.

**The confirming query decides what happens next**, and it reads `executedQty` on
each leg, not merely `status`:
- No leg executed → position still open → dispatch the SELL.
- A leg executed in full → the position is already closed → record the exit,
  dispatch nothing.
- A leg executed partially → **UNMEASURED** (§10). Treat as `CRITICAL`, halt
  entries, do not sell. `FOK` removes partial fills from the entry path but not
  from a triggered protective leg.

**The discretionary SELL is `MARKET`.** A `CLOSE` is a decision that the position
should not be held; a limit that misses would leave it held and unprotected, which
is the state this sequence exists to minimise. This is the one place the design
accepts unbounded slippage for certainty of exit — the same trade-off as the
`STOP_LOSS` leg, for the same reason.

**The window is bounded and reportable.** Between the confirmed cancel and the
SELL's acknowledgement the position is open and unprotected. That window is one
round trip, is entered deliberately, and must be logged on entry and exit with the
symbol and position identity, so an operator can see it in the record rather than
infer it.

## 5. `Position`

Add `entry_bar_time` (ID seed; `opened_at` is wall-clock and unusable after
restart), `protection: ProtectionState`, `order_list_id`, `last_reconciled_at`.

`ProtectionState` must include `ABSENT_BY_DESIGN` distinct from unexpected absence,
or a neither-enabled config reads as permanent divergence.

**`protection` carries no default and is not nullable.** `ABSENT_BY_DESIGN` is the
tempting default and is the wrong one: it asserts "no protection is expected here",
which is the off-switch for the divergence detector on that position, so a site that
forgot the field would produce a position the reconciler has been told to ignore.
Same reasoning as `RiskAssessment.stage`, one notch stronger — `stage` is nullable
because "no stage" is a real state, while `protection` has a member for every state.

> **BUILT at M5a, with one deliberate departure from this section.** All four
> fields exist, `protection` is required and non-nullable as specified, and
> `opened_at` was made explicit alongside `entry_bar_time` rather than left to be
> mistaken for it.
>
> **`ProtectionState` shipped with TWO members, not the five this contract names.**
> `ABSENT_BY_DESIGN` and `UNKNOWN` only; `PENDING`, `ACTIVE` and `DIVERGED` land
> with the milestones that first *write* them. The reason is this section's own
> argument about `protection` turned on the enum: it is the one field whose wrong
> value is **silent**, because `ABSENT_BY_DESIGN` switches off the divergence
> detector rather than failing. An unwritten member is a plausible-looking value
> within reach of whoever is nearest a construction site and needs something to
> type. Adding a member later is additive and moves no fixture; removing one
> already assigned somewhere is not. **This does not weaken the required-and-
> non-nullable argument above** — "a member for every state" means every state
> *reachable*, and the two shipped are exactly those: one forced by this contract
> (a both-disabled config must not read as permanent divergence), one by the
> timed-out-write rule.
>
> **What is NOT built and is not this section's to build:** nothing in `src/`
> constructs a `Position` yet, so nothing populates `protection`. The consequence
> is recorded at §7's annotation.

`stop_loss` / `take_profit` are redefined as requested levels, **immutable once
set**. What rests is queried, never cached. `trailing_stop` / `highest_price` /
`lowest_price` retained pending the trailing milestone, and `trailing_stop` is
explicitly **outside** the immutability rule — it is rewritten every bar by design.

> **STILL TRUE, and it acquired a second consequence at M5b commit 13.** Nothing
> above is superseded: the trailing fields are still retained pending the trailing
> milestone, and `trailing_stop` is still outside the immutability rule.
>
> What commit 13 added is that **committed risk no longer prices off
> `trailing_stop`**. `Portfolio._binding_stop` returns the resting level only. The
> rule is *committed risk prices off what rests at the venue*, and the resting set
> is a consequence of §3's three legs — none of which is a trailing leg — so today
> that set is exactly `{stop_loss}`. When venue-side trailing lands, a trailing
> level starts resting and becomes eligible without re-opening the decision.
>
> The defect that forced it: a trailed position priced its forward risk off a
> level held only in memory, understating it by 58% on the measured fixture
> (`sl=88, tr=95, mark=100, qty=10` gave `-50` where what rests gives `-120`), so
> the daily-loss check permitted entries on protection that does not exist. It is
> latent only because `advance_trailing_stop` is `trailing_stop`'s sole writer in
> `src/` and has no caller.
>
> `should_exit` still prefers the trail, and that asymmetry is deliberate:
> `should_exit` asks whether to exit **now**, `_binding_stop` asks what happens if
> the bot **stops running**. Only the second is what committed risk means.

> **"The trailing milestone" has no owner, and at M5c that stopped being an
> oversight and became a finding.** This section defers the design to a milestone
> that does not exist, while `CLAUDE.md` assigns *driving*
> `advance_trailing_stop` to execution — so **the two documents have been
> pointing at each other**, and a reader arriving at either was sent to the other.
>
> Neither can resolve it, because the question is prior to ownership: **does the
> trailing level rest at the venue, or does it not exist?** §3 fixes the list at
> three legs and none is a trailing leg, so today the answer is "it does not
> exist" and a trailing level is client-side — which §1 rejected outright.
>
> **The single home for that question is `docs/NEXT_MILESTONE.md`'s item 2**, not
> this section and not `CLAUDE.md`. Both now point *there* rather than at each
> other. Answering it needs either an amendment to §3's leg set or a reopening of
> §1, and **M5c did neither** — it named the question and stopped.

**"Immutable once set", not "immutable after entry", and the difference is
load-bearing.** §7 keys divergence off what was *requested*, so a position with
nothing requested gives reconciliation nothing to compare: the reconciler is
**structurally silent** on it, and no budget, cadence or patience resolves the state.
Under the committed-risk rule such a position also refuses every entry,
portfolio-wide, permanently — the one refusal in the system that cannot clear.

A position that has *never* carried a requested stop is therefore outside this
rule's premise, and protection may be **re-requested** for it through the same
next-generation machinery §7 specifies for unprotected divergence. A level that has
been set stays immutable.

Reachable routes to the state are narrow but real: `stop_loss.enabled` flipped
`false` → `true` between runs with a position open, and the placement-unknown state
after a timed-out write. Adoption of pre-existing holdings is **not** a route — see
§5b — because no `Position` is ever constructed for a holding the bot did not open.

Where detectable at boot it is refused at boot, before any socket, in the family of
the five existing root refusals. Where it is not, it escalates as a **terminal**
`CRITICAL` (`docs/QB_ESCALATION.md`, site 5), because a refusal that can never clear
is not a refusal and an operator who reads it as "wait for the next bar" will wait
forever.

## 5b. Pre-existing holdings are not adopted as positions

Today `_seed_portfolio` reads only the quote balance and builds an empty `positions`
dict, so the bot does not adopt base holdings — **by accident, not by decision**.
This settles it, because it determines whether §5's boot refusal is reachable at all,
and because a bot that adopts holdings it did not open is a different product.

**The case for adopting.** The account is the truth. A holding the bot cannot see is
not in `equity`, and equity is the denominator of every sizing decision and of the
daily-loss threshold. Understated equity is conservative in isolation, but the
wrongness is not confined: with no adoption, `has_position` is `False` regardless of
what the account holds, so a `BUY` passes `ALREADY_IN_POSITION` and buys **more**,
sized against an equity that excludes the holding it is adding to.
`max_position_size_percent` is computed against the wrong denominator. **The bot can
pyramid onto a manual holding without knowing it exists.** That is a safety argument,
and it is the strongest one on either side.

**The case against.** A holding the bot did not open has no entry price, no stop, no
take-profit, no `entry_bar_time`. `Position.entry_price` is required `Money`; using
the current mark makes `unrealized_pnl` identically zero by construction and every
P&L figure about it fiction. It has no requested protection and no legitimate way to
have had any — which is exactly §5's terminal state, manufactured at boot on every
run. And adopting means the bot will eventually **sell an asset a human bought**, on
a strategy `CLOSE`, through cancel → query → `MARKET`.

**Decision: count material holdings toward equity; never construct a `Position` for
them; refuse entries on their symbol.**

| Consumer | Behaviour |
|---|---|
| `equity` | Counts the holding. Denominator correct |
| entries | Refused on that symbol under `UNMANAGED_HOLDING` while it remains |
| `CLOSE` | `_exit_assessment` finds no `Position` and returns `NOTHING_TO_CLOSE`. **The bot never sells it** — enforced by the existing code path, not by a new guard |
| §5's route 3 | **Closed by decision.** No `Position` is constructed without the bot having opened it, so adoption cannot manufacture a stopless position |

**Materiality is `min_notional`.** A holding worth less than the symbol's
`min_notional` cannot be sold at all, so it is definitionally dust, and dust must not
block a pair forever. The threshold is already on `SymbolInfo`, is exchange-supplied,
and is the one number in this milestone that needs no provenance line.

**The snapshot is taken at boot, before any `Position` exists, and that timing is the
correctness argument.** Measuring "unmanaged base" from raw balances at any later
moment would count base held by positions *the bot opened*: `equity` would
double-count it (once as `quantity × mark`, once as an unmanaged holding) and the
refusal would mislabel — reporting `UNMANAGED_HOLDING` where the truth is
`ALREADY_IN_POSITION`. At boot `positions` is empty by construction, so the snapshot
excludes bot-owned base with no arithmetic, and the set is then immutable for the
process lifetime because the bot never sells an unmanaged holding.

The honest consequence: **the refusal does not clear within a run.** It clears across
a restart, once the operator has sold. It escalates as a boot `WARNING`, once —
never `CRITICAL`, because it is an ordinary state of a shared account and escalating
it would train an operator to skim the level that carries §5's terminal condition.

**One gap, named rather than absorbed.** `_mark_prices` prices open positions from
`last_candle`; an unmanaged holding in an asset with **no configured pair** has no
mark source. Refusing the boot over an unrelated asset is too aggressive, and
silently ignoring it is today's behaviour. So: ignore unpriceable holdings and log a
`WARNING` naming the asset and the fact that it is excluded from equity. The
resulting error in equity is conservative (understated), and the warning is what
stops it being invisible.

## 6. Client order IDs

```
tb1-{symbol}-{entry_bar_time_ms}-{gen}-{leg}
```

**The guarantee, stated precisely.** Generation 0 is DERIVABLE from
`(symbol, entry_bar_time)` alone — pure computation, no persistence, no I/O. Any
generation above 0 is RECOVERABLE but not derivable: it requires querying
prefix-matching orders and taking the highest seen, so recovery needs a successful
exchange round trip and fails if the exchange has aged those orders out of its
query window. The scheme is **not** "no persistence needed" without qualification;
it is "no persistence needed for the first placement, exchange-recoverable
thereafter."

The generation segment exists because re-placement after an unprotected divergence
would otherwise collide with consumed IDs and return `-2010 'Duplicate order sent.'`
(MEASURED).

> **"Consumed" is narrower than it reads, and this is now MEASURED at M5c:**
>
> > **A client order ID is unique against LIVE orders only. A terminal order's ID
> > is RELEASED and immediately reusable. This holds identically for single
> > orders and for order lists.**
>
> *(TESTNET, BTCUSDT, 2026-08-12. Live single with a repeated `newClientOrderId`
> → `-2010`; the same ID after cancelling that order → accepted with a new
> `orderId`; a live order list resubmitted byte-identical → `-2010`; a terminated
> list resubmitted byte-identical → accepted, new `orderListId`, new leg
> `orderId`s, leg `clientOrderId`s honoured byte-for-byte. The full table and the
> re-place branches are in §8.)*
>
> **What this means for the generation segment: it is still required, and its
> justification narrows.** It is not needed to avoid colliding with *terminated*
> orders — those IDs are free. It is needed for the case §7 actually describes: a
> re-placement while the previous generation's legs are **still resting**, which
> is exactly when a collision would occur and exactly when re-placing matters.
>
> **A consequence that is NOT a collision and is carried as an open item:** if
> terminal IDs are released, a client order ID is not a unique key *across time*,
> so two different orders can carry the same one. See
> `docs/NEXT_MILESTONE.md` for the reconciliation question that raises.

Prefix `tb1-` is required because `get_open_orders` returns **every** order on the
symbol, ours and otherwise, and only a prefix distinguishes them.

> **`{leg}` AND THE LIST-LEVEL ID ARE NOW BOUND, and section 6 did not bind
> either.** Recorded here because implementation closed two things this section
> left open, and a reader arriving cold would find no form to follow.
>
> **The leg vocabulary is `W` / `SL` / `TP`**, bound by `OrderListLeg` in
> `exchange/ids.py`. §8 records those codes only as what one probe happened to
> send; they are now the scheme's. The choice was made WHILE IMPLEMENTING
> rather than decided in advance -- defensible, since they are the only codes
> the venue is measured to honour byte-for-byte, and consequential, since the
> two-character codes are what force the generation ceiling.
>
> **The list-level ID is `tb1-{symbol}-{ms}-{gen}-L`** -- the same seeds, guard
> and bound, with `L` in the leg position and deliberately NOT a member of
> `OrderListLeg`, because a list is not a leg. §3 requires `listClientOrderId`
> on both shapes and this section defines no form for it.
>
> **That form was OBSERVED AT M5c, not chosen at M5d.** M5c's probe already
> sent `tb1-BTCUSDT-<ms>-0-L`, with control arms suffixing it (`-L8`, `-Lz36`);
> M5d re-derived it without knowing. **The agreement is not evidence**: the
> second derivation could not have been contradicted by the first, because it
> did not know of it. Two independent guesses agreeing shows the answer was
> obvious, not that it was right.
>
> **The generation ceiling is 99**, derived: an ID is
> `20 + len(symbol) + digits(generation) + len(leg)`, so a 12-character symbol
> with a 2-character leg admits two digits. Enforced in `exchange/ids.py`, with
> an output guard that re-validates length and character class **separately**,
> because the venue reports a length violation as "Illegal characters found". Note the library
tag is *not* the reason: `create_order` auto-injects `x-HNA2TXFJ` plus a random
suffix when no ID is supplied (MEASURED), but the order-list endpoints are **raw
passthrough and inject nothing** (MEASURED — unsupplied leg IDs came back
exchange-generated, not library-tagged). Only the neither-enabled branch uses
`create_order`. Leg IDs are honoured byte-for-byte on **both** shapes (MEASURED,
T1 for OTO and T2 for OTOCO).

## 7. Reconciliation

**Keyed off what was REQUESTED, never off what is absent.** Divergence is
"protection was requested and does not rest," not "no legs are resting."

Compared: existence, `status`, `executedQty`, `origQty`, `clientOrderId`,
`orderListId`, and per-type legally-sendable prices. `stopPrice` round-trips and is
compared — but **numerically, not as a string**: `"40917.83"` is returned as
`"40917.83000000"` (MEASURED, B2), so the comparison is `Decimal`-normalised and a
string comparison would manufacture divergence every cycle. `price` and
`timeInForce` on a stop-market leg are server defaults and are excluded entirely —
comparing them manufactures divergence for the same reason (MEASURED, B2/B3/B4).

> **WHICH ENDPOINT SUPPLIES THIS SET IS NOW MEASURED, AND IT IS NOT THE LIST
> READ-BACK.** This paragraph reads as though a list query is the
> reconciliation view. It is not, and cannot be.
>
> `v3_get_order_list` returns each leg as an **identity triple** --
> `{symbol, orderId, clientOrderId}` and nothing else. No `status`, no
> `executedQty`, no `origQty`, no prices (MEASURED at M5d against a captured
> payload whose full key set was enumerated in the same read).
>
> `get_open_orders` returns **full order objects for all three legs, including
> pendings in `PENDING_NEW`**, carrying `status`, `executedQty`, `origQty` and
> `stopPrice` (MEASURED at M5d against a live OTOCO). **That is where the
> compare set comes from**, and §6's `tb1-` prefix is what separates our legs
> from everyone else's in the result.
>
> **The consequence for cost runs in the cheap direction**, which is worth
> stating because the first analysis got the sign wrong: the compare set costs
> **one call per symbol, amortised across every position on that symbol** --
> not one list query per position, and not the four-calls-per-position figure a
> mid-milestone finding briefly proposed. See `docs/M5_NUMBERS.md`'s `T_recon`.
>
> The list read-back keeps one irreplaceable use, and only one: it is a view of
> a **terminated** list, which distinguishes "never placed" from "placed and
> already gone". `v3_get_all_order_list` and a per-leg `get_order` also show
> terminated state, and `v3_get_all_order_list` is the one that avoids §8's
> reused-ID ambiguity -- see `docs/NEXT_MILESTONE.md`.

**Shape is identified by leg count or by our own IDs.** `contingencyType` reads
`"OTO"` on every payload of both shapes and never once `"OTOCO"` (MEASURED).

**The placement response is not a source of truth for list identity.**
`listClientOrderId` is deterministically `null` there when a list terminates in the
same call, while the leg IDs in that same payload are correct (MEASURED, T1).

> **NARROWED at M5d: the null is a property of TERMINATING IN THE SAME CALL,
> not of the placement response.** A list that did **not** terminate in its
> placement call returned `listClientOrderId` **populated**, carrying the value
> we derived and sent *(TESTNET, BTCUSDT, order list 91590, 2026-08-14)*. That
> is the first observation of the non-terminating case, and it means an absent
> value never carries information about the list -- only about the call.
>
> The sentence's conclusion is unchanged and the reasoning under it improves:
> the placement response is still not a source of truth for list identity,
> because **we derive that identity ourselves** and never need the response to
> supply it.

> **Five earlier measurements RE-CONFIRMED at M5c — re-confirmations, not new
> results, and listed together because they were taken in one run against a
> different question.** *(TESTNET, BTCUSDT, 2026-08-12, the duplicate order-list
> probe.)* Nothing here changes a decision; the value is that claims the design
> rests on were re-observed on a later day, on a live venue, by a probe that was
> not looking for them.
>
> 1. `contingencyType` reads **`"OTO"`** on every OTOCO payload and never once
>    `"OTOCO"` — §7, above.
> 2. `listClientOrderId` is **`null`** in the placement response and **present**
>    in the `v3_get_order_list` read-back of the same list — §7, this paragraph.
> 3. A `FOK` working leg that cannot fill expires the whole list: every leg
>    `EXPIRED`, `expiryReason` `UNFILLED_FOK_ORDER_EXPIRED`, `ALL_DONE`, zero
>    residue — §4.
> 4. Leg `clientOrderId`s are honoured **byte-for-byte** — §6.
> 5. The order-list endpoints are **raw passthrough and inject no library tag** —
>    §6. Every returned `clientOrderId` was exactly what was sent.

**A filled working order legitimately returns with pendings still `PENDING_NEW`**
(DOCUMENTED; the fill path is UNMEASURED). Never escalate on the placement
response. Re-query with a **BOUNDED DEADLINE**; escalate only if the pendings are
still `PENDING_NEW` after it. Without a deadline, "entry filled, protection never
materialised" is indistinguishable from the normal transient.

`expiryReason` gives a machine-readable cause: `UNFILLED_FOK_ORDER_EXPIRED` vs
`OTO_PHASE_ONE_EXPIRED`. Present on both shapes; both protective legs share the
latter, so it explains the phase, not the leg (MEASURED, T2).

Moments: at boot, after each placement, per candle per open position.

Unprotected divergence → re-place once at the next generation; on failure
`CRITICAL`, halt entries, **do not auto-close**. Re-placing is reversible; closing
realises a loss on a possibly-transient read.

**OPEN DEFECT — committed risk prices a stop this section knows is not resting.**
Divergence is keyed off what was *requested*, so a position in the site-3 state has
a non-`None` `stop_loss` **by definition** — that is how the divergence was
detected. `CLAUDE.md`'s committed-risk term selects `binding_stop` from the
position's requested levels and sums `min(0, (binding_stop − mark) x quantity)`, so
it prices a level known not to rest.

**Consequence: committed risk is UNDERSTATED, and the daily-loss check therefore
permits entries on the strength of protection that does not exist — on the one
position the system knows to be unprotected.**

The uncomputable-risk discriminator cannot see it: that test is `stop_loss is None`,
scoped by `stop_loss.enabled`, and here `stop_loss` is not `None`. `ProtectionState`
can see it, which is the argument for keying the uncomputable count off `protection`
as well as off `stop_loss`.

> **NARROWED at M5b's rotation: "`ProtectionState` can see it" is true of THIS
> state — the site-3 divergence — and of nothing wider.** The sentence above reads
> as though `protection` discriminates the whole class of "the binding level does
> not rest". It does not, and the over-generalisation reached a ruling at M5b
> commit 13 before measurement rejected it.
>
> The counter-case is a **trailed** position: its `STOP_LOSS` leg rests exactly as
> requested, so it is `ACTIVE` in every sense this enum will mean, and yet its
> committed risk was priced off a trailing level that rests nowhere. Neither
> branch of `protection` helps — admitting `ACTIVE` to `_TRUSTED_PROTECTION` counts
> it and counts it wrong, while leaving `ACTIVE` untrusted refuses every entry
> portfolio-wide for a healthy position. The error there is in **level selection**,
> not in protection state, and commit 13 fixed it there.
>
> So the two defects are siblings, not one: same consequence (understated
> committed risk), different cause, different discriminator. Commit 13 closed the
> selection half and **this section's defect is untouched by it** — a position
> whose *requested* stop is not resting still prices off that stop, because that
> level is non-`None` by definition. **Still M5d's, still open.**

> **THE MECHANISM STATED FOUR PARAGRAPHS ABOVE IS STALE, and it is the sentence
> "the uncomputable-risk discriminator cannot see it: that test is `stop_loss is
> None`, scoped by `stop_loss.enabled`" that fails.** Annotated at M5d, not
> amended, per the rule that a finding later found wrong is annotated in a
> subsequent block.
>
> **The discriminator has a third clause.** `core/portfolio.py:444` reads
> `stop is None or mark is None or position.protection not in
> _TRUSTED_PROTECTION`. The `protection` clause was added at M5a, and this
> section's own M5a annotation below records it — *"keying off `protection` is
> already wired"* — but the defect paragraph was never brought into line, so the
> two halves of this section disagree about what the code does.
>
> **What follows is narrower than the stale text implies, and sharper.** The
> discriminator sees *everything except one pairing*: `ABSENT_BY_DESIGN` with a
> non-`None` `stop_loss`. Under `UNKNOWN` the position is already counted
> uncomputable. So site 3 does not escape because the discriminator is blind to
> protection state; it escapes through a single **incoherent** pair —
> `ABSENT_BY_DESIGN` asserts no protection is expected, and a requested stop
> contradicts it. Measured at M5d over the full space: 0 of 16 `(protection,
> level)` pairings reach the pricing arm once that pair is excluded, so the
> incoherent pair is not an edge case but the **whole** of the pricing arm.
>
> Pinned by `test_an_absent_by_design_position_with_a_requested_stop_is_priced`
> (M5d commit 1a), whose docstring says closing site 3 inverts it.

**Latent, not live.** The site-3 state requires a detected divergence *and* a failed
re-place, and the reconciler that produces it does not exist yet. That bounds how
alarming this is today; it does not bound how alarming it is once M5d lands.

**Not fixed here.** The reconciler is M5d's. This note exists so that M5a does not
lock a `committed_risk` signature that forecloses the fix, and so that whoever
writes M5d does not have to rediscover the interaction. Whether such a position
should count as *uncomputable* (refuse) rather than as *mispriced* (understate) is
the natural fix and is deliberately **not** prescribed here.

> **Annotation added at M5a's rotation — the note DID its job, and the defect is
> unchanged.** `Portfolio.committed_risk` shipped returning `(total,
> uncomputable)`, and the uncomputable test reads `stop is None or mark is None
> or position.protection not in _TRUSTED_PROTECTION` — so the signature this note
> existed to protect is in place and **keying off `protection` is already wired**,
> not merely possible.
>
> **What has NOT changed is the thing that matters.** `_TRUSTED_PROTECTION` is a
> whitelist containing only `ABSENT_BY_DESIGN`, and nothing in `src/` assigns
> `Position.protection` at all, so the operative condition today is still the
> absent stop level. A position in the site-3 state would still price off a
> requested stop known not to rest. **This note is not discharged**; M5a built the
> shape and M5d must still close the defect.
>
> One consequence of `_TRUSTED_PROTECTION` being a whitelist is worth stating
> here rather than leaving to be inferred: when `PENDING`, `ACTIVE` and `DIVERGED`
> are added, each defaults to **untrusted** until someone deliberately admits it.
> For `ACTIVE` that will be wrong and cheap — a spurious refusal. For `DIVERGED`
> it is right. That is the intended direction: the error that refuses an entry
> costs a missed trade, the error that trusts a stop that is not there costs the
> position.

> **"The reconciler is M5d's" IS A SCHEDULING CLAIM MADE INSIDE A CONTRACT
> DOCUMENT, and it is superseded by `docs/NEXT_MILESTONE.md`.** Annotated at M5d;
> the sentence stays where it is.
>
> **Not because the schedule changed — because a contract is the wrong home for
> one.** This document decides *where the protective levels live*. Which
> milestone builds a given component is live planning, and this project keeps
> live planning in exactly one place: `NEXT_MILESTONE.md`, *"the single home for
> live open items"*. A schedule recorded in a decided document is a fact with no
> owner: rotation re-reads the contracts for superseded prose, but nothing
> prompts a re-read when a *milestone* moves, because the milestone that moved it
> was editing different files.
>
> It had already drifted. This sentence said M5d while `NEXT_MILESTONE.md`
> scoped M5d to the adapter surface and listed no reconciler — a disagreement
> reported at M5d's opening Phase 1 and left unadjudicated until then. **Read
> `NEXT_MILESTONE.md` for the schedule; read this document for the decision.**
>
> The current answer, for readers arriving here first: the reconciler lands as
> **M5e's opening block, before any order**, and site 3 is deferred to it because
> the fix requires `ACTIVE` — a `ProtectionState` member that cannot exist before
> a writer does. Both are recorded in `NEXT_MILESTONE.md` with their reasoning.
>
> **What SURVIVES from the paragraph above, unchanged:** everything except the
> milestone name. The note's purpose — that M5a must not lock a `committed_risk`
> signature which forecloses the fix — was served and is discharged; the
> `(total, uncomputable)` shape is in place. And the choice it declines to
> prescribe, *uncomputable (refuse)* versus *mispriced (understate)*, is still
> deliberately unprescribed here.

> **SITE 3 IS CLOSED, at M5e, and NOT by the change three deferrals predicted.**
> Annotated rather than struck, because the prediction being wrong is the part
> worth keeping.
>
> Every deferral above expected site 3 to be closed by a dedicated fix needing
> `ACTIVE`. What actually closed it was the **`DIVERGED` write plus this
> whitelist's existing untrusted default**: a position whose requested stop is
> found not to rest now carries `DIVERGED`, which is outside
> `_TRUSTED_PROTECTION`, so `committed_risk`'s third disjunct fires and it counts
> uncomputable. It is never priced off the stop. That happened one commit before
> `ACTIVE` was admitted, and it required no code written for site 3 at all.
>
> `ACTIVE`'s admission, when it came, did the **opposite** thing: it widened the
> pricing arm so that a *correctly* protected position stops counting
> uncomputable. Without it the first live position would have refused every
> subsequent entry portfolio-wide — the interlock firing on the healthy path. So
> the two changes point in opposite directions and only the first is site 3's.
>
> **The choice this note declined to prescribe was made by the whitelist, not by
> a decision here:** *uncomputable (refuse)*. The alternative — pricing off a
> stop nobody has confirmed rests — is the understate direction that
> `_TRUSTED_PROTECTION`'s own comment names as the expensive one.
>
> **UNEXERCISED.** Nothing constructs a `Position` in `src/` — one grep, one
> hit, the class definition — so no position has ever carried `DIVERGED` outside
> a test. Site 3 is closed by construction and unobserved in operation.

> **FALSIFIED ON BOTH CLAUSES, and the second is the interesting one.**
> `OrderExecutor._open_position` has constructed a `Position` since M5f
> `8ca878e`. And a position HAS carried `DIVERGED` outside a test: the first
> supervised run (2026-08-27) reported `states="diverged=1"` on 28 consecutive
> reconciliation passes.
>
> **It was a defect, not site 3.** Every one of those was the identifier-space
> mismatch fixed at `3970968` — `classify_protection` compared the venue's
> numeric `orderListId` against our derived `tb1-` client id, so *correctly
> protected* positions read `DIVERGED`. The second run, after the fix, reported
> `active=1` on all 81 passes.
>
> **So site 3 remains unobserved in operation, and the sentence above is still
> the right conclusion reached through a premise that has expired.** What is
> now known is narrower and worth stating exactly: `DIVERGED` has been written
> in production, and every instance was our bug rather than a venue divergence.

## 8. Errors

`translate_binance_error` must match **message text, not code**. `-2010 'Duplicate
order sent.'` is a SUCCESS SIGNAL under deterministic IDs, not an error. `-2011` →
benign `OrderNotFoundError` on cancel paths; note `cancel_all_open_orders` raises
`-2011` on an already-clear book, so routine emptiness arrives as an exception.
Filter failures → `FilterRejectedError` carrying the parsed filter name. `-1106` →
programming error, raise loudly. `-1158` / `-1159` / `-1128` → contract errors.

> **`-2011` on a cancel path is CONFIRMED benign on a real OTO teardown, and the
> teardown itself is a measurement worth keeping.** Cancelling the **working leg
> alone auto-cancelled both pending legs**: the subsequent cancels for those two
> returned `-2011 'Unknown order sent.'`, and the list went to **zero open** —
> `get_open_orders` and `v3_get_open_order_list` both empty.
> *(TESTNET, BTCUSDT, 2026-08-12.)*
>
> Two consequences. **One cancel collapses the list**, so a reconciler or the §4b
> close path must not treat per-leg cancellation as three independent operations
> to be driven to success. And **the `-2011` those follow-up cancels produce is
> routine rather than exceptional** — the same shape §8 already records for
> `cancel_all_open_orders` on an already-clear book, now observed on the exact
> object this contract places.

> **MEASURED at M5c, and it does NOT hold for order LISTS: an exact duplicate is
> ACCEPTED.** The sentence above is a statement about a duplicate client order
> ID. Resubmitting an *accepted order list's* byte-identical parameters produces
> no error at all — no `-2010`, no rejection of any kind.
>
> *Provenance: `POST /api/v3/orderList/otoco`, TESTNET, BTCUSDT, 2026-08-12,
> resubmitted **0.647 s** after the original from the recorded request dict, never
> from the response.*
>
> | | original | exact duplicate |
> |---|---|---|
> | `orderListId` | 72321 | **72322 — new** |
> | leg `orderId`s | 2089800/01/02 | **2089803/04/05 — new** |
> | leg `clientOrderId`s | `tb1-…-0-W` / `-SL` / `-TP` | **identical, byte-for-byte** |
> | outcome | accepted | **accepted** |
>
> **Both control arms were also accepted**, so neither identity field is
> deduplicated: a **fresh `listClientOrderId` with the same leg IDs** produced
> list 72323, and the **same `listClientOrderId` with fresh leg IDs** produced
> 72324. A consumed leg `clientOrderId` is therefore reusable, and the venue
> honours it byte-for-byte on the reuse.
>
> **Scope, stated precisely.** The original was **terminal** at resubmission —
> read back immediately beforehand as `listStatusType: ALL_DONE`,
> `listOrderStatus: ALL_DONE`, every leg `EXPIRED` under `UNFILLED_FOK_ORDER_EXPIRED`.
> So what is measured is that a *terminated* list's IDs are immediately reusable.
> Whether a **live** list's resubmission is refused is UNMEASURED.
>
> The asymmetry matters and is not symmetric-looking: a *rejection* here would
> have generalised **upward** to the live case, since a live order's ID is at
> least as present at the venue as a terminated one's. **Acceptance does not
> generalise downward.** See `CLAUDE.md`'s timed-out-write annotation for what
> that costs the recovery path.

> **THE LIVE CASE IS NOW MEASURED, AND IT IS A REJECTION. The paragraph above is
> corrected rather than deleted**, per the rule that a finding later found wrong
> is annotated in a subsequent block. Its reasoning about the asymmetry was sound;
> its conclusion about what that costs the recovery path was wrong, because the
> missing measurement has since been taken.
>
> **A live order list, resubmitted byte-identical, is REJECTED with `-2010`,
> HTTP 400, `"Duplicate order sent."`** The list was confirmed live by read-back
> immediately beforehand: `listOrderStatus: EXECUTING`,
> `listStatusType: EXEC_STARTED`, working leg `NEW`, both pendings `PENDING_NEW`.
> *(TESTNET, BTCUSDT, 2026-08-12.)*
>
> **THE ACTUAL RULE, and it is not about lists at all:**
>
> > **A client order ID is unique against LIVE orders only. A terminal order's ID
> > is RELEASED and immediately reusable. This holds identically for single
> > orders and for order lists.**
>
> | State | Same ID resubmitted | Outcome |
> |---|---|---|
> | single `LIMIT`+`GTC`, resting | `newClientOrderId` | **`-2010` rejected** |
> | same single, after cancel | `newClientOrderId` | **accepted**, new `orderId` |
> | order list, live (`EXECUTING`) | byte-identical | **`-2010` rejected** |
> | order list, terminated (`ALL_DONE`) | byte-identical | **accepted**, new `orderListId`, new leg `orderId`s, leg `clientOrderId`s honoured byte-for-byte |
>
> **Why the earlier reading was wrong is worth more than the correction.** Every
> arm of the first probe ran against a *terminated* original, so the arm set could
> not distinguish *ID release* from *absence of deduplication* — both hypotheses
> predict the same result in every state it sampled. The acceptances were correct
> observations of the wrong state; **the defect was in the design of the arm set,
> not in any measurement it made.** The single-order arm is what discriminated
> them, and it was not in the original design.
>
> **The re-place branch table, against the measurement:**
>
> | After a timed-out write | Re-place | Status |
> |---|---|---|
> | never placed | accepted | correct — nothing rested |
> | placed, `FOK`-expired, nothing rests | accepted | correct — this *is* the "nothing rests" branch |
> | placed and still live | **`-2010`** | the success signal, as designed |
> | placed, working leg **filled**, pendings live | pendings' IDs are still live, so a byte-identical re-place collides | **REASONED, NOT MEASURED** — needs a fill |
>
> **One deviation, marked.** Arm 10's working leg was `LIMIT`+**`GTC`**, not §3's
> `FOK`, because a `FOK` leg cannot rest and so cannot produce a live list without
> a fill. Uniqueness is not a property of `timeInForce`, so the result should
> generalise to a live `FOK` list — **INFERRED, NOT MEASURED.**

> **THE TABLE'S FIRST ROW IS NO LONGER REACHED, BY THE PROJECT OWNER'S RULING
> AT M5f. The table is not wrong and is not withdrawn** -- every row still
> describes what the venue does. What changed is that the caller no longer
> takes the "never placed" branch's action.
>
> **The ruling, verbatim: "Fail-closed on UNRESOLVED states for Ruling 2."** On
> a verdict this repository calls `UNRESOLVED` -- the query failed, so which row
> applies is unknown -- the caller keeps its pending record and **re-places
> nothing**, retrying the query on the next candle-handler invocation. It is
> annotated into `CLAUDE.md`'s timed-out-write rule at `107178f`, and the code
> is `OrderExecutor.__call__` in `src/trading_bot/execution/executor.py`
> (`8ca878e`, corrected at `0c10a38`).
>
> **THE GROUNDS ARE THIS TABLE'S OWN FOURTH ROW.** It is the only row marked
> **REASONED, NOT MEASURED**, it needs a fill to settle, and it is the row in
> which a re-place opens a **second, unprotected entry**. A recovery path cannot
> know which row it is in -- that ambiguity is why it exists -- so the ruling
> takes the reading whose wrong answer is reversible: a refused recovery costs a
> missed trade, a duplicated entry cannot be un-placed.
>
> **What this does NOT touch.** Rows two and three are implemented rather than
> merely intact: a resolution finding the list TERMINATED records no position,
> and one finding it LIVE records the position it proves exists. The `-2010`
> success signal and arm 10's measurement stand exactly as written. Only the
> caller's behaviour when it cannot tell which row applies has changed.

## 9. Costs

Order-list domain type; `ProtectionState`; three error classes; a reconciler.
`Portfolio` gains open/close methods it lacks entirely. `free_quote` needs `ge=0`.
`SymbolInfo` must model `PERCENT_PRICE_BY_SIDE`; a band violation is a REFUSAL
VALUE, not a raise, with a configured margin since the average moves between bar
close and submission. **That margin is deliberately unspecified here** — it has a
real trade-off and belongs to M5 with a named default and a stated rationale.

**`max_entry_slippage` is a new config field.** It belongs in `RiskConfig`, typed
`Decimal` because it multiplies a price (the money rule: a config field becomes
`Decimal` at the milestone that first multiplies it by money), constrained `gt=0`,
and shipped with a named default.

**`TradeIntent.price` changes meaning, and its docstring becomes FALSE.** It reads
*"the signal's price, which is the closed candle's close"*; under §4 it is
`entry_limit`, a derived price, and must be corrected.
`TradeIntent._check_invariants` enforces `levels.entry_price == self.price`, so
`compute_protective_levels` must be called with `entry_limit` as well — a change
to `evaluate`'s composed path, not only to a docstring. The `binding_price` fix
already landed stays correct unchanged: `min(price, stop_price)` still selects the
lowest leg price, with `price` now meaning `entry_limit`.

> **SUPERSEDED in its mechanism, not in its consequence — see M5-0's D3.**
> `TradeIntent` does not change what a field *means*; it **splits** into
> `EntryIntent` and `ExitIntent`. A `CLOSE` dispatches `MARKET` and carries no
> limit price at all, so one field cannot serve both, and a field whose meaning
> depends on `side` makes `_check_invariants` conditional on `side` — an invariant
> somebody eventually inverts.
>
> Everything above about `entry_limit` being the reference for the protective
> levels *and* for sizing stands unchanged, and is now a property of the type:
> `EntryIntent` enforces `levels.entry_price == entry_limit`, plus
> `entry_limit >= reference_price`, which makes §4's slippage **direction**
> unfakeable independently of whatever bound `max_entry_slippage` carries in
> config. `CLAUDE.md` holds the full field sets and invariants.

`backtesting/` must model intrabar triggering (§1).

**Q-D is folded in as a decision:** the port widens to expose the composed path,
and `RiskAssessment` moves with it. Implemented in **M5b**, alongside the entry
reference and the intent split, because `EntryIntent`'s invariants and the widened
port move together.

## 10. Unmeasured / open

- `MARKET_LOT_SIZE` and `NOTIONAL.applyMinToMarket` on a **triggered** stop-type
  order — UNRESOLVED; neither the library nor `exchangeInfo` states it. Mainnet
  BTCUSDT/ETHUSDT report zeroed min/step so conservatism is free there; `maxQty` is
  live and parsed-but-unread. **Both protective legs are stop-markets, so if it
  binds it binds on everything.**
- `_enforce` is blind to notional for MARKET and stop-market orders — pinned to M5.
- Pending-leg partial fill — requires an irreversible fill. `FOK` removes it from
  the entry path only.
- The `PENDING_NEW` → `NEW` transition on a real fill — DOCUMENTED, never measured.

  > **STILL UNMEASURED, and one adjacent thing now IS.** `get_open_orders`
  > returns pending protective legs **in `PENDING_NEW`** on a live list
  > (MEASURED at M5d) -- so a recovery path asking "does anything rest" can see
  > protection that has not activated, and need not infer it from the working
  > leg. What was measured is `PENDING_NEW` **before** any fill; the transition
  > this line names is the **post-fill** case and still needs one. The two are
  > one sentence apart and must not be conflated.
- `TAKE_PROFIT`'s algo-slot cost — inferred, not measured.
- `LIMIT_MAKER`-at-activation blast radius — UNMEASURED; the reason it was not
  chosen.
- **The 36-character client-order-ID limit is ASSUMED, not measured.** It was
  asserted in the Step 1 probe report and never verified. The scheme reaches it at
  generation >= 100 on a 12-character symbol
  (`tb1-` + 12 + 13 + 3 separators + 3 + 1 = 36). One deliberately over-long
  rejected request would settle it, free. Not a Q-C blocker.

  > **THE ARITHMETIC ASSUMES A ONE-CHARACTER LEG AND OVERSTATES THE HEADROOM.**
  > That trailing `1` is the leg code. Two of the three measured codes -- `SL`
  > and `TP` -- are **two** characters, so on a twelve-character symbol those
  > legs reach **37** and are REJECTED at generation >= 100, where this line
  > says the scheme merely "reaches" the limit. The error is in the
  > **overstating** direction: it claims headroom that is not there.
  >
  > Not a live defect. On the shipped symbols (7 characters) the worst case is
  > 31 against 36, and `exchange/ids.py` took the **binding** case -- a
  > generation ceiling of 99, derived from the 2-character leg -- so the
  > overstatement cannot reach the generator. MEASURED, every component read
  > from the tree.

  > **NOW MEASURED at M5c, and the assumed figure was right.** 36 characters is
  > accepted; 37 is rejected with HTTP **400**, code **`-1100`**, and the venue
  > states its own rule verbatim:
  >
  > ```
  > Illegal characters found in parameter 'workingClientOrderId'; legal range is '^[a-zA-Z0-9-_]{1,36}$'.
  > ```
  >
  > *Provenance: `POST /api/v3/orderList/otoco`, TESTNET, BTCUSDT, 2026-08-12,
  > incrementing the working leg's ID length upward from 36 to the first
  > rejection.*
  >
  > Two things the measurement adds beyond the number. The regex constrains the
  > **character set** as well — `[a-zA-Z0-9-_]` — which §6's scheme satisfies,
  > since it uses only alphanumerics and `-`. And the **sharp edge**: a **LENGTH**
  > violation is reported as *"Illegal characters found"*, so anyone debugging a
  > too-long ID reads the message and goes looking for a bad character. The regex
  > in the message is the only thing that discloses the real cause, and it
  > discloses both rules at once.
