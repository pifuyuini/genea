"""Build a source ZIP from explicitly selected public project files."""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "PUBLICATION.md", ".gitignore", ".python-version",
    "genealogy_core.py", "server.py", "pyproject.toml", "uv.lock",
)
PUBLIC_GLOBS = (
    "static/*.js", "static/*.css", "static/*.html",
    "demo/README.md", "demo/*.py", "demo/readonly-api.js", "demo/readonly.css",
    "demo/data/workspace.json", "demo/data/photos/*.jpg", "demo/screenshots/*.jpg",
    "scripts/*.py", "tests/test_*.py", "tests/test_*.js",
)


def build(version: str, output_dir: Path | None = None) -> Path:
    if not version or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in version):
        raise ValueError("Version must contain only letters, digits, dots, and hyphens.")
    files = {ROOT / name for name in ROOT_FILES}
    for pattern in PUBLIC_GLOBS:
        files.update(ROOT.glob(pattern))
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Expected a regular public source file: {path.relative_to(ROOT)}")
    destination = output_dir or ROOT / ".release"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"genea-{version}-source.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        for path in sorted(files):
            output.write(path, f"genea-{version}/{path.relative_to(ROOT).as_posix()}")
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="v0.1.0-preview.1")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    print(build(args.version, args.output_dir))


if __name__ == "__main__":
    main()
