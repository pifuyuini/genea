import copy
import unittest
from unittest.mock import patch

import genealogy_core as core
import kinship_naming as naming
from kinship_inference import infer_direct_relationship
from test_kinship_inference import graph


def arms(up, down, *, source_genders=None, target_genders=None, common_gender="male"):
    """Two disjoint arms of an actual parent graph, with deterministic IDs."""
    source = tuple([f"person_s{i}" for i in range(up)] + ["person_common"])
    target = tuple([f"person_t{i}" for i in range(down)] + ["person_common"])
    source_genders = source_genders or ["male"] * up
    target_genders = target_genders or ["male"] * down
    people = {"person_common": (0, common_gender)}
    for path, distance, genders in ((source, up, source_genders), (target, down, target_genders)):
        people.update({person_id: (distance - index, genders[index]) for index, person_id in enumerate(path[:-1])})
    edges = [(path[index + 1], path[index]) for path in (source, target) for index in range(len(path) - 1)]
    workspace = graph(people, edges)
    for index, person in enumerate(workspace["people"].values()):
        person["name"] = f"合成人物{index}"
    return workspace, source, target


class ExtendedKinshipTests(unittest.TestCase):
    def result(self, up, down, **kwargs):
        workspace, source, target = arms(up, down, **kwargs)
        result = infer_direct_relationship(workspace, source[0], target[0])
        self.assertEqual((result["status"], len(result["results"]), result["note"]), ("resolved", 1, ""))
        return workspace, source, target, result["results"][0]

    def test_canonical_selector_uses_one_proven_sibling_turn(self):
        cases = {(5, 2): "f,f,f,f,xb,s", (5, 1): "f,f,f,f,xb", (3, 2): "f,f,xb,s", (5, 3): "f,f,f,f,xb,s,s", (2, 5): "f,xb,s,s,s,s", (4, 0): "f,f,f,f", (0, 4): "s,s,s,s"}
        for (up, down), expected in cases.items():
            with self.subTest(up=up, down=down):
                workspace, source, target = arms(up, down)
                self.assertEqual(naming.canonical_selector(workspace["people"], source, target), expected)
        workspace, source, target = arms(5, 2, source_genders=["female", "male", "female", "male", "female"], target_genders=["female", "female"])
        self.assertEqual(naming.canonical_selector(workspace["people"], source, target), "f,m,f,m,xs,d")

    def test_jia_lan_to_jia_daihua_has_correct_five_two_generations(self):
        names = {"person_lan": (5, "male"), "person_zhu": (4, "male"), "person_zheng": (3, "male"), "person_daishan": (2, "male"), "person_yuan": (1, "male"), "person_root": (0, "male"), "person_yan": (1, "male"), "person_daihua": (2, "male")}
        lineage = ["person_root", "person_yuan", "person_daishan", "person_zheng", "person_zhu", "person_lan"]
        edges = list(zip(lineage, lineage[1:])) + [("person_root", "person_yan"), ("person_yan", "person_daihua")]
        workspace = graph(names, edges)
        for person_id, name in zip(names, ("贾兰", "贾珠", "贾政", "贾代善", "贾源", "始祖", "贾演", "贾代化")):
            workspace["people"][person_id]["name"] = name
        result = infer_direct_relationship(workspace, "person_lan", "person_daihua")["results"][0]
        self.assertEqual(result["label"], "堂曾祖父")
        self.assertIn("曾祖父的堂兄弟（长幼未知）", result["explanation"])
        self.assertIn("贾兰 → 贾珠 → 贾政 → 贾代善 → 贾源 → 始祖 → 贾演 → 贾代化。", result["explanation"])
        self.assertNotIn("person_", result["explanation"])
        self.assertNotIn("族高祖父", result["label"])
        source = tuple(reversed(lineage))
        target = ("person_daihua", "person_yan", "person_root")
        self.assertEqual(naming.structural_relationship(workspace["people"], source, target, concise=False), "高祖父的兄弟（长幼未知）的儿子")
        yan = infer_direct_relationship(workspace, "person_lan", "person_yan")["results"][0]
        self.assertEqual(yan["label"], "伯叔高祖父（长幼未知）")
        self.assertIn("高祖父的兄弟（长幼未知）", yan["explanation"])

    def test_formal_remote_labels_and_their_actual_structure(self):
        cases = {
            (5, 2): ("堂曾祖父", "曾祖父的堂兄弟（长幼未知）"),
            (5, 1): ("伯叔高祖父（长幼未知）", "高祖父的兄弟（长幼未知）"),
            (4, 2): ("堂祖父", "祖父的堂兄弟（长幼未知）"),
            (3, 2): ("堂伯叔父（长幼未知）", "父亲的堂兄弟（长幼未知）"),
            (5, 3): ("从堂祖父", "曾祖父的堂兄弟（长幼未知）的儿子"),
            (2, 5): ("堂曾孙", "堂兄弟（长幼未知）的曾孙"),
        }
        for (up, down), (label, structure) in cases.items():
            with self.subTest(up=up, down=down):
                workspace, source, target, result = self.result(up, down)
                self.assertEqual(result["label"], label)
                self.assertTrue(result["explanation"].startswith(structure + "；"))
                self.assertNotIn("依据：", result["explanation"])
                self.assertNotIn("person_", result["explanation"])

    def test_remote_relations_in_reverse_are_descendants_of_the_correct_cousin(self):
        cases = {(2, 5): ("堂曾孙", "堂兄弟（长幼未知）的曾孙"), (1, 5): ("侄玄孙", "兄弟（长幼未知）的玄孙"), (2, 4): ("堂侄孙", "堂兄弟（长幼未知）的孙子"), (2, 3): ("堂侄子", "堂兄弟（长幼未知）的儿子"), (3, 5): ("从堂侄孙", "父亲的堂兄弟（长幼未知）的曾孙")}
        for (up, down), (label, structure) in cases.items():
            with self.subTest(up=up, down=down):
                workspace, source, target, result = self.result(up, down)
                self.assertEqual(result["label"], label)
                self.assertTrue(result["explanation"].startswith(structure + "；"))

    def test_female_remote_targets_have_female_formal_names(self):
        cases = {(5, 2): "堂姑曾祖母", (5, 1): "姑高祖母", (4, 2): "堂姑祖母", (3, 2): "堂姑母", (5, 3): "从堂姑祖母", (2, 5): "堂侄曾孙女", (1, 5): "侄玄孙女"}
        for (up, down), label in cases.items():
            with self.subTest(up=up, down=down):
                genders = ["female"] + ["male"] * (down - 1)
                workspace, source, target, result = self.result(up, down, target_genders=genders)
                self.assertEqual(result["label"], label)
                self.assertNotIn("person_", result["explanation"])

    def test_maternal_branches_remain_distinct_and_missing_terms_use_safe_structure(self):
        cases = [(["male", "female", "male"], ["male", "male"], "堂舅父", "母亲的堂兄弟（长幼未知）"), (["male", "male", "female"], ["male", "male"], "父亲的舅表兄弟（长幼未知）", "父亲的舅表兄弟（长幼未知）"), (["male", "male", "female"], ["female", "male"], "舅表姑母", "父亲的舅表姐妹（长幼未知）"), (["male", "male", "male"], ["female", "female"], "姑表姑母", "父亲的姑表姐妹（长幼未知）")]
        for source_genders, target_genders, label, structure in cases:
            with self.subTest(source=source_genders, target=target_genders):
                workspace, source, target, result = self.result(3, 2, source_genders=source_genders, target_genders=target_genders)
                self.assertEqual(result["label"], label)
                self.assertTrue(result["explanation"].startswith(structure + "；"))

    def test_direct_formal_ancestors_and_descendants_keep_target_gender(self):
        for distance in (3, 4):
            for gender in ("male", "female"):
                with self.subTest(distance=distance, gender=gender):
                    workspace, source, target, ancestor = self.result(distance, 0, common_gender=gender)
                    self.assertEqual(ancestor["label"], ("曾祖" if distance == 3 else "高祖") + ("父" if gender == "male" else "母"))
                    target_genders = [gender] + ["male"] * (distance - 1)
                    workspace, source, target, descendant = self.result(0, distance, target_genders=target_genders)
                    self.assertEqual(descendant["label"], ("曾孙" if distance == 3 else "玄孙") + ("" if gender == "male" else "女"))

    def test_maternal_lineal_formal_terms_preserve_the_female_branch(self):
        ancestor_cases = [(["male", "female", "male"], "male", "外曾祖父"), (["male", "male", "female"], "male", "曾外祖父"), (["male", "female", "female"], "female", "外曾外祖母")]
        for genders, common_gender, label in ancestor_cases:
            with self.subTest(genders=genders, common=common_gender):
                self.assertEqual(self.result(3, 0, source_genders=genders, common_gender=common_gender)[3]["label"], label)
        descendant_cases = [(["male", "male", "female"], "外曾孙"), (["male", "female", "male"], "曾外孙"), (["female", "female", "female"], "外曾外孙女")]
        for genders, label in descendant_cases:
            with self.subTest(genders=genders):
                self.assertEqual(self.result(0, 3, target_genders=genders)[3]["label"], label)

    def test_beyond_lexicon_lineal_paths_are_readable_without_numeric_distance(self):
        workspace, source, target, ancestor = self.result(20, 0)
        self.assertNotIn(naming.canonical_selector(workspace["people"], source, target), naming._TERMS)
        self.assertEqual(ancestor["label"], "的".join(["高祖父"] * 5))
        workspace, source, target, descendant = self.result(0, 20, target_genders=["female"] + ["male"] * 19)
        self.assertEqual(descendant["label"], "的".join(["玄孙"] * 4 + ["玄孙女"]))
        for label in (ancestor["label"], descendant["label"]):
            self.assertNotIn("代", label)
            self.assertFalse(any(character.isdigit() for character in label))

    def test_beyond_lexicon_collateral_paths_keep_both_lineal_arms(self):
        workspace, source, target, result = self.result(12, 10)
        self.assertNotIn(naming.canonical_selector(workspace["people"], source, target), naming._TERMS)
        self.assertEqual(result["label"], "高祖父的高祖父的祖父的堂兄弟（长幼未知）的玄孙的玄孙")
        self.assertNotIn("双方距", result["label"])
        self.assertFalse(any(character.isdigit() for character in result["label"]))

    def test_alias_order_never_controls_formal_choice(self):
        workspace, source, target = arms(5, 2)
        selector = naming.canonical_selector(workspace["people"], source, target)
        expected = infer_direct_relationship(workspace, source[0], target[0])
        with patch.dict(naming._TERMS, {selector: list(reversed(naming._TERMS[selector]))}):
            self.assertEqual(infer_direct_relationship(workspace, source[0], target[0]), expected)
        self.assertEqual(expected["results"][0]["label"], "堂曾祖父")

    def test_age_specific_or_informal_only_aliases_fall_back_without_guessing(self):
        workspace, source, target = arms(5, 1)
        selector = naming.canonical_selector(workspace["people"], source, target)
        with patch.dict(naming._TERMS, {selector: ["伯高祖父", "叔高祖父", "太爷爷", "高祖公"]}):
            result = infer_direct_relationship(workspace, source[0], target[0])["results"][0]
        self.assertEqual(result["label"], "高祖父的兄弟（长幼未知）")

    def test_remote_names_and_edge_order_do_not_change_labels_or_proof(self):
        workspace, source, target = arms(5, 2)
        before = copy.deepcopy(workspace)
        expected = infer_direct_relationship(workspace, source[0], target[0])
        self.assertEqual(workspace, before)
        shuffled = copy.deepcopy(workspace)
        shuffled["relationships"].reverse()
        self.assertEqual(infer_direct_relationship(shuffled, source[0], target[0]), expected)
        for person in shuffled["people"].values():
            person["name"] = "妹妹妈妈妻子"
            person["introduction"] = "高祖父"
        renamed = infer_direct_relationship(shuffled, source[0], target[0])
        self.assertEqual([item["label"] for item in renamed["results"]], [item["label"] for item in expected["results"]])
        self.assertNotIn("person_", renamed["results"][0]["explanation"])
        self.assertIn("曾祖父的堂兄弟（长幼未知）", renamed["results"][0]["explanation"])

    def test_remote_duplicate_ancestor_evidence_collapses_with_stable_names(self):
        workspace, source, target = arms(5, 2)
        workspace["people"]["person_common"]["name"] = "稳定共同祖先"
        other = core.add_person(workspace, {"generation_id": "g0", "gender": "female", "name": "另一共同祖先"})
        # Keep deterministic evidence ordering independent of generated IDs.
        del workspace["people"][other["id"]]
        other["id"] = "person_z_common"
        workspace["people"][other["id"]] = other
        core.add_relationship(workspace, other["id"], source[-2])
        core.add_relationship(workspace, other["id"], target[-2])
        result = infer_direct_relationship(workspace, source[0], target[0])
        self.assertEqual([item["label"] for item in result["results"]], ["堂曾祖父"])
        self.assertEqual(result["note"], "")
        self.assertIn("稳定共同祖先", result["results"][0]["explanation"])
        self.assertNotIn("另一共同祖先", result["results"][0]["explanation"])
        workspace["relationships"].reverse()
        self.assertEqual(infer_direct_relationship(workspace, source[0], target[0]), result)

    def test_remote_multiple_parent_branches_keep_different_formal_terms(self):
        workspace, source, target = arms(3, 2)
        mother = core.add_person(workspace, {"generation_id": "g2", "gender": "female", "name": "母系家长"})
        core.add_relationship(workspace, source[-2], mother["id"])
        core.add_relationship(workspace, mother["id"], source[0])
        before = copy.deepcopy(workspace)
        result = infer_direct_relationship(workspace, source[0], target[0])
        self.assertEqual([item["label"] for item in result["results"]], ["堂伯叔父（长幼未知）", "堂舅父"])
        self.assertIn("存在多重亲缘", result["note"])
        self.assertIn("父亲的堂兄弟（长幼未知）", result["results"][0]["explanation"])
        self.assertIn("母亲的堂兄弟（长幼未知）", result["results"][1]["explanation"])
        self.assertEqual(workspace, before)
        workspace["relationships"].reverse()
        self.assertEqual(infer_direct_relationship(workspace, source[0], target[0]), result)

    def test_nephew_canonical_turn_cannot_be_reduced_to_self_or_spouse(self):
        workspace, source, target, result = self.result(1, 2)
        self.assertEqual(naming.canonical_selector(workspace["people"], source, target), "xb,s")
        self.assertEqual(result["label"], "侄子")
        self.assertNotEqual(source[0], target[0])


if __name__ == "__main__":
    unittest.main()
