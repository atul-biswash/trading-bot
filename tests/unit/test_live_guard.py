"""The live-trading guard: every route to LIVE is refused, and nothing else is.

CLAUDE.md, Config & safety: live trading is BLOCKED until entry-fee deduction and
base-quantity netting are implemented. The owner ruled its enforcement at M5k,
and this file pins it:

* the four routes to LIVE -- ``config.yaml``, ``BOT_MODE``, ``run --mode live``
  and ``check_testnet.py --mode live`` -- each tested SEPARATELY, because a
  guard on one route passes a test of another;
* the credential backstop in ``Settings.binance_credentials``, which holds even
  if every entry-point check were deleted;
* TESTNET, PAPER and BACKTEST are NOT refused;
* ruling 2: PAPER and BACKTEST hold no exchange credentials, and TESTNET never
  falls back to the live slots.

**NO CLIENT IS EVER CONSTRUCTED.** The autouse ``constructors`` fixture
replaces ``binance.AsyncClient.create`` and ``BinanceClient.create`` with
recorders that raise, so a guard that fails open fails the test instead of
connecting -- and the fixture asserts on teardown that neither was reached.

**EXPRESSIVENESS FIRST.** Every refusal test first shows that its route ALONE
resolves the mode it claims, so a refusal caused by something else -- an
unparseable config, a missing key -- cannot pass for the guard.

**M5i-115 applies to every ``pytest.raises`` here:** an unmet ``raises`` reports
``Failed``, not ``AssertionError``, and that is what a kill looks like.
"""

from __future__ import annotations

import inspect
import logging
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import trading_bot.main as cli
from trading_bot.config.settings import (
    LIVE_TRADING_BLOCKED_MESSAGE,
    Settings,
    _load_yaml_config,
    get_settings,
    refuse_live_trading,
)
from trading_bot.core.enums import TradingMode
from trading_bot.core.exceptions import ConfigError, LiveTradingBlockedError
from trading_bot.exchange.binance_client import BinanceClient

# `scripts/` is not a package and is outside `pythonpath`, so it is added here
# rather than restructured -- the script is a script, not library code.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_testnet

_REPO = Path(__file__).resolve().parents[2]

#: The owner's text, written here INDEPENDENTLY of the constant it checks, so an
#: edit to the constant is a failure rather than a self-comparison.
_OWNER_TEXT = (
    "FATAL: Live trading is blocked by architectural invariant (CLAUDE.md).\n"
    "Base-denominated entry fee netting is unmodeled in position sizing and order "
    "list generation.\n"
    "Startup refused."
)

#: Distinctive values in the LIVE slots. Their absence from any return value or
#: exception text is what separates "no fallback" from "a fallback that
#: happened to be refused later".
_LIVE_KEY = "LIVE-SLOT-KEY-SENTINEL-must-never-be-read"
_LIVE_SECRET = "LIVE-SLOT-SECRET-SENTINEL-must-never-be-read"

#: Environment variables a reader might expect to unlock live. None exists in
#: the tree; setting them all is how "no bypass" is tested as far as a finite
#: test can test it -- the signature test below pins the rest structurally.
_PLAUSIBLE_BYPASSES = (
    "CONFIRM_LIVE",
    "ALLOW_LIVE",
    "BOT_ALLOW_LIVE",
    "TRADING_BOT_ALLOW_LIVE",
    "LIVE_TRADING_ENABLED",
)

_CONFIG = """\
mode: {mode}
strategy:
  name: sma_crossover
  params:
    fast_period: 10
    slow_period: 30
backtesting:
  start_date: "2024-01-01"
  end_date: "2024-02-01"
  initial_balance: 5000
logging:
  console: false
  file:
    enabled: false
"""

#: The real constructor, bound before any fixture replaces it, so the backstop
#: test can drive it while `binance.AsyncClient.create` stays a recorder.
_REAL_BINANCE_CLIENT_CREATE = BinanceClient.create


class _ConstructorReachedError(AssertionError):
    """A client constructor was called; the guard failed open."""


class _RecordingSecrets:
    """A ``Secrets`` stand-in that records every key slot READ.

    ``Settings`` reads ``bot_mode`` and the four slots by attribute, so a
    duck-typed object is enough, and recording the reads is what lets a test
    assert that a refusal came BEFORE any slot was touched -- which a return
    value or an exception cannot show.
    """

    def __init__(
        self,
        *,
        bot_mode: TradingMode,
        testnet_key: str = "",
        testnet_secret: str = "",
        live_key: str = "",
        live_secret: str = "",
    ) -> None:
        self.bot_mode = bot_mode
        self.slots = {
            "binance_testnet_api_key": testnet_key,
            "binance_testnet_api_secret": testnet_secret,
            "binance_api_key": live_key,
            "binance_api_secret": live_secret,
        }
        self.reads: list[str] = []

    def _read(self, name: str) -> str:
        self.reads.append(name)
        return self.slots[name]

    @property
    def binance_testnet_api_key(self) -> str:
        return self._read("binance_testnet_api_key")

    @property
    def binance_testnet_api_secret(self) -> str:
        return self._read("binance_testnet_api_secret")

    @property
    def binance_api_key(self) -> str:
        return self._read("binance_api_key")

    @property
    def binance_api_secret(self) -> str:
        return self._read("binance_api_secret")


def _config(tmp_path: Path, mode: str) -> Path:
    path = tmp_path / f"config_{mode}.yaml"
    path.write_text(_CONFIG.format(mode=mode), encoding="utf-8")
    return path


def _settings(config_path: Path, secrets: _RecordingSecrets) -> Settings:
    return Settings(_load_yaml_config(config_path), secrets)


@pytest.fixture(autouse=True)
def constructors(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Replace both client constructors with recorders that fail if called."""
    from binance import AsyncClient

    reached: list[str] = []

    async def _async_client_create(*_args: Any, **_kwargs: Any) -> Any:
        reached.append("binance.AsyncClient.create")
        raise _ConstructorReachedError("binance.AsyncClient.create was called")

    async def _binance_client_create(*_args: Any, **_kwargs: Any) -> Any:
        reached.append("BinanceClient.create")
        raise _ConstructorReachedError("BinanceClient.create was called")

    monkeypatch.setattr(AsyncClient, "create", _async_client_create)
    monkeypatch.setattr(BinanceClient, "create", _binance_client_create)
    yield reached
    assert reached == [], f"a client constructor was reached: {reached}"


@pytest.fixture
def logging_setup(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record ``setup_logging`` calls instead of reconfiguring the root logger.

    Two jobs. It keeps ``main`` from replacing the root handlers pytest's log
    capture depends on, and it lets a test assert that a refusal happened
    BEFORE logging was set up -- a refused start opens no log file.
    """
    calls: list[object] = []
    monkeypatch.setattr(cli, "setup_logging", calls.append)
    return calls


# --------------------------------------------------------------------------
# The message
# --------------------------------------------------------------------------
def test_the_message_is_the_owners_text_exactly() -> None:
    """Ruling 3's text, byte for byte, with "permanently" gone.

    MUTATION: any edit to ``LIVE_TRADING_BLOCKED_MESSAGE``. To survive, a
    mutant would have to leave the text byte-identical, which is no mutation.
    """
    assert LIVE_TRADING_BLOCKED_MESSAGE == _OWNER_TEXT
    assert "permanently" not in LIVE_TRADING_BLOCKED_MESSAGE
    assert not LIVE_TRADING_BLOCKED_MESSAGE.endswith("\n")


# --------------------------------------------------------------------------
# Each route to LIVE, separately
# --------------------------------------------------------------------------
def test_config_yaml_live_is_refused_at_startup(
    tmp_path: Path, logging_setup: list[object]
) -> None:
    """Route A: ``mode: live`` in ``config.yaml``, and nothing else.

    MUTATION: delete ``main``'s pre-dispatch guard, or move it below
    ``setup_logging``. ``strategies`` builds no client and reads no key, so
    neither the ``--mode`` guard nor the credential backstop can stand in:
    only the pre-dispatch guard refuses here, and only before logging.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    path = _config(tmp_path, "live")
    assert "BOT_MODE" not in os.environ
    assert get_settings(str(path)).mode is TradingMode.LIVE

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--config", str(path), "strategies"])

    assert exit_info.value.code == _OWNER_TEXT
    assert logging_setup == []


def test_bot_mode_live_is_refused_at_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logging_setup: list[object]
) -> None:
    """Route B: ``BOT_MODE=live`` over a config that says testnet.

    MUTATION: key the guard on ``settings.config.mode`` rather than the
    RESOLVED ``settings.mode``. The config alone says TESTNET here, so only a
    guard that reads the resolved mode refuses.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    path = _config(tmp_path, "testnet")
    assert _load_yaml_config(path).mode is TradingMode.TESTNET
    monkeypatch.setenv("BOT_MODE", "live")
    assert get_settings(str(path)).mode is TradingMode.LIVE

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--config", str(path), "strategies"])

    assert exit_info.value.code == _OWNER_TEXT
    assert logging_setup == []


def test_cli_mode_live_is_refused_at_startup(
    tmp_path: Path, logging_setup: list[object], caplog: pytest.LogCaptureFixture
) -> None:
    """Route C: ``run --mode live`` over a config and environment of testnet.

    MUTATION: delete the guard in ``_cmd_run``. The credential backstop would
    still refuse -- ``_cmd_run`` reads credentials for LIVE -- so the exit alone
    cannot see it. What does is the ``Starting in`` line: the guard runs before
    it, the backstop after it. Deleting ``main``'s ``except
    LiveTradingBlockedError`` instead lets the generic handler return 1, and
    the ``raises`` goes unmet.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    path = _config(tmp_path, "testnet")
    assert get_settings(str(path)).mode is TradingMode.TESTNET
    argv = ["--config", str(path), "run", "--mode", "live"]
    assert cli._build_parser().parse_args(argv).mode is TradingMode.LIVE

    with caplog.at_level(logging.INFO), pytest.raises(SystemExit) as exit_info:
        cli.main(argv)

    assert exit_info.value.code == _OWNER_TEXT
    starting = [
        r
        for r in caplog.records
        if r.name == "trading_bot.main" and "Starting in" in r.getMessage()
    ]
    assert starting == []


def test_check_testnet_live_is_refused_even_with_confirm_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route D: ``check_testnet.py --mode live --confirm-live``.

    MUTATION: restore the ``and not args.confirm_live`` gate. With the flag
    set it passes, reaches ``get_settings`` -- replaced here by a recorder
    that raises -- and the ``raises`` goes unmet. The parse is shown first, so
    the refusal cannot be argparse rejecting the command with exit 2.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    argv = ["--mode", "live", "--confirm-live"]
    parsed = check_testnet._build_parser().parse_args(argv)
    assert parsed.mode == "live"
    assert parsed.confirm_live is True

    read: list[object] = []

    def _no_settings(*args: Any, **_kwargs: Any) -> Any:
        read.append(args)
        raise AssertionError("check_testnet read settings before refusing live")

    monkeypatch.setattr(check_testnet, "get_settings", _no_settings)

    with pytest.raises(SystemExit) as exit_info:
        check_testnet.main(argv)

    assert exit_info.value.code == _OWNER_TEXT
    assert read == []


# --------------------------------------------------------------------------
# The credential backstop
# --------------------------------------------------------------------------
def test_the_credential_read_refuses_live_before_any_key_is_read(config_path: Path) -> None:
    """``binance_credentials`` refuses LIVE before touching any slot.

    Every slot is populated, so a missing-key refusal cannot be the cause.
    MUTATION: move the refusal below the slot reads, or raise it as a
    ``ConfigError``. The first leaves reads behind; the second fails the exact
    type check, and would be swallowed as "Configuration error" by
    ``check_testnet.py``.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    secrets = _RecordingSecrets(
        bot_mode=TradingMode.LIVE,
        testnet_key="tn-key",
        testnet_secret="tn-secret",
        live_key=_LIVE_KEY,
        live_secret=_LIVE_SECRET,
    )
    settings = _settings(config_path, secrets)
    assert settings.mode is TradingMode.LIVE

    with pytest.raises(LiveTradingBlockedError) as exc_info:
        settings.binance_credentials()

    assert type(exc_info.value) is LiveTradingBlockedError
    assert not isinstance(exc_info.value, ConfigError)
    assert str(exc_info.value) == _OWNER_TEXT
    assert secrets.reads == []


async def test_binance_client_create_refuses_live_before_constructing(
    config_path: Path, constructors: list[str]
) -> None:
    """The real ``BinanceClient.create`` refuses LIVE before ``AsyncClient``.

    MUTATION: construct before reading credentials, or drop the credential
    refusal. Either reaches the ``AsyncClient.create`` recorder, which raises
    ``_ConstructorReachedError`` in place of ``LiveTradingBlockedError``.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    secrets = _RecordingSecrets(
        bot_mode=TradingMode.LIVE, live_key=_LIVE_KEY, live_secret=_LIVE_SECRET
    )
    settings = _settings(config_path, secrets)
    assert settings.mode is TradingMode.LIVE

    with pytest.raises(LiveTradingBlockedError):
        await _REAL_BINANCE_CLIENT_CREATE(settings)

    assert constructors == []
    assert secrets.reads == []


# --------------------------------------------------------------------------
# What is NOT refused
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mode",
    [TradingMode.TESTNET, TradingMode.PAPER, TradingMode.BACKTEST],
    ids=["testnet", "paper", "backtest"],
)
def test_non_live_modes_are_not_refused(
    tmp_path: Path, logging_setup: list[object], mode: TradingMode
) -> None:
    """Real money is refused and nothing else is.

    MUTATION: key the guard on ``is_live_connection`` -- ``[testnet]`` fails --
    or on ``mode is not TradingMode.TESTNET`` -- ``[paper]`` and
    ``[backtest]`` fail.
    """
    path = _config(tmp_path, mode.value)
    assert get_settings(str(path)).mode is mode

    refuse_live_trading(mode)
    assert cli.main(["--config", str(path), "strategies"]) == 0
    assert len(logging_setup) == 1


# --------------------------------------------------------------------------
# No bypass
# --------------------------------------------------------------------------
def test_every_override_at_once_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, logging_setup: list[object]
) -> None:
    """Every route and every plausible escape hatch together: still refused.

    MUTATION: add an escape keyed on any of ``_PLAUSIBLE_BYPASSES``. A finite
    list cannot prove no escape exists, which is why the signature test below
    pins the helper's parameters too.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    path = _config(tmp_path, "live")
    monkeypatch.setenv("BOT_MODE", "live")
    for name in _PLAUSIBLE_BYPASSES:
        monkeypatch.setenv(name, "1")
    assert get_settings(str(path)).mode is TradingMode.LIVE

    with pytest.raises(SystemExit) as run_exit:
        cli.main(["--config", str(path), "run", "--mode", "live"])
    assert run_exit.value.code == _OWNER_TEXT

    with pytest.raises(SystemExit) as check_exit:
        check_testnet.main(["--mode", "live", "--confirm-live", "--config", str(path)])
    assert check_exit.value.code == _OWNER_TEXT


def test_the_guard_takes_no_override_parameter() -> None:
    """The helper takes the mode and nothing else.

    MUTATION: add any parameter -- an ``allow=`` flag, a ``force=`` switch.
    This is "no bypass" as a property of the interface, which no finite set
    of environment variables can establish.
    """
    assert list(inspect.signature(refuse_live_trading).parameters) == ["mode"]


def test_the_process_exits_one_with_the_message_on_stderr(tmp_path: Path) -> None:
    """The real interpreter, the real entry point: exit 1, the message on stderr.

    MUTATION: drop the guard. The exit code alone would NOT catch that --
    ``main``'s generic handler also returns 1 -- which is why the message on
    stderr is asserted beside it. ``strategies`` builds no client and the
    environment conftest leaves holds no key, so even a mutant cannot reach a
    venue from here.
    """
    path = _config(tmp_path, "live")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO / "src")

    result = subprocess.run(
        [sys.executable, "-m", "trading_bot", "--config", str(path), "strategies"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert result.returncode == 1
    assert _OWNER_TEXT in result.stderr
    assert "Traceback" not in result.stderr
    assert "Registered strategies" not in result.stdout


# --------------------------------------------------------------------------
# Ruling 2: PAPER and BACKTEST hold no credentials; TESTNET never falls back
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "mode", [TradingMode.PAPER, TradingMode.BACKTEST], ids=["paper", "backtest"]
)
def test_paper_and_backtest_hold_no_exchange_credentials(
    config_path: Path, mode: TradingMode
) -> None:
    """PAPER and BACKTEST refuse with the ruled ``ConfigError``, reading no slot.

    Every slot is populated, so the refusal cannot be a missing-key one.
    MUTATION: let these modes fall through to the testnet read -- they would
    return the testnet pair -- or back to the live slots, as they did before.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    secrets = _RecordingSecrets(
        bot_mode=mode,
        testnet_key="tn-key",
        testnet_secret="tn-secret",
        live_key=_LIVE_KEY,
        live_secret=_LIVE_SECRET,
    )
    settings = _settings(config_path, secrets)
    assert settings.mode is mode

    with pytest.raises(ConfigError) as exc_info:
        settings.binance_credentials()

    assert type(exc_info.value) is ConfigError
    assert str(exc_info.value) == "PAPER and BACKTEST modes do not use exchange credentials"
    assert secrets.reads == []


def test_an_empty_testnet_slot_refuses_without_touching_the_live_slots(
    config_path: Path,
) -> None:
    """No fallback: an empty testnet slot refuses, and the live slots stay unread.

    The live slots hold distinctive sentinels, and the stand-in is shown to
    hold them, so a fallback WOULD find them. MUTATION: restore
    ``testnet or live`` -- the sentinel comes back and the ``raises`` is unmet.
    Or read the live slot and refuse afterwards -- the recorded reads show it,
    which no return value or message could.

    M5i-115: an unmet ``pytest.raises`` raises ``Failed``, not
    ``AssertionError``.
    """
    secrets = _RecordingSecrets(
        bot_mode=TradingMode.TESTNET, live_key=_LIVE_KEY, live_secret=_LIVE_SECRET
    )
    settings = _settings(config_path, secrets)
    assert settings.mode is TradingMode.TESTNET
    assert secrets.slots["binance_api_key"] == _LIVE_KEY

    with pytest.raises(ConfigError) as exc_info:
        settings.binance_credentials()

    assert str(exc_info.value) == "Missing Binance Testnet credentials"
    assert _LIVE_KEY not in str(exc_info.value)
    assert _LIVE_SECRET not in str(exc_info.value)
    assert "binance_api_key" not in secrets.reads
    assert "binance_api_secret" not in secrets.reads


def test_testnet_returns_exactly_the_testnet_slots(config_path: Path) -> None:
    """TESTNET with both testnet slots populated returns exactly them.

    MUTATION: prefer the live slots, or mix the pair. The live sentinels sit
    beside the testnet values, so either is visible in the returned pair.
    """
    secrets = _RecordingSecrets(
        bot_mode=TradingMode.TESTNET,
        testnet_key="tn-key",
        testnet_secret="tn-secret",
        live_key=_LIVE_KEY,
        live_secret=_LIVE_SECRET,
    )
    settings = _settings(config_path, secrets)
    assert settings.mode is TradingMode.TESTNET

    assert settings.binance_credentials() == ("tn-key", "tn-secret")
    assert set(secrets.reads) == {"binance_testnet_api_key", "binance_testnet_api_secret"}
