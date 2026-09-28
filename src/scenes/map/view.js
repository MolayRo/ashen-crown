// 地图渲染：摄像机、地图图像（3 帧动画 + 变化格）、范围格、路径箭头、单位、光标、标记
import { W, H } from '../../core/renderer.js';
import { fill, frameRect } from '../../core/gfx.js';
import { drawText } from '../../core/font.js';
import { images, sheets } from '../../core/assets.js';
import { key, unkey } from '../../game/pathfind.js';
import { speedMul } from '../../core/settings.js';

export const TS = 16;

export function teamColor(u) {
  if (u.team === 'enemy') return 'red';
  if (u.team === 'ally' || u.team === 'npc') return 'green';
  return 'blue';
}

// 按动画表取帧（全局计时，所有待机单位同步）
function animFrame(sheet, name, t) {
  const a = sheet && sheet.meta.anims && sheet.meta.anims[name];
  if (!a || !a.length) return null;
  let total = 0;
  for (const [, d] of a) total += d;
  let m = t % total;
  for (const [f, d] of a) { if (m < d) return f; m -= d; }
  return a[0][0];
}

export class MapView {
  constructor(state) {
    this.state = state;
    this.cam = { x: 0, y: 0 };
    this.camTarget = { x: 0, y: 0 };
    this.cursor = { x: 0, y: 0 };
    this.t = 0;
    this.overlays = { move: null, attack: null, staff: null, threat: null, unitRange: null, deploy: null };
    this.path = null;
    this.anims = new Map();      // uid -> {px, py, dir, moving, alpha, flash, offx, offy}
    this.floaters = [];           // 飘字
    this.effects = [];            // 地图特效（火焰、闪光）
    this.markers = [];            // 增援预告
    this.hideUnits = new Set();
    this.mapW = state.w * TS;
    this.mapH = state.h * TS;
    this.shake = 0;
  }

  // ---- 摄像机 ----
  clampCam(x, y) {
    const maxX = Math.max(0, this.mapW - W), maxY = Math.max(0, this.mapH - H);
    const cx = this.mapW < W ? -(W - this.mapW) / 2 : Math.max(0, Math.min(maxX, x));
    const cy = this.mapH < H ? -(H - this.mapH) / 2 : Math.max(0, Math.min(maxY, y));
    return { x: Math.round(cx), y: Math.round(cy) };
  }
  centerOn(tx, ty, instant = false) {
    const c = this.clampCam(tx * TS + 8 - W / 2, ty * TS + 8 - H / 2);
    this.camTarget = c;
    if (instant) this.cam = { ...c };
  }
  // 光标靠近屏幕边缘时推动摄像机
  follow(tx, ty, margin = 2) {
    let { x, y } = this.camTarget;
    const px = tx * TS, py = ty * TS;
    if (px - x < margin * TS) x = px - margin * TS;
    if (px + TS - x > W - margin * TS) x = px + TS - W + margin * TS;
    if (py - y < margin * TS) y = py - margin * TS;
    if (py + TS - y > H - margin * TS) y = py + TS - H + margin * TS;
    this.camTarget = this.clampCam(x, y);
  }
  get camSettled() { return Math.abs(this.cam.x - this.camTarget.x) < 1 && Math.abs(this.cam.y - this.camTarget.y) < 1; }

  update() {
    this.t++;
    const sp = 6 * speedMul();
    for (const k of ['x', 'y']) {
      const d = this.camTarget[k] - this.cam[k];
      this.cam[k] += Math.sign(d) * Math.min(Math.abs(d), Math.max(1, Math.abs(d) * 0.25, sp));
    }
    for (const f of this.floaters) { f.t++; f.y -= f.t < 20 ? 0.5 : 0; }
    this.floaters = this.floaters.filter((f) => f.t < f.life);
    for (const e of this.effects) e.t++;
    this.effects = this.effects.filter((e) => e.t < e.life);
    if (this.shake > 0) this.shake--;
  }

  screenOf(tx, ty) { return { x: tx * TS - Math.round(this.cam.x), y: ty * TS - Math.round(this.cam.y) }; }
  tileAt(sx, sy) { return { x: Math.floor((sx + Math.round(this.cam.x)) / TS), y: Math.floor((sy + Math.round(this.cam.y)) / TS) }; }

  addFloater(tx, ty, text, color = '#ffffff', life = 60) {
    this.floaters.push({ x: tx * TS + 8, y: ty * TS - 2, text, color, t: 0, life });
  }

  // ---- 绘制 ----
  draw(ctx, opts = {}) {
    const s = this.state;
    const ox = Math.round(this.cam.x) + (this.shake ? Math.round((Math.random() - 0.5) * 4) : 0);
    const oy = Math.round(this.cam.y);
    fill(ctx, 0, 0, W, H, '#0a0a10');
    // 地图底图（3 帧动画：0,1,2,1）
    const seq = [0, 1, 2, 1];
    const fi = seq[Math.floor(this.t / 24) % 4];
    const base = images['map_' + s.chapterId + '_' + fi] || images['map_' + s.chapterId + '_0'];
    if (base) ctx.drawImage(base, -ox, -oy);
    else this.drawFallbackTiles(ctx, ox, oy);
    // 已改变的格子（开门、开箱、焚毁）
    const alt = images['map_' + s.chapterId + '_alt'];
    for (const [x, y] of s.changed) {
      if (alt) ctx.drawImage(alt, x * TS, y * TS, TS, TS, x * TS - ox, y * TS - oy, TS, TS);
      else fill(ctx, x * TS - ox, y * TS - oy, TS, TS, '#3a3028');
    }
    // 焚毁的村庄冒烟
    for (const [k, v] of Object.entries(s.villages)) {
      if (v !== 'razed') continue;
      const [x, y] = k.split(',').map(Number);
      this.drawFx(ctx, 'smoke', x * TS + 8 - ox, y * TS + 12 - oy, this.t + x * 7);
    }
    // 目标标记
    const obj = s.ch.objective;
    if (obj.escape) for (const [x, y] of obj.escape) this.drawFx(ctx, 'escape', x * TS - ox, y * TS - oy, this.t, true);
    if (obj.seize) this.drawFx(ctx, 'seize', obj.seize[0] * TS - ox, obj.seize[1] * TS - oy, this.t, true);
    if (obj.defendTile) this.drawFx(ctx, 'defend', obj.defendTile[0] * TS - ox, obj.defendTile[1] * TS - oy, this.t, true);
    // 范围格
    const ov = this.overlays;
    if (ov.threat) this.drawRange(ctx, ov.threat, 'threat', ox, oy);
    if (ov.unitRange) this.drawRange(ctx, ov.unitRange, 'attack', ox, oy);
    if (ov.deploy) this.drawRange(ctx, ov.deploy, 'move', ox, oy);
    if (ov.attack) this.drawRange(ctx, ov.attack, 'attack', ox, oy);
    if (ov.staff) this.drawRange(ctx, ov.staff, 'staff', ox, oy);
    if (ov.move) this.drawRange(ctx, ov.move, 'move', ox, oy);
    if (this.path && this.path.length > 1) this.drawPath(ctx, this.path, ox, oy);
    // 增援预告
    for (const m of this.markers) this.drawFx(ctx, 'warn', m.x * TS - ox, m.y * TS - oy, this.t, true);
    // 单位
    const units = s.units.filter((u) => !u.dead && !u.hidden && !this.hideUnits.has(u.uid)).concat(s.units.filter((u) => (u.dead || u.hidden) && this.anims.get(u.uid) && this.anims.get(u.uid).fading));
    units.sort((a, b) => this.unitPy(a) - this.unitPy(b));
    for (const u of units) this.drawUnit(ctx, u, ox, oy, opts);
    // 地图特效
    for (const e of this.effects) this.drawFx(ctx, e.name, e.x - ox, e.y - oy, e.t);
    // 光标
    if (opts.cursor !== false) this.drawCursor(ctx, ox, oy);
    // 飘字
    for (const f of this.floaters) {
      const a = f.t > f.life - 15 ? (f.life - f.t) / 15 : 1;
      ctx.globalAlpha = a;
      drawText(ctx, f.text, Math.round(f.x - ox), Math.round(f.y - oy - Math.min(10, f.t * 0.6)), f.color, { align: 'center', shadow: '#000' });
      ctx.globalAlpha = 1;
    }
  }

  drawFallbackTiles(ctx, ox, oy) {
    const s = this.state;
    const COL = { '.': '#5c9a3a', ',': '#6aa840', '"': '#b89a68', T: '#245232', h: '#8a9a4a', '^': '#8a6a50', A: '#c8c0b8', '~': '#2858a8', _: '#6aa8e8', '=': '#8a6a44', B: '#1c3a78', '#': '#3a3848', '+': '#7e7c92', c: '#8c1c30', '|': '#a8a6b8', D: '#6a4424', C: '#e0a830', V: '#c04a38', H: '#8e2e28', F: '#9a9aa6', G: '#6e6e7c', K: '#e0c040', S: '#5a586c', x: '#4a3a34', r: '#6a5a4a', f: '#9a6a3a', a: '#d0c8b0', P: '#5a586c' };
    for (let y = 0; y < s.h; y++) for (let x = 0; x < s.w; x++) {
      fill(ctx, x * TS - ox, y * TS - oy, TS, TS, COL[s.charAt(x, y)] || '#444');
    }
  }

  unitPy(u) {
    const a = this.anims.get(u.uid);
    return a && a.moving ? a.py : u.y * TS;
  }

  drawRange(ctx, set, kind, ox, oy) {
    const fx = sheets.mapfx;
    const n = 4;
    const fi = Math.floor(this.t / 8) % n;
    for (const k of set) {
      const { x, y } = typeof k === 'number' ? unkey(k) : k;
      const sx = x * TS - ox, sy = y * TS - oy;
      if (sx < -TS || sy < -TS || sx > W || sy > H) continue;
      if (fx && fx.has(kind + fi)) fx.draw(ctx, kind + fi, sx, sy);
      else {
        const c = { move: 'rgba(80,140,255,0.45)', attack: 'rgba(255,70,60,0.42)', staff: 'rgba(80,220,110,0.42)', threat: 'rgba(200,40,140,0.32)' }[kind];
        fill(ctx, sx + 1, sy + 1, TS - 2, TS - 2, c);
      }
    }
  }

  drawPath(ctx, path, ox, oy) {
    const fx = sheets.mapfx;
    const dirOf = (a, b) => (b.x > a.x ? 'r' : b.x < a.x ? 'l' : b.y > a.y ? 'd' : 'u');
    for (let i = 0; i < path.length; i++) {
      const p = path[i];
      const sx = p.x * TS - ox, sy = p.y * TS - oy;
      let name;
      if (i === 0) name = 'arrow_start_' + dirOf(p, path[1]);
      else if (i === path.length - 1) name = 'arrow_head_' + dirOf(path[i - 1], p);
      else {
        const a = dirOf(p, path[i - 1]), b = dirOf(p, path[i + 1]);
        const set = new Set([a, b]);
        if (set.has('l') && set.has('r')) name = 'arrow_h';
        else if (set.has('u') && set.has('d')) name = 'arrow_v';
        else name = 'arrow_' + (set.has('u') ? 'n' : 's') + (set.has('r') ? 'e' : 'w');
      }
      if (fx && fx.has(name)) fx.draw(ctx, name, sx, sy);
      else fill(ctx, sx + 5, sy + 5, 6, 6, '#f8e060');
    }
  }

  drawFx(ctx, name, x, y, t, tileAnchored = false) {
    const fx = sheets.mapfx;
    if (fx && fx.meta.anims && fx.meta.anims[name]) {
      const f = animFrame(fx, name, t);
      if (f) fx.draw(ctx, f, x, y);
      return;
    }
    if (fx && fx.has(name + '0')) { fx.draw(ctx, name + (Math.floor(t / 10) % 2), x, y); return; }
    // 占位
    if (name === 'warn') { if (Math.floor(t / 15) % 2 === 0) drawText(ctx, '!', x + 6, y + 2, '#ff4030', { shadow: '#000' }); }
    else if (name === 'escape') frameRect(ctx, x + 1, y + 1, TS - 2, TS - 2, '#60e080');
    else if (name === 'seize') frameRect(ctx, x + 1, y + 1, TS - 2, TS - 2, '#f8d040');
    else if (name === 'defend') frameRect(ctx, x + 1, y + 1, TS - 2, TS - 2, '#60a0ff');
  }

  drawCursor(ctx, ox, oy) {
    const fx = sheets.mapfx;
    const sx = this.cursor.x * TS - ox, sy = this.cursor.y * TS - oy;
    if (fx && fx.meta.anims && fx.meta.anims.cursor) {
      fx.draw(ctx, animFrame(fx, 'cursor', this.t), sx, sy);
      return;
    }
    const p = Math.floor(this.t / 15) % 2;
    const c = '#fff4c0';
    const d = p ? 1 : 0;
    for (const [cx, cy, dx, dy] of [[sx - d, sy - d, 1, 1], [sx + TS - 1 + d, sy - d, -1, 1], [sx - d, sy + TS - 1 + d, 1, -1], [sx + TS - 1 + d, sy + TS - 1 + d, -1, -1]]) {
      fill(ctx, cx, cy, 4 * dx, 1, c);
      fill(ctx, cx, cy, 1, 4 * dy, c);
    }
  }

  drawUnit(ctx, u, ox, oy, opts) {
    const sh = sheets.units;
    const a = this.anims.get(u.uid) || {};
    const px = (a.moving ? a.px : u.x * TS) + (a.offx || 0) - ox;
    const py = (a.moving ? a.py : u.y * TS) + (a.offy || 0) - oy;
    if (px < -32 || py < -32 || px > W + 16 || py > H + 32) return;
    const alpha = a.alpha != null ? a.alpha : 1;
    if (alpha <= 0) return;
    const team = u.acted && u.team === 'player' && this.state.phase === 'player' && !a.moving ? 'grey' : teamColor(u);
    const model = u.model || 'soldier';
    let anim = 'idle';
    let flip = false;
    if (a.moving || (opts.selected === u && !a.moving)) {
      const dir = a.dir || 'down';
      anim = dir === 'left' || dir === 'right' ? 'side' : dir;
      flip = dir === 'right';
    }
    const fx = sheets.mapfx;
    if (fx && fx.has('shadow')) fx.draw(ctx, 'shadow', px, py + 12, false, alpha * 0.9);
    if (sh) {
      let name = animFrame(sh, `${model}_${team}_${anim}`, a.moving ? a.walkT || this.t : this.t);
      if (!name) name = animFrame(sh, `${model}_${team === 'grey' ? 'blue' : team}_idle`, this.t);
      if (name) {
        const fxX = px + 8, fxY = py + 15;
        if (team === 'grey' && !sh.has(name)) sh.drawGrey(ctx, name.replace('_grey_', '_blue_'), fxX, fxY, flip);
        else sh.draw(ctx, name, fxX, fxY, flip, alpha);
        if (a.flash) sh.drawTinted(ctx, name, fxX, fxY, flip, a.flashColor || '#ffffff', a.flash);
        // 首领标记
        if (u.boss && u.team === 'enemy') this.drawBossMark(ctx, px, py);
        if (opts.talkMarks && opts.talkMarks.has(u.uid)) this.drawFx(ctx, 'talk', px + 10, py - 6, this.t);
        return;
      }
    }
    // 占位
    const col = { red: '#d04038', blue: '#3c64b8', green: '#3c9040', grey: '#7a7a86' }[team];
    ctx.globalAlpha = alpha;
    fill(ctx, px + 3, py + 3, 10, 12, col);
    fill(ctx, px + 5, py + 1, 6, 5, '#f2b896');
    ctx.globalAlpha = 1;
    drawText(ctx, u.name.slice(0, 1), px + 8, py + 3, '#fff', { align: 'center' });
  }

  drawBossMark(ctx, px, py) {
    const c = '#f8d040';
    fill(ctx, px + 12, py - 1, 4, 1, c);
    fill(ctx, px + 12, py - 1, 1, 3, c);
    fill(ctx, px + 14, py - 2, 1, 2, c);
    fill(ctx, px + 15, py - 1, 1, 3, c);
    fill(ctx, px + 12, py + 1, 4, 1, c);
  }
}
