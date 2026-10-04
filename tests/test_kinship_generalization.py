"""Independent graph and metamorphic acceptance checks for kinship and everyday appellations.

Run with the project interpreter. Default unittest discovery is memory-only.
The optional --report runner writes one explicit JSON acceptance report and
can compare the public literary demo with a supplied Git baseline in memory.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from copy import deepcopy
import itertools
import json
from pathlib import Path
import random
import signal
import subprocess
import time
import types
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import genealogy_core as core

DEMO = ROOT / "demo/data/workspace.json"
REPORT = {"seed": 20261003, "demo": {}, "synthetic": {}, "performance": [], "query_invocations": 0, "oracle_verified_queries": 0, "composition_witnesses_verified": 0, "appellation_witnesses_verified": 0}
BASELINE_DIRECT = None
BASELINE_PATH = None
BASELINE_QUERY = None


def query(workspace, source, target):
    REPORT["query_invocations"] += 1
    return core.relationship_query(workspace, source, target)


def graph(records, edges=()):
    """Create legal generation graphs with display data unrelated to kinship."""
    levels = sorted({level for level, gender in records.values()})
    workspace = {"schema_version": 2,
                 "generations": [{"id": f"g{level}", "position": level, "name": f"Level {level}"} for level in levels],
                 "people": {}, "relationships": []}
    for pid, (level, gender) in records.items():
        workspace["people"][pid] = {
            "id": pid, "generation_id": f"g{level}", "name": f"Name {pid}",
            "gender": gender, "order": len(workspace["people"]),
            "introduction": "Display text only", "photo_path": None,
            "created_at": "fixed", "updated_at": "fixed",
        }
    for index, edge in enumerate(edges):
        parent, child = edge[:2]
        kind = edge[2] if len(edge) > 2 else "standard"
        pg, cg = records[parent][1], records[child][1]
        workspace["relationships"].append({
            "id": f"edge{index:04d}", "parent_id": parent, "child_id": child,
            "kind": kind,
            "parent_label": ("爸爸" if pg == "male" else "妈妈") if kind == "standard" else (edge[3] if len(edge) > 3 else "师父"),
            "child_label": ("儿子" if cg == "male" else "女儿") if kind == "standard" else (edge[4] if len(edge) > 4 else "徒弟"),
            "code": ("father" if pg == "male" else "mother") + "_" + ("son" if cg == "male" else "daughter") if kind == "standard" else "special",
            "color_key": "standard" if kind == "standard" else "special",
            "created_at": "fixed", "updated_at": "fixed",
        })
    return workspace


def family_edge(edge, people):
    """An independent fixture vocabulary for explicitly registered family roles."""
    if edge["kind"] == "standard":
        return True
    parent_groups = [
        {"父": "male", "父亲": "male", "爸爸": "male", "母": "female", "母亲": "female", "妈妈": "female"},
        {"养父": "male", "养母": "female"},
        {"继父": "male", "继母": "female"},
        {"义父": "male", "义母": "female"},
        {"嫡父": "male", "嫡母": "female", "庶父": "male", "庶母": "female"},
    ]
    child_groups = [
        {"子": "male", "儿子": "male", "女": "female", "女儿": "female", "孩子": None},
        {"养子": "male", "养女": "female"},
        {"继子": "male", "继女": "female"},
        {"义子": "male", "义女": "female"},
        {"嫡子": "male", "嫡女": "female", "庶子": "male", "庶女": "female"},
    ]
    for parents, children in zip(parent_groups, child_groups):
        if edge["parent_label"] in parents and edge["child_label"] in children:
            parent_gender = people[edge["parent_id"]]["gender"]
            child_gender = people[edge["child_id"]]["gender"]
            return parents[edge["parent_label"]] == parent_gender and children[edge["child_label"]] in (None, child_gender)
    return False


def family_graph(workspace):
    links = {pid: set() for pid in workspace["people"]}
    for edge in workspace["relationships"]:
        if family_edge(edge, workspace["people"]):
            a, b = edge["parent_id"], edge["child_id"]
            links[a].add(b)
            links[b].add(a)
    return links


def familiar_cousins(source_gender="male", target_gender="male", special=None):
    records = {"g": (0, "male"), "m": (1, "female"), "a": (1, "female"),
               "s": (2, source_gender), "c": (2, "female"),
               "f": (1, "male"), "t": (2, target_gender)}
    edges = [("g", "m"), ("g", "a"), ("m", "s"), ("a", "c"), ("f", "c"), ("f", "t")]
    if special:
        parent_label, child_label, parent_gender = special
        records["g"] = (0, parent_gender)
        edges[1] = ("g", "a", "special", parent_label, child_label)
    return graph(records, edges)


def oracle(workspace):
    """Boolean reachability, without enumerating ancestry paths or naming."""
    parents = {pid: set() for pid in workspace["people"]}
    links = {pid: set() for pid in workspace["people"]}
    for edge in workspace["relationships"]:
        parent, child = edge["parent_id"], edge["child_id"]
        links[parent].add(child)
        links[child].add(parent)
        if edge["kind"] == "standard":
            parents[child].add(parent)
    ancestors = {}
    for start in workspace["people"]:
        seen, pending = {start}, [start]
        while pending:
            for parent in parents[pending.pop()]:
                if parent not in seen:
                    seen.add(parent)
                    pending.append(parent)
        ancestors[start] = seen
    return ancestors, links, family_graph(workspace)


def distance(links, start, target):
    pending = deque([(start, 0)])
    seen = {start}
    while pending:
        current, count = pending.popleft()
        if current == target:
            return count
        for neighbor in links[current] - seen:
            seen.add(neighbor)
            pending.append((neighbor, count + 1))
    return None


def semantic_signature(result):
    direct = result["direct_relationship"]
    return (direct["status"], tuple(item["label"] for item in direct["results"]),
            direct.get("composition", {}).get("label"), direct.get("appellation", {}).get("label"))


def remap(workspace, seed=20261003, rename=True):
    """Relabel IDs, reorder all records, and optionally change display language."""
    rng = random.Random(seed)
    changed = deepcopy(workspace)
    ids = list(changed["people"])
    names = ["岳父奶奶", "not a spouse", "الأسماء فقط", "Åsa 🌲", "名字不推亲属"]
    shuffled_ids = list(range(len(ids)))
    rng.shuffle(shuffled_ids)
    mapping = {old: f"renamed_{number:04d}" for old, number in zip(ids, shuffled_ids)}
    people = []
    for index, (pid, person) in enumerate(changed["people"].items()):
        person["id"] = mapping[pid]
        person["order"] = rng.randrange(10000)
        if rename:
            person["name"] = names[index % len(names)] + f" #{index}"
            person["introduction"] = "爸爸 mother wife son 妹妹"
        people.append((mapping[pid], person))
    rng.shuffle(people)
    changed["people"] = dict(people)
    for index, edge in enumerate(changed["relationships"]):
        edge["parent_id"], edge["child_id"] = mapping[edge["parent_id"]], mapping[edge["child_id"]]
        edge["id"] = f"new_edge_{len(changed['relationships']) - index:04d}"
    rng.shuffle(changed["relationships"])
    rng.shuffle(changed["generations"])
    return changed, mapping


def mixed_unique():
    return graph({"s": (1, "male"), "m": (0, "female"), "c": (1, "female"),
                  "f": (0, "male"), "t": (1, "male")},
                 [("m", "s"), ("m", "c"), ("f", "c"), ("f", "t")])


def collapsed(levels):
    records = {f"l{level}p{side}": (level, "male" if side == 0 else "female")
               for level in range(levels) for side in range(2)}
    edges = [(f"l{level}p{parent}", f"l{level + 1}p{child}")
             for level in range(levels - 1) for parent in range(2) for child in range(2)]
    return graph(records, edges)


class GeneralizationTests(unittest.TestCase):
    def check_query(self, workspace, source, target, evidence=None):
        ancestors, links, family_links = evidence or oracle(workspace)
        result = query(workspace, source, target)
        legacy = (BASELINE_PATH or core.relationship_path)(workspace, source, target)
        self.assertEqual(set(result), {"path_text", "person_ids", "relationship_ids", "direct_relationship"})
        self.assertEqual({key: result[key] for key in legacy}, legacy)
        steps = distance(links, source, target)
        direct = result["direct_relationship"]
        expected = "resolved" if ancestors[source] & ancestors[target] else ("unsupported" if steps is not None else "disconnected")
        self.assertEqual(direct["status"], expected)
        if BASELINE_QUERY is not None:
            legacy_query = BASELINE_QUERY(workspace, source, target)
            self.assertEqual({key: result[key] for key in ("path_text", "person_ids", "relationship_ids")},
                             {key: legacy_query[key] for key in ("path_text", "person_ids", "relationship_ids")})
            self.assertEqual({key: value for key, value in direct.items() if key != "appellation"},
                             legacy_query["direct_relationship"])
        if expected in ("resolved", "disconnected"):
            self.assertNotIn("appellation", direct)
        else:
            family_steps = distance(family_links, source, target)
            single_registered = steps == 1
            if family_steps is None and not single_registered:
                self.assertNotIn("appellation", direct)
            else:
                app = direct["appellation"]
                self.assertEqual(set(app), {"label", "explanation", "note"})
                for value in app.values():
                    self.assertIsInstance(value, str)
                    self.assertTrue(value.strip())
                marker = "完整家庭路径：" if family_steps is not None else "完整登记路径："
                self.assertIn(marker, app["explanation"])
                names = app["explanation"].rsplit(marker, 1)[1].removesuffix("。").split(" → ")
                by_name = {person["name"]: pid for pid, person in workspace["people"].items()}
                witness = [by_name[name] for name in names]
                self.assertEqual((witness[0], witness[-1]), (source, target))
                self.assertEqual(len(witness), len(set(witness)))
                self.assertEqual(len(witness) - 1, family_steps if family_steps is not None else 1)
                edge_by_pair = {frozenset((edge["parent_id"], edge["child_id"])): edge
                                for edge in workspace["relationships"]}
                net = 0
                for a, b in zip(witness, witness[1:]):
                    self.assertIn(b, family_links[a] if family_steps is not None else links[a])
                    edge = edge_by_pair[frozenset((a, b))]
                    net += 1 if a == edge["parent_id"] else -1
                positions = {generation["id"]: generation["position"] for generation in workspace["generations"]}
                self.assertEqual(net, positions[workspace["people"][target]["generation_id"]] -
                                 positions[workspace["people"][source]["generation_id"]])
                if app["label"].startswith(("表兄弟（平辈", "表姐妹（平辈")):
                    self.assertEqual(net, 0)
                    self.assertTrue(app["label"].startswith("表兄弟" if workspace["people"][target]["gender"] == "male" else "表姐妹"))
                REPORT["appellation_witnesses_verified"] += 1
        if expected == "resolved":
            self.assertTrue(direct["results"])
            self.assertNotIn("composition", direct)
            if BASELINE_DIRECT is not None:
                self.assertEqual(direct, BASELINE_DIRECT(workspace, source, target))
        else:
            self.assertEqual(direct["results"], [])
        if expected == "unsupported":
            comp = direct["composition"]
            self.assertEqual(set(comp), {"label", "explanation", "note"})
            for value in comp.values():
                self.assertIsInstance(value, str)
                self.assertTrue(value.strip())
            self.assertIn("完整登记路径：", comp["explanation"])
            witness_names = comp["explanation"].rsplit("完整登记路径：", 1)[1].removesuffix("。").split(" → ")
            by_name = {person["name"]: pid for pid, person in workspace["people"].items()}
            witness = [by_name[name] for name in witness_names]
            self.assertEqual((witness[0], witness[-1]), (source, target))
            self.assertEqual(len(witness) - 1, steps)
            self.assertEqual(len(witness), len(set(witness)))
            for a, b in zip(witness, witness[1:]):
                self.assertIn(b, links[a])
            REPORT["composition_witnesses_verified"] += 1
            if "登记特殊称谓" not in comp["label"]:
                self.assertNotIn("夫妻", comp["label"])
                self.assertNotIn("丈夫", comp["label"])
                self.assertNotIn("妻子", comp["label"])
        if expected == "disconnected":
            self.assertNotIn("composition", direct)
            self.assertEqual(result["person_ids"], [])
        else:
            self.assertEqual(len(result["relationship_ids"]), steps)
            self.assertEqual(result["person_ids"][0], source)
            self.assertEqual(result["person_ids"][-1], target)
            edge_map = {edge["id"]: edge for edge in workspace["relationships"]}
            labels = []
            for a, b, eid in zip(result["person_ids"], result["person_ids"][1:], result["relationship_ids"]):
                edge = edge_map[eid]
                self.assertEqual({a, b}, {edge["parent_id"], edge["child_id"]})
                labels.append(edge["child_label"] if a == edge["parent_id"] else edge["parent_label"])
            self.assertEqual(result["path_text"], "的".join(labels) if labels else "自己")
        REPORT["oracle_verified_queries"] += 1
        return result

    def test_demo_all_1444_directed_pairs_keep_path_contract_and_blood_results(self):
        workspace = json.loads(DEMO.read_text(encoding="utf-8"))
        self.assertEqual((len(workspace["people"]), len(workspace["relationships"])), (38, 42))
        before = deepcopy(workspace)
        evidence = oracle(workspace)
        counts, compositions, multiple, appellations = Counter(), 0, 0, Counter()
        started = time.perf_counter()
        for source, target in itertools.product(workspace["people"], repeat=2):
            with self.subTest(source=source, target=target):
                result = self.check_query(workspace, source, target, evidence)
                direct = result["direct_relationship"]
                counts[direct["status"]] += 1
                compositions += "composition" in direct
                multiple += len(direct["results"]) > 1
                if "appellation" in direct:
                    appellations[direct["appellation"]["label"]] += 1
        self.assertEqual(workspace, before)
        self.assertEqual(sum(counts.values()), 1444)
        REPORT["demo"] = {"people": 38, "relationships": 42, "directed_pairs": 1444,
                          "status_distribution": dict(counts), "composition_count": compositions,
                          "multiple_blood_labels": multiple,
                          "baseline_resolved_comparison": BASELINE_DIRECT is not None,
                          "baseline_path_comparison": BASELINE_PATH is not None,
                          "baseline_all_direct_fields_comparison": BASELINE_QUERY is not None,
                          "appellation_count": sum(appellations.values()),
                          "appellation_distribution": dict(appellations),
                          "seconds": round(time.perf_counter() - started, 6)}

    def test_demo_xuepan_to_jiazhen_and_reverse_use_registered_mixed_evidence(self):
        workspace = json.loads(DEMO.read_text(encoding="utf-8"))
        source = next(pid for pid, p in workspace["people"].items() if p["name"] == "薛蟠")
        target = next(pid for pid, p in workspace["people"].items() if p["name"] == "贾珍")
        for a, b in ((source, target), (target, source)):
            result = self.check_query(workspace, a, b)
            self.assertEqual(result["direct_relationship"]["appellation"]["label"], "表兄弟（平辈，长幼未知）")
            comp = result["direct_relationship"]["composition"]
            self.assertIn("共同孩子桥", comp["explanation"])
            self.assertIn(workspace["people"][a]["name"], comp["explanation"])
            self.assertIn(workspace["people"][b]["name"], comp["explanation"])
            self.assertNotEqual(comp["label"], result["path_text"])

    def test_unique_mixed_chain_preserves_direction_and_bridge_meaning(self):
        workspace = mixed_unique()
        forward = self.check_query(workspace, "s", "t")["direct_relationship"]["composition"]
        reverse = self.check_query(workspace, "t", "s")["direct_relationship"]["composition"]
        self.assertEqual(forward["label"], "母亲的孩子的父亲的儿子")
        self.assertEqual(reverse["label"], "父亲的孩子的母亲的儿子")
        self.assertIn("共同孩子桥", forward["explanation"])
        self.assertIn("不能据此证明婚姻", forward["note"])

    def test_unique_mixed_chain_names_ids_and_record_order_are_irrelevant(self):
        workspace = mixed_unique()
        expected = {}
        for source, target in itertools.product(workspace["people"], repeat=2):
            expected[source, target] = semantic_signature(self.check_query(workspace, source, target))
        for seed in range(5):
            changed, mapping = remap(workspace, seed)
            for source, target in expected:
                self.assertEqual(semantic_signature(self.check_query(changed, mapping[source], mapping[target])),
                                 expected[source, target])
        REPORT["synthetic"]["unique_graph_metamorphisms"] = {"variants": 5, "pairs_per_variant": 25}

    def test_equivalent_common_children_and_many_parents_do_not_create_marriage(self):
        workspace = graph({"a": (0, "female"), "b": (0, "male"), "other": (0, "male"),
                           "c": (1, "male"), "d": (1, "female")},
                          [(p, c) for p in ("a", "b", "other") for c in ("c", "d")])
        expected = query(workspace, "a", "b")["direct_relationship"]
        self.assertEqual(expected["status"], "unsupported")
        self.assertEqual(expected["composition"]["label"], "孩子的父亲")
        for seed in range(6):
            changed, mapping = remap(workspace, seed, rename=False)
            result = self.check_query(changed, mapping["a"], mapping["b"])["direct_relationship"]
            self.assertEqual(result["composition"]["label"], expected["composition"]["label"])
        for a, b in itertools.product(workspace["people"], repeat=2):
            self.check_query(workspace, a, b)

    def test_two_independent_common_child_bridges_keep_both_connections(self):
        workspace = graph({"a": (0, "female"), "b": (0, "male"), "d": (0, "female"),
                           "c1": (1, "male"), "c2": (1, "female")},
                          [("a", "c1"), ("b", "c1"), ("b", "c2"), ("d", "c2")])
        comp = self.check_query(workspace, "a", "d")["direct_relationship"]["composition"]
        self.assertEqual(comp["label"], "孩子的父亲的孩子的母亲")
        self.assertIn("Name c1", comp["explanation"])
        self.assertIn("Name c2", comp["explanation"])

    def test_special_called_dad_is_only_a_quoted_registered_label(self):
        workspace = graph({"p": (0, "male"), "c": (1, "male")},
                          [("p", "c", "special", "爸爸", "儿子")])
        for source, target, original in (("c", "p", "爸爸"), ("p", "c", "儿子")):
            result = self.check_query(workspace, source, target)
            comp = result["direct_relationship"]["composition"]
            self.assertIn(original, comp["label"])
            self.assertIn("登记特殊称谓", comp["label"])
            self.assertNotEqual(comp["label"], "父亲")
            self.assertEqual(result["path_text"], original)

    def test_special_display_terms_are_not_used_as_structural_tokens(self):
        for special in ("母亲", "wife", "妻子", "丈夫", "叔父", "الأب", "⟪自定义⟫"):
            workspace = graph({"a": (0, "male"), "b": (1, "female"), "c": (2, "male")},
                              [("a", "b", "special", special, "任意下称谓"), ("b", "c")])
            result = self.check_query(workspace, "c", "a")
            comp = result["direct_relationship"]["composition"]
            self.assertIn(special, comp["label"])
            self.assertIn("登记特殊称谓", comp["label"])
            self.assertIn("母亲", comp["label"])
            self.assertEqual(result["direct_relationship"]["results"], [])

    def test_far_common_ancestor_overlap_does_not_turn_siblings_into_cousins(self):
        workspace = graph({"root": (0, "male"), "g": (1, "female"), "p": (2, "male"),
                           "a": (3, "male"), "b": (3, "female")},
                          [("root", "g"), ("g", "p"), ("p", "a"), ("p", "b")])
        a = self.check_query(workspace, "a", "b")["direct_relationship"]["results"]
        b = self.check_query(workspace, "b", "a")["direct_relationship"]["results"]
        self.assertEqual([x["label"] for x in a], ["姐妹（长幼未知）"])
        self.assertEqual([x["label"] for x in b], ["兄弟（长幼未知）"])

    def test_input_edge_order_does_not_choose_a_different_composition(self):
        workspace = graph({"a": (0, "female"), "b": (0, "male"), "d": (0, "female"),
                           "c1": (1, "male"), "c2": (1, "female")},
                          [("a", "c1"), ("b", "c1"), ("a", "c2"), ("d", "c2")])
        expected = query(workspace, "a", "b")["direct_relationship"]
        for seed in range(10):
            changed = deepcopy(workspace)
            random.Random(seed).shuffle(changed["relationships"])
            changed["people"] = dict(reversed(list(changed["people"].items())))
            self.assertEqual(self.check_query(changed, "a", "b")["direct_relationship"], expected)

    def test_names_and_introductions_do_not_change_demo_relationship_labels(self):
        workspace = json.loads(DEMO.read_text(encoding="utf-8"))
        renamed = deepcopy(workspace)
        for index, person in enumerate(renamed["people"].values()):
            person["name"] = ["mother father", "عائلة", "家族 🔍", "wife 妻子"][index % 4] + str(index)
            person["introduction"] = "丈夫 祖母 舅舅"
        count = 0
        for source, target in itertools.product(workspace["people"], repeat=2):
            self.assertEqual(semantic_signature(query(workspace, source, target)),
                             semantic_signature(query(renamed, source, target)))
            count += 1
        REPORT["demo"]["display_rename_directed_pairs"] = count

    def test_seeded_216_person_graph_matches_reachability_and_direction_oracle(self):
        rng = random.Random(20261003)
        records = {f"level{level}_p{person}": (level, rng.choice(("male", "female")))
                   for level in range(9) for person in range(24)}
        edges = []
        for level in range(1, 9):
            for person in range(24):
                child = f"level{level}_p{person}"
                parents = rng.sample(range(24), 2 if rng.random() < 0.4 else 1)
                for parent in parents:
                    kind = "special" if rng.random() < 0.16 else "standard"
                    edges.append((f"level{level - 1}_p{parent}", child, kind))
        workspace = graph(records, edges)
        before = deepcopy(workspace)
        evidence = oracle(workspace)
        ids = list(records)
        pairs = list(itertools.product(ids, repeat=2))
        counts, appellations = Counter(), Counter()
        started = time.perf_counter()
        for source, target in sorted(pairs):
            direct = self.check_query(workspace, source, target, evidence)["direct_relationship"]
            counts[direct["status"]] += 1
            if "appellation" in direct:
                appellations[direct["appellation"]["label"]] += 1
        self.assertEqual(workspace, before)
        REPORT["synthetic"]["seeded_graph"] = {
            "people": len(records), "edges": len(edges), "directed_pairs": len(pairs),
            "status_distribution": dict(counts), "coverage": "all ordered person pairs",
            "appellation_count": sum(appellations.values()), "appellation_distribution": dict(appellations),
            "seconds": round(time.perf_counter() - started, 6)}

    def test_ten_layer_pedigree_collapse_has_valid_results_and_no_side_effects(self):
        workspace = collapsed(10)
        before = deepcopy(workspace)
        for a, b in (("l9p0", "l9p1"), ("l9p1", "l9p0"), ("l9p0", "l0p0")):
            self.check_query(workspace, a, b)
        self.assertEqual(workspace, before)
        REPORT["synthetic"]["pedigree_collapse_correctness"] = {"people": 20, "edges": 36, "directed_pairs": 3}


    def test_familiar_cousins_need_no_common_ancestor_and_follow_target_gender(self):
        for source_gender, target_gender in itertools.product(("male", "female"), repeat=2):
            workspace = familiar_cousins(source_gender, target_gender)
            before = deepcopy(workspace)
            for source, target, gender in (("s", "t", target_gender), ("t", "s", source_gender)):
                direct = self.check_query(workspace, source, target)["direct_relationship"]
                self.assertEqual((direct["status"], direct["results"]), ("unsupported", []))
                self.assertEqual(direct["appellation"]["label"],
                                 ("表兄弟" if gender == "male" else "表姐妹") + "（平辈，长幼未知）")
            self.assertEqual(workspace, before)

    def test_recognized_family_specials_support_daily_cousins_without_blood_claim(self):
        profiles = [("爸爸", "女儿", "male"), ("养父", "养女", "male"),
                    ("继母", "继女", "female"), ("义父", "义女", "male"),
                    ("嫡母", "庶女", "female")]
        for profile in profiles:
            with self.subTest(profile=profile):
                workspace = familiar_cousins(special=profile)
                direct = self.check_query(workspace, "s", "t")["direct_relationship"]
                self.assertEqual(direct["status"], "unsupported")
                self.assertEqual(direct["results"], [])
                self.assertEqual(direct["appellation"]["label"], "表兄弟（平辈，长幼未知）")

    def test_unknown_teacher_and_mismatched_family_roles_do_not_generalize(self):
        profiles = [("师父", "徒弟", "male"), ("像养父的老师", "徒弟", "male"),
                    ("养父", "义女", "male"), ("养父", "养女", "female")]
        for profile in profiles:
            with self.subTest(profile=profile):
                workspace = familiar_cousins(special=profile)
                direct = self.check_query(workspace, "s", "t")["direct_relationship"]
                self.assertEqual(direct["status"], "unsupported")
                self.assertNotIn("appellation", direct)
                self.assertTrue(direct["composition"])

    def test_single_nonfamily_special_uses_registered_term_without_network_expansion(self):
        workspace = graph({"teacher": (0, "male"), "student": (1, "female"), "child": (2, "male")},
                          [("teacher", "student", "special", "师父", "徒弟"), ("student", "child")])
        self.assertEqual(self.check_query(workspace, "student", "teacher")["direct_relationship"]["appellation"]["label"], "师父")
        self.assertEqual(self.check_query(workspace, "teacher", "student")["direct_relationship"]["appellation"]["label"], "徒弟")
        self.assertNotIn("appellation", self.check_query(workspace, "child", "teacher")["direct_relationship"])

    def test_family_path_can_be_longer_than_the_original_teacher_shortcut(self):
        workspace = familiar_cousins()
        shortcut = graph({"m": (1, "female"), "t": (2, "male")},
                         [("m", "t", "special", "老师", "学生")])["relationships"][0]
        shortcut["id"] = "teacher_shortcut"
        workspace["relationships"].append(shortcut)
        result = self.check_query(workspace, "s", "t")
        self.assertEqual(len(result["relationship_ids"]), 2)
        app = result["direct_relationship"]["appellation"]
        self.assertEqual(app["label"], "表兄弟（平辈，长幼未知）")
        names = app["explanation"].rsplit("完整家庭路径：", 1)[1].removesuffix("。").split(" → ")
        self.assertEqual(len(names) - 1, 6)

    def test_shared_children_only_keep_parent_label_with_many_parents(self):
        workspace = graph({"a": (0, "female"), "b": (0, "male"), "d": (0, "female"),
                           "c1": (1, "male"), "c2": (1, "female")},
                          [(parent, child) for parent in ("a", "b", "d") for child in ("c1", "c2")])
        for source, target in itertools.permutations(("a", "b", "d"), 2):
            direct = self.check_query(workspace, source, target)["direct_relationship"]
            self.assertEqual(direct["appellation"]["label"],
                             "孩子的父亲" if workspace["people"][target]["gender"] == "male" else "孩子的母亲")
            self.assertNotIn("表", direct["appellation"]["label"])

    def test_pure_two_bridge_connection_uses_plain_peer_not_cousin(self):
        workspace = graph({"a": (0, "female"), "b": (0, "male"), "d": (0, "female"),
                           "c1": (1, "male"), "c2": (1, "female")},
                          [("a", "c1"), ("b", "c1"), ("b", "c2"), ("d", "c2")])
        for source, target in (("a", "d"), ("d", "a")):
            label = self.check_query(workspace, source, target)["direct_relationship"]["appellation"]["label"]
            self.assertIn("平辈亲戚", label)
            self.assertNotIn("表", label)

    def test_daily_generation_grades_follow_actual_parent_child_directions(self):
        workspace = familiar_cousins()
        # Extend the unrelated target branch above and below, not through names.
        for depth in range(1, 6):
            older = f"older{depth}"
            younger = f"younger{depth}"
            extra = graph({older: (1 - depth, "male"), younger: (2 + depth, "female"),
                           "op": (2 - depth, "male"), "yp": (1 + depth, "female")},
                          [(older, "op"), ("yp", younger)])
            for pid in (older, younger):
                workspace["people"][pid] = extra["people"][pid]
                workspace["generations"].extend(g for g in extra["generations"]
                                                 if g["id"] == extra["people"][pid]["generation_id"] and
                                                 g["id"] not in {x["id"] for x in workspace["generations"]})
            for edge, parent, child in ((extra["relationships"][0], older, "f" if depth == 1 else f"older{depth - 1}"),
                                       (extra["relationships"][1], "t" if depth == 1 else f"younger{depth - 1}", younger)):
                edge["id"] = f"grade_{depth}_{edge['id']}"
                edge["parent_id"], edge["child_id"] = parent, child
                edge["parent_label"] = "爸爸" if workspace["people"][parent]["gender"] == "male" else "妈妈"
                edge["child_label"] = "儿子" if workspace["people"][child]["gender"] == "male" else "女儿"
                workspace["relationships"].append(edge)
            for target in (older, younger):
                app = self.check_query(workspace, "s", target)["direct_relationship"]["appellation"]
                self.assertIn("辈", app["label"])
                self.assertIn("亲戚", app["label"])
                self.assertNotIn("表兄弟", app["label"])
                self.assertNotIn("表姐妹", app["label"])
                delta = -1 - depth if target == older else depth
                tier = ({-2: "祖", -3: "曾祖", -4: "高祖"}.get(delta, "高祖辈以上") if delta < 0
                        else {1: "侄", 2: "孙", 3: "曾孙", 4: "玄孙"}.get(delta, "玄孙辈以下"))
                self.assertIn(tier, app["label"])
                self.assertIn(f"目标{'长' if delta < 0 else '晚'}{abs(delta)}辈", app["explanation"])

    def test_familiar_unique_graph_names_ids_and_record_order_never_decide_terms(self):
        workspace = familiar_cousins()
        expected = semantic_signature(self.check_query(workspace, "s", "t"))
        for seed in range(6):
            changed, mapping = remap(workspace, seed)
            self.assertEqual(semantic_signature(self.check_query(changed, mapping["s"], mapping["t"])), expected)
        REPORT["synthetic"]["familiar_graph_metamorphisms"] = {"variants": 6, "directed_pairs": 6}


def baseline_function(ref):
    """Load only explicitly scoped baseline modules in memory; no files."""
    def source(path):
        return subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT, text=True)
    naming = types.ModuleType("generalization_baseline_naming")
    naming.__file__ = str(ROOT / "kinship_naming.py")
    exec(compile(source("kinship_naming.py"), naming.__file__, "exec"), naming.__dict__)
    inference = types.ModuleType("generalization_baseline_inference")
    exec(compile(source("kinship_inference.py"), str(ROOT / "kinship_inference.py"), "exec"), inference.__dict__)
    inference.name_distant_relationship = naming.name_distant_relationship
    inference.structural_relationship = naming.structural_relationship
    composition = types.ModuleType("generalization_baseline_composition")
    exec(compile(source("kinship_composition.py"), str(ROOT / "kinship_composition.py"), "exec"), composition.__dict__)
    composition.infer_direct_relationship = inference.infer_direct_relationship
    legacy_core = types.ModuleType("generalization_baseline_core")
    legacy_core.__file__ = str(ROOT / "genealogy_core.py")
    core_source = source("genealogy_core.py").replace(
        "    from kinship_composition import compose_registered_connection" + chr(10), "")
    exec(compile(core_source, legacy_core.__file__, "exec"), legacy_core.__dict__)
    legacy_core.infer_direct_relationship = inference.infer_direct_relationship
    legacy_core.compose_registered_connection = composition.compose_registered_connection
    return inference.infer_direct_relationship, legacy_core.relationship_path, legacy_core.relationship_query


def performance_probe():
    """Bound ancestor-path explosion instead of extending the graph indefinitely."""
    previous = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise TimeoutError("Eight-second acceptance budget expired")
    signal.signal(signal.SIGALRM, expired)
    try:
        for levels in (6, 8, 10, 12):
            workspace = collapsed(levels)
            started = time.perf_counter()
            entry = {"levels": levels, "people": levels * 2, "edges": 4 * (levels - 1),
                     "upward_routes_per_bottom_person": 2 ** (levels - 1), "directed_queries": 1, "budget_seconds": 8}
            signal.setitimer(signal.ITIMER_REAL, 8)
            try:
                result = query(workspace, f"l{levels - 1}p0", f"l{levels - 1}p1")
                entry.update({"completed": True, "status": result["direct_relationship"]["status"],
                              "result_labels": len(result["direct_relationship"]["results"])})
            except TimeoutError:
                entry["completed"] = False
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                entry["seconds"] = round(time.perf_counter() - started, 6)
                REPORT["performance"].append(entry)
            if not entry["completed"]:
                break
    finally:
        signal.signal(signal.SIGALRM, previous)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--demo-path", type=Path)
    args, other = parser.parse_known_args()
    if args.demo_path:
        DEMO = args.demo_path
    if args.report:
        if args.baseline_ref:
            BASELINE_DIRECT, BASELINE_PATH, BASELINE_QUERY = baseline_function(args.baseline_ref)
            REPORT["baseline_ref"] = args.baseline_ref
        started = time.perf_counter()
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GeneralizationTests))
        performance_probe()
        REPORT["tests"] = {"run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                           "skipped": len(result.skipped), "passed": result.wasSuccessful(),
                           "seconds": round(time.perf_counter() - started, 6)}
        REPORT["failure_details"] = [{"test": str(test), "traceback": details}
                                     for test, details in result.failures + result.errors]
        args.report.write_text(json.dumps(REPORT, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Acceptance report: {args.report}")
        raise SystemExit(0 if result.wasSuccessful() else 1)
    unittest.main(argv=[__file__, *other])
