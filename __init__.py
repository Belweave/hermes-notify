"""Hermes Pocket entrypoint. Registration performs no network I/O."""


def register(ctx):
    import json
    import os

    if not hasattr(ctx, "register_approval_transport"):
        raise RuntimeError("This Hermes build lacks the public approval transport API")
    from .hermes_notify.runtime import Runtime
    from .hermes_notify.tools import SCHEMAS, calling_session

    if hasattr(ctx, "register_cli_command"):
        from .hermes_notify.onboarding import register_cli
        register_cli(ctx)

    if hasattr(ctx, "register_skill"):
        from . import skills
        skills.register(ctx)

    enabled = ctx.get_config("enabled", False) is True
    settings = {key: ctx.get_config(key, default) for key, default in {
        "timeout_seconds": 120, "device_id": "", "publisher_origin": "", "worker_name": "",
        "worker_subdomain": "", "progress_enabled": False, "progress_interval_seconds": 5,
        "retention_days": 30, "allow_reply_injection": False,
    }.items()}
    token, publish_token = "", ""
    if enabled:
        from agent.secret_scope import get_secret
        token = get_secret("NOTIFY_API_TOKEN", "")
        publish_token = get_secret("HERMES_NOTIFY_PUBLISH_TOKEN", "")
    state = getattr(ctx, "state", None)
    runtime = Runtime(state.data_dir, enabled=enabled, token=token, publish_token=publish_token,
                      settings=settings, test_url=os.environ.get("HERMES_NOTIFY_TEST_URL") if enabled else None,
                      test_worker_url=os.environ.get("HERMES_NOTIFY_TEST_WORKER_URL") if enabled else None,
                      inject=getattr(ctx, "inject_message", None)) if state is not None else None
    # Recording/catalog contexts intentionally have no state. They still see every registration.
    ctx.on_unload(runtime.close if runtime else lambda: None)
    ctx.register_approval_transport("notify", runtime.present if runtime else lambda request: request.respond("deny"))
    if hasattr(ctx, "register_hook"):
        ctx.register_hook("pre_approval_request", runtime.observe_pre if runtime else lambda **_: None)
        ctx.register_hook("post_approval_response", runtime.observe_post if runtime else lambda **_: None)
    if hasattr(ctx, "register_tool"):
        for spec in SCHEMAS:
            def handle(args, _name=spec["name"], **kwargs):
                if runtime is None:
                    return json.dumps({"ok": False, "error": "Persistent Hermes profile state is unavailable"})
                # Reject unknown model fields before allowing any side effects.
                allowed = next(s for s in SCHEMAS if s["name"] == _name)["parameters"]["properties"]
                if not isinstance(args, dict) or set(args) - set(allowed):
                    return json.dumps({"ok": False, "error": "Unknown tool argument"})
                return json.dumps(runtime.call(_name, args, calling_session(kwargs)), ensure_ascii=True)
            ctx.register_tool(name=spec["name"], toolset="hermes_notify", schema=spec, handler=handle,
                              description=spec["description"])
