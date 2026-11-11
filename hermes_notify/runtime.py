"""Hermes Pocket orchestration. No model, shell, credential store, or idle poller."""

import sqlite3
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass

from .bridge import ApprovalBridge
from .client import API_BASE, NotifyClient, NotifyError, WorkerClient, https_url, identifier
from .journal import Journal, encode
from .ledger import Ledger
from .publisher import Publisher
from .progress import Progress
from .replies import Replies
from .queue import WorkQueue
from .workspace import EDITABLE, TERMINAL, digest, normalize_project, now, notify_text, run_id, slug, text, validate


@dataclass(frozen=True)
class Session:
    key: str = ""
    id: str = ""

    @property
    def identity(self):
        return self.id or self.key

    def matches(self, run):
        if self.id and run.get("sessionId"):
            return self.id == run["sessionId"] and not (self.key and run.get("sessionKey") and self.key != run["sessionKey"])
        return bool(self.key and self.key == run.get("sessionKey"))


class Runtime(Publisher, Progress, Replies):
    def __init__(self, data_dir, *, enabled=False, token="", publish_token="", settings=None,
                 test_url=None, test_worker_url=None, inject=None):
        self.settings = settings or {}
        self.enabled, self.token, self.publish_token = enabled, token, publish_token
        self.test_url, self.test_worker_url, self.inject = test_url, test_worker_url, inject
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.observer_lock = threading.Lock()
        self.observed = OrderedDict()
        self.journal = Journal(data_dir, retention_days=self.settings.get("retention_days", 30))
        self.ledger = Ledger(self.journal.directory / "approvals.sqlite3")
        self.queue = WorkQueue(self._work, self._background_failure)
        self._notify = None
        self._worker = None
        # Lost host requests are never resumed as permissions after restart.
        for approval in self.journal.all("approval"):
            if approval["status"] == "pending":
                approval["status"] = "expired"
                self.journal.put("approval", approval["requestId"], approval)
                self._apply_approval(approval)
        self.snapshot()

    def _ready(self):
        if self.stopped.is_set():
            raise NotifyError("Hermes Pocket has unloaded")
        if not self.enabled:
            raise NotifyError("Notify is not set up yet. Ask the user to run `hermes notify setup` in a terminal, then start a new session")

    @property
    def api(self):
        self._ready()
        if self._notify is None:
            if not self.token:
                raise NotifyError("No Notify key is saved. Ask the user to run `hermes notify setup` in a terminal, then start a new session")
            self._notify = NotifyClient(self.token, self.test_url or API_BASE)
        return self._notify

    @property
    def worker(self):
        self._ready()
        if self._worker is None:
            origin = self.settings.get("publisher_origin", "")
            if not origin:
                import re
                name, subdomain = self.settings.get("worker_name", ""), self.settings.get("worker_subdomain", "")
                if not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", x) for x in (name, subdomain)):
                    raise NotifyError("Configure publisher_origin or worker_name and worker_subdomain")
                origin = f"https://{name}.{subdomain}.workers.dev"
            self.publisher_origin = https_url(origin, origin=True)
            self._worker = WorkerClient(self.publish_token, self.test_worker_url or origin)
        return self._worker

    def key(self, kind, value):
        return "hp-" + digest([self.journal.identity, kind, value])

    def _run(self, args, session):
        project = slug(args.get("project"))
        project_data = self.journal.get("project", project)
        rid = args.get("run_id") or (project_data or {}).get("runId")
        run = self.journal.get("run", run_id(rid)) if rid else None
        if not run or run["workspace"]["project"] != project or not session.matches(run):
            raise NotifyError("Release run does not belong to the calling session", status=403)
        return run

    def _session_run(self, args, session):
        """The caller's run for this project, or a lightweight "updates" run.

        Sending a notification or asking a question must not require the full
        release workflow or a Worker. Ownership rules are unchanged: another
        session's unfinished run is never reused.
        """
        try:
            return self._run(args, session)
        except NotifyError as exc:
            if exc.status != 403 or args.get("run_id"):
                raise
        project = slug(args.get("project"))
        mapping = self.journal.get("project", project, {})
        current = self.journal.get("run", mapping["runId"]) if mapping.get("runId") else None
        if current and current["workspace"]["status"] not in TERMINAL:
            raise NotifyError("Another session owns this project's active release; use a different project name", status=409)
        self.release({"action": "begin", "project": project, "version": "updates", "name": project,
                      "stage": "Updates"}, session)
        return self._run({"project": project}, session)

    def _save_run(self, run):
        validate(run["workspace"])
        self.journal.put("run", run["workspace"]["runId"], run)

    def _change(self, run, fields):
        w = run["workspace"]
        if all(w.get(k) == v for k, v in fields.items()):
            return run
        run["workspace"] = validate(w | fields | {"revision": w["revision"] + 1, "updatedAt": now()})
        self._save_run(run)
        return run

    def call(self, name, args, session):
        try:
            if not isinstance(args, dict):
                raise NotifyError("Tool arguments must be an object", status=400)
            args = normalize_project(name, args)
            with self.lock:
                if name == "notify_status":
                    return self.status(args, session)
                self._ready()
                encoded = encode(args)
                if any(secret and secret != "dummy" and secret in encoded for secret in (self.token, self.publish_token)):
                    raise NotifyError("Tool content contains a configured credential", status=400)
                if not session.identity:
                    raise NotifyError("A host-provided session is required", status=403)
                methods = {"notify_release": self.release, "notify_publish_app": self.publish,
                           "notify_send": self.send, "notify_ask": self.ask, "notify_replies": self.replies}
                result = methods[name](args, session)
                self.snapshot()
                return {"ok": True, **result}
        except NotifyError as exc:
            try:
                self._delivery(args.get("project", "") if isinstance(args, dict) else "", "failed", str(exc))
            except (OSError, NotifyError):
                pass
            return {"ok": False, **exc.public()}
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error):
            self._background_failure("Invalid input or local storage unavailable")
            return {"ok": False, "error": "Invalid input or local storage unavailable"}

    def release(self, args, session):
        action = args.get("action")
        project = slug(args.get("project"))
        if action == "begin":
            name = text(args.get("name", project), 80, "name")
            version = text(args.get("version"), 80, "version")
            rid = run_id(args.get("run_id") or "run_" + digest([project, version, session.identity])[:32])
            existing = self.journal.get("run", rid)
            if existing:
                if not session.matches(existing) or existing["workspace"]["project"] != project or existing["workspace"]["version"] != version:
                    raise NotifyError("Run ID conflicts with another release", status=409)
                # Resume durable delivery, including an end discarded during unload.
                # Progress only publishes data when this run still owns the project.
                self.queue.submit(("progress", rid), None)
                return {"workspace": existing["workspace"], "resumed": True}
            mapping = self.journal.get("project", project, {})
            previous = self.journal.get("run", mapping.get("runId", ""))
            if previous and previous["workspace"]["status"] not in TERMINAL:
                raise NotifyError("Finish the current project run before starting another", status=409)
            w = {"schemaVersion": 1, "project": project, "runId": rid, "revision": 1,
                 "name": name, "version": version, "status": "preparing", "stage": "Preparing",
                 "summary": "", "progress": None, "checks": [], "artifacts": [], "notes": "",
                 "updatedAt": now(), "appId": mapping.get("appId"), "approval": None}
            w.update({k: args[k] for k in EDITABLE if k in args})
            run = {"workspace": validate(w), "sessionKey": session.key, "sessionId": session.id}
            self._save_run(run)
            self.journal.put("project", project, mapping | {"project": project, "runId": rid})
            self.queue.submit(("progress", rid), None)
            return {"workspace": w}
        run = self._run(args, session)
        w = run["workspace"]
        if action == "status":
            return {"workspace": w}
        if type(args.get("expected_revision")) is not int or args["expected_revision"] != w["revision"]:
            raise NotifyError("Workspace changed; read its current revision before updating", status=409)
        fields = {k: args[k] for k in EDITABLE if k in args}
        if action == "update":
            if w["status"] in TERMINAL:
                raise NotifyError("A finished release is immutable; begin a new version", status=409)
            if "status" in args:
                if args["status"] not in ("preparing", "running") or w["status"] in ("awaiting_approval", "approved"):
                    raise NotifyError("Approval and completion states are host-controlled", status=400)
                fields["status"] = args["status"]
        elif action == "finish":
            result = args.get("result")
            if result not in ("succeeded", "failed", "canceled"):
                raise NotifyError("Finish requires the release action result", status=400)
            summary = text(args.get("result_summary"), 500, "action result summary")
            if result == "succeeded" and w["status"] in ("awaiting_approval", "denied", "failed", "canceled"):
                raise NotifyError("This release cannot be marked shipped", status=409)
            if w["status"] in TERMINAL:
                raise NotifyError("Release already finished", status=409)
            fields.update(status={"succeeded": "shipped", "failed": "failed", "canceled": "canceled"}[result], summary=summary)
            run["completion"] = {"result": result, "summary": summary, "at": now()}
        else:
            raise NotifyError("Unknown release action", status=400)
        self._change(run, fields)
        self.queue.submit(("progress", w["runId"]), None)
        return {"workspace": run["workspace"]}

    def _intent(self, key, kind, body, run):
        proposed = {"id": key, "kind": kind, "body": body, "phase": "prepared", "runId": run["workspace"]["runId"]}
        intent = self.journal.create("intent", key, proposed)
        if intent["body"] != body or intent["kind"] != kind:
            raise NotifyError("Idempotency intent conflicts with earlier content", status=409)
        return intent

    def _write_once(self, kind, body, run, logical_key, operation):
        key = self.key(kind, [run["workspace"]["runId"], logical_key])
        intent = self._intent(key, kind, body, run)
        if intent["phase"] == "done":
            return intent["result"]
        if intent["phase"] in ("sending", "unknown"):
            raise NotifyError("Previous write outcome is unknown; no duplicate was sent")
        if intent.get("retryAt", 0) > time.time():
            raise NotifyError("API retry interval has not elapsed", status=429)
        sending = intent | {"phase": "sending"}
        if not self.journal.replace_if("intent", key, intent, sending):
            raise NotifyError("This write is already in progress; no duplicate was sent")
        intent = sending
        try:
            result = operation(body, key)
        except NotifyError as exc:
            intent.update(phase="unknown" if exc.uncertain else "rejected", error=exc.public())
            if exc.retry_after:
                intent["retryAt"] = time.time() + exc.retry_after
            self.journal.put("intent", key, intent)
            raise
        intent.update(phase="done", result=result)
        self.journal.put("intent", key, intent)
        return result

    def _notification(self, run, body, logical_key):
        result = self._write_once("notification", body, run, logical_key, self.api.send)
        notification = result.get("notification", {})
        if not isinstance(notification, dict) or not isinstance(notification.get("id"), str):
            raise NotifyError("Notify did not return a notification receipt")
        delivery = self.delivery_state(result)
        self._delivery(run["workspace"]["project"], delivery, "Notify receipt recorded; phone display is unconfirmed")
        return {"notificationId": notification["id"], "delivery": delivery, "accepted": result.get("accepted", 0)}

    @staticmethod
    def delivery_state(result):
        if any(type(result.get(k, 0)) is not int or result.get(k, 0) < 0 for k in ("queued", "accepted")):
            raise NotifyError("Invalid delivery receipt")
        if result.get("queued", 0) > 0:
            return "queued"
        if result.get("accepted", 0) > 0:
            return "accepted"
        return "not_accepted"

    def send(self, args, session):
        run = self._session_run(args, session)
        body = {"body": notify_text(args.get("body"), 8000, "body"), "project": run["workspace"]["project"]}
        if len(body["body"].encode()) > 16384:
            raise NotifyError("Notification body exceeded byte limit", status=400)
        for field, limit in (("title", 80), ("summary", 500)):
            if field in args:
                body[field] = notify_text(args[field], limit, field)
        for field in ("url", "imageUrl"):
            if field in args:
                body[field] = https_url(notify_text(args[field], 2048, field))
        if "body_format" in args:
            if args["body_format"] not in ("text", "markdown"):
                raise NotifyError("Invalid body format", status=400)
            body["bodyFormat"] = args["body_format"]
        mapping = self.journal.get("project", body["project"], {})
        if mapping.get("appId"):
            body["appId"] = mapping["appId"]
            if "url" in body:
                from urllib.parse import urlsplit
                if urlsplit(body["url"]).netloc != urlsplit(mapping["url"]).netloc:
                    raise NotifyError("App destination must stay on the registered origin", status=400)
        if self.settings.get("device_id"):
            body["deviceIds"] = [self.settings["device_id"]]
        return self._notification(run, body, args.get("idempotency_key") or digest(body))

    def _delivery(self, project, state, message):
        try:
            project = slug(project)
        except NotifyError:
            project = ""
        record = {"project": project, "state": state, "message": message[:500]}
        self.journal.put("delivery", project, record)
        self.snapshot()

    def snapshot(self):
        value = {"schemaVersion": 1, "configured": self.enabled and bool(self.token),
                 "runs": [r["workspace"] for r in self.journal.all("run")[:10]],
                 "pending": [{"requestId": a["requestId"], "title": a["title"], "status": a["status"]}
                             for a in self.journal.all("approval")[:30]],
                 "deliveries": self.journal.all("delivery")[:30], "updatedAt": now()}
        while len(encode(value).encode()) > 480 * 1024 and value["runs"]:
            value["runs"].pop()
        self.journal.snapshot(value)
        return value

    def status(self, args, session):
        # Local-only. No token probe, inbox read, or poll as a side effect of status.
        value = self.snapshot()
        if args.get("project"):
            run = self._run(args, session)
            value["runs"] = [run["workspace"]]
        return {"ok": True, **value, "enabled": self.enabled,
                "publisherConfigured": bool(self.publish_token and (self.settings.get("publisher_origin") or self.settings.get("worker_name"))),
                "queueDropped": self.queue.dropped,
                "publications": [self._publication_result(p) for p in self.journal.all("publication")[:20]],
                "uncertainWrites": [{k: i[k] for k in ("id", "kind", "phase")} for i in self.journal.all("intent")
                                    if i["phase"] in ("sending", "unknown")][:20]}

    def _background_failure(self, message):
        try:
            self._delivery("", "failed", message)
        except Exception:
            pass

    def observe_pre(self, *, request_id="", request_digest="", session_key="", session_id="", **_):
        if not self.enabled or self.stopped.is_set() or not request_id or not request_digest:
            return
        # No storage/network, no raw command retention, fixed-size correlation cache.
        with self.observer_lock:
            self.observed[request_id] = {"requestId": request_id, "digest": request_digest,
                                         "sessionKey": session_key, "sessionId": session_id}
            while len(self.observed) > 128:
                self.observed.popitem(last=False)

    def observe_post(self, *, request_id="", request_digest="", choice="", **_):
        if request_id and request_digest and not self.stopped.is_set():
            self.queue.submit(("approval", request_id), {"digest": request_digest, "choice": choice})

    def present(self, request):
        if not self.enabled or self.stopped.is_set():
            return request.respond("deny")
        try:
            with self.observer_lock:
                correlation = self.observed.pop(request.request_id, None)
            if correlation and correlation["digest"] == request.digest:
                with self.lock:
                    session = Session(correlation["sessionKey"], correlation["sessionId"])
                    candidates = [r for r in self.journal.all("run") if session.matches(r) and r["workspace"]["status"] not in TERMINAL]
                    if len(candidates) == 1:
                        run = candidates[0]
                        a = correlation | {"runId": run["workspace"]["runId"], "version": run["workspace"]["version"],
                                           "title": "Hermes approval", "status": "pending"}
                        self.journal.put("approval", request.request_id, a)
                        self._apply_approval(a)
                        self.queue.submit(("progress", a["runId"]), None)
            bridge = ApprovalBridge(self.api, self.ledger, timeout_seconds=self.settings.get("timeout_seconds", 120),
                                    device_id=self.settings.get("device_id", ""), is_cancelled=self.stopped.is_set,
                                    on_state=self._approval_state)
            return bridge.present(request)
        except (NotifyError, OSError, ValueError, TypeError):
            return request.respond("deny")

    def _approval_state(self, request, state, interaction_id, action_digest):
        with self.lock:
            a = self.journal.get("approval", request.request_id)
            if a and a["digest"] == request.digest:
                a.update(interactionId=interaction_id, actionDigest=action_digest, transportState=state)
                # Only the host's post observer can confirm the consumed decision.
                if state in ("failed", "denied"):
                    a["status"] = "denied"
                    self._apply_approval(a)
                self.journal.put("approval", request.request_id, a)
                self.snapshot()

    def _apply_approval(self, a):
        run = self.journal.get("run", a["runId"])
        if not run or run["workspace"]["version"] != a["version"] or run["workspace"]["status"] in TERMINAL:
            return
        existing = run["workspace"]["approval"]
        if a["status"] != "pending" and existing and existing["requestId"] != a["requestId"]:
            return
        status = {"pending": "awaiting_approval", "approved": "approved", "denied": "denied", "expired": "failed", "canceled": "canceled"}[a["status"]]
        self._change(run, {"status": status, "approval": {k: a[k] for k in ("requestId", "digest", "title", "status")}})
        self.snapshot()

    def _work(self, key, value):
        if self.stopped.is_set():
            return
        if not self.lock.acquire(timeout=0.1):
            if not self.stopped.is_set():
                self.queue.submit(key, value, delay=0.1)
            return
        try:
            if self.stopped.is_set():
                return
            if key[0] == "approval":
                a = self.journal.get("approval", key[1])
                if not a or a["digest"] != value["digest"]:
                    return
                a["status"] = "approved" if value["choice"] == "once" and a.get("transportState") == "consumed" else "denied"
                self.journal.put("approval", key[1], a)
                self._apply_approval(a)
                rid = a["runId"]
            else:
                rid = key[1]
            run = self.journal.get("run", rid)
            if run:
                self._deliver_progress(run)
            if self.queue.dropped:
                self._delivery("", "coalesced", "Delivery queue dropped intermediate work; current local state is retained")

        finally:
            self.lock.release()

    def close(self):
        self.stopped.set()
        abandoned = self.queue.close()
        if abandoned:
            self._background_failure("Plugin unloaded with queued work; retry from the owning session")
        self.snapshot()
