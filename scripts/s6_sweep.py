"""S6 sweep: run every declared variant once over the in-sample window at the 1.20% arm, resumably.

``python scripts/s6_sweep.py [--clone ROOT] [--workers N] [--probe] [--dry-run]``

Run from the S6 DEPLOYMENT CLONE, with its own interpreter. It makes one ``python -m trading_bot backtest``
per variant (``--start 2017-08-17 --end 2024-01-01 --stop-slippage 1.20 --strategy S --timeframe T --param
K=V ...``), so every run goes through the research-protocol guard and the evidence door exactly as an
operator's would, and each run's record names its variant by itself. **The sweep adds no state a record
does not already hold.**

**Resumable after a power cut because completion is read from the RECORDS, never from the sweep's own
notes.** Each invocation scans ``<clone>/data/backtests`` through :func:`trading_bot.backtesting.selection.read_run`,
runs only the variants that have no sealed, evidence-eligible record, and stops when there are none. A run
cut off by the power leaves a directory with no record, or an unsealed ``-running`` directory, and neither
counts (``read_run`` says so); the variant is simply run again.

**Parallel workers only after a check (R-CH).** With ``--workers N`` above 1 the sweep first runs ONE variant
alone and then the same variant beside another one, and compares the two runs' trade-log digests. Equal:
the rest runs ``N`` at a time. Unequal, or either probe run left no record: the rest runs serially, and
the manifest says why. The probe costs one extra run of that variant, which the ledger lists as a duplicate
(it agrees with the first, so it is not a conflict).

**Every variant is logged mechanically.** ``<clone>/data/s6_sweep_manifest.jsonl`` takes one flushed JSON
line per event: the start (what was done and what was missing), the parallel check, each launch and finish
with its process id, exit status and seconds, and an end line holding the whole ledger, 216 rows. After the
last run the report names every MISSING variant, every DUPLICATED one, every OFF-GRID run, every CONFLICT (two
runs of a variant whose trade logs disagree) and every skipped directory.

``--probe`` runs the first declared variant of each FAMILY AND TIMEFRAME (six: the two strategies cost very
different amounts a bar, so a probe of one strategy would not time the other), serially, and stops (the timing
probe: the runs are real in-sample evidence and count toward the 216). ``--dry-run`` prints the plan and runs
nothing.
Exit status: 0 the ledger is complete with no conflict and no failed run; 1 it is not; 2 refused.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from trading_bot.backtesting import selection as sel
from trading_bot.backtesting.protocol import ProtocolError, Variant, parse_protocol

__all__ = ["backtest_argv", "main", "order_by_cost", "sweep"]

EXIT_INCOMPLETE: Final = 1
EXIT_REFUSED: Final = 2
_STOP_SLIPPAGE: Final = "1.20"
#: Relative cost of a variant's run, for ORDER only (heaviest first so no long run starts last). The
#: weights are the bar counts of P116's measurement, rounded (1h : 4h : 1d = 24 : 6 : 1), and the
#: strategy factor is its measured per-call cost ratio (rsi about 3.8 ms a bar against about 2.5).
_TIMEFRAME_WEIGHT: Final = {"1h": 24, "4h": 6, "1d": 1}
_FAMILY_FACTOR: Final = {"rsi": 1.5}

Clock = Callable[[], datetime]
Launcher = Callable[[Sequence[str], Path, Path], "subprocess.Popen[bytes]"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# What to run
# --------------------------------------------------------------------------
def backtest_argv(python: str, variant: Variant, rules: sel.SelectionRules) -> list[str]:
    """The ``backtest`` command line of one variant: in sample, at the selection arm, both pairs."""
    argv = [
        python,
        "-m",
        "trading_bot",
        "backtest",
        "--start",
        rules.history_start.isoformat(),
        "--end",
        rules.boundary.isoformat(),
        "--stop-slippage",
        _STOP_SLIPPAGE,
        "--strategy",
        variant.family,
        "--timeframe",
        variant.timeframe,
    ]
    for name, value in variant.params.items():
        argv += ["--param", f"{name}={value}"]
    return argv


def _cost(variant: Variant) -> float:
    return _TIMEFRAME_WEIGHT.get(variant.timeframe, 1) * _FAMILY_FACTOR.get(variant.family, 1.0)


def order_by_cost(variants: Sequence[Variant]) -> list[Variant]:
    """Heaviest first; equal costs keep the declared order (the sort is stable)."""
    return sorted(variants, key=lambda v: -_cost(v))


def _label(variant: Variant) -> str:
    params = "-".join(f"{k}{v}" for k, v in sorted(variant.params.items()))
    return f"{variant.family}-{variant.timeframe}-{params}"


def _variant_json(variant: Variant) -> dict[str, Any]:
    return {
        "family": variant.family,
        "timeframe": variant.timeframe,
        "filtered": variant.filtered,
        "params": dict(sorted(variant.params.items())),
    }


# --------------------------------------------------------------------------
# The manifest
# --------------------------------------------------------------------------
class Manifest:
    """An append-only JSON-lines file: one flushed, fsynced line per event."""

    def __init__(self, path: Path, clock: Clock) -> None:
        self._path = path
        self._clock = clock
        path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, kind: str, **fields: Any) -> None:
        line = json.dumps(
            {"event": kind, "at": self._clock().isoformat(), **fields}, sort_keys=True
        )
        with self._path.open("ab") as handle:
            handle.write(line.encode("ascii") + b"\n")
            handle.flush()
            os.fsync(handle.fileno())


# --------------------------------------------------------------------------
# Launching and the pool
# --------------------------------------------------------------------------
def launch(argv: Sequence[str], cwd: Path, log_path: Path) -> subprocess.Popen[bytes]:
    """Start one worker in ``cwd`` with its console output in ``log_path``."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as handle:
        return subprocess.Popen(list(argv), cwd=cwd, stdout=handle, stderr=subprocess.STDOUT)


@dataclass(frozen=True)
class Finished:
    variant: Variant
    pid: int
    returncode: int
    seconds: float


@dataclass
class _Running:
    variant: Variant
    process: subprocess.Popen[bytes]
    started: float


def run_pool(
    variants: Sequence[Variant],
    *,
    workers: int,
    phase: str,
    argv_for: Callable[[Variant], Sequence[str]],
    root: Path,
    logs: Path,
    manifest: Manifest,
    launcher: Launcher = launch,
    poll_s: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
) -> list[Finished]:
    """Run ``variants`` at most ``workers`` at a time; every launch and finish is a manifest line.

    On an interrupt (Ctrl+C) it terminates the workers it started, records that, and re-raises.
    """
    pending = list(variants)
    running: list[_Running] = []
    finished: list[Finished] = []
    counter = 0
    try:
        while pending or running:
            while pending and len(running) < workers:
                variant = pending.pop(0)
                counter += 1
                process = launcher(
                    argv_for(variant), root, logs / f"{phase}-{counter:03d}-{_label(variant)}.log"
                )
                manifest.event(
                    "launch",
                    phase=phase,
                    variant=_variant_json(variant),
                    pid=process.pid,
                    workers=workers,
                )
                running.append(_Running(variant, process, time.monotonic()))
            sleep(poll_s)
            still: list[_Running] = []
            for item in running:
                code = item.process.poll()
                if code is None:
                    still.append(item)
                    continue
                seconds = round(time.monotonic() - item.started, 3)
                finished.append(Finished(item.variant, item.process.pid, code, seconds))
                manifest.event(
                    "finish",
                    phase=phase,
                    variant=_variant_json(item.variant),
                    pid=item.process.pid,
                    returncode=code,
                    seconds=seconds,
                )
            running = still
    except BaseException:
        for item in running:
            item.process.terminate()
        manifest.event(
            "interrupted", phase=phase, terminated=[item.process.pid for item in running]
        )
        raise
    return finished


# --------------------------------------------------------------------------
# The ledger and the parallel check (R-CH)
# --------------------------------------------------------------------------
def scan(backtests: Path, protocol: Any, rules: sel.SelectionRules) -> sel.Ledger:
    """Every run directory under ``backtests`` through the evidence door, reconciled against the variants."""
    directories = sorted(p for p in backtests.iterdir() if p.is_dir()) if backtests.is_dir() else []
    return sel.reconcile(protocol, [sel.read_run(d, protocol, rules) for d in directories])


def _names(backtests: Path) -> set[str]:
    return {p.name for p in backtests.iterdir() if p.is_dir()} if backtests.is_dir() else set()


def _digest_of(
    variant: Variant, names: set[str], backtests: Path, protocol: Any, rules: sel.SelectionRules
) -> str | None:
    """The trade-log digest of ``variant`` among the directories ``names``, or ``None`` if it has none."""
    for name in sorted(names):
        got = sel.read_run(backtests / name, protocol, rules)
        if isinstance(got, sel.PointRun) and sel.variant_key(got.variant) == sel.variant_key(
            variant
        ):
            return got.trade_log_sha256
    return None


@dataclass(frozen=True)
class Check:
    """The outcome of R-CH's check: whether parallel workers are allowed, and why."""

    performed: bool
    parallel_allowed: bool
    reason: str
    serial_digest: str | None = None
    parallel_digest: str | None = None


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SweepResult:
    ledger: sel.Ledger
    check: Check
    failed: tuple[Finished, ...]
    exit_code: int


def _ledger_rows(ledger: sel.Ledger, protocol: Any) -> list[dict[str, Any]]:
    duplicate_names = {sel.variant_key(v): names for v, names in ledger.duplicates}
    conflict_names = {sel.variant_key(v): names for v, names in ledger.conflicts}
    rows = []
    for variant in protocol.variants():
        key = sel.variant_key(variant)
        point = ledger.points.get(key)
        rows.append(
            {
                "variant": _variant_json(variant),
                "run": None if point is None else point.run,
                "trade_log_sha256": None if point is None else point.trade_log_sha256,
                "runs": list(duplicate_names.get(key, conflict_names.get(key, ()))),
                "conflict": key in conflict_names,
            }
        )
    return rows


def sweep(
    *,
    root: Path,
    backtests: Path,
    manifest_path: Path,
    logs: Path,
    protocol: Any,
    rules: sel.SelectionRules,
    python: str,
    workers: int,
    probe: bool = False,
    launcher: Launcher = launch,
    argv_for: Callable[[Variant], Sequence[str]] | None = None,
    clock: Clock = _utcnow,
    poll_s: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
) -> SweepResult:
    """Run what is missing, check parallel safety first (R-CH), and report the ledger."""
    build = argv_for if argv_for is not None else (lambda v: backtest_argv(python, v, rules))
    manifest = Manifest(manifest_path, clock)
    ledger = scan(backtests, protocol, rules)
    conflicted = {sel.variant_key(v) for v, _ in ledger.conflicts}
    todo = order_by_cost([v for v in ledger.missing if sel.variant_key(v) not in conflicted])
    if probe:
        firsts: dict[tuple[str, str], Variant] = {}
        for variant in protocol.variants():
            firsts.setdefault((variant.family, variant.timeframe), variant)
        wanted = {sel.variant_key(v) for v in firsts.values()}
        todo = [v for v in todo if sel.variant_key(v) in wanted]
    manifest.event(
        "sweep_start",
        declared=ledger.declared,
        with_a_run=len(ledger.points),
        to_run=len(todo),
        workers=workers,
        probe=probe,
        python=python,
    )
    failed: list[Finished] = []
    check = Check(False, False, "not needed: serial run requested" if workers < 2 else "")

    if workers > 1 and not probe and len(todo) >= 2:
        check = _parallel_check(
            todo,
            backtests,
            protocol,
            rules,
            build,
            root,
            logs,
            manifest,
            launcher,
            poll_s,
            sleep,
            failed,
        )
        manifest.event(
            "parallel_check",
            performed=check.performed,
            parallel_allowed=check.parallel_allowed,
            reason=check.reason,
            serial_trade_log_sha256=check.serial_digest,
            parallel_trade_log_sha256=check.parallel_digest,
        )
        ledger = scan(backtests, protocol, rules)
        conflicted = {sel.variant_key(v) for v, _ in ledger.conflicts}
        todo = order_by_cost([v for v in ledger.missing if sel.variant_key(v) not in conflicted])
    elif workers > 1 and not probe:
        check = Check(False, False, "fewer than two variants left: nothing to run beside")

    if todo:
        pool = workers if check.parallel_allowed else 1
        failed += [
            f
            for f in run_pool(
                todo,
                workers=pool,
                phase="sweep",
                argv_for=build,
                root=root,
                logs=logs,
                manifest=manifest,
                launcher=launcher,
                poll_s=poll_s,
                sleep=sleep,
            )
            if f.returncode != 0
        ]
    ledger = scan(backtests, protocol, rules)
    complete = ledger.complete and not failed and not probe
    manifest.event(
        "sweep_end",
        declared=ledger.declared,
        with_a_run=len(ledger.points),
        missing=len(ledger.missing),
        duplicates=len(ledger.duplicates),
        conflicts=len(ledger.conflicts),
        skipped=[{"run": s.run, "reason": s.reason.value} for s in ledger.skipped],
        failed=[{"variant": _variant_json(f.variant), "returncode": f.returncode} for f in failed],
        complete=complete,
        ledger=_ledger_rows(ledger, protocol),
    )
    return SweepResult(ledger, check, tuple(failed), 0 if complete else EXIT_INCOMPLETE)


def _parallel_check(
    todo: Sequence[Variant],
    backtests: Path,
    protocol: Any,
    rules: sel.SelectionRules,
    build: Callable[[Variant], Sequence[str]],
    root: Path,
    logs: Path,
    manifest: Manifest,
    launcher: Launcher,
    poll_s: float,
    sleep: Callable[[float], None],
    failed: list[Finished],
) -> Check:
    """R-CH: one variant alone, then the same variant beside another; equal trade logs allow parallel."""
    cheapest = sorted(todo, key=_cost)
    probe, beside = cheapest[0], cheapest[1]

    def pool(variants: Sequence[Variant], workers: int, phase: str) -> list[Finished]:
        return run_pool(
            variants,
            workers=workers,
            phase=phase,
            argv_for=build,
            root=root,
            logs=logs,
            manifest=manifest,
            launcher=launcher,
            poll_s=poll_s,
            sleep=sleep,
        )

    before = _names(backtests)
    serial = pool([probe], 1, "check-serial")
    middle = _names(backtests)
    together = pool([probe, beside], 2, "check-parallel")
    after = _names(backtests)
    failed += [f for f in serial + together if f.returncode != 0]
    serial_digest = _digest_of(probe, middle - before, backtests, protocol, rules)
    parallel_digest = _digest_of(probe, after - middle, backtests, protocol, rules)
    if serial_digest is None or parallel_digest is None:
        return Check(
            True,
            False,
            "a probe run left no sealed record: running serially",
            serial_digest,
            parallel_digest,
        )
    if serial_digest != parallel_digest:
        return Check(
            True,
            False,
            "the trade-log digests differ between the serial and the parallel run: running serially",
            serial_digest,
            parallel_digest,
        )
    return Check(True, True, "the trade-log digests are equal", serial_digest, parallel_digest)


# --------------------------------------------------------------------------
# The command
# --------------------------------------------------------------------------
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="s6_sweep.py",
        description="Run the S6 in-sample sweep (PROTOCOL.md section 6), resumably.",
    )
    parser.add_argument(
        "--clone", type=Path, default=Path.cwd(), help="the deployment clone's root"
    )
    parser.add_argument("--protocol", type=Path, default=None, help="the protocol file")
    parser.add_argument("--python", default=sys.executable, help="the interpreter for the workers")
    parser.add_argument(
        "--workers", type=int, default=1, help="parallel workers, after R-CH's check"
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="run the first variant of each family and timeframe, serially",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan and run nothing")
    return parser


def _report(result: SweepResult, protocol: Any) -> str:
    ledger = result.ledger
    lines = [
        "S6 SWEEP LEDGER",
        f"  variants declared {ledger.declared}; with a sealed evidence-eligible record {len(ledger.points)}",
        f"  parallel check: {result.check.reason or 'not performed'}",
    ]
    for variant in ledger.missing:
        lines.append(f"  MISSING {sel.variant_key(variant)}")
    for variant, names in ledger.duplicates:
        lines.append(f"  DUPLICATED {sel.variant_key(variant)}: {', '.join(names)}")
    for variant, names in ledger.conflicts:
        lines.append(f"  CONFLICT {sel.variant_key(variant)}: {', '.join(names)}")
    for skipped in ledger.skipped:
        tag = "OFF-GRID" if skipped.reason is sel.SkipReason.OFF_GRID else "SKIPPED"
        lines.append(f"  {tag} {skipped.run}: {skipped.reason.value}: {skipped.detail}")
    for finished in result.failed:
        lines.append(
            f"  FAILED {sel.variant_key(finished.variant)}: exit status {finished.returncode}"
        )
    lines.append(f"  {'COMPLETE' if result.exit_code == 0 else 'NOT COMPLETE'}")
    return "\n".join(lines) + "\n"


def main(
    argv: Sequence[str] | None = None, *, launcher: Launcher = launch, poll_s: float = 0.2
) -> int:
    args = _parser().parse_args(argv)
    if args.workers < 1:
        print("REFUSED: --workers must be at least 1", file=sys.stderr)
        return EXIT_REFUSED
    root: Path = args.clone
    protocol_file: Path = (
        args.protocol if args.protocol is not None else root / "docs" / "research" / "PROTOCOL.md"
    )
    try:
        text = protocol_file.read_text(encoding="utf-8")
        protocol = parse_protocol(text)
        rules = sel.parse_rules(text)
    except (OSError, ProtocolError, sel.SelectionRulesError) as exc:
        print(f"REFUSED: the protocol cannot be used: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    backtests = root / "data" / "backtests"
    if args.dry_run:
        ledger = scan(backtests, protocol, rules)
        todo = order_by_cost(ledger.missing)
        print(
            f"plan: {len(todo)} of {ledger.declared} variants to run; {len(ledger.points)} already have a record"
        )
        for variant in todo[:3]:
            print("  first: " + " ".join(backtest_argv(args.python, variant, rules)))
        return 0
    result = sweep(
        root=root,
        backtests=backtests,
        manifest_path=root / "data" / "s6_sweep_manifest.jsonl",
        logs=root / "data" / "s6_sweep_logs",
        protocol=protocol,
        rules=rules,
        python=args.python,
        workers=args.workers,
        probe=args.probe,
        launcher=launcher,
        poll_s=poll_s,
    )
    print(_report(result, protocol), end="")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
