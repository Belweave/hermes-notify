"""`hermes notify setup` signs in, saves the key, enables the plugin, finds the phone and sends a test."""

from types import SimpleNamespace

from hermes_notify import onboarding


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
    ctx = SimpleNamespace(set_config=lambda k, v: config.update({k: v}), get_config=lambda k, d=None: config.get(k, d))
    args = SimpleNamespace(reauth=False, no_browser=True, no_wait=False)
    assert onboarding.cmd_setup(ctx, args) == 0
    out = capsys.readouterr().out
    assert saved == {"token": "ntf_new"} and config == {"enabled": True}
    assert "ABCD-EFGH" in out and "Demo iPhone" in out and onboarding.IOS_URL in out
    assert calls[-1][1] == "notifications"


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
