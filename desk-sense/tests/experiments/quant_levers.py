"""B0 speed levers (DECISIONS.md 2026-09-24). Run from desk-sense/: python tests/experiments/<this file>.
Needs model/dist; quant_levers also needs model/artifacts/int8_acc4 and int4 (model.quantize.quantize)."""
import json, sys, tempfile, time
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
from app.supervisor import Supervisor
from app.worker import peak_rss_mb
import tests.measure_browser as mb

N = 200
steps = list(mb.steps(N))
runs = {}
for name, bundle in [("int8_weights (shipped)", "model/dist"), ("int8_compute", "model/artifacts/int8_acc4"), ("int4_weights", "model/artifacts/int4")]:
    with tempfile.TemporaryDirectory() as tmp:
        sup = Supervisor(Path(tmp) / "m.db", bundle=bundle, threads=2)
        sup.warm(); lat, picks = [], []
        for state, qs in steps:
            r = sup.decide(state, qs)
            lat.append(r["latency_ms"])
            p = r["answers"]["next"]["probabilities"]
            top = sorted(p.values(), reverse=True)
            picks.append((r["answers"]["next"]["choice"], top[0] - top[1]))
        peak = sup.worker_stats()["peak_rss_mb"]
        sup.close()
    runs[name] = {"latency_ms": {"p50": float(np.percentile(lat, 50)), "p95": float(np.percentile(lat, 95))},
                  "worker_peak_mb": peak, "picks": picks}
    print(name, runs[name]["latency_ms"], peak, flush=True)
base = runs["int8_weights (shipped)"]["picks"]
out = {"steps": N, "threads": 2, "where": "dev container, 4 vCPU, 15 GB RAM, Linux; base Laya (untrained on browser steps)"}
for name, r in runs.items():
    same = [a[0] == b[0] for a, b in zip(r["picks"], base)]
    dec = [s for s, b in zip(same, base) if b[1] >= 0.2]
    out[name] = {"latency_ms": r["latency_ms"], "worker_peak_mb": r["worker_peak_mb"],
                 "same_pick_as_shipped": round(sum(same) / len(same), 3),
                 "same_pick_on_decisive": "%d/%d" % (sum(dec), len(dec))}
json.dump(out, open("reports/browser/b0_quant_levers.json", "w"), indent=2)
print(json.dumps(out, indent=2))
