const $ = (id) => document.getElementById(id);

async function loadSettings() {
  const { engineUrl, token } = await chrome.storage.local.get(["engineUrl", "token"]);
  if (engineUrl) $("engineUrl").value = engineUrl;
  if (token) $("token").value = token;
  else $("pairing").open = true;
}

$("save").onclick = async () => {
  await chrome.storage.local.set({ engineUrl: $("engineUrl").value.trim(), token: $("token").value.trim() });
  $("pairing").open = false;
};

$("task").onsubmit = async (e) => {
  e.preventDefault();
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url?.startsWith("http")) return render({ result: { op: "blocked", why: "open a web page first" } });
  const origin = new URL(tab.url).origin + "/*";
  // Site access is granted one site at a time, by this click.
  const granted = await chrome.permissions.request({ origins: [origin] }).catch(() => false);
  if (!granted) return render({ result: { op: "blocked", why: "site access was not granted" } });
  const sites = $("sites").value.split(/[\s,]+/).filter(Boolean);
  chrome.runtime.sendMessage({ type: "start", goal: $("goal").value.trim(), tabId: tab.id, sites });
};

$("stop").onclick = () => chrome.runtime.sendMessage({ type: "stop" });
$("allow").onclick = () => chrome.runtime.sendMessage({ type: "confirm", yes: true });
$("decline").onclick = () => chrome.runtime.sendMessage({ type: "confirm", yes: false });

function describe(a) {
  if (!a) return "";
  const target = a.name ? ` “${a.name}”` : a.index !== undefined ? ` #${a.index}` : "";
  const value = a.value ? ` ← “${a.value}”` : "";
  const why = a.why || a.message ? ` — ${a.why || a.message}` : "";
  return `${a.op}${target}${value}${why}`;
}

function render(s) {
  $("status").textContent = s.running ? "working" : s.result ? s.result.op : "idle";
  $("start").disabled = !!s.running;
  $("confirm").hidden = !s.pending;
  if (s.pending) {
    $("confirmReason").textContent = s.pending.reason;
    $("confirmAction").textContent = describe(s.pending.action);
  }
  const log = $("log");
  log.replaceChildren();
  for (const entry of s.log || []) {
    const li = document.createElement("li");
    const a = entry.action || entry.result;
    const src = document.createElement("span");
    src.className = "src";
    src.textContent = a.source ? a.source + " " : "";
    li.append(src, describe(a) + (entry.result?.seconds ? ` (${entry.result.seconds.toFixed(1)} s)` : ""));
    log.append(li);
  }
  if (s.result && !(s.log || []).length) {
    const li = document.createElement("li");
    li.textContent = describe(s.result);
    log.append(li);
  }
}

chrome.runtime.onMessage.addListener((msg) => { if (msg.type === "state") render(msg.state); });
chrome.runtime.sendMessage({ type: "get" }).then(render).catch(() => {});
loadSettings();
