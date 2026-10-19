"""Content-set configuration (``demoforge.toml``).

Set-level presentation defaults and runtime pins. Individual demos are *not*
configured here — they are auto-discovered from ``demos/*/demo.yaml``
(see :mod:`demoforge.discovery`). This keeps "adding a demo" a one-folder action.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from demoforge.errors import ConfigError

CONFIG_FILENAME = "demoforge.toml"
# Per-machine overrides beside demoforge.toml (git-ignored): tool locations and
# where captures run differ from one machine to the next, so they are not content.
LOCAL_CONFIG_FILENAME = "demoforge.local.toml"
_LOCAL_TABLES = ("capture", "runtimes")


@dataclass(frozen=True)
class NarrationConfig:
    enabled: bool = True
    provider: str = "piper"
    voice: str = "en_US-amy-medium"


@dataclass(frozen=True)
class PresentationConfig:
    intro: bool = True
    # A card after the title listing where each demo starts, to skip to it.
    contents: bool = True
    outro: bool = True


@dataclass(frozen=True)
class CaptureConfig:
    """How the ``run`` stage launches the agent.

    ``path_prepend`` holds directories prepended to the captured agent's ``PATH``.
    A demo's ``requires`` names the *tool*; this names *where it lives on this
    machine*, which is per-machine and therefore config, not demo content. It
    exists because an agent inherits its environment from whatever shell launched
    DemoForge, so a tool installed after that shell started is invisible to it —
    and the resulting capture fails for an environmental reason that looks
    exactly like the demo being too hard.
    """

    path_prepend: tuple[str, ...] = ()
    # Where the agent's scratch folder is created. Empty means the system temp
    # dir. Recorded paths show this location, so a short neutral one reads best.
    sandbox_root: str = ""


@dataclass(frozen=True)
class ContentSetConfig:
    """Parsed ``demoforge.toml``."""

    id: str
    title: str
    subtitle: str = ""
    description: str = ""
    presentation: PresentationConfig = field(default_factory=PresentationConfig)
    narration: NarrationConfig = field(default_factory=NarrationConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    runtimes: dict[str, str] = field(default_factory=dict)
    # [display] paths: local path prefixes rewritten in everything rendered
    # (see demoforge.redact). Captured bundles keep the real paths.
    display_paths: tuple[tuple[str, str], ...] = ()

    @classmethod
    def load(cls, path: Path) -> "ContentSetConfig":
        """Load and validate a ``demoforge.toml`` at ``path``."""
        if not path.exists():
            raise ConfigError(f"no {CONFIG_FILENAME} found at {path}")
        try:
            with path.open("rb") as fh:
                data: dict[str, Any] = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
        local = path.with_name(LOCAL_CONFIG_FILENAME)
        if local.exists():
            try:
                with local.open("rb") as fh:
                    overrides: dict[str, Any] = tomllib.load(fh)
            except tomllib.TOMLDecodeError as exc:
                raise ConfigError(f"{local} is not valid TOML: {exc}") from exc
            unknown = set(overrides) - set(_LOCAL_TABLES)
            if unknown:
                raise ConfigError(
                    f"{local}: only {", ".join(_LOCAL_TABLES)} may be overridden locally, "
                    f"not {", ".join(sorted(unknown))}"
                )
            for name in _LOCAL_TABLES:
                if name in overrides:
                    data[name] = {**(data.get(name) or {}), **overrides[name]}

        set_tbl = data.get("set")
        if not isinstance(set_tbl, dict) or "id" not in set_tbl:
            raise ConfigError(f"{path} must contain a [set] table with an 'id'")

        pres = data.get("presentation", {}) or {}
        narr = data.get("narration", {}) or {}
        cap = data.get("capture", {}) or {}
        runtimes = {k: str(v) for k, v in (data.get("runtimes", {}) or {}).items()}
        paths = (data.get("display", {}) or {}).get("paths", {}) or {}
        if not isinstance(paths, dict):
            raise ConfigError(f"{path}: [display] paths must be a table of from = to")

        prepend = cap.get("path_prepend", ()) or ()
        if isinstance(prepend, str):
            raise ConfigError(
                f"{path}: [capture] path_prepend must be a list of directories, not a string"
            )

        return cls(
            id=str(set_tbl["id"]),
            title=str(set_tbl.get("title", set_tbl["id"])),
            subtitle=str(set_tbl.get("subtitle", "")),
            description=str(set_tbl.get("description", "")),
            presentation=PresentationConfig(
                intro=bool(pres.get("intro", True)),
                contents=bool(pres.get("contents", True)),
                outro=bool(pres.get("outro", True)),
            ),
            narration=NarrationConfig(
                enabled=bool(narr.get("enabled", True)),
                provider=str(narr.get("provider", "piper")),
                voice=str(narr.get("voice", "en_US-amy-medium")),
            ),
            capture=CaptureConfig(
                path_prepend=tuple(str(p) for p in prepend),
                sandbox_root=str(cap.get("sandbox_root", "") or ""),
            ),
            runtimes=runtimes,
            display_paths=_display_rules(
                path, paths, (data.get("display", {}) or {}).get("home")
            ),
        )


def _display_rules(
    path: Path, paths: dict[str, Any], home: Any
) -> tuple[tuple[str, str], ...]:
    """The path rewrites for rendered and frozen output.

    ``home`` stands in for the home folder of whoever runs DemoForge, so a set's
    committed config never has to name anyone's real user folder.
    """
    rules = [(str(k), str(v)) for k, v in paths.items()]
    if home is not None:
        if not isinstance(home, str) or not home:
            raise ConfigError(f"{path}: [display] home must be a folder path")
        real = str(Path.home())
        if real not in dict(rules):
            rules.append((real, home))
    return tuple(rules)
