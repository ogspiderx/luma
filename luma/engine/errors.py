"""Exceptions raised by Luma's engine.

The CLI ancestor of this engine called SystemExit when a tool could not be
installed. That would tear down a running TUI, so the engine raises catchable
exceptions instead and lets the caller decide how to show them.
"""


class LumaError(Exception):
    """Base class for engine errors that are safe to show to a user."""

    #: Short, plain-language sentence suitable for display in the UI.
    user_message = "Something went wrong."

    def __init__(self, message=None):
        self.user_message = message or self.user_message
        super().__init__(self.user_message)


class ToolInstallError(LumaError):
    """A required external tool is missing and could not be installed."""


class InvalidURLError(LumaError):
    """A URL was rejected before it reached any external tool."""


class UnsafePathError(LumaError):
    """A folder path was rejected because it escaped its allowed base."""
