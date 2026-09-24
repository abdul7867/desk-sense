"""int8 quantization (plan §8.5). See DECISIONS.md 2026-09-23 for why the default is weight-only.

`weight-only` (default): block-wise int8 weights (MatMulNBits / GatherBlockQuantized), fp32 activations.
`dynamic`: the plan's original quantize_dynamic. It also quantizes activations per tensor, and
ModernBERT's activation outliers (worst in mlp.Wo) wreck it: 73% argmax agreement with fp32.
Gather is included in both so the 256k x 768 embedding table (~60% of parameters) is quantized too.
"""
import argparse
import shutil
from pathlib import Path

from model.pin import ARTIFACTS

OP_TYPES = ["MatMul", "Gather"]
EMBEDDING_NODE = "/encoder/embeddings/tok_embeddings/Gather"


BUNDLE_FILES = ("tokenizer.json", "runtime.json", "keep_ids.npy")


def copy_bundle_files(src, dst):
    for name in BUNDLE_FILES:
        if (src / name).exists():
            shutil.copy(src / name, dst / name)


def save_external(model, dst):
    import onnx

    for stale in ("model.onnx", "model.data"):
        (dst / stale).unlink(missing_ok=True)
    onnx.save_model(model, str(dst / "model.onnx"), save_as_external_data=True, all_tensors_to_one_file=True,
                    location="model.data", size_threshold=1024)


def weights_mb(dst):
    return round(sum(f.stat().st_size for f in dst.iterdir() if f.name not in BUNDLE_FILES) / 1e6)


def quantize_embedding_blocks(model, block=32, node_name=EMBEDDING_NODE):
    """Gather(W, ids) -> Reshape(Gather(W_int8, ids) * Gather(scale, ids), [.., d]).

    ORT's weight-only quantizer only does 4-bit Gather. This is symmetric int8 with one scale per
    `block` values of each token row (block=0: one scale per row).
    """
    import numpy as np
    from onnx import helper, numpy_helper

    g = model.graph
    node = next(n for n in g.node if n.name == node_name)
    init = next(i for i in g.initializer if i.name == node.input[0])
    w = numpy_helper.to_array(init).astype(np.float32)
    V, d = w.shape
    b = d if block <= 0 else block
    wb = w.reshape(V, d // b, b)
    scale = np.maximum(np.abs(wb).max(axis=2, keepdims=True), 1e-8) / 127.0
    wq = np.clip(np.round(wb / scale), -127, 127).astype(np.int8)

    base, ids, out = node.input[0], node.input[1], node.output[0]
    g.initializer.remove(init)
    g.initializer.extend([numpy_helper.from_array(wq, base + "_int8"),
                          numpy_helper.from_array(scale.astype(np.float32), base + "_scale"),
                          numpy_helper.from_array(np.array([0, 0, d], dtype=np.int64), base + "_shape")])
    idx = list(g.node).index(node)
    g.node.remove(node)
    new = [
        helper.make_node("Gather", [base + "_int8", ids], [out + "_q"], name=node_name + "_q", axis=0),
        helper.make_node("Cast", [out + "_q"], [out + "_qf"], name=node_name + "_cast", to=1),
        helper.make_node("Gather", [base + "_scale", ids], [out + "_s"], name=node_name + "_scale", axis=0),
        helper.make_node("Mul", [out + "_qf", out + "_s"], [out + "_b"], name=node_name + "_dequant"),
        helper.make_node("Reshape", [out + "_b", base + "_shape"], [out], name=node_name + "_reshape"),
    ]
    for i, n in enumerate(new):
        g.node.insert(idx + i, n)
    return float(np.abs((wq.astype(np.float32) * scale).reshape(V, d) - w).max())


def quantize_weight_only(src, dst, bits=8, block_size=32, emb_block=32, accuracy_level=None):
    import onnx
    from onnxruntime.quantization.matmul_nbits_quantizer import DefaultWeightOnlyQuantConfig, MatMulNBitsQuantizer

    dst.mkdir(parents=True, exist_ok=True)
    model = onnx.load(str(src / "model.onnx"))
    err = quantize_embedding_blocks(model, emb_block)
    print("embedding table int8 (block %d), max abs error %.2e" % (emb_block, err))
    kw = dict(block_size=block_size, is_symmetric=True, bits=bits, accuracy_level=accuracy_level,
              op_types_to_quantize=("MatMul",), quant_axes=(("MatMul", 0),))
    qz = MatMulNBitsQuantizer(model, algo_config=DefaultWeightOnlyQuantConfig(**kw), **kw)
    qz.process()
    save_external(qz.model.model, dst)
    copy_bundle_files(src, dst)
    print("int%d weight-only" % bits, dst, weights_mb(dst), "MB")


def quantize_dynamic_int8(src, dst, per_channel=False):
    from onnxruntime.quantization import QuantType, quantize_dynamic

    dst.mkdir(parents=True, exist_ok=True)
    quantize_dynamic(
        model_input=str(src / "model.onnx"),
        model_output=str(dst / "model.onnx"),
        use_external_data_format=True,
        weight_type=QuantType.QInt8,
        op_types_to_quantize=OP_TYPES,
        per_channel=per_channel,
        extra_options={"MatMulConstBOnly": True},
    )
    copy_bundle_files(src, dst)
    print("int8 dynamic", dst, weights_mb(dst), "MB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ARTIFACTS / "fp32")
    ap.add_argument("--dst", type=Path, default=ARTIFACTS / "int8")
    ap.add_argument("--mode", choices=["weight-only", "dynamic"], default="weight-only")
    ap.add_argument("--bits", type=int, default=8, choices=[4, 8])
    ap.add_argument("--block-size", type=int, default=32)
    ap.add_argument("--emb-block", type=int, default=32, help="0 = one scale per embedding row")
    ap.add_argument("--accuracy-level", type=int, choices=[1, 4], help="4 = int8 compute with block-quantized activations")
    ap.add_argument("--per-channel", action="store_true", help="dynamic mode only")
    args = ap.parse_args()
    if args.mode == "dynamic":
        quantize_dynamic_int8(args.src, args.dst, args.per_channel)
    else:
        quantize_weight_only(args.src, args.dst, args.bits, args.block_size, args.emb_block, args.accuracy_level)


if __name__ == "__main__":
    main()
