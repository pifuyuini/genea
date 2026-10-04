// Real frontend functions and event bindings, with memory-only DOM/network boundaries.
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_experimental_tools_ui.js
var toolHarness = readFile("tests/test_cross_generation_ui.js");
eval(toolHarness.slice(0, toolHarness.indexOf("async function runCrossGenerationTests()")));
const toolElement = element;
element = function (tag, id) {
  const node = toolElement(tag, id);
  node.show = function () { this.open = true; };
  node.showModal = function () { this.open = true; modal = this; };
  node.close = function () { this.open = false; if (modal === this) modal = null; };
  node.reset = function () {};
  node.select = function () {};
  node.files = [];
  return node;
};
document.createElement = element;
document.createTextNode = (text) => { const node = element("text"); node.textContent = text; return node; };
document.getElementById = (id) => query("#" + id);
function flatten(node) { return [node, ...node.children.flatMap(flatten)]; }
const toolQueryAll = queryAll;
queryAll = function (selector, root) {
  if (selector === '#person-gender input, #relationship-kind input') return [...genderInputs, ...relationshipInputs];
  if (selector.includes(".lane-name") || selector === ".relative-edit") {
    return [...nodes.values()].flatMap(flatten).filter((node) => node.matches(selector));
  }
  return toolQueryAll(selector, root);
};
document.querySelectorAll = queryAll;
async function clickTool(node) {
  for (const entry of node.listeners.click || []) await entry.callback(event(node));
  drainMicrotasks();
}
function deferredTool() { let resolve; const promise = new Promise((done) => { resolve = done; }); return { promise, resolve }; }
function toolResponse(value, status = 200) { return { ok: status < 400, status, json: async () => value }; }
async function runExperimentalToolTests() {
  const config = (enabled, readOnly = false) => ({ experimental_features_enabled: enabled, experimental_cross_generation: enabled,
    read_only: readOnly, read_only_reason: readOnly ? "历史含跨代关系，请重新启用实验后编辑。" : null });
  const fixture = {
    generations: [{ id: "g1", name: "祖辈", position: 0 }, { id: "g2", name: "父辈", position: 1 }, { id: "g3", name: "子辈", position: 2 }],
    people: {
      a: { id: "a", name: "同名", generation_id: "g1", gender: "female", introduction: "祖母", order: 0 },
      b: { id: "b", name: "同名", generation_id: "g2", gender: "male", introduction: "父亲", order: 0 },
      c: { id: "c", name: "孩子", generation_id: "g3", gender: "female", introduction: "女儿", order: 0 },
    }, relationships: [{ id: "r", parent_id: "a", child_id: "c", kind: "standard", parent_label: "妈妈", child_label: "女儿" }],
  };
  const history = { undo_label: "编辑人物", redo_label: "移动人物" };
  const path = { path_text: "女儿", person_ids: ["a", "c"], relationship_ids: ["r"],
    direct_relationship: { status: "resolved", results: [{ label: "推导称谓", explanation: "推导依据" }], note: "" } };
  const pair = { status: "success", intent: "pair", source_id: "a", target_id: "c", results: [{ person_id: "c", name: "孩子", path_result: path }] };
  const report = { report_id: "report-1", status: "issues", summary: { errors: 1, notices: 1, repairable: 1 }, issues: [
    { id: "derived", code: "standard_fields", severity: "error", message: "标准称谓需要同步", person_ids: ["a"], relationship_ids: ["r"],
      repair: { action: "normalize", label: "同步标准称谓", description: "只同步该关系的标准称谓，不改变亲子方向。" } },
    { id: "missing", code: "missing_photo", severity: "notice", message: "孩子尚未添加照片", person_ids: ["c"], relationship_ids: [], repair: null },
  ] };
  const clean = { report_id: "report-2", status: "ok", summary: { errors: 0, notices: 0, repairable: 0 }, issues: [] };
  let requests = [], storedConfig = config(false), queryResponse = pair, checkResponse = report, clipboard = [], toasts = [];
  let confirmResult = true, confirmMessages = [];
  state.workspace = clone(fixture); state.history = clone(history); state.workspaceLoaded = true; state.camera.hasFit = true;
  state.selectionA = null; state.selectionB = null;
  render = () => { renderSelection(); renderModeControls(); renderExperimentalControls(); renderHistory(); };
  renderWorkspaceChrome = () => {};
  handleCameraResize = () => {};
  animatePersonInspector = () => {};
  requestDraw = () => {};
  showToast = (text, tone, action) => toasts.push({ text, tone, action });
  askConfirmation = async (text) => { confirmMessages.push(text); return confirmResult; };
  writeClipboardText = async (text) => { clipboard.push(text); };
  const defaultFetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === "/api/config") {
      if (options.method === "POST") storedConfig = config(JSON.parse(options.body).experimental_features_enabled);
      return toolResponse(clone(storedConfig));
    }
    if (url === "/api/workspace") return toolResponse(clone(fixture));
    if (url === "/api/history") return toolResponse(history);
    if (url === "/api/query") return toolResponse(queryResponse);
    if (url === "/api/check") return toolResponse(checkResponse);
    if (url === "/api/check/fix") { checkResponse = clean; return toolResponse({ workspace: clone(fixture), history: { undo_label: "修复家谱", redo_label: null }, config: storedConfig }); }
    if (url.startsWith("/api/path?")) return toolResponse(path);
    return toolResponse({ workspace: clone(fixture), history, config: storedConfig });
  };
  fetch = defaultFetch;
  bindEvents();
  await loadWorkspace(); renderExperimentalControls();
  assert(!experimentsEnabled() && canEditWorkspace(), "ordinary configuration loads with editing available");
  assert($("#advanced-query").hidden && $("#check-genealogy").hidden, "ordinary mode hides experimental entry points");
  const before = JSON.stringify(state.workspace), beforeHistory = JSON.stringify(state.history);
  await toggleExperimentalFeatures();
  assert(experimentsEnabled() && $("#experiments-toggle").getAttribute("aria-pressed") === "true", "toggle applies server-confirmed unified feature state");
  assert(requests.find((entry) => entry.url === "/api/config" && entry.options.method === "POST").options.body === '{"experimental_features_enabled":true}', "configuration POST uses the unified field");
  assert(JSON.stringify(state.workspace) === before && JSON.stringify(state.history) === beforeHistory && state.mutations === 0, "toggle changes neither workspace nor undo state");
  const realClosePerson = closePersonDialog;
  $("#person-dialog").open = true; closePersonDialog = async () => false;
  const beforeCancel = requests.length; await toggleExperimentalFeatures();
  assert(experimentsEnabled() && requests.length === beforeCancel, "cancelled draft guard prevents configuration mutation");
  $("#person-dialog").open = false; closePersonDialog = realClosePerson;
  $("#relationship-dialog").showModal(); await toggleExperimentalFeatures();
  assert(experimentsEnabled() && requests.length === beforeCancel, "relationship modal preserves its unsaved draft and prevents toggle");
  $("#relationship-dialog").close();
  fetch = async () => { throw new Error("offline"); };
  await toggleExperimentalFeatures();
  assert(experimentsEnabled() && Boolean(state.configError) && !canEditWorkspace(), "ambiguous configuration failure retains confirmed state and requires explicit retry");
  assert(!$("#config-error").hidden && !$("#config-retry").disabled, "configuration failure exposes retry");
  storedConfig = config(false, true); fetch = defaultFetch;
  await retryRuntimeConfig();
  assert(!experimentsEnabled() && state.config.read_only && !state.configError, "retry synchronizes the stored setting and read-only reason");
  assert(!$("#workspace-read-only").hidden && allText($("#workspace-read-only-reason")).includes("历史"), "read-only banner explains history compatibility");
  assert(!$("#experiments-toggle").disabled, "read-only workspace can re-enable experimental features");
  renderBoard(); renderWriteAccess(); renderHistory();
  for (const id of ["person-save", "person-delete", "person-name", "person-generation", "person-photo", "person-photo-remove", "relationship-save", "relationship-delete", "generation-submit", "link-mode", "history-undo", "history-redo"]) {
    assert($("#" + id).disabled, "read-only disables " + id);
  }
  assert([...genderInputs, ...relationshipInputs].every((input) => input.disabled), "read-only disables person and relationship radio inputs");
  assert(flatten($("#generation-lanes")).filter((node) => node.matches(".lane-name,.lane-add,.lane-remove,.lane-empty")).every((node) => node.disabled), "canvas mutation controls remain disabled after direct board redraw");
  assert(crossGenerationRelationships().length === 1 && state.workspace.relationships.length === 1, "read-only preserves existing cross-generation geometry inputs");
  assert(!canLinkPeople("a", "b"), "read-only disallows adjacent links as well");
  const protectedRequests = requests.length;
  for (const [url, method] of [["/api/people", "POST"], ["/api/people/a", "PATCH"], ["/api/people/a", "DELETE"], ["/api/photos", "POST"], ["/api/generations", "POST"], ["/api/relationships", "POST"], ["/api/history/undo", "POST"], ["/api/history/redo", "POST"], ["/api/check/fix", "POST"]]) {
    let blocked = false; try { await api(url, { method, body: "{}" }); } catch { blocked = true; }
    assert(blocked, "read-only blocks programmatic " + method + " " + url);
  }
  await travelHistory("undo"); await toggleLinkMode(); acceptDroppedPhoto({ dataTransfer: { files: [] } });
  assert(requests.length === protectedRequests, "read-only guards dispatch no mutations or history writes");
  await openPersonDialog("g1", "a");
  assert($("#person-dialog").open && $("#person-name").value === "同名" && $("#person-name").disabled, "read-only inspector shows existing person fields without enabling edits");
  assert($(".photo-picker").getAttribute("aria-disabled") === "true", "read-only photo picker is semantically disabled");
  assert($(".photo-actions").hidden && $(".photo-hint").hidden && !$("#person-photo-readonly").hidden,
    "read-only photo UI hides upload and drop invitations and shows a viewing note");
  assert($(".photo-picker").tabIndex === -1 && $(".photo-picker").getAttribute("aria-label").includes("仅可查看"),
    "read-only photo does not invite keyboard activation");
  $("#person-dialog").open = false;
  state.perspective = true; state.selectionA = "a"; state.selectionB = "c";
  state.relationshipPath = { ...path, labels: ["女儿"] }; state.relationshipCopyText = relationshipCopySummary(path, path.path_text, "a", "c");
  renderSelection();
  assert(!allText($("#selection-result")).includes("推导称谓") && allText($("#selection-result")).includes("女儿"), "off mode shows only original registered chain even if a result contains derived data");
  await copyRelationship();
  assert(clipboard.at(-1) === "孩子 是 同名 的：女儿", "off-mode copy remains the original chain");
  state.perspective = false; storedConfig = config(true); applyRuntimeConfig(storedConfig); render();
  const queryWorkspace = JSON.stringify(state.workspace), queryHistory = JSON.stringify(state.history);
  advancedQueryState().open = true; $("#advanced-query-input").value = "同名的子女有哪些";
  await runAdvancedQuery();
  assert(advancedQueryState().result === pair && state.mutations === 0, "advanced POST query is treated as a read");
  assert(JSON.stringify(state.workspace) === queryWorkspace && JSON.stringify(state.history) === queryHistory, "query preserves workspace and history");
  assert(allText($("#advanced-query-results")).includes("孩子"), "query renders named results");
  await selectAdvancedQueryResult(pair, pair.results[0]);
  assert(state.selectionA === "a" && state.selectionB === "c" && state.perspective && !advancedQueryState().open, "query result enters A/B in backend-defined direction");
  assert(state.relationshipPath.direct_relationship.results[0].label === "推导称谓", "pair result preserves supplied inference evidence");
  await copyRelationship(); assert(clipboard.at(-1) === "孩子 是 同名 的：女儿", "advanced result copy excludes derived text");
  queryResponse = { ...pair, intent: "relatives", relationship_type: "adoptive_mother", results: [{
    person_id: "c", name: "阿玛兰妲", matched_labels: ["养母"],
    path_result: { ...path, path_text: "养母", direct_relationship: { status: "resolved", results: [{ label: "姑母", explanation: "血亲依据" }], note: "" } },
  }] };
  await runAdvancedQuery();
  assert(allText($("#advanced-query-results").children[0].children[1]) === "养母 · 姑母",
    "relative finder explains the registered adoptive match before the independent blood-kinship title");
  await selectAdvancedQueryResult(queryResponse, queryResponse.results[0]);
  await copyRelationship();
  assert(clipboard.at(-1) === "孩子 是 同名 的：养母",
    "finder matching labels do not alter the selected pair's original-chain copy");
  queryResponse = { status: "needs_disambiguation", intent: "relatives", ambiguities: [{ slot: 0, mention: "同名", candidates: [
    { id: "a", name: "同名", generation: "祖辈", gender: "female", introduction: "祖母" },
    { id: "b", name: "同名", generation: "父辈", gender: "male", introduction: "父亲" },
  ] }], results: [] };
  advancedQueryState().open = true; await runAdvancedQuery();
  const candidates = $("#advanced-query-results").children[0].children.slice(1);
  assert(candidates.length === 2 && allText(candidates[0]).includes("祖辈 · 女 · 祖母"), "disambiguation shows generation, gender and introduction");
  queryResponse = pair; await clickTool(candidates[0]);
  const resolvedRequest = requests.filter((entry) => entry.url === "/api/query").at(-1);
  assert(JSON.parse(resolvedRequest.options.body).resolutions["0"] === "a", "disambiguation resubmits explicit stable ID in its text slot");
  assert(advancedQueryState().result === pair, "resolved query replaces ambiguity choices");
  for (const status of ["not_found", "unsupported"]) {
    queryResponse = { status, message: status + "说明", results: [], ambiguities: [] }; await runAdvancedQuery();
    assert(allText($("#advanced-query-status")).includes(status + "说明"), "renders " + status + " without assuming intent exists");
  }
  // Late responses cannot restore experimental UI after a mode, workspace or selection change.
  let pending = deferredTool(); fetch = () => pending.promise;
  const staleQuery = runAdvancedQuery(); applyRuntimeConfig(config(false)); render(); pending.resolve(toolResponse(pair)); await staleQuery;
  assert(advancedQueryState().result === null && $("#advanced-query").hidden, "disabling experiments discards an in-flight advanced result");
  applyRuntimeConfig(config(true)); pending = deferredTool(); fetch = () => pending.promise;
  const changedWorkspace = runAdvancedQuery(); replaceWorkspace(clone(fixture), false); pending.resolve(toolResponse(pair)); await changedWorkspace;
  assert(advancedQueryState().result === null && !advancedQueryState().loading, "workspace replacement invalidates pending advanced query");
  pending = deferredTool(); fetch = () => pending.promise;
  const changedSelection = runAdvancedQuery(); clearPerspectiveSelection("b"); pending.resolve(toolResponse(pair)); await changedSelection;
  assert(advancedQueryState().result === null, "A/B selection changes discard pending advanced query");
  const first = deferredTool(), second = deferredTool(); let requestIndex = 0;
  fetch = () => (++requestIndex === 1 ? first.promise : second.promise);
  const oldRun = runAdvancedQuery(), newRun = runAdvancedQuery(); second.resolve(toolResponse(pair)); await newRun;
  first.resolve(toolResponse({ status: "not_found", results: [] })); await oldRun;
  assert(advancedQueryState().result === pair, "latest query request wins out-of-order responses");
  fetch = defaultFetch; storedConfig = config(true); queryResponse = pair; state.perspective = false;
  const checkHistory = JSON.stringify(state.history), checkWorkspace = JSON.stringify(state.workspace);
  await openGenealogyCheck();
  assert($("#check-dialog").open && checkReportState().report === report, "check opens a report dialog");
  assert(state.mutations === 0 && JSON.stringify(state.workspace) === checkWorkspace && JSON.stringify(state.history) === checkHistory, "check GET never writes workspace or history");
  assert(allText($("#check-results")).includes("需要处理") && allText($("#check-results")).includes("资料提醒"), "check separates structural issues and information notices");
  const repairs = flatten($("#check-results")).filter((node) => node.classList.contains("check-fix"));
  assert(repairs.length === 1 && allText($("#check-results")).includes(report.issues[0].repair.description), "only backend-provided safe repair gets a button and description");
  confirmResult = false; const beforeRepair = requests.length; await repairCheckIssue(report, report.issues[0]);
  assert(requests.length === beforeRepair && checkReportState().report === report, "cancelled individual repair keeps its report and performs no write");
  confirmResult = true; await repairCheckIssue(report, report.issues[0]);
  assert(confirmMessages.at(-1).includes("不改变亲子方向") && confirmMessages.at(-1).includes("可以撤销"), "repair confirmation describes the actual change and undo");
  const fixRequest = requests.find((entry) => entry.url === "/api/check/fix");
  assert(JSON.parse(fixRequest.options.body).issue_id === "derived" && JSON.parse(fixRequest.options.body).report_id === "report-1", "repair submits one issue in its checked report");
  assert(state.history.undo_label === "修复家谱" && checkReportState().report === clean, "repair applies mutation response, retains undo label and refreshes report");
  const staleFixCount = requests.length; await repairCheckIssue(report, report.issues[0]);
  assert(requests.length === staleFixCount, "obsolete rendered repair cannot submit again");
  checkResponse = report; await runGenealogyCheck();
  fetch = async (url, options = {}) => url === "/api/check/fix" ? toolResponse({ error: "report stale" }, 409) : defaultFetch(url, options);
  await repairCheckIssue(report, report.issues[0]);
  assert(checkReportState().report === report && toasts.at(-1).text.includes("家谱已变化"), "409 refreshes workspace and report for a new voluntary repair");
  closeGenealogyCheck();
  pending = deferredTool(); fetch = () => pending.promise;
  const lateCheck = openGenealogyCheck(); applyRuntimeConfig(config(false)); render(); pending.resolve(toolResponse(report)); await lateCheck;
  assert(!$("#check-dialog").open && checkReportState().report === null, "disabled experiments close the check and reject late reports");
  fetch = defaultFetch; storedConfig = config(false); applyRuntimeConfig(storedConfig); state.perspective = false; render();
  await api("/api/people/b", { method: "PATCH", body: '{"name":"新名字"}' });
  assert(canEditWorkspace() && state.mutations === 0, "ordinary writable workspace retains original mutation behavior");
  renderWriteAccess();
  assert(!$(".photo-actions").hidden && !$(".photo-hint").hidden && $("#person-photo-readonly").hidden && $(".photo-picker").tabIndex === 0,
    "ordinary editing restores photo upload, drop guidance and keyboard access");
  const tray = $("#selection-tray"), board = $("#generation-board"), camera = $(".camera-controls");
  tray.hidden = false; camera.hidden = false;
  const geometries = [
    { name: "desktop long query", width: 1280, height: 720, top: 113, cameraTop: 658 },
    { name: "desktop read-only notice", width: 1280, height: 720, top: 178, cameraTop: 658 },
    { name: "compact read-only toolbar", width: 390, height: 740, top: 202, cameraTop: 676 },
  ];
  for (const geometry of geometries) {
    window.innerHeight = geometry.height;
    board.rect = rect(0, geometry.top, geometry.width, geometry.height - geometry.top);
    camera.rect = rect(20, geometry.cameraTop, 300, 50);
    syncSelectionTrayBounds();
    const panelBottom = geometry.height - parseFloat(tray.style.bottom);
    const panelTop = panelBottom - parseFloat(tray.style.maxHeight);
    assert(panelTop >= geometry.top + 12, geometry.name + " keeps panel header below actual canvas top");
    assert(panelBottom <= geometry.cameraTop - 12, geometry.name + " leaves a margin above camera controls");
    assert(parseFloat(tray.style.maxHeight) === geometry.cameraTop - geometry.top - 24,
      geometry.name + " uses available canvas height for scrolling without reducing text size");
  }
  board.rect = rect(0, 113, 1280, 607); camera.rect = rect(20, 658, 300, 50); window.innerHeight = 720;
  syncSelectionTrayBounds();
  assert(tray.style.maxHeight === "521px", "expanded desktop height recovers after compact read-only layout");
  // A damaged document must remain inspectable after configuration has loaded.
  state.workspaceLoaded = false; state.workspaceLoadFailed = false; state.configLoaded = false;
  state.workspace = { generations: [], people: {}, relationships: [] };
  storedConfig = config(false, true);
  const unreadable = { report_id: "damaged-file", status: "unreadable", summary: { errors: 1, notices: 0, repairable: 0 },
    issues: [{ id: "workspace_unreadable", code: "workspace_unreadable", severity: "error", message: "工作区不是有效的 UTF-8 JSON；不能自动修复。", person_ids: [], relationship_ids: [], repair: null }] };
  fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === "/api/config") {
      if (options.method === "POST") storedConfig = config(JSON.parse(options.body).experimental_features_enabled, true);
      return toolResponse(storedConfig);
    }
    if (url === "/api/workspace") return toolResponse({ error: "Workspace is unreadable. No changes were made." }, 503);
    if (url === "/api/check") return toolResponse(unreadable);
    throw new Error("Damaged workspace must not dispatch another content request");
  };
  let loadFailed = false;
  try { await loadWorkspace(); } catch { loadFailed = true; }
  render();
  assert(loadFailed && state.configLoaded && !state.workspaceLoaded && !$("#experiments-toggle").disabled,
    "successful config read keeps toggle available when workspace loading fails");
  state.perspective = false; state.selectionA = null; state.selectionB = null;
  await toggleExperimentalFeatures();
  assert(experimentsEnabled() && !$("#check-genealogy").hidden && !$("#check-genealogy").disabled,
    "enabling experiments exposes raw-file inspection without a loaded workspace");
  assert(!canEditWorkspace() && $("#person-save").disabled && $("#advanced-query").hidden && $("#advanced-query-input").disabled,
    "damaged workspace keeps content editing and advanced queries unavailable");
  state.configError = "earlier settings request failed";
  await retryRuntimeConfig();
  assert(state.configLoaded && !state.configError && !$("#experiments-toggle").disabled && !$("#check-genealogy").disabled,
    "successful setting retry is not mislabeled as a config failure when document reload still fails");
  const damagedWorkspace = JSON.stringify(state.workspace), damagedHistory = JSON.stringify(state.history), beforeInspection = requests.length;
  await openGenealogyCheck();
  assert(checkReportState().report === unreadable && $("#check-dialog").open && allText($("#check-status")).includes("无法完整读取"),
    "raw unreadable report remains visible after workspace GET failure");
  assert(requests.length === beforeInspection + 1 && requests.at(-1).url === "/api/check" && !requests.at(-1).options.method &&
    state.mutations === 0 && JSON.stringify(state.workspace) === damagedWorkspace && JSON.stringify(state.history) === damagedHistory,
    "damaged-file inspection is one GET with no initialization, mutation or undo changes");
  assert(!flatten($("#check-results")).some((node) => node.tagName === "BUTTON"),
    "unreadable report offers neither invented location targets nor automatic repairs");
  print("PASS " + checks + " experimental tool UI assertions (JSC, memory-only)");
}
var completed = false, failure = null;
const startup = source.lastIndexOf("\nsetTheme(state.theme);");
eval(source.slice(0, startup) + "\n(" + runExperimentalToolTests.toString() + ")().then(() => { completed = true; }, error => { failure = error; });");
drainMicrotasks();
if (failure) throw failure;
if (!completed) throw new Error("Experimental tool assertions did not finish");
