"""The agent loop on the fake worker (picks the ranker's top option at p=0.9) and a scripted thinker."""
import http.client
import json
import sqlite3
import threading

import pytest

from app.supervisor import make_server
from browser.controller import Controller
from browser.serve import agent_routes
from browser.steplog import StepLog
from thinker.fake import ScriptedThinker


def el(i, role, name, **kw):
    return {"i": i, "role": role, "name": name, **kw}


def flights_page(**kw):
    page = {"host": "flights.example", "title": "Find flights", "elements": [
        el(0, "link", "Home", region="header"),
        el(1, "textbox", "From", value=kw.get("frm", "")),
        el(2, "textbox", "To", value=kw.get("to", "")),
        el(3, "button", "Search flights"),
        el(4, "button", "Search hotels"),
    ]}
    return page


FLIGHT_PLAN = [{"op": "type", "target": "From", "value": "Zurich"},
               {"op": "type", "target": "To", "value": "London"},
               {"op": "click", "target": "Search flights"}]


class CountingSup:
    """Wraps a fake supervisor to count local-model calls."""

    def __init__(self, sup):
        self.sup, self.decides = sup, 0

    def decide(self, *a):
        self.decides += 1
        return self.sup.decide(*a)

    def warm(self):
        self.sup.warm()


@pytest.fixture
def make_ctl(make_sup, tmp_path):
    made = []

    def make(plans=None, texts=None, script=None):
        sup = CountingSup(make_sup(fake_policy="first"))
        thinkers = []

        def factory():
            t = ScriptedThinker({"go": plans or FLIGHT_PLAN}, texts)
            if script:
                t.resolve = script
            thinkers.append(t)
            return t

        log = StepLog(tmp_path / "steps.db")
        made.append(log)
        return Controller(sup, factory, log), sup, thinkers, log

    yield make
    for log in made:
        log.close()


def test_obvious_task_runs_on_fast_paths_only(make_ctl):
    ctl, sup, thinkers, _ = make_ctl()
    a = ctl.start("go", None, flights_page())
    assert (a["op"], a["index"], a["value"], a["source"]) == ("type", 1, "Zurich", "fastpath")
    a = ctl.step(a["task"], flights_page(frm="Zurich"), {"ok": True})
    assert (a["op"], a["index"], a["value"]) == ("type", 2, "London")
    a = ctl.step(a["task"], flights_page(frm="Zurich", to="London"), {"ok": True})
    assert (a["op"], a["index"]) == ("click", 3) and "confirm" not in a
    a = ctl.step(a["task"], {"host": "flights.example", "title": "Results", "elements": []}, {"ok": True, "changed": True})
    assert a["op"] == "finish"
    assert sup.decides == 0 and thinkers[0].calls == ["plan"]


def test_fuzzy_target_goes_to_the_local_model(make_ctl):
    ctl, sup, thinkers, _ = make_ctl(plans=[{"op": "click", "target": "search button"}])
    a = ctl.start("go", None, flights_page())
    assert (a["op"], a["index"], a["source"], a["zone"]) == ("click", 3, "model", "act")
    assert sup.decides == 1 and thinkers[0].calls == ["plan"]


def test_field_already_filled_is_skipped(make_ctl):
    ctl, _, _, _ = make_ctl()
    a = ctl.start("go", None, flights_page(frm="Zurich"))
    assert (a["op"], a["index"]) == ("type", 2)


def test_failed_twice_asks_the_thinker(make_ctl):
    ctl, _, thinkers, _ = make_ctl(plans=[{"op": "click", "target": "Search flights"}])
    a = ctl.start("go", None, flights_page())
    a = ctl.step(a["task"], flights_page(), {"ok": True, "changed": False})  # click did nothing
    a = ctl.step(a["task"], flights_page(), {"ok": False})
    assert a["source"] == "thinker" and "resolve" in thinkers[0].calls


def test_risky_action_needs_confirmation_and_decline_stops(make_ctl):
    page = {"host": "shop.example", "title": "Cart", "elements": [el(1, "button", "Place order")]}
    ctl, _, _, _ = make_ctl(plans=[{"op": "click", "target": "Place order"}])
    a = ctl.start("go", None, page)
    assert a["op"] == "click" and "buys" in a["confirm"]
    assert ctl.step(a["task"], page, {"declined": True})["op"] == "stop"
    assert ctl.step(a["task"], page, {})["op"] == "finish"


def test_irreversible_plan_step_needs_confirmation(make_ctl):
    ctl, _, _, _ = make_ctl(plans=[{"op": "click", "target": "Search flights", "irreversible": True}])
    assert "irreversible" in ctl.start("go", None, flights_page())["confirm"]


def test_other_site_pauses(make_ctl):
    ctl, _, _, _ = make_ctl()
    a = ctl.start("go", ["flights.example"], flights_page())
    a = ctl.step(a["task"], dict(flights_page(), host="evil.example"), {"ok": True})
    assert a["op"] == "pause" and a["host"] == "evil.example"


def test_unreadable_goal_is_refused(make_ctl):
    ctl, _, _, _ = make_ctl()
    assert ctl.start("ខ្ញុំចង់ទិញសំបុត្រ", None, flights_page())["op"] == "refused"


def test_unreadable_top_labels_go_to_the_thinker(make_ctl):
    page = {"host": "x.example", "title": "t", "elements": [el(1, "button", "ស្វែងរក"), el(2, "button", "ជួយ")]}
    ctl, sup, thinkers, _ = make_ctl(plans=[{"op": "click", "target": "search"}])
    a = ctl.start("go", None, page)
    assert a["source"] == "thinker" and sup.decides == 0


def test_type_without_value_composes_text(make_ctl):
    page = {"host": "mail.example", "title": "Compose", "elements": [el(1, "textarea", "Message")]}
    ctl, _, thinkers, _ = make_ctl(plans=[{"op": "type", "target": "Message"}], texts={"Message": "Thanks!"})
    a = ctl.start("go", None, page)
    assert a["value"] == "Thanks!" and "compose" in thinkers[0].calls


def test_thinker_budget_ends_task_as_blocked(make_ctl):
    def always_replan(state, candidates, reason):
        return {"kind": "replan", "subgoals": [{"op": "click", "target": "Nope", "value": None, "irreversible": False}]}

    page = {"host": "x.example", "title": "t", "elements": [el(1, "button", "Nope")]}
    ctl, _, _, _ = make_ctl(plans=[{"op": "click", "target": "Nope"}], script=always_replan)
    a = ctl.start("go", None, page)
    for _ in range(30):
        if a["op"] in ("blocked", "finish"):
            break
        a = ctl.step(a["task"], page, {"ok": False})
    assert a["op"] == "blocked"


def test_a_detour_click_does_not_complete_the_step(make_ctl):
    """Regression: the fallback click on 'Checkout' was counted as finishing 'Add to cart'."""
    page = {"host": "shop.example", "title": "Kettle", "elements": [el(0, "button", "Add to cart"),
                                                                     el(1, "button", "Checkout")]}
    ctl, _, _, _ = make_ctl(plans=[{"op": "click", "target": "Add to cart"}, {"op": "click", "target": "Checkout"}])
    a = ctl.start("go", None, page)
    assert a["index"] == 0 and a["advance"] is True
    a = ctl.step(a["task"], page, {"ok": True, "changed": False})  # nothing happened: try another way
    assert a["index"] == 1 and a["advance"] is False
    task = ctl.tasks[a["task"]]
    assert task.cursor == 0
    a = ctl.step(a["task"], page, {"ok": True, "changed": True})  # the detour worked but the step isn't done
    a = ctl.step(a["task"], page, {"ok": True, "changed": True})  # same detour again: no progress
    assert a["source"] == "thinker" or task.fail_streak >= 1


def test_model_maps_plan_wording_to_labels_and_moves_on(make_ctl):
    """Regression: 'departure city' → the 'From' field was retyped forever because no word matched."""
    ctl, sup, _, _ = make_ctl(plans=[{"op": "type", "target": "departure city", "value": "Zurich"},
                                     {"op": "click", "target": "Search flights"}])
    a = ctl.start("go", None, flights_page())
    assert (a["op"], a["index"], a["source"], a["advance"]) == ("type", 1, "model", True)
    a = ctl.step(a["task"], flights_page(frm="Zurich"), {"ok": True, "changed": True})
    assert (a["op"], a["index"], a["source"]) == ("click", 3, "fastpath")


def test_repeating_the_same_action_brings_in_the_thinker(make_ctl):
    page = {"host": "x.example", "title": "t", "elements": [el(0, "button", "Help"), el(1, "button", "Menu")]}
    only_menu = dict(page, elements=[el(1, "button", "Menu")])
    ctl, _, thinkers, _ = make_ctl(plans=[{"op": "click", "target": "Help"}])
    a = ctl.start("go", None, page)
    tid = a["task"]
    a = ctl.step(tid, only_menu, {"ok": False})  # "Help" failed and vanished: "Menu" is a detour
    assert (a["index"], a["advance"]) == (1, False)
    sources = []
    for _ in range(4):
        a = ctl.step(tid, only_menu, {"ok": True, "changed": True})
        sources.append(a.get("source"))
        if a["op"] != "click" or a["source"] == "thinker":
            break
    assert "thinker" in sources and ctl.tasks[tid].cursor == 0


def test_several_different_detours_bring_in_the_thinker(make_ctl):
    """Review finding: distinct wrong picks never repeated exactly, so the loop guard never fired."""
    ctl, _, thinkers, _ = make_ctl(plans=[{"op": "click", "target": "Help"}])
    page = {"host": "x.example", "title": "t", "elements": [el(0, "button", "Help"), el(1, "button", "Menu")]}
    a = ctl.start("go", None, page)
    tid = a["task"]
    a = ctl.step(tid, page, {"ok": False})  # "Help" failed: later non-matching picks are detours
    sources = []
    for n in range(2, 8):  # each page offers one new, different element
        a = ctl.step(tid, dict(page, elements=[el(n, "button", "Item %d" % n)]), {"ok": True, "changed": True})
        sources.append(a.get("source"))
        if a.get("source") == "thinker":
            break
    assert "thinker" in sources and len(sources) <= 4


def test_browser_act_bar_comes_from_schema_browser(make_sup):
    """The fake model is 0.97 sure. Under a 0.99 act bar a click is only 'confirm', so the thinker decides."""
    sup = make_sup(fake_policy="first")
    t = ScriptedThinker({"go": [{"op": "click", "target": "search button"}]})
    ctl = Controller(sup, lambda: t, schema={"allowed_scripts": ["latin"], "zones": {"act": 0.99, "confirm": 0.6}})
    a = ctl.start("go", None, flights_page())
    assert a["source"] == "thinker" and "resolve" in t.calls
    default = Controller(sup, lambda: ScriptedThinker({"go": [{"op": "click", "target": "search button"}]}))
    assert default.zones["act"] == 0.95 and default.start("go", None, flights_page())["source"] == "model"


def test_card_numbers_never_reach_the_thinker_or_the_log(make_ctl, tmp_path):
    seen = []

    def spy(state, candidates, reason):
        seen.append(json.dumps(candidates))
        return {"kind": "ask_user", "message": "?"}

    page = {"host": "shop.example", "title": "Pay", "elements": [
        el(1, "textbox", "Card number", value="4111 1111 1111 1111"), el(2, "button", "ស្វែងរក")]}
    ctl, _, _, log = make_ctl(plans=[{"op": "click", "target": "search"}], script=spy)
    ctl.start("go", None, page)
    log.flush()
    logged = json.dumps(sqlite3.connect(str(tmp_path / "steps.db")).execute("SELECT * FROM steps").fetchall())
    assert seen and all("4111" not in s for s in seen) and "4111" not in logged


def test_steps_are_logged_for_training(make_ctl, tmp_path):
    ctl, _, _, log = make_ctl(plans=[{"op": "click", "target": "search button"}])
    ctl.start("go", None, flights_page())
    log.flush()
    rows = sqlite3.connect(str(tmp_path / "steps.db")).execute("SELECT source, options, zone FROM steps").fetchall()
    assert rows[0][0] == "model" and "Search flights" in rows[0][1] and rows[0][2] == "act"


def test_agent_routes_over_http(make_ctl):
    ctl, sup, _, _ = make_ctl()
    server = make_server(sup.sup, 0, token="tok", routes=agent_routes(ctl))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def post(path, body):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
        conn.request("POST", path, json.dumps(body), {"Authorization": "Bearer tok"})
        r = conn.getresponse()
        out = r.status, json.loads(r.read())
        conn.close()
        return out

    try:
        code, a = post("/v1/agent/start", {"goal": "go", "page": flights_page()})
        assert code == 200 and a["op"] == "type" and a["plan"][0]["target"] == "From"
        code, b = post("/v1/agent/step", {"task": a["task"], "page": flights_page(frm="Zurich"), "last": {"ok": True}})
        assert code == 200 and b["index"] == 2
        assert post("/v1/agent/step", {"page": {}})[0] == 400
        assert post("/v1/agent/stop", {"task": a["task"]})[1]["existed"] is True
    finally:
        server.shutdown()
        server.server_close()
