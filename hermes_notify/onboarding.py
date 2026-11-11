"""`hermes notify setup`: one guided command from nothing to a test push on your phone.

1. Sign in to Notify (or create a free account) with a short browser code.
2. Save the scoped API key to this Hermes profile and turn the plugin on.
3. Wait for the Notify phone app to register, with install links.
4. Send a test notification.
5. Send Hermes command approvals to the phone, with the terminal prompt as fallback.

Standard library only, so it behaves the same on macOS, Linux and Windows,
including over SSH where no browser can open.
"""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .client import API_BASE, USER_AGENT, NoRedirects

SITE = "https://notify.belweave.ai"
ENV_NAME = "NOTIFY_API_TOKEN"
SCOPES = ["notifications:send", "interactions:create", "interactions:read", "devices:read",
          "apps:read", "apps:write", "activities:read", "activities:write",
          "services:read", "services:write"]  # services:* manages the answer webhook.
KEY_LIFETIME_SECONDS = 90 * 86400
IOS_URL = "https://testflight.apple.com/join/1MDYPc7a"
ANDROID_URL = "https://github.com/Belweave/notify/tree/main/apps/android"
PHONE_WAIT_SECONDS = 600
TRANSPORT_KEY = "security.approval.transport"
FALLBACK_KEY = "security.approval.transport_fallback"

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
    _say("Step 2 of 4 - Connect your phone")
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
    """Turn the runtime on. True when this call changed it."""
    if ctx is None or not hasattr(ctx, "set_config"):
        return False
    if ctx.get_config("enabled", False) is True:
        return False
    ctx.set_config("enabled", True)
    return True


def _hermes_config(*args):
    """Run Hermes's public `hermes config` command for this profile. None when unavailable.

    Plugin settings (ctx.set_config) cannot reach security.*, and Hermes's config writer is
    not a public plugin API, so setup uses the same documented command a user would type.
    """
    exe = shutil.which("hermes")
    if not exe:
        return None
    try:
        done = subprocess.run([exe, "config", *args], capture_output=True, text=True, timeout=60,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def approval_transport():
    value = _hermes_config("get", TRANSPORT_KEY)
    return value.strip().lower() if value is not None else None


def _say_approval_snippet():
    _say("    hermes config set security.approval.transport notify")
    _say("    hermes config set security.approval.transport_fallback builtin")
    _say()


def enable_approvals(*, force=False):
    """Route Hermes command approvals to Notify. Returns a short status word."""
    current = approval_transport()
    if current is None:
        return "unknown"
    if current not in ("", "builtin", "notify") and not force:
        return f"other:{current}"
    if current != "notify" and _hermes_config("set", TRANSPORT_KEY, "notify") is None:
        return "unknown"
    # Hermes's default fallback denies: if Notify cannot be reached, every flagged command would
    # be refused without a prompt. Use the normal terminal prompt instead. To refuse instead:
    # `hermes config set security.approval.transport_fallback deny`.
    if (_hermes_config("get", FALLBACK_KEY) or "").strip().lower() != "builtin":
        _hermes_config("set", FALLBACK_KEY, "builtin")
    return "already" if current == "notify" else "on"


def disable_approvals():
    return "off" if _hermes_config("set", TRANSPORT_KEY, "builtin") is not None else "unknown"


def _setup_approvals(phones, *, skip=False):
    _say("Step 4 of 4 - Approve Hermes commands from your phone")
    _say()
    if skip:
        _say("  Skipped (--no-approvals). Turn it on later with `hermes notify approvals on`.")
        _say()
        return
    if not phones:
        _say("  Waiting for a phone first. When the app is signed in, run `hermes notify approvals on`.")
        _say()
        return
    result = enable_approvals()
    if result == "already":
        _say("  Already on: approval prompts go to your phone.")
    elif result == "on":
        _say("  On. When Hermes needs permission for a command, your phone gets Approve / Deny.")
        _say("  If Notify can't be reached, Hermes asks in the terminal as usual.")
        _say("  Turn off any time with `hermes notify approvals off`.")
    elif result.startswith("other:"):
        _say(f"  Another approval transport is selected ({result[6:]}); leaving it alone.")
        _say("  Use `hermes notify approvals on --force` to switch to your phone.")
    else:
        _say("  Could not update the Hermes config automatically. Run:")
        _say_approval_snippet()
        return
    _say()


def cmd_setup(ctx, args):
    _say()
    _say("Hermes x Notify setup")
    _say("Get Hermes updates, questions and approvals on your phone.")
    _say()
    token = "" if getattr(args, "reauth", False) else _saved_token()
    if token:
        try:
            devices(token)
            _say("Step 1 of 4 - Notify key already saved for this profile. (Use --reauth to replace it.)")
            _say()
        except SetupError:
            token = ""
    if not token:
        token = sign_in(open_browser=not getattr(args, "no_browser", False))
        _save_token(token)
        _say("  Signed in. API key saved to this Hermes profile.")
        _say()
    if _enable(ctx):
        _say("  Plugin turned on for this profile.")
        _say()
    phones = wait_for_phone(token, wait=not getattr(args, "no_wait", False))
    _say("Step 3 of 4 - Test notification")
    _say()
    accepted, queued = send_test(token)
    if phones and (accepted or queued):
        _say("  Notify accepted it. Check your phone for \"Hermes is connected\".")
    elif phones:
        _say("  Notify took the request but no phone accepted it; check notification permissions.")
    else:
        _say("  Saved to your Notify inbox. It will show on your phone once the app is signed in.")
    _say()
    _setup_approvals(phones, skip=getattr(args, "no_approvals", False))
    _say("All set. It works in open Hermes sessions right away. Try:")
    _say("  \"Send me a Notify message when you're done.\"")
    _say("  \"Ask me on my phone whether to deploy, and wait for my answer.\"")
    _say()
    return 0


def readiness(ctx):
    """One answer to "can Notify tools work right now", shared by `hermes notify status`.

    Returns (key_saved, loaded_enabled, file_enabled): what Hermes's loaded config says and what
    the profile's config.yaml on disk says. They differ when a process loaded before setup.
    """
    from .runtime import profile_setting
    token = _saved_token()
    loaded = ctx.get_config("enabled", False) is True if ctx is not None else None
    on_disk = profile_setting("enabled") is True
    return bool(token), loaded, on_disk


def cmd_status(ctx, args):
    token = _saved_token()
    _, loaded, on_disk = readiness(ctx)
    enabled = bool(loaded or on_disk)
    transport = approval_transport()
    _say(f"Notify key:  {'saved' if token else 'missing - run `hermes notify setup`'}")
    _say(f"Plugin on:   {'yes' if enabled else 'no - run `hermes notify setup`'}")
    stale = loaded is not None and loaded != on_disk
    if stale:
        _say("Config:      loaded settings differ from config.yaml - restart Hermes and the gateway")
    _say("Approvals:   " + ("phone (Notify)" if transport == "notify" else
                            "unknown" if transport is None else f"{transport} - `hermes notify approvals on` to use your phone"))
    if token:
        phones = devices(token)
        _say(f"Phones:      {', '.join(_describe(d) for d in phones) if phones else 'none - install the Notify app and sign in'}")
    _say()
    _say("Running Hermes sessions pick up changes on their next Notify call. If a session still says")
    _say("Notify is not set up, restart Hermes (and `hermes gateway`, if you run one), then ask it to")
    _say("call notify_status: `lastConfigError` names any configuration failure.")
    return 0 if token and enabled and not stale else 1


def cmd_test(ctx, args):
    token = _saved_token()
    if not token:
        raise SetupError("No Notify key yet. Run `hermes notify setup` first.")
    accepted, queued = send_test(token)
    _say("Notify accepted the test notification." if accepted or queued else
         "Notify took the request, but no phone is registered yet. Install the app and sign in.")
    return 0


def cmd_approvals(ctx, args):
    if getattr(args, "state", "on") == "off":
        result = disable_approvals()
        _say("Approvals: back to the terminal prompt." if result == "off" else
             "Could not update the config. Run: hermes config set security.approval.transport builtin")
        return 0 if result == "off" else 1
    result = enable_approvals(force=getattr(args, "force", False))
    if result in ("on", "already"):
        _say("Approvals: your phone (Notify). The terminal prompt is the fallback if Notify can't be reached.")
        return 0
    if result.startswith("other:"):
        _say(f"Another approval transport is selected ({result[6:]}). Use --force to switch.")
        return 1
    _say("Could not update the config automatically. Run:")
    _say_approval_snippet()
    return 1


WEBHOOK_SECRET_ENV = "NOTIFY_WEBHOOK_SECRET"
DEFAULT_WEBHOOK_PORT = 8645


def _public_url_from_boat(port):
    """On a Boat sandbox, `boat host` gives the port a stable public HTTPS URL."""
    import re
    exe = shutil.which("boat")
    if not exe:
        return None
    try:
        done = subprocess.run([exe, "host", str(port), "--public", "--localhost", "--json",
                               "--title", "Hermes Notify webhook"],
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"https://[^\s\"']+", done.stdout or "")
    return match.group(0).rstrip("/") if done.returncode == 0 and match else None


def _create_webhook(token, url):
    from .inbound import EVENTS
    return _request("POST", API_BASE + "/webhooks", token=token, body={
        "name": "Hermes (" + (socket.gethostname() or "computer").split(".")[0][:40] + ")",
        "url": url, "preset": "generic", "events": list(EVENTS), "isDefault": True})


def _probe(url, seconds=20):
    """GET the public health URL until something answers (the listener may need a moment)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            status, body = _request("GET", url, timeout=5)
            if status == 200 and body.get("service") == "hermes-notify":
                return True
        except SetupError:
            pass
        time.sleep(2)
    return False


def cmd_webhooks(ctx, args):
    """Push phone answers into Hermes: Notify calls a signed webhook instead of Hermes polling."""
    from .inbound import Inbound, PATH
    port = int(getattr(args, "port", None) or DEFAULT_WEBHOOK_PORT)
    if getattr(args, "state", "on") == "off":
        if ctx is not None and hasattr(ctx, "set_config"):
            ctx.set_config("inbound_webhook_port", 0)
        webhook_id = ctx.get_config("inbound_webhook_id", "") if ctx is not None else ""
        token = _saved_token()
        if webhook_id and token:
            _request("DELETE", API_BASE + "/webhooks/" + webhook_id, token=token)
        if ctx is not None and hasattr(ctx, "set_config"):
            ctx.set_config("inbound_webhook_id", "")
        _say("Inbound webhooks: off. Use notify_replies to collect answers.")
        return 0
    token = _saved_token()
    if not token:
        raise SetupError("No Notify key yet. Run `hermes notify setup` first.")
    base = (getattr(args, "url", None) or "").rstrip("/")
    if not base:
        _say(f"Getting a public HTTPS URL for port {port}...")
        base = _public_url_from_boat(port) or ""
    if not base.startswith("https://"):
        _say("Hermes needs a public HTTPS URL that forwards to port %d on this machine." % port)
        _say("  On a Boat sandbox:   boat host <sandbox-id> %d --public --localhost" % port)
        _say("  Elsewhere, e.g.:     cloudflared tunnel --url http://localhost:%d" % port)
        _say("Then run: hermes notify webhooks on --url https://<that-url>")
        return 1
    url = base if base.endswith(PATH) else base + PATH
    status, created = _create_webhook(token, url)
    if status == 403:
        _say("Your Notify key predates webhook permission. Approve a new key in the browser:")
        token = sign_in(open_browser=not getattr(args, "no_browser", False))
        _save_token(token)
        status, created = _create_webhook(token, url)
    secret = created.get("signingSecret") if isinstance(created, dict) else None
    webhook = created.get("webhook") if isinstance(created, dict) else None
    if status >= 400 or not isinstance(secret, str) or not isinstance(webhook, dict):
        raise SetupError(f"Notify could not save the webhook (HTTP {status}): {created.get('error', '')}".rstrip(": "))
    from hermes_cli.gateway_setup_wizard import save_env_values
    save_env_values(**{WEBHOOK_SECRET_ENV: secret})
    os.environ[WEBHOOK_SECRET_ENV] = secret
    if ctx is not None and hasattr(ctx, "set_config"):
        old = ctx.get_config("inbound_webhook_id", "")
        if old and old != webhook.get("id"):
            _request("DELETE", API_BASE + "/webhooks/" + old, token=token)
        ctx.set_config("inbound_webhook_port", port)
        ctx.set_config("inbound_webhook_id", webhook.get("id", ""))
        ctx.set_config("allow_reply_injection", True)
    # Lets the TUI/gateway host accept the answer as a new turn in the asking session.
    _hermes_config("set", "plugins.entries.hermes-notify.allow_gateway_injection", "true")
    _say(f"Notify will push answers to {url}")
    # Prove the public URL reaches this machine. A running Hermes may already hold the port.
    probe = Inbound(lambda _iid: None)
    probe.ensure(port=port, host="127.0.0.1", secret=secret)
    try:
        reachable = _probe(url)
    finally:
        probe.close()
    if reachable:
        _say("Reachable from the internet: yes.")
    else:
        _say("Could not reach the URL yet. Hermes listens once it reloads; check again with `hermes notify status`.")
    _say("Restart Hermes (and the gateway, if one runs) so it starts listening. Phone answers then")
    _say("arrive in the session that asked, with no polling.")
    return 0


def register_cli(ctx):
    def setup_parser(parser):
        subs = parser.add_subparsers(dest="notify_command", required=False)
        setup = subs.add_parser("setup", help="Sign in to Notify, connect your phone and send a test")
        for p in (parser, setup):
            p.add_argument("--reauth", action="store_true", help="Sign in again and replace the saved key")
            p.add_argument("--no-browser", action="store_true", help="Print the sign-in link without opening a browser")
            p.add_argument("--no-wait", action="store_true", help="Do not wait for the phone app to register")
            p.add_argument("--no-approvals", action="store_true",
                           help="Do not send Hermes command approvals to the phone")
        subs.add_parser("status", help="Show whether Notify is configured and which phones are connected")
        subs.add_parser("test", help="Send a test notification to your phone")
        approvals = subs.add_parser("approvals", help="Send Hermes command approvals to your phone (on) or the terminal (off)")
        approvals.add_argument("state", choices=["on", "off"])
        approvals.add_argument("--force", action="store_true", help="Replace another selected approval transport")
        hooks = subs.add_parser("webhooks", help="Push phone answers into Hermes with a signed webhook (no polling)")
        hooks.add_argument("state", choices=["on", "off"])
        hooks.add_argument("--url", help="Public HTTPS URL that forwards to the port (detected on Boat)")
        hooks.add_argument("--port", type=int, default=DEFAULT_WEBHOOK_PORT, help="Local port to listen on")
        hooks.add_argument("--no-browser", action="store_true", help="Print sign-in links instead of opening a browser")
        parser.set_defaults(func=dispatch)

    def dispatch(args):
        command = getattr(args, "notify_command", None) or "setup"
        handler = {"setup": cmd_setup, "status": cmd_status, "test": cmd_test, "approvals": cmd_approvals,
                   "webhooks": cmd_webhooks}[command]
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
