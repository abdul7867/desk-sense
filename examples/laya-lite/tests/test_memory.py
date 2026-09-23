"""R1 / G2 / G5: whole-app peak memory with the real model. Skipped when no bundle is built.

Runs tests.measure_app in a fresh process so pytest's own memory is not counted.
Linux RSS of memory-mapped weights depends on page-cache state: the same bundle measured 398 MB
here and 502 MB right after it was written. The G2 gate uses the worst run (DECISIONS.md).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / "model" / "dist"

pytestmark = [pytest.mark.model,
              pytest.mark.skipif(not (BUNDLE / "model.onnx").exists(), reason="no model bundle; run model.build_model")]


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    out = tmp_path_factory.mktemp("mem") / "report.json"
    subprocess.run([sys.executable, "-m", "tests.measure_app", "--bundle", str(BUNDLE), "--n", "60", "--out", str(out)],
                   cwd=ROOT, check=False, capture_output=True, timeout=1800)
    return json.loads(out.read_text())


def test_whole_app_peak_memory_within_budget(report):
    assert report["statuses"] == {"done": 60}
    assert report["peak_mb"]["total"] <= 500, report["peak_mb"]


def test_worker_has_no_torch(report):
    assert report["worker_imports_torch"] is False


def test_watchdog_does_not_fire_on_a_healthy_worker(report):
    assert report["worker_restarts"] == 0


def test_cold_start_under_5s(report):
    assert report["cold_start_s"] <= 5.0
