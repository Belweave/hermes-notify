"""Small public Hermes tool surface. Session identity never comes from model input."""

from .runtime import Session

STRING = {"type": "string"}
PROJECT = {"project": {"type": "string", "description": "Short project name, e.g. my-app. Optional for notify_send, notify_ask and notify_replies (defaults to hermes)."},
           "run_id": STRING}
CONTENT = {"name": STRING, "stage": STRING, "summary": STRING, "notes": STRING,
           "progress": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
           "checks": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {
               "label": STRING, "status": {"type": "string", "enum": ["pending", "running", "passed", "failed"]}},
               "required": ["label", "status"], "additionalProperties": False}},
           "artifacts": {"type": "array", "maxItems": 20, "items": {"type": "object", "properties": {
               "label": STRING, "url": STRING}, "required": ["label", "url"], "additionalProperties": False}}}


def schema(name, description, properties, required):
    return {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}


SCHEMAS = [
    schema("notify_release", "Begin, update, finish or inspect a release workspace. Use measured progress or null. Updates require expected_revision. Only finish with an explicit action result can record shipped.",
           PROJECT | CONTENT | {"action": {"type": "string", "enum": ["begin", "update", "finish", "status"]},
           "version": STRING, "expected_revision": {"type": "integer", "minimum": 1},
           "status": {"type": "string", "enum": ["preparing", "running"]},
           "result": {"type": "string", "enum": ["succeeded", "failed", "canceled"]}, "result_summary": STRING}, ["action", "project"]),
    schema("notify_publish_app", "Publish this release to the configured Worker, or register an existing HTTPS App URL. Resume the same durable publication on retry. Does not deploy code.",
           PROJECT | {"name": {"type": "string", "maxLength": 40}, "url": STRING}, ["project"]),
    schema("notify_send", "Send a push notification to the user's phone through Notify. Works on its own; no release run or Worker is needed. A receipt proves provider acceptance only. Reuse idempotency_key for the same intended update.",
           PROJECT | {"title": STRING, "body": STRING, "summary": STRING, "url": STRING, "imageUrl": STRING,
                      "body_format": {"type": "string", "enum": ["text", "markdown"]}, "idempotency_key": STRING}, ["body"]),
    schema("notify_ask", "Ask the user a question on their phone (approval, yes_no or free-text reply). Works on its own. Set wait_seconds (up to 25) to wait for the answer; otherwise collect it later with notify_replies. This never grants a Hermes host permission.",
           PROJECT | {"title": STRING, "prompt": STRING, "kind": {"type": "string", "enum": ["approval", "yes_no", "reply"]},
                      "expires_in_seconds": {"type": "integer", "minimum": 30, "maximum": 86400},
                      "wait_seconds": {"type": "number", "minimum": 0, "maximum": 25}, "idempotency_key": STRING}, ["prompt"]),
    schema("notify_replies", "Collect attributed replies for the original release and calling session. Polls only on demand. Injection additionally requires operator opt-in and host authorization.",
           PROJECT | {"inject": {"type": "boolean"}}, []),
    schema("notify_status", "Read bounded local configuration, release, approval and delivery state. Makes no network requests.", PROJECT, []),
]


def calling_session(kwargs):
    # Public helper reads Hermes's task-local context, including the route key needed by
    # inject_message. It is not a mutable process-global environment guess.
    from gateway.session_context import get_session_env
    key = get_session_env("HERMES_SESSION_KEY", "")
    session_id = str(kwargs.get("session_id") or get_session_env("HERMES_SESSION_ID", "") or "")
    if not key and not session_id:
        # Single-user surfaces (CLI, TUI, cron, scripts) may run without a bound session.
        # They share one local identity instead of failing every call.
        session_id = "local"
    return Session(key, session_id)
