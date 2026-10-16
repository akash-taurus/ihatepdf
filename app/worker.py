"""Background execution helpers for the desktop app.

PDF work can take a while (OCR and compression especially), so every operation
runs on a QThread and reports back through signals instead of blocking the GUI.
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

#: How much extracted text to show in the log pane before truncating.
LOG_TEXT_LIMIT = 4000


class Worker(QThread):
    """Run ``fn(*args, **kwargs)`` off the GUI thread."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception:
            self.failed.emit(traceback.format_exc(limit=4))


def format_result(result: Any) -> str:
    """Render a tool result for the log pane."""
    if isinstance(result, str):
        text = result
    elif isinstance(result, (list, tuple)):
        text = "\n".join(str(item) for item in result)
    else:
        text = json.dumps(result, indent=2, default=str)
    if len(text) > LOG_TEXT_LIMIT:
        text = text[:LOG_TEXT_LIMIT] + f"\n… ({len(text) - LOG_TEXT_LIMIT} more characters)"
    return text
