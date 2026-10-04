"""Exercise the downloadable archive, including its isolated Python imports."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("genea_public_source", ROOT / "scripts/build_source.py")
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


class PublicSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="genea-source-test-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        (cls.output / ".codex-tmp").touch()
        cls.archive = packager.build("v0.2.0-preview.1", cls.output)
        with ZipFile(cls.archive) as archive:
            cls.paths = {"/".join(Path(name).parts[1:]) for name in archive.namelist()}
            archive.extractall(cls.output / "unpacked")
        cls.bundle = cls.output / "unpacked/genea-v0.2.0-preview.1"

    def test_archive_contains_the_modules_licenses_and_native_build_inputs(self):
        required = {
            "server.py", "genealogy_core.py", "kinship_inference.py", "kinship_naming.py",
            "kinship_composition.py", "kinship_appellation.py", "relationship_query.py",
            "workspace_inspection.py", "resources/kinship/terms.json", "resources/kinship/LICENSE",
            "desktop/macos/Genea.swift", "desktop/macos/build_app.py",
            "desktop/macos/backend_bootstrap.py", "desktop/macos/Info.plist",
            "desktop/macos/RUNTIME-LICENSES.md", "demo/data/workspace.json",
            "demo2/data/workspace.json", "demo2/portraits/manifest.json", "demo2/build_pages.py",
            "demo2/demos.html",
        }
        self.assertTrue(required.issubset(self.paths), required - self.paths)
        self.assertEqual((self.bundle / "resources/kinship/LICENSE").read_bytes(),
                         (ROOT / "resources/kinship/LICENSE").read_bytes())

    def test_archive_excludes_working_data_generated_sites_and_build_products(self):
        forbidden = {".git", ".venv", ".release", "data", "tmp", "local-app", "design-qa", "dist", "build"}
        self.assertFalse({Path(path).parts[0] for path in self.paths} & forbidden)
        self.assertFalse(any(".runtime" in Path(path).parts or "__pycache__" in Path(path).parts
                             or path.endswith((".pyc", ".app")) or "/portraits/generated/" in path
                             for path in self.paths))
        self.assertEqual({path for path in self.paths if path.startswith("docs/")},
                         {"docs/app.js", "docs/motion.js", "docs/readonly-api.js", "docs/workspace.json", "docs/paths.json",
                          "docs/index.html", "docs/styles.css", "docs/readonly.css"})
        photos = [path for path in self.paths if "/photos/" in path]
        self.assertEqual(sum(path.startswith("demo/data/photos/") for path in photos), 38)
        self.assertEqual(sum(path.startswith("demo2/data/photos/") for path in photos), 46)
        self.assertTrue(all(path.startswith(("demo/data/photos/", "demo2/data/photos/")) for path in photos))

    def test_extracted_archive_imports_without_third_party_packages_or_personal_data(self):
        code = (
            "import json; import genealogy_core as core; import server; "
            "import relationship_query; import workspace_inspection; "
            "from pathlib import Path; "
            "print(json.dumps({'empty_people': len(core.default_workspace()['people']), "
            "'personal_data_created': Path('data').exists()}))"
        )
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=self.bundle,
                                check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), {"empty_people": 0, "personal_data_created": False})
        for demo in ("demo", "demo2"):
            subprocess.run([sys.executable, "-B", f"{demo}/run_demo.py", "--help"], cwd=self.bundle,
                           check=True, capture_output=True, text=True)
            self.assertEqual((self.bundle / demo / "data/workspace.json").read_bytes(),
                             (ROOT / demo / "data/workspace.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
