// 寻路：移动范围（Dijkstra）、路径、攻击范围、接近目标用的距离场
import { moveType, sameSide } from './rules.js';
import { hasTrait } from './data/classes.js';

export const DIRS4 = [[0, -1], [1, 0], [0, 1], [-1, 0]];

export function key(x, y) { return y * 1000 + x; }
export function unkey(k) { return { x: k % 1000, y: Math.floor(k / 1000) }; }

// 某单位进入某格的消耗（Infinity = 不能进入）
export function enterCost(state, u, x, y) {
  if (x < 0 || y < 0 || x >= state.w || y >= state.h) return Infinity;
  const t = state.terrainAt(x, y);
  const mt = moveType(u);
  let c = t.cost[mt];
  if (c == null) return Infinity;
  if (t.forest && hasTrait(u, 'forest')) c = 1;
  return c;
}

// 小顶堆
class Heap {
  constructor() { this.a = []; }
  push(k, p) {
    const a = this.a;
    a.push([p, k]);
    let i = a.length - 1;
    while (i > 0) {
      const j = (i - 1) >> 1;
      if (a[j][0] <= a[i][0]) break;
      [a[i], a[j]] = [a[j], a[i]];
      i = j;
    }
  }
  pop() {
    const a = this.a;
    const top = a[0];
    const last = a.pop();
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = i * 2 + 1, r = l + 1;
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[i], a[m]] = [a[m], a[i]];
        i = m;
      }
    }
    return top;
  }
  get size() { return this.a.length; }
}

// 移动范围：返回 Map(key → {cost, prev})，包含可经过的格子。
// 敌对单位阻挡通行；友方单位可穿过但不能停留（由 stoppable 判断）。
export function moveRange(state, u, movOverride = null, from = null) {
  const mov = movOverride != null ? movOverride : u.mov;
  const sx = from ? from.x : u.x, sy = from ? from.y : u.y;
  const res = new Map();
  const start = key(sx, sy);
  res.set(start, { cost: 0, prev: -1 });
  const heap = new Heap();
  heap.push(start, 0);
  while (heap.size) {
    const [c, k] = heap.pop();
    const node = res.get(k);
    if (!node || c > node.cost) continue;
    const { x, y } = unkey(k);
    for (const [dx, dy] of DIRS4) {
      const nx = x + dx, ny = y + dy;
      const ec = enterCost(state, u, nx, ny);
      if (ec === Infinity) continue;
      const nc = c + ec;
      if (nc > mov) continue;
      const o = state.unitAt(nx, ny);
      if (o && o !== u && !sameSide(o, u)) continue;
      const nk = key(nx, ny);
      const old = res.get(nk);
      if (!old || nc < old.cost) {
        res.set(nk, { cost: nc, prev: k });
        heap.push(nk, nc);
      }
    }
  }
  return res;
}

// 可停留的格子
export function stoppable(state, u, range) {
  const out = [];
  for (const k of range.keys()) {
    const { x, y } = unkey(k);
    const o = state.unitAt(x, y);
    if (!o || o === u) out.push({ x, y, cost: range.get(k).cost });
  }
  return out;
}

export function pathTo(range, x, y) {
  const path = [];
  let k = key(x, y);
  if (!range.has(k)) return null;
  while (k !== -1) {
    path.push(unkey(k));
    k = range.get(k).prev;
  }
  return path.reverse();
}

// 与某格曼哈顿距离在 [a,b] 内的所有格
export function tilesInRange(state, x, y, a, b) {
  const out = [];
  for (let dy = -b; dy <= b; dy++) {
    const rem = b - Math.abs(dy);
    for (let dx = -rem; dx <= rem; dx++) {
      const d = Math.abs(dx) + Math.abs(dy);
      if (d < a) continue;
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= state.w || ny >= state.h) continue;
      out.push({ x: nx, y: ny });
    }
  }
  return out;
}

// 距离场：从 sources 出发，按单位 u 的移动消耗反向扩散（进入格子的消耗）。
// 用于 AI 接近远处目标。blockHostile：敌对单位是否阻挡。
export function distanceField(state, u, sources, blockHostile = true, maxCost = 999) {
  const dist = new Map();
  const heap = new Heap();
  for (const s of sources) {
    const k = key(s.x, s.y);
    if (!dist.has(k)) { dist.set(k, 0); heap.push(k, 0); }
  }
  while (heap.size) {
    const [c, k] = heap.pop();
    if (c > dist.get(k)) continue;
    if (c > maxCost) break;
    const { x, y } = unkey(k);
    // 从 (x,y) 反推到邻格 n：单位从 n 走进 (x,y) 需要 enterCost(x,y)
    const ec = enterCost(state, u, x, y);
    if (ec === Infinity && c > 0) continue;
    const step = c === 0 ? Math.min(ec, 1) : ec;
    for (const [dx, dy] of DIRS4) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= state.w || ny >= state.h) continue;
      if (enterCost(state, u, nx, ny) === Infinity) continue;
      if (blockHostile) {
        const o = state.unitAt(nx, ny);
        if (o && o !== u && !sameSide(o, u)) continue;
      }
      const nk = key(nx, ny);
      const nc = c + (step === Infinity ? 1 : step);
      if (!dist.has(nk) || nc < dist.get(nk)) {
        dist.set(nk, nc);
        heap.push(nk, nc);
      }
    }
  }
  return dist;
}
