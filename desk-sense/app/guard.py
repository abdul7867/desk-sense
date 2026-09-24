"""Language guard (plan §9.4): fixed script list, refuse everything else (R2).

Laya's confidence gives no warning on text it cannot read (model card: Khmer, 0% accuracy at 95%
confidence), so unsupported input is refused here, before it reaches the model.
Latin script cannot separate English from Hinglish (M7); both are allowed and labeled "en".
"""
import json
import unicodedata
from dataclasses import dataclass

SCRIPTS = {
    "latin": ((0x0041, 0x005A), (0x0061, 0x007A), (0x00C0, 0x024F), (0x1E00, 0x1EFF)),
    "devanagari": ((0x0900, 0x097F), (0xA8E0, 0xA8FF), (0x1CD0, 0x1CFF)),
}
LANGUAGE_OF_SCRIPT = {"devanagari": "hi", "latin": "en"}
# Share of letters that may come from other scripts (a stray symbol, a name) before refusing.
FOREIGN_TOLERANCE = 0.10


@dataclass
class GuardResult:
    ok: bool
    language: str = None
    reason: str = None
    message: str = None
    scripts: dict = None


def text_of(state):
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        return " ".join(text_of(v) for v in state.values())
    if isinstance(state, (list, tuple)):
        return " ".join(text_of(v) for v in state)
    return "" if state is None else json.dumps(state, ensure_ascii=False)


def script_of(ch):
    cp = ord(ch)
    for name, ranges in SCRIPTS.items():
        if any(lo <= cp <= hi for lo, hi in ranges):
            return name
    return "other"


def count_scripts(text):
    counts = {}
    for ch in text:
        if unicodedata.category(ch)[0] in ("L", "M"):
            s = script_of(ch)
            counts[s] = counts.get(s, 0) + 1
    return counts


def words_by_script(text):
    """Each word counts once, for the script most of its letters are in. Devanagari packs more
    sound into fewer letters than Latin, so letter counts would call a mixed ticket English."""
    counts, word = {}, []
    for ch in text + " ":
        if unicodedata.category(ch)[0] in ("L", "M"):
            word.append(script_of(ch))
        elif word:
            s = max(set(word), key=word.count)
            counts[s] = counts.get(s, 0) + 1
            word = []
    return counts


def check(state, allowed=("latin", "devanagari")):
    text = text_of(state)
    if not text.strip():
        return GuardResult(False, reason="empty", message="The ticket is empty. Nothing to classify.")
    counts = count_scripts(text)
    letters = sum(counts.values())
    if letters == 0:
        return GuardResult(False, reason="no_text", scripts=counts,
                           message="The ticket has no words, only numbers or symbols. Please add a description.")
    foreign = sum(n for s, n in counts.items() if s not in allowed)
    if foreign / letters > FOREIGN_TOLERANCE:
        return GuardResult(False, reason="unsupported_script", scripts=counts,
                           message="This language is not supported yet. Supported: Hindi and English (incl. Hinglish).")
    words = words_by_script(text)
    main = max((s for s in words if s in allowed), key=words.get)
    return GuardResult(True, language=LANGUAGE_OF_SCRIPT[main], scripts=counts)
