# Current milestone — Phase 5 M4a: composition root and the observable intent stream

**Status:** not started
**Baseline to confirm first:** `python scripts/check.py` → 569 passed
(566 unit + 3 integration) · ruff 0 · ruff format clean over 82 files · mypy 0
across 58 files. Run it **bare** — never piped.

Scope is the **composition root**: the component that owns a `Portfolio`, primes
the per-pair exchange filters a `RiskManager` needs, attaches the risk decision
to `TradingEngine.on_signal`, and emits one structured log line per outcome.

**Nothing is dispatched.** The executor at the end of the chain writes a log line
and returns. Order placement is M5.

The decision path has never run against live market data — only against scripted
fakes. Wiring it behind a log-only executor makes it observable on Testnet for
days at zero risk, and turns M5's hardest questions (what does `Portfolio` look
like after eight hours? how often does the sub-tick stop gate actually fire?)
into things there is *data* about.

Read `CLAUDE.md` for the rules and locked decisions, and `docs/PHASE_HISTORY.md`
for why M1–M3 and the hardening pass are shaped the way they are.

---

## Contracts to verify empirically before designing

Do not take these from this document — confirm them in the code.

- `engine/modes.py` — currently a docstring-only stub. Its docstring already
  describes this milestone's job: *"Assembles the right set of collaborators …
  for the active TradingMode, so `live_engine` stays mode-agnostic."*
- `TradingEngine.create` in `engine/live_engine.py` — **it builds the provider
  itself.** This is the open fork below; read it before designing around it.
- `TradingEngine.on_signal` and `_emit` — handlers run in registration order and
  are isolated. Confirm what `_emit` does with an exception, because the error
  path depends on it.
- `RiskManager.__init__` in `risk/manager.py` — four keyword-only collaborators:
  `config`, `provider`, `pairs: Mapping[str, PairContext]`, `clock`. `pairs` is
  **not** `Optional` and is copied into a `dict`; nothing refreshes it after
  construction.
- `RiskAssessment` / `TradeIntent` in `risk/manager.py` — every field available
  to log, and which components are `None` on which refusal.
- `RiskDecision.rule` — reachable as `assessment.decision.rule`, **two levels
  down**, and `decision` is `None` for refusals that never reach `approve`.
- `Portfolio` in `core/portfolio.py` — `record_realised_pnl`, `start_cooldown`,
  `positions`, `free_quote`. M3 defined these and calls **none** of them.
- `BaseExchangeClient.get_symbol_info` in `exchange/base.py` — a coroutine, and
  it memoises. This is why filters are primed once at startup.
- `utils/logger.py` — `PlainFormatter`, `JsonFormatter` and `surplus_fields`.
  Structured fields now reach **both** sinks; confirm before designing a schema.
- `main.py` — the current wiring, which registers no signal handler at all.

---

## The config conversion M4a owns

**None — confirm rather than assume.** A log-only executor performs no money
arithmetic. If the design proves otherwise, convert the field in its own commit
under the amended rule (*multiplies **or compares***).

---

## The open fork — settle this first

**`TradingEngine.create` owns provider construction, and the root needs the same
provider instance for `RiskManager`.** Two ways, and they lead to different
shapes:

1. **Take it from the engine post-construction** — build the engine as today,
   then read its provider back out. Smallest change; requires exposing the
   provider, and leaves construction order implicit.
2. **The root builds the provider and injects it** — `TradingEngine.create`
   already accepts an optional `provider`, so this uses an existing seam. The
   root then owns the object graph explicitly, which is what a composition root
   is *for*, at the cost of moving startup sequencing out of the engine.

Nothing else in M4a can be designed until this is chosen. Decide it, record the
reasoning, and do not let it be settled implicitly by whichever code is written
first.

---

## Design questions to resolve before writing code

**1. Named collaborators, not anonymous handlers.**

`RiskManager` and the log-only executor are **named collaborators of the root**,
composed into **one chained handler** registered on `on_signal` — not two
independent registrations. The chain catches **per collaborator** and emits a
structured error line naming which one failed, so a failure is attributable
rather than merely contained. `_emit`'s isolation is the outer net, not the
mechanism.

**2. Boot-time `PairContext` priming, and failing fast.**

Filters come from `get_symbol_info` per enabled pair at startup. **This is M4a's
only I/O**, and it stays in the root: `RiskManager` remains I/O-free, which is
what keeps it testable with a plain dict.

**Refuse to start on an unprimeable symbol.** One bad pair out of five is a
configuration error, and a bot that silently trades four of them is worse than
one that will not start. Note the "fails at boot" property M3 designed for is
worth nothing if the failure is a warning nobody reads.

**3. The log schema.**

One fixed field set with an **`event=` discriminator** — `event=risk_refused`,
`event=intent_dispatched`. Absent fields are **absent, not null**: a field that
is missing means "not reached", which is information, and null-padding destroys
it.

`rule_fired` is **nullable and legitimately absent**. `RiskAssessment.decision`
is `None` for every refusal that never reaches `approve` — unknown pair, no
signal price, non-BUY action — so a schema requiring it would be wrong for a
whole class of outcomes.

**Open question, not yet decided:** whether an eighth field, `stage`, should name
where evaluation stopped (`preconditions` / `limits` / `atr` / `levels` /
`sizing` / `affordability`). Today that is inferable only from which component is
non-`None`, which is an awkward thing to ask of a log consumer. Decide it as part
of the schema, not after.

**4. What "observable" has to mean.**

Structured, fixed-field, machine-parseable — the Testnet output must be
analysable after the fact, ideally loadable into a frame. Free text does not
count. Note `logging.file.json` defaults to **false**, so the JSON sink is off
out of the box; the plain sink now carries the same fields as logfmt, but the
run's configuration is a deliberate choice, not a default to inherit.

---

## Scope constraints

- The log-only executor sits at the same seam the real executor will occupy and
  consumes `TradeIntent` **unmodified**. If it needs something the intent does
  not carry, that is a finding about `TradeIntent`, not a licence to reach around
  the seam.
- Do not touch `risk/` behaviour. A wanted change there is a finding to report.
- **Q-A (per-handler failure counter) is deferred to M4b**, deliberately. A
  consecutive-failure threshold should be set from soak data, not guessed before
  the path has ever run. M4a produces exactly the data that sets it.

---

## Tests

Hermetic, no network, no real time. Cover:

- the root builds a manager whose `pairs` covers every enabled pair
- an unprimeable symbol refuses startup, with the reason visible
- the chained handler catches per collaborator and names the failing one
- the log line carries every fixed field for an approved intent **and** for a
  refusal, asserted on the structured record rather than a message string
- a refusal with no `decision` omits `rule_fired` rather than nulling it
- an exit intent (`levels is None`) logs coherently
- no money value built from a float — structural, via the `Money` guard

---

## Definition of done

- `python scripts/check.py` green, run **bare**; test count stated with its
  condition (see below)
- `mypy` zero; `ruff check` and `ruff format --check` zero
- No `type: ignore` added to `src/`
- Design presented and confirmed **before** implementation
- **A Testnet run of at least one full session, with the structured intent log
  retained and read.** This milestone's deliverable is observability; a green
  suite does not demonstrate it.

⚠️ **Retention will bite this run.** At `max_bytes` 10 MB and `backup_count` 5,
ten pairs on 1m bars gives roughly **4–12 days** before rotation, and the
**oldest file is discarded first** — which is where warmup behaviour lives, i.e.
exactly what a first observation run wants to inspect. Raise `backup_count`, or
copy the log aside, before starting a long run.

---

## Open items — not scoped to this milestone

- **PAPER mode reaches Binance *mainnet* with empty credentials. Contained by
  M4a, not fixed.** This contradicts "Testnet is the default everywhere", so it
  is recorded rather than left in the code to be rediscovered.

  Two lines make it happen, and each is defensible alone:
  `config/settings.py:83` raises only when `mode.is_live_connection`, so PAPER
  and BACKTEST get `("", "")` back instead of an error; `binance_client.py:112`
  sets `testnet = settings.mode is TradingMode.TESTNET`, which is `False` for
  PAPER — so the adapter points at `api.binance.com`. `main.py:129` gates its
  own credential check on the same property, so nothing upstream catches it
  either. Before M4a, `run --mode paper` therefore opened an *unauthenticated
  mainnet* connection and streamed live production prices. Read-only, no order
  path — but it is a live-environment connection that the mode name says should
  not exist.

  **M4a contains it**: `live_system` refuses a non-`is_live_connection` mode as
  its very first statement, before any client is constructed, so the CLI now
  exits 1 with a message naming the missing simulator. The underlying defect is
  untouched — anything that builds a `BinanceClient` outside the composition
  root still gets a mainnet client in PAPER mode.

  The real fix is a decision, not a patch: either PAPER resolves `testnet=True`
  (live prices from Testnet, which is what "live prices, no orders sent" almost
  certainly meant), or `binance_credentials()` refuses every mode that
  constructs a client. Belongs with `paper/simulator.py`, which is the milestone
  that gives PAPER a composition root of its own.

- ~~A flaky integration test.~~ **Closed — and worth keeping as a worked
  example of a test asserting more than its contract promised.**

  `test_testnet_provider_seeds_history_and_extends_it_live` asserted
  `len(extended) == len(seeded) + 1`: that the first live candle is always a
  *new* bar. It is not. When the REST seed's last bar is the same bar the
  WebSocket then closes, `BufferedMarketDataProvider._append` **replaces it in
  place** (`market_data.py:378`, *"same bar re-delivered, possibly corrected"*)
  and the frame grows by **zero**. Which path occurs is a race with the minute
  boundary.

  The production code was correct throughout — replace-on-equal-`open_time` is a
  locked decision and is what makes a corrected bar safe after a reconnect.
  The test now asserts the invariant common to both paths: growth ∈ {0, 1}, last
  index equals `live.open_time`, index monotonic and unique; on the replace path
  the final row must have *changed* and match the delivered candle; on the append
  path the seeded rows must be undisturbed.

  The changed-row assertion is the load-bearing one: "grew by 0" is equally
  satisfied by a provider that **dropped** the bar, which is a real failure
  wearing the same shape. Both branches and three illegal shapes (drop, grow-by-2,
  wrong final index) were exercised against a fake before trusting a live run.

  **Two rules paid for themselves here.** It went unidentified for several
  sessions because the run that first hit it was piped through `tail`, which
  discarded pytest's summary; it was named the moment a run was made **bare**.
  And no retry decorator was ever added — retrying would have hidden a genuine
  gap between a test's assumption and a documented contract rather than exposing
  it.
- **`make check` has never been executed through `make` on this machine.** `make`
  is not installed. The four delegating recipes are tab-indented (verified) and
  the gate itself no longer depends on `make`, but `$(PYTHON)` expansion and
  recipe execution remain unexercised. Needs one run where `make` exists.
- **`make cov` and `make format` do not honour `$(PYTHON)`.** They call bare
  `pytest` / `ruff`, so `make PYTHON=... cov` silently uses a different
  interpreter than `make PYTHON=... check` would. Outside the gate, so left
  alone; inconsistent, so recorded.
- **The `logging.file.json` flag controls console *and* file together.** There is
  no way to have a pretty console and a JSON file. ~3 lines in
  `_console_handler` to separate; deliberately out of scope so far.
- **Nothing enforces the documented counts.** They are updated by hand in two
  files and have drifted within a single session more than once. Worth a check
  that reads them from a live run, but it must not become a gate that fails for
  a reason unrelated to the code.
- **Transitive dependencies still float.** The direct layer is pinned exactly;
  `websockets`/`aiohttp` under `python-binance` and friends resolve freely.
  `pydantic` pins `pydantic-core==2.46.4` exactly, so the `Money` guard's engine
  *is* locked; `pandas` constrains `numpy` only as `>=1.26.0`, so the float64
  leak path is pinned by **our** direct line and would be exposed if that line
  were relaxed. Proper fix is `pip-compile` with hashes over a `requirements.in`
  — deferred because it changes the install procedure for every contributor and
  the Docker build, and wants its own decision.

---

## After this: Phase 5 M4b, then M5

**M4b** — the per-handler failure counter (Q-A), thresholds set from M4a's soak
data. Automatic removal of a failing handler stays **rejected**: disabling a
broken executor converts "orders are failing" into "orders are not being
attempted" while positions are open.

**M5** — order dispatch. `OrderExecutor` over `BinanceClient.create_order`, the
unprotected window between an entry fill and its stop, idempotency via
`client_order_id`, order-status tracking, and `Portfolio` write-back. Q-B
(escalation policy) and Q-C (which protective levels rest at the exchange, and
how they reconcile with the client-side view after a restart) are settled at the
start of that milestone, not during it.
