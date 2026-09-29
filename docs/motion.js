/* Small, interruptible critically damped spring. No dependencies or fixed-duration gestures. */
function createValueSpring(read, write, finish = () => {}) {
  let frame = null, previousTime = null, target = null;
  let velocity = {};
  function stop() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    previousTime = null;
    velocity = {};
  }
  function step(time) {
    frame = null;
    const dt = Math.min((time - (previousTime ?? time - 16.667)) / 1000, 0.04);
    previousTime = time;
    const value = read(), next = {};
    const omega = 24;
    const decay = Math.exp(-omega * dt);
    let settled = true;
    for (const key of Object.keys(target)) {
      const offset = value[key] - target[key];
      const auxiliary = ((velocity[key] || 0) + omega * offset) * dt;
      next[key] = target[key] + (offset + auxiliary) * decay;
      velocity[key] = ((velocity[key] || 0) - omega * auxiliary) * decay;
      const precision = key === "scale" ? 0.0005 : 0.15;
      if (Math.abs(next[key] - target[key]) > precision || Math.abs(velocity[key]) > precision * 12) settled = false;
    }
    write(settled ? { ...target } : next);
    if (settled) {
      stop();
      finish();
    } else {
      frame = requestAnimationFrame(step);
    }
  }
  return {
    stop,
    to(next, options = {}) {
      target = { ...next };
      if (options.immediate || matchMedia("(prefers-reduced-motion: reduce)").matches) {
        stop();
        write({ ...target });
        finish();
        return;
      }
      if (options.velocity) velocity = { ...velocity, ...options.velocity };
      if (frame === null) {
        previousTime = null;
        frame = requestAnimationFrame(step);
      }
    },
    get target() { return target; },
    get running() { return frame !== null; },
  };
}
