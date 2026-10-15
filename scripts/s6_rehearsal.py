"""S6 rehearsal: drive the whole S6/S7 chain over a NARROWED protocol, with the real engine, in a throwaway worktree.

``python scripts/s6_rehearsal.py --root DIR --store DIR [--case pass|fail|both] [--keep]``

R-CL: before any S6 run, the chain is rehearsed end to end -- sweep, selection, entry writing, the out-of-sample
runs at all three arms, and the S7 gate, in both a passing and a failing case. This is that rehearsal. **It
writes nothing under the repository it is run from and commits nothing to ``docs/research/``**: each case
builds a detached worktree OUTSIDE the repository, at HEAD, with its own ``.venv`` and a NON-EDITABLE
install by commit (the only shape the evidence door accepts), a junction to the canonical store, and a
narrowed protocol written and committed INSIDE the worktree. Everything it records lives under ``--root``.

**The hops are real commands.** The sweep (``s6_sweep.py --workers 2``, R-CH's check included), the selection
(``s6_select.py``, with and without ``--out``), every out-of-sample run (``python -m trading_bot backtest``
built from the entry exactly as the owner's step O6 builds it), the refused second read and the gate
(``s7_gate.py``) are subprocesses of the worktree's own interpreter. Only what no command does is done here: writing
the narrowed protocol, committing it, and marking the entries ``read`` (no tool does that yet).

**Every hop is recorded**: command, working directory, exit status, the SHA-256 of its combined output, its
seconds, what was expected and whether it matched, one JSON line in ``<root>/<case>/hops.jsonl`` and the
output itself in ``<root>/<case>/out/``. A hop that does not match what was predicted STOPS the case: it is a
seam fault to diagnose, and the worktree is kept for the diagnosis (``--clean-only`` removes it).

**The narrowing is a property of the windows, not of the machinery.** The in-sample window must span a calendar
year (the selection refuses a fold that ends after the boundary or leaves no training window), and the
out-of-sample window must hold only COMPLETE quarters (S7 refuses a trade that belongs to no regime), so the
boundary and the end are quarter starts. The PASS case lowers S7's four thresholds so that a small window can
meet them; the FAIL case leaves the real ones. Neither edits ``docs/research/PROTOCOL.md``.

**Cleanup removes the junction first**, with ``cmd /c rmdir`` and by itself, and refuses to remove the
worktree if the link is still there: ``git worktree remove`` would otherwise be a recursive delete that might
follow the link into the canonical store. The store's file count is taken before and after.

Exit status: 0 every hop of every case matched; 1 a hop did not; 2 refused (a bad argument or location).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

from trading_bot.backtesting import gate as gate_rules
from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.candidate import canonical_number
from trading_bot.backtesting.evidence import RUN_RECORD_NAME, load_eligible_record
from trading_bot.backtesting.protocol import declaration, parse_protocol

__all__ = [
    "Config",
    "Expect",
    "HopMismatchError",
    "Outcome",
    "Rehearsal",
    "find_oos_records",
    "main",
    "mark_read",
    "narrow_protocol",
    "oos_argv",
    "parse_boot_line",
    "worktree_url",
]

EXIT_MISMATCH: Final = 1
EXIT_REFUSED: Final = 2
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
#: The arms as step O6 spells them on the command line (``--stop-slippage 1.20``); the protocol's own text is
#: canonical (``1.2``), and ``go`` checks that the two name the same numbers.
_O6_ARMS: Final = ("0.05", "0.66", "1.20")
_QUARTER_MONTHS: Final = (1, 4, 7, 10)
CASES: Final = ("pass", "fail")


class HopMismatchError(Exception):
    """A hop did not do what was predicted; the case stops here and its worktree is kept."""

    def __init__(self, record: HopRecord) -> None:
        super().__init__(f"hop {record.number:02d} {record.name}: {record.detail}")
        self.record = record


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


Run = Callable[[Sequence[str], Path, Mapping[str, str]], Outcome]


def real_run(argv: Sequence[str], cwd: Path, env: Mapping[str, str]) -> Outcome:
    """Run ``argv`` in ``cwd``, stderr merged into stdout, decoded as UTF-8."""
    started = time.monotonic()
    done = subprocess.run(
        list(argv),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return Outcome(
        done.returncode, done.stdout.decode("utf-8", errors="replace"), time.monotonic() - started
    )


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


@dataclass(frozen=True)
class HopRecord:
    case: str
    number: int
    name: str
    kind: str
    argv: tuple[str, ...]
    cwd: str
    returncode: int | None
    output_sha256: str
    seconds: float
    expected: str
    matched: bool
    detail: str


@dataclass(frozen=True)
class Config:
    """Where everything is, and the windows the narrowed protocol takes."""

    repo: Path
    root: Path
    store: Path
    python: str
    start: date = date(2023, 12, 1)
    boundary: date = date(2025, 1, 1)
    end: date = date(2025, 4, 1)
    keep: bool = False
    label: str = "run"


def _environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")}
    env.update(
        {
            "COLUMNS": "1000",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
        }
    )
    return env


# --------------------------------------------------------------------------
# One case
# --------------------------------------------------------------------------
@dataclass
class Rehearsal:
    """One case (``pass`` or ``fail``): its worktree, its hops, and the order they run in."""

    case: str
    config: Config
    run: Run = real_run
    echo: Callable[[str], None] = print
    records: list[HopRecord] = field(default_factory=list, init=False)
    _entry_ids: list[str] = field(default_factory=list, init=False)
    _store_before: int | None = field(default=None, init=False)
    _earlier: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Number this object's hops after those already kept for the case (a ``--clean-only`` follows a run)."""
        log = self.base / "hops.jsonl"
        self._earlier = len(log.read_bytes().splitlines()) if log.is_file() else 0

    # ---- locations ----------------------------------------------------
    @property
    def base(self) -> Path:
        return self.config.root / self.config.label / self.case

    @property
    def wt(self) -> Path:
        return self.base / "wt"

    @property
    def py(self) -> str:
        return str(self.wt / ".venv" / "Scripts" / "python.exe")

    @property
    def backtests(self) -> Path:
        return self.wt / "data" / "backtests"

    @property
    def link(self) -> Path:
        return self.wt / "data" / "historical"

    # ---- recording ----------------------------------------------------
    def _record(self, record: HopRecord, output: str) -> HopRecord:
        out = self.base / "out"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{record.number:02d}-{record.name}.txt").write_bytes(output.encode("utf-8"))
        with (self.base / "hops.jsonl").open("ab") as handle:
            handle.write((json.dumps(asdict(record), sort_keys=True) + "\n").encode("ascii"))
        self.records.append(record)
        verdict = "MATCH" if record.matched else "MISMATCH"
        self.echo(
            f"[{self.case}] {record.number:02d} {record.name}: {verdict}; exit {record.returncode}; "
            f"sha256 {record.output_sha256[:16]}; {record.seconds:.1f} s"
            + ("" if record.matched else f"; {record.detail}")
        )
        if not record.matched:
            raise HopMismatchError(record)
        return record

    def hop(self, name: str, argv: Sequence[str], cwd: Path, expect: Expect) -> Outcome:
        """Run one command and record it against its prediction; a mismatch is recorded and then raises."""
        outcome = self.run(argv, cwd, _environment())
        problem = expect.mismatch(outcome)
        record = HopRecord(
            case=self.case,
            number=self._earlier + len(self.records) + 1,
            name=name,
            kind="command",
            argv=tuple(str(a) for a in argv),
            cwd=str(cwd),
            returncode=outcome.returncode,
            output_sha256=hashlib.sha256(outcome.output.encode("utf-8")).hexdigest(),
            seconds=round(outcome.seconds, 3),
            expected=expect.describe(),
            matched=problem is None,
            detail=problem or "",
        )
        self._record(record, outcome.output)
        return outcome

    def check(self, name: str, expected: str, problem: str | None, evidence: str = "") -> None:
        """Record a check that no command makes; ``problem`` is ``None`` when the prediction held."""
        record = HopRecord(
            case=self.case,
            number=self._earlier + len(self.records) + 1,
            name=name,
            kind="check",
            argv=(),
            cwd=str(self.wt),
            returncode=None,
            output_sha256=hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
            seconds=0.0,
            expected=expected,
            matched=problem is None,
            detail=problem or "",
        )
        self._record(record, evidence)

    # ---- small commands ----------------------------------------------
    def git(self, name: str, *args: str, expect: Expect | None = None) -> Outcome:
        return self.hop(name, ["git", *args], self.wt, expect or Expect(0))

    def status_is_clean(self, name: str) -> None:
        self.git(name, "status", "--porcelain", expect=Expect(0, empty=True))

    def head(self) -> str:
        outcome = self.run(["git", "rev-parse", "HEAD"], self.wt, _environment())
        return outcome.output.strip()

    # ---- the phases ---------------------------------------------------
    def setup(self, narrowed: str) -> None:
        repo, wt = self.config.repo, self.wt
        self.base.mkdir(parents=True, exist_ok=True)
        self._store_before = file_count(self.config.store)
        self.hop(
            "worktree-add",
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(wt), "HEAD"],
            repo,
            Expect(0),
        )
        self.hop("venv", [self.config.python, "-m", "venv", str(wt / ".venv")], wt, Expect(0))
        self.hop(
            "pip-requirements",
            [self.py, "-m", "pip", "install", "-r", "requirements.txt"],
            wt,
            Expect(0),
        )
        (wt / "data").mkdir(exist_ok=True)
        self.hop(
            "junction",
            ["cmd", "/c", "mklink", "/J", str(self.link), str(self.config.store)],
            wt,
            Expect(0, contains=("Junction created",)),
        )
        (wt / "docs" / "research" / "PROTOCOL.md").write_bytes(narrowed.encode("utf-8"))
        self.commit(
            "narrowed-protocol", "docs/research/PROTOCOL.md", "rehearsal: narrowed protocol"
        )
        self.reinstall("install-by-commit")
        self.boot_accepted("boot-after-narrowing")

    def commit(self, name: str, path: str, message: str) -> None:
        """Add ``path`` and commit it inside the worktree (the commit is reachable from nothing else)."""
        self.git(f"add-{name}", "add", path)
        self.git(
            f"commit-{name}",
            "-c",
            "user.name=rehearsal",
            "-c",
            "user.email=rehearsal@invalid",
            "commit",
            "-m",
            message,
        )

    def reinstall(self, name: str) -> None:
        """Install the worktree's HEAD by commit; ``--force-reinstall --no-deps`` because a plain install of
        a new commit into a venv that already holds the package keeps the OLD one (measured, P118)."""
        self.hop(
            name,
            [
                self.py,
                "-m",
                "pip",
                "install",
                "--force-reinstall",
                "--no-deps",
                worktree_url(self.wt, self.head()),
            ],
            self.wt,
            Expect(0),
        )

    def boot_accepted(self, name: str) -> None:
        outcome = self.hop(name, [self.py, "-m", "trading_bot", "strategies"], self.wt, Expect(0))
        fields = parse_boot_line(outcome.output)
        wanted = {
            "verdict": "accepted",
            "install_kind": "vcs",
            "code_intact": "true",
            "checkout_dirty": "false",
            "commits_agree": "true",
            "config_tracked": "true",
            "code_commit": self.head(),
        }
        wrong = {k: fields.get(k) for k, v in wanted.items() if fields.get(k) != v}
        self.check(
            f"{name}-provenance",
            "boot_provenance " + " ".join(f"{k}={v}" for k, v in wanted.items()),
            f"not as predicted: {wrong}" if wrong else None,
            outcome.output,
        )
        self.status_is_clean(f"{name}-status")

    def sweep_and_select(self) -> None:
        wt = self.wt
        self.hop(
            "sweep",
            [self.py, "scripts/s6_sweep.py", "--workers", "2"],
            wt,
            Expect(
                0,
                contains=(
                    "variants declared 2; with a sealed evidence-eligible record 2",
                    "parallel check: the trade-log digests are equal",
                    "  COMPLETE",
                ),
                absent=("MISSING", "CONFLICT", "FAILED", "NOT COMPLETE", "SKIPPED", "OFF-GRID"),
                counts=(("DUPLICATED", 1),),
            ),
        )
        self.status_is_clean("status-after-sweep")
        report = self.hop(
            "select-report",
            [self.py, "scripts/s6_select.py", "--backtests", "data/backtests"],
            wt,
            Expect(0, contains=("S6 SELECTION", "variants declared 2; with a run 2")),
        )
        match = re.search(r"cells with a candidate (\d+) of 2", report.output)
        count = int(match.group(1)) if match else 0
        self.check(
            "select-has-candidates",
            "at least one cell has a candidate (else the rehearsal reads nothing)",
            None if count >= 1 else f"{count} candidates",
            report.output,
        )
        self.status_is_clean("status-after-report")
        written = self.hop(
            "select-write",
            [
                self.py,
                "scripts/s6_select.py",
                "--backtests",
                "data/backtests",
                "--out",
                "docs/research/selection.json",
                "--entries-dir",
                "docs/research/entries",
            ],
            wt,
            Expect(0, contains=("selection file docs", " sha256 ")),
        )
        self._entry_ids = [
            Path(line.split(" ", 1)[1].strip()).stem
            for line in written.output.splitlines()
            if line.startswith("entry ")
        ]
        self.check(
            "select-entries-match-report",
            f"{count} entry lines",
            None if len(self._entry_ids) == count else f"{len(self._entry_ids)} entry lines",
            written.output,
        )
        listing = self.hop(
            "status-lists-the-new-files",
            ["git", "status", "--porcelain"],
            wt,
            Expect(0, contains=("docs/research/selection.json",)),
        )
        self.check(
            "status-holds-only-the-new-files",
            f"{count + 1} lines, all untracked",
            None
            if len(listing.output.splitlines()) == count + 1
            and all(line.startswith("??") for line in listing.output.splitlines())
            else "other lines",
            listing.output,
        )
        self.commit("selection", "docs/research", "rehearsal: selection and pending entries")
        self.reinstall("install-at-entries")
        self.boot_accepted("boot-at-entries")

    def _entries(self) -> list[dict[str, Any]]:
        return [
            json.loads((self.wt / "docs" / "research" / "entries" / f"{i}.json").read_text("utf-8"))
            for i in self._entry_ids
        ]

    def out_of_sample(self, arms: Sequence[str]) -> None:
        cfg, wt = self.config, self.wt
        for entry in self._entries():
            for arm in _O6_ARMS:
                self.hop(
                    f"oos-{entry['id']}-{arm}",
                    oos_argv(self.py, entry, arm, start=cfg.boundary, end=cfg.end),
                    wt,
                    Expect(0),
                )
        for entry in self._entries():
            found = find_oos_records(self.backtests, entry["id"])
            self.check(
                f"oos-records-{entry['id']}",
                f"one sealed out-of-sample record at each of {list(arms)}",
                None if sorted(found) == sorted(arms) else f"arms {sorted(found)}",
                json.dumps(found, sort_keys=True),
            )
        self.status_is_clean("status-after-oos")
        names = sorted(p.name for p in self.backtests.iterdir() if p.is_dir())
        first = self._entries()[0]
        self.hop(
            "second-read-same-arm",
            oos_argv(self.py, first, _O6_ARMS[0], start=cfg.boundary, end=cfg.end),
            wt,
            Expect(1, contains=("local_prior_read", "once per arm")),
        )
        after = sorted(p.name for p in self.backtests.iterdir() if p.is_dir())
        self.check(
            "second-read-left-no-run",
            "no new run directory",
            None if after == names else f"directories changed: {sorted(set(after) ^ set(names))}",
            "\n".join(after),
        )
        self.status_is_clean("status-after-refusal")

    def mark_and_recheck(self) -> None:
        cfg, wt = self.config, self.wt
        for entry in self._entries():
            records = find_oos_records(self.backtests, entry["id"])
            path = wt / "docs" / "research" / "entries" / f"{entry['id']}.json"
            path.write_bytes(entry_bytes(mark_read(entry, records)))
        self.check("entries-marked-read", "every entry rewritten with status read", None)
        self.commit("read", "docs/research", "rehearsal: entries marked read")
        self.reinstall("install-at-read")
        self.boot_accepted("boot-at-read")
        names = sorted(p.name for p in self.backtests.iterdir() if p.is_dir())
        self.hop(
            "read-after-read",
            oos_argv(self.py, self._entries()[0], _O6_ARMS[0], start=cfg.boundary, end=cfg.end),
            wt,
            Expect(1, contains=("already_read", "has been read out of sample already")),
        )
        after = sorted(p.name for p in self.backtests.iterdir() if p.is_dir())
        self.check(
            "read-after-read-left-no-run",
            "no new run directory",
            None if after == names else f"directories changed: {sorted(set(after) ^ set(names))}",
            "\n".join(after),
        )

    def gate(self) -> None:
        count = len(self._entry_ids)
        if self.case == "pass":
            expect = Expect(
                0,
                contains=(
                    "S7 DECISION GATE",
                    f"S7 SUMMARY: {count} of {count} candidates read PASS",
                ),
                absent=("S7: FAIL",),
                counts=(("S7: PASS", count),),
            )
        else:
            expect = Expect(
                0,
                contains=(
                    "S7 DECISION GATE",
                    "NOT MET  trades",
                    f"S7 SUMMARY: 0 of {count} candidates",
                ),
                absent=("S7: PASS",),
                counts=(("S7: FAIL", count),),
            )
        self.hop(
            "s7-gate",
            [self.py, "scripts/s7_gate.py", "--backtests", "data/backtests"],
            self.wt,
            expect,
        )

    # ---- the case -----------------------------------------------------
    def go(self, protocol_text: str) -> None:
        cfg = self.config
        narrowed = narrow_protocol(
            protocol_text, start=cfg.start, boundary=cfg.boundary, end=cfg.end, case=self.case
        )
        arms = parse_protocol(narrowed).arms
        flags = sorted(canonical_number(Decimal(a)) for a in _O6_ARMS)
        if flags != sorted(arms):
            raise ValueError(f"step O6 runs arms {flags}, and the protocol's are {sorted(arms)}")
        self.setup(narrowed)
        self.sweep_and_select()
        self.out_of_sample(arms)
        self.mark_and_recheck()
        self.gate()

    def cleanup(self) -> None:
        """Remove the junction by itself, then the worktree, then show the store is as it was. Idempotent."""
        if not self.wt.exists():
            return
        if self.link.exists():
            self.hop(
                "junction-remove", ["cmd", "/c", "rmdir", str(self.link)], self.wt.parent, Expect(0)
            )
        self.check(
            "junction-gone",
            "the junction is gone before the worktree is removed",
            "the junction is still there; the worktree is NOT removed"
            if self.link.exists()
            else None,
        )
        self.hop(
            "worktree-remove",
            ["git", "-C", str(self.config.repo), "worktree", "remove", "--force", str(self.wt)],
            self.config.repo,
            Expect(0),
        )
        after = file_count(self.config.store)
        before = self._store_before
        self.check(
            "store-untouched",
            f"the canonical store holds {before} files before and after",
            None if before is None or before == after else f"{before} before, {after} after",
            f"{before} -> {after}",
        )


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s6_rehearsal.py",
        description="Rehearse the S6/S7 chain in a throwaway worktree (R-CL).",
    )
    parser.add_argument(
        "--root", required=True, type=Path, help="where the cases live, OUTSIDE the repository"
    )
    parser.add_argument(
        "--store", required=True, type=Path, help="the canonical mainnet-historical store"
    )
    parser.add_argument("--case", choices=("pass", "fail", "both"), default="both")
    parser.add_argument(
        "--python", default=sys.executable, help="the interpreter that builds each venv"
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--keep", action="store_true", help="do not remove a case's worktree when it passes"
    )
    parser.add_argument(
        "--label",
        default=None,
        help="this invocation's directory under --root (default: the UTC time); a label already used is refused",
    )
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="remove the named case(s) worktree under --label and stop",
    )
    return parser


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def main(argv: Sequence[str] | None = None, *, run: Run = real_run) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.clean_only and args.label is None:
        parser.error("--clean-only needs the --label of the invocation whose worktree it removes")
    label: str = args.label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    repo: Path = args.repo
    if _inside(args.root, repo) or _inside(repo, args.root):
        print("REFUSED: --root must be outside the repository and not contain it", file=sys.stderr)
        return EXIT_REFUSED
    if not args.store.is_dir():
        print(f"REFUSED: the store {args.store} is not a directory", file=sys.stderr)
        return EXIT_REFUSED
    protocol_text = (repo / "docs" / "research" / "PROTOCOL.md").read_text(encoding="utf-8")
    config = Config(repo, args.root, args.store, args.python, keep=args.keep, label=label)
    cases = CASES if args.case == "both" else (args.case,)
    status = 0
    for case in cases:
        rehearsal = Rehearsal(case, config, run=run)
        if args.clean_only:
            rehearsal.cleanup()
            continue
        if rehearsal.base.exists():
            print(
                f"REFUSED: {rehearsal.base} exists; an invocation's evidence is never overwritten, "
                "so use another --label (or --clean-only with this one)",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        try:
            rehearsal.go(protocol_text)
        except HopMismatchError as exc:
            print(f"[{case}] STOPPED: {exc}; the worktree is kept at {rehearsal.wt}")
            status = EXIT_MISMATCH
            break
        if not config.keep:
            try:
                rehearsal.cleanup()
            except HopMismatchError as exc:
                print(f"[{case}] CLEANUP STOPPED: {exc}")
                status = EXIT_MISMATCH
                break
        print(f"[{case}] DONE: {len(rehearsal.records)} hops, every one matched")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
