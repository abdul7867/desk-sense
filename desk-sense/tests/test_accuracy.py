"""G4, Day 7 only (plan R5): per-language accuracy and ECE on the untouched test split.

Deselected by default. Run it once, on Day 7:  pytest -m day7 --run-day7
Every run is logged to reports/test_runs.log by model.evaluate.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_SPLIT = ROOT / "data" / "splits" / "test.jsonl"
BUNDLE = ROOT / "model" / "dist"
GATES = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))["gates"]

pytestmark = [pytest.mark.day7, pytest.mark.model]


@pytest.fixture(scope="module")
def result(request):
    if not request.config.getoption("--run-day7"):
        pytest.skip("test split is for Day 7 only; pass --run-day7")
    if not TEST_SPLIT.exists() or not (BUNDLE / "model.onnx").exists():
        pytest.skip("needs data/splits/test.jsonl and model/dist")
    out = subprocess.run([sys.executable, "-m", "model.evaluate", "--bundle", str(BUNDLE), "--split", "test", "--final"],
                         cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def test_each_language_meets_g4(result):
    failing = {lang: v for lang, v in result.items()
               if v["accuracy"] < GATES["g4_min_accuracy"] or v["ece"] > GATES["g4_max_ece"]}
    assert not failing, "disable these languages (R4): %s" % json.dumps(
        {k: {"accuracy": v["accuracy"], "ece": v["ece"]} for k, v in failing.items()})
