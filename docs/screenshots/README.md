# Catalog screenshots

These images capture the actual App code in Chromium at a phone viewport, using the synthetic API and authentication fixtures in `app/tests/workspace.spec.js`. They do not show a physical phone, a deployed Worker or live Notify delivery.

| File | Playwright scenario |
| --- | --- |
| `release-phone.png` | Running release displays measured progress, checks, notes and safe artifacts. Original `running-phone.png`. |
| `approval-phone.png` | Native approval status is separate from written replies. Original `awaiting-approval-phone.png`. |
| `shipped-phone.png` | Shipped state has a distinct result and stops automatic polling. Original `shipped-phone.png`. |

Captured November 4, 2026 ET during the 42-scenario App suite. See [App verification](../../app/VERIFICATION.md) for original output paths and reproduction. The test fixture's version, timestamps and example artifact URLs are illustrative. The screenshot SHA URLs in the catalog draft must be replaced with the final public commit before submission.
