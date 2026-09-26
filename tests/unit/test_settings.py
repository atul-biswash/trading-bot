"""Which config file was loaded, and which bytes of it.

``Settings.config_path`` and ``Settings.config_sha256`` feed the startup
provenance line. The digest is worth something only if it describes the bytes
that were PARSED, so the file is read once and those bytes are hashed, decoded
and parsed -- never a second read.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from trading_bot.config.settings import get_settings
from trading_bot.core.enums import TradingMode

_BODY = """\
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


def test_config_digest_is_of_bytes_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test 13. The digest and the parsed config come from ONE read.

    The file changes under the reader: its first read returns the testnet
    body, every later read the paper body. A digest of a second read would
    carry the paper body's hash, and a parse from a second read would carry its
    mode, so both halves are pinned by one fixture. ``read_text`` is recorded
    too, because a parse through it is a second read that ``read_bytes`` would
    never see.

    MUTATION m8: hash a second ``read_bytes``. The digest becomes the paper
    body's, and the count assertion sees two reads.
    """
    path = tmp_path / "config.yaml"
    first = _BODY.format(mode="testnet").encode("utf-8")
    later = _BODY.format(mode="paper").encode("utf-8")
    path.write_bytes(first)
    target = path.resolve()

    original_read_bytes = Path.read_bytes
    original_read_text = Path.read_text
    byte_reads: list[Path] = []
    text_reads: list[Path] = []

    def _read_bytes(self: Path) -> bytes:
        if self.resolve() == target:
            byte_reads.append(self)
            return first if len(byte_reads) == 1 else later
        return original_read_bytes(self)

    def _read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.resolve() == target:
            text_reads.append(self)
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", _read_bytes)
    monkeypatch.setattr(Path, "read_text", _read_text)

    settings = get_settings(str(path))

    assert len(byte_reads) == 1
    assert text_reads == []
    assert settings.config_sha256 == hashlib.sha256(first).hexdigest()
    assert settings.config_sha256 != hashlib.sha256(later).hexdigest()
    assert settings.mode is TradingMode.TESTNET
    assert settings.config_path == target
    assert settings.config_path is not None
    assert settings.config_path.is_absolute()


def test_crlf_and_lf_configs_parse_identically(tmp_path: Path) -> None:
    """Decoding bytes drops ``read_text``'s newline translation; YAML does not care.

    ``_read_config`` switched from ``read_text`` to ``read_bytes`` so the digest
    and the parse share one read. That removed universal-newline translation,
    so a CRLF file now reaches the YAML parser with its CRs. The two parses
    must still agree, and the two digests must differ, because the bytes do.
    """
    lf = tmp_path / "lf.yaml"
    crlf = tmp_path / "crlf.yaml"
    body = _BODY.format(mode="testnet")
    lf.write_bytes(body.encode("utf-8"))
    crlf.write_bytes(body.replace("\n", "\r\n").encode("utf-8"))

    lf_settings = get_settings(str(lf))
    get_settings.cache_clear()
    crlf_settings = get_settings(str(crlf))

    assert crlf_settings.config == lf_settings.config
    assert crlf_settings.config_sha256 != lf_settings.config_sha256
