"""Command-line overrides of a backtest's settings (R-BR), parsed and applied with the config's own checks.

The project owner's ruling R-BR, verbatim: *"Backtests take --stop-slippage and strategy, timeframe and
parameter overrides on the command line. Every effective setting is written into the run record and
into the candidate digest; a record without them is not evidence_eligible."*

**The file stays as committed.** The deployment procedure (``CLAUDE.md``) says to leave ``config.yaml`` as
committed at the pinned commit and launch from it; a modified or untracked config refuses. An override
changes what the run uses and not the bytes that were read, so the record names both: the file's digest,
and the ``effective`` block of :mod:`trading_bot.backtesting.candidate`.

**What each override does.**

* ``--stop-slippage PERCENT`` replaces ``backtesting.stop_slippage_percent``. It is the arm (R-B2).
* ``--strategy NAME`` replaces ``strategy.name`` **and drops the configured parameters**: they belong to
  the strategy being replaced, and laying them over another strategy would hand it names it does not take.
  The new strategy's parameters are exactly the ``--param`` values, and its defaults otherwise.
* ``--param KEY=VALUE`` (repeatable) sets one strategy parameter. Without ``--strategy`` it is laid over
  the configured parameters. The value is read as JSON when it is JSON (``20`` an integer, ``30.0`` a
  float, ``true`` a boolean) and as plain text otherwise.
* ``--timeframe TF`` sets every pair's timeframe. **If the config validator then refuses the staleness
  bound, it raises ``risk.max_position_staleness_s``** to ``(3 + k) x T`` seconds, ``T`` the timeframe and
  ``k = n - 1`` with ``n`` the smaller of ``max_open_positions`` and the number of enabled pairs: the
  round value the validator itself recommends. The committed bound of 180 s passes only because the
  shortest timeframe is 1m; it is refused at 5m and above (``M5m-314``, measured). A backtest stamps every
  open position on every bar, so the bound never acts there; the validator still insists on it, and a
  raised value is in the record's ``effective`` block. A config the validator accepts is left as it is.

**Everything is validated before a run directory exists.** The strategy is constructed once (an unknown
name or parameter is refused with the registry's own message), a non-integer for a parameter declared
``int`` is refused (``M5m-315``), and the whole config is re-validated through ``AppConfig``, so an
override that the committed config's checks would refuse is refused here.
"""

from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final

from pydantic import ValidationError

from trading_bot.backtesting.candidate import canonical_value
from trading_bot.config.models import AppConfig
from trading_bot.core.exceptions import ConfigError, StrategyError
from trading_bot.utils.helpers import timeframe_to_ms

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

__all__ = [
    "Overrides",
    "apply_overrides",
    "build_overrides",
    "parse_param",
    "parse_percent",
]

_KEY: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class Overrides:
    """What the command line changed. ``None`` and an empty tuple mean "not given"."""

    stop_slippage: Decimal | None = None
    strategy: str | None = None
    timeframe: str | None = None
    params: tuple[tuple[str, object], ...] = ()

    @property
    def is_empty(self) -> bool:
        return (
            self.stop_slippage is None
            and self.strategy is None
            and self.timeframe is None
            and not self.params
        )

    def record(self) -> dict[str, object]:
        """The overrides as given, in the form the run record keeps; only what was given."""
        out: dict[str, object] = {}
        if self.stop_slippage is not None:
            out["stop_slippage_percent"] = canonical_value(self.stop_slippage)
        if self.strategy is not None:
            out["strategy"] = self.strategy
        if self.timeframe is not None:
            out["timeframe"] = self.timeframe
        if self.params:
            out["params"] = {key: canonical_value(value) for key, value in self.params}
        return out


def parse_percent(text: str) -> Decimal:
    """``text`` as a non-negative, finite percentage, exactly (no float).

    :raises ConfigError: it is not a number, not finite, or negative.
    """
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ConfigError(f"--stop-slippage {text!r} is not a number") from None
    if not value.is_finite() or value < 0:
        raise ConfigError(f"--stop-slippage {text!r} must be a finite number of at least 0")
    return value


def parse_param(text: str) -> tuple[str, object]:
    """``KEY=VALUE`` as a key and a value; the value is JSON if it parses as a scalar, else text.

    :raises ConfigError: there is no ``=``, the key is not an identifier, the value is empty, or
        the value is a JSON object, array or ``null``.
    """
    key, separator, raw = text.partition("=")
    if not separator or not _KEY.match(key):
        raise ConfigError(f"--param {text!r} is not KEY=VALUE with an identifier for KEY")
    if raw == "":
        raise ConfigError(f"--param {key} has no value")
    try:
        value: object = json.loads(raw)
    except ValueError:
        return key, raw
    if value is None or isinstance(value, (dict, list)):
        raise ConfigError(f"--param {key} takes a number, a boolean or text, not {raw!r}")
    return key, value


def build_overrides(
    *,
    stop_slippage: Decimal | None = None,
    strategy: str | None = None,
    timeframe: str | None = None,
    params: Sequence[str] | None = None,
) -> Overrides:
    """The overrides a command line gave, with each ``--param`` parsed.

    :raises ConfigError: a ``--param`` is malformed or names one key twice.
    """
    parsed: list[tuple[str, object]] = []
    seen: set[str] = set()
    for text in params or ():
        key, value = parse_param(text)
        if key in seen:
            raise ConfigError(f"--param {key} is given twice")
        seen.add(key)
        parsed.append((key, value))
    return Overrides(
        stop_slippage=stop_slippage,
        strategy=strategy,
        timeframe=timeframe,
        params=tuple(parsed),
    )


def _staleness_bound_s(config: AppConfig, timeframe: str) -> int:
    """``(3 + k) x T`` seconds, ``T`` the one timeframe every pair now has: the validator's round value."""
    n = min(config.risk.limits.max_open_positions, len(config.trading.enabled_pairs))
    return (3 + max(n - 1, 0)) * (timeframe_to_ms(timeframe) // 1000)


def apply_overrides(config: AppConfig, overrides: Overrides) -> AppConfig:
    """``config`` with ``overrides`` laid over it, re-validated whole.

    :raises ConfigError: the timeframe is unknown, the strategy or a parameter is refused by the
        registry, or the result fails the config's own validation.
    """
    if overrides.is_empty:
        return config
    data = config.model_dump()
    if overrides.strategy is not None or overrides.params:
        strategy = dict(data["strategy"])
        params: dict[str, object] = (
            {} if overrides.strategy is not None else dict(strategy["params"])
        )
        params.update(dict(overrides.params))
        if overrides.strategy is not None:
            strategy["name"] = overrides.strategy
        strategy["params"] = params
        data["strategy"] = strategy
    if overrides.timeframe is not None:
        try:
            timeframe_to_ms(overrides.timeframe)
        except ValueError as exc:
            raise ConfigError(
                f"--timeframe {overrides.timeframe!r} is not a timeframe: {exc}"
            ) from exc
        for pair in data["trading"]["pairs"]:
            pair["timeframe"] = overrides.timeframe
    if overrides.stop_slippage is not None:
        backtesting = dict(data["backtesting"])
        backtesting["stop_slippage_percent"] = overrides.stop_slippage
        data["backtesting"] = backtesting
    effective = _validated(data, config, overrides.timeframe)
    _require_buildable(effective)
    return effective


def _validated(data: dict[str, Any], config: AppConfig, timeframe: str | None) -> AppConfig:
    """``data`` through ``AppConfig``; if only the staleness bound refuses it, raised and tried again.

    The bound is raised ONLY when a timeframe override was given and the validator's own message names
    ``max_position_staleness_s``: a config the validator accepts (1m, say) is left as committed.
    """
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        if timeframe is None or "max_position_staleness_s" not in str(exc):
            raise ConfigError(f"The overrides give an invalid config: {exc}") from exc
    needed = float(_staleness_bound_s(config, timeframe))
    data["risk"]["max_position_staleness_s"] = max(
        float(data["risk"]["max_position_staleness_s"]), needed
    )
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"The overrides give an invalid config: {exc}") from exc


def _require_buildable(effective: AppConfig) -> None:
    """Build the strategy once, and refuse a non-integer for a parameter declared ``int``.

    The second check is not the registry's: a float period such as ``fast_period=4.0`` PASSES the
    constructor and then raises ``TypeError`` on every bar, which the engine isolates, counts and
    quarantines after five, so the run would finish having traded nothing (``M5m-315``, measured).
    """
    from trading_bot.strategies.registry import create_strategy

    try:
        strategy = create_strategy(effective.strategy.name, **effective.strategy.params)
    except (StrategyError, ValueError, TypeError) as exc:
        raise ConfigError(f"The overrides give a strategy that cannot be built: {exc}") from exc
    declared = inspect.signature(type(strategy)).parameters
    for key, value in effective.strategy.params.items():
        parameter = declared.get(key)
        if parameter is None or parameter.annotation not in ("int", int):
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(
                f"{key} is an integer parameter of {effective.strategy.name!r} and {value!r} is not "
                "an integer; write it without a decimal point"
            )
