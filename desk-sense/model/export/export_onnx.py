"""Export the full Laya model (encoder + typed decision head) to ONNX with dynamic axes (plan §8.2).

Writes a runnable bundle: model.onnx + model.data (weights as external data, so ORT memory-maps
them instead of holding a second copy) + tokenizer.json + runtime.json.
With --trim DIR (from model.trim.trim_vocab), the embedding table is cut to the kept rows first.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import torch

from model.pin import ARTIFACTS, SHA256, WEEK1_MAX_LEN, load_agent, snapshot_dir

INPUTS = ["input_ids", "attention_mask", "marker_pos", "marker_mask", "qtype"]
OUTPUTS = ["logits", "act_logits"]
DYNAMIC = {
    "input_ids": {0: "n", 1: "seq"},
    "attention_mask": {0: "n", 1: "seq"},
    "marker_pos": {0: "n", 1: "k"},
    "marker_mask": {0: "n", 1: "k"},
    "qtype": {0: "n"},
    "logits": {0: "n", 1: "k"},
    "act_logits": {0: "n"},
}


def verify_checksums(snap):
    for name, want in SHA256.items():
        h = hashlib.sha256()
        with open(snap / name, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != want:
            raise RuntimeError("checksum mismatch for %s: %s" % (name, h.hexdigest()))


def write_bundle_files(agent, snap, out_dir, trim_dir=None):
    tok = agent.tok
    special = {"cls_id": tok.cls_token_id, "sep_id": tok.sep_token_id, "mask_id": tok.mask_token_id,
               "pad_id": tok.pad_token_id, "mask_token": tok.mask_token}
    if trim_dir is not None:
        new = {int(old): i for i, old in enumerate(np.load(trim_dir / "keep_ids.npy"))}
        special = {k: (new[v] if k.endswith("_id") else v) for k, v in special.items()}
    runtime = {
        "source": {"repo": "convaiinnovations/laya-multilingual"},
        "trimmed": trim_dir is not None,
        "max_len": WEEK1_MAX_LEN,
        "head_max_len": agent.cfg.get("head_max_len", 192),
        "special": special,
        "temperature": agent.cfg.get("temperature", [1.0, 1.0, 1.0]),
        "temperature_by_options": agent.cfg.get("temperature_by_options", {}),
    }
    (out_dir / "runtime.json").write_text(json.dumps(runtime, indent=2))
    shutil.copy((trim_dir or snap / "tokenizer") / "tokenizer.json", out_dir / "tokenizer.json")
    if trim_dir is not None:
        shutil.copy(trim_dir / "keep_ids.npy", out_dir / "keep_ids.npy")


def trim_embeddings(model, trim_dir):
    keep = torch.from_numpy(np.load(trim_dir / "keep_ids.npy"))
    emb = model.encoder.embeddings.tok_embeddings
    new = torch.nn.Embedding(len(keep), emb.embedding_dim, padding_idx=None)
    new.weight.data = emb.weight.data[keep].clone()
    model.encoder.embeddings.tok_embeddings = new
    model.encoder.config.vocab_size = len(keep)
    return model


class ExportableHeadLayer(torch.nn.Module):
    """Same weights and math as the head's pre-LN nn.TransformerEncoderLayer (ReLU FFN, eval mode).

    nn.MultiheadAttention's legacy ONNX trace bakes the trace-time sequence length into a Reshape,
    so the exported head only ran at that one length (plan §8.2's main failure mode). Every shape
    here comes from the input at run time.
    """

    def __init__(self, layer):
        super().__init__()
        self.norm1, self.norm2 = layer.norm1, layer.norm2
        self.linear1, self.linear2 = layer.linear1, layer.linear2
        att = layer.self_attn
        self.in_proj_weight, self.in_proj_bias = att.in_proj_weight, att.in_proj_bias
        self.out_proj = att.out_proj
        self.nhead = att.num_heads
        if not layer.norm_first or layer.activation_relu_or_gelu != 1:
            raise RuntimeError("head layer is not the pre-LN ReLU layout this export assumes")

    def forward(self, x, src_key_padding_mask):
        n, L, d = x.shape
        hd = d // self.nhead
        qkv = torch.nn.functional.linear(self.norm1(x), self.in_proj_weight, self.in_proj_bias)
        q, k, v = (t.reshape(n, L, self.nhead, hd).transpose(1, 2) for t in qkv.chunk(3, dim=-1))
        bias = torch.zeros_like(src_key_padding_mask, dtype=x.dtype).masked_fill(src_key_padding_mask, float("-inf"))
        scores = q @ k.transpose(-1, -2) / (hd ** 0.5) + bias[:, None, None, :]
        ctx = (torch.softmax(scores, -1) @ v).transpose(1, 2).reshape(n, L, d)
        x = x + self.out_proj(ctx)
        return x + self.linear2(torch.relu(self.linear1(self.norm2(x))))


def make_exportable(model):
    if model.head is not None:
        model.head.layers = torch.nn.ModuleList(ExportableHeadLayer(layer) for layer in model.head.layers)
    return model


def example_inputs():
    # Longer than ModernBERT's 128-token local window so tracing takes the sliding-attention path.
    b = {
        "input_ids": torch.randint(5, 1000, (3, 300)),
        "attention_mask": torch.ones(3, 300, dtype=torch.long),
        "marker_pos": torch.tensor([[10, 14, 18, 0], [10, 14, 0, 0], [10, 12, 14, 16]]),
        "marker_mask": torch.tensor([[1, 1, 1, 0], [1, 1, 0, 0], [1, 1, 1, 1]], dtype=torch.bool),
        "qtype": torch.tensor([0, 2, 1]),
    }
    b["attention_mask"][1, 200:] = 0
    return tuple(b[k] for k in INPUTS)


def save_external(onnx_path):
    import onnx

    m = onnx.load(str(onnx_path))
    # onnx appends to an existing external-data file; a re-export would double it.
    (onnx_path.parent / "model.data").unlink(missing_ok=True)
    onnx.save_model(m, str(onnx_path), save_as_external_data=True, all_tensors_to_one_file=True,
                    location="model.data", size_threshold=1024)


def export(model_path, out_dir, trim_dir=None, checkpoint=None):
    snap = snapshot_dir()
    verify_checksums(snap)
    agent = load_agent(checkpoint)
    model = agent.model.eval()
    if trim_dir is not None:
        model = trim_embeddings(model, trim_dir)
    inputs = example_inputs()
    with torch.no_grad():
        ref = model(*inputs)
        model = make_exportable(model)
        got = model(*inputs)
        drift = max(float((a - b).abs().max()) for a, b in zip(ref, got))
        if drift > 1e-3:
            raise RuntimeError("exportable head drifts from the original by %g" % drift)
        print("exportable head matches original, max logit diff %.2e" % drift)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in ("model.onnx", "model.data", "keep_ids.npy"):
        (out_dir / stale).unlink(missing_ok=True)
    with torch.no_grad():
        torch.onnx.export(
            model, inputs, str(out_dir / model_path),
            input_names=INPUTS, output_names=OUTPUTS, dynamic_axes=DYNAMIC,
            opset_version=17, do_constant_folding=True, dynamo=False,
        )
    save_external(out_dir / model_path)
    write_bundle_files(agent, snap, out_dir, trim_dir)
    print("exported", out_dir / model_path, round((out_dir / "model.data").stat().st_size / 1e6), "MB of weights")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ARTIFACTS / "fp32")
    ap.add_argument("--trim", type=Path, help="dir with keep_ids.npy + tokenizer.json from model.trim.trim_vocab")
    ap.add_argument("--checkpoint", type=Path, help="fine-tuned checkpoint dir; default: the pinned base model")
    args = ap.parse_args()
    export("model.onnx", args.out, args.trim, args.checkpoint)


if __name__ == "__main__":
    main()
