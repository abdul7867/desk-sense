## Known limits — Week 1 prototype (dry run on synthetic data, 2026-09-24)

- **Languages supported:** English and Hinglish pass G4 on dummy data. Hindi fails G4 on calibration
  (ECE 0.117 > 0.10) because department routing collapses to 43% on unseen Hindi phrasings, so it would be
  **disabled** (R4: remove `devanagari` from `schema.json` `allowed_scripts`). Everything else is refused
  by script. English and Hinglish can't be told apart (M7); both are allowed.
- **Max input length:** 512 tokens per question sequence, about 448 for the ticket after the question text.
  Longer tickets are refused with a message, never cut. Configurable (`model_max_len`); 256 halves
  worst-case latency but would refuse about 7% of dummy tickets.
- **Peak memory measured:** 343 MB whole app with the 38k-token vocabulary (worst page-cache case);
  329 MB with the 8.5k corpus-only vocabulary; 398–502 MB with the untrimmed 197k vocabulary.
  Measured as Linux RSS on a 16 GB container. **Not yet measured on a 4 GB machine or on Windows.**
- **Speed:** short tickets take about 1 s. A 512-token ticket takes about 8 s at p95 on 2 threads (5 questions,
  each re-reading the ticket). G5's 2 s isn't met for long tickets.
- **Known wrong-answer patterns (dummy data):**
  - Hindi department routing on unfamiliar phrasings.
  - Words the trimming corpus never saw: English department routing falls 83% → 67% (38k vocabulary) or
    50% (8.5k vocabulary) on 36 hand-written out-of-vocabulary tickets.
  - The base model before fine-tuning is near chance on our 5-department schema.
- **Confidence:** calibrated per question type (temperatures 1.38 / 1.91 / 1.76). Zones use the top
  calibrated probability. Calibration is fitted on dummy data and must be re-fitted on real data.
- **Not yet built / not yet true:**
  - real labeled data
  - a Laya fork (GitHub unreachable from the build container)
  - per-language or per-option-count calibration
  - English vs Hinglish separation
  - OS-level memory cap
  - an installer
  - a UI (CLI and 127.0.0.1 API only)
  - Kaggle GPU fine-tuning (CPU-only here)
