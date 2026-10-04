// Run from the repository root:
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_history_ui.js
// Uses the actual frontend functions with memory-only DOM/network boundaries.
// No HTTP requests, workspace writes, browser storage, or external dependencies.
var source = readFile("static/app.js");
var state = {
  mutations: 0,
  historyBusy: false,
  history: { undo_label: "编辑人物", redo_label: null },
  workspace: {
    generations: [],
    people: { a: { id: "a" }, b: { id: "b" } },
    relationships: [],
  },
  perspective: true,
  selectionA: "a",
  selectionB: "b",
  selectionTarget: "b",
};
var checks = 0;
var prefetched = 0;
var requests = 0;
var domQueries = 0;
var dialogOpen = false;
var closeResult = true;
var personEditor = { saving: false };
var relationshipSaving = false;
var fetch;

function assert(value, name) {
  checks += 1;
  if (!value) throw new Error(name);
}
async function loadRuntimeConfig() { state.config = await api("/api/config"); }
function canEditWorkspace() { return true; }
function invalidateExperimentalTasks() {}
function renderWriteAccess() {}
function renderHistory() {}
function renderWorkspaceSaveState() {}
function render() {}
function renderSelection() {}
function showToast() {}
function cancelActivePersonDrag() {}
function invalidateRelationshipTasks() { state.relationshipCopyText = null; }
function prefetchRelationshipPath() { prefetched += 1; }
function $(selector) {
  domQueries += 1;
  return selector === "dialog:modal" ? null : { open: dialogOpen };
}
async function closePersonDialog() { return closeResult; }
function response(value) {
  return { ok: true, json: async () => value };
}
async function rejects(promise) {
  try { await promise; return false; }
  catch { return true; }
}
function extract(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) {
    throw new Error("Frontend function boundary changed: " + startMarker);
  }
  return source.slice(start, end);
}

eval(extract("async function api(", "function hideToast("));
eval(extract("function workspaceFrom(", "function generations("));
eval(extract("function people()", "function peopleInGeneration("));
eval(extract("function relationships()", "function personName("));
eval(extract("async function loadWorkspace(", "function renderHistory("));
eval(extract("async function travelHistory(", "function requestDraw("));
eval(extract("function openGenerationDialog(", "function closeGenerationDialog("));
eval(extract("async function openPersonDialog(", "async function closePersonDialog("));
eval(extract("async function openRelationshipDialog(", "function closeRelationshipDialog("));
eval(extract("function activatePerson(", "async function selectLinkPerson("));

async function run() {
  let resolveFetch;
  fetch = () => {
    requests += 1;
    return new Promise((resolve) => { resolveFetch = resolve; });
  };
  const first = api("/api/people", { method: "POST" });
  assert(state.mutations === 1, "first mutation acquires the shared write lock");
  assert(await rejects(api("/api/people", { method: "PATCH" })),
    "a concurrent mutation is rejected");
  assert(requests === 1, "a rejected concurrent mutation never reaches fetch");
  resolveFetch(response({ history: { undo_label: "添加人物", redo_label: null } }));
  await first;
  assert(state.mutations === 0, "successful mutation releases the write lock");
  assert(state.history.undo_label === "添加人物", "successful response updates history labels");

  state.historyBusy = true;
  fetch = async () => response({});
  assert(await rejects(api("/api/people", { method: "POST" })),
    "history navigation blocks ordinary mutations");
  await api("/api/history/undo", { method: "POST" });
  await api("/api/workspace");
  assert(state.mutations === 0, "history requests and reads remain available during history navigation");

  state.historyBusy = false;
  fetch = async () => { throw new Error("offline"); };
  assert(await rejects(api("/api/people", { method: "PATCH" })),
    "network failure rejects the mutation");
  assert(state.mutations === 0, "network failure releases the write lock");

  state.history = { undo_label: "编辑人物", redo_label: null };
  fetch = async (path, options) => {
    if (options.method === "POST") throw new Error("failed undo");
    if (path === "/api/config") return response({ experimental_features_enabled: false, experimental_cross_generation: false, read_only: false, read_only_reason: null });
    if (path === "/api/workspace") {
      return response({
        generations: [],
        people: { a: { id: "a" }, b: { id: "b" } },
        relationships: [],
      });
    }
    return response({ undo_label: "编辑人物", redo_label: null });
  };
  await travelHistory("undo");
  assert(prefetched === 1, "failed undo followed by successful synchronization recalculates A/B");
  assert(state.selectionA === "a" && state.selectionB === "b",
    "synchronization preserves valid A/B selections");
  assert(state.historyBusy === false && state.mutations === 0,
    "history recovery releases both operation locks");

  fetch = async (path, options) => {
    if (options.method === "POST") throw new Error("failed undo");
    if (path === "/api/config") return response({ experimental_features_enabled: false, experimental_cross_generation: false, read_only: false, read_only_reason: null });
    if (path === "/api/workspace") {
      return response({ generations: [], people: { b: { id: "b" } }, relationships: [] });
    }
    return response({ undo_label: "编辑人物", redo_label: null });
  };
  await travelHistory("undo");
  assert(state.selectionA === null && state.selectionB === "b",
    "synchronization clears deleted people from the selection");

  dialogOpen = true;
  closeResult = false;
  requests = 0;
  fetch = async () => { requests += 1; return response({}); };
  await travelHistory("undo");
  assert(requests === 0 && !state.historyBusy,
    "canceling draft discard sends no history request and releases the lock");

  dialogOpen = false;
  const guardedEntries = [
    ["generation editor", () => openGenerationDialog("rename", "generation")],
    ["person editor", () => openPersonDialog("generation", "a")],
    ["relationship editor", () => openRelationshipDialog("relationship")],
    ["keyboard person activation", () => activatePerson("a")],
  ];
  for (const lock of ["historyBusy", "mutations"]) {
    state.historyBusy = lock === "historyBusy";
    state.mutations = lock === "mutations" ? 1 : 0;
    for (const [name, open] of guardedEntries) {
      domQueries = 0;
      state.focusedPersonId = "previous";
      state.editingRelationshipId = "previous-relationship";
      await open();
      assert(domQueries === 0 &&
        state.focusedPersonId === "previous" &&
        state.editingRelationshipId === "previous-relationship",
      lock + " blocks " + name + " before opening stale UI");
    }
  }
  state.historyBusy = false;
  state.mutations = 0;
  print("PASS " + checks + " frontend history assertions (remote JSC, memory-only)");
}

let completed = false, failure = null;
run().then(() => { completed = true; }, (error) => { failure = error; });
drainMicrotasks();
if (failure) throw failure;
if (!completed) throw new Error("History UI assertions did not finish");
