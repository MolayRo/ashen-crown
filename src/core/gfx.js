// 基础绘图：像素边框窗口、血条、精灵表
import { drawText, textWidth } from './font.js';

export function fill(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

export function frameRect(ctx, x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, w, 1);
  ctx.fillRect(x, y + h - 1, w, 1);
  ctx.fillRect(x, y, 1, h);
  ctx.fillRect(x + w - 1, y, 1, h);
}

function lerpColor(a, b, t) {
  const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
  const r = Math.round(((pa >> 16) & 255) + (((pb >> 16) & 255) - ((pa >> 16) & 255)) * t);
  const g = Math.round(((pa >> 8) & 255) + (((pb >> 8) & 255) - ((pa >> 8) & 255)) * t);
  const bl = Math.round((pa & 255) + ((pb & 255) - (pa & 255)) * t);
  return '#' + ((1 << 24) | (r << 16) | (g << 8) | bl).toString(16).slice(1);
}
export { lerpColor };

// 窗口风格：外描边、边框亮色、边框暗色、填充上/下、内高光
export const WINDOW_STYLES = {
  menu:   { out: '#0b0a16', rim: '#e9d9a6', rim2: '#8a6d34', top: '#243a7a', bot: '#15214c', hi: '#3a58a8' },
  dark:   { out: '#070610', rim: '#9c8a5c', rim2: '#4a3c20', top: '#1b1a2c', bot: '#0f0e1a', hi: '#2c2a44' },
  dialog: { out: '#1c1008', rim: '#fff4d6', rim2: '#9a7440', top: '#f7ecd0', bot: '#e8d4a4', hi: '#fffaea' },
  red:    { out: '#12060a', rim: '#f0c8a0', rim2: '#7a3020', top: '#7a2228', bot: '#461218', hi: '#9a3a38' },
  blue:   { out: '#060a16', rim: '#c8dcff', rim2: '#3a5890', top: '#2a4c98', bot: '#172a5c', hi: '#4468b8' },
  green:  { out: '#06120a', rim: '#d0f0b8', rim2: '#3a6a30', top: '#2c6a3a', bot: '#173e22', hi: '#3e8a4c' },
  gold:   { out: '#140c02', rim: '#fff0b0', rim2: '#9a6a18', top: '#6a4a14', bot: '#3a280a', hi: '#8a6420' },
};

export function drawWindow(ctx, x, y, w, h, style = 'menu', alpha = 1) {
  const s = typeof style === 'string' ? WINDOW_STYLES[style] || WINDOW_STYLES.menu : style;
  x = Math.round(x); y = Math.round(y); w = Math.round(w); h = Math.round(h);
  if (w < 6 || h < 6) return;
  const prevA = ctx.globalAlpha;
  ctx.globalAlpha = alpha;
  // 填充：分段渐变（保持像素色带感）
  const bands = Math.max(2, Math.min(8, Math.floor(h / 6)));
  const ih = h - 6;
  for (let i = 0; i < bands; i++) {
    const y0 = y + 3 + Math.floor((ih * i) / bands);
    const y1 = y + 3 + Math.floor((ih * (i + 1)) / bands);
    ctx.fillStyle = lerpColor(s.top, s.bot, i / (bands - 1));
    ctx.fillRect(x + 3, y0, w - 6, y1 - y0);
  }
  ctx.fillStyle = s.hi;
  ctx.fillRect(x + 3, y + 3, w - 6, 1);
  ctx.globalAlpha = prevA;
  // 边框（圆角：跳过角点）
  ctx.fillStyle = s.out;
  ctx.fillRect(x + 2, y, w - 4, 1);
  ctx.fillRect(x + 2, y + h - 1, w - 4, 1);
  ctx.fillRect(x, y + 2, 1, h - 4);
  ctx.fillRect(x + w - 1, y + 2, 1, h - 4);
  ctx.fillRect(x + 1, y + 1, 1, 1);
  ctx.fillRect(x + w - 2, y + 1, 1, 1);
  ctx.fillRect(x + 1, y + h - 2, 1, 1);
  ctx.fillRect(x + w - 2, y + h - 2, 1, 1);
  ctx.fillStyle = s.rim;
  ctx.fillRect(x + 2, y + 1, w - 4, 1);
  ctx.fillRect(x + 1, y + 2, 1, h - 4);
  ctx.fillStyle = s.rim2;
  ctx.fillRect(x + 2, y + h - 2, w - 4, 1);
  ctx.fillRect(x + w - 2, y + 2, 1, h - 4);
  // 内圈暗线
  ctx.fillStyle = s.out;
  ctx.globalAlpha = 0.55 * alpha;
  ctx.fillRect(x + 2, y + 2, w - 4, 1);
  ctx.fillRect(x + 2, y + 2, 1, h - 4);
  ctx.globalAlpha = prevA;
}

// 标题条（窗口顶部的小标签）
export function drawTab(ctx, x, y, label, style = 'gold') {
  const w = textWidth(label) + 12;
  drawWindow(ctx, x, y, w, 16, style);
  drawText(ctx, label, x + 6, y + 2, '#fff6d8', { shadow: '#1a1004' });
  return w;
}

// 血条 / 经验条
export function drawBar(ctx, x, y, w, h, frac, fg = '#78d060', bg = '#20242e', edge = '#0b0a16') {
  fill(ctx, x - 1, y - 1, w + 2, h + 2, edge);
  fill(ctx, x, y, w, h, bg);
  const fw = Math.max(0, Math.min(w, Math.round(w * frac)));
  if (fw > 0) {
    fill(ctx, x, y, fw, h, fg);
    ctx.globalAlpha = 0.35;
    fill(ctx, x, y, fw, 1, '#ffffff');
    ctx.globalAlpha = 1;
  }
}

// FE 式分段血条：每格代表 1 HP，两行显示
export function drawHpTicks(ctx, x, y, hp, maxHp, perRow = 40) {
  const rows = maxHp > perRow ? 2 : 1;
  for (let r = 0; r < rows; r++) {
    const start = r * perRow;
    const count = Math.min(perRow, maxHp - start);
    for (let i = 0; i < count; i++) {
      const filled = start + i < hp;
      const px = x + i * 2;
      const py = y + r * 5;
      fill(ctx, px, py, 1, 4, filled ? '#f8f0c8' : '#3a3448');
      if (filled) fill(ctx, px, py + 3, 1, 1, '#c8a860');
    }
  }
}

// 精灵表：frames 为 {名字: [x, y, w, h, 锚点x, 锚点y]}
export class Sheet {
  constructor(img, meta) {
    this.img = img;
    this.meta = meta || {};
    this.frames = (meta && meta.frames) || {};
  }
  has(name) { return !!this.frames[name]; }
  draw(ctx, name, x, y, flip = false, alpha = 1) {
    const f = this.frames[name];
    if (!f) return false;
    const [sx, sy, w, h, ax = 0, ay = 0] = f;
    const prev = ctx.globalAlpha;
    if (alpha !== 1) ctx.globalAlpha = prev * alpha;
    if (flip) {
      ctx.save();
      ctx.translate(Math.round(x), Math.round(y));
      ctx.scale(-1, 1);
      ctx.drawImage(this.img, sx, sy, w, h, -(w - ax), -ay, w, h);
      ctx.restore();
    } else {
      ctx.drawImage(this.img, sx, sy, w, h, Math.round(x) - ax, Math.round(y) - ay, w, h);
    }
    if (alpha !== 1) ctx.globalAlpha = prev;
    return true;
  }
  // 以纯色剪影绘制（受击闪白、暗化等）
  drawTinted(ctx, name, x, y, flip, color, alpha = 1) {
    const f = this.frames[name];
    if (!f) return false;
    const sil = silhouette(this.img, color, this.img.src + '#sheet');
    const [sx, sy, w, h, ax = 0, ay = 0] = f;
    const prev = ctx.globalAlpha;
    ctx.globalAlpha = prev * alpha;
    if (flip) {
      ctx.save();
      ctx.translate(Math.round(x), Math.round(y));
      ctx.scale(-1, 1);
      ctx.drawImage(sil, sx, sy, w, h, -(w - ax), -ay, w, h);
      ctx.restore();
    } else {
      ctx.drawImage(sil, sx, sy, w, h, Math.round(x) - ax, Math.round(y) - ay, w, h);
    }
    ctx.globalAlpha = prev;
    return true;
  }
  // 灰度绘制
  drawGrey(ctx, name, x, y, flip) {
    const f = this.frames[name];
    if (!f) return false;
    const g = greyscale(this.img, this.img.src + '#grey');
    const [sx, sy, w, h, ax = 0, ay = 0] = f;
    if (flip) {
      ctx.save();
      ctx.translate(Math.round(x), Math.round(y));
      ctx.scale(-1, 1);
      ctx.drawImage(g, sx, sy, w, h, -(w - ax), -ay, w, h);
      ctx.restore();
    } else ctx.drawImage(g, sx, sy, w, h, Math.round(x) - ax, Math.round(y) - ay, w, h);
    return true;
  }
}

// 把图片处理成纯色剪影（受击闪白等），带缓存
const silCache = new Map();
export function silhouette(img, color, key) {
  const k = (key || img.src || '') + '|' + color;
  let c = silCache.get(k);
  if (!c) {
    c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height;
    const g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    g.globalCompositeOperation = 'source-in';
    g.fillStyle = color;
    g.fillRect(0, 0, c.width, c.height);
    silCache.set(k, c);
  }
  return c;
}

// 灰度化（已行动单位）
const greyCache = new Map();
export function greyscale(img, key) {
  const k = key || img.src;
  let c = greyCache.get(k);
  if (!c) {
    c = document.createElement('canvas');
    c.width = img.width;
    c.height = img.height;
    const g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height);
    const a = d.data;
    for (let i = 0; i < a.length; i += 4) {
      const l = a[i] * 0.3 + a[i + 1] * 0.55 + a[i + 2] * 0.15;
      const v = Math.round(l * 0.72 + 30);
      a[i] = v; a[i + 1] = v; a[i + 2] = Math.min(255, v + 8);
    }
    g.putImageData(d, 0, 0);
    greyCache.set(k, c);
  }
  return c;
}

// 带箭头的小三角（菜单翻页提示等）
export function drawArrow(ctx, x, y, dir, color = '#f8e8b0') {
  ctx.fillStyle = color;
  for (let i = 0; i < 4; i++) {
    if (dir === 'down') ctx.fillRect(x - 3 + i, y + i, 7 - i * 2, 1);
    else if (dir === 'up') ctx.fillRect(x - 3 + i, y + 3 - i, 7 - i * 2, 1);
    else if (dir === 'right') ctx.fillRect(x + i, y - 3 + i, 1, 7 - i * 2);
    else ctx.fillRect(x + 3 - i, y - 3 + i, 1, 7 - i * 2);
  }
}

// 菜单手形光标（像素绘制，随时间轻微晃动）
export function drawPointer(ctx, x, y, t = 0) {
  const off = Math.round(Math.sin(t * 0.18) * 1.5);
  x += off;
  const O = '#1a1206', W1 = '#fff8e0', G = '#e0b848', S = '#9a7020';
  const rows = [
    '..OOOO....',
    '.OWWWWOOO.',
    'OWWWWWWWWO',
    'OWWWWWGGGO',
    'OWGWWWOOO.',
    '.OSSSSO...',
    '..OOOO....',
  ];
  for (let r = 0; r < rows.length; r++) {
    for (let c = 0; c < rows[r].length; c++) {
      const ch = rows[r][c];
      if (ch === '.') continue;
      ctx.fillStyle = ch === 'O' ? O : ch === 'W' ? W1 : ch === 'G' ? G : S;
      ctx.fillRect(x - 10 + c, y - 3 + r, 1, 1);
    }
  }
}
