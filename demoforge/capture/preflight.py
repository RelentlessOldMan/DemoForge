"""Pre-capture environment checks.

``run`` is the one stage that spends real agent time, and it is the one stage
whose result cannot be recomputed. So anything knowably wrong about the
environment should be caught *before* the agent is invoked, not discovered
afterwards in a failing verdict.

The specific failure this exists to prevent: a demo whose prompt points at a PDF
needs the agent's Read tool to rasterize it, which needs ``pdftoppm`` on the
agent's ``PATH``. A Windows process inherits its environment at creation and
never refreshes it, so a tool installed after the launching shell started is
invisible to every descendant — including the agent. The capture then fails
because of a stale ``PATH``, which is indistinguishable, in the verdict, from the
demo being too hard. That is a bad capture *and* wasted agent time.

The engine stays domain-agnostic: it knows a demo ``requires`` some executable
names, and that the content set's ``[capture] path_prepend`` says where tools
live on this machine. It knows nothing about PDFs or poppler.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from demoforge.config import CaptureConfig
from demoforge.model import Demo

PATH_SEP = os.pathsep

# Credentials that make the Claude CLI bill an API account instead of the
# subscription it is logged in with. Captures are a user's own interactive-style
# runs, so they should cost what that user's own runs cost; a key that happens to
# be in the launching shell (set for some other tool) must not silently redirect
# the bill. Stripped from the agent's environment only — never from DemoForge's.
BILLING_ENV_VARS = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


def capture_env(
    capture: CaptureConfig | None = None,
    *,
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build the environment for the captured agent.

    ``path_prepend`` entries go in front of the inherited ``PATH`` so a pinned
    tool wins over anything of the same name already there. Non-existent
    directories are dropped rather than raising: a content set is shared across
    machines, and a path that is only meaningful on one of them should not break
    capture on the others. :func:`missing_requirements` is what actually reports
    a tool the demo needs and cannot find.

    API-billing credentials (:data:`BILLING_ENV_VARS`) are removed, so the agent
    authenticates with the CLI's own login.
    """
    env = dict(os.environ if base is None else base)
    for name in BILLING_ENV_VARS:
        env.pop(name, None)
    entries = [d for d in (capture.path_prepend if capture else ()) if Path(d).is_dir()]
    if entries:
        current = env.get("PATH", "")
        env["PATH"] = PATH_SEP.join([*entries, current]) if current else PATH_SEP.join(entries)
    return env


def resolve_tool(name: str, env: dict[str, str]) -> str | None:
    """Locate executable ``name`` on ``env``'s PATH, or return ``None``.

    Resolved against the *capture* PATH, not DemoForge's own — the question is
    always what the agent will be able to run.
    """
    return shutil.which(name, path=env.get("PATH"))


def missing_requirements(demo: Demo, env: dict[str, str]) -> tuple[str, ...]:
    """Which of ``demo.requires`` the agent would not be able to run."""
    return tuple(name for name in demo.requires if resolve_tool(name, env) is None)


@dataclass(frozen=True)
class Preflight:
    """What the environment can and cannot give this demo's agent."""

    demo_id: str
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing

    def message(self) -> str:
        """A failure message that says what is wrong *and* how to fix it."""
        tools = ", ".join(self.missing)
        plural = "tools" if len(self.missing) > 1 else "tool"
        return (
            f"demo {self.demo_id!r} requires {plural} the agent cannot run: {tools}. "
            f"Refusing to capture, because the run would fail for an environmental "
            f"reason rather than a real one — and spend agent time doing it.\n"
            f"Fix either by installing the {plural}, or — if already installed — by "
            f"adding the directory to [capture] path_prepend in the content set's "
            f"demoforge.toml. Note that a tool installed after the current shell "
            f"started is invisible to it until a NEW shell is opened; restarting "
            f"Claude Code alone does not refresh an inherited PATH."
        )


def preflight(demo: Demo, env: dict[str, str]) -> Preflight:
    """Check ``demo``'s declared requirements against the capture environment."""
    return Preflight(demo_id=demo.id, missing=missing_requirements(demo, env))
