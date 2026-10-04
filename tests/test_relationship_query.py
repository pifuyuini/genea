"""Rule grammar and graph-typed filtering over public or synthetic records only."""
import copy
import importlib.util
import itertools
from pathlib import Path
import unittest
from unittest.mock import patch

import genealogy_core as core
import relationship_query as query
from test_kinship_inference import graph
import test_kinship_composition as composition

chain = composition.chain


def named_graph(people, edges=()):
    workspace = graph(people, edges)
    for person_id, person in workspace["people"].items():
        person["name"] = person_id
    return workspace


def public_demo(directory):
    path = Path(__file__).resolve().parents[1] / directory / "build_demo.py"
    spec = importlib.util.spec_from_file_location("query_" + directory, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build()


def relatives(workspace, source, term):
    return query.run_query(workspace, f"{source}的{term}有哪些")


def ids(result):
    return [person["person_id"] for person in result["results"]]


def typed_fixture():
    people = {
        "g": (0, "male"), "gm": (0, "female"), "mg": (0, "male"),
        "f": (1, "male"), "m": (1, "female"), "extra": (1, "male"),
        "punc": (1, "male"), "paut": (1, "female"),
        "munc": (1, "male"), "maut": (1, "female"),
        "s": (2, "male"), "bro": (2, "male"), "sis": (2, "female"),
        "pc": (2, "male"), "pcf": (2, "female"), "mc": (2, "male"), "mcf": (2, "female"),
        "son": (3, "male"), "daughter": (3, "female"), "niece": (3, "female"),
        "gs": (4, "male"), "gd": (4, "female"),
    }
    edges = [(grand, child) for grand in ("g", "gm") for child in ("f", "punc", "paut")]
    edges += [("mg", child) for child in ("m", "munc", "maut")]
    edges += [(parent, child) for parent in ("f", "m") for child in ("s", "bro", "sis")]
    edges += [("extra", "s"), ("punc", "pc"), ("paut", "pcf"), ("munc", "mc"), ("maut", "mcf"),
              ("s", "son"), ("s", "daughter"), ("sis", "niece"), ("son", "gs"), ("daughter", "gd")]
    return named_graph(people, edges)


class RelationshipQueryTests(unittest.TestCase):
    def test_pair_two_word_orders_preserve_source_direction(self):
        workspace = named_graph({"甲": (0, "female"), "乙": (1, "male")}, [("甲", "乙")])
        for text in ("甲和乙是什么关系", "乙是甲的什么人", "请问：甲与乙之间是什么关系？", "甲 跟 乙 有什么关系！"):
            with self.subTest(text=text):
                result = query.run_query(workspace, text)
                self.assertEqual((result["status"], result["intent"], result["source_id"], result["target_id"]), ("success", "pair", "甲", "乙"))
                self.assertEqual(result["results"][0]["path_result"], core.relationship_query(workspace, "甲", "乙"))
        reverse = query.run_query(workspace, "甲是乙的什么人")
        self.assertEqual((reverse["source_id"], reverse["target_id"]), ("乙", "甲"))

    def test_registered_names_containing_connectors_in_both_word_orders(self):
        for name, connector in itertools.product(("王和平", "陈与明", "刘跟生"), "和与跟"):
            workspace = named_graph({"a": (0, "male"), "b": (1, "female")}, [("a", "b")])
            workspace["people"]["a"]["name"] = name
            workspace["people"]["b"]["name"] = "张明"
            for text, source, target in ((name + connector + "张明是什么关系", "a", "b"),
                                         ("张明" + connector + name + "是什么关系", "b", "a"),
                                         (name + "是张明的什么人", "b", "a"),
                                         ("张明是" + name + "的什么人", "a", "b")):
                with self.subTest(text=text):
                    result = query.run_query(workspace, text)
                    self.assertEqual((result["status"], result["source_id"], result["target_id"]), ("success", source, target))
                    self.assertEqual(result["results"][0]["path_result"], core.relationship_query(workspace, source, target))

    def test_quoted_names_protect_connectors_and_both_name_positions(self):
        workspace = named_graph({"a": (0, "male"), "b": (1, "female")}, [("a", "b")])
        workspace["people"]["a"]["name"] = "王和平"
        workspace["people"]["b"]["name"] = "马跟涛"
        for opening, closing in (("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』"), (chr(34), chr(34)), (chr(39), chr(39))):
            for connector in "和与跟":
                first, second = opening + "王和平" + closing, opening + "马跟涛" + closing
                for text, source, target in ((first + connector + second + "是什么关系？", "a", "b"),
                                             (second + connector + first + "之间是什么关系", "b", "a"),
                                             (first + "是" + second + "的什么人", "b", "a")):
                    with self.subTest(text=text):
                        result = query.run_query(workspace, text)
                        self.assertEqual((result["status"], result["source_id"], result["target_id"]), ("success", source, target))

    def test_multiple_valid_name_splits_keep_candidates_and_pair_constraints(self):
        workspace = named_graph({"a": (0, "male"), "b": (0, "male"), "c": (0, "male"), "d": (0, "male")})
        for person_id, name in (("a", "王"), ("b", "张和明"), ("c", "王和张"), ("d", "明")):
            workspace["people"][person_id]["name"] = name
        text = "王和张和明是什么关系"
        result = query.run_query(workspace, text)
        self.assertEqual(result["status"], "needs_disambiguation")
        self.assertEqual([[candidate["id"] for candidate in ambiguity["candidates"]] for ambiguity in result["ambiguities"]], [["a", "c"], ["b", "d"]])
        partial = query.run_query(workspace, text, {"0": "c"})
        self.assertEqual((partial["status"], partial["source_id"], partial["target_id"]), ("success", "c", "d"))
        incompatible = query.run_query(workspace, text, {"0": "a", "1": "d"})
        self.assertEqual(incompatible["status"], "needs_disambiguation")
        self.assertEqual([item["slot"] for item in incompatible["ambiguities"]], ["0", "1"])
        self.assertEqual(incompatible["results"], [])
        compatible = query.run_query(workspace, text, {"0": "a", "1": "b"})
        self.assertEqual((compatible["source_id"], compatible["target_id"]), ("a", "b"))
        protected = query.run_query(workspace, "“王和张”和“明”是什么关系")
        self.assertEqual((protected["source_id"], protected["target_id"]), ("c", "d"))

    def test_connector_names_preserve_duplicate_name_slots_and_resolutions(self):
        workspace = named_graph({"a": (0, "male"), "b": (0, "male"), "c": (1, "female"), "d": (1, "female")})
        for person_id in ("a", "b"):
            workspace["people"][person_id]["name"] = "王和平"
        for person_id in ("c", "d"):
            workspace["people"][person_id]["name"] = "张明"
        text = "王和平和张明是什么关系"
        result = query.run_query(workspace, text)
        self.assertEqual([item["slot"] for item in result["ambiguities"]], ["0", "1"])
        partial = query.run_query(workspace, text, {"0": "b"})
        self.assertEqual(partial["source_id"], "b")
        self.assertEqual([item["slot"] for item in partial["ambiguities"]], ["1"])
        resolved = query.run_query(workspace, text, {"0": "b", "1": "d"})
        self.assertEqual((resolved["source_id"], resolved["target_id"]), ("b", "d"))
        wrong = query.run_query(workspace, text, {"0": "d"})
        self.assertEqual(wrong["status"], "needs_disambiguation")
        self.assertNotIn("source_id", wrong)

    def test_missing_person_does_not_truncate_registered_connector_name(self):
        workspace = named_graph({"a": (0, "male")})
        workspace["people"]["a"]["name"] = "王和平"
        result = query.run_query(workspace, "王和平和未登记人物是什么关系")
        self.assertEqual(result["status"], "not_found")
        self.assertIn("“未登记人物”", result["message"])
        self.assertNotIn("平和未登记人物", result["message"])

    def test_connector_names_leave_relative_and_unsupported_grammar_unchanged(self):
        workspace = named_graph({"a": (0, "male"), "b": (1, "female")}, [("a", "b")])
        workspace["people"]["a"]["name"] = "王和平"
        self.assertEqual(ids(relatives(workspace, "王和平", "子女")), ["b"])
        self.assertEqual(query.run_query(workspace, "王和平的妻子有哪些")["status"], "unsupported")
        same = query.run_query(workspace, "王和平和王和平是什么关系")
        self.assertEqual((same["source_id"], same["target_id"]), ("a", "a"))
        self.assertEqual(same["results"][0]["path_result"]["direct_relationship"]["results"][0]["label"], "自己")

    def test_chinese_quotes_middle_dots_and_fullwidth_punctuation(self):
        workspace = named_graph({"a": (0, "male"), "b": (1, "female")}, [("a", "b")])
        workspace["people"]["a"]["name"] = "何塞·阿尔卡蒂奥"
        workspace["people"]["b"]["name"] = "阿玛兰妲·乌尔苏拉"
        result = query.run_query(workspace, "请告诉我，“何塞・阿尔卡蒂奥”和‘阿玛兰妲·乌尔苏拉’是什么关系？")
        self.assertEqual((result["source_id"], result["target_id"]), ("a", "b"))

    def test_exact_full_name_has_priority_over_containing_names(self):
        workspace = named_graph({"a": (0, "male"), "b": (0, "male"), "c": (1, "female")})
        workspace["people"]["a"]["name"] = "甲"
        workspace["people"]["b"]["name"] = "甲乙"
        workspace["people"]["c"]["name"] = "丙"
        self.assertEqual(query.run_query(workspace, "甲和丙是什么关系")["source_id"], "a")

    def test_duplicate_full_names_and_both_ambiguous_slots_are_returned(self):
        workspace = named_graph({"a": (0, "male"), "b": (0, "male"), "c": (1, "female"), "d": (1, "female")})
        for person_id in ("a", "b"):
            workspace["people"][person_id]["name"] = "同名甲"
        for person_id in ("c", "d"):
            workspace["people"][person_id]["name"] = "同名乙"
        result = query.run_query(workspace, "同名甲和同名乙是什么关系")
        self.assertEqual(result["status"], "needs_disambiguation")
        self.assertEqual([ambiguity["slot"] for ambiguity in result["ambiguities"]], ["0", "1"])
        self.assertEqual(set(result["ambiguities"][0]["candidates"][0]), {"id", "name", "generation", "gender", "introduction"})
        partial = query.run_query(workspace, "同名甲和同名乙是什么关系", {"0": "a"})
        self.assertEqual(partial["source_id"], "a")
        self.assertEqual([ambiguity["slot"] for ambiguity in partial["ambiguities"]], ["1"])
        resolved = query.run_query(workspace, "同名甲和同名乙是什么关系", {"0": "a", "1": "d"})
        self.assertEqual((resolved["source_id"], resolved["target_id"]), ("a", "d"))

    def test_reverse_grammar_resolutions_use_text_slot_order(self):
        workspace = named_graph({"a": (0, "male"), "b": (0, "male"), "c": (1, "female"), "d": (1, "female")})
        for person_id, name in (("a", "祖甲"), ("b", "祖甲"), ("c", "子乙"), ("d", "子乙")):
            workspace["people"][person_id]["name"] = name
        result = query.run_query(workspace, "子乙是祖甲的什么人", {"0": "d", "1": "b"})
        self.assertEqual((result["source_id"], result["target_id"]), ("b", "d"))

    def test_partial_aliases_merge_all_candidates_without_first_match(self):
        workspace = named_graph({"a": (0, "male"), "b": (0, "female"), "c": (1, "female")})
        for person_id, name in (("a", "王甲（小王）"), ("b", "王乙（小王）"), ("c", "丙")):
            workspace["people"][person_id]["name"] = name
        for mention in ("小王", "王"):
            result = query.run_query(workspace, mention + "和丙是什么关系")
            self.assertEqual([item["id"] for item in result["ambiguities"][0]["candidates"]], ["a", "b"])

    def test_title_shortening_can_omit_middle_surname(self):
        workspace = public_demo("demo2")
        result = relatives(workspace, "奥雷里亚诺上校", "子女")
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["results"]), 18)
        self.assertEqual(workspace["people"][result["source_id"]]["name"], "奥雷里亚诺·布恩迪亚上校")
        self.assertTrue(all(item["path_result"]["direct_relationship"]["status"] == "resolved" for item in result["results"]))

    def test_bracket_name_and_ambiguous_base_in_demo2(self):
        workspace = public_demo("demo2")
        result = relatives(workspace, "梅梅", "子女")
        self.assertEqual([item["name"] for item in result["results"]], ["奥雷里亚诺·巴比伦"])
        ambiguous = relatives(workspace, "奥雷里亚诺", "子女")
        self.assertEqual(ambiguous["status"], "needs_disambiguation")
        self.assertGreater(len(ambiguous["ambiguities"][0]["candidates"]), 12)

    def test_wrong_candidate_is_not_accepted_even_for_unique_mention(self):
        workspace = named_graph({"甲": (0, "male"), "乙": (1, "female")})
        result = query.run_query(workspace, "甲和乙是什么关系", {"0": "乙"})
        self.assertEqual(result["status"], "needs_disambiguation")
        self.assertNotIn("source_id", result)
        self.assertEqual([item["id"] for item in result["ambiguities"][0]["candidates"]], ["甲"])

    def test_malformed_resolutions_return_structured_errors(self):
        workspace = named_graph({"甲": (0, "male"), "乙": (1, "female")})
        for resolutions in ([], "甲", {"2": "甲"}, {0: "甲"}, {"0": None}, {"0": []}):
            with self.subTest(resolutions=resolutions):
                self.assertEqual(query.run_query(workspace, "甲和乙是什么关系", resolutions)["status"], "unsupported")
        self.assertEqual(query.run_query(workspace, "甲和乙是什么关系", {"0": "不存在"})["status"], "needs_disambiguation")

    def test_not_found_empty_results_and_unsupported_are_distinct(self):
        workspace = named_graph({"甲": (0, "male")})
        self.assertEqual(query.run_query(workspace, "甲和不存在是什么关系")["status"], "not_found")
        result = relatives(workspace, "甲", "子女")
        self.assertEqual((result["status"], result["results"]), ("success", []))
        for text in ("", None, 123, "谁的妻子最漂亮", "甲的妻子有哪些", "甲年龄多大"):
            with self.subTest(text=text):
                result = query.run_query(workspace, text)
                self.assertEqual(result["status"], "unsupported")
                self.assertEqual((result["results"], result["ambiguities"]), ([], []))
                self.assertTrue(result["message"])

    def test_parent_children_and_gender_aliases_use_direct_edges(self):
        workspace = typed_fixture()
        expected = {"父母": {"f", "m", "extra"}, "爸爸": {"f", "extra"}, "妈妈": {"m"},
                    "子女": {"son", "daughter"}, "儿子": {"son"}, "女儿": {"daughter"}}
        for term, people in expected.items():
            with self.subTest(term=term):
                self.assertEqual(set(ids(relatives(workspace, "s", term))), people)

    def test_grandparents_and_grandchildren_distinguish_parent_sex(self):
        workspace = typed_fixture()
        expected = {"祖父母": {"g", "gm", "mg"}, "爷爷": {"g"}, "奶奶": {"gm"}, "外祖父母": {"mg"}, "外公": {"mg"},
                    "孙辈": {"gs", "gd"}, "孙子": {"gs"}, "孙女": set(), "外孙女": {"gd"}}
        for term, people in expected.items():
            with self.subTest(term=term):
                self.assertEqual(set(ids(relatives(workspace, "s", term))), people)

    def test_ancestors_and_descendants_include_far_generations(self):
        workspace = typed_fixture()
        self.assertEqual(set(ids(relatives(workspace, "s", "祖先"))), {"g", "gm", "mg", "f", "m", "extra"})
        self.assertEqual(set(ids(relatives(workspace, "s", "后代"))), {"son", "daughter", "gs", "gd"})

    def test_sibling_age_aliases_do_not_guess_from_name_order_or_intro(self):
        workspace = typed_fixture()
        workspace["people"]["bro"].update(order=999, introduction="年轻弟弟")
        workspace["people"]["sis"].update(order=-999, introduction="年长姐姐")
        for term in ("哥哥", "弟弟"):
            result = relatives(workspace, "s", term)
            self.assertEqual(ids(result), ["bro"])
            self.assertIn("没有长幼信息", result["message"])
            self.assertEqual(result["results"][0]["path_result"]["direct_relationship"]["results"][0]["label"], "兄弟（长幼未知）")
        for term in ("姐姐", "妹妹"):
            self.assertEqual(ids(relatives(workspace, "s", term)), ["sis"])

    def test_uncles_aunts_and_nephews_nieces_are_typed_by_branch(self):
        workspace = typed_fixture()
        expected = {"伯叔姑舅姨": {"punc", "paut", "munc", "maut"}, "叔叔": {"punc"}, "姑母": {"paut"}, "舅舅": {"munc"}, "姨妈": {"maut"}}
        for term, people in expected.items():
            self.assertEqual(set(ids(relatives(workspace, "s", term))), people)
        self.assertEqual(set(ids(relatives(workspace, "bro", "侄子女"))), {"son", "daughter"})
        self.assertEqual(set(ids(relatives(workspace, "sis", "侄女"))), {"daughter"})
        self.assertEqual(ids(relatives(workspace, "s", "外甥女")), ["niece"])

    def test_cousins_are_typed_by_both_branches_without_label_matching(self):
        workspace = typed_fixture()
        expected = {"堂表亲": {"pc", "pcf", "mc", "mcf"}, "堂兄弟": {"pc"}, "堂姐妹": set(),
                    "表兄弟": {"mc"}, "表姐妹": {"pcf", "mcf"}}
        for term, people in expected.items():
            with self.subTest(term=term):
                self.assertEqual(set(ids(relatives(workspace, "s", term))), people)
        with patch.object(query, "_label", return_value="任意显示文案"):
            self.assertEqual(set(ids(relatives(workspace, "s", "堂表亲"))), expected["堂表亲"])

    def test_distant_cousins_and_duplicate_parent_proofs_are_merged(self):
        workspace = named_graph({"g": (0, "male"), "gm": (0, "female"), "a": (1, "male"), "b": (1, "male"),
                                 "aa": (2, "male"), "bb": (2, "male"), "s": (3, "female"), "t": (3, "male")},
                                [(grand, child) for grand in ("g", "gm") for child in ("a", "b")] + [("a", "aa"), ("b", "bb"), ("aa", "s"), ("bb", "t")])
        self.assertEqual(ids(relatives(workspace, "s", "堂兄弟")), ["t"])
        self.assertEqual(relatives(workspace, "s", "堂兄弟")["results"][0]["path_result"]["direct_relationship"]["note"], "")

    def test_real_multiple_kinship_is_one_person_with_all_original_proofs(self):
        workspace = named_graph({"g": (0, "male"), "f1": (1, "male"), "f2": (1, "male"), "m": (1, "female"),
                                 "s": (2, "male"), "t": (2, "female")},
                                [("g", "f1"), ("g", "f2"), ("f1", "s"), ("f2", "t"), ("m", "s"), ("m", "t")])
        for term in ("姐妹", "堂姐妹"):
            result = relatives(workspace, "s", term)
            self.assertEqual(ids(result), ["t"])
            self.assertEqual(result["results"][0]["matched_labels"], ["姐妹（长幼未知）"] if term == "姐妹" else ["堂姐妹（长幼未知）"])
            direct = result["results"][0]["path_result"]["direct_relationship"]
            self.assertEqual([proof["label"] for proof in direct["results"]], ["姐妹（长幼未知）", "堂姐妹（长幼未知）"])
            self.assertIn("多重亲缘", direct["note"])

    def test_siblings_cannot_reappear_as_cousins_by_looping_through_grandparent(self):
        workspace = named_graph({"g": (0, "male"), "f": (1, "male"), "s": (2, "male"), "t": (2, "female")},
                                [("g", "f"), ("f", "s"), ("f", "t")])
        self.assertEqual(ids(relatives(workspace, "s", "姐妹")), ["t"])
        self.assertEqual(ids(relatives(workspace, "s", "堂表亲")), [])

    def test_explicit_adoptive_roles_and_biological_filters_remain_separate(self):
        workspace = named_graph({"bio": (0, "male"), "adopt": (0, "female"), "child": (1, "male")},
                                [("bio", "child"), ("adopt", "child", "special")])
        workspace["relationships"][1].update(parent_label="养母", child_label="养子")
        self.assertEqual(set(ids(relatives(workspace, "child", "父母"))), {"bio", "adopt"})
        self.assertEqual(ids(relatives(workspace, "child", "亲生父母")), ["bio"])
        self.assertEqual(ids(relatives(workspace, "child", "养亲")), ["adopt"])
        adopt = next(item for item in relatives(workspace, "child", "父母")["results"] if item["person_id"] == "adopt")
        self.assertEqual(adopt["matched_labels"], ["养母"])
        self.assertEqual(ids(relatives(workspace, "adopt", "养子")), ["child"])
        self.assertEqual(ids(relatives(workspace, "bio", "养子女")), [])

    def test_demo2_adoptive_mother_keeps_original_blood_aunt_result(self):
        workspace = public_demo("demo2")
        result = relatives(workspace, "奥雷里亚诺·何塞", "养母")
        self.assertEqual({item["name"] for item in result["results"]}, {"阿玛兰妲", "蕾梅黛丝·莫斯科特"})
        aunt = next(item for item in result["results"] if item["name"] == "阿玛兰妲")
        self.assertEqual([proof["label"] for proof in aunt["path_result"]["direct_relationship"]["results"]], ["姑母"])
        self.assertNotIn("appellation", aunt["path_result"]["direct_relationship"])
        self.assertEqual(aunt["matched_labels"], ["养母"])
        self.assertEqual(aunt["path_result"], core.relationship_query(workspace, result["source_id"], aunt["person_id"]))
        pair = query.run_query(workspace, "阿玛兰妲是奥雷里亚诺·何塞的什么人")
        self.assertNotIn("matched_labels", pair["results"][0])
        self.assertEqual(pair["results"][0]["path_result"], aunt["path_result"])

    def test_registered_family_special_can_supply_typed_sibling(self):
        workspace = named_graph({"p": (0, "female"), "a": (1, "male"), "b": (1, "female")}, [("p", "a", "special"), ("p", "b", "special")])
        for relationship in workspace["relationships"]:
            relationship.update(parent_label="养母", child_label="养子" if relationship["child_id"] == "a" else "养女")
        result = relatives(workspace, "a", "姐妹")
        self.assertEqual(ids(result), ["b"])
        self.assertEqual(result["results"][0]["path_result"]["direct_relationship"]["appellation"]["label"], "姐妹（长幼未知）")

    def test_teacher_arbitrary_labels_and_gender_mismatch_do_not_become_family(self):
        for parent_label, child_label in (("师父", "徒弟"), ("爸爸", "养子"), ("养母", "养子"), ("兄弟", "兄弟"), ("养父（恩人）", "养子")):
            workspace = named_graph({"p": (0, "male"), "c": (1, "male")}, [("p", "c", "special")])
            workspace["relationships"][0].update(parent_label=parent_label, child_label=child_label)
            self.assertEqual(ids(relatives(workspace, "c", "父母")), [])
            self.assertEqual(ids(relatives(workspace, "c", "养亲")), [])

    def test_common_child_and_pure_multiple_bridges_are_not_table_cousins(self):
        for steps in ("DU", "DUDU", "DDUU"):
            workspace, people = chain(steps)
            self.assertNotIn(people[-1], ids(relatives(workspace, "人物0", "表兄弟")))
        workspace, people = chain("DU")
        self.assertEqual(ids(relatives(workspace, "人物0", "父母")), [])
        self.assertEqual(ids(relatives(workspace, "人物0", "子女")), [people[1]])

    def test_synthetic_daily_table_cousins_keep_direction_gender_and_evidence(self):
        workspace, people = composition.KinshipCompositionTests().example()
        for source, target in (("薛蟠", "贾珍"), ("贾珍", "薛蟠")):
            result = relatives(workspace, source, "表兄弟")
            item = next(item for item in result["results"] if item["name"] == target)
            self.assertEqual(item["path_result"]["direct_relationship"]["appellation"]["label"], "表兄弟（平辈，长幼未知）")
            self.assertEqual(item["matched_labels"], ["表兄弟（平辈，长幼未知）"])
            self.assertIn("完整家庭路径", item["path_result"]["direct_relationship"]["appellation"]["explanation"])
        workspace["people"][people[-1]]["gender"] = "female"
        item = next(item for item in relatives(workspace, "薛蟠", "表姐妹")["results"] if item["name"] == "贾珍")
        self.assertEqual(item["path_result"]["direct_relationship"]["appellation"]["label"], "表姐妹（平辈，长幼未知）")

    def test_public_demo_daily_table_cousins_in_both_directions(self):
        workspace = public_demo("demo")
        for source, target in (("薛蟠", "贾珍"), ("贾珍", "薛蟠")):
            result = relatives(workspace, source, "表兄弟")
            item = next(item for item in result["results"] if item["name"] == target)
            self.assertEqual(item["path_result"]["direct_relationship"]["status"], "unsupported")
            self.assertEqual(item["path_result"]["direct_relationship"]["appellation"]["label"], "表兄弟（平辈，长幼未知）")
        self.assertGreater(len(relatives(workspace, "贾母", "孙辈")["results"]), 3)

    def test_one_request_builds_one_index_and_public_result_shape_has_no_metadata(self):
        workspace = typed_fixture()
        with patch.object(query, "QueryIndex", wraps=query.QueryIndex) as index:
            result = relatives(workspace, "s", "堂表亲")
        self.assertEqual(index.call_count, 1)
        for item in result["results"]:
            self.assertEqual(set(item), {"person_id", "name", "matched_labels", "path_result"})
            self.assertEqual(set(item["path_result"]), {"path_text", "person_ids", "relationship_ids", "direct_relationship"})
            direct = item["path_result"]["direct_relationship"]
            self.assertEqual(set(direct), {"status", "results", "note"})
            self.assertTrue(all(set(proof) == {"label", "explanation"} for proof in direct["results"]))

    def test_edges_and_people_order_do_not_change_query_sorting(self):
        workspace = typed_fixture()
        expected = relatives(workspace, "s", "堂表亲")
        reordered = copy.deepcopy(workspace)
        reordered["relationships"].reverse()
        reordered["people"] = dict(reversed(list(reordered["people"].items())))
        actual = relatives(reordered, "s", "堂表亲")
        self.assertEqual(ids(actual), ids(expected))
        for old, new in zip(expected["results"], actual["results"]):
            self.assertEqual(old["path_result"]["direct_relationship"], new["path_result"]["direct_relationship"])
            self.assertEqual(new["path_result"], core.relationship_query(reordered, "s", new["person_id"]))

    def test_rename_ids_and_names_do_not_determine_relative_types(self):
        workspace = typed_fixture()
        expected = set(ids(relatives(workspace, "s", "堂表亲")))
        renamed = copy.deepcopy(workspace)
        mapping = {person_id: f"id_{index}" for index, person_id in enumerate(reversed(list(workspace["people"])))}
        renamed["people"] = {mapping[person_id]: {**person, "id": mapping[person_id], "name": "名字" + mapping[person_id]} for person_id, person in workspace["people"].items()}
        for relationship in renamed["relationships"]:
            relationship.update(id="edge" + relationship["id"], parent_id=mapping[relationship["parent_id"]], child_id=mapping[relationship["child_id"]])
        result = relatives(renamed, "名字" + mapping["s"], "堂表亲")
        self.assertEqual(set(ids(result)), {mapping[person_id] for person_id in expected})

    def test_closest_kinship_precedes_more_distant_formal_cousins(self):
        workspace = named_graph({"g": (0, "male"), "a": (1, "male"), "b": (1, "male"),
                                 "aa": (2, "male"), "ab": (2, "male"), "bb": (2, "male"),
                                 "s": (3, "female"), "near": (3, "male"), "far": (3, "male")},
                                [("g", "a"), ("g", "b"), ("a", "aa"), ("a", "ab"), ("b", "bb"),
                                 ("aa", "s"), ("ab", "near"), ("bb", "far")])
        result = relatives(workspace, "s", "堂兄弟")
        self.assertEqual(ids(result), ["near", "far"])
        self.assertEqual([len(item["path_result"]["relationship_ids"]) for item in result["results"]], [4, 6])

    def test_daily_filter_uses_family_evidence_even_with_nonfamily_shortcut(self):
        workspace, people = composition.KinshipCompositionTests().example()
        workspace["relationships"].append({"id": "teacher-shortcut", "parent_id": people[0], "child_id": people[-1],
                                           "kind": "special", "parent_label": "老师", "child_label": "学生"})
        result = relatives(workspace, "薛蟠", "表兄弟")
        item = next(item for item in result["results"] if item["name"] == "贾珍")
        self.assertEqual(item["path_result"]["person_ids"], [people[0], people[-1]])
        appellation = item["path_result"]["direct_relationship"]["appellation"]
        self.assertEqual(appellation["label"], "表兄弟（平辈，长幼未知）")
        self.assertIn("完整家庭路径：薛蟠 → 薛母 → 王父", appellation["explanation"])

    def test_direct_adoption_all_genders_and_trimmed_registered_terms(self):
        for parent_gender, child_gender in itertools.product(("male", "female"), repeat=2):
            workspace = named_graph({"p": (0, parent_gender), "c": (1, child_gender)}, [("p", "c", "special")])
            relationship = workspace["relationships"][0]
            relationship.update(parent_label=" 养" + ("父" if parent_gender == "male" else "母") + " ",
                                child_label="养" + ("子" if child_gender == "male" else "女"))
            parents = relatives(workspace, "c", "养父母")
            children = relatives(workspace, "p", "养子女")
            self.assertEqual(ids(parents), ["p"])
            self.assertEqual(ids(children), ["c"])
            self.assertEqual(parents["results"][0]["matched_labels"], [relationship["parent_label"].strip()])
            self.assertEqual(children["results"][0]["matched_labels"], [relationship["child_label"]])

    def test_introduction_only_marriage_does_not_supply_relatives(self):
        workspace = named_graph({"p": (0, "male"), "c": (1, "female")})
        workspace["people"]["p"]["introduction"] = "c的父亲，也是另一个人物的丈夫。"
        workspace["people"]["c"]["introduction"] = "p的女儿，住在同一家。"
        self.assertEqual(ids(relatives(workspace, "p", "子女")), [])
        self.assertEqual(query.run_query(workspace, "p的妻子有哪些")["status"], "unsupported")

    def test_pure_function_and_all_public_pair_contracts(self):
        workspace = typed_fixture()
        before = copy.deepcopy(workspace)
        for source, target in itertools.product(workspace["people"], repeat=2):
            result = query.run_query(workspace, f"{source}和{target}是什么关系")
            self.assertEqual(result["results"][0]["path_result"], core.relationship_query(workspace, source, target))
        relatives(workspace, "s", "堂表亲")
        self.assertEqual(workspace, before)


if __name__ == "__main__":
    unittest.main()
