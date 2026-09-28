// 剧情脚本注册表：合并各章节文件，按需解析
import { parseScript } from '../../story/parser.js';
import prologue from './prologue.js';
import ch1 from './ch1.js';
import ch2 from './ch2.js';
import ch3 from './ch3.js';
import ch4 from './ch4.js';
import ch5 from './ch5.js';
import ending from './ending.js';
import quotes from './quotes.js';
import extra from './extra.js';

export const RAW = { ...prologue, ...ch1, ...ch2, ...ch3, ...ch4, ...ch5, ...ending, ...quotes, ...extra };
const cache = new Map();

export function hasScript(id) { return !!RAW[id]; }

export function getScript(id) {
  if (!RAW[id]) return null;
  if (!cache.has(id)) cache.set(id, parseScript(RAW[id]));
  return cache.get(id);
}
