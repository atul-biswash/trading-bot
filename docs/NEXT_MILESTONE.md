# Current milestone — M5a: the vocabulary

**M5 is six milestones, not one.** M5-0 (decisions) is complete. M5a is the first
that changes `src/`, and it is deliberately the one with no I/O in it.

Read first: `docs/QC_PROTECTIVE_ORDERS.md` (the contract), `docs/M5_NUMBERS.md`
(the six numbers and their status), `docs/QB_ESCALATION.md` (what `CRITICAL`
does). The decisions themselves are locked in `CLAUDE.md`; this file is the task
list and the single home for live open items.

## Prerequisite, already met

**`alpha` is BOUNDED at 0.5** and its measurement is taken — `M5_NUMBERS.md` §3.
No further measurement gates M5a.

## What M5a delivers

**Config.** `max_entry_slippage`, the `PERCENT_PRICE_BY_SIDE` band margin,
`max_position_staleness`, `dispatch_deadline_s`, `reconcile_deadline_s`. The
TP-only refusal as a **mechanical** rename commit (`_check_protective_coverage`)
followed by the semantic commit adding the third check. The `AppConfig` coherence
validator enforcing `P_sim x D + N_max x T_recon <= alpha x T_min`, with the
refusal message given in `M5_NUMBERS.md`.

**Domain.** `ProtectionState` in `core/enums.py`. `Position` gains
`entry_bar_time`, `protection` (**required, non-nullable**), `order_list_id`,
`last_reconciled_at`, with `opened_at` made explicit. `Portfolio` gains `ge=0` on
`free_quote`, `open_position` / `close_position`, the unmanaged-holdings boot
snapshot, and the mark-to-stop committed-risk term in `daily_loss_exceeded`.
`SymbolInfo` models `PERCENT_PRICE_BY_SIDE` and `MAX_NUM_ALGO_ORDERS`.
`OrderStatus` gains `PENDING_NEW` and `EXPIRED_IN_MATCH` — without which
`to_order` raises an **untranslated** `ValueError` on any order-list read-back,
so no later milestone can be built without it. `Order` gains `order_list_id` and
`stop_price`; `OrderRequest` gains `time_in_force`.

**Do NOT add a `model_validator` to `Position`.** `validate_assignment=True` means
it re-runs on every assignment and would observe the intermediate state between
`advance_trailing_stop`'s two writes. The prescribed fix — collapsing those writes
into one method on `Position` — has to land first, and it is not M5a's.

## Sequencing — one item is explicitly last

**The composed-path warm-up runs `evaluate` at composition-root time, so it lands
LAST in M5a, after the domain widening has settled.** Every construction site the
boot path touches is one this milestone changes — `Position.protection` required
and non-nullable, `Portfolio` open/close, `EntryIntent`/`ExitIntent`,
`daily_loss_exceeded` gaining `marks`. A warm-up written against today's shapes
needs rewriting inside the same milestone that changes them.

Its scope is an open decision: `UNKNOWN_PAIR` warms the entry to the path only and
needs no market data or portfolio state, while warming the full path needs a
synthetic pair context and portfolio — more boot-time machinery, and more to rot.
Either way it is **timed and logged at boot**, because boot-time code that exists
only for timing rots silently and the failure is invisible until the cost
reappears on a real order.

## Absorbed from open items into M5a's scope

These were carried as open items and are now scheduled work, so they are removed
from the list below rather than duplicated:

- `Portfolio.free_quote` gains `ge=0` — Q-C's write-back gives it a second caller.
- `NO_MARK_PRICE`'s two divergent reason strings collapse; the port question that
  blocked it is decided.
- `_exit_assessment`'s approval site gets the test it lacks.
- `_enforce`'s `min_notional` blindness for `MARKET` and stop-market orders, and
  its use of `step_size` / `min_qty` where sizing uses the **effective** filters.

**Q-D is closed**, not deferred: folded into Q-C as a decision, implemented in
M5b when the port widens and `RiskAssessment` moves to `core/`.

---

## Open items — carried forward, none scheduled

**Q-A — the per-collaborator failure counter. Still unschedulable, and that is
the finding.** Its thresholds need soak data that cannot exist until something
dispatches an order, so it is blocked behind M5. Two things about it are already
settled: **automatic removal of a failing handler stays REJECTED** — disabling a
broken executor converts "orders are failing" into "orders are not being
attempted" while positions are open — and the shape M4a left is unchanged.
`TradingEngine._emit` catches per handler and logs, but the engine's
consecutive-failure counter is fed only from `_evaluate`, so a permanently broken
handler produces a traceback every bar forever and no pair is ever quarantined.
M4a's chained handler mitigates this by never raising; the counter would make it
visible rather than merely contained.

- **`MARKET_LOT_SIZE` and `NOTIONAL.applyMinToMarket` on a *triggered* stop-type
  order — UNRESOLVED.** Neither the installed `python-binance` nor the
  `exchangeInfo` payload states whether "market" means an order submitted with
  `type=MARKET` or any order that executes at market, including a triggered
  `STOP_LOSS`. Both carry the values and neither defines the term. Settling it
  needs Binance's published spot documentation or a test that requires a stop to
  actually trigger — an irreversible fill.

  Sizing takes the stricter of `LOT_SIZE` and `MARKET_LOT_SIZE` rather than
  guessing. On mainnet BTCUSDT and ETHUSDT the market filter reports zeroed
  min/step, so the conservatism currently costs nothing; it is there for the
  symbol nobody has checked. **Under Q-C both protective legs are stop-markets,
  so if this binds, it binds on everything.**

- **`MarketLotSize.max_qty` is parsed but not read.** The "0 means no constraint"
  convention is per-field, not filter-wide: both Testnet and mainnet report a real
  `maxQty` beside zeroed min/step, so applying one rule to all three would either
  discard a live maximum or refuse every trade. Nothing enforces a maximum
  quantity today and `max_position_size_percent` already bounds size from above.
  Carried for fidelity to the wire and tested through the mapper.

- **The 36-character client-order-ID limit is ASSUMED, not measured.** It was
  asserted in a probe report and never verified. Q-C's ID scheme reaches it at
  generation >= 100 on a 12-character symbol. One deliberately over-long rejected
  request would settle it, free, and it is not a blocker.

- **Two adjacent refusal-guard pairs remain unpinned by an ordering test:**
  `unsupported_action` against `no_mark_price`, and `no_mark_price` against
  `limit_refused`. The second is the one where a swap crashes rather than
  mislabels — equity is computed between the guards — so a test there would assert
  on an exception type and prove something other than ordering. Pre-existing debt
  that M4b illuminated rather than created.

- **`size_not_tradeable` against `unaffordable` is order-INDEPENDENT, a different
  claim from the entry above and not to be collapsed into it.** Those two are
  *unpinned*; this one is *unpinnable*. `is_tradeable` is `quantity > 0` and a
  negative quantity is forbidden, so `not is_tradeable` implies `cost == 0`, and
  the affordability guard is `cost > free_quote` — for any non-negative balance
  the two conditions are mutually exclusive and swapping the guards is
  unobservable in every reachable state. A test that bit would need a negative
  `free_quote` and would then fail on a harmless refactor while pinning nothing
  real.

- **PAPER mode reaches Binance *mainnet* with empty credentials. Contained by
  M4a, not fixed.** This contradicts "Testnet is the default everywhere", so it is
  recorded rather than left in the code to be rediscovered.

  Two lines make it happen, each defensible alone: `Settings.binance_credentials`
  raises only when `mode.is_live_connection`, so PAPER and BACKTEST get `("", "")`
  back instead of an error; `BinanceClient.create` sets `testnet` from
  `settings.mode is TradingMode.TESTNET`, which is `False` for PAPER — so the
  adapter points at `api.binance.com`. `main.py` gates its own credential check on
  the same property, so nothing upstream catches it. Before M4a,
  `run --mode paper` opened an *unauthenticated mainnet* connection and streamed
  live production prices. Read-only, no order path — but a live-environment
  connection the mode name says should not exist.

  **M4a contains it:** `live_system` refuses a non-`is_live_connection` mode as
  its first statement, before any client is constructed. The underlying defect is
  untouched — anything building a `BinanceClient` outside the composition root
  still gets a mainnet client in PAPER mode.

  The real fix is a decision, not a patch: either PAPER resolves `testnet=True`
  (live prices from Testnet, which is what "live prices, no orders sent" almost
  certainly meant), or `binance_credentials()` refuses every mode that constructs
  a client. It belongs with `paper/simulator.py`, the milestone that gives PAPER a
  composition root of its own.

- **A leak window in `BinanceMarketDataStream.create`, unreachable only because
  another file forbids it.** `create` awaits `_BinanceSocketSource.create` — which
  builds a **second** `AsyncClient` — and *then* calls `cls(...)`. If that
  constructor raises, the source is dropped without `aclose()`, leaking a live
  aiohttp session. Its three `ValueError`s are unreachable **only** because
  `config/models.py` rejects those values at load: `reconnect_backoff_s`
  `Field(gt=0)`, `reconnect_max_retries` `Field(ge=0)`, and `_check_backoff_bounds`
  for `max < base`, with `validate_assignment=True` closing the assignment path.

  **The coupling is cross-module and nothing links the two files.** Relaxing a
  config constraint, or constructing the stream from anything other than
  `EngineConfig`, opens the window silently. The smallest correct fix belongs in
  `websocket_client.py` rather than the composition root, which cannot see the
  source:

  ```python
  source = await _BinanceSocketSource.create(settings)
  try:
      return cls(source, ...)
  except Exception:
      await source.aclose()
      raise
  ```

  Not a live defect. Recorded because the reason it is safe lives nowhere near the
  code that is safe. For contrast, that second `AsyncClient` is otherwise closed
  correctly: `stream.stop()` calls `source.aclose()` unconditionally, outside the
  task guard, so it releases whether or not `start()` was ever called.

- **`main.py`'s two error paths disagree about which stream they write to.** One
  uses `log.error`, which reaches the console handler — **stdout** via
  `RichHandler`. The other uses `print(..., file=sys.stderr)`. So a configuration
  file that fails to *load* reports on stderr, while every `TradingBotError` after
  that — including all five M4a boot refusals — reports on stdout. An operator
  running `bot run 2>errors.log` captures nothing; one running `1>/dev/null` loses
  every refusal message. It also means the refusal text disappears entirely under
  `logging.console: false`. Small and self-contained, but a behaviour change to
  the CLI's contract, so it wants its own commit.

- **`make check` has never been executed through `make` on this machine.** `make`
  is not installed. The four delegating recipes are tab-indented (verified) and
  the gate itself no longer depends on `make`, but `$(PYTHON)` expansion and
  recipe execution remain unexercised. Needs one run where `make` exists.

- **`make cov` and `make format` do not honour `$(PYTHON)`.** They call bare
  `pytest` / `ruff`, so `make PYTHON=... cov` silently uses a different
  interpreter than `make PYTHON=... check` would. Outside the gate, so left alone;
  inconsistent, so recorded.

- **The `logging.file.json` flag controls console *and* file together.** There is
  no way to have a pretty console and a JSON file. Roughly three lines in
  `_console_handler` to separate; deliberately out of scope so far.

- **Nothing enforces that the *prose* still describes the current plan, either.**
  The sibling of the counts item below, one level up, and it has now bitten twice
  in one milestone. The rotation procedure names three files; `README.md` drifted
  on the gate counts because the procedure did not name it, and
  `QC_PROTECTIVE_ORDERS.md` drifted on **substance** because a decided contract can
  be superseded by a later decision while the milestone doing the superseding edits
  entirely different files. Q-C §9 went on specifying `TradeIntent.price` changing
  meaning after D3 had split the type.

  The procedure has been widened — `README.md` joins step 2, and a fourth step
  re-reads the contracts — but **the fix is a discipline, not a mechanism**, and
  discipline is what failed the first time. What would actually catch it is hard to
  automate honestly: "does this paragraph still describe the plan" is not greppable,
  and a check that fired on every superseded-looking sentence would be ignored
  within a milestone. The cheapest real improvement is probably a convention that a
  superseding decision names the contract section it supersedes, so the annotation
  becomes a lookup rather than a re-read. Recorded rather than solved.

- **Nothing enforces the documented counts.** They are updated by hand and have
  drifted within a single session more than once. `ruff format` and `mypy` each
  appear in **three** places: the fenced gate output in `CLAUDE.md`, the
  gate-scope table in `CLAUDE.md`, and `README.md`. Worth a check that reads the
  numbers from a live run, but it must not become a gate that fails for a reason
  unrelated to the code.

- **`ruff` and `mypy` are unpinned while every runtime dependency is pinned
  `==`.** `requirements-dev.txt` floats the two tools that *produce the numbers
  the gate reports*. A pin in this project encodes a **verified** version, not a
  working one — `pydantic`, `pandas` and `numpy` carry line comments saying so —
  and by that standard these two have a stronger claim than most: a `ruff` minor
  release can change `ruff format`'s output and turn the gate red on a tree
  nobody touched, and a `mypy` release can add a check that fails a file it
  passed yesterday. Either failure looks like a regression in the code and is
  not one.

  Raised repeatedly in conversation and never written down, which is presumably
  why it keeps being raised. Recording it here so the next raise can be answered
  from the file. Deliberately not fixed in passing: pinning them changes what a
  fresh `pip install -r requirements-dev.txt` produces for every contributor, and
  it wants the same decision as `pip-compile` below rather than a separate one.

- **Transitive dependencies still float.** The direct layer is pinned exactly;
  `websockets` / `aiohttp` under `python-binance` and friends resolve freely.
  `pydantic` pins `pydantic-core` exactly, so the `Money` guard's engine *is*
  locked; `pandas` constrains `numpy` only as `>=1.26.0`, so the float64 leak path
  is pinned by **our** direct line and would be exposed if that line were relaxed.
  The proper fix is `pip-compile` with hashes over a `requirements.in` — deferred
  because it changes the install procedure for every contributor and the Docker
  build, and wants its own decision.

- **S3's M5a salvage covers `src/` docstrings too, not only the out-of-repo
  document.** The salvage was originally scoped to the 751-line
  `PROJECT_KNOWLEDGE.md` held outside the repository — diffing the sections that
  state rules in their own voice (§§5–8, §§10–12) against `CLAUDE.md`, on the
  finding that its §7 carried a handler rule (`no I/O`) that `CLAUDE.md` never
  had. §9 was checked and is clean: 20 rules, none absent, because its own header
  defers to `CLAUDE.md` and it never claimed completeness. **Look at the sections
  that state rules, not the one that curates them.**

  The scope widens because a second instance surfaced from a different source
  entirely. *"An exit must always be permitted — a limit that could trap an open
  position would be a risk rule that creates risk"* governs the whole `CLOSE`
  path and lived only in `core/interfaces.py::RiskManager.approve`'s docstring and
  in `risk/manager.py::_exit_assessment`. It was never in `CLAUDE.md`. It was
  found the same way `no I/O` was — by M5 trying to violate it — and it has now
  been added *with* its scope clause.

  **Two instances of the same class, from two different sources:**

  | Rule | Lived in |
  |---|---|
  | `no I/O` on the handler chain | one docstring (`engine/modes.py`) |
  | `an exit must always be permitted` | one docstring (`core/interfaces.py`) |

  Both are rules the authority did not know about, both constrain code nobody had
  written yet, and both surfaced only when M5 tried to act on them — which is the
  argument for finding the rest before M5a writes code rather than after.

  So the M5a salvage is: the seven `PROJECT_KNOWLEDGE.md` sections **plus** a pass
  over `src/` module and method docstrings for rules stated in the imperative —
  "must", "never", "always", "only" — that constrain future code and appear
  nowhere in `CLAUDE.md`. Classify each as deliberately dropped, enforced by code
  instead, or accidentally absent. **Produce the list; promote nothing.** Each
  promotion is a semantic change to the authority and gets its own commit, per the
  constraint that governed M5-0's own salvage item.
