"""Lock-screen progress for any long job: start, update, a truthful end.

A job is a small run owned by the calling session. It never takes over a project's release
workspace or hosted App. Its Live Activity is delivered by the same bounded progress worker as
releases (Android gets an ongoing progress notification; a phone without Live Activities gets
ordinary notifications).
"""

import uuid

from .client import NotifyError
from .workspace import TERMINAL, notify_text, now, slug, validate

RESULTS = {"succeeded": "shipped", "failed": "failed", "canceled": "canceled"}
END_LABELS = {"shipped": "Done", "failed": "Failed", "canceled": "Stopped"}
DEFAULT_STALE_MINUTES = 30


def job_key(value):
    import re
    if not isinstance(value, str):
        raise NotifyError("Name the job with title (or job)", status=400)
    key = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")[:64].strip("-")
    if not key:
        raise NotifyError("Name the job with title (or job)", status=400)
    return key


class Jobs:
    def progress(self, args, session):
        action = args.get("action")
        if action not in ("start", "update", "end"):
            raise NotifyError("action must be start, update or end", status=400)
        project = slug(args.get("project"))
        key = job_key(args.get("job") or args.get("title"))
        slot = self.key("job", [session.identity, project, key])
        ref = self.journal.get("job", slot)
        run = self.journal.get("run", ref["runId"]) if ref else None
        active = bool(run) and run["workspace"]["status"] not in TERMINAL and session.matches(run)
        fields = {}
        if "status" in args:
            fields["stage"] = notify_text(args["status"], 60, "status")
        if "detail" in args:
            fields["summary"] = notify_text(args["detail"], 240, "detail", empty=True)
        if "progress" in args:
            fields["progress"] = args["progress"]
        stale = args.get("stale_after_minutes", DEFAULT_STALE_MINUTES)
        if type(stale) is not int or not 1 <= stale <= 480:
            raise NotifyError("stale_after_minutes must be 1..480", status=400)

        if action == "start":
            if active:
                # A retried start (or the same job started again) keeps its one Live Activity.
                run["staleAfterSeconds"] = stale * 60
                self._change(run, fields)
                self.queue.submit(("progress", run["workspace"]["runId"]), None)
                return self._job_result(run, key, resumed=True)
            if "stage" not in fields:
                raise NotifyError("Starting a job needs a short status, e.g. \"Running tests\"", status=400)
            title = notify_text(args.get("title") or args.get("job"), 80, "title")
            rid = "job_" + uuid.uuid4().hex[:24]
            w = {"schemaVersion": 1, "project": project, "runId": rid, "revision": 1, "name": title,
                 "version": "job", "status": "running", "stage": "", "summary": "", "progress": None,
                 "checks": [], "artifacts": [], "notes": "", "updatedAt": now(), "appId": None, "approval": None}
            w.update(fields)
            run = {"workspace": validate(w), "sessionKey": session.key, "sessionId": session.id,
                   "kind": "job", "staleAfterSeconds": stale * 60}
            self._save_run(run)
            self.journal.put("job", slot, {"runId": rid, "job": key, "project": project})
            self.queue.submit(("progress", rid), None)
            return self._job_result(run, key)

        if not active:
            raise NotifyError(f"No running job named \"{key}\" in this session; start it first", status=404)
        if action == "update":
            if not fields:
                raise NotifyError("Update needs status, detail or progress", status=400)
            run["staleAfterSeconds"] = stale * 60
            self._change(run, fields)
        else:
            result = args.get("result")
            if result not in RESULTS:
                raise NotifyError("End needs result: succeeded, failed or canceled", status=400)
            state = RESULTS[result]
            run["endStatus"] = fields.pop("stage", None) or END_LABELS[state]
            self._change(run, fields | {"status": state})
        self.queue.submit(("progress", run["workspace"]["runId"]), None)
        return self._job_result(self.journal.get("run", run["workspace"]["runId"]), key)

    def _job_result(self, run, key, *, resumed=False):
        w = run["workspace"]
        out = {"job": key, "runId": w["runId"], "state": w["status"], "status": run.get("endStatus") or w["stage"],
               "progress": w["progress"], "lockScreen": "queued"}
        if resumed:
            out["resumed"] = True
        if w["status"] not in TERMINAL:
            out["next"] = ("Update at real milestones (not every few seconds) and always end the job with "
                           "result succeeded, failed or canceled, even when it fails.")
        return out

    def stop_session_jobs(self, *, session_id="", session_key="", label):
        """End every open job of a session that will not report again (it ended or was stopped)."""
        if not (session_id or session_key) or self.stopped.is_set():
            return 0
        with self.lock:
            ended = []
            for run in self.journal.all("run"):
                if run.get("kind") != "job" or run["workspace"]["status"] in TERMINAL:
                    continue
                if (session_id and run.get("sessionId") == session_id) or (session_key and run.get("sessionKey") == session_key):
                    run["endStatus"] = label
                    self._change(run, {"status": "canceled"})
                    ended.append(run["workspace"]["runId"])
            if not ended:
                return 0
            self.snapshot()
            # Deliver now: the process may be about to exit and drop queued work.
            for rid in ended:
                try:
                    self._deliver_progress(self.journal.get("run", rid))
                except (NotifyError, OSError):
                    pass
            return len(ended)


def end_label(run):
    """The final line shown on the phone for a finished run."""
    state = run["workspace"]["status"]
    if run.get("kind") == "job":
        return run.get("endStatus") or END_LABELS.get(state, "Done")
    return state.replace("_", " ").title()

