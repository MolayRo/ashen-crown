// 混音平衡检查：node tools/audio/mix.mjs [id ...]
//   把每首曲子的每个声部单独渲染（同样的音量/声像/混响），测它演奏时的响度，给出相对整首混音的 dB。
//   另给出整首的低/中/高频段能量占比，用来发现“低音糊”“高频刺耳”。无法用耳朵听，就用这些数据调平衡。
import { SongRenderer } from '../../src/core/synth.js';
import { MUSIC } from '../../src/game/data/music.js';

const ids = process.argv.slice(2).filter((a) => !a.startsWith('-'));

function bands(L, R, sr, from, to) {
  // 一阶滤波器粗分三段：<250Hz、250~2500Hz、>2500Hz
  const a1 = Math.exp(-2 * Math.PI * 250 / sr), a2 = Math.exp(-2 * Math.PI * 2500 / sr);
  let l1 = 0, l2 = 0, eLow = 0, eMid = 0, eHigh = 0;
  for (let i = from; i < to; i++) {
    const x = (L[i] + R[i]) * 0.5;
    l1 = x + (l1 - x) * a1;           // < 250
    l2 = x + (l2 - x) * a2;           // < 2500
    eLow += l1 * l1; eMid += (l2 - l1) * (l2 - l1); eHigh += (x - l2) * (x - l2);
  }
  const tot = eLow + eMid + eHigh || 1;
  return [eLow / tot, eMid / tot, eHigh / tot].map((v) => Math.round(v * 100));
}

for (const id of ids.length ? ids : Object.keys(MUSIC)) {
  const def = MUSIC[id];
  const full = new SongRenderer(def);
  full.step(Infinity);
  const res = full.result;
  const from = res.loop ? res.loopStart : 0, to = res.loop ? res.loopEnd : res.length;
  const [lo, mid, hi] = bands(res.left, res.right, res.sr, from, to);
  console.log(`\n${id}（${def.name}）整首原始响度 ${res.lufsRaw.toFixed(1)} LUFS，频段能量 低${lo}% 中${mid}% 高${hi}%`);
  const rows = [];
  for (const tr of def.tracks) {
    const solo = new SongRenderer({ ...def, tracks: [tr] });
    solo.step(Infinity);
    const r = solo.result;
    rows.push([tr.name, tr.inst, r.lufsRaw - res.lufsRaw]);
  }
  rows.sort((a, b) => b[2] - a[2]);
  for (const [n, inst, d] of rows) console.log(`  ${n.padEnd(9)} @${inst.padEnd(9)} ${d >= 0 ? '+' : ''}${d.toFixed(1)} dB ${'#'.repeat(Math.max(0, Math.round(20 + d)))}`);
}
