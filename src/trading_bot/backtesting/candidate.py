"""The effective settings of a backtest run, and the digests that name a candidate (R-BR).

The project owner's ruling R-BR, verbatim: *"Backtests take --stop-slippage and strategy, timeframe and
parameter overrides on the command line. Every effective setting is written into the run record and
into the candidate digest; a record without them is not evidence_eligible."*

**Why a block of its own.** A run is named by the config FILE it read (its digest is in the record) and
by what the command line then changed. Two runs of one file can be different candidates, so the file's
digest alone no longer says which one a record is. :func:`effective_settings` is what the run actually
used, after every override, in a form that does not depend on how it was reached: the same strategy,
parameters, pairs, costs and risk bound give the same block whether they came from a file or from flags.

**Two digests, and why two.** ``candidate_digest`` names the CANDIDATE: the config file's digest, the
strategy and its parameters, the pairs and their timeframes, the risk bound, the stored-``exchangeInfo``
environment and every cost **except the stop-slippage arm**. ``settings_digest`` covers every effective
setting including the arm. A candidate is reported at three arms (R-B2) and read out of sample once, so the
guard binds an entry to the first and the record carries both. This split is the implementer's reading of
*"the candidate digest"* and is stated here so the owner can overrule it.

**What neither digest covers:** the window (it is the record's ``window`` block, and the guard judges it),
and ``overrides`` (how the settings were reached, kept in the block for the reader and left out of both
digests so that two routes to one set of settings agree).

**Numbers are canonical.** ``30``, ``30.0`` and ``Decimal("30")`` are one value and print as ``30``; a
digest that depended on how a grid value was typed would make one candidate two.

Pure: no file, no clock, no network.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from trading_bot.core.exceptions import TradingBotError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.config.models import AppConfig, BacktestConfig

__all__ = [
    "ARM_FIELD",
    "EffectiveSettingsError",
    "candidate_arm",
    "candidate_digest",
    "canonical_number",
    "canonical_value",
    "check_record_digests",
    "effective_settings",
    "settings_digest",
]

#: The cost that is the arm, left out of ``candidate_digest`` and named by the record's arm.
ARM_FIELD: Final = "stop_slippage_percent"

_CANDIDATE_KEYS: Final = ("config_sha256", "strategy", "pairs", "risk", "exchange_info_environment")
_COST_KEYS: Final = ("fee_percent", "slippage_percent", ARM_FIELD, "initial_balance")


class EffectiveSettingsError(TradingBotError):
    """An effective-settings block is malformed, or does not match the digests a record carries."""


def canonical_number(value: object) -> str:
    """A finite number as the shortest plain decimal string; ``30``, ``30.0`` and ``3E+1`` are ``30``."""
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    if not number.is_finite():
        raise EffectiveSettingsError(f"{value!r} is not a finite number")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def canonical_value(value: object) -> object:
    """``value`` in the form a digest reads: numbers as plain strings, containers recursed.

    ``bool`` is tested before the numbers (it is an ``int``), so ``True`` stays ``True`` and is never
    read as ``1``.

    :raises EffectiveSettingsError: a value of a type a strategy parameter cannot be, or a non-finite
        number.
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float, Decimal)):
        return canonical_number(value)
    if isinstance(value, Mapping):
        return {str(key): canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    raise EffectiveSettingsError(f"{type(value).__name__} cannot be part of the effective settings")


def effective_settings(
    config: AppConfig,
    window: BacktestConfig,
    pairs: Sequence[tuple[str, str]],
    *,
    config_sha256: str | None,
    overrides: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """What a run used, after every override, as a JSON-ready block.

    :param config: the effective config (the file's, with any overrides applied).
    :param window: the resolved window and costs; only its costs and environment are read.
    :param pairs: the ``(symbol, timeframe)`` pairs the run replays, in the order it replays them.
    :param config_sha256: the digest of the file that was read, or ``None`` if unknown.
    :param overrides: the overrides as the command gave them, kept for the reader.
    """
    return {
        "config_sha256": config_sha256,
        "strategy": {
            "name": config.strategy.name,
            "params": {
                key: canonical_value(config.strategy.params[key])
                for key in sorted(config.strategy.params)
            },
        },
        "pairs": [{"symbol": symbol, "timeframe": timeframe} for symbol, timeframe in pairs],
        "risk": {"max_position_staleness_s": canonical_value(config.risk.max_position_staleness_s)},
        "exchange_info_environment": window.exchange_info_environment,
        "costs": {
            "fee_percent": canonical_number(window.fee_percent),
            "slippage_percent": canonical_number(window.slippage_percent),
            ARM_FIELD: canonical_number(window.stop_slippage_percent),
            "initial_balance": canonical_number(window.initial_balance),
        },
        "overrides": canonical_value(dict(overrides or {})),
    }


def _digest(payload: Mapping[str, object]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _costs_of(effective: Mapping[str, object]) -> Mapping[str, object]:
    costs = effective.get("costs")
    if not isinstance(costs, Mapping) or any(key not in costs for key in _COST_KEYS):
        raise EffectiveSettingsError(
            f"the effective settings carry no complete costs block: {costs!r}"
        )
    return costs


def _require_keys(effective: Mapping[str, object]) -> None:
    missing = [key for key in (*_CANDIDATE_KEYS, "costs") if key not in effective]
    if missing:
        raise EffectiveSettingsError(f"the effective settings lack {', '.join(missing)}")


def candidate_arm(effective: Mapping[str, object]) -> str:
    """The stop-slippage arm of a run, as the canonical string the block holds (``"1.2"`` for 1.20%)."""
    _require_keys(effective)
    return str(_costs_of(effective)[ARM_FIELD])


def candidate_digest(effective: Mapping[str, object]) -> str:
    """The SHA-256 naming the candidate: every effective setting except the stop-slippage arm."""
    _require_keys(effective)
    costs = {key: value for key, value in _costs_of(effective).items() if key != ARM_FIELD}
    payload = {key: effective[key] for key in _CANDIDATE_KEYS}
    payload["costs"] = costs
    return _digest(payload)


def settings_digest(effective: Mapping[str, object]) -> str:
    """The SHA-256 of every effective setting, the arm included; ``overrides`` is left out."""
    _require_keys(effective)
    _costs_of(effective)
    return _digest({key: value for key, value in effective.items() if key != "overrides"})


def check_record_digests(record: Mapping[str, object]) -> None:
    """Refuse a run record whose effective block is absent or does not match its digests.

    :raises EffectiveSettingsError: the record has no ``effective`` block, or no digest, or a digest
        that is not the one the block gives (a record edited after it was written).
    """
    effective = record.get("effective")
    if not isinstance(effective, Mapping):
        raise EffectiveSettingsError("the record carries no effective settings")
    for name, compute in (
        ("candidate_digest", candidate_digest),
        ("settings_digest", settings_digest),
    ):
        stored = record.get(name)
        if not isinstance(stored, str):
            raise EffectiveSettingsError(f"the record carries no {name}")
        if stored != compute(effective):
            raise EffectiveSettingsError(
                f"the record's {name} is not the digest of its effective settings"
            )
