# Lessons

Durable mistakes and the rules they produced. Committed, so they survive machines,
teammates, and reinstalls — unlike Claude's machine-local auto memory.

Fed by the `memory-promotion` skill. Read this before working in an area it mentions.

**Format:** one line per lesson. Date, what happened, what to do instead. Link out
for detail. Keep it scannable — a ledger nobody reads protects nothing.

---

<!-- Example. Replace with your own and delete this block.

- **2026-09-19 — Migration shipped without a rollback path.** A failed deploy could
  not be reverted without manual SQL. *Rule:* every migration ships with a tested
  `down`. See `docs/decisions.md#migrations`.

-->

<!-- Add newest at the top. -->

- **2026-09-24 — Corpus trim cost 28 accuracy points on text that was in the corpus.** The model
  also reads the question and option text, which was not in the corpus, and the merge closure
  followed only one way of building each token. *Rule:* the trim always includes `schema_lines()`
  and follows every producer of each token, and `trim_vocab` refuses to write a tokenizer that
  changes any corpus line. `build_model`'s per-step accuracy gate is what caught it.

- **2026-09-23 — A "wait until the benchmark ends" loop never ended.** `pgrep -f "tests.measure_app"`
  matched the loop's own command line, so it waited on itself. *Rule:* wait on a PID, or use a
  pattern the waiting command cannot contain (`tests[.]measure_app`), and check the loop has exited.

- **2026-09-23 — Same bundle measured 398 MB and 502 MB.** Linux RSS of memory-mapped weights depends
  on page-cache state (a just-written file maps in larger chunks). *Rule:* repeat memory measurements,
  include one right after a build, gate on the worst run. See DECISIONS.md, G2.
- **2026-09-23 — Re-export doubled model.data to 2.2 GB.** `onnx.save_model(save_as_external_data=True)`
  appends to an existing data file. *Rule:* delete `model.data` before writing it (export_onnx does now).
- **2026-09-23 — The plan's memory settings measured worse here.** Arena off, `quantize_dynamic` and a
  5-question batch each cost hundreds of MB or most of the accuracy. *Rule:* treat plan settings as
  hypotheses; measure before and after, and record the numbers in DECISIONS.md.
