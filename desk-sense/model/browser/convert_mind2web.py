"""Mind2Web (CC-BY-4.0; the authors ask for research use) -> browser-step training rows.

Each Mind2Web step becomes the exact question the engine asks at run time: the element table is
rebuilt from the step's candidates and cleaned HTML, shortlisted by `browser.rank`, and turned into
one Choice question by `browser.question`. So training and serving see the same text.

    python -m model.browser.convert_mind2web data/raw/mind2web/train_*.json --out data/browser/mind2web.jsonl

The planner's wording of each step is not in Mind2Web, so it is varied per step (seeded):
exact element name, a partial one, or none at all (only the goal and history).
"""
import argparse
import json
import random
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from browser import question, rank  # noqa: E402

TEXT_INPUTS = {"text", "email", "search", "tel", "url", "number", "password", "date", ""}
REGIONS = {"header", "nav", "footer", "main", "form", "aside"}
OPS = {"CLICK": "click", "TYPE": "type", "SELECT": "select", "HOVER": "click", "ENTER": "click"}
NAME_MAX = 80


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent, self.children, self.text = tag, attrs, parent, [], []


class Tree(HTMLParser):
    """Mind2Web's cleaned HTML: every element has backend_node_id; visible text sits in <text>."""

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.cur, self.by_id = self.root, {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        n = Node(tag, dict(attrs), self.cur)
        self.cur.children.append(n)
        if "backend_node_id" in n.attrs:
            self.by_id[n.attrs["backend_node_id"]] = n
        self.cur = n

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        if data.strip():
            self.cur.text.append(data.strip())


def squash(s):
    return " ".join(str(s or "").split())[:NAME_MAX]


def own_text(n, skip=("option",)):
    out = list(n.text)
    for c in n.children:
        if c.tag not in skip:
            out.append(own_text(c, skip))
    return " ".join(t for t in out if t)


def label_near(n):
    """A <label> in the element's nearest ancestors, the way a form lays it out."""
    p, hops = n.parent, 0
    while p is not None and hops < 3:
        for c in p.children:
            if c.tag == "label" and c is not n:
                t = squash(own_text(c))
                if t:
                    return t
        p, hops = p.parent, hops + 1
    return ""


def role_of(tag, a):
    if a.get("role"):
        return a["role"]
    if tag == "a":
        return "link"
    if tag in ("select", "textarea", "option"):
        return tag
    if tag == "input":
        t = (a.get("type") or "").lower()
        if t in ("checkbox", "radio"):
            return t
        if t == "search":
            return "searchbox"
        return "textbox" if t in TEXT_INPUTS else "button"
    return "button"


def element(cand, tree):
    a = json.loads(cand["attributes"])
    n = tree.by_id.get(cand["backend_node_id"])
    tag = cand["tag"]
    role = role_of(tag, a)
    text = squash(own_text(n)) if n is not None else ""
    name = squash(a.get("aria_label") or a.get("placeholder") or a.get("title") or a.get("alt") or text
                  or (label_near(n) if n is not None else "") or (a.get("value") if role == "button" else ""))
    if role in ("textbox", "searchbox", "textarea", "select", "combobox") and n is not None:
        name = squash(a.get("aria_label") or label_near(n) or a.get("placeholder") or a.get("title") or name)
    value = ""
    if a.get("type") == "password":
        value = "(filled)" if a.get("input_value") else ""
    elif role in ("checkbox", "radio"):
        value = "checked" if a.get("input_checked") == "true" else "unchecked"
    elif tag == "select" and n is not None:
        sel = [c for c in n.children if c.tag == "option" and c.attrs.get("option_selected") == "true"]
        value = squash(own_text(sel[0])) if sel else ""
    elif role in ("textbox", "searchbox", "textarea", "combobox"):
        value = squash(a.get("input_value") or "")
    region = ""
    p = n.parent if n is not None else None
    while p is not None:
        if p.attrs.get("role") in ("dialog", "alertdialog") or p.attrs.get("aria_modal") == "true":
            region = "dialog"
            break
        if p.tag in REGIONS and not region:
            region = p.tag
        p = p.parent
    try:
        x, y = [float(v) for v in a.get("bounding_box_rect", "0,0,0,0").split(",")[:2]]
    except ValueError:
        x = y = 0.0
    return {"role": role, "name": name, "value": value, "region": region, "_y": y, "_x": x,
            "_id": cand["backend_node_id"]}


def history_line(repr_):
    """'[combobox]  Reservation type -> SELECT: Pickup' -> 'select Reservation type "Pickup"'."""
    left, _, right = repr_.partition("->")
    name = squash(left.split("]", 1)[-1])
    op, _, value = right.strip().partition(":")
    text = "%s %s" % (OPS.get(op.strip(), "click"), name)
    return text + (' "%s"' % squash(value) if value.strip() else "")


def subgoal_for(op, value, target_el, rng):
    """The planner's wording is unknown: vary it so the model learns to map words to labels."""
    words = target_el["name"].split()
    mode = rng.choices(["exact", "partial", "none"], weights=[3, 4, 3])[0]
    if mode == "exact" or (mode == "partial" and len(words) < 2):
        target = target_el["name"]
    elif mode == "partial":
        keep = rng.sample(words, rng.randint(1, len(words) - 1))
        target = " ".join(w for w in words if w in keep).lower()
    else:
        target = ""
    return mode, {"op": op, "target": target, "value": value or None}


def convert_task(task, rng_seed):
    rows, stats = [], {"steps": 0, "in_shortlist": 0, "rank": []}
    reprs = task["action_reprs"]
    for k, act in enumerate(task["actions"]):
        stats["steps"] += 1
        tree = Tree(act["cleaned_html"])
        cands = act["pos_candidates"][:1] + act["neg_candidates"]
        if not act["pos_candidates"]:
            continue
        els = [element(c, tree) for c in cands]
        els = [e for e in els if e["name"] or e["role"] in ("textbox", "searchbox", "textarea", "select")]
        els.sort(key=lambda e: (round(e["_y"] / 10), e["_x"]))  # reading order
        pos_id = act["pos_candidates"][0]["backend_node_id"]
        for i, e in enumerate(els):
            e["i"] = i
        pos = next((e for e in els if e["_id"] == pos_id), None)
        if pos is None:
            continue
        rng = random.Random("%s-%s" % (rng_seed, act["action_uid"]))
        op = OPS.get(act["operation"]["op"], "click")
        mode, sub = subgoal_for(op, act["operation"].get("value"), pos, rng)
        public = [{k2: v for k2, v in e.items() if not k2.startswith("_")} for e in els]
        ranked = rank.rank(public, sub)
        r = next(j for j, e in enumerate(ranked) if e["i"] == pos["i"])
        stats["rank"].append(r)
        short = ranked[: rank.SHORTLIST]
        label = str(pos["i"]) if r < rank.SHORTLIST else "none_of_these"
        stats["in_shortlist"] += r < rank.SHORTLIST
        title = next((squash(own_text(n)) for n in tree.by_id.values() if n.tag == "title"), "")
        page = {"host": task["website"], "title": title, "dialog": any(e["region"] == "dialog" for e in short)}
        history = [history_line(x) for x in reprs[:k]]
        rows.append({
            "id": act["action_uid"], "language": "en", "group": task["website"], "stratum": task["domain"],
            "state": question.build_state(task["confirmed_task"], sub, history, page),
            "questions": {"next": question.build_question(short)}, "labels": {"next": label},
            "meta": {"target_mode": mode, "pos_rank": r, "candidates": len(els), "op": op},
        })
    return rows, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", default="m2w-1")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    total = {"tasks": 0, "steps": 0, "rows": 0, "in_shortlist": 0, "rank": []}
    with open(args.out, "w", encoding="utf-8") as f:
        for path in args.inputs:
            for task in json.loads(path.read_text(encoding="utf-8")):
                rows, st = convert_task(task, args.seed)
                total["tasks"] += 1
                total["steps"] += st["steps"]
                total["in_shortlist"] += st["in_shortlist"]
                total["rank"] += st["rank"]
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                total["rows"] += len(rows)
            print("%s: %d tasks, %d rows so far" % (path.name, total["tasks"], total["rows"]), flush=True)
    ranks = sorted(total.pop("rank"))
    total["shortlist_recall"] = round(total["in_shortlist"] / max(1, total["rows"]), 4)
    total["median_rank"] = ranks[len(ranks) // 2] if ranks else None
    print(json.dumps(total, indent=2))
    (args.out.with_suffix(".stats.json")).write_text(json.dumps(total, indent=2) + "\n")


if __name__ == "__main__":
    main()
