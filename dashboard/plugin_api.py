"""Read only the runtime's bounded, secret-free, profile-local status snapshot.

Hermes mounts this router with its authentication and plugin enablement gates.
No runtime imports, settings reads, credentials, network calls, or write routes.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Response
from hermes_cli.plugins_state import PluginState

router = APIRouter()
MAX_BYTES = 512 * 1024
MAX_RUNS = 20
MAX_PENDING = 50
MAX_DELIVERIES = 50
RUN_STATES = {"preparing", "running", "awaiting_approval", "approved", "shipped", "denied", "failed", "canceled"}
DECISION_STATES = {"pending", "approved", "denied", "expired", "canceled"}
CHECK_STATES = {"pending", "running", "passed", "failed"}


def _text(value, limit, *, pattern=None, choices=None):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError("Invalid text")
    if pattern and not re.fullmatch(pattern, value):
        raise ValueError("Invalid identifier")
    if choices and value not in choices:
        raise ValueError("Invalid state")
    return value


def _object(value):
    if not isinstance(value, dict):
        raise ValueError("Expected an object")
    return value


def _rows(value, limit, convert):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError("Invalid list")
    return [convert(_object(row)) for row in value]


def _integer(value, minimum):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid integer")
    return value


def _project(value):
    return _text(value, 64, pattern=r"[a-z0-9][a-z0-9-]{0,63}")


def _artifact(row):
    url = _text(row["url"], 2048)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Invalid artifact URL")
    if re.search(r"[\s\x00-\x1f\x7f\\]", url):
        raise ValueError("Invalid artifact URL")
    return {"label": _text(row["label"], 80), "url": url}


def _decision(row):
    return {
        "requestId": _text(row["requestId"], 128),
        "title": _text(row["title"], 80),
        "status": _text(row["status"], 16, choices=DECISION_STATES),
    }


def _workspace(row):
    if type(row["schemaVersion"]) is not int or row["schemaVersion"] != 1:
        raise ValueError("Unsupported workspace")
    progress = row["progress"]
    if progress is not None and (type(progress) not in (float, int) or not math.isfinite(progress) or not 0 <= progress <= 1):
        raise ValueError("Invalid progress")
    approval = row["approval"]
    if approval is not None:
        approval = _object(approval)
        approval = {**_decision(approval), "digest": _text(approval["digest"], 512)}
    return {
        "schemaVersion": 1,
        "project": _project(row["project"]),
        "runId": _text(row["runId"], 128, pattern=r"[A-Za-z0-9_-]{1,128}"),
        "revision": _integer(row["revision"], 1),
        "name": _text(row["name"], 80),
        "version": _text(row["version"], 80),
        "status": _text(row["status"], 24, choices=RUN_STATES),
        "stage": _text(row["stage"], 80),
        "summary": _text(row["summary"], 500),
        "progress": progress,
        "checks": _rows(row["checks"], 20, lambda check: {
            "label": _text(check["label"], 80),
            "status": _text(check["status"], 16, choices=CHECK_STATES),
        }),
        "artifacts": _rows(row["artifacts"], 20, _artifact),
        "notes": _text(row["notes"], 8000),
        "updatedAt": _text(row["updatedAt"], 64),
        "appId": None if row["appId"] is None else _text(row["appId"], 128),
        "approval": approval,
    }


def validate_snapshot(value):
    """Project only documented fields, never pass through an extra runtime field."""
    row = _object(value)
    if type(row["schemaVersion"]) is not int or row["schemaVersion"] != 1:
        raise ValueError("Unsupported snapshot")
    if type(row["configured"]) is not bool:
        raise ValueError("Invalid configured flag")
    return {
        "schemaVersion": 1,
        "configured": row["configured"],
        "runs": _rows(row["runs"], MAX_RUNS, _workspace),
        "pending": _rows(row["pending"], MAX_PENDING, _decision),
        "deliveries": _rows(row["deliveries"], MAX_DELIVERIES, lambda delivery: {
            "project": "" if delivery["project"] == "" else _project(delivery["project"]),
            "state": _text(delivery["state"], 80),
            "message": _text(delivery["message"], 500),
        }),
        "updatedAt": _text(row["updatedAt"], 64),
    }


def _read_snapshot():
    # Public storage API, resolved for each request. Unlike plugin_data_dir(),
    # PluginState.data_dir does not mkdir, so even a missing snapshot is read-only.
    directory = PluginState("hermes-notify").data_dir
    if directory.is_symlink() or directory.parent.is_symlink():
        raise ValueError("Invalid storage")
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(directory / "status.json", flags)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("Invalid snapshot file")
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Snapshot too large")
    return validate_snapshot(json.loads(raw))


@router.get("/status")
def status(response: Response):
    # A sync handler runs this bounded file read in FastAPI's thread pool.
    response.headers["Cache-Control"] = "no-store"
    try:
        return _read_snapshot()
    except FileNotFoundError:
        raise HTTPException(404, "No status snapshot. Enable the runtime for this profile and use notify_status.", headers={"Cache-Control": "no-store"}) from None
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        raise HTTPException(503, "Status snapshot unavailable or incompatible. Refresh after the runtime writes a valid snapshot.", headers={"Cache-Control": "no-store"}) from None
