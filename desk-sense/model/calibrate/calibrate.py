"""Calibrate last (plan §8.6, M1): one temperature per question type, fitted on the calib split only,
on the exact bundle that ships. Writes the temperatures into that bundle's runtime.json.

    python -m model.calibrate.calibrate --bundle model/dist
"""
import argparse
import json
from pathlib import Path

import numpy as np

from app.runtime import QTYPES, TEMP_MAX, TEMP_MIN
from model.data import load_schema, load_split, target_index
from model.evaluate import ece
from model.pin import DIST, REPORTS

GRID = np.exp(np.linspace(np.log(TEMP_MIN), np.log(TEMP_MAX), 200))


def softmax_t(z, t):
    z = z / t
    z = z - z.max()
    p = np.exp(z)
    return p / p.sum()


def collect(model, rows, questions):
    """{qtype: [(logits, target), ...]} from uncalibrated logits."""
    out = {name: [] for name in QTYPES}
    for r in rows:
        rq = r.get("questions") or questions  # browser steps carry their own options
        qs = {q: rq[q] for q in rq if target_index(rq[q], r["labels"].get(q)) is not None}
        if not qs:
            continue
        raw = model.raw(r["state"], qs)
        for qid, z in raw.items():
            out[qs[qid]["type"]].append((z, target_index(qs[qid], r["labels"][qid])))
    return out


def nll(pairs, t):
    return -float(np.mean([np.log(max(softmax_t(z, t)[y], 1e-12)) for z, y in pairs]))


def ece_at(pairs, t):
    ps = [softmax_t(z, t) for z, _ in pairs]
    return ece([p.max() for p in ps], [int(p.argmax() == y) for p, (_, y) in zip(ps, pairs)])


def fit(pairs):
    return float(GRID[int(np.argmin([nll(pairs, t) for t in GRID]))])


def calibrate(bundle, rows, min_items=30):
    from app.ort_model import OrtModel

    questions = load_schema()["questions"]
    model = OrtModel(bundle)
    data = collect(model, rows, questions)
    cfg_path = Path(bundle) / "runtime.json"
    cfg = json.loads(cfg_path.read_text())
    temps = list(cfg.get("temperature", [1.0, 1.0, 1.0]))
    report = {}
    for name, pairs in data.items():
        if len(pairs) < min_items:
            report[name] = {"n": len(pairs), "skipped": "fewer than %d items; temperature left at %.3f" % (min_items, temps[QTYPES[name]])}
            continue
        t = fit(pairs)
        report[name] = {"n": len(pairs), "temperature": round(t, 4),
                        "ece_before": round(ece_at(pairs, 1.0), 4), "ece_after": round(ece_at(pairs, t), 4)}
        temps[QTYPES[name]] = t
    cfg["temperature"] = temps
    cfg["temperature_by_options"] = {}
    cfg["calibrated"] = any("temperature" in v for v in report.values())
    cfg_path.write_text(json.dumps(cfg, indent=2))
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, default=DIST)
    args = ap.parse_args()
    rows = load_split("calib")
    if rows is None:
        raise SystemExit("no calib split; run `python -m model.data split` first")
    report = calibrate(args.bundle, rows)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "calibration.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
