"""``main``'s startup order: banner, provenance line, refusal, then dispatch.

The provenance collector is replaced through ``trading_bot.main``'s own
binding, so these tests pin WHERE ``main`` logs and refuses; what the
collector establishes is ``tests/unit/test_provenance.py``'s subject.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

import trading_bot.main as cli
from trading_bot.utils.provenance import InstallKind, Provenance, refusal_message


def _facts(*, accepted: bool) -> Provenance:
    return Provenance(
        install_kind=InstallKind.VCS if accepted else InstallKind.EDITABLE,
        code_commit="a" * 40 if accepted else None,
        code_intact=True if accepted else None,
        code_files_checked=67 if accepted else 0,
        module_file=Path("trading_bot/__init__.py"),
        checkout_root=Path("checkout"),
        checkout_commit="a" * 40,
        dirty_paths=() if accepted else ("config.yaml",),
        commits_agree=True if accepted else None,
        config_path=Path("checkout/config.yaml"),
        config_sha256="0" * 64,
        config_tracked=True,
        python_version="3.12.10",
        package_version="0.1.0",
        unknown_reasons=(),
    )


def _provenance_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == "trading_bot.main" and vars(r).get("event") == "boot_provenance"
    ]


@pytest.fixture(autouse=True)
def _no_logging_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ``main`` from replacing the root handlers ``caplog`` depends on."""
    monkeypatch.setattr(cli, "setup_logging", lambda _config: None)


def test_provenance_line_precedes_starting_in(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test 14. The boot line comes after the banner and before ``Starting in``.

    Accepted provenance lets ``run`` dispatch; the testnet config has no
    credentials, so ``_cmd_run`` returns 1 at the credential read, which is
    AFTER its ``Starting in`` line.

    MUTATION m9: log the line inside ``_cmd_run`` after ``Starting in``.
    """
    facts = _facts(accepted=True)
    monkeypatch.setattr(cli, "collect_provenance", lambda *_a, **_k: facts)

    with caplog.at_level(logging.INFO):
        code = cli.main(["--config", str(config_path), "run"])

    assert code == 1
    main_records = [r for r in caplog.records if r.name == "trading_bot.main"]
    messages = [r.getMessage() for r in main_records]
    boot = [i for i, r in enumerate(main_records) if vars(r).get("event") == "boot_provenance"]
    starting = [i for i, m in enumerate(messages) if m.startswith("Starting in")]
    banner = [i for i, m in enumerate(messages) if "____" in m]
    assert len(boot) == 1
    assert len(starting) == 1
    assert len(banner) == 1
    assert banner[0] < boot[0] < starting[0]
    assert vars(main_records[boot[0]]).get("verdict") == "accepted"
    assert main_records[boot[0]].levelno == logging.INFO


def test_refusal_precedes_dispatch_and_is_logged(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test 26. A refused ``run`` exits with the reasons, logged, before dispatch.

    ``_cmd_run`` is a recorder that fails if reached. The exit carries
    :func:`refusal_message`'s text, and the boot line is at ``ERROR`` with the
    verdict and every reason.

    MUTATION m9: the line moved into ``_cmd_run`` is never logged here.
    """
    facts = _facts(accepted=False)
    reached: list[Any] = []
    monkeypatch.setattr(cli, "collect_provenance", lambda *_a, **_k: facts)
    monkeypatch.setattr(cli, "_cmd_run", lambda *args: reached.append(args) or 0)

    with caplog.at_level(logging.INFO), pytest.raises(SystemExit) as exit_info:
        cli.main(["--config", str(config_path), "run"])

    assert exit_info.value.code == refusal_message(facts)
    assert reached == []
    records = _provenance_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert vars(records[0]).get("verdict") == "refused"
    reasons = vars(records[0]).get("refusal_reasons")
    assert isinstance(reasons, str)
    assert reasons.split(";") == list(facts.refusal_reasons)
    assert "install_kind=editable" in reasons
    starting = [r for r in caplog.records if r.getMessage().startswith("Starting in")]
    assert starting == []


def test_refused_provenance_does_not_gate_other_subcommands(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The refusal is ``run``'s alone; every subcommand still logs the line.

    ``strategies`` and ``backtest`` touch no venue, store or lock (P55 S0.6),
    so they are not gated -- but the boot line is logged on every boot.
    """
    facts = _facts(accepted=False)
    monkeypatch.setattr(cli, "collect_provenance", lambda *_a, **_k: facts)

    with caplog.at_level(logging.INFO):
        assert cli.main(["--config", str(config_path), "strategies"]) == 0
        assert cli.main(["--config", str(config_path), "backtest"]) == 0

    records = _provenance_records(caplog)
    assert len(records) == 2
    assert [vars(r).get("verdict") for r in records] == ["refused", "refused"]
