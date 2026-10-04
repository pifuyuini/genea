"""Read-only inspection of the saved v2 document, with two explicit repairs."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

import genealogy_core as core
from kinship_appellation import is_family_relationship


_FAMILY_PARENT_WORDS = {"父", "父亲", "爸爸", "母", "母亲", "妈妈", "生父", "生母", "干爹", "干娘", "干爸", "干妈"}
_FAMILY_CHILD_WORDS = {"子", "儿子", "女", "女儿", "孩子", "干儿子", "干女儿"}
for _prefix in ("养", "继", "义", "嫡", "庶"):
    _FAMILY_PARENT_WORDS.update({_prefix + "父", _prefix + "母"})
    _FAMILY_CHILD_WORDS.update({_prefix + "子", _prefix + "女"})


def _summary(issues: list[dict]) -> dict:
    return {
        "errors": sum(issue["severity"] == "error" for issue in issues),
        "notices": sum(issue["severity"] == "notice" for issue in issues),
        "repairable": sum(issue["repair"] is not None for issue in issues),
    }


def unreadable_report(code: str, message: str) -> dict:
    issues = [{"id": code, "severity": "error", "code": code, "message": message,
               "person_ids": [], "relationship_ids": [], "repair": None}]
    return {"status": "unreadable", "summary": _summary(issues), "issues": issues}


def _document_shape(raw) -> bool:
    return (isinstance(raw, dict) and raw.get("schema_version") == 2
            and isinstance(raw.get("generations"), list)
            and isinstance(raw.get("people"), dict)
            and isinstance(raw.get("relationships"), list))


def _history_shape(raw) -> bool:
    history = raw.get("_history", {"undo": [], "redo": []})
    if not isinstance(history, dict):
        return False
    for direction in ("undo", "redo"):
        entries = history.get(direction, [])
        if not isinstance(entries, list):
            return False
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("label"), str):
                return False
            snapshot = entry.get("workspace")
            if not _document_shape(snapshot):
                return False
            if any(not isinstance(person, dict) for person in snapshot["people"].values()):
                return False
            if any(not isinstance(item, dict) or not isinstance(item.get("id"), str)
                   for item in snapshot["relationships"]):
                return False
    return True


def contains_cross_generation(raw) -> bool:
    """Recognize resolvable non-adjacent edges without changing malformed data."""
    if not isinstance(raw, dict):
        return False
    generations, people, relationships = raw.get("generations"), raw.get("people"), raw.get("relationships")
    if not isinstance(generations, list) or not isinstance(people, dict) or not isinstance(relationships, list):
        return False
    positions = {item["id"]: item["position"] for item in generations
                 if isinstance(item, dict) and isinstance(item.get("id"), str)
                 and type(item.get("position")) is int}
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        parent_id, child_id = relationship.get("parent_id"), relationship.get("child_id")
        if not isinstance(parent_id, str) or not isinstance(child_id, str):
            continue
        parent, child = people.get(parent_id), people.get(child_id)
        if not isinstance(parent, dict) or not isinstance(child, dict):
            continue
        parent_generation, child_generation = parent.get("generation_id"), child.get("generation_id")
        if not isinstance(parent_generation, str) or not isinstance(child_generation, str):
            continue
        a, b = positions.get(parent_generation), positions.get(child_generation)
        if a is not None and b is not None and abs(a - b) > 1:
            return True
    return False


def saved_cross_generation(raw) -> bool:
    if contains_cross_generation(raw):
        return True
    if not isinstance(raw, dict) or not isinstance(raw.get("_history"), dict):
        return False
    for direction in ("undo", "redo"):
        entries = raw["_history"].get(direction, [])
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and contains_cross_generation(entry.get("workspace")):
                    return True
    return False


def _cyclic_components(graph: dict[str, list[str]]) -> list[list[str]]:
    index, low, active, on_stack, components = {}, {}, [], set(), []

    def visit(person_id):
        index[person_id] = low[person_id] = len(index)
        active.append(person_id)
        on_stack.add(person_id)
        for child_id in graph.get(person_id, []):
            if child_id not in index:
                visit(child_id)
                low[person_id] = min(low[person_id], low[child_id])
            elif child_id in on_stack:
                low[person_id] = min(low[person_id], index[child_id])
        if low[person_id] == index[person_id]:
            component = []
            while True:
                item = active.pop()
                on_stack.remove(item)
                component.append(item)
                if item == person_id:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for person_id in graph:
        if person_id not in index:
            visit(person_id)
    return components


def inspect_workspace(raw, photo_exists: Callable[[str], bool] | None = None) -> dict:
    if not _document_shape(raw):
        return unreadable_report("workspace_structure", "工作区不是完整的 schema v2 文档；不会补齐、转换或自动修复。")
    issues = []
    repair_blocked = False

    def issue(issue_id, severity, code, message, people=(), relationships=(), repair=None):
        issues.append({"id": issue_id, "severity": severity, "code": code, "message": message,
                       "person_ids": list(people), "relationship_ids": list(relationships), "repair": repair})

    if not _history_shape(raw):
        issue("history_structure", "error", "history_structure", "持久化撤销或重做快照格式损坏；检查不会修改历史，不能自动修复。")
        repair_blocked = True

    generations = {}
    occupied_positions = {}
    for number, generation in enumerate(raw["generations"]):
        token = f"generation:{number}"
        if (not isinstance(generation, dict) or not isinstance(generation.get("id"), str)
                or not generation["id"] or type(generation.get("position")) is not int or generation["position"] < 0):
            issue(token, "error", "generation_structure", "代际缺少有效 ID 或非负整数位置，不能自动修复。")
            repair_blocked = True
            continue
        generation_id, position = generation["id"], generation["position"]
        if generation_id in generations:
            issue(token + ":duplicate", "error", "duplicate_generation_id", f"代际 ID {generation_id} 重复，不能自动合并。")
            repair_blocked = True
        if position in occupied_positions:
            issue(token + ":position", "error", "duplicate_generation_position", f"代际 {generation_id} 与 {occupied_positions[position]} 使用同一位置。")
            repair_blocked = True
        generations[generation_id] = generation
        occupied_positions[position] = generation_id

    people = {}
    names = defaultdict(list)
    for person_id, person in raw["people"].items():
        token = f"person:{person_id}"
        if (not isinstance(person_id, str) or not person_id or not isinstance(person, dict)
                or person.get("id") != person_id or not isinstance(person.get("name"), str)
                or not person["name"].strip() or person.get("gender") not in ("male", "female")
                or not isinstance(person.get("generation_id"), str)):
            issue(token, "error", "person_structure", f"人物 {person_id} 的 ID、姓名、性别或代际字段无效，不能自动修复。",
                  (person_id,) if isinstance(person_id, str) else ())
            repair_blocked = True
            continue
        people[person_id] = person
        names[person["name"].strip()].append(person_id)
        if person["generation_id"] not in generations:
            issue(token + ":generation", "error", "missing_generation", f"“{person['name']}”引用的代际 {person['generation_id']} 不存在。", (person_id,))
        if not str(person.get("introduction") or "").strip():
            issue(token + ":introduction", "notice", "empty_introduction", f"“{person['name']}”尚未填写简介。", (person_id,))
        photo = person.get("photo_path")
        if photo not in (None, "") and photo_exists is not None and (not isinstance(photo, str) or not photo_exists(photo)):
            issue(token + ":photo", "error", "missing_photo", f"“{person['name']}”的照片引用不可用。", (person_id,), repair={
                "action": "clear_missing_photo", "label": "清除失效照片引用",
                "description": f"将“{person['name']}”的失效照片恢复为默认头像，原照片文件保留。",
            })

    for name, person_ids in names.items():
        if len(person_ids) > 1:
            issue("same_name:" + person_ids[0], "notice", "same_name", f"有 {len(person_ids)} 位人物同名“{name}”；查询时需要选择具体人物，不会自动合并。", person_ids)

    relationship_ids, pairs, graph, valid_relationships, connected = set(), {}, defaultdict(list), [], set()
    for number, relationship in enumerate(raw["relationships"]):
        token = f"relationship:{number}"
        if (not isinstance(relationship, dict) or not isinstance(relationship.get("id"), str)
                or not relationship["id"] or not isinstance(relationship.get("parent_id"), str)
                or not isinstance(relationship.get("child_id"), str)
                or relationship.get("kind") not in ("standard", "special")):
            issue(token, "error", "relationship_structure", "关系缺少有效 ID、端点或类型，不能自动修复。")
            repair_blocked = True
            continue
        relationship_id, parent_id, child_id = relationship["id"], relationship["parent_id"], relationship["child_id"]
        endpoint_ids = [parent_id] if parent_id == child_id else [parent_id, child_id]
        if relationship_id in relationship_ids:
            issue(token + ":id", "error", "duplicate_relationship_id", f"关系 ID {relationship_id} 重复，不能确定修复目标。", endpoint_ids, (relationship_id,))
            repair_blocked = True
        relationship_ids.add(relationship_id)
        if parent_id not in people or child_id not in people:
            issue(token + ":reference", "error", "missing_person", f"关系 {relationship_id} 引用了不存在或格式无效的人物。", endpoint_ids, (relationship_id,))
            continue
        connected.update(endpoint_ids)
        parent, child = people[parent_id], people[child_id]
        if parent_id == child_id:
            issue(token + ":self", "error", "self_relationship", f"“{parent['name']}”存在指向自己的关系。", endpoint_ids, (relationship_id,))
        else:
            graph[parent_id].append(child_id)
            valid_relationships.append(relationship)
        pair = (parent_id, child_id)
        if pair in pairs:
            issue(token + ":duplicate", "error", "duplicate_relationship", f"“{parent['name']} → {child['name']}”存在重复关系。", endpoint_ids, (pairs[pair], relationship_id))
        pairs[pair] = relationship_id
        a = generations.get(parent["generation_id"])
        b = generations.get(child["generation_id"])
        if a is not None and b is not None:
            if a["position"] == b["position"]:
                issue(token + ":same_generation", "error", "same_generation", f"“{parent['name']} → {child['name']}”位于同一代际。", endpoint_ids, (relationship_id,))
            elif a["position"] > b["position"]:
                issue(token + ":reversed", "error", "reversed_generation", f"“{parent['name']}”作为父母却在“{child['name']}”下方；不会自动反转端点。", endpoint_ids, (relationship_id,))
        if relationship["kind"] == "standard":
            expected = core._standard_fields(raw, parent_id, child_id)
            changes = {key: value for key, value in expected.items() if relationship.get(key) != value}
            if changes:
                type_names = {"father_son": "父亲与儿子", "father_daughter": "父亲与女儿",
                              "mother_son": "母亲与儿子", "mother_daughter": "母亲与女儿"}
                detail = []
                if "code" in changes:
                    previous_type = type_names.get(relationship.get("code")) if isinstance(relationship.get("code"), str) else None
                    target_type = type_names[expected["code"]]
                    detail.append(f"关系类型由“{previous_type}”改为“{target_type}”" if previous_type else f"关系类型修正为“{target_type}”")
                for field, label in (("parent_label", "父母称谓"), ("child_label", "子女称谓")):
                    if field in changes:
                        previous_label = relationship.get(field)
                        detail.append(f"{label}由“{previous_label}”改为“{changes[field]}”"
                                      if isinstance(previous_label, str) and previous_label.strip()
                                      else f"{label}补齐为“{changes[field]}”")
                if "color_key" in changes:
                    detail.append(f"连线颜色改为“{type_names[expected['code']]}”对应的颜色")
                issue(token + ":standard", "error", "standard_fields", f"“{parent['name']} → {child['name']}”的标准称谓与性别不一致。", endpoint_ids, (relationship_id,), {
                    "action": "recompute_standard_relationship", "label": "修复标准称谓",
                    "description": f"将“{parent['name']} → {child['name']}”的" + "；".join(detail) + "。人物及连线方向保持不变。",
                })
        elif (not isinstance(relationship.get("parent_label"), str) or not relationship["parent_label"].strip()
              or not isinstance(relationship.get("child_label"), str) or not relationship["child_label"].strip()):
            issue(token + ":labels", "error", "special_labels", f"关系 {relationship_id} 的特殊称谓缺失；不会自动改写特殊关系。", endpoint_ids, (relationship_id,))
            repair_blocked = True
        elif ((relationship["parent_label"].strip() in _FAMILY_PARENT_WORDS or relationship["child_label"].strip() in _FAMILY_CHILD_WORDS)
              and not is_family_relationship(raw, relationship)):
            issue(token + ":family_terms", "notice", "unsupported_family_terms", f"“{parent['name']} → {child['name']}”的特殊亲子词与性别或成对词规则不符，暂不能用于家庭称谓推导；请人工核对。", endpoint_ids, (relationship_id,))

    for component in _cyclic_components(graph):
        component_ids = set(component)
        edge_ids = [relationship["id"] for relationship in valid_relationships
                    if relationship["parent_id"] in component_ids and relationship["child_id"] in component_ids]
        issue("cycle:" + component[0], "error", "relationship_cycle", "亲子方向形成闭环，无法自动决定应修改哪条关系。", component, edge_ids)
    for person_id, person in people.items():
        if person_id not in connected:
            issue(f"person:{person_id}:isolated", "notice", "isolated_person", f"“{person['name']}”尚未登记关系；这可能是有意的建模选择。", (person_id,))
    if repair_blocked:
        for item in issues:
            item["repair"] = None
    return {"status": "issues" if issues else "ok", "summary": _summary(issues), "issues": issues}


def apply_repair(workspace: dict, issue: dict):
    repair = issue.get("repair")
    if not repair:
        raise core.ValidationError("该问题不支持自动修复。")
    if repair["action"] == "recompute_standard_relationship":
        return core.update_relationship(workspace, issue["relationship_ids"][0], {"kind": "standard"})
    if repair["action"] == "clear_missing_photo":
        person = workspace["people"][issue["person_ids"][0]]
        person["photo_path"] = None
        person["updated_at"] = core.now()
        return person
    raise core.ValidationError("未知修复操作。")
