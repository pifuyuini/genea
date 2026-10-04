/* Runs without dependencies in Node, or macOS JavaScriptCore shell:
   /System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc tests/test_desktop_bridge.js */
const bridgeSource = typeof require === "function"
  ? require("fs").readFileSync("desktop/macos/bridge.js", "utf8")
  : readFile("desktop/macos/bridge.js");
const nativeSource = typeof require === "function"
  ? require("fs").readFileSync("desktop/macos/Genea.swift", "utf8")
  : readFile("desktop/macos/Genea.swift");
const nativeClipboardLine = nativeSource.split("\n").find(line => line.includes("navigator.clipboard.writeText"));
const nativeClipboardLiteral = nativeClipboardLine?.slice(nativeClipboardLine.indexOf("evaluateJavaScript(") + "evaluateJavaScript(".length, nativeClipboardLine.lastIndexOf(")"));
const nativeClipboardScript = nativeClipboardLiteral ? JSON.parse(nativeClipboardLiteral) : null;
const logResult = typeof print === "function" ? print : console.log;
function assert(value, message) { if (!value) throw new Error(message); }
function fixture(options = {}) {
  const clipboard = [], preferences = [];
  class StorageMock {
    constructor() { this.values = new Map(); }
    setItem(key, value) { this.values.set(String(key), String(value)); }
    getItem(key) { return this.values.get(String(key)) ?? null; }
  }
  const localStorage = new StorageMock();
  const appearances = [];
  const window = {
    geneaPreferenceSnapshot: { "genea-appearance": "mocha", "foreign-key": "skip" },
    geneaFamilyName: "Demo2 · 百年孤独",
    webkit: { messageHandlers: {
      geneaClipboard: { postMessage: value => clipboard.push(value) },
      geneaPreferences: { postMessage: value => preferences.push(value) },
      geneaAppearance: { postMessage: value => appearances.push(value) },
    } },
  };
  const navigator = {};
  const state = { workspaceLoaded: true, workspace: { people: { a: {}, b: {} }, generations: [{}, {}] } };
  const personEditor = { saving: false };
  const relationship = { kind: "special", parent_label: "养父", child_label: "养女" };
  const dialog = { open: false };
  const fields = { "#relationship-dialog": dialog, "#parent-label": { value: "养父" }, "#child-label": { value: "养女" } };
  const images = [{ complete: true, naturalWidth: 10 }, { complete: false, naturalWidth: 0 }];
  const document = { querySelector: key => fields[key], querySelectorAll: () => images };
  const values = { relationshipSaving: false, dirty: false, kind: "special" };
  // Lexical globals match the existing app.js; no DOM or UI markup is changed by injection.
  const factory = new Function("window", "navigator", "document", "state", "personEditor", "relationshipById", "relationshipKindValue", "personHasChanges", "Storage", "localStorage", "values",
    "with (values) { " + bridgeSource + " } return window.geneaDesktop;");
  const desktop = factory(window, navigator, document, state, personEditor, () => relationship,
    () => values.kind, () => values.dirty, StorageMock, localStorage, values);
  return { desktop, navigator, state, personEditor, fields, dialog, values, localStorage, clipboard, preferences, appearances };
}
async function run() {
  const f = fixture();
  assert(!f.desktop.closeStatus().busy && !f.desktop.closeStatus().dirty, "clean workspace can close");
  for (const key of ["mutations", "historyBusy", "configBusy"]) {
    f.state[key] = 1;
    assert(f.desktop.closeStatus().busy, key + " must prevent closing");
    f.state[key] = 0;
  }
  f.personEditor.saving = true;
  assert(f.desktop.closeStatus().busy, "person save prevents closing");
  f.personEditor.saving = false;
  f.values.relationshipSaving = true;
  assert(f.desktop.closeStatus().busy, "relationship save prevents closing");
  f.values.relationshipSaving = false;
  f.values.dirty = true;
  assert(f.desktop.closeStatus().dirty, "person draft requires confirmation");
  f.values.dirty = false;
  f.dialog.open = true;
  assert(!f.desktop.closeStatus().dirty, "unchanged relationship stays clean");
  f.fields["#child-label"].value = "养子";
  assert(f.desktop.closeStatus().dirty, "relationship role draft requires confirmation");
  f.fields["#child-label"].value = "养女";
  f.values.kind = "standard";
  assert(f.desktop.closeStatus().dirty, "relationship kind draft requires confirmation");
  f.dialog.open = false;
  const summary = f.desktop.reviewStatus();
  assert(summary.loaded && summary.people === 2 && summary.generations === 2 && summary.loadedPhotos === 1 && summary.photoElements === 2, "review emits aggregate load counts only");
  assert(f.localStorage.getItem("genea-appearance") === "mocha" && f.localStorage.getItem("foreign-key") === null, "restore only existing appearance keys");
  assert(f.preferences.length === 0, "restore does not send redundant native writes");
  f.localStorage.setItem("genea-appearance", "latte");
  f.localStorage.setItem("unrelated", "keep");
  assert(f.preferences.length === 1 && f.preferences[0].value === "latte" && f.localStorage.getItem("unrelated") === "keep", "persist only existing appearance keys, preserve storage behavior");
  assert(f.desktop.familyName === "Demo2 · 百年孤独", "the injected family name reaches the page header");
  f.desktop.appearanceChanged("mocha", true); f.desktop.appearanceChanged("unexpected");
  assert(f.appearances.map((item) => item.theme + ":" + item.explicit).join(",") === "mocha:true,latte:false",
    "title bar tint follows the resolved page theme; only explicit choices pin the window appearance");
assert(nativeClipboardScript, "native smoke script is present");
const nativeCopy = new Function("navigator", "return " + nativeClipboardScript)(f.navigator);
assert(f.clipboard.length === 1 && typeof f.clipboard[0].text === "string", "actual native injected script executes clipboard bridge");
f.desktop.completeClipboard(f.clipboard[0].id, true);
await nativeCopy;
f.clipboard.length = 0;
const copy = f.navigator.clipboard.writeText("public relation chain");
  assert(f.clipboard.length === 1 && f.clipboard[0].text === "public relation chain", "clipboard uses native message");
  f.desktop.completeClipboard(f.clipboard[0].id, true);
  await copy;
  const failed = f.navigator.clipboard.writeText("failure");
  f.desktop.completeClipboard(f.clipboard[1].id, false);
  let rejected = false;
  try { await failed; } catch { rejected = true; }
  assert(rejected, "native clipboard failure rejects to existing UI");
  f.desktop.completeClipboard(999, true);
  logResult("PASS desktop bridge: save/draft close guards, aggregate review, per-family preferences, family title and title bar tint, clipboard success/failure");
}
run().catch(error => { logResult("FAIL " + error.message); if (typeof quit === "function") quit(1); else process.exitCode = 1; });
