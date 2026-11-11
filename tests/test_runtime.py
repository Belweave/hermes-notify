import os
import importlib.util
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_notify.client import NotifyClient, NotifyError, WorkerClient, https_url
from hermes_notify.journal import Journal
from hermes_notify.runtime import Runtime, Session
from scripts.mock_notify import PocketMock
from test_approval import request

SESSION = Session("route_a", "session_a")




def call(runtime, tool, **args):
    return runtime.call("notify_" + tool, args, SESSION)


def begin(runtime, version="1.0", **extra):
    result = call(runtime, "release", action="begin", project="demo", name="Demo release", version=version, **extra)
    assert result["ok"], result
    assert runtime.queue.drain(30)
    return result["workspace"]


def update(runtime, *, drain=True, **extra):
    w = call(runtime, "release", action="status", project="demo")["workspace"]
    result = call(runtime, "release", action="update", project="demo", expected_revision=w["revision"], **extra)
    if drain:
        assert runtime.queue.drain(30)
    return result


def finish(runtime, result="succeeded"):
    w = call(runtime, "release", action="status", project="demo")["workspace"]
    result = call(runtime, "release", action="finish", project="demo", expected_revision=w["revision"], result=result, result_summary="Release action returned successfully" if result == "succeeded" else "Release action did not complete")
    assert runtime.queue.drain(30)
    return result


def publish(runtime):
    result = call(runtime, "publish_app", project="demo")
    assert result["ok"], result
    return result


def restart(runtime, url):
    runtime.close()
    return Runtime(runtime.journal.directory, enabled=True, token="dummy", publish_token="dummy",
                   settings=runtime.settings, test_url=url + "/api/agent", test_worker_url=url)


@pytest.mark.parametrize("publication_completed", [False, True])
def test_superseded_publication_retry_cannot_replace_current_workspace(pocket, publication_completed):
    rt, mock, _ = pocket
    first = begin(rt, version="1.0")
    if publication_completed:
        publish(rt)
    else:
        mock.fail("POST", "/api/agent/apps", status=403)
        assert not call(rt, "publish_app", project="demo")["ok"]
    finish(rt)
    second = begin(rt, version="2.0")
    publish(rt)
    assert rt.queue.drain(30)
    requests_before = len(mock.requests)
    retry = call(rt, "publish_app", project="demo", run_id=first["runId"])
    assert not retry["ok"] and retry["httpStatus"] == 409
    assert len(mock.requests) == requests_before
    assert mock.workspaces["demo"]["runId"] == second["runId"]
    assert rt.journal.get("project", "demo")["runId"] == second["runId"]


@pytest.mark.parametrize("resume_tool", ["release", "publish_app"])
def test_owner_can_resume_terminal_delivery_after_unload(pocket, resume_tool):
    rt, mock, url = pocket
    rt.settings["progress_enabled"] = True
    begin(rt)
    publish(rt)
    assert rt.queue.drain(30)
    # Hold the runtime lock so the real worker cannot deliver the queued finish.
    # Persist through the public tool first, then invoke the actual unload path.
    with rt.lock:
        workspace = call(rt, "release", action="status", project="demo")["workspace"]
        done = call(rt, "release", action="finish", project="demo",
                    expected_revision=workspace["revision"], result="succeeded",
                    result_summary="Release action returned successfully")
        assert done["ok"] and done["workspace"]["status"] == "shipped"
        rt.close()
    assert mock.workspaces["demo"]["status"] == "preparing"
    assert next(iter(mock.activities.values()))["status"] != "ended"
    resumed = restart(rt, url)
    try:
        args = {"project": "demo"}
        if resume_tool == "release":
            args.update(action="begin", version="1.0")
        result = call(resumed, resume_tool, **args)
        assert result["ok"] and result["resumed"]
        assert resumed.queue.drain(30)
        assert mock.workspaces["demo"]["status"] == "shipped"
        assert next(iter(mock.activities.values()))["status"] == "ended"
        assert mock.count("POST", "/api/agent/activities") == 1
        requests_after_recovery = len(mock.requests)
        assert call(resumed, resume_tool, **args)["resumed"]
        assert resumed.queue.drain(30)
        assert len(mock.requests) == requests_after_recovery
    finally:
        resumed.close()


@pytest.mark.parametrize("restart_before_finish", [False, True])
def test_completion_recovers_and_ends_a_start_with_a_lost_response(pocket, restart_before_finish):
    rt, mock, url = pocket
    rt.settings["progress_enabled"] = True
    mock.fail("POST", "/api/agent/activities", status=503, after=True)
    begin(rt)
    assert len(mock.activities) == 1
    # Authoritative activity reads need not repeat create-time delivery counters.
    next(iter(mock.activities.values())).pop("accepted")
    active = restart(rt, url) if restart_before_finish else rt
    try:
        assert finish(active)["ok"]
        activity = next(iter(mock.activities.values()))
        assert activity["status"] == "ended"
        assert mock.count("POST", "/api/agent/activities") == 1
        read = ("GET", "/api/agent/activities/" + activity["key"])
        end = ("POST", "/api/agent/activities/" + activity["id"] + "/end")
        assert mock.count(*read) == mock.count(*end) == 1
        requests = [(method, path) for method, path, *_ in mock.requests]
        assert requests.index(read) < requests.index(end)
    finally:
        if restart_before_finish:
            active.close()


def test_release_lifecycle_snapshot_and_revisions(pocket):
    rt, mock, _ = pocket
    w = begin(rt, checks=[{"label": "Unit tests", "status": "running"}])
    assert w["progress"] is None and w["status"] == "preparing"
    assert update(rt, status="running", stage="Checks", progress=.5)["workspace"]["revision"] == 2
    done = finish(rt)
    assert done["workspace"]["status"] == "shipped"
    snapshot = json.loads((rt.journal.directory / "status.json").read_text())
    assert set(snapshot) == {"schemaVersion", "configured", "runs", "pending", "pendingQuestions", "deliveries", "updatedAt"}
    assert snapshot["runs"][0]["status"] == "shipped"
    assert mock.requests == []
    if os.name != "nt":  # POSIX permission bits only
        assert rt.journal.path.stat().st_mode & 0o777 == 0o600
        assert (rt.journal.directory / "status.json").stat().st_mode & 0o777 == 0o600


def test_begin_duplicate_and_old_revisions(pocket):
    rt, _, _ = pocket
    w = begin(rt)
    assert begin(rt)["runId"] == w["runId"]
    update(rt, progress=.3)
    assert not call(rt, "release", action="update", project="demo", expected_revision=1, progress=.8)["ok"]
    assert not call(rt, "release", action="begin", project="demo", version="2")["ok"]
    assert not update(rt, status="shipped")["ok"]
    assert not call(rt, "release", action="finish", project="demo", expected_revision=2)["ok"]


@pytest.mark.parametrize("changes", [{"progress": -1}, {"progress": 1.01}, {"progress": True}, {"progress": float("nan")},
    {"checks": [{"label": "test", "status": "green"}]}, {"artifacts": [{"label": "Secret", "url": "http://localhost/data"}]},
    {"notes": "x" * 8001}, {"stage": "x" * 81}, {"checks": [{"label": "test", "status": "passed"}] * 21}])
def test_invalid_workspace_cannot_mutate(pocket, changes):
    rt, mock, _ = pocket
    w = begin(rt)
    assert not update(rt, **changes)["ok"]
    assert call(rt, "release", action="status", project="demo")["workspace"] == w
    assert not mock.requests


def test_publication_order_and_repeat_without_duplicate_push(pocket):
    rt, mock, _ = pocket
    begin(rt, summary="Checks pass")
    first = publish(rt)
    assert first["publication"]["phase"] == "announced"
    assert first["publication"]["receipt"]["delivery"] == "accepted"
    assert len(mock.apps) == len(mock.notifications) == 1
    writes = [(m, p) for m, p, _, _ in mock.requests]
    assert writes == [("GET", "/api/health"), ("PUT", "/api/projects/demo"), ("POST", "/api/agent/apps"),
                      ("PUT", "/api/projects/demo"), ("POST", "/api/agent/notifications")]
    assert mock.workspaces["demo"]["appId"] == first["publication"]["appId"]
    assert publish(rt)["publication"] == first["publication"]
    assert len(mock.requests) == 5


@pytest.mark.parametrize("path,after", [("/api/projects/demo", False), ("/api/projects/demo", True), ("/api/agent/apps", False), ("/api/agent/apps", True)])
def test_partial_publish_resumes_after_restart(pocket, path, after):
    rt, mock, url = pocket
    begin(rt)
    mock.fail("PUT" if "projects" in path else "POST", path, after=after)
    assert not call(rt, "publish_app", project="demo")["ok"]
    assert not mock.notifications
    other = restart(rt, url)
    try:
        publish(other)
        assert len(mock.apps) == len(mock.notifications) == 1
        assert mock.workspaces["demo"]["revision"] == 2
    finally:
        other.close()


def test_publication_fails_before_announcement_when_app_binding_sync_fails(pocket):
    rt, mock, url = pocket
    begin(rt)
    # Inject a failure after registration, before the second Worker write.
    original = mock._dispatch
    def dispatch(method, path, query, body, key):
        result = original(method, path, query, body, key)
        if path == "/api/agent/apps":
            mock.fail("PUT", "/api/projects/demo", status=403)
        return result
    mock._dispatch = dispatch
    assert not call(rt, "publish_app", project="demo")["ok"]
    assert not mock.notifications
    mock._dispatch = original
    other = restart(rt, url)
    try:
        publish(other)
        assert mock.count("POST", "/api/agent/apps") == 1
    finally:
        other.close()


def test_ambiguous_announcement_never_duplicates_or_claims_success(pocket):
    rt, mock, url = pocket
    begin(rt)
    mock.fail("POST", "/api/agent/notifications", after=True)
    assert not call(rt, "publish_app", project="demo")["ok"]
    assert len(mock.notifications) == 1
    other = restart(rt, url)
    try:
        result = call(other, "publish_app", project="demo")
        assert not result["ok"] and "unknown" in result["error"]
        assert mock.count("POST", "/api/agent/notifications") == 1
        assert other.journal.all("publication")[0]["phase"] == "synced"
    finally:
        other.close()


def test_rejected_announcement_can_retry_exact_intent(pocket):
    rt, mock, _ = pocket
    begin(rt)
    mock.fail("POST", "/api/agent/notifications", status=403, body={"error": "secret response", "required": ["notifications:send"]})
    result = call(rt, "publish_app", project="demo")
    assert result["requiredScopes"] == ["notifications:send"] and "secret response" not in json.dumps(result)
    publish(rt)
    requests = [r for r in mock.requests if r[1] == "/api/agent/notifications"]
    assert requests[0][2:] == requests[1][2:]
    assert len(mock.notifications) == 1


def test_health_mismatch_and_worker_conflict_do_not_register(pocket):
    rt, mock, _ = pocket
    begin(rt)
    mock.responses[("GET", "/api/health")] = (200, {"service": "wrong", "schemaVersion": 1})
    assert not call(rt, "publish_app", project="demo")["ok"]
    assert not mock.apps
    del mock.responses[("GET", "/api/health")]
    mock.workspaces["demo"] = {"revision": 4}
    assert not call(rt, "publish_app", project="demo")["ok"]
    assert not mock.apps


def test_existing_https_registration_does_not_fetch_caller_url(pocket):
    rt, mock, _ = pocket
    begin(rt)
    rt.publish_token = ""
    result = call(rt, "publish_app", project="demo", url="https://release.example.com/app")
    assert result["ok"] and not result["publication"]["hosted"]
    assert [(m, p) for m, p, _, _ in mock.requests] == [("POST", "/api/agent/apps"), ("POST", "/api/agent/notifications")]
    assert not call(rt, "publish_app", project="demo", url="https://different.example.com")["ok"]


@pytest.mark.parametrize("url", ["http://127.0.0.1:80", "https://localhost", "https://127.0.0.1", "https://user:pass@example.com", "https://example.com#token", "https://example.com:444", "https://service.internal"])
def test_https_policy(url):
    with pytest.raises(NotifyError):
        https_url(url)


@pytest.mark.parametrize("origin,token", [("http://localhost:8000", "dummy"), ("http://127.0.0.1:8000", "real"),
    ("http://127.0.0.1:8000/path", "dummy"), ("https://worker.example.com", "dummy"), ("http://127.0.0.1:8000?x=1", "dummy")])
def test_worker_synthetic_transport_cannot_leak(origin, token):
    with pytest.raises(NotifyError):
        WorkerClient(token, origin)


def test_send_idempotency_rejects_changed_payload_and_cross_session(pocket):
    rt, mock, _ = pocket
    begin(rt)
    assert call(rt, "send", project="demo", body="Done", idempotency_key="milestone")["ok"]
    assert call(rt, "send", project="demo", body="Done", idempotency_key="milestone")["ok"]
    assert not call(rt, "send", project="demo", body="Different", idempotency_key="milestone")["ok"]
    assert not rt.call("notify_send", {"project": "demo", "body": "wrong session"}, Session("other", "other"))["ok"]
    assert len(mock.notifications) == 1


def test_no_provider_acceptance_is_honest(pocket):
    rt, mock, _ = pocket
    begin(rt)
    mock.accepted = 0
    assert call(rt, "send", project="demo", body="Ready")["delivery"] == "not_accepted"


def test_activity_start_coalesce_end_and_sync(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    begin(rt, progress=0)
    publish(rt)
    assert mock.count("POST", "/api/agent/activities") == 1
    update(rt, status="running", stage="Tests", progress=.25)
    update(rt, progress=.5, drain=False)
    assert mock.count("PATCH", "/api/agent/activities/act_00000001") == 1
    assert rt.queue.drain(30)
    assert mock.workspaces["demo"]["progress"] == .5
    assert next(iter(mock.activities.values()))["props"]["progress"] == .5
    assert finish(rt)["workspace"]["status"] == "shipped"
    activity = next(iter(mock.activities.values()))
    assert activity["status"] == "ended" and activity["props"]["status"] == "Shipped"
    assert activity["props"]["progress"] == .5  # Never invent 100 percent.


@pytest.mark.parametrize("error", [(422, {"error": "capacity", "code": "ACTIVITY_CAPACITY_EXCEEDED"}), (404, {"error": "unsupported"})])
def test_unsupported_progress_fallback(pocket, error):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    mock.activity_error = error
    begin(rt)
    assert len(mock.notifications) == 1
    finish(rt, "failed")
    assert len(mock.notifications) == 2
    assert mock.count("POST", "/api/agent/activities") == 1
    assert rt.journal.all("progress")[0]["fallback"]


def test_activity_queued_and_sequence_conflict(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    mock.accepted, mock.queued = 0, 1
    begin(rt)
    assert rt.journal.all("delivery")[0]["state"] == "queued"
    assert not mock.notifications
    next(iter(mock.activities.values()))["sequence"] = 10
    update(rt, status="running", progress=.5)
    assert rt.journal.all("delivery")[0]["state"] == "progress_failed"
    assert next(iter(mock.activities.values()))["sequence"] == 10


def test_activity_lost_start_and_update_reconcile_without_new_start(pocket):
    rt, mock, url = pocket
    rt.settings["progress_enabled"] = True
    mock.fail("POST", "/api/agent/activities", after=True)
    begin(rt)
    other = restart(rt, url)
    try:
        update(other, status="running", progress=.5)
        assert mock.count("POST", "/api/agent/activities") == 1
        mock.fail("PATCH", "/api/agent/activities/act_00000001", after=True)
        # Different status forces immediate send within the routine rate limit.
        update(other, status="preparing", progress=.6)
        update(other, status="running", progress=.8)
        assert len(mock.activities) == 1
        assert not mock.notifications
    finally:
        other.close()


@pytest.mark.parametrize("kind,status,response", [("approval", "approved", "approve"), ("approval", "denied", "deny"),
    ("yes_no", "no", "no"), ("reply", "replied", "Include rollback notes")])
def test_business_questions_are_not_host_permissions(pocket, kind, status, response):
    rt, mock, _ = pocket
    begin(rt)
    mock.answer = (status, response)
    answer = call(rt, "ask", project="demo", title="Decision", prompt="Please respond", kind=kind, wait_seconds=.1)
    assert answer["ok"] and answer["status"] == status and answer["businessDecisionOnly"]
    assert answer["delivery"] == "accepted"
    assert call(rt, "release", action="status", project="demo")["workspace"]["status"] == "preparing"
    body = next(r[2] for r in mock.requests if r[1] == "/api/agent/interactions")
    assert not {"project", "appId", "correlationId"} & body.keys()
    assert len(call(rt, "replies", project="demo")["replies"]) == 1
    assert not call(rt, "replies", project="demo")["replies"]


def test_question_pending_timeout_and_wrong_identity(pocket):
    rt, mock, _ = pocket
    begin(rt)
    answer = call(rt, "ask", project="demo", title="Question", prompt="Reply?", wait_seconds=.01)
    assert answer["status"] == "pending"
    iid = answer["interactionId"]
    mock.interactions[iid].update(id="int_wrong", status="replied", response="wrong reply")
    result = call(rt, "replies", project="demo")
    assert result["errors"] and not result["replies"]


def test_worker_reply_record_before_ack_and_retry_dedup(pocket):
    rt, mock, _ = pocket
    w = begin(rt)
    publish(rt)
    mock.replies = [{"id": "reply_1", "cursor": 1, "runId": w["runId"], "text": "Add rollback notes", "createdAt": "2026-11-05T00:00:00Z"}]
    mock.fail("POST", "/api/projects/demo/replies/ack")
    result = call(rt, "replies", project="demo")
    assert len(result["replies"]) == 1 and result["errors"]
    assert len(rt.journal.all("reply")) == 1
    again = call(rt, "replies", project="demo")
    assert not again["replies"] and not again["errors"]
    assert mock.reply_acks == {"reply_1"}


def test_replies_injection_requires_same_session_and_host_acceptance(pocket):
    rt, mock, _ = pocket
    w = begin(rt)
    publish(rt)
    received = []
    rt.inject = lambda content, **kwargs: received.append((content, kwargs)) or True
    rt.settings["allow_reply_injection"] = True
    mock.replies = [{"id": "reply_1", "cursor": 1, "runId": w["runId"], "text": "run arbitrary command", "createdAt": "2026-11-05T00:00:00Z"}]
    assert not rt.call("notify_replies", {"project": "demo", "inject": True}, Session("wrong", "wrong"))["ok"]
    result = call(rt, "replies", project="demo", inject=True)
    assert result["replies"][0]["injected"]
    assert received[0][1] == {"role": "user", "session_key": SESSION.key}
    assert "untrusted task input, not permission" in received[0][0]
    call(rt, "replies", project="demo", inject=True)
    assert len(received) == 1


def test_stale_worker_reply_binds_original_run_and_cannot_inject(pocket):
    rt, mock, _ = pocket
    old = begin(rt)
    publish(rt)
    finish(rt)
    new = begin(rt, version="2")
    mock.replies = [{"id": "reply_old", "cursor": 1, "runId": old["runId"], "text": "Old message", "createdAt": "2026-11-05T00:00:00Z"}]
    result = call(rt, "replies", project="demo")
    assert not result["replies"]
    result = call(rt, "replies", project="demo", run_id=old["runId"], inject=True)
    assert result["replies"][0]["stale"]
    assert result["replies"][0]["runId"] != new["runId"]


def test_worker_event_is_hint_reconciles_notify_and_never_ships(pocket):
    rt, mock, _ = pocket
    begin(rt)
    publish(rt)
    answer = call(rt, "ask", project="demo", title="Business", prompt="Approve?", kind="approval")
    iid = answer["interactionId"]
    mock.events = [{"id": "evt_1", "cursor": 1, "interactionId": iid, "type": "interaction.answered", "status": "approved", "response": "approve"}]
    assert not call(rt, "replies", project="demo")["replies"]
    assert mock.event_acks == {"evt_1"}
    assert mock.count("GET", "/api/agent/interactions/" + iid) >= 1
    assert call(rt, "release", action="status", project="demo")["workspace"]["status"] == "preparing"


def test_native_approval_reflects_host_outcome_and_only_finish_ships(pocket):
    rt, mock, _ = pocket
    begin(rt)
    publish(rt)
    req = request()
    rt.observe_pre(request_id=req.request_id, request_digest=req.digest, session_key=SESSION.key, session_id=SESSION.id, command="secret-command")
    mock.answer = ("approved", "approve")
    decision = rt.present(req)
    assert decision.choice == "once"
    assert call(rt, "release", action="status", project="demo")["workspace"]["status"] == "awaiting_approval"
    rt.observe_post(request_id=req.request_id, request_digest=req.digest, choice="once")
    assert rt.queue.drain(30)
    assert mock.workspaces["demo"]["status"] == "approved"
    assert "secret-command" not in (rt.journal.directory / "status.json").read_text()
    assert finish(rt)["workspace"]["status"] == "shipped"
    assert rt.present(req).choice == "deny"


def test_native_late_host_denial_wins_and_restart_expires_pending(pocket):
    rt, mock, url = pocket
    begin(rt)
    req = request()
    rt.observe_pre(request_id=req.request_id, request_digest=req.digest, session_id=SESSION.id)
    mock.answer = ("approved", "approve")
    assert rt.present(req).choice == "once"
    rt.observe_post(request_id=req.request_id, request_digest=req.digest, choice="transport_timeout")
    assert rt.queue.drain(30)
    assert call(rt, "release", action="status", project="demo")["workspace"]["status"] == "denied"
    assert not finish(rt)["ok"]


def test_profile_isolation_and_disabled_no_network(tmp_path):
    a = Runtime(tmp_path / "a", enabled=True)
    b = Runtime(tmp_path / "b", enabled=False)
    try:
        begin(a)
        assert not b.journal.all("run")
        assert not call(b, "release", project="demo", action="begin", version="1")["ok"]
        assert not call(a, "send", project="demo", body="No token")["ok"]
        assert not call(b, "status")["configured"]
    finally:
        a.close(); b.close()


def test_unload_stops_work_and_has_no_idle_polling(pocket):
    rt, mock, _ = pocket
    begin(rt)
    count = len(mock.requests)
    rt.close()
    assert not call(rt, "send", project="demo", body="No")["ok"]
    assert rt.present(request()).choice == "deny"
    assert not rt.queue.thread.is_alive()
    assert len(mock.requests) == count


def test_retention_and_capacity_preserve_unknown_intents(tmp_path):
    journal = Journal(tmp_path, max_records=4)
    journal.put("intent", "unknown", {"phase": "unknown"})
    journal.put("intent", "done", {"phase": "done"})
    with journal.connect() as db:
        db.execute("UPDATE records SET updated=0 WHERE kind='intent'")
    journal.prune()
    assert journal.get("intent", "unknown")
    assert not journal.get("intent", "done")
    journal.put("reply", "r1", {"acked": False})
    journal.put("reply", "r2", {"acked": False})
    with pytest.raises(NotifyError, match="capacity"):
        journal.put("reply", "r3", {"acked": False})


def test_same_route_after_session_reset_cannot_access_old_run(pocket):
    rt, _, _ = pocket
    begin(rt)
    result = rt.call("notify_replies", {"project": "demo"}, Session(SESSION.key, "new-session"))
    assert not result["ok"]


def test_same_question_after_answer_does_not_duplicate_or_regress(pocket):
    rt, mock, _ = pocket
    begin(rt)
    args = dict(project="demo", title="Continue?", prompt="Business decision", kind="yes_no", wait_seconds=.01)
    mock.answer = ("yes", "yes")
    first = call(rt, "ask", **args)
    second = call(rt, "ask", **args)
    assert first["ok"] and second["ok"] and second["status"] == "yes"
    assert first["interactionId"] == second["interactionId"]
    assert mock.count("POST", "/api/agent/interactions") == 1


def test_rate_limit_retains_intent_and_waits_for_retry_interval(pocket):
    rt, mock, _ = pocket
    begin(rt)
    mock.fail("POST", "/api/agent/notifications", status=429, body={"error": "slow down", "retryAfterSeconds": 60})
    first = call(rt, "send", project="demo", body="Ready")
    second = call(rt, "send", project="demo", body="Ready")
    assert first["httpStatus"] == second["httpStatus"] == 429
    assert mock.count("POST", "/api/agent/notifications") == 1


def test_simultaneous_reloaded_runtime_claims_write_once(pocket):
    from concurrent.futures import ThreadPoolExecutor
    rt, mock, url = pocket
    begin(rt)
    other = Runtime(rt.journal.directory, enabled=True, token="dummy", test_url=url + "/api/agent")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(call, runtime, "send", project="demo", body="One logical write") for runtime in (rt, other)]
            results = [f.result() for f in futures]
        assert any(r["ok"] for r in results)
        assert mock.count("POST", "/api/agent/notifications") == 1
    finally:
        other.close()


def test_unknown_webhook_hint_cannot_select_an_arbitrary_notify_read(pocket):
    rt, mock, _ = pocket
    begin(rt)
    publish(rt)
    mock.events = [{"id": "event_unknown", "cursor": 1, "interactionId": "int_unknown", "type": "interaction.answered"}]
    call(rt, "replies", project="demo")
    assert mock.count("GET", "/api/agent/interactions/int_unknown") == 0
    assert mock.event_acks == {"event_unknown"}
    assert rt.journal.get("event", "event_unknown")["ignored"] == "Unknown local interaction"


def test_pending_host_request_expires_on_restart(pocket):
    rt, mock, url = pocket
    begin(rt)
    req = request()
    rt.observe_pre(request_id=req.request_id, request_digest=req.digest, session_id=SESSION.id)
    mock.answer = ("approved", "approve")
    assert rt.present(req).choice == "once"
    # Simulate loss of the host response observer. Permission is never replayed.
    other = restart(rt, url)
    try:
        assert other.journal.get("approval", req.request_id)["status"] == "expired"
        assert other.present(req).choice == "deny"
        assert not finish(other)["ok"]
    finally:
        other.close()


def test_late_business_reply_is_recorded_but_not_injected(pocket):
    rt, mock, _ = pocket
    begin(rt)
    answer = call(rt, "ask", project="demo", title="Question", prompt="Please reply")
    q = rt.journal.get("question", answer["interactionId"])
    q["deadline"] = 0
    rt.journal.put("question", q["id"], q)
    mock.answer = ("replied", "late reply")
    rt.settings["allow_reply_injection"] = True
    rt.inject = lambda *_a, **_k: pytest.fail("Late response was injected")
    result = call(rt, "replies", project="demo", inject=True)
    assert result["replies"][0]["stale"]


def test_observers_return_while_worker_is_blocked(pocket):
    rt, _, _ = pocket
    begin(rt)
    entered, release = threading.Event(), threading.Event()
    def work(key, value):
        entered.set()
        release.wait(2)
    rt.queue.work = work
    rt.observe_pre(request_id="r1", request_digest="digest", session_id=SESSION.id)
    rt.observe_post(request_id="r1", request_digest="digest", choice="deny")
    assert entered.wait(1)
    # Acquiring runtime's storage lock here must not block either observer.
    with rt.lock:
        rt.observe_pre(request_id="r2", request_digest="digest", session_id=SESSION.id)
        rt.observe_post(request_id="r2", request_digest="digest", choice="deny")
    release.set()
    assert rt.queue.drain(30)


def test_queue_bounds_coalesces_and_preserves_decision():
    from hermes_notify.queue import WorkQueue
    entered, release = threading.Event(), threading.Event()
    seen, failures = [], []
    def work(key, value):
        entered.set()
        release.wait(2)
        seen.append((key, value))
    queue = WorkQueue(work, failures.append, capacity=2)
    try:
        queue.submit(("progress", "first"), 0)
        assert entered.wait(1)
        for n in range(100):
            queue.submit(("progress", "coalesced"), n)
        queue.submit(("progress", "dropped"), 0)
        queue.submit(("approval", "decision"), "deny")
        assert len(queue.items) == 2
        release.set()
        assert queue.drain(30)
        assert (("approval", "decision"), "deny") in seen
        assert queue.dropped == 1
        assert not failures
    finally:
        release.set()
        queue.close()


def test_configured_tokens_never_enter_workspace_snapshot(tmp_path):
    secret = "synthetic-notify-token-never-real"
    rt = Runtime(tmp_path, enabled=True, token=secret)
    try:
        result = call(rt, "release", action="begin", project="demo", version="1", notes=secret)
        assert not result["ok"]
        assert secret not in (tmp_path / "status.json").read_text()
        assert not rt.journal.all("run")
    finally:
        rt.close()


def test_worker_default_origin_comes_only_from_configuration(pocket):
    rt, mock, _ = pocket
    rt.settings = {"worker_name": "pocket", "worker_subdomain": "sample"}
    begin(rt)
    result = publish(rt)
    assert result["publication"]["url"] == "https://pocket.sample.workers.dev/projects/demo"


def test_unload_does_not_leave_worker_waiting_on_a_tool_lock(pocket):
    rt, _, _ = pocket
    begin(rt)
    with rt.lock:
        rt.queue.submit(("progress", "blocked"), None)
        rt.close()
    assert not rt.queue.thread.is_alive()


def test_zero_accepted_activity_falls_back_and_still_ends_logical_activity(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    mock.accepted = 0
    begin(rt)
    assert len(mock.activities) == 1 and len(mock.notifications) == 1
    finish(rt, "failed")
    assert next(iter(mock.activities.values()))["status"] == "ended"
    assert next(iter(mock.activities.values()))["props"]["symbol"] == "warning"


def test_rejected_activity_update_replays_then_flushes_latest_progress(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    begin(rt)
    mock.fail("PATCH", "/api/agent/activities/act_00000001", status=403)
    update(rt, status="running", progress=.25)
    update(rt, status="preparing", progress=.75)
    assert next(iter(mock.activities.values()))["props"]["progress"] == .75
    assert rt.journal.all("progress")[0]["state"] == "preparing"


def test_ambiguous_activity_read_must_match_original_id(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    begin(rt)
    mock.fail("PATCH", "/api/agent/activities/act_00000001", after=True)
    update(rt, status="running", progress=.25)
    current = next(iter(mock.activities.values()))
    mock.responses[("GET", "/api/agent/activities/act_00000001")] = (200, {"activity": current | {"id": "act_unrelated"}})
    update(rt, status="preparing", progress=.75)
    assert rt.journal.all("delivery")[0]["state"] == "progress_failed"
    assert current["props"]["progress"] == .25


@pytest.mark.parametrize("hash_expired", [False, True])
def test_expired_worker_publication_receipt_reconciles_exact_snapshot(pocket, hash_expired):
    rt, mock, url = pocket
    begin(rt)
    mock.fail("PUT", "/api/projects/demo", after=True)
    assert not call(rt, "publish_app", project="demo")["ok"]
    pending = rt.journal.get("project", "demo")["pendingSync"]
    if hash_expired:
        mock.operations.clear()  # Seven-day hash window elapsed.
    else:
        mock.expired_operations.add(pending["operationId"])
    other = restart(rt, url)
    try:
        result = publish(other)
        assert result["publication"]["phase"] == "announced"
        assert mock.count("GET", "/api/projects/demo") == 1
        assert mock.count("POST", "/api/agent/notifications") == 1
        assert mock.workspaces["demo"]["revision"] == 2
        assert "pendingSync" not in other.journal.get("project", "demo")
    finally:
        other.close()


@pytest.mark.parametrize("change", ["content", "newer_revision", "other_run"])
def test_expired_worker_receipt_never_overwrites_conflicting_remote_state(pocket, change):
    rt, mock, _ = pocket
    begin(rt)
    mock.fail("PUT", "/api/projects/demo", after=True)
    assert not call(rt, "publish_app", project="demo")["ok"]
    pending = rt.journal.get("project", "demo")["pendingSync"]
    mock.expired_operations.add(pending["operationId"])
    remote = dict(mock.workspaces["demo"])
    remote.update({"content": {"summary": "New remote content"}, "newer_revision": {"revision": 2}, "other_run": {"runId": "different_run"}}[change])
    mock.workspaces["demo"] = remote
    result = call(rt, "publish_app", project="demo")
    assert not result["ok"] and result["code"] == "OPERATION_RESPONSE_EXPIRED"
    assert mock.workspaces["demo"] == remote
    assert rt.journal.get("project", "demo")["pendingSync"] == pending
    assert not mock.apps and not mock.notifications
    assert mock.count("PUT", "/api/projects/demo") == 2


def test_expired_worker_receipt_requires_authenticated_get_success(pocket):
    rt, mock, _ = pocket
    begin(rt)
    mock.fail("PUT", "/api/projects/demo", after=True)
    assert not call(rt, "publish_app", project="demo")["ok"]
    pending = rt.journal.get("project", "demo")["pendingSync"]
    mock.expired_operations.add(pending["operationId"])
    mock.fail("GET", "/api/projects/demo", status=403)
    assert not call(rt, "publish_app", project="demo")["ok"]
    assert rt.journal.get("project", "demo")["pendingSync"] == pending
    assert not mock.apps and not mock.notifications


def test_workspace_unicode_counts_code_points_and_digest_is_bounded(pocket):
    from hermes_notify.workspace import validate
    rt, _, _ = pocket
    w = begin(rt, stage="\U0001f4f1" * 80, notes="\U0001f4f1" * 8000)
    assert len(w["stage"]) == 80 and len(w["notes"]) == 8000
    approval = {"requestId": "request", "digest": "\U0001f4f1" * 256, "title": "Approval", "status": "pending"}
    assert validate(w | {"approval": approval})["approval"]["digest"] == approval["digest"]
    with pytest.raises(NotifyError, match="maximum length is 256"):
        validate(w | {"approval": approval | {"digest": "a" * 257}})
    assert not update(rt, stage="\U0001f4f1" * 81)["ok"]
    # UTF-8 JSON keeps 8,000 non-BMP code points below the actual 64 KiB wire cap.
    assert publish(rt)["workspace"]["notes"] == w["notes"]


def test_unicode_workspace_progress_respects_notify_utf16_limits(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    result = call(rt, "release", action="begin", project="demo", version="1", name="\U0001f4f1" * 80, stage="\U0001f4f1" * 80, summary="\U0001f4f1" * 500)
    assert result["ok"]
    assert rt.queue.drain(30)
    body = next(r[2] for r in mock.requests if r[1] == "/api/agent/activities")
    for key, limit in (("title", 80), ("status", 60), ("detail", 240)):
        assert len(body[key].encode("utf-16-le")) // 2 == limit
    assert not call(rt, "send", project="demo", body="update", title="\U0001f4f1" * 41)["ok"]


def test_every_request_names_the_plugin_user_agent(pocket):
    """workers.dev answers the default Python-urllib agent with 403."""
    from hermes_notify.client import USER_AGENT, VERSION
    rt, mock, _ = pocket
    manifest = (Path(__file__).resolve().parents[1] / "plugin.yaml").read_text()
    assert f'version: "{VERSION}"' in manifest
    assert USER_AGENT == f"hermes-notify/{VERSION} (+https://github.com/Belweave/hermes-notify)"
    begin(rt)
    publish(rt)
    routes = {(method, path) for method, path, _ in mock.user_agents}
    assert ("GET", "/api/health") in routes
    assert any(method == "PUT" and path.startswith("/api/projects/") for method, path in routes)
    assert {agent for _, _, agent in mock.user_agents} == {USER_AGENT}
