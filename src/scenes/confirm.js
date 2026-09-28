// 确认对话框（覆盖层）
import { W, H } from '../core/renderer.js';
import { drawWindow, fill } from '../core/gfx.js';
import { drawText, wrapText } from '../core/font.js';
import { ListMenu } from '../ui/menu.js';

export class ConfirmDialog {
  constructor(message, cb, opts = {}) {
    this.overlay = true;
    this.message = message;
    this.cb = cb;
    this.lines = wrapText(message, 200);
    const h = this.lines.length * 14 + 12;
    this.boxH = h;
    this.menu = new ListMenu([
      { label: opts.yes || '是', value: true },
      { label: opts.no || '否', value: false },
    ], { x: W / 2 - 40, y: H / 2 + h / 2 - 6, w: 80, align: 'center', index: opts.defaultNo === false ? 0 : 1 });
    this.single = !!opts.single;
    if (this.single) this.menu = new ListMenu([{ label: opts.ok || '确定', value: true }], { x: W / 2 - 40, y: H / 2 + h / 2 - 6, w: 80, align: 'center' });
  }

  update(game) {
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'select') { game.remove(this); this.cb && this.cb(r.item.value); game.input.consumeAll(); }
    else if (r.type === 'cancel') { game.remove(this); this.cb && this.cb(false); game.input.consumeAll(); }
  }

  draw(ctx, game) {
    ctx.globalAlpha = 0.45;
    fill(ctx, 0, 0, W, H, '#000');
    ctx.globalAlpha = 1;
    const bw = 220;
    const bx = (W - bw) / 2;
    const by = H / 2 - this.boxH / 2 - 26;
    drawWindow(ctx, bx, by, bw, this.boxH + 8, 'menu');
    this.lines.forEach((l, i) => drawText(ctx, l, W / 2, by + 9 + i * 14, '#ffffff', { align: 'center', shadow: '#000' }));
    this.menu.draw(ctx, game.frame);
  }
}

// 纯提示框
export function alertBox(game, message, cb) {
  game.push(new ConfirmDialog(message, () => cb && cb(), { single: true }));
}
