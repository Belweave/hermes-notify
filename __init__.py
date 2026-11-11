"""Hermes Pocket entrypoint. Registration performs no network I/O."""


def register(ctx):
    import json
    import logging
    import os

    if not hasattr(ctx, "register_approval_transport"):
        raise RuntimeError("This Hermes build lacks the public approval transport API")
    from .hermes_notify.runtime import SETTINGS, Runtime, profile_setting, resolve_secret
    from .hermes_notify.tools import SCHEMAS, calling_session

    if hasattr(ctx, "register_cli_command"):
        from .hermes_notify.onboarding import register_cli
        register_cli(ctx)

    if hasattr(ctx, "register_skill"):
        from . import skills
        skills.register(ctx)

    # Configuration and secrets are resolved in the caller's profile context: at load, on every
    # tool call and in the pre-approval hook. A load-time snapshot alone left a long-running
    # gateway/TUI "not set up" after `hermes notify setup`. Approval workers have no profile
    # context, so they use the values from the most recent refresh instead of reading secrets.
    def enabled_setting():
        if ctx.get_config("enabled", False) is True:
            return True
        # A context loaded before `hermes notify setup` wrote config.yaml can keep answering from
        # its load-time view. The profile's config file on disk is the source of truth.
        return profile_setting("enabled") is True

    def resolved():
        enabled = enabled_setting()
        return {
            "enabled": enabled,
            "settings": {key: ctx.get_config(key, default) for key, default in SETTINGS.items()},
            "token": resolve_secret("NOTIFY_API_TOKEN") if enabled else "",
            "publish_token": resolve_secret("HERMES_NOTIFY_PUBLISH_TOKEN") if enabled else "",
            "test_url": os.environ.get("HERMES_NOTIFY_TEST_URL") if enabled else None,
            "test_worker_url": os.environ.get("HERMES_NOTIFY_TEST_WORKER_URL") if enabled else None,
            "webhook_secret": resolve_secret("NOTIFY_WEBHOOK_SECRET") if enabled else "",
        }

    state = getattr(ctx, "state", None)
    runtime = None
    if state is not None:
        try:
            initial = resolved()
        except Exception as exc:
            initial = {"enabled": False, "settings": {}, "token": "", "publish_token": ""}
            logging.getLogger("hermes_notify").warning("Notify configuration unavailable at load: %s", type(exc).__name__)
        runtime = Runtime(state.data_dir, inject=getattr(ctx, "inject_message", None), **initial)

    def refresh():
        if runtime is None:
            return
        try:
            runtime.configure(**resolved())
        except Exception as exc:
            # Keep the last good configuration. Record and log only the exception class, never
            # its message: it could carry secret-resolution details.
            runtime.config_error(type(exc).__name__)

    # Recording/catalog contexts intentionally have no state. They still see every registration.
    ctx.on_unload(runtime.close if runtime else lambda: None)
    ctx.register_approval_transport("notify", runtime.present if runtime else lambda request: request.respond("deny"))
    if hasattr(ctx, "register_hook"):
        def observe_pre(**kwargs):
            refresh()
            return runtime.observe_pre(**kwargs)
        ctx.register_hook("pre_approval_request", observe_pre if runtime else lambda **_: None)
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
                refresh()
                return json.dumps(runtime.call(_name, args, calling_session(kwargs)), ensure_ascii=True)
            ctx.register_tool(name=spec["name"], toolset="hermes_notify", schema=spec, handler=handle,
                              description=spec["description"])
