# Release workspace implementation contract

The approved first product is a full release workspace App, hosted by a configurable Cloudflare Worker. The Worker serves its HTML, JavaScript, Paper Mono, and persistent project data. Publishing a workspace creates or updates a version of that App's data and registers its stable URL with Notify. Existing hosted Apps can also be registered. Arbitrary generated code upload is outside this first template's publisher contract.

The local build must send no real Notify request, read no real credential, and perform no deployment. Tests supply synthetic credentials and isolated Hermes/Wrangler homes. The Notify CLI is optional. The separate authorized one-prompt phone test has since passed. A complete live rehearsal still needs hosting setup, additional App/activity scopes and its own authorization.

## Shared workspace shape

```json
{
  "schemaVersion": 1,
  "project": "release-demo",
  "runId": "run_example",
  "revision": 1,
  "name": "Release workspace",
  "version": "1.0.0",
  "status": "running",
  "stage": "Checks",
  "summary": "Checking the release candidate.",
  "progress": 0.5,
  "checks": [{"label": "Unit tests", "status": "passed"}],
  "artifacts": [{"label": "Release notes", "url": "https://example.com/releases/1.0.0"}],
  "notes": "Release notes and rollback instructions.",
  "updatedAt": "2026-11-05T01:00:00Z",
  "appId": null,
  "approval": null
}
```

Required fields are all shown; `appId`, `approval`, and `progress` can be null. Status is `preparing`, `running`, `awaiting_approval`, `approved`, `shipped`, `denied`, `failed`, or `canceled`. A check's status is `pending`, `running`, `passed`, or `failed`. An approval, when present, is `{requestId, digest, title, status}` with status `pending`, `approved`, `denied`, `expired`, or `canceled`. The digest is for correlation, never a permission granted by the App. No raw command, token, session key, or transcript belongs in this document.

Project slugs match `[a-z0-9][a-z0-9-]{0,63}`; run IDs are 1 to 128 letters, digits, underscores, or hyphens. Names, versions, stages and check/artifact labels are at most 80 Unicode code points; summaries at most 500; notes at most 8000; approval digests at most 256. At most 20 checks and 20 HTTPS artifact links are allowed. Progress is measured work from 0 to 1, or null. Local revisions increase for each mutation; Worker revisions increase for each accepted publication. Coalescing means they can differ. Limit workspace request bodies to 64 KiB, encoded as UTF-8.

## Worker HTTP boundary

The Worker uses a constant-time bearer check against its configured `PUBLISH_TOKEN` for all publisher requests. The Python client reads the matching `HERMES_NOTIFY_PUBLISH_TOKEN` through Hermes only when explicitly enabled. Production origin defaults to the incoming HTTPS workers.dev origin; `APP_ORIGIN` can pin a custom HTTPS origin. The host base URL is operator configuration, never a model-supplied endpoint. Wrangler sets `workers_dev: true`; no deploy command is executed in this phase.

| Request | Contract |
| --- | --- |
| `GET /api/health` | Public `{service: "hermes-pocket", schemaVersion: 1}`. |
| `PUT /api/projects/{project}` | Publisher sends `{operationId, expectedRevision, workspace}`. First revision expects 0. Return `{workspace, revision, unchanged}`. Atomically reject conflicts; the same operation ID and bytes replay a retained response. Keep at most 32 responses per project and 256 globally for up to seven days. Expired responses return `OPERATION_RESPONSE_EXPIRED`; older operations can return `REVISION_CONFLICT`. Reconcile only an authenticated GET matching the exact pending workspace at the expected next revision. |
| `GET /api/projects/{project}` | Publisher or matching authenticated browser gets `{workspace, revision}`; no public private-data path. |
| `GET /api/projects/{project}/config` | Public `{project, appId}` for starting sign-in, with no release data. |
| `GET /projects/{project}` | Full App shell. It contains no private release data. |
| `POST /api/projects/{project}/replies` | Matching browser session and same-origin request send `{id, runId, text}`. Text maximum 2000. Deduplicate ID and reject an old run. Return `{id, cursor, accepted: true}`. |
| `GET /api/projects/{project}/replies?after=0` | Publisher-only, bounded `{replies: [{id, cursor, runId, text, createdAt}], cursor}`. |
| `POST /api/projects/{project}/replies/ack` | Publisher-only `{ids: [...]}` acknowledges persisted local receipt. |
| `POST /api/notify/webhooks` | Notify saved reply-webhook format, raw-byte `X-Notify-Signature` verification with `NOTIFY_WEBHOOK_SECRET`, five-minute freshness, delivery/outcome deduplication. No action is executed. |
| `GET /api/events?after=0` | Publisher-only `{events: [{id, cursor, interactionId, type}], cursor}` for reconciliation through authoritative Notify REST. |
| `POST /api/events/ack` | Publisher-only `{ids: [...]}`. |
| `/auth/{project}/challenge`, `/auth/{project}/session` | Official microAuth challenge and session exchange, same-origin writes and atomic nonce consumption. Session GET and DELETE check/logout. Validate the project's registered App ID, exact origin, and configured `OWNER_SUBJECT`; an unconfigured owner gets no private data. |

Worker persistence uses a SQLite Durable Object for ordered publication, challenge consumption, reply cursors and deduplication. Keep bounded history and purge expired authentication state. No agent API token belongs in the Worker or browser. Use the official microAuth SDK and preserve its license. Tests inject verification keys and synthetic sessions through test-only dependency seams, not a production auth bypass.

The browser imports `connect(project)` from `/auth.js`; it handles the official SDK's challenge/session exchange and returns an authenticated result or throws a safe message. The UI reads `/auth/{project}/session`, then project data. It sends written replies, never approval decisions. Approval is answered only in Notify's native interaction.

## Hermes boundary

Python owns a profile-local SQLite journal and writes a bounded, secret-free `status.json` in `ctx.state.data_dir` for the optional Desktop pane. Snapshot shape: `{schemaVersion: 1, configured: bool, runs: [workspace...], pending: [{requestId, title, status}], deliveries: [{project, state, message}], updatedAt}`. Backend tools and the native approval transport work without Desktop or Notify CLI.

Explicit tools are `notify_release` (begin/update/finish/status), `notify_publish_app`, `notify_send`, `notify_ask`, `notify_replies`, and `notify_status`. They begin/update/finish a release, publish its App or register an existing URL, send a rich update, ask a business question, collect replies, and inspect state. Hermes retains actual command execution and approval policy. Fast observers bind host request ID/digest to the original session/run; a bounded worker delivers progress. The approval transport preserves the exact immutable request and returns only `once` or `deny`. A phone answer cannot itself mark a release shipped; Hermes records completion after the release action reports success.

Reply retrieval records the original run and session. It returns attributed input to the calling task, or uses the public session-injection API only when that API permits the same session. Replies never become commands or host permissions. Webhooks wake reconciliation; polling remains the default behind NAT. No inactive-task poller or mandatory inbound port is introduced.

## Parallel ownership

- Worker task owns `worker/`, `app/public/auth.js`, and `docs/WORKER.md`.
- App task owns `app/` except `public/auth.js`, including static assets, UI tests, and design notes.
- Hermes task owns `desktop/`, `dashboard/`, `skills/`, and `docs/notes/hermes-features.md`.
- Runtime task owns `__init__.py`, `hermes_notify/`, `tests/`, `plugin.yaml`, and `scripts/mock_notify.py`. It may add runtime notes under `docs/notes/`.
- Root owns all other top-level scripts, shared docs, packaging, integration, and all commits.

All authors read this contract before editing. Propose necessary contract changes in the task result; do not silently invent a competing field or route.
