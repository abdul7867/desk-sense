// content.js in a real (headless) Chromium page, no network: node --test extension/test
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execSync } from "node:child_process";
import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const CONTENT = readFileSync(join(HERE, "..", "content.js"), "utf8");
const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require("playwright")); } catch { ({ chromium } = require(join(execSync("npm root -g").toString().trim(), "playwright"))); }

let browser, page;
before(async () => { browser = await chromium.launch(); page = await browser.newPage(); });
after(async () => { await browser.close(); });

async function load(html) {
  await page.setContent(`<!doctype html><title>t</title><body>${html}</body>`);
  await page.addScriptTag({ content: CONTENT });
  return page.evaluate(() => window.__dsAgent.read());
}
const byName = (table, name) => table.elements.find((e) => e.name === name);

test("names come from aria-label, labels, placeholder and text, like the converter", async () => {
  const t = await load(`
    <button aria-label="Close dialog">x</button>
    <label for="f">From</label><input id="f">
    <label>Topic <select><option>Choose</option><option>Billing</option></select></label>
    <input placeholder="Search products">
    <a href="#">Help centre</a>
    <input type="submit" value="Send">`);
  assert.equal(byName(t, "Close dialog").role, "button");
  assert.equal(byName(t, "From").role, "textbox");
  assert.equal(byName(t, "Topic").role, "select");
  assert.equal(byName(t, "Topic").value, "Choose");
  assert.equal(byName(t, "Search products").role, "textbox");
  assert.equal(byName(t, "Help centre").role, "link");
  assert.equal(byName(t, "Send").type, "submit");
});

test("secrets never leave the page", async () => {
  await load(`<input type="password" aria-label="Password"><input aria-label="Card number" autocomplete="cc-number">
              <input aria-label="OTP"><input aria-label="City">`);
  await page.fill("[aria-label=Password]", "hunter2");
  await page.fill("[aria-label='Card number']", "4111111111111111");
  await page.fill("[aria-label=OTP]", "123456");
  await page.fill("[aria-label=City]", "Pune");
  const t = await page.evaluate(() => window.__dsAgent.read());
  const dump = JSON.stringify(t);
  for (const secret of ["hunter2", "4111111111111111", "123456"]) assert.ok(!dump.includes(secret), secret);
  assert.equal(byName(t, "Password").value, "(filled)");
  assert.equal(byName(t, "Card number").value, "(filled)");
  assert.equal(byName(t, "City").value, "Pune");
});

test("hidden, invisible and inert elements are left out; disabled is flagged", async () => {
  const t = await load(`<button>Visible</button><button style="display:none">Gone</button>
    <div aria-hidden="true"><button>Hidden</button></div><button disabled>Off</button>
    <input type="hidden" value="x">`);
  const names = t.elements.map((e) => e.name);
  assert.deepEqual(names.filter((n) => ["Gone", "Hidden"].includes(n)), []);
  assert.equal(byName(t, "Off").disabled, true);
  assert.ok(names.includes("Visible"));
});

test("dialogs, open shadow roots and new elements are reported", async () => {
  await load(`<button>Before</button><div id="host"></div>`);
  await page.evaluate(() => {
    document.getElementById("host").attachShadow({ mode: "open" }).innerHTML = "<button>Inside shadow</button>";
    const d = document.createElement("dialog"); d.setAttribute("open", ""); d.innerHTML = "<button>Accept all</button>";
    document.body.append(d);
  });
  const t = await page.evaluate(() => window.__dsAgent.read());
  assert.ok(byName(t, "Inside shadow"));
  assert.equal(byName(t, "Accept all").region, "dialog");
  assert.equal(t.dialog, true);
  await page.evaluate(() => { const b = document.createElement("button"); b.textContent = "Later"; document.body.append(b); });
  const t2 = await page.evaluate(() => window.__dsAgent.read());
  assert.equal(byName(t2, "Later").new, true);
  assert.equal(byName(t2, "Before").new, undefined);
});

test("forms posting elsewhere carry their host", async () => {
  const t = await load(`<form action="https://pay.example.net/go"><button type="submit">Pay</button></form>`);
  assert.equal(byName(t, "Pay").form_host, "pay.example.net");
});

test("selectOption picks by visible text and fires change; signature tracks text and form state", async () => {
  await load(`<select aria-label="Language"><option value="en">English</option><option value="hi">Hindi</option></select><p id="c">Cart: 0</p>`);
  await page.evaluate(() => { window.changed = 0; document.querySelector("select").addEventListener("change", () => window.changed++); });
  const s0 = await page.evaluate(() => window.__dsAgent.signature());
  const i = (await page.evaluate(() => window.__dsAgent.read())).elements.findIndex((e) => e.name === "Language");
  assert.equal(await page.evaluate((i) => window.__dsAgent.selectOption(i, "hindi"), i), true);
  assert.equal(await page.evaluate(() => [document.querySelector("select").value, window.changed].join()), "hi,1");
  const s1 = await page.evaluate(() => window.__dsAgent.signature());
  assert.notEqual(s0, s1);
  await page.evaluate(() => { document.getElementById("c").textContent = "Cart: 1"; }); // same length text change
  assert.notEqual(await page.evaluate(() => window.__dsAgent.signature()), s1);
  assert.equal(await page.evaluate((i) => window.__dsAgent.selectOption(i, "Tamil"), i), false);
});

test("injecting twice keeps one agent", async () => {
  await load(`<button>A</button>`);
  await page.evaluate(() => { window.__dsAgent.marker = 1; });
  await page.addScriptTag({ content: CONTENT });
  assert.equal(await page.evaluate(() => window.__dsAgent.marker), 1);
});
