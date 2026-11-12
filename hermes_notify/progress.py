"""Measured progress with durable activity identity and bounded event-driven updates."""

import time

from .client import NotifyError, identifier
from .workspace import TERMINAL, digest, notify_clip


class Progress:
    def _deliver_progress(self, run):
        # The internal run behind plain notify_send/notify_ask calls has no progress to show.
        if self.stopped.is_set() or run.get("auto"):
            return
        w = run["workspace"]
        project, rid = w["project"], w["runId"]
        mapping = self.journal.get("project", project, {})
        interval = max(5, min(300, float(self.settings.get("progress_interval_seconds", 5))))
        if mapping.get("hosted") and mapping.get("runId") == rid:
            delay = interval - (time.time() - mapping.get("lastSyncAt", 0))
            dirty = mapping.get("publishedHash") != digest({k: v for k, v in w.items() if k != "revision"})
            if dirty and delay > 0 and mapping.get("publishedState") == w["status"] and w["status"] not in TERMINAL:
                self.queue.submit(("progress", rid), None, delay=delay)
                return
            try:
                self._sync_workspace(run)
            except NotifyError as exc:
                self._delivery(project, "sync_failed", str(exc))
        if not self.settings.get("progress_enabled", False):
            return
        progress = self.journal.get("progress", rid, {"runId": rid, "key": self.key("activity", rid), "sequence": 0})
        state = w["status"]
        signature = digest([w["stage"], state, w["summary"], w["progress"]])
        desired_signature = signature
        if progress.get("signature") == signature:
            return
        terminal = state in TERMINAL
        changed_state = progress.get("state") != state
        interval = max(5, min(300, float(self.settings.get("progress_interval_seconds", 5))))
        if not terminal and not changed_state and time.time() - progress.get("lastAt", 0) < interval:
            # A single pending event sleeps until due; no timer or polling for idle tasks.
            self.queue.submit(("progress", rid), None, delay=interval - (time.time() - progress["lastAt"]))
            return
        props = {"status": notify_clip(state.replace("_", " ").title() if terminal or state in ("approved", "awaiting_approval") else w["stage"], 60),
                 "detail": notify_clip(w["summary"], 240) or None, "progress": w["progress"]}
        try:
            if progress.get("fallback"):
                if terminal and progress.get("activityId"):
                    body = {"status": props["status"], "symbol": "success" if state == "shipped" else "warning",
                            "ifSequence": progress["sequence"], "dismissAfterSeconds": 60}
                    try:
                        self._write_once("activity-end", body, run, "fallback-end",
                                         lambda body, key: self.api.end_activity(progress["activityId"], body, key))
                    except NotifyError as exc:
                        progress["endError"] = str(exc)
                        self.journal.put("progress", rid, progress)
                self._fallback_progress(run, progress, signature)
                return
            if not progress.get("activityId"):
                if terminal and not progress.get("startAttempted"):
                    self._fallback_progress(run, progress, signature)
                    return
                body = {"key": progress["key"], "title": notify_clip(w["name"], 80), "status": props["status"],
                        "style": "steps", "privacyMode": "private", "accentColor": "#30D158"}
                body.update({k: v for k, v in props.items() if v is not None})
                if self.settings.get("device_id"):
                    body["deviceIds"] = [self.settings["device_id"]]
                # Persist the original start body across crashes and later stage changes.
                progress.setdefault("startBody", body)
                progress.setdefault("startSignature", signature)
                progress.setdefault("startState", state)
                recovering = progress.get("startAttempted", False)
                progress["startAttempted"] = True
                self.journal.put("progress", rid, progress)
                if recovering:
                    # A lost create response cannot cause a second start.
                    result = self.api.get_activity(progress["key"])
                    if result.get("activity", {}).get("key") != progress["key"]:
                        raise NotifyError("Recovered activity key does not match this run")
                    result = {**result, "accepted": result.get("activity", {}).get("accepted", 0)}
                else:
                    result = self.api.start_activity(progress["startBody"], self.key("activity-start", rid))
            else:
                body = props | {"ifSequence": progress["sequence"]}
                if terminal:
                    body.update(symbol="success" if state == "shipped" else "warning", dismissAfterSeconds=60)
                else:
                    body.update(title=notify_clip(w["name"], 80), priority="high" if changed_state else "normal")
                pending = progress.get("pending")
                if pending:
                    current = self.api.get_activity(progress["activityId"]).get("activity", {})
                    if current.get("id") != progress["activityId"]:
                        raise NotifyError("Activity read returned a different identity")
                    expected = pending["body"]["ifSequence"]
                    if current.get("sequence") == expected + 1 and all(current.get("props", {}).get(k) == v for k, v in pending["body"].items() if k not in ("ifSequence", "priority", "dismissAfterSeconds")):
                        progress.update(sequence=current["sequence"], signature=pending["signature"], state=pending["state"], lastAt=time.time())
                        del progress["pending"]
                        self.journal.put("progress", rid, progress)
                        if progress["signature"] != signature:
                            return self._deliver_progress(run)
                        return
                    if current.get("sequence") != expected:
                        raise NotifyError("Activity changed remotely; stale update was not applied", status=409)
                    body = pending["body"]
                else:
                    progress["pending"] = {"body": body, "signature": signature, "state": state, "terminal": terminal}
                    self.journal.put("progress", rid, progress)
                pending = progress["pending"]
                result = (self.api.end_activity(progress["activityId"], body, self.key("activity-end", [rid, body]))
                          if pending["terminal"] else self.api.update_activity(progress["activityId"], body))
                signature, state = pending["signature"], pending["state"]
            latest_signature = desired_signature
            if not progress.get("activityId"):
                signature, state = progress["startSignature"], progress["startState"]
            activity = result.get("activity", {})
            identifier(activity.get("id"))
            if type(activity.get("sequence")) is not int or activity["sequence"] < 0:
                raise NotifyError("Invalid activity sequence")
            if progress.get("activityId") and progress["activityId"] != activity["id"]:
                raise NotifyError("Activity identity changed")
            if progress.get("pending") and activity["sequence"] != progress["pending"]["body"]["ifSequence"] + 1:
                raise NotifyError("Activity did not confirm the requested sequence")
            progress.update(activityId=activity["id"], sequence=activity["sequence"],
                            signature=signature, state=state, lastAt=time.time(), readiness=activity.get("readiness", {}))
            progress.pop("pending", None)
            self.journal.put("progress", rid, progress)
            delivery = self.delivery_state(result)
            self._delivery(project, delivery, "Progress receipt recorded; phone display is unconfirmed")
            if terminal and latest_signature != signature:
                # A recovered start must be ended even when its GET response has no
                # delivery counters. Never leave an unknown-start activity open.
                self._deliver_progress(run)
            elif activity.get("status") == "failed" or (delivery == "not_accepted" and not result.get("queued", 0)):
                self._fallback_progress(run, progress, latest_signature)
            elif latest_signature != signature:
                self._deliver_progress(run)
        except NotifyError as exc:
            if exc.status in (404, 422) or exc.code in ("ACTIVITY_CAPACITY_EXCEEDED", "NO_CAPABLE_DEVICES", "UNSUPPORTED_DEVICE"):
                self._fallback_progress(run, progress, signature)
            else:
                self._delivery(project, "progress_failed", str(exc))

    def _fallback_progress(self, run, progress, signature):
        w = run["workspace"]
        progress["fallback"] = True
        self.journal.put("progress", w["runId"], progress)
        body = {"title": notify_clip(w["name"], 80), "body": w["summary"] or w["stage"], "project": w["project"]}
        if w["appId"]:
            body["appId"] = w["appId"]
        if self.settings.get("device_id"):
            body["deviceIds"] = [self.settings["device_id"]]
        try:
            self._notification(run, body, "progress-" + signature)
            progress.update(signature=signature, state=w["status"], lastAt=time.time())
            self.journal.put("progress", w["runId"], progress)
        except NotifyError as exc:
            self._delivery(w["project"], "progress_failed", str(exc))
