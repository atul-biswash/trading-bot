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
| TP only | refused at config load | — |
| neither | single order, `LIMIT` + `FOK` | `create_order` |

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

**Cost, stated plainly:** risk-per-trade is a PRE-SLIPPAGE guarantee and the
take-profit is a PRE-SLIPPAGE target. Neither is exact.

## 4. Entry mechanics

`entry_limit = round_to_tick(close x (1 + max_entry_slippage), ROUND_FLOOR)` — a
marketable limit. Slippage is bounded by an operator-chosen number, not by the book.

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

`stop_loss` / `take_profit` are redefined as requested levels, **immutable once
set**. What rests is queried, never cached. `trailing_stop` / `highest_price` /
`lowest_price` retained pending the trailing milestone, and `trailing_stop` is
explicitly **outside** the immutability rule — it is rewritten every bar by design.

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

Prefix `tb1-` is required because `get_open_orders` returns **every** order on the
symbol, ours and otherwise, and only a prefix distinguishes them. Note the library
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

**Shape is identified by leg count or by our own IDs.** `contingencyType` reads
`"OTO"` on every payload of both shapes and never once `"OTOCO"` (MEASURED).

**The placement response is not a source of truth for list identity.**
`listClientOrderId` is deterministically `null` there when a list terminates in the
same call, while the leg IDs in that same payload are correct (MEASURED, T1).

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

## 8. Errors

`translate_binance_error` must match **message text, not code**. `-2010 'Duplicate
order sent.'` is a SUCCESS SIGNAL under deterministic IDs, not an error. `-2011` →
benign `OrderNotFoundError` on cancel paths; note `cancel_all_open_orders` raises
`-2011` on an already-clear book, so routine emptiness arrives as an exception.
Filter failures → `FilterRejectedError` carrying the parsed filter name. `-1106` →
programming error, raise loudly. `-1158` / `-1159` / `-1128` → contract errors.

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
- `TAKE_PROFIT`'s algo-slot cost — inferred, not measured.
- `LIMIT_MAKER`-at-activation blast radius — UNMEASURED; the reason it was not
  chosen.
- **The 36-character client-order-ID limit is ASSUMED, not measured.** It was
  asserted in the Step 1 probe report and never verified. The scheme reaches it at
  generation >= 100 on a 12-character symbol
  (`tb1-` + 12 + 13 + 3 separators + 3 + 1 = 36). One deliberately over-long
  rejected request would settle it, free. Not a Q-C blocker.
