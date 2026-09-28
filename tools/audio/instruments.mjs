// 音色校准：node tools/audio/instruments.mjs
//   用同一段乐句（力度 v12、无混响）渲染每个音色，测积分响度与峰值，并给出让所有音色等响（目标 -20 LUFS）的 amp 建议值。
//   鼓组每种鼓按八分音符连击测量。作曲时轨道音量 vol 就可以按“角色”设置，而不必补偿音色本身的响度差异。
import { renderSong, INSTRUMENTS, DRUMS, gainToDb } from '../../src/core/synth.js';

const TARGET = -20;
const PHRASES = {
  bass: 'o2 l8 c c g c >c <c g c | a a >e <a >a <a >e <a |',
  mid: 'o4 l4 c e g >c | <b g e d | c2 e2 | g1 |',
  timp: 'o2 l4 d r <a r | >d r <a r |',
};
const range = { tri: 'bass', trisoft: 'bass', fbass: 'bass', lowstr: 'bass', pizz: 'bass', timp: 'timp' };

function measure(def) {
  const song = { id: 'cal', bpm: 120, loop: false, lufs: 0, ...def };
  // 关掉归一化：借 lufsRaw（归一化前测得）
  const r = renderSong(song);
  let pk = 0;
  for (let i = 0; i < r.length; i++) pk = Math.max(pk, Math.abs(r.left[i]), Math.abs(r.right[i]));
  return { lufs: r.lufsRaw, peak: gainToDb(pk) - r.gainDb };
}

console.log(`音色（同一乐句 v12，目标 ${TARGET} LUFS）`);
for (const [name, ins] of Object.entries(INSTRUMENTS)) {
  if (ins.engine === 'kit') continue;
  const phrase = PHRASES[range[name] || 'mid'];
  const m = measure({ tracks: [{ inst: name, mml: 'v12 ' + phrase, send: 0 }] });
  const sugg = ins.amp * Math.pow(10, (TARGET - m.lufs) / 20);
  console.log(`  ${name.padEnd(9)} ${m.lufs.toFixed(1).padStart(6)} LUFS  峰值 ${m.peak.toFixed(1).padStart(6)} dBFS  amp ${ins.amp} → 建议 ${sugg.toFixed(3)}`);
}
console.log(`\n鼓组（八分音符连击 v12，目标 ${TARGET} LUFS）`);
const KEYS = { kick: 'c', rim: 'c+', snare: 'd', msnare: 'd+', tomL: 'e', tomM: 'f', hat: 'f+', tomH: 'g', phat: 'g+', ohat: 'a', ride: 'a+', crash: 'b' };
for (const [kind, key] of Object.entries(KEYS)) {
  const m = measure({ tracks: [{ inst: 'kit', mml: `v12 o4 l8 [${key}]16`, send: 0 }] });
  const sugg = DRUMS[kind].gain * Math.pow(10, (TARGET - m.lufs) / 20);
  console.log(`  ${kind.padEnd(7)} ${m.lufs.toFixed(1).padStart(6)} LUFS  峰值 ${m.peak.toFixed(1).padStart(6)} dBFS  gain ${DRUMS[kind].gain} → 建议 ${sugg.toFixed(3)}`);
}
