# Local verification

The complete release workflow is implemented and rehearsed locally with synthetic Notify responses. Hermes's loader, tool registry and approval gate, and Cloudflare's local Worker runtime are real. A separate authorized one-prompt phone test passed on November 4: Notify accepted it for one device, and the human approval returned Hermes's `once` decision with request/ledger correlation verified. Send time was 0.838 seconds and round trip 68.795 seconds. This establishes native approval delivery only; **deployed App sign-in, live progress and a real release shipment remain unverified.** The build itself made no live Notify calls or real credential reads.

## Results on November 4, 2026 ET

| Check | Result | What it establishes |
| --- | --- | --- |
| Python suite | 124 passed | Native approval safety, registered tools, profile/session binding, durable intents, publication recovery, progress/fallback, replies, bounded storage and unload. |
| Worker suite | 22 passed | Actual workerd and SQLite, official SDK verification with synthetic keys, conflicts/replay, authentication, signature/freshness checks, reply/event deduplication, storage failure/restart and production assets. |
| App browser suite | 42 passed | Chromium scenarios for phone/desktop layouts, safe rendering, replies, retries, stale runs, expiry, offline/visibility handling and refresh pacing. |
| Desktop SDK suite | 9 passed | Actual pinned SDK exports/import rules, registration, profile/connection races, cleanup, link policy and official font integrity. |
| Desktop backend suite | 27 passed | Actual FastAPI route and public Hermes storage contract, profile selection, read-only behavior, file bounds, malformed snapshots, symlinks and safe errors. |
| Skill validation | Passed | Packaged release skill structure; native entrypoint explicitly registers it. |
| Full package admission | All 16 checks passed | Manifest, dependency declaration, isolated registration, declared capabilities, security scan, core-override check and Desktop surface. One development-harness import warning, described below. |
| End-to-end local release | Approve, deny and timeout passed | Python publisher to real local Worker, synthetic microAuth and reply, real Hermes approval, conditional action execution, final workspace and activity. |

The tested Hermes source is `ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`, recorded with its archive checksum in [SOURCES.json](SOURCES.json). The earlier approval-only spike also ran against installed source `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. The complete build has not been validated against every released Hermes version, and no minimum published version is claimed.

## Full local release

`scripts/release_demo.py` creates a temporary Hermes profile and loads the authored plugin through actual discovery. It calls the registered tool handlers, not a parallel imitation of the runtime. A separate loopback Notify fixture records Apps, rich pushes, interactions and Live Activities.

The Python publisher calls the real Worker service running in local workerd with disk-backed SQLite. A test-only entry injects an ephemeral P-256 verification key into the official SDK seam. The production entry has no test-key binding or auth bypass. The simulated phone uses a real one-use challenge, signed ES256 pass, secure-cookie session, private workspace read and same-origin reply. Reposting the same reply ID creates one receipt; Hermes returns it once to the original task as untrusted input.

The real `check_execute_code_guard` requests permission for an exact local receipt-writing script. A separate test actor approves, denies, or gives no answer. Before the gate returns and the host observer settles, the receipt does not exist. On approval only, the harness runs that script, verifies its successful exit and output, then records shipped. Deny and timeout execute no action and leave the workspace denied. All three cases end the mock activity and confirm the Worker's final state.

The harness uses synthetic tokens, blocks non-loopback Python connections, blocks workerd outbound services, and disables Miniflare's public CF metadata fetch. The Worker process gets an empty home and an allowlisted environment. It has no live mode. Outputs are `.local/demo/<timestamp>-<answer>/summary.json`, `workspace.json`, `status.json`, and an approval-only `release-receipt.json`. The outputs contain synthetic release data only. No external release is implied.

## Reproduce

From the repository root:

```sh
uv sync --only-group dev
.venv/bin/python scripts/fetch_hermes.py
.venv/bin/python -m pytest
node worker/scripts/isolated.mjs ci
node worker/scripts/isolated.mjs check
node worker/scripts/isolated.mjs test
node worker/scripts/isolated.mjs build
.venv/bin/python scripts/release_demo.py --answer approve
.venv/bin/python scripts/release_demo.py --answer deny
.venv/bin/python scripts/release_demo.py --answer timeout
node --experimental-vm-modules --test desktop/tests/plugin.test.mjs
.venv/bin/python scripts/validate_package.py
```

For the App, follow [app/VERIFICATION.md](../app/VERIFICATION.md): install the pinned dev dependencies, provide Playwright Chromium, and run `npm run check` and `npm test` from `app/`. Tests use one browser worker and a loopback static server. API/auth fixtures are test-route interceptions, never shipped production paths.

For the backend, create `desktop/tests/.venv`, install [desktop/tests/requirements.txt](../desktop/tests/requirements.txt), then run:

```sh
desktop/tests/.venv/bin/python -m pytest -q dashboard/tests
desktop/tests/.venv/bin/python desktop/tests/catalog_check.py
```

The Worker wrapper uses an empty temporary home and pinned dependencies with install scripts disabled. Build copies the static App and licensed browser SDK, then bundles the Worker with esbuild. It does not invoke `wrangler deploy`, login or account commands. The official SDK's 135 recorded file hashes match the release archive. Paper Mono's WOFF2 files and licenses are retained in App and Desktop assets. The runtime and rehearsal do not invoke the Notify CLI.

## Package validation and limits

`scripts/stage_plugin.py` creates `.local/package/hermes-notify` from authored sources, docs, UI and Worker code. It excludes virtual environments, dependencies, build output, local test artifacts, local databases, logs, credential-file patterns and Wrangler state; it rejects source symlinks. The current package is about 3.1 MB before compression. The static Worker App assets are about 168 KiB and the Worker bundle about 80 KiB. These are disk sizes, not memory measurements or transfer budgets.

`scripts/validate_package.py` runs pinned Hermes admission checks against that complete stage with an empty home and registration environment. The machine-readable result is `.local/package-validation.json`. All 16 checks pass. The warning names development-only scripts importing the real manager, guard context or admission checker. Those scripts are not loaded by the plugin runtime. The runtime-only companion package also passes; its receipt is [desktop/tests/catalog-result.json](../desktop/tests/catalog-result.json).

The validator reports `in_process` because native approval transports hold a live request/response channel. This is intentional and must not be presented as host isolation. The lightweight validation environment emits optional builtin-import diagnostics for absent `requests`/`httpx`; its collision scan does not replace booting a complete production Hermes installation. The backend suite emits Starlette's httpx deprecation warning; Node reports expected VM/type-strip experimental warnings.

`notify_release(action="finish", result="succeeded", ...)` records the caller's explicit action result. It is not an independent verifier of arbitrary release commands. The bundled skill requires the actual command and output check first, and the rehearsal proves that ordering. Phone approval cannot by itself set shipped. Unknown external write results remain visible for operator reconciliation rather than creating duplicate work.

## Remaining live checks

- The separate one-prompt test is complete. Verify the configured token has the additional App and activity scopes before a later full rehearsal; the three approval scopes do not establish that.
- A later authorized Worker deployment, migrations, publisher secret and verified owner subject for the exact HTTPS origin. The local publisher updates the complete release template; it does not deploy infrastructure or upload arbitrary generated code.
- A real Notify deep link, consent/pass exchange, secure-cookie session, App rendering, approval response and reply on the target phone. Synthetic signatures prove server behavior, not the actual phone bridge.
- Live Activity capability, readiness, visible updates and fallback on the chosen phone. Provider acceptance or queued delivery is not proof of display.
- Saved webhook live headers/retries, production JWKS rotation, host authentication and a live Desktop/Webapp renderer. The Desktop tests verify source contracts and behavior through a harness; they do not launch the full application.
- The under-90-second recording, clean production install, public repository, catalog PR and entry submission. These remain later authorized actions. The [85-second runbook](DEMO.md) is ready locally.

The historical one-prompt helper `scripts/spike.py --live` still requires explicit authorization for any new send and an injected token. It is not called by any build or test above. The complete phone rehearsal sends more than that single prompt and needs its own authorization.
