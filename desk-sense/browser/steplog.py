"""Every browser step, written off the hot path to its own SQLite file. The log is also training data:
(state, options, chosen action) rows for fine-tuning and distillation. It holds page text, so it
belongs in gitignored data/ like tickets do."""
import json
import queue
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS steps (
    task_id     TEXT NOT NULL,
    n           INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    goal        TEXT NOT NULL,
    state       TEXT,
    options     TEXT,              -- JSON: the question's criteria the model saw, if it was asked
    action      TEXT NOT NULL,     -- JSON: what the engine returned
    source      TEXT NOT NULL,     -- fastpath | model | thinker | engine
    zone        TEXT,
    latency_ms  INTEGER
);
"""


class StepLog:
    def __init__(self, path):
        self.path = str(path)
        self.q = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run(self):
        db = sqlite3.connect(self.path, isolation_level=None)
        # A lost step row costs one training example, not a request: no fsync per write.
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.executescript(SCHEMA)
        self._ready.set()
        while True:
            row = self.q.get()
            if row is None:
                break
            db.execute("INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
            self.q.task_done()
        db.close()

    def add(self, task_id, n, goal, state, options, action, zone=None, latency_ms=None):
        self.q.put((task_id, n, datetime.now(timezone.utc).isoformat(timespec="seconds"), goal, state,
                    None if options is None else json.dumps(options, ensure_ascii=False),
                    json.dumps(action, ensure_ascii=False), action.get("source", "engine"), zone, latency_ms))

    def flush(self):
        self.q.join()

    def close(self):
        self.q.put(None)
        self._thread.join()
