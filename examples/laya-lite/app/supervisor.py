"""Supervisor (plan §9.2): owns SQLite, the request queue, the worker's lifetime and its memory.

    python -m app.supervisor --port 8765            # local HTTP API on 127.0.0.1 only
    python -m app.supervisor --fake                 # no model, random answers
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from app import guard, zones
from app.store import Store

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema.json"
DEFAULT_BUNDLE = ROOT / "model" / "dist"
HOST = "127.0.0.1"  # R7: never 0.0.0.0
# glibc otherwise keeps one heap per thread and holds freed activation buffers: +200-400 MB of RSS
# after a long ticket. Large blocks go to mmap and are returned on free. Ignored off Linux.
WORKER_MALLOC_ENV = {"MALLOC_ARENA_MAX": "1", "MALLOC_TRIM_THRESHOLD_": "0", "MALLOC_MMAP_THRESHOLD_": "65536"}


def process_memory_mb(pid):
    """What the watchdog guards: memory only this process holds. Windows: private bytes. Linux:
    anonymous memory. Not RSS: the weights are memory-mapped, and their clean file pages count in
    RSS but the OS can drop them under pressure; on RSS a healthy worker would trip 450 MB after
    enough distinct tokens had paged in their embedding rows (DECISIONS.md)."""
    import psutil

    if sys.platform.startswith("linux"):
        try:
            with open("/proc/%d/smaps_rollup" % pid) as f:
                for line in f:
                    if line.startswith("Anonymous:"):
                        return int(line.split()[1]) / 1024
        except OSError:
            pass
    mi = psutil.Process(pid).memory_info()
    return getattr(mi, "private", mi.rss) / 1e6


class Worker:
    def __init__(self, cmd, log_path, ready_timeout=180):
        self.log = open(log_path, "a", encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", USE_TF="0", **WORKER_MALLOC_ENV)
        self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=self.log, text=True, encoding="utf-8", bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        self.started = time.perf_counter()
        ready = self.recv(ready_timeout)
        if not ready or not ready.get("ready"):
            self.stop()
            raise RuntimeError("worker did not start; see %s" % log_path)
        self.cold_start_s = time.perf_counter() - self.started

    def _read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    @property
    def pid(self):
        return self.proc.pid

    def alive(self):
        return self.proc.poll() is None

    def send(self, obj):
        try:
            self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def recv(self, timeout):
        """Next reply, or None if the worker died or went silent past `timeout`."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                line = self.lines.get(timeout=min(0.2, max(0.0, deadline - time.monotonic())))
            except queue.Empty:
                if time.monotonic() >= deadline:
                    return None
                continue
            if line is None:
                return None
            if line.strip():
                return json.loads(line)

    def stop(self):
        if self.alive():
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()


class Supervisor:
    def __init__(self, db_path, bundle=DEFAULT_BUNDLE, fake=False, fake_delay=0.0, schema_path=SCHEMA_PATH,
                 idle_timeout=300.0, mem_limit_mb=450.0, watchdog_interval=1.0, max_attempts=3,
                 request_timeout=120.0, threads=2, max_len=None):
        self.store = Store(db_path)
        self.schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        self.log_path = Path(db_path).with_suffix(".worker.log")
        cmd = [sys.executable, "-m", "app.worker"]
        # Tokens the model reads per question (question + options + ticket). Lower = faster, but the
        # ticket must fit: longer ones are refused as too_long, never cut.
        self.max_len = int(max_len or self.schema.get("model_max_len", 512))
        cmd += (["--fake", "--fake-delay", str(fake_delay)] if fake
                else ["--bundle", str(bundle), "--threads", str(threads), "--max-len", str(self.max_len)])
        self.cmd = cmd
        self.idle_timeout, self.mem_limit_mb = idle_timeout, mem_limit_mb
        self.max_attempts, self.request_timeout = max_attempts, request_timeout
        self.worker = None
        self.lock = threading.RLock()  # the queue: one request in the worker at a time
        self.busy = False
        self.last_used = time.monotonic()
        self.events = []
        self.peak_worker_mb = 0.0
        self._closed = threading.Event()
        self._watchdog = threading.Thread(target=self._watch, args=(watchdog_interval,), daemon=True)
        self._watchdog.start()

    # worker lifetime -------------------------------------------------------

    def _ensure_worker(self):
        if self.worker is None or not self.worker.alive():
            if self.worker is not None:
                self._event("worker_died", pid=self.worker.pid)
                self.worker.stop()
            self.worker = Worker(self.cmd, self.log_path)
            self._event("worker_started", pid=self.worker.pid, cold_start_s=round(self.worker.cold_start_s, 2))
        return self.worker

    def _drop_worker(self, why):
        w, self.worker = self.worker, None
        if w is not None:
            self._event(why, pid=w.pid)
            w.stop()

    def _event(self, kind, **kw):
        self.events.append(dict(kind=kind, t=round(time.time(), 3), **kw))

    def _watch(self, interval):
        while not self._closed.wait(interval):
            w = self.worker
            if w is None or not w.alive():
                continue
            try:
                mb = process_memory_mb(w.pid)
            except Exception:
                continue
            self.peak_worker_mb = max(self.peak_worker_mb, mb)
            if mb > self.mem_limit_mb:
                # Stop it now; the in-flight request is replayed from SQLite on a fresh worker (M13).
                self._event("watchdog_kill", pid=w.pid, mb=round(mb, 1))
                w.proc.kill()
            elif not self.busy and time.monotonic() - self.last_used > self.idle_timeout:
                if self.lock.acquire(blocking=False):
                    try:
                        if not self.busy and self.worker is w:
                            self._drop_worker("idle_stop")
                    finally:
                        self.lock.release()

    # requests ----------------------------------------------------------------

    def submit(self, state, questions=None, allow_truncate=False, _test=None):
        questions = questions or self.schema["questions"]
        rid = self.store.add_request(state, questions)  # R8: persisted before anything can fail
        return self._process(rid, allow_truncate=allow_truncate, _test=_test)

    def replay_pending(self):
        """Finish whatever a previous run left behind (supervisor crash, power loss)."""
        return [self._process(rid) for rid in self.store.pending_ids()]

    def _process(self, rid, allow_truncate=False, _test=None):
        req = self.store.get_request(rid)
        g = guard.check(req["state"], tuple(self.schema.get("allowed_scripts", ("latin", "devanagari"))))
        if not g.ok:
            refusal = {"reason": g.reason, "message": g.message, "scripts": g.scripts}
            self.store.finish(rid, "refused", {"refused": refusal})
            return {"id": rid, "status": "refused", **refusal}
        while True:
            if self.store.get_request(rid)["attempts"] >= self.max_attempts:
                self.store.fail(rid)
                return {"id": rid, "status": "failed", "message": "worker failed %d times" % self.max_attempts}
            attempt = self.store.bump_attempts(rid)
            msg = {"id": rid, "state": req["state"], "questions": req["questions"], "attempt": attempt,
                   "max_tokens": self.schema.get("max_state_tokens", 512), "allow_truncate": allow_truncate}
            if _test:
                msg["_test"] = _test
            with self.lock:
                self.busy = True
                try:
                    w = self._ensure_worker()
                    reply = w.recv(self.request_timeout) if w.send(msg) else None
                    if reply is None:
                        self._drop_worker("worker_lost_request")
                finally:
                    self.busy = False
                    self.last_used = time.monotonic()
            if reply is None:
                continue
            if "error" in reply:
                self.store.fail(rid)
                return {"id": rid, "status": "failed", "message": reply["error"]}
            if "too_long" in reply:
                info = reply["too_long"]
                refusal = {"reason": "too_long", "tokens": info["state_tokens"], "limit": info["room"],
                           "message": "The ticket is %d tokens; the model can read %d. Shorten it or split it "
                                      "into parts. Nothing was cut." % (info["state_tokens"], info["room"])}
                self.store.finish(rid, "refused", {"refused": refusal}, language=g.language)
                return {"id": rid, "status": "refused", **refusal}
            zone = zones.assign(reply["answers"], self.schema["zones"])
            self.store.finish(rid, "done", reply["answers"], g.language, zone, reply.get("latency_ms"))
            return {"id": rid, "status": "done", "language": g.language, "zone": zone,
                    "answers": reply["answers"], "latency_ms": reply.get("latency_ms"), "attempts": attempt}

    def worker_stats(self):
        with self.lock:
            w = self._ensure_worker()
            w.send({"cmd": "stats"})
            reply = w.recv(10)
            return reply["stats"] if reply else None

    def close(self):
        self._closed.set()
        with self.lock:
            self._drop_worker("shutdown")
        self.store.close()


def make_server(sup, port=0):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True, "requests": sup.store.counts()})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/predict":
                return self._send(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                state = body["state"]
            except (ValueError, KeyError):
                return self._send(400, {"error": "body must be JSON with a 'state' field"})
            self._send(200, sup.submit(state, body.get("questions")))

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer((HOST, port), Handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "laya_lite.db"))
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    sup = Supervisor(args.db, bundle=args.bundle, fake=args.fake)
    done = sup.replay_pending()
    if done:
        print("replayed %d unfinished requests" % len(done))
    server = make_server(sup, args.port)
    print("listening on http://%s:%d" % server.server_address[:2])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        sup.close()


if __name__ == "__main__":
    main()
