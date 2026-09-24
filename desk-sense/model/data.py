"""Labeled data: format, splits, labeler agreement.

One JSON object per line in data/labeled/*.jsonl:
    {"id": "t-0001", "language": "hi", "state": "मुझसे दो बार ...",
     "labels": {"department": "billing", "urgency": 2, "refund_requested": true,
                "sentiment": "angry", "needs_human": false}}
`urgency` may be the level index or its text. Missing labels are skipped for that question.
Optional `group` (near-duplicates, one phrasing, one customer) keeps rows together in one split;
optional `stratum` (e.g. department) makes every split get groups from every stratum.

    python -m model.data split                    # data/labeled -> data/splits (70/10/10/10 per language)
    python -m model.data agreement a.jsonl b.jsonl
"""
import argparse
import hashlib
import json
import os
import random
from pathlib import Path

from model.pin import DATA, REPORTS, SCHEMA

LABELED = DATA / "labeled"
SPLITS = DATA / "splits"
FRACTIONS = {"train": 0.7, "val": 0.1, "calib": 0.1, "test": 0.1}


def load_schema():
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def target_index(qdef, value):
    """Label value -> option index in the order the model scores options."""
    if value is None:
        return None
    t = qdef["type"]
    if t == "noul":
        if isinstance(value, str):
            value = value.strip().lower() in ("true", "yes", "1", "haan", "हाँ")
        return int(bool(value))
    options = list(qdef["criteria"].keys()) if t == "choice" and isinstance(qdef["criteria"], dict) else list(qdef["criteria"])
    if t == "score" and isinstance(value, int):
        return value if 0 <= value < len(options) else None
    return options.index(value) if value in options else None


def load_split(name):
    path = SPLITS / ("%s.jsonl" % name)
    return read_jsonl(path) if path.exists() else None


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split_by_group(items, seed):
    """Whole groups go to one split; each stratum spreads its groups over all splits."""
    out = {k: [] for k in FRACTIONS}
    strata = {}
    for r in items:
        strata.setdefault(r.get("stratum"), {}).setdefault(r.get("group", r["id"]), []).append(r)
    for stratum, groups in sorted(strata.items(), key=lambda kv: str(kv[0])):
        keys = sorted(groups)
        random.Random("%s-%s" % (seed, stratum)).shuffle(keys)
        held = max(1, round(len(keys) * FRACTIONS["test"])) if len(keys) >= 4 else 0
        order = ["test"] * held + ["calib"] * held + ["val"] * held
        for i, key in enumerate(keys):
            out[order[i] if i < len(order) else "train"].extend(groups[key])
    return out


def split(seed=7, force=False):
    test_path = SPLITS / "test.jsonl"
    if test_path.exists() and not force:
        raise SystemExit("test split already exists and is locked (plan R5). Re-splitting would leak it into "
                         "training. Use --force only with a DECISIONS.md entry saying why.")
    rows = [r for p in sorted(LABELED.glob("*.jsonl")) for r in read_jsonl(p)]
    if not rows:
        raise SystemExit("no labeled data in %s" % LABELED)
    by_lang = {}
    for r in rows:
        by_lang.setdefault(r["language"], []).append(r)
    out = {k: [] for k in FRACTIONS}
    for lang, items in sorted(by_lang.items()):
        if any("group" in r for r in items):
            for name, rows_ in split_by_group(items, "%s-%s" % (seed, lang)).items():
                out[name].extend(rows_)
            continue
        random.Random("%s-%s" % (seed, lang)).shuffle(items)
        n, start = len(items), 0
        for i, (name, frac) in enumerate(FRACTIONS.items()):
            end = n if i == len(FRACTIONS) - 1 else start + round(n * frac)
            out[name].extend(items[start:end])
            start = end
    SPLITS.mkdir(parents=True, exist_ok=True)
    if test_path.exists():
        os.chmod(test_path, 0o644)
    for name, items in out.items():
        write_jsonl(SPLITS / ("%s.jsonl" % name), items)
    os.chmod(test_path, 0o444)
    lock = {"sha256": sha256(test_path), "rows": len(out["test"]), "seed": seed,
            "counts": {k: {lang: sum(r["language"] == lang for r in v) for lang in by_lang} for k, v in out.items()}}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "test_lock.json").write_text(json.dumps(lock, indent=2))
    print(json.dumps(lock["counts"], indent=2))


def agreement(path_a, path_b):
    """Share of double-labeled items where both labelers gave the same answer, per question."""
    schema = load_schema()["questions"]
    a = {r["id"]: r for r in read_jsonl(path_a)}
    b = {r["id"]: r for r in read_jsonl(path_b)}
    both = sorted(set(a) & set(b))
    result = {}
    for qid, qdef in schema.items():
        pairs = [(target_index(qdef, a[i]["labels"].get(qid)), target_index(qdef, b[i]["labels"].get(qid))) for i in both]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        result[qid] = {"n": len(pairs), "agreement": round(sum(x == y for x, y in pairs) / len(pairs), 3) if pairs else None}
    worst = min((v["agreement"] for v in result.values() if v["agreement"] is not None), default=None)
    result["_verdict"] = ("fix the labeling guide before labeling more (plan Day 2: < 80%)"
                          if worst is not None and worst < 0.8 else "ok")
    return result


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split")
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--force", action="store_true")
    g = sub.add_parser("agreement")
    g.add_argument("a", type=Path)
    g.add_argument("b", type=Path)
    args = ap.parse_args()
    if args.cmd == "split":
        split(args.seed, args.force)
    else:
        print(json.dumps(agreement(args.a, args.b), indent=2))


if __name__ == "__main__":
    main()
