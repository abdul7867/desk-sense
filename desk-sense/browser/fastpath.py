"""Steps obvious enough to skip the model entirely. Each rule must be certain, not just likely:
a wrong fast path costs more than the ~0.1-0.5 s of model time it saves."""
from browser.question import op_for
from browser.rank import usable, words


def _norm(text):
    return " ".join(sorted(words(text)))


def decide(elements, subgoal, page, failed=()):
    """An action dict, or None to fall through to the model. Elements that already failed on this
    step are never fast-pathed again."""
    elements = [el for el in elements if el["i"] not in failed]
    if page.get("busy"):
        return {"op": "wait", "why": "page busy"}
    if not subgoal:
        return None
    op, target = subgoal.get("op"), _norm(subgoal.get("target"))
    if op in ("scroll", "wait", "done"):
        return {"op": op, "why": "planned move"}
    if not target:
        return None
    exact = [el for el in elements if usable(el) and op_for(el) == op and _norm(el.get("name")) == target]
    if len(exact) != 1:
        exact = [el for el in exact if el.get("region") == "dialog"] if exact else []
    if len(exact) == 1:
        el = exact[0]
        if op == "type" and subgoal.get("value") is not None and (el.get("value") or "") == subgoal["value"]:
            return {"op": "skip", "index": el["i"], "why": "field already holds the value"}
        return {"op": op, "index": el["i"], "value": subgoal.get("value"), "why": "exact name match"}
    if op in ("click", "select"):
        want = words(subgoal.get("target"))
        fresh = [el for el in elements if usable(el) and el.get("new") and el.get("role") in ("option", "menuitem")]
        sugg = [el for el in fresh if want <= words(el.get("name"))]
        if len(sugg) == 1:
            return {"op": "click", "index": sugg[0]["i"], "why": "single matching suggestion"}
        # A suggestion list that just appeared: "Heathrow" -> "London Heathrow (LHR)". Only when one
        # suggestion shares strictly more of the target's words than any other.
        if want and fresh:
            scored = sorted(((len(want & words(el.get("name"))), el) for el in fresh), key=lambda x: -x[0])
            if scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] > scored[1][0]):
                return {"op": "click", "index": scored[0][1]["i"], "why": "best matching new suggestion"}
    want = words(subgoal.get("target"))
    if want and page.get("more_below") and not any(
            want <= (words(el.get("name")) | words(el.get("placeholder"))) for el in elements if usable(el)):
        return {"op": "scroll", "why": "target not on screen yet"}  # cheap and reversible, unlike a wrong click
    return None
