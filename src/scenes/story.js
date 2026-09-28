// 剧情播放：背景、头像（口型/眨眼）、逐字显示、快进、跳过（确认）、对白回看
import { W, H } from '../core/renderer.js';
import { drawWindow, fill } from '../core/gfx.js';
import { drawText, wrapText, visibleLength, drawTextScaled, textWidth } from '../core/font.js';
import { images, sheets } from '../core/assets.js';
import { settings, speedMul } from '../core/settings.js';
import { audio } from '../core/audio.js';
import { getScript } from '../game/story/index.js';
import { PORTRAIT_EXPR, EXPRESSIONS, CHARACTERS } from '../game/data/characters.js';
import { ConfirmDialog } from './confirm.js';

const POS_X = { farleft: -8, left: 44, right: 196, farright: 248 };
const BOX = { x: 4, y: 122, w: 312, h: 54 };
const LINES = 3;
const LINE_H = 15;
const TEXT_W = 292;

export function portraitFrame(id, expr, variant = '') {
  const sh = sheets.portraits;
  if (!sh) return null;
  const allowed = EXPRESSIONS[PORTRAIT_EXPR[id] || 'one'] || ['normal'];
  let e = expr && allowed.includes(expr) ? expr : 'normal';
  // 缺少的表情退回相近表情
  if (!sh.has(`${id}_${e}`)) e = 'normal';
  const name = variant ? `${id}_${e}_${variant}` : `${id}_${e}`;
  if (sh.has(name)) return name;
  if (sh.has(`${id}_${e}`)) return `${id}_${e}`;
  return null;
}

export function drawPortrait(ctx, id, expr, x, y, flip, variant = '', alpha = 1) {
  const sh = sheets.portraits;
  const f = portraitFrame(id, expr, variant);
  if (sh && f) { sh.draw(ctx, f, x, y, flip, alpha); return true; }
  // 素材缺失时的占位剪影
  ctx.globalAlpha = alpha;
  drawWindow(ctx, x + 8, y + 8, 64, 72, 'dark');
  drawText(ctx, (CHARACTERS[id] && CHARACTERS[id].name) || id, x + 40, y + 40, '#fff', { align: 'center' });
  ctx.globalAlpha = 1;
  return false;
}

export class StoryScene {
  // opts: {campaign, battle, overlay(地图上播放), onDone}
  constructor(scriptId, opts = {}) {
    this.scriptId = scriptId;
    this.opts = opts;
    this.overlay = !!opts.overlay;
    this.campaign = opts.campaign || null;
    this.battle = opts.battle || null;
    this.nodes = getScript(scriptId) || [];
    this.stack = [{ nodes: this.nodes, i: 0 }];
    this.bg = this.overlay ? 'map' : 'black';
    this.bgAlpha = 1;
    this.slots = {};          // pos -> {id, expr, alpha, blinkT}
    this.speaker = null;
    this.line = null;         // 当前对白 {name, id, text, pages, page, shown}
    this.waitT = 0;
    this.shakeT = 0;
    this.flashT = 0;
    this.flashColor = '#fff';
    this.fade = 0;
    this.fadeTarget = 0;
    this.card = null;         // 章节标题卡
    this.log = [];
    this.logView = null;
    this.frame = 0;
    this.done = false;
    this.textTimer = 0;
    this.blipCount = 0;
  }

  enter(game) {
    this.game = game;
    if (!this.nodes.length) { this.finish(); return; }
    this.advance();
  }

  cond(expr) {
    if (!expr) return true;
    // 战斗中的 onmap 条件交给战斗状态判断，其余交给战役
    return expr.split('&').every((p) => {
      p = p.trim();
      const neg = p.startsWith('!');
      const q = neg ? p.slice(1) : p;
      let r;
      if (q.startsWith('onmap:') && this.battle) r = !!this.battle.findUnit(q.slice(6));
      else if (q.startsWith('alive:') && this.battle && this.battle.findUnit(q.slice(6))) r = true;
      else if (this.campaign) r = this.campaign.cond(q);
      else r = true;
      return neg ? !r : r;
    });
  }

  nextNode() {
    while (this.stack.length) {
      const fr = this.stack[this.stack.length - 1];
      if (fr.i >= fr.nodes.length) { this.stack.pop(); continue; }
      const n = fr.nodes[fr.i++];
      if (n.t === 'if') {
        let body = null;
        for (const b of n.branches) if (this.cond(b.cond)) { body = b.body; break; }
        if (!body && n.else) body = n.else;
        if (body) this.stack.push({ nodes: body, i: 0 });
        continue;
      }
      return n;
    }
    return null;
  }

  // 执行指令直到遇到需要等待的节点
  advance() {
    this.line = null;
    for (let guard = 0; guard < 500; guard++) {
      const n = this.nextNode();
      if (!n) { this.finish(); return; }
      switch (n.t) {
        case 'bg':
          if (n.id !== this.bg) {
            if (this.bg === 'black' || this.bg === 'map' || n.id === 'map' || this.fade >= 1) { this.bg = n.id; }
            else { this.pendingBg = n.id; this.fadeTarget = 1; this.waitFade = true; return; }
          }
          break;
        case 'music':
          if (n.id === 'stop') audio.stopMusic(1.2); else audio.playMusic(n.id);
          break;
        case 'sfx': audio.sfx(n.id); break;
        case 'wait': this.waitT = Math.round(n.n / speedMul()); return;
        case 'shake': this.shakeT = n.n * 3; break;
        case 'flash': this.flashT = 10; this.flashColor = n.color === 'red' ? '#ff3020' : '#ffffff'; break;
        case 'fadeout': this.fadeTarget = 1; this.waitFade = true; return;
        case 'fadein': this.fadeTarget = 0; this.waitFade = true; return;
        case 'chapter':
          this.card = { title: n.title, name: n.name, t: 0 };
          audio.playJingle && audio.playJingle('chapter');
          return;
        case 'show': this.show(n.id, n.pos, n.expr); break;
        case 'hide':
          if (n.id === 'all') this.slots = {};
          else for (const k of Object.keys(this.slots)) if (this.slots[k].id === n.id) delete this.slots[k];
          if (this.speaker === n.id) this.speaker = null;
          break;
        case 'set':
          if (this.campaign) this.campaign.flags[n.flag] = true;
          break;
        case 'say': this.startLine(n.name, n.id, n.text, n.expr); return;
        case 'narr': this.startLine(null, null, n.text, null); return;
        default: break;
      }
    }
  }

  show(id, pos, expr) {
    for (const k of Object.keys(this.slots)) if (this.slots[k].id === id) {
      if (!pos || pos === k) { this.slots[k].expr = expr || this.slots[k].expr; return; }
      delete this.slots[k];
    }
    if (!pos) pos = this.freeSlot();
    this.slots[pos] = { id, expr: expr || 'normal', alpha: 0, blinkT: 60 + Math.floor(Math.random() * 180) };
  }

  freeSlot() {
    for (const p of ['left', 'right', 'farleft', 'farright']) if (!this.slots[p]) return p;
    // 替换最早的非说话人
    for (const p of ['farleft', 'farright', 'left', 'right']) if (this.slots[p].id !== this.speaker) return p;
    return 'left';
  }

  slotOf(id) {
    for (const k of Object.keys(this.slots)) if (this.slots[k].id === id) return k;
    return null;
  }

  startLine(name, id, text, expr) {
    if (this.fade > 0 && !this.waitFade) this.fadeTarget = 0;
    if (id && PORTRAIT_EXPR[id]) {
      const pos = this.slotOf(id);
      if (!pos) this.show(id, null, expr || 'normal');
      else if (expr) this.slots[pos].expr = expr;
    }
    this.speaker = id;
    const lines = wrapText(text, TEXT_W);
    const pages = [];
    for (let i = 0; i < lines.length; i += LINES) pages.push(lines.slice(i, i + LINES));
    this.line = { name, id, text, pages, page: 0, shown: 0, total: pageLen(pages[0]) };
    this.log.push({ name: name || '', text });
    if (this.log.length > 300) this.log.shift();
    this.textTimer = 0;
  }

  finish() {
    if (this.done) return;
    this.done = true;
    this.game.remove(this);
    if (this.opts.onDone) this.opts.onDone();
  }

  // 跳过：只执行有副作用的指令
  skipAll() {
    let lastMusic = null;
    for (let n = this.nextNode(); n; n = this.nextNode()) {
      if (n.t === 'set' && this.campaign) this.campaign.flags[n.flag] = true;
      if (n.t === 'music') lastMusic = n.id;
    }
    if (lastMusic) { if (lastMusic === 'stop') audio.stopMusic(0.5); else audio.playMusic(lastMusic); }
    this.finish();
  }

  update(game) {
    this.frame++;
    const input = game.input;
    // 头像淡入、眨眼
    for (const s of Object.values(this.slots)) {
      s.alpha = Math.min(1, s.alpha + 0.12);
      if (--s.blinkT < -6) s.blinkT = 90 + Math.floor(Math.random() * 200);
    }
    if (this.shakeT > 0) this.shakeT--;
    if (this.flashT > 0) this.flashT--;
    // 淡入淡出（waitFade 为真时阻塞脚本，否则只是画面渐变）
    if (this.fade !== this.fadeTarget) {
      const d = this.fadeTarget - this.fade;
      this.fade += Math.sign(d) * Math.min(Math.abs(d), 0.06 * speedMul() * (input.fast() ? 3 : 1));
      if (this.waitFade) return;
    }
    if (this.waitFade) {
      this.waitFade = false;
      if (this.pendingBg) { this.bg = this.pendingBg; this.pendingBg = null; this.fadeTarget = 0; this.waitFade = true; return; }
      this.advance();
      return;
    }
    if (this.logView) { this.updateLog(input); return; }
    if (input.pressed('log') || (input.mouse.wheel < 0 && this.log.length > 1)) {
      this.logView = { scroll: Math.max(0, this.log.length - 1) };
      audio.sfx('page');
      return;
    }
    if (input.cancel()) {
      audio.sfx('cancel');
      game.push(new ConfirmDialog('跳过这段剧情？', (yes) => { if (yes) this.skipAll(); }, { yes: '跳过', no: '继续观看' }));
      return;
    }
    const fast = input.fast() || !!game.autoAdvance;
    if (this.card) {
      this.card.t += fast ? 4 : 1;
      if (this.card.t > 150 || ((input.confirm() || input.click()) && this.card.t > 20)) {
        this.card = null;
        // 标题卡之后保持黑屏，由后续 @fadein 或第一句对白淡入
        this.fade = 1;
        this.fadeTarget = 1;
        this.advance();
      }
      return;
    }
    if (this.waitT > 0) { this.waitT -= fast ? 4 : 1; if (this.waitT <= 0) this.advance(); return; }
    const L = this.line;
    if (!L) return;
    const pageDone = L.shown >= L.total;
    if (!pageDone) {
      const spd = settings.textSpeed;
      let perFrame = [0.34, 0.5, 1, 99][spd] ?? 1;
      if (fast) perFrame = 99;
      this.textTimer += perFrame;
      const add = Math.floor(this.textTimer);
      if (add > 0) {
        this.textTimer -= add;
        L.shown = Math.min(L.total, L.shown + add);
        if (spd < 3 && !fast) {
          this.blipCount += add;
          if (this.blipCount >= 3) { this.blipCount = 0; audio.sfx('text', { vol: 0.35 }); }
        }
      }
      if (input.confirm() || input.click()) L.shown = L.total;
      return;
    }
    if (fast) {
      this.autoT = (this.autoT || 0) + 1;
      if (this.autoT < 5) return;
    }
    this.autoT = 0;
    if (fast || input.confirm() || input.click()) {
      if (L.page < L.pages.length - 1) {
        L.page++;
        L.shown = 0;
        L.total = pageLen(L.pages[L.page]);
      } else {
        this.advance();
      }
    }
  }

  updateLog(input) {
    const lv = this.logView;
    if (input.repeat('up') || input.mouse.wheel < 0) lv.scroll = Math.max(0, lv.scroll - 1);
    if (input.repeat('down') || input.mouse.wheel > 0) {
      if (lv.scroll >= this.log.length - 1 && (input.mouse.wheel > 0)) { this.logView = null; return; }
      lv.scroll = Math.min(this.log.length - 1, lv.scroll + 1);
    }
    if (input.cancel() || input.pressed('log') || input.confirm() || input.click()) { this.logView = null; audio.sfx('cancel'); }
  }

  draw(ctx, game) {
    const sx = this.shakeT > 0 ? Math.round((Math.random() - 0.5) * Math.min(6, this.shakeT / 3)) : 0;
    const sy = this.shakeT > 0 ? Math.round((Math.random() - 0.5) * Math.min(4, this.shakeT / 4)) : 0;
    ctx.save();
    ctx.translate(sx, sy);
    // 背景
    if (this.bg !== 'map') {
      const img = images['bg_' + this.bg];
      if (img) ctx.drawImage(img, 0, 0);
      else fill(ctx, -8, -8, W + 16, H + 16, '#07060b');
    } else {
      ctx.globalAlpha = 0.25;
      fill(ctx, 0, 0, W, H, '#000');
      ctx.globalAlpha = 1;
    }
    // 头像
    const talking = this.line && this.line.shown < this.line.total;
    for (const pos of ['farleft', 'farright', 'left', 'right']) {
      const s = this.slots[pos];
      if (!s) continue;
      const x = POS_X[pos];
      const flip = pos === 'right' || pos === 'farright';
      let variant = '';
      if (s.blinkT < 0) variant = 'blink';
      if (talking && s.id === this.speaker && Math.floor(this.frame / 7) % 2 === 0) variant = 'talk';
      drawPortrait(ctx, s.id, s.expr, x, BOX.y - 80, flip, variant, s.alpha);
      // 非说话人稍暗
      if (this.speaker && s.id !== this.speaker) {
        const sh = sheets.portraits;
        const f = portraitFrame(s.id, s.expr, variant);
        if (sh && f) sh.drawTinted(ctx, f, x, BOX.y - 80, flip, '#0a0814', 0.22 * s.alpha);
      }
    }
    ctx.restore();

    // 对白框
    const L = this.line;
    if (L && !this.card) {
      const narr = !L.name;
      drawWindow(ctx, BOX.x, BOX.y, BOX.w, BOX.h, narr ? 'dark' : 'dialog', narr ? 0.92 : 1);
      if (!narr) {
        const pos = this.slotOf(L.id);
        const right = pos === 'right' || pos === 'farright';
        const nw = textWidth(L.name) + 16;
        const nx = right ? BOX.x + BOX.w - nw - 10 : BOX.x + 10;
        drawWindow(ctx, nx, BOX.y - 13, nw, 17, 'gold');
        drawText(ctx, L.name, nx + 8, BOX.y - 10, '#fff4d0', { shadow: '#2a1804' });
      }
      const page = L.pages[L.page] || [];
      let left = L.shown;
      const col = narr ? '#ece4d0' : '#2a1a10';
      for (let i = 0; i < page.length; i++) {
        const n = visibleLength(page[i]);
        drawText(ctx, page[i], BOX.x + 10, BOX.y + 6 + i * LINE_H, col, { limit: Math.max(0, left), shadow: narr ? '#000' : null });
        left -= n;
        if (left <= 0) break;
      }
      if (L.shown >= L.total && Math.floor(this.frame / 16) % 2 === 0) {
        const ax = BOX.x + BOX.w - 14, ay = BOX.y + BOX.h - 10;
        ctx.fillStyle = narr ? '#f0d890' : '#6a3a10';
        ctx.fillRect(ax, ay, 7, 1); ctx.fillRect(ax + 1, ay + 1, 5, 1); ctx.fillRect(ax + 2, ay + 2, 3, 1); ctx.fillRect(ax + 3, ay + 3, 1, 1);
      }
    }
    // 章节标题卡
    if (this.card) this.drawCard(ctx);
    // 操作提示
    if (!this.card && !this.logView) {
      ctx.globalAlpha = 0.7;
      drawText(ctx, 'Shift快进  L回看  Esc跳过', W - 4, 2, '#d8d0c0', { align: 'right', shadow: '#000' });
      ctx.globalAlpha = 1;
    }
    if (this.flashT > 0) {
      ctx.globalAlpha = this.flashT / 10;
      fill(ctx, 0, 0, W, H, this.flashColor);
      ctx.globalAlpha = 1;
    }
    if (this.fade > 0) {
      ctx.globalAlpha = Math.round(this.fade * 8) / 8;
      fill(ctx, 0, 0, W, H, '#000');
      ctx.globalAlpha = 1;
    }
    if (this.logView) this.drawLog(ctx);
  }

  drawCard(ctx) {
    const t = this.card.t;
    const a = Math.min(1, t / 20) * (t > 130 ? Math.max(0, (150 - t) / 20) : 1);
    ctx.globalAlpha = Math.min(1, a * 1.2);
    fill(ctx, 0, 0, W, H, '#07060c');
    ctx.globalAlpha = a;
    fill(ctx, 40, 88, 240, 1, '#b8943c');
    drawTextScaled(ctx, this.card.title, W / 2, 56, '#e8d8a8', 2, { align: 'center', shadow: '#000' });
    drawTextScaled(ctx, this.card.name, W / 2, 98, '#fff4d8', 2, { align: 'center', outline: '#3a1c08' });
    ctx.globalAlpha = 1;
  }

  drawLog(ctx) {
    ctx.globalAlpha = 0.9;
    fill(ctx, 0, 0, W, H, '#07060c');
    ctx.globalAlpha = 1;
    drawWindow(ctx, 6, 4, W - 12, H - 8, 'dark');
    drawText(ctx, '对白回看（↑↓ 滚动，Esc 返回）', 14, 9, '#f0d890', { shadow: '#000' });
    const lv = this.logView;
    // 自下而上排版，当前选中的一条在底部
    let y = H - 20;
    for (let i = lv.scroll; i >= 0 && y > 26; i--) {
      const e = this.log[i];
      const lines = wrapText(e.text, W - 40);
      const h = lines.length * 14 + (e.name ? 14 : 0) + 4;
      y -= h;
      if (y < 24) break;
      let yy = y;
      if (e.name) { drawText(ctx, e.name, 16, yy, '#f8c870', { shadow: '#000' }); yy += 14; }
      for (const l of lines) { drawText(ctx, l, 24, yy, i === lv.scroll ? '#ffffff' : '#c8c0b0', { shadow: '#000' }); yy += 14; }
    }
  }
}

function pageLen(lines) {
  if (!lines) return 0;
  let n = 0;
  for (const l of lines) n += visibleLength(l);
  return n;
}
