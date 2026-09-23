"""CLI instead of a browser UI (plan M10, solo guidance).

    python -m app.cli ask "मुझसे दो बार शुल्क लिया गया"      # classify one ticket
    python -m app.cli ask --file ticket.txt
    python -m app.cli shell                                # one ticket per line, model stays loaded
    python -m app.cli correct 12 department billing        # log a correction
    python -m app.cli status
Add --fake to run without the model.
"""
import argparse
import sys
from pathlib import Path

from app.supervisor import DEFAULT_BUNDLE, ROOT, Supervisor

ZONE_LABEL = {"act": "ACT     (auto-apply)", "confirm": "CONFIRM (check this)", "flag": "FLAG    (human review)"}


def value_of(ans):
    if ans["type"] == "choice":
        return ans["choice"]
    if ans["type"] == "score":
        top = max(ans["probabilities"], key=ans["probabilities"].get)
        return "%s (level %s, expected %.2f)" % (ans["legend"][top], top, ans["score"]) if "legend" in ans else top
    return "yes" if ans["noul"] >= 0.5 else "no"


def show(res, out=sys.stdout):
    if res["status"] != "done":
        out.write("#%s %s: %s\n" % (res["id"], res["status"].upper(), res.get("message", "")))
        return
    out.write("#%s  language=%s  %s  %sms\n" % (res["id"], res["language"], ZONE_LABEL[res["zone"]], res["latency_ms"]))
    for qid, ans in res["answers"].items():
        out.write("  %-17s %-40s p=%.2f  %s\n" % (qid, value_of(ans), ans["zone_confidence"], ans["zone"]))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="laya-lite")
    ap.add_argument("--db", default=str(ROOT / "laya_lite.db"))
    ap.add_argument("--bundle", default=str(DEFAULT_BUNDLE))
    ap.add_argument("--fake", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("text", nargs="?")
    a.add_argument("--file", type=Path)
    sub.add_parser("shell")
    c = sub.add_parser("correct")
    c.add_argument("request_id", type=int)
    c.add_argument("question_id")
    c.add_argument("value")
    sub.add_parser("status")
    args = ap.parse_args(argv)

    sup = Supervisor(args.db, bundle=args.bundle, fake=args.fake)
    try:
        if args.cmd == "ask":
            text = args.file.read_text(encoding="utf-8") if args.file else args.text
            if text is None:
                ap.error("give the ticket text or --file")
            show(sup.submit(text))
        elif args.cmd == "shell":
            print("One ticket per line. Ctrl-D to quit.")
            for line in sys.stdin:
                if line.strip():
                    show(sup.submit(line.strip()))
        elif args.cmd == "correct":
            before = sup.store.add_correction(args.request_id, args.question_id, args.value)
            print("logged: #%d %s %s -> %s" % (args.request_id, args.question_id, before, args.value))
        elif args.cmd == "status":
            print(sup.store.counts())
    finally:
        sup.close()


if __name__ == "__main__":
    main()
