// 标题画面
import { W, H } from '../core/renderer.js';
import { fill, drawWindow } from '../core/gfx.js';
import { drawText, drawTextScaled } from '../core/font.js';
import { images } from '../core/assets.js';
import { audio } from '../core/audio.js';
import { ListMenu } from '../ui/menu.js';
import { hasAnySave, latestSave, readSave, hasCleared } from '../game/saves.js';
import { loadFromSave } from './flowctl.js';
import { ConfirmDialog } from './confirm.js';
import { NewGameScene } from './newgame.js';
import { SettingsScene } from './settings.js';
import { HelpScene } from './help.js';
import { CreditsScene } from './credits.js';
import { SaveLoadScene } from './saveload.js';

export class TitleScene {
  constructor() {
    this.t = 0;
    this.pressed = false;
    this.embers = [];
    for (let i = 0; i < 40; i++) this.embers.push(this.newEmber(true));
  }

  newEmber(init = false) {
    return { x: Math.random() * W, y: init ? Math.random() * H : H + 4, vy: 0.15 + Math.random() * 0.45, vx: (Math.random() - 0.5) * 0.2, life: 0, c: Math.random() < 0.3 ? '#ffe070' : Math.random() < 0.6 ? '#f08020' : '#c84010', ph: Math.random() * 6 };
  }

  enter(game) {
    this.game = game;
    game.campaign = null;
    if (audio.ready) this.pressed = true;
    audio.playMusic('title', { fade: 1.5 });
    this.buildMenu();
  }

  resume() { this.buildMenu(this.menu ? this.menu.index : 0); }

  buildMenu(index = 0) {
    const has = hasAnySave();
    this.menu = new ListMenu([
      { label: '开始游戏', value: 'new' },
      { label: '继续游戏', value: 'continue', enabled: has, reason: '还没有任何存档' },
      { label: '读取存档', value: 'load', enabled: has, reason: '还没有任何存档' },
      { label: '设置', value: 'settings' },
      { label: '操作说明', value: 'help' },
      { label: '制作人员与素材', value: 'credits' },
      { label: '退出游戏', value: 'quit' },
    ], { x: W / 2 - 60, y: 80, w: 120, align: 'center', rowH: 13, padY: 3, visible: 7, style: 'dark', cancelable: false });
    this.menu.index = index;
  }

  update(game) {
    this.t++;
    for (const e of this.embers) {
      e.y -= e.vy; e.x += e.vx + Math.sin((this.t + e.ph * 40) / 40) * 0.12; e.life++;
      if (e.y < -4) Object.assign(e, this.newEmber());
    }
    const input = game.input;
    if (!this.pressed) {
      if (input.anyKey || input.click() || input.confirm()) {
        this.pressed = true;
        audio.unlock();
        audio.playMusic('title', { fade: 1.5 });
        audio.sfx('confirm');
        input.consumeAll();
      }
      return;
    }
    const r = this.menu.update(input);
    if (!r) return;
    if (r.type === 'blocked') { game.showToast(r.item.reason); return; }
    if (r.type !== 'select') return;
    switch (r.item.value) {
      case 'new': game.push(new NewGameScene()); break;
      case 'continue': {
        const s = latestSave();
        if (s) loadFromSave(game, s.data);
        break;
      }
      case 'load': game.push(new SaveLoadScene('load')); break;
      case 'settings': game.push(new SettingsScene()); break;
      case 'help': game.push(new HelpScene()); break;
      case 'credits': game.push(new CreditsScene()); break;
      case 'quit':
        game.push(new ConfirmDialog('退出游戏？', (yes) => {
          if (!yes) return;
          audio.stopMusic(0.5);
          try { window.close(); } catch (e) { /* 浏览器可能不允许 */ }
          game.push(new QuitScene());
        }));
        break;
      default: break;
    }
  }

  draw(ctx, game) {
    const bg = images.title_bg;
    if (bg) ctx.drawImage(bg, 0, 0); else fill(ctx, 0, 0, W, H, '#0b0812');
    for (const e of this.embers) {
      const a = Math.max(0, Math.min(1, (e.y / H) * 1.4));
      ctx.globalAlpha = a * (0.6 + 0.4 * Math.sin(this.t / 7 + e.ph));
      fill(ctx, Math.round(e.x), Math.round(e.y), 1, 1, e.c);
    }
    ctx.globalAlpha = 1;
    const logo = images.logo;
    const ly = 8 + Math.round(Math.sin(this.t / 50) * 1);
    if (logo) ctx.drawImage(logo, Math.round((W - logo.width) / 2), ly);
    else {
      drawTextScaled(ctx, '灰烬王冠', W / 2, 18, '#f8d070', 3, { align: 'center', outline: '#2a1004' });
      drawText(ctx, 'THE ASHEN CROWN', W / 2, 58, '#c8a060', { align: 'center', shadow: '#000' });
    }
    if (!this.pressed) {
      if (Math.floor(this.t / 30) % 2 === 0) drawText(ctx, '按任意键开始', W / 2, 128, '#fff4d8', { align: 'center', shadow: '#2a1004' });
    } else {
      this.menu.draw(ctx, this.t);
      const it = this.menu.current();
      if (it && it.enabled === false) drawText(ctx, it.reason, W / 2, 176 - 12, '#c8b0a0', { align: 'center', shadow: '#000' });
    }
    ctx.globalAlpha = 0.55;
    drawText(ctx, hasCleared() ? '★ 已通关' : 'v1.0', 4, H - 13, '#c8b890', { shadow: '#000' });
    drawText(ctx, '© 2026 原创作品', W - 4, H - 13, '#c8b890', { align: 'right', shadow: '#000' });
    ctx.globalAlpha = 1;
  }
}

export class QuitScene {
  update(game) {
    if (game.input.anyKey || game.input.click()) { game.pop(); game.input.consumeAll(); }
  }
  draw(ctx) {
    fill(ctx, 0, 0, W, H, '#050408');
    drawText(ctx, '感谢游玩《灰烬王冠》。', W / 2, 70, '#f0d8a0', { align: 'center' });
    drawText(ctx, '浏览器不允许网页自行关闭时，直接关闭此标签页即可。', W / 2, 92, '#b8b0a0', { align: 'center' });
    drawText(ctx, '按任意键返回标题画面', W / 2, 120, '#8a8478', { align: 'center' });
  }
}
