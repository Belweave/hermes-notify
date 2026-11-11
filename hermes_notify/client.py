"""Bounded stdlib transports for the pinned Notify Agent and publisher contracts."""

import ipaddress
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

API_BASE = "https://notify.belweave.ai/api/agent"
VERSION = "0.2.2"
# Name this client explicitly. Some edge networks, including workers.dev,
# reject the default Python-urllib agent with 403 before the Worker runs.
USER_AGENT = f"hermes-notify/{VERSION} (+https://github.com/Belweave/hermes-notify)"
TEST_TOKEN = "dummy"
MAX_RESPONSE_BYTES = 128 * 1024


class NotifyError(Exception):
    """Safe diagnostic. Raw server bodies and credential-bearing URLs never escape."""

    def __init__(self, message, *, status=None, code=None, required=(), retry_after=None):
        super().__init__(message)
        self.status, self.code = status, code
        self.required, self.retry_after = tuple(required), retry_after

    @property
    def uncertain(self):
        return self.status is None or self.status >= 500 or self.status in (202, 408, 409)

    def public(self):
        result = {"error": str(self)}
        if self.status is not None:
            result["httpStatus"] = self.status
        if self.code:
            result["code"] = self.code
        if self.required:
            result["requiredScopes"] = list(self.required)
        if self.retry_after is not None:
            result["retryAfterSeconds"] = self.retry_after
        return result


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def https_url(value, *, origin=False):
    """Validate a public HTTPS name without fetching an arbitrary caller URL."""
    try:
        u = urlsplit(value)
        host = u.hostname or ""
        valid = (isinstance(value, str) and len(value) <= 2048 and u.scheme == "https"
                 and host and not u.username and not u.password and not u.fragment
                 and not any(c.isspace() or ord(c) < 32 for c in value) and "\\" not in value
                 and u.port in (None, 443) and not host.endswith("."))
        if origin:
            valid = valid and u.path in ("", "/") and not u.query
        try:
            valid = valid and ipaddress.ip_address(host).is_global
        except ValueError:
            valid = valid and bool(re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", host))
            valid = valid and not host.endswith((".localhost", ".local", ".internal", ".test", ".invalid"))
        if not valid:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise NotifyError("A public HTTPS URL is required") from None
    return value.rstrip("/") if origin else value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise NotifyError("Invalid remote identifier")
    return value


class JsonClient:
    def __init__(self, token, base_url, *, test_path):
        if not isinstance(token, str) or not token or any(c.isspace() or ord(c) < 32 for c in token):
            raise NotifyError("API token is missing or invalid")
        try:
            u = urlsplit(base_url)
            loopback = (u.scheme == "http" and u.hostname == "127.0.0.1" and u.port
                        and u.path == test_path and not u.query and not u.fragment
                        and not u.username and not u.password)
        except ValueError:
            loopback = False
        if base_url.startswith("http:") or token == TEST_TOKEN:
            if not (loopback and token == TEST_TOKEN):
                raise NotifyError("Test transport requires loopback and the dummy token")
        self._token, self._base_url = token, base_url
        self._opener = build_opener(ProxyHandler({}), NoRedirects())

    def _request(self, method, path, *, timeout=5, body=None, key=None, authenticated=True):
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if authenticated:
            headers["Authorization"] = "Bearer " + self._token
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":"), sort_keys=True, allow_nan=False, ensure_ascii=False).encode()
            if len(data) > 64 * 1024:
                raise NotifyError("Request exceeded size limit", status=400)
        if key:
            headers["Idempotency-Key"] = identifier(key)
        request = Request(self._base_url + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=max(0.01, min(30, timeout))) as response:
                status = response.status
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # Only extract constrained machine metadata, never the server's error text.
            try:
                raw = exc.read(MAX_RESPONSE_BYTES + 1)
                detail = json.loads(raw) if len(raw) <= MAX_RESPONSE_BYTES else {}
                detail = detail if isinstance(detail, dict) else {}
            except (ValueError, OSError):
                detail = {}
            finally:
                exc.close()
            code = detail.get("code")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z_]{1,80}", code):
                code = None
            required = detail.get("required", [])
            required = [x for x in required[:30] if isinstance(x, str) and re.fullmatch(r"[a-z]+:[a-z]+", x)] if isinstance(required, list) else []
            retry = detail.get("retryAfterSeconds")
            if not isinstance(retry, (int, float)) or not 0 <= retry <= 86400:
                retry = 60 if exc.code == 429 else None
            raise NotifyError(f"API returned HTTP {exc.code}", status=exc.code, code=code,
                              required=required, retry_after=retry) from None
        except (URLError, OSError, ValueError):
            raise NotifyError("API connection failed") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise NotifyError("API response exceeded size limit")
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            raise NotifyError("API returned invalid JSON") from None
        if not isinstance(result, dict):
            raise NotifyError("API returned an invalid response")
        if status == 202:
            raise NotifyError("API operation is still in progress", status=202)
        return result


class NotifyClient(JsonClient):
    def __init__(self, token, base_url=API_BASE):
        if base_url != API_BASE and not base_url.startswith("http://127.0.0.1:"):
            raise NotifyError("Notify origin is fixed; tests require loopback")
        super().__init__(token, base_url, test_path="/api/agent")

    @staticmethod
    def _interaction_path(interaction_id):
        return "/interactions/" + identifier(interaction_id)

    def create(self, body, key, timeout=5):
        return self._request("POST", "/interactions", body=body, key=key, timeout=timeout)

    def get_interaction(self, interaction_id):
        return self._request("GET", self._interaction_path(interaction_id))

    def wait(self, interaction_id, seconds, timeout):
        path = self._interaction_path(interaction_id) + f"/wait?timeout={min(25, max(0, seconds)):.3f}"
        return self._request("GET", path, timeout=timeout)

    def cancel(self, interaction_id, timeout=5):
        return self._request("POST", self._interaction_path(interaction_id) + "/cancel", timeout=timeout)

    def send(self, body, key):
        return self._request("POST", "/notifications", body=body, key=key)

    def register_app(self, body):
        # Documented upsert by identical launch URL; no invented idempotency header.
        return self._request("POST", "/apps", body=body)

    def update_app(self, app_id, body):
        return self._request("PATCH", "/apps/" + identifier(app_id), body=body)

    def get_app(self, app_id):
        return self._request("GET", "/apps/" + identifier(app_id))

    def start_activity(self, body, key):
        return self._request("POST", "/activities", body=body, key=key)

    def get_activity(self, activity_id):
        return self._request("GET", "/activities/" + identifier(activity_id))

    def update_activity(self, activity_id, body):
        return self._request("PATCH", "/activities/" + identifier(activity_id), body=body)

    def end_activity(self, activity_id, body, key):
        return self._request("POST", "/activities/" + identifier(activity_id) + "/end", body=body, key=key)

    def inbox_projects(self):
        return self._request("GET", "/inbox/projects")

    def inbox(self, *, project=None, cursor=None, limit=20):
        params = {"limit": max(1, min(50, limit))}
        if project:
            params["project"] = project  # Notify project ID, not a local project slug.
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/inbox/notifications?" + urlencode(params))


class WorkerClient(JsonClient):
    def __init__(self, token, origin):
        if token != TEST_TOKEN:
            origin = https_url(origin, origin=True)
        super().__init__(token, origin, test_path="")
        self.origin = origin

    def health(self):
        result = self._request("GET", "/api/health", authenticated=False)
        if result.get("service") != "hermes-pocket" or result.get("schemaVersion") != 1:
            raise NotifyError("Publisher health contract mismatch")
        return result

    def put(self, project, operation_id, expected_revision, workspace):
        return self._request("PUT", "/api/projects/" + identifier(project), body={
            "operationId": operation_id, "expectedRevision": expected_revision, "workspace": workspace})

    def get(self, project):
        return self._request("GET", "/api/projects/" + identifier(project))

    def replies(self, project, after):
        return self._request("GET", f"/api/projects/{identifier(project)}/replies?after={int(after)}")

    def ack_replies(self, project, ids):
        return self._request("POST", f"/api/projects/{identifier(project)}/replies/ack", body={"ids": ids})

    def events(self, after):
        return self._request("GET", f"/api/events?after={int(after)}")

    def ack_events(self, ids):
        return self._request("POST", "/api/events/ack", body={"ids": ids})
