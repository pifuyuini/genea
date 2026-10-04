import copy
import itertools
import unittest

import genealogy_core as core
from kinship_composition import compose_registered_connection
from kinship_inference import infer_direct_relationship
from test_kinship_inference import graph


def chain(steps, *, genders=None, names=None, special_labels=None):
    """U/D are ordinary edges; lowercase u/d are directed special records."""
    positions = [0]
    for step in steps:
        positions.append(positions[-1] + (1 if step.upper() == "D" else -1))
    offset = -min(positions)
    genders = genders or ["male"] * len(positions)
    person_ids = [f"person_{index}" for index in range(len(positions))]
    people = {person_id: (position + offset, genders[index]) for index, (person_id, position) in enumerate(zip(person_ids, positions))}
    edges = []
    for index, step in enumerate(steps):
        pair = (person_ids[index], person_ids[index + 1]) if step.upper() == "D" else (person_ids[index + 1], person_ids[index])
        edges.append((*pair, "special") if step.islower() else pair)
    workspace = graph(people, edges)
    for index, person_id in enumerate(person_ids):
        workspace["people"][person_id]["name"] = names[index] if names else f"人物{index}"
    for index, labels in (special_labels or {}).items():
        workspace["relationships"][index].update({"parent_label": labels[0], "child_label": labels[1]})
    return workspace, person_ids


class KinshipCompositionTests(unittest.TestCase):
    def query(self, workspace, source, target):
        result = core.relationship_query(workspace, source, target)
        direct = result["direct_relationship"]
        self.assertEqual((direct["status"], direct["results"]), ("unsupported", []))
        composition = direct["composition"]
        self.assertEqual(set(composition), {"label", "explanation", "note"})
        self.assertTrue(all(isinstance(value, str) and value for value in composition.values()))
        self.assertIn("未登记夫妻", composition["note"])
        self.assertIn("不能", composition["note"])
        return result, composition

    def example(self):
        names = ["薛蟠", "薛母", "王父", "王夫人", "贾珠", "贾政", "贾代善", "贾源", "始祖", "贾演", "贾代化", "贾敬", "贾珍"]
        genders = ["male", "female", "male", "female"] + ["male"] * 9
        return chain("UUDDUUUUDDDD", genders=genders, names=names)

    def test_xue_pan_to_jia_zhen_is_three_ordered_segments(self):
        workspace, people = self.example()
        before = copy.deepcopy(workspace)
        legacy = core.relationship_path(workspace, people[0], people[-1])
        result, composition = self.query(workspace, people[0], people[-1])
        self.assertEqual(composition["label"], "姨母的孩子的父亲的从堂侄子")
        self.assertIn("血亲段“姨母”：薛蟠 → 薛母 → 王父 → 王夫人", composition["explanation"])
        self.assertIn("共同孩子桥：王夫人 → 贾珠 → 贾政", composition["explanation"])
        self.assertIn("血亲段“从堂侄子”", composition["explanation"])
        self.assertIn("完整登记路径：薛蟠 → 薛母 → 王父 → 王夫人 → 贾珠 → 贾政 → 贾代善 → 贾源 → 始祖 → 贾演 → 贾代化 → 贾敬 → 贾珍。", composition["explanation"])
        self.assertNotIn("person_", composition["explanation"])
        self.assertEqual({key: result[key] for key in legacy}, legacy)
        self.assertEqual(workspace, before)

    def test_reverse_connection_changes_bridge_gender_and_blood_direction(self):
        workspace, people = self.example()
        result, composition = self.query(workspace, people[-1], people[0])
        self.assertEqual(composition["label"], "从堂父的孩子的母亲的外甥")
        self.assertIn("共同孩子桥：贾政 → 贾珠 → 王夫人", composition["explanation"])
        self.assertIn("王夫人是该孩子的母亲", composition["explanation"])
        self.assertIn("血亲段“外甥”", composition["explanation"])

    def test_common_child_structure_in_both_directions_for_all_genders(self):
        for left_gender, child_gender, right_gender in itertools.product(("male", "female"), repeat=3):
            with self.subTest(left=left_gender, child=child_gender, right=right_gender):
                workspace, people = chain("DU", genders=[left_gender, child_gender, right_gender])
                for source, target, target_gender in ((people[0], people[2], right_gender), (people[2], people[0], left_gender)):
                    result, composition = self.query(workspace, source, target)
                    self.assertEqual(composition["label"], "孩子的" + ("父亲" if target_gender == "male" else "母亲"))
                    self.assertNotIn("夫妻", composition["label"])
                    self.assertNotIn("丈夫", composition["label"])
                    self.assertNotIn("妻子", composition["label"])

    def test_more_than_two_registered_parents_are_not_assumed_to_be_a_couple(self):
        workspace = graph({"parent_a": (0, "male"), "parent_b": (0, "female"), "parent_c": (0, "male"), "child": (1, "female")}, [("parent_a", "child"), ("parent_b", "child"), ("parent_c", "child")])
        for source, target in itertools.permutations(("parent_a", "parent_b", "parent_c"), 2):
            with self.subTest(source=source, target=target):
                result, composition = self.query(workspace, source, target)
                target_gender = workspace["people"][target]["gender"]
                self.assertEqual(composition["label"], "孩子的" + ("父亲" if target_gender == "male" else "母亲"))
                self.assertIn("两侧均登记", composition["explanation"])

    def test_multiple_children_choose_one_stable_shortest_proof(self):
        workspace = graph({"parent_a": (0, "male"), "parent_b": (0, "female"), "person_a_child": (1, "female"), "person_z_child": (1, "male")}, [("parent_a", "person_z_child"), ("parent_b", "person_z_child"), ("parent_a", "person_a_child"), ("parent_b", "person_a_child")])
        workspace["people"]["person_a_child"]["name"] = "排后面的名字"
        workspace["people"]["person_z_child"]["name"] = "排前面的名字"
        legacy = core.relationship_path(workspace, "parent_a", "parent_b")
        result, expected = self.query(workspace, "parent_a", "parent_b")
        self.assertEqual({key: result[key] for key in legacy}, legacy)
        self.assertEqual(legacy["person_ids"], ["parent_a", "person_z_child", "parent_b"])
        self.assertIn("排后面的名字", expected["explanation"])
        self.assertNotIn("排前面的名字", expected["explanation"])
        workspace["relationships"].reverse()
        result, reordered = self.query(workspace, "parent_a", "parent_b")
        self.assertEqual(reordered, expected)

    def test_two_adjacent_common_child_bridges_preserve_order(self):
        workspace, people = chain("DUDU", genders=["male", "male", "female", "female", "male"])
        result, composition = self.query(workspace, people[0], people[-1])
        self.assertEqual(composition["label"], "孩子的母亲的孩子的父亲")
        self.assertEqual(composition["explanation"].count("共同孩子桥"), 2)
        self.assertIn("人物0 → 人物1 → 人物2", composition["explanation"])
        self.assertIn("人物2 → 人物3 → 人物4", composition["explanation"])

    def test_blood_segment_between_two_bridges_is_named_as_siblings(self):
        workspace, people = chain("DUUDDU", genders=["male", "male", "male", "female", "male", "male", "female"])
        result, composition = self.query(workspace, people[0], people[-1])
        self.assertEqual(composition["label"], "孩子的父亲的兄弟（长幼未知）的孩子的母亲")
        self.assertEqual(composition["explanation"].count("共同孩子桥"), 2)
        self.assertIn("血亲段“兄弟（长幼未知）”", composition["explanation"])

    def test_special_father_word_is_only_quoted_registration_not_blood(self):
        workspace, people = chain("u", special_labels={0: ("爸爸", "孩子")})
        for source, target, label in ((people[0], people[1], "爸爸"), (people[1], people[0], "孩子")):
            with self.subTest(source=source):
                result, composition = self.query(workspace, source, target)
                self.assertEqual(composition["label"], f"“{label}”（登记特殊称谓）")
                self.assertIn(f"登记特殊称谓“{label}”", composition["explanation"])
                self.assertEqual(result["path_text"], label)

    def test_special_edges_split_blood_segments_and_do_not_become_parent_edges(self):
        workspace, people = chain("UuDDU", genders=["male", "female", "male", "female", "male", "male"], special_labels={1: ("爸爸", "孩子")})
        result, composition = self.query(workspace, people[0], people[-1])
        self.assertEqual(composition["label"], "母亲的“爸爸”（登记特殊称谓）的女儿的孩子的父亲")
        self.assertIn("登记特殊称谓“爸爸”：人物1 → 人物2", composition["explanation"])
        self.assertEqual(composition["explanation"].count("共同孩子桥"), 1)

    def test_multiple_special_records_and_bridge_keep_their_direction(self):
        workspace, people = chain("dDUdU", special_labels={0: ("师兄", "师弟"), 3: ("搭档", "伙伴")})
        result, composition = self.query(workspace, people[0], people[-1])
        self.assertEqual(composition["label"], "“师弟”（登记特殊称谓）的孩子的父亲的“伙伴”（登记特殊称谓）的父亲")
        self.assertEqual(composition["explanation"].count("登记特殊称谓“"), 2)
        self.assertEqual(composition["explanation"].count("共同孩子桥"), 1)

    def test_blood_resolved_query_ignores_a_shorter_special_connection(self):
        workspace = graph({"grand": (0, "male"), "parent": (1, "male"), "aunt": (1, "female"), "ego": (2, "male")}, [("grand", "parent"), ("grand", "aunt"), ("parent", "ego"), ("aunt", "ego", "special")])
        expected = infer_direct_relationship(workspace, "ego", "aunt")
        result = core.relationship_query(workspace, "ego", "aunt")
        self.assertEqual(result["direct_relationship"], expected)
        self.assertEqual(result["direct_relationship"]["results"][0]["label"], "姑母")
        self.assertNotIn("composition", result["direct_relationship"])
        self.assertEqual(result["path_text"], "师父")

    def test_all_existing_multiple_blood_results_remain_exact(self):
        workspace = graph({"grand": (0, "male"), "father": (1, "male"), "aunt": (1, "female"), "other": (1, "male"), "ego": (2, "male"), "target": (2, "female")}, [("grand", "father"), ("grand", "aunt"), ("father", "ego"), ("aunt", "target"), ("other", "ego"), ("other", "target")])
        expected = infer_direct_relationship(workspace, "ego", "target")
        result = core.relationship_query(workspace, "ego", "target")
        self.assertEqual(result["direct_relationship"], expected)
        self.assertEqual(len(expected["results"]), 2)
        self.assertNotIn("composition", result["direct_relationship"])

    def test_disconnected_and_self_queries_have_no_composition(self):
        workspace = graph({"a": (0, "male"), "b": (0, "female")})
        for source, target, status in (("a", "b", "disconnected"), ("a", "a", "resolved")):
            with self.subTest(source=source, target=target):
                result = core.relationship_query(workspace, source, target)
                self.assertEqual(result["direct_relationship"]["status"], status)
                self.assertNotIn("composition", result["direct_relationship"])
                self.assertIsNone(compose_registered_connection(workspace, source, target))

    def test_pure_blood_path_needs_no_structural_composition(self):
        workspace, people = chain("UUDD")
        self.assertIsNone(compose_registered_connection(workspace, people[0], people[-1]))
        self.assertNotIn("composition", core.relationship_query(workspace, people[0], people[-1])["direct_relationship"])

    def test_connection_structure_is_independent_of_names_and_dictionary_order(self):
        workspace, people = self.example()
        before = copy.deepcopy(workspace)
        expected = compose_registered_connection(workspace, people[0], people[-1])
        self.assertEqual(workspace, before)
        changed = copy.deepcopy(workspace)
        changed["relationships"].reverse()
        changed["people"] = dict(reversed(list(changed["people"].items())))
        self.assertEqual(compose_registered_connection(changed, people[0], people[-1]), expected)
        for person in changed["people"].values():
            person.update({"name": "妻子哥哥", "introduction": "丈夫", "order": 999})
        renamed = compose_registered_connection(changed, people[0], people[-1])
        self.assertEqual(renamed["label"], expected["label"])
        self.assertEqual(renamed["note"], expected["note"])
        self.assertNotIn("person_", renamed["explanation"])
        self.assertIn("妻子哥哥", renamed["explanation"])

    def test_unique_connection_keeps_structure_under_total_id_replacement(self):
        workspace, people = self.example()
        expected = compose_registered_connection(workspace, people[0], people[-1])
        replacements = {person_id: f"renamed_{100 - index}" for index, person_id in enumerate(people)}
        changed = copy.deepcopy(workspace)
        changed["people"] = {replacements[person_id]: {**person, "id": replacements[person_id]} for person_id, person in changed["people"].items()}
        for relationship in changed["relationships"]:
            relationship["parent_id"] = replacements[relationship["parent_id"]]
            relationship["child_id"] = replacements[relationship["child_id"]]
            relationship["id"] = "renamed_" + relationship["id"]
        actual = compose_registered_connection(changed, replacements[people[0]], replacements[people[-1]])
        self.assertEqual(actual, expected)

    def test_unnamed_people_have_display_placeholders_only(self):
        workspace, people = chain("DU")
        for person in workspace["people"].values():
            person.pop("name")
        result, composition = self.query(workspace, people[0], people[-1])
        self.assertEqual(composition["label"], "孩子的父亲")
        self.assertIn("未命名人物", composition["explanation"])
        self.assertNotIn("person_", composition["explanation"])

    def test_unknown_person_keeps_core_not_found_error(self):
        workspace, people = chain("DU")
        with self.assertRaises(core.NotFoundError):
            core.relationship_query(workspace, people[0], "missing")


if __name__ == "__main__":
    unittest.main()
