// 剧情脚本解析：文本 → 指令树（见 docs/design.md §6）
import { SPEAKERS } from '../game/data/characters.js';

const SAY_RE = /^([^：:\s（(\[]{1,12})(?:\[([a-z_]+)\])?(?:[（(]([a-z]+)[)）])?[：:](.*)$/;

export function parseScript(src) {
  const root = [];
  const stack = [{ body: root }];
  const lines = String(src).split('\n');
  for (let ln = 0; ln < lines.length; ln++) {
    const raw = lines[ln];
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const top = stack[stack.length - 1];
    if (line.startsWith('@')) {
      const sp = line.indexOf(' ');
      const cmd = (sp < 0 ? line.slice(1) : line.slice(1, sp)).trim();
      const arg = sp < 0 ? '' : line.slice(sp + 1).trim();
      const args = arg ? arg.split(/\s+/) : [];
      switch (cmd) {
        case 'if': {
          const node = { t: 'if', branches: [{ cond: arg, body: [] }], else: null };
          top.body.push(node);
          stack.push({ node, body: node.branches[0].body });
          break;
        }
        case 'elif': {
          const fr = stack[stack.length - 1];
          if (!fr.node) break;
          const b = { cond: arg, body: [] };
          fr.node.branches.push(b);
          fr.body = b.body;
          break;
        }
        case 'else': {
          const fr = stack[stack.length - 1];
          if (!fr.node) break;
          fr.node.else = [];
          fr.body = fr.node.else;
          break;
        }
        case 'end':
          if (stack.length > 1) stack.pop();
          break;
        case 'bg': top.body.push({ t: 'bg', id: args[0] || 'black' }); break;
        case 'music': top.body.push({ t: 'music', id: args[0] || 'stop' }); break;
        case 'sfx': top.body.push({ t: 'sfx', id: args[0] }); break;
        case 'wait': top.body.push({ t: 'wait', n: parseInt(args[0] || '30', 10) }); break;
        case 'shake': top.body.push({ t: 'shake', n: parseInt(args[0] || '6', 10) }); break;
        case 'flash': top.body.push({ t: 'flash', color: args[0] || 'white' }); break;
        case 'fadeout': top.body.push({ t: 'fadeout' }); break;
        case 'fadein': top.body.push({ t: 'fadein' }); break;
        case 'chapter': {
          const [title, name] = arg.split('|');
          top.body.push({ t: 'chapter', title: (title || '').trim(), name: (name || '').trim() });
          break;
        }
        case 'show': top.body.push({ t: 'show', id: args[0], pos: args[1] || null, expr: args[2] || 'normal' }); break;
        case 'hide': top.body.push({ t: 'hide', id: args[0] || 'all' }); break;
        case 'set': top.body.push({ t: 'set', flag: args[0] }); break;
        default: top.body.push({ t: 'unknown', cmd, arg, line: ln + 1 });
      }
      continue;
    }
    const m = SAY_RE.exec(line);
    if (m) {
      const name = m[1];
      const text = m[4].trim();
      if (name === '旁白') { top.body.push({ t: 'narr', text }); continue; }
      const id = m[2] || SPEAKERS[name] || null;
      top.body.push({ t: 'say', name, id, expr: m[3] || null, text });
      continue;
    }
    top.body.push({ t: 'narr', text: line });
  }
  return root;
}

// 展开条件分支，得到线性指令序列（cond 为判定函数）
export function flatten(nodes, cond, out = []) {
  for (const n of nodes) {
    if (n.t === 'if') {
      let taken = null;
      for (const b of n.branches) if (cond(b.cond)) { taken = b.body; break; }
      if (!taken && n.else) taken = n.else;
      if (taken) flatten(taken, cond, out);
    } else out.push(n);
  }
  return out;
}
