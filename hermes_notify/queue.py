"""One lifecycle-owned worker, bounded and coalescing, with no polling timers."""

import threading
import time
from collections import OrderedDict


class WorkQueue:
    def __init__(self, work, failed, *, capacity=64):
        self.work, self.failed, self.capacity = work, failed, capacity
        self.items = OrderedDict()
        self.condition = threading.Condition()
        self.stopped = False
        self.busy = False
        self.thread = None
        self.dropped = 0

    def submit(self, key, value, *, delay=0):
        with self.condition:
            if self.stopped:
                return False
            if key not in self.items and len(self.items) >= self.capacity:
                victim = next((k for k in self.items if k[0] == "progress"), None)
                if victim is None:
                    self.dropped += 1
                    return False
                self.items.pop(victim)
                self.dropped += 1
            due = time.monotonic() + max(0, delay)
            if key in self.items:
                due = min(due, self.items[key][0])
            self.items[key] = (due, value)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="hermes-pocket-delivery", daemon=True)
                self.thread.start()
            self.condition.notify_all()
            return True

    def _run(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.stopped or self.items)
                if self.stopped:
                    return
                key = min(self.items, key=lambda k: self.items[k][0])
                due, value = self.items[key]
                remaining = due - time.monotonic()
                if remaining > 0:
                    self.condition.wait(remaining)
                    continue
                del self.items[key]
                self.busy = True
            try:
                self.work(key, value)
            except Exception:
                # Keep the supervisor alive, and never log payloads or exception text.
                self.failed("Background operation failed; retry from the owning session")
            finally:
                with self.condition:
                    self.busy = False
                    self.condition.notify_all()

    def drain(self, timeout=10):
        with self.condition:
            return self.condition.wait_for(lambda: not self.busy and not self.items, timeout)

    def close(self):
        with self.condition:
            self.stopped = True
            abandoned = len(self.items)
            self.items.clear()
            self.condition.notify_all()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(6)
        return abandoned + self.dropped
