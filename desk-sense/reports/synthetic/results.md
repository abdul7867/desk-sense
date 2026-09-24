# Per-language results — Day 7 DRY RUN on SYNTHETIC data

> These numbers come from `model/synthetic.py` dummy tickets, not real users. They show the pipeline
> and the gates working end to end. They say nothing about real-world accuracy.
> Measured on 2026-09-24 in the 16 GB / 4-vCPU dev container.

Bundle: fine-tuned on 743 dummy tickets (2 epochs, CPU, 43 min) → vocabulary trimmed to the corpus
plus the top 100k common merges (38,317 tokens) → int8 weight-only → calibrated on the calib split.
The test split was read **once** (`test_runs.log`, sha256 in `test_lock.json`). Test phrasings are
never seen in training.

G4 thresholds (set on Day 1): accuracy ≥ 75%, ECE ≤ 0.10.

| Language | Test N (answers) | Accuracy | ECE | Before-calibration ECE | After-int8 Δ (val) | Status |
|---|---|---|---|---|---|---|
| English (en + Hinglish) | 475 (95 tickets) | **97.3%** | 0.024 | not measured (test read once) | −0.9 pt | **ship** |
| Hindi | 255 (51 tickets) | **84.7%** | **0.117** | not measured (test read once) | +0.4 pt | **disable** (ECE over 0.10, R4) |

By variety: English 98.6% (ECE 0.012) · Hinglish 96.1% (ECE 0.037) · Hindi 84.7% (ECE 0.117).

Hindi per question: department **43.1%** · needs_human 88.2% · urgency 92.2% · refund 100% · sentiment 100%.
English per question: department 99.0% · needs_human 93.7% · urgency 93.7% · refund 100% · sentiment 100%.

**What the Hindi failure tells us (without looking at the test errors, R5):** Hindi validation accuracy was
96–98%, so the model fits the phrasings it saw. Each department has only 5 training phrasings per
variety. The test phrasings are new ones, and Hindi department routing doesn't generalise from 5.
The fix is more varied Hindi training text (real tickets), not tuning on this test set.

## Memory and stability (G2 / G5) for this bundle

| Measure | Result |
|---|---|
| Whole-app peak, right after the build (worst case) | **343.2 MB** (worker 306.2 + supervisor/CLI 37.0) |
| Cold start | 0.79 s |
| Model latency, 200 requests (every 10th is a 512-token ticket) | p50 1.09 s · p95 7.9 s |
| 60-minute soak | 60 min, **2,012 requests, all done, 0 restarts**, peak **344.7 MB** (vs 343.2 MB in a 200-request run: no growth), p50 1.06 s / p95 8.0 s |
