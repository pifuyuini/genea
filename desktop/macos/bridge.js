(() => {
  "use strict";
const preferenceKeys = new Set(["genea-appearance", "genea-theme"]);
for (const [key, value] of Object.entries(window.geneaPreferenceSnapshot || {})) {
  if (preferenceKeys.has(key)) localStorage.setItem(key, value);
}
const originalSetItem = Storage.prototype.setItem;
Storage.prototype.setItem = function(key, value) {
  originalSetItem.call(this, key, value);
  if (this === localStorage && preferenceKeys.has(key)) {
    window.webkit.messageHandlers.geneaPreferences.postMessage({ key, value: String(value) });
  }
};
const pending = new Map();
  let sequence = 0;
  window.geneaDesktop = {
    // The page shows which family this window holds; the native title text is hidden.
    familyName: typeof window.geneaFamilyName === "string" ? window.geneaFamilyName : "",
    // The title bar is tinted to the page chrome; only an explicit choice pins the window appearance.
    appearanceChanged(theme, explicit) {
      window.webkit.messageHandlers.geneaAppearance?.postMessage({ theme: theme === "mocha" ? "mocha" : "latte", explicit: Boolean(explicit) });
    },
    completeClipboard(id, success) {
      const request = pending.get(id);
      if (!request) return;
      pending.delete(id);
      if (success) request.resolve();
      else request.reject(new Error("系统剪贴板写入失败"));
    },
    closeStatus() {
      if (typeof state === "undefined") return { busy: false, dirty: false };
      const dialog = document.querySelector("#relationship-dialog");
      const relationship = typeof relationshipById === "function" ? relationshipById(state.editingRelationshipId) : null;
      let relationshipDirty = false;
      if (dialog?.open && relationship) {
        const kind = relationshipKindValue();
        relationshipDirty = kind !== (relationship.kind || relationship.type || "standard") ||
          (kind === "special" && (document.querySelector("#parent-label").value.trim() !== (relationship.parent_label || "") ||
          document.querySelector("#child-label").value.trim() !== (relationship.child_label || "")));
      }
      return {
        busy: Boolean(state.mutations || state.historyBusy || state.configBusy ||
          (typeof personEditor !== "undefined" && personEditor.saving) ||
          (typeof relationshipSaving !== "undefined" && relationshipSaving)),
        dirty: Boolean((typeof personHasChanges === "function" && personHasChanges()) || relationshipDirty),
      };
    },
    reviewStatus() {
      return {
        loaded: typeof state !== "undefined" && state.workspaceLoaded,
        people: typeof state !== "undefined" ? Object.keys(state.workspace.people).length : 0,
        generations: typeof state !== "undefined" ? state.workspace.generations.length : 0,
        relationships: typeof state !== "undefined" ? (state.workspace.relationships || []).length : 0,
        photoElements: document.querySelectorAll(".person-node img").length,
        loadedPhotos: [...document.querySelectorAll(".person-node img")].filter(img => img.complete && img.naturalWidth > 0).length,
        ...this.closeStatus(),
      };
    },
  };
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: {
    writeText(text) {
      return new Promise((resolve, reject) => {
        const id = ++sequence;
        pending.set(id, { resolve, reject });
        window.webkit.messageHandlers.geneaClipboard.postMessage({ id, text: String(text) });
      });
    },
  } });
})();
