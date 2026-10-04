"""Experimental, local-rule natural-language relation queries.

One per-query index resolves visible names and supports typed graph filtering.
Typed evidence is internal: public path results retain the existing chain,
blood result, registered composition and familiar form of address unchanged.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import re
import unicodedata

import genealogy_core as core
from kinship_appellation import family_connection_metadata, is_family_relationship
from kinship_inference import _ancestor_paths, _label, valid_kinship_paths
from kinship_naming import canonical_selector


@dataclass(frozen=True)
class RelativeType:
    kind: str
    gender: str | None = None
    tag: str | None = None
    biological_only: bool = False
    age_unknown: bool = False


_RELATIVE_TYPES: dict[str, RelativeType] = {}


def _aliases(words: str, kind: str, **options) -> None:
    for word in words.split("/"):
        _RELATIVE_TYPES[word] = RelativeType(kind, **options)


_aliases("父母/双亲", "parents")
_aliases("父亲/爸爸/父", "parents", gender="male")
_aliases("母亲/妈妈/母", "parents", gender="female")
_aliases("亲生父母", "parents", biological_only=True)
_aliases("亲生父亲", "parents", gender="male", biological_only=True)
_aliases("亲生母亲", "parents", gender="female", biological_only=True)
_aliases("子女/孩子/儿女", "children")
_aliases("儿子/子", "children", gender="male")
_aliases("女儿/女", "children", gender="female")
_aliases("亲生子女", "children", biological_only=True)
_aliases("祖父母", "grandparents")
_aliases("祖父/爷爷", "grandparents", gender="male", tag="paternal_grandparents")
_aliases("祖母/奶奶", "grandparents", gender="female", tag="paternal_grandparents")
_aliases("外祖父母", "grandparents", tag="maternal_grandparents")
_aliases("外祖父/外公", "grandparents", gender="male", tag="maternal_grandparents")
_aliases("外祖母/外婆", "grandparents", gender="female", tag="maternal_grandparents")
_aliases("孙辈/孙子女", "grandchildren")
_aliases("孙子", "grandchildren", gender="male", tag="sons_grandchildren")
_aliases("孙女", "grandchildren", gender="female", tag="sons_grandchildren")
_aliases("外孙/外孙子", "grandchildren", gender="male", tag="daughters_grandchildren")
_aliases("外孙女", "grandchildren", gender="female", tag="daughters_grandchildren")
_aliases("祖先/直系祖先", "ancestors")
_aliases("后代/直系后代", "descendants")
_aliases("兄弟姐妹/兄弟姊妹/手足", "siblings")
_aliases("兄弟", "siblings", gender="male")
_aliases("姐妹/姊妹", "siblings", gender="female")
_aliases("哥哥/弟弟/兄/弟", "siblings", gender="male", age_unknown=True)
_aliases("姐姐/妹妹/姐/妹", "siblings", gender="female", age_unknown=True)
_aliases("伯叔姑舅姨/叔伯姑舅姨/伯叔姑姨/叔伯姑姨/叔伯/伯叔/姑舅姨", "uncles_aunts")
_aliases("伯父/叔父/叔叔/伯伯/伯叔父", "uncles_aunts", gender="male", tag="paternal_uncles_aunts", age_unknown=True)
_aliases("姑母/姑姑", "uncles_aunts", gender="female", tag="paternal_uncles_aunts")
_aliases("舅父/舅舅", "uncles_aunts", gender="male", tag="maternal_uncles_aunts")
_aliases("姨母/姨妈/阿姨", "uncles_aunts", gender="female", tag="maternal_uncles_aunts")
_aliases("侄甥/侄甥辈/侄子女和外甥/侄子女与外甥", "nephews_nieces")
_aliases("侄子女", "nephews_nieces", tag="brothers_children")
_aliases("侄子", "nephews_nieces", gender="male", tag="brothers_children")
_aliases("侄女", "nephews_nieces", gender="female", tag="brothers_children")
_aliases("外甥/外甥子", "nephews_nieces", gender="male", tag="sisters_children")
_aliases("外甥女", "nephews_nieces", gender="female", tag="sisters_children")
_aliases("堂表亲/堂表兄弟姐妹/堂表兄弟姊妹", "cousins")
_aliases("堂亲/堂兄弟姐妹", "cousins", tag="paternal_cousins")
_aliases("表亲/表兄弟姐妹", "cousins", tag="maternal_cousins")
_aliases("堂兄弟", "cousins", gender="male", tag="paternal_cousins")
_aliases("堂姐妹", "cousins", gender="female", tag="paternal_cousins")
_aliases("表兄弟", "cousins", gender="male", tag="maternal_cousins")
_aliases("表姐妹", "cousins", gender="female", tag="maternal_cousins")
_aliases("堂哥/堂弟/堂哥哥/堂弟弟", "cousins", gender="male", tag="paternal_cousins", age_unknown=True)
_aliases("堂姐/堂妹", "cousins", gender="female", tag="paternal_cousins", age_unknown=True)
_aliases("表哥/表弟/表哥哥/表弟弟", "cousins", gender="male", tag="maternal_cousins", age_unknown=True)
_aliases("表姐/表妹", "cousins", gender="female", tag="maternal_cousins", age_unknown=True)
_aliases("养亲/养父母", "adoptive_parents")
_aliases("养父", "adoptive_parents", gender="male")
_aliases("养母", "adoptive_parents", gender="female")
_aliases("养子女/养孩子", "adoptive_children")
_aliases("养子", "adoptive_children", gender="male")
_aliases("养女", "adoptive_children", gender="female")

_EXAMPLES = "可试：贾珍和薛蟠是什么关系；贾母的孙辈有哪些；奥雷里亚诺上校的子女有哪些。"
_MIDDLE_DOTS = str.maketrans("·•・･‧.．", "       ")


def _normalized(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).translate(_MIDDLE_DOTS).casefold().split())


def _mention(value: str) -> str:
    return value.strip().strip(chr(34) + chr(39) + "“”‘’「」『』，,:：").strip()


def _pair_mentions(value: str) -> list[list[str]]:
    """Enumerate connector positions outside quoted names, without guessing."""
    closing_quotes = {"“": "”", "‘": "’", "「": "」", "『": "』", chr(34): chr(34), chr(39): chr(39)}
    closing = None
    alternatives = []
    for position, character in enumerate(value):
        if closing is not None:
            if character == closing:
                closing = None
            continue
        if character in closing_quotes:
            closing = closing_quotes[character]
        elif character in "和与跟":
            mentions = [_mention(value[:position]), _mention(value[position + 1:])]
            if all(mentions):
                alternatives.append(mentions)
    return alternatives


def _parse(text: str):
    value = unicodedata.normalize("NFKC", text).strip().rstrip("?？!！。 \t\n")
    for prefix in ("帮我查一下", "请告诉我", "请问", "查询", "查找", "找出", "查一下"):
        if value.startswith(prefix):
            value = value[len(prefix):].lstrip("，,:： ")
            break
    reverse = re.fullmatch(r"(.+?)是(.+?)的(?:什么人|什么亲戚|什么关系)", value)
    if reverse:
        return "pair", [[_mention(reverse[1]), _mention(reverse[2])]], None, 1, 0
    pair = re.fullmatch(r"(.+?)(?:之间)?(?:是什么关系|是何关系|有什么关系|是什么亲戚|的关系|什么关系)", value)
    if pair:
        alternatives = _pair_mentions(pair[1])
        if alternatives:
            return "pair", alternatives, None, 0, 1
    relative = re.fullmatch(r"(.+)的(.+?)(?:有哪些人|有哪些|都有谁|有谁|是谁|名单)?", value)
    if relative:
        return "relatives", [[_mention(relative[1])]], relative[2].strip(), 0, None
    return None


def _reply(status: str, *, intent=None, message=None, **fields) -> dict:
    result = {"status": status, "ambiguities": [], "results": []}
    if intent is not None:
        result["intent"] = intent
    if message is not None:
        result["message"] = message
    result.update(fields)
    return result


def _name_aliases(name: str) -> set[str]:
    aliases = set(re.findall(r"[（(]([^()（）]+)[）)]", name))
    base = re.sub(r"[（(][^()（）]*[）)]", "", name).strip()
    aliases.add(base)
    for title in ("上校", "将军", "夫人", "姨妈", "小姐", "太君"):
        if base.endswith(title):
            first = re.split(r"[·•・･‧.．]", base)[0]
            if first != base:
                aliases.add(first + title)
    return {_normalized(alias) for alias in aliases if alias}


def _lineage_tags(people: dict, source_path: tuple[str, ...], target_path: tuple[str, ...]) -> set[str]:
    up, down = len(source_path) - 1, len(target_path) - 1
    tags = set()
    if up > 0 and down == 0:
        tags.add("ancestors")
        if up == 1:
            tags.add("parents")
        if up == 2:
            tags.update(("grandparents", "paternal_grandparents" if people[source_path[1]]["gender"] == "male" else "maternal_grandparents"))
    elif down > 0 and up == 0:
        tags.add("descendants")
        if down == 1:
            tags.add("children")
        if down == 2:
            tags.update(("grandchildren", "sons_grandchildren" if people[target_path[1]]["gender"] == "male" else "daughters_grandchildren"))
    elif up == down == 1:
        tags.add("siblings")
    elif up == 2 and down == 1:
        tags.update(("uncles_aunts", "paternal_uncles_aunts" if people[source_path[1]]["gender"] == "male" else "maternal_uncles_aunts"))
    elif up == 1 and down == 2:
        tags.update(("nephews_nieces", "brothers_children" if people[target_path[1]]["gender"] == "male" else "sisters_children"))
    elif up == down and up >= 2:
        paternal = all(people[person_id]["gender"] == "male" for person_id in (*source_path[1:-1], *target_path[1:-1]))
        tags.update(("cousins", "paternal_cousins" if paternal else "maternal_cousins"))
    return tags


class QueryIndex:
    """A fresh request-scoped name/parent/family index, with lazy ancestry cache."""
    def __init__(self, workspace):
        self.workspace = workspace
        self.people = workspace["people"]
        self.generations = {generation["id"]: generation for generation in workspace["generations"]}
        self.names = defaultdict(list)
        self.aliases = {}
        parent_sets = defaultdict(set)
        self.family = defaultdict(list)
        self.records = defaultdict(list)
        self.ancestry = {}
        self.family_trees = {}
        for person_id, person in self.people.items():
            self.names[_normalized(person["name"])].append(person_id)
            self.aliases[person_id] = _name_aliases(person["name"])
        for relationship in workspace["relationships"]:
            parent, child = relationship["parent_id"], relationship["child_id"]
            self.records[frozenset((parent, child))].append(relationship)
            if relationship.get("kind") == "standard":
                parent_sets[child].add(parent)
            if is_family_relationship(workspace, relationship):
                self.family[parent].append((child, relationship))
                self.family[child].append((parent, relationship))
        self.parents = {child: tuple(sorted(parents)) for child, parents in parent_sets.items()}
        for neighbors in self.family.values():
            neighbors.sort(key=lambda item: (item[0], item[1]["id"]))

    def person_order(self, person_id):
        person = self.people[person_id]
        return self.generations[person["generation_id"]]["position"], person.get("order", 0), person_id

    def candidates(self, mention):
        normalized = _normalized(mention)
        if not normalized:
            return []
        exact = self.names.get(normalized)
        if exact:
            return sorted(exact, key=self.person_order)
        return sorted((person_id for person_id, person in self.people.items()
                       if normalized in self.aliases[person_id] or normalized in _normalized(person["name"])), key=self.person_order)

    def candidate_details(self, person_id):
        person = self.people[person_id]
        return {"id": person_id, "name": person["name"], "generation": self.generations[person["generation_id"]]["name"],
                "gender": person["gender"], "introduction": person.get("introduction", "")}

    def ancestors(self, person_id):
        if person_id not in self.ancestry:
            self.ancestry[person_id] = _ancestor_paths(self.parents, person_id)
        return self.ancestry[person_id]

    def family_path(self, source, target):
        if source not in self.family_trees:
            pending, previous = deque([source]), {source: (None, None)}
            while pending:
                current = pending.popleft()
                for neighbor, relationship in self.family.get(current, ()):
                    if neighbor not in previous:
                        previous[neighbor] = current, relationship
                        pending.append(neighbor)
            self.family_trees[source] = previous
        previous = self.family_trees[source]
        if target not in previous:
            return None
        people, relationships, current = [target], [], target
        while previous[current][0] is not None:
            parent, relationship = previous[current]
            people.append(parent)
            relationships.append(relationship)
            current = parent
        return list(reversed(people)), list(reversed(relationships))

    def evidence(self, source, target):
        evidence = []
        blood_paths = list(valid_kinship_paths(self.ancestors(source), self.ancestors(target)))
        for source_path, target_path in blood_paths:
            evidence.append({"tags": _lineage_tags(self.people, source_path, target_path), "edges": len(source_path) + len(target_path) - 2,
                             "label": _label(self.people, source_path, target_path), "biological": True,
                             "selector": canonical_selector(self.people, source_path, target_path)})
        family_path = self.family_path(source, target)
        if family_path is not None:
            people, relationships = family_path
            metadata = family_connection_metadata(people, relationships)
            if not metadata["valleys"]:
                up = metadata["directions"].count("U")
                source_path, target_path = tuple(people[:up + 1]), tuple(reversed(people[up:]))
                label = _label(self.people, source_path, target_path)
                if len(relationships) == 1 and relationships[0].get("kind") == "special":
                    field = "child_label" if relationships[0]["parent_id"] == source else "parent_label"
                    label = relationships[0][field].strip()
                evidence.append({"tags": _lineage_tags(self.people, source_path, target_path), "edges": len(relationships),
                                 "label": label, "biological": False})
            elif not blood_paths and metadata["form"] == "daily_cousin":
                evidence.append({"tags": {"cousins", "maternal_cousins"}, "edges": len(relationships),
                                 "label": ("表兄弟" if self.people[target]["gender"] == "male" else "表姐妹") + "（平辈，长幼未知）", "biological": False})
        for relationship in self.records.get(frozenset((source, target)), ()):
            if relationship.get("kind") == "special" and is_family_relationship(self.workspace, relationship):
                if relationship["parent_label"].strip() in {"养父", "养母"} and relationship["child_label"].strip() in {"养子", "养女"}:
                    kind = "adoptive_parents" if relationship["child_id"] == source else "adoptive_children"
                    field = "parent_label" if kind == "adoptive_parents" else "child_label"
                    evidence.append({"tags": {kind}, "edges": 1, "label": relationship[field].strip(), "biological": False})
        return evidence


def run_query(workspace: dict, text: str, resolutions=None) -> dict:
    """Pure, bounded grammar. User input errors return structured responses."""
    if not isinstance(text, str) or not text.strip():
        return _reply("unsupported", message="请填写人物关系问题。" + _EXAMPLES)
    parsed = _parse(text)
    if parsed is None:
        return _reply("unsupported", message="暂不支持这个问法。" + _EXAMPLES)
    intent, alternatives, relative_word, source_slot, target_slot = parsed
    slot_count = len(alternatives[0])
    spec = None
    if intent == "relatives":
        spec = _RELATIVE_TYPES.get(relative_word)
        if spec is None:
            return _reply("unsupported", intent=intent, message="暂不支持此类筛选；可查询父母、子女、孙辈、兄弟姐妹、堂表亲或养亲。" + _EXAMPLES)
    if resolutions is None:
        resolutions = {}
    if not isinstance(resolutions, dict) or any(key not in {str(index) for index in range(slot_count)} or not isinstance(value, str) for key, value in resolutions.items()):
        return _reply("unsupported", intent=intent, message="人物选择应使用查询中的槽位编号和人物 ID，请重新选择。")
    index = QueryIndex(workspace)
    records = [(mentions, [index.candidates(mention) for mention in mentions]) for mentions in alternatives]
    complete = [(mentions, candidates) for mentions, candidates in records if all(candidates)]
    if not complete:
        # Prefer an actual registered name when explaining a missing second name.
        mentions, candidates = max(records, key=lambda record: (
            sum(bool(candidates) for candidates in record[1]),
            sum(_normalized(mention) in index.names for mention in record[0])))
        missing = "、".join(f"“{mention}”" for mention, candidates in zip(mentions, candidates) if not candidates)
        return _reply("not_found", intent=intent, message=f"未找到人物{missing}；请使用画布中的姓名或括号内简称。")

    def combined_candidates(records, slot):
        return sorted({person_id for _, candidates in records for person_id in candidates[slot]}, key=index.person_order)

    compatible = [(mentions, candidates) for mentions, candidates in complete
                  if all(choice in candidates[int(slot)] for slot, choice in resolutions.items())]
    invalid_slots = set()
    if compatible:
        complete = compatible
    else:
        invalid_slots = {slot for slot, choice in resolutions.items() if choice not in combined_candidates(complete, int(slot))}
        if invalid_slots:
            complete = [(mentions, candidates) for mentions, candidates in complete
                        if all(choice in candidates[int(slot)] for slot, choice in resolutions.items() if slot not in invalid_slots)]
        else:
            # Each selected person exists, but the selected pair has no valid
            # textual split. Ask again rather than combining incompatible names.
            invalid_slots = set(resolutions)

    selected, ambiguities = {}, []
    for slot_number in range(slot_count):
        slot = str(slot_number)
        candidates = combined_candidates(complete, slot_number)
        mention = "／".join(dict.fromkeys(mentions[slot_number] for mentions, _ in complete))
        chosen = resolutions.get(slot)
        if chosen in candidates and slot not in invalid_slots:
            selected[slot] = chosen
        elif chosen is None and len(candidates) == 1:
            selected[slot] = candidates[0]
        else:
            ambiguities.append({"slot": slot, "mention": mention, "candidates": [index.candidate_details(person_id) for person_id in candidates]})
    fields = {}
    if str(source_slot) in selected:
        fields["source_id"] = selected[str(source_slot)]
    if target_slot is not None and str(target_slot) in selected:
        fields["target_id"] = selected[str(target_slot)]
    if spec is not None:
        fields["relationship_type"] = spec.kind
    if ambiguities:
        return _reply("needs_disambiguation", intent=intent, message="姓名或简称对应多位人物，或选择已不属于该姓名；请确认所有列出的槽位。", ambiguities=ambiguities, **fields)
    source = fields["source_id"]
    if intent == "pair":
        target = fields["target_id"]
        return _reply("success", intent=intent, results=[{"person_id": target, "name": index.people[target]["name"], "path_result": core.relationship_query(workspace, source, target)}], **fields)
    matches = []
    for target in index.people:
        if target == source or (spec.gender is not None and index.people[target]["gender"] != spec.gender):
            continue
        proofs = [proof for proof in index.evidence(source, target)
                  if (spec.tag or spec.kind) in proof["tags"] and (not spec.biological_only or proof["biological"])]
        if proofs:
            best = min(proofs, key=lambda proof: (proof["edges"], proof["label"]))
            matched_labels = list(dict.fromkeys(proof["label"] for proof in sorted(proofs, key=lambda proof: (proof["edges"], proof["label"]))))
            matches.append((best["edges"], best["label"], index.person_order(target), target, matched_labels))
    matches.sort()
    results = [{"person_id": target, "name": index.people[target]["name"], "matched_labels": matched_labels,
                "path_result": core.relationship_query(workspace, source, target)} for _, _, _, target, matched_labels in matches]
    message = "现有记录没有长幼信息，按相应兄弟姐妹或伯叔合称返回。" if spec.age_unknown else "已按登记亲子结构和日常亲戚称呼筛选。"
    if not results:
        message += " 当前没有匹配的登记结果。"
    return _reply("success", intent=intent, message=message, results=results, **fields)
