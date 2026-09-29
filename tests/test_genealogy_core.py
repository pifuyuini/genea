import unittest
import genealogy_core as core

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.w = core.default_workspace()
        self.g1 = core.add_generation(self.w, "first", name="上")
        self.g2 = core.add_generation(self.w, "below", self.g1["id"], "下")
    def person(self, generation, gender, name): return core.add_person(self.w, {"generation_id": generation["id"], "gender": gender, "name": name})
    def test_blank_and_generations(self):
        self.assertEqual(core.default_workspace()["schema_version"], 2); self.assertEqual([g["position"] for g in self.w["generations"]], [0, 1])
    def test_four_standard_relationships(self):
        expected = {("male", "male"): "father_son", ("male", "female"): "father_daughter", ("female", "male"): "mother_son", ("female", "female"): "mother_daughter"}
        for index, ((a, b), code) in enumerate(expected.items()):
            parent = self.person(self.g1, a, f"p{index}"); child = self.person(self.g2, b, f"c{index}")
            self.assertEqual(core.add_relationship(self.w, parent["id"], child["id"])["code"], code)
    def test_non_adjacent_rejected(self):
        g3 = core.add_generation(self.w, "below", self.g2["id"]); a = self.person(self.g1, "male", "a"); b = self.person(g3, "male", "b")
        with self.assertRaises(core.ValidationError): core.add_relationship(self.w, a["id"], b["id"])
    def test_inserting_generation_removes_relationships_that_are_no_longer_adjacent(self):
        parent = self.person(self.g1, "male", "父"); child = self.person(self.g2, "male", "子"); relationship = core.add_relationship(self.w, parent["id"], child["id"])
        core.add_generation(self.w, "above", self.g2["id"], "中间层")
        self.assertNotIn(relationship["id"], [item["id"] for item in self.w["relationships"]])
    def test_move_removes_invalid_relationship(self):
        g3 = core.add_generation(self.w, "below", self.g2["id"]); a = self.person(self.g1, "male", "a"); b = self.person(self.g2, "female", "b"); r = core.add_relationship(self.w, a["id"], b["id"])
        _, removed = core.update_person(self.w, b["id"], {"generation_id": g3["id"]}); self.assertEqual(removed, [r["id"]]); self.assertFalse(self.w["relationships"])
    def test_update_person_rejects_invalid_names_and_gender(self):
        person = self.person(self.g1, "male", "有效")
        for name in ("", "   ", None, 42):
            with self.subTest(name=name), self.assertRaises(core.ValidationError): core.update_person(self.w, person["id"], {"name": name})
        with self.assertRaises(core.ValidationError): core.update_person(self.w, person["id"], {"gender": "unknown"})
        updated, _ = core.update_person(self.w, person["id"], {"name": "  新名  ", "gender": "female"}); self.assertEqual(updated["name"], "新名"); self.assertEqual(updated["gender"], "female")
    def test_reorder_generation_people_moves_forward_and_backward(self):
        first = self.person(self.g1, "male", "a")
        second = self.person(self.g1, "female", "b")
        third = self.person(self.g1, "male", "c")
        core.reorder_generation_people(self.w, self.g1["id"], [third["id"], first["id"], second["id"]])
        self.assertEqual([self.w["people"][person_id]["order"] for person_id in [third["id"], first["id"], second["id"]]], [0, 1, 2])
        core.reorder_generation_people(self.w, self.g1["id"], [second["id"], third["id"], first["id"]])
        self.assertEqual([self.w["people"][person_id]["order"] for person_id in [second["id"], third["id"], first["id"]]], [0, 1, 2])

    def test_reorder_generation_people_accepts_single_and_empty_generations(self):
        only = self.person(self.g1, "male", "only")
        core.reorder_generation_people(self.w, self.g1["id"], [only["id"]])
        core.reorder_generation_people(self.w, self.g2["id"], [])
        self.assertEqual(only["order"], 0)

    def test_reorder_generation_people_rejects_incomplete_duplicate_foreign_and_unknown_ids(self):
        first = self.person(self.g1, "male", "a")
        second = self.person(self.g1, "female", "b")
        foreign = self.person(self.g2, "male", "foreign")
        invalid_orders = (
            [first["id"]],
            [first["id"], first["id"]],
            [first["id"], foreign["id"]],
            [first["id"], "missing-person"],
            None,
            "not-an-array",
        )
        for person_ids in invalid_orders:
            with self.subTest(person_ids=person_ids), self.assertRaises(core.ValidationError):
                core.reorder_generation_people(self.w, self.g1["id"], person_ids)
        with self.assertRaises(core.NotFoundError):
            core.reorder_generation_people(self.w, "missing-generation", [first["id"], second["id"]])

    def test_reorder_generation_people_preserves_other_layers_people_and_relationships(self):
        parent_a = self.person(self.g1, "male", "parent-a")
        parent_b = self.person(self.g1, "female", "parent-b")
        child = self.person(self.g2, "male", "child")
        core.add_relationship(self.w, parent_a["id"], child["id"])
        before_child = dict(child)
        before_relationships = [dict(item) for item in self.w["relationships"]]
        core.reorder_generation_people(self.w, self.g1["id"], [parent_b["id"], parent_a["id"]])
        self.assertEqual(child, before_child)
        self.assertEqual(self.w["relationships"], before_relationships)

    def test_cross_generation_move_still_removes_invalid_relationship_after_reorder(self):
        g3 = core.add_generation(self.w, "below", self.g2["id"])
        parent = self.person(self.g1, "male", "parent")
        child = self.person(self.g2, "female", "child")
        relationship = core.add_relationship(self.w, parent["id"], child["id"])
        core.reorder_generation_people(self.w, self.g1["id"], [parent["id"]])
        _, removed = core.update_person(self.w, child["id"], {"generation_id": g3["id"]})
        self.assertEqual(removed, [relationship["id"]])
        self.assertFalse(self.w["relationships"])

    def test_special_and_path(self):
        a = self.person(self.g1, "female", "a"); b = self.person(self.g2, "male", "b"); r = core.add_relationship(self.w, a["id"], b["id"])
        core.update_relationship(self.w, r["id"], {"kind": "special", "parent_label": "师父", "child_label": "徒弟"})
        path = core.relationship_path(self.w, b["id"], a["id"]); self.assertEqual(path["path_text"], "师父"); self.assertEqual(path["person_ids"], [b["id"], a["id"]]); self.assertEqual(path["relationship_ids"], [r["id"]])
        self.assertEqual(core.relationship_path(self.w, a["id"], b["id"])["path_text"], "徒弟")
    def test_preview_special_path_uses_ids_and_returns_b_to_a_label(self):
        child = self.person(self.g2, "male", "我"); parent = self.person(self.g1, "female", "母亲")
        child["id"] = "person_49a0d45604ae"; parent["id"] = "person_918d04108d2d"
        self.w["people"] = {child["id"]: child, parent["id"]: parent}
        self.w["relationships"] = [{"id": "rel_aefccb2d49cd", "parent_id": parent["id"], "child_id": child["id"], "kind": "special", "code": "special", "parent_label": "养母", "child_label": "养子", "color_key": "special"}]
        result = core.relationship_path(self.w, child["id"], parent["id"])
        self.assertEqual(result, {"path_text": "养母", "person_ids": [child["id"], parent["id"]], "relationship_ids": ["rel_aefccb2d49cd"]})
        self.assertEqual(core.relationship_path(self.w, parent["id"], child["id"])["path_text"], "养子")
    def test_standard_path_is_bidirectional(self):
        parent = self.person(self.g1, "female", "妈妈"); child = self.person(self.g2, "male", "孩子"); relationship = core.add_relationship(self.w, parent["id"], child["id"])
        self.assertEqual(core.relationship_path(self.w, child["id"], parent["id"])["path_text"], "妈妈")
        self.assertEqual(core.relationship_path(self.w, parent["id"], child["id"])["path_text"], "儿子")
        self.assertEqual(core.relationship_path(self.w, child["id"], parent["id"])["relationship_ids"], [relationship["id"]])

if __name__ == "__main__": unittest.main()
