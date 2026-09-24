# FAILED build (attempt 1): corpus-trim bugs, fixed in commit 0f5aace. Kept as evidence.

# Model build

- checkpoint: model/synthetic-run/ckpt
- vocabulary trim: B (corpus)
- G1: worst diff 1.000000 over 609 questions -> FAIL
- validation accuracy per step: {"torch": {"en": 0.9844, "hi": 0.9633}, "onnx_fp32_trimmed": {"en": 0.7, "hi": 0.6816}, "int8": {"en": 0.7111, "hi": 0.6816}}
- calibration: {"choice": {"n": 344, "temperature": 4.7739, "ece_before": 0.2019, "ece_after": 0.0962}, "score": {"n": 172, "temperature": 0.8613, "ece_before": 0.0869, "ece_after": 0.0853}, "noul": {"n": 344, "temperature": 3.5747, "ece_before": 0.1316, "ece_after": 0.0887}}
- result: **FAIL: onnx_fp32_trimmed drops en validation accuracy by 28.4 points; onnx_fp32_trimmed drops hi validation accuracy by 28.2 points; int8 drops en validation accuracy by 27.3 points; int8 drops hi validation accuracy by 28.2 points**
