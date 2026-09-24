"""Gate B3 on a browser split: is the local model safe to act alone, and how often can it?

    LAYA_DATA_DIR=data/browser python -m model.browser.evaluate_browser --bundle model/browser-run/dist --split val
    ... --split test --final --bundle A --bundle B     # once, at the end; appended to browser_test_runs.log
Act precision = accuracy on the steps it would do without asking (top probability >= act threshold).
Coverage = share of steps in that zone. The baseline is the ranker's first choice.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from app.ort_model import OrtModel
from model.data import SPLITS, load_split, sha256, target_index
from model.evaluate import ece
from model.pin import REPORTS, ROOT

ZONES = json.loads((ROOT / "schema_browser.json").read_text())["zones"]


def score(rows, probs):
    out = {}
    groups = {"all": rows}
    for r in rows:
        groups.setdefault("wording:" + r["meta"]["target_mode"], []).append(r)
    for name, rs in groups.items():
        top = np.array([probs[r["id"]].max() for r in rs])
        right = np.array([probs[r["id"]].argmax() == r["_y"] for r in rs])
        first = np.array([r["_y"] == 0 for r in rs])
        act = top >= ZONES["act"]
        out[name] = {
            "n": len(rs), "accuracy": round(float(right.mean()), 4), "ranker_first_choice": round(float(first.mean()), 4),
            "act_coverage": round(float(act.mean()), 4),
            "act_precision": round(float(right[act].mean()), 4) if act.any() else None,
            "confirm_or_act_coverage": round(float((top >= ZONES["confirm"]).mean()), 4),
            "ece": round(ece(top, right), 4),
        }
    return out


def run(bundle, rows, threads):
    model = OrtModel(bundle, threads=threads)
    probs = {}
    for i, r in enumerate(rows):
        q = r["questions"]["next"]
        r["_y"] = target_index(q, r["labels"]["next"])
        probs[r["id"]] = np.asarray(model.probs(r["state"], {"next": q})["next"])
        if i % 100 == 0:
            print("%d/%d" % (i, len(rows)), file=sys.stderr, flush=True)
    top = np.array([probs[r["id"]].max() for r in rows])
    right = np.array([probs[r["id"]].argmax() == r["_y"] for r in rows])
    sweep = {}
    for t in (0.85, 0.90, 0.93, 0.95, 0.97, 0.98, 0.99):
        sel = top >= t
        sweep[str(t)] = {"coverage": round(float(sel.mean()), 4),
                         "precision": round(float(right[sel].mean()), 4) if sel.any() else None}
    return {"bundle": str(bundle), "zones": ZONES, "result": score(rows, probs), "act_threshold_sweep": sweep}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, action="append", required=True, help="repeat to score several bundles")
    ap.add_argument("--split", default="val", choices=["val", "calib", "test"])
    ap.add_argument("--final", action="store_true",
                    help="required for the test split: read once, every bundle in the same run, logged")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.split == "test" and not args.final:
        raise SystemExit("the browser test split is locked: read it once, at the end, with --final")
    rows = load_split(args.split)
    if rows is None:
        raise SystemExit("no %s split under LAYA_DATA_DIR" % args.split)
    reports = [run(b, rows, args.threads) for b in args.bundle]
    report = reports[0] if len(reports) == 1 else {"bundles": reports}
    report["split"] = args.split
    out = args.out or REPORTS / ("b3_%s.json" % args.split)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    if args.split == "test":
        with open(REPORTS / "browser_test_runs.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "test_sha256": sha256(SPLITS / "test.jsonl"),
                                "rows": len(rows), "results": [{"bundle": r["bundle"], "all": r["result"]["all"],
                                                                 "at_act_bar": r["act_threshold_sweep"][str(ZONES["act"])]}
                                                                for r in reports]}) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
