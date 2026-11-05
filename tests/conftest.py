import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("HERMES_SOURCE", ROOT / ".local/hermes-source"))
if not (SOURCE / "hermes_cli/plugins.py").is_file():
    raise RuntimeError("Run scripts/fetch_hermes.py before testing against real Hermes")
sys.path[:0] = [str(ROOT), str(SOURCE)]

# Install an isolated home before importing any Hermes code in test modules.
# No real credentials or the user's Hermes configuration are read by this suite.
import tempfile
_TEST_HOME = tempfile.TemporaryDirectory(prefix="pocket-test-home-")
os.environ["HERMES_HOME"] = _TEST_HOME.name
os.environ["NOTIFY_API_TOKEN"] = "dummy"
os.environ["HERMES_NOTIFY_PUBLISH_TOKEN"] = "dummy"
os.environ.pop("HERMES_NOTIFY_TEST_URL", None)
os.environ.pop("HERMES_NOTIFY_TEST_WORKER_URL", None)

import pytest


@pytest.fixture(autouse=True)
def isolated_secret_boundary(monkeypatch, tmp_path):
    from agent import secret_scope
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("NOTIFY_API_TOKEN", "dummy")
    monkeypatch.setenv("HERMES_NOTIFY_PUBLISH_TOKEN", "dummy")

    def synthetic_secret(name, default=None):
        if name not in ("NOTIFY_API_TOKEN", "HERMES_NOTIFY_PUBLISH_TOKEN"):
            return default
        scope = secret_scope.current_secret_scope()
        return scope.get(name, default) if scope is not None else default
    monkeypatch.setattr(secret_scope, "get_secret", synthetic_secret)

    import socket
    original_connect = socket.socket.connect
    def loopback_only(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] != "127.0.0.1":
            raise AssertionError("Tests may connect only to synthetic IPv4 loopback")
        return original_connect(sock, address)
    monkeypatch.setattr(socket.socket, "connect", loopback_only)

@pytest.fixture
def pocket(tmp_path):
    from hermes_notify.runtime import Runtime
    from scripts.mock_notify import PocketMock
    mock = PocketMock()
    with mock.serve() as url:
        runtime = Runtime(tmp_path, enabled=True, token="dummy", publish_token="dummy",
                          settings={"publisher_origin": "https://pocket.example.com"},
                          test_url=url + "/api/agent", test_worker_url=url)
        yield runtime, mock, url
        runtime.close()
