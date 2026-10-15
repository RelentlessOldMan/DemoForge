"""The declarative demo schema (``demos/NN_name/demo.yaml``).

A :class:`Demo` is a *job*: a realistic prompt, the files staged into the agent's
working copy, the runtime that executes/validates the result, and property-based
``checks`` (never byte-exact comparison — see docs/architecture.md §6).

Parsing is intentionally strict: an invalid ``demo.yaml`` raises :class:`DemoError`
pointing at the offending file, rather than silently discovering a half-demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from demoforge.errors import DemoError

VALID_RUNTIMES = frozenset({"octave", "python", "node", "none"})


@dataclass(frozen=True)
class Check:
    """A single property-based success criterion.

    ``kind`` selects an implementation from the checks registry
    (:mod:`demoforge.checks`); ``params`` holds the kind-specific configuration
    (e.g. ``{"metric": "speedup", "min": 3.0}``). Keeping params open-ended is
    what makes the check set an extensible plugin registry.
    """

    id: str
    kind: str
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, path: Path | None = None) -> "Check":
        if not isinstance(data, dict):
            raise DemoError(f"each check must be a mapping, got {type(data).__name__}", path=path)
        if "id" not in data:
            raise DemoError("check is missing required field 'id'", path=path)
        if "kind" not in data:
            raise DemoError(f"check {data['id']!r} is missing required field 'kind'", path=path)
        reserved = {"id", "kind", "description"}
        params = {k: v for k, v in data.items() if k not in reserved}
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            description=str(data.get("description", "")),
            params=params,
        )


@dataclass(frozen=True)
class Presentation:
    """How a demo wants to be featured — *what* to show, never *how* it looks."""

    enabled: bool = True
    highlights: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Presentation":
        if not data:
            return cls()
        highlights = tuple(data.get("highlights", ()) or ())
        return cls(enabled=bool(data.get("enabled", True)), highlights=highlights)


@dataclass(frozen=True)
class Demo:
    """A discovered, validated demo. ``dir`` is the demo folder on disk."""

    id: str
    title: str
    order: int
    dir: Path
    enabled: bool = True
    prompt: str = "prompt.md"
    inputs: tuple[str, ...] = ()
    # External executables the *agent* must be able to run during capture (e.g. a
    # PDF rasterizer for a demo whose spec is a PDF). Names only — where they live
    # is per-machine, and belongs in the content set's [capture] path_prepend.
    # Checked before the agent is invoked, so a missing tool costs no agent time.
    requires: tuple[str, ...] = ()
    runtime: str = "none"
    checks: tuple[Check, ...] = ()
    narration: str | None = None
    presentation: Presentation = field(default_factory=Presentation)
    # DemoForge-owned verification harness (NOT staged into the agent's working
    # copy). Run after the agent finishes to produce `metrics_from` independently.
    harness: str | None = None
    metrics_from: str = "metrics.json"
    # Who the person asking is, for the simulated user who reads Claude's answers
    # and replies (capture/conversation.py). Not staged: Claude never sees it.
    # Without it the capture is the first prompt alone.
    user: str | None = None
    max_follow_ups: int = 3

    # ---- derived paths -------------------------------------------------
    @property
    def prompt_path(self) -> Path:
        return self.dir / self.prompt

    @property
    def narration_path(self) -> Path | None:
        return self.dir / self.narration if self.narration else None

    @property
    def user_path(self) -> Path | None:
        return self.dir / self.user if self.user else None

    @property
    def harness_path(self) -> Path | None:
        return self.dir / self.harness if self.harness else None

    def input_paths(self) -> list[Path]:
        return [self.dir / p for p in self.inputs]

    def staged_inputs(self) -> list[tuple[Path, str]]:
        """``(source, staged-relative-path)`` for each declared input.

        An input declared under the demo's ``input/`` directory keeps its path
        *relative to ``input/``*, so a demo can hand the agent a directory tree
        — e.g. a whole fictional repository with ``src/``, ``tests/``, ``logs/``
        — instead of a flat pile of files. This also keeps same-named files in
        different directories distinct (``src/README.md`` vs ``docs/README.md``),
        which a basename-only staging would collide. Anything declared outside
        ``input/`` stages at its basename.
        """
        staged: list[tuple[Path, str]] = []
        for decl in self.inputs:
            parts = PurePosixPath(decl.replace("\\", "/")).parts
            rel = "/".join(parts[1:]) if len(parts) > 1 and parts[0] == "input" else parts[-1]
            staged.append((self.dir / decl, rel))
        return staged

    # ---- parsing -------------------------------------------------------
    @classmethod
    def from_yaml(cls, data: dict[str, Any], *, dir: Path) -> "Demo":
        """Build a Demo from parsed ``demo.yaml`` data rooted at ``dir``."""
        if not isinstance(data, dict):
            raise DemoError("demo.yaml must contain a mapping at the top level", path=dir)

        for required in ("id", "title"):
            if required not in data:
                raise DemoError(f"demo.yaml is missing required field '{required}'", path=dir)

        runtime = str(data.get("runtime", "none"))
        if runtime not in VALID_RUNTIMES:
            raise DemoError(
                f"runtime {runtime!r} is not one of {sorted(VALID_RUNTIMES)}", path=dir
            )

        order = data.get("order", 0)
        try:
            order = int(order)
        except (TypeError, ValueError):
            raise DemoError(f"order must be an integer, got {order!r}", path=dir) from None

        inputs = tuple(str(p) for p in (data.get("inputs") or ()))
        for decl in inputs:
            norm = decl.replace("\\", "/")
            if norm.startswith("/") or ".." in PurePosixPath(norm).parts:
                raise DemoError(
                    f"input {decl!r} must be a relative path inside the demo "
                    f"(no absolute paths, no '..')",
                    path=dir,
                )
        requires = data.get("requires") or ()
        if isinstance(requires, str):
            raise DemoError(
                "requires must be a list of executable names, not a string", path=dir
            )
        requires = tuple(str(r) for r in requires)

        checks = tuple(
            Check.from_dict(c, path=dir) for c in (data.get("checks") or ())
        )
        _reject_duplicate_check_ids(checks, dir)

        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            order=order,
            dir=dir,
            enabled=bool(data.get("enabled", True)),
            prompt=str(data.get("prompt", "prompt.md")),
            inputs=inputs,
            requires=requires,
            runtime=runtime,
            checks=checks,
            narration=(str(data["narration"]) if data.get("narration") else None),
            presentation=Presentation.from_dict(data.get("presentation")),
            harness=(str(data["harness"]) if data.get("harness") else None),
            metrics_from=str(data.get("metrics_from", "metrics.json")),
            user=(str(data["user"]) if data.get("user") else None),
            max_follow_ups=_non_negative_int(data.get("max_follow_ups", 3), "max_follow_ups", dir),
        )


def _non_negative_int(value: Any, name: str, dir: Path) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise DemoError(f"{name} must be an integer, got {value!r}", path=dir) from None
    if n < 0:
        raise DemoError(f"{name} must not be negative, got {n}", path=dir)
    return n


def _reject_duplicate_check_ids(checks: tuple[Check, ...], dir: Path) -> None:
    seen: set[str] = set()
    for c in checks:
        if c.id in seen:
            raise DemoError(f"duplicate check id {c.id!r}", path=dir)
        seen.add(c.id)
