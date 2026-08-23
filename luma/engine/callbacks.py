"""
The seam between the download engine and whatever is displaying it.

The engine never prints. It reports through this object, so the same engine
drives the CLI test harness, the Textual UI, or a test double without change.

Every callback is optional; the defaults do nothing, so a caller can supply
only the events it cares about.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


def _ignore(*_args, **_kwargs):
    """Default no-op callback."""


@dataclass
class EngineCallbacks:
    """Callbacks the engine invokes as work progresses.

    Note on threads: when downloads run, these fire from worker threads, not
    the caller's thread. A UI implementation is responsible for marshalling
    back to its own thread (in Textual, via ``App.call_from_thread``).
    """

    #: General progress text not tied to one video ("Measuring connection...").
    on_status: Callable[[str], None] = field(default=_ignore)

    #: Installing an external tool: (description, bytes_done, bytes_total).
    #: ``bytes_total`` is 0 when the server did not report a length.
    on_tool_progress: Callable[[str, int, int], None] = field(default=_ignore)

    #: A video started. (tag, url)
    on_video_start: Callable[[str, str], None] = field(default=_ignore)

    #: A human-readable milestone for one video. (tag, message)
    on_video_status: Callable[[str, str], None] = field(default=_ignore)

    #: The video's real title, once known. (tag, title)
    on_video_title: Callable[[str, str], None] = field(default=_ignore)

    #: Live progress for one video. (tag, parsed) where ``parsed`` is the dict
    #: returned by :func:`luma.engine.download.parse_progress`.
    on_video_progress: Callable[[str, dict], None] = field(default=_ignore)

    #: A video finished. (tag, url, ok, reason, filepath)
    #: ``reason`` is empty on success; ``filepath`` may be None if unknown.
    on_video_done: Callable[[str, str, bool, str, Optional[str]], None] = field(
        default=_ignore
    )
