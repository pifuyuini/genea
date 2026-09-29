// JSC integration tests of the actual static adapter, app API and bound read-only entry points.
// Browser-only rendering is replaced by the existing memory DOM boundary, never by API substitutes.
var fixture = readFile("tests/test_navigation_ui.js");
var boundaryEnd = fixture.indexOf("function runNavigationTests()");
if (boundaryEnd < 0) throw new Error("Navigation test DOM boundary moved");
eval(fixture.slice(0, boundaryEnd));
const originalElement = element;
element = function(...args) {
  const node = originalElement(...args);
  node.prepend = (...items) => { items.forEach(item => item.parentElement = node); node.children.unshift(...items); };
  return node;
};
document.createElement = element;
document.createTextNode = text => { const node = element("#text"); node.textContent = text; return node; };
const radioControls = [element("input"), element("input")];
const originalQueryAll = queryAll;
queryAll = function(selector, root) {
  if (selector === "#person-gender input, #relationship-kind input, #person-generation") return [...radioControls, query("#person-generation")];
  if (selector === "#person-name, #person-introduction, #parent-label, #child-label") return selector.split(", ").map(part => query(part));
  return originalQueryAll(selector, root);
};
document.querySelectorAll = queryAll;


function setTimeout() { return 0; }
function clearTimeout() {}

var demoWorkspace = JSON.parse(readFile("docs/workspace.json"));
var demoPaths = JSON.parse(readFile("docs/paths.json"));
var assetRequests = [], serverRequests = [], objectUrls = 0;
window.location = { href: "https://example.github.io/genea/index.html" };
var location = window.location;
document.currentScript = { src: "https://example.github.io/genea/readonly-api.js" };

// JavaScriptCore has no browser URL globals. These fixtures cover the URL forms the adapter uses.
class URLSearchParams {
  constructor(search = "") { this.entries = search.replace(/^\?/, "").split("&").filter(Boolean).map(part => {
    const split = part.indexOf("=");
    return [decodeURIComponent(split < 0 ? part : part.slice(0, split)),
      decodeURIComponent(split < 0 ? "" : part.slice(split + 1))];
  }); }
  get(name) { return this.entries.find(([key]) => key === name)?.[1] ?? null; }
}
class URL {
  constructor(value, base = location.href) {
    value = String(value); base = String(base);
    const origin = base.match(/^https?:\/\/[^/]+/)?.[0] || "https://example.github.io";
    const absolute = /^https?:\/\//.test(value) ? value : origin +
      (value.startsWith("/") ? value : base.slice(origin.length).split(/[?#]/)[0].replace(/[^/]*$/, "") + value);
    const match = absolute.match(/^(https?:\/\/[^/]+)([^?#]*)(\?[^#]*)?(#.*)?$/);
    const segments = [];
    for (const part of match[2].split("/")) {
      if (part === "..") segments.pop(); else if (part && part !== ".") segments.push(part);
    }
    this.origin = match[1]; this.pathname = "/" + segments.join("/") + (match[2].endsWith("/") || match[2].endsWith("/.") || match[2].endsWith("/..") ? "/" : "");
    this.search = match[3] || ""; this.hash = match[4] || "";
    this.href = this.origin + this.pathname + this.search + this.hash;
    this.searchParams = new URLSearchParams(this.search);
  }
  toString() { return this.href; }
  static createObjectURL() { objectUrls += 1; return "blob:demo"; }
  static revokeObjectURL() {}
}
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function response(value) { return { ok: true, json: async () => copy(value) }; }
fetch = async (url, options = {}) => {
  const path = String(url);
  assetRequests.push([path, options.method || "GET"]);
  if (path.endsWith("workspace.json")) return response(demoWorkspace);
  if (path.endsWith("paths.json")) return response(demoPaths);
  throw new Error("Unexpected static request: " + path);
};
eval(readFile("demo/readonly-api.js"));

async function runReadonlyTests() {
  const before = JSON.stringify(demoWorkspace);
  assert(window.GeneaDemo?.readonly === true, "static adapter explicitly selects read-only mode");
  const adapter = window.GeneaDemo;
  const workspace = await adapter.request("/api/workspace");
  assert(Object.keys(workspace.people).length === 38 && workspace.relationships.length === 42, "actual adapter loads the complete literary demo");
  const history = await adapter.request("/api/history");
  assert(!history.undo_label && !history.redo_label, "public demo has no editable history");
  for (const [from, to] of [
    ["person_baoyu", "person_baochai"], ["person_baochai", "person_baoyu"],
    ["person_yingchun", "person_xingfuren"], ["person_xingfuren", "person_yingchun"],
    ["person_keqing", "person_qinye"], ["person_baoyu", "person_qinye"],
    ["person_baoyu", "person_baoyu"],
  ]) {
    const result = await adapter.request("/api/path?from=" + from + "&to=" + to);
    assert(JSON.stringify(result) === JSON.stringify(demoPaths[from][to]), "adapter returns the generated directional path: " + from + " to " + to);
  }
  const mutations = [
    ["POST", "/api/generations"], ["PATCH", "/api/generations/generation_01"],
    ["DELETE", "/api/generations/generation_01"],
    ["PATCH", "/api/generations/generation_01/people-order"],
    ["POST", "/api/people"], ["PATCH", "/api/people/person_baoyu"], ["DELETE", "/api/people/person_baoyu"],
    ["POST", "/api/relationships"], ["PATCH", "/api/relationships/rel_demo"], ["DELETE", "/api/relationships/rel_demo"],
    ["POST", "/api/photos"], ["POST", "/api/history/undo"], ["POST", "/api/history/redo"],
  ];
  const requestCount = assetRequests.length;
  for (const [method, path] of mutations) {
    let denied = false;
    try { await adapter.request(path, { method, body: "{}" }); } catch { denied = true; }
    assert(denied, "adapter rejects " + method + " " + path);
  }
  assert(assetRequests.length === requestCount, "read-only mutations never reach fetch");
  assert(assetRequests.every(([path, method]) => {
    const asset = new URL(path, location.href);
    return method === "GET" && asset.origin === "https://example.github.io" &&
      ["/genea/workspace.json", "/genea/paths.json"].includes(asset.pathname);
  }), "static reads remain under the repository subpath and never call root APIs");
  assert(JSON.stringify(demoWorkspace) === before, "adapter does not modify demo fixture");

  state.workspace = workspace;
  state.workspaceLoaded = true;
  state.history = history;
  requestDraw = () => {};
  renderHistory = () => {};
  renderWorkspaceSaveState = () => {};
  render = () => {};
  showToast = () => {};
  const appBefore = JSON.stringify(state.workspace);
  for (const [method, path] of mutations) {
    let denied = false;
    try { await api(path, { method, body: "{}" }); } catch { denied = true; }
    assert(denied, "actual application API refuses read-only " + method + " " + path);
  }
  assert(JSON.stringify(state.workspace) === appBefore, "denied app mutations preserve workspace");
  const readWorkspace = await api("/api/workspace");
  assert(Object.keys(readWorkspace.people).length === 38, "actual application API reads through static adapter");

  // Removing the adapter leaves the original server API behavior intact.
  delete window.GeneaDemo;
  fetch = async (path, options = {}) => {
    serverRequests.push([path, options.method || "GET", options.body]);
    return response({ workspace: { generations: [], people: {}, relationships: [] }, history: { undo_label: "编辑人物", redo_label: null } });
  };
  await api("/api/people/person_baoyu", { method: "PATCH", body: '{"name":"临时测试"}' });
  await api("/api/workspace");
  assert(serverRequests.length === 2 && serverRequests[0][1] === "PATCH" && serverRequests[1][1] === "GET",
    "ordinary Python application still sends mutations and reads to the server");
  assert(serverRequests[0][0] === "/api/people/person_baoyu", "ordinary mode retains API route");
  window.GeneaDemo = adapter;

  // Real action functions must stop before their editable DOM or storage paths.
  const blockedActions = [
    ["generation dialog", () => openGenerationDialog("first")],
    ["save generation", () => saveGeneration(event($("#generation-form")))],
    ["delete generation", () => deleteGeneration("generation_01")],
    ["save person", () => savePerson(event($("#person-form")))],
    ["delete person", () => deletePerson()],
    ["create relationship", () => createDraggedRelationship("person_baoyu", "person_zheng")],
    ["save relationship", () => saveRelationship(event($("#relationship-form")))],
    ["delete relationship", () => deleteRelationship()],
    ["add relative", () => addRelativeFromInspector()],
    ["reorder person", () => reorderPersonInGeneration("person_baoyu", "generation_05", 0)],
    ["move person", () => movePersonToGeneration("person_baoyu", "generation_04")],
    ["undo", () => travelHistory("undo")],
    ["redo", () => travelHistory("redo")],
    ["link mode", () => toggleLinkMode()],
  ];
  const ordinaryCalls = serverRequests.length;
  state.editingPersonId = "person_baoyu";
  for (const [name, action] of blockedActions) {
    await action();
    assert(JSON.stringify(state.workspace) === appBefore, "blocked " + name + " preserves demo");
  }
  assert(serverRequests.length === ordinaryCalls && !state.linkMode, "blocked UI actions neither fetch nor enter editing mode");

  await runReadonlyBindings();
  assert(JSON.stringify(state.workspace) === appBefore, "bound controls preserve workspace");
  assert(serverRequests.length === ordinaryCalls && objectUrls === 0, "read-only controls create no upload preview or server calls");
  print("PASS " + checks + " read-only demo assertions (actual adapter/app, memory browser boundaries)");
}

async function runReadonlyBindings() {
  bindEvents();
  configureReadonlyDemo();
  requestNavigatorUpdate = () => {};
  renderBoard();
  renderModeControls();
  assert(Object.keys(state.workspace.people).length === 38, "mode visibility regression uses the real nonempty demo");
  assert($("#link-mode").hidden && !$("#perspective-mode").hidden && !$("#select-mode").hidden,
    "real board render hides editing links but keeps browse and relationship entries visible");
  assert(!$(".mode-switcher").hidden && !$("#perspective-mode").disabled && !$("#select-mode").disabled,
    "public browsing modes remain enabled in the mode toolbar");
  const disabledControls = ["#link-mode", "#generation-menu-toggle", "#add-first-generation",
    "#add-generation-above", "#add-generation-below", "#history-undo", "#history-redo",
    "#person-photo", "#person-photo-remove", "#person-save", "#person-delete",
    "#person-relative-add", "#person-relative-confirm", "#relationship-save", "#relationship-delete", "#generation-submit"];
  for (const selector of disabledControls) assert($(selector).disabled, "read-only control is disabled: " + selector);
  for (const control of $$("#person-gender input, #relationship-kind input, #person-generation")) {
    assert(control.disabled, "native gender, generation and relationship choices cannot edit");
  }
  for (const selector of ["#person-name", "#person-introduction", "#parent-label", "#child-label"]) {
    assert($(selector).readOnly, "profile text remains selectable but not editable: " + selector);
  }
  assert($(".photo-picker").tabIndex === -1, "read-only photo is not presented as an upload control");
  assert($(".header-actions").children.some(node => node.href === window.GeneaDemo.downloadUrl), "read-only view offers full-version download");

  const form = $("#person-form"), photo = $("#person-photo"), picker = $(".photo-picker");
  let submissions = 0, fileDialogs = 0;
  form.requestSubmit = () => { submissions += 1; };
  photo.click = () => { fileDialogs += 1; };
  photo.files = [{ name: "fictional-test.jpg", type: "image/jpeg", size: 20 }];
  const draftBefore = JSON.stringify(personEditor), filesBefore = photo.files;
  emit(photo, "change", event(photo));
  emit($("#person-photo-remove"), "click", event($("#person-photo-remove")));
  emit(picker, "keydown", event(picker, { key: "Enter" }));
  emit(picker, "keydown", event(picker, { key: " " }));
  const drop = event(form, { dataTransfer: { types: ["Files"], files: photo.files } });
  emit(form, "dragover", drop); emit(form, "drop", drop);
  emit(form, "keydown", event(form, { key: "Enter", metaKey: true }));
  emit(form, "keydown", event(form, { key: "Enter", ctrlKey: true }));
  assert(drop.defaultPrevented && !picker.classList.contains("is-drop-target"), "read-only file drop is consumed without upload affordance");
  assert(photo.files === filesBefore && JSON.stringify(personEditor) === draftBefore,
    "photo changes/removal/drop do not alter the inspector draft");
  assert(submissions === 0 && fileDialogs === 0, "photo keyboard controls and save shortcuts cannot start editing");

  for (const selector of ["#history-undo", "#history-redo", "#add-first-generation",
    "#person-delete", "#relationship-delete", "#person-relative-confirm", "#link-mode"]) {
    emit($(selector), "click", event($(selector)));
  }
  for (const selector of ["#generation-form", "#person-form", "#relationship-form"]) {
    const submit = event($(selector));
    emit($(selector), "submit", submit);
    assert(submit.defaultPrevented, "read-only submit is canceled: " + selector);
  }

  const idle = element("div");
  $("#link-mode").hidden = true;
  emit(document, "keydown", event(idle, { key: "l" }));
  assert(!state.linkMode, "L cannot enter link creation mode");
  emit(document, "keydown", event(idle, { key: "r" }));
  assert(state.perspective, "R still opens read-only A/B mode when the link button is hidden");
  emit(document, "keydown", event(idle, { key: "r" }));
  assert(!state.perspective, "R exits A/B mode normally");
  emit(document, "keydown", event(idle, { key: "z", metaKey: true }));
  emit(document, "keydown", event(idle, { key: "z", metaKey: true, shiftKey: true }));
  assert(!state.historyBusy, "undo shortcuts cannot start data history navigation");

  const card = element("article");
  card.dataset.personId = "person_baoyu";
  card.classList.add("person-node");
  card.rect = rect(10, 20, 200, 100);
  beginPersonPointer(event(card, { pointerId: 77, shiftKey: true }));
  assert(state.drag?.selectOnly && !state.drag.relationship, "read-only card gestures cannot reorder, move or Shift-link");
  movePersonPointer(event(card, { pointerId: 77, clientX: 360, clientY: 240 }));
  await endPersonPointer(event(card, { pointerId: 77, clientX: 360, clientY: 240 }));
  assert(!state.drag && !card.hasPointerCapture(77), "read-only card drag finishes without pending edit");
}
const startup = source.lastIndexOf("\nsetTheme(state.theme);");
if (startup < 0) throw new Error("Application startup boundary moved");
let finished = false, failure = null;
eval(readFile("static/motion.js") + "\n" + source.slice(0, startup) +
  "\n" + runReadonlyBindings.toString() + "\n(" + runReadonlyTests.toString() + ")().then(() => { finished = true; }, error => { failure = error; });");
drainMicrotasks();
if (failure) throw failure;
if (!finished) throw new Error("Read-only tests did not finish");
