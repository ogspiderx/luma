from dataclasses import dataclass, field
from typing import Callable, Optional


def _ignore(*_args, **_kwargs):
    pass


@dataclass
class EngineCallbacks:
    on_status: Callable[[str], None] = field(default=_ignore)

    on_tool_progress: Callable[[str, int, int], None] = field(default=_ignore)

    on_video_start: Callable[[str, str], None] = field(default=_ignore)

    on_video_status: Callable[[str, str], None] = field(default=_ignore)

    on_video_title: Callable[[str, str], None] = field(default=_ignore)

    on_video_progress: Callable[[str, dict], None] = field(default=_ignore)

    on_video_done: Callable[[str, str, bool, str, Optional[str]], None] = field(
        default=_ignore
    )
