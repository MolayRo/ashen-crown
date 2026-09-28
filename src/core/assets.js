// 资源加载：图片 + JSON 元数据
// 单文件版（dist/灰烬王冠.html）会把全部素材以 data URI 形式放进 window.__EMBED，这里优先使用。
import { Sheet } from './gfx.js';

export const images = {};
export const sheets = {};
export const data = {};

function embedded(src) {
  const e = typeof window !== 'undefined' && window.__EMBED;
  return e ? e[src] : undefined;
}

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('图片加载失败：' + src));
    const emb = embedded(src);
    if (emb === null) { reject(new Error('素材不存在：' + src)); return; }
    img.src = emb || src;
  });
}

export async function loadJSON(src) {
  const emb = embedded(src);
  if (emb !== undefined) {
    if (emb === null) throw new Error('数据不存在：' + src);
    return typeof emb === 'string' ? JSON.parse(emb) : emb;
  }
  const r = await fetch(src);
  if (!r.ok) throw new Error('数据加载失败：' + src);
  return r.json();
}

// manifest: [{key, img, meta?}]；meta 为 JSON 路径时生成 Sheet
export async function loadAll(manifest, onProgress) {
  let done = 0;
  const total = manifest.length;
  await Promise.all(manifest.map(async (m) => {
    try {
      if (m.json && !m.img) {
        data[m.key] = await loadJSON(m.json);
      } else {
        const img = await loadImage(m.img);
        images[m.key] = img;
        if (m.meta) {
          const meta = await loadJSON(m.meta);
          sheets[m.key] = new Sheet(img, meta);
          data[m.key] = meta;
        }
      }
    } catch (e) {
      if (!m.optional) throw e;
      console.warn(e.message);
    }
    done++;
    if (onProgress) onProgress(done / total);
  }));
}
