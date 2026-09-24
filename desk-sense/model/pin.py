"""Pinned upstream: plan M4. Change these only with a DECISIONS.md entry."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "model" / "artifacts"
DIST = ROOT / "model" / "dist"
# Overridable so smoke runs on synthetic data never touch the real data/, model/ or reports/.
DATA = Path(os.environ.get("LAYA_DATA_DIR", ROOT / "data"))
REPORTS = Path(os.environ.get("LAYA_REPORTS_DIR", ROOT / "reports"))
MODEL_OUT = Path(os.environ.get("LAYA_MODEL_OUT", ROOT / "model"))
ARTIFACTS = MODEL_OUT / "artifacts"
DIST = MODEL_OUT / "dist"
SCHEMA = ROOT / "schema.json"

HF_REPO = "convaiinnovations/laya-multilingual"
HF_REVISION = "052592a15d198d9ad47da779604259b10b47b7aa"
LAYA_VERSION = "0.3.6"

SHA256 = {
    "model.safetensors": "9d628fd971b700382ac6f65920a86f149777b2e748e0c955fb3b19695aa8f204",
}

WEEK1_MAX_LEN = 512


def snapshot_dir():
    from huggingface_hub import snapshot_download

    return Path(snapshot_download(HF_REPO, revision=HF_REVISION))


def load_agent(checkpoint=None, device="cpu"):
    """Build-time only: the torch model, from a fine-tuned checkpoint dir or the pinned revision."""
    os.environ.setdefault("USE_TF", "0")
    import laya

    if laya.__version__ != LAYA_VERSION:
        raise RuntimeError("laya %s installed, pinned %s" % (laya.__version__, LAYA_VERSION))
    return laya.load(str(checkpoint or snapshot_dir()), device=device)
