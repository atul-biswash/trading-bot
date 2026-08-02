# Current milestone — Phase 5 M4b: move `stage` inward, then count failures

M4a wired the composition root and made the intent stream observable. Two things
it deliberately left in a provisional shape now come due, and both were deferred
for the same reason: **neither could be designed before the path had run.**

Everything below assumes M4a as built — read `engine/modes.py` and the M4a entry
in `docs/PHASE_HISTORY.md` before designing.

---

## Item 1 — `RiskAssessment.stage`, set by `evaluate`

**The problem M4a shipped with, knowingly.** `modes._refusal_stage` labels each
refusal for the log schema by **re-deriving `RiskManager.evaluate`'s control
flow** in a second file. Four of `evaluate`'s ten refusals return every
component as `None` — unknown pair, unusable price, `SELL`, nothing-to-close —
so they are separable only by position in that sequence, plus the `Signal` and
the root's own `pairs` mapping. Adding a refusal path, or reordering two checks,
mislabels a log line with nothing else failing.

**Why it was not done in M4a.** `RiskAssessment.stage` needs a stage vocabulary
*in the domain*, and choosing that vocabulary before an operator had read a
single one of these labels would have been designing the enum backwards. M4a's
job was to prove the vocabulary against real refusals. It has.

**The change.** `evaluate` sets `stage` at each `refuse(...)` call site and on
approval; `RefusalStage` (or its successor) moves from `engine/modes.py` into
the domain; `_refusal_stage` collapses to reading `assessment.stage`; the
`TestStageLadder` ordering sweep loses its reason to exist and most of it can be
deleted rather than ported.

**Decide, do not assume:**

- Does `stage` belong on `RiskAssessment` or on `RiskDecision`? `RiskDecision`
  already carries `rule`, and the two vocabularies overlap at `no_mark_price`.
  Overlapping-but-not-identical enums in one object is a smell; so is a second
  `rule`-shaped field.
- Is `stage` optional or required? Required is stronger — a refusal that cannot
  say where it stopped is the condition this item exists to remove — but it
  makes every `RiskAssessment(...)` construction site say something.
- Approval: one `approved` stage, or no stage at all? The log schema currently
  omits `stage` from `intent_dispatched` entirely.

**Do not** widen the `RiskManager` **port** as part of this. `evaluate`,
`check_exit` and `advance_trailing_stop` are still class-only; the port declares
`size_position` and `approve` (`core/interfaces.py:181`). That is a separate
decision belonging to M5, when execution becomes a second consumer.

---

## Item 2 — Q-A, the per-collaborator failure counter

**Deferred from M4a with a reason that still holds:** a consecutive-failure
threshold should be set from soak data, not guessed. M4a produces exactly that
data — `collaborator_failed` lines, named per collaborator, structured.

**Soak first.** Run the composition root against Testnet long enough to see
whether `collaborator_failed` ever fires in normal operation, and at what rate.
A threshold chosen before that number exists is a guess wearing a constant's
clothing.

**Automatic removal of a failing handler stays REJECTED.** Disabling a broken
executor converts "orders are failing" into "orders are not being attempted"
while positions are open. Whatever the counter does, it must not do that.

**Note the shape M4a left.** `TradingEngine._emit` catches per handler and logs
(`live_engine.py:325`), but the engine's consecutive-failure counter is fed only
from `_evaluate` (`:275`) — so a permanently broken handler produces a traceback
every bar forever and no pair is ever quarantined. M4a's chained handler mitigates
this by never raising, catching per collaborator inside itself. The counter is
what makes it visible rather than merely contained.

---

## Scope constraints

- **No order dispatch.** That is M5.
- **No new collaborator.** `IntentLogger` stays the terminal one.
- **Do not touch `live_engine.py:160`.** The empty-strategy guard is correct for
  a directly-constructed engine; the root refuses earlier with a better message,
  and both are wanted.

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

- **A leak window in `BinanceMarketDataStream.create` that is unreachable only
  because another file forbids it.** Checked during M4a, not a live defect, and
  recorded because the reason it is safe lives nowhere near the code that is
  safe.

  `create` (`websocket_client.py:184-206`) awaits `_BinanceSocketSource.create`
  — which builds a **second** `AsyncClient` (`:122`) — and *then* calls
  `cls(...)`. If that constructor raises, `source` is dropped without
  `aclose()`, leaking a live aiohttp session. Its three `ValueError`s
  (`websocket_client.py:164-169`) are unreachable **only** because
  `config/models.py` rejects those values at load: `reconnect_backoff_s`
  `Field(gt=0)`, `reconnect_max_retries` `Field(ge=0)`, and
  `_check_backoff_bounds` for `max < base` — with `validate_assignment=True`
  closing the assignment path too. All four verified.

  **The coupling is cross-module and nothing links the two files.** Relaxing a
  config constraint — or constructing the stream from anything other than
  `EngineConfig` — opens the window silently. Smallest correct fix, in
  `websocket_client.py` rather than the root (which cannot see `source`), and
  the same shape as `market_data.py:205-213`:

  ```python
  source = await _BinanceSocketSource.create(settings)
  try:
      return cls(source, ...)
  except Exception:
      await source.aclose()
      raise
  ```

  Note for contrast what is **not** a problem: that second `AsyncClient` is
  otherwise closed correctly. `stream.stop()` calls `source.aclose()`
  unconditionally at `websocket_client.py:250`, outside the task guard, so it
  releases whether or not `start()` was ever called — verified through the real
  chain with a counting fake, and on a step-5 boot failure.

- **`main.py`'s two error paths disagree about which stream they write to.**
  `:177` uses `log.error`, which reaches the console handler — **stdout** via
  `RichHandler`. `:162` uses `print(..., file=sys.stderr)`. So a configuration
  file that fails to *load* reports on stderr, while every `TradingBotError`
  after that — including all five M4a boot refusals — reports on stdout. An
  operator running `bot run 2>errors.log` captures nothing; one running
  `1>/dev/null` loses every refusal message. Also means the refusal text
  disappears entirely under `logging.console: false`.

  Small and self-contained, but it is a behaviour change to the CLI's contract
  and wants its own commit rather than riding along with a milestone.

- **Empty `enabled_pairs` is now refused at the root** (`_pair_timeframes`),
  distinguishing "`trading.pairs` is empty" from "all N configured pair(s) have
  `enabled: false`". `live_engine.py:160` was **not** touched and remains
  correct for direct construction — the root simply refuses earlier, before a
  client and a socket exist, and with a `TradingBotError` rather than a bare
  `ValueError` that escapes `main`'s handler as a traceback.

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

- **Nothing enforces the documented counts.** They are updated by hand and have
  drifted within a single session more than once. M4a sharpened the hazard
  rather than removing it: `ruff format` and `mypy` each appear in **three**
  places, not two — the fenced gate output in `CLAUDE.md`, the gate-scope table
  in `CLAUDE.md`, and `README.md` — so a pre-commit pass that checks the two
  obvious ones leaves the scope table stale. Worth a check that reads the
  numbers from a live run, but it must not become a gate that fails for a reason
  unrelated to the code.

- **Transitive dependencies still float.** The direct layer is pinned exactly;
  `websockets`/`aiohttp` under `python-binance` and friends resolve freely.
  `pydantic` pins `pydantic-core==2.46.4` exactly, so the `Money` guard's engine
  *is* locked; `pandas` constrains `numpy` only as `>=1.26.0`, so the float64
  leak path is pinned by **our** direct line and would be exposed if that line
  were relaxed. Proper fix is `pip-compile` with hashes over a `requirements.in`
  — deferred because it changes the install procedure for every contributor and
  the Docker build, and wants its own decision.

---

## After this: M5

**M5** — order dispatch. `OrderExecutor` over `BinanceClient.create_order`, the
unprotected window between an entry fill and its stop, idempotency via
`client_order_id`, order-status tracking, and `Portfolio` write-back — the last
of which retires M4a's boot-snapshot portfolio, which nothing mutates today.

**Q-B** (escalation policy) and **Q-C** (which protective levels rest at the
exchange, and how they reconcile with the client-side view after a restart) are
settled at the start of that milestone, not during it.

M5 is also when widening the `RiskManager` port becomes a real question rather
than a deferred one, because execution becomes its second consumer.
