# desk-sense — the app

Offline support-ticket triage in Hindi, English and Hinglish, on the
[Laya](https://huggingface.co/convaiinnovations/laya) multilingual decision model, built to fit a
4 GB i3/Ryzen machine in ≤ 500 MB. A ticket goes in; five typed answers come out, each with a
calibrated probability and a zone: **act**, **confirm** or **flag** for a human.

Built in the Week-1 sprint planned in [`LAYA_LITE_MASTER_PLAN.md`](LAYA_LITE_MASTER_PLAN.md) (Day 1 on the real
base model, Days 2–7 as a dry run on dummy data), with the [Tokensaver](../docs/TOKENSAVER.md) setup.
The repository front page is [`../README.md`](../README.md).

```
$ python -m app.cli ask "मुझसे दो बार शुल्क लिया गया, कृपया रिफंड करें"
#1  language=hi  FLAG    (human review)  787ms
  department        billing                                  p=0.41  flag
  urgency           blocking work (level 2, expected 1.90)   p=0.91  act
  refund_requested  yes                                      p=0.96  act
  sentiment         neutral                                  p=0.74  confirm
  needs_human       yes                                      p=0.97  act
```

That's the **base model, not fine-tuned yet**. The 0.41 on `department` is the plan's zero-shot
warning, and the zone logic correctly sends the ticket to a human.

## Where it stands

All numbers were measured in a 16 GB / 4-vCPU Linux dev container, **not** the target machine.
Details: [`reports/day-1.md`](reports/day-1.md). Reasons: [`DECISIONS.md`](DECISIONS.md).

| Gate | Result |
|---|---|
| **G1** ONNX matches original | **PASS**: worst Δp 0.000052 over 609 questions (limit 0.01) |
| **G2** peak ≤ 500 MB | **FAIL by 2 MB** at worst: 398 MB typically, 502 MB when the weights file is freshly written. A stage B vocab trim (37k tokens) measured 362 MB. Needs real ticket text |
| **G3** learnability | Not run: no labeled data yet. Script ready and smoke-tested |
| **G4** final quality | Day 7 |
| **G5** hardware | Early reading: p50 0.83 s; p95 6.9 s because 512-token tickets are encoded once per question |
| R2 language guard | Hindi/Latin allowed; Khmer, Arabic, Chinese, Cyrillic, Tamil refused; empty refused |
| R3 offline | **PASS**: real model answered inside a network namespace with no network |
| R7 127.0.0.1 only | **PASS** (tested) |
| R8 no lost requests | **PASS**: worker killed mid-request, crash loops, watchdog kills and supervisor restarts all tested |

### Days 2–7 dry run on dummy data

Real tickets aren't in yet, so the whole plan was run on 1,200 generated Hindi, English and Hinglish
tickets ([`reports/day-2-7-dryrun.md`](reports/day-2-7-dryrun.md)). It proves the pipeline and gates work.
It does **not** show real-world accuracy.

| Gate | Dummy-data result |
|---|---|
| G3 learnability | **PASS**: en 96.7% / hi 95.1% vs ~54% baseline |
| G2 memory, fine-tuned + 38k-token vocabulary | **PASS**: 343 MB whole app, worst case |
| G4 on the locked test split (run once) | English **97.3%** (ECE 0.024) PASS · Hindi 84.7% but ECE **0.117** FAIL → disabled |
| G5 | 1-hour soak **PASS**: 2,012 requests, 0 crashes, 344.7 MB flat · long tickets still ~8 s p95 (fails 2 s) |

The weakest point is Hindi department routing on phrasings the model hasn't seen (43%). The fix is
real, varied Hindi tickets.

## Run it

```bash
# Build machine (torch, CPU wheel is enough):
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0
pip install -r requirements-build.txt
python -m model.build_model            # ~7 min: trim -> ONNX (+G1) -> int8 -> calibrate -> model/dist

# Target machine (no torch; copy model/dist over):
pip install -r requirements-runtime.txt
python -m app.cli ask "bhai mera payment do baar kat gaya"
python -m app.cli shell                # one ticket per line, model stays loaded
python -m app.cli correct 12 department billing
python -m app.supervisor --port 8765   # POST /predict {"state": ...} on 127.0.0.1

python -m pytest -q                    # 38 tests on a fake worker; memory tests run when model/dist exists
python -m tests.measure_app --n 200    # G2/G5: whole-app peak memory + latency -> reports/g2_memory.json
```

Add `--fake` to the CLI or supervisor to run without the model.

## How it works

```
CLI / HTTP (127.0.0.1) ─► Supervisor ─────────────► Worker process (ONNX Runtime, no torch)
                          │ SQLite first (R8)       │ tokenizer (trimmed) + int8 weights (memory-mapped)
                          │ language guard (R2)     │ refuses tickets that do not fit, never truncates
                          │ watchdog 450 MB private │ questions batched ≤ 512 tokens
                          │ crash → restart+replay  │
                          └ zones act/confirm/flag  └ malloc_trim after each request
```

Model pipeline, fixed order (plan R6), one command (`model/build_model.py`):

```
[fine-tune on Kaggle] → trim vocab → export ONNX → G1 → int8 → per-step accuracy check → calibrate → model/dist
```

## Changes to the plan, and why

Each is measured, and each has a row in `DECISIONS.md`.

- **int8 is weight-only, not `quantize_dynamic`.** Dynamic int8 kept only 72% of answers the same as
  fp32, because of activation outliers in ModernBERT's MLP. Weight-only block-32 int8 keeps 100% of decisive answers.
- **ORT arena on, not off** (§10.1): a 512-token ticket peaks at 416 MB with it and 561 MB without.
- **Weights as external data:** ORT memory-maps them, so the model load dropped from +580 MB to +10 MB.
- **The watchdog reads private memory, not RSS.** Mapped weight pages are reclaimable, and an RSS watchdog would
  kill a healthy worker.
- **Stage A vocab trim is always on** (lossless for accepted scripts). **Stage B must use real text**: a
  corpus-free cap got memory to 362 MB but kept only 60% of decisive answers.

## Next (plan Days 2–7)

1. Collect 800+ real tickets and label them with [`docs/labeling-guide.md`](docs/labeling-guide.md).
   Then `python -m model.data split` (locks the test split) and `agreement` on the 10% double-labeled.
2. G3 on Kaggle: `python -m model.finetune.finetune --per-language 200 --out ckpt_g3`.
3. Full fine-tune, then `python -m model.build_model --checkpoint ckpt --corpus data/raw/tickets.txt`.
4. Day 5 on the 4 GB machine: `tests.measure_app`, then decide the input cap for G5.
5. Day 7: `pytest -m day7 --run-day7`, once.

## Layout

`app/` runtime (no torch) · `model/` build pipeline · `tests/` · `reports/` measured results ·
`schema.json` the use case · `data/` gitignored (real text never goes in git) · model binaries gitignored,
rebuilt from the pinned checkpoint (`model/pin.py`).
