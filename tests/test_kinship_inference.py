import copy
import itertools
import unittest

import genealogy_core as core
from kinship_inference import infer_direct_relationship


def graph(people, edges=()):
    """Build deterministic synthetic schema-v2 records without real user data."""
    workspace = core.default_workspace()
    positions = sorted({position for position, gender in people.values()})
    workspace["generations"] = [{"id": f"g{position}", "position": position, "name": str(position)} for position in positions]
    workspace["people"] = {
        person_id: {"id": person_id, "generation_id": f"g{position}", "gender": gender, "name": "无关姓名", "order": 0, "introduction": "无关介绍"}
        for person_id, (position, gender) in people.items()
    }
    for edge in edges:
        parent_id, child_id = edge[:2]
        relationship = core.add_relationship(workspace, parent_id, child_id)
        relationship["id"] = f"{parent_id}-{child_id}"
        if len(edge) == 3:
            relationship.update({"kind": edge[2], "parent_label": "师父", "child_label": "徒弟"})
    return workspace


class KinshipInferenceTests(unittest.TestCase):
    def assert_single(self, workspace, source, target, expected):
        result = infer_direct_relationship(workspace, source, target)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual([item["label"] for item in result["results"]], [expected])
        self.assertEqual(result["note"], "")
        self.assertTrue(result["results"][0]["explanation"])
        return result

    def test_self_without_registered_edges(self):
        workspace = graph({"self": (0, "female")})
        self.assert_single(workspace, "self", "self", "自己")
        self.assertEqual(core.relationship_query(workspace, "self", "self")["person_ids"], ["self"])

    def test_parent_and_child_in_both_directions(self):
        for parent_gender, child_gender in itertools.product(("male", "female"), repeat=2):
            with self.subTest(parent_gender=parent_gender, child_gender=child_gender):
                workspace = graph({"parent": (0, parent_gender), "child": (1, child_gender)}, [("parent", "child")])
                self.assert_single(workspace, "child", "parent", "父亲" if parent_gender == "male" else "母亲")
                self.assert_single(workspace, "parent", "child", "儿子" if child_gender == "male" else "女儿")

    def test_grandparents_and_grandchildren_in_both_directions(self):
        for middle_gender, ancestor_gender, child_gender in itertools.product(("male", "female"), repeat=3):
            with self.subTest(middle=middle_gender, ancestor=ancestor_gender, child=child_gender):
                workspace = graph({"grand": (0, ancestor_gender), "parent": (1, middle_gender), "child": (2, child_gender)}, [("grand", "parent"), ("parent", "child")])
                ancestor = ("外祖" if middle_gender == "female" else "祖") + ("父" if ancestor_gender == "male" else "母")
                child = ("外孙" if middle_gender == "female" else "孙") + ("子" if child_gender == "male" else "女")
                self.assert_single(workspace, "child", "grand", ancestor)
                self.assert_single(workspace, "grand", "child", child)

    def test_siblings_do_not_infer_age_or_full_and_half_siblings(self):
        workspace = graph({"parent": (0, "female"), "brother": (1, "male"), "sister": (1, "female")}, [("parent", "brother"), ("parent", "sister")])
        workspace["people"]["brother"].update({"name": "弟弟", "order": 99, "introduction": "较年轻"})
        workspace["people"]["sister"].update({"name": "姐姐", "order": -1})
        self.assert_single(workspace, "sister", "brother", "兄弟（长幼未知）")
        self.assert_single(workspace, "brother", "sister", "姐妹（长幼未知）")
        for result in infer_direct_relationship(workspace, "brother", "sister")["results"]:
            self.assertNotIn("同胞", result["explanation"])

    def test_uncles_aunts_and_nephews_nieces_in_both_directions(self):
        for parent_gender, relative_gender, ego_gender in itertools.product(("male", "female"), repeat=3):
            with self.subTest(parent=parent_gender, relative=relative_gender, ego=ego_gender):
                workspace = graph({"grand": (0, "female"), "parent": (1, parent_gender), "relative": (1, relative_gender), "ego": (2, ego_gender)}, [("grand", "parent"), ("grand", "relative"), ("parent", "ego")])
                if parent_gender == "male":
                    older = "伯父／叔父（长幼未知）" if relative_gender == "male" else "姑母"
                    younger = "侄子" if ego_gender == "male" else "侄女"
                else:
                    older = "舅父" if relative_gender == "male" else "姨母"
                    younger = "外甥" if ego_gender == "male" else "外甥女"
                self.assert_single(workspace, "ego", "relative", older)
                self.assert_single(workspace, "relative", "ego", younger)

    def test_first_cousin_branches_in_both_directions(self):
        prefixes = {("male", "male"): "堂", ("male", "female"): "姑表", ("female", "male"): "舅表", ("female", "female"): "姨表"}
        for left_gender, right_gender, ego_gender, target_gender in itertools.product(("male", "female"), repeat=4):
            with self.subTest(left=left_gender, right=right_gender, target=target_gender, ego=ego_gender):
                workspace = graph({"grand": (0, "female"), "left": (1, left_gender), "right": (1, right_gender), "ego": (2, ego_gender), "target": (2, target_gender)}, [("grand", "left"), ("grand", "right"), ("left", "ego"), ("right", "target")])
                forward = prefixes[left_gender, right_gender] + ("兄弟" if target_gender == "male" else "姐妹") + "（长幼未知）"
                reverse = prefixes[right_gender, left_gender] + ("兄弟" if ego_gender == "male" else "姐妹") + "（长幼未知）"
                self.assert_single(workspace, "ego", "target", forward)
                self.assert_single(workspace, "target", "ego", reverse)

    def test_distant_lineal_relations_use_formal_gender_specific_terms(self):
        for distance in (3, 4, 6):
            with self.subTest(distance=distance):
                people = {f"p{i}": (i, "female" if i == 0 else "male") for i in range(distance + 1)}
                workspace = graph(people, [(f"p{i}", f"p{i + 1}") for i in range(distance)])
                ancestor = self.assert_single(workspace, f"p{distance}", "p0", {3: "曾祖母", 4: "高祖母", 6: "烈祖母"}[distance])
                descendant = infer_direct_relationship(workspace, "p0", f"p{distance}")["results"][0]
                if distance in (3, 4):
                    self.assertEqual(descendant["label"], {3: "曾孙", 4: "玄孙"}[distance])
                else:
                    self.assertIn(descendant["label"], ("晜孙", "昆孙"))
                self.assertNotIn("相隔", ancestor["results"][0]["label"])
                self.assertNotIn("相隔", descendant["label"])

    def test_distant_collateral_uses_cousin_parent_structure(self):
        workspace = graph({"grand": (0, "male"), "left": (1, "male"), "right": (1, "female"), "next": (2, "male"), "ego": (3, "male"), "target": (2, "female")}, [("grand", "left"), ("grand", "right"), ("left", "next"), ("next", "ego"), ("right", "target")])
        forward = infer_direct_relationship(workspace, "ego", "target")["results"][0]
        reverse = infer_direct_relationship(workspace, "target", "ego")["results"][0]
        self.assertEqual(forward["label"], "姑表姑母")
        self.assertIn("父亲的姑表姐妹（长幼未知）", forward["explanation"])
        self.assertEqual(reverse["label"], "舅表侄子")
        self.assertIn("舅表兄弟（长幼未知）的儿子", reverse["explanation"])

    def test_special_edges_remain_in_chain_but_not_blood_inference(self):
        workspace = graph({"parent": (0, "female"), "child": (1, "male")}, [("parent", "child", "special")])
        result = core.relationship_query(workspace, "child", "parent")
        self.assertEqual(result["path_text"], "师父")
        self.assertEqual(result["direct_relationship"]["status"], "unsupported")
        self.assertEqual(result["direct_relationship"]["results"], [])
        self.assertTrue(result["direct_relationship"]["note"])

    def test_only_exact_standard_kind_counts(self):
        for kind in ("STANDARD", "standard-like", None):
            with self.subTest(kind=kind):
                workspace = graph({"parent": (0, "male"), "child": (1, "female")}, [("parent", "child", kind)])
                self.assertEqual(infer_direct_relationship(workspace, "child", "parent")["status"], "unsupported")

    def test_disconnected_is_missing_records_not_no_kinship(self):
        workspace = graph({"a": (0, "male"), "b": (0, "female")})
        result = infer_direct_relationship(workspace, "a", "b")
        self.assertEqual(result["status"], "disconnected")
        self.assertEqual(result["results"], [])
        self.assertIn("未找到已登记的连接", result["note"])
        self.assertNotIn("没有亲属关系", result["note"])
        self.assertEqual(core.relationship_path(workspace, "a", "b"), {"path_text": "", "person_ids": [], "relationship_ids": []})

    def test_common_child_does_not_imply_spouse(self):
        workspace = graph({"a": (0, "male"), "b": (0, "female"), "child": (1, "male")}, [("a", "child"), ("b", "child")])
        for source, target in (("a", "b"), ("b", "a")):
            result = infer_direct_relationship(workspace, source, target)
            self.assertEqual((result["status"], result["results"]), ("unsupported", []))
            self.assertIn("婚姻", result["note"])

    def test_duplicate_shared_parent_proofs_collapse_to_one_label(self):
        workspace = graph({"father": (0, "male"), "mother": (0, "female"), "a": (1, "male"), "b": (1, "female")}, [("father", "a"), ("father", "b"), ("mother", "a"), ("mother", "b")])
        result = self.assert_single(workspace, "a", "b", "姐妹（长幼未知）")
        self.assertEqual(result["results"][0]["explanation"], "无关姓名 → 无关姓名 → 无关姓名。")

    def test_multiple_parents_all_participate(self):
        workspace = graph({"p0": (0, "male"), "p1": (0, "female"), "p2": (0, "male"), "ego": (1, "male"), "target": (1, "female")}, [("p0", "ego"), ("p1", "ego"), ("p2", "ego"), ("p2", "target")])
        self.assert_single(workspace, "ego", "target", "姐妹（长幼未知）")
        for parent in ("p0", "p1", "p2"):
            self.assertEqual(infer_direct_relationship(workspace, "ego", parent)["status"], "resolved")

    def test_true_multiple_kinship_lists_different_labels(self):
        workspace = graph({"grand": (0, "male"), "father": (1, "male"), "aunt": (1, "female"), "other": (1, "male"), "ego": (2, "male"), "target": (2, "female")}, [("grand", "father"), ("grand", "aunt"), ("father", "ego"), ("aunt", "target"), ("other", "ego"), ("other", "target")])
        result = infer_direct_relationship(workspace, "ego", "target")
        self.assertEqual([item["label"] for item in result["results"]], ["姐妹（长幼未知）", "姑表姐妹（长幼未知）"])
        self.assertIn("存在多重亲缘", result["note"])

    def test_multiple_cousin_routes_classify_each_parent_branch(self):
        workspace = graph({"grand": (0, "male"), "father": (1, "male"), "mother": (1, "female"), "uncle": (1, "male"), "ego": (2, "female"), "target": (2, "male")}, [("grand", "father"), ("grand", "mother"), ("grand", "uncle"), ("father", "ego"), ("mother", "ego"), ("uncle", "target")])
        result = infer_direct_relationship(workspace, "ego", "target")
        self.assertEqual([item["label"] for item in result["results"]], sorted(["堂兄弟（长幼未知）", "舅表兄弟（长幼未知）"]))
        self.assertIn("存在多重亲缘", result["note"])

    def test_siblings_cannot_go_around_shared_parent_to_become_cousins(self):
        workspace = graph({"grand": (0, "male"), "parent": (1, "male"), "a": (2, "male"), "b": (2, "female")}, [("grand", "parent"), ("parent", "a"), ("parent", "b")])
        self.assert_single(workspace, "a", "b", "姐妹（长幼未知）")

    def test_same_label_via_two_grandparents_has_stable_proof(self):
        workspace = graph({"a-grand": (0, "male"), "z-grand": (0, "female"), "left": (1, "male"), "right": (1, "male"), "ego": (2, "male"), "target": (2, "male")}, [("z-grand", "left"), ("z-grand", "right"), ("a-grand", "left"), ("a-grand", "right"), ("left", "ego"), ("right", "target")])
        for person_id, name in {"a-grand": "祖父", "z-grand": "祖母", "left": "甲父", "right": "乙父", "ego": "甲", "target": "乙"}.items():
            workspace["people"][person_id]["name"] = name
        result = self.assert_single(workspace, "ego", "target", "堂兄弟（长幼未知）")
        self.assertEqual(result["results"][0]["explanation"], "甲 → 甲父 → 祖父 → 乙父 → 乙。")
        workspace["people"]["a-grand"]["name"] = "最后排序的名字"
        workspace["people"]["z-grand"]["name"] = "最先排序的名字"
        renamed = self.assert_single(workspace, "ego", "target", "堂兄弟（长幼未知）")
        self.assertIn("最后排序的名字", renamed["results"][0]["explanation"])
        self.assertNotIn("最先排序的名字", renamed["results"][0]["explanation"])

    def test_older_shared_ancestors_do_not_add_spurious_distant_kinship(self):
        workspace = graph({"great": (0, "male"), "grand": (1, "male"), "parent": (2, "male"), "a": (3, "male"), "b": (3, "female")}, [("great", "grand"), ("grand", "parent"), ("parent", "a"), ("parent", "b")])
        result = self.assert_single(workspace, "a", "b", "姐妹（长幼未知）")
        self.assertEqual(result["results"][0]["explanation"], "无关姓名 → 无关姓名 → 无关姓名。")

    def test_edge_order_does_not_change_labels_or_explanations(self):
        workspace = graph({"g": (0, "male"), "p": (1, "male"), "q": (1, "female"), "shared": (1, "male"), "a": (2, "male"), "b": (2, "female")}, [("g", "p"), ("g", "q"), ("p", "a"), ("q", "b"), ("shared", "a"), ("shared", "b")])
        expected = infer_direct_relationship(workspace, "a", "b")
        edges = workspace["relationships"]
        for rotation in range(len(edges)):
            for candidate in (edges[rotation:] + edges[:rotation], list(reversed(edges[rotation:] + edges[:rotation]))):
                shuffled = {**workspace, "relationships": candidate}
                self.assertEqual(infer_direct_relationship(shuffled, "a", "b"), expected)

    def test_standard_inference_can_differ_from_shortest_special_chain(self):
        workspace = graph({"grand": (0, "male"), "p": (1, "male"), "q": (1, "female"), "ego": (2, "male")}, [("q", "ego", "special"), ("grand", "p"), ("grand", "q"), ("p", "ego")])
        self.assertEqual(core.relationship_path(workspace, "ego", "q"), {"path_text": "师父", "person_ids": ["ego", "q"], "relationship_ids": ["q-ego"]})
        result = core.relationship_query(workspace, "ego", "q")
        self.assertEqual(result["path_text"], "师父")
        self.assertEqual(result["direct_relationship"]["results"][0]["label"], "姑母")

    def test_explanation_uses_names_without_exposing_internal_ids(self):
        workspace = graph({"person_grand": (0, "female"), "person_parent": (1, "male"), "person_ego": (2, "female")}, [("person_grand", "person_parent"), ("person_parent", "person_ego")])
        for person_id, name in {"person_ego": "甲", "person_parent": "甲父", "person_grand": "合成祖母"}.items():
            workspace["people"][person_id]["name"] = name
        upward = self.assert_single(workspace, "person_ego", "person_grand", "祖母")
        self.assertEqual(upward["results"][0]["explanation"], "甲 → 甲父 → 合成祖母。")
        downward = self.assert_single(workspace, "person_grand", "person_ego", "孙女")
        self.assertEqual(downward["results"][0]["explanation"], "合成祖母 → 甲父 → 甲。")
        for result in (upward, downward):
            self.assertNotIn("person_", result["results"][0]["explanation"])
        workspace["people"]["person_parent"]["name"] = "名字叫妈妈"
        workspace["people"]["person_grand"]["name"] = "名字叫外祖父"
        renamed = self.assert_single(workspace, "person_ego", "person_grand", "祖母")
        self.assertEqual(renamed["results"][0]["explanation"], "甲 → 名字叫妈妈 → 名字叫外祖父。")

    def test_missing_names_use_display_placeholder(self):
        workspace = graph({"person_parent": (0, "male"), "person_child": (1, "male")}, [("person_parent", "person_child")])
        for name in (None, "", "   "):
            with self.subTest(name=name):
                workspace["people"]["person_parent"]["name"] = name
                workspace["people"]["person_child"].pop("name", None)
                result = self.assert_single(workspace, "person_child", "person_parent", "父亲")
                self.assertEqual(result["results"][0]["explanation"], "未命名人物 → 未命名人物。")

    def test_pure_function_does_not_change_any_records(self):
        workspace = graph({"p": (0, "female"), "a": (1, "male"), "b": (1, "female")}, [("p", "a"), ("p", "b")])
        before = copy.deepcopy(workspace)
        infer_direct_relationship(workspace, "a", "b")
        core.relationship_query(workspace, "a", "b")
        self.assertEqual(workspace, before)

    def test_query_preserves_exact_legacy_path_shape_and_edge_order(self):
        workspace = graph({"father": (0, "male"), "mother": (0, "female"), "a": (1, "male"), "b": (1, "female")}, [("mother", "a"), ("mother", "b"), ("father", "a"), ("father", "b")])
        expected = {"path_text": "妈妈的女儿", "person_ids": ["a", "mother", "b"], "relationship_ids": ["mother-a", "mother-b"]}
        self.assertEqual(core.relationship_path(workspace, "a", "b"), expected)
        query = core.relationship_query(workspace, "a", "b")
        self.assertEqual({key: query[key] for key in expected}, expected)
        self.assertEqual(set(query), {*expected, "direct_relationship"})

    def test_unknown_people_still_raise_core_not_found(self):
        workspace = graph({"a": (0, "male")})
        for source, target in (("a", "missing"), ("missing", "a"), ("missing", "missing")):
            with self.subTest(source=source, target=target), self.assertRaises(core.NotFoundError):
                core.relationship_query(workspace, source, target)


if __name__ == "__main__":
    unittest.main()
