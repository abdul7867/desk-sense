"""Browser-step latency and whole-engine peak memory (gates B0, B4, B5). Same method as
measure_app: real supervisor + worker, each process reporting its own peak.

    python -m tests.measure_browser --bundle model/dist --n 500 --threads 2
Steps are generated like real ones: a page of 30-150 elements, the controller's shortlist (12) plus
the fixed moves, a state of goal + subgoal + history, one question per step.
"""
import argparse
import json
import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.supervisor import DEFAULT_BUNDLE, ROOT, Supervisor  # noqa: E402
from app.worker import peak_rss_mb  # noqa: E402
from browser import question, rank  # noqa: E402

WORDS = ("search flights hotels cars home deals help sign in account orders cart checkout settings profile "
         "language notifications email phone name city from to date return passengers class economy business "
         "next previous save cancel close accept cookies filter sort price rating reviews details more menu "
         "download upload share print contact support billing invoice refund status track delivery address "
         "मेरा खाता भुगतान खोजें सहायता भाषा").split()
ROLES = ("button", "link", "link", "link", "textbox", "select", "checkbox", "option", "tab", "menuitem")
GOALS = ("Search flights from Zurich to London next Friday", "Change my account language to Hindi and save",
         "Find the refund status of order 4821", "Open the Pune office page and copy its phone number",
         "Download last month's invoice", "मेरे ऑर्डर की डिलीवरी ट्रैक करो")


def page(rng):
    n = rng.randint(30, 150)
    els = [{"i": i, "role": rng.choice(ROLES), "name": " ".join(rng.sample(WORDS, rng.randint(1, 4))).title(),
            "region": rng.choice(("", "", "header", "main", "dialog", "footer")), "new": rng.random() < 0.1}
           for i in range(n)]
    return {"host": "site%d.example" % rng.randint(1, 9), "title": " ".join(rng.sample(WORDS, 3)).title(),
            "dialog": any(e["region"] == "dialog" for e in els), "elements": els}


def steps(n, seed=7):
    rng = random.Random(seed)
    for _ in range(n):
        p = page(rng)
        target = rng.choice(p["elements"])
        sub = {"op": question.op_for(target), "target": target["name"],
               "value": " ".join(rng.sample(WORDS, 2)) if question.op_for(target) == "type" else None}
        history = ["click #%d %s" % (rng.randint(0, 99), " ".join(rng.sample(WORDS, 2))) for _ in range(rng.randint(0, 5))]
        cands = rank.shortlist(p["elements"], sub)
        yield question.build_state(rng.choice(GOALS), sub, history, p), {"next": question.build_question(cands)}


def measure(bundle, n, threads, db):
    sup = Supervisor(db, bundle=bundle, threads=threads)
    lat_e2e, lat_model, tokens, statuses, zones = [], [], [], {}, {}
    try:
        sup.warm()
        for state, qs in steps(n):
            t = time.perf_counter()
            res = sup.decide(state, qs)
            lat_e2e.append((time.perf_counter() - t) * 1000)
            key = res["status"] if res["status"] != "refused" else "refused:" + res["reason"]
            statuses[key] = statuses.get(key, 0) + 1
            if res["status"] == "done":
                lat_model.append(res["latency_ms"])
                zones[res["zone"]] = zones.get(res["zone"], 0) + 1
                if res.get("usage"):
                    tokens.append(res["usage"]["input_tokens"])
        stats = sup.worker_stats()
        cold = next(e["cold_start_s"] for e in sup.events if e["kind"] == "worker_started")
        restarts = sum(e["kind"] in ("watchdog_kill", "worker_lost_step") for e in sup.events)
    finally:
        sup.close()
    supervisor_mb = peak_rss_mb()
    pct = lambda xs, q: round(float(np.percentile(xs, q)), 1) if xs else None  # noqa: E731
    return {
        "steps": n, "statuses": statuses, "zones_untrained_or_trained": zones, "threads": threads,
        "bundle": str(bundle), "bundle_weights_mb": round(sum(f.stat().st_size for f in Path(bundle).glob("model.*")) / 1e6),
        "tokens_per_step": {"p50": pct(tokens, 50), "p95": pct(tokens, 95), "max": max(tokens) if tokens else None},
        "model_latency_ms": {"p50": pct(lat_model, 50), "p95": pct(lat_model, 95)},
        "end_to_end_ms": {"p50": pct(lat_e2e, 50), "p95": pct(lat_e2e, 95)},
        "peak_mb": {"worker": stats["peak_rss_mb"], "supervisor": round(supervisor_mb, 1),
                    "total": round(supervisor_mb + stats["peak_rss_mb"], 1)},
        "worker_imports_torch": stats["torch_loaded"] or stats["transformers_loaded"],
        "worker_restarts": restarts, "cold_start_s": cold, "platform": sys.platform,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--out", type=Path, default=ROOT / "reports" / "browser" / "b0_baseline.json")
    ap.add_argument("--label", default="", help="where this ran: machine, RAM, cores")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        report = measure(args.bundle, args.n, args.threads, Path(tmp) / "m.db")
    report["label"] = args.label
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["worker_restarts"] == 0 and not report["worker_imports_torch"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
