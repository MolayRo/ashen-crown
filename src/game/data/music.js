// 《灰烬王冠》全部曲目（原创，程序合成）。
// 记谱：MML（语法见 src/core/synth.js 顶部），伴奏声部由下方的和弦工具按和弦进行生成，保证和声正确。
// 每首曲子的 chords 字段是完整和弦进行（按小节），tools/audio/score.mjs 用它检查旋律强拍是否落在和弦音上。
//
// “灰烬王冠主题”（D 小调 8 小节）：A. A D E | F— E D | D. C B♭ D | C♯. D E — …
//   title 以圆号完整陈述（庄严进行曲），final 以小号在快速弦乐下强奏并移到 E 小调再回 D 小调，
//   ending 变为 D 大调（F→F♯）完整再现；chapter 短曲只用它的前两小节“头”。
import { TPQ } from '../../core/synth.js';

// ============================================================
// 作曲工具
// ============================================================
const ROOT_PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
const QUALITY = {
  '': [0, 4, 7], m: [0, 3, 7], dim: [0, 3, 6], aug: [0, 4, 8], sus2: [0, 2, 7], sus4: [0, 5, 7],
  7: [0, 4, 7, 10], maj7: [0, 4, 7, 11], m7: [0, 3, 7, 10], m7b5: [0, 3, 6, 10], dim7: [0, 3, 6, 9],
  6: [0, 4, 7, 9], m6: [0, 3, 7, 9], add9: [0, 4, 7, 14], madd9: [0, 3, 7, 14], 9: [0, 4, 7, 10, 14],
  5: [0, 7], '7sus4': [0, 5, 7, 10], mM7: [0, 3, 7, 11], '7b9': [0, 4, 7, 10, 13],
};
const acc = (c) => (c === '#' ? 1 : c === 'b' ? -1 : 0);

export function parseChord(sym) {
  const m = /^([A-G])([#b]?)([^/]*)(?:\/([A-G])([#b]?))?$/.exec(sym.trim());
  if (!m) throw new Error('无法解析和弦 ' + sym);
  const ivs = QUALITY[m[3]];
  if (!ivs) throw new Error('未知和弦性质 ' + sym);
  const root = (ROOT_PC[m[1]] + acc(m[2]) + 12) % 12;
  const bass = m[4] ? (ROOT_PC[m[4]] + acc(m[5]) + 12) % 12 : root;
  return { sym, root, ivs, bass, pcs: [...new Set(ivs.map((i) => (root + i) % 12))] };
}

// 和弦进行："Dm | Bb | Gm A | Dm"，| 分小节，同小节多个和弦平分（或写 Gm:3 A:1 指定拍数），% 延续上一个和弦
export function chart(str, beats = 4, unit = TPQ) {
  const out = [];
  let t = 0, prev = null;
  for (const bar of str.split('|').map((s) => s.trim()).filter(Boolean)) {
    const items = bar.split(/\s+/).map((tk) => { const [s, d] = tk.split(':'); return { s, d: d ? +d * unit : 0 }; });
    const fixed = items.reduce((a, x) => a + x.d, 0), free = items.filter((x) => !x.d).length;
    const each = free ? (beats * unit - fixed) / free : 0;
    for (const x of items) {
      const len = x.d || each;
      const ch = x.s === '%' ? prev : parseChord(x.s);
      out.push({ t, len, ch });
      prev = ch; t += len;
    }
  }
  return out;
}

const NAMES = ['c', 'c+', 'd', 'd+', 'e', 'f', 'f+', 'g', 'g+', 'a', 'a+', 'b'];
const LEN = { 192: '1', 144: '2.', 96: '2', 72: '4.', 48: '4', 36: '8.', 24: '8', 18: '16.', 12: '16', 6: '32', 64: '3', 32: '6', 16: '12', 8: '24' };
const lenStr = (t) => LEN[t] || '%' + t;
const nm = (m) => NAMES[((m % 12) + 12) % 12];
const oc = (m) => Math.floor(m / 12) - 1;

// [{m: midi | [midi…] | null, len, v}] → MML（绝对八度）
export function toMML(items) {
  const out = [];
  let o = null, vel = null;
  for (const it of items) {
    if (it.v != null && it.v !== vel) { out.push('v' + it.v); vel = it.v; }
    const L = lenStr(it.len);
    if (it.m == null) out.push('r' + L);
    else if (Array.isArray(it.m)) out.push('{' + it.m.map((m) => 'o' + oc(m) + nm(m)).join(' ') + '}' + L);
    else { if (oc(it.m) !== o) { o = oc(it.m); out.push('o' + o); } out.push(nm(it.m) + L); }
  }
  return out.join(' ');
}

// 声部型：R 根音(或 slash 低音) T 三音 F 五音 S 七音(无则八度) O 高八度根音 N 九音 X 休止 H 延长上一音
//   后缀 + / - 升降八度，数字=时值（缺省用 len），! 重音。例："R8 R8 O8 R8 F8 R8 O8 R8"
//   (n) = 根音上方 n 个半音（半音邻音等），例："R16 R16 (1)16 R16"
function parsePat(pat, dlen) {
  return pat.trim().split(/\s+/).map((tk) => {
    const m = /^(\([+-]?\d+\)|[RTFSONXHB])([+-]*)(\d*)(\.?)(!?)$/.exec(tk);
    if (!m) throw new Error('无法解析声部型 ' + tk);
    let len = m[3] ? Math.round(TPQ * 4 / +m[3]) : dlen;
    if (m[4]) len = Math.round(len * 1.5);
    const shift = [...m[2]].reduce((a, c) => a + (c === '+' ? 12 : -12), 0);
    return { d: m[1], shift, len, accent: !!m[5] };
  });
}
function degree(ch, d, rootM, bassM) {
  const iv = ch.ivs;
  if (d[0] === '(') return rootM + parseInt(d.slice(1), 10);
  switch (d) {
    case 'R': return rootM;
    case 'B': return bassM;
    case 'T': return rootM + (iv[1] ?? 4);
    case 'F': return rootM + (iv.length >= 3 ? iv[2] : iv[1] ?? 7);
    case 'S': return rootM + (iv.length >= 4 && iv[3] < 12 ? iv[3] : 12);
    case 'O': return rootM + 12;
    case 'N': return rootM + 14;
    default: return null;
  }
}
const place = (pc, lo) => lo + ((pc - lo) % 12 + 12) % 12;

// 按和弦生成分解/贝斯声部。opts: { pat, lo 根音最低 MIDI, v 力度, len 缺省时值, slash 用斜线低音当 R, restart:'chord'|'bar' }
export function line(chartStr, opts = {}) {
  const beats = opts.beats || 4, unit = opts.unit || TPQ;
  const ch = typeof chartStr === 'string' ? chart(chartStr, beats, unit) : chartStr;
  const pat = parsePat(opts.pat || 'R4', opts.len || TPQ);
  const lo = opts.lo ?? 40, v = opts.v ?? 11;
  const items = [];
  for (const seg of ch) {
    const rootM = place(opts.slash ? seg.ch.bass : seg.ch.root, lo);
    const rootReal = opts.slash ? place(seg.ch.root, rootM - 11) : rootM; // slash 时和弦根音取低音之下最近的
    let t = 0, k = 0;
    while (t < seg.len) {
      const p = pat[k % pat.length];
      const len = Math.min(p.len, seg.len - t);
      if (p.d === 'H' && items.length && items[items.length - 1].m != null) items[items.length - 1].len += len;
      else if (p.d === 'X' || p.d === 'H') items.push({ m: null, len });
      else {
        const base = p.d === 'R' ? rootM : p.d[0] === '(' && opts.slash ? rootM + parseInt(p.d.slice(1), 10) : degree(seg.ch, p.d, rootReal, rootM);
        items.push({ m: base + p.shift, len, v: Math.min(15, v + (p.accent ? 2 : 0)) });
      }
      t += len; k++;
    }
  }
  return 'v' + v + ' ' + toMML(items);
}

// 和弦铺底：声部进行最小移动的排列。opts: { lo, hi, n 声部数, v, rhythm "2 4 r4"（循环）, spread 开放排列 }
function voicingCands(ch, n, lo, hi, spread) {
  let ivs = [...new Set(ch.ivs.map((i) => i % 12))];
  if (ivs.length > n) ivs = n === 3 && ivs.length >= 4 ? [ivs[0], ivs[1], ivs[3]] : ivs.slice(0, n); // 三声部七和弦省略五音
  const pc = (m, iv) => (((m - ch.root - iv) % 12) + 12) % 12 === 0;
  const cands = [];
  for (let r = 0; r < ivs.length; r++) {
    const rot = ivs.slice(r).concat(ivs.slice(0, r));
    for (let start = lo; start < lo + 12; start++) {
      if (!pc(start, rot[0])) continue;
      const notes = [start];
      for (let k = 1; k < rot.length; k++) {
        let m = notes[k - 1] + 1;
        while (!pc(m, rot[k])) m++;
        notes.push(m);
      }
      for (let k = 0; notes.length < n; k++) notes.push(notes[k] + 12); // 声部不够：自下而上高八度重复
      if (spread && notes.length >= 3) { notes[notes.length - 2] -= 12; notes.sort((a, b) => a - b); }
      for (const shift of [0, 12]) {
        const vv = notes.map((x) => x + shift);
        if (vv[0] >= lo && vv[vv.length - 1] <= hi) cands.push(vv);
      }
    }
  }
  return cands;
}
export function pad(chartStr, opts = {}) {
  const beats = opts.beats || 4, unit = opts.unit || TPQ;
  const ch = typeof chartStr === 'string' ? chart(chartStr, beats, unit) : chartStr;
  const lo = opts.lo ?? 55, hi = opts.hi ?? 79, n = opts.n ?? 3, v = opts.v ?? 10;
  const rhythm = opts.rhythm ? opts.rhythm.trim().split(/\s+/).map((tk) => {
    const m = /^(r?)(\d+)(\.?)$/.exec(tk);
    let len = Math.round(TPQ * 4 / +m[2]); if (m[3]) len = Math.round(len * 1.5);
    return { rest: !!m[1], len };
  }) : null;
  let prev = null;
  const items = [];
  for (const seg of ch) {
    const cands = voicingCands(seg.ch, n, lo, hi, opts.spread);
    if (!cands.length) throw new Error(`和弦 ${seg.ch.sym} 在 ${lo}~${hi} 内排不下 ${n} 个声部`);
    let best = cands[0], bestD = Infinity;
    const center = (lo + hi) / 2;
    for (const c of cands) {
      const d = prev ? c.reduce((a, x, i) => a + Math.abs(x - prev[Math.min(i, prev.length - 1)]), 0)
        : Math.abs(c.reduce((a, x) => a + x, 0) / c.length - center);
      if (d < bestD) { bestD = d; best = c; }
    }
    prev = best;
    if (!rhythm) { items.push({ m: best, len: seg.len, v }); continue; }
    let t = 0, k = 0;
    while (t < seg.len) {
      const r = rhythm[k++ % rhythm.length];
      const len = Math.min(r.len, seg.len - t);
      items.push(r.rest ? { m: null, len } : { m: best, len, v });
      t += len;
    }
  }
  return 'v' + v + ' ' + toMML(items);
}

// 鼓：beat('s', [['X..x x... X..x x.xx', 4], 'L', ...]) —— X=15 x=11 o=7 g=5 1~9=7~15 . 休止
const DRUM_NOTE = { k: 'c', r: 'c+', s: 'd', m: 'd+', t: 'e', u: 'f', h: 'f+', i: 'g', p: 'g+', o: 'a', y: 'a+', c: 'b' };
export function beat(drum, segs, step = 16) {
  const note = DRUM_NOTE[drum];
  const tl = Math.round(TPQ * 4 / step);
  const out = ['o4'];
  let vel = null, rest = 0;
  const flush = () => { if (rest) { out.push('r%' + rest); rest = 0; } };
  for (const sg of segs) {
    if (sg === 'L') { flush(); out.push('L'); continue; }
    const [pat, times = 1] = sg;
    const cells = pat.replace(/\s+/g, '');
    for (let r = 0; r < times; r++) {
      for (const c of cells) {
        let vv = null;
        if (c === 'X') vv = 15; else if (c === 'x') vv = 11; else if (c === 'o') vv = 7; else if (c === 'g') vv = 5;
        else if (c >= '1' && c <= '9') vv = 6 + +c;
        if (vv == null) { rest += tl; continue; }
        flush();
        if (vv !== vel) { out.push('v' + vv); vel = vv; }
        out.push(note + '%' + tl);
      }
    }
  }
  flush();
  return out.join(' ');
}

const bar4 = (n) => 'r1 '.repeat(n);                       // 4/4 整小节休止
const barsT = (n, ticks) => `r%${ticks} `.repeat(n);        // 任意拍号整小节休止
const roll = (note, n, v0, v1, len = 32) => {               // 定音鼓/军鼓滚奏（渐强）
  const out = [];
  for (let i = 0; i < n; i++) out.push(`v${Math.round(v0 + (v1 - v0) * i / Math.max(1, n - 1))} ${note}${len}`);
  return out.join(' ');
};

const E16 = '................';
const kitT = (name, drum, segs, o = {}) => ({
  name, inst: 'kit', vol: o.vol ?? 0.7, pan: o.pan ?? 0, send: o.send ?? 0.14, human: o.human ?? 0, mml: beat(drum, segs, o.step || 16),
});
const M34 = { beats: 3 };            // 3/4 拍
const M68 = { beats: 6, unit: 24 };  // 6/8 拍（以八分音符为单位）

// ============================================================
// 主题动机（D 小调，o4 起，8 小节）
// ============================================================
const THEME = `o4 a4. a8 >d4 e4 | f2. e8 d8 | d4. c8 <b-4 >d4 | c+4. d8 e2 |
  <a4. a8 >d4 e4 | f4. g8 a4 f4 | g4. f8 e4 c+4 | d2. r4 |`;
// 同一主题的 D 大调版本（结局）
const THEME_MAJ = `o4 a4. a8 >d4 e4 | f+2. e8 d8 | d4. c+8 <b4 >d4 | c+4. d8 e2 |
  <a4. a8 >d4 e4 | f+4. g8 a4 f+4 | g4. f+8 e4 c+4 | d1 |`;

// ============================================================
// 1. title 标题：庄严而哀伤的进行曲
//    D 小调 ♩=76 4/4 · 前奏 2 小节 + 循环 24 小节（A 圆号主题 / B 关系大调弦乐 / A' 小号+圆号+小提琴强奏）
// ============================================================
const TI_IN = 'Dm | Dm';
const TI_A = 'Dm | Bb | Gm | A | Dm | F/C | Gm A | Dm';
const TI_B = 'Bb | C | F | Dm | Gm | C | Bb | A';
const TI_B_MEL = `o5 d2 f4 d4 | e2 g4 e4 | f4. g8 a2 | a4 g8 f8 d2 | b-4. a8 g2 | e4. f8 g2 | f4. e8 d2 | e4. d8 c+2 |`;
const title = {
  name: '灰烬王冠', key: 'D 小调', bpm: 76, loop: true,
  desc: '庄严哀伤的进行曲：圆号陈述主题，军鼓与定音鼓送葬般的步伐，副歌转关系大调由弦乐歌唱，再由小号全奏主题。',
  reverb: { size: 0.8, damp: 0.45, wet: 0.34 }, send: 0.3,
  chords: [TI_IN, TI_A, TI_B, TI_A].join(' | '), melody: ['horn', 'strlead', 'trumpet'],
  tracks: [
    { name: 'horn', inst: 'horn', vol: 1, pan: -0.12, send: 0.32,
      mml: `r1 | r1 | L v12 ${THEME} v9 o4 f1 | g1 | a1 | a1 | b-1 | g1 | f1 | e1 | v9 k-12 ${THEME} k0` },
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.12, send: 0.3,
      mml: `r1 | r1 | L ${bar4(16)} v12 ${THEME}` },
    { name: 'strlead', inst: 'strlead', vol: 0.8, pan: 0.05, send: 0.34,
      mml: `r1 | r1 | L ${bar4(8)} v12 ${TI_B_MEL} v10 k12 ${THEME} k0` },
    { name: 'pad', inst: 'strings', vol: 0.35, send: 0.35,
      mml: `r1 ${pad('Dm', { lo: 50, hi: 69, v: 7 })} L ${pad(TI_A, { lo: 53, hi: 72, v: 8 })} ${pad(TI_B, { lo: 53, hi: 72, v: 7 })} ${pad(TI_A, { lo: 50, hi: 74, n: 4, v: 10, spread: true })}` },
    { name: 'bass', inst: 'lowstr', vol: 0.7, pan: -0.05, send: 0.22,
      mml: `v9 o2 {d a}1 | v11 {d a}1 | L ${line(TI_A, { pat: 'R2 F-2', lo: 38, v: 11, slash: true })} ${line(TI_B, { pat: 'R1', lo: 38, v: 10, slash: true })} ${line(TI_A, { pat: 'R4. R8 F-4 F-4', lo: 38, v: 12, slash: true })}` },
    { name: 'harp', inst: 'harp', vol: 0.45, pan: 0.3, send: 0.35,
      mml: `r1 | r1 | L ${line(TI_A, { pat: 'R8 F8 O8 T+8 O8 F8 R8 F8', lo: 50, v: 8 })} ${line(TI_B, { pat: 'R8 F8 O8 T+8 F+8 T+8 O8 F8', lo: 50, v: 9 })} ${line(TI_A, { pat: 'R8 F8 O8 T+8 O8 F8 R8 F8', lo: 50, v: 10 })}` },
    { name: 'timp', inst: 'timp', vol: 0.5, pan: 0.08, send: 0.3,
      mml: `o2 ${roll('d', 32, 4, 12)} | v13 d4 r8 <a8 >d4 r4 |
        L v11 d4 r2. | r1 | r1 | <a4 r4 a4 r4 | >d4 r2. | r1 | r2 <a4 a8 a8 | >d4 r2. |
        ${bar4(7)} <${roll('a', 32, 3, 12)} > |
        v13 d4 r4 d4 r4 | r1 | r1 | <a4 r4 a4 a4 | >d4 r4 d4 r4 | r1 | r2 <a4 a8 a8 | >d2 r2 |` },
    kitT('snare', 'm', [[E16, 1], ['x..g x... x..g x.oo', 1], 'L', ['o..g o... o..g o.gg', 8], [E16, 7], ['gggg oooo xxxx XXXX', 1], ['X..x X... X..x X.xx', 7], ['X..x X... XxxX XXXX', 1]], { vol: 0.5, pan: -0.15, send: 0.2 }),
    kitT('cym', 'c', [[E16, 2], 'L', ['o...............', 1], [E16, 15], ['X...............', 1], [E16, 7]], { vol: 0.4, pan: 0.25, send: 0.3 }),
    { name: 'bell', inst: 'bell', vol: 0.4, pan: 0.2, send: 0.4,
      mml: `r1 | r1 | L ${bar4(16)} v10 o5 d1 | r1 | r1 | r1 | d1 | r1 | r1 | {<a >d}1 |` },
  ],
};

// ============================================================
// 2. sad 逃亡/悲伤：缓慢稀疏，弦乐与方波
//    B 小调 ♩=72 3/4 · 前奏 2 小节 + 循环 24 小节（a 12.5% 方波独奏带回声 / b 弦乐歌唱+方波三度 / a' 长笛+弦乐低八度）
// ============================================================
const SA_IN = 'Bm | Bm';
const SA_A = 'Bm | G | Em | F# | Bm | G | Em:2 F#:1 | Bm';
const SA_B = 'G | D/F# | Em | Bm | G | D | Em | F#';
const SA_A2 = 'Bm | G | Em | F# | Bm | G | Em | F#7';
const SA_MEL_A = `o5 f+2 e4 | d2. | e4. f+8 g4 | f+2. | b4. a8 f+4 | g2 d4 | e4 d4 c+4 | <b2. |`;
const SA_MEL_B = `o5 g2 f+4 | f+2 e4 | e2 d4 | d4 c+4 <b4 | >d4 g4 b4 | a2 f+4 | g4 f+4 e4 | f+2. |`;
const SA_CNT_B = `o5 r2 b4 | a2. | g2. | f+2. | r2 g4 | f+2. | e2. | c+2. |`;
const SA_MEL_A2 = `o5 f+2 e4 | d2. | e4. f+8 g4 | f+2. | b4. a8 f+4 | g2 d4 | e2 g4 | <a+4 >c+4 e4 |`;
const sad = {
  name: '流亡', key: 'B 小调', bpm: 72, meter: [3, 4], loop: true,
  desc: '缓慢的三拍子：孤独的方波旋律带着回声，弦乐以下行的延留音链回应，竖琴稀疏地分解和弦。',
  reverb: { size: 0.86, damp: 0.5, wet: 0.36 }, send: 0.32,
  echo: { time: 60 / 72 / 2, fb: 0.32, wet: 0.45, lp: 2800 },
  chords: [SA_IN, SA_A, SA_B, SA_A2].join(' | '), melody: ['sq12', 'strlead', 'flute'],
  tracks: [
    { name: 'sq12', inst: 'sq12', vol: 0.95, pan: -0.15, echo: 0.35, send: 0.3,
      mml: `${barsT(2, 144)} L v11 ${SA_MEL_A} v8 ${SA_CNT_B} ${barsT(8, 144)}` },
    { name: 'strlead', inst: 'strlead', vol: 0.9, pan: 0.1, send: 0.36,
      mml: `${barsT(2, 144)} L ${barsT(8, 144)} v12 ${SA_MEL_B} v9 k-12 ${SA_MEL_A2} k0` },
    { name: 'flute', inst: 'flute', vol: 1, pan: 0.05, send: 0.34,
      mml: `${barsT(2, 144)} L ${barsT(16, 144)} v12 ${SA_MEL_A2}` },
    { name: 'pad', inst: 'strings', vol: 0.35, send: 0.4,
      mml: `r%144 ${pad('Bm', { ...M34, lo: 50, hi: 69, v: 6 })} L ${pad(SA_A, { ...M34, lo: 52, hi: 71, v: 7 })} ${pad(SA_B, { ...M34, lo: 52, hi: 71, v: 7 })} ${pad(SA_A2, { ...M34, lo: 50, hi: 71, n: 4, v: 9 })}` },
    { name: 'bass', inst: 'lowstr', vol: 0.6, send: 0.25,
      mml: `v7 o1 b2. | v9 b2. | L ${line(SA_A, { ...M34, pat: 'R2.', lo: 35, v: 10, slash: true })} ${line(SA_B, { ...M34, pat: 'R2.', lo: 35, v: 10, slash: true })} ${line(SA_A2, { ...M34, pat: 'R2.', lo: 35, v: 11, slash: true })}` },
    { name: 'harp', inst: 'harp', vol: 0.45, pan: 0.25, send: 0.4,
      mml: `${line(SA_IN, { ...M34, pat: 'R8 F8 O8 T+8 O8 F8', lo: 47, v: 8 })} L ${line(SA_A, { ...M34, pat: 'R8 F8 O8 T+8 O8 F8', lo: 47, v: 7 })} ${line(SA_B, { ...M34, pat: 'R8 F8 O8 T+8 F+8 T+8', lo: 47, v: 8 })} ${line(SA_A2, { ...M34, pat: 'R8 F8 O8 T+8 O8 F8', lo: 47, v: 9 })}` },
  ],
};

// ============================================================
// 3. calm 日常/营地：温暖
//    F 大调 6/8（附点四分=64）· 前奏 2 小节 + 循环 32 小节（长笛民谣旋律 / 单簧管对位 / 竖琴摇篮式分解 / 拨弦低音）
// ============================================================
const CA_IN = 'F | F';
const CA_A = 'F | Bb | F | C7 | F | Bb | Gm C | F';
const CA_A2 = 'F | Bb | Dm | C | Bb | F/A | Gm7 C | F';
const CA_B = 'Dm | Am | Bb | F | Gm | Am | Bb | C';
const CA_A3 = 'F | Bb | F | C7 | Bb | F/A | Gm | C7';
const CA_ALL = [CA_A, CA_A2, CA_B, CA_A3].join(' | ');
const CA_MEL_A = `o5 c4 f8 a4 g8 | f4. d4. | c4 f8 a4 >c8 | <b-4 a8 g4. | a4 f8 c4 f8 | d4 c8 d4 f8 | g4. e4. | f2. |`;
const CA_MEL_A2 = `o5 c4 f8 a4 g8 | f4. d4. | a4 d8 f4 a8 | g4 f8 e4 c8 | d4 f8 b-4 a8 | a4 g8 f4 c8 | b-4 a8 g4 e8 | f2. |`;
const CA_MEL_B = `o5 d4 f8 a4. | e4 c8 <a4. | >d4 f8 b-4. | a4. f4. | b-4. g4. | a4. e4. | f4. d4. | e4 f8 g4. |`;
const CA_CNT_B = `o5 f2. | e2. | d2. | c2. | d2. | c2. | d2. | e2. |`;
const CA_CNT_A2 = `o4 a2. | b-2. | a2. | g2. | f2. | f2. | g2. | a2. |`;
const CA_MEL_A3 = `o5 c4 f8 a4 g8 | f4. d4. | c4 f8 a4 >c8 | <b-4 a8 g4. | d4 f8 b-4 a8 | a4 g8 f4 c8 | g4. b-4. | b-4 a8 g4 e8 |`;
const calm = {
  name: '营火', key: 'F 大调', bpm: 96, meter: [6, 8], loop: true,
  desc: '温暖的 6/8 田园曲：长笛唱民谣般的旋律，单簧管在低音区回应，竖琴与拨弦贝斯像篝火一样摇晃。',
  reverb: { size: 0.66, damp: 0.5, wet: 0.28 }, send: 0.26,
  chords: [CA_IN, CA_ALL].join(' | '), melody: ['flute', 'clarinet'],
  tracks: [
    { name: 'flute', inst: 'flute', vol: 1, pan: 0.1, send: 0.28,
      mml: `${barsT(2, 144)} L v12 ${CA_MEL_A} ${CA_MEL_A2} v9 ${CA_CNT_B} v12 ${CA_MEL_A3}` },
    { name: 'clarinet', inst: 'clarinet', vol: 0.8, pan: -0.2, send: 0.26,
      mml: `${barsT(2, 144)} L ${barsT(8, 144)} v9 ${CA_CNT_A2} v12 k-12 ${CA_MEL_B} k0 ${barsT(8, 144)}` },
    { name: 'strlead', inst: 'strlead', vol: 0.5, pan: -0.05, send: 0.3,
      mml: `${barsT(2, 144)} L ${barsT(24, 144)} v10 k-12 ${CA_MEL_A3} k0` },
    { name: 'pad', inst: 'strings', vol: 0.3, send: 0.32,
      mml: `${barsT(2, 144)} L ${pad(CA_A, { ...M68, lo: 53, hi: 70, v: 6 })} ${pad(CA_A2, { ...M68, lo: 53, hi: 70, v: 7 })} ${pad(CA_B, { ...M68, lo: 53, hi: 70, v: 7 })} ${pad(CA_A3, { ...M68, lo: 53, hi: 72, n: 4, v: 8 })}` },
    { name: 'harp', inst: 'harp', vol: 0.45, pan: 0.25, send: 0.3,
      mml: `${line(CA_IN, { ...M68, pat: 'R8 F8 O8 T+8 O8 F8', lo: 53, v: 9 })} L ${line(CA_ALL, { ...M68, pat: 'R8 F8 O8 T+8 O8 F8', lo: 53, v: 9 })}` },
    { name: 'bass', inst: 'pizz', vol: 0.65, pan: -0.1, send: 0.2,
      mml: `${barsT(2, 144)} L ${line(CA_ALL, { ...M68, pat: 'R4. F-4.', lo: 36, v: 11, slash: true })}` },
    kitT('shaker', 'h', [['......', 2], 'L', ['......', 8], ['ogg ogg', 8], ['o.g o.g', 8], ['ogg ogg', 8]], { step: 8, vol: 0.45, pan: 0.3, human: 0.1 }),
    { name: 'chime', inst: 'glock', vol: 0.35, pan: 0.3, send: 0.4,
      mml: `${barsT(2, 144)} L ${barsT(8, 144)} v9 o6 c2. | ${barsT(15, 144)} v8 o6 f2. | ${barsT(7, 144)}` },
  ],
};

// ============================================================
// 4. tension 阴谋/反派/修道院：低沉、半音、不安
//    C 小调 ♩=76 4/4 · 循环 16 小节（低音弦乐半音邻音顽固音型 / C 持续低音 / 管风琴与合唱 / 定音鼓心跳 / 圆号半音动机）
// ============================================================
const TE_CH = 'Cm | Db/C | Cm | Bdim/C | Cm | Cm | Ab | G | Ab | Adim | Bb | Bdim7 | Cm | Db | Fm | G7';
const tension = {
  name: '暗流', key: 'C 小调', bpm: 76, loop: true,
  desc: '低音弦乐在 C 上以半音邻音不停打转，管风琴与合唱在修道院般的混响里浮现，圆号吹出 G—A♭—G—F♯ 的阴影动机。',
  reverb: { size: 0.9, damp: 0.55, wet: 0.42 }, send: 0.36,
  echo: { time: 60 / 76 * 0.75, fb: 0.4, wet: 0.4, lp: 2200 },
  chords: TE_CH, melody: ['horn', 'eerie'],
  tracks: [
    { name: 'ostinato', inst: 'strstac', vol: 0.6, pan: -0.2, send: 0.3, mml: `L v10
      [o3 c8 c8 d-8 c8 c8 c8 <b8 >c8]8 |
      o2 a-8 a-8 a8 a-8 a-8 a-8 g8 a-8 | a8 a8 b-8 a8 a8 a8 g+8 a8 | b-8 b-8 b8 b-8 b-8 b-8 a8 b-8 | b8 b8 >c8 <b8 b8 b8 a+8 b8 |
      o3 c8 c8 d-8 c8 c8 c8 <b8 >c8 | d-8 d-8 d8 d-8 d-8 d-8 c8 d-8 | <f8 f8 g-8 f8 f8 f8 e8 f8 | g8 g8 a-8 g8 g8 g8 f+8 g8 |` },
    { name: 'drone', inst: 'lowstr', vol: 0.55, send: 0.3, mml: `L ${line(TE_CH, { pat: 'R1', lo: 31, v: 10, slash: true })}` },
    { name: 'organ', inst: 'organ', vol: 0.4, pan: 0.15, send: 0.45, mml: `L ${pad(TE_CH, { lo: 51, hi: 68, v: 7 })}` },
    { name: 'choir', inst: 'choir', vol: 0.4, pan: -0.1, send: 0.45, mml: `L ${bar4(8)} ${pad('Ab | Adim | Bb | Bdim7 | Cm | Db | Fm | G7', { lo: 55, hi: 72, v: 8 })}` },
    { name: 'horn', inst: 'horn', vol: 1, pan: 0.05, send: 0.34, mml: `L ${bar4(4)} v11 o4 g2. a-4 | g2. f+4 | e-2. d4 | d1 | ${bar4(4)} v12 o5 c2. d-4 | d-2. c4 | c2 <a-2 | b2. g4 |` },
    { name: 'eerie', inst: 'sq12', vol: 0.45, pan: 0.3, echo: 0.5, send: 0.3, mml: `L ${bar4(8)} v8 o5 e-4 d4 r2 | e-4 c4 r2 | f4 d4 r2 | a-4 f4 r2 | ${bar4(4)}` },
    { name: 'timp', inst: 'timp', vol: 0.5, send: 0.35, mml: `L o2 [v10 c8 v7 c8 r2.]8 | ${bar4(3)} <${roll('g', 32, 3, 11)} > | [v11 c8 v8 c8 r2.]3 | r2 <${roll('g', 16, 5, 12)} > |` },
    { name: 'bell', inst: 'bell', vol: 0.4, pan: -0.25, send: 0.5, mml: `L v9 o4 c1 | ${bar4(7)} v7 c1 | ${bar4(7)}` },
  ],
};

// ============================================================
// 5. prep 关前整备：轻快行军
//    G 大调 ♩=112 4/4 · 前奏 1 小节 + 循环 24 小节（50% 方波附点旋律 / 小号副歌 / 拨弦“嗯-啪”低音 / 轻军鼓）
// ============================================================
const PR_A = 'G | C | G | D | G | C | Am D | G';
const PR_B = 'C | D | G | Em | C | D | G/B C | D7';
const PR_A2 = 'G | C | G | D | G | C | Am D7 | G';
const PR_MEL_A = `o4 g4 b8. g16 >d4 d4 | e4 c8. e16 g4 e4 | d4 <b8. >d16 g4 d4 | <a4 f+8. a16 >d2 |
  <g4 b8. g16 >d4 d4 | e4 g8. e16 c4 e4 | c8. <b16 a4 f+8. a16 >d4 | <g4 b4 g2 |`;
const PR_MEL_B = `o5 e2 g4 e4 | f+2 a4 f+4 | g4. f+8 g4 b4 | b4. a8 g4 e4 | e2 g4 >c4 | <a2 f+4 d4 | g4 d4 e4 g4 | f+4 e4 d4 c4 |`;
const prep = {
  name: '整备', key: 'G 大调', bpm: 112, loop: true,
  desc: '轻快的行军：方波吹着附点节奏的旋律，拨弦低音与方波后半拍和弦“嗯-啪”，副歌交给小号，最后钟琴加入。',
  reverb: { size: 0.6, damp: 0.45, wet: 0.24 }, send: 0.22,
  echo: { time: 60 / 112 * 0.75, fb: 0.3, wet: 0.3, lp: 3000 },
  chords: ['G', PR_A, PR_B, PR_A2].join(' | '), melody: ['lead', 'trumpet'],
  tracks: [
    { name: 'lead', inst: 'sq50', vol: 1, pan: -0.1, echo: 0.25, mml: `r1 | L v12 ${PR_MEL_A} ${bar4(8)} v12 ${PR_MEL_A}` },
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.1, mml: `r1 | L ${bar4(8)} v12 ${PR_MEL_B} ${bar4(8)}` },
    { name: 'glock', inst: 'glock', vol: 0.35, pan: 0.3, send: 0.3, mml: `r1 | L ${bar4(16)} v8 k12 ${PR_MEL_A} k0` },
    { name: 'chords', inst: 'sqpluck', vol: 0.35, pan: 0.2, mml: `r1 | L ${pad(PR_A, { lo: 55, hi: 72, v: 9, rhythm: 'r4 4' })} ${pad(PR_B, { lo: 55, hi: 72, v: 8, rhythm: 'r4 4' })} ${pad(PR_A2, { lo: 55, hi: 72, v: 9, rhythm: 'r4 4' })}` },
    { name: 'horn', inst: 'horn', vol: 0.4, pan: -0.2, mml: `r1 | L ${bar4(8)} ${pad(PR_B, { lo: 52, hi: 67, v: 8 })} ${pad(PR_A2, { lo: 52, hi: 67, v: 7, rhythm: '2' })}` },
    { name: 'arp', inst: 'sq25', vol: 0.5, pan: 0.25, echo: 0.2, mml: `r1 | L ${bar4(8)} ${line(PR_B, { pat: 'R16 T16 F16 O16', lo: 60, v: 7 })} ${bar4(8)}` },
    { name: 'bass', inst: 'pizz', vol: 0.7, mml: `v11 o2 g4 r4 d4 r4 | L ${line([PR_A, PR_B, PR_A2].join(' | '), { pat: 'R4 X4 F-4 X4', lo: 40, v: 12, slash: true })}` },
    kitT('snare', 's', [['X..x X..x X.x. XxXx', 1], 'L', ['x... x.o. x... x.oo', 7], ['x... x.o. x.x. xxXX', 1], ['x... x... x... x.o.', 7], ['x... x... x.x. x.xx', 1], ['X..o x.o. X..o x.xx', 7], ['X..o x.o. X.x. XXXX', 1]], { vol: 0.5, pan: -0.1 }),
    kitT('kick', 'k', [['X...X...X...X...', 1], 'L', ['x.......x.......', 8], ['x...............', 8], ['X.......X.......', 8]], { vol: 0.55 }),
    kitT('hat', 'h', [[E16, 1], 'L', ['o.g.o.g.o.g.o.g.', 8], ['o.o.o.o.o.o.o.o.', 8], ['o.g.o.g.o.g.o.g.', 8]], { vol: 0.45, pan: 0.2, human: 0.1 }),
    kitT('cym', 'c', [[E16, 1], 'L', ['x...............', 1], [E16, 15], ['X...............', 1], [E16, 7]], { vol: 0.4, pan: 0.25 }),
  ],
};

// ============================================================
// 6. player1 我方回合（第 1~3 章）：昂扬、英雄感
//    降 B 大调 ♩=124 4/4 · 前奏 2 小节 + 循环 36 小节（小号主旋律 / 弦乐关系小调副歌 / 高潮 / 4 小节回转）
// ============================================================
const P1_IN = 'Eb | F';
const P1_A = 'Bb | Eb | Bb | F | Gm | Eb | Cm F | Bb';
const P1_A2 = 'Bb | Eb | Bb | F | Gm | Eb | F | F';
const P1_B = 'Gm | Dm | Eb | Bb | Cm | Gm | Eb | F';
const P1_C = 'Eb | F | Dm | Gm | Eb | F | Gm | F';
const P1_T = 'Eb | F | Eb | F';
const P1_HEAD = `o4 f4 b-8. >c16 d2 | e-4. f8 g2 | f4. d8 <b-4 >d4 | c4. <b-8 a4 >c4 |`;
const P1_MEL_A = `${P1_HEAD} o5 d4 <b-8. >c16 d4 g4 | g4. f8 e-4 g4 | g4 e-4 f4. e-8 | d2. r4 |`;
const P1_MEL_A2 = `${P1_HEAD} o5 d4 g8. a16 b-2 | g4. f8 e-4 g4 | f4. g8 a4 >c4 | c4. <a8 f2 |`;
const P1_MEL_B = `o4 b-4 >d4 g2 | f4. e8 d2 | e-4 g4 b-2 | b-4. a8 f2 | g4 e-4 c2 | d4. e-8 d4 <b-4 | >e-4 g4 b-4 g4 | a2 >c2 |`;
const P1_MEL_C = `o5 b-2 g4 e-4 | >c2 <a4 f4 | >d4. c8 <a4 f4 | b-4. a8 g2 | e-4 g8 b-8 >e-2 | c4. <b-8 a4 f4 | b-4. a8 g4 d4 | f2. r4 |`;
const P1_MEL_T = `o4 g8 b-8 >e-4 <g8 b-8 >e-4 | <a8 >c8 f4 <a8 >c8 f4 | g4 f4 e-4 g4 | f2 c4 e-4 |`;
const P1_DRIVE = 'R8 R8 O8 R8 F-8 R8 O8 R8';
const player1 = {
  name: '旗帜之下', key: '降 B 大调', bpm: 124, loop: true,
  desc: '昂扬的我方回合：小号以“F—B♭. C D”的上行号角开篇，八分音符贝斯推动，副歌转 G 小调由弦乐接手，最后小号在高音区爆发。',
  reverb: { size: 0.62, damp: 0.45, wet: 0.24 }, send: 0.22,
  chords: [P1_IN, P1_A, P1_A2, P1_B, P1_C, P1_T].join(' | '), melody: ['trumpet', 'strlead'],
  tracks: [
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.08, mml: `r1 | r1 | L v12 ${P1_MEL_A} ${P1_MEL_A2} ${bar4(8)} v13 ${P1_MEL_C} v12 ${P1_MEL_T}` },
    { name: 'strlead', inst: 'strlead', vol: 0.85, pan: -0.1, mml: `r1 | r1 | L ${bar4(16)} v12 ${P1_MEL_B} v10 k-12 ${P1_MEL_C} k0 ${bar4(4)}` },
    { name: 'horn', inst: 'horn', vol: 0.5, pan: -0.25, mml: `${pad(P1_IN, { lo: 51, hi: 67, v: 11, rhythm: '4. 8 r4 4' })} L ${bar4(8)} ${line(P1_A2, { pat: 'T2 F2', lo: 55, v: 9 })} ${pad(P1_B, { lo: 51, hi: 67, v: 7 })} ${pad(P1_C, { lo: 51, hi: 67, v: 9, rhythm: '2' })} ${pad(P1_T, { lo: 51, hi: 67, v: 11, rhythm: '4. 8 r4 4' })}` },
    { name: 'pad', inst: 'strings', vol: 0.32, send: 0.28, mml: `r1 | r1 | L ${pad(P1_A + ' | ' + P1_A2, { lo: 55, hi: 72, v: 8, rhythm: '2' })} ${bar4(8)} ${pad(P1_C + ' | ' + P1_T, { lo: 55, hi: 74, n: 4, v: 9, rhythm: '2' })}` },
    { name: 'arp', inst: 'sq25', vol: 0.5, pan: 0.3, mml: `r1 | r1 | L ${bar4(8)} ${line(P1_A2, { pat: 'R8 F8 O8 F8', lo: 58, v: 7 })} ${line(P1_B, { pat: 'R16 T16 F16 O16', lo: 58, v: 8 })} ${bar4(12)}` },
    { name: 'bass', inst: 'fbass', vol: 0.7, mml: `v12 o2 e-4. e-8 r4 e-4 | f4. f8 r4 f4 | L ${line([P1_A, P1_A2].join(' | '), { pat: P1_DRIVE, lo: 34, v: 12 })} ${line(P1_B, { pat: 'R4. R8 F-4 R4', lo: 34, v: 11 })} ${line([P1_C, P1_T].join(' | '), { pat: P1_DRIVE, lo: 34, v: 12 })}` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o2 v12 e-4 r2. | f4 r4 ${roll('f', 16, 6, 13)} | L v12 <b-4 r2. | ${bar4(15)} ${bar4(8)} >e-4 r2. | f4 r2. | ${bar4(5)} r2 ${roll('f', 16, 5, 12)} | e-4 r2. | f4 r2. | r1 | r2 ${roll('f', 16, 5, 13)} |` },
    kitT('kick', 'k', [['X.....x.X.......', 2], 'L', ['X.....x.X.......', 16], ['x.......x.......', 8], ['X.....x.X.....x.', 12]], { vol: 0.55 }),
    kitT('snare', 's', [['....X.......X...', 1], ['....X...X.X.XXXX', 1], 'L', ['....X.......X...', 7], ['....X.......XxXx', 1], ['....X.......X...', 7], ['....X...X.x.XXXX', 1],
      ['....x.......x...', 7], ['....x...x.x.xxXX', 1], ['....X.......X...', 7], ['X.X.X.X.XxXxXXXX', 1], ['....X.......X...', 3], ['xxxxXXXXxxxxXXXX', 1]], { vol: 0.5 }),
    kitT('hat', 'h', [['x.o.x.o.x.o.x.o.', 2], 'L', ['x.o.x.o.x.o.x.o.', 16], ['o.o.o.o.o.o.o.o.', 8], ['x.o.x.o.x.o.x.o.', 12]], { vol: 0.3, pan: 0.2, human: 0.1 }),
    kitT('cym', 'c', [[E16, 2], 'L', ['X...............', 1], [E16, 7], ['x...............', 1], [E16, 7], ['o...............', 1], [E16, 7], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3]], { vol: 0.4, pan: 0.25 }),
  ],
};

// ============================================================
// 7. player2 我方回合（第 4~5 章）：更紧迫、悲壮
//    A 小调 ♩=136 4/4 · 前奏 2 小节 + 循环 40 小节（十六分音符弦乐顽固音型 / 小号主旋律 / 副歌转关系大调 / 合唱 / 渐强过门）
// ============================================================
const P2_IN = 'Am | Am';
const P2_A = 'Am | F | C | G | Am | F | Dm | E';
const P2_A2 = 'Am | F | C | G | F | G | Esus4 | E';
const P2_B = 'F | G | C | Am | F | G | Am | E';
const P2_C = 'Dm | E | Am | F | Dm | E | F | E';
const P2_D = 'Am | Am | F | F | Dm | Dm | E | E';
const P2_HEAD = `o5 e2 <a4 >c4 | c4. <b8 a2 | g4 >c4 e4. d8 | d2. r4 |`;
const P2_MEL_A = `${P2_HEAD} o5 e2 a4 g4 | f4. e8 c2 | d4 f4 a4. g8 | g+2. r4 |`;
const P2_MEL_A2 = `${P2_HEAD} o5 a4. g8 f4 c4 | g4. f8 d4 <b4 | >a2 b2 | g+2. r4 |`;
const P2_MEL_B = `o4 a4 >c4 f2 | g4. f8 d2 | e4 g4 >c2 | c4. <b8 a2 | a4 g4 f4 a4 | g4. f8 d4 g4 | e2 a2 | g+2 b2 |`;
const P2_MEL_C = `o5 a4. >d8 d2 | <b4. g+8 e2 | >c4. <b8 a4 e4 | f4 a4 >c2 | d2 <f4 a4 | g+2 b4 >e4 | c4. <b8 a4 f4 | e2. r4 |`;
const P2_MEL_D = `o4 a1 | >c1 | c2 <a2 | >f1 | f2 d2 | <a1 | b1 | g+2 b2 |`;
const P2_OST = 'R16 F16 O16 F16';
const player2 = {
  name: '决意', key: 'A 小调', bpm: 136, loop: true,
  desc: '紧迫悲壮的我方回合：十六分音符的弦乐像急促的心跳，小号吹出坚定的小调旋律，副歌短暂转入 C 大调，过门由合唱与定音鼓层层推高。',
  reverb: { size: 0.66, damp: 0.45, wet: 0.26 }, send: 0.22,
  chords: [P2_IN, P2_A, P2_A2, P2_B, P2_C, P2_D].join(' | '), melody: ['trumpet', 'strlead', 'horn'],
  tracks: [
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.08, mml: `r1 | r1 | L v12 ${P2_MEL_A} ${P2_MEL_A2} ${bar4(8)} v13 ${P2_MEL_C} ${bar4(8)}` },
    { name: 'strlead', inst: 'strlead', vol: 0.85, pan: -0.1, mml: `r1 | r1 | L ${bar4(8)} v10 k-12 ${P2_MEL_A2} k0 v12 ${P2_MEL_B} v10 k-12 ${P2_MEL_C} k0 ${bar4(8)}` },
    { name: 'horn', inst: 'horn', vol: 0.7, pan: -0.2, mml: `r1 | r1 | L ${bar4(24)} ${pad(P2_C, { lo: 52, hi: 67, v: 9, rhythm: '2' })} v11 ${P2_MEL_D}` },
    { name: 'ostinato', inst: 'strstac', vol: 0.45, pan: 0.2, mml: `${line(P2_IN, { pat: P2_OST, lo: 57, v: 9 })} L ${line(P2_A + ' | ' + P2_A2, { pat: P2_OST, lo: 57, v: 10 })} ${bar4(8)} ${line(P2_C, { pat: P2_OST, lo: 57, v: 11 })} ${line(P2_D, { pat: P2_OST, lo: 57, v: 9 })}` },
    { name: 'arp', inst: 'sq25', vol: 0.35, pan: 0.25, mml: `r1 | r1 | L ${bar4(16)} ${line(P2_B, { pat: 'R16 T16 F16 O16', lo: 60, v: 8 })} ${bar4(16)}` },
    { name: 'choir', inst: 'choir', vol: 0.35, pan: -0.05, send: 0.35, mml: `r1 | r1 | L ${bar4(16)} ${pad([P2_B, P2_C, P2_D].join(' | '), { lo: 55, hi: 72, v: 9 })}` },
    { name: 'bass', inst: 'fbass', vol: 0.7, mml: `${line(P2_IN, { pat: 'R8 R8 R8 R8 R8 R8 O8 R8', lo: 33, v: 11 })} L ${line([P2_A, P2_A2, P2_B, P2_C].join(' | '), { pat: 'R8 R8 R8 R8 R8 R8 O8 R8', lo: 33, v: 12 })} ${line('Am | Am | F | F', { pat: 'R2 R2', lo: 33, v: 11 })} ${line('Dm | Dm | E | E', { pat: 'R8 R8 R8 R8 R8 R8 O8 R8', lo: 33, v: 12 })}` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o1 v11 a4 r2. | a4 r4 ${roll('a', 16, 5, 12)} | L v12 a4 r2. | ${bar4(15)} ${bar4(7)} >${roll('e', 32, 4, 12)} | d4 r2. | e4 r2. | <a4 r2. | >f4 r2. | d4 r2. | e4 r2. | f4 r2. | e4 r4 e4 e4 | <a1 | r1 | r1 | r1 | >d4 r2. | r1 | e4 r4 e4 r4 | ${roll('e', 32, 4, 13)} |` },
    kitT('kick', 'k', [['X...............', 1], ['X...X...X...X...', 1], 'L', ['X..xX...X..xX...', 16], ['X.......X.......', 8], ['X.x.X.x.X.x.X.x.', 8], ['X...............', 4], ['X...X...X...X...', 3], ['X.X.X.X.XXXXXXXX', 1]], { vol: 0.55 }),
    kitT('snare', 's', [[E16, 1], ['............XXXX', 1], 'L', ['....X.......X...', 7], ['....X...X.X.XXXX', 1], ['....X.......X...', 7], ['....X...X.X.XXXX', 1],
      ['....x.......x...', 7], ['....x.......xxXX', 1], ['....X.......X...', 7], ['X.X.X.X.XXXXXXXX', 1], [E16, 4], ['....x.......x...', 3], ['xxxxxxxxXXXXXXXX', 1]], { vol: 0.5 }),
    kitT('hat', 'h', [[E16, 2], 'L', ['xoxoxoxoxoxoxoxo', 16], ['o.o.o.o.o.o.o.o.', 8], ['xoxoxoxoxoxoxoxo', 8], [E16, 4], ['o.o.o.o.o.o.o.o.', 4]], { vol: 0.28, pan: 0.2, human: 0.12 }),
    kitT('cym', 'c', [[E16, 2], 'L', ['X...............', 1], [E16, 7], ['x...............', 1], [E16, 7], ['o...............', 1], [E16, 7], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3], [E16, 4], ['x...............', 1], [E16, 3]], { vol: 0.4, pan: 0.25 }),
  ],
};

// ============================================================
// 8. enemy 敌方回合：紧张、低音驱动
//    E 小调 ♩=150 4/4 · 前奏 1 小节 + 循环 32 小节（八分音符低音 riff / 圆号低音动机 / 方波旋律 / 小号 / 弗里几亚 F 大调威胁段）
// ============================================================
const EN_IN = 'Em';
const EN_A = 'Em | Em | C | B | Em | Em | C | B';
const EN_B = 'Em | D | C | B | Em | D | C | B7';
const EN_C = 'Am | Em | Am | B | C | D | C | B';
const EN_D = 'Em:2 F:2 | Em:2 F:2 | Em:2 F:2 | G:2 B:2 | Em:2 F:2 | Em:2 F:2 | Em:2 F:2 | G:2 B:2';
const EB = {
  Em: 'e8 e8 >e8 <e8 >d8 <e8 <b8 >e8', C: 'c8 c8 >c8 <c8 <b8 >c8 <g8 >c8', B: '<b8 b8 >b8 <b8 >a8 <b8 f+8 b8 >',
  D: 'd8 d8 >d8 <d8 c8 d8 <a8 >d8', Am: 'a8 a8 >a8 <a8 >g8 <a8 e8 a8', EF: 'e8 e8 >e8 <e8 f8 f8 >f8 <f8', GB: 'g8 g8 >g8 <g8 <b8 b8 >b8 <b8 >',
};
const enBass = (seq) => seq.split(' ').map((c) => EB[c] + ' |').join(' ');
const EN_BASS = `o2 ${enBass('Em')} L ${enBass('Em Em C B Em Em C B Em D C B Em D C B Am Em Am B C D C B EF EF EF GB EF EF EF GB')}`;
const EN_MEL_A = `o3 b2. >c4 | <b1 | >c2. d4 | d+1 | o4 b2. >c4 | <b1 | >c2. d4 | d+1 |`;
const EN_MEL_B = `o5 e4 g4 b4. a8 | a4. g8 f+2 | g4 e4 c4 e4 | d+2. r4 | e4 g4 b4 >e4 | d4. c8 <a2 | g4 e4 g4 >c4 | <b2 a4 f+4 |`;
const EN_MEL_C = `o5 a4. >c8 e2 | <b4. g8 e2 | >c4 <b4 a4 e4 | f+2. d+4 | e4 g4 >c4. <b8 | a4 f+4 d4. e8 | g4 e4 c4 g4 | f+1 |`;
const EN_MEL_D = `o4 e2 f2 | g2 a2 | b2 >c2 | d2 d+2 |`;
const enemy = {
  name: '黑鹰进军', key: 'E 小调', bpm: 150, loop: true,
  desc: '低音 riff 驱动的敌方回合：E—E—E′—E—D′—E—B—E 的八分音符不停逼近，圆号在低音区徘徊，最后一段用弗里几亚的 F 大调制造压迫感。',
  reverb: { size: 0.55, damp: 0.5, wet: 0.2 }, send: 0.18,
  echo: { time: 60 / 150 * 0.75, fb: 0.3, wet: 0.25, lp: 2500 },
  chords: [EN_IN, EN_A, EN_B, EN_C, EN_D].join(' | '), melody: ['horn', 'lead', 'trumpet'],
  tracks: [
    { name: 'bass', inst: 'fbass', vol: 0.75, mml: `v12 ${EN_BASS}` },
    { name: 'bass2', inst: 'tri', vol: 0.35, mml: `v11 ${EN_BASS}` },
    { name: 'horn', inst: 'horn', vol: 0.9, pan: -0.15, mml: `r1 | L v11 ${EN_MEL_A} ${bar4(16)} v11 ${EN_MEL_D} ${EN_MEL_D}` },
    { name: 'lead', inst: 'sq25', vol: 1, pan: 0.15, echo: 0.3, mml: `r1 | L ${bar4(8)} v12 ${EN_MEL_B} ${bar4(16)}` },
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.05, mml: `r1 | L ${bar4(16)} v12 ${EN_MEL_C} ${bar4(4)} v11 k12 ${EN_MEL_D} k0` },
    { name: 'strlead', inst: 'strlead', vol: 0.55, pan: -0.05, mml: `r1 | L ${bar4(16)} v10 k-12 ${EN_MEL_C} k0 ${bar4(8)}` },
    { name: 'chug', inst: 'strstac', vol: 0.4, pan: 0.2, mml: `r1 | L ${pad(EN_A + ' | ' + EN_B, { lo: 52, hi: 67, v: 9, rhythm: 'r8 8' })} ${pad(EN_C, { lo: 52, hi: 69, v: 10, rhythm: 'r8 8' })} ${pad(EN_D, { lo: 52, hi: 67, v: 9, rhythm: 'r8 8' })}` },
    { name: 'choir', inst: 'choir', vol: 0.35, send: 0.3, mml: `r1 | L ${bar4(24)} ${pad(EN_D, { lo: 52, hi: 69, v: 9 })}` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o2 v11 e4 r2. | L e4 r2. | ${bar4(7)} e4 r2. | ${bar4(7)} <a4 r2. > | ${bar4(7)} [e4 r4 f4 r4 |]3 g4 r4 <b4 r4 > | [e4 r4 f4 r4 |]3 g4 r4 <b4 b8 b8 > |` },
    kitT('kick', 'k', [['X...............', 1], 'L', ['X.....x.X.......', 8], ['X.....x.X.....x.', 8], ['X.x...x.X.x...x.', 8], ['X...X...X...X...', 8]], { vol: 0.55 }),
    kitT('snare', 's', [['............xxXX', 1], 'L', ['....X.......X...', 7], ['....X.......XxXX', 1], ['....X.......X...', 7], ['....X.......XxXX', 1], ['....X.......X...', 7], ['X.X.X.X.XXXXXXXX', 1], [E16, 3], ['........XxXxXXXX', 1], [E16, 3], ['XXXXXXXXXXXXXXXX', 1]], { vol: 0.5 }),
    kitT('tom', 't', [[E16, 1], 'L', [E16, 24], ['....x.......x..x', 3], [E16, 1], ['....x.......x..x', 3], [E16, 1]], { vol: 0.5 }),
    kitT('hat', 'h', [[E16, 1], 'L', ['x.x.x.x.x.x.x.x.', 16], ['xoxoxoxoxoxoxoxo', 8], ['o...o...o...o...', 8]], { vol: 0.28, pan: 0.2, human: 0.12 }),
    kitT('cym', 'c', [[E16, 1], 'L', ['X...............', 1], [E16, 7], ['x...............', 1], [E16, 7], ['X...............', 1], [E16, 3], ['x...............', 1], [E16, 3], ['X...............', 1], [E16, 7]], { vol: 0.4, pan: 0.25 }),
  ],
};

// ============================================================
// 9. boss 首领战：激烈
//    G 小调 ♩=160 4/4 · 前奏 2 小节 + 循环 40 小节（半音抽搐的十六分音符弦乐 / 铜管主题 / 那不勒斯 A♭ 副歌 / 定音鼓与合唱）
// ============================================================
const BO_IN = 'Gm | Gm';
const BO_A = 'Gm | Gm | Eb | D | Gm | Gm | Eb | D7';
const BO_B = 'Cm | Gm | Ab | D | Cm | Gm | Ab | D';
const BO_C = 'Eb | F | D | Gm | Eb | F | Ab | D';
const BO_D = 'Gm | F#dim | Gm | F#dim | Eb | Cm | D | D7';
const BO_ALL = [BO_A, BO_B, BO_A, BO_C, BO_D].join(' | ');
const BO_MEL_A = `o4 g8 g8 >d4 <b-4. a8 | g2. r4 | g8 b-8 >e-4 g4. f8 | f+2. r4 | g8 g8 >d4 <b-4. a8 | g4 f4 d4 <b-4 | >e-4 g4 b-4 g4 | a2 f+4 >c4 |`;
const BO_MEL_B = `o5 e-2 g4. f8 | d2. <b-4 | >c2 e-4. d8 | d2 f+2 | g2 >c4. <b-8 | b-2. g4 | a-2 >c4 e-4 | d2 <a2 |`;
const BO_MEL_C = `o5 b-4. g8 e-2 | >c4. <a8 f2 | >d4. <a8 f+2 | g1 | g4 b-4 >e-2 | <a4 >c4 f2 | e-2 c2 | d2. <a4 |`;
const BO_MEL_D = `o3 g1 | a1 | b-1 | >c1 | e-2 g2 | g2 e-2 | f+2 a2 | >c2 <a2 |`;
const BO_OST = 'R16 R16 (1)16 R16 R16 R16 (-1)16 R16';
const boss = {
  name: '死斗', key: 'G 小调', bpm: 160, loop: true,
  desc: '激烈的首领战：弦乐以 G—G—A♭—G 的半音抽搐不停奔跑，铜管吹出锋利的主题，副歌借那不勒斯 A♭ 和弦拔高，尾段定音鼓与低音圆号步步紧逼。',
  reverb: { size: 0.6, damp: 0.45, wet: 0.22 }, send: 0.2,
  chords: [BO_IN, BO_ALL].join(' | '), melody: ['trumpet', 'strlead', 'horn'],
  tracks: [
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.08, mml: `r1 | r1 | L v12 ${BO_MEL_A} ${bar4(8)} v13 ${BO_MEL_A} v13 ${BO_MEL_C} ${bar4(8)}` },
    { name: 'strlead', inst: 'strlead', vol: 0.85, pan: -0.1, mml: `r1 | r1 | L ${bar4(8)} v12 ${BO_MEL_B} ${bar4(8)} v10 k-12 ${BO_MEL_C} k0 ${bar4(8)}` },
    { name: 'horn', inst: 'horn', vol: 0.6, pan: -0.25, mml: `r1 | r1 | L ${pad(BO_A, { lo: 50, hi: 65, v: 9, rhythm: '4 r4 r4 4' })} ${pad(BO_B, { lo: 50, hi: 65, v: 8 })} v11 k-12 ${BO_MEL_A} k0 ${pad(BO_C, { lo: 50, hi: 65, v: 10, rhythm: '2' })} v12 ${BO_MEL_D}` },
    { name: 'ostinato', inst: 'strstac', vol: 0.45, pan: 0.2, mml: `${line(BO_IN, { pat: BO_OST, lo: 55, v: 10 })} L ${line(BO_A, { pat: BO_OST, lo: 55, v: 11 })} ${line(BO_B, { pat: BO_OST, lo: 55, v: 9 })} ${line(BO_A + ' | ' + BO_C, { pat: BO_OST, lo: 55, v: 11 })} ${line(BO_D, { pat: BO_OST, lo: 55, v: 10 })}` },
    { name: 'choir', inst: 'choir', vol: 0.35, send: 0.3, mml: `r1 | r1 | L ${bar4(8)} ${pad(BO_B, { lo: 55, hi: 72, v: 9 })} ${bar4(8)} ${pad(BO_C + ' | ' + BO_D, { lo: 55, hi: 72, v: 10 })}` },
    { name: 'bass', inst: 'fbass', vol: 0.7, mml: `${line(BO_IN, { pat: 'R8 R8 R8 R8 R8 R8 R8 R8', lo: 31, v: 11 })} L ${line(BO_ALL, { pat: 'R8 R8 O8 R8 R8 R8 O8 R8', lo: 31, v: 12 })}` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o2 ${roll('g', 32, 4, 13)} | v13 g4 r4 d4 r4 |
      L g4 r2. | r1 | r1 | d4 r4 d8 d8 d4 | g4 r2. | r1 | r1 | d4 r4 d4 d4 |
      ${bar4(7)} ${roll('d', 32, 3, 12)} |
      g4 r4 g4 r4 | r1 | r1 | d4 r4 d8 d8 d4 | g4 r4 g4 r4 | r1 | r1 | d4 d4 d4 d4 |
      r1 | r1 | d4 r2. | g4 r2. | r1 | r1 | r1 | d4 r4 d4 d4 |
      g4 r4 g8 g8 g4 | a4 r4 a8 a8 a4 | g4 r4 g8 g8 g4 | a4 r4 a8 a8 a4 | r1 | r1 | d4 r4 d4 r4 | ${roll('d', 32, 5, 14)} |` },
    kitT('kick', 'k', [['X...............', 1], ['X...X...X.X.XXXX', 1], 'L', ['X..xX...X..xX...', 8], ['X.......X.......', 8], ['X..xX...X..xX...', 8], ['X.x.X.x.X.x.X.x.', 8], ['X...............', 4], ['X...X...X...X...', 3], ['X.X.X.X.XXXXXXXX', 1]], { vol: 0.55 }),
    kitT('snare', 's', [[E16, 1], ['....X...X.X.XXXX', 1], 'L', ['....X.......X...', 7], ['....X...X.XXXXXX', 1], ['........X.......', 7], ['........X...XXXX', 1], ['....X.......X...', 7], ['....X...X.XXXXXX', 1], ['....X.......X...', 7], ['X.X.X.X.XXXXXXXX', 1], [E16, 4], ['....x.......x...', 3], ['XXXXXXXXXXXXXXXX', 1]], { vol: 0.5 }),
    kitT('hat', 'h', [[E16, 2], 'L', ['x.x.x.x.x.x.x.x.', 8], ['x...x...x...x...', 8], ['xoxoxoxoxoxoxoxo', 16], [E16, 4], ['x.x.x.x.x.x.x.x.', 4]], { vol: 0.28, pan: 0.2, human: 0.12 }),
    kitT('cym', 'c', [[E16, 2], 'L', ['X...............', 1], [E16, 3], ['x...............', 1], [E16, 3], ['o...............', 1], [E16, 7], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3], [E16, 4], ['X...............', 1], [E16, 3]], { vol: 0.4, pan: 0.25 }),
  ],
};

// ============================================================
// 10. final 最终决战（第五章）：悲壮宏大，融入主题
//    D 小调 ♩=132 4/4 · 前奏 2 小节 + 循环 44 小节（主题小号强奏 / 弦乐高音对题 / 铜管英雄段 / 主题转 E 小调由弦乐与合唱 / 主题全奏+钟 / 回转）
// ============================================================
const FI_IN = 'Dm | A';
const FI_A = 'Dm | Bb | Gm | A | Dm | F/C | Gm A | Dm';
const FI_A2 = 'Bb | F | Gm | Dm | Bb | C | Gm | A';
const FI_B = 'Bb | F | Gm | Dm | Bb | C | Am | B7';
const FI_C = 'Em | C | Am | B | Em | G/D | Am B | Em:2 A7:2';
const FI_E = 'Bb | Gm | Asus4 | A';
const FI_ALL = [FI_A, FI_A2, FI_B, FI_C, FI_A, FI_E].join(' | ');
const FI_MEL_A2 = `o6 d2 <b-4 f4 | >c2 <a4 f4 | b-4. a8 g4 d4 | f2 a2 | >d4. c8 <b-4 f4 | >c4. d8 e2 | d4. c8 <b-4 g4 | a2 >c+2 |`;
const FI_MEL_B = `o5 f4 b-4 >d2 | c4. <b-8 a2 | g4 b-4 >d4. c8 | <a1 | b-4 >d4 f2 | e4. d8 c2 | c4. <b8 a4 e4 | d+2 f+4 a4 |`;
const FI_MEL_E = `o5 f2 d2 | g2 b-2 | a1 | e2 c+2 |`;
const final = {
  name: '灰烬王冠·终章', key: 'D 小调', bpm: 132, loop: true,
  desc: '最终决战：十六分音符弦乐与进行曲军鼓之上，小号强奏灰烬王冠主题；中段主题移到 E 小调由弦乐和合唱唱出，最后回到 D 小调全奏，钟声敲响。',
  reverb: { size: 0.78, damp: 0.45, wet: 0.3 }, send: 0.26,
  chords: [FI_IN, FI_ALL].join(' | '), melody: ['trumpet', 'strlead'],
  tracks: [
    { name: 'trumpet', inst: 'trumpet', vol: 1, pan: 0.08, mml: `r1 | r1 | L v12 ${THEME} ${bar4(8)} v12 ${FI_MEL_B} ${bar4(8)} v13 ${THEME} v12 ${FI_MEL_E}` },
    { name: 'strlead', inst: 'strlead', vol: 0.85, pan: -0.1, mml: `r1 | r1 | L ${bar4(8)} v12 ${FI_MEL_A2} ${bar4(8)} v12 k2 ${THEME} k0 v11 k12 ${THEME} k0 ${bar4(4)}` },
    { name: 'horn', inst: 'horn', vol: 0.55, pan: -0.25, mml: `r1 | ${pad('A', { lo: 52, hi: 67, v: 11, rhythm: '4 4 4 4' })} L ${pad(FI_A, { lo: 50, hi: 65, v: 9, rhythm: '2' })} ${line(FI_A2, { pat: 'T2 F2', lo: 53, v: 9 })} v10 k-12 ${FI_MEL_B} k0 ${pad(FI_C, { lo: 52, hi: 67, v: 9 })} v11 k-12 ${THEME} k0 ${pad(FI_E, { lo: 50, hi: 65, v: 11, rhythm: '2' })}` },
    { name: 'choir', inst: 'choir', vol: 0.35, send: 0.34, mml: `${pad(FI_IN, { lo: 55, hi: 72, v: 7 })} L ${bar4(8)} ${pad([FI_A2, FI_B, FI_C, FI_A].join(' | '), { lo: 55, hi: 72, v: 9 })} ${pad(FI_E, { lo: 55, hi: 72, v: 11 })}` },
    { name: 'ostinato', inst: 'strstac', vol: 0.45, pan: 0.2, mml: `${line(FI_IN, { pat: 'O16 F16 T16 F16', lo: 50, v: 8 })} L ${line(FI_ALL, { pat: 'O16 F16 T16 F16', lo: 50, v: 10 })}` },
    { name: 'bass', inst: 'fbass', vol: 0.6, mml: `${line(FI_IN, { pat: 'R8', lo: 33, v: 11 })} L ${line(FI_ALL, { pat: 'R8 R8 O8 R8 R8 R8 O8 R8', lo: 33, v: 12 })}` },
    { name: 'lowstr', inst: 'lowstr', vol: 0.4, send: 0.3, mml: `v10 o2 d1 | <a1 | L ${line(FI_ALL, { pat: 'R1', lo: 31, v: 11, slash: true })}` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o2 ${roll('d', 32, 3, 12)} | <a4 r4 a4 a8 a8 > |
      L d4 r4 d4 r4 | r1 | r1 | <a4 r4 a4 r4 > | d4 r4 d4 r4 | r1 | r2 <a4 a4 > | d2 r2 |
      ${bar4(8)} ${bar4(7)} <${roll('b', 32, 4, 12)} > |
      e4 r2. | r1 | r1 | <b4 r4 b4 r4 > | e4 r2. | r1 | r1 | r2 <a4 a4 > |
      d4 r4 d4 r4 | d4 r2. | r1 | <a4 r4 a4 a4 > | d4 r4 d4 r4 | r1 | r2 <a4 a8 a8 > | d2 r2 |
      r1 | r1 | <${roll('a', 32, 4, 12)} | a4 a4 a8 a8 a4 > |` },
    kitT('kick', 'k', [['X...............', 1], ['X...X...X...X...', 1], 'L', ['X...X...X...X...', 8], ['X.......X.......', 8], ['X...X...X...X...', 8], ['X.......X.......', 8], ['X.x.X.x.X.x.X.x.', 8], ['X...X...X...X...', 3], ['X.X.X.X.XXXXXXXX', 1]], { vol: 0.5 }),
    kitT('snare', 'm', [[E16, 1], ['....x...x...xxXX', 1], 'L', ['X..x x..x X..x x.xx', 7], ['X.xx X.xx XXXX XXXX', 1], ['....x.......x...', 7], ['....x.......xxXX', 1], ['X..x x..x X..x x.xx', 7], ['XXXXXXXXXXXXXXXX', 1],
      ['....x.......x...', 7], ['....x...x.x.xxXX', 1], ['X..x X..x X..x X.xx', 7], ['X.xx X.xx XXXX XXXX', 1], ['X...X...X...X...', 3], ['gggg oooo xxxx XXXX', 1]], { vol: 0.5, send: 0.2 }),
    kitT('ride', 'y', [[E16, 2], 'L', [E16, 32], ['x.x.x.x.x.x.x.x.', 8], [E16, 4]], { vol: 0.25, pan: 0.3 }),
    kitT('cym', 'c', [[E16, 2], 'L', ['X...............', 1], [E16, 7], ['x...............', 1], [E16, 7], ['X...............', 1], [E16, 7], ['X...............', 1], [E16, 7], ['X...............', 1], [E16, 3], ['X...............', 1], [E16, 3], ['x...............', 1], [E16, 3]], { vol: 0.4, pan: 0.25, send: 0.3 }),
    { name: 'bell', inst: 'bell', vol: 0.4, pan: 0.2, send: 0.45, mml: `r1 | r1 | L ${bar4(32)} v10 o5 d1 | r1 | r1 | r1 | d1 | r1 | r1 | {<a >d}1 | ${bar4(4)}` },
  ],
};

// ============================================================
// 11. ending 结局与制作人员：温暖而感伤，主题完整再现
//    降 B 大调 → D 大调 ♩=84 4/4 · 前奏 2 小节 + 循环 32 小节（长笛新旋律 / 弦乐带出主题“头” / 转 D 大调圆号完整唱出主题 / 尾声经 D 小调回到降 B）
// ============================================================
const ED_IN = 'Bb | Bb';
const ED_A = 'Bb | F/A | Gm | Eb | Bb/F | Eb | Cm7 F | Bb';
const ED_B = 'Gm | Eb | Bb | F | Gm | Eb | Gm6 | A7';
const ED_C = 'D | Bm | G | A | D | F#m | G A | D';
const ED_D = 'G | A | F#m Bm | G A | D | Dm | Gm | F7';
const ED_ALL = [ED_A, ED_B, ED_C, ED_D].join(' | ');
const ED_MEL_A = `o5 d4. c8 <b-4 >f4 | f4. e-8 c2 | d4. c8 <b-4 g4 | b-4 >e-4 g2 | f4. e-8 d4 <b-4 | >g4. f8 e-2 | e-4. d8 c4 <a4 | b-2. r4 |`;
const ED_MEL_B = `o5 d4. d8 g4 a4 | b-2. a8 g8 | f4. e-8 d4 f4 | c2 <a4 >c4 | d4. d8 g4 a4 | b-4. >c8 <b-4 g4 | e2 g2 | a2 g4 e4 |`;
const ED_MEL_D = `o5 b4. a8 g2 | a4. g8 e2 | f+4 c+4 d4 f+4 | g4 <b4 >c+4 e4 | d1 | f2 d2 | <b-2 >d2 | c2 <a4 >e-4 |`;
const ending = {
  name: '余烬与晨曦', key: '降 B 大调 → D 大调', bpm: 84, loop: true,
  desc: '温暖感伤的结局：钢琴分解和弦与长笛开场，弦乐带出主题的“头”，转入 D 大调后圆号与弦乐完整唱出大调化的灰烬王冠主题，尾声经 D 小调回到降 B。',
  reverb: { size: 0.8, damp: 0.5, wet: 0.32 }, send: 0.3,
  chords: [ED_IN, ED_ALL].join(' | '), melody: ['flute', 'strlead', 'horn'],
  tracks: [
    { name: 'flute', inst: 'flute', vol: 1, pan: 0.1, mml: `r1 | r1 | L v12 ${ED_MEL_A} ${bar4(16)} v12 ${ED_MEL_D}` },
    { name: 'strlead', inst: 'strlead', vol: 0.85, pan: -0.1, mml: `r1 | r1 | L ${bar4(8)} v12 ${ED_MEL_B} v10 k12 ${THEME_MAJ} k0 v9 k-12 ${ED_MEL_D} k0` },
    { name: 'horn', inst: 'horn', vol: 0.85, pan: -0.2, mml: `r1 | r1 | L ${bar4(8)} ${line(ED_B, { pat: 'T1', lo: 55, v: 8 })} v12 ${THEME_MAJ} ${pad(ED_D, { lo: 50, hi: 65, v: 8 })}` },
    { name: 'piano', inst: 'piano', vol: 0.45, pan: 0.25, send: 0.32, mml: `${line(ED_IN, { pat: 'R8 F8 O8 T+8 F+8 T+8 O8 F8', lo: 46, v: 9 })} L ${line(ED_ALL, { pat: 'R8 F8 O8 T+8 F+8 T+8 O8 F8', lo: 46, v: 9 })}` },
    { name: 'pad', inst: 'strings', vol: 0.3, send: 0.34, mml: `r1 ${pad('Bb', { lo: 53, hi: 70, v: 6 })} L ${pad(ED_A + ' | ' + ED_B, { lo: 53, hi: 70, v: 7 })} ${pad(ED_C, { lo: 53, hi: 74, n: 4, v: 9, spread: true })} ${pad(ED_D, { lo: 53, hi: 70, v: 7 })}` },
    { name: 'choir', inst: 'choir', vol: 0.3, send: 0.4, mml: `r1 | r1 | L ${bar4(16)} ${pad(ED_C, { lo: 55, hi: 72, v: 8 })} ${bar4(8)}` },
    { name: 'bass', inst: 'lowstr', vol: 0.6, send: 0.25, mml: `v9 o1 b-1 | b-1 | L ${line(ED_A + ' | ' + ED_B, { pat: 'R1', lo: 34, v: 10, slash: true })} ${line(ED_C, { pat: 'R2 F-2', lo: 34, v: 11, slash: true })} ${line(ED_D, { pat: 'R1', lo: 34, v: 10, slash: true })}` },
    { name: 'timp', inst: 'timp', vol: 0.45, mml: `r1 | r1 | L ${bar4(15)} r2 o1 ${roll('a', 16, 3, 11)} | v12 >d4 r2. | ${bar4(7)} ${bar4(4)} d4 r2. | ${bar4(3)}` },
    kitT('cym', 'c', [[E16, 2], 'L', [E16, 15], ['........gggooxxx', 1], ['o...............', 1], [E16, 15]], { vol: 0.35, pan: 0.25, send: 0.35 }),
    { name: 'bell', inst: 'bell', vol: 0.55, pan: 0.2, send: 0.45, mml: `r1 | r1 | L ${bar4(16)} v9 o5 d1 | r1 | r1 | r1 | v8 d1 | r1 | r1 | r1 | ${bar4(4)} v8 d1 | ${bar4(3)}` },
  ],
};

// ============================================================
// 短曲（playJingle）
// ============================================================
// 胜利号角：降 B 大调 ♩=132，三连音号角上行 → IV–V → 主和弦，约 5.5 秒
const victory = {
  name: '胜利', key: '降 B 大调', bpm: 132, loop: false,
  desc: '三连音的小号号角冲上主和弦。',
  reverb: { size: 0.6, damp: 0.4, wet: 0.26 }, send: 0.24,
  chords: 'Bb | Eb:2 F:2 | Bb', melody: ['trumpet'],
  tracks: [
    { name: 'trumpet', inst: 'trumpet', vol: 1, mml: `v13 o4 f12 f12 f12 b-4 >d8 f8 b-4 | g4. f8 a4. >c8 | v14 d1 |` },
    { name: 'trumpet2', inst: 'trumpet', vol: 0.6, pan: 0.2, mml: `v11 o4 d12 d12 d12 f4 b-8 >d8 f4 | e-4. d8 f4. a8 | b-1 |` },
    { name: 'horn', inst: 'horn', vol: 0.4, pan: -0.2, mml: pad('Bb | Eb:2 F:2 | Bb', { lo: 50, hi: 65, v: 11 }) },
    { name: 'strings', inst: 'strings', vol: 0.3, mml: pad('Bb | Eb:2 F:2 | Bb', { lo: 55, hi: 74, n: 4, v: 10 }) },
    { name: 'bass', inst: 'lowstr', vol: 0.6, mml: `v12 o1 b-2 >f2 | e-2 f2 | <b-1 |` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o1 v13 b-4 r2. | r2 >f4 f8 f8 | <${roll('b-', 16, 7, 14)} v15 b-2 |` },
    kitT('snare', 's', [[E16, 1], ['........xxxxXXXX', 1], ['X...............', 1]], { vol: 0.5 }),
    kitT('cym', 'c', [['X...............', 1], [E16, 1], ['X...............', 1]], { vol: 0.4 }),
  ],
};

// 失败：D 小调 ♩=72，A—G—F—E—C♯ 下行落到 D，低音钟一响，约 5 秒
const gameover = {
  name: '败北', key: 'D 小调', bpm: 72, loop: false,
  desc: '弦乐缓缓下行落回 D，合唱与低音钟收尾。',
  reverb: { size: 0.85, damp: 0.5, wet: 0.36 }, send: 0.32,
  chords: 'Dm:1 Bb:1 A7:2 | Dm:2', melody: ['lead'],
  tracks: [
    { name: 'lead', inst: 'strlead', vol: 1, mml: `v12 o4 a4 g8 f8 e4 c+4 | d2` },
    { name: 'pad', inst: 'strings', vol: 0.35, mml: pad('Dm:1 Bb:1 A7:2 | Dm:2', { lo: 53, hi: 69, v: 9 }) },
    { name: 'choir', inst: 'choir', vol: 0.3, mml: pad('Dm:1 Bb:1 A7:2 | Dm:2', { lo: 57, hi: 72, v: 8 }) },
    { name: 'bass', inst: 'lowstr', vol: 0.6, mml: `v11 o2 d4 <b-4 a2 | >d2` },
    { name: 'timp', inst: 'timp', vol: 0.45, mml: `r2 o1 ${roll('a', 16, 3, 10)} | v12 >d2` },
    { name: 'bell', inst: 'bell', vol: 0.4, mml: `r1 | v10 o4 d2` },
  ],
};

// 章节开始：主题的“头”A. A D E | F，定音鼓滚奏推到 D 小调主和弦，约 3.8 秒
const chapter = {
  name: '章节', key: 'D 小调', bpm: 96, loop: false,
  desc: '圆号吹出主题的前两小节，定音鼓滚奏与钟声落在 D 小调。',
  reverb: { size: 0.75, damp: 0.45, wet: 0.32 }, send: 0.3,
  chords: 'Dm | Dm:2', melody: ['horn'],
  tracks: [
    { name: 'horn', inst: 'horn', vol: 1, mml: `v12 o4 a4. a8 >d4 e4 | v13 f2` },
    { name: 'trumpet', inst: 'trumpet', vol: 0.4, pan: 0.2, mml: `r1 | v11 o5 {d a}2` },
    { name: 'pad', inst: 'strings', vol: 0.35, mml: `${pad('Dm', { lo: 50, hi: 65, v: 8 })} ${pad('Dm:2', { lo: 53, hi: 74, n: 4, v: 11 })}` },
    { name: 'bass', inst: 'lowstr', vol: 0.6, mml: `v10 o2 d1 | v12 d2` },
    { name: 'timp', inst: 'timp', vol: 0.5, mml: `o2 ${roll('d', 32, 3, 12)} | v14 d2` },
    { name: 'bell', inst: 'bell', vol: 0.4, mml: `r1 | v10 o5 d2` },
    kitT('cym', 'c', [[E16, 1], ['X.......', 1]], { vol: 0.4 }),
  ],
};

export const MUSIC = { title, sad, calm, tension, prep, player1, player2, enemy, boss, final, ending, victory, gameover, chapter };
for (const [id, def] of Object.entries(MUSIC)) def.id = id;
