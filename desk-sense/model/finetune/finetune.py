"""Fine-tune Laya on our labeled splits (plan §8.1). Meant for a Kaggle GPU; runs on CPU, slowly.

Written against laya 0.3.6's own model and sequence code because the author's notebook could not be
fetched from this environment. Saves a checkpoint `laya.load()` can read, so export_onnx --checkpoint
takes it directly.

    python -m model.finetune.finetune --out model/artifacts/ckpt                        # full (Day 3)
    python -m model.finetune.finetune --per-language 200 --out model/artifacts/ckpt_g3  # G3 (Day 2)
"""
import argparse
import json
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch

from model.data import load_schema, load_split, target_index
from model.evaluate import evaluate, majority_baseline
from model.pin import REPORTS, WEEK1_MAX_LEN, load_agent, snapshot_dir


def items_for(agent, rows, questions, max_len):
    from laya.common import QTYPES, build_sequence

    from app.runtime import to_internal

    head = agent.cfg.get("head_max_len", 192)
    out = []
    for r in rows:
        for qid, qdef in (r.get("questions") or questions).items():
            y = target_index(qdef, r["labels"].get(qid))
            if y is None:
                continue
            q = to_internal(qdef)
            ids, markers = build_sequence(agent.tok, r["state"], q, max_len, head)
            out.append({"ids": ids, "markers": markers, "qtype": QTYPES[q["t"]], "label": y})
    return out


def micro_batches(items, max_tokens):
    """Split a batch so rows x longest sequence stays under max_tokens (activation memory bound).
    Long tickets run alone; short ones share a pass."""
    out, cur = [], []
    for it in sorted(items, key=lambda x: len(x["ids"])):
        width = max(len(x["ids"]) for x in cur + [it])
        if cur and width * (len(cur) + 1) > max_tokens:
            out.append(cur)
            cur = []
        cur.append(it)
    if cur:
        out.append(cur)
    return out


def limit_per_language(rows, n, seed):
    by = {}
    for r in rows:
        by.setdefault(r["language"], []).append(r)
    out = []
    for lang, rs in by.items():
        random.Random(seed).shuffle(rs)
        out.extend(rs[:n])
    return out


def torch_prob_fn(agent):
    def fn(state, qs):
        agent.model.eval()
        with torch.no_grad():
            ans = agent.predict(state, qs)["answers"]
        out = {}
        for qid, a in ans.items():
            out[qid] = np.array([1 - a["noul"], a["noul"]]) if a["type"] == "noul" else np.array(list(a["probabilities"].values()))
        return out
    return fn


def peak_rss_mb():
    try:
        import resource

        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    except ImportError:  # Windows
        return None


def save_checkpoint(agent, out, info):
    from safetensors.torch import save_file

    out.mkdir(parents=True, exist_ok=True)
    snap = snapshot_dir()
    for sub in ("tokenizer", "encoder"):
        if (out / sub).exists():
            shutil.rmtree(out / sub)
        shutil.copytree(snap / sub, out / sub)
    cfg = dict(agent.cfg, training=info, fine_tuned_from=str(snap.name))
    (out / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2))
    sd = {k: v.detach().cpu().contiguous() for k, v in agent.model.state_dict().items()}
    save_file(sd, str(out / "model.safetensors"))


def train(args):
    from laya.common import collate_items

    questions = load_schema()["questions"]
    train_rows, val_rows = load_split("train"), load_split("val")
    if train_rows is None or val_rows is None:
        raise SystemExit("need data/splits/train.jsonl and val.jsonl; run `python -m model.data split`")
    if args.per_language:
        train_rows = limit_per_language(train_rows, args.per_language, args.seed)
    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    agent = load_agent(args.init, device=device)
    agent.model.encoder.config.reference_compile = False
    if args.freeze_embeddings:
        # 197M of the 322M parameters; our few hundred tickets cannot improve them, and frozen rows
        # stay identical to the base model, so trimming and quantizing them behaves as measured.
        agent.model.encoder.embeddings.tok_embeddings.weight.requires_grad_(False)
    items = items_for(agent, train_rows, questions, args.max_len)
    opt = torch.optim.AdamW([p for p in agent.model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.01)
    steps = args.epochs * ((len(items) + args.batch - 1) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(1, steps), pct_start=0.1)
    use_amp = device == "cuda"
    log = []
    t0 = time.time()
    for epoch in range(args.epochs):
        agent.model.train()
        random.Random(args.seed + epoch).shuffle(items)
        losses = []
        for i in range(0, len(items), args.batch):
            chunk = items[i: i + args.batch]
            opt.zero_grad()
            total = 0.0
            for micro in micro_batches(chunk, args.max_batch_tokens):
                b = collate_items([micro], agent.tok.pad_token_id)
                with torch.autocast(device_type=device, dtype=torch.bfloat16, enabled=use_amp):
                    logits, _ = agent.model(b["input_ids"].to(device), b["attention_mask"].to(device),
                                            b["marker_pos"].to(device), b["marker_mask"].to(device), b["qtype"].to(device))
                # Sum-reduced and divided by the full batch: gradients equal one pass over `chunk`.
                loss = torch.nn.functional.cross_entropy(logits.float(), b["label"].to(device), reduction="sum") / len(chunk)
                loss.backward()
                total += loss.item()
            loss = torch.tensor(total)
            torch.nn.utils.clip_grad_norm_(agent.model.parameters(), 1.0)
            opt.step()
            sched.step()
            losses.append(loss.item())
            if args.max_steps and len(losses) >= args.max_steps:
                break
        val = evaluate(torch_prob_fn(agent), val_rows, questions)
        log.append({"epoch": epoch + 1, "train_loss": round(float(np.mean(losses)), 4),
                    "val": {k: v["accuracy"] for k, v in val.items()}, "minutes": round((time.time() - t0) / 60, 1)})
        print(json.dumps(log[-1]), flush=True)
    base = majority_baseline(train_rows, val_rows, questions)
    g3 = {lang: {"model": val[lang]["accuracy"], "majority": base[lang]["accuracy"],
                 "margin": round(val[lang]["accuracy"] - base[lang]["accuracy"], 4),
                 "passed": val[lang]["accuracy"] - base[lang]["accuracy"] >= 0.10} for lang in val}
    info = {"epochs": args.epochs, "lr": args.lr, "batch": args.batch, "train_rows": len(train_rows),
            "freeze_embeddings": args.freeze_embeddings, "minutes": round((time.time() - t0) / 60, 1),
            "peak_rss_mb": peak_rss_mb(),
            "train_items": len(items), "device": device, "log": log, "g3": g3,
            "versions": {"torch": torch.__version__}}
    save_checkpoint(agent, args.out, info)
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / ("finetune_%s.json" % args.out.name)).write_text(json.dumps(info, indent=2))
    print(json.dumps({"g3": g3}, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--init", type=Path, help="start from this checkpoint; default: the pinned base model")
    ap.add_argument("--per-language", type=int, help="G3: use only this many training rows per language")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch", type=int, default=16, help="(ticket, question) items per step")
    ap.add_argument("--max-len", type=int, default=WEEK1_MAX_LEN)
    ap.add_argument("--max-steps", type=int, default=0, help="stop each epoch early (smoke tests)")
    ap.add_argument("--max-batch-tokens", type=int, default=2048,
                    help="micro-batch token budget; 16 x 512-token items needed 14 GB on CPU and were OOM-killed")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--no-freeze-embeddings", dest="freeze_embeddings", action="store_false",
                    help="also train the 256k x 768 embedding table (much more memory)")
    train(ap.parse_args())


if __name__ == "__main__":
    main()
