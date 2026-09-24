"""Runs the extension's own tests (extension/test/*.test.mjs) under Node, so `pytest` covers them."""
import shutil
import subprocess
from pathlib import Path

import pytest

EXT_TESTS = sorted(str(p) for p in (Path(__file__).resolve().parents[2] / "extension" / "test").glob("*.test.mjs"))


def _playwright_available():
    if shutil.which("node") is None:
        return False
    probe = ("const {createRequire}=require('module');const r=createRequire(process.cwd()+'/');"
             "try{r('playwright')}catch(e){r(require('child_process').execSync('npm root -g').toString().trim()+'/playwright')}")
    return subprocess.run(["node", "-e", probe], capture_output=True).returncode == 0


@pytest.mark.skipif(not _playwright_available(), reason="needs node and playwright (npm i -g playwright)")
def test_extension_js_suite():
    res = subprocess.run(["node", "--test", *EXT_TESTS], capture_output=True, text=True, timeout=600)
    assert res.returncode == 0, res.stdout[-4000:] + res.stderr[-2000:]
