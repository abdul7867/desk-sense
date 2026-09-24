"""Student for gate B5: a copy of a fine-tuned checkpoint with fewer encoder layers.

    python -m model.browser.prune_layers --src model/artifacts/ckpt_browser2 --out model/artifacts/student8
    python -m model.browser.prune_layers --src ... --out ... --keep 0,6,12,21

Default keeps the global-attention layers (mmBERT-base: 0, 3, ..., 21 of 22). ModernBERT picks each
layer's attention from `config.layer_types[index]`, so the kept layers' types are written back in
their new order; an index-based rule (every 3rd layer is global) would silently change them.
Embeddings, the final norm and the decision head are kept unchanged.
"""
import argparse
import json
import re
import shutil
from pathlib import Path


def plan(config, keep=None):
    types = config["layer_types"]
    keep = keep if keep is not None else [i for i, t in enumerate(types) if t == "full_attention"]
    if not keep or any(not 0 <= i < len(types) for i in keep) or sorted(set(keep)) != keep:
        raise ValueError("keep must be sorted, unique layer indices below %d" % len(types))
    return keep, [types[i] for i in keep]


def prune(src, out, keep=None):
    from safetensors.torch import load_file, save_file

    src, out = Path(src), Path(out)
    cfg = json.loads((src / "encoder" / "config.json").read_text())
    keep, types = plan(cfg, keep)
    new_index = {old: new for new, old in enumerate(keep)}
    state = load_file(str(src / "model.safetensors"))
    pruned = {}
    for k, v in state.items():
        m = re.match(r"encoder\.layers\.(\d+)\.(.*)", k)
        if m is None:
            pruned[k] = v
        elif int(m.group(1)) in new_index:
            pruned["encoder.layers.%d.%s" % (new_index[int(m.group(1))], m.group(2))] = v
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(src, out, ignore=shutil.ignore_patterns("model.safetensors"))
    cfg.update(num_hidden_layers=len(keep), layer_types=types)
    (out / "encoder" / "config.json").write_text(json.dumps(cfg, indent=2))
    agent_cfg = json.loads((out / "rl_agent_config.json").read_text())
    agent_cfg["pruned_from"] = {"checkpoint": str(src), "kept_layers": keep, "layer_types": types}
    (out / "rl_agent_config.json").write_text(json.dumps(agent_cfg, indent=2))
    save_file(pruned, str(out / "model.safetensors"))
    return keep, types


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--keep", help="comma-separated layer indices; default: the global-attention layers")
    args = ap.parse_args()
    keep = [int(x) for x in args.keep.split(",")] if args.keep else None
    keep, types = prune(args.src, args.out, keep)
    print(json.dumps({"kept_layers": keep, "layer_types": types}))


if __name__ == "__main__":
    main()
