# Current milestone — M5: order dispatch

**Q-C is decided.** The contract is `docs/QC_PROTECTIVE_ORDERS.md`, and M5
implements against it rather than re-deciding it. Read that first; this file is
the task list and the single home for live open items.

## What M5 delivers

The bot places its first order. Concretely:

1. **`execution/executor.py`** — currently a docstring-only stub. It maps an
   approved `TradeIntent` onto the placement shape the config selects (OTOCO, OTO
   or a single order), dispatches it, and hands the result to reconciliation.
2. **The reconciler** — compares requested protection against what the exchange
   reports, at boot, after each placement, and per candle per open position.
3. **`Portfolio` write-back** — open/close methods it does not have today, driven
   by observed fills rather than by our own dispatch. This retires M4a's
   boot-snapshot portfolio, which nothing mutates.
4. **`IntentLogger` is replaced**, not extended. It was deliberately not called
   `Executor` and deliberately not placed in `execution/`; that stub is now
   claimed for real.

## Ordered by what blocks what

**First, because everything else assumes them:**

- `max_entry_slippage` as a new `RiskConfig` field — `Decimal` (it multiplies a
  price), `gt=0`, with a named default and a stated rationale.
- `TradeIntent.price` changes meaning to `entry_limit`. Its docstring is
  currently **false** under Q-C and must be corrected; `_check_invariants` forces
  `compute_protective_levels` to be called with `entry_limit` too. The
  `binding_price` sizing fix already landed stays correct unchanged.
- `SymbolInfo` must model `PERCENT_PRICE_BY_SIDE`, with a band violation as a
  **refusal value, not a raise**. The margin against the moving 5-minute average
  is deliberately unspecified by Q-C and needs a named default here.
- `ProtectionState` including `ABSENT_BY_DESIGN`, and the new `Position` fields:
  `entry_bar_time`, `protection`, `order_list_id`, `last_reconciled_at`.
- The TP-only refusal in `RiskConfig`, with the validator renamed
  `_check_protective_coverage` — **a separate, mechanical commit** from the
  semantic change that adds the third check.

**Then:**

- `translate_binance_error` rebuilt to match **message text, not code**.
  `-2010 'Duplicate order sent.'` is a success signal under deterministic IDs and
  must not surface as an error. New: `OrderNotFoundError`, `FilterRejectedError`
  carrying the parsed filter name, and contract errors for `-1106` / `-1128` /
  `-1158` / `-1159`.
- The discretionary `CLOSE` path: cancel, confirm by query, sell `MARKET`.
- The unprotected-window log line, on entry and exit, with symbol and position
  identity.

## Q-B — escalation policy

Settled at the start of M5, not during it. What `CRITICAL` actually does — halt
entries, notify, and by what mechanism — is undecided, and Q-C leans on it in
three places.

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

**Q-D is no longer open.** It was folded into Q-C as a decision: the port widens
to expose the composed path and `RiskAssessment` moves with it. Implementation
belongs to M5.

- **`_enforce` is blind to notional for exactly the order types
  `applyMinToMarket` covers. M5 work.** `BinanceClient._enforce` guards its
  `min_notional` check with `if price is not None`, and `OrderRequest.price` is
  `None` for both `MARKET` and stop-market (`STOP_LOSS`, which carries only
  `stop_price`). So the independent last line of defence cannot perform the check
  at all for those types, while `NOTIONAL.applyMinToMarket` is measured `true` on
  BTCUSDT and ETHUSDT, on Testnet and mainnet alike.

  This is the sibling of the sizing bug fixed alongside it, one layer down, and
  it is **not** closed by that fix: sizing now measures the notional at the lowest
  price the trade carries, but `_enforce` re-checks independently.

  It cannot be fixed by symmetry. A market order has no price to multiply, so
  `_enforce` would need one passed in — a signature change to the adapter plus a
  decision about where that price comes from (the signal's reference price, a
  fresh ticker, or the `avgPrice` the filter itself is evaluated against, which is
  a five-minute average and not any price the caller holds). Under Q-C both
  protective legs are stop-markets, so this now sits on the main path.

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

- **`Portfolio.free_quote` has no `ge=0` constraint.** A negative free quote is
  nonsense for spot and is unreachable today only because the portfolio is seeded
  from exchange balance strings — an unenforced domain invariant held up by its
  one caller. Q-C's write-back gives it a second caller, so this stops being
  theoretical in M5.

- **`NO_MARK_PRICE` is constructed twice with different reason text.** `approve`
  says "…; equity is unknown, so no limit can be checked"; `evaluate` says only
  "cannot value open position(s) …". The two never meet at runtime because
  `evaluate` bypasses the public `approve` entirely — it calls `_mark_prices` then
  `_approve` directly. Collapsing them is a decision about the port, which Q-C has
  now made, so it can land with M5.

- **`_exit_assessment`'s approval site passes `stage=None` and is pinned by no
  test.** It is the second of two approval constructions — the entry approval in
  `evaluate` is covered by `test_an_approval_reports_no_stage`, this one is not —
  and it can drift alone. Its fixture shape differs enough (an open position, a
  `CLOSE` signal) to be separate work rather than a rider. Recorded so it is not
  mistaken for covered by the entry-path test. Q-C changes this path, so M5
  touches it.

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

- **Nothing enforces the documented counts.** They are updated by hand and have
  drifted within a single session more than once. `ruff format` and `mypy` each
  appear in **three** places: the fenced gate output in `CLAUDE.md`, the
  gate-scope table in `CLAUDE.md`, and `README.md`. Worth a check that reads the
  numbers from a live run, but it must not become a gate that fails for a reason
  unrelated to the code.

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

  **Three instances of the same class in two turns**, and the third is the
  inverse shape, which is why it belongs in the same entry rather than filed
  separately:

  | Rule | Lived in | Shape |
  |---|---|---|
  | `no I/O` on the handler chain | one docstring (`engine/modes.py`) | rule outside the authority |
  | `an exit must always be permitted` | one docstring (`core/interfaces.py`) | rule outside the authority |
  | `all files are LF` | the authority | **authority asserting what the tree never satisfied** |

  The first two are rules the authority did not know about; the third is a rule
  the tree did not obey. Both directions are invisible from the side that matters,
  and both surface only when something tries to act on them.

  So the M5a salvage is: the seven `PROJECT_KNOWLEDGE.md` sections **plus** a pass
  over `src/` module and method docstrings for rules stated in the imperative —
  "must", "never", "always", "only" — that constrain future code and appear
  nowhere in `CLAUDE.md`. Classify each as deliberately dropped, enforced by code
  instead, or accidentally absent. **Produce the list; promote nothing.** Each
  promotion is a semantic change to the authority and gets its own commit, per the
  constraint that governed M5-0's own salvage item.
