"""Deterministic shortlist: the model only ever sees the top SHORTLIST elements, so the options fit
the head budget and nothing is cut silently. Cheap: plain word overlap, no model."""
import unicodedata

from browser.question import op_for

SHORTLIST = 12


def words(text):
    """Letters, combining marks and digits form words. Plain `\\w` splits Devanagari at vowel signs."""
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    out, cur = set(), []
    for ch in text + " ":
        if unicodedata.category(ch)[0] in ("L", "M", "N"):
            cur.append(ch)
        elif cur:
            w = "".join(cur)
            if len(w) > 1 or w.isdigit():
                out.add(w)
            cur = []
    return out


def score(el, subgoal, failed=()):
    want = words(subgoal.get("target")) | words(subgoal.get("value")) if subgoal else set()
    have = words(el.get("name")) | words(el.get("value")) | words(el.get("placeholder"))
    s = 0.0
    if want and have:
        overlap = len(want & have)
        s += 3.0 * overlap / len(want) + 1.0 * overlap / len(have)
    if subgoal and op_for(el) == subgoal.get("op"):
        s += 1.0
    if el.get("region") == "dialog":
        s += 0.5
    if el.get("new"):
        s += 0.3
    if el["i"] in failed:
        s -= 5.0
    return s


def usable(el):
    return not el.get("disabled") and el.get("type") != "hidden"


def rank(elements, subgoal, failed=()):
    """Best first; ties keep page order, which is reading order."""
    pool = [el for el in elements if usable(el)]
    return sorted(pool, key=lambda el: -score(el, subgoal, failed))


def shortlist(elements, subgoal, failed=(), page=0, k=SHORTLIST):
    ranked = rank(elements, subgoal, failed)
    return ranked[page * k: (page + 1) * k]
