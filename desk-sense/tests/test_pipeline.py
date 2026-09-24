"""Pipeline pieces that need no model: data splits, the test-set lock, calibration, ECE, trimming."""
import json
import os
from pathlib import Path

import numpy as np
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_tickets.jsonl"


@pytest.fixture
def data_env(tmp_path, monkeypatch):
    import model.data as d

    (tmp_path / "labeled").mkdir()
    (tmp_path / "labeled" / "t.jsonl").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(d, "LABELED", tmp_path / "labeled")
    monkeypatch.setattr(d, "SPLITS", tmp_path / "splits")
    monkeypatch.setattr(d, "REPORTS", tmp_path / "reports")
    return d, tmp_path


def test_split_is_per_language_and_locks_test(data_env):
    d, tmp = data_env
    d.split()
    counts = json.loads((tmp / "reports" / "test_lock.json").read_text())["counts"]
    total = sum(sum(v.values()) for v in counts.values())
    assert total == 60 and set(counts["test"]) == {"hi", "en"}
    assert counts["train"]["en"] > counts["val"]["en"]
    test = tmp / "splits" / "test.jsonl"
    assert not os.access(test, os.W_OK) or os.geteuid() == 0  # read-only (root ignores the bit)
    assert oct(test.stat().st_mode)[-3:] == "444"
    with pytest.raises(SystemExit, match="locked"):
        d.split()


def test_splits_do_not_overlap(data_env):
    d, tmp = data_env
    d.split()
    ids = {name: {r["id"] for r in d.read_jsonl(tmp / "splits" / ("%s.jsonl" % name))} for name in d.FRACTIONS}
    names = list(ids)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not ids[a] & ids[b], (a, b)


def test_target_index_mapping():
    from model.data import load_schema, target_index

    q = load_schema()["questions"]
    assert target_index(q["department"], "billing") == 0
    assert target_index(q["urgency"], 2) == 2 and target_index(q["urgency"], "soon") == 1
    assert target_index(q["refund_requested"], True) == 1 and target_index(q["refund_requested"], "no") == 0
    assert target_index(q["department"], "unknown-team") is None and target_index(q["urgency"], 9) is None


def test_agreement_flags_low_agreement(tmp_path):
    from model.data import agreement, read_jsonl, write_jsonl

    rows = read_jsonl(FIXTURE)[:10]
    flipped = [dict(r, labels=dict(r["labels"], department="other")) for r in rows]
    write_jsonl(tmp_path / "a.jsonl", rows)
    write_jsonl(tmp_path / "b.jsonl", flipped)
    res = agreement(tmp_path / "a.jsonl", tmp_path / "b.jsonl")
    assert res["urgency"]["agreement"] == 1.0 and res["department"]["agreement"] < 0.8
    assert "fix the labeling guide" in res["_verdict"]


def test_ece_perfect_and_overconfident():
    from model.evaluate import ece

    assert ece([1.0, 1.0], [1, 1]) == 0.0
    assert ece([0.95] * 10, [1] * 5 + [0] * 5) == pytest.approx(0.45)


def test_temperature_fit_softens_overconfident_logits():
    from model.calibrate.calibrate import ece_at, fit

    rng = np.random.default_rng(0)
    pairs = []
    for _ in range(400):
        y = int(rng.integers(3))
        z = rng.normal(0, 1, 3)
        z[y if rng.random() < 0.6 else (y + 1) % 3] += 2.0
        pairs.append((z * 4.0, y))  # 60% accurate, scaled to look very sure
    t = fit(pairs)
    assert t > 1.5
    assert ece_at(pairs, t) < ece_at(pairs, 1.0) / 2


def test_evaluate_scores_per_language():
    from model.data import load_schema, read_jsonl, target_index
    from model.evaluate import evaluate, majority_baseline

    rows = read_jsonl(FIXTURE)
    qs = load_schema()["questions"]

    def oracle(state, questions):
        row = next(r for r in rows if r["state"] == state)
        out = {}
        for qid, qdef in questions.items():
            k = 2 if qdef["type"] == "noul" else len(qdef["criteria"])
            p = np.full(k, 0.0)
            p[target_index(qdef, row["labels"][qid])] = 1.0
            out[qid] = p
        return out

    res = evaluate(oracle, rows, qs)
    assert res["hi"]["accuracy"] == 1.0 and res["en"]["accuracy"] == 1.0 and res["en"]["ece"] == 0.0
    base = majority_baseline(rows, rows, qs)
    assert base["en"]["accuracy"] < 1.0


def test_trim_keeps_bytes_and_base_chars_and_drops_other_scripts():
    from model.trim.trim_vocab import trim

    tok = {
        "model": {"type": "BPE", "byte_fallback": True, "unk_token": "<unk>",
                  "vocab": {"<unk>": 0, "<0x41>": 1, "a": 2, "b": 3, "ab": 4, "क": 5, "ा": 6, "का": 7,
                            "中": 8, "文": 9, "中文": 10, "▁": 11},
                  "merges": [["a", "b"], ["क", "ा"], ["中", "文"]]},
        "added_tokens": [{"id": 0, "content": "<unk>"}],
        "post_processor": None,
    }
    out, keep = trim(tok)
    kept = set(out["model"]["vocab"])
    assert {"<unk>", "<0x41>", "a", "b", "ab", "क", "ा", "का", "▁"} <= kept
    assert not {"中", "文", "中文"} & kept
    assert out["model"]["merges"] == [["a", "b"], ["क", "ा"]]
    assert list(keep) == sorted(keep) and out["model"]["vocab"]["ab"] == list(keep).index(4)


def test_trim_keeps_whitespace_added_tokens():
    """Regression: '\\n' is an added token in mmBERT's tokenizer; dropping it turned every newline
    into a byte token, so multi-line tickets and browser states read differently than in training."""
    from model.trim.trim_vocab import trim

    tok = {
        "model": {"type": "BPE", "byte_fallback": True, "unk_token": "<unk>",
                  "vocab": {"<unk>": 0, "\n": 1, "\n\n": 2, "\t": 3, "<unused0>": 4, "中文": 5, "a": 6},
                  "merges": []},
        "added_tokens": [{"id": 0, "content": "<unk>"}, {"id": 1, "content": "\n"}, {"id": 2, "content": "\n\n"},
                         {"id": 3, "content": "\t"}, {"id": 4, "content": "<unused0>"}, {"id": 5, "content": "中文"}],
        "post_processor": None,
    }
    out, _ = trim(tok)
    kept = set(out["model"]["vocab"])
    assert {"\n", "\n\n", "\t", "<unused0>", "a"} <= kept and "中文" not in kept
    assert {a["content"] for a in out["added_tokens"]} == {"<unk>", "\n", "\n\n", "\t", "<unused0>"}


def test_group_split_keeps_phrasings_apart_and_covers_every_stratum(tmp_path, monkeypatch):
    import model.data as d
    from model.synthetic import make_ticket
    import random

    rng = random.Random(1)
    rows = [make_ticket(rng, v, i) for v in ("hi", "en", "hinglish") for i in range(200)]
    (tmp_path / "labeled").mkdir()
    d.write_jsonl(tmp_path / "labeled" / "s.jsonl", rows)
    monkeypatch.setattr(d, "LABELED", tmp_path / "labeled")
    monkeypatch.setattr(d, "SPLITS", tmp_path / "splits")
    monkeypatch.setattr(d, "REPORTS", tmp_path / "reports")
    d.split()
    sp = {n: d.read_jsonl(tmp_path / "splits" / ("%s.jsonl" % n)) for n in d.FRACTIONS}
    groups = {n: {r["group"] for r in v} for n, v in sp.items()}
    assert not groups["train"] & (groups["test"] | groups["val"] | groups["calib"])
    strata = {r["stratum"] for r in rows}
    for name in ("val", "calib", "test"):
        assert {r["stratum"] for r in sp[name]} == strata, name


def test_synthetic_labels_follow_composition():
    import random

    from model.synthetic import make_ticket

    rng = random.Random(5)
    for i in range(300):
        r = make_ticket(rng, rng.choice(["hi", "en", "hinglish"]), i)
        lab = r["labels"]
        assert not lab["refund_requested"] or lab["department"] == "billing"
        assert lab["needs_human"] == (lab["department"] in ("billing", "technical", "account") or lab["sentiment"] == "angry")
        if lab["department"] in ("sales", "other"):
            assert lab["urgency"] == 0


def test_micro_batches_bound_tokens_and_keep_every_item():
    pytest.importorskip("torch")
    from model.finetune.finetune import micro_batches

    items = [{"ids": [0] * n} for n in (500, 40, 40, 300, 60, 512, 30)]
    parts = micro_batches(items, 1024)
    assert sorted(len(x["ids"]) for p in parts for x in p) == sorted(len(x["ids"]) for x in items)
    for p in parts:
        assert len(p) == 1 or max(len(x["ids"]) for x in p) * len(p) <= 1024


def test_closure_follows_every_producer_of_a_token():
    from model.trim.trim_vocab import build_closure

    # abcd can be built as abc+d or ab+cd; BPE may take either path, so both must survive.
    merges = [("a", "b"), ("c", "d"), ("ab", "c"), ("abc", "d"), ("ab", "cd")]
    assert {"a", "b", "c", "d", "ab", "cd", "abc", "abcd"} <= build_closure({"abcd"}, merges)


def test_schema_lines_are_what_the_model_reads():
    from model.data import load_schema
    from model.trim.trim_vocab import schema_lines

    lines = schema_lines(load_schema())
    assert "choice question: Which team should handle this ticket?" in lines
    assert " billing: invoices, payments, charges, refunds" in lines
    assert " true: yes, the statement holds" in lines
