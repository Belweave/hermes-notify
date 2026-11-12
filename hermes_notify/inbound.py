"""Signed inbound webhooks from Notify: a push hint that a question was answered.

A delivery is only a hint. The runtime re-reads the interaction from the Notify API before it
records or injects anything, so a forged or replayed body can at most cause one extra GET.
"""

import hashlib
import hmac
import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PATH = "/notify/webhook"
MAX_BODY = 64 * 1024
TOLERANCE_SECONDS = 300
CLOCK_SKEW_SECONDS = 60  # A signature from the future beyond normal clock skew is refused.
RETRY_SECONDS = 15
EVENTS = ("interaction.answered", "interaction.expired", "interaction.canceled")
logger = logging.getLogger("hermes_notify")


def sign(secret, body, timestamp=None):
    """Notify's scheme: X-Notify-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">."""
    t = str(int(timestamp if timestamp is not None else time.time()))
    return f"t={t},v1=" + hmac.new(secret.encode(), t.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify(secret, header, body, now=None):
    match = re.fullmatch(r"t=(\d{10}),v1=([a-f0-9]{64})", header or "")
    if not secret or not match:
        return False
    age = (now if now is not None else time.time()) - int(match.group(1))
    if age > TOLERANCE_SECONDS or age < -CLOCK_SKEW_SECONDS:
        return False
    expected = hmac.new(secret.encode(), match.group(1).encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, match.group(2))


class Inbound:
    """One listener per process. If the port is taken (another Hermes process of this profile
    already listens), this process simply does not listen; answers are settled in the shared
    profile journal either way."""

    def __init__(self, on_hint):
        self.on_hint = on_hint
        self.secret = ""
        self.server = None
        self.address = None
        self.failed = None
        self.closed = False
        self.retry = None
        self.lock = threading.Lock()

    @property
    def listening(self):
        return self.server is not None

    def ensure(self, *, port, host, secret):
        with self.lock:
            self.secret = secret or ""
            wanted = (host or "127.0.0.1", int(port or 0))
            if self.server is not None and (self.address != wanted or not self.secret):
                self._stop()
            if self.server is not None or not wanted[1] or not self.secret:
                return
            if self.closed or (self.failed and self.failed[0] == wanted and time.monotonic() - self.failed[1] < RETRY_SECONDS - 1):
                return
            try:
                server = ThreadingHTTPServer(wanted, self._handler())
            except OSError as exc:
                if not self.failed:
                    logger.info("Notify webhook listener waiting for %s:%s (%s); retrying every %ss",
                                *wanted, type(exc).__name__, RETRY_SECONDS)
                self.failed = (wanted, time.monotonic())
                # Another short-lived Hermes command (`hermes notify ...`, `hermes gateway restart`)
                # may hold the port for a while. Keep trying so a long-running gateway takes over.
                self._schedule_retry(wanted)
                return
            server.daemon_threads = True
            self.server, self.address, self.failed = server, wanted, None
            threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5},
                             name="hermes-notify-inbound", daemon=True).start()

    def _schedule_retry(self, wanted):
        # Called with the lock held. A retry that fails again runs inside the previous timer's
        # thread, which is still alive at that point: it must schedule the next attempt itself.
        current = self.retry
        if self.closed or (current is not None and current.is_alive() and current is not threading.current_thread()):
            return
        self.retry = threading.Timer(RETRY_SECONDS, self._retry, args=(wanted,))
        self.retry.daemon = True
        self.retry.start()

    def _retry(self, wanted):
        with self.lock:
            if self.closed or self.server is not None or not self.failed or self.failed[0] != wanted:
                return
            self.failed = (wanted, 0)
            secret = self.secret
        self.ensure(port=wanted[1], host=wanted[0], secret=secret)

    def _stop(self):
        server, self.server, self.address = self.server, None, None
        if server is not None:
            server.shutdown()
            server.server_close()

    def close(self):
        with self.lock:
            self.closed = True
            if self.retry is not None:
                self.retry.cancel()
            self._stop()

    def _handler(self):
        inbound = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "hermes-notify"
            sys_version = ""

            def log_message(self, *_):
                pass

            def _reply(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.split("?")[0] in (PATH, PATH + "/health"):
                    return self._reply(200, {"ok": True, "service": "hermes-notify"})
                self._reply(404, {"ok": False})

            def do_POST(self):
                if self.path.split("?")[0] != PATH:
                    return self._reply(404, {"ok": False})
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if not 0 < length <= MAX_BODY:
                    return self._reply(413, {"ok": False})
                body = self.rfile.read(length)
                if not verify(inbound.secret, self.headers.get("X-Notify-Signature"), body):
                    return self._reply(401, {"ok": False, "error": "bad signature"})
                try:
                    payload = json.loads(body)
                    kind = payload.get("type")
                    iid = payload["interaction"]["id"]
                    if kind not in EVENTS or not isinstance(iid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", iid):
                        raise ValueError
                except (ValueError, KeyError, TypeError, AttributeError):
                    return self._reply(400, {"ok": False})
                try:
                    inbound.on_hint(iid)
                except Exception:
                    return self._reply(503, {"ok": False})
                self._reply(202, {"ok": True})

        return Handler
