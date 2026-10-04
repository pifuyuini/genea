// Run from the repository root with the macOS JavaScriptCore helper:
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_cross_generation_ui.js
// Executes the application against the shared memory-only navigation DOM.
// No server, files, storage, browser, or real clipboard are changed.
var navigationHarness = readFile("tests/test_navigation_ui.js");
var harnessEnd = navigationHarness.indexOf("function runNavigationTests()");
if (harnessEnd < 0) throw new Error("Shared navigation harness boundary changed");
eval(navigationHarness.slice(0, harnessEnd));

const baseElement = element;
element = function (tag, id) {
  const node = baseElement(tag, id), append = node.append;
  node.append = function (...items) {
    append.call(this, ...items.map((item) => {
      if (typeof item !== "string") return item;
      const text = baseElement("text"); text.textContent = item; return text;
    }));
  };
  return node;
};
document.createElement = element;
document.createElementNS = (_, tag) => element(tag);
document.createTextNode = (text) => { const node = element("text"); node.textContent = text; return node; };
var genderInputs = [{ value: "male", checked: false }, { value: "female", checked: true }];
var relationshipInputs = [{ value: "standard", checked: true }, { value: "special", checked: false }];
const baseQuery = query, baseQueryAll = queryAll;
query = function (selector, root) {
  if (selector === '#person-gender input[name="person-gender"]:checked') return genderInputs.find((input) => input.checked);
  if (selector === '#relationship-kind input[name="relationship-kind"]:checked') return relationshipInputs.find((input) => input.checked);
  if (selector === ".lane-header") return root?.children.find((child) => child.classList.contains("lane-header")) || null;
  const relationship = selector.match(/^\.(relationship-path|relationship-hit)\[data-relationship-id="([^"]+)"\]$/);
  if (relationship) return query("#relationship-layer").children.find((child) =>
    child.classList.contains(relationship[1]) && child.getAttribute("data-relationship-id") === relationship[2]) || null;
  return baseQuery(selector, root);
};
queryAll = function (selector, root) {
  if (selector === '#person-gender input[name="person-gender"]') return genderInputs;
  if (selector === '#relationship-kind input[name="relationship-kind"]') return relationshipInputs;
  if (selector === ".person-node") return root && root !== document ? personNodes.filter((node) => root.contains(node)) : personNodes;
  if (selector === ".person-node.is-inspected") return personNodes.filter((node) => node.classList.contains("is-inspected"));
  return baseQueryAll(selector, root);
};
document.querySelector = query;
document.querySelectorAll = queryAll;
function setTimeout() { return 0; }
function clearTimeout() {}
// Camera animation is outside this test; camera and connector calculations remain real.
function createValueSpring(read, write) {
  return { stop() {}, to(value) { write(value); } };
}
function response(data, ok = true) { return { ok, json: async () => data }; }
function clone(value) { return JSON.parse(JSON.stringify(value)); }
function allText(node) { return node.children.length ? node.children.map(allText).join("") : node.textContent; }
function pathSamples(path) {
  const tokens = path.match(/[MLVHQ]|-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi), output = [];
  let index = 0, point = [0, 0];
  function line(next) {
    const count = Math.max(1, Math.ceil(Math.hypot(next[0] - point[0], next[1] - point[1]) / 4));
    for (let step = 1; step <= count; step += 1) output.push([
      point[0] + (next[0] - point[0]) * step / count,
      point[1] + (next[1] - point[1]) * step / count,
    ]);
    point = next;
  }
  while (index < tokens.length) {
    const command = tokens[index++];
    if (command === "M") { point = [Number(tokens[index++]), Number(tokens[index++])]; output.push(point); }
    else if (command === "L") line([Number(tokens[index++]), Number(tokens[index++])]);
    else if (command === "H") line([Number(tokens[index++]), point[1]]);
    else if (command === "V") line([point[0], Number(tokens[index++])]);
    else if (command === "Q") {
      const control = [Number(tokens[index++]), Number(tokens[index++])];
      const next = [Number(tokens[index++]), Number(tokens[index++])];
      for (let step = 1; step <= 20; step += 1) {
        const t = step / 20, u = 1 - t;
        output.push([u * u * point[0] + 2 * u * t * control[0] + t * t * next[0],
          u * u * point[1] + 2 * u * t * control[1] + t * t * next[1]]);
      }
      point = next;
    } else throw new Error("Unrecognized SVG command: " + command);
  }
  return output;
}

async function runCrossGenerationTests() {
  var requests = [], toasts = [], clipboardWrites = [];
  var configResponse = { experimental_features_enabled: false, experimental_cross_generation: false, read_only: false, read_only_reason: null };
  var fixture = {
    generations: Array.from({ length: 7 }, (_, index) => ({ id: "g" + (index + 1), name: "第 " + (index + 1) + " 行", position: index })),
    people: {
      early: { id: "early", name: "上行父亲", gender: "male", generation_id: "g1", order: 0 },
      near: { id: "near", name: "相邻子女", gender: "female", generation_id: "g2", order: 0 },
      unknown: { id: "unknown", name: "未填性别", gender: "", generation_id: "g2", order: 1 },
      middle: { id: "middle", name: "右侧中间人物", gender: "male", generation_id: "g3", order: 0 },
      mother: { id: "mother", name: "母亲", gender: "female", generation_id: "g5", order: 0 },
      peer: { id: "peer", name: "同排人物", gender: "male", generation_id: "g5", order: 1 },
      father: { id: "father", name: "父亲", gender: "male", generation_id: "g6", order: 0 },
      baby: { id: "baby", name: "末代儿子", gender: "male", generation_id: "g7", order: 0 },
      free: { id: "free", name: "末代女儿", gender: "female", generation_id: "g7", order: 1 },
    },
    relationships: [
      { id: "r-m", parent_id: "mother", child_id: "baby", kind: "standard", parent_label: "妈妈", child_label: "儿子" },
      { id: "r-f", parent_id: "father", child_id: "baby", kind: "standard", parent_label: "爸爸", child_label: "儿子" },
      { id: "r-a", parent_id: "early", child_id: "baby", kind: "standard", parent_label: "爸爸", child_label: "儿子" },
      { id: "r-adj", parent_id: "early", child_id: "near", kind: "standard", parent_label: "爸爸", child_label: "女儿" },
    ],
  };
  var history = { undo_label: "编辑人物", redo_label: null };
  state.workspace = clone(fixture); state.history = clone(history); state.camera.hasFit = true;
  state.workspaceLoaded = false; state.perspective = false;
  render = function () {};
  renderWorkspaceChrome = function () {};
  showToast = (message, tone) => toasts.push({ message, tone });
  fetch = async (path, options = {}) => {
    requests.push({ path, options });
    if (path === "/api/config") return response(configResponse);
    if (path === "/api/workspace") return response(fixture);
    if (path === "/api/history") return response(history);
    return response({ workspace: clone(state.workspace) });
  };
  await loadWorkspace();
  assert(state.config.experimental_cross_generation === false && state.workspaceLoaded, "default runtime config loads before enabling workspace interactions");
  assert(requests.map((request) => request.path).join(",") === "/api/config,/api/workspace,/api/history", "config is a read outside workspace/history APIs");
  assert(Object.keys(state.workspace).sort().join(",") === "generations,people,relationships" &&
    JSON.stringify(state.history) === JSON.stringify(history) && state.mutations === 0, "configuration never enters serialized workspace or history");
  renderModeControls();
  assert($("#cross-generation-status").hidden && $("#help-cross-generation").hidden &&
    $("#help-link-target").textContent.includes("相邻代"), "ordinary mode keeps its adjacent-generation guide and hides experimental labeling");

  const pairs = [["mother", "free"], ["free", "mother"], ["mother", "father"], ["mother", "peer"],
    ["unknown", "baby"], ["baby", "baby"], ["mother", "baby"], ["missing", "baby"], ["early", "free"]];
  for (const enabled of [false, true]) {
    state.config.experimental_features_enabled = state.config.experimental_cross_generation = enabled;
    for (const [first, second] of pairs) {
      const allowed = canLinkPeople(first, second), before = requests.length;
      await createDraggedRelationship(first, second);
      assert(requests.length === before + Number(allowed), (enabled ? "experimental" : "ordinary") + " candidate/submit agreement: " + first + " → " + second);
      if (allowed) {
        const body = JSON.parse(requests.at(-1).options.body), rows = generations();
        assert(rows.findIndex((row) => row.id === personById(body.source_id).generation_id) <
          rows.findIndex((row) => row.id === personById(body.target_id).generation_id), "submitted relationship always puts the parent above the child");
      } else assert(toasts.at(-1).tone === "error", "invalid candidates get an actionable error before POST");
    }
  }
  state.config.experimental_features_enabled = state.config.experimental_cross_generation = true;
  renderModeControls();
  assert(!$("#cross-generation-status").hidden && !$("#help-cross-generation").hidden &&
    $("#cross-generation-status").textContent !== undefined && $("#help-link-target").textContent.includes("任意上行或下行"), "experimental mode has a visible badge and an accurate link guide");
  state.editingPersonId = "mother";
  renderPersonRelatives();
  const options = $("#person-relative-add").children.filter((group) => group.tagName === "OPTGROUP");
  assert(options.length === 2 && options[0].label === "设为父母" && options[1].label === "设为子女", "all rows in the inspector are classified as parents or children");
  assert(options.flatMap((group) => group.children).map((option) => option.value).sort().join(",") ===
    people().filter((person) => canLinkPeople("mother", person.id)).map((person) => person.id).sort().join(","), "inspector offers exactly the same candidates as drag and click linking");
  assert(options.flatMap((group) => group.children).every((option) => option.textContent.includes(personGenerationName(personById(option.value).generation_id))), "every relative option labels its actual row");
  state.config.experimental_features_enabled = state.config.experimental_cross_generation = false;
  renderPersonRelatives();
  assert($("#person-relative-add").children.filter((group) => group.tagName === "OPTGROUP")
    .flatMap((group) => group.children).every((option) => personById(option.value).generation_id === "g6"), "ordinary inspector still offers only adjacent rows");
  state.config.experimental_features_enabled = state.config.experimental_cross_generation = true;
  assert(personMoveNotice("mother", "g7").includes("同排或倒置") && personMoveNotice("baby", "g5").includes("拒绝"), "experimental move preview explains same-row and reversed parent/child conflicts");
  assert(!personMoveNotice("mother", "g4"), "legal experimental moves preserve a non-adjacent parent relationship");
  state.config.experimental_features_enabled = state.config.experimental_cross_generation = false;
  assert(personMoveNotice("mother", "g4").includes("取消 1 条不再相邻"), "ordinary move preview retains automatic edge-removal behavior");
  state.config.experimental_features_enabled = state.config.experimental_cross_generation = true;

  // Geometry includes very wide intermediate content and row headings taller than the cards.
  const board = $("#generation-board"), stage = $("#canvas-stage"), lanes = $("#generation-lanes"), svg = $("#relationship-layer");
  board.clientWidth = 1000; board.clientHeight = 700; board.rect = rect(100, 80, 1000, 700);
  $("#person-dialog").open = false; $("#selection-tray").hidden = true; $(".selection-tray").hidden = true;
  $("#canvas-navigator").hidden = true; $(".camera-controls").hidden = true;
  lanes.scrollWidth = 2200; lanes.scrollHeight = 1260;
  stage.offsetWidth = 2200; stage.clientWidth = 2200; stage.offsetHeight = 1260; stage.clientHeight = 1260;
  stage.measure = () => rect(112 + state.camera.x, 98 + state.camera.y, lanes.scrollWidth * state.camera.scale, lanes.scrollHeight * state.camera.scale);
  Object.defineProperty(svg, "innerHTML", { get() { return ""; }, set() { this.replaceChildren(); } });
  Object.defineProperty(stage, "scrollWidth", { get() { return Math.max(lanes.scrollWidth, Number(svg.getAttribute("width") || 0)); } });
  Object.assign(state.camera, { x: 0, y: 0, scale: 1 });
  function measureNode(node, box) {
    node.world = box;
    node.measure = () => { const base = stage.getBoundingClientRect(); return rect(
      base.left + box.left * state.camera.scale, base.top + box.top * state.camera.scale,
      box.width * state.camera.scale, box.height * state.camera.scale); };
    return node;
  }
  laneNodes = generations().map((row, index) => {
    const lane = element("section"); lane.className = "generation-lane"; lane.dataset.generationId = row.id;
    const header = element("div"); header.className = "lane-header";
    measureNode(header, rect(8, index * 180 + 12, 176, 140));
    lane.append(header); return lane;
  });
  personNodes = people().map((person) => {
    const level = generations().findIndex((row) => row.id === person.generation_id);
    const card = element("article"); card.className = "person-node"; card.dataset.personId = person.id;
    measureNode(card, rect(person.id === "middle" ? 1960 : 260 + person.order * 230, level * 180 + 48, 180, 80));
    laneNodes[level].append(card); return card;
  });
  function routed(id) { return $('.relationship-path[data-relationship-id="' + id + '"]'); }
  function noIntersections(id) {
    const edge = relationshipEnds(relationshipById(id)), samples = pathSamples(routed(id).getAttribute("d"));
    const obstacles = personNodes.filter((node) => ![String(edge.sourceId), String(edge.targetId)].includes(node.dataset.personId))
      .concat(laneNodes.map((lane) => lane.children[0]));
    return obstacles.every((node) => !samples.some(([x, y]) => x > node.world.left && x < node.world.right &&
      y > node.world.top && y < node.world.bottom));
  }
  drawRelationships();
  for (const id of ["r-m", "r-a"]) {
    assert(routed(id).getAttribute("data-cross-generation") === "true" && noIntersections(id), "cross-generation SVG avoids every intermediate card and row heading: " + id);
    assert(routed(id).getAttribute("d").includes("Q"), "cross-generation channels retain rounded corners: " + id);
  }
  assert(routed("r-f").getAttribute("data-cross-generation") === "false" && routed("r-f").getAttribute("d").includes(" V "),
    "adjacent father-to-child routing keeps the original channel algorithm");
  const motherPoints = pathSamples(routed("r-m").getAttribute("d")), fatherPoints = pathSamples(routed("r-f").getAttribute("d"));
  assert(motherPoints.at(-1)[0] !== fatherPoints.at(-1)[0], "adjacent and cross-generation parents use distinct shared child ports");
  const bounds = cameraContentBounds(), maxX = Math.max(...motherPoints.map((point) => point[0]));
  assert(maxX > lanes.scrollWidth && bounds.width > maxX, "external channel stays to the right of all content and inside overview bounds");
  assert(Number(svg.getAttribute("width")) === bounds.width && svg.getAttribute("viewBox") === "0 0 " + bounds.width + " " + bounds.height &&
    stage.scrollWidth === bounds.width, "SVG/viewBox and canvas stage scrolling extent include external channels");
  const firstRoutes = new Map(["r-m", "r-a"].map((id) => [id, routed(id).getAttribute("d")]));
  state.workspace.relationships.reverse(); drawRelationships();
  assert([...firstRoutes].every(([id, d]) => routed(id).getAttribute("d") === d), "stable relationship IDs retain channels when data order changes");
  Object.assign(state.camera, { x: 145, y: -82, scale: 0.5 }); drawRelationships();
  assert([...firstRoutes].every(([id, d]) => routed(id).getAttribute("d") === d), "pan and zoom normalization preserve world connector geometry");
  const middle = personNodes.find((node) => node.dataset.personId === "middle");
  middle.world.left = 3100; middle.world.right = 3280; lanes.scrollWidth = 3400;
  stage.offsetWidth = 3400; stage.clientWidth = 3400; drawRelationships();
  assert(noIntersections("r-m") && Math.max(...pathSamples(routed("r-m").getAttribute("d")).map((point) => point[0])) > middle.world.right,
    "redrawing after a wider row moves the channel beyond newly positioned middle cards");
  fitCamera();
  const visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.left + visible.width >= cameraContentBounds().width,
    "real overview camera includes the expanded channel at all zoom levels");
  $("#canvas-navigator").hidden = false; state.navigator.collapsed = false; updateNavigatorGeometry();
  assert($("#navigator-edges").children.filter((node) => node.tagName === "PATH").length === 2, "navigator uses actual external SVG routes for cross-generation edges");
  assert($("#navigator-edges").children.filter((node) => node.tagName === "PATH")
    .every((node) => node.getAttribute("vector-effect") === "non-scaling-stroke"),
    "minimap channel strokes stay visible after world-coordinate scaling");
  assert(state.navigator.map.scale * cameraContentBounds().width <= 184.00001,
    "navigator world range includes the complete external-channel width");
  state.workspace.relationships = state.workspace.relationships.filter((edge) => !["r-m", "r-a"].includes(edge.id));
  drawRelationships();
  assert(cameraContentBounds().width === lanes.scrollWidth && Number(svg.getAttribute("width")) === lanes.scrollWidth,
    "removing the last cross-generation edge shrinks overview and SVG extents without stale feedback");
  state.workspace = clone(fixture); state.camera.scale = 1;

  // Actual save/move handlers preserve the received workspace and present atomic server rejection.
  $("#person-name").value = "母亲的新简介"; $("#person-introduction").value = "仅编辑资料";
  $("#person-generation").value = "g5"; $("#person-photo").files = [];
  state.editingPersonId = "mother"; personEditor.baseline = "";
  const edgesBeforeEdit = JSON.stringify(state.workspace.relationships);
  fetch = async (path, options = {}) => {
    requests.push({ path, options });
    const value = clone(state.workspace);
    if (path === "/api/people/mother") Object.assign(value.people.mother, JSON.parse(options.body));
    return response({ workspace: value, removed_relationship_ids: [] });
  };
  await savePerson({ preventDefault() {} });
  assert(JSON.stringify(state.workspace.relationships) === edgesBeforeEdit && personById("mother").introduction === "仅编辑资料" &&
    $("#person-save-status").textContent === "已保存", "metadata save preserves cross-generation edges through the real inspector handler");
  assert($("#person-generation-warning").hidden, "metadata-only editing does not warn about detaching cross-generation edges");
  $("#person-generation").value = "g4"; updatePersonPreview();
  assert($("#person-generation-warning").dataset.kind === "info" && $("#person-generation-warning").textContent.includes("保留"),
    "legal experimental inspector move previews retained relationships");
  $("#person-generation").value = "g7"; updatePersonPreview();
  assert($("#person-generation-warning").dataset.kind === "error" && $("#person-generation-warning").textContent.includes("此次修改会被拒绝"),
    "invalid experimental inspector move previews the atomic rejection");
  const beforeRejectedMove = JSON.stringify(state.workspace);
  fetch = async (path, options) => { requests.push({ path, options }); return response({ error: "无法移动「母亲」：与「末代儿子」同排，现有关系保留" }, false); };
  await movePersonToGeneration("mother", "g7");
  assert(JSON.stringify(state.workspace) === beforeRejectedMove && toasts.at(-1).tone === "error" &&
    toasts.at(-1).message.includes("末代儿子"), "a rejected move keeps the confirmed workspace and shows the server's conflict person");
  await savePerson({ preventDefault() {} });
  assert(JSON.stringify(state.workspace) === beforeRejectedMove && $("#person-save-status").dataset.kind === "error" &&
    $("#person-save-status").textContent.includes("末代儿子"), "rejected inspector save keeps all edges and surfaces server conflict details");

  // Config failures cannot silently present an adjacent-only canvas for experimental data.
  state.workspaceLoaded = false; requests = [];
  fetch = async (path, options) => { requests.push({ path, options }); return response({ error: "config unavailable" }, false); };
  let failed = false;
  try { await loadWorkspace(); } catch { failed = true; }
  assert(failed && state.workspaceLoadFailed && requests.length === 1 && requests[0].path === "/api/config",
    "configuration failure marks initial loading failed before reading an ambiguous workspace");
  fetch = async (path, options) => {
    requests.push({ path, options });
    return response(path === "/api/config" ? { experimental_features_enabled: true, experimental_cross_generation: true, read_only: false, read_only_reason: null } : path === "/api/history" ? history : fixture);
  };
  await loadWorkspace();
  assert(state.workspaceLoaded && !state.workspaceLoadFailed && state.config.experimental_cross_generation,
    "successful retry clears the config load failure and restores experimental capability");

  // New results and clipboard tasks still invalidate across a workspace replacement.
  state.perspective = true; state.selectionA = "baby"; state.selectionB = "mother";
  var pathRequests = [];
  fetch = (path, options) => {
    requests.push({ path, options });
    return new Promise((resolve) => pathRequests.push({ path, resolve }));
  };
  var navigator = { clipboard: { writeText(value) { clipboardWrites.push(value); return Promise.resolve(); } } };
  // The production clipboard helper resolves the global navigator.
  globalThis.navigator = navigator;
  const old = prefetchRelationshipPath();
  const oldPath = pathRequests[0];
  replaceWorkspace(clone(state.workspace));
  assert(state.relationshipPath === null && state.relationshipCopyText === null && state.relationshipPathLoading && pathRequests.length === 2,
    "workspace replacement invalidates experimental path results and starts a fresh request");
  oldPath.resolve(response({ path_text: "旧称谓", person_ids: ["baby", "mother"], relationship_ids: ["r-m"] }));
  await old;
  assert(state.relationshipPath === null && state.relationshipPathLoading, "late pre-replacement result cannot revive a stale cross-generation title");
  const result = { path_text: "妈妈", person_ids: ["baby", "mother"], relationship_ids: ["r-m"],
    direct_relationship: { status: "unsupported", results: [], note: "画布行距不能推导亲属称谓",
      appellation: { label: "实验称呼", explanation: "显示说明", note: "只展示结果" } } };
  pathRequests[1].resolve(response(result));
  for (let turn = 0; state.relationshipPathLoading && turn < 20; turn += 1) await Promise.resolve();
  assert(state.relationshipPath?.person_ids.join(",") === "baby,mother" && state.relationshipCopyText === "母亲 是 末代儿子 的：妈妈",
    "fresh cross-generation result retains original path records and chain text");
  await copyRelationship();
  assert(clipboardWrites.at(-1) === "母亲 是 末代儿子 的：妈妈" && !clipboardWrites.at(-1).includes("实验称呼"),
    "copy action still copies only the original relation chain");
  assert(pathRequests.every((request) => request.path === "/api/path?from=baby&to=mother"),
    "cross-generation capability never adds visual row distance or mode flags to the existing path API");

  print("PASS " + checks + " cross-generation UI assertions (JSC, memory-only)");
}
var completed = false, failure = null;
const startup = source.lastIndexOf("\nsetTheme(state.theme);");
if (startup < 0) throw new Error("Application startup boundary changed");
eval(source.slice(0, startup) + "\n(" + runCrossGenerationTests.toString() + ")().then(() => { completed = true; }, error => { failure = error; });");
drainMicrotasks();
if (failure) throw failure;
if (!completed) throw new Error("Cross-generation UI assertions did not finish");
