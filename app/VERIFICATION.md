# Local verification

Verified November 4, 2026 ET. Run these commands from the repository root with the pinned dependencies installed:

```sh
npm --prefix app run check
node worker/scripts/isolated.mjs check
DESIGN_SHOTS_DIR=/tmp/hermes-design-shots npm --prefix app test -- --reporter=line
```

Result: 72 Playwright scenarios, one Chromium worker. The browser host builds and runs the **production Worker** in local workerd with disk-backed SQLite, then forwards loopback requests into it. It has no credentials and blocks outbound services. Private session/workspace responses are intercepted only by Playwright. No test routes or fixtures are copied into the production assets.

## Design coverage

- The official Paper Mono variable WOFF2 and OFL license match the current [official download](https://paper.design/mono/download) byte for byte. Every visible text element, native form control, placeholder and generated text starts with Paper Mono in computed styles. A loaded font face is required, so a declared but missing font cannot pass.
- Each state below passes the font check, text/placeholder contrast of at least 4.5:1, loaded marks, no overflow, and reduced motion. Native input/select probes and remaining release statuses, reply receipts/retries and sign-out failures use the same checks.
- Phone widths 320, 360, 390 and 430px pass. The 900px iPhone Duo inner layout passes; existing 768px and 1440px layout coverage remains. Keyboard focus, touch targets, contract-limit reflow, private-state clearing and text-only rendering still pass.
- First-party HTML, CSS, scripts, SVGs and the shipped browser SDK are fetched from the Worker and scanned for forbidden placeholder copy, em-dash characters and non-house device naming. Generated error documents are scanned too. Legal/provenance text is preserved as attribution, not UI copy. Project-provided text is rendered faithfully and never treated as HTML.
- The official Nous Research woman mark and Notify mark match their recorded SHA-256 digests. Tests require the proper mark on visible provider controls and disallow image recoloring, masking or cropping. See [provenance](public/logos/PROVENANCE.md).
- The disabled primary-button hover regression failed at **1.68:1** before its fix. Enabled, disabled, hover and focus states now meet 4.5:1. Gates suppress the Reply link when its destination is hidden, while keeping Sign out available to an authenticated user.
- Browser 404/configuration-error responses, root, no-script recovery and actual unsupported-browser `/auth.js` behavior use the same styling. API/auth error responses preserve JSON; HEAD returns no body. Four inert recovery assets stay available when origin configuration is invalid; scripts and private routes still fail closed.

## Screenshots

Fresh captures live outside the repository in `/tmp/hermes-design-shots/`. For each state below there are two PNGs: `<state>-390.png` and `<state>-900.png`. Their viewport heights are 844px; full-page captures include content below the fold.

| State filename | Meaning |
| --- | --- |
| `signed-out` | Notify sign-in gate |
| `loading` | Session verification in progress |
| `pending-decision` | Published release with a pending native approval |
| `release-complete` | Completed release and its evidence |
| `error` | Private workspace fetch failed |
| `empty` | No release published for the project |
| `empty-release` | Snapshot with no checks, notes, artifacts or measurement |
| `auth-error` | Actual auth connector in an unsupported browser |
| `root` | Worker root with no project link |
| `not-found` | Worker document 404 |
| `service-error` | Worker configuration-error document |

These are browser test scenarios with synthetic private data. They verify the production HTML, CSS, font, marks and Worker routing; they are not a record of a live release or Notify phone round trip. No captured fixture data ships in `app/public`.

## Full repository checks

Python: 126 passed. Worker: 23 passed. App: 72 passed. Desktop SDK: 9 passed. Desktop backend: 28 passed. Total: **258 tests**. Hermes CLI validation passes all 16 checks; the existing development-helper import warning is unchanged. The official payload scanner passes on a clean working-tree source export.

Gitleaks initially reports three known non-secret matches in the unchanged official SDK: two SHA-256 manifest values whose file names include `generate_secret`, and the JavaScript template that formats dynamically generated private-key bytes as PEM. The source and recorded SDK hashes were verified. Re-running with only those exact finding fingerprints excluded reports no leaks. No source-wide or rule-wide suppression was added.

The mechanical design scan's only finding was the disabled hover contrast issue described above. That finding has an observed failing-before/passing-after browser regression. No Apple build was needed. No account command, deployment or remote write was performed during this pass.

## Integration constraints

- Browser session shape remains `{ok: true, authenticated: true, project}`. The UI requires an authenticated flag and matching project when present.
- Actual native microAuth, physical-phone rendering and production deployment are still separate live checks. The ordinary-browser auth error uses the real built connector and SDK; successful private-state tests use synthetic route responses.
- Native approvals remain in Notify. The app cannot grant host permission through a reply.
- Reply retry identity and private drafts remain in memory only. No secrets, tokens or project fixtures are persisted by these visual tests.
