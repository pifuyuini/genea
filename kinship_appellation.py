"""Familiar forms of address over registered family connections.

This display layer never changes the blood-kinship result or the workspace.
Family parent/child directions determine relative generations; names only format
actual evidence. Unrecognized special terms do not become family graph edges.
"""
from __future__ import annotations

from collections import defaultdict, deque

from kinship_inference import infer_direct_relationship


DAILY_NOTE = "按亲戚往来的日常称呼归纳，详细连接可展开查看。"
_REGISTERED_NOTE = "按已登记称谓称呼，详细连接可展开查看。"
_BASIC_PARENTS = {"male": {"父", "父亲", "爸爸"}, "female": {"母", "母亲", "妈妈"}}
_BASIC_CHILDREN = {"male": {"子", "儿子", "孩子"}, "female": {"女", "女儿", "孩子"}}
_FAMILY_GROUPS = (("养",), ("继",), ("义",), ("嫡", "庶"))


def is_family_relationship(workspace: dict, relationship: dict) -> bool:
    """Recognize only literal paired roles consistent with the stored genders."""
    if relationship.get("kind") == "standard":
        return True
    if relationship.get("kind") != "special":
        return False
    people = workspace["people"]
    parent_gender = people[relationship["parent_id"]]["gender"]
    child_gender = people[relationship["child_id"]]["gender"]
    parent_label = relationship["parent_label"].strip()
    child_label = relationship["child_label"].strip()
    if parent_label in _BASIC_PARENTS[parent_gender] and child_label in _BASIC_CHILDREN[child_gender]:
        return True
    parent_role = "父" if parent_gender == "male" else "母"
    child_role = "子" if child_gender == "male" else "女"
    return any(
        parent_label in {prefix + parent_role for prefix in group}
        and child_label in {prefix + child_role for prefix in group}
        for group in _FAMILY_GROUPS
    )


def _family_connection(workspace: dict, from_id: str, to_id: str) -> tuple[list[str], list[dict]] | None:
    adjacency: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for relationship in workspace["relationships"]:
        if is_family_relationship(workspace, relationship):
            parent, child = relationship["parent_id"], relationship["child_id"]
            adjacency[parent].append((child, relationship))
            adjacency[child].append((parent, relationship))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: (item[0], item[1]["id"]))
    pending = deque([from_id])
    previous: dict[str, tuple[str | None, dict | None]] = {from_id: (None, None)}
    while pending:
        current = pending.popleft()
        if current == to_id:
            person_ids, relationships = [current], []
            while previous[current][0] is not None:
                parent, relationship = previous[current]
                person_ids.append(parent)
                relationships.append(relationship)
                current = parent
            return list(reversed(person_ids)), list(reversed(relationships))
        for neighbor, relationship in adjacency.get(current, ()):
            if neighbor not in previous:
                previous[neighbor] = current, relationship
                pending.append(neighbor)
    return None


def _generation_label(relative_generation: int, target_male: bool, collateral: bool) -> str:
    distance = abs(relative_generation)
    if relative_generation < 0:
        if distance == 1:
            if collateral:
                return "叔伯辈亲戚" if target_male else "姑姨辈亲戚"
            return "父亲辈亲戚" if target_male else "母亲辈亲戚"
        if distance <= 4:
            return {2: "祖", 3: "曾祖", 4: "高祖"}[distance] + ("父" if target_male else "母") + "辈亲戚"
        return "高祖辈以上的" + ("男性" if target_male else "女性") + "长辈亲戚"
    if distance == 1:
        return "侄甥辈亲戚" if target_male else "侄甥女辈亲戚"
    if distance <= 4:
        generation = {2: "孙子", 3: "曾孙", 4: "玄孙"}[distance] if target_male else {2: "孙女", 3: "曾孙女", 4: "玄孙女"}[distance]
        return generation + "辈亲戚"
    return "玄孙辈以下的" + ("男性" if target_male else "女性") + "晚辈亲戚"


def family_connection_metadata(person_ids: list[str], relationships: list[dict]) -> dict:
    """Internal structural facts shared by daily naming and typed query filters."""
    directions = ["D" if relationship["parent_id"] == person_ids[index] else "U" for index, relationship in enumerate(relationships)]
    valleys = [index for index in range(len(directions) - 1) if directions[index:index + 2] == ["D", "U"]]
    relative = directions.count("D") - directions.count("U")
    collateral = False
    start = 0
    for index in valleys:
        segment = directions[start:index]
        collateral |= "U" in segment and "D" in segment
        start = index + 2
    segment = directions[start:]
    collateral |= "U" in segment and "D" in segment
    if not valleys:
        form = "family_kinship"
    elif len(relationships) == 2:
        form = "shared_child"
    elif relative == 0 and collateral:
        form = "daily_cousin"
    elif relative == 0:
        form = "same_generation_relative"
    else:
        form = "generation_relative"
    return {"directions": directions, "valleys": valleys, "relative_generation": relative,
            "collateral": collateral, "form": form}


def infer_familiar_appellation(workspace: dict, from_id: str, to_id: str) -> dict | None:
    """Return a daily form of address for the query caller's unsupported pair.

    The caller keeps exact resolved blood labels. A family-only shortest simple
    connection can be longer than the old chain if that chain uses a non-family
    special record. With no family path, a single direct special label can be
    displayed literally; an unknown multi-edge route stays in the composition.
    """
    people = workspace["people"]
    people[from_id]
    people[to_id]
    if from_id == to_id:
        return None

    def name(person_id):
        return (people[person_id].get("name") or "").strip() or "未命名人物"

    def registered_label(relationship, source):
        return relationship["child_label"] if relationship["parent_id"] == source else relationship["parent_label"]

    connection = _family_connection(workspace, from_id, to_id)
    if connection is None:
        direct_records = [relationship for relationship in workspace["relationships"] if {relationship["parent_id"], relationship["child_id"]} == {from_id, to_id}]
        if not direct_records:
            return None
        relationship = min(direct_records, key=lambda item: item["id"])
        label = registered_label(relationship, from_id)
        return {"label": label, "explanation": f"按双方登记的“{label}”称呼。完整登记路径：{name(from_id)} → {name(to_id)}。", "note": _REGISTERED_NOTE}

    person_ids, relationships = connection
    metadata = family_connection_metadata(person_ids, relationships)
    valleys = metadata["valleys"]
    target_male = people[to_id]["gender"] == "male"
    relative = metadata["relative_generation"]
    collateral = metadata["collateral"]

    if len(relationships) == 1 and relationships[0].get("kind") == "special":
        label = registered_label(relationships[0], from_id)
        rule = f"按双方已登记的家庭称谓“{label}”称呼。"
    elif not valleys:
        # Use the proven family path as a display-only parent/child chain;
        # this local copy never enters the original blood graph or persistence.
        segment_workspace = {**workspace, "relationships": [{**relationship, "kind": "standard"} for relationship in relationships]}
        label = infer_direct_relationship(segment_workspace, from_id, to_id)["results"][0]["label"]
        rule = f"按已登记家庭亲子方向逐级称呼为{label}。"
    elif len(relationships) == 2:
        label = "孩子的" + ("父亲" if target_male else "母亲")
        rule = f"双方通过共同孩子{name(person_ids[1])}联系，按该孩子的家长角色称呼。"
    elif relative == 0:
        if collateral:
            label = ("表兄弟" if target_male else "表姐妹") + "（平辈，长幼未知）"
            rule = "双方在家庭亲子路径中同辈，连接含旁系亲戚段，按亲戚往来的日常表亲称呼归纳；长幼未登记。"
        else:
            label = "平辈亲戚"
            rule = "双方在家庭亲子路径中同辈，路径通过共同孩子或后代相接，按平辈亲戚称呼。"
    else:
        label = _generation_label(relative, target_male, collateral)
        rule = f"家庭亲子方向显示目标{'长' if relative < 0 else '晚'}{abs(relative)}辈，以{label}作日常概括。"

    details = []
    if valleys:
        bridges = [" → ".join(name(person_id) for person_id in person_ids[index:index + 3]) for index in valleys]
        details.append("共同孩子连接：" + "；".join(bridges) + "。")
    family_specials = [f"{name(person_ids[index])} → {name(person_ids[index + 1])}（{registered_label(relationship, person_ids[index])}）" for index, relationship in enumerate(relationships) if relationship.get("kind") == "special"]
    if family_specials:
        details.append("家庭登记称谓：" + "；".join(family_specials) + "。")
    full_path = " → ".join(name(person_id) for person_id in person_ids)
    return {"label": label, "explanation": rule + "".join(details) + "完整家庭路径：" + full_path + "。", "note": DAILY_NOTE}
