# Current milestone — Q-C: where the protective levels actually live

**This is an open design question, not a scoped task.** There is no plan below,
no file list and no acceptance criteria, because none of those can be written
until the question is answered. The design conversation happens first.

## The question

**Which protective levels rest as live orders at the exchange, and which stay
client-side — and how are the two views reconciled when they disagree?**

Both halves matter. The first is a placement decision; the second is what makes
the first survivable.

## Why it comes before `executor.py`

Every executor design assumes an answer to this, whether or not it says so. The
answer decides what `create_order` is called with and how many times, what the
unprotected window between an entry fill and its stop actually *is* (or whether
it exists at all), what order-status tracking has to track, and what `Portfolio`
write-back reconciles against. Settle it afterwards and the executor gets
rewritten rather than extended.

That is the whole reason this is a milestone and not a footnote inside M5.

## The current position, stated honestly

`risk/manager.py` implements and documents client-side stops evaluated on the
**closed bar's `close`**, never its high or low. That is **correct as policy**:
triggering on a price the bar has already left is optimistic in backtest and
dishonest live, so feeding the close makes a stop fire late rather than early,
which is the safe direction to be wrong in.

It is **incomplete as survival**. A client-side stop needs a live process to
act. A crashed bot, a lost WebSocket, a host reboot, a deploy — in every one of
those the position is open and nothing is watching it. The module docstring
already calls this path "the fallback"; what it does not say is what the primary
is, because there is no primary yet.

## The reconciliation problem

An exchange-resting stop and the client-side view are two records of one fact,
and they drift:

- The exchange can fill or cancel a resting order while the client still
  believes it rests. The client then holds a position it thinks is protected and
  is not, or thinks it holds a position it no longer has.
- A trailing stop that moves client-side has to be cancelled and replaced at the
  exchange. Between the cancel and the replace there is a gap, and a crash
  inside that gap leaves no stop at all.
- After a restart the client-side view is rebuilt from whatever was persisted
  while the exchange view is authoritative and current. Which one wins, and how
  is the difference detected rather than assumed away?

**Which record is authoritative, and at what moment**, is the part that has to be
decided rather than discovered later from a reconciliation bug.

---

## Carried forward — still open, none of them scheduled

**Q-A — the per-collaborator failure counter. UNSCHEDULABLE, and that is the
finding rather than a scheduling accident.** Deferred from M4a on the grounds
that a consecutive-failure threshold should come from soak data rather than a
guess. M4a was supposed to produce that data — `collaborator_failed` lines,
named per collaborator, structured. It has not and it **cannot yet**: nothing
dispatches an order, so the only collaborator that can fail is `IntentLogger`,
whose failure mode is "logging broke". A threshold calibrated against that
population would be calibrated against the wrong one. It cannot be scheduled
until M5 gives it a collaborator that touches the network.

*Two things about it that are already settled.* **Automatic removal of a failing
handler stays REJECTED** — disabling a broken executor converts "orders are
failing" into "orders are not being attempted" while positions are open, and
whatever the counter does it must not do that. And the shape M4a left is
unchanged by M4b: `TradingEngine._emit` catches per handler and logs, but the
engine's consecutive-failure counter is fed only from `_evaluate`, so a
permanently broken handler produces a traceback every bar forever and no pair is
ever quarantined. M4a's chained handler mitigates this by never raising. The
counter is what would make it visible rather than merely contained.

**Q-B — escalation policy.** Settled at the start of M5, not during it.

**Q-D — the `RiskManager` port.** `evaluate`, `check_exit` and
`advance_trailing_stop` are class-only; the port declares `size_position` and
`approve`. Widening it becomes a real question when execution becomes its second
consumer. M4b deliberately did not touch it, and deliberately did not move
`RiskAssessment` out of `risk/manager.py` either — the two are the same decision
and should be made once, with all consumers visible.

Note for the record: M4b's brief said `RefusalStage` would move "into the
domain", and that phrase resolved to **two** destinations once the tree was
read. The enum moved to `core/enums.py` (forced: `engine/` imports `risk/`, so
`risk/` cannot import `engine/`). `RiskAssessment` did not move, and defers to
Q-D.

---

## After Q-C: M5 — order dispatch

`OrderExecutor` over `BinanceClient.create_order`, the unprotected window
between an entry fill and its stop, idempotency via `client_order_id`,
order-status tracking, and `Portfolio` write-back — the last of which retires
M4a's boot-snapshot portfolio, which nothing mutates today.

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

- **`_exit_assessment`'s approval site passes `stage=None` and is pinned by no
  test.** It is the second of the two approval constructions — the entry
  approval in `evaluate` is covered by `test_an_approval_reports_no_stage`, this
  one is not — and it can drift alone. Left uncovered in the M4b follow-up
  because its fixture shape differs enough (an open position, a `CLOSE` signal)
  to be separate work rather than a rider. Recorded so it is not mistaken for
  covered by the entry-path test.

- **Two adjacent refusal-guard pairs remain unpinned by an ordering test:**
  `unsupported_action ↔ no_mark_price` and `no_mark_price ↔ limit_refused`. The
  second is the one where a swap crashes rather than mislabels — equity is
  computed between the guards — so a test there would assert on an exception
  type and prove something other than ordering. Pre-existing debt that M4b
  illuminated rather than created.

- **`size_not_tradeable ↔ unaffordable` is order-INDEPENDENT, which is a
  different claim from the entry above and must not be collapsed into it.**
  Those two are *unpinned*; this one is *unpinnable*. `is_tradeable` is
  `quantity > 0` and a negative quantity is forbidden, so `not is_tradeable`
  implies `cost == 0`, and the affordability guard is `cost > free_quote` — for
  any non-negative balance the two conditions are **mutually exclusive** and
  swapping the guards is unobservable in every reachable state. A test that bit
  would need a negative `free_quote` and would then fail on a harmless
  refactor while pinning nothing real. Recorded because the reasoning is not
  obvious and was re-derived once already; see M4b findings (iii) and (iv) in
  `docs/PHASE_HISTORY.md`.

- **This document's own open items cite roughly ten line references** —
  `config/settings.py`, `binance_client.py`, `main.py`, `websocket_client.py`
  and `market_data.py` all appear below with `:NNN` suffixes. M4b established
  that a line number in prose is an unaudited drift surface and deleted three
  such references from test docstrings rather than correcting them, on the
  grounds that the prose was already right about the ordering and the numbers
  were not. These are the same hazard in a document instead of a docstring, and
  nothing checks them. **Carried verbatim for now**: verifying or stripping them
  is its own small pass, and doing it silently inside a milestone rotation would
  bury a change nobody asked for.

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
