# Model build

- checkpoint: model/artifacts/ckpt_browser2
- vocabulary trim: A (script)
- G1: worst diff 0.000055 over 619 questions -> pass
- validation accuracy per step: {"torch": {"en": 0.8255}, "onnx_fp32_trimmed": {"en": 0.8255}, "int8": {"en": 0.8234}}
- calibration: {"choice": {"n": 564, "temperature": 1.5539, "ece_before": 0.085, "ece_after": 0.0327}, "score": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}, "noul": {"n": 0, "skipped": "fewer than 30 items; temperature left at 1.000"}}
- result: **PASS**
