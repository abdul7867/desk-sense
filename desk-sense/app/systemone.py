"""`POST /v1/systemone`: the Laya / TypeSafe Jev wire format, validated at the boundary.

Request:  {"state": <str | object | list>, "questions": {qid: {type, instructions, criteria?}}, "model"?: str}
Response: {"answers": {qid: {...}}, "usage": {...}} plus desk-sense extras (zone, latency_ms) that
Jev clients ignore. Limits follow Jev: Choice 2-255 options, Score 2-10 levels.
"""
MAX_QUESTIONS = 16
MAX_CHOICE_OPTIONS = 255
SCORE_LEVELS = (2, 10)
QTYPES = ("choice", "score", "noul")


class InvalidRequest(ValueError):
    pass


def _text(value, what):
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequest("%s must be a non-empty string" % what)
    return value


def _question(qid, q):
    if not isinstance(q, dict):
        raise InvalidRequest("question %r must be an object" % qid)
    t = q.get("type")
    if t not in QTYPES:
        raise InvalidRequest("question %r: type must be one of %s" % (qid, ", ".join(QTYPES)))
    out = {"type": t, "instructions": _text(q.get("instructions"), "question %r instructions" % qid)}
    crit = q.get("criteria")
    if t == "choice":
        if isinstance(crit, list):
            if not all(isinstance(c, str) and c for c in crit):
                raise InvalidRequest("question %r: choice options must be non-empty strings" % qid)
            if len(set(crit)) != len(crit):
                raise InvalidRequest("question %r: choice options must be unique" % qid)
            crit = {c: None for c in crit}
        if not isinstance(crit, dict) or not all(isinstance(k, str) and k for k in crit):
            raise InvalidRequest("question %r: choice criteria must be a list or an object of options" % qid)
        if not 2 <= len(crit) <= MAX_CHOICE_OPTIONS:
            raise InvalidRequest("question %r: choice needs 2-%d options" % (qid, MAX_CHOICE_OPTIONS))
        out["criteria"] = crit
    elif t == "score":
        lo, hi = SCORE_LEVELS
        if not isinstance(crit, list) or not lo <= len(crit) <= hi:
            raise InvalidRequest("question %r: score criteria must be a list of %d-%d levels" % (qid, lo, hi))
        out["criteria"] = crit
    elif crit is not None:
        if not isinstance(crit, dict) or set(crit) - {"true", "false"}:
            raise InvalidRequest("question %r: noul criteria may only have 'true' and 'false'" % qid)
        out["criteria"] = crit
    return out


def validate(body):
    """Returns (state, questions) or raises InvalidRequest with a message safe to show the caller."""
    if not isinstance(body, dict):
        raise InvalidRequest("body must be a JSON object")
    state = body.get("state")
    if state is None or isinstance(state, (bool, int, float)):
        raise InvalidRequest("'state' must be text, an object or a list")
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise InvalidRequest("'questions' must be a non-empty object")
    if len(questions) > MAX_QUESTIONS:
        raise InvalidRequest("at most %d questions per request" % MAX_QUESTIONS)
    return state, {str(qid): _question(qid, q) for qid, q in questions.items()}


def to_wire(result):
    """Supervisor result -> (http status, Jev-shaped body)."""
    status = result["status"]
    if status == "done":
        return 200, {"answers": result["answers"], "usage": result.get("usage") or {"input_tokens": 0, "output_tokens": 0},
                     "zone": result["zone"], "language": result.get("language"), "latency_ms": result.get("latency_ms")}
    if status == "refused":
        detail = {k: v for k, v in result.items() if k not in ("id", "status")}
        return 422, {"error": {"type": "refused", **detail}}
    return 500, {"error": {"type": "failed", "message": result.get("message", "")}}
