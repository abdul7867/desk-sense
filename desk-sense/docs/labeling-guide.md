# Labeling guide — ticket triage (draft, Day 1)

One ticket = one line in `data/labeled/<labeler>.jsonl`. Answer all five questions. If you truly
cannot tell, leave that label out; don't guess. Label what the customer wrote, not what you think
happened. The format is in `model/data.py`.

## department — which team should handle it?

| Option | Means | Examples |
|---|---|---|
| billing | money: invoices, charges, payments, refunds | "मुझसे दो बार शुल्क लिया गया" · "invoice mein amount galat hai" |
| technical | the product misbehaves: bugs, crashes, errors, slowness, outages | "ऐप खोलते ही बंद हो जाता है" · "Dashboard shows 503 since morning" |
| account | getting in or changing who they are: login, password, OTP, profile, access | "पासवर्ड रीसेट का ईमेल नहीं आ रहा" · "OTP aa hi nahi raha" |
| sales | buying more or buying differently: prices, plans, quotes, upgrades | "सालाना प्लान की कीमत क्या है?" · "Quote for 50 seats please" |
| other | none of the above: thanks, feedback, spam, unclear | "धन्यवाद, हल हो गया" · "Great support team!" |

Money **and** a bug ("payment failed with error 500") → **technical** if the product broke,
**billing** if the money moved wrongly. Write the tie-breaker you used in `notes`.

## urgency — 0 not urgent · 1 soon · 2 blocking work

| Level | Means | Examples |
|---|---|---|
| 0 | a question or request with no time pressure | "प्लान की कीमत बताइए" · "Can you send the invoice copy sometime?" |
| 1 | something is wrong but work continues | "ऐप धीमा चल रहा है" · "Charged twice, please refund" |
| 2 | they cannot work, or many users are affected, or they say it is blocking | "पूरी टीम का काम रुका हुआ है" · "Nobody can log in, urgent" |

## refund_requested — true / false

True only when they ask for money back (refund, reversal, "paisa wapas"). A complaint about price is false.
True: "कृपया रिफंड करें" · "refund chahiye". False: "invoice galat hai" · "too expensive".

## sentiment — angry · neutral · happy

| Option | Examples |
|---|---|
| angry | "तीसरी बार शिकायत कर रहा हूँ!!" · "This is useless 😡" |
| neutral | "मेरा OTP नहीं आ रहा" · "Please share the quote" |
| happy | "धन्यवाद, बहुत बढ़िया" · "Thanks a lot, it works!" |

## needs_human — true / false

True if a canned reply would not solve it: money must move, an account must be changed, a bug
must be investigated, or they are angry. False for FAQs ("what is the price?") and thanks.
True: "मुझसे दो बार शुल्क लिया गया" · "dashboard down hai". False: "धन्यवाद" · "What are your hours?"

## Rules

- 10% of tickets are labeled by two people. Below 80% agreement on any question, fix this guide first
  (`python -m model.data agreement a.jsonl b.jsonl`).
- Remove names, phone numbers, emails and order IDs, or check there are none, before any AI pre-labeling (plan Day 0).
- Nobody opens `data/splits/test.jsonl` except its owner.
