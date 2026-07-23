"""Strategy registry — an Open/Closed factory.

New strategies register themselves with the ``@register_strategy("name")``
decorator; selecting one at runtime is just a name lookup driven by
``strategy.name`` in config.yaml. Adding a strategy therefore requires no
changes to the engine (Open for extension, closed for modification).
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from trading_bot.core.exceptions import StrategyConfigError, StrategyNotFoundError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from trading_bot.strategies.base import BaseStrategy

_REGISTRY: dict[str, type["BaseStrategy"]] = {}


def register_strategy(name: str):
    """Class decorator that registers a strategy under ``name``."""

    def decorator(cls: type["BaseStrategy"]) -> type["BaseStrategy"]:
        key = name.lower()
        if key in _REGISTRY:
            raise ValueError(f"Strategy already registered: {name!r}")
        cls.name = name
        _REGISTRY[key] = cls
        return cls

    return decorator


def create_strategy(name: str, **params: Any) -> "BaseStrategy":
    """Instantiate the strategy registered under ``name`` with ``params``."""
    # Import examples so their decorators run and populate the registry.
    from trading_bot.strategies import examples  # noqa: F401

    cls = _REGISTRY.get(name.lower())
    if cls is None:
        available = ", ".join(sorted(_REGISTRY)) or "(none)"
        raise StrategyNotFoundError(f"Unknown strategy {name!r}. Registered: {available}")

    # Check the parameter *names* against the constructor before calling it. A
    # typo in config.yaml would otherwise surface as a bare
    # "__init__() got an unexpected keyword argument 'fast_perio'", which says
    # nothing about which strategy or what it would have accepted. Binding
    # rather than catching around the call keeps the two failures distinct: a
    # TypeError raised *inside* a constructor is a bug and still propagates.
    try:
        inspect.signature(cls).bind(**params)
    except TypeError as exc:
        accepted = ", ".join(_accepted_params(cls)) or "(none)"
        raise StrategyConfigError(
            f"Strategy {name!r} cannot accept the parameters configured for it "
            f"({exc}). Accepted parameters: {accepted}"
        ) from exc

    return cls(**params)


def _accepted_params(cls: type[BaseStrategy]) -> list[str]:
    """The keyword parameter names ``cls`` accepts, for error messages."""
    keyword_kinds = (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )
    return [
        parameter_name
        for parameter_name, parameter in inspect.signature(cls).parameters.items()
        if parameter.kind in keyword_kinds
    ]


def available_strategies() -> list[str]:
    from trading_bot.strategies import examples  # noqa: F401

    return sorted(_REGISTRY)
