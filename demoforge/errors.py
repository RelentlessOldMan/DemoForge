"""Exception hierarchy for DemoForge.

All errors the engine raises deliberately derive from :class:`DemoForgeError` so
callers (and the CLI) can distinguish expected, actionable failures from bugs.
"""


class DemoForgeError(Exception):
    """Base class for all expected DemoForge errors."""


class ConfigError(DemoForgeError):
    """A content set's ``demoforge.toml`` is missing or malformed."""


class DemoError(DemoForgeError):
    """A ``demo.yaml`` is missing required fields or otherwise invalid.

    Carries the offending demo path so the CLI can point the user at it.
    """

    def __init__(self, message: str, *, path=None):
        super().__init__(message)
        self.path = path


class CheckError(DemoForgeError):
    """A check definition is invalid or a check could not be evaluated."""


class ContentSetError(DemoForgeError):
    """A directory is not a usable content set."""
