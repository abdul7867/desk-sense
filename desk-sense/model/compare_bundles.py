"""Score several bundles on one labeled file, per language and per variety, side by side.

    python -m model.compare_bundles data/synthetic/out_of_corpus.jsonl A=model/x/dist B=model/y/dist --out r.json
Never pass the locked test split here; that is model.evaluate --final (plan R5).
"""
import argparse
import json
from pathlib import Path

from model.data import read_jsonl
from model.evaluate import evaluate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", type=Path)
    ap.add_argument("bundles", nargs="+", help="NAME=bundle_dir")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if args.rows.name == "test.jsonl":
        raise SystemExit("the test split is locked (plan R5): use model.evaluate --final on Day 7")
    from app.ort_model import OrtModel

    rows = read_jsonl(args.rows)
    result = {"rows": str(args.rows), "n": len(rows), "bundles": {}}
    for spec in args.bundles:
        name, path = spec.split("=", 1)
        m = OrtModel(path, threads=4)
        result["bundles"][name] = {"path": path, "vocab": len(m.rt.enc.tok.get_vocab()),
                                   "by_language": evaluate(m.probs, rows),
                                   "by_variety": evaluate(m.probs, rows, key="variety")}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    for name, b in result["bundles"].items():
        print(name, "vocab", b["vocab"], {k: v["accuracy"] for k, v in b["by_variety"].items()})


if __name__ == "__main__":
    main()
