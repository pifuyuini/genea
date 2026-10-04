import http.client
import json
import tempfile
import threading
import unittest
from urllib.parse import urlencode
from unittest.mock import patch

import genealogy_core as core
import server


class PathApiTests(unittest.TestCase):
    def setUp(self):
        mode = patch.object(server, "EXPERIMENTAL_CROSS_GENERATION", True)
        mode.start()
        self.addCleanup(mode.stop)
        self.directory = tempfile.TemporaryDirectory(prefix="path-api-")
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(server.configure_data_dir, server.DATA_DIR)
        server.configure_data_dir(self.directory.name)
        self.workspace = core.default_workspace()
        upper = core.add_generation(self.workspace, "first")
        middle = core.add_generation(self.workspace, "below", upper["id"])
        lower = core.add_generation(self.workspace, "below", middle["id"])

        def person(generation, gender):
            return core.add_person(self.workspace, {"generation_id": generation["id"], "gender": gender, "name": "测试人物"})["id"]

        self.grand = person(upper, "male")
        self.father = person(middle, "male")
        self.mother = person(middle, "female")
        self.aunt = person(middle, "female")
        self.ego = person(lower, "male")
        self.cousin = person(lower, "female")
        self.isolated = person(lower, "female")
        for parent, child in ((self.grand, self.father), (self.grand, self.aunt), (self.father, self.ego), (self.mother, self.ego), (self.aunt, self.cousin)):
            core.add_relationship(self.workspace, parent, child)
        server.write_workspace(self.workspace)

        class QuietHandler(server.FamilyHandler):
            def log_message(self, format, *args):
                pass

        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.httpd.shutdown()
        self.thread.join(timeout=3)
        self.httpd.server_close()
        self.assertFalse(self.thread.is_alive())

    def request(self, source, target):
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=3)
        try:
            connection.request("GET", "/api/path?" + urlencode({"from": source, "to": target}))
            response = connection.getresponse()
            return response.status, json.loads(response.read().decode("utf-8"))
        finally:
            connection.close()

    def test_disabled_mode_returns_only_the_legacy_chain_without_inference(self):
        server.configure_experimental_cross_generation(False)
        original = server.STATE_PATH.read_bytes()
        with patch.object(core, "relationship_query", side_effect=AssertionError("Experimental inference must not run.")):
            for source, target in ((self.ego, self.cousin), (self.ego, self.isolated), (self.ego, self.ego)):
                status, result = self.request(source, target)
                self.assertEqual(status, 200)
                self.assertEqual(result, core.relationship_path(self.workspace, source, target))
                self.assertEqual(set(result), {"path_text", "person_ids", "relationship_ids"})
        self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_resolved_contract_includes_unchanged_chain_and_direct_results(self):
        expected_path = core.relationship_path(self.workspace, self.ego, self.cousin)
        before = server.STATE_PATH.read_bytes()
        status, result = self.request(self.ego, self.cousin)
        self.assertEqual(status, 200)
        self.assertEqual(set(result), {"path_text", "person_ids", "relationship_ids", "direct_relationship"})
        self.assertEqual({key: result[key] for key in expected_path}, expected_path)
        direct = result["direct_relationship"]
        self.assertEqual(set(direct), {"status", "results", "note"})
        self.assertEqual(direct["status"], "resolved")
        self.assertEqual(direct["results"][0]["label"], "姑表姐妹（长幼未知）")
        self.assertEqual(set(direct["results"][0]), {"label", "explanation"})
        self.assertTrue(direct["results"][0]["explanation"].startswith("测试人物"))
        self.assertNotIn("依据：", direct["results"][0]["explanation"])
        self.assertNotIn("person_", direct["results"][0]["explanation"])
        self.assertEqual(direct["note"], "")
        self.assertEqual(server.STATE_PATH.read_bytes(), before)
        self.assertEqual(server.history_status(), {"undo_label": None, "redo_label": None})

    def test_special_only_contract_keeps_registered_custom_labels(self):
        relationship = core.add_relationship(self.workspace, self.aunt, self.isolated)
        core.update_relationship(self.workspace, relationship["id"], {"kind": "special", "parent_label": "养母", "child_label": "养女"})
        server.write_workspace(self.workspace)
        status, result = self.request(self.isolated, self.aunt)
        self.assertEqual(status, 200)
        self.assertEqual(result["path_text"], "养母")
        self.assertEqual(result["person_ids"], [self.isolated, self.aunt])
        self.assertEqual(result["relationship_ids"], [relationship["id"]])
        self.assertEqual(result["direct_relationship"]["status"], "unsupported")
        self.assertEqual(result["direct_relationship"]["results"], [])
        self.assertTrue(result["direct_relationship"]["note"])
        composition = result["direct_relationship"]["composition"]
        self.assertEqual(composition["label"], "“养母”（登记特殊称谓）")
        self.assertIn("登记特殊称谓", composition["explanation"])
        self.assertTrue(composition["note"])

    def test_disconnected_contract_preserves_empty_legacy_path(self):
        status, result = self.request(self.ego, self.isolated)
        self.assertEqual(status, 200)
        self.assertEqual((result["path_text"], result["person_ids"], result["relationship_ids"]), ("", [], []))
        self.assertEqual(result["direct_relationship"]["status"], "disconnected")
        self.assertEqual(result["direct_relationship"]["results"], [])
        self.assertIn("未找到已登记的连接", result["direct_relationship"]["note"])

    def test_common_child_is_unsupported_not_spouse(self):
        status, result = self.request(self.father, self.mother)
        self.assertEqual(status, 200)
        self.assertTrue(result["relationship_ids"])
        self.assertEqual(result["direct_relationship"]["status"], "unsupported")
        self.assertEqual(result["direct_relationship"]["results"], [])
        self.assertIn("婚姻", result["direct_relationship"]["note"])
        composition = result["direct_relationship"]["composition"]
        self.assertEqual(set(composition), {"label", "explanation", "note"})
        self.assertEqual(composition["label"], "孩子的母亲")
        self.assertIn("共同孩子桥", composition["explanation"])
        self.assertIn("未登记夫妻", composition["note"])
        self.assertNotIn("person_", composition["explanation"])
        status, reverse = self.request(self.mother, self.father)
        self.assertEqual(status, 200)
        self.assertEqual(reverse["direct_relationship"]["composition"]["label"], "孩子的父亲")
        self.assertEqual(result["direct_relationship"]["appellation"]["label"], "孩子的母亲")
        self.assertEqual(reverse["direct_relationship"]["appellation"]["label"], "孩子的父亲")

    def test_self_contract(self):
        status, result = self.request(self.isolated, self.isolated)
        self.assertEqual(status, 200)
        self.assertEqual((result["path_text"], result["person_ids"], result["relationship_ids"]), ("自己", [self.isolated], []))
        self.assertEqual(result["direct_relationship"]["results"][0]["label"], "自己")
        self.assertEqual(result["direct_relationship"]["status"], "resolved")

    def test_multiple_relationship_contract(self):
        core.add_relationship(self.workspace, self.mother, self.cousin)
        server.write_workspace(self.workspace)
        status, result = self.request(self.ego, self.cousin)
        self.assertEqual(status, 200)
        self.assertEqual([item["label"] for item in result["direct_relationship"]["results"]], ["姐妹（长幼未知）", "姑表姐妹（长幼未知）"])
        self.assertIn("存在多重亲缘", result["direct_relationship"]["note"])

    def test_extended_formal_name_and_structure_keep_the_legacy_chain(self):
        generation = self.workspace["generations"][-1]
        current = self.ego
        for depth in (3, 4, 5):
            generation = core.add_generation(self.workspace, "below", generation["id"])
            child = core.add_person(self.workspace, {"generation_id": generation["id"], "gender": "male", "name": f"合成第{depth}代"})["id"]
            core.add_relationship(self.workspace, current, child)
            current = child
        core.update_person(self.workspace, self.aunt, {"gender": "male"})
        core.update_person(self.workspace, self.cousin, {"gender": "male"})
        server.write_workspace(self.workspace)
        expected = core.relationship_path(self.workspace, current, self.cousin)
        before = server.STATE_PATH.read_bytes()
        status, result = self.request(current, self.cousin)
        self.assertEqual(status, 200)
        self.assertEqual({key: result[key] for key in expected}, expected)
        direct = result["direct_relationship"]
        self.assertEqual(set(direct), {"status", "results", "note"})
        self.assertEqual(direct["results"][0]["label"], "堂曾祖父")
        self.assertIn("曾祖父的堂兄弟（长幼未知）", direct["results"][0]["explanation"])
        self.assertNotIn("依据：", direct["results"][0]["explanation"])
        self.assertNotIn("person_", direct["results"][0]["explanation"])
        self.assertEqual(server.STATE_PATH.read_bytes(), before)
        status, reverse = self.request(self.cousin, current)
        self.assertEqual(status, 200)
        self.assertEqual(reverse["direct_relationship"]["results"][0]["label"], "堂曾孙")

    def test_mixed_composition_contract_does_not_persist_new_data(self):
        from test_kinship_composition import chain

        workspace, people = chain("UuDDU", genders=["male", "female", "male", "female", "male", "male"], special_labels={1: ("爸爸", "孩子")})
        server.write_workspace(workspace)
        before = server.STATE_PATH.read_bytes()
        legacy = core.relationship_path(workspace, people[0], people[-1])
        status, result = self.request(people[0], people[-1])
        self.assertEqual(status, 200)
        self.assertEqual({key: result[key] for key in legacy}, legacy)
        direct = result["direct_relationship"]
        self.assertEqual(set(direct), {"status", "results", "note", "composition", "appellation"})
        self.assertEqual((direct["status"], direct["results"]), ("unsupported", []))
        self.assertEqual(direct["composition"]["label"], "母亲的“爸爸”（登记特殊称谓）的女儿的孩子的父亲")
        self.assertTrue(all(isinstance(value, str) and value for value in direct["composition"].values()))
        self.assertEqual(server.STATE_PATH.read_bytes(), before)
        self.assertEqual(server.history_status(), {"undo_label": None, "redo_label": None})

    def test_daily_cousin_appellation_preserves_old_chain_and_composition(self):
        from kinship_composition import compose_registered_connection
        from kinship_inference import infer_direct_relationship
        from test_kinship_composition import KinshipCompositionTests

        workspace, people = KinshipCompositionTests().example()
        server.write_workspace(workspace)
        legacy = core.relationship_path(workspace, people[0], people[-1])
        blood = infer_direct_relationship(workspace, people[0], people[-1])
        composition = compose_registered_connection(workspace, people[0], people[-1])
        before = server.STATE_PATH.read_bytes()
        status, result = self.request(people[0], people[-1])
        self.assertEqual(status, 200)
        self.assertEqual({key: result[key] for key in legacy}, legacy)
        direct = result["direct_relationship"]
        self.assertEqual({key: direct[key] for key in blood}, blood)
        self.assertEqual(direct["composition"], composition)
        appellation = direct["appellation"]
        self.assertEqual(set(appellation), {"label", "explanation", "note"})
        self.assertEqual(appellation["label"], "表兄弟（平辈，长幼未知）")
        self.assertIn("完整家庭路径：", appellation["explanation"])
        self.assertTrue(all(isinstance(value, str) and value for value in appellation.values()))
        self.assertEqual(server.STATE_PATH.read_bytes(), before)
        self.assertEqual(server.history_status(), {"undo_label": None, "redo_label": None})
        status, reverse = self.request(people[-1], people[0])
        self.assertEqual(status, 200)
        self.assertEqual(reverse["direct_relationship"]["appellation"]["label"], "表兄弟（平辈，长幼未知）")

    def test_nonfamily_multi_special_path_keeps_only_registered_composition(self):
        from test_kinship_composition import chain

        workspace, people = chain("du", special_labels={0: ("老师", "学生"), 1: ("师父", "徒弟")})
        server.write_workspace(workspace)
        status, result = self.request(people[0], people[-1])
        self.assertEqual(status, 200)
        self.assertEqual(result["direct_relationship"]["status"], "unsupported")
        self.assertNotIn("appellation", result["direct_relationship"])
        self.assertIn("composition", result["direct_relationship"])

    def test_missing_person_keeps_404_contract(self):
        for source, target in ((self.ego, "missing"), ("", self.ego), ("missing", "missing")):
            with self.subTest(source=source, target=target):
                status, result = self.request(source, target)
                self.assertEqual(status, 404)
                self.assertEqual(result, {"error": "Person not found."})


if __name__ == "__main__":
    unittest.main()
