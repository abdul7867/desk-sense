"""Actions that always need the person's confirmation, whoever chose them (fast path, model or
thinker). No setting turns this off. False positives cost one click; false negatives can cost money."""
import re

from browser.rank import words

RISKY_WORDS = {
    # English
    "buy", "pay", "purchase", "order", "checkout", "delete", "remove", "send", "submit", "post", "publish",
    "transfer", "confirm", "book", "subscribe", "unsubscribe", "withdraw", "donate",
    # Hindi
    "खरीदें", "ख़रीदें", "भुगतान", "भेजें", "हटाएं", "हटाएँ", "मिटाएं", "ऑर्डर", "पुष्टि", "जमा",
}
SENSITIVE_FIELDS = re.compile(r"card|cvv|cvc|expiry|otp|one.time|pin\b|iban|account.number|ssn|aadhaar|pan\b", re.I)
SENSITIVE_TYPES = {"password"}


def risky(action, el, subgoal, page):
    """Reason string if this action needs confirmation, else None."""
    op = action.get("op")
    if subgoal and subgoal.get("irreversible"):
        return "the plan marks this step as irreversible"
    if el is None:
        return None
    text = " ".join(str(el.get(k) or "") for k in ("name", "value", "autocomplete", "id_hint"))
    if op == "click" and words(el.get("name")) & RISKY_WORDS:
        return "the button looks like it buys, sends or deletes something"
    if op == "click" and el.get("type") == "submit" and el.get("form_host") and el["form_host"] != page.get("host"):
        return "the form sends data to another site (%s)" % el["form_host"]
    if op == "type" and (el.get("type") in SENSITIVE_TYPES or SENSITIVE_FIELDS.search(text)):
        return "the field asks for a password, card or one-time code"
    return None


def site_allowed(host, allowlist):
    host = (host or "").lower().rstrip(".")
    return any(host == a or host.endswith("." + a) for a in allowlist)
