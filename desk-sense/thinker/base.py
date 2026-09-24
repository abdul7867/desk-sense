"""The "System Two" side of the browser agent: slow, rare calls that plan, write text, and take over
hard steps. The local model makes every routine decision; a thinker is called about twice per task.

Providers implement Thinker. Plain dicts cross the interface so the engine never depends on a
provider's SDK:
    subgoal    {"op": "click|type|select|scroll|wait|done", "target": str, "value": str|None, "irreversible": bool}
    resolution {"kind": "pick|replan|ask_user", "index": int|None, "value": str|None,
                "subgoals": [subgoal]|None, "message": str}
"""
OPS = ("click", "type", "select", "scroll", "wait", "done")


class ThinkerError(RuntimeError):
    """The provider failed (network, refusal, bad output). The controller stops the task as blocked."""


class Thinker:
    name = "base"

    def plan(self, goal, page):
        """-> list of subgoals for `goal`, starting from `page` ({host, title, elements})."""
        raise NotImplementedError

    def resolve(self, state, candidates, reason):
        """-> resolution for a step the local model could not settle (`reason`: flag, blocked, failed)."""
        raise NotImplementedError

    def compose(self, field, context):
        """-> text to type into `field` ({name, role}); `context` is the goal and current subgoal."""
        raise NotImplementedError


def clean_subgoals(raw):
    """Keep only well-formed subgoals; a provider's output is untrusted until checked."""
    out = []
    for s in raw or []:
        if not isinstance(s, dict) or s.get("op") not in OPS:
            continue
        value = s.get("value")
        out.append({"op": s["op"], "target": str(s.get("target") or ""),
                    "value": None if value is None else str(value), "irreversible": bool(s.get("irreversible"))})
    return out
