import copy
import itertools
import unittest

import genealogy_core as core
from kinship_appellation import infer_familiar_appellation, is_family_relationship
from kinship_composition import compose_registered_connection
from kinship_inference import infer_direct_relationship
from test_kinship_composition import chain
import test_kinship_composition as composition_tests
from test_kinship_inference import graph


class FamiliarAppellationTests(unittest.TestCase):
    def query(self, workspace, source, target):
        legacy = core.relationship_path(workspace, source, target)
        blood = infer_direct_relationship(workspace, source, target)
        composition = compose_registered_connection(workspace, source, target)
        before = copy.deepcopy(workspace)
        result = core.relationship_query(workspace, source, target)
        direct = result["direct_relationship"]
        self.assertEqual((direct["status"], direct["results"]), ("unsupported", []))
        self.assertEqual({key: result[key] for key in legacy}, legacy)
        self.assertEqual({key: direct[key] for key in blood}, blood)
        self.assertEqual(direct["composition"], composition)
        self.assertEqual(workspace, before)
        appellation = direct["appellation"]
        self.assertEqual(set(appellation), {"label", "explanation", "note"})
        self.assertTrue(all(isinstance(value, str) and value for value in appellation.values()))
        self.assertIn("详细连接可展开查看", appellation["note"])
        return result, appellation

    def test_xue_pan_and_jia_zhen_are_familiar_cousins_in_both_directions(self):
        workspace, people = composition_tests.KinshipCompositionTests().example()
        for source, target in ((people[0], people[-1]), (people[-1], people[0])):
            with self.subTest(source=source):
                result, appellation = self.query(workspace, source, target)
                self.assertEqual(appellation["label"], "表兄弟（平辈，长幼未知）")
                self.assertIn("王夫人", appellation["explanation"])
                self.assertIn("贾政", appellation["explanation"])
                self.assertIn("贾珠", appellation["explanation"])
                self.assertIn("完整家庭路径：", appellation["explanation"])
                self.assertNotIn("person_", appellation["explanation"])
                self.assertNotIn("无法", appellation["note"])
                self.assertNotIn("血缘", appellation["note"])

    def test_female_target_is_familiar_female_cousin_without_age_guess(self):
        workspace, people = composition_tests.KinshipCompositionTests().example()
        core.update_person(workspace, people[-1], {"gender": "female", "name": "姐姐"})
        result, appellation = self.query(workspace, people[0], people[-1])
        self.assertEqual(appellation["label"], "表姐妹（平辈，长幼未知）")
        reverse, reverse_appellation = self.query(workspace, people[-1], people[0])
        self.assertEqual(reverse_appellation["label"], "表兄弟（平辈，长幼未知）")

    def test_one_collateral_segment_plus_shared_child_is_enough_for_daily_cousins(self):
        workspace, people = chain("UUDDUD", genders=["male", "female", "male", "female", "male", "male", "female"])
        for source, target, label in ((people[0], people[-1], "表姐妹（平辈，长幼未知）"), (people[-1], people[0], "表兄弟（平辈，长幼未知）")):
            with self.subTest(source=source):
                self.assertEqual(self.query(workspace, source, target)[1]["label"], label)

    def test_direct_shared_child_parents_keep_parent_role_for_all_genders(self):
        for left, child, right in itertools.product(("male", "female"), repeat=3):
            with self.subTest(left=left, child=child, right=right):
                workspace, people = chain("DU", genders=[left, child, right])
                for source, target, gender in ((people[0], people[2], right), (people[2], people[0], left)):
                    result, appellation = self.query(workspace, source, target)
                    self.assertEqual(appellation["label"], "孩子的" + ("父亲" if gender == "male" else "母亲"))
                    self.assertNotIn("表", appellation["label"])

    def test_more_than_two_parents_all_keep_the_shared_child_role(self):
        workspace = graph({"a": (0, "male"), "b": (0, "female"), "c": (0, "male"), "child": (1, "female")}, [("a", "child"), ("b", "child"), ("c", "child")])
        for source, target in itertools.permutations(("a", "b", "c"), 2):
            with self.subTest(source=source, target=target):
                gender = workspace["people"][target]["gender"]
                self.assertEqual(self.query(workspace, source, target)[1]["label"], "孩子的" + ("父亲" if gender == "male" else "母亲"))

    def test_shared_grandchild_without_collateral_segment_is_same_generation_kin(self):
        workspace, people = chain("DDUU")
        self.assertEqual(self.query(workspace, people[0], people[-1])[1]["label"], "平辈亲戚")

    def test_multiple_bridges_without_collateral_segment_are_same_generation_kin(self):
        for steps in ("DUDU", "DUDUDU", "UDUD"):
            with self.subTest(steps=steps):
                workspace, people = chain(steps)
                self.assertEqual(self.query(workspace, people[0], people[-1])[1]["label"], "平辈亲戚")

    def test_multiple_bridges_with_a_collateral_segment_are_familiar_cousins(self):
        workspace, people = chain("UUDDUDUD")
        result, appellation = self.query(workspace, people[0], people[-1])
        self.assertEqual(appellation["label"], "表兄弟（平辈，长幼未知）")
        self.assertIn("人物3 → 人物4 → 人物5", appellation["explanation"])
        self.assertIn("人物5 → 人物6 → 人物7", appellation["explanation"])

    def test_mixed_older_relatives_have_familiar_generation_categories(self):
        categories = {1: ("叔伯辈亲戚", "姑姨辈亲戚"), 2: ("祖父辈亲戚", "祖母辈亲戚"), 3: ("曾祖父辈亲戚", "曾祖母辈亲戚"), 4: ("高祖父辈亲戚", "高祖母辈亲戚"), 6: ("高祖辈以上的男性长辈亲戚", "高祖辈以上的女性长辈亲戚")}
        for distance, labels in categories.items():
            for index, gender in enumerate(("male", "female")):
                with self.subTest(distance=distance, gender=gender):
                    steps = "UUDDU" + "U" * (distance - 1)
                    genders = ["male"] * len(steps) + [gender]
                    workspace, people = chain(steps, genders=genders)
                    result, appellation = self.query(workspace, people[0], people[-1])
                    self.assertEqual(appellation["label"], labels[index])
                    self.assertIn(f"长{distance}辈", appellation["explanation"])

    def test_mixed_younger_relatives_have_familiar_generation_categories(self):
        categories = {1: ("侄甥辈亲戚", "侄甥女辈亲戚"), 2: ("孙子辈亲戚", "孙女辈亲戚"), 3: ("曾孙辈亲戚", "曾孙女辈亲戚"), 4: ("玄孙辈亲戚", "玄孙女辈亲戚"), 6: ("玄孙辈以下的男性晚辈亲戚", "玄孙辈以下的女性晚辈亲戚")}
        for distance, labels in categories.items():
            for index, gender in enumerate(("male", "female")):
                with self.subTest(distance=distance, gender=gender):
                    steps = "DUUDD" + "D" * (distance - 1)
                    genders = ["male"] * len(steps) + [gender]
                    workspace, people = chain(steps, genders=genders)
                    result, appellation = self.query(workspace, people[0], people[-1])
                    self.assertEqual(appellation["label"], labels[index])
                    self.assertIn(f"晚{distance}辈", appellation["explanation"])

    def test_older_connection_without_collateral_uses_parent_generation_category(self):
        workspace, people = chain("DUU", genders=["male", "male", "male", "female"])
        self.assertEqual(self.query(workspace, people[0], people[-1])[1]["label"], "母亲辈亲戚")

    def test_literal_family_special_pairs_are_recognized_with_gender_consistency(self):
        cases = [("养父", "养子", "male", "male"), ("养母", "养女", "female", "female"), ("继母", "继子", "female", "male"), ("义父", "义女", "male", "female"), ("嫡母", "庶女", "female", "female"), ("庶父", "嫡子", "male", "male"), ("爸爸", "孩子", "male", "female"), ("母亲", "女儿", "female", "female")]
        for parent_label, child_label, parent_gender, child_gender in cases:
            with self.subTest(parent=parent_label, child=child_label):
                workspace, people = chain("u", genders=[child_gender, parent_gender], special_labels={0: (parent_label, child_label)})
                self.assertTrue(is_family_relationship(workspace, workspace["relationships"][0]))
                self.assertEqual(self.query(workspace, people[0], people[1])[1]["label"], parent_label)
                self.assertEqual(self.query(workspace, people[1], people[0])[1]["label"], child_label)
                self.assertEqual(infer_direct_relationship(workspace, people[0], people[1])["status"], "unsupported")

    def test_family_specials_connect_daily_kin_without_entering_blood_graph(self):
        workspace, people = chain("uUDDUD", genders=["male", "female", "male", "female", "male", "male", "male"], special_labels={0: ("养母", "养子")})
        result, appellation = self.query(workspace, people[0], people[-1])
        self.assertEqual(appellation["label"], "表兄弟（平辈，长幼未知）")
        self.assertIn("家庭登记称谓：人物0 → 人物1（养母）", appellation["explanation"])
        self.assertIn("“养母”（登记特殊称谓）", result["direct_relationship"]["composition"]["label"])

    def test_pure_family_special_chain_can_use_existing_grandparent_terms(self):
        workspace, people = chain("uU", special_labels={0: ("养父", "养子")})
        self.assertEqual(self.query(workspace, people[0], people[-1])[1]["label"], "祖父")
        self.assertEqual(self.query(workspace, people[-1], people[0])[1]["label"], "孙子")

    def test_teacher_classmate_long_text_and_mismatched_roles_do_not_make_family(self):
        cases = [("师父", "徒弟", "male", "male"), ("同学", "同学", "male", "male"), ("养父（实际上是老师）", "养子", "male", "male"), ("养父", "继子", "male", "male"), ("养母", "养女", "male", "male"), ("爸爸", "女儿", "male", "male")]
        for parent_label, child_label, parent_gender, child_gender in cases:
            with self.subTest(parent=parent_label, child=child_label):
                genders = [child_gender, parent_gender] + ["male"] * 5
                workspace, people = chain("uUDDUD", genders=genders, special_labels={0: (parent_label, child_label)})
                self.assertFalse(is_family_relationship(workspace, workspace["relationships"][0]))
                result = core.relationship_query(workspace, people[0], people[-1])
                self.assertNotIn("appellation", result["direct_relationship"])
                self.assertIn("composition", result["direct_relationship"])

    def test_single_nonfamily_special_uses_only_the_registered_name(self):
        workspace, people = chain("u", special_labels={0: ("师父", "徒弟")})
        result, appellation = self.query(workspace, people[0], people[1])
        self.assertEqual(appellation["label"], "师父")
        self.assertIn("完整登记路径：人物0 → 人物1。", appellation["explanation"])
        self.assertEqual(self.query(workspace, people[1], people[0])[1]["label"], "徒弟")

    def test_multiple_unknown_specials_keep_only_original_composition(self):
        workspace, people = chain("du", special_labels={0: ("老师", "学生"), 1: ("师父", "徒弟")})
        result = core.relationship_query(workspace, people[0], people[-1])
        self.assertEqual(result["direct_relationship"]["status"], "unsupported")
        self.assertNotIn("appellation", result["direct_relationship"])
        self.assertIn("登记特殊称谓", result["direct_relationship"]["composition"]["label"])

    def test_family_evidence_can_be_longer_than_the_old_teacher_shortcut(self):
        workspace, people = chain("UUDDU")
        shortcut = core.add_relationship(workspace, people[-1], people[0])
        core.update_relationship(workspace, shortcut["id"], {"kind": "special", "parent_label": "老师", "child_label": "学生"})
        result, appellation = self.query(workspace, people[0], people[-1])
        self.assertEqual(result["path_text"], "老师")
        self.assertEqual(result["person_ids"], [people[0], people[-1]])
        self.assertEqual(appellation["label"], "叔伯辈亲戚")
        self.assertIn("完整家庭路径：人物0 → 人物1 → 人物2 → 人物3 → 人物4 → 人物5。", appellation["explanation"])
        self.assertNotIn("老师", appellation["explanation"])

    def test_blood_resolved_and_disconnected_and_self_keep_exact_results(self):
        workspace = graph({"grand": (0, "male"), "parent": (1, "male"), "aunt": (1, "female"), "ego": (2, "male"), "isolated": (2, "female")}, [("grand", "parent"), ("grand", "aunt"), ("parent", "ego"), ("aunt", "ego", "special")])
        for source, target in (("ego", "aunt"), ("ego", "grand"), ("ego", "isolated"), ("ego", "ego")):
            with self.subTest(source=source, target=target):
                expected = infer_direct_relationship(workspace, source, target)
                result = core.relationship_query(workspace, source, target)
                self.assertEqual(result["direct_relationship"], expected)
                self.assertNotIn("appellation", result["direct_relationship"])

    def test_multiple_precise_blood_labels_are_not_replaced_with_daily_generalization(self):
        workspace = graph({"grand": (0, "male"), "father": (1, "male"), "aunt": (1, "female"), "other": (1, "male"), "ego": (2, "male"), "target": (2, "female")}, [("grand", "father"), ("grand", "aunt"), ("father", "ego"), ("aunt", "target"), ("other", "ego"), ("other", "target")])
        expected = infer_direct_relationship(workspace, "ego", "target")
        self.assertEqual(core.relationship_query(workspace, "ego", "target")["direct_relationship"], expected)
        self.assertEqual(len(expected["results"]), 2)

    def test_names_edges_dictionary_order_and_unique_id_replacement_do_not_change_structure(self):
        workspace, people = composition_tests.KinshipCompositionTests().example()
        before = copy.deepcopy(workspace)
        expected = infer_familiar_appellation(workspace, people[0], people[-1])
        self.assertEqual(workspace, before)
        changed = copy.deepcopy(workspace)
        changed["relationships"].reverse()
        changed["people"] = dict(reversed(list(changed["people"].items())))
        self.assertEqual(infer_familiar_appellation(changed, people[0], people[-1]), expected)
        replacements = {person_id: f"renamed_{100 - index}" for index, person_id in enumerate(people)}
        changed["people"] = {replacements[person_id]: {**person, "id": replacements[person_id]} for person_id, person in changed["people"].items()}
        for relationship in changed["relationships"]:
            relationship["parent_id"] = replacements[relationship["parent_id"]]
            relationship["child_id"] = replacements[relationship["child_id"]]
            relationship["id"] = "renamed_" + relationship["id"]
        self.assertEqual(infer_familiar_appellation(changed, replacements[people[0]], replacements[people[-1]]), expected)
        for person in changed["people"].values():
            person.update({"name": "妈妈姐姐师父", "introduction": "妻子", "order": -99})
        renamed = infer_familiar_appellation(changed, replacements[people[0]], replacements[people[-1]])
        self.assertEqual(renamed["label"], expected["label"])
        self.assertEqual(renamed["note"], expected["note"])
        self.assertNotIn("renamed_", renamed["explanation"])

    def test_duplicate_shared_children_choose_stable_daily_evidence(self):
        workspace = graph({"a": (0, "male"), "b": (0, "female"), "c_first": (1, "male"), "c_last": (1, "female")}, [("a", "c_last"), ("b", "c_last"), ("a", "c_first"), ("b", "c_first")])
        workspace["people"]["c_first"]["name"] = "后排序名字"
        workspace["people"]["c_last"]["name"] = "前排序名字"
        expected = self.query(workspace, "a", "b")[1]
        self.assertEqual(expected["label"], "孩子的母亲")
        self.assertIn("后排序名字", expected["explanation"])
        self.assertNotIn("前排序名字", expected["explanation"])
        workspace["relationships"].reverse()
        self.assertEqual(self.query(workspace, "a", "b")[1], expected)

    def test_missing_names_are_display_placeholders(self):
        workspace, people = chain("UUDDUD")
        for person in workspace["people"].values():
            person.pop("name")
        result, appellation = self.query(workspace, people[0], people[-1])
        self.assertEqual(appellation["label"], "表兄弟（平辈，长幼未知）")
        self.assertIn("未命名人物", appellation["explanation"])
        self.assertNotIn("person_", appellation["explanation"])

    def test_unknown_person_still_raises_core_not_found(self):
        workspace, people = chain("DU")
        with self.assertRaises(core.NotFoundError):
            core.relationship_query(workspace, people[0], "missing")


if __name__ == "__main__":
    unittest.main()
