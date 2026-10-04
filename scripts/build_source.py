"""Build the browser and native sources from an explicit public file list."""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VERSION = "v0.2.0-preview.1"
SOURCE_FILES = (
    "README.md", "PUBLICATION.md", ".gitignore", ".python-version",
    "pyproject.toml", "uv.lock", ".github/workflows/release.yml",
    "genealogy_core.py", "server.py",
    "kinship_appellation.py", "kinship_composition.py", "kinship_inference.py",
    "kinship_naming.py", "relationship_query.py", "workspace_inspection.py",
    "static/app.js", "static/index.html", "static/motion.js", "static/styles.css",
    "docs/app.js", "docs/motion.js", "docs/readonly-api.js", "docs/workspace.json", "docs/paths.json",
    "docs/index.html", "docs/styles.css", "docs/readonly.css",
    "resources/kinship/README.md", "resources/kinship/LICENSE", "resources/kinship/terms.json",
    "demo/README.md", "demo/build_demo.py", "demo/build_pages.py", "demo/run_demo.py",
    "demo/readonly-api.js", "demo/readonly.css", "demo/data/workspace.json",
    "demo2/README.md", "demo2/build_demo.py", "demo2/build_pages.py", "demo2/run_demo.py",
    "demo2/demos.html",
    "demo2/query-engine.js", "demo2/readonly-api.js", "demo2/readonly.css",
    "demo2/data/workspace.json", "demo2/portraits/README.md", "demo2/portraits/manifest.json",
    "demo2/portraits/prompt-01.txt", "demo2/portraits/prompt-02.txt", "demo2/portraits/prompt-03.txt",
    "desktop/macos/Genea.swift", "desktop/macos/build_app.py",
    "desktop/macos/backend_bootstrap.py", "desktop/macos/bridge.js", "desktop/macos/Info.plist",
    "desktop/macos/README.md", "desktop/macos/RUNTIME-LICENSES.md",
    "desktop/macos/assets/genea-icon.png", "desktop/macos/assets/icon-prompt.txt",
    "scripts/build_source.py", "scripts/build_kinship_terms.py",
    "tests/test_cross_generation.py", "tests/test_cross_generation_ui.js",
    "tests/test_demo2_data.py", "tests/test_demo2_portraits.py",
    "tests/test_demo2_query.js", "tests/test_demo2_readonly.js", "tests/test_demo_data.py",
    "tests/test_desktop_backend.py", "tests/test_desktop_bridge.js",
    "tests/test_desktop_launch.py", "tests/test_desktop_packaging.py",
    "tests/test_experimental_config.py", "tests/test_experimental_tools_ui.js",
    "tests/test_genealogy_core.py", "tests/test_gui_markup.py", "tests/test_history.py",
    "tests/test_history_ui.js", "tests/test_kinship_appellation.py",
    "tests/test_kinship_composition.py", "tests/test_kinship_generalization.py",
    "tests/test_kinship_inference.py", "tests/test_kinship_naming.py", "tests/test_kinship_ui.js",
    "tests/test_motion.js", "tests/test_navigation_ui.js", "tests/test_pages_build.py",
    "tests/test_pages_demo2.py", "tests/test_path_api.py", "tests/test_public_source.py",
    "tests/test_readonly_demo.js", "tests/test_redesign_ui.js", "tests/test_relationship_query.py",
    "tests/test_server_storage.py", "tests/test_workspace_inspection.py", "tests/test_workspace_ui.js",
)
PUBLIC_GLOBS = (
    "demo/data/photos/*.jpg",
    "demo2/data/photos/*.jpg",
    "demo/screenshots/*.jpg",
)


def source_files() -> list[Path]:
    files = {ROOT / name for name in SOURCE_FILES}
    for pattern in PUBLIC_GLOBS:
        files.update(ROOT.glob(pattern))
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Expected a regular public source file: {path.relative_to(ROOT)}")
    return sorted(files)


def build(version: str, output_dir: Path | None = None) -> Path:
    if not version or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in version):
        raise ValueError("Version must contain only letters, digits, dots, and hyphens.")
    files = source_files()
    destination = output_dir or ROOT / ".release"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"genea-{version}-source.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, f"genea-{version}/{path.relative_to(ROOT).as_posix()}")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(build(args.version, args.output_dir))


if __name__ == "__main__":
    main()
