"""Hermes entrypoint. Loading registers a transport and performs no network I/O."""

def register(ctx):
    import os
    import threading

    if not hasattr(ctx, "register_approval_transport"):
        raise RuntimeError("This Hermes build lacks the public approval transport API")
    enabled = ctx.get_config("enabled", False) is True
    timeout = ctx.get_config("timeout_seconds", 120)
    device_id = ctx.get_config("device_id", "")
    # Capture profile ownership now. Hermes invokes transports on a fresh worker thread.
    # The catalog's recording context deliberately has no persistent state.
    state = getattr(ctx, "state", None)
    data_dir = state.data_dir if state is not None else None
    token = os.environ.get("NOTIFY_API_TOKEN", "") if enabled else ""
    test_url = os.environ.get("HERMES_NOTIFY_TEST_URL") if enabled else None
    stopped = threading.Event()
    ctx.on_unload(stopped.set)

    def present(request):
        if not enabled or data_dir is None or stopped.is_set():
            return request.respond("deny")
        from .hermes_notify.bridge import ApprovalBridge
        from .hermes_notify.client import API_BASE, NotifyClient
        from .hermes_notify.ledger import Ledger

        # Open client and storage only when an approval is actually requested.
        client = NotifyClient(token, test_url or API_BASE)
        ledger = Ledger(data_dir / "approvals.sqlite3")
        bridge = ApprovalBridge(
            client, ledger,
            timeout_seconds=timeout,
            device_id=device_id,
            is_cancelled=stopped.is_set,
        )
        return bridge.present(request)

    ctx.register_approval_transport("notify", present)
