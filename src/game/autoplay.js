// 我方自动操作（用于无头模拟测试与浏览器内“自动演示”验收）：目标导向 + 风险评估
import * as R from './rules.js';
import { ITEMS } from './data/items.js';
import { hasTrait } from './data/classes.js';
import { moveRange, stoppable, tilesInRange, distanceField, key } from './pathfind.js';
import { addUnitThreat } from './ai.js';

function enemies(state) { return state.living('enemy').filter((e) => !e.caged); }

// 每个敌人威胁的格子集合
let threatSeq = 0;
export function buildThreat(state) {
  const list = [];
  riskCache.clear();
  list.cacheId = 't' + (threatSeq++) + ':';
  for (const e of enemies(state)) {
    const mode = e.ai ? e.ai.mode : 'aggressive';
    if (mode === 'passive' || mode === 'thief' || mode === 'idle') continue;
    const set = new Set();
    addUnitThreat(state, e, set, mode === 'guard');
    list.push({ e, set });
  }
  return list;
}

// 单位 u 停在 t 时，下个敌方回合预计承受的伤害（dmg：偏悲观的期望值；worst：全部命中的最坏情况）
const riskCache = new Map();
function riskAt(state, u, t, threat) {
  const ck = u.uid + ':' + key(t.x, t.y) + ':' + u.hp;
  if (threat.cacheId && riskCache.has(threat.cacheId + ck)) return riskCache.get(threat.cacheId + ck);
  const ox = u.x, oy = u.y;
  state.setPos(u, t.x, t.y);
  let total = 0, worst = 0;
  let n = 0;
  for (const { e, set } of threat) {
    if (e.dead || !set.has(key(t.x, t.y))) continue;
    const w = R.equipped(e);
    if (!w) continue;
    // 近似：攻击者站在距离 = 武器最小射程的位置
    const [a] = R.weaponRange(e, w.id);
    const pos = { x: t.x + a, y: t.y };
    const fc = R.forecast(state, e, pos, u, w.id);
    const p = Math.min(1, fc.att.hit / 100 + 0.2);
    total += p * fc.att.dmg * fc.att.times;
    if (fc.att.hit > 0) worst += fc.att.dmg * fc.att.times;
    n++;
  }
  state.setPos(u, ox, oy);
  const r = { dmg: total, worst, n };
  if (threat.cacheId) riskCache.set(threat.cacheId + ck, r);
  return r;
}

function objectiveTiles(state) {
  const o = state.ch.objective;
  if (o.seize) return [{ x: o.seize[0], y: o.seize[1] }];
  return [];
}

// 为单位 u 规划一步：{unit, dest, action}
export function planPlayer(state, u, threat) {
  const range = moveRange(state, u);
  const stops = stoppable(state, u, range);
  const plan = { unit: u, dest: { x: u.x, y: u.y }, action: null };
  // 久攻不下时逐渐放宽风险容忍度
  const bold = Math.max(0.35, 1 - Math.max(0, state.turn - 8) / 20);
  const safe = (t, frac = 0.75) => riskAt(state, u, t, threat).dmg * bold < u.hp * frac;
  const obj = state.ch.objective;

  // 护送目标：朝撤离点前进，尽量安全
  if (u.escort) {
    const esc = obj.escape || [];
    const at = stops.find((t) => esc.some(([x, y]) => x === t.x && y === t.y) && safe(t, 1.2));
    if (at) { plan.dest = at; plan.action = { type: 'escape' }; return plan; }
    const df = distanceField(state, u, esc.map(([x, y]) => ({ x, y })), true);
    let best = null;
    for (const t of stops) {
      const d = df.get(key(t.x, t.y)) ?? 999;
      const r = riskAt(state, u, t, threat).dmg;
      const sc = -d * 3 - r * 4 - (r >= u.hp ? 200 : 0);
      if (!best || sc > best.sc) best = { sc, t };
    }
    if (best) plan.dest = best.t;
    return plan;
  }

  // 坚守：王子坐镇要塞中央，只在原地反击（能当回合交谈招募时例外）
  const talkNow = (state.ch.events || []).some((ev) => {
    if (ev.on !== 'talk' || ev.a !== u.id || state.fired.includes(ev.id)) return false;
    const tgt = state.findUnit(ev.b);
    return tgt && tgt.team !== 'player' && stops.some((t) => Math.abs(t.x - tgt.x) + Math.abs(t.y - tgt.y) === 1);
  });
  if (u.lord && obj.type === 'defend' && obj.defendTile && !talkNow) {
    const [dx, dy] = obj.defendTile;
    const onTile = stops.find((t) => t.x === dx && t.y === dy);
    if (onTile) {
      plan.dest = onTile;
      const tgt = enemies(state).map((f) => ({ f, d: Math.abs(f.x - dx) + Math.abs(f.y - dy) }))
        .filter(({ f, d }) => R.usableWeapons(u).some((w) => R.inRange(u, w.id, d)));
      let best = null;
      for (const { f, d } of tgt) {
        for (const w of R.usableWeapons(u)) {
          if (!R.inRange(u, w.id, d)) continue;
          const fc = R.forecast(state, u, onTile, f, w.id);
          const cm = fc.def.canCounter ? fc.def.dmg * fc.def.times : 0;
          if (cm >= u.hp) continue;
          const sc = (fc.att.hit / 100) * fc.att.dmg * fc.att.times - (fc.def.canCounter ? (fc.def.hit / 100) * cm : 0);
          if (!best || sc > best.sc) best = { sc, f, w };
        }
      }
      if (best) plan.action = { type: 'attack', target: best.f, weaponIdx: u.items.indexOf(best.w) };
      return plan;
    }
  }

  // 占领
  if (u.lord && obj.seize) {
    const [sx, sy] = obj.seize;
    const boss = state.units.find((o) => o.tag === 'final');
    if (boss && boss.dead && stops.some((t) => t.x === sx && t.y === sy)) {
      plan.dest = { x: sx, y: sy }; plan.action = { type: 'seize' }; return plan;
    }
  }

  // 招募交谈
  for (const ev of state.ch.events || []) {
    if (ev.on !== 'talk' || ev.a !== u.id || state.fired.includes(ev.id)) continue;
    const tgt = state.findUnit(ev.b);
    if (!tgt || tgt.team === 'player') continue;
    const adj = stops.filter((t) => Math.abs(t.x - tgt.x) + Math.abs(t.y - tgt.y) === 1);
    const ok = adj.filter((t) => safe(t, 0.9));
    const pick = (ok.length ? ok : adj)[0];
    if (pick && (ok.length || u.hp > u.mhp * 0.6)) { plan.dest = pick; plan.action = { type: 'talk', target: tgt }; return plan; }
  }

  // 开牢门（第三章）
  for (const ev of state.ch.events || []) {
    if (ev.on !== 'door' || state.fired.includes(ev.id)) continue;
    if (!(hasTrait(u, 'lockpick') || state.doorKey(u) >= 0)) continue;
    const [dx, dy] = ev.at;
    const adj = stops.filter((t) => Math.abs(t.x - dx) + Math.abs(t.y - dy) === 1);
    if (adj.length) { plan.dest = adj[0]; plan.action = { type: 'door', x: dx, y: dy }; return plan; }
  }

  // 访问村庄
  for (const t of stops) {
    const k = t.x + ',' + t.y;
    if ((state.ch.villages || {})[k] && !state.villages[k] && safe(t, 0.9)) {
      plan.dest = t; plan.action = { type: 'visit' }; return plan;
    }
  }

  // 开宝箱（盗贼或有钥匙）
  if (hasTrait(u, 'lockpick') || state.chestKey(u) >= 0) {
    for (const t of stops) {
      const k = t.x + ',' + t.y;
      if ((state.ch.chests || {})[k] && !state.chests[k] && state.charAt(t.x, t.y) === 'C' && safe(t, 0.8)) {
        plan.dest = t; plan.action = { type: 'chest' }; return plan;
      }
    }
  }

  // 治疗
  const staves = R.usableStaves(u);
  if (staves.length) {
    let best = null;
    const friends = state.living().filter((o) => o.team === 'player' && o !== u && o.hp < o.mhp - 4);
    for (const st of staves) {
      const [a, b] = R.weaponRange(u, st.id);
      for (const t of stops) {
        for (const f of friends) {
          const d = Math.abs(f.x - t.x) + Math.abs(f.y - t.y);
          if (d < a || d > b) continue;
          const r = riskAt(state, u, t, threat).dmg;
          const sc = (f.mhp - f.hp) * 2 + (f.lord ? 8 : 0) - r * 3 - (r >= u.hp ? 100 : 0);
          if (!best || sc > best.sc) best = { sc, t, f, st };
        }
      }
    }
    if (best && best.sc > 0) { plan.dest = best.t; plan.action = { type: 'staff', target: best.f, staff: best.st }; return plan; }
  }

  // 自救：HP 低时用伤药并退到安全处
  if (u.hp < u.mhp * 0.5 && u.mhp - u.hp >= 8) {
    const idx = u.items.findIndex((i) => ITEMS[i.id].heal && ITEMS[i.id].type === 'item');
    if (idx >= 0) {
      let best = null;
      for (const t of stops) {
        const r = riskAt(state, u, t, threat).dmg;
        if (!best || r < best.r) best = { r, t };
      }
      plan.dest = best.t; plan.action = { type: 'item', idx }; return plan;
    }
  }

  // 重伤且没有伤药：退到最安全、靠近治疗者或回复地形的位置
  if (u.hp < u.mhp * 0.35 && !u.items.some((i) => ITEMS[i.id].heal && ITEMS[i.id].type === 'item')) {
    const healers = state.living('player').filter((p) => p !== u && R.usableStaves(p).length);
    let best = null;
    for (const t of stops) {
      const r = riskAt(state, u, t, threat).dmg;
      const ter = state.terrainAt(t.x, t.y);
      const nearHealer = healers.some((h) => Math.abs(h.x - t.x) + Math.abs(h.y - t.y) <= 3);
      const sc = -r * 3 + (ter.heal ? 15 : 0) + (nearHealer ? 10 : 0);
      if (!best || sc > best.sc) best = { sc, t, r };
    }
    if (best && best.r < u.hp) { plan.dest = best.t; plan.atkScore = -60; return plan; }
  }

  // 攻击
  let bestAtk = null;
  const foes = enemies(state).filter((e) => !(e.recruitable && state.ch.events.some((ev) => ev.on === 'talk' && ev.b === e.id && !state.fired.includes(ev.id) && state.findUnit(ev.a))));
  const keyHolder = enemies(state).find((e) => e.drop && e.items.some((i) => ITEMS[i.id].key === 'door'));
  const dpt = obj.type === 'defend' ? obj.defendTile : null;
  for (const w of R.usableWeapons(u)) {
    const [a, b] = R.weaponRange(u, w.id);
    for (const t of stops) {
      if (dpt && Math.abs(t.x - dpt[0]) + Math.abs(t.y - dpt[1]) > 5) continue;
      if (obj.seize && !u.lord && obj.seize[0] === t.x && obj.seize[1] === t.y) continue;
      for (const f of foes) {
        const d = Math.abs(f.x - t.x) + Math.abs(f.y - t.y);
        if (d < a || d > b) continue;
        const ox = u.x, oy = u.y;
        state.setPos(u, t.x, t.y);
        const fc = R.forecast(state, u, t, f, w.id, { moved: Math.abs(t.x - ox) + Math.abs(t.y - oy) });
        state.setPos(u, ox, oy);
        const A = fc.att, D = fc.def;
        const exp = Math.min(f.hp, (A.hit / 100) * A.dmg * A.times);
        const kill = A.dmg * A.times >= f.hp ? (A.hit / 100) : 0;
        const counterMax = D.canCounter ? D.dmg * D.times : 0;
        const counterExp = D.canCounter ? (D.hit / 100) * D.dmg * D.times : 0;
        // 击杀目标后，它不会再在敌方回合攻击
        const rr = riskAt(state, u, t, threat);
        const killsIt = kill > 0.6;
        const r = rr.dmg * bold;
        const hpAfter = u.hp - counterExp;
        let sc = exp * 1.5 + kill * (u.lord ? 45 : 30) - counterExp * 1.2 * bold - r * (u.lord ? 0.9 : 0.7) + (f.boss ? 4 : 0);
        if (counterMax >= u.hp && D.hit > 0) sc -= u.lord ? 300 : 80 * (D.hit / 100 + 0.3);
        if (rr.worst * (killsIt ? 0.7 : 1) >= hpAfter) sc -= u.lord ? 40 : 30 * bold;
        if (rr.dmg * (killsIt ? 0.75 : 1) >= hpAfter * (u.lord ? 0.85 : 1)) sc -= u.lord ? 250 : 50 * bold;
        if (A.dmg === 0) sc -= 40;
        if (keyHolder && f === keyHolder) sc += 25;
        // 最终首领：只要不会被反击打死，就积极进攻
        if (f.tag === 'final' && counterMax < u.hp) sc += 30;
        // 像普通玩家一样分配经验：等级低的人更优先拿击杀，老兵让出击杀
        const team = state.living('player').filter((p) => !p.escort);
        const avgLv = team.reduce((s2, p) => s2 + p.lv, 0) / Math.max(1, team.length);
        sc += kill * (avgLv - u.lv) * 4;
        if (u.id === 'glenn' && kill > 0.5 && avgLv < u.lv - 2) sc -= 12;
        if (!bestAtk || sc > bestAtk.sc) bestAtk = { sc, t, f, w };
      }
    }
  }
  if (bestAtk && bestAtk.sc > -5) {
    plan.dest = bestAtk.t;
    plan.action = { type: 'attack', target: bestAtk.f, weaponIdx: u.items.indexOf(bestAtk.w) };
    plan.atkScore = bestAtk.sc;
    return plan;
  }

  // 移动：朝目标推进，停在风险可接受的格子
  let goals = [];
  // 可招募目标：交谈者朝它移动
  const talkGoal = (state.ch.events || []).find((ev) => ev.on === 'talk' && ev.a === u.id && !state.fired.includes(ev.id) && state.findUnit(ev.b) && state.findUnit(ev.b).team !== 'player');
  if (talkGoal) {
    const tgt = state.findUnit(talkGoal.b);
    goals = [{ x: tgt.x, y: tgt.y }];
  } else if (obj.type === 'defend') {
    const dp = obj.defendTile;
    if (u.lord) goals = [{ x: dp[0], y: dp[1] }];
    else {
      const gates = [[dp[0], dp[1] - 2], [dp[0] - 3, dp[1]], [dp[0] + 3, dp[1]], [dp[0], dp[1] - 1]];
      const idx = state.living('player').indexOf(u) % gates.length;
      goals = [{ x: gates[idx][0], y: gates[idx][1] }];
    }
  } else if (obj.type === 'escape') {
    const esc = state.units.find((o) => o.escort && !o.hidden && !o.dead);
    // 朝撤离点推进开路（但不会停在撤离点上），清理护送目标附近的敌人
    goals = esc ? (obj.escape || []).map(([x, y]) => ({ x, y })) : [];
    const near = enemies(state).filter((e) => esc && Math.abs(e.x - esc.x) + Math.abs(e.y - esc.y) <= 10);
    if (near.length) goals = near.map((e) => ({ x: e.x, y: e.y }));
  } else {
    goals = enemies(state).map((e) => ({ x: e.x, y: e.y }));
    // 需要钥匙才能完成目标时，优先追击携带门钥匙的敌人
    const needKey = (state.ch.events || []).some((ev) => ev.on === 'door' && !state.fired.includes(ev.id))
      && !state.living('player').some((p) => hasTrait(p, 'lockpick') || state.doorKey(p) >= 0);
    if (needKey) {
      const holder = enemies(state).find((e) => e.drop && e.items.some((i) => ITEMS[i.id].key === 'door'));
      if (holder) goals = [{ x: holder.x, y: holder.y }];
    }
    goals.push(...objectiveTiles(state));
  }
  if (!goals.length) return plan;
  const df = distanceField(state, u, goals, false);
  let best = null;
  for (const t of stops) {
    const d = df.get(key(t.x, t.y)) ?? 999;
    const r = riskAt(state, u, t, threat);
    let sc = -d * 2 - r.dmg * bold * (u.lord ? 1.8 : 1.4) - (r.dmg >= u.hp * (u.lord ? 0.85 : 1) ? 150 : 0);
    if (r.worst >= u.hp) sc -= u.lord ? 40 : 25 * bold;
    if (r.n >= 3) sc -= 10;
    // 不要挡住护送目标的撤离点 / 王子要占领的王座
    if (obj.escape && obj.escape.some(([ex, ey]) => ex === t.x && ey === t.y)) sc -= 100;
    if (obj.seize && !u.lord && obj.seize[0] === t.x && obj.seize[1] === t.y) sc -= 200;
    // 脆弱单位（弓手、法师、修女）尽量待在同伴身后
    const frail = !R.usableWeapons(u).some((w) => R.weaponRange(u, w.id)[0] === 1) || u.def <= 4;
    if (frail && r.n > 0) sc -= 12 * r.n * bold;
    if (!best || sc > best.sc) best = { sc, t };
  }
  if (best) plan.dest = best.t;
  return plan;
}

// 执行一个计划（直接调用状态接口，不做演出）
export function executePlan(state, plan) {
  const u = plan.unit;
  const fx = u.x, fy = u.y;
  state.setPos(u, plan.dest.x, plan.dest.y);
  state.recordMove(u, fx, fy);
  const a = plan.action;
  let result = null;
  if (a) {
    switch (a.type) {
      case 'attack': {
        const quote = state.combatQuote(u, a.target);
        result = state.doAttack(u, a.target, a.weaponIdx);
        result.quote = quote;
        break;
      }
      case 'staff': result = state.doStaff(u, a.target, u.items.indexOf(a.staff)); break;
      case 'talk': result = state.doTalk(u, a.target); break;
      case 'visit': result = state.doVisit(u); break;
      case 'chest': result = state.doChest(u); break;
      case 'door': result = state.doDoor(u, a.x, a.y); break;
      case 'item': result = state.useItem(u, a.idx); break;
      case 'seize': state.doSeize(u); break;
      case 'escape': state.doEscape(u); break;
      default: break;
    }
  }
  if (!u.dead && !u.hidden) state.endAction(u);
  else state.checkOutcome();
  return result;
}

// 我方回合的行动顺序
export function playerOrder(state) {
  const us = state.living('player').filter((u) => !u.acted);
  const rank = (u) => (u.escort ? 100 : 0) + (R.usableStaves(u).length && !R.usableWeapons(u).length ? 50 : 0) + (u.lord ? 8 : 0) - (u.str + u.mag);
  return us.sort((a, b) => rank(a) - rank(b));
}

// 自动整备（模拟一个普通玩家的整备习惯）：人人带一瓶伤药、分发仓库里的好武器
export function autoPrep(c, ch) {
  const ids = c.available();
  const price = ITEMS.vulnerary.price;
  const healId = (u) => u.items.findIndex((i) => ITEMS[i.id].heal && ITEMS[i.id].type === 'item');
  for (const id of ids) {
    const u = c.roster[id];
    if (healId(u) >= 0 || u.items.length >= 5) continue;
    const ci = c.convoy.findIndex((i) => ITEMS[i.id].heal && ITEMS[i.id].type === 'item');
    if (ci >= 0) { u.items.push(c.convoy.splice(ci, 1)[0]); continue; }
    if (ch.shop && ch.shop.includes('vulnerary') && c.gold >= price + 100) { c.gold -= price; u.items.push({ id: 'vulnerary', uses: 3 }); }
  }
  // 仓库里能用的武器/魔法书交给能用的人
  for (let i = c.convoy.length - 1; i >= 0; i--) {
    const it = c.convoy[i];
    const d = ITEMS[it.id];
    if (d.type === 'item') continue;
    const who = ids.map((id) => c.roster[id]).find((u) => u.items.length < 5 && R.canUse(u, it.id) && !u.items.some((x) => x.id === it.id));
    if (who) { who.items.push(it); c.convoy.splice(i, 1); }
  }
  // 能力提升道具立刻使用
  for (const id of ids) {
    const u = c.roster[id];
    for (let i = u.items.length - 1; i >= 0; i--) {
      const d = ITEMS[u.items[i].id];
      if (!d.boost) continue;
      for (const [s, v] of Object.entries(d.boost)) { if (s === 'hp') { u.mhp += v; u.hp = u.mhp; } else u[s] += v; }
      u.items.splice(i, 1);
    }
    // 自动加点（推荐）
    if (u.points) { const p = R.recommendAlloc({ ...u, team: 'player' }); R.applyAlloc(u, p); }
  }
}

// 计划的优先级：特殊目标 > 击杀/攻击 > 治疗 > 移动
export function planScore(plan) {
  const a = plan.action;
  if (!a) return -100 - (plan.unit.lord ? 5 : 0);
  switch (a.type) {
    case 'escape': case 'seize': case 'talk': case 'door': case 'visit': case 'chest': return 200;
    case 'attack': return plan.atkScore ?? 0;
    case 'staff': return 20;
    case 'item': return 40;
    default: return 0;
  }
}

// 选出本步最该行动的单位（每步都重新评估所有未行动单位）
export function bestPlayerPlan(state) {
  const us = playerOrder(state);
  if (!us.length) return null;
  const threat = buildThreat(state);
  let best = null;
  for (const u of us) {
    const plan = planPlayer(state, u, threat);
    const sc = planScore(plan) - (u.escort ? 300 : 0);
    if (!best || sc > best.sc) best = { sc, plan };
  }
  return best.plan;
}

// 无头跑完我方一个回合
export function autoPlayerPhase(state) {
  let guard = 0;
  while (!state.outcome && guard++ < 40) {
    const plan = bestPlayerPlan(state);
    if (!plan) break;
    executePlan(state, plan);
  }
}
