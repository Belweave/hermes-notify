# An 85-second release

The demo follows one release from Hermes to a useful phone App. The current local rehearsal proves its components without pretending a mock is a live phone. The separate one-prompt approval test has passed. Film the complete workflow only after hosting and the multi-update live rehearsal are authorized and verified.

| Time | Show | Say or do |
| --- | --- | --- |
| 0–8 s | Hermes task: release a small project | “Hermes is preparing a release. I can leave the desk without losing the work.” |
| 8–20 s | Notify push opens the release workspace | Show the version, checks, release notes and artifacts. The App already works as a persistent workspace. |
| 20–32 s | Live Activity advances through measured work | Show a real stage change. Use an ordinary progress notification if the target phone lacks Live Activity support. |
| 32–44 s | Write a short reply in the App | “Keep the rollback notes with this release.” Return to Hermes long enough to show the attributed reply in the original task. |
| 44–60 s | One native Notify approval | Read the exact release action and approve once. No App button grants host permission. |
| 60–74 s | Hermes completes and verifies the action | The release command succeeds, then Hermes records shipped. The App changes and the Live Activity ends. |
| 74–85 s | Reopen the App and show saved outcome | “The task becomes a workspace I can use, with a decision tied to the work that asked for it.” |

Allow five seconds for trimming and keep the exported video below 90 seconds. Use one project and one phone. Avoid setup, terminal dependency output, or repeated taps in the recorded flow.

## Rehearsal evidence

From the repository root:

```sh
node worker/scripts/isolated.mjs build
.venv/bin/python scripts/release_demo.py --answer approve
.venv/bin/python scripts/release_demo.py --answer deny
.venv/bin/python scripts/release_demo.py --answer timeout
```

The script always uses synthetic credentials and loopback Notify. It creates an isolated Hermes profile, real tool registrations, and an actual local workerd instance. Workerd uses the production service with a test-only key resolver and an ephemeral signing key; its test entry is excluded from deployment. The browser session exchange still validates ES256, origin, App, owner and one-use challenge. Reply retries use one ID and produce one locally attributed result.

Approve creates exactly one local `release-receipt.json`, then publishes shipped and ends the mock activity. Deny and timeout create no receipt; both stop the action and leave the workspace denied. Each case produces `summary.json`, `workspace.json` and `status.json` under `.local/demo/`. These are the local proof, not evidence of remote delivery or a real release deployment.

## Before filming on the phone

The remaining dependencies are a separately authorized Worker deployment, a securely configured publisher secret, and a verified owner subject for that exact HTTPS origin. The separate one-prompt approval test has passed. Its three approval scopes do not automatically cover Apps and Live Activities; verify the additional scopes before the full rehearsal.

Check the actual phone's consent flow, App cookies, deep link, delivery and Live Activity capability. Then authorize the complete rehearsal's multiple updates and release action. Keep the original one-prompt authorization limited to its original scope. Live webhook delivery is optional for this demo; polling the active approval and collecting replies on demand work behind NAT.

If a permission, network or hosting step fails, show its saved failure and recovery instead of editing it into a claimed successful release. No live recording, public video, repository push or hackathon submission has been made in this local build.
