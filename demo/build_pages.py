#!/usr/bin/env python3
"""Build an independent Demo1 preview with the frozen legacy UI."""
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
    if output_dir is None:
        raise ValueError("Demo1 is frozen; specify an independent --output-dir.")
    output = Path(output_dir)
    if output.resolve().is_relative_to((ROOT / "docs").resolve()):
        raise ValueError("The published docs tree is frozen; choose an independent output directory.")
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
    for filename in ("index.html", "styles.css", "motion.js", "app.js", "readonly-api.js", "readonly.css"):
        shutil.copyfile(ROOT / "docs" / filename, output / filename)
    for filename, value in (("workspace.json", workspace), ("paths.json", paths)):
        (output / filename).write_text(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True, help="Independent preview directory outside the published docs tree")
    args = parser.parse_args()
    output = build(args.output_dir)
    print(f"Built read-only Pages demo: {output}")


if __name__ == "__main__":
    main()
