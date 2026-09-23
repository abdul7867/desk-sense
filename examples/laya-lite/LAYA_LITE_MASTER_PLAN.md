# Laya Multilingual Lite — Master Plan (Week 1 Sprint)

> **Goal of this week:** a working prototype that proves a multilingual typed-decision model can run on a **4 GB RAM i3 / Ryzen** machine using **≤ 500 MB peak memory**, with **measured** accuracy in 1–2 languages.
>
> **Not the goal of this week:** a polished, production-ready product. That comes after the Day 7 decision.

---

## Table of contents

1. [Hard rules](#1-hard-rules)
2. [Background: what we are building on](#2-background-what-we-are-building-on)
3. [Scope for Week 1](#3-scope-for-week-1)
4. [Team and ownership](#4-team-and-ownership)
5. [Day 0 prep checklist](#5-day-0-prep-checklist)
6. [Day-by-day plan](#6-day-by-day-plan)
7. [Go/No-Go gates](#7-gono-go-gates)
8. [Model pipeline (fixed order)](#8-model-pipeline-fixed-order)
9. [App architecture](#9-app-architecture)
10. [Memory: how to measure and control it](#10-memory-how-to-measure-and-control-it)
11. [Testing and acceptance](#11-testing-and-acceptance)
12. [Mistakes to avoid](#12-mistakes-to-avoid)
13. [Risk register](#13-risk-register)
14. [Templates](#14-templates)
15. [Week 2+ backlog](#15-week-2-backlog)
16. [References](#16-references)

---

## 1. Hard rules

These are non-negotiable. If a decision breaks one of these, it is the wrong decision.

| # | Rule | How we check it |
|---|---|---|
| R1 | Peak **private memory** of the whole app ≤ **500 MB** (target ~350 MB) | Automated memory test (Section 10) |
| R2 | Fixed language list. Unsupported input is **refused**, never guessed | Language guard + test cases |
| R3 | Works **offline** after setup | Run test with network disabled |
| R4 | A language that fails its quality gate is **disabled**, not shipped | Final gate (Section 11) |
| R5 | The **test set is never used** for training or tuning | Test set stored separately, one owner |
| R6 | Pipeline order is fixed: fine-tune → trim → ONNX → int8 → **calibrate last** | One script, no manual steps |
| R7 | Local server binds to `127.0.0.1` only, never `0.0.0.0` | Code review |
| R8 | No request is lost on crash | Kill-worker test |

**Memory metric definition (R1):**
- Windows: **peak private bytes** (`psutil` → `memory_info().peak_pagefile`)
- Linux: **peak RSS** (`resource.getrusage(...).ru_maxrss`)
- Measured for supervisor + worker + UI **combined**.

---

## 2. Background: what we are building on

**Base model:** Laya by Convai Innovations (Apache 2.0).
- GitHub: https://github.com/NandhaKishorM/laya
- Hugging Face hub: https://huggingface.co/convaiinnovations/laya
- Checkpoint we use: `convaiinnovations/laya-multilingual`

**What it does:** takes a *state* (text, email, ticket, or JSON) plus *typed questions*, and returns typed answers with probabilities in **one forward pass**. It does not generate text.

| Question type | Returns |
|---|---|
| `choice` | selected option + probability per option + confidence |
| `score` | expected level on an ordinal scale + distribution |
| `noul` | probability that the statement is true |

**Checkpoint facts (from the model card):**

| | `laya-multilingual` |
|---|---|
| Encoder | mmBERT-base |
| Parameters | ~322M |
| Context | 1024 tokens |
| Languages | 100+ |
| Speed (Tesla T4 GPU, 1 question) | ~33 ms |

**Known limits we must respect (from the model card):**
- Near chance on typed decisions **zero-shot**. It must be fine-tuned.
- Multilingual quality is uneven. On a 51-language intent test it cleared 3× random on only 23 languages.
- Confidence gives **no warning** on unreadable input (Khmer: 0% accuracy at 95% confidence). → We need a language guard.
- Keep `choice` questions under ~20 options.
- Ships over-confident → must calibrate on our own data.
- If `laya.load()` hangs, run with `USE_TF=0`.
- The project is very new (many releases in a single day in Sept 2026). → **Pin versions and fork.**

**Quick sanity check (Day 1 morning):**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install laya
```

```python
import os
os.environ["USE_TF"] = "0"
import laya

agent = laya.load("convaiinnovations/laya-multilingual")
result = agent.predict(
    {"body": "मुझसे दो बार शुल्क लिया गया, कृपया रिफंड करें"},
    {
        "department": {
            "type": "choice",
            "instructions": "Which team should handle this?",
            "criteria": {
                "billing": "invoices, payments, refunds",
                "technical": "bugs and outages",
                "sales": "pricing",
            },
        },
        "urgency": {
            "type": "score",
            "instructions": "How urgent is this?",
            "criteria": ["not urgent", "soon", "blocking"],
        },
    },
)
print(result["answers"])
```

---

## 3. Scope for Week 1

| ✅ In scope | ❌ Out of scope (Week 2+) |
|---|---|
| 1–2 languages: **[Hindi, English incl. Hinglish]** ← edit | More languages |
| 1 use case, 3–5 questions | Extra use cases |
| Day 1 go/no-go gates | Custom Hinglish detector |
| Correct pipeline order | Per-language × per-option-count calibration |
| Worker process + SQLite + retry | Installer / packaging |
| Memory test on a real 4 GB machine | Polished UI |
| Vocab trimming **only if** over budget | Monthly retraining automation |
| Simple memory watchdog | OS-level Job Object / cgroup cap |

**Our use case (filled 2026-09-23; source of truth: `schema.json`):**

> Use case: `Support-ticket triage: route, rate urgency, flag refunds, mood, and tickets needing a person`
>
> Languages: `Hindi (Devanagari) · English incl. Hinglish (Latin; not separable by script, M7)`

**Question schema (lock on Day 1, max 20 options each):**

| ID | Type | Instruction | Options / scale |
|---|---|---|---|
| q1 `department` | choice | Which team should handle this ticket? | billing · technical · account · sales · other |
| q2 `urgency` | score | How urgent is this ticket? | not urgent · soon · blocking work |
| q3 `refund_requested` | noul | The customer is asking for money back. | true / false |
| q4 `sentiment` | choice | What is the customer's mood? | angry · neutral · happy |
| q5 `needs_human` | noul | A person must reply; an automatic reply is not enough. | true / false |

---

## 4. Team and ownership

| Role | Owner | Responsibilities |
|---|---|---|
| ML dev | `____` | ONNX conversion, fine-tuning, quantization, calibration, model tests |
| App dev | `____` | Supervisor, worker, SQLite, language guard, UI, memory watchdog |
| Data lead | `____` | Schema, labeling guide, labeling, splits, **test set owner** |
| Labelers (1–2) | `____` | Labeling, agreement checks |
| Sprint lead | `____` | Daily sync, decisions, scope control, decision log |

> **Solo?** Drop to **one language**, skip the UI (use a CLI), and expect only a demo by Day 7.

**Daily sync:** 15 minutes, same time every day. Agenda: done, blocked, today. Nothing else.

---

## 5. Day 0 prep checklist

Do these **before** Day 1 so no time is wasted.

- [ ] Target test machine available: 4 GB RAM, i3 / Ryzen, ideally with an HDD
- [ ] Record machine specs: CPU model, RAM, disk type (HDD/SSD), OS version
- [ ] Kaggle account with GPU access verified
- [ ] Git repo created with this file at the root
- [ ] Fork `NandhaKishorM/laya`; note the exact version/commit used
- [ ] Download model files once; store checksums (`sha256sum`)
- [ ] Collect **raw real user text** for the use case (target 800+ samples across languages)
- [ ] If using AI pre-labeling: confirm the data has **no private user info**, or use only local tools
- [ ] Agree on the question schema draft (Section 3)
- [ ] Everyone has read Section 12 (Mistakes to avoid)

**Repo layout:**

```
laya-lite/
├── LAYA_LITE_MASTER_PLAN.md    ← this file
├── DECISIONS.md                ← decision log (Section 14)
├── data/
│   ├── raw/
│   ├── labeled/
│   └── splits/                 ← train / val / calib / test (test = locked)
├── model/
│   ├── finetune/               ← Kaggle notebook + configs
│   ├── export/                 ← ONNX export + verification
│   ├── quantize/
│   ├── calibrate/
│   └── build_model.py          ← runs the whole pipeline in order
├── app/
│   ├── supervisor.py
│   ├── worker.py
│   ├── guard.py
│   ├── store.py                ← SQLite
│   └── ui.py
├── tests/
│   ├── test_memory.py
│   ├── test_crash_retry.py
│   ├── test_guard.py
│   └── test_accuracy.py
└── reports/                    ← daily metrics, gate results
```

---
## 6. Day-by-day plan

Legend: **ML** = ML dev · **APP** = App dev · **DATA** = Data lead + labelers · **ALL** = everyone

### Day 1 — Go/No-Go

**ML**
- [ ] Run the sanity check (Section 2) on the 4 GB machine
- [ ] **Gate G1:** export to ONNX, run verification script (Section 8.3)
- [ ] **Gate G2:** quantize to int8, measure peak memory (Section 10)

**DATA**
- [ ] Lock the question schema
- [ ] Write the labeling guide (1 page: definitions + 2 examples per option)
- [ ] Start labeling

**APP**
- [ ] Supervisor + worker skeleton using a **fake model** that returns random probabilities
- [ ] SQLite schema (Section 9.3)

**End of day decision (sprint lead):**
- [ ] G1 pass → continue
- [ ] G1 fail → choose: hand-write decision head (+2 days, cut Day 6 user test) **or** switch to English checkpoint
- [ ] G2 result recorded; decide whether vocab trimming is needed on Day 5
- [ ] Log decisions in `DECISIONS.md`

### Day 2 — Data + learnability

**DATA**
- [ ] Label 300–500 examples total
- [ ] 10% of examples labeled by **two people**; compute agreement
- [ ] If agreement < 80%: fix the guide before labeling more

**ML**
- [ ] **Gate G3:** quick fine-tune with first ~200 examples per language
- [ ] Compare against the "most common answer" baseline

**APP**
- [ ] Request logging to SQLite **before** processing
- [ ] Crash-retry: supervisor restarts worker and replays unfinished requests

**End of day decision:**
- [ ] G3 pass → continue
- [ ] G3 fail for a language → drop that language, log it

### Day 3 — Real fine-tune

**ML**
- [ ] Full fine-tune on Kaggle with all labeled training data
- [ ] Track validation accuracy per language

**DATA**
- [ ] Finish splits per language: train 70% / val 10% / calib 10% / **test 10% (locked)**
- [ ] Hand test set to its owner; nobody else opens it

**APP**
- [ ] Language guard: script detection (Section 9.4)
- [ ] Token counting + visible "too long" warning (no silent cut-off)

### Day 4 — Build the shippable model file

**ML**
- [ ] Run `build_model.py`: ONNX → int8 → calibrate (one temperature per question type)
- [ ] Compare accuracy after **each** step; stop if any language drops > 2 points
- [ ] Record results in `reports/`

**APP**
- [ ] Replace fake model with real ONNX model in the worker
- [ ] Confidence zones per question: act / confirm / flag (Section 9.5)
- [ ] Minimal UI (Tkinter) or CLI

### Day 5 — Real hardware integration

**ALL**
- [ ] Run on the 4 GB machine **with a browser and an office app open**
- [ ] Measure: peak memory, response time (p50 / p95), cold start from disk
- [ ] Run `test_memory.py`, `test_crash_retry.py`, `test_guard.py`
- [ ] If peak memory > 500 MB → do vocab trimming now (Section 8.4), then re-run Day 4 steps
- [ ] If cold start > 5 s → add "keep model loaded" option

### Day 6 — Real users

**ALL**
- [ ] 3–5 people use it on real tasks for at least 30 minutes each
- [ ] Log every wrong answer, confusing moment, and crash
- [ ] Fix **critical bugs only**; everything else goes to the Week 2 backlog

### Day 7 — Buffer + decision

**ALL**
- [ ] Fix leftovers
- [ ] Run the final test set **once**, record results per language
- [ ] Write the "Known limits" list
- [ ] Demo
- [ ] Decision: **Go / Adjust / Stop** for the next phase, logged in `DECISIONS.md`

---

## 7. Go/No-Go gates

| Gate | Day | Pass criteria | If it fails |
|---|---|---|---|
| **G1 ONNX conversion** | 1 | On 200 varied requests (different numbers of questions and options), ONNX output matches the original within **0.01** max probability difference | Encoder-only ONNX + hand-written head, or English checkpoint |
| **G2 Memory** | 1 | int8 peak measured; projected whole-app peak ≤ 500 MB (with trimming if needed) | 4-bit weights, or smaller dedicated classifier |
| **G3 Learnability** | 2 | ~200 examples per language beats majority baseline by **≥ 10 points** on validation | Drop that language |
| **G4 Final quality** | 7 | Per language: accuracy ≥ **75%** (set Day 1, 2026-09-23), ECE ≤ **0.10** | Disable that language |
| **G5 Hardware** | 5 | Peak ≤ 500 MB, p95 response ≤ **2.0 s** (set Day 1, 2026-09-23), no crashes in 1 hour | Trim vocab, reduce threads, shorten inputs |

> **Set G4 and G5 numbers on Day 1**, before seeing any results. Choosing thresholds after seeing results is cheating yourself.

---

## 8. Model pipeline (fixed order)

```
Fine-tune → Trim vocabulary (only if needed) → Export ONNX → int8 → Calibrate → Final test
```

**Why this order:** trimming and quantizing change the model's outputs. Calibrating before them makes the calibration wrong. Calibration always happens **last**, on the exact file we ship.

### 8.1 Fine-tune (Kaggle GPU)

- Start from the author's fine-tuning notebook in the Laya repo (`notebooks/`).
- It was written for the English checkpoint → point it at `convaiinnovations/laya-multilingual` and expect small fixes.
- Save: final weights, config, training log, exact library versions.

### 8.2 Export to ONNX

- Export the full model if possible.
- Mark sequence length and batch as **dynamic axes**.
- Watch for the decision head being frozen to one fixed number of questions/options. That is the main failure mode.

### 8.3 Verify the export (Gate G1)

Template to adapt. The key idea: same inputs, compare probabilities.

```python
# model/export/verify_onnx.py  (template — adapt to the real export)
import json, numpy as np

def verify(original_predict, onnx_predict, cases, tol=0.01):
    worst = 0.0
    failures = []
    for case in cases:  # 200 varied cases: 1–5 questions, 2–20 options
        a = original_predict(case["state"], case["questions"])
        b = onnx_predict(case["state"], case["questions"])
        for qid in case["questions"]:
            pa = np.array(a[qid]["probs"])
            pb = np.array(b[qid]["probs"])
            diff = float(np.max(np.abs(pa - pb)))
            worst = max(worst, diff)
            if diff > tol:
                failures.append({"case": case["id"], "q": qid, "diff": diff})
    print(f"Worst diff: {worst:.4f} | failures: {len(failures)}")
    json.dump(failures, open("reports/g1_failures.json", "w"), indent=2)
    return len(failures) == 0
```

### 8.4 Trim vocabulary (only if over memory budget)

- Keep tokens that appear in **our real text**, plus:
  - all digits and punctuation
  - every single character of our target scripts (e.g., all Devanagari characters)
  - special tokens (`[CLS]`, `[SEP]`, `[MASK]`, `[PAD]`, `[UNK]`)
- **Rebuild the tokenizer** so unfamiliar words split into smaller kept pieces. Do not just delete rows and map to `[UNK]`.
- Re-map the embedding matrix to the new token IDs.
- Re-test accuracy per language. Names, product codes, and Hinglish are the first things to check.

### 8.5 Quantize to int8

```python
from onnxruntime.quantization import quantize_dynamic, QuantType

quantize_dynamic(
    model_input="model/export/laya_ml.onnx",
    model_output="model/quantize/laya_ml_int8.onnx",
    weight_type=QuantType.QInt8,
)
```

Re-test accuracy **per language**. Weaker languages may drop more than English.

### 8.6 Calibrate (last)

- Use the **calibration split** only (never the test split).
- Week 1: fit **one temperature per question type** (`choice`, `score`, `noul`).
- Week 2+: per option count and per language, once there is enough data.
- Report ECE before and after.

### 8.7 One script

`model/build_model.py` runs 8.4 → 8.6 in order, writes a report to `reports/`, and fails loudly if any step drops accuracy by more than 2 points.

---
## 9. App architecture

```
┌──────────────┐     ┌────────────────────┐     ┌─────────────────────┐
│  UI / CLI    │ ⇄   │  Supervisor        │ ⇄   │  Model worker       │
│  (~20–30 MB) │     │  (~30 MB)          │     │  (~250–320 MB)      │
└──────────────┘     │  - queue + retry   │     │  - ONNX Runtime     │
                     │  - memory watchdog │     │  - tokenizer        │
                     │  - idle shutdown   │     │  - int8 model       │
                     └─────────┬──────────┘     └─────────────────────┘
                               │
                     ┌─────────▼──────────┐
                     │  SQLite            │
                     │  requests, results │
                     │  corrections       │
                     └────────────────────┘
```

### 9.1 Why a separate worker process

When Python frees a model inside the same process, the OS often does **not** get the memory back. Killing the worker process always returns it.

### 9.2 Supervisor responsibilities

- Save every request to SQLite **before** sending it to the worker
- Start the worker on demand; stop it after **[5] minutes** idle
- **Memory watchdog:** check worker memory every 1 s; if > **450 MB**, stop it cleanly and restart
- If the worker crashes, restart it and replay unfinished requests
- Serve on `127.0.0.1` only

### 9.3 SQLite schema

```sql
CREATE TABLE requests (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL,
    state_json  TEXT NOT NULL,
    questions   TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending','done','failed','refused')),
    attempts    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE results (
    request_id  INTEGER REFERENCES requests(id),
    answers     TEXT NOT NULL,   -- JSON with choice/probs/confidence
    language    TEXT,
    zone        TEXT CHECK (zone IN ('act','confirm','flag')),
    latency_ms  INTEGER
);

CREATE TABLE corrections (
    request_id  INTEGER REFERENCES requests(id),
    question_id TEXT NOT NULL,
    model_value TEXT,
    user_value  TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
```

### 9.4 Language guard

- Week 1: **script detection** (Laya includes `laya.lang` for this).
  - Target scripts (e.g., Devanagari, Latin) → allowed
  - Anything else → **refused** with a clear message
- Known gap: Latin script cannot tell English from Hinglish. Both are in the training data, so both are allowed in Week 1.
- Week 2+: tiny letter-pattern classifier trained on our own data to separate English vs Hinglish.

### 9.5 Confidence zones

| Zone | Rule (tune on validation data) | Action |
|---|---|---|
| **Act** | confidence ≥ **[0.85]** | Apply automatically |
| **Confirm** | **[0.60]** ≤ confidence < **[0.85]** | Show answer, ask user to confirm |
| **Flag** | confidence < **[0.60]** | Send for human review |

### 9.6 Input length

- Count tokens **before** sending to the model.
- Hindi/Tamil use more tokens per word than English, so the same length of text costs more.
- If over the cap (512 in Week 1): show a warning and either split or ask the user to shorten. **Never cut silently.**

---

## 10. Memory: how to measure and control it

### 10.1 ONNX Runtime settings (worker)

```python
import onnxruntime as ort

opts = ort.SessionOptions()
opts.enable_cpu_mem_arena = False      # don't pre-grab extra RAM
opts.enable_mem_pattern = False        # don't reserve memory for patterns
opts.intra_op_num_threads = 2          # i3 / low-end Ryzen
opts.inter_op_num_threads = 1
opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

session = ort.InferenceSession(
    "model/quantize/laya_ml_int8.onnx",
    sess_options=opts,
    providers=["CPUExecutionProvider"],
)
```

**Runtime dependencies (worker):** `onnxruntime`, `tokenizers`, `numpy`. **No** `torch`, **no** `transformers`.

### 10.2 Measuring peak memory

```python
# tests/test_memory.py (core idea)
import psutil, sys

def peak_mb(pid):
    p = psutil.Process(pid)
    mi = p.memory_info()
    if sys.platform == "win32":
        return mi.peak_pagefile / 1e6     # peak private bytes
    import resource
    # Linux: only valid for the current process; for a child, use its own reporting
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3

LIMIT_MB = 500
# 1. start supervisor + worker + UI
# 2. run 200 realistic requests incl. longest allowed inputs
# 3. sum peak_mb() for all processes
# 4. assert total <= LIMIT_MB
```

### 10.3 Memory budget (estimates — replace with measured values)

| Part | Estimate | Measured (Day 5) |
|---|---|---|
| Python + ONNX Runtime | 60–80 MB | |
| Model (int8, trimmed vocab) | 150–180 MB | |
| Model (int8, **no** trimming) | ~330 MB | |
| Working memory (512 tokens) | 30–60 MB | |
| Tokenizer + guard | 15–25 MB | |
| Supervisor + UI | 30–50 MB | |
| **Total** | **~285–395 MB** | |

---

## 11. Testing and acceptance

| Test | What it checks | Pass |
|---|---|---|
| `test_memory.py` | Whole-app peak memory | ≤ 500 MB |
| `test_crash_retry.py` | Kill worker mid-request | Request completes after restart, nothing lost |
| `test_guard.py` | Unsupported scripts, empty input, over-long input | Refused / warned correctly |
| `test_accuracy.py` | Per-language accuracy + ECE on **test split** | Meets G4 (run on Day 7 only) |
| Offline test | Network disabled | Everything works |
| Cold start | Model load from HDD | ≤ 5 s, or "keep loaded" option exists |
| Background load | Browser + office app open | Still meets memory and speed targets |

**Definition of done for Week 1:**
- [ ] Runs on a real 4 GB i3/Ryzen machine at ≤ 500 MB peak
- [ ] 1–2 languages with **measured** accuracy on the untouched test set
- [ ] No lost requests on crash
- [ ] Honest "Known limits" list written

---

## 12. Mistakes to avoid

These were real mistakes found during planning. Do not repeat them.

| # | Mistake | Correct approach |
|---|---|---|
| M1 | Calibrating before quantizing/trimming | Calibrate **last**, on the shipped file |
| M2 | Treating ONNX conversion as a minor risk | It's **Gate G1 on Day 1** |
| M3 | Assuming multilingual fine-tuning will work | Prove it with **Gate G3** on Day 2 |
| M4 | Depending on a days-old project unpinned | Pin versions, fork, store checksums |
| M5 | Unloading the model inside the same process | Separate worker process, kill it |
| M6 | Deleting vocab rows and mapping to `[UNK]` | Rebuild tokenizer with fallback pieces |
| M7 | Expecting script detection to find Hinglish | It can't; plan for it explicitly |
| M8 | Assuming 512 tokens = same text length in every language | Measure per language, warn visibly |
| M9 | "RAM usage" with no definition | Peak private bytes (Win) / peak RSS (Linux) |
| M10 | Browser UI on a 4 GB machine | Lightweight native UI or CLI |
| M11 | Guessing data sizes | Measure with a learning curve (100 / 300 / 1000) |
| M12 | Trusting estimates as facts | Every number gets a "measured" column |
| M13 | Hard memory cap that kills mid-request | Watchdog below the cap + retry from SQLite |
| M14 | Binding server to `0.0.0.0` | `127.0.0.1` only |
| M15 | Setting thresholds after seeing results | Set G4/G5 on Day 1 |

---

## 13. Risk register

| Risk | Likelihood | Impact | Early warning | Response |
|---|---|---|---|---|
| ONNX conversion fails | Medium | High | G1, Day 1 | Hand-written head, or English checkpoint |
| Multilingual won't learn | Medium | High | G3, Day 2 | Fewer languages |
| Labeling slow / low quality | High | High | Agreement < 80% on Day 2 | Simplify questions, add labelers, AI pre-label + human review |
| Memory over budget | Medium | High | G2, Day 1 | Vocab trim, then 4-bit |
| Too slow on i3 | Medium | Medium | Day 5 timing | Shorter inputs, fewer questions per call, keep loaded |
| Upstream breaks | Medium | Medium | Pinned fork | No action needed |
| Scope creep | High | Medium | New ideas in sync | Week 2 backlog |

---

## 14. Templates

### 14.1 Daily sync (copy into `reports/day-N.md`)

```markdown
## Day N — YYYY-MM-DD

**Gates:** G1 [ ] G2 [ ] G3 [ ] G4 [ ] G5 [ ]

| Person | Done yesterday | Today | Blocked? |
|---|---|---|---|
| ML | | | |
| APP | | | |
| DATA | | | |

**Numbers today:** peak MB ___ | p95 latency ___ s | val accuracy ___ | labeled count ___

**Decisions needed:**
```

### 14.2 Decision log (`DECISIONS.md`)

```markdown
| Date | Decision | Why | Alternatives considered | Owner |
|---|---|---|---|---|
| | | | | |
```

### 14.3 Per-language results (`reports/results.md`)

```markdown
| Language | Test N | Accuracy | ECE | Before calib ECE | After int8 Δ | Status |
|---|---|---|---|---|---|---|
| Hindi | | | | | | ship / disable |
| English | | | | | | ship / disable |
```

### 14.4 Known limits (Day 7)

```markdown
## Known limits — Week 1 prototype
- Languages supported:
- Max input length:
- Peak memory measured:
- Known wrong-answer patterns:
- Not yet built:
```

---

## 15. Week 2+ backlog

- [ ] More languages (repeat G3 per language)
- [ ] English vs Hinglish classifier
- [ ] Calibration per language and per option count
- [ ] OS-level memory cap (Windows Job Object / Linux cgroup)
- [ ] Installer (e.g., PyInstaller)
- [ ] Monthly retraining from logged corrections (full pipeline + all gates)
- [ ] Rust/C++ runtime if Python overhead matters
- [ ] 4-bit weights experiment
- [ ] Better UI

---

## 16. References

- Laya model card (hub): https://huggingface.co/convaiinnovations/laya
- Laya GitHub: https://github.com/NandhaKishorM/laya
- Laya PyPI: https://pypi.org/project/laya/
- Laya demo: https://huggingface.co/spaces/convaiinnovations/laya-demo
- ONNX Runtime quantization docs: https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html
- psutil docs: https://psutil.readthedocs.io/

> **Reminder:** every estimate in this file is a starting guess. Replace it with a measured number as soon as you have one.
