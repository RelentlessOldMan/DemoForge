"""Pluggable runtimes: how a demo's working copy is executed/validated.

Phase 2 ships the ``octave`` runtime (the first content set's ``.m`` demos run on
GNU Octave — no MATLAB license here, see docs/architecture.md §10). Python/Node
runtimes slot in behind the same tiny surface later.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from demoforge.errors import DemoForgeError


class RuntimeUnavailable(DemoForgeError):
    """A required runtime binary is not configured or not found on disk."""


def resolve_binary(runtime: str, runtimes: dict[str, str]) -> Path:
    """Resolve a runtime's executable from a content set's ``[runtimes]`` map.

    ``runtimes`` is ``ContentSetConfig.runtimes`` (e.g. the pinned octave path).
    """
    configured = runtimes.get(runtime)
    if not configured:
        raise RuntimeUnavailable(
            f"runtime {runtime!r} is not configured; add it to [runtimes] in demoforge.toml"
        )
    path = Path(configured)
    # A bare command name (e.g. "python") is resolved by the OS; an explicit path
    # must exist so we fail early with a clear message instead of a cryptic OSError.
    if (path.parent != Path(".")) and not path.exists():
        raise RuntimeUnavailable(f"runtime {runtime!r} not found at {path}")
    return path


def run_octave_script(
    octave_bin: Path,
    work_dir: Path,
    script: str,
    *,
    timeout: float | None = 300.0,
) -> subprocess.CompletedProcess[str]:
    """Run ``script`` (a filename resolvable in ``work_dir``) under octave-cli.

    ``work_dir`` is both the CWD and on the load path, so the script can call
    function files staged alongside it and read inputs by basename.
    """
    cmd = [str(octave_bin), "--norc", "--quiet", script]
    return _run(cmd, work_dir, timeout)


def run_python_script(
    python_bin: Path,
    work_dir: Path,
    script: str,
    *,
    timeout: float | None = 300.0,
) -> subprocess.CompletedProcess[str]:
    """Run ``script`` under the Python runtime, with ``work_dir`` as CWD.

    Decodes as UTF-8 so a harness's output is console-code-page independent.
    """
    cmd = [str(python_bin), script]
    return _run(cmd, work_dir, timeout)


def _run(cmd: list[str], work_dir: Path, timeout: float | None):
    try:
        return subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        # A bare runtime name (e.g. "octave") that isn't actually on PATH surfaces
        # here, not at resolve_binary — turn it into the same clear failure.
        raise RuntimeUnavailable(f"runtime executable not found: {cmd[0]!r}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DemoForgeError(
            f"runtime command timed out after {timeout:g}s: {cmd[0]!r}"
        ) from exc
