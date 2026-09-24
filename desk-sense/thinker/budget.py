"""Per-task cap on thinker calls, so a confused page cannot turn into an expensive loop."""
from thinker.base import Thinker, ThinkerError

DEFAULT_LIMITS = {"plan": 1, "resolve": 4, "compose": 3}


class BudgetExhausted(ThinkerError):
    pass


class Budgeted(Thinker):
    def __init__(self, inner, limits=None):
        self.inner, self.name = inner, inner.name
        self.limits = dict(DEFAULT_LIMITS, **(limits or {}))
        self.used = {k: 0 for k in self.limits}

    def _take(self, kind):
        if self.used[kind] >= self.limits[kind]:
            raise BudgetExhausted("thinker %s budget used up (%d)" % (kind, self.limits[kind]))
        self.used[kind] += 1

    def plan(self, goal, page):
        self._take("plan")
        return self.inner.plan(goal, page)

    def resolve(self, state, candidates, reason):
        self._take("resolve")
        return self.inner.resolve(state, candidates, reason)

    def compose(self, field, context):
        self._take("compose")
        return self.inner.compose(field, context)
