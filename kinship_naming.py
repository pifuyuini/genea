"""Name proven kinship paths without running an external relationship parser.

The bundled MIT lexicon supplies aliases only. Kinship inference first proves
an upward/downward path; this module encodes that path and selects a readable,
gender-specific, age-neutral term. Names never participate in naming decisions.
"""
from __future__ import annotations

import json
from pathlib import Path


_TERMS: dict[str, list[str]] = json.loads(
    (Path(__file__).resolve().parent / "resources" / "kinship" / "terms.json").read_text(encoding="utf-8")
)

# Familiar formal names resolve a few alias ambiguities, rather than replacing
# the lexicon with a second catalogue. Each preference must occur in the data.
_PREFERRED = {
    "f,f,f": "曾祖父", "f,f,m": "曾祖母",
    "f,f,f,f": "高祖父", "f,f,f,m": "高祖母",
    "s,s,s": "曾孙", "s,s,d": "曾孙女",
    "s,s,s,s": "玄孙", "s,s,s,d": "玄孙女",
    "f,f,f,f,xb,s": "堂曾祖父",
    "f,f,f,xb,s": "堂祖父",
    "f,f,xb,s": "堂伯叔父",
    "f,f,f,f,xb": "伯叔高祖父",
}

_UP = {
    ("f",): "父亲", ("m",): "母亲",
    ("f", "f"): "祖父", ("f", "m"): "祖母",
    ("m", "f"): "外祖父", ("m", "m"): "外祖母",
    ("f", "f", "f"): "曾祖父", ("f", "f", "m"): "曾祖母",
    ("f", "f", "f", "f"): "高祖父", ("f", "f", "f", "m"): "高祖母",
}
_DOWN = {
    ("s",): "儿子", ("d",): "女儿",
    ("s", "s"): "孙子", ("s", "d"): "孙女",
    ("d", "s"): "外孙子", ("d", "d"): "外孙女",
    ("s", "s", "s"): "曾孙", ("s", "s", "d"): "曾孙女",
    ("s", "s", "s", "s"): "玄孙", ("s", "s", "s", "d"): "玄孙女",
}


def _parent_token(people: dict, person_id: str) -> str:
    return "f" if people[person_id]["gender"] == "male" else "m"


def _child_token(people: dict, person_id: str) -> str:
    return "s" if people[person_id]["gender"] == "male" else "d"


def canonical_selector(people: dict, source_path: tuple[str, ...], target_path: tuple[str, ...]) -> str:
    """Encode the already proven two-arm path, with exactly one sibling turn."""
    if len(target_path) == 1:
        tokens = [_parent_token(people, person_id) for person_id in source_path[1:]]
    elif len(source_path) == 1:
        tokens = [_child_token(people, person_id) for person_id in reversed(target_path[:-1])]
    else:
        tokens = [_parent_token(people, person_id) for person_id in source_path[1:-1]]
        tokens.append("xb" if people[target_path[-2]]["gender"] == "male" else "xs")
        tokens.extend(_child_token(people, person_id) for person_id in reversed(target_path[:-2]))
    return ",".join(tokens)


def _lineal(tokens: tuple[str, ...], vocabulary: dict[tuple[str, ...], str]) -> str:
    """Compress familiar lineal segments, preserving every parent/child edge."""
    parts = []
    offset = 0
    while offset < len(tokens):
        for length in range(min(4, len(tokens) - offset), 0, -1):
            segment = tokens[offset:offset + length]
            if segment in vocabulary:
                parts.append(vocabulary[segment])
                offset += length
                break
    return "的".join(parts)


def structural_relationship(people: dict, source_path: tuple[str, ...], target_path: tuple[str, ...], *, concise: bool = True) -> str:
    """Readable fallback, with the unknown age attached to the actual turn.

    Two long arms can be shortened around their first-cousin segment, e.g.
    '曾祖父的堂兄弟（长幼未知）'. The unabbreviated form is still available as
    '高祖父的兄弟（长幼未知）的儿子'; both preserve the correct generations.
    """
    up, down = len(source_path) - 1, len(target_path) - 1
    if down == 0:
        return _lineal(tuple(_parent_token(people, person_id) for person_id in source_path[1:]), _UP)
    if up == 0:
        return _lineal(tuple(_child_token(people, person_id) for person_id in reversed(target_path[:-1])), _DOWN)
    if concise and up >= 2 and down >= 2:
        ancestor = _lineal(tuple(_parent_token(people, person_id) for person_id in source_path[1:-2]), _UP)
        left_male = people[source_path[-2]]["gender"] == "male"
        right_male = people[target_path[-2]]["gender"] == "male"
        branch = {(True, True): "堂", (True, False): "姑表", (False, True): "舅表", (False, False): "姨表"}[(left_male, right_male)]
        cousin = branch + ("兄弟" if people[target_path[-3]]["gender"] == "male" else "姐妹") + "（长幼未知）"
        descendant = _lineal(tuple(_child_token(people, person_id) for person_id in reversed(target_path[:-3])), _DOWN)
        return "的".join(part for part in (ancestor, cousin, descendant) if part)
    ancestor = _lineal(tuple(_parent_token(people, person_id) for person_id in source_path[1:-1]), _UP)
    sibling = ("兄弟" if people[target_path[-2]]["gender"] == "male" else "姐妹") + "（长幼未知）"
    descendant = _lineal(tuple(_child_token(people, person_id) for person_id in reversed(target_path[:-2])), _DOWN)
    return "的".join(part for part in (ancestor, sibling, descendant) if part)


def _formal_alias(alias: str, target_male: bool) -> bool:
    # Exclude regional/familiar forms and honorifics, rather than trusting alias
    # ordering. The lexicon itself intentionally preserves those alternatives.
    if any(part in alias for part in ("爷", "奶", "公", "婆", "爹", "娘", "爸", "妈", "姥", "毑", "嬷", "姆", "嗲", "娭", "仔", "翁", "几", "房", "家", "息", "同胞", "亲")):
        return False
    neutral = alias.replace("伯叔", "").replace("叔伯", "").replace("兄弟", "").replace("姐妹", "").replace("姊妹", "")
    if any(part in neutral for part in ("伯", "叔", "兄", "弟", "姐", "妹", "姊")):
        return False
    if target_male:
        return alias.endswith(("父", "孙", "子", "兄弟", "侄", "甥"))
    return alias.endswith(("母", "女", "姐妹", "姊妹", "姑", "姨"))


def _alias_rank(alias: str) -> tuple[int, int, int, int, str]:
    ending = 0 if alias.endswith(("父", "母", "孙", "女", "子", "兄弟", "姐妹", "姊妹")) else 1
    prefix = 0 if alias.startswith(("堂", "表", "外", "曾", "高", "玄", "从堂", "从表")) else 1
    uncommon = 1 if any(part in alias for part in ("元孙", "重孙")) else 0
    return ending, prefix, uncommon, len(alias), alias


def _unknown_age(term: str) -> str:
    if any(part in term for part in ("伯叔", "叔伯", "兄弟", "姐妹", "姊妹")):
        return term + "（长幼未知）"
    return term


def name_distant_relationship(people: dict, source_path: tuple[str, ...], target_path: tuple[str, ...]) -> str:
    selector = canonical_selector(people, source_path, target_path)
    aliases = _TERMS.get(selector, ())
    preferred = _PREFERRED.get(selector)
    if preferred in aliases:
        return _unknown_age(preferred)
    target_male = people[target_path[0]]["gender"] == "male"
    candidates = {alias for alias in aliases if _formal_alias(alias, target_male)}
    if candidates:
        return _unknown_age(min(candidates, key=_alias_rank))
    return structural_relationship(people, source_path, target_path)
