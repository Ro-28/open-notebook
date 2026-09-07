"""Persistent error log for debugging.

Every WARNING+ record from the API and the background worker is appended to a
rotating file (default ``data/logs/errors.log``, override with
``OPEN_NOTEBOOK_ERROR_LOG``) in addition to the normal console output. Rotation
keeps ~10 MB x 5 files so it can be left on indefinitely.

The file is what the UI's Settings → Advanced "Recent errors" panel and
``GET /api/app/errors`` read; the launcher's "Show Logs" opens the same folder.
"""

import os
from pathlib import Path
from typing import List, Optional

from loguru import logger

_ERROR_LOG_SINK_ID: Optional[int] = None


def error_log_path() -> Path:
    env = os.getenv("OPEN_NOTEBOOK_ERROR_LOG")
    if env:
        return Path(env)
    root = Path(os.getenv("OPEN_NOTEBOOK_DATA_DIR") or Path(__file__).resolve().parents[2] / "data")
    return root / "logs" / "errors.log"


def setup_error_log(process_name: str, force: bool = False) -> Path:
    """Attach the rotating error sink once per process. Returns the log path.

    Several dependencies (content-core, surreal-commands' worker) call ``logger.remove()`` with no
    arguments at import/startup time, which would silently drop this sink. ``logger.remove`` is
    therefore wrapped once so a blanket removal re-attaches the error sink afterwards.
    ``force`` re-attaches explicitly.
    """
    global _ERROR_LOG_SINK_ID
    path = error_log_path()
    if _ERROR_LOG_SINK_ID is not None and not force:
        return path
    _install_remove_guard(process_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ERROR_LOG_SINK_ID = _add_sink(path, process_name)
    logger.info(f"Error log: {path}")
    return path


def _add_sink(path: Path, process_name: str) -> int:
    return logger.add(
        str(path),
        level=os.getenv("OPEN_NOTEBOOK_ERROR_LOG_LEVEL", "WARNING"),
        rotation="10 MB",
        retention=5,
        enqueue=True,  # safe across threads and the worker's subprocesses
        backtrace=False,
        diagnose=False,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | " + process_name + " | "
            "{name}:{function}:{line} - {message}"
        ),
    )


_REMOVE_GUARD_INSTALLED = False


def _install_remove_guard(process_name: str) -> None:
    global _REMOVE_GUARD_INSTALLED
    if _REMOVE_GUARD_INSTALLED:
        return
    _REMOVE_GUARD_INSTALLED = True
    original_remove = logger.remove

    def guarded_remove(handler_id=None):
        global _ERROR_LOG_SINK_ID
        original_remove(handler_id)
        if handler_id is None or handler_id == _ERROR_LOG_SINK_ID:
            # blanket removal (or ours): put the error sink back
            _ERROR_LOG_SINK_ID = _add_sink(error_log_path(), process_name)

    logger.remove = guarded_remove  # type: ignore[method-assign]


def tail_error_log(lines: int = 200, level: Optional[str] = None) -> List[str]:
    """Last ``lines`` records (multi-line tracebacks are kept with their record)."""
    path = error_log_path()
    if not path.exists():
        return []
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        chunk = min(size, 512 * 1024)
        fh.seek(size - chunk)
        text = fh.read().decode("utf-8", errors="replace")
    records: List[str] = []
    for line in text.splitlines():
        # A new record starts with a timestamp; continuation lines belong to the previous one.
        if len(line) > 23 and line[4] == "-" and line[10] == " " and line[13] == ":":
            records.append(line)
        elif records:
            records[-1] += "\n" + line
    if level:
        want = level.upper()
        records = [r for r in records if f"| {want:<8} |" in r]
    return records[-lines:]


def clear_error_log() -> None:
    path = error_log_path()
    if path.exists():
        path.write_text("")
