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
        worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
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


class PocketMock:
    """Synthetic Agent/Worker HTTP harness. Never authenticates to an external service."""

    def __init__(self):
        self.requests = []
        self.user_agents = []
        self.responses = {}
        self.failures = {}
        self.apps = {}
        self.notifications = {}
        self.interactions = {}
        self.activities = {}
        self.workspaces = {}
        self.operations = {}
        self.expired_operations = set()
        self.replies = []
        self.events = []
        self.reply_acks = set()
        self.event_acks = set()
        self.accepted = 1
        self.queued = 0
        self.activity_error = None
        self.answer = None
        self.lock = threading.RLock()

    def fail(self, method, path, status=503, body=None, *, after=False):
        self.failures.setdefault((method, path), []).append((status, body or {"error": "synthetic failure"}, after))

    def count(self, method, path):
        return sum(m == method and urlsplit(p).path == path for m, p, _, _ in self.requests)

    def dispatch(self, method, path, body, key):
        from urllib.parse import parse_qs
        u = urlsplit(path)
        route = u.path
        self.requests.append((method, path, body, key))
        failure = (self.failures.get((method, route)) or [None])[0]
        if failure:
            self.failures[(method, route)].pop(0)
            if not failure[2]:
                return failure[:2]
        result = self._dispatch(method, route, parse_qs(u.query), body, key)
        return failure[:2] if failure else result

    def _dispatch(self, method, path, query, body, key):
        if (method, path) in self.responses:
            return self.responses[(method, path)]
        if path == "/api/health":
            return 200, {"service": "hermes-pocket", "schemaVersion": 1}
        if path == "/api/agent/apps" and method == "POST":
            app = self.apps.setdefault(body["url"], {"id": "app_" + str(len(self.apps) + 1).zfill(8)})
            app.update(body)
            return 201, {"app": app, "created": True}
        if path == "/api/agent/notifications" and method == "POST":
            self.notifications.setdefault(key, {"id": "anot_" + str(len(self.notifications) + 1).zfill(8), **body})
            return 201, {"notification": self.notifications[key], "accepted": self.accepted}
        if path == "/api/agent/interactions" and method == "POST":
            old = next((i for i in self.interactions.values() if i["mockKey"] == key), None)
            if old:
                return 201, {"interaction": old, "accepted": self.accepted}
            iid = "int_" + str(len(self.interactions) + 1).zfill(8)
            interaction = {"id": iid, **body, "actionDigest": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
                           "status": "pending", "response": None, "mockKey": key}
            self.interactions[iid] = interaction
            return 201, {"interaction": interaction, "accepted": self.accepted}
        if path.startswith("/api/agent/interactions/"):
            iid = path.split("/")[4]
            interaction = self.interactions.get(iid)
            if not interaction:
                return 404, {"error": "not found"}
            if path.endswith("/cancel"):
                interaction.update(status="canceled", response=None)
            elif self.answer:
                status, response = self.answer
                interaction.update(status=status, response=response)
            return 200, {"interaction": interaction, "timedOut": interaction["status"] == "pending"}
        if path == "/api/agent/activities" and method == "POST":
            if self.activity_error:
                return self.activity_error
            old = next((a for a in self.activities.values() if a["key"] == body["key"]), None)
            if old:
                return 409, {"error": "active key"}
            aid = "act_" + str(len(self.activities) + 1).zfill(8)
            self.activities[aid] = {"id": aid, "key": body["key"], "sequence": 0, "status": "starting",
                                    "props": body, "accepted": self.accepted, "readiness": {"ready": 0, "queuedStarts": self.queued}}
            return 201, {"activity": self.activities[aid], "accepted": self.accepted, "queued": self.queued, "failed": 0}
        if path.startswith("/api/agent/activities/"):
            aid = path.split("/")[4]
            activity = self.activities.get(aid) or next((a for a in self.activities.values() if a["key"] == aid), None)
            if not activity:
                return 404, {"error": "not found"}
            if method == "GET":
                return 200, {"activity": activity}
            if body.get("ifSequence") != activity["sequence"]:
                return 409, {"error": "sequence conflict"}
            activity["sequence"] += 1
            activity["props"].update({k: v for k, v in body.items() if k not in ("ifSequence", "priority", "dismissAfterSeconds")})
            activity["status"] = "ended" if path.endswith("/end") else "active"
            return 200, {"activity": activity, "accepted": self.accepted, "failed": 0, "queued": self.queued}
        if path.startswith("/api/projects/"):
            project = path.split("/")[3]
            if path.endswith("/replies/ack"):
                self.reply_acks.update(body["ids"])
                return 200, {"ok": True}
            if path.endswith("/replies"):
                cursor = int(query.get("after", [0])[0])
                rows = [r for r in self.replies if r["cursor"] > cursor and r["id"] not in self.reply_acks]
                return 200, {"replies": rows, "cursor": rows[-1]["cursor"] if rows else cursor}
            if method == "PUT":
                op = self.operations.get(body["operationId"])
                if op:
                    if op[0] != body:
                        return 409, {"error": "changed operation"}
                    if body["operationId"] in self.expired_operations:
                        return 409, {"error": "operation_response_expired", "code": "OPERATION_RESPONSE_EXPIRED"}
                    return 200, op[1]
                revision = self.workspaces.get(project, {}).get("revision", 0)
                if body["expectedRevision"] != revision or body["workspace"]["revision"] != revision + 1:
                    return 409, {"error": "revision_conflict", "code": "REVISION_CONFLICT"}
                self.workspaces[project] = body["workspace"]
                result = {"workspace": body["workspace"], "revision": revision + 1, "unchanged": False}
                self.operations[body["operationId"]] = (body, result)
                return 200, result
            if project in self.workspaces:
                return 200, {"workspace": self.workspaces[project], "revision": self.workspaces[project]["revision"]}
        if path == "/api/events/ack":
            self.event_acks.update(body["ids"])
            return 200, {"ok": True}
        if path == "/api/events":
            cursor = int(query.get("after", [0])[0])
            rows = [e for e in self.events if e["cursor"] > cursor and e["id"] not in self.event_acks]
            return 200, {"events": rows, "cursor": rows[-1]["cursor"] if rows else cursor}
        return 404, {"error": "Unknown mock route"}

    @contextmanager
    def serve(self):
        state = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def handle_request(self):
                state.user_agents.append((self.command, urlsplit(self.path).path, self.headers.get("User-Agent")))
                if self.path != "/api/health" and self.headers.get("Authorization") != "Bearer dummy":
                    self.send_error(401)
                    return
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else None
                with state.lock:
                    code, result = state.dispatch(self.command, self.path, body, self.headers.get("Idempotency-Key"))
                    data = json.dumps(result).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            do_GET = do_POST = do_PUT = do_PATCH = handle_request
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.02), daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)
