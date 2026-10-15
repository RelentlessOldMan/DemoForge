"""DemoForge data model: pure dataclasses, no I/O of their own beyond parsing.

- :mod:`demoforge.model.demo` — the declarative demo schema (``demo.yaml``).
- :mod:`demoforge.model.bundle` — the run-bundle types (events, metadata, results).
"""

from demoforge.model.bundle import (
    EVENT_TYPES,
    CheckResult,
    Event,
    Results,
    RunBundle,
    RunMetadata,
    new_run_id,
)
from demoforge.model.demo import Check, Demo, Presentation

__all__ = [
    "Check",
    "Demo",
    "Presentation",
    "Event",
    "EVENT_TYPES",
    "RunMetadata",
    "CheckResult",
    "Results",
    "RunBundle",
    "new_run_id",
]
