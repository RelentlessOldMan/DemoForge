"""Built-in check kinds (architecture.md §6).

| kind               | asserts                                   |
|--------------------|-------------------------------------------|
| ``command``        | a command exits with the expected code    |
| ``threshold``      | a measured metric is within min/max       |
| ``numeric_tolerance`` | a measured error is within tolerance   |
| ``file_exists``    | an expected artifact was produced         |
| ``contains``       | a produced file cites (or, with ``absent: true``, never cites) text |
| ``metric``         | surfaces a number for display (no pass/fail) |

Each operates on a :class:`~demoforge.checks.CheckContext`: ``work_dir`` for
file/command checks, ``metrics`` for threshold/tolerance/metric checks.
"""

from __future__ import annotations

import re
import subprocess

from demoforge.checks import CheckContext, CheckKind, register
from demoforge.errors import CheckError
from demoforge.model import Check, CheckResult

# A command check's subprocess is capped so a hung command fails the check rather
# than blocking verification forever (matches the runtimes' default budget).
_COMMAND_TIMEOUT = 300.0


def _as_number(value) -> float | None:
    """Coerce a metric value to float, or ``None`` if it isn't numeric.

    Metrics come from a harness-written JSON file, so a malformed run can put a
    string/``null``/list where a number belongs. Returning ``None`` lets a check
    report a clean failure instead of raising deep inside ``evaluate``. ``bool`` is
    rejected: ``True``/``False`` are not meaningful threshold/tolerance values.
    """
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@register
class CommandCheck(CheckKind):
    kind = "command"

    def validate(self, check: Check) -> None:
        self.require(check, "run")

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        cmd = str(check.params["run"])
        expect = int(check.params.get("expect_exit", 0))
        # The command is trusted content-set input (committed demo.yaml), so
        # shell=True is intentional; the timeout guards against a hang, not injection.
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(ctx.work_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_COMMAND_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                id=check.id, kind=self.kind, passed=False, value=None,
                message=f"command timed out after {_COMMAND_TIMEOUT:g}s: {cmd}",
            )
        passed = proc.returncode == expect
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        msg = f"exit {proc.returncode} (expected {expect})"
        if tail and not passed:
            msg += " — " + " / ".join(tail)
        return CheckResult(id=check.id, kind=self.kind, passed=passed, value=proc.returncode, message=msg)


@register
class ThresholdCheck(CheckKind):
    kind = "threshold"

    def validate(self, check: Check) -> None:
        self.require(check, "metric")
        if "min" not in check.params and "max" not in check.params:
            raise CheckError(f"threshold check {check.id!r} needs at least one of 'min'/'max'")
        for bound in ("min", "max"):
            if bound in check.params and _as_number(check.params[bound]) is None:
                raise CheckError(f"threshold check {check.id!r}: {bound!r} must be a number")

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        metric = str(check.params["metric"])
        if metric not in ctx.metrics:
            return CheckResult(
                id=check.id, kind=self.kind, passed=False, value=None,
                message=f"metric {metric!r} was not recorded by the run",
            )
        value = _as_number(ctx.metrics[metric])
        if value is None:
            return CheckResult(
                id=check.id, kind=self.kind, passed=False, value=ctx.metrics[metric],
                message=f"metric {metric!r}={ctx.metrics[metric]!r} is not a number",
            )
        lo = _as_number(check.params.get("min"))
        hi = _as_number(check.params.get("max"))
        passed = (lo is None or value >= lo) and (hi is None or value <= hi)
        bounds = ", ".join(
            p for p in ([f"min {lo}"] if lo is not None else []) + ([f"max {hi}"] if hi is not None else [])
        )
        return CheckResult(
            id=check.id, kind=self.kind, passed=passed, value=value,
            message=f"{metric}={value} ({bounds})",
        )


@register
class NumericToleranceCheck(CheckKind):
    kind = "numeric_tolerance"

    def validate(self, check: Check) -> None:
        self.require(check, "max_abs_error")
        if _as_number(check.params["max_abs_error"]) is None:
            raise CheckError(f"tolerance check {check.id!r}: 'max_abs_error' must be a number")

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        metric = str(check.params.get("metric", "max_abs_error"))
        bound = float(check.params["max_abs_error"])
        if metric not in ctx.metrics:
            return CheckResult(
                id=check.id, kind=self.kind, passed=False, value=None,
                message=f"error metric {metric!r} was not recorded by the run",
            )
        value = _as_number(ctx.metrics[metric])
        if value is None:
            return CheckResult(
                id=check.id, kind=self.kind, passed=False, value=ctx.metrics[metric],
                message=f"error metric {metric!r}={ctx.metrics[metric]!r} is not a number",
            )
        passed = value <= bound
        return CheckResult(
            id=check.id, kind=self.kind, passed=passed, value=value,
            message=f"{metric}={value:g} (tolerance {bound:g})",
        )


@register
class FileExistsCheck(CheckKind):
    kind = "file_exists"

    def validate(self, check: Check) -> None:
        if "pattern" not in check.params and "path" not in check.params:
            raise CheckError(f"file_exists check {check.id!r} needs 'pattern' or 'path'")
        pattern = str(check.params.get("pattern") or check.params.get("path"))
        if pattern.startswith(("/", "\\")) or (len(pattern) > 1 and pattern[1] == ":"):
            raise CheckError(f"file_exists check {check.id!r}: pattern must be relative")

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        pattern = str(check.params.get("pattern") or check.params["path"])
        matches = sorted(ctx.work_dir.glob(pattern))
        passed = len(matches) > 0
        names = ", ".join(m.name for m in matches[:3])
        return CheckResult(
            id=check.id, kind=self.kind, passed=passed, value=len(matches),
            message=(f"matched {len(matches)}: {names}" if passed else f"no match for {pattern!r}"),
        )


@register
class ContainsCheck(CheckKind):
    kind = "contains"

    def validate(self, check: Check) -> None:
        self.require(check, "file")
        if "text" not in check.params and "pattern" not in check.params:
            raise CheckError(f"contains check {check.id!r} needs 'text' or 'pattern'")

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        target = ctx.work_dir / str(check.params["file"])
        if not target.is_file():
            return CheckResult(
                id=check.id, kind=self.kind, passed=False, value=False,
                message=f"file {check.params['file']!r} not found",
            )
        content = target.read_text(encoding="utf-8", errors="replace")
        if "pattern" in check.params:
            needle = str(check.params["pattern"])
            found = re.search(needle, content) is not None
            desc = f"pattern {needle!r}"
        else:
            needle = str(check.params["text"])
            found = needle in content
            desc = f"text {needle!r}"
        if check.params.get("absent", False):
            # A guard against a wrong answer: e.g. a decoy must not be named as the cause.
            return CheckResult(
                id=check.id, kind=self.kind, passed=not found, value=found,
                message=(f"absent as required: {desc}" if not found else f"must not contain {desc}"),
            )
        return CheckResult(
            id=check.id, kind=self.kind, passed=found, value=found,
            message=(f"found {desc}" if found else f"missing {desc}"),
        )


@register
class MetricCheck(CheckKind):
    """Surfaces a measured number for display; never passes or fails a demo."""

    kind = "metric"

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        name = str(check.params.get("name", check.id))
        value = ctx.metrics.get(name)
        return CheckResult(
            id=check.id, kind=self.kind, passed=None, value=value,
            message=(f"{name}={value}" if value is not None else f"{name} not recorded"),
        )
