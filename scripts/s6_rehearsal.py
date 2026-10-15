"""S6 rehearsal, first part: the narrowed protocol and the pure helpers over what the chain writes.

R-CL: before any S6 run the whole chain is rehearsed end to end over a NARROWED protocol, with the real
engine, in a throwaway worktree. This part holds what needs no process: ``narrow_protocol`` (the real
``PROTOCOL.md`` cut to two variants and short windows, parsed by all three readers before it is returned),
the out-of-sample command line built from an entry as step O6 builds it, the marking of an entry ``read``,
the reading of a run directory's record, and ``Expect``, what a hop is predicted to do. The commands, the
worktree and the cleanup are the next commit's.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from trading_bot.backtesting import gate as gate_rules
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import canonical_number
from trading_bot.backtesting.evidence import RUN_RECORD_NAME, load_eligible_record
from trading_bot.backtesting.protocol import declaration, parse_protocol

__all__ = [
    "CASES",
    "Expect",
    "Outcome",
    "entry_bytes",
    "file_count",
    "find_oos_records",
    "mark_read",
    "narrow_protocol",
    "oos_argv",
    "parse_boot_line",
    "worktree_url",
]

_BEGIN: Final = "<!-- protocol-json:begin -->"
_END: Final = "<!-- protocol-json:end -->"
_BANNER: Final = (
    "<!-- P118 REHEARSAL COPY: a narrowed protocol written inside a throwaway worktree. -->\n"
)
#: The pass case's thresholds: as low as the rules allow, so that a small window can meet them.
_PASS_S7: Final = {
    "profit_factor_min": "0.0001",
    "trades_min": 1,
    "max_drawdown_max": "0.9999",
    "regimes_positive_min": 1,
}
_QUARTER_MONTHS: Final = (1, 4, 7, 10)
CASES: Final = ("pass", "fail")


# --------------------------------------------------------------------------
# What the narrowed protocol is
# --------------------------------------------------------------------------
def _is_quarter_start(day: date) -> bool:
    return day.day == 1 and day.month in _QUARTER_MONTHS


def narrow_protocol(
    text: str, *, start: date, boundary: date, end: date, case: str, min_trades: int = 3
) -> str:
    """``text`` (the real ``PROTOCOL.md``) with its declaration narrowed to two variants and short windows.

    The families become ``sma_crossover`` at ``4h`` with ``fast_period`` 10 and ``slow_period`` 50 (two
    variants: the filter off and on); the history is ``[start, end)`` with ``boundary`` inside it; the
    selection's walk-forward trains from ``start`` and tests the calendar year before the boundary; the
    minimum in-sample trades are ``min_trades``. In the ``pass`` case the ``s7`` block takes the lowest
    thresholds the rules admit; in the ``fail`` case it is the real block. Every other key, and all of the
    prose, is the real protocol's. The result is parsed by all three readers before it is returned.

    :raises ValueError: a case that is not ``pass`` or ``fail``, a boundary or end that is not a quarter
        start, or a boundary that is not 1 January (the walk-forward tests the year before it).
    :raises trading_bot.backtesting.protocol.ProtocolError: the narrowed declaration is refused.
    """
    if case not in CASES:
        raise ValueError(f"case {case!r} is not one of {CASES}")
    if not (_is_quarter_start(boundary) and _is_quarter_start(end)):
        raise ValueError(
            "the boundary and the end must be quarter starts: S7 refuses a part quarter"
        )
    if (boundary.month, boundary.day) != (1, 1):
        raise ValueError(
            "the boundary must be 1 January: the walk-forward tests the year before it"
        )
    top = json.loads(json.dumps(dict(declaration(text))))
    top["history"] = {"start": start.isoformat(), "end_exclusive": end.isoformat()}
    top["boundary"] = boundary.isoformat()
    top["min_in_sample_trades"] = min_trades
    top["selection"]["walk_forward"] = {
        "train_start": start.isoformat(),
        "test_years": [boundary.year - 1],
    }
    top["families"] = [
        {
            "id": "sma_crossover",
            "strategy": "sma_crossover",
            "timeframes": ["4h"],
            "grid": {"fast_period": [10], "slow_period": [50]},
        }
    ]
    if case == "pass":
        top["s7"] = dict(_PASS_S7)
    head, rest = text.split(_BEGIN, 1)
    tail = rest.split(_END, 1)[1]
    body = json.dumps(top, indent=2)
    narrowed = f"{_BANNER}{head}{_BEGIN}\n```json\n{body}\n```\n{_END}{tail}"
    parse_protocol(narrowed)
    sel.parse_rules(narrowed)
    gate_rules.parse_gate_rules(narrowed)
    return narrowed


# --------------------------------------------------------------------------
# Pure helpers over what the chain writes
# --------------------------------------------------------------------------
def oos_argv(
    python: str, entry: Mapping[str, Any], arm: str, *, start: date, end: date
) -> list[str]:
    """The out-of-sample ``backtest`` command of one (entry, arm), built from the entry as step O6 builds it."""
    variant = entry["selection"]["variant"]
    argv = [
        python,
        "-m",
        "trading_bot",
        "backtest",
        "--start",
        start.isoformat(),
        "--end",
        end.isoformat(),
        "--stop-slippage",
        arm,
        "--strategy",
        str(variant["family"]),
        "--timeframe",
        str(variant["timeframe"]),
    ]
    for name, value in variant["params"].items():
        argv += ["--param", f"{name}={value}"]
    return argv


def entry_bytes(body: Mapping[str, Any]) -> bytes:
    """An entry as ``s6_select.py`` writes one: indented JSON, ASCII, one trailing newline, LF."""
    return (json.dumps(body, indent=2) + "\n").encode("ascii")


def mark_read(entry: Mapping[str, Any], records: Mapping[str, tuple[str, str]]) -> dict[str, Any]:
    """``entry`` marked ``read``, its ``oos.records`` holding, per arm, the run directory and ``run.json`` digest.

    Nothing in the tree does this yet; the shape is the one ``gate.evaluate`` reads and
    ``docs/research/entries/s5-baseline.json`` shows.
    """
    marked = dict(entry)
    marked["status"] = "read"
    marked["oos"] = {
        "records": {
            arm: {"run": run, "run_json_sha256": digest}
            for arm, (run, digest) in sorted(records.items(), key=lambda item: Decimal(item[0]))
        }
    }
    return marked


def find_oos_records(backtests: Path, entry_id: str) -> dict[str, tuple[str, str]]:
    """``{arm: (run directory, run.json SHA-256)}`` of every sealed out-of-sample record of ``entry_id``.

    Every record is read through the evidence door (``tests/unit/test_backtest_evidence.py`` holds the census
    that requires it), so a record that is not evidence stops the rehearsal rather than being skipped: the
    gate would refuse it. Arms are written as the entry writes them (``canonical_number``). Two records of
    one arm are returned as the later directory; the guard makes that unreachable, and the caller asserts
    the count.

    :raises trading_bot.backtesting.evidence.EvidenceRefusedError: a run directory's record is not evidence.
    """
    found: dict[str, tuple[str, str]] = {}
    for directory in (
        sorted(p for p in backtests.iterdir() if p.is_dir()) if backtests.is_dir() else []
    ):
        path = directory / RUN_RECORD_NAME
        if not path.is_file():
            continue
        record = load_eligible_record(path, min_schema=gate_rules.MIN_RECORD_SCHEMA)
        block = record.get("protocol")
        if not isinstance(block, dict) or block.get("entry_id") != entry_id:
            continue
        if block.get("window_class") != "out_of_sample":
            continue
        arm = canonical_number(Decimal(str(block["arm"])))
        found[arm] = (directory.name, hashlib.sha256(path.read_bytes()).hexdigest())
    return found


_PAIR: Final = re.compile(r"(\w+)=(\S+)")


def parse_boot_line(output: str) -> dict[str, str]:
    """The ``key=value`` fields of the first ``boot_provenance`` line of ``output``; empty if there is none."""
    for line in output.splitlines():
        if "boot_provenance" in line:
            return dict(_PAIR.findall(line))
    return {}


def worktree_url(worktree: Path, sha: str) -> str:
    """The ``pip`` requirement that installs ``worktree`` at ``sha`` by commit (spaces as ``%20``)."""
    return f"binance-trading-bot @ git+file:///{worktree.as_posix().replace(' ', '%20')}@{sha}"


def file_count(root: Path) -> int:
    """Every file under ``root``. ``os.walk`` does not follow links, so a link inside ``root`` counts none."""
    return sum(len(files) for _, _, files in os.walk(root))


# --------------------------------------------------------------------------
# Running a hop
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Outcome:
    returncode: int
    output: str
    seconds: float


@dataclass(frozen=True)
class Expect:
    """What a hop is predicted to do: an exit status, phrases present and absent, and counts of phrases."""

    code: int
    contains: tuple[str, ...] = ()
    absent: tuple[str, ...] = ()
    counts: tuple[tuple[str, int], ...] = ()
    empty: bool = False

    def describe(self) -> str:
        parts = [f"exit {self.code}"]
        parts += [f"has {p!r}" for p in self.contains]
        parts += [f"lacks {p!r}" for p in self.absent]
        parts += [f"{n} x {p!r}" for p, n in self.counts]
        parts += ["no output"] if self.empty else []
        return "; ".join(parts)

    def mismatch(self, outcome: Outcome) -> str | None:
        """What differs from the prediction, or ``None`` if nothing does."""
        problems: list[str] = []
        if outcome.returncode != self.code:
            problems.append(f"exit {outcome.returncode}, predicted {self.code}")
        problems += [f"missing {p!r}" for p in self.contains if p not in outcome.output]
        problems += [f"unexpected {p!r}" for p in self.absent if p in outcome.output]
        if self.empty and outcome.output.strip():
            problems.append(f"output {outcome.output.strip()[:200]!r}, predicted none")
        for phrase, count in self.counts:
            got = outcome.output.count(phrase)
            if got != count:
                problems.append(f"{got} x {phrase!r}, predicted {count}")
        return "; ".join(problems) or None
