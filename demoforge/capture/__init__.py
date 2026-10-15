"""Capture: the one non-deterministic stage.

Invokes the agent headlessly, normalizes its raw event stream into the canonical
run-bundle vocabulary, then verifies the result by property. Everything the
capture writes is a frozen record; nothing downstream re-runs the agent.
"""

from demoforge.capture.normalize import normalize
from demoforge.capture.run import RunResult, approve_run, run_demo

__all__ = ["normalize", "run_demo", "approve_run", "RunResult"]
