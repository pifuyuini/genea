// Run on the remote Mac from the repository root:
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_workspace_ui.js
// Exercises the actual app functions against memory-only DOM and network boundaries.
var source = readFile("static/app.js");
var checks = 0;
function assert(value, name) { checks += 1; if (!value) throw new Error(name); }
function extract(startMarker, endMarker) {
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error("Function boundary changed: " + startMarker);
  return source.slice(start, end);
}
function element(tag = "div") {
  const values = new Set(), attributes = {};
  return {
    tagName: tag, children: [], dataset: {}, style: {}, hidden: true, open: false,
    textContent: "", clientWidth: 1000, clientHeight: 700, listeners: {},
    classList: {
      add: (...items) => items.forEach((item) => values.add(item)),
      remove: (...items) => items.forEach((item) => values.delete(item)),
      contains: (item) => values.has(item),
      toggle(item, force) { const next = force === undefined ? !values.has(item) : force; next ? values.add(item) : values.delete(item); return next; },
    },
    setAttribute(name, value) { attributes[name] = String(value); },
    getAttribute: (name) => attributes[name] ?? null,
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    contains(candidate) { return this.children.includes(candidate); },
    focus() { document.activeElement = this; },
    addEventListener(name, callback) { this.listeners[name] = callback; },
    matches: () => false,
    getBoundingClientRect() { return this.rect || { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight }; },
  };
}
var document = { body: element("body"), activeElement: null, createElement: element };
var nodes = new Map();
function $(selector) { if (!nodes.has(selector)) nodes.set(selector, element()); return nodes.get(selector); }
function $$(selector) { return selector === ".person-node" ? [] : []; }
var compact = false, draft = false, resized = 0, draws = 0, targetCamera = null;
var state = {
  workspace: {
    generations: [{ id: "child", name: "同辈", position: 1 }, { id: "parent", name: "父辈", position: 0 }],
    people: {
      a: { id: "a", name: "张甲", gender: "male", generation_id: "parent", order: 0 },
      b: { id: "b", name: "李乙", gender: "female", generation_id: "child", order: 0 },
    },
    relationships: [{ id: "r1", parent_id: "a", child_id: "b" }],
  },
  mutations: 0, historyBusy: false, history: {},
  workspaceLoaded: false, workspaceLoadFailed: false, connectionFailed: false, saveFailed: false,
  focusedGenerationId: null,
  selectionA: null, selectionB: null, focusedPersonId: null, linkSource: null,
  camera: { x: 0, y: 0, scale: 0.5 }, editingPersonId: null,
};
var CSS = { escape: (value) => value };
function matchMedia() { return { matches: compact }; }
function personHasChanges() { return draft; }
function handleCameraResize() { resized += 1; }
function closeGenerationMenu() { $("#generation-menu").hidden = true; }
function closeSearchResults() { $("#search-results").hidden = true; }
function renderHistory() {}
function requestDraw() { draws += 1; }
function moveCameraTo(value) { targetCamera = value; }
function clampCameraScale(value) { return Math.min(2.25, Math.max(0.2, value)); }
function beginPersonPointer() {}
function setActiveRelationshipPerson() {}
function clearActiveRelationshipPerson() {}
function activatePerson() {}
var fetch;
eval(extract("function createIcon(", "async function api("));
eval(extract("async function api(", "function hideToast("));
eval(extract("function generations()", "async function loadWorkspace("));
eval(extract("function renderWorkspaceSaveState()", "const nodeMotions ="));
eval(extract("function getCameraViewport(", "function clampCameraScale("));
eval(extract("function stageBox(", "function spreadRelationshipPorts("));
eval(extract("function focusGenerationInCanvas(", "function focusCurrentPerson("));
eval(extract("function createPersonNode(", "function openGenerationDialog("));

async function run() {
  renderWorkspaceSaveState();
  assert($("#workspace-save-state").textContent === "正在载入", "unloaded data is not advertised as saved");
  state.workspaceLoaded = true;
  renderWorkspaceChrome();
  assert($("#workspace-people-count").textContent === 2, "people counter derives from the workspace");
  assert($("#workspace-generation-count").textContent === 2, "generation counter derives from the workspace");
  assert($("#workspace-relationship-count").textContent === 1, "relationship counter derives from the workspace");
  const navigation = $("#generation-navigation");
  assert(navigation.children[0].dataset.generationId === "parent", "navigation follows ordered generations, not source order");
  assert(navigation.children[0].children[0].textContent === "01", "navigation ordinal uses two digits");
  assert(navigation.children[0].children[1].textContent === "父辈", "navigation displays actual generation names");
  assert(navigation.children[0].children[2].textContent === 1, "navigation shows actual generation population");
  state.focusedGenerationId = "parent";
  navigation.children[0].focus();
  renderWorkspaceChrome();
  assert(document.activeElement === navigation.children[0], "navigation keyboard focus survives workspace rerender");
  assert(navigation.children[0].getAttribute("aria-current") === "true", "focused generation is announced as current");
  assert($("#workspace-overview").getAttribute("aria-current") === "false", "overview is not simultaneously selected");
  state.workspace.generations = state.workspace.generations.filter((row) => row.id !== "parent");
  renderWorkspaceChrome();
  assert(state.focusedGenerationId === null && navigation.children.length === 1, "removed generations cannot leave stale navigation state");
  state.workspace.generations.push({ id: "parent", name: "父辈", position: 0 });

  toggleWorkspaceSidebar();
  assert(document.body.classList.contains("sidebar-collapsed"), "desktop toggle collapses the sidebar");
  assert($("#workspace-sidebar-toggle").getAttribute("aria-expanded") === "false", "desktop collapsed state matches aria-expanded");
  toggleWorkspaceSidebar();
  assert(!document.body.classList.contains("sidebar-collapsed"), "desktop toggle restores the sidebar");
  compact = true;
  syncWorkspaceSidebar();
  assert($("#workspace-sidebar-toggle").getAttribute("aria-expanded") === "false", "compact navigation is closed by default");
  toggleWorkspaceSidebar();
  assert(document.body.classList.contains("sidebar-open"), "compact toggle opens the navigation drawer");
  assert($("#workspace-sidebar-toggle").getAttribute("aria-expanded") === "true", "compact drawer expanded state is announced");
  const focusedNavigation = element("button");
  $("#workspace-sidebar").append(focusedNavigation);
  focusedNavigation.focus();
  assert(closeWorkspaceSidebar(), "open compact sidebar can be dismissed");
  assert(document.activeElement === $("#workspace-sidebar-toggle"), "closing the sidebar moves hidden navigation focus to the toggle");
  assert(!closeWorkspaceSidebar(), "closing an already closed sidebar does not resize again");
  compact = false;
  document.body.classList.add("sidebar-open");
  syncWorkspaceSidebar();
  assert(!document.body.classList.contains("sidebar-open"), "returning to desktop clears obsolete drawer state");

  $("#help-popover").hidden = true;
  const previousFocus = document.activeElement;
  toggleWorkspaceHelp({ stopPropagation() {} });
  assert(!$("#help-popover").hidden && $("#help-toggle").getAttribute("aria-expanded") === "true", "help opens with matching aria-expanded");
  assert(document.activeElement === previousFocus, "opening static help does not steal focus");
  assert(closeWorkspaceHelp(true) && $("#help-popover").hidden, "help closes deterministically");
  assert(document.activeElement === $("#help-toggle"), "help Escape dismissal can restore toggle focus");

  $("#canvas-stage").rect = { left: 100, top: -300, width: 1100, height: 500 };
  $('.generation-lane[data-generation-id="parent"]').rect = { left: 114, top: 0, width: 900, height: 110 };
  $("#generation-board").clientWidth = 1000;
  $("#generation-board").clientHeight = 700;
  const snapshot = JSON.stringify(state.workspace);
  assert(focusGenerationInCanvas("parent"), "generation focus finds its target lane");
  assert(targetCamera.scale >= 0.75, "generation focus preserves readable node scale");
  assert(Math.abs(targetCamera.x + getCameraViewport().baseX + 28 * targetCamera.scale - 40) < 0.001, "wide generation focus keeps its heading at the left safe margin");
  assert(state.focusedGenerationId === "parent", "generation focus updates navigation selection");
  assert(JSON.stringify(state.workspace) === snapshot, "generation navigation never modifies data");
  $("#person-dialog").open = true;
  $("#person-dialog").rect = { left: 620, top: 50, width: 350, height: 600 };
  focusGenerationInCanvas("parent");
  assert(targetCamera.scale >= 0.75 && targetCamera.x + getCameraViewport().baseX + 28 * targetCamera.scale >= 40, "open inspector does not force an unreadable generation scale");
  $("#person-dialog").open = false;

  const person = state.workspace.people.a;
  state.selectionA = "a";
  state.editingPersonId = "a";
  $("#person-dialog").open = true;
  const card = createPersonNode(person);
  assert(card.getAttribute("aria-label") === "张甲，男，A 选者", "person accessibility name and A selection remain intact");
  assert(card.children[1].children[1].textContent === "男", "gender remains a separate readable short label");
  assert(card.children[1].children[2].textContent === "1 条关系", "person relationship metadata derives from actual edges");
  assert(card.children[2].classList.contains("node-open-icon"), "person card has a separate visual open affordance");
  assert(card.classList.contains("is-inspected"), "open inspector survives node rebuilding");
  assert(!!card.listeners.pointerdown && !!card.listeners.keydown, "card drag and keyboard activation are retained");
  $("#person-dialog").open = false;

  draft = true;
  renderWorkspaceSaveState();
  assert($("#workspace-save-state").dataset.state === "draft", "unsaved inspector changes are not called saved");
  draft = false;
  let complete;
  fetch = () => new Promise((resolve) => { complete = resolve; });
  const pending = api("/api/people/a", { method: "PATCH" });
  assert($("#workspace-save-state").textContent === "保存中…", "active mutation announces saving");
  complete({ ok: true, json: async () => ({}) });
  await pending;
  assert($("#workspace-save-state").textContent === "画布已保存", "successful mutation announces saved");
  fetch = async () => { throw new Error("offline"); };
  try { await api("/api/people/a", { method: "PATCH" }); } catch {}
  assert($("#workspace-save-state").textContent === "连接失败" && state.mutations === 0, "network failure is visible and releases the mutation lock");
  fetch = async () => ({ ok: true, json: async () => ({}) });
  await api("/api/path?from=a&to=b");
  assert($("#workspace-save-state").textContent === "保存失败", "successful unrelated read does not hide an unsuccessful save");
  await api("/api/people/a", { method: "PATCH" });
  assert($("#workspace-save-state").textContent === "画布已保存", "successful retry clears the save failure");
  state.workspaceLoaded = false;
  fetch = async () => ({ ok: false, json: async () => ({ error: "storage failed" }) });
  try { await api("/api/workspace"); } catch {}
  assert($("#workspace-save-state").textContent === "载入失败", "failed initial load cannot remain in a false saved or loading state");

  assert(source.includes('$("#generation-navigation").addEventListener("click"'), "navigation uses one delegated listener rather than per-render bindings");
  assert(source.includes('if (closeWorkspaceHelp(true) || closeWorkspaceSidebar(true))'), "Escape closes workspace overlays before editor/mode teardown");
  assert(source.includes('new ResizeObserver(handleCameraResize)') && source.includes('viewportObserver.observe(board)'), "canvas size is observed through sidebar layout animation");
  print("PASS " + checks + " workspace UI assertions (remote JSC, memory-only)");
}
let completed = false, failure = null;
run().then(() => { completed = true; }, (error) => { failure = error; });
drainMicrotasks();
if (failure) throw failure;
if (!completed) throw new Error("Workspace UI assertions did not finish");
