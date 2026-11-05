"""Local-only Notify stand-in. The test actor, not an agent API route, answers."""

import hashlib
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class MockNotify:
    def __init__(self, answer="approve"):
        self.answer = answer
        self.created = threading.Event()
        self.answered = threading.Event()
        self.interaction = None
        self.requests = []
        self.keys = {}
        self.lock = threading.Lock()

    def phone_answer(self):
        if not self.created.wait(10):
            return
        with self.lock:
            if self.answer == "timeout":
                return
            self.interaction.update(
                status="approved" if self.answer == "approve" else "denied",
                response=self.answer, respondingDeviceId="dev_mock_phone",
                respondingUserId="mock_person", respondedAt="2026-11-05T00:00:01Z",
            )
        self.answered.set()

    @contextmanager
    def serve(self):
        state = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def send_json(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                key = self.headers.get("Idempotency-Key")
                state.requests.append(("POST", self.path, body, key))
                if self.path == "/api/agent/interactions":
                    with state.lock:
                        if key not in state.keys:
                            state.interaction = {
                                "id": "int_mock_approval", **body, "status": "pending",
                                "choices": ["approve", "deny"], "response": None,
                                "imageUrl": None, "url": None,
                                "actionDigest": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
                                "primaryLabel": None, "secondaryLabel": None, "accepted": 1,
                                "respondingDeviceId": None, "respondingUserId": None,
                                "expiresAt": "2026-11-05T00:02:00Z", "createdAt": "2026-11-05T00:00:00Z",
                                "respondedAt": None, "canceledAt": None,
                            }
                            state.keys[key] = state.interaction["id"]
                        snapshot = dict(state.interaction)
                    self.send_json(201, {"interaction": snapshot, "accepted": 1})
                    state.created.set()
                elif self.path == "/api/agent/interactions/int_mock_approval/cancel":
                    with state.lock:
                        if state.interaction["status"] == "pending":
                            state.interaction["status"] = "canceled"
                        self.send_json(200, {"interaction": state.interaction})
                else:
                    self.send_json(404, {"error": "Unknown mock route"})

            def do_GET(self):
                state.requests.append(("GET", self.path, None, None))
                if urlsplit(self.path).path != "/api/agent/interactions/int_mock_approval/wait":
                    self.send_json(404, {"error": "Unknown mock route"})
                    return
                state.answered.wait(0.1)
                with state.lock:
                    snapshot = dict(state.interaction)
                self.send_json(200, {"interaction": snapshot, "timedOut": snapshot["status"] == "pending"})

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        actor = threading.Thread(target=self.phone_answer, daemon=True)
        worker.start()
        actor.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}/api/agent"
        finally:
            server.shutdown()
            server.server_close()
            worker.join(2)
            actor.join(2)
