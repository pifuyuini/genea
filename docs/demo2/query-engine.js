/* Bounded public-demo grammar; all relationship evidence is precomputed by Python. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.GeneaDemoQuery = api;
})(globalThis, function () {
  "use strict";
  const EXAMPLES = "可试：贾珍和薛蟠是什么关系；贾母的孙辈有哪些；奥雷里亚诺上校的子女有哪些。";
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const normalize = (value) => String(value).normalize("NFKC").replace(/[·•・･‧.．]/g, " ").toLowerCase().replace(/ß/g, "ss").replace(/ς/g, "σ").replace(/\s/g, "");
  const mention = (value) => value.trim().replace(/^["'“”‘’「」『』，,:：]+|["'“”‘’「」『』，,:：]+$/g, "").trim();
  function pairMentions(value) {
    const closingQuotes = { "“": "”", "‘": "’", "「": "」", "『": "』", '"': '"', "'": "'" };
    let closing = null;
    const alternatives = [];
    for (let position = 0; position < value.length; position += 1) {
      const character = value[position];
      if (closing !== null) {
        if (character === closing) closing = null;
        continue;
      }
      if (closingQuotes[character]) closing = closingQuotes[character];
      else if ("和与跟".includes(character)) {
        const names = [mention(value.slice(0, position)), mention(value.slice(position + 1))];
        if (names.every(Boolean)) alternatives.push(names);
      }
    }
    return alternatives;
  }
  function parse(text) {
    let value = text.normalize("NFKC").trim().replace(/[?？!！。 \t\n]+$/g, "");
    for (const prefix of ["帮我查一下", "请告诉我", "请问", "查询", "查找", "找出", "查一下"]) {
      if (value.startsWith(prefix)) {
        value = value.slice(prefix.length).replace(/^[，,:： ]+/, "");
        break;
      }
    }
    let match = value.match(/^(.+?)是(.+?)的(?:什么人|什么亲戚|什么关系)$/);
    if (match) return { intent: "pair", alternatives: [[mention(match[1]), mention(match[2])]], sourceSlot: 1, targetSlot: 0 };
    match = value.match(/^(.+?)(?:之间)?(?:是什么关系|是何关系|有什么关系|是什么亲戚|的关系|什么关系)$/);
    if (match) {
      const alternatives = pairMentions(match[1]);
      if (alternatives.length) return { intent: "pair", alternatives, sourceSlot: 0, targetSlot: 1 };
    }
    match = value.match(/^(.+)的(.+?)(?:有哪些人|有哪些|都有谁|有谁|是谁|名单)?$/);
    if (match) return { intent: "relatives", alternatives: [[mention(match[1])]], relativeWord: match[2].trim(), sourceSlot: 0, targetSlot: null };
    return null;
  }
  function reply(status, fields) {
    return Object.assign({ status, ambiguities: [], results: [] }, fields || {});
  }
  function compareProof(a, b) {
    return a.edges - b.edges || (a.label < b.label ? -1 : a.label > b.label ? 1 : 0);
  }
  function run(data, paths, text, resolutions) {
    if (typeof text !== "string" || !text.trim()) return reply("unsupported", { message: "请填写人物关系问题。" + EXAMPLES });
    const parsed = parse(text);
    if (!parsed) return reply("unsupported", { message: "暂不支持这个问法。" + EXAMPLES });
    const { intent, alternatives, relativeWord, sourceSlot, targetSlot } = parsed;
    const slotCount = alternatives[0].length;
    let spec = null;
    if (intent === "relatives") {
      spec = data.relative_types[relativeWord];
      if (!spec) return reply("unsupported", { intent, message: "暂不支持此类筛选；可查询父母、子女、孙辈、兄弟姐妹、堂表亲或养亲。" + EXAMPLES });
    }
    if (resolutions === undefined || resolutions === null) resolutions = {};
    if (typeof resolutions !== "object" || Array.isArray(resolutions) ||
        Object.entries(resolutions).some(([slot, id]) => !Array.from({ length: slotCount }, (_, i) => String(i)).includes(slot) || typeof id !== "string")) {
      return reply("unsupported", { intent, message: "人物选择应使用查询中的槽位编号和人物 ID，请重新选择。" });
    }
    const persons = new Map(data.people.map((person) => [person.id, person]));
    const order = (a, b) => persons.get(a).rank - persons.get(b).rank;
    const candidates = (name) => {
      const normalized = normalize(name);
      if (!normalized) return [];
      const exact = data.people.filter((person) => person.normalized_name === normalized);
      return (exact.length ? exact : data.people.filter((person) =>
        person.aliases.includes(normalized) || person.normalized_name.includes(normalized))).map((person) => person.id).sort(order);
    };
    const details = (id) => {
      const { name, generation, gender, introduction } = persons.get(id);
      return { id, name, generation, gender, introduction };
    };
    const records = alternatives.map((names) => ({ names, candidates: names.map(candidates) }));
    let complete = records.filter((record) => record.candidates.every((ids) => ids.length));
    if (!complete.length) {
      const score = (record) => [
        record.candidates.filter((ids) => ids.length).length,
        record.names.filter((name) => data.people.some((person) => person.normalized_name === normalize(name))).length,
      ];
      const best = records.reduce((a, b) => {
        const first = score(a), second = score(b);
        return second[0] > first[0] || (second[0] === first[0] && second[1] > first[1]) ? b : a;
      });
      const missing = best.names.filter((_, i) => !best.candidates[i].length).map((name) => "“" + name + "”").join("、");
      return reply("not_found", { intent, message: "未找到人物" + missing + "；请使用画布中的姓名或括号内简称。" });
    }
    const combined = (rows, slot) => [...new Set(rows.flatMap((row) => row.candidates[slot]))].sort(order);
    const compatible = complete.filter((record) => Object.entries(resolutions).every(([slot, id]) => record.candidates[Number(slot)].includes(id)));
    let invalidSlots = new Set();
    if (compatible.length) complete = compatible;
    else {
      invalidSlots = new Set(Object.entries(resolutions).filter(([slot, id]) => !combined(complete, Number(slot)).includes(id)).map(([slot]) => slot));
      if (invalidSlots.size) {
        complete = complete.filter((record) => Object.entries(resolutions).every(([slot, id]) => invalidSlots.has(slot) || record.candidates[Number(slot)].includes(id)));
      } else invalidSlots = new Set(Object.keys(resolutions));
    }
    const selected = {}, ambiguities = [];
    for (let number = 0; number < slotCount; number += 1) {
      const slot = String(number), ids = combined(complete, number), chosen = resolutions[slot];
      if (ids.includes(chosen) && !invalidSlots.has(slot)) selected[slot] = chosen;
      else if (chosen === undefined && ids.length === 1) selected[slot] = ids[0];
      else ambiguities.push({ slot, mention: [...new Set(complete.map((row) => row.names[number]))].join("／"), candidates: ids.map(details) });
    }
    const fields = { intent };
    if (selected[String(sourceSlot)]) fields.source_id = selected[String(sourceSlot)];
    if (targetSlot !== null && selected[String(targetSlot)]) fields.target_id = selected[String(targetSlot)];
    if (spec) fields.relationship_type = spec.kind;
    if (ambiguities.length) return reply("needs_disambiguation", Object.assign(fields, {
      message: "姓名或简称对应多位人物，或选择已不属于该姓名；请确认所有列出的槽位。", ambiguities,
    }));
    const source = fields.source_id;
    if (intent === "pair") {
      const target = fields.target_id;
      return reply("success", Object.assign(fields, { results: [{ person_id: target, name: persons.get(target).name, path_result: clone(paths[source][target]) }] }));
    }
    const matches = [];
    for (const person of data.people) {
      if (person.id === source || (spec.gender !== null && person.gender !== spec.gender)) continue;
      const proofs = (data.evidence[source][person.id] || []).filter((proof) =>
        proof.tags.includes(spec.tag || spec.kind) && (!spec.biological_only || proof.biological)).sort(compareProof);
      if (!proofs.length) continue;
      matches.push({
        id: person.id, edges: proofs[0].edges, label: proofs[0].label,
        matched_labels: [...new Set(proofs.map((proof) => proof.label))],
      });
    }
    matches.sort((a, b) => compareProof(a, b) || order(a.id, b.id));
    const results = matches.map((item) => ({
      person_id: item.id, name: persons.get(item.id).name, matched_labels: item.matched_labels,
      path_result: clone(paths[source][item.id]),
    }));
    let message = spec.age_unknown ? "现有记录没有长幼信息，按相应兄弟姐妹或伯叔合称返回。" : "已按登记亲子结构和日常亲戚称呼筛选。";
    if (!results.length) message += " 当前没有匹配的登记结果。";
    return reply("success", Object.assign(fields, { message, results }));
  }
  return { run, parse, normalize };
});
