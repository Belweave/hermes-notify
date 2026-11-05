# Local verification

The approval spike is ready for one explicitly authorized live phone test. **No real Notify push or phone answer has been tested yet.** All completed Notify round trips use a loopback HTTP mock and a simulated phone actor.

## What ran

- The real Hermes plugin manager discovered `plugin.yaml`, imported `register(ctx)`, and registered `notify` in a temporary profile.
- The real `check_execute_code_guard` created a host approval request for a harmless proposed print script. The plugin sent one HTTP interaction-create request to mock Notify, then read the answer through the wait endpoint.
- A separate simulated phone actor supplied approve, deny, or no answer. Hermes returned the corresponding approved/denied result. No proposed script or shell command was executed.
- Plugin unload removed the registered transport. The default-disabled configuration produced no mock push.
- The unit/integration suite covers changed interaction IDs, digests, kinds, titles and prompts; opaque digest values; negative and missing responses; timeout; duplicate/reopened requests; concurrent ledger claims; unload while waiting; late host results; unknown create outcomes; large prompts; credential/endpoint separation; and mock responses checked against the captured public OpenAPI schemas.

The local suite passed **35 tests**. The runtime package passed all **15** Hermes catalog validation checks with no warnings. Validation of the full authored tree also passes all 15 checks, with one warning: the development-only `scripts/spike.py` harness imports Hermes manager and guard internals to exercise real host behavior. Those imports are not in the plugin entrypoint or runtime import path; do not present the harness as a stable public Hermes CLI. The isolation report correctly says `in_process`: approval transports hold a live host request channel. This is not an isolated or sandboxed plugin.

The pinned source is `ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`. The same mocked approval path also passed against the installed source at `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. Catalog CLI validation used that installed Hermes executable and a separate local data root. Source-level validation used the pinned archive. No normal Hermes profile configuration was edited.

A single `/usr/bin/time -l` run of the complete isolated harness against installed Hermes took **1.23 seconds** and reported **71,450,624 bytes** maximum resident set size. This includes Hermes imports, the mock HTTP server, and its shutdown. It is a whole-process observation, not the plugin's incremental memory cost or a production benchmark.

The runtime researcher separately ran focused upstream tests: **116 passed, 1 failed**. The failure was a macOS portable-validator string assertion, diagnosed in [runtime notes](notes/hermes-runtime.md). It is separate from this plugin's passing checks.

## Reproduce

```sh
uv sync --only-group dev
.venv/bin/python scripts/fetch_hermes.py
.venv/bin/python -m pytest
.venv/bin/python scripts/spike.py
.venv/bin/python scripts/spike.py --answer deny
.venv/bin/python scripts/spike.py --answer timeout
.venv/bin/python scripts/spike.py --disabled
.venv/bin/python scripts/stage_plugin.py
HERMES_HOME="$PWD/.local/validation-home" hermes plugins validate "$PWD/.local/package/hermes-notify" --json
```

The package stage contains authored runtime, docs, and development files. Validate that directory, or a clean Git export, rather than the working folder with its downloaded Hermes source and disposable environments. The admission scanner traverses untracked research content too; `.gitignore` is not its exclusion policy.

`scripts/spike.py` creates and removes its own temporary profile. Mock mode overwrites an inherited Notify token with a public dummy sentinel, forces a loopback URL, and cannot send that sentinel to the real Notify server. Live credentials cannot be sent to the mock transport. Redirects and ambient HTTP proxies are disabled in the small client.

## The next live test

Only after Preetham authorizes one real push:

1. Use an existing Notify token with `notifications:send`, `interactions:create`, and `interactions:read`. Supply it through `NOTIFY_API_TOKEN` in the process environment, or populate that variable from the OS keychain. Never paste it into chat, command arguments, committed files, or logs. No particular keychain entry is assumed or created.
2. Optionally set `HERMES_NOTIFY_DEVICE_ID` to the intended phone. Without it, Notify uses the token's account routing and may reach more than one registered device.
3. Run `.venv/bin/python scripts/spike.py --live`.
4. Read the exact proposed print script in Notify and approve once. The terminal should report `hermes_approved: true`, `continued: true`, and `action_executed: false`. This proves that the real host received the phone's decision without performing a separate business action.
5. Record whether the phone displayed the prompt, the returned decision, and approximate latency. A successful create response alone does not prove delivery. A denied/expired request should never report approved.

The test changes no normal Hermes settings. It sends one interaction and may send a cancellation if the attempt fails while time remains. The prompt expires on Notify if local cancellation cannot complete. A separate denial or offline test would be another real push and needs to fit the later authorization.

## Deliberate spike limits

- No hosted App publishing, Live Activity, project inbox, reply-to-session tool, MCP adapter, CLI setup, webhook receiver, or Desktop panel is implemented. Those are specified in [DESIGN.md](DESIGN.md).
- No authenticated MCP inventory, real webhook delivery, pass exchange, real device rendering, or hosted App launch was exercised.
- A create timeout denies locally and leaves an unknown remote result to expire. The spike does not implement production outbox reconciliation or retry.
- The ledger prevents repeated consumption of a host request. It does not recreate an in-memory Hermes approval after a process crash. `consumed` records the plugin's decision emission, not successful execution of an action.
- Unload marks in-flight work canceled. A blocking socket operation can continue until its bounded timeout; Hermes has an independent deadline and discards late results. No forced thread termination is claimed.
- The runtime captures configuration, token, and profile storage at load. Reload after changes. Token rotation and concurrent profiles with different accounts need dedicated production tests.
- Ledger retention and a status/cleanup UI are not implemented. The isolated test profile is removed at exit; production retention must be bounded before general use.
- This is a source-pinned development proof, not a released-version compatibility guarantee or a completed hackathon entry.
