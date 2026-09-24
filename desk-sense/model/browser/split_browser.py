"""Browser training rows -> train / val / calib / test, split by website (no site in two splits).

    python -m model.browser.split_browser data/browser/mind2web.jsonl --out data/browser/splits

Steps with no target words whose target fell outside the shortlist teach only "none fits": 90% of
them are dropped (seeded), the rest kept so the model still learns when to say it.
"""
import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from model.data import read_jsonl, split_by_group, write_jsonl  # noqa: E402

KEEP_BLIND_NONE = 0.10


def keep(rows, seed):
    rng = random.Random(seed)
    return [r for r in rows
            if not (r["meta"]["target_mode"] == "none" and r["labels"]["next"] == "none_of_these")
            or rng.random() < KEEP_BLIND_NONE]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", default="browser-m2w-1")
    args = ap.parse_args()
    rows = read_jsonl(args.rows)
    kept = keep(rows, "m2w-filter")
    splits = split_by_group(kept, args.seed)
    train_sites = {r["group"] for r in splits["train"]}
    for name in ("val", "calib", "test"):
        if train_sites & {r["group"] for r in splits[name]}:
            raise SystemExit("site overlap between train and %s" % name)
    args.out.mkdir(parents=True, exist_ok=True)
    summary = {"rows_in": len(rows), "rows_kept": len(kept)}
    for name, rs in splits.items():
        write_jsonl(args.out / ("%s.jsonl" % name), rs)
        summary[name] = {"rows": len(rs), "sites": len({r["group"] for r in rs}),
                         "none_label": round(sum(r["labels"]["next"] == "none_of_these" for r in rs) / max(1, len(rs)), 3),
                         "wording": dict(collections.Counter(r["meta"]["target_mode"] for r in rs))}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
