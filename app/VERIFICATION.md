# Local verification

Commands run in `/Users/preetham/Code/hermes-notify/app`:

```sh
npm install --ignore-scripts --no-audit --no-fund
npm run check
npm test
```

Result: 42 Playwright scenarios passed, one Chromium worker. The final run uses the official downloaded font. No Apple build or large build was needed. Production assets are about 128 KiB on disk, including the font and Worker-owned auth connector.

The font was fetched from `https://paper.design/mono/download`; the archive's unmodified `PaperMono[wght].woff2` and `OFL.txt` are bundled. No external font request occurs at runtime.

## Screenshot outputs

Paths below are relative to `app/`. They are synthetic test scenarios, not evidence of a live release or Notify round trip.

- `test-results/workspace-public-shell-and-f44bb-ease-data-or-fixture-bypass/signed-out-phone.png`
- `test-results/workspace-running-release--c3f94-ks-notes-and-safe-artifacts/running-phone.png`
- `test-results/workspace-native-approval--4d1d3--reply-grants-no-permission/awaiting-approval-phone.png`
- `test-results/workspace-shipped-has-a-di-710b8-and-stops-automatic-polling/shipped-phone.png`
- `test-results/workspace-failed-has-a-dis-2a86c-and-stops-automatic-polling/failed-phone.png`
- `test-results/workspace-responsive-layou-c06a9-o-and-keeps-controls-usable/workspace-360.png`
- `test-results/workspace-responsive-layou-f241d-o-and-keeps-controls-usable/workspace-768.png`
- `test-results/workspace-responsive-layou-4cfdc-o-and-keeps-controls-usable/workspace-1440.png`

Report: `playwright-report/index.html`.

## Integration constraints

- `public/auth.js` and the official SDK bundle are owned by the Worker task. UI tests intercept the connector module and HTTP routes. No production mock path is shipped.
- Session shape matches the Worker implementation: `{ok: true, authenticated: true, project}`. The UI ignores `ok` and requires the authenticated flag and matching project when present.
- The UI uses one combined release/rollback notes field, exactly as the shared contract defines.
- Notify's official entry point is used because the shared document has no native interaction URL. Host decisions remain native-only.
- Auth connector timeouts and native capability behavior belong to the connector. The UI serializes that operation with its own requests and independently verifies the resulting cookie session.
- Reply retry identity lasts for this page's lifetime. Private drafts and receipts are deliberately not persisted in browser storage.
- Live authentication, physical-phone behavior, and actual Worker routing require root's integration checks. No deployment, Notify send, remote push, PR, or commit was performed.
