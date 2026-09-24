"""ONNX Runtime model: the only model code the worker loads. No torch, no transformers."""
from pathlib import Path

import numpy as np

from app.runtime import OptionsTooLong, Runtime, collate
from app.worker import release_free_heap

MODEL_FILE = "model.onnx"
# Questions per forward pass are grouped so that rows x sequence length stays under this. Short tickets
# run as one batch; a 512-token ticket runs one question at a time. Measured on the int8 bundle,
# 512-token ticket: 5-question batch peaks at 726 MB, one at a time at 416 MB (DECISIONS.md).
MAX_BATCH_TOKENS = 512




def make_session(model_path, threads=2):
    import onnxruntime as ort

    opts = ort.SessionOptions()
    # Plan §10.1 turns the arena off. Measured here it is the other way round: without it, glibc
    # fragments on per-op mallocs (peak 561 MB on a 512-token ticket); with it, 416 MB (DECISIONS.md).
    opts.enable_cpu_mem_arena = True
    opts.enable_mem_pattern = False
    opts.intra_op_num_threads = threads
    opts.inter_op_num_threads = 1
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])


class OrtModel:
    def __init__(self, bundle_dir, threads=2, max_len=None, max_batch_tokens=MAX_BATCH_TOKENS):
        bundle_dir = Path(bundle_dir)
        self.rt = Runtime(bundle_dir, max_len=max_len)
        release_free_heap()
        self.sess = make_session(bundle_dir / MODEL_FILE, threads)
        self.max_batch_tokens = max_batch_tokens

    def forward(self, items):
        """Logits for every item, in chunks bounded by max_batch_tokens; padded to a common width."""
        chunks, cur = [], []
        for it in items:
            width = max([len(x["ids"]) for x in cur + [it]])
            if cur and width * (len(cur) + 1) > self.max_batch_tokens:
                chunks.append(cur)
                cur = []
            cur.append(it)
        chunks.append(cur)
        kmax = max(len(it["markers"]) for it in items)
        logits = np.full((len(items), kmax), -1e4, dtype=np.float32)
        acts, row = [], 0
        for chunk in chunks:
            lg, act = self.sess.run(None, collate(chunk, self.rt.enc.pad_id))
            logits[row: row + len(chunk), : lg.shape[1]] = lg
            acts.append(act)
            row += len(chunk)
        return logits, np.concatenate(acts)

    def probs(self, state, questions, calibrated=True):
        items, _, _ = self.rt.prepare(state, questions)
        logits, _ = self.forward(items)
        return dict(zip(questions, self.rt.probs(logits, items, calibrated)))

    def raw(self, state, questions):
        """Uncalibrated logits per question, for fitting temperatures."""
        items, _, _ = self.rt.prepare(state, questions)
        logits, _ = self.forward(items)
        return {qid: np.asarray(logits[r, : len(it["markers"])], dtype=np.float64)
                for r, (qid, it) in enumerate(zip(questions, items))}

    def predict(self, state, questions, allow_truncate=False, strict=False):
        try:
            items, batch, info = self.rt.prepare(state, questions, strict)
        except OptionsTooLong as e:
            return {"options_too_long": str(e)}
        if info["truncated"] and not allow_truncate:
            return {"too_long": info}
        logits, act = self.forward(items)
        return {
            "answers": self.rt.decode(questions, items, logits, act),
            "usage": {"input_tokens": int(batch["attention_mask"].sum()), **info},
        }
