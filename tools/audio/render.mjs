// 音频离线渲染 + 分析：node tools/audio/render.mjs [id ...] [--no-wav] [--sfx] [--music]
//   把曲目/音效渲染成 WAV（tools/audio/out/），并检查：NaN/Inf、采样峰值与 4 倍过采样真峰值、RMS、
//   积分响度 LUFS（BS.1770）、直流偏移、削波、循环接缝连续性（loopEnd 之后的延续 vs loopStart 之后）。
//   输出 out/report.md 与 out/report.json。我们无法用耳朵听，所以一切以这里的数据为准。
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderSong, renderSfx, measureLoudness, gainToDb, DEFAULT_SR, CEILING_DB } from '../../src/core/synth.js';
import { MUSIC } from '../../src/game/data/music.js';
import { SFX } from '../../src/game/data/sfx.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, 'out');
const args = process.argv.slice(2);
const flags = new Set(args.filter((a) => a.startsWith('--')));
let ids = args.filter((a) => !a.startsWith('--'));
const noWav = flags.has('--no-wav');
if (!ids.length) {
  if (!flags.has('--sfx')) ids.push(...Object.keys(MUSIC));
  if (!flags.has('--music')) ids.push(...Object.keys(SFX));
}

fs.mkdirSync(path.join(OUT, 'music'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'sfx'), { recursive: true });

function writeWav(file, L, R, sr, from = 0, to = L.length) {
  const n = to - from, buf = Buffer.alloc(44 + n * 4);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 4, 4); buf.write('WAVE', 8);
  buf.write('fmt ', 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
  buf.writeUInt32LE(sr, 24); buf.writeUInt32LE(sr * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34);
  buf.write('data', 36); buf.writeUInt32LE(n * 4, 40);
  for (let i = 0; i < n; i++) {
    const l = Math.max(-1, Math.min(1, L[from + i])), r = Math.max(-1, Math.min(1, R[from + i]));
    buf.writeInt16LE(Math.round(l * 32767), 44 + i * 4);
    buf.writeInt16LE(Math.round(r * 32767), 46 + i * 4);
  }
  fs.writeFileSync(file, buf);
}

function concat(parts) {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const out = new Float32Array(n);
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

// 4 倍过采样真峰值（窗函数 sinc 插值，24 抽头/相位）
const TP_TAPS = 12;
const TP_H = [1, 2, 3].map((ph) => {
  const h = [];
  for (let k = -TP_TAPS + 1; k <= TP_TAPS; k++) {
    const x = k - ph / 4;
    const sinc = Math.sin(Math.PI * x) / (Math.PI * x);
    const w = 0.5 + 0.5 * Math.cos(Math.PI * x / (TP_TAPS + 0.5));
    h.push(sinc * w);
  }
  return h;
});
function truePeak(X) {
  let pk = 0;
  const n = X.length;
  for (let i = TP_TAPS; i < n - TP_TAPS; i++) {
    const a = Math.abs(X[i]);
    if (a > pk) pk = a;
    if (a < pk * 0.5 && Math.abs(X[i + 1]) < pk * 0.5) continue; // 远低于峰值的地方不可能产生样间峰
    for (const h of TP_H) {
      let y = 0;
      for (let k = 0; k < h.length; k++) y += X[i - TP_TAPS + 1 + k] * h[k];
      if (Math.abs(y) > pk) pk = Math.abs(y);
    }
  }
  return pk;
}

function basicStats(L, R, from, to) {
  let pk = 0, ss = 0, dcL = 0, dcR = 0, clip = 0, bad = 0;
  for (let i = from; i < to; i++) {
    const l = L[i], r = R[i];
    if (!Number.isFinite(l) || !Number.isFinite(r)) { bad++; continue; }
    const a = Math.max(Math.abs(l), Math.abs(r));
    if (a > pk) pk = a;
    if (a >= 0.999) clip++;
    ss += l * l + r * r; dcL += l; dcR += r;
  }
  const n = Math.max(1, to - from);
  return { peakDb: gainToDb(pk), rmsDb: gainToDb(Math.sqrt(ss / (2 * n))), dcL: dcL / n, dcR: dcR / n, clip, bad };
}

// 循环接缝：玩家听到的是 …[loopEnd-1] → [loopStart]…；渲染时 loopEnd 之后还多渲染了 GUARD 个真实延续采样，
// 两者之差就是“跳转点与真实连续播放的差异”，应当 < -90 dB（浮点噪声级别）。
function seamStats(res) {
  const { left: L, right: R, loopStart: ls, loopEnd: le } = res;
  const guard = Math.min(256, res.length - le);
  let err = 0;
  for (let j = 0; j < guard; j++) err = Math.max(err, Math.abs(L[le + j] - L[ls + j]), Math.abs(R[le + j] - R[ls + j]));
  // 跳转处一阶差分 vs 附近 20ms 内一阶差分的最大值（点击检测）
  const jump = Math.max(Math.abs(L[ls] - L[le - 1]), Math.abs(R[ls] - R[le - 1]));
  let local = 0;
  const w = Math.round(res.sr * 0.02);
  for (let i = le - w; i < le - 1; i++) local = Math.max(local, Math.abs(L[i + 1] - L[i]), Math.abs(R[i + 1] - R[i]));
  for (let i = ls; i < ls + w; i++) local = Math.max(local, Math.abs(L[i + 1] - L[i]), Math.abs(R[i + 1] - R[i]));
  // 循环起点附近是否有声音（不应该是空白）
  const s = basicStats(L, R, ls, Math.min(res.length, ls + res.sr));
  return { errDb: gainToDb(err), jump, localMaxStep: local, jumpRatio: local > 0 ? jump / local : 0, startRmsDb: s.rmsDb };
}

const report = { sr: DEFAULT_SR, ceilingDb: CEILING_DB, music: [], sfx: [] };
const problems = [];
const f1 = (x) => (Number.isFinite(x) ? x.toFixed(1) : String(x));

for (const id of ids) {
  if (MUSIC[id]) {
    const def = MUSIC[id];
    const t0 = performance.now();
    const res = renderSong(def, DEFAULT_SR);
    const ms = performance.now() - t0;
    const from = res.loop ? res.loopStart : 0, to = res.loop ? res.loopEnd : res.length;
    const st = basicStats(res.left, res.right, 0, res.length);
    const lu = measureLoudness(res.left, res.right, res.sr, from, to);
    const tp = Math.max(truePeak(res.left), truePeak(res.right));
    const row = {
      id, name: def.name || '', loop: res.loop, key: def.key || '', bpm: def.bpm, meter: (def.meter || [4, 4]).join('/'),
      durSec: +res.duration.toFixed(2), introSec: +res.introSec.toFixed(2), loopSec: +res.loopSec.toFixed(2),
      bufSec: +(res.length / res.sr).toFixed(2), lufs: +lu.integrated.toFixed(2), maxMomentary: +lu.maxMomentary.toFixed(1),
      peakDb: +st.peakDb.toFixed(2), truePeakDb: +gainToDb(tp).toFixed(2), rmsDb: +st.rmsDb.toFixed(2),
      dc: +Math.max(Math.abs(st.dcL), Math.abs(st.dcR)).toExponential(1), clip: st.clip, nan: st.bad,
      gainDb: +res.gainDb.toFixed(2), limitDb: +res.limitDb.toFixed(2), voices: res.voices, renderMs: Math.round(ms),
      warnings: res.warnings,
    };
    if (res.loop) row.seam = seamStats(res);
    report.music.push(row);
    if (st.bad) problems.push(`${id}: ${st.bad} 个 NaN/Inf`);
    if (st.peakDb > -1) problems.push(`${id}: 峰值 ${f1(st.peakDb)} dBFS ≥ -1`);
    if (st.clip) problems.push(`${id}: ${st.clip} 个削波采样`);
    if (row.seam && row.seam.errDb > -90) problems.push(`${id}: 循环接缝误差 ${f1(row.seam.errDb)} dB`);
    if (row.seam && row.seam.startRmsDb < -60) problems.push(`${id}: 循环起点 1 秒几乎无声 (${f1(row.seam.startRmsDb)} dB)`);
    for (const w of res.warnings) problems.push(w);
    console.log(`${id.padEnd(9)} ${res.loop ? 'loop ' : 'jingle'} dur ${f1(res.duration)}s intro ${f1(res.introSec)} loop ${f1(res.loopSec)} | LUFS ${f1(lu.integrated)} peak ${f1(st.peakDb)} TP ${f1(gainToDb(tp))} rms ${f1(st.rmsDb)} | gain ${f1(res.gainDb)} lim ${f1(res.limitDb)} | seam ${row.seam ? f1(row.seam.errDb) + 'dB' : '-'} | ${res.voices} voices ${Math.round(ms)}ms`);
    if (!noWav) {
      const dir = path.join(OUT, 'music');
      writeWav(path.join(dir, `${id}.wav`), res.left, res.right, res.sr);
      if (res.loop) {
        // 模拟游戏里的循环播放：完整一遍 + 再绕两次循环点 + 淡出
        const ls = res.loopStart, le = res.loopEnd, sr = res.sr;
        const tailN = Math.min(le - ls, sr * 8);
        const mk = (X) => {
          const a = concat([X.subarray(0, le), X.subarray(ls, le), X.subarray(ls, ls + tailN)]);
          const f = Math.min(sr * 4, tailN);
          for (let i = 0; i < f; i++) a[a.length - 1 - i] *= i / f;
          return a;
        };
        const pl = mk(res.left), pr = mk(res.right);
        writeWav(path.join(dir, `${id}_play.wav`), pl, pr, sr);
        // 只听接缝：跳转前 3 秒 + 跳转后 3 秒
        const w = sr * 3;
        const sl = concat([res.left.subarray(le - w, le), res.left.subarray(ls, ls + w)]);
        const srr = concat([res.right.subarray(le - w, le), res.right.subarray(ls, ls + w)]);
        writeWav(path.join(dir, `${id}_seam.wav`), sl, srr, sr);
      }
    }
  } else if (SFX[id]) {
    const t0 = performance.now();
    const res = renderSfx({ id, ...SFX[id] }, DEFAULT_SR);
    const ms = performance.now() - t0;
    const st = basicStats(res.left, res.right, 0, res.length);
    const lu = measureLoudness(res.left, res.right, res.sr, 0, res.length);
    const tp = Math.max(truePeak(res.left), truePeak(res.right));
    const row = {
      id, durSec: +(res.length / res.sr).toFixed(3), peakDb: +st.peakDb.toFixed(2), truePeakDb: +gainToDb(tp).toFixed(2),
      rmsDb: +st.rmsDb.toFixed(1), maxMomentary: +lu.maxMomentary.toFixed(1), nan: st.bad, clip: st.clip, renderMs: +ms.toFixed(1),
    };
    report.sfx.push(row);
    if (st.bad) problems.push(`sfx ${id}: ${st.bad} 个 NaN/Inf`);
    if (st.peakDb > -1) problems.push(`sfx ${id}: 峰值 ${f1(st.peakDb)} dBFS ≥ -1`);
    console.log(`sfx ${id.padEnd(11)} ${row.durSec.toFixed(3)}s peak ${f1(st.peakDb)} TP ${f1(gainToDb(tp))} rms ${f1(st.rmsDb)} momentary ${f1(lu.maxMomentary)} | ${row.renderMs}ms`);
    if (!noWav) writeWav(path.join(OUT, 'sfx', `${id}.wav`), res.left, res.right, res.sr);
  } else {
    console.warn('未知 id：' + id);
  }
}

// 报告
const md = [];
md.push(`# 音频分析报告（${new Date().toISOString().slice(0, 19)}，渲染采样率 ${DEFAULT_SR} Hz）\n`);
if (report.music.length) {
  md.push('| id | 调/速度 | 前奏+循环(秒) | LUFS | 峰值 dBFS | 真峰值 dBTP | RMS | 限幅 dB | 接缝误差 dB | 跳变/邻域 | 声部 | 渲染 ms |');
  md.push('|---|---|---|---|---|---|---|---|---|---|---|---|');
  for (const r of report.music) {
    md.push(`| ${r.id} | ${r.key} ♩=${r.bpm} ${r.meter} | ${r.loop ? `${r.introSec}+${r.loopSec}` : `${r.durSec}（短曲）`} | ${r.lufs} | ${r.peakDb} | ${r.truePeakDb} | ${r.rmsDb} | ${r.limitDb} | ${r.seam ? r.seam.errDb.toFixed(1) : '-'} | ${r.seam ? r.seam.jumpRatio.toFixed(2) : '-'} | ${r.voices} | ${r.renderMs} |`);
  }
}
if (report.sfx.length) {
  md.push('\n| 音效 | 时长 s | 峰值 dBFS | 真峰值 | RMS | 最大瞬时响度 LUFS |');
  md.push('|---|---|---|---|---|---|');
  for (const r of report.sfx) md.push(`| ${r.id} | ${r.durSec} | ${r.peakDb} | ${r.truePeakDb} | ${r.rmsDb} | ${r.maxMomentary} |`);
}
md.push('\n## 问题\n');
md.push(problems.length ? problems.map((p) => '- ' + p).join('\n') : '无');
if (ids.length === Object.keys(MUSIC).length + Object.keys(SFX).length) {
  fs.writeFileSync(path.join(OUT, 'report.md'), md.join('\n') + '\n');
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify({ ...report, problems }, null, 1));
}
console.log(problems.length ? '\n问题：\n' + problems.join('\n') : '\n未发现问题');
process.exitCode = problems.length ? 1 : 0;
