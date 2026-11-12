"""The Hermes x Notify story: idempotency, question lifecycle, job progress and interruptions."""

import json
import time

from hermes_notify.runtime import Session

S = Session("route_x", "session_x")


def ask(rt, **args):
    return rt.call("notify_ask", {"prompt": "Agent Hermes: deploy build 142 to production? Deny keeps build 141.",
                                  "kind": "approval", **args}, S)


def age(rt, seconds):
    """Pretend every retry-window record was written `seconds` ago."""
    with rt.journal.connect() as db:
        rows = db.execute("SELECT key, body FROM records WHERE kind='recent'").fetchall()
    for key, raw in rows:
        value = json.loads(raw)
        value["at"] -= seconds
        rt.journal.put("recent", key, value)


def test_yesterdays_approval_is_never_returned_for_the_same_question(pocket):
    rt, mock, _ = pocket
    mock.answer = ("approved", "approve")
    first = ask(rt, wait_seconds=.1)
    assert first["status"] == "approved" and first["proceed"]
    q = rt.journal.get("question", first["interactionId"])
    q["deadline"] = time.time() - 1
    rt.journal.put("question", q["id"], q)
    mock.answer = None
    again = ask(rt, wait_seconds=.1)
    assert again["status"] == "pending" and again["proceed"] is False and again["mustPoll"]
    assert again["interactionId"] != first["interactionId"]
    assert mock.count("POST", "/api/agent/interactions") == 2


def test_retried_ask_while_pending_resumes_without_a_second_copy(pocket):
    rt, mock, _ = pocket
    first = ask(rt)
    retry = ask(rt)
    assert retry["interactionId"] == first["interactionId"] and retry["resumed"]
    assert mock.count("POST", "/api/agent/interactions") == 1


def test_explicit_idempotency_key_is_the_same_event(pocket):
    rt, mock, _ = pocket
    mock.answer = ("denied", "deny")
    first = ask(rt, idempotency_key="deploy-142", wait_seconds=.1)
    again = ask(rt, idempotency_key="deploy-142", wait_seconds=.1)
    assert first["interactionId"] == again["interactionId"] and again["resumed"]
    assert again["status"] == "denied" and not again["proceed"]
    assert mock.count("POST", "/api/agent/interactions") == 1


def test_a_retried_send_is_deduplicated_but_a_later_identical_message_is_sent(pocket):
    rt, mock, _ = pocket
    first = rt.call("notify_send", {"body": "Backup finished"}, S)
    retry = rt.call("notify_send", {"body": "Backup finished"}, S)
    assert first["ok"] and retry["ok"] and retry["duplicate"] and "duplicate" not in first
    assert retry["notificationId"] == first["notificationId"]
    assert len(mock.notifications) == 1
    age(rt, 3600)
    later = rt.call("notify_send", {"body": "Backup finished"}, S)
    assert later["ok"] and "duplicate" not in later and later["notificationId"] != first["notificationId"]
    assert len(mock.notifications) == 2


def test_upgrade_from_content_keys_does_not_revive_an_old_answer(pocket):
    """0.2.x keyed questions by content alone. The first ask after upgrading must not reuse them."""
    rt, mock, _ = pocket
    mock.answer = ("yes", "yes")
    first = rt.call("notify_ask", {"prompt": "Rotate keys?", "kind": "yes_no", "wait_seconds": .1}, S)
    with rt.journal.connect() as db:
        db.execute("DELETE FROM records WHERE kind='recent'")
    q = rt.journal.get("question", first["interactionId"])
    q["deadline"] = time.time() - 1
    rt.journal.put("question", q["id"], q)
    mock.answer = None
    again = rt.call("notify_ask", {"prompt": "Rotate keys?", "kind": "yes_no"}, S)
    assert again["interactionId"] != first["interactionId"] and again["status"] == "pending"


def test_plain_send_never_starts_a_live_activity(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    assert rt.call("notify_send", {"body": "Tests passed"}, S)["ok"]
    assert rt.call("notify_ask", {"prompt": "Merge?", "kind": "yes_no"}, S)["ok"]
    assert rt.queue.drain(10)
    assert mock.count("POST", "/api/agent/activities") == 0
    assert not rt.call("notify_status", {}, S)["runs"]


def progress(rt, session=S, **args):
    return rt.call("notify_progress", args, session)


def activity(mock):
    assert len(mock.activities) == 1, mock.activities
    return next(iter(mock.activities.values()))


def test_job_progress_starts_once_updates_and_ends_truthfully(pocket):
    rt, mock, _ = pocket
    assert rt.settings.get("progress_enabled") is not True  # Jobs do not depend on the release setting.
    started = progress(rt, action="start", title="Test suite", status="Running tests", progress=0.1)
    assert started["ok"] and started["state"] == "running" and "next" in started
    retried = progress(rt, action="start", title="Test suite", status="Running tests")
    assert retried["resumed"] and retried["runId"] == started["runId"]
    assert rt.queue.drain(10)
    assert mock.count("POST", "/api/agent/activities") == 1
    start_body = next(r[2] for r in mock.requests if r[1] == "/api/agent/activities")
    assert start_body["title"] == "Test suite" and start_body["status"] == "Running tests"
    assert start_body["staleAfterSeconds"] == 1800 and start_body["style"] == "standard"
    rt.settings["progress_interval_seconds"] = 5
    for p in (0.5, 0.9):  # Within the interval: coalesced to the latest value.
        assert progress(rt, action="update", title="Test suite", status="Running tests", progress=p)["ok"]
    ended = progress(rt, action="end", title="Test suite", result="failed", status="2 tests failed", detail="checkout")
    assert ended["ok"] and ended["state"] == "failed" and ended["status"] == "2 tests failed"
    assert rt.queue.drain(10)
    a = activity(mock)
    assert a["status"] == "ended" and a["props"]["status"] == "2 tests failed"
    assert not progress(rt, action="update", title="Test suite", status="late")["ok"]
    # The same job name later is a new run with a new Live Activity, not a resurrected one.
    again = progress(rt, action="start", title="Test suite", status="Running tests")
    assert again["runId"] != started["runId"]
    assert rt.queue.drain(10)
    assert mock.count("POST", "/api/agent/activities") == 2


def test_job_end_without_result_or_start_without_status_is_refused(pocket):
    rt, _, _ = pocket
    assert progress(rt, action="start", title="Build")["httpStatus"] == 400
    assert progress(rt, action="start", title="Build", status="Compiling")["ok"]
    assert progress(rt, action="end", title="Build")["httpStatus"] == 400
    assert progress(rt, action="update", title="Other", status="x")["httpStatus"] == 404


def test_another_session_cannot_drive_or_end_my_job(pocket):
    rt, _, _ = pocket
    assert progress(rt, action="start", title="Migration", status="Copying rows")["ok"]
    other = Session("route_y", "session_y")
    assert progress(rt, other, action="end", title="Migration", result="succeeded")["httpStatus"] == 404


def test_ended_session_marks_its_jobs_stopped_on_the_phone(pocket):
    rt, mock, _ = pocket
    assert progress(rt, action="start", title="Nightly import", status="Importing")["ok"]
    other = Session("route_y", "session_y")
    assert progress(rt, other, action="start", title="Backup", status="Copying")["ok"]
    assert rt.queue.drain(10)
    assert rt.stop_session_jobs(session_id=S.id, label="Stopped: session ended") == 1
    ended = [a for a in mock.activities.values() if a["status"] == "ended"]
    assert len(ended) == 1 and ended[0]["props"]["status"] == "Stopped: session ended"
    assert rt.stop_session_jobs(session_id=S.id, label="Stopped: session ended") == 0


def test_job_on_a_phone_without_live_activities_falls_back_to_messages(pocket):
    rt, mock, _ = pocket
    mock.activity_error = (422, {"error": "unsupported", "code": "NO_CAPABLE_DEVICES"})
    assert progress(rt, action="start", title="Deploy", status="Uploading")["ok"]
    assert rt.queue.drain(10)
    assert progress(rt, action="end", title="Deploy", result="succeeded")["ok"]
    assert rt.queue.drain(10)
    bodies = [n["body"] for n in mock.notifications.values()]
    assert bodies == ["Uploading", "Done"]


def test_replies_resumes_a_bounded_wait_and_cancel_withdraws(pocket):
    rt, mock, _ = pocket
    asked = ask(rt)
    assert asked["status"] == "pending" and "notify_replies" in asked["next"]
    nothing = rt.call("notify_replies", {"wait_seconds": .2}, S)
    assert nothing["ok"] and not nothing["replies"] and nothing["pendingQuestions"]
    assert mock.count("GET", "/api/agent/interactions/" + asked["interactionId"] + "/wait") == 1
    mock.answer = ("approved", "approve")
    got = rt.call("notify_replies", {"wait_seconds": .2}, S)
    assert [(r["status"], r["proceed"]) for r in got["replies"]] == [("approved", True)]
    # Answered first: cancel keeps the answer and says so.
    kept = rt.call("notify_cancel", {"interaction_id": asked["interactionId"]}, S)
    assert kept["status"] == "approved" and "note" in kept
    mock.answer = None
    second = rt.call("notify_ask", {"prompt": "Hermes: also restart the workers? No leaves them running.", "kind": "yes_no"}, S)
    canceled = rt.call("notify_cancel", {"interaction_id": second["interactionId"]}, S)
    assert canceled["status"] == "canceled" and not canceled["proceed"]
    assert not rt.call("notify_status", {}, S)["pendingQuestions"]
    other = rt.call("notify_cancel", {"interaction_id": second["interactionId"]}, Session("route_y", "session_y"))
    assert other["httpStatus"] == 403


def test_a_wait_does_not_hold_the_lock_needed_by_approvals(pocket):
    import threading
    rt, mock, _ = pocket
    asked = ask(rt)
    entered = threading.Event()
    original = rt.api.wait

    def slow_wait(*a, **k):
        entered.set()
        time.sleep(1)
        return original(*a, **k)
    rt.api.wait = slow_wait
    worker = threading.Thread(target=rt.call, args=("notify_replies", {"wait_seconds": 1}, S))
    worker.start()
    assert entered.wait(5)
    started = time.monotonic()
    assert rt.lock.acquire(timeout=0.5)  # An approval or webhook hint can take the lock meanwhile.
    rt.lock.release()
    assert time.monotonic() - started < 0.5
    worker.join(10)
    assert asked["ok"]


def test_not_accepted_question_warns_not_to_wait(pocket):
    rt, mock, _ = pocket
    mock.accepted = 0
    asked = ask(rt)
    assert asked["delivery"] == "not_accepted" and "Do not wait" in asked["warning"]


def test_system_prompt_section_carries_the_four_rules():
    from hermes_notify.tools import PROMPT_SECTION, SCHEMAS
    assert len(PROMPT_SECTION) <= 4000
    for phrase in ("notify_ask, never notify_send", "proceed: true", "wait_seconds 25", "notify_cancel",
                   "who is asking", "Never put secrets", "notify_progress", "never permission"):
        assert phrase in PROMPT_SECTION, phrase
    ask_tool = next(s for s in SCHEMAS if s["name"] == "notify_ask")["description"]
    assert "proceed" in ask_tool and "stands alone" in ask_tool and "secrets" in ask_tool


def test_a_failed_wait_still_returns_the_question_it_asked(pocket):
    rt, mock, _ = pocket
    mock.fail("GET", "/api/agent/interactions/int_00000001/wait", status=503)
    asked = ask(rt, wait_seconds=1)
    assert asked["ok"] and asked["status"] == "pending" and asked["waitError"]["httpStatus"] == 503
    assert ask(rt)["resumed"] and mock.count("POST", "/api/agent/interactions") == 1
