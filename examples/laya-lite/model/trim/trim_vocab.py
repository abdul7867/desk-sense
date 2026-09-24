"""Vocabulary trimming (plan §8.4), done by rebuilding the BPE tokenizer, never by mapping to [UNK] (M6).

Stage A, lossless for anything the guard lets through: drop tokens containing letters outside the
allowed scripts, and the merges that build them. A merge's output contains its inputs' letters, so
none of those merges can fire on Latin/Devanagari text.
Stage B, lossy, the plan's method: `--corpus` keeps only tokens our real text uses (plus the merges
that build them). `--max-merges` is a corpus-free fallback: BPE stopped earlier, by global rank.
Words that lose their token split into smaller kept pieces; every base character and all 256 byte
tokens stay, so nothing becomes <unk>.

Writes tokenizer.json + keep_ids.npy (new id -> old id) for export_onnx --trim.
    python -m model.trim.trim_vocab --out model/artifacts/trim                        # stage A
    python -m model.trim.trim_vocab --corpus data/raw/tickets.txt --out ...          # stage B
"""
import argparse
import json
import unicodedata
from pathlib import Path

import numpy as np

from app.guard import script_of
from model.pin import ARTIFACTS, snapshot_dir

KEEP_ADDED = {"<pad>", "<eos>", "<bos>", "<unk>", "<mask>", "<start_of_turn>", "<end_of_turn>"}


def letters_allowed(token, allowed):
    return all(script_of(c) in allowed for c in token if unicodedata.category(c)[0] in ("L", "M"))


def is_byte_token(token):
    return len(token) == 6 and token.startswith("<0x") and token.endswith(">")


def merge_pair(m):
    return tuple(m) if isinstance(m, list) else tuple(m.split(" ", 1))


def corpus_tokens(tok_path, lines):
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(tok_path))
    used = set()
    for enc in tok.encode_batch([ln for ln in lines if ln.strip()], add_special_tokens=False):
        used.update(enc.tokens)
    return used


def build_closure(tokens, merges):
    """Every token plus the inputs of *every* merge that can build it, recursively.

    BPE reaches a token by whichever merges win on that word, not necessarily the lowest-ranked
    merge that produces it. Following only one producer dropped real intermediates ("▁account"
    fell apart into "▁acc ou nt"). All producers is a superset of every path actually taken.
    """
    producers = {}
    for a, b in merges:
        producers.setdefault(a + b, []).append((a, b))
    out, stack = set(), list(tokens)
    while stack:
        t = stack.pop()
        if t in out:
            continue
        out.add(t)
        for pair in producers.get(t, ()):
            stack.extend(pair)
    return out


def schema_lines(schema):
    """The question text and options the model reads with every ticket (build_sequence's format).
    They must tokenize exactly as in training, so they are always part of the trim corpus."""
    from app.runtime import render_options, to_internal

    lines = []
    for qdef in schema["questions"].values():
        q = to_internal(qdef)
        lines.append("%s question: %s" % (q["t"], q["ins"]))
        lines.extend(" " + o for o in render_options(q))
    return lines


def lossless_on(src_path, out_json, keep_ids, lines):
    """Lines whose tokens change after trimming (should be none for the corpus)."""
    from tokenizers import Tokenizer

    orig = Tokenizer.from_file(str(src_path))
    new = Tokenizer.from_str(json.dumps(out_json))
    bad = []
    for ln in lines:
        a = orig.encode(ln, add_special_tokens=False).ids
        b = [int(keep_ids[i]) for i in new.encode(ln, add_special_tokens=False).ids]
        if a != b:
            bad.append(ln)
    return bad


def trim(tok_json, allowed=("latin", "devanagari"), max_merges=None, corpus=None):
    model = tok_json["model"]
    assert model["type"] == "BPE" and model.get("byte_fallback"), "expects a byte-fallback BPE tokenizer"
    vocab, merges = model["vocab"], [merge_pair(m) for m in model["merges"]]
    produced = {a + b for a, b in merges}
    added = {a["content"] for a in tok_json["added_tokens"]}

    keep = {t for t in vocab if t in KEEP_ADDED or is_byte_token(t) or t == model.get("unk_token")}
    keep |= {t for t in vocab if t not in produced and t not in added and letters_allowed(t, allowed)}

    allowed_merges = [(r, a, b) for r, (a, b) in enumerate(merges) if (a + b) in vocab and letters_allowed(a + b, allowed)]
    if max_merges is not None:
        allowed_merges = allowed_merges[:max_merges]
    if corpus is not None:
        wanted = build_closure(corpus, merges)
        allowed_merges = [(r, a, b) for r, a, b in allowed_merges if a + b in wanted]
    kept_ranks = set()
    changed = True
    while changed:  # fixpoint: a few merges list their inputs after themselves
        changed = False
        for r, a, b in allowed_merges:
            if r not in kept_ranks and a in keep and b in keep:
                kept_ranks.add(r)
                keep.add(a + b)
                changed = True

    old_ids = sorted(vocab[t] for t in keep)
    new_id = {old: new for new, old in enumerate(old_ids)}
    id_to_tok = {i: t for t, i in vocab.items()}
    out = json.loads(json.dumps(tok_json))
    out["model"]["vocab"] = {id_to_tok[old]: new_id[old] for old in old_ids}
    out["model"]["merges"] = [list(merges[r]) for r in sorted(kept_ranks)]
    out["added_tokens"] = [dict(a, id=new_id[a["id"]]) for a in tok_json["added_tokens"] if a["id"] in new_id]
    out["post_processor"] = None
    return out, np.array(old_ids, dtype=np.int64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, help="default: the pinned checkpoint's tokenizer")
    ap.add_argument("--out", type=Path, default=ARTIFACTS / "trim")
    ap.add_argument("--corpus", type=Path, help="real text, one item per line (stage B)")
    ap.add_argument("--max-merges", type=int, default=None, help="corpus-free stage B fallback")
    args = ap.parse_args()
    args.src = args.src or snapshot_dir() / "tokenizer" / "tokenizer.json"
    src = json.loads(args.src.read_text(encoding="utf-8"))
    lines = None
    if args.corpus:
        from model.data import load_schema

        lines = [ln for ln in args.corpus.read_text(encoding="utf-8").splitlines() if ln.strip()]
        lines += schema_lines(load_schema())
    corpus = corpus_tokens(args.src, lines) if lines else None
    out, keep_ids = trim(src, max_merges=args.max_merges, corpus=corpus)
    if lines:
        bad = lossless_on(args.src, out, keep_ids, lines)
        if bad:
            raise SystemExit("corpus trim changed the tokens of %d/%d corpus lines, e.g. %r"
                             % (len(bad), len(lines), bad[0][:80]))
        print("corpus trim is lossless on all %d corpus + schema lines" % len(lines))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "tokenizer.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    np.save(args.out / "keep_ids.npy", keep_ids)
    print("vocab %d -> %d, merges %d -> %d" % (len(src["model"]["vocab"]), len(keep_ids),
                                               len(src["model"]["merges"]), len(out["model"]["merges"])))


if __name__ == "__main__":
    main()
