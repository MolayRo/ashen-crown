// 点阵字体：从烘焙好的图集逐字贴图，保证像素锐利。
// 文本支持简单着色标记：{y}黄色{/}、{r}红{/}、{b}蓝{/}、{g}绿{/}、{w}白{/}、{k}灰{/}
import { GLYPHS, FONT_ASCENT, FONT_LINE } from './fontdata.js';

export const LINE = FONT_LINE;
let atlas = null;
const tinted = new Map();

export const MARK_COLORS = {
  y: '#f8d860', r: '#ff7a68', b: '#8cc4ff', g: '#98e080', w: '#ffffff', k: '#9a98a8', o: '#ffb050', p: '#d8a8ff',
};

export function initFont(img) {
  atlas = img;
  tinted.clear();
}

function tintedAtlas(color) {
  let c = tinted.get(color);
  if (!c) {
    c = document.createElement('canvas');
    c.width = atlas.width;
    c.height = atlas.height;
    const g = c.getContext('2d');
    g.drawImage(atlas, 0, 0);
    g.globalCompositeOperation = 'source-in';
    g.fillStyle = color;
    g.fillRect(0, 0, c.width, c.height);
    tinted.set(color, c);
  }
  return c;
}

export function hasGlyph(ch) { return !!GLYPHS[ch]; }
export function charWidth(ch) {
  const g = GLYPHS[ch];
  return g ? g[6] : 12;
}

// 解析标记，返回 [{text, mark}] 片段
export function parseMarks(str) {
  const out = [];
  let mark = null;
  let buf = '';
  for (let i = 0; i < str.length; i++) {
    const ch = str[i];
    if (ch === '{') {
      const end = str.indexOf('}', i);
      if (end > i && end - i <= 3) {
        const tag = str.slice(i + 1, end);
        if (tag === '/' || MARK_COLORS[tag]) {
          if (buf) out.push({ text: buf, mark });
          buf = '';
          mark = tag === '/' ? null : tag;
          i = end;
          continue;
        }
      }
    }
    buf += ch;
  }
  if (buf) out.push({ text: buf, mark });
  return out;
}

export function stripMarks(str) {
  return parseMarks(str).map((p) => p.text).join('');
}

export function textWidth(str) {
  let w = 0;
  for (const ch of stripMarks(str)) w += charWidth(ch);
  return w;
}

function drawRaw(ctx, str, x, y, color) {
  const src = tintedAtlas(color);
  let px = Math.round(x);
  const base = Math.round(y) + FONT_ASCENT;
  for (const ch of str) {
    const g = GLYPHS[ch];
    if (!g) { px += 12; continue; }
    const w = g[2], h = g[3];
    if (w > 0 && h > 0) ctx.drawImage(src, g[0], g[1], w, h, px + g[4], base - g[5] - h, w, h);
    px += g[6];
  }
  return px;
}

// y 为行框顶部（CJK 字形 11px 高，顶在 y）。返回绘制后的 x。
// opts: {shadow: color, align: 'left'|'center'|'right', limit: 字符数（打字机效果）}
export function drawText(ctx, str, x, y, color = '#ffffff', opts = null) {
  if (str == null) return x;
  str = String(str);
  const shadow = opts && opts.shadow;
  const align = opts && opts.align;
  let limit = opts && opts.limit != null ? opts.limit : Infinity;
  if (align === 'center') x = Math.round(x - textWidth(str) / 2);
  else if (align === 'right') x = Math.round(x - textWidth(str));
  const parts = str.indexOf('{') >= 0 ? parseMarks(str) : [{ text: str, mark: null }];
  let px = x;
  for (const p of parts) {
    if (limit <= 0) break;
    let t = p.text;
    if ([...t].length > limit) t = [...t].slice(0, limit).join('');
    limit -= [...t].length;
    const col = p.mark ? MARK_COLORS[p.mark] : color;
    if (shadow) drawRaw(ctx, t, px + 1, y + 1, shadow);
    px = drawRaw(ctx, t, px, y, col);
  }
  return px;
}

// 描边文字（标题、伤害数字等）
export function drawTextOutlined(ctx, str, x, y, color, outline, opts = null) {
  const align = opts && opts.align;
  if (align === 'center') x = Math.round(x - textWidth(str) / 2);
  else if (align === 'right') x = Math.round(x - textWidth(str));
  const plain = stripMarks(String(str));
  for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [1, -1], [-1, 1], [1, 1]]) drawRaw(ctx, plain, x + dx, y + dy, outline);
  return drawText(ctx, str, x, y, color);
}

// 按像素宽度折行（中文逐字断行，英文单词尽量不拆），遵守行首禁则
const NO_START = '，。、：；！？）」』】》〉…—～·.,:;!?)]”’%';
const NO_END = '（「『【《〈“‘([';
export function wrapText(str, maxW) {
  const lines = [];
  for (const para of String(str).split('\n')) {
    const parts = parseMarks(para);
    // 展开成 {ch, mark}
    const chars = [];
    for (const p of parts) for (const ch of p.text) chars.push({ ch, mark: p.mark });
    let line = [];
    let w = 0;
    let i = 0;
    while (i < chars.length) {
      const c = chars[i];
      let cw = charWidth(c.ch);
      // 英文单词整体处理
      let j = i;
      if (/[A-Za-z0-9]/.test(c.ch)) {
        while (j + 1 < chars.length && /[A-Za-z0-9'\-]/.test(chars[j + 1].ch)) { j++; cw += charWidth(chars[j].ch); }
      }
      if (w + cw > maxW && line.length) {
        // 行首禁则：下一个字符不能出现在行首时，把当前行最后一个字挪下去
        if (NO_START.includes(c.ch) && line.length > 1) {
          const last = line.pop();
          lines.push(line);
          line = [last];
          w = charWidth(last.ch);
        } else {
          // 行尾禁则
          if (line.length > 1 && NO_END.includes(line[line.length - 1].ch)) {
            const last = line.pop();
            lines.push(line);
            line = [last];
            w = charWidth(last.ch);
          } else {
            lines.push(line);
            line = [];
            w = 0;
          }
        }
        if (c.ch === ' ') { i++; continue; }
      }
      for (let k = i; k <= j; k++) line.push(chars[k]);
      w += cw;
      i = j + 1;
    }
    lines.push(line);
  }
  // 还原为带标记的字符串
  return lines.map((ln) => {
    let s = '';
    let mark = null;
    for (const c of ln) {
      if (c.mark !== mark) {
        if (mark) s += '{/}';
        if (c.mark) s += '{' + c.mark + '}';
        mark = c.mark;
      }
      s += c.ch;
    }
    if (mark) s += '{/}';
    return s;
  });
}

// 放大绘制（章节标题、回合横幅等）：先画到离屏画布再整数倍放大，保持像素锐利
const bigCache = new Map();
export function drawTextScaled(ctx, str, x, y, color, scale = 2, opts = {}) {
  const k = str + '|' + color + '|' + (opts.outline || '') + '|' + (opts.shadow || '');
  let c = bigCache.get(k);
  if (!c) {
    const w = textWidth(str) + 4;
    c = document.createElement('canvas');
    c.width = w;
    c.height = 16;
    const g = c.getContext('2d');
    if (opts.outline) drawTextOutlined(g, str, 2, 2, color, opts.outline);
    else drawText(g, str, 2, 2, color, opts.shadow ? { shadow: opts.shadow } : null);
    if (bigCache.size > 200) bigCache.clear();
    bigCache.set(k, c);
  }
  let dx = x;
  if (opts.align === 'center') dx = Math.round(x - (c.width * scale) / 2);
  else if (opts.align === 'right') dx = Math.round(x - c.width * scale);
  const prev = ctx.imageSmoothingEnabled;
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(c, 0, 0, c.width, c.height, dx - 2 * scale, Math.round(y) - 2 * scale, c.width * scale, c.height * scale);
  ctx.imageSmoothingEnabled = prev;
  return c.width * scale;
}

export function visibleLength(str) {
  return [...stripMarks(str)].length;
}
