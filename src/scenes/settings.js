// 设置：音量、亮度、显示、CRT、文字与演出速度、难度（即时预览，自动保存）
import { W, H } from '../core/renderer.js';
import { fill, drawWindow, drawPointer, drawArrow } from '../core/gfx.js';
import { drawText, wrapText } from '../core/font.js';
import { settings, setSetting, resetSettings, DEFAULTS } from '../core/settings.js';
import { audio } from '../core/audio.js';
import { DIFFICULTY_NAMES } from '../game/campaign.js';
import { ConfirmDialog } from './confirm.js';

function slider(key, label, min, max, step, desc, fmt = (v) => v + '%') {
  return { key, label, type: 'slider', min, max, step, desc, fmt };
}
function choice(key, label, options, desc) {
  return { key, label, type: 'choice', options, desc };
}

export class SettingsScene {
  constructor() {
    this.overlay = true;
    this.index = 0;
    this.scroll = 0;
    this.visible = 8;
    this.dragging = null;
  }

  enter(game) {
    this.game = game;
    const inGame = !!game.campaign;
    this.rows = [
      slider('masterVol', '总音量', 0, 100, 10, '所有声音的总音量。'),
      slider('musicVol', '音乐音量', 0, 100, 10, '背景音乐的音量。'),
      slider('sfxVol', '音效音量', 0, 100, 10, '菜单、战斗等音效的音量。调整时会播放试听音效。'),
      slider('brightness', '画面亮度', 60, 140, 5, '整体画面亮度，即时生效。'),
      { key: '_fullscreen', label: '显示模式', type: 'fullscreen', desc: '切换窗口 / 全屏（也可以按 F11）。' },
      choice('pixelPerfect', '整数缩放', [[true, '开'], [false, '关']], '关闭 CRT 时按整数倍放大像素，画面最锐利；关闭则铺满窗口。'),
      choice('crt', 'CRT 滤镜', [[true, '开'], [false, '关']], '模拟显像管电视：扫描线、屏幕曲率、暗角、色偏与荧光。关闭后恢复清晰像素画面。'),
      slider('crtStrength', 'CRT 强度', 0, 100, 5, '扫描线深浅、屏幕弯曲程度与暗角强度。'),
      slider('crtGlow', '荧光与色偏', 0, 100, 5, '荧光粉辉光与 RGB 色彩偏移的强度。'),
      choice('textSpeed', '文字速度', [[0, '慢'], [1, '中'], [2, '快'], [3, '瞬间']], '剧情对白逐字显示的速度。按住 Shift 可随时快进。'),
      choice('battleAnim', '战斗演出', [[1, '完整'], [0, '简略']], '完整：切换到侧视战斗动画。简略：直接在地图上表现攻击。战斗中按 Shift 加速，按 X/Esc 跳过。'),
      choice('gameSpeed', '游戏速度', [[0, '普通'], [1, '快速'], [2, '极速']], '地图移动、敌方行动与战斗动画的速度。'),
      choice('confirmEnd', '结束回合确认', [[true, '开'], [false, '关']], '还有单位未行动时结束回合，是否弹出确认。'),
      { key: '_difficulty', label: '难度', type: 'difficulty', desc: inGame ? '修改后从下一章开始生效（当前章节不受影响）。' : '难度在“开始游戏”时选择。' },
      { key: '_reset', label: '恢复默认设置', type: 'action', desc: '把所有设置恢复为默认值。' },
      { key: '_back', label: '返回', type: 'action', desc: '设置会自动保存，重新打开游戏后依然有效。' },
    ];
  }

  valueText(r) {
    if (r.type === 'slider') return r.fmt(settings[r.key]);
    if (r.type === 'choice') { const o = r.options.find((x) => x[0] === settings[r.key]); return o ? o[1] : '?'; }
    if (r.type === 'fullscreen') return document.fullscreenElement ? '全屏' : '窗口';
    if (r.type === 'difficulty') {
      const c = this.game.campaign;
      if (!c) return '—';
      const cur = DIFFICULTY_NAMES[c.difficulty];
      if (c.pendingDifficulty && c.pendingDifficulty !== c.difficulty) return `${cur} → ${DIFFICULTY_NAMES[c.pendingDifficulty]}`;
      return cur;
    }
    return '';
  }

  adjust(r, dir) {
    if (r.type === 'slider') {
      const v = Math.max(r.min, Math.min(r.max, settings[r.key] + dir * r.step));
      if (v !== settings[r.key]) {
        setSetting(r.key, v);
        this.after(r);
      }
    } else if (r.type === 'choice') {
      const i = r.options.findIndex((o) => o[0] === settings[r.key]);
      const n = r.options.length;
      const ni = (i + dir + n) % n;
      setSetting(r.key, r.options[ni][0]);
      this.after(r);
    } else if (r.type === 'fullscreen') {
      toggleFullscreen();
      audio.sfx('confirm');
    } else if (r.type === 'difficulty') {
      const c = this.game.campaign;
      if (!c) { audio.sfx('error'); return; }
      const order = ['easy', 'normal', 'hard'];
      const cur = c.pendingDifficulty || c.difficulty;
      const ni = (order.indexOf(cur) + dir + 3) % 3;
      c.pendingDifficulty = order[ni] === c.difficulty ? null : order[ni];
      audio.sfx('cursor');
    }
  }

  after(r) {
    if (r.key.endsWith('Vol')) { audio.applyVolumes(); audio.sfx(r.key === 'musicVol' ? 'cursor' : 'confirm'); }
    else audio.sfx('cursor');
  }

  activate(r) {
    if (r.key === '_back') { audio.sfx('cancel'); this.game.pop(); return; }
    if (r.key === '_reset') {
      this.game.push(new ConfirmDialog('恢复全部默认设置？', (yes) => { if (yes) { resetSettings(); audio.applyVolumes(); } }));
      return;
    }
    this.adjust(r, 1);
  }

  rowRect(i) {
    const r = i - this.scroll;
    return { x: 20, y: 30 + r * 13, w: W - 40, h: 13 };
  }

  update(game) {
    const input = game.input;
    const n = this.rows.length;
    if (input.repeat('up')) { this.index = (this.index - 1 + n) % n; audio.sfx('cursor'); }
    if (input.repeat('down')) { this.index = (this.index + 1) % n; audio.sfx('cursor'); }
    if (input.mouse.wheel) { this.scroll = Math.max(0, Math.min(n - this.visible, this.scroll + Math.sign(input.mouse.wheel))); }
    const r = this.rows[this.index];
    if (input.repeat('left')) this.adjust(r, -1);
    if (input.repeat('right')) this.adjust(r, 1);
    // 鼠标
    const m = input.mouse;
    let hover = -1;
    for (let i = this.scroll; i < Math.min(n, this.scroll + this.visible); i++) {
      const rr = this.rowRect(i);
      if (m.x >= rr.x && m.x < rr.x + rr.w && m.y >= rr.y && m.y < rr.y + rr.h) hover = i;
    }
    if (hover >= 0 && m.moved && hover !== this.index) this.index = hover;
    if (m.left && this.dragging == null && hover >= 0 && this.rows[hover].type === 'slider' && m.x >= 150) this.dragging = hover;
    if (!m.left) this.dragging = null;
    if (this.dragging != null) {
      const row = this.rows[this.dragging];
      const frac = Math.max(0, Math.min(1, (m.x - 172) / 100));
      const v = Math.round((row.min + frac * (row.max - row.min)) / row.step) * row.step;
      if (v !== settings[row.key]) { setSetting(row.key, v); if (row.key.endsWith('Vol')) audio.applyVolumes(); }
    }
    if (input.click() && hover >= 0) {
      const row = this.rows[hover];
      if (row.type === 'action') this.activate(row);
      else if (row.type !== 'slider') this.adjust(row, m.x < 222 ? -1 : 1);
    }
    if (input.confirm()) this.activate(r);
    if (input.cancel()) { audio.sfx('cancel'); game.pop(); return; }
    if (this.index < this.scroll) this.scroll = this.index;
    if (this.index >= this.scroll + this.visible) this.scroll = this.index - this.visible + 1;
  }

  draw(ctx, game) {
    ctx.globalAlpha = 0.7;
    fill(ctx, 0, 0, W, H, '#05040a');
    ctx.globalAlpha = 1;
    drawWindow(ctx, 12, 6, W - 24, 150, 'menu');
    drawText(ctx, '设置', 24, 12, '#f8e0a0', { shadow: '#000' });
    drawText(ctx, '←→ 调整　Enter 切换　Esc 返回', W - 24, 12, '#b8c0e0', { align: 'right', shadow: '#000' });
    for (let i = this.scroll; i < Math.min(this.rows.length, this.scroll + this.visible); i++) {
      const r = this.rows[i];
      const rr = this.rowRect(i);
      const sel = i === this.index;
      if (sel) { ctx.globalAlpha = 0.25; fill(ctx, rr.x, rr.y, rr.w, rr.h, '#fff2c0'); ctx.globalAlpha = 1; drawPointer(ctx, rr.x + 10, rr.y + 6, game.frame); }
      drawText(ctx, r.label, rr.x + 16, rr.y + 1, '#ffffff', { shadow: '#0b0a16' });
      if (r.type === 'slider') {
        const v = settings[r.key];
        const frac = (v - r.min) / (r.max - r.min);
        fill(ctx, 172, rr.y + 5, 100, 3, '#0b0a16');
        fill(ctx, 172, rr.y + 5, Math.round(100 * frac), 3, '#f0c860');
        fill(ctx, 170 + Math.round(100 * frac), rr.y + 2, 4, 9, '#fff8e0');
        drawText(ctx, this.valueText(r), rr.x + rr.w - 6, rr.y + 1, '#f8e8b0', { align: 'right', shadow: '#000' });
      } else if (r.type !== 'action') {
        const t = this.valueText(r);
        drawArrow(ctx, 178, rr.y + 6, 'left', sel ? '#f8e8b0' : '#8a88a0');
        drawText(ctx, t, 222, rr.y + 1, '#f8e8b0', { align: 'center', shadow: '#000' });
        drawArrow(ctx, 264, rr.y + 6, 'right', sel ? '#f8e8b0' : '#8a88a0');
      }
    }
    if (this.scroll > 0) drawArrow(ctx, W / 2, 26, 'up');
    if (this.scroll + this.visible < this.rows.length) drawArrow(ctx, W / 2, 148, 'down');
    const r = this.rows[this.index];
    drawWindow(ctx, 12, 146, W - 24, 32, 'dark');
    wrapText(r.desc, W - 48).slice(0, 2).forEach((l, i) => drawText(ctx, l, 22, 150 + i * 13, '#e8e0c8', { shadow: '#000' }));
  }
}

export function toggleFullscreen() {
  try {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  } catch (e) { /* 忽略 */ }
}

export { DEFAULTS };
