"""Which layer groups survive int8? Quantize one group at a time, measure drift against fp32.

    python -m model.quantize.sweep --n 60
"""
import argparse
import json
import re
import tempfile
from pathlib import Path

import onnx

from model.export.verify_onnx import OrtReference, verify
from model.export.cases import make_cases
from model.pin import ARTIFACTS, REPORTS
from model.quantize.quantize import copy_bundle_files, weights_mb

GROUPS = {
    "embeddings": r"^/encoder/embeddings/tok_embeddings/Gather$",
    "enc_attn_qkv": r"^/encoder/layers\.\d+/attn/Wqkv/MatMul$",
    "enc_attn_out": r"^/encoder/layers\.\d+/attn/Wo/MatMul$",
    "enc_mlp_in": r"^/encoder/layers\.\d+/mlp/Wi/MatMul$",
    "enc_mlp_out": r"^/encoder/layers\.\d+/mlp/Wo/MatMul$",
    "decision_head": r"^/(layers\.\d+|scorer)/",
}


def weight_nodes(model_path):
    m = onnx.load(str(model_path), load_external_data=False)
    init = {i.name for i in m.graph.initializer}
    return [n.name for n in m.graph.node
            if n.op_type in ("MatMul", "Gather") and any(i in init for i in n.input)]


def nodes_matching(names, patterns):
    return [n for n in names if any(re.search(GROUPS[p], n) for p in patterns)]


def quantize_nodes(src, dst, nodes, per_channel=False):
    from onnxruntime.quantization import QuantType, quantize_dynamic

    dst.mkdir(parents=True, exist_ok=True)
    quantize_dynamic(str(src / "model.onnx"), str(dst / "model.onnx"), weight_type=QuantType.QInt8,
                     nodes_to_quantize=nodes, per_channel=per_channel, use_external_data_format=True,
                     extra_options={"MatMulConstBOnly": True})
    copy_bundle_files(src, dst)
    return weights_mb(dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ARTIFACTS / "fp32")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--variants", default=",".join(GROUPS))
    args = ap.parse_args()

    names = weight_nodes(args.src / "model.onnx")
    reference = OrtReference(args.src)
    cases = make_cases(args.n, seed=99)
    results = {}
    for variant in args.variants.split(","):
        groups = variant.split("+")
        with tempfile.TemporaryDirectory() as tmp:
            size = quantize_nodes(args.src, Path(tmp), nodes_matching(names, groups))
            from app.ort_model import OrtModel

            summary, _ = verify(OrtModel(tmp, threads=4), reference, cases)
        results[variant] = {"size_mb": round(size), "worst": summary["worst_max_prob_diff"],
                            "argmax_agreement": summary["argmax_agreement"], "over_tol": summary["failures"]}
        print(variant, results[variant], flush=True)
    REPORTS.mkdir(exist_ok=True)
    out = REPORTS / "quant_sweep.json"
    prev = json.loads(out.read_text()) if out.exists() else {}
    prev.update(results)
    out.write_text(json.dumps(prev, indent=2))


if __name__ == "__main__":
    main()
