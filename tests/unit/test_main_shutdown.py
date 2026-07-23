"""Tests for the CLI's signal wiring — including the Windows fallback.

``loop.add_signal_handler`` is POSIX-only, so on Windows the CLI falls back to
``signal.signal``. That branch cannot be reached on a POSIX test runner
naturally, so the loop method is patched to raise ``NotImplementedError`` and
the fallback is asserted directly. This matters because the two paths are not
interchangeable: without the fallback, Windows shuts down via task cancellation,
and a second Ctrl-C arriving mid-cleanup aborts the close of the WebSocket and
REST connections.
"""

from __future__ import annotations

import asyncio
import signal
from typing import Any

import pytest

from trading_bot.main import _install_shutdown_handlers


class SpyEngine:
    """Stands in for TradingEngine; records graceful-stop requests."""

    def __init__(self) -> None:
        self.stop_requests = 0

    def request_stop(self) -> None:
        self.stop_requests += 1


async def test_posix_path_uses_the_loop_signal_handler() -> None:
    engine = SpyEngine()
    loop = asyncio.get_running_loop()
    installed: list[Any] = []
    original = loop.add_signal_handler

    def record(sig: Any, callback: Any, *args: Any) -> None:
        installed.append((sig, callback, args))

    loop.add_signal_handler = record  # type: ignore[method-assign]
    try:
        _install_shutdown_handlers(engine)  # type: ignore[arg-type]
    finally:
        loop.add_signal_handler = original  # type: ignore[method-assign]

    assert [entry[0] for entry in installed] == [signal.SIGINT, signal.SIGTERM]
    # The callback runs on the loop, so logging inside it is safe.
    for _sig, callback, args in installed:
        callback(*args)
    assert engine.stop_requests == 2


async def test_windows_fallback_installs_a_plain_signal_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the loop refuses, a signal.signal handler must take over."""
    engine = SpyEngine()
    loop = asyncio.get_running_loop()

    def unsupported(*args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Windows")

    handlers: dict[Any, Any] = {}

    def fake_signal(sig: Any, handler: Any) -> Any:
        handlers[sig] = handler
        return None

    monkeypatch.setattr(loop, "add_signal_handler", unsupported)
    monkeypatch.setattr(signal, "signal", fake_signal)

    _install_shutdown_handlers(engine)  # type: ignore[arg-type]

    assert set(handlers) == {signal.SIGINT, signal.SIGTERM}

    # Firing the handler must not touch the engine synchronously: it schedules
    # onto the loop, which is what makes it safe from a signal context.
    handlers[signal.SIGINT](signal.SIGINT, None)
    assert engine.stop_requests == 0
    await asyncio.sleep(0)  # let the scheduled callback run
    assert engine.stop_requests == 1


async def test_windows_fallback_survives_a_non_main_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """signal.signal() raises off the main thread; startup must not fail."""
    engine = SpyEngine()
    loop = asyncio.get_running_loop()

    def unsupported(*args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Windows")

    def refuses(sig: Any, handler: Any) -> Any:
        raise ValueError("signal only works in main thread")

    monkeypatch.setattr(loop, "add_signal_handler", unsupported)
    monkeypatch.setattr(signal, "signal", refuses)

    _install_shutdown_handlers(engine)  # type: ignore[arg-type]  # must not raise
