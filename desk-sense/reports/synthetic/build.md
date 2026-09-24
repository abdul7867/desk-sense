# Model build

- checkpoint: model/synthetic-run/ckpt
- vocabulary trim: B (corpus)
- G1: worst diff 1.000000 over 609 questions -> FAIL
- validation accuracy per step: {"torch": {"en": 0.9844, "hi": 0.9633}, "onnx_fp32_trimmed": {"en": 0.9844, "hi": 0.9633}, "int8": {"en": 0.9756, "hi": 0.9673}}
- calibration: {"choice": {"n": 344, "temperature": 1.3841, "ece_before": 0.0119, "ece_after": 0.0121}, "score": {"n": 172, "temperature": 1.9137, "ece_before": 0.0255, "ece_after": 0.0287}, "noul": {"n": 344, "temperature": 1.7649, "ece_before": 0.0113, "ece_after": 0.0053}}
- result: **PASS**
