"""Standalone isolated real-Hermes loader/registry probe, invoked by pytest only."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), os.environ.get("HERMES_SOURCE") or str(ROOT / ".local/hermes-source")]


def main():
    from scripts.mock_notify import PocketMock
    with tempfile.TemporaryDirectory(prefix="pocket-registry-") as scratch, PocketMock().serve() as url:
        home = Path(scratch)
        (home / "plugins").mkdir()
        (home / "plugins/hermes-notify").symlink_to(ROOT, target_is_directory=True)
        (home / "bundled").mkdir()
        os.environ.update(HERMES_HOME=str(home), HERMES_BUNDLED_PLUGINS=str(home / "bundled"),
                          HERMES_NOTIFY_TEST_URL=url + "/api/agent", HERMES_NOTIFY_TEST_WORKER_URL=url,
                          NOTIFY_API_TOKEN="dummy", HERMES_NOTIFY_PUBLISH_TOKEN="dummy")
        (home / "config.yaml").write_text(json.dumps({"plugins": {"enabled": ["hermes-notify"], "isolation": "in_process",
            "entries": {"hermes-notify": {"settings": {"enabled": True, "publisher_origin": "https://pocket.example.com"}}}}}))
        from gateway.session_context import scoped_session_key
        from hermes_cli.plugins import get_plugin_manager
        from tools.registry import registry
        manager = get_plugin_manager()
        manager.discover_and_load()
        names = ["notify_release", "notify_publish_app", "notify_send", "notify_ask", "notify_replies", "notify_status",
                 "notify_progress", "notify_cancel"]
        assert all(registry.get_entry(n, scope=manager.scope_key) for n in names)
        with scoped_session_key("probe-route"):
            def call(name, args):
                result = json.loads(registry.dispatch(name, args, scope=manager.scope_key, session_id="probe-session"))
                assert result["ok"], result
                return result
            call("notify_release", {"action": "begin", "project": "probe", "version": "1"})
            call("notify_publish_app", {"project": "probe"})
            call("notify_send", {"project": "probe", "body": "Synthetic registry update"})
            asked = call("notify_ask", {"project": "probe", "title": "Synthetic question", "prompt": "Reply?"})
            call("notify_replies", {"project": "probe"})
            call("notify_cancel", {"interaction_id": asked["interactionId"]})
            call("notify_progress", {"action": "start", "title": "Synthetic job", "status": "Working"})
            call("notify_status", {})
        sections = getattr(manager, "_system_prompt_sections", {})
        assert "hermes-notify.rules" in sections, sorted(sections)
        manager.unload("hermes-notify")
        assert manager.get_approval_transport("notify") is None
        assert all(registry.get_entry(n, scope=manager.scope_key) is None for n in names)
        print(json.dumps({"registered": len(names), "dispatched": len(names), "unloaded": True}))


if __name__ == "__main__":
    main()
