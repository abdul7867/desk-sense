"""SQLite store (plan §9.3). Every request is written before the worker sees it (R8)."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL,
    state_json  TEXT NOT NULL,
    questions   TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending','done','failed','refused')),
    attempts    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS results (
    request_id  INTEGER REFERENCES requests(id),
    answers     TEXT NOT NULL,   -- JSON with choice/probs/confidence; {"refused": {...}} when refused
    language    TEXT,
    zone        TEXT CHECK (zone IN ('act','confirm','flag')),
    latency_ms  INTEGER
);

CREATE TABLE IF NOT EXISTS corrections (
    request_id  INTEGER REFERENCES requests(id),
    question_id TEXT NOT NULL,
    model_value TEXT,
    user_value  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def add_request(self, state, questions):
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO requests (created_at, state_json, questions, status) VALUES (?, ?, ?, 'pending')",
                (now(), json.dumps(state, ensure_ascii=False), json.dumps(questions, ensure_ascii=False)))
            return cur.lastrowid

    def get_request(self, rid):
        row = self.db.execute(
            "SELECT id, state_json, questions, status, attempts FROM requests WHERE id = ?", (rid,)).fetchone()
        if row is None:
            return None
        return {"id": row[0], "state": json.loads(row[1]), "questions": json.loads(row[2]),
                "status": row[3], "attempts": row[4]}

    def bump_attempts(self, rid):
        with self.lock:
            self.db.execute("UPDATE requests SET attempts = attempts + 1 WHERE id = ?", (rid,))
        return self.get_request(rid)["attempts"]

    def pending_ids(self):
        return [r[0] for r in self.db.execute("SELECT id FROM requests WHERE status = 'pending' ORDER BY id")]

    def finish(self, rid, status, answers, language=None, zone=None, latency_ms=None):
        with self.lock:
            self.db.execute("BEGIN")
            try:
                self.db.execute("INSERT INTO results (request_id, answers, language, zone, latency_ms) VALUES (?, ?, ?, ?, ?)",
                                (rid, json.dumps(answers, ensure_ascii=False), language, zone, latency_ms))
                self.db.execute("UPDATE requests SET status = ? WHERE id = ?", (status, rid))
            except Exception:
                self.db.execute("ROLLBACK")
                raise
            self.db.execute("COMMIT")

    def fail(self, rid):
        with self.lock:
            self.db.execute("UPDATE requests SET status = 'failed' WHERE id = ?", (rid,))

    def result(self, rid):
        row = self.db.execute("SELECT answers, language, zone, latency_ms FROM results WHERE request_id = ?",
                              (rid,)).fetchone()
        if row is None:
            return None
        return {"answers": json.loads(row[0]), "language": row[1], "zone": row[2], "latency_ms": row[3]}

    def add_correction(self, rid, question_id, user_value):
        res = self.result(rid)
        model_value = None
        if res and question_id in res["answers"]:
            a = res["answers"][question_id]
            model_value = str(a.get("choice", a.get("score", a.get("noul"))))
        with self.lock:
            self.db.execute("INSERT INTO corrections (request_id, question_id, model_value, user_value, created_at) "
                            "VALUES (?, ?, ?, ?, ?)", (rid, question_id, model_value, str(user_value), now()))
        return model_value

    def counts(self):
        return dict(self.db.execute("SELECT status, COUNT(*) FROM requests GROUP BY status").fetchall())

    def close(self):
        self.db.close()
