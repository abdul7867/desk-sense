---
name: codebase-overview
description: The architecture map of desk-sense — what it does, how it is laid out, where things live, and the conventions that are not obvious from any single file. Use whenever you need to orient in this codebase, before exploring or searching for where something belongs.
---

# Codebase overview

## What this project is

An offline ticket-triage app: a ticket (Hindi, English or Hinglish) goes in, five typed answers come
out (department, urgency, refund?, sentiment, needs a human?) with calibrated probabilities and a
confidence zone. The model is Laya multilingual (mmBERT + a typed decision head), exported to ONNX
and int8-quantized so it runs in ≤ 500 MB on a 4 GB machine without torch.

## Stack

- Python 3.11. Runtime: onnxruntime, tokenizers, numpy, psutil. Build: laya 0.3.6, torch, onnx.
- SQLite (WAL) for requests/results/corrections. pytest. No web UI: CLI + a 127.0.0.1 JSON API.

## Layout

```
schema.json          # the use case: questions, allowed scripts, zones, gate thresholds (one source)
app/                 # RUNTIME. Must never import torch/transformers.
  runtime.py         # numpy port of laya's sequence building + decoding (G1 checks it token-for-token)
  ort_model.py       # ONNX session + batching by token budget
  worker.py          # separate process, JSON lines on stdin/stdout; --fake for tests
  supervisor.py      # queue, SQLite-first, crash replay, memory watchdog, idle stop, HTTP on 127.0.0.1
  guard.py zones.py store.py cli.py
model/               # BUILD. torch allowed.
  pin.py             # pinned HF revision + sha256 + paths (env overrides for smoke runs)
  trim/ export/ quantize/ calibrate/ finetune/   # pipeline steps, each runnable alone
  build_model.py     # runs them in the fixed order and fails loudly
  data.py evaluate.py
browser/             # AGENT (supervisor process): controller loop, rank shortlist, fastpath, safety,
                     #   question (one Choice per step), steplog (training data), serve.py (entry point)
thinker/             # planners behind one interface: Claude (Haiku default, lazy SDK import), scripted fake
extension/           # Chrome MV3: content.js element table, background.js loop + chrome.debugger input, side panel
bench/               # offline agent benchmark: pages/, tasks.jsonl, run.mjs (Playwright + real extension)
app/systemone.py     # Jev/Laya /v1/systemone wire format, validated
model/browser/       # browser training: convert_mind2web (steps -> runtime questions), split_browser (by site),
                     #   evaluate_browser (gate B3). Use LAYA_DATA_DIR=data/browser, LAYA_MODEL_OUT=model/browser-run
tests/               # fake-worker tests + measure_app.py (the G2/G5 measurement); tests/agent/ for the agent
reports/             # measured gate results; DECISIONS.md explains the choices
```

## Where things go

| I need to add... | It goes in... |
|---|---|
| a question or option | `schema.json` (then re-label; the test split is locked) |
| a language | `schema.json` allowed_scripts + `app/guard.py` SCRIPTS, then G3 for it |
| anything the worker imports | `app/`, torch-free; check `worker_imports_torch` in measure_app |
| a model-pipeline step | `model/<step>/`, wired into `model/build_model.py` in plan §8 order |
| a gate threshold change | `schema.json` gates + a `DECISIONS.md` row |

## Data flow

1. `Supervisor.submit` writes the request to SQLite (`pending`) before anything else.
2. `guard.check` refuses empty/unsupported-script input (stored as `refused`, worker never sees it).
3. The worker tokenizes once, refuses if the ticket does not fit (`too_long`, never truncated
   silently), runs questions in token-budget batches, returns answers.
4. If the worker dies or the watchdog kills it, the supervisor restarts it and replays the request
   (up to `max_attempts`). `replay_pending()` finishes requests a crashed supervisor left behind.
5. `zones.assign` marks each answer act/confirm/flag by top calibrated probability; stored as `done`.

## Conventions that are not obvious

- Weights ship as external data (`model.onnx` + `model.data`) so ORT memory-maps them. Inline
  weights double the load peak.
- ORT arena is ON and batches are capped at 512 tokens. Both measured, both against plan §10.1's
  suggestions (DECISIONS.md). Do not "fix" them back without re-measuring.
- The watchdog reads anonymous/private memory, not RSS: mapped weight pages are reclaimable.
- `quantize_dynamic` breaks this model (activation outliers in mlp.Wo). Weight-only int8 is the default.
- Vocabulary trim stage A (script) is lossless and always on. Stage B needs a real-text corpus; a
  merge-rank cap looked fine on memory and destroyed accuracy.
- Zone confidence is the top calibrated probability, not laya's entropy `confidence`.

## Browser agent data flow

1. The extension reads the page (numbered element table) and posts it to `/v1/agent/start|step`.
2. `browser/controller.py`: allowlist → `fastpath` (no model) → `rank.shortlist` (top 12) → one
   `Supervisor.decide` call (no SQLite-first, no replay, `strict` options) → thinker only on flag,
   two failures, unreadable labels or text to write → `safety.risky` on every action.
3. The extension performs the action with `chrome.debugger` input, reports `{ok, changed}`, repeats.
   Risky actions come back with `confirm` and wait for the person.

## Known rough edges

- Long tickets (512 tokens × 5 questions) take ~7 s on 2 threads here: Laya re-reads the ticket per question.
- G2 is over by a hair with stage A only; stage B (real corpus) is the plan's fix.
- Fine-tune script is our own (upstream notebook unreachable); smoke-tested on CPU only.
