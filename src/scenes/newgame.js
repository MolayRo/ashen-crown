// 新游戏：选择难度与模式
import { W, H } from '../core/renderer.js';
import { fill, drawWindow } from '../core/gfx.js';
import { drawText, wrapText } from '../core/font.js';
import { ListMenu } from '../ui/menu.js';
import { newGame } from './flowctl.js';
import { audio } from '../core/audio.js';

const DIFFS = [
  { value: 'easy', label: '简单', desc: '敌军等级较低、能力较弱，部分敌人不会出现，AI 攻击时不会刻意集火；初始金钱与道具更充足，获得的金钱 ×1.5。适合想专注于剧情的玩家。' },
  { value: 'normal', label: '普通', desc: '标准难度。需要合理利用地形、武器克制与治疗，才能顺利推进。' },
  { value: 'hard', label: '困难', desc: '敌军等级 +2 且力量、速度更高，首领更强，会出现额外的敌兵；AI 优先集火可击杀的目标与治疗者；初始资源少，获得的金钱 ×0.7。' },
];
const MODES = [
  { value: 'casual', label: '休闲模式', desc: '伙伴在战斗中倒下时只会撤退，本章结束后归队。王子倒下仍会失败。' },
  { value: 'classic', label: '经典模式', desc: '伙伴倒下即永久阵亡，之后的剧情与队伍都会反映这一点。王子倒下即失败。' },
];

export class NewGameScene {
  constructor() {
    this.overlay = true;
    this.step = 0;
    this.diff = null;
    this.menu = this.diffMenu();
  }
  diffMenu() {
    return new ListMenu(DIFFS.map((d) => ({ ...d })), { x: 24, y: 40, w: 90, visible: 3, index: 1, title: '选择难度' });
  }
  modeMenu() {
    return new ListMenu(MODES.map((d) => ({ ...d })), { x: 24, y: 40, w: 110, visible: 2, index: 1, title: '选择模式' });
  }
  update(game) {
    const r = this.menu.update(game.input);
    if (!r) return;
    if (r.type === 'cancel') {
      if (this.step === 0) game.pop();
      else { this.step = 0; this.menu = this.diffMenu(); this.menu.setIndex(DIFFS.findIndex((d) => d.value === this.diff), true); }
      return;
    }
    if (r.type !== 'select') return;
    if (this.step === 0) {
      this.diff = r.item.value;
      this.step = 1;
      this.menu = this.modeMenu();
    } else {
      const mode = r.item.value;
      audio.stopMusic(1.2);
      newGame(game, this.diff, mode);
    }
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.6;
    fill(ctx, 0, 0, W, H, '#05040a');
    ctx.globalAlpha = 1;
    drawWindow(ctx, 16, 10, W - 32, 22, 'gold');
    drawText(ctx, this.step === 0 ? '新游戏 —— 第 1 步：难度' : '新游戏 —— 第 2 步：模式', W / 2, 15, '#fff4d8', { align: 'center', shadow: '#2a1804' });
    this.menu.draw(ctx, game.frame);
    const it = this.menu.current();
    drawWindow(ctx, 136, 40, 168, 104, 'dark');
    drawText(ctx, it.label, 146, 47, '#f8d878', { shadow: '#000' });
    wrapText(it.desc, 150).forEach((l, i) => drawText(ctx, l, 146, 65 + i * 14, '#e8e0d0', { shadow: '#000' }));
    const note = this.step === 0 ? '游戏中可在设置里修改难度，下一章起生效。' : `已选择难度：${DIFFS.find((d) => d.value === this.diff).label}　X 返回上一步`;
    drawWindow(ctx, 16, 150, W - 32, 22, 'dark');
    drawText(ctx, note, W / 2, 155, '#c8c0b0', { align: 'center', shadow: '#000' });
  }
}
