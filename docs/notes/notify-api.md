# Notify API research

Research date: November 4, 2026, Eastern Time. Public snapshots were fetched on November 5 UTC. This note records public documentation and schema evidence, not a tested phone round trip. No credentials, authenticated tools, pushes, app registrations, or submissions were used.

## Spike contract available now

Use direct HTTPS against `https://notify.belweave.ai/api/agent`. The CLI is optional. Requests use `Authorization: Bearer <scoped user key>` and JSON bodies. Existing `ntf_` and linked-account `ak_` keys are documented. The three scopes for sending an update, asking, and reading an answer are `notifications:send`, `interactions:create`, and `interactions:read`. The dashboard's **Server integration** preset does not include `interactions:read`, so that preset alone cannot complete this round trip. [Access](https://notify.belweave.ai/docs/access), [deployed OpenAPI](https://notify.belweave.ai/openapi.json).

| Operation | Exact route | Required scopes | Documented success |
| --- | --- | --- | --- |
| Notify | `POST /api/agent/notifications` | `notifications:send` | `201`, `{notification, accepted, idempotent?, message?}` |
| Ask | `POST /api/agent/interactions` | `interactions:create`, `notifications:send` | `201`, `{interaction, accepted, idempotent?, liveActivityId?, queued?, message?}` |
| Get answer | `GET /api/agent/interactions/{id}` | `interactions:read` | `200`, `{interaction}` |
| Wait for answer | `GET /api/agent/interactions/{id}/wait?timeout=25` | `interactions:read` | `200`, `{interaction, timedOut}` |
| Cancel | `POST /api/agent/interactions/{id}/cancel` | `interactions:create` | `200`, `{interaction}` |
| Discover pending prompts | `GET /api/agent/interactions` | `interactions:read` | `200`, `{interactions: InboxInteraction[]}` |

The wait query is named `timeout`, a number from 0 to 25 seconds. The schema does not declare its default; send it explicitly. Get, wait, and cancel describe a prompt **created by this token**. List instead covers the account's pending prompts from every source. Do not assume a replacement token can retrieve an older token's prompt. [OpenAPI operations `postInteractions`, `getInteractionsId`, `getInteractionsIdWait`, `getInteractions`](https://notify.belweave.ai/openapi.json).

Minimal update body:

```json
{
  "title": "Hermes task",
  "body": "The project workspace is ready.",
  "project": "Hermes Pocket"
}
```

Minimal approval body:

```json
{
  "title": "Hermes approval",
  "prompt": "Approve the displayed action for the recorded project version?",
  "kind": "approval",
  "presentation": "notification",
  "expiresInSeconds": 120
}
```

Give each logical write its own stable `Idempotency-Key` header. Retain the returned `interaction.id`, `actionDigest`, kind, expiry, and the local action/version mapping before waiting. A lost create response is an unknown outcome. Reuse the same key and exact intended payload when reconciling; do not create another prompt merely because a wait timed out. [Decision guide](https://notify.belweave.ai/docs/ask-decision), [delivery guide](https://notify.belweave.ai/docs/delivery).

**Proposed spike acceptance rule:** grant one execution only when the stored interaction ID and digest match, `kind == "approval"`, `status == "approved"`, and `response == "approve"`, while the original host request is still valid. Consume that permission durably once. Treat every other state, malformed response, unavailable server, or lost host request as no permission. The digest binds Notify's stored prompt; it does not attest an external command unless the integration binds that command itself. This rule is integration policy, not a new Notify endpoint.

### Exact message and interaction shapes

`POST /notifications` requires `body` only. Its request fields are `body`, `title`, `imageUrl`, `url`, `deviceIds`, `project`, `summary`, `bodyFormat`, `appId`, `oncall`, and `group`. Limits: body 1–8,000 UTF-16 code units and 16,384 UTF-8 bytes; title 1–80, default `Notify`; summary 1–500; project 1–80; URLs at most 2,048; selected devices 1–50 IDs of 1–100 characters. `bodyFormat` is `text|markdown`; current V1 clients display plain text. `appId` matches `^app_[A-Za-z0-9_-]{8,64}$`. App-linked destinations must stay on the registered origin. `deviceIds`, `group`, and `oncall` are mutually exclusive by documentation; on-call also needs `oncall:write`. [Message guide](https://notify.belweave.ai/docs/send-update), [validation reference](https://notify.belweave.ai/docs/notification-api), [OpenAPI](https://notify.belweave.ai/openapi.json).

The returned `AgentNotification` requires `id`, `title`, `body`, nullable `imageUrl`, nullable `url`, and `createdAt`. It may also include nullable `projectId`, nullable `summary`, `bodyFormat`, and `appId`. This agent response uses `notification.id` and `accepted`; it is different from a service webhook's `eventId` and `delivered`.

`POST /interactions` requires `title` (1–80), `prompt` (1–2,000), and `kind` (`approval|yes_no|reply`). Optional fields are `imageUrl`, `url`, `deviceIds`, `group`, `expiresInSeconds` (integer 30–86,400, default 900), `presentation`, `style`, `design`, `accentColor`, `primaryLabel`, `secondaryLabel`, `callback`, and `webhookId`. It does **not** declare `project`, `appId`, `correlationId`, `summary`, or `body` as direct interaction fields. Keep those associations in the integration's journal; do not copy the message body schema into an ask. [Direct interaction reference](https://notify.belweave.ai/docs/agent-api), [OpenAPI](https://notify.belweave.ai/openapi.json).

`presentation: "live_activity"` permits only `approval|yes_no`, limits prompt to 240 and expiry to 28,800 seconds, and rejects `url` and `imageUrl`. Only that presentation accepts `style` (`approval|shell|verdict|signal`), design, hex accent, and 1–24 character action labels. Labels do not change canonical answers. `group` and `deviceIds` cannot coexist. Default notification presentation supports text replies through `kind: "reply"`; service webhooks instead call that response type `text`.

Every field below is required on the OpenAPI `Interaction` object, even when its value is nullable:

| Fields | Type |
| --- | --- |
| `id`, `title`, `prompt`, `actionDigest` | string |
| `kind` | `approval|yes_no|reply` |
| `presentation` | `notification|live_activity` |
| `status` | `pending|approved|denied|yes|no|replied|canceled|expired` |
| `choices` | string array |
| `response`, `imageUrl`, `url`, `primaryLabel`, `secondaryLabel`, `respondingDeviceId`, `respondingUserId` | string or null |
| `accepted` | integer |
| `createdAt`, `expiresAt` | date-time string |
| `respondedAt`, `canceledAt` | date-time string or null |

`actionDigest` is only typed as a string in the public schema. Its server calculation is not specified there. Do not invent a digest algorithm or assume it is the local host request digest. Accept future response fields without weakening the required decision checks. [OpenAPI `Interaction`, `InteractionCreated`, `AgentNotificationCreated`](https://notify.belweave.ai/openapi.json).

### State and retries

The documented interaction lifecycle begins at `pending` and ends at one of `approved`, `denied`, `yes`, `no`, `replied`, `expired`, or `canceled`. Approval answers use `approve|deny`; yes/no answers use `yes|no`; reply carries text. The first valid server-confirmed answer settles a shared question. An offline phone can queue an answer that later loses to another answer, cancellation, expiry, or revoked access. An agent can read or cancel, but cannot submit the human answer. [Decision guide](https://notify.belweave.ai/docs/ask-decision), [family behavior](https://notify.belweave.ai/docs/family), [access boundary](https://notify.belweave.ai/docs/access).

`timedOut` describes one wait, not a terminal interaction status. A successful HTTP read, CLI exit 0 on a pending get, provider acceptance, and a queued phone response are not approval. Read/wait the same ID until the caller's own deadline; stop dependent work when that deadline passes. Cancellation and notification withdrawal are distinct operations. Service event reads explicitly settle overdue pending questions as expired; the public agent schema does not document that implementation detail.

The delivery guide specifies 1–200 character idempotency keys, matching replay of the original result, `202` for an in-progress identical request, `409` for changed content, and `400` for empty/oversized keys. That section explicitly describes the **service** namespace. Agent notify/ask declare the header, and the skills instruct stable-key retries, but the public schema does not fully specify agent key lifetime, namespace, concurrent-create behavior, or replay status codes. Those remain confirmation items. Do not turn the service description into an unverified agent guarantee. [Delivery](https://notify.belweave.ai/docs/delivery), [agent OpenAPI](https://notify.belweave.ai/openapi.json).

Errors have required string `error`, with optional `code`, `issues`, and `required: string[]`. `401` means invalid/revoked/expired access; `403` can identify missing scopes; `404` conceals unavailable resources. The generated notify/ask operations list only 201/400/401/403/404, while the guides describe additional conflict, queue, capacity, rate-limit, and delivery-failure outcomes. A client must preserve error bodies and reconcile ambiguous writes instead of treating the schema's response list as exhaustive.

## Evidence boundary

Public documentation and deployed schemas are verified observations. Recommendations above are labeled as proposals. No tool execution or device display was tested. Anonymous `POST /mcp` with JSON-RPC `tools/list` and anonymous `GET /mcp` both returned `401 {"error":"Unauthorized"}`. Preetham subsequently supplied an authenticated schema-only read from the `user-notify` client: 99 live tools, 38 additions and no missing names relative to the initial public inventory. The [verified inventory](notify-mcp-inventory.md), [condensed schema observations](notify-mcp-live-schemas.json), and [diff](notify-mcp-diff.md) supersede the earlier inventory limitation. No tool calls were made by that client read.

Snapshots are in `.local/research/notify/`, including `openapi.json`, `llms-full.txt`, the individual Markdown guides, public JWKS, OAuth metadata, the MCP request/response, and a timestamped SHA-256 source manifest. [`spike-contract.json`](../../.local/research/notify/spike-contract.json) preserves 32 relevant operations and all 23 transitively referenced schemas without changing their contents. It is an OpenAPI subset, not an MCP schema.

## Full hosted Notify Apps

Notify Apps can open a normal HTTPS website with its own frontend, backend, network requests, and sessions. No SDK is required simply to open the site. The hosting requirement is a reachable HTTPS launch URL that the publisher controls; plain HTTP is documented only for `localhost` development. The API registers a URL. It does not upload or deploy a hosted site's source or assets. **Proposed publication flow:** deploy through an explicitly configured hosting provider, verify the resulting site, register or update its Notify App, then send an app-linked update. Store deployment and registration receipts separately so partial failure can resume. [Hosted Apps](https://notify.belweave.ai/docs/web-apps), [App API](https://notify.belweave.ai/openapi.json).

| App operation | Contract under `/api/agent` |
| --- | --- |
| `POST /apps` | Required `name` (1–40), `url` (URI, maximum 2,048); optional `iconUrl` (maximum 2,048), `project` (1–80), `teamId`. `apps:write`. Returns `201 {app, created, message?}`. Re-registering an existing URL updates it. |
| `GET /apps`; `GET /apps/{id}` | `apps:read`; returns `{apps: App[]}` or `{app}`. |
| `PATCH /apps/{id}` | `apps:write`; optional `name`, `url`, nullable `iconUrl`, nullable `project`, `publicClient`. Unknown properties are rejected by the schema. Returns `{app, message?}`. |
| `POST /apps/{id}/share` | `apps:write`; required `teamId` or null, optional `notify` boolean. Only the contributor can move it. Sharing normally notifies other members; `notify: false` suppresses that notice. Returns `{app}`. |
| `POST /apps/{id}/revoke` | `apps:write`; revokes this account's sign-in consent. Returns `{app}`. |
| `DELETE /apps/{id}` | `apps:write`; removes the registration, returns `{ok: true}`. |

`App` includes `id`, `name`, `origin`, nullable `iconUrl`, launch `url`, project ID/name, `publicClient`, `ownedByViewer`, opaque `storageScope`, consent/profile flags and timestamps, creator, and nullable team metadata. Registration does not grant profile consent. A changed origin clears consent; storage generations are part of the host's account/app/origin/workspace partitioning. The docs cap an account at 100 registrations. No App-create idempotency header is declared, so retain the returned ID and use the documented existing-URL behavior rather than assuming a general idempotency contract. [OpenAPI `App`, `postApps`, `patchAppsId`, `postAppsIdShare`](https://notify.belweave.ai/openapi.json).

A personal registration is private by default. Its owner may PATCH `{"publicClient":true}` and share `belweave-notify://web/<app-id>` with unrelated Notify accounts. Every viewer opens the same registration and separately approves sign-in; optional profile refusal does not remove identity. Public mode does not create a directory or grant publisher management. Disable it before moving the registration into a team or family. Changing public eligibility resets grants/storage generations, but the website still owns existing sessions. Docs identify Tools 0.14.0+ and the iOS 1.5.9 library behavior; this research did not test an installed phone build. [Public website clients](https://notify.belweave.ai/docs/web-apps), [pinned CLI implementation](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/cli/commands/apps.mjs).

Announce the App through `/notifications` with `appId` and, optionally, a same-origin `url`. The person must tap to open it. An ask has no declared `appId` field; a service-webhook payload explicitly forbids combining `appId` with `response`. A project workspace and its approval should therefore share an integration-owned mapping, not an invented combined Notify operation. [Tap behavior](https://notify.belweave.ai/docs/web-apps), [webhook fields](https://notify.belweave.ai/docs/notification-api).

Hosted Apps are distinct from personal packaged Mini Apps. Packages use `web`/`notify-web-v1`, free commerce, and isolated optional local storage. They have no hosted sign-in bridge or network capability, are owner-only, and physical-device execution is documented as disabled pending approval. Their build/publish APIs are not the hosting path for a full web App. The iOS hosted view requires iOS 18.4+. Browser/device features vary by platform, and an available bridge method is not a permission grant. Current microAuth targets iOS bridge v3, with no documented Android microAuth parity. [Mini Apps](https://notify.belweave.ai/docs/mini-apps), [hosted capabilities](https://notify.belweave.ai/docs/web-apps).

## Sign-in pass and nonce flow

The hosted website's pass is separate from an agent API key and MCP OAuth access token. Its verified public contract is:

| Item | Value |
| --- | --- |
| Signature/header | ES256 JWT, protected `typ: "notify-pass+jwt"` |
| Issuer | Exactly `https://notify.belweave.ai` |
| Audience | Exactly the registered website origin, including scheme and port; no path or trailing slash |
| JWKS | `https://notify.belweave.ai/.well-known/jwks.json` |
| Subject | Pairwise `hk_…` subject scoped to origin; registrations on one origin share it, different origins receive different subjects |
| Required new-flow claims | `iss`, `aud`, `sub`, `iat`, `exp`, `jti`, `app_id`, `nonce` |
| Lifetime | Pass lifetime at most 120 seconds; server challenge also expires after 120 seconds, including time spent in consent |
| Binding | Exact expected `app_id` and `nonce == stored challenge` |
| Optional identity | Top-level `name`, `email`; `profile.phone`, `profile.timeZone`, `profile.pronouns`, `profile.custom`; paired `team_id` and `team_role` |

The origin-scoped `hk_` subject is explicitly documented, not inferred from Clerk. The public JWKS snapshot contains an EC P-256 signing key with `alg: ES256`. The SDK verifies a bounded nonempty subject string; it does not enforce the `hk_` prefix or reveal the pairwise derivation algorithm. [Pass claims](https://notify.belweave.ai/docs/web-apps), [public JWKS](https://notify.belweave.ai/.well-known/jwks.json), [pinned verifier `src/microauth/server/handshake.ts`](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/server/handshake.ts).

The complete new-flow exchange, verified in the pinned source and the downloaded 0.14.2 browser/server bundles:

1. The website calls `connectMicroAuth({challengePath, sessionPath, fields})`. Without a `window.notify.microAuth` function it returns `{available:false}` without starting authentication.
2. The browser POSTs `{}` to the website's same-origin challenge path using cookies, `cache: "no-store"`, and `redirect: "error"`.
3. The website binds a random 32-byte base64url challenge to a separate random browser binding held in an HttpOnly, Secure, SameSite cookie. It persists `{challenge, expiresAt}` and returns the challenge. `/auth/challenge` is an example website route, not a Notify endpoint.
4. The bridge receives `microAuth({challenge, fields})`. The viewer approves sign-in and optional sharing. The resulting pass carries the nonce.
5. The browser POSTs `{"token":"<pass>"}` to the website's same-origin session path with the binding cookie. The binding must come from that cookie, never from the JSON body or JWT.
6. `createMicroAuthServer.complete(token, binding)` verifies signature, type, issuer, exact string audience, app ID, nonce, required claims, integer times, expiry, and a maximum 120-second lifetime with zero clock tolerance. It atomically consumes the stored binding/challenge after verification.
7. The website issues its own session cookie and applies its own authorization. The example rotates its session, clears the challenge cookie, and stores sessions on persistent SQLite. Its eight-hour session lifetime is an example policy, not a Notify pass lifetime.

Sources at exact Tools commit `390013d3e89c23776a0a6087646a4f7f995a0b38`: [`src/microauth/browser/session.ts`](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/browser/session.ts), [`browser/bridge.ts`](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/browser/bridge.ts), [`server/binding.ts`](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/server/binding.ts), [`server/handshake.ts`](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/server/handshake.ts), [`examples/microauth/node-session.mjs`](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/examples/microauth/node-session.mjs).

Use `(issuer, subject)` as identity and pin the expected app ID. Name, account email, and profile text are optional, not independent identity attestations or authorization. Do not merge accounts by email. Revoking consent stops future passes, not the site's existing sessions or retained data. Copy the complete release SDK with shared chunks, declarations, license and notices. [microAuth guide](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/skills/notify/notify-apps/references/microauth.md).

The older `getToken()` flow has no browser-bound challenge. Its raw-pass middleware requires durable atomic `jti` consumption. The new microAuth helper requires `jti` but implements replay prevention through atomic challenge consumption, without a separate `jti` table in that helper. Do not combine the two examples into a weaker flow. The new helper also requires HTTPS even though App registration permits localhost HTTP. [Verifier](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/server/handshake.ts), [pass middleware](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/connector/passes/http.ts).

## Webhook directions and receiver contracts

**Inbound service webhook, sender to Notify.** A service returns a credential-bearing URL shaped `https://notify.belweave.ai/hooks/whk_<token>`. POST JSON with required `body`. Optional `response` uses `type: approval|yes_no|text`, expiry 30–86,400 seconds, optional `correlationId` up to 100 characters, callback, and saved `webhookId`. Read `GET /hooks/{token}/events/{eventId}`; cancel or withdraw with POST to the corresponding `/cancel` or `/withdraw` suffix. No service event long-poll route is documented. URL possession authorizes access; there is no documented inbound HMAC requirement. Service create/rotate return the URL once; agent list/get redact it. [Connection credential](https://notify.belweave.ai/docs/quickstart), [webhook reference](https://notify.belweave.ai/docs/notification-api), [question flow](https://notify.belweave.ai/docs/ask-decision).

**Per-question callback, Notify to a receiver.** A classic callback is `{url, token}` with public HTTPS and a 16–512 character token. It sends `Authorization: Bearer <callback.token>`, `Notify-Timestamp`, and `Notify-Signature: v1=<hex HMAC-SHA256>`. The HMAC key is that token; input is timestamp, a dot, and unchanged body bytes. Connector callbacks instead specify `{target:{connectorId,route,path}}`, use the connector callback secret, and enter the fixed `POST /.notify/callback` gateway without a bearer header. The route/path are persisted with the interaction. Do not let a reply choose a forwarding destination. [Callback reference](https://notify.belweave.ai/docs/notification-api), [connector reference](https://notify.belweave.ai/docs/connect).

```json
{
  "type": "notification.response",
  "interactionId": "int_EXAMPLE_ONLY",
  "actionDigest": "<stored actionDigest>",
  "eventId": null,
  "correlationId": null,
  "kind": "approval",
  "status": "approved",
  "action": "approve",
  "text": null,
  "respondedAt": "2026-11-04T23:00:00.000Z"
}
```

This callback reports human answers only, not cancellation or expiry. For a reply, kind/action are `reply` and text holds the answer. Agent asks can have null event/correlation IDs. Verify before parsing, reject future timestamps and timestamps more than 300 seconds old, compare in constant time, match the retained interaction/digest, and durably deduplicate. The SDK signature helper checks HMAC and freshness, not business authorization or replay storage. Callback requests refuse redirects, time out after 10 seconds, and retry non-2xx outcomes after 30 seconds, 2 minutes, 10 minutes, and 1 hour, exhausting after five failed attempts. The connector gateway has its own five-second upstream timeout. [Callback delivery](https://notify.belweave.ai/docs/notification-api), [pinned signature helper](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/connector/callbacks/signature.ts), [gateway behavior](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/README.md#mandatory-access-gateway).

**Saved reply webhook, Notify to an account subscription.** Its `whk_…` ID names a saved endpoint; it is not the inbound service URL credential. `POST /api/agent/webhooks` requires `services:write`, `name` (1–80), and HTTPS `url` (maximum 2,048). Optional fields: `preset: generic|grok|slack` (default generic), up to 16 `{name,value}` headers, one to three lifecycle `events`, `enabled` (default true), and `isDefault` (default false). Header names are 1–128 token characters and values 1–4,096 characters. Returns `201 {webhook, signingSecret}` once. Reads require `services:read`; PATCH/DELETE/test/rotate require `services:write`. Read `{id}` returns the endpoint and up to 50 recent deliveries. `POST /{id}/test` sends a real outbound sample and returns 202; it was not called. [OpenAPI webhook operations](https://notify.belweave.ai/openapi.json), [subscription guide](https://notify.belweave.ai/docs/notification-api).

Generic and grok subscriptions use this documented envelope; Slack uses a `text` payload instead:

```json
{
  "type": "interaction.answered",
  "interaction": {
    "id": "int_EXAMPLE_ONLY",
    "title": "Proceed with the recorded action?",
    "kind": "approval",
    "status": "approved",
    "response": "approve",
    "respondingDeviceId": "dev_EXAMPLE_ONLY",
    "respondedAt": "2026-11-04T23:00:00.000Z"
  },
  "sentAt": "2026-11-04T23:00:01.000Z"
}
```

`service: {id,title}` is present for service-associated events. Expired/canceled events can have null response/device/time. This envelope does not supply the classic callback's top-level interaction ID or action digest. **Proposed receiver policy:** use the stored interaction ID to read current server state and compare the saved digest before granting a host action. Do not expect either callback format to prove external execution. The documented serializer source paths are `apps/website/src/server/lib/callback-payload.ts` and `apps/website/src/server/lib/reply-webhooks.ts`; their server repository was not publicly readable, so these body shapes are documentation evidence, not a verified server-source pin. [Public receiver guide](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/skills/notify/notify-automation/references/receivers.md).

Saved endpoints use **`X-Notify-Signature: t=<unix>,v1=<hex>`**, signing the same `timestamp + "." + rawBody` construction with the endpoint's signing secret. Reject timestamps outside age 0–300 seconds and use constant-time comparison. `X-Notify-Delivery-Id` stays stable across retries; body stays unchanged and signature timestamp refreshes. Durably deduplicate the delivery ID and also enforce one-time business handling for the interaction/outcome, since several endpoints can receive the same outcome. Acknowledge 2xx only after durable receipt. Retries occur after 1, 5, 15, and 40 minutes for timeouts/5xx; 4xx and redirects are final failures. [Exact signature and retry rules](https://notify.belweave.ai/docs/notification-api).

Events are `interaction.answered`, `interaction.expired`, and `interaction.canceled`. Notify considers the enabled account default, explicit interaction `webhookId`, and service's current `defaultReplyWebhookId`; it deduplicates endpoints within that event. Only one account default is selected at a time. Replacing headers replaces the list; omitted headers preserve saved values, and read masks are not valid replacement secrets. Secret rotation invalidates the old signing material. The public API does not promise an automatic overlap window. For the spike, polling avoids needing a public receiver; callbacks can be a later durable wake-up path.

## Progress and project grouping

Direct progress routes are `POST /api/agent/activities`, `GET /activities`, `GET|PATCH /activities/{identifier}`, and `POST /activities/{identifier}/end`. Reads need `activities:read`, writes `activities:write`. Identifier can be ID or start key. Start requires title 1–80 and status 1–60; optional subtitle 1–120, detail 1–240, progress 0–1, style/design, symbol, privacy, accent, key 1–100, replacement, targeting, expiry and staleness. Expiry is 60–28,800 seconds, default 28,800; staleness is 0–28,800, default 14,400. The exact schemas are in the saved subset. [Activity guide](https://notify.belweave.ai/docs/activity-api), [OpenAPI](https://notify.belweave.ai/openapi.json).

Start returns 201; update/end return 200. Mutations return `{activity, accepted, failed}` plus optional `queued`, `superseded`, `replaced`, `idempotent`, `message`, `apnsPriority`, and `priorityReason`. Activity states are `starting|active|partial|failed|ended|expired`. Read `activity.readiness`, including queued starts, native creation confirmation, missing update tokens, and errors. Provider acceptance can leave a start in `starting`. Task success/failure belongs in the content and integration state, not in an assumption that a push was visible.

One key selects a continuing activity; an idempotency key selects one write. Updates increment `sequence`; use `ifSequence` to reject stale writers. Clear optional subtitle/detail/progress with null. Updating an ended/expired activity returns 409. End is logical immediately even when delivery is queued; send explicit final status/symbol because omitted values become `Complete`/`success`. End dismissal is 0–14,400 seconds, default 0. A duplicate active key yields 409; capacity is five activities per device, with 422 `ACTIVITY_CAPACITY_EXCEEDED`. `replace: true` ends the same requester's matching key, including old targets, and preserves unrelated keys. [Lifecycle and delivery](https://notify.belweave.ai/docs/activity-api), [limits](https://notify.belweave.ai/docs/delivery).

iOS starts share a 60-second per-device pacing interval across senders. Routine updates coalesce; interaction changes and endings are preserved. APNs routine priority is 5; requested high-priority milestones use 10 within four/minute and twenty/hour per activity, otherwise fall back with `budget_exhausted`. Android uses ongoing/actionable notifications rather than ActivityKit layouts. None of these counts proves display. End the task even if its card never became visible. [Activity update schema](https://notify.belweave.ai/openapi.json), [pacing guide](https://notify.belweave.ai/docs/activity-api).

Projects are account-scoped inbox groupings, not an independent project-management API. A message's `project` name creates or resolves a project after Unicode normalization/case folding; the first spelling remains the display name. At 500 projects, a new name can fall back to unfiled with a message while the send succeeds. App registration also accepts `project`. [Project behavior](https://notify.belweave.ai/docs/send-update), [App schema](https://notify.belweave.ai/openapi.json).

`GET /api/agent/inbox/projects` returns `{projects, totalUnread}`; each row has nullable project ID, name, unread/total counts, and nullable latest title/preview/image/time. `GET /inbox/notifications` takes `project` as a **project ID** or `unfiled`, optional `unread=1|true`, `limit=1..50`, and cursor; it returns `{items, nextCursor, readThroughToken}`. Reads need `inbox:read`. Read/unread mutations need `inbox:write`. Read-all requires `{"readThrough":"<readThroughToken>","project":"<optional filter>"}`, preserving newer arrivals beyond the list watermark. Project grouping does not replace earlier system notifications. [Inbox operations](https://notify.belweave.ai/openapi.json).

## Optional CLI and MCP paths

The public CLI release is 0.14.2. Its archive and SHA256SUMS were downloaded and matched, but nothing was installed or executed. Supported Node lines require at least 22.23.4, 24.22.1, or 26.12.1. The CLI uses the same HTTP API; a Python integration need not depend on Node or spawn the CLI. [Release setup](https://notify.belweave.ai/docs/quickstart), [pinned Tools README](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/README.md).

For later authorized use, the equivalent approval command is:

```sh
notify send ask "Approve the recorded action?" --approval --title "Hermes approval" --expires-in 2m --idempotency-key "operation-specific-key" --wait --timeout 2m
notify interaction get int_RETURNED_ID
notify interaction wait int_RETURNED_ID --timeout 2m
```

Creation and waiting are separate facts. `--poll` waits 20 seconds; standalone `interaction wait` defaults to 60 seconds and chains HTTP waits of at most 25 seconds. Outcome commands use exit 4 for timeout/cancel/expiry, 5 for denial/no, 7 for no accepted or queued delivery; 1/2/3/6 cover API/usage/auth/network failures. Exit 0 on a get can still mean pending. The pinned CLI has interaction list/get/wait, so use the REST cancel route instead of inventing a CLI cancel command. Explicit `--expires-in` avoids the stdin expiry discrepancy below. [CLI docs](https://notify.belweave.ai/docs/cli), [pinned result handling](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/cli/foundation/results.mjs), [interaction commands](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/cli/commands/interaction.mjs).

MCP uses Streamable HTTP at `https://notify.belweave.ai/mcp`, with a scoped bearer key or OAuth. Public discovery currently advertises resource `https://notify.belweave.ai/mcp` and authorization server `https://clerk.notify.belweave.ai`, with S256 PKCE. That OAuth issuer/JWKS is distinct from the hosted site's ES256 pass issuer/JWKS. The protected-resource/default challenge omits `tokens:manage`; the authorization-server metadata includes it as a supported scope. Supported scope does not mean granted scope. [Resource metadata](https://notify.belweave.ai/.well-known/oauth-protected-resource/mcp), [authorization metadata](https://notify.belweave.ai/.well-known/oauth-authorization-server), [MCP reference](https://notify.belweave.ai/docs/mcp).

Verified `ask` waits at most 25 seconds per call for notification presentation. Legacy `timeoutSeconds` values up to 600 remain accepted but are capped. Live Activity asks return pending immediately with queued attempts. Resume with `interactions_wait` or `interactions_get` using the creating token. Creation/transport can exceed the nominal wait budget in wall-clock time. All 99 live tool names and the supplied schema constraints are in [the MCP appendix](notify-mcp-inventory.md). The stored JSON preserves condensed observations rather than inventing raw `inputSchema`/`outputSchema` objects.

## Discrepancies and limits that affect implementation

| Finding | Consequence |
| --- | --- |
| Anonymous MCP discovery returned 401; the later user-supplied authenticated schema read reports 99 tools. | Inventory and recorded constraints are now verified. The supplied JSON is condensed; use the current raw schema when implementing MCP calls rather than treating the prose constraints as a JSON Schema object. |
| Notify's server repository returns 404 to an anonymous commit lookup. | No deployed server commit can be claimed. Public Tools is pinned separately; its commit is not the server deployment SHA. |
| Activity reference says default accent `#246BEB`; deployed start schema says `#30D158`. | Supply an explicit accent if the default matters. [Reference](https://notify.belweave.ai/docs/activity-reference), [schema](https://notify.belweave.ai/openapi.json). |
| Activity guide permits omitting the end body; agent OpenAPI marks its request body required. | Send `{}` or explicit final fields for the direct agent API. The guide shows service routes, so this may be an interface distinction. [Guide](https://notify.belweave.ai/docs/activity-api). |
| Generated notify/ask error responses omit several documented outcomes, and callback URL/token pairing and notification targeting exclusions are not fully encoded. | Apply the prose constraints as well as the schema; handle documented 202/409/422/429/502 outcomes without claiming every route emits each one. |
| General idempotency prose is service-scoped; agent headers have no TTL or namespace documentation. | Preserve keys and exact intent, but leave retention, atomic replay behavior, and cross-token recovery as explicit live-test questions. |
| Installed skill is tagged compatible CLI 0.13.0; public release is 0.14.2. Older guide material lacks public-client details. | Use the pinned CLI and deployed App schema for public website distribution. |
| Installed automation skill says service get provides endpoint/configuration; public access docs and OpenAPI say agent reads omit the URL. | Capture the credential on create/rotate; do not expect a later agent get to recover it. [Access](https://notify.belweave.ai/docs/access). |
| Installed message skill describes read-all relative to operation time; deployed API requires a list watermark. | Retain `readThroughToken` and send it as `readThrough`; do not mark unseen newer items read. |
| The website connector guide and installed transport guide describe in-memory tunnel identity; public Tools 0.14.2 README describes persistent tunnel identity. | Follow the pinned Tools behavior if later using a connector; do not promise a fresh hostname each restart. [Website guide](https://notify.belweave.ai/docs/connect), [pinned Tools documentation](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/README.md#opentunnel-051-options). |
| CLI ask's stdin path computes expiry from `stdin.expiresIn`, then overwrites `expiresInSeconds`; raw OpenAPI `expiresInSeconds` alone is not preserved. | Use `--expires-in` or direct HTTP. This is verified in pinned `src/cli/commands/send.mjs`, not inferred from prose. [Source](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/cli/commands/send.mjs). |
| Saved webhook payloads and some delivery metadata are documented beyond the generated response schema, including a delivery `interactionId` mentioned in prose but absent from `ReplyWebhookDelivery`. | Parse documented optional fields defensively, retain unknown fields, and confirm actual payloads before production use. |

Additional reliability constraints: account/service rolling limits are documented as 1,500/300 requests per minute; 429 carries `Retry-After: 60` and `retryAfterSeconds`. Unlimited monthly use does not remove those limits. A push acceptance or receipt does not establish display or attention. A missed banner can coexist with a durable inbox item. Delivery retries and webhook retries can repeat transport, so business effects need their own durable deduplication. Token replacement can break token-owned prompt access. Public-client disable, consent revocation, and an offline phone do not prove deletion of existing website sessions or downloaded data. [Delivery](https://notify.belweave.ai/docs/delivery), [Apps](https://notify.belweave.ai/docs/web-apps), [agent contract](https://notify.belweave.ai/openapi.json).

## Source record

- Read the complete public guide chapters for quickstart/auth, messages/projects, decisions, progress/layouts, hosted Apps, Mini Apps, family/network, delivery, access, webhooks, CLI, MCP, agent API, connectors, teams, and on-call. The combined public document and individual Markdown pages are saved. `auth.md` was also read. API reference schemas relevant to this contract were read in full.
- Read the Notify agent skill (`~/.agents/skills/notify/SKILL.md`), all eight workflow guides, and the relevant microAuth, Mini Apps, receiver, permission, activity design/delivery, and connector transport references. This research used public sources and made no authenticated calls. The user explicitly prohibited real pushes in this phase.
- [Public Notify Tools commit](https://github.com/Belweave/notify-tools/commit/390013d3e89c23776a0a6087646a4f7f995a0b38): `390013d3e89c23776a0a6087646a4f7f995a0b38`, dated October 27, 2026. The public source archive and commit metadata are saved. Referenced source paths above are pinned to it.
- [Tools 0.14.2 release archive](https://notify.belweave.ai/downloads/notify-tools/v0.14.2/notify-tools-0.14.2.tar.gz): SHA-256 `36f0b4bc7e5cc42d2463463ab3dc1e042560bbc63673743981bedbb5ab7eee71`, matched against [published SHA256SUMS](https://notify.belweave.ai/downloads/notify-tools/v0.14.2/SHA256SUMS). Its `sdk/browser.mjs` and `sdk/server.mjs` were read alongside the source; the release manifest does not advertise a build commit.
- [Deployed OpenAPI](https://notify.belweave.ai/openapi.json): SHA-256 `0199992597bb7a19c6817df42d2651cfbe79c701348f2f3d1122b21f05b0f0fb`, OpenAPI 3.1 with 75 paths and 103 operations. `/api/agent/openapi.json` is semantically identical but serialized differently. Neither supplies a deployed code commit.
- [Snapshot manifest](../../.local/research/notify/sources.json) records public source URLs, retrieval timestamps, status, byte size and SHA-256. [Raw anonymous MCP response](../../.local/research/notify/mcp-tools-list.raw) and [request metadata](../../.local/research/notify/mcp-tools-list-metadata.json) record the discovery limit. Raw upstream snapshots retain upstream spelling and punctuation; this note uses phone and belweave.
