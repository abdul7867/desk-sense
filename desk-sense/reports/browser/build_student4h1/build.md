# Model build

- checkpoint: model/artifacts/student4h1_distilled
- vocabulary trim: A (script)
- G1: worst diff 0.000051 over 619 questions -> pass
- validation accuracy per step: {"torch": {"en": 0.7468}, "onnx_fp32_trimmed": {"en": 0.7468}, "int8": {"en": 0.7468}}
- calibration: {"choice": {"n": 564, "temperature": 1.685, "ece_before": 0.0879, "ece_after": 0.0404}, "score": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}, "noul": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}}
- result: **PASS**
