"""Validation for the shared release workspace, without runtime dependencies."""

import hashlib
import math
import re
from datetime import datetime, timezone

from .client import NotifyError, https_url
from .journal import encode

TERMINAL = {"shipped", "failed", "canceled", "denied"}
STATUSES = TERMINAL | {"preparing", "running", "awaiting_approval", "approved"}
EDITABLE = {"name", "stage", "summary", "progress", "checks", "artifacts", "notes"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def text(value, limit, label, *, empty=False):
    if not isinstance(value, str) or (not empty and not value) or len(value) > limit:
        raise NotifyError(f"Invalid {label}; maximum length is {limit}", status=400)
    if any((ord(c) < 32 and c not in "\n\t") or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise NotifyError(f"Invalid control character in {label}", status=400)
    return value


def notify_text(value, limit, label, *, empty=False):
    """Notify's documented message limits use UTF-16, unlike our workspace."""
    text(value, limit, label, empty=empty)
    if len(value.encode("utf-16-le")) // 2 > limit:
        raise NotifyError(f"Invalid {label}; maximum Notify length is {limit}", status=400)
    return value


def notify_clip(value, limit):
    """Fit a workspace label into Notify's narrower native display fields."""
    return value.encode("utf-16-le")[:limit * 2].decode("utf-16-le", errors="ignore")


def slug(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value):
        raise NotifyError("Invalid project slug", status=400)
    return value


def run_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise NotifyError("Invalid run ID", status=400)
    return value


def app_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"app_[A-Za-z0-9_-]{8,64}", value):
        raise NotifyError("Invalid App ID")
    return value


def validate(w):
    required = {"schemaVersion", "project", "runId", "revision", "name", "version", "status", "stage", "summary", "progress", "checks", "artifacts", "notes", "updatedAt", "appId", "approval"}
    if set(w) != required or w["schemaVersion"] != 1:
        raise NotifyError("Invalid workspace shape", status=400)
    slug(w["project"])
    run_id(w["runId"])
    for k in ("name", "version", "stage"):
        text(w[k], 80, k)
    text(w["summary"], 500, "summary", empty=True)
    text(w["notes"], 8000, "notes", empty=True)
    if w["status"] not in STATUSES or type(w["revision"]) is not int or w["revision"] < 1:
        raise NotifyError("Invalid workspace state or revision", status=400)
    p = w["progress"]
    if p is not None and (type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1):
        raise NotifyError("Progress must be measured work from 0 to 1, or null", status=400)
    for field in ("checks", "artifacts"):
        if not isinstance(w[field], list) or len(w[field]) > 20:
            raise NotifyError("Workspace supports at most 20 checks and 20 artifacts", status=400)
        for item in w[field]:
            keys = {"label", "status" if field == "checks" else "url"}
            if not isinstance(item, dict) or set(item) != keys:
                raise NotifyError("Invalid workspace item", status=400)
            text(item["label"], 80, "label")
            if field == "checks" and item["status"] not in ("pending", "running", "passed", "failed"):
                raise NotifyError("Invalid check status", status=400)
            if field == "artifacts":
                https_url(item["url"])
    if w["appId"] is not None:
        app_id(w["appId"])
    a = w["approval"]
    if a is not None:
        if set(a) != {"requestId", "digest", "title", "status"} or a["status"] not in ("pending", "approved", "denied", "expired", "canceled"):
            raise NotifyError("Invalid approval state", status=400)
        run_id(a["requestId"])
        text(a["digest"], 256, "digest")
        text(a["title"], 80, "approval title")
    if len(encode(w).encode()) > 60 * 1024:
        raise NotifyError("Workspace exceeded size limit", status=400)
    return w


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()
