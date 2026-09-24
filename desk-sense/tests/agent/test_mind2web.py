"""Mind2Web conversion and per-row-question evaluation, on a tiny hand-made step (no download)."""
import json

import numpy as np

from model.browser.convert_mind2web import Tree, convert_task, element, history_line
from model.evaluate import evaluate, majority_baseline

HTML = """<html backend_node_id="1"><head><title backend_node_id="2">Tock</title></head><body>
<header backend_node_id="3"><a backend_node_id="4" aria_label="Tock home page"/></header>
<form backend_node_id="5"><div backend_node_id="6"><label backend_node_id="7"><text backend_node_id="8">Reservation type</text></label>
<div backend_node_id="9"><select backend_node_id="10" name="type">
<option backend_node_id="11" option_selected="true"><text backend_node_id="12">Dine in</text></option>
<option backend_node_id="13"><text backend_node_id="14">Pickup</text></option></select></div></div>
<input backend_node_id="15" type="search" placeholder="Find a location" input_value="Columbus"/>
<button backend_node_id="16"><text backend_node_id="17">Search</text></button></form></body></html>"""


def cand(nid, tag, y, **attrs):
    return {"tag": tag, "backend_node_id": nid,
            "attributes": json.dumps(dict(attrs, backend_node_id=nid, bounding_box_rect="10,%d,100,20" % y))}


TASK = {"website": "exploretock", "domain": "Travel", "confirmed_task": "Order pickup in Boston",
        "action_reprs": ["[combobox]  Reservation type -> SELECT: Pickup", "[searchbox]  Find a location -> TYPE: Boston"],
        "actions": [
            {"action_uid": "a1", "cleaned_html": HTML, "operation": {"op": "SELECT", "value": "Pickup"},
             "pos_candidates": [cand("10", "select", 50)],
             "neg_candidates": [cand("4", "a", 0, aria_label="Tock home page"), cand("15", "input", 80, type="search",
                                                                                     placeholder="Find a location", input_value="Columbus"),
                                cand("16", "button", 110)]},
            {"action_uid": "a2", "cleaned_html": HTML, "operation": {"op": "TYPE", "value": "Boston"},
             "pos_candidates": [cand("15", "input", 80, type="search", placeholder="Find a location", input_value="Columbus")],
             "neg_candidates": [cand("10", "select", 50), cand("16", "button", 110)]},
        ]}


def test_elements_are_named_like_the_extension_names_them():
    tree = Tree(HTML)
    sel = element(cand("10", "select", 50), tree)
    assert (sel["role"], sel["name"], sel["value"], sel["region"]) == ("select", "Reservation type", "Dine in", "form")
    box = element(cand("15", "input", 80, type="search", placeholder="Find a location", input_value="Columbus"), tree)
    assert (box["role"], box["name"], box["value"]) == ("searchbox", "Find a location", "Columbus")
    assert element(cand("16", "button", 110), tree)["name"] == "Search"
    assert element(cand("4", "a", 0, aria_label="Tock home page"), tree)["region"] == "header"


def test_history_lines():
    assert history_line("[combobox]  Reservation type -> SELECT: Pickup") == 'select Reservation type "Pickup"'
    assert history_line("[svg]   -> CLICK") == "click "


def test_convert_task_builds_runtime_questions():
    rows, stats = convert_task(TASK, "seed")
    assert stats["steps"] == 2 and len(rows) == 2
    first, second = rows
    crit = first["questions"]["next"]["criteria"]
    assert first["labels"]["next"] in crit and crit[first["labels"]["next"]].startswith("select Reservation type")
    assert {"scroll_down", "none_of_these"} <= set(crit)
    assert first["group"] == "exploretock" and first["state"].startswith("goal: Order pickup in Boston")
    assert 'done: select Reservation type "Pickup"' in second["state"]


def test_evaluate_uses_each_rows_own_questions_and_ranker_baseline():
    rows, _ = convert_task(TASK, "seed")
    labels = [r["labels"]["next"] for r in rows]

    def oracle(state, qs):
        row = next(r for r in rows if r["state"] == state)
        keys = list(qs["next"]["criteria"])
        return {"next": np.eye(len(keys))[keys.index(row["labels"]["next"])]}

    assert evaluate(oracle, rows, {})["en"]["accuracy"] == 1.0
    base = majority_baseline(rows, rows, {})["en"]["accuracy"]
    first_keys = [list(r["questions"]["next"]["criteria"])[0] for r in rows]
    assert base == np.mean([a == b for a, b in zip(first_keys, labels)])


def test_prune_plan_keeps_global_layers_and_their_types():
    import pytest

    from model.browser.prune_layers import plan

    types = ["full_attention", "sliding_attention", "sliding_attention"] * 7 + ["full_attention"]
    keep, kept_types = plan({"layer_types": types})
    assert keep == [0, 3, 6, 9, 12, 15, 18, 21] and set(kept_types) == {"full_attention"}
    keep, kept_types = plan({"layer_types": types}, [0, 1, 21])
    assert kept_types == ["full_attention", "sliding_attention", "full_attention"]
    with pytest.raises(ValueError):
        plan({"layer_types": types}, [3, 0])
