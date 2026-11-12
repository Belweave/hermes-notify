# Changelog

## 0.3.0

Safety
- Asking the same question again no longer returns an earlier answer. Without an `idempotency_key`, identical content reused the first question forever, so a repeated "Deploy to production?" could come back `approved` from a previous day. Identical content now resumes the earlier question only while it is still open; otherwise a new question goes to the phone.
- `notify_ask` and `notify_replies` results carry `proceed`: true only for a timely `approved`, `yes` or `replied`. Denied, no, expired, canceled, stale or no answer all mean "do not proceed".
- A question whose creation outcome is unknown is not asked again until it would have expired, so it never reaches the phone twice.
- Answer webhooks refuse signatures dated more than a minute in the future.

Added
- `notify_progress` shows any long job on the lock screen (iOS Live Activity, Android progress notification, or ordinary notifications as a fallback): start once, update at milestones, end with the real result. It does not need the release workflow or `progress_enabled`.
- Activities carry `staleAfterSeconds` (default 30 minutes), so the phone marks progress stale if Hermes stops reporting. When a session finishes (CLI exit, `/new`, gateway reset or shutdown), the `on_session_finalize` hook ends its jobs as "Stopped: session ended" and prints a one-line notice.
- `notify_replies` takes `wait_seconds` (up to 25) to resume a bounded wait on the newest open question.
- `notify_cancel` withdraws a question that is no longer needed; an answer that arrived first is kept.
- A system prompt section gives each new Hermes session Notify's four rules: ask instead of notify when you need an answer, bound every wait, make prompts stand alone, keep secrets off the phone.
- The Desktop pane and dashboard API show pending questions, label jobs apart from releases, say whether Notify is set up and when each delivery happened.

Changed
- Tool descriptions say when to use each tool and what to do with the result.
- `notify_send` without an `idempotency_key` deduplicates identical content for ten minutes (a retried call or restarted gateway); later identical messages are sent. A deduplicated result says `duplicate: true`.
- Phone approval prompts end with "Approve runs this once. Deny, or no answer within N min, and Hermes does not run it."
- Failures name their fix: an expired key or missing permission says `hermes notify setup --reauth`, a rate limit says when to retry, an unreachable Notify says a retry will not send a second copy.
- `hermes notify status` shows the plugin version, how answers arrive and an unreachable Notify on one line; `hermes notify test` explains a missing phone; setup steps are numbered consistently.
- `hermes notify webhooks on` no longer asks for a restart: running processes listen at their next Notify call.
- Waits release the runtime lock, so a phone approval is never held up by a question wait.
- On a Hermes without the approval transport API the plugin registers messaging, questions and progress and logs how to update, instead of failing to load.

Fixed
- Plain `notify_send` and `notify_ask` calls with `progress_enabled: true` started a Live Activity named after the project that never ended. The internal run behind them no longer has progress, a hosted workspace or a place in the status pane.
- The answer webhook listener stopped retrying after one attempt when another Hermes command held the port, so a gateway started meanwhile never listened.

Compatibility
- No setting, environment variable or tool argument was removed. Callers that relied on identical `notify_send` content being suppressed for more than ten minutes, or on identical `notify_ask` content returning a closed question, should pass `idempotency_key`.
- Status snapshots gain optional `kind`, `at` and `pendingQuestions` fields; the dashboard API still reads 0.2.x snapshots.
- Two new tools and one new hook are declared in `plugin.yaml` and the catalog entry.
