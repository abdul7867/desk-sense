---
paths:
  - "**/*.py"
description: desk-sense Python conventions. Loads only when touching Python files.
---

# Python rules

- `app/` is the shipped runtime: onnxruntime, tokenizers, numpy, psutil and the stdlib only.
  torch/transformers/laya imports belong in `model/`.
- Validate at the boundary: `guard.check` for input, `Supervisor.submit` for requests, CLI args.
- Never `except Exception:` without turning it into a reply, a stored status or a re-raise.
- Parameterized SQL only (`store.py`). Every request row is written before it is processed.
- Numbers in reports are measured and say where (machine, threads). Estimates are labelled estimates.
