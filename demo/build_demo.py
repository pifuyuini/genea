"""Build the public Genea demo workspace: the Jia clan of *Dream of the Red Chamber* (《红楼梦》).

The workspace is assembled through genealogy_core so every relationship passes the same validation as the app.
IDs and timestamps are fixed, so rebuilding produces an identical, diff-friendly demo/data/workspace.json.

Usage:  python3 demo/build_demo.py            # rewrite demo/data/workspace.json
        python3 demo/build_demo.py --check    # exit 1 if the committed snapshot is out of date
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import genealogy_core as core  # noqa: E402

SNAPSHOT = Path(__file__).resolve().parent / "data" / "workspace.json"
TIMESTAMP = "2026-09-29T00:00:00+00:00"
PLACEHOLDER = "原著未载名讳，此处为连接家族关系而设的节点。"

# (key, name, gender, introduction) per generation row, in display order.
GENERATIONS = [
    ("始祖", [
        ("shizu", "贾氏始祖", "male", "宁国公与荣国公是一母同胞的兄弟。" + PLACEHOLDER),
    ]),
    ("水字辈", [
        ("yan", "贾演", "male", "宁国公，宁国府一支的开创者。"),
        ("yuan", "贾源", "male", "荣国公，荣国府一支的开创者。"),
    ]),
    ("代字辈", [
        ("daihua", "贾代化", "male", "宁国公之子，承袭宁府家业。"),
        ("daishan", "贾代善", "male", "荣国公之子，娶金陵史侯家的小姐为妻。"),
        ("jiamu", "贾母", "female", "史太君，出身金陵史家，荣国府的老祖宗。"),
        ("wanggong", "王公", "male", "金陵王家长辈，王夫人与薛姨妈之父。" + PLACEHOLDER),
    ]),
    ("文字辈", [
        ("fu", "贾敷", "male", "贾代化长子，八九岁时夭亡。"),
        ("jing", "贾敬", "male", "贾代化次子，中过进士，后在城外道观修道。"),
        ("xingfuren", "邢夫人", "female", "贾赦的继室。"),
        ("she", "贾赦", "male", "贾代善长子，袭一等将军之职。"),
        ("min", "贾敏", "female", "贾母之女，嫁与林如海，早逝。"),
        ("ruhai", "林如海", "male", "巡盐御史，林黛玉之父。"),
        ("zheng", "贾政", "male", "贾代善次子，任工部员外郎，为人端方正直。"),
        ("wangfuren", "王夫人", "female", "贾政之妻，出身金陵王家。"),
        ("zhaoyiniang", "赵姨娘", "female", "贾政之妾，探春与贾环的生母。"),
        ("xueyima", "薛姨妈", "female", "王夫人之妹，携子女寄居贾府梨香院。"),
    ]),
    ("玉字辈", [
        ("zhen", "贾珍", "male", "贾敬之子，袭三品威烈将军，宁国府的当家人。"),
        ("youshi", "尤氏", "female", "贾珍的继室，贾蓉的继母，主持宁府内务。"),
        ("xichun", "贾惜春", "female", "贾敬之女，贾府四春中最小的一位，擅长作画。"),
        ("yingchun", "贾迎春", "female", "贾赦之女，姨娘所出，性情懦弱，人称“二木头”。"),
        ("lian", "贾琏", "male", "贾赦之子，与王熙凤一同料理荣府事务。"),
        ("xifeng", "王熙凤", "female", "贾琏之妻，王夫人的内侄女，精明强干的荣府管家奶奶。"),
        ("daiyu", "林黛玉", "female", "林如海与贾敏之女，自幼寄居贾府，与宝玉青梅竹马。"),
        ("liwan", "李纨", "female", "贾珠之妻，贾珠早逝后守节教子。"),
        ("zhu", "贾珠", "male", "贾政长子，不到二十岁便病故。"),
        ("yuanchun", "贾元春", "female", "贾政长女，入宫受封贤德妃。"),
        ("baoyu", "贾宝玉", "male", "贾政次子，衔玉而生，大观园中的“怡红公子”。"),
        ("tanchun", "贾探春", "female", "贾政之女，赵姨娘所出，精明能干，曾协理荣府。"),
        ("huan", "贾环", "male", "贾政之子，赵姨娘所出。"),
        ("baochai", "薛宝钗", "female", "薛姨妈之女，端庄博学，佩戴金锁。"),
        ("xuepan", "薛蟠", "male", "薛姨妈之子，人称“呆霸王”。"),
        ("qinye", "秦业", "male", "营缮郎，秦钟之父，秦可卿的养父。"),
    ]),
    ("草字辈", [
        ("rong", "贾蓉", "male", "贾珍之子。"),
        ("qiaojie", "巧姐", "female", "贾琏与王熙凤之女，名字由刘姥姥所取。"),
        ("lan", "贾兰", "male", "贾珠与李纨之子。"),
        ("keqing", "秦可卿", "female", "秦业从养生堂抱养的女儿，嫁与贾蓉为妻。"),
        ("qinzhong", "秦钟", "male", "秦业之子，宝玉的同窗好友。"),
    ]),
]

# Parent → children. Spouses are implied by shared children (the model records parent-child links only).
RELATIONSHIPS = {
    "shizu": ["yan", "yuan"],
    "yan": ["daihua"],
    "yuan": ["daishan"],
    "daihua": ["fu", "jing"],
    "daishan": ["she", "zheng", "min"],
    "jiamu": ["she", "zheng", "min"],
    "wanggong": ["wangfuren", "xueyima"],
    "jing": ["zhen", "xichun"],
    "she": ["lian", "yingchun"],
    "zheng": ["zhu", "yuanchun", "baoyu", "tanchun", "huan"],
    "wangfuren": ["zhu", "yuanchun", "baoyu", "tanchun"],
    "zhaoyiniang": ["tanchun", "huan"],
    "min": ["daiyu"],
    "ruhai": ["daiyu"],
    "xueyima": ["xuepan", "baochai"],
    "xingfuren": ["yingchun"],
    "zhen": ["rong"],
    "youshi": ["rong"],
    "lian": ["qiaojie"],
    "xifeng": ["qiaojie"],
    "zhu": ["lan"],
    "liwan": ["lan"],
    "qinye": ["qinzhong", "keqing"],
}
# Relationships that use custom titles instead of the gender-derived 爸爸 / 妈妈 / 儿子 / 女儿.
SPECIAL = {
    ("xingfuren", "yingchun"): ("嫡母", "庶女"),
    ("wangfuren", "tanchun"): ("嫡母", "庶女"),
    ("youshi", "rong"): ("继母", "继子"),
    ("qinye", "keqing"): ("养父", "养女"),
}


def build() -> dict:
    """Return the demo workspace, built with the same rules the app enforces."""
    pending: list[str] = []
    original_new_id, original_now = core.new_id, core.now
    core.new_id = lambda prefix: f"{prefix}_{pending.pop(0)}"
    core.now = lambda: TIMESTAMP
    try:
        workspace = core.default_workspace()
        previous = None
        for index, (title, members) in enumerate(GENERATIONS, start=1):
            pending.append(f"{index:02d}")
            generation = core.add_generation(workspace, "below" if previous else "first", previous, title)
            previous = generation["id"]
            for order, (key, name, gender, introduction) in enumerate(members):
                pending.append(key)
                core.add_person(workspace, {"generation_id": previous, "name": name, "gender": gender,
                                            "introduction": introduction, "order": order,
                                            "photo_path": f"/photos/photo_{key}.jpg"})
        for parent, children in RELATIONSHIPS.items():
            for child in children:
                pending.append(f"{parent}__{child}")
                relationship = core.add_relationship(workspace, f"person_{parent}", f"person_{child}")
                if (parent, child) in SPECIAL:
                    parent_label, child_label = SPECIAL[(parent, child)]
                    core.update_relationship(workspace, relationship["id"],
                                             {"kind": "special", "parent_label": parent_label, "child_label": child_label})
        return core.ensure_workspace(workspace)
    finally:
        core.new_id, core.now = original_new_id, original_now


def render(workspace: dict) -> str:
    return json.dumps(workspace, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    text = render(build())
    if "--check" in sys.argv[1:]:
        current = SNAPSHOT.read_text(encoding="utf-8") if SNAPSHOT.exists() else ""
        if current != text:
            print("demo/data/workspace.json is out of date; run: python3 demo/build_demo.py")
            return 1
        print("demo snapshot is up to date")
        return 0
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(text, encoding="utf-8")
    workspace = json.loads(text)
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}: {len(workspace['generations'])} generations, "
          f"{len(workspace['people'])} people, {len(workspace['relationships'])} relationships")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
