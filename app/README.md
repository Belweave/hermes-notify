# Release workspace App

Static phone UI for `GET /projects/{project}`. There is no runtime framework, build step, fixture switch, or client token. The Worker copies `public/` into its asset bundle, adds the official Notify SDK, and serves the shell and authenticated API. The Worker owns `public/auth.js`; this task does not modify it.

## Files

- `public/index.html`, `styles.css`, `favicon.svg`: public shell, responsive release sheet, and UI identity.
- `public/app.js`: session lifecycle, polling, reply state, run changes, and sign-out.
- `public/api.js`: serialized requests, 12-second data timeout, response-size and content-type bounds.
- `public/model.js`: schema projection, project and receipt checks, HTTPS artifact validation, and decision text.
- `public/view.js`: DOM rendering using text nodes and known attributes only.
- `public/fonts/`: official Paper Mono variable WOFF2 and SIL Open Font License. Provenance is in [DESIGN.md](DESIGN.md).
- `tests/workspace.spec.js`: browser behavior, trust boundaries, retry races, responsive layout, and screenshots.
- `scripts/test-server.mjs`: loopback-only static test host. It returns 404 for every API/auth route. All fixtures and synthetic sessions exist only in Playwright route interception.

## Local checks

From `app/`:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run check
npm test
```

Playwright is pinned in `package-lock.json`; tests run with one Chromium worker. An installed Playwright Chromium browser is required. `APP_TEST_PORT` can select a different loopback port if 4179 is occupied. The test runner starts and stops its own static server. No production environment, credential, Notify request, or deployment is involved.

## Runtime behavior

The route slug selects both `/auth/{project}/session` and `/api/projects/{project}`. A successful session response must contain `authenticated: true`; a supplied `project` must match. Sign-in calls `connect(project)` and rechecks the server session. The UI does not retain the connector result or handle identity passes. A regular browser without Notify's capability receives an actionable sign-in explanation.

Snapshot reads and reply writes share a queue with session operations and the auth connector. Data requests have a 12-second timeout and 64 KiB response cap. Active updates start at 10 seconds. Unchanged snapshots and failures back off to 60 seconds. Five consecutive failures pause automatic updates; explicit refresh can retry. Hidden/offline views pause timers. Returning to an active view refreshes once. Shipped, failed, denied, and canceled views stop polling, with manual refresh retained.

Replies use `{id, runId, text}` and a cryptographic UUID. Pending sends disable submission. Unknown results preserve the exact payload for an explicit retry. Only a matching `{id, cursor, accepted: true}` receipt confirms persistence. The UI never claims Hermes has read it. A draft from an older run requires review before it is reassigned. Drafts, receipts, and retry IDs are memory-only and disappear on reload, sign-out, or session expiry. After an uncertain send, retry before reloading to reconcile that same ID.

Release notes and rollback notes share the contract's single `notes` field and render as plain text. Artifact URLs must be absolute HTTPS without credentials, whitespace, or backslashes. They open in a new tab with `noopener noreferrer` and a visible hostname. Invalid or regressed snapshots cannot replace the last verified view. Empty contract text fields get explicit, nonnumeric empty states.

There is no host approval action. The current-decision section links to the official Notify entry point and explains how to open the pending native approval. The contract has no verified per-request deep link, so the UI does not invent one. Approval recorded is distinct from shipped.

## Verification and limits

`npm run check` and 42 Playwright scenarios passed locally with one worker. The scenarios cover signed-out and unsupported sign-in, route-specific authorization, running/approved/terminal states, native-approval separation, reply pending/confirmed/error and deduplication, stale runs, expiry and sign-out failure, offline/backoff/visibility, serialized traffic, timeout, unsafe data, text escaping, empty fields, maximum content, and responsive layouts.

Screenshots were inspected at 360px, 768px, and 1440px. The layout also passed a 320px reflow check using contract-limit content. Tests verified actual Paper Mono loading, visible keyboard focus, reduced motion, and at least 44px control dimensions. Computed contrast ratios: body 12.99:1, muted 5.49:1, primary button 7.82:1, warning 7.21:1, error 6.73:1, control border 3.79:1, focus 7.60:1. These are focused checks, not a full accessibility audit.

The screenshots and HTML test report are generated under ignored `test-results/` and `playwright-report/`. The [verification record](VERIFICATION.md) lists exact output paths. This phase does not test a live microAuth exchange, physical phone, or deployed Worker. Worker integration and native sign-in remain root's integration responsibility. There are no shared-contract changes.
