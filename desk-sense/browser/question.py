"""One Choice question per step: which of the shortlisted elements (or a fixed move) comes next.

An element is a dict from the extension's table:
    {"i": 7, "role": "button", "name": "Search flights", "value": "", "region": "dialog", "new": true,
     "type": "submit", "form_host": "example.com"}
A subgoal comes from the thinker's plan:
    {"op": "type", "target": "From", "value": "Zurich", "irreversible": false}
"""
import re

TYPE_ROLES = {"textbox", "searchbox", "textarea", "combobox"}
SELECT_ROLES = {"select", "listbox"}
FIXED_MOVES = {
    "scroll_down": "scroll down to see more",
    "scroll_up": "scroll up",
    "wait": "wait, the page is still loading",
    "done": "the current step is already complete",
    "none_of_these": "none of these elements fits",
}
NAME_CHARS = 40
LABEL_CHARS = 60
INSTRUCTIONS = "Which action moves the task forward right now?"


def clean(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def op_for(el):
    if el.get("role") in TYPE_ROLES:
        return "type"
    if el.get("role") in SELECT_ROLES:
        return "select"
    return "click"


def label(el):
    """What the model sees for one element: action, role, name, and where it is."""
    parts = [op_for(el), el.get("role", "element"), clean(el.get("name"), NAME_CHARS) or "(no name)"]
    if el.get("value"):
        parts.append("= " + clean(el["value"], 16))
    elif op_for(el) == "type":
        parts.append("empty")
    if el.get("region") == "dialog":
        parts.append("· dialog")
    if el.get("new"):
        parts.append("· new")
    return clean(" ".join(parts), LABEL_CHARS)


def build_question(candidates):
    criteria = {str(el["i"]): label(el) for el in candidates}
    criteria.update(FIXED_MOVES)
    return {"type": "choice", "instructions": INSTRUCTIONS, "criteria": criteria}


def describe_subgoal(sub):
    if not sub:
        return "finish the task"
    text = "%s %s" % (sub.get("op", "click"), clean(sub.get("target"), 60))
    if sub.get("value"):
        text += ' ← "%s"' % clean(sub["value"], 60)
    return text


def build_state(goal, subgoal, history, page, max_history=3):
    """Compact text the model reads. Roughly 100 tokens; the worker still refuses anything that does
    not fit (too_long) and the controller then retries with less history. The goal is never cut."""
    lines = ["goal: " + clean(goal, 300), "now: " + describe_subgoal(subgoal)]
    recent = history[-max_history:] if max_history else []
    if recent:
        lines.append("done: " + "; ".join(clean(h, 60) for h in recent))
    page_line = "page: %s · %s" % (clean(page.get("host"), 60), clean(page.get("title"), 80))
    if page.get("dialog"):
        page_line += " · dialog open"
    lines.append(page_line)
    return "\n".join(lines)
