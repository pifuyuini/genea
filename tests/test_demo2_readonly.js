// Actual static transport and generated app functions; no DOM rendering or Python server.
const assets = {
  "workspace.json": JSON.parse(readFile("docs/demo2/workspace.json")),
  "paths.json": JSON.parse(readFile("docs/demo2/paths.json")),
  "queries.json": JSON.parse(readFile("docs/demo2/queries.json")),
  "check.json": JSON.parse(readFile("docs/demo2/check.json")),
};
let checks = 0, requests = [];
function assert(condition, message) { checks += 1; if (!condition) throw new Error(message); }
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function equal(actual, expected) {
  if (actual === expected) return true;
  if (actual === null || expected === null || typeof actual !== "object" || typeof expected !== "object") return false;
  const a = Object.keys(actual).sort(), b = Object.keys(expected).sort();
  return JSON.stringify(a) === JSON.stringify(b) && a.every((key) => equal(actual[key], expected[key]));
}
class URLSearchParams {
  constructor(search) { this.values = String(search || "").replace(/^\?/, "").split("&").filter(Boolean).map((part) => {
    const separator = part.indexOf("=");
    return [decodeURIComponent(separator < 0 ? part : part.slice(0, separator)), decodeURIComponent(separator < 0 ? "" : part.slice(separator + 1))];
  }); }
  get(key) { return this.values.find((entry) => entry[0] === key)?.[1] ?? null; }
}
class URL {
  constructor(value, base) {
    value = String(value); base = String(base || "https://example.github.io/genea/demo2/");
    const origin = base.match(/^https?:\/\/[^/]+/)[0];
    let absolute = /^https?:\/\//.test(value) ? value : origin + (value.startsWith("/") ? value : base.slice(origin.length).split(/[?#]/)[0].replace(/[^/]*$/, "") + value);
    const match = absolute.match(/^(https?:\/\/[^/]+)([^?#]*)(\?[^#]*)?(#.*)?$/);
    const parts = [];
    for (const part of match[2].split("/")) { if (part === "..") parts.pop(); else if (part && part !== ".") parts.push(part); }
    this.pathname = "/" + parts.join("/") + (match[2].endsWith("/") || match[2].endsWith("/.") ? "/" : "");
    this.origin = match[1]; this.href = this.origin + this.pathname + (match[3] || "") + (match[4] || "");
  }
  toString() { return this.href; }
}
var document = { currentScript: { src: "https://example.github.io/genea/demo2/readonly-api.js" } };
var window = globalThis;
var fetch = async (url) => {
  const value = String(url);
  requests.push(value);
  const name = value.slice(value.lastIndexOf("/") + 1);
  assert(value === "https://example.github.io/genea/demo2/" + name && assets[name], "Asset escaped /genea/demo2/: " + value);
  return { ok: true, json: async () => copy(assets[name]) };
};
load("demo2/query-engine.js");
load("demo2/readonly-api.js");
const appSource = readFile("docs/demo2/app.js");
var state = { config: { read_only: true, read_only_reason: "公开演示仅供查看" }, workspaceLoaded: true };
function renderWorkspaceSaveState() {}
function personName(id) { return assets["workspace.json"].people[id]?.name || "未知人物"; }
eval(appSource.match(/async function api\(path, options = \{\}\) \{\n[\s\S]*?\n\}/)[0]);
eval(appSource.match(/function relationshipCopySummary\([\s\S]*?\n\}/)[0]);
async function rejects(task, message, status) {
  let caught = false;
  try { await task(); } catch (error) { caught = true; if (status) assert(error.status === status, message + ": status"); }
  assert(caught, message);
}
async function run() {
  const before = JSON.stringify(assets), adapter = GeneaDemo;
  let config = await api("/api/config");
  assert(config.experimental_features_enabled && config.read_only && config.read_only_reason.includes("本次浏览"), "Initial demo config is experimental and permanently read-only");
  const workspace = await api("/api/workspace"); workspace.people.person_founder.name = "Changed in caller";
  assert(assets["workspace.json"].people.person_founder.name !== "Changed in caller", "Cached workspace is independent of callers");
  assert(equal(await api("/api/history"), { undo_label: null, redo_label: null }), "No editable history");
  for (const source of Object.keys(assets["paths.json"])) {
    for (const target of Object.keys(assets["paths.json"][source])) {
      assert(equal(await api("/api/path?from=" + source + "&to=" + target), assets["paths.json"][source][target]), "Adapter returns the complete directional pair");
    }
  }
  const result = await api("/api/query", { method: "POST", body: JSON.stringify({ text: "奥雷里亚诺上校的子女有哪些" }) });
  assert(result.results.length === 18 && result.status === "success", "Browser query lists all eighteen sons");
  assert(equal(await api("/api/check"), assets["check.json"]), "Report is the generated inspection output");
  const mutations = [["POST", "/api/people"], ["PATCH", "/api/people/person_founder"], ["DELETE", "/api/people/person_founder"],
    ["POST", "/api/generations"], ["POST", "/api/relationships"], ["POST", "/api/photos"],
    ["POST", "/api/history/undo"], ["POST", "/api/check/fix"]];
  const count = requests.length;
  for (const [method, path] of mutations) {
    await rejects(() => adapter.request(path, { method, body: "{}" }), "Adapter rejects " + method + " " + path, 403);
    await rejects(() => api(path, { method, body: "{}" }), "Actual app API rejects " + method + " " + path);
  }
  assert(requests.length === count, "Denied writes never call fetch");
  await rejects(() => adapter.request("/api/config", { method: "POST", body: '{"experimental_features_enabled":"yes"}' }), "Invalid config leaves state unchanged", 400);
  assert((await adapter.request("/api/config")).experimental_features_enabled, "Invalid config cannot disable the experiment");
  config = await api("/api/config", { method: "POST", body: '{"experimental_features_enabled":false}' });
  assert(!config.experimental_features_enabled && config.read_only, "Turning experiments off never enables editing");
  const ordinary = await api("/api/path?from=person_aureliano_jose&to=person_amaranta");
  assert(!ordinary.direct_relationship && ordinary.path_text === "养母", "Ordinary mode returns only the original chain");
  await rejects(() => adapter.request("/api/query", { method: "POST", body: '{"text":"丽贝卡的养父母有哪些"}' }), "Disabled query is unavailable", 403);
  await rejects(() => adapter.request("/api/check"), "Disabled inspection is unavailable", 403);
  config = await adapter.request("/api/config", { method: "POST", body: '{"experimental_features_enabled":true}' });
  assert(config.experimental_features_enabled && config.read_only, "Turning experiments back on never enables editing");
  const enriched = await api("/api/path?from=person_aureliano_jose&to=person_amaranta");
  assert(enriched.direct_relationship.results[0].label === "姑母", "Experiment shows the proven blood relationship");
  const copied = relationshipCopySummary(enriched, enriched.path_text, "person_aureliano_jose", "person_amaranta");
  assert(copied.endsWith("的：养母") && !copied.includes("姑母"), "Copy still contains only the registered chain");
  await rejects(() => adapter.request("/api/path?from=unknown&to=person_founder"), "Missing person is reported", 404);
  const saved = window.GeneaDemo; delete window.GeneaDemo;
  await rejects(() => api("/api/workspace"), "Missing adapter cannot fall back to root APIs");
  window.GeneaDemo = saved;
  assert(requests.length === count, "No service APIs or extra fetches were made");
  const fresh = GeneaDemoTransport.create((name) => Promise.resolve(assets[name]), GeneaDemoQuery);
  assert((await fresh.request("/api/config")).experimental_features_enabled, "A fresh browser session restores the default");
  for (const route of ["/api/query", "/api/check", "/api/path?from=person_founder&to=person_ursula"]) {
    let release;
    const gate = new Promise((resolve) => { release = resolve; });
    const delayed = GeneaDemoTransport.create((name) => gate.then(() => assets[name]), GeneaDemoQuery);
    const pending = delayed.request(route, route === "/api/query" ? { method: "POST", body: '{"text":"奥雷里亚诺上校的子女有哪些"}' } : {});
    await delayed.request("/api/config", { method: "POST", body: '{"experimental_features_enabled":false}' });
    await delayed.request("/api/config", { method: "POST", body: '{"experimental_features_enabled":true}' });
    release();
    await rejects(() => pending, "Late result is rejected after experiment changes: " + route, 409);
  }
  assert(JSON.stringify(assets) === before, "All demo fixtures remain unchanged");
  print("PASS " + checks + " static adapter/app API assertions; all 2116 pairs and delayed config switches");
}
run().catch((error) => { print("FAIL " + error.stack); throw error; });
