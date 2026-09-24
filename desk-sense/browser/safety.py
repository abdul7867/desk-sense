"""Actions that always need the person's confirmation, whoever chose them (fast path, model or
thinker). No setting turns this off. False positives cost one click; false negatives can cost money.
Also: sensitive field values never leave the engine (thinker calls, step log)."""
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
MASK = "(filled)"


def sensitive(el):
    """A field whose contents are secret: passwords, card data, one-time codes, ID numbers."""
    text = " ".join(str(el.get(k) or "") for k in ("name", "autocomplete", "id_hint"))
    return el.get("type") in SENSITIVE_TYPES or bool(SENSITIVE_FIELDS.search(text)) \
        or str(el.get("autocomplete") or "").startswith("cc-")


def redact(page):
    """The page with sensitive values replaced, before anything reads it. The extension masks them
    too; this is the engine's own guarantee, in case a page labels a field in a way it missed."""
    elements = [dict(el, value=MASK if el.get("value") else "") if sensitive(el) else el
                for el in page.get("elements", [])]
    return dict(page, elements=elements)


def risky(action, el, subgoal, page):
    """Reason string if this action needs confirmation, else None."""
    op = action.get("op")
    if subgoal and subgoal.get("irreversible"):
        return "the plan marks this step as irreversible"
    if el is None:
        return None
    if op == "click" and words(el.get("name")) & RISKY_WORDS:
        return "the button looks like it buys, sends or deletes something"
    if op == "select" and (words(el.get("name")) | words(action.get("value"))) & RISKY_WORDS:
        return "the choice looks like it buys, sends or deletes something"
    if op == "click" and el.get("type") == "submit" and el.get("form_host") and el["form_host"] != page.get("host"):
        return "the form sends data to another site (%s)" % el["form_host"]
    if op in ("type", "select") and sensitive(el):
        return "the field asks for a password, card or one-time code"
    return None


def site_allowed(host, allowlist):
    host = (host or "").lower().rstrip(".")
    return any(host == a or host.endswith("." + a) for a in allowlist)
