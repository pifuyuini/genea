#!/usr/bin/env python3
"""Build the public, read-only Pages demo from the bundled fictional workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import genealogy_core as core


def build(output_dir: Path | None = None) -> Path:
    output = Path(output_dir) if output_dir is not None else ROOT / "docs"
    source = ROOT / "demo" / "data"
    workspace = core.ensure_workspace(json.loads((source / "workspace.json").read_text(encoding="utf-8")))
    portraits = []
    for person in workspace["people"].values():
        photo = person.get("photo_path")
        if not photo:
            continue
        filename = Path(photo).name
        portrait = source / "photos" / filename
        if not portrait.is_file():
            raise FileNotFoundError(f"Missing demo portrait: {portrait}")
        portraits.append((portrait, filename))
        person["photo_path"] = "photos/" + filename

    # The Python domain model is the one source of truth for all ordered pairs.
    ids = sorted(workspace["people"])
    paths = {
        first: {second: core.relationship_path(workspace, first, second) for second in ids}
        for first in ids
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "photos").mkdir(exist_ok=True)
    for portrait, filename in portraits:
        shutil.copyfile(portrait, output / "photos" / filename)
    for filename in ("styles.css", "motion.js", "app.js"):
        shutil.copyfile(ROOT / "static" / filename, output / filename)
    for filename in ("readonly-api.js", "readonly.css"):
        shutil.copyfile(ROOT / "demo" / filename, output / filename)
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/', 'href="./').replace('src="/', 'src="./')
    html = html.replace("<title>Genea · 家族图册</title>", "<title>Genea · 公开只读演示</title>")
    html = html.replace("Genea 家族图册：在本机整理代际、人物与亲子关系。",
                        "浏览虚构示例家谱，体验人物档案、缩略导航与亲属关系查询。下载完整版可在本机编辑。")
    html = html.replace('<body data-theme=', '<body data-readonly="true" data-theme=', 1)
    html = html.replace("</head>", '  <link rel="stylesheet" href="./readonly.css" />\n  </head>', 1)
    html = html.replace('<script src="./motion.js"', '<script src="./readonly-api.js" defer></script>\n    <script src="./motion.js"', 1)
    (output / "index.html").write_text(html, encoding="utf-8")
    for filename, value in (("workspace.json", workspace), ("paths.json", paths)):
        (output / filename).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Output directory (default: repository docs/)")
    args = parser.parse_args()
    output = build(args.output_dir)
    print(f"Built read-only Pages demo: {output}")


if __name__ == "__main__":
    main()
