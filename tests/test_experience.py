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

