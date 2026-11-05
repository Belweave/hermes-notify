# Paper design audit

Audited November 4, 2026 ET, before UI edits. Scope: the release workspace in `app/public`, the production Worker router, and the complete built asset set.

References inspected: [Paper](https://paper.design/) and [Paper Mono](https://paper.design/mono). Paper's open spacing, restrained controls and aligned edges fit the existing release sheet. Paper Mono's measured typography and light rules inform this refinement. The requested quiet palette takes precedence over decorative treatments on the reference sites.

## Gaps found

- `app/public/styles.css:35`: form inheritance omits `select` and placeholder declarations. Existing Playwright coverage checks only the body font (`app/tests/workspace.spec.js:393`), so a visible child or native control can silently use another face.
- `app/public/index.html:19` and `app/public/favicon.svg:1`: invented h mark substitutes for the official Nous Research mark. Notify appears in controls without its verified mark. No logo provenance record exists.
- `app/public/index.html:107`: footer slogan adds marketing copy to a task surface. Empty checks, artifacts and notes (`:72`, `:81`, `app/public/view.js:75`) name missing data without a next action. Missing project data is presented as a generic failure (`app/public/app.js:108`).
- `app/public/index.html:28,40,63,86`: repeated labels compete with headings. Decorative section numbers (`:70,75,79`) do not communicate sequence.
- `app/public/styles.css:47,76,99,139`: tight heading tracking and thick colored edges depart from the requested deliberate typography and hairline rules. Multiple colored status fills overwhelm the single accent.
- `worker/src/index.js:22-39`: root and unknown routes depend on bare asset fallthrough; server failures use JSON even for a browser document. Missing, unavailable and no-project pages need the same font, styling and explicit recovery as the app. API errors must retain their JSON contract.
- `app/tests/workspace.spec.js:382`: responsive coverage starts at 360px and does not systematically cover 320-430px, the 900px inner layout, or every gate. No served-asset copy or official-logo hash check exists.

## Verification to add

Check every visible text element, form control and placeholder with computed styles, verify the loaded official font and logo bytes, enforce copy rules on served first-party assets, exercise every gate and release state against the production Worker asset path, and capture phone and wide views. Preserve keyboard focus, contrast, touch targets, reduced motion, secure headers and private data boundaries.


## Additional finding during verification

The mechanical design scan identified a disabled primary button hover contrast failure in `app/public/styles.css`. The active hover selector overrode the disabled background. A browser regression reproduced the failure at 1.68:1 before the fix. Hover styles now exclude disabled controls; the same regression checks the disabled, enabled, hover and focus states against 4.5:1.

The no-script state also now hides the sign-in loading message and gives a reload action after JavaScript is enabled. Once sign-in is verified, the loading message explicitly says the release is loading.

The error/empty screenshots exposed a Reply link pointing into a hidden workspace. Gates now hide that link while retaining Sign out for an authenticated session. The font/state checks also assert this control boundary.

## Outcome

Every listed gap is addressed. The current verification results and reproducible commands are in [the app verification record](../../app/VERIFICATION.md). The [machine-readable receipt](design-validation.json) records source hashes, all 16 admission checks, the contrast regression, reviewed secret-scan false positives and the 22 screenshot hashes. Source and commands use relative paths; screenshot outputs are under the requested temporary directory.
