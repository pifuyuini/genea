import http.client
import json
import sys
import tempfile
import threading
import types
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

import genealogy_core as core
import server


def family_fixture(cross=False):
    workspace = core.default_workspace()
    generations = [core.add_generation(workspace, "first", name="父辈")]
    generations.append(core.add_generation(workspace, "below", generations[-1]["id"], "子辈"))
    generations.append(core.add_generation(workspace, "below", generations[-1]["id"], "后辈"))
    parent = core.add_person(workspace, {"generation_id": generations[0]["id"], "gender": "female", "name": "母亲", "introduction": "母亲的简介"})
    child = core.add_person(workspace, {"generation_id": generations[2 if cross else 1]["id"], "gender": "male", "name": "孩子", "introduction": "孩子的简介"})
    relationship = core.add_relationship(workspace, parent["id"], child["id"], allow_cross_generation=cross)
    return workspace, generations, parent, child, relationship


class ExperimentalConfigTests(unittest.TestCase):
    def setUp(self):
        mode = patch.object(server, "EXPERIMENTAL_CROSS_GENERATION", False)
        mode.start()
        self.addCleanup(mode.stop)
        self.directory = tempfile.TemporaryDirectory()
        server.configure_data_dir(self.directory.name)
        self.httpd = None

    def tearDown(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.thread.join(timeout=3)
            self.httpd.server_close()
        server.configure_data_dir(server.DEFAULT_DATA_DIR)
        self.directory.cleanup()

    def store(self, workspace):
        original = (json.dumps(workspace, ensure_ascii=False, indent=2) + "\n").encode()
        server.STATE_PATH.write_bytes(original)
        return original

    def request(self, method, path, payload=None):
        if self.httpd is None:
            class QuietHandler(server.FamilyHandler):
                def log_message(self, format, *args):
                    pass
            self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
            self.thread.start()
        connection = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=3)
        body = json.dumps(payload).encode() if payload is not None else None
        connection.request(method, path, body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read()
        result = json.loads(raw.decode()) if "application/json" in response.getheader("Content-Type", "") else raw
        status = response.status
        connection.close()
        return status, result

    def test_first_defaults_do_not_initialize_settings_or_workspace_on_config_reads(self):
        expected = {"experimental_features_enabled": False, "experimental_cross_generation": False,
                    "read_only": False, "read_only_reason": None}
        self.assertEqual(self.request("GET", "/api/config"), (200, expected))
        self.assertFalse(server.SETTINGS_PATH.exists())
        self.assertFalse(server.STATE_PATH.exists())
        self.assertEqual(self.request("GET", "/api/check")[0], 403)
        server.configure_experimental_cross_generation(True)
        status, config = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertTrue(config["experimental_features_enabled"])
        self.assertFalse(config["read_only"])
        status, report = self.request("GET", "/api/check")
        self.assertEqual(status, 200)
        self.assertEqual(report["status"], "unreadable")
        self.assertFalse(server.STATE_PATH.exists())
        self.assertFalse(server.SETTINGS_PATH.exists())
        self.assertFalse(server.PHOTOS_DIR.exists())

    def test_toggle_persists_only_settings_and_preserves_workspace_and_history_bytes(self):
        workspace = family_fixture()[0]
        workspace[server.HISTORY_KEY] = {"undo": [{"label": "此前操作", "workspace": deepcopy(workspace)}], "redo": []}
        original = self.store(workspace)
        for enabled in (True, False, True):
            status, config = self.request("POST", "/api/config", {"experimental_features_enabled": enabled})
            self.assertEqual(status, 200)
            self.assertEqual(config["experimental_features_enabled"], enabled)
            self.assertEqual(config["experimental_cross_generation"], enabled)
            self.assertEqual(server.STATE_PATH.read_bytes(), original)
            self.assertEqual(json.loads(server.SETTINGS_PATH.read_bytes()), {"experimental_features_enabled": enabled})
            self.assertFalse(server.PHOTOS_DIR.exists())
        server.configure_experimental_cross_generation(False)
        server.configure_data_dir(self.directory.name)
        self.assertTrue(server.configuration_status()["experimental_features_enabled"])
        self.assertEqual(server.history_status()["undo_label"], "此前操作")

    def test_settings_are_independent_per_family_and_override_legacy_defaults(self):
        server.update_configuration(True)
        with tempfile.TemporaryDirectory() as other:
            server.configure_data_dir(other)
            self.assertFalse(server.experimental_features_enabled())
            server.update_configuration(False)
            server.configure_experimental_cross_generation(True)
            self.assertFalse(server.experimental_features_enabled())
            server.configure_data_dir(self.directory.name)
            server.configure_experimental_cross_generation(False)
            self.assertTrue(server.experimental_features_enabled())
        self.assertFalse(server.STATE_PATH.exists())

    def test_toggle_requires_a_real_boolean_and_cannot_mutate_content(self):
        original = self.store(family_fixture()[0])
        for value in (None, 0, 1, "true", [], {}):
            status, result = self.request("POST", "/api/config", {"experimental_features_enabled": value})
            self.assertEqual(status, 400)
            self.assertIn("布尔值", result["error"])
            self.assertEqual(server.STATE_PATH.read_bytes(), original)
            self.assertFalse(server.SETTINGS_PATH.exists())

    def test_off_cross_generation_allows_workspace_history_original_path_and_photos(self):
        workspace, _, parent, child, _ = family_fixture(cross=True)
        server.PHOTOS_DIR.mkdir()
        (server.PHOTOS_DIR / "portrait.png").write_bytes(b"portrait")
        parent["photo_path"] = "/photos/portrait.png"
        original = self.store(workspace)
        status, config = self.request("GET", "/api/config")
        self.assertEqual(status, 200)
        self.assertTrue(config["read_only"])
        self.assertFalse(config["experimental_features_enabled"])
        self.assertIsInstance(config["read_only_reason"], str)
        self.assertEqual(self.request("GET", "/api/workspace"), (200, workspace))
        self.assertEqual(self.request("GET", "/api/history"), (200, {"undo_label": None, "redo_label": None}))
        with patch.object(core, "relationship_query", side_effect=AssertionError("Inference must stay disabled.")):
            status, result = self.request("GET", f"/api/path?from={child['id']}&to={parent['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(result, {"path_text": "妈妈", "person_ids": [child["id"], parent["id"]], "relationship_ids": [workspace["relationships"][0]["id"]]})
        self.assertEqual(self.request("GET", "/photos/portrait.png"), (200, b"portrait"))
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertFalse(server.SETTINGS_PATH.exists())

    def test_all_http_content_writes_are_blocked_before_photo_landing(self):
        workspace, generations, parent, child, relationship = family_fixture(cross=True)
        original = self.store(workspace)
        requests = [
            ("POST", "/api/generations", {"placement": "below", "anchor_id": generations[0]["id"]}),
            ("POST", "/api/people", {"generation_id": generations[0]["id"], "gender": "male", "name": "新人物"}),
            ("POST", "/api/relationships", {"source_id": parent["id"], "target_id": child["id"]}),
            ("POST", "/api/photos", {"person_id": parent["id"], "data_url": "data:image/png;base64,aW1hZ2U="}),
            ("PATCH", f"/api/people/{parent['id']}", {"name": "不应保存"}),
            ("PATCH", f"/api/generations/{generations[0]['id']}", {"name": "不应保存"}),
            ("PATCH", f"/api/generations/{generations[0]['id']}/people-order", {"person_ids": [parent["id"]]}),
            ("PATCH", f"/api/relationships/{relationship['id']}", {"kind": "special", "parent_label": "养母", "child_label": "养子"}),
            ("DELETE", f"/api/people/{parent['id']}", None),
            ("DELETE", f"/api/relationships/{relationship['id']}", None),
            ("DELETE", f"/api/generations/{generations[1]['id']}", None),
            ("POST", "/api/history/undo", {}),
            ("POST", "/api/history/redo", {}),
        ]
        for method, path, payload in requests:
            with self.subTest(method=method, path=path):
                status, result = self.request(method, path, payload)
                self.assertEqual(status, 403)
                self.assertIn("只读", result["error"])
                self.assertEqual(server.STATE_PATH.read_bytes(), original)
                self.assertFalse(server.PHOTOS_DIR.exists())
                self.assertFalse(server.STATE_PATH.with_suffix(".json.tmp").exists())
        action = Mock()
        with self.assertRaises(server.ReadOnlyError):
            server.mutate(action)
        action.assert_not_called()
        with self.assertRaises(server.ReadOnlyError):
            server.write_workspace(core.default_workspace())
        with self.assertRaises(server.ReadOnlyError):
            server.save_photo(parent["id"], b"photo", ".png")
        self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_history_only_cross_generation_including_discarded_tail_keeps_everything_read_only(self):
        cross_workspace = family_fixture(cross=True)[0]
        for direction, length in (("undo", 1), ("redo", 1), ("undo", server.HISTORY_LIMIT + 2)):
            current = family_fixture()[0]
            snapshots = [{"label": "跨代", "workspace": cross_workspace}]
            snapshots += [{"label": "普通", "workspace": deepcopy(current)}] * (length - 1)
            current[server.HISTORY_KEY] = {"undo": [], "redo": [], direction: snapshots}
            original = self.store(current)
            self.assertTrue(server.configuration_status()["read_only"])
            self.assertEqual(server.read_workspace()["relationships"], current["relationships"])
            with self.assertRaises(server.ReadOnlyError):
                server.navigate_history(direction)
            with self.assertRaises(server.ReadOnlyError):
                server.mutate(lambda workspace: workspace["people"].clear())
            self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_reenabling_restores_editing_and_undo_without_losing_roles(self):
        workspace, _, parent, _, _ = family_fixture(cross=True)
        original = self.store(workspace)
        status, config = self.request("POST", "/api/config", {"experimental_features_enabled": True})
        self.assertEqual(status, 200)
        self.assertFalse(config["read_only"])
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        status, result = self.request("PATCH", f"/api/people/{parent['id']}", {"name": "新名字"})
        self.assertEqual(status, 200)
        self.assertFalse(result["config"]["read_only"])
        self.assertTrue(result["config"]["experimental_features_enabled"])
        self.assertEqual(result["workspace"]["relationships"], workspace["relationships"])
        self.request("POST", "/api/config", {"experimental_features_enabled": False})
        blocked = server.STATE_PATH.read_bytes()
        self.assertEqual(self.request("POST", "/api/history/undo", {})[0], 403)
        self.assertEqual(server.STATE_PATH.read_bytes(), blocked)
        self.request("POST", "/api/config", {"experimental_features_enabled": True})
        status, restored = self.request("POST", "/api/history/undo", {})
        self.assertEqual(status, 200)
        self.assertEqual(restored["workspace"], workspace)
        self.assertTrue(restored["config"]["experimental_features_enabled"])

    def test_ordinary_workspace_keeps_adjacent_only_operations_when_off(self):
        workspace, generations, parent, child, _ = family_fixture()
        self.store(workspace)
        self.assertFalse(server.configuration_status()["read_only"])
        status, result = self.request("PATCH", f"/api/people/{parent['id']}", {"name": "改名"})
        self.assertEqual(status, 200)
        self.assertEqual(result["removed_relationship_ids"], [])
        status, result = self.request("POST", "/api/generations", {"placement": "below", "anchor_id": generations[0]["id"]})
        self.assertEqual(status, 201)
        self.assertEqual(result["workspace"]["relationships"], [])
        self.assertFalse(result["config"]["experimental_features_enabled"])
        self.assertEqual(server.history_status()["undo_label"], "添加代际")

    def test_query_requires_feature_and_reads_workspace_once_with_resolutions(self):
        workspace = family_fixture()[0]
        original = self.store(workspace)
        module = types.ModuleType("relationship_query")
        module.run_query = Mock(return_value={"status": "resolved", "mode": "pair", "text": "查询"})
        with patch.dict(sys.modules, {"relationship_query": module}):
            with patch.object(server, "read_workspace", wraps=server.read_workspace) as read:
                self.assertEqual(self.request("POST", "/api/query", {"text": "孩子和母亲是什么关系"})[0], 403)
                read.assert_not_called()
                module.run_query.assert_not_called()
                server.update_configuration(True)
                status, result = self.request("POST", "/api/query", {"text": "孩子和母亲是什么关系", "resolutions": {"孩子": "chosen-id"}})
                self.assertEqual(status, 200)
                self.assertEqual(result["status"], "resolved")
                read.assert_called_once_with()
                module.run_query.assert_called_once_with(workspace, "孩子和母亲是什么关系", {"孩子": "chosen-id"})
        self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_cli_existing_settings_priority_and_first_defaults_without_persisting(self):
        original = self.store(family_fixture(cross=True)[0])
        for saved in (None, False, True):
            for flag in (False, True):
                server.SETTINGS_PATH.unlink(missing_ok=True)
                if saved is not None:
                    server.SETTINGS_PATH.write_text(json.dumps({"experimental_features_enabled": saved}))
                settings_before = server.SETTINGS_PATH.read_bytes() if saved is not None else None
                arguments = ["server.py", "--data-dir", self.directory.name, "--port", "0"]
                if flag:
                    arguments.append("--experimental-cross-generation")
                with patch.object(sys, "argv", arguments), patch.object(server, "ThreadingHTTPServer") as http_server:
                    http_server.return_value.serve_forever.side_effect = KeyboardInterrupt
                    server.main()
                    expected = flag if saved is None else saved
                    self.assertEqual(server.configuration_status()["experimental_features_enabled"], expected)
                    http_server.return_value.server_close.assert_called_once_with()
                self.assertEqual(server.STATE_PATH.read_bytes(), original)
                self.assertEqual(server.SETTINGS_PATH.read_bytes() if server.SETTINGS_PATH.exists() else None, settings_before)
                self.assertFalse(server.PHOTOS_DIR.exists())

    def test_cli_allows_existing_corrupt_data_to_be_inspected_without_rewriting(self):
        original = b"{"
        server.STATE_PATH.write_bytes(original)
        with patch.object(sys, "argv", ["server.py", "--data-dir", self.directory.name, "--experimental-cross-generation"]), patch.object(server, "ThreadingHTTPServer") as http_server, patch.object(server, "read_state", side_effect=AssertionError("Startup must not load existing content.")):
            http_server.return_value.serve_forever.side_effect = KeyboardInterrupt
            server.main()
        status, report = self.request("GET", "/api/check")
        self.assertEqual(status, 200)
        self.assertEqual(report["status"], "unreadable")
        self.assertEqual(report["summary"]["repairable"], 0)
        self.assertEqual(self.request("GET", "/api/workspace")[0], 503)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertFalse(server.SETTINGS_PATH.exists())
        self.assertFalse(server.PHOTOS_DIR.exists())


if __name__ == "__main__":
    unittest.main()
