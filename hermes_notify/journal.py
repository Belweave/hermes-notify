"""Profile-local bounded journal. Connections and transactions are deliberately short."""

import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .client import NotifyError


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)


class Journal:
    def __init__(self, directory, *, retention_days=30, max_records=2000):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.directory / "runtime.sqlite3"
        self.lock = threading.RLock()
        self.retention = max(1, min(90, int(retention_days))) * 86400
        self.max_records = max_records
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA secure_delete=ON")
            db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, key TEXT, body TEXT NOT NULL, updated REAL NOT NULL, PRIMARY KEY(kind,key))")
        self.prune()
        if self.get("meta", "identity") is None:
            self.put("meta", "identity", {"id": uuid.uuid4().hex})
        self.identity = self.get("meta", "identity")["id"]

    @contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=1)
            try:
                with db:
                    yield db
            finally:
                db.close()

    def get(self, kind, key, default=None):
        with self.connect() as db:
            row = db.execute("SELECT body FROM records WHERE kind=? AND key=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else default

    def all(self, kind):
        with self.connect() as db:
            rows = db.execute("SELECT body FROM records WHERE kind=? ORDER BY updated DESC, key", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, kind, key, value):
        raw = encode(value)
        if len(raw.encode()) > 64 * 1024:
            raise NotifyError("Journal record exceeded size limit")
        with self.connect() as db:
            exists = db.execute("SELECT 1 FROM records WHERE kind=? AND key=?", (kind, key)).fetchone()
            if not exists and db.execute("SELECT count(*) FROM records").fetchone()[0] >= self.max_records:
                raise NotifyError("Journal capacity reached; archive completed work before continuing")
            db.execute("INSERT INTO records VALUES(?,?,?,?) ON CONFLICT(kind,key) DO UPDATE SET body=excluded.body, updated=excluded.updated",
                       (kind, key, raw, time.time()))
        return value

    def create(self, kind, key, value):
        """Atomically create a durable intent, returning the winning value."""
        raw = encode(value)
        if len(raw.encode()) > 64 * 1024:
            raise NotifyError("Journal record exceeded size limit")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM records WHERE kind=? AND key=?", (kind, key)).fetchone()
            if row:
                return json.loads(row[0])
            if db.execute("SELECT count(*) FROM records").fetchone()[0] >= self.max_records:
                raise NotifyError("Journal capacity reached; archive completed work before continuing")
            db.execute("INSERT INTO records VALUES(?,?,?,?)", (kind, key, raw, time.time()))
        return value

    def replace_if(self, kind, key, previous, value):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM records WHERE kind=? AND key=?", (kind, key)).fetchone()
            if not row or json.loads(row[0]) != previous:
                return False
            db.execute("UPDATE records SET body=?,updated=? WHERE kind=? AND key=?",
                       (encode(value), time.time(), kind, key))
            return True

    def prune(self):
        # Old receipts may be forgotten only after the documented retention window.
        # Active/uncertain intents never expire silently or gain a fresh write attempt.
        with self.connect() as db:
            rows = db.execute("SELECT kind,key,body FROM records WHERE updated < ?", (time.time() - self.retention,)).fetchall()
            for kind, key, raw in rows:
                value = json.loads(raw)
                keep = kind in ("meta", "project")
                keep |= kind == "run" and value["workspace"]["status"] not in ("shipped", "failed", "canceled", "denied")
                keep |= kind == "intent" and value.get("phase") not in ("done", "rejected")
                keep |= kind == "publication" and value.get("phase") != "announced"
                keep |= kind in ("reply", "event") and not value.get("acked", False)
                keep |= kind == "question" and value.get("status") == "pending"
                if not keep:
                    db.execute("DELETE FROM records WHERE kind=? AND key=?", (kind, key))

    def snapshot(self, value):
        raw = encode(value).encode()
        if len(raw) > 512 * 1024:
            raise NotifyError("Status snapshot exceeded size limit")
        with self.lock:
            fd, path = tempfile.mkstemp(prefix=".status-", suffix=".json", dir=self.directory)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(path, self.directory / "status.json")
            finally:
                if os.path.exists(path):
                    os.unlink(path)
