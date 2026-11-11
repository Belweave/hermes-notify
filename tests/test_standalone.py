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


def test_other_session_cannot_reuse_project(tmp_path):
    mock = PocketMock()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", settings={}, test_url=url + "/api/agent")
        try:
            assert rt.call("notify_send", {"body": "mine", "project": "shared"}, SESSION)["ok"]
            other = rt.call("notify_send", {"body": "theirs", "project": "shared"}, Session("", "other"))
            assert not other["ok"] and other["httpStatus"] == 409
        finally:
            rt.close()


def test_project_names_are_normalized():
    assert normalize_project("notify_send", {})["project"] == "hermes"
    assert normalize_project("notify_send", {"project": "My App!"})["project"] == "my-app"
    assert normalize_project("notify_status", {}) == {}
