"""Deterministic varied request generator for G1 and drift checks: 1-5 questions, 2-20 options."""
import random

STATES = [
    "मुझसे दो बार शुल्क लिया गया, कृपया रिफंड करें",
    "मेरा खाता लॉक हो गया है और पासवर्ड रीसेट का ईमेल नहीं आ रहा",
    "ऐप खोलते ही बंद हो जाता है, पूरी टीम का काम रुका हुआ है",
    "क्या आप बता सकते हैं कि सालाना प्लान की कीमत क्या है?",
    "The app crashes every time I open settings, nobody on my team can work.",
    "I was charged twice for my subscription this month. Please refund one.",
    "Can you send me a quote for 50 seats on the annual plan?",
    "Thanks, the issue is fixed now. Great support!",
    "bhai mera payment do baar kat gaya, refund chahiye jaldi",
    "login nahi ho raha, OTP aa hi nahi raha, urgent hai",
    "pricing page pe annual plan ka rate kya hai? discount milega?",
    "app bahut slow chal raha hai kal se, kuch karo please",
    {"subject": "Invoice #4471 wrong amount", "body": "The invoice shows ₹12,400 but we agreed ₹9,800."},
    {"subject": "सर्वर डाउन", "body": "हमारा डैशबोर्ड पिछले एक घंटे से लोड नहीं हो रहा है। 503 error आ रहा है।"},
]

WORDS = ["billing", "technical", "account", "sales", "shipping", "returns", "security", "privacy",
         "onboarding", "legal", "partnerships", "hardware", "mobile", "web", "api", "reports",
         "integrations", "feedback", "spam", "other", "hr", "compliance"]

INSTRUCTIONS = ["Which team should handle this?", "What is the main topic?", "Where should this be routed?",
                "यह किस विभाग का मामला है?", "Kaunsi team ko bhejna chahiye?"]
SCALES = [["not urgent", "soon", "blocking"], ["very negative", "negative", "neutral", "positive", "very positive"],
          ["low", "medium", "high", "critical"], ["no", "yes"], ["0", "1", "2", "3", "4", "5", "6"]]
STATEMENTS = ["The customer is asking for a refund.", "The customer is angry.",
              "ग्राहक पैसे वापस मांग रहा है।", "A human agent must reply.", "Yeh spam hai."]


def long_state(rng):
    parts = [s if isinstance(s, str) else s["body"] for s in STATES]
    return " ".join(rng.choice(parts) for _ in range(60))


def make_cases(n=200, seed=1234):
    rng = random.Random(seed)
    cases = []
    for i in range(n):
        state = long_state(rng) if i % 25 == 0 else rng.choice(STATES)
        questions = {}
        for j in range(rng.randint(1, 5)):
            kind = rng.choice(["choice", "choice", "score", "noul"])
            if kind == "choice":
                opts = rng.sample(WORDS, rng.randint(2, 20))
                crit = {o: ("%s related requests" % o if rng.random() < 0.5 else None) for o in opts}
                questions["q%d" % j] = {"type": "choice", "instructions": rng.choice(INSTRUCTIONS), "criteria": crit}
            elif kind == "score":
                questions["q%d" % j] = {"type": "score", "instructions": "How would you rate this?",
                                        "criteria": rng.choice(SCALES)}
            else:
                questions["q%d" % j] = {"type": "noul", "instructions": rng.choice(STATEMENTS)}
        cases.append({"id": i, "state": state, "questions": questions})
    return cases
