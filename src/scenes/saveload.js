// 存档 / 读档界面
import { W, H } from '../core/renderer.js';
import { fill, drawWindow, drawPointer } from '../core/gfx.js';
import { drawText } from '../core/font.js';
import { audio } from '../core/audio.js';
import { listSaves, writeSave, fmtTime, fmtDate } from '../game/saves.js';
import { DIFFICULTY_NAMES, MODE_NAMES } from '../game/campaign.js';
import { ConfirmDialog } from './confirm.js';
import { loadFromSave } from './flowctl.js';

export class SaveLoadScene {
  // mode: 'save' | 'load'；battle：地图中存档时传入当前战斗
  constructor(mode, opts = {}) {
    this.overlay = true;
    this.mode = mode;
    this.battle = opts.battle || null;
    this.onSaved = opts.onSaved || null;
    this.refresh();
    this.index = mode === 'save' ? 1 : Math.max(0, this.slots.findIndex((s) => s.data));
  }
  refresh() { this.slots = listSaves(); }

  slotRect(i) { return { x: 20, y: 28 + i * 34, w: W - 40, h: 32 }; }

  update(game) {
    const input = game.input;
    const n = this.slots.length;
    if (input.repeat('up')) { this.index = (this.index - 1 + n) % n; audio.sfx('cursor'); }
    if (input.repeat('down')) { this.index = (this.index + 1) % n; audio.sfx('cursor'); }
    const m = input.mouse;
    let hover = -1;
    for (let i = 0; i < n; i++) { const r = this.slotRect(i); if (m.x >= r.x && m.x < r.x + r.w && m.y >= r.y && m.y < r.y + r.h) hover = i; }
    if (hover >= 0 && m.moved) this.index = hover;
    if (input.cancel()) { audio.sfx('cancel'); game.pop(); return; }
    if (input.confirm() || (input.click() && hover >= 0)) this.choose(game);
  }

  choose(game) {
    const s = this.slots[this.index];
    if (this.mode === 'save') {
      if (s.slot === 'auto') { audio.sfx('error'); game.showToast('自动存档位只在每章开战前自动写入'); return; }
      const doSave = () => {
        const ok = writeSave(s.slot, game.campaign, this.battle);
        audio.sfx(ok ? 'save' : 'error');
        game.showToast(ok ? `已保存到 存档 ${s.slot}` : '保存失败：浏览器存储不可用');
        this.refresh();
        if (this.onSaved) this.onSaved();
      };
      if (s.data) game.push(new ConfirmDialog(`覆盖 存档 ${s.slot}？`, (yes) => { if (yes) doSave(); }));
      else doSave();
    } else {
      if (!s.data) { audio.sfx('error'); game.showToast('这个存档位是空的'); return; }
      const go = () => { audio.sfx('confirm'); loadFromSave(game, s.data); };
      if (game.campaign) game.push(new ConfirmDialog('读取这个存档？当前未保存的进度将会丢失。', (yes) => { if (yes) go(); }));
      else go();
    }
  }

  draw(ctx, game) {
    ctx.globalAlpha = 0.75;
    fill(ctx, 0, 0, W, H, '#05040a');
    ctx.globalAlpha = 1;
    drawWindow(ctx, 12, 4, W - 24, 22, 'gold');
    drawText(ctx, this.mode === 'save' ? '保存进度' : '读取存档', W / 2, 9, '#fff4d8', { align: 'center', shadow: '#2a1804' });
    this.slots.forEach((s, i) => {
      const r = this.slotRect(i);
      const sel = i === this.index;
      const disabled = (this.mode === 'save' && s.slot === 'auto') || (this.mode === 'load' && !s.data);
      drawWindow(ctx, r.x, r.y, r.w, r.h, sel ? 'blue' : 'menu', disabled ? 0.75 : 1);
      const name = s.slot === 'auto' ? '自动存档' : `存档 ${s.slot}`;
      drawText(ctx, name, r.x + 20, r.y + 3, disabled ? '#8a88a0' : '#f8e0a0', { shadow: '#000' });
      if (s.data) {
        const d = s.data;
        drawText(ctx, `${d.label.chapter}  ${d.label.stage}`, r.x + 84, r.y + 3, '#ffffff', { shadow: '#000' });
        drawText(ctx, `${DIFFICULTY_NAMES[d.difficulty] || ''} · ${MODE_NAMES[d.mode] || ''}  艾尔文 Lv.${d.lv}`, r.x + 20, r.y + 17, '#c8d0f0', { shadow: '#000' });
        drawText(ctx, `${fmtTime(d.playtime)}  ${fmtDate(d.time)}`, r.x + r.w - 8, r.y + 17, '#a8b0d0', { align: 'right', shadow: '#000' });
      } else {
        drawText(ctx, '—— 空 ——', r.x + 84, r.y + 3, '#8a88a0', { shadow: '#000' });
      }
      if (sel) drawPointer(ctx, r.x + 12, r.y + 9, game.frame);
    });
    drawText(ctx, this.mode === 'save' ? '选择存档位保存（自动存档只能读取）　Esc 返回' : '选择要读取的存档　Esc 返回', W / 2, H - 12, '#a8b0d0', { align: 'center', shadow: '#000' });
  }
}
