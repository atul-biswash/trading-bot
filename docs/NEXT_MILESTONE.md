# Current milestone — Phase 5 M4: composition root and the observable intent path

**Status:** not started
**Baseline to confirm first:** 517 passed (514 unit + 3 integration) · mypy 0 · ruff 0

Scope is the **composition root**: the component that owns a `Portfolio`, primes
the `Mapping[str, PairContext]` a `RiskManager` needs, attaches
`RiskManager.evaluate` to `TradingEngine.on_signal`, and logs every resulting
`TradeIntent` in a structured, analysable form.

**Nothing is dispatched.** The executor at the end of this chain writes a log
line and returns. Order placement is M5.

This milestone exists because it was split out of execution deliberately. The
whole decision path — sizing, the ATR gate, the protective levels, the limits —
has never once run against live market data; it has only ever run against
scripted fakes. Wiring it behind a log-only executor makes it observable on
Testnet for days at zero risk, and turns M5's hardest questions (what does
`Portfolio` look like after eight hours? how often does the sub-tick stop gate
actually fire?) into things you have *data* about instead of opinions.

It also exercises a property M3 designed for but never proved: an unknown symbol
must fail at **boot**, when the filters are primed, rather than on the first
signal hours later.

Read `CLAUDE.md` for the rules and locked decisions, and `docs/PHASE_HISTORY.md`
for why M1–M3 are shaped the way they are.

---

## Contracts to verify empirically before designing

Do not take these from this document — confirm them in the code.

- `RiskManager.__init__` in `risk/manager.py` — exactly what must be supplied:
  `config`, `provider`, `pairs`, `clock`. Note it takes a `Mapping[str, PairContext]`
  and copies it; nothing refreshes it after construction.
- `PairContext` — `timeframe` **and** `symbol_info` together. Confirm there is no
  state in which one resolves and the other does not.
- `RiskAssessment` / `TradeIntent` in `risk/manager.py` — every field available to
  log, which components are populated on a refusal, and the fact that
  `levels is None` marks an exit intent.
- `RiskDecision.rule` and `RiskRule` in `core/models.py` / `core/enums.py` — the
  six rules `approve` can report, and which refusals instead carry only a string.
- `Portfolio` in `core/portfolio.py` — `record_realised_pnl`, `start_cooldown`,
  `positions`, `free_quote`. M3 defined these and calls **none** of them.
- `TradingEngine.create` and `TradingEngine.on_signal` in `engine/live_engine.py`
  — how the engine is built today, and where a handler attaches.
- `TradingEngine._emit` — read it. Confirm exactly what happens to a handler that
  raises, because Q-A depends on it and an earlier version of the docs got it
  backwards.
- `BinanceClient.get_symbol_info` in `exchange/binance_client.py` — it is a
  coroutine and it caches. This is why filters are primed at startup rather than
  fetched per signal.
- `main.py` — the current wiring, which registers **no** signal handler at all.
- `utils/logger.py` — what structured logging support already exists, before
  inventing any.

---

## The config conversion M4 owns

**None — confirm rather than assume.** Nothing on this path multiplies a config
field by money: the log-only executor performs no arithmetic. If the design
proves otherwise, convert the field in its own commit per the project rule.

---

## Design questions to resolve before writing code

**1. Where does the composition root live, and what owns the `Portfolio`?**

`main.py` currently builds an engine and runs it. Decide whether the wiring goes
there, into `engine/modes.py` (which exists as a stub for exactly this), or into
a new module. State who holds the single `Portfolio` instance for the process
lifetime, and how a second component would be prevented from making its own.

**2. Priming `PairContext`, and what happens when it fails.**

Filters come from `get_symbol_info` per enabled pair at startup. Decide the
failure policy: one bad symbol out of five — refuse to start, or start without
it? Say which, and make the reason visible. Note the "fails at boot" property is
worth nothing if the failure is a warning nobody reads.

**3. Q-A — handler-failure detection. Scoped INTO this milestone.**

`_emit` catches, logs and continues, with no counter and no state. Add a
**per-handler consecutive-failure counter** whose output is an **alert and a
state flag only**, mirroring the strategy quarantine so there is one mechanism
and one mental model. Any success resets it.

**Automatic removal of a failing handler from the chain is explicitly rejected.**
Disabling a broken executor converts "orders are failing" into "orders are not
being attempted" while positions are open — a silent downgrade from a loud
problem, which is the exact inversion this project keeps finding and fixing.
The counter reports; it does not amputate.

**4. Q-B — escalation policy. Deferred to M5, recorded here so it is not
rediscovered.**

A `HandlerFatalError` that `_emit` re-raises needs two things this milestone does
not have: a **named recipient** (nothing consumes alerts until notifications
exist) and a **defined shutdown sequence**. A bare re-raise out of `_emit`
propagates into the candle callback and tears down the feed — and the feed is
what drives `check_exit`, so the escalation would remove the exit path along with
the entry path.

"Suspend entries, keep exits" is the intended shape, but it must state **which
failure classes it covers**, given that `CLOSE` signals traverse the same handler
chain as `BUY` signals. A policy that cannot distinguish "the executor cannot
place entries" from "the executor cannot place anything" is not a policy.

**5. Q-C — resting protective orders vs the client-side view. Opens M5.**

Decide which protective levels are placed as **resting orders at the exchange**
and how they reconcile against `Position.stop_loss` / `trailing_stop`.

The client-side stop evaluated on bar close (`RiskManager.check_exit`) is correct
**as policy** — it refuses to claim a fill at a price the bar has already left —
and incomplete **as survival**: it requires a live process to act on it. A bot
that is not running has no stop at all. A resting exchange stop survives the
process; a trailing stop that moves every bar cannot practically rest. Decide the
split, and how the two views are reconciled after a restart, **before**
`execution/executor.py` is written — this constrains its shape more than any
other decision.

---

## Scope constraints

- **"Observable" means a structured log line per intent, with fixed fields:**
  `symbol`, `action`, `quantity`, `entry price`, `stop`, `take-profit`,
  `approved`, `rule fired`, `refusal reason`. Not free text. The Testnet output
  has to be analysable after the fact — grep-able, and ideally parseable into a
  frame — or the milestone has not delivered its only real deliverable.
- **The log-only executor sits at the same `on_signal` seam the real executor
  will occupy, and consumes `TradeIntent` unmodified.** It must not reach around
  the seam for data the real executor would not have. If it needs something the
  intent does not carry, that is a finding about `TradeIntent`, not a licence to
  bypass it.
- Do not touch `risk/` behaviour. If M4 wants a change there, that is a finding
  to report, not to implement.

---

## Tests

Hermetic unit tests, no network, no real time. Cover:

- the composition root builds a manager whose `pairs` covers every enabled pair
- a symbol whose `get_symbol_info` fails produces the chosen boot behaviour
- the log-only executor emits every fixed field, for an approved intent **and**
  for a refusal, asserted on the structured record rather than on a message string
- an exit intent (`levels is None`) logs coherently
- **a raising handler leaves the other handlers and the feed intact** — the
  isolation property `_emit` claims, asserted rather than assumed
- the per-handler failure counter increments on consecutive failures, resets on
  success, and raises its alert at the threshold without removing the handler
- no money value built from a float — structural, via the `Money` guard

---

## Definition of done

- `pytest` → all green, no previously passing test broken
- `mypy` → zero; `ruff check src tests` → zero
- No `type: ignore` added to `src/` (it is currently free of them)
- Design was presented and confirmed **before** implementation
- Committed as its own commit(s), with the reasoning in the body
- **A Testnet run of at least one full session, with the structured intent log
  retained and eyeballed.** This milestone's output is observability; a green
  test suite does not demonstrate it.

---

## Open items — not scoped to this milestone

Tracked here rather than in `PHASE_HISTORY.md`, which is a build log and must not
carry current state.

- **`Decimal`-vs-`float` comparison in decision paths.** `Decimal * float` raises
  `TypeError`, which is what makes the config conversion boundary
  self-announcing. `Decimal < float` does **not** raise — it compares against the
  binary expansion (`0.1` → `0.1000000000000000055…`), so the decision is made on
  a number that is not the one in `config.yaml`. The locked rule has been amended
  to "multiplies **or compares**" (see `CLAUDE.md`), because a field consumed only
  by comparison would otherwise never trigger its own conversion.

  A survey of `src/` found **no current instance** — every comparison in `risk/`
  is `Decimal`-vs-`Decimal` or `int`-vs-`int`, and every remaining `float` config
  field is either unused or float-to-float seconds in the websocket backoff. This
  is therefore a *forward* hazard, and its first victims are predictable:
  `BacktestConfig` and `PaperTradingConfig` carry `fee_percent` and
  `slippage_percent` as `float`, and both will be consumed against money by M5 and
  the backtest milestone. Convert them at that point, under the amended rule —
  and note that a threshold comparison now counts as the trigger, not just an
  arithmetic one.

  **This and the config-mutability decision are one finding from two
  directions.** `config/models.py` was left unguarded on assignment on the
  argument that config is never mutated after load — a convention, not something
  enforced. The comparison hole is exactly what would make violating that
  convention *silent*: a float assigned into a `Decimal` config field would flow
  into `move_pct < config.activation_percent` and decide a trailing stop without
  raising.

  The obvious hardening was checked before being recommended. **Answered for
  pydantic 2.13.4, and explicitly not as a contract:** assigning `0.1` to a plain
  `Decimal`-annotated field under `validate_assignment` coerces via the
  shortest-repr path, yielding `Decimal('0.1')` — not
  `Decimal('0.1000000000000000055…')`. So guarding the five config classes would
  be cheap hardening rather than the harmful "freeze binary noise into a
  canonical-looking Decimal" it might have been. Not implemented now.

  That answer is **observed runtime behaviour of an unpinned dependency**
  (`pydantic>=2.5.0`), which is the uncomfortable part. The `Money` guard itself
  rests on the same unpinned validation semantics. Note the asymmetry in how the
  two classes of dependency fail: a lint or type-checker bump breaks the build
  **loudly**, on a morning when nothing changed; a change in validation semantics
  breaks the **money domain quietly**, and no gate in this project would notice.

  Related, and not a separate finding: `risk/` raises 24 bare `ValueError`s for
  incoherent inputs and **nothing in `src/` catches any of them**. Their only
  containment is `_evaluate`'s handler, and only for the sites a strategy can
  reach — the risk rules run under a signal handler, where `_emit` swallows. That
  is the same silent-swallow shape as A1, and it is what Q-A and Q-B exist to
  address.

- **Declared-but-unused dependencies.** Runtime: `httpx`, `SQLAlchemy`,
  `aiosqlite`, `fastapi` and `uvicorn` are in `requirements.txt` and imported
  nowhere. Dev: `freezegun` and `respx` likewise — the tests inject a `Clock`
  rather than freezing time, and nothing calls `httpx` yet. Install weight and
  attack surface for software that manages money. All seven are deliberately
  left on floors rather than pinned, because pinning them would assert a
  commitment the project has not made; decide per package whether it is genuinely
  pending or should be dropped until a caller exists. (`python-dotenv` is a
  separate case: unimported but genuinely required, pulled in by
  `pydantic-settings` for `.env` loading.)

- **Transitive dependencies still float.** The direct layer is pinned exactly for
  everything `src/` imports or a gate executes; nothing pins what those packages
  in turn depend on. Two findings from checking the metadata, which point in
  opposite directions:

  - `pydantic 2.13.4` requires `pydantic-core==2.46.4` — **exact**. Pinning
    `pydantic` therefore genuinely pins the Rust engine that performs `Decimal`
    coercion, so the `Money` guard's verified behaviour is locked, not merely
    appearing to be.
  - `pandas 2.3.3` requires `numpy>=1.26.0` (Python ≥3.12) — a **floor with no
    ceiling**. `pandas` does not constrain `numpy` upward at all. The float64
    leak path is pinned only because `requirements.txt` pins `numpy` directly;
    that protection is ours and would vanish if the direct pin were ever relaxed
    on the assumption that `pandas` covers it.

  Everything else — `websockets` and `aiohttp` under `python-binance`, `anyio`
  under `httpx`, and so on — resolves freely. The proper fix is `pip-compile`
  with hashes over a `requirements.in`, producing a fully resolved lock.
  Deferred deliberately: it changes the install procedure for every contributor
  and the Docker build, so it wants its own decision rather than riding along in
  a hygiene commit.
- **`Signal.metadata` is a convention, not a constraint.** `CLAUDE.md` requires
  plain `int`/`float`/`str` values because the field gets persisted and NumPy
  scalars break serialisation, but the field is `dict[str, object]` and nothing
  enforces it. Strategies comply today by hand. Worth enforcing structurally
  before persistence exists, since that is when a violation starts costing
  something.
- **`ruff` and `mypy` versions are unpinned** (`ruff>=0.3.0`, `mypy>=1.8.0`). The
  gate reads an absolute zero, so a new release can turn the build red with no
  code change.
- **`scripts/` is outside every gate.** `ruff check`, `ruff format --check` and
  `mypy` are all scoped to `src`/`tests`, so `scripts/check_testnet.py` and
  `scripts/download_data.py` are neither linted, formatter-checked, nor
  type-checked. Unlike `tests/` being outside mypy — which is policy — this is an
  accident of the path list. It matters more than it looks: `check_testnet.py`
  connects to Binance with **real credentials** and is exempt from the strict
  typing the rest of the policy depends on. Bringing it in is its own commit,
  because it may surface real findings rather than being a no-op.

---

## After this: Phase 5 M5 — order dispatch

`OrderExecutor` over `BinanceClient.create_order`, protective-order placement
resolved per Q-C, the unprotected window between an entry fill and its stop,
idempotency via `client_order_id`, order-status tracking, and `Portfolio`
write-back. `_enforce` remains the independent last line of defence immediately
before dispatch. Q-B is settled at the start of that milestone, not during it.
