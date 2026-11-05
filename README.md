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
uv run --no-project python scripts/fetch_hermes.py
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

Read `NOTIFY_API_TOKEN` from the environment, optionally populated by an OS keychain. Required scopes are `notifications:send`, `interactions:create`, and `interactions:read`. Never place a token in this YAML, a tool argument, or an app bundle. The Notify CLI is not required.

The tested Hermes source commit is recorded in [SOURCES.json](docs/SOURCES.json). Older builds without `register_approval_transport` are refused. A release version floor still needs confirmation; this spike does not claim compatibility with every Hermes version.

## One later live test

The live test is prepared but has not been run. After explicit authorization, supply the token through the environment and run:

```sh
.venv/bin/python scripts/spike.py --live
```

It sends one approval for a harmless proposed `print` script, waits up to two minutes, and reports Hermes's decision. Even after approval, it does not execute code. Set `HERMES_NOTIFY_DEVICE_ID` to target one phone. See the verification document for expected outcomes and limits.
