import json
import importlib.util
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from hermes_cli.approval_transport import ApprovalRequest, invoke_approval_transport
from hermes_notify.bridge import ApprovalBridge, TransportUnavailable
from hermes_notify.client import NotifyClient, NotifyError, TEST_TOKEN
from hermes_notify.ledger import Ledger
from hermes_notify.runtime import Runtime
from scripts.mock_notify import MockNotify

ROOT = Path(__file__).resolve().parents[1]


def request(**overrides):
    params = dict(command='print("approved")', description="Run this exact test script",
                  pattern_key="spike", pattern_keys=("spike",), session_key="spike",
                  surface="gateway", allow_session=True, allow_permanent=True, timeout_seconds=2)
    return ApprovalRequest.create(**(params | overrides))


class FakeNotify:
    def __init__(self, status="approved", response="approve", change=None):
        self.status, self.response, self.change = status, response, change or {}
        self.creates = 0
        self.waits = 0
        self.cancels = 0

    def create(self, body, key, timeout):
        self.creates += 1
        self.body, self.key = body, key
        self.interaction = dict(body, id="int_test", actionDigest="a" * 64, status="pending", response=None)
        return {"interaction": self.interaction, "accepted": 0}

    def wait(self, interaction_id, seconds, timeout):
        self.waits += 1
        return {"interaction": self.interaction | {"status": self.status, "response": self.response} | self.change,
                "timedOut": self.status == "pending"}

    def cancel(self, interaction_id, timeout):
        self.cancels += 1


@pytest.mark.parametrize(("status", "response", "expected"), [
    ("approved", "approve", "once"), ("denied", "deny", "deny"),
    ("expired", None, "deny"), ("canceled", None, "deny"), ("yes", "yes", "deny"),
    ("replied", "approve", "deny"), ("approved", None, "deny"), ("approved", "yes", "deny"),
    ("unexpected", "approve", "deny"),
])
def test_only_explicit_approval_grants_once(tmp_path, status, response, expected):
    api = FakeNotify(status, response)
    bridge = ApprovalBridge(api, Ledger(tmp_path / "db"))
    req = request()
    outcome = invoke_approval_transport(bridge.present, req, timeout_seconds=2)
    assert outcome.choice == expected
    assert api.creates == 1
    assert api.key == "hermes-" + req.request_id
    assert api.body["kind"] == "approval"


@pytest.mark.parametrize("change", [
    {"id": "int_another_request"}, {"actionDigest": "b" * 64}, {"kind": "reply"},
    {"prompt": "different action"}, {"title": "changed"}, {"presentation": "live_activity"},
])
def test_changed_interaction_fails_closed(tmp_path, change):
    bridge = ApprovalBridge(FakeNotify(change=change), Ledger(tmp_path / "db"))
    assert bridge.present(request()).choice == "deny"


def test_no_duplicate_after_consumption_or_reopening_ledger(tmp_path):
    api, req = FakeNotify(), request()
    path = tmp_path / "db"
    assert ApprovalBridge(api, Ledger(path)).present(req).choice == "once"
    assert ApprovalBridge(api, Ledger(path)).present(req).choice == "deny"
    assert api.creates == 1


def test_concurrent_requests_claim_exactly_once(tmp_path):
    ledger = Ledger(tmp_path / "db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ledger.claim("same", "digest"), range(12)))
    assert sum(results) == 1


def test_transport_error_does_not_retry_or_leak(tmp_path, caplog):
    class Unavailable(FakeNotify):
        def create(self, body, key, timeout):
            super().create(body, key, timeout)
            raise NotifyError("pretend-secret")
    api, req = Unavailable(), request()
    bridge = ApprovalBridge(api, Ledger(tmp_path / "db"))
    # Nothing reached the phone: raise so the host applies transport_fallback (terminal prompt
    # when the operator opted in, otherwise its own deny). The exception carries no details.
    with pytest.raises(TransportUnavailable) as raised:
        bridge.present(req)
    assert "pretend-secret" not in str(raised.value)
    # The request ID is claimed once; a retry of the same request never sends again.
    assert bridge.present(req).choice == "deny"
    assert api.creates == 1
    assert "pretend-secret" not in caplog.text


def test_host_falls_back_when_transport_is_unavailable(tmp_path):
    from hermes_cli.approval_transport import invoke_approval_transport
    rt = Runtime(tmp_path, enabled=True, token="", settings={})
    try:
        result = invoke_approval_transport(rt.present, request(), timeout_seconds=2)
        assert result.failure == "error" and result.choice == "deny"
    finally:
        rt.close()


def test_pending_timeout_never_approves_or_sends_again(tmp_path):
    api = FakeNotify("pending", None)
    bridge = ApprovalBridge(api, Ledger(tmp_path / "db"), timeout_seconds=0.8)
    assert bridge.present(request()).choice == "deny"
    assert api.creates == 1
    assert api.waits <= 3


def test_unload_during_wait_rejects_an_approved_response(tmp_path):
    stopped = threading.Event()
    class StopDuringWait(FakeNotify):
        def wait(self, *args):
            result = super().wait(*args)
            stopped.set()
            return result
    api = StopDuringWait()
    bridge = ApprovalBridge(api, Ledger(tmp_path / "db"), is_cancelled=stopped.is_set)
    assert bridge.present(request()).choice == "deny"
    assert api.cancels == 1


def test_action_digest_is_opaque_not_a_locally_invented_algorithm(tmp_path):
    class OpaqueDigest(FakeNotify):
        def create(self, *args):
            result = super().create(*args)
            self.interaction["actionDigest"] = "opaque-server-v2-digest"
            return result
    assert ApprovalBridge(OpaqueDigest(), Ledger(tmp_path / "db")).present(request()).choice == "once"


def test_late_transport_result_cannot_change_host_denial(tmp_path):
    released, finished = threading.Event(), threading.Event()
    class SlowNotify(FakeNotify):
        def wait(self, *args):
            assert released.wait(2)
            return super().wait(*args)
    bridge = ApprovalBridge(SlowNotify(), Ledger(tmp_path / "db"))
    def present(req):
        try:
            return bridge.present(req)
        finally:
            finished.set()
    result = invoke_approval_transport(present, request(), timeout_seconds=0.05)
    released.set()
    assert finished.wait(2)
    assert result.choice == "deny" and result.failure == "timeout"


@pytest.mark.parametrize("command", ["x" * 2100, "\U0001f4f1" * 1100])
def test_long_action_is_refused_without_truncation(tmp_path, command):
    api = FakeNotify()
    assert ApprovalBridge(api, Ledger(tmp_path / "db")).present(request(command=command)).choice == "deny"
    assert api.creates == 0


@pytest.mark.parametrize("url", ["https://evil.example/api/agent", "http://localhost:8080/api/agent",
    "http://127.0.0.1:8080/other", "http://user@127.0.0.1:8080/api/agent", "http://127.0.0.1:8080/api/agent?secret=yes"])
def test_test_transport_cannot_leak_tokens(url):
    with pytest.raises(NotifyError):
        NotifyClient(TEST_TOKEN, url)


def test_real_token_cannot_be_sent_to_mock():
    with pytest.raises(NotifyError):
        NotifyClient("pretend-real-token", "http://127.0.0.1:8080/api/agent")
    with pytest.raises(NotifyError):
        NotifyClient(TEST_TOKEN)


def test_plugin_captures_profile_secret_before_transport_worker(tmp_path, monkeypatch):
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    spec = importlib.util.spec_from_file_location("profile_test_notify", ROOT / "__init__.py",
                                                 submodule_search_locations=[str(ROOT)])
    plugin = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = plugin
    spec.loader.exec_module(plugin)
    transports, cleanup = {}, []
    ctx = SimpleNamespace(
        get_config=lambda key, default=None: {"enabled": True}.get(key, default),
        state=SimpleNamespace(data_dir=tmp_path),
        register_approval_transport=lambda name, callback: transports.update({name: callback}),
        on_unload=cleanup.append,
    )
    mock = MockNotify()
    with mock.serve() as url:
        monkeypatch.setenv("NOTIFY_API_TOKEN", "wrong-profile-token")
        monkeypatch.setenv("HERMES_NOTIFY_TEST_URL", url)
        scope = set_secret_scope({"NOTIFY_API_TOKEN": TEST_TOKEN})
        try:
            plugin.register(ctx)
        finally:
            reset_secret_scope(scope)
        # This worker has no secret scope; registration already captured the correct key.
        result = invoke_approval_transport(transports["notify"], request(), timeout_seconds=2)
        assert result.choice == "once"
        cleanup[0]()
        assert transports["notify"](request()).choice == "deny"


@pytest.mark.parametrize("answer", ["approve", "deny", "timeout", "disabled"])
def test_real_hermes_loader_http_gate_and_unload(answer):
    args = ["--disabled"] if answer == "disabled" else ["--answer", answer]
    done = subprocess.run([sys.executable, str(ROOT / "scripts/spike.py"), *args],
                          cwd=ROOT, capture_output=True, text=True, timeout=180, check=True)  # cold Hermes import is slow on CI runners
    report = json.loads(done.stdout)
    assert report["plugin_loaded"] and report["transport_unloaded"]
    assert report["hermes_approved"] == (answer == "approve")
    assert report["mock_pushes"] == (0 if answer == "disabled" else 1)
    assert not report["action_executed"]
