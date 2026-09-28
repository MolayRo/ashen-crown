// 角色详情：能力 / 物品 / 简介 三页；我方角色可在此手动加点
import { W, H } from '../core/renderer.js';
import { fill, drawWindow, drawBar, drawPointer } from '../core/gfx.js';
import { drawText, wrapText } from '../core/font.js';
import { audio } from '../core/audio.js';
import { CLASSES, STAT_NAMES, TRAITS } from '../game/data/classes.js';
import { ITEMS } from '../game/data/items.js';
import * as R from '../game/rules.js';
import bios from '../game/story/bios.js';
import { drawPortrait } from './story.js';
import { className, drawIcon } from './map/hud.js';
import { ConfirmDialog } from './confirm.js';

const STAT_KEYS = ['hp', 'str', 'mag', 'skl', 'spd', 'lck', 'def', 'res'];
const ALLOC_ROWS = ['hp', 'str', 'mag', 'skl', 'spd', 'lck', 'def', 'res', 'mov'];

export class UnitInfoScene {
  // opts: {state, list(可切换的单位列表), campaign, onChange}
  constructor(u, opts = {}) {
    this.overlay = true;
    this.u = u;
    this.opts = opts;
    this.page = 0;
    this.alloc = null;   // {pending, row}
  }

  canAlloc() { return this.u.team === 'player' && !this.u.escort && (this.u.points || 0) > 0; }

  update(game) {
    const input = game.input;
    if (this.alloc) { this.updateAlloc(game); return; }
    if (input.repeat('left')) { this.page = (this.page + 2) % 3; audio.sfx('page'); }
    if (input.repeat('right')) { this.page = (this.page + 1) % 3; audio.sfx('page'); }
    const list = this.opts.list;
    if (list && list.length > 1) {
      const i = list.indexOf(this.u);
      if (input.repeat('up')) { this.u = list[(i - 1 + list.length) % list.length]; audio.sfx('cursor'); }
      if (input.repeat('down')) { this.u = list[(i + 1) % list.length]; audio.sfx('cursor'); }
    }
    const m = input.mouse;
    if (input.click()) {
      if (this.page === 0 && this.canAlloc() && m.x >= 236 && m.x < 312 && m.y >= 150 && m.y < 170) { this.openAlloc(); return; }
      if (m.y < 20) { this.page = m.x < W / 2 ? (this.page + 2) % 3 : (this.page + 1) % 3; audio.sfx('page'); return; }
    }
    if (input.confirm() && this.page === 0 && this.canAlloc()) { this.openAlloc(); return; }
    if (input.cancel() || input.pressed('info')) { audio.sfx('cancel'); game.remove(this); if (this.opts.onClose) this.opts.onClose(); }
  }

  openAlloc() {
    audio.sfx('confirm');
    this.alloc = { pending: {}, row: 0 };
  }

  updateAlloc(game) {
    const input = game.input;
    const A = this.alloc;
    const u = this.u;
    const rows = ALLOC_ROWS.length + 3; // + 推荐 / 确认 / 取消
    if (input.repeat('up')) { A.row = (A.row - 1 + rows) % rows; audio.sfx('cursor'); }
    if (input.repeat('down')) { A.row = (A.row + 1) % rows; audio.sfx('cursor'); }
    const m = input.mouse;
    let hover = -1;
    for (let i = 0; i < rows; i++) {
      const r = allocRowRect(i);
      if (m.x >= r.x && m.x < r.x + r.w && m.y >= r.y && m.y < r.y + r.h) hover = i;
    }
    if (hover >= 0 && m.moved) A.row = hover;
    const s = ALLOC_ROWS[A.row];
    const inc = () => {
      const why = R.allocBlock(u, s, A.pending);
      if (why) { audio.sfx('error'); game.showToast(why); return; }
      A.pending[s] = (A.pending[s] || 0) + R.allocGain(s);
      audio.sfx('statup');
    };
    const dec = () => {
      if (!A.pending[s]) { audio.sfx('error'); return; }
      A.pending[s] -= R.allocGain(s);
      if (!A.pending[s]) delete A.pending[s];
      audio.sfx('cancel');
    };
    if (s) {
      if (input.repeat('right')) inc();
      if (input.repeat('left')) dec();
      if (input.click() && hover === A.row) { if (m.x >= 280) inc(); else if (m.x >= 250) dec(); }
    }
    const act = (i) => {
      const k = i - ALLOC_ROWS.length;
      if (k === 0) { A.pending = R.recommendAlloc(u); audio.sfx('confirm'); }
      else if (k === 1) {
        if (!Object.keys(A.pending).length) { audio.sfx('error'); return; }
        R.applyAlloc(u, A.pending);
        audio.sfx('levelup');
        game.showToast(`${u.name} 的能力提升了`);
        this.alloc = null;
        if (this.opts.onChange) this.opts.onChange(u);
      } else if (k === 2) { this.alloc = null; audio.sfx('cancel'); }
    };
    if (input.confirm() || (input.click() && hover >= ALLOC_ROWS.length)) {
      if (A.row >= ALLOC_ROWS.length) act(A.row);
      else inc();
    }
    if (input.cancel()) {
      if (Object.keys(A.pending).length) game.push(new ConfirmDialog('放弃这次加点？', (yes) => { if (yes) this.alloc = null; }));
      else { this.alloc = null; audio.sfx('cancel'); }
    }
  }

  draw(ctx, game) {
    const u = this.u;
    ctx.globalAlpha = 0.8; fill(ctx, 0, 0, W, H, '#05040a'); ctx.globalAlpha = 1;
    // 左栏：头像与基本信息
    const style = u.team === 'enemy' ? 'red' : u.team === 'player' ? 'blue' : 'green';
    drawWindow(ctx, 2, 2, 112, 176, style);
    drawPortrait(ctx, u.portrait || 'soldier', 'normal', 18, 6, false);
    drawText(ctx, u.name, 58, 90, '#ffffff', { align: 'center', shadow: '#000' });
    drawText(ctx, className(u), 58, 105, '#f8e0a0', { align: 'center', shadow: '#000' });
    drawText(ctx, `Lv ${u.lv}`, 12, 122, '#c8d8ff', { shadow: '#000' });
    drawText(ctx, u.team === 'player' && u.lv < R.MAX_LEVEL ? `EXP ${u.exp}` : 'EXP --', 104, 122, '#c8d8ff', { align: 'right', shadow: '#000' });
    drawText(ctx, `HP ${u.hp}/${u.mhp}`, 12, 138, '#ffffff', { shadow: '#000' });
    drawBar(ctx, 12, 154, 90, 3, u.hp / u.mhp, '#78d060');
    if (u.team === 'player' && !u.escort) drawText(ctx, `潜能点 ${u.points || 0}`, 12, 161, u.points ? '#f8d040' : '#8a88a0', { shadow: '#000' });
    if (u.boss) drawText(ctx, '首领', 104, 161, '#f8d040', { align: 'right', shadow: '#000' });
    // 右栏
    drawWindow(ctx, 116, 2, W - 118, 176, 'menu');
    if (this.alloc) { this.drawAlloc(ctx, game); return; }
    const tabs = ['能力', '物品', '简介'];
    tabs.forEach((t, i) => drawText(ctx, t, 150 + i * 56, 6, i === this.page ? '#f8e0a0' : '#8a90b0', { align: 'center', shadow: '#000' }));
    fill(ctx, 124 + this.page * 56, 19, 52, 1, '#f8e0a0');
    if (this.page === 0) this.drawStats(ctx, game);
    else if (this.page === 1) this.drawItems(ctx);
    else this.drawBio(ctx);
    drawText(ctx, '←→ 翻页' + (this.opts.list && this.opts.list.length > 1 ? '  ↑↓ 切换人物' : '') + '  X 返回', 214, H - 14, '#8a90b0', { align: 'center', shadow: '#000' });
  }

  drawStats(ctx, game) {
    const u = this.u;
    STAT_KEYS.forEach((k, i) => {
      const col = i < 4 ? 0 : 1, row = i % 4;
      const x = 124 + col * 98, y = 26 + row * 18;
      const v = k === 'hp' ? u.mhp : R.stat(u, k);
      const cap = R.capOf(u, k);
      drawText(ctx, STAT_NAMES[k], x, y, '#c8d8ff', { shadow: '#000' });
      drawText(ctx, String(v), x + 60, y, v >= cap ? '#80ff80' : '#ffffff', { align: 'right', shadow: '#000' });
      drawBar(ctx, x + 64, y + 5, 26, 2, v / cap, '#f0c860', '#20243a');
    });
    const w = R.equipped(u);
    const wid = w ? w.id : null;
    const d = wid ? ITEMS[wid] : null;
    const atk = d ? (d.magic ? R.stat(u, 'mag') : R.stat(u, 'str')) + d.mt : 0;
    const hit = d ? d.hit + R.stat(u, 'skl') * 2 + Math.floor(R.stat(u, 'lck') / 2) : 0;
    const avo = R.attackSpeed(u, wid) * 2 + R.stat(u, 'lck');
    const crit = d ? (d.crit || 0) + Math.floor(R.stat(u, 'skl') / 2) : 0;
    const rows = [['移动', u.mov], ['攻击', d ? atk : '--'], ['命中', d ? hit : '--'], ['回避', avo], ['必杀', d ? crit : '--'], ['攻速', R.attackSpeed(u, wid)]];
    rows.forEach(([k, v], i) => {
      const x = 124 + (i % 3) * 64, y = 102 + Math.floor(i / 3) * 16;
      drawText(ctx, k, x, y, '#f8e0a0', { shadow: '#000' });
      drawText(ctx, String(v), x + 52, y, '#ffffff', { align: 'right', shadow: '#000' });
    });
    const traits = CLASSES[u.cls].traits.map((t) => TRAITS[t] && TRAITS[t].name).filter(Boolean);
    drawText(ctx, '特长：' + (traits.join('、') || '无'), 124, 136, '#e8e4d8', { shadow: '#000' });
    if (this.canAlloc()) {
      drawWindow(ctx, 236, 150, 76, 20, 'gold');
      drawText(ctx, 'Z 加点', 274, 154, '#fff4d8', { align: 'center', shadow: '#2a1804' });
    } else if (u.team === 'player' && !u.escort) {
      drawText(ctx, '升级后可获得潜能点', 124, 152, '#8a88a0', { shadow: '#000' });
    }
  }

  drawItems(ctx) {
    const u = this.u;
    u.items.forEach((it, i) => {
      const d = ITEMS[it.id];
      const y = 26 + i * 18;
      drawIcon(ctx, d.icon, 124, y - 2);
      drawText(ctx, d.name, 142, y, R.canUse(u, it.id) || d.type === 'item' ? '#ffffff' : '#9a98a8', { shadow: '#000' });
      if (R.equipIndex(u) === i && R.isAttackWeapon(it.id)) drawText(ctx, 'E', 206, y, '#f8d040', { shadow: '#000' });
      let info = '';
      if (d.type === 'item') info = d.uses ? `${it.uses}/${d.uses}` : '';
      else if (d.type === 'staff') info = `回复${d.heal}+`;
      else info = `威${d.mt} 中${d.hit} 射${d.rng[0]}-${d.rng[1]}`;
      drawText(ctx, info, W - 8, y, '#f8e8b0', { align: 'right', shadow: '#000' });
    });
    if (!u.items.length) drawText(ctx, '（没有物品）', 140, 30, '#8a88a0', { shadow: '#000' });
    const c = CLASSES[u.cls];
    drawText(ctx, '可用武器：' + (c.weapons.map((w) => ({ sword: '剑', lance: '枪', axe: '斧', bow: '弓', tome: '魔法', staff: '杖' })[w]).join('、') || '无'), 124, 122, '#c8d8ff', { shadow: '#000' });
  }

  drawBio(ctx) {
    const u = this.u;
    const c = CLASSES[u.cls];
    let y = 26;
    const bio = bios[u.id];
    if (bio) { for (const l of wrapText(bio, W - 134)) { drawText(ctx, l, 124, y, '#f0ece0', { shadow: '#000' }); y += 13; } y += 4; }
    for (const l of wrapText(`【${c.name}】${c.desc}`, W - 134)) { drawText(ctx, l, 124, y, '#c8d8ff', { shadow: '#000' }); y += 13; }
    for (const t of c.traits) {
      const tr = TRAITS[t];
      if (!tr) continue;
      for (const l of wrapText(`【${tr.name}】${tr.desc}`, W - 134)) { drawText(ctx, l, 124, y, '#f8e0a0', { shadow: '#000' }); y += 13; }
    }
  }

  drawAlloc(ctx, game) {
    const u = this.u;
    const A = this.alloc;
    const pts = (u.points || 0) - R.pendingCost(u, A.pending);
    drawText(ctx, `剩余潜能点 ${pts}`, 124, 6, '#f8d040', { shadow: '#000' });
    drawText(ctx, '费用', 224, 6, '#8a90b0', { shadow: '#000' });
    drawText(ctx, '已加/上限', W - 38, 6, '#8a90b0', { align: 'right', shadow: '#000' });
    ALLOC_ROWS.forEach((k, i) => {
      const y = allocRowRect(i).y + 1;
      const sel = A.row === i;
      if (sel) { ctx.globalAlpha = 0.25; fill(ctx, 120, y - 1, W - 124, 12, '#fff2c0'); ctx.globalAlpha = 1; drawPointer(ctx, 128, y + 5, game.frame); }
      const cur = k === 'hp' ? u.mhp : u[k];
      const add = A.pending[k] || 0;
      const fav = CLASSES[u.cls].favored.includes(k);
      drawText(ctx, STAT_NAMES[k] + (fav ? '★' : ''), 136, y, fav ? '#f8e0a0' : '#c8d8ff', { shadow: '#000' });
      drawText(ctx, String(cur), 196, y, '#ffffff', { align: 'right', shadow: '#000' });
      if (add) drawText(ctx, '+' + add, 199, y, '#80ff80', { shadow: '#000' });
      drawText(ctx, `${R.allocCost(u, k)}点`, 224, y, '#a8b0d0', { shadow: '#000' });
      const used = (u.alloc && u.alloc[k]) || 0;
      drawText(ctx, `${used + add}/${R.ALLOC_LIMIT[k]}`, W - 44, y, '#8a90b0', { align: 'right', shadow: '#000' });
      drawText(ctx, '－', W - 36, y, add ? '#ffb0a0' : '#5a5870', { shadow: '#000' });
      drawText(ctx, '＋', W - 20, y, R.allocBlock(u, k, A.pending) ? '#5a5870' : '#80ff80', { shadow: '#000' });
    });
    ['推荐加点', '确认', '取消'].forEach((t, j) => {
      const i = ALLOC_ROWS.length + j;
      const r = allocRowRect(i);
      drawWindow(ctx, r.x, r.y, r.w, r.h, A.row === i ? 'gold' : 'dark');
      drawText(ctx, t, r.x + r.w / 2, r.y + 3, '#ffffff', { align: 'center', shadow: '#000' });
    });
    const s = ALLOC_ROWS[A.row];
    const why = s ? R.allocBlock(u, s, A.pending) : null;
    const tips = ['推荐：按职业定位自动分配，确认前还可以再修改。', '确认后加点永久生效。', '放弃这次的分配。'];
    const tip = s ? (why ? `无法提升：${why}` : '←→ 调整。★专长 1 点 +1，其余 2 点 +1，HP 1 点 +2；每项最多 +5，移动仅 1 次。') : tips[A.row - ALLOC_ROWS.length];
    wrapText(tip, W - 132).slice(0, 2).forEach((l, i) => drawText(ctx, l, 124, 152 + i * 12, why ? '#ffb0a0' : '#a8b0d0', { shadow: '#000' }));
  }
}

function allocRowRect(i) {
  if (i < ALLOC_ROWS.length) return { x: 120, y: 19 + i * 12, w: W - 124, h: 12 };
  const j = i - ALLOC_ROWS.length;
  return { x: 124 + j * 64, y: 129, w: 60, h: 18 };
}
