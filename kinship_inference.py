"""Infer direct kinship from registered standard parent-child relationships.

The result addresses the target from the source person's point of view. Names,
introductions, custom labels and person order never participate in inference.
"""
from __future__ import annotations

from collections import defaultdict, deque

from kinship_naming import name_distant_relationship, structural_relationship


def _ancestor_paths(parents: dict[str, tuple[str, ...]], person_id: str) -> dict[str, list[tuple[str, ...]]]:
    """Include every upward path, including the person as their own ancestor."""
    paths: dict[str, list[tuple[str, ...]]] = defaultdict(list)
    pending = [(person_id,)]
    while pending:
        path = pending.pop()
        paths[path[-1]].append(path)
        for parent_id in parents.get(path[-1], ()):
            if parent_id not in path:
                pending.append((*path, parent_id))
    return paths


def _label(people: dict, source_path: tuple[str, ...], target_path: tuple[str, ...]) -> str:
    up, down = len(source_path) - 1, len(target_path) - 1
    target_male = people[target_path[0]]["gender"] == "male"
    if down == 0:
        if up == 1:
            return "父亲" if target_male else "母亲"
        if up == 2:
            maternal = people[source_path[1]]["gender"] == "female"
            return ("外祖" if maternal else "祖") + ("父" if target_male else "母")
        return name_distant_relationship(people, source_path, target_path)
    if up == 0:
        if down == 1:
            return "儿子" if target_male else "女儿"
        if down == 2:
            maternal = people[target_path[1]]["gender"] == "female"
            return ("外孙" if maternal else "孙") + ("子" if target_male else "女")
        return name_distant_relationship(people, source_path, target_path)
    if up == down == 1:
        return ("兄弟" if target_male else "姐妹") + "（长幼未知）"
    if up == 2 and down == 1:
        paternal = people[source_path[1]]["gender"] == "male"
        if paternal:
            return "伯父／叔父（长幼未知）" if target_male else "姑母"
        return "舅父" if target_male else "姨母"
    if up == 1 and down == 2:
        brother_child = people[target_path[1]]["gender"] == "male"
        if brother_child:
            return "侄子" if target_male else "侄女"
        return "外甥" if target_male else "外甥女"
    if up == down == 2:
        source_parent_male = people[source_path[1]]["gender"] == "male"
        target_parent_male = people[target_path[1]]["gender"] == "male"
        branch = {
            (True, True): "堂", (True, False): "姑表",
            (False, True): "舅表", (False, False): "姨表",
        }[(source_parent_male, target_parent_male)]
        return branch + ("兄弟" if target_male else "姐妹") + "（长幼未知）"
    return name_distant_relationship(people, source_path, target_path)


def _explanation(people: dict, source_path: tuple[str, ...], target_path: tuple[str, ...]) -> str:
    # Names are display-only; the proof has already been selected using IDs.
    path = (*source_path, *reversed(target_path[:-1]))
    names = [(people[person_id].get("name") or "").strip() or "未命名人物" for person_id in path]
    evidence = " → ".join(names) + "。"
    if max(len(source_path), len(target_path)) > 3:
        return structural_relationship(people, source_path, target_path) + "；" + evidence
    return evidence


def _connected(adjacency: dict[str, set[str]], from_id: str, to_id: str) -> bool:
    pending = deque([from_id])
    seen = {from_id}
    while pending:
        for neighbor in adjacency.get(pending.popleft(), ()):
            if neighbor == to_id:
                return True
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return False


def valid_kinship_paths(source_ancestors: dict, target_ancestors: dict):
    """Yield proven disjoint ancestor arms for naming and internal typed queries."""
    for ancestor_id in sorted(source_ancestors.keys() & target_ancestors.keys()):
        for source_path in source_ancestors[ancestor_id]:
            for target_path in target_ancestors[ancestor_id]:
                if not set(source_path[:-1]) & set(target_path[:-1]):
                    yield source_path, target_path


def infer_direct_relationship(workspace: dict, from_id: str, to_id: str) -> dict:
    """Return stable, deduplicated kinship labels without changing the workspace.

    Only kind == "standard" is biological evidence. The workspace's legal
    directed parent graph can have multiple parents and undirected cycles.
    Each proof goes upward to a common ancestor, then downward to the target;
    its two arms may share only that ancestor. Proofs for an identical label
    collapse to one result, chosen by edge count and then person IDs.
    """
    people = workspace["people"]
    people[from_id]
    people[to_id]
    if from_id == to_id:
        return {"status": "resolved", "results": [{"label": "自己", "explanation": "起点和目标是同一人物。"}], "note": ""}

    parent_sets: dict[str, set[str]] = defaultdict(set)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for relationship in workspace["relationships"]:
        parent_id, child_id = relationship["parent_id"], relationship["child_id"]
        adjacency[parent_id].add(child_id)
        adjacency[child_id].add(parent_id)
        if relationship.get("kind") == "standard":
            parent_sets[child_id].add(parent_id)
    parents = {child_id: tuple(sorted(parent_ids)) for child_id, parent_ids in parent_sets.items()}
    source_ancestors = _ancestor_paths(parents, from_id)
    target_ancestors = _ancestor_paths(parents, to_id)
    proofs: dict[str, tuple[int, tuple[str, ...], tuple[str, ...]]] = {}
    for source_path, target_path in valid_kinship_paths(source_ancestors, target_ancestors):
        label = _label(people, source_path, target_path)
        proof = (len(source_path) + len(target_path) - 2, source_path, target_path)
        if label not in proofs or proof < proofs[label]:
            proofs[label] = proof
    if proofs:
        ordered = sorted(proofs, key=lambda label: (proofs[label][0], label))
        results = [{"label": label, "explanation": _explanation(people, proofs[label][1], proofs[label][2])} for label in ordered]
        return {"status": "resolved", "results": results, "note": "存在多重亲缘，已列出当前规则成立的不同称谓。" if len(results) > 1 else ""}
    if _connected(adjacency, from_id, to_id):
        return {"status": "unsupported", "results": [], "note": "已找到登记连接，但当前普通亲子规则无法推导直接亲属称谓；特殊关系及共同子女不能据此推断血缘或婚姻。"}
    return {"status": "disconnected", "results": [], "note": "未找到已登记的连接，现有记录不足以推导直接亲属称谓。"}
