"""Compose one registered connection without asserting blood kinship or marriage.

A sorted shortest simple path is split at special records and at every standard
child-to-other-parent turn. Each remaining U*D* segment is independently named
by the existing blood-kinship rules, using only that segment's recorded edges.
"""
from __future__ import annotations

from collections import defaultdict, deque

from kinship_inference import infer_direct_relationship


COMPOSITION_NOTE = (
    "这是对一种最短已登记连接的分段化简，不是直接血缘称谓。"
    "当前家谱未登记夫妻关系，共同孩子不能据此证明婚姻；特殊称谓仅按登记内容引用。"
)


def _shortest_connection(workspace: dict, from_id: str, to_id: str) -> tuple[list[str], list[dict]] | None:
    adjacency: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for relationship in workspace["relationships"]:
        parent_id, child_id = relationship["parent_id"], relationship["child_id"]
        adjacency[parent_id].append((child_id, relationship))
        adjacency[child_id].append((parent_id, relationship))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: (item[0], item[1]["id"]))

    pending = deque([from_id])
    previous: dict[str, tuple[str | None, dict | None]] = {from_id: (None, None)}
    while pending:
        current = pending.popleft()
        if current == to_id:
            people, relationships = [current], []
            while previous[current][0] is not None:
                parent, relationship = previous[current]
                people.append(parent)
                relationships.append(relationship)
                current = parent
            return list(reversed(people)), list(reversed(relationships))
        for neighbor, relationship in adjacency.get(current, ()):
            if neighbor not in previous:
                previous[neighbor] = current, relationship
                pending.append(neighbor)
    return None


def compose_registered_connection(workspace: dict, from_id: str, to_id: str) -> dict | None:
    """Return a structural composition for a connected, unsupported query.

    The query caller preserves blood-resolved results and invokes this only for
    unsupported connections. This function returns None for an empty path, a
    disconnected pair, or a path that is already one pure blood segment.
    Names are read exclusively when formatting evidence, never for path choice.
    """
    people = workspace["people"]
    people[from_id]
    people[to_id]
    connection = _shortest_connection(workspace, from_id, to_id)
    if connection is None:
        return None
    person_ids, relationships = connection
    if not relationships:
        return None

    def person_name(person_id):
        return (people[person_id].get("name") or "").strip() or "未命名人物"

    def step_direction(index):
        relationship = relationships[index]
        if relationship.get("kind") != "standard":
            return "special"
        return "down" if relationship["parent_id"] == person_ids[index] else "up"

    directions = [step_direction(index) for index in range(len(relationships))]
    labels, explanations = [], []
    has_bridge_or_special = False

    def append_blood_segment(start, end):
        if start == end:
            return
        segment = {**workspace, "relationships": relationships[start:end]}
        result = infer_direct_relationship(segment, person_ids[start], person_ids[end])["results"][0]
        labels.append(result["label"])
        explanations.append(f"血亲段“{result['label']}”：{result['explanation'].removesuffix('。')}")

    start = index = 0
    while index < len(relationships):
        if directions[index] == "special":
            append_blood_segment(start, index)
            relationship = relationships[index]
            field = "child_label" if relationship["parent_id"] == person_ids[index] else "parent_label"
            registered_label = relationship[field]
            labels.append(f"“{registered_label}”（登记特殊称谓）")
            explanations.append(f"登记特殊称谓“{registered_label}”：{person_name(person_ids[index])} → {person_name(person_ids[index + 1])}")
            has_bridge_or_special = True
            index += 1
            start = index
        elif index + 1 < len(relationships) and directions[index:index + 2] == ["down", "up"]:
            append_blood_segment(start, index)
            left_id, child_id, right_id = person_ids[index:index + 3]
            parent_label = "父亲" if people[right_id]["gender"] == "male" else "母亲"
            labels.append("孩子的" + parent_label)
            explanations.append(
                f"共同孩子桥：{person_name(left_id)} → {person_name(child_id)} → {person_name(right_id)}"
                f"（两侧均登记为{person_name(child_id)}的家长，{person_name(right_id)}是该孩子的{parent_label}）"
            )
            has_bridge_or_special = True
            index += 2
            start = index
        else:
            index += 1
    append_blood_segment(start, len(relationships))
    if not has_bridge_or_special:
        return None
    full_path = " → ".join(person_name(person_id) for person_id in person_ids)
    return {
        "label": "的".join(labels),
        "explanation": "；".join(explanations) + "。完整登记路径：" + full_path + "。",
        "note": COMPOSITION_NOTE,
    }
