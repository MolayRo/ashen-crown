// 音频渲染 Worker（module worker）：收到 { key: 'm:曲目' | 's:音效' }，离线合成后把 PCM 转移（零拷贝）回主线程
import { SongRenderer, renderSfx, DEFAULT_SR } from './synth.js';
import { MUSIC } from '../game/data/music.js';
import { SFX } from '../game/data/sfx.js';

self.onmessage = (e) => {
  const { key } = e.data || {};
  const id = String(key || '').slice(2);
  try {
    const t0 = performance.now();
    let r;
    if (key[0] === 'm') {
      if (!MUSIC[id]) throw new Error('未知曲目 ' + id);
      const rr = new SongRenderer(MUSIC[id], DEFAULT_SR);
      rr.step(Infinity);
      r = rr.result;
    } else {
      if (!SFX[id]) throw new Error('未知音效 ' + id);
      r = renderSfx({ id, ...SFX[id] }, DEFAULT_SR);
    }
    const result = {
      sr: r.sr, left: r.left, right: r.right, length: r.length,
      loopStart: r.loopStart, loopEnd: r.loopEnd, duration: r.duration, ms: performance.now() - t0,
    };
    self.postMessage({ key, ok: true, result }, [r.left.buffer, r.right.buffer]);
  } catch (err) {
    self.postMessage({ key, ok: false, error: String((err && err.stack) || err) });
  }
};
