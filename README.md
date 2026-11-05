# Hermes x Notify

Local exploration for a Hermes plugin that puts useful apps, progress, and decisions on your phone through Notify by belweave.

This repository contains research, a proposed product design, and a working approval transport spike. Hosted App publishing, Live Activities, project routing, MCP integration, and webhook receipt are design work for the next phase. They are not implemented in this spike.

- [Research](docs/RESEARCH.md)
- [Design and demo](docs/DESIGN.md)
- [Milestones through November 11](docs/PLAN.md)
- [Verification and live-test instructions](docs/VERIFICATION.md)

## Run the local spike

Requires Python 3.11 or newer and `uv` for the development environment. The plugin itself uses only Python's standard library and Hermes's public plugin context.

```sh
uv sync --only-group dev
.venv/bin/python scripts/fetch_hermes.py
.venv/bin/python scripts/spike.py
.venv/bin/python scripts/spike.py --answer deny
.venv/bin/python scripts/spike.py --answer timeout
.venv/bin/python -m pytest
```

`fetch_hermes.py` downloads the pinned public Hermes source and verifies the archive hash. It does not set up a Git remote. The spike uses a temporary Hermes profile, loads the real plugin through Hermes discovery, and enters Hermes's real code approval gate. A loopback HTTP mock simulates Notify and a separate test actor supplies the phone response. It does not run the proposed code.

No real credentials are used in mock mode. Mock mode replaces any inherited Notify token with a dummy value and only connects to `127.0.0.1`. The user's normal Hermes profile is untouched.

## Plugin behavior

The plugin registers the `notify` approval transport. It creates one Notify approval interaction, waits within the host deadline, and returns `once` only for a matching, confirmed `approved` / `approve` response. It binds both the Hermes request digest and Notify action digest. SQLite records one-time consumption before returning permission. Denial, timeout, malformed replies, repeated requests, and transport errors grant no permission.

The transport is off by default. For an explicitly authorized installation, settings belong under:

```yaml
plugins:
  enabled: [hermes-notify]
  isolation: in_process
  entries:
    hermes-notify:
      settings:
        enabled: true
        timeout_seconds: 120
        device_id: "" # Optional ID for one phone; empty uses account routing.
security:
  approval:
    transport: notify
approvals:
  mode: manual
  timeout: 120
```

Supply `NOTIFY_API_TOKEN` through the environment, optionally populated by an OS keychain. The plugin resolves it through Hermes's public `agent.secret_scope.get_secret` API during registration so another profile's token cannot be substituted by a later worker. It reads no credential files or keychain directly. Required scopes are `notifications:send`, `interactions:create`, and `interactions:read`. Never place a token in this YAML, a tool argument, or an app bundle. The Notify CLI is not required.

The tested Hermes source commit is recorded in [SOURCES.json](docs/SOURCES.json). Older builds without `register_approval_transport` are refused. A release version floor still needs confirmation; this spike does not claim compatibility with every Hermes version.

## Network and storage

When enabled and selected for an approval, the plugin sends the host-redacted action and description to `https://notify.belweave.ai/api/agent/interactions`, reads that interaction's wait endpoint, and may cancel it on failure. It uses TLS verification, refuses redirects, and ignores ambient HTTP proxies. Registration performs no network I/O. There is no idle poller, telemetry, subprocess, listening server, or CLI dependency in the plugin runtime. Hermes invokes the callback on a worker; the bridge permits two concurrent waits and caps each wait by its own timeout and the host deadline.

The plugin writes `approvals.sqlite3` inside Hermes's profile-owned `ctx.state.data_dir`. It stores request/interaction IDs, digests, outcome state, and creation time; it does not store the token or full prompt. The database file is restricted to its owner. This spike has no automatic record retention policy yet. The declared token is read once through Hermes during registration and retained in memory until unload; reload after rotating it. The plugin reads no files outside its package and profile data through its own code.

Development helpers have separate behavior: the source fetcher downloads one checksum-pinned public Hermes archive into `.local/`; the mock harness opens a temporary loopback server and profile and removes them on exit. Only the explicit `--live` harness mode sends a real Notify interaction. Full-tree catalog validation reports the harness's internal Hermes imports as a warning; the runtime entrypoint uses public APIs. See [verification](docs/VERIFICATION.md) for that distinction and the remaining limits.

## One later live test

The live test is prepared but has not been run. After explicit authorization, supply the token through the environment and run:

```sh
.venv/bin/python scripts/spike.py --live
```

It sends one approval for a harmless proposed `print` script, waits up to two minutes, and reports Hermes's decision. Even after approval, it does not execute code. Set `HERMES_NOTIFY_DEVICE_ID` to target one phone. See the verification document for expected outcomes and limits.
