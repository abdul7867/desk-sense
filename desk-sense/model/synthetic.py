"""SYNTHETIC tickets for exercising the pipeline before real data exists. Not for any claim about
real-world quality: every result built on this is labelled synthetic in reports/synthetic/.

Tickets are composed from phrase banks (issue + optional urgency / refund / tone / filler), so labels
follow from the composition. Each issue phrase is a `group`: splits keep groups apart, so the test
set uses phrasings never seen in training. Varieties: hi (Devanagari), en, hinglish (labelled "en",
since the guard cannot tell them apart; `variety` keeps them separable for reporting).

    python -m model.synthetic                     # -> data/synthetic/
"""
import argparse
import json
import random
from pathlib import Path

from model.pin import ROOT

OUT = ROOT / "data" / "synthetic"

# issue phrases per department: (text, tone override or None)
ISSUES = {
    "en": {
        "billing": ["I was charged twice for {obj}", "{obj} shows {amt} but we agreed {amt2}",
                    "{amt} was deducted but the order failed", "I cancelled but still got billed for {obj}",
                    "the invoice for {obj} has the wrong GST number", "auto-renewal charged {amt} without asking",
                    "the discount code was not applied on {obj}", "I got billed in dollars instead of rupees"],
        "technical": ["the app crashes when I open {feat}", "{feat} has not loaded since {when}",
                      "I get error {code} on {feat}", "the website is very slow since {when}",
                      "exporting reports gives a blank file", "notifications stopped working in {feat}",
                      "data I saved in {feat} disappeared", "sync keeps failing on my phone"],
        "account": ["I can't log in, the OTP never arrives", "the password reset email is not coming",
                    "my account got locked after {k} attempts", "I want to change the email on my account",
                    "the two-factor code says invalid every time", "I need to add a new user to our team account",
                    "my profile shows someone else's name", "I cannot open my account after changing my number"],
        "sales": ["what is the price of the annual plan?", "please send a quote for {k} seats",
                  "is there a discount for NGOs?", "I want to upgrade to the business plan",
                  "do you offer a free trial for {k} users?", "can we pay quarterly instead of yearly?",
                  "what is the difference between basic and pro?", "we want to buy {k} more licences"],
        "other": [("thank you, the issue is solved now", "happy"), ("great support, keep it up", "happy"),
                  "I wanted to share some feedback on the new design", "what are your office hours?",
                  "please remove me from the newsletter", "is your office open on Sunday?",
                  ("I love the new update", "happy"), "who is my account manager?"],
    },
    "hi": {
        "billing": ["{obj} के लिए मुझसे दो बार पैसे कट गए", "{obj} में {amt} दिख रहा है जबकि {amt2} तय हुआ था",
                    "{amt} कट गए पर ऑर्डर फेल हो गया", "रद्द करने के बाद भी {obj} का बिल आ गया",
                    "{obj} के चालान में GST नंबर गलत है", "बिना पूछे ऑटो-रिन्यूअल में {amt} कट गए",
                    "{obj} पर डिस्काउंट कोड नहीं लगा", "रुपये की जगह डॉलर में बिल आया"],
        "technical": ["{feat} खोलते ही ऐप बंद हो जाता है", "{when} से {feat} लोड नहीं हो रहा",
                      "{feat} पर {code} एरर आ रहा है", "{when} से वेबसाइट बहुत धीमी चल रही है",
                      "रिपोर्ट एक्सपोर्ट करने पर खाली फाइल आती है", "{feat} में नोटिफिकेशन आने बंद हो गए",
                      "{feat} में सेव किया डेटा गायब हो गया", "फोन पर सिंक बार-बार फेल हो रहा है"],
        "account": ["लॉगिन नहीं हो रहा, OTP आता ही नहीं", "पासवर्ड रीसेट का ईमेल नहीं आ रहा",
                    "{k} बार कोशिश के बाद मेरा खाता लॉक हो गया", "मुझे अपने खाते का ईमेल बदलना है",
                    "टू-फैक्टर कोड हर बार गलत बताता है", "हमारी टीम के खाते में नया यूज़र जोड़ना है",
                    "मेरी प्रोफाइल पर किसी और का नाम दिख रहा है", "नंबर बदलने के बाद खाता खुल नहीं रहा"],
        "sales": ["सालाना प्लान की कीमत क्या है?", "{k} सीटों के लिए कोटेशन भेजिए",
                  "क्या NGO के लिए कोई छूट है?", "मुझे बिज़नेस प्लान में अपग्रेड करना है",
                  "क्या {k} यूज़र के लिए फ्री ट्रायल मिलेगा?", "क्या हम सालाना की जगह तिमाही भुगतान कर सकते हैं?",
                  "बेसिक और प्रो में क्या फर्क है?", "हमें {k} और लाइसेंस खरीदने हैं"],
        "other": [("धन्यवाद, समस्या हल हो गई", "happy"), ("बढ़िया सपोर्ट, ऐसे ही रखिए", "happy"),
                  "नए डिज़ाइन पर कुछ सुझाव देना था", "आपके ऑफिस का समय क्या है?",
                  "मुझे न्यूज़लेटर से हटा दीजिए", "क्या रविवार को ऑफिस खुला है?",
                  ("नया अपडेट बहुत अच्छा लगा", "happy"), "मेरा अकाउंट मैनेजर कौन है?"],
    },
    "hinglish": {
        "billing": ["{obj} ke liye do baar paise kat gaye", "{obj} mein {amt} dikh raha hai jabki {amt2} tay hua tha",
                    "{amt} kat gaye par order fail ho gaya", "cancel karne ke baad bhi {obj} ka bill aa gaya",
                    "{obj} ki invoice mein GST number galat hai", "bina puche auto-renewal mein {amt} kat gaye",
                    "{obj} pe discount code laga hi nahi", "rupees ki jagah dollar mein bill aaya"],
        "technical": ["{feat} kholte hi app band ho jata hai", "{when} se {feat} load nahi ho raha",
                      "{feat} pe {code} error aa raha hai", "{when} se website bahut slow chal rahi hai",
                      "report export karo to khali file aati hai", "{feat} mein notifications aana band ho gaye",
                      "{feat} mein save kiya data gayab ho gaya", "phone pe sync baar baar fail ho raha hai"],
        "account": ["login nahi ho raha, OTP aata hi nahi", "password reset ka email nahi aa raha",
                    "{k} baar try karne ke baad account lock ho gaya", "mujhe account ka email change karna hai",
                    "two-factor code har baar invalid bolta hai", "team account mein naya user add karna hai",
                    "meri profile pe kisi aur ka naam dikh raha hai", "number change karne ke baad account khul nahi raha"],
        "sales": ["annual plan ka price kya hai?", "{k} seats ka quote bhej do",
                  "NGO ke liye koi discount hai kya?", "business plan mein upgrade karna hai",
                  "{k} users ke liye free trial milega?", "yearly ki jagah quarterly pay kar sakte hain?",
                  "basic aur pro mein kya fark hai?", "humein {k} aur licence kharidne hain"],
        "other": [("thank you, problem solve ho gayi", "happy"), ("badhiya support, aise hi rakhna", "happy"),
                  "naye design pe kuch feedback dena tha", "aapke office ka time kya hai?",
                  "mujhe newsletter se hata do", "kya Sunday ko office khula hai?",
                  ("naya update bahut accha laga", "happy"), "mera account manager kaun hai?"],
    },
}

SLOTS = {
    "en": {"obj": ["my subscription", "order #{n}", "the annual plan", "invoice {n}"],
           "feat": ["settings", "the dashboard", "reports", "the mobile app"],
           "when": ["this morning", "yesterday", "two days"]},
    "hi": {"obj": ["मेरी सदस्यता", "ऑर्डर #{n}", "सालाना प्लान", "चालान {n}"],
           "feat": ["सेटिंग्स", "डैशबोर्ड", "रिपोर्ट्स", "मोबाइल ऐप"],
           "when": ["आज सुबह", "कल", "दो दिन"]},
    "hinglish": {"obj": ["meri subscription", "order #{n}", "annual plan", "invoice {n}"],
                 "feat": ["settings", "dashboard", "reports", "mobile app"],
                 "when": ["aaj subah", "kal", "do din"]},
}

BLOCKING = {"en": ["the whole team is stuck.", "we cannot work at all.", "this is urgent, customers are waiting.",
                   "nothing works since morning."],
            "hi": ["पूरी टीम का काम रुका हुआ है।", "हम बिल्कुल काम नहीं कर पा रहे।",
                   "यह बहुत ज़रूरी है, ग्राहक इंतज़ार कर रहे हैं।", "सुबह से कुछ भी नहीं चल रहा।"],
            "hinglish": ["poori team ka kaam ruka hua hai.", "hum bilkul kaam nahi kar pa rahe.",
                         "urgent hai, customers wait kar rahe hain.", "subah se kuch bhi nahi chal raha."]}
NO_RUSH = {"en": ["no rush, whenever you can.", "please check when you get time."],
           "hi": ["कोई जल्दी नहीं है।", "जब समय मिले तब देख लीजिए।"],
           "hinglish": ["koi jaldi nahi hai.", "jab time mile tab dekh lena."]}
REFUND = {"en": ["Please refund the extra amount.", "I want my money back.", "Kindly reverse the charge."],
          "hi": ["कृपया अतिरिक्त पैसे वापस करें।", "मुझे मेरे पैसे वापस चाहिए।", "कृपया चार्ज रिवर्स करें।"],
          "hinglish": ["extra paisa wapas karo please.", "mujhe mera paisa wapas chahiye.", "charge reverse kar do please."]}
TONE = {"angry": {"en": ["This is the third time I am complaining!!", "Very disappointed with your service.", "Totally unacceptable."],
                  "hi": ["तीसरी बार शिकायत कर रहा हूँ!!", "आपकी सर्विस से बहुत निराश हूँ।", "यह बिल्कुल ठीक नहीं है।"],
                  "hinglish": ["teesri baar complain kar raha hoon!!", "aapki service se bahut disappointed hoon.", "yeh bilkul theek nahi hai."]},
        "happy": {"en": ["Thanks for the quick help last time!", "Love your product."],
                  "hi": ["पिछली बार की मदद के लिए धन्यवाद!", "आपका प्रोडक्ट बहुत पसंद है।"],
                  "hinglish": ["pichli baar ki help ke liye thanks!", "aapka product bahut pasand hai."]},
        "neutral": {"en": ["Hi,", "Hello team,", ""], "hi": ["नमस्ते,", "हैलो टीम,", ""], "hinglish": ["Hi,", "Namaste,", ""]}}
FILLER = {"en": ["I have been using your product for three years.", "Earlier everything worked fine.",
                 "I already wrote to you last week but got no reply.", "My manager is asking me for an update.",
                 "I tried logging out and in again.", "I also cleared the cache and restarted the phone."],
          "hi": ["मैं तीन साल से आपका प्रोडक्ट इस्तेमाल कर रहा हूँ।", "पहले सब ठीक चल रहा था।",
                 "मैंने पिछले हफ्ते भी लिखा था पर कोई जवाब नहीं आया।", "मेरे मैनेजर अपडेट माँग रहे हैं।",
                 "मैंने लॉगआउट करके फिर से लॉगिन किया।", "कैश भी साफ किया और फोन भी रीस्टार्ट किया।"],
          "hinglish": ["main teen saal se aapka product use kar raha hoon.", "pehle sab theek chal raha tha.",
                       "maine pichle hafte bhi likha tha par koi reply nahi aaya.", "mere manager update maang rahe hain.",
                       "maine logout karke dobara login kiya.", "cache bhi clear kiya aur phone restart bhi kiya."]}
URGENCY_LEVELS = ["not urgent", "soon", "blocking work"]


def fill(rng, template, variety):
    s = SLOTS[variety]
    amt, amt2 = rng.sample([499, 999, 1499, 2400, 4999, 9800, 12400], 2)
    return template.format(obj=rng.choice(s["obj"]).format(n=rng.randint(1000, 99999)), amt="₹%d" % amt,
                           amt2="₹%d" % amt2, feat=rng.choice(s["feat"]), when=rng.choice(s["when"]),
                           code=rng.choice(["500", "403", "E-102", "timeout"]), k=rng.choice([3, 5, 10, 25, 50]),
                           n=rng.randint(1000, 99999))


def make_ticket(rng, variety, i):
    dept = rng.choice(list(ISSUES[variety]))
    idx = rng.randrange(len(ISSUES[variety][dept]))
    issue = ISSUES[variety][dept][idx]
    issue, forced_tone = issue if isinstance(issue, tuple) else (issue, None)
    tone = forced_tone or ("neutral" if dept == "other" else rng.choices(["angry", "neutral", "happy"], [0.35, 0.5, 0.15])[0])
    urgency = 0 if dept in ("sales", "other") else 1
    parts_after = []
    if dept in ("billing", "technical", "account"):
        r = rng.random()
        if r < 0.35:
            urgency = 2
            parts_after.append(rng.choice(BLOCKING[variety]))
        elif r < 0.5:
            urgency = 0
            parts_after.append(rng.choice(NO_RUSH[variety]))
    refund = dept == "billing" and rng.random() < 0.6
    if refund:
        parts_after.insert(0, rng.choice(REFUND[variety]))
    filler = rng.sample(FILLER[variety], rng.randint(4, 6)) * rng.randint(2, 6) if rng.random() < 0.1 else []
    opener = rng.choice(TONE[tone][variety]) if tone != "neutral" or rng.random() < 0.7 else ""
    body = fill(rng, issue, variety)
    body = body[0].upper() + body[1:] if variety != "hi" else body
    stop = "" if body.endswith("?") else ("।" if variety == "hi" else ".")
    text = " ".join(p for p in [opener, " ".join(filler), body + stop, *parts_after] if p)
    needs_human = dept in ("billing", "technical", "account") or tone == "angry"
    return {"id": "syn-%s-%04d" % (variety, i), "language": "hi" if variety == "hi" else "en", "variety": variety,
            "state": text, "group": "%s:%s:%d" % (variety, dept, idx), "stratum": "%s:%s" % (variety, dept),
            "labels": {"department": dept, "urgency": urgency, "refund_requested": refund,
                       "sentiment": tone, "needs_human": needs_human},
            "synthetic": True}


def second_labeler(rng, rows, share=0.1, flip=0.06):
    """A second labeler on 10% of rows who disagrees ~6% of the time (Day-2 agreement drill)."""
    out = []
    for r in rng.sample(rows, int(len(rows) * share)):
        labels = dict(r["labels"])
        if rng.random() < flip * 3:
            q = rng.choice(["sentiment", "urgency", "needs_human"])
            labels[q] = {"sentiment": lambda v: rng.choice([s for s in ("angry", "neutral", "happy") if s != v]),
                         "urgency": lambda v: min(2, v + 1) if v < 2 else 1,
                         "needs_human": lambda v: not v}[q](labels[q])
        out.append(dict(r, labels=labels))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-variety", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2530)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    rows = [make_ticket(rng, v, i) for v in ("hi", "en", "hinglish") for i in range(args.per_variety)]
    (args.out / "labeled").mkdir(parents=True, exist_ok=True)
    with open(args.out / "labeled" / "labeler_a.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(args.out / "double_labeled_b.jsonl", "w", encoding="utf-8") as f:
        for r in second_labeler(rng, rows):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote %d synthetic tickets to %s" % (len(rows), args.out))


if __name__ == "__main__":
    main()
