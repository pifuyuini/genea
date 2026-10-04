"""Build an offline arm64 Genea.app using the existing uv Python runtime."""
from __future__ import annotations

import argparse
import json
import os
import plistlib
from pathlib import Path
import shutil
import select
import subprocess
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "desktop" / "macos"
BACKEND_FILES = (
    "server.py", "genealogy_core.py", "workspace_inspection.py",
    "kinship_naming.py", "kinship_inference.py", "kinship_composition.py",
    "kinship_appellation.py", "relationship_query.py",
)


def run(*args: str | Path) -> None:
    subprocess.run([str(arg) for arg in args], check=True)


def resource_plan(root: Path = ROOT, *, include_demos: bool = True) -> list[tuple[Path, str]]:
    """Explicit public allowlist; private root data is never a build input."""
    plan = [(root / name, "backend/" + name) for name in BACKEND_FILES]
    plan += [
        (root / "desktop/macos/backend_bootstrap.py", "backend/backend_bootstrap.py"),
        (root / "desktop/macos/bridge.js", "bridge.js"),
        (root / "desktop/macos/RUNTIME-LICENSES.md", "RUNTIME-LICENSES.md"),
        (root / "static", "static"),
        (root / "resources", "resources"),
    ]
    if include_demos:
        plan += [(root / "demo/data", "seeds/demo1/data"),
                 (root / "demo2/data", "seeds/demo2/data")]
    return plan


def validate_resources(resources: Path, *, include_demos: bool = True) -> None:
    required = [
        "Python/bin/python3.12", "Python/lib/python3.12/LICENSE.txt",
        "backend/backend_bootstrap.py", "backend/server.py",
        "backend/resources/kinship/terms.json", "resources/kinship/LICENSE",
        "static/index.html", "static/app.js", "static/styles.css", "bridge.js",
        "AppIcon.icns", "RUNTIME-LICENSES.md",
    ]
    if include_demos:
        required += ["seeds/demo1/data/workspace.json", "seeds/demo2/data/workspace.json"]
    missing = [name for name in required if not (resources / name).is_file()]
    if missing:
        raise ValueError("Missing App resources: " + ", ".join(missing))
    for demo in (("demo1", "demo2") if include_demos else ()):
        data = resources / "seeds" / demo / "data"
        workspace = json.loads((data / "workspace.json").read_text())
        for person in workspace["people"].values():
            photo = person.get("photo_path")
            if photo and photo.startswith("/photos/") and not (data / "photos" / Path(photo).name).is_file():
                raise ValueError(f"Missing {demo} seed photo: {photo}")
    if (resources / "data").exists() or (resources / "backend/data").exists():
        raise ValueError("Private data must not be bundled.")


def relocate_and_sign_runtime(runtime: Path, original: Path) -> None:
    """Repoint only bundled dylib references; leave macOS system libraries intact."""
    macho = [runtime / "bin/python3.12"]
    macho += sorted(runtime.rglob("*.dylib"))
    macho += sorted(runtime.rglob("*.so"))
    for path in macho:
        output = subprocess.check_output(["otool", "-L", str(path)], text=True)
        for line in output.splitlines()[1:]:
            dependency = line.strip().split(" (", 1)[0]
            if dependency.startswith(str(original) + "/"):
                bundled = runtime / Path(dependency).relative_to(original)
                replacement = "@loader_path/" + os.path.relpath(bundled, path.parent)
                if dependency == str(original / path.relative_to(runtime)):
                    run("xcrun", "install_name_tool", "-id", replacement, path)
                else:
                    run("xcrun", "install_name_tool", "-change", dependency, replacement, path)
        run("codesign", "--force", "--sign", "-", path)



def verify_bundled_backend(resources: Path, work: Path, *, include_demos: bool = True) -> None:
    """Exercise the relocated runtime, packaged imports and the App startup contract."""
    data = work / "backend-smoke-data"
    if include_demos:
        shutil.copytree(resources / "seeds/demo2/data", data)
    else:
        data.mkdir()
    backend = resources / "backend"
    bootstrap = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));sys.argv.pop(0);runpy.run_path(sys.argv[0],run_name='__main__')"
    process = subprocess.Popen(
        [str(resources / "Python/bin/python3.12"), "-I", "-B", "-u", "-c", bootstrap,
         str(backend), str(backend / "backend_bootstrap.py"), "--data-dir", str(data),
         *(["--experimental-default"] if include_demos else [])], cwd=work,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        if not select.select([process.stdout], [], [], 10)[0]:
            raise RuntimeError("Bundled backend did not announce readiness.")
        ready = json.loads(process.stdout.readline())
        with urlopen(ready["url"] + "/api/workspace", timeout=5) as response:
            workspace = json.loads(response.read())
        expected = json.loads((data / "workspace.json").read_text())
        if len(workspace["people"]) != len(expected["people"]):
            raise RuntimeError("Bundled backend did not load its isolated family copy.")
        with urlopen(ready["url"] + "/", timeout=5) as response:
            if b"<html" not in response.read().lower():
                raise RuntimeError("Bundled static UI was not served.")
        process.stdin.close()
        if process.wait(timeout=5) != 0:
            raise RuntimeError("Bundled backend did not shut down cleanly.")
        if process.stdout.read():
            raise RuntimeError("Bundled backend polluted the readiness stream.")
        print("Relocated App backend: ready, isolated family and static UI verified; EOF exit clean.")
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def create_icon(iconset: Path, destination: Path) -> None:
    iconset.mkdir()
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            suffix = "@2x" if scale == 2 else ""
            pixels = size * scale
            run("sips", "-z", str(pixels), str(pixels), SOURCE / "assets/genea-icon.png",
                "--out", iconset / f"icon_{size}x{size}{suffix}.png")
    run("iconutil", "-c", "icns", iconset, "-o", destination)


def build(output: Path, runtime_source: Path, *, include_demos: bool = True,
          default_library_dir: Path | None = None) -> Path:
    output = output.expanduser().absolute()
    if output.suffix != ".app":
        raise ValueError("--output must name a .app directory.")
    # Build artifacts belong inside this task's marked project tmp directory.
    resolved_parent = output.parent.resolve()
    if not resolved_parent.is_relative_to((ROOT / "tmp").resolve()):
        raise ValueError("--output must be inside the project's tmp directory.")
    if not any((parent / ".codex-tmp").is_file() for parent in
               (resolved_parent, *resolved_parent.parents) if parent.is_relative_to((ROOT / "tmp").resolve())):
        raise ValueError("--output requires a task-owned .codex-tmp parent.")
    if output.exists():
        raise FileExistsError(f"Choose a new output path; existing output is preserved: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    build_directory = Path(tempfile.mkdtemp(prefix="genea-build-", dir=output.parent))
    (build_directory / ".codex-tmp").write_text("Created by desktop/macos/build_app.py.\n")
    app = build_directory / output.name
    contents = app / "Contents"
    resources = contents / "Resources"
    executable = contents / "MacOS/Genea"
    executable.parent.mkdir(parents=True)
    resources.mkdir()
    try:
        for source, relative in resource_plan(include_demos=include_demos):
            target = resources / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        (resources / "backend/resources").symlink_to("../resources", target_is_directory=True)
        # Full runtime includes licenses and optional libraries without installing anything.
        shutil.copytree(runtime_source, resources / "Python", symlinks=True)
        relocate_and_sign_runtime(resources / "Python", runtime_source)
        create_icon(build_directory / "AppIcon.iconset", resources / "AppIcon.icns")
        info = plistlib.loads((SOURCE / "Info.plist").read_bytes())
        info["GeneaIncludeDemoSeeds"] = include_demos
        if default_library_dir is not None:
            info["GeneaDefaultLibraryDirectory"] = str(default_library_dir.expanduser().absolute())
        (contents / "Info.plist").write_bytes(plistlib.dumps(info, sort_keys=False))
        run("xcrun", "swiftc", "-O", "-target", "arm64-apple-macos13.0",
            "-module-cache-path", build_directory / "swift-module-cache",
            "-framework", "AppKit", "-framework", "WebKit", SOURCE / "Genea.swift", "-o", executable)
        validate_resources(resources, include_demos=include_demos)
        # Validate the copied interpreter, with environment Python configuration ignored.
        run(resources / "Python/bin/python3.12", "-I", "-B", "-c",
            "import sys,json,http.server,pathlib; print('Bundled Python:',sys.version.split()[0],sys.prefix)")
        run("codesign", "--force", "--sign", "-", app)
        run("codesign", "--verify", "--deep", "--strict", app)
        app.rename(output)
        verify_bundled_backend(output / "Contents/Resources", build_directory, include_demos=include_demos)
    finally:
        shutil.rmtree(build_directory)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=Path(sys.base_prefix))
    parser.add_argument("--without-demos", action="store_true",
                        help="Omit literary sample seeds; keep family import and an empty-family fallback.")
    parser.add_argument("--default-library-dir", type=Path,
                        help="Set this App copy's persistent default library without bundling any family data.")
    args = parser.parse_args()
    app = build(args.output, args.runtime.resolve(), include_demos=not args.without_demos,
                default_library_dir=args.default_library_dir)
    print(f"Built {app}")
    print(f"Size: {sum(p.stat().st_size for p in app.rglob('*') if p.is_file()) / 1024**2:.1f} MiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
