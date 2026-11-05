# Python runtime handoff

Implemented locally in `__init__.py`, `hermes_notify/`, `plugin.yaml`, `scripts/mock_notify.py`, and `tests/`. No new runtime dependencies, subagents, commits, live Notify calls, credential-store reads, deployment, remote writes, or Notify changes. Tests use isolated Hermes homes, synthetic tokens and IPv4 loopback HTTP; the test process rejects other network connections. Root retains packaging and shared-document ownership.

## Verification

Run from the repository root:

```sh
.venv/bin/python -m pytest
```

Final result: **119 passed**. This includes the original 36 approval-spike tests, 77 runtime behavior cases, and 6 registration/schema cases. The registration probe loads the actual plugin with `.local/hermes-source`, dispatches all six tools through the real registry, then verifies removal on unload. The original spike still exercises real Hermes approval gating for approve, deny, timeout, and disabled configurations. No proposed release command is executed by these probes.

The added tests cover publication ordering; Worker replay after a lost response and expiry of retained receipts/hashes; exact authenticated reconciliation without overwriting newer content; Unicode code-point and native UTF-16 limits; registration failure/restart; App binding failure before announcement; ambiguous push suppression; exact retry after scope rejection; cross-runtime atomic send claims; profile/session isolation and session resets; schema constraints; wrong interaction/activity IDs; stale revisions and replies; on-demand webhook reconciliation; record-before-ack and deduplication; authorized same-session injection; native host decision correlation and restart expiry; measured progress, delayed coalescing, sequence conflicts, capacity/unsupported fallback and logical end; queue bounds; retention; missing configuration; rate limits; and unload.

Outgoing App registration, notification, interaction, activity start/update/end bodies are validated against the saved deployed OpenAPI request schemas in `tests/fixtures/notify-runtime-contract.json`. The fixture was extracted from `.local/research/notify/openapi.json`, without descriptions or any schema changes. The existing complete approval response fixture remains intact. The supplied verified MCP inventory was consulted; production uses REST and does not call MCP.

`git diff --check` passes for the reviewed working tree. Parent should rerun the suite after integration changes.

## Runtime surface

- `notify_release`: `begin`, `update`, `finish`, `status`. `begin` requires project/version and binds host-provided session identity. Updates and finish require `expected_revision`. Only finish with `result: succeeded|failed|canceled` and `result_summary` records the explicit action result. An approval alone cannot record shipped. An awaiting, denied, failed or canceled run cannot be finished successfully. Notes, checks, HTTPS artifact URLs, stage and measured progress follow the shared workspace shape.
- `notify_publish_app`: publishes the fixed release-workspace data to the configured Worker, or registers an existing HTTPS `url`. It never uploads generated executable code, runs a build/deploy command, or fetches a caller-supplied URL. A supplied App `name` must meet Notify's actual 40-character limit, even though the workspace name permits 80.
- `notify_send`: rich notification with project/App association, stable intent and provider receipt. App-linked destinations must retain the registered origin. No display/attention claim is made.
- `notify_ask`: notification-presented business `approval`, `yes_no`, or `reply`; optional single bounded wait up to 25 seconds. This is never host permission. Project/run/session associations stay in SQLite, because the deployed interaction request schema has no project/App/correlation fields.
- `notify_replies`: polls Worker replies/events and locally known Notify questions only when invoked. Records receipt before acknowledgement, deduplicates, preserves original run/session, and returns attributed untrusted input. Injection also needs explicit tool `inject: true`, operator `allow_reply_injection: true`, the matching live session route and the public host API accepting the operation. Replies never execute commands.
- `notify_status`: bounded local state, publication phases and uncertain-write diagnostics. No network probe or inbox fetch. The REST client additionally offers inbox project/list reads for subsequent integration; the ordinary tools already group messages and Apps into the project inbox.

Tool results are JSON strings at the Hermes registry boundary. Session IDs and session route keys are taken from host kwargs and `gateway.session_context.get_session_env("HERMES_SESSION_KEY", "")`, never model arguments. `ctx.register_tool`, `register_skill`, `register_hook`, `register_approval_transport`, `inject_message`, `on_unload` and `ctx.state.data_dir` were checked against the pinned local Hermes source. The entrypoint also calls packaged `skills.register(ctx)` when `register_skill` is available, so the release-workspace skill is registered in native Hermes. No private-core patches were introduced.

## Publication and persistence

Hosted flow: prepared, Worker health check, durable conditional workspace PUT, deployed, Notify URL upsert, registered App ID saved, workspace App binding synchronized, then announcement. Existing HTTPS URL registration skips Worker publication. Repeated calls resume the same run's publication and stable URL; a changed name/URL conflicts with an in-progress intent. A repeated completed publish returns its receipt without another push.

Every Worker PUT persists its exact `{operationId, expectedRevision, workspace}` before sending. An unknown Worker response replays those bytes. If its saved response has expired (`OPERATION_RESPONSE_EXPIRED`), or its seven-day operation hash has expired (`REVISION_CONFLICT`), the client uses authenticated GET and accepts only the exact pending workspace at its expected next revision. It clears `pendingSync` only after that exact confirmation. Newer revisions, changed content, another run, or an unavailable authenticated read leave the pending intent intact; no rebase or overwrite occurs. App registration is the documented URL upsert. Notify notification/question writes durably claim their intent before sending, including across concurrently loaded runtimes. Known rejected writes can retry the same content/key. An ambiguous write, malformed response, connection loss, or process crash during send remains unknown and is not blindly resent. Status exposes these intents. There is no invented notification lookup-by-key route. A phone-delivery outcome with zero accepted targets is recorded as `not_accepted`; queued and accepted are separate from display.

Files in `ctx.state.data_dir`:

- `runtime.sqlite3`: profile-local run/session mappings, project/App mappings, publication state, exact intents, activity sequences, business questions, replies, and event receipts.
- `approvals.sqlite3`: original once-only host request/digest ledger, extended with a 10,000-row bound and 90-day cleanup.
- `status.json`: atomic, bounded shared Desktop snapshot with exactly `schemaVersion`, `configured`, `runs`, `pending`, `deliveries`, and `updatedAt`. It contains no session keys or native command text. Known configured credentials are rejected from explicit tool content. Files are created with mode 0600.

Workspace bounds count Unicode code points and shared approval digests are limited to 256 code points. JSON uses UTF-8 on disk and on the wire, so escaping cannot artificially expand non-BMP notes beyond the request cap. The separate Notify native-field guards retain its documented UTF-16 limits; progress labels are fitted to those narrower fields without changing workspace data.

The main journal caps records at 2,000 and each record at 64 KiB. Completed records age out at startup after configurable 1..90 days, default 30. Active/uncertain intents are retained rather than silently gaining a fresh attempt. Exhaustion fails explicitly. Snapshot output is bounded to 480 KiB, up to ten whole workspaces, thirty approvals and thirty delivery summaries. There is no idle pruning or polling process.

## Progress, native approvals and cleanup

A single lazy worker owns a bounded 64-entry queue. Observers only capture bounded request correlation or enqueue work; they do not access storage or HTTP. Routine updates coalesce for at least five seconds. A delayed pending event wakes only to flush that update; an empty queue waits without polling. Terminal and approval state changes bypass routine pacing. Native approval waits retain the spike's two-slot limit and bounded long polls.

Progress starts once with a durable activity key, uses measured progress or null, updates with `ifSequence`, and ends with explicit success/warning content. Capacity and unsupported-target failures fall back to ordinary updates. If a created activity falls back because no target accepted it, completion still attempts its logical end. Unknown starts are reconciled by activity key. Ambiguous updates read the recorded activity and sequence; a stale writer never overwrites a different sequence. Delivery/readiness data does not claim phone display.

The fast `pre_approval_request` observer captures the host request ID/digest and session. The transport persists the unambiguous matching active run, shows awaiting approval, and preserves the immutable request in the original bridge. Only a matching authoritative Notify `approval/approved/approve` can produce `once`; other outcomes deny. The host's `post_approval_response` observer confirms approved or denied in the workspace. Host timeout beats a late consumed transport response. Lost pending host requests expire after restart and cannot be revived by a webhook. If several active releases share a session, the runtime declines to guess their project mapping; the underlying exact host approval still works.

Worker events are already signature-verified at the Worker boundary. Python treats them only as wake-up hints, records them, fetches authoritative Notify state for known local interactions, checks correlation, and acknowledges after reconciliation. Native approval history cannot grant permission through this path. Unknown interaction hints are recorded and ignored without fetching arbitrary prompts.

Unload signals cancellation, clears pending queued work, joins the worker with bounded waiting, and records abandoned work. Hermes removes all registered tools, hooks and the transport. There are no LLM calls, inbound listener, CLI dependency, or shell command in the runtime.

## Configuration and integration limits

`enabled` defaults false. Only enabled registration resolves the declared `NOTIFY_API_TOKEN` and `HERMES_NOTIFY_PUBLISH_TOKEN` through `agent.secret_scope.get_secret`, capturing them before worker threads. Production Notify origin is fixed. The Worker origin is operator `publisher_origin`, or `https://{worker_name}.{worker_subdomain}.workers.dev`. Test overrides require the literal synthetic `dummy` token and `http://127.0.0.1:<port>` with the exact path. Redirects and ambient HTTP proxies are disabled.

Sending needs `notifications:send`; questions/host approvals add `interactions:create` and `interactions:read`; publication needs `apps:write`; enabled progress needs `activities:write` and `activities:read` for recovery. Inbox reads need `inbox:read` if used. Missing-scope responses preserve only safe machine diagnostics. A token rotation does not make old token-owned questions accessible; it may require a new explicit question.

`progress_enabled` defaults false. `allow_reply_injection` defaults false and does not bypass Hermes's separate injection authorization. Native transport selection still requires operator `security.approval.transport: notify` in a profile that permits the public in-process transport. Not every Hermes approval/human-input path uses that transport.

No live delivery, phone rendering, deployed Worker, microAuth, or actual action execution is claimed by the Python tests. Root should test the Python client against the integrated local Worker and perform any later explicitly authorized live rehearsal separately. Existing-URL registration validates HTTPS syntax and public hostname policy but intentionally does not fetch arbitrary caller destinations.

## Shared-contract notes for parent

No new shared fields or routes are required. Please clarify these existing semantics when integrating:

1. Local workspace revisions count local mutations. Worker revisions count ordered publications. Coalescing means they can differ; the publisher copies the latest content into the next Worker revision and retains `remoteRevision` privately. A Desktop optimistic edit uses the local revision; an App read uses the Worker revision. Neither is permission.
2. `announced` means a notification receipt was recorded, with accepted/not-accepted delivery shown separately. Ambiguous Notify writes require operator reconciliation; automatic retry cannot promise no duplicates because the deployed agent idempotency retention/recovery contract is unspecified.
3. Workspace names permit 80 characters but Notify App registration permits 40. The public publish tool has a separate optional `name` field and rejects an overlong default rather than truncating it.
4. Root-owned `pyproject.toml`, packaging/version text, README and integrated UI metadata should be aligned with `plugin.yaml` version `0.2.0`. This task did not edit those files.
