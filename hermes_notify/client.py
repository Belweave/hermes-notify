"""Small, bounded client for the documented Notify Agent REST API."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

API_BASE = "https://notify.belweave.ai/api/agent"
TEST_TOKEN = "dummy"  # Public sentinel for loopback tests, never a Notify credential.
MAX_RESPONSE_BYTES = 128 * 1024


class NotifyError(Exception):
    """Safe to log: never includes response bodies, URLs, prompts, or credentials."""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class NotifyClient:
    def __init__(self, token, base_url=API_BASE):
        if not isinstance(token, str) or not token or any(c.isspace() for c in token):
            raise NotifyError("Notify token is missing or invalid")
        if base_url != API_BASE:
            url = urlsplit(base_url)
            if not (
                token == TEST_TOKEN and url.scheme == "http" and url.hostname == "127.0.0.1"
                and url.port and url.path == "/api/agent" and not url.query
                and not url.fragment and not url.username and not url.password
            ):
                raise NotifyError("Test transport requires loopback and the dummy token")
        elif token == TEST_TOKEN:
            raise NotifyError("Dummy token cannot be sent to Notify")
        self._token = token
        self._base_url = base_url
        # No ambient proxy forwarding and no redirects carrying Authorization elsewhere.
        self._opener = build_opener(ProxyHandler({}), NoRedirects())

    def _request(self, method, path, *, timeout, body=None, key=None):
        headers = {"Authorization": "Bearer " + self._token, "Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, separators=(",", ":")).encode()
        if key:
            headers["Idempotency-Key"] = key
        request = Request(self._base_url + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=max(0.01, timeout)) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise NotifyError(f"Notify returned HTTP {exc.code}") from None
        except (URLError, OSError, ValueError):
            raise NotifyError("Notify connection failed") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise NotifyError("Notify response exceeded size limit")
        try:
            result = json.loads(payload)
        except (ValueError, UnicodeError):
            raise NotifyError("Notify returned invalid JSON") from None
        if not isinstance(result, dict):
            raise NotifyError("Notify returned an invalid response")
        return result

    @staticmethod
    def _interaction_path(interaction_id):
        if not isinstance(interaction_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", interaction_id):
            raise NotifyError("Notify returned an invalid interaction ID")
        return "/interactions/" + interaction_id

    def create(self, body, key, timeout):
        return self._request("POST", "/interactions", body=body, key=key, timeout=timeout)

    def wait(self, interaction_id, seconds, timeout):
        path = self._interaction_path(interaction_id) + f"/wait?timeout={min(25, max(0, seconds)):.3f}"
        return self._request("GET", path, timeout=timeout)

    def cancel(self, interaction_id, timeout):
        return self._request("POST", self._interaction_path(interaction_id) + "/cancel", timeout=timeout)
