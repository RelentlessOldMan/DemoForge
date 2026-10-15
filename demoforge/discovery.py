"""Content-set loading and automatic demo discovery.

A *content set* is any directory with a ``demoforge.toml`` plus a ``demos/``
folder. Every subfolder of ``demos/`` that contains a ``demo.yaml`` is a demo —
discovered automatically, ordered by ``(order, id)``. Adding, removing, or
reordering a demo is therefore a pure filesystem action (architecture.md §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from demoforge.config import CONFIG_FILENAME, ContentSetConfig
from demoforge.errors import ContentSetError, DemoError
from demoforge.model import Demo, RunBundle
from demoforge.redact import PathRewriter

DEMO_MANIFEST = "demo.yaml"


@dataclass
class ContentSet:
    """A loaded content set: its config, root, and standard subdirectories."""

    root: Path
    config: ContentSetConfig

    @property
    def demos_dir(self) -> Path:
        return self.root / "demos"

    @property
    def approved_dir(self) -> Path:
        return self.root / "approved"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    def demos(self, *, enabled_only: bool = False) -> list[Demo]:
        """Discover demos under ``demos/``, sorted by ``(order, id)``."""
        demos = discover_demos(self.demos_dir)
        if enabled_only:
            demos = [d for d in demos if d.enabled]
        return demos

    def run_dir_for(self, demo_id: str, run_id: str) -> Path:
        """``runs/<demo>/<run-id>/`` — where a fresh capture is written (§5)."""
        return self.runs_dir / demo_id / run_id

    def approved_dir_for(self, demo_id: str) -> Path:
        """``approved/<demo>/`` — the frozen, committed bundle for a demo."""
        return self.approved_dir / demo_id

    @property
    def path_rewriter(self) -> PathRewriter:
        """The set's ``[display] paths`` rules (identity when there are none)."""
        return PathRewriter(self.config.display_paths)

    def display_bundle(self, demo_id: str) -> RunBundle:
        """The approved bundle as renderers should read it: display paths applied.

        Only for rendering. Capture, approve and staleness read the real bundle.
        """
        rw = self.path_rewriter
        return RunBundle(self.approved_dir_for(demo_id), rewrite=rw.apply if rw else None)


def load_content_set(root: Path) -> ContentSet:
    """Load the content set rooted at ``root`` (must contain ``demoforge.toml``)."""
    root = Path(root)
    if not root.is_dir():
        raise ContentSetError(f"{root} is not a directory")
    config_path = root / CONFIG_FILENAME
    config = ContentSetConfig.load(config_path)
    return ContentSet(root=root, config=config)


def discover_demos(demos_dir: Path) -> list[Demo]:
    """Parse every ``demos/*/demo.yaml`` under ``demos_dir``.

    Missing ``demos/`` yields an empty list (a brand-new set has no demos yet).
    Raises :class:`DemoError` on a malformed manifest or a duplicate demo id.
    """
    if not demos_dir.is_dir():
        return []

    demos: list[Demo] = []
    for child in sorted(demos_dir.iterdir()):
        manifest = child / DEMO_MANIFEST
        if not manifest.is_file():
            continue
        demos.append(_load_demo(child, manifest))

    _reject_duplicate_ids(demos)
    demos.sort(key=lambda d: (d.order, d.id))
    return demos


def _load_demo(dir: Path, manifest: Path) -> Demo:
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DemoError(f"{manifest} is not valid YAML: {exc}", path=manifest) from exc
    if data is None:
        raise DemoError("demo.yaml is empty", path=manifest)
    return Demo.from_yaml(data, dir=dir)


def _reject_duplicate_ids(demos: list[Demo]) -> None:
    seen: dict[str, Path] = {}
    for d in demos:
        if d.id in seen:
            raise DemoError(
                f"duplicate demo id {d.id!r} in {d.dir} and {seen[d.id]}", path=d.dir
            )
        seen[d.id] = d.dir
