# Notify MCP: live schemas vs inventory

Source: authenticated `user-notify` client, GetDynamicTools (schemas only, no tool calls), 2026-11-04 ET.

Counts: live 99, inventory 61, added (live only) 38, missing (inventory only) 0, changed 0 names. No host prefix: names are bare.

## Added (live, not in inventory)
- connectors (7): create, get, heartbeat, list, remove, rotate_secret, update
- devices: devices_remove
- groups (4): create, delete, get, update
- inbox: inbox_unread
- oncall (6): create, delete, get, override_add, override_remove, update
- pages: pages_list
- services (5): delete, get, rotate, share, update
- teams (11): apps, audit, clear_domain, delete, devices, invites, leave, rename, request_domain, revoke_invite, verify_domain
- tokens (2): tokens_list, tokens_revoke (no create route)

## Spike-relevant constraints (now confirmed)
- notify: required body only. body<=8000, title<=80 (default "Notify"), summary<=500, bodyFormat text|markdown, project<=80, appId ^app_, deviceIds 1..50, group ^dgrp_, idempotencyKey<=200. Returns anot_ id.
- ask / interactions_create: required title<=80, prompt<=2000, kind approval|yes_no|reply. expiresInSeconds 30..86400 (default 900). group XOR deviceIds.
  - presentation=live_activity: kind only approval|yes_no, prompt<=240, expires<=28800, no url/imageUrl.
  - style/design/accentColor/primaryLabel/secondaryLabel (labels<=24) allowed ONLY with live_activity.
  - callback {url, token 16..512, target{connectorId conn_, route, path}}; webhookId ^whk_.
- ask/interactions_wait: <=25s per call, timeoutSeconds up to 600 accepted but capped; timeout keeps prompt pending.
- activities_start: required title<=80, status<=60. key<=100, replace, subtitle<=120, detail<=240, progress 0..1, symbol terminal|code|build|success|warning, style standard|ring|hero|terminal|steps, privacyMode standard|private, expires 60..28800, stale 0..28800. Max 5/device -> 422 ACTIVITY_CAPACITY_EXCEEDED.
- activities_update: priority high limited 4/min, 20/h per activity (downgrades, priorityReason budget_exhausted); ifSequence for ordering. activities_end status defaults "Complete".
- apps_create: required name<=40, url; acts as upsert on existing URL. apps_update: publicClient (owner only; resets grants + storage); new origin clears consent.
- mini_apps_offer: 1 offer/package/minute; never auto-installs. block/disable/remove/report require reason<=500.
- webhooks_create: preset generic|grok|slack, events interaction.answered|expired|canceled, isDefault for account-wide replies.
- inbox_list limit 1..50; activities_list/events_list limit 1..100.

## Scopes (from descriptions)
- notify, notification_withdraw: notifications:send (+oncall:write when oncall set)
- ask: interactions:create + notifications:send + interactions:read
- interactions_create: interactions:create + notifications:send; get/wait/list: interactions:read; cancel: interactions:create
- activities_*: activities:read / activities:write
- apps_*, mini_apps_*: apps:read / apps:write (mini_apps_offer also notifications:send)
- inbox_*: inbox:read / inbox:write; events_list, activity_feed: events:read
- services_*, webhooks_*: services:read / services:write
- connectors_*: connectors:read/write; devices: devices:read/write; billing_get: billing:read
- teams_*, groups_*: teams:read/write (teams_apps also apps:read); oncall_*, pages_*: oncall:read/write
- tokens_*: tokens:manage; auth_status/auth_revoke: any scope
