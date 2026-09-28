// 可存档的伪随机数（mulberry32）
export class RNG {
  constructor(seed) {
    this.s = (seed >>> 0) || 0x9e3779b9;
  }
  next() {
    let t = (this.s = (this.s + 0x6d2b79f5) >>> 0);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  int(n) { return Math.floor(this.next() * n); }
  pick(arr) { return arr[this.int(arr.length)]; }
  get state() { return this.s; }
  set state(v) { this.s = v >>> 0; }
}

export function randomSeed() {
  return (Math.random() * 4294967296) >>> 0;
}
