"""Confidence zones (plan §9.5). Zone confidence is the top calibrated probability, the quantity
temperature calibration makes honest; Laya's entropy `confidence` is not a probability."""
ORDER = {"act": 0, "confirm": 1, "flag": 2}


def top_probability(answer):
    if answer["type"] == "noul":
        return max(answer["noul"], 1.0 - answer["noul"])
    return max(answer["probabilities"].values())


def zone_for(p, act=0.85, confirm=0.60):
    if p >= act:
        return "act"
    if p >= confirm:
        return "confirm"
    return "flag"


def assign(answers, thresholds):
    """Per-question zone added in place; the request's zone is its least certain question."""
    worst = "act"
    for ans in answers.values():
        p = top_probability(ans)
        ans["zone"] = zone_for(p, thresholds["act"], thresholds["confirm"])
        ans["zone_confidence"] = round(p, 4)
        if ORDER[ans["zone"]] > ORDER[worst]:
            worst = ans["zone"]
    return worst
