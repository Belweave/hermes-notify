"""`hermes notify setup` signs in, saves the key, enables the plugin, finds the phone and sends a test."""

from types import SimpleNamespace

from hermes_notify import onboarding


def fake_config(monkeypatch, initial=None, available=True):
    """Stand-in for the `hermes config` CLI. Never touches a real Hermes install."""
    values = dict(initial or {})

    def run(*args):
        if not available:
            return None
        if args[0] == "get":
            return values.get(args[1], {onboarding.TRANSPORT_KEY: "builtin", onboarding.FALLBACK_KEY: "deny"}.get(args[1], ""))
        values[args[1]] = args[2]
        return ""
    monkeypatch.setattr(onboarding, "_hermes_config", run)
    return values


def test_setup_flow_end_to_end(monkeypatch, capsys):
    calls, saved, config = [], {}, {}
    polls = iter([(400, {"error": "authorization_pending"}), (200, {"accessToken": "ntf_new", "token": {"id": "tok"}})])
    phones = iter([[], [{"id": "d1", "platform": "ios", "deviceName": "Demo iPhone", "active": True}]])

    def fake(method, url, *, body=None, token=None, timeout=15, key=None):
        calls.append((method, url.rsplit("/", 1)[-1], token))
        if url.endswith("/device-authorization/start"):
            assert set(body["scopes"]) >= {"notifications:send", "interactions:create", "devices:read"}
            return 200, {"deviceCode": "dc", "userCode": "ABCD-EFGH", "verificationUriComplete": "https://x/cli?code=1",
                         "interval": 1, "expiresIn": 60}
        if url.endswith("/device-authorization/token"):
            return next(polls)
        if url.endswith("/devices"):
            return 200, {"devices": next(phones)}
        if url.endswith("/notifications"):
            assert token == "ntf_new" and key
            return 201, {"accepted": 1, "queued": 0}
        raise AssertionError(url)

    monkeypatch.setattr(onboarding, "_request", fake)
    monkeypatch.setattr(onboarding.time, "sleep", lambda _: None)
    monkeypatch.setattr(onboarding, "_saved_token", lambda: "")
    monkeypatch.setattr(onboarding, "_save_token", lambda t: saved.update(token=t))
    monkeypatch.setattr(onboarding, "_can_open_browser", lambda: False)
    hermes_config = fake_config(monkeypatch)
    ctx = SimpleNamespace(set_config=lambda k, v: config.update({k: v}), get_config=lambda k, d=None: config.get(k, d))
    args = SimpleNamespace(reauth=False, no_browser=True, no_wait=False)
    assert onboarding.cmd_setup(ctx, args) == 0
    out = capsys.readouterr().out
    assert saved == {"token": "ntf_new"} and config == {"enabled": True}
    assert "ABCD-EFGH" in out and "Demo iPhone" in out and onboarding.IOS_URL in out
    assert calls[-1][1] == "notifications"
    assert hermes_config == {onboarding.TRANSPORT_KEY: "notify", onboarding.FALLBACK_KEY: "builtin"}
    assert "Approve / Deny" in out


def test_declined_sign_in_is_reported(monkeypatch):
    def fake(method, url, **_):
        if url.endswith("/start"):
            return 200, {"deviceCode": "dc", "userCode": "X", "verificationUri": "https://x", "interval": 1, "expiresIn": 60}
        return 400, {"error": "access_denied"}
    monkeypatch.setattr(onboarding, "_request", fake)
    monkeypatch.setattr(onboarding.time, "sleep", lambda _: None)
    try:
        onboarding.sign_in(open_browser=False)
    except onboarding.SetupError as exc:
        assert "declined" in str(exc)
    else:
        raise AssertionError("expected SetupError")


def test_approvals_keep_a_users_choices(monkeypatch):
    other = fake_config(monkeypatch, {onboarding.TRANSPORT_KEY: "slack"})
    assert onboarding.enable_approvals() == "other:slack" and other[onboarding.TRANSPORT_KEY] == "slack"
    assert onboarding.enable_approvals(force=True) == "on" and other[onboarding.TRANSPORT_KEY] == "notify"
    # Set by hand earlier (transport notify, default deny fallback): add the terminal fallback.
    on = fake_config(monkeypatch, {onboarding.TRANSPORT_KEY: "notify"})
    assert onboarding.enable_approvals() == "already" and on[onboarding.FALLBACK_KEY] == "builtin"
    assert onboarding.disable_approvals() == "off" and on[onboarding.TRANSPORT_KEY] == "builtin"
    fake_config(monkeypatch, available=False)
    assert onboarding.enable_approvals() == "unknown"


def test_approvals_wait_for_a_phone(monkeypatch, capsys):
    values = fake_config(monkeypatch)
    onboarding._setup_approvals([], skip=False)
    assert values == {} and "approvals on" in capsys.readouterr().out
    onboarding._setup_approvals([{"id": "d"}], skip=True)
    assert values == {}


def test_every_setup_failure_names_its_fix(monkeypatch, capsys):
    from hermes_notify.client import explain
    cases = {401: "--reauth", 403: "--reauth", 429: "Wait a minute", 503: "Try again in a few minutes"}
    for status, fix in cases.items():
        message = onboarding._failure(status, {"required": ["devices:read"]}, "Could not check your phones")
        assert fix in message and "Could not check your phones" in message
        assert "token" not in message.lower() or status == 401
    assert "devices:read" in onboarding._failure(403, {"required": ["devices:read"]}, "x")
    for status, fix in {401: "--reauth", 403: "--reauth", 429: "Retry", 502: "Retry"}.items():
        assert fix in explain(status, ("notifications:send",), 30)


def test_test_command_explains_a_missing_phone(monkeypatch, capsys):
    monkeypatch.setattr(onboarding, "_saved_token", lambda: "ntf_saved")
    monkeypatch.setattr(onboarding, "_request", lambda method, url, **kw:
                        (200, {"devices": []}) if url.endswith("/devices") else (201, {"accepted": 0, "queued": 0}))
    assert onboarding.cmd_test(None, SimpleNamespace()) == 1
    out = capsys.readouterr().out
    assert "No phone is connected" in out and onboarding.IOS_URL in out and "ntf_saved" not in out


def test_status_reports_unreachable_notify_in_one_line(monkeypatch, capsys):
    monkeypatch.setattr(onboarding, "_saved_token", lambda: "ntf_saved")
    monkeypatch.setattr(onboarding, "readiness", lambda ctx: (True, True, True))
    monkeypatch.setattr(onboarding, "approval_transport", lambda: "notify")

    def offline(*_a, **_k):
        raise onboarding.SetupError("Could not reach notify.belweave.ai. Check your internet connection and try again.")
    monkeypatch.setattr(onboarding, "_request", offline)
    ctx = SimpleNamespace(get_config=lambda k, d=None: d)
    assert onboarding.cmd_status(ctx, SimpleNamespace()) == 1
    out = capsys.readouterr().out
    assert "Phones:      unknown - Could not reach" in out and "Plugin:      hermes-notify" in out
    assert "ntf_saved" not in out
