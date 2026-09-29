import http.client, json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
import server
import genealogy_core as core

class StorageTests(unittest.TestCase):
    def tearDown(self): server.configure_data_dir(server.DEFAULT_DATA_DIR)
    def test_blank_custom_workspace_and_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            server.configure_data_dir(directory); self.assertEqual(server.read_workspace(), core.default_workspace()); self.assertEqual(server.STATE_PATH.name, "workspace.json")
            workspace = core.default_workspace(); core.add_generation(workspace, "first"); server.write_workspace(workspace); self.assertEqual(server.read_workspace(), workspace)
    def test_corruption_fails_closed(self):
        for original in (b"{", b"[]"):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as directory:
                server.configure_data_dir(directory); Path(directory, "workspace.json").write_bytes(original)
                with self.assertRaises(server.StateLoadError): server.read_workspace()
                self.assertEqual(Path(directory, "workspace.json").read_bytes(), original)
    def test_static_path_uses_real_parent_relationship(self):
        original = server.STATIC_DIR
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory, "static"); root.mkdir(); sibling = Path(directory, "static-evil"); sibling.mkdir()
            server.STATIC_DIR = root
            self.assertEqual(server.resolve_static_path("/asset.js"), (root / "asset.js").resolve())
            self.assertIsNone(server.resolve_static_path("/../static-evil/asset.js"))
        server.STATIC_DIR = original
    def test_photo_replacement_and_person_delete_retain_undoable_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            server.configure_data_dir(directory); workspace = core.default_workspace(); generation = core.add_generation(workspace, "first"); person = core.add_person(workspace, {"generation_id": generation["id"], "gender": "male", "name": "我"}); server.write_workspace(workspace)
            workspace, first = server.save_photo(person["id"], b"first", ".png"); first_file = server.local_photo_path(first); self.assertTrue(first_file.is_file())
            workspace, second = server.save_photo(person["id"], b"second", ".png"); self.assertTrue(first_file.exists()); self.assertTrue(server.local_photo_path(second).is_file())
            _, removed = server.delete_person_persisted(person["id"]); self.assertEqual(removed, []); self.assertTrue(server.local_photo_path(second).is_file())
            other = core.add_person(workspace, {"generation_id": generation["id"], "gender": "female", "name": "其他"}); outside = Path(directory) / "unknown-photo"; outside.write_bytes(b"keep"); other["photo_path"] = str(outside); server.write_workspace(workspace)
            server.delete_person_persisted(other["id"]); self.assertTrue(outside.is_file()); outside.unlink()
    def test_person_photo_removal_persists_and_keeps_photos_for_undo(self):
        with tempfile.TemporaryDirectory() as directory:
            server.configure_data_dir(directory)
            workspace = core.default_workspace()
            generation = core.add_generation(workspace, "first")
            person = core.add_person(workspace, {"generation_id": generation["id"], "gender": "male", "name": "我"})
            other = core.add_person(workspace, {"generation_id": generation["id"], "gender": "female", "name": "其他"})
            server.write_workspace(workspace)
            _, photo = server.save_photo(person["id"], b"portrait", ".png")
            _, other_photo = server.save_photo(other["id"], b"other", ".png")

            workspace, (updated, removed) = server.update_person_persisted(person["id"], {"name": "新名字"})
            self.assertEqual(updated["name"], "新名字")
            self.assertEqual(updated["photo_path"], photo)
            self.assertEqual(removed, [])
            self.assertTrue(server.local_photo_path(photo).is_file())
            self.assertEqual(server.read_workspace(), workspace)

            workspace, (updated, removed) = server.update_person_persisted(person["id"], {"photo_path": None})
            self.assertIsNone(updated["photo_path"])
            self.assertEqual(removed, [])
            self.assertTrue(server.local_photo_path(photo).exists())
            self.assertEqual(server.local_photo_path(other_photo).read_bytes(), b"other")
            self.assertEqual(server.read_workspace(), workspace)
            self.assertIsNone(server.read_workspace()["people"][person["id"]]["photo_path"])

    def test_failed_person_photo_removal_preserves_the_saved_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            server.configure_data_dir(directory)
            workspace = core.default_workspace()
            generation = core.add_generation(workspace, "first")
            person = core.add_person(workspace, {"generation_id": generation["id"], "gender": "male", "name": "我"})
            server.write_workspace(workspace)
            workspace, photo = server.save_photo(person["id"], b"portrait", ".png")
            with patch.object(server, "write_workspace", side_effect=OSError("cannot persist")):
                with self.assertRaises(OSError):
                    server.update_person_persisted(person["id"], {"photo_path": None})
            self.assertEqual(server.read_workspace(), workspace)
            self.assertEqual(server.local_photo_path(photo).read_bytes(), b"portrait")

    def test_reorder_generation_people_persists_after_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            server.configure_data_dir(directory)
            workspace = core.default_workspace()
            generation = core.add_generation(workspace, "first")
            first = core.add_person(workspace, {"generation_id": generation["id"], "gender": "male", "name": "a"})
            second = core.add_person(workspace, {"generation_id": generation["id"], "gender": "female", "name": "b"})
            server.write_workspace(workspace)
            saved, _ = server.mutate(
                lambda current: core.reorder_generation_people(
                    current,
                    generation["id"],
                    [second["id"], first["id"]],
                )
            )
            refreshed = server.read_workspace()
            self.assertEqual(saved, refreshed)
            self.assertEqual(
                [refreshed["people"][person_id]["order"] for person_id in [second["id"], first["id"]]],
                [0, 1],
            )
    def test_people_order_http_contract_and_request_body_errors(self):
        class QuietHandler(server.FamilyHandler):
            def log_message(self, format, *args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            server.configure_data_dir(directory)
            workspace = core.default_workspace()
            generation = core.add_generation(workspace, "first")
            first = core.add_person(workspace, {"generation_id": generation["id"], "gender": "male", "name": "a"})
            second = core.add_person(workspace, {"generation_id": generation["id"], "gender": "female", "name": "b"})
            server.write_workspace(workspace)

            httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()

            def request(method, path, raw_body=None):
                connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=3)
                headers = {}
                if raw_body is not None:
                    if isinstance(raw_body, str):
                        raw_body = raw_body.encode("utf-8")
                    headers["Content-Type"] = "application/json"
                connection.request(method, path, body=raw_body, headers=headers)
                response = connection.getresponse()
                response_body = json.loads(response.read().decode("utf-8"))
                status = response.status
                connection.close()
                return status, response_body

            try:
                endpoint = f"/api/generations/{generation['id']}/people-order"
                status, payload = request(
                    "PATCH",
                    endpoint,
                    json.dumps({"person_ids": [second["id"], first["id"]]}),
                )
                self.assertEqual(status, 200)
                self.assertEqual(
                    [payload["workspace"]["people"][person_id]["order"] for person_id in [second["id"], first["id"]]],
                    [0, 1],
                )
                self.assertEqual(server.read_workspace(), payload["workspace"])

                status, photo_payload = request(
                    "POST",
                    "/api/photos",
                    json.dumps({
                        "person_id": first["id"],
                        "filename": "photo.png",
                        "data_url": "data:image/png;base64,aW1hZ2U=",
                    }),
                )
                self.assertEqual(status, 201)
                self.assertTrue(photo_payload["photo_path"].startswith("/photos/"))

                status, updated_payload = request(
                    "PATCH",
                    f"/api/people/{first['id']}",
                    json.dumps({"photo_path": None}),
                )
                self.assertEqual(status, 200)
                self.assertIsNone(updated_payload["person"]["photo_path"])
                self.assertEqual(updated_payload["removed_relationship_ids"], [])
                self.assertEqual(server.read_workspace(), updated_payload["workspace"])
                self.assertTrue(server.local_photo_path(photo_payload["photo_path"]).exists())

                unchanged = server.STATE_PATH.read_bytes()
                failures = (
                    (endpoint, json.dumps({"person_ids": [first["id"]]}), 400),
                    (endpoint, json.dumps({"person_ids": [first["id"], first["id"]]}), 400),
                    (endpoint, json.dumps({"person_ids": [first["id"], "missing-person"]}), 400),
                    ("/api/generations/missing-generation/people-order", json.dumps({"person_ids": []}), 404),
                    (endpoint, "[]", 400),
                    (endpoint, "null", 400),
                    (endpoint, '"value"', 400),
                    (endpoint, "{", 400),
                )
                for path, raw_body, expected_status in failures:
                    with self.subTest(path=path, raw_body=raw_body):
                        status, error = request("PATCH", path, raw_body)
                        self.assertEqual(status, expected_status)
                        self.assertIsInstance(error.get("error"), str)
                        self.assertEqual(server.STATE_PATH.read_bytes(), unchanged)

                status, alive = request("GET", "/api/workspace")
                self.assertEqual(status, 200)
                self.assertEqual(alive, server.read_workspace())
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=3)



if __name__ == "__main__": unittest.main()
