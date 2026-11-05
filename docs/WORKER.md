# Hermes Pocket Worker

The Worker implements [IMPLEMENTATION.md](IMPLEMENTATION.md) using framework-light JavaScript, Cloudflare static assets, and one SQLite Durable Object. It serves the App shell, authenticates publication and private browser reads, persists written replies, and records verified Notify webhook events for publisher reconciliation. It never sends a Notify message or executes an approval or reply.

Source is in [`worker/src`](../worker/src), the official browser adapter is [`app/public/auth.js`](../app/public/auth.js), and the deploy configuration is [`worker/wrangler.jsonc`](../worker/wrangler.jsonc). No deployment or account operation was performed.

## Local commands

Run these from the repository root:

```sh
node worker/scripts/isolated.mjs ci
node worker/scripts/isolated.mjs check
node worker/scripts/isolated.mjs test
node worker/scripts/isolated.mjs build
```

`ci` installs the exact lockfile with lifecycle scripts, audit, and funding requests disabled. Dependencies come from the public npm registry. The first lockfile was generated with the same wrapper's `install` command. The scripts use Node, not a globally configured Wrangler command.

Each invocation creates an empty temporary home and an allowlisted child environment. It isolates npm configuration/cache, Hermes state, Wrangler state, and XDG configuration, suppresses Wrangler metrics, limits Node's heap to 512 MiB, and limits esbuild's Go concurrency to two. Tests run one file at a time, with one workerd instance active at a time and disk-backed SQLite in the temporary directory. Cleanup removes the temporary home after the child exits. No stored Cloudflare credentials are loaded. No `deploy`, `login`, `whoami`, Notify CLI, or Notify mutation is invoked.

The tests generate an ephemeral P-256 key pair and use synthetic publisher/webhook values. A separate test entry supplies the public verification key through the official SDK's key resolver seam. Only that test entry has storage/failure controls. Production has no test-key binding, bypass flag, fixture route, or unsigned-session path. All runtime outbound requests are blocked by the harness, including the production-verifier negative test.

`build` copies the App-owned `app/public/` to `worker/dist/public/`, adds the official browser SDK and licenses, and bundles the Worker into `worker/dist/worker.mjs`. It rejects hidden files and symlinks in public assets. It does not invoke Wrangler. The App files must exist before building. Build output and dependencies are ignored inside `worker/`.

Validated locally: **22 passing tests**, syntax checks, all **135 vendored file hashes**, and the complete production bundle. The test suite itself builds and serves the current App through Miniflare's real static-assets binding. The bundle is about 78 KiB before compression; this is a local build measurement, not a deployed startup measurement.

## Operator configuration

The default configuration has `workers_dev: true`, `preview_urls: false`, `nodejs_compat`, the `POCKET` Durable Object binding, and the `v1` migration with `new_sqlite_classes: ["PocketStore"]`. Static assets use `run_worker_first: true` and `html_handling: "none"`, so `/projects/{project}` serves the shell without redirecting away from the project URL. Unknown API routes cannot fall through to HTML. The compatibility date is pinned to `2026-07-30`, which the pinned local workerd supports.

| Binding | Purpose |
| --- | --- |
| `PUBLISH_TOKEN` | Operator-provided secret shared with the Hermes publisher. Use 32 to 512 non-whitespace characters. The Worker compares SHA-256 digests using the runtime's constant-time primitive. Missing or short configuration authorizes no publisher. |
| `OWNER_SUBJECT` | Exact, previously verified origin-scoped microAuth `hk_` subject. Missing configuration grants no browser access, even if a caller knows an App ID. It is not an email address. |
| `NOTIFY_WEBHOOK_SECRET` | Saved generic reply-webhook signing secret, at least 32 characters. This is separate from the publish token and Notify agent token. Without it, the receiver returns 503. |
| `APP_ORIGIN` | Optional exact HTTPS origin, without a trailing slash, path, credentials, or query. Without it, only the incoming HTTPS `*.workers.dev` origin is accepted. |
| `ASSETS` | Static-assets binding configured by Wrangler. |
| `POCKET` | SQLite Durable Object namespace configured by Wrangler. |

No Notify agent API token or additional session-signing secret belongs in this Worker. Session cookies are random opaque values; only their hashes are persisted.

For a future authorized custom domain, provision the hostname and add a Wrangler custom-domain route, for example:

```json
{
  "workers_dev": true,
  "vars": { "APP_ORIGIN": "https://pocket.example.com" },
  "routes": [{ "pattern": "pocket.example.com", "custom_domain": true }]
}
```

For an existing zone route instead, use a route such as `pocket.example.com/*` with the operator's `zone_name`. `APP_ORIGIN` pins all App/API requests to that origin; the workers.dev URL then serves only the public health check. Do not include the production secret values in source or configuration examples. The selected origin must exactly match the origin registered with Notify. Origin changes require a corresponding registration/owner-subject review and fresh sign-in.

These are configuration instructions only. Domain provisioning, secret provisioning, Notify App registration, and deployment remain separate authorized operations. No custom hostname, token, account identifier, or owner identity was invented or discovered from local credentials.

## Publication and browser boundary

- `GET /api/health` is public and returns `{service: "hermes-pocket", schemaVersion: 1}`.
- `PUT /api/projects/{project}` requires the publisher bearer token and `{operationId, expectedRevision, workspace}`. All shared workspace fields are required, unknown fields are rejected, and the entire JSON request is limited to 64 KiB, including streamed bodies. The next revision must equal the expected revision plus one, including when the run changes.
- Revision comparison, workspace replacement, saved operation response, and App-change session invalidation happen in one SQLite transaction. Different bytes with a retained operation ID produce `409 operation_conflict`. A revision race produces `409 revision_conflict`. Exact retained retries return the original response and the original `unchanged` value. New writes have `unchanged: false`; this field is not a new receipt for a replay.
- `GET /api/projects/{project}` requires either the publisher or a browser session for that exact project, registered App ID, origin, and configured owner. Responses have `Cache-Control: private, no-store`; no public fixture or data endpoint exists.
- `GET /api/projects/{project}/config` exposes only `{project, appId}`. Unknown projects return 404.
- `GET /projects/{project}` returns the public App shell with no private release data. Static responses carry a restrictive same-origin CSP, no-store, nosniff, and no-referrer headers. No CORS permission is granted.

The Worker stores the latest workspace only. Retained operation responses supply limited publication history. Project, run, revision, and schema validation follows the shared contract. Extra defensive bounds are listed below for parent/client agreement.

Errors are `{error: "safe_lowercase_code", code: "SAFE_UPPERCASE_CODE"}` with the appropriate HTTP status. The uppercase machine code is compatible with the Python client's constrained error-metadata reader. No input values, secrets, SQL errors, or verifier details are echoed.

## Official browser-bound microAuth

`connect(project)` imports the unmodified official browser SDK, checks that microAuth is available and the project has an App ID, requests no optional profile fields, performs the SDK's challenge/session exchange, then verifies the server session. It returns `{authenticated: true, project}` or throws a safe message. An ordinary browser or unsupported Notify bridge gets a sign-in explanation; it receives no alternate private-data access.

`POST /auth/{project}/challenge` accepts `{}` from the exact origin and sets a random `__Host-hp-binding-{project}` cookie. The official server SDK generates the challenge, and SQLite binds it to that cookie hash, project, App ID, origin, and a two-minute expiry. `POST /auth/{project}/session` accepts `{token}` and verifies the official ES256 pass, protected type, issuer, exact audience, App ID, nonce, issue/expiry times, and required claims. The verifier uses only `https://notify.belweave.ai/.well-known/jwks.json`. The browser never controls the key endpoint.

Nonce consumption is a single conditional `DELETE ... RETURNING`. Only one concurrent completion can consume it. The Worker separately retains a hash of the verified `jti` until pass expiry, requires the configured owner, and issues a project-specific opaque session cookie. Both binding and session cookies use `__Host-`, `Path=/`, `Secure`, `HttpOnly`, and `SameSite=Strict`.

`GET /auth/{project}/session` returns `{ok: true, authenticated: true, project}` for a valid session, otherwise 401. `DELETE` requires same-origin intent, deletes the session and pending browser binding, and clears both cookies. Every browser write requires an exact `Origin` header and rejects `Sec-Fetch-Site: cross-site`. Private browser reads reject an explicitly different origin or cross-site fetch metadata. Publisher credentials never substitute for a browser session when submitting a human reply.

Sessions last one hour with no sliding extension. Changing a project's App ID deletes its sessions and challenges. Changing or removing `OWNER_SUBJECT` makes nonmatching sessions unusable immediately. Notify consent revocation alone does not revoke this website's existing cookie; explicit logout, owner configuration, App registration changes, and bounded expiry are the local controls. There is intentionally no public owner-enrollment endpoint. The operator must already have a verified subject for this origin.

## Human reply and webhook queues

The browser submits `{id, runId, text}` to `POST /api/projects/{project}/replies`. New replies must match the current run. IDs are scoped to the project; a retry with the same ID, run, and text returns its original `{id, cursor, accepted: true}` receipt. Changed content with the same retained ID returns 409. A previously accepted retry can still return its receipt after the run changes, but it cannot append input to the new run.

The publisher reads `/api/projects/{project}/replies?after=0` in ascending cursor order, up to 100 records and 96 KiB of UTF-8 JSON per page. Complete records are paged without skipping oversized combinations. Persist each receipt in the local Hermes journal before calling `/replies/ack` with `{ids: [...]}`. Acknowledgement clears stored reply text immediately and retains a deduplication receipt. Repeated or unknown acknowledgement IDs are harmless no-ops. The response is `{acknowledged: ids}`. Reply text is task input, never a command or host approval.

`POST /api/notify/webhooks` implements the **saved generic reply webhook**, not Slack presets, per-question callbacks, or inbound service URLs. It requires:

1. `X-Notify-Signature: t=<unix-seconds>,v1=<hex-HMAC-SHA256>` over `timestamp + "." + exact raw body bytes`.
2. Signature age from zero through 300 seconds, checked again after reading/verifying the body.
3. A bounded `X-Notify-Delivery-Id` and the documented nested `interaction` envelope for `interaction.answered`, `interaction.expired`, or `interaction.canceled`.

Delivery IDs deduplicate exact raw body hashes. Outcome identity is `(type, interaction.id)`; a hash of kind, status, response, and respondedAt detects conflicting outcomes. Distinct delivery IDs for the same outcome create no second event. Event insertion and delivery receipt insertion are atomic. Database or capacity failure returns 503 with no false accepted receipt. No webhook body, signature, response text, or secret is persisted; only hashes and the reconciliation identifiers are retained.

Publisher-only `/api/events?after=0` returns at most 100 `{id, cursor, interactionId, type}` events. `/api/events/ack` accepts `{ids: [...]}` after local journal persistence. A received event is a reason for Hermes to fetch authoritative Notify interaction state, compare the saved scope/digest, and reconcile its own pending request. The Worker cannot grant permission or mark an action complete.

Cursors are durable, monotonically increasing SQLite integers. Reply cursors are global across projects, so gaps are normal. Empty pages return the supplied cursor. Poll from a journaled cursor, or from zero during recovery; unacknowledged records remain available. A cursor is not an acknowledgement.

## Hard bounds and contract clarifications

One named object (`hermes-pocket-v1`) bounds the whole installation rather than creating unlimited objects from public project paths. All table names and SQL fragments are fixed in source; incoming values use bound parameters.

| Data | Bound and retention |
| --- | --- |
| Projects | 128 latest workspaces, each derived from a request no larger than 64 KiB. Projects are not automatically deleted. |
| Publication operation hashes | 4096 globally, seven days after publication. |
| Full operation responses | Latest 32 per project, at most 256 globally, and at most seven days. |
| Pending replies | 128 per project, 1024 globally; never silently evicted. |
| Acknowledged reply receipts | 4096 globally, seven days after ack, with text erased. |
| Pending webhook events | 1024 globally; never silently evicted. |
| Acknowledged event receipts | 4096 globally, seven days after ack. |
| Delivery receipts | 8192 globally, seven days after first receipt. |
| Pending challenges | 16 per project, 256 globally, two-minute expiry. |
| Sessions | 8 per project, 128 globally, one-hour expiry. |
| Used pass IDs | 512 globally, retained only until the verified pass expires. |
| Queue pages and ack batches | 100 records/IDs; reply pages also fit 96 KiB of UTF-8 JSON. |

Capacity errors preserve accepted pending data and return 503, or 429 for authentication capacity. Expiry is purged on requests and by a Durable Object alarm scheduled for the earliest retention deadline. With no expiring records, the alarm is removed. This introduces no inactive-task poller.

The shared contract leaves these points open. Parent/client changes should explicitly adopt or revise them:

- **Bounded replay horizon:** exact publication responses can be replayed only while the full response is retained. An older retained operation hash returns `409 operation_response_expired`; reconcile with authenticated GET. A retry after the seven-day hash window still cannot apply its original revision again, because revisions only advance. Operation IDs must never be deliberately reused. Infinite replay and bounded history cannot both be guaranteed.
- **Post-ack dedup horizon:** reply/outcome receipts last seven days after ack, and delivery receipts last seven days after first receipt. Later duplicates can reappear. Hermes must keep its own durable receipt/outcome correlation and must never execute an event directly.
- **`unchanged` on exact replay:** the original `unchanged: false` is preserved to honor saved-response replay. If callers require `unchanged: true` on retries, that requires an explicit contract revision.
- **Additional input bounds:** operation/reply/ack IDs use 1 to 128 letters, digits, underscores, or hyphens. App IDs use `app_` followed by 1 to 128 of those characters. Artifact URLs are at most 2048 characters and cannot embed credentials, whitespace, or backslashes. Approval request IDs are at most 128 characters, digests 256, and titles 80. Text bounds count Unicode code points and reject ASCII controls except newline and tab. Reply and ack bodies are limited to 16 KiB, auth bodies to 36 KiB, webhook/publication bodies to 64 KiB. Saved webhook response strings are at most 8000 characters. Validation failures and unknown routes contain no incoming values.
- **Owner provisioning:** configure a verified origin-specific `OWNER_SUBJECT` before browser use. This implementation does not enroll the first visitor or disclose an unconfigured visitor's identity. Any enrollment tool needs its own explicit design and authorization.
- **Registration is publisher-owned:** the publisher places the registered Notify App ID in a new workspace revision. The Worker verifies passes against that ID but cannot itself query account registration state without an agent token, which the contract excludes.

Integration aligned Python's workspace validation with the App and Worker: Unicode code points and a 256-character approval digest bound. Pending-publication recovery recognizes `OPERATION_RESPONSE_EXPIRED` and `REVISION_CONFLICT`, then reconciles only an authenticated GET matching the exact pending content and expected next revision. The local release rehearsal now exercises Python publication, synthetic signed microAuth, deduplicated browser replies and final workspace state against actual workerd. No alternate route or shared field was needed.

## Verification and remaining live work

Tests cover publication replay and conflicting bytes, racing revisions, transactional rollback, schema/body limits, real ES256 verification through the official SDK, claim and signature tampering, single-use challenge races, pass-ID reuse, unconfigured/wrong owners, project separation, expiry/logout/App changes, bounded authentication, same-origin replies, old-run replies, ack deduplication, queue pagination/capacity, raw webhook signatures/freshness, both webhook deduplication levels, SQLite failure and restart persistence, production assets, and absence of production test paths.

Still unverified: a deployed Worker/migration, actual Cloudflare account limits and billing, remote JWKS key rotation, a real Notify bridge/consent exchange and cookie behavior on the target phone, saved-webhook live headers/retries, operator owner provisioning, and a full Python-to-deployed-Worker round trip. The local Worker never fetched live JWKS in tests and never sent anything to Notify. The App's visual/interaction QA and the Python runtime belong to their respective agents.

## Public references

- Notify's [App and microAuth contract](https://notify.belweave.ai/docs/web-apps) and [saved-webhook signature contract](https://notify.belweave.ai/docs/notification-api).
- Installed Notify Apps microAuth and Automation receiver skills, read alongside the public documentation. No skill-triggered sends were performed.
- [Official SDK provenance and licenses](../worker/VENDOR.md).
- Cloudflare [SQLite Durable Object transactions](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/), [static-assets configuration and bindings](https://developers.cloudflare.com/workers/static-assets/binding/), and [custom domains](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).
