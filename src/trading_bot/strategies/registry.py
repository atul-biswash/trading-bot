"""Strategy registry — an Open/Closed factory.

New strategies register themselves with the ``@register_strategy("name")``
decorator; selecting one at runtime is just a name lookup driven by
``strategy.name`` in config.yaml. Adding a strategy therefore requires no
changes to the engine (Open for extension, closed for modification).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from trading_bot.core.exceptions import StrategyNotFoundError

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
        raise StrategyNotFoundError(
            f"Unknown strategy {name!r}. Registered: {available}"
        )
    return cls(**params)


def available_strategies() -> list[str]:
    from trading_bot.strategies import examples  # noqa: F401

    return sorted(_REGISTRY)
