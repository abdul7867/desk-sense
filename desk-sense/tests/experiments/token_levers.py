"""B0 speed levers (DECISIONS.md 2026-09-24). Run from desk-sense/: python tests/experiments/<this file>.
Needs model/dist; quant_levers also needs model/artifacts/int8_acc4 and int4 (model.quantize.quantize)."""
import functools, json, sys, tempfile
from pathlib import Path
sys.path.insert(0, ".")
from browser import question, rank
import tests.measure_browser as mb

SHORT = {"scroll_down": "scroll down", "scroll_up": "scroll up", "wait": "wait", "done": "step already done",
         "none_of_these": "none fits"}
orig_fixed, orig_short = dict(question.FIXED_MOVES), rank.shortlist
out = {}
for name, fixed, k in [("short_fixed_k12", SHORT, 12), ("long_fixed_k8", orig_fixed, 8), ("short_fixed_k8", SHORT, 8)]:
    question.FIXED_MOVES.clear(); question.FIXED_MOVES.update(fixed)
    rank.shortlist = functools.partial(orig_short, k=k)
    with tempfile.TemporaryDirectory() as tmp:
        r = mb.measure(Path("model/dist"), 200, 2, Path(tmp) / "m.db")
    out[name] = {"tokens_p50": r["tokens_per_step"]["p50"], "latency_ms": r["model_latency_ms"], "peak_mb": r["peak_mb"]["total"]}
    print(name, out[name], flush=True)
json.dump(out, open("reports/browser/b0_token_levers.json", "w"), indent=2)
