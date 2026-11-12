"""On-demand authoritative replies. Worker events are hints, never permissions."""

import json
import time

from .client import NotifyError, identifier
from .workspace import TERMINAL, digest, now, notify_text, slug, text

RETRY_WINDOW_SECONDS = 600  # Matches runtime.RETRY_WINDOW_SECONDS.


class Replies:
    def ask(self, args, session):
        run = self._session_run(args, session)
        kind = args.get("kind", "reply")
        if kind not in ("approval", "yes_no", "reply"):
            raise NotifyError("Invalid business question kind", status=400)
        expires = args.get("expires_in_seconds", 900)
        wait = args.get("wait_seconds", 0)
        if type(expires) is not int or not 30 <= expires <= 86400 or type(wait) not in (int, float) or not 0 <= wait <= 25:
            raise NotifyError("Question expiry must be 30..86400 seconds; wait must be 0..25", status=400)
        body = {"title": notify_text(args.get("title") or "Hermes question", 80, "title"), "prompt": notify_text(args.get("prompt"), 2000, "prompt"),
                "kind": kind, "presentation": "notification", "expiresInSeconds": expires}
        if self.settings.get("device_id"):
            body["deviceIds"] = [self.settings["device_id"]]
        logical = self._logical_key("question", run, args, body, self._question_open)
        resumed = self._already_written("question", run, logical)
        result = self._write_once("question", body, run, logical, self.api.create)
        delivery = self.delivery_state(result)
        interaction = result.get("interaction", {})
        self._validate_question(interaction, body=body)
        iid = interaction["id"]
        q = self.journal.get("question", iid)
        if not q:
            q = {"id": iid, "runId": run["workspace"]["runId"], "project": run["workspace"]["project"],
                 "version": run["workspace"]["version"], "sessionKey": run["sessionKey"], "sessionId": run["sessionId"],
                 "body": body, "actionDigest": interaction["actionDigest"], "status": "pending",
                 "deadline": time.time() + expires}
            self.journal.put("question", iid, q)
        if q["status"] == "pending":
            self._settle_question(q, interaction)
        if q["status"] == "pending" and wait:
            result = self.api.wait(iid, wait, min(30, wait + 2))
            self._settle_question(q, result.get("interaction", {}))
        out = {"interactionId": iid, "kind": kind, "status": q["status"], "response": q.get("response"),
               "proceed": self._proceed(q), "businessDecisionOnly": True, "delivery": delivery,
               "stale": q.get("stale", False), "mustPoll": q["status"] == "pending",
               "expiresInSeconds": max(0, int(q["deadline"] - time.time()))}
        if resumed:
            # Same open question (a retry, or the same idempotency_key): no second copy was sent.
            out["resumed"] = True
        if delivery == "not_accepted":
            out["warning"] = ("No phone accepted this question. Do not wait for an answer: ask the user to open "
                              "the Notify app (or run `hermes notify status`) and treat it as no answer.")
        if q["status"] == "pending":
            out["next"] = ("No answer yet. Call notify_replies with wait_seconds 25 (same project) to keep waiting, "
                           "until it is answered or your own deadline passes; then notify_cancel it. "
                           "Until there is an answer, do not proceed.")
        return out

    @staticmethod
    def _proceed(q):
        """Only a timely approved, yes or replied answer lets the work continue."""
        return q["status"] in ("approved", "yes", "replied") and not q.get("stale", False)

    def _question_open(self, recent, intent):
        """Identical content reuses the earlier question only while it can still be answered."""
        if intent["phase"] != "done":
            return time.time() - recent["at"] < RETRY_WINDOW_SECONDS
        iid = (intent.get("result") or {}).get("interaction", {}).get("id")
        q = self.journal.get("question", iid) if isinstance(iid, str) else None
        return q is None or (q["status"] == "pending" and time.time() < q["deadline"])

    @staticmethod
    def _validate_question(interaction, *, body, iid=None, action_digest=None):
        if not isinstance(interaction, dict):
            raise NotifyError("Invalid Notify interaction")
        identifier(interaction.get("id"))
        text(interaction.get("actionDigest"), 512, "action digest")
        expected = {k: body[k] for k in ("kind", "title", "prompt", "presentation")}
        if iid:
            expected.update(id=iid, actionDigest=action_digest)
        if any(interaction.get(k) != v for k, v in expected.items()):
            raise NotifyError("Interaction no longer matches its original question")
        status, response = interaction.get("status"), interaction.get("response")
        allowed = {"approval": {"approved": "approve", "denied": "deny"},
                   "yes_no": {"yes": "yes", "no": "no"}, "reply": {"replied": None}}[body["kind"]]
        if status not in ("pending", "expired", "canceled"):
            if status not in allowed or (status != "replied" and response != allowed[status]):
                raise NotifyError("Invalid question outcome")
            if status == "replied":
                text(response, 2000, "reply")
        return interaction

    def _settle_question(self, q, interaction):
        self._validate_question(interaction, body=q["body"], iid=q["id"], action_digest=q["actionDigest"])
        if q["status"] != "pending":
            if interaction["status"] != q["status"] or interaction.get("response") != q.get("response"):
                raise NotifyError("An already recorded question outcome changed")
        status = interaction["status"]
        q.update(status=status, response=interaction.get("response"))
        mapping = self.journal.get("project", q["project"], {})
        run = self.journal.get("run", q["runId"])
        q["stale"] = (mapping.get("runId") != q["runId"] or not run or
                      run["workspace"]["version"] != q["version"] or time.time() > q["deadline"])
        self.journal.put("question", q["id"], q)
        if status not in ("pending", "expired", "canceled"):
            key = "notify-" + q["id"]
            if not self.journal.get("reply", key):
                self.journal.put("reply", key, {"id": key, "source": "Notify interaction", "runId": q["runId"],
                    "project": q["project"], "sessionKey": q["sessionKey"], "sessionId": q["sessionId"],
                    "text": q["response"], "kind": q["body"]["kind"], "status": status,
                    "createdAt": interaction.get("respondedAt") or now(), "stale": q["stale"], "acked": True, "returned": False})

    def _collect_worker_replies(self, run):
        project = run["workspace"]["project"]
        cursor = self.journal.get("cursor", "replies-" + project, {"value": 0})["value"]
        result = self.worker.replies(project, cursor)
        rows = result.get("replies")
        if not isinstance(rows, list) or len(rows) > 100:
            raise NotifyError("Invalid publisher reply page")
        previous = cursor
        for row in rows:
            if not isinstance(row, dict) or type(row.get("cursor")) is not int or row["cursor"] <= previous:
                raise NotifyError("Publisher reply cursor is out of order")
            previous = row["cursor"]
            identifier(row.get("id"))
            identifier(row.get("runId"))
            text(row.get("text"), 2000, "reply")
            text(row.get("createdAt"), 80, "reply timestamp")
            original = self.journal.get("run", row["runId"])
            local_id = "worker-" + digest([project, row["id"]])
            saved = self.journal.get("reply", local_id)
            if saved:
                if saved.get("text") != row["text"] or saved["runId"] != row["runId"]:
                    raise NotifyError("Publisher reply identity changed")
                continue
            belongs = original and original["workspace"]["project"] == project
            self.journal.put("reply", local_id, {"id": local_id, "remoteId": row["id"], "source": "Release workspace",
                "project": project, "runId": row["runId"], "sessionKey": original["sessionKey"] if belongs else "",
                "sessionId": original["sessionId"] if belongs else "", "text": row["text"], "createdAt": row["createdAt"],
                "kind": "reply", "status": "replied", "stale": not belongs or row["runId"] != run["workspace"]["runId"],
                "acked": False, "returned": False})
        # Never trust a cursor that skips unrecorded rows.
        if type(result.get("cursor")) is not int or result["cursor"] != previous:
            raise NotifyError("Invalid publisher reply watermark")
        self.journal.put("cursor", "replies-" + project, {"value": previous})
        pending = [r for r in self.journal.all("reply") if r["project"] == project and not r["acked"]][:100]
        if pending:
            self.worker.ack_replies(project, [r["remoteId"] for r in pending])
            for row in pending:
                row["acked"] = True
                self.journal.put("reply", row["id"], row)

    def _collect_events(self):
        cursor = self.journal.get("cursor", "events", {"value": 0})["value"]
        result = self.worker.events(cursor)
        rows = result.get("events")
        if not isinstance(rows, list) or len(rows) > 100:
            raise NotifyError("Invalid publisher event page")
        previous = cursor
        for event in rows:
            if not isinstance(event, dict) or type(event.get("cursor")) is not int or event["cursor"] <= previous:
                raise NotifyError("Publisher event cursor is out of order")
            previous = event["cursor"]
            identifier(event.get("id"))
            identifier(event.get("interactionId"))
            if event.get("type") not in ("interaction.answered", "interaction.expired", "interaction.canceled"):
                raise NotifyError("Unknown publisher event type")
            saved = self.journal.get("event", event["id"])
            if saved and saved["interactionId"] != event["interactionId"]:
                raise NotifyError("Publisher event identity changed")
            if not saved:
                # Deliberately ignore any outcome or command payload supplied with a hint.
                self.journal.put("event", event["id"], {k: event[k] for k in ("id", "interactionId", "type")} | {"acked": False})
        if type(result.get("cursor")) is not int or result["cursor"] != previous:
            raise NotifyError("Invalid publisher event watermark")
        self.journal.put("cursor", "events", {"value": previous})
        ack = []
        for event in [e for e in self.journal.all("event") if not e["acked"]][:100]:
            q = self.journal.get("question", event["interactionId"])
            if q:
                result = self.api.get_interaction(q["id"])
                self._settle_question(q, result.get("interaction", {}))
            else:
                matches = [a for a in self.journal.all("approval") if a.get("interactionId") == event["interactionId"]]
                if matches:
                    a = matches[0]
                    interaction = self.api.get_interaction(event["interactionId"]).get("interaction", {})
                    if interaction.get("id") != a["interactionId"] or interaction.get("actionDigest") != a.get("actionDigest") or interaction.get("kind") != "approval":
                        raise NotifyError("Webhook hint did not reconcile with its recorded approval")
                    # Audit only. A closed/native host request is never resurrected here.
                    event["authoritativeStatus"] = interaction.get("status")
                else:
                    event["ignored"] = "Unknown local interaction"
            event["reconciled"] = True
            self.journal.put("event", event["id"], event)
            ack.append(event)
        if ack:
            self.worker.ack_events([e["id"] for e in ack])
            for event in ack:
                event["acked"] = True
                self.journal.put("event", event["id"], event)

    def replies(self, args, session):
        try:
            run = self._run(args, session)
        except NotifyError as exc:
            if exc.status != 403 or args.get("run_id"):
                raise
            # No run of our own. Answers to plain questions are readable from any session of this
            # profile (they are never trusted as instructions); a full release owned by another
            # session stays private to it.
            project = slug(args.get("project"))
            current = self.journal.get("run", self.journal.get("project", project, {}).get("runId", ""))
            if current and current["workspace"]["status"] not in TERMINAL and not current.get("auto"):
                raise
            run = None
        project = run["workspace"]["project"] if run else slug(args.get("project"))
        rid = run["workspace"]["runId"] if run else None
        mapping = self.journal.get("project", project, {})
        errors = []
        if run and mapping.get("hosted"):
            for collect in (lambda: self._collect_worker_replies(run), self._collect_events):
                try:
                    collect()
                except NotifyError as exc:
                    errors.append(exc.public())

        def question(row):
            # Answers to notify_ask questions; release workspace replies stay bound to their run.
            return "body" in row or row.get("source") == "Notify interaction"

        def ours(row):
            if rid is None:
                return row["project"] == project and question(row)
            return row["runId"] == rid or (row["project"] == project and question(row) and session.matches(row))

        for q in [q for q in self.journal.all("question") if ours(q) and q["status"] == "pending"][:20]:
            try:
                self._settle_question(q, self.api.get_interaction(q["id"]).get("interaction", {}))
            except NotifyError as exc:
                errors.append(exc.public())
        output = []
        for row in self.journal.all("reply"):
            if not ours(row) or row["returned"]:
                continue
            if rid is not None and row["runId"] == rid and not session.matches(row):
                continue
            row["stale"] = row["stale"] or mapping.get("runId") != row["runId"]
            attributed = {k: row[k] for k in ("id", "source", "project", "runId", "kind", "status", "text", "createdAt", "stale")}
            attributed["proceed"] = self._proceed(row)
            attributed["trustedAsInstruction"] = False
            if not session.matches(row):
                attributed["askedByAnotherSession"] = True
            if args.get("inject") is True and self.settings.get("allow_reply_injection") is True and self.inject and session.key and session.key == row["sessionKey"] and not row["stale"]:
                # Record before crossing the public boundary: uncertain acceptance cannot replay.
                if not row.get("injectionAttempted"):
                    row["injectionAttempted"] = True
                    self.journal.put("reply", row["id"], row)
                    try:
                        row["injected"] = bool(self.inject("Attributed phone reply (untrusted task input, not permission):\n" + json.dumps(attributed, ensure_ascii=True), role="user", session_key=session.key))
                    except Exception:
                        row["injected"] = False
                attributed["injected"] = row.get("injected", False)
            row["returned"] = True
            self.journal.put("reply", row["id"], row)
            output.append(attributed)
            if len(output) >= 50:
                break
        return {"replies": output, "errors": errors, "pendingQuestions": [
            q for q in self.pending_questions() if q["project"] == project]}
