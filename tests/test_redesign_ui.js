// Run from the repository root:
// /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_redesign_ui.js
// Exercises the redesigned interaction helpers with the real app.js functions and memory-only boundaries.
var source = readFile("static/app.js");
var checks = 0;
function assert(value, name) { checks += 1; if (!value) throw new Error(name); }
function extract(startMarker, endMarker) {
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error("Function boundary changed: " + startMarker);
  return source.slice(start, end);
}
function element(tag = "div") {
  const classes = new Set(), attributes = {};
  return {
    tagName: tag.toUpperCase(), children: [], dataset: {}, style: {}, textContent: "", listeners: {}, open: false,
    classList: {
      add: (...items) => items.forEach((item) => classes.add(item)),
      remove: (...items) => items.forEach((item) => classes.delete(item)),
      contains: (item) => classes.has(item),
      toggle(item, force) { const next = force === undefined ? !classes.has(item) : force; next ? classes.add(item) : classes.delete(item); return next; },
    },
    setAttribute(name, value) { attributes[name] = String(value); },
    getAttribute: (name) => attributes[name] ?? null,
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    addEventListener(name, callback) { this.listeners[name] = callback; },
  };
}
function text(node) {
  if (typeof node === "string") return node;
  return node.children.length ? node.children.map(text).join("") : node.textContent;
}
var document = { body: element("body"), activeElement: null, createElement: element };
var nodes = new Map();
function $(selector) {
  if (selector === "dialog:modal") return null;
  if (!nodes.has(selector)) nodes.set(selector, element());
  return nodes.get(selector);
}
function $$() { return []; }
var CSS = { escape: (value) => value };
var timers = [];
function setTimeout(callback, delay) { timers.push(delay); return timers.length; }
function clearTimeout() {}
var calls = [];
function record(name) { return () => calls.push(name); }
var fitCamera = record("fit"), resetCamera = record("reset"), toggleLinkMode = record("link");
var enterPerspective = record("perspective"), exitPerspective = record("exit-perspective");
var enterSelectMode = record("select"), toggleWorkspaceHelp = record("help");
function zoomCamera(multiplier) { calls.push(multiplier > 1 ? "zoom-in" : "zoom-out"); }
function travelHistory(direction) { calls.push("history-" + direction); }
function beginPersonPointer() {}
function setActiveRelationshipPerson() {}
function clearActiveRelationshipPerson() {}
function activatePerson() {}

var state = {
  workspace: {
    generations: [{ id: "g1", name: "祖辈", position: 0 }, { id: "g2", name: "父辈", position: 1 }, { id: "g3", name: "同辈", position: 2 }],
    people: {
      f: { id: "f", name: "陈父", gender: "male", generation_id: "g1", order: 0 },
      m: { id: "m", name: "林母", gender: "female", generation_id: "g1", order: 1 },
      s: { id: "s", name: "陈子", gender: "male", generation_id: "g2", order: 0 },
      d: { id: "d", name: "陈女", gender: "female", generation_id: "g2", order: 1 },
      e: { id: "e", name: "陈旧", gender: "female", generation_id: "g2", order: 2 },
      x: { id: "x", name: "无名", gender: "", generation_id: "g2", order: 3 },
      c: { id: "c", name: "陈孙", gender: "female", generation_id: "g3", order: 0 },
    },
    relationships: [
      { id: "r1", parent_id: "f", child_id: "s", kind: "standard", code: "father_son", parent_label: "爸爸", child_label: "儿子" },
      { id: "r2", parent_id: "m", child_id: "s", kind: "standard", code: "mother_son", parent_label: "妈妈", child_label: "儿子" },
      { id: "r3", parent_id: "m", child_id: "d", kind: "standard", code: "mother_daughter", parent_label: "妈妈", child_label: "女儿" },
      { id: "r4", parent_id: "s", child_id: "c", kind: "special", code: "special", parent_label: "养父", child_label: "养女" },
      { id: "r5", parent_id: "f", child_id: "e" },
    ],
  },
  camera: { scale: 1 }, perspective: false, linkMode: false, linkSource: null,
  selectionA: null, selectionB: null, focusedPersonId: null, editingPersonId: null,
  focusedRelationshipId: null, activeRelationshipId: null, activeRelationshipPersonId: null,
  relationshipPathLoading: false, relationshipPathError: null, relationshipCopyText: null, relationshipPath: null,
};

eval(extract("function createIcon(", "async function api("));
eval(extract("function hideToast(", "function workspaceFrom("));
eval(extract("function generations()", "async function loadWorkspace("));
eval(extract("function createPersonNode(", "function openGenerationDialog("));
eval(extract("function personRelatives(", "function createRelativeItem("));
eval(extract("function canLinkPeople(", "function markLinkCandidates("));
eval(extract("function relationshipRoles(", "function setActiveRelationship("));
eval(extract("function relationshipPathData(", "function drawRelationships("));
eval(extract("function relationshipKindKey(", "let relationshipSaving"));
eval(extract("function renderSelectionResult(", "function relationshipPathText("));
eval(extract("function handleShortcutKeydown(", "function toggleTheme("));

// Rounded connectors keep their exact endpoints and fall back to square routing when there is no room.
const straight = relationshipPathData({ x1: 10, y1: 0, x2: 10, y2: 100, channelY: 50 });
assert(straight === "M 10 0 V 50 H 10 V 100", "vertical connectors stay straight");
const rounded = relationshipPathData({ x1: 0, y1: 0, x2: 80, y2: 100, channelY: 50 });
assert(rounded.startsWith("M 0 0 V 40 Q 0 50 10 50") && rounded.endsWith("Q 80 50 80 60 V 100"), "wide connectors get 10px rounded elbows");
const leftward = relationshipPathData({ x1: 80, y1: 0, x2: 0, y2: 100, channelY: 50 });
assert(leftward.includes("Q 80 50 70 50") && leftward.endsWith("V 100"), "leftward connectors bend toward the child");
const tight = relationshipPathData({ x1: 0, y1: 0, x2: 6, y2: 100, channelY: 50 });
assert(tight.includes("Q 0 50 3 50"), "narrow offsets clamp the corner radius to half the run");
assert(!relationshipPathData({ x1: 0, y1: 49.5, x2: 40, y2: 100, channelY: 50 }).includes("Q"), "channels hugging a card fall back to square corners");

// Link candidates follow the backend rules: adjacent generations, known genders and no duplicate edge.
assert(canLinkPeople("f", "d"), "adjacent unrelated people with genders can be linked");
assert(!canLinkPeople("f", "s"), "an existing relationship is not offered again");
assert(!canLinkPeople("s", "d"), "people in the same generation cannot be linked");
assert(!canLinkPeople("f", "c"), "non-adjacent generations cannot be linked");
assert(!canLinkPeople("x", "f") && !canLinkPeople("f", "x"), "people without a gender cannot be linked");
assert(!canLinkPeople("s", "s"), "a person cannot be linked to themselves");

// Relatives are labelled from the inspected person's point of view.
const sonRelatives = personRelatives("s");
assert(sonRelatives.length === 3, "relatives include both parents and children");
assert(sonRelatives.some((item) => item.person.id === "f" && item.side === "parent" && item.role === "爸爸" && item.kind === "father_son"), "father keeps the stored parent title");
assert(sonRelatives.some((item) => item.person.id === "c" && item.side === "child" && item.role === "养女" && item.kind === "special"), "special children use the custom child title");
assert(personRelatives("e")[0].role === "父亲", "legacy edges without labels fall back to a gendered title");

// Hover roles: one line labels both ends, one person labels every relative.
state.focusedRelationshipId = "r1";
let roles = relationshipRoles();
assert(roles.length === 2 && roles[0].personId === "f" && roles[0].role === "爸爸" && roles[0].edge === "bottom" &&
  roles[1].personId === "s" && roles[1].role === "儿子" && roles[1].edge === "top", "a focused line labels parent and child ends");
state.focusedRelationshipId = null;
state.activeRelationshipPersonId = "s";
roles = relationshipRoles();
assert(roles.length === 3 && roles.find((item) => item.personId === "m").role === "妈妈" &&
  roles.find((item) => item.personId === "c").edge === "top", "a hovered person labels parents below and children above");
state.perspective = true; state.selectionA = "c"; state.selectionB = "f";
assert(relationshipRoles().length === 0, "a completed A/B path shows the chain instead of per-card roles");
state.perspective = false; state.selectionA = null; state.selectionB = null; state.activeRelationshipPersonId = null;
assert(relationshipRoles().length === 0, "no hover means no role badges");

// The kinship chain is rebuilt from the server path so custom labels survive intact.
assert(JSON.stringify(relationshipPathLabels({ person_ids: ["c", "s", "f"], relationship_ids: ["r4", "r1"] }, "养父的爸爸")) ===
  JSON.stringify(["养父", "爸爸"]), "path labels follow each step's direction");
assert(JSON.stringify(relationshipPathLabels({ person_ids: [], relationship_ids: ["missing"] }, "妈妈的儿子")) ===
  JSON.stringify(["妈妈", "儿子"]), "unknown relationship ids fall back to the path text");

state.selectionA = "c"; state.selectionB = "f"; state.relationshipCopyText = "陈父 是 陈孙 的：养父的爸爸";
state.relationshipPath = { labels: ["养父", "爸爸"] };
renderSelectionResult(true);
const result = $("#selection-result");
assert(result.dataset.state === "ready" && result.children.length === 2, "a ready path renders a lead line and a chain");
assert(text(result.children[0]) === "陈父 是 陈孙 的", "the lead names B before A");
assert(result.children[1].children.map(text).join("|") === "养父|的|爸爸", "chain steps are separated by 的 joiners");
state.relationshipPathLoading = true;
renderSelectionResult(true);
assert(result.dataset.state === "loading", "an in-flight path shows a loading state");
state.relationshipPathLoading = false;
renderSelectionResult(false);
assert(result.dataset.state === "empty" && text(result).includes("再点选一位人物"), "a partial selection asks for the second person");

// Toasts carry a tone and an optional one-step action.
showToast("关系已删除", "success", undoAction());
const toast = $("#toast");
assert(toast.dataset.tone === "success" && toast.classList.contains("is-visible"), "toast exposes its tone");
assert(toast.children.length === 3 && toast.children[2].textContent === "撤销", "undo toast renders an action button");
assert(timers.at(-1) === 6000, "actionable toasts stay long enough to reach");
toast.children[2].listeners.click();
assert(calls.at(-1) === "history-undo" && !toast.classList.contains("is-visible"), "the toast action undoes and dismisses");
showToast("保存失败", "error");
assert(toast.children.length === 2 && timers.at(-1) === 5200, "errors stay longer than information");

// Single-key shortcuts never fire while typing, in dialogs or with modifiers.
const idle = { closest: () => null };
function press(key, extra = {}) {
  const event = { key, target: idle, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra };
  handleShortcutKeydown(event);
  return event;
}
$("#link-mode").hidden = false;
calls.length = 0;
assert(press("f").defaultPrevented && calls.at(-1) === "fit", "F fits the whole atlas");
press("F"); press("+"); press("-"); press("0");
assert(calls.join(",") === "fit,fit,zoom-in,zoom-out,reset", "zoom keys map to the camera");
calls.length = 0;
press("f", { target: { closest: () => ({}) } });
press("f", { metaKey: true });
press("f", { isComposing: true });
assert(calls.length === 0, "typing, modified and composing keys are ignored");
press("v");
assert(calls.length === 0, "V is a no-op while already editing");
state.linkMode = true; press("v"); state.linkMode = false;
press("l"); press("r");
state.perspective = true; press("r"); state.perspective = false;
assert(calls.join(",") === "select,link,perspective,exit-perspective", "mode keys enter and leave modes");
const existingPeople = state.workspace.people;
state.workspace.people = {};
$("#link-mode").hidden = true;
calls.length = 0;
press("l"); press("r");
assert(calls.length === 0, "mode keys wait until people exist");
state.workspace.people = existingPeople;
assert(!press("q").defaultPrevented, "unmapped keys keep their default behavior");

// Link mode highlights valid targets on the cards themselves.
state.selectionA = null; state.selectionB = null;
state.linkMode = true; state.linkSource = "f";
assert(createPersonNode(state.workspace.people.f).classList.contains("is-link-source"), "the source card is marked");
assert(createPersonNode(state.workspace.people.d).classList.contains("is-link-candidate"), "adjacent unrelated cards are candidates");
assert(!createPersonNode(state.workspace.people.s).classList.contains("is-link-candidate"), "already related cards are not candidates");
assert(!createPersonNode(state.workspace.people.c).classList.contains("is-link-candidate"), "distant generations are not candidates");
const card = createPersonNode(state.workspace.people.d);
assert(card.children[2].classList.contains("node-open-icon") && card.children[2].innerHTML.includes("#i-open"), "cards use the sprite open icon");

print("PASS " + checks + " redesign UI assertions (JSC, memory-only)");
