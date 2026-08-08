# Project knowledge — orientation for a reviewer without repository access

This file exists for one situation: an architecture-review conversation with an
assistant that **cannot read the repository**. It carries the context needed to
reason about the design, and the exchange behaviour a reviewer could not derive
from the code even with access, because it lives in a remote venue rather than in
the tree.

---

## Standing warning — read before relying on anything here

**Nothing audits this file.** It is outside every gate, grep and review that
touches the code. A previous version of this material referenced a
`MILESTONE_WORKFLOW.md` that existed nowhere in the tree, for months, and nothing
in the repository could have detected that.

**There are two documents with this name, and this is the newer one.** This file is
tracked in the repository and is the *source* of the material pasted into a review
conversation. A much longer predecessor exists outside the repository; it restated
`CLAUDE.md` at length — exactly what the precedence rule below forbids — and it is
superseded. The discriminator is easy: **the old one numbers its sections, this one
does not.** A rule found only in the numbered version has not necessarily been
adopted anywhere; check it against `CLAUDE.md` before relying on it. That has
already caught one rule which governed real behaviour and lived nowhere else.

**Precedence, when sources disagree:**

1. **The code wins over `CLAUDE.md`.**
2. **`CLAUDE.md` wins over this file.**

So this file **points at** `CLAUDE.md` and does not restate it. Anything restated
here eventually contradicts the code, and the contradiction is invisible from
inside the repository.

It is also written to avoid anything that moves at a milestone boundary — no test
counts, no file counts, no current milestone, no commit hashes, no line-number
references. If you find one of those here, it is a bug in this file.

**If the reviewer needs a fact about the current state — what is built, what the
gate reports, what is being worked on — ask for `CLAUDE.md` and
`docs/NEXT_MILESTONE.md` to be pasted.** Do not infer it from here.

---

## What the software is

A single-account, bar-close automated trading bot for **Binance Spot**, in Python,
written to be treated as software that will eventually manage real money.
Correctness and safety are prioritised over speed of development, and every design
decision is recorded with its reasoning rather than only its outcome.

Deliberate non-goals, because they shape everything: **spot only, long only** — no
futures, margin, leverage or shorting; **no high-frequency trading** — it reacts at
bar close and nowhere else; **one position per symbol**, no pyramiding; one
strategy per pair.

## Where the documents live and what each is for

- **`CLAUDE.md`** — the authority. Architecture, the money rule, locked decisions,
  the quality gate, testing style, and the docs-rotation workflow. Loaded into
  every working session, which is why the workflow lives there rather than in a
  separate file somebody has to remember to read.
- **`docs/NEXT_MILESTONE.md`** — the current task, and the single home for live
  open items.
- **`docs/PHASE_HISTORY.md`** — append-only build log. What each milestone decided
  and *why*, including alternatives rejected, written in the tense it was decided.
  Never restates current state.
- **`docs/QC_PROTECTIVE_ORDERS.md`** — the protective-order contract: where the
  protective levels rest, the placement shapes, the identity scheme, and what
  reconciliation compares.
- **`docs/QB_ESCALATION.md`** — what `CRITICAL` means operationally, its binding
  sites, and which of them can clear on their own.
- **`docs/M5_NUMBERS.md`** — the safety numbers, each with what it protects
  against, what a wrong value costs in each direction, and its measurement status.
  A number here is never quoted without that status.

## Architecture, in the shape a reviewer needs

Clean architecture with dependencies pointing inward. `core/` holds domain models
and abstract ports; outer layers implement them. Concretely: `core` defines an
`ExchangeClient` port, the Binance adapter implements it, all exchange JSON is
converted by pure mapper functions, and every call routes through one
retry-and-error-translation helper so callers only ever see domain exceptions.

Four properties are worth knowing because most review questions land on them:

**Money is `Decimal` in the domain, never `float`** — enforced by a validator, not
by convention. There is exactly one `Decimal`→`float` boundary, in the data layer,
because indicator maths runs on NumPy. Full reasoning is in `CLAUDE.md`; it is the
single most load-bearing invariant in the codebase.

**A refusal is a value, not an exception.** The decision path runs on every bar,
and routine market states — too small to trade, daily loss cap reached, no
placeable stop this bar — are returned as frozen objects carrying their reason and
the stage they stopped at. Raising on those would print a traceback every bar
forever. Genuine contract violations still raise.

**Strategies are edge-triggered and stateless.** A signal fires on the transition
bar and is silent while the condition persists; state is recomputed from the
buffer rather than held on the strategy object, so behaviour is identical after a
restart or a redelivered bar.

**Order dispatch runs inline on the candle pipeline, under a budget.** Signal
handlers are awaited sequentially from the market-data callback, so whatever they
do is charged directly to the feed. The governing rule is not "no I/O" but *no
latency we do not bound ourselves*: a per-call deadline distinct from the general
request timeout, a per-invocation budget, and a reserved floor that reconciliation
cannot be starved of — because between skipping a placement and skipping a
reconciliation, the placement is the safe one to skip. A bounded queue with its own
consumer was considered and rejected: it makes the portfolio writable from a task
that is not the one reading it, and the first bug that buys is a duplicate entry.
`CLAUDE.md` carries the reasoning and the numbers live in `docs/M5_NUMBERS.md`.

---

## Binance Spot exchange behaviour — measured, not documented

This section is the main reason the file exists. These findings come from probes
against Binance Spot Testnet with a live account. **A reviewer cannot derive any
of it from reading the code**, and several items contradict what the client
library's own docstrings imply.

### Order-list shapes: OTO and OTOCO

Entry-plus-protection can be placed atomically as an **order list**: a *working*
leg (the entry) and one or two *pending* legs (the protection) that sit inactive
until the working leg fills.

- **OTOCO** — working leg plus two pending legs, above and below. Its pending
  parameters use `pendingAbove*` and `pendingBelow*` prefixes.
- **OTO** — working leg plus a single pending leg. Its pending parameters use the
  **plain `pending*` prefix**, not the above/below split. The two shapes do not
  share a pending-parameter naming convention.

Both are placed through endpoints the client library wraps as bare passthrough —
**every wrapped method has the signature `(self, **params)`**, so parameter names
are recoverable only from documentation or from the exchange's own error messages,
never from the function signature. The library performs no validation whatsoever;
an unknown key is forwarded and fails at the venue.

**Order types are restricted per slot, and the restrictions differ.** A `MARKET`
order is refused as a working type. A plain `LIMIT` is refused in the
pending-above slot. The two refusals come back as *different* error codes with
different wording, one naming OTO and one naming OCO — the pending pair is
validated as an OCO even inside an OTOCO.

**Fields are not merely optional — several are forbidden.** A stop-market pending
leg rejects a limit price and a time-in-force if they are sent, rather than
ignoring them. So the correct request is type-dependent in both directions: some
fields must be present, others must be absent, and sending a superfluous one is an
error.

### Read-back does not round-trip the request

**The single most important item for anyone designing reconciliation.**

- A leg reports a `timeInForce` that it would have *rejected* if you had sent one.
- A stop-market leg reports `price` as zero rather than omitting it.
- Prices round-trip **numerically but not as strings** — a value sent as
  `"40917.83"` returns as `"40917.83000000"`. Any comparison must be
  decimal-normalised; a string comparison manufactures a divergence on every
  cycle.

So a reconciler that diffs a read-back against the request it sent will report
constant, spurious divergence. Only fields that genuinely round-trip may be
compared, and the set is smaller than it looks.

**The placement response and a subsequent query disagree** on at least one field:
a list's caller-supplied identifier comes back `null` in the placement response
when the list terminates within the same call, while a query returns it correctly.
The per-leg identifiers in that *same* placement payload are correct. This is
deterministic, not a race — which is the argument for recording the placement
response and the read-back as separate observations rather than treating either as
the truth.

### The response cannot tell you which shape you placed

`contingencyType` reads `"OTO"` for **both** shapes and never reads `"OTOCO"`.
There is no field naming the shape. Identification must come from the **leg count**
or from **caller-supplied client order IDs**, both of which are reliable.

Caller-supplied identifiers are honoured byte-for-byte on both shapes, for the
list and for every leg — which is what makes a deterministic, derived identifier
scheme viable. Note the asymmetry: the plain single-order endpoint auto-injects a
library tag when no identifier is supplied, while the order-list endpoints inject
nothing.

### Error codes are overloaded; only the message discriminates

**This is a correctness trap, not a nuisance.** The same numeric code carries
several unrelated meanings, and some of them are *successes*:

- One code covers "duplicate order", "filter failure" and "insufficient balance".
  Under a deterministic client-order-ID scheme, **"duplicate order" is a success
  signal** — it means the order already landed. Treating it as an error by code
  reports failure on success.
- Another code covers "unknown order", "unknown order list" and is *also* what a
  cancel-everything call returns against an already-empty book. Routine emptiness
  arrives as an exception.
- A "parameter sent when not required" code always names the offending field, and
  is a programming error rather than a market state.

Any translation layer must match **message text**, not code. Matching on code
alone will conflate a success with a hard failure.

### Filters are evaluated at submission, and a violation kills the whole list

Price-band and notional filters are applied when the request is *submitted*, not
when a pending leg later activates. A single out-of-band pending price refuses the
**entire order list** — nothing is created, not even the valid legs.

Two consequences a reviewer should hold onto:

- **A "never fills" placeholder leg is impossible.** The price band is bounded on
  both sides, so there is no price far enough away to be inert and still legal.
  Shape branching cannot be collapsed by padding a missing leg.
- **Notional is evaluated per leg, at that leg's own price.** A protective stop
  resting below the entry carries a *smaller* notional than the entry does, so a
  quantity that satisfies the minimum at the entry price can be rejected at the
  stop. Sizing must clear the minimum at the **lowest** price the trade will
  carry. This was found by being rejected, not by reading documentation.

### Expiry has a machine-readable cause

Legs carry a field naming *why* they expired, distinguishing "the entry could not
fill" from "the protection died because the entry did". Present on both shapes. It
is more reliable than inferring cause from leg ordering or status alone.

### What remains unmeasured, and why it matters

Every probe was constructed so that **nothing could fill** — a deliberate safety
constraint, since a fill on a live venue is irreversible. The cost is a known
blind spot:

- The entire **fill path** is unmeasured. The transition of pending legs from
  inactive to live on a real fill is documented by the exchange but never
  observed here.
- **Partial fills** of a protective leg are unmeasured.
- Whether market-order-specific filters bind an order that *becomes* a market
  order on trigger is **stated nowhere** — not by the exchange response, not by the
  client library. It is genuinely unresolved rather than merely unread, and it
  matters because protective legs are stop-market orders.

**Treat any claim about the fill path as documented-or-assumed, never measured.**
The distinction is maintained deliberately throughout the design notes, and a
reviewer should hold the design to it.

---

## How to review this project usefully

- **Ask for the file rather than assuming its contents.** `CLAUDE.md` and the docs
  under `docs/` are the source of truth and can be pasted into the conversation.
- **Distinguish measured from assumed.** The project marks findings MEASURED,
  DOCUMENTED or UNMEASURED, and the marks are load-bearing. Safety *numbers* carry
  a further status, **BOUNDED** — a measurement exists and constrains what the
  value must clear, but does not derive it, so the value itself remains a policy
  choice. That is a different claim from either "measured" or "guessed", and
  collapsing it into one of them loses the thing worth knowing. A design resting on
  an unmeasured claim is not automatically wrong, but it should say so.
- **An instrument is validated against a known answer before its output is
  trusted.** A measurement in this project was once accepted, argued from, and
  written into `CLAUDE.md` before proving to be an artefact of a broken text
  matcher — one whose signature was visible in the reported figures and went
  unremarked by both author and reviewer. The discipline adopted afterwards is to
  run any instrument against a case whose answer is already known, and to treat two
  instruments disagreeing as a stop condition rather than something to explain
  around. A reviewer shown a measurement is entitled to ask how the instrument was
  checked.
- **Challenge locked decisions on evidence, not taste.** `CLAUDE.md` carries a list
  of decisions marked not to be re-litigated without an explicit reason. They each
  record why; a reviewer disagreeing should engage with that reasoning.
- **The most valuable output is a point neither side had considered.** Design work
  on this project has been run as two independent proposals compared against each
  other, precisely because a single proposal can only be checked for internal
  consistency.
