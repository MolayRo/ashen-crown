// 数据一致性检查：剧情脚本引用、说话人/表情、背景、曲目、音效、素材帧名、字库覆盖
// 用法：node tools/tests/validate.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CHAPTERS } from '../../src/game/data/chapters.js';
import { CLASSES } from '../../src/game/data/classes.js';
import { ITEMS } from '../../src/game/data/items.js';
import { PLAYABLE, PORTRAIT_EXPR, EXPRESSIONS, CHARACTERS, BOSSES } from '../../src/game/data/characters.js';
import { RAW, getScript } from '../../src/game/story/index.js';
import { defaultBattleSet } from '../../src/game/battle.js';

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const errors = [];
const warns = [];
const err = (m) => errors.push(m);
const warn = (m) => warns.push(m);
const readJSON = (p) => { try { return JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8')); } catch (e) { return null; } };

const BG_IDS = ['festival', 'throne_fire', 'passage', 'forest_night', 'village_burning', 'village_after', 'capital_square', 'river_bridge',
  'refugee_camp', 'monastery_ext', 'chapel', 'snow_road', 'snow_fort', 'war_camp', 'castle_gate', 'throne_dawn', 'coronation', 'capital_dawn'];

// ---- 章节引用的脚本 ----
const need = new Set(['prologue', 'interlude_proclaim', 'ending', 'gameover_elwin', 'gameover_martha']);
for (const ch of CHAPTERS) {
  for (const k of ['pre', 'post', 'after']) if (ch[k]) need.add(ch[k]);
  for (const ev of ch.events || []) if (ev.script) need.add(ev.script);
  for (const g of ch.reinforcements || []) if (g.warn) need.add(g.warn);
  for (const v of Object.values(ch.villages || {})) if (v.script) need.add(v.script);
}
need.add('ch4_boss_retreat');
for (const id of PLAYABLE) if (id !== 'elwin') { need.add('death_' + id); need.add('retreat_' + id); }
for (const id of need) if (!RAW[id]) err(`缺少剧情脚本 ${id}`);

// ---- 曲目与音效登记 ----
let musicIds = null, sfxIds = null;
try { const m = await import('../../src/game/data/music.js'); musicIds = new Set(Object.keys(m.MUSIC || m.TRACKS || m.default || {})); } catch (e) { warn('无法读取 music.js：' + e.message); }
try { const s = await import('../../src/game/data/sfx.js'); sfxIds = new Set(Object.keys(s.SFX || s.default || {})); } catch (e) { warn('无法读取 sfx.js：' + e.message); }
const usedMusic = new Set(['title', 'prep', 'enemy', 'boss', 'ending', 'victory', 'gameover', 'chapter']);
for (const ch of CHAPTERS) { usedMusic.add(ch.music.player); usedMusic.add(ch.music.enemy); }
const usedSfx = new Set(['cursor', 'confirm', 'cancel', 'select', 'error', 'step', 'step_horse', 'wing', 'sword', 'lance', 'axe', 'bow', 'throw',
  'fire', 'thunder', 'dark', 'light', 'hit', 'hit_heavy', 'miss', 'crit', 'nodmg', 'death', 'heal', 'levelup', 'statup', 'recruit', 'chest', 'door',
  'item', 'gold', 'visit', 'phase', 'warn', 'burn', 'text', 'save', 'page']);

// ---- 剧情节点检查 ----
const portraits = readJSON('assets/portraits.json');
function walk(nodes, id) {
  for (const n of nodes) {
    if (n.t === 'if') { for (const b of n.branches) walk(b.body, id); if (n.else) walk(n.else, id); continue; }
    if (n.t === 'unknown') err(`[${id}] 未知指令 @${n.cmd}（第 ${n.line} 行）`);
    if (n.t === 'bg' && !['map', 'black'].includes(n.id) && !BG_IDS.includes(n.id)) err(`[${id}] 未知背景 ${n.id}`);
    if (n.t === 'music' && n.id !== 'stop') usedMusic.add(n.id);
    if (n.t === 'sfx') usedSfx.add(n.id);
    if (n.t === 'show' || n.t === 'say') {
      const pid = n.id;
      if (n.t === 'say' && !pid) { err(`[${id}] 说话人“${n.name}”没有对应头像 id`); continue; }
      if (!PORTRAIT_EXPR[pid]) { err(`[${id}] 未知人物 id ${pid}`); continue; }
      const expr = n.expr || 'normal';
      const allowed = EXPRESSIONS[PORTRAIT_EXPR[pid]];
      if (!allowed.includes(expr)) warn(`[${id}] ${pid} 没有表情 ${expr}（将退回 normal）`);
      if (portraits && !portraits.frames[`${pid}_${allowed.includes(expr) ? expr : 'normal'}`]) err(`[${id}] 头像帧缺失 ${pid}_${expr}`);
    }
  }
}
for (const id of Object.keys(RAW)) walk(getScript(id), id);
if (musicIds) for (const m of usedMusic) if (!musicIds.has(m)) err(`曲目未登记 ${m}`);
if (sfxIds) for (const s of usedSfx) if (!sfxIds.has(s)) err(`音效未登记 ${s}`);

// ---- 头像完整性 ----
if (portraits) {
  for (const [pid, set] of Object.entries(PORTRAIT_EXPR)) {
    for (const e of EXPRESSIONS[set]) for (const v of ['', '_talk', '_blink']) if (!portraits.frames[`${pid}_${e}${v}`]) err(`头像缺帧 ${pid}_${e}${v}`);
    if (!portraits.frames[`${pid}_mini`]) err(`缺小头像 ${pid}_mini`);
  }
} else warn('portraits.json 尚未生成');

// ---- 地图小人 ----
const units = readJSON('assets/units.json');
if (units) {
  const models = new Set(Object.values(CLASSES).map((c) => c.model));
  for (const m of models) for (const t of ['blue', 'red', 'green', 'grey']) for (const a of ['idle', 'down', 'up', 'side']) {
    if (!units.anims[`${m}_${t}_${a}`]) err(`地图小人缺动画 ${m}_${t}_${a}`);
  }
} else warn('units.json 尚未生成');

// ---- 战斗动画 ----
const bu = readJSON('assets/battle_units.json');
if (bu) {
  const sets = new Set(PLAYABLE.map((id) => CHARACTERS[id].battle));
  for (const b of Object.values(BOSSES)) sets.add(b.battle);
  for (const ch of CHAPTERS) {
    for (const u of ch.units) if (u.cls) sets.add(u.battle || defaultBattleSet(u.cls, u.team || 'enemy'));
    for (const g of ch.reinforcements || []) for (const u of g.units) sets.add(defaultBattleSet(u.cls, 'enemy'));
  }
  for (const s of sets) {
    if (!bu.sets || !bu.sets[s]) { err(`战斗动画缺组 ${s}`); continue; }
    if (!bu.anims[`${s}_idle`]) err(`战斗动画缺 ${s}_idle`);
    const staffUser = bu.sets[s].type === 'staff';
    if (s !== 'martha' && !bu.anims[`${s}_${staffUser ? 'staff' : 'attack'}`]) err(`战斗动画缺 ${s}_${staffUser ? 'staff' : 'attack'}`);
    if (!bu.anims[`${s}_dodge`]) warn(`战斗动画缺 ${s}_dodge`);
  }
} else warn('battle_units.json 尚未生成');

// ---- 图标 ----
const icons = readJSON('assets/icons.json');
if (icons) { for (const [id, d] of Object.entries(ITEMS)) if (!icons.frames[d.icon]) err(`缺物品图标 ${d.icon}（${id}）`); }
else warn('icons.json 尚未生成');

// ---- 地图图像 ----
for (const ch of CHAPTERS) for (const f of ['0', '1', '2', 'alt']) if (!fs.existsSync(path.join(ROOT, 'assets/maps', `${ch.id}_${f}.png`))) err(`缺地图图像 ${ch.id}_${f}.png`);
for (const b of BG_IDS) if (!fs.existsSync(path.join(ROOT, 'assets/bg', b + '.png'))) err(`缺背景 ${b}.png`);

for (const w of warns) console.log('警告：' + w);
for (const e of errors) console.log('错误：' + e);
console.log(`检查完成：错误 ${errors.length}，警告 ${warns.length}`);
process.exit(errors.length ? 1 : 0);
