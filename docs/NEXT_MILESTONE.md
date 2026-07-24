# Current milestone — Phase 5 M2: protective exit rules

**Status:** not started
**Baseline to confirm first:** 373 passed · mypy 0 · ruff 0

Scope is **`src/trading_bot/risk/rules.py` only** — pure functions that compute
stop-loss, take-profit and trailing-stop levels, and decide when an open position
should exit.

Do **not** implement `risk/manager.py`, the risk limits, portfolio state, or any
engine wiring. That is M3.

Read `CLAUDE.md` for the rules and locked decisions, and `docs/PHASE_HISTORY.md`
for why Phase 5 M1 is shaped the way it is — M2 must stay consistent with it.

---

## Contracts to verify empirically before designing

Do not take these from this document — confirm them in the code. They are listed
so you know what to look at, not so you can skip looking.

- `Money` and `_reject_float` in `core/models.py` — the enforced Decimal guard.
- `Position` — especially `stop_loss`, `take_profit`, `trailing_stop`,
  `highest_price`, `lowest_price`. **The trailing stop's high-water mark already
  has a home**, so `rules.py` can stay pure. Do not put state on `self`.
- `SizingDecision` and `calculate_position_size` in `risk/position_sizing.py` —
  the return-shape precedent, and what M2 must compose with.
- `RiskManager` in `core/interfaces.py`. Leave `approve` alone; its
  `# type: ignore` is self-removing and belongs to M3.
- `StopLossConfig`, `TakeProfitConfig`, `TrailingStopConfig` in `config/models.py`
  — currently **all `float`**.
- `atr()` and `true_range()` in `indicators/indicators.py` — float64 Series out.
- `round_price()` in `utils/helpers.py` — **unconditionally `ROUND_DOWN`.**
- `SymbolInfo.price_tick`.

---

## The config conversion M2 owns

Per the project rule — *a config field becomes `Decimal` at the milestone that
first multiplies it by money* — M2 is expected to convert:

- `StopLossConfig.percent`, `StopLossConfig.atr_multiplier`
- `TakeProfitConfig.percent`, `TakeProfitConfig.rr_multiple`
- `TrailingStopConfig.activation_percent`, `TrailingStopConfig.trail_percent`

`atr_period` stays `int`. `max_daily_loss_percent` stays `float` for M3.

---

## Design questions to resolve before writing code

**1. Directional tick rounding — the most consequential decision in M2.**

`round_price` always truncates, which can be correct for at most one side of a
protective level. Consider: for a long, if the stop rounds *away* from entry, the
realised stop distance exceeds the distance `size_by_risk_per_trade` divided by —
so actual risk silently exceeds the configured `risk_per_trade` budget. A
rounding direction chosen by accident is a silent risk-budget breach.

Work out the conservative direction for stop-loss and for take-profit
independently, decide whether the principle generalises, and say whether it needs
a new directional helper alongside `round_price` or a change to it. State the
`decimal` rounding mode explicitly.

**2. The ATR `float`→`Decimal` boundary.**

`atr()` returns float64, but a stop price must be `Money`, and `Money` rejects
`numpy.float64`. This is a *different* boundary from the config one and needs its
own named, tested conversion. Decide where it lives and how it avoids becoming a
precision leak.

**3. Does `rules.py` take a DataFrame, or a pre-computed ATR value?**

Taking a frame drags pandas into the risk layer and makes every test build one.
Taking a value keeps `rules.py` pure and trivially testable but pushes "where
does the frame come from" into M3. Argue it, and make the signatures honest so M3
slots in without rework. Flag which bridge you intend for M3: a
`MarketDataProvider` port reference on the manager, ATR in `Signal.metadata`, or
a changed port.

**4. Order of operations, given M1.**

`risk_per_trade` sizing needs a stop price; an `rr` take-profit needs the stop
distance. Pin the sequence explicitly and make the signatures express it.

**5. Trailing stop is the only stateful rule.**

Decide whether `rules.py` mutates a `Position` or returns a level for the caller
to assign. A trailing stop must **never move against the position** — make that
monotonicity a property of the code, not a comment.

**6. Contradictory config.**

What happens when `take_profit.type == "rr"` but `stop_loss.enabled` is `False`?
There is no stop distance to multiply. Decide between a pydantic
`model_validator` on `RiskConfig` at load time and a runtime `ValueError`, and
justify it. Consider what other combinations are incoherent.

**7. Return shape.**

Bare `Decimal`s, or a frozen value object like `SizingDecision`? "No stop
configured" is a legitimate, expected outcome that must be representable — the
same problem M1 solved with a wrapper.

**8. Exit detection.**

Beyond computing levels, should M2 decide whether an open position *should* exit
at a given price? Decide whether that lives here or in M3, and whether it returns
a boolean or a richer "why" — an operator needs to know which rule fired.

---

## Tests

Hermetic unit tests in `tests/unit/test_risk_rules.py`. Exact `Decimal`
assertions, no float tolerance. Cover:

- percent and ATR stop-loss; percent and RR take-profit
- **directional rounding at awkward tick sizes**, including a case proving the
  stop distance never exceeds what sizing budgeted
- trailing-stop activation threshold, and that the trail **never moves against**
  the position across a sequence of prices
- the contradictory-config case(s)
- zero/negative price guards, and parameter validation raising `ValueError`
- that no result is ever built from a float — the `Money` guard should make this
  structural; show it, including `numpy.float64`
- **an integration-style unit test composing M2 with M1**: compute a stop, size
  from it, and assert realised risk at that stop is `<=` the `risk_per_trade`
  budget. This is the test that catches a rounding-direction mistake.

---

## Definition of done

- `pytest` → all green, no previously passing test broken
- `mypy` → zero
- `ruff check src tests` → zero
- Design was presented and confirmed **before** implementation
- Committed as its own commit, with the reasoning in the body

---

## After this: Phase 5 M3

`risk/manager.py` — limits, approval, portfolio state, the ATR data bridge, and
`on_signal` wiring into `TradingEngine`. This is also where
`RiskManager.approve`'s `portfolio` parameter finally gets typed, which will make
mypy flag its `# type: ignore` as unused and force its removal.
