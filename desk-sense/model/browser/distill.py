"""Train a pruned student (prune_layers.py) against the full fine-tuned teacher (gate B5).

    LAYA_DATA_DIR=data/browser python -m model.browser.distill \\
        --teacher model/artifacts/ckpt_browser2 --student model/artifacts/student8 --out model/artifacts/student8_distilled

Loss = (1 - alpha) * cross-entropy on the true option + alpha * T^2 * KL(teacher_T || student_T).
Teacher logits are computed once, up front, so each epoch costs only the student's passes.
"""
import argparse
import json
import random
import shutil
import time
from pathlib import Path

import numpy as np
import torch

from model.data import load_split
from model.evaluate import evaluate
from model.finetune.finetune import items_for, micro_batches, peak_rss_mb, torch_prob_fn
from model.pin import REPORTS, load_agent


def teacher_logits(teacher, items, max_tokens):
    from laya.common import collate_items

    teacher.model.eval()
    with torch.no_grad():
        for micro in micro_batches(items, max_tokens):
            b = collate_items([micro], teacher.tok.pad_token_id)
            logits, _ = teacher.model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])
            for it, row in zip(micro, logits.float()):
                it["teacher"] = row[: len(it["markers"])].clone()


def save(agent, student_dir, out, info):
    from safetensors.torch import save_file

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(student_dir, out, ignore=shutil.ignore_patterns("model.safetensors"))  # keeps the pruned config
    cfg = json.loads((out / "rl_agent_config.json").read_text())
    cfg["distillation"] = info
    (out / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2))
    save_file({k: v.detach().cpu().contiguous() for k, v in agent.model.state_dict().items()}, str(out / "model.safetensors"))


def main():
    from laya.common import collate_items

    ap = argparse.ArgumentParser()
    ap.add_argument("--teacher", type=Path, required=True)
    ap.add_argument("--student", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--alpha", type=float, default=0.5)
    ap.add_argument("--temperature", type=float, default=2.0)
    ap.add_argument("--max-len", type=int, default=320)
    ap.add_argument("--max-batch-tokens", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    train_rows, val_rows = load_split("train"), load_split("val")
    torch.manual_seed(args.seed)
    t0 = time.time()
    teacher = load_agent(args.teacher)
    items = items_for(teacher, train_rows, {}, args.max_len)
    teacher_logits(teacher, items, args.max_batch_tokens * 2)
    del teacher
    teacher_min = round((time.time() - t0) / 60, 1)

    agent = load_agent(args.student)
    agent.model.encoder.config.reference_compile = False
    agent.model.encoder.embeddings.tok_embeddings.weight.requires_grad_(False)
    opt = torch.optim.AdamW([p for p in agent.model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.01)
    steps = args.epochs * ((len(items) + args.batch - 1) // args.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(1, steps), pct_start=0.1)
    T, log = args.temperature, []
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
                logits, _ = agent.model(b["input_ids"], b["attention_mask"], b["marker_pos"], b["marker_mask"], b["qtype"])
                logits = logits.float()
                ce = torch.nn.functional.cross_entropy(logits, b["label"], reduction="sum")
                kl = 0.0
                for row, it in zip(logits, micro):
                    k = len(it["markers"])
                    kl = kl + torch.nn.functional.kl_div(torch.log_softmax(row[:k] / T, -1), torch.softmax(it["teacher"] / T, -1),
                                                         reduction="sum") * T * T
                loss = ((1 - args.alpha) * ce + args.alpha * kl) / len(chunk)
                loss.backward()
                total += loss.item()
            torch.nn.utils.clip_grad_norm_(agent.model.parameters(), 1.0)
            opt.step()
            sched.step()
            losses.append(total)
        val = evaluate(torch_prob_fn(agent), val_rows, {})
        log.append({"epoch": epoch + 1, "loss": round(float(np.mean(losses)), 4), "val": {k: v["accuracy"] for k, v in val.items()},
                    "minutes": round((time.time() - t0) / 60, 1)})
        print(json.dumps(log[-1]), flush=True)
    info = {"teacher": str(args.teacher), "student": str(args.student), "epochs": args.epochs, "lr": args.lr,
            "alpha": args.alpha, "temperature": T, "train_items": len(items), "teacher_pass_minutes": teacher_min,
            "minutes": round((time.time() - t0) / 60, 1), "peak_rss_mb": peak_rss_mb(), "log": log,
            "versions": {"torch": torch.__version__}}
    save(agent, args.student, args.out, info)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / ("distill_%s.json" % args.out.name)).write_text(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
