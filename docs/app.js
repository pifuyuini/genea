const SVG_NS = "http://www.w3.org/2000/svg";
const DRAG_THRESHOLD = 9;
const THEME_QUERY = "(prefers-color-scheme: dark)";
const THEME_KEY = "genea-appearance";
const state = {
  workspace: { generations: [], people: {}, relationships: [] },
  // An explicit choice is remembered; otherwise the atlas follows the system appearance.
  theme: localStorage.getItem(THEME_KEY) || (localStorage.getItem("genea-theme") === "mocha" ? "mocha" : null) ||
    (matchMedia(THEME_QUERY).matches ? "mocha" : "latte"),
  editingGenerationId: null, editingPersonId: null, editingRelationshipId: null,
  generationIntent: null, confirmationResolver: null,
  perspective: false, selectionA: null, selectionB: null, selectionTarget: "a",
  copyRequestId: 0, copyInFlight: false, relationshipCopyError: null,
  pathRequestId: 0, relationshipPathLoading: false, relationshipCopyText: null,
  relationshipPathError: null, relationshipPath: null,
  linkMode: false, linkSource: null, drag: null,
  focusedPersonId: null, searchQuery: "", searchActiveIndex: -1,
  activeRelationshipId: null, focusedRelationshipId: null,
  activeRelationshipPersonId: null,
  camera: {
    x: 0, y: 0, scale: 1, pan: null, hasFit: false,
    viewportWidth: 0, viewportHeight: 0, viewport: null, resizeFrame: null,
    spaceHeld: false, suppressClick: null,
  },
  navigator: { collapsed: false, frame: null, geometryDirty: true, map: null, drag: null },
  drawFrame: null,
  history: { undo_label: null, redo_label: null }, historyBusy: false, mutations: 0,
  workspaceLoaded: false, workspaceLoadFailed: false, connectionFailed: false, saveFailed: false,
  focusedGenerationId: null,
};
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
function createIcon(name) {
  const icon = document.createElement("span");
  icon.className = "icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = '<svg focusable="false"><use href="#i-' + name + '"></use></svg>';
  return icon;
}

function isReadonlyDemo() {
  return typeof window !== "undefined" && window.GeneaDemo?.readonly === true;
}
function preventDemoEdit(event) {
  if (!isReadonlyDemo()) return false;
  event?.preventDefault();
  return true;
}
function configureReadonlyDemo() {
  if (!isReadonlyDemo()) return;
  document.body.dataset.readonly = "true";
  $(".workspace-title h2").textContent = "示例家谱";
  $(".sidebar-footer span").textContent = "虚构演示资料 · 不保存修改";
  $("#select-mode .mode-label").textContent = "浏览";
  $("#select-mode").dataset.tooltip = "浏览 · V";
  $(".camera-controls").setAttribute("aria-label", "画布视图");
  $(".help-header h2").textContent = "浏览示例家谱";
  $("#load-error p").textContent = "演示数据暂时无法载入，请检查网络后重试。";
  for (const row of $$(".help-grid dl > div")) {
    if (/排序或调整代际|建立亲子关系|撤销|重做|保存人物档案/.test(row.textContent)) row.hidden = true;
    if (row.textContent.includes("编辑 / 连线 / 关系")) {
      $("dt", row).textContent = "浏览 / 关系";
      $("dd", row).textContent = "V / R";
    }
  }
  for (const selector of ["#link-mode", "#generation-menu-toggle", "#add-first-generation",
    "#add-generation-above", "#add-generation-below", "#history-undo", "#history-redo",
    "#person-photo", "#person-photo-remove", "#person-save", "#person-delete",
    "#person-relative-add", "#person-relative-confirm", "#relationship-save", "#relationship-delete",
    "#generation-submit"]) {
    $(selector).disabled = true;
  }
  for (const control of $$("#person-gender input, #relationship-kind input, #person-generation")) {
    control.disabled = true;
  }
  for (const control of $$("#person-name, #person-introduction, #parent-label, #child-label")) {
    control.readOnly = true;
    control.removeAttribute("required");
  }
  const photo = $(".photo-picker");
  photo.tabIndex = -1;
  photo.removeAttribute("role");
  photo.setAttribute("aria-label", "人物照片");
  for (const button of $$("button.button[data-close-dialog]")) button.textContent = "关闭";
  $("[data-close-dialog=relationship-dialog]").setAttribute("aria-label", "关闭关系详情");
  const download = document.createElement("a");
  download.className = "primary-button demo-download";
  download.href = window.GeneaDemo.downloadUrl;
  download.textContent = "下载完整版";
  download.setAttribute("aria-label", "下载 Genea 完整版本，在本机编辑自己的家谱");
  $(".header-actions").prepend(download);
}

async function api(path, options = {}) {
  const mutating = options.method && options.method.toUpperCase() !== "GET";
  if (mutating && isReadonlyDemo()) throw new Error("公开只读演示不保存修改，请下载完整版。");
  if (mutating && (state.mutations || (state.historyBusy && !path.startsWith("/api/history/")))) {
    throw new Error("上一步正在保存，请稍后再试");
  }
  if (mutating) { state.mutations += 1; renderHistory(); renderWorkspaceSaveState(); }
  try {
    if (isReadonlyDemo()) {
      const data = await window.GeneaDemo.request(path, options);
      state.connectionFailed = false;
      return data;
    }
    let response;
    try {
      response = await fetch(path, {
        ...options,
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      });
    } catch {
      state.connectionFailed = true;
      throw new Error("暂时无法连接服务，请检查连接后重试");
    }
    state.connectionFailed = false;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.details?.errors?.join("；") || data.error || "请求失败");
    if (mutating) state.saveFailed = false;
    if (data.history) state.history = data.history;
    return data;
  } catch (error) {
    if (mutating) state.saveFailed = true;
    if (!state.workspaceLoaded && (path === "/api/workspace" || path === "/api/history")) state.workspaceLoadFailed = true;
    throw error;
  } finally {
    if (mutating) { state.mutations -= 1; renderHistory(); }
    renderWorkspaceSaveState();
  }
}
function hideToast() {
  clearTimeout(showToast.timer);
  showToast.timer = null;
  $("#toast").classList.remove("is-visible");
}

const TOAST_ICONS = { info: "info", success: "check", error: "alert" };
function showToast(message, tone = "info", action = null) {
  const toast = $("#toast");
  const text = document.createElement("span");
  text.className = "toast-message";
  text.textContent = message;
  toast.replaceChildren(createIcon(TOAST_ICONS[tone] || "info"), text);
  if (action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action.label;
    button.addEventListener("click", () => { hideToast(); action.run(); });
    toast.append(button);
  }
  toast.dataset.tone = tone;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(hideToast, action ? 6000 : tone === "error" ? 5200 : 3200);
}
// Offer a one-step undo for the mutation that just finished.
function undoAction() {
  return { label: "撤销", run: () => travelHistory("undo") };
}
function workspaceFrom(data) {
  const value = data.workspace || data.state || data;
  return {
    generations: value.generations || [],
    people: value.people || value.persons || [],
    relationships: value.relationships || [],
  };
}
function generations() {
  const rows = state.workspace.generations || [];
  return [...rows].sort((a, b) =>
    (a.position ?? a.order ?? a.index ?? rows.indexOf(a)) -
    (b.position ?? b.order ?? b.index ?? rows.indexOf(b))
  );
}
function people() {
  const value = state.workspace.people;
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}
function peopleInGeneration(generationId) {
  const all = people();
  const sourceIndex = new Map(all.map((person, index) => [String(person.id), index]));
  const orderValue = (person) => {
    const value = person.order;
    return value !== null && value !== undefined && Number.isFinite(Number(value))
      ? Number(value)
      : sourceIndex.get(String(person.id));
  };
  return all
    .filter((person) => String(person.generation_id) === String(generationId))
    .sort((a, b) => orderValue(a) - orderValue(b) ||
      sourceIndex.get(String(a.id)) - sourceIndex.get(String(b.id)));
}
function relationships() { return state.workspace.relationships || []; }
function personById(id) { return people().find((item) => String(item.id) === String(id)); }
function relationshipById(id) { return relationships().find((item) => String(item.id) === String(id)); }
function personName(id) { return personById(id)?.name || "未知人物"; }
function relationshipEnds(item) {
  return { sourceId: item.source_id ?? item.parent_id, targetId: item.target_id ?? item.child_id };
}
async function loadWorkspace() {
  state.workspace = workspaceFrom(await api("/api/workspace"));
  state.history = await api("/api/history");
  state.workspaceLoaded = true;
  state.workspaceLoadFailed = false;
  state.saveFailed = false;
  reconcileWorkspaceSelection();
  render();
  if (state.perspective) prefetchRelationshipPath();
}
function reconcileWorkspaceSelection() {
  if (state.selectionA && !personById(state.selectionA)) { state.selectionA = null; state.selectionTarget = "a"; }
  if (state.selectionB && !personById(state.selectionB)) { state.selectionB = null; state.selectionTarget = "b"; }
  if (!personById(state.focusedPersonId)) state.focusedPersonId = null;
  if (!personById(state.linkSource)) state.linkSource = null;
  if (!relationshipById(state.focusedRelationshipId)) state.focusedRelationshipId = null;
}
function renderHistory() {
  for (const direction of ["undo", "redo"]) {
    const button = $("#history-" + direction);
    const verb = direction === "undo" ? "撤销" : "重做";
    const label = state.history[direction + "_label"];
    button.disabled = isReadonlyDemo() || state.historyBusy || state.mutations > 0 || !label;
    button.setAttribute("aria-label", label ? verb + "：" + label : verb);
    button.dataset.tooltip = label ? verb + "「" + label + "」 · " + (direction === "undo" ? "⌘/Ctrl Z" : "⌘/Ctrl ⇧Z") : "暂无可" + verb + "的操作";
  }
}
async function travelHistory(direction) {
  if (preventDemoEdit()) return;
  const label = state.history[direction + "_label"];
  if (!label || state.historyBusy || state.mutations || personEditor.saving || $("dialog:modal")) return;
  state.historyBusy = true;
  renderHistory();
  try {
    if ($("#person-dialog").open && !await closePersonDialog()) return;
    cancelActivePersonDrag();
    invalidateRelationshipTasks();
    const result = await api("/api/history/" + direction, { method: "POST", body: "{}" });
    state.workspace = workspaceFrom(result);
    reconcileWorkspaceSelection();
    render({ animate: true });
    if (state.perspective) prefetchRelationshipPath();
    showToast((direction === "undo" ? "已撤销 · " : "已重做 · ") + label, "success");
  } catch (error) {
    try { await loadWorkspace(); } catch { /* Keep the last confirmed canvas when offline. */ }
    showToast(error.message, "error");
  } finally {
    state.historyBusy = false;
    renderHistory();
  }
}
function requestDraw() {
  if (state.drawFrame !== null) return;
  state.drawFrame = requestAnimationFrame(() => {
    state.drawFrame = null;
    drawRelationships();
  });
}
function render({ animate = false, velocities = {} } = {}) {
  const positions = animate || nodeMotions.size ? captureNodePositions() : null;
  stopNodeMotions();
  state.activeRelationshipId = null;
  state.activeRelationshipPersonId = null;
  renderBoard();
  refreshPersonGenerationOptions();
  renderWorkspaceChrome();
  renderSelection();
  renderModeControls();
  renderSearchResults();
  renderHistory();
  applyCamera();
  if (positions) animateNodesFrom(positions, velocities);
  requestDraw();
  if (!state.camera.hasFit && generations().length > 0) {
    state.camera.hasFit = true;
    requestAnimationFrame(fitReadableCamera);
  }
}
function renderWorkspaceSaveState() {
  const output = $("#workspace-save-state");
  if (!output) return;
  let status = isReadonlyDemo() ? "readonly" : "saved", text = isReadonlyDemo() ? "公开只读演示" : "画布已保存";
  if (state.mutations) { status = "saving"; text = "保存中…"; }
  else if (state.connectionFailed) { status = "error"; text = "连接失败"; }
  else if (state.saveFailed) { status = "error"; text = "保存失败"; }
  else if (state.workspaceLoadFailed) { status = "error"; text = "载入失败"; }
  else if (!state.workspaceLoaded) { status = "loading"; text = "正在载入"; }
  else if (personHasChanges()) { status = "draft"; text = "未保存更改"; }
  output.dataset.state = status;
  output.textContent = text;
}
function renderWorkspaceChrome() {
  const rows = generations();
  $("#workspace-people-count").textContent = people().length;
  $("#workspace-generation-count").textContent = rows.length;
  $("#workspace-relationship-count").textContent = relationships().length;
  if (!rows.some((row) => String(row.id) === String(state.focusedGenerationId))) state.focusedGenerationId = null;
  const navigation = $("#generation-navigation");
  const focusedId = navigation.contains(document.activeElement) ? document.activeElement.dataset.generationId : null;
  navigation.replaceChildren();
  rows.forEach((row, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "generation-nav-item";
    button.dataset.generationId = row.id;
    const count = peopleInGeneration(row.id).length;
    button.setAttribute("aria-label", (row.name || "未命名代际") + "，" + count + " 人，定位代际");
    if (String(row.id) === String(state.focusedGenerationId)) button.setAttribute("aria-current", "true");
    const number = document.createElement("span");
    number.className = "generation-nav-index";
    number.textContent = String(index + 1).padStart(2, "0");
    const name = document.createElement("span");
    name.className = "generation-nav-name";
    name.textContent = row.name || "未命名代际";
    const badge = document.createElement("span");
    badge.className = "generation-nav-count";
    badge.textContent = count;
    badge.setAttribute("aria-hidden", "true");
    button.append(number, name, badge);
    navigation.append(button);
    if (String(focusedId) === String(row.id)) button.focus({ preventScroll: true });
  });
  $("#workspace-overview").setAttribute("aria-current", state.focusedGenerationId === null ? "true" : "false");
  $$(".generation-lane").forEach((lane) =>
    lane.classList.toggle("is-focused", String(lane.dataset.generationId) === String(state.focusedGenerationId)));
  renderWorkspaceSaveState();
  syncWorkspaceSidebar();
}
function isCompactWorkspace() {
  return matchMedia("(max-width: 900px)").matches;
}
function syncWorkspaceSidebar() {
  const compact = isCompactWorkspace();
  if (!compact) document.body.classList.remove("sidebar-open");
  const expanded = compact ? document.body.classList.contains("sidebar-open") : !document.body.classList.contains("sidebar-collapsed");
  $("#workspace-sidebar-toggle").setAttribute("aria-expanded", String(expanded));
  $("#workspace-sidebar-toggle").setAttribute("aria-label", expanded ? "收起代际导航" : "展开代际导航");
  if (!expanded && $("#workspace-sidebar").contains(document.activeElement)) {
    $("#workspace-sidebar-toggle").focus({ preventScroll: true });
  }
}
function closeWorkspaceSidebar(restoreFocus = false) {
  if (!document.body.classList.contains("sidebar-open")) return false;
  document.body.classList.remove("sidebar-open");
  syncWorkspaceSidebar();
  handleCameraResize();
  if (restoreFocus) $("#workspace-sidebar-toggle").focus({ preventScroll: true });
  return true;
}
function toggleWorkspaceSidebar() {
  closeWorkspaceHelp();
  document.body.classList.toggle(isCompactWorkspace() ? "sidebar-open" : "sidebar-collapsed");
  syncWorkspaceSidebar();
  handleCameraResize();
}
function closeWorkspaceHelp(restoreFocus = false) {
  const popover = $("#help-popover");
  const wasOpen = !popover.hidden;
  popover.hidden = true;
  $("#help-toggle").setAttribute("aria-expanded", "false");
  if (restoreFocus && wasOpen) $("#help-toggle").focus({ preventScroll: true });
  return wasOpen;
}
function toggleWorkspaceHelp(event) {
  event.stopPropagation();
  const shouldOpen = $("#help-popover").hidden;
  closeGenerationMenu();
  closeSearchResults();
  $("#help-popover").hidden = !shouldOpen;
  $("#help-toggle").setAttribute("aria-expanded", String(shouldOpen));
}
const nodeMotions = new Map();
function captureNodePositions() {
  return new Map($$(".person-node").map((node) => [node.dataset.personId, node.getBoundingClientRect()]));
}
function stopNodeMotions() {
  const hadMotions = nodeMotions.size > 0;
  for (const motion of nodeMotions.values()) motion.stop();
  nodeMotions.clear();
  if (hadMotions) requestNavigatorUpdate(true);
}
function animateNodesFrom(positions, velocities = {}) {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    requestDraw();
    requestNavigatorUpdate(true);
    return;
  }
  for (const node of $$(".person-node")) {
    const before = positions.get(node.dataset.personId);
    if (!before) {
      node.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160 });
      continue;
    }
    const after = node.getBoundingClientRect();
    let offset = { x: (before.left - after.left) / state.camera.scale, y: (before.top - after.top) / state.camera.scale };
    if (Math.hypot(offset.x, offset.y) < 0.5) continue;
    node.classList.add("is-settling");
    const paint = (value) => {
      offset = value;
      node.style.transform = "translate3d(" + value.x + "px," + value.y + "px,0)";
      requestDraw();
    };
    paint(offset);
    const motion = createValueSpring(() => offset, paint, () => {
      node.style.transform = "";
      node.classList.remove("is-settling");
      nodeMotions.delete(node.dataset.personId);
      requestDraw();
      // FLIP transforms can inflate scrollWidth until the last card settles.
      // Rebuild once from final layout, never on each animation frame.
      if (!nodeMotions.size) requestNavigatorUpdate(true);
    });
    nodeMotions.set(node.dataset.personId, motion);
    motion.to({ x: 0, y: 0 }, { velocity: velocities[node.dataset.personId] });
  }
  if (!nodeMotions.size) requestNavigatorUpdate(true);
}
const cameraMotion = createValueSpring(
  () => ({ x: state.camera.x, y: state.camera.y, scale: state.camera.scale }),
  (value) => { Object.assign(state.camera, value); applyCamera(); },
);
function moveCameraTo(value, immediate = false) {
  cameraMotion.to(value, { immediate });
}
// Board-local visible coordinates are shared by fitting, focus and the navigator.
function getCameraViewport() {
  const board = $("#generation-board");
  const boardRect = board.getBoundingClientRect();
  const stageRect = $("#canvas-stage").getBoundingClientRect();
  let right = board.clientWidth;
  let bottom = board.clientHeight;
  const inspector = $("#person-dialog");
  if (inspector.open && !matchMedia("(max-width: 719px)").matches) {
    const rect = inspector.getBoundingClientRect();
    if (rect.left < boardRect.left + right && rect.left + rect.width > boardRect.left) {
      right = Math.max(1, rect.left - boardRect.left - 16);
    }
  }
  for (const selector of [".camera-controls", "#selection-tray"]) {
    const element = $(selector);
    if (!element || element.hidden) continue;
    const rect = element.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && rect.left < boardRect.left + right &&
        rect.left + rect.width > boardRect.left && rect.top < boardRect.top + bottom) {
      bottom = Math.max(1, rect.top - boardRect.top - 16);
    }
  }
  const navigator = $("#canvas-navigator");
  if (!isCompactWorkspace() && navigator && !navigator.hidden) {
    const rect = navigator.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0 && rect.left < boardRect.left + right &&
        rect.left + rect.width > boardRect.left && rect.top < boardRect.top + bottom &&
        rect.top + rect.height > boardRect.top) {
      // Keep the larger fit beside or above the corner overlay. This decision uses
      // layout dimensions, never camera scale, so panning/zooming cannot flip it.
      const beside = { width: Math.max(1, Math.min(right, rect.left - boardRect.left - 12)), height: bottom };
      const above = { width: right, height: Math.max(1, Math.min(bottom, rect.top - boardRect.top - 12)) };
      const bounds = cameraContentBounds();
      const besideScale = fitBoundsScale(bounds, beside), aboveScale = fitBoundsScale(bounds, above);
      const available = besideScale > aboveScale ||
        (besideScale === aboveScale && beside.width * beside.height > above.width * above.height) ? beside : above;
      right = available.width;
      bottom = available.height;
    }
  }
  return {
    left: 0, top: 0, width: right, height: bottom,
    baseX: stageRect.left - boardRect.left - state.camera.x,
    baseY: stageRect.top - boardRect.top - state.camera.y,
  };
}
function cameraViewportWorld(viewport, camera = state.camera) {
  return {
    left: (viewport.left - viewport.baseX - camera.x) / camera.scale,
    top: (viewport.top - viewport.baseY - camera.y) / camera.scale,
    width: viewport.width / camera.scale,
    height: viewport.height / camera.scale,
  };
}
function cameraForWorldCenter(worldX, worldY, scale, viewport) {
  return {
    x: viewport.left + viewport.width / 2 - viewport.baseX - worldX * scale,
    y: viewport.top + viewport.height / 2 - viewport.baseY - worldY * scale,
    scale,
  };
}
function cameraContentBounds() {
  const lanes = $("#generation-lanes");
  return { left: 0, top: 0, width: lanes.scrollWidth, height: lanes.scrollHeight };
}
function fitBoundsScale(bounds, viewport, padding = 16) {
  if (!bounds.width || !bounds.height) return 1;
  return Math.min(2.25, Math.max(1, viewport.width - padding * 2) / bounds.width,
    Math.max(1, viewport.height - padding * 2) / bounds.height);
}
function clampCameraScale(value) {
  const minimum = Math.min(0.2, fitBoundsScale(cameraContentBounds(), getCameraViewport()));
  return Math.min(2.25, Math.max(minimum, value));
}

function applyCamera() {
  const stage = $("#canvas-stage");
  const board = $("#generation-board");
  state.camera.viewportWidth = board.clientWidth;
  state.camera.viewportHeight = board.clientHeight;
  stage.style.transformOrigin = "0 0";
  stage.style.transform = "translate3d(" + state.camera.x + "px," + state.camera.y +
    "px,0) scale(" + state.camera.scale + ")";
  const percent = state.camera.scale * 100;
  $("#camera-zoom-level").textContent = (percent < 1 ? percent.toPrecision(2) : Math.round(percent)) + "%";
  state.camera.viewport = getCameraViewport();
  // Far views trade secondary card details for larger names; card boxes never resize.
  stage.classList.toggle("is-far", state.camera.scale < (stage.classList.contains("is-far") ? 0.56 : 0.5));
  paintCanvasGrid(state.camera.viewport);
  requestNavigatorUpdate();
}
function paintCanvasGrid(viewport) {
  const grid = $(".canvas-grid");
  if (!grid) return;
  let size = 24 * state.camera.scale;
  while (size < 14) size *= 2;
  while (size > 44) size /= 2;
  const originX = (viewport.baseX + state.camera.x) % size;
  const originY = (viewport.baseY + state.camera.y) % size;
  grid.style.backgroundSize = size + "px " + size + "px";
  grid.style.transform = "translate3d(" + originX + "px," + originY + "px,0)";
}

function setCameraScale(value, clientX, clientY, animated = false) {
  const next = clampCameraScale(value);
  if (next === state.camera.scale) {
    cameraMotion.stop();
    return;
  }
  const boardRect = $("#generation-board").getBoundingClientRect();
  const viewport = getCameraViewport();
  const pointerX = clientX - boardRect.left;
  const pointerY = clientY - boardRect.top;
  const worldX = (pointerX - viewport.baseX - state.camera.x) / state.camera.scale;
  const worldY = (pointerY - viewport.baseY - state.camera.y) / state.camera.scale;
  moveCameraTo({
    x: pointerX - viewport.baseX - worldX * next,
    y: pointerY - viewport.baseY - worldY * next,
    scale: next,
  }, !animated);
}
function zoomCamera(multiplier) {
  const rect = $("#generation-board").getBoundingClientRect();
  const viewport = getCameraViewport();
  setCameraScale(
    (cameraMotion.running ? cameraMotion.target.scale : state.camera.scale) * multiplier,
    rect.left + viewport.left + viewport.width / 2,
    rect.top + viewport.top + viewport.height / 2, true,
  );
}
function resetCamera() {
  const viewport = getCameraViewport();
  const world = cameraViewportWorld(viewport);
  moveCameraTo(cameraForWorldCenter(world.left + world.width / 2,
    world.top + world.height / 2, 1, viewport));
}
function applyFitCamera(keepReadable) {
  const bounds = cameraContentBounds();
  if (!generations().length || !bounds.width || !bounds.height) {
    moveCameraTo({ x: 0, y: 0, scale: 1 }, keepReadable);
    return;
  }
  const viewport = getCameraViewport();
  const naturalScale = fitBoundsScale(bounds, viewport);
  const scale = keepReadable ? Math.max(naturalScale, 0.75) : naturalScale;
  const camera = cameraForWorldCenter(bounds.left + bounds.width / 2,
    bounds.top + bounds.height / 2, scale, viewport);
  if (keepReadable && bounds.width * scale > viewport.width - 32) {
    camera.x = viewport.left + 16 - viewport.baseX - bounds.left * scale;
  }
  if (keepReadable && bounds.height * scale > viewport.height - 32) {
    camera.y = viewport.top + 16 - viewport.baseY - bounds.top * scale;
  }
  moveCameraTo(camera, keepReadable);
}
function fitCamera() { applyFitCamera(false); }
function fitReadableCamera() { applyFitCamera(true); }

function focusPersonInCanvas(personId) {
  const node = $('.person-node[data-person-id="' + CSS.escape(String(personId)) + '"]');
  if (!node) {
    fitCamera();
    return false;
  }
  const box = stageBox(node, $("#canvas-stage").getBoundingClientRect(), state.camera.scale);
  const scale = clampCameraScale(Math.max(state.camera.scale, 0.82));
  moveCameraTo(cameraForWorldCenter(box.left + box.width / 2,
    box.top + box.height / 2, scale, getCameraViewport()));
  requestDraw();
  return true;
}
function focusGenerationInCanvas(generationId) {
  const lane = $('.generation-lane[data-generation-id="' + CSS.escape(String(generationId)) + '"]');
  if (!lane) return false;
  const box = stageBox(lane, $("#canvas-stage").getBoundingClientRect(), state.camera.scale);
  const viewport = getCameraViewport();
  const padding = isCompactWorkspace() ? 20 : 40;
  const scale = clampCameraScale(Math.max(0.75, Math.min(1, fitBoundsScale(box, viewport, padding))));
  const camera = cameraForWorldCenter(box.left + box.width / 2,
    box.top + box.height / 2, scale, viewport);
  if (box.width * scale > viewport.width - padding * 2) {
    camera.x = viewport.left + padding - viewport.baseX - box.left * scale;
  }
  if (box.height * scale > viewport.height - padding * 2) {
    camera.y = viewport.top + padding - viewport.baseY - box.top * scale;
  }
  moveCameraTo(camera);
  state.focusedGenerationId = generationId;
  renderWorkspaceChrome();
  requestDraw();
  return true;
}
function focusCurrentPerson() {
  if (state.focusedPersonId && focusPersonInCanvas(state.focusedPersonId)) {
    showToast("已聚焦人物：" + personName(state.focusedPersonId));
    return;
  }
  state.focusedPersonId = null;
  renderModeControls();
  showToast("请先点选或搜索一位人物，再聚焦");
}

function isCameraInteractiveTarget(target) {
  return Boolean(target.closest(
    ".person-node,.relationship-hit,.lane-header,.camera-controls,.selection-tray,.canvas-navigator," +
    "button,input,select,textarea,a,label,dialog,[role=button],[contenteditable]",
  ));
}
function isSpacePanControl(target) {
  const control = target.closest(
    ".camera-controls,.selection-tray,.canvas-navigator,button,input,select,textarea,a,label,dialog," +
    "[contenteditable],[role=button]",
  );
  return Boolean(control && !control.matches(".person-node,.relationship-hit"));
}
function startCameraPan(event, space = false) {
  if (state.drag || state.camera.pan || state.navigator.drag) return;
  const board = $("#generation-board");
  cameraMotion.stop();
  state.camera.pan = {
    pointerId: event.pointerId, space,
    startClientX: event.clientX, startClientY: event.clientY,
    startX: state.camera.x, startY: state.camera.y, moved: false,
  };
  board.setPointerCapture(event.pointerId);
}
function beginCameraPan(event) {
  if (event.button !== 0 || !event.isPrimary || isCameraInteractiveTarget(event.target)) return;
  startCameraPan(event);
}
function beginSpacePanCapture(event) {
  // Each new gesture replaces the previous click suppression.
  state.camera.suppressClick = null;
  if (!state.camera.spaceHeld || event.button !== 0 || !event.isPrimary ||
      state.drag || state.camera.pan || isSpacePanControl(event.target)) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  startCameraPan(event, true);
}
function moveCameraPan(event) {
  const pan = state.camera.pan;
  if (!pan || event.pointerId !== pan.pointerId) return;
  const dx = event.clientX - pan.startClientX;
  const dy = event.clientY - pan.startClientY;
  if (!pan.moved && Math.hypot(dx, dy) < 5) return;
  pan.moved = true;
  $("#generation-board").classList.add("is-panning");
  state.camera.x = pan.startX + dx;
  state.camera.y = pan.startY + dy;
  applyCamera();
}
function clearCameraPan(pointerId = null, release = true) {
  const pan = state.camera.pan;
  if (!pan || (pointerId !== null && pointerId !== pan.pointerId)) return;
  const board = $("#generation-board");
  state.camera.pan = null;
  if (pan.space || pan.moved) state.camera.suppressClick = pan.pointerId;
  board.classList.remove("is-panning");
  if (release && board.hasPointerCapture(pan.pointerId)) board.releasePointerCapture(pan.pointerId);
}
function endCameraPan(event) { clearCameraPan(event.pointerId); }
function cancelCameraPan(event) {
  if (state.camera.pan?.pointerId !== event.pointerId) return;
  clearSpacePan();
  clearCameraPan(event.pointerId);
}
function clearSpacePan() {
  state.camera.spaceHeld = false;
  $("#generation-board").classList.remove("is-space-panning");
  if (state.camera.pan?.space) clearCameraPan();
}
function handleSpaceKeydown(event) {
  if ((event.code !== "Space" && event.key !== " ") || event.altKey || event.ctrlKey || event.metaKey ||
      isSpacePanControl(event.target) || $("dialog:modal")) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  // A held key must not activate a focused card during an existing person drag.
  if (state.drag || state.camera.pan || state.navigator.drag) return;
  state.camera.spaceHeld = true;
  $("#generation-board").classList.add("is-space-panning");
}
function handleSpaceKeyup(event) {
  if (event.code !== "Space" && event.key !== " ") return;
  if (state.camera.spaceHeld) event.preventDefault();
  clearSpacePan();
}
function suppressCameraClick(event) {
  if (state.camera.suppressClick === null || event.detail === 0) return;
  const pointerId = state.camera.suppressClick;
  state.camera.suppressClick = null;
  if (event.pointerId !== undefined && event.pointerId !== pointerId) return;
  event.preventDefault();
  event.stopImmediatePropagation();
}
function handleCameraWheel(event) {
  if (state.drag || state.camera.pan || state.navigator.drag) return;
  if (event.target.closest(".camera-controls,.canvas-navigator,input,select,textarea,dialog")) return;
  const laneNodes = event.target.closest(".lane-nodes");
  if (laneNodes && (event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY))) return;
  event.preventDefault();
  const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 240 : 1);
  const multiplier = Math.exp(-Math.max(-160, Math.min(160, delta)) * 0.002);
  setCameraScale(state.camera.scale * multiplier, event.clientX, event.clientY);
}
function handleCameraResize() {
  syncWorkspaceSidebar();
  if (isCompactWorkspace()) clearNavigatorDrag();
  cameraMotion.stop();
  if (state.camera.resizeFrame !== null) return;
  const oldViewport = state.camera.viewport || getCameraViewport();
  const world = cameraViewportWorld(oldViewport);
  state.camera.resizeFrame = requestAnimationFrame(() => {
    state.camera.resizeFrame = null;
    const viewport = getCameraViewport();
    Object.assign(state.camera, cameraForWorldCenter(world.left + world.width / 2,
      world.top + world.height / 2, state.camera.scale, viewport));
    applyCamera();
    requestNavigatorUpdate(true);
    requestDraw();
  });
}

function requestNavigatorUpdate(geometry = false) {
  state.navigator.geometryDirty ||= geometry;
  if (state.navigator.frame !== null) return;
  state.navigator.frame = requestAnimationFrame(() => {
    state.navigator.frame = null;
    if (!$("#navigator-map") || isCompactWorkspace() || state.navigator.collapsed) return;
    if (state.navigator.geometryDirty) {
      updateNavigatorGeometry();
      state.navigator.geometryDirty = false;
    }
    updateNavigatorViewport();
  });
}
function updateNavigatorGeometry() {
  const edgeGroup = $("#navigator-edges");
  const peopleGroup = $("#navigator-people");
  edgeGroup.replaceChildren();
  peopleGroup.replaceChildren();
  const bounds = cameraContentBounds();
  const nodes = $$(".person-node");
  $("#navigator-empty").hidden = nodes.length > 0;
  $("#navigator-viewport").style.display = nodes.length ? "" : "none";
  state.navigator.map = null;
  if (!nodes.length || !bounds.width || !bounds.height) return;
  const scale = Math.min(184 / bounds.width, 104 / bounds.height);
  const map = { scale, x: (200 - bounds.width * scale) / 2, y: (120 - bounds.height * scale) / 2 };
  state.navigator.map = map;
  const stageRect = $("#canvas-stage").getBoundingClientRect();
  const points = new Map();
  for (const node of nodes) {
    const box = stageBox(node, stageRect, state.camera.scale);
    // Layout animations move the DOM temporarily; the navigator represents final layout.
    const transform = getComputedStyle(node).transform;
    const matrix = transform === "none" ? null : new DOMMatrixReadOnly(transform);
    const left = box.left - (matrix?.m41 || 0), top = box.top - (matrix?.m42 || 0);
    const x = map.x + (left + box.width / 2) * scale;
    const y = map.y + (top + box.height / 2) * scale;
    points.set(String(node.dataset.personId), { x, y });
    const marker = document.createElementNS(SVG_NS, "rect");
    marker.dataset.personId = node.dataset.personId;
    const width = Math.max(2, box.width * scale), height = Math.max(2, box.height * scale);
    marker.setAttribute("x", x - width / 2);
    marker.setAttribute("y", y - height / 2);
    marker.setAttribute("width", width);
    marker.setAttribute("height", height);
    marker.setAttribute("rx", Math.min(1.5, height / 4));
    peopleGroup.append(marker);
  }
  for (const relationship of relationships()) {
    const ends = relationshipEnds(relationship);
    const from = points.get(String(ends.sourceId)), to = points.get(String(ends.targetId));
    if (!from || !to) continue;
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", from.x); line.setAttribute("y1", from.y);
    line.setAttribute("x2", to.x); line.setAttribute("y2", to.y);
    edgeGroup.append(line);
  }
  updateNavigatorSelection();
}
function updateNavigatorSelection() {
  for (const marker of $$("#navigator-people rect")) {
    const id = marker.dataset.personId;
    marker.classList.toggle("is-selected", String(state.focusedPersonId) === id);
    marker.classList.toggle("is-selection-a", String(state.selectionA) === id);
    marker.classList.toggle("is-selection-b", String(state.selectionB) === id);
  }
}
function updateNavigatorViewport() {
  const map = state.navigator.map;
  if (!map) return;
  const world = cameraViewportWorld(getCameraViewport());
  const rect = $("#navigator-viewport");
  // Clamp the indicator at the SVG edges; panning outside the graph remains possible.
  const left = Math.max(0, Math.min(200, map.x + world.left * map.scale));
  const top = Math.max(0, Math.min(120, map.y + world.top * map.scale));
  const right = Math.max(0, Math.min(200, map.x + (world.left + world.width) * map.scale));
  const bottom = Math.max(0, Math.min(120, map.y + (world.top + world.height) * map.scale));
  rect.setAttribute("x", left); rect.setAttribute("y", top);
  rect.setAttribute("width", Math.max(0, right - left));
  rect.setAttribute("height", Math.max(0, bottom - top));
}
function navigatorPoint(event) {
  const rect = $("#navigator-map").getBoundingClientRect();
  return { x: (event.clientX - rect.left) * 200 / rect.width, y: (event.clientY - rect.top) * 120 / rect.height };
}
function beginNavigatorPointer(event) {
  if (event.button !== 0 || !event.isPrimary || !state.navigator.map ||
      state.drag || state.camera.pan || state.navigator.drag) return;
  event.preventDefault();
  event.stopPropagation();
  cameraMotion.stop();
  const svg = $("#navigator-map");
  svg.focus({ preventScroll: true });
  const point = navigatorPoint(event);
  if (event.target !== $("#navigator-viewport")) {
    const map = state.navigator.map;
    moveCameraTo(cameraForWorldCenter((point.x - map.x) / map.scale,
      (point.y - map.y) / map.scale, state.camera.scale, getCameraViewport()), true);
  }
  state.navigator.drag = { pointerId: event.pointerId, startPoint: point,
    startX: state.camera.x, startY: state.camera.y };
  svg.classList.add("is-dragging");
  svg.setPointerCapture(event.pointerId);
}
function moveNavigatorPointer(event) {
  const drag = state.navigator.drag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  event.preventDefault();
  const point = navigatorPoint(event);
  state.camera.x = drag.startX - (point.x - drag.startPoint.x) / state.navigator.map.scale * state.camera.scale;
  state.camera.y = drag.startY - (point.y - drag.startPoint.y) / state.navigator.map.scale * state.camera.scale;
  applyCamera();
}
function clearNavigatorDrag(pointerId = null, release = true) {
  const drag = state.navigator.drag;
  if (!drag || (pointerId !== null && pointerId !== drag.pointerId)) return;
  state.navigator.drag = null;
  const svg = $("#navigator-map");
  svg.classList.remove("is-dragging");
  if (release && svg.hasPointerCapture(drag.pointerId)) svg.releasePointerCapture(drag.pointerId);
}
function endNavigatorPointer(event) { clearNavigatorDrag(event.pointerId); }
function handleNavigatorKeydown(event) {
  const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  const direction = directions[event.key];
  if (!direction || !state.navigator.map || event.altKey || event.metaKey || event.ctrlKey) return;
  event.preventDefault();
  event.stopPropagation();
  cameraMotion.stop();
  const viewport = getCameraViewport();
  state.camera.x -= direction[0] * viewport.width * 0.1;
  state.camera.y -= direction[1] * viewport.height * 0.1;
  applyCamera();
}
function toggleNavigator() {
  state.navigator.collapsed = !state.navigator.collapsed;
  const expanded = !state.navigator.collapsed;
  $("#navigator-content").hidden = !expanded;
  $("#navigator-toggle").setAttribute("aria-expanded", String(expanded));
  $("#navigator-toggle").setAttribute("aria-label", expanded ? "收起缩略导航" : "展开缩略导航");
  $("#navigator-toggle-label").textContent = expanded ? "收起" : "展开";
  clearNavigatorDrag();
  handleCameraResize();
  requestNavigatorUpdate();
}

function renderBoard() {
  const rows = generations();
  const lanes = $("#generation-lanes");
  lanes.innerHTML = "";
  lanes.classList.toggle("is-linking", Boolean(state.linkMode && state.linkSource));
  $(".empty-state", $("#generation-board")).hidden = rows.length > 0 || state.workspaceLoadFailed || !state.workspaceLoaded;
  $("#load-error").hidden = !state.workspaceLoadFailed || rows.length > 0;
  $("#add-first-generation").hidden = isReadonlyDemo() || rows.length > 0;
  $("#add-generation-above").hidden = rows.length === 0;
  $("#add-generation-below").hidden = rows.length === 0;
  $("#perspective-mode").hidden = people().length === 0;
  $("#link-mode").hidden = isReadonlyDemo() || people().length === 0;
  $("#generation-menu-toggle").hidden = isReadonlyDemo() || rows.length === 0;
  rows.forEach((generation, generationIndex) => {
    const label = generation.name || "未命名代际";
    const lane = document.createElement("section");
    lane.className = "generation-lane";
    lane.dataset.generationId = generation.id;
    lane.setAttribute("aria-label", "第 " + (generationIndex + 1) + " 代：" + label);
    if (String(generation.id) === String(state.focusedGenerationId)) lane.classList.add("is-focused");
    const header = document.createElement("div");
    header.className = "lane-header";
    const ordinal = document.createElement("span");
    ordinal.className = "lane-ordinal";
    ordinal.setAttribute("aria-hidden", "true");
    ordinal.textContent = String(generationIndex + 1).padStart(2, "0");
    const name = document.createElement("button");
    name.type = "button";
    name.className = "lane-name";
    const nameText = document.createElement("span");
    nameText.textContent = label;
    name.append(nameText, createIcon("edit"));
    name.disabled = isReadonlyDemo();
    name.setAttribute("aria-label", (isReadonlyDemo() ? "代际：" : "重命名代际：") + label);
    name.addEventListener("click", () => openGenerationDialog("rename", generation.id));
    const lanePeople = peopleInGeneration(generation.id);
    const count = document.createElement("span");
    count.className = "lane-count";
    count.textContent = "第 " + (generationIndex + 1) + " 代 · " + lanePeople.length + " 人";
    const add = document.createElement("button");
    add.type = "button";
    add.className = "lane-add";
    add.disabled = isReadonlyDemo();
    add.append(createIcon("user-plus"), document.createTextNode("添加人物"));
    add.addEventListener("click", () => openPersonDialog(generation.id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "lane-remove";
    remove.disabled = isReadonlyDemo();
    remove.hidden = lanePeople.length > 0;
    remove.setAttribute("aria-label", "删除空代际：" + label);
    remove.dataset.tooltip = "删除这个空代际";
    remove.append(createIcon("trash"));
    remove.addEventListener("click", () => deleteGeneration(generation.id));
    const actions = document.createElement("div");
    actions.className = "lane-actions";
    actions.append(add, remove);
    header.append(ordinal, name, count, actions);
    const nodes = document.createElement("div");
    nodes.className = "lane-nodes";
    nodes.addEventListener("scroll", () => { requestDraw(); requestNavigatorUpdate(true); }, { passive: true });
    lanePeople.forEach((person) => nodes.append(createPersonNode(person)));
    if (!lanePeople.length) {
      const empty = document.createElement("button");
      empty.type = "button";
      empty.className = "lane-empty";
      empty.disabled = isReadonlyDemo();
      const hint = document.createElement("small");
      hint.textContent = "这一代还没有人物";
      empty.append(createIcon("user-plus"), document.createTextNode("添加人物"), hint);
      empty.addEventListener("click", () => openPersonDialog(generation.id));
      nodes.append(empty);
    }
    lane.append(header, nodes);
    lanes.append(lane);
  });
  requestNavigatorUpdate(true);
}
function createPersonNode(person) {
  const node = document.createElement("article");
  node.className = "person-node";
  node.dataset.personId = person.id;
  node.dataset.gender = person.gender || "unknown";
  node.tabIndex = 0;
  node.setAttribute("role", "button");
  const genderText = person.gender === "male" ? "男" : person.gender === "female" ? "女" : "性别未填写";
  node.setAttribute("aria-label", person.name + "，" + genderText);
  if (String(state.selectionA) === String(person.id)) {
    node.dataset.selection = "a";
    node.setAttribute("aria-label", node.getAttribute("aria-label") + "，A 选者");
  }
  if (String(state.selectionB) === String(person.id)) {
    node.dataset.selection = "b";
    node.setAttribute("aria-label", node.getAttribute("aria-label") + "，B 选者");
  }
  if (String(state.linkSource) === String(person.id)) node.classList.add("is-link-source");
  else if (state.linkMode && state.linkSource && canLinkPeople(state.linkSource, person.id)) node.classList.add("is-link-candidate");
  if (String(state.focusedPersonId) === String(person.id)) {
    node.dataset.focused = "true";
    node.setAttribute("aria-current", "true");
  }
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  if (person.photo_path || person.photo_url) {
    const image = document.createElement("img");
    image.src = person.photo_path || person.photo_url; image.alt = "";
    avatar.append(image);
  } else {
    avatar.textContent = Array.from(person.name || "?")[0];
  }
  const meta = document.createElement("div");
  meta.className = "node-meta";
  const title = document.createElement("strong");
  title.className = "person-name";
  title.title = person.name;
  title.textContent = person.name;
  const detail = document.createElement("span");
  detail.className = "person-gender";
  detail.setAttribute("aria-label", "性别：" + genderText);
  detail.textContent = genderText;
  const relationCount = relationships().filter((item) => {
    const ends = relationshipEnds(item);
    return [ends.sourceId, ends.targetId].some((id) => String(id) === String(person.id));
  }).length;
  const relationDetail = document.createElement("span");
  relationDetail.className = "node-relations";
  relationDetail.textContent = relationCount + " 条关系";
  relationDetail.setAttribute("aria-hidden", "true");
  meta.append(title, detail, relationDetail);
  const selection = node.dataset.selection;
  if (selection) {
    const status = document.createElement("span");
    status.className = "person-status";
    status.textContent = selection.toUpperCase() + " 选者";
    meta.append(status);
  }
  const openIcon = createIcon("open");
  openIcon.classList.add("node-open-icon");
  node.append(avatar, meta, openIcon);
  if ($("#person-dialog").open && String(state.editingPersonId) === String(person.id)) node.classList.add("is-inspected");
  node.addEventListener("pointerdown", beginPersonPointer);
  node.addEventListener("pointerenter", () => setActiveRelationshipPerson(person.id));
  node.addEventListener("pointerleave", () => {
    if (document.activeElement !== node) clearActiveRelationshipPerson(person.id);
  });
  node.addEventListener("focus", () => setActiveRelationshipPerson(person.id));
  node.addEventListener("blur", () => {
    if (!node.matches(":hover")) clearActiveRelationshipPerson(person.id);
  });
  node.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activatePerson(person.id);
    }
  });
  return node;
}
function openGenerationDialog(intent, generationId = null) {
  if (preventDemoEdit()) return;
  if (state.historyBusy || state.mutations) return;
  const generation = generationId ? generations().find((item) => String(item.id) === String(generationId)) : null;
  state.generationIntent = { intent, generationId };
  $("#generation-dialog-title").textContent = intent === "rename" ? "重命名代际" :
    intent === "first" ? "建立第一代" :
    intent === "above" ? "增加上一代" : "增加下一代";
  $("#generation-submit").textContent = intent === "rename" ? "保存名称" : "创建代际";
  $("#generation-name").value = generation?.name || "";
  const usedNames = new Set(generations().map((row) => row.name));
  $$("[data-generation-name]").forEach((button) => {
    const used = usedNames.has(button.dataset.generationName) && button.dataset.generationName !== generation?.name;
    button.classList.toggle("is-used", used);
    button.setAttribute("aria-pressed", String(button.dataset.generationName === generation?.name));
  });
  $("#generation-dialog").showModal();
  $("#generation-name").focus();
  $("#generation-name").select();
}

function closeGenerationDialog() {
  $("#generation-dialog").close();
  state.generationIntent = null;
  $("#generation-form").reset();
}

async function saveGeneration(event) {
  if (preventDemoEdit(event)) return;
  event.preventDefault();
  const current = state.generationIntent;
  if (!current) return;
  const name = $("#generation-name").value.trim();
  try {
    let data;
    if (current.intent === "rename") {
      data = await api("/api/generations/" + encodeURIComponent(current.generationId), {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
    } else {
      const rows = generations();
      const anchorId = current.intent === "above" ? rows[0]?.id :
        current.intent === "below" ? rows.at(-1)?.id : undefined;
      const body = { placement: current.intent };
      if (anchorId) body.anchor_id = anchorId;
      if (name) body.name = name;
      data = await api("/api/generations", { method: "POST", body: JSON.stringify(body) });
    }
    state.workspace = workspaceFrom(data);
    closeGenerationDialog();
    render();
    if (current.intent === "rename") {
      showToast("代际名称已更新", "success");
    } else {
      const created = data.generation?.id;
      showToast("已添加代际「" + (data.generation?.name || name || "新代际") + "」", "success");
      if (created) requestAnimationFrame(() => focusGenerationInCanvas(created));
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteGeneration(id) {
  if (preventDemoEdit()) return;
  if (people().some((person) => String(person.generation_id) === String(id))) {
    showToast("只能删除没有人物的代际", "error"); return;
  }
  const generation = generations().find((row) => String(row.id) === String(id));
  if (!await askConfirmation("代际「" + (generation?.name || "未命名代际") + "」中没有人物，删除后可以撤销。", {
    title: "删除这个空代际？", confirmLabel: "删除代际", tone: "danger",
  })) return;
  try {
    state.workspace = workspaceFrom(await api("/api/generations/" + encodeURIComponent(id), { method: "DELETE" }));
    render();
    showToast("代际已删除", "success", undoAction());
  } catch (error) { showToast(error.message, "error"); }
}
const personEditor = { baseline: "", photoUrl: null, removePhoto: false, saving: false, motion: null, initialFocus: null };

function personGenderValue() {
  return $('#person-gender input[name="person-gender"]:checked')?.value || "";
}
function setPersonGenderValue(value) {
  $$('#person-gender input[name="person-gender"]').forEach((input) => { input.checked = input.value === value; });
}
function personFormValue() {
  return JSON.stringify({
    name: $("#person-name").value, gender: personGenderValue(),
    generation: $("#person-generation").value, introduction: $("#person-introduction").value,
    photo: $("#person-photo").files?.[0]?.name || "", removePhoto: personEditor.removePhoto,
  });
}
function personHasChanges() {
  if (isReadonlyDemo()) return false;
  return $("#person-dialog").open && personFormValue() !== personEditor.baseline;
}
function setPersonStatus(message, kind = "") {
  const output = $("#person-save-status");
  output.textContent = message;
  output.dataset.kind = kind;
}
function refreshPersonGenerationOptions() {
  if (!$("#person-dialog").open) return;
  const select = $("#person-generation");
  const selected = select.value;
  const rows = generations();
  select.replaceChildren();
  const stillExists = rows.some((generation) => String(generation.id) === selected);
  if (!stillExists) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "请选择代际";
    placeholder.disabled = true;
    select.append(placeholder);
  }
  rows.forEach((generation) => {
    const option = document.createElement("option");
    option.value = generation.id;
    option.textContent = generation.name || "未命名层级";
    select.append(option);
  });
  select.value = stillExists ? selected : "";
  updatePersonPreview();
  renderPersonRelatives();
  if (selected && !stillExists) setPersonStatus("所属代际已被删除，请重新选择", "error");
}
function personGenerationName(id) {
  return generations().find((item) => String(item.id) === String(id))?.name || "未选择代际";
}
function renderProfileAvatar(target, person, photoPath = person?.photo_path || person?.photo_url) {
  target.replaceChildren();
  target.dataset.gender = person?.gender || "";
  if (photoPath) {
    const image = document.createElement("img");
    image.src = photoPath;
    image.alt = "";
    target.append(image);
  } else {
    target.textContent = Array.from(person?.name || "新")[0];
  }
}
function updatePersonPreview() {
  const person = personById(state.editingPersonId);
  const name = $("#person-name").value.trim();
  const draft = { name, gender: personGenderValue() };
  const photoPath = personEditor.photoUrl || (personEditor.removePhoto ? null : person?.photo_path || person?.photo_url);
  renderProfileAvatar($("#person-photo-preview"), draft, photoPath);
  $("#person-photo-label").textContent = photoPath ? "更换照片" : "添加照片";
  $("#person-photo-remove").hidden = !photoPath;
  $("#person-dialog-title").textContent = name || (person ? "未填写姓名" : "添加人物");
  const relationCount = person ? relationships().filter((item) => {
    const ends = relationshipEnds(item);
    return [ends.sourceId, ends.targetId].some((id) => String(id) === String(person.id));
  }).length : 0;
  const genderText = draft.gender === "male" ? "男" : draft.gender === "female" ? "女" : "";
  $("#person-profile-context").textContent = [personGenerationName($("#person-generation").value), genderText,
    person ? relationCount + " 条关系" : "新人物"].filter(Boolean).join(" · ");
  const warning = $("#person-generation-warning");
  const rows = generations();
  const destination = rows.findIndex((g) => String(g.id) === $("#person-generation").value);
  const affected = person ? relationships().filter((item) => {
    const { sourceId, targetId } = relationshipEnds(item);
    if (![sourceId, targetId].some((id) => String(id) === String(person.id))) return false;
    const otherId = String(sourceId) === String(person.id) ? targetId : sourceId;
    const other = personById(otherId);
    const otherIndex = rows.findIndex((g) => String(g.id) === String(other?.generation_id));
    return Math.abs(destination - otherIndex) !== 1;
  }).length : 0;
  warning.hidden = !affected;
  warning.textContent = affected ? "保存后，将取消 " + affected + " 条不再相邻的关系。" : "";
}
function personInputChanged(event) {
  if (preventDemoEdit(event)) return;
  // The relative picker acts immediately and is not part of the person draft.
  if (event?.target?.id === "person-relative-add") return;
  updatePersonPreview();
  renderWorkspaceSaveState();
  if (!personEditor.saving) setPersonStatus(personHasChanges() ? "有未保存的修改" : (state.editingPersonId ? "已保存" : "填写资料后保存"), personHasChanges() ? "changed" : "");
}
function releasePersonPhotoPreview() {
  if (personEditor.photoUrl) URL.revokeObjectURL(personEditor.photoUrl);
  personEditor.photoUrl = null;
}
function animatePersonInspector(entering) {
  const card = $("#person-form");
  const wasAnimating = personEditor.motion && personEditor.motion.playState === "running";
  const current = wasAnimating ? { transform: getComputedStyle(card).transform, opacity: getComputedStyle(card).opacity } : null;
  personEditor.motion?.cancel();
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const offset = matchMedia("(max-width: 719px)").matches ? "translateY(22px)" : "translateX(22px)";
  const hidden = { transform: reduced ? "none" : offset, opacity: 0 };
  const shown = { transform: "none", opacity: 1 };
  const motion = card.animate([current || (entering ? hidden : shown), entering ? shown : hidden],
    { duration: reduced ? 80 : entering ? 220 : 160, easing: "cubic-bezier(.2,.8,.2,1)", fill: "both" });
  personEditor.motion = motion;
  return motion;
}
async function openPersonDialog(generationId, personId = null) {
  if (isReadonlyDemo() && !personById(personId)) return;
  if (state.historyBusy || state.mutations) return;
  if (personEditor.saving) return;
  if ($("#person-dialog").open && String(state.editingPersonId) === String(personId) &&
      String(state.editingGenerationId) === String(generationId)) return;
  if (personHasChanges() && !await askConfirmation("当前档案有未保存的修改。放弃这些修改，并打开另一份档案？", {
    title: "放弃未保存的修改？", confirmLabel: "放弃修改",
  })) return;
  const wasOpen = $("#person-dialog").open;
  personEditor.motion?.cancel();
  personEditor.motion = null;
  releasePersonPhotoPreview();
  personEditor.removePhoto = false;
  personEditor.initialFocus = document.activeElement;
  state.editingGenerationId = generationId;
  state.editingPersonId = personId;
  const person = personId ? personById(personId) : null;
  $("#person-name").value = person?.name || "";
  setPersonGenderValue(person?.gender || "");
  $("#person-introduction").value = person?.introduction || "";
  const generationSelect = $("#person-generation");
  generationSelect.replaceChildren();
  generations().forEach((generation) => {
    const option = document.createElement("option");
    option.value = generation.id;
    option.textContent = generation.name || "未命名层级";
    generationSelect.append(option);
  });
  generationSelect.value = person?.generation_id || generationId || "";
  $("#person-photo").value = "";
  $("#person-delete").hidden = !person;
  $("#person-save").textContent = person ? "保存修改" : "创建人物";
  personEditor.baseline = personFormValue();
  updatePersonPreview();
  renderPersonRelatives();
  setPersonStatus(isReadonlyDemo() ? "公开只读演示 · 下载完整版后可编辑" : person ? "已保存" : "填写资料后保存");
  $(".inspector-content").scrollTop = 0;
  if (!wasOpen) {
    $("#person-dialog").show();
    document.body.classList.add("has-person-inspector");
    animatePersonInspector(true);
    handleCameraResize();
  }
  $$(".person-node").forEach((node) => node.classList.toggle("is-inspected", String(node.dataset.personId) === String(personId)));
  $("#person-name").focus({ preventScroll: true });
  renderWorkspaceSaveState();
}
async function closePersonDialog(force = false) {
  const dialog = $("#person-dialog");
  if (!dialog.open) return true;
  if (personEditor.saving && !force) return false;
  if (!force && personHasChanges() && !await askConfirmation("关闭后，这份档案里未保存的修改将会丢失。", {
    title: "放弃未保存的修改？", confirmLabel: "放弃并关闭",
  })) return false;
  const motion = animatePersonInspector(false);
  await motion.finished.catch(() => {});
  if (personEditor.motion !== motion) return false;
  motion.cancel();
  personEditor.motion = null;
  dialog.close();
  document.body.classList.remove("has-person-inspector");
  handleCameraResize();
  releasePersonPhotoPreview();
  personEditor.removePhoto = false;
  const personId = state.editingPersonId;
  state.editingGenerationId = null;
  state.editingPersonId = null;
  $("#person-form").reset();
  renderWorkspaceSaveState();
  $$(".person-node.is-inspected").forEach((node) => node.classList.remove("is-inspected"));
  const source = personId ? $('.person-node[data-person-id="' + CSS.escape(String(personId)) + '"]') : personEditor.initialFocus;
  if (source?.isConnected) source.focus({ preventScroll: true });
  return true;
}
function setPersonSaving(saving) {
  personEditor.saving = saving;
  $("#person-form").setAttribute("aria-busy", String(saving));
  $$("input, select, textarea, button", $("#person-form")).forEach((control) => control.disabled = saving);
  $(".photo-picker").setAttribute("aria-disabled", String(saving));
  $("#person-save").textContent = saving ? "保存中…" : state.editingPersonId ? "保存修改" : "创建人物";
}
async function savePerson(event) {
  if (preventDemoEdit(event)) return;
  event.preventDefault();
  if (personEditor.saving) return;
  const payload = {
    generation_id: $("#person-generation").value,
    name: $("#person-name").value.trim(),
    gender: personGenderValue(),
    introduction: $("#person-introduction").value.trim() || null,
  };
  if (!payload.generation_id || !payload.name || !payload.gender) {
    setPersonStatus("请填写姓名、性别和所属代际", "error");
    return;
  }
  if (personEditor.removePhoto) payload.photo_path = null;
  let savedId = state.editingPersonId;
  const photo = $("#person-photo").files?.[0];
  setPersonSaving(true);
  setPersonStatus("正在保存…");
  let savedPerson = false;
  try {
    const previousIds = new Set(people().map((person) => String(person.id)));
    const data = savedId
      ? await api("/api/people/" + encodeURIComponent(savedId), { method: "PATCH", body: JSON.stringify(payload) })
      : await api("/api/people", { method: "POST", body: JSON.stringify(payload) });
    state.workspace = workspaceFrom(data);
    savedId = savedId || data.person?.id || data.id || people().find((person) => !previousIds.has(String(person.id)))?.id;
    if (!savedId) throw new Error("人物已保存，请重新打开档案确认");
    savedPerson = true;
    // Keep the created ID for a photo-upload retry; a retry must never create a second person.
    state.editingPersonId = savedId;
    state.editingGenerationId = payload.generation_id;
    if (photo) {
      state.workspace = workspaceFrom(await api("/api/photos", {
        method: "POST",
        body: JSON.stringify({ person_id: savedId, filename: photo.name, data_url: await readFileAsDataUrl(photo) }),
      }));
    }
    $("#person-photo").value = "";
    personEditor.removePhoto = false;
    releasePersonPhotoPreview();
    personEditor.baseline = personFormValue();
    const created = !previousIds.has(String(savedId));
    render();
    updatePersonPreview();
    renderPersonRelatives();
    $("#person-delete").hidden = false;
    $("#person-save").textContent = "保存修改";
    $('.person-node[data-person-id="' + CSS.escape(String(savedId)) + '"]')?.classList.add("is-inspected");
    setPersonStatus("已保存", "success");
    showToast(data.removed_relationship_ids?.length
      ? "人物已保存，已取消 " + data.removed_relationship_ids.length + " 条不再相邻的关系"
      : created ? "已添加「" + payload.name + "」" : "人物资料已保存", "success");
    if (created) requestAnimationFrame(() => focusPersonInCanvas(savedId));
  } catch (error) {
    setPersonStatus((savedPerson ? "资料已保存，照片处理失败：" : "保存失败：") + error.message + "，请重试。", "error");
    if (savedPerson) { render(); updatePersonPreview(); }
  } finally {
    setPersonSaving(false);
  }
}

async function deletePerson() {
  if (preventDemoEdit()) return;
  if (personEditor.saving || !state.editingPersonId) return;
  const personId = state.editingPersonId;
  const name = personName(personId);
  const linked = relationships().filter((item) => {
    const ends = relationshipEnds(item);
    return [ends.sourceId, ends.targetId].some((id) => String(id) === String(personId));
  }).length;
  if (!await askConfirmation(linked
    ? "「" + name + "」的档案和 " + linked + " 条关系会一起删除，删除后可以撤销。"
    : "「" + name + "」的档案会被删除，删除后可以撤销。", {
    title: "删除这位人物？", confirmLabel: "删除人物", tone: "danger",
  })) return;
  try {
    setPersonSaving(true);
    state.workspace = workspaceFrom(await api("/api/people/" + encodeURIComponent(personId), { method: "DELETE" }));
    await closePersonDialog(true);
    render();
    showToast("已删除「" + name + "」", "success", undoAction());
  } catch (error) { setPersonStatus("删除失败：" + error.message, "error"); }
  finally { setPersonSaving(false); }
}
function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
// Parents and children of one person, labelled from that person's point of view.
function personRelatives(personId) {
  return relationships().flatMap((relationship) => {
    const { sourceId, targetId } = relationshipEnds(relationship);
    const otherIsParent = String(targetId) === String(personId);
    if (!otherIsParent && String(sourceId) !== String(personId)) return [];
    const other = personById(otherIsParent ? sourceId : targetId);
    if (!other) return [];
    const fallback = otherIsParent ? (other.gender === "male" ? "父亲" : "母亲") : (other.gender === "male" ? "儿子" : "女儿");
    return [{
      relationship, person: other, side: otherIsParent ? "parent" : "child",
      role: (otherIsParent ? relationship.parent_label : relationship.child_label) || fallback,
      kind: relationshipKindKey(relationship, sourceId, targetId),
    }];
  });
}
function createRelativeItem(item) {
  const row = document.createElement("div");
  row.className = "relative-item";
  const open = document.createElement("button");
  open.type = "button";
  open.className = "relative-person";
  open.dataset.relativeId = item.person.id;
  open.setAttribute("aria-label", "查看" + item.role + "「" + item.person.name + "」的档案");
  const avatar = document.createElement("span");
  avatar.className = "relative-avatar";
  renderProfileAvatar(avatar, item.person);
  const copy = document.createElement("span");
  copy.className = "relative-copy";
  const name = document.createElement("strong");
  name.textContent = item.person.name;
  const detail = document.createElement("small");
  detail.textContent = personGenerationName(item.person.generation_id);
  copy.append(name, detail);
  const role = document.createElement("span");
  role.className = "relative-role";
  role.dataset.kind = item.kind;
  role.textContent = item.role;
  open.append(avatar, copy, role);
  const edit = document.createElement("button");
  edit.type = "button";
  edit.className = "icon-button relative-edit";
  edit.disabled = isReadonlyDemo();
  edit.hidden = isReadonlyDemo();
  edit.dataset.relationshipId = item.relationship.id;
  edit.dataset.tooltip = "编辑关系";
  edit.dataset.tooltipAlign = "end";
  edit.setAttribute("aria-label", "编辑与「" + item.person.name + "」的关系");
  edit.append(createIcon("link"));
  row.append(open, edit);
  return row;
}
function renderPersonRelatives() {
  const list = $("#person-relatives");
  const field = $("#person-relative-field");
  const select = $("#person-relative-add");
  const person = personById(state.editingPersonId);
  list.replaceChildren();
  select.replaceChildren();
  const note = (text) => {
    const paragraph = document.createElement("p");
    paragraph.className = "relatives-empty";
    paragraph.textContent = text;
    list.append(paragraph);
  };
  if (!person) {
    $("#person-relatives-count").textContent = "";
    note("保存人物后，可以在这里添加父母或子女。");
    field.hidden = true;
    return;
  }
  const relatives = personRelatives(person.id);
  $("#person-relatives-count").textContent = relatives.length ? relatives.length + " 位" : "";
  [["parent", "父母"], ["child", "子女"]].forEach(([side, title]) => {
    const items = relatives.filter((item) => item.side === side)
      .sort((a, b) => (Number(a.person.order) || 0) - (Number(b.person.order) || 0));
    if (!items.length) return;
    const group = document.createElement("div");
    group.className = "relatives-group";
    const heading = document.createElement("p");
    heading.className = "relatives-group-title";
    heading.textContent = title;
    group.append(heading, ...items.map(createRelativeItem));
    list.append(group);
  });
  if (!relatives.length) note("还没有记录父母或子女。");
  if (isReadonlyDemo()) {
    field.hidden = true;
    return;
  }
  const rows = generations();
  const index = rows.findIndex((row) => String(row.id) === String(person.generation_id));
  const related = new Set(relatives.map((item) => String(item.person.id)));
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = "添加父母或子女…";
  select.append(placeholder);
  let candidates = 0;
  [[index - 1, "父母"], [index + 1, "子女"]].forEach(([rowIndex, role]) => {
    const row = index < 0 ? null : rows[rowIndex];
    if (!row) return;
    const options = peopleInGeneration(row.id).filter((other) => other.gender && !related.has(String(other.id)));
    if (!options.length) return;
    const group = document.createElement("optgroup");
    group.label = (row.name || "未命名代际") + " · 设为" + role;
    options.forEach((other) => {
      const option = document.createElement("option");
      option.value = other.id;
      option.textContent = other.name + "（" + (other.gender === "male" ? "男" : "女") + "）";
      group.append(option);
    });
    select.append(group);
    candidates += options.length;
  });
  field.hidden = !candidates || !person.gender;
  select.disabled = false;
  $("#person-relative-confirm").disabled = true;
}
async function openRelativeProfile(personId) {
  const other = personById(personId);
  if (!other) return;
  await openPersonDialog(other.generation_id, other.id);
  if (String(state.editingPersonId) !== String(other.id)) return;
  state.focusedPersonId = other.id;
  render();
  requestAnimationFrame(() => focusPersonInCanvas(other.id));
}
async function editRelativeRelationship(relationshipId) {
  const returnTo = state.editingPersonId;
  await openRelationshipDialog(relationshipId);
  if (!$("#relationship-dialog").open) return;
  $("#relationship-dialog").addEventListener("close", () => {
    const person = personById(returnTo);
    if (person && !$("#person-dialog").open) openPersonDialog(person.generation_id, person.id);
  }, { once: true });
}
async function addRelativeFromInspector() {
  if (preventDemoEdit()) return;
  const select = $("#person-relative-add");
  const otherId = select.value;
  if (!otherId || !state.editingPersonId) return;
  select.disabled = true;
  $("#person-relative-confirm").disabled = true;
  await createDraggedRelationship(state.editingPersonId, otherId);
  renderPersonRelatives();
}
function acceptDroppedPhoto(event) {
  if (preventDemoEdit(event)) return;
  const files = [...(event.dataTransfer?.files || [])];
  $(".photo-picker").classList.remove("is-drop-target");
  if (!files.length) return;
  event.preventDefault();
  const file = files.find((item) => item.type.startsWith("image/"));
  if (personEditor.saving) return;
  if (!file) { setPersonStatus("请拖入 JPG、PNG、GIF 或 WebP 图片", "error"); return; }
  const transfer = new DataTransfer();
  transfer.items.add(file);
  $("#person-photo").files = transfer.files;
  $("#person-photo").dispatchEvent(new Event("change"));
}
function activatePerson(personId) {
  if (state.historyBusy || state.mutations) return;
  state.focusedPersonId = personId;
  updateNavigatorSelection();
  if (state.perspective) {
    selectPerspectivePerson(personId);
  } else if (state.linkMode) {
    selectLinkPerson(personId);
  } else {
    const person = personById(personId);
    openPersonDialog(person.generation_id, personId);
  }
}

async function selectLinkPerson(personId) {
  if (preventDemoEdit()) return;
  if (!state.linkSource) {
    state.linkSource = personId;
    showToast("已选择起点「" + personName(personId) + "」，请点选相邻代的人物");
    render();
    return;
  }
  if (String(state.linkSource) === String(personId)) {
    showToast("连线终点不能与起点相同", "error");
    return;
  }
  const source = state.linkSource;
  state.linkSource = null;
  await createDraggedRelationship(source, personId);
  render();
}

function exitLinkMode(shouldRender = true) {
  cancelActivePersonDrag();
  state.linkMode = false;
  state.linkSource = null;
  $("#link-mode").setAttribute("aria-pressed", "false");
  if (shouldRender) render();
}

async function enterSelectMode() {
  if ($("#person-dialog").open && !await closePersonDialog()) return;
  cancelActivePersonDrag();
  invalidateRelationshipTasks();
  state.perspective = false;
  state.selectionA = null;
  state.selectionB = null;
  state.selectionTarget = "a";
  state.linkMode = false;
  state.linkSource = null;
  hideToast();
  render();
}

function renderModeControls() {
  const selecting = !state.linkMode && !state.perspective;
  $("#select-mode").setAttribute("aria-pressed", String(selecting));
  $("#link-mode").setAttribute("aria-pressed", String(state.linkMode));
  $("#perspective-mode").setAttribute("aria-pressed", String(state.perspective));
  document.body.dataset.mode = state.perspective ? "relationship" : state.linkMode ? "link" : "select";
  $(".canvas-hint").textContent = state.perspective
    ? "点选人物填入 A / B · 按住空格拖动画布 · Esc 退出关系"
    : state.linkMode
      ? (state.linkSource ? "已选起点「" + personName(state.linkSource) + "」· 点选相邻代的人物完成连线 · Esc 取消"
        : "连线模式 · 依次点选两人或拖出连线 · Esc 退出")
      : isReadonlyDemo() ? "公开只读演示 · 点选查看资料 · 按住空格平移"
        : "点选查看资料 · 拖动人物排序或换代 · 按住空格平移";
  $("#camera-focus").setAttribute("aria-disabled", String(!state.focusedPersonId));
}

function closeGenerationMenu(restoreFocus = false) {
  const wasOpen = !$("#generation-menu").hidden;
  $("#generation-menu").hidden = true;
  $("#generation-menu-toggle").setAttribute("aria-expanded", "false");
  if (restoreFocus && wasOpen) $("#generation-menu-toggle").focus();
}

function toggleGenerationMenu(event) {
  if (preventDemoEdit(event)) return;
  event.stopPropagation();
  closeWorkspaceHelp();
  const menu = $("#generation-menu");
  const shouldOpen = menu.hidden;
  menu.hidden = !shouldOpen;
  $("#generation-menu-toggle").setAttribute("aria-expanded", String(shouldOpen));
  if (shouldOpen) {
    requestAnimationFrame(() => $("#generation-menu button:not([hidden])")?.focus());
  }
}

function closeSearchResults() {
  const results = $("#search-results");
  results.hidden = true;
  const input = $("#person-search-input");
  input.setAttribute("aria-expanded", "false");
  input.setAttribute("aria-activedescendant", "");
  state.searchActiveIndex = -1;
}

function selectSearchResult(personId) {
  state.focusedPersonId = personId;
  $("#person-search-input").value = personName(personId);
  state.searchQuery = personName(personId);
  state.searchActiveIndex = -1;
  closeSearchResults();
  renderBoard();
  requestAnimationFrame(() => focusPersonInCanvas(personId));
}

function renderSearchResults() {
  const input = $("#person-search-input");
  const results = $("#search-results");
  const query = input.value.trim();
  state.searchQuery = query;
  results.innerHTML = "";
  if (!query || document.activeElement !== input) {
    closeSearchResults();
    return;
  }
  const matches = people().filter((person) => person.name?.includes(query)).slice(0, 8);
  if (!matches.length) {
    const empty = document.createElement("div");
    empty.className = "search-empty";
    const title = document.createElement("strong");
    title.textContent = "没有找到「" + query + "」";
    const hint = document.createElement("small");
    hint.textContent = "可以只输入名字中的一个字";
    empty.append(createIcon("search"), title, hint);
    results.append(empty);
  } else {
    state.searchActiveIndex = Math.min(state.searchActiveIndex, matches.length - 1);
    matches.forEach((person, index) => {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "search-result";
      option.setAttribute("role", "option");
      option.id = "search-result-" + String(person.id).replace(/[^a-zA-Z0-9_-]/g, "-");
      option.setAttribute("aria-selected", String(index === state.searchActiveIndex));
      const avatar = document.createElement("span");
      avatar.className = "search-result-avatar";
      renderProfileAvatar(avatar, person);
      const copy = document.createElement("span");
      copy.className = "search-result-copy";
      const title = document.createElement("strong");
      const at = person.name.indexOf(query);
      const mark = document.createElement("mark");
      mark.textContent = person.name.slice(at, at + query.length);
      title.append(person.name.slice(0, at), mark, person.name.slice(at + query.length));
      const generation = generations().find((item) => String(item.id) === String(person.generation_id));
      const detail = document.createElement("small");
      detail.textContent = (generation?.name || "未命名代际") + " · " +
        (person.gender === "male" ? "男" : person.gender === "female" ? "女" : "未填写性别");
      copy.append(title, detail);
      option.append(avatar, copy, createIcon("arrow-up-right"));
      option.addEventListener("click", () => selectSearchResult(person.id));
      results.append(option);
    });
    const footer = document.createElement("div");
    footer.className = "search-footer";
    footer.setAttribute("aria-hidden", "true");
    footer.textContent = "↑↓ 选择 · ↵ 定位 · Esc 关闭";
    results.append(footer);
  }
  results.hidden = false;
  input.setAttribute("aria-expanded", "true");
  const active = matches[state.searchActiveIndex];
  input.setAttribute("aria-activedescendant", active
    ? "search-result-" + String(active.id).replace(/[^a-zA-Z0-9_-]/g, "-")
    : "");
}

function handleSearchKeydown(event) {
  const input = event.currentTarget;
  const query = input.value.trim();
  const matches = people().filter((person) => person.name?.includes(query)).slice(0, 8);
  if (event.key === "ArrowDown" && matches.length) {
    event.preventDefault();
    state.searchActiveIndex = (state.searchActiveIndex + 1 + matches.length) % matches.length;
    renderSearchResults();
  } else if (event.key === "ArrowUp" && matches.length) {
    event.preventDefault();
    state.searchActiveIndex = state.searchActiveIndex <= 0
      ? matches.length - 1
      : state.searchActiveIndex - 1;
    renderSearchResults();
  } else if (event.key === "Enter" && state.searchActiveIndex >= 0 && matches[state.searchActiveIndex]) {
    event.preventDefault();
    selectSearchResult(matches[state.searchActiveIndex].id);
  } else if (event.key === "Escape") {
    event.preventDefault();
    closeSearchResults();
  }
}

function invalidateCopyRequest() {
  state.copyRequestId += 1;
  state.copyInFlight = false;
  state.relationshipCopyError = null;
}

function isCopyRequestCurrent(token, a, b) {
  return token === state.copyRequestId &&
    state.copyInFlight &&
    state.perspective &&
    String(state.selectionA) === String(a) &&
    String(state.selectionB) === String(b);
}

function invalidatePathRequest() {
  state.pathRequestId += 1;
  state.relationshipPathLoading = false;
  state.relationshipCopyText = null;
  state.relationshipPathError = null;
  state.relationshipPath = null;
}

function invalidateRelationshipTasks() {
  invalidateCopyRequest();
  invalidatePathRequest();
}

function isPathRequestCurrent(token, a, b) {
  return token === state.pathRequestId &&
    state.relationshipPathLoading &&
    state.perspective &&
    String(state.selectionA) === String(a) &&
    String(state.selectionB) === String(b);
}

async function toggleLinkMode() {
  if (preventDemoEdit()) return;
  if ($("#person-dialog").open && !await closePersonDialog()) return;
  cancelActivePersonDrag();
  if (state.linkMode) {
    exitLinkMode();
    showToast("已退出连线模式");
    return;
  }
  invalidateRelationshipTasks();
  state.perspective = false;
  state.selectionA = null;
  state.selectionB = null;
  state.selectionTarget = "a";
  $("#perspective-mode").setAttribute("aria-pressed", "false");
  state.linkMode = true;
  state.linkSource = null;
  $("#link-mode").setAttribute("aria-pressed", "true");
  showToast("连线模式：先点选一位人物作为起点");
  render();
}
function beginPersonPointer(event) {
  if (event.button !== 0 || !event.isPrimary || state.mutations || state.historyBusy) return;
  cameraMotion.stop();
  const node = event.currentTarget;
  const rect = node.getBoundingClientRect();
  const existingTransform = getComputedStyle(node).transform;
  const matrix = existingTransform === "none" ? null : new DOMMatrixReadOnly(existingTransform);
  const initialX = matrix?.m41 || 0, initialY = matrix?.m42 || 0;
  nodeMotions.get(node.dataset.personId)?.stop();
  nodeMotions.delete(node.dataset.personId);
  node.classList.remove("is-settling");
  node.setPointerCapture(event.pointerId);
  node.classList.add("is-pressed");
  state.drag = {
    pointerId: event.pointerId, node, personId: node.dataset.personId,
    startX: event.clientX, startY: event.clientY, initialX, initialY,
    samples: [{ x: event.clientX, y: event.clientY, time: event.timeStamp }],
    offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top,
    dragging: false, selectOnly: isReadonlyDemo() || state.perspective || ($("#person-dialog").open && String(state.editingPersonId) === node.dataset.personId),
    inspectorLocked: $("#person-dialog").open && String(state.editingPersonId) === node.dataset.personId,
    relationship: !isReadonlyDemo() && !state.perspective && (state.linkMode || event.shiftKey),
    targetLane: null, targetNode: null, reorderIndex: null, reorderGenerationId: null,
  };
  node.addEventListener("pointermove", movePersonPointer);
  node.addEventListener("pointerup", endPersonPointer);
  node.addEventListener("pointercancel", cancelPersonPointer);
  node.addEventListener("lostpointercapture", lostPersonPointerCapture);
}
function movePersonPointer(event) {
  const drag = state.drag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  const dx = event.clientX - drag.startX, dy = event.clientY - drag.startY;
  if (!drag.dragging && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
  if (drag.selectOnly) {
    if (!isReadonlyDemo() && !drag.dragging && drag.inspectorLocked) showToast("请在档案中修改所属代际，或关闭档案后拖动");
    drag.dragging = true;
    drag.node.classList.remove("is-pressed");
    return;
  }
  if (!drag.dragging) {
    drag.dragging = true;
    drag.node.classList.add("is-dragging");
    if (drag.relationship) markLinkCandidates(drag.personId);
    else drag.node.style.opacity = "0.82";
  }
  if (!drag.relationship) {
    drag.node.style.transform = "translate3d(" + (drag.initialX + dx / state.camera.scale) + "px," +
      (drag.initialY + dy / state.camera.scale) + "px,0)";
    drag.samples.push({ x: event.clientX, y: event.clientY, time: event.timeStamp });
    drag.samples = drag.samples.filter((sample) => event.timeStamp - sample.time <= 90);
    requestDraw();
  }
  clearDropTargets();
  const underPointer = document.elementsFromPoint(event.clientX, event.clientY);
  if (drag.relationship) {
    drag.targetNode = underPointer.find((element) =>
      element.classList?.contains("person-node") && element !== drag.node
    ) || null;
    drag.targetNode?.classList.add("is-link-target");
    updateLinkPreview(drag, event);
  } else {
    drag.targetLane = underPointer.find((element) => {
      if (!element.classList?.contains("generation-lane")) return false;
      const rect = element.getBoundingClientRect();
      return event.clientX >= rect.left && event.clientX <= rect.right &&
        event.clientY >= rect.top && event.clientY <= rect.bottom;
    }) || null;
    drag.targetLane?.classList.add("is-drop-target");
    if (drag.targetLane) updateReorderPreview(drag, drag.targetLane, event.clientX);
  }
}
async function endPersonPointer(event) {
  const drag = state.drag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  releaseDragListeners(drag, event.pointerId);
  if (!drag.dragging) {
    clearDragVisuals(drag);
    activatePerson(drag.personId);
    return;
  }
  if (drag.selectOnly || state.perspective) {
    clearDragVisuals(drag);
    return;
  }
  const lane = drag.targetLane;
  const node = drag.targetNode;
  const relationshipDrag = drag.relationship;
  const reorderIndex = drag.reorderIndex;
  const reorderGenerationId = drag.reorderGenerationId;
  const firstSample = drag.samples.find((sample) => event.timeStamp - sample.time <= 90);
  const seconds = firstSample ? (event.timeStamp - firstSample.time) / 1000 : 0;
  const velocity = seconds > 0.008 ? {
    x: (event.clientX - firstSample.x) / seconds / state.camera.scale,
    y: (event.clientY - firstSample.y) / seconds / state.camera.scale,
  } : { x: 0, y: 0 };
  const velocities = { [drag.personId]: velocity };
  clearDragVisuals(drag, !relationshipDrag);
  try {
    if (relationshipDrag) {
      state.linkSource = null;
      $$(".is-link-source").forEach((element) => element.classList.remove("is-link-source"));
      clearLinkPreview();
      renderModeControls();
      await createDraggedRelationship(drag.personId, node?.dataset.personId);
    } else if (lane && reorderIndex !== null && reorderGenerationId) {
      await reorderPersonInGeneration(drag.personId, reorderGenerationId, reorderIndex, velocities);
    } else if (lane) {
      await movePersonToGeneration(drag.personId, lane.dataset.generationId, velocities);
    } else {
      showToast("未放入任何代际，位置保持不变");
    }
  } finally {
    if (!relationshipDrag && drag.node.isConnected) {
      const positions = captureNodePositions();
      drag.node.style.transform = "";
      drag.node.classList.remove("is-drop-pending");
      animateNodesFrom(positions, velocities);
    }
  }
}
function cancelPersonPointer(event) {
  const drag = state.drag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  releaseDragListeners(drag, event.pointerId);
  clearDragVisuals(drag);
  if (drag.dragging) showToast("已取消拖动");
}
function lostPersonPointerCapture(event) {
  const drag = state.drag;
  if (!drag || event.pointerId !== drag.pointerId) return;
  releaseDragListeners(drag, event.pointerId, false);
  const wasDragging = drag.dragging;
  clearDragVisuals(drag);
  if (wasDragging) showToast("人物拖动已中断");
}

function cancelActivePersonDrag() {
  const drag = state.drag;
  if (!drag) return;
  releaseDragListeners(drag, drag.pointerId);
  const wasDragging = drag.dragging;
  clearDragVisuals(drag);
  if (wasDragging) showToast("人物拖动已中断");
}

function releaseDragListeners(drag, pointerId, releaseCapture = true) {
  drag.node.removeEventListener("pointermove", movePersonPointer);
  drag.node.removeEventListener("pointerup", endPersonPointer);
  drag.node.removeEventListener("pointercancel", cancelPersonPointer);
  drag.node.removeEventListener("lostpointercapture", lostPersonPointerCapture);
  if (releaseCapture && drag.node.hasPointerCapture(pointerId)) {
    drag.node.releasePointerCapture(pointerId);
  }
}
function updateReorderPreview(drag, lane, clientX) {
  const person = personById(drag.personId);
  const generationId = lane.dataset.generationId;
  if (!person || String(person.generation_id) !== String(generationId)) return;
  const container = $(".lane-nodes", lane);
  if (!container) return;
  const nodes = $$(".person-node", container).filter((node) => node !== drag.node);
  const index = nodes.findIndex((node) => {
    const rect = node.getBoundingClientRect();
    return clientX < rect.left + rect.width / 2;
  });
  const insertionIndex = index < 0 ? nodes.length : index;
  const styles = getComputedStyle(container);
  const gap = Number.parseFloat(styles.columnGap || styles.gap) || 0;
  let left;
  if (!nodes.length) {
    left = drag.node.offsetLeft;
  } else if (insertionIndex === 0) {
    left = Math.max(0, nodes[0].offsetLeft - gap / 2);
  } else if (insertionIndex >= nodes.length) {
    const last = nodes[nodes.length - 1];
    left = last.offsetLeft + last.offsetWidth + gap / 2;
  } else {
    const previous = nodes[insertionIndex - 1];
    const target = nodes[insertionIndex];
    left = (previous.offsetLeft + previous.offsetWidth + target.offsetLeft) / 2;
  }
  const verticalNodes = nodes.length ? nodes : [drag.node];
  const top = Math.min(...verticalNodes.map((node) => node.offsetTop));
  const bottom = Math.max(...verticalNodes.map((node) => node.offsetTop + node.offsetHeight));
  const placeholder = document.createElement("div");
  placeholder.className = "reorder-placeholder";
  placeholder.setAttribute("aria-hidden", "true");
  placeholder.style.position = "absolute";
  placeholder.style.left = left + "px";
  placeholder.style.top = top + "px";
  placeholder.style.width = "3px";
  placeholder.style.height = Math.max(1, bottom - top) + "px";
  placeholder.style.pointerEvents = "none";
  container.append(placeholder);
  container.dataset.reordering = "true";
  drag.node.classList.add("is-sorting");
  drag.reorderIndex = insertionIndex;
  drag.reorderGenerationId = generationId;
}

function clearReorderPreview() {
  $$(".reorder-placeholder").forEach((placeholder) => placeholder.remove());
  $$(".lane-nodes[data-reordering]").forEach((container) =>
    container.removeAttribute("data-reordering")
  );
  $$(".person-node.is-sorting").forEach((node) => node.classList.remove("is-sorting"));
}

function clearDropTargets() {
  clearReorderPreview();
  if (state.drag) {
    state.drag.reorderIndex = null;
    state.drag.reorderGenerationId = null;
  }
  $$(".is-drop-target, .is-link-target").forEach((element) =>
    element.classList.remove("is-drop-target", "is-link-target")
  );
}
// Adjacent-generation people with a gender and no existing edge can receive a new link.
function canLinkPeople(firstId, secondId) {
  const first = personById(firstId), second = personById(secondId);
  if (!first?.gender || !second?.gender || String(first.id) === String(second.id)) return false;
  const rows = generations();
  const firstLevel = rows.findIndex((row) => String(row.id) === String(first.generation_id));
  const secondLevel = rows.findIndex((row) => String(row.id) === String(second.generation_id));
  if (firstLevel < 0 || secondLevel < 0 || Math.abs(firstLevel - secondLevel) !== 1) return false;
  return !relationships().some((item) => {
    const ends = relationshipEnds(item);
    return [String(ends.sourceId), String(ends.targetId)].sort().join("|") ===
      [String(first.id), String(second.id)].sort().join("|");
  });
}
function markLinkCandidates(sourceId) {
  $("#generation-lanes").classList.add("is-linking");
  $$(".person-node").forEach((node) =>
    node.classList.toggle("is-link-candidate", canLinkPeople(sourceId, node.dataset.personId)));
}
function updateLinkPreview(drag, event) {
  const svg = $("#relationship-layer");
  const stageRect = $("#canvas-stage").getBoundingClientRect();
  const box = stageBox(drag.node, stageRect, state.camera.scale);
  const x = (event.clientX - stageRect.left) / state.camera.scale;
  const y = (event.clientY - stageRect.top) / state.camera.scale;
  const startY = y < box.top + box.height / 2 ? box.top : box.bottom;
  let preview = $(".link-preview", svg);
  if (!preview) {
    preview = document.createElementNS(SVG_NS, "path");
    preview.setAttribute("class", "link-preview");
    svg.append(preview);
  }
  const bend = (y - startY) / 2;
  preview.setAttribute("d", "M " + box.centerX + " " + startY + " C " + box.centerX + " " + (startY + bend) +
    " " + x + " " + (y - bend) + " " + x + " " + y);
  preview.classList.toggle("is-valid", Boolean(drag.targetNode?.classList.contains("is-link-candidate")));
}
function clearLinkPreview() {
  $$(".link-preview").forEach((preview) => preview.remove());
  $("#generation-lanes").classList.toggle("is-linking", Boolean(state.linkMode && state.linkSource));
  if (!state.linkMode || !state.linkSource) {
    $$(".person-node.is-link-candidate").forEach((node) => node.classList.remove("is-link-candidate"));
  }
}
function clearDragVisuals(drag, keepPosition = false) {
  clearDropTargets();
  if (drag.relationship) clearLinkPreview();
  drag.node.classList.remove("is-pressed", "is-dragging");
  if (keepPosition) drag.node.classList.add("is-drop-pending");
  else drag.node.style.transform = "";
  drag.node.style.opacity = "";
  state.drag = null;
  requestDraw();
  if (!keepPosition) requestNavigatorUpdate(true);
}
async function reorderPersonInGeneration(personId, generationId, insertionIndex, velocities = {}) {
  if (preventDemoEdit()) return;
  const currentIds = peopleInGeneration(generationId).map((person) => String(person.id));
  const withoutDragged = currentIds.filter((id) => id !== String(personId));
  const nextIds = [...withoutDragged];
  nextIds.splice(Math.min(insertionIndex, nextIds.length), 0, String(personId));
  if (nextIds.every((id, index) => id === currentIds[index])) {
    showToast("人物顺序未变化");
    return;
  }
  try {
    state.workspace = workspaceFrom(await api(
      "/api/generations/" + encodeURIComponent(generationId) + "/people-order",
      { method: "PATCH", body: JSON.stringify({ person_ids: nextIds }) },
    ));
    render({ animate: true, velocities });
    showToast("人物顺序已更新", "success", undoAction());
  } catch (error) {
    try {
      await loadWorkspace();
      showToast("排序失败，已同步最新顺序", "error");
    } catch (syncError) {
      showToast("排序失败且同步失败，当前顺序状态未知：" + syncError.message, "error");
    }
  }
}

async function movePersonToGeneration(personId, generationId, velocities = {}) {
  if (preventDemoEdit()) return;
  const person = personById(personId);
  if (!person || String(person.generation_id) === String(generationId)) {
    showToast("人物已在这一代"); return;
  }
  try {
    state.workspace = workspaceFrom(await api("/api/people/" + encodeURIComponent(personId), {
      method: "PATCH", body: JSON.stringify({ generation_id: generationId }),
    }));
    render({ animate: true, velocities });
    showToast("已移到「" + personGenerationName(generationId) + "」", "success", undoAction());
  } catch (error) { showToast(error.message, "error"); }
}
async function createDraggedRelationship(firstId, secondId) {
  if (preventDemoEdit()) return;
  if (!secondId) { showToast("按住 Shift 拖到相邻代的人物上才能建立关系", "error"); return; }
  const first = personById(firstId), second = personById(secondId);
  if (!first?.gender || !second?.gender) {
    showToast("双方都必须填写性别后才能建立标准亲子关系", "error"); return;
  }
  const rows = generations();
  const firstLevel = rows.findIndex((row) => String(row.id) === String(first.generation_id));
  const secondLevel = rows.findIndex((row) => String(row.id) === String(second.generation_id));
  if (firstLevel === secondLevel) { showToast("同一代的人物不能建立亲子关系", "error"); return; }
  if (firstLevel < 0 || secondLevel < 0 || Math.abs(firstLevel - secondLevel) !== 1) {
    showToast("亲子关系只能连接相邻的两代", "error"); return;
  }
  const sourceId = firstLevel < secondLevel ? first.id : second.id;
  const targetId = firstLevel < secondLevel ? second.id : first.id;
  try {
    const data = await api("/api/relationships", {
      method: "POST", body: JSON.stringify({ source_id: sourceId, target_id: targetId }),
    });
    state.workspace = workspaceFrom(data);
    render();
    const label = data.relationship?.parent_label;
    showToast(label ? "已记录：「" + personName(sourceId) + "」是「" + personName(targetId) + "」的" + label
      : "关系已建立", "success", undoAction());
  } catch (error) { showToast(error.message, "error"); }
}
const RELATIONSHIP_KIND_LABELS = {
  father_son: "父子",
  father_daughter: "父女",
  mother_son: "母子",
  mother_daughter: "母女",
  special: "特殊",
};

function stageBox(element, stageRect, scale) {
  const rect = element.getBoundingClientRect();
  const left = (rect.left - stageRect.left) / scale;
  const top = (rect.top - stageRect.top) / scale;
  const width = rect.width / scale;
  const height = rect.height / scale;
  return {
    left, top, width, height,
    right: left + width,
    bottom: top + height,
    centerX: left + width / 2,
  };
}

function spreadRelationshipPorts(edges, endpoint) {
  const nodeKey = endpoint === "source" ? "sourceId" : "targetId";
  const boxKey = endpoint === "source" ? "sourceBox" : "targetBox";
  const otherBoxKey = endpoint === "source" ? "targetBox" : "sourceBox";
  const outputKey = endpoint === "source" ? "x1" : "x2";
  const grouped = new Map();
  edges.forEach((edge) => {
    const key = String(edge[nodeKey]);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(edge);
  });
  grouped.forEach((items) => {
    items.sort((a, b) => a[otherBoxKey].centerX - b[otherBoxKey].centerX ||
      String(a.relationship.id).localeCompare(String(b.relationship.id)));
    const box = items[0][boxKey];
    const sidePadding = Math.min(34, box.width * 0.18);
    const available = Math.max(0, box.width - sidePadding * 2);
    const gap = items.length > 1 ? Math.min(28, available / (items.length - 1)) : 0;
    const start = box.centerX - gap * (items.length - 1) / 2;
    items.forEach((edge, index) => { edge[outputKey] = start + gap * index; });
  });
}

function assignRelationshipChannels(edges) {
  const grouped = new Map();
  edges.forEach((edge) => {
    const sourceGeneration = personById(edge.sourceId)?.generation_id || "source";
    const targetGeneration = personById(edge.targetId)?.generation_id || "target";
    const key = String(sourceGeneration) + "→" + String(targetGeneration);
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(edge);
  });
  grouped.forEach((items) => {
    items.forEach((edge) => {
      edge.spanStart = Math.min(edge.x1, edge.x2);
      edge.spanEnd = Math.max(edge.x1, edge.x2);
    });
    items.sort((a, b) => a.spanStart - b.spanStart || a.spanEnd - b.spanEnd);
    const trackEnds = [];
    items.forEach((edge) => {
      let track = trackEnds.findIndex((end) => edge.spanStart > end + 22);
      if (track < 0) track = trackEnds.length;
      trackEnds[track] = edge.spanEnd;
      edge.track = track;
    });
    const top = Math.max(...items.map((edge) => edge.y1));
    const bottom = Math.min(...items.map((edge) => edge.y2));
    const distance = Math.max(1, bottom - top);
    const inset = Math.min(34, distance * 0.2);
    const usable = Math.max(0, distance - inset * 2);
    const trackCount = Math.max(1, trackEnds.length);
    items.forEach((edge) => {
      edge.channelY = trackCount === 1
        ? top + distance / 2
        : top + inset + usable * ((edge.track + 0.5) / trackCount);
    });
  });
}

function createRelationshipDefinitions(svg) {
  const defs = document.createElementNS(SVG_NS, "defs");
  Object.keys(RELATIONSHIP_KIND_LABELS).forEach((kind) => {
    const marker = document.createElementNS(SVG_NS, "marker");
    marker.id = "relationship-arrow-" + kind;
    marker.setAttribute("viewBox", "0 0 8 8");
    marker.setAttribute("refX", "7.5");
    marker.setAttribute("refY", "4");
    marker.setAttribute("markerWidth", "5.5");
    marker.setAttribute("markerHeight", "5.5");
    marker.setAttribute("markerUnits", "strokeWidth");
    marker.setAttribute("orient", "auto");
    const arrow = document.createElementNS(SVG_NS, "path");
    arrow.setAttribute("d", "M 0 0 L 8 4 L 0 8 Z");
    arrow.setAttribute("class", "relationship-marker");
    arrow.setAttribute("data-kind", kind);
    marker.append(arrow);
    defs.append(marker);
  });
  svg.append(defs);
}

function shortestRelationshipPathIds(startId, endId) {
  if (!startId || !endId || String(startId) === String(endId)) return [];
  const adjacency = new Map();
  relationships().forEach((relationship) => {
    const ends = relationshipEnds(relationship);
    const source = String(ends.sourceId), target = String(ends.targetId);
    if (!adjacency.has(source)) adjacency.set(source, []);
    if (!adjacency.has(target)) adjacency.set(target, []);
    adjacency.get(source).push({ personId: target, relationshipId: String(relationship.id) });
    adjacency.get(target).push({ personId: source, relationshipId: String(relationship.id) });
  });
  const start = String(startId), end = String(endId);
  const queue = [start];
  const previous = new Map([[start, null]]);
  while (queue.length && !previous.has(end)) {
    const current = queue.shift();
    (adjacency.get(current) || []).forEach((step) => {
      if (previous.has(step.personId)) return;
      previous.set(step.personId, { personId: current, relationshipId: step.relationshipId });
      queue.push(step.personId);
    });
  }
  if (!previous.has(end)) return [];
  const ids = [];
  for (let current = end; current !== start;) {
    const step = previous.get(current);
    ids.push(step.relationshipId);
    current = step.personId;
  }
  return ids.reverse();
}

function relationshipFocusIds() {
  if (state.focusedRelationshipId) return [String(state.focusedRelationshipId)];
  if (state.perspective && state.selectionA && state.selectionB) {
    return shortestRelationshipPathIds(state.selectionA, state.selectionB);
  }
  if (state.activeRelationshipId) return [String(state.activeRelationshipId)];
  const personId = state.activeRelationshipPersonId ||
    (state.perspective && !state.selectionB ? state.selectionA : null);
  if (personId) {
    return relationships()
      .filter((relationship) => {
        const ends = relationshipEnds(relationship);
        return String(ends.sourceId) === String(personId) || String(ends.targetId) === String(personId);
      })
      .map((relationship) => String(relationship.id));
  }
  return [];
}

function applyRelationshipFocus() {
  const svg = $("#relationship-layer");
  if (!svg) return;
  const ids = new Set(relationshipFocusIds());
  svg.classList.toggle("has-active-relationship", ids.size > 0);
  $$('[data-relationship-id]', svg).forEach((element) => {
    element.classList.toggle("is-active", ids.has(String(element.dataset.relationshipId)));
  });
  $$(".person-node").forEach((node) => {
    node.classList.remove("is-relationship-endpoint");
    delete node.dataset.relationshipKind;
    delete node.dataset.relationshipRole;
    delete node.dataset.roleEdge;
    delete node.dataset.roleKind;
  });
  ids.forEach((id) => {
    const relationship = relationshipById(id);
    if (!relationship) return;
    const ends = relationshipEnds(relationship);
    const kind = ids.size === 1
      ? relationshipKindKey(relationship, ends.sourceId, ends.targetId)
      : "multiple";
    [ends.sourceId, ends.targetId].forEach((personId) => {
      const node = $('.person-node[data-person-id="' + CSS.escape(String(personId)) + '"]');
      if (!node) return;
      node.classList.add("is-relationship-endpoint");
      node.dataset.relationshipKind = kind;
    });
  });
  relationshipRoles().forEach((item) => {
    const node = $('.person-node[data-person-id="' + CSS.escape(String(item.personId)) + '"]');
    if (!node) return;
    node.dataset.relationshipRole = item.role;
    node.dataset.roleEdge = item.edge;
    node.dataset.roleKind = item.kind;
  });
}
// Kinship badges on cards: a hovered line labels both ends, a hovered person labels relatives.
function relationshipRoles() {
  const single = (id) => {
    const relationship = relationshipById(id);
    if (!relationship) return [];
    const ends = relationshipEnds(relationship);
    const kind = relationshipKindKey(relationship, ends.sourceId, ends.targetId);
    return [
      { personId: ends.sourceId, role: relationship.parent_label, edge: "bottom", kind },
      { personId: ends.targetId, role: relationship.child_label, edge: "top", kind },
    ].filter((item) => item.role);
  };
  if (state.focusedRelationshipId) return single(state.focusedRelationshipId);
  if (state.perspective && state.selectionA && state.selectionB) return [];
  if (state.activeRelationshipId) return single(state.activeRelationshipId);
  const personId = state.activeRelationshipPersonId || (state.perspective ? state.selectionA : null);
  if (!personId) return [];
  return personRelatives(personId).map((item) => ({
    personId: item.person.id, role: item.role, edge: item.side === "parent" ? "bottom" : "top", kind: item.kind,
  }));
}

function setActiveRelationship(relationshipId) {
  state.activeRelationshipId = relationshipId;
  state.activeRelationshipPersonId = null;
  applyRelationshipFocus();
}

function clearActiveRelationship(relationshipId) {
  if (String(state.activeRelationshipId) !== String(relationshipId)) return;
  state.activeRelationshipId = null;
  applyRelationshipFocus();
}

function setFocusedRelationship(relationshipId) {
  state.focusedRelationshipId = relationshipId;
  applyRelationshipFocus();
}

function clearFocusedRelationship(relationshipId) {
  if (String(state.focusedRelationshipId) !== String(relationshipId)) return;
  state.focusedRelationshipId = null;
  applyRelationshipFocus();
}

function setActiveRelationshipPerson(personId) {
  state.activeRelationshipId = null;
  state.activeRelationshipPersonId = personId;
  applyRelationshipFocus();
}

function clearActiveRelationshipPerson(personId) {
  if (String(state.activeRelationshipPersonId) !== String(personId)) return;
  state.activeRelationshipPersonId = null;
  applyRelationshipFocus();
}

// Orthogonal routing with softened corners; the channel keeps parallel lines apart.
function relationshipPathData(edge) {
  const { x1, y1, x2, y2, channelY } = edge;
  const direction = Math.sign(x2 - x1);
  const radius = Math.max(0, Math.min(10, Math.abs(x2 - x1) / 2, channelY - y1, y2 - channelY));
  if (!direction || radius < 1) return "M " + x1 + " " + y1 + " V " + channelY + " H " + x2 + " V " + y2;
  return "M " + x1 + " " + y1 +
    " V " + (channelY - radius) +
    " Q " + x1 + " " + channelY + " " + (x1 + direction * radius) + " " + channelY +
    " H " + (x2 - direction * radius) +
    " Q " + x2 + " " + channelY + " " + x2 + " " + (channelY + radius) +
    " V " + y2;
}
function drawRelationships() {
  const stage = $("#canvas-stage");
  const lanes = $("#generation-lanes");
  const svg = $("#relationship-layer");
  const focusedRelationshipId = document.activeElement?.classList?.contains("relationship-hit")
    ? document.activeElement.dataset.relationshipId
    : null;
  svg.innerHTML = "";
  const stageRect = stage.getBoundingClientRect();
  const width = Math.max(
    stage.scrollWidth, stage.offsetWidth, stage.clientWidth,
    lanes.scrollWidth, lanes.offsetWidth, lanes.clientWidth,
  );
  const height = Math.max(
    stage.scrollHeight, stage.offsetHeight, stage.clientHeight,
    lanes.scrollHeight, lanes.offsetHeight, lanes.clientHeight,
  );
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.setAttribute("preserveAspectRatio", "none");
  createRelationshipDefinitions(svg);
  const scale = state.camera.scale;
  const boxCache = new Map();
  const boxFor = (id, element) => {
    const key = String(id);
    if (!boxCache.has(key)) boxCache.set(key, stageBox(element, stageRect, scale));
    return boxCache.get(key);
  };
  const edges = relationships().map((relationship) => {
    const ends = relationshipEnds(relationship);
    const source = $('.person-node[data-person-id="' + CSS.escape(String(ends.sourceId)) + '"]');
    const target = $('.person-node[data-person-id="' + CSS.escape(String(ends.targetId)) + '"]');
    if (!source || !target) return null;
    const sourceBox = boxFor(ends.sourceId, source);
    const targetBox = boxFor(ends.targetId, target);
    return {
      relationship,
      sourceId: ends.sourceId,
      targetId: ends.targetId,
      sourceBox,
      targetBox,
      x1: sourceBox.centerX,
      y1: sourceBox.bottom,
      x2: targetBox.centerX,
      y2: targetBox.top,
    };
  }).filter(Boolean);
  spreadRelationshipPorts(edges, "source");
  spreadRelationshipPorts(edges, "target");
  assignRelationshipChannels(edges);
  edges.forEach((edge) => {
    const relationship = edge.relationship;
    const kind = relationship.kind || relationship.type || "standard";
    const kindKey = relationshipKindKey(relationship, edge.sourceId, edge.targetId);
    const d = relationshipPathData(edge);
    const commonAttributes = (element) => {
      element.setAttribute("d", d);
      element.setAttribute("data-kind", kindKey);
      element.setAttribute("data-relationship-id", relationship.id);
      element.setAttribute("data-source-id", edge.sourceId);
      element.setAttribute("data-target-id", edge.targetId);
    };
    const casing = document.createElementNS(SVG_NS, "path");
    casing.setAttribute("class", "relationship-casing");
    commonAttributes(casing);
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("class", "relationship-path");
    path.setAttribute("marker-end", "url(#relationship-arrow-" + kindKey + ")");
    commonAttributes(path);
    const origin = document.createElementNS(SVG_NS, "circle");
    origin.setAttribute("class", "relationship-origin");
    origin.setAttribute("cx", edge.x1);
    origin.setAttribute("cy", edge.y1);
    origin.setAttribute("r", "4");
    origin.setAttribute("data-kind", kindKey);
    origin.setAttribute("data-relationship-id", relationship.id);
    origin.setAttribute("data-source-id", edge.sourceId);
    origin.setAttribute("data-target-id", edge.targetId);
    const hit = document.createElementNS(SVG_NS, "path");
    hit.setAttribute("class", "relationship-hit");
    commonAttributes(hit);
    hit.setAttribute("tabindex", "0");
    hit.setAttribute("role", "button");
    const relationLabel = kind === "special"
      ? [relationship.parent_label, relationship.child_label].filter(Boolean).join(" / ") || "特殊"
      : RELATIONSHIP_KIND_LABELS[kindKey] || "亲子";
    const accessibleLabel = (isReadonlyDemo() ? "查看关系：" : "编辑：") + personName(edge.sourceId) + " 到 " +
      personName(edge.targetId) + " 的" + relationLabel + "关系";
    hit.setAttribute("aria-label", accessibleLabel);
    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = personName(edge.sourceId) + " → " + personName(edge.targetId) +
      " · " + relationLabel;
    hit.append(title);
    hit.addEventListener("pointerenter", () => setActiveRelationship(relationship.id));
    hit.addEventListener("pointerleave", () => {
      if (document.activeElement !== hit) clearActiveRelationship(relationship.id);
    });
    hit.addEventListener("pointerdown", () => setActiveRelationship(relationship.id));
    hit.addEventListener("focus", () => setFocusedRelationship(relationship.id));
    hit.addEventListener("blur", () => {
      clearFocusedRelationship(relationship.id);
      if (!hit.matches(":hover")) clearActiveRelationship(relationship.id);
    });
    hit.addEventListener("click", () => openRelationshipDialog(relationship.id));
    hit.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault(); openRelationshipDialog(relationship.id);
      }
    });
    svg.append(casing, path, origin, hit);
  });
  applyRelationshipFocus();
  if (focusedRelationshipId) {
    const replacement = $('.relationship-hit[data-relationship-id="' +
      CSS.escape(String(focusedRelationshipId)) + '"]', svg);
    replacement?.focus({ preventScroll: true });
  }
}
function relationshipKindKey(relationship, sourceId, targetId) {
  if ((relationship.kind || relationship.type) === "special") return "special";
  const standardCodes = new Set([
    "father_son", "father_daughter", "mother_son", "mother_daughter",
  ]);
  if (standardCodes.has(relationship.code)) return relationship.code;
  const source = personById(sourceId), target = personById(targetId);
  return (source?.gender === "male" ? "father" : "mother") + "_" +
    (target?.gender === "male" ? "son" : "daughter");
}
let relationshipSaving = false;
function relationshipKindValue() {
  return $('#relationship-kind input[name="relationship-kind"]:checked')?.value || "standard";
}
function setRelationshipKindValue(value) {
  $$('#relationship-kind input[name="relationship-kind"]').forEach((input) => { input.checked = input.value === value; });
}
// Standard titles follow gender; special ones use the labels typed in the dialog.
function relationshipDialogRoles(item) {
  const { sourceId, targetId } = relationshipEnds(item);
  const source = personById(sourceId), target = personById(targetId);
  if (relationshipKindValue() === "special") {
    return [$("#parent-label").value.trim() || "上代称谓", $("#child-label").value.trim() || "下代称谓"];
  }
  return [source?.gender === "male" ? "爸爸" : "妈妈", target?.gender === "male" ? "儿子" : "女儿"];
}
function renderRelationshipContext(item) {
  const context = $("#relationship-context");
  context.replaceChildren();
  const { sourceId, targetId } = relationshipEnds(item);
  const roles = relationshipDialogRoles(item);
  const kind = relationshipKindValue() === "special" ? "special"
    : relationshipKindKey({ ...item, kind: "standard", type: "standard", code: null }, sourceId, targetId);
  context.dataset.kind = kind;
  [sourceId, targetId].forEach((personId, index) => {
    if (index) {
      const connector = document.createElement("span");
      connector.className = "relationship-connector";
      connector.append(createIcon("arrow-down"));
      context.append(connector);
    }
    const person = personById(personId);
    const card = document.createElement("div");
    card.className = "relationship-person";
    const avatar = document.createElement("span");
    avatar.className = "profile-avatar";
    renderProfileAvatar(avatar, person);
    const meta = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = person?.name || "未知人物";
    const detail = document.createElement("span");
    detail.textContent = (index ? "下一代 · " : "上一代 · ") + personGenerationName(person?.generation_id);
    meta.append(title, detail);
    const role = document.createElement("span");
    role.className = "relationship-role";
    role.textContent = roles[index];
    card.append(avatar, meta, role);
    context.append(card);
  });
}
async function openRelationshipDialog(id) {
  if (state.historyBusy || state.mutations) return;
  if (relationshipSaving) return;
  if ($("#person-dialog").open && !await closePersonDialog()) return;
  const item = relationshipById(id);
  if (!item) return;
  state.editingRelationshipId = id;
  setRelationshipKindValue(item.kind || item.type || "standard");
  const special = (item.kind || item.type) === "special";
  $("#parent-label").value = special ? item.parent_label || "" : "";
  $("#child-label").value = special ? item.child_label || "" : "";
  syncRelationshipFields();
  $("#relationship-dialog").showModal();
}
function closeRelationshipDialog() {
  if (relationshipSaving) return;
  $("#relationship-dialog").close();
  state.editingRelationshipId = null;
  $("#relationship-form").reset();
  syncRelationshipFields();
}
function syncRelationshipFields() {
  const special = relationshipKindValue() === "special";
  $("#parent-label-field").hidden = !special;
  $("#child-label-field").hidden = !special;
  $("#parent-label").required = special;
  $("#child-label").required = special;
  const item = relationshipById(state.editingRelationshipId);
  const labels = { father_son: "父子", father_daughter: "父女", mother_son: "母子", mother_daughter: "母女", special: "特殊" };
  const ends = item ? relationshipEnds(item) : {};
  const key = item ? relationshipKindKey({ ...item, kind: "standard", type: "standard", code: null }, ends.sourceId, ends.targetId) : "";
  $("#relationship-dialog-title").textContent = special ? "特殊关系" : (labels[key] || "亲子") + "关系";
  if (!item) {
    $("#relationship-description").textContent = "";
    return;
  }
  renderRelationshipContext(item);
  const [parentRole] = relationshipDialogRoles(item);
  $("#relationship-description").textContent = special
    ? (isReadonlyDemo() ? "已记录的特殊关系称谓：" + item.parent_label + " / " + item.child_label
      : "分别填写两位人物在这段关系中的称谓，例如养父与养女。")
    : "「" + personName(ends.sourceId) + "」是「" + personName(ends.targetId) + "」的" + parentRole +
      "，称谓由双方性别与相邻代际自动确定。";
}
function setRelationshipSaving(saving) {
  relationshipSaving = saving;
  $("#relationship-form").setAttribute("aria-busy", String(saving));
  $$("input, select, button", $("#relationship-form")).forEach((control) => control.disabled = saving);
  $("#relationship-save").textContent = saving ? "保存中…" : "保存关系";
}
async function saveRelationship(event) {
  if (preventDemoEdit(event)) return;
  event.preventDefault();
  if (relationshipSaving) return;
  const id = state.editingRelationshipId;
  const kind = relationshipKindValue();
  const payload = {
    kind,
    parent_label: kind === "special" ? $("#parent-label").value.trim() : null,
    child_label: kind === "special" ? $("#child-label").value.trim() : null,
  };
  if (kind === "special" && (!payload.parent_label || !payload.child_label)) {
    showToast("特殊关系必须填写双方称谓", "error"); return;
  }
  setRelationshipSaving(true);
  try {
    state.workspace = workspaceFrom(await api("/api/relationships/" + encodeURIComponent(id), {
      method: "PATCH", body: JSON.stringify(payload),
    }));
    setRelationshipSaving(false);
    closeRelationshipDialog();
    render();
    if (state.perspective) prefetchRelationshipPath();
    showToast("关系已保存", "success");
  } catch (error) {
    $("#relationship-description").textContent = "保存失败：" + error.message + "，请重试。";
  } finally { setRelationshipSaving(false); }
}
async function deleteRelationship() {
  if (preventDemoEdit()) return;
  if (relationshipSaving || !state.editingRelationshipId) return;
  const id = state.editingRelationshipId;
  const item = relationshipById(id);
  const ends = relationshipEnds(item);
  if (!await askConfirmation("「" + personName(ends.sourceId) + "」与「" + personName(ends.targetId) + "」之间的连线会被删除，两位人物的档案保持不变。", {
    title: "删除这段关系？", confirmLabel: "删除关系", tone: "danger",
  })) return;
  try {
    setRelationshipSaving(true);
    state.workspace = workspaceFrom(await api("/api/relationships/" + encodeURIComponent(id), { method: "DELETE" }));
    setRelationshipSaving(false);
    closeRelationshipDialog();
    render();
    if (state.perspective) prefetchRelationshipPath();
    showToast("关系已删除", "success", undoAction());
  } catch (error) { $("#relationship-description").textContent = "删除失败：" + error.message; }
  finally { setRelationshipSaving(false); }
}
async function enterPerspective() {
  if ($("#person-dialog").open && !await closePersonDialog()) return;
  if (state.perspective) return;
  exitLinkMode(false);
  invalidateRelationshipTasks();
  state.perspective = true; state.selectionA = null; state.selectionB = null;
  state.selectionTarget = "a";
  $("#perspective-mode").setAttribute("aria-pressed", "true");
  $("#person-search-input").blur();
  closeSearchResults();
  hideToast();
  render();
}
function exitPerspective() {
  cancelActivePersonDrag();
  invalidateRelationshipTasks();
  state.perspective = false; state.selectionA = null; state.selectionB = null;
  state.selectionTarget = "a";
  $("#perspective-mode").setAttribute("aria-pressed", "false");
  hideToast();
  render();
}
function selectPerspectiveTarget(slot) {
  if (!state.perspective) return;
  state.selectionTarget = slot;
  renderSelection();
}

function clearPerspectiveSelection(slot) {
  if (!state.perspective) return;
  invalidateRelationshipTasks();
  state[slot === "a" ? "selectionA" : "selectionB"] = null;
  state.selectionTarget = slot;
  hideToast();
  render();
  $("#selection-" + slot).focus({ preventScroll: true });
}

function selectPerspectivePerson(id) {
  if (!state.perspective) return;
  const key = state.selectionTarget === "a" ? "selectionA" : "selectionB";
  const otherKey = state.selectionTarget === "a" ? "selectionB" : "selectionA";
  if (String(state[otherKey]) === String(id)) {
    showToast("A 与 B 不能是同一人物，请选择其他人物", "error");
    return;
  }
  if (String(state[key]) === String(id)) return;
  const restoreFocus = document.activeElement?.classList?.contains("person-node");
  state.focusedPersonId = id;
  invalidateRelationshipTasks();
  state[key] = id;
  if (!state[otherKey]) state.selectionTarget = otherKey === "selectionA" ? "a" : "b";
  hideToast();
  render();
  if (restoreFocus) {
    $('.person-node[data-person-id="' + CSS.escape(String(id)) + '"]')
      ?.focus({ preventScroll: true });
  }
  if (state.selectionA && state.selectionB) prefetchRelationshipPath();
}
function renderSelection() {
  const visibilityChanged = $("#selection-tray").hidden !== !state.perspective;
  $("#selection-tray").hidden = !state.perspective;
  updateNavigatorSelection();
  if (visibilityChanged) handleCameraResize();
  ["a", "b"].forEach((slot) => {
    const personId = state[slot === "a" ? "selectionA" : "selectionB"];
    const slotButton = $("#selection-" + slot);
    const label = slot.toUpperCase();
    const person = personById(personId);
    const badge = document.createElement("span");
    badge.className = "slot-badge";
    badge.textContent = label;
    const copy = document.createElement("span");
    copy.className = "slot-copy";
    const name = document.createElement("strong");
    name.textContent = person ? person.name : "未选择";
    const hint = document.createElement("small");
    hint.textContent = person ? personGenerationName(person.generation_id)
      : state.selectionTarget === slot ? "点选画布中的人物" : "等待选择";
    copy.append(name, hint);
    slotButton.replaceChildren(badge, copy);
    slotButton.dataset.filled = String(Boolean(person));
    slotButton.setAttribute("aria-pressed", String(state.selectionTarget === slot));
    slotButton.setAttribute("aria-label", "选择或替换 " + label + "：" +
      (personId ? personName(personId) : "未选择"));
    $("#clear-selection-" + slot).disabled = !personId;
    $("#clear-selection-" + slot).hidden = !personId;
  });
  const hasSelection = Boolean(state.selectionA && state.selectionB);
  $("#swap-selection").disabled = !hasSelection;
  const copyButton = $("#export-relationship");
  let label = "复制关系";
  let busy = false;
  let status = "请选择人物填入 " + state.selectionTarget.toUpperCase();
  if (state.copyInFlight) {
    label = "复制中…";
    status = "正在复制 B 相对 A 的关系…";
    busy = true;
  } else if (hasSelection && state.relationshipPathLoading) {
    label = "关系计算中…";
    status = "正在计算 B 相对 A 的关系…";
    busy = true;
  } else if (hasSelection && state.relationshipPathError) {
    label = "重试计算";
    status = "计算失败：" + state.relationshipPathError;
  } else if (hasSelection && state.relationshipCopyError) {
    label = "重试复制";
    status = "复制失败：" + state.relationshipCopyError;
  } else if (hasSelection && !state.relationshipCopyText) {
    label = "暂无关系";
    status = "未找到 A 与 B 之间的关系，可替换任一人物";
  } else if (hasSelection) {
    status = "关系已就绪 · 点选人物替换 " + state.selectionTarget.toUpperCase();
  }
  copyButton.disabled = !hasSelection || busy ||
    (!state.relationshipCopyText && !state.relationshipPathError);
  copyButton.replaceChildren(createIcon(state.relationshipPathError ? "undo" : "copy"), document.createTextNode(label));
  copyButton.setAttribute("aria-label", label);
  copyButton.setAttribute("aria-busy", String(busy));
  $("#selection-status").textContent = status;
  $("#selection-status").dataset.state = state.relationshipPathError || state.relationshipCopyError ? "error" : "";
  $("#selection-tray").classList.toggle("is-ready", Boolean(hasSelection && state.relationshipCopyText && !busy && !state.relationshipPathError && !state.relationshipCopyError));
  renderSelectionResult(hasSelection);
}
// Shows the computed kinship chain instead of hiding it behind the copy action.
function renderSelectionResult(hasSelection) {
  const result = $("#selection-result");
  const paragraph = (className, text) => {
    const element = document.createElement("p");
    element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  let status = "empty";
  if (!hasSelection) {
    result.replaceChildren(paragraph("result-placeholder",
      state.selectionA || state.selectionB ? "再点选一位人物，即可查看两人的称谓关系" : "依次点选两位人物，查看 B 是 A 的什么人"));
  } else if (state.relationshipPathLoading) {
    status = "loading";
    result.replaceChildren(paragraph("result-placeholder", "正在推算称谓…"));
  } else if (state.relationshipPathError) {
    status = "error";
    result.replaceChildren(paragraph("result-placeholder", "称谓暂时无法计算，请重试。"));
  } else if (!state.relationshipCopyText) {
    status = "none";
    result.replaceChildren(paragraph("result-placeholder", "两人之间还没有可以追溯的亲子连线。"));
  } else {
    status = "ready";
    const name = (id, slot) => {
      const element = document.createElement("span");
      element.className = "result-person";
      element.dataset.slot = slot;
      element.textContent = personName(id);
      return element;
    };
    const lead = paragraph("result-lead");
    lead.append(name(state.selectionB, "b"), " 是 ", name(state.selectionA, "a"), " 的");
    const chain = paragraph("result-chain");
    (state.relationshipPath?.labels || []).forEach((label, index) => {
      if (index) {
        const joiner = document.createElement("span");
        joiner.className = "chain-joiner";
        joiner.textContent = "的";
        chain.append(joiner);
      }
      const step = document.createElement("span");
      step.className = "chain-step";
      step.textContent = label;
      chain.append(step);
    });
    result.replaceChildren(lead, chain);
  }
  result.dataset.state = status;
}
function relationshipPathLabels(result, pathText) {
  const personIds = Array.isArray(result?.person_ids) ? result.person_ids : [];
  const relationshipIds = Array.isArray(result?.relationship_ids) ? result.relationship_ids : [];
  const labels = relationshipIds.map((id, index) => {
    const relationship = relationshipById(id);
    const next = personIds[index + 1];
    if (!relationship || next === undefined) return "";
    return String(relationshipEnds(relationship).sourceId) === String(next)
      ? relationship.parent_label : relationship.child_label;
  });
  return labels.length && labels.every(Boolean) ? labels : pathText.split("的").filter(Boolean);
}
function relationshipPathText(result) {
  if (!result || typeof result !== "object") return "";
  for (const key of ["text", "relationship_text", "path_text", "label", "description"]) {
    if (typeof result[key] === "string" && result[key].trim()) return result[key].trim();
  }
  if (typeof result.path === "string" && result.path.trim()) return result.path.trim();
  const steps = Array.isArray(result.path) ? result.path :
    Array.isArray(result.labels) ? result.labels : [];
  return steps.map((step) => {
    if (typeof step === "string") return step.trim();
    if (!step || typeof step !== "object") return "";
    return step.label || step.relationship_label || step.text ||
      step.parent_label || step.child_label || step.name || "";
  }).filter(Boolean).join("的");
}

async function prefetchRelationshipPath() {
  if (!state.perspective || !state.selectionA || !state.selectionB) return;
  const a = state.selectionA;
  const b = state.selectionB;
  const token = ++state.pathRequestId;
  invalidateCopyRequest();
  state.relationshipCopyText = null;
  state.relationshipPathError = null;
  state.relationshipPathLoading = true;
  renderSelection();
  try {
    let result;
    try {
      result = await api("/api/path?from=" + encodeURIComponent(a) + "&to=" + encodeURIComponent(b));
    } catch (error) {
      if (!isPathRequestCurrent(token, a, b)) return;
      state.relationshipPathError = error instanceof Error ? error.message : "未知错误";
      return;
    }
    if (!isPathRequestCurrent(token, a, b)) return;
    const pathText = relationshipPathText(result);
    state.relationshipCopyText = result.found === false || !pathText
      ? null
      : personName(b) + " 是 " + personName(a) + " 的：" + pathText;
    state.relationshipPath = state.relationshipCopyText ? { labels: relationshipPathLabels(result, pathText) } : null;
  } finally {
    if (isPathRequestCurrent(token, a, b)) {
      state.relationshipPathLoading = false;
      renderSelection();
    }
  }
}

async function writeClipboardText(text) {
  let clipboardError = null;
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      clipboardError = error;
    }
  }
  const activeElement = document.activeElement;
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.setAttribute("aria-hidden", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  textarea.style.opacity = "0";
  let copied = false;
  try {
    document.body.append(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    copied = document.execCommand("copy");
  } finally {
    textarea.remove();
    if (activeElement instanceof HTMLElement) activeElement.focus();
  }
  if (!copied) {
    throw clipboardError || new Error("当前浏览器不支持剪贴板复制");
  }
}

async function copyRelationship() {
  if (state.copyInFlight || state.relationshipPathLoading || !state.perspective) return;
  if (state.relationshipPathError) {
    await prefetchRelationshipPath();
    return;
  }
  if (!state.selectionA || !state.selectionB || !state.relationshipCopyText) {
    showToast("关系尚未计算完成，未复制", "error");
    return;
  }
  const a = state.selectionA;
  const b = state.selectionB;
  const sentence = state.relationshipCopyText;
  const token = ++state.copyRequestId;
  state.copyInFlight = true;
  state.relationshipCopyError = null;
  renderSelection();

  // 必须在点击任务的第一个异步等待之前同步调用，保留 clipboard user activation。
  const clipboardPromise = writeClipboardText(sentence);
  try {
    await clipboardPromise;
    if (!isCopyRequestCurrent(token, a, b) ||
        sentence !== state.relationshipCopyText) return;
    showToast("关系已复制到剪贴板", "success");
  } catch (error) {
    if (!isCopyRequestCurrent(token, a, b) ||
        sentence !== state.relationshipCopyText) return;
    state.relationshipCopyError = error instanceof Error ? error.message : "未知错误";
  } finally {
    if (isCopyRequestCurrent(token, a, b) &&
        sentence === state.relationshipCopyText) {
      state.copyInFlight = false;
      renderSelection();
    }
  }
}

function askConfirmation(message, { title = "请确认", confirmLabel = "确认", tone = "default" } = {}) {
  if (state.confirmationResolver) state.confirmationResolver(false);
  $("#confirm-title").textContent = title;
  $("#confirm-message").textContent = message;
  $("#confirm-accept").textContent = confirmLabel;
  $("#confirm-dialog").dataset.tone = tone;
  $("#confirm-dialog").showModal();
  $("#confirm-cancel").focus();
  return new Promise((resolve) => {
    state.confirmationResolver = resolve;
  });
}

function resolveConfirmation(accepted) {
  if (!state.confirmationResolver) return;
  const resolve = state.confirmationResolver;
  state.confirmationResolver = null;
  if ($("#confirm-dialog").open) $("#confirm-dialog").close();
  resolve(accepted);
}

function bindEvents() {
  $("#workspace-sidebar-toggle").addEventListener("click", toggleWorkspaceSidebar);
  $("#workspace-overview").addEventListener("click", () => {
    state.focusedGenerationId = null;
    closeWorkspaceSidebar();
    renderWorkspaceChrome();
    requestAnimationFrame(fitCamera);
  });
  $("#generation-navigation").addEventListener("click", (event) => {
    const button = event.target.closest(".generation-nav-item");
    if (!button || !event.currentTarget.contains(button)) return;
    closeWorkspaceSidebar();
    requestAnimationFrame(() => focusGenerationInCanvas(button.dataset.generationId));
  });
  $("#help-toggle").addEventListener("click", toggleWorkspaceHelp);
  $("#history-undo").addEventListener("click", () => travelHistory("undo"));
  $("#history-redo").addEventListener("click", () => travelHistory("redo"));
  $("#add-first-generation").addEventListener("click", () => openGenerationDialog("first"));
  $("#add-generation-above").addEventListener("click", () => {
    closeGenerationMenu();
    openGenerationDialog("above");
  });
  $("#add-generation-below").addEventListener("click", () => {
    closeGenerationMenu();
    openGenerationDialog("below");
  });
  $("#generation-menu-toggle").addEventListener("click", toggleGenerationMenu);
  $("#generation-form").addEventListener("submit", saveGeneration);
  $("#generation-cancel").addEventListener("click", closeGenerationDialog);
  $("#generation-dialog").addEventListener("cancel", () => {
    state.generationIntent = null;
  });
  $("#confirm-cancel").addEventListener("click", () => resolveConfirmation(false));
  $("#confirm-accept").addEventListener("click", () => resolveConfirmation(true));
  $("#confirm-dialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    resolveConfirmation(false);
  });
  $("#person-form").addEventListener("submit", savePerson);
  $("#person-delete").addEventListener("click", deletePerson);
  $("#relationship-form").addEventListener("submit", saveRelationship);
  $("#relationship-delete").addEventListener("click", deleteRelationship);
  $("#relationship-kind").addEventListener("change", syncRelationshipFields);
  $$("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.closeDialog === "person-dialog") closePersonDialog();
    if (button.dataset.closeDialog === "relationship-dialog") closeRelationshipDialog();
  }));
  $("#person-dialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    closePersonDialog();
  });
  $("#person-form").addEventListener("input", personInputChanged);
  $("#person-generation").addEventListener("change", personInputChanged);
  $("#person-gender").addEventListener("change", personInputChanged);
  $("#person-photo").addEventListener("change", () => {
    if (preventDemoEdit()) return;
    const file = $("#person-photo").files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/gif", "image/webp"].includes(file.type) || file.size > 8 * 1024 * 1024) {
      $("#person-photo").value = "";
      releasePersonPhotoPreview();
      updatePersonPreview();
      setPersonStatus("请选择不超过 8 MB 的 JPG、PNG、GIF 或 WebP 照片", "error");
      return;
    }
    releasePersonPhotoPreview();
    personEditor.photoUrl = URL.createObjectURL(file);
    personEditor.removePhoto = false;
    personInputChanged();
  });
  $("#person-photo-remove").addEventListener("click", () => {
    if (preventDemoEdit()) return;
    releasePersonPhotoPreview();
    $("#person-photo").value = "";
    personEditor.removePhoto = true;
    personInputChanged();
  });
  $(".photo-picker").addEventListener("keydown", (event) => {
    if (preventDemoEdit(event)) return;
    if ((event.key === "Enter" || event.key === " ") && !personEditor.saving) {
      event.preventDefault();
      $("#person-photo").click();
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (personHasChanges()) { event.preventDefault(); event.returnValue = ""; }
  });
  $("#relationship-dialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    closeRelationshipDialog();
  });
  $("#link-mode").addEventListener("click", toggleLinkMode);
  $("#perspective-mode").addEventListener("click", enterPerspective);
  $("#select-mode").addEventListener("click", enterSelectMode);
  $("#exit-perspective").addEventListener("click", exitPerspective);
  ["a", "b"].forEach((slot) => {
    $("#selection-" + slot).addEventListener("click", () => selectPerspectiveTarget(slot));
    $("#clear-selection-" + slot).addEventListener("click", () => clearPerspectiveSelection(slot));
  });
  $("#swap-selection").addEventListener("click", () => {
    invalidateRelationshipTasks();
    [state.selectionA, state.selectionB] = [state.selectionB, state.selectionA];
    hideToast();
    render();
    prefetchRelationshipPath();
  });
  $("#export-relationship").addEventListener("click", copyRelationship);
  $("#theme-toggle").addEventListener("click", toggleTheme);
  matchMedia(THEME_QUERY).addEventListener?.("change", (event) => {
    if (!localStorage.getItem(THEME_KEY)) setTheme(event.matches ? "mocha" : "latte");
  });
  $(".name-suggestions").addEventListener("click", (event) => {
    const suggestion = event.target.closest("[data-generation-name]");
    if (!suggestion) return;
    $("#generation-name").value = suggestion.dataset.generationName;
    $$("[data-generation-name]").forEach((button) => button.setAttribute("aria-pressed", String(button === suggestion)));
    $("#generation-name").focus();
  });
  $("#person-relatives").addEventListener("click", (event) => {
    const edit = event.target.closest(".relative-edit");
    if (edit) { editRelativeRelationship(edit.dataset.relationshipId); return; }
    const relative = event.target.closest(".relative-person");
    if (relative) openRelativeProfile(relative.dataset.relativeId);
  });
  $("#person-relative-add").addEventListener("change", (event) => {
    $("#person-relative-confirm").disabled = !event.currentTarget.value;
  });
  $("#person-relative-confirm").addEventListener("click", addRelativeFromInspector);
  $("#person-form").addEventListener("keydown", (event) => {
    if (isReadonlyDemo() && event.key === "Enter" && (event.metaKey || event.ctrlKey)) { event.preventDefault(); return; }
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !personEditor.saving) {
      event.preventDefault();
      $("#person-form").requestSubmit();
    }
  });
  $("#person-form").addEventListener("dragover", (event) => {
    if (preventDemoEdit(event)) return;
    if (!event.dataTransfer?.types?.includes("Files") || personEditor.saving) return;
    event.preventDefault();
    $(".photo-picker").classList.add("is-drop-target");
  });
  $("#person-form").addEventListener("dragleave", (event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) $(".photo-picker").classList.remove("is-drop-target");
  });
  $("#person-form").addEventListener("drop", acceptDroppedPhoto);
  // Stray file drops elsewhere must not navigate away from the atlas.
  document.addEventListener("dragover", (event) => {
    if (event.dataTransfer?.types?.includes("Files")) event.preventDefault();
  });
  document.addEventListener("drop", (event) => {
    if (event.dataTransfer?.types?.includes("Files")) event.preventDefault();
  });
  $("#relationship-form").addEventListener("input", (event) => {
    if (event.target.matches("#parent-label, #child-label")) syncRelationshipFields();
  });
  $("#search-clear").addEventListener("click", () => {
    $("#person-search-input").value = "";
    state.searchActiveIndex = -1;
    $("#person-search-input").focus();
    renderSearchResults();
  });
  $("#retry-load").addEventListener("click", () => {
    loadWorkspace().catch((error) => { showToast(error.message, "error"); render(); });
  });
  document.addEventListener("keydown", handleShortcutKeydown);
  $("#camera-zoom-out").addEventListener("click", () => zoomCamera(1 / 1.2));
  $("#camera-zoom-level").addEventListener("click", resetCamera);
  $("#camera-zoom-in").addEventListener("click", () => zoomCamera(1.2));
  $("#camera-fit").addEventListener("click", fitCamera);
  $("#camera-focus").addEventListener("click", focusCurrentPerson);
  $("#person-search-input").addEventListener("input", () => {
    state.searchActiveIndex = -1;
    renderSearchResults();
  });
  $("#person-search-input").addEventListener("focus", renderSearchResults);
  $("#person-search-input").addEventListener("keydown", handleSearchKeydown);
  $(".person-search").addEventListener("focusout", (event) => {
    if (!event.relatedTarget || !event.currentTarget.contains(event.relatedTarget)) {
      closeSearchResults();
    }
  });
  $("#generation-menu").addEventListener("keydown", (event) => {
    const items = $$("#generation-menu button:not([hidden])");
    const index = items.indexOf(document.activeElement);
    if (event.key === "ArrowDown" && items.length) {
      event.preventDefault();
      items[(index + 1 + items.length) % items.length].focus();
    } else if (event.key === "ArrowUp" && items.length) {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length].focus();
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeGenerationMenu(true);
    }
  });
  $(".generation-menu-wrap").addEventListener("focusout", (event) => {
    if (!event.relatedTarget || !event.currentTarget.contains(event.relatedTarget)) {
      closeGenerationMenu();
    }
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest("#help-toggle,#help-popover")) closeWorkspaceHelp();
    if (!event.target.closest("#workspace-sidebar,#workspace-sidebar-toggle")) closeWorkspaceSidebar();
    if (!event.target.closest(".generation-menu-wrap")) closeGenerationMenu();
    if (!event.target.closest(".person-search")) closeSearchResults();
  });
  document.addEventListener("keydown", async (event) => {
    const typing = event.target.closest("input,textarea,select,[contenteditable=true]");
    if ((event.metaKey || event.ctrlKey) && !event.altKey && !typing && !$("dialog:modal")) {
      const key = event.key.toLowerCase();
      if (key === "z" || (key === "y" && event.ctrlKey)) {
        event.preventDefault();
        await travelHistory(key === "y" || event.shiftKey ? "redo" : "undo");
        return;
      }
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      $("#person-search-input").focus();
      $("#person-search-input").select();
    }
    if (event.key === "Escape") {
      if (event.defaultPrevented || $("dialog:modal")) return;
      if (state.camera.pan || state.camera.spaceHeld || state.navigator.drag) {
        event.preventDefault();
        clearSpacePan();
        clearCameraPan();
        clearNavigatorDrag();
        return;
      }
      if (closeWorkspaceHelp(true) || closeWorkspaceSidebar(true)) {
        event.preventDefault();
        return;
      }
      if ($("#person-dialog").open) {
        event.preventDefault();
        await closePersonDialog();
        return;
      }
      const hadPopover = !$("#generation-menu").hidden || !$("#search-results").hidden;
      closeGenerationMenu(true);
      closeSearchResults();
      if (hadPopover) return;
      if (state.drag || state.camera.pan) {
        event.preventDefault();
        cancelActivePersonDrag();
        clearCameraPan();
        return;
      }
      if (state.linkMode) {
        event.preventDefault();
        if (state.linkSource) {
          state.linkSource = null;
          render();
          showToast("已取消连线起点");
        } else {
          exitLinkMode();
        }
      } else if (state.perspective) {
        event.preventDefault();
        exitPerspective();
        $("#perspective-mode").focus({ preventScroll: true });
      }
    }
  });
  const board = $("#generation-board");
  board.addEventListener("pointerdown", beginSpacePanCapture, true);
  board.addEventListener("click", suppressCameraClick, true);
  board.addEventListener("pointerdown", beginCameraPan);
  board.addEventListener("pointermove", moveCameraPan);
  board.addEventListener("pointerup", endCameraPan);
  board.addEventListener("pointercancel", cancelCameraPan);
  board.addEventListener("lostpointercapture", (event) => {
    if (state.camera.pan?.pointerId === event.pointerId) {
      clearCameraPan(event.pointerId, false);
      clearSpacePan();
    }
  });
  board.addEventListener("wheel", handleCameraWheel, { passive: false });
  document.addEventListener("keydown", handleSpaceKeydown, true);
  document.addEventListener("keyup", handleSpaceKeyup, true);
  $("#navigator-toggle").addEventListener("click", toggleNavigator);
  const navigator = $("#navigator-map");
  navigator.addEventListener("pointerdown", beginNavigatorPointer);
  navigator.addEventListener("pointermove", moveNavigatorPointer);
  navigator.addEventListener("pointerup", endNavigatorPointer);
  navigator.addEventListener("pointercancel", endNavigatorPointer);
  navigator.addEventListener("lostpointercapture", (event) => clearNavigatorDrag(event.pointerId, false));
  navigator.addEventListener("keydown", handleNavigatorKeydown);
  window.addEventListener("blur", () => {
    clearSpacePan();
    clearNavigatorDrag();
    clearCameraPan();
    cancelActivePersonDrag();
  });
  window.addEventListener("resize", handleCameraResize);
  if (typeof ResizeObserver === "function") {
    const viewportObserver = new ResizeObserver(handleCameraResize);
    viewportObserver.observe(board);
    viewportObserver.observe($(".camera-controls"));
    viewportObserver.observe($("#selection-tray"));
    viewportObserver.observe($("#canvas-navigator"));
    new ResizeObserver(() => { requestNavigatorUpdate(true); requestDraw(); }).observe($("#generation-lanes"));
  }
  board.addEventListener("scroll", requestDraw, { passive: true });
}
// Single-key shortcuts stay out of text entry, dialogs and modified key presses.
function handleShortcutKeydown(event) {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.isComposing) return;
  if (event.target.closest?.("input,textarea,select,dialog,[contenteditable=true]") || $("dialog:modal")) return;
  const hasPeople = people().length > 0;
  const shortcuts = {
    "?": () => toggleWorkspaceHelp(event),
    "/": () => { $("#person-search-input").focus(); $("#person-search-input").select(); },
    "+": () => zoomCamera(1.2),
    "=": () => zoomCamera(1.2),
    "-": () => zoomCamera(1 / 1.2),
    "0": resetCamera,
    f: fitCamera,
    v: () => { if (state.linkMode || state.perspective) enterSelectMode(); },
    l: () => { if (hasPeople && !isReadonlyDemo()) toggleLinkMode(); },
    r: () => { if (hasPeople) state.perspective ? exitPerspective() : enterPerspective(); },
  };
  const action = shortcuts[event.key.length === 1 ? event.key.toLowerCase() : ""] || shortcuts[event.key];
  if (!action) return;
  event.preventDefault();
  action();
}
function toggleTheme(event) {
  const next = state.theme === "latte" ? "mocha" : "latte";
  const apply = () => setTheme(next, true);
  if (!document.startViewTransition || matchMedia("(prefers-reduced-motion: reduce)").matches) {
    apply();
    return;
  }
  const rect = event.currentTarget.getBoundingClientRect();
  const x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
  const root = document.documentElement.style;
  root.setProperty("--reveal-x", x + "px");
  root.setProperty("--reveal-y", y + "px");
  root.setProperty("--reveal-r", Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + "px");
  document.startViewTransition(apply);
}
function setTheme(theme, persist = false) {
  state.theme = theme;
  document.body.dataset.theme = theme;
  if (persist) localStorage.setItem(THEME_KEY, theme);
  $("#theme-toggle").setAttribute("aria-label", theme === "latte" ? "切换到深色外观" : "切换到浅色外观");
  const themeColor = $("meta[name=theme-color]");
  if (themeColor) themeColor.content = theme === "latte" ? "#f4f0e8" : "#15130f";
  requestAnimationFrame(drawRelationships);
}
setTheme(state.theme);
bindEvents();
configureReadonlyDemo();
syncRelationshipFields();
loadWorkspace().catch((error) => { showToast(error.message, "error"); render(); });
