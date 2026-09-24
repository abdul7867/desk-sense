// Offline benchmark: the real extension in Chromium, driving the real engine on local pages.
//
//   node bench/run.mjs                    # fake model + scripted thinker: checks the plumbing (gate B1)
//   node bench/run.mjs --real --runs 5    # real model bundle (model/dist) + scripted thinker
//   node bench/run.mjs --tasks tasks_fuzzy.jsonl   # plans that don't name the exact labels: the model must decide
//
// Needs Playwright (npm i -g playwright, or set NODE_PATH). Writes reports/browser/bench_<mode>.json.
import { execSync, spawn } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const flag = (name, dflt) => { const i = args.indexOf(name); return i < 0 ? dflt : args[i + 1]; };
const REAL = args.includes("--real");
const RUNS = Number(flag("--runs", 1));
const ONLY = flag("--only", null);
const HEADED = args.includes("--headed");
const TASKS = flag("--tasks", "tasks.jsonl");
const SUITE = TASKS.replace(/^tasks_?|\.jsonl$/g, "") || "exact";

function loadPlaywright() {
  const require = createRequire(import.meta.url);
  try { return require("playwright"); } catch { /* fall through to the global install */ }
  return require(join(execSync("npm root -g").toString().trim(), "playwright"));
}

function servePages(dir) {
  const types = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css" };
  const server = createServer((req, res) => {
    const path = join(dir, decodeURIComponent(new URL(req.url, "http://x").pathname));
    if (!path.startsWith(dir)) { res.writeHead(403).end(); return; }
    try {
      const body = readFileSync(path);
      res.writeHead(200, { "Content-Type": types[extname(path)] || "application/octet-stream" }).end(body);
    } catch { res.writeHead(404).end(); }
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
}

async function waitHealthy(url, token, proc, ms = 60000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (proc.exitCode !== null) throw new Error("engine exited early");
    try {
      const r = await fetch(url + "/health", { headers: { Authorization: "Bearer " + token } });
      if (r.ok) return;
    } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("engine did not become healthy");
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const tasks = readFileSync(join(ROOT, "bench", TASKS), "utf8").split("\n").filter(Boolean).map(JSON.parse)
    .filter((t) => !ONLY || t.id === ONLY);
  const tmp = mkdtempSync(join(tmpdir(), "ds-bench-"));
  const pages = await servePages(join(ROOT, "bench", "pages"));
  const pagesUrl = `http://127.0.0.1:${pages.address().port}/`;

  const { chromium } = loadPlaywright();
  const ext = join(ROOT, "extension");
  const context = await chromium.launchPersistentContext(join(tmp, "profile"), {
    headless: !HEADED, channel: "chromium",
    args: [`--disable-extensions-except=${ext}`, `--load-extension=${ext}`],
  });
  const sw = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker");
  const extId = new URL(sw.url()).host;

  const script = { plans: {}, texts: {} };
  for (const t of tasks) { script.plans[t.goal] = t.plan; Object.assign(script.texts, t.texts || {}); }
  writeFileSync(join(tmp, "script.json"), JSON.stringify(script));
  const token = "bench-" + Math.random().toString(36).slice(2);
  const port = 20000 + Math.floor(Math.random() * 20000);
  const engineArgs = ["-m", "browser.serve", "--port", String(port), "--extension-id", extId, "--thinker", "fake",
    "--thinker-script", join(tmp, "script.json"), "--db", join(tmp, "e.db"), "--steps-db", join(tmp, "steps.db")];
  if (!REAL) engineArgs.push("--fake");
  const engine = spawn("python3", engineArgs, { cwd: ROOT, env: { ...process.env, DESK_SENSE_TOKEN: token }, stdio: ["ignore", "inherit", "inherit"] });
  const engineUrl = `http://127.0.0.1:${port}`;
  const results = [];
  try {
    await waitHealthy(engineUrl, token, engine);
    await sw.evaluate(([u, t]) => chrome.storage.local.set({ engineUrl: u, token: t }), [engineUrl, token]);

    for (const task of tasks) {
      for (let run = 1; run <= RUNS; run++) {
        const page = await context.newPage();
        const url = pagesUrl + task.page;
        await page.goto(url);
        const tabId = await sw.evaluate((u) => chrome.tabs.query({}).then((ts) => ts.find((t) => t.url === u).id), url);
        const t0 = Date.now();
        await sw.evaluate(([g, id]) => { self.startTask(g, id, []); return true; }, [task.goal, tabId]);
        const asked = [];
        let state;
        for (;;) {
          state = await sw.evaluate(() => self.getState());
          if (state.pending) {
            const name = state.pending.action.name;
            asked.push(name);
            const yes = task.confirm[name] === true;
            await sw.evaluate((y) => self.answerConfirm(y), yes);
          } else if (!state.running && state.result) {
            break;
          } else if (Date.now() - t0 > 60000) {
            await sw.evaluate(() => self.stopTask());
            state.result = { op: "timeout" };
            break;
          }
          await sleep(50);
        }
        const seconds = (Date.now() - t0) / 1000;
        const passed = await page.evaluate((c) => { try { return !!eval(c); } catch { return false; } }, task.check);
        const mustAsk = (task.must_ask || []).every((n) => asked.includes(n));
        const actions = state.log.filter((e) => e.action).map((e) => e.action);
        const bySource = {};
        for (const a of actions) bySource[a.source || "?"] = (bySource[a.source || "?"] || 0) + 1;
        const success = passed && mustAsk;
        results.push({ task: task.id, run, success, end: state.result.op, why: state.result.why,
          seconds, steps: actions.length, sources: bySource, asked,
          ...(success ? {} : { trail: actions, page: await page.evaluate(() => JSON.stringify(window.__bench)) }) });
        await page.close();
      }
    }
  } finally {
    engine.kill();
    await context.close();
    pages.close();
  }

  const ok = results.filter((r) => r.success).length;
  for (const r of results) {
    console.log(`${r.success ? "PASS" : "FAIL"}  ${r.task.padEnd(15)} run ${r.run}  ${r.seconds.toFixed(2)} s  ${r.steps} steps  ` +
      `${JSON.stringify(r.sources)}  end=${r.end}${r.why ? " (" + r.why + ")" : ""}${r.asked.length ? "  asked: " + r.asked.join(", ") : ""}`);
  }
  const median = (xs) => { const s = [...xs].sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };
  const report = {
    mode: REAL ? "real-model" : "fake-model", suite: SUITE, runs: RUNS, measured_on: process.env.BENCH_MACHINE || "unlabelled machine",
    success: `${ok}/${results.length}`, median_seconds: median(results.map((r) => r.seconds)), results,
  };
  mkdirSync(join(ROOT, "reports", "browser"), { recursive: true });
  const name = `bench_${REAL ? "real" : "fake"}${SUITE === "exact" ? "" : "_" + SUITE}.json`;
  writeFileSync(join(ROOT, "reports", "browser", name), JSON.stringify(report, null, 2) + "\n");
  console.log(`\n${ok}/${results.length} passed, median ${report.median_seconds?.toFixed(2)} s per task`);
  process.exit(ok === results.length ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(2); });
