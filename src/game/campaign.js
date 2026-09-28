// 战役进度：名册、仓库、金钱、难度、模式、剧情旗标、章节阶段、存档
import { newRosterEntry } from './battle.js';
import { makeItem } from './data/items.js';
import { PLAYABLE, CHARACTERS } from './data/characters.js';

export const SAVE_VERSION = 1;
export const DIFFICULTY_NAMES = { easy: '简单', normal: '普通', hard: '困难' };
export const MODE_NAMES = { casual: '休闲模式', classic: '经典模式' };

export class Campaign {
  constructor() {
    this.difficulty = 'normal';
    this.pendingDifficulty = null;
    this.mode = 'classic';
    this.chapter = 0;          // 0..4 对应第一~五章
    this.stage = 'prologue';   // prologue | pre | prep | battle | post | ending | complete
    this.roster = {};
    this.order = [];
    this.recruited = [];
    this.dead = [];
    this.lost = [];
    this.convoy = [];
    this.gold = 0;
    this.flags = {};
    this.playtime = 0;          // 秒
    this.tutorial = {};         // 已显示过的教学提示
    this.formation = {};        // 章节 id -> 出击顺序（id 列表）
    this.log = [];
  }

  static newGame(difficulty, mode) {
    const c = new Campaign();
    c.difficulty = difficulty;
    c.mode = mode;
    for (const id of ['elwin', 'glenn', 'nora', 'serin']) c.addRecruit(id, newRosterEntry(id));
    c.gold = { easy: 1500, normal: 800, hard: 400 }[difficulty];
    c.convoy = [makeItem('vulnerary')];
    if (difficulty === 'easy') c.convoy.push(makeItem('vulnerary'), makeItem('elixir'));
    if (difficulty === 'hard') c.convoy = [];
    return c;
  }

  isRecruited(id) { return this.recruited.includes(id); }
  isDead(id) { return this.dead.includes(id) || this.lost.includes(id); }
  isAlive(id) { return this.isRecruited(id) && !this.dead.includes(id); }

  addRecruit(id, data) {
    if (!this.recruited.includes(id)) this.recruited.push(id);
    if (!this.order.includes(id)) this.order.push(id);
    this.roster[id] = data;
  }

  markDead(id) {
    if (!this.dead.includes(id)) this.dead.push(id);
  }

  markLost(id) {
    if (!this.lost.includes(id) && !this.isRecruited(id)) this.lost.push(id);
  }

  // 当前可出击的角色（按名册顺序，王子第一）
  available() {
    return this.order.filter((id) => this.isAlive(id) && this.roster[id]);
  }

  deployList(ch) {
    const avail = this.available();
    const saved = this.formation[ch.id];
    let list = saved ? saved.filter((id) => avail.includes(id)) : avail.slice();
    for (const id of avail) if (!list.includes(id) && list.length < ch.deploy.length) list.push(id);
    // 王子必须出击且在第一位
    list = ['elwin', ...list.filter((id) => id !== 'elwin')];
    return list.slice(0, ch.deploy.length);
  }

  // 出击点分配（与 ch.deploy 对齐，空位为 null）；“调整站位”保存的站位优先
  deploySlots(ch) {
    const list = this.deployList(ch);
    const fs = this.formationSlots && this.formationSlots[ch.id];
    if (fs && fs.length === ch.deploy.length) {
      const ids = fs.filter(Boolean);
      if (ids.length === list.length && ids.every((id) => list.includes(id))) return fs.slice();
    }
    return ch.deploy.map((_, i) => list[i] || null);
  }

  scaleGold(g) {
    const m = { easy: 1.5, normal: 1, hard: 0.7 }[this.difficulty] || 1;
    return Math.round((g * m) / 10) * 10;
  }

  // 剧情脚本条件（alive = 在队且存活）
  cond(expr) {
    if (!expr) return true;
    return expr.split('&').every((part) => {
      let p = part.trim();
      let neg = false;
      if (p.startsWith('!')) { neg = true; p = p.slice(1); }
      const [k, v] = p.split(':');
      let r = false;
      if (k === 'alive') r = v === 'elwin' ? true : this.isAlive(v);
      else if (k === 'dead') r = this.dead.includes(v) || this.lost.includes(v);
      else if (k === 'recruited') r = this.isRecruited(v);
      else if (k === 'flag') r = !!this.flags[v];
      else if (k === 'mode') r = this.mode === v;
      else if (k === 'diff' || k === 'difficulty') r = this.difficulty === v;
      return neg ? !r : r;
    });
  }

  // 章节开始时生效的难度变更
  applyPendingDifficulty() {
    if (this.pendingDifficulty && this.pendingDifficulty !== this.difficulty) {
      this.difficulty = this.pendingDifficulty;
    }
    this.pendingDifficulty = null;
  }

  toJSON() {
    return {
      v: SAVE_VERSION, difficulty: this.difficulty, pendingDifficulty: this.pendingDifficulty, mode: this.mode,
      chapter: this.chapter, stage: this.stage, roster: this.roster, order: this.order, recruited: this.recruited,
      dead: this.dead, lost: this.lost, convoy: this.convoy, gold: this.gold, flags: this.flags,
      playtime: this.playtime, tutorial: this.tutorial, formation: this.formation, formationSlots: this.formationSlots || {},
    };
  }

  static fromJSON(d) {
    const c = new Campaign();
    Object.assign(c, JSON.parse(JSON.stringify(d)));
    delete c.v;
    return c;
  }

  partySummary() {
    return this.available().map((id) => (CHARACTERS[id] ? CHARACTERS[id].name : id));
  }
}

export { PLAYABLE };
