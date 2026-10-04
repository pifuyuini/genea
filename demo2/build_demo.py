"""Build the public seven-generation 《百年孤独》 Demo2 with fixed IDs and dates.

Only the curated parent-child records are included. Marriage, companionship and
care without an explicit adoption record remain in introductions, not edges.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import genealogy_core as core

SNAPSHOT = Path(__file__).resolve().parent / "data" / "workspace.json"
TIMESTAMP = "2026-10-04T00:00:00+00:00"
PORTRAIT_MANIFEST = Path(__file__).resolve().parent / "portraits" / "manifest.json"

AURELIANO_SONS = [
    ("a_triste", "奥雷里亚诺·特里斯特", "male", "Aureliano Triste。上校的十七名儿子之一，在马孔多建设制冰事业并推动铁路到来。"),
    ("a_centeno", "奥雷里亚诺·森特诺", "male", "Aureliano Centeno。上校的十七名儿子之一，与特里斯特一同经营制冰事业。"),
    ("a_serrador", "奥雷里亚诺·塞拉多尔", "male", "Aureliano Serrador。上校的十七名儿子之一；详名用于与家族中其他奥雷里亚诺区分。"),
    ("a_arcaya", "奥雷里亚诺·阿尔卡亚", "male", "Aureliano Arcaya。上校的十七名儿子之一；详名用于与家族中其他奥雷里亚诺区分。"),
    ("a_amador", "奥雷里亚诺·阿玛多", "male", "Aureliano Amador。上校的十七名儿子之一，在兄弟遭到追杀后幸存多年。"),
    *[(f"a_unknown_{index:02d}", f"奥雷里亚诺（未详名{index:02d}）", "male",
       f"Aureliano。上校的十七名儿子之一。原著未逐一记载这十二人的完整姓名；{index:02d}仅是演示消歧编号，不表示出生排行。各母不同，未建立共享的未知母亲节点。")
      for index in range(1, 13)],
]

# Display order keeps the principal family left and the seventeen sons to the right.
GENERATIONS = [
    ("第一代", [
        ("founder", "何塞·阿尔卡蒂奥·布恩迪亚", "male", "José Arcadio Buendía。与乌尔苏拉共同建立马孔多的家族创始人。两人也是表亲，但本演示不虚构他们未列出的祖先。"),
        ("ursula", "乌尔苏拉·伊瓜兰", "female", "Úrsula Iguarán。何塞·阿尔卡蒂奥·布恩迪亚的妻子与表亲，长期维系家族生活。她与丈夫收养丽贝卡。"),
        ("nicanor_ulloa", "尼卡诺尔·乌略亚", "male", "Nicanor Ulloa。丽贝卡的亲生父亲，与布恩迪亚夫妇的养亲身份分开登记。"),
        ("rebeca_montiel", "丽贝卡·蒙铁尔", "female", "Rebeca Montiel。丽贝卡的亲生母亲；同名母女使用各自完整姓名消歧。"),
        ("apolinar", "阿波利纳尔·莫斯科特", "male", "Apolinar Moscote。莫斯科特家的父亲，蕾梅黛丝与安帕罗的父亲，在马孔多担任行政官。"),
    ]),
    ("第二代", [
        ("jose_arcadio", "何塞·阿尔卡蒂奥", "male", "José Arcadio。创始夫妇的儿子，与庇拉尔生下阿尔卡蒂奥，后来与养妹丽贝卡结婚；婚姻仅在简介中说明。"),
        ("colonel", "奥雷里亚诺·布恩迪亚上校", "male", "Coronel Aureliano Buendía。创始夫妇的儿子，与庇拉尔生下奥雷里亚诺·何塞，另与不同母亲有十七名儿子。妻子是蕾梅黛丝·莫斯科特。"),
        ("amaranta", "阿玛兰妲", "female", "Amaranta。创始夫妇的女儿，奥雷里亚诺·何塞的姑母。蕾梅黛丝去世后她收养了他，养母称谓与姑母血亲依据分别保留。"),
        ("rebeca", "丽贝卡", "female", "Rebeca。尼卡诺尔·乌略亚与丽贝卡·蒙铁尔的女儿，由布恩迪亚夫妇收养，后来与何塞·阿尔卡蒂奥结婚。"),
        ("pilar", "庇拉尔·特尔内拉", "female", "Pilar Ternera。阿尔卡蒂奥与奥雷里亚诺·何塞的母亲，两人的父亲分别为何塞·阿尔卡蒂奥与上校。"),
        ("remedios_moscote", "蕾梅黛丝·莫斯科特", "female", "Remedios Moscote。阿波利纳尔的女儿、上校的妻子，接纳奥雷里亚诺·何塞为长子；她去世后阿玛兰妲收养了他。"),
        ("amparo", "安帕罗·莫斯科特", "female", "Amparo Moscote。阿波利纳尔的女儿、蕾梅黛丝的姐妹，与布恩迪亚家往来。"),
    ]),
    ("第三代", [
        ("arcadio", "阿尔卡蒂奥", "male", "Arcadio。何塞·阿尔卡蒂奥与庇拉尔的儿子，与桑塔索菲亚生下美人儿蕾梅黛丝和双胞胎兄弟。"),
        ("aureliano_jose", "奥雷里亚诺·何塞", "male", "Aureliano José。上校与庇拉尔的儿子。先由蕾梅黛丝认作长子，后来由阿玛兰妲收养；阿玛兰妲同时是他的姑母。"),
        ("santa_sofia", "桑塔索菲亚·德拉·彼达", "female", "Santa Sofía de la Piedad。阿尔卡蒂奥的伴侣，美人儿蕾梅黛丝及何塞第二、奥雷里亚诺第二的母亲。"),
        ("fernando", "费尔南多·德尔·卡皮奥", "male", "Fernando del Carpio。费尔南达的父亲，出身家道衰落的德尔·卡皮奥家庭。"),
        ("renata_argote", "蕾娜塔·阿尔戈特", "female", "Renata Argote。费尔南达的母亲，与费尔南多共同登记为她的亲生父母。"),
        *AURELIANO_SONS,
    ]),
    ("第四代", [
        ("remedios_beauty", "美人儿蕾梅黛丝", "female", "Remedios la Bella。阿尔卡蒂奥与桑塔索菲亚的女儿；以‘美人儿’区别于第二代的蕾梅黛丝·莫斯科特。"),
        ("jose_segundo", "何塞·阿尔卡蒂奥第二", "male", "José Arcadio Segundo。阿尔卡蒂奥与桑塔索菲亚的儿子，奥雷里亚诺第二的双胞胎兄弟，经历香蕉公司工人的命运。"),
        ("aureliano_segundo", "奥雷里亚诺第二", "male", "Aureliano Segundo。阿尔卡蒂奥与桑塔索菲亚的儿子，费尔南达的丈夫，三个第五代孩子的父亲；与佩特拉的伴侣关系只写在简介中。"),
        ("fernanda", "费尔南达·德尔·卡皮奥", "female", "Fernanda del Carpio。费尔南多与蕾娜塔的女儿，与奥雷里亚诺第二生下何塞第五代、梅梅和阿玛兰妲·乌尔苏拉。"),
        ("petra", "佩特拉·科特斯", "female", "Petra Cotes。曾与双胞胎兄弟往来，长期与奥雷里亚诺第二相伴；伴侣关系仅保留在简介中，不编造亲子边。"),
    ]),
    ("第五代", [
        ("jose_arcadio_v", "何塞·阿尔卡蒂奥（第五代）", "male", "José Arcadio。奥雷里亚诺第二与费尔南达的儿子，以第五代标注区别于同名祖辈。"),
        ("meme", "蕾娜塔·蕾梅黛丝（梅梅）", "female", "Renata Remedios（Meme）。奥雷里亚诺第二与费尔南达的女儿，与毛里西奥生下奥雷里亚诺·巴比伦。"),
        ("amaranta_ursula", "阿玛兰妲·乌尔苏拉", "female", "Amaranta Úrsula。奥雷里亚诺第二与费尔南达的女儿，加斯通的妻子，后来与外甥奥雷里亚诺·巴比伦生下末代奥雷里亚诺。她的母子边跨越第五至第七行。"),
        ("mauricio", "毛里西奥·巴比伦", "male", "Mauricio Babilonia。梅梅的恋人、奥雷里亚诺·巴比伦的父亲；西语全名用于区别父子。"),
        ("gaston", "加斯通", "male", "Gastón。阿玛兰妲·乌尔苏拉的丈夫；本演示不加入夫妻边或未具名孩子，因此他可以是孤立节点。"),
    ]),
    ("第六代", [
        ("aureliano_babilonia", "奥雷里亚诺·巴比伦", "male", "Aureliano Babilonia。梅梅与毛里西奥的儿子，阿玛兰妲·乌尔苏拉的外甥及末代奥雷里亚诺的父亲，最终读懂家族手稿。"),
    ]),
    ("第七代", [
        ("aureliano_last", "奥雷里亚诺（末代）", "male", "Aureliano。奥雷里亚诺·巴比伦与阿玛兰妲·乌尔苏拉的儿子，布恩迪亚家族的末代孩子；独立姓名标注用于与十七子及上校区分。"),
    ]),
]

BIOLOGICAL = {
    "founder": ["jose_arcadio", "colonel", "amaranta"],
    "ursula": ["jose_arcadio", "colonel", "amaranta"],
    "nicanor_ulloa": ["rebeca"], "rebeca_montiel": ["rebeca"],
    "apolinar": ["remedios_moscote", "amparo"],
    "jose_arcadio": ["arcadio"], "pilar": ["arcadio", "aureliano_jose"],
    "colonel": ["aureliano_jose", *[person[0] for person in AURELIANO_SONS]],
    "arcadio": ["remedios_beauty", "jose_segundo", "aureliano_segundo"],
    "santa_sofia": ["remedios_beauty", "jose_segundo", "aureliano_segundo"],
    "fernando": ["fernanda"], "renata_argote": ["fernanda"],
    "aureliano_segundo": ["jose_arcadio_v", "meme", "amaranta_ursula"],
    "fernanda": ["jose_arcadio_v", "meme", "amaranta_ursula"],
    "meme": ["aureliano_babilonia"], "mauricio": ["aureliano_babilonia"],
    "aureliano_babilonia": ["aureliano_last"], "amaranta_ursula": ["aureliano_last"],
}
ADOPTION = {
    ("founder", "rebeca"): ("养父", "养女"),
    ("ursula", "rebeca"): ("养母", "养女"),
    ("remedios_moscote", "aureliano_jose"): ("养母", "养子"),
    ("amaranta", "aureliano_jose"): ("养母", "养子"),
}


def build() -> dict:
    manifest = json.loads(PORTRAIT_MANIFEST.read_text(encoding="utf-8"))
    photos = {person["person_id"]: "/photos/" + person["output_file"]
              for sheet in manifest["sheets"] for person in sheet["portraits"]}
    pending = []
    original_new_id, original_now = core.new_id, core.now
    core.new_id = lambda prefix: f"{prefix}_{pending.pop(0)}"
    core.now = lambda: TIMESTAMP
    try:
        workspace = core.default_workspace()
        previous = None
        for index, (title, members) in enumerate(GENERATIONS, start=1):
            pending.append(f"demo2_{index:02d}")
            generation = core.add_generation(workspace, "below" if previous else "first", previous, title,
                                             allow_cross_generation=True)
            previous = generation["id"]
            for order, (key, name, gender, introduction) in enumerate(members):
                pending.append(key)
                core.add_person(workspace, {"generation_id": previous, "name": name, "gender": gender,
                                           "introduction": introduction, "order": order, "photo_path": photos[f"person_{key}"]})
        for parent, children in BIOLOGICAL.items():
            for child in children:
                pending.append(f"{parent}__{child}")
                core.add_relationship(workspace, f"person_{parent}", f"person_{child}", allow_cross_generation=True)
        for (parent, child), (parent_label, child_label) in ADOPTION.items():
            pending.append(f"{parent}__{child}")
            relationship = core.add_relationship(workspace, f"person_{parent}", f"person_{child}", allow_cross_generation=True)
            core.update_relationship(workspace, relationship["id"], {"kind": "special", "parent_label": parent_label, "child_label": child_label})
        return core.ensure_workspace(workspace)
    finally:
        core.new_id, core.now = original_new_id, original_now


def render(workspace: dict) -> str:
    return json.dumps(workspace, ensure_ascii=False, indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify the committed deterministic snapshot")
    args = parser.parse_args(argv)
    text = render(build())
    if args.check:
        current = SNAPSHOT.read_text(encoding="utf-8") if SNAPSHOT.exists() else ""
        if current != text:
            print("demo2/data/workspace.json is out of date; run: .venv/bin/python -B demo2/build_demo.py")
            return 1
        print("Demo2 snapshot is up to date")
        return 0
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(text, encoding="utf-8")
    workspace = json.loads(text)
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}: {len(workspace['generations'])} generations, {len(workspace['people'])} people, {len(workspace['relationships'])} relationships")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
