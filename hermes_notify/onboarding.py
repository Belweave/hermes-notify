"""`hermes notify setup`: one guided command from nothing to a test push on your phone.

1. Sign in to Notify (or create a free account) with a short browser code.
2. Save the scoped API key to this Hermes profile and turn the plugin on.
3. Wait for the Notify phone app to register, with install links.
4. Send a test notification.

Standard library only, so it behaves the same on macOS, Linux and Windows,
including over SSH where no browser can open.
"""

import json
import os
import platform
import socket
import sys
import time
import webbrowser
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .client import API_BASE, USER_AGENT, NoRedirects

SITE = "https://notify.belweave.ai"
ENV_NAME = "NOTIFY_API_TOKEN"
SCOPES = ["notifications:send", "interactions:create", "interactions:read", "devices:read",
          "apps:read", "apps:write", "activities:read", "activities:write"]
KEY_LIFETIME_SECONDS = 90 * 86400
IOS_URL = "https://testflight.apple.com/join/1MDYPc7a"
ANDROID_URL = "https://github.com/Belweave/notify/tree/main/apps/android"
PHONE_WAIT_SECONDS = 600

_opener = build_opener(NoRedirects())


class SetupError(Exception):
    pass


def _request(method, url, *, body=None, token=None, timeout=15, key=None):
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["Idempotency-Key"] = key
    try:
        with _opener.open(Request(url, data=data, headers=headers, method=method), timeout=timeout) as response:
            return response.status, json.loads(response.read(256 * 1024) or b"{}")
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read(64 * 1024) or b"{}")
        except ValueError:
            detail = {}
        finally:
            exc.close()
        return exc.code, detail if isinstance(detail, dict) else {}
    except (URLError, OSError, ValueError):
        raise SetupError("Could not reach notify.belweave.ai. Check your internet connection and try again.") from None


def _say(text=""):
    print(text, flush=True)


def _can_open_browser():
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    if sys.platform in ("darwin", "win32"):
        return True
    # Linux/BSD: only with a graphical session, otherwise webbrowser may launch a text browser.
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _client_name():
    host = (socket.gethostname() or "computer").split(".")[0][:40]
    return f"Hermes on {host} ({platform.system() or 'unknown OS'})"


def sign_in(*, open_browser=True):
    """Device-code sign-in. Works for new and existing Notify accounts. Returns the API key."""
    status, started = _request("POST", SITE + "/api/device-authorization/start", body={
        "clientName": _client_name(), "scopes": SCOPES, "expiresInSeconds": KEY_LIFETIME_SECONDS})
    if status >= 400 or not isinstance(started.get("deviceCode"), str):
        raise SetupError(f"Notify could not start sign-in (HTTP {status}). Try again in a minute.")
    url = started.get("verificationUriComplete") or started.get("verificationUri")
    _say("Step 1 of 3 - Sign in to Notify (free; new accounts are created on the same page)")
    _say()
    _say(f"  Open:  {url}")
    _say(f"  Code:  {started.get('userCode')}")
    _say()
    if open_browser and _can_open_browser():
        try:
            webbrowser.open(url)
            _say("  Opened your browser. Sign in with Apple or Google, then approve \"Hermes\".")
        except Exception:
            _say("  Open the link above in any browser, on this computer or your phone.")
    else:
        _say("  Open the link above in any browser, on this computer or your phone,")
        _say("  sign in with Apple or Google, then approve \"Hermes\".")
    _say()
    _say("  Waiting for approval...", )
    interval = max(1, int(started.get("interval") or 5))
    deadline = time.monotonic() + max(30, int(started.get("expiresIn") or 600))
    while time.monotonic() < deadline:
        time.sleep(interval)
        status, result = _request("POST", SITE + "/api/device-authorization/token",
                                  body={"deviceCode": started["deviceCode"]})
        if status < 400 and isinstance(result.get("accessToken"), str):
            return result["accessToken"]
        error = result.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval = int(result.get("interval") or interval + 5)
            continue
        if error == "access_denied":
            raise SetupError("Sign-in was declined in the browser. Run `hermes notify setup` to try again.")
        if error == "expired_token":
            break
        raise SetupError(f"Notify sign-in failed (HTTP {status}). Run `hermes notify setup` to try again.")
    raise SetupError("The sign-in code expired. Run `hermes notify setup` to get a new one.")


def devices(token):
    status, result = _request("GET", API_BASE + "/devices", token=token)
    if status == 401:
        raise SetupError("Your saved Notify key is no longer valid. Run `hermes notify setup --reauth`.")
    if status == 403:
        raise SetupError("Your Notify key cannot list devices. Run `hermes notify setup --reauth` to grant access.")
    if status >= 400:
        raise SetupError(f"Notify returned HTTP {status} while checking devices.")
    rows = result.get("devices")
    return [d for d in rows if isinstance(d, dict) and d.get("active", True)] if isinstance(rows, list) else []


def _describe(device):
    name = device.get("deviceName") or ("iPhone" if device.get("platform") == "ios" else "Android phone")
    return f"{name} ({device.get('platform', 'phone')})"


def wait_for_phone(token, *, wait=True):
    found = devices(token)
    _say("Step 2 of 3 - Connect your phone")
    _say()
    if found:
        for device in found:
            _say(f"  Found {_describe(device)}.")
        _say()
        return found
    _say("  Install the Notify app and sign in with the SAME account you just used:")
    _say(f"    iPhone:   {IOS_URL}  (TestFlight, free)")
    _say(f"    Android:  {ANDROID_URL}")
    _say("  Open Notify, sign in, and tap Allow when it asks to send notifications.")
    _say()
    if not wait:
        return []
    _say("  Waiting for your phone to register (Ctrl+C to skip)...")
    deadline = time.monotonic() + PHONE_WAIT_SECONDS
    try:
        while time.monotonic() < deadline:
            time.sleep(4)
            found = devices(token)
            if found:
                _say(f"  Connected {_describe(found[0])}.")
                _say()
                return found
    except KeyboardInterrupt:
        _say()
    _say("  No phone yet. Finish installing the app, then run `hermes notify test`.")
    _say()
    return []


def send_test(token):
    status, result = _request("POST", API_BASE + "/notifications", token=token,
                              key="hermes-setup-" + str(int(time.time())), body={
                                  "title": "Hermes is connected",
                                  "body": "Your Hermes agent can now send you updates and ask you questions here.",
                                  "project": "hermes"})
    if status >= 400:
        raise SetupError(f"The test notification was not accepted (HTTP {status}).")
    accepted = result.get("accepted", 0) if isinstance(result, dict) else 0
    queued = result.get("queued", 0) if isinstance(result, dict) else 0
    return accepted, queued


def _saved_token():
    try:
        from agent.secret_scope import get_secret
        return get_secret(ENV_NAME, "") or ""
    except Exception:
        return os.environ.get(ENV_NAME, "")


def _save_token(token):
    # Public plugin API (hermes_cli/data/plugin_api.json): Hermes's own profile .env writer,
    # the same file the install prompt uses, at the right path on every OS.
    from hermes_cli.gateway_setup_wizard import save_env_values
    save_env_values(**{ENV_NAME: token})
    os.environ[ENV_NAME] = token


def _enable(ctx):
    if ctx is not None and hasattr(ctx, "set_config"):
        ctx.set_config("enabled", True)
        return True
    return False


def cmd_setup(ctx, args):
    _say()
    _say("Hermes x Notify setup")
    _say("Get Hermes updates, questions and approvals on your phone.")
    _say()
    token = "" if getattr(args, "reauth", False) else _saved_token()
    if token:
        try:
            devices(token)
            _say("Step 1 of 3 - Notify key already saved for this profile. (Use --reauth to replace it.)")
            _say()
        except SetupError:
            token = ""
    if not token:
        token = sign_in(open_browser=not getattr(args, "no_browser", False))
        _save_token(token)
        _say("  Signed in. API key saved to this Hermes profile.")
        _say()
    if _enable(ctx):
        _say("  Plugin turned on (plugins.entries.hermes-notify.settings.enabled: true).")
        _say()
    phones = wait_for_phone(token, wait=not getattr(args, "no_wait", False))
    _say("Step 3 of 3 - Test notification")
    _say()
    accepted, queued = send_test(token)
    if phones and (accepted or queued):
        _say("  Sent. Check your phone for \"Hermes is connected\".")
    elif phones:
        _say("  Notify accepted the request but no device took it yet; check notification permissions.")
    else:
        _say("  Saved to your Notify inbox. It will show on your phone once the app is signed in.")
    _say()
    _say("All set. Start a new Hermes session and try:")
    _say("  \"Send me a Notify message when you're done.\"")
    _say("  \"Ask me on my phone whether to deploy, and wait for my answer.\"")
    _say()
    _say("Optional: approve Hermes commands from your phone by adding to config.yaml:")
    _say("  security:")
    _say("    approval:")
    _say("      transport: notify")
    _say()
    return 0


def cmd_status(ctx, args):
    token = _saved_token()
    enabled = bool(ctx.get_config("enabled", False)) if ctx is not None else None
    _say(f"Notify key:  {'saved' if token else 'missing - run `hermes notify setup`'}")
    _say(f"Plugin on:   {'yes' if enabled else 'no - run `hermes notify setup`'}")
    if token:
        phones = devices(token)
        _say(f"Phones:      {', '.join(_describe(d) for d in phones) if phones else 'none - install the Notify app and sign in'}")
    return 0 if token and enabled else 1


def cmd_test(ctx, args):
    token = _saved_token()
    if not token:
        raise SetupError("No Notify key yet. Run `hermes notify setup` first.")
    accepted, queued = send_test(token)
    _say("Test notification sent." if accepted or queued else
         "Notify accepted the request, but no phone is registered yet. Install the app and sign in.")
    return 0


def register_cli(ctx):
    def setup_parser(parser):
        subs = parser.add_subparsers(dest="notify_command", required=False)
        setup = subs.add_parser("setup", help="Sign in to Notify, connect your phone and send a test")
        for p in (parser, setup):
            p.add_argument("--reauth", action="store_true", help="Sign in again and replace the saved key")
            p.add_argument("--no-browser", action="store_true", help="Print the sign-in link without opening a browser")
            p.add_argument("--no-wait", action="store_true", help="Do not wait for the phone app to register")
        subs.add_parser("status", help="Show whether Notify is configured and which phones are connected")
        subs.add_parser("test", help="Send a test notification to your phone")
        parser.set_defaults(func=dispatch)

    def dispatch(args):
        command = getattr(args, "notify_command", None) or "setup"
        handler = {"setup": cmd_setup, "status": cmd_status, "test": cmd_test}[command]
        try:
            return handler(ctx, args)
        except SetupError as exc:
            _say(f"\n{exc}")
            return 1
        except KeyboardInterrupt:
            _say("\nSetup canceled. Run `hermes notify setup` any time to continue.")
            return 130

    ctx.register_cli_command(name="notify", help="Set up Notify: sign in, connect your phone, send a test",
                             setup_fn=setup_parser, handler_fn=dispatch,
                             description="Connect Hermes to the Notify phone app in one step.")
