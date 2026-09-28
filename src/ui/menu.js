// 通用列表菜单：键盘/鼠标/滚轮，禁用项显示原因
import { drawWindow, drawPointer, fill, drawArrow } from '../core/gfx.js';
import { drawText, textWidth } from '../core/font.js';
import { audio } from '../core/audio.js';

export class ListMenu {
  // items: [{label, value, enabled=true, reason, right, color, icon}]
  constructor(items, opts = {}) {
    this.items = items;
    this.x = opts.x ?? 8;
    this.y = opts.y ?? 8;
    this.rowH = opts.rowH ?? 16;
    this.padX = opts.padX ?? 18;
    this.padY = opts.padY ?? 5;
    this.visible = opts.visible ?? Math.min(items.length, 9);
    this.style = opts.style ?? 'menu';
    this.minW = opts.minW ?? 0;
    this.fixedW = opts.w ?? null;
    this.index = opts.index ?? 0;
    this.scroll = 0;
    this.title = opts.title ?? null;
    this.onChange = opts.onChange ?? null;
    this.cancelable = opts.cancelable ?? true;
    this.sound = opts.sound ?? true;
    this.drawItem = opts.drawItem ?? null;
    this.noWindow = opts.noWindow ?? false;
    this.align = opts.align ?? 'left';
    this.hoverIndex = -1;
    this._ensureValid(1);
    this._clampScroll();
  }

  get w() {
    if (this.fixedW) return this.fixedW;
    let m = this.minW;
    for (const it of this.items) m = Math.max(m, textWidth(it.label) + this.padX + 10 + (it.right ? textWidth(String(it.right)) + 12 : 0));
    return m;
  }
  get h() { return this.visible * this.rowH + this.padY * 2; }

  current() { return this.items[this.index]; }

  _ensureValid(dir) {
    if (!this.items.length) return;
    this.index = Math.max(0, Math.min(this.items.length - 1, this.index));
  }

  _clampScroll() {
    if (this.index < this.scroll) this.scroll = this.index;
    if (this.index >= this.scroll + this.visible) this.scroll = this.index - this.visible + 1;
    this.scroll = Math.max(0, Math.min(Math.max(0, this.items.length - this.visible), this.scroll));
  }

  setIndex(i, silent = false) {
    if (i === this.index) return;
    this.index = i;
    this._clampScroll();
    if (!silent && this.sound) audio.sfx('cursor');
    if (this.onChange) this.onChange(this.current(), this.index);
  }

  // 返回 {type: 'select'|'cancel'|'blocked', item}
  update(input) {
    if (!this.items.length) {
      if (input.cancel() && this.cancelable) return { type: 'cancel' };
      return null;
    }
    const n = this.items.length;
    if (input.repeat('up')) this.setIndex((this.index - 1 + n) % n);
    if (input.repeat('down')) this.setIndex((this.index + 1) % n);
    if (input.mouse.wheel) {
      const d = input.mouse.wheel > 0 ? 1 : -1;
      if (n > this.visible) {
        this.scroll = Math.max(0, Math.min(n - this.visible, this.scroll + d));
        if (this.index < this.scroll) this.setIndex(this.scroll, true);
        if (this.index >= this.scroll + this.visible) this.setIndex(this.scroll + this.visible - 1, true);
      } else {
        this.setIndex(Math.max(0, Math.min(n - 1, this.index + d)));
      }
    }
    // 鼠标悬停
    const m = input.mouse;
    this.hoverIndex = -1;
    const hit = this.hitTest(m.x, m.y);
    if (hit >= 0) {
      this.hoverIndex = hit;
      if (m.moved && hit !== this.index) this.setIndex(hit);
    }
    if (input.confirm() || (input.click() && hit >= 0)) {
      if (input.click() && hit >= 0) this.setIndex(hit, true);
      const it = this.current();
      if (it.enabled === false) {
        if (this.sound) audio.sfx('error');
        return { type: 'blocked', item: it };
      }
      if (this.sound) audio.sfx('confirm');
      return { type: 'select', item: it, index: this.index };
    }
    if (input.cancel() && this.cancelable) {
      if (this.sound) audio.sfx('cancel');
      return { type: 'cancel' };
    }
    return null;
  }

  hitTest(mx, my) {
    const x0 = this.x, y0 = this.y + this.padY + (this.title ? 16 : 0);
    if (mx < x0 || mx >= x0 + this.w) return -1;
    const r = Math.floor((my - y0) / this.rowH);
    if (my < y0 || r < 0 || r >= this.visible) return -1;
    const i = this.scroll + r;
    return i < this.items.length ? i : -1;
  }

  draw(ctx, frame = 0) {
    const w = this.w;
    const th = this.title ? 16 : 0;
    if (!this.noWindow) drawWindow(ctx, this.x, this.y, w, this.h + th, this.style);
    if (this.title) {
      drawText(ctx, this.title, this.x + 8, this.y + 5, '#f8e0a0', { shadow: '#10081c' });
      fill(ctx, this.x + 6, this.y + 19, w - 12, 1, 'rgba(255,240,200,0.25)');
    }
    const y0 = this.y + this.padY + th;
    for (let r = 0; r < this.visible; r++) {
      const i = this.scroll + r;
      if (i >= this.items.length) break;
      const it = this.items[i];
      const y = y0 + r * this.rowH;
      if (i === this.index) {
        ctx.globalAlpha = 0.28;
        fill(ctx, this.x + 4, y, w - 8, this.rowH, '#fff2c0');
        ctx.globalAlpha = 1;
      }
      if (this.drawItem) {
        this.drawItem(ctx, it, this.x + this.padX, y + Math.floor((this.rowH - 12) / 2), i === this.index, i);
      } else {
        const col = it.enabled === false ? '#8a8898' : (it.color || '#ffffff');
        const tx = this.align === 'center' ? this.x + w / 2 : this.x + this.padX;
        drawText(ctx, it.label, tx, y + Math.floor((this.rowH - 12) / 2), col, { shadow: '#0b0a16', align: this.align === 'center' ? 'center' : undefined });
        if (it.right != null) drawText(ctx, String(it.right), this.x + w - 8, y + Math.floor((this.rowH - 12) / 2), it.enabled === false ? '#8a8898' : '#f8e8b0', { shadow: '#0b0a16', align: 'right' });
      }
      if (i === this.index) drawPointer(ctx, this.x + (this.align === 'center' ? Math.max(10, w / 2 - textWidth(it.label) / 2 - 4) : 12), y + Math.floor(this.rowH / 2), frame);
    }
    if (this.scroll > 0) drawArrow(ctx, this.x + w / 2, this.y + th + 1, 'up');
    if (this.scroll + this.visible < this.items.length) drawArrow(ctx, this.x + w / 2, this.y + this.h + th - 5, 'down');
  }
}

// 底部帮助/说明条
export function drawHelpBar(ctx, text, y = 164, style = 'dark') {
  drawWindow(ctx, 2, y, 316, 16, style, 0.94);
  drawText(ctx, text, 8, y + 2, '#e8e0c8', { shadow: '#000' });
}
