import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import genealogy_core as core

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "demo2"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load_module("genea_demo2_builder", DEMO / "build_demo.py")
launcher = load_module("genea_demo2_launcher", DEMO / "run_demo.py")


class Demo2DataTests(unittest.TestCase):
    def setUp(self):
        self.workspace = json.loads((DEMO / "data" / "workspace.json").read_text(encoding="utf-8"))
        self.people = self.workspace["people"]
        self.relationships = self.workspace["relationships"]

    def person(self, key):
        return self.people["person_" + key]

    def parents(self, key, kind="standard"):
        return {item["parent_id"] for item in self.relationships if item["child_id"] == "person_" + key and item["kind"] == kind}

    def labels(self, source, target):
        return [result["label"] for result in core.relationship_query(self.workspace, "person_" + source, "person_" + target)["direct_relationship"]["results"]]

    def test_snapshot_rebuild_is_byte_identical_with_fixed_ids_and_dates(self):
        original_new_id, original_now = core.new_id, core.now
        self.assertEqual(builder.render(builder.build()), (DEMO / "data" / "workspace.json").read_text(encoding="utf-8"))
        self.assertEqual(builder.render(builder.build()), builder.render(self.workspace))
        self.assertIs(core.new_id, original_new_id)
        self.assertIs(core.now, original_now)
        for person in self.people.values():
            self.assertEqual((person["created_at"], person["updated_at"]), ("2026-10-04T00:00:00+00:00",) * 2)
        for relationship in self.relationships:
            self.assertEqual((relationship["created_at"], relationship["updated_at"]), ("2026-10-04T00:00:00+00:00",) * 2)

    def test_seven_rows_forty_six_people_and_fifty_three_typed_edges(self):
        self.assertEqual(core.ensure_workspace(self.workspace), self.workspace)
        self.assertEqual((len(self.workspace["generations"]), len(self.people), len(self.relationships)), (7, 46, 53))
        self.assertEqual(sum(item["kind"] == "standard" for item in self.relationships), 49)
        self.assertEqual(sum(item["kind"] == "special" for item in self.relationships), 4)
        self.assertEqual(len({person["photo_path"] for person in self.people.values()}), 46)
        self.assertTrue(all((DEMO / "data" / person["photo_path"].lstrip("/")).is_file() for person in self.people.values()))
        self.assertEqual([generation["name"] for generation in self.workspace["generations"]], ["第一代", "第二代", "第三代", "第四代", "第五代", "第六代", "第七代"])
        self.assertEqual([generation["position"] for generation in self.workspace["generations"]], list(range(7)))
        counts = [sum(person["generation_id"] == generation["id"] for person in self.people.values()) for generation in self.workspace["generations"]]
        self.assertEqual(counts, [5, 7, 22, 5, 5, 1, 1])
        self.assertEqual(len({item["id"] for item in self.relationships}), 53)
        self.assertNotIn("_history", self.workspace)

    def test_main_line_precedes_seventeen_independent_sons_in_third_row(self):
        generation = self.workspace["generations"][2]
        ordered = sorted((person for person in self.people.values() if person["generation_id"] == generation["id"]), key=lambda person: person["order"])
        self.assertEqual([person["id"] for person in ordered[:5]], ["person_arcadio", "person_aureliano_jose", "person_santa_sofia", "person_fernando", "person_renata_argote"])
        expected_sons = ["a_triste", "a_centeno", "a_serrador", "a_arcaya", "a_amador"] + [f"a_unknown_{index:02d}" for index in range(1, 13)]
        self.assertEqual([person["id"] for person in ordered[5:]], ["person_" + key for key in expected_sons])
        self.assertEqual([person["order"] for person in ordered], list(range(22)))
        for key in expected_sons:
            self.assertEqual(self.parents(key), {"person_colonel"})
            self.assertEqual(self.person(key)["gender"], "male")
        self.assertEqual({item["child_id"] for item in self.relationships if item["parent_id"] == "person_colonel" and item["kind"] == "standard"}, {"person_" + key for key in ["aureliano_jose", *expected_sons]})
        self.assertEqual(len({self.person(key)["id"] for key in expected_sons}), 17)

    def test_unknown_twelve_are_not_a_birth_order_or_shared_mother(self):
        unknown = [self.person(f"a_unknown_{index:02d}") for index in range(1, 13)]
        self.assertEqual(len(unknown), 12)
        self.assertTrue(all(person["name"].startswith("奥雷里亚诺（未详名") for person in unknown))
        self.assertTrue(all(person["introduction"].startswith("Aureliano。") for person in unknown))
        self.assertTrue(all("不表示出生排行" in person["introduction"] for person in unknown))
        self.assertTrue(all("各母不同" in person["introduction"] for person in unknown))
        self.assertEqual(sum(person["id"].startswith("person_a_unknown_") for person in self.people.values()), 12)
        for index in range(1, 13):
            self.assertEqual(self.parents(f"a_unknown_{index:02d}"), {"person_colonel"})

    def test_rebeca_biological_and_adoptive_parents_are_distinct(self):
        self.assertEqual(self.parents("rebeca"), {"person_nicanor_ulloa", "person_rebeca_montiel"})
        self.assertEqual(self.parents("rebeca", "special"), {"person_founder", "person_ursula"})
        self.assertEqual(self.labels("rebeca", "nicanor_ulloa"), ["父亲"])
        self.assertEqual(self.labels("rebeca", "rebeca_montiel"), ["母亲"])
        for parent, label in (("founder", "养父"), ("ursula", "养母")):
            result = core.relationship_query(self.workspace, "person_rebeca", "person_" + parent)
            self.assertEqual(result["path_text"], label)
            self.assertEqual(result["direct_relationship"]["status"], "unsupported")
            self.assertEqual(result["direct_relationship"]["appellation"]["label"], label)

    def test_aureliano_jose_adoptions_keep_their_two_explicit_records(self):
        self.assertEqual(self.parents("aureliano_jose"), {"person_colonel", "person_pilar"})
        self.assertEqual(self.parents("aureliano_jose", "special"), {"person_remedios_moscote", "person_amaranta"})
        relationships = {(item["parent_id"], item["child_id"]): item for item in self.relationships}
        for parent in ("remedios_moscote", "amaranta"):
            item = relationships[("person_" + parent, "person_aureliano_jose")]
            self.assertEqual((item["parent_label"], item["child_label"]), ("养母", "养子"))
        introduction = self.person("aureliano_jose")["introduction"]
        self.assertIn("先由蕾梅黛丝", introduction)
        self.assertIn("后来由阿玛兰妲", introduction)

    def test_amaranta_adoptive_chain_and_blood_aunt_result_are_separate(self):
        result = core.relationship_query(self.workspace, "person_aureliano_jose", "person_amaranta")
        self.assertEqual((result["path_text"], result["relationship_ids"]), ("养母", ["rel_amaranta__aureliano_jose"]))
        direct = result["direct_relationship"]
        self.assertEqual(direct["status"], "resolved")
        self.assertIn("姑母", [item["label"] for item in direct["results"]])
        self.assertTrue(any("奥雷里亚诺·布恩迪亚上校" in item["explanation"] for item in direct["results"] if item["label"] == "姑母"))
        self.assertNotIn("appellation", direct)
        self.assertNotIn("养母", [item["label"] for item in direct["results"]])

    def test_arcadio_and_aureliano_jose_keep_sibling_and_cousin_results(self):
        expected = ["兄弟（长幼未知）", "堂兄弟（长幼未知）"]
        self.assertEqual(self.labels("arcadio", "aureliano_jose"), expected)
        self.assertEqual(self.labels("aureliano_jose", "arcadio"), expected)
        result = core.relationship_query(self.workspace, "person_arcadio", "person_aureliano_jose")["direct_relationship"]
        self.assertIn("存在多重亲缘", result["note"])
        self.assertIn("庇拉尔", result["results"][0]["explanation"])
        self.assertTrue(all("同胞" not in item["label"] for item in result["results"]))

    def test_last_child_has_fifth_row_mother_and_sixth_row_father(self):
        self.assertEqual(self.parents("aureliano_last"), {"person_aureliano_babilonia", "person_amaranta_ursula"})
        positions = {generation["id"]: generation["position"] for generation in self.workspace["generations"]}
        spans = [(item["parent_id"], item["child_id"], positions[self.people[item["child_id"]]["generation_id"]] - positions[self.people[item["parent_id"]]["generation_id"]]) for item in self.relationships]
        self.assertEqual([(parent, child, span) for parent, child, span in spans if span != 1], [("person_amaranta_ursula", "person_aureliano_last", 2)])
        self.assertEqual((positions[self.person("amaranta_ursula")["generation_id"]], positions[self.person("aureliano_babilonia")["generation_id"]], positions[self.person("aureliano_last")["generation_id"]]), (4, 5, 6))
        self.assertIn("母亲", self.labels("aureliano_last", "amaranta_ursula"))
        self.assertIn("父亲", self.labels("aureliano_last", "aureliano_babilonia"))
        self.assertEqual(core.relationship_path(self.workspace, "person_aureliano_last", "person_amaranta_ursula")["path_text"], "妈妈")

    def test_no_marriage_edges_or_false_children_and_isolated_roles_are_preserved(self):
        pairs = [("jose_arcadio", "rebeca"), ("colonel", "remedios_moscote"), ("gaston", "amaranta_ursula"), ("petra", "jose_segundo"), ("petra", "aureliano_segundo"), ("founder", "ursula")]
        endpoints = [{item["parent_id"], item["child_id"]} for item in self.relationships]
        for left, right in pairs:
            self.assertNotIn({"person_" + left, "person_" + right}, endpoints)
        linked = {person_id for item in self.relationships for person_id in (item["parent_id"], item["child_id"])}
        self.assertEqual(set(self.people) - linked, {"person_petra", "person_gaston"})
        for key in ("petra", "gaston"):
            result = core.relationship_query(self.workspace, "person_" + key, "person_founder")
            self.assertEqual(result["direct_relationship"]["status"], "disconnected")

    def test_all_two_thousand_one_hundred_sixteen_queries_preserve_contract_and_order(self):
        reversed_workspace = copy.deepcopy(self.workspace)
        reversed_workspace["relationships"].reverse()
        before = copy.deepcopy(self.workspace)
        queries = 0
        for source in self.people:
            for target in self.people:
                with self.subTest(source=source, target=target):
                    query = core.relationship_query(self.workspace, source, target)
                    legacy = core.relationship_path(self.workspace, source, target)
                    self.assertEqual(set(query), {"path_text", "person_ids", "relationship_ids", "direct_relationship"})
                    self.assertEqual({key: query[key] for key in legacy}, legacy)
                    direct = query["direct_relationship"]
                    self.assertIn(direct["status"], {"resolved", "unsupported", "disconnected"})
                    self.assertIsInstance(direct["note"], str)
                    self.assertEqual(len({item["label"] for item in direct["results"]}), len(direct["results"]))
                    for item in direct["results"]:
                        self.assertEqual(set(item), {"label", "explanation"})
                        self.assertTrue(item["label"] and item["explanation"])
                    if source == target:
                        self.assertEqual(direct["results"][0]["label"], "自己")
                    for field in ("composition", "appellation"):
                        if field in direct:
                            self.assertEqual(set(direct[field]), {"label", "explanation", "note"})
                            self.assertTrue(all(isinstance(value, str) and value for value in direct[field].values()))
                    reversed_query = core.relationship_query(reversed_workspace, source, target)
                    self.assertEqual(reversed_query["direct_relationship"], direct)
                    reversed_legacy = core.relationship_path(reversed_workspace, source, target)
                    self.assertEqual({key: reversed_query[key] for key in reversed_legacy}, reversed_legacy)
                    queries += 1
        self.assertEqual(queries, 2116)
        self.assertEqual(self.workspace, before)


class Demo2LauncherTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(os.environ.get("GENEA_TEST_TMP", ROOT / "tmp"))
        temp_root.mkdir(parents=True, exist_ok=True)
        prefix = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-demo2-launcher-")
        self.directory = tempfile.TemporaryDirectory(prefix=prefix, dir=temp_root)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        (self.root / ".codex-tmp").write_text("Created by Demo2 launcher tests.\n", encoding="utf-8")

    def test_default_launch_creates_marked_independent_sessions_and_keeps_old_edits(self):
        with patch.object(launcher, "ROOT", self.root):
            first = launcher.prepare_data_directory()
            first_snapshot = first / "workspace.json"
            first_snapshot.write_text("preserved demo edit", encoding="utf-8")
            second = launcher.prepare_data_directory()
        self.assertNotEqual(first, second)
        self.assertTrue((first.parent / ".codex-tmp").is_file())
        self.assertTrue((second.parent / ".codex-tmp").is_file())
        self.assertTrue(first.parent.is_relative_to(self.root / "tmp"))
        self.assertEqual(first_snapshot.read_text(encoding="utf-8"), "preserved demo edit")
        self.assertEqual((second / "workspace.json").read_text(encoding="utf-8"), (DEMO / "data" / "workspace.json").read_text(encoding="utf-8"))
        expected_photos = {path.name for path in (DEMO / "data" / "photos").iterdir()}
        self.assertEqual(len(expected_photos), 46)
        self.assertEqual({path.name for path in (second / "photos").iterdir()}, expected_photos)
        for name in expected_photos:
            self.assertEqual((second / "photos" / name).read_bytes(), (DEMO / "data" / "photos" / name).read_bytes())

    def test_explicit_reuse_does_not_reset_or_copy_existing_edits(self):
        target = self.root / "existing" / "data"
        target.mkdir(parents=True)
        snapshot = target / "workspace.json"
        snapshot.write_text("existing edit", encoding="utf-8")
        self.assertEqual(launcher.prepare_data_directory(target), target)
        self.assertEqual(snapshot.read_text(encoding="utf-8"), "existing edit")
        self.assertEqual(set(target.iterdir()), {snapshot})

    def test_refuses_real_and_committed_demo_data_including_descendants(self):
        for protected in (ROOT / "data", ROOT / "demo" / "data", DEMO / "data"):
            for target in (protected, protected / "photos"):
                with self.subTest(target=str(target)), self.assertRaises(ValueError):
                    launcher.prepare_data_directory(target)

    def test_explicit_missing_or_empty_directory_is_not_initialized(self):
        absent = self.root / "absent"
        with self.assertRaises(ValueError):
            launcher.prepare_data_directory(absent)
        self.assertFalse(absent.exists())
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaises(ValueError):
            launcher.prepare_data_directory(empty)
        self.assertEqual(list(empty.iterdir()), [])

    def test_default_server_arguments_enable_isolated_cross_generation_mode(self):
        with patch.object(launcher, "ROOT", self.root), patch.object(launcher.subprocess, "call", return_value=0) as launch, patch("builtins.print"):
            self.assertEqual(launcher.main([]), 0)
        arguments = launch.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--port") + 1], "8767")
        self.assertIn("--experimental-cross-generation", arguments)
        data_dir = Path(arguments[arguments.index("--data-dir") + 1])
        self.assertTrue(data_dir.is_relative_to(self.root / "tmp"))
        self.assertTrue((data_dir / "workspace.json").is_file())
        self.assertTrue((data_dir.parent / ".codex-tmp").is_file())


if __name__ == "__main__":
    unittest.main()
