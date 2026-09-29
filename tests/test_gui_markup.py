import re
import unittest
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []

    def handle_starttag(self, tag, attributes):
        self.elements.append((tag, dict(attributes)))


class GuiMarkupTests(unittest.TestCase):
    def setUp(self):
        self.document = Document()
        self.document.feed((ROOT / "static/index.html").read_text())
        self.by_id = {attrs["id"]: (tag, attrs) for tag, attrs in self.document.elements if "id" in attrs}

    def test_unique_ids_and_all_static_js_targets_exist(self):
        counts = Counter(attrs["id"] for _, attrs in self.document.elements if "id" in attrs)
        self.assertTrue(all(count == 1 for count in counts.values()))
        script = (ROOT / "static/app.js").read_text()
        targets = set(re.findall(r'\$\("#([a-zA-Z0-9_-]+)"\)', script))
        self.assertFalse(targets - self.by_id.keys(), f"Missing HTML targets: {targets - self.by_id.keys()}")

    def test_sidebar_help_and_stats_have_real_targets(self):
        for identifier in ("workspace-sidebar", "generation-navigation", "workspace-overview",
                           "workspace-people-count", "workspace-generation-count", "workspace-relationship-count"):
            self.assertIn(identifier, self.by_id)
        for identifier in ("workspace-sidebar-toggle", "help-toggle"):
            _, attrs = self.by_id[identifier]
            self.assertIn(attrs["aria-controls"], self.by_id)
            self.assertIn("aria-expanded", attrs)
            self.assertTrue(attrs.get("aria-label"))
        self.assertEqual(self.by_id["workspace-save-state"][1]["role"], "status")
        self.assertIn("hidden", self.by_id["help-popover"][1])

    def test_every_controlled_region_exists(self):
        for _, attrs in self.document.elements:
            for identifier in attrs.get("aria-controls", "").split():
                self.assertIn(identifier, self.by_id)

    def test_assets_and_local_scripts_exist(self):
        for tag, attrs in self.document.elements:
            if tag == "script" and attrs.get("src", "").startswith("/"):
                self.assertTrue((ROOT / "static" / attrs["src"].lstrip("/")).is_file())
        self.assertEqual(self.by_id["person-photo"][1]["type"], "file")
        self.assertEqual(self.by_id["person-name"][1]["autocomplete"], "off")


if __name__ == "__main__":
    unittest.main()
