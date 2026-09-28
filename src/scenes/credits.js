// 制作人员与素材来源（结局时自动滚动）
import { W, H } from '../core/renderer.js';
import { fill } from '../core/gfx.js';
import { drawText, drawTextScaled } from '../core/font.js';
import { images } from '../core/assets.js';
import { audio } from '../core/audio.js';

export const CREDITS = [
  ['title', '灰烬王冠'],
  ['sub', 'THE ASHEN CROWN'],
  ['gap'],
  ['head', '企划 · 剧本 · 程序 · 美术 · 音乐'],
  ['line', 'Claude（Anthropic）独立制作'],
  ['line', '应玩家委托完成的原创中文战棋作品'],
  ['gap'],
  ['head', '引擎'],
  ['line', '原生 JavaScript + Canvas 2D + WebGL（CRT 着色器）'],
  ['line', '无第三方运行库'],
  ['gap'],
  ['head', '美术'],
  ['line', '地图、角色头像、地图小人、战斗动画、背景、图标'],
  ['line', '全部由 Python + Pillow 程序化绘制的原创像素画'],
  ['gap'],
  ['head', '音乐与音效'],
  ['line', '浏览器内实时合成的原创芯片音乐与音效'],
  ['line', '（方波、三角波、噪声与采样器风格音色）'],
  ['gap'],
  ['head', '字体'],
  ['line', 'Fusion Pixel Font 缝合像素字体 12px'],
  ['line', '作者 TakWolf · SIL Open Font License 1.1'],
  ['line', 'github.com/TakWolf/fusion-pixel-font'],
  ['line', '内含 Ark Pixel Font（TakWolf）、Cubic 11（ACh-K）'],
  ['line', '与 Galmuri（Minseo Lee）字形，均为 OFL 1.1'],
  ['gap'],
  ['head', '素材许可说明'],
  ['line', '除上述字体外，所有图像、音乐、音效与文本'],
  ['line', '均为本作原创，未使用任何商业游戏资产。'],
  ['line', '详细清单见 docs/素材来源与许可.md'],
  ['gap'],
  ['head', '灵感来源'],
  ['line', '致敬 GBA 时代的《火焰纹章》系列'],
  ['line', '（本作与其无任何关联，角色、地图、音乐均为原创）'],
  ['gap'],
  ['gap'],
  ['end', '感谢游玩'],
];

export class CreditsScene {
  constructor(opts = {}) {
    this.ending = !!opts.ending;
    this.overlay = !this.ending;
    this.y = this.ending ? H + 10 : 30;
    this.t = 0;
  }
  enter() {
    if (this.ending) audio.playMusic('ending', { fade: 1.5 });
  }
  totalH() {
    let h = 0;
    for (const [k] of CREDITS) h += k === 'gap' ? 10 : k === 'title' ? 34 : 15;
    return h;
  }
  update(game) {
    this.t++;
    const input = game.input;
    const speed = input.fast() ? 2 : 0.35;
    if (this.ending) {
      this.y -= speed;
      if (game.autotest) this.y -= 6;
      if (this.y < -this.totalH() + 60) {
        this.y = -this.totalH() + 60;
        if (!this.finished && game.autotest && window.__autotest) { game.autotestNote('制作人员名单播放完毕：全流程通关'); window.__autotest.done = true; }
        this.finished = true;
      }
      if (this.finished && (input.confirm() || input.click() || input.cancel())) {
        import('./flowctl.js').then((m) => m.toTitle(game));
        this.finished = false;
        this.leaving = true;
      }
      return;
    }
    if (input.repeat('down') || input.mouse.wheel > 0) this.y -= 12;
    if (input.repeat('up') || input.mouse.wheel < 0) this.y += 12;
    this.y = Math.min(30, Math.max(-this.totalH() + 140, this.y));
    if (input.cancel() || input.confirm() || input.click()) { audio.sfx('cancel'); game.pop(); }
  }
  draw(ctx) {
    fill(ctx, 0, 0, W, H, '#07060b');
    const bg = images.bg_capital_dawn;
    if (this.ending && bg) { ctx.globalAlpha = 0.35; ctx.drawImage(bg, 0, 0); ctx.globalAlpha = 1; }
    let y = Math.round(this.y);
    for (const [k, v] of CREDITS) {
      if (k === 'gap') { y += 10; continue; }
      if (k === 'title') { drawTextScaled(ctx, v, W / 2, y, '#f8d070', 2, { align: 'center', outline: '#2a1004' }); y += 34; continue; }
      const col = k === 'head' ? '#f8c860' : k === 'sub' ? '#b89860' : k === 'end' ? '#fff4d8' : '#e8e4d8';
      drawText(ctx, v, W / 2, y, col, { align: 'center', shadow: '#000' });
      y += 15;
    }
    if (!this.ending) drawText(ctx, '↑↓ 滚动　Esc 返回', W / 2, H - 14, '#8a88a0', { align: 'center', shadow: '#000' });
    else if (this.finished && Math.floor(this.t / 30) % 2 === 0) drawText(ctx, '— 完 —　按任意键返回标题', W / 2, H - 16, '#f0d8a0', { align: 'center', shadow: '#000' });
  }
}
