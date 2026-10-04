import http.client
import json
import sys
import tempfile
import threading
import unittest
from copy import deepcopy
from unittest.mock import patch

import genealogy_core as core
import server


def cross_generation_fixture():
    workspace = core.default_workspace()
    generations = [core.add_generation(workspace, "first", name="第1层")]
    for number in range(2, 6):
        generations.append(core.add_generation(workspace, "below", generations[-1]["id"], f"第{number}层"))
    parent = core.add_person(workspace, {"generation_id": generations[0]["id"], "gender": "female", "name": "母亲"})
    child = core.add_person(workspace, {"generation_id": generations[2]["id"], "gender": "male", "name": "孩子"})
    adopted = core.add_person(workspace, {"generation_id": generations[4]["id"], "gender": "female", "name": "养女"})
    standard = core.add_relationship(workspace, child["id"], parent["id"], allow_cross_generation=True)
    special = core.add_relationship(workspace, parent["id"], adopted["id"], allow_cross_generation=True)
    core.update_relationship(workspace, special["id"], {"kind": "special", "parent_label": "养母", "child_label": "养女"})
    return workspace, generations, parent, child, adopted, standard, special


class CrossGenerationCoreTests(unittest.TestCase):
    def setUp(self):
        self.workspace, self.generations, self.parent, self.child, self.adopted, self.standard, self.special = cross_generation_fixture()

    def test_default_rejects_nonadjacent_and_enabled_orients_reverse_input(self):
        self.workspace["relationships"] = []
        with self.assertRaisesRegex(core.ValidationError, "adjacent"):
            core.add_relationship(self.workspace, self.parent["id"], self.child["id"])
        relationship = core.add_relationship(self.workspace, self.child["id"], self.parent["id"], allow_cross_generation=True)
        self.assertEqual((relationship["parent_id"], relationship["child_id"], relationship["code"]),
                         (self.parent["id"], self.child["id"], "mother_son"))
        with self.assertRaises(core.ConflictError):
            core.add_relationship(self.workspace, self.parent["id"], self.child["id"], allow_cross_generation=True)

    def test_same_generation_and_self_relationships_are_rejected_in_both_modes(self):
        peer = core.add_person(self.workspace, {"generation_id": self.parent["generation_id"], "gender": "male", "name": "同排人物"})
        before = deepcopy(self.workspace)
        for enabled in (False, True):
            for target in (self.parent, peer):
                with self.subTest(enabled=enabled, target=target["name"]), self.assertRaises(core.ValidationError):
                    core.add_relationship(self.workspace, self.parent["id"], target["id"], allow_cross_generation=enabled)
                self.assertEqual(self.workspace, before)

    def test_metadata_edits_keep_standard_and_special_relationships_exactly(self):
        before = deepcopy(self.workspace["relationships"])
        for payload in ({"name": "新名字"}, {"introduction": "新的简介"},
                        {"photo_path": "/photos/portrait.png"}, {"order": 7}):
            updated, removed = core.update_person(self.workspace, self.parent["id"], payload, allow_cross_generation=True)
            self.assertEqual(removed, [])
            self.assertEqual(self.workspace["relationships"], before)
            for key, value in payload.items():
                self.assertEqual(updated[key], value)

    def test_gender_edits_refresh_only_standard_appellations(self):
        special = deepcopy(self.special)
        original_endpoints = (self.standard["parent_id"], self.standard["child_id"])
        core.update_person(self.workspace, self.parent["id"], {"gender": "male"}, allow_cross_generation=True)
        self.assertEqual((self.standard["code"], self.standard["parent_label"], self.standard["child_label"]),
                         ("father_son", "爸爸", "儿子"))
        core.update_person(self.workspace, self.child["id"], {"gender": "female"}, allow_cross_generation=True)
        self.assertEqual((self.standard["code"], self.standard["parent_label"], self.standard["child_label"]),
                         ("father_daughter", "爸爸", "女儿"))
        self.assertEqual((self.standard["parent_id"], self.standard["child_id"]), original_endpoints)
        self.assertEqual(self.special, special)

    def test_legal_parent_and_child_moves_keep_all_roles_and_relationships(self):
        before = deepcopy(self.workspace["relationships"])
        for person, generation in ((self.parent, self.generations[1]),
                                   (self.child, self.generations[4]),
                                   (self.child, self.generations[2])):
            updated, removed = core.update_person(self.workspace, person["id"], {"generation_id": generation["id"]}, allow_cross_generation=True)
            self.assertEqual(updated["generation_id"], generation["id"])
            self.assertEqual(removed, [])
            self.assertEqual(self.workspace["relationships"], before)

    def test_same_row_and_reversed_moves_reject_the_entire_payload(self):
        cases = ((self.parent["id"], self.generations[2]["id"]),
                 (self.parent["id"], self.generations[3]["id"]),
                 (self.child["id"], self.generations[0]["id"]))
        for person_id, generation_id in cases:
            workspace = deepcopy(self.workspace)
            before = deepcopy(workspace)
            with self.subTest(person_id=person_id, generation_id=generation_id):
                with self.assertRaises(core.ValidationError) as error:
                    core.update_person(workspace, person_id, {
                        "generation_id": generation_id, "name": "不应保存",
                        "gender": "female", "introduction": "不应保存",
                        "photo_path": "/photos/not-saved.png", "order": 99,
                    }, allow_cross_generation=True)
                self.assertIn(self.parent["name"], str(error.exception))
                self.assertIn(self.child["name"], str(error.exception))
                self.assertEqual(workspace, before)
        core.update_person(self.workspace, self.parent["id"], {"generation_id": self.generations[1]["id"]}, allow_cross_generation=True)
        before = deepcopy(self.workspace)
        with self.assertRaises(core.ValidationError):
            core.update_person(self.workspace, self.child["id"], {"generation_id": self.generations[0]["id"]}, allow_cross_generation=True)
        self.assertEqual(self.workspace, before)

    def test_moves_validate_all_incoming_outgoing_and_special_roles(self):
        outgoing = core.add_relationship(self.workspace, self.child["id"], self.adopted["id"], allow_cross_generation=True)
        core.update_relationship(self.workspace, outgoing["id"], {"kind": "special", "parent_label": "养父", "child_label": "养女"})
        core.update_person(self.workspace, self.child["id"], {"generation_id": self.generations[3]["id"]}, allow_cross_generation=True)
        before = deepcopy(self.workspace)
        cases = ((self.child["id"], self.generations[4]["id"], ("孩子", "养女")),
                 (self.child["id"], self.generations[0]["id"], ("母亲", "孩子")),
                 (self.adopted["id"], self.generations[0]["id"], ("母亲", "养女")))
        for person_id, generation_id, names in cases:
            with self.subTest(person_id=person_id, generation_id=generation_id):
                with self.assertRaises(core.ValidationError) as error:
                    core.update_person(self.workspace, person_id, {"generation_id": generation_id, "name": "不应保存"}, allow_cross_generation=True)
                for name in names:
                    self.assertIn(name, str(error.exception))
                self.assertEqual(self.workspace, before)

    def test_invalid_metadata_cannot_partially_apply_a_generation_change(self):
        before = deepcopy(self.workspace)
        for invalid in ({"gender": "unknown"}, {"name": ""}, {"name": None}):
            with self.subTest(invalid=invalid), self.assertRaises(core.ValidationError):
                core.update_person(self.workspace, self.child["id"],
                                   {"generation_id": self.generations[4]["id"], **invalid},
                                   allow_cross_generation=True)
            self.assertEqual(self.workspace, before)

    def test_inserting_appending_and_deleting_empty_generations_keep_relationships(self):
        before = deepcopy(self.workspace)
        for placement, anchor in (("below", self.generations[0]["id"]),
                                  ("below", self.generations[-1]["id"]),
                                  ("above", self.generations[0]["id"])):
            inserted = core.add_generation(self.workspace, placement, anchor, "新增空层", allow_cross_generation=True)
            self.assertEqual(self.workspace["relationships"], before["relationships"])
            core.delete_generation(self.workspace, inserted["id"])
            self.assertEqual(self.workspace, before)

    def test_deleting_an_existing_empty_generation_keeps_all_endpoints(self):
        before = deepcopy(self.workspace["relationships"])
        core.delete_generation(self.workspace, self.generations[1]["id"])
        self.assertEqual(self.workspace["relationships"], before)
        self.assertEqual([generation["position"] for generation in self.workspace["generations"]], [0, 1, 2, 3])

    def test_person_and_explicit_relationship_deletion_keep_existing_semantics(self):
        removed = core.delete_person(self.workspace, self.child["id"])
        self.assertEqual(removed, [self.standard["id"]])
        self.assertEqual(self.workspace["relationships"], [self.special])
        core.delete_relationship(self.workspace, self.special["id"])
        self.assertEqual(self.workspace["relationships"], [])
        self.assertIn(self.parent["id"], self.workspace["people"])
        self.assertIn(self.adopted["id"], self.workspace["people"])

    def test_cross_generation_relationship_paths_use_endpoint_roles(self):
        self.assertEqual(core.relationship_path(self.workspace, self.child["id"], self.parent["id"])["path_text"], "妈妈")
        self.assertEqual(core.relationship_path(self.workspace, self.parent["id"], self.child["id"])["path_text"], "儿子")
        self.assertEqual(core.relationship_path(self.workspace, self.adopted["id"], self.parent["id"])["path_text"], "养母")


class CrossGenerationServerTests(unittest.TestCase):
    def setUp(self):
        self.mode = patch.object(server, "EXPERIMENTAL_CROSS_GENERATION", True)
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.directory = tempfile.TemporaryDirectory()
        server.configure_data_dir(self.directory.name)
        self.workspace, self.generations, self.parent, self.child, self.adopted, self.standard, self.special = cross_generation_fixture()
        server.write_workspace(self.workspace)
        self.httpd = None

    def tearDown(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.thread.join(timeout=3)
        server.configure_data_dir(server.DEFAULT_DATA_DIR)
        self.directory.cleanup()

    def request(self, method, path, payload=None):
        if self.httpd is None:
            class QuietHandler(server.FamilyHandler):
                def log_message(self, format, *args):
                    pass

            self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=3)
        body = json.dumps(payload).encode() if payload is not None else None
        connection.request(method, path, body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        result = json.loads(response.read().decode())
        status = response.status
        connection.close()
        return status, result

    def test_config_is_read_only_and_independent_of_workspace_and_history(self):
        original = server.STATE_PATH.read_bytes()
        with patch.object(server, "read_state", side_effect=AssertionError("Config must not read state.")):
            for enabled in (False, True):
                server.configure_experimental_cross_generation(enabled)
                status, config = self.request("GET", "/api/config")
                self.assertEqual(status, 200)
                self.assertEqual(config["experimental_features_enabled"], enabled)
                self.assertEqual(config["experimental_cross_generation"], enabled)
                self.assertEqual(config["read_only"], not enabled)
                self.assertEqual(config["read_only_reason"] is None, enabled)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertEqual(self.request("GET", "/api/workspace"), (200, self.workspace))
        self.assertEqual(self.request("GET", "/api/history"), (200, {"undo_label": None, "redo_label": None}))
        self.assertEqual(self.request("POST", "/api/config", {})[0], 400)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertNotIn("experimental_cross_generation", server.read_workspace())
        self.assertNotIn(server.HISTORY_KEY, server.read_workspace())

    def test_http_creation_obeys_feature_switch_and_rejects_same_row(self):
        workspace = deepcopy(self.workspace)
        workspace["relationships"] = []
        peer = core.add_person(workspace, {"generation_id": self.generations[0]["id"], "gender": "male", "name": "同排人物"})
        server.write_workspace(workspace)
        server.configure_experimental_cross_generation(False)
        original = server.STATE_PATH.read_bytes()
        payload = {"source_id": self.child["id"], "target_id": self.parent["id"]}
        self.assertEqual(self.request("POST", "/api/relationships", payload)[0], 400)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        server.configure_experimental_cross_generation(True)
        status, result = self.request("POST", "/api/relationships", payload)
        self.assertEqual(status, 201)
        self.assertEqual((result["relationship"]["parent_id"], result["relationship"]["child_id"]),
                         (self.parent["id"], self.child["id"]))
        self.assertEqual(result["history"]["undo_label"], "建立关系")
        original = server.STATE_PATH.read_bytes()
        status, error = self.request("POST", "/api/relationships", {"source_id": self.parent["id"], "target_id": peer["id"]})
        self.assertEqual(status, 400)
        self.assertIn("different generations", error["error"])
        self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_http_metadata_gender_and_photo_updates_keep_all_relationships(self):
        status, result = self.request("PATCH", f"/api/people/{self.child['id']}",
                                      {"name": "新名字", "introduction": "新的简介", "gender": "female"})
        self.assertEqual(status, 200)
        self.assertEqual(result["removed_relationship_ids"], [])
        self.assertEqual(result["workspace"]["relationships"][0]["code"], "mother_daughter")
        self.assertEqual(result["workspace"]["relationships"][1], self.special)
        status, result = self.request("PATCH", f"/api/people/{self.parent['id']}", {"gender": "male"})
        self.assertEqual(status, 200)
        self.assertEqual(result["workspace"]["relationships"][0]["code"], "father_daughter")
        expected = deepcopy(result["workspace"]["relationships"])
        status, result = self.request("POST", "/api/photos", {
            "person_id": self.parent["id"], "filename": "portrait.png",
            "data_url": "data:image/png;base64,aW1hZ2U=",
        })
        self.assertEqual(status, 201)
        self.assertEqual(result["workspace"]["relationships"], expected)
        self.assertEqual(server.local_photo_path(result["photo_path"]).read_bytes(), b"image")
        self.assertEqual(result["history"]["undo_label"], "更新照片")
        self.assertEqual(server.read_workspace(), result["workspace"])

    def test_http_invalid_move_preserves_saved_bytes_and_redo_history(self):
        server.update_person_persisted(self.child["id"], {"name": "临时名字"})
        server.navigate_history("undo")
        original = server.STATE_PATH.read_bytes()
        history = server.history_status()
        for generation in self.generations[2:4]:
            status, result = self.request("PATCH", f"/api/people/{self.parent['id']}", {
                "generation_id": generation["id"], "name": "不应保存", "gender": "male", "introduction": "不应保存",
            })
            self.assertEqual(status, 400)
            self.assertIn(self.parent["name"], result["error"])
            self.assertIn(self.child["name"], result["error"])
            self.assertEqual(server.STATE_PATH.read_bytes(), original)
            self.assertEqual(server.history_status(), history)
            self.assertEqual(server.read_workspace(), self.workspace)

    def test_http_legal_move_and_undo_redo_preserve_cross_generation_roles(self):
        status, changed = self.request("PATCH", f"/api/people/{self.child['id']}", {"generation_id": self.generations[-1]["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(changed["removed_relationship_ids"], [])
        self.assertEqual(changed["workspace"]["relationships"], self.workspace["relationships"])
        self.assertEqual(changed["history"]["undo_label"], "移动人物")
        self.assertEqual(server.read_workspace(), changed["workspace"])
        status, undone = self.request("POST", "/api/history/undo", {})
        self.assertEqual(status, 200)
        self.assertEqual(undone["workspace"], self.workspace)
        status, redone = self.request("POST", "/api/history/redo", {})
        self.assertEqual(status, 200)
        self.assertEqual(redone["workspace"], changed["workspace"])
        self.assertEqual(redone["history"]["undo_label"], "移动人物")
        raw = json.loads(server.STATE_PATH.read_bytes())
        self.assertEqual(raw["schema_version"], 2)
        self.assertNotIn("experimental_cross_generation", raw)
        self.assertNotIn(server.HISTORY_KEY, raw[server.HISTORY_KEY]["undo"][-1]["workspace"])

    def test_http_inserting_appending_and_deleting_generations_keep_links(self):
        added_ids = []
        for anchor in (self.generations[0], self.generations[-1]):
            status, result = self.request("POST", "/api/generations", {"placement": "below", "anchor_id": anchor["id"], "name": "空层"})
            self.assertEqual(status, 201)
            self.assertEqual(result["workspace"]["relationships"], self.workspace["relationships"])
            added_ids.append(result["generation"]["id"])
        for generation_id in added_ids:
            status, result = self.request("DELETE", f"/api/generations/{generation_id}")
            self.assertEqual(status, 200)
            self.assertEqual(result["workspace"]["relationships"], self.workspace["relationships"])
        self.assertEqual(result["workspace"], self.workspace)

    def test_delete_person_undo_redo_restores_all_cross_generation_links(self):
        status, deleted = self.request("DELETE", f"/api/people/{self.parent['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(set(deleted["removed_relationship_ids"]), {self.standard["id"], self.special["id"]})
        self.assertEqual(deleted["workspace"]["relationships"], [])
        status, restored = self.request("POST", "/api/history/undo", {})
        self.assertEqual(status, 200)
        self.assertEqual(restored["workspace"], self.workspace)
        status, redone = self.request("POST", "/api/history/redo", {})
        self.assertEqual(status, 200)
        self.assertEqual(redone["workspace"], deleted["workspace"])

    def test_noop_metadata_edit_does_not_drop_links_or_rewrite_redo(self):
        server.update_person_persisted(self.child["id"], {"name": "临时名字"})
        server.navigate_history("undo")
        original = server.STATE_PATH.read_bytes()
        with patch.object(core, "now", return_value="2099-01-01T00:00:00+00:00"):
            updated, (_, removed) = server.update_person_persisted(self.child["id"], {"name": self.child["name"]})
        self.assertEqual(removed, [])
        self.assertEqual(updated, self.workspace)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertEqual(server.history_status()["redo_label"], "编辑人物")


class CrossGenerationStartupTests(unittest.TestCase):
    def setUp(self):
        self.mode = patch.object(server, "EXPERIMENTAL_CROSS_GENERATION", False)
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.directory = tempfile.TemporaryDirectory()
        server.configure_data_dir(self.directory.name)
        self.workspace = cross_generation_fixture()[0]

    def tearDown(self):
        server.configure_data_dir(server.DEFAULT_DATA_DIR)
        self.directory.cleanup()

    def store_raw(self, raw):
        original = (json.dumps(raw, ensure_ascii=False, indent=2) + "\n").encode()
        server.STATE_PATH.write_bytes(original)
        return original

    def ordinary_workspace(self):
        workspace = deepcopy(self.workspace)
        workspace["relationships"] = []
        return workspace

    def test_disabled_mode_reads_current_state_and_blocks_mutations_without_cleanup(self):
        original = self.store_raw(self.workspace)
        self.assertEqual(server.read_workspace(), self.workspace)
        self.assertTrue(server.configuration_status()["read_only"])
        for operation in (lambda: server.mutate(lambda workspace: workspace.clear()),
                          lambda: server.navigate_history("undo")):
            with self.assertRaises(server.ReadOnlyError):
                operation()
            self.assertEqual(server.STATE_PATH.read_bytes(), original)
            self.assertFalse(server.PHOTOS_DIR.exists())
            self.assertFalse(server.STATE_PATH.with_suffix(".json.tmp").exists())

    def test_disabled_mode_checks_every_persisted_undo_and_redo_snapshot(self):
        for direction, length in (("undo", 1), ("redo", 1), ("undo", server.HISTORY_LIMIT + 1)):
            raw = self.ordinary_workspace()
            entries = [{"label": "跨代快照", "workspace": self.workspace}]
            entries += [{"label": "普通快照", "workspace": self.ordinary_workspace()}] * (length - 1)
            raw[server.HISTORY_KEY] = {"undo": [], "redo": [], direction: entries}
            original = self.store_raw(raw)
            with self.subTest(direction=direction, length=length):
                self.assertEqual(server.read_workspace(), self.ordinary_workspace())
                self.assertTrue(server.configuration_status()["read_only"])
                with self.assertRaises(server.ReadOnlyError):
                    server.navigate_history(direction)
                self.assertEqual(server.STATE_PATH.read_bytes(), original)
                self.assertFalse(server.PHOTOS_DIR.exists())

    def test_enabled_mode_loads_and_restores_persisted_cross_generation_history(self):
        raw = self.ordinary_workspace()
        history = {"undo": [{"label": "跨代快照", "workspace": self.workspace}], "redo": []}
        raw[server.HISTORY_KEY] = history
        original = self.store_raw(raw)
        server.configure_experimental_cross_generation(True)
        current, loaded_history = server.read_state()
        self.assertEqual(current, self.ordinary_workspace())
        self.assertEqual(loaded_history, history)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        restored, status = server.navigate_history("undo")
        self.assertEqual(restored, self.workspace)
        self.assertEqual(status["redo_label"], "跨代快照")
        redone, _ = server.navigate_history("redo")
        self.assertEqual(redone, self.ordinary_workspace())
        self.assertEqual(server.read_workspace(), redone)

    def test_disabled_mode_rejects_cross_generation_writes_before_creating_files(self):
        with self.assertRaises(server.ReadOnlyError):
            server.write_workspace(self.workspace)
        self.assertFalse(server.STATE_PATH.exists())
        self.assertFalse(server.PHOTOS_DIR.exists())
        for direction in ("undo", "redo"):
            history = {"undo": [], "redo": [], direction: [{"label": "跨代快照", "workspace": self.workspace}]}
            with self.assertRaises(server.ReadOnlyError):
                server.write_workspace(self.ordinary_workspace(), history)
            self.assertFalse(server.STATE_PATH.exists())
            self.assertFalse(server.PHOTOS_DIR.exists())

    def test_cli_allows_read_only_current_and_history_cross_generation_without_rewriting(self):
        for location in ("current", "undo", "redo"):
            raw = deepcopy(self.workspace) if location == "current" else self.ordinary_workspace()
            if location != "current":
                raw[server.HISTORY_KEY] = {"undo": [], "redo": [], location: [{"label": "跨代快照", "workspace": self.workspace}]}
            original = self.store_raw(raw)
            arguments = ["server.py", "--data-dir", self.directory.name, "--port", "0"]
            with patch.object(sys, "argv", arguments), patch.object(server, "ThreadingHTTPServer") as http_server:
                http_server.return_value.serve_forever.side_effect = KeyboardInterrupt
                server.main()
                http_server.assert_called_once()
                self.assertTrue(server.configuration_status()["read_only"])
            self.assertEqual(server.STATE_PATH.read_bytes(), original)
            self.assertFalse(server.PHOTOS_DIR.exists())
            self.assertFalse(server.SETTINGS_PATH.exists())

    def test_cli_switch_defaults_to_false_and_enables_cross_generation_explicitly(self):
        for enabled in (False, True):
            original = self.store_raw(self.workspace if enabled else self.ordinary_workspace())
            server.configure_experimental_cross_generation(True)
            arguments = ["server.py", "--data-dir", self.directory.name]
            if enabled:
                arguments.append("--experimental-cross-generation")
            with patch.object(sys, "argv", arguments), patch.object(server, "ThreadingHTTPServer") as http_server:
                http_server.return_value.serve_forever.side_effect = KeyboardInterrupt
                server.main()
                self.assertIs(server.EXPERIMENTAL_CROSS_GENERATION, enabled)
                http_server.assert_called_once_with(("127.0.0.1", 8765), server.FamilyHandler)
                http_server.return_value.server_close.assert_called_once_with()
            self.assertEqual(server.STATE_PATH.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
