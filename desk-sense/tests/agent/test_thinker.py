"""Thinker package: budget, scripted fake, and the Claude provider against a stub client (no network)."""
from types import SimpleNamespace

import pytest

import thinker
from thinker.base import ThinkerError, clean_subgoals
from thinker.budget import Budgeted, BudgetExhausted
from thinker.fake import ScriptedThinker

CANDS = [{"i": 4, "role": "button", "name": "Search"}, {"i": 9, "role": "link", "name": "Help"}]


def test_clean_subgoals_drops_malformed():
    raw = [{"op": "type", "target": "From", "value": 7}, {"op": "hack"}, "x", {"op": "done"}]
    assert clean_subgoals(raw) == [{"op": "type", "target": "From", "value": "7", "irreversible": False},
                                   {"op": "done", "target": "", "value": None, "irreversible": False}]


def test_budget_caps_each_kind():
    t = Budgeted(ScriptedThinker(), {"resolve": 2})
    t.plan("g", {})
    with pytest.raises(BudgetExhausted):
        t.plan("g", {})
    t.resolve("s", CANDS, "flag")
    t.resolve("s", CANDS, "flag")
    with pytest.raises(BudgetExhausted):
        t.resolve("s", CANDS, "flag")


def test_fake_thinker_is_deterministic():
    t = thinker.make("fake", plans={"g": [{"op": "click", "target": "Search"}]}, texts={"Message": "hi"})
    assert t.plan("g", {})[0]["target"] == "Search"
    assert t.resolve("s", CANDS, "flag")["index"] == 4
    assert t.resolve("s", [], "flag")["kind"] == "ask_user"
    assert t.compose({"name": "Message"}, "") == "hi"


def test_unknown_thinker():
    with pytest.raises(ValueError):
        thinker.make("nope")


class StubMessages:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.parsed, self.stop_reason, self.calls = parsed, stop_reason, []

    def parse(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=self.parsed)


def claude(parsed, stop_reason="end_turn", **kw):
    from thinker.anthropic_provider import ClaudeThinker

    msgs = StubMessages(parsed, stop_reason)
    return ClaudeThinker(client=SimpleNamespace(messages=msgs), **kw), msgs


def test_claude_defaults_to_haiku_without_effort(monkeypatch):
    monkeypatch.delenv("THINKER_MODEL", raising=False)
    from thinker.anthropic_provider import Plan, Subgoal

    t, msgs = claude(Plan(subgoals=[Subgoal(op="type", target="From", value="Zurich")]))
    plan = t.plan("fly from Zurich", {"host": "f.example", "title": "Flights", "elements": CANDS})
    assert plan == [{"op": "type", "target": "From", "value": "Zurich", "irreversible": False}]
    call = msgs.calls[0]
    assert call["model"] == "claude-haiku-4-5" and "output_config" not in call
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "<page_data>" in call["messages"][0]["content"]


def test_claude_bigger_model_runs_at_low_effort(monkeypatch):
    monkeypatch.delenv("THINKER_EFFORT", raising=False)
    from thinker.anthropic_provider import Composed

    t, msgs = claude(Composed(text="Hello"), model="claude-sonnet-5")
    assert t.compose({"name": "Message", "role": "textbox"}, "reply politely") == "Hello"
    assert msgs.calls[0]["output_config"] == {"effort": "low"}


def test_claude_resolve_only_accepts_offered_elements():
    from thinker.anthropic_provider import Resolution

    t, _ = claude(Resolution(kind="pick", index=4))
    assert t.resolve("state", CANDS, "flag")["index"] == 4
    t, _ = claude(Resolution(kind="pick", index=99))
    with pytest.raises(ThinkerError):
        t.resolve("state", CANDS, "flag")


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_claude_bad_stops_raise(stop_reason):
    from thinker.anthropic_provider import Composed

    t, _ = claude(Composed(text="x"), stop_reason)
    with pytest.raises(ThinkerError):
        t.compose({"name": "f"}, "")
