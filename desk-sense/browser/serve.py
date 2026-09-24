"""Browser agent engine: the desk-sense supervisor plus the agent routes, on 127.0.0.1 only.

    DESK_SENSE_TOKEN=<pairing token> python -m browser.serve --extension-id <id>
    python -m browser.serve --fake --thinker fake        # no model, no API: for tests and the bench

Routes (all need `Authorization: Bearer <token>`):
    POST /v1/agent/start  {"goal", "sites"?, "page"}        -> first action + task id + plan
    POST /v1/agent/step   {"task", "page", "last"?}         -> next action
    POST /v1/agent/stop   {"task"}
    POST /v1/systemone    Jev/Laya wire format, for any other client
"""
import argparse
import json
import os
import secrets
from pathlib import Path

import thinker
from app.supervisor import DEFAULT_BUNDLE, ROOT, Supervisor, make_server
from browser.controller import Controller
from browser.steplog import StepLog


def agent_routes(ctl):
    def need(body, *keys):
        if not isinstance(body, dict) or any(k not in body for k in keys):
            return "body must be a JSON object with %s" % ", ".join(keys)
        if "page" in body and not isinstance(body["page"], dict):
            return "'page' must be an object"
        return None

    def start(body):
        err = need(body, "goal", "page")
        return (400, {"error": err}) if err else (200, ctl.start(str(body["goal"]), body.get("sites"), body["page"]))

    def step(body):
        err = need(body, "task", "page")
        return (400, {"error": err}) if err else (200, ctl.step(str(body["task"]), body["page"], body.get("last")))

    def stop(body):
        err = need(body, "task")
        return (400, {"error": err}) if err else (200, ctl.stop(str(body["task"])))

    return {"/v1/agent/start": start, "/v1/agent/step": step, "/v1/agent/stop": stop}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "desk_sense.db"))
    ap.add_argument("--steps-db", default=str(ROOT / "data" / "browser_steps.db"))
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--fake", action="store_true", help="fake model (deterministic: picks the ranker's top)")
    ap.add_argument("--thinker", default="claude", help="claude (default) or fake")
    ap.add_argument("--thinker-script", help="fake thinker only: JSON file {goal: [subgoal, ...]}")
    ap.add_argument("--extension-id", action="append", default=[], help="Chrome extension id allowed to call")
    args = ap.parse_args()

    token = os.environ.get("DESK_SENSE_TOKEN") or secrets.token_urlsafe(24)
    sup = Supervisor(args.db, bundle=args.bundle, fake=args.fake, fake_policy="first", threads=args.threads)
    cfg = {"plans": json.loads(Path(args.thinker_script).read_text(encoding="utf-8"))} if args.thinker_script else {}
    Path(args.steps_db).parent.mkdir(parents=True, exist_ok=True)
    steplog = StepLog(args.steps_db)
    ctl = Controller(sup, lambda: thinker.make(args.thinker, **cfg), steplog,
                     tuple(sup.schema.get("allowed_scripts", ("latin", "devanagari"))))
    origins = tuple("chrome-extension://" + i for i in args.extension_id)
    server = make_server(sup, args.port, token=token, allowed_origins=origins, routes=agent_routes(ctl))
    print("listening on http://%s:%d" % server.server_address[:2])
    if "DESK_SENSE_TOKEN" not in os.environ:
        print("pairing token (paste into the extension's side panel): %s" % token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        steplog.close()
        sup.close()


if __name__ == "__main__":
    main()
