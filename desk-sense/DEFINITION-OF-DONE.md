# Definition of Done

Work is finished when every applicable gate passes. Mark a gate N/A only when it genuinely does
not apply, and say why. The `ship-it` skill walks this list.

## Gates

- [ ] **Implemented** — edge cases and error paths handled, not only the happy path
- [ ] **Tested** — including the failure path; a bug fix includes a test that fails before the fix
- [ ] **Tests pass** — `python -m pytest -q`, green
- [ ] **No torch in the runtime** — nothing under `app/` imports torch/transformers
      (`measure_app` reports `worker_imports_torch: false`)
- [ ] **Model change → gates re-run** — any change to export, quantization, trimming or the
      checkpoint re-runs `model.build_model` (G1 + per-step accuracy) and `tests.measure_app` (G2/G5);
      the new numbers go in `reports/` with where they were measured
- [ ] **Test split untouched** — nothing read `data/splits/test.jsonl` except a Day-7 `--final` run
- [ ] **Documented** — README / DECISIONS.md updated in this same change
- [ ] **Errors handled** — no silent catches; refusals tell the user what to do
- [ ] **Secure** — no secrets or real user text committed; server on 127.0.0.1 only
- [ ] **Accessible** — N/A for the Week-1 CLI; applies when a UI exists
- [ ] **Reviewed** — `code-reviewer` subagent run; findings addressed or explicitly waived
- [ ] **Overview current** — `.claude/skills/codebase-overview/SKILL.md` updated if the layout moved

## Waiving a gate

Waiving is allowed. Waiving silently is not. Write the waiver in the commit body: which gate, why,
and what would un-waive it.
