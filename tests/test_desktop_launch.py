"""Exercise public and no-demo native apps using only isolated public/synthetic libraries.

Run with the repository interpreter, --app <Genea.app> --qa-dir <task-marked QA directory>.
Actual WKWebViews check loaded counts, clipboard round trips, screenshots and persistence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import select
import subprocess
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def run_native(app: Path, library: Path, output: Path, *options: str) -> dict:
    completed = subprocess.run(
        [str(app / "Contents/MacOS/Genea"), "--library-dir", str(library),
         "--open-all", "--smoke-test", str(output), *options],
        capture_output=True, text=True, timeout=45,
    )
    (output.parent / (output.name + ".log")).write_text(
        completed.stdout + completed.stderr, encoding="utf-8")
    assert completed.returncode == 0, "Native smoke failed; see the task-owned native log."
    return json.loads((output / "smoke.json").read_text(encoding="utf-8"))


def check_window(result: dict, expected: dict, families: int) -> None:
    assert result["loaded"] and result["snapshot"] and result["clipboard"]
    assert result["people"] == len(expected["people"])
    assert result["generations"] == len(expected["generations"])
    assert result["relationships"] == len(expected["relationships"])
    photos = sum(bool(person.get("photo_path") or person.get("photo_url"))
                 for person in expected["people"].values())
    assert result["loadedPhotos"] == photos and result["photoElements"] == photos
    assert result["familySelectorItems"] == families and result["titlePresent"]


def save_synthetic_generation(app: Path, data: Path) -> None:
    resources = app / "Contents/Resources"
    backend = resources / "backend"
    boot = "import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_path(sys.argv.pop(1),run_name='__main__')"
    process = subprocess.Popen(
        [str(resources / "Python/bin/python3.12"), "-I", "-B", "-u", "-c", boot,
         str(backend), str(backend / "backend_bootstrap.py"), "--data-dir", str(data)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert select.select([process.stdout], [], [], 10)[0], "Synthetic backend readiness timed out"
        ready = json.loads(process.stdout.readline())
        request = Request(ready["url"] + "/api/generations",
                          data=json.dumps({"placement": "first", "name": "Synthetic saved generation"}).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            json.loads(response.read())
        process.stdin.close()
        assert process.wait(timeout=5) == 0, "Synthetic backend did not exit cleanly"
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
        process.stdout.close()
        process.stderr.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--qa-dir", required=True, type=Path)
    args = parser.parse_args()
    args.app = args.app.resolve()
    args.qa_dir = args.qa_dir.resolve()
    if (not args.qa_dir.is_relative_to((ROOT / "tmp").resolve()) or
            not (args.qa_dir / ".codex-tmp").is_file()):
        parser.error("--qa-dir must be this task's marked directory inside project tmp/")
    info = plistlib.loads((args.app / "Contents/Info.plist").read_bytes())
    includes_demos = info.get("GeneaIncludeDemoSeeds", True)
    with tempfile.TemporaryDirectory(prefix="native-test-", dir=args.qa_dir) as directory:
        work = Path(directory)
        (work / ".codex-tmp").write_text("Created by test_desktop_launch.py.\n")
        library = work / "library"
        first = run_native(args.app, library, work / "first")
        if includes_demos:
            assert set(first) == {"demo1", "demo2"}, "Public app must register its two sample families"
            for family, result in first.items():
                expected = json.loads((args.app / "Contents/Resources/seeds" / family /
                                       "data/workspace.json").read_text())
                check_window(result, expected, 2)
            second = run_native(args.app, library, work / "second")
            assert set(second) == set(first), "Relaunch must retain the existing sample families"
            print("PASS public native app: two families, DOM/photo counts, clipboard, snapshots and relaunch")
        else:
            registry = json.loads((library / "libraries.json").read_text())
            assert len(registry) == 1 and registry[0]["name"] == "我的家谱"
            family = registry[0]["id"]
            assert family.startswith("family-") and set(first) == {family}
            empty = {"people": {}, "generations": [], "relationships": []}
            check_window(first[family], empty, 1)
            save_synthetic_generation(args.app, library / family)
            second = run_native(args.app, library, work / "second")
            expected = json.loads((library / family / "workspace.json").read_text())
            assert len(expected["generations"]) == 1
            check_window(second[family], expected, 1)
            assert json.loads((library / "libraries.json").read_text()) == registry
            source = work / "synthetic-source"
            source.mkdir()
            source_bytes = json.dumps({"schema_version": 2, **empty}).encode()
            (source / "workspace.json").write_bytes(source_bytes)
            imported_library = work / "imported-library"
            imported = run_native(args.app, imported_library, work / "imported",
                                  "--import-family", str(source))
            imported_registry = json.loads((imported_library / "libraries.json").read_text())
            assert len(imported_registry) == 1 and imported_registry[0]["name"] == "我的家谱"
            assert len(imported) == 1, "First import must precede the empty-family fallback"
            assert not (imported_library / "demo1").exists() and not (imported_library / "demo2").exists()
            assert (source / "workspace.json").read_bytes() == source_bytes
            check_window(next(iter(imported.values())), empty, 1)
            print("PASS no-demo native app: one family, synthetic save/restart, first import, unchanged source, clipboard and snapshots")


if __name__ == "__main__":
    main()
