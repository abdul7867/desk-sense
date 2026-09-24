// Injected on demand into the task's tab. Builds the numbered element table the engine decides on,
// and does the small DOM jobs the debugger protocol can't (scroll into view, select an <option>).
// Password values are never read. Element refs stay in the page; only the table leaves it.
(() => {
  if (window.__dsAgent) return;

  const INTERACTIVE = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary",
    "[contenteditable=''], [contenteditable=true]",
    "[role=button],[role=link],[role=checkbox],[role=radio],[role=tab],[role=menuitem],[role=option]",
    "[role=switch],[role=combobox],[role=textbox],[role=searchbox],[role=listbox]",
  ].join(",");
  const TEXT_INPUTS = new Set(["text", "email", "search", "tel", "url", "number", "password", "date", ""]);
  const NAME_MAX = 80;

  function* walk(root) {
    for (const el of root.querySelectorAll("*")) {
      yield el;
      if (el.shadowRoot) yield* walk(el.shadowRoot);
    }
  }

  function roleOf(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a") return "link";
    if (tag === "button" || tag === "summary") return "button";
    if (tag === "select") return "select";
    if (tag === "textarea") return "textarea";
    if (el.isContentEditable) return "textbox";
    if (tag === "input") {
      const t = (el.getAttribute("type") || "").toLowerCase();
      if (t === "checkbox" || t === "radio") return t;
      if (t === "search") return "searchbox";
      if (TEXT_INPUTS.has(t)) return "textbox";
      return "button"; // submit, button, reset, image
    }
    return "button";
  }

  const squash = (s) => (s || "").replace(/\s+/g, " ").trim().slice(0, NAME_MAX);

  // A label's own words, without the text of controls inside it (a <select>'s options, say).
  function labelText(label) {
    const copy = label.cloneNode(true);
    copy.querySelectorAll("input,select,textarea,button").forEach((c) => c.remove());
    return squash(copy.textContent);
  }

  function nameOf(el) {
    const aria = el.getAttribute("aria-label");
    if (aria) return squash(aria);
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(/\s+/).map((id) => el.getRootNode().getElementById?.(id)?.innerText || "").join(" ");
      if (t.trim()) return squash(t);
    }
    if (el.id) {
      const lab = el.getRootNode().querySelector?.(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return labelText(lab);
    }
    const wrap = el.closest("label");
    if (wrap && wrap !== el) return labelText(wrap);
    if (el.tagName === "INPUT" && ["submit", "button", "reset"].includes(el.type)) return squash(el.value);
    return squash(el.placeholder || el.innerText || el.title || el.alt || el.getAttribute("name") || "");
  }

  function valueOf(el, role) {
    if (el.type === "password") return el.value ? "(filled)" : "";
    if (role === "checkbox" || role === "radio" || role === "switch")
      return (el.checked ?? el.getAttribute("aria-checked") === "true") ? "checked" : "unchecked";
    if (el.tagName === "SELECT") return squash(el.selectedOptions[0]?.text || "");
    if ("value" in el && typeof el.value === "string" && el.tagName !== "BUTTON") return squash(el.value);
    if (el.isContentEditable) return squash(el.innerText);
    return "";
  }

  function regionOf(el) {
    if (el.closest("dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]")) return "dialog";
    const r = el.closest("header,nav,footer,main,form,aside");
    return r ? r.tagName.toLowerCase() : "";
  }

  function visible(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    if (r.bottom < -innerHeight || r.top > 2 * innerHeight) return false; // on screen, or within one screen
    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none" || Number(s.opacity) === 0) return false;
    return !el.closest("[aria-hidden=true],[inert]");
  }

  function disabled(el) {
    return el.disabled || el.getAttribute("aria-disabled") === "true" || !!el.closest("fieldset[disabled]");
  }

  let seen = new Set();
  let els = [];

  function read() {
    const rows = [];
    const nextSeen = new Set();
    els = [];
    for (const el of walk(document)) {
      if (!el.matches(INTERACTIVE) || !visible(el)) continue;
      const role = roleOf(el);
      const name = nameOf(el);
      const key = role + "|" + name;
      nextSeen.add(key);
      const row = { i: els.length, role, name, value: valueOf(el, role), region: regionOf(el) };
      if (disabled(el)) row.disabled = true;
      if (el.type === "password") row.type = "password";
      if (el.type === "submit" || (el.tagName === "BUTTON" && el.type === "submit" && el.form)) {
        row.type = "submit";
        try { row.form_host = new URL(el.form?.action || location.href).hostname; } catch (e) { /* bad action */ }
      }
      const ac = el.getAttribute("autocomplete");
      if (ac) row.autocomplete = ac;
      if (seen.size && !seen.has(key)) row.new = true;
      els.push(el);
      rows.push(row);
    }
    seen = nextSeen;
    const dialog = rows.some((r) => r.region === "dialog");
    const busy = document.readyState !== "complete" || !!document.querySelector("[aria-busy=true],[role=progressbar]:not([hidden])");
    const moreBelow = scrollY + innerHeight < document.documentElement.scrollHeight - 4;
    return {
      host: location.hostname, url: location.href, title: document.title, dialog, busy,
      more_below: moreBelow, elements: rows,
    };
  }

  // Resolves once the DOM has been quiet for `quietMs`, or after `maxMs`.
  function settle(quietMs = 150, maxMs = 2000) {
    return new Promise((resolve) => {
      let timer = setTimeout(done, quietMs);
      const stop = setTimeout(done, maxMs);
      const mo = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(done, quietMs); });
      mo.observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
      function done() { mo.disconnect(); clearTimeout(timer); clearTimeout(stop); resolve(); }
    });
  }

  // Did the last action change anything? URL, visible text and form state, hashed (FNV-1a).
  function signature() {
    const fields = [...document.querySelectorAll("input,select,textarea")]
      .map((e) => (e.type === "password" ? e.value.length : e.type === "checkbox" || e.type === "radio" ? e.checked : e.value));
    const s = location.href + "\u0000" + document.body.innerText + "\u0000" + fields.join("\u0001");
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
    return (h >>> 0).toString(16) + ":" + s.length;
  }

  function target(i) {
    const el = els[i];
    if (!el || !el.isConnected) throw new Error("element " + i + " is gone");
    el.scrollIntoView({ block: "center", inline: "center" });
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }

  function focusForTyping(i) {
    const el = els[i];
    el.focus();
    if (typeof el.select === "function") el.select();
    else if (el.isContentEditable) document.getSelection().selectAllChildren(el);
  }

  function selectOption(i, text) {
    const el = els[i];
    if (el.tagName !== "SELECT") return false;
    const want = (text || "").trim().toLowerCase();
    const opt = [...el.options].find((o) => o.text.trim().toLowerCase() === want || o.value.toLowerCase() === want)
      || [...el.options].find((o) => o.text.trim().toLowerCase().startsWith(want));
    if (!opt) return false;
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set.call(el, opt.value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  window.__dsAgent = { read, settle, signature, target, focusForTyping, selectOption };
})();
