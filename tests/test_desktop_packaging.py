import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("genea_build_app", ROOT / "desktop/macos/build_app.py")
build_app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_app)
TEMP_ROOT = Path(os.environ.get("GENEA_QA_DIR", "")).resolve()


def setUpModule():
    if (not os.environ.get("GENEA_QA_DIR") or
            not TEMP_ROOT.is_relative_to((ROOT / "tmp").resolve()) or
            not (TEMP_ROOT / ".codex-tmp").is_file()):
        raise RuntimeError("Set GENEA_QA_DIR to this task\'s marked directory inside project tmp/.")


class DesktopPackagingTests(unittest.TestCase):
    def test_build_plan_is_public_allowlist_without_private_data(self):
        plan = build_app.resource_plan()
        sources = [source.relative_to(ROOT) for source, _ in plan]
        self.assertNotIn(Path("data"), sources)
        self.assertFalse(any(source.parts[0] == "data" for source in sources))
        self.assertIn(Path("demo/data"), sources)
        self.assertIn(Path("demo2/data"), sources)
        self.assertEqual(len({relative for _, relative in plan}), len(plan))

    def test_no_demo_plan_omits_all_seed_and_private_data(self):
        plan = build_app.resource_plan(include_demos=False)
        sources = [source.relative_to(ROOT) for source, _ in plan]
        self.assertFalse(any(source.parts[0] in {"data", "demo", "demo2"} for source in sources))
        self.assertFalse(any(relative.startswith("seeds/") for _, relative in plan))

    def test_validation_requires_runtime_and_referenced_seed_photos(self):
        with tempfile.TemporaryDirectory(prefix="package-test-", dir=TEMP_ROOT) as directory:
            resources = Path(directory)
            (resources / ".codex-tmp").write_text("Created by test_desktop_packaging.py.\n")
            with self.assertRaisesRegex(ValueError, "Missing App resources"):
                build_app.validate_resources(resources)
            for path in ("Python/bin/python3.12", "Python/lib/python3.12/LICENSE.txt",
                         "backend/backend_bootstrap.py", "backend/server.py",
                         "backend/resources/kinship/terms.json", "resources/kinship/LICENSE",
                         "static/index.html", "static/app.js", "static/styles.css", "bridge.js",
                         "AppIcon.icns", "RUNTIME-LICENSES.md"):
                target = resources / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.touch()
            build_app.validate_resources(resources, include_demos=False)
            for demo in ("demo1", "demo2"):
                data = resources / "seeds" / demo / "data"
                data.mkdir(parents=True)
                (data / "workspace.json").write_text(json.dumps({"people": {
                    "p": {"photo_path": "/photos/portrait.png"}}}))
                (data / "photos").mkdir()
            with self.assertRaisesRegex(ValueError, "Missing demo1 seed photo"):
                build_app.validate_resources(resources)
            for demo in ("demo1", "demo2"):
                (resources / "seeds" / demo / "data/photos/portrait.png").touch()
            build_app.validate_resources(resources)
            (resources / "data").mkdir()
            with self.assertRaisesRegex(ValueError, "Private data"):
                build_app.validate_resources(resources)


if __name__ == "__main__":
    unittest.main()
