// 《灰烬王冠》音频播放 API
//   audio.unlock()                          首次用户交互时调用：创建/恢复 AudioContext（本模块也会自动监听首次按键/点击）
//   audio.playMusic(id, {fade: 1, restart}) 循环播放；与当前曲目相同则什么都不做；否则旧曲淡出、新曲淡入
//   audio.stopMusic(fade = 1)
//   audio.playJingle(id)                    非循环短曲（victory/gameover/chapter），先淡出当前音乐；返回时长（秒）
//   audio.sfx(id, {vol: 1, rate: 1})        音效；同一音效极短时间内重复触发会被限流
//   audio.applyVolumes()                    读取 settings.masterVol/musicVol/sfxVol（0~100）立即生效
//   audio.preload(ids)                      预渲染（异步，在 Worker 里做，不卡主线程），返回 Promise
//   audio.musicId / audio.ready
//
// 全部声音由 synth.js 离线合成成 PCM：优先在 module Worker 里渲染（synth-worker.js），不支持时退回主线程分片渲染。
// 渲染采样率固定 32 kHz（GBA 质感、省内存），浏览器自动重采样。循环曲目的缓冲自带无缝循环点（见 synth.js 顶部说明）。
// 总线：音乐/音效 → 主音量 → 软削波保险（|x|<0.85 严格线性）→ 输出。
import { settings, onSettingsChange } from './settings.js';
import { DEFAULT_SR, SongRenderer, renderSfx, songInfo } from './synth.js';
import { MUSIC } from '../game/data/music.js';
import { SFX } from '../game/data/sfx.js';

const MB = 1024 * 1024;
const nowMs = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
// 滑块 0~100 → 增益：1.5 次方曲线（50 → -9 dB，70 → -4.6 dB，100 → 0 dB）
const volCurve = (v) => {
  const x = Math.max(0, Math.min(100, Number(v) || 0)) / 100;
  return x <= 0 ? 0 : Math.pow(x, 1.5);
};

// 软削波曲线：前级 ×0.5 后进入 WaveShaper，曲线把 [-1,1] 映射回原幅度 [-2,2]；
// |x| ≤ 0.85 严格线性（正常音量下永远只走这一段），之上用 tanh 平滑逼近 ±1，音乐+音效叠加时也不会硬削波。
function softClipCurve(n = 4097) {
  const c = new Float32Array(n), K = 0.85, R = 1 - K;
  for (let i = 0; i < n; i++) {
    const x = ((i / (n - 1)) * 2 - 1) * 2;
    const a = Math.abs(x);
    const y = a <= K ? a : K + R * Math.tanh((a - K) / R);
    c[i] = x < 0 ? -y : y;
  }
  return c;
}

class AudioEngine {
  constructor() {
    this.ctx = null;
    this.musicId = null;          // 当前（或解锁后将要播放的）循环曲目 id
    this.cacheLimitMB = 160;      // 已渲染的循环曲目缓冲内存上限，超出按最近最少使用淘汰（正在播放的不淘汰）
    this.useWorker = true;        // 设为 false 可强制主线程分片渲染（调试用）
    this.renderLog = [];          // 最近的渲染耗时记录
    this._want = null;            // { id, fade, offset }：想播放但还没开始的曲目（未解锁或渲染中）
    this._token = 0;              // 每次切换音乐 +1，用于丢弃过期的异步回调
    this._voices = [];            // 音乐/短曲实例 { id, src, gain, jingle, fading, fadeEnd, timer, started, offset }
    this._bufs = new Map();       // key('m:id' | 's:id') → { buffer, loopStart, loopEnd, duration, bytes, used, kind }
    this._raw = new Map();        // AudioContext 创建前渲染好的 PCM
    this._jobs = new Map();
    this._queue = [];
    this._active = null;
    this._seq = 0;
    this._worker = undefined;     // undefined 未启动 / Worker / null 不可用
    this._sfxLast = new Map();
    this._sfxPlaying = [];
    this._info = new Map();
    this._warned = new Set();
    if (typeof window !== 'undefined') {
      onSettingsChange((k) => { if (k === '*' || /Vol$/.test(String(k))) this.applyVolumes(); });
      this._hookGestures();
    }
  }

  get ready() { return !!this.ctx && this.ctx.state === 'running'; }

  // ---------------------------------------------------------------- 解锁 / 总线
  unlock() {
    if (typeof window === 'undefined') return;
    if (!this.ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { this._warnOnce('浏览器不支持 Web Audio'); return; }
      try { this.ctx = new AC({ latencyHint: 'interactive' }); } catch (e) {
        try { this.ctx = new AC(); } catch (e2) { this._warnOnce('无法创建 AudioContext：' + e2); return; }
      }
      this._buildGraph();
      this.ctx.onstatechange = () => this._onState();
      for (const [key, r] of this._raw) this._store(key, r);
      this._raw.clear();
      // 在后台预渲染全部音效与短曲（优先级低于想播放的音乐）
      for (const id of Object.keys(SFX)) this._request('s:' + id, 1);
      for (const id of Object.keys(MUSIC)) if (!MUSIC[id].loop) this._request('m:' + id, 1);
      if (this._want) this._startWanted(this._token);
    }
    if (this.ctx.state !== 'running') {
      try { const p = this.ctx.resume(); if (p && p.then) p.then(() => this._onState(), () => {}); } catch (e) { /* 忽略 */ }
      try { // iOS：必须在手势回调里真正播放一次声音才会解锁
        const b = this.ctx.createBuffer(1, 1, this.ctx.sampleRate);
        const s = this.ctx.createBufferSource();
        s.buffer = b; s.connect(this.ctx.destination); s.start(0);
      } catch (e) { /* 忽略 */ }
    }
  }

  _hookGestures() {
    const evs = ['pointerdown', 'mousedown', 'touchend', 'keydown'];
    const h = () => {
      this.unlock();
      if (this.ready) for (const e of evs) window.removeEventListener(e, h, true);
    };
    for (const e of evs) window.addEventListener(e, h, true);
  }

  _onState() {
    if (this.ready && this._want) this._startWanted(this._token);
  }

  _buildGraph() {
    const c = this.ctx;
    this.master = c.createGain();
    this.musicBus = c.createGain();
    this.sfxBus = c.createGain();
    const pre = c.createGain();
    pre.gain.value = 0.5;
    const shaper = c.createWaveShaper();
    shaper.curve = softClipCurve();
    shaper.oversample = 'none';
    this.musicBus.connect(this.master);
    this.sfxBus.connect(this.master);
    this.master.connect(pre);
    pre.connect(shaper);
    shaper.connect(c.destination);
    this.applyVolumes(true);
  }

  applyVolumes(instant = false) {
    if (!this.ctx || !this.master) return;
    const t = this.ctx.currentTime;
    const set = (node, v) => {
      const p = node.gain;
      if (instant) { p.cancelScheduledValues(t); p.value = v; return; }
      this._hold(p, t);
      p.linearRampToValueAtTime(v, t + 0.05);
    };
    set(this.master, volCurve(settings.masterVol));
    set(this.musicBus, volCurve(settings.musicVol));
    set(this.sfxBus, volCurve(settings.sfxVol));
  }

  _hold(p, t) {
    if (p.cancelAndHoldAtTime) { p.cancelAndHoldAtTime(t); return; }
    const v = p.value;
    p.cancelScheduledValues(t);
    p.setValueAtTime(v, t);
  }

  // ---------------------------------------------------------------- 音乐
  playMusic(id, opts = {}) {
    const fade = Math.max(0, Number(opts.fade ?? 1.0) || 0);
    if (!id || id === 'stop') { this.stopMusic(fade); return; }
    const def = MUSIC[id];
    if (!def) { this._warnOnce('未知曲目：' + id); return; }
    if (!def.loop) { this.playJingle(id); return; }
    if (!opts.restart && this.musicId === id) return; // 同一首：绝不叠加
    this.musicId = id;
    const token = ++this._token;
    const offset = Math.max(0, Number(opts.offset) || 0);
    this._want = { id, fade, offset };
    this._request('m:' + id, 3);
    if (!this.ctx) return; // 尚未解锁：记住想播的曲目，unlock 后自动开始
    // 同一首还在淡出中：直接拉回来（不重新开始）
    const reuse = opts.restart || offset ? null : this._voices.find((v) => v.id === id && !v.jingle && !v.stopped);
    for (const v of this._voices.slice()) if (v !== reuse) this._fadeOut(v, fade);
    if (reuse) { this._fadeIn(reuse, fade); this._want = null; return; }
    this._startWanted(token);
  }

  stopMusic(fade = 1.0) {
    this._token++;
    this._want = null;
    this.musicId = null;
    if (!this.ctx) return;
    const f = Math.max(0, Number(fade) || 0);
    for (const v of this._voices.slice()) this._fadeOut(v, f);
  }

  playJingle(id) {
    const def = MUSIC[id];
    if (!def) { this._warnOnce('未知短曲：' + id); return 0; }
    if (def.loop) { this.playMusic(id); return 0; }
    const dur = this.durationOf(id);
    this._token++;
    this._want = null;
    this.musicId = null;
    if (!this.ctx) return dur;
    for (const v of this._voices.slice()) this._fadeOut(v, 0.3);
    const token = this._token, key = 'm:' + id;
    const go = () => {
      if (token !== this._token || !this.ctx) return;
      const e = this._bufs.get(key);
      if (e) this._startVoice(id, e, 0, 0, true);
    };
    if (this._bufs.has(key)) go();
    else this._request(key, 3).then(go, (err) => this._warnOnce('渲染失败 ' + key + '：' + err));
    return dur;
  }

  // 曲目时长（秒）：短曲 = 乐谱长度；循环曲 = 前奏 + 一遍循环
  durationOf(id) {
    if (!this._info.has(id)) this._info.set(id, MUSIC[id] ? songInfo(MUSIC[id]) : null);
    const inf = this._info.get(id);
    return inf ? (inf.loop ? inf.introSec + inf.loopSec : inf.duration) : 0;
  }

  _startWanted(token) {
    const w = this._want;
    if (!w || !this.ctx || token !== this._token) return;
    const key = 'm:' + w.id;
    const e = this._bufs.get(key);
    if (!e) { // 首次需要时先等渲染完成再淡入
      this._request(key, 3).then(
        () => { if (token === this._token && this._want === w) this._startWanted(token); },
        (err) => this._warnOnce('渲染失败 ' + key + '：' + err),
      );
      return;
    }
    this._want = null;
    this._startVoice(w.id, e, w.fade, w.offset, false);
  }

  _startVoice(id, e, fade, offset, jingle) {
    const c = this.ctx, t = c.currentTime;
    const src = c.createBufferSource();
    src.buffer = e.buffer;
    if (!jingle) { src.loop = true; src.loopStart = e.loopStart; src.loopEnd = e.loopEnd; }
    const g = c.createGain();
    if (fade > 0.01) { g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(1, t + fade); }
    else g.gain.setValueAtTime(1, t);
    src.connect(g);
    g.connect(this.musicBus);
    const maxOff = jingle ? e.buffer.duration : e.loopEnd;
    const off = Math.min(offset || 0, Math.max(0, maxOff - 0.02));
    src.start(t, off);
    const v = { id, src, gain: g, jingle, fading: false, fadeEnd: 0, timer: 0, started: t, offset: off, stopped: false };
    src.onended = () => this._dropVoice(v);
    this._voices.push(v);
    e.used = nowMs();
    return v;
  }

  _fadeOut(v, fade) {
    if (v.stopped || !this.ctx) return;
    const t = this.ctx.currentTime, d = Math.max(0.02, fade);
    if (v.fading && v.fadeEnd <= t + d) return; // 已经在更快地淡出
    v.fading = true;
    v.fadeEnd = t + d;
    const p = v.gain.gain;
    this._hold(p, t);
    p.linearRampToValueAtTime(0, t + d);
    clearTimeout(v.timer);
    v.timer = setTimeout(() => { if (v.fading) this._stopVoice(v); }, (d + 0.15) * 1000);
  }

  _fadeIn(v, fade) {
    const t = this.ctx.currentTime, p = v.gain.gain;
    clearTimeout(v.timer);
    v.fading = false;
    this._hold(p, t);
    p.linearRampToValueAtTime(1, t + Math.max(0.02, fade));
  }

  _stopVoice(v) {
    if (v.stopped) return;
    clearTimeout(v.timer);
    try { v.src.stop(); } catch (e) { /* 已停止 */ }
    this._dropVoice(v);
  }

  _dropVoice(v) {
    v.stopped = true;
    clearTimeout(v.timer);
    const i = this._voices.indexOf(v);
    if (i >= 0) this._voices.splice(i, 1);
    try { v.src.disconnect(); v.gain.disconnect(); } catch (e) { /* 忽略 */ }
  }

  // 当前音乐播放位置（调试/试听页用）
  musicPosition() {
    if (!this.ctx) return null;
    const v = this._voices.find((x) => !x.fading && !x.stopped) || this._voices[this._voices.length - 1];
    if (!v) return null;
    const e = this._bufs.get('m:' + v.id);
    let pos = this.ctx.currentTime - v.started + v.offset, loops = 0;
    if (!v.jingle && e && pos >= e.loopEnd) {
      const L = e.loopEnd - e.loopStart;
      loops = Math.floor((pos - e.loopStart) / L);
      pos = e.loopStart + ((pos - e.loopStart) % L);
    }
    return { id: v.id, pos, loops, jingle: v.jingle, loopStart: e ? e.loopStart : 0, loopEnd: e ? e.loopEnd : 0, length: e ? e.buffer.duration : 0 };
  }

  // ---------------------------------------------------------------- 音效
  sfx(id, opts = {}) {
    if (!this.ready) return;
    const def = SFX[id];
    if (!def) { this._warnOnce('未知音效：' + id); return; }
    const c = this.ctx, t = c.currentTime;
    const last = this._sfxLast.get(id);
    if (last !== undefined && t - last < (def.gap ?? 0.04)) return; // 限流：避免同一音效叠加爆音
    this._sfxLast.set(id, t);
    const key = 's:' + id;
    let e = this._bufs.get(key);
    if (!e) { // Worker 还没渲染到：就地同步渲染（音效很短，几毫秒）
      try { this._store(key, renderSfx({ id, ...def }, DEFAULT_SR)); } catch (err) { this._warnOnce('音效渲染失败 ' + id + '：' + err); return; }
      this._cancelJob(key);
      e = this._bufs.get(key);
    }
    const max = def.max ?? 3;
    let same = 0;
    for (const p of this._sfxPlaying) if (p.id === id) same++;
    if (same >= max) this._stopSfx(this._sfxPlaying.find((p) => p.id === id), t);
    if (this._sfxPlaying.length >= 24) this._stopSfx(this._sfxPlaying[0], t);
    const src = c.createBufferSource();
    src.buffer = e.buffer;
    const rate = Number(opts.rate ?? 1);
    if (Number.isFinite(rate) && rate !== 1) src.playbackRate.value = Math.max(0.25, Math.min(4, rate));
    const g = c.createGain();
    const vol = Number(opts.vol ?? 1);
    g.gain.value = Number.isFinite(vol) ? Math.max(0, Math.min(4, vol)) : 1;
    src.connect(g);
    g.connect(this.sfxBus);
    src.start(t);
    const p = { id, src, g };
    src.onended = () => {
      const i = this._sfxPlaying.indexOf(p);
      if (i >= 0) this._sfxPlaying.splice(i, 1);
      try { src.disconnect(); g.disconnect(); } catch (x) { /* 忽略 */ }
    };
    this._sfxPlaying.push(p);
  }

  _stopSfx(p, t) {
    if (!p) return;
    const i = this._sfxPlaying.indexOf(p);
    if (i >= 0) this._sfxPlaying.splice(i, 1);
    try { p.g.gain.setTargetAtTime(0, t, 0.006); p.src.stop(t + 0.04); } catch (x) { /* 忽略 */ }
  }

  // ---------------------------------------------------------------- 预渲染 / 渲染队列
  preload(ids) {
    const list = (Array.isArray(ids) ? ids : [ids]).filter(Boolean);
    return Promise.all(list.map((id) => {
      if (MUSIC[id]) return this._request('m:' + id, 2).catch(() => {});
      if (SFX[id]) return this._request('s:' + id, 1).catch(() => {});
      this._warnOnce('preload：未知 id ' + id);
      return undefined;
    })).then(() => undefined);
  }

  // 优先级：3 = 正要播放，2 = 预加载音乐，1 = 后台预渲染音效/短曲
  _request(key, prio = 0) {
    const have = this._bufs.get(key);
    if (have) { have.used = nowMs(); return Promise.resolve(); }
    if (this._raw.has(key)) return Promise.resolve();
    let job = this._jobs.get(key);
    if (job) {
      if (prio > job.prio) { job.prio = prio; this._sortQueue(); }
      return job.promise;
    }
    job = { key, prio, seq: ++this._seq, t0: 0 };
    job.promise = new Promise((res, rej) => { job.resolve = res; job.reject = rej; });
    job.promise.catch(() => {}); // “发出即忘”的请求失败时不报未处理的 rejection
    this._jobs.set(key, job);
    this._queue.push(job);
    this._sortQueue();
    this._pump();
    return job.promise;
  }

  _sortQueue() { this._queue.sort((a, b) => b.prio - a.prio || a.seq - b.seq); }

  _cancelJob(key) {
    const job = this._jobs.get(key);
    if (!job || job === this._active) return;
    const i = this._queue.indexOf(job);
    if (i >= 0) this._queue.splice(i, 1);
    this._jobs.delete(key);
    job.resolve();
  }

  _pump() {
    if (this._active || !this._queue.length) return;
    const job = this._queue.shift();
    this._active = job;
    job.t0 = nowMs();
    const w = this._getWorker();
    if (w) {
      try { w.postMessage({ key: job.key }); return; } catch (e) { this._worker = null; }
    }
    this._renderMain(job);
  }

  _getWorker() {
    if (!this.useWorker || typeof Worker === 'undefined') return null;
    if (this._worker !== undefined) return this._worker;
    try {
      const w = new Worker(new URL('./synth-worker.js', import.meta.url), { type: 'module', name: 'ashen-audio' });
      w.onmessage = (e) => this._onWorker(e.data);
      w.onerror = (e) => {
        if (e && e.preventDefault) e.preventDefault();
        console.warn('[audio] Worker 不可用，改为主线程分片渲染', (e && e.message) || '');
        try { w.terminate(); } catch (x) { /* 忽略 */ }
        this._worker = null;
        if (this._active) this._renderMain(this._active);
      };
      this._worker = w;
    } catch (e) {
      this._worker = null;
    }
    return this._worker;
  }

  _onWorker(d) {
    const job = this._active;
    if (!job || !d || d.key !== job.key) return;
    if (d.ok) this._finish(job, d.result);
    else this._failJob(job, d.error);
  }

  // 主线程兜底：每 6ms 一片，片间让出主线程
  _renderMain(job) {
    const id = job.key.slice(2);
    if (job.key[0] === 's') {
      setTimeout(() => {
        if (this._active !== job) return;
        try { this._finish(job, renderSfx({ id, ...SFX[id] }, DEFAULT_SR)); } catch (e) { this._failJob(job, e); }
      }, 0);
      return;
    }
    let rr;
    try { rr = new SongRenderer(MUSIC[id], DEFAULT_SR); } catch (e) { this._failJob(job, e); return; }
    const tick = () => {
      if (this._active !== job) return;
      let done;
      try { done = rr.step(6); } catch (e) { this._failJob(job, e); return; }
      if (done) this._finish(job, rr.result);
      else setTimeout(tick, 4);
    };
    setTimeout(tick, 0);
  }

  _finish(job, r) {
    if (this._active === job) this._active = null;
    this._jobs.delete(job.key);
    this.renderLog.push({ key: job.key, ms: Math.round(nowMs() - job.t0), renderMs: r && r.ms ? Math.round(r.ms) : undefined });
    if (this.renderLog.length > 60) this.renderLog.shift();
    try {
      if (this.ctx) this._store(job.key, r);
      else this._raw.set(job.key, r);
      job.resolve();
    } catch (e) {
      job.reject(e);
    }
    this._pump();
  }

  _failJob(job, err) {
    if (this._active === job) this._active = null;
    this._jobs.delete(job.key);
    console.warn('[audio] 渲染失败', job.key, err);
    job.reject(err);
    this._pump();
  }

  _store(key, r) {
    const n = Math.max(1, r.length);
    const buf = this.ctx.createBuffer(2, n, r.sr);
    buf.getChannelData(0).set(r.left.subarray(0, n));
    buf.getChannelData(1).set(r.right.subarray(0, n));
    this._bufs.set(key, {
      buffer: buf, loopStart: r.loopStart / r.sr, loopEnd: r.loopEnd / r.sr, duration: r.duration,
      bytes: n * 8, used: nowMs(), kind: key[0],
    });
    if (key[0] === 'm') this._evict();
  }

  _evict() {
    const limit = this.cacheLimitMB * MB;
    let total = 0;
    const list = [];
    for (const [k, e] of this._bufs) {
      if (e.kind === 'm' && MUSIC[k.slice(2)] && MUSIC[k.slice(2)].loop) { total += e.bytes; list.push([k, e]); }
    }
    if (total <= limit) return;
    const busy = new Set(this._voices.map((v) => 'm:' + v.id));
    if (this.musicId) busy.add('m:' + this.musicId);
    if (this._want) busy.add('m:' + this._want.id);
    list.sort((a, b) => a[1].used - b[1].used);
    for (const [k, e] of list) {
      if (total <= limit) break;
      if (busy.has(k)) continue;
      this._bufs.delete(k);
      total -= e.bytes;
    }
  }

  // ---------------------------------------------------------------- 调试
  status() {
    let bytes = 0;
    for (const e of this._bufs.values()) bytes += e.bytes;
    return {
      ready: this.ready, state: this.ctx ? this.ctx.state : '未创建', sampleRate: this.ctx ? this.ctx.sampleRate : 0,
      musicId: this.musicId, want: this._want ? this._want.id : null,
      voices: this._voices.map((v) => ({ id: v.id, jingle: v.jingle, fading: v.fading })),
      sfxPlaying: this._sfxPlaying.length, cachedMB: +(bytes / MB).toFixed(1), cached: [...this._bufs.keys()],
      rendering: this._active ? this._active.key : null, queue: this._queue.map((j) => j.key),
      worker: this._worker ? 'module worker' : this._worker === null ? '主线程分片' : '未启动',
    };
  }

  // 接一个分析器到主输出（试听页画电平/波形用）
  analyser() {
    if (!this.ctx) return null;
    if (!this._an) {
      this._an = this.ctx.createAnalyser();
      this._an.fftSize = 2048;
      this.master.connect(this._an);
    }
    return this._an;
  }

  _warnOnce(msg) {
    if (this._warned.has(msg)) return;
    this._warned.add(msg);
    console.warn('[audio] ' + msg);
  }
}

export const audio = new AudioEngine();
export default audio;
