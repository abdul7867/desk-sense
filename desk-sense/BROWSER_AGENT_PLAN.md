# Browser agent plan: a local, Jev-style browser agent, faster than Claude in Chrome, light enough for a 4 GB PC

## Context

- **The problem:** Claude in Chrome feels slow. It reasons in text over every page before each click.
- **The idea we're copying:** TypeSafe's **Jev** (cloud-only, closed, Sept 2026) picks the next browser action in **one ~100 ms
  decision**. The Browser Use `jev-ultrafast` agent works like this:
  - it builds a numbered table of the page's buttons and fields;
  - one Jev call picks both the action and its target;
  - an LLM is used only to write text that has to be typed.
- **What we want:** the same result, but **running locally**, meaning no cloud round trip per step, no per-call fee and works
  offline. It must also use **less RAM** and be **faster**. Claude (API) is the "thinker" for planning, writing text and hard
  steps. Other AI providers can be plugged in later. Scope is **any website**.
- **Why this repo is the right base:** desk-sense already runs **Laya**, the open Jev-like model, whose server speaks
  Jev's exact `POST /v1/systemone` protocol. It runs on CPU in ~345 MB with:
  - memory-mapped int8 weights;
  - a crash-safe supervisor/worker split;
  - calibrated act / confirm / flag confidence zones;
  - a localhost-only server.

  The engine exists. Missing: the browser side, browser-action training data, and speed work (today a 5-question call is
  ~0.85 s p50 on 2 threads).

**The honest target:** clearly beat Claude in Chrome on speed and RAM. Beating Jev's raw ~100 ms per decision needs the
distilled student model (Phase 5), which isn't guaranteed. That's why every speed claim is a measured gate.

All paths below are under `desk-sense/`. Ticket triage keeps working unchanged.

---

## Architecture

```
Chrome side panel (goal) ─► extension ──fetch 127.0.0.1──► engine (desk-sense supervisor)
  content.js: numbered element table          browser/controller: fast path → shortlist → 1 question
  background.js: acts via chrome.debugger       └► worker (Laya ONNX int8, no torch)   ~every step
                                                thinker/ (Claude API, pluggable)        ~2 calls per task
```

- **No second browser.** The agent works inside your own Chrome, which is a RAM win.
- **Actions use `chrome.debugger` Input events** (trusted clicks and typing). This works on React inputs and on sites
  that reject synthetic events. The cost is Chrome's "debugging" bar while a task runs.
- **Reading the page:** the content script builds the element table in one pass per step. It includes visible, enabled,
  interactive elements (open shadow roots included), each with index, role, name (≤ 40 characters), value, region, and whether it's
  new since the last step. Password values are never read. It waits for the page to settle (no DOM changes for 150 ms,
  2 s maximum).
- **Extension → engine link:** `fetch` to `127.0.0.1:8765` using `host_permissions`.
  - Protected by a pairing token in a custom header and an extension-origin check.
  - Request bodies capped at 256 KB.
  - Native messaging is the fallback if Chrome blocks localhost access.
- **API keys stay in the engine** (environment variable or OS keyring), never in the extension.

## Decision format (one model pass per step)

- **One Choice question per step.** Options combine action and target. The element's role decides the action (textbox →
  type, select → select, else click):
  `{"7": "click button Search flights · dialog", "3": "type textbox From · empty", ..., "scroll_down", "scroll_up", "wait", "done", "none_of_these"}`.
  Keys are element indices, so duplicate labels can't merge.
- **State:** `goal | now: <current subgoal + value> | done: <last 3 actions> | page: host · title | dialog?`, about
  100 tokens. It's fitted to a **256-token cap** by dropping the oldest history entries first; the goal is never cut.
- **Shortlist before the model:** a deterministic ranker keeps the options under the 192-token head budget, so nothing is
  ever silently cut.
  - The ranker scores text overlap with the subgoal and value, role fit, and new or dialog elements.
  - It passes the top 12 elements, at most 10 tokens each.
  - If the model answers `none_of_these`, it gets the next 12 once; after that the step goes to the thinker.
- **Zones:**
  - **act** (≥ 0.85): execute.
  - **confirm:** execute only reversible, low-risk actions, then check the page changed.
  - **flag:** send the step to the thinker.
- **Typed values** come from the plan (or the thinker's `compose` call), never from page text.

## Thinker (Claude first, pluggable): new `thinker/` package

- **Interface** (`thinker/base.py`):
  - `plan(goal, page)` → subgoals, each with {action, target hint, value, irreversible}.
  - `resolve(state, candidates, reason)` → a pick, a new plan, or "ask the user".
  - `compose(field, context)` → text to type.
- **Claude provider** (`thinker/anthropic_provider.py`): official `anthropic` SDK.
  - Structured output via pydantic schemas.
  - Model is a config value (`THINKER_MODEL`). Default is **Claude Haiku 4.5** (`claude-haiku-4-5`), the fastest
    and cheapest, chosen by the owner. Models that take an effort level run at `THINKER_EFFORT` (default `low`,
    `medium` if the benchmark shows it's needed).
  - Cached fixed system prompt, 20 s timeout, one retry.
- **Test provider:** `thinker/fake.py`, a scripted provider for tests. OpenRouter or a local model can be added later behind
  the same interface.
- **When the thinker is called** (`thinker/budget.py`):
  - one `plan` call, fired while the first page loads;
  - after that, only on a flag, `BLOCKED`, 2 failed steps, or free text to write.
  - Budget per task: 1 plan, 4 resolve, 3 compose calls, then stop as blocked.
- **Where it runs:** in the supervisor process, imported only when first needed, with its own `requirements-browser.txt`.
  Never in the worker, and never under `app/`: `.claude/rules/backend.md:9` limits `app/` to
  onnxruntime/tokenizers/numpy/psutil/stdlib.

## Speed plan (levers in order of payoff; every number here is a target until measured)

| Lever | Expected gain |
|---|---|
| **One question per step** instead of 5. `app/runtime.py:82-105` re-reads the state once per question | ~5× fewer passes |
| **256-token cap** (typical steps are 180–220 tokens) | ~linear |
| **Fast paths skip the model**: exact name match with the planned target or value, autocomplete option that starts with the typed value, spinner visible → wait | 30–50% of steps |
| **Keep the worker warm** during a task; preload when the side panel opens | removes 0.8–2 s cold starts |
| **Lighter step logging**: new `Supervisor.decide()` with no before-write; the step log is written in the background to a separate SQLite database with relaxed disk syncing | ~10–40 ms per step |
| **int8 compute** (`quantize.py --accuracy-level 4`, already measured at 98.9% decisive agreement) | ~1.5–2× |
| **Stop ORT threads from busy-waiting** (`allow_spinning=0`) so Chrome isn't starved on 2 cores | measure |
| **4-bit weights** (`--bits 4` already exists) | behind the accuracy gate |
| **Distilled student** (below) | ~2.5–3× |

**Distilled student:** a pruned copy of the fine-tuned Laya that keeps only the global-attention layers. mmBERT-base uses global
attention every 3rd layer; read the exact layer count from the checkpoint config. It keeps the embeddings and the decision
head, and is trained on the teacher's outputs plus the true labels. The alternative is mmBERT-small with a new head.

- **Catch:** ModernBERT picks local or global attention from a layer's position number. After pruning, each kept layer's
  attention type must be pinned, and the G1 export check must prove it.

**RAM:**
- The script-only vocabulary trim is kept. The corpus trim is unsafe for open-web text (`DECISIONS.md:15`).
- The target engine peak is therefore reached through the student and 4-bit embeddings, not a vocabulary trim.

## Training data for "any website"

1. **Mind2Web:** ~1,000 training tasks across 137 sites. It's CC-BY-4.0 but the authors ask for research use, so
   **confirm the license fits before training**. WebLINX is likely non-commercial only, so check it too.
   Convert with `model/browser/convert_mind2web.py`, reusing the same table builder and ranker. The Python port is checked
   against the JavaScript on shared fixtures.
2. **Your own traces:** the extension's record mode saves (table, action, goal) while you work, into gitignored `data/`.
3. **Claude as teacher:** Claude (Batches API) writes subgoals for Mind2Web tasks and labels your recorded states. Every live
   `resolve` call also becomes a new training row. This is how the system learns from Claude over time.
4. **Synthetic offline pages** (forms, autocomplete, date pickers, pop-ups), labelled automatically.

- **Row format:** `{id, language, group: <site>, stratum, state, questions: {next: …}, labels: {next: "7"}}`.
- **Splitting by `group`** keeps validation and test sites out of training entirely. The test split stays locked, as
  today.
- **Fine-tuning** runs on Kaggle GPU (CPU training measured at 43 min for 743 rows, so it won't scale).

## Language guard (`app/guard.py`)

- `guard.check` stays the same for tickets.
- A new `check_fields` checks the goal and plan text against `schema_browser.json`'s allowed scripts.
- An element label in an unsupported script becomes `[label: unsupported script]`. If it's among the top 3 candidates, the
  step goes to the thinker. Refuse, never guess.

## Safety (`browser/safety.py`, runs after every decision including fast paths and Claude picks)

- **Always confirm with you**, with no way to turn it off:
  - buy, pay, order, checkout, delete, send, submit, post, transfer (multilingual, e.g. खरीदें, भेजें);
  - plan steps marked `irreversible`;
  - card, password or OTP fields;
  - a form that submits to another site.
- **Allowlist:** sites are allowed one at a time. Navigating to an unlisted site pauses the task.
- **Prompt injection:**
  - The local model can only pick from listed options.
  - Typed values come from the plan.
  - Claude gets page text inside an untrusted-data block, and its structured output can only pick listed options.
  - Plan changes can't add new sites or values without your approval.
- **Server:** stays on 127.0.0.1 only, with the token and origin checks.

## Files

**New:**
- `app/systemone.py`: validates Jev/Laya `/v1/systemone` requests.
- `browser/`: `controller.py`, `rank.py`, `fastpath.py`, `question.py`, `safety.py`, `steplog.py`.
- `thinker/`: `base.py`, `anthropic_provider.py`, `fake.py`, `budget.py`.
- `extension/`: `manifest.json`, `background.js`, `content.js`, `sidepanel.*`.
- `model/browser/`: `convert_mind2web.py`, `convert_traces.py`, `teacher_label.py`, `prune_layers.py`, `distill.py`.
- `schema_browser.json`.
- `bench/`: `pages/`, `tasks.jsonl`, `run.py`.
- `tests/browser/` and `tests/measure_browser.py`.

**Changed:**
- `app/supervisor.py` (routes at :260-272): new `POST /v1/agent/step` and `POST /v1/systemone`, `decide()`, the
  pairing token and origin check, keeping the worker warm while a task is active.
- `app/runtime.py`: `fit_state` and an `options_too_long` refusal, replacing the silent option cutting at :90-95.
- `app/guard.py`: `check_fields`.
- `app/ort_model.py`: the `allow_spinning` setting.
- `model/data.py`, `model/evaluate.py`, `model/finetune/finetune.py`, `model/calibrate/calibrate.py`: per-row questions
  (today they read `schema.json`), and calibration temperatures grouped by option count (today one temperature per type,
  `calibrate.py:72`).
- `model/build_model.py`: `--schema`, `--bits`, `--accuracy-level`, and a student step.
- `model/trim/trim_vocab.py`: read allowed scripts from the schema.

**DECISIONS.md rows needed:**
- browser steps skip crash replay (replaying a click on a changed page is unsafe);
- int8 compute and 4-bit weights;
- layer pruning;
- the per-field guard;
- the thinker living outside `app/`.

**Reused as-is:**
- supervisor/worker crash handling;
- watchdog (`supervisor.py:29-45`);
- zones (`app/zones.py`);
- ORT session setup (`app/ort_model.py:18-29`);
- `malloc_trim` (`worker.py:17-26`);
- the whole trim → ONNX → int8 → calibrate pipeline;
- FakeModel and the `make_sup` test fixture;
- `tests/measure_app.py` patterns.

## Phases and gates (thresholds fixed before seeing results, desk-sense style)

| Phase | Work | Gate |
|---|---|---|
| **B0 Baseline** | Measure 1 question, ≤ 256 tokens, current int8 bundle, 2 threads | Numbers recorded, on the dev box and the 4 GB PC |
| **B1 Plumbing** | Routes, controller, extension, fake model and fake thinker, offline bench pages | 5 offline tasks pass end to end on fakes; `/v1/systemone` matches reference request/response files; ticket tests still green |
| **B2 Shortlist** | Ranker plus the Mind2Web and trace converters | Correct element in the top 12 on ≥ 97% of validation steps; zero truncations |
| **B3 Model** | Fine-tune Laya on browser rows and build | On sites never seen in training: act-zone precision ≥ 97%, act coverage ≥ 50% (stretch 75%), ECE ≤ 0.10 |
| **B4 Speed, base model** | One question, fast paths, warm worker, int8 compute | Decision p50 ≤ 300 ms, p95 ≤ 500 ms (2 threads); engine peak ≤ 400 MB; thinker adds ≤ 60 MB |
| **B5 Student** | Prune and distill, optional 4-bit | p50 ≤ 120 ms, p95 ≤ 200 ms (stretch p50 ≤ 60 ms, i.e. faster than Jev's ~100 ms). Peak ≤ 300 MB (stretch 220 MB). Precision within 1 point and coverage within 5 points of the teacher |
| **B6 Offline tasks** | Full agent on the bench | Success ≥ 90%. Median time per task ≤ ⅓ of Claude in Chrome's. Median ≤ 2 Claude calls per task. **100% of risky actions stopped.** Zero off-allowlist actions |
| **B7 Live and soak** | 6 of your real sites (never trained on), 1-hour soak | Live success reported (target ≥ 70%); no restarts; flat memory |

## Risks to watch

- **Base Laya won't hit ~100 ms on an i3.** Only the student might. For short tasks, page loads and the plan call dominate
  total time.
- **"Any site" accuracy is the hardest part.** Public data is small, and some things can't be read at all: cross-origin
  iframes, canvas, closed shadow DOM, virtualised lists.
- **4 GB PC:** Chrome alone uses 1.5–2.5 GB, and swapping ruins p95. Windows must be measured separately, because the
  Linux malloc settings don't apply there.
- **Smaller risks:** dataset licenses; the debugging bar; sites that detect automation; the model favouring options by
  their position in the list.

## Verification

1. `python -m pytest -q`: ticket tests plus `tests/browser/` on the fake model and fake thinker.
2. `python -m tests.measure_browser --n 500 --threads 2`: B0, B4 and B5 latency and peak private memory.
3. `python -m model.build_model --schema schema_browser.json`: per-step accuracy gate and G1 (including the student's
   attention pinning).
4. `python -m model.evaluate --split val --by group`: B3 on sites never seen in training.
5. `python -m bench.run --suite offline --runs 5`: B6. Also run Claude in Chrome with the `/fast` shortcut on the same
   tasks, 3 runs each, same checker.
6. Repeat steps 2 and 5 on the 4 GB Windows PC.
7. Run the `ship-it` skill before calling any phase done.
