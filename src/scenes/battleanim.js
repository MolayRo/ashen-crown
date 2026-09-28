// 侧视战斗演出（GBA 火纹式）：冲刺、攻击帧、投射物/魔法、受击闪白、伤害数字、HP 逐格减少、阵亡退场
import { W, H } from '../core/renderer.js';
import { fill, drawWindow } from '../core/gfx.js';
import { drawText, drawTextOutlined, drawTextScaled } from '../core/font.js';
import { sheets } from '../core/assets.js';
import { settings, speedMul } from '../core/settings.js';
import { audio } from '../core/audio.js';
import { ITEMS } from '../game/data/items.js';
import { drawIcon, className } from './map/hud.js';

const GROUND = 108;
const LX = 96, RX = 224;

function terrainKind(state, u) {
  const t = state.terrainAt(u.x, u.y);
  const ch = state.charAt(u.x, u.y);
  const theme = state.theme;
  if (theme === 'snow') return { bg: 'snow', plat: ch === '+' || ch === 'F' || ch === 'G' ? 'stone' : 'snow' };
  if (theme === 'indoor') return { bg: 'indoor', plat: 'stone' };
  if (theme === 'castle') {
    if ('+c|KSDa'.includes(ch)) return { bg: 'castle', plat: 'stone' };
    return { bg: ch === 'F' || ch === 'G' ? 'fort' : 'plains', plat: ch === '"' ? 'road' : ch === 'F' || ch === 'G' ? 'stone' : 'grass' };
  }
  if (t.forest) return { bg: 'forest', plat: 'forest' };
  if (ch === '=' || ch === '_') return { bg: 'bridge', plat: 'wood' };
  if (ch === 'V' || ch === 'H' || ch === 'r') return { bg: 'village', plat: 'road' };
  if (ch === 'F' || ch === 'G') return { bg: 'fort', plat: 'stone' };
  if (ch === '"') return { bg: 'plains', plat: 'road' };
  return { bg: 'plains', plat: 'grass' };
}

export class BattleAnimScene {
  constructor(res, opts = {}) {
    this.overlay = true;
    this.res = res;
    this.state = opts.state;
    this.onDone = opts.onDone;
    const { att, def } = res;
    const attRight = att.team === 'player' || (att.team === 'ally' && def.team === 'enemy');
    this.sides = {
      att: { u: att, right: attRight, fc: res.fc.att, hp: res.pre.attHp, shownHp: res.pre.attHp },
      def: { u: def, right: !attRight, fc: res.fc.def, hp: res.pre.defHp, shownHp: res.pre.defHp },
    };
    for (const k of ['att', 'def']) {
      const S = this.sides[k];
      S.x = S.right ? RX : LX;
      S.baseX = S.x;
      S.off = 0;
      S.anim = 'idle';
      S.animT = 0;
      S.frameIdx = 0;
      S.flash = 0;
      S.alpha = 1;
      S.shake = 0;
      S.set = S.u.battle || 'soldier';
    }
    this.dist = res.fc.dist;
    this.kind = terrainKind(this.state, def);
    this.kindAtt = terrainKind(this.state, att);
    this.fx = [];
    this.nums = [];
    this.flashScreen = 0;
    this.shakeScreen = 0;
    this.t = 0;
    this.phase = 'intro';
    this.introT = 0;
    this.skipped = false;
    this.gen = this.run();
    this.prevMusic = audio.musicId;
    this.bossFight = att.boss || def.boss;
  }

  enter(game) {
    this.game = game;
    if (this.bossFight) audio.playMusic('boss', { fade: 0.4 });
  }

  meta() { return sheets.battle_units && sheets.battle_units.meta; }
  setInfo(set) { const m = this.meta(); return (m && m.sets && m.sets[set]) || { dash: true, type: 'melee' }; }
  hasAnim(set, anim) { const m = this.meta(); return !!(m && m.anims && m.anims[`${set}_${anim}`]); }
  animList(set, anim) { const m = this.meta(); return (m && m.anims && m.anims[`${set}_${anim}`]) || null; }
  eventIdx(set, anim, key) { const m = this.meta(); const e = m && m.events && m.events[`${set}_${anim}`]; return e && e[key] != null ? e[key] : null; }

  speed() { return speedMul() * (this.game.input.fast() || this.game.autoAdvance ? 2.5 : 1); }

  *waitF(n) { let t = 0; while (t < n) { t += this.speed(); yield; } }

  // 播放一段动画，在事件帧调用回调（生成器）
  *playAnim(S, anim, onEvent, evKey) {
    const list = this.animList(S.set, anim) || this.animList(S.set, 'attack') || null;
    S.anim = anim;
    if (!list) {
      // 无素材：简单的前冲动作
      for (let i = 0; i < 6; i++) { S.off += (S.right ? -2 : 2); yield; }
      if (onEvent) yield* onEvent();
      for (let i = 0; i < 6; i++) { S.off -= (S.right ? -2 : 2); yield; }
      S.anim = 'idle';
      return;
    }
    const ev = this.eventIdx(S.set, anim, evKey) ?? this.eventIdx(S.set, anim, 'hit') ?? Math.floor(list.length / 2);
    for (let i = 0; i < list.length; i++) {
      S.frameName = list[i][0];
      if (i === ev && onEvent) yield* onEvent();
      yield* this.waitF(list[i][1]);
    }
    S.frameName = null;
    S.anim = 'idle';
  }

  *run() {
    // 开场：淡入
    for (let i = 0; i <= 12; i++) { this.introT = i / 12; yield; }
    yield* this.waitF(16);
    const strikes = this.res.strikes;
    for (let si = 0; si < strikes.length; si++) {
      const st = strikes[si];
      const S = this.sides[st.who];
      const T = this.sides[st.who === 'att' ? 'def' : 'att'];
      yield* this.strike(S, T, st);
      if (T.hp <= 0) break;
      if (S.hp <= 0) break;
      yield* this.waitF(10);
    }
    // 阵亡退场
    for (const k of ['att', 'def']) {
      const S = this.sides[k];
      if (S.hp <= 0) {
        audio.sfx('death');
        for (let i = 0; i < 30; i++) { S.flash = i % 6 < 3 ? 0.8 : 0; S.alpha = 1 - i / 30; yield* this.waitF(1); }
        S.alpha = 0;
      }
    }
    yield* this.waitF(24);
    for (let i = 12; i >= 0; i--) { this.introT = i / 12; yield; }
  }

  *strike(S, T, st) {
    const info = this.setInfo(S.set);
    const w = S.fc.weapon ? ITEMS[S.fc.weapon] : null;
    const ranged = this.dist >= 2;
    let anim = st.crit && this.hasAnim(S.set, 'crit') ? 'crit' : 'attack';
    if (ranged && info.type === 'melee' && this.hasAnim(S.set, 'ranged')) anim = 'ranged';
    const dir = S.right ? -1 : 1;
    const doDash = info.dash !== false && info.type === 'melee' && !ranged;
    const dashTo = doDash ? (T.baseX - S.baseX) - dir * 40 : 0;
    if (st.crit) {
      audio.sfx('crit');
      this.flashScreen = 6;
      yield* this.waitF(16);
    }
    if (doDash) {
      this.fx.push({ name: 'dust', x: S.baseX, y: GROUND, t: 0, flip: S.right });
      const n = 8;
      for (let i = 1; i <= n; i++) { S.off = (dashTo * i) / n; yield* this.waitF(1); }
    }
    const wtype = w ? w.type : 'sword';
    const self = this;
    const impact = function* () {
      if (info.type === 'bow' || anim === 'ranged') {
        audio.sfx(info.type === 'bow' ? 'bow' : 'throw');
        const proj = info.type === 'bow' ? 'arrow' : (info.ranged || (wtype === 'axe' ? 'handaxe' : 'javelin'));
        yield* self.projectile(S, T, proj);
      } else if (info.type === 'magic' || wtype === 'tome') {
        const spell = (w && w.spell) || info.spell || 'fire';
        audio.sfx(spell === 'light' ? 'light' : spell);
        yield* self.spell(S, T, spell);
      } else {
        audio.sfx(wtype === 'lance' ? 'lance' : wtype === 'axe' ? 'axe' : 'sword');
      }
      yield* self.applyHit(S, T, st);
    };
    yield* this.playAnim(S, anim, impact, info.type === 'bow' || anim === 'ranged' ? 'shoot' : info.type === 'magic' ? 'spell' : 'hit');
    if (doDash) {
      const n = 8;
      for (let i = n - 1; i >= 0; i--) { S.off = (dashTo * i) / n; yield* this.waitF(1); }
    }
  }

  *projectile(S, T, name) {
    const x0 = S.baseX + S.off + (S.right ? -18 : 18), y0 = GROUND - 30;
    const x1 = T.baseX + T.off, y1 = GROUND - 30;
    const p = { name, x: x0, y: y0, t: 0, flip: !S.right, proj: true };
    this.fx.push(p);
    const n = 14;
    for (let i = 1; i <= n; i++) { p.x = x0 + ((x1 - x0) * i) / n; p.y = y0 - Math.sin((i / n) * Math.PI) * 6; p.t++; yield* this.waitF(1); }
    p.dead = true;
  }

  *spell(S, T, spell) {
    const tx = T.baseX + T.off, ty = GROUND - 26;
    if (spell === 'fire') {
      const x0 = S.baseX + S.off + (S.right ? -16 : 16);
      const p = { name: 'fireball', x: x0, y: ty, t: 0, flip: !S.right, proj: true };
      this.fx.push(p);
      for (let i = 1; i <= 12; i++) { p.x = x0 + ((tx - x0) * i) / 12; p.t++; yield* this.waitF(1); }
      p.dead = true;
      this.fx.push({ name: 'fire_burst', x: tx, y: ty, t: 0 });
      yield* this.waitF(8);
    } else if (spell === 'thunder') {
      this.fx.push({ name: 'thunder', x: tx, y: GROUND, t: 0 });
      this.flashScreen = 3;
      yield* this.waitF(12);
    } else if (spell === 'dark') {
      this.fx.push({ name: 'dark', x: tx, y: ty, t: 0 });
      yield* this.waitF(18);
    } else {
      this.fx.push({ name: 'light', x: tx, y: GROUND, t: 0 });
      this.flashScreen = 4;
      yield* this.waitF(14);
    }
  }

  *applyHit(S, T, st) {
    if (!st.hit) {
      audio.sfx('miss');
      this.nums.push({ text: 'MISS', x: T.baseX + T.off, y: GROUND - 60, t: 0, color: '#c8e0ff' });
      const list = this.animList(T.set, 'dodge');
      const dir = T.right ? 1 : -1;
      for (let i = 0; i < 6; i++) { T.off = dir * i * 2; T.frameName = list ? list[Math.min(list.length - 1, Math.floor(i / 3))][0] : null; yield* this.waitF(1); }
      yield* this.waitF(8);
      for (let i = 5; i >= 0; i--) { T.off = dir * i * 2; yield* this.waitF(1); }
      T.frameName = null;
      return;
    }
    audio.sfx(st.crit ? 'hit_heavy' : st.dmg === 0 ? 'nodmg' : 'hit');
    this.fx.push({ name: st.crit ? 'critspark' : 'hitspark', x: T.baseX + T.off, y: GROUND - 28, t: 0 });
    if (st.crit) { this.shakeScreen = 14; this.flashScreen = 4; }
    this.nums.push({ text: st.dmg === 0 ? '0' : String(st.dmg), x: T.baseX + T.off, y: GROUND - 62, t: 0, color: st.crit ? '#ffe040' : '#ffffff', crit: st.crit });
    const hurt = this.animList(T.set, 'hurt');
    const target = st.who === 'att' ? st.defHp : st.attHp;
    T.hp = target;
    for (let i = 0; i < 10; i++) {
      T.flash = i % 4 < 2 ? 0.9 : 0;
      T.shake = (i % 2 ? 2 : -2) * (st.crit ? 2 : 1);
      if (hurt && i < 6) T.frameName = hurt[0][0];
      if (T.shownHp > target) T.shownHp -= 1;
      yield* this.waitF(1);
    }
    T.flash = 0; T.shake = 0; T.frameName = null;
    while (T.shownHp > target) { T.shownHp -= 1; yield* this.waitF(1.5); }
  }

  finish() {
    if (this.done) return;
    this.done = true;
    if (this.bossFight && this.prevMusic && this.prevMusic !== 'boss') audio.playMusic(this.prevMusic, { fade: 0.6 });
    this.game.remove(this);
    if (this.onDone) this.onDone();
  }

  update(game) {
    this.t++;
    if (game.input.cancel() && !this.skipped) {
      // 跳过演出：直接跳到结果
      this.skipped = true;
      audio.sfx('cancel');
      this.finish();
      return;
    }
    const steps = Math.max(1, Math.round(this.speed()));
    for (let k = 0; k < 1; k++) {
      const r = this.gen.next();
      if (r.done) { this.finish(); return; }
    }
    void steps;
    for (const f of this.fx) f.t += 1;
    this.fx = this.fx.filter((f) => !f.dead && f.t < 80);
    for (const n of this.nums) n.t++;
    this.nums = this.nums.filter((n) => n.t < 50);
    if (this.flashScreen > 0) this.flashScreen--;
    if (this.shakeScreen > 0) this.shakeScreen--;
  }

  drawUnit(ctx, S) {
    const sh = sheets.battle_units;
    const x = Math.round(S.baseX + S.off + S.shake);
    const y = GROUND;
    let frame = S.frameName;
    if (!frame) {
      const idle = this.animList(S.set, 'idle');
      if (idle) {
        let tot = 0; for (const [, d] of idle) tot += d;
        let m = this.t % tot; frame = idle[0][0];
        for (const [f, d] of idle) { if (m < d) { frame = f; break; } m -= d; }
      }
    }
    if (S.alpha <= 0) return;
    if (sh && frame && sh.has(frame)) {
      sh.draw(ctx, frame, x, y, !S.right, S.alpha);
      if (S.flash) sh.drawTinted(ctx, frame, x, y, !S.right, '#ffffff', S.flash * S.alpha);
      return;
    }
    // 占位小人
    ctx.globalAlpha = S.alpha;
    const col = S.u.team === 'enemy' ? '#b83c30' : '#3c64b8';
    fill(ctx, x - 8, y - 40, 16, 28, col);
    fill(ctx, x - 6, y - 52, 12, 12, '#f2b896');
    fill(ctx, x - 7, y - 12, 5, 12, '#3a2414');
    fill(ctx, x + 2, y - 12, 5, 12, '#3a2414');
    fill(ctx, x + (S.right ? -20 : 8), y - 34, 12, 3, '#dfe6ee');
    if (S.flash) { ctx.globalAlpha = S.flash * S.alpha; fill(ctx, x - 8, y - 52, 16, 52, '#fff'); }
    ctx.globalAlpha = 1;
  }

  drawFx(ctx, f) {
    const sh = sheets.battle_fx;
    const m = sh && sh.meta;
    let frame = null;
    const a = m && m.anims && m.anims[f.name];
    if (a) {
      let t = f.t, tot = 0;
      for (const [, d] of a) tot += d;
      if (!f.proj && t >= tot) { f.dead = true; return; }
      t = f.proj ? t % tot : t;
      frame = a[0][0];
      for (const [fr, d] of a) { if (t < d) { frame = fr; break; } t -= d; }
    } else if (sh && sh.has(f.name)) frame = f.name;
    else if (sh && sh.has(f.name + '0')) frame = f.name + '0';
    if (sh && frame) {
      // 法术、火花等发光特效用加色混合，箭矢/投掷物/扬尘正常绘制
      const glow = !['arrow', 'javelin', 'handaxe', 'dust'].includes(f.name);
      if (glow) ctx.globalCompositeOperation = 'lighter';
      sh.draw(ctx, frame, Math.round(f.x), Math.round(f.y), !!f.flip);
      ctx.globalCompositeOperation = 'source-over';
      return;
    }
    // 占位特效
    const c = { hitspark: '#fff8c0', critspark: '#ffe040', fire_burst: '#f08020', fireball: '#f06020', thunder: '#f8f080', dark: '#9a40b8', light: '#fffae0', arrow: '#c8b080', javelin: '#dfe6ee', handaxe: '#a4aebe', dust: '#c8b490' }[f.name] || '#fff';
    const r = f.name === 'thunder' ? 3 : f.name.endsWith('spark') ? 6 - f.t / 3 : 4;
    if (r <= 0) return;
    if (f.name === 'thunder') fill(ctx, f.x - 2, 0, 4, GROUND, c);
    else fill(ctx, Math.round(f.x - r), Math.round(f.y - r), Math.round(r * 2), Math.round(r * 2), c);
  }

  drawHud(ctx) {
    for (const k of ['att', 'def']) {
      const S = this.sides[k];
      const x0 = S.right ? W / 2 : 0;
      const style = S.u.team === 'enemy' ? 'red' : S.u.team === 'player' ? 'blue' : 'green';
      // 名字框
      drawWindow(ctx, x0 + (S.right ? 84 : 4), 4, 72, 18, style);
      drawText(ctx, S.u.name, x0 + (S.right ? 120 : 40), 7, '#ffffff', { align: 'center', shadow: '#000' });
      // 数值框
      drawWindow(ctx, x0 + 2, 124, W / 2 - 4, 54, style);
      const fc = S.fc;
      const w = fc.weapon ? ITEMS[fc.weapon] : (S === this.sides.def && fc.shownWeapon ? ITEMS[fc.shownWeapon] : null);
      if (w) { drawIcon(ctx, w.icon, x0 + 8, 128); drawText(ctx, w.name, x0 + 26, 130, '#ffffff', { shadow: '#000' }); }
      else drawText(ctx, '—', x0 + 26, 130, '#9a98a8');
      const can = S === this.sides.att || fc.canCounter;
      const vals = [['命中', can ? fc.hit : '--'], ['伤害', can ? fc.dmg + (fc.times > 1 ? '×2' : '') : '--'], ['必杀', can ? fc.crit : '--']];
      // 标签金色、数值白色，紧凑排成一行
      let tx = x0 + 8;
      for (const [lab, v] of vals) {
        tx = drawText(ctx, lab, tx, 144, '#f8e0a0', { shadow: '#000' });
        tx = drawText(ctx, String(v), tx + 1, 144, can ? '#ffffff' : '#8a8898', { shadow: '#000' });
        tx += 8;
      }
      // HP
      drawText(ctx, String(Math.max(0, S.shownHp)), x0 + 16, 160, '#ffffff', { align: 'center', shadow: '#000' });
      const max = S.u.mhp;
      const perRow = 30;
      for (let i = 0; i < Math.min(max, 60); i++) {
        const row = Math.floor(i / perRow), col = i % perRow;
        const filled = i < S.shownHp;
        fill(ctx, x0 + 30 + col * 4, 159 + row * 7, 3, 5, filled ? '#f8f0c8' : '#3a3448');
        if (filled) fill(ctx, x0 + 30 + col * 4, 163 + row * 7, 3, 1, '#c8a060');
      }
    }
  }

  draw(ctx) {
    const a = this.introT;
    const sx = this.shakeScreen ? Math.round((Math.random() - 0.5) * 6) : 0;
    const sy = this.shakeScreen ? Math.round((Math.random() - 0.5) * 4) : 0;
    // 背景
    ctx.globalAlpha = a;
    fill(ctx, 0, 0, W, H, '#07060b');
    ctx.save();
    ctx.translate(sx, sy);
    const bgs = sheets.battle_bg;
    if (bgs && bgs.has('bg_' + this.kind.bg)) bgs.draw(ctx, 'bg_' + this.kind.bg, 0, 0);
    else { fill(ctx, 0, 0, W, 90, '#3a5a8a'); fill(ctx, 0, 90, W, 34, '#4a7a3a'); }
    for (const k of ['att', 'def']) {
      const S = this.sides[k];
      const kind = k === 'att' ? this.kindAtt : this.kind;
      const pn = 'plat_' + kind.plat;
      if (bgs && bgs.has(pn)) bgs.draw(ctx, pn, S.baseX, GROUND);
      else fill(ctx, S.baseX - 50, GROUND, 100, 8, '#5a4a38');
    }
    // 人物：攻击者画在上层
    const order = [this.sides.def, this.sides.att];
    for (const S of order) this.drawUnit(ctx, S);
    for (const f of this.fx) this.drawFx(ctx, f);
    for (const n of this.nums) {
      const yy = n.y - Math.min(12, n.t * 1.2);
      const al = n.t > 36 ? (50 - n.t) / 14 : 1;
      ctx.globalAlpha = a * al;
      if (n.crit) drawTextScaled(ctx, n.text, n.x, yy - 6, n.color, 2, { align: 'center', outline: '#2a0404' });
      else drawTextOutlined(ctx, n.text, n.x, yy, n.color, '#200808', { align: 'center' });
      ctx.globalAlpha = a;
    }
    ctx.restore();
    this.drawHud(ctx);
    if (this.flashScreen > 0) { ctx.globalAlpha = this.flashScreen / 6; fill(ctx, 0, 0, W, H, '#ffffff'); }
    ctx.globalAlpha = 1;
    if (a > 0.9) {
      ctx.globalAlpha = 0.55;
      drawText(ctx, 'Shift 加速  X 跳过', W / 2, 8, '#e8e0c8', { align: 'center', shadow: '#000' });
      ctx.globalAlpha = 1;
    }
  }
}

// 治疗演出：治疗者举杖 → 目标身上的光柱 → HP 逐格回升
export class HealAnimScene extends BattleAnimScene {
  constructor(res, opts = {}) {
    const { healer, target, amount } = res;
    const fake = {
      att: healer, def: target,
      fc: {
        dist: Math.abs(healer.x - target.x) + Math.abs(healer.y - target.y),
        att: { weapon: opts.staffId || null, hit: 100, dmg: 0, crit: 0, times: 1 },
        def: { weapon: null, shownWeapon: null, canCounter: false },
      },
      pre: { attHp: healer.hp, defHp: target.hp - amount },
      strikes: [],
    };
    super(fake, opts);
    this.amount = amount;
    // 双方同一阵营：我方治疗者站右侧、敌方站左侧，受治疗者站另一边
    const S = this.sides.att, T = this.sides.def;
    S.right = healer.team !== 'enemy';
    T.right = !S.right;
    S.x = S.baseX = S.right ? RX : LX;
    T.x = T.baseX = T.right ? RX : LX;
    this.enemySide = healer.team === 'enemy';
    this.bossFight = false;
    this.gen = this.run();
  }

  *run() {
    for (let i = 0; i <= 12; i++) { this.introT = i / 12; yield; }
    yield* this.waitF(12);
    const S = this.sides.att, T = this.sides.def;
    const self = this;
    const onHeal = function* () {
      audio.sfx('heal');
      self.fx.push({ name: 'heal', x: T.baseX, y: GROUND - 26, t: 0 });
      const target = T.hp + self.amount;
      self.nums.push({ text: '+' + self.amount, x: T.baseX, y: GROUND - 62, t: 0, color: '#a0ffb0' });
      for (let i = 0; i < 36 || T.shownHp < target; i++) {
        T.flash = i % 8 < 4 ? 0.35 : 0;
        if (i % 2 === 0 && T.shownHp < target) T.shownHp += 1;
        yield* self.waitF(1);
      }
      T.hp = target;
      T.flash = 0;
    };
    const anim = this.hasAnim(S.set, 'staff') ? 'staff' : 'attack';
    yield* this.playAnim(S, anim, onHeal, 'heal');
    yield* this.waitF(24);
    for (let i = 12; i >= 0; i--) { this.introT = i / 12; yield; }
  }

  drawUnit(ctx, S) {
    // 受治疗者闪的是淡绿色
    if (S === this.sides.def && S.flash) {
      const f = S.flash;
      S.flash = 0;
      super.drawUnit(ctx, S);
      S.flash = f;
      const sh = sheets.battle_units;
      const frame = S.frameName || (this.animList(S.set, 'idle') || [[null]])[0][0];
      if (sh && frame && sh.has(frame)) sh.drawTinted(ctx, frame, Math.round(S.baseX + S.off), GROUND, !S.right, '#a0ffb0', f);
      return;
    }
    super.drawUnit(ctx, S);
  }

  drawHud(ctx) {
    for (const k of ['att', 'def']) {
      const S = this.sides[k];
      const x0 = S.right ? W / 2 : 0;
      const team = this.enemySide ? 'red' : 'blue';
      drawWindow(ctx, x0 + (S.right ? 84 : 4), 4, 72, 18, team);
      drawText(ctx, S.u.name, x0 + (S.right ? 120 : 40), 7, '#ffffff', { align: 'center', shadow: '#000' });
      drawWindow(ctx, x0 + 2, 124, W / 2 - 4, 54, S === this.sides.att ? 'green' : team);
      if (S === this.sides.att) {
        const w = S.fc.weapon ? ITEMS[S.fc.weapon] : null;
        if (w) { drawIcon(ctx, w.icon, x0 + 8, 128); drawText(ctx, w.name, x0 + 26, 130, '#ffffff', { shadow: '#000' }); }
        drawText(ctx, `回复 ${this.amount} HP`, x0 + 8, 144, '#c8ffd0', { shadow: '#000' });
      } else {
        drawText(ctx, '接受治疗', x0 + 8, 130, '#c8d8ff', { shadow: '#000' });
      }
      drawText(ctx, String(Math.max(0, S.shownHp)), x0 + 16, 160, '#ffffff', { align: 'center', shadow: '#000' });
      const max = S.u.mhp;
      for (let i = 0; i < Math.min(max, 60); i++) {
        const row = Math.floor(i / 30), col = i % 30;
        const filled = i < S.shownHp;
        fill(ctx, x0 + 30 + col * 4, 159 + row * 7, 3, 5, filled ? '#f8f0c8' : '#3a3448');
        if (filled) fill(ctx, x0 + 30 + col * 4, 163 + row * 7, 3, 1, '#c8a060');
      }
    }
  }
}
