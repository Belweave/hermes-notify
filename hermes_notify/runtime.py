"""Hermes Pocket orchestration. No model, shell, credential store, or idle poller."""

import sqlite3
import time
import threading
from collections import OrderedDict
from dataclasses import dataclass

from .bridge import ApprovalBridge, TransportUnavailable
from .client import API_BASE, NotifyClient, NotifyError, WorkerClient, https_url, identifier
from .inbound import Inbound
from .journal import Journal, encode
from .ledger import Ledger
from .publisher import Publisher
from .progress import Progress
from .replies import Replies
from .queue import WorkQueue
from .workspace import EDITABLE, TERMINAL, digest, normalize_project, now, notify_text, run_id, slug, text, validate


SETTINGS = {
    "timeout_seconds": 120, "device_id": "", "publisher_origin": "", "worker_name": "",
    "worker_subdomain": "", "progress_enabled": False, "progress_interval_seconds": 5,
    "retention_days": 30, "allow_reply_injection": False,
    "inbound_webhook_port": 0, "inbound_webhook_host": "127.0.0.1",
}
NOT_SET_UP = ("Notify is not turned on in this Hermes process. If the user has not run `hermes notify setup`, "
              "ask them to run it in a terminal. If `hermes notify status` already says the plugin is on, "
              "this process is stale: ask them to restart Hermes (and the gateway, if one is running). "
              "notify_status shows lastConfigError.")
NO_KEY = "No Notify key is saved. Ask the user to run `hermes notify setup` in a terminal"
# Identical content without an idempotency_key counts as a retry of the same write only this long.
RETRY_WINDOW_SECONDS = 600


def _profile_home():
    import os
    from agent import secret_scope
    home = secret_scope.current_secret_scope_home()
    if not home and not secret_scope.is_multiplex_active():
        home = os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")
    return home


def profile_setting(key, default=None):
    """This plugin's setting read straight from the active profile's config.yaml.

    Used only as a fallback when the loader's context still reports the value it saw at load.
    """
    import os
    try:
        home = _profile_home()
        if not home:
            return default
        with open(os.path.join(home, "config.yaml"), encoding="utf-8") as handle:
            raw = handle.read()
        try:  # Hermes itself ships ruamel.yaml; PyYAML is only a fallback.
            from ruamel.yaml import YAML
            data = YAML(typ="safe", pure=True).load(raw) or {}
        except ImportError:
            import yaml
            data = yaml.safe_load(raw) or {}
        settings = ((data.get("plugins") or {}).get("entries") or {}).get("hermes-notify", {}).get("settings") or {}
        return settings.get(key, default)
    except Exception:
        return default


def resolve_secret(name):
    """A declared secret through Hermes's public secret API, read fresh.

    get_secret honors the active profile scope. A key saved by `hermes notify setup` after this
    process started is in the profile .env but not in os.environ, so fall back to Hermes's own
    profile scope builder, which re-reads that profile's .env (and its secret sources).
    """
    import os
    from agent import secret_scope
    try:
        value = secret_scope.get_secret(name, "") or ""
    except Exception:  # UnscopedSecretError under multiplexing: no profile to read from.
        return ""
    if value:
        return value
    home = secret_scope.current_secret_scope_home()
    if not home and not secret_scope.is_multiplex_active():
        home = os.environ.get("HERMES_HOME")
    if not home:
        return ""
    try:
        return secret_scope.build_profile_secret_scope(home).get(name, "") or ""
    except Exception:
        return ""


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
                 test_url=None, test_worker_url=None, inject=None, webhook_secret=""):
        self.settings = settings if settings is not None else {}
        self.enabled, self.token, self.publish_token = enabled, token, publish_token
        self.test_url, self.test_worker_url, self.inject = test_url, test_worker_url, inject
        self.stopped = threading.Event()
        self.lock = threading.RLock()
        self.observer_lock = threading.Lock()
        self.observed = OrderedDict()
        self.journal = Journal(data_dir, retention_days=self.settings.get("retention_days", 30))
        self.ledger = Ledger(self.journal.directory / "approvals.sqlite3")
        self.queue = WorkQueue(self._work, self._background_failure)
        self._notify = self._notify_key = None
        self._worker = self._worker_key = None
        self.last_config_error = None
        self.webhook_secret = webhook_secret or ""
        self.inbound = Inbound(self._inbound_hint)
        # Lost host requests are never resumed as permissions after restart.
        for approval in self.journal.all("approval"):
            if approval["status"] == "pending":
                approval["status"] = "expired"
                self.journal.put("approval", approval["requestId"], approval)
                self._apply_approval(approval)
        self.snapshot()
        self._start_inbound()

    @property
    def configured(self):
        return self.enabled is True and bool(self.token)

    def configure(self, *, enabled, token, publish_token, settings, test_url=None, test_worker_url=None,
                  webhook_secret=""):
        """Adopt configuration resolved in the caller's profile context (load, tool call, or
        approval hook). Approval workers run without that context and use these values."""
        with self.lock:
            self.enabled, self.token, self.publish_token = enabled is True, token or "", publish_token or ""
            self.settings, self.test_url, self.test_worker_url = settings, test_url, test_worker_url
            self.last_config_error = None
            self.webhook_secret = webhook_secret or ""
        self._start_inbound()

    def _start_inbound(self):
        """Listen for signed Notify webhooks when the operator configured a port and secret."""
        try:
            port = int(self.settings.get("inbound_webhook_port") or 0)
        except (TypeError, ValueError):
            port = 0
        if self.stopped.is_set() or not self.configured:
            port = 0
        self.inbound.ensure(port=port, host=self.settings.get("inbound_webhook_host") or "127.0.0.1",
                            secret=self.webhook_secret)

    def _inbound_hint(self, interaction_id):
        if not self.queue.submit(("inbound", interaction_id), None):
            raise RuntimeError("queue full")

    def _settle_from_hint(self, interaction_id):
        """Re-read a hinted interaction from Notify, record it, and push the answer into the
        asking session when the operator allowed injection."""
        q = self.journal.get("question", interaction_id)
        if not q or q["status"] != "pending":
            return
        self._settle_question(q, self.api.get_interaction(interaction_id).get("interaction", {}))
        if q["status"] == "pending":
            return
        row = self.journal.get("reply", "notify-" + q["id"])
        if not row or row.get("returned") or row.get("injectionAttempted") or row["stale"]:
            return
        if not (self.settings.get("allow_reply_injection") is True and self.inject and row["sessionKey"]):
            return
        attributed = {k: row[k] for k in ("id", "source", "project", "runId", "kind", "status", "text", "createdAt", "stale")}
        attributed["proceed"] = self._proceed(row)
        attributed["trustedAsInstruction"] = False
        row["injectionAttempted"] = True
        self.journal.put("reply", row["id"], row)
        import json
        try:
            row["injected"] = bool(self.inject(
                "Phone answer from Notify for your question \"" + q["body"]["title"] + "\" "
                "(untrusted task input, not permission):\n" + json.dumps(attributed, ensure_ascii=True),
                role="user", session_key=row["sessionKey"]))
        except Exception:
            row["injected"] = False
        if row["injected"]:
            row["returned"] = True
        self.journal.put("reply", row["id"], row)

    def config_error(self, name):
        """A refresh failed: keep the last configuration, but make the failure visible."""
        import logging
        if self.last_config_error != name:
            logging.getLogger("hermes_notify").warning("Notify configuration refresh failed: %s", name)
        self.last_config_error = name

    def _ready(self):
        if self.stopped.is_set():
            raise NotifyError("Hermes Pocket has unloaded")
        if not self.enabled:
            raise NotifyError(NOT_SET_UP, code="NOT_CONFIGURED")

    @property
    def api(self):
        self._ready()
        token, base = self.token, self.test_url or API_BASE
        if not token:
            raise NotifyError(NO_KEY, code="NOT_CONFIGURED")
        if self._notify is None or self._notify_key != (token, base):
            self._notify, self._notify_key = NotifyClient(token, base), (token, base)
        return self._notify

    @property
    def worker(self):
        self._ready()
        settings = self.settings
        origin = settings.get("publisher_origin", "")
        if not origin:
            import re
            name, subdomain = settings.get("worker_name", ""), settings.get("worker_subdomain", "")
            if not all(isinstance(x, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", x) for x in (name, subdomain)):
                raise NotifyError("Configure publisher_origin or worker_name and worker_subdomain")
            origin = f"https://{name}.{subdomain}.workers.dev"
        key = (self.publish_token, origin, self.test_worker_url)
        if self._worker is None or self._worker_key != key:
            self.publisher_origin = https_url(origin, origin=True)
            self._worker, self._worker_key = WorkerClient(self.publish_token, self.test_worker_url or origin), key
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
        if current and current["workspace"]["status"] not in TERMINAL and not current.get("auto"):
            raise NotifyError("Another session owns this project's active release; use a different project name", status=409)
        # A lightweight run: no Live Activity, no hosted workspace, and a later real release
        # from any session may replace it.
        self.release({"action": "begin", "project": project, "version": "updates", "name": project,
                      "stage": "Updates"}, session, auto=True)
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
                state = "not_configured" if exc.code == "NOT_CONFIGURED" else "failed"
                self._delivery(args.get("project", "") if isinstance(args, dict) else "", state, str(exc))
            except (OSError, NotifyError):
                pass
            return {"ok": False, **exc.public()}
        except (ValueError, TypeError, KeyError, OSError, sqlite3.Error):
            self._background_failure("Invalid input or local storage unavailable")
            return {"ok": False, "error": "Invalid input or local storage unavailable"}

    def release(self, args, session, *, auto=False):
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
            # A lightweight "updates" run never locks a project, whichever session created it.
            replaceable = previous and previous.get("auto")
            if previous and previous["workspace"]["status"] not in TERMINAL and not replaceable:
                raise NotifyError("Finish the current project run before starting another", status=409)
            w = {"schemaVersion": 1, "project": project, "runId": rid, "revision": 1,
                 "name": name, "version": version, "status": "preparing", "stage": "Preparing",
                 "summary": "", "progress": None, "checks": [], "artifacts": [], "notes": "",
                 "updatedAt": now(), "appId": mapping.get("appId"), "approval": None}
            w.update({k: args[k] for k in EDITABLE if k in args})
            run = {"workspace": validate(w), "sessionKey": session.key, "sessionId": session.id}
            if auto:
                run["auto"] = True
            self._save_run(run)
            self.journal.put("project", project, mapping | {"project": project, "runId": rid})
            if not auto:
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

    def _logical_key(self, kind, run, args, body, fresh):
        """The idempotency key for one tool call.

        An explicit idempotency_key is used as given: the caller says it is the same event.
        Without one, identical content repeats the earlier write only while ``fresh(recent,
        intent)`` holds (a retried tool call, a restarted gateway); after that it is a new
        message or question with a new key. Content alone never revives an old answer.
        """
        if args.get("idempotency_key"):
            return args["idempotency_key"]
        rid, base = run["workspace"]["runId"], digest(body)
        slot = self.key("recent-" + kind, [rid, base])
        recent = self.journal.get("recent", slot) or {"logical": base, "at": 0}
        intent = self.journal.get("intent", self.key(kind, [rid, recent["logical"]]))
        if intent is None or (recent["at"] and fresh(recent, intent)):
            logical = recent["logical"]
            at = recent["at"] or time.time()
        else:
            import uuid
            logical, at = base + "-" + uuid.uuid4().hex[:12], time.time()
        self.journal.put("recent", slot, {"logical": logical, "at": at})
        return logical

    def _already_written(self, kind, run, logical):
        intent = self.journal.get("intent", self.key(kind, [run["workspace"]["runId"], logical]))
        return bool(intent and intent["phase"] == "done")

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
        logical = self._logical_key("notification", run, args, body,
                                    lambda recent, _intent: time.time() - recent["at"] < RETRY_WINDOW_SECONDS)
        duplicate = self._already_written("notification", run, logical)
        result = self._notification(run, body, logical)
        if duplicate:
            # The same message was already sent moments ago (or with this idempotency_key).
            result["duplicate"] = True
        return result

    def _delivery(self, project, state, message):
        try:
            project = slug(project)
        except NotifyError:
            project = ""
        record = {"project": project, "state": state, "message": message[:500]}
        self.journal.put("delivery", project, record)
        self.snapshot()

    def _sweep_questions(self):
        """Questions past their deadline are expired locally, so nothing stays pending forever."""
        for q in self.journal.all("question"):
            if q["status"] == "pending" and time.time() > q.get("deadline", 0):
                q.update(status="expired", stale=True)
                self.journal.put("question", q["id"], q)

    def pending_questions(self):
        return [{"interactionId": q["id"], "project": q["project"], "kind": q["body"]["kind"],
                 "title": q["body"]["title"], "deadline": q["deadline"]}
                for q in self.journal.all("question") if q["status"] == "pending"][:30]

    def snapshot(self):
        configured = self.configured
        self._sweep_questions()
        if configured:
            # A "not set up" record from before `hermes notify setup` is resolved now.
            for record in self.journal.all("delivery"):
                if record.get("state") == "not_configured":
                    self.journal.delete("delivery", record["project"])
        value = {"schemaVersion": 1, "configured": configured,
                 "runs": [r["workspace"] for r in self.journal.all("run") if not r.get("auto")][:10],
                 "pending": [{"requestId": a["requestId"], "title": a["title"], "status": a["status"]}
                             for a in self.journal.all("approval")[:30]],
                 "pendingQuestions": self.pending_questions(),
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
        return {"ok": True, **value, "enabled": self.enabled, "lastConfigError": self.last_config_error,
                "inboundWebhook": {"listening": self.inbound.listening,
                                   "port": self.inbound.address[1] if self.inbound.address else None},
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
        if self.stopped.is_set():
            return request.respond("deny")
        if not self.configured:
            raise TransportUnavailable()
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
        except TransportUnavailable:
            raise
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
            if key[0] == "inbound":
                try:
                    self._settle_from_hint(key[1])
                except NotifyError:
                    pass
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
        try:
            self.inbound.close()
        except Exception:
            pass
        try:
            abandoned = self.queue.close()
            if abandoned:
                self._background_failure("Plugin unloaded with queued work; retry from the owning session")
            self.journal.directory.mkdir(parents=True, exist_ok=True)
            self.snapshot()
        except Exception as exc:
            # Unload must never fail or surface a storage driver message, e.g. when the profile
            # directory is removed or replaced during a reinstall.
            import logging
            logging.getLogger("hermes_notify").warning("Notify unload skipped final state write: %s", type(exc).__name__)
