"""Recoverable publication of the fixed release template or an existing HTTPS App."""

import time

from .client import NotifyError, https_url
from .workspace import app_id, digest, notify_text


class Publisher:
    def _sync_workspace(self, run):
        project = run["workspace"]["project"]
        mapping = self.journal.get("project", project, {})
        if mapping.get("runId") != run["workspace"]["runId"]:
            raise NotifyError("A newer release owns this project's workspace", status=409)
        # A durable, exact pending write is replayed before any newer content.
        desired = dict(run["workspace"])
        content_hash = digest({k: v for k, v in desired.items() if k != "revision"})
        pending = mapping.get("pendingSync")
        if not pending and mapping.get("publishedHash") == content_hash:
            return mapping
        if not pending:
            expected = mapping.get("remoteRevision", 0)
            workspace = desired | {"revision": expected + 1}
            pending = {"operationId": self.key("workspace", [project, expected, workspace]),
                       "expectedRevision": expected, "workspace": workspace, "hash": content_hash}
            mapping["pendingSync"] = pending
            self.journal.put("project", project, mapping)
        try:
            result = self.worker.put(project, pending["operationId"], pending["expectedRevision"], pending["workspace"])
        except NotifyError as exc:
            # Full replay responses are bounded. After their eviction (or the seven-day
            # operation-hash window), only an exact authenticated current snapshot proves
            # this pending write landed. Never rebase onto or overwrite different content.
            if exc.status != 409 or exc.code not in ("OPERATION_RESPONSE_EXPIRED", "REVISION_CONFLICT"):
                raise
            result = self.worker.get(project)
            if result.get("workspace") != pending["workspace"] or result.get("revision") != pending["expectedRevision"] + 1:
                raise NotifyError("Publisher history expired and current workspace conflicts with the pending write",
                                  status=409, code=exc.code) from None
        if result.get("workspace") != pending["workspace"] or result.get("revision") != pending["expectedRevision"] + 1:
            raise NotifyError("Publisher did not confirm the expected workspace revision")
        mapping.update(remoteRevision=result["revision"], publishedHash=pending["hash"],
                       lastSyncAt=time.time(), publishedState=pending["workspace"]["status"])
        del mapping["pendingSync"]
        self.journal.put("project", project, mapping)
        if pending["hash"] != content_hash:
            return self._sync_workspace(run)
        return mapping

    def publish(self, args, session):
        run = self._run(args, session)
        w = run["workspace"]
        project, rid = w["project"], w["runId"]
        mapping = self.journal.get("project", project)
        if mapping.get("runId") != rid:
            raise NotifyError("A newer release owns this project's workspace", status=409)
        existing_url = args.get("url")
        hosted = existing_url is None
        if hosted:
            # Access resolves only operator configuration and the captured secret.
            self.worker
            url = self.publisher_origin + "/projects/" + project
        else:
            url = https_url(notify_text(existing_url, 2048, "App URL"))
        name = notify_text(args.get("name", w["name"]), 40, "Notify App name (supply name if the workspace name is longer)")
        operation_id = self.key("publish", rid)
        operation = self.journal.get("publication", operation_id)
        if operation and (operation["url"] != url or operation["name"] != name):
            raise NotifyError("Publication is bound to its original name and URL", status=409)
        if mapping.get("url") and mapping["url"] != url:
            raise NotifyError("This project already has a different stable App URL", status=409)
        if not operation:
            operation = {"id": operation_id, "runId": rid, "url": url, "name": name,
                         "hosted": hosted, "phase": "prepared", "workspace": w}
            self.journal.put("publication", operation_id, operation)
        if operation["phase"] == "announced":
            self.queue.submit(("progress", rid), None)
            return {"publication": self._publication_result(operation), "workspace": run["workspace"], "resumed": True}
        if hosted:
            self.worker.health()
        if operation["phase"] == "prepared":
            if hosted:
                self._sync_workspace(run)
            operation["phase"] = "deployed" if hosted else "url_validated"
            self.journal.put("publication", operation_id, operation)
        if operation["phase"] in ("deployed", "url_validated"):
            result = self.api.register_app({"name": name, "url": url, "project": project})
            app = result.get("app", {})
            if not isinstance(app, dict) or app.get("url") != url:
                raise NotifyError("Notify returned a different App URL")
            app_id(app.get("id"))
            if mapping.get("appId") and mapping["appId"] != app["id"]:
                raise NotifyError("Notify changed the project's App identity")
            operation.update(phase="registered", appId=app["id"])
            self.journal.put("publication", operation_id, operation)
        if operation["phase"] == "registered":
            mapping = self.journal.get("project", project)
            mapping.update(appId=operation["appId"], url=url, hosted=hosted)
            self.journal.put("project", project, mapping)
            self._change(run, {"appId": operation["appId"]})
            if hosted:
                self._sync_workspace(run)
            operation["phase"] = "synced"
            self.journal.put("publication", operation_id, operation)
        if operation["phase"] == "synced":
            # Freeze announcement content. A later progress edit cannot change a retry intent.
            body = {"title": name, "body": operation["workspace"]["summary"] or "Your release workspace is ready.",
                    "project": project, "appId": operation["appId"], "url": url}
            if self.settings.get("device_id"):
                body["deviceIds"] = [self.settings["device_id"]]
            receipt = self._notification(run, body, operation_id)
            operation.update(receipt=receipt, phase="announced")
            self.journal.put("publication", operation_id, operation)
        return {"publication": self._publication_result(operation), "workspace": run["workspace"]}

    @staticmethod
    def _publication_result(operation):
        return {key: operation[key] for key in ("id", "phase", "url", "hosted", "appId", "receipt") if key in operation}
