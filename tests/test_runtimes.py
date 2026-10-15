"""Runtime resolution and subprocess error handling."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from demoforge.errors import DemoForgeError
from demoforge.runtimes import (
    RuntimeUnavailable,
    resolve_binary,
    run_python_script,
)


def test_resolve_binary_requires_configuration():
    with pytest.raises(RuntimeUnavailable, match="not configured"):
        resolve_binary("octave", {})


def test_resolve_binary_rejects_missing_explicit_path(tmp_path):
    missing = tmp_path / "nope" / "octave-cli.exe"
    with pytest.raises(RuntimeUnavailable, match="not found"):
        resolve_binary("octave", {"octave": str(missing)})


def test_resolve_binary_allows_bare_command_name():
    # A bare name is resolved later by the OS; resolve_binary must not reject it.
    assert resolve_binary("python", {"python": "python"}) == Path("python")


def test_run_missing_binary_raises_runtime_unavailable(tmp_path):
    with pytest.raises(RuntimeUnavailable, match="not found"):
        run_python_script(Path("definitely-not-a-real-binary-xyz"), tmp_path, "x.py")


def test_run_timeout_raises_clean_error(tmp_path):
    script = tmp_path / "sleep.py"
    script.write_text("import time; time.sleep(5)\n", encoding="utf-8")
    with pytest.raises(DemoForgeError, match="timed out"):
        run_python_script(Path(sys.executable), tmp_path, "sleep.py", timeout=0.3)
