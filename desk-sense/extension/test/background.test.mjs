// background.js with fake chrome.* and a scripted engine, no network: node --test extension/test
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "background.js"), "utf8");

function harness({ actions, attachFails = false, engineStatus = 200, targetThrows = false }) {
  const calls = { cdp: [], posts: [], attached: 0, detached: 0 };
  let sig = 0;
  const page = {
    __dsAgent: {
      settle: async () => {},
      read: () => ({ host: "shop.example", title: "t", elements: [{ i: 0, role: "button", name: "Go" }] }),
      signature: () => "s" + sig,
      target: () => { if (targetThrows) throw new Error("element 0 is gone"); sig++; return { x: 10, y: 20 }; },
      focusForTyping: () => {},
      selectOption: () => true,
    },
  };
  const queue = [...actions];
  const ctx = {
    console, setTimeout, clearTimeout, Promise, JSON, Date, String, Error,
    window: page,
    fetch: async (url, opts) => {
      calls.posts.push({ path: new URL(url).pathname, body: JSON.parse(opts.body), auth: opts.headers.Authorization });
      if (engineStatus !== 200) return { ok: false, status: engineStatus, json: async () => ({ error: "missing or wrong token" }) };
      return { ok: true, status: 200, json: async () => queue.shift() || { op: "finish" } };
    },
    chrome: {
      sidePanel: { setPanelBehavior: () => Promise.resolve() },
      runtime: { sendMessage: () => Promise.resolve(), onMessage: { addListener: () => {} } },
      storage: { local: { get: async () => ({ engineUrl: "http://127.0.0.1:9", token: "tok" }) } },
      scripting: {
        executeScript: async ({ func, args, files }) => (files ? [] : [{ result: await func(...(args || [])) }]),
      },
      debugger: {
        attach: async () => { if (attachFails) throw new Error("Another debugger is attached"); calls.attached++; },
        detach: async () => { calls.detached++; },
        sendCommand: async (_t, method, params) => { calls.cdp.push([method, params]); },
      },
    },
  };
  ctx.self = ctx;
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return { self: ctx, calls };
}

test("a click is sent as trusted mouse input, reported, and the debugger is released", async () => {
  const { self, calls } = harness({ actions: [{ task: "t1", op: "click", index: 0 }, { op: "finish" }] });
  const res = await self.startTask("buy", 7, []);
  assert.equal(res.op, "finish");
  assert.deepEqual(calls.cdp.map(([m, p]) => p.type), ["mouseMoved", "mousePressed", "mouseReleased"]);
  assert.equal(calls.posts[0].path, "/v1/agent/start");
  assert.equal(calls.posts[0].auth, "Bearer tok");
  assert.deepEqual(calls.posts[1].body.last, { ok: true, changed: true });
  assert.equal(calls.attached, 1);
  assert.equal(calls.detached, 1);
});

test("typing uses insertText with the planned value", async () => {
  const { self, calls } = harness({ actions: [{ task: "t1", op: "type", index: 0, value: "Zurich" }] });
  await self.startTask("fly", 7, []);
  // Objects made inside the vm sandbox have its prototypes: compare as JSON.
  assert.equal(JSON.stringify(calls.cdp.at(-1)), JSON.stringify(["Input.insertText", { text: "Zurich" }]));
});

test("a risky action waits for the person; declining sends nothing to the page", async () => {
  const { self, calls } = harness({ actions: [{ task: "t1", op: "click", index: 0, confirm: "buys something" }, { op: "stop" }] });
  const run = self.startTask("buy", 7, []);
  for (let i = 0; i < 50 && !self.getState().pending; i++) await new Promise((r) => setTimeout(r, 5));
  assert.equal(self.getState().pending.reason, "buys something");
  assert.equal(self.answerConfirm(false), true);
  const res = await run;
  assert.equal(res.op, "stop");
  assert.deepEqual(calls.cdp, []);
  assert.deepEqual(calls.posts[1].body.last, { declined: true });
});

test("allowing a risky action performs it", async () => {
  const { self, calls } = harness({ actions: [{ task: "t1", op: "click", index: 0, confirm: "sends" }] });
  const run = self.startTask("send", 7, []);
  for (let i = 0; i < 50 && !self.getState().pending; i++) await new Promise((r) => setTimeout(r, 5));
  self.answerConfirm(true);
  await run;
  assert.equal(calls.cdp.length, 3);
});

test("a failed action is reported as not ok, and the loop continues", async () => {
  const { self, calls } = harness({ actions: [{ task: "t1", op: "click", index: 0 }], targetThrows: true });
  const res = await self.startTask("go", 7, []);
  assert.equal(res.op, "finish");
  assert.equal(calls.posts[1].body.last.ok, false);
  assert.match(calls.posts[1].body.last.error, /gone/);
});

test("engine refusal and debugger conflicts end the task as blocked, releasing what was taken", async () => {
  const refused = harness({ actions: [], engineStatus: 401 });
  const r1 = await refused.self.startTask("go", 7, []);
  assert.equal(r1.op, "blocked");
  assert.match(r1.why, /401/);
  assert.equal(refused.calls.detached, 1);
  const busy = harness({ actions: [], attachFails: true });
  const r2 = await busy.self.startTask("go", 7, []);
  assert.equal(r2.op, "blocked");
  assert.equal(busy.calls.detached, 0);
});

test("only one task runs at a time", async () => {
  const { self } = harness({ actions: [{ task: "t1", op: "click", index: 0, confirm: "x" }] });
  const first = self.startTask("a", 7, []);
  await assert.rejects(self.startTask("b", 7, []), /already running/);
  for (let i = 0; i < 50 && !self.getState().pending; i++) await new Promise((r) => setTimeout(r, 5));
  self.answerConfirm(false);
  await first;
});
