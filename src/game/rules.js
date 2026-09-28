// 战斗规则：命中、伤害、必杀、追击、克制、特效、经验、升级、加点
import { CLASSES, STATS, hasTrait } from './data/classes.js';
import { ITEMS } from './data/items.js';
import { CHARACTERS } from './data/characters.js';
import { terrainOf } from './data/terrain.js';

export const MAX_LEVEL = 20;
export const DOUBLE_THRESHOLD = 4;
export const POINTS_PER_LEVEL = 2;

export function cls(u) { return CLASSES[u.cls]; }
export function moveType(u) { return cls(u).moveType; }
export function isFlying(u) { return moveType(u) === 'fly'; }
export function isArmored(u) { return moveType(u) === 'armor'; }
export function isMounted(u) { return moveType(u) === 'horse'; }
export function unitMov(u) { return u.mov; }

export function canUse(u, itemId) {
  const d = ITEMS[itemId];
  if (!d) return false;
  if (d.type === 'item') return true;
  if (d.lock && d.lock !== u.id) return false;
  return cls(u).weapons.includes(d.type);
}

export function isAttackWeapon(itemId) {
  const d = ITEMS[itemId];
  return !!d && d.type !== 'item' && d.type !== 'staff';
}

// 当前装备的武器（物品对象），没有可用武器返回 null
export function equipped(u) {
  if (u.equip != null) {
    const it = u.items[u.equip];
    if (it && isAttackWeapon(it.id) && canUse(u, it.id)) return it;
  }
  for (const it of u.items) if (isAttackWeapon(it.id) && canUse(u, it.id)) return it;
  return null;
}

export function equipIndex(u) {
  const w = equipped(u);
  return w ? u.items.indexOf(w) : -1;
}

export function usableWeapons(u) {
  return u.items.filter((it) => isAttackWeapon(it.id) && canUse(u, it.id));
}
export function usableStaves(u) {
  return u.items.filter((it) => ITEMS[it.id].type === 'staff' && canUse(u, it.id));
}

export function weaponRange(u, itemId) {
  const d = ITEMS[itemId];
  if (!d || !d.rng) return [0, 0];
  let [a, b] = d.rng;
  if (b === 'mag') b = Math.max(1, Math.floor(stat(u, 'mag') / 2));
  return [a, b];
}

// 能力值（含装备加成）
export function stat(u, s) {
  let v = u[s] || 0;
  if (s !== 'hp') {
    const w = equipped(u);
    if (w) {
      const d = ITEMS[w.id];
      if (d.bonus && d.bonus[s]) v += d.bonus[s];
    }
  }
  return v;
}

// 武器相克：剑>斧>枪>剑
export function triangle(aType, bType) {
  const win = { sword: 'axe', axe: 'lance', lance: 'sword' };
  if (!aType || !bType) return 0;
  if (win[aType] === bType) return 1;
  if (win[bType] === aType) return -1;
  return 0;
}

function isEffective(weaponId, target) {
  const d = ITEMS[weaponId];
  if (!d || !d.eff) return false;
  for (const e of d.eff) {
    if (e === 'fly' && isFlying(target)) return true;
    if (e === 'armor' && isArmored(target)) return true;
    if (e === 'horse' && isMounted(target)) return true;
  }
  return false;
}

export function attackSpeed(u, weaponId) {
  const spd = stat(u, 'spd');
  if (!weaponId) return spd;
  const d = ITEMS[weaponId];
  const carry = d.magic ? stat(u, 'mag') : stat(u, 'str');
  return spd - Math.max(0, (d.wt || 0) - carry);
}

// 统率光环：2 格内有我方领主（非本人）
function leaderAura(state, u, pos) {
  if (!state) return false;
  for (const o of state.units) {
    if (o === u || o.dead || o.hidden || !o.lord) continue;
    if (!sameSide(o, u)) continue;
    const ox = o === u ? pos.x : o.x, oy = o.y;
    if (Math.abs(ox - pos.x) + Math.abs(oy - pos.y) <= 2) return true;
  }
  return false;
}

export function sameSide(a, b) {
  const side = (t) => (t === 'enemy' ? 'enemy' : 'player');
  return side(a.team) === side(b.team);
}

export function terrainBonus(state, pos, u) {
  if (!state || !pos) return { def: 0, avo: 0, name: '' };
  if (u && isFlying(u)) return { def: 0, avo: 0, name: state.terrainAt(pos.x, pos.y).name };
  const t = state.terrainAt(pos.x, pos.y);
  return { def: t.def || 0, avo: t.avo || 0, name: t.name };
}

// 单方战斗数值
export function combatSide(state, u, uPos, weaponId, foe, foePos, foeWeaponId, opts = {}) {
  const d = weaponId ? ITEMS[weaponId] : null;
  const fd = foeWeaponId ? ITEMS[foeWeaponId] : null;
  const tri = d && fd ? triangle(d.type, fd.type) : 0;
  const eff = d ? isEffective(weaponId, foe) : false;
  const magic = !!(d && d.magic);
  const tb = terrainBonus(state, foePos, foe);
  const myTb = terrainBonus(state, uPos, u);
  const aura = leaderAura(state, u, uPos);
  const foeAura = leaderAura(state, foe, foePos);
  let atk = 0, dmg = 0, hit = 0, crit = 0;
  if (d) {
    atk = (magic ? stat(u, 'mag') : stat(u, 'str')) + d.mt * (eff ? 3 : 1) + tri;
    if (opts.initiator && hasTrait(u, 'charge') && (opts.moved || 0) >= 4) atk += 3;
    const foeDef = (magic ? stat(foe, 'res') : stat(foe, 'def')) + tb.def;
    dmg = Math.max(0, atk - foeDef - (hasTrait(foe, 'bulwark') ? 1 : 0));
    let rawHit = d.hit + stat(u, 'skl') * 2 + Math.floor(stat(u, 'lck') / 2) + tri * 15;
    if (aura) rawHit += 10;
    if (hasTrait(u, 'forest') && state && state.terrainAt(uPos.x, uPos.y).forest) rawHit += 10;
    if (magic && hasTrait(u, 'scholar')) rawHit += 10;
    let avo = attackSpeed(foe, foeWeaponId) * 2 + stat(foe, 'lck') + tb.avo;
    if (foeAura) avo += 5;
    if (hasTrait(foe, 'lockpick')) avo += 10;
    hit = clamp(rawHit - avo, 0, 100);
    let rawCrit = (d.crit || 0) + Math.floor(stat(u, 'skl') / 2);
    if (magic && hasTrait(u, 'scholar')) rawCrit += 5;
    crit = hasTrait(foe, 'bulwark') ? 0 : clamp(rawCrit - stat(foe, 'lck'), 0, 100);
  }
  return { atk, dmg, hit, crit, tri, eff, magic, as: attackSpeed(u, weaponId), terrain: myTb };
}

function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

export function inRange(u, weaponId, dist) {
  if (!weaponId) return false;
  const [a, b] = weaponRange(u, weaponId);
  return dist >= a && dist <= b;
}

// 战斗预测：attacker 在 aPos 用 weaponId 攻击 defender（defender 在自身位置）
export function forecast(state, att, aPos, def, weaponId, opts = {}) {
  const dPos = { x: def.x, y: def.y };
  const dist = Math.abs(aPos.x - dPos.x) + Math.abs(aPos.y - dPos.y);
  const dw = equipped(def);
  const dWeaponId = dw ? dw.id : null;
  const canCounter = !!dWeaponId && inRange(def, dWeaponId, dist) && !def.noCounter;
  const A = combatSide(state, att, aPos, weaponId, def, dPos, canCounter ? dWeaponId : null, { initiator: true, moved: opts.moved });
  const D = combatSide(state, def, dPos, canCounter ? dWeaponId : null, att, aPos, weaponId, {});
  const aTimes = A.as - attackSpeed(def, dWeaponId) >= DOUBLE_THRESHOLD ? 2 : 1;
  const dTimes = canCounter && D.as - attackSpeed(att, weaponId) >= DOUBLE_THRESHOLD ? 2 : 1;
  return {
    dist,
    att: { unit: att, pos: aPos, weapon: weaponId, hp: att.hp, maxhp: att.mhp, ...A, times: aTimes },
    def: { unit: def, pos: dPos, weapon: canCounter ? dWeaponId : null, shownWeapon: dWeaponId, hp: def.hp, maxhp: def.mhp, ...D, times: canCounter ? dTimes : 0, canCounter },
  };
}

// 2RN 真实命中（显示 70 实际更可靠，显示 30 实际更难中），与 GBA 系列一致
export function rollHit(rng, hit) {
  const r = (rng.int(100) + rng.int(100)) / 2;
  return r < hit;
}

// 结算一次战斗，返回每一击的记录；会修改双方 HP
export function resolveCombat(state, att, aPos, def, weaponId, rng, opts = {}) {
  const fc = forecast(state, att, aPos, def, weaponId, opts);
  const seq = [];
  const order = ['att', 'def'];
  if (fc.att.times > 1) order.push('att');
  if (fc.def.canCounter && fc.def.times > 1) order.push('def');
  const strikes = [];
  const dealt = { att: 0, def: 0 };
  for (const who of order) {
    const S = fc[who];
    const O = who === 'att' ? fc.def : fc.att;
    if (who === 'def' && !fc.def.canCounter) continue;
    if (S.unit.hp <= 0 || O.unit.hp <= 0) break;
    const hit = rollHit(rng, S.hit);
    let crit = false;
    let dmg = 0;
    if (hit) {
      crit = rng.int(100) < S.crit;
      dmg = S.dmg * (crit ? 3 : 1);
      dmg = Math.min(dmg, O.unit.hp);
      O.unit.hp -= dmg;
      dealt[who] += dmg;
    }
    strikes.push({ who, hit, crit, dmg, attHp: fc.att.unit.hp, defHp: fc.def.unit.hp, kill: O.unit.hp <= 0 });
  }
  seq.push(...strikes);
  return { fc, strikes: seq, dealt, attDead: att.hp <= 0, defDead: def.hp <= 0 };
}

// ---- 经验 ----
export function combatExp(u, foe, dealtDamage, killed) {
  if (u.lv >= MAX_LEVEL) return 0;
  const diff = (foe.lv || 1) - u.lv;
  let e = dealtDamage > 0 ? Math.max(2, Math.floor((36 + diff) / 3)) : 1;
  if (killed) {
    e += Math.max(4, diff * 3 + 30);
    if (foe.boss) e += 40;
  }
  return Math.max(1, Math.min(100, e));
}

export function staffExp(u, staffId) {
  if (u.lv >= MAX_LEVEL) return 0;
  const d = ITEMS[staffId];
  return d && d.heal >= 20 ? 20 : d && d.rng && d.rng[1] === 'mag' ? 22 : 17;
}

export function healAmount(healer, staffId, target) {
  const d = ITEMS[staffId];
  let amt = d.heal + stat(healer, 'mag');
  if (hasTrait(healer, 'prayer')) amt += Math.floor(stat(healer, 'mag') / 2);
  return Math.min(amt, target.mhp - target.hp);
}

// ---- 成长 ----
export function growthOf(u) {
  const c = cls(u);
  const ch = CHARACTERS[u.id];
  const g = {};
  for (const s of STATS) g[s] = (c.growth[s] || 0) + ((ch && ch.growthMod && ch.growthMod[s]) || 0);
  return g;
}

export function capOf(u, s) {
  const c = cls(u);
  if (s === 'hp') return c.caps.hp;
  return c.caps[s] ?? 30;
}

function getStat(u, s) { return s === 'hp' ? u.mhp : u[s]; }
function addStat(u, s, v) {
  if (s === 'hp') { u.mhp += v; u.hp += v; } else u[s] += v;
}

// 升级：按成长率掷骰，返回各项增长；保底至少 2 项增长
export function levelUp(u, rng) {
  const g = growthOf(u);
  const gains = {};
  for (const s of STATS) {
    let n = 0;
    let rate = g[s];
    while (rate >= 100) { n++; rate -= 100; }
    if (rng.int(100) < rate) n++;
    const room = capOf(u, s) - getStat(u, s);
    n = Math.max(0, Math.min(n, room));
    if (n) gains[s] = n;
  }
  const count = Object.keys(gains).length;
  if (count < 2) {
    const order = STATS.filter((s) => !gains[s] && capOf(u, s) > getStat(u, s)).sort((a, b) => g[b] - g[a]);
    for (let i = 0; i < 2 - count && i < order.length; i++) gains[order[i]] = 1;
  }
  for (const s of Object.keys(gains)) addStat(u, s, gains[s]);
  u.lv += 1;
  u.points = (u.points || 0) + POINTS_PER_LEVEL;
  return gains;
}

// 获得经验，可能连续升级；返回 [{gains, lv}] 列表
export function gainExp(u, amount, rng) {
  const ups = [];
  if (u.lv >= MAX_LEVEL || amount <= 0) return ups;
  u.exp += amount;
  while (u.exp >= 100 && u.lv < MAX_LEVEL) {
    u.exp -= 100;
    const gains = levelUp(u, rng);
    ups.push({ gains, lv: u.lv });
  }
  if (u.lv >= MAX_LEVEL) u.exp = 0;
  return ups;
}

// ---- 手动加点（潜能点）----
// 每次升级获得 2 点。职业专长能力 1 点换 +1，其余能力 2 点换 +1；HP 1 点换 +2；
// 移动力 6 点换 +1，每人仅限 1 次。每项能力通过加点最多提升 5（HP 最多 10），且不能超过职业上限。
export const ALLOC_LIMIT = { hp: 10, str: 5, mag: 5, skl: 5, spd: 5, lck: 5, def: 5, res: 5, mov: 1 };
export const ALLOC_KEYS = ['hp', 'str', 'mag', 'skl', 'spd', 'lck', 'def', 'res', 'mov'];

export function allocCost(u, s) {
  if (s === 'mov') return 6;
  if (s === 'hp') return 1;
  return cls(u).favored.includes(s) ? 1 : 2;
}
export function allocGain(s) { return s === 'hp' ? 2 : 1; }

// 返回不能加点的原因（null 表示可以）
export function allocBlock(u, s, pending = {}) {
  const alloc = u.alloc || {};
  const used = (alloc[s] || 0) + (pending[s] || 0);
  const pts = (u.points || 0) - pendingCost(u, pending);
  if (pts < allocCost(u, s)) return '潜能点不足';
  if (used + allocGain(s) > ALLOC_LIMIT[s]) return s === 'mov' ? '移动力只能提升一次' : '已达加点上限';
  if (s === 'mov') return null;
  const cur = (s === 'hp' ? u.mhp : u[s]) + (pending[s] || 0);
  if (cur + allocGain(s) > capOf(u, s)) return '已达职业上限';
  return null;
}

export function pendingCost(u, pending) {
  let c = 0;
  for (const s of Object.keys(pending)) c += (pending[s] / allocGain(s)) * allocCost(u, s);
  return c;
}

export function applyAlloc(u, pending) {
  u.alloc = u.alloc || {};
  const cost = pendingCost(u, pending);
  for (const s of Object.keys(pending)) {
    const v = pending[s];
    if (!v) continue;
    if (s === 'hp') { u.mhp += v; u.hp += v; } else u[s] += v;
    u.alloc[s] = (u.alloc[s] || 0) + v;
  }
  u.points -= cost;
}

// 推荐加点：按职业推荐顺序轮流分配
export function recommendAlloc(u) {
  const pending = {};
  const order = cls(u).rec || cls(u).favored;
  let guard = 0;
  let progress = true;
  while (progress && guard++ < 100) {
    progress = false;
    for (const s of order) {
      if (!allocBlock(u, s, pending)) {
        pending[s] = (pending[s] || 0) + allocGain(s);
        progress = true;
      }
    }
  }
  return pending;
}

// 伤药等回复
export function itemHeal(u, itemId) {
  const d = ITEMS[itemId];
  return Math.min(d.heal || 0, u.mhp - u.hp);
}
