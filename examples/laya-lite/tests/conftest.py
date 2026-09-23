import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.supervisor import Supervisor  # noqa: E402


@pytest.fixture
def make_sup(tmp_path):
    made = []

    def make(**kw):
        kw.setdefault("fake", True)
        sup = Supervisor(tmp_path / "t.db", **kw)
        made.append(sup)
        return sup

    yield make
    for s in made:
        s.close()


def pytest_addoption(parser):
    parser.addoption("--run-day7", action="store_true", help="run the locked test split (plan R5: once, Day 7)")
