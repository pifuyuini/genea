import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import genealogy_core as core
import server


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        server.configure_data_dir(self.directory.name)
        self.workspace = core.default_workspace()
        self.upper = core.add_generation(self.workspace, "first", name="父辈")
        self.lower = core.add_generation(self.workspace, "below", self.upper["id"], "同辈")
        self.last = core.add_generation(self.workspace, "below", self.lower["id"], "子辈")
        self.parent = core.add_person(self.workspace, {"generation_id": self.upper["id"], "gender": "female", "name": "妈妈"})
        self.child = core.add_person(self.workspace, {"generation_id": self.lower["id"], "gender": "male", "name": "我"})
        self.sibling = core.add_person(self.workspace, {"generation_id": self.lower["id"], "gender": "female", "name": "妹妹"})
        self.relationship = core.add_relationship(self.workspace, self.parent["id"], self.child["id"])
        server.write_workspace(self.workspace)

    def tearDown(self):
        server.configure_data_dir(server.DEFAULT_DATA_DIR)
        self.directory.cleanup()

    def test_legacy_workspace_has_empty_history_and_reads_do_not_rewrite_it(self):
        original = server.STATE_PATH.read_bytes()
        self.assertEqual(server.history_status(), {"undo_label": None, "redo_label": None})
        self.assertEqual(server.read_workspace(), self.workspace)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertNotIn(server.HISTORY_KEY, json.loads(original))

    def test_person_delete_undo_redo_restores_relationship_and_photo(self):
        _, photo = server.save_photo(self.parent["id"], b"portrait", ".png")
        before_delete = server.read_workspace()
        deleted, removed = server.delete_person_persisted(self.parent["id"])
        self.assertNotIn(self.parent["id"], deleted["people"])
        self.assertEqual(removed, [self.relationship["id"]])
        self.assertEqual(server.history_status()["undo_label"], "删除人物")
        restored, status = server.navigate_history("undo")
        self.assertEqual(restored, before_delete)
        self.assertEqual(status["redo_label"], "删除人物")
        self.assertEqual(server.local_photo_path(photo).read_bytes(), b"portrait")
        redone, _ = server.navigate_history("redo")
        self.assertEqual(redone, deleted)
        self.assertTrue(server.local_photo_path(photo).exists())

    def test_move_and_reorder_undo_restore_exact_structure(self):
        before = server.read_workspace()
        order = [self.sibling["id"], self.child["id"]]
        ordered, _ = server.mutate(
            lambda workspace: core.reorder_generation_people(workspace, self.lower["id"], order),
            "调整人物排序",
        )
        moved, (_, removed) = server.update_person_persisted(self.child["id"], {"generation_id": self.last["id"]})
        self.assertEqual(removed, [self.relationship["id"]])
        self.assertEqual(moved["relationships"], [])
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, ordered)
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, before)
        server.navigate_history("redo")
        redone, _ = server.navigate_history("redo")
        self.assertEqual(redone, moved)

    def test_inserting_generation_undo_restores_cancelled_relationship(self):
        before = server.read_workspace()
        changed, generation = server.mutate(
            lambda workspace: core.add_generation(workspace, "below", self.upper["id"], "新一代"),
            "添加代际",
        )
        self.assertEqual(changed["relationships"], [])
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, before)
        self.assertNotIn(generation, restored["generations"])

    def test_special_relationship_edit_and_delete_can_be_undone(self):
        special, _ = server.mutate(
            lambda workspace: core.update_relationship(workspace, self.relationship["id"], {
                "kind": "special", "parent_label": "养母", "child_label": "养子",
            }),
            "编辑关系",
        )
        server.mutate(lambda workspace: core.delete_relationship(workspace, self.relationship["id"]), "删除关系")
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, special)
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, self.workspace)

    def test_history_survives_data_directory_reconfiguration_without_nested_snapshots(self):
        changed, _ = server.update_person_persisted(self.child["id"], {"name": "新的名字"})
        server.configure_data_dir(server.DEFAULT_DATA_DIR)
        server.configure_data_dir(self.directory.name)
        self.assertEqual(server.read_workspace(), changed)
        self.assertEqual(server.history_status()["undo_label"], "编辑人物")
        raw = json.loads(server.STATE_PATH.read_text())
        self.assertIn(server.HISTORY_KEY, raw)
        self.assertNotIn(server.HISTORY_KEY, raw[server.HISTORY_KEY]["undo"][0]["workspace"])
        self.assertNotIn(server.HISTORY_KEY, server.read_workspace())
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, self.workspace)

    def test_new_edit_clears_redo_and_cleans_only_abandoned_photo(self):
        _, first = server.save_photo(self.parent["id"], b"first", ".png")
        _, second = server.save_photo(self.parent["id"], b"second", ".png")
        unknown = server.PHOTOS_DIR / "not-created-by-history.png"
        unknown.write_bytes(b"keep")
        outside = Path(self.directory.name) / "outside.png"
        outside.write_bytes(b"outside")
        server.navigate_history("undo")
        self.assertTrue(server.local_photo_path(second).exists())
        server.update_person_persisted(self.child["id"], {"name": "新编辑"})
        self.assertIsNone(server.history_status()["redo_label"])
        self.assertFalse(server.local_photo_path(second).exists())
        self.assertTrue(server.local_photo_path(first).exists())
        self.assertEqual(unknown.read_bytes(), b"keep")
        self.assertEqual(outside.read_bytes(), b"outside")
        with self.assertRaises(core.ConflictError):
            server.navigate_history("redo")

    def test_history_limit_discards_old_snapshots_and_unused_photos(self):
        _, first = server.save_photo(self.parent["id"], b"old", ".png")
        _, second = server.save_photo(self.parent["id"], b"current", ".png")
        for index in range(server.HISTORY_LIMIT):
            server.update_person_persisted(self.child["id"], {"name": f"人物 {index}"})
        _, history = server.read_state()
        self.assertEqual(len(history["undo"]), server.HISTORY_LIMIT)
        self.assertFalse(server.local_photo_path(first).exists())
        self.assertTrue(server.local_photo_path(second).exists())
        for _ in range(server.HISTORY_LIMIT):
            server.navigate_history("undo")
        self.assertIsNone(server.history_status()["undo_label"])
        self.assertEqual(server.read_workspace()["people"][self.parent["id"]]["photo_path"], second)

    def test_noop_edits_preserve_redo_and_do_not_rewrite_storage(self):
        server.update_person_persisted(self.child["id"], {"name": "暂时改名"})
        server.navigate_history("undo")
        original = server.STATE_PATH.read_bytes()
        with patch.object(core, "now", return_value="2099-01-01T00:00:00+00:00"):
            server.update_person_persisted(self.child["id"], {"name": self.child["name"]})
            server.mutate(lambda workspace: core.update_relationship(workspace, self.relationship["id"], {"kind": "standard"}), "编辑关系")
            server.mutate(lambda workspace: core.update_generation(workspace, self.upper["id"], {"name": self.upper["name"]}), "编辑代际")
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertEqual(server.history_status()["redo_label"], "编辑人物")
        _, first = server.save_photo(self.parent["id"], b"same-image", ".png")
        original = server.STATE_PATH.read_bytes()
        _, second = server.save_photo(self.parent["id"], b"same-image", ".png")
        self.assertEqual(first, second)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_failed_write_keeps_history_and_photos_and_rolls_back_new_upload(self):
        _, photo = server.save_photo(self.parent["id"], b"old", ".png")
        original = server.STATE_PATH.read_bytes()
        original_photos = set(server.PHOTOS_DIR.iterdir())
        with patch.object(server, "write_workspace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                server.save_photo(self.parent["id"], b"new", ".png")
            with self.assertRaises(OSError):
                server.navigate_history("undo")
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertEqual(set(server.PHOTOS_DIR.iterdir()), original_photos)
        self.assertEqual(server.local_photo_path(photo).read_bytes(), b"old")

    def test_cleanup_failure_does_not_undo_a_successful_save(self):
        _, old = server.save_photo(self.parent["id"], b"old", ".png")
        _, newest = server.save_photo(self.parent["id"], b"new", ".png")
        server.navigate_history("undo")
        with patch.object(server, "remove_local_photo", side_effect=PermissionError("photo busy")), patch("builtins.print"):
            saved, _ = server.update_person_persisted(self.child["id"], {"name": "已保存"})
        self.assertEqual(server.read_workspace(), saved)
        self.assertEqual(server.read_workspace()["people"][self.parent["id"]]["photo_path"], old)
        self.assertTrue(server.local_photo_path(newest).exists())

    def test_http_history_contract_and_all_mutation_responses(self):
        class QuietHandler(server.FamilyHandler):
            def log_message(self, format, *args):
                pass

        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        def request(method, path, payload=None):
            connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
            body = json.dumps(payload).encode() if payload is not None else None
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            result = json.loads(response.read().decode())
            status = response.status
            connection.close()
            return status, result

        def mutate(method, path, payload=None, label=None):
            status, result = request(method, path, payload)
            self.assertIn(status, {200, 201})
            self.assertEqual(result["history"]["undo_label"], label)
            self.assertIn("redo_label", result["history"])
            self.assertNotIn(server.HISTORY_KEY, result["workspace"])
            return result

        try:
            status, history = request("GET", "/api/history")
            self.assertEqual((status, history), (200, {"undo_label": None, "redo_label": None}))
            status, error = request("POST", "/api/history/undo", {})
            self.assertEqual(status, 400)
            self.assertIn("error", error)
            person = mutate("POST", "/api/people", {"generation_id": self.lower["id"], "gender": "male", "name": "新人物"}, "添加人物")["person"]
            mutate("PATCH", f"/api/people/{person['id']}", {"name": "改名"}, "编辑人物")
            mutate("PATCH", f"/api/people/{person['id']}", {"generation_id": self.last["id"]}, "移动人物")
            mutate("POST", "/api/photos", {"person_id": person["id"], "filename": "photo.png", "data_url": "data:image/png;base64,aW1hZ2U="}, "更新照片")
            mutate("PATCH", f"/api/people/{person['id']}", {"photo_path": None}, "移除照片")
            relation = mutate("POST", "/api/relationships", {"source_id": self.child["id"], "target_id": person["id"]}, "建立关系")["relationship"]
            mutate("PATCH", f"/api/relationships/{relation['id']}", {"kind": "special", "parent_label": "养父", "child_label": "养子"}, "编辑关系")
            mutate("DELETE", f"/api/relationships/{relation['id']}", label="删除关系")
            mutate("PATCH", f"/api/generations/{self.lower['id']}/people-order", {"person_ids": [self.sibling["id"], self.child["id"]]}, "调整人物排序")
            generation = mutate("POST", "/api/generations", {"placement": "below", "anchor_id": self.last["id"], "name": "新一代"}, "添加代际")["generation"]
            mutate("PATCH", f"/api/generations/{generation['id']}", {"name": "后代"}, "编辑代际")
            mutate("DELETE", f"/api/generations/{generation['id']}", label="删除代际")
            deleted = mutate("DELETE", f"/api/people/{person['id']}", label="删除人物")["workspace"]
            status, undone = request("POST", "/api/history/undo", {})
            self.assertEqual(status, 200)
            self.assertIn(person["id"], undone["workspace"]["people"])
            self.assertEqual(undone["history"]["redo_label"], "删除人物")
            status, redone = request("POST", "/api/history/redo", {})
            self.assertEqual(status, 200)
            self.assertEqual(redone["workspace"], deleted)
            self.assertEqual(redone["history"]["undo_label"], "删除人物")
            self.assertIsNone(redone["history"]["redo_label"])
            status, workspace = request("GET", "/api/workspace")
            self.assertEqual(status, 200)
            self.assertNotIn(server.HISTORY_KEY, workspace)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
