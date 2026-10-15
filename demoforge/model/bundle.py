"""Run-bundle types: the frozen record of a single agent run.

A run bundle lives at ``runs/<demo>/<run-id>/`` and, once approved, is copied
immutably to ``approved/<demo>/``. Downstream rendering reads *only* these types,
never the Claude CLI's internal shapes — see docs/architecture.md §5.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Canonical event vocabulary (architecture.md §5.1). The raw stream-json from the
# Claude CLI is normalized into exactly these types so the renderer is insulated
# from CLI-internal changes.
EVENT_TYPES = frozenset(
    {
        "prompt",
        "user_message",
        "user_done",
        "assistant_text",
        "tool_call",
        "file_read",
        "file_search",
        "file_write",
        "file_edit",
        "command",
        "command_output",
        "test_result",
        "artifact",
        "completion",
    }
)


@dataclass(frozen=True)
class Event:
    """One normalized, observable event on the run timeline.

    ``t`` is relative seconds from run start and is informational only — the
    renderer re-times the presentation (architecture.md §5.1, video §5.2). No
    internal model reasoning is ever captured here.
    """

    seq: int
    t: float
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unknown event type {self.type!r}")

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"seq": self.seq, "t": self.t, "type": self.type}
        out.update(self.data)
        return out

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Event":
        data = {k: v for k, v in obj.items() if k not in ("seq", "t", "type")}
        return cls(seq=int(obj["seq"]), t=float(obj["t"]), type=str(obj["type"]), data=data)


@dataclass
class RunMetadata:
    """Reproducibility metadata (architecture.md §7). Recorded where practical."""

    demo_id: str
    model: str | None = None
    created: str | None = None  # ISO-8601 UTC
    capture_mode: str = "headless"  # interactive | headless
    git_commit: str | None = None
    git_dirty: bool | None = None  # uncommitted changes when the run was captured
    prompt_hash: str | None = None
    user_hash: str | None = None  # the demo's user.md brief, when it has one
    input_hashes: dict[str, str] = field(default_factory=dict)
    runtimes: dict[str, str] = field(default_factory=dict)
    os: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "RunMetadata":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        kwargs = {k: v for k, v in obj.items() if k in known}
        return cls(**kwargs)


@dataclass(frozen=True)
class CheckResult:
    """Outcome of evaluating one :class:`~demoforge.model.demo.Check`.

    ``passed`` is ``None`` for informational ``metric`` checks (they surface a
    number but never fail a demo). ``value`` is the measured quantity for display.
    """

    id: str
    kind: str
    passed: bool | None
    value: Any = None
    message: str = ""

    @property
    def is_metric(self) -> bool:
        return self.passed is None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "CheckResult":
        return cls(
            id=str(obj["id"]),
            kind=str(obj["kind"]),
            passed=obj.get("passed"),
            value=obj.get("value"),
            message=str(obj.get("message", "")),
        )


@dataclass
class Results:
    """The collected check outcomes for a run (``results.json``)."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A demo passes if every non-``metric`` check passed."""
        return all(c.passed for c in self.checks if c.passed is not None)

    def metrics(self) -> dict[str, Any]:
        """Displayable name → value map from metric checks."""
        return {c.id: c.value for c in self.checks if c.is_metric}

    def to_json(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [c.to_json() for c in self.checks],
        }

    @classmethod
    def from_json(cls, obj: dict[str, Any]) -> "Results":
        return cls(checks=[CheckResult.from_json(c) for c in obj.get("checks", [])])


def new_run_id(when: datetime | None = None, *, seed: str = "") -> str:
    """Generate an immutable, sortable run id: ``<UTC-timestamp>-<shorthash>``.

    The timestamp makes run dirs sort chronologically; the short hash keeps ids
    unique within a second. ``seed`` (e.g. the prompt hash) diversifies the hash.
    """
    when = when or datetime.now(timezone.utc)
    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha1(f"{stamp}{seed}".encode()).hexdigest()[:8]
    return f"{stamp}-{digest}"


# Standard file names inside a bundle (architecture.md §5).
BUNDLE_METADATA = "metadata.json"
BUNDLE_PROMPT = "prompt.md"
BUNDLE_TRANSCRIPT_JSONL = "transcript.jsonl"
BUNDLE_TRANSCRIPT_MD = "transcript.md"
BUNDLE_EVENTS = "events.jsonl"
BUNDLE_RESULTS = "results.json"
BUNDLE_ARTIFACTS = "artifacts"


@dataclass
class RunBundle:
    """Filesystem view of a run bundle rooted at :attr:`root`.

    Owns the layout (§5) and read/write of its parts, but not *how* a run is
    produced (that is the capture stage) — so the same type serves raw ``runs/``
    bundles and frozen ``approved/`` bundles alike.
    """

    root: Path
    # Applied to every JSON-shaped value read back (``PathRewriter.apply``), so a
    # renderer sees display paths while the files on disk keep the real ones.
    # Capture and approve never set it.
    rewrite: Callable[[Any], Any] | None = None

    def _shown(self, obj: Any) -> Any:
        return self.rewrite(obj) if self.rewrite is not None else obj

    # ---- paths ---------------------------------------------------------
    @property
    def metadata_path(self) -> Path:
        return self.root / BUNDLE_METADATA

    @property
    def prompt_path(self) -> Path:
        return self.root / BUNDLE_PROMPT

    @property
    def events_path(self) -> Path:
        return self.root / BUNDLE_EVENTS

    @property
    def transcript_jsonl_path(self) -> Path:
        return self.root / BUNDLE_TRANSCRIPT_JSONL

    @property
    def transcript_md_path(self) -> Path:
        return self.root / BUNDLE_TRANSCRIPT_MD

    @property
    def results_path(self) -> Path:
        return self.root / BUNDLE_RESULTS

    @property
    def artifacts_dir(self) -> Path:
        return self.root / BUNDLE_ARTIFACTS

    # ---- lifecycle -----------------------------------------------------
    def create(self) -> "RunBundle":
        """Create the bundle directory skeleton. Idempotent."""
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        return self

    def exists(self) -> bool:
        return self.metadata_path.exists()

    # ---- metadata ------------------------------------------------------
    def write_metadata(self, meta: RunMetadata) -> None:
        _write_json(self.metadata_path, meta.to_json())

    def read_metadata(self) -> RunMetadata:
        return RunMetadata.from_json(self._shown(_read_json(self.metadata_path)))

    # ---- events --------------------------------------------------------
    def write_events(self, events: list[Event]) -> None:
        with self.events_path.open("w", encoding="utf-8", newline="\n") as fh:
            for ev in events:
                fh.write(json.dumps(ev.to_json(), ensure_ascii=False, sort_keys=True))
                fh.write("\n")

    def read_events(self) -> list[Event]:
        events: list[Event] = []
        with self.events_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(Event.from_json(self._shown(json.loads(line))))
        return events

    # ---- results -------------------------------------------------------
    def write_results(self, results: Results) -> None:
        _write_json(self.results_path, results.to_json())

    def read_results(self) -> Results:
        return Results.from_json(self._shown(_read_json(self.results_path)))

    # ---- text ----------------------------------------------------------
    def read_text(self, path: Path) -> str:
        """A text file in the bundle (prompt, artifact), as a renderer should show it."""
        return self._shown(path.read_text(encoding="utf-8", errors="replace"))


def _write_json(path: Path, obj: Any) -> None:
    # Stable, deterministic JSON so approved bundles and re-renders are byte-stable.
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
