# Official Notify tools alongside Pocket

Pocket uses the public REST API for deterministic runtime work. The official Notify MCP server and CLI remain useful for broader tasks and operator diagnostics. Neither is loaded or spawned by the plugin. No MCP execution or CLI account operation was performed for this build.

## MCP through Hermes

Hermes supports Streamable HTTP, header environment substitution and server-native tool allowlists. The example below uses the [verified 99-tool inventory](notes/notify-mcp-inventory.md) and the pinned [Hermes MCP configuration contract](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/reference/mcp-config-reference.md). Configure only after the user is ready to connect the account:

```yaml
mcp_servers:
  notify:
    url: https://notify.belweave.ai/mcp
    headers:
      Authorization: "Bearer ${NOTIFY_API_TOKEN}"
    tools:
      include: [apps_list, apps_get, inbox_projects, inbox_list, devices_list]
```

The token stays in the intended profile's secret environment; the YAML stores a reference. The example exposes read tools. Add each tool family and its scopes deliberately for a task. Do not expose all 99 tools on every turn or let a second tool create a duplicate of an in-flight Pocket operation. Apps, inbox and device reads need their respective `apps:read`, `inbox:read` and `devices:read` scopes. The basic approval token is insufficient for those extra reads.

Notify also documents OAuth for MCP. Its OAuth authorization server is distinct from the App sign-in-pass issuer. The [MCP docs](https://notify.belweave.ai/docs/mcp) describe account connection; Pocket does not read or reuse that connection's cached credentials. Setting up MCP is optional and does not change Hermes's native approval policy.

## Optional CLI

The reviewed public Notify Tools release is 0.14.2. The archive, checksum, command names and Node floors were verified during research, but the CLI was not installed or executed here. Use the official [quickstart](https://notify.belweave.ai/docs/quickstart) for a later install and account setup. Do not run a download-and-execute installer as part of loading this plugin.

For a later authorized interaction, the existing CLI can inspect a known interaction using `notify interaction get <id>` or wait using `notify interaction wait <id> --timeout 2m`. Read the returned status: a successful `get` can still report pending. Do not infer execution permission from a CLI exit code or route its answer around Hermes's immutable request. The [API notes](notes/notify-api.md#optional-cli-and-mcp-paths) record exact creation commands, exit-code behavior and limits.

CLI state and plugin state are separate. Pocket reads neither the CLI's token file nor its login cache. Install, enable, status, publish, progress, approval and reply paths all work with `notify` absent from `PATH`.

## Saved reply webhook

The optional receiver is `POST /api/notify/webhooks` on the configured Worker. It accepts the saved generic subscription format, with raw-byte `X-Notify-Signature` validation, freshness checks and durable delivery/outcome deduplication. The Worker secret is `NOTIFY_WEBHOOK_SECRET`. Configure a saved subscription only in a separately authorized live setup; registration and test endpoints themselves can send traffic.

Webhook events carry reconciliation identifiers. The active task's `notify_replies` call fetches authoritative Notify state for a known interaction and acknowledges the event after recording it. They cannot resume a lost native host permission. There is no inbound port on the Hermes machine and no idle background polling loop.

Per-question callback signatures use a different format and are not accepted by this receiver. Inbound Notify service URLs with `whk_` credentials also have a different purpose. See [Worker setup](WORKER.md) and the [webhook contract](notes/notify-api.md#webhook-directions-and-receiver-contracts) before connecting those surfaces.
