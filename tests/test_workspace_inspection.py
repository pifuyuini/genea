import http.client
import json
import tempfile
import threading
import unittest
from copy import deepcopy
from unittest.mock import patch

import genealogy_core as core
import server
import workspace_inspection as inspection
from test_experimental_config import family_fixture


class WorkspaceInspectionTests(unittest.TestCase):
    def setUp(self):
        self.workspace, self.generations, self.parent, self.child, self.relationship = family_fixture()

    def codes(self, report):
        return {issue["code"] for issue in report["issues"]}

    def test_healthy_workspace_and_cross_generation_have_no_errors_or_avatar_notices(self):
        for workspace in (self.workspace, family_fixture(cross=True)[0]):
            for photo in (None, ""):
                for person in workspace["people"].values():
                    person["photo_path"] = photo
                before = deepcopy(workspace)
                report = inspection.inspect_workspace(workspace, photo_exists=lambda path: False)
                self.assertEqual(report, {"status": "ok", "summary": {"errors": 0, "notices": 0, "repairable": 0}, "issues": []})
                self.assertEqual(workspace, before)

    def test_multiple_parents_adoption_and_multiple_ancestry_are_accepted(self):
        workspace, generations, parent, child, _ = family_fixture(cross=True)
        father = core.add_person(workspace, {"generation_id": generations[0]["id"], "gender": "male", "name": "父亲", "introduction": "父亲"})
        adoptive = core.add_person(workspace, {"generation_id": generations[0]["id"], "gender": "female", "name": "养母", "introduction": "养母"})
        core.add_relationship(workspace, father["id"], child["id"], allow_cross_generation=True)
        adopted = core.add_relationship(workspace, adoptive["id"], child["id"], allow_cross_generation=True)
        core.update_relationship(workspace, adopted["id"], {"kind": "special", "parent_label": "养母", "child_label": "养子"})
        above = core.add_generation(workspace, "above", generations[0]["id"], allow_cross_generation=True)
        grand = core.add_person(workspace, {"generation_id": above["id"], "gender": "male", "name": "祖辈", "introduction": "祖辈"})
        core.add_relationship(workspace, grand["id"], parent["id"], allow_cross_generation=True)
        core.add_relationship(workspace, grand["id"], father["id"], allow_cross_generation=True)
        self.assertEqual(inspection.inspect_workspace(workspace)["summary"]["errors"], 0)

    def test_severe_top_level_structure_is_not_normalized_or_repairable(self):
        malformed = [[], {"schema_version": 1}, {"schema_version": 2, "generations": [], "relationships": []},
                     {"schema_version": 2, "generations": [], "people": [], "relationships": []}]
        for raw in malformed:
            before = deepcopy(raw)
            report = inspection.inspect_workspace(raw)
            self.assertEqual(report["status"], "unreadable")
            self.assertEqual(report["summary"]["repairable"], 0)
            self.assertEqual(raw, before)

    def test_nested_invalid_fields_are_reported_without_crashing_or_offering_repairs(self):
        cases = []
        wrong_person = deepcopy(self.workspace)
        wrong_person["people"][self.parent["id"]]["gender"] = []
        cases.append(wrong_person)
        wrong_id = deepcopy(self.workspace)
        wrong_id["people"][self.parent["id"]]["id"] = "different-id"
        cases.append(wrong_id)
        wrong_generation = deepcopy(self.workspace)
        wrong_generation["generations"][0]["position"] = "zero"
        cases.append(wrong_generation)
        wrong_relationship = deepcopy(self.workspace)
        wrong_relationship["relationships"][0]["kind"] = []
        cases.append(wrong_relationship)
        for workspace in cases:
            before = deepcopy(workspace)
            report = inspection.inspect_workspace(workspace)
            self.assertGreater(report["summary"]["errors"], 0)
            self.assertEqual(report["summary"]["repairable"], 0)
            self.assertEqual(workspace, before)

    def test_missing_person_and_generation_references_are_explicit_errors(self):
        workspace = deepcopy(self.workspace)
        workspace["relationships"][0]["child_id"] = "missing-person"
        workspace["people"][self.parent["id"]]["generation_id"] = "missing-generation"
        report = inspection.inspect_workspace(workspace)
        self.assertTrue({"missing_person", "missing_generation"} <= self.codes(report))
        self.assertTrue(all(issue["repair"] is None for issue in report["issues"]))

    def test_duplicate_ids_block_ambiguous_repairs_and_duplicate_edges_are_reported(self):
        duplicate = deepcopy(self.relationship)
        duplicate["id"] = "another-relationship"
        self.workspace["relationships"].append(duplicate)
        report = inspection.inspect_workspace(self.workspace)
        issue = next(item for item in report["issues"] if item["code"] == "duplicate_relationship")
        self.assertEqual(issue["relationship_ids"], [self.relationship["id"], "another-relationship"])
        duplicate["id"] = self.relationship["id"]
        duplicate["parent_label"] = "错误"
        report = inspection.inspect_workspace(self.workspace)
        self.assertIn("duplicate_relationship_id", self.codes(report))
        self.assertEqual(report["summary"]["repairable"], 0)
        self.workspace["generations"].append(deepcopy(self.generations[0]))
        self.assertIn("duplicate_generation_id", self.codes(inspection.inspect_workspace(self.workspace)))

    def test_self_same_generation_and_reversed_edges_are_not_automatically_changed(self):
        cases = []
        self_edge = deepcopy(self.workspace)
        self_edge["relationships"][0]["child_id"] = self.parent["id"]
        cases.append((self_edge, "self_relationship"))
        same = deepcopy(self.workspace)
        same["people"][self.child["id"]]["generation_id"] = self.parent["generation_id"]
        cases.append((same, "same_generation"))
        reversed_workspace = deepcopy(self.workspace)
        reversed_workspace["relationships"][0]["parent_id"], reversed_workspace["relationships"][0]["child_id"] = self.child["id"], self.parent["id"]
        cases.append((reversed_workspace, "reversed_generation"))
        for workspace, code in cases:
            before = deepcopy(workspace)
            report = inspection.inspect_workspace(workspace)
            issue = next(item for item in report["issues"] if item["code"] == code)
            self.assertIsNone(issue["repair"])
            self.assertEqual(workspace, before)

    def test_cycles_return_the_component_and_all_internal_edges(self):
        third = core.add_person(self.workspace, {"generation_id": self.generations[2]["id"], "gender": "female", "name": "第三人", "introduction": "简介"})
        ids = [self.parent["id"], self.child["id"], third["id"]]
        self.workspace["relationships"] = [
            {"id": f"cycle-{number}", "parent_id": ids[number], "child_id": ids[(number + 1) % 3],
             "kind": "special", "code": "special", "parent_label": "老师", "child_label": "学生", "color_key": "special"}
            for number in range(3)
        ]
        report = inspection.inspect_workspace(self.workspace)
        cycle = next(item for item in report["issues"] if item["code"] == "relationship_cycle")
        self.assertEqual(set(cycle["person_ids"]), set(ids))
        self.assertEqual(set(cycle["relationship_ids"]), {"cycle-0", "cycle-1", "cycle-2"})
        self.assertIsNone(cycle["repair"])

    def test_standard_repair_describes_exact_changes_and_preserves_endpoints(self):
        self.relationship["parent_label"] = "旧称谓"
        self.relationship["color_key"] = "old"
        before = deepcopy(self.workspace)
        report = inspection.inspect_workspace(self.workspace)
        issue = next(item for item in report["issues"] if item["code"] == "standard_fields")
        self.assertEqual(issue["repair"]["action"], "recompute_standard_relationship")
        self.assertIn("旧称谓", issue["repair"]["description"])
        self.assertIn("妈妈", issue["repair"]["description"])
        self.assertIn("连线颜色", issue["repair"]["description"])
        for key in ("parent_label", "child_label", "color_key", "photo_path", "code=", "null", "person_", "rel_"):
            self.assertNotIn(key, issue["repair"]["description"])
        self.assertEqual(self.workspace, before)
        repaired = deepcopy(self.workspace)
        inspection.apply_repair(repaired, issue)
        self.assertEqual((repaired["relationships"][0]["id"], repaired["relationships"][0]["parent_id"], repaired["relationships"][0]["child_id"]),
                         (self.relationship["id"], self.parent["id"], self.child["id"]))
        self.assertEqual(repaired["relationships"][0]["parent_label"], "妈妈")
        self.assertEqual(repaired["people"], before["people"])

    def test_missing_photo_only_clears_the_selected_reference_without_recomputing_labels(self):
        self.parent["photo_path"] = "/photos/missing.png"
        self.relationship["parent_label"] = "保留待修复的称谓"
        report = inspection.inspect_workspace(self.workspace, photo_exists=lambda path: False)
        issue = next(item for item in report["issues"] if item["code"] == "missing_photo")
        self.assertIn("默认头像", issue["repair"]["description"])
        before_relationships = deepcopy(self.workspace["relationships"])
        inspection.apply_repair(self.workspace, issue)
        self.assertIsNone(self.parent["photo_path"])
        self.assertEqual(self.workspace["relationships"], before_relationships)
        for invalid in ("/photos/missing.png", "outside.png", 42):
            self.parent["photo_path"] = invalid
            report = inspection.inspect_workspace(self.workspace, photo_exists=lambda path: path == "/photos/exists.png")
            self.assertIn("missing_photo", self.codes(report))
        self.parent["photo_path"] = "/photos/exists.png"
        self.assertNotIn("missing_photo", self.codes(inspection.inspect_workspace(self.workspace, photo_exists=lambda path: True)))

    def test_same_name_empty_intro_isolation_and_unrecognized_family_terms_are_notices(self):
        self.child["name"] = self.parent["name"]
        self.child["introduction"] = ""
        core.add_person(self.workspace, {"generation_id": self.generations[-1]["id"], "gender": "female", "name": "孤立人物", "introduction": "有意不登记关系"})
        core.update_relationship(self.workspace, self.relationship["id"], {"kind": "special", "parent_label": "养母", "child_label": "养女"})
        report = inspection.inspect_workspace(self.workspace)
        self.assertTrue({"same_name", "empty_introduction", "isolated_person", "unsupported_family_terms"} <= self.codes(report))
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertEqual(report["summary"]["repairable"], 0)
        self.assertTrue(all(issue["severity"] == "notice" for issue in report["issues"]))

    def test_registered_adoption_and_nonfamily_terms_do_not_receive_family_warnings(self):
        for labels in (("养母", "养子"), ("老师", "学生"), ("师父", "徒弟")):
            core.update_relationship(self.workspace, self.relationship["id"], {"kind": "special", "parent_label": labels[0], "child_label": labels[1]})
            self.assertNotIn("unsupported_family_terms", self.codes(inspection.inspect_workspace(self.workspace)))

    def test_broken_history_is_reported_and_blocks_current_automatic_repairs(self):
        self.relationship["parent_label"] = "旧称谓"
        self.workspace[server.HISTORY_KEY] = {"undo": [{"label": "坏快照", "workspace": {"schema_version": 2}}], "redo": []}
        before = deepcopy(self.workspace)
        report = inspection.inspect_workspace(self.workspace)
        self.assertIn("history_structure", self.codes(report))
        self.assertEqual(report["summary"]["repairable"], 0)
        self.assertEqual(self.workspace, before)

    def test_cross_generation_detection_scans_all_history_and_does_not_change_it(self):
        cross = family_fixture(cross=True)[0]
        self.assertTrue(inspection.contains_cross_generation(cross))
        self.assertFalse(inspection.contains_cross_generation(self.workspace))
        self.workspace[server.HISTORY_KEY] = {"undo": [{"label": "跨代", "workspace": cross}] + [{"label": "普通", "workspace": deepcopy(self.workspace)}] * 40, "redo": []}
        before = deepcopy(self.workspace)
        self.assertTrue(inspection.saved_cross_generation(self.workspace))
        self.assertEqual(self.workspace, before)
        cross["relationships"][0]["child_id"] = []
        self.assertFalse(inspection.contains_cross_generation(cross))


class WorkspaceInspectionApiTests(unittest.TestCase):
    def setUp(self):
        mode = patch.object(server, "EXPERIMENTAL_CROSS_GENERATION", True)
        mode.start()
        self.addCleanup(mode.stop)
        self.directory = tempfile.TemporaryDirectory()
        server.configure_data_dir(self.directory.name)
        self.workspace, self.generations, self.parent, self.child, self.relationship = family_fixture()
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
        result = json.loads(response.read().decode())
        status = response.status
        connection.close()
        return status, result

    def report_and_issue(self, code):
        status, report = self.request("GET", "/api/check")
        self.assertEqual(status, 200)
        issue = next(item for item in report["issues"] if item["code"] == code)
        return report, issue

    def test_check_uses_original_file_without_initializing_or_normalizing_damage(self):
        for original in (None, b"{", b"[]", b'{"schema_version": 2}'):
            if original is None:
                server.STATE_PATH.unlink(missing_ok=True)
            else:
                server.STATE_PATH.write_bytes(original)
            status, report = self.request("GET", "/api/check")
            self.assertEqual(status, 200)
            self.assertEqual(set(report), {"report_id", "status", "summary", "issues"})
            self.assertEqual(report["status"], "unreadable")
            self.assertEqual(report["summary"]["repairable"], 0)
            self.assertEqual(server.STATE_PATH.read_bytes() if server.STATE_PATH.exists() else None, original)
            self.assertFalse(server.SETTINGS_PATH.exists())
            self.assertFalse(server.PHOTOS_DIR.exists())

    def test_check_keeps_saved_bytes_history_and_photo_files_unchanged(self):
        self.relationship["parent_label"] = "旧称谓"
        self.workspace[server.HISTORY_KEY] = {"undo": [{"label": "已有历史", "workspace": deepcopy(self.workspace)}], "redo": []}
        original = self.store(self.workspace)
        server.PHOTOS_DIR.mkdir()
        (server.PHOTOS_DIR / "unreferenced.png").write_bytes(b"keep")
        report, issue = self.report_and_issue("standard_fields")
        self.assertEqual(report["summary"]["repairable"], 1)
        self.assertEqual(set(issue), {"id", "severity", "code", "message", "person_ids", "relationship_ids", "repair"})
        self.assertEqual(set(issue["repair"]), {"action", "label", "description"})
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertEqual((server.PHOTOS_DIR / "unreferenced.png").read_bytes(), b"keep")
        self.assertFalse(server.SETTINGS_PATH.exists())

    def test_standard_fix_is_one_undo_transaction_and_invalidates_old_reports(self):
        self.relationship["parent_label"] = "旧称谓"
        self.parent["photo_path"] = "/photos/missing.png"
        before = deepcopy(self.workspace)
        self.store(self.workspace)
        first, issue = self.report_and_issue("standard_fields")
        second, _ = self.report_and_issue("standard_fields")
        status, fixed = self.request("POST", "/api/check/fix", {"report_id": first["report_id"], "issue_id": issue["id"]})
        self.assertEqual(status, 200)
        self.assertTrue(fixed["config"]["experimental_features_enabled"])
        self.assertEqual(fixed["history"]["undo_label"], "修复标准称谓")
        self.assertEqual(fixed["workspace"]["relationships"][0]["parent_label"], "妈妈")
        self.assertEqual(fixed["workspace"]["people"], before["people"])
        raw = json.loads(server.STATE_PATH.read_bytes())
        self.assertEqual(len(raw[server.HISTORY_KEY]["undo"]), 1)
        self.assertEqual(raw[server.HISTORY_KEY]["undo"][0]["workspace"], before)
        written = server.STATE_PATH.read_bytes()
        status, error = self.request("POST", "/api/check/fix", {"report_id": second["report_id"], "issue_id": issue["id"]})
        self.assertEqual(status, 409)
        self.assertIn("刷新", error["error"])
        self.assertEqual(server.STATE_PATH.read_bytes(), written)
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored, before)
        redone, _ = server.navigate_history("redo")
        self.assertEqual(redone, fixed["workspace"])

    def test_photo_fix_does_not_repair_other_labels_or_delete_unknown_photos(self):
        self.parent["photo_path"] = "/photos/missing.png"
        self.relationship["parent_label"] = "仍待修复"
        self.store(self.workspace)
        server.PHOTOS_DIR.mkdir()
        (server.PHOTOS_DIR / "keep.png").write_bytes(b"keep")
        report, issue = self.report_and_issue("missing_photo")
        status, fixed = self.request("POST", "/api/check/fix", {"report_id": report["report_id"], "issue_id": issue["id"]})
        self.assertEqual(status, 200)
        self.assertIsNone(fixed["workspace"]["people"][self.parent["id"]]["photo_path"])
        self.assertEqual(fixed["workspace"]["relationships"], self.workspace["relationships"])
        self.assertEqual(fixed["history"]["undo_label"], "清除失效照片引用")
        self.assertEqual((server.PHOTOS_DIR / "keep.png").read_bytes(), b"keep")
        restored, _ = server.navigate_history("undo")
        self.assertEqual(restored["people"][self.parent["id"]]["photo_path"], "/photos/missing.png")

    def test_any_saved_byte_change_including_new_damage_makes_a_report_stale(self):
        self.relationship["parent_label"] = "旧称谓"
        original = self.store(self.workspace)
        for changed in (original + b" ", b"{"):
            self.store(self.workspace)
            report, issue = self.report_and_issue("standard_fields")
            server.STATE_PATH.write_bytes(changed)
            status, error = self.request("POST", "/api/check/fix", {"report_id": report["report_id"], "issue_id": issue["id"]})
            self.assertEqual(status, 409)
            self.assertIn("刷新", error["error"])
            self.assertEqual(server.STATE_PATH.read_bytes(), changed)

    def test_reappearing_photo_is_rechecked_before_clearing_its_reference(self):
        self.parent["photo_path"] = "/photos/restored.png"
        original = self.store(self.workspace)
        report, issue = self.report_and_issue("missing_photo")
        server.PHOTOS_DIR.mkdir()
        (server.PHOTOS_DIR / "restored.png").write_bytes(b"restored")
        status, result = self.request("POST", "/api/check/fix", {"report_id": report["report_id"], "issue_id": issue["id"]})
        self.assertEqual(status, 409)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertEqual((server.PHOTOS_DIR / "restored.png").read_bytes(), b"restored")

    def test_nonrepairable_and_structurally_damaged_reports_never_save(self):
        self.parent["introduction"] = ""
        original = self.store(self.workspace)
        report, issue = self.report_and_issue("empty_introduction")
        status, result = self.request("POST", "/api/check/fix", {"report_id": report["report_id"], "issue_id": issue["id"]})
        self.assertEqual(status, 400)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.relationship["parent_label"] = "旧称谓"
        self.workspace["generations"].append(deepcopy(self.generations[0]))
        original = self.store(self.workspace)
        report, issue = self.report_and_issue("standard_fields")
        self.assertIsNone(issue["repair"])
        self.assertEqual(self.request("POST", "/api/check/fix", {"report_id": report["report_id"], "issue_id": issue["id"]})[0], 400)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)

    def test_failed_persistence_leaves_content_history_and_report_available_for_retry(self):
        self.relationship["parent_label"] = "旧称谓"
        original = self.store(self.workspace)
        report, issue = self.report_and_issue("standard_fields")
        with patch.object(server, "write_workspace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                server.fix_workspace_issue(report["report_id"], issue["id"])
        self.assertEqual(server.STATE_PATH.read_bytes(), original)
        self.assertIn(report["report_id"], server.CHECK_REPORTS)
        fixed, _ = server.fix_workspace_issue(report["report_id"], issue["id"])
        self.assertEqual(fixed["relationships"][0]["parent_label"], "妈妈")
        self.assertEqual(len(server.read_state()[1]["undo"]), 1)

    def test_disabled_feature_blocks_checks_and_fixes_without_reading_or_writing_content(self):
        self.relationship["parent_label"] = "旧称谓"
        original = self.store(self.workspace)
        report, issue = self.report_and_issue("standard_fields")
        server.update_configuration(False)
        with patch.object(server, "check_workspace", wraps=server.check_workspace), patch.object(inspection, "inspect_workspace", side_effect=AssertionError("Inspection must not run.")):
            self.assertEqual(self.request("GET", "/api/check")[0], 403)
            self.assertEqual(self.request("POST", "/api/check/fix", {"report_id": report["report_id"], "issue_id": issue["id"]})[0], 403)
        self.assertEqual(server.STATE_PATH.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
