# desk-sense

Offline support-ticket triage (Hindi, English, Hinglish) on the Laya multilingual decision model, built
to run on a 4 GB i3/Ryzen machine in ≤ 500 MB. Week-1 sprint: `LAYA_LITE_MASTER_PLAN.md`.

## Commands

```bash
pip install -r requirements-build.txt          # build machine (torch CPU: see file header)
pip install -r requirements-runtime.txt        # target machine: no torch
python -m pytest -q                            # fake worker; model tests skip without model/dist
python -m model.build_model                    # trim -> ONNX -> int8 -> calibrate -> model/dist
python -m tests.measure_app --n 200            # whole-app peak memory + latency -> reports/g2_memory.json
python -m app.cli ask "मुझसे दो बार शुल्क लिया गया"   # add --fake to run without the model
```

## Architecture

See `.claude/skills/codebase-overview`. Invoke it instead of exploring the tree.

## Non-negotiables (plan §1, enforced by tests)

- The worker (`app/`) never imports torch or transformers. Build code lives in `model/`.
- Peak memory is **measured**, never estimated: `tests.measure_app`. Every number in a report
  says where it was measured (this dev container is 16 GB and 4 cores, not the target).
- Pipeline order is fixed: fine-tune -> trim -> ONNX -> int8 -> calibrate last. One script:
  `model/build_model.py`. Never calibrate a file that is changed afterwards.
- `data/splits/test.jsonl` is opened only by `model.evaluate --final`, once, on Day 7.
- Unsupported scripts are refused in `app/guard.py`, never guessed. Input is never cut silently.
- Server binds `127.0.0.1` only.
- Any change to a gate threshold, quantization method or vocabulary trim gets a `DECISIONS.md` row.

## Working agreements

- No AI co-author or session trailers in commits or PRs (no `Co-Authored-By: Claude`, no
  `Claude-Session:`). `attribution` is off in `.claude/settings.json` and the Bash hook refuses them.
- Definition of Done: `DEFINITION-OF-DONE.md`. Run the `ship-it` skill before declaring done.
- Model binaries (`model/artifacts`, `model/dist`) and real user text (`data/*`) are gitignored.
- Delegate long runs (build ~7 min, measure ~5 min) and log reading to subagents.
- Record durable mistakes in `docs/lessons.md`.

## Compact instructions

Preserve: current gate being worked (G1-G5), measured numbers and where they were measured,
decisions and why, failing test output. Drop superseded experiments.
