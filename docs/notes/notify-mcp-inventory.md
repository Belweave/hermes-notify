# Notify MCP verified inventory

Verified on November 4, 2026, Eastern Time, from the authenticated `user-notify` client's `GetDynamicTools` schema read supplied by Preetham. No tools were called. The live surface has **99 tools**, with bare names and no host prefix: **38 additions, zero missing names** compared with the initial 61-name public inventory.

[Live schema observations](notify-mcp-live-schemas.json) record every name, required scopes, required parameters, and key constraints. That file is a condensed transcription of the authenticated schemas, not a raw machine-validatable `inputSchema` / `outputSchema` export. [The supplied diff](notify-mcp-diff.md) records the changes. These authenticated observations supersede the earlier public-only inventory.

## All 99 tools

| Family | Count | Exact live names |
| --- | --- | --- |
| Messages | 2 | `notification_withdraw`, `notify` |
| Decisions | 6 | `ask`, `interactions_cancel`, `interactions_create`, `interactions_get`, `interactions_list`, `interactions_wait` |
| Progress | 5 | `activities_end`, `activities_get`, `activities_list`, `activities_start`, `activities_update` |
| History | 2 | `activity_feed`, `events_list` |
| Hosted Apps | 7 | `apps_create`, `apps_get`, `apps_list`, `apps_remove`, `apps_revoke`, `apps_share`, `apps_update` |
| Mini Apps | 9 | `mini_apps_block`, `mini_apps_disable`, `mini_apps_export`, `mini_apps_get`, `mini_apps_list`, `mini_apps_offer`, `mini_apps_remove`, `mini_apps_report`, `mini_apps_review` |
| Inbox | 6 | `inbox_get`, `inbox_list`, `inbox_projects`, `inbox_read`, `inbox_read_all`, `inbox_unread` |
| Services | 7 | `services_create`, `services_delete`, `services_get`, `services_list`, `services_rotate`, `services_share`, `services_update` |
| Devices | 2 | `devices_list`, `devices_remove` |
| Connectors | 7 | `connectors_create`, `connectors_get`, `connectors_heartbeat`, `connectors_list`, `connectors_remove`, `connectors_rotate_secret`, `connectors_update` |
| Teams | 17 | `teams_apps`, `teams_audit`, `teams_clear_domain`, `teams_create`, `teams_delete`, `teams_devices`, `teams_get`, `teams_invite`, `teams_invites`, `teams_leave`, `teams_list`, `teams_remove_member`, `teams_rename`, `teams_request_domain`, `teams_revoke_invite`, `teams_set_role`, `teams_verify_domain` |
| Groups | 5 | `groups_create`, `groups_delete`, `groups_get`, `groups_list`, `groups_update` |
| On-call | 8 | `oncall_create`, `oncall_delete`, `oncall_get`, `oncall_list`, `oncall_me`, `oncall_override_add`, `oncall_override_remove`, `oncall_update` |
| Pages | 4 | `pages_create`, `pages_get`, `pages_list`, `pages_resolve` |
| Reply webhooks | 7 | `webhooks_create`, `webhooks_delete`, `webhooks_get`, `webhooks_list`, `webhooks_rotate_secret`, `webhooks_test`, `webhooks_update` |
| Tokens | 2 | `tokens_list`, `tokens_revoke` |
| Billing | 1 | `billing_get` |
| Current grant | 2 | `auth_revoke`, `auth_status` |

## Verified constraints for the integration

- `notify` requires only `body` (at most 8,000). Title is at most 80, summary 500, project 80, and idempotency key 200. `bodyFormat` accepts `text|markdown`; App IDs use the `app_` form. It returns an `anot_` notification ID.
- `ask` and `interactions_create` require title, prompt, and `kind: approval|yes_no|reply`. Title is at most 80, prompt 2,000, and expiry 30 to 86,400 seconds with a default of 900. `group` and `deviceIds` are mutually exclusive.
- `presentation: live_activity` allows approval or yes/no only, limits prompt to 240 and expiry to 28,800, and rejects URL/image fields. Style, design, accent, and action labels are valid only for this presentation; labels are at most 24 characters.
- Callback accepts URL, a 16 to 512 character token, or a connector target with connector ID, route and path. Saved reply-webhook IDs use `whk_`. Do not conflate a saved webhook ID with a service's credential-bearing event URL.
- `ask` and `interactions_wait` cap each wait at 25 seconds. Legacy values up to 600 are capped. A timed-out wait leaves the interaction pending; it neither cancels nor approves it.
- `activities_start` requires title and status. The limit is five concurrent activities per device, with 422 `ACTIVITY_CAPACITY_EXCEEDED`. High-priority updates have budgets of four per minute and twenty per hour per activity; excess requests downgrade with a reason. Use `ifSequence` for ordering. Supply an explicit final status when ending failed work because the default is `Complete`.
- `apps_create` upserts by URL. App updates can alter `publicClient`; that owner-only operation resets grants and storage. Changing origin clears consent.
- `mini_apps_offer` is limited to one offer per package per minute and never installs a package automatically. Moderation operations require a reason of at most 500 characters.
- `webhooks_create` supports generic, grok, and slack presets, answered/expired/canceled events, and an account-default selection.
- `inbox_list` accepts limits 1 to 50. `activities_list` and `events_list` accept 1 to 100.

For exact per-tool required fields and scopes, use the supplied [99-tool snapshot](notify-mcp-live-schemas.json). For full REST request/response structures, use the separately verified [Agent OpenAPI](https://notify.belweave.ai/openapi.json). MCP wrapper arguments and REST fields are separate interfaces: for example, MCP uses `idempotencyKey`, while REST sends `Idempotency-Key` as a header.

## Scopes and human boundaries

`ask` needs `interactions:create`, `notifications:send`, and `interactions:read`; `interactions_create` needs the first two, while later get/wait/list needs read. Cancellation requires create. This is why creating and waiting separately still needs all three scopes for the complete spike.

Apps and Mini Apps use `apps:read/write`; offers also require `notifications:send`. Activities, inbox, services/webhooks, devices, connectors, teams/groups, and on-call/pages use their corresponding read/write scopes. `teams_apps` also needs `apps:read`. Events/feed need `events:read`, billing needs `billing:read`, and token list/revoke needs `tokens:manage`. The JSON snapshot records each operation's exact scope set.

No live tool creates a human answer, grants hosted-App consent, issues a Notify pass, creates an API token, accepts a team invitation, or acknowledges/escalates an on-call page. Token management exposes list and revoke only. Mini App archive publishing is an exact-byte CLI/API flow, not an inferred MCP tool.

## Discovery history and OAuth

The original anonymous request to `https://notify.belweave.ai/mcp` returned 401. That established an authentication requirement, not absence of tools. The later authenticated schema read supplied by Preetham resolves the inventory gap. Neither step sent a notification or called any of the listed tools.

The public MCP endpoint uses Streamable HTTP with a scoped bearer key or OAuth. Its resource is `https://notify.belweave.ai/mcp`; current discovery advertises `https://clerk.notify.belweave.ai` as authorization server and S256 PKCE. Discover these values rather than hard-coding a historical provider. OAuth identity-token signing metadata is separate from the hosted App's ES256 pass and Notify JWKS. Supported scopes do not mean granted scopes. [MCP reference](https://notify.belweave.ai/docs/mcp), [resource metadata](https://notify.belweave.ai/.well-known/oauth-protected-resource/mcp), [authorization metadata](https://notify.belweave.ai/.well-known/oauth-authorization-server).
