/* Public Pages transport: reads assets; experiment preferences live in this tab only. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GeneaDemoTransport = api;
  if (typeof document !== "undefined" && document.currentScript) {
    const base = new URL(".", document.currentScript.src);
    const cache = new Map();
    const assetFetch = root.fetch.bind(root);
    async function read(name) {
      if (!cache.has(name)) cache.set(name, assetFetch(new URL(name, base)).then((response) => {
        if (!response.ok) throw new Error("演示数据暂时无法载入，请刷新或重试。");
        return response.json();
      }).catch((error) => { cache.delete(name); throw error; }));
      return cache.get(name);
    }
    root.GeneaDemo = api.create(read, root.GeneaDemoQuery);
  }
})(globalThis, function () {
  "use strict";
  const REASON = "公开演示仅供查看，不保存修改；实验开关只影响本次浏览。下载完整版可在本机编辑。";
  const clone = (value) => JSON.parse(JSON.stringify(value));
  function error(message, status) { const value = new Error(message); value.status = status; return value; }
  function create(read, engine) {
    let enabled = true, epoch = 0;
    const config = () => ({
      experimental_features_enabled: enabled, experimental_cross_generation: enabled,
      read_only: true, read_only_reason: REASON,
    });
    const body = (options) => {
      try { return JSON.parse(options.body || "{}"); }
      catch { throw error("查询或设置格式无法读取，请重试。", 400); }
    };
    const unchanged = (token) => {
      if (token !== epoch) throw error("实验显示已切换，请重新查询。", 409);
    };
    return {
      readonly: true,
      downloadUrl: "https://github.com/pifuyuini/genea/archive/refs/tags/v0.2.0-preview.1.zip",
      async request(path, options) {
        options = options || {};
        const method = (options.method || "GET").toUpperCase();
        const route = String(path).split("?")[0];
        if (route === "/api/config" && (method === "GET" || method === "POST")) {
          if (method === "POST") {
            const value = body(options).experimental_features_enabled;
            if (typeof value !== "boolean") throw error("experimental_features_enabled 必须是布尔值。", 400);
            if (enabled !== value) { enabled = value; epoch += 1; }
          }
          return config();
        }
        if (route === "/api/query" && method === "POST") {
          if (!enabled) throw error("请先开启实验功能。", 403);
          const token = epoch, payload = body(options);
          const [data, paths] = await Promise.all([read("queries.json"), read("paths.json")]);
          unchanged(token);
          return clone(engine.run(data, paths, payload.text, payload.resolutions));
        }
        if (method !== "GET") throw error("公开只读演示不保存修改或执行修复，请下载完整版。", 403);
        if (route === "/api/workspace") return clone(await read("workspace.json"));
        if (route === "/api/history") return { undo_label: null, redo_label: null };
        if (route === "/api/path") {
          const token = epoch;
          const params = new URLSearchParams(String(path).split("?")[1] || "");
          const paths = await read("paths.json");
          unchanged(token);
          const result = paths[params.get("from")] && paths[params.get("from")][params.get("to")];
          if (!result) throw error("演示人物不存在。", 404);
          const value = clone(result);
          if (!enabled) delete value.direct_relationship;
          return value;
        }
        if (route === "/api/check") {
          if (!enabled) throw error("请先开启实验功能。", 403);
          const token = epoch, report = await read("check.json");
          unchanged(token);
          return clone(report);
        }
        throw error("公开演示不提供此接口。", 404);
      },
    };
  }
  return { create, reason: REASON };
});
