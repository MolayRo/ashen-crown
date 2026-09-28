// 生成单文件版：dist/灰烬王冠.html（全部代码与素材内嵌，双击即可在浏览器中游玩，无需服务器）
// 用法：node tools/build_single.mjs
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import * as esbuild from 'esbuild';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT_DIR = path.join(ROOT, 'dist');
fs.mkdirSync(OUT_DIR, { recursive: true });

// 1. 打包代码（含 Worker：以文本形式内嵌，运行时用 Blob URL 创建）
const workerPlugin = {
  name: 'inline-worker',
  setup(build) {
    build.onResolve({ filter: /\?worker-inline$/ }, (args) => ({ path: path.join(args.resolveDir, args.path.replace('?worker-inline', '')), namespace: 'worker-inline' }));
    build.onLoad({ filter: /.*/, namespace: 'worker-inline' }, async (args) => {
      const r = await esbuild.build({ entryPoints: [args.path], bundle: true, write: false, format: 'iife', minify: true, target: 'es2020' });
      return { contents: `export default ${JSON.stringify(r.outputFiles[0].text)};`, loader: 'js' };
    });
  },
};

const result = await esbuild.build({
  entryPoints: [path.join(ROOT, 'src', 'main.js')],
  bundle: true,
  write: false,
  format: 'iife',
  minify: true,
  target: 'es2020',
  charset: 'utf8',
  define: { 'import.meta.env.SINGLE': 'true' },
  plugins: [workerPlugin],
  logLevel: 'warning',
});
const js = result.outputFiles[0].text;

// 2. 内嵌素材
const embed = {};
function walk(dir) {
  for (const f of fs.readdirSync(dir)) {
    const p = path.join(dir, f);
    const st = fs.statSync(p);
    if (st.isDirectory()) { walk(p); continue; }
    const rel = path.relative(ROOT, p).split(path.sep).join('/');
    if (f.endsWith('.png')) embed[rel] = 'data:image/png;base64,' + fs.readFileSync(p).toString('base64');
    else if (f.endsWith('.json')) embed[rel] = fs.readFileSync(p, 'utf8');
  }
}
walk(path.join(ROOT, 'assets'));

// 3. 组装 HTML
let html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const safe = (s) => s.replace(/<\/script/gi, '<\\/script');
// 注意：必须用函数形式替换，否则压缩后代码里的 $' $` $& 会被当成替换模式
html = html.replace('<link rel="icon" href="assets/icon.png">', () => `<link rel="icon" href="${embed['assets/icon.png'] || ''}">`);
html = html.replace(
  '<script type="module" src="src/main.js"></script>',
  () => `<script>window.__EMBED=${safe(JSON.stringify(embed))};window.__SINGLE=true;</script>\n<script>${safe(js)}</script>`,
);
const out = path.join(OUT_DIR, 'ashen-crown.html');
fs.writeFileSync(out, html);
// 根目录再放一份中文名的，方便双击
fs.writeFileSync(path.join(ROOT, '灰烬王冠.html'), html);
const mb = (fs.statSync(out).size / 1024 / 1024).toFixed(2);
console.log(`已生成 dist/ashen-crown.html 与 灰烬王冠.html（${mb} MB，素材 ${Object.keys(embed).length} 个）`);
