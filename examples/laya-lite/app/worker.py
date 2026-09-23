"""Model worker: a separate process so killing it always returns its memory to the OS (plan §9.1, M5).

Protocol: one JSON object per line on stdin; one JSON reply per line on stdout.
    {"id": 7, "state": ..., "questions": {...}, "attempt": 1, "max_tokens": 512}
    {"cmd": "stats"}
Runtime deps: onnxruntime, tokenizers, numpy. `--fake` needs only numpy.
"""
import argparse
import json
import os
import sys
import time

import numpy as np


def release_free_heap():
    """glibc keeps freed memory: ~200 MB after parsing tokenizer.json, ~180 MB after a long ticket.
    Hand it back so those peaks do not stack with the next one."""
    if sys.platform.startswith("linux"):
        import ctypes

        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except OSError:
            pass


def memory_breakdown_mb():
    """Linux only: resident memory now, split into anonymous (private) and file-backed (mapped weights)."""
    try:
        d = {}
        with open("/proc/self/smaps_rollup") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3 and parts[2] == "kB":
                    d[parts[0].rstrip(":")] = int(parts[1]) / 1024
        return {"rss_now": round(d["Rss"], 1), "anon_now": round(d["Anonymous"], 1),
                "file_backed_now": round(d["Rss"] - d["Anonymous"], 1)}
    except (OSError, KeyError):
        return None


def peak_rss_mb():
    if sys.platform == "win32":
        import psutil

        return psutil.Process().memory_info().peak_pagefile / 1e6
    import resource

    kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return kb / 1e6 if sys.platform == "darwin" else kb / 1024


class FakeModel:
    """Random probabilities, same reply shape as the real model. Test hooks live only here."""

    def __init__(self, delay=0.0):
        self.delay = delay
        self.rng = np.random.default_rng()
        self.hog = None

    def predict(self, req):
        hooks = req.get("_test") or {}
        attempt = req.get("attempt", 1)
        if hooks.get("crash_on_attempt") in (attempt, "always"):
            os._exit(3)
        if hooks.get("hog_on_attempt") == attempt:
            self.hog = np.ones(int(hooks.get("hog_mb", 300) * 1e6) // 8)
            time.sleep(hooks.get("hog_hold_s", 5))
        time.sleep(float(hooks.get("delay", self.delay)))
        text = req["state"] if isinstance(req["state"], str) else json.dumps(req["state"], ensure_ascii=False)
        n_tokens = len(text.split())
        limit = req.get("max_tokens", 512)
        if n_tokens > limit and not req.get("allow_truncate"):
            return {"too_long": {"state_tokens": n_tokens, "room": limit, "truncated": True}}
        answers = {}
        for qid, q in req["questions"].items():
            if q["type"] == "noul":
                p = float(self.rng.random())
                answers[qid] = {"type": "noul", "noul": round(p, 4), "confidence": round(max(p, 1 - p), 4)}
                continue
            opts = list(q["criteria"].keys()) if q["type"] == "choice" else [str(i) for i in range(len(q["criteria"]))]
            p = self.rng.dirichlet(np.ones(len(opts)) * 0.3)
            ans = {"type": q["type"], "probabilities": {o: round(float(v), 4) for o, v in zip(opts, p)},
                   "confidence": round(float(p.max()), 4)}
            if q["type"] == "choice":
                ans["choice"] = opts[int(p.argmax())]
            else:
                ans["score"] = round(float((np.arange(len(p)) * p).sum()), 4)
            answers[qid] = ans
        return {"answers": answers, "usage": {"input_tokens": n_tokens}}


class RealModel:
    def __init__(self, bundle, threads):
        from app.ort_model import OrtModel

        self.m = OrtModel(bundle, threads=threads)

    def predict(self, req):
        return self.m.predict(req["state"], req["questions"], allow_truncate=req.get("allow_truncate", False))


def serve(model, out):
    def reply(obj):
        out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        out.flush()

    reply({"ready": True, "pid": os.getpid()})
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        if req.get("cmd") == "stats":
            reply({"stats": {"pid": os.getpid(), "peak_rss_mb": round(peak_rss_mb(), 1),
                             "memory_now_mb": memory_breakdown_mb(),
                             "torch_loaded": "torch" in sys.modules,
                             "transformers_loaded": "transformers" in sys.modules}})
            continue
        t = time.perf_counter()
        try:
            res = model.predict(req)
        except Exception as e:  # a bad request must not take the worker down
            reply({"id": req.get("id"), "error": "%s: %s" % (type(e).__name__, e)})
            continue
        res["id"] = req.get("id")
        res["latency_ms"] = round((time.perf_counter() - t) * 1000)
        reply(res)
        release_free_heap()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle")
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--fake-delay", type=float, default=0.0)
    ap.add_argument("--threads", type=int, default=2)
    args = ap.parse_args()
    # The protocol owns stdout; anything a library prints goes to stderr instead.
    out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    model = FakeModel(args.fake_delay) if args.fake else RealModel(args.bundle, args.threads)
    serve(model, out)


if __name__ == "__main__":
    main()
