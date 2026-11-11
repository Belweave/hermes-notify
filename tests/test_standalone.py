"""Simple notifications and questions work with only NOTIFY_API_TOKEN: no release run, Worker or project."""

from hermes_notify.runtime import Runtime, Session
from hermes_notify.workspace import normalize_project
from scripts.mock_notify import PocketMock

SESSION = Session("", "cli-session")


def test_send_and_ask_without_release_or_worker(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            sent = rt.call("notify_send", {"body": "Build finished"}, SESSION)
            assert sent["ok"], sent
            assert mock.count("POST", "/api/agent/notifications") == 1
            asked = rt.call("notify_ask", {"title": "Deploy?", "prompt": "Ship it?", "kind": "yes_no"}, SESSION)
            assert asked["ok"] and asked["status"] == "pending", asked
            mock.answer = ("yes", "yes")
            replies = rt.call("notify_replies", {}, SESSION)
            assert replies["ok"] and replies["replies"][0]["text"] == "yes", replies
            again = rt.call("notify_send", {"body": "Second update", "project": "hermes"}, SESSION)
            assert again["ok"], again
            assert len(rt.journal.all("run")) == 1
        finally:
            rt.close()


def test_updates_run_never_locks_a_project(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            assert rt.call("notify_send", {"body": "mine", "project": "shared"}, SESSION)["ok"]
            other = rt.call("notify_send", {"body": "theirs", "project": "shared"}, Session("", "other"))
            assert other["ok"], other
        finally:
            rt.close()


def test_real_release_of_another_session_still_blocks(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            assert rt.call("notify_release", {"action": "begin", "project": "shared", "version": "1.0"}, SESSION)["ok"]
            other = rt.call("notify_send", {"body": "theirs", "project": "shared"}, Session("", "other"))
            assert not other["ok"] and other["httpStatus"] == 409
            replies = rt.call("notify_replies", {"project": "shared"}, Session("", "other"))
            assert not replies["ok"]
        finally:
            rt.close()


def test_answer_is_readable_from_another_session(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            asked = rt.call("notify_ask", {"prompt": "Ship it?", "kind": "yes_no"}, SESSION)
            assert asked["ok"] and asked["mustPoll"] and "notify_replies" in asked["next"], asked
            status = rt.call("notify_status", {}, SESSION)
            assert status["pendingQuestions"][0]["interactionId"] == asked["interactionId"]
            assert status["lastConfigError"] is None
            mock.answer = ("yes", "yes")
            got = rt.call("notify_replies", {}, Session("", "later-session"))
            assert got["ok"] and got["replies"][0]["text"] == "yes", got
            assert got["replies"][0]["askedByAnotherSession"] and not got["replies"][0]["trustedAsInstruction"]
            assert not rt.call("notify_status", {}, SESSION)["pendingQuestions"]
        finally:
            rt.close()


def test_yes_no_answers_can_be_injected(tmp_path):
    mock = PocketMock()
    injected = []
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={"allow_reply_injection": True},
                     test_url=url + "/api/agent", inject=lambda text, **kw: injected.append((text, kw)) or True)
        try:
            session = Session("key-1", "sid-1")
            assert rt.call("notify_ask", {"prompt": "Ship it?", "kind": "yes_no"}, session)["ok"]
            mock.answer = ("yes", "yes")
            got = rt.call("notify_replies", {"inject": True}, session)
            assert got["replies"][0]["injected"] is True, got
            assert len(injected) == 1 and injected[0][1]["session_key"] == "key-1"
        finally:
            rt.close()


def test_expired_questions_are_swept(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            asked = rt.call("notify_ask", {"prompt": "Ship it?", "kind": "yes_no"}, SESSION)
            q = rt.journal.get("question", asked["interactionId"])
            q["deadline"] = 0
            rt.journal.put("question", q["id"], q)
            status = rt.call("notify_status", {}, SESSION)
            assert not status["pendingQuestions"]
            assert rt.journal.get("question", q["id"])["status"] == "expired"
        finally:
            rt.close()


def test_close_never_raises_when_storage_is_gone(tmp_path):
    import shutil
    rt = Runtime(tmp_path / "data", enabled=False, settings={})
    shutil.rmtree(tmp_path / "data")
    rt.close()


def test_not_set_up_message_is_actionable(tmp_path):
    rt = Runtime(tmp_path, enabled=False, settings={})
    try:
        out = rt.call("notify_send", {"body": "x"}, SESSION)
        assert not out["ok"] and "restart Hermes" in out["error"] and "new session" not in out["error"]
    finally:
        rt.close()


def test_project_names_are_normalized():
    assert normalize_project("notify_send", {})["project"] == "hermes"
    assert normalize_project("notify_send", {"project": "My App!"})["project"] == "my-app"
    assert normalize_project("notify_status", {}) == {}


def test_real_release_replaces_own_updates_run(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            assert rt.call("notify_send", {"body": "hi", "project": "demo"}, SESSION)["ok"]
            begun = rt.call("notify_release", {"action": "begin", "project": "demo", "version": "2.0"}, SESSION)
            assert begun["ok"] and begun["workspace"]["version"] == "2.0", begun
            assert rt.call("notify_send", {"body": "on the release", "project": "demo"}, SESSION)["ok"]
            assert rt.journal.get("project", "demo")["runId"] == begun["workspace"]["runId"]
        finally:
            rt.close()
