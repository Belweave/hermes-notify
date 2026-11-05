#!/usr/bin/env python3
"""Load the plugin in real Hermes and exercise its execute_code approval gate."""

import argparse
import json
import os
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.mock_notify import MockNotify
from hermes_notify.client import TEST_TOKEN


def run(source, *, live=False, answer="approve", enabled=True):
    if not (source / "hermes_cli/plugins.py").is_file():
        raise SystemExit("Hermes source missing. Run scripts/fetch_hermes.py first.")
    if live and not os.environ.get("NOTIFY_API_TOKEN"):
        raise SystemExit("Live test needs NOTIFY_API_TOKEN from env or the OS keychain.")
    sys.path.insert(0, str(source.resolve()))
    mock = MockNotify(answer)
    with tempfile.TemporaryDirectory(prefix="hermes-notify-") as scratch, (nullcontext(None) if live else mock.serve()) as url:
        home = Path(scratch)
        plugins = home / "plugins"
        plugins.mkdir()
        (plugins / "hermes-notify").symlink_to(ROOT, target_is_directory=True)
        bundled = home / "empty-bundled"
        bundled.mkdir()
        # JSON is valid YAML. The real user's profile and credentials are never changed.
        timeout = 120 if live else 3
        (home / "config.yaml").write_text(json.dumps({
            "plugins": {"enabled": ["hermes-notify"], "isolation": "in_process", "entries": {"hermes-notify": {"settings": {
                "enabled": enabled, "timeout_seconds": timeout,
                "device_id": os.environ.get("HERMES_NOTIFY_DEVICE_ID", "") if live else "",
            }}}},
            "approvals": {"mode": "manual", "timeout": timeout},
            "security": {"approval": {"transport": "notify"}},
        }))
        os.environ.update(HERMES_HOME=str(home), HERMES_BUNDLED_PLUGINS=str(bundled), HERMES_GATEWAY_SESSION="1")
        # Remove inherited switches which could bypass the gate in this isolated test process.
        for name in ("HERMES_YOLO_MODE", "HERMES_SAFE_MODE", "HERMES_ENABLE_PROJECT_PLUGINS", "HERMES_QUIET", "HERMES_CRON_SESSION", "HERMES_SESSION_PLATFORM"):
            os.environ.pop(name, None)
        if live:
            os.environ.pop("HERMES_NOTIFY_TEST_URL", None)
        else:
            os.environ.update(NOTIFY_API_TOKEN=TEST_TOKEN, HERMES_NOTIFY_TEST_URL=url)
        from hermes_cli.plugins import get_plugin_manager
        from tools import approval, approval_context

        manager = get_plugin_manager()
        manager.discover_and_load()
        if manager.get_approval_transport("notify") is None:
            raise SystemExit("Hermes did not load the Notify transport")
        session = approval_context.set_current_session_key("hermes-notify-spike")
        try:
            # The actual Hermes gate receives a harmless proposed script. No code is executed.
            result = approval.check_execute_code_guard('print("Notify approval round trip complete")', "local")
        finally:
            approval_context.reset_current_session_key(session)
            manager.unload("hermes-notify")
        pushes = sum(method == "POST" and path == "/api/agent/interactions" for method, path, *_ in mock.requests)
        if not live and enabled and pushes != 1:
            raise SystemExit("Spike failed: the real Hermes gate did not create exactly one mock prompt")
        summary = {
            "mode": "live" if live else "mock", "plugin_loaded": True,
            "event": "Hermes execute_code approval", "hermes_approved": result.get("approved") is True,
            "mock_pushes": pushes if not live else None,
            "phone_answer": answer if not live and enabled else "inspect Notify for live result" if live else "not requested",
            "continued": result.get("approved") is True,
            "action_executed": False,
            "transport_unloaded": manager.get_approval_transport("notify") is None,
        }
        print(json.dumps(summary, indent=2))
        return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hermes-source", type=Path, default=ROOT / ".local/hermes-source")
    parser.add_argument("--answer", choices=["approve", "deny", "timeout"], default="approve")
    parser.add_argument("--live", action="store_true", help="Send ONE real phone approval using NOTIFY_API_TOKEN. Requires user authorization.")
    parser.add_argument("--disabled", action="store_true", help="Verify the default-off plugin sends nothing")
    args = parser.parse_args()
    run(args.hermes_source, live=args.live, answer=args.answer, enabled=not args.disabled)
