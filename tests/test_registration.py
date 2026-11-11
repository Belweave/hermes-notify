import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from hermes_notify.tools import SCHEMAS
from scripts.mock_notify import PocketMock
from test_runtime import SESSION, begin, call, finish, publish, update

ROOT = Path(__file__).resolve().parents[1]


def load_plugin():
    name = "runtime_registration_test"
    spec = importlib.util.spec_from_file_location(name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_registered_api_shapes_and_manifest_match(tmp_path, monkeypatch):
    from agent import secret_scope
    from gateway.session_context import scoped_session_key
    from ruamel.yaml import YAML
    from hermes_cli.plugins import PluginContext
    import inspect

    manifest = YAML(typ="safe").load((ROOT / "plugin.yaml").read_text())
    registered, hooks, transports, cleanup, skills = {}, {}, {}, [], []
    def register_tool(**kwargs):
        inspect.signature(PluginContext.register_tool).bind(None, **kwargs)
        registered[kwargs["name"]] = kwargs
    ctx = SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path), get_config=lambda k, d: d,
                          register_tool=register_tool, register_hook=lambda n, fn: hooks.update({n: fn}),
                          register_approval_transport=lambda n, fn: transports.update({n: fn}), on_unload=cleanup.append,
                          register_skill=lambda *args, **kwargs: skills.append((args, kwargs)))
    monkeypatch.setattr(secret_scope, "get_secret", lambda *_: pytest.fail("Disabled plugin resolved a secret"))
    load_plugin().register(ctx)
    try:
        assert set(registered) == set(manifest["provides_tools"])
        assert set(hooks) == set(manifest["provides_hooks"])
        catalog = YAML(typ="safe").load((ROOT / "plugin-catalog/hermes-notify.yaml").read_text())
        capabilities = catalog["capabilities"]
        assert set(capabilities) == {"provides_tools", "provides_hooks", "provides_middleware", "requires_env"}
        assert set(capabilities["provides_tools"]) == set(registered)
        assert set(capabilities["provides_hooks"]) == set(hooks)
        assert capabilities["provides_middleware"] == manifest.get("provides_middleware", []) == []
        assert capabilities["requires_env"] == [e if isinstance(e, str) else e["name"] for e in manifest["requires_env"]]
        assert catalog["name"] == manifest["name"] and catalog["version"] == manifest["version"]
        assert set(transports) == {"notify"}
        assert skills[0][0][0] == "notify-release-workspace"
        assert Path(skills[0][0][1]).is_file()
        for tool in registered.values():
            Draft202012Validator.check_schema(tool["schema"]["parameters"])
        with scoped_session_key(SESSION.key):
            result = json.loads(registered["notify_status"]["handler"]({}, session_id=SESSION.id))
        assert not result["configured"]
    finally:
        for stop in cleanup:
            stop()


def test_enabled_registration_captures_both_secrets_and_caller_context(tmp_path, monkeypatch):
    from agent import secret_scope
    from gateway.session_context import scoped_session_key
    registered, cleanup, reads = {}, [], []
    def secret(name, default):
        reads.append(name)
        return "dummy"
    monkeypatch.setattr(secret_scope, "get_secret", secret)
    with PocketMock().serve() as url:
        monkeypatch.setenv("HERMES_NOTIFY_TEST_URL", url + "/api/agent")
        monkeypatch.setenv("HERMES_NOTIFY_TEST_WORKER_URL", url)
        ctx = SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path),
              get_config=lambda k, d: {"enabled": True, "publisher_origin": "https://pocket.example.com"}.get(k, d),
              register_tool=lambda **kw: registered.update({kw["name"]: kw}), register_hook=lambda *_: None,
              register_approval_transport=lambda *_: None, on_unload=cleanup.append)
        load_plugin().register(ctx)
        try:
            assert reads == ["NOTIFY_API_TOKEN", "HERMES_NOTIFY_PUBLISH_TOKEN"]
            # Tool calls re-resolve in the caller's own context, so a key saved after load is
            # picked up; they read only the declared secrets.
            reads.clear()
            with scoped_session_key(SESSION.key):
                result = json.loads(registered["notify_release"]["handler"]({"action": "begin", "project": "test", "version": "1"}, session_id=SESSION.id))
                assert result["ok"]
                result = json.loads(registered["notify_publish_app"]["handler"]({"project": "test"}, session_id=SESSION.id))
                assert result["ok"]
                invalid = json.loads(registered["notify_publish_app"]["handler"]({"project": "test", "publisher": "https://bad.example.com"}, session_id=SESSION.id))
                assert not invalid["ok"]
            with scoped_session_key("other"):
                result = json.loads(registered["notify_send"]["handler"]({"project": "test", "body": "Wrong"}, session_id="other"))
                assert not result["ok"]
            assert reads and set(reads) == {"NOTIFY_API_TOKEN", "HERMES_NOTIFY_PUBLISH_TOKEN"}
        finally:
            for stop in cleanup:
                stop()


def test_catalog_context_registers_all_without_storage_or_secret_reads(monkeypatch):
    from agent import secret_scope
    tools, hooks = [], []
    monkeypatch.setattr(secret_scope, "get_secret", lambda *_: pytest.fail("Catalog read a secret"))
    ctx = SimpleNamespace(get_config=lambda k, d: d, register_tool=lambda **kw: tools.append(kw),
                          register_hook=lambda *a: hooks.append(a), register_approval_transport=lambda *a: None,
                          on_unload=lambda fn: None)
    load_plugin().register(ctx)
    assert len(tools) == 6 and len(hooks) == 2


def test_all_notify_runtime_write_shapes_match_saved_openapi(pocket):
    rt, mock, _ = pocket
    rt.settings["progress_enabled"] = True
    begin(rt, progress=0)
    publish(rt)
    update(rt, status="running", progress=.5)
    call(rt, "send", project="demo", body="A rich update", title="Update", summary="Status", body_format="markdown")
    call(rt, "ask", project="demo", title="Question", prompt="Please reply")
    finish(rt)
    contract = json.loads((ROOT / "tests/fixtures/notify-runtime-contract.json").read_text())["paths"]
    checked = set()
    for method, path, body, key in mock.requests:
        if not body or not path.startswith("/api/agent"):
            continue
        path = path.removeprefix("/api/agent")
        if path.startswith("/activities/"):
            path = "/activities/{identifier}/end" if path.endswith("/end") else "/activities/{identifier}"
        operation = contract[path][method.lower()]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        Draft202012Validator(schema).validate(body)
        assert not set(body) - set(schema["properties"])
        checked.add((method, path))
    assert len(checked) == 6


def test_real_hermes_loader_dispatches_six_tools_and_unloads():
    import subprocess
    done = subprocess.run([sys.executable, str(ROOT / "tests/loader_runtime_probe.py")],
                          cwd=ROOT, capture_output=True, text=True, timeout=180, check=True)  # cold Hermes import is slow on CI runners
    assert json.loads(done.stdout) == {"registered": 6, "dispatched": 6, "unloaded": True}


def test_calling_session_uses_documented_gateway_accessor(monkeypatch):
    from gateway import session_context
    from hermes_notify.tools import calling_session
    reads = []
    def get_session_env(name, default):
        reads.append((name, default))
        return "public-gateway-route"
    monkeypatch.setattr(session_context, "get_session_env", get_session_env)
    session = calling_session({"session_id": "host-session"})
    assert session.key == "public-gateway-route" and session.id == "host-session"
    assert reads == [("HERMES_SESSION_KEY", "")]


def test_setup_after_load_works_without_restart(tmp_path, monkeypatch):
    """Regression (0.2.1): a gateway/TUI that loaded the plugin before `hermes notify setup`
    stayed "not set up" because enabled and the key were read once at load."""
    from agent import secret_scope
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("NOTIFY_API_TOKEN", raising=False)
    config, registered, cleanup = {"enabled": False}, {}, []
    with PocketMock().serve() as url:
        monkeypatch.setenv("HERMES_NOTIFY_TEST_URL", url + "/api/agent")
        ctx = SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path / "data"),
                              get_config=lambda k, d=None: config.get(k, d),
                              register_tool=lambda **kw: registered.update({kw["name"]: kw}), register_hook=lambda *_: None,
                              register_approval_transport=lambda *_: None, on_unload=cleanup.append)
        load_plugin().register(ctx)
        try:
            send = registered["notify_send"]["handler"]
            before = json.loads(send({"body": "hi"}, session_id="s1"))
            assert not before["ok"] and "hermes notify setup" in before["error"]
            # What `hermes notify setup` does from another process: save the key, turn it on.
            (home / ".env").write_text("NOTIFY_API_TOKEN=dummy\n")
            secret_scope.invalidate_env_file_cache(home / ".env")
            config["enabled"] = True
            after = json.loads(send({"body": "hi"}, session_id="s1"))
            assert after["ok"], after
            status = json.loads(registered["notify_status"]["handler"]({}, session_id="s1"))
            assert status["configured"] and not [d for d in status["deliveries"] if d["state"] == "not_configured"]
        finally:
            for stop in cleanup:
                stop()


def test_stale_loader_config_falls_back_to_profile_file(tmp_path, monkeypatch):
    """Regression (0.2.2): a context whose get_config kept its load-time view (enabled=False)
    left a long-running gateway "not set up" while config.yaml said the plugin was on."""
    from agent import secret_scope
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("NOTIFY_API_TOKEN", raising=False)
    registered, cleanup = {}, []
    with PocketMock().serve() as url:
        monkeypatch.setenv("HERMES_NOTIFY_TEST_URL", url + "/api/agent")
        ctx = SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path / "data"),
                              get_config=lambda k, d=None: False if k == "enabled" else d,
                              register_tool=lambda **kw: registered.update({kw["name"]: kw}), register_hook=lambda *_: None,
                              register_approval_transport=lambda *_: None, on_unload=cleanup.append)
        load_plugin().register(ctx)
        try:
            (home / ".env").write_text("NOTIFY_API_TOKEN=dummy\n")
            secret_scope.invalidate_env_file_cache(home / ".env")
            (home / "config.yaml").write_text("plugins:\n  enabled: [hermes-notify]\n  entries:\n"
                                              "    hermes-notify:\n      settings:\n        enabled: true\n")
            after = json.loads(registered["notify_send"]["handler"]({"body": "hi"}, session_id="s1"))
            assert after["ok"], after
        finally:
            for stop in cleanup:
                stop()


def test_refresh_failure_is_reported_not_swallowed(tmp_path, monkeypatch):
    registered, cleanup = {}, []
    state = {"fail": False}

    def get_config(key, default=None):
        if state["fail"]:
            raise LookupError("boom")
        return default
    ctx = SimpleNamespace(state=SimpleNamespace(data_dir=tmp_path / "data"), get_config=get_config,
                          register_tool=lambda **kw: registered.update({kw["name"]: kw}), register_hook=lambda *_: None,
                          register_approval_transport=lambda *_: None, on_unload=cleanup.append)
    load_plugin().register(ctx)
    try:
        state["fail"] = True
        status = json.loads(registered["notify_status"]["handler"]({}, session_id="s1"))
        assert status["lastConfigError"] == "LookupError" and "boom" not in json.dumps(status)
    finally:
        for stop in cleanup:
            stop()
