"""One task = a plan from the thinker, then one fast decision per page step.

Order per step: allowlist → fast path (no model) → shortlist + one local-model question → thinker only
when the model is unsure, the step failed twice, or text must be written. Every action, whoever chose
it, goes through the safety check; risky ones come back with `confirm` set and the extension asks
the person before doing them.

Actions returned to the extension:
    click / type / select   {"op", "index", "value"?}
    scroll                  {"op": "scroll", "direction": "down" | "up"}
    wait
    finish / stop / pause / ask_user / blocked / refused    (the task ends or needs the person)
"""
import itertools
import threading

from app import guard
from browser import fastpath, question, rank, safety
from thinker.base import ThinkerError
from thinker.budget import Budgeted

MAX_RECURSION = 4
ACTING_OPS = ("click", "type", "select")


class Task:
    def __init__(self, tid, goal, sites, thinker):
        self.id, self.goal, self.sites, self.thinker = tid, goal, list(sites), thinker
        self.subgoals, self.cursor = [], 0
        self.history, self.failed = [], set()
        self.fail_streak, self.page_offset = 0, 0
        self.last, self.n, self.over = None, 0, False
        self.lock = threading.Lock()

    @property
    def subgoal(self):
        return self.subgoals[self.cursor] if self.cursor < len(self.subgoals) else None

    def advance(self, note):
        self.history.append(note)
        self.cursor += 1
        self.fail_streak, self.page_offset = 0, 0
        self.failed.clear()


def describe(a):
    text = "%s #%s" % (a["op"], a.get("index"))
    if a.get("name"):
        text += " %s" % a["name"]
    if a.get("value"):
        text += ' "%s"' % a["value"]
    return text


class Controller:
    def __init__(self, sup, thinker_factory, steplog=None, allowed_scripts=("latin", "devanagari")):
        self.sup, self.thinker_factory, self.steplog = sup, thinker_factory, steplog
        self.allowed = tuple(allowed_scripts)
        self.tasks, self._ids, self._lock = {}, itertools.count(1), threading.Lock()

    # public -------------------------------------------------------------------

    def start(self, goal, sites, page):
        page = safety.redact(page)
        g = guard.check_fields([goal], self.allowed)
        if not g.ok:
            return {"op": "refused", "why": g.message}
        sites = [s.lower() for s in (sites or [])] or [page.get("host", "").lower()]
        if not safety.site_allowed(page.get("host"), sites):
            return {"op": "pause", "why": "this site is not on the task's list", "host": page.get("host")}
        threading.Thread(target=self.sup.warm, daemon=True).start()  # overlaps the worker's cold start with planning
        with self._lock:
            tid = "t%d" % next(self._ids)
        task = Task(tid, goal, sites, Budgeted(self.thinker_factory()))
        try:
            task.subgoals = task.thinker.plan(goal, page)
        except ThinkerError as e:
            return {"task": tid, "op": "blocked", "why": "could not plan the task: %s" % e}
        if not task.subgoals:
            return {"task": tid, "op": "blocked", "why": "the planner returned no steps"}
        with self._lock:
            self.tasks[tid] = task
        with task.lock:
            action = self._next(task, page)
        return dict(action, task=tid, plan=task.subgoals)

    def step(self, tid, page, last=None):
        page = safety.redact(page)
        with self._lock:
            task = self.tasks.get(tid)
        if task is None:
            return {"op": "blocked", "why": "unknown task %r" % tid}
        with task.lock:
            if task.over:
                return {"op": "finish", "why": "task already ended", "source": "engine"}
            if last and last.get("declined"):
                return self._end(task, {"op": "stop", "why": "you declined the action", "source": "engine"})
            self._absorb(task, last or {})
            return dict(self._next(task, page), task=tid)

    def stop(self, tid):
        with self._lock:
            task = self.tasks.pop(tid, None)
        if task is not None:
            with task.lock:
                task.over = True
        return {"op": "stop", "task": tid, "existed": task is not None}

    # step logic ---------------------------------------------------------------

    def _absorb(self, task, last):
        """Learn from the previous action's outcome, reported by the extension."""
        prev, task.last = task.last, None
        if not prev:
            return
        if prev["op"] in ACTING_OPS:
            ok = last.get("ok") and (last.get("changed") or prev["op"] != "click")
            repeat = task.history and task.history[-1] == describe(prev)
            if ok and prev.get("advance"):
                task.fail_streak = 0
                task.advance(describe(prev))
            elif ok and not repeat:
                task.fail_streak = 0
                task.history.append(describe(prev))
            elif ok:  # the same detour again: no progress, so it counts as a failure
                task.failed.add(prev.get("index"))
                task.fail_streak += 1
            else:
                task.failed.add(prev.get("index"))
                task.fail_streak += 1
        else:
            if prev["op"] == "scroll":
                task.page_offset = 0
            if prev.get("advance"):
                task.advance(describe(prev))

    def _next(self, task, page, depth=0):
        if depth > MAX_RECURSION:
            return self._emit(task, page, {"op": "blocked", "why": "the plan keeps changing", "source": "engine"})
        if not safety.site_allowed(page.get("host"), task.sites):
            return self._emit(task, page, {"op": "pause", "why": "this site is not on the task's list",
                                           "host": page.get("host"), "source": "engine"})
        sub = task.subgoal
        if sub is None:
            return self._end(task, {"op": "finish", "why": "all steps done", "source": "engine"})
        if task.fail_streak >= 2:
            return self._think(task, page, sub, "the last two tries on this step failed", depth)
        elements = page.get("elements", [])
        a = fastpath.decide(elements, sub, page, task.failed)
        if a is not None:
            if a["op"] in ("skip", "done"):
                task.advance("%s: %s" % (a["op"], question.describe_subgoal(sub)))
                return self._next(task, page, depth + 1)
            if "index" in a:
                el = next(e for e in elements if e["i"] == a["index"])
                return self._target(task, page, sub, el, "fastpath", depth)
            a["source"] = "fastpath"
            if a["op"] == "scroll":
                a["direction"] = "down"
            a["advance"] = a["op"] == sub["op"]
            return self._act(task, page, sub, a)
        return self._ask_model(task, page, sub, elements, depth)

    def _ask_model(self, task, page, sub, elements, depth):
        cands = rank.shortlist(elements, sub, task.failed, task.page_offset)
        if not cands:
            if task.page_offset == 0:
                return self._act(task, page, sub, {"op": "scroll", "direction": "down", "source": "engine"})
            return self._think(task, page, sub, "no usable elements on this page", depth)
        unreadable = [el["i"] for el in cands if not guard.readable(el.get("name"), self.allowed)]
        if set(unreadable) & {el["i"] for el in cands[:3]}:
            return self._think(task, page, sub, "the likely targets are in a script the local model can't read", depth,
                               cands)
        shown = [dict(el, name="[label: unsupported script]") if el["i"] in unreadable else el for el in cands]
        q = question.build_question(shown)
        state = question.build_state(task.goal, sub, task.history, page)
        res = self.sup.decide(state, {"next": q})
        if res["status"] == "refused" and res.get("reason") == "too_long":
            state = question.build_state(task.goal, sub, task.history, page, max_history=0)
            res = self.sup.decide(state, {"next": q})
        if res["status"] != "done":
            return self._think(task, page, sub, "local model: %s" % res.get("message", res.get("reason")), depth, cands)
        ans = res["answers"]["next"]
        meta = {"zone": ans["zone"], "p": ans["zone_confidence"], "latency_ms": res.get("latency_ms"),
                "state": state, "options": q["criteria"]}
        key = ans["choice"]
        if ans["zone"] == "flag":
            return self._think(task, page, sub, "the local model is unsure", depth, cands, meta)
        if key in ("scroll_down", "scroll_up"):
            return self._act(task, page, sub, {"op": "scroll", "direction": key[7:], "source": "model"}, meta)
        if key == "wait":
            return self._act(task, page, sub, {"op": "wait", "source": "model"}, meta)
        if key == "done":
            task.advance("done: " + question.describe_subgoal(sub))
            return self._next(task, page, depth + 1)
        if key == "none_of_these":
            if task.page_offset == 0:
                task.page_offset = 1
                return self._next(task, page, depth + 1)
            return self._think(task, page, sub, "none of the offered elements fits", depth, cands, meta)
        el = next(e for e in cands if str(e["i"]) == key)
        op = question.op_for(el)
        if ans["zone"] == "confirm" and op == "click":
            return self._think(task, page, sub, "the local model is fairly sure but a click is hard to undo", depth,
                               cands, meta)
        return self._target(task, page, sub, el, "model", depth, meta)

    def _target(self, task, page, sub, el, source, depth, meta=None, value=None):
        op = question.op_for(el)
        fits = op == sub["op"] or (sub["op"] == "select" and op == "click")
        want = rank.words(sub.get("target"))
        # Mapping the plan's wording to the page's labels ("departure city" → "From") is the model's
        # job, so its pick completes the step. Once this step has failed, a pick that shares no word
        # with the target is a detour (clicking "Checkout" because "Add to cart" did nothing).
        on_target = (source == "thinker" or not want or not task.failed
                     or bool(want & (rank.words(el.get("name")) | rank.words(el.get("value")))))
        a = {"op": op, "index": el["i"], "name": question.clean(el.get("name"), 40), "source": source,
             "advance": fits and on_target}
        if op in ("type", "select"):
            a["value"] = value if value is not None else sub.get("value")
            if op == "type" and a["value"] is None:
                try:
                    a["value"] = task.thinker.compose({"name": el.get("name"), "role": el.get("role")},
                                                      "goal: %s\nstep: %s" % (task.goal, question.describe_subgoal(sub)))
                except ThinkerError as e:
                    return self._end(task, {"op": "blocked", "why": "could not write the text: %s" % e,
                                            "source": "engine"})
        return self._act(task, page, sub, a, meta)

    def _think(self, task, page, sub, reason, depth, cands=None, meta=None):
        cands = cands if cands is not None else rank.shortlist(page.get("elements", []), sub, task.failed)
        state = question.build_state(task.goal, sub, task.history, page)
        try:
            r = task.thinker.resolve(state, cands, reason)
        except ThinkerError as e:
            return self._end(task, {"op": "blocked", "why": "%s; the planner could not help: %s" % (reason, e),
                                    "source": "engine"})
        task.fail_streak = 0
        if r["kind"] == "pick":
            el = next((e for e in cands if e["i"] == r["index"]), None)
            if el is None:
                return self._end(task, {"op": "blocked", "why": "the planner picked an element that isn't offered",
                                        "source": "engine"})
            return self._target(task, page, sub, el, "thinker", depth, meta, r.get("value"))
        if r["kind"] == "replan" and r.get("subgoals"):
            task.subgoals = task.subgoals[: task.cursor] + r["subgoals"]
            task.page_offset = 0
            return self._next(task, page, depth + 1)
        return self._emit(task, page, {"op": "ask_user", "why": reason, "message": r.get("message") or reason,
                                       "source": "thinker"})

    def _act(self, task, page, sub, a, meta=None):
        el = next((e for e in page.get("elements", []) if e["i"] == a.get("index")), None)
        reason = safety.risky(a, el, sub, page)
        if reason:
            a["confirm"] = reason
        task.last = a
        return self._emit(task, page, a, meta)

    def _end(self, task, a):
        task.over = True
        return self._emit(task, {}, a)

    def _emit(self, task, page, a, meta=None):
        task.n += 1
        a["step"] = task.n
        if meta:
            a["zone"], a["p"] = meta["zone"], meta["p"]
        if self.steplog is not None:
            m = meta or {}
            self.steplog.add(task.id, task.n, task.goal, m.get("state"), m.get("options"),
                             {k: v for k, v in a.items() if k != "step"}, m.get("zone"), m.get("latency_ms"))
        return a
