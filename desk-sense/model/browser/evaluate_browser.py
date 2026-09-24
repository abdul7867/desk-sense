"""Gate B3 on a browser split: is the local model safe to act alone, and how often can it?

    LAYA_DATA_DIR=data/browser python -m model.browser.evaluate_browser --bundle model/browser-run/dist --split val
Act precision = accuracy on the steps it would do without asking (top probability >= act threshold).
Coverage = share of steps in that zone. The baseline is the ranker's first choice.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

from app.ort_model import OrtModel
from model.data import load_split, target_index
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--split", default="val", choices=["val", "calib"], help="test stays locked (read once, at the end)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    rows = load_split(args.split)
    if rows is None:
        raise SystemExit("no %s split under LAYA_DATA_DIR" % args.split)
    model = OrtModel(args.bundle, threads=args.threads)
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
    report = {"bundle": str(args.bundle), "split": args.split, "zones": ZONES, "result": score(rows, probs),
              "act_threshold_sweep": sweep}
    out = args.out or REPORTS / ("b3_%s.json" % args.split)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
