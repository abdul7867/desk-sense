// Task loop: read the page, ask the local engine for the next action, do it with trusted input
// events (chrome.debugger), report what happened, repeat. Risky actions wait for the person.
const MAX_STEPS = 80;
const DEFAULT_ENGINE = "http://127.0.0.1:8765";

chrome.sidePanel?.setPanelBehavior?.({ openPanelOnActionClick: true }).catch(() => {});

const state = { running: false, taskId: null, tabId: null, goal: "", log: [], pending: null, result: null };
let confirmResolver = null;

function publish() {
  chrome.runtime.sendMessage({ type: "state", state: snapshot() }).catch(() => {});
}
function snapshot() {
  return JSON.parse(JSON.stringify(state));
}
function note(entry) {
  state.log.push({ t: Date.now(), ...entry });
  if (state.log.length > 200) state.log.shift();
  publish();
}

async function engine(path, body) {
  const { engineUrl = DEFAULT_ENGINE, token = "" } = await chrome.storage.local.get(["engineUrl", "token"]);
  const resp = await fetch(engineUrl + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: JSON.stringify(body),
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(`engine ${resp.status}: ${JSON.stringify(data.error || data)}`);
  return data;
}

async function inPage(tabId, fn, ...args) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: fn, args });
  return res?.result;
}

const readPage = (tabId) => inPage(tabId, async () => { await window.__dsAgent.settle(); return window.__dsAgent.read(); });
const pageSignature = (tabId) => inPage(tabId, () => window.__dsAgent.signature());
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function cdp(tabId, method, params) {
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

async function click(tabId, index) {
  const { x, y } = await inPage(tabId, (i) => window.__dsAgent.target(i), index);
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: 1 });
  await cdp(tabId, "Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: 1 });
}

async function typeText(tabId, index, text) {
  await click(tabId, index);
  await inPage(tabId, (i) => window.__dsAgent.focusForTyping(i), index);
  await cdp(tabId, "Input.insertText", { text: text ?? "" });
}

async function perform(tabId, a) {
  if (a.op === "click") return click(tabId, a.index);
  if (a.op === "type") return typeText(tabId, a.index, a.value);
  if (a.op === "select") {
    const ok = await inPage(tabId, (i, v) => window.__dsAgent.selectOption(i, v), a.index, a.value);
    if (!ok) await click(tabId, a.index); // custom dropdown: open it, the next step picks the option
    return;
  }
  if (a.op === "scroll") return inPage(tabId, (d) => window.scrollBy(0, d * innerHeight * 0.8), a.direction === "up" ? -1 : 1);
  if (a.op === "wait") return sleep(600);
  throw new Error("unknown action " + a.op);
}

function askConfirm(a) {
  state.pending = { reason: a.confirm, action: a };
  publish();
  return new Promise((resolve) => { confirmResolver = resolve; });
}

self.answerConfirm = (yes) => {
  if (!confirmResolver) return false;
  const r = confirmResolver;
  confirmResolver = null;
  state.pending = null;
  publish();
  r(!!yes);
  return true;
};

const ENDINGS = new Set(["finish", "stop", "pause", "ask_user", "blocked", "refused"]);

async function run(goal, tabId, sites) {
  let attached = false;
  try {
    await chrome.debugger.attach({ tabId }, "1.3");
    attached = true;
    let page = await readPage(tabId);
    let a = await engine("/v1/agent/start", { goal, sites, page });
    state.taskId = a.task || null;
    for (let n = 0; n < MAX_STEPS; n++) {
      note({ action: a });
      if (ENDINGS.has(a.op)) return a;
      if (a.confirm && !(await askConfirm(a))) {
        a = await engine("/v1/agent/step", { task: state.taskId, page, last: { declined: true } });
        continue;
      }
      const before = await pageSignature(tabId).catch(() => null);
      let last = { ok: true };
      try {
        await perform(tabId, a);
      } catch (e) {
        last = { ok: false, error: String(e.message || e) };
      }
      page = await readPage(tabId);
      const after = await pageSignature(tabId).catch(() => null);
      last.changed = before !== after;
      a = await engine("/v1/agent/step", { task: state.taskId, page, last });
    }
    return { op: "blocked", why: "step limit reached" };
  } finally {
    if (attached) await chrome.debugger.detach({ tabId }).catch(() => {});
  }
}

self.startTask = async (goal, tabId, sites) => {
  if (state.running) throw new Error("a task is already running");
  Object.assign(state, { running: true, taskId: null, tabId, goal, log: [], pending: null, result: null });
  publish();
  const t0 = Date.now();
  try {
    state.result = await run(goal, tabId, sites);
  } catch (e) {
    state.result = { op: "blocked", why: String(e.message || e) };
  }
  state.result.seconds = (Date.now() - t0) / 1000;
  state.running = false;
  note({ result: state.result });
  return state.result;
};

self.getState = snapshot;

self.stopTask = async () => {
  if (state.taskId) await engine("/v1/agent/stop", { task: state.taskId }).catch(() => {});
  self.answerConfirm(false);
};

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg.type === "start") {
    self.startTask(msg.goal, msg.tabId, msg.sites).catch(() => {});
    reply({ ok: true });
  } else if (msg.type === "confirm") {
    reply({ ok: self.answerConfirm(msg.yes) });
  } else if (msg.type === "stop") {
    self.stopTask().then(() => reply({ ok: true }));
    return true;
  } else if (msg.type === "get") {
    reply(snapshot());
  }
  return false;
});
