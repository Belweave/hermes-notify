# Submission checklist

Audited November 4, 2026 ET against NousResearch/hermes-agent commit `ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df` and the complete primary hackathon announcement. **PASS** means an applicable local check already passed; **FIXED** means this audit corrected a repository gap. A process or plan can pass a documentation check while its external action remains pending. These labels do not certify catalog acceptance, a filmed demo or submission.

Source URLs, retrieval time and SHA-256 hashes are in [SUBMISSION-SOURCES.json](SUBMISSION-SOURCES.json). The upstream recursive tree was complete and included `.github/PULL_REQUEST_TEMPLATE.md`, both root contribution languages, and the English/Chinese developer contribution pages. The English root guide is the canonical policy; examples for unrelated core features are not additional entrypoints this plugin must implement.

## Sources

- [Nous Research announcement](https://x.com/NousResearch/status/2118094256438936062) and [submission form definition](https://api.typeform.com/forms/FwJLvOln), read without submitting.
- [Catalog README and entry schema](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/plugin-catalog/README.md).
- [Catalog submission guide](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/plugins/catalog-submission.md).
- [Developer guide and native layout](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/website/docs/developer-guide/plugins/index.md).
- [CONTRIBUTING](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/CONTRIBUTING.md) and [PR template](https://github.com/NousResearch/hermes-agent/blob/ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df/.github/PULL_REQUEST_TEMPLATE.md).

## Hackathon announcement

- **H1 PASS**: Eligible plugin implementation; six native tools, state, approvals and a hosted App supply behavior beyond instructions. Evidence: `__init__.py:4`, `hermes_notify/tools.py:21`.
- **H2 PASS**: Usefulness, reliability, polish and creativity have concrete local evidence; judging outcomes are not claimed. Evidence: `docs/DEMO.md:7`, `docs/VERIFICATION.md:9`, `docs/screenshots/README.md:1`.
- **H3 FIXED**: Demo requirement is explicit: working behavior, under 90 seconds, X post tagging @NousResearch. The 85-second plan is ready; recording/posting remain PENDING. Evidence: `docs/DEMO.md:40`.
- **H4 FIXED**: Entry sequence and required form fields are documented: catalog PR plus X link, title, description, email and Discord handle. Opening/submitting remain PENDING. Evidence: `docs/DEMO.md:40`.
- **H5 FIXED**: Both deadlines are retained: announcement 5 PM EST November 11, form copy 1 PM PST; plan before the earlier 4 PM EST. Evidence: `docs/DEMO.md:44`.
- **H6 FIXED**: The primary announcement permits form submission after PR opening, without prior merge; marketplace acceptance still requires review. Evidence: `docs/notes/catalog-and-clients.md:138`.

## Catalog admission rules

- **R1 PASS**: Maintainer review remains the admission gate; the local draft does not claim acceptance. External PR/merge are PENDING. Evidence: `README.md:11`, `docs/CATALOG_PR.md:3`.
- **R2 PASS**: Entry uses a complete 40-hex pin; screenshot URLs use the same pin. Public reachability of the final candidate remains a publication check. Evidence: `plugin-catalog/hermes-notify.yaml:6`.
- **R3 PASS**: No plugin self-updater or remote code replacement. Evidence: `README.md:116`, official workflow-equivalent self-updater scan: no findings.
- **R4 FIXED**: Future pin changes require a new reviewed catalog PR, matching version and screenshot pins. Evidence: `docs/CATALOG_PR.md:3`.
- **R5 PASS**: Submission is prepared for the author/contributor and the specified Belweave repository; no claim of Nous curation. Evidence: `plugin.yaml:5`, `plugin-catalog/hermes-notify.yaml:5`.
- **R6 PASS**: All six tools, two hooks, empty middleware list and required environment declarations match actual registration. Evidence: `tests/test_registration.py:26`, `docs/CATALOG_PR.md:42`.
- **R7 PASS**: Security scan is safe; all admission checks pass. The development-helper warning is retained and reviewed below. Evidence: complete CLI output below.
- **R8 PASS**: Desktop uses public SDK contributions; no prototype patches, internal markup manipulation or executable injection. Evidence: `desktop/plugin.js:4`, CLI desktop surface check: passed.
- **R9 PASS**: Production uses public registration, session and storage APIs without replacing Hermes core. Development-only imports are disclosed. Evidence: `__init__.py:49`, `hermes_notify/tools.py:45`, CLI no core override check: passed.
- **R10 PASS**: Production Python has no third-party dependencies; development packages are pinned and locked. Hermes core pins are not changed. Evidence: `pyproject.toml:6`, `README.md:111`.
- **R11 PASS**: Credentials resolve through Hermes secret scope; no credential files, keychain or vendor login reuse. Evidence: `__init__.py:25`, `README.md:113`.
- **R12 PASS**: Native requests remain exact, single-use and bounded; denial, timeout and unattended policies fail closed. Evidence: `hermes_notify/runtime.py:328`, `docs/VERIFICATION.md:26`.
- **R13 PASS**: Network, external reads, commands/downloads, background work, stored data/secrets and telemetry are disclosed in both README and PR draft. Evidence: `README.md:105`, `docs/CATALOG_PR.md:51`.
- **R14 PASS**: Version 0.2.0 matches the code; only tested macOS is listed. No unverified SemVer floor is invented; the source-only compatibility limit is explicit. Evidence: `plugin.yaml:3`, `plugin-catalog/hermes-notify.yaml:13`, `docs/CATALOG_PR.md:70`.
- **R15 PASS**: Original standalone product integration; no bundled-plugin skin or competing bundled-plugin fork. Evidence: `docs/CATALOG_PR.md:22`.
- **R16 PASS**: No listed-plugin lineage is copied. The vendored official SDK retains its separate provenance and notices. Evidence: `worker/VENDOR.md:1`, `docs/CATALOG_PR.md:93`.
- **R17 PASS**: Clean candidate export contains reviewable source and inert fonts/screenshots; official payload scan reports no findings. Setup binaries come from pinned official packages and are disclosed. Evidence: `scripts/stage_plugin.py:10`, `README.md:111`, official payload scan: exit 0.
- **R18 PASS**: No browser-vault login backend is registered; community tier is appropriate. Evidence: `__init__.py:4`, `plugin-catalog/hermes-notify.yaml:9`.

## Entry schema and submission layout

- **E1 PASS**: Catalog filename and manifest key agree and use the allowed name syntax. Evidence: `plugin-catalog/hermes-notify.yaml:3`.
- **E2 PASS**: Repository is the user-specified HTTPS Belweave URL. Evidence: `plugin-catalog/hermes-notify.yaml:5`.
- **E3 PASS**: SHA is a full immutable commit, not a branch, tag or short hash. Evidence: `plugin-catalog/hermes-notify.yaml:6`.
- **E4 PASS**: No subdir is needed: manifest and entrypoint are at repository root. Evidence: `plugin.yaml:1`.
- **E5 PASS**: One-line description and maintainer are present. Evidence: `plugin-catalog/hermes-notify.yaml:7`.
- **E6 PASS**: Tier is community; no contributor-assigned official/verified status or onboarding claim. Evidence: `plugin-catalog/hermes-notify.yaml:9`.
- **E7 PASS**: Automation is an allowed category; title is Hermes Pocket. Evidence: `plugin-catalog/hermes-notify.yaml:10`.
- **E8 PASS**: Version is quoted and matches the manifest and project. Evidence: `plugin-catalog/hermes-notify.yaml:11`.
- **E9 PASS**: Only tested macOS is advertised; empty/all-platform metadata is avoided. Evidence: `plugin-catalog/hermes-notify.yaml:13`.
- **E10 PASS**: Three GitHub-hosted HTTPS screenshots are below the six-image limit and pinned consistently. Evidence: `plugin-catalog/hermes-notify.yaml:14`.
- **E11 PASS**: README rendering is enabled; optional image, docs_url and subdir are omitted without placeholders. Evidence: `plugin-catalog/hermes-notify.yaml:12`.
- **E12 PASS**: Known issues disclose full-phone and released-version limitations. Evidence: `plugin-catalog/hermes-notify.yaml:18`.
- **E13 PASS**: Capability mapping contains exactly the four catalog keys; native manifest capability consent is a different API. Evidence: `tests/test_registration.py:49`.
- **E14 FIXED**: PR draft is scoped to one upstream catalog YAML with purpose, surfaces, disclosure lines and screenshot provenance. Evidence: `docs/CATALOG_PR.md:3`.
- **E15 FIXED**: README supplies exact pinned Git/local install paths, activation, configuration and the local demo flow. Evidence: `README.md:9`.

## Developer guide native-plugin contract

- **L1 PASS**: Root plugin.yaml plus callable __init__.py register(ctx) form the native package. Evidence: `__init__.py:4`.
- **L2 PASS**: Manifest identity/declarations, schemas, runtime handlers and registration remain separated by responsibility; example filenames are not mandatory. Evidence: `hermes_notify/tools.py:21`.
- **L3 PASS**: Handlers have host kwargs and declared JSON schemas; six tools and two hooks match registrations. Evidence: `tests/test_registration.py:36`.
- **L4 PASS**: Disabled registration performs no network/secret reads; missing host transport raises a useful error. Evidence: `__init__.py:9`.
- **L5 PASS**: Settings use ctx.get_config, declared types/defaults and public secret resolution. Evidence: `plugin.yaml:14`.
- **L6 PASS**: Durable state uses ctx.state.data_dir, not the install tree; unload closes bounded work. Evidence: `__init__.py:29`.
- **L7 FIXED**: The native entrypoint explicitly registers the packaged skill, whose instructions use its namespaced skill_view identifier. Evidence: `skills/notify-release-workspace/SKILL.md:26`.
- **L8 PASS**: Actual Hermes discovery/registry and local workerd execute the rehearsal; doctor and admission checks inspect the complete package. Evidence: `tests/test_registration.py:138`.
- **L9 PASS**: Optional Desktop and dashboard files use the documented surfaces; backend and Desktop activation remain separate. Evidence: `docs/CATALOG_PR.md:47`.

## Contribution guide and PR template

- **C1 PASS**: Integration belongs in a standalone repository; the future upstream change adds only a catalog entry. Evidence: `docs/CATALOG_PR.md:3`.
- **C2 PASS**: Custom runtime is justified by exact host approval, persistence, retries and session attribution; a skill supplies guidance only. Evidence: `docs/CATALOG_PR.md:62`.
- **C3 FIXED**: Open/closed PR and issue searches plus source/catalog inspection are recorded without claiming exhaustive uniqueness; repeat before submission. Evidence: `docs/CATALOG_PR.md:13`.
- **C4 PASS**: Security boundaries reject invalid inputs, avoid runtime shell interpolation, preserve secret redaction and cover symlink checks. Evidence: `docs/VERIFICATION.md:9`.
- **C5 PASS**: Cross-platform effects are considered; only macOS has evidence. Windows ACLs, subprocess behavior and Linux support are not claimed. Evidence: `docs/CATALOG_PR.md:31`.
- **C6 PASS**: Dependency policy is satisfied by no production Python dependencies, locked dev tooling, immutable upstream source and SDK provenance. Evidence: `pyproject.toml:8`.
- **C7 FIXED**: Audit commits and future upstream title follow Conventional Commits; unrelated prior history is preserved. Evidence: `docs/CATALOG_PR.md:109`.
- **C8 FIXED**: Skill description is one sentence ending in a period and at most 60 characters. Evidence: `skills/notify-release-workspace/SKILL.md:3`.
- **C9 FIXED**: Skill author credits Preetham first; version and MIT license are explicit. Evidence: `skills/notify-release-workspace/SKILL.md:5`.
- **C10 FIXED**: Skill uses the required section order with triggers, prerequisites, invocation, reference, procedure, pitfalls and verification. Evidence: `skills/notify-release-workspace/SKILL.md:13`.
- **C11 FIXED**: Skill names actual installed native tools and terminal/execute_code; no invented MCP dependency or wrapped shell utility instructions. Evidence: `skills/notify-release-workspace/SKILL.md:34`.
- **C12 PASS**: Skill has no platform-specific helper scripts; no unjustified platform gating or extra dependency is added. Evidence: `skills/notify-release-workspace/SKILL.md:22`.
- **C13 FIXED**: Skill package-relocation test lives under tests/skills, uses stdlib only and proves the installed file is registered; suite fixtures prohibit external connections. Evidence: `tests/skills/test_notify_release_workspace_skill.py:9`.
- **C14 PASS**: No new .env.example block, inline parser, new skill helper or core bundled-skill change is required. Evidence: `skills/notify-release-workspace/SKILL.md:17`.
- **T1 FIXED**: PR template purpose, related issue, change type and changed paths are filled without fabricated issue links. Evidence: `docs/CATALOG_PR.md:15`.
- **T2 FIXED**: PR test steps and tested platform are concrete; core tests/lint remain unchecked until the actual upstream PR checkout exists. Evidence: `docs/CATALOG_PR.md:24`.
- **T3 PASS**: Relevant regression tests and approve/deny/timeout rehearsals exist; deterministic proof is separated from the unrun model-driven skill flow. Evidence: `docs/VERIFICATION.md:20`.
- **T4 FIXED**: README, configuration, tool/skill docs and housekeeping applicability are explicit; unrelated core example files remain out of scope. Evidence: `docs/CATALOG_PR.md:99`.
- **T5 PASS**: Screenshots/logs are provided, with synthetic App captures clearly distinguished from live phone evidence. Evidence: `docs/CATALOG_PR.md:81`.
- **T6 PASS**: MIT authorship license and SDK/font third-party licenses are preserved. Evidence: `LICENSE:1`.

## Five correctness fixes and regression proof

The November 4 integration review found the following bugs. Their production fixes landed in `b95b349` and are included in the published catalog pin `8c73716`; this pass builds on Chief Engineer's `db1fdf0`. Tests and evidence were strengthened without changing production code or the pin. Published commits were not rewritten.

For each row, a separate clean export of `db1fdf0` received the updated regression tests and a narrow patch removing only that fix. These are reconstructed pre-fix behaviors, not historical commits. Each before-run exited 1 for the reported assertion; the fixed code passed all ten cases and the complete suite. [REGRESSION-EVIDENCE.json](REGRESSION-EVIDENCE.json) records the exact patches, baseline, code/test hashes, commands and complete-log hashes. The isolated before/after work never modified the main checkout's runtime.

| Finding | Fix and regression | Before the fix | With the fix |
| --- | --- | --- | --- |
| **B1 FIXED** | Reject a historical publication before resuming any side effect, and verify current run ownership before workspace sync. Source: `hermes_notify/publisher.py:55`; regression: `tests/test_runtime.py:60`. | Both incomplete and completed historical retries were accepted; the interrupted publication could overwrite the newer workspace. Two cases failed. | Both cases pass: HTTP 409, zero added requests, and the newer local/remote run remains current. |
| **B2 FIXED** | Re-enqueue durable progress on both owning-session begin and completed-publication resume. Source: `hermes_notify/runtime.py:149`; regression: `tests/test_runtime.py:81`. | After finish persisted and the real runtime unloaded, the Worker stayed `preparing` instead of `shipped`. Both resume-path cases failed. | Both paths ship the saved state, end the original activity, and make no additional requests on a second resume. |
| **B3 FIXED** | Recover an attempted activity start by its original key before deciding whether a terminal run needs an end; missing delivery counters cannot bypass that end. Source: `hermes_notify/progress.py:58`; regression: `tests/test_runtime.py:118`. | The activity stayed `starting` instead of `ended`, with and without a restart. Two cases failed. | Both pass: one start, one key lookup before one end, with no duplicate activity. |
| **B4 FIXED** | Cap UTF-8 reply pages at 96 KiB, reserving envelope space below Python's 128 KiB response limit. Source: `worker/src/store.js:125`; regression: `worker/test/worker.test.mjs:298`. | Real Python collection returned `API response exceeded size limit` for both 70-row ASCII and Unicode cases. Two cases failed. | Both pass through workerd and the actual Python collector: every reply is attributed, returned once and acknowledged; pages advance without loss. |
| **B5 FIXED** | Accept an empty project only for global delivery diagnostics; retain strict workspace and nonempty-project validation. Source: `dashboard/plugin_api.py:125`; regression: `dashboard/tests/test_status.py:95`. | Both a synthetic global record and an actual runtime error changed FastAPI status to 503. Two cases failed. | Both return 200 and preserve all runs; an invalid nonempty delivery project still returns 503. |

Regression commands and full-suite commands are recorded in the evidence JSON and [verification guide](VERIFICATION.md). Worker tests require the root Python environment as documented in [WORKER.md](WORKER.md#local-commands).

## Published candidate

- **P1 DONE**: `8c73716f9adbf6b3e26ec77651cf45508bee3e09` is on public `main` at https://github.com/Belweave/hermes-notify. An anonymous clone checks it out, `gh api repos/Belweave/hermes-notify/commits/<sha>` resolves it, and all three pinned screenshot URLs return HTTP 200 (checked November 4, 2026 ET).

## Pending external evidence and actions

These are not marked pass or fixed because they have not been completed by this local audit:

- Deploy/configure the Worker and verify real App sign-in, deep links, progress, reply and release result on the phone. Only the separate native approval test is proven live.
- Run the model-driven skill flow on the authorized configured host. No LLM execution is implied by the deterministic skill/registration tests.
- Film and measure the actual under-90-second demo; post it on X tagging `@NousResearch`.
- Open the one-file catalog PR as the repository owner/contributor, run required upstream checks, and await maintainer-started CI/review. A merge is needed for listing, not for submitting the entry form.
- Supply the final PR/video links and contact fields in the official form before the conservative deadline. No external message, PR, video post or submission is authorized by this audit.

## Local verification receipt

All suites were rerun after strengthening the five review regressions: **228 passed** in total, comprising Python 126, Worker 23, App 42, Desktop 9 and backend 28. All ten focused regression cases pass with the fixes present and fail with the corresponding fix removed in isolated copies. Current full-suite logs and local approve/deny/timeout receipts are in `.local/regression-proof/full/`; the portable evidence record is [REGRESSION-EVIDENCE.json](REGRESSION-EVIDENCE.json).

The authoritative Hermes source is pinned as above. Validation uses an empty home/profile, disabled project plugins and no operator credentials. The complete source export is scanned, including developer helpers. The development-only private-import warning is expected: those scripts explicitly exercise the real Hermes manager, guard context and admission checker. Production registration uses public APIs. `in_process` is intentional for the approval channel, not a sandbox claim.

### Exact candidate and dependency preparation

The catalog draft pins `8c73716f9adbf6b3e26ec77651cf45508bee3e09`, which contains the audited implementation, README and skill corrections. A following metadata commit updates the entry to that candidate and records this receipt; no runtime code changes occur in that metadata commit. Both the candidate and final HEAD are validated. A commit cannot contain its own SHA.

Command: `.venv/bin/python -m hermes_cli.main plugins validate .local/candidates/8c73716f9adbf6b3e26ec77651cf45508bee3e09/source --install-deps --json`, under the same pinned-source isolation plus `HERMES_RUNTIME_DIR=.local/validation-tools`. Exit status: `0`; all 16 checks pass; security is `safe`. Its full stdout is byte-for-byte identical to the JSON block below (SHA-256 `1263f5a13dde95fe529cd9df4f7de941709ca2c65d6de3637c49b2ce02951cb7`). Full stderr:

```text
⚠ install out of sync (ffmpeg: not installed or outdated; node: not installed or outdated; npm: not installed or outdated; ripgrep: not installed or outdated; venv: out of sync with uv.lock) — this unknown-managed install must rebuild the artifact to fix
  → Resolving Python dependencies…
  ✓ Resolving Python dependencies
  → Installing Python dependencies…
  ✓ Installing Python dependencies
```

The startup warning describes the isolated source installation's optional toolchain. Python dependency resolution and installation complete successfully; this is not proof of a fully provisioned production Hermes host. The warning is preserved, not treated as a plugin admission failure. Raw command, stdout, stderr and result are retained in `.local/candidates/8c73716f9adbf6b3e26ec77651cf45508bee3e09/`.

### Full output of hermes plugins validate at HEAD

The equivalent pinned-source CLI invocation is `.venv/bin/python -m hermes_cli.main plugins validate .local/submission-audit/head --json`. `PYTHONPATH` selects the recorded Hermes source; HOME and HERMES_HOME are isolated. The directory is a clean `git archive HEAD` export when checking the committed result. Full stdout and stderr follow without filtering, and exit status is recorded. A final post-commit rerun must match these bytes; its external receipt identifies the final SHA, avoiding an impossible self-referential commit hash in this file. The separate `--install-deps` candidate receipt records the dependency-prepared admission pass and full setup diagnostics.

<!-- CLI-OUTPUT-START -->
Exit status: `0`. Stderr: empty (0 bytes). Full stdout:

```json
{
  "ok": true,
  "checks": [
    {
      "name": "manifest",
      "ok": true,
      "detail": "plugin.yaml parses"
    },
    {
      "name": "manifest fields",
      "ok": true,
      "detail": "name, version, description present"
    },
    {
      "name": "requires_hermes",
      "ok": true,
      "detail": "not declared"
    },
    {
      "name": "config schema",
      "ok": true,
      "detail": "shape valid"
    },
    {
      "name": "requires_env",
      "ok": true,
      "detail": "all entries UPPER_SNAKE"
    },
    {
      "name": "oauth",
      "ok": true,
      "detail": "not declared"
    },
    {
      "name": "loadable",
      "ok": true,
      "detail": "entry: __init__.py, desktop/plugin.js"
    },
    {
      "name": "python dependencies",
      "ok": true,
      "detail": "none declared"
    },
    {
      "name": "capability probe",
      "ok": true,
      "detail": "register() ran in isolation"
    },
    {
      "name": "declared tools",
      "ok": true,
      "detail": "matches registrations"
    },
    {
      "name": "declared hooks",
      "ok": true,
      "detail": "matches registrations"
    },
    {
      "name": "declared middleware",
      "ok": true,
      "detail": "matches registrations"
    },
    {
      "name": "built-in tool collisions",
      "ok": true,
      "detail": "no collisions"
    },
    {
      "name": "security scan",
      "ok": true,
      "detail": "safe"
    },
    {
      "name": "no core override",
      "ok": true,
      "detail": "no runtime rebinds of Hermes core"
    },
    {
      "name": "desktop surface",
      "ok": true,
      "detail": "stays inside the plugin SDK surface"
    }
  ],
  "warnings": [
    "private core imports (catalog rule 9: public surfaces only; these can break on any release): scripts/release_demo.py:117 gateway.session_context.clear_session_vars; scripts/release_demo.py:118 hermes_cli.plugins.get_plugin_manager; scripts/validate_package.py:23 hermes_cli.plugin_validate.validate_plugin_dir; scripts/release_demo.py:117 gateway.session_context.set_session_vars; scripts/spike.py:50 hermes_cli.plugins.get_plugin_manager. Use ctx.* / documented plugin APIs, or open an issue for the seam you need."
  ],
  "isolation": {
    "verdict": "in_process",
    "host_ready": false,
    "reasons": [
      "__init__.py:35 ctx.register_approval_transport(): approval transports hold the live approval request/response channel"
    ],
    "notes": [
      "dashboard backend API is served through the plugin host (buffered responses)"
    ],
    "ctx_methods": [
      "register_app",
      "register_approval_transport",
      "register_hook",
      "register_skill",
      "register_tool"
    ]
  }
}
```
<!-- CLI-OUTPUT-END -->

### Other command results

```text
.venv/bin/python -m pytest
126 passed in 30.83s

hermes plugins doctor <clean-export> --ci
Plugin Doctor: <repo>/.local/submission-audit/head
  manifest: hermes-notify 0.2.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 6 tool(s), 2 hook(s)

Official validate_plugin_catalog.py <entry> --json: ok=true, errors=[], warnings=[]
Official scan_plugin_payloads.py <clean-export>: exit 0, stdout/stderr empty
Catalog workflow self-updater scan: no findings
Skill format: 58-character description, required section order, attribution and license present
```
