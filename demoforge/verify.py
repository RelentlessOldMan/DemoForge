"""Property-based verification of a finished run (architecture.md §6).

Given a demo and the artifacts a run produced, DemoForge stages an isolated
working copy, runs the demo's *independent* harness to measure authoritative
metrics, then evaluates the demo's checks against those metrics and files. This
is the engine's answer to "did the agent actually do the job?" — measured by
property, never by trusting the agent's own reported numbers.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from demoforge.checks import CheckContext, run_checks, validate_check
from demoforge.discovery import ContentSet
from demoforge.errors import DemoError, DemoForgeError
from demoforge.model import CheckResult, Demo, Results
from demoforge.runtimes import resolve_binary, run_octave_script, run_python_script


@dataclass
class VerifyOutcome:
    demo_id: str
    results: Results
    metrics: dict[str, Any] = field(default_factory=dict)
    harness_ran: bool = False
    harness_ok: bool = True
    harness_output: str = ""
    work_dir: Path | None = None

    @property
    def passed(self) -> bool:
        """The demo is verified iff its harness succeeded and all checks passed."""
        harness_gate = self.harness_ok or not self.harness_ran
        return harness_gate and self.results.passed


def stage_work_dir(demo: Demo, artifacts_dirs: list[Path], dest: Path) -> Path:
    """Stage the demo's inputs + produced artifacts into ``dest``.

    Inputs keep their structure relative to the demo's ``input/`` dir (see
    :meth:`Demo.staged_inputs`), so a demo that hands the agent a directory tree
    verifies against that same tree. Later ``artifacts_dirs`` override earlier
    ones and override inputs, mirroring a real run where the agent's output sits
    on top of the files it started with. Artifacts keep their relative paths, so
    a fix the agent made in ``src/gate.m`` replaces ``src/gate.m``.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for src, rel in demo.staged_inputs():
        if not src.exists():
            raise DemoError(f"declared input is missing: {src}", path=demo.dir)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    for adir in artifacts_dirs:
        if not adir.is_dir():
            raise DemoError(f"artifacts dir does not exist: {adir}", path=demo.dir)
        for f in sorted(p for p in adir.rglob("*") if p.is_file()):
            target = dest / f.relative_to(adir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
    return dest


def verify_demo(
    demo: Demo,
    content_set: ContentSet,
    *,
    artifacts_dirs: list[Path],
    work_dir: Path,
    octave_bin: Path | None = None,
) -> VerifyOutcome:
    """Run ``demo``'s harness + checks against ``artifacts_dirs`` in ``work_dir``."""
    for check in demo.checks:  # a malformed check must fail loudly, not pass vacuously
        validate_check(check)
    stage_work_dir(demo, artifacts_dirs, work_dir)

    harness_ran = False
    harness_ok = True
    harness_output = ""
    metrics_path = work_dir / demo.metrics_from
    if demo.harness:
        harness_ran = True
        hp = demo.harness_path
        if hp is None or not hp.exists():
            raise DemoError(f"harness not found: {demo.harness}", path=demo.dir)
        _stage_harness_dir(hp.parent, work_dir)
        # The harness is the only authority on the numbers. A metrics file the
        # agent left behind must not stand in for one the harness failed to write.
        metrics_path.unlink(missing_ok=True)
        proc = _run_harness(demo, content_set, work_dir, hp.name, octave_bin)
        harness_ok = proc.returncode == 0
        harness_output = (proc.stdout or "") + (proc.stderr or "")

    metrics = _load_metrics(metrics_path)
    ctx = CheckContext(work_dir=work_dir, metrics=metrics)
    checks = run_checks(list(demo.checks), ctx)
    if harness_ran and not harness_ok:
        # Recorded in results.json, so `passed` there is false and approve refuses.
        checks.append(CheckResult(
            id="harness", kind="harness", passed=False,
            message=_tail(harness_output) or "harness exited non-zero",
        ))
    results = Results(checks=checks)

    return VerifyOutcome(
        demo_id=demo.id,
        results=results,
        metrics=metrics,
        harness_ran=harness_ran,
        harness_ok=harness_ok,
        harness_output=harness_output,
        work_dir=work_dir,
    )


def _stage_harness_dir(harness_dir: Path, work_dir: Path) -> None:
    """Copy the harness's whole directory (e.g. checks/) into the work dir.

    This carries DemoForge-owned verification support files — such as a hidden
    reference output the agent must never see as an input — alongside the harness,
    without ever staging them into the agent's working copy during a run.
    """
    for f in sorted(harness_dir.iterdir()):
        if f.is_file():
            shutil.copy2(f, work_dir / f.name)


def _run_harness(demo: Demo, cs: ContentSet, work_dir: Path, script: str, octave_bin: Path | None):
    if demo.runtime == "octave":
        binary = octave_bin or resolve_binary("octave", cs.config.runtimes)
        return run_octave_script(binary, work_dir, script)
    if demo.runtime == "python":
        binary = resolve_binary("python", cs.config.runtimes)
        return run_python_script(binary, work_dir, script)
    raise DemoForgeError(
        f"no harness runner for runtime {demo.runtime!r} (octave/python supported)"
    )


def _tail(text: str, lines: int = 6) -> str:
    return "\n".join(text.strip().splitlines()[-lines:])


def _load_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DemoForgeError(f"metrics file {path.name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DemoForgeError(f"metrics file {path.name} must contain a JSON object")
    return data
