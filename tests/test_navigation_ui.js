// Run from the repository root with the macOS JavaScriptCore helper:
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_navigation_ui.js
// Executes the actual application and event bindings against memory-only browser boundaries.
var source = readFile("static/app.js");
var checks = 0, networkCalls = 0, storageWrites = 0, redraws = 0;
var frames = new Map(), nextFrame = 0, clock = 0, reducedMotion = true;
var readCamera = () => ({ x: 0, y: 0, scale: 1 });
var viewportWidth = 1440, modal = null;
var personNodes = [], laneNodes = [], nodes = new Map();
function assert(value, name) { checks += 1; if (!value) throw new Error(name); }
function close(actual, expected, name) { assert(Math.abs(actual - expected) < 0.00001, name + " (" + actual + " vs " + expected + ")"); }
function rect(left, top, width, height) { return { left, top, width, height, right: left + width, bottom: top + height, x: left, y: top }; }
function element(tag = "div", id = "") {
  const classes = new Set(), attrs = {}, listeners = {}, captures = new Set();
  const value = {
    tagName: tag.toUpperCase(), id, children: [], parentElement: null, dataset: {}, style: {},
    hidden: false, open: false, isContentEditable: false, clientWidth: 0, clientHeight: 0,
    scrollWidth: 0, scrollHeight: 0, offsetLeft: 0, offsetTop: 0, offsetWidth: 0, offsetHeight: 0,
    textContent: "", value: "", listeners,
    classList: {
      add: (...items) => items.forEach((item) => classes.add(item)),
      remove: (...items) => items.forEach((item) => classes.delete(item)),
      contains: (name) => classes.has(name),
      toggle(name, force) { const next = force === undefined ? !classes.has(name) : force; next ? classes.add(name) : classes.delete(name); return next; },
    },
    setAttribute(name, value) { attrs[name] = String(value); if (name === "class") String(value).split(/\s+/).forEach((item) => classes.add(item)); },
    getAttribute: (name) => attrs[name] ?? null,
    removeAttribute(name) { delete attrs[name]; },
    append(...items) { items.forEach((item) => { item.parentElement = this; this.children.push(item); }); },
    appendChild(item) { this.append(item); return item; },
    replaceChildren(...items) { this.children = []; this.append(...items); },
    contains(candidate) { return candidate === this || this.children.some((child) => child.contains(candidate)); },
    matches(selector) {
      return selector.split(",").some((part) => {
        part = part.trim();
        if (part === "[contenteditable=true]" || part === '[contenteditable="true"]') return this.isContentEditable;
        if (part === "[contenteditable]") return this.isContentEditable;
        if (part === "[role=button]" || part === '[role="button"]') return this.getAttribute("role") === "button";
        if (part.startsWith("#")) return this.id === part.slice(1);
        if (part.startsWith(".")) return this.classList.contains(part.slice(1));
        return this.tagName.toLowerCase() === part;
      });
    },
    closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; },
    querySelector(selector) { return query(selector, this); },
    querySelectorAll(selector) { return queryAll(selector, this); },
    addEventListener(type, callback, options) { (listeners[type] ||= []).push({ callback, options }); },
    removeEventListener(type, callback) { listeners[type] = (listeners[type] || []).filter((entry) => entry.callback !== callback); },
    setPointerCapture(id) { captures.add(id); },
    hasPointerCapture(id) { return captures.has(id); },
    releasePointerCapture(id) { captures.delete(id); },
    focus() { document.activeElement = this; },
    blur() { if (document.activeElement === this) document.activeElement = document.body; },
    getBoundingClientRect() { return this.measure ? this.measure() : this.rect || rect(0, 0, this.clientWidth, this.clientHeight); },
  };
  Object.defineProperty(value, "className", { get() { return [...classes].join(" "); }, set(text) { classes.clear(); String(text).split(/\s+/).filter(Boolean).forEach((item) => classes.add(item)); } });
  return value;
}
function query(selector, root) {
  if (selector === "dialog:modal") return modal;
  const person = selector.match(/^\.person-node\[data-person-id="([^"]+)"\]$/);
  if (person) return personNodes.find((node) => node.dataset.personId === person[1]) || null;
  const lane = selector.match(/^\.generation-lane\[data-generation-id="([^"]+)"\]$/);
  if (lane) return laneNodes.find((node) => node.dataset.generationId === lane[1]) || null;
  if (!nodes.has(selector)) nodes.set(selector, element(selector.includes("dialog") ? "dialog" : "div", selector.startsWith("#") ? selector.slice(1) : ""));
  return nodes.get(selector);
}
function queryAll(selector, root) {
  if (selector === ".person-node") return personNodes;
  if (selector === ".generation-lane") return laneNodes;
  if (selector === "#navigator-people rect") return query("#navigator-people").children;
  if (root && root !== document) return root.children.filter((child) => child.matches(selector));
  return [];
}
var document = element("document");
document.body = element("body");
document.activeElement = document.body;
document.querySelector = query;
document.querySelectorAll = queryAll;
document.createElement = element;
document.createElementNS = (_, tag) => element(tag);
var window = element("window");
window.innerWidth = viewportWidth;
var localStorage = { getItem: () => null, setItem() { storageWrites += 1; } };
var CSS = { escape: (value) => String(value) };
function matchMedia(query) {
  if (query.includes("prefers-reduced-motion")) return { matches: reducedMotion };
  const max = query.match(/max-width:\s*(\d+)px/);
  const min = query.match(/min-width:\s*(\d+)px/);
  return { matches: max ? viewportWidth <= Number(max[1]) : min ? viewportWidth >= Number(min[1]) : false };
}
function getComputedStyle(node) { return { transform: "none", display: node.hidden ? "none" : "block", visibility: "visible" }; }
function requestAnimationFrame(callback) { const id = ++nextFrame; frames.set(id, callback); return id; }
function cancelAnimationFrame(id) { frames.delete(id); }
function tick() { clock += 16.667; const pending = [...frames.values()]; frames.clear(); pending.forEach((callback) => callback(clock)); }
function settle() { for (let n = 0; frames.size && n < 300; n += 1) tick(); assert(!frames.size, "scheduled navigation work settles"); }
function fetch() { networkCalls += 1; throw new Error("Navigation must not request the server"); }
function event(target, changes = {}) {
  return {
    target, currentTarget: target, type: "", key: "", code: "", button: 0, isPrimary: true,
    pointerId: 1, clientX: 300, clientY: 220, timeStamp: clock, defaultPrevented: false,
    propagationStopped: false, immediateStopped: false, shiftKey: false, ctrlKey: false, metaKey: false, altKey: false,
    preventDefault() { this.defaultPrevented = true; },
    stopPropagation() { this.propagationStopped = true; },
    stopImmediatePropagation() { this.immediateStopped = true; this.propagationStopped = true; },
    ...changes,
  };
}
function emit(target, type, value) {
  value.currentTarget = target; value.type = type;
  const entries = [...(target.listeners[type] || [])].sort((a, b) => Number(b.options === true || b.options?.capture) - Number(a.options === true || a.options?.capture));
  for (const entry of entries) { entry.callback(value); if (value.immediateStopped) break; }
  drainMicrotasks();
}
function runNavigationTests() {
  readCamera = () => state.camera;
  requestDraw = () => { redraws += 1; };
  renderWorkspaceChrome = () => {};
  syncWorkspaceSidebar = () => {};
  const board = $("#generation-board"), stage = $("#canvas-stage"), lanes = $("#generation-lanes");
  board.clientWidth = 1000; board.clientHeight = 700; board.rect = rect(100, 80, 1000, 700);
  const stageBase = { x: 12, y: 18 };
  stage.measure = () => rect(board.rect.left + stageBase.x + state.camera.x, board.rect.top + stageBase.y + state.camera.y, lanes.scrollWidth * state.camera.scale, lanes.scrollHeight * state.camera.scale);
  lanes.measure = () => stage.getBoundingClientRect();
  $("#person-dialog").open = false;
  $("#selection-tray").hidden = true;
  $(".selection-tray").hidden = true;
  $(".camera-controls").rect = rect(760, 700, 310, 52);
  function camera(x, y, scale) { Object.assign(state.camera, { x, y, scale }); applyCamera(); }
  function worldCenter() { const area = getCameraViewport(), view = cameraViewportWorld(area); return { x: view.left + view.width / 2, y: view.top + view.height / 2 }; }
  function expectCenter(before, name) { const after = worldCenter(); close(after.x, before.x, name + " x"); close(after.y, before.y, name + " y"); }
  function setGeometry(width, height) {
    lanes.scrollWidth = width; lanes.scrollHeight = height;
    lanes.offsetWidth = width; lanes.offsetHeight = height;
  }
  const workspace = {
    generations: [{ id: "one", name: "一代", position: 0 }, { id: "two", name: "二代", position: 1 }],
    people: { a: { id: "a", name: "甲", generation_id: "one", order: 0 }, b: { id: "b", name: "乙", generation_id: "two", order: 0 } },
    relationships: [{ id: "r", parent_id: "a", child_id: "b" }],
  };
  state.workspace = workspace;
  state.history = { undo_label: "编辑人物", redo_label: "移动人物" };
  const dataBefore = JSON.stringify(state.workspace), historyBefore = JSON.stringify(state.history);

  const area = { left: 20, top: 30, width: 600, height: 400, baseX: 12, baseY: 18 };
  close(fitBoundsScale({ width: 10000, height: 400 }, area), 0.0568, "ultrawide fit is allowed below 20 percent");
  close(fitBoundsScale({ width: 20, height: 20 }, area), 2.25, "small diagram fit keeps the 225 percent upper limit");
  const centerCamera = cameraForWorldCenter(1000, 900, 0.5, area);
  const visibleWorld = cameraViewportWorld(area, centerCamera);
  close(visibleWorld.left + visibleWorld.width / 2, 1000, "world centering honors viewport and stage horizontal offsets");
  close(visibleWorld.top + visibleWorld.height / 2, 900, "world centering honors viewport and stage vertical offsets");

  setGeometry(1200, 600); camera(-200, 45, 0.7);
  fitCamera(); settle();
  let visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.top <= 0 && visible.left + visible.width >= 1200 && visible.top + visible.height >= 600, "ordinary overview contains every content boundary");
  setGeometry(12000, 800); fitCamera(); settle();
  assert(state.camera.scale < 0.2, "actual overview reaches below the old zoom floor");
  visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.left + visible.width >= 12000, "ultrawide overview includes both ends");
  fitReadableCamera(); settle();
  assert(state.camera.scale >= 0.75, "initial view preserves readable names");

  camera(-700, -230, 0.33);
  const beforeReset = worldCenter();
  resetCamera(); settle();
  close(state.camera.scale, 1, "zoom-label action restores 100 percent");
  expectCenter(beforeReset, "100 percent reset preserves visible world center");
  const pointer = { x: board.rect.left + 367, y: board.rect.top + 211 };
  const current = getCameraViewport();
  const anchoredWorld = {
    x: (pointer.x - board.rect.left - current.baseX - state.camera.x) / state.camera.scale,
    y: (pointer.y - board.rect.top - current.baseY - state.camera.y) / state.camera.scale,
  };
  setCameraScale(1.8, pointer.x, pointer.y); settle();
  close(board.rect.left + current.baseX + state.camera.x + anchoredWorld.x * state.camera.scale, pointer.x, "zoom retains horizontal pointer anchor");
  close(board.rect.top + current.baseY + state.camera.y + anchoredWorld.y * state.camera.scale, pointer.y, "zoom retains vertical pointer anchor");

  state.workspace = { generations: [], people: {}, relationships: [] }; setGeometry(0, 0);
  fitCamera(); settle();
  assert(Number.isFinite(state.camera.x) && Number.isFinite(state.camera.y) && state.camera.scale === 1, "empty overview has a finite readable camera");
  state.workspace = workspace; setGeometry(1200, 600);


  // Panel and dock geometry constrain the same region used by overview and reset.
  camera(-320, -180, 0.65); settle();
  const fullArea = getCameraViewport();
  $("#person-dialog").rect = rect(800, 130, 280, 580); $("#person-dialog").open = true;
  const panelArea = getCameraViewport();
  assert(panelArea.width < fullArea.width && panelArea.width <= 684, "inspector reserves its overlapping horizontal area");
  $("#selection-tray").hidden = false; $("#selection-tray").rect = rect(260, 605, 510, 105);
  const dockArea = getCameraViewport();
  assert(dockArea.height <= 509, "relationship dock reserves its overlapping vertical area");
  fitCamera(); settle(); visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.top <= 0 && visible.left + visible.width >= 1200 && visible.top + visible.height >= 600, "overview remains complete with inspector and relationship tray");
  const panelCenter = worldCenter(); resetCamera(); settle();
  expectCenter(panelCenter, "100 percent reset honors the unobstructed viewport center");
  const preResize = worldCenter();
  board.clientWidth = 800; board.clientHeight = 600; board.rect = rect(100, 80, 800, 600);
  handleCameraResize(); handleCameraResize(); settle();
  expectCenter(preResize, "resizing preserves world center");
  $("#person-dialog").open = false; $("#selection-tray").hidden = true;
  board.clientWidth = 1000; board.clientHeight = 700; board.rect = rect(100, 80, 1000, 700);
  handleCameraResize(); settle();


  const navigatorPanel = $("#canvas-navigator");
  const beforeNavigatorResize = worldCenter();
  navigatorPanel.rect = rect(760, 500, 222, 196);
  handleCameraResize(); settle();
  assert(getCameraViewport().height <= 408, "expanded desktop navigator is excluded from the usable canvas");
  expectCenter(beforeNavigatorResize, "expanding navigator preserves world center");
  fitCamera(); settle(); visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.top <= 0 && visible.left + visible.width >= 1200 && visible.top + visible.height >= 600, "overview clears expanded navigator as well as toolbar");

  setGeometry(500, 2000);
  const tallArea = getCameraViewport();
  assert(tallArea.width === 648 && tallArea.height === 604, "tall content chooses the taller area beside the corner navigator");
  fitCamera(); settle(); visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.top <= 0 && visible.left + visible.width >= 500 && visible.top + visible.height >= 2000, "tall overview fits completely beside the navigator");
  for (const scale of [0.08, 0.82, 2.25]) {
    camera(-350, -210, scale);
    const stableArea = getCameraViewport();
    assert(stableArea.width === tallArea.width && stableArea.height === tallArea.height, "tall-content avoidance stays stable at camera scale " + scale);
  }
  setGeometry(10000, 100);
  const wideArea = getCameraViewport();
  assert(wideArea.width === 1000 && wideArea.height === 408, "wide content chooses the wider area above the corner navigator");
  fitCamera(); settle(); visible = cameraViewportWorld(getCameraViewport());
  assert(visible.left <= 0 && visible.top <= 0 && visible.left + visible.width >= 10000 && visible.top + visible.height >= 100, "wide overview fits completely above the navigator");
  for (const scale of [0.08, 0.82, 2.25]) {
    camera(-350, -210, scale);
    const stableArea = getCameraViewport();
    assert(stableArea.width === wideArea.width && stableArea.height === wideArea.height, "wide-content avoidance stays stable at camera scale " + scale);
  }
  setGeometry(1200, 600); settle();

  $("#person-dialog").open = true; navigatorPanel.rect = rect(560, 500, 222, 196);
  assert(getCameraViewport().height <= 408 && getCameraViewport().width <= 684, "inspector and navigator jointly constrain overview");
  $("#person-dialog").open = false;
  const expandedHeight = getCameraViewport().height;
  navigatorPanel.rect = rect(760, 644, 222, 52);
  assert(getCameraViewport().height > expandedHeight && getCameraViewport().height <= 604, "collapsed navigator title gives back canvas height while retaining dock clearance");
  navigatorPanel.rect = rect(760, 500, 222, 196);
  viewportWidth = 900; window.innerWidth = 900;
  assert(getCameraViewport().height > expandedHeight, "narrow layout ignores the CSS-hidden navigator rectangle");
  viewportWidth = 1440; window.innerWidth = 1440;
  navigatorPanel.rect = rect(0, 0, 0, 0); handleCameraResize(); settle();

  function worldNode(id, box) {
    const node = element("article"); node.classList.add("person-node"); node.dataset.personId = id;
    node.setAttribute("role", "button"); node.parentElement = board;
    node.measure = () => { const position = stage.getBoundingClientRect(); return rect(position.left + box.left * state.camera.scale, position.top + box.top * state.camera.scale, box.width * state.camera.scale, box.height * state.camera.scale); };
    return node;
  }
  const personA = worldNode("a", { left: 150, top: 120, width: 130, height: 80 });
  const personB = worldNode("b", { left: 780, top: 390, width: 130, height: 80 });
  personNodes = [personA, personB];
  camera(0, 0, 0.1); settle();
  assert(focusPersonInCanvas("a"), "person focus resolves an existing person");
  settle(); close(state.camera.scale, 0.82, "person focus restores the minimum readable 82 percent");
  close(worldCenter().x, 215, "person focus centers its world horizontal coordinate");
  close(worldCenter().y, 160, "person focus centers its world vertical coordinate");

  const svg = $("#navigator-map"), indicator = $("#navigator-viewport");
  svg.rect = rect(860, 530, 200, 120); svg.classList.add("canvas-navigator"); svg.parentElement = board;
  indicator.parentElement = svg;
  state.focusedPersonId = "a"; state.selectionA = "a"; state.selectionB = "b";
  requestNavigatorUpdate(true); settle();
  assert($("#navigator-people").children.length === 2 && $("#navigator-edges").children.length === 1, "navigator draws people and existing relationship edges");
  assert($("#navigator-people").children[0].classList.contains("is-selected") && $("#navigator-people").children[1].classList.contains("is-selection-b"), "navigator reflects focused and A/B selected people");
  assert($("#navigator-people").children.every((marker) => !marker.textContent && marker.children.length === 0), "navigator markers omit person names and photos");
  const map = state.navigator.map;
  close(Number($("#navigator-people").children[0].getAttribute("x")) + Number($("#navigator-people").children[0].getAttribute("width")) / 2, map.x + 215 * map.scale, "navigator person markers use world coordinates");
  const oldMarkers = [...$("#navigator-people").children];
  const oldIndicator = indicator.getAttribute("x");
  state.camera.x -= 500; applyCamera(); applyCamera(); applyCamera();
  assert(frames.size === 1, "repeated camera paints coalesce navigator work into one frame");
  settle();
  assert($("#navigator-people").children[0] === oldMarkers[0] && indicator.getAttribute("x") !== oldIndicator, "camera movement updates viewport without rebuilding geometry");
  requestNavigatorUpdate(true); settle();
  assert($("#navigator-people").children[0] !== oldMarkers[0], "layout update refreshes navigator geometry");

  bindEvents();
  const downCapture = board.listeners.pointerdown.find((entry) => entry.callback === beginSpacePanCapture);
  assert(downCapture?.options === true, "Space panning intercepts pointerdown in capture phase");
  assert(board.listeners.click.some((entry) => entry.callback === suppressCameraClick && entry.options === true), "post-pan clicks are suppressed before person and relationship activation");
  const scaleBeforeNav = state.camera.scale;
  const requestedWorld = { x: 740, y: 420 };
  const mapDown = event(svg, { pointerId: 21, clientX: svg.rect.left + map.x + requestedWorld.x * map.scale, clientY: svg.rect.top + map.y + requestedWorld.y * map.scale });
  emit(svg, "pointerdown", mapDown); settle();
  close(worldCenter().x, requestedWorld.x, "navigator click centers the requested horizontal world coordinate");
  close(worldCenter().y, requestedWorld.y, "navigator click centers the requested vertical world coordinate");
  close(state.camera.scale, scaleBeforeNav, "navigator click preserves zoom");
  assert(document.activeElement === svg && svg.hasPointerCapture(21), "navigator pointer action takes keyboard focus and pointer capture");
  emit(svg, "pointerup", event(svg, { pointerId: 21 }));
  assert(!state.navigator.drag && !svg.hasPointerCapture(21), "navigator release clears drag and pointer capture");

  const dragOrigin = { x: state.camera.x, y: state.camera.y };
  emit(svg, "pointerdown", event(indicator, { pointerId: 22, clientX: 920, clientY: 575 }));
  close(state.camera.x, dragOrigin.x, "grabbing navigator viewport does not jump the camera");
  emit(svg, "pointermove", event(indicator, { pointerId: 99, clientX: 935, clientY: 585 }));
  close(state.camera.x, dragOrigin.x, "another pointer cannot move a navigator drag");
  emit(svg, "pointermove", event(indicator, { pointerId: 22, clientX: 935, clientY: 585 }));
  close(state.camera.x, dragOrigin.x - 15 / map.scale * scaleBeforeNav, "navigator viewport horizontal drag maps to camera motion");
  close(state.camera.y, dragOrigin.y - 10 / map.scale * scaleBeforeNav, "navigator viewport vertical drag maps to camera motion");
  emit(svg, "pointercancel", event(svg, { pointerId: 22 }));
  assert(!state.navigator.drag && !svg.hasPointerCapture(22), "navigator cancellation clears drag capture");
  for (const [key, dx, dy] of [["ArrowRight", 1, 0], ["ArrowLeft", -1, 0], ["ArrowUp", 0, -1], ["ArrowDown", 0, 1]]) {
    const before = worldCenter(), world = cameraViewportWorld(getCameraViewport());
    const arrow = event(svg, { key }); emit(svg, "keydown", arrow);
    close(worldCenter().x - before.x, dx * world.width * 0.1, key + " pans 10 percent horizontally");
    close(worldCenter().y - before.y, dy * world.height * 0.1, key + " pans 10 percent vertically");
    assert(arrow.defaultPrevented && arrow.propagationStopped, key + " prevents page scrolling");
  }
  close(state.camera.scale, scaleBeforeNav, "navigator dragging and keyboard panning preserve zoom");
  emit($("#navigator-toggle"), "click", event($("#navigator-toggle")));
  assert(state.navigator.collapsed && $("#navigator-content").hidden && $("#navigator-toggle").getAttribute("aria-expanded") === "false", "navigator collapse updates visibility and accessible expanded state");
  emit($("#navigator-toggle"), "click", event($("#navigator-toggle"))); settle();
  assert(!state.navigator.collapsed && !$("#navigator-content").hidden && $("#navigator-toggle").getAttribute("aria-expanded") === "true", "navigator expands again without persistence");
  viewportWidth = 900; window.innerWidth = 900;
  const desktopMarkers = [...$("#navigator-people").children];
  requestNavigatorUpdate(true); settle();
  assert(state.navigator.geometryDirty && $("#navigator-people").children[0] === desktopMarkers[0], "900px narrow layout defers hidden navigator geometry");
  viewportWidth = 1440; window.innerWidth = 1440;
  requestNavigatorUpdate(); settle();
  assert(!state.navigator.geometryDirty, "desktop return refreshes deferred navigator geometry");

  // Real bound handlers run in capture-before-bubble order.
  function pressSpace(target = document.body) { const press = event(target, { key: " ", code: "Space" }); emit(document, "keydown", press); return press; }
  function releaseSpace() { emit(document, "keyup", event(document.body, { key: " ", code: "Space" })); }
  for (const target of [element("input"), element("textarea"), element("select"), element("button"), element("dialog"), svg]) {
    const press = pressSpace(target);
    assert(!press.defaultPrevented && !state.camera.spaceHeld, target.tagName + " keeps its native Space action");
  }
  const editable = element(); editable.isContentEditable = true;
  assert(!pressSpace(editable).defaultPrevented && !state.camera.spaceHeld, "editable content retains Space typing");
  modal = element("dialog"); assert(!pressSpace().defaultPrevented && !state.camera.spaceHeld, "modal dialogs disable global Space panning"); modal = null;
  const relationship = element("path"); relationship.classList.add("relationship-hit"); relationship.setAttribute("role", "button"); relationship.parentElement = board;
  const selectionBefore = JSON.stringify({ a: state.selectionA, b: state.selectionB, focus: state.focusedPersonId, link: state.linkSource });
  for (const [index, target] of [board, personA, relationship].entries()) {
    const id = 30 + index, before = { x: state.camera.x, y: state.camera.y };
    const press = pressSpace(target);
    assert(press.defaultPrevented && state.camera.spaceHeld, "Space enables pan from canvas/person/relationship target " + index);
    const down = event(target, { pointerId: id, clientX: 400, clientY: 300 });
    emit(board, "pointerdown", down);
    assert(down.immediateStopped && state.camera.pan?.space && !state.drag, "Space pointer capture prevents edit entry for target " + index);
    emit(board, "pointermove", event(target, { pointerId: id, clientX: 445, clientY: 330 }));
    close(state.camera.x, before.x + 45, "Space pan moves horizontal camera for target " + index);
    close(state.camera.y, before.y + 30, "Space pan moves vertical camera for target " + index);
    emit(board, "pointerup", event(target, { pointerId: id }));
    const click = event(target, { pointerId: id, detail: 1 }); emit(board, "click", click);
    assert(click.immediateStopped && click.defaultPrevented, "Space pan suppresses subsequent activation for target " + index);
    releaseSpace();
    assert(!state.camera.pan && !state.camera.spaceHeld && !board.hasPointerCapture(id), "Space gesture leaves no capture or mode for target " + index);
  }
  assert(JSON.stringify({ a: state.selectionA, b: state.selectionB, focus: state.focusedPersonId, link: state.linkSource }) === selectionBefore, "Space navigation preserves A/B, selected person and relationship source");

  pressSpace(); const buttonDown = event(element("button"), { pointerId: 40 }); emit(board, "pointerdown", buttonDown);
  assert(!buttonDown.defaultPrevented && !state.camera.pan, "holding Space does not steal button pointer interaction"); releaseSpace();
  beginPersonPointer(event(personA, { currentTarget: personA, pointerId: 41 }));
  const activeDrag = state.drag;
  const midDrag = pressSpace(personA);
  assert(state.drag === activeDrag && !state.camera.spaceHeld && midDrag.defaultPrevented && !state.camera.pan, "Space never converts an already started person drag");
  cancelActivePersonDrag();
  for (const ending of ["keyup", "pointercancel", "lostpointercapture", "blur", "Escape"]) {
    pressSpace(); emit(board, "pointerdown", event(personA, { pointerId: 50 }));
    if (ending === "keyup") releaseSpace();
    else if (ending === "blur") emit(window, "blur", event(window));
    else if (ending === "Escape") emit(document, "keydown", event(document.body, { key: "Escape" }));
    else { if (ending === "lostpointercapture") board.releasePointerCapture(50); emit(board, ending, event(board, { pointerId: 50 })); }
    assert(!state.camera.spaceHeld && !state.camera.pan && !board.classList.contains("is-space-panning") && !board.classList.contains("is-panning") && !board.hasPointerCapture(50), ending + " clears Space camera state");
  }
  emit(svg, "pointerdown", event(indicator, { pointerId: 60, clientX: 920, clientY: 575 }));
  emit(window, "blur", event(window));
  assert(!state.navigator.drag && !svg.hasPointerCapture(60), "window blur clears navigator capture");
  reducedMotion = false; camera(0, 0, 0.82); settle();
  resetCamera(); tick(); const intermediate = { x: state.camera.x, y: state.camera.y, scale: state.camera.scale };
  emit(board, "pointerdown", event(board, { pointerId: 70, clientX: 400, clientY: 300 }));
  settle();
  assert(!cameraMotion.running && state.camera.x === intermediate.x && state.camera.scale === intermediate.scale, "manual pan interrupts an in-flight reset at its current presentation");
  emit(board, "pointerup", event(board, { pointerId: 70 })); reducedMotion = true;
  settle();


  camera(-340, -110, 0.6); settle();
  const wheelPointer = { x: board.rect.left + 420, y: board.rect.top + 260 };
  const wheelViewport = getCameraViewport();
  const wheelWorld = { x: (420 - wheelViewport.baseX - state.camera.x) / state.camera.scale, y: (260 - wheelViewport.baseY - state.camera.y) / state.camera.scale };
  const wheel = event(board, { clientX: wheelPointer.x, clientY: wheelPointer.y, deltaX: 0, deltaY: -40, deltaMode: 0 });
  emit(board, "wheel", wheel); settle();
  assert(wheel.defaultPrevented && state.camera.scale > 0.6, "bound wheel handler performs anchored zoom and stops page scroll");
  close(board.rect.left + wheelViewport.baseX + state.camera.x + wheelWorld.x * state.camera.scale, wheelPointer.x, "wheel entry keeps horizontal pointer anchor");
  close(board.rect.top + wheelViewport.baseY + state.camera.y + wheelWorld.y * state.camera.scale, wheelPointer.y, "wheel entry keeps vertical pointer anchor");
  const beforeBlockedWheel = state.camera.scale;
  const navigatorWheel = event(svg, { clientX: wheelPointer.x, clientY: wheelPointer.y, deltaX: 0, deltaY: -40, deltaMode: 0 });
  emit(board, "wheel", navigatorWheel);
  assert(!navigatorWheel.defaultPrevented && state.camera.scale === beforeBlockedWheel, "navigator wheel does not leak into main canvas zoom");
  emit(svg, "pointerdown", event(indicator, { pointerId: 71, clientX: 920, clientY: 575 }));
  emit($("#navigator-toggle"), "click", event($("#navigator-toggle")));
  assert(!state.navigator.drag && !svg.hasPointerCapture(71), "collapsing navigator releases an active pointer drag");
  emit($("#navigator-toggle"), "click", event($("#navigator-toggle"))); settle();


  // Undo/reorder FLIP offsets can temporarily enlarge scrollWidth after layout.
  reducedMotion = false; settle();
  const settledWidth = lanes.scrollWidth;
  Object.defineProperty(lanes, "scrollWidth", {
    configurable: true,
    get() { return personNodes.some((node) => Boolean(node.style.transform)) ? 1500 : settledWidth; },
  });
  const beforeLayout = captureNodePositions();
  beforeLayout.set("a", { ...beforeLayout.get("a"), left: beforeLayout.get("a").left + 500 });
  beforeLayout.set("b", { ...beforeLayout.get("b"), left: beforeLayout.get("b").left + 150 });
  const realUpdateGeometry = updateNavigatorGeometry;
  let animationGeometryUpdates = 0;
  updateNavigatorGeometry = () => { animationGeometryUpdates += 1; realUpdateGeometry(); };
  animateNodesFrom(beforeLayout);
  requestNavigatorUpdate(true); tick();
  assert(nodeMotions.size === 2 && lanes.scrollWidth === 1500, "FLIP animation exposes temporary visual overflow in layout measurements");
  close(state.navigator.map.scale, 184 / 1500, "navigator can initially observe temporary animated overflow");
  const animatedMarker = $("#navigator-people").children[0];
  const updatesDuringAnimation = animationGeometryUpdates;
  settle();
  assert(!nodeMotions.size && lanes.scrollWidth === settledWidth, "all node animations finish and release temporary overflow");
  close(state.navigator.map.scale, 184 / settledWidth, "navigator remeasures final layout width after every node settles");
  close(Number($("#navigator-people").children[0].getAttribute("width")), 130 * 184 / settledWidth, "settled person marker uses final layout scale instead of stale overflow scale");
  assert($("#navigator-people").children[0] !== animatedMarker, "settled layout replaces navigator geometry observed during animation");
  assert(animationGeometryUpdates === updatesDuringAnimation + 1, "all FLIP completions schedule one final geometry refresh");
  updateNavigatorGeometry = realUpdateGeometry;
  Object.defineProperty(lanes, "scrollWidth", { value: settledWidth, writable: true, configurable: true });
  reducedMotion = true;

  assert(JSON.stringify(state.workspace) === dataBefore, "camera navigation preserves people, generations and relationships");
  assert(JSON.stringify(state.history) === historyBefore, "camera navigation preserves undo and redo history");
  assert(networkCalls === 0 && storageWrites === 0, "camera navigation has no network or persistence writes");
  print("PASS " + checks + " navigation UI assertions (remote JSC, memory-only)");
}
const startup = source.lastIndexOf("\nsetTheme(state.theme);");
if (startup < 0) throw new Error("Application startup boundary changed");
eval(readFile("static/motion.js") + "\n" + source.slice(0, startup) + "\n(" + runNavigationTests.toString() + ")();");
