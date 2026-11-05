# Catalog, clients, and hackathon research

Research date: November 4, 2026, Eastern Time. Hermes source and documentation are pinned to [`ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`][hermes-pin]. Public pages were checked on November 5 UTC. This is a source review, not a claim that the Desktop UI, official mobile beta, or third-party plugins were exercised.

**Plan to November 11 at 4 PM ET.** Preetham requested this earlier target after the research. The supplied brief says 5 PM EST; the public submission form's thank-you text instead describes the end as 1 PM PST, which is **4 PM EST**. Preserve that source discrepancy and finish before the earlier time. Details and evidence are below.

For Notify, the supported route is a standalone Python plugin, optionally with a Desktop SDK half. The browser Webapp can load Desktop plugins from its serving host. Support for arbitrary plugin UI in the official mobile beta remains unverified. A phone notification or approval alone is already represented in the catalog; the stronger proposed product is a useful App, persistent project state, progress, and an exact decision connected to the original Hermes task.

## Catalog admission

The [submission guide][submission] and [canonical catalog README][catalog-readme] contain the same 18 admission rules. Their marked rule sections were compared locally and are identical at this pin.

| Rule | Requirement and consequence for Notify |
| --- | --- |
| 1. Maintainer review | Admission is a PR to `NousResearch/hermes-agent`, reviewed and merged by a maintainer. There is no automatic registry submission. |
| 2. Exact commit | Pin a full 40-character commit SHA. Branches, tags, and short hashes do not identify an admissible release. |
| 3. No self-update | Installed catalog code cannot download replacements for itself, including remote plugin bundles. Updates use a reviewed catalog pin change and `hermes plugins update`. Keep generated user Apps separate from the plugin's executable update path. |
| 4. Review every update | Each SHA bump is a new PR. Review covers the adopted upstream commit range, not just the new YAML value. |
| 5. Eligible submitter | The repository owner or a major contributor submits it. Maintainers can curate reviewed batches; owners retain the right to change or remove those listings. Drive-by submissions of unrelated repositories are declined. |
| 6. Accurate capabilities | Declared tools, hooks, middleware, and required environment variables must reflect the pinned implementation. Include every registered surface; do not describe a transport as a model tool when it registers no tool. |
| 7. Scanner findings | Admission runs the install scanner. A dangerous verdict fails; caution findings require reviewer attention. An exact catalog-pin install can accept reviewed caution findings without another prompt, but dangerous findings still block. |
| 8. Desktop SDK only | Desktop code has the renderer's authority, not a capability sandbox. Use SDK contributions. No core/browser prototype patching, dynamic evaluation, remote or internal bundle imports, script injection, core DOM manipulation, or internal stores. Raw bridge calls and suspicious selectors produce review warnings; some violations require manual review. |
| 9. No core replacement | Do not replace or wrap Hermes functions, methods, module attributes, or private tables. Use public hooks, middleware, providers, and registration APIs. Private imports/calls can produce warnings even without mutation. Request a public hook when one is missing. |
| 10. Dependency policy | Plugins do not inherit Hermes's three-day dependency release quarantine. Dependencies must respect Hermes's fixed core constraints. Use an old enough compatible lower bound and an upper bound; maintain a plugin quarantine policy where practical. A recent minimum alone is not a reason to hold admission. |
| 11. Hermes owns credentials | Read declared secrets through `agent.secret_scope.get_secret`. Subscription credentials use `credentialed_provider_request` with `requires_auth`. Third-party OAuth uses a declared `oauth:` client and the same helper, with HTTPS endpoints and appropriate API hosts. Do not read credential files, another CLI's login, browser profiles, or the keychain directly; do not implement token refresh or impersonate a vendor client. |
| 12. Respect approvals | Never auto-approve, disable guards, or launch children in an inherited bypass mode to perform unapproved work. Human waits must end cleanly or time out in unattended operation. |
| 13. Disclose behavior | README and PR must disclose third-party network calls, reads outside plugin data, commands, persistent background work, and credential storage. Telemetry and usage reporting are opt-in. |
| 14. Truthful compatibility | Use a released SemVer `requires_hermes` floor, never a date or a future release. Repeat it in the native manifest and entry. Portable packages use the entry's floor. Version labels must match the code; dependencies must resolve under core constraints. Do not infer Notify's minimum version solely from another plugin's floor. |
| 15. No bundled-plugin forks | Changes to bundled plugins belong upstream. A renamed skin or vendor lookalike is not a separate catalog product under Nous branding. |
| 16. Distinct lineage | A fork must have materially different architecture/transport, or a missing capability whose upstream PR was declined or unanswered for 30 days. Small rebrands are declined. Accepted forks disclose their origin. |
| 17. Reviewable payloads | Do not bundle opaque native binaries, WebAssembly, Python bytecode, or archives hiding them. A necessary native component needs a public build in its own repository and a GitHub provenance attestation tied to the pinned source commit. Setup-time downloads must come from the upstream tool's official source, use a checksum pin, and be disclosed. |
| 18. Vendor password managers | A browser-vault login backend must come from the password-manager vendor at maintainer-assigned verified tier, or Nous at official tier. The runtime checks its own install provenance and reviewed pin; local, ordinary Git, project, pip, and override installs cannot relax this rule. Notify should not implement such a backend. |

Rules 3 and 9 are design-level admission blockers. The review process is a point-in-time review of a commit, not a security audit or a guarantee about later code. Delisting removes discovery but leaves installed copies; security/policy removal uses `removed.yaml` and blocks normal install, enable, update, and load paths. [Catalog policy][catalog-readme]; [catalog user guide][catalog-guide].

### Entry and package

The native layout for this project is `plugin.yaml` plus `__init__.py`; an optional `desktop/plugin.js` adds UI. Portable Agent Plugins v1 packages can instead use `plugin.json`, including MCP declarations and skills. The catalog CI and validator explicitly accept portable-only packages. The submission guide's introductory layout is less precise than that implementation. [Validator][validator]; [CI][catalog-ci].

There is another concrete mismatch: the guide lists `dashboard/manifest.json` as an entrypoint, but the pinned validator's `_check_loadable` recognizes `__init__.py`, `desktop/plugin.js`, `plugin.json`, or a declared language pack with `locales/`. A dashboard-only native package cannot rely on the guide's wording to pass this validator. Notify's Python entrypoint avoids the mismatch.

Required entry fields are `name`, `repo`, `sha`, `description`, and `maintainer`. Useful optional fields are:

| Field | Contract |
| --- | --- |
| `name` | 1 to 64 lowercase letters, digits, underscores, or hyphens. Choose a name representing this project's own identity. |
| `repo`, `subdir` | Public HTTPS repository; optional plain relative subdirectory. No absolute path, backslash, empty interior segment, or `.`/`..` segment. |
| `tier` | Default `community`. Only Nous maintainers assign `verified` or `official`; being the integration vendor does not let us self-assign a tier. |
| `category` | One of desktop, memory, platform, web, tools, voice, automation, models, general. Proposed Notify shelf: automation or tools, settled with the final feature set. |
| `requires_hermes`, `version` | Tested release floor plus a quoted, cosmetic version label. The SHA chooses the installed code. |
| `platforms` | Host OS values: linux, macos, windows; empty means all. This does not claim compatibility with a particular phone client. |
| `capabilities` | Lists for `provides_tools`, `provides_hooks`, `provides_middleware`, and `requires_env`. |
| `title`, `docs_url`, `known_issues` | Card title, documentation, and nonblocking install notes. Disclose required setup and unsupported modes. |
| `image`, `screenshots` | HTTPS GitHub-hosted images; banner displayed at 2:1, gallery at most six images. Pin asset URLs to the reviewed commit. |
| `readme` | Defaults true. The docs build renders the README at the pinned commit, from the entry subdirectory when applicable. |
| `onboarding` | Curated onboarding placement for official/verified entries only. |
| `attested_binaries` | Exceptional native payload paths whose provenance CI verifies. Unnecessary for the proposed Python/JS plugin. |

The structural validator accepts unknown fields with warnings, not silent validation of their meaning. Its version-label grammar allows 1 to 32 characters. The generated listing and author pages come from the entry; there is no second listing to maintain. [Entry schema][catalog-readme]; [structural validator][schema].

### Validation and submission sequence

1. Finish the standalone repository and validate its exact candidate tree with `hermes plugins validate /path/to/plugin --install-deps`.
2. Check real discovery and behavior as well. The validator's capability probe invokes registration through a recording context in a subprocess; passing it is not proof of a working approval round trip, UI, or network path.
3. Prepare one `plugin-catalog/<name>.yaml` entry. In an upstream checkout, run `python3 scripts/validate_plugin_catalog.py plugin-catalog/<name>.yaml`.
4. Prepare the PR description with functionality, public Hermes APIs, all rule 13 disclosures, setup requirements, and UI screenshots.
5. Once publication is separately authorized, publish the reviewed candidate and open the catalog PR. Catalog-entry PRs are data-only: CI permits `plugin-catalog/**` and `contributors/emails/**`, not simultaneous changes to the admission machinery.
6. CI checks schema, obtains the exact source commit, confines paths and symlinks, validates the plugin with dependencies, checks opaque payloads/attestations and self-updaters, then a maintainer reviews the source.

The native validator fails undeclared registered tools/hooks/middleware, while a declared item that did not register is a warning. The catalog entry's capability lists and manifest should still agree under rule 6; do not treat the shape-only catalog check as proof of that agreement. [Capability probe and checks][validator]; [admission CI][catalog-ci].

**Executed here:** the source-pinned structural validator checked 977 catalog files, returned exit 0, and reported zero errors and five warnings. The warnings are unknown fields in existing entries, not failures. Receipt: [catalog-validation.json](../../.local/research/catalog/catalog-validation.json). This did not install or execute all listed plugins, and no catalog PR was created.

## Where a plugin appears

| Surface | Verified behavior | Consequence for Notify |
| --- | --- | --- |
| Native Hermes Desktop | `Capabilities → Plugins` has one row per package, with Desktop and Agent columns. Desktop contributions can add panes, workspace/routes, sidebar items, status, palette commands, keybindings, settings pages, and themes. | Add a small Apps/runs/decisions panel using the SDK if it improves the workflow. A Python plugin alone does not supply a custom pane. |
| Desktop's browser Webapp | `hermes webapp` serves the Desktop workspace to a browser, including a phone browser. It loads Desktop plugins from the serving host's app-level directory and offers installation through Capabilities. | A responsive SDK panel can be available here. Verify it on the intended browser; native-only SDK facilities are not universally available. |
| Web Dashboard | `hermes dashboard` has a separate bundle and manifest system, tabs, named shell/page slots, themes, and backend routes. | A Desktop plugin does not automatically become a dashboard tab. Build this extra frontend only if needed. |
| Official Hermes Mobile beta | The official public page currently presents a beta waitlist. Public sources examined did not establish a third-party UI SDK or arbitrary Desktop/dashboard plugin rendering in the native app. | Do not promise that the Notify pane will appear in the native beta. Test the actual supported build before making that claim. |
| Community `hermes-mobile` | A cataloged WebSocket gateway adapter for an author's own mobile/web client, with separate TypeScript and Python client SDKs. | This is not the official mobile beta and not a plugin-UI loader. It is a possible chat client transport, not a requirement for Notify. |
| CLI, gateway, and messaging | Agent tools, hooks, and approved transports execute in the host runtime when enabled and available to that session. Their client representation depends on that surface's capabilities. | Keep the core Notify workflow usable without a custom renderer or the Notify CLI. Do not make UI installation a hidden prerequisite for host events. |

Sources: [Desktop guide][desktop], [Desktop SDK][sdk], [dashboard extension guide][dashboard], [Webapp plugin router][webapp-router], [browser bridge][webapp-bridge], [official mobile page][mobile-page], [community mobile entry][mobile-entry].

### Desktop details that affect implementation

Desktop plugins are app-level. Agent installation and enablement are profile-level. A unified package's Desktop half is copied into the app's `desktop-plugins` root, so switching profiles does not create separate panes. The panel must derive the active connection/profile from public host state and explicitly handle a missing or disabled backend half. Remote native Desktop needs its own local Desktop copy; the Webapp uses the host serving the browser instead. [Desktop guide][desktop]; [unified package delivery][sdk].

A disk plugin is plain ESM. Supported imports are `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`; JSX source is not compiled at load time. Register components through the scoped context, use `ctx.onDispose` for cleanup, and use public state/actions and `ctx.rest`/`ctx.socket` for the plugin backend. The shared backend namespace is `/api/plugins/<id>`, typically supplied by a declared `dashboard/plugin_api.py`. That shared namespace does not make the two frontend SDKs interchangeable. [SDK][sdk].

The browser bridge reads the host's plugin entry and package marker through dedicated `/api/desktop-plugins/*` routes. New or removed folders are discovered; editing a browser-loaded entry requires **Reload desktop plugins**, since the browser cannot watch host files. Native-only features such as plugin folder access are unavailable there. This is a source-backed browser route, not evidence about the official native phone app. [Router][webapp-router]; [bridge][webapp-bridge]; [Desktop guide][desktop].

The proposed Notify pane should show Apps, a selected task's progress, pending decisions, and delivery failures. It should retain profile/account identity with asynchronous results. Use Paper Mono in plugin-owned UI where the SDK's styling contract permits it; preserve Hermes theme variables and public component boundaries. This paragraph is a design recommendation, not implemented behavior.

## Lessons from marketplace entries

### Phone Harness

Pinned entry: [`phone-harness`][phone-entry], source `phone-harness/phone-harness` at `7e3ea6cff1377db4d4f37e852c59493120aa52b6`, package `integrations/hermes`. The catalog uses the repository's older `ShawnPana` owner spelling; the public source resolves under the current organization.

The plugin registers one `phone_exec` tool, one `pre_tool_call` hook, and a packaged skill when present. The model writes Python that drives a local Apple phone through macOS mirroring, Android through adb, or a cloud phone. The hook requests host approval by default; its `approve` directive means request human approval, not grant permission. Optional classifier auto-run is explicitly documented as a bypassable heuristic. The wrapper uses a process lock, bounded execution, process-group termination, and a workspace that survives calls. [README][phone-readme]; [complete Hermes wrapper][phone-code].

Lesson: one understandable tool, a visible result, and a skill can produce a clear demo. Its README and catalog disclose local script execution, screenshots, account access, cloud cost, and telemetry choices. Notify can borrow that clarity and concrete approval flow. It should not borrow private core imports or assume that catalog inclusion means every implementation choice is an endorsed public API. No real phone was controlled in this review.

### print3d

Pinned entry: [`print3d`][print-entry], `mfranzon/print3d` at `ff98a8c07253a90f5e4afefa42c2ffd893797eec`.

This is a portable package with a skill and stdio MCP server launched through `uvx --from ${PLUGIN_ROOT} print3d mcp`, marked untrusted. The agent writes a Blender script; the pipeline measures/checks the mesh, likeness, and fits, slices with Bambu Studio, returns actionable advice, and writes a 3D viewer and project artifacts. It ends at a reviewable `.3mf`; it never sends a job to the printer. The Desktop preview is an artifact viewer, not evidence that print3d ships a custom Desktop SDK pane. [README][print-readme]; [manifest][print-manifest]; [MCP declaration][print-mcp]; [MCP tools][print-tools]; [pipeline][print-pipeline].

The catalog declares macOS and Linux, a Blender prerequisite, and known issues including missing Bambu Studio checks at install and a skill symlink that prevents Windows support. Some tools annotated read-only still generate derived images and HTML in the job area, a behavior the catalog disclosure makes explicit. [Entry][print-entry]; [tools][print-tools].

Lesson: the artifact is the product. A Notify demo should open and use the generated App, show a consequential interaction, and preserve a useful result. Describe build prerequisites, external commands, and actual delivery boundaries as precisely as this entry describes the last step before printing. Its published benchmarks and screenshots are author-provided evidence; they were not reproduced here.

### Direct overlap

| Entry | What is already represented | Implication |
| --- | --- | --- |
| [ntfy-approval][ntfy-entry] | Phone delivery of Hermes approval prompts through the public approval transport, with deny on failure/timeout. Its source also refuses a request when a worker arrives outside the bound profile. | Native approval interception alone is not a novel claim. Profile correlation and prompt withdrawal deserve explicit tests. [Registration source][ntfy-code]. |
| [Pushary][pushary-entry] | Notifications, questions, native approvals, optional per-tool gates, lifecycle events, and instructions fed into a later turn. | Do not position Notify as the first phone companion or first two-way approval plugin. This comparison is based on the pinned catalog entry, not a full audit of Pushary code. |
| [Super Artifacts][super-entry] | Hosted pages/forms/trackers, stable URLs, version history, and reading visitor submissions through MCP plus a skill. | Publishing a phone-friendly page alone is also represented. Its README exposes the extra OAuth setup needed beyond its portable MCP declaration, a useful onboarding lesson. [README][super-readme]; [declaration][super-mcp]. |
| [Hermes Mobile Adapter][mobile-entry] | A WebSocket platform for custom clients, with chat, media, approval/clarification cards, device routing, and SDKs. | Avoid building a redundant general chat transport. The entry's listening port, token scope, and device-binding disclosures show why transport identity must be explicit. [README][mobile-readme]; [entrypoint][mobile-code]. |

**Proposed distinction:** connect an actual Hermes task to a persistent Notify App, project inbox, native progress where supported, a specific approval, and a reply that changes the original task. The runtime should own correlation, expiry, deduplication, recovery, and publication state. Those guarantees are stronger evidence of plugin value than an instruction telling the model to send a notification. No feature-by-feature uniqueness claim is established by this focused survey. Notify's public interface findings and limits are in [notify-api.md](notify-api.md).

## Hackathon requirements and uncertainty

The primary [submission form][form] was read through its unauthenticated [form-definition API][form-api], without submitting anything. It requires plugin title, description, email, Discord username, an X demo-post URL, and a GitHub catalog-PR URL. It explicitly asks for a demo video on X tagging `@nousresearch` and directs entrants to the official catalog-submission instructions.

The original [Nous Research announcement on X][announcement] is dated November 4, 2026 in X's public embed response and confirms a seven-day event with $20,000 in cash prizes. The embed truncates the longer post. Direct access to the full X page returned 403 during research.

A [third-party mirror][announcement-mirror] reproduces the fuller announcement: 5 PM EST on November 11; usefulness, reliability, polish, and creativity; preference for plugins doing more than a prompt or skill; and a demo under 90 seconds showing working behavior. These align with the supplied brief. Treat them as supplied requirements corroborated by a mirror, not as independently recovered full text from the primary X page.

The form's thank-you description instead says the event ends on November 11 at **1 PM PST**. That equals **4 PM EST**, one hour earlier. It is thank-you copy, not a verified server-enforced cutoff. Neither source should be silently corrected to match the other. The safe planning assumption is to submit before 4 PM EST if authorized, and have the final candidate and video ready well before then.

The public form establishes that a catalog PR link is required; it does not establish that the PR must already be merged at submission time. Catalog acceptance still depends on maintainer review. Do not promise automatic marketplace admission or a judging outcome.

The official mobile page currently offers a waitlist. A [public issue][mobile-issue] reports a full Android testing group, but that is a user report, not a current capacity guarantee. The attempted public `NousResearch/hermes-mobile-beta` repository read returned 404. That does not prove the project does not exist; it prevents verification of its source or plugin UI contract here.

## Focused reading ledger

Core paths below all refer to [Hermes `ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`][hermes-pin]. Linked third-party paths identify their own exact pins.

| Read | Scope |
| --- | --- |
| [Catalog submission guide][submission], [canonical README][catalog-readme], [catalog user guide][catalog-guide] | Complete documents; all 18 rules, entry schema, listing/update/removal behavior. |
| [Desktop Plugin SDK][sdk], [Desktop user guide][desktop], [Extending the Dashboard][dashboard] | Complete documents, including registration, delivery, trust, profile scope, browser differences, and backend mounting. |
| [Build a Plugin][plugin-guide] | Interface map and standalone-package policy. The broader runtime review is in [hermes-runtime.md](hermes-runtime.md). |
| [Catalog CI][catalog-ci], [structural validator][schema] | Admission workflow and schema. Structural validator executed on the pinned catalog. |
| [Plugin validator][validator] | Manifest/loadable checks, registration probe, capability comparison, dependency and scanner orchestration. |
| [Webapp plugin routes][webapp-router], [browser bridge][webapp-bridge] | Complete files; source evidence for loading Desktop entries in the browser Webapp. |
| [Phone Harness README][phone-readme], [wrapper][phone-code], [manifest][phone-manifest] | Complete Hermes integration files. No device/runtime test. |
| [print3d README][print-readme], [manifest][print-manifest], [MCP declaration][print-mcp], [MCP server][print-tools], [pipeline][print-pipeline] | Complete named files. No Blender, slicer, or printer run. |
| [ntfy registration][ntfy-code] | Complete entrypoint; transport registration, profile check, and cleanup hook. Not a complete transport audit. |
| [Super Artifacts README][super-readme] and [MCP declaration][super-mcp] | Complete named files; hosted connector and explicit OAuth setup. |
| [Community mobile README][mobile-readme] and [entrypoint][mobile-code] | Complete named files, plus pinned catalog disclosure. Protocol implementation not audited. |
| [Official mobile page][mobile-page], [public mobile issue][mobile-issue], [hackathon form][form-api], [X announcement][announcement] | Public reads; limitations above. No login, form submission, or outreach. |

Machine-readable public-source receipts and the structural result are under `.local/research/catalog/`. No runtime code, third-party installation, credentials, public posts, repository pushes, PRs, or submissions were changed by this research task.

[hermes-pin]: https://github.com/NousResearch/hermes-agent/commit/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df
[submission]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/plugins/catalog-submission.md
[catalog-readme]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/README.md
[catalog-guide]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/features/plugin-catalog.md
[plugin-guide]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/plugins/index.md
[sdk]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/desktop-plugin-sdk.md
[desktop]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/desktop.md
[dashboard]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/user-guide/features/extending-the-dashboard.md
[catalog-ci]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/.github/workflows/plugin-catalog-ci.yml
[schema]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/scripts/validate_plugin_catalog.py
[validator]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/plugin_validate.py
[webapp-router]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/hermes_cli/web_routers/desktop_plugins.py
[webapp-bridge]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/apps/desktop/src/lib/browser-desktop-plugins.ts
[phone-entry]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/phone-harness.yaml
[phone-readme]: https://github.com/phone-harness/phone-harness/blob/7e3ea6cff1377db4d4f37e852c59493120aa52b6/integrations/hermes/README.md
[phone-code]: https://github.com/phone-harness/phone-harness/blob/7e3ea6cff1377db4d4f37e852c59493120aa52b6/integrations/hermes/__init__.py
[phone-manifest]: https://github.com/phone-harness/phone-harness/blob/7e3ea6cff1377db4d4f37e852c59493120aa52b6/integrations/hermes/plugin.yaml
[print-entry]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/print3d.yaml
[print-readme]: https://github.com/mfranzon/print3d/blob/ff98a8c07253a90f5e4afefa42c2ffd893797eec/README.md
[print-manifest]: https://github.com/mfranzon/print3d/blob/ff98a8c07253a90f5e4afefa42c2ffd893797eec/plugin.json
[print-mcp]: https://github.com/mfranzon/print3d/blob/ff98a8c07253a90f5e4afefa42c2ffd893797eec/mcp.json
[print-tools]: https://github.com/mfranzon/print3d/blob/ff98a8c07253a90f5e4afefa42c2ffd893797eec/src/print3d/mcp_server.py
[print-pipeline]: https://github.com/mfranzon/print3d/blob/ff98a8c07253a90f5e4afefa42c2ffd893797eec/src/print3d/pipeline.py
[ntfy-entry]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/ntfy-approval.yaml
[ntfy-code]: https://github.com/AhmetArif0/hermes-ntfy-approval/blob/95d3a4b838073d6908c578ca1a9f04154349a2cf/ntfy-approval/__init__.py
[pushary-entry]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/pushary.yaml
[super-entry]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/super-artifacts.yaml
[super-readme]: https://github.com/Super-Artifacts/plugins/blob/dce02981a179a09dad6509fe58a3a7b8cf020735/hermes/README.md
[super-mcp]: https://github.com/Super-Artifacts/plugins/blob/dce02981a179a09dad6509fe58a3a7b8cf020735/hermes/mcp.json
[mobile-entry]: https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/hermes-mobile.yaml
[mobile-readme]: https://github.com/geniok1980/hermes-mobile-adapter/blob/91bdca089770c3ad83f157e2932d8c3d9ed55a6a/README.md
[mobile-code]: https://github.com/geniok1980/hermes-mobile-adapter/blob/91bdca089770c3ad83f157e2932d8c3d9ed55a6a/adapter/hermes_mobile/__init__.py
[mobile-page]: https://hermes-agent.nousresearch.com/mobile
[mobile-issue]: https://github.com/NousResearch/hermes-agent/issues/147269
[form]: https://form.typeform.com/to/FwJLvOln
[form-api]: https://api.typeform.com/forms/FwJLvOln
[announcement]: https://x.com/NousResearch/status/2118094256438936062
[announcement-mirror]: https://teapawt.net/NousResearch?sort=popular
