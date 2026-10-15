"""Staleness detection: does an approved bundle still match its demo?

Every bundle records the ``prompt_hash`` and ``input_hashes`` of the demo as it
stood when the run was captured (architecture.md §7). Editing ``prompt.md`` or an
input afterwards does not corrupt the bundle — it remains a faithful record of
*that* run — but it no longer answers the question the demo now asks, and the
rendered record and deck would show the captured (old) prompt with no warning.

Comparing the recorded hashes against the demo on disk is a pure function of
committed files, so it belongs on the deterministic side of the pipeline. This
module is also the single definition of how those hashes are computed, so capture
and staleness cannot drift apart.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from demoforge.discovery import ContentSet
from demoforge.model import Demo, RunBundle


def prompt_hash(demo: Demo) -> str:
    """Hash of the demo's prompt text, newline-normalized by text-mode reading."""
    return hash_text(demo.prompt_path.read_text(encoding="utf-8"))


def user_hash(demo: Demo) -> str | None:
    """Hash of the demo's ``user.md`` brief, or ``None`` if it has none."""
    path = demo.user_path
    if path is None or not path.is_file():
        return None
    return hash_text(path.read_text(encoding="utf-8"))


def input_hashes(demo: Demo) -> dict[str, str]:
    """Staged-relpath → content hash for every input that exists on disk."""
    return {rel: hash_file(p) for p, rel in demo.staged_inputs() if p.exists()}


@dataclass(frozen=True)
class Staleness:
    """What changed in a demo since one of its runs was captured.

    ``unrecorded`` means the bundle predates hash recording, so staleness is
    unknowable — reported, but never treated as stale (we do not fabricate a
    verdict we cannot support).
    """

    demo_id: str
    prompt_changed: bool = False
    user_changed: bool = False
    inputs_changed: tuple[str, ...] = ()
    inputs_added: tuple[str, ...] = ()
    inputs_removed: tuple[str, ...] = ()
    unrecorded: bool = False

    @property
    def is_stale(self) -> bool:
        return bool(
            self.prompt_changed
            or self.user_changed
            or self.inputs_changed
            or self.inputs_added
            or self.inputs_removed
        )

    def reasons(self) -> list[str]:
        """Human-readable reasons, most significant first. Empty when fresh."""
        out: list[str] = []
        if self.prompt_changed:
            out.append("prompt.md changed since capture")
        if self.user_changed:
            out.append("user.md changed since capture")
        for label, names in (
            ("input changed", self.inputs_changed),
            ("input added", self.inputs_added),
            ("input removed", self.inputs_removed),
        ):
            for name in names:
                out.append(f"{label}: {name}")
        return out

    def summary(self) -> str:
        if self.unrecorded:
            return "no recorded hashes — staleness unknown (re-capture to record them)"
        if not self.is_stale:
            return "up to date with the demo"
        return "; ".join(self.reasons())


def bundle_staleness(demo: Demo, bundle: RunBundle) -> Staleness:
    """Compare ``bundle``'s recorded demo hashes against ``demo`` on disk."""
    meta = bundle.read_metadata()
    if not meta.prompt_hash and not meta.input_hashes:
        return Staleness(demo_id=demo.id, unrecorded=True)

    recorded = dict(meta.input_hashes)
    current = input_hashes(demo)
    return Staleness(
        demo_id=demo.id,
        prompt_changed=bool(meta.prompt_hash) and meta.prompt_hash != prompt_hash(demo),
        # A bundle from before briefs were hashed has none: only a recorded hash
        # can show a change.
        user_changed=bool(meta.user_hash) and meta.user_hash != user_hash(demo),
        inputs_changed=tuple(
            sorted(k for k in recorded.keys() & current.keys() if recorded[k] != current[k])
        ),
        inputs_added=tuple(sorted(current.keys() - recorded.keys())),
        inputs_removed=tuple(sorted(recorded.keys() - current.keys())),
    )


def approved_staleness(cs: ContentSet, demo: Demo) -> Staleness | None:
    """Staleness of the demo's approved bundle, or ``None`` if it has none."""
    root = cs.approved_dir_for(demo.id)
    bundle = RunBundle(root)
    if not bundle.exists():
        return None
    return bundle_staleness(demo, bundle)


def stale_approved(cs: ContentSet, demos: list[Demo] | None = None) -> list[Staleness]:
    """Every approved demo whose prompt or inputs have changed since capture."""
    out: list[Staleness] = []
    for demo in demos if demos is not None else cs.demos():
        st = approved_staleness(cs, demo)
        if st is not None and st.is_stale:
            out.append(st)
    return out


def hash_text(text: str) -> str:
    """Canonical content hash for prompt text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path) -> str:
    """Canonical content hash for an input file (exact bytes)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
