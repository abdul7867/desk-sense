"""`POST /v1/systemone` (Laya / Jev wire format) and the HTTP boundary: body cap, origin, host, token."""
import http.client
import json
import threading

import pytest

from app import systemone
from app.supervisor import MAX_BODY_BYTES, make_server

QUESTIONS = {
    "department": {"type": "choice", "instructions": "Which team?", "criteria": {"billing": "money", "other": "rest"}},
    "urgency": {"type": "score", "instructions": "How urgent?", "criteria": ["low", "mid", "high"]},
    "refund": {"type": "noul", "instructions": "Asks for money back."},
}


@pytest.fixture
def serve(make_sup):
    servers = []

    def start(**kw):
        server = make_server(make_sup(), 0, **kw)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server.server_address[1]

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def post(port, path, body, headers=None, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    data = raw if raw is not None else json.dumps(body).encode("utf-8")
    conn.request("POST", path, data, {"Content-Type": "application/json", **(headers or {})})
    resp = conn.getresponse()
    out = resp.status, json.loads(resp.read() or b"null")
    conn.close()
    return out


def test_systemone_answers_in_jev_shape(serve):
    port = serve()
    code, body = post(port, "/v1/systemone", {"state": {"body": "billed twice, refund please"}, "questions": QUESTIONS})
    assert code == 200
    assert set(body["answers"]) == set(QUESTIONS)
    assert body["answers"]["department"]["choice"] in ("billing", "other")
    assert "score" in body["answers"]["urgency"] and "noul" in body["answers"]["refund"]
    assert "input_tokens" in body["usage"] and body["zone"] in ("act", "confirm", "flag")


def test_systemone_accepts_choice_list(serve):
    code, body = post(serve(), "/v1/systemone", {"state": "hello there", "questions": {
        "q": {"type": "choice", "instructions": "Pick one", "criteria": ["a", "b", "c"]}}})
    assert code == 200 and body["answers"]["q"]["choice"] in "abc"


@pytest.mark.parametrize("body, fragment", [
    ({"questions": QUESTIONS}, "'state'"),
    ({"state": 5, "questions": QUESTIONS}, "'state'"),
    ({"state": "x", "questions": {}}, "'questions'"),
    ({"state": "x", "questions": {"q": {"type": "maybe", "instructions": "?"}}}, "type must be"),
    ({"state": "x", "questions": {"q": {"type": "choice", "instructions": "?", "criteria": ["only"]}}}, "2-255"),
    ({"state": "x", "questions": {"q": {"type": "choice", "instructions": "?", "criteria": ["a", "a"]}}}, "unique"),
    ({"state": "x", "questions": {"q": {"type": "score", "instructions": "?", "criteria": ["one"]}}}, "2-10"),
    ({"state": "x", "questions": {"q": {"type": "noul", "instructions": ""}}}, "instructions"),
    ({"state": "x", "questions": {"q": {"type": "noul", "instructions": "?", "criteria": {"maybe": 1}}}}, "noul"),
])
def test_systemone_rejects_bad_requests(serve, body, fragment):
    code, out = post(serve(), "/v1/systemone", body)
    assert code == 400 and out["error"]["type"] == "invalid_request"
    assert fragment in out["error"]["message"]


def test_systemone_refusal_is_422(serve):
    code, out = post(serve(), "/v1/systemone", {"state": "ខ្ញុំត្រូវការជំនួយ", "questions": QUESTIONS})
    assert code == 422 and out["error"]["reason"] == "unsupported_script"


def test_too_many_questions():
    qs = {"q%d" % i: {"type": "noul", "instructions": "?"} for i in range(systemone.MAX_QUESTIONS + 1)}
    with pytest.raises(systemone.InvalidRequest):
        systemone.validate({"state": "x", "questions": qs})


def test_body_cap(serve):
    code, out = post(serve(), "/predict", None, raw=b"x" * (MAX_BODY_BYTES + 1))
    assert code == 413


def test_web_page_origin_is_refused(serve):
    ext = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    port = serve(allowed_origins=(ext,))
    assert post(port, "/predict", {"state": "hi"}, {"Origin": "https://evil.example"})[0] == 403
    assert post(port, "/predict", {"state": "hi"}, {"Origin": ext})[0] == 200
    assert post(port, "/predict", {"state": "hi"})[0] == 200  # CLI / curl: no Origin


def test_foreign_host_header_is_refused(serve):
    assert post(serve(), "/predict", {"state": "hi"}, {"Host": "attacker.example:8765"})[0] == 403


def test_token_required_when_set(serve):
    port = serve(token="s3cret")
    assert post(port, "/v1/systemone", {"state": "hi", "questions": QUESTIONS})[0] == 401
    assert post(port, "/v1/systemone", {"state": "hi", "questions": QUESTIONS}, {"Authorization": "Bearer nope"})[0] == 401
    assert post(port, "/v1/systemone", {"state": "hi", "questions": QUESTIONS}, {"Authorization": "Bearer s3cret"})[0] == 200
