// 《灰烬王冠》音效参数（全部程序合成，渲染器见 src/core/synth.js renderSfx）
// 每个音效由若干“层”叠成：
//   tone  sfxr 式振荡/噪声层：wave(square|pulse|saw|tri|sine|noise|metal) f 频率或 [[秒,Hz],…](指数插值)
//         amp 包络 [[秒,电平],…] 或 a/h/d(+shape)，lp/hp/bp 滤波(可为路径) q，vib/trem/arp/crush/drive/crackle
//   notes 用乐器演奏一小段 MML（升级号角、招募旋律）
//   drum  鼓组里的一击
//   公共：t 起始秒（层内路径时间从该层起点算）、gain、pan、send（混响发送）
// 顶层：db 峰值电平（dBFS，渲染后按峰值归一）、reverb、gap 同一音效最短触发间隔（秒，限流）、max 同时最多几个实例
export const SFX = {
  // —— 界面 ——
  cursor: {
    db: -13, gap: 0.03, max: 2,
    layers: [
      { wave: 'pulse', duty: 0.25, f: 1760, a: 0.001, d: 0.035, lp: 6500 },
      { wave: 'noise', hp: 5000, a: 0.0005, d: 0.008, gain: 0.25 },
    ],
  },
  confirm: {
    db: -13, gap: 0.05,
    layers: [
      { wave: 'pulse', duty: 0.5, f: 1046.5, arp: [[0, 0], [0.05, 7]], a: 0.002, h: 0.06, d: 0.1, lp: 5200 },
      { wave: 'sine', f: 2093, arp: [[0, 0], [0.05, 7]], a: 0.002, h: 0.05, d: 0.14, gain: 0.35 },
    ],
  },
  cancel: {
    db: -12, gap: 0.05,
    layers: [
      { wave: 'pulse', duty: 0.25, f: 784, arp: [[0, 0], [0.05, -7]], a: 0.002, h: 0.05, d: 0.09, lp: 3500 },
      { wave: 'tri', f: 392, arp: [[0, 0], [0.05, -7]], a: 0.002, h: 0.05, d: 0.08, gain: 0.5 },
    ],
  },
  select: {
    db: -12, gap: 0.06,
    layers: [
      { wave: 'tri', f: [[0, 520], [0.07, 1400]], a: 0.002, h: 0.04, d: 0.07 },
      { wave: 'sine', t: 0.05, f: 2093, a: 0.001, d: 0.14, gain: 0.35 },
    ],
  },
  error: {
    db: -10, gap: 0.12, max: 1,
    layers: [
      { wave: 'pulse', duty: 0.25, f: [[0, 208], [0.07, 196]], a: 0.002, h: 0.05, d: 0.03, lp: 2400 },
      { wave: 'pulse', duty: 0.25, t: 0.1, f: [[0, 196], [0.08, 175]], a: 0.002, h: 0.06, d: 0.04, lp: 2400 },
      { wave: 'saw', f: 104, a: 0.002, h: 0.16, d: 0.04, lp: 900, gain: 0.35 },
    ],
  },
  text: { // 对白逐字：极短、极轻，高频连续触发也不刺耳
    db: -16, gap: 0.03, max: 2,
    layers: [{ wave: 'tri', f: 1480, a: 0.0006, d: 0.016, shape: 1.5, lp: 4000 }],
  },
  page: {
    db: -11, gap: 0.06, max: 2,
    layers: [{ wave: 'noise', bp: [[0, 2200], [0.1, 4800]], q: 0.7, amp: [[0, 0], [0.02, 1], [0.06, 0.45], [0.13, 0]], crackle: 180 }],
  },
  save: {
    db: -8, gap: 0.3, reverb: { size: 0.6, damp: 0.4, wet: 0.35 },
    layers: [
      { type: 'notes', inst: 'glock', bpm: 200, mml: 'v12 o5 l16 c g >c e g >c8', send: 0.5 },
      { type: 'notes', inst: 'chime', bpm: 200, t: 0.35, mml: 'v11 o6 c4', gain: 0.8, send: 0.6 },
    ],
  },
  phase: { // 回合切换：上扬的风声 + 明亮的“锵”
    db: -5, gap: 0.5, reverb: { size: 0.65, damp: 0.4, wet: 0.3 },
    layers: [
      { wave: 'noise', bp: [[0, 350], [0.32, 3800]], q: 1.1, amp: [[0, 0], [0.28, 0.9], [0.36, 0]], send: 0.3 },
      { wave: 'metal', t: 0.3, f: 1250, hp: 2500, amp: [[0, 0], [0.002, 0.7], [0.5, 0]], send: 0.5 },
      { type: 'notes', inst: 'brass', bpm: 120, t: 0.3, mml: 'v13 o4 {g >d g}8', gain: 0.9, send: 0.4 },
      { type: 'notes', inst: 'chime', bpm: 120, t: 0.3, mml: 'v12 o6 d4', gain: 0.5, send: 0.6 },
    ],
  },
  warn: { // 增援警报：两音交替四声
    db: -8, gap: 0.6, max: 1,
    layers: [0, 1, 2, 3].map((k) => ({ wave: 'pulse', duty: 0.25, t: k * 0.15, f: k % 2 ? 659 : 880, a: 0.002, h: 0.09, d: 0.03, lp: 4000 }))
      .concat([{ wave: 'saw', f: 110, a: 0.01, h: 0.52, d: 0.08, lp: 700, gain: 0.3, trem: [13.3, 0.9] }]),
  },
  // —— 地图移动 ——
  step: {
    db: -15, gap: 0.07, max: 2,
    layers: [
      { wave: 'noise', lp: 900, a: 0.002, d: 0.05 },
      { wave: 'sine', f: [[0, 120], [0.04, 70]], a: 0.001, d: 0.05, gain: 0.8 },
    ],
  },
  step_horse: { // 马蹄：两声木块般的“哒哒”
    db: -12, gap: 0.12, max: 2,
    layers: [
      { wave: 'sine', f: [[0, 950], [0.03, 720]], a: 0.0005, d: 0.035 },
      { wave: 'noise', bp: 1600, q: 1.5, a: 0.0005, d: 0.015, gain: 0.6 },
      { wave: 'sine', t: 0.085, f: [[0, 800], [0.03, 610]], a: 0.0005, d: 0.035, gain: 0.8 },
      { wave: 'noise', t: 0.085, bp: 1400, q: 1.5, a: 0.0005, d: 0.015, gain: 0.5 },
    ],
  },
  wing: { // 扇翅：两下
    db: -12, gap: 0.15, max: 2,
    layers: [
      { wave: 'noise', bp: [[0, 380], [0.08, 1400], [0.2, 450]], q: 1.2, amp: [[0, 0], [0.06, 1], [0.2, 0]] },
      { wave: 'noise', t: 0.2, bp: [[0, 350], [0.08, 1200], [0.2, 420]], q: 1.2, amp: [[0, 0], [0.06, 0.65], [0.2, 0]] },
    ],
  },
  // —— 攻击 ——
  sword: {
    db: -5, gap: 0.06,
    layers: [
      { wave: 'noise', bp: [[0, 1200], [0.1, 5200], [0.17, 2500]], q: 1.4, amp: [[0, 0], [0.045, 1], [0.17, 0]] },
      { wave: 'metal', t: 0.03, f: 2400, hp: 3000, amp: [[0, 0], [0.003, 0.35], [0.22, 0]] },
    ],
  },
  lance: {
    db: -5, gap: 0.06,
    layers: [
      { wave: 'noise', bp: [[0, 700], [0.07, 2600]], q: 1.4, amp: [[0, 0], [0.03, 1], [0.1, 0]] },
      { wave: 'noise', t: 0.07, hp: 2000, a: 0.001, d: 0.035, gain: 0.7 },
      { wave: 'sine', t: 0.07, f: [[0, 200], [0.06, 110]], a: 0.001, d: 0.07, gain: 0.8 },
    ],
  },
  axe: {
    db: -5, gap: 0.06,
    layers: [
      { wave: 'noise', bp: [[0, 300], [0.14, 1400], [0.23, 600]], q: 1.0, amp: [[0, 0], [0.1, 1], [0.24, 0]] },
      { wave: 'sine', f: [[0, 130], [0.22, 60]], amp: [[0, 0], [0.08, 0.6], [0.26, 0]] },
    ],
  },
  bow: { // 弓弦“嘣”+箭的“嗖”
    db: -6, gap: 0.06,
    layers: [
      { wave: 'pulse', duty: 0.15, f: [[0, 330], [0.12, 205]], a: 0.001, d: 0.18, lp: [[0, 4200], [0.15, 700]] },
      { wave: 'noise', t: 0.02, hp: [[0, 3000], [0.25, 6500]], amp: [[0, 0], [0.03, 0.6], [0.26, 0]], gain: 0.7 },
    ],
  },
  throw: { // 旋转飞行的呼啸
    db: -7, gap: 0.06,
    layers: [{ wave: 'noise', bp: [[0, 900], [0.3, 2300]], q: 1.2, trem: [18, 0.75], amp: [[0, 0], [0.05, 1], [0.32, 0]] }],
  },
  // —— 魔法 ——
  fire: {
    db: -4, gap: 0.1, reverb: { size: 0.55, damp: 0.5, wet: 0.25 },
    layers: [
      { wave: 'noise', lp: [[0, 400], [0.15, 2600], [0.85, 900]], amp: [[0, 0], [0.12, 1], [0.3, 0.7], [0.9, 0]], crackle: 45, send: 0.3 },
      { wave: 'sine', f: [[0, 95], [0.3, 55]], amp: [[0, 0], [0.05, 0.8], [0.5, 0]] },
      { wave: 'saw', f: [[0, 120], [0.4, 80]], lp: 650, drive: 2, amp: [[0, 0], [0.1, 0.35], [0.6, 0]] },
    ],
  },
  thunder: {
    db: -3, gap: 0.1, reverb: { size: 0.7, damp: 0.45, wet: 0.3 },
    layers: [
      { wave: 'noise', hp: 900, drive: 3, amp: [[0, 0], [0.003, 1], [0.06, 0.25], [0.13, 0]], send: 0.4 },
      { wave: 'square', f: 820, crush: 4, arp: [[0, 0], [0.02, 7], [0.04, -5], [0.06, 12], [0.08, 3], [0.1, -12], [0.12, 5]], amp: [[0, 0], [0.005, 0.5], [0.16, 0]], lp: 5000 },
      { wave: 'noise', t: 0.04, lp: [[0, 320], [1.1, 110]], amp: [[0, 0], [0.08, 1], [1.2, 0]], gain: 1.1, send: 0.4 },
    ],
  },
  dark: {
    db: -4, gap: 0.1, reverb: { size: 0.85, damp: 0.5, wet: 0.35 },
    layers: [
      { wave: 'saw', f: [[0, 110], [0.9, 55]], vib: [7, 0.4], lp: [[0, 1500], [0.9, 300]], amp: [[0, 0], [0.25, 1], [0.9, 0]], send: 0.4 },
      { wave: 'saw', f: [[0, 116.5], [0.9, 58.3]], lp: [[0, 1200], [0.9, 250]], amp: [[0, 0], [0.25, 0.6], [0.9, 0]], send: 0.4 },
      { wave: 'noise', bp: 600, q: 2, amp: [[0, 0], [0.35, 0.6], [0.4, 0]], send: 0.6 },
      { wave: 'sine', t: 0.3, f: 55, amp: [[0, 0], [0.08, 0.8], [0.7, 0]] },
    ],
  },
  light: {
    db: -5, gap: 0.1, reverb: { size: 0.8, damp: 0.35, wet: 0.4 },
    layers: [
      { type: 'notes', inst: 'glock', bpm: 240, mml: 'v12 o6 l16 c e g >c e g', send: 0.6 },
      { wave: 'sine', f: [[0, 1046.5], [0.6, 2093]], trem: [12, 0.5], amp: [[0, 0], [0.1, 0.4], [0.8, 0]], send: 0.6 },
      { type: 'notes', inst: 'chime', bpm: 240, t: 0.25, mml: 'v12 o6 g4', gain: 0.7, send: 0.6 },
    ],
  },
  // —— 命中 ——
  hit: {
    db: -3, gap: 0.03,
    layers: [
      { wave: 'noise', bp: 1800, q: 0.8, amp: [[0, 0], [0.002, 1], [0.08, 0]] },
      { wave: 'sine', f: [[0, 170], [0.08, 60]], amp: [[0, 0], [0.003, 1], [0.12, 0]] },
    ],
  },
  hit_heavy: {
    db: -2.5, gap: 0.05,
    layers: [
      { wave: 'noise', lp: [[0, 5500], [0.22, 800]], drive: 2, amp: [[0, 0], [0.002, 1], [0.26, 0]] },
      { wave: 'sine', f: [[0, 125], [0.25, 40]], amp: [[0, 0], [0.004, 1], [0.36, 0]] },
      { wave: 'metal', f: 900, hp: 3000, amp: [[0, 0], [0.01, 0.3], [0.4, 0]] },
    ],
  },
  miss: {
    db: -8, gap: 0.06,
    layers: [{ wave: 'noise', bp: [[0, 2500], [0.15, 700]], q: 1.5, amp: [[0, 0], [0.03, 1], [0.17, 0]] }],
  },
  crit: { // 必杀：蓄力（上扬锯齿+噪声）→ 冲击（重击+吊镲）
    db: -2, gap: 0.2, max: 1, reverb: { size: 0.6, damp: 0.45, wet: 0.25 },
    layers: [
      { wave: 'saw', f: [[0, 200], [0.35, 1250]], trem: [25, 0.6], lp: 3200, amp: [[0, 0], [0.3, 0.7], [0.36, 0]] },
      { wave: 'noise', bp: [[0, 500], [0.35, 4200]], q: 1.2, amp: [[0, 0], [0.33, 0.6], [0.36, 0]] },
      { wave: 'noise', t: 0.36, lp: [[0, 6500], [0.34, 700]], drive: 2.5, amp: [[0, 0], [0.002, 1], [0.34, 0]], send: 0.3 },
      { wave: 'sine', t: 0.36, f: [[0, 115], [0.34, 38]], amp: [[0, 0], [0.004, 1], [0.55, 0]] },
      { type: 'drum', kind: 'crash', t: 0.36, gain: 0.8, send: 0.3 },
    ],
  },
  nodmg: { // 金属格挡“叮”
    db: -6, gap: 0.05,
    layers: [
      { wave: 'metal', f: 1400, hp: 1500, amp: [[0, 0], [0.001, 1], [0.35, 0]] },
      { wave: 'sine', f: 2200, a: 0.001, d: 0.32, shape: 3, gain: 0.5 },
      { wave: 'sine', f: 3130, a: 0.001, d: 0.22, shape: 3, gain: 0.35 },
      { wave: 'noise', hp: 2500, a: 0.0005, d: 0.02, gain: 0.5 },
    ],
  },
  death: { // 阵亡/退场：闪烁着下沉消散
    db: -5, gap: 0.2, reverb: { size: 0.75, damp: 0.4, wet: 0.35 },
    layers: [
      { wave: 'pulse', duty: 0.25, f: [[0, 880], [1.0, 110]], trem: [14, 0.55], lp: [[0, 5000], [1.0, 700]], amp: [[0, 0], [0.04, 0.6], [1.05, 0]], send: 0.4 },
      { wave: 'noise', lp: [[0, 4000], [1.0, 500]], amp: [[0, 0], [0.1, 0.3], [1.1, 0]], send: 0.4 },
      { type: 'notes', inst: 'glock', bpm: 220, mml: 'v10 o6 l16 e c <a f d <b-', gain: 0.6, send: 0.6 },
    ],
  },
  // —— 支援/成长 ——
  heal: {
    db: -6, gap: 0.2, reverb: { size: 0.7, damp: 0.35, wet: 0.35 },
    layers: [
      { type: 'notes', inst: 'glock', bpm: 280, mml: 'v11 o5 l16 c e g >c e g >c4', send: 0.6 },
      { wave: 'sine', f: [[0, 523], [0.5, 1046.5]], amp: [[0, 0], [0.15, 0.35], [0.9, 0]], send: 0.5 },
      { wave: 'noise', hp: 6000, trem: [16, 0.8], amp: [[0, 0], [0.2, 0.15], [0.9, 0]], send: 0.6 },
    ],
  },
  levelup: { // 短小号角琶音
    db: -4, gap: 0.3, reverb: { size: 0.6, damp: 0.4, wet: 0.28 },
    layers: [
      { type: 'notes', inst: 'trumpet', bpm: 150, mml: 'v13 o5 l16 c e g >c8 <g16 >c4', send: 0.3 },
      { type: 'notes', inst: 'sq25', bpm: 150, mml: 'v10 o6 l16 c e g >c8 <g16 >c4', gain: 0.4, send: 0.3 },
      { type: 'notes', inst: 'horn', bpm: 150, t: 0.4, mml: 'v11 o4 {e g >c}4', gain: 0.7, send: 0.3 },
      { type: 'drum', kind: 'crash', t: 0.4, gain: 0.35 },
    ],
  },
  statup: {
    db: -13, gap: 0.05,
    layers: [
      { wave: 'pulse', duty: 0.5, f: 1568, arp: [[0, 0], [0.04, 5]], a: 0.001, h: 0.05, d: 0.08, lp: 6000 },
      { wave: 'sine', f: 3136, arp: [[0, 0], [0.04, 5]], a: 0.001, d: 0.12, gain: 0.3 },
    ],
  },
  recruit: { // 喜悦短旋律
    db: -6, gap: 0.5, reverb: { size: 0.6, damp: 0.4, wet: 0.3 },
    layers: [
      { type: 'notes', inst: 'sq50', bpm: 180, mml: 'v12 o5 l16 g >c e g8 e g >c4', send: 0.3 },
      { type: 'notes', inst: 'glock', bpm: 180, mml: 'v10 o6 l16 g >c e g8 e g >c4', gain: 0.5, send: 0.4 },
      { type: 'notes', inst: 'harp', bpm: 180, mml: 'v11 o4 l16 c g >c e g8 r8 {c e g}4', gain: 0.7, send: 0.4 },
    ],
  },
  // —— 地图事件 ——
  chest: { // 吱呀开盖 + 闪光
    db: -6, gap: 0.4, reverb: { size: 0.55, damp: 0.4, wet: 0.3 },
    layers: [
      { wave: 'saw', f: [[0, 90], [0.25, 145]], lp: 900, trem: [30, 0.8], crush: 5, amp: [[0, 0], [0.05, 0.5], [0.3, 0]] },
      { type: 'notes', inst: 'glock', bpm: 150, t: 0.3, mml: 'v12 o6 l32 c e g >c8', send: 0.5 },
      { type: 'notes', inst: 'chime', bpm: 150, t: 0.4, mml: 'v10 o6 e4', gain: 0.6, send: 0.5 },
    ],
  },
  door: { // 厚重木门：吱呀 + 撞击
    db: -5, gap: 0.4, reverb: { size: 0.6, damp: 0.5, wet: 0.3 },
    layers: [
      { wave: 'saw', f: [[0, 70], [0.5, 96]], lp: 700, trem: [22, 0.9], amp: [[0, 0], [0.1, 0.5], [0.55, 0]] },
      { wave: 'sine', t: 0.55, f: [[0, 95], [0.2, 45]], amp: [[0, 0], [0.004, 1], [0.35, 0]], send: 0.3 },
      { wave: 'noise', t: 0.55, lp: 450, amp: [[0, 0], [0.003, 0.7], [0.14, 0]], send: 0.3 },
    ],
  },
  item: { // 使用道具：“咕嘟”两个气泡 + 叮
    db: -7, gap: 0.2,
    layers: [
      { wave: 'sine', f: [[0, 300], [0.08, 820]], a: 0.001, d: 0.1 },
      { wave: 'sine', t: 0.1, f: [[0, 460], [0.08, 1150]], a: 0.001, d: 0.1 },
      { type: 'notes', inst: 'chime', bpm: 150, t: 0.2, mml: 'v11 o6 e8', gain: 0.6 },
    ],
  },
  gold: { // 两音硬币 + 金币碰撞
    db: -8, gap: 0.15,
    layers: [
      { wave: 'pulse', duty: 0.5, f: 987.8, arp: [[0, 0], [0.06, 5]], a: 0.001, h: 0.05, d: 0.28, lp: 6000 },
      { wave: 'metal', t: 0.02, f: 2500, hp: 3500, amp: [[0, 0], [0.001, 0.5], [0.12, 0]] },
      { wave: 'metal', t: 0.1, f: 2900, hp: 3500, amp: [[0, 0], [0.001, 0.4], [0.1, 0]] },
      { wave: 'metal', t: 0.17, f: 2300, hp: 3500, amp: [[0, 0], [0.001, 0.3], [0.1, 0]] },
    ],
  },
  visit: { // 村庄门铃般的三音
    db: -8, gap: 0.4, reverb: { size: 0.6, damp: 0.4, wet: 0.3 },
    layers: [
      { type: 'notes', inst: 'chime', bpm: 180, mml: 'v12 o5 l8 g b >d4', send: 0.4 },
      { type: 'notes', inst: 'harp', bpm: 180, mml: 'v10 o4 l8 g b >d4', gain: 0.6, send: 0.3 },
    ],
  },
  burn: { // 村庄被烧：火焰轰燃 + 噼啪 + 远处坍塌
    db: -5, gap: 0.5, max: 1, reverb: { size: 0.75, damp: 0.5, wet: 0.3 },
    layers: [
      { wave: 'noise', lp: [[0, 300], [0.3, 2200], [1.3, 700]], amp: [[0, 0], [0.25, 1], [0.8, 0.6], [1.4, 0]], crackle: 60, send: 0.3 },
      { wave: 'saw', f: [[0, 70], [1.2, 50]], lp: 400, drive: 2.5, amp: [[0, 0], [0.2, 0.4], [1.3, 0]] },
      { wave: 'sine', t: 0.6, f: [[0, 80], [0.4, 40]], amp: [[0, 0], [0.01, 0.8], [0.6, 0]], send: 0.4 },
      { wave: 'noise', t: 0.6, lp: [[0, 1500], [0.5, 300]], amp: [[0, 0], [0.01, 0.6], [0.6, 0]], crackle: 30, send: 0.4 },
    ],
  },
};
