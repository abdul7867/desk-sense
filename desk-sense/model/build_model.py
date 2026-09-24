"""The whole model pipeline, in the fixed order (plan §8, R6): trim -> ONNX -> int8 -> calibrate.
Fine-tuning happens before this (model/finetune, on Kaggle); pass its output with --checkpoint.

    python -m model.build_model                                   # base model, stage-A trim
    python -m model.build_model --checkpoint model/artifacts/ckpt --corpus data/raw/tickets.txt

Fails loudly (exit 1) when:
  - G1: ONNX differs from torch by > 0.01 on any probability (skipped for a corpus trim, which
    changes tokenization on purpose; the accuracy check below covers it)
  - any step drops a language's validation accuracy by > 2 points against the torch model
  - with no validation split: int8 flips > 2% of decisive answers against fp32 (proxy)
Writes reports/build.json and reports/build.md.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from model.pin import ARTIFACTS, DIST, REPORTS, ROOT

MAX_DROP = 0.02
MIN_DECISIVE_AGREEMENT = 0.98


def run(step, *args):
    print("\n== %s: %s" % (step, " ".join(args)), flush=True)
    subprocess.run([sys.executable, "-m", *args], cwd=ROOT, check=True)


def accuracy_by_language(result):
    return {lang: v["accuracy"] for lang, v in result.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path, help="fine-tuned checkpoint; default: the pinned base model")
    ap.add_argument("--corpus", type=Path, help="real text for a stage-B vocabulary trim")
    ap.add_argument("--add-top-merges", type=int, default=0, help="with --corpus: extra top-ranked merges kept")
    ap.add_argument("--g1-cases", type=int, default=200)
    args = ap.parse_args()

    from model.data import load_split
    from model.evaluate import evaluate
    from model.export.cases import make_cases
    from model.export.verify_onnx import OrtReference, TorchReference, verify
    from app.ort_model import OrtModel
    import numpy as np

    started = time.time()
    report = {"checkpoint": str(args.checkpoint or "base (pinned)"), "trim": ("B (corpus + top %d merges)" % args.add_top_merges if args.add_top_merges else "B (corpus)") if args.corpus else "A (script)",
              "steps": {}, "failures": []}
    trim, fp32, int8 = ARTIFACTS / "trim", ARTIFACTS / "fp32", ARTIFACTS / "int8"

    trim_args = ["model.trim.trim_vocab", "--out", str(trim)] + (["--corpus", str(args.corpus)] if args.corpus else [])
    if args.corpus and args.add_top_merges:
        trim_args += ["--add-top-merges", str(args.add_top_merges)]
    run("trim", *trim_args)
    export_args = ["model.export.export_onnx", "--out", str(fp32), "--trim", str(trim)]
    run("export", *export_args + (["--checkpoint", str(args.checkpoint)] if args.checkpoint else []))

    torch_ref = TorchReference(args.checkpoint)
    fp32_model = OrtModel(fp32, threads=4)
    fp32_model.rt.keep_ids = np.load(fp32 / "keep_ids.npy")
    g1, _ = verify(fp32_model, torch_ref, make_cases(args.g1_cases))
    report["steps"]["g1"] = g1
    if not args.corpus and not g1["passed"]:
        report["failures"].append("G1: ONNX export differs from torch (worst %.4f)" % g1["worst_max_prob_diff"])

    run("int8", "model.quantize.quantize", "--src", str(fp32), "--dst", str(int8))
    int8_model = OrtModel(int8, threads=4)

    val = load_split("val")
    if val:
        stages = {"torch": torch_ref.probs, "onnx_fp32_trimmed": fp32_model.probs, "int8": int8_model.probs}
        accs = {name: accuracy_by_language(evaluate(fn, val)) for name, fn in stages.items()}
        report["steps"]["val_accuracy"] = accs
        for name in ("onnx_fp32_trimmed", "int8"):
            for lang, base in accs["torch"].items():
                drop = base - accs[name].get(lang, 0.0)
                if drop > MAX_DROP:
                    report["failures"].append("%s drops %s validation accuracy by %.1f points" % (name, lang, drop * 100))
    else:
        drift, _ = verify(int8_model, OrtReference(fp32), make_cases(args.g1_cases))
        report["steps"]["int8_drift_proxy"] = drift
        report["steps"]["val_accuracy"] = "no validation split: accuracy per step not measured"
        if drift["decisive_agreement"] < MIN_DECISIVE_AGREEMENT:
            report["failures"].append("int8 changes %.1f%% of decisive answers" % ((1 - drift["decisive_agreement"]) * 100))
    del torch_ref

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(int8, DIST)
    if load_split("calib"):
        run("calibrate", "model.calibrate.calibrate", "--bundle", str(DIST))
        report["steps"]["calibration"] = json.loads((REPORTS / "calibration.json").read_text())
    else:
        report["steps"]["calibration"] = "no calib split: shipped uncalibrated (temperature 1.0)"
    report["minutes"] = round((time.time() - started) / 60, 1)
    report["passed"] = not report["failures"]

    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "build.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    lines = ["# Model build", "", "- checkpoint: %s" % report["checkpoint"], "- vocabulary trim: %s" % report["trim"],
             "- G1: worst diff %.6f over %d questions -> %s" % (g1["worst_max_prob_diff"], g1["questions"], "pass" if g1["passed"] else "FAIL"),
             "- validation accuracy per step: %s" % json.dumps(report["steps"]["val_accuracy"], ensure_ascii=False),
             "- calibration: %s" % json.dumps(report["steps"]["calibration"]),
             "- result: **%s**" % ("PASS" if report["passed"] else "FAIL: " + "; ".join(report["failures"]))]
    (REPORTS / "build.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
