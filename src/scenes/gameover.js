// 战败画面：重新开始本章 / 读取存档 / 返回标题
import { W, H } from '../core/renderer.js';
import { fill } from '../core/gfx.js';
import { drawText, drawTextScaled } from '../core/font.js';
import { ListMenu } from '../ui/menu.js';
import { restartChapter, toTitle, loadFromSave } from './flowctl.js';
import { readSave } from '../game/saves.js';
import { SaveLoadScene } from './saveload.js';

const REASONS = { lord: '艾尔文倒下了……', escort: '玛莎没能逃出去……', occupied: '霜牙关要塞被攻陷了……' };

export class GameOverScene {
  constructor(state, why) {
    this.state = state;
    this.why = why;
    this.t = 0;
    this.menu = new ListMenu([
      { label: '重新开始本章', value: 'restart' },
      { label: '读取存档', value: 'load' },
      { label: '返回标题', value: 'title' },
    ], { x: W / 2 - 60, y: 110, w: 120, align: 'center', cancelable: false });
  }
  update(game) {
    this.t++;
    if (this.t < 60) return;
    if (game.autotest && this.t === 90) {
      window.__autotest.failures++;
      if (window.__autotest.failures <= 5) { game.autotestNote('战败，重新开始本章'); restartChapter(game); }
      else { game.autotestNote('战败次数过多，停止'); window.__autotest.done = true; }
      return;
    }
    const r = this.menu.update(game.input);
    if (!r || r.type !== 'select') return;
    if (r.item.value === 'restart') {
      if (game.chapterSnapshot) restartChapter(game);
      else {
        const auto = readSave('auto');
        if (auto && auto.campaign.chapter === game.campaign.chapter) loadFromSave(game, auto);
        else toTitle(game);
      }
    } else if (r.item.value === 'load') game.push(new SaveLoadScene('load'));
    else toTitle(game);
  }
  draw(ctx, game) {
    const a = Math.min(1, this.t / 60);
    ctx.globalAlpha = a;
    fill(ctx, 0, 0, W, H, '#0a0306');
    drawTextScaled(ctx, '战　败', W / 2, 40, '#c83030', 3, { align: 'center', outline: '#200000' });
    drawText(ctx, REASONS[this.why] || '战斗失败了……', W / 2, 88, '#e0c8c0', { align: 'center', shadow: '#000' });
    ctx.globalAlpha = 1;
    if (this.t >= 60) this.menu.draw(ctx, game.frame);
  }
}
