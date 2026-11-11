import json
import socket
import time
import urllib.request

from hermes_notify.inbound import PATH, sign, verify
from hermes_notify.runtime import Runtime, Session
from scripts.mock_notify import PocketMock


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(port, body, signature):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{PATH}", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "X-Notify-Signature": signature})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_signature_scheme_matches_notify():
    body = b'{"type":"interaction.answered"}'
    header = sign("whsec", body, timestamp=1791633600)
    assert verify("whsec", header, body, now=1791633600)
    assert not verify("other", header, body, now=1791633600)
    assert not verify("whsec", header, body + b" ", now=1791633600)
    assert not verify("whsec", header, body, now=1791633600 + 301)  # replay window
    assert not verify("whsec", "forged", body)


def test_signed_answer_is_pushed_into_the_asking_session(tmp_path):
    mock, injected, port = PocketMock(), [], free_port()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", webhook_secret="whsec",
                     settings={"allow_reply_injection": True, "inbound_webhook_port": port},
                     test_url=url + "/api/agent", inject=lambda text, **kw: injected.append((text, kw)) or True)
        try:
            session = Session("key-1", "sid-1")
            asked = rt.call("notify_ask", {"title": "Deploy?", "prompt": "Ship it?", "kind": "yes_no"}, session)
            assert asked["ok"] and asked["mustPoll"], asked
            assert rt.call("notify_status", {}, session)["inboundWebhook"]["listening"]
            mock.answer = ("yes", "yes")
            body = json.dumps({"type": "interaction.answered", "interaction": {"id": asked["interactionId"]}}).encode()
            assert post(port, body, "t=1791633600,v1=" + "0" * 64) == 401
            assert post(port, body, sign("whsec", body)) == 202
            deadline = time.monotonic() + 10
            while not injected and time.monotonic() < deadline:
                time.sleep(0.05)
            assert injected and injected[0][1]["session_key"] == "key-1"
            assert '"text": "yes"' in injected[0][0] and "not permission" in injected[0][0]
            # Already delivered: notify_replies does not hand it out a second time.
            assert not rt.call("notify_replies", {}, session)["replies"]
            assert not rt.call("notify_status", {}, session)["pendingQuestions"]
        finally:
            rt.close()


def test_hint_without_injection_still_settles_for_notify_replies(tmp_path):
    mock, port = PocketMock(), free_port()
    with mock.serve() as url:
        rt = Runtime(tmp_path, enabled=True, token="dummy", webhook_secret="whsec",
                     settings={"inbound_webhook_port": port}, test_url=url + "/api/agent")
        try:
            asked = rt.call("notify_ask", {"prompt": "Ship it?", "kind": "yes_no"}, Session("", "a"))
            mock.answer = ("no", "no")
            body = json.dumps({"type": "interaction.answered", "interaction": {"id": asked["interactionId"]}}).encode()
            assert post(port, body, sign("whsec", body)) == 202
            deadline = time.monotonic() + 10
            while rt.journal.get("question", asked["interactionId"])["status"] == "pending" and time.monotonic() < deadline:
                time.sleep(0.05)
            assert rt.call("notify_replies", {}, Session("", "a"))["replies"][0]["text"] == "no"
        finally:
            rt.close()


def test_no_listener_without_port_or_secret(tmp_path):
    rt = Runtime(tmp_path, enabled=True, token="dummy", settings={"inbound_webhook_port": free_port()})
    try:
        assert not rt.inbound.listening
    finally:
        rt.close()
