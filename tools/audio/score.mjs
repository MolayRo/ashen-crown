// 乐谱检查：node tools/audio/score.mjs [id ...] [-v]
//   · MML 解析警告（小节线未对齐、未知字符…）、各声部长度与循环点一致性
//   · 和声：song.melody 列出的旋律声部，强拍（4/4 第 1、3 拍；3/4 第 1 拍；6/8 第 1、4 个八分音符）起音必须是当时和弦的和弦音
//     跨强拍延留到新和弦上的音（倚音/延留音）单独列出供人工确认
//   · 每个声部的音域、全曲时长、循环长度
import { compileSong, TPQ } from '../../src/core/synth.js';
import { MUSIC, chart } from '../../src/game/data/music.js';

const args = process.argv.slice(2);
const verbose = args.includes('-v');
const ids = args.filter((a) => !a.startsWith('-'));
const NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
const nn = (m) => NAMES[((m % 12) + 12) % 12] + (Math.floor(m / 12) - 1);

let errors = 0, warns = 0;
for (const id of ids.length ? ids : Object.keys(MUSIC)) {
  const def = MUSIC[id];
  const comp = compileSong(def);
  const [num, den] = def.meter || [4, 4];
  const barTicks = comp.barTicks;
  const beatUnit = den === 8 ? TPQ / 2 : TPQ;
  const strongStep = den === 8 ? (num % 3 === 0 ? TPQ * 1.5 : barTicks) : num === 4 ? TPQ * 2 : barTicks;
  const lines = [];
  const pos = (t) => `${Math.floor(t / barTicks) + 1}:${(t % barTicks) / beatUnit + 1}`;
  for (const w of comp.warnings) { lines.push('  ✗ ' + w); errors++; }
  let chs = null;
  if (def.chords) {
    chs = chart(def.chords, barTicks / beatUnit, beatUnit);
    const chEnd = chs.length ? chs[chs.length - 1].t + chs[chs.length - 1].len : 0;
    if (chEnd !== comp.endTick) { lines.push(`  ✗ 和弦进行长度 ${chEnd / barTicks} 小节 ≠ 乐曲 ${comp.endTick / barTicks} 小节`); errors++; }
  }
  const chordAt = (t) => { if (!chs) return null; for (const c of chs) if (t >= c.t && t < c.t + c.len) return c; return null; };
  let strong = 0, bad = 0;
  for (const trk of comp.tracks) {
    const tr = trk.tr, name = tr.name || String(trk.ti);
    let lo = 999, hi = -999;
    for (const ev of trk.events) for (const m of ev.notes) { lo = Math.min(lo, m + (tr.trans || 0)); hi = Math.max(hi, m + (tr.trans || 0)); }
    if (verbose && trk.events.length && tr.inst !== 'kit') lines.push(`  · ${name.padEnd(9)} @${tr.inst} 音域 ${nn(lo)}~${nn(hi)}  ${trk.events.length} 个音符`);
    if (!chs || !(def.melody || []).includes(name)) continue;
    for (const ev of trk.events) {
      const m = ev.notes[0] + (tr.trans || 0);
      const pcs = [m % 12];
      // 起音在强拍
      if (ev.tick % strongStep === 0) {
        strong++;
        const c = chordAt(ev.tick);
        if (c && !c.ch.pcs.includes(pcs[0])) { bad++; errors++; lines.push(`  ✗ ${name} ${pos(ev.tick)} ${nn(m)} 不在 ${c.ch.sym} 内`); }
      }
      // 延留过强拍、且那里换了和弦
      for (let t = Math.ceil((ev.tick + 1) / strongStep) * strongStep; t < ev.tick + ev.len; t += strongStep) {
        const c0 = chordAt(ev.tick), c = chordAt(t);
        if (c && c0 && c !== c0 && c.ch.sym !== c0.ch.sym && !c.ch.pcs.includes(pcs[0])) {
          warns++; lines.push(`  △ ${name} ${nn(m)} 从 ${pos(ev.tick)} 延留到 ${pos(t)} 的 ${c.ch.sym}（非和弦音，确认是否为有意的延留）`);
        }
      }
      // 连奏滑音的目标音
      if (ev.legato) for (const [off, mm] of ev.legato) {
        const t = ev.tick + off;
        if (t % strongStep === 0) {
          strong++;
          const c = chordAt(t);
          if (c && !c.ch.pcs.includes(((mm + (tr.trans || 0)) % 12 + 12) % 12)) { bad++; errors++; lines.push(`  ✗ ${name} ${pos(t)} ${nn(mm)}（连奏）不在 ${c.ch.sym} 内`); }
        }
      }
    }
  }
  const head = `${id.padEnd(9)} ${def.key || ''} ♩=${def.bpm} ${num}/${den}  ${def.loop ? `前奏 ${comp.introSec.toFixed(1)}s + 循环 ${comp.loopSec.toFixed(1)}s（${(comp.endTick - (comp.loopTick || 0)) / barTicks} 小节）` : `短曲 ${comp.duration.toFixed(2)}s`}`
    + (chs && def.melody ? `  强拍旋律音 ${strong} 个，非和弦音 ${bad} 个` : '');
  console.log(head);
  for (const l of lines) console.log(l);
}
console.log(`\n错误 ${errors}，需确认 ${warns}`);
process.exitCode = errors ? 1 : 0;
