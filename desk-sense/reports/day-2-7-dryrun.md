## Days 2–7 — dry run on SYNTHETIC data (2026-09-23 → 2026-09-24)

**Gates (dummy data):** G1 [x] · G2 [x] 343 MB · G3 [x] · G4 [~] English pass, Hindi fail (ECE) · G5 [~] 1-hour soak PASS (0 crashes), long tickets too slow (p95 8 s)

Real tickets didn't exist yet, so every step ran on 1,200 generated tickets (`model/synthetic.py`).
Test phrasings are never in training. All numbers were measured in the 16 GB / 4-vCPU dev container,
2 worker threads. Evidence is in `reports/synthetic/`.

| Day | Plan step | Result |
|---|---|---|
| 2 | Labeler agreement (10% double-labeled) | 92–100% per question → "ok" (`day2_agreement.json`) |
| 2 | **G3** quick fine-tune, 200 tickets per language | **PASS**: en 96.7% vs 54.9% baseline; hi 95.1% vs 54.3% (`finetune_ckpt_g3.json`) |
| 3 | Splits 70/10/10/10, test locked | Grouped by phrasing, every variety × department in every split (`test_lock.json`) |
| 3 | Full fine-tune, 743 tickets | Validation en 98.4%, hi 97.1%; 43 min on CPU; first attempt OOM-killed, fixed (`finetune_full.log`) |
| 4 | `build_model`: trim → ONNX → int8 → calibrate | First attempt **FAILED** the gate (−28 pt, trim bugs, fixed). Final: every step within 2 points |
| 4 | Calibration, one temperature per question type | Temperatures 1.38 / 1.91 / 1.76; ECE on calib stays ≤ 0.03 |
| 5 | **G2** memory, worst page-cache case | **343.2 MB** whole app (38k vocabulary) · 328.6 MB (8.5k) · 398–502 MB (untrimmed) |
| 5 | Input cap | 512: p95 7.0 s · 256: p95 3.0 s (refuses ~7% of dummy tickets) |
| 5 | **G5** 60-minute soak | **PASS**: 60 min, **2,012 requests, all done, 0 restarts**, peak **344.7 MB** (vs 343.2 MB in a 200-request run: no growth), p50 1.06 s / p95 8.0 s |
| 5 | Out-of-vocabulary risk of trimming | English −5 pt (38k) / −10 pt (8.5k) on unfamiliar words (`out_of_corpus_compare.json`) |
| 7 | **G4** test split, run once | English 97.3% / ECE 0.024 **PASS**; Hindi 84.7% / ECE 0.117 **FAIL → disable** (`results.md`) |
| 7 | Known limits | `known-limits.md` |

**Bugs found and fixed along the way:**
- The fine-tune ran out of memory at 14 GB; fixed with token-budget micro-batches.
- Two corpus-trim bugs, caught by the build's own accuracy gate.
- A half-applied commit broke `measure_app`; it's fixed and tested.
- A wait loop matched its own command line and never exited.

**Decisions needed (unchanged, and more urgent now):**
- Real tickets. Above all, varied Hindi text: Hindi department routing is the weakest point.
- A 4 GB target machine (Windows private bytes).
- Long-ticket policy: a 256/384 input cap, or fewer questions per call.
