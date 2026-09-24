"""Per-language accuracy and ECE on a split.

    python -m model.evaluate --bundle model/dist --split val
The test split is refused unless --final (plan R5); every final run is appended to reports/test_runs.log.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from model.data import load_schema, load_split, sha256, SPLITS, target_index
from model.pin import DIST, REPORTS

ECE_BINS = 15


def ece(conf, correct, bins=ECE_BINS):
    conf, correct = np.asarray(conf, float), np.asarray(correct, float)
    if len(conf) == 0:
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (conf > lo) & (conf <= hi)
        if sel.any():
            total += sel.mean() * abs(conf[sel].mean() - correct[sel].mean())
    return float(total)


def predictions(prob_fn, rows, questions):
    """prob_fn(state, questions) -> {qid: probs}. Yields (row, qid, probs, target)."""
    for r in rows:
        qs = {q: questions[q] for q in questions if target_index(questions[q], r["labels"].get(q)) is not None}
        if not qs:
            continue
        probs = prob_fn(r["state"], qs)
        for qid in qs:
            yield r, qid, np.asarray(probs[qid]), target_index(questions[qid], r["labels"][qid])


def score(records):
    """records: (key, qid, qtype, probs, target) -> per-key (language or variety) summary."""
    out = {}
    for lang in sorted({r[0] for r in records}):
        rs = [r for r in records if r[0] == lang]
        correct = [int(p.argmax() == t) for _, _, _, p, t in rs]
        conf = [float(p.max()) for _, _, _, p, _ in rs]
        per_q = {}
        for qid in sorted({r[1] for r in rs}):
            qc = [int(p.argmax() == t) for _, q, _, p, t in rs if q == qid]
            per_q[qid] = {"n": len(qc), "accuracy": round(float(np.mean(qc)), 4)}
        out[lang] = {"n": len(rs), "accuracy": round(float(np.mean(correct)), 4),
                     "ece": round(ece(conf, correct), 4), "per_question": per_q}
    return out


def evaluate(prob_fn, rows, questions=None, key="language"):
    questions = questions or load_schema()["questions"]
    records = [(r.get(key, r["language"]), qid, questions[qid]["type"], p, t)
               for r, qid, p, t in predictions(prob_fn, rows, questions)]
    return score(records)


def evaluate_multi(prob_fn, rows, keys, questions=None):
    """One pass over the model, scored under several groupings (the test split is read once)."""
    questions = questions or load_schema()["questions"]
    preds = list(predictions(prob_fn, rows, questions))
    return {k: score([(r.get(k, r["language"]), qid, questions[qid]["type"], p, t) for r, qid, p, t in preds])
            for k in keys}


def majority_baseline(train_rows, eval_rows, questions=None):
    """G3's yardstick: always answer the most common training label."""
    questions = questions or load_schema()["questions"]
    majority = {}
    for qid, qdef in questions.items():
        ts = [target_index(qdef, r["labels"].get(qid)) for r in train_rows]
        ts = [t for t in ts if t is not None]
        if ts:
            majority[qid] = max(set(ts), key=ts.count)

    def prob_fn(state, qs):
        out = {}
        for qid in qs:
            k = len(qs[qid]["criteria"]) if qs[qid]["type"] != "noul" else 2
            p = np.zeros(k)
            p[majority.get(qid, 0)] = 1.0
            out[qid] = p
        return out

    return evaluate(prob_fn, eval_rows, questions)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, default=DIST)
    ap.add_argument("--split", default="val", choices=["train", "val", "calib", "test"])
    ap.add_argument("--final", action="store_true", help="required for the test split (Day 7, once)")
    ap.add_argument("--by", default="language", help="group results by this row field (e.g. variety)")
    args = ap.parse_args()
    if args.split == "test" and not args.final:
        raise SystemExit("the test split is locked (plan R5): run it once on Day 7 with --final")
    rows = load_split(args.split)
    if rows is None:
        raise SystemExit("no %s split; run `python -m model.data split` first" % args.split)
    from app.ort_model import OrtModel

    m = OrtModel(args.bundle)
    keys = [args.by] + (["variety"] if args.by != "variety" and any("variety" in r for r in rows) else [])
    scored = evaluate_multi(m.probs, rows, keys)
    result = scored[args.by]
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.split == "test":
        REPORTS.mkdir(exist_ok=True)
        with open(REPORTS / "test_runs.log", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "bundle": str(args.bundle),
                                "test_sha256": sha256(SPLITS / "test.jsonl"), "result": result,
                                "by_other_keys": {k: v for k, v in scored.items() if k != args.by}},
                               ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
