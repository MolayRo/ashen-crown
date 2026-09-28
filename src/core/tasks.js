// 协程：用生成器写顺序动画/事件脚本。
//   yield            → 等 1 帧
//   yield 数字 n      → 等 n 帧
//   yield 生成器      → 运行子协程直到结束
//   yield () => bool  → 每帧检查，返回 true 时继续
export class TaskRunner {
  constructor() { this.tasks = []; }

  add(gen, owner = null) {
    const t = { stack: [gen], wait: 0, cond: null, done: false, owner };
    this.tasks.push(t);
    return t;
  }

  get busy() { return this.tasks.length > 0; }

  clear(owner = null) {
    if (owner == null) this.tasks.length = 0;
    else this.tasks = this.tasks.filter((t) => t.owner !== owner);
  }

  update() {
    for (const t of this.tasks.slice()) this._step(t);
    this.tasks = this.tasks.filter((t) => !t.done);
  }

  _step(t) {
    if (t.wait > 0) { t.wait--; return; }
    if (t.cond) { if (!t.cond()) return; t.cond = null; }
    let guard = 0;
    while (t.stack.length && guard++ < 1000) {
      const g = t.stack[t.stack.length - 1];
      let r;
      try {
        r = g.next();
      } catch (e) {
        console.error('task error', e);
        t.stack.length = 0;
        break;
      }
      if (r.done) { t.stack.pop(); continue; }
      const v = r.value;
      if (v == null) return;
      if (typeof v === 'number') { t.wait = Math.max(0, Math.round(v) - 1); return; }
      if (typeof v === 'function') { if (!v()) { t.cond = v; return; } continue; }
      if (v && typeof v.next === 'function') { t.stack.push(v); continue; }
      return;
    }
    if (!t.stack.length) t.done = true;
  }
}

export function* wait(n) { yield n; }
export function* waitUntil(fn) { yield fn; }
