"""R8: no request is lost on crash."""
import threading
import time

import psutil


def test_worker_crash_mid_request_is_retried(make_sup):
    sup = make_sup()
    res = sup.submit("login nahi ho raha", _test={"crash_on_attempt": 1})
    assert res["status"] == "done" and res["attempts"] == 2
    kinds = [e["kind"] for e in sup.events]
    assert kinds.count("worker_started") == 2 and "worker_lost_request" in kinds


def test_worker_killed_from_outside_mid_request(make_sup):
    sup = make_sup()
    sup.submit("warm up")
    pid = sup.worker.pid

    def kill_soon():
        time.sleep(0.5)
        psutil.Process(pid).kill()

    threading.Thread(target=kill_soon).start()
    res = sup.submit("app band ho gaya", _test={"delay": 2})
    assert res["status"] == "done" and res["attempts"] == 2
    assert sup.worker.pid != pid


def test_gives_up_after_max_attempts_and_says_so(make_sup):
    sup = make_sup(max_attempts=2)
    res = sup.submit("refund", _test={"crash_on_attempt": "always"})
    assert res["status"] == "failed" and "2 times" in res["message"]
    assert sup.store.get_request(res["id"]) | {"state": None, "questions": None} == {
        "id": res["id"], "state": None, "questions": None, "status": "failed", "attempts": 2}


def test_supervisor_crash_leaves_pending_requests_that_are_replayed(make_sup, tmp_path):
    sup = make_sup()
    # A previous supervisor saved these and died before the worker answered.
    ids = [sup.store.add_request(t, sup.schema["questions"]) for t in ("payment fail", "पासवर्ड रीसेट नहीं हो रहा")]
    assert sup.store.pending_ids() == ids
    results = sup.replay_pending()
    assert [r["status"] for r in results] == ["done", "done"]
    assert sup.store.pending_ids() == []


def test_memory_watchdog_restarts_worker_and_request_completes(make_sup):
    sup = make_sup(mem_limit_mb=150, watchdog_interval=0.2)
    res = sup.submit("slow app", _test={"hog_on_attempt": 1, "hog_mb": 400, "hog_hold_s": 10})
    assert res["status"] == "done" and res["attempts"] == 2
    kills = [e for e in sup.events if e["kind"] == "watchdog_kill"]
    assert len(kills) == 1 and kills[0]["mb"] > 150


def test_idle_worker_is_stopped_and_restarted_on_demand(make_sup):
    sup = make_sup(idle_timeout=0.5, watchdog_interval=0.1)
    sup.submit("hello, need help with billing")
    first = sup.worker.pid
    time.sleep(1.5)
    assert sup.worker is None and "idle_stop" in [e["kind"] for e in sup.events]
    res = sup.submit("another ticket about login")
    assert res["status"] == "done" and sup.worker.pid != first
