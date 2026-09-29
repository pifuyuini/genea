import importlib.util
import json
import unittest
from pathlib import Path

import genealogy_core as core

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_demo", ROOT / "demo" / "build_demo.py")
build_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_demo)


class DemoDataTests(unittest.TestCase):
    def setUp(self):
        self.workspace = json.loads((ROOT / "demo" / "data" / "workspace.json").read_text(encoding="utf-8"))
        self.ids = {person["name"]: person["id"] for person in self.workspace["people"].values()}

    def test_snapshot_matches_build_script(self):
        self.assertEqual(build_demo.render(build_demo.build()), (ROOT / "demo" / "data" / "workspace.json").read_text(encoding="utf-8"))

    def test_demo_is_a_valid_connected_family(self):
        workspace = core.ensure_workspace(self.workspace)
        self.assertEqual((len(workspace["generations"]), len(workspace["people"]), len(workspace["relationships"])), (6, 38, 42))
        self.assertNotIn("_history", self.workspace)
        photos = ROOT / "demo" / "data" / "photos"
        self.assertEqual({person["photo_path"] for person in workspace["people"].values()},
                         {"/photos/" + path.name for path in photos.glob("*.jpg")})
        self.assertEqual(core.remove_nonadjacent_relationships(workspace), [])
        linked = {person_id for item in workspace["relationships"] for person_id in (item["parent_id"], item["child_id"])}
        self.assertEqual(linked, set(workspace["people"]))
        # Marriages are not parent-child links, so the Qin family joins the Jia clan only through Qin Keqing's marriage.
        root = self.ids["贾氏始祖"]
        unreachable = {person["name"] for person_id, person in workspace["people"].items()
                       if person_id != root and not core.relationship_path(workspace, root, person_id)["relationship_ids"]}
        self.assertEqual(unreachable, {"秦业", "秦钟", "秦可卿"})

    def test_kinship_examples_follow_the_novel(self):
        path = lambda a, b: core.relationship_path(self.workspace, self.ids[a], self.ids[b])["path_text"]
        self.assertEqual(path("贾宝玉", "薛宝钗"), "妈妈的爸爸的女儿的女儿")
        self.assertEqual(path("巧姐", "贾母"), "爸爸的爸爸的妈妈")
        self.assertEqual(path("贾迎春", "邢夫人"), "嫡母")
        self.assertEqual(path("秦可卿", "秦业"), "养父")
        self.assertEqual(path("贾蓉", "尤氏"), "继母")


if __name__ == "__main__":
    unittest.main()
