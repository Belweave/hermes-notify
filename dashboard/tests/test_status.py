"""Run with the pinned public Hermes source, never an installed user profile."""
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / ".local/hermes-source"
sys.path.insert(0, str(SOURCE))


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    # Loading this public storage module does not load configuration or profiles.
    spec = importlib.util.spec_from_file_location("notify_status_under_test", ROOT / "dashboard/plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    app.include_router(module.router, prefix="/api/plugins/hermes-notify")
    with TestClient(app) as client:
        yield module, client, tmp_path


def sample():
    return {
        "schemaVersion": 1, "configured": True,
        "runs": [{
            "schemaVersion": 1, "project": "demo", "runId": "run_1", "revision": 1,
            "name": "Release", "version": "1.0.0", "status": "running", "stage": "Checks",
            "summary": "One check passed.", "progress": 0.5,
            "checks": [{"label": "Tests", "status": "passed"}],
            "artifacts": [{"label": "Release notes", "url": "https://example.com/release"}],
            "notes": "Rollback notes", "updatedAt": "2026-11-05T01:00:00Z",
            "appId": "app_demo", "approval": None,
        }],
        "pending": [{"requestId": "req_demo", "title": "Release 1.0.0", "status": "pending"}],
        "deliveries": [{"project": "demo", "state": "accepted", "message": "Provider accepted."}],
        "updatedAt": "2026-11-05T01:00:00Z",
    }


def projected(value):
    """What the route returns for a snapshot: optional fields from newer runtimes get defaults."""
    import copy
    value = copy.deepcopy(value)
    for run in value["runs"]:
        run.setdefault("kind", "release")
    for delivery in value["deliveries"]:
        delivery.setdefault("at", None)
    value.setdefault("pendingQuestions", [])
    return value


def write(directory, payload):
    from hermes_cli.plugins_state import PluginState
    path = directory / "plugin-data" / PluginState("hermes-notify").data_dir.name / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return path


def test_missing_status_does_not_create_storage(api):
    _, client, directory = api
    response = client.get("/api/plugins/hermes-notify/status")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert not (directory / "plugin-data").exists()
    assert str(directory) not in response.text


def test_contract_read_only_and_extra_fields_are_not_exposed(api):
    _, client, directory = api
    value = sample()
    value["token"] = "synthetic-private-field"
    value["runs"][0]["sessionKey"] = "synthetic-session-key"
    value["runs"][0]["artifacts"][0]["transcript"] = "synthetic-transcript"
    path = write(directory, value)
    before = path.read_bytes(), path.stat().st_mtime_ns
    response = client.get("/api/plugins/hermes-notify/status")
    assert response.status_code == 200
    assert response.json() == projected(sample())
    assert response.headers["cache-control"] == "no-store"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    for verb in (client.post, client.put, client.delete, client.patch):
        assert verb("/api/plugins/hermes-notify/status").status_code == 405


def test_global_delivery_error_preserves_all_workspace_status(api):
    _, client, directory = api
    value = sample()
    value["deliveries"].append({"project": "", "state": "failed", "message": "Queued work needs an owning-session retry."})
    write(directory, value)
    response = client.get("/api/plugins/hermes-notify/status")
    assert response.status_code == 200
    assert response.json() == projected(value)
    value["deliveries"][-1]["project"] = "../another-profile"
    write(directory, value)
    assert client.get("/api/plugins/hermes-notify/status").status_code == 503


def test_runtime_global_diagnostic_preserves_desktop_status(api):
    from hermes_cli.plugins_state import PluginState
    from hermes_notify.runtime import Runtime, Session

    _, client, _ = api
    runtime = Runtime(PluginState("hermes-notify").data_dir, enabled=True, token="dummy")
    session = Session("synthetic-route", "synthetic-session")
    try:
        result = runtime.call("notify_release", {"action": "begin", "project": "demo", "version": "1"}, session)
        assert result["ok"] and runtime.queue.drain(5)
        before = client.get("/api/plugins/hermes-notify/status")
        assert before.status_code == 200
        # The producer deliberately uses an empty project for an invalid call.
        invalid = runtime.call("notify_release", {"action": "begin", "version": "2"}, session)
        assert not invalid["ok"]
        after = client.get("/api/plugins/hermes-notify/status")
        assert after.status_code == 200
        assert after.json()["runs"] == before.json()["runs"]
        assert any(row["project"] == "" and row["state"] == "failed" for row in after.json()["deliveries"])
    finally:
        runtime.close()


def test_profile_lookup_is_per_request_and_query_cannot_choose_path(api, monkeypatch, tmp_path):
    _, client, home = api
    write(home, sample())
    second = tmp_path / "second-profile"
    value = sample()
    value["runs"][0]["project"] = "other"
    write(second, value)
    assert client.get("/api/plugins/hermes-notify/status").json()["runs"][0]["project"] == "demo"
    monkeypatch.setenv("HERMES_HOME", str(second))
    result = client.get("/api/plugins/hermes-notify/status", params={"path": str(home / "status.json"), "profile": "default"})
    assert result.json()["runs"][0]["project"] == "other"
    monkeypatch.setenv("HERMES_HOME", str(home))
    assert client.get("/api/plugins/hermes-notify/status").json()["runs"][0]["project"] == "demo"


def test_request_context_scope_reaches_sync_handler(api, tmp_path):
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override
    _, client, home = api
    write(home, sample())
    second = tmp_path / "scoped-profile"
    value = sample()
    value["runs"][0]["project"] = "scoped"
    write(second, value)
    token = set_hermes_home_override(second)
    try:
        assert client.get("/api/plugins/hermes-notify/status").json()["runs"][0]["project"] == "scoped"
    finally:
        reset_hermes_home_override(token)
    assert client.get("/api/plugins/hermes-notify/status").json()["runs"][0]["project"] == "demo"


@pytest.mark.parametrize("change", [
    lambda v: v.update(schemaVersion=2),
    lambda v: v.update(configured="yes"),
    lambda v: v.update(runs=v["runs"] * 21),
    lambda v: v.update(pending=v["pending"] * 51),
    lambda v: v.update(deliveries=v["deliveries"] * 51),
    lambda v: v["runs"][0].update(project="../wrong"),
    lambda v: v["runs"][0].update(progress=True),
    lambda v: v["runs"][0].update(progress=float("nan")),
    lambda v: v["runs"][0].update(progress=1.1),
    lambda v: v["runs"][0].update(notes="x" * 8001),
    lambda v: v["runs"][0].update(revision=False),
    lambda v: v["runs"][0].update(status="success"),
    lambda v: v["runs"][0]["artifacts"][0].update(url="javascript:alert(1)"),
    lambda v: v["runs"][0]["artifacts"][0].update(url="https://synthetic:secret@example.com/"),
    lambda v: v["runs"][0]["artifacts"][0].update(url="https://example.com/\nsecret"),
])
def test_invalid_or_oversized_shapes_fail_closed(api, change):
    _, client, directory = api
    value = sample()
    change(value)
    write(directory, value)
    response = client.get("/api/plugins/hermes-notify/status")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert str(directory) not in response.text


@pytest.mark.parametrize("kind", ["bytes", "malformed", "symlink", "directory", "fifo", "storage-symlink"])
def test_bounded_regular_file_only(api, kind, tmp_path):
    module, client, directory = api
    path = write(directory, sample())
    if kind == "bytes":
        path.write_bytes(b" " * (module.MAX_BYTES + 1))
    elif kind == "malformed":
        path.write_text("{broken")
    elif kind == "symlink":
        path.unlink()
        target = tmp_path / "unrelated.json"
        target.write_text(json.dumps(sample()))
        path.symlink_to(target)
    elif kind == "directory":
        path.unlink()
        path.mkdir()
    elif kind == "fifo":
        path.unlink()
        os.mkfifo(path)
    else:
        actual = path.parent.with_name("elsewhere")
        path.parent.rename(actual)
        path.parent.symlink_to(actual, target_is_directory=True)
    assert client.get("/api/plugins/hermes-notify/status").status_code == 503


def test_unconfigured_snapshot_is_valid_and_still_read_only(api):
    _, client, directory = api
    value = sample()
    value.update(configured=False, runs=[], pending=[], deliveries=[])
    write(directory, value)
    assert client.get("/api/plugins/hermes-notify/status").json() == projected(value)


def test_pending_questions_job_kind_and_delivery_time_are_projected(api):
    module, client, directory = api
    payload = sample()
    payload["runs"][0]["kind"] = "job"
    payload["deliveries"][0]["at"] = "2026-11-12T10:00:00Z"
    payload["pendingQuestions"] = [{"interactionId": "int_1", "project": "demo", "kind": "yes_no",
                                    "title": "Restart workers?", "deadline": 1794477600.5, "extra": "dropped"}]
    write(directory, payload)
    body = client.get("/api/plugins/hermes-notify/status").json()
    assert body["runs"][0]["kind"] == "job"
    assert body["deliveries"][0]["at"] == "2026-11-12T10:00:00Z"
    assert body["pendingQuestions"] == [{"interactionId": "int_1", "project": "demo", "kind": "yes_no",
                                         "title": "Restart workers?", "deadline": 1794477600.5}]


def test_snapshot_from_an_older_runtime_still_reads(api):
    _, client, directory = api
    write(directory, sample())  # 0.2.x: no kind, no delivery time, no pendingQuestions.
    body = client.get("/api/plugins/hermes-notify/status").json()
    assert body["runs"][0]["kind"] == "release" and body["pendingQuestions"] == []
    assert body["deliveries"][0]["at"] is None


def test_malformed_pending_question_hides_the_snapshot(api):
    _, client, directory = api
    payload = sample()
    payload["pendingQuestions"] = [{"interactionId": "../x", "project": "demo", "kind": "yes_no", "title": "x", "deadline": 1}]
    write(directory, payload)
    assert client.get("/api/plugins/hermes-notify/status").status_code == 503
