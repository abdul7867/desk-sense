"""Scripted thinker for tests and offline benchmarks: no network, fully deterministic."""
from thinker.base import Thinker, clean_subgoals


class ScriptedThinker(Thinker):
    """`plans`: {goal: [subgoal, ...]}. Resolve picks the first candidate (the ranker's best), or
    asks the person when there is none. Compose returns `texts[field name]`."""
    name = "fake"

    def __init__(self, plans=None, texts=None):
        self.plans, self.texts = dict(plans or {}), dict(texts or {})
        self.calls = []

    def plan(self, goal, page):
        self.calls.append("plan")
        return clean_subgoals(self.plans.get(goal, [{"op": "done", "target": ""}]))

    def resolve(self, state, candidates, reason):
        self.calls.append("resolve")
        if not candidates:
            return {"kind": "ask_user", "index": None, "value": None, "subgoals": None,
                    "message": "I can't find a way forward on this page (%s)." % reason}
        return {"kind": "pick", "index": candidates[0]["i"], "value": None, "subgoals": None, "message": ""}

    def compose(self, field, context):
        self.calls.append("compose")
        return self.texts.get(field.get("name"), "")
