#!/usr/bin/env python3
"""Build read-only Demo2 at docs/demo2/ and a new docs/demos/ directory page.

Run: python3 -B demo2/build_pages.py
The browser reads fixed literary data. No Python server, writes, or repair actions
are provided; experiment preferences affect only the current browser tab.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import re
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import genealogy_core as core
import relationship_query as query
import workspace_inspection as inspection

MARKER = ".genea-pages-demo2"


def output_path(output_dir: Path | str | None = None) -> Path:
    output = Path(output_dir).resolve() if output_dir is not None else ROOT / "docs" / "demo2"
    if output.name != "demo2" or output == ROOT / "demo2":
        raise ValueError("Demo2 output must be a separate directory named demo2; never use docs/ or the source demo2/.")
    if output.exists() and any(output.iterdir()) and not (output / MARKER).is_file():
        raise ValueError("Refusing to replace a nonempty directory not created by this Demo2 builder.")
    return output


def query_data(workspace: dict) -> dict:
    index = query.QueryIndex(workspace)
    ids = sorted(workspace["people"], key=index.person_order)
    people = []
    for rank, person_id in enumerate(ids):
        details = index.candidate_details(person_id)
        people.append({**details, "rank": rank,
                       "normalized_name": query._normalized(details["name"]),
                       "aliases": sorted(index.aliases[person_id])})
    evidence = {
        source: {
            target: [{**proof, "tags": sorted(proof["tags"])}
                     for proof in index.evidence(source, target)]
            for target in ids if target != source
        }
        for source in ids
    }
    return {"people": people, "relative_types": {word: asdict(spec) for word, spec in query._RELATIVE_TYPES.items()},
            "evidence": evidence}


def replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError("Public-demo injection point changed: " + before[:70])
    return text.replace(before, after, 1)


def public_app(source: str) -> str:
    pattern = r"async function api\(path, options = \{\}\) \{\n.*?\n\}\n"
    transport = """async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const mutating = method !== "GET" && !["/api/config", "/api/query"].includes(path);
  if (mutating) throw new Error(state.config.read_only_reason || "公开演示仅供查看，不保存修改或执行修复。");
  try {
    if (!window.GeneaDemo) throw new Error("演示组件尚未载入，请刷新页面。");
    const data = await window.GeneaDemo.request(path, options);
    state.connectionFailed = false;
    return data;
  } catch (error) {
    if (!state.workspaceLoaded && ["/api/config", "/api/workspace", "/api/history"].includes(path)) state.workspaceLoadFailed = true;
    throw error;
  } finally {
    renderWorkspaceSaveState();
  }
}
"""
    source, count = re.subn(pattern, lambda _: transport, source, count=1, flags=re.S)
    if count != 1:
        raise ValueError("Application API boundary changed.")
    replacements = {
        "照片仅供查看。重新启用实验性功能后可更换。": "公开演示的照片仅供查看。下载完整版可在本机更换。",
        "正在保存这份家谱的实验设置…": "正在切换本次演示的实验显示…",
        "已关闭；这份家谱含跨代关系，暂时只能查看": "已关闭；公开演示仍为只读",
        "已关闭实验功能；这份家谱含跨代关系，暂时只能查看": "已关闭实验功能；公开演示仍为只读",
        "正在检查已保存的家谱，检查不会修改资料…": "正在读取演示数据的检查报告，不会修改资料…",
        '" 项可逐项修复"': '" 项修复需下载完整版"',
        '"可逐项修复"': '"修复需完整版"',
    }
    for before, after in replacements.items():
        source = replace_once(source, before, after)
    return source

def public_html(source: str) -> str:
    source = source.replace('href="/', 'href="./').replace('src="/', 'src="./')
    replacements = {
        "<title>Genea · 家族图册</title>": "<title>Genea · 百年孤独 Demo2</title>",
        "Genea 家族图册：在本机整理代际、人物与亲子关系。": "百年孤独七代家谱：46 人、原创头像与新版实验功能。公开只读，不保存修改。",
        '<body data-theme=': '<body data-readonly="true" data-theme=',
        "</head>": '  <link rel="stylesheet" href="./readonly.css" />\n  </head>',
        '<div class="header-actions">': '<div class="header-actions">\n          <a class="button demo-route" href="../demos/">演示目录</a>',
        "开关只记在这份家谱的本机设置里，不写入家谱文件，也不进入撤销历史。": "开关仅影响本次浏览，刷新后恢复开启。公开演示不能编辑、保存或修复。",
        "只生成报告；修复前先说明改动，可撤销": "展示这份演示数据的检查报告，可定位提醒；不执行修复",
        "父母可连接任意下行的子女，长线沿右侧通道绕行": "展示已登记的跨代关系；长线沿右侧通道绕行，演示不能编辑",
        "整理家谱的常用操作": "浏览百年孤独示例家谱",
        "父母可连接任意下行的子女，同排不可连；移动保留关系，同排或倒置会被拒绝，行距不参与称谓推导。「关系」模式另有亲戚称呼与一句话查询，侧栏可检查家谱。": "此示例展示七代家谱与已登记的跨代关系，画布行距不参与称谓推导。「关系」模式可查看亲戚称呼并用一句话查询；侧栏可查看检查报告。公开演示仅可查看。",
        ">我的家谱</h2>": ">百年孤独 · Demo2</h2>",
        "资料只保存在这台电脑上": "公开文学演示 · 不保存修改",
        "当前家谱仅可查看": "Demo2 · 公开只读演示",
        "只检查已保存的资料，不会自动改动家谱。提醒供你核对；可修复的项目会先说明改动，修复后也能撤销。": "这是公开演示数据的预计算检查报告。可定位人物与关系供你核对；这里不能编辑资料或执行修复。",
        "重新检查": "重新载入报告",
        "编辑历史与画布视图": "画布视图",
        '<script src="./motion.js"': '<script src="./query-engine.js" defer></script>\n    <script src="./readonly-api.js" defer></script>\n    <script src="./motion.js"',
    }
    for before, after in replacements.items():
        source = replace_once(source, before, after)
    for label in ["排序或调整代际", "建立亲子关系", "撤销", "重做", "保存人物档案"]:
        source = replace_once(source, "<div><dt>" + label, "<div hidden><dt>" + label)
    source = replace_once(source, "<div><dt>编辑 / 连线 / 关系</dt><dd><kbd>V</kbd> <kbd>L</kbd> <kbd>R</kbd></dd></div>",
                          "<div><dt>查看 / 关系</dt><dd><kbd>V</kbd> <kbd>R</kbd></dd></div>")
    source = replace_once(source, "并复制这句称谓。", "并复制原登记关系链。")
    return source


def build(output_dir: Path | str | None = None) -> Path:
    output = output_path(output_dir)
    source = ROOT / "demo2" / "data"
    raw = json.loads((source / "workspace.json").read_text(encoding="utf-8"))
    workspace = core.ensure_workspace(raw)
    portraits = []
    for person in workspace["people"].values():
        filename = Path(person["photo_path"]).name
        portrait = source / "photos" / filename
        if not portrait.is_file():
            raise FileNotFoundError("Missing Demo2 portrait: " + str(portrait))
        portraits.append((portrait, filename))
        person["photo_path"] = "photos/" + filename
    ids = sorted(workspace["people"])
    paths = {first: {second: core.relationship_query(workspace, first, second) for second in ids} for first in ids}
    queries = query_data(workspace)
    report = inspection.inspect_workspace(raw, photo_exists=lambda photo: (source / "photos" / Path(photo).name).is_file())
    report["report_id"] = "demo2-public-v0.2.0-preview.1"
    app = public_app((ROOT / "static" / "app.js").read_text(encoding="utf-8"))
    html = public_html((ROOT / "static" / "index.html").read_text(encoding="utf-8"))
    directory_html = (ROOT / "demo2" / "demos.html").read_text(encoding="utf-8")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / MARKER).write_text("Genea public Demo2 builder output.\n", encoding="utf-8")
    (output / "photos").mkdir()
    for portrait, filename in portraits:
        shutil.copyfile(portrait, output / "photos" / filename)
    for filename in ("styles.css", "motion.js"):
        shutil.copyfile(ROOT / "static" / filename, output / filename)
    for filename in ("readonly-api.js", "query-engine.js", "readonly.css"):
        shutil.copyfile(ROOT / "demo2" / filename, output / filename)
    (output / "app.js").write_text(app, encoding="utf-8")
    (output / "index.html").write_text(html, encoding="utf-8")
    for filename, value in (("workspace.json", workspace), ("paths.json", paths), ("queries.json", queries), ("check.json", report)):
        (output / filename).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    directory = output.parent / "demos"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "index.html").write_text(directory_html, encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Separate Demo2 output directory; default: docs/demo2/")
    args = parser.parse_args()
    print("Built public read-only Demo2: " + str(build(args.output_dir)))


if __name__ == "__main__":
    main()
