"""Translate only a confirmed, matching Notify approval to a one-use Hermes decision."""

import logging
import math
import re
import threading
import time

from .client import NotifyError

logger = logging.getLogger(__name__)
_slots = threading.BoundedSemaphore(2)


class TransportUnavailable(RuntimeError):
    """Notify cannot present this approval. Raised (not a deny) so Hermes applies the
    operator's security.approval.transport_fallback, e.g. the normal terminal prompt."""

    def __init__(self):
        super().__init__("Notify approval transport is unavailable")


class ApprovalBridge:
    def __init__(self, client, ledger, *, timeout_seconds=120, device_id="", is_cancelled=lambda: False, on_state=None):
        self.client = client
        self.ledger = ledger
        self.timeout_seconds = timeout_seconds
        self.device_id = device_id
        self.is_cancelled = is_cancelled
        self.on_state = on_state or (lambda *_: None)

    def present(self, request):
        if not _slots.acquire(blocking=False):
            raise TransportUnavailable()
        try:
            return self._present(request)
        finally:
            _slots.release()

    def _present(self, request):
        if self.is_cancelled():
            return request.respond("deny")
        seconds = min(float(self.timeout_seconds), float(request.timeout_seconds), 300.0)
        if not math.isfinite(seconds) or seconds <= 0.5 or "once" not in request.allowed_choices:
            return request.respond("deny")
        # Leave time for the host to receive the decision; the host separately enforces its deadline.
        deadline = time.monotonic() + seconds - 0.25
        prompt = f"{request.description}\n\nAction: {request.command}\n\nApprove once only. Request {request.request_id[:8]}."
        if len(prompt.encode("utf-16-le")) // 2 > 2000:
            # Never truncate the action that a person is being asked to authorize.
            return request.respond("deny")
        if not self.ledger.claim(request.request_id, request.digest):
            return request.respond("deny")
        interaction_id = None
        digest = None
        state = "failed"
        try:
            body = {
                "title": "Hermes needs your approval", "prompt": prompt, "kind": "approval",
                "presentation": "notification", "expiresInSeconds": max(30, math.ceil(seconds)),
            }
            if self.device_id:
                body["deviceIds"] = [self.device_id]
            # Do not retry an unknown POST result here. The key permits later reconciliation.
            try:
                created = self.client.create(body, "hermes-" + request.request_id, min(10, self._remaining(deadline)))
            except NotifyError:
                # Nothing reached the phone, so no one has been asked yet. Let the host apply
                # transport_fallback (for example the terminal prompt) instead of a silent deny.
                logger.warning("Notify approval could not be created; Hermes will use its transport fallback")
                raise TransportUnavailable() from None
            interaction = self._interaction(created)
            interaction_id = interaction["id"]
            digest = interaction["actionDigest"]
            self._validate(interaction, interaction_id, digest, body)
            self.ledger.bind(request.request_id, interaction_id, digest)
            self.on_state(request, "pending", interaction_id, digest)
            while True:
                self._remaining(deadline)
                self._validate(interaction, interaction_id, digest, body)
                status = interaction["status"]
                if status == "approved" and interaction.get("response") == "approve":
                    state = "consumed"
                    # Commit consumption before returning. Crash here loses permission, never replays it.
                    self.ledger.finish(request.request_id, state)
                    self.on_state(request, state, interaction_id, digest)
                    return request.respond("once")
                if status != "pending":
                    state = "denied"
                    return request.respond("deny")
                remaining = self._remaining(deadline)
                if remaining <= 0.1:
                    # Too little time left for a useful long poll. Coarse clocks (Windows)
                    # would otherwise spend one more request on a zero-second wait.
                    raise NotifyError("Approval deadline reached")
                started = time.monotonic()
                result = self.client.wait(interaction_id, min(5, max(0, remaining - 0.1)), min(7, remaining))
                interaction = self._interaction(result)
                # A pending answer can arrive immediately. Bound request rate even on a broken server.
                if interaction.get("status") == "pending":
                    pause = min(max(0, 0.5 - (time.monotonic() - started)), max(0, deadline - time.monotonic()))
                    if pause:
                        time.sleep(pause)
        except (NotifyError, OSError, ValueError, TypeError, KeyError):
            # Never log exception contents: they may contain prompts or secrets.
            logger.warning("Notify approval did not complete; Hermes will deny the request")
            return request.respond("deny")
        finally:
            if state != "consumed":
                self.ledger.finish(request.request_id, state)
                self.on_state(request, state, interaction_id, digest)
                # A cancellation failure leaves the server prompt to expire. It cannot authorize Hermes.
                if interaction_id and deadline > time.monotonic():
                    try:
                        self.client.cancel(interaction_id, min(2, max(0.01, deadline - time.monotonic())))
                    except NotifyError:
                        pass

    def _remaining(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or self.is_cancelled():
            raise NotifyError("Approval deadline reached")
        return remaining

    @staticmethod
    def _interaction(result):
        interaction = result.get("interaction")
        if not isinstance(interaction, dict):
            raise NotifyError("Notify response lacks interaction")
        return interaction

    @staticmethod
    def _validate(interaction, interaction_id, digest, body):
        if not isinstance(interaction_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", interaction_id):
            raise NotifyError("Invalid interaction ID")
        if not isinstance(digest, str) or not digest or len(digest) > 512:
            raise NotifyError("Invalid action digest")
        expected = {"id": interaction_id, "actionDigest": digest, "kind": "approval",
                    "presentation": "notification", "title": body["title"], "prompt": body["prompt"]}
        if any(interaction.get(key) != value for key, value in expected.items()):
            raise NotifyError("Interaction no longer matches the requested action")
