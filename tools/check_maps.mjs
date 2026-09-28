// 检查章节地图：行宽、单位落点是否可站立、出击点、并导出给地图绘制器的 JSON
// 用法：node tools/check_maps.mjs [--print]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CHAPTERS } from '../src/game/data/chapters.js';
import { CLASSES } from '../src/game/data/classes.js';
import { CHARACTERS, BOSSES } from '../src/game/data/characters.js';
import { terrainOf } from '../src/game/data/terrain.js';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const print = process.argv.includes('--print');
let problems = 0;

for (const ch of CHAPTERS) {
  const w = ch.rows[0].length, h = ch.rows.length;
  const bad = ch.rows.findIndex((r) => r.length !== w);
  if (bad >= 0) { console.log(`[${ch.id}] 第 ${bad} 行宽度 ${ch.rows[bad].length} ≠ ${w}`); problems++; }
  const at = (x, y) => (ch.rows[y] || '')[x];
  const occupied = new Map();
  const check = (label, x, y, clsId) => {
    const c = at(x, y);
    if (c == null) { console.log(`[${ch.id}] ${label} 在地图外 (${x},${y})`); problems++; return; }
    const t = terrainOf(c, ch.theme);
    const mt = CLASSES[clsId].moveType;
    if (t.cost[mt] == null) { console.log(`[${ch.id}] ${label} 站在不可通行的 ${t.name} (${x},${y}) '${c}'`); problems++; }
    const k = x + ',' + y;
    if (occupied.has(k)) { console.log(`[${ch.id}] ${label} 与 ${occupied.get(k)} 重叠 (${x},${y})`); problems++; }
    occupied.set(k, label);
  };
  ch.deploy.forEach(([x, y], i) => check('出击点' + i, x, y, 'lord'));
  for (const u of ch.units) {
    const clsId = u.char ? CHARACTERS[u.char].cls : u.boss ? BOSSES[u.boss].cls : u.cls;
    check((u.char || u.boss || u.cls) + (u.diff ? '(' + u.diff.join('/') + ')' : ''), u.x, u.y, clsId);
  }
  for (const g of ch.reinforcements || []) for (const u of g.units) {
    const c = at(u.x, u.y);
    const t = terrainOf(c, ch.theme);
    if (t.cost[CLASSES[u.cls].moveType] == null) { console.log(`[${ch.id}] 增援 ${u.cls} 落点不可通行 (${u.x},${u.y})`); problems++; }
  }
  for (const k of Object.keys(ch.villages || {})) { const [x, y] = k.split(',').map(Number); if (at(x, y) !== 'V') { console.log(`[${ch.id}] 村庄 ${k} 不是 V`); problems++; } }
  for (const k of Object.keys(ch.chests || {})) { const [x, y] = k.split(',').map(Number); if (at(x, y) !== 'C') { console.log(`[${ch.id}] 宝箱 ${k} 不是 C`); problems++; } }
  if (print) {
    console.log(`\n== ${ch.id} ${ch.name} ${w}x${h} (${ch.theme})`);
    const marks = new Map();
    ch.deploy.forEach(([x, y], i) => marks.set(x + ',' + y, String(i)));
    for (const u of ch.units) marks.set(u.x + ',' + u.y, u.char ? '@' : u.boss ? 'B' : 'e');
    console.log('    ' + Array.from({ length: w }, (_, i) => (i % 10)).join(''));
    ch.rows.forEach((r, y) => {
      let s = '';
      for (let x = 0; x < w; x++) s += marks.get(x + ',' + y) || r[x];
      console.log(String(y).padStart(3) + ' ' + s);
    });
  }
  // 导出给绘制器
  const out = path.join(ROOT, 'tools', 'maps');
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, ch.id + '.json'), JSON.stringify({ id: ch.id, theme: ch.theme, rows: ch.rows }, null, 1));
}
console.log(problems ? `发现 ${problems} 个问题` : '地图检查通过');
process.exit(problems ? 1 : 0);
