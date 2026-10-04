// Python supplies expected responses on stdin; test the actual browser grammar and data.
load("demo2/query-engine.js");
const queryData = JSON.parse(readFile("docs/demo2/queries.json"));
const paths = JSON.parse(readFile("docs/demo2/paths.json"));
const cases = JSON.parse(readline());
let checks = 0;
function equal(actual, expected) {
  if (actual === expected) return true;
  if (actual === null || expected === null || typeof actual !== "object" || typeof expected !== "object") return false;
  if (Array.isArray(actual) !== Array.isArray(expected)) return false;
  const a = Object.keys(actual).sort(), b = Object.keys(expected).sort();
  return JSON.stringify(a) === JSON.stringify(b) && a.every((key) => equal(actual[key], expected[key]));
}
function assert(condition, message) { checks += 1; if (!condition) throw new Error(message); }
for (const item of cases) {
  const actual = GeneaDemoQuery.run(queryData, paths, item.text, item.resolutions);
  const projected = Object.assign({}, actual, {
    results: actual.results.map((row) => {
      assert(equal(row.path_result, paths[actual.source_id][row.person_id]), "Returned path differs from the Python pair table: " + item.text);
      const value = Object.assign({}, row); delete value.path_result; return value;
    }),
  });
  assert(equal(projected, item.expected), "Python/browser response differs: " + item.text + "\nActual: " + JSON.stringify(projected) + "\nExpected: " + JSON.stringify(item.expected));
}
print("PASS " + cases.length + " Python/browser query cases; " + checks + " assertions");
