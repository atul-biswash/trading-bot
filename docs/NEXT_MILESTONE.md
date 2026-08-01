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

- **A flaky integration test — now IDENTIFIED, and the fix belongs to the test.**
  `tests/integration/test_market_data_integration.py::test_testnet_provider_seeds_history_and_extends_it_live`.
  It failed on 2026-08-01 (`1 failed / 516 passed`), was unidentifiable because
  that run had been piped through `tail`, and reproduced during the M4a docs
  rotation on a run made **bare** — which is how it was finally named.

  ```
  assert 120 == (120 + 1)
  ```

  **Cause.** The test asserts `len(extended) == len(seeded) + 1`, i.e. that the
  first live candle is always a *new* bar. It is not always: when the REST seed
  lands such that its final bar is the same bar the WebSocket then closes,
  `BufferedMarketDataProvider._append` **replaces it in place** rather than
  appending — `market_data.py:378`, *"same bar re-delivered, possibly
  corrected"*. The failure output shows exactly that: identical `open_time`
  (`11:10:00+00:00`), volume `0.04062` → `0.05837`.

  **The production code is correct**; replace-on-equal-`open_time` is a locked
  decision and is what makes a corrected bar safe after a reconnect. The test
  encodes an assumption the contract never made. The fix is to assert the
  *invariant* — the frame grew by 0 or 1, the last index equals `live.open_time`,
  the index stays monotonic and unique — rather than a fixed increment.

  **Still no retry decorator.** The rule held and paid: retrying would have
  hidden a real gap between a test's assumption and a documented contract. Fix
  the assertion, in its own commit, not here.
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
