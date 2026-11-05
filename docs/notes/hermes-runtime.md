# Hermes plugin runtime research

Research date: November 4, 2026, America/New_York. All source claims below refer to [NousResearch/hermes-agent at `ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`][commit], committed at `2026-11-04T21:38:09Z`. This is a source pin, not a claim about a released Hermes version.

Hermes has a public `ctx.register_approval_transport(name, present_fn)` API. It is the best starting point for a Notify approval integration: the plugin presents a host-created request and returns a correlated decision; Hermes retains command checks, allowed approval scopes, persistence, and the final authorization. Approval observer hooks alone cannot return an approval. This API is explicit in the pinned source and exercised by upstream tests, although the main plugin guide does not describe it in its registration walkthrough. [Registration implementation][registration]; [request and response contract][transport]; [integration tests][approval-tests].

The research ran 117 upstream tests: 116 passed and one validator assertion failed on macOS. It also verified that approval transport workers do not explicitly propagate the caller's context variables. The proposed Notify bridge must capture profile configuration before entering that worker and use explicit request correlation. No live Notify request, phone interaction, model call, or command execution was performed by this research.

## Sources and scope

The public entry point was the [official plugin developer guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins). The source archive was downloaded directly from GitHub without cloning or adding a remote. It is unpacked at `.local/hermes-source`; metadata is in `.local/research/hermes-source.json`. Its archive SHA-256 is `975c0f4f49a102dc59a38659596d064877904c821802484729bed91a43558f68`.

The complete pinned Markdown for 23 relevant guides was read, including examples: the main plugin guide, observer hooks, middleware, subagent lifecycle, model and memory providers, plugin LLM access, delegation providers, terminal environments, messaging adapters, application declarations, catalog submission, context engines, browser providers and vaults, secret sources, image/video/search providers, Desktop SDK, dashboard extensions, and the user guides for plugins and hooks. The inventory, exact source URLs, line counts, and hashes are in `.local/research/docs-read.json`. This does not claim to cover every recursively linked page on the site.

The manifest parser, discovery implementation, Python loader, hook dispatcher, and approval transport implementation were read in full. Adjacent approval and context paths were traced to their callers. Where narrative documentation and implementation differ, this note uses the pinned implementation and identifies the difference.

## Package, discovery, and lifecycle

A native Python plugin needs `plugin.yaml` and `__init__.py` with `register(ctx)`. Put support modules beside them and use relative imports. The loader imports packages under a `hermes_plugins` namespace, with profile collision handling. A portable Agent Plugins package uses `plugin.json` and supported skills/MCP components instead; it does not supply the native Python registration function needed for this approval transport. [Main guide][guide]; [loader][loader].

Discovery searches bundled packages, the active profile's `plugins` directory, and Python entry points in `hermes_agent.plugins`. Directory packages can be flat or one category deep. A raw manager can opt into project plugins, but gateway sessions ignore project-local plugins. Do not depend on a repository's `.hermes/plugins` being loaded by Desktop or gateway sessions. Directory candidates take precedence over duplicate entry points; later directory sources generally win matching registry keys, with additional protection against impersonating bundled packages. [Discovery][discovery]; [manager discovery and gates][manager].

External plugins require explicit enablement. A disabled entry wins over an enabled entry. Bundled backend and platform packages have special loading paths, so their behavior is not a template for a Notify package. `requires_plugins` influences ordering but is advisory: a missing dependency warns, and cycles fall back to deterministic ordering. Probe dependencies with `ctx.has_plugin()` when correctness depends on them. [Manifest parsing and ordering][manifest]; [manager discovery and gates][manager].

Useful manifest fields are `name`, `version`, `description`, `provides_tools`, `provides_hooks`, `python_dependencies`, `config_schema`, `requires_hermes`, and optional capability declarations. Keep declared tools and hooks aligned with registration for diagnostics and catalog validation. At this pin, `manifest_version` defaults to 1 and future values warn; `api_version` is parsed but is not a complete runtime compatibility gate. `requires_hermes` and the package's declared Hermes dependency participate in compatibility checks. No minimum released version containing approval transports was established. [Manifest implementation][manifest]; [validator][validator].

Python dependencies from an authored `pyproject.toml` take precedence over manifest dependencies for the runtime set. Discovery warns about missing dependencies rather than installing them. Use Hermes package-management admission for a supported installation; do not add packages directly to a managed Hermes environment. A separate disposable research environment is different from a production plugin installation. [Dependency documentation][guide]; [loader][loader].

`register(ctx)` runs for each load, including force reload, rather than once for the lifetime of an installation. Loading has a bounded import/registration worker: the default deadline is 10 seconds, values are capped at 600, and zero runs inline. A timed-out worker can continue, but subsequent registrations from its abandoned context are rejected. Failed loads roll back owned registrations. Force reload unloads owned registrations and cleanup callbacks before loading again. [Loader][loader]; [context lifecycle methods][registration].

Use the context's registration methods, not a manager registry mutation. `ctx.on_unload(callback)` registers cleanup in reverse acquisition order. `ctx.spawn_task(coro, name=...)` supervises an asyncio task and cancels it on unload, but requires an already running loop. These are useful for closing a client and expiring pending work. They do not make a raw transport worker cancellable. Native `in_process` plugins execute trusted Python with the user's privileges. At this pin, `register_approval_transport` is explicitly unsupported in `host` isolation. [Context lifecycle methods][registration]; [isolation support matrix][isolation].

## Registration APIs and hook contracts

The relevant public methods are:

| API | Contract at this pin |
| --- | --- |
| `ctx.register_hook(hook_name, callback, *, hold_stream=False)` | Returns an owned `PluginRegistration`; callback receives keyword payload fields. |
| `ctx.register_approval_transport(name, present_fn)` | Returns `None`; callback takes one `ApprovalRequest` and returns an `ApprovalDecision`, synchronously or asynchronously. Inactive until selected in configuration. |
| `ctx.register_middleware(kind, callback)` | Returns an owned registration. Kinds are `tool_request`, `llm_request`, `tool_execution`, and `llm_execution`. |
| `ctx.register_tool(name, toolset, schema, handler, ...)` | Registers a model-facing tool; handlers receive the argument mapping and context keyword arguments and return the tool's serialized result. Registration can return `None` when rejected. |
| `ctx.get_config(key, default)` | Reads this plugin's `settings` subtree, with legacy `config` fallback. Capture values while the correct profile is active. |
| `ctx.on_unload(callback)` / `ctx.spawn_task(coro, name=...)` | Owned cleanup / supervised asyncio work, respectively. |

Signatures and ownership come from [PluginContext][registration]. Hook dispatch filters fields for callbacks with narrow signatures, but accepting `**kwargs` is the documented way to tolerate additive payload fields. The complete implemented hook-name set is `VALID_HOOKS` in `hermes_cli/plugins.py`; use it instead of a prose count in older guides. [Dispatcher][dispatch]; [hook names][hook-names].

The important callback shapes and return values are:

| Hook | Payload and meaning | Return behavior |
| --- | --- | --- |
| `pre_tool_call` | `tool_name`, `args`, `task_id`, `session_id`, `tool_call_id`, `turn_id`, `api_request_id`, and middleware trace when available. | `None` observes. `{"action": "block", "message": ...}` blocks when the message is nonempty. `{"action": "approve", "message": ..., "rule_key": ...}` requests Hermes human approval; it does not approve execution. `{"action": "modify", "args": {...}}` merges argument changes. |
| `post_tool_call` | `tool_name`, `args`, `result: str`, `task_id`, `duration_ms`, and additional status/call identifiers when available. | Return ignored; use the dedicated transform hook when changing results. |
| `transform_tool_result` | `tool_name`, `args`, `result: str`, `task_id`, and additional call/status fields. | First returned `str` replaces the result, including an empty string. `None` leaves it unchanged. |
| `pre_llm_call` | `session_id`, `user_message` as text or content parts, `conversation_history`, `is_first_turn`, `model`, and `platform`. | Nonempty `str` or `{"context": ...}` injects context; `{"action": "block", "message": ...}` blocks. `None` does nothing; failures are generally skipped. Fires once per turn, not per HTTP request. |
| `pre_approval_request` | Command, description, pattern keys, session key, surface, and available session/turn/tool IDs. Selected transports also supply `request_id` and `request_digest`. | Observer only. Cannot grant, deny, or replace the approval result. |
| `post_approval_response` | The same approval correlation plus `choice`, including transport failure outcomes. | Observer only. |
| `on_human_input_request` / `on_human_input_resolved` | Kind, redacted prompt, available session/platform metadata, and a separate human-input request ID. Covers approval, clarification, and sudo flows. | Observation, without exposing secret answers. These IDs are distinct from transport approval IDs. |
| `on_session_start` / `on_session_end` | Agent run boundaries and available session/turn data. | Observation. `on_session_end` is not a guarantee that the conversation has permanently closed. |
| `on_session_finalize` / `on_session_reset` | Finalization or replacement of an active session; gateway reset includes outgoing and replacement identity, while CLI/TUI fields are narrower. | Finalize can return a notice string or message mapping on supporting surfaces. Reset is observation only. Do not rely on the main guide's simplified “ignored” summary for finalize. |
| `on_session_delete` | Committed deletion/archive identity, reason, profile, and optional deleted-ID collection. | Process-local observation after commit, not a durable delivery queue. |

These are selected fields rather than exhaustive schemas; absent context remains absent. [Hook guide][hooks]; [observer schema][observer]; [approval hook caller][approval-context]; [selected transport caller][prompt].

Hook failure policy is not uniform. `pre_tool_call` fails closed on exceptions or timeout. A block with a nonempty message wins over approval directives; the first approval request wins; argument edits merge in registration order. Most bounded observer/transform hooks skip failed callbacks. The default hook deadline is 30 seconds, capped at 600, with zero disabling the worker deadline. `pre_approval_request`, `post_approval_response`, human-input hooks, and finalization/reset hooks are not in the general bounded-hook allowlist. Keep their callbacks short and perform no network wait there. The transport deadline starts after the pre-approval observer has returned. [Dispatcher][dispatch]; [directive resolution][directives]; [selected transport caller][prompt].

Request middleware runs before the tool approval path and can replace request data. It returns a replacement rather than depending on mutation of a discarded copy. Execution middleware can call the next handler once or short-circuit; failures before invoking the next handler can fall through. It is therefore unsuitable as the sole authorization gate. Neither middleware kind is necessary for the first Notify approval proof. [Middleware guide][middleware]; [middleware chain tests][middleware-tests].

## Approval transport and correlation

Registration names are unique per manager/profile, normalized to lowercase, and limited to `[a-z0-9][a-z0-9_-]{0,63}`. `builtin` is reserved. The registered transport is removed on unload. A profile-home check prevents resolving a transport registered for another active home. Selection is explicit:

```yaml
plugins:
  enabled: [hermes-notify]
  isolation: in_process
approvals:
  mode: manual
  timeout: 30
security:
  approval:
    transport: notify
```

This is proposed local configuration for a plugin registering the name `notify`; it was not applied to the user's Hermes home. Omitting `transport_fallback` preserves denial when the selected transport fails. Only explicit `transport_fallback: builtin` enables another prompt surface. Failure while redacting/building the request denies even with that fallback configured. [Registration][registration]; [transport selection][prompt].

The frozen schema-1 request contains `request_id`, `digest`, `command`, `description`, `pattern_key`, `pattern_keys`, `surface`, `timeout_seconds`, and `allowed_choices`. The command and description are force-redacted before the callback. Pattern keys remain metadata and should not be treated as safe free-form text. The digest binds a new UUID and the canonical request fields to an internal session key. That session key is **not a field on the callback's request object**. [Request schema][transport]; [request construction][prompt].

Return `request.respond(choice)`, where the choice is one of the values actually offered by `request.allowed_choices`. The possible values are `once`, `session`, `always`, and `deny`, but not every request offers all four. The host requires an actual `ApprovalDecision` with matching request ID and digest. A string, dictionary, stale response, or broader scope is rejected. A Notify reply should be translated into a decision for the saved host request only after its own identity and correlation checks succeed. [Response validation][transport].

Hermes invokes the callback on a bounded daemon thread; async callbacks are resolved there. The global limit is eight active workers. Timeout, interruption, exception, invalid response, stale response, unavailable transport, or exhausted capacity denies by default. A timed-out worker is not terminated: its eventual result is discarded, and its slot remains occupied until it exits. The plugin needs shorter network deadlines and its own cancellation/expiry logic. A reload also cannot forcibly stop a raw worker already running. [Worker implementation][transport].

Hardline blocks and other core policy checks remain ahead of the human transport. Existing allow rules, session approvals, bypass modes, or unattended/cron policy may resolve a request without calling it. A transport is a replacement presentation channel for an approval that Hermes has decided to request, not an observer of every command or a mechanism to impose approvals on all execution. Smart approval can also decide before human presentation or restrict the available scope. [Approval gate][approval-gate]; [hardline and routing tests][approval-tests].

### Context constraint verified locally

The transport worker creates a plain `threading.Thread` without explicit `contextvars.copy_context()`. In the tested CPython 3.14.8 runtime, `sys.flags.thread_inherit_context` was zero and a caller marker was absent in the transport. The same marker survived a bounded `pre_tool_call` callback, whose dispatcher explicitly copies context. This is a verified result for this runtime, not a claim that every Python build uses the same thread inheritance default. Receipt: `.local/research/contextvars-probe.json`. [Transport worker][transport]; [hook context propagation][dispatch].

Recommended design, not an existing Hermes guarantee:

1. During `register(ctx)`, capture the profile-bound configuration and initialize the client and durable-state handles while the correct profile is active. Do not first resolve ambient configuration, secrets, or a lazy state handle inside the approval worker.
2. In a fast `pre_approval_request` observer, retain a bounded mapping from transport `request_id` plus `request_digest` to the supplied session key and optional session/turn/tool IDs. Do not send the internal session key to a phone by default.
3. In the transport, join against that mapping and store a separate mapping to the Notify decision ID. Return only the original request's correlated decision, once. Unknown or expired mappings deny.
4. On completion, timeout, cancellation, and unload, expire the mapping and close or invalidate outstanding work. Keep concurrent profiles and concurrent calls independent.

Do not join on the human-input hook's request ID: it is a different UUID. Do not use `ctx.inject_message()` as an approval response. That API injects conversational input with its own capability/profile restrictions and explicitly does not replace approval or clarification channels. [Human-input implementation][human-input]; [conversation API][conversation].

## Other public surfaces

| Surface | Relevance to this integration |
| --- | --- |
| Model-facing Python tools | Appropriate for explicit Notify actions such as creating or updating an App; separate from the human approval transport. |
| `ctx.post_message()` and message handles | Post/edit into the currently bound gateway conversation. They do not provide a general background cross-chat addressing API. |
| `ctx.inject_message()` | Conversational follow-up to an allowed session; not authorization, slash-command execution, or a substitute for a pending decision. |
| Messaging platform adapter | Useful if Notify later becomes an inbound chat platform. Requires the platform adapter lifecycle and routing contract; unnecessary for outbound decisions and progress. |
| `ctx.subagent_lifecycle` | Public serializable handles/snapshots for delegated work. Avoid reaching into private agent registries to show progress. |
| Model, memory, context-engine, terminal, browser, and media providers | Dedicated backend contracts and selection paths. They do not need to be replaced to send Notify events. `ctx.llm` is the host-owned route if model access is later needed. |
| Desktop SDK | A separate `@hermes/plugin-sdk` surface for a Desktop panel, commands, and settings. Optional for the Python approval path. |
| Web dashboard extension | A different dashboard SDK and registration mechanism. Do not assume a Desktop plugin bundle loads here. Shared Python plugin API routes can back either UI. |

Sources: [conversation API][conversation], [platform adapter guide][platforms], [subagent lifecycle guide][subagents], [plugin guide and provider links][guide], [Desktop SDK][desktop], and [dashboard guide][dashboard]. The read inventory has exact pinned links for each provider guide.

## Smallest local proof and install recipe

The smallest real proof is a two-file native plugin registering one approval transport, explicitly enabled in an isolated home. The upstream test `test_live_temp_home_fixture_plugin_routes_and_hardline_stays_core_owned` already creates such a package, loads it through real discovery, routes CLI and gateway approval requests, force reloads, and confirms a hardline block never reaches the transport. It calls the guard API without executing the sample commands. That test passed here. [Fixture, lines 443 onward][fixture].

For the proposed Notify proof, replace that fixture's immediate response with a client that creates a decision on a loopback mock Notify server, obtains its reply, verifies its correlation, and returns `request.respond("once")` or `request.respond("deny")`. Add a fast pre-approval observer only when session correlation is required. Exercise denial, no reply before deadline, duplicate/late reply, and mismatched request identity. The critical assertion is that the real Hermes guard returns the expected approved/denied result after the mocked round trip. A direct unit call to the callback would not demonstrate plugin discovery or host response validation.

This research did not implement or claim that mock HTTP round trip. The upstream fixture proves the Hermes portion. The application spike and its Notify contract tests are separate work in this repository.

For a local package, use a disposable home and the pinned Hermes installation. The following is a development recipe, not a command log:

```sh
hermes_notify_repo=/Users/preetham/Code/hermes-notify
hermes_probe_home=$(mktemp -d "${TMPDIR:-/tmp}/hermes-notify-probe.XXXXXX")
mkdir -p "$hermes_probe_home/plugins"
ln -s "$hermes_notify_repo" "$hermes_probe_home/plugins/hermes-notify"
HERMES_HOME="$hermes_probe_home" hermes plugins list
HERMES_HOME="$hermes_probe_home" hermes plugins doctor "$hermes_notify_repo" --ci
HERMES_HOME="$hermes_probe_home" hermes plugins validate "$hermes_notify_repo" --install-deps
HERMES_HOME="$hermes_probe_home" hermes plugins enable hermes-notify
```

Put the proposed configuration above into that temporary home's `config.yaml`, together with a mock-only endpoint and synthetic credentials appropriate to the implementation. Retain the temporary home until its logs have been inspected. The `hermes` executable must come from the intended pinned installation; merely setting `HERMES_HOME` does not select a source version.

Doctor exercises real discovery/import/registration with temporary state and blocks direct Python socket connections during registration; it is not a sandbox. Catalog validation checks package declarations and admission constraints with a recording context. At this pin, the stub accepts public methods such as `register_approval_transport` as no-ops, so a passing validation does not exercise the callback or its return contract. It also does not reproduce every runtime context property. Run the real guard test too. [Doctor documentation][guide]; [validator][validator]; [catalog requirements][catalog].

Keep registration offline. For catalog preparation, disclose network and storage behavior, preserve host authorization, and use public registration APIs. No remote publication, catalog submission, or production installation was performed in this research. [Catalog requirements][catalog].

## Verification receipts and limits

Tests used a disk-backed isolated environment at `.local/research/venv`, CPython 3.14.8, the upstream `scripts/run_tests.sh`, one worker, a 60-second per-file timeout, and no file retries. Only binary dependencies needed by the focused tests were installed. This was not a full Hermes build or full test suite.

| Upstream file | Result |
| --- | --- |
| `tests/hermes_cli/test_approval_transport.py` | 23 passed |
| `tests/hermes_cli/test_plugins_loader.py` | 1 passed |
| `tests/hermes_cli/test_plugin_manifest_v2.py` | 32 passed |
| `tests/hermes_cli/test_plugin_hook_failure_reporting.py` | 6 passed |
| `tests/hermes_cli/test_plugins_middleware_chain.py` | 5 passed |
| `tests/hermes_cli/test_plugin_validate.py` | 49 passed, 1 failed |

The failure is `test_portable_validation_fails_orphan_and_reports_availability`: its assertion accepts exactly `missing_app` or `unsupported_os`, while the macOS validator appends `, path ...` for a located-but-missing application path. A separate probe returned `ok: true` with that detail, confirming a test expectation mismatch rather than a rejected package. The pinned source was not patched. [Assertion][validator-test]; [detail construction][validator-detail].

Logs and probes are local research receipts:

- `.local/research/approval-tests.log`: 23 passes, 3.4 seconds.
- `.local/research/plugin-tests.log`: 93 passes and the one failure, 26.3 seconds.
- `.local/research/contextvars-probe.json`: transport context loss and hook context propagation.
- `.local/research/portable-validator-probe.json`: successful report with the macOS detail string.
- `.local/research/docs-read.json` and `.local/research/hermes-source.json`: reading and source provenance.

Reproduce the focused suite from `.local/hermes-source` using:

```sh
HERMES_HOME=/Users/preetham/Code/hermes-notify/.local/research/test-home \
HERMES_PYTHON=/Users/preetham/Code/hermes-notify/.local/research/venv/bin/python \
HERMES_TEST_FILE_RETRIES=0 \
scripts/run_tests.sh -j 1 --file-timeout 60 \
  tests/hermes_cli/test_approval_transport.py \
  tests/hermes_cli/test_plugins_loader.py \
  tests/hermes_cli/test_plugin_manifest_v2.py \
  tests/hermes_cli/test_plugin_hook_failure_reporting.py \
  tests/hermes_cli/test_plugins_middleware_chain.py \
  tests/hermes_cli/test_plugin_validate.py
```

Remaining uncertainties are the minimum released Hermes version containing this API, a supported install of this exact plugin in a full Hermes environment, the Notify HTTP contract and real delivery/reply behavior, and the final catalog validator's handling of the complete package. Those require separate checks; none follows merely from these upstream tests.

[commit]: https://github.com/NousResearch/hermes-agent/commit/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df
[guide]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/plugins/index.md
[registration]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L230
[transport]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/approval_transport.py
[approval-tests]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tests/hermes_cli/test_approval_transport.py
[loader]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_loader.py
[discovery]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_discovery.py
[manager]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L1203
[manifest]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_manifest.py
[validator]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugin_validate.py
[isolation]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugin_isolation.py#L35
[dispatch]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins_dispatch.py
[hook-names]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L109
[hooks]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/features/hooks.md
[observer]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/observer-hooks.md
[approval-context]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tools/approval_context.py#L54
[prompt]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tools/approval_prompt.py#L199
[directives]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L1914
[middleware]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/middleware.md
[middleware-tests]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tests/hermes_cli/test_plugins_middleware_chain.py
[approval-gate]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tools/approval.py#L824
[human-input]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tools/human_input_hooks.py
[conversation]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugins.py#L588
[platforms]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/adding-platform-adapters.md
[subagents]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/subagent-lifecycle-api.md
[desktop]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/desktop-plugin-sdk.md
[dashboard]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/features/extending-the-dashboard.md
[fixture]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tests/hermes_cli/test_approval_transport.py#L443
[catalog]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/plugins/catalog-submission.md
[validator-test]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/tests/hermes_cli/test_plugin_validate.py#L69
[validator-detail]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugin_validate.py#L681
