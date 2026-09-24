## Day 1 — 2026-09-23

**Gates:** G1 [x] pass · G2 [ ] fail by 2 MB (worst case; stage B trim required) · G3 [ ] needs labeled data · G4 [ ] Day 7 · G5 [ ] long tickets too slow (decide Day 5)

Measured in the dev container (16 GB RAM, 4 vCPU, Linux 6.18, no GPU, worker on 2 threads).
**Not the 4 GB target machine.** Day 5 repeats all of this there.

| Person | Done today | Next | Blocked? |
|---|---|---|---|
| ML | Sanity check. G1 pass. int8 method chosen by measurement. Stage A trim. Pipeline script. Fine-tune script (CPU smoke test) | Stage B corpus trim once real text exists; fine-tune on Kaggle | Needs labeled data + Kaggle GPU; GitHub fork (403 here) |
| APP | Supervisor, worker, SQLite, crash replay, watchdog, idle stop, guard, zones, CLI, 127.0.0.1 API; 38 tests | Run on the 4 GB machine; G5 input-length decision | Target machine |
| DATA | Schema locked (`schema.json`); labeling guide drafted (`docs/labeling-guide.md`); split and agreement tools | Collect 800+ real tickets, label, 10% double-labeled | Real ticket text |

**Numbers today:** peak MB **398–502** (same bundle; see G2) | p95 latency **6.9 s** (p50 0.83 s) | val accuracy — (no labels) | labeled count **0** (only 60 synthetic rows for smoke tests)

### Sanity check (plan §2), pinned checkpoint, torch fp32, CPU

| Ticket | department | urgency (0–2) | refund | ms |
|---|---|---|---|---|
| मुझसे दो बार शुल्क लिया गया, कृपया रिफंड करें | billing (1.00) | 1.87 | 0.996 | 140 |
| The app crashes every time I open settings… | technical (0.98) | 1.91 | 0.000 | 126 |
| bhai mera payment do baar kat gaya, refund chahiye | billing (1.00) | 1.67 | 0.998 | 130 |

Torch fp32 peak RSS: **4,091 MB.** That's why the runtime is ONNX int8 with no torch.

### G1 — ONNX conversion: PASS

200 generated requests, 609 questions, 1–5 questions and 2–20 options each, Hindi/English/Hinglish,
8 inputs longer than 512 tokens. Worst |Δp| **0.000052** (limit 0.01). Top answer matches 100%, and the token port matches 200/200.
The first export failed at runtime (decision head fixed at 300 tokens); fixed, see DECISIONS.md.
Files: `reports/g1_summary.json`, `reports/build.md`.

### G2 — memory: FAIL by 2 MB in the worst measured case

| Build | Weights | Whole-app peak RSS | Worker | Supervisor + CLI |
|---|---|---|---|---|
| Plan settings (inline weights, arena off, batch of 5), no trim | 364 MB | **1,421 MB** | 1,384 | 37 |
| Stage A trim + external data + memory settings, 5 runs | 313 MB | **397.7–398.9 MB** | 361 | 37 |
| Same bundle, measured right after it was written | 313 MB | **502.2 MB** | 465 | 37 |
| Stage B *proxy* (37k tokens; accuracy unusable, memory only) | 175 MB | **362.5 MB** (freshly written) | 325 | 37 |

The 398 vs 502 gap is file-backed weight pages. How much of the memory-mapped weights file counts as
resident depends on how the kernel holds it in cache, so the same bytes measure differently.
Windows "private bytes" (the plan's target metric) doesn't count these pages at all. That's still to verify on Day 5.
**Decision: vocabulary stage B from real ticket text (plan §8.4), then re-measure.**
Other results: no torch in the worker; cold start **1.9 s** (0.8 s with the stage B proxy); 200/200 requests done.

Where the untrimmed 1,421 MB went, and what fixed each part:

| Part | Before | After | Fix |
|---|---|---|---|
| Tokenizer (256k vocab) | +320 MB resident, 437 peak | ~70 MB | Stage A trim; `malloc_trim` after load |
| Model load | +580 MB transient | +10 MB (memory-mapped) | External-data weights |
| Activations, 5 × 512 tokens | +230–600 MB | ~+50 MB | Arena on; 512-token batches; `malloc_trim` per request |

### G5 — speed (early reading; the gate itself is Day 5 on the target)

2 threads: model p50 **0.83 s**, p95 **6.9 s**. Every 10th benchmark request is a full 512-token ticket, and
Laya encodes the ticket once per question (5×). Short tickets take ~0.8 s. Long tickets won't meet 2 s on an i3.

### What the base model does on our schema (zero-shot, not a gate)

The Hindi refund ticket gets `department=billing` at only **p=0.41** with our 5 described departments,
against 1.00 with the 3-option sanity check. The zone logic correctly sends it to FLAG. That's the plan's
"near chance zero-shot" warning; G3 (Day 2) is the test.

**Decisions needed:** real ticket text for stage B and labeling · a 4 GB test machine · the G5 answer for long tickets (input cap at 256 tokens? fewer questions per call?)
