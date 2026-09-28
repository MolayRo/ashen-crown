// 敌方/友军 AI：按行为模式（进攻、守点、固守、支援、烧村、盗贼、占领、犹豫）规划一步行动
import * as R from './rules.js';
import { ITEMS } from './data/items.js';
import { moveRange, stoppable, tilesInRange, distanceField, key } from './pathfind.js';

// 估计一次攻击的收益
function scoreAttack(state, u, pos, target, weapon) {
  const fc = R.forecast(state, u, pos, target, weapon.id, { moved: Math.abs(pos.x - u.x) + Math.abs(pos.y - u.y) });
  const A = fc.att, D = fc.def;
  const hitP = A.hit / 100;
  const critP = A.crit / 100;
  const perHit = A.dmg * (1 - critP) + Math.min(target.hp, A.dmg * 3) * critP;
  const expDmg = Math.min(target.hp, hitP * perHit * A.times);
  // 击杀概率（近似）
  let killP = 0;
  const need = A.dmg > 0 ? Math.ceil(target.hp / A.dmg) : 99;
  if (need <= A.times) killP = need === 1 ? hitP : hitP * hitP;
  else if (A.dmg > 0 && A.dmg * 3 >= target.hp) killP = hitP * critP;
  let counter = 0;
  if (D.canCounter) counter = (D.hit / 100) * D.dmg * D.times;
  const t = state.terrainAt(pos.x, pos.y);
  const diff = state.difficulty;
  let s = expDmg * 1.2 + killP * (diff === 'hard' ? 60 : diff === 'easy' ? 25 : 40);
  s -= counter * (diff === 'hard' ? 0.8 : 0.45);
  if (!R.isFlying(u)) s += (t.def || 0) * 2 + (t.avo || 0) * 0.08;
  if (target.lord) s += 6;
  if (target.escort) s += 10;
  if (R.usableStaves(target).length && !R.usableWeapons(target).length) s += diff === 'easy' ? 0 : 8;
  if (A.dmg === 0) s -= 30;
  if (diff === 'easy') s += state.rng.next() * 10 - 5;
  return { s, fc };
}

function hostiles(state, u) {
  return state.living().filter((o) => state.hostile(u, o) && !o.caged && !(u.team === 'enemy' && o.team === 'enemy'));
}

function activeMode(state, u) {
  const ai = u.ai || { mode: 'aggressive' };
  let mode = ai.mode;
  if (ai.start != null && state.turn < ai.start && !u.provoked) return 'idle';
  if (mode === 'hold' || mode === 'guard') {
    if (u.provoked && ai.wake !== false && mode === 'hold') mode = 'aggressive';
    if (ai.until != null && state.turn >= ai.until) mode = 'aggressive';
    if (ai.range != null) {
      const near = hostiles(state, u).some((o) => Math.abs(o.x - u.x) + Math.abs(o.y - u.y) <= ai.range);
      if (near) mode = 'aggressive';
    }
  }
  if (state.difficulty === 'hard' && mode === 'hold' && ai.hardAggro) mode = 'aggressive';
  return mode;
}

export function planAction(state, u) {
  const mode = activeMode(state, u);
  const plan = { unit: u, dest: { x: u.x, y: u.y }, path: null, action: null, mode };

  if (mode === 'idle') return plan;

  const range = mode === 'guard' ? null : moveRange(state, u, mode === 'passive' ? Math.max(1, u.mov - 2) : null);
  const stops = range ? stoppable(state, u, range) : [{ x: u.x, y: u.y, cost: 0 }];
  const setDest = (t) => { plan.dest = { x: t.x, y: t.y }; plan.path = range ? pathFrom(range, t) : null; };

  // 盗贼：抢宝箱 → 逃跑
  if (mode === 'thief') return planThief(state, u, plan, range, stops, setDest);

  // 支援：治疗受伤的同伴
  if (R.usableStaves(u).length) {
    const h = bestHeal(state, u, stops);
    if (h) { setDest(h.tile); plan.action = { type: 'staff', target: h.target, staff: h.staff }; return plan; }
    if (mode === 'support') {
      // 跟随最近的同伴，保持在后方
      const friends = state.living(u.team).filter((o) => o !== u && !o.caged);
      if (friends.length && range) {
        const df = distanceField(state, u, friends.map((f) => ({ x: f.x, y: f.y })), true);
        let best = null;
        for (const t of stops) {
          const d = df.get(key(t.x, t.y)) ?? 999;
          const threat = threatAt(state, u, t);
          const sc = -Math.abs(d - 2) * 3 - threat * 4;
          if (!best || sc > best.sc) best = { t, sc };
        }
        if (best) setDest(best.t);
      }
      return plan;
    }
  }

  // 烧村
  if (mode === 'raze') {
    const villages = [];
    for (const [k, v] of Object.entries(state.ch.villages || {})) {
      if (state.villages[k]) continue;
      const [x, y] = k.split(',').map(Number);
      if (v.noRaze) continue;
      if (u.ai.villages && !u.ai.villages.some(([vx, vy]) => vx === x && vy === y)) continue;
      villages.push({ x, y });
    }
    const reach = stops.find((t) => villages.some((v) => v.x === t.x && v.y === t.y));
    if (reach) { setDest(reach); plan.action = { type: 'raze' }; return plan; }
    const atk = bestAttack(state, u, stops);
    if (atk && atk.s > 12) { setDest(atk.tile); plan.action = { type: 'attack', target: atk.target, weapon: atk.weapon }; return plan; }
    if (villages.length) { approach(state, u, stops, villages, setDest); return plan; }
  }

  // 占领（第四章：冲向要塞中心）
  if (mode === 'seize') {
    const dp = state.ch.objective.defendTile;
    if (dp) {
      const reach = stops.find((t) => t.x === dp[0] && t.y === dp[1]);
      if (reach) { setDest(reach); return plan; }
      const atk = bestAttack(state, u, stops);
      if (atk && atk.s > 5) { setDest(atk.tile); plan.action = { type: 'attack', target: atk.target, weapon: atk.weapon }; return plan; }
      approach(state, u, stops, [{ x: dp[0], y: dp[1] }], setDest, true);
      return plan;
    }
  }

  // 犹豫（薇拉）：只移动不攻击
  if (mode === 'passive') {
    const goal = (u.ai && u.ai.goal) ? [{ x: u.ai.goal[0], y: u.ai.goal[1] }] : hostiles(state, u).map((o) => ({ x: o.x, y: o.y }));
    const far = stops.filter((t) => hostiles(state, u).every((o) => Math.abs(o.x - t.x) + Math.abs(o.y - t.y) >= 2));
    approach(state, u, far.length ? far : stops, goal, setDest);
    return plan;
  }

  // 攻击
  const atk = bestAttack(state, u, mode === 'guard' ? [{ x: u.x, y: u.y }] : (mode === 'hold' ? stops.filter((t) => withinLeash(u, t)) : stops));
  if (atk && atk.s > -15) {
    setDest(atk.tile);
    plan.action = { type: 'attack', target: atk.target, weapon: atk.weapon };
    return plan;
  }
  if (mode === 'guard' || mode === 'hold') return plan;

  // 接近最近的敌人
  const targets = hostiles(state, u).map((o) => ({ x: o.x, y: o.y }));
  if (u.ai && u.ai.goal) targets.push({ x: u.ai.goal[0], y: u.ai.goal[1] });
  approach(state, u, stops, targets, setDest);
  return plan;
}

function withinLeash(u, t) {
  const leash = u.ai && u.ai.leash;
  if (leash == null) return true;
  const hx = u.ai.home ? u.ai.home[0] : u.x, hy = u.ai.home ? u.ai.home[1] : u.y;
  return Math.abs(t.x - hx) + Math.abs(t.y - hy) <= leash;
}

function pathFrom(range, t) {
  const path = [];
  let k = key(t.x, t.y);
  while (k !== -1 && range.has(k)) {
    path.push({ x: k % 1000, y: Math.floor(k / 1000) });
    k = range.get(k).prev;
  }
  return path.reverse();
}

function bestAttack(state, u, stops) {
  let best = null;
  const weapons = R.usableWeapons(u);
  if (!weapons.length) return null;
  const foes = hostiles(state, u);
  if (!foes.length) return null;
  // 预先筛选：只看可能在射程内的目标
  let maxR = 0;
  for (const w of weapons) maxR = Math.max(maxR, R.weaponRange(u, w.id)[1]);
  for (const t of stops) {
    for (const f of foes) {
      const d = Math.abs(f.x - t.x) + Math.abs(f.y - t.y);
      if (d > maxR) continue;
      for (const w of weapons) {
        if (!R.inRange(u, w.id, d)) continue;
        const { s } = scoreAttack(state, u, t, f, w);
        // 同分时偏好少移动
        const sc = s - (Math.abs(t.x - u.x) + Math.abs(t.y - u.y)) * 0.05;
        if (!best || sc > best.s) best = { s: sc, tile: t, target: f, weapon: w };
      }
    }
  }
  return best;
}

function bestHeal(state, u, stops) {
  let best = null;
  const friends = state.living().filter((o) => o !== u && !state.hostile(u, o) && o.hp < o.mhp && !o.caged);
  if (!friends.length) return null;
  for (const st of R.usableStaves(u)) {
    const [a, b] = R.weaponRange(u, st.id);
    for (const t of stops) {
      for (const f of friends) {
        const d = Math.abs(f.x - t.x) + Math.abs(f.y - t.y);
        if (d < a || d > b) continue;
        const missing = f.mhp - f.hp;
        if (missing < 5 && f.hp > f.mhp * 0.6) continue;
        const sc = missing * 2 + (f.boss ? 6 : 0) - threatAt(state, u, t) * 2;
        if (!best || sc > best.sc) best = { sc, tile: t, target: f, staff: st };
      }
    }
  }
  return best;
}

// 粗略威胁：该格在多少个敌对单位的攻击范围内（只看相邻 1~2 格的近似）
function threatAt(state, u, t) {
  let n = 0;
  for (const o of hostiles(state, u)) {
    const d = Math.abs(o.x - t.x) + Math.abs(o.y - t.y);
    if (d <= o.mov + 2) n++;
  }
  return n;
}

function approach(state, u, stops, targets, setDest, ignoreUnits = false) {
  if (!targets.length) return;
  const df = distanceField(state, u, targets, !ignoreUnits);
  let best = null;
  for (const t of stops) {
    const d = df.get(key(t.x, t.y));
    if (d == null) continue;
    const ter = state.terrainAt(t.x, t.y);
    const sc = -d * 10 + (R.isFlying(u) ? 0 : (ter.def || 0) + (ter.avo || 0) * 0.05);
    if (!best || sc > best.sc) best = { sc, t };
  }
  if (best) setDest(best.t);
}

function planThief(state, u, plan, range, stops, setDest) {
  const chests = [];
  for (const k of Object.keys(state.ch.chests || {})) {
    if (state.chests[k]) continue;
    const [x, y] = k.split(',').map(Number);
    chests.push({ x, y });
  }
  const reach = stops.find((t) => chests.some((c) => c.x === t.x && c.y === t.y));
  if (reach) { setDest(reach); plan.action = { type: 'chest' }; return plan; }
  if (chests.length) { approach(state, u, stops, chests, setDest); return plan; }
  // 抢完后先躲藏，到指定回合才逃离
  if (u.ai && u.ai.flee != null && state.turn < u.ai.flee) {
    if (u.ai.lurk) approach(state, u, stops, [{ x: u.ai.lurk[0], y: u.ai.lurk[1] }], setDest);
    return plan;
  }
  const esc = (u.ai && u.ai.escape) || [];
  const escTiles = esc.map(([x, y]) => ({ x, y }));
  const out = stops.find((t) => escTiles.some((e) => e.x === t.x && e.y === t.y));
  if (out) { setDest(out); plan.action = { type: 'escape' }; return plan; }
  if (escTiles.length) approach(state, u, stops, escTiles, setDest);
  return plan;
}

// 某一方全部单位的威胁范围（用于“敌方威胁范围”显示）
export function threatTiles(state, team = 'enemy') {
  const set = new Set();
  for (const u of state.living(team)) {
    if (u.caged) continue;
    const mode = u.ai ? u.ai.mode : 'aggressive';
    if (mode === 'passive' || mode === 'thief') continue;
    addUnitThreat(state, u, set, mode === 'guard');
  }
  return set;
}

export function addUnitThreat(state, u, set, noMove = false) {
  const weapons = R.usableWeapons(u);
  if (!weapons.length) return set;
  const stops = noMove ? [{ x: u.x, y: u.y }] : [...moveRange(state, u).keys()].map((k) => ({ x: k % 1000, y: Math.floor(k / 1000) }));
  let lo = 99, hi = 0;
  for (const w of weapons) { const [a, b] = R.weaponRange(u, w.id); lo = Math.min(lo, a); hi = Math.max(hi, b); }
  for (const t of stops) {
    const o = state.unitAt(t.x, t.y);
    if (o && o !== u && !state.hostile(o, u)) continue;
    for (const r of tilesInRange(state, t.x, t.y, lo, hi)) set.add(key(r.x, r.y));
  }
  return set;
}

export { ITEMS };
