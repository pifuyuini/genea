// Run from the repository root with the macOS JavaScriptCore helper:
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_kinship_ui.js
// Executes actual app functions with in-memory DOM, API and clipboard boundaries.
var source = readFile("static/app.js"), checks = 0, htmlWrites = [];
function assert(value, name) { checks += 1; if (!value) throw new Error(name); }
function extract(startMarker, endMarker) {
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error("Function boundary changed: " + startMarker);
  return source.slice(start, end);
}
function element(tag = "div") {
  const classes = new Set(), attributes = {};
  return {
    tagName: tag.toUpperCase(), children: [], dataset: {}, style: {}, textContent: "", value: "", files: [], listeners: {}, open: false,
    classList: {
      add: (...items) => items.forEach((item) => classes.add(item)),
      remove: (...items) => items.forEach((item) => classes.delete(item)),
      contains: (item) => classes.has(item),
      toggle(item, force) { const next = force === undefined ? !classes.has(item) : force; next ? classes.add(item) : classes.delete(item); return next; },
    },
    set innerHTML(value) { htmlWrites.push(String(value)); },
    setAttribute(name, value) { attributes[name] = String(value); },
    getAttribute: (name) => attributes[name] ?? null,
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, callback) { this.listeners[name] = callback; },
    focus() { document.activeElement = this; },
    getBoundingClientRect() { return { top: 0, bottom: 0, height: 0, width: 0 }; },
    select() {}, setSelectionRange() {}, remove() {},
  };
}
function text(node) {
  if (typeof node === "string") return node;
  return node.children.length ? node.children.map(text).join("") : node.textContent;
}
function visibleText(node) {
  if (typeof node === "string") return node;
  if (node.tagName === "DETAILS" && !node.open) {
    return node.children.filter((child) => typeof child !== "string" && child.tagName === "SUMMARY").map(visibleText).join("");
  }
  return node.children.length ? node.children.map(visibleText).join("") : node.textContent;
}
function clickDisclosure(details, bubblingAction = () => {}) {
  const event = { defaultPrevented: false, preventDefault() { this.defaultPrevented = true; } };
  details.children[0].listeners.click?.(event);
  bubblingAction();
  // Native summary activation occurs after click listeners; it can target a now-detached details.
  if (!event.defaultPrevented) details.open = !details.open;
}
function descendants(node, className) {
  return node.children.filter((child) => typeof child !== "string").flatMap((child) =>
    [...(child.className === className ? [child] : []), ...descendants(child, className)]);
}
var document = { body: element("body"), activeElement: null, createElement: element, createTextNode: (value) => value, execCommand: () => false };
var HTMLElement = function() {};
var nodes = new Map();
function $(selector) {
  if (selector === "dialog:modal") return null;
  if (!nodes.has(selector)) nodes.set(selector, element());
  return nodes.get(selector);
}
function $$() { return []; }
var CSS = { escape: (value) => String(value) };
var clipboardWrites = [], clipboardMode = "success", resolveClipboard;
var navigator = { clipboard: { writeText(value) {
  clipboardWrites.push(value);
  if (clipboardMode === "failure") return Promise.reject(new Error("clipboard unavailable"));
  if (clipboardMode === "pending") return new Promise((resolve) => { resolveClipboard = resolve; });
  return Promise.resolve();
} } };
var state = {};
var personEditor = { saving: false, removePhoto: false }, relationshipSaving = false;
var apiCalls = [], pathRequests = [], mutationResult, workspaceResult, toasts = [], renderCount = 0;
function freshWorkspace() {
  return {
    generations: [{ id: "parents", name: "父辈", position: 0 }, { id: "children", name: "同辈", position: 1 }, { id: "later", name: "后辈", position: 2 }],
    people: {
      a: { id: "a", name: "甲", gender: "male", generation_id: "parents", order: 0 },
      b: { id: "b", name: "乙", gender: "female", generation_id: "children", order: 0 },
      c: { id: "c", name: "丙", gender: "male", generation_id: "children", order: 1 },
    },
    relationships: [
      { id: "r1", source_id: "a", target_id: "b", parent_label: "爸爸", child_label: "女儿", kind: "standard" },
      { id: "r2", source_id: "a", target_id: "c", parent_label: "爸爸", child_label: "儿子", kind: "standard" },
    ],
  };
}
function reset() {
  state = {
    config: { experimental_features_enabled: true, experimental_cross_generation: true, read_only: false },
    workspace: freshWorkspace(), perspective: true, selectionA: "b", selectionB: "c", selectionTarget: "b",
    focusedPersonId: null, linkSource: null, focusedRelationshipId: null,
    pathRequestId: 0, copyRequestId: 0, relationshipPathLoading: false, copyInFlight: false,
    relationshipPath: null, relationshipPathError: null, relationshipCopyText: null, relationshipCopyError: null, relationshipEvidenceOpen: false,
    history: { undo_label: "编辑人物", redo_label: "编辑人物" }, historyBusy: false, mutations: 0,
    editingPersonId: "b", editingRelationshipId: "r1",
  };
  apiCalls = []; pathRequests = []; clipboardWrites = []; toasts = []; htmlWrites = []; clipboardMode = "success";
  personEditor.saving = false; personEditor.removePhoto = false; relationshipSaving = false;
}
function api(path, options = {}) {
  apiCalls.push({ path, options });
  if (path.startsWith("/api/path?")) return new Promise((resolve, reject) => pathRequests.push({ path, resolve, reject }));
  if (path === "/api/config") return Promise.resolve({ experimental_features_enabled: true, experimental_cross_generation: true, read_only: false, read_only_reason: null });
  if (path === "/api/workspace") return Promise.resolve(workspaceResult);
  if (path === "/api/history") return Promise.resolve(state.history);
  return Promise.resolve(mutationResult);
}
function render() { renderCount += 1; renderSelection(); }
function renderHistory() {}
function updateNavigatorSelection() {}
function handleCameraResize() {}
function personGenerationName(id) { return state.workspace.generations.find((row) => row.id === id)?.name || ""; }
function showToast(message, tone) { toasts.push({ message, tone }); }
function hideToast() {}
function cancelActivePersonDrag() {}
function undoAction() { return { label: "撤销", run() {} }; }
function setPersonStatus() {}
function setPersonSaving(value) { personEditor.saving = value; }
function personGenderValue() { return $("#person-gender").value; }
function personFormValue() { return "saved"; }
function releasePersonPhotoPreview() {}
function updatePersonPreview() {}
function renderPersonRelatives() {}
function requestAnimationFrame() {}
async function closePersonDialog() { return true; }
async function askConfirmation() { return true; }
function relationshipKindValue() { return "standard"; }
function setRelationshipSaving(value) { relationshipSaving = value; }
function closeRelationshipDialog() {}

// These are the same functions and swap binding used by the browser application.
eval(extract("function createIcon(", "async function api("));
eval(extract("function workspaceFrom(", "function generations("));
eval(extract("function generations()", "async function loadWorkspace("));
eval(extract("async function loadWorkspace(", "function renderHistory("));
eval(extract("async function travelHistory(", "function requestDraw("));
eval(extract("function invalidateCopyRequest(", "async function toggleLinkMode("));
eval(extract("function clearPerspectiveSelection(", "function renderSelection("));
eval(extract("function renderSelection()", "function askConfirmation("));
eval(extract("async function savePerson(", "async function deletePerson("));
eval(extract("async function reorderPersonInGeneration(", "const RELATIONSHIP_KIND_LABELS"));
eval(extract("async function saveRelationship(", "async function enterPerspective("));
eval(extract('  $("#swap-selection").addEventListener(', '  $("#export-relationship").addEventListener('));

const multiResult = {
  path_text: "爸爸的儿子", person_ids: ["b", "a", "c"], relationship_ids: ["r1", "r2"],
  direct_relationship: { status: "resolved", results: [
    { label: "兄弟（长幼未知）", explanation: "双方共享父亲甲。" },
    { label: "父系共同祖先另一条路径中的堂兄弟（长幼未知）", explanation: "另一路径沿父系祖先相连。" },
  ], note: "存在多重亲属关系；人物排列不能作为长幼依据。" },
};
const legacyResult = { path_text: "爸爸的儿子", person_ids: ["b", "a", "c"], relationship_ids: ["r1", "r2"] };
const mixedResult = {
  path_text: "女儿的爸爸的爸爸的儿子",
  person_ids: ["b", "child", "father", "grandfather", "c"], relationship_ids: ["bridge-1", "bridge-2", "parent-1", "parent-2"],
  direct_relationship: { status: "unsupported", results: [], note: "这条混合链暂不作直接血亲推断。",
    composition: {
      label: "孩子的父亲的兄弟（长幼未知）",
      explanation: "乙 → 女儿丁 → 丁的父亲戊 → 戊的父亲己 → 丙；乙与戊通过共同孩子丁相连，戊与丙共享父亲己。",
      note: "只描述一种登记连接；共同孩子不等于夫妻，兄弟长幼未知。",
    },
  },
};
const reversedMixedResult = {
  path_text: "爸爸的儿子的女儿的妈妈",
  person_ids: [...mixedResult.person_ids].reverse(), relationship_ids: [...mixedResult.relationship_ids].reverse(),
  direct_relationship: { ...mixedResult.direct_relationship, composition: {
    ...mixedResult.direct_relationship.composition,
    label: "兄弟（长幼未知）的孩子的母亲",
    explanation: "丙 → 父亲己 → 戊 → 女儿丁 → 丁的母亲乙；仅按这个方向描述已登记的连接。",
  } },
};
const familiarResult = {
  path_text: "妈妈的爸爸的女儿的儿子的爸爸的爸爸的爸爸的爸爸的儿子的儿子的儿子的儿子",
  person_ids: ["b", "mother", "maternal-grandfather", "aunt", "cousin", "cousin-father", "grandfather", "great-grandfather",
    "ancestor", "ancestor-son", "relative-grandfather", "relative-father", "c"],
  relationship_ids: Array.from({ length: 12 }, (_,index) => "familiar-" + index),
  direct_relationship: { status: "unsupported", results: [], note: "混合链不作直接血亲推断。",
    composition: {
      label: "姨母的孩子的父亲的从堂侄子",
      explanation: "姨母一侧经已登记孩子进入另一家庭，再按父系关系分段连接到丙。",
      note: "只描述一种登记连接；这不是直接血亲结论，共同孩子不等于夫妻。",
    },
    appellation: {
      label: "表兄弟（平辈，长幼未知）",
      explanation: "按姨表亲一侧的家庭往来归纳为平辈表兄弟。完整家庭路径：乙 → 母亲 → 外祖父 → 姨母 → 姨表亲 → 父亲 → 父系长辈 → 丙。",
      note: "按亲戚往来称呼归纳。",
    },
  },
};
const reversedFamiliarResult = {
  path_text: "爸爸的爸爸的爸爸的爸爸的儿子的儿子的儿子的儿子的妈妈的爸爸的女儿的儿子",
  person_ids: [...familiarResult.person_ids].reverse(), relationship_ids: [...familiarResult.relationship_ids].reverse(),
  direct_relationship: { ...familiarResult.direct_relationship, appellation: {
    ...familiarResult.direct_relationship.appellation,
    explanation: "从丙一侧重新描述家庭往来。完整家庭路径：丙 → 父系长辈 → 父亲 → 姨表亲 → 姨母 → 外祖父 → 母亲 → 乙。",
    note: "从丙一侧按亲戚往来称呼归纳。",
  } },
};
function settlePath(result = multiResult, index = pathRequests.length - 1) { pathRequests[index].resolve(result); }
async function ready(result = multiResult) {
  const pending = prefetchRelationshipPath(); settlePath(result); await pending;
}
function assertCleared(message) {
  assert(state.relationshipPath === null && state.relationshipCopyText === null && state.relationshipPathError === null &&
    state.relationshipCopyError === null && !state.copyInFlight && !state.relationshipEvidenceOpen, message);
}
async function run() {
  reset();
  const first = prefetchRelationshipPath();
  assert(pathRequests[0].path === "/api/path?from=b&to=c", "requests retain the B-relative-to-A direction");
  assert(state.relationshipPathLoading && $("#selection-result").dataset.state === "loading", "query starts in loading state");
  settlePath(); await first;
  assert(state.relationshipPath.person_ids.join(",") === "b,a,c" && state.relationshipPath.relationship_ids.join(",") === "r1,r2", "complete path response is retained");
  assert(state.relationshipPath.direct_relationship === multiResult.direct_relationship && state.relationshipPath.labels.join(",") === "爸爸,儿子", "direct response and derived chain labels are retained together");
  const result = $("#selection-result");
  assert(text(result.children[0]) === "丙 是 乙 的", "the lead keeps B before A");
  assert(text(descendants(result, "result-chain")[0]) === "爸爸的儿子", "original step-by-step chain remains visible");
  assert(descendants(result, "direct-entry").length === 2, "every direct relationship is rendered");
  assert(descendants(result, "direct-label").map(text).join("|") === multiResult.direct_relationship.results.map((item) => item.label).join("|"), "labels including long and age-unknown titles remain intact");
  assert(descendants(result, "direct-explanation").every((node) => text(node).startsWith("依据：")), "each direct label has its evidence");
  assert(text(result).includes("实验") && text(result).includes(multiResult.direct_relationship.note), "experimental title and multiple/age note are visible");
  await copyRelationship();
  assert(clipboardWrites[0] === "丙 是 乙 的：爸爸的儿子", "resolved copy contains only the original chain and direction");
  assert(multiResult.direct_relationship.results.every((item) => !clipboardWrites[0].includes(item.label) && !clipboardWrites[0].includes(item.explanation)), "copy excludes every direct label and its evidence");
  assert(!clipboardWrites[0].includes("实验") && !clipboardWrites[0].includes(multiResult.direct_relationship.note), "copy excludes the experimental heading and note");
  assert(!state.copyInFlight && toasts.at(-1).tone === "success", "copy finishes and announces success");

  $("#swap-selection").listeners.click();
  assert(state.selectionA === "c" && state.selectionB === "b" && pathRequests.at(-1).path === "/api/path?from=c&to=b", "swap binding requests the reversed direction");
  assertCleared("swap clears prior derived result and copy state");
  settlePath({ path_text: "爸爸的女儿", direct_relationship: { status: "resolved", results: [{ label: "姐妹（长幼未知）", explanation: "共享父亲。" }], note: "长幼未知。" } });
  await Promise.resolve();
  assert(state.relationshipCopyText.startsWith("乙 是 丙 的：爸爸的女儿") && text(result).includes("姐妹（长幼未知）"), "swap displays the newly computed direction");

  await ready(legacyResult);
  assert(descendants(result, "direct-relationship").length === 0 && text(result).includes("爸爸的儿子"), "responses without the new field keep the chain without an empty experimental section");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "乙 是 丙 的：爸爸的儿子", "legacy copy keeps the original plain sentence");
  const unsupported = { path_text: "养父的儿子", direct_relationship: { status: "unsupported", results: [], note: "关系链包含特殊关系，不作血亲推断。" } };
  await ready(unsupported);
  assert(text(result).includes("养父的儿子") && text(result).includes("暂不支持直接称谓推导"), "special relation keeps its chain and explains unsupported inference");
  assert(text(result).includes(unsupported.direct_relationship.note) && !text(result).includes("没有亲属关系"), "unsupported note does not claim an absence of kinship");
  await copyRelationship();
  assert(!$("#export-relationship").disabled && clipboardWrites.at(-1) === "乙 是 丙 的：养父的儿子", "unsupported special relationship remains copyable as its original custom chain only");
  assert(!clipboardWrites.at(-1).includes(unsupported.direct_relationship.note) && !clipboardWrites.at(-1).includes("实验"), "unsupported copy excludes experimental limitations");
  await ready({ path_text: "妈妈的女儿", direct_relationship: { status: "failed", results: "invalid experimental results", note: "推导服务暂不可用" } });
  await copyRelationship();
  assert(!$("#export-relationship").disabled && clipboardWrites.at(-1) === "乙 是 丙 的：妈妈的女儿", "failed experimental status and unexpected result fields do not alter chain copy");
  assert(!clipboardWrites.at(-1).includes("推导服务") && !clipboardWrites.at(-1).includes("实验"), "experimental failure metadata is never copied");
  for (const [response, chain] of [
    [{ relationship_text: "养母的女儿" }, "养母的女儿"],
    [{ path: "妈妈的儿子" }, "妈妈的儿子"],
    [{ labels: ["父亲", "女儿"] }, "父亲的女儿"],
  ]) {
    await ready(response); await copyRelationship();
    assert(clipboardWrites.at(-1) === "乙 是 丙 的：" + chain, "legacy path fields remain compatible with chain-only copy");
  }
  const disconnected = { path_text: "", person_ids: [], relationship_ids: [], direct_relationship: { status: "disconnected", results: [], note: "当前记录不足以连接两人。" } };
  await ready(disconnected);
  assert(result.dataset.state === "none" && text(result).includes("这不代表两人没有亲属关系"), "disconnected state explains the limit of available records");
  assert(text(result).includes(disconnected.direct_relationship.note) && $("#export-relationship").disabled, "disconnected note is visible and unavailable chain cannot be copied");

  await ready();
  state.relationshipCopyError = "old clipboard error";
  const retry = prefetchRelationshipPath();
  assertCleared("requery with unchanged A/B clears old result, copy and error");
  pathRequests.at(-1).reject(new Error("service unavailable")); await retry;
  assert(result.dataset.state === "error" && state.relationshipPathError === "service unavailable", "query errors show the retry state");
  assert(!$("#export-relationship").disabled && text($("#export-relationship")) === "重试计算", "query errors leave the retry action available");
  const retryAction = copyRelationship(); settlePath(); await retryAction;
  assert(state.relationshipPathError === null && text(result).includes("兄弟"), "copy action retries calculation after a path error");
  clipboardMode = "failure"; await copyRelationship();
  assert(state.relationshipCopyError === "clipboard unavailable" && text($("#export-relationship")) === "重试复制", "clipboard failure offers retry without discarding the path");
  clipboardMode = "success"; await copyRelationship();
  assert(state.relationshipCopyError === null && !state.copyInFlight, "successful copy retry clears its error");

  const oldQuery = prefetchRelationshipPath(), oldIndex = pathRequests.length - 1;
  state.selectionTarget = "b"; selectPerspectivePerson("a");
  assertCleared("changing B clears the old result and copy");
  assert(pathRequests.at(-1).path === "/api/path?from=c&to=a", "selection change requests the current pair");
  settlePath({ path_text: "旧结果", direct_relationship: multiResult.direct_relationship }, oldIndex); await oldQuery;
  assert(state.relationshipPathLoading && state.relationshipPath === null, "late result for the previous pair cannot replace the active request");
  settlePath({ path_text: "爸爸", direct_relationship: { status: "resolved", results: [{ label: "父亲", explanation: "亲子连线。" }], note: "" } }); await Promise.resolve();
  assert(state.relationshipCopyText.startsWith("甲 是 丙 的：爸爸"), "new pair completes normally after a stale response");
  clearPerspectiveSelection("a");
  assertCleared("clearing A removes all derived state");
  assert(result.dataset.state === "empty" && $("#export-relationship").disabled, "partial selection hides results and disables copy");

  reset(); await ready();
  clipboardMode = "pending"; const oldCopy = copyRelationship();
  assert(state.copyInFlight, "pending clipboard write marks copy busy");
  const nextWorkspace = freshWorkspace(); nextWorkspace.people.c.name = "新丙";
  replaceWorkspace(nextWorkspace);
  assertCleared("workspace replacement invalidates in-flight copy and clears all results");
  assert(state.relationshipPathLoading && pathRequests.length === 2, "same A/B is recalculated after workspace replacement");
  resolveClipboard(); await oldCopy;
  assert(!toasts.some((toast) => toast.tone === "success"), "obsolete clipboard completion cannot announce current success");
  settlePath(); await Promise.resolve();
  assert(state.relationshipCopyText.startsWith("新丙 是 乙 的"), "refreshed copy uses names from the new workspace");

  const staleWorkspaceRequest = prefetchRelationshipPath();
  const snapshot = state.workspace, token = state.pathRequestId;
  state.workspace = freshWorkspace();
  assert(!isPathRequestCurrent(token, state.selectionA, state.selectionB, snapshot), "workspace identity is part of request validity even with the same token and pair");
  settlePath({ path_text: "迟到旧工作区" }); await staleWorkspaceRequest;
  assert(state.relationshipPath === null && state.relationshipCopyText === null, "response from another workspace snapshot cannot populate results");
  replaceWorkspace(state.workspace, false);

  // Each mutation below executes the real save/history/move functions with a server response boundary.
  reset(); await ready();
  $("#person-generation").value = "children"; $("#person-name").value = "乙"; $("#person-gender").value = "male";
  mutationResult = freshWorkspace(); mutationResult.people.b.gender = "male";
  await savePerson({ preventDefault() {} });
  assert(state.workspace.people.b.gender === "male" && state.relationshipPathLoading, "saving gender with unchanged names/pair recalculates kinship");
  assertCleared("person save clears prior result and copy");
  assert(pathRequests.length === 2, "person save starts exactly one replacement query");
  settlePath(); await Promise.resolve();

  const beforeOrder = pathRequests.length;
  mutationResult = freshWorkspace(); mutationResult.people.b.order = 1; mutationResult.people.c.order = 0;
  await reorderPersonInGeneration("c", "children", 0);
  assert(pathRequests.length === beforeOrder + 1 && state.relationshipPathLoading, "same-generation reorder invalidates and refreshes kinship");
  assertCleared("reorder does not preserve old titles");
  settlePath(); await Promise.resolve();
  mutationResult = freshWorkspace(); mutationResult.people.b.generation_id = "later"; mutationResult.relationships = [];
  await movePersonToGeneration("b", "later");
  assert(state.workspace.relationships.length === 0 && state.relationshipPathLoading, "moving generations recalculates after the server removes invalid links");
  settlePath(disconnected); await Promise.resolve();
  assert(result.dataset.state === "none", "move-derived disconnected state replaces prior inference");

  mutationResult = freshWorkspace(); mutationResult.relationships[0].kind = "special";
  await saveRelationship({ preventDefault() {} });
  assertCleared("relationship save clears stale resolved inference");
  assert(state.relationshipPathLoading, "relationship save refreshes the same pair");
  settlePath(unsupported); await Promise.resolve();
  mutationResult = freshWorkspace(); mutationResult.relationships = [];
  await deleteRelationship();
  assertCleared("relationship delete clears old chain and inference");
  settlePath(disconnected); await Promise.resolve();
  assert(text(result).includes("这不代表两人没有亲属关系"), "deleting the last connecting relation renders record-level uncertainty");

  for (const direction of ["undo", "redo"]) {
    reset(); await ready();
    const stale = prefetchRelationshipPath(), staleIndex = pathRequests.length - 1;
    mutationResult = freshWorkspace(); mutationResult.people.c.gender = "female";
    await travelHistory(direction);
    assertCleared(direction + " replaces and clears old results despite unchanged A/B");
    assert(state.relationshipPathLoading && !state.historyBusy, direction + " starts fresh kinship calculation and releases the history lock");
    settlePath({ path_text: "旧工作区关系" }, staleIndex); await stale;
    assert(state.relationshipPath === null && state.relationshipPathLoading, direction + " rejects a late response from the prior workspace");
    settlePath({ path_text: "爸爸的女儿", direct_relationship: { status: "resolved", results: [{ label: "姐妹（长幼未知）", explanation: "共享父亲。" }], note: "" } }); await Promise.resolve();
    assert(text(result).includes("姐妹（长幼未知）"), direction + " displays the recalculated title");
  }

  reset(); await ready();
  workspaceResult = freshWorkspace(); workspaceResult.people.b.name = "新乙";
  const loading = loadWorkspace();
  assertCleared("loadWorkspace clears derived state before its read completes");
  await loading;
  assert(state.workspaceLoaded && state.relationshipPathLoading && pathRequests.length === 2, "workspace synchronization refreshes the valid same pair once");
  settlePath(); await Promise.resolve();
  assert(state.relationshipCopyText.startsWith("丙 是 新乙 的"), "synchronized result uses new workspace names");
  const withoutB = freshWorkspace(); delete withoutB.people.c;
  replaceWorkspace(withoutB); render();
  assertCleared("replacement removing B clears all computed state");
  assert(state.selectionB === null && !state.relationshipPathLoading && $("#export-relationship").disabled, "removed selections are reconciled without querying missing people");
  // A mixed connection remains unsupported as a direct relation, but has its own useful experimental result.
  reset();
  const mixedPending = prefetchRelationshipPath();
  assert(result.dataset.state === "loading" && descendants(result, "direct-relationship").length === 0,
    "mixed request loading removes any previous experimental section");
  settlePath(mixedResult); await mixedPending;
  const composition = mixedResult.direct_relationship.composition;
  assert(state.relationshipPath.direct_relationship === mixedResult.direct_relationship &&
    state.relationshipPath.person_ids.join(",") === mixedResult.person_ids.join(",") &&
    state.relationshipPath.relationship_ids.join(",") === mixedResult.relationship_ids.join(","),
    "the full mixed response including its composition and path metadata is cached");
  const mixedSection = descendants(result, "direct-relationship")[0];
  assert(mixedSection.dataset.state === "unsupported" && state.relationshipPath.direct_relationship.results.length === 0,
    "composition does not promote a registered connection to a resolved direct relationship");
  assert(text(descendants(result, "direct-heading")[0]) === "关系链化简 · 实验" &&
    mixedSection.getAttribute("aria-label") === "关系链化简 · 实验", "mixed result has a distinct visual and accessible heading");
  assert(text(descendants(result, "direct-label")[0]) === composition.label, "the complete composition label is visible");
  assert(text(descendants(result, "direct-explanation")[0]) === "依据：" + composition.explanation,
    "mixed result includes the registered path and shared-child evidence");
  assert(text(descendants(result, "direct-note")[0]) === composition.note, "mixed uncertainty includes the shared-child marriage limitation");
  assert(!text(result).includes("暂不支持直接称谓推导") && !text(result).includes(mixedResult.direct_relationship.note),
    "generic unsupported wording does not conceal the useful composition");
  assert(text(result.children[0]) === "丙 是 乙 的" && text(descendants(result, "result-chain")[0]) === mixedResult.path_text,
    "mixed presentation preserves B-relative-to-A direction and the original chain");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "丙 是 乙 的：" + mixedResult.path_text, "mixed copy uses only the original relationship chain");
  assert([composition.label, composition.explanation, composition.note, "实验", "关系链化简"]
    .every((item) => !clipboardWrites.at(-1).includes(item)), "mixed copy excludes every experimental field");

  const staleMixed = prefetchRelationshipPath(), staleMixedIndex = pathRequests.length - 1;
  $("#swap-selection").listeners.click();
  assertCleared("mixed swap clears the previous composition and copy state");
  assert(pathRequests.at(-1).path === "/api/path?from=c&to=b" && result.dataset.state === "loading",
    "mixed swap starts a calculation for the reversed pair");
  settlePath(mixedResult, staleMixedIndex); await staleMixed;
  assert(state.relationshipPath === null && state.relationshipPathLoading, "late mixed response cannot overwrite the reversed request");
  settlePath(reversedMixedResult); await Promise.resolve();
  assert(text(result.children[0]) === "乙 是 丙 的" &&
    text(descendants(result, "direct-label")[0]) === reversedMixedResult.direct_relationship.composition.label,
    "mixed swap displays the reverse-specific composition");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "乙 是 丙 的：" + reversedMixedResult.path_text, "mixed reverse copy keeps its newly computed chain");

  state.selectionTarget = "a"; selectPerspectivePerson("a");
  assertCleared("replacing A clears the mixed composition");
  assert(pathRequests.at(-1).path === "/api/path?from=a&to=b", "changing A recalculates the current mixed direction");
  settlePath(mixedResult); await Promise.resolve();
  assert(text(result.children[0]) === "乙 是 甲 的", "replacement result uses the new A name");
  for (const slot of ["a", "b"]) {
    clearPerspectiveSelection(slot);
    assertCleared("clearing " + slot + " removes composition and copy state");
    assert(result.dataset.state === "empty" && descendants(result, "direct-relationship").length === 0 &&
      $("#export-relationship").disabled, "clearing " + slot + " hides the experimental result and disables copying");
  }

  reset();
  for (const invalid of [null, {}, { ...composition, label: 42 }, { ...composition, label: " " },
    { ...composition, explanation: null }, { ...composition, note: [] }, { ...composition, note: " " }]) {
    await ready({ ...mixedResult, direct_relationship: { ...mixedResult.direct_relationship, composition: invalid } });
    assert(text(result).includes("暂不支持直接称谓推导") && !text(result).includes("关系链化简") &&
      descendants(result, "direct-entry").length === 0, "malformed or incomplete composition falls back without fabricated results");
    await copyRelationship();
    assert(clipboardWrites.at(-1) === "丙 是 乙 的：" + mixedResult.path_text,
      "unusable experimental metadata does not prevent original-chain copying");
  }
  await ready({ ...multiResult, direct_relationship: { ...multiResult.direct_relationship, composition } });
  assert(text(descendants(result, "direct-heading")[0]) === "直接关系推导 · 实验" &&
    descendants(result, "direct-entry").length === 2 && !text(result).includes(composition.label),
    "resolved direct relationships keep precedence over unrelated composition metadata");
  await ready({ ...disconnected, direct_relationship: { ...disconnected.direct_relationship, composition } });
  assert(result.dataset.state === "none" && !text(result).includes(composition.label) && $("#export-relationship").disabled,
    "disconnected records cannot be made available by stray composition metadata");
  await ready({ ...mixedResult, direct_relationship: { status: "failed", results: [], note: "失败说明", composition } });
  assert(text(result).includes("暂不支持直接称谓推导") && !text(result).includes(composition.label),
    "composition is presented only for the agreed unsupported status");

  reset();
  state.workspace.people.b.name = '<img src=x onerror="alert(1)">乙';
  state.workspace.people.c.name = "<script>alert(2)</script>丙";
  const literalComposition = {
    label: '<img src=x onerror="alert(3)">养父的从堂侄子',
    explanation: "<script>alert(4)</script>这只是自由称谓登记路径。",
    note: "<b>共同孩子不等于夫妻</b>，自由称谓不证明血缘。",
  };
  const literalResult = { path_text: '<img src=x onerror="alert(5)">养父的儿子',
    direct_relationship: { status: "unsupported", results: [], composition: literalComposition } };
  await ready(literalResult);
  assert(text(result.children[0]) === state.workspace.people.c.name + " 是 " + state.workspace.people.b.name + " 的",
    "names containing HTML remain literal text in the result lead");
  assert(text(descendants(result, "result-chain")[0]) === literalResult.path_text,
    "custom relationship labels containing HTML remain literal original-chain text");
  assert(text(descendants(result, "direct-label")[0]) === literalComposition.label &&
    text(descendants(result, "direct-explanation")[0]) === "依据：" + literalComposition.explanation &&
    text(descendants(result, "direct-note")[0]) === literalComposition.note,
    "all composition fields preserve literal free titles and HTML-looking text");
  assert(htmlWrites.every((value) => value.startsWith('<svg focusable="false">')),
    "untrusted names and composition fields never enter an HTML parsing sink");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === state.workspace.people.c.name + " 是 " + state.workspace.people.b.name + " 的：" + literalResult.path_text,
    "literal special relationship copying stays chain-only");

  reset(); await ready(mixedResult);
  const priorWorkspaceQuery = prefetchRelationshipPath(), priorWorkspaceIndex = pathRequests.length - 1;
  const mixedWorkspace = freshWorkspace(); mixedWorkspace.people.c.name = "新丙";
  replaceWorkspace(mixedWorkspace);
  assertCleared("workspace replacement clears mixed results despite unchanged A/B");
  pathRequests[priorWorkspaceIndex].reject(new Error("late workspace failure")); await priorWorkspaceQuery;
  assert(state.relationshipPathLoading && state.relationshipPathError === null,
    "late failure from the prior workspace cannot affect the active mixed request");
  pathRequests.at(-1).reject(new Error("mixed service unavailable")); await Promise.resolve(); await Promise.resolve();
  assert(result.dataset.state === "error" && descendants(result, "direct-relationship").length === 0,
    "mixed calculation failure replaces the old composition with a retry state");
  const mixedRetry = copyRelationship(); settlePath(mixedResult); await mixedRetry;
  assert(text(result).includes(composition.label) && state.relationshipCopyText === "新丙 是 乙 的：" + mixedResult.path_text &&
    clipboardWrites.length === 0, "retry recalculates the mixed result before a new clipboard action");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "新丙 是 乙 的：" + mixedResult.path_text,
    "recalculated mixed result copies only the chain with current names");

  reset(); await ready(mixedResult);
  state.editingPersonId = "c";
  $("#person-generation").value = "children"; $("#person-name").value = "丙"; $("#person-gender").value = "female";
  mutationResult = freshWorkspace(); mutationResult.people.c.gender = "female";
  await savePerson({ preventDefault() {} });
  assertCleared("person editing invalidates cached mixed composition");
  const editedMixed = { ...mixedResult, path_text: "女儿的爸爸的爸爸的女儿",
    direct_relationship: { ...mixedResult.direct_relationship, composition: {
      ...composition, label: "孩子的父亲的姐妹（长幼未知）", explanation: "保存人物性别后重新描述登记链，丙为戊的姐妹。",
    } } };
  settlePath(editedMixed); await Promise.resolve();
  assert(text(descendants(result, "direct-label")[0]) === editedMixed.direct_relationship.composition.label,
    "person editing displays recalculated mixed titles");
  mutationResult = freshWorkspace(); mutationResult.relationships[0].kind = "special";
  await saveRelationship({ preventDefault() {} });
  assertCleared("relationship editing invalidates cached mixed composition");
  settlePath(literalResult); await Promise.resolve();
  assert(text(descendants(result, "direct-label")[0]) === literalComposition.label,
    "relationship editing can display free-title composition without blood inference");
  mutationResult = freshWorkspace(); mutationResult.relationships = [];
  await deleteRelationship();
  assertCleared("deleting a relationship clears the mixed chain and composition");
  settlePath(disconnected); await Promise.resolve();
  assert(result.dataset.state === "none" && !text(result).includes("关系链化简"),
    "deleting the connection replaces composition with record-level disconnection");

  for (const direction of ["undo", "redo"]) {
    reset(); await ready(mixedResult);
    const stale = prefetchRelationshipPath(), index = pathRequests.length - 1;
    mutationResult = freshWorkspace();
    await travelHistory(direction);
    assertCleared(direction + " clears cached composition before recalculating");
    settlePath(mixedResult, index); await stale;
    assert(state.relationshipPath === null && state.relationshipPathLoading,
      direction + " rejects a late mixed result from the previous workspace");
    settlePath(reversedMixedResult); await Promise.resolve();
    assert(text(descendants(result, "direct-label")[0]) === reversedMixedResult.direct_relationship.composition.label,
      direction + " displays the fresh mixed result");
    await copyRelationship();
    assert(clipboardWrites.at(-1) === "丙 是 乙 的：" + reversedMixedResult.path_text,
      direction + " still copies only the recalculated original chain");
  }
  reset(); await ready(mixedResult);
  workspaceResult = freshWorkspace(); workspaceResult.people.b.name = "新乙";
  const reloadMixed = loadWorkspace();
  assertCleared("workspace reload clears composition before its read completes");
  await reloadMixed;
  settlePath(mixedResult); await Promise.resolve();
  assert(text(result).includes(composition.label) && state.relationshipCopyText === "丙 是 新乙 的：" + mixedResult.path_text,
    "workspace reload refreshes mixed composition and current-name chain copying");
  // Everyday appellations lead the result; full records remain available through native disclosure.
  reset();
  state.workspace.people.b.name = "薛蟠"; state.workspace.people.c.name = "贾珍";
  await ready(familiarResult);
  const appellation = familiarResult.direct_relationship.appellation;
  const familiarComposition = familiarResult.direct_relationship.composition;
  const familiarSection = descendants(result, "direct-relationship")[0];
  let evidence = descendants(result, "relationship-evidence")[0];
  assert(state.relationshipPath.direct_relationship === familiarResult.direct_relationship &&
    state.relationshipPath.person_ids.join(",") === familiarResult.person_ids.join(",") &&
    state.relationshipPath.relationship_ids.join(",") === familiarResult.relationship_ids.join(","),
    "complete everyday response and original path records remain cached");
  assert(state.relationshipPath.direct_relationship.status === "unsupported" &&
    state.relationshipPath.direct_relationship.results.length === 0 &&
    state.relationshipPath.direct_relationship.note === familiarResult.direct_relationship.note &&
    state.relationshipPath.direct_relationship.composition === familiarComposition,
    "everyday display preserves original status, results, notes and composition metadata");
  assert(text(result.children[0]) === "贾珍 是 薛蟠 的" && visibleText(result).includes(appellation.label),
    "the target pair immediately shows its everyday cousin appellation in B-relative-to-A direction");
  assert(text(familiarSection.children[0]) === "亲戚称呼 · 实验" &&
    familiarSection.getAttribute("aria-label") === "亲戚称呼 · 实验", "everyday result has its own visible and accessible heading");
  assert(visibleText(result).includes(appellation.note) && !visibleText(result).includes(appellation.explanation),
    "main result shows the short human note while keeping detailed appellation evidence folded");
  assert(!visibleText(result).includes(familiarResult.path_text) && !visibleText(result).includes(familiarComposition.label) &&
    !visibleText(result).includes(familiarComposition.explanation), "long original structures no longer dominate the main result");
  assert(!text(result).includes(familiarComposition.note) && !text(result).includes(familiarResult.direct_relationship.note) &&
    !visibleText(result).includes("暂不支持"), "old blood-relationship warnings do not negate the everyday appellation");
  assert(evidence.tagName === "DETAILS" && !evidence.open && evidence.getAttribute("open") === null &&
    evidence.children[0].tagName === "SUMMARY" && text(evidence.children[0]) === "查看具体关系依据",
    "specific evidence uses an accessible native disclosure that is closed by default");
  assert(text(evidence).includes("原关系链") && text(descendants(evidence, "result-chain")[0]) === familiarResult.path_text,
    "disclosed evidence explicitly labels and retains the entire original relationship chain");
  assert(text(evidence).includes(appellation.explanation) && text(evidence).includes(familiarComposition.label) &&
    text(evidence).includes(familiarComposition.explanation), "appellation rules and composition facts remain available for review");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "贾珍 是 薛蟠 的：" + familiarResult.path_text,
    "closed everyday result copies the full original chain only");
  evidence = descendants(result, "relationship-evidence")[0]; clickDisclosure(evidence);
  assert(visibleText(result).includes(appellation.explanation) && visibleText(result).includes(familiarResult.path_text),
    "opening the native disclosure reveals the recorded basis and original chain");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "贾珍 是 薛蟠 的：" + familiarResult.path_text &&
    [appellation.label, appellation.explanation, appellation.note, familiarComposition.label, familiarComposition.note, "实验"]
      .every((item) => !clipboardWrites.at(-1).includes(item)), "opening evidence does not add experimental fields to clipboard output");
  assert(descendants(result, "relationship-evidence")[0].open && visibleText(result).includes(appellation.explanation),
    "copy feedback rerenders retain the expanded evidence for the current query");
  const cachedFamiliarPath = state.relationshipPath, cachedFamiliarCopy = state.relationshipCopyText;
  renderSelection();
  assert(descendants(result, "relationship-evidence")[0].open &&
    state.relationshipPath === cachedFamiliarPath && state.relationshipCopyText === cachedFamiliarCopy,
    "same-query repaint preserves disclosure state without changing API data or copy semantics");
  clickDisclosure(descendants(result, "relationship-evidence")[0], renderSelection);
  assert(!descendants(result, "relationship-evidence")[0].open && !visibleText(result).includes(familiarResult.path_text),
    "summary click closes the disclosure even when a bubbling action repaints it");
  renderSelection();
  assert(!descendants(result, "relationship-evidence")[0].open && !visibleText(result).includes(appellation.explanation),
    "same-query repaint also preserves an explicitly closed disclosure");
  clickDisclosure(descendants(result, "relationship-evidence")[0], renderSelection);
  assert(descendants(result, "relationship-evidence")[0].open &&
    visibleText(result).includes(appellation.explanation) && visibleText(result).includes(familiarResult.path_text),
    "summary click opens exactly once and survives repaint before native default activation");
  const retiredEvidence = descendants(result, "relationship-evidence")[0];
  const newFamiliarQuery = prefetchRelationshipPath();
  assertCleared("requery invalidates the expanded evidence together with prior relationship data");
  clickDisclosure(retiredEvidence);
  assert(!state.relationshipEvidenceOpen && result.dataset.state === "loading",
    "a click queued on retired evidence cannot reopen it while a replacement query is loading");
  settlePath(familiarResult); await newFamiliarQuery;
  assert(!descendants(result, "relationship-evidence")[0].open,
    "a replacement query starts with evidence folded even when A/B did not change");
  clickDisclosure(retiredEvidence); renderSelection();
  assert(!descendants(result, "relationship-evidence")[0].open,
    "retired evidence cannot change the new query after its response arrives");

  const teacherAppellation = { label: "老师", explanation: "按登记称谓称呼。完整登记路径：乙 → 丙。",
    note: "按双方登记称谓称呼。" };
  await ready({ path_text: "老师", direct_relationship: { status: "unsupported", results: [], appellation: teacherAppellation } });
  assert(visibleText(result).includes("亲戚称呼 · 实验") && text(descendants(result, "direct-label")[0]) === "老师" &&
    !visibleText(result).includes("表兄弟"), "a valid appellation without composition displays its registered special title without guessing cousins");
  assert(text(descendants(result, "relationship-evidence")[0]).includes(teacherAppellation.explanation),
    "appellation-only responses retain their complete registered-path explanation");
  for (const invalid of [null, {}, { ...appellation, label: 42 }, { ...appellation, label: " " },
    { ...appellation, explanation: null }, { ...appellation, note: [] }, { ...appellation, note: " " }]) {
    await ready({ ...familiarResult, direct_relationship: { ...familiarResult.direct_relationship, appellation: invalid } });
    assert(text(descendants(result, "direct-heading")[0]) === "关系链化简 · 实验" &&
      visibleText(result).includes(familiarComposition.label) && descendants(result, "relationship-evidence").length === 0,
      "malformed appellation falls back to the compatible existing composition presentation");
    await copyRelationship();
    assert(clipboardWrites.at(-1) === "贾珍 是 薛蟠 的：" + familiarResult.path_text,
      "invalid everyday metadata leaves original-chain copying available");
  }
  await ready({ path_text: "老师的学生", direct_relationship: { status: "unsupported", results: [], note: "仅保留登记称谓。" } });
  assert(text(result).includes("暂不支持直接称谓推导") && !text(result).includes("表兄弟"),
    "an older server without everyday or composition fields keeps its existing fallback without inventing a family title");
  await ready({ ...multiResult, direct_relationship: { ...multiResult.direct_relationship, appellation, composition: familiarComposition } });
  assert(text(descendants(result, "direct-heading")[0]) === "直接关系推导 · 实验" &&
    descendants(result, "direct-entry").length === 2 && descendants(result, "relationship-evidence").length === 0 &&
    !text(result).includes(appellation.label), "resolved blood relationships keep every precise result ahead of stray everyday metadata");
  await ready({ ...disconnected, direct_relationship: { ...disconnected.direct_relationship, appellation, composition: familiarComposition } });
  assert(result.dataset.state === "none" && !text(result).includes(appellation.label) &&
    descendants(result, "relationship-evidence").length === 0 && $("#export-relationship").disabled,
    "disconnection takes precedence over any stray everyday metadata");
  await ready({ path_text: "老师", direct_relationship: { status: "failed", results: [], note: "失败说明", appellation } });
  assert(!text(result).includes(appellation.label) && descendants(result, "relationship-evidence").length === 0,
    "daily appellations are used only for the agreed connected unsupported status");

  reset();
  state.workspace.people.b.name = '<img src=x onerror="alert(6)">乙';
  state.workspace.people.c.name = "<script>alert(7)</script>丙";
  const literalAppellation = { label: '<img src=x onerror="alert(8)">养父',
    explanation: "<script>alert(9)</script>完整登记路径：养父。",
    note: "<b>按家庭往来称呼。</b>" };
  const literalFamiliar = { ...literalResult, direct_relationship: { ...literalResult.direct_relationship, appellation: literalAppellation } };
  await ready(literalFamiliar);
  assert(text(result.children[0]) === state.workspace.people.c.name + " 是 " + state.workspace.people.b.name + " 的" &&
    text(descendants(result, "direct-label")[0]) === literalAppellation.label, "HTML-looking names and everyday labels remain literal visible text");
  assert(visibleText(result).includes(literalAppellation.note) &&
    text(descendants(result, "relationship-evidence")[0]).includes(literalAppellation.explanation),
    "HTML-looking daily notes and disclosed explanations remain literal text");
  assert(htmlWrites.every((value) => value.startsWith('<svg focusable="false">')),
    "everyday fields never enter an HTML parsing sink");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === state.workspace.people.c.name + " 是 " + state.workspace.people.b.name + " 的：" + literalFamiliar.path_text,
    "literal daily fields and disclosed structures do not change chain-only copying");

  reset(); await ready(familiarResult); clickDisclosure(descendants(result, "relationship-evidence")[0]);
  const oldFamiliar = prefetchRelationshipPath(), oldFamiliarIndex = pathRequests.length - 1;
  $("#swap-selection").listeners.click();
  assertCleared("everyday swap clears previous appellation and copy state");
  assert(result.dataset.state === "loading" && descendants(result, "relationship-evidence").length === 0 &&
    pathRequests.at(-1).path === "/api/path?from=c&to=b", "everyday swap removes stale disclosures and requests the reversed pair");
  settlePath(familiarResult, oldFamiliarIndex); await oldFamiliar;
  assert(state.relationshipPath === null && state.relationshipPathLoading, "late everyday response cannot overwrite the reversed request");
  settlePath(reversedFamiliarResult); await Promise.resolve();
  assert(text(result.children[0]) === "乙 是 丙 的" &&
    visibleText(result).includes(reversedFamiliarResult.direct_relationship.appellation.note) &&
    text(descendants(result, "relationship-evidence")[0]).includes(reversedFamiliarResult.direct_relationship.appellation.explanation),
    "swap uses newly calculated direction-specific everyday notes and evidence");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "乙 是 丙 的：" + reversedFamiliarResult.path_text, "reversed everyday copy uses only the reversed original chain");

  for (const slot of ["a", "b"]) {
    reset(); await ready(familiarResult); clickDisclosure(descendants(result, "relationship-evidence")[0]);
    const stale = prefetchRelationshipPath(), index = pathRequests.length - 1;
    state.selectionTarget = slot; selectPerspectivePerson("a");
    assertCleared("replacing " + slot + " clears the everyday result");
    settlePath(familiarResult, index); await stale;
    assert(state.relationshipPath === null && state.relationshipPathLoading, "changing " + slot + " rejects a late everyday response");
    settlePath(reversedFamiliarResult); await Promise.resolve();
    assert(visibleText(result).includes(reversedFamiliarResult.direct_relationship.appellation.note),
      "changing " + slot + " renders fresh everyday metadata");
    clickDisclosure(descendants(result, "relationship-evidence")[0]); clearPerspectiveSelection(slot);
    assert(!state.relationshipEvidenceOpen && result.dataset.state === "empty" && descendants(result, "relationship-evidence").length === 0 && $("#export-relationship").disabled,
      "clearing " + slot + " removes daily results and disclosures");
  }

  reset(); await ready(familiarResult); clickDisclosure(descendants(result, "relationship-evidence")[0]);
  state.editingPersonId = "c";
  $("#person-generation").value = "children"; $("#person-name").value = "丙"; $("#person-gender").value = "female";
  mutationResult = freshWorkspace(); mutationResult.people.c.gender = "female";
  await savePerson({ preventDefault() {} });
  assertCleared("person editing clears cached everyday titles and copy text");
  const editedFamiliar = { ...familiarResult, path_text: familiarResult.path_text.replace(/儿子$/, "女儿"),
    direct_relationship: { ...familiarResult.direct_relationship, appellation: {
      ...appellation, label: "表姐妹（平辈，长幼未知）", explanation: "按更新后的家庭称呼归纳。完整家庭路径：乙 → 家庭成员 → 丙。",
    } } };
  settlePath(editedFamiliar); await Promise.resolve();
  assert(text(descendants(result, "direct-label")[0]) === editedFamiliar.direct_relationship.appellation.label,
    "person editing shows the freshly computed everyday title");
  mutationResult = freshWorkspace(); mutationResult.relationships[0].kind = "special";
  await saveRelationship({ preventDefault() {} });
  assertCleared("relationship editing invalidates cached everyday titles");
  settlePath(literalFamiliar); await Promise.resolve();
  assert(text(descendants(result, "direct-label")[0]) === literalAppellation.label,
    "relationship editing displays returned special family titles as everyday text");
  mutationResult = freshWorkspace(); mutationResult.relationships = [];
  await deleteRelationship();
  assertCleared("relationship deletion clears everyday labels and original copy chain");
  settlePath(disconnected); await Promise.resolve();
  assert(result.dataset.state === "none" && descendants(result, "relationship-evidence").length === 0,
    "deletion replaces everyday labels and evidence with current record-level disconnection");

  for (const direction of ["undo", "redo"]) {
    reset(); await ready(familiarResult); clickDisclosure(descendants(result, "relationship-evidence")[0]);
    const stale = prefetchRelationshipPath(), index = pathRequests.length - 1;
    mutationResult = freshWorkspace();
    await travelHistory(direction);
    assertCleared(direction + " clears everyday labels before requerying");
    settlePath(familiarResult, index); await stale;
    assert(state.relationshipPath === null && state.relationshipPathLoading, direction + " rejects a late everyday result from the old workspace");
    settlePath(reversedFamiliarResult); await Promise.resolve();
    assert(visibleText(result).includes(reversedFamiliarResult.direct_relationship.appellation.note) &&
      !descendants(result, "relationship-evidence")[0].open, direction + " shows fresh everyday metadata with evidence folded again");
    await copyRelationship();
    assert(clipboardWrites.at(-1) === "丙 是 乙 的：" + reversedFamiliarResult.path_text,
      direction + " copies only the current original chain");
  }

  reset(); await ready(familiarResult); clickDisclosure(descendants(result, "relationship-evidence")[0]);
  clipboardMode = "pending"; const pendingEverydayCopy = copyRelationship();
  const changedFamiliarWorkspace = freshWorkspace(); changedFamiliarWorkspace.people.c.name = "新丙";
  replaceWorkspace(changedFamiliarWorkspace);
  assertCleared("workspace replacement clears everyday results and invalidates a pending copy");
  resolveClipboard(); await pendingEverydayCopy;
  assert(!toasts.some((toast) => toast.tone === "success"), "obsolete everyday clipboard completion cannot announce current success");
  settlePath(familiarResult); await Promise.resolve();
  clipboardMode = "success"; await copyRelationship();
  assert(clipboardWrites.at(-1) === "新丙 是 乙 的：" + familiarResult.path_text,
    "workspace replacement refreshes everyday metadata while original-chain copy uses current names");
  const failingEveryday = prefetchRelationshipPath();
  assert(result.dataset.state === "loading" && descendants(result, "relationship-evidence").length === 0,
    "requery hides cached everyday titles and old disclosure");
  pathRequests.at(-1).reject(new Error("everyday service unavailable")); await failingEveryday;
  assert(result.dataset.state === "error" && descendants(result, "relationship-evidence").length === 0,
    "everyday query failure shows retry without stale labels or evidence");
  const retryEveryday = copyRelationship(); settlePath(familiarResult); await retryEveryday;
  assert(visibleText(result).includes(appellation.label) && state.relationshipCopyText === "新丙 是 乙 的：" + familiarResult.path_text,
    "retry recalculates everyday labels and retains chain-only copy text");
  workspaceResult = freshWorkspace(); workspaceResult.people.b.name = "新乙";
  const reloadEveryday = loadWorkspace();
  assertCleared("workspace reload clears everyday labels before the read completes");
  await reloadEveryday;
  settlePath(familiarResult); await Promise.resolve();
  assert(visibleText(result).includes(appellation.label) && state.relationshipCopyText === "丙 是 新乙 的：" + familiarResult.path_text,
    "workspace synchronization displays daily labels using current workspace names");

  print("PASS " + checks + " kinship UI assertions (JSC, memory-only)");
}
let completed = false, failure = null;
run().then(() => { completed = true; }, (error) => { failure = error; });
drainMicrotasks();
if (failure) throw failure;
if (!completed) throw new Error("Kinship UI assertions did not finish");
