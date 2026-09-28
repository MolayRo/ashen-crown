// 战斗地图场景：我方回合操作、敌方/友军回合演出、事件、胜负
import { W, H } from '../../core/renderer.js';
import { fill, drawWindow } from '../../core/gfx.js';
import { drawText, drawTextScaled, textWidth, wrapText } from '../../core/font.js';
import { TaskRunner } from '../../core/tasks.js';
import { settings, speedMul } from '../../core/settings.js';
import { audio } from '../../core/audio.js';
import { ListMenu } from '../../ui/menu.js';
import { MapView, TS } from './view.js';
import * as HUD from './hud.js';
import { key, unkey, pathTo, stoppable, tilesInRange } from '../../game/pathfind.js';
import { threatTiles, addUnitThreat } from '../../game/ai.js';
import * as R from '../../game/rules.js';
import { ITEMS } from '../../game/data/items.js';
import { CLASSES, hasTrait } from '../../game/data/classes.js';
import { CHARACTERS } from '../../game/data/characters.js';
import { hasScript } from '../../game/story/index.js';
import { StoryScene } from '../story.js';
import { ConfirmDialog } from '../confirm.js';
import { SettingsScene } from '../settings.js';
import { SaveLoadScene } from '../saveload.js';
import { HelpScene } from '../help.js';
import { UnitInfoScene } from '../unitinfo.js';
import { ItemMenuScene, TradeScene, ConvoyScene } from '../items.js';
import { BattleAnimScene, HealAnimScene } from '../battleanim.js';
import { GameOverScene } from '../gameover.js';
import { battleWon, toTitle } from '../flowctl.js';
import { bestPlayerPlan } from '../../game/autoplay.js';

const ACTION_NAMES = {
  seize: '占领', escape: '撤离', attack: '攻击', staff: '杖', talk: '交谈', visit: '访问', chest: '开箱', door: '开门',
  item: '物品', trade: '交换', supply: '运输队', wait: '待机',
};

const TUTORIAL = {
  start: ['【教学】用方向键或鼠标移动光标，选中蓝色的我方单位后按 Z（或左键）。', '蓝色格子是移动范围，红色格子是攻击范围。'],
  move: ['【教学】选择目的地后会弹出行动菜单。', '移动之后、行动之前按 X（或右键）可以撤销移动。'],
  forecast: ['【教学】这是战斗预测：伤害、命中、必杀、是否追击(×2)与反击。', '剑克斧、斧克枪、枪克剑，优势方会显示绿色箭头。'],
  heal: ['【教学】赛琳可以用“杖”治疗相邻的伙伴，治疗也能获得经验。'],
  terrain: ['【教学】森林、丘陵等地形能提高防御与回避，画面右下角可以查看。', '按 R 显示敌人的威胁范围，按 C 查看单位的详细资料。'],
  endturn: ['【教学】全部单位行动完毕后回合会自动结束；', '也可以按 E 或在地图菜单中“结束回合”。'],
  village: ['【教学】让单位停在村庄入口选择“访问”，能获得道具并保护村民。', '敌人会烧毁没被访问的村庄！'],
  talk: ['【教学】单位头上出现气泡时，可以让指定的人去“交谈”，也许能让对方加入。'],
  levelup: ['【教学】升级时除了随机成长，还会获得 2 点潜能点。', '在地图菜单或整备中“部队 → 加点”自由分配。'],
};

export class MapScene {
  constructor(state, opts = {}) {
    this.state = state;
    this.fresh = opts.fresh !== false;
    this.view = new MapView(state);
    this.tasks = new TaskRunner();
    this.mode = 'intro';
    this.sel = null;
    this.origin = null;
    this.range = null;
    this.moveSet = null;
    this.menu = null;
    this.targets = null;
    this.tIndex = 0;
    this.showThreat = false;
    this.notice = null;
    this.banner = null;
    this.hpPanels = null;
    this.expBar = null;
    this.levelUp = null;
    this.committed = false;
    this.autoplay = false;
    this.speedup = false;
  }

  get ch() { return this.state.ch; }

  enter(game) {
    this.game = game;
    this.campaign = game.campaign;
    const s = this.state;
    const lord = s.lord();
    if (lord) { this.view.cursor = { x: lord.x, y: lord.y }; this.view.centerOn(lord.x, lord.y, true); }
    game.fadeLevel = 1;
    game.fadeTarget = 0;
    if (game.autotest) {
      this.autoplay = true;
      this.speedup = true;
      if (game.autotestNote) game.autotestNote(`${this.ch.id} 开战（${this.state.living('player').length} 人出击）`);
    }
    this.tasks.add(this.introSeq());
  }

  // ---------------------------------------------------------------- 协程
  *introSeq() {
    const s = this.state;
    this.mode = 'busy';
    if (this.fresh) {
      audio.playMusic(this.ch.music.player);
      yield 20;
      s.begin();
      yield* this.runQueue();
      if (this.ch.tutorial) this.tutorial('start');
      if (this.ch.warning) {
        const dp = this.ch.objective.defendTile;
        if (dp) { this.view.centerOn(dp[0], dp[1]); this.view.cursor = { x: dp[0], y: dp[1] }; yield* this.wait(20); }
        this.game.push(new TutorialOverlay([this.ch.warning], { title: '注意', style: 'red' }));
        yield;
      }
      yield* this.bannerSeq('我方回合', `第 ${s.turn} 回合`, '#1c3a8a');
      this.updateMarkers();
      yield* this.runQueue();
    } else {
      audio.playMusic(s.phase === 'enemy' ? this.ch.music.enemy : this.ch.music.player);
      if (s.phase !== 'player') {
        // 读取到非我方回合的存档（理论上不会发生），直接继续敌方回合
        yield* this.enemyPhase(true);
        return;
      }
      this.updateMarkers();
      yield 10;
    }
    this.toIdle();
  }

  *bannerSeq(text, sub, color) {
    if (text === '我方回合' || text === '敌方回合' || text === '友军回合') audio.sfx('phase');
    this.banner = { text, sub, color, t: 0 };
    while (this.banner.t < 70) {
      this.banner.t += this.fastNow() ? 3 : 1;
      if (this.game.input.confirm() || this.game.input.click()) this.banner.t = Math.max(this.banner.t, 58);
      yield;
    }
    this.banner = null;
  }

  fastNow() { return this.game.input.fast() || this.speedup; }

  *wait(n) {
    let t = 0;
    while (t < n) { t += (this.fastNow() ? 3 : 1) * speedMul(); yield; }
  }

  *playScript(id) {
    if (!id || !hasScript(id)) return;
    let done = false;
    this.game.push(new StoryScene(id, { overlay: true, campaign: this.campaign, battle: this.state, onDone: () => { done = true; } }));
    yield () => done;
  }

  *runQueue() {
    const s = this.state;
    let guard = 0;
    while (s.queue.length && guard++ < 100) {
      const ev = s.queue.shift();
      switch (ev.type) {
        case 'script':
          yield* this.playScript(ev.id);
          break;
        case 'death':
          yield* this.deathSeq(ev);
          break;
        case 'recruit': {
          const u = ev.unit;
          this.notice = { lines: [`${u.name} 加入了队伍！`], t: 110, style: 'blue' };
          const a = this.animOf(u);
          for (let i = 0; i < 12; i++) { a.flash = (i % 4 < 2) ? 0.8 : 0; a.flashColor = '#a0d0ff'; yield 2; }
          a.flash = 0;
          break;
        }
        case 'razed': {
          audio.sfx('burn');
          this.view.centerOn(ev.x, ev.y);
          for (let i = 0; i < 3; i++) this.view.effects.push({ name: 'fire', x: ev.x * TS + (i - 1) * 4, y: ev.y * TS - 2 + (i % 2) * 3, t: i * 5, life: 70 });
          yield* this.wait(30);
          this.notice = { lines: ['村庄被追兵烧毁了……'], t: 100, style: 'red' };
          yield* this.wait(40);
          break;
        }
        case 'spawn': {
          audio.sfx('warn');
          const first = ev.units[0];
          if (first) { this.view.centerOn(first.x, first.y); yield* this.wait(20); }
          for (const u of ev.units) { const a = this.animOf(u); a.alpha = 0; }
          for (let i = 0; i <= 10; i++) { for (const u of ev.units) this.animOf(u).alpha = i / 10; yield 2; }
          this.notice = { lines: ['敌军增援出现了！'], t: 90, style: 'red' };
          yield* this.wait(30);
          break;
        }
        case 'warn':
          this.updateMarkers();
          audio.sfx('warn');
          if (this.view.markers.length) {
            const m = this.view.markers[0];
            this.view.centerOn(m.x, m.y);
            yield* this.wait(40);
          }
          this.notice = { lines: ['注意：红色“!”处下回合将出现敌军增援。'], t: 150, style: 'red' };
          break;
        case 'terrainHeal':
          if (!ev.unit.dead) this.view.addFloater(ev.unit.x, ev.unit.y, '+' + ev.amount, '#80ff90', 50);
          break;
        case 'notice':
          audio.sfx('door');
          this.notice = { lines: [ev.text], t: 150, style: 'blue' };
          yield* this.wait(60);
          break;
        default: break;
      }
    }
  }

  animOf(u) {
    let a = this.view.anims.get(u.uid);
    if (!a) { a = {}; this.view.anims.set(u.uid, a); }
    return a;
  }

  *deathSeq(ev) {
    const u = ev.unit;
    if (u.team === 'player' || u.recruitable || u.team === 'ally') {
      if (ev.script && hasScript(ev.script) && !u.lord) yield* this.playScript(ev.script);
    }
    audio.sfx('death');
    const a = this.animOf(u);
    a.fading = true;
    for (let i = 10; i >= 0; i--) { a.alpha = i / 10; a.flash = i % 2 ? 0.6 : 0; yield 3; }
    a.fading = false;
    this.view.anims.delete(u.uid);
    if (u.team === 'player' && !u.lord && !u.escort) {
      this.notice = { lines: [this.state.mode === 'casual' ? `${u.name} 撤退了。本章结束后归队。` : `${u.name} 阵亡了……`], t: 110, style: 'dark' };
    }
  }

  *moveSeq(u, path) {
    if (!path || path.length < 2) return;
    const a = this.animOf(u);
    a.moving = true;
    a.walkT = 0;
    const mt = CLASSES[u.cls].moveType;
    for (let i = 1; i < path.length; i++) {
      const p0 = path[i - 1], p1 = path[i];
      a.dir = p1.x > p0.x ? 'right' : p1.x < p0.x ? 'left' : p1.y > p0.y ? 'down' : 'up';
      if (i % 2 === 1) audio.sfx(mt === 'horse' ? 'step_horse' : mt === 'fly' ? 'wing' : 'step', { vol: 0.5 });
      const steps = Math.max(2, Math.round(8 / speedMul() / (this.fastNow() ? 2 : 1)));
      for (let k = 1; k <= steps; k++) {
        a.px = (p0.x + (p1.x - p0.x) * (k / steps)) * TS;
        a.py = (p0.y + (p1.y - p0.y) * (k / steps)) * TS;
        a.walkT += 1;
        if (u.team !== 'player') this.view.follow(Math.round(a.px / TS), Math.round(a.py / TS), 3);
        yield;
      }
    }
  }

  endMoveAnim(u) {
    const a = this.view.anims.get(u.uid);
    if (a) { a.moving = false; a.dir = null; }
  }

  // ---------------------------------------------------------------- 战斗演出
  *combatSeq(res) {
    const s = this.state;
    if (settings.battleAnim === 1) {
      let done = false;
      this.game.push(new BattleAnimScene(res, { state: s, onDone: () => { done = true; } }));
      yield () => done;
    } else {
      yield* this.mapCombat(res);
    }
    for (const e of res.exp || []) yield* this.expSeq(e);
    for (const d of res.drops || []) {
      audio.sfx('item');
      this.notice = { lines: [`${d.unit.name} 获得了 ${ITEMS[d.item].name}` + (d.toConvoy ? '（物品已满，送往运输队）' : '')], t: 120, style: 'blue' };
      yield* this.wait(50);
    }
    yield* this.runQueue();
  }

  // 治疗演出：完整演出时切到侧视画面，简略时在地图上闪光飘字
  *healSeq(res, staffId) {
    if (settings.battleAnim === 1 && res.amount > 0) {
      let done = false;
      this.game.push(new HealAnimScene(res, { state: this.state, staffId, onDone: () => { done = true; } }));
      yield () => done;
      return;
    }
    const target = res.target;
    audio.sfx('heal');
    this.view.effects.push({ name: 'sparkle', x: target.x * TS + 4, y: target.y * TS + 2, t: 0, life: 40 });
    const b = this.animOf(target);
    for (let i = 0; i < 8; i++) { b.flash = i % 2 ? 0 : 0.5; b.flashColor = '#a0ffb0'; yield 3; }
    b.flash = 0;
    this.view.addFloater(target.x, target.y, '+' + res.amount, '#80ff90', 60);
    yield* this.wait(30);
  }

  *mapCombat(res) {
    const { att, def } = res;
    let hpA = res.pre.attHp, hpD = res.pre.defHp;
    this.hpPanels = { att, def, hpA, hpD };
    this.view.centerOn(def.x, def.y);
    yield* this.wait(10);
    for (const st of res.strikes) {
      const src = st.who === 'att' ? att : def;
      const tgt = st.who === 'att' ? def : att;
      const a = this.animOf(src);
      const dx = Math.sign(tgt.x - src.x) * 5, dy = Math.sign(tgt.y - src.y) * 5;
      const w = R.equipped(src);
      const wd = w ? ITEMS[w.id] : null;
      audio.sfx(wd ? (wd.type === 'bow' ? 'bow' : wd.type === 'tome' ? (wd.spell || 'fire') : wd.type === 'lance' ? 'lance' : wd.type === 'axe' ? 'axe' : 'sword') : 'sword');
      for (let i = 1; i <= 4; i++) { a.offx = (dx * i) / 4; a.offy = (dy * i) / 4; yield; }
      const b = this.animOf(tgt);
      if (st.hit) {
        audio.sfx(st.crit ? 'crit' : st.dmg === 0 ? 'nodmg' : 'hit');
        this.view.addFloater(tgt.x, tgt.y, st.crit ? `必杀 ${st.dmg}` : String(st.dmg), st.crit ? '#ffd040' : '#ff8070', 50);
        if (st.crit) this.view.shake = 12;
        for (let i = 0; i < 6; i++) { b.flash = i % 2 ? 0 : 0.9; b.offx = (i % 2 ? -1 : 1); yield 2; }
        b.flash = 0; b.offx = 0;
      } else {
        audio.sfx('miss');
        this.view.addFloater(tgt.x, tgt.y, 'MISS', '#c8d8ff', 45);
        for (let i = 0; i < 4; i++) { b.offx = -Math.sign(dx) * 2; yield 2; }
        b.offx = 0;
      }
      hpA = st.attHp; hpD = st.defHp;
      this.hpPanels = { att, def, hpA, hpD };
      for (let i = 4; i >= 0; i--) { a.offx = (dx * i) / 4; a.offy = (dy * i) / 4; yield; }
      yield* this.wait(14);
    }
    yield* this.wait(16);
    this.hpPanels = null;
  }

  *expSeq(e) {
    const u = e.unit;
    if (!e.amount || u.dead) return;
    let cur = e.before.exp;
    const target = e.before.exp + e.amount;
    this.expBar = { name: u.name, exp: cur };
    audio.sfx('text', { vol: 0.2 });
    yield* this.wait(10);
    // 反推升级前的能力
    const snaps = [];
    const tmp = { ...u };
    for (let i = e.ups.length - 1; i >= 0; i--) {
      const g = e.ups[i].gains;
      const beforeLv = e.ups[i].lv - 1;
      for (const [k, v] of Object.entries(g)) { if (k === 'hp') tmp.mhp -= v; else tmp[k] -= v; }
      snaps.unshift({ lv: beforeLv, mhp: tmp.mhp, str: tmp.str, mag: tmp.mag, skl: tmp.skl, spd: tmp.spd, lck: tmp.lck, def: tmp.def, res: tmp.res });
    }
    let upIdx = 0;
    while (cur < target) {
      cur = Math.min(target, cur + (this.fastNow() ? 4 : 1) * speedMul());
      this.expBar.exp = cur % 100 === 0 && cur > 0 && cur === target ? 100 : cur % 100;
      if (Math.floor(cur) % 4 === 0) audio.sfx('text', { vol: 0.15 });
      if (cur >= 100 * (upIdx + 1) && upIdx < e.ups.length) {
        this.expBar.exp = 100;
        yield* this.wait(10);
        this.expBar = null;
        yield* this.levelUpSeq(u, snaps[upIdx], e.ups[upIdx].gains);
        upIdx++;
        this.expBar = { name: u.name, exp: 0 };
      }
      yield;
    }
    yield* this.wait(18);
    this.expBar = null;
  }

  *levelUpSeq(u, before, gains) {
    audio.sfx('levelup');
    this.levelUp = { u, before: { ...before }, gains, shown: 0, t: 0 };
    const temp = { ...u, ...before };
    this.levelUp.before = { ...before, name: u.name };
    // 以升级后等级显示
    this.levelUp.uDisp = { ...u };
    yield* this.wait(40);
    const keys = ['hp', 'str', 'mag', 'skl', 'spd', 'lck', 'def', 'res'];
    for (let i = 0; i < keys.length; i++) {
      this.levelUp.shown = i + 1;
      if (gains[keys[i]]) { audio.sfx('statup'); yield* this.wait(10); } else yield 2;
    }
    yield* this.wait(50);
    // 等待确认
    let t = 0;
    while (t++ < 240 && !(this.game.input.confirm() || this.game.input.click() || this.fastNow())) { this.levelUp.t = t; yield; }
    this.levelUp = null;
    void temp;
    if (this.campaign && !this.campaign.tutorial.levelup) this.tutorial('levelup');
  }

  // ---------------------------------------------------------------- 我方行动执行
  *doActionSeq(kind, payload) {
    const s = this.state;
    const u = this.sel;
    this.mode = 'busy';
    this.clearOverlays();
    let endTurnForUnit = true;
    switch (kind) {
      case 'attack': {
        const { target, weaponIdx } = payload;
        const quote = s.combatQuote(u, target);
        if (quote) yield* this.playScript(quote);
        const res = s.doAttack(u, target, weaponIdx);
        yield* this.combatSeq(res);
        break;
      }
      case 'staff': {
        const { target, idx } = payload;
        const staffId = u.items[idx] ? u.items[idx].id : null;
        const res = s.doStaff(u, target, idx);
        yield* this.healSeq(res, staffId);
        for (const e of res.exp) yield* this.expSeq(e);
        break;
      }
      case 'talk': {
        const script = s.doTalk(u, payload.target);
        if (script) yield* this.playScript(script);
        yield* this.runQueue();
        break;
      }
      case 'visit': {
        const r = s.doVisit(u);
        audio.sfx('visit');
        if (r.script) yield* this.playScript(r.script);
        const lines = [];
        if (r.item) lines.push(`获得了 ${ITEMS[r.item].name}` + (r.toConvoy ? '（物品已满，送往运输队）' : ''));
        if (r.gold) lines.push(`获得了 ${r.gold} 金`);
        if (lines.length) { audio.sfx(r.gold ? 'gold' : 'item'); this.notice = { lines, t: 120, style: 'blue' }; yield* this.wait(40); }
        break;
      }
      case 'chest': {
        audio.sfx('chest');
        const r = s.doChest(u);
        yield* this.wait(20);
        const lines = [];
        if (r.item) lines.push(`${u.name} 获得了 ${ITEMS[r.item].name}` + (r.toConvoy ? '（物品已满，送往运输队）' : ''));
        if (r.gold) lines.push(`获得了 ${r.gold} 金`);
        if (!lines.length) lines.push('宝箱是空的……');
        audio.sfx('item');
        this.notice = { lines, t: 120, style: 'blue' };
        yield* this.wait(40);
        break;
      }
      case 'door': {
        audio.sfx('door');
        s.doDoor(u, payload.x, payload.y);
        yield* this.wait(20);
        yield* this.runQueue();
        break;
      }
      case 'seize': {
        audio.sfx('confirm');
        s.doSeize(u);
        break;
      }
      case 'escape': {
        audio.sfx('confirm');
        const a = this.animOf(u);
        a.fading = true;
        for (let i = 10; i >= 0; i--) { a.alpha = i / 10; yield 2; }
        a.fading = false;
        s.doEscape(u);
        yield* this.runQueue();
        break;
      }
      case 'item': {
        const r = payload.result;
        if (r.heal) { audio.sfx('heal'); this.view.addFloater(u.x, u.y, '+' + r.heal, '#80ff90', 60); }
        if (r.boost) {
          audio.sfx('statup');
          const txt = Object.entries(r.boost).map(([k, v]) => `${k === 'hp' ? '最大HP' : { str: '力量', mag: '魔力', skl: '技巧', spd: '速度', lck: '幸运', def: '防御', res: '魔防' }[k]} +${v}`).join('　');
          this.notice = { lines: [`${u.name}：${txt}`], t: 120, style: 'blue' };
        }
        yield* this.wait(40);
        break;
      }
      case 'wait':
      default:
        break;
    }
    if (!u.dead && !u.hidden && endTurnForUnit) s.endAction(u);
    else s.checkOutcome();
    this.endMoveAnim(u);
    yield* this.runQueue();
    this.sel = null;
    this.committed = false;
    if (s.outcome) { yield* this.finishSeq(); return; }
    if (!s.playerCanAct()) {
      yield* this.wait(10);
      if (this.ch.tutorial && !this.campaign.tutorial.endturn) this.tutorial('endturn');
      yield* this.enemyPhase();
      return;
    }
    this.toIdle(true);
  }

  // ---------------------------------------------------------------- 敌方/友军回合
  *enemyPhase(resume = false) {
    const s = this.state;
    this.mode = 'enemy';
    this.clearOverlays();
    this.view.markers = [];
    if (!resume) s.endPlayerPhase();
    audio.playMusic(this.ch.music.enemy);
    yield* this.bannerSeq('敌方回合', `第 ${s.turn} 回合`, '#8a1c24');
    yield* this.runQueue();
    yield* this.aiLoop();
    if (s.outcome) { yield* this.finishSeq(); return; }
    const ph = s.endEnemyPhase();
    yield* this.runQueue();
    if (s.outcome) { yield* this.finishSeq(); return; }
    if (ph === 'ally') {
      yield* this.bannerSeq('友军回合', '', '#1c6a2c');
      yield* this.aiLoop();
      if (s.outcome) { yield* this.finishSeq(); return; }
      s.nextTurn();
    }
    // 我方回合
    audio.playMusic(this.ch.music.player);
    yield* this.bannerSeq('我方回合', `第 ${s.turn} 回合`, '#1c3a8a');
    yield* this.runQueue();
    if (s.outcome) { yield* this.finishSeq(); return; }
    this.updateMarkers();
    const lord = s.lord();
    if (lord && settings.autoCursor) { this.view.cursor = { x: lord.x, y: lord.y }; this.view.centerOn(lord.x, lord.y); }
    this.toIdle(true);
  }

  *aiLoop() {
    const s = this.state;
    let plan;
    let guard = 0;
    while (!s.outcome && (plan = s.nextAi()) && guard++ < 200) {
      const u = plan.unit;
      const moves = plan.dest && (plan.dest.x !== u.x || plan.dest.y !== u.y);
      if (!moves && !plan.action) { u.acted = true; continue; }
      this.view.centerOn(u.x, u.y);
      let t = 0;
      while (!this.view.camSettled && t++ < 20) yield;
      yield* this.wait(6);
      if (moves && plan.path) yield* this.moveSeq(u, plan.path);
      let quote = null;
      if (plan.action && plan.action.type === 'attack') {
        quote = s.combatQuote(u, plan.action.target);
        if (quote) yield* this.playScript(quote);
      }
      const res = s.applyAi(plan);
      this.endMoveAnim(u);
      if (res) {
        if (res.type === 'combat') yield* this.combatSeq(res);
        else if (res.type === 'heal') {
          const st = R.usableStaves(res.healer)[0];
          yield* this.healSeq(res, st ? st.id : null);
        } else if (res.type === 'steal') {
          audio.sfx('chest');
          this.notice = { lines: [`${u.name} 抢走了宝箱里的${res.item ? ITEMS[res.item].name : '东西'}！`], t: 110, style: 'red' };
          yield* this.wait(40);
        } else if (res.type === 'flee') {
          this.notice = { lines: [`${u.name} 逃走了。`], t: 90, style: 'dark' };
          yield* this.wait(30);
        } else if (res.type === 'raze') {
          yield* this.runQueue();
        }
      } else {
        yield* this.wait(4);
      }
      yield* this.runQueue();
    }
  }

  // ---------------------------------------------------------------- 胜负
  *finishSeq() {
    const s = this.state;
    this.mode = 'done';
    this.clearOverlays();
    yield* this.wait(20);
    if (this.game.autotestNote) this.game.autotestNote(`${this.ch.id} ${s.outcome === 'victory' ? '胜利' : '失败(' + s.defeatReason + ')'}，第 ${s.turn} 回合；我方：` + s.units.filter((u) => u.team === 'player' && !u.escort).map((u) => `${u.name}Lv${u.lv}${u.dead ? '†' : ''}`).join(' '));
    if (s.outcome === 'victory') {
      if (s.flags.defended && this.ch.id === 'ch4' && !s.flags.bossKilled) yield* this.playScript('ch4_boss_retreat');
      audio.playJingle('victory');
      this.bigText = { text: '胜　利', color: '#f8d860', t: 0 };
      yield* this.wait(150);
      this.bigText = null;
      battleWon(this.game, s);
    } else {
      audio.stopMusic(0.6);
      const why = s.defeatReason;
      if (why === 'lord') yield* this.playScript('gameover_elwin');
      else if (why === 'escort') yield* this.playScript('gameover_martha');
      audio.playJingle('gameover');
      this.game.push(new GameOverScene(s, why));
    }
  }

  // ---------------------------------------------------------------- 模式切换
  toIdle(recompute = false) {
    this.mode = 'idle';
    this.menu = null;
    this.targets = null;
    this.clearOverlays();
    if (this.showThreat) this.view.overlays.threat = threatTiles(this.state);
    if (recompute) this.unitRanges = null;
    if (this.unitRangeSet && this.unitRangeSet.size) this.rebuildUnitRange();
    this.game.input.consumeAll();
  }

  clearOverlays() {
    const ov = this.view.overlays;
    ov.move = ov.attack = ov.staff = null;
    this.view.path = null;
  }

  updateMarkers() {
    this.view.markers = this.state.warnings();
  }

  // 教学提示：第一次遇到时弹出一个小窗口，按键或点击后关闭（不会挡住之后的操作）
  tutorial(k) {
    if (!this.campaign || this.campaign.tutorial[k]) return;
    this.campaign.tutorial[k] = true;
    this.game.push(new TutorialOverlay(TUTORIAL[k]));
  }

  selectUnit(u) {
    const s = this.state;
    this.sel = u;
    this.origin = { x: u.x, y: u.y };
    this.range = s.moveRangeOf(u);
    const stops = stoppable(s, u, this.range);
    this.moveSet = new Set(stops.map((t) => key(t.x, t.y)));
    const atk = new Set();
    const staff = new Set();
    const weapons = R.usableWeapons(u);
    const staves = R.usableStaves(u);
    for (const t of stops) {
      for (const w of weapons) { const [a, b] = R.weaponRange(u, w.id); for (const r of tilesInRange(s, t.x, t.y, a, b)) if (!this.moveSet.has(key(r.x, r.y))) atk.add(key(r.x, r.y)); }
      for (const w of staves) { const [a, b] = R.weaponRange(u, w.id); for (const r of tilesInRange(s, t.x, t.y, a, b)) if (!this.moveSet.has(key(r.x, r.y))) staff.add(key(r.x, r.y)); }
    }
    this.view.overlays.move = this.moveSet;
    this.view.overlays.attack = weapons.length ? atk : null;
    this.view.overlays.staff = !weapons.length && staves.length ? staff : null;
    this.mode = 'move';
    audio.sfx('select');
    if (this.ch.tutorial) {
      if (!this.campaign.tutorial.move) this.tutorial('move');
      else if (u.id === 'serin' && !this.campaign.tutorial.heal) this.tutorial('heal');
    }
  }

  rebuildUnitRange() {
    const set = new Set();
    for (const uid of this.unitRangeSet) {
      const u = this.state.byUid(uid);
      if (!u || u.dead || u.hidden) { this.unitRangeSet.delete(uid); continue; }
      addUnitThreat(this.state, u, set, u.ai && u.ai.mode === 'guard');
    }
    this.view.overlays.unitRange = set.size ? set : null;
  }

  // ---------------------------------------------------------------- 更新
  update(game) {
    this.view.update();
    if (this.campaign) this.campaign.playtime += 1 / 60;
    if (this.notice && --this.notice.t <= 0) this.notice = null;
    if (this.bigText) this.bigText.t++;
    if (this.tasks.busy) {
      this.tasks.update();
      return;
    }
    const input = game.input;
    // 自动演示（验收用）：我方回合由 AI 代为操作
    if (this.autoplay && this.mode === 'idle' && this.state.phase === 'player') { this.autoStep(); return; }
    switch (this.mode) {
      case 'idle': this.updateIdle(input); break;
      case 'move': this.updateMove(input); break;
      case 'action': this.updateAction(input); break;
      case 'weapon': this.updateWeapon(input); break;
      case 'target': this.updateTarget(input); break;
      default: break;
    }
  }

  moveCursor(input, restrict = null) {
    const v = this.view;
    const d = input.dir();
    let moved = false;
    if (d) {
      const nx = v.cursor.x + (d === 'left' ? -1 : d === 'right' ? 1 : 0);
      const ny = v.cursor.y + (d === 'up' ? -1 : d === 'down' ? 1 : 0);
      if (this.state.inBounds(nx, ny)) { v.cursor = { x: nx, y: ny }; moved = true; }
    }
    if (input.mouse.moved && input.mouse.inside) {
      const t = v.tileAt(input.mouse.x, input.mouse.y);
      if (this.state.inBounds(t.x, t.y) && (t.x !== v.cursor.x || t.y !== v.cursor.y)) { v.cursor = t; moved = true; }
    }
    if (moved) {
      audio.sfx('cursor', { vol: 0.35 });
      v.follow(v.cursor.x, v.cursor.y);
      if (this.ch.tutorial && this.campaign && this.campaign.tutorial.move && !this.campaign.tutorial.terrain) {
        const t = this.state.terrainAt(v.cursor.x, v.cursor.y);
        if (t.forest) this.tutorial('terrain');
      }
    }
    return moved;
  }

  updateIdle(input) {
    const s = this.state;
    this.moveCursor(input);
    const c = this.view.cursor;
    const u = s.unitAt(c.x, c.y);
    if (input.pressed('threat')) {
      this.showThreat = !this.showThreat;
      this.view.overlays.threat = this.showThreat ? threatTiles(s) : null;
      audio.sfx(this.showThreat ? 'confirm' : 'cancel');
      this.notice = { lines: [this.showThreat ? '显示敌方威胁范围（紫色）' : '隐藏敌方威胁范围'], t: 60, style: 'dark' };
      return;
    }
    if (input.pressed('info')) {
      if (u) { audio.sfx('confirm'); this.game.push(new UnitInfoScene(u, { state: s })); }
      return;
    }
    if (input.pressed('next')) {
      const list = s.living('player').filter((x) => !x.acted);
      if (list.length) {
        const i = (list.findIndex((x) => x.x === c.x && x.y === c.y) + 1) % list.length;
        this.view.cursor = { x: list[i].x, y: list[i].y };
        this.view.follow(list[i].x, list[i].y, 3);
        audio.sfx('cursor');
      }
      return;
    }
    if (input.pressed('menu')) { this.openMapMenu(); return; }
    if (input.pressed('end')) { this.askEndTurn(); return; }
    if (input.confirm() || (input.click() && input.mouse.inside)) {
      if (u && u.team === 'player' && !u.acted) { this.selectUnit(u); return; }
      if (u && (u.team !== 'player')) {
        this.unitRangeSet = this.unitRangeSet || new Set();
        if (this.unitRangeSet.has(u.uid)) this.unitRangeSet.delete(u.uid); else this.unitRangeSet.add(u.uid);
        this.rebuildUnitRange();
        audio.sfx(this.unitRangeSet.has(u.uid) ? 'select' : 'cancel');
        return;
      }
      this.openMapMenu();
      return;
    }
    if (input.cancel()) {
      if (this.unitRangeSet && this.unitRangeSet.size) { this.unitRangeSet.clear(); this.rebuildUnitRange(); audio.sfx('cancel'); }
    }
  }

  updateMove(input) {
    const s = this.state;
    const u = this.sel;
    this.moveCursor(input);
    const c = this.view.cursor;
    const k = key(c.x, c.y);
    this.view.path = this.range.has(k) ? pathTo(this.range, c.x, c.y) : null;
    if (input.pressed('info')) { this.game.push(new UnitInfoScene(s.unitAt(c.x, c.y) || u, { state: s })); return; }
    if (input.cancel()) {
      audio.sfx('cancel');
      this.sel = null;
      this.view.cursor = { x: u.x, y: u.y };
      this.toIdle();
      return;
    }
    if (input.confirm() || (input.click() && input.mouse.inside)) {
      if (c.x === u.x && c.y === u.y) { this.openActionMenu(); return; }
      if (this.moveSet.has(k)) { this.startMove(c.x, c.y); return; }
      // 直接点击敌人：移动到能攻击它的位置
      const tgt = s.unitAt(c.x, c.y);
      if (tgt && s.hostile(u, tgt) && !tgt.caged) {
        const spot = this.bestSpotToAttack(u, tgt);
        if (spot) { this.pendingAttack = tgt; this.startMove(spot.x, spot.y); return; }
      }
      audio.sfx('error');
    }
  }

  bestSpotToAttack(u, tgt) {
    const s = this.state;
    let best = null;
    for (const k of this.moveSet) {
      const { x, y } = unkey(k);
      const d = Math.abs(x - tgt.x) + Math.abs(y - tgt.y);
      const ok = R.usableWeapons(u).some((w) => R.inRange(u, w.id, d));
      if (!ok) continue;
      const t = s.terrainAt(x, y);
      const cost = this.range.get(k).cost;
      const sc = (t.def || 0) * 3 + (t.avo || 0) * 0.2 - cost * 0.5 + (this.view.path && this.view.path.length && this.view.path[this.view.path.length - 1].x === x && this.view.path[this.view.path.length - 1].y === y ? 50 : 0);
      if (!best || sc > best.sc) best = { x, y, sc };
    }
    return best;
  }

  startMove(x, y) {
    const s = this.state;
    const u = this.sel;
    const path = pathTo(this.range, x, y);
    this.clearOverlays();
    this.mode = 'busy';
    audio.sfx('confirm');
    const self = this;
    this.tasks.add((function* () {
      yield* self.moveSeq(u, path);
      s.setPos(u, x, y);
      self.endMoveAnim(u);
      s.recordMove(u, self.origin.x, self.origin.y);
      self.view.cursor = { x, y };
      // 区域事件
      if (s.queue.length) yield* self.runQueue();
      if (s.outcome) { yield* self.finishSeq(); return; }
      self.openActionMenu();
    })());
  }

  undoMove() {
    const s = this.state;
    const u = this.sel;
    if (!this.committed) {
      s.setPos(u, this.origin.x, this.origin.y);
      u.moved = 0;
    }
    this.view.cursor = { x: u.x, y: u.y };
    this.selectUnit(u);
  }

  openActionMenu() {
    const s = this.state;
    const u = this.sel;
    this.clearOverlays();
    const acts = s.actionsFor(u);
    if (u.lord && !acts.includes('supply')) acts.splice(acts.indexOf('item') >= 0 ? acts.indexOf('item') + 1 : acts.length - 1, 0, 'supply');
    const items = acts.map((a) => ({ label: ACTION_NAMES[a], value: a }));
    const sp = this.view.screenOf(u.x, u.y);
    const right = sp.x < W / 2;
    this.menu = new ListMenu(items, { x: right ? W - 76 : 6, y: 6, w: 70, visible: items.length, rowH: 14, padY: 4 });
    this.mode = 'action';
    const talk = s.talkTargets(u);
    this.talkMarks = new Set(talk.map((t) => t.uid));
    if (this.pendingAttack && acts.includes('attack') && s.attackTargets(u).includes(this.pendingAttack)) {
      const tgt = this.pendingAttack;
      this.pendingAttack = null;
      this.menu.setIndex(items.findIndex((i) => i.value === 'attack'), true);
      this.beginAttack(tgt);
      return;
    }
    this.pendingAttack = null;
    if (this.ch.tutorial) {
      if (acts.includes('visit')) this.tutorial('village');
      if (acts.includes('talk')) this.tutorial('talk');
    }
  }

  updateAction(input) {
    const r = this.menu.update(input);
    if (!r) return;
    if (r.type === 'cancel') { this.undoMove(); return; }
    if (r.type !== 'select') return;
    const s = this.state;
    const u = this.sel;
    switch (r.item.value) {
      case 'attack': this.beginAttack(); break;
      case 'staff': this.beginTargets('staff', s.staffTargets(u)); break;
      case 'talk': this.beginTargets('talk', s.talkTargets(u)); break;
      case 'trade': this.beginTargets('trade', s.tradeTargets(u)); break;
      case 'door': this.beginTargets('door', s.doorsNear(u)); break;
      case 'visit': this.act('visit'); break;
      case 'chest': this.act('chest'); break;
      case 'seize': this.act('seize'); break;
      case 'escape': this.act('escape'); break;
      case 'wait': this.act('wait'); break;
      case 'item':
        this.game.push(new ItemMenuScene(u, {
          state: s, inBattle: true,
          onUse: (result) => { this.act('item', { result }); },
          onChange: () => { this.committed = this.committed; },
        }));
        break;
      case 'supply':
        this.game.push(new ConvoyScene(this.campaign, u, { onClose: () => { this.openActionMenu(); } }));
        break;
      default: break;
    }
  }

  act(kind, payload = {}) {
    this.menu = null;
    this.tasks.add(this.doActionSeq(kind, payload));
  }

  beginAttack(preTarget = null) {
    const s = this.state;
    const u = this.sel;
    const weapons = R.usableWeapons(u).filter((w) => s.attackTargets(u).some((t) => s.weaponsFor(u, t).includes(w)));
    if (!weapons.length) { audio.sfx('error'); return; }
    this.preTarget = preTarget;
    if (weapons.length === 1) { this.chooseWeapon(u.items.indexOf(weapons[0])); return; }
    const items = weapons.map((w) => {
      const d = ITEMS[w.id];
      return { label: d.name, value: u.items.indexOf(w), icon: d.icon, right: `威${d.mt} 中${d.hit}` };
    });
    const eq = R.equipIndex(u);
    this.menu = new ListMenu(items, {
      x: this.view.screenOf(u.x, u.y).x < W / 2 ? W - 156 : 6, y: 6, w: 150, visible: items.length, title: '选择武器',
      index: Math.max(0, items.findIndex((i) => i.value === eq)),
      drawItem: (ctx, it, x, y, sel) => {
        HUD.drawIcon(ctx, it.icon, x - 2, y - 2);
        drawText(ctx, it.label, x + 16, y, '#fff', { shadow: '#000' });
        drawText(ctx, it.right, x + 124, y, '#f8e8b0', { align: 'right', shadow: '#000' });
      },
    });
    this.mode = 'weapon';
  }

  updateWeapon(input) {
    const r = this.menu.update(input);
    if (!r) return;
    if (r.type === 'cancel') { this.openActionMenu(); return; }
    if (r.type === 'select') this.chooseWeapon(r.item.value);
  }

  chooseWeapon(idx) {
    const s = this.state;
    const u = this.sel;
    this.weaponIdx = idx;
    const w = u.items[idx];
    const targets = s.attackTargets(u).filter((t) => s.weaponsFor(u, t).includes(w));
    this.beginTargets('attack', targets);
    if (this.preTarget && targets.includes(this.preTarget)) { this.tIndex = targets.indexOf(this.preTarget); this.focusTarget(); }
    this.preTarget = null;
  }

  beginTargets(kind, list) {
    if (!list.length) { audio.sfx('error'); return; }
    this.targetKind = kind;
    this.targets = list;
    this.tIndex = 0;
    this.mode = 'target';
    this.menu = null;
    // 显示射程
    const s = this.state;
    const u = this.sel;
    const set = new Set();
    if (kind === 'attack') {
      const [a, b] = R.weaponRange(u, u.items[this.weaponIdx].id);
      for (const t of tilesInRange(s, u.x, u.y, a, b)) set.add(key(t.x, t.y));
      this.view.overlays.attack = set;
      if (this.ch.tutorial) this.tutorial('forecast');
    } else if (kind === 'staff') {
      for (const it of R.usableStaves(u)) { const [a, b] = R.weaponRange(u, it.id); for (const t of tilesInRange(s, u.x, u.y, a, b)) set.add(key(t.x, t.y)); }
      this.view.overlays.staff = set;
    }
    this.focusTarget();
  }

  focusTarget() {
    const t = this.targets[this.tIndex];
    this.view.cursor = { x: t.x, y: t.y };
    this.view.follow(t.x, t.y, 2);
  }

  updateTarget(input) {
    const s = this.state;
    const u = this.sel;
    const n = this.targets.length;
    const d = input.dir();
    if (d) { this.tIndex = (this.tIndex + (d === 'left' || d === 'up' ? -1 : 1) + n) % n; this.focusTarget(); audio.sfx('cursor'); }
    if (input.mouse.moved && input.mouse.inside) {
      const t = this.view.tileAt(input.mouse.x, input.mouse.y);
      const i = this.targets.findIndex((o) => o.x === t.x && o.y === t.y);
      if (i >= 0 && i !== this.tIndex) { this.tIndex = i; this.focusTarget(); audio.sfx('cursor'); }
    }
    if (input.pressed('info')) { const t = this.targets[this.tIndex]; if (t.uid) this.game.push(new UnitInfoScene(t, { state: s })); return; }
    if (input.cancel()) {
      audio.sfx('cancel');
      this.view.cursor = { x: u.x, y: u.y };
      this.clearOverlays();
      if (this.targetKind === 'attack' && R.usableWeapons(u).length > 1) { this.openActionMenu(); this.beginAttack(); if (this.mode !== 'weapon') this.openActionMenu(); }
      else this.openActionMenu();
      return;
    }
    if (input.confirm() || input.click()) {
      if (input.click()) {
        const t = this.view.tileAt(input.mouse.x, input.mouse.y);
        const i = this.targets.findIndex((o) => o.x === t.x && o.y === t.y);
        if (i < 0) { audio.sfx('error'); return; }
        this.tIndex = i;
      }
      const tgt = this.targets[this.tIndex];
      audio.sfx('confirm');
      switch (this.targetKind) {
        case 'attack': this.act('attack', { target: tgt, weaponIdx: this.weaponIdx }); break;
        case 'staff': {
          const staffIdx = u.items.findIndex((it) => ITEMS[it.id].type === 'staff' && R.canUse(u, it.id) && (() => { const [a, b] = R.weaponRange(u, it.id); const dd = Math.abs(tgt.x - u.x) + Math.abs(tgt.y - u.y); return dd >= a && dd <= b; })());
          this.act('staff', { target: tgt, idx: staffIdx });
          break;
        }
        case 'talk': this.act('talk', { target: tgt }); break;
        case 'door': this.act('door', { x: tgt.x, y: tgt.y }); break;
        case 'trade':
          this.game.push(new TradeScene(u, tgt, { onClose: (changed) => { if (changed) this.committed = true; this.view.cursor = { x: u.x, y: u.y }; this.openActionMenu(); } }));
          break;
        default: break;
      }
    }
  }

  // ---------------------------------------------------------------- 地图菜单
  openMapMenu() {
    const s = this.state;
    const items = [
      { label: '部队', value: 'units' },
      { label: '目标', value: 'objective' },
      { label: this.showThreat ? '隐藏威胁范围' : '威胁范围', value: 'threat' },
      { label: '保存进度', value: 'save' },
      { label: '读取存档', value: 'load' },
      { label: '设置', value: 'settings' },
      { label: '操作说明', value: 'help' },
      { label: '自动演示', value: 'auto', right: this.autoplay ? '开' : '关' },
      { label: '结束回合', value: 'end' },
      { label: '返回标题', value: 'title' },
    ];
    this.menu = new ListMenu(items, { x: W - 116, y: 8, w: 108, visible: items.length, rowH: 14, padY: 4 });
    this.mode = 'mapmenu';
    audio.sfx('confirm');
    this.game.push(new MapMenuOverlay(this));
  }

  onMapMenu(value) {
    const s = this.state;
    const game = this.game;
    switch (value) {
      case 'units': game.push(new UnitListScene(s)); break;
      case 'objective': game.push(new ObjectiveScene(s)); break;
      case 'threat':
        this.showThreat = !this.showThreat;
        this.view.overlays.threat = this.showThreat ? threatTiles(s) : null;
        break;
      case 'save': game.push(new SaveLoadScene('save', { battle: s })); break;
      case 'load': game.push(new SaveLoadScene('load')); break;
      case 'settings': game.push(new SettingsScene()); break;
      case 'help': game.push(new HelpScene()); break;
      case 'auto':
        this.autoplay = !this.autoplay;
        this.speedup = this.autoplay;
        game.autoAdvance = this.autoplay;
        this.notice = { lines: [this.autoplay ? '自动演示：开启（我方由 AI 代为操作，再次选择可关闭）' : '自动演示：关闭'], t: 120, style: 'dark' };
        break;
      case 'end': this.askEndTurn(); break;
      case 'title':
        game.push(new ConfirmDialog('返回标题画面？未保存的进度将会丢失。', (yes) => { if (yes) toTitle(game); }));
        break;
      default: break;
    }
  }

  askEndTurn() {
    const s = this.state;
    const go = () => { this.mode = 'busy'; this.tasks.add(this.enemyPhase()); };
    if (s.playerCanAct() && settings.confirmEnd) {
      this.game.push(new ConfirmDialog('还有单位没有行动，确定结束回合？', (yes) => { if (yes) go(); }));
    } else go();
  }

  // 自动演示：用自动操作逻辑执行一个我方单位
  autoStep() {
    const s = this.state;
    const plan = bestPlayerPlan(s);
    if (!plan) { this.mode = 'busy'; this.tasks.add(this.enemyPhase()); return; }
    const u = plan.unit;
    this.sel = u;
    this.origin = { x: u.x, y: u.y };
    this.range = s.moveRangeOf(u);
    const path = pathTo(this.range, plan.dest.x, plan.dest.y);
    this.mode = 'busy';
    const self = this;
    this.tasks.add((function* () {
      self.view.centerOn(u.x, u.y);
      yield 6;
      if (path && path.length > 1) yield* self.moveSeq(u, path);
      s.setPos(u, plan.dest.x, plan.dest.y);
      self.endMoveAnim(u);
      s.recordMove(u, self.origin.x, self.origin.y);
      if (s.queue.length) yield* self.runQueue();
      const a = plan.action;
      if (!a) { yield* self.doActionSeq('wait'); return; }
      if (a.type === 'attack') yield* self.doActionSeq('attack', { target: a.target, weaponIdx: a.weaponIdx });
      else if (a.type === 'staff') yield* self.doActionSeq('staff', { target: a.target, idx: u.items.indexOf(a.staff) });
      else if (a.type === 'item') { const r = s.useItem(u, a.idx); yield* self.doActionSeq('item', { result: r }); }
      else if (a.type === 'door') yield* self.doActionSeq('door', { x: a.x, y: a.y });
      else yield* self.doActionSeq(a.type, a);
    })());
  }

  // 某格（含单位向上超出格子的部分）在屏幕上的矩形，面板不能压住它
  tileRect(tx, ty) {
    const p = this.view.screenOf(tx, ty);
    return { x: p.x - 4, y: p.y - 16, w: TS + 8, h: TS + 20 };
  }

  // ---------------------------------------------------------------- 绘制
  // 可以交谈（招募）的对象：头上一直显示对话气泡，提示玩家去交谈
  recruitMarks() {
    const s = this.state;
    const set = new Set();
    for (const ev of s.ch.events || []) {
      if (ev.on !== 'talk' || s.fired.includes(ev.id)) continue;
      const a = s.findUnit(ev.a), b = s.findUnit(ev.b);
      if (a && b && a.team === 'player' && b.team !== 'player' && s.cond(ev.cond)) set.add(b.uid);
    }
    return set;
  }

  draw(ctx, game) {
    const s = this.state;
    const marks = this.mode === 'action' && this.talkMarks && this.talkMarks.size ? this.talkMarks : (s.phase === 'player' ? this.recruitMarks() : null);
    this.view.draw(ctx, { selected: this.mode === 'move' || this.mode === 'action' ? this.sel : null, cursor: this.mode !== 'enemy' && this.mode !== 'done' && !this.banner, talkMarks: marks });
    const c = this.view.cursor;
    const sp = this.view.screenOf(c.x, c.y);
    // 需要保持可见的格子：光标、选中的单位、当前目标
    const avoid = [this.tileRect(c.x, c.y)];
    if (this.sel && ['move', 'action', 'weapon', 'target'].includes(this.mode)) avoid.push(this.tileRect(this.sel.x, this.sel.y));
    if ((this.mode === 'idle' || this.mode === 'move') && !this.banner) {
      const u = s.unitAt(c.x, c.y);
      if (u) {
        const r = HUD.placePanel(HUD.UNIT_PANEL.w, HUD.UNIT_PANEL.h, avoid, HUD.oppositeOrder(sp.x, true));
        HUD.drawUnitPanel(ctx, u, r);
        avoid.push(r);
      }
      const tr = HUD.placePanel(HUD.TERRAIN_PANEL.w, HUD.TERRAIN_PANEL.h, avoid, HUD.oppositeOrder(sp.x, false));
      HUD.drawTerrainPanel(ctx, s.terrainAt(c.x, c.y), tr);
      avoid.push(tr);
      if (this.mode === 'idle') {
        const os = HUD.objectiveSize(s);
        const orr = HUD.placePanel(os.w, os.h, avoid, HUD.oppositeOrder(W - sp.x, true));
        HUD.drawObjectivePanel(ctx, s, orr);
        avoid.push(orr);
      }
    }
    if (this.mode === 'target' && this.targets) {
      const u = this.sel;
      const t = this.targets[this.tIndex];
      avoid.push(this.tileRect(t.x, t.y));
      const tsp = this.view.screenOf(t.x, t.y);
      if (this.targetKind === 'attack') {
        const fc = R.forecast(s, u, { x: u.x, y: u.y }, t, u.items[this.weaponIdx].id, { moved: u.moved });
        const r = HUD.placePanel(HUD.FORECAST.w, HUD.FORECAST.h, avoid, HUD.oppositeOrder(tsp.x, true));
        HUD.drawForecast(ctx, fc, r);
        avoid.push(r);
      } else if (t.uid) {
        const extra = this.targetKind === 'staff' ? 18 : 0;
        const r = HUD.placePanel(HUD.UNIT_PANEL.w, HUD.UNIT_PANEL.h + extra, avoid, HUD.oppositeOrder(tsp.x, true));
        HUD.drawUnitPanel(ctx, t, r);
        if (extra) {
          const st = R.usableStaves(u)[0];
          const amt = st ? R.healAmount(u, st.id, t) : 0;
          drawWindow(ctx, r.x, r.y + HUD.UNIT_PANEL.h, r.w, extra, 'green', 0.96);
          drawText(ctx, `治疗后 HP ${t.hp + amt}/${t.mhp}（+${amt}）`, r.x + r.w / 2, r.y + HUD.UNIT_PANEL.h + 3, '#e8ffe0', { align: 'center', shadow: '#000' });
        }
        avoid.push(r);
      }
    }
    if (this.menu && (this.mode === 'action' || this.mode === 'weapon')) {
      this.menu.draw(ctx, game.frame);
      avoid.push({ x: this.menu.x, y: this.menu.y, w: this.menu.w, h: this.menu.h + (this.menu.title ? 16 : 0) });
    }
    if (this.hpPanels) this.drawHpPanels(ctx);
    if (this.expBar) HUD.drawExpBar(ctx, this.expBar.name, this.expBar.exp, game.frame);
    if (this.levelUp) {
      const L = this.levelUp;
      HUD.drawLevelUp(ctx, L.uDisp, L.before, L.gains, L.shown, L.t);
    }
    if (this.banner) HUD.drawPhaseBanner(ctx, this.banner.text, this.banner.sub, this.banner.t, this.banner.color);
    if (this.notice) HUD.drawNotice(ctx, this.notice.lines, null, this.notice.style, avoid);
    if (this.bigText) {
      const a = Math.min(1, this.bigText.t / 20);
      ctx.globalAlpha = a * 0.6;
      fill(ctx, 0, 70, W, 40, '#000');
      ctx.globalAlpha = a;
      drawTextScaled(ctx, this.bigText.text, W / 2, 78, this.bigText.color, 2, { align: 'center', outline: '#2a1004' });
      ctx.globalAlpha = 1;
    }
    if (this.autoplay) drawText(ctx, '自动演示中', W - 4, H - 14, '#f8d878', { align: 'right', shadow: '#000' });
    // 操作提示：放在不遮挡光标和面板的一侧（上或下），都放不下就不显示
    if (this.mode === 'idle' && !this.banner && !this.notice && !this.autoplay) {
      const hint = 'Z确认 X取消 C详情 R威胁 M菜单';
      const hw = textWidth(hint) + 4;
      const cand = [{ x: (W - hw) / 2, y: H - 14, w: hw, h: 13 }, { x: (W - hw) / 2, y: 2, w: hw, h: 13 }];
      const spot = cand.find((r) => !avoid.some((a) => HUD.rectOverlap(r, a)));
      if (spot) {
        ctx.globalAlpha = 0.8;
        drawText(ctx, hint, W / 2, spot.y + 1, '#e8e0c8', { align: 'center', shadow: '#000' });
        ctx.globalAlpha = 1;
      }
    }
  }

  drawHpPanels(ctx) {
    const P = this.hpPanels;
    const draw = (u, hp, x, style) => {
      drawWindow(ctx, x, H - 40, 120, 36, style);
      drawText(ctx, u.name, x + 8, H - 36, '#fff', { shadow: '#000' });
      drawText(ctx, `${hp}/${u.mhp}`, x + 112, H - 36, '#f8f0d0', { align: 'right', shadow: '#000' });
      fill(ctx, x + 8, H - 18, 104, 5, '#1a1824');
      fill(ctx, x + 8, H - 18, Math.round((104 * hp) / u.mhp), 5, hp / u.mhp > 0.5 ? '#78d060' : hp / u.mhp > 0.25 ? '#e8c040' : '#e85040');
    };
    draw(P.def, P.hpD, 8, P.def.team === 'enemy' ? 'red' : 'blue');
    draw(P.att, P.hpA, W - 128, P.att.team === 'enemy' ? 'red' : 'blue');
  }
}

// ---------------------------------------------------------------- 教学 / 注意事项弹窗
export class TutorialOverlay {
  constructor(lines, opts = {}) {
    this.overlay = true;
    this.title = opts.title || '教学';
    this.style = opts.style || 'gold';
    this.lines = [];
    for (const l of lines) this.lines.push(...wrapText(l.replace(/^【教学】/, ''), 264));
    this.t = 0;
  }
  update(game) {
    this.t++;
    if (game.autoAdvance && this.t > 15) { game.remove(this); return; }
    if (this.t > 12 && (game.input.confirm() || game.input.click() || game.input.cancel())) {
      audio.sfx('confirm');
      game.remove(this);
      game.input.consumeAll();
    }
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.3;
    fill(ctx, 0, 0, W, H, '#000');
    ctx.globalAlpha = 1;
    const w = 284, h = this.lines.length * 14 + 40;
    const x = (W - w) / 2, y = Math.round((H - h) / 2);
    drawWindow(ctx, x, y, w, h, 'menu');
    drawWindow(ctx, x + 8, y - 8, textWidth(this.title) + 16, 17, this.style);
    drawText(ctx, this.title, x + 16, y - 5, '#fff4d8', { shadow: '#2a1804' });
    this.lines.forEach((l, i) => drawText(ctx, l, x + 10, y + 12 + i * 14, '#f8f0e0', { shadow: '#000' }));
    if (Math.floor(this.t / 20) % 2 === 0) drawText(ctx, 'Z / 点击 继续', x + w - 10, y + h - 15, '#c8b890', { align: 'right', shadow: '#000' });
  }
}

// ---------------------------------------------------------------- 地图菜单覆盖层
class MapMenuOverlay {
  constructor(scene) { this.overlay = true; this.scene = scene; }
  update(game) {
    const r = this.scene.menu.update(game.input);
    if (!r) return;
    if (r.type === 'cancel') { game.remove(this); this.scene.toIdle(); return; }
    if (r.type === 'select') {
      game.remove(this);
      this.scene.toIdle();
      this.scene.onMapMenu(r.item.value);
    }
  }
  draw(ctx, game) { this.scene.menu.draw(ctx, game.frame); }
}

// ---------------------------------------------------------------- 部队一览
export class UnitListScene {
  constructor(state) {
    this.overlay = true;
    this.state = state;
    const us = state.living('player').filter((u) => !u.escort);
    this.units = us;
    this.menu = new ListMenu(us.map((u) => ({ label: u.name, value: u })), {
      x: 8, y: 8, w: W - 16, visible: Math.min(8, us.length), rowH: 18, title: '部队一览（Z 查看详情 / 加点）',
      drawItem: (ctx, it, x, y) => {
        const u = it.value;
        drawText(ctx, u.name, x, y, u.acted ? '#9a98a8' : '#ffffff', { shadow: '#000' });
        drawText(ctx, HUD.className(u), x + 52, y, '#c8d8ff', { shadow: '#000' });
        drawText(ctx, `Lv${u.lv}`, x + 118, y, '#f8e0a0', { shadow: '#000' });
        drawText(ctx, `HP ${u.hp}/${u.mhp}`, x + 150, y, '#ffffff', { shadow: '#000' });
        const w = R.equipped(u);
        drawText(ctx, w ? ITEMS[w.id].name : '—', x + 218, y, '#e0e0e0', { shadow: '#000' });
        if (u.points) drawText(ctx, `★${u.points}`, x + 280, y, '#f8d040', { shadow: '#000' });
      },
    });
  }
  update(game) {
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'cancel') { game.remove(this); return; }
    if (r.type === 'select') game.push(new UnitInfoScene(r.item.value, { state: this.state, list: this.units }));
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.5; fill(ctx, 0, 0, W, H, '#000'); ctx.globalAlpha = 1;
    this.menu.draw(ctx, game.frame);
  }
}

// ---------------------------------------------------------------- 目标窗口
export class ObjectiveScene {
  constructor(state) { this.overlay = true; this.state = state; }
  update(game) { if (game.input.cancel() || game.input.confirm() || game.input.click()) { audio.sfx('cancel'); game.remove(this); } }
  draw(ctx) {
    const s = this.state;
    const ch = s.ch;
    ctx.globalAlpha = 0.5; fill(ctx, 0, 0, W, H, '#000'); ctx.globalAlpha = 1;
    drawWindow(ctx, 16, 8, W - 32, 164, 'menu');
    drawText(ctx, `${ch.title}　${ch.name}`, W / 2, 14, '#f8e0a0', { align: 'center', shadow: '#000' });
    const lines = [
      ['胜利条件', ch.objective.text],
      ['失败条件', ch.objective.lose],
      ['当前回合', `第 ${s.turn} 回合` + (ch.objective.type === 'defend' ? `（坚守到第 ${ch.objective.turns} 回合结束）` : '')],
      ['兵力', `我方 ${s.living('player').length} 人　敌方 ${s.living('enemy').filter((u) => !u.recruitable).length} 人`],
    ];
    if (ch.bonus) lines.push(['附加', ch.bonus]);
    let y = 34;
    for (const [k, v] of lines) {
      drawText(ctx, k, 28, y, '#c8d8ff', { shadow: '#000' });
      const wrapped = wrapText(v, W - 32 - 92);
      wrapped.forEach((l, j) => drawText(ctx, l, 88, y + j * 14, '#ffffff', { shadow: '#000' }));
      y += Math.max(1, wrapped.length) * 14 + 4;
    }
    drawText(ctx, `难度：${{ easy: '简单', normal: '普通', hard: '困难' }[s.difficulty]}　${s.mode === 'casual' ? '休闲模式' : '经典模式'}`, W / 2, 152, '#a8b0d0', { align: 'center', shadow: '#000' });
  }
}
