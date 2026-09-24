"""Gate G1 (plan §8.3): same inputs, compare probabilities.

    python -m model.export.verify_onnx --bundle model/artifacts/fp32            # vs original torch model
    python -m model.export.verify_onnx --bundle int8 --reference fp32 --tag int8 # drift report, no torch
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np

from app.ort_model import OrtModel
from model.export.cases import make_cases
from model.pin import REPORTS, WEEK1_MAX_LEN

TOL = 0.01
DECISIVE_MARGIN = 0.2


def probs_from_answer(ans):
    if ans["type"] == "noul":
        return np.array([1.0 - ans["noul"], ans["noul"]])
    return np.array(list(ans["probabilities"].values()))


class TorchReference:
    def __init__(self, checkpoint=None):
        from model.pin import load_agent

        self.agent = load_agent(checkpoint)
        self.agent.cfg["max_len"] = WEEK1_MAX_LEN

    def probs(self, state, questions):
        answers = self.agent.predict(state, questions)["answers"]
        return {qid: probs_from_answer(a) for qid, a in answers.items()}

    def token_parity(self, rt, state, questions):
        from laya.common import build_sequence

        from app.runtime import build_sequence as port, to_internal

        keep = getattr(rt, "keep_ids", None)
        for qdef in questions.values():
            q = to_internal(qdef)
            a = build_sequence(self.agent.tok, state, q, rt.max_len, rt.head_max_len)
            b = port(rt.enc, state, q, rt.max_len, rt.head_max_len)
            ids = [int(keep[i]) for i in b[0]] if keep is not None else b[0]
            if (a[0], a[1]) != (ids, b[1]):
                return False
        return True


class OrtReference:
    def __init__(self, bundle):
        self.m = OrtModel(bundle, threads=4)

    def probs(self, state, questions):
        return self.m.probs(state, questions)

    def token_parity(self, rt, state, questions):
        return True


def verify(candidate, reference, cases, tol=TOL):
    worst, failures, parity_fail, agree, total, lat = 0.0, [], 0, 0, 0, []
    diffs, dec_total, dec_agree = [], 0, 0
    for case in cases:
        state, qs = case["state"], case["questions"]
        if not reference.token_parity(candidate.rt, state, qs):
            parity_fail += 1
        a = reference.probs(state, qs)
        t = time.perf_counter()
        b = candidate.probs(state, qs)
        lat.append((time.perf_counter() - t) * 1000)
        for qid in qs:
            diff = float(np.max(np.abs(a[qid] - b[qid])))
            worst = max(worst, diff)
            diffs.append(diff)
            total += 1
            same = int(a[qid].argmax() == b[qid].argmax())
            agree += same
            top2 = np.sort(a[qid])[-2:]
            if top2[1] - top2[0] >= DECISIVE_MARGIN:
                dec_total += 1
                dec_agree += same
            if diff > tol:
                failures.append({"case": case["id"], "q": qid, "diff": round(diff, 5), "k": len(a[qid])})
    return {
        "cases": len(cases), "questions": total, "tolerance": tol,
        "worst_max_prob_diff": round(worst, 6), "failures": len(failures),
        "mean_max_prob_diff": round(float(np.mean(diffs)), 6),
        "argmax_agreement": round(agree / total, 4),
        "decisive_questions": dec_total,
        "decisive_agreement": round(dec_agree / max(1, dec_total), 4),
        "token_parity_failures": parity_fail,
        "candidate_latency_ms_p50": round(float(np.percentile(lat, 50)), 1),
        "candidate_latency_ms_p95": round(float(np.percentile(lat, 95)), 1),
        "passed": not failures and parity_fail == 0,
    }, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--reference", type=Path, help="bundle dir; omit to compare against the torch original")
    ap.add_argument("--checkpoint", type=Path, help="torch reference checkpoint; default: the pinned base model")
    ap.add_argument("--tag", default="g1")
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()

    reference = OrtReference(args.reference) if args.reference else TorchReference(args.checkpoint)
    candidate = OrtModel(args.bundle, threads=4)
    if (args.bundle / "keep_ids.npy").exists():  # trimmed: compare token ids in the original vocabulary
        candidate.rt.keep_ids = np.load(args.bundle / "keep_ids.npy")
    summary, failures = verify(candidate, reference, make_cases(args.n))
    summary["candidate"] = str(args.bundle)
    summary["reference"] = str(args.reference or "torch original (laya 0.3.6)")
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / ("%s_summary.json" % args.tag)).write_text(json.dumps(summary, indent=2))
    (REPORTS / ("%s_failures.json" % args.tag)).write_text(json.dumps(failures, indent=2))
    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
