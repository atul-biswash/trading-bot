# Binance Spot Trading Bot

Production-grade automated Binance Spot trading bot in Python. **Treat this as
software that will eventually manage real money.** Every design decision
prioritises correctness, safety and robustness over speed of development.

Detailed build history: `docs/PHASE_HISTORY.md`
Current task: `docs/NEXT_MILESTONE.md`

---

## Working method — non-negotiable

1. **One milestone at a time.** Finish and verify before moving on. If a task is
   too large, split it and do the first part only.
2. **Design before code.** Explain the approach, why it was chosen, and the
   alternatives — then stop and wait for my confirmation before implementing.
   If you see a better architecture than the one I proposed, say so first.
3. **Verify empirically.** Introspect the real code before relying on any API,
   shape or contract. Never assume a signature. Confirm the green baseline
   *before* changing anything.
4. **Never skip testing. Never trade code quality for speed.**
5. End every milestone with: summary of work, next recommended step, potential
   improvements — then stop for confirmation.

Standards: Clean Architecture, SOLID, DRY, KISS, PEP 8, full type hints, proper
exception handling. No hardcoded secrets — `.env` for secrets, `config.yaml` for
behaviour.

---

## The money rule — the single most important invariant

**Money is `Decimal` in the domain, never `float`.** Enforced, not documented:

```python
Money = Annotated[Decimal, BeforeValidator(_reject_float)]   # core/models.py
```

Every price, quantity and balance field uses it. Constructing one from a `float`
raises `ValidationError`. `numpy.float64` is caught by the same check — it is a
`float` subclass and is what `DataFrame.iloc` returns, which is the realistic
leak path. `int` and `str` pass through because both convert exactly.

`Decimal * float` raises `TypeError`, so any config value used in money
arithmetic needs a deliberate conversion boundary.

**There is exactly one `Decimal`→`float` boundary**, in the data layer:
`BufferedMarketDataProvider.get_dataframe()` produces float64 OHLCV because
indicator maths runs on NumPy. `last_candle()` returns full `Decimal` precision.
Anything needing a price takes it from the candle, never the frame.

**The reverse boundary (`float`→`Decimal`) is config load**, done once by
pydantic. Rule: *a config field becomes `Decimal` at the milestone that first
multiplies it by money.* Never scatter `Decimal(str(x))` through business logic.
Note the deliberate asymmetry: config is where a float is *allowed* to become a
Decimal; the domain is where it is forbidden.

---

## Architecture

Clean Architecture. `core/` holds domain models and abstract ports; outer layers
implement them and depend inward only.

```
src/trading_bot/
  core/          models · enums · interfaces (ports) · exceptions
  config/        settings · pydantic config models
  exchange/      base · binance_client · models (mappers) · websocket_client
  data/          market_data · historical · repository
  indicators/    hand-written TA functions
  strategies/    base · registry · helpers · examples/
  engine/        live_engine · modes
  risk/          manager · rules · position_sizing
  backtesting/   engine · portfolio · metrics
  paper/         simulator
  persistence/   database · models
  notifications/ base · telegram
  utils/         logger · helpers
```

### Key seams

- **`MarketDataProvider`** — `get_dataframe(symbol, timeframe)` (float64 OHLCV,
  tz-aware UTC `DatetimeIndex` named `open_time`), `last_candle` (Decimal),
  `is_ready`, `on_candle`. It **appends before it notifies**, so a candle handed
  to a subscriber is already `buffer[-1]`.
- **`Strategy.generate_signal(symbol, candles, *, last_candle: Candle)`** — the
  frame is for indicator maths; `last_candle` is the only admissible source for
  `Signal.price` and `Signal.timestamp`.
- **`TradingEngine.on_signal(handler)`** — where risk and execution attach. The
  engine does **not** enrich signals; a signal leaves the strategy complete, so
  backtest and live share one code path.

---

## Locked decisions — do not re-litigate without an explicit reason

**Domain**
- Value objects are **frozen** pydantic models; `Position` is mutable by design.
- `core/` imports pandas only under `TYPE_CHECKING`. Outer layers import normally.
- `SignalAction` is `BUY | SELL | CLOSE`. **There is no `HOLD`** —
  `generate_signal` returning `None` is the only "no opinion". `SELL` means "open
  a short" and is unreachable on spot, so strategies emit `BUY`/`CLOSE` only.

**Strategies**
- **Edge-triggered, not level-triggered.** A cross fires on the transition bar
  and is silent while the condition persists, or execution places a duplicate
  order every bar.
- **Stateless recomputation** from the buffer, never state on `self`. Identical
  after a restart, after a reconnect re-delivers a corrected bar, and in backtest.
- `warmup_period` is **derived from the indicator NaN contract**, never guessed.
  Indicators express warmup as leading `NaN` — never zero, never back-filled.
- **Insufficient data is not an error.** Short input returns all-`NaN` / `None`;
  raising would count toward the engine's quarantine and disable a pair that
  only needed more candles.
- `strength` stays `1.0` unless there is a defensible measure. A fabricated
  confidence that a later layer might multiply a position size by is worse than
  an honest constant; diagnostics go in `metadata` instead.
- `metadata` values must be plain `int`/`float`/`str` — it gets persisted, and
  NumPy scalars leak into logs and break serialisation.

**Risk**
- Rounding **down** to `step_size` for quantities (`ROUND_DOWN`). Rounding up can
  overspend a balance and get the order rejected — or filled.
- Exchange filters are applied **in sizing**, not deferred to execution:
  `BinanceClient._enforce` signals violations by *raising*, and "too small to
  trade" is routine, not exceptional. `_enforce` stays as an independent last
  line of defence.
- "No trade" is a **frozen value object carrying its reason**, never a bare
  `Decimal(0)`, `None`, or an exception. See `SizingDecision`.
- `equity` means **total portfolio value in quote currency**, not free balance.

**Dependencies**
- **`python-binance`**, not the official Binance connector — built-in Testnet
  support, mature async/websocket managers, order helpers.
- **`pandas-ta` is NOT used and must not be reintroduced.** The 0.3.x line was
  pulled from PyPI; 0.4.x forces a heavyweight `numba`/LLVM dependency plus
  pinned NumPy/pandas — fragile for software that manages money. Indicators are
  small hand-written unit-tested functions in `indicators/`.
- `requirements.txt` is the single runtime dependency source; dev tools in
  `requirements-dev.txt`.

**Style**
- `timezone.utc` — do **not** switch to the `datetime.UTC` alias (`UP017` is
  suppressed project-wide for this reason).
- Enums are `str, Enum`, not `StrEnum` (`UP042` suppressed deliberately:
  `StrEnum` changes `str(member)` from `"OrderSide.BUY"` to `"BUY"`, which would
  alter logs and persisted strings).
- No quoted annotations in new code (files carry `from __future__ import annotations`).
- New exception classes end in `Error`. `zip()` always takes `strict=`. Never
  use `l` as a variable name.
- **All files are LF**, pinned by `.gitattributes`. Write LF.
- `# fmt: off` / `# fmt: on` fences hand-laid data tables in tests. It only works
  at **statement boundaries** — it does *not* protect a table inside a
  `@pytest.mark.parametrize` argument list. Define such tables at module level
  and reference them from `parametrize`.

**Config & safety**
- **Testnet is the default everywhere.** Live trading requires explicit
  confirmation. Every example defaults to Testnet.

---

## Quality gates — hard zero

```bash
pytest                      # 373 passed  (370 unit + 3 opt-in Testnet integration)
pytest -m "not integration" # 370 passed  — use this for fast iteration
mypy                        # Success: no issues found in 54 source files
ruff check src tests        # All checks passed!
make check                  # all three
```

**mypy and ruff must report ZERO.** This is a hard gate, not a baseline to diff
against. Any new finding is a regression.

Do **not** reach zero by adding `noqa` or `type: ignore`. Fix the code. If a
suppression is genuinely warranted, make it *self-removing* and justify it in a
comment — e.g. `RiskManager.approve` carries
`# type: ignore[no-untyped-def]` and `warn_unused_ignores` is enabled, so mypy
will force its deletion the moment the parameter is typed.

The 3 integration tests are read-only against Binance **Testnet**, never place an
order, and are gated by `tests/integration/credentials.py` (which reads through
`Secrets()`, so `.env` works — not just environment variables).

---

## Testing style

Unit tests are hermetic: no network, no real time, scripted fakes, injectable
seams, injected `sleep`. `asyncio_mode=auto`. Exact `Decimal` assertions in money
code — no float tolerance, because a result that is merely *close* is a bug and a
tolerant test cannot detect the float leak the domain exists to prevent.

---

## Git workflow

Commit at each verified milestone, never mid-milestone. Before committing, all
three gates must be green. Write the *why* in the commit body, not just the what.

I review via `git diff` — so keep mechanical changes (formatting, line endings,
renames) in **separate commits** from semantic ones. Never mix them.

---

## Current state

Phases 1–4 complete. Phase 5 M1 (position sizing) complete. Tooling cleanup
complete. See `docs/NEXT_MILESTONE.md` for what is in flight.
