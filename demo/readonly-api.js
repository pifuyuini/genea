/* Static transport used only by the public GitHub Pages demo. */
(() => {
  const base = new URL(".", document.currentScript.src);
  const cache = new Map();
  async function read(name) {
    if (!cache.has(name)) {
      cache.set(name, fetch(new URL(name, base)).then((response) => {
        if (!response.ok) throw new Error("演示数据暂时无法载入，请刷新或重试。");
        return response.json();
      }).catch((error) => { cache.delete(name); throw error; }));
    }
    return cache.get(name);
  }
  window.GeneaDemo = {
    readonly: true,
    downloadUrl: "https://github.com/pifuyuini/genea/archive/refs/tags/v0.1.0-preview.1.zip",
    async request(path, options = {}) {
      if ((options.method || "GET").toUpperCase() !== "GET") {
        throw new Error("公开只读演示不保存修改，请下载完整版。");
      }
      const url = new URL(path, base);
      let data;
      if (url.pathname === "/api/workspace") data = await read("workspace.json");
      else if (url.pathname === "/api/history") data = { undo_label: null, redo_label: null };
      else if (url.pathname === "/api/path") {
        const paths = await read("paths.json");
        data = paths[url.searchParams.get("from")]?.[url.searchParams.get("to")];
        if (!data) throw new Error("演示人物不存在。");
      } else throw new Error("公开演示不提供此接口。");
      // Keep the cached fixture independent of the application's in-memory view.
      return JSON.parse(JSON.stringify(data));
    },
  };
})();
