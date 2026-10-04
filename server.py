from __future__ import annotations
import argparse, base64, binascii, json, mimetypes, re, threading, uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from copy import deepcopy
from urllib.parse import parse_qs, unquote, urlparse
import genealogy_core as core
import workspace_inspection as inspection

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DEFAULT_DATA_DIR = ROOT / "data"
DATA_DIR = DEFAULT_DATA_DIR; PHOTOS_DIR = DATA_DIR / "photos"; STATE_PATH = DATA_DIR / "workspace.json"; SETTINGS_PATH = DATA_DIR / "settings.json"
STATE_LOCK = threading.RLock()
HISTORY_KEY = "_history"
HISTORY_LIMIT = 30
EXPERIMENTAL_CROSS_GENERATION = False
CHECK_REPORTS = {}
PHOTO_MIME_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}

class StateLoadError(RuntimeError): pass
class ReadOnlyError(RuntimeError): pass
class FeatureDisabledError(RuntimeError): pass
class InspectionConflictError(core.ConflictError): pass

def configure_data_dir(data_dir: Path | str) -> None:
    global DATA_DIR, PHOTOS_DIR, STATE_PATH, SETTINGS_PATH
    DATA_DIR = Path(data_dir); PHOTOS_DIR = DATA_DIR / "photos"; STATE_PATH = DATA_DIR / "workspace.json"; SETTINGS_PATH = DATA_DIR / "settings.json"
    CHECK_REPORTS.clear()

def configure_experimental_cross_generation(enabled: bool) -> None:
    """Set the legacy CLI default; saved per-family preferences take priority."""
    global EXPERIMENTAL_CROSS_GENERATION
    EXPERIMENTAL_CROSS_GENERATION = bool(enabled)

def read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {"experimental_features_enabled": EXPERIMENTAL_CROSS_GENERATION}
    try: settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateLoadError("家谱设置无法读取；没有改写设置或家谱。") from exc
    if not isinstance(settings, dict) or type(settings.get("experimental_features_enabled")) is not bool:
        raise StateLoadError("家谱 settings.json 的实验开关必须是布尔值。")
    return settings

def experimental_features_enabled() -> bool:
    return read_settings()["experimental_features_enabled"]

def read_raw_document(*, missing_ok: bool = False):
    try: original = STATE_PATH.read_bytes()
    except FileNotFoundError:
        if missing_ok: return None, None
        raise StateLoadError("工作区文件不存在；没有初始化任何数据。")
    except OSError as exc: raise StateLoadError("Workspace is unreadable.") from exc
    try: raw = json.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise StateLoadError("Workspace is unreadable.") from exc
    return original, raw

def read_only_status(enabled: bool | None = None) -> tuple[bool, str | None]:
    if enabled is None: enabled = experimental_features_enabled()
    try: _, raw = read_raw_document(missing_ok=True)
    except StateLoadError:
        return True, "家谱数据无法正常读取；请运行检查或人工修复原文件。"
    if not enabled and inspection.saved_cross_generation(raw):
        return True, "当前家谱或撤销、重做历史含跨代关系；关闭实验功能时整个家谱只读。重新开启后可继续编辑。"
    return False, None

def configuration_status() -> dict:
    with STATE_LOCK:
        enabled = experimental_features_enabled()
        read_only, reason = read_only_status(enabled)
        return {"experimental_features_enabled": enabled, "experimental_cross_generation": enabled,
                "read_only": read_only, "read_only_reason": reason}

def update_configuration(enabled) -> dict:
    if type(enabled) is not bool: raise core.ValidationError("experimental_features_enabled 必须是布尔值。")
    with STATE_LOCK:
        settings = read_settings()
        if not SETTINGS_PATH.exists() or settings["experimental_features_enabled"] != enabled:
            settings["experimental_features_enabled"] = enabled
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temporary = SETTINGS_PATH.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(SETTINGS_PATH)
        return configuration_status()

def require_experimental_features() -> None:
    if not experimental_features_enabled():
        raise FeatureDisabledError("请先开启实验功能。")

def require_writable() -> None:
    read_only, reason = read_only_status()
    if read_only: raise ReadOnlyError(reason)

def check_workspace() -> dict:
    with STATE_LOCK:
        require_experimental_features()
        try:
            original = STATE_PATH.read_bytes()
        except FileNotFoundError:
            original = None
            report = inspection.unreadable_report("workspace_missing", "工作区文件不存在；检查没有初始化数据，也不能自动修复。")
        except OSError:
            original = None
            report = inspection.unreadable_report("workspace_unreadable", "无法读取工作区文件；检查不会改写数据。")
        else:
            try: raw = json.loads(original.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                report = inspection.unreadable_report("workspace_unreadable", "工作区不是有效的 UTF-8 JSON；不能自动修复。")
            else: report = inspection.inspect_workspace(raw, photo_exists=photo_reference_exists)
        report["report_id"] = str(uuid.uuid4())
        CHECK_REPORTS[report["report_id"]] = {"path": STATE_PATH, "original": original, "report": deepcopy(report)}
        return report

def fix_workspace_issue(report_id, issue_id) -> tuple[dict, object]:
    if not isinstance(report_id, str) or not isinstance(issue_id, str):
        raise core.ValidationError("report_id 和 issue_id 必须是字符串。")
    with STATE_LOCK:
        require_experimental_features()
        saved = CHECK_REPORTS.get(report_id)
        if saved is None or saved["path"] != STATE_PATH:
            raise InspectionConflictError("检查报告已过期，请刷新检查结果。")
        try: original = STATE_PATH.read_bytes()
        except OSError as exc: raise InspectionConflictError("家谱已变化或无法读取，请刷新检查结果后再修复。") from exc
        if original != saved["original"]:
            raise InspectionConflictError("家谱已变化，请刷新检查结果后再修复。")
        require_writable()
        _, raw = read_raw_document()
        previous = next((issue for issue in saved["report"]["issues"] if issue["id"] == issue_id), None)
        if previous is None or previous["repair"] is None:
            raise core.ValidationError("该检查问题不支持自动修复。")
        current = inspection.inspect_workspace(raw, photo_exists=photo_reference_exists)
        issue = next((issue for issue in current["issues"] if issue["id"] == issue_id), None)
        if issue is None or issue["repair"] != previous["repair"]:
            raise InspectionConflictError("问题已变化，请刷新检查结果后再修复。")
        result = mutate(lambda workspace: inspection.apply_repair(workspace, issue), issue["repair"]["label"])
        CHECK_REPORTS.clear()
        return result

def read_state() -> tuple[dict, dict]:
    with STATE_LOCK:
        if not STATE_PATH.exists(): write_workspace(core.default_workspace())
        _, raw = read_raw_document()
        if not isinstance(raw, dict): raise StateLoadError("Workspace must be an object.")
        try:
            workspace = core.ensure_workspace(raw)
            history = raw.get(HISTORY_KEY, {"undo": [], "redo": []})
            if not isinstance(history, dict): raise core.ValidationError("Invalid history.")
            normalized = {"undo": [], "redo": []}
            for direction in normalized:
                entries = history.get(direction, [])
                if not isinstance(entries, list): raise core.ValidationError("Invalid history.")
                for entry in entries:
                    if not isinstance(entry, dict) or not isinstance(entry.get("label"), str):
                        raise core.ValidationError("Invalid history entry.")
                    snapshot = entry.get("workspace")
                    if not isinstance(snapshot, dict): raise core.ValidationError("Invalid history snapshot.")
                    snapshot = core.ensure_workspace(snapshot)
                    normalized[direction].append({"label": entry["label"], "workspace": snapshot})
                normalized[direction] = normalized[direction][-HISTORY_LIMIT:]
            return workspace, normalized
        except core.ValidationError as exc: raise StateLoadError("Workspace schema is invalid.") from exc

def read_workspace() -> dict:
    return read_state()[0]

def history_status(history: dict | None = None) -> dict:
    if history is None: _, history = read_state()
    return {
        "undo_label": history["undo"][-1]["label"] if history["undo"] else None,
        "redo_label": history["redo"][-1]["label"] if history["redo"] else None,
    }

def write_workspace(workspace: dict, history: dict | None = None) -> None:
    require_writable()
    normalized = core.ensure_workspace(workspace)
    if history is not None: normalized[HISTORY_KEY] = history
    if not experimental_features_enabled() and inspection.saved_cross_generation(normalized):
        raise ReadOnlyError("跨代家谱只能在实验功能开启时写入；没有保存任何内容。")
    DATA_DIR.mkdir(parents=True, exist_ok=True); PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); temporary.replace(STATE_PATH)

def referenced_photos(workspace: dict, history: dict) -> set[str]:
    snapshots = [workspace, *(entry["workspace"] for entries in history.values() for entry in entries)]
    return {
        person["photo_path"]
        for snapshot in snapshots for person in snapshot["people"].values()
        if local_photo_path(person.get("photo_path")) is not None
    }

def persist_state(workspace: dict, history: dict, previous_photos: set[str]) -> None:
    write_workspace(workspace, history)
    for photo in previous_photos - referenced_photos(workspace, history):
        try:
            remove_local_photo(photo)
        except OSError as exc:
            # State is already committed; cleanup failure must not invalidate it.
            print(f"Photo cleanup deferred for {photo}: {exc}")

def restore_unchanged_timestamps(before: dict, after: dict) -> None:
    # Core operations update timestamps even when a form is saved without changes.
    for old_items, new_items in (
        (before["people"], after["people"]),
        ({item["id"]: item for item in before["relationships"]}, {item["id"]: item for item in after["relationships"]}),
    ):
        for item_id, item in new_items.items():
            previous = old_items.get(item_id)
            if previous is not None and {k: v for k, v in item.items() if k != "updated_at"} == {k: v for k, v in previous.items() if k != "updated_at"}:
                if "updated_at" in previous: item["updated_at"] = previous["updated_at"]
                else: item.pop("updated_at", None)

def mutate(action, label="编辑家谱"):
    with STATE_LOCK:
        require_writable()
        workspace, history = read_state()
        before = deepcopy(workspace)
        previous_photos = referenced_photos(workspace, history)
        result = action(workspace)
        restore_unchanged_timestamps(before, workspace)
        if workspace != before:
            history["undo"] = [*history["undo"], {"label": label, "workspace": before}][-HISTORY_LIMIT:]
            history["redo"] = []
            persist_state(workspace, history, previous_photos)
        return workspace, result

def navigate_history(direction: str) -> tuple[dict, dict]:
    if direction not in {"undo", "redo"}: raise core.ValidationError("Invalid history direction.")
    with STATE_LOCK:
        require_writable()
        workspace, history = read_state()
        if not history[direction]: raise core.ConflictError("没有可撤销的操作。" if direction == "undo" else "没有可重做的操作。")
        previous_photos = referenced_photos(workspace, history)
        entry = history[direction].pop()
        opposite = "redo" if direction == "undo" else "undo"
        history[opposite] = [*history[opposite], {"label": entry["label"], "workspace": workspace}][-HISTORY_LIMIT:]
        restored = entry["workspace"]
        persist_state(restored, history, previous_photos)
        return restored, history_status(history)

def local_photo_path(public_path) -> Path | None:
    if not isinstance(public_path, str) or not public_path.startswith("/photos/"):
        return None
    name = public_path.removeprefix("/photos/")
    if not name or Path(name).name != name:
        return None
    candidate = (PHOTOS_DIR / name).resolve()
    return candidate if candidate.parent == PHOTOS_DIR.resolve() else None

def photo_reference_exists(public_path) -> bool:
    photo = local_photo_path(public_path)
    return photo is not None and photo.is_file()

def remove_local_photo(public_path) -> None:
    photo = local_photo_path(public_path)
    if photo is not None:
        photo.unlink(missing_ok=True)

def resolve_static_path(request_path: str) -> Path | None:
    root = STATIC_DIR.resolve()
    candidate = (root / "index.html") if request_path in {"", "/"} else (root / Path(unquote(request_path.lstrip("/")))).resolve()
    return candidate if candidate.is_relative_to(root) else None

def update_person_persisted(person_id: str, payload: dict) -> tuple[dict, tuple[dict, list[str]]]:
    with STATE_LOCK:
        previous = read_workspace()["people"].get(person_id, {})
        if "generation_id" in payload and payload["generation_id"] != previous.get("generation_id"):
            label = "移动人物"
        elif "photo_path" in payload and payload["photo_path"] is None and previous.get("photo_path"):
            label = "移除照片"
        else:
            label = "编辑人物"
        return mutate(lambda workspace: core.update_person(workspace, person_id, payload, allow_cross_generation=experimental_features_enabled()), label)

def delete_person_persisted(person_id: str) -> tuple[dict, list[str]]:
    return mutate(lambda workspace: core.delete_person(workspace, person_id), "删除人物")

def save_photo(person_id: str, image: bytes, extension: str) -> tuple[dict, str]:
    with STATE_LOCK:
        require_writable()
        workspace = read_workspace()
        if person_id not in workspace["people"]:
            raise core.NotFoundError("Person not found.")
        old_photo = local_photo_path(workspace["people"][person_id].get("photo_path"))
        if old_photo is not None and old_photo.is_file() and old_photo.read_bytes() == image:
            return workspace, workspace["people"][person_id]["photo_path"]
        name = core.new_id("photo") + extension
        public = "/photos/" + name
        new_photo = PHOTOS_DIR / name
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        new_photo.write_bytes(image)
        try:
            workspace, _ = mutate(
                lambda current: core.update_person(current, person_id, {"photo_path": public}, allow_cross_generation=experimental_features_enabled()),
                "更新照片",
            )
        except Exception:
            new_photo.unlink(missing_ok=True)
            raise
        return workspace, public

def safe_photo_extension(filename, mime_type):
    if mime_type in PHOTO_MIME_EXTENSIONS: return PHOTO_MIME_EXTENSIONS[mime_type]
    suffix = Path(filename or "").suffix.lower()
    return ".jpg" if suffix == ".jpeg" else suffix if suffix in {".jpg", ".png", ".gif", ".webp"} else ".png"

def decode_photo_data(data_url):
    match = re.match(r"^data:(image/[a-zA-Z0-9.+-]+);base64,(.+)$", data_url)
    return base64.b64decode(match.group(2) if match else data_url, validate=True), match.group(1) if match else None

class FamilyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): print(f"{self.address_string()} - {format % args}")
    def handle_one_request(self):
        try: super().handle_one_request()
        except StateLoadError as exc: self.send_json({"error": str(exc) + " No changes were made."}, HTTPStatus.SERVICE_UNAVAILABLE)
        except (ReadOnlyError, FeatureDisabledError) as exc: self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except InspectionConflictError as exc: self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except core.NotFoundError as exc: self.send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
        except (core.ValidationError, core.ConflictError) as exc: self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise core.ValidationError("Invalid JSON body.") from exc
        if not isinstance(payload, dict):
            raise core.ValidationError("JSON body must be an object.")
        return payload
    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode(); self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config": return self.send_json(configuration_status())
        if parsed.path == "/api/check": return self.send_json(check_workspace())
        if parsed.path == "/api/workspace": return self.send_json(read_workspace())
        if parsed.path == "/api/history": return self.send_json(history_status())
        if parsed.path == "/api/path":
            query = parse_qs(parsed.query)
            query_function = core.relationship_query if experimental_features_enabled() else core.relationship_path
            return self.send_json(query_function(read_workspace(), query.get("from", [""])[0], query.get("to", [""])[0]))
        if parsed.path.startswith("/photos/"): return self.serve_photo(parsed.path)
        self.serve_static(parsed.path)
    def do_POST(self): self.dispatch_write("POST")
    def do_PATCH(self): self.dispatch_write("PATCH")
    def do_DELETE(self): self.dispatch_write("DELETE")
    def dispatch_write(self, method):
        # Keep each mutation's workspace and history status from the same revision.
        with STATE_LOCK:
            self.dispatch_write_locked(method)

    def dispatch_write_locked(self, method):
        path = urlparse(self.path).path; payload = self.body() if method != "DELETE" else {}
        if method == "POST" and path == "/api/config":
            return self.send_json(update_configuration(payload.get("experimental_features_enabled")))
        if method == "POST" and path == "/api/query":
            require_experimental_features()
            from relationship_query import run_query
            return self.send_json(run_query(read_workspace(), payload.get("text"), payload.get("resolutions")))
        if method == "POST" and path == "/api/check/fix":
            workspace, _ = fix_workspace_issue(payload.get("report_id"), payload.get("issue_id"))
            return self.send_json({"workspace": workspace, "history": history_status(), "config": configuration_status()})
        if method == "POST" and path in {"/api/history/undo", "/api/history/redo"}:
            workspace, history = navigate_history(path.rsplit("/", 1)[1])
            return self.send_json({"workspace": workspace, "history": history, "config": configuration_status()})
        result_key = None
        if method == "POST" and path == "/api/generations": result_key = "generation"; workspace, result = mutate(lambda w: core.add_generation(w, payload.get("placement"), payload.get("anchor_id"), payload.get("name"), allow_cross_generation=experimental_features_enabled()), "添加代际")
        elif method == "POST" and path == "/api/people": result_key = "person"; workspace, result = mutate(lambda w: core.add_person(w, payload), "添加人物")
        elif method == "POST" and path == "/api/relationships": result_key = "relationship"; workspace, result = mutate(lambda w: core.add_relationship(w, payload.get("source_id"), payload.get("target_id"), allow_cross_generation=experimental_features_enabled()), "建立关系")
        elif method == "POST" and path == "/api/photos": return self.photo(payload)
        elif method == "PATCH" and (order_match := re.fullmatch(r"/api/generations/([^/]+)/people-order", path)):
            generation_id = unquote(order_match.group(1))
            workspace, result = mutate(
                lambda w: core.reorder_generation_people(w, generation_id, payload.get("person_ids")),
                "调整人物排序",
            )
        else:
            match = re.fullmatch(r"/api/(generations|people|relationships)/([^/]+)", path)
            if not match: return self.send_json({"error": "Unknown endpoint."}, HTTPStatus.NOT_FOUND)
            resource, item_id = match.group(1), unquote(match.group(2))
            if resource == "generations" and method == "PATCH": result_key = "generation"; workspace, result = mutate(lambda w: core.update_generation(w, item_id, payload), "编辑代际")
            elif resource == "generations" and method == "DELETE": workspace, result = mutate(lambda w: core.delete_generation(w, item_id), "删除代际")
            elif resource == "people" and method == "PATCH": workspace, result = update_person_persisted(item_id, payload)
            elif resource == "people" and method == "DELETE": workspace, result = delete_person_persisted(item_id)
            elif resource == "relationships" and method == "PATCH": result_key = "relationship"; workspace, result = mutate(lambda w: core.update_relationship(w, item_id, payload), "编辑关系")
            elif resource == "relationships" and method == "DELETE": workspace, result = mutate(lambda w: core.delete_relationship(w, item_id), "删除关系")
            else: return self.send_json({"error": "Method not allowed."}, HTTPStatus.METHOD_NOT_ALLOWED)
        response = {"workspace": workspace, "history": history_status(), "config": configuration_status()}
        if isinstance(result, tuple): response.update({"person": result[0], "removed_relationship_ids": result[1]})
        elif isinstance(result, dict): response[result_key or "item"] = result
        elif isinstance(result, list): response["removed_relationship_ids"] = result
        self.send_json(response, HTTPStatus.CREATED if method == "POST" else HTTPStatus.OK)
    def photo(self, payload):
        try: image, mime = decode_photo_data(str(payload.get("data_url") or ""))
        except (ValueError, binascii.Error): return self.send_json({"error": "Invalid image data."}, HTTPStatus.BAD_REQUEST)
        if len(image) > 8 * 1024 * 1024: return self.send_json({"error": "Image is larger than 8 MB."}, HTTPStatus.BAD_REQUEST)
        person_id = payload.get("person_id")
        workspace, public = save_photo(person_id, image, safe_photo_extension(payload.get("filename"), mime)); self.send_json({"photo_path": public, "workspace": workspace, "history": history_status(), "config": configuration_status()}, HTTPStatus.CREATED)
    def serve_photo(self, path):
        file_path = PHOTOS_DIR / Path(unquote(path.removeprefix("/photos/"))).name
        if not file_path.is_file(): return self.send_error(HTTPStatus.NOT_FOUND)
        content = file_path.read_bytes(); self.send_response(HTTPStatus.OK); self.send_header("Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"); self.send_header("Content-Length", str(len(content))); self.end_headers(); self.wfile.write(content)
    def serve_static(self, path):
        file_path = resolve_static_path(path)
        if file_path is None or not file_path.is_file(): return self.send_error(HTTPStatus.NOT_FOUND)
        content = file_path.read_bytes(); self.send_response(HTTPStatus.OK); self.send_header("Content-Type", mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"); self.send_header("Content-Length", str(len(content))); self.end_headers(); self.wfile.write(content)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--host", default="127.0.0.1"); parser.add_argument("--port", type=int, default=8765); parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--experimental-cross-generation", action="store_true", help="Default experimental features to enabled when this family has no saved settings.")
    args = parser.parse_args()
    configure_experimental_cross_generation(args.experimental_cross_generation)
    configure_data_dir(args.data_dir)
    if not STATE_PATH.exists():
        try: read_workspace()
        except StateLoadError as exc: parser.exit(2, str(exc) + "\n")
    server = ThreadingHTTPServer((args.host, args.port), FamilyHandler)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()

if __name__ == "__main__": main()
