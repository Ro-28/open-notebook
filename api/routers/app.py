"""Local launcher integration: lets the web UI shut down the whole local stack.

Only active when the API was started by scripts/app/open-notebook.sh, which
sets OPEN_NOTEBOOK_LAUNCHER_SCRIPT. The shutdown endpoint additionally requires
a loopback client so a LAN-exposed instance can never be stopped remotely.
"""

import os
import subprocess
from ipaddress import ip_address
from typing import List, Optional

from fastapi import APIRouter, Query, Request
from loguru import logger
from pydantic import BaseModel

from open_notebook.exceptions import AuthenticationError, ConfigurationError
from open_notebook.utils.error_log import (
    clear_error_log,
    error_log_path,
    tail_error_log,
)

router = APIRouter(prefix="/app", tags=["app"])


class LauncherStatus(BaseModel):
    launcher: bool
    can_shutdown: bool


class ErrorLogResponse(BaseModel):
    path: str
    count: int
    records: List[str]


def _launcher_script() -> str | None:
    path = os.getenv("OPEN_NOTEBOOK_LAUNCHER_SCRIPT", "").strip()
    return path if path and os.path.isfile(path) else None


def _is_loopback(request: Request) -> bool:
    host = request.client.host if request.client else ""
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "testclient")


@router.get("/launcher", response_model=LauncherStatus)
async def launcher_status(request: Request):
    script = _launcher_script()
    return LauncherStatus(launcher=script is not None, can_shutdown=script is not None and _is_loopback(request))


@router.post("/shutdown", status_code=202)
async def shutdown(request: Request):
    """Stop every local service (SurrealDB, API, worker, UI, Learn sidecar) and the launcher app."""
    script = _launcher_script()
    if not script:
        raise ConfigurationError("Not running under the local launcher")
    if not _is_loopback(request):
        raise AuthenticationError("Shutdown is only allowed from localhost")
    logger.warning("Shutdown requested from the UI; stopping all services")
    # Detach fully: the stop script kills this very process.
    subprocess.Popen(
        ["/bin/bash", script, "stop"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return {"status": "stopping"}


@router.get("/errors", response_model=ErrorLogResponse)
async def recent_errors(
    lines: int = Query(200, ge=1, le=2000),
    level: Optional[str] = Query(None, pattern="^(?i)(warning|error|critical)$"),
):
    """Tail of the persistent error log (API + worker), newest last."""
    records = tail_error_log(lines=lines, level=level)
    return ErrorLogResponse(path=str(error_log_path()), count=len(records), records=records)


@router.delete("/errors", status_code=204)
async def clear_errors():
    clear_error_log()
    return None
