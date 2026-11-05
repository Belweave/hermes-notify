# Hermes x Notify research

Research date: November 4, 2026, Eastern Time. The implementation and source study use Hermes commit [`ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`](https://github.com/NousResearch/hermes-agent/commit/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df). The installed local Hermes checkout was also tested at `b200f5bc60e31588ba2cb60e288029c4a54ba5fa`. Public Notify documentation and OpenAPI were fetched without credentials; Preetham separately supplied an authenticated, schema-only MCP inventory. [SOURCES.json](SOURCES.json) records archive and API hashes.

The strongest direction is a native Hermes plugin that publishes useful hosted Notify Apps and keeps their progress, decisions, and project history connected to Hermes. A notification wrapper alone leaves much of the value to ordinary MCP tools and skills. A plugin can own exact host approvals, durable correlation, lifecycle handling, and publication recovery.

## What is established

- Hermes has a public approval-transport registration API. The host supplies a redacted immutable request and validates the returned decision's ID, digest, allowed scope, and deadline. Observer hooks cannot answer approvals. This is implemented and tested in source, even though the main guide's registration walkthrough does not cover it fully.
- Notify's REST API can create a phone approval and read its server-confirmed response. The spike exercises those shapes through a local HTTP mock and returns the result through the real Hermes approval gate. Real phone delivery remains untested.
- A Notify App registration opens an existing hosted website. It does not deploy application code. The publishing feature must coordinate hosting, App registration, and an App-linked notification.
- Hosted Apps and packaged offline Mini Apps are separate products. The current public Mini App documentation gates physical-device runtime. Use hosted Apps for this demo.

Sources: [Hermes approval contract](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/approval_transport.py), [Notify Agent OpenAPI](https://notify.belweave.ai/openapi.json), [Notify App guide](https://notify.belweave.ai/docs/web-apps), [Notify Mini Apps](https://notify.belweave.ai/docs/mini-apps).

## Hermes plugin mechanics

### Lifecycle and packaging

A native package has `plugin.yaml` and `__init__.py` exposing `register(ctx)`. Support modules use relative imports. Hermes loads the package under its plugin namespace and calls registration for each load. A force reload disposes owned registrations before loading again. Keep import and registration offline and fast; acquire no long-lived network task merely because the package was discovered.

Discovery includes bundled plugins, the active profile's plugin directory, and the `hermes_agent.plugins` Python entry-point group. Project-local discovery is opt-in in some contexts and is ignored by gateway sessions. Install in a profile for CLI, Desktop, and gateway use. External packages must be explicitly enabled. Missing advisory plugin dependencies warn; code must still check any dependency it needs.

Declare metadata, tools, hooks, configuration, dependencies, and the supported Hermes version range accurately. `pyproject.toml` runtime dependencies take precedence over manifest dependency declarations. Hermes's package manager handles installation; the plugin must not mutate the shared runtime on import. The spike declares no runtime dependencies and has a separate locked development environment.

Loaders and hook dispatchers track registration ownership. Use `ctx.on_unload` for cleanup and `ctx.spawn_task` for supervised async work when an event loop exists. The loader has a default ten-second registration deadline. A timed-out Python thread is not forcibly killed, so a plugin still needs bounded I/O. Approval transports currently require `in_process` isolation, a trusted-code boundary; they are not supported in the isolated plugin host.

There is no verified minimum released Hermes version for `register_approval_transport` yet. The spike checks for that capability and reports the two exact tested source revisions. Do not invent a release floor from the source tree's placeholder version.

Sources: [plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [loader](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_loader.py), [manifest parser](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_manifest.py), [detailed runtime note](notes/hermes-runtime.md).

### Hooks and approval scope

`pre_tool_call` can block, modify arguments, or ask Hermes to require approval. Asking for approval is not approving the tool. `post_tool_call` observes results; transformation uses separate hooks. Most observers ignore returned values and should enqueue a compact update instead of making a network call.

`pre_approval_request` and `post_approval_response` are observers. The actual phone channel registers with `ctx.register_approval_transport("notify", present)`, selected explicitly by `security.approval.transport: notify`. It returns `request.respond("once")` or `request.respond("deny")`. The plugin never grants session-wide or permanent permission, even when Hermes offers those choices.

The request contains a fresh request ID, digest, redacted command/description, pattern metadata, surface, timeout, and allowed choices. The session key is bound inside the digest but is not a request field. For a future project/session mapping, join the transport request ID and digest to the fast approval observer's context. Human-input observer IDs are different IDs and cannot serve as that join key.

The worker does not explicitly copy the caller's context variables. Capture profile settings, secret references, and storage paths before entering it. Hermes discards late responses, but the callback can keep running. The spike has a shorter local deadline, two worker slots, bounded five-second long polls, and an unload flag. A timeout never becomes approval.

Core policy remains first: hardline blocks, existing grants, bypass modes, and unattended policies can resolve execution without invoking the transport. Some human-input gates use other APIs. In particular, the pinned generic plugin-rule gate is marked `transport=False`; do not promise that every `pre_tool_call` approval directive will appear on the phone through this transport.

`on_session_end` describes an agent-run boundary, not necessarily permanent conversation closure. Finalize, reset, and delete have separate semantics. Background delivery must use durable state rather than assuming a process-local hook will always run after a crash.

Sources: [registration](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L437), [approval caller](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tools/approval_prompt.py#L199), [generic gate](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tools/approval.py#L774), [hook dispatcher](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_dispatch.py).

### Available plugin surfaces

| Surface | Purpose | Notify relevance |
| --- | --- | --- |
| Native tools, hooks, middleware, slash/CLI commands, bundled skills | Agent operations and lifecycle extensions. | Primary runtime and explicit App/message/decision tools. |
| Model and delegation providers | Inference backends and delegated-work selection. | Reuse Hermes facilities; no replacement needed. |
| Memory and context-engine providers | Persistent memory and compression. | Keep Notify state in plugin storage, not a replacement memory backend. |
| Terminal environment and computer-use providers | Command execution environments and device/computer drivers. | Use the existing execution path for building Apps; preserve approvals. |
| Messaging platform adapters | Gateway routing, inbound events, replies, and connection lifecycle. | Optional later inbound channel. Unnecessary for the first outbound workflow. |
| Desktop SDK | Native Desktop panes, pages, commands, status and settings surfaces. | App/run/decision companion UI. |
| Web dashboard extensions | Separate dashboard tabs, routes, shell slots, themes. | Can reuse a backend, but does not load a Desktop bundle automatically. |
| Model/media/search/browser/secret providers | Dedicated backend contracts and configuration. | Use public contracts if needed; do not monkey-patch core functions. |
| Portable Agent Plugins and configured MCP | Skills and external tool servers. | Official Notify MCP provides broader capability access beside the native bridge. |
| Gateway event hooks and shell hooks | Drop-in handlers or configured commands. | Possible lightweight integrations, without the full native coordination model. |

Source: [official surface map](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), with pinned guide inventory and contracts in [runtime notes](notes/hermes-runtime.md).

## Does official Hermes Mobile render plugin UI?

**No supported route for arbitrary plugin UI in the official native mobile beta was established from the public source and docs. Treat that client as an unsupported UI target for this plugin until its actual build or a published SDK proves otherwise.** This is a compatibility decision, not proof that a private beta contains no renderer. The official page is a [mobile beta waitlist](https://hermes-agent.nousresearch.com/mobile); the attempted public `NousResearch/hermes-mobile-beta` source returned 404. The inspected Hermes tree has Desktop renderer code but no official native mobile application source to audit.

The browser Webapp is a confirmed alternative: a phone browser can use the Desktop workspace and its plugins. That must not be described as the native mobile app rendering plugins. Each possible extension route has a different boundary:

| Route | File and line evidence at the pinned Hermes commit | What it establishes |
| --- | --- | --- |
| Desktop panes and pages | [`website/docs/user-guide/desktop.md:712-721`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/desktop.md#L712-L721) | Desktop loads a local ESM `plugin.js` and contributes UI through its SDK. A Python backend alone does not provide a pane. |
| Desktop UI in a phone browser | [`website/docs/user-guide/desktop.md:732-758`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/desktop.md#L732-L758); [`apps/desktop/src/lib/browser-desktop-plugins.ts:19-49`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/apps/desktop/src/lib/browser-desktop-plugins.ts#L19-L49) | The browser loader reads the serving host's Desktop plugin directory through dedicated HTTP routes. Native-only capabilities still need feature detection. |
| A native client using the gateway | [`hermes_cli/web_server_surface.py:44-68`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/web_server_surface.py#L44-L68), [`:84-91`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/web_server_surface.py#L84-L91); [`hermes_cli/web_server.py:812-820`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/web_server.py#L812-L820) | The Desktop-plugin HTTP routes are enabled only for `webapp`; `gateway`, `serve`, and `dashboard` return 404. Connecting to Hermes's native-client gateway does not itself deliver Desktop plugin code. This does not rule out a separate renderer in an unavailable client. |
| Plugin cards and tool views | [`website/docs/developer-guide/desktop-plugin-sdk.md:1106-1164`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/desktop-plugin-sdk.md#L1106-L1164), [`:1181-1246`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/desktop-plugin-sdk.md#L1181-L1246) | Transcript directives, interactive HTML previews, and custom tool-media views are real Desktop SDK features. An unclaimed directive remains plain text. They are not a documented cross-client native mobile card protocol. |
| Web Dashboard UI | [`website/docs/user-guide/features/extending-the-dashboard.md:9-20`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/features/extending-the-dashboard.md#L9-L20) | Dashboard uses its own manifest, JS bundle, and SDK. It shares a backend namespace with Desktop, not a frontend renderer. Neither SDK documents delivery into the native mobile beta. |
| Messaging adapters | [`hermes_cli/plugins.py:779-809`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L779-L809); [`plugin-catalog/hermes-mobile.yaml:1-18`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/hermes-mobile.yaml#L1-L18) | A plugin can register a platform adapter. The community mobile adapter exposes chat and approval/clarification cards for its author's own clients. It is a community package, not the official mobile beta or an extension loader for it. |

**Product consequence:** Notify is the phone surface: rich pushes, exact approvals and replies, Live Activities where supported, project inboxes, and full hosted Apps. Keep an optional SDK pane in Hermes Desktop and the browser Webapp. Do not depend on the native mobile beta loading that pane or build another general chat client. Backend tools can still serve sessions originating from other clients when the host enables them; that is separate from custom UI rendering.

Desktop plugins are app-level; agent enablement is profile-level. The pane must retain the selected profile/account with asynchronous results and show when its backend is missing. A remote native Desktop installation needs its local UI half; the Webapp loads from the serving host. See [`desktop.md:760-778`](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/desktop.md#L760-L778) and [the full client research](notes/catalog-and-clients.md#where-a-plugin-appears).

## Notify capabilities mapped to Hermes

| Notify capability | Hermes seam | Implementation decision |
| --- | --- | --- |
| Rich notifications: title, body, image, URL, summary, project, App destination | Explicit tool; selected post-tool/finalization events | Publish useful milestones. Do not forward every token or tool trace. |
| Approval, yes/no, text reply | Public approval transport for supported host gates; explicit business-decision tools otherwise | Keep request kind, exact action/version, interaction ID, and digest together. |
| Live Activities and ongoing Android progress | Session/task lifecycle and subagent snapshots | Start once, coalesce stage updates, end on completion/failure/cancellation. Capability-check before claiming display. |
| Inbox projects and archives | Profile/session/project mapping | Retain artifacts and updates across chat turns; map business decisions locally where interaction fields lack project/App support. |
| Hosted Notify Apps | Explicit publish/update tool plus a configured publisher | Deploy, health-check, register, then announce. Maintain one stable App identity per project. |
| App sign-in pass | Hosted App backend and official microAuth SDK | Verify identity on the server; keep agent tokens out of browser code. |
| Saved reply webhooks | Optional hosted receiver and plugin outbox | Verify, persist, deduplicate, reconcile, then resolve the waiting operation. |
| Service event URLs | External event producers | Useful for events that originate outside Hermes; protect generated URLs as credentials. |
| Full MCP surface | Hermes MCP configuration and task-selected toolsets | Preserve broad access while keeping the default model tool list focused. |
| Notify CLI | Optional setup, diagnostics, manual recovery | Structured JSON and argv; no mandatory CLI runtime dependency. |

The public interaction API uses `kind: approval|yes_no|reply`; a service webhook's free-text response type is named `text`. Direct interaction creation does not declare `project`, `appId`, or `correlationId`. A message can contain those supported routing fields, but the plugin must not copy them indiscriminately into an interaction body.

An approval uses `POST /api/agent/interactions` and requires `notifications:send` plus `interactions:create`; reading the answer also needs `interactions:read`. The documented Server integration token preset omits that read scope. Wait uses `GET /interactions/{id}/wait?timeout=...`, capped at 25 seconds per request. Get/wait/cancel describe prompts created by that token; token replacement may complicate recovery.

The accepted state is `kind=approval`, `status=approved`, `response=approve`, matching the saved interaction and action digest before the host deadline. `yes`, a text reply, `timedOut`, provider acceptance, or a queued offline answer is not equivalent. Notify's agent API cannot submit the human answer.

The public schema declares `actionDigest` as a string. Store and compare it as opaque data; it is not the Hermes request digest. Stable idempotency keys are supported on notify/ask, but agent key lifetime and concurrent replay semantics are not fully specified publicly. The spike denies an ambiguous create result and never blindly resends it.

Sources: [deployed Agent OpenAPI](https://notify.belweave.ai/openapi.json), [decisions](https://notify.belweave.ai/docs/ask-decision), [access](https://notify.belweave.ai/docs/access), [delivery](https://notify.belweave.ai/docs/delivery), [API notes](notes/notify-api.md).

### Apps, identity, webhooks, and interface coverage

`POST /api/agent/apps` registers a name and launch URL; repeated registration of the same URL updates it. `PATCH /apps/{id}` updates the saved registration. A notification with `appId` opens that App; an optional destination must remain on its registered origin. A personal registration is private by default. `publicClient: true` enables unrelated viewers to deliberately open the same registration and separately consent; it does not grant management access or create a public catalog. Do not turn this on merely to demo a private personal App.

The App sign-in pass is an ES256 JWT with protected type `notify-pass+jwt`, issuer `https://notify.belweave.ai`, the exact website origin as `aud`, and a pairwise `hk_` subject. Apps on the same origin share the subject; validate `app_id` separately. The current microAuth SDK binds a fresh nonce to the initiating browser, consumes it atomically, and verifies a maximum 120-second pass/challenge lifetime. Profile fields are optional. A website creates and revokes its own sessions after verification. The older `getToken()` path does not provide the same browser-bound challenge. [Apps and pass claims](https://notify.belweave.ai/docs/web-apps), [pinned verifier](https://github.com/Belweave/notify-tools/blob/390013d3e89c23776a0a6087646a4f7f995a0b38/src/microauth/server/handshake.ts).

Do not conflate these three webhook mechanisms:

| Mechanism | Direction and verification |
| --- | --- |
| Service event URL, `https://notify.belweave.ai/hooks/whk_<token>` | External producer sends into Notify. The URL is a credential. Create/rotate returns it; later agent reads redact it. |
| Per-question callback | Notify sends `notification.response` with interaction ID and action digest. Classic callbacks use `Notify-Timestamp` and `Notify-Signature: v1=...`, plus the configured bearer token. Connector callbacks use the fixed connector ingress and their own secret. |
| Saved reply webhook, also named by a `whk_` ID | Notify sends an `interaction.answered|expired|canceled` envelope. Verify `X-Notify-Signature: t=...,v1=...` over raw bytes, and deduplicate `X-Notify-Delivery-Id`. Its envelope lacks the action digest; reconcile through the saved interaction before authorizing. |

Both outbound signature constructions cover `timestamp + "." + rawBody`, but their headers, secrets, payloads, and retry rules differ. Reject future or more-than-five-minute-old signatures, persist before acknowledging, and deduplicate the interaction outcome as well as delivery IDs. Acknowledging receipt does not prove the business action ran. [Webhook reference](https://notify.belweave.ai/docs/notification-api), [receiver contracts](notes/notify-api.md#webhook-directions-and-receiver-contracts).

Live Activities use an activity key for a continuing task and a separate idempotency key for a write. `ifSequence` prevents stale updates. There are device capacity and start-pacing limits; end with explicit final state so failure is not labeled success by an omitted-field default. Android uses an ongoing notification through the same API. Inbox projects are grouping labels, not a project CRUD system. Listing returns a `readThroughToken`; read-all uses that watermark so newer arrivals remain unread. [Progress and grouping details](notes/notify-api.md#progress-and-project-grouping).

The public REST schema exposes 103 operations across 75 paths. Preetham supplied an authenticated schema-only read confirming **99 live MCP tools**, with **38 additions and zero missing names** relative to the initial 61-name public inventory. Bare tool names, required scopes/parameters, and constraints are recorded in the [verified MCP appendix](notes/notify-mcp-inventory.md) and [condensed schema snapshot](notes/notify-mcp-live-schemas.json). The additions cover connectors, token list/revoke, and more service/device/inbox/group/team/on-call/page management. Anonymous discovery's 401 is now only historical context. No MCP tool was called. REST operations must not be mechanically renamed into invented MCP tools. The CLI release and SDK were read at Tools 0.14.2; CLI execution is optional, and the spike runs without it.

The installed Notify skill advertises compatibility with CLI 0.13.0 and differs from deployed documentation on service URL recovery and inbox read-all. Public schemas and pinned release code take precedence for those contracts. Other discrepancies, including idempotency details and CLI stdin expiry handling, are recorded in [API notes](notes/notify-api.md#discrepancies-and-limits-that-affect-implementation).

## Testing and proof

Hermes provides `plugins doctor` for runtime discovery diagnostics and `plugins validate` for catalog admission. Validation uses a recording context; it does not exercise the live approval callback. The spike therefore tests both the real loader/gate and the mocked HTTP contract. Its development tests need no model subscription, Notify CLI, real token, or phone.

The research separately ran 117 focused upstream tests: 116 passed and one macOS portable-validator assertion failed. The failure expects a shorter availability string than the validator returns; the standalone probe still reports a valid package. This is recorded in [runtime notes](notes/hermes-runtime.md). It is not a failure of this plugin's validation and not a claim that the whole Hermes suite passed.

Detailed local results and reproduction commands belong in [VERIFICATION.md](VERIFICATION.md). No production profile was changed, no real push was sent, and no Notify codebase was modified.

## Catalog admission

The catalog is a human-reviewed directory whose trust boundary is an exact source commit. Submission eventually requires a public HTTPS repository with a loadable entrypoint, local `hermes plugins validate ... --install-deps`, then one entry file in `plugin-catalog/<name>.yaml` in a maintainer-reviewed PR. None of those remote actions is authorized in this phase. [Submission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission).

The canonical rules at the pinned source are:

| Rule | Requirement and consequence for this plugin |
| --- | --- |
| 1 | A maintainer reviews and merges the catalog entry. Listing is not self-service. |
| 2 | Pin a full 40-character commit SHA. Branches, tags, and short hashes are not pins. |
| 3 | No self-updating plugin code or remote executable plugin bundles. App content deployment is separate; it cannot replace the installed plugin or Desktop bundle. |
| 4 | Every SHA change gets another reviewed PR. |
| 5 | Submit as the repository owner or a major contributor, except maintainer-curated sweeps. |
| 6 | Declared tools, hooks, middleware, and environment needs must match actual registrations. |
| 7 | The install scanner runs at admission. Dangerous findings fail; caution findings require reviewer attention. |
| 8 | Desktop code stays inside the SDK. No core DOM/store manipulation, prototype patching, dynamic code execution, injected scripts, or unauthorized module imports. |
| 9 | No replacing or rebinding Hermes core at runtime. Use public APIs; undocumented imports and private-method calls warn. |
| 10 | Plugin dependencies have their own security policy and must fit Hermes's fixed constraints. Use bounded compatible versions; no assumption that Hermes's release quarantine covers plugin packages. |
| 11 | Resolve declared secrets through Hermes, including `agent.secret_scope.get_secret`. Do not read `.env`, auth files, vendor CLI credentials, browser stores, or the keychain directly. The operator can provide env values; the plugin uses the profile-scoped route. |
| 12 | Preserve host approvals and unattended-run policy. No bypasses or hanging human waits. |
| 13 | Disclose third-party network calls, outside reads, shell/background behavior, credential handling, and storage. Telemetry is opt-in. |
| 14 | Use a truthful SemVer compatibility floor, matching manifest and entry, and a version label matching the pin. A source date is not a version floor. |
| 15 | Do not submit a skin/fork of a bundled plugin or use Nous branding for a lookalike. |
| 16 | One listing per lineage unless a fork is materially different under the documented conditions; disclose its origin. |
| 17 | Ship reviewable source. Binaries/bytecode or hidden executable payloads are disallowed except the stated provenance-attested native-build path. Setup-time downloads must be official, checksum-pinned, and disclosed. |
| 18 | Browser password-manager backends must come from the vendor at verified tier, or Nous at official tier. Notify does not need this surface. |

The entry needs its name, HTTPS repository URL, exact SHA, description, and maintainer; use `subdir` only if the plugin is not at repository root. Start at `community` tier. Only Nous sets `verified` or `official`. Add a truthful category, version, supported platforms, compatibility floor, and matching capability declarations. Optional banner/screenshots use approved GitHub image hosts; up to six screenshots are supported. README rendering uses the reviewed pin. A removed entry can be blocked from install, enablement, and load; ordinary delisting has different effects.

The spike's production code uses public registration and secret APIs. Its development harness deliberately imports the real host gate to verify behavior; full-tree validation reports that as a warning, documented in the verification record. Before submission, settle the released-version floor and include all network/storage disclosures and UI screenshots. The exploration's source fetch helper downloads only the pinned Hermes test source into ignored local storage; it is not an installed-plugin updater.

Source: [complete canonical policy and entry schema](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/README.md).

## Marketplace lessons and the hackathon

The source-pinned catalog contains 977 entries. Its structural validator returned zero errors and five existing-field warnings. That checks catalog shape, not the runtime reliability of every listed plugin. The focused comparisons below are source reviews; no third-party plugin was installed or exercised.

| Entry | Concrete behavior | Lesson for this entry |
| --- | --- | --- |
| [Phone Harness](https://github.com/phone-harness/phone-harness/tree/7e3ea6cff1377db4d4f37e852c59493120aa52b6/integrations/hermes) | One tool and a pre-tool approval hook drive a phone through local or cloud execution, with bounded execution and a persistent workspace. | Make the visible outcome easy to understand. Keep setup, approvals, external execution, and cost disclosures precise. Its catalog presence does not endorse every internal API choice. |
| [print3d](https://github.com/mfranzon/print3d/tree/ff98a8c07253a90f5e4afefa42c2ffd893797eec) | A portable skill/MCP package builds and checks a printable artifact, renders previews, and ends with a reviewable project file. It does not send a job to the printer. | Show someone using the resulting App. A durable artifact and an honest delivery boundary matter more than a long tool list. |
| [ntfy-approval](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/ntfy-approval.yaml) and [Pushary](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/pushary.yaml) | Phone approvals, notifications, and two-way companion workflows are already represented. | Do not claim the first phone approval integration. Demonstrate what App publication and durable task coordination add. |
| [Super Artifacts](https://github.com/Super-Artifacts/plugins/tree/dce02981a179a09dad6509fe58a3a7b8cf020735/hermes) | Hosted pages, forms, trackers, version history, and reading submissions through MCP and a skill. | A hosted page alone is also established. Connect the usable App to native progress, an exact Hermes approval, and the original task. |

The recommended distinction is the complete workflow: Hermes publishes a useful App, the phone shows progress, a decision affects one original task, and the App and project history retain the result. The plugin owns correlation, expiry, deduplication, and recovery. This is an inference about fit to the supplied judging criteria, not evidence of a judging result or uniqueness across the whole catalog. Pins and reading scope are in [the marketplace review](notes/catalog-and-clients.md#lessons-from-marketplace-entries).

The [public entry form](https://form.typeform.com/to/FwJLvOln), read through its [form-definition API](https://api.typeform.com/forms/FwJLvOln), requires a title, description, contact fields, an X demo-post URL, and a catalog-PR URL. It does not say the PR must already be merged. The supplied brief requires a demo under 90 seconds and scores usefulness, reliability, polish, and creativity. Prepare those materials locally; publication and submission remain outside this phase.

**Planning deadline: November 11, 2026 at 4 PM ET**, as Preetham requested, ahead of the brief's official 5 PM ET. The form's thank-you copy also says 1 PM PST, equivalent to 4 PM ET, so public deadline text is inconsistent. That copy is not proof of a server-enforced cutoff. Target completed submissions by 3 PM ET if later authorized. [Evidence and access limitations](notes/catalog-and-clients.md#hackathon-requirements-and-uncertainty).

## Risks and decisions that affect scope

1. **Hosting is a separate dependency.** Notify registration cannot deploy code. Pick one host and preserve a bring-your-own-URL mode.
2. **Host compatibility needs a release floor.** Pin the tested source and confirm the first supported Hermes release before publication.
3. **Approval coverage is narrower than all human input.** Document exactly which host gates route through the transport; use explicit decision/reply tools for other workflows.
4. **Delivery is not display.** Offline phones, disabled permissions, unsupported builds, and queued Live Activities need honest status and expiry.
5. **Recovery crosses two systems.** A lost create reply, rotated token, duplicate webhook, restart, or stale host request cannot safely grant permission by inference.
6. **Identity is app-scoped.** Pairwise subjects, consent, nonce replay, session revocation, and origin changes need a real backend contract.
7. **Source access is not platform validation.** Desktop/mobile SDK declarations and public Notify docs do not prove the intended phone build renders every surface. The next authorized live test is the gate for those claims.

## Reading record

The runtime researcher read 23 complete relevant Hermes guides and the loader, manifest, dispatcher, and approval implementations. Its reading ledger is `.local/research/docs-read.json`, with pinned paths and hashes. [Runtime notes](notes/hermes-runtime.md) contain the full technical findings. [Notify notes](notes/notify-api.md) contain public API evidence and distinguish unauthenticated documentation from untested account behavior. [Catalog and client notes](notes/catalog-and-clients.md) record all 18 admission rules, marketplace source reviews, Desktop/browser boundaries, and hackathon evidence.
