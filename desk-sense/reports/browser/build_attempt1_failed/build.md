# Model build

- checkpoint: model/artifacts/ckpt_browser
- vocabulary trim: A (script)
- G1: worst diff 0.000052 over 609 questions -> pass
- validation accuracy per step: {"torch": {"en": 0.7386}, "onnx_fp32_trimmed": {"en": 0.7168}, "int8": {"en": 0.7124}}
- calibration: {"choice": {"n": 572, "temperature": 2.7395, "ece_before": 0.18, "ece_after": 0.0988}, "score": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}, "noul": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}}
- result: **FAIL: onnx_fp32_trimmed drops en validation accuracy by 2.2 points; int8 drops en validation accuracy by 2.6 points**
