"""Browser decision core: question, shortlist, fast paths, safety. Pure Python, no model."""
import pytest

from app.runtime import OptionsTooLong, build_sequence
from browser import fastpath, question, rank, safety


def el(i, role, name, **kw):
    return {"i": i, "role": role, "name": name, **kw}


PAGE = {"host": "flights.example", "title": "Find flights"}
TABLE = [
    el(0, "link", "Home", region="header"),
    el(1, "textbox", "From", value=""),
    el(2, "textbox", "To", value=""),
    el(3, "button", "Search flights"),
    el(4, "button", "Search hotels"),
    el(5, "link", "Help", region="footer"),
]


def test_question_offers_elements_plus_fixed_moves():
    q = question.build_question(TABLE[:3])
    assert q["type"] == "choice"
    assert list(q["criteria"])[:3] == ["0", "1", "2"]
    assert {"scroll_down", "done", "none_of_these"} <= set(q["criteria"])
    assert q["criteria"]["1"] == "type textbox From empty"


def test_duplicate_names_stay_separate_options():
    q = question.build_question([el(1, "button", "Search"), el(2, "button", "Search")])
    assert q["criteria"]["1"] == q["criteria"]["2"] and len(q["criteria"]) == 2 + len(question.FIXED_MOVES)


def test_labels_are_capped():
    long = el(9, "button", "x" * 500, value="y" * 500, region="dialog", new=True)
    assert len(question.label(long)) <= question.LABEL_CHARS


def test_state_keeps_goal_and_recent_history():
    s = question.build_state("book a flight to London", {"op": "type", "target": "To", "value": "London"},
                             ["a1", "a2", "a3", "a4"], dict(PAGE, dialog=True))
    assert s.startswith("goal: book a flight to London")
    assert 'now: type To ← "London"' in s and "a1" not in s and "a4" in s and "dialog open" in s
    assert "done:" not in question.build_state("g", None, ["a"], PAGE, max_history=0)


def test_shortlist_puts_the_planned_target_first():
    top = rank.shortlist(TABLE, {"op": "click", "target": "Search flights"})
    assert top[0]["i"] == 3
    assert rank.shortlist(TABLE, {"op": "type", "target": "To", "value": "London"})[0]["i"] == 2


def test_shortlist_pages_and_skips_disabled_and_failed():
    many = [el(i, "button", "item %d" % i) for i in range(30)] + [el(99, "button", "Go", disabled=True)]
    first, second = rank.shortlist(many, None), rank.shortlist(many, None, page=1)
    assert len(first) == rank.SHORTLIST and not {e["i"] for e in first} & {e["i"] for e in second}
    assert all(e["i"] != 99 for e in rank.rank(many, None))
    assert rank.shortlist(TABLE, {"op": "click", "target": "Search flights"}, failed={3})[0]["i"] != 3


def test_shortlist_drops_identical_labels():
    dup = [el(1, "button", "Boston NY"), el(2, "button", "Boston NY"), el(3, "button", "Boston MA"),
           el(4, "button", "Boston NY", region="dialog")]
    ids = [e["i"] for e in rank.shortlist(dup, {"op": "click", "target": "Boston NY"})]
    assert ids.count(1) + ids.count(2) == 1 and 4 in ids and 3 in ids  # a dialog copy is a different option


def test_words_keep_devanagari_whole():
    assert rank.words("अभी खरीदें!") == {"अभी", "खरीदें"}


def test_fastpath_exact_match_and_already_filled():
    a = fastpath.decide(TABLE, {"op": "type", "target": "from", "value": "Zurich"}, PAGE)
    assert a == {"op": "type", "index": 1, "value": "Zurich", "why": "exact name match"}
    filled = [dict(TABLE[1], value="Zurich")]
    assert fastpath.decide(filled, {"op": "type", "target": "From", "value": "Zurich"}, PAGE)["op"] == "skip"


def test_fastpath_falls_through_when_unsure():
    assert fastpath.decide(TABLE, {"op": "click", "target": "Search"}, PAGE) is None  # two partial matches
    dup = [el(1, "button", "Next"), el(2, "button", "Next")]
    assert fastpath.decide(dup, {"op": "click", "target": "Next"}, PAGE) is None
    assert fastpath.decide(TABLE, None, PAGE) is None


def test_fastpath_waits_and_picks_single_suggestion():
    assert fastpath.decide(TABLE, None, dict(PAGE, busy=True))["op"] == "wait"
    sugg = TABLE + [el(7, "option", "London Heathrow (LHR)", new=True), el(8, "option", "Paris (CDG)", new=True)]
    assert fastpath.decide(sugg, {"op": "click", "target": "London"}, PAGE)["index"] == 7


def test_fastpath_scrolls_when_target_is_off_screen():
    sub = {"op": "click", "target": "Pune office"}
    assert fastpath.decide(TABLE, sub, dict(PAGE, more_below=True))["op"] == "scroll"
    assert fastpath.decide(TABLE, sub, PAGE) is None  # bottom of the page: let the model judge wording
    assert fastpath.decide(TABLE, {"op": "click", "target": "Search"}, dict(PAGE, more_below=True)) is None


def test_empty_fields_rank_first_for_typing_when_the_label_does_not_match():
    table = [el(1, "textbox", "From", value="Zurich (ZRH)"), el(2, "textbox", "To", value="")]
    assert rank.shortlist(table, {"op": "type", "target": "destination", "value": "London"})[0]["i"] == 2
    # a matching label still wins over emptiness
    table = [el(1, "textbox", "From", value="Zurich"), el(2, "textbox", "Notes", value="")]
    assert rank.shortlist(table, {"op": "type", "target": "From", "value": "Basel"})[0]["i"] == 1


def test_fastpath_picks_best_new_suggestion_only_when_unambiguous():
    sugg = TABLE + [el(7, "option", "London Heathrow (LHR)", new=True), el(8, "option", "London Gatwick (LGW)", new=True)]
    assert fastpath.decide(sugg, {"op": "click", "target": "Heathrow"}, PAGE)["index"] == 7
    assert fastpath.decide(sugg, {"op": "click", "target": "London airport"}, PAGE) is None  # tie: model decides
    zrh = TABLE + [el(9, "option", "Zurich (ZRH)", new=True), el(10, "option", "Zagreb (ZAG)", new=True)]
    assert fastpath.decide(zrh, {"op": "click", "target": "Zurich airport"}, PAGE)["index"] == 9
    old = TABLE + [el(11, "option", "London Heathrow (LHR)")]  # not new: not a suggestion list
    assert fastpath.decide(old, {"op": "click", "target": "Heathrow"}, PAGE) is None


def test_dialog_breaks_a_tie():
    dup = [el(1, "button", "Accept"), el(2, "button", "Accept", region="dialog")]
    assert fastpath.decide(dup, {"op": "click", "target": "Accept"}, PAGE)["index"] == 2


@pytest.mark.parametrize("element, action, sub, expect", [
    (el(1, "button", "Place order"), "click", None, "buys"),
    (el(1, "button", "अभी खरीदें"), "click", None, "buys"),
    (el(1, "button", "Delete account"), "click", None, "buys"),
    (el(1, "textbox", "Password", type="password"), "type", None, "password"),
    (el(1, "textbox", "Card number"), "type", None, "card"),
    (el(1, "button", "Next", type="submit", form_host="evil.example"), "click", None, "another site"),
    (el(1, "button", "Next"), "click", {"irreversible": True}, "irreversible"),
    (el(1, "select", "Bulk action"), ("select", "Delete selected"), None, "buys"),
    (el(1, "select", "Card expiry month"), ("select", "04"), None, "card"),
    (el(1, "textbox", "Code", autocomplete="one-time-code"), "type", None, "card"),
])
def test_risky_actions_need_confirmation(element, action, sub, expect):
    op, value = action if isinstance(action, tuple) else (action, None)
    assert expect in safety.risky({"op": op, "value": value}, element, sub, PAGE)


def test_ordinary_select_passes():
    assert safety.risky({"op": "select", "value": "Hindi"}, el(1, "select", "Language"), None, PAGE) is None


def test_redact_masks_secrets_only():
    page = dict(PAGE, elements=[el(1, "textbox", "Card number", value="4111 1111 1111 1111"),
                                el(2, "textbox", "OTP", value="123456"),
                                el(3, "textbox", "Security code", autocomplete="cc-csc", value="999"),
                                el(4, "textbox", "Password", type="password", value=""),
                                el(5, "textbox", "City", value="Pune")])
    values = [e["value"] for e in safety.redact(page)["elements"]]
    assert values == ["(filled)", "(filled)", "(filled)", "", "Pune"]
    assert page["elements"][0]["value"] == "4111 1111 1111 1111"  # the caller's copy is untouched


@pytest.mark.parametrize("element, action", [
    (el(1, "button", "Search flights"), "click"),
    (el(1, "textbox", "From"), "type"),
    (el(1, "button", "Next", type="submit", form_host="flights.example"), "click"),
])
def test_ordinary_actions_pass(element, action):
    assert safety.risky({"op": action}, element, None, PAGE) is None


def test_site_allowlist():
    assert safety.site_allowed("www.flights.example", ["flights.example"])
    assert not safety.site_allowed("flights.example.evil.com", ["flights.example"])
    assert not safety.site_allowed("notflights.example", ["flights.example"])


class StubEncoder:
    """One token per character, enough to exercise the head budget."""
    cls_id, sep_id, mask_id, pad_id, mask_token = 1, 2, 3, 0, "[MASK]"

    def ids(self, text):
        return [10 + (ord(c) % 50) for c in text]


def test_strict_refuses_instead_of_cutting_options():
    q = {"t": "choice", "ins": "pick", "crit": {"a" * 30: None, "b" * 30: None, "c" * 30: None}}
    ids, markers, _, _ = build_sequence(StubEncoder(), "state", q, 256, 64)  # tickets: laya cuts silently
    assert len(markers) == 3
    with pytest.raises(OptionsTooLong):
        build_sequence(StubEncoder(), "state", q, 256, 64, strict=True)
    short = {"t": "choice", "ins": "pick", "crit": {"a": None, "b": None}}
    assert len(build_sequence(StubEncoder(), "state", short, 256, 64, strict=True)[1]) == 2


@pytest.mark.parametrize("name, risky_expected", [
    ("Place order", True), ("Place your order", True), ("Order now", True), ("Confirm order", True),
    ("Order", True), ("Order for ₹499", True), ("order (2 items)", True),
    ("Open order 4817", False), ("Sort order", False), ("Track your order", False),
])
def test_order_is_risky_only_as_a_purchase(name, risky_expected):
    assert (safety.risky({"op": "click"}, el(1, "button", name), None, PAGE) is not None) is risky_expected


def test_typing_ignores_what_fields_already_contain():
    """Regression: a message body went into Subject because Subject held 'Report ready'."""
    table = [el(1, "textbox", "To", value="ravi@example.com"), el(2, "textbox", "Subject", value="Report ready"),
             el(3, "textarea", "Message", value="")]
    sub = {"op": "type", "target": "body", "value": "Hi Ravi, the report is ready."}
    assert rank.shortlist(table, sub)[0]["i"] == 3
