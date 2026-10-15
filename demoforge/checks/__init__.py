"""Property-based checks: an extensible registry of success criteria.

DemoForge verifies a run by *measurable property* — tests pass, speedup ≥ N,
error < tol, artifact exists, report cites evidence — never by byte-exact output
comparison (architecture.md §6). Each check ``kind`` is a plugin registered here;
content sets can add their own by importing and calling :func:`register`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from demoforge.errors import CheckError
from demoforge.model import Check, CheckResult


@dataclass
class CheckContext:
    """Everything a check needs to evaluate a finished run.

    ``work_dir`` is where the run's artifacts live (the bundle's ``artifacts/`` or
    the live working copy). ``metrics`` are numbers the run harness measured
    (e.g. ``{"speedup": 4.2, "max_abs_error": 3e-12}``) that metric/threshold
    checks read from.
    """

    work_dir: Path
    metrics: dict[str, Any] = field(default_factory=dict)


class CheckKind:
    """Base class for a check implementation.

    Subclasses set :attr:`kind` and implement :meth:`evaluate`; override
    :meth:`validate` to enforce required params at load time.
    """

    kind: str = ""

    def validate(self, check: Check) -> None:  # noqa: D401 - simple hook
        """Raise :class:`CheckError` if ``check.params`` is malformed."""

    def evaluate(self, check: Check, ctx: CheckContext) -> CheckResult:
        raise NotImplementedError

    # helpers -----------------------------------------------------------
    def require(self, check: Check, *names: str) -> None:
        missing = [n for n in names if n not in check.params]
        if missing:
            raise CheckError(
                f"check {check.id!r} (kind {self.kind!r}) is missing required "
                f"param(s): {', '.join(missing)}"
            )


_REGISTRY: dict[str, CheckKind] = {}


def register(impl: CheckKind | type[CheckKind]) -> CheckKind:
    """Register a check kind. Usable as a decorator on a :class:`CheckKind` subclass."""
    inst = impl() if isinstance(impl, type) else impl
    if not inst.kind:
        raise CheckError("check kind must define a non-empty 'kind'")
    _REGISTRY[inst.kind] = inst
    return inst


def get_kind(kind: str) -> CheckKind:
    try:
        return _REGISTRY[kind]
    except KeyError:
        raise CheckError(
            f"unknown check kind {kind!r}; known kinds: {', '.join(sorted(_REGISTRY))}"
        ) from None


def known_kinds() -> list[str]:
    return sorted(_REGISTRY)


def validate_check(check: Check) -> None:
    """Validate a single check against its registered kind (load-time guard)."""
    get_kind(check.kind).validate(check)


def run_check(check: Check, ctx: CheckContext) -> CheckResult:
    """Evaluate a single check and return its :class:`CheckResult`."""
    return get_kind(check.kind).evaluate(check, ctx)


def run_checks(checks: list[Check], ctx: CheckContext) -> list[CheckResult]:
    return [run_check(c, ctx) for c in checks]


# Importing the built-in kinds registers them as a side effect.
from demoforge.checks import kinds as _kinds  # noqa: E402,F401

__all__ = [
    "CheckContext",
    "CheckKind",
    "register",
    "get_kind",
    "known_kinds",
    "validate_check",
    "run_check",
    "run_checks",
]
