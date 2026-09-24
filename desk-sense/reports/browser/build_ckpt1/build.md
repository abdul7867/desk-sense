# Model build

- checkpoint: model/artifacts/ckpt_browser
- vocabulary trim: A (script)
- G1: worst diff 0.000052 over 619 questions -> pass
- validation accuracy per step: {"torch": {"en": 0.7386}, "onnx_fp32_trimmed": {"en": 0.7386}, "int8": {"en": 0.7386}}
- calibration: {"choice": {"n": 572, "temperature": 2.9706, "ece_before": 0.1935, "ece_after": 0.0911}, "score": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}, "noul": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}}
- result: **PASS**
