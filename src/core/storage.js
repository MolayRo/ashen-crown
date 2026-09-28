// localStorage 包装：隐私模式/禁用存储时不抛错，退化为内存存储
const mem = new Map();

function ls() {
  try {
    const s = window.localStorage;
    const probe = '__ashen_probe__';
    s.setItem(probe, '1');
    s.removeItem(probe);
    return s;
  } catch (e) {
    return null;
  }
}

let backend = null;
let checked = false;
function get() {
  if (!checked) { backend = typeof window !== 'undefined' ? ls() : null; checked = true; }
  return backend;
}

export const storage = {
  get available() { return !!get(); },
  getItem(k) {
    const s = get();
    try { return s ? s.getItem(k) : (mem.has(k) ? mem.get(k) : null); } catch (e) { return mem.get(k) ?? null; }
  },
  setItem(k, v) {
    const s = get();
    try { if (s) s.setItem(k, v); else mem.set(k, v); return true; } catch (e) { mem.set(k, v); return false; }
  },
  removeItem(k) {
    const s = get();
    try { if (s) s.removeItem(k); } catch (e) { /* ignore */ }
    mem.delete(k);
  },
  getJSON(k) {
    const raw = this.getItem(k);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
  },
  setJSON(k, v) { return this.setItem(k, JSON.stringify(v)); },
};
