// 战斗状态：地图、单位、回合、行动、事件、胜负判定。纯逻辑，不依赖 DOM，可在 Node 中测试。
import { terrainOf, OPENED } from './data/terrain.js';
import { CLASSES, STATS, ENEMY_CLASS_NAMES, hasTrait } from './data/classes.js';
import { ITEMS, makeItem } from './data/items.js';
import { CHARACTERS, BOSSES } from './data/characters.js';
import { RNG } from './rng.js';
import * as R from './rules.js';
import { moveRange, stoppable, tilesInRange, key } from './pathfind.js';
import { planAction } from './ai.js';

export const MAX_ITEMS = 5;

let UID = 1;

// ---- 单位构造 ----
export function statsAtLevel(clsId, lv) {
  const c = CLASSES[clsId];
  const s = {};
  for (const k of STATS) s[k] = c.base[k] + Math.floor(((c.growth[k] || 0) * (lv - 1)) / 100);
  return s;
}

function baseUnit(fields) {
  const u = {
    uid: 'u' + UID++, id: null, name: '', cls: 'soldier', team: 'enemy', lv: 1, exp: 0,
    hp: 1, mhp: 1, str: 0, mag: 0, skl: 0, spd: 0, lck: 0, def: 0, res: 0, mov: 5,
    items: [], equip: null, x: 0, y: 0, acted: false, dead: false, hidden: false,
    boss: false, lord: false, escort: false, portrait: null, battle: null, model: null,
    ai: null, provoked: false, drop: false, alloc: {}, points: 0, moved: 0,
  };
  return Object.assign(u, fields);
}

export function applyStats(u, s) {
  u.mhp = s.hp; u.hp = s.hp;
  for (const k of STATS) if (k !== 'hp') u[k] = s[k];
}

// 由存档里的角色数据生成战斗单位
export function unitFromRoster(r) {
  const u = baseUnit({});
  Object.assign(u, JSON.parse(JSON.stringify(r)));
  u.uid = 'u' + UID++;
  u.team = 'player';
  u.acted = false; u.dead = false; u.hidden = false; u.moved = 0;
  const ch = CHARACTERS[u.id];
  if (ch) { u.portrait = ch.portrait; u.battle = ch.battle; u.lord = !!ch.lord; }
  u.model = CLASSES[u.cls].model;
  return u;
}

// 新角色初始数据（存入名册的格式）
export function newRosterEntry(id) {
  const ch = CHARACTERS[id];
  const c = CLASSES[ch.cls];
  return {
    id, name: ch.name, cls: ch.cls, lv: ch.lv, exp: 0,
    hp: ch.stats.hp, mhp: ch.stats.hp, str: ch.stats.str, mag: ch.stats.mag, skl: ch.stats.skl, spd: ch.stats.spd,
    lck: ch.stats.lck, def: ch.stats.def, res: ch.stats.res, mov: c.mov,
    items: ch.items.map((i) => makeItem(i)), equip: null, alloc: {}, points: 0,
    kills: 0, battles: 0,
  };
}

// 把战斗单位写回名册格式
export function rosterFromUnit(u) {
  return {
    id: u.id, name: u.name, cls: u.cls, lv: u.lv, exp: u.exp, hp: u.mhp, mhp: u.mhp,
    str: u.str, mag: u.mag, skl: u.skl, spd: u.spd, lck: u.lck, def: u.def, res: u.res, mov: u.mov,
    items: u.items.map((i) => ({ id: i.id, uses: i.uses })), equip: u.equip, alloc: { ...(u.alloc || {}) }, points: u.points || 0,
    kills: u.kills || 0, battles: u.battles || 0,
  };
}

// 难度修正：敌方普通单位按等级成长；首领固定数值再加减
function makeChapterUnit(t, difficulty) {
  const team = t.team || 'enemy';
  let u;
  if (t.char) {
    // 可招募角色（希德、薇拉）或友军（多兰）：使用角色本身数据
    const r = newRosterEntry(t.char);
    u = baseUnit({ ...r, id: t.char, team, recruitable: !!t.recruitable });
    const ch = CHARACTERS[t.char];
    u.portrait = ch.portrait; u.battle = ch.battle;
    if (t.hp != null) u.hp = t.hp;
  } else if (t.boss && BOSSES[t.boss]) {
    const b = BOSSES[t.boss];
    u = baseUnit({ id: t.boss, name: b.name, cls: b.cls, lv: b.lv, team, boss: t.isBoss !== false, portrait: b.portrait, battle: b.battle });
    const s = { ...b.stats };
    if (team === 'enemy') {
      if (difficulty === 'easy') { s.hp -= 3; s.str -= 1; s.skl -= 1; s.spd -= 1; s.def -= 1; }
      if (difficulty === 'hard') { s.hp += 5; s.str += 2; s.skl += 2; s.spd += 2; s.def += 1; s.res += 1; }
    }
    applyStats(u, s);
    u.mov = CLASSES[b.cls].mov;
    u.items = (t.items || b.items).map((i) => makeItem(i));
  } else {
    let lv = t.lv || 1;
    if (team === 'enemy') {
      if (difficulty === 'easy') lv = Math.max(1, lv - 2);
      if (difficulty === 'hard') lv = lv + 1;
    }
    const s = statsAtLevel(t.cls, lv);
    if (team === 'enemy' && difficulty === 'hard') { s.str += 1; s.spd += 1; }
    if (team === 'enemy' && difficulty === 'easy') { s.skl = Math.max(0, s.skl - 1); }
    u = baseUnit({ id: t.id || t.cls, cls: t.cls, lv, team });
    applyStats(u, s);
    u.mov = CLASSES[t.cls].mov;
    u.items = (t.items || []).map((i) => makeItem(i));
    u.name = t.name || (team === 'enemy' ? (ENEMY_CLASS_NAMES[t.cls] || CLASSES[t.cls].name) : CLASSES[t.cls].name);
    u.portrait = t.portrait || (team === 'enemy' ? 'soldier' : 'villager');
    u.battle = t.battle || defaultBattleSet(t.cls, team);
  }
  if (t.name) u.name = t.name;
  u.model = CLASSES[u.cls].model;
  u.x = t.x; u.y = t.y;
  u.ai = t.ai ? (typeof t.ai === 'string' ? { mode: t.ai } : { ...t.ai }) : (team === 'player' ? null : { mode: 'aggressive' });
  u.drop = !!t.drop;
  u.escort = !!t.escort;
  u.caged = !!t.caged;
  u.tag = t.tag || null;
  if (t.escort) { u.noCounter = true; }
  if (t.hp != null) u.hp = Math.min(u.mhp, t.hp);
  return u;
}

export function defaultBattleSet(clsId, team) {
  const map = {
    soldier: 'soldier', fighter: 'fighter', mercenary: 'mercenary', archer: 'archer', mage: 'mage_e', darkmage: 'darkmage',
    knight: 'knight_e', cavalier: 'cavalier_e', pegasus: 'pegasus_e', wyvern: 'wyvern', priest: 'priest', general: 'general',
    cleric: 'priest', civilian: 'martha', usurper: 'valder',
  };
  return map[clsId] || 'soldier';
}

// ---- 战斗状态 ----
export class BattleState {
  constructor(chapter, campaign, opts = {}) {
    this.ch = chapter;
    this.chapterId = chapter.id;
    this.campaign = campaign;
    this.difficulty = campaign.difficulty;
    this.mode = campaign.mode;
    this.theme = chapter.theme;
    this.h = chapter.rows.length;
    this.w = chapter.rows[0].length;
    this.tiles = chapter.rows.map((r) => r.split(''));
    this.changed = [];            // 已改变的格子 [x,y]（开门、开箱、焚毁）
    this.units = [];
    this.turn = 1;
    this.phase = 'player';
    this.rng = new RNG(opts.seed != null ? opts.seed : (Date.now() >>> 0));
    this.fired = [];              // 已触发的事件 id
    this.flags = {};
    this.villages = {};           // "x,y" -> 'visited' | 'razed'
    this.chests = {};             // "x,y" -> 'opened'
    this.reinf = (chapter.reinforcements || []).map((g, i) => ({ ...g, idx: i, done: false }));
    this.outcome = null;
    this.defeatReason = null;
    this.queue = [];              // 交给界面播放的事件
    this.aiQueue = null;
    this.goldGained = 0;
    this.log = [];
    this._occ = null;
    if (!opts.empty) this._setup(opts);
  }

  _setup(opts) {
    const c = this.campaign;
    const diff = this.difficulty;
    // 我方
    const deployIds = opts.deploy || c.deploySlots(this.ch);
    const slots = this.ch.deploy;
    deployIds.forEach((id, i) => {
      const r = id && c.roster[id];
      if (!r || !slots[i]) return;
      const u = unitFromRoster(r);
      u.x = slots[i][0]; u.y = slots[i][1];
      this.units.push(u);
    });
    // 章节单位（按难度筛选）
    for (const t of this.ch.units) {
      if (t.diff && !t.diff.includes(diff)) continue;
      if (t.char && t.team !== 'npc' && (c.isDead(t.char) || c.isRecruited(t.char))) continue;
      this.units.push(makeChapterUnit(t, diff));
    }
    this._occ = null;
  }

  // ---- 基础查询 ----
  charAt(x, y) { return this.tiles[y] && this.tiles[y][x]; }
  terrainAt(x, y) { return terrainOf(this.charAt(x, y), this.theme); }
  inBounds(x, y) { return x >= 0 && y >= 0 && x < this.w && y < this.h; }

  unitAt(x, y) {
    if (!this._occ) {
      this._occ = new Map();
      for (const u of this.units) if (!u.dead && !u.hidden) this._occ.set(key(u.x, u.y), u);
    }
    return this._occ.get(key(x, y)) || null;
  }
  invalidate() { this._occ = null; }

  living(team = null) {
    return this.units.filter((u) => !u.dead && !u.hidden && (team == null || u.team === team));
  }
  findUnit(id) { return this.units.find((u) => u.id === id && !u.dead && !u.hidden) || null; }
  byUid(uid) { return this.units.find((u) => u.uid === uid) || null; }
  lord() { return this.units.find((u) => u.lord && u.team === 'player') || null; }

  setPos(u, x, y) { u.x = x; u.y = y; this._occ = null; }

  hostile(a, b) { return !R.sameSide(a, b); }

  push(ev) { this.queue.push(ev); }

  // ---- 条件 ----
  cond(expr) {
    if (!expr) return true;
    return expr.split('&').every((part) => {
      let p = part.trim();
      let neg = false;
      if (p.startsWith('!')) { neg = true; p = p.slice(1); }
      const [k, v] = p.split(':');
      let r = false;
      if (k === 'alive') r = !!this.findUnit(v) && this.findUnit(v).team === 'player';
      else if (k === 'onmap') r = !!this.findUnit(v);
      else if (k === 'recruited') r = this.campaign.isRecruited(v);
      else if (k === 'dead') r = this.campaign.isDead(v);
      else if (k === 'flag') r = !!this.flags[v] || !!this.campaign.flags[v];
      else if (k === 'diff') r = this.difficulty === v;
      else if (k === 'mode') r = this.mode === v;
      return neg ? !r : r;
    });
  }

  // ---- 移动 ----
  moveRangeOf(u) { return moveRange(this, u); }

  // 某单位在其当前位置可用武器能打到的敌人
  attackTargets(u, pos = null) {
    const p = pos || u;
    const res = [];
    for (const it of R.usableWeapons(u)) {
      const [a, b] = R.weaponRange(u, it.id);
      for (const t of tilesInRange(this, p.x, p.y, a, b)) {
        const o = this.unitAt(t.x, t.y);
        if (o && this.hostile(u, o) && !o.caged && !res.includes(o)) res.push(o);
      }
    }
    return res;
  }

  weaponsFor(u, target, pos = null) {
    const p = pos || u;
    const d = Math.abs(p.x - target.x) + Math.abs(p.y - target.y);
    return R.usableWeapons(u).filter((it) => R.inRange(u, it.id, d));
  }

  staffTargets(u) {
    const res = [];
    for (const it of R.usableStaves(u)) {
      const [a, b] = R.weaponRange(u, it.id);
      for (const t of tilesInRange(this, u.x, u.y, a, b)) {
        const o = this.unitAt(t.x, t.y);
        if (o && o !== u && !this.hostile(u, o) && o.hp < o.mhp && !res.includes(o)) res.push(o);
      }
    }
    return res;
  }

  adjacent(u) {
    const res = [];
    for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) {
      const o = this.unitAt(u.x + dx, u.y + dy);
      if (o) res.push(o);
    }
    return res;
  }

  talkTargets(u) {
    const res = [];
    for (const o of this.adjacent(u)) {
      const ev = this.talkEvent(u, o);
      if (ev) res.push(o);
    }
    return res;
  }

  talkEvent(a, b) {
    for (const ev of this.ch.events || []) {
      if (ev.on !== 'talk' || this.fired.includes(ev.id)) continue;
      if (ev.a === a.id && ev.b === b.id && this.cond(ev.cond)) return ev;
    }
    return null;
  }

  tradeTargets(u) {
    return this.adjacent(u).filter((o) => o.team === 'player' && !o.escort && (o.items.length || u.items.length));
  }

  canVisit(u) {
    const t = this.terrainAt(u.x, u.y);
    if (!t.village) return false;
    const k = u.x + ',' + u.y;
    if (this.villages[k]) return false;
    return (this.ch.villages || {})[k] != null && !u.escort;
  }

  chestKey(u) { return u.items.findIndex((i) => ITEMS[i.id].key === 'chest'); }
  doorKey(u) { return u.items.findIndex((i) => ITEMS[i.id].key === 'door'); }

  canOpenChest(u) {
    if (this.charAt(u.x, u.y) !== 'C') return false;
    if (this.chests[u.x + ',' + u.y]) return false;
    return hasTrait(u, 'lockpick') || this.chestKey(u) >= 0;
  }

  doorsNear(u) {
    if (!(hasTrait(u, 'lockpick') || this.doorKey(u) >= 0)) return [];
    const res = [];
    for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) {
      const x = u.x + dx, y = u.y + dy;
      if (this.charAt(x, y) === 'D') res.push({ x, y });
    }
    return res;
  }

  canSeize(u) {
    const s = this.ch.objective.seize;
    if (!s || !u.lord) return false;
    if (u.x !== s[0] || u.y !== s[1]) return false;
    const boss = this.units.find((o) => o.boss && o.team === 'enemy' && o.tag === 'final');
    return !boss || boss.dead;
  }

  canEscape(u) {
    const esc = this.ch.objective.escape;
    if (!esc || !u.escort) return false;
    return esc.some(([x, y]) => x === u.x && y === u.y);
  }

  // 行动菜单：返回可用行动（顺序即菜单顺序）
  actionsFor(u) {
    const acts = [];
    if (this.canSeize(u)) acts.push('seize');
    if (this.canEscape(u)) acts.push('escape');
    if (this.attackTargets(u).length) acts.push('attack');
    if (this.staffTargets(u).length) acts.push('staff');
    if (this.talkTargets(u).length) acts.push('talk');
    if (this.canVisit(u)) acts.push('visit');
    if (this.canOpenChest(u)) acts.push('chest');
    if (this.doorsNear(u).length) acts.push('door');
    if (u.items.length) acts.push('item');
    if (this.tradeTargets(u).length) acts.push('trade');
    acts.push('wait');
    return acts;
  }

  // ---- 行动 ----
  recordMove(u, fromX, fromY) {
    u.moved = Math.abs(u.x - fromX) + Math.abs(u.y - fromY);
    this._areaEvents(u);
  }

  _areaEvents(u) {
    for (const ev of this.ch.events || []) {
      if (ev.on !== 'area' || this.fired.includes(ev.id)) continue;
      if (u.team !== (ev.team || 'player')) continue;
      const [x, y, w, h] = ev.rect;
      if (u.x >= x && u.x < x + w && u.y >= y && u.y < y + h && this.cond(ev.cond)) {
        this.fire(ev);
      }
    }
  }

  fire(ev, extra = {}) {
    if (ev.id && !ev.repeat) this.fired.push(ev.id);
    if (ev.script) this.push({ type: 'script', id: ev.script, ...extra });
    if (ev.flag) this.flags[ev.flag] = true;
    if (ev.effect) this._effect(ev.effect, extra);
  }

  _effect(effect, extra) {
    for (const e of [].concat(effect)) {
      const [k, v] = e.split(':');
      if (k === 'recruit') this.recruit(this.findUnit(v));
      else if (k === 'free') this.freeCaged(v);
      else if (k === 'flag') this.flags[v] = true;
      else if (k === 'activate') this.units.forEach((o) => { if (o.ai && o.ai.group === v) o.provoked = true; });
    }
  }

  recruit(u) {
    if (!u || u.team === 'player') return;
    u.team = 'player';
    u.ai = null;
    u.recruitable = false;
    u.caged = false;
    u.acted = false;
    this.campaign.addRecruit(u.id, rosterFromUnit(u));
    this.push({ type: 'recruit', unit: u });
    this.invalidate();
  }

  freeCaged(id) {
    const u = this.units.find((o) => o.id === id && o.caged);
    if (!u) return;
    u.caged = false;
    this.recruit(u);
    this.flags['freed_' + id] = true;
  }

  // 攻击：返回战斗结果供界面演出
  doAttack(u, target, weaponIdx = null) {
    if (weaponIdx != null) u.equip = weaponIdx;
    const w = R.equipped(u);
    const pre = { attHp: u.hp, defHp: target.hp };
    const res = R.resolveCombat(this, u, { x: u.x, y: u.y }, target, w.id, this.rng, { moved: u.moved });
    res.pre = pre;
    res.att = u; res.def = target;
    target.provoked = true;
    if (target.ai && target.ai.group) this._effect('activate:' + target.ai.group);
    this._afterCombat(res);
    return res;
  }

  _afterCombat(res) {
    const { att, def } = res;
    res.exp = [];
    res.drops = [];
    // 经验（只有我方单位获得）
    for (const [me, foe, side] of [[att, def, 'att'], [def, att, 'def']]) {
      if (me.team !== 'player' || me.hp <= 0 || me.escort) continue;
      const dealt = res.dealt[side];
      const killed = foe.hp <= 0;
      const participated = side === 'att' || res.strikes.some((s) => s.who === 'def');
      if (!participated) continue;
      const amt = R.combatExp(me, foe, dealt, killed);
      const before = { lv: me.lv, exp: me.exp };
      const ups = R.gainExp(me, amt, this.rng);
      res.exp.push({ unit: me, amount: amt, before, ups });
      if (killed) me.kills = (me.kills || 0) + 1;
      me.battles = (me.battles || 0) + 1;
    }
    for (const u of [att, def]) {
      if (u.hp <= 0) this.kill(u, u === att ? def : att, res);
    }
    this.checkOutcome();
  }

  kill(u, killer, res = null) {
    if (u.dead) return;
    u.dead = true;
    u.hp = 0;
    this.invalidate();
    // 掉落
    if (u.drop && killer && killer.team === 'player' && u.items.length) {
      const it = u.items[u.items.length - 1];
      const got = this.giveItem(killer, { id: it.id, uses: it.uses });
      if (res) res.drops.push({ unit: killer, item: it.id, toConvoy: got === 'convoy' });
    }
    if (u.team === 'player') {
      if (u.lord) { this.outcome = 'defeat'; this.defeatReason = 'lord'; }
      else if (u.escort) { this.outcome = 'defeat'; this.defeatReason = 'escort'; }
      else if (this.mode === 'casual') { u.retreated = true; }
      else this.campaign.markDead(u.id);
      this.push({ type: 'death', unit: u, script: (this.mode === 'casual' && !u.lord && !u.escort ? 'retreat_' : 'death_') + u.id });
    } else if (u.team === 'ally' || u.recruitable) {
      if (CHARACTERS[u.id]) this.campaign.markLost(u.id);
      this.push({ type: 'death', unit: u, script: 'death_' + u.id });
    } else {
      this.push({ type: 'death', unit: u });
    }
    for (const ev of this.ch.events || []) {
      if (ev.on === 'death' && ev.unit === u.id && !this.fired.includes(ev.id) && this.cond(ev.cond)) this.fire(ev);
    }
  }

  giveItem(u, item) {
    if (u && u.items.length < MAX_ITEMS) { u.items.push(item); return 'unit'; }
    this.campaign.convoy.push(item);
    return 'convoy';
  }

  // 首领战前对白
  combatQuote(att, def) {
    const pairs = [[att, def], [def, att]];
    for (const [boss, other] of pairs) {
      if (!boss.boss && !boss.quotes) continue;
      for (const ev of this.ch.events || []) {
        if (ev.on !== 'combat' || ev.unit !== boss.id || this.fired.includes(ev.id)) continue;
        if (ev.with && (ev.with !== other.id || other.team !== 'player')) continue;
        if (!this.cond(ev.cond)) continue;
        this.fired.push(ev.id);
        // 同一首领的通用台词和专属台词只播一个
        if (ev.with) this.fired.push(...(this.ch.events || []).filter((e) => e.on === 'combat' && e.unit === boss.id && !e.with).map((e) => e.id));
        return ev.script;
      }
    }
    return null;
  }

  doStaff(u, target, staffIdx) {
    const it = u.items[staffIdx];
    const amt = R.healAmount(u, it.id, target);
    target.hp += amt;
    const expAmt = R.staffExp(u, it.id);
    const before = { lv: u.lv, exp: u.exp };
    const ups = u.team === 'player' ? R.gainExp(u, expAmt, this.rng) : [];
    return { type: 'heal', healer: u, target, amount: amt, exp: u.team === 'player' ? [{ unit: u, amount: expAmt, before, ups }] : [] };
  }

  doTalk(u, target) {
    const ev = this.talkEvent(u, target);
    if (!ev) return null;
    this.fire(ev);
    if (ev.recruit) this.recruit(target);
    return ev.script;
  }

  doVisit(u) {
    const k = u.x + ',' + u.y;
    const v = (this.ch.villages || {})[k];
    this.villages[k] = 'visited';
    const out = { script: v.script, item: null, gold: 0 };
    if (v.item) { const got = this.giveItem(u, makeItem(v.item)); out.item = v.item; out.toConvoy = got === 'convoy'; }
    if (v.gold) {
      const g = this.campaign.scaleGold(v.gold);
      this.campaign.gold += g;
      this.goldGained += g;
      out.gold = g;
    }
    if (v.flag) this.flags[v.flag] = true;
    this.campaign.flags['visited_' + this.chapterId + '_' + k] = true;
    return out;
  }

  razeVillage(x, y) {
    const k = x + ',' + y;
    this.villages[k] = 'razed';
    this.tiles[y][x] = OPENED.V;
    this.changed.push([x, y]);
    this.push({ type: 'razed', x, y });
  }

  doChest(u) {
    const k = u.x + ',' + u.y;
    const c = (this.ch.chests || {})[k];
    this.chests[k] = 'opened';
    this.changed.push([u.x, u.y]);
    if (!hasTrait(u, 'lockpick')) this.consumeUse(u, this.chestKey(u));
    const out = { item: null, gold: 0 };
    if (c && c.item) { const got = this.giveItem(u, makeItem(c.item)); out.item = c.item; out.toConvoy = got === 'convoy'; }
    if (c && c.gold) { const g = this.campaign.scaleGold(c.gold); this.campaign.gold += g; this.goldGained += g; out.gold = g; }
    return out;
  }

  doDoor(u, x, y) {
    this.tiles[y][x] = OPENED.D;
    this.changed.push([x, y]);
    if (!hasTrait(u, 'lockpick')) this.consumeUse(u, this.doorKey(u));
    this.invalidate();
    const evs = [];
    for (const ev of this.ch.events || []) {
      if (ev.on === 'door' && ev.at[0] === x && ev.at[1] === y && !this.fired.includes(ev.id) && this.cond(ev.cond)) {
        this.fire(ev, { opener: u.id });
        evs.push(ev);
      }
    }
    return evs;
  }

  consumeUse(u, idx) {
    if (idx < 0) return;
    const it = u.items[idx];
    it.uses -= 1;
    if (it.uses <= 0) {
      u.items.splice(idx, 1);
      if (u.equip != null) {
        if (u.equip === idx) u.equip = null;
        else if (u.equip > idx) u.equip -= 1;
      }
    }
  }

  // 使用道具：返回效果描述
  useItem(u, idx) {
    const it = u.items[idx];
    const d = ITEMS[it.id];
    const out = { item: it.id, heal: 0, boost: null };
    if (d.heal) {
      out.heal = R.itemHeal(u, it.id);
      u.hp += out.heal;
    }
    if (d.boost) {
      out.boost = {};
      for (const [s, v] of Object.entries(d.boost)) {
        const cap = R.capOf(u, s);
        const cur = s === 'hp' ? u.mhp : u[s];
        const add = Math.max(0, Math.min(v, cap - cur));
        if (s === 'hp') { u.mhp += add; u.hp += add; } else u[s] += add;
        out.boost[s] = add;
      }
    }
    this.consumeUse(u, idx);
    return out;
  }

  canUseItem(u, idx) {
    const it = u.items[idx];
    const d = ITEMS[it.id];
    if (d.type !== 'item') return { ok: false, why: '这不是消耗品' };
    if (d.key) return { ok: false, why: '钥匙会在开门或开箱时自动使用' };
    if (d.heal && u.hp >= u.mhp) return { ok: false, why: 'HP 已满' };
    if (d.boost) {
      const room = Object.entries(d.boost).some(([s]) => (s === 'hp' ? u.mhp : u[s]) < R.capOf(u, s));
      if (!room) return { ok: false, why: '已达职业上限' };
    }
    return { ok: true };
  }

  doSeize(u) {
    this.outcome = 'victory';
    this.push({ type: 'seize', unit: u });
  }

  doEscape(u) {
    u.hidden = true;
    this.invalidate();
    this.flags['escaped_' + u.id] = true;
    for (const ev of this.ch.events || []) {
      if (ev.on === 'escape' && ev.unit === u.id && !this.fired.includes(ev.id)) this.fire(ev);
    }
    this.checkOutcome();
  }

  endAction(u) {
    u.acted = true;
    this.checkOutcome();
  }

  // ---- 胜负 ----
  checkOutcome() {
    if (this.outcome) return this.outcome;
    const lord = this.lord();
    if (!lord || lord.dead) { this.outcome = 'defeat'; this.defeatReason = 'lord'; return this.outcome; }
    const esc = this.units.find((u) => u.escort);
    if (esc && esc.dead) { this.outcome = 'defeat'; this.defeatReason = 'escort'; return this.outcome; }
    const obj = this.ch.objective;
    const dp = obj.defendTile;
    if (dp) {
      const o = this.unitAt(dp[0], dp[1]);
      if (o && o.team === 'enemy') { this.outcome = 'defeat'; this.defeatReason = 'occupied'; return this.outcome; }
    }
    const enemies = this.living('enemy').filter((u) => !u.recruitable);
    const boss = this.units.find((u) => u.boss && u.team === 'enemy');
    switch (obj.type) {
      case 'boss':
        if (boss && boss.dead) this.outcome = 'victory';
        break;
      case 'rout':
        if (enemies.length === 0 && obj.need && !this.cond(obj.need)) {
          // 防卡关：驻军全灭但牢门还没打开（钥匙随阵亡者遗失等）→ 自动打开牢门救出囚犯
          for (const ev of this.ch.events || []) {
            if (ev.on === 'door' && !this.fired.includes(ev.id)) {
              const [x, y] = ev.at;
              if (this.tiles[y][x] === 'D') { this.tiles[y][x] = OPENED.D; this.changed.push([x, y]); this.invalidate(); }
              this.push({ type: 'notice', text: '驻军全灭。众人在狱卒的腰带上找到了备用钥匙，打开了牢门。' });
              this.fire(ev, { opener: 'elwin' });
            }
          }
        }
        if ((!obj.need || this.cond(obj.need)) && enemies.length === 0) this.outcome = 'victory';
        break;
      case 'escape':
        if (esc && this.flags['escaped_' + esc.id]) this.outcome = 'victory';
        break;
      case 'defend':
        if (boss && boss.dead) { this.outcome = 'victory'; this.flags.bossKilled = true; }
        break;
      default: break;
    }
    return this.outcome;
  }

  // ---- 回合 ----
  // 战斗开始：开场事件 + 第一回合
  begin() {
    for (const ev of this.ch.events || []) {
      if (ev.on === 'start' && !this.fired.includes(ev.id) && this.cond(ev.cond)) this.fire(ev);
    }
    this.startPlayerPhase();
  }

  // 开始我方回合：地形回复、事件、增援预告
  startPlayerPhase() {
    this.phase = 'player';
    for (const u of this.living()) if (u.team === 'player') { u.acted = false; u.moved = 0; }
    this._terrainHeal('player');
    this._turnEvents('player');
    this.checkOutcome();
  }

  warnings() {
    // 下回合将出现的增援位置（在我方回合显示）
    const out = [];
    for (const g of this.reinf) {
      if (g.done || !this._groupActive(g)) continue;
      if (g.turn === this.turn + 1) for (const u of g.units) if (!u.diff || u.diff.includes(this.difficulty)) out.push({ x: u.x, y: u.y });
    }
    return out;
  }

  _groupActive(g) {
    if (g.diff && !g.diff.includes(this.difficulty)) return false;
    return this.cond(g.cond);
  }

  endPlayerPhase() {
    for (const u of this.living('player')) u.acted = true;
    this.phase = 'enemy';
    for (const u of this.living('enemy')) { u.acted = false; u.moved = 0; }
    this._terrainHeal('enemy');
    this._turnEvents('enemy');
    this.aiQueue = this._aiOrder('enemy');
  }

  _aiOrder(team) {
    const us = this.living(team).filter((u) => !u.caged);
    const players = this.living().filter((u) => u.team !== team && !R.sameSide(u, us[0] || u));
    const dist = (u) => {
      let m = 999;
      for (const p of players) m = Math.min(m, Math.abs(p.x - u.x) + Math.abs(p.y - u.y));
      return m;
    };
    const rank = (u) => (u.ai && u.ai.mode === 'support' ? 1000 : 0) + (u.boss ? 500 : 0) + dist(u);
    return us.sort((a, b) => rank(a) - rank(b)).map((u) => u.uid);
  }

  // 下一个 AI 行动（界面负责演出，然后调用 applyAi）
  nextAi() {
    while (this.aiQueue && this.aiQueue.length) {
      const uid = this.aiQueue.shift();
      const u = this.byUid(uid);
      if (!u || u.dead || u.hidden || u.acted || u.caged) continue;
      const plan = planAction(this, u);
      return plan;
    }
    return null;
  }

  // 执行 AI 计划：先移动，再行动。返回行动结果
  applyAi(plan) {
    const u = plan.unit;
    if (plan.dest && (plan.dest.x !== u.x || plan.dest.y !== u.y)) {
      const fx = u.x, fy = u.y;
      this.setPos(u, plan.dest.x, plan.dest.y);
      u.moved = Math.abs(u.x - fx) + Math.abs(u.y - fy);
    }
    let result = null;
    const a = plan.action;
    if (a) {
      if (a.type === 'attack') {
        const quote = this.combatQuote(u, a.target);
        result = this.doAttack(u, a.target, u.items.indexOf(a.weapon));
        result.quote = quote;
        result.type = 'combat';
      } else if (a.type === 'staff') {
        result = this.doStaff(u, a.target, u.items.indexOf(a.staff));
      } else if (a.type === 'raze') {
        this.razeVillage(u.x, u.y);
        result = { type: 'raze', x: u.x, y: u.y };
      } else if (a.type === 'chest') {
        const k = u.x + ',' + u.y;
        const c = (this.ch.chests || {})[k];
        this.chests[k] = 'opened';
        this.changed.push([u.x, u.y]);
        if (c && c.item) u.items.push(makeItem(c.item));
        result = { type: 'steal', item: c && c.item };
      } else if (a.type === 'escape') {
        u.hidden = true;
        this.invalidate();
        result = { type: 'flee', unit: u };
      }
    }
    u.acted = true;
    this.checkOutcome();
    return result;
  }

  // 敌方回合结束：生成增援 → 友军回合或下一回合
  endEnemyPhase() {
    this._spawnReinforcements();
    const obj = this.ch.objective;
    if (obj.type === 'defend' && this.turn >= obj.turns && !this.outcome) {
      this.outcome = 'victory';
      this.flags.defended = true;
    }
    if (this.living('ally').length) {
      this.phase = 'ally';
      for (const u of this.living('ally')) u.acted = false;
      this._terrainHeal('ally');
      this.aiQueue = this._aiOrder('ally');
      return 'ally';
    }
    return this.nextTurn();
  }

  nextTurn() {
    this.turn += 1;
    this.startPlayerPhase();
    return 'player';
  }

  _terrainHeal(team) {
    for (const u of this.living(team)) {
      const t = this.terrainAt(u.x, u.y);
      if (t.heal && u.hp < u.mhp) {
        const amt = Math.min(u.mhp - u.hp, Math.max(1, Math.floor((u.mhp * t.heal) / 100)));
        u.hp += amt;
        this.push({ type: 'terrainHeal', unit: u, amount: amt });
      }
    }
  }

  _turnEvents(phase) {
    for (const ev of this.ch.events || []) {
      if (ev.on !== 'turn' || this.fired.includes(ev.id)) continue;
      if ((ev.phase || 'player') !== phase) continue;
      if (ev.turn != null && ev.turn !== this.turn) continue;
      if (ev.from != null && this.turn < ev.from) continue;
      if (!this.cond(ev.cond)) continue;
      this.fire(ev);
    }
    // 增援预告
    if (phase === 'player') {
      for (const g of this.reinf) {
        if (!g.done && g.turn === this.turn + 1 && g.warn && this._groupActive(g) && !this.fired.includes('warn' + g.idx)) {
          this.fired.push('warn' + g.idx);
          this.push({ type: 'script', id: g.warn });
          this.push({ type: 'warn', group: g.idx });
        }
      }
    }
  }

  _spawnReinforcements() {
    const spawned = [];
    for (const g of this.reinf) {
      if (g.done || g.turn !== this.turn + 1) continue;
      g.done = true;
      if (!this._groupActive(g)) continue;
      // 敌人已全灭时不再出现（“全灭”胜利已判定）
      if (this.outcome) continue;
      for (const t of g.units) {
        if (t.diff && !t.diff.includes(this.difficulty)) continue;
        const pos = this._freeNear(t.x, t.y, t.cls);
        if (!pos) continue;
        const u = makeChapterUnit({ ...t, x: pos.x, y: pos.y }, this.difficulty);
        u.acted = true;
        this.units.push(u);
        this.invalidate();
        spawned.push(u);
      }
    }
    if (spawned.length) this.push({ type: 'spawn', units: spawned });
    return spawned;
  }

  _freeNear(x, y, clsId) {
    const fake = { cls: clsId, team: 'enemy' };
    for (let r = 0; r <= 2; r++) {
      for (const t of r === 0 ? [{ x, y }] : tilesInRange(this, x, y, r, r)) {
        if (this.unitAt(t.x, t.y)) continue;
        const c = this.terrainAt(t.x, t.y).cost[CLASSES[clsId].moveType];
        if (c == null) continue;
        void fake;
        return t;
      }
    }
    return null;
  }

  // 是否还有我方单位可以行动
  playerCanAct() {
    return this.living('player').some((u) => !u.acted);
  }

  // ---- 结算（写回战役）----
  finish() {
    const c = this.campaign;
    for (const u of this.units) {
      if (u.team !== 'player' || u.escort) continue;
      if (!CHARACTERS[u.id]) continue;
      if (u.dead && this.mode === 'classic') continue;
      const r = rosterFromUnit(u);
      r.hp = r.mhp;
      c.roster[u.id] = r;
    }
  }

  // ---- 存档 ----
  toJSON() {
    return {
      chapterId: this.chapterId, turn: this.turn, phase: this.phase, rng: this.rng.state,
      tiles: this.tiles.map((r) => r.join('')), changed: this.changed, fired: this.fired, flags: this.flags,
      villages: this.villages, chests: this.chests, reinf: this.reinf.map((g) => g.done),
      goldGained: this.goldGained,
      units: this.units.map((u) => ({ ...u, items: u.items.map((i) => ({ ...i })) })),
    };
  }

  static fromJSON(data, chapter, campaign) {
    const s = new BattleState(chapter, campaign, { empty: true });
    s.turn = data.turn;
    s.phase = data.phase;
    s.rng.state = data.rng;
    s.tiles = data.tiles.map((r) => r.split(''));
    s.changed = data.changed || [];
    s.fired = data.fired || [];
    s.flags = data.flags || {};
    s.villages = data.villages || {};
    s.chests = data.chests || {};
    (data.reinf || []).forEach((d, i) => { if (s.reinf[i]) s.reinf[i].done = d; });
    s.goldGained = data.goldGained || 0;
    s.units = data.units.map((u) => ({ ...u }));
    let maxUid = 0;
    for (const u of s.units) maxUid = Math.max(maxUid, parseInt(String(u.uid).slice(1), 10) || 0);
    if (UID <= maxUid) UID = maxUid + 1;
    s.invalidate();
    return s;
  }
}
