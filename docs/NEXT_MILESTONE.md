# Current milestone — Q-A: the per-collaborator failure counter

**UNSCHEDULED, and that is the finding, not a scheduling accident.**

Q-A was deferred from M4a with a reason that has not moved: a
consecutive-failure threshold should be set from soak data rather than guessed.
M4a was supposed to produce that data — `collaborator_failed` lines, named per
collaborator, structured. It has not, and it cannot yet: **nothing dispatches an
order**, so the only collaborator that can fail is `IntentLogger`, whose failure
mode is "logging broke". A threshold calibrated against that number would be
calibrated against the wrong population entirely.

So Q-A stays open and stays unscheduled until M5 gives it a collaborator that
touches the network. Writing it now would produce a constant wearing a
guess's clothing, which is the exact thing the deferral existed to prevent.

**Automatic removal of a failing handler stays REJECTED.** Disabling a broken
executor converts "orders are failing" into "orders are not being attempted"
while positions are open. Whatever the counter does, it must not do that.

**The shape M4a left, unchanged by M4b.** `TradingEngine._emit` catches per
handler and logs, but the engine's consecutive-failure counter is fed only from
`_evaluate` — so a permanently broken handler produces a traceback every bar
forever and no pair is ever quarantined. M4a's chained handler mitigates this by
never raising, catching per collaborator inside itself. The counter is what
makes it visible rather than merely contained.

---

## Recommended next: M5 — order dispatch

`OrderExecutor` over `BinanceClient.create_order`, the unprotected window
between an entry fill and its stop, idempotency via `client_order_id`,
order-status tracking, and `Portfolio` write-back — the last of which retires
M4a's boot-snapshot portfolio, which nothing mutates today.

**Q-B** (escalation policy) and **Q-C** (which protective levels rest at the
exchange, and how they reconcile with the client-side view after a restart) are
settled at the start of that milestone, not during it.

**Q-D — the `RiskManager` port.** M5 is when widening it becomes a real question
rather than a deferred one, because execution becomes its second consumer.
`evaluate`, `check_exit` and `advance_trailing_stop` are still class-only; the
port declares `size_position` and `approve`. M4b deliberately did **not** touch
this, and deliberately did not move `RiskAssessment` out of `risk/manager.py`
either — the two decisions are the same decision and should be made once, with
all consumers visible.

Note for the record: M4b's brief said `RefusalStage` would move "into the
domain", and that phrase resolved to **two** destinations once the tree was
read. The enum moved to `core/enums.py` (forced: `engine/` imports `risk/`, so
`risk/` cannot import `engine/`). `RiskAssessment` did not move, and defers to
Q-D.

---

## Open items — not scoped to any milestone

- **`Portfolio.free_quote` has no `ge=0` constraint** (`core/portfolio.py`). A
  negative free quote is nonsense for spot and is unreachable today only because
  the portfolio is seeded from exchange balance strings — an unenforced domain
  invariant held up by its one caller. Surfaced by M4b while checking whether
  the `size_not_tradeable` / `unaffordable` guard pair was separately
  satisfiable (it is not; see M4b finding iii). **Deliberately not added in
  M4b**: it is a domain change with its own blast radius, not a rider on an
  observability milestone.

- **`NO_MARK_PRICE` is constructed twice with different reason text.** `approve`
  says "…; equity is unknown, so no limit can be checked"; `evaluate` says only
  "cannot value open position(s) …". The two never meet at runtime because
  `evaluate` bypasses the public `approve` entirely — it calls `_mark_prices`
  then `_approve` directly. Collapsing them is a decision about the port, so it
  belongs with Q-D.

- **Two adjacent refusal-guard pairs remain unpinned by an ordering test:**
  `unsupported_action ↔ no_mark_price` and `no_mark_price ↔ limit_refused`. The
  second is the one where a swap crashes rather than mislabels — equity is
  computed between the guards — so a test there would assert on an exception
  type and prove something other than ordering. Pre-existing debt that M4b
  illuminated rather than created.

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

- **Empty `enabled_pairs` is refused at the root** (`_pair_timeframes`),
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
  drifted within a single session more than once. M4b moved only the `pytest`
  numbers — no `src/`, `tests/` or `scripts/` file was added or deleted, so
  `ruff format` held at 83 and `mypy` at 58 — which is exactly the case where a
  hurried pass updates the fenced gate output and leaves the scope table alone.
  `ruff format` and `mypy` each appear in **three** places: the fenced gate
  output in `CLAUDE.md`, the gate-scope table in `CLAUDE.md`, and `README.md`.
  Worth a check that reads the numbers from a live run, but it must not become a
  gate that fails for a reason unrelated to the code.

- **Transitive dependencies still float.** The direct layer is pinned exactly;
  `websockets`/`aiohttp` under `python-binance` and friends resolve freely.
  `pydantic` pins `pydantic-core==2.46.4` exactly, so the `Money` guard's engine
  *is* locked; `pandas` constrains `numpy` only as `>=1.26.0`, so the float64
  leak path is pinned by **our** direct line and would be exposed if that line
  were relaxed. Proper fix is `pip-compile` with hashes over a `requirements.in`
  — deferred because it changes the install procedure for every contributor and
  the Docker build, and wants its own decision.
