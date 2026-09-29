/* Run on macOS: jsc static/motion.js tests/test_motion.js */
let clock = 0, nextFrame = 0, reduced = false;
const frames = new Map();
function requestAnimationFrame(callback) { const id = ++nextFrame; frames.set(id, callback); return id; }
function cancelAnimationFrame(id) { frames.delete(id); }
function matchMedia() { return { matches: reduced }; }
function tick(milliseconds = 16.667) {
  clock += milliseconds;
  const current = [...frames.values()];
  frames.clear();
  current.forEach((callback) => callback(clock));
}
function settle() { for (let n = 0; frames.size && n < 300; n += 1) tick(); assert(!frames.size, "spring should settle"); }
function assert(value, message) { if (!value) throw new Error(message); }
let passed = 0;
function test(name, action) {
  frames.clear(); clock = 0; reduced = false;
  action(); passed += 1; print("PASS " + name);
}
test("settles without overshoot", () => {
  let value = { x: 0 }, finishes = 0;
  const spring = createValueSpring(() => value, (next) => { assert(next.x >= value.x && next.x <= 100, "monotonic"); value = next; }, () => finishes++);
  spring.to({ x: 100 }); settle();
  assert(value.x === 100 && finishes === 1 && !spring.running, "exact final value and one completion");
});
test("retarget uses current presentation without a jump", () => {
  let value = { x: 0 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: 100 }); tick(); tick();
  const before = value.x;
  spring.to({ x: -50 });
  assert(value.x === before, "retarget is continuous");
  settle(); assert(value.x === -50, "new target");
});
test("retarget preserves velocity", () => {
  let value = { x: 0 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: 100 }); tick(); tick();
  const before = value.x;
  spring.to({ x: before }); tick(1);
  assert(value.x > before, "momentum is preserved, not reset");
  settle(); assert(value.x === before, "returns to requested point");
});
test("drag release velocity is accepted", () => {
  let value = { x: 0, y: 0 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: 0, y: 0 }, { velocity: { x: 200, y: -200 } }); tick();
  assert(value.x > 0 && value.y < 0, "velocity direction");
  settle(); assert(value.x === 0 && value.y === 0, "rest");
});
test("stop leaves the current value and cancels frames", () => {
  let value = { x: 0 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: 100 }); tick();
  const before = value.x; spring.stop(); tick();
  assert(value.x === before && !spring.running, "stop");
});
test("immediate mode replaces an in-flight animation", () => {
  let value = { x: 0 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: 100 }); tick(); spring.to({ x: -10 }, { immediate: true });
  assert(value.x === -10 && !frames.size, "no stale frame");
});
test("reduced motion commits without travel", () => {
  reduced = true; let value = { x: 0 }, finished = false;
  const spring = createValueSpring(() => value, next => value = next, () => finished = true);
  spring.to({ x: 100 });
  assert(value.x === 100 && finished && !frames.size, "reduced motion");
});
test("camera axes and scale settle independently", () => {
  let value = { x: 40, y: -100, scale: 0.2 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: -450, y: 270, scale: 2.25 }); settle();
  assert(value.x === -450 && value.y === 270 && value.scale === 2.25, "all camera coordinates");
});
test("a suspended frame stays finite", () => {
  let value = { x: 0 };
  const spring = createValueSpring(() => value, next => value = next);
  spring.to({ x: 100 }); tick(); tick(30000);
  assert(Number.isFinite(value.x) && value.x <= 100, "finite after suspension"); settle();
});
print(passed + " motion tests passed");
