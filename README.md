# Hermes Pocket

Keep a Hermes release task on your phone through Notify by belweave. Open its release workspace, follow progress in a Live Activity, answer a precise approval, and return to the result after the release action finishes.

The local implementation includes a complete release App, a configurable Cloudflare Worker, six Hermes tools, native approval transport, written replies, signed webhook receipt, and an optional Desktop/Webapp companion. Notify's CLI is optional. The Python runtime has no third-party dependencies, model calls, or shell commands.

The full workflow passes locally with real Hermes, local workerd, and synthetic Notify responses. A separate authorized phone test also passed: one real approval returned Hermes's `once` decision. **Worker deployment, App sign-in, deep links and live progress remain unverified.** See [verification](docs/VERIFICATION.md) and the [85-second demo plan](docs/DEMO.md).

## Quick start (macOS, Linux, Windows)

You only need a Notify API token for phone notifications and questions. The Cloudflare Worker, release workspaces and Live Activities are optional extras.

1. Install and enable the plugin:

   ```sh
   hermes plugins install hermes-notify
   hermes plugins enable hermes-notify
   ```

2. Add your token to the Hermes secrets file (`~/.hermes/.env`, or `%LOCALAPPDATA%\hermes\.env` on native Windows):

   ```sh
   NOTIFY_API_TOKEN=ntf_...
   ```

   Create a token at [notify.belweave.ai](https://notify.belweave.ai/docs) with `notifications:send`, `interactions:create` and `interactions:read`.

3. Turn the runtime on in `config.yaml`, keeping your other settings:

   ```yaml
   plugins:
     entries:
       hermes-notify:
         settings:
           enabled: true
   ```

4. Start a new Hermes session and ask, for example, "Send me a Notify message when the tests finish" or "Ask me on my phone whether to deploy".

`notify_send`, `notify_ask` and `notify_replies` work on their own; `project` is optional and defaults to `hermes`. Phone approvals for Hermes commands are opt-in: add `security.approval.transport: notify` as shown in [Configure](#configure-after-live-setup-is-authorized).

The Python runtime uses only the standard library and runs the same on macOS, Linux and Windows. CI runs the test suite on all three.

## Install

The source repository is [Belweave/hermes-notify](https://github.com/Belweave/hermes-notify). This is a catalog candidate; installation by the bare catalog name becomes available only after maintainer acceptance. Use a Hermes build with the public approval transport API. The verified source revision is recorded below; no minimum released version is claimed.

For a published candidate, set `POCKET_COMMIT` to the complete 40-character reviewed commit from the [catalog entry](plugin-catalog/hermes-notify.yaml), then install into the intended Hermes profile without enabling it yet:

```sh
hermes plugins install Belweave/hermes-notify --ref "$POCKET_COMMIT" --no-enable
hermes plugins doctor hermes-notify --ci
```

For a maintainer's local checkout, run this from the repository root instead. It installs committed `HEAD`; uncommitted edits are not included:

```sh
hermes plugins install "file://$(pwd)" --ref "$(git rev-parse HEAD)" --no-enable
hermes plugins doctor hermes-notify --ci
```

Hermes warns about the local `file://` source. No remote is needed for that source. Configure credentials and settings as described below, then run `hermes plugins enable hermes-notify` and restart the Hermes session. Use `hermes plugins disable hermes-notify` and reload to stop the runtime. The Desktop contribution has a separate opt-in toggle. A source export from `scripts/stage_plugin.py` is for inspection and validation, not an argument accepted by `hermes plugins install`.

## Rehearse locally

Requires Python 3.11+, `uv`, and Node 22.23+ for Worker development. The harness installs no normal Hermes profile and reads no real credential.

```sh
uv sync --only-group dev
.venv/bin/python scripts/fetch_hermes.py
node worker/scripts/isolated.mjs ci
node worker/scripts/isolated.mjs build
.venv/bin/python scripts/release_demo.py
.venv/bin/python scripts/release_demo.py --answer deny
.venv/bin/python scripts/release_demo.py --answer timeout
```

On Windows, use `.venv\Scripts\python` in place of `.venv/bin/python`.

Each rehearsal loads the plugin through the real Hermes manager and calls its registered tools. A local Cloudflare runtime stores the published workspace. A signed synthetic microAuth pass opens a session and posts a written reply; Hermes retrieves it once, attributed to its original task. A separate simulated phone actor answers the real Hermes approval request. Only an approved action writes a local release receipt. The App and Live Activity then reach the final state.

Results go to `.local/demo/<timestamp>-<answer>/`: `summary.json`, `workspace.json`, `status.json`, and, for approval only, `release-receipt.json`. The simulated receipt is the rehearsal's release action, not a deployment. There is no live switch on this script. Both Python and workerd reject external runtime requests. Worker builds run with an empty home, a 512 MiB Node heap, bounded concurrency, and disk-backed storage.

## Use from Hermes

| Tool | Purpose |
| --- | --- |
| `notify_release` | Begin a version, update measured stages, inspect state, and record an explicit release-action result. |
| `notify_publish_app` | Publish the release workspace to the configured Worker, or register an existing HTTPS App. Repeat to resume an incomplete publication. |
| `notify_send` | Send a rich update grouped into the project's Notify inbox. |
| `notify_ask` | Ask a business question or request a written answer. This does not authorize a Hermes command. |
| `notify_replies` | Collect replies for the original run and session; optionally inject them when both Hermes and the operator permit it. |
| `notify_status` | Read bounded local status and unresolved operations without network traffic. |

Load the bundled skill explicitly with `skill_view("hermes-notify:notify-release-workspace")`; native plugin skills are namespaced and do not appear automatically in the system prompt. Hermes's native approval transport carries the immutable command request to Notify and returns only `once` or `deny`. Request IDs, digests, scope and deadlines stay under host control. An approval alone never marks a release shipped; the caller must first execute and verify the release action, then report its result. Written replies are task input, never execution permission.

The first publisher updates the complete release template and its data. It does not upload arbitrary generated code or deploy Worker infrastructure. Existing-URL registration validates the URL without fetching arbitrary destinations. Notify registration is separate from hosting.

## Configure after live setup is authorized

Use the [Worker setup guide](docs/WORKER.md) to prepare a host. `worker/wrangler.jsonc` enables `workers.dev`; set `worker_name` and `worker_subdomain` below to its hostname. Set `publisher_origin` instead for a custom HTTPS origin. The Worker needs a publisher secret and a verified, origin-specific owner subject before private browser access works. No first-visitor enrollment is provided.

After installing, merge these keys into the intended Hermes profile's `config.yaml`; preserve its other settings and existing enabled plugins. Keep the backend and optional Desktop toggle separate. The plugin is disabled by default; a configured profile can use:

```yaml
plugins:
  enabled: [hermes-notify]
  isolation: in_process
  entries:
    hermes-notify:
      settings:
        enabled: true
        worker_name: hermes-pocket
        worker_subdomain: your-account
        progress_enabled: true
        timeout_seconds: 120
        device_id: "" # Optional: one phone. Empty uses Notify account routing.
security:
  approval:
    transport: notify
approvals:
  mode: manual
  timeout: 120
```

Supply `NOTIFY_API_TOKEN` and `HERMES_NOTIFY_PUBLISH_TOKEN` through the intended Hermes profile's secret mechanism. The publisher value must match the Worker's `PUBLISH_TOKEN`. The plugin resolves declared secrets through Hermes at load; it does not read credential files, another CLI's login, or the OS keychain directly. Reload after rotation. Never place secrets in this YAML, model arguments, App assets or release notes.

For the complete workflow, the Notify token needs `notifications:send`, `interactions:create`, `interactions:read`, `apps:write`, `activities:write`, and `activities:read`. Webhook setup is an optional operator operation with separate service scopes. [Integration options](docs/INTEGRATIONS.md) covers official MCP and CLI use without making either a runtime dependency.

This build is checked against Hermes source `ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`. A minimum published version remains unverified. The approval transport requires the public in-process API; it is not a sandboxed plugin. Desktop SDK UI works through Desktop and its browser Webapp. Official native mobile plugin UI remains unverified, so Notify supplies the phone surface.

## Storage and network behavior

When enabled, explicit tools send selected workspace content and updates to Notify's fixed HTTPS Agent API and the operator's Worker. Native approvals send the host-redacted action. Ordinary progress uses one lazy worker with a bounded queue and at least five seconds between routine updates. Approval and terminal changes can flush sooner. There is no idle-task poller, inbound runtime port, telemetry or CLI subprocess. Delivery receipts distinguish queued, accepted and not accepted; they do not prove the phone displayed anything.

Hermes owns the profile data directory. `runtime.sqlite3` retains run/session mappings, publication intents, questions and replies; `approvals.sqlite3` prevents reuse of a native request; `status.json` exposes bounded state to the optional pane. Files use mode 0600. The journal caps rows at 2,000 and records at 64 KiB. Completed data expires on startup after 30 days by default. Active and uncertain operations are kept, and capacity exhaustion fails explicitly. The status snapshot is at most 480 KiB and omits session keys and raw commands. Selected summaries, notes and reply text are persistent content; the runtime rejects its known configured credentials, but callers must still choose appropriate content.

The Worker uses bounded SQLite Durable Object storage, bearer-authenticated publishing, same-origin browser writes, official microAuth verification, and raw-byte webhook signature checks. It never receives the agent API token or executes approvals. Public shell assets contain no private workspace data. [Worker limits and retention](docs/WORKER.md) describe replay windows and setup requirements.

Disable the plugin in its Hermes profile and reload to stop runtime work. Disable the optional Desktop contribution separately. Existing hosted data and Notify Apps are not deleted by unload; their removal is a separate operator action.

## Installation disclosures (catalog rule 13)

| Behavior | Scope |
| --- | --- |
| Third-party network calls | Enabled tools and approval/progress work call `https://notify.belweave.ai/api/agent` and the configured HTTPS Worker. They transmit selected workspace data, messages, replies and host-redacted approval requests. The Worker verifies sign-in keys only at `https://notify.belweave.ai/.well-known/jwks.json`. The App uses the official Notify bridge and its same-origin Worker API. User-opened artifact links may lead to other HTTPS sites. |
| Reads outside plugin data | The runtime obtains declared credentials, configuration and session identity through Hermes public APIs. The optional backend uses the public profile storage API to locate this plugin's `status.json`. It does not read other plugins' data, project files, transcripts, credential files, browser profiles or the keychain. Packaged source, fonts and SDK files are ordinary installation assets. |
| Shell commands and downloaded tools | Production Python, Worker and UI code run no shell command or CLI. Developer setup fetches a pinned Hermes source archive from GitHub and locked packages from the official npm/Python package registries. Local development uses Node, esbuild, workerd and optional Playwright Chromium; npm lockfile integrity hashes pin the native build packages. None of those executables is bundled in the plugin. The opt-in local rehearsal runs one fixed synthetic Python receipt action after the real host approval gate allows it. |
| Background work and waits | One lazy Python worker has a 64-entry queue; approval waits have two slots and host/plugin deadlines. Empty queues sleep without polling. Unload cancels and joins bounded work; explicit later tool calls resume durable recovery. App refreshes back off from 10 to 60 seconds, pause when hidden/offline, and stop for terminal runs. Desktop refreshes active state every 15 seconds while visible. Worker retention alarms run only for expiring state. |
| Stored credentials and content | Enabled registration captures the two Hermes-resolved tokens in process memory; the plugin does not write them to its journal or snapshot. `HERMES_NOTIFY_PUBLISH_TOKEN` is optional unless publishing to the Worker. Worker secrets are operator-managed bindings, never browser assets. SQLite stores workspace content, replies, correlation and receipt data, plus hashes of browser session/binding tokens and pass IDs. Raw sign-in JWTs are not stored. See the bounds above and [Worker retention](docs/WORKER.md#hard-bounds-and-contract-clarifications). |
| Telemetry and usage reporting | None is implemented by the plugin. Isolated Worker development disables Wrangler metrics and npm audit/funding requests. Hosting and Notify retain their own service behavior; no extra analytics endpoint is added. |

The optional nonsecret `HERMES_NOTIFY_TEST_URL` and `HERMES_NOTIFY_TEST_WORKER_URL` overrides accept only IPv4 loopback with the literal synthetic token `dummy`. Production credentials cannot redirect traffic through them. There is no self-updater, runtime code download, core patch, or replacement of a built-in tool. Updates use Hermes's reviewed package installation flow. The full disclosure and surface inventory is in the [local catalog PR draft](docs/CATALOG_PR.md).

Source is MIT licensed. The unchanged official Notify SDK is Apache-2.0 with retained third-party notices; Paper Mono uses the SIL Open Font License. See [LICENSE](LICENSE), [SDK provenance](worker/VENDOR.md), and the licenses beside each font. The UI is English-first.

## Development checks

```sh
.venv/bin/python -m pytest
node worker/scripts/isolated.mjs check
node worker/scripts/isolated.mjs test
node --experimental-vm-modules --test desktop/tests/plugin.test.mjs
```

The [verification guide](docs/VERIFICATION.md) also covers the App browser suite, backend tests and catalog admission check. The [submission checklist](docs/SUBMISSION-CHECKLIST.md) maps the official guidelines to local evidence and records the remaining publishing and filming steps. UI fonts are the official self-hosted Paper Mono WOFF2 files with their SIL Open Font License. [Research](docs/RESEARCH.md), [design](docs/DESIGN.md), [shared contract](docs/IMPLEMENTATION.md), and [milestones](docs/PLAN.md) record source evidence and the remaining live work.
