from __future__ import annotations

from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
import uuid

from kinship_inference import infer_direct_relationship

COLORS = {
    "father_son": "father-son", "father_daughter": "father-daughter",
    "mother_son": "mother-son", "mother_daughter": "mother-daughter",
}
LABELS = {
    "father_son": ("爸爸", "儿子"), "father_daughter": ("爸爸", "女儿"),
    "mother_son": ("妈妈", "儿子"), "mother_daughter": ("妈妈", "女儿"),
}

class ValidationError(ValueError): pass
class NotFoundError(ValueError): pass
class ConflictError(ValueError): pass

def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def default_workspace() -> dict[str, Any]:
    return {"schema_version": 2, "generations": [], "people": {}, "relationships": []}

def ensure_workspace(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("schema_version") != 2:
        raise ValidationError("Unsupported workspace schema.")
    result = deepcopy(default_workspace())
    result["generations"] = list(raw.get("generations") or [])
    result["people"] = dict(raw.get("people") or {})
    result["relationships"] = list(raw.get("relationships") or [])
    return result

def _generation(workspace: dict, generation_id: str) -> dict:
    for generation in workspace["generations"]:
        if generation["id"] == generation_id:
            return generation
    raise NotFoundError("Generation not found.")

def _person(workspace: dict, person_id: str) -> dict:
    try: return workspace["people"][person_id]
    except KeyError as exc: raise NotFoundError("Person not found.") from exc

def normalize_positions(workspace: dict) -> None:
    workspace["generations"].sort(key=lambda item: item["position"])
    for index, generation in enumerate(workspace["generations"]): generation["position"] = index

def remove_nonadjacent_relationships(workspace: dict) -> list[str]:
    removed = []
    kept = []
    for relationship in workspace["relationships"]:
        try:
            _oriented(workspace, relationship["parent_id"], relationship["child_id"])
        except ValidationError:
            removed.append(relationship["id"])
        else:
            kept.append(relationship)
    workspace["relationships"] = kept
    return removed

def add_generation(workspace: dict, placement: str, anchor_id: str | None = None, name: str | None = None, *, allow_cross_generation: bool = False) -> dict:
    generations = workspace["generations"]
    if placement not in {"first", "above", "below"}: raise ValidationError("Invalid placement.")
    if placement == "first":
        if generations: raise ConflictError("First generation already exists.")
        index = 0
    else:
        anchor = _generation(workspace, anchor_id or "")
        index = anchor["position"] + (1 if placement == "below" else 0)
    generation = {"id": new_id("gen"), "name": (name or "").strip() or f"第{index + 1}层", "position": index}
    generations.insert(index, generation); normalize_positions(workspace)
    if not allow_cross_generation: remove_nonadjacent_relationships(workspace)
    return generation

def update_generation(workspace: dict, generation_id: str, changes: dict) -> dict:
    generation = _generation(workspace, generation_id)
    if "name" in changes:
        name = str(changes["name"]).strip()
        if not name: raise ValidationError("Generation name is required.")
        generation["name"] = name
    return generation

def delete_generation(workspace: dict, generation_id: str) -> None:
    _generation(workspace, generation_id)
    if any(p["generation_id"] == generation_id for p in workspace["people"].values()):
        raise ConflictError("Generation is not empty.")
    workspace["generations"] = [g for g in workspace["generations"] if g["id"] != generation_id]
    normalize_positions(workspace)

def add_person(workspace: dict, payload: dict) -> dict:
    _generation(workspace, str(payload.get("generation_id") or ""))
    gender = payload.get("gender")
    if gender not in {"male", "female"}: raise ValidationError("Gender must be male or female.")
    name = str(payload.get("name") or "").strip()
    if not name: raise ValidationError("Name is required.")
    timestamp = now(); person_id = new_id("person")
    person = {"id": person_id, "generation_id": payload["generation_id"], "name": name, "gender": gender,
              "introduction": str(payload.get("introduction") or ""), "photo_path": payload.get("photo_path"),
              "order": int(payload.get("order", len(workspace["people"]))), "created_at": timestamp, "updated_at": timestamp}
    workspace["people"][person_id] = person
    return person

def reorder_generation_people(workspace: dict, generation_id: str, person_ids: list[str]) -> None:
    """Replace one generation's complete person order without changing other data."""
    _generation(workspace, generation_id)
    if not isinstance(person_ids, list) or any(not isinstance(person_id, str) for person_id in person_ids):
        raise ValidationError("person_ids must be an array of person IDs.")
    if len(person_ids) != len(set(person_ids)):
        raise ValidationError("person_ids must not contain duplicates.")

    expected_ids = {
        person_id
        for person_id, person in workspace["people"].items()
        if person["generation_id"] == generation_id
    }
    if set(person_ids) != expected_ids:
        raise ValidationError("person_ids must contain every person in the generation exactly once.")

    for order, person_id in enumerate(person_ids):
        workspace["people"][person_id]["order"] = order

def _standard_fields(workspace: dict, parent_id: str, child_id: str) -> dict:
    parent, child = _person(workspace, parent_id), _person(workspace, child_id)
    if parent["gender"] not in {"male", "female"} or child["gender"] not in {"male", "female"}:
        raise ValidationError("Both people must have gender.")
    code = ("father" if parent["gender"] == "male" else "mother") + "_" + ("son" if child["gender"] == "male" else "daughter")
    parent_label, child_label = LABELS[code]
    return {"kind": "standard", "code": code, "parent_label": parent_label, "child_label": child_label, "color_key": COLORS[code]}

def _oriented(workspace: dict, source_id: str, target_id: str, *, allow_cross_generation: bool = False) -> tuple[str, str]:
    source, target = _person(workspace, source_id), _person(workspace, target_id)
    a = _generation(workspace, source["generation_id"])["position"]
    b = _generation(workspace, target["generation_id"])["position"]
    if allow_cross_generation:
        if a == b: raise ValidationError("People must be in different generations.")
    elif abs(a - b) != 1: raise ValidationError("People must be in adjacent generations.")
    return (source_id, target_id) if a < b else (target_id, source_id)

def add_relationship(workspace: dict, source_id: str, target_id: str, *, allow_cross_generation: bool = False) -> dict:
    parent_id, child_id = _oriented(workspace, source_id, target_id, allow_cross_generation=allow_cross_generation)
    if any(r["parent_id"] == parent_id and r["child_id"] == child_id for r in workspace["relationships"]):
        raise ConflictError("Relationship already exists.")
    timestamp = now(); relationship = {"id": new_id("rel"), "parent_id": parent_id, "child_id": child_id,
        **_standard_fields(workspace, parent_id, child_id), "created_at": timestamp, "updated_at": timestamp}
    workspace["relationships"].append(relationship); return relationship

def _relationship(workspace: dict, relationship_id: str) -> dict:
    for relationship in workspace["relationships"]:
        if relationship["id"] == relationship_id: return relationship
    raise NotFoundError("Relationship not found.")

def update_relationship(workspace: dict, relationship_id: str, payload: dict) -> dict:
    relationship = _relationship(workspace, relationship_id); kind = payload.get("kind")
    if kind == "standard": relationship.update(_standard_fields(workspace, relationship["parent_id"], relationship["child_id"]))
    elif kind == "special":
        parent_label, child_label = str(payload.get("parent_label") or "").strip(), str(payload.get("child_label") or "").strip()
        if not parent_label or not child_label: raise ValidationError("Special labels are required.")
        relationship.update({"kind": "special", "code": "special", "parent_label": parent_label, "child_label": child_label, "color_key": "special"})
    else: raise ValidationError("Invalid relationship kind.")
    relationship["updated_at"] = now(); return relationship

def _validate_person_relationship_order(workspace: dict, person_id: str, generation_id: str) -> None:
    conflicts = []
    for relationship in workspace["relationships"]:
        if person_id not in {relationship["parent_id"], relationship["child_id"]}: continue
        parent = _person(workspace, relationship["parent_id"])
        child = _person(workspace, relationship["child_id"])
        parent_generation = generation_id if parent["id"] == person_id else parent["generation_id"]
        child_generation = generation_id if child["id"] == person_id else child["generation_id"]
        if _generation(workspace, parent_generation)["position"] >= _generation(workspace, child_generation)["position"]:
            conflicts.append(f'{parent["name"]} → {child["name"]}')
    if conflicts:
        raise ValidationError("父母必须位于子女上方；关系冲突：" + "、".join(conflicts))

def update_person(workspace: dict, person_id: str, payload: dict, *, allow_cross_generation: bool = False) -> tuple[dict, list[str]]:
    current = _person(workspace, person_id)
    person = dict(current) if allow_cross_generation else current
    if "generation_id" in payload: _generation(workspace, payload["generation_id"]); person["generation_id"] = payload["generation_id"]
    if "gender" in payload:
        if payload["gender"] not in {"male", "female"}: raise ValidationError("Gender must be male or female.")
        person["gender"] = payload["gender"]
    if "name" in payload:
        if not isinstance(payload["name"], str) or not payload["name"].strip():
            raise ValidationError("Name must be a non-empty string.")
        person["name"] = payload["name"].strip()
    for key in ("introduction", "photo_path", "order"):
        if key in payload: person[key] = payload[key]
    if allow_cross_generation:
        if person["generation_id"] != current["generation_id"]:
            _validate_person_relationship_order(workspace, person_id, person["generation_id"])
        current.update(person)
        person = current
    removed = []
    kept = []
    for relationship in workspace["relationships"]:
        if person_id in {relationship["parent_id"], relationship["child_id"]}:
            if not allow_cross_generation:
                try: parent_id, child_id = _oriented(workspace, relationship["parent_id"], relationship["child_id"])
                except ValidationError: removed.append(relationship["id"]); continue
                relationship["parent_id"], relationship["child_id"] = parent_id, child_id
            if relationship["kind"] == "standard": relationship.update(_standard_fields(workspace, relationship["parent_id"], relationship["child_id"]))
        kept.append(relationship)
    workspace["relationships"] = kept; person["updated_at"] = now()
    return person, removed

def delete_person(workspace: dict, person_id: str) -> list[str]:
    _person(workspace, person_id); del workspace["people"][person_id]
    removed = [r["id"] for r in workspace["relationships"] if person_id in {r["parent_id"], r["child_id"]}]
    workspace["relationships"] = [r for r in workspace["relationships"] if r["id"] not in removed]
    return removed

def delete_relationship(workspace: dict, relationship_id: str) -> None:
    _relationship(workspace, relationship_id)
    workspace["relationships"] = [r for r in workspace["relationships"] if r["id"] != relationship_id]

def relationship_path(workspace: dict, from_id: str, to_id: str) -> dict:
    """Return how the `to` person is addressed by the `from` person."""
    _person(workspace, from_id)
    _person(workspace, to_id)
    if from_id == to_id: return {"path_text": "自己", "person_ids": [from_id], "relationship_ids": []}
    adjacency: dict[str, list[tuple[str, str, str]]] = {}
    for r in workspace["relationships"]:
        adjacency.setdefault(r["parent_id"], []).append((r["child_id"], r["child_label"], r["id"]))
        adjacency.setdefault(r["child_id"], []).append((r["parent_id"], r["parent_label"], r["id"]))
    queue = deque([(from_id, [from_id], [], [])]); seen = {from_id}
    while queue:
        current, people, relationships, labels = queue.popleft()
        for neighbor, label, relationship_id in adjacency.get(current, []):
            if neighbor in seen: continue
            if neighbor == to_id: return {"path_text": "的".join([*labels, label]), "person_ids": [*people, neighbor], "relationship_ids": [*relationships, relationship_id]}
            seen.add(neighbor); queue.append((neighbor, [*people, neighbor], [*relationships, relationship_id], [*labels, label]))
    return {"path_text": "", "person_ids": [], "relationship_ids": []}


def relationship_query(workspace: dict, from_id: str, to_id: str) -> dict:
    """Keep the chain, infer blood kinship, and compose unsupported connections."""
    from kinship_composition import compose_registered_connection
    from kinship_appellation import infer_familiar_appellation

    path = relationship_path(workspace, from_id, to_id)
    direct = infer_direct_relationship(workspace, from_id, to_id)
    if direct["status"] == "unsupported":
        composition = compose_registered_connection(workspace, from_id, to_id)
        if composition is not None:
            direct["composition"] = composition
        appellation = infer_familiar_appellation(workspace, from_id, to_id)
        if appellation is not None:
            direct["appellation"] = appellation
    return {**path, "direct_relationship": direct}
