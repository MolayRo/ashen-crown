// 入口：初始化渲染/输入/音频，加载资源，进入标题画面
import { Renderer, W, H } from './core/renderer.js';
import { Input } from './core/input.js';
import { Game } from './core/game.js';
import { loadSettings, settings, onSettingsChange } from './core/settings.js';
import { loadImage, loadAll, images } from './core/assets.js';
import { initFont, drawText } from './core/font.js';
import { fill, drawWindow } from './core/gfx.js';
import { audio } from './core/audio.js';
import { CHAPTERS } from './game/data/chapters.js';
import { registerScenes } from './scenes/flowctl.js';
import { TitleScene } from './scenes/title.js';
import { PrepScene } from './scenes/prep.js';
import { MapScene } from './scenes/map/mapscene.js';
import { CreditsScene } from './scenes/credits.js';
import { toggleFullscreen } from './scenes/settings.js';

const bootEl = document.getElementById('boot');

function fail(e) {
  console.error(e);
  bootEl.style.display = '';
  bootEl.classList.add('err');
  bootEl.textContent = '启动失败：' + (e && e.message ? e.message : e);
}

export const BG_IDS = ['festival', 'throne_fire', 'passage', 'forest_night', 'village_burning', 'village_after', 'capital_square',
  'river_bridge', 'refugee_camp', 'monastery_ext', 'chapel', 'snow_road', 'snow_fort', 'war_camp', 'castle_gate', 'throne_dawn',
  'coronation', 'capital_dawn'];

function manifest() {
  const m = [
    { key: 'title_bg', img: 'assets/title_bg.png', optional: true },
    { key: 'logo', img: 'assets/logo.png', optional: true },
    { key: 'units', img: 'assets/units.png', meta: 'assets/units.json', optional: true },
    { key: 'portraits', img: 'assets/portraits.png', meta: 'assets/portraits.json', optional: true },
    { key: 'icons', img: 'assets/icons.png', meta: 'assets/icons.json', optional: true },
    { key: 'mapfx', img: 'assets/mapfx.png', meta: 'assets/mapfx.json', optional: true },
    { key: 'battle_units', img: 'assets/battle_units.png', meta: 'assets/battle_units.json', optional: true },
    { key: 'battle_fx', img: 'assets/battle_fx.png', meta: 'assets/battle_fx.json', optional: true },
    { key: 'battle_bg', img: 'assets/battle_bg.png', meta: 'assets/battle_bg.json', optional: true },
  ];
  for (const id of BG_IDS) m.push({ key: 'bg_' + id, img: `assets/bg/${id}.png`, optional: true });
  for (const ch of CHAPTERS) {
    for (const f of ['0', '1', '2', 'alt']) m.push({ key: `map_${ch.id}_${f}`, img: `assets/maps/${ch.id}_${f}.png`, optional: true });
  }
  return m;
}

class LoadingScene {
  constructor() { this.p = 0; }
  update() {}
  draw(ctx) {
    fill(ctx, 0, 0, W, H, '#07060b');
    drawText(ctx, '灰烬王冠', W / 2, 70, '#e8c878', { align: 'center' });
    drawWindow(ctx, 80, 96, 160, 12, 'dark');
    fill(ctx, 84, 100, Math.round(152 * this.p), 4, '#f0c860');
    drawText(ctx, '载入中……', W / 2, 116, '#8a7a58', { align: 'center' });
  }
}

function toastDrawer(ctx, toast) {
  const a = Math.min(1, toast.t / 20);
  ctx.globalAlpha = a;
  const w = Math.min(W - 20, 24 + [...toast.text].length * 12);
  drawWindow(ctx, (W - w) / 2, H - 34, w, 20, 'dark');
  drawText(ctx, toast.text, W / 2, H - 30, '#fff4d8', { align: 'center', shadow: '#000' });
  ctx.globalAlpha = 1;
}

async function boot() {
  loadSettings();
  const display = document.getElementById('screen');
  const renderer = new Renderer(display);
  const input = new Input(renderer, display);
  const game = new Game(renderer, input);
  game.audio = audio;
  game.toastDrawer = toastDrawer;
  window.__game = game;
  onSettingsChange((k) => {
    if (k === 'pixelPerfect' || k === 'crt' || k === '*') renderer.resize();
  });
  input.onFirstGesture = () => audio.unlock();
  window.addEventListener('keydown', (e) => {
    if (e.code === 'F11') { e.preventDefault(); toggleFullscreen(); }
  });

  const fontImg = await loadImage('assets/font12.png');
  initFont(fontImg);
  bootEl.style.display = 'none';
  display.focus();

  registerScenes({ TitleScene, PrepScene, MapScene, CreditsScene });

  const loading = new LoadingScene();
  game.push(loading);

  let last = performance.now();
  let acc = 0;
  let lastRaf = 0;
  const STEP = 1000 / 60;
  function tick(now) {
    acc += Math.min(250, now - last);
    last = now;
    if (window.__pause) { acc = 0; return; }
    let n = 0;
    while (acc >= STEP && n < 4) { game.update(); acc -= STEP; n++; }
    if (n === 4) acc = 0;
    if (n > 0) { game.draw(); renderer.present(); }
  }
  function frame(now) {
    lastRaf = performance.now();
    tick(now);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  // 某些嵌入式/后台环境会暂停 requestAnimationFrame，用定时器兜底保证逻辑继续运行
  setInterval(() => {
    const now = performance.now();
    if (now - lastRaf > 100) tick(now);
  }, 16);
  // 调试：同步推进若干帧（自动化测试用）
  window.__step = (n = 60) => { for (let i = 0; i < n; i++) game.update(); game.draw(); renderer.present(); return game.frame; };

  await loadAll(manifest(), (p) => { loading.p = p; });
  if (audio.preload) audio.preload(['title']);
  if (debugStart(game)) return;
  game.transition(() => game.replace(new TitleScene()), 20);
}

// 开发调试入口：?debug=battle&ch=0 / ?debug=story&id=prologue / ?debug=prep&ch=1
function debugStart(game) {
  const q = new URLSearchParams(location.search);
  const mode = q.get('debug');
  if (!mode) return false;
  import('./game/campaign.js').then(async ({ Campaign }) => {
    const flow = await import('./scenes/flowctl.js');
    const { advanceChapter } = await import('./game/flow.js');
    const { newRosterEntry } = await import('./game/battle.js');
    const c = Campaign.newGame(q.get('diff') || 'normal', q.get('mode') || 'classic');
    const chIdx = parseInt(q.get('ch') || '0', 10);
    for (const id of ['doran', 'sid', 'mira', 'vera']) {
      const need = { doran: 1, sid: 2, mira: 3, vera: 4 }[id];
      if (chIdx >= need) c.addRecruit(id, newRosterEntry(id));
    }
    c.chapter = chIdx;
    game.campaign = c;
    void advanceChapter;
    if (mode === 'autotest') {
      // 端到端自动验收：从新游戏开始，剧情自动推进、整备自动出击、战斗由 AI 代打，一直到制作人员名单
      game.autotest = true;
      game.autoAdvance = true;
      window.__autotest = { log: [], done: false, failures: 0, started: Date.now() };
      const note = (m) => {
        window.__autotest.log.push(`[${((Date.now() - window.__autotest.started) / 1000).toFixed(0)}s] ${m}`);
        console.log('[autotest]', m);
        document.title = 'autotest ' + window.__autotest.log.length + ': ' + m;
      };
      game.autotestNote = note;
      c.chapter = 0;
      c.stage = q.get('stage') || 'prologue';
      c.recruited = ['elwin', 'glenn', 'nora', 'serin'];
      c.order = c.recruited.slice();
      for (const id of Object.keys(c.roster)) if (!c.recruited.includes(id)) delete c.roster[id];
      note('新游戏开始');
      flow.goStage(game);
      return;
    }
    if (mode === 'battle') { c.stage = 'battle'; game.transition(() => flow.startBattle(game)); }
    else if (mode === 'prep') { c.stage = 'prep'; flow.goStage(game); }
    else if (mode === 'story') { flow.playScripts(game, [q.get('id') || 'prologue'], () => flow.toTitle(game)); }
    else if (mode === 'stage') { c.stage = q.get('stage') || 'pre'; flow.goStage(game); }
  });
  return true;
}

boot().catch(fail);
