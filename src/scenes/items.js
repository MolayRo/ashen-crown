// 物品界面：单位物品菜单、交换、运输队（仓库）
import { W, H } from '../core/renderer.js';
import { fill, drawWindow, drawPointer } from '../core/gfx.js';
import { drawText, wrapText } from '../core/font.js';
import { audio } from '../core/audio.js';
import { ListMenu } from '../ui/menu.js';
import { ITEMS } from '../game/data/items.js';
import * as R from '../game/rules.js';
import { MAX_ITEMS } from '../game/battle.js';
import { ConfirmDialog } from './confirm.js';
import { drawIcon, drawMini } from './map/hud.js';

export function itemLabel(it) {
  const d = ITEMS[it.id];
  return d.name;
}
export function itemUses(it) {
  const d = ITEMS[it.id];
  return d.type === 'item' && d.uses ? `${it.uses}/${d.uses}` : '';
}

function drawItemRow(ctx, u, it, x, y, sel, idx, dim = false) {
  const d = ITEMS[it.id];
  drawIcon(ctx, d.icon, x - 2, y - 2);
  const usable = !u || R.canUse(u, it.id);
  drawText(ctx, d.name, x + 16, y, dim || !usable ? '#9a98a8' : '#ffffff', { shadow: '#000' });
  if (u && R.equipIndex(u) === idx && R.isAttackWeapon(it.id)) drawText(ctx, 'E', x + 76, y, '#f8d040', { shadow: '#000' });
  const us = itemUses(it);
  if (us) drawText(ctx, us, x + 112, y, '#f8e8b0', { align: 'right', shadow: '#000' });
}

function drawItemDesc(ctx, it, u, y = 128) {
  if (!it) return;
  const d = ITEMS[it.id];
  drawWindow(ctx, 4, y, W - 8, H - y - 4, 'dark');
  let lines = [];
  if (d.type !== 'item') {
    const parts = [];
    if (d.mt != null) parts.push(`威力 ${d.mt}`);
    if (d.heal != null) parts.push(`回复 ${d.heal}+魔力`);
    if (d.hit != null && d.type !== 'staff') parts.push(`命中 ${d.hit}`);
    if (d.crit != null) parts.push(`必杀 ${d.crit}`);
    if (d.wt != null && d.type !== 'staff') parts.push(`重量 ${d.wt}`);
    if (d.rng) parts.push(`射程 ${d.rng[0]}~${d.rng[1] === 'mag' ? '魔力÷2' : d.rng[1]}`);
    lines.push(parts.join('  '));
  }
  lines = lines.concat(wrapText(d.desc, W - 28));
  if (u && d.type !== 'item' && !R.canUse(u, it.id)) lines.push(d.lock ? '（专属武器，无法使用）' : '（该职业无法使用这种武器）');
  lines.slice(0, 3).forEach((l, i) => drawText(ctx, l, 12, y + 5 + i * 13, i === 0 && d.type !== 'item' ? '#f8e0a0' : '#e8e4d8', { shadow: '#000' }));
}

// 单位的物品菜单（地图中 / 整备中）
export class ItemMenuScene {
  // opts: {state, inBattle, onUse(result), campaign(整备时), onChange}
  constructor(u, opts = {}) {
    this.overlay = true;
    this.u = u;
    this.opts = opts;
    this.sub = null;
    this.build();
  }
  build(index = 0) {
    const u = this.u;
    this.menu = new ListMenu(u.items.map((it, i) => ({ label: ITEMS[it.id].name, value: i })), {
      x: 8, y: 8, w: 150, visible: MAX_ITEMS, title: `${u.name} 的物品`, index,
      drawItem: (ctx, item, x, y, sel, i) => drawItemRow(ctx, u, u.items[item.value], x, y, sel, item.value),
    });
    if (!u.items.length) this.menu.items = [];
  }
  update(game) {
    const u = this.u;
    if (this.sub) {
      const r = this.sub.update(game.input);
      if (!r) return;
      if (r.type === 'cancel') { this.sub = null; return; }
      if (r.type === 'blocked') { game.showToast(r.item.reason); return; }
      if (r.type === 'select') this.doSub(game, r.item.value);
      return;
    }
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'cancel') { game.remove(this); if (this.opts.onClose) this.opts.onClose(); return; }
    if (r.type !== 'select') return;
    const idx = r.item.value;
    const it = u.items[idx];
    const d = ITEMS[it.id];
    const opts = [];
    if (R.isAttackWeapon(it.id)) {
      const can = R.canUse(u, it.id);
      opts.push({ label: '装备', value: 'equip', enabled: can && R.equipIndex(u) !== idx, reason: can ? '已经装备着' : (d.lock ? '专属武器' : '该职业无法使用') });
    }
    if (d.type === 'item') {
      const st = this.opts.state;
      let chk = { ok: true };
      if (st) chk = st.canUseItem(u, idx);
      else if (d.key) chk = { ok: false, why: '钥匙会在开门或开箱时自动使用' };
      else if (d.heal && u.hp >= u.mhp) chk = { ok: false, why: 'HP 已满' };
      opts.push({ label: '使用', value: 'use', enabled: chk.ok, reason: chk.why });
    }
    if (this.opts.campaign) opts.push({ label: '存入仓库', value: 'store' });
    opts.push({ label: '丢弃', value: 'drop', enabled: !d.lock, reason: '专属武器不能丢弃' });
    this.subIdx = idx;
    this.sub = new ListMenu(opts, { x: 162, y: 8 + 21 + idx * 16, w: 80, visible: opts.length, rowH: 14, padY: 4 });
  }
  doSub(game, v) {
    const u = this.u;
    const idx = this.subIdx;
    this.sub = null;
    if (v === 'equip') { u.equip = idx; audio.sfx('confirm'); this.build(idx); if (this.opts.onChange) this.opts.onChange(); }
    else if (v === 'use') {
      if (this.opts.inBattle) {
        const r = this.opts.state.useItem(u, idx);
        game.remove(this);
        if (this.opts.onUse) this.opts.onUse(r);
        return;
      }
      // 整备中使用（能力提升道具）
      const d = ITEMS[u.items[idx].id];
      const st = { canUseItem: () => ({ ok: true }) };
      void st;
      if (d.heal) { u.hp = Math.min(u.mhp, u.hp + d.heal); }
      if (d.boost) {
        for (const [s, val] of Object.entries(d.boost)) {
          const cap = R.capOf(u, s);
          const cur = s === 'hp' ? u.mhp : u[s];
          const add = Math.max(0, Math.min(val, cap - cur));
          if (s === 'hp') { u.mhp += add; u.hp += add; } else u[s] += add;
        }
      }
      const it = u.items[idx];
      it.uses -= 1;
      if (it.uses <= 0) { u.items.splice(idx, 1); if (u.equip != null && u.equip >= idx) u.equip = u.equip === idx ? null : u.equip - 1; }
      audio.sfx('statup');
      game.showToast(`${u.name} 使用了 ${d.name}`);
      this.build(Math.min(idx, u.items.length - 1));
      if (this.opts.onChange) this.opts.onChange();
    } else if (v === 'store') {
      const it = u.items.splice(idx, 1)[0];
      if (u.equip != null && u.equip >= idx) u.equip = u.equip === idx ? null : u.equip - 1;
      this.opts.campaign.convoy.push(it);
      audio.sfx('confirm');
      this.build(Math.max(0, Math.min(idx, u.items.length - 1)));
      if (this.opts.onChange) this.opts.onChange();
    } else if (v === 'drop') {
      game.push(new ConfirmDialog(`丢弃 ${ITEMS[u.items[idx].id].name}？`, (yes) => {
        if (!yes) return;
        u.items.splice(idx, 1);
        if (u.equip != null && u.equip >= idx) u.equip = u.equip === idx ? null : u.equip - 1;
        this.build(Math.max(0, Math.min(idx, u.items.length - 1)));
        if (this.opts.onChange) this.opts.onChange();
      }));
    }
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.6; fill(ctx, 0, 0, W, H, '#07060c'); ctx.globalAlpha = 1;
    this.menu.draw(ctx, game.frame);
    if (!this.u.items.length) drawText(ctx, '（没有物品）', 40, 34, '#9a98a8', { shadow: '#000' });
    const cur = this.u.items[this.sub ? this.subIdx : this.menu.index];
    drawItemDesc(ctx, cur, this.u);
    if (this.sub) {
      this.sub.draw(ctx, game.frame);
      const it = this.sub.current();
      if (it && it.enabled === false) drawText(ctx, it.reason, 250, this.sub.y + 4, '#ffb0a0', { shadow: '#000' });
    }
  }
}

// 交换
export class TradeScene {
  constructor(a, b, opts = {}) {
    this.overlay = true;
    this.a = a; this.b = b;
    this.opts = opts;
    this.side = 0;
    this.row = 0;
    this.pick = null;
    this.changed = false;
  }
  units() { return [this.a, this.b]; }
  rowRect(side, row) { return { x: side === 0 ? 8 : W / 2 + 4, y: 50 + row * 16, w: W / 2 - 12, h: 16 }; }
  update(game) {
    const input = game.input;
    const d = input.dir();
    if (d === 'up') { this.row = (this.row + MAX_ITEMS - 1) % MAX_ITEMS; audio.sfx('cursor'); }
    if (d === 'down') { this.row = (this.row + 1) % MAX_ITEMS; audio.sfx('cursor'); }
    if (d === 'left' || d === 'right') { this.side = 1 - this.side; audio.sfx('cursor'); }
    const m = input.mouse;
    let hover = null;
    for (let s = 0; s < 2; s++) for (let r = 0; r < MAX_ITEMS; r++) {
      const rr = this.rowRect(s, r);
      if (m.x >= rr.x && m.x < rr.x + rr.w && m.y >= rr.y && m.y < rr.y + rr.h) hover = [s, r];
    }
    if (hover && m.moved) { this.side = hover[0]; this.row = hover[1]; }
    if (input.cancel()) {
      if (this.pick) { this.pick = null; audio.sfx('cancel'); return; }
      audio.sfx('cancel');
      game.remove(this);
      if (this.opts.onClose) this.opts.onClose(this.changed);
      return;
    }
    if (input.confirm() || (input.click() && hover)) {
      const us = this.units();
      if (!this.pick) {
        const it = us[this.side].items[this.row];
        if (!it) { audio.sfx('error'); return; }
        const d = ITEMS[it.id];
        if (d.lock && d.lock === us[this.side].id) { audio.sfx('error'); game.showToast('专属武器不能交给别人'); return; }
        this.pick = { side: this.side, row: this.row };
        this.side = 1 - this.side;
        this.row = Math.min(this.row, us[this.side].items.length);
        audio.sfx('confirm');
        return;
      }
      if (this.side === this.pick.side) { this.pick = { side: this.side, row: this.row }; return; }
      const src = us[this.pick.side], dst = us[this.side];
      const itA = src.items[this.pick.row];
      const itB = dst.items[this.row];
      if (itB) {
        const d = ITEMS[itB.id];
        if (d.lock && d.lock === dst.id) { audio.sfx('error'); game.showToast('专属武器不能交给别人'); return; }
        src.items[this.pick.row] = itB;
        dst.items[this.row] = itA;
      } else {
        if (dst.items.length >= MAX_ITEMS) { audio.sfx('error'); return; }
        src.items.splice(this.pick.row, 1);
        dst.items.push(itA);
      }
      for (const u of us) if (u.equip != null && (!u.items[u.equip] || !R.canUse(u, u.items[u.equip].id))) u.equip = null;
      this.pick = null;
      this.changed = true;
      audio.sfx('confirm');
    }
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.88; fill(ctx, 0, 0, W, H, '#07060c'); ctx.globalAlpha = 1;
    const us = this.units();
    for (let s = 0; s < 2; s++) {
      const u = us[s];
      const x = s === 0 ? 4 : W / 2;
      drawWindow(ctx, x, 4, W / 2 - 4, 132, s === this.side ? 'blue' : 'menu');
      drawMini(ctx, u.portrait, x + 6, 8);
      drawText(ctx, u.name, x + 44, 12, '#fff', { shadow: '#000' });
      drawText(ctx, `${u.items.length}/${MAX_ITEMS}`, x + W / 2 - 14, 12, '#c8d8ff', { align: 'right', shadow: '#000' });
      for (let r = 0; r < MAX_ITEMS; r++) {
        const rr = this.rowRect(s, r);
        const it = u.items[r];
        if (this.pick && this.pick.side === s && this.pick.row === r) { ctx.globalAlpha = 0.35; fill(ctx, rr.x, rr.y, rr.w, rr.h, '#f8d040'); ctx.globalAlpha = 1; }
        if (it) drawItemRow(ctx, u, it, rr.x + 18, rr.y + 2, false, r);
        else drawText(ctx, '—', rr.x + 34, rr.y + 2, '#6a6878');
        if (s === this.side && r === this.row) drawPointer(ctx, rr.x + 12, rr.y + 8, game.frame);
      }
    }
    const cur = us[this.side].items[this.row];
    drawItemDesc(ctx, cur, us[this.side], 140);
    if (!cur) { drawWindow(ctx, 4, 140, W - 8, 36, 'dark'); drawText(ctx, this.pick ? '选择要放到哪里（空位 = 直接交给对方）' : '选择要交换的物品，X 结束交换', 12, 146, '#e8e4d8', { shadow: '#000' }); }
  }
}

// 运输队（仓库）：取出 / 存入
export class ConvoyScene {
  constructor(campaign, u, opts = {}) {
    this.overlay = true;
    this.c = campaign;
    this.u = u;
    this.opts = opts;
    this.side = 0; // 0 仓库 1 单位
    this.build();
  }
  build(ci = 0, ui = 0) {
    const c = this.c, u = this.u;
    this.left = new ListMenu(c.convoy.map((it, i) => ({ label: ITEMS[it.id].name, value: i })), {
      x: 4, y: 20, w: 150, visible: 7, title: `运输队（${c.convoy.length}）`, index: ci, sound: false,
      drawItem: (ctx, item, x, y) => drawItemRow(ctx, u, c.convoy[item.value], x, y, false, -1),
    });
    this.right = new ListMenu(u.items.map((it, i) => ({ label: ITEMS[it.id].name, value: i })), {
      x: 166, y: 20, w: 150, visible: MAX_ITEMS, title: `${u.name}（${u.items.length}/${MAX_ITEMS}）`, index: ui, sound: false,
      drawItem: (ctx, item, x, y) => drawItemRow(ctx, u, u.items[item.value], x, y, false, item.value),
    });
  }
  update(game) {
    const input = game.input;
    if (input.pressed('left') || input.pressed('right')) { this.side = 1 - this.side; audio.sfx('cursor'); return; }
    const m = input.mouse;
    if (m.moved) this.side = m.x < W / 2 ? 0 : 1;
    const menu = this.side === 0 ? this.left : this.right;
    const r = menu.update(input);
    if (!r) return;
    if (r.type === 'cancel') { game.remove(this); if (this.opts.onClose) this.opts.onClose(); return; }
    if (r.type !== 'select') return;
    const c = this.c, u = this.u;
    if (this.side === 0) {
      if (u.items.length >= MAX_ITEMS) { audio.sfx('error'); game.showToast('物品已满（最多 5 件）'); return; }
      const it = c.convoy.splice(r.item.value, 1)[0];
      u.items.push(it);
      audio.sfx('confirm');
    } else {
      const idx = r.item.value;
      const d = ITEMS[u.items[idx].id];
      if (d.lock) { audio.sfx('error'); game.showToast('专属武器请随身携带'); return; }
      const it = u.items.splice(idx, 1)[0];
      if (u.equip != null && u.equip >= idx) u.equip = u.equip === idx ? null : u.equip - 1;
      c.convoy.push(it);
      audio.sfx('confirm');
    }
    this.build(Math.min(this.left.index, Math.max(0, c.convoy.length - 1)), Math.min(this.right.index, Math.max(0, u.items.length - 1)));
    if (this.opts.onChange) this.opts.onChange();
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.88; fill(ctx, 0, 0, W, H, '#07060c'); ctx.globalAlpha = 1;
    drawText(ctx, '运输队：←→ 切换　Z 取出/存入　X 返回', W / 2, 4, '#f8e0a0', { align: 'center', shadow: '#000' });
    this.left.draw(ctx, this.side === 0 ? game.frame : 0);
    this.right.draw(ctx, this.side === 1 ? game.frame : 0);
    if (!this.c.convoy.length) drawText(ctx, '（空）', 60, 48, '#8a88a0', { shadow: '#000' });
    const menu = this.side === 0 ? this.left : this.right;
    const list = this.side === 0 ? this.c.convoy : this.u.items;
    drawItemDesc(ctx, list[menu.index], this.u, 140);
  }
}
