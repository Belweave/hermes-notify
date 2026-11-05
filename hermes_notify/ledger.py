"""An approval is claimed once. A crashed host must ask for fresh approval."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS approvals (
                request_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,
                interaction_id TEXT, action_digest TEXT, state TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=1)
        try:
            with db:
                yield db
        finally:
            db.close()

    def claim(self, request_id, request_digest):
        with self._connect() as db:
            result = db.execute(
                "INSERT OR IGNORE INTO approvals(request_id, request_digest, state) VALUES (?, ?, 'creating')",
                (request_id, request_digest),
            )
            return result.rowcount == 1

    def bind(self, request_id, interaction_id, action_digest):
        with self._connect() as db:
            db.execute(
                "UPDATE approvals SET interaction_id=?, action_digest=?, state='pending' WHERE request_id=?",
                (interaction_id, action_digest, request_id),
            )

    def finish(self, request_id, state):
        with self._connect() as db:
            db.execute("UPDATE approvals SET state=? WHERE request_id=?", (state, request_id))
