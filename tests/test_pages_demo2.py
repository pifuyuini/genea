"""Static Demo2 contracts, Python equivalence and JavaScriptCore parity.

Run from the public repository: python3 -B -m unittest discover -s tests -p test_pages_demo2.py
JavaScriptCore parity runs on macOS when its system command is present.
No tests rebuild Demo1, launch a server, or write temporary files.
"""
from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import genealogy_core as core
import relationship_query as query
import workspace_inspection as inspection
from demo2 import build_pages as pages

JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")


def read(name):
    return json.loads((ROOT / "docs" / "demo2" / name).read_text(encoding="utf-8"))


def projected(result):
    return {**result, "results": [{key: value for key, value in item.items() if key != "path_result"}
                                 for item in result["results"]]}


class StaticAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag in {"script", "link", "img", "a"}:
            value = fields.get("src", fields.get("href"))
            if value:
                self.assets.append(value)


class Demo2PagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / "demo2" / "data"
        cls.raw = json.loads((cls.source / "workspace.json").read_text(encoding="utf-8"))
        cls.workspace = read("workspace.json")
        cls.paths = read("paths.json")
        cls.queries = read("queries.json")

    def test_all_2116_directional_pairs_match_current_core(self):
        self.assertEqual(len(self.workspace["people"]), 46)
        self.assertEqual(sum(len(row) for row in self.paths.values()), 2116)
        for source in self.workspace["people"]:
            for target in self.workspace["people"]:
                with self.subTest(source=source, target=target):
                    self.assertEqual(self.paths[source][target], core.relationship_query(self.workspace, source, target))
        self.assertEqual(self.paths["person_founder"]["person_founder"]["path_text"], "自己")
        self.assertEqual(self.paths["person_aureliano_jose"]["person_amaranta"]["path_text"], "养母")
        self.assertEqual(self.paths["person_petra"]["person_gaston"]["direct_relationship"]["status"], "disconnected")
        labels = {row["label"] for row in self.paths["person_arcadio"]["person_aureliano_jose"]["direct_relationship"]["results"]}
        self.assertTrue({"兄弟（长幼未知）", "堂兄弟（长幼未知）"} <= labels)

    def test_inference_and_filter_evidence_ignore_relationship_entry_order(self):
        reordered = {**self.workspace, "relationships": list(reversed(self.workspace["relationships"]))}
        for source in self.workspace["people"]:
            for target in self.workspace["people"]:
                with self.subTest(source=source, target=target):
                    self.assertEqual(core.relationship_query(reordered, source, target)["direct_relationship"],
                                     self.paths[source][target]["direct_relationship"])
        self.assertEqual(pages.query_data(reordered), self.queries)
        daily = self.paths["person_amparo"]["person_colonel"]["direct_relationship"]
        self.assertEqual(daily["status"], "unsupported")
        self.assertEqual(daily["appellation"]["label"], "表兄弟（平辈，长幼未知）")
        results = query.run_query(self.workspace, self.workspace["people"]["person_amparo"]["name"] + "的表兄弟有哪些")["results"]
        self.assertIn("person_colonel", {result["person_id"] for result in results})

    def test_snapshot_preserves_all_seven_rows_relationships_and_portraits(self):
        expected = core.ensure_workspace(self.raw)
        for person in expected["people"].values():
            person["photo_path"] = "photos/" + Path(person["photo_path"]).name
        self.assertEqual(self.workspace, expected)
        self.assertEqual(len(expected["generations"]), 7)
        self.assertEqual(len(expected["relationships"]), 53)
        self.assertEqual(sum(row["kind"] == "special" for row in expected["relationships"]), 4)
        photos = list((ROOT / "docs" / "demo2" / "photos").glob("*.jpg"))
        self.assertEqual(len(photos), 46)
        for photo in photos:
            self.assertEqual(photo.read_bytes(), (self.source / "photos" / photo.name).read_bytes())
        levels = {row["id"]: row["position"] for row in expected["generations"]}
        cross = [row["id"] for row in expected["relationships"]
                 if levels[expected["people"][row["child_id"]]["generation_id"]] > levels[expected["people"][row["parent_id"]]["generation_id"]] + 1]
        self.assertEqual(cross, ["rel_amaranta_ursula__aureliano_last"])

    def test_query_index_export_and_real_check_report(self):
        self.assertEqual(self.queries, pages.query_data(self.workspace))
        report = read("check.json")
        report.pop("report_id")
        self.assertEqual(report, inspection.inspect_workspace(
            self.raw, photo_exists=lambda photo: (self.source / "photos" / Path(photo).name).is_file()))
        self.assertEqual(report["summary"], {"errors": 0, "notices": 2, "repairable": 0})
        self.assertEqual({issue["person_ids"][0] for issue in report["issues"]}, {"person_petra", "person_gaston"})

    def test_asset_urls_and_read_only_copy_contract(self):
        output = ROOT / "docs" / "demo2"
        html = (output / "index.html").read_text(encoding="utf-8")
        assets = StaticAssets()
        assets.feed(html)
        for value in assets.assets:
            self.assertFalse(value.startswith("/"), value)
            if value.startswith("data:"):
                continue
            self.assertTrue((output / value).exists(), value)
        self.assertIn('data-readonly="true"', html)
        for text in ["公开只读", "刷新后恢复开启", "不能编辑、保存或修复", "预计算检查报告"]:
            self.assertIn(text, html)
        app = (output / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("await fetch(", app)
        self.assertIn("await window.GeneaDemo.request(path, options)", app)
        source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        pattern = r"function relationshipCopySummary\(.*?\n\}"
        self.assertEqual(re.search(pattern, app, re.S).group(), re.search(pattern, source, re.S).group())
        for name in ["styles.css", "motion.js"]:
            self.assertEqual((output / name).read_bytes(), (ROOT / "static" / name).read_bytes())
        for name in ["query-engine.js", "readonly-api.js", "readonly.css"]:
            self.assertEqual((output / name).read_bytes(), (ROOT / "demo2" / name).read_bytes())

    def test_demo_directory_links_both_isolated_versions(self):
        directory = ROOT / "docs" / "demos"
        html = (directory / "index.html").read_text(encoding="utf-8")
        assets = StaticAssets()
        assets.feed(html)
        self.assertIn('href="https://pifuyuini.github.io/genea/"', html)
        self.assertIn('href="../demo2/"', html)
        for value in assets.assets:
            self.assertFalse(value.startswith("/"), value)
            if not value.startswith("https:"):
                self.assertTrue((directory / value).exists(), value)
        self.assertIn("Demo1 · 保留旧版", html)
        self.assertIn("Demo2 · 新版实验", html)
        self.assertIn("两份演示都只供查看", html)
        self.assertIn("@media (max-width: 640px)", html)
        self.assertEqual(html, (ROOT / "demo2" / "demos.html").read_text(encoding="utf-8"))

    def test_builder_refuses_docs_root_and_source(self):
        for path in [ROOT / "docs", ROOT, ROOT / "demo2", ROOT / "static", ROOT / "docs" / "photos"]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                pages.output_path(path)
        self.assertEqual(pages.output_path(), ROOT / "docs" / "demo2")

    @unittest.skipUnless(JSC.is_file(), "macOS system JavaScriptCore is unavailable")
    def test_browser_query_matches_python_for_every_person_and_relative_word(self):
        cases = []
        for person in self.workspace["people"].values():
            for word in query._RELATIVE_TYPES:
                cases.append({"text": person["name"] + "的" + word + "有哪些"})
        cases += [
            {"text": ""},
            {"text": None},
            {"text": "给家谱写一首诗"},
            {"text": "奥雷里亚诺上校的朋友有哪些"},
            {"text": "不存在的人和乌尔苏拉是什么关系"},
            {"text": "奥雷里亚诺的子女有哪些"},
            {"text": "奥雷里亚诺的子女有哪些", "resolutions": {"0": "person_colonel"}},
            {"text": "奥雷里亚诺的子女有哪些", "resolutions": {"0": "person_gaston"}},
            {"text": "奥雷里亚诺上校的子女有哪些", "resolutions": {"9": "person_colonel"}},
            {"text": "奥雷里亚诺上校的子女有哪些", "resolutions": []},
            {"text": "奥雷里亚诺·何塞和阿玛兰妲是什么关系"},
            {"text": "阿玛兰妲是奥雷里亚诺·何塞的什么人"},
            {"text": "阿玛兰妲和奥雷里亚诺·何塞之间有什么关系"},
            {"text": "请问，“奥雷里亚诺·何塞”与「阿玛兰妲」是什么亲戚？"},
            {"text": "查一下奥雷里亚诺上校的子女有哪些。"},
            {"text": "丽贝卡的亲生父母有哪些"},
            {"text": "丽贝卡的养父母有哪些"},
            {"text": "丽贝卡和尼卡诺尔是什么关系"},
            {"text": "奥雷里亚诺上校和奥雷里亚诺上校是什么关系"},
            {"text": "佩特拉跟加斯通是什么关系"},
            {"text": "阿玛兰妲·乌尔苏拉的外甥有哪些"},
            {"text": "奥雷里亚诺·何塞的表兄弟有哪些"},
            {"text": "REMEDIOS LA BELLA的父母有哪些"},
        ]
        for source in self.workspace["people"].values():
            for target in self.workspace["people"].values():
                cases.append({"text": source["name"] + "和" + target["name"] + "是什么关系"})
        for case in cases:
            case["expected"] = projected(query.run_query(self.workspace, case["text"], case.get("resolutions")))
        result = subprocess.run([str(JSC), "tests/test_demo2_query.js"], cwd=ROOT,
                                input=json.dumps(cases, ensure_ascii=True) + "\n", text=True,
                                capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout[-5000:] + result.stderr[-5000:])
        self.assertIn("PASS", result.stdout)
        print(result.stdout.strip())

    @unittest.skipUnless(JSC.is_file(), "macOS system JavaScriptCore is unavailable")
    def test_browser_adapter_and_actual_app_api(self):
        result = subprocess.run([str(JSC), "tests/test_demo2_readonly.js"], cwd=ROOT,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout[-5000:] + result.stderr[-5000:])
        self.assertIn("PASS", result.stdout)
        print(result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
