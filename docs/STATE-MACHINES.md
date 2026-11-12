# State machines

How a question and a lock-screen progress activity live inside the plugin. Every state is
stored in the profile journal (`runtime.sqlite3`) before the network call that depends on it,
so a crash, a retried tool call or a restarted gateway resumes the same object instead of
creating a second one. Tests named in the last column cover each transition.

## Question (`notify_ask`)

States: **sending** (intent recorded, request in flight), **unknown** (no reply from Notify;
the outcome is uncertain), **rejected**, **pending** (on the phone), **answered** (`approved`,
`denied`, `yes`, `no` or `replied`), **expired**, **canceled**, and per answer **returned**
(handed to the agent once) and **stale** (answered too late or for a superseded run).

`proceed` is true only for `approved`, `yes` or `replied` that is not stale. Everything else,
including no answer yet, means "do not proceed".

| From | Event | To | What the person and the agent see | Test |
|---|---|---|---|---|
| none | `notify_ask` | sending, then pending | One prompt on the phone. Idempotency-Key derived from the profile, run and content. | `test_business_questions_are_not_host_permissions` |
| none | Same content while the earlier question is still pending and before its deadline (a retried call, a restarted gateway) | pending (same question) | `resumed: true`; no second prompt. | `test_retried_ask_while_pending_resumes_without_a_second_copy` |
| none | Same content after the earlier question was answered, expired or canceled | new pending question | A new prompt; the old answer is never returned for it. | `test_yesterdays_approval_is_never_returned_for_the_same_question` |
| none | Same explicit `idempotency_key` | same question | The caller named one event: its recorded outcome is returned with `resumed: true`. | `test_explicit_idempotency_key_is_the_same_event` |
| sending | No response (network, 5xx, crash) | unknown | "Outcome unknown; no duplicate was sent." Once the question would have expired, the same content is a new question. | `test_unknown_question_outcome_is_never_sent_twice_within_the_window` |
| sending | 4xx, 429 | rejected | One sentence with the fix (`--reauth`, retry after N s). Same content retries the same key. | `test_rate_limit_retains_intent_and_waits_for_retry_interval` |
| pending | `wait_seconds` on `notify_ask` or `notify_replies` ends with an answer | answered | `proceed` per the rule above. The wait releases the runtime lock, so phone approvals and webhook hints keep working. | `test_replies_resumes_a_bounded_wait_and_cancel_withdraws`, `test_a_wait_does_not_hold_the_lock_needed_by_approvals` |
| pending | Wait times out or the wait request fails | pending | `mustPoll: true`, `next` says to keep waiting with `notify_replies` until the agent's deadline, then cancel. A failed wait is `waitError`, not a failure of the ask. | `test_a_failed_wait_still_returns_the_question_it_asked` |
| pending | Signed webhook (`interaction.answered/expired/canceled`) | answered, expired or canceled | The body is only a hint: the plugin re-reads the interaction from the Notify API. With injection allowed, the answer enters the asking session as untrusted user input. | `test_signed_answer_is_pushed_into_the_asking_session` |
| pending | Unsigned, wrongly signed, older than 5 minutes or more than 1 minute in the future | pending | HTTP 401; no read, no state change. | `test_signature_scheme_matches_notify` |
| pending, answered | Duplicate or out-of-order deliveries | unchanged after the first | One API read settles it; a recorded outcome can never change. | `test_replayed_or_reordered_deliveries_settle_once_from_the_api` |
| pending | `notify_cancel` from the asking session | canceled | The prompt is withdrawn. If the person answered first, the answer is kept and returned. | `test_replies_resumes_a_bounded_wait_and_cancel_withdraws` |
| pending | Deadline passes | expired, stale | `pendingQuestions` drops it; a later answer cannot exist (Notify expires it too). | `test_late_business_reply_is_recorded_but_not_injected` |
| pending | Hermes restarts | pending | Durable: `notify_replies` from any session of the profile, or a webhook, settles it. | `test_hint_without_injection_still_settles_for_notify_replies` |
| answered | `notify_replies` | returned | Each answer is returned once, with attribution and `trustedAsInstruction: false`. | `test_business_questions_are_not_host_permissions` |
| answered late or for a superseded run | `notify_replies` | returned, stale | `proceed: false`; never injected. | `test_stale_worker_reply_binds_original_run_and_cannot_inject` |

A question is a business decision. It never satisfies a Hermes command approval: those use
Hermes's own approval request, a single-use ledger and an action digest checked against the
interaction (`hermes_notify/bridge.py`).

## Progress activity (`notify_progress`, and release runs with `progress_enabled`)

States: **running** (job recorded, start queued), **starting** (`startAttempted` recorded,
create in flight), **active** (activity ID and sequence known), **pending update** (update
body recorded before the request), **fallback** (the phone cannot show Live Activities:
ordinary notifications instead), **ended** (`shipped`/`failed`/`canceled` locally; the phone
shows the end line and dismisses it after 60 seconds). **Stale** is shown by the phone itself
when no update arrives for `stale_after_minutes` (default 30).

| From | Event | To | What the phone shows | Test |
|---|---|---|---|---|
| none | `start` | running, then starting, then active | One Live Activity: title and status line, `staleAfterSeconds` set. | `test_job_progress_starts_once_updates_and_ends_truthfully` |
| running, active | `start` again with the same title in the same session | unchanged | `resumed: true`; no second activity. | same |
| starting | Create response lost, then the next delivery | active | The plugin reads the activity by key; it never starts a second one. | `test_activity_lost_start_and_update_reconcile_without_new_start` |
| starting | 404, 422, no capable device or capacity | fallback | Ordinary notifications with the status, and the end line. | `test_job_on_a_phone_without_live_activities_falls_back_to_messages` |
| active | `update` within the progress interval (5 s minimum) | active | Coalesced: the latest values arrive once the interval passes. | `test_activity_start_coalesce_end_and_sync` |
| active | `update` | pending update, then active | `ifSequence` guards the write; a lost response is reconciled by a read. | `test_rejected_activity_update_replays_then_flushes_latest_progress` |
| active | Someone else changed the activity (409) | active | Nothing overwritten; recorded as `progress_failed`. | `test_activity_queued_and_sequence_conflict` |
| active | `end` with `result` | ended | The final status (`Done`, `Failed`, `Stopped` or the given line). Later updates are refused. | `test_job_progress_starts_once_updates_and_ends_truthfully` |
| ended | `start` with the same title | new running job | A new activity; the old one is never revived. | same |
| running, active | Session finalized (CLI exit, `/new`, gateway reset or shutdown) | ended | "Stopped: session ended", delivered before the hook returns. The CLI prints a one-line notice. | `test_ended_session_marks_its_jobs_stopped_on_the_phone`, `test_session_finalize_hook_ends_that_sessions_jobs_and_says_so` |
| active | Hermes is killed | active (locally) | The phone marks it stale after `stale_after_minutes`; Live Activities end on their own after 8 hours. | Not testable locally |
| any | Another session addresses the job | unchanged | 404: jobs belong to the session that started them. | `test_another_session_cannot_drive_or_end_my_job` |
| none | `notify_send` / `notify_ask` | none | Plain messages and questions never start a Live Activity. | `test_plain_send_never_starts_a_live_activity` |
