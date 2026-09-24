"""Torch-free port of Laya's sequence building and answer decoding (laya 0.3.6, common.py/agent.py).

The worker must not import torch or transformers (plan §10.1), so everything the model needs
around its forward pass lives here, on `tokenizers` + numpy. G1 checks this port token-for-token
against the original.
"""
import json
import math
from pathlib import Path

import numpy as np

QTYPES = {"choice": 0, "score": 1, "noul": 2}
QTYPE_NAMES = {v: k for k, v in QTYPES.items()}

# laya clamps shipped temperatures to this range; sharper would publish coin flips as certainties.
TEMP_MIN, TEMP_MAX = 0.5, 5.0


def clamp_temperature(t):
    try:
        t = float(t)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(t):
        return 1.0
    return min(TEMP_MAX, max(TEMP_MIN, t))


def serialize_state(state):
    return state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)


def render_criterion(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "), default=str)


def to_internal(qdef):
    t = qdef["type"]
    crit = qdef.get("criteria")
    if t == "choice" and isinstance(crit, list):
        crit = {c: None for c in crit}
    ins = qdef["instructions"]
    if not isinstance(ins, str):
        ins = json.dumps(ins)
    return {"t": t, "ins": ins, "crit": crit}


def render_options(q):
    t, crit = q["t"], q.get("crit")
    if t == "choice":
        return [k if v is None or v == "" else "%s: %s" % (k, render_criterion(v)) for k, v in crit.items()]
    if t == "score":
        return ["level %d: %s" % (i, render_criterion(c)) for i, c in enumerate(crit)]
    crit = crit or {}
    f, tr = crit.get("false"), crit.get("true")
    return [
        "false: " + (render_criterion(f) if f not in (None, "") else "no, the statement does not hold"),
        "true: " + (render_criterion(tr) if tr not in (None, "") else "yes, the statement holds"),
    ]


class TextEncoder:
    """`tokenizers` wrapper exposing the special ids Laya's sequence format needs."""

    def __init__(self, tokenizer_path, special):
        from tokenizers import Tokenizer

        self.tok = Tokenizer.from_file(str(tokenizer_path))
        self.cls_id = special["cls_id"]
        self.sep_id = special["sep_id"]
        self.mask_id = special["mask_id"]
        self.pad_id = special["pad_id"]
        self.mask_token = special["mask_token"]

    def ids(self, text):
        return self.tok.encode(text, add_special_tokens=False).ids


def build_sequence(enc, state, q, max_len, head_max_len, state_ids=None):
    """[CLS] <type> instructions [SEP] [MASK] opt0 [MASK] opt1 ... [SEP] state [SEP].
    `state_ids`: the state already tokenized, so a 5-question request tokenizes the ticket once."""
    mask = enc.mask_token
    opts = render_options(q)
    ins = str(q["ins"]).replace(mask, " ")
    head_ids = enc.ids("%s question: %s" % (q["t"], ins))
    opt_ids = [[enc.mask_id] + enc.ids(" " + o.replace(mask, " "))[:48] for o in opts]
    opt_budget = head_max_len - sum(len(o) for o in opt_ids)
    if opt_budget < 16:
        per = max(4, (head_max_len - 16) // max(1, len(opt_ids)))
        opt_ids = [o[:per] for o in opt_ids]
        opt_budget = head_max_len - sum(len(o) for o in opt_ids)
    head_ids = head_ids[: max(8, opt_budget)]
    ids = [enc.cls_id] + head_ids + [enc.sep_id]
    markers = []
    for o in opt_ids:
        markers.append(len(ids))
        ids.extend(o)
    ids.append(enc.sep_id)
    room = max(0, max_len - len(ids) - 1)
    st = state_ids if state_ids is not None else enc.ids(serialize_state(state).replace(mask, " "))
    ids = ids + st[:room] + [enc.sep_id]
    return ids[:max_len], [m for m in markers if m < max_len], room, len(st)


def collate(items, pad_id):
    n, L = len(items), max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    ids = np.full((n, L), pad_id, dtype=np.int64)
    att = np.zeros((n, L), dtype=np.int64)
    mpos = np.zeros((n, kmax), dtype=np.int64)
    mmask = np.zeros((n, kmax), dtype=bool)
    for i, it in enumerate(items):
        ids[i, : len(it["ids"])] = it["ids"]
        att[i, : len(it["ids"])] = 1
        k = len(it["markers"])
        mpos[i, :k] = it["markers"]
        mmask[i, :k] = True
    qtype = np.array([it["qtype"] for it in items], dtype=np.int64)
    return {"input_ids": ids, "attention_mask": att, "marker_pos": mpos, "marker_mask": mmask, "qtype": qtype}


def confidence_from_probs(p, k):
    if k < 2:
        return 1.0
    p = p[:k]
    ent = -(p * np.log(np.clip(p, 1e-12, 1.0))).sum()
    return float(np.clip(1.0 - ent / math.log(k), 0.0, 1.0))


def temp_bucket(qtype, k):
    size = "2" if k <= 2 else "3-5" if k <= 5 else "6-10" if k <= 10 else "11+"
    return "%s:%s" % (QTYPE_NAMES[int(qtype)], size)


def softmax(z):
    z = z - z.max()
    p = np.exp(z)
    return p / p.sum()


class Runtime:
    """Everything around the forward pass. `forward` is any callable taking the collated batch."""

    def __init__(self, bundle_dir, max_len=None):
        bundle_dir = Path(bundle_dir)
        self.cfg = json.loads((bundle_dir / "runtime.json").read_text())
        self.enc = TextEncoder(bundle_dir / "tokenizer.json", self.cfg["special"])
        self.max_len = max_len or self.cfg["max_len"]
        self.head_max_len = self.cfg["head_max_len"]
        self.temperature = [clamp_temperature(t) for t in self.cfg.get("temperature", [1.0, 1.0, 1.0])]
        self.temperature_by_options = {k: clamp_temperature(v) for k, v in self.cfg.get("temperature_by_options", {}).items()}

    def prepare(self, state, questions):
        """Returns items, the collated batch, and length info: `room` is how many state tokens the
        tightest question leaves space for; `truncated` means the model would not see all of it."""
        items, room = [], self.max_len
        st = self.enc.ids(serialize_state(state).replace(self.enc.mask_token, " "))
        n_state = len(st)
        for qid, qdef in questions.items():
            q = to_internal(qdef)
            seq, markers, r, _ = build_sequence(self.enc, state, q, self.max_len, self.head_max_len, st)
            room = min(room, r)
            if len(markers) != len(render_options(q)):
                raise ValueError("question %r options exceed head_max_len=%d" % (qid, self.head_max_len))
            items.append({"ids": seq, "markers": markers, "qtype": QTYPES[q["t"]]})
        info = {"state_tokens": n_state, "room": room, "truncated": n_state > room}
        return items, collate(items, self.enc.pad_id), info

    def temperature_for(self, qtype, k):
        return self.temperature_by_options.get(temp_bucket(qtype, k), self.temperature[qtype])

    def probs(self, logits, items, calibrated=True):
        out = []
        for r, it in enumerate(items):
            k = len(it["markers"])
            t = self.temperature_for(it["qtype"], k) if calibrated else 1.0
            out.append(softmax(np.asarray(logits[r, :k], dtype=np.float64) / t))
        return out

    def decode(self, questions, items, logits, act_logits):
        z = act_logits - act_logits.max(-1, keepdims=True)
        act = np.exp(z) / np.exp(z).sum(-1, keepdims=True)
        answers = {}
        for r, (qid, (p, qdef)) in enumerate(zip(questions, zip(self.probs(logits, items), questions.values()))):
            q = to_internal(qdef)
            k = len(p)
            conf = round(confidence_from_probs(p, k), 4)
            ext = {"act_probability": round(float(act[r, 0]), 4)}
            if q["t"] == "choice":
                keys = list(q["crit"].keys())
                answers[qid] = {"type": "choice", "choice": keys[int(p.argmax())],
                                "probabilities": {kk: round(float(v), 4) for kk, v in zip(keys, p)},
                                "confidence": conf, "action": ext}
            elif q["t"] == "score":
                answers[qid] = {"type": "score", "score": round(float((np.arange(k) * p).sum()), 4),
                                "legend": {str(i): c for i, c in enumerate(q["crit"])},
                                "probabilities": {str(i): round(float(v), 4) for i, v in enumerate(p)},
                                "confidence": conf, "action": ext}
            else:
                answers[qid] = {"type": "noul", "noul": round(float(p[1]), 4),
                                "confidence": round(max(float(p[1]), 1.0 - float(p[1])), 4), "action": ext}
        return answers

    def count_state_tokens(self, state):
        return len(self.enc.ids(serialize_state(state)))
