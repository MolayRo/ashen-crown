// 《灰烬王冠》软件合成器
//   MML 乐谱解析 → 音符事件 → 音色渲染（芯片方波/三角波/噪声 + “GBA 采样器”风格弦乐/铜管/竖琴/钟/定音鼓…）
//   → 混响/回声 → 响度归一与限幅 → 无缝循环缓冲。
// 纯计算、不依赖 DOM：浏览器主线程、Web Worker、Node（tools/audio）共用同一份代码，保证“分析的就是播放的”。
//
// 循环布局（避免循环点爆音/余音丢失）：
//   连续渲染 [前奏 I][循环第 1 遍 Ls][第 2 遍的前 T 秒][保护区]，
//   loopStart = I + T，loopEnd = I + T + Ls。第 2 遍开头天然带着第 1 遍的余音与混响尾巴，
//   而 T 秒之后两遍内容完全相同（每个音符的振荡器相位/噪声种子只取决于它在乐谱里的位置），
//   所以从 loopEnd 跳回 loopStart 是逐采样连续的。保护区让浏览器插值读到 loopEnd 之后也是正确的延续。

export const TPQ = 48;              // 每个四分音符的 tick 数（三连音 16/8 也是整数）
export const DEFAULT_SR = 32000;    // 渲染采样率：GBA 质感 + 省内存；浏览器会自动重采样到声卡采样率
export const TARGET_LUFS = -16;     // 音乐/短曲统一响度目标
export const CEILING_DB = -1.5;     // 采样峰值上限（dBFS）

const TAU = Math.PI * 2;
const CENT = Math.LN2 / 1200;
const GUARD = 256;                  // 循环尾部保护采样数

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

export function mtof(m) { return 440 * Math.pow(2, (m - 69) / 12); }
export function dbToGain(db) { return Math.pow(10, db / 20); }
export function gainToDb(g) { return 20 * Math.log10(Math.max(1e-12, g)); }

// 确定性随机数（mulberry32）
export function rng(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function hash3(a, b, c) {
  let h = (0x9e3779b9 ^ a) >>> 0;
  h = Math.imul(h ^ (h >>> 16), 0x85ebca6b);
  h = (h ^ (b + 0x632be59b)) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  h = (h ^ Math.imul(c + 1, 0x27d4eb2f)) >>> 0;
  h ^= h >>> 16;
  return h >>> 0;
}

// 正弦表（线性插值），相位以“周”为单位，必须在 [0,1)
const SIN_N = 4096;
const SIN = new Float32Array(SIN_N + 1);
for (let i = 0; i <= SIN_N; i++) SIN[i] = Math.sin(TAU * i / SIN_N);
function sin1(p) {
  const x = p * SIN_N, i = x | 0;
  return SIN[i] + (SIN[i + 1] - SIN[i]) * (x - i);
}
// 任意相位
function sinw(p) { return sin1(p - Math.floor(p)); }

// PolyBLEP 抗混叠修正
function blep(t, dt) {
  if (t < dt) { t /= dt; return t + t - t * t - 1; }
  if (t > 1 - dt) { t = (t - 1) / dt; return t * t + t + t + 1; }
  return 0;
}

// ================================================================
// MML 乐谱
// ================================================================
// 音符 c d e f g a b（+/# 升，- 降），长度 1 2 4 8 16 32（3 6 12 24 为三连音），附点 .，%n 直接写 tick
// r 休止   o4 八度（o4 c = 中央 C）  > < 升/降八度   l8 默认长度   v0~15 力度（v+2/v-2 相对）
// q1~8 发音时值比例   @名字 换音色   p-50~50 声像   k±n 移调   t120 速度   L 循环起点
// { c e g }4 和弦    c4&c8 / c4^8 连音（&后接不同音高 = 连奏滑音）   c8! 重音
// [ ... / ... ]3 重复 3 次（/ 之后的部分最后一遍跳过）   | 小节线（校验对齐）   ; 注释到行尾
const NOTE_PC = { c: 0, d: 2, e: 4, f: 5, g: 7, a: 9, b: 11 };

function lineCol(src, i) {
  let line = 1, col = 1;
  for (let k = 0; k < i && k < src.length; k++) { if (src[k] === '\n') { line++; col = 1; } else col++; }
  return line + ':' + col;
}

export function parseMML(src, opt = {}) {
  const name = opt.name || 'mml';
  const barTicks = opt.barTicks || TPQ * 4;
  const events = [], tempos = [], warnings = [];
  let loopTick = null;
  // 注释替换为空格，保持下标不变（报错位置准确）
  const s = String(src || '').replace(/;[^\n]*/g, (m) => ' '.repeat(m.length));
  const st = { oct: opt.oct ?? 4, len: TPQ, vel: opt.v ?? 12, q: opt.q ?? 8, inst: opt.inst || null, pan: null, trans: 0, tick: 0 };
  let evCount = 0;
  const warn = (msg, i) => warnings.push(`[${name}] ${lineCol(s, i)} ${msg}`);
  const isD = (c) => c >= '0' && c <= '9';
  const skipWs = (i) => { while (i < s.length && s[i] <= ' ') i++; return i; };

  function readInt(i) {
    let j = i, sign = 1;
    if (s[j] === '-') { sign = -1; j++; } else if (s[j] === '+') j++;
    let k = j;
    while (k < s.length && isD(s[k])) k++;
    if (k === j) return [null, i];
    return [sign * parseInt(s.slice(j, k), 10), k];
  }
  function readNum(i) {
    let k = i;
    while (k < s.length && (isD(s[k]) || s[k] === '.')) k++;
    if (k === i) return [null, i];
    return [parseFloat(s.slice(i, k)), k];
  }
  function readLen(i, def) {
    let ticks = def ?? st.len, j = i;
    if (s[j] === '%') {
      const [v, k] = readInt(j + 1);
      if (v == null || v <= 0) warn('% 后需要正整数 tick', j); else { ticks = v; j = k; }
    } else {
      let k = j;
      while (k < s.length && isD(s[k])) k++;
      if (k > j) {
        const n = parseInt(s.slice(j, k), 10);
        if (!n || (TPQ * 4) % n) warn(`长度 ${n} 不能整除全音符`, j);
        ticks = Math.round(TPQ * 4 / (n || 4));
        j = k;
      }
    }
    let add = ticks;
    while (s[j] === '.') { add /= 2; ticks += add; j++; }
    return [Math.round(ticks), j];
  }
  function readPitch(i) {
    let pc = NOTE_PC[s[i]], j = i + 1;
    while (s[j] === '+' || s[j] === '#' || s[j] === '-') { pc += s[j] === '-' ? -1 : 1; j++; }
    return [(st.oct + 1) * 12 + pc + st.trans, j];
  }
  function readChord(i) { // s[i] === '{'
    const save = st.oct, notes = [];
    let j = i + 1;
    while (j < s.length && s[j] !== '}') {
      const c = s[j];
      if (c <= ' ') j++;
      else if (NOTE_PC[c] !== undefined) { const [m, k] = readPitch(j); notes.push(m); j = k; }
      else if (c === '>') { st.oct++; j++; }
      else if (c === '<') { st.oct--; j++; }
      else if (c === 'o') { const [v, k] = readInt(j + 1); if (v != null) st.oct = v; j = k > j + 1 ? k : j + 1; }
      else { warn(`和弦内的未知字符 "${c}"`, j); j++; }
    }
    if (s[j] !== '}') warn('和弦缺少 }', i);
    st.oct = save;
    const [t, k] = readLen(j + 1);
    if (!notes.length) warn('空和弦', i);
    return [notes, t, k];
  }
  function emit(notes, len, accent) {
    const ev = {
      tick: st.tick, len, notes, vel: Math.max(0, Math.min(15, st.vel + (accent ? 3 : 0))) / 15,
      q: st.q, inst: st.inst, pan: st.pan, legato: null, idx: evCount++,
    };
    events.push(ev);
    st.tick += len;
    return ev;
  }
  function accentAt(i) { return s[i] === '!' ? [true, i + 1] : [false, i]; }
  function ties(ev, i) {
    for (;;) {
      const j = skipWs(i);
      if (s[j] === '^') { const [t, k] = readLen(j + 1); ev.len += t; st.tick += t; i = k; continue; }
      if (s[j] === '&') {
        let k = skipWs(j + 1);
        while (s[k] === '<' || s[k] === '>') { st.oct += s[k] === '>' ? 1 : -1; k = skipWs(k + 1); }
        if (NOTE_PC[s[k]] !== undefined) {
          const [m, k2] = readPitch(k);
          const [t, k3] = readLen(k2);
          const last = ev.legato ? ev.legato[ev.legato.length - 1][1] : ev.notes[0];
          if (m !== last) {
            if (ev.notes.length === 1) (ev.legato || (ev.legato = [])).push([ev.len, m]);
            else warn('和弦只能与相同和弦连音', k);
          }
          ev.len += t; st.tick += t; i = k3; continue;
        }
        if (s[k] === '{') { const [, t, k2] = readChord(k); ev.len += t; st.tick += t; i = k2; continue; }
        warn('& 后面需要音符', j); i = j + 1; continue;
      }
      return i;
    }
  }

  function run(i0, i1) {
    let i = i0;
    while (i < i1) {
      const c = s[i];
      if (c <= ' ') { i++; continue; }
      if (NOTE_PC[c] !== undefined) {
        const [m, j] = readPitch(i);
        const [t, k] = readLen(j);
        const [acc, k2] = accentAt(k);
        const ev = emit([m], t, acc);
        i = ties(ev, k2);
        continue;
      }
      switch (c) {
        case 'r': { const [t, j] = readLen(i + 1); st.tick += t; i = j; break; }
        case 'o': { const [v, j] = readInt(i + 1); if (v == null) warn('o 后需要数字', i); else st.oct = v; i = Math.max(j, i + 1); break; }
        case '>': st.oct++; i++; break;
        case '<': st.oct--; i++; break;
        case 'l': { const [t, j] = readLen(i + 1, TPQ); st.len = t; i = j; break; }
        case 'v': {
          if (s[i + 1] === '+' || s[i + 1] === '-') { const [v, j] = readInt(i + 1); if (v != null) st.vel = Math.max(0, Math.min(15, st.vel + v)); i = Math.max(j, i + 2); }
          else { const [v, j] = readInt(i + 1); if (v == null) warn('v 后需要数字', i); else st.vel = Math.max(0, Math.min(15, v)); i = Math.max(j, i + 1); }
          break;
        }
        case 'q': { const [v, j] = readInt(i + 1); if (v == null || v < 1 || v > 8) warn('q 取 1~8', i); else st.q = v; i = Math.max(j, i + 1); break; }
        case '@': {
          let j = i + 1;
          while (j < s.length && /[A-Za-z0-9_]/.test(s[j])) j++;
          if (j === i + 1) warn('@ 后需要音色名', i); else st.inst = s.slice(i + 1, j);
          i = j; break;
        }
        case 'p': { const [v, j] = readInt(i + 1); st.pan = v == null ? null : Math.max(-1, Math.min(1, v / 50)); i = Math.max(j, i + 1); break; }
        case 'k': { const [v, j] = readInt(i + 1); if (v == null) warn('k 后需要数字', i); else st.trans = v; i = Math.max(j, i + 1); break; }
        case 't': { const [v, j] = readNum(i + 1); if (!v) warn('t 后需要速度', i); else tempos.push([st.tick, v]); i = Math.max(j, i + 1); break; }
        case 'L': if (loopTick != null && loopTick !== st.tick) warn('重复的循环点 L', i); loopTick = st.tick; i++; break;
        case '|': if (st.tick % barTicks) warn(`小节线未对齐：第 ${Math.floor(st.tick / barTicks) + 1} 小节多出 ${st.tick % barTicks} tick`, i); i++; break;
        case '{': { const [notes, t, k] = readChord(i); const [acc, k2] = accentAt(k); const ev = emit(notes, t, acc); i = ties(ev, k2); break; }
        case '[': {
          let depth = 0, j = i, brk = -1;
          for (; j < i1; j++) {
            if (s[j] === '[') depth++;
            else if (s[j] === ']') { depth--; if (depth === 0) break; }
            else if (s[j] === '/' && depth === 1) brk = j;
          }
          if (j >= i1) { warn('缺少 ]', i); j = i1; }
          let [n, k] = readInt(j + 1);
          if (n == null) { n = 2; k = j + 1; }
          for (let r = 0; r < n; r++) run(i + 1, r === n - 1 && brk >= 0 ? brk : j);
          i = k; break;
        }
        case ']': warn('多余的 ]', i); i++; break;
        case '/': i++; break; // 重复体内“最后一遍跳过”的分隔符：非最后一遍时忽略
        case '&': case '^': warn('连音符号前没有音符', i); i++; break;
        default: warn(`未知字符 "${c}"`, i); i++; break;
      }
    }
  }
  run(0, s.length);
  return { events, tempos, loopTick, endTick: st.tick, warnings };
}

// ================================================================
// 音色表（时间单位秒）
// engine: sub 减法合成 | add 加法合成(拨弦/钢琴/定音鼓/管风琴/钟琴) | fm 调频(钟) | choir 人声 | kit 鼓组
// env: a 起音(线性) d 衰减时间常数 s 持续电平 r 释音时间常数
// ================================================================
export const INSTRUMENTS = {
  // —— 芯片方波/三角波 ——
  sq12: { engine: 'sub', osc: [{ w: 'pulse', duty: 0.125 }], amp: 0.24, env: { a: 0.004, d: 0.5, s: 0.72, r: 0.07 },
    vib: { delay: 0.22, rate: 5.8, depth: 13 }, filter: { type: 'lp', f: 6500, q: 0.6 } },
  sq25: { engine: 'sub', osc: [{ w: 'pulse', duty: 0.25 }], amp: 0.19, env: { a: 0.004, d: 0.5, s: 0.72, r: 0.07 },
    vib: { delay: 0.22, rate: 5.8, depth: 13 }, filter: { type: 'lp', f: 6500, q: 0.6 } },
  sq50: { engine: 'sub', osc: [{ w: 'pulse', duty: 0.5 }], amp: 0.17, env: { a: 0.004, d: 0.5, s: 0.72, r: 0.07 },
    vib: { delay: 0.22, rate: 5.8, depth: 13 }, filter: { type: 'lp', f: 6000, q: 0.6 } },
  // 短促的方波（琶音/伴奏）
  sqpluck: { engine: 'sub', osc: [{ w: 'pulse', duty: 0.25 }], amp: 0.43, env: { a: 0.002, d: 0.12, s: 0.25, r: 0.05 },
    filter: { type: 'lp', mul: 3, env: 5, ed: 0.08, q: 0.7, min: 400 } },
  // GBA 波形通道感的三角波贝斯（4 bit 量化）
  tri: { engine: 'sub', osc: [{ w: 'tri4' }], amp: 0.3, env: { a: 0.003, d: 0.6, s: 0.88, r: 0.045 } },
  trisoft: { engine: 'sub', osc: [{ w: 'tri' }], amp: 0.3, env: { a: 0.006, d: 0.8, s: 0.9, r: 0.08 } },

  // —— “GBA 采样器”风格 ——
  strings: { engine: 'sub', osc: [{ w: 'saw', det: -9, ph: 0.1 }, { w: 'saw', det: 0, ph: 0.45 }, { w: 'saw', det: 9, ph: 0.8 }],
    amp: 0.15, filter: { type: 'lp', f: 2500, key: 0.35, q: 0.65, vel: 0.5 }, env: { a: 0.2, d: 0.6, s: 0.9, r: 0.42 },
    vib: { delay: 0.35, rate: 5.2, depth: 9 } },
  strlead: { engine: 'sub', osc: [{ w: 'saw', det: -7, ph: 0.1 }, { w: 'saw', det: 0, ph: 0.45 }, { w: 'saw', det: 7, ph: 0.8 }],
    amp: 0.15, filter: { type: 'lp', f: 3200, key: 0.4, q: 0.7, vel: 0.5 }, env: { a: 0.07, d: 0.6, s: 0.9, r: 0.3 },
    vib: { delay: 0.25, rate: 5.4, depth: 13 } },
  strstac: { engine: 'sub', osc: [{ w: 'saw', det: -8, ph: 0.1 }, { w: 'saw', det: 0, ph: 0.45 }, { w: 'saw', det: 8, ph: 0.8 }],
    amp: 0.28, filter: { type: 'lp', f: 2400, key: 0.35, q: 0.7, env: 0.8, ed: 0.06, vel: 0.6 }, env: { a: 0.008, d: 0.14, s: 0.45, r: 0.07 } },
  lowstr: { engine: 'sub', osc: [{ w: 'saw', det: -6, ph: 0.2 }, { w: 'saw', det: 6, ph: 0.7 }, { w: 'tri', lv: 0.6 }],
    amp: 0.19, filter: { type: 'lp', f: 900, key: 0.5, q: 0.7, vel: 0.4 }, env: { a: 0.08, d: 0.8, s: 0.9, r: 0.3 } },
  brass: { engine: 'sub', osc: [{ w: 'saw', det: -5, ph: 0.2 }, { w: 'saw', det: 5, ph: 0.6 }],
    amp: 0.19, filter: { type: 'lp', mul: 1.8, env: 4.5, ea: 0.03, ed: 0.32, q: 1.2, min: 350, vel: 0.8 },
    env: { a: 0.03, d: 0.35, s: 0.82, r: 0.11 }, vib: { delay: 0.3, rate: 5.5, depth: 11 }, pitch: { amt: -0.4, time: 0.035 } },
  trumpet: { engine: 'sub', osc: [{ w: 'saw', det: -4, ph: 0.2 }, { w: 'saw', det: 4, ph: 0.6 }],
    amp: 0.19, filter: { type: 'lp', mul: 2.4, env: 5.5, ea: 0.02, ed: 0.25, q: 1.3, min: 500, vel: 0.9 },
    env: { a: 0.022, d: 0.3, s: 0.8, r: 0.09 }, vib: { delay: 0.28, rate: 5.8, depth: 12 }, pitch: { amt: -0.5, time: 0.03 } },
  horn: { engine: 'sub', osc: [{ w: 'saw', det: -6, ph: 0.2 }, { w: 'saw', det: 6, ph: 0.6 }, { w: 'tri', lv: 0.5 }],
    amp: 0.18, filter: { type: 'lp', mul: 1.3, env: 2.2, ea: 0.06, ed: 0.4, q: 0.9, min: 250, vel: 0.7 },
    env: { a: 0.06, d: 0.5, s: 0.88, r: 0.18 }, vib: { delay: 0.35, rate: 5, depth: 8 }, pitch: { amt: -0.25, time: 0.05 } },
  flute: { engine: 'sub', osc: [{ w: 'sine' }, { w: 'tri', lv: 0.16 }], amp: 0.23, env: { a: 0.045, d: 0.4, s: 0.86, r: 0.12 },
    vib: { delay: 0.2, rate: 5, depth: 15 }, noise: { lv: 0.035, chiff: 0.22, cd: 0.035, bp: 2.2, q: 1.2 } },
  clarinet: { engine: 'sub', osc: [{ w: 'pulse', duty: 0.5 }, { w: 'sine', lv: 0.4 }], amp: 0.13,
    filter: { type: 'lp', mul: 3.2, q: 0.8, min: 500 }, env: { a: 0.03, d: 0.4, s: 0.86, r: 0.1 }, vib: { delay: 0.3, rate: 5, depth: 7 } },
  oboe: { engine: 'sub', osc: [{ w: 'pulse', duty: 0.22 }, { w: 'saw', lv: 0.4, ph: 0.3 }], amp: 0.17,
    filter: { type: 'lp', mul: 4, q: 1.6, min: 900 }, env: { a: 0.035, d: 0.4, s: 0.85, r: 0.1 }, vib: { delay: 0.25, rate: 5.3, depth: 10 } },
  choir: { engine: 'choir', amp: 0.44, env: { a: 0.28, d: 0.8, s: 0.92, r: 0.5 }, vib: { delay: 0.35, rate: 5, depth: 11 },
    formants: [[640, 1.0, 5], [1100, 0.5, 7], [2600, 0.16, 9]] },
  organ: { engine: 'add', amp: 0.15, env: { a: 0.05, d: 1, s: 1, r: 0.22 },
    partials: [[0.5, 0.55, 0], [1, 1, 0], [2, 0.55, 0], [3, 0.28, 0], [4, 0.22, 0], [6, 0.1, 0], [8, 0.07, 0]], vib: { delay: 0.1, rate: 6.2, depth: 4 } },
  harp: { engine: 'add', amp: 0.25, env: { a: 0.002, d: 99, s: 1, r: 0.35 }, decayKey: 0.5,
    partials: [[1, 1, 1.5], [2, 0.42, 0.95], [3, 0.2, 0.62], [4, 0.12, 0.45], [5, 0.06, 0.34], [6, 0.035, 0.28]],
    noise: { lv: 0.06, decay: 0.004, lp: 3000 }, velBright: 0.3 },
  pizz: { engine: 'add', amp: 0.28, env: { a: 0.002, d: 99, s: 1, r: 0.08 }, decayKey: 0.35,
    partials: [[1, 1, 0.3], [2, 0.5, 0.2], [3, 0.3, 0.12], [4, 0.15, 0.08], [5, 0.07, 0.06]], noise: { lv: 0.05, decay: 0.004, lp: 2000 } },
  piano: { engine: 'add', amp: 0.23, env: { a: 0.002, d: 99, s: 1, r: 0.28 }, decayKey: 0.6, stretch: 0.0004, velBright: 0.5,
    partials: [[1, 1, 1.9], [2, 0.5, 1.25], [3, 0.3, 0.85], [4, 0.17, 0.6], [5, 0.1, 0.45], [6, 0.06, 0.35], [7, 0.035, 0.3]],
    noise: { lv: 0.09, decay: 0.005, lp: 2400 } },
  bell: { engine: 'fm', amp: 0.14, ratio: 3.5, index: 3.2, isus: 0.25, idec: 0.7, env: { a: 0.002, d: 2.4, s: 0, r: 1.0 } },
  chime: { engine: 'fm', amp: 0.18, ratio: 2.0, index: 1.6, isus: 0.1, idec: 0.4, env: { a: 0.002, d: 1.4, s: 0, r: 0.6 } },
  glock: { engine: 'add', amp: 0.27, env: { a: 0.001, d: 99, s: 1, r: 0.3 },
    partials: [[1, 1, 1.1], [2.76, 0.32, 0.32], [5.4, 0.14, 0.14], [8.93, 0.06, 0.07]] },
  timp: { engine: 'add', amp: 0.41, mono: true, env: { a: 0.003, d: 99, s: 1, r: 0.6 }, pitch: { amt: 0.35, time: 0.05 },
    partials: [[1, 1, 1.15], [1.5, 0.45, 0.72], [1.98, 0.26, 0.5], [2.44, 0.12, 0.36], [2.9, 0.06, 0.26], [0.52, 0.35, 0.16]],
    noise: { lv: 0.3, decay: 0.03, lp: 450 } },
  fbass: { engine: 'sub', osc: [{ w: 'saw', ph: 0.3 }, { w: 'tri', lv: 0.9 }], amp: 0.44,
    filter: { type: 'lp', mul: 2.5, env: 5, ed: 0.1, q: 0.8, min: 160 }, env: { a: 0.004, d: 0.45, s: 0.55, r: 0.06 } },
  kit: { engine: 'kit', amp: 0.62, mono: true }, // 每条鼓轨只放一种鼓，新的一击掐断上一击（滚奏不会越叠越响）
};

// 允许曲目内定义变体：{ base: 'strings', env: {...} } —— 顶层字段浅合并
let instSerial = 0;
const resolved = new WeakMap();
export function resolveInstrument(name, local) {
  const raw = (local && local[name]) || INSTRUMENTS[name];
  if (!raw) return null;
  let r = resolved.get(raw);
  if (r) return r;
  if (raw.base) {
    const b = resolveInstrument(raw.base, raw.base === name ? null : local);
    if (!b) return null;
    r = { ...b, ...raw };
    delete r.base;
  } else r = { ...raw };
  r.__id = 'i' + (++instSerial); // 缓存键用
  resolved.set(raw, r);
  return r;
}

const WAVE = { saw: 0, pulse: 1, square: 1, tri: 2, sine: 3, tri4: 4, noise: 5 };

// ================================================================
// 声部渲染
// v: { s0 起点, s1 松键点, cut 单音轨截断点(-1 无), f 频率, segs 连奏[[偏移, 频率]], vel, amp, pl, pr, send, echo, seed, midi }
// o: { sr, len, L, R, S(混响发送), E(回声发送) }
// ================================================================
function envConsts(env, sr) {
  return {
    aInc: 1 / Math.max(1, (env.a || 0.001) * sr),
    dMul: env.d > 0 ? Math.exp(-1 / (env.d * sr)) : 0,
    sus: env.s ?? 1,
    rMul: Math.exp(-1 / (Math.max(0.003, env.r ?? 0.05) * sr)),
  };
}

function vibConsts(vib, sr) {
  if (!vib) return null;
  return { delay: vib.delay * sr, ramp: Math.max(1, (vib.ramp ?? 0.25) * sr), rate16: vib.rate * 16 / sr, depth: vib.depth * CENT };
}

// 声部结束处理：单音轨截断（5ms 淡出）或余音上限（150ms 淡出）。返回 [循环上限, 淡出起点, 淡出长度]
function voiceEnd(v, o) {
  const lim = o.len - v.s0;
  let fs = 1e15, fl = 1;
  if (v.maxN > 0) { fl = Math.max(1, Math.round(0.15 * o.sr)); fs = v.maxN - fl; }
  if (v.cut >= 0) {
    const c = v.cut - v.s0;
    if (c < fs) { fs = c; fl = Math.max(1, Math.round(0.005 * o.sr)); }
  }
  return [Math.min(lim, fs + fl), fs, fl];
}

// 松键后最长余音（秒）。用于限制声部长度并决定循环尾巴 T 的长度
const RING_CAP = 6;
const REL_FLOOR = 1e-3; // 释音衰减到 -60 dB 即结束（混音里早已听不见）
export function ringTime(ins) {
  if (!ins) return 0;
  if (ins.engine === 'kit') return 3.2;
  return Math.min(ins.ring ?? RING_CAP, 6.9 * Math.max(0.003, ins.env?.r ?? 0.05));
}

function vSub(I, v, o) {
  const sr = o.sr, L = o.L, R = o.R, S = o.S, E = o.E;
  const n0 = v.s0;
  const [lenMax, fs, fl] = voiceEnd(v, o);
  if (lenMax <= 0) return;
  const { aInc, dMul, sus, rMul } = envConsts(I.env, sr);
  const gate = v.s1 - n0;
  const oscs = I.osc, no = oscs.length;
  const ph = new Float64Array(no), mul = new Float64Array(no), lv = new Float64Array(no);
  const dut = new Float64Array(no), typ = new Int32Array(no), dt = new Float64Array(no);
  for (let k = 0; k < no; k++) {
    const oc = oscs[k];
    ph[k] = oc.ph || 0;
    mul[k] = Math.pow(2, (oc.det || 0) / 1200 + (oc.oct || 0));
    lv[k] = oc.lv ?? 1;
    dut[k] = oc.duty ?? 0.5;
    typ[k] = WAVE[oc.w] ?? 0;
  }
  const rnd = rng(v.seed);
  // 滤波器（TPT 状态变量滤波器）
  const F = I.filter;
  let ftype = -1, fk = 1, fBase = 0, fEnv = 0, fAinc = 1, fD16 = 0, fMin = 20, fe = 0, feStage = 0;
  if (F) {
    ftype = F.type === 'hp' ? 2 : F.type === 'bp' ? 1 : 0;
    fk = 1 / (F.q || 0.707);
    fBase = F.mul ? F.mul * v.f : (F.f || 2000) * Math.pow(v.f / 261.63, F.key || 0);
    if (F.vel) fBase *= Math.pow(2, (v.vel - 0.8) * F.vel * 2);
    fEnv = F.env || 0;
    fAinc = F.ea ? 16 / (F.ea * sr) : 1;
    fD16 = F.ed ? Math.exp(-16 / (F.ed * sr)) : 0;
    fMin = F.min || 20;
    if (!fEnv) { fe = 0; feStage = 2; }
  }
  let ic1 = 0, ic2 = 0, a1 = 0, a2 = 0, a3 = 0;
  // 气声/吹口噪声
  const NZ = I.noise;
  let nzA1 = 0, nzA2 = 0, nzA3 = 0, nzK = 1, nzI1 = 0, nzI2 = 0, chiff = 0, chiffMul = 0, nzLv = 0;
  if (NZ) {
    const fc = Math.min(0.45 * sr, v.f * (NZ.bp || 2));
    const g = Math.tan(Math.PI * fc / sr);
    nzK = 1 / (NZ.q || 1);
    nzA1 = 1 / (1 + g * (g + nzK)); nzA2 = g * nzA1; nzA3 = g * nzA2;
    chiff = NZ.chiff || 0; chiffMul = Math.exp(-1 / ((NZ.cd || 0.03) * sr)); nzLv = NZ.lv || 0;
  }
  const vb = vibConsts(I.vib, sr);
  const pe = I.pitch;
  const peN = pe ? pe.time * sr : 1;
  const segs = v.segs;
  let segI = 0, fCur = v.f;
  const glideMul = segs ? Math.exp(-16 / ((I.glide || 0.025) * sr)) : 0;
  let fGlide = v.f;
  let e = 0, stage = 0, vibPh = 0;
  const gl = v.amp * v.pl, gr = v.amp * v.pr, gs = v.amp * v.send, ge = v.amp * v.echo;
  for (let i = 0; i < lenMax; i++) {
    if ((i & 15) === 0) {
      if (segs) {
        while (segI < segs.length && i >= segs[segI][0]) fCur = segs[segI++][1];
        fGlide = fCur + (fGlide - fCur) * glideMul;
      } else fGlide = fCur;
      let f = fGlide;
      if (pe) f *= Math.pow(2, pe.amt * Math.exp(-i / peN) / 12);
      if (vb && i >= vb.delay) {
        const d = vb.depth * Math.min(1, (i - vb.delay) / vb.ramp);
        f *= 1 + d * sin1(vibPh);
        vibPh += vb.rate16; if (vibPh >= 1) vibPh -= 1;
      }
      const inv = f / sr;
      for (let k = 0; k < no; k++) dt[k] = inv * mul[k];
      if (ftype >= 0) {
        let fc = fBase * (1 + fEnv * fe);
        if (fc < fMin) fc = fMin;
        if (fc > 0.45 * sr) fc = 0.45 * sr;
        const g = Math.tan(Math.PI * fc / sr);
        a1 = 1 / (1 + g * (g + fk)); a2 = g * a1; a3 = g * a2;
        if (feStage === 0) { fe += fAinc; if (fe >= 1) { fe = 1; feStage = 1; } } else if (feStage === 1) fe *= fD16;
      }
    }
    // 包络
    if (stage === 0) { e += aInc; if (e >= 1) { e = 1; stage = 1; } if (i >= gate) stage = 2; }
    else if (stage === 1) { e = sus + (e - sus) * dMul; if (i >= gate) stage = 2; else if (sus === 0 && e < REL_FLOOR) break; }
    else { e *= rMul; if (e < REL_FLOOR) break; }
    let amp = e;
    if (i >= fs) { const c = 1 - (i - fs) / fl; if (c <= 0) break; amp *= c; }
    // 振荡器
    let x = 0;
    for (let k = 0; k < no; k++) {
      const p = ph[k], d = dt[k];
      let y;
      switch (typ[k]) {
        case 0: y = 2 * p - 1 - blep(p, d); break;
        case 1: { const w = dut[k]; y = (p < w ? 1 : -1) + blep(p, d) - blep(p >= w ? p - w : p - w + 1, d) - (2 * w - 1); break; }
        case 2: y = 4 * Math.abs(p - 0.5) - 1; break;
        case 3: y = sin1(p); break;
        case 4: y = Math.round((4 * Math.abs(p - 0.5) - 1) * 7.5) / 7.5; break;
        default: y = rnd() * 2 - 1;
      }
      let np = p + d; if (np >= 1) np -= 1; ph[k] = np;
      x += y * lv[k];
    }
    if (NZ) {
      const n = rnd() * 2 - 1;
      const v3 = n - nzI2, v1 = nzA1 * nzI1 + nzA2 * v3, v2 = nzI2 + nzA2 * nzI1 + nzA3 * v3;
      nzI1 = 2 * v1 - nzI1; nzI2 = 2 * v2 - nzI2;
      x += v1 * nzK * (nzLv + chiff) * 3;
      chiff *= chiffMul;
    }
    if (ftype >= 0) {
      const v3 = x - ic2, v1 = a1 * ic1 + a2 * v3, v2 = ic2 + a2 * ic1 + a3 * v3;
      ic1 = 2 * v1 - ic1; ic2 = 2 * v2 - ic2;
      x = ftype === 0 ? v2 : ftype === 1 ? v1 * fk : x - fk * v1 - v2;
    }
    const y = x * amp, idx = n0 + i;
    L[idx] += y * gl; R[idx] += y * gr; S[idx] += y * gs; E[idx] += y * ge;
  }
}

// 加法合成：每个分音独立衰减（竖琴、拨弦、钢琴、钟琴、定音鼓、管风琴）
function vAdd(I, v, o) {
  const sr = o.sr, L = o.L, R = o.R, S = o.S, E = o.E;
  const n0 = v.s0;
  const [lenMax, fs, fl] = voiceEnd(v, o);
  if (lenMax <= 0) return;
  const P = I.partials, f0 = v.f;
  const kScale = I.decayKey ? Math.pow(261.63 / f0, I.decayKey) : 1;
  const B = I.stretch || 0;
  const np = P.length;
  const ph = new Float64Array(np), rat = new Float64Array(np), am = new Float64Array(np), dm = new Float64Array(np), dt = new Float64Array(np);
  let used = 0;
  for (let k = 0; k < np; k++) {
    const [r, l, d] = P[k];
    const ratio = B ? r * Math.sqrt(1 + B * r * r) : r;
    if (f0 * ratio > 0.45 * sr) continue;
    let lvl = l;
    if (I.velBright && r > 1) lvl *= Math.pow(Math.max(0.05, v.vel), I.velBright * (r - 1));
    rat[used] = ratio; am[used] = lvl;
    dm[used] = d > 0 ? Math.exp(-1 / (d * kScale * sr)) : 1;
    ph[used] = (k * 0.381966) % 1;
    used++;
  }
  const { aInc, dMul, sus, rMul } = envConsts(I.env, sr);
  const gate = v.s1 - n0;
  const rnd = rng(v.seed);
  const NZ = I.noise;
  let nzAmp = NZ ? NZ.lv : 0, lp = 0;
  const nzMul = NZ ? Math.exp(-1 / (NZ.decay * sr)) : 0;
  const nzC = NZ ? 1 - Math.exp(-TAU * (NZ.lp || 2000) / sr) : 0;
  const pe = I.pitch, peN = pe ? pe.time * sr : 1;
  const vb = vibConsts(I.vib, sr);
  let vibPh = 0;
  let e = 0, stage = 0;
  const gl = v.amp * v.pl, gr = v.amp * v.pr, gs = v.amp * v.send, ge = v.amp * v.echo;
  for (let i = 0; i < lenMax; i++) {
    if ((i & 15) === 0) {
      let f = f0;
      if (pe) f *= Math.pow(2, pe.amt * Math.exp(-i / peN) / 12);
      if (vb && i >= vb.delay) {
        const d = vb.depth * Math.min(1, (i - vb.delay) / vb.ramp);
        f *= 1 + d * sin1(vibPh);
        vibPh += vb.rate16; if (vibPh >= 1) vibPh -= 1;
      }
      if ((i & 255) === 0 && i > 0) {
        // 剔除已衰减到听不见的分音（分音振幅只会减小），全部衰减完就提前结束
        let sum = nzAmp, w = 0;
        for (let k = 0; k < used; k++) {
          if (am[k] * e < 1e-5) continue;
          ph[w] = ph[k]; rat[w] = rat[k]; am[w] = am[k]; dm[w] = dm[k]; sum += am[k]; w++;
        }
        used = w;
        if (sum * e < REL_FLOOR) break;
      }
      const inv = f / sr;
      for (let k = 0; k < used; k++) dt[k] = inv * rat[k];
    }
    if (stage === 0) { e += aInc; if (e >= 1) { e = 1; stage = 1; } if (i >= gate) stage = 2; }
    else if (stage === 1) { e = sus + (e - sus) * dMul; if (i >= gate) stage = 2; }
    else { e *= rMul; if (e < REL_FLOOR) break; }
    let amp = e;
    if (i >= fs) { const c = 1 - (i - fs) / fl; if (c <= 0) break; amp *= c; }
    let x = 0;
    for (let k = 0; k < used; k++) {
      const p = ph[k];
      x += am[k] * sin1(p);
      let q = p + dt[k]; if (q >= 1) q -= 1; ph[k] = q;
      am[k] *= dm[k];
    }
    if (NZ && nzAmp > 1e-6) {
      lp += nzC * ((rnd() * 2 - 1) - lp);
      x += lp * nzAmp * 2;
      nzAmp *= nzMul;
    }
    const y = x * amp, idx = n0 + i;
    L[idx] += y * gl; R[idx] += y * gr; S[idx] += y * gs; E[idx] += y * ge;
  }
}

// 双算子调频（钟声、风铃）
function vFM(I, v, o) {
  const sr = o.sr, L = o.L, R = o.R, S = o.S, E = o.E;
  const n0 = v.s0;
  const [lenMax, fs, fl] = voiceEnd(v, o);
  if (lenMax <= 0) return;
  const { aInc, dMul, sus, rMul } = envConsts(I.env, sr);
  const gate = v.s1 - n0;
  const dc = v.f * (I.cr || 1) / sr, dmod = v.f * I.ratio / sr;
  let idx0 = I.index * (0.5 + 0.5 * v.vel);
  const isus = I.isus || 0, im = Math.exp(-1 / ((I.idec || 0.5) * sr));
  let pc = 0, pm = 0, e = 0, stage = 0;
  const gl = v.amp * v.pl, gr = v.amp * v.pr, gs = v.amp * v.send, ge = v.amp * v.echo;
  for (let i = 0; i < lenMax; i++) {
    if (stage === 0) { e += aInc; if (e >= 1) { e = 1; stage = 1; } if (i >= gate) stage = 2; }
    else if (stage === 1) { e = sus + (e - sus) * dMul; if (i >= gate) stage = 2; else if (sus === 0 && e < REL_FLOOR) break; }
    else { e *= rMul; if (e < REL_FLOOR) break; }
    let amp = e;
    if (i >= fs) { const c = 1 - (i - fs) / fl; if (c <= 0) break; amp *= c; }
    const m = sin1(pm) * idx0;
    const x = sinw(pc + m);
    pc += dc; if (pc >= 1) pc -= 1;
    pm += dmod; if (pm >= 1) pm -= 1;
    idx0 = isus + (idx0 - isus) * im;
    const y = x * amp, id = n0 + i;
    L[id] += y * gl; R[id] += y * gr; S[id] += y * gs; E[id] += y * ge;
  }
}

// 人声“啊”：去谐锯齿波 → 三个共振峰带通
function vChoir(I, v, o) {
  const sr = o.sr, L = o.L, R = o.R, S = o.S, E = o.E;
  const n0 = v.s0;
  const [lenMax, fs, fl] = voiceEnd(v, o);
  if (lenMax <= 0) return;
  const { aInc, dMul, sus, rMul } = envConsts(I.env, sr);
  const gate = v.s1 - n0;
  const det = [-11, 0, 11].map((c) => Math.pow(2, c / 1200));
  const ph = [0.13, 0.52, 0.86];
  const FM = I.formants, nf = FM.length;
  const fa1 = [], fa2 = [], fa3 = [], fk = [], fg = [], i1 = new Float64Array(nf), i2 = new Float64Array(nf);
  for (let k = 0; k < nf; k++) {
    const [fc, gain, q] = FM[k];
    const g = Math.tan(Math.PI * Math.min(fc, 0.45 * sr) / sr);
    fk[k] = 1 / q;
    fa1[k] = 1 / (1 + g * (g + fk[k])); fa2[k] = g * fa1[k]; fa3[k] = g * fa2[k]; fg[k] = gain * fk[k];
  }
  const vb = vibConsts(I.vib, sr);
  let vibPh = 0, e = 0, stage = 0, dt = v.f / sr, lp = 0;
  const gl = v.amp * v.pl, gr = v.amp * v.pr, gs = v.amp * v.send, ge = v.amp * v.echo;
  for (let i = 0; i < lenMax; i++) {
    if ((i & 15) === 0) {
      let f = v.f;
      if (vb && i >= vb.delay) {
        const d = vb.depth * Math.min(1, (i - vb.delay) / vb.ramp);
        f *= 1 + d * sin1(vibPh);
        vibPh += vb.rate16; if (vibPh >= 1) vibPh -= 1;
      }
      dt = f / sr;
    }
    if (stage === 0) { e += aInc; if (e >= 1) { e = 1; stage = 1; } if (i >= gate) stage = 2; }
    else if (stage === 1) { e = sus + (e - sus) * dMul; if (i >= gate) stage = 2; }
    else { e *= rMul; if (e < REL_FLOOR) break; }
    let amp = e;
    if (i >= fs) { const c = 1 - (i - fs) / fl; if (c <= 0) break; amp *= c; }
    let src = 0;
    for (let k = 0; k < 3; k++) {
      const d = dt * det[k], p = ph[k];
      src += 2 * p - 1 - blep(p, d);
      let q = p + d; if (q >= 1) q -= 1; ph[k] = q;
    }
    let x = 0;
    for (let k = 0; k < nf; k++) {
      const v3 = src - i2[k], v1 = fa1[k] * i1[k] + fa2[k] * v3, v2 = i2[k] + fa2[k] * i1[k] + fa3[k] * v3;
      i1[k] = 2 * v1 - i1[k]; i2[k] = 2 * v2 - i2[k];
      x += v1 * fg[k];
    }
    lp += 0.08 * (src - lp);
    x += lp * 0.12;
    const y = x * amp, id = n0 + i;
    L[id] += y * gl; R[id] += y * gr; S[id] += y * gs; E[id] += y * ge;
  }
}

// —— 鼓组 ——（音高类别选鼓：c 底鼓 c+ 边击 d 军鼓 d+ 进行曲军鼓 e 低嗵 f 中嗵 f+ 闭镲 g 高嗵 g+ 踩镲 a 开镲 a+ 叮叮镲 b 吊镲）
const KIT_MAP = ['kick', 'rim', 'snare', 'msnare', 'tomL', 'tomM', 'hat', 'tomH', 'phat', 'ohat', 'ride', 'crash'];
export const DRUMS = {
  kick: { f0: 150, f1: 47, pt: 0.03, decay: 0.17, click: 0.5, len: 0.5, gain: 0.72 },
  snare: { tone: 188, tone2: 330, td: 0.05, nd: 0.13, hp: 1300, lp: 9000, mixT: 0.55, mixN: 0.85, len: 0.45, gain: 0.63 },
  msnare: { tone: 205, tone2: 360, td: 0.04, nd: 0.17, hp: 1800, lp: 10000, mixT: 0.4, mixN: 1.0, len: 0.55, gain: 0.49 },
  rim: { f: 1750, d: 0.012, gain: 1.2, len: 0.08 },
  hat: { d: 0.036, hp: 7200, gain: 1.77, len: 0.2 },
  phat: { d: 0.02, hp: 6500, gain: 2.2, len: 0.12 },
  ohat: { d: 0.26, hp: 6800, gain: 0.7, len: 1.1 },
  ride: { d: 0.55, hp: 5200, gain: 0.89, len: 1.8 },
  crash: { d: 0.95, hp: 3600, gain: 0.48, len: 3.2 },
  tomL: { f: 92, d: 0.34, gain: 0.55, len: 0.9 },
  tomM: { f: 128, d: 0.28, gain: 0.54, len: 0.8 },
  tomH: { f: 172, d: 0.23, gain: 0.56, len: 0.7 },
};
const METAL = [205.3, 304.4, 369.6, 522.7, 540, 800];

function vKit(I, v, o) {
  const kind = KIT_MAP[((v.midi % 12) + 12) % 12];
  const P = { ...DRUMS[kind], ...(I[kind] || {}) };
  const sr = o.sr, L = o.L, R = o.R, S = o.S, E = o.E;
  const n0 = v.s0;
  const nFull = Math.round(P.len * sr);
  let n = Math.min(o.len - n0, nFull);
  if (v.cut >= 0) n = Math.min(n, v.cut - n0 + Math.round(0.004 * sr));
  if (n <= 0) return;
  const rnd = rng(v.seed);
  const amp = v.amp * (P.gain ?? 1);
  const gl = amp * v.pl, gr = amp * v.pr, gs = amp * v.send, ge = amp * v.echo;
  // 淡出位置只取决于完整长度（被缓冲区末尾截断的声部也必须与完整声部逐采样一致）
  let fadeStart = nFull - Math.max(1, Math.round(nFull * 0.06)), fadeEnd = nFull;
  if (v.cut >= 0 && v.cut - n0 < fadeStart) { fadeStart = v.cut - n0; fadeEnd = fadeStart + Math.round(0.004 * sr); }
  const out = (i, y) => {
    if (i >= fadeStart) y *= Math.max(0, (fadeEnd - i) / (fadeEnd - fadeStart));
    const id = n0 + i;
    L[id] += y * gl; R[id] += y * gr; S[id] += y * gs; E[id] += y * ge;
  };
  const svf = (fc, q) => {
    const g = Math.tan(Math.PI * Math.min(fc, 0.45 * sr) / sr), k = 1 / q;
    const a1 = 1 / (1 + g * (g + k));
    return { a1, a2: g * a1, a3: g * g * a1, k, i1: 0, i2: 0 };
  };
  const tick = (f, x) => {
    const v3 = x - f.i2, v1 = f.a1 * f.i1 + f.a2 * v3, v2 = f.i2 + f.a2 * f.i1 + f.a3 * v3;
    f.i1 = 2 * v1 - f.i1; f.i2 = 2 * v2 - f.i2;
    f.lp = v2; f.bp = v1; return x - f.k * v1 - v2; // 返回高通
  };
  if (kind === 'kick') {
    let ph = 0, a = 1, c = P.click, prev = 0;
    const aM = Math.exp(-1 / (P.decay * sr)), cM = Math.exp(-1 / (0.0025 * sr));
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      const f = P.f1 + (P.f0 - P.f1) * Math.exp(-t / P.pt);
      ph += f / sr; if (ph >= 1) ph -= 1;
      let y = sin1(ph) * a;
      const nz = rnd() * 2 - 1;
      y += (nz - prev) * 0.5 * c; prev = nz;
      c *= cM; a *= aM;
      if (i < 24) y *= i / 24;
      out(i, y * 1.1);
    }
  } else if (kind === 'snare' || kind === 'msnare') {
    let p1 = 0, p2 = 0, t1 = 1, nA = 1;
    const tM = Math.exp(-1 / (P.td * sr)), nM = Math.exp(-1 / (P.nd * sr));
    const hp = svf(P.hp, 0.7), lp = svf(P.lp, 0.7);
    for (let i = 0; i < n; i++) {
      p1 += P.tone / sr; if (p1 >= 1) p1 -= 1;
      p2 += P.tone2 / sr; if (p2 >= 1) p2 -= 1;
      const tone = (sin1(p1) + 0.5 * sin1(p2)) * t1 * P.mixT;
      tick(lp, rnd() * 2 - 1);
      const nz = tick(hp, lp.lp) * nA * P.mixN;
      t1 *= tM; nA *= nM;
      let y = tone + nz * 1.4;
      if (i < 8) y *= i / 8;
      out(i, y);
    }
  } else if (kind === 'rim') {
    let p = 0, a = 1;
    const aM = Math.exp(-1 / (P.d * sr));
    const bp = svf(3200, 2.5);
    for (let i = 0; i < n; i++) {
      p += P.f / sr; if (p >= 1) p -= 1;
      tick(bp, rnd() * 2 - 1);
      out(i, (sin1(p) * 0.8 + bp.bp * 1.5) * a);
      a *= aM;
    }
  } else if (kind === 'hat' || kind === 'phat' || kind === 'ohat' || kind === 'ride' || kind === 'crash') {
    const scale = kind === 'ride' ? 2.3 : kind === 'crash' ? 1.35 : 1.7;
    const ph = new Float64Array(6), dt = METAL.map((f) => f * scale / sr);
    const hp = svf(P.hp, 0.75), hp2 = svf(P.hp * 0.8, 0.6);
    const lpC = kind === 'crash' ? svf(11000, 0.6) : null;
    let a = 1;
    const aM = Math.exp(-1 / (P.d * sr));
    const nzMix = kind === 'crash' ? 0.75 : kind === 'ride' ? 0.25 : 0.5;
    const atkN = kind === 'crash' ? Math.round(0.004 * sr) : 4;
    for (let i = 0; i < n; i++) {
      let m = 0;
      for (let k = 0; k < 6; k++) { ph[k] += dt[k]; if (ph[k] >= 1) ph[k] -= 1; m += ph[k] < 0.5 ? 1 : -1; }
      let x = m / 6 * (1 - nzMix) + (rnd() * 2 - 1) * nzMix;
      if (lpC) { tick(lpC, x); x = lpC.lp; }
      x = tick(hp, x);
      x = tick(hp2, x);
      let y = x * a * 1.6;
      if (i < atkN) y *= i / atkN;
      if (kind === 'ride') { y += Math.sin(TAU * 3100 * i / sr) * a * a * 0.08; }
      out(i, y);
      a *= aM;
    }
  } else { // toms
    let ph = 0, a = 1, nA = 0.35;
    const aM = Math.exp(-1 / (P.d * sr)), nM = Math.exp(-1 / (0.012 * sr));
    const bp = svf(P.f * 6, 1.5);
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      const f = P.f * (1 + 0.55 * Math.exp(-t / 0.045));
      ph += f / sr; if (ph >= 1) ph -= 1;
      tick(bp, rnd() * 2 - 1);
      let y = sin1(ph) * a + bp.bp * nA;
      if (i < 16) y *= i / 16;
      out(i, y);
      a *= aM; nA *= nM;
    }
  }
}

const ENGINES = { sub: vSub, add: vAdd, fm: vFM, choir: vChoir, kit: vKit };

// ================================================================
// 效果器
// ================================================================
// Freeverb（8 并联梳状 + 4 串联全通，左右声道错开）
export class Reverb {
  constructor(sr, p = {}) {
    const sc = sr / 44100;
    const combs = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617], aps = [556, 441, 341, 225], spread = 23;
    this.cl = combs.map((d) => new Float32Array(Math.max(1, Math.round(d * sc))));
    this.cr = combs.map((d) => new Float32Array(Math.max(1, Math.round((d + spread) * sc))));
    this.al = aps.map((d) => new Float32Array(Math.max(1, Math.round(d * sc))));
    this.ar = aps.map((d) => new Float32Array(Math.max(1, Math.round((d + spread) * sc))));
    this.icl = new Int32Array(8); this.icr = new Int32Array(8); this.ial = new Int32Array(4); this.iar = new Int32Array(4);
    this.fsl = new Float64Array(8); this.fsr = new Float64Array(8);
    const size = p.size ?? 0.7, damp = p.damp ?? 0.4, width = p.width ?? 1;
    this.fb = 0.7 + 0.28 * size;
    this.d1 = damp * 0.4; this.d2 = 1 - this.d1;
    const wet = (p.wet ?? 0.3) * 3;
    this.w1 = wet * (width / 2 + 0.5); this.w2 = wet * ((1 - width) / 2);
    this.pre = Math.round((p.predelay ?? 0.015) * sr);
    this.pbuf = new Float32Array(Math.max(1, this.pre)); this.pi = 0;
    // 估算 RT60（最长梳状、无阻尼）
    this.rt60 = -3 * (1617 / 44100) / Math.log10(this.fb);
  }
  process(inp, L, R, from, to) {
    const { cl, cr, al, ar, icl, icr, ial, iar, fsl, fsr, fb, d1, d2, w1, w2, pbuf } = this;
    const usePre = this.pre > 0;
    let pi = this.pi;
    for (let i = from; i < to; i++) {
      let x = inp[i];
      if (usePre) { const d = pbuf[pi]; pbuf[pi] = x; x = d; if (++pi >= pbuf.length) pi = 0; }
      x *= 0.015;
      let ol = 0, or = 0;
      for (let k = 0; k < 8; k++) {
        let b = cl[k], j = icl[k];
        let y = b[j];
        fsl[k] = y * d2 + fsl[k] * d1;
        b[j] = x + fsl[k] * fb;
        if (++j >= b.length) j = 0; icl[k] = j;
        ol += y;
        b = cr[k]; j = icr[k];
        y = b[j];
        fsr[k] = y * d2 + fsr[k] * d1;
        b[j] = x + fsr[k] * fb;
        if (++j >= b.length) j = 0; icr[k] = j;
        or += y;
      }
      for (let k = 0; k < 4; k++) {
        let b = al[k], j = ial[k];
        let bo = b[j];
        let y = -ol + bo; b[j] = ol + bo * 0.5; ol = y;
        if (++j >= b.length) j = 0; ial[k] = j;
        b = ar[k]; j = iar[k];
        bo = b[j];
        y = -or + bo; b[j] = or + bo * 0.5; or = y;
        if (++j >= b.length) j = 0; iar[k] = j;
      }
      L[i] += ol * w1 + or * w2;
      R[i] += or * w1 + ol * w2;
    }
    this.pi = pi;
  }
}

// 乒乓回声（反馈回路带低通）
export class Echo {
  constructor(sr, p = {}) {
    this.n = Math.max(1, Math.round((p.time ?? 0.3) * sr));
    this.bl = new Float32Array(this.n); this.br = new Float32Array(this.n); this.pos = 0;
    this.fb = p.fb ?? 0.35; this.wet = p.wet ?? 0.3;
    this.c = 1 - Math.exp(-TAU * (p.lp ?? 3500) / sr);
    this.sl = 0; this.sr_ = 0;
    this.tail = this.n / sr * Math.log(0.0001) / Math.log(Math.max(0.01, this.fb));
  }
  process(inp, L, R, from, to) {
    const { bl, br, n, fb, wet, c } = this;
    let pos = this.pos, sl = this.sl, sr_ = this.sr_;
    for (let i = from; i < to; i++) {
      const yl = bl[pos], yr = br[pos];
      sl += c * (inp[i] + yr * fb - sl);
      sr_ += c * (yl * fb - sr_);
      bl[pos] = sl; br[pos] = sr_;
      L[i] += yl * wet; R[i] += yr * wet;
      if (++pos >= n) pos = 0;
    }
    this.pos = pos; this.sl = sl; this.sr_ = sr_;
  }
}

// ================================================================
// 响度（ITU-R BS.1770 K 加权 + 门限）
// ================================================================
function biquadCoefs(type, fc, G, Q, fs) {
  const A = Math.pow(10, G / 40), w0 = TAU * fc / fs, cw = Math.cos(w0), alpha = Math.sin(w0) / (2 * Q);
  let b0, b1, b2, a0, a1, a2;
  if (type === 'shelf') {
    const sA = 2 * Math.sqrt(A) * alpha;
    b0 = A * ((A + 1) + (A - 1) * cw + sA); b1 = -2 * A * ((A - 1) + (A + 1) * cw); b2 = A * ((A + 1) + (A - 1) * cw - sA);
    a0 = (A + 1) - (A - 1) * cw + sA; a1 = 2 * ((A - 1) - (A + 1) * cw); a2 = (A + 1) - (A - 1) * cw - sA;
  } else {
    b0 = (1 + cw) / 2; b1 = -(1 + cw); b2 = (1 + cw) / 2; a0 = 1 + alpha; a1 = -2 * cw; a2 = 1 - alpha;
  }
  return [b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0];
}

export class LoudnessMeter {
  constructor(sr) {
    this.sr = sr;
    this.hs = biquadCoefs('shelf', 1500, 4, 1 / Math.SQRT2, sr);
    this.hp = biquadCoefs('hp', 38, 0, 0.5, sr);
    this.st = new Float64Array(16); // 左右各两级双二阶状态
    this.hop = Math.round(sr * 0.1);
    this.acc = 0; this.cnt = 0; this.hops = [];
  }
  push(L, R, from, to) {
    const [b0, b1, b2, a1, a2] = this.hs, [c0, c1, c2, e1, e2] = this.hp, s = this.st;
    let acc = this.acc, cnt = this.cnt;
    for (let i = from; i < to; i++) {
      let sum = 0;
      for (let ch = 0; ch < 2; ch++) {
        const x = ch ? R[i] : L[i], o = ch * 8;
        const y = b0 * x + b1 * s[o] + b2 * s[o + 1] - a1 * s[o + 2] - a2 * s[o + 3];
        s[o + 1] = s[o]; s[o] = x; s[o + 3] = s[o + 2]; s[o + 2] = y;
        const z = c0 * y + c1 * s[o + 4] + c2 * s[o + 5] - e1 * s[o + 6] - e2 * s[o + 7];
        s[o + 5] = s[o + 4]; s[o + 4] = y; s[o + 7] = s[o + 6]; s[o + 6] = z;
        sum += z * z;
      }
      acc += sum;
      if (++cnt >= this.hop) { this.hops.push(acc / cnt); acc = 0; cnt = 0; }
    }
    this.acc = acc; this.cnt = cnt;
  }
  // 返回 { integrated, maxMomentary }
  result() {
    const h = this.hops, blocks = [];
    for (let i = 0; i + 4 <= h.length; i++) blocks.push((h[i] + h[i + 1] + h[i + 2] + h[i + 3]) / 4);
    if (!blocks.length && h.length) blocks.push(h.reduce((a, b) => a + b, 0) / h.length);
    const lk = (p) => -0.691 + 10 * Math.log10(Math.max(1e-20, p));
    let maxM = -Infinity;
    for (const b of blocks) maxM = Math.max(maxM, lk(b));
    const abs = blocks.filter((b) => lk(b) > -70);
    if (!abs.length) return { integrated: -Infinity, maxMomentary: maxM };
    const g = lk(abs.reduce((a, b) => a + b, 0) / abs.length) - 10;
    const rel = abs.filter((b) => lk(b) > g);
    return { integrated: lk(rel.reduce((a, b) => a + b, 0) / rel.length), maxMomentary: maxM };
  }
}

export function measureLoudness(L, R, sr, from = 0, to = L.length) {
  const m = new LoudnessMeter(sr);
  // 先用 0.5 秒稳定滤波器状态
  const pre = Math.max(0, from - Math.round(sr * 0.5));
  if (pre < from) { m.push(L, R, pre, from); m.hops.length = 0; m.acc = 0; m.cnt = 0; }
  m.push(L, R, from, to);
  return m.result();
}

// 前瞻限幅：只压超过 ceiling 的峰，攻击时间 = 前瞻长度，释放为指数
export function limitPeaks(L, R, ceiling, sr, from = 0, to = L.length) {
  const n = to - from, W = Math.max(8, Math.round(sr * 0.0015));
  const req = new Float32Array(n);
  let any = false;
  for (let i = 0; i < n; i++) {
    const p = Math.max(Math.abs(L[from + i]), Math.abs(R[from + i]));
    req[i] = p > ceiling ? ceiling / p : 1;
    if (req[i] < 1) any = true;
  }
  if (!any) return 0;
  // 前瞻窗口最小值（单调队列）
  const mn = new Float32Array(n), dq = new Int32Array(n);
  let h = 0, t = 0;
  for (let i = n - 1; i >= 0; i--) {
    while (t > h && req[dq[t - 1]] >= req[i]) t--;
    dq[t++] = i;
    while (dq[h] > i + W - 1) h++;
    mn[i] = req[dq[h]];
  }
  // 盒式平均（窗口 W），保证在峰值处增益 ≤ 所需
  const rel = Math.exp(-1 / (0.08 * sr));
  let sum = 0, g = 1, worst = 1;
  for (let i = 0; i < n; i++) {
    sum += mn[i];
    if (i >= W) sum -= mn[i - W];
    const avg = sum / Math.min(i + 1, W);
    const target = Math.min(avg, mn[i]);
    g = Math.min(target, 1 - (1 - g) * rel);
    if (g < worst) worst = g;
    L[from + i] *= g; R[from + i] *= g;
  }
  return -gainToDb(worst);
}

// ================================================================
// 编译曲目
// ================================================================
export function compileSong(def) {
  const [num, den] = def.meter || [4, 4];
  const barTicks = Math.round(TPQ * 4 * num / den);
  const warnings = [];
  const tracks = [];
  const tempoEv = [];
  let endTick = 0, loopTick = null;
  (def.tracks || []).forEach((tr, ti) => {
    const r = parseMML(tr.mml, { name: `${def.id || 'song'}:${tr.name || ti}`, barTicks, oct: tr.oct, inst: tr.inst, v: tr.v, q: tr.q });
    for (const w of r.warnings) warnings.push(w);
    for (const t of r.tempos) tempoEv.push(t);
    tracks.push({ tr, ti, events: r.events, endTick: r.endTick, loopTick: r.loopTick });
    endTick = Math.max(endTick, r.endTick);
  });
  if (def.loop) {
    for (const t of tracks) {
      if (t.loopTick == null) { if (t.events.length) warnings.push(`[${def.id}:${t.tr.name || t.ti}] 循环曲目缺少 L 循环点`); continue; }
      if (loopTick == null) loopTick = t.loopTick;
      else if (loopTick !== t.loopTick) warnings.push(`[${def.id}:${t.tr.name || t.ti}] 循环点 ${t.loopTick} 与其它声部 ${loopTick} 不一致`);
    }
    if (loopTick == null) loopTick = 0;
  }
  for (const t of tracks) {
    if (t.events.length && t.endTick !== endTick) warnings.push(`[${def.id}:${t.tr.name || t.ti}] 声部长度 ${t.endTick} 与全曲 ${endTick} 不一致（差 ${endTick - t.endTick} tick）`);
  }
  // 速度表
  tempoEv.sort((a, b) => a[0] - b[0]);
  const map = [{ tick: 0, bpm: def.bpm || 120, sec: 0 }];
  for (const [tick, bpm] of tempoEv) {
    const last = map[map.length - 1];
    if (tick === last.tick) { last.bpm = bpm; continue; }
    map.push({ tick, bpm, sec: last.sec + (tick - last.tick) * 60 / (last.bpm * TPQ) });
  }
  const tickToSec = (t) => {
    let k = map.length - 1;
    while (k > 0 && map[k].tick > t) k--;
    const m = map[k];
    return m.sec + (t - m.tick) * 60 / (m.bpm * TPQ);
  };
  return {
    def, tracks, barTicks, endTick, loopTick: def.loop ? loopTick : null, tickToSec, warnings,
    duration: tickToSec(endTick),
    introSec: def.loop ? tickToSec(loopTick) : 0,
    loopSec: def.loop ? tickToSec(endTick) - tickToSec(loopTick) : 0,
  };
}

// 不渲染，只给出时长信息（playJingle 立即返回时长用）
export function songInfo(def) {
  const c = compileSong(def);
  return { duration: c.duration, introSec: c.introSec, loopSec: c.loopSec, loop: !!def.loop, warnings: c.warnings };
}

function panGains(p) {
  const a = (Math.max(-1, Math.min(1, p)) + 1) * Math.PI / 4;
  return [Math.cos(a), Math.sin(a)];
}

// 展开为声部列表。passes: [{from,to,origin,start}]（tick 区间 → 采样起点）
function buildVoices(comp, sr, passes, bufLen, songDef) {
  const voices = [];
  const secAt = comp.tickToSec;
  const local = songDef.instruments;
  const instCache = new Map();
  const getInst = (name) => {
    if (!instCache.has(name)) {
      const ins = resolveInstrument(name, local);
      if (!ins) comp.warnings.push(`[${songDef.id}] 未知音色 @${name}`);
      instCache.set(name, ins);
    }
    return instCache.get(name);
  };
  for (const trk of comp.tracks) {
    const tr = trk.tr;
    const tv = tr.vol ?? 1, tpan = tr.pan ?? 0, send = tr.send ?? songDef.send ?? 0.25, echo = tr.echo ?? 0;
    const det = tr.det || 0, trans = tr.trans || 0, human = tr.human || 0;
    const mono = tr.mono ?? !!getInst(tr.inst)?.mono;
    const list = [];
    for (const ps of passes) {
      const base = secAt(ps.origin);
      for (const ev of trk.events) {
        if (ev.tick < ps.from || ev.tick >= ps.to) continue;
        const s0 = ps.start + Math.round((secAt(ev.tick) - base) * sr);
        if (s0 >= bufLen) continue;
        const gateTicks = ev.q >= 8 ? ev.len : Math.max(1, Math.round(ev.len * ev.q / 8));
        const s1 = ps.start + Math.round((secAt(ev.tick + gateTicks) - base) * sr);
        const ins = getInst(ev.inst || tr.inst);
        if (!ins) continue;
        let segs = null;
        if (ev.legato) {
          segs = ev.legato.map(([off, m]) => [Math.round((secAt(ev.tick + off) - secAt(ev.tick)) * sr), mtof(m + trans + det / 100)]);
        }
        const [pl, pr] = panGains(ev.pan ?? tpan);
        const maxN = ins.engine === 'kit' ? 0 : (s1 - s0) + Math.round(ringTime(ins) * sr);
        for (let ni = 0; ni < ev.notes.length; ni++) {
          const midi = ev.notes[ni] + trans;
          const seed = hash3(trk.ti, ev.idx, ni);
          let vel = ev.vel;
          if (human) vel *= 1 + (rng(seed ^ 0x5bd1e995)() - 0.5) * 2 * human;
          const amp = (ins.amp ?? 0.3) * tv * Math.pow(Math.max(0, vel), ins.velCurve ?? 1.4);
          list.push({ s0, s1, cut: -1, maxN, midi, f: mtof(midi + det / 100), vel, amp, pl, pr, send, echo, seed, segs, ins });
        }
      }
    }
    if (mono) {
      list.sort((a, b) => a.s0 - b.s0);
      for (let i = 0; i < list.length; i++) {
        let j = i + 1;
        while (j < list.length && list[j].s0 === list[i].s0) j++;
        if (j < list.length) list[i].cut = list[j].s0;
      }
    }
    for (const v of list) voices.push(v);
  }
  return voices;
}

// ================================================================
// 曲目渲染器（可分片执行：step(毫秒预算)，主线程兜底用；Worker/Node 一次跑完）
// ================================================================
export class SongRenderer {
  constructor(def, sr = DEFAULT_SR, opt = {}) {
    this.def = def; this.sr = sr; this.opt = opt;
    const comp = this.comp = compileSong(def);
    this.warnings = comp.warnings;
    const rv = def.reverb ? new Reverb(sr, def.reverb) : null;
    const ec = def.echo ? new Echo(sr, def.echo) : null;
    this.rv = rv; this.ec = ec;
    // 尾巴 T：声部最长余音 + 效果器衰减都要在 T 内衰减到听不见（-100dB 量级），循环点才能逐采样一致
    let maxRing = 0;
    for (const t of comp.tracks) {
      for (const ev of t.events) maxRing = Math.max(maxRing, ringTime(resolveInstrument(ev.inst || t.tr.inst, def.instruments)));
    }
    const fxTail = Math.max(rv ? rv.rt60 * 1.6 : 0, ec ? ec.tail : 0);
    const tail = def.tail ?? Math.min(14, Math.max(4, maxRing + 0.5, fxTail + 1.0));
    if (def.loop) {
      const I = Math.round(comp.introSec * sr);
      const Ls = Math.round(comp.loopSec * sr);
      const T = Math.round(tail * sr);
      const len = I + T + Ls + GUARD;
      const passes = [{ from: 0, to: comp.loopTick, origin: 0, start: 0 }];
      for (let st = I; st < len; st += Ls) passes.push({ from: comp.loopTick, to: comp.endTick, origin: comp.loopTick, start: st });
      this.len = len;
      this.loopStart = I + T;
      this.loopEnd = I + T + Ls;
      this.voices = buildVoices(comp, sr, passes, len, def);
    } else {
      const end = Math.round(comp.duration * sr);
      this.len = end + Math.round(tail * sr);
      this.loopStart = 0; this.loopEnd = 0;
      this.voices = buildVoices(comp, sr, [{ from: 0, to: comp.endTick + 1, origin: 0, start: 0 }], this.len, def);
    }
    this.voices.sort((a, b) => a.s0 - b.s0);
    const n = this.len;
    this.L = new Float32Array(n); this.R = new Float32Array(n);
    this.S = new Float32Array(n); this.E = ec ? new Float32Array(n) : this.S; // 无回声时发送到哪都无所谓（ge=0）
    if (!ec) for (const v of this.voices) v.echo = 0;
    this.o = { sr, len: n, L: this.L, R: this.R, S: this.S, E: this.E };
    this.cache = new Map(); this.cacheBytes = 0; this.zero = new Float32Array(0);
    this.prepareCache();
    this.phase = 0; this.vi = 0; this.pos = 0;
    this.meter = null; this.result = null;
    this.stats = { voices: this.voices.length };
  }

  // 声部缓存：同一音色、同音高、同时值（同力度）的音符波形完全相同（像 GBA 采样器一样），渲染一次后直接混入。
  // 预先统计每个键出现的次数：只缓存会重复出现的键（循环两遍里的“双胞胎”音符一定重复），用完最后一次就释放。
  // 有键的声部一律走“渲染到临时缓冲再混入”的同一路径、种子只取决于键，因此无论命中与否结果逐采样相同。
  voiceKey(v) {
    const ins = v.ins, eng = ins.engine;
    if (v.segs || ins.cache === false) return null;
    const kind = eng === 'kit' ? KIT_MAP[((v.midi % 12) + 12) % 12] : null;
    const len = kind ? Math.round(({ ...DRUMS[kind], ...(ins[kind] || {}) }).len * this.sr) : v.maxN;
    if (!(len > 0) || len > this.sr * 10) return null;
    v.clen = len;
    return kind
      ? ins.__id + '|' + kind
      : ins.__id + '|' + v.f.toFixed(3) + '|' + (v.s1 - v.s0) + '|' + v.maxN + (eng === 'fm' || ins.velBright || ins.filter?.vel ? '|' + v.vel.toFixed(3) : '');
  }
  prepareCache() {
    const cnt = new Map();
    for (const v of this.voices) { v.key = this.voiceKey(v); if (v.key) cnt.set(v.key, (cnt.get(v.key) || 0) + 1); }
    for (const v of this.voices) if (v.key && cnt.get(v.key) < 2) v.key = null;
    this.keyLeft = cnt;
  }
  renderVoice(v) {
    const ins = v.ins, eng = ins.engine, key = v.key;
    if (!key) { ENGINES[eng](ins, v, this.o); return; }
    let wav = this.cache.get(key);
    if (!wav) {
      const len = v.clen;
      const tmp = new Float32Array(len), zero = this.zero.length >= len ? this.zero : (this.zero = new Float32Array(len));
      let hs = 2166136261;
      for (let i = 0; i < key.length; i++) hs = Math.imul(hs ^ key.charCodeAt(i), 16777619);
      const vv = { ...v, s0: 0, s1: v.s1 - v.s0, cut: -1, amp: 1, pl: 1, pr: 0, send: 0, echo: 0, seed: hs >>> 0 };
      ENGINES[eng](ins, vv, { sr: this.sr, len, L: tmp, R: zero, S: zero, E: zero });
      zero.fill(0, 0, len);
      let last = len - 1;
      while (last > 0 && tmp[last] === 0) last--;
      wav = tmp.subarray(0, last + 1);
      if (this.cacheBytes + len * 4 <= 48e6) { this.cache.set(key, wav); this.cacheBytes += len * 4; }
    } else this.stats.cacheHits = (this.stats.cacheHits || 0) + 1;
    const left = this.keyLeft.get(key) - 1;
    this.keyLeft.set(key, left);
    if (left <= 0 && this.cache.has(key)) { this.cacheBytes -= this.cache.get(key).buffer.byteLength; this.cache.delete(key); }
    // 混入（单音轨截断时 5ms 淡出）
    const { L, R, S, E } = this.o;
    const s0 = v.s0, n = Math.min(wav.length, this.len - s0);
    const cutI = v.cut >= 0 ? v.cut - s0 : 1e15, fadeN = Math.max(1, Math.round(0.005 * this.sr));
    const gl = v.amp * v.pl, gr = v.amp * v.pr, gs = v.amp * v.send, ge = v.amp * v.echo;
    for (let i = 0; i < n; i++) {
      let y = wav[i];
      if (i >= cutI) { const c = 1 - (i - cutI) / fadeN; if (c <= 0) break; y *= c; }
      const id = s0 + i;
      L[id] += y * gl; R[id] += y * gr; S[id] += y * gs; E[id] += y * ge;
    }
  }

  step(budgetMs = Infinity) {
    const t0 = now();
    const CH = 16384;
    for (;;) {
      if (this.phase === 0) { // 声部
        while (this.vi < this.voices.length) {
          const v = this.voices[this.vi++];
          this.renderVoice(v);
          if (budgetMs !== Infinity && now() - t0 > budgetMs) return false;
        }
        this.cache = null; this.zero = null;
        this.phase = 1; this.pos = 0;
      } else if (this.phase === 1) { // 效果
        const end = Math.min(this.len, this.pos + CH);
        if (this.rv) this.rv.process(this.S, this.L, this.R, this.pos, end);
        if (this.ec) this.ec.process(this.E, this.L, this.R, this.pos, end);
        this.pos = end;
        if (end >= this.len) {
          this.phase = 2;
          this.S = this.E = this.o.S = this.o.E = null;
          this.meter = new LoudnessMeter(this.sr);
          this.mFrom = this.def.loop ? this.loopStart : 0;
          this.mTo = this.def.loop ? this.loopEnd : this.len;
          this.pos = Math.max(0, this.mFrom - Math.round(this.sr * 0.5));
          this.peak = 0;
        }
      } else if (this.phase === 2) { // 响度测量
        const end = Math.min(this.mTo, this.pos + CH);
        if (this.pos < this.mFrom) { const e2 = Math.min(end, this.mFrom); this.meter.push(this.L, this.R, this.pos, e2); if (e2 >= this.mFrom) { this.meter.hops.length = 0; this.meter.acc = 0; this.meter.cnt = 0; } this.pos = e2; continue; }
        this.meter.push(this.L, this.R, this.pos, end);
        this.pos = end;
        if (end >= this.mTo) {
          const lu = this.meter.result();
          this.lufs = lu.integrated;
          const target = (this.def.lufs ?? TARGET_LUFS) + (this.def.gain ?? 0);
          this.gain = isFinite(lu.integrated) ? dbToGain(target - lu.integrated) : 1;
          this.phase = 3; this.pos = 0;
        }
      } else if (this.phase === 3) { // 施加增益 + 统计峰值
        const end = Math.min(this.len, this.pos + CH), g = this.gain, L = this.L, R = this.R;
        let pk = this.peak;
        for (let i = this.pos; i < end; i++) {
          const l = L[i] * g, r = R[i] * g;
          L[i] = l; R[i] = r;
          const a = l < 0 ? -l : l, b = r < 0 ? -r : r;
          if (a > pk) pk = a; if (b > pk) pk = b;
        }
        this.peak = pk; this.pos = end;
        if (end >= this.len) { this.phase = 4; }
      } else if (this.phase === 4) { // 限幅 / 收尾
        const ceil = dbToGain(CEILING_DB);
        this.limitDb = 0;
        if (this.peak > ceil) {
          if (this.peak > ceil * 2) { // 超得太多：整体降增益，只让限幅器处理剩余的一点
            const g = ceil * 1.25 / this.peak;
            for (let i = 0; i < this.len; i++) { this.L[i] *= g; this.R[i] *= g; }
            this.gain *= g;
          }
          this.limitDb = limitPeaks(this.L, this.R, ceil, this.sr);
        }
        this.finish();
        return true;
      } else return true;
      if (now() - t0 > budgetMs) return false;
    }
  }

  finish() {
    let L = this.L, R = this.R, len = this.len;
    if (!this.def.loop) {
      // 去掉尾部静音，再做短淡出
      let last = len - 1;
      while (last > 0 && Math.abs(L[last]) < 1e-4 && Math.abs(R[last]) < 1e-4) last--;
      const newLen = Math.min(len, last + Math.round(this.sr * 0.05));
      if (newLen < len) { L = L.slice(0, newLen); R = R.slice(0, newLen); len = newLen; }
      const f = Math.min(len, Math.round(this.sr * 0.03));
      for (let i = 0; i < f; i++) { const g = i / f; L[len - 1 - i] *= g; R[len - 1 - i] *= g; }
    }
    let pk = 0, bad = 0;
    for (let i = 0; i < len; i++) {
      const a = L[i], b = R[i];
      if (!(a === a) || !(b === b) || !isFinite(a) || !isFinite(b)) { L[i] = 0; R[i] = 0; bad++; continue; }
      const m = Math.max(Math.abs(a), Math.abs(b));
      if (m > pk) pk = m;
    }
    if (bad) this.warnings.push(`[${this.def.id}] ${bad} 个非法采样（NaN/Inf）已清零`);
    this.result = {
      id: this.def.id, sr: this.sr, left: L, right: R, length: len, loop: !!this.def.loop,
      loopStart: this.loopStart, loopEnd: this.loopEnd, duration: this.comp.duration,
      introSec: this.comp.introSec, loopSec: this.comp.loopSec,
      lufsRaw: this.lufs, gainDb: gainToDb(this.gain), peakDb: gainToDb(pk), limitDb: this.limitDb || 0,
      voices: this.voices.length, warnings: this.warnings,
    };
    this.L = this.R = null; this.voices = null; this.o = null;
  }
}

export function renderSong(def, sr = DEFAULT_SR) {
  const r = new SongRenderer(def, sr);
  r.step(Infinity);
  return r.result;
}

// ================================================================
// 音效（sfxr 式参数化 + 可复用乐器/鼓）
// 层 type：
//   tone  { wave: square|pulse|saw|tri|sine|noise|metal, duty, f 频率或 [[t,f],…] 指数插值, amp [[t,a],…] 或 a/h/d,
//           lp/hp/bp 截止或 [[t,f],…], q, vib [速率,半音], trem [速率,深度], arp [[t,半音],…], crush 位深, drive, crackle }
//   notes { inst, mml, bpm }   乐器短旋律（升级号角、招募）
//   drum  { kind: kick|snare|…, f } 鼓
// 公共：t 起始秒, gain, pan, send（混响发送）
// ================================================================
function pathVal(p, t, expo) {
  if (typeof p === 'number') return p;
  if (t <= p[0][0]) return p[0][1];
  for (let i = 1; i < p.length; i++) {
    if (t <= p[i][0]) {
      const [t0, v0] = p[i - 1], [t1, v1] = p[i];
      const u = t1 > t0 ? (t - t0) / (t1 - t0) : 1;
      if (expo && v0 > 0 && v1 > 0) return v0 * Math.pow(v1 / v0, u);
      return v0 + (v1 - v0) * u;
    }
  }
  return p[p.length - 1][1];
}
function pathEnd(p) { return typeof p === 'number' ? 0 : p[p.length - 1][0]; }

function toneLayer(Ly, o, seed) {
  const sr = o.sr, L = o.L, R = o.R, S = o.S;
  const n0 = Math.round((Ly.t || 0) * sr);
  let ampP = Ly.amp;
  if (!ampP) { // a 起音 h 保持 d 衰减（(1-u)^shape 曲线，默认 2 = 先快后慢）
    const a = Ly.a ?? 0.003, h = Ly.h ?? 0, d = Ly.d ?? 0.2, sh = Ly.shape ?? 2;
    ampP = [[0, 0], [a, 1], [a + h, 1]];
    for (let k = 1; k <= 12; k++) ampP.push([a + h + d * k / 12, Math.pow(1 - k / 12, sh)]);
  }
  const dur = Math.max(pathEnd(ampP), 0.001);
  const n = Math.min(o.len - n0, Math.round(dur * sr));
  if (n <= 0) return;
  const rnd = rng(seed);
  const wave = Ly.wave || 'square';
  const duty = Ly.duty ?? 0.5;
  const fP = Ly.f ?? 440;
  const flt = [];
  const mk = (type, p) => ({ type, p, i1: 0, i2: 0, a1: 0, a2: 0, a3: 0, k: 1 / (Ly.q || 0.8) });
  if (Ly.lp) flt.push(mk(0, Ly.lp));
  if (Ly.hp) flt.push(mk(2, Ly.hp));
  if (Ly.bp) flt.push(mk(1, Ly.bp));
  const [pl, pr] = panGains(Ly.pan || 0);
  const g = Ly.gain ?? 1, send = Ly.send ?? 0;
  const metal = new Float64Array(6);
  const crushQ = Ly.crush ? Math.pow(2, Ly.crush - 1) : 0;
  let ph = 0, dt = 0, amp = 1, crackA = 0, lastCr = 0;
  const crM = Math.exp(-1 / (0.004 * sr));
  for (let i = 0; i < n; i++) {
    const t = i / sr;
    if ((i & 15) === 0) {
      let f = pathVal(fP, t, true);
      if (Ly.arp) { let semi = 0; for (const [at, s] of Ly.arp) if (t >= at) semi = s; f *= Math.pow(2, semi / 12); }
      if (Ly.vib) f *= Math.pow(2, Ly.vib[1] * Math.sin(TAU * Ly.vib[0] * t) / 12);
      dt = f / sr;
      amp = pathVal(ampP, t, false);
      if (Ly.trem) amp *= 1 - Ly.trem[1] * (0.5 + 0.5 * Math.sin(TAU * Ly.trem[0] * t));
      for (const F of flt) {
        const fc = Math.max(20, Math.min(0.45 * sr, pathVal(F.p, t, true)));
        const gg = Math.tan(Math.PI * fc / sr);
        F.a1 = 1 / (1 + gg * (gg + F.k)); F.a2 = gg * F.a1; F.a3 = gg * F.a2;
      }
    }
    let x;
    switch (wave) {
      case 'saw': x = 2 * ph - 1 - blep(ph, dt); break;
      case 'tri': x = 4 * Math.abs(ph - 0.5) - 1; break;
      case 'sine': x = sin1(ph); break;
      case 'noise': x = rnd() * 2 - 1; break;
      case 'metal': { // 6 个非谐方波，最低分音 = f
        let m = 0;
        for (let k = 0; k < 6; k++) { metal[k] += METAL[k] / 205.3 * dt; if (metal[k] >= 1) metal[k] -= Math.floor(metal[k]); m += metal[k] < 0.5 ? 1 : -1; }
        x = m / 6 * 0.6 + (rnd() * 2 - 1) * 0.4; break;
      }
      default: { const w = wave === 'pulse' ? duty : 0.5; x = (ph < w ? 1 : -1) + blep(ph, dt) - blep(ph >= w ? ph - w : ph - w + 1, dt) - (2 * w - 1); }
    }
    ph += dt; if (ph >= 1) ph -= Math.floor(ph);
    if (crushQ) x = Math.round(x * crushQ) / crushQ; // 降位深、过载都放在滤波之前：阶梯/削顶边沿经滤波才不会产生样间过冲
    if (Ly.drive) x = Math.tanh(x * Ly.drive) / Math.tanh(Ly.drive);
    for (const F of flt) {
      const v3 = x - F.i2, v1 = F.a1 * F.i1 + F.a2 * v3, v2 = F.i2 + F.a2 * F.i1 + F.a3 * v3;
      F.i1 = 2 * v1 - F.i1; F.i2 = 2 * v2 - F.i2;
      x = F.type === 0 ? v2 : F.type === 1 ? v1 * F.k * 1.5 : x - F.k * v1 - v2;
    }
    if (Ly.crackle) {
      if (rnd() < Ly.crackle / sr) { crackA = 0.6 + rnd() * 0.4; lastCr = rnd() < 0.5 ? -1 : 1; }
      x = x * 0.35 + lastCr * crackA * (rnd() * 0.8 + 0.2);
      crackA *= crM;
    }
    const y = x * amp * g, id = n0 + i;
    L[id] += y * pl; R[id] += y * pr; S[id] += y * send;
  }
}

function sfxLen(def) {
  let end = 0;
  for (const Ly of def.layers) {
    const t = Ly.t || 0;
    if (Ly.type === 'notes') end = Math.max(end, t + songInfo({ bpm: Ly.bpm || 120, tracks: [{ mml: Ly.mml, inst: Ly.inst }] }).duration + 2.5);
    else if (Ly.type === 'drum') end = Math.max(end, t + (DRUMS[Ly.kind]?.len ?? 1));
    else if (Ly.amp) end = Math.max(end, t + pathEnd(Ly.amp));
    else end = Math.max(end, t + (Ly.a ?? 0.003) + (Ly.h ?? 0) + (Ly.d ?? 0.2));
  }
  return end;
}

export function renderSfx(def, sr = DEFAULT_SR) {
  const rv = def.reverb ? new Reverb(sr, { predelay: 0.005, ...def.reverb }) : null;
  const tail = rv ? Math.min(3, rv.rt60 * 0.8) : 0.05;
  const len = Math.max(1, Math.round((sfxLen(def) + tail) * sr));
  const L = new Float32Array(len), R = new Float32Array(len), S = new Float32Array(len);
  const o = { sr, len, L, R, S, E: S };
  def.layers.forEach((Ly, li) => {
    const seed = hash3(li, (def.seed || 7) * 131, 17);
    if (Ly.type === 'notes') {
      const song = { id: 'sfx', bpm: Ly.bpm || 120, tracks: [{ mml: Ly.mml, inst: Ly.inst, vol: Ly.gain ?? 1, pan: Ly.pan || 0, send: Ly.send ?? 0 }], instruments: def.instruments };
      const comp = compileSong(song);
      const start = Math.round((Ly.t || 0) * sr);
      const vs = buildVoices(comp, sr, [{ from: 0, to: comp.endTick + 1, origin: 0, start }], len, song);
      for (const v of vs) { v.echo = 0; ENGINES[v.ins.engine](v.ins, v, o); }
    } else if (Ly.type === 'drum') {
      const ins = resolveInstrument('kit');
      const [pl, pr] = panGains(Ly.pan || 0);
      const midi = 60 + KIT_MAP.indexOf(Ly.kind);
      vKit({ ...ins, [Ly.kind]: Ly.p || {} }, { s0: Math.round((Ly.t || 0) * sr), s1: 0, cut: -1, midi, f: 0, vel: 1, amp: Ly.gain ?? 1, pl, pr, send: Ly.send ?? 0, echo: 0, seed }, o);
    } else {
      toneLayer(Ly, o, seed);
    }
  });
  if (rv) rv.process(S, L, R, 0, len);
  // 峰值归一到 def.db（默认 -3 dBFS）；尾部低于峰值 -60 dB 的余响截掉
  let pk = 0;
  for (let i = 0; i < len; i++) pk = Math.max(pk, Math.abs(L[i]), Math.abs(R[i]));
  const target = dbToGain(def.db ?? -3);
  const g = pk > 0 ? target / pk : 1;
  const thr = target * 1e-3;
  let last = 0;
  for (let i = 0; i < len; i++) {
    L[i] *= g; R[i] *= g;
    if (!(L[i] === L[i]) || !(R[i] === R[i])) { L[i] = 0; R[i] = 0; }
    if (Math.abs(L[i]) > thr || Math.abs(R[i]) > thr) last = i;
  }
  const n = Math.min(len, last + Math.round(sr * 0.01) + 1);
  const left = L.slice(0, n), right = R.slice(0, n);
  const f = Math.min(n, Math.round(sr * 0.008));
  for (let i = 0; i < f; i++) { const k = i / f; left[n - 1 - i] *= k; right[n - 1 - i] *= k; }
  return { id: def.id, sr, left, right, length: n, loop: false, loopStart: 0, loopEnd: 0, duration: n / sr };
}
