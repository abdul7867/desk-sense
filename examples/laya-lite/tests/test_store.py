import socket
import sqlite3

from app.store import Store
from app.supervisor import HOST, make_server
from app import zones


def columns(db, table):
    return [r[1] for r in db.execute("PRAGMA table_info(%s)" % table)]


def test_schema_matches_plan(tmp_path):
    Store(tmp_path / "s.db").close()
    db = sqlite3.connect(tmp_path / "s.db")
    assert columns(db, "requests") == ["id", "created_at", "state_json", "questions", "status", "attempts"]
    assert columns(db, "results") == ["request_id", "answers", "language", "zone", "latency_ms"]
    assert columns(db, "corrections") == ["request_id", "question_id", "model_value", "user_value", "created_at"]


def test_request_is_persisted_before_the_worker_runs(make_sup, tmp_path):
    sup = make_sup(max_attempts=1)
    res = sup.submit("app crash ho raha hai", _test={"crash_on_attempt": 1})
    assert res["status"] == "failed"
    db = sqlite3.connect(tmp_path / "t.db")
    assert db.execute("SELECT status, attempts FROM requests WHERE id=?", (res["id"],)).fetchone() == ("failed", 1)


def test_done_request_has_result_zone_and_language(make_sup):
    sup = make_sup()
    res = sup.submit("मुझसे दो बार शुल्क लिया गया")
    stored = sup.store.result(res["id"])
    assert res["status"] == "done" and stored["language"] == "hi"
    assert stored["zone"] in ("act", "confirm", "flag")
    assert set(stored["answers"]) == set(sup.schema["questions"])


def test_correction_records_model_and_user_value(make_sup):
    sup = make_sup()
    res = sup.submit("refund chahiye")
    model_value = res["answers"]["department"]["choice"]
    assert sup.store.add_correction(res["id"], "department", "billing") == model_value
    row = sup.store.db.execute("SELECT model_value, user_value FROM corrections").fetchone()
    assert row == (model_value, "billing")


def test_zone_thresholds():
    t = {"act": 0.85, "confirm": 0.60}
    answers = {"a": {"type": "noul", "noul": 0.95}, "b": {"type": "choice", "probabilities": {"x": 0.7, "y": 0.3}},
               "c": {"type": "score", "probabilities": {"0": 0.5, "1": 0.3, "2": 0.2}}}
    assert zones.assign(answers, t) == "flag"
    assert [answers[k]["zone"] for k in "abc"] == ["act", "confirm", "flag"]
    assert zones.zone_for(0.85) == "act" and zones.zone_for(0.6) == "confirm" and zones.zone_for(0.599) == "flag"


def test_server_binds_loopback_only(make_sup):
    server = make_server(make_sup(), 0)
    try:
        assert HOST == "127.0.0.1"
        assert server.server_address[0] == "127.0.0.1"
        assert server.socket.family == socket.AF_INET
    finally:
        server.server_close()
