# Current milestone — Phase 5 M3: risk manager

**Status:** not started
**Baseline to confirm first:** 460 passed · mypy 0 · ruff 0

Scope is **`src/trading_bot/risk/manager.py`** — the concrete `RiskManager` that
vets each signal against configured limits, sizes it (M1), attaches its protective
levels (M2), and is the handler wired into `TradingEngine.on_signal`. This is the
milestone that finally composes M1 + M2 into a live path.

It also owns the portfolio/limit **state** the manager reads (open positions, free
balance, equity, daily P&L, per-symbol cooldown) and the **ATR data bridge** that
turns a `MarketDataProvider` frame into the scalar `atr_value` M2's `rules.py`
expects.

Do **not** place orders or touch execution/`OrderExecutor`, the paper simulator,
or the backtest engine — producing an approved, sized, protected *intent* is the
boundary. Order dispatch is the next milestone.

Read `CLAUDE.md` for the rules and locked decisions, and `docs/PHASE_HISTORY.md`
for why M1 and M2 are shaped the way they are — M3 must compose with both without
reworking them.

---

## Contracts to verify empirically before designing

Do not take these from this document — confirm them in the code. They are listed
so you know what to look at, not so you can skip looking.

- `RiskManager` in `core/interfaces.py` — **both** methods. `size_position`
  returns a `SizingDecision`; `approve(signal, *, portfolio)` currently returns
  `bool` and carries a self-removing `# type: ignore[no-untyped-def]` on its
  unannotated `portfolio`. Typing `portfolio` this milestone is what forces that
  ignore to be deleted (`warn_unused_ignores` is on).
- `calculate_position_size` in `risk/position_sizing.py` — what `size_position`
  delegates to, and the `stop_price` it needs for `risk_per_trade`.
- `compute_protective_levels` / `should_exit` / `ProtectiveLevels` in
  `risk/rules.py` — how M3 obtains the stop the sizer needs, and the exit predicate
  M3 acts on. Note a level can come back `None` (disabled or sub-tick).
- `Position` in `core/models.py` — the mutable open-position type, its protective
  fields, and `unrealized_pnl(price)`.
- `RiskLimitsConfig` in `config/models.py` — `max_open_positions`,
  `max_daily_loss_percent` (still **`float`**), `max_position_size_percent`
  (already `Decimal`), `cooldown_minutes`. `StopLossConfig.atr_period` for the ATR
  bridge.
- `TradingEngine.on_signal` and its isolation model in `engine/live_engine.py` —
  the seam M3 attaches to, and how a raising handler is treated (quarantine).
- `MarketDataProvider` in `core/interfaces.py` — `get_dataframe`, `last_candle`,
  `is_ready` — the source the ATR bridge reads from.
- `atr()` in `indicators/indicators.py` — float64, **NaN during warmup** (the
  bridge must not hand a NaN to `rules.py`, which rejects non-finite ATR).
- The **injected-clock / injected-sleep** pattern already used (e.g. in
  `exchange/base.py`, the engine) — daily-loss and cooldown are time-dependent and
  must be testable without real time.

---

## The config conversion M3 owns

Per the project rule — *a config field becomes `Decimal` at the milestone that
first multiplies it by money* — M3 converts:

- `RiskLimitsConfig.max_daily_loss_percent` (the daily-loss tracker multiplies it
  by equity).

`max_open_positions` and `cooldown_minutes` stay `int` (a count and a duration,
never multiplied by money).

---

## Design questions to resolve before writing code

**1. The portfolio type — the most consequential decision in M3.**

`approve` takes a `portfolio` that has no type yet. Decide its shape and where it
lives. It must be referenced by the `RiskManager` port in `core/interfaces.py`, so
— like `SizingDecision` — it cannot live in `risk/`; `core/` is the innermost
layer. What does it hold: open `Position`s, free quote balance, equity, realised
daily P&L, per-symbol cooldown timestamps? Is it a frozen snapshot passed in per
call, or mutable live state the manager owns and updates? Argue it, and make
`equity` (total quote value incl. mark-to-market) computable from it.

**2. `approve`'s return shape — a port change to weigh.**

The port returns `bool`, but a rejected signal must tell an operator *why* (max
positions hit, symbol in cooldown, daily-loss halt). Decide whether to change the
port to a reason-carrying frozen object — the same problem M1 and M2 solved with
`SizingDecision` / `ProtectiveLevels` — and justify the port change if you make
it. State how it stays consistent with those two.

**3. The ATR data bridge.**

Confirm the M2-flagged intent: the manager holds a `MarketDataProvider` reference,
computes `atr(high, low, close, stop_loss.atr_period)`, and passes
`float(series.iloc[-1])` to `compute_protective_levels`. Decide how warmup is
handled — ATR is NaN until `atr_period + 1` bars, and `rules.py` **raises** on a
non-finite ATR, so the bridge must gate on readiness (skip, or fall back) rather
than hand a NaN across. State where `atr_period` readiness is checked.

**4. Order of operations for one signal.**

`risk_per_trade` sizing needs a stop; the stop may need ATR; `approve` may reject
before any of it. Pin the sequence: approve → protective levels (ATR) → size (from
the stop) → assemble the intent. Make the manager method express it, and decide
what a `None` stop (M2 sub-tick/disabled) means for `risk_per_trade` sizing here.

**5. Daily-loss tracking and cooldown — the stateful, time-dependent parts.**

Both need a clock. Decide where realised P&L accrues, how the day boundary is
defined (UTC) and reset, and how a per-symbol cooldown is recorded and expired.
Inject the clock so tests are hermetic. Keep the state's owner explicit.

**6. What M3 outputs, and where it stops.**

On an approved signal M3 produces an intent (an `OrderRequest`?) carrying quantity
and protective levels — but does **not** dispatch it. Decide the exact output type
and the seam the execution milestone will pick up, so it slots in without rework.

**7. `should_exit` wiring.**

M2's `should_exit` is a pure predicate over one price. Decide whether M3 drives it
here (per closed candle, choosing close vs high/low deliberately) or whether that
belongs with execution. If here, say which price it feeds and why.

---

## Tests

Hermetic unit tests in `tests/unit/test_risk_manager.py`, no network, no real
time (inject the clock), scripted fake `MarketDataProvider`. Exact `Decimal`
assertions in money code. Cover:

- each limit independently: `max_open_positions`, daily-loss halt, per-symbol
  cooldown — with the clock advanced explicitly
- `approve` rejection carries a reason naming the rule that fired
- equity = free quote + mark-to-market of open positions
- the ATR bridge: the manager computes ATR and feeds `rules.py`; **warmup is
  handled without raising** (NaN ATR never reaches `rules.py`)
- a `None` stop (sub-tick/disabled) handled coherently for each sizing method
- an **integration-style unit test composing M1 + M2 + M3**: a signal in →
  approved, sized, protected intent out, asserting the realised risk at the stop
  ≤ the `risk_per_trade` budget end to end
- no result built from a float — structural via the `Money` guard
- the `RiskManager.approve` `# type: ignore` is gone (mypy would flag it unused)

---

## Definition of done

- `pytest` → all green, no previously passing test broken
- `mypy` → zero (including the forced removal of `approve`'s `# type: ignore`)
- `ruff check src tests` → zero
- Design was presented and confirmed **before** implementation
- Committed as its own commit(s), with the reasoning in the body; keep the
  `max_daily_loss_percent` type change in its own commit, separate from new logic

---

## After this: Phase 5 M4 (execution wiring)

Placing the approved, sized, protected intent: `OrderExecutor` over
`BinanceClient.create_order`, protective-order placement (stop / take-profit),
and the paper simulator. `_enforce` remains the independent last line of defence
immediately before dispatch.
