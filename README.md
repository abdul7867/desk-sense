# desk-sense

**Offline support-ticket triage for Hindi, English and Hinglish that fits on a cheap 4 GB PC.**

A customer ticket goes in; five answers come out, each with a calibrated probability and a decision
zone: **act** (apply automatically), **confirm** (a person checks it) or **flag** (a person decides).

| Question | Kind | Answers |
|---|---|---|
| Which team should handle it? | choice | billing · technical · account · sales · other |
| How urgent is it? | score | not urgent · soon · blocking work |
| Is the customer asking for money back? | yes/no | |
| What is the customer's mood? | choice | angry · neutral · happy |
| Does a person need to reply? | yes/no | |

It runs fully offline in about **345 MB of memory**, with no GPU and no PyTorch on the target machine.
Languages it can't read are refused, never guessed. Nothing is lost if the process crashes.

```
$ python -m app.cli ask "bhai mera payment do baar kat gaya, refund chahiye"
#1  language=en  FLAG    (human review)  768ms
  department        billing                                  p=1.00  act
  urgency           blocking work (level 2, expected 1.64)   p=0.70  confirm
  refund_requested  yes                                      p=0.98  act
  sentiment         neutral                                  p=0.57  flag
  needs_human       yes                                      p=0.85  confirm
```

## Where it stands

> **Honest status:** no real customer tickets have been used yet. The base model was measured on
> Day 1. Days 2–7 of the plan were run end to end on **1,200 generated (dummy) tickets** to prove the
> pipeline and every quality gate. Those accuracy numbers show the machinery works, **not** how well
> it will do on real tickets. All numbers were measured on a 16 GB / 4-core Linux machine (worker on
> 2 threads), not yet on the 4 GB target.

| Gate | Result |
|---|---|
| **G1** converted model matches the original | **Pass**: largest probability difference 0.000052 (limit 0.01) |
| **G2** whole app ≤ 500 MB | **Pass**: 343 MB, worst case, with the fine-tuned model |
| **G3** model learns our task (dummy data) | **Pass**: English 96.7%, Hindi 95.1% (baseline ~54%) |
| **G4** final accuracy, test set used once (dummy data) | English + Hinglish **97.3% pass** · Hindi 84.7%, but its confidence isn't reliable enough (calibration error 0.117 > 0.10) → **Hindi switched off** |
| **G5** stability | **Pass**: 1 hour, 2,012 requests, 0 crashes, memory flat at 345 MB |
| **G5** speed ≤ 2 s | Short tickets **~1 s**; long (512-token) tickets **~8 s**. Not met yet |
| Works offline · local-only server · no lost requests | **Pass** (all tested) |

Details: [`desk-sense/reports/day-2-7-dryrun.md`](desk-sense/reports/day-2-7-dryrun.md) ·
decisions and their measurements: [`desk-sense/DECISIONS.md`](desk-sense/DECISIONS.md).

## Quick start

```bash
cd desk-sense

# Build machine (needs PyTorch; the CPU build is enough):
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.0
pip install -r requirements-build.txt
python -m model.build_model          # trim → ONNX → int8 → calibrate → model/dist (~7 min)

# Target machine (no PyTorch). Copy model/dist over, then:
pip install -r requirements-runtime.txt
python -m app.cli ask "मुझसे दो बार शुल्क लिया गया, कृपया रिफंड करें"
python -m app.cli shell              # one ticket per line
python -m app.supervisor --port 8765 # JSON API on 127.0.0.1 only

python -m pytest -q                  # add --fake to the CLI to try it without a model
```

## How it works

```
CLI / local API ─► Supervisor ───────────────► Worker process (ONNX Runtime, int8, no PyTorch)
                   saves every request first    weights memory-mapped, trimmed vocabulary
                   refuses unsupported scripts  refuses tickets that don't fit, never cuts them
                   memory watchdog + restart    
                   act / confirm / flag zones
```

Model pipeline, always in this order: fine-tune → trim vocabulary → export to ONNX → int8 → calibrate.
One command (`model/build_model.py`) runs it and stops if any step costs more than 2 accuracy points.

## What it needs next

1. **Real tickets**: 800+ labeled, especially varied Hindi (Hindi department routing is the weakest point).
   Labeling guide: [`desk-sense/docs/labeling-guide.md`](desk-sense/docs/labeling-guide.md).
2. **A 4 GB test machine**, ideally Windows, to confirm memory and speed where it will actually run.
3. **A choice for long tickets**: shorter input (256 tokens halves the worst case) or fewer questions per ticket.

## What's in this repository

| Path | What it is |
|---|---|
| [`desk-sense/`](desk-sense/) | The app: runtime, model pipeline, tests, reports ([app README](desk-sense/README.md)) |
| `claude/`, `install.sh`, `profiles/`, `templates/` | **Tokensaver**, the Claude Code setup this was built with ([docs/TOKENSAVER.md](docs/TOKENSAVER.md)) |
| `docs/` | Tokensaver documentation: measuring, memory, research |
| [`docs/claude-in-chrome.md`](docs/claude-in-chrome.md) | Making Claude in Chrome faster on a 4 GB PC: speed shortcut, settings, low-RAM Chrome setup |

## Credits

The base model is [Laya](https://huggingface.co/convaiinnovations/laya) (multilingual checkpoint) by
Convai Innovations, Apache-2.0. desk-sense pins it by revision and checksum, fine-tunes it, and runs it
through ONNX Runtime.
