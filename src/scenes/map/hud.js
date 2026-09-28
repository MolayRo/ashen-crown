// 地图 HUD：单位信息、地形、目标、战斗预测、回合横幅、经验条、升级窗口
import { W, H } from '../../core/renderer.js';
import { fill, drawWindow, drawBar } from '../../core/gfx.js';
import { drawText, drawTextScaled, textWidth, wrapText } from '../../core/font.js';
import { sheets } from '../../core/assets.js';
import { ITEMS } from '../../game/data/items.js';
import { CLASSES, STAT_NAMES, ENEMY_CLASS_NAMES } from '../../game/data/classes.js';
import * as R from '../../game/rules.js';

export function className(u) {
  if (u.team === 'enemy' && ENEMY_CLASS_NAMES[u.cls]) return ENEMY_CLASS_NAMES[u.cls];
  return CLASSES[u.cls].name;
}

export function drawMini(ctx, id, x, y) {
  const sh = sheets.portraits;
  if (sh && sh.has(id + '_mini')) { sh.draw(ctx, id + '_mini', x, y); return; }
  fill(ctx, x, y, 32, 32, '#2a2838');
  drawText(ctx, '?', x + 16, y + 10, '#888', { align: 'center' });
}

export function drawIcon(ctx, name, x, y) {
  const sh = sheets.icons;
  if (sh && sh.has(name)) { sh.draw(ctx, name, x, y); return true; }
  fill(ctx, x + 3, y + 3, 10, 10, '#8a8aa0');
  return false;
}

export function itemIcon(id) { return (ITEMS[id] && ITEMS[id].icon) || 'vulnerary'; }

const TEAM_STYLE = { player: 'blue', enemy: 'red', ally: 'green', npc: 'green' };

// ---- 面板布局：在四个角里挑一个不遮挡关键格子（光标、目标、攻击者）的位置 ----
export function rectOverlap(a, b) {
  return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}
export function cornerRect(w, h, corner) {
  const x = corner[1] === 'l' ? 4 : W - w - 4;
  const y = corner[0] === 't' ? 4 : H - h - 4;
  return { x, y, w, h };
}
// order：按优先级排列的角（'tl' 'tr' 'bl' 'br'）；avoid：不能压住的矩形
export function placePanel(w, h, avoid, order) {
  for (const c of order) {
    const r = cornerRect(w, h, c);
    if (!avoid.some((a) => rectOverlap(r, a))) return r;
  }
  // 实在找不到：选压住面积最小的角
  let best = null;
  for (const c of order) {
    const r = cornerRect(w, h, c);
    let area = 0;
    for (const a of avoid) {
      const ix = Math.max(0, Math.min(r.x + r.w, a.x + a.w) - Math.max(r.x, a.x));
      const iy = Math.max(0, Math.min(r.y + r.h, a.y + a.h) - Math.max(r.y, a.y));
      area += ix * iy;
    }
    if (!best || area < best.area) best = { r, area };
  }
  return best.r;
}
// 与某个屏幕 x 相反的一侧优先
export function oppositeOrder(sx, preferTop = true) {
  const left = sx > W / 2;
  const v = preferTop ? ['t', 'b'] : ['b', 't'];
  const h1 = left ? 'l' : 'r', h2 = left ? 'r' : 'l';
  return [v[0] + h1, v[1] + h1, v[0] + h2, v[1] + h2];
}

export const UNIT_PANEL = { w: 118, h: 40 };
export const TERRAIN_PANEL = { w: 62, h: 36 };
export const FORECAST = { w: 128, h: 90 };

// 悬停单位的小窗（pos = {x, y}）
export function drawUnitPanel(ctx, u, pos) {
  const w = UNIT_PANEL.w, h = UNIT_PANEL.h;
  const { x, y } = pos;
  drawWindow(ctx, x, y, w, h, TEAM_STYLE[u.team] || 'menu', 0.96);
  drawMini(ctx, u.portrait || 'soldier', x + 4, y + 4);
  drawText(ctx, u.name, x + 40, y + 5, '#ffffff', { shadow: '#000' });
  drawText(ctx, `HP ${u.hp}/${u.mhp}`, x + 40, y + 20, '#f8f0d0', { shadow: '#000' });
  drawBar(ctx, x + 40, y + 34, 70, 2, u.hp / u.mhp, u.hp / u.mhp > 0.5 ? '#78d060' : u.hp / u.mhp > 0.25 ? '#e8c040' : '#e85040');
  if (u.boss) drawText(ctx, '首领', x + w - 6, y + 5, '#f8d040', { align: 'right', shadow: '#000' });
  else drawText(ctx, 'Lv' + u.lv, x + w - 6, y + 5, '#c8d8ff', { align: 'right', shadow: '#000' });
}

export function drawTerrainPanel(ctx, t, pos) {
  const w = TERRAIN_PANEL.w, h = TERRAIN_PANEL.h;
  const { x, y } = pos;
  drawWindow(ctx, x, y, w, h, 'dark', 0.94);
  drawText(ctx, t.name, x + w / 2, y + 4, '#f8e8b0', { align: 'center', shadow: '#000' });
  drawText(ctx, `防${t.def >= 0 ? '+' : ''}${t.def} 避${t.avo >= 0 ? '+' : ''}${t.avo}`, x + w / 2, y + 19, '#e0e0f0', { align: 'center', shadow: '#000' });
}

function objectiveLines(state) {
  const obj = state.ch.objective;
  const txt = obj.type === 'defend' ? `坚守 ${Math.max(0, obj.turns - state.turn + 1)} 回合` : shortObjective(obj);
  const phase = { player: '我方回合', enemy: '敌方回合', ally: '友军回合' }[state.phase] || '';
  return [txt, `${phase} · 第 ${state.turn} 回合`];
}
export function objectiveSize(state) {
  const [a, b] = objectiveLines(state);
  return { w: Math.max(textWidth(a), textWidth(b)) + 16, h: 34 };
}
export function drawObjectivePanel(ctx, state, pos) {
  const [txt, turn] = objectiveLines(state);
  const { w, h } = objectiveSize(state);
  const { x, y } = pos;
  drawWindow(ctx, x, y, w, h, 'dark', 0.92);
  drawText(ctx, txt, x + 8, y + 3, '#f8e0a0', { shadow: '#000' });
  drawText(ctx, turn, x + 8, y + 17, '#c8d0f0', { shadow: '#000' });
}

function shortObjective(obj) {
  switch (obj.type) {
    case 'boss': return '目标：击败首领';
    case 'escape': return '目标：护送玛莎撤离';
    case 'rout': return '目标：救出囚犯并全灭';
    case 'seize': return '目标：击败瓦尔德占领王座';
    default: return '目标';
  }
}

// 战斗预测窗口（紧凑版，pos = {x, y}）：左列我方、右列对手，中间是项目名
export function drawForecast(ctx, fc, pos) {
  const w = FORECAST.w, h = FORECAST.h;
  const { x, y } = pos;
  drawWindow(ctx, x, y, w, h, 'menu', 0.97);
  const A = fc.att, D = fc.def;
  const colA = x + 28, colD = x + w - 28, mid = x + w / 2;
  // 名字（超长时截成 4 个字）
  const nm = (s) => ([...s].length > 4 ? [...s].slice(0, 4).join('') : s);
  drawText(ctx, nm(A.unit.name), colA, y + 3, '#9cc8ff', { align: 'center', shadow: '#000' });
  drawText(ctx, nm(D.unit.name), colD, y + 3, '#ff9c8c', { align: 'center', shadow: '#000' });
  fill(ctx, x + 6, y + 16, w - 12, 1, 'rgba(255,240,200,0.25)');
  // 武器图标 + 克制箭头 + 特效标记
  const wA = A.weapon ? ITEMS[A.weapon] : null;
  const wD = D.shownWeapon ? ITEMS[D.shownWeapon] : null;
  if (wA) drawIcon(ctx, wA.icon, colA - 8, y + 18);
  if (wD && D.canCounter) drawIcon(ctx, wD.icon, colD - 8, y + 18);
  else drawText(ctx, '无反击', colD, y + 20, '#ffb080', { align: 'center', shadow: '#000' });
  drawTri(ctx, colA + 13, y + 26, A.tri);
  drawTri(ctx, colD + 13, y + 26, D.canCounter ? D.tri : 0);
  if (A.eff) drawText(ctx, '效', colA - 22, y + 20, '#80ff80', { shadow: '#000' });
  if (D.eff && D.canCounter) drawText(ctx, '效', colD - 22, y + 20, '#80ff80', { shadow: '#000' });
  const rows = [
    ['HP', A.hp, D.hp],
    ['伤害', A.dmg + (A.times > 1 ? '×2' : ''), D.canCounter ? D.dmg + (D.times > 1 ? '×2' : '') : '--'],
    ['命中', A.hit, D.canCounter ? D.hit : '--'],
    ['必杀', A.crit, D.canCounter ? D.crit : '--'],
  ];
  rows.forEach((r, i) => {
    const yy = y + 36 + i * 13;
    drawText(ctx, r[0], mid, yy, '#f8e0a0', { align: 'center', shadow: '#000' });
    drawText(ctx, String(r[1]), colA, yy, A.eff && i === 1 ? '#a0ff90' : '#ffffff', { align: 'center', shadow: '#000' });
    drawText(ctx, String(r[2]), colD, yy, D.canCounter || i === 0 ? '#ffffff' : '#8a8898', { align: 'center', shadow: '#000' });
  });
}

function drawTri(ctx, x, y, tri) {
  if (!tri) return;
  const c = tri > 0 ? '#60f060' : '#ff5040';
  for (let i = 0; i < 3; i++) {
    if (tri > 0) fill(ctx, x - i, y + i - 2, 1 + i * 2, 1, c);
    else fill(ctx, x - i, y - i + 2, 1 + i * 2, 1, c);
  }
}

// 回合横幅
export function drawPhaseBanner(ctx, text, sub, t, color) {
  // t: 0..70
  let off;
  if (t < 12) off = (12 - t) * 30; else if (t > 58) off = -(t - 58) * 30; else off = 0;
  const a = t < 6 ? t / 6 : t > 64 ? (70 - t) / 6 : 1;
  ctx.globalAlpha = 0.85 * a;
  fill(ctx, 0, 68, W, 44, color);
  ctx.globalAlpha = a;
  fill(ctx, 0, 68, W, 1, '#fff4d0');
  fill(ctx, 0, 111, W, 1, '#fff4d0');
  drawTextScaled(ctx, text, W / 2 + off, 74, '#ffffff', 2, { align: 'center', outline: '#10081c' });
  if (sub) drawText(ctx, sub, W / 2 - off, 98, '#f8e8c0', { align: 'center', shadow: '#000' });
  ctx.globalAlpha = 1;
}

// 经验条
export function drawExpBar(ctx, name, exp, t) {
  const w = 180, h = 30, x = (W - w) / 2, y = H - 50;
  drawWindow(ctx, x, y, w, h, 'menu');
  drawText(ctx, name, x + 8, y + 8, '#ffffff', { shadow: '#000' });
  drawText(ctx, 'EXP', x + 56, y + 8, '#f8e0a0', { shadow: '#000' });
  drawBar(ctx, x + 82, y + 12, 64, 5, Math.min(1, exp / 100), '#f8d040', '#2a2440');
  drawText(ctx, String(Math.floor(exp)), x + w - 8, y + 8, '#ffffff', { align: 'right', shadow: '#000' });
}

// 升级窗口
export function drawLevelUp(ctx, u, before, gains, shown, t) {
  const w = 216, h = 118, x = (W - w) / 2, y = 22;
  drawWindow(ctx, x, y, w, h, 'blue');
  drawMini(ctx, u.portrait, x + 8, y + 8);
  drawText(ctx, u.name, x + 46, y + 8, '#ffffff', { shadow: '#000' });
  drawText(ctx, `${className(u)}  Lv ${before.lv} → ${u.lv}`, x + 46, y + 22, '#f8e0a0', { shadow: '#000' });
  const keys = ['hp', 'str', 'mag', 'skl', 'spd', 'lck', 'def', 'res'];
  keys.forEach((k, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const xx = x + 14 + col * 102, yy = y + 44 + row * 16;
    const g = gains[k] || 0;
    const visible = i < shown;
    const val = (k === 'hp' ? before.mhp : before[k]) + (visible ? g : 0);
    drawText(ctx, STAT_NAMES[k], xx, yy, '#c8d8ff', { shadow: '#000' });
    drawText(ctx, String(val), xx + 56, yy, '#ffffff', { align: 'right', shadow: '#000' });
    if (visible && g) {
      const bounce = Math.max(0, 4 - (t - i * 10) / 2);
      drawText(ctx, '+' + g, xx + 62, yy - Math.round(bounce), '#80ff80', { shadow: '#000' });
    }
  });
  if (shown >= 8) drawText(ctx, `获得潜能点 +${R.POINTS_PER_LEVEL}（部队→加点）`, x + w / 2, y + h - 14, '#f8d878', { align: 'center', shadow: '#000' });
}

// 小提示窗（获得物品、增援等）：y 为数字时固定位置；传 avoid（矩形数组）时自动选上方或下方不遮挡的位置
export function drawNotice(ctx, rawLines, y = 24, style = 'dark', avoid = null) {
  const lines = [];
  for (const l of rawLines) lines.push(...wrapText(l, W - 36));
  let w = 0;
  for (const l of lines) w = Math.max(w, textWidth(l));
  w += 20;
  const h = lines.length * 14 + 10;
  const x = Math.round((W - w) / 2);
  if (avoid) {
    const top = { x, y: 44, w, h }, bottom = { x, y: H - h - 44, w, h };
    const hitTop = avoid.some((a) => rectOverlap(top, a));
    const hitBottom = avoid.some((a) => rectOverlap(bottom, a));
    y = hitTop && !hitBottom ? bottom.y : top.y;
  }
  if (y + h > H - 2) y = H - 2 - h;
  drawWindow(ctx, x, y, w, h, style, 0.96);
  lines.forEach((l, i) => drawText(ctx, l, x + 10, y + 5 + i * 14, '#f8f0e0', { shadow: '#000' }));
}
