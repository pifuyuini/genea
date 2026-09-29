"""Exercise the actual public Pages builder using only the literary demo."""
import importlib.util
import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import genealogy_core as core

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_pages", ROOT / "demo/build_pages.py")
build_pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_pages)


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.scripts = []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "script" and attrs.get("src"):
            self.scripts.append(attrs["src"])
        for attr in ("src", "href"):
            value = attrs.get(attr)
            if value and not value.startswith(("#", "data:")):
                self.references.append((tag, value))


class PagesBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="genea-pages-test-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name) / "site"
        cls.source_files = [ROOT / "demo/data/workspace.json", *sorted((ROOT / "demo/data/photos").glob("*.jpg")),
                            *sorted((ROOT / "static").glob("*"))]
        cls.source_before = {path: path.read_bytes() for path in cls.source_files if path.is_file()}
        build_pages.build(cls.output)
        cls.workspace = json.loads((cls.output / "workspace.json").read_text(encoding="utf-8"))
        cls.paths = json.loads((cls.output / "paths.json").read_text(encoding="utf-8"))
        cls.demo = json.loads((ROOT / "demo/data/workspace.json").read_text(encoding="utf-8"))

    def test_all_demo_people_relationships_and_portraits_are_packaged(self):
        self.assertEqual((len(self.workspace["generations"]), len(self.workspace["people"]),
                          len(self.workspace["relationships"])), (6, 38, 42))
        self.assertNotIn("_history", self.workspace)
        self.assertEqual(set(self.workspace["people"]), set(self.demo["people"]))
        self.assertEqual(self.workspace["relationships"], self.demo["relationships"])
        photos = sorted((self.output / "photos").glob("*.jpg"))
        self.assertEqual(len(photos), 38)
        self.assertEqual({p["photo_path"] for p in self.workspace["people"].values()},
                         {"photos/" + path.name for path in photos})
        for photo in photos:
            with self.subTest(photo=photo.name):
                self.assertEqual(photo.read_bytes(), (ROOT / "demo/data/photos" / photo.name).read_bytes())

    def test_every_ordered_path_matches_the_actual_python_core(self):
        ids = set(self.demo["people"])
        self.assertEqual(set(self.paths), ids)
        checked = 0
        for source in ids:
            self.assertEqual(set(self.paths[source]), ids)
            for target in ids:
                with self.subTest(source=source, target=target):
                    self.assertEqual(self.paths[source][target], core.relationship_path(self.demo, source, target))
                checked += 1
        self.assertEqual(checked, 1444)

    def test_representative_direction_special_and_disconnected_paths(self):
        examples = [
            ("person_baoyu", "person_baochai", "妈妈的爸爸的女儿的女儿"),
            ("person_yingchun", "person_xingfuren", "嫡母"),
            ("person_xingfuren", "person_yingchun", "庶女"),
            ("person_keqing", "person_qinye", "养父"),
            ("person_qinye", "person_keqing", "养女"),
            ("person_baoyu", "person_qinye", ""),
            ("person_baoyu", "person_baoyu", "自己"),
        ]
        for source, target, expected in examples:
            with self.subTest(source=source, target=target):
                self.assertEqual(self.paths[source][target]["path_text"], expected)

    def test_page_resources_work_under_a_repository_subpath(self):
        html = (self.output / "index.html").read_text(encoding="utf-8")
        parsed = Resources()
        parsed.feed(html)
        self.assertTrue((self.output / ".nojekyll").is_file())
        base = "https://example.github.io/genea/"
        local = []
        for tag, reference in parsed.references:
            if urlparse(reference).scheme:
                continue
            with self.subTest(reference=reference):
                self.assertFalse(reference.startswith("/"), "Root-absolute resources escape project Pages.")
                self.assertTrue(urljoin(base, reference).startswith(base))
                resource = urlparse(reference).path
                self.assertTrue((self.output / resource).is_file(), reference)
                local.append(reference)
        self.assertTrue(any("styles.css" in name for name in local))
        adapter = next(i for i, name in enumerate(parsed.scripts) if name.endswith("readonly-api.js"))
        application = next(i for i, name in enumerate(parsed.scripts) if name.endswith("app.js"))
        self.assertLess(adapter, application)
        for person in self.workspace["people"].values():
            self.assertTrue(urljoin(base, person["photo_path"]).startswith(base))

    def test_readonly_styles_keep_browse_and_relationship_modes_visible(self):
        parsed = Resources()
        parsed.feed((self.output / "index.html").read_text(encoding="utf-8"))
        styles = [reference for tag, reference in parsed.references if tag == "link" and reference.endswith(".css")]
        base = next(index for index, name in enumerate(styles) if name.endswith("/styles.css"))
        readonly = next(index for index, name in enumerate(styles) if name.endswith("/readonly.css"))
        self.assertGreater(readonly, base, "Read-only visibility rules must override the editable theme.")
        css = (self.output / "readonly.css").read_text(encoding="utf-8")
        rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        visible_mode_rules = [body for selector, body in rules
                              if "body[data-readonly]" in selector and
                              ".mode-switcher:has(#perspective-mode:not([hidden]))" in selector]
        self.assertTrue(any(re.search(r"display\s*:\s*flex\s*;", body) for body in visible_mode_rules),
                        "Hiding the link button must not hide the public browse/relationship toolbar.")

    def test_build_does_not_modify_the_editable_application_or_demo(self):
        for path, before in self.source_before.items():
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertEqual(path.read_bytes(), before)
        original = (ROOT / "static/index.html").read_text(encoding="utf-8")
        self.assertNotIn('src="readonly-api.js"', original)
        self.assertNotIn('src="/readonly-api.js"', original)

    def test_output_contains_no_python_runtime_or_source_workspace(self):
        paths = [path.relative_to(self.output) for path in self.output.rglob("*") if path.is_file()]
        self.assertFalse(any(".runtime" in path.parts or "__pycache__" in path.parts for path in paths))
        self.assertFalse(any(path.suffix in {".py", ".pyc"} for path in paths))
        self.assertEqual([str(path) for path in paths if path.name == "workspace.json"], ["workspace.json"])


if __name__ == "__main__":
    unittest.main()
