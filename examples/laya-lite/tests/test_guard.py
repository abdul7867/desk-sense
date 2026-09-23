import pytest

from app import guard


@pytest.mark.parametrize("text,lang", [
    ("मुझसे दो बार शुल्क लिया गया, कृपया रिफंड करें", "hi"),
    ("The app crashes every time I open settings.", "en"),
    ("bhai mera payment do baar kat gaya, refund chahiye", "en"),
    ("मेरा OTP नहीं आ रहा, login blocked है", "hi"),
    ("Invoice ₹12,400 — wrong amount!!", "en"),
    ("Café résumé naïve", "en"),
])
def test_allowed(text, lang):
    r = guard.check(text)
    assert r.ok and r.language == lang


@pytest.mark.parametrize("text", [
    "ខ្ញុំត្រូវបានគិតប្រាក់ពីរដង",       # Khmer: the model card's 0%-accuracy-at-95%-confidence case
    "لقد تم خصم المبلغ مرتين",           # Arabic
    "我被收了两次费用",                     # Chinese
    "Меня списали дважды",               # Russian
    "நான் இரண்டு முறை கட்டணம் செலுத்தினேன்",  # Tamil: Indic, but not on our list
])
def test_unsupported_script_refused(text):
    r = guard.check(text)
    assert not r.ok and r.reason == "unsupported_script"
    assert "not supported" in r.message


@pytest.mark.parametrize("text,reason", [("", "empty"), ("   \n\t", "empty"), ("12345 !!! ₹₹", "no_text")])
def test_empty_or_no_words_refused(text, reason):
    r = guard.check(text)
    assert not r.ok and r.reason == reason


def test_mostly_hindi_with_a_foreign_name_is_allowed():
    assert guard.check("मेरा ऑर्डर अभी तक नहीं आया, कृपया जल्दी भेजें। ऑर्डर नंबर 5521, नाम 李").ok


def test_structured_state_is_checked_across_fields():
    assert guard.check({"subject": "Refund", "body": "पैसे वापस करो"}).ok
    assert not guard.check({"subject": "", "body": "我被收了两次费用"}).ok


def test_too_long_is_refused_visibly_not_cut(make_sup):
    sup = make_sup()
    sup.schema["max_state_tokens"] = 20
    res = sup.submit("word " * 50)
    assert res["status"] == "refused" and res["reason"] == "too_long"
    assert res["tokens"] == 50 and res["limit"] == 20
    assert "Nothing was cut" in res["message"]
    assert sup.store.get_request(res["id"])["status"] == "refused"


def test_refused_input_never_reaches_the_worker(make_sup):
    sup = make_sup()
    res = sup.submit("ខ្ញុំត្រូវបានគិតប្រាក់ពីរដង")
    assert res["status"] == "refused"
    assert sup.worker is None
    assert sup.store.result(res["id"])["answers"]["refused"]["reason"] == "unsupported_script"
