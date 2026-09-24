"""Whole-app peak memory and latency (plan §10.2, gates G2/G5). Runs in its own process so the
number is supervisor + UI (this process) + worker, and nothing else.

    python -m tests.measure_app --bundle model/dist --n 200
Linux: peak RSS (ru_maxrss), each process reporting its own. Windows: peak private bytes.
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.supervisor import DEFAULT_BUNDLE, ROOT, Supervisor  # noqa: E402
from app.worker import peak_rss_mb  # noqa: E402
from model.export.cases import STATES  # noqa: E402

LIMIT_MB = 500


def requests(n):
    """Realistic tickets plus, every 10th, the longest allowed input (fills the 512-token window)."""
    texts = [s if isinstance(s, str) else json.dumps(s, ensure_ascii=False) for s in STATES]
    out = []
    for i in range(n):
        if i % 10 == 0:
            out.append((" ".join(texts[j % len(texts)] for j in range(i, i + 80)), True))
        else:
            out.append((texts[i % len(texts)], False))
    return out


def timed_requests(minutes):
    """Soak mode: the same request mix, repeated until `minutes` have passed (G5: 1 hour, no crashes)."""
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        for req in requests(100):
            if time.monotonic() >= deadline:
                return
            yield req


def measure(bundle, n, threads, db, max_len=None, minutes=None):
    sup = Supervisor(db, bundle=bundle, threads=threads, max_len=max_len)  # real watchdog: it must not fire on a healthy worker
    lat_e2e, lat_model, statuses = [], [], {}
    started = time.monotonic()
    try:
        for text, fill_window in (timed_requests(minutes) if minutes else requests(n)):
            t = time.perf_counter()
            res = sup.submit(text, allow_truncate=fill_window)
            lat_e2e.append((time.perf_counter() - t) * 1000)
            statuses[res["status"]] = statuses.get(res["status"], 0) + 1
            if res["status"] == "done":
                lat_model.append(res["latency_ms"])
        stats = sup.worker_stats()
        cold = next(e["cold_start_s"] for e in sup.events if e["kind"] == "worker_started")
        restarts = sum(e["kind"] in ("watchdog_kill", "worker_lost_request") for e in sup.events)
    finally:
        sup.close()
    supervisor_mb = peak_rss_mb()
    total = supervisor_mb + stats["peak_rss_mb"]
    return {
        "requests": sum(statuses.values()), "minutes": round((time.monotonic() - started) / 60, 1), "statuses": statuses, "threads": threads, "max_len": sup.max_len, "bundle": str(bundle),
        "bundle_weights_mb": round(sum(f.stat().st_size for f in Path(bundle).glob("model.*")) / 1e6),
        "peak_mb": {"worker": stats["peak_rss_mb"], "supervisor_and_ui": round(supervisor_mb, 1),
                    "total": round(total, 1), "limit": LIMIT_MB},
        "worker_memory_at_end_mb": stats.get("memory_now_mb"),
        "worker_imports_torch": stats["torch_loaded"] or stats["transformers_loaded"],
        "worker_restarts": restarts,
        "cold_start_s": cold,
        "model_latency_ms": {"p50": float(np.percentile(lat_model, 50)), "p95": float(np.percentile(lat_model, 95))},
        "end_to_end_ms": {"p50": round(float(np.percentile(lat_e2e, 50)), 1),
                          "p95": round(float(np.percentile(lat_e2e, 95)), 1)},
        "passed": total <= LIMIT_MB and restarts == 0 and set(statuses) == {"done"},
        "platform": sys.platform,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "g2_memory.json")
    ap.add_argument("--label", default="")
    ap.add_argument("--max-len", type=int, help="override schema.json model_max_len")
    ap.add_argument("--minutes", type=float, help="soak: run for this long instead of --n requests")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        report = measure(args.bundle, args.n, args.threads, Path(tmp) / "m.db", args.max_len, args.minutes)
    report["label"] = args.label
    args.out.parent.mkdir(exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
