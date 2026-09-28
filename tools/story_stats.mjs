// 《灰烬王冠》剧情脚本统计与校验
//
// 用法：node tools/story_stats.mjs [选项]
//   （无选项）      统计每个脚本的有效字数（只数台词/旁白正文里的汉字）、主线总字数，并做格式校验
//   --dump          按主线顺序打印实际会显示的台词（可配合下面的选项预览缺席分支是否通顺）
//   --dead=a:ch2,b:ch4   指定角色在某章战斗中阵亡（该章战后起 dead:id 成立）
//   --absent=doran,sid,vera   可选角色未招募（第一章多兰视为休闲模式下撤退、未入队）
//   --late=doran    多兰没交谈但活到战斗结束，战后自动入队
//   --mode=casual   休闲模式
//   --ch4=kill      第四章走“击败格里姆”路线（默认走“坚守到援军”路线）
//
// 主线定义：全员招募、全员存活、经典模式，@if 取第一个成立的分支；
// 按 MAINLINE 的播放顺序推进（招募脚本播完后 recruited 成立，@set 的旗标对后续脚本生效）。
// 条件语义（与引擎约定）：alive:id = 未阵亡，且已入队或正作为友军/可招募单位在当前战斗地图上；
// dead:id = 经典模式阵亡；recruited:id = 已入队。

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const STORY = process.env.STORY_DIR ? path.resolve(process.env.STORY_DIR) : path.join(ROOT, 'src', 'game', 'story');
const BDF = path.join(ROOT, 'tools', 'fonts', 'fusion-pixel-12px-proportional-zh_hans.bdf');

const STORY_FILES = ['prologue', 'ch1', 'ch2', 'ch3', 'ch4', 'ch5', 'ending'];
const ALL_FILES = [...STORY_FILES, 'quotes'];

const BGS = new Set(('festival throne_fire passage forest_night village_burning village_after capital_square river_bridge ' +
  'refugee_camp monastery_ext chapel snow_road snow_fort war_camp castle_gate throne_dawn coronation capital_dawn black map').split(' '));
const MUSIC = new Set('title sad calm tension prep player1 player2 enemy boss final ending stop'.split(' '));
const SFX = new Set('fire door hit_heavy death heal recruit chest phase warn burn thunder sword gold item levelup statup visit'.split(' '));
const POS = ['farleft', 'left', 'right', 'farright'];
const EX_FULL = ['normal', 'smile', 'angry', 'sad', 'surprise'];
const EX_MID = ['normal', 'smile', 'angry'];
const EX_MIN = ['normal'];
const CHARS = {
  elwin: ['艾尔文', EX_FULL], glenn: ['格伦', EX_FULL], nora: ['诺拉', EX_FULL], serin: ['赛琳', EX_FULL],
  doran: ['多兰', EX_FULL], sid: ['希德', EX_FULL], mira: ['米拉', EX_FULL], vera: ['薇拉', EX_FULL],
  aldric: ['艾德里克王', EX_FULL], valder: ['瓦尔德', EX_FULL],
  gord: ['戈尔德', EX_MID], hagen: ['哈根', EX_MID], morgan: ['摩根', EX_MID], grimm: ['格里姆', EX_MID],
  martha: ['玛莎', EX_MID], oswin: ['奥斯温', EX_MID], abbot: ['本笃', EX_MID],
  soldier: ['黑鹰士兵', EX_MIN], villager: ['村民', EX_MIN],
};
const NAME2ID = Object.fromEntries(Object.entries(CHARS).map(([id, [n]]) => [n, id]));
const COMPANIONS = ['glenn', 'nora', 'serin', 'doran', 'sid', 'mira', 'vera'];
const INITIAL = ['glenn', 'nora', 'serin'];
const RECRUIT_AT = { doran: 'ch1_doran_talk', sid: 'ch2_sid_talk', mira: 'ch3_mira_freed', vera: 'ch4_vera_talk' };
const JOIN_CH = { doran: 1, sid: 2, mira: 3, vera: 4 };

const REQUIRED = {
  prologue: ['prologue', 'interlude_proclaim'],
  ch1: ['ch1_pre', 'ch1_start', 'ch1_turn2', 'ch1_reinf_warn', 'ch1_doran_talk', 'ch1_village_a', 'ch1_village_b',
    'ch1_village_c', 'ch1_boss', 'ch1_boss_elwin', 'ch1_boss_death', 'ch1_post'],
  ch2: ['ch2_pre', 'ch2_start', 'ch2_turn3_hint', 'ch2_reinf_warn', 'ch2_sid_talk', 'ch2_boss', 'ch2_boss_elwin',
    'ch2_boss_doran', 'ch2_boss_death', 'ch2_martha_escape', 'ch2_post', 'interlude_square'],
  ch3: ['ch3_pre', 'ch3_start', 'ch3_reinf_warn', 'ch3_mira_freed', 'ch3_boss', 'ch3_boss_elwin', 'ch3_boss_mira',
    'ch3_boss_death', 'ch3_post'],
  ch4: ['ch4_pre', 'ch4_start', 'ch4_reinf_warn', 'ch4_turn5', 'ch4_last_turn', 'ch4_vera_talk', 'ch4_boss',
    'ch4_boss_elwin', 'ch4_boss_vera', 'ch4_boss_death', 'ch4_boss_retreat', 'ch4_post'],
  ch5: ['ch5_pre', 'ch5_start', 'ch5_reinf_warn', 'ch5_boss', 'ch5_boss_elwin', 'ch5_boss_glenn', 'ch5_boss_vera',
    'ch5_boss_doran', 'ch5_boss_sid', 'ch5_boss_defeated', 'ch5_post'],
  ending: ['ending'],
  quotes: [...COMPANIONS.flatMap((id) => ['death_' + id, 'retreat_' + id]), 'gameover_elwin', 'gameover_martha'],
};

// 主线播放顺序（第四章默认“坚守”路线：ch4_last_turn + ch4_boss_retreat；--ch4=kill 换成 ch4_boss_death）
const MAINLINE = [
  'prologue', 'interlude_proclaim',
  'ch1_pre', 'ch1_start', 'ch1_turn2', 'ch1_reinf_warn', 'ch1_doran_talk', 'ch1_village_a', 'ch1_village_b', 'ch1_village_c',
  'ch1_boss', 'ch1_boss_elwin', 'ch1_boss_death', 'ch1_post',
  'ch2_pre', 'ch2_start', 'ch2_turn3_hint', 'ch2_sid_talk', 'ch2_reinf_warn', 'ch2_boss', 'ch2_boss_elwin', 'ch2_boss_doran',
  'ch2_boss_death', 'ch2_martha_escape', 'ch2_post', 'interlude_square',
  'ch3_pre', 'ch3_start', 'ch3_reinf_warn', 'ch3_mira_freed', 'ch3_boss', 'ch3_boss_elwin', 'ch3_boss_mira', 'ch3_boss_death',
  'ch3_post',
  'ch4_pre', 'ch4_start', 'ch4_reinf_warn', 'ch4_vera_talk', 'ch4_turn5', 'ch4_boss', 'ch4_boss_elwin', 'ch4_boss_vera',
  'ch4_last_turn', 'ch4_boss_retreat', 'ch4_post',
  'ch5_pre', 'ch5_start', 'ch5_reinf_warn', 'ch5_boss', 'ch5_boss_elwin', 'ch5_boss_glenn', 'ch5_boss_vera', 'ch5_boss_doran',
  'ch5_boss_sid', 'ch5_boss_defeated', 'ch5_post',
  'ending',
];

// 触发条件本身保证在场的角色（这些脚本里该角色的台词不必包在 @if alive 里）
const GUARANTEED = {
  prologue: ['glenn', 'nora', 'serin'], interlude_proclaim: ['glenn', 'nora', 'serin'],
  ch1_start: ['doran'], ch1_doran_talk: ['doran'],
  ch2_start: ['sid'], ch2_sid_talk: ['sid'], ch2_boss_doran: ['doran'],
  ch3_start: ['mira'], ch3_mira_freed: ['mira'], ch3_boss_mira: ['mira'],
  ch4_start: ['vera'], ch4_vera_talk: ['vera'], ch4_boss_vera: ['vera'],
  ch5_boss_glenn: ['glenn'], ch5_boss_vera: ['vera'], ch5_boss_doran: ['doran'], ch5_boss_sid: ['sid'],
};
for (const id of COMPANIONS) { GUARANTEED['death_' + id] = [id]; GUARANTEED['retreat_' + id] = [id]; }

// 只在某角色在场时才会播放的脚本（交谈 / 专属首领对话）
const REQUIRES = {
  ch1_doran_talk: 'doran', ch2_sid_talk: 'sid', ch4_vera_talk: 'vera',
  ch2_boss_doran: 'doran', ch3_boss_mira: 'mira', ch4_boss_vera: 'vera',
  ch5_boss_glenn: 'glenn', ch5_boss_vera: 'vera', ch5_boss_doran: 'doran', ch5_boss_sid: 'sid',
};

const SLANG = ['哈哈哈', '666', '牛逼', '卧槽', '搞定', '给力', '靠谱', '吐槽', '点赞', '打卡', '躺平', '内卷', '破防',
  '绝绝子', '颜值', '粉丝', '拜拜', '嗨', '酷毙', '萌', '宅', '秒杀', '神马', '有木有', '坑爹', '稳了', '尬'];

// ---------------------------------------------------------------- 参数
const args = process.argv.slice(2);
const opt = (k) => { const a = args.find((s) => s === '--' + k || s.startsWith('--' + k + '=')); return a == null ? null : (a.includes('=') ? a.split('=')[1] : true); };
const DUMP = !!opt('dump');
const SIM = {
  dead: Object.fromEntries(String(opt('dead') || '').split(',').filter(Boolean).map((s) => { const [id, ch] = s.split(':'); return [id, Number(String(ch || 'ch1').replace('ch', ''))]; })),
  absent: new Set(String(opt('absent') || '').split(',').filter(Boolean)),
  late: new Set(String(opt('late') || '').split(',').filter(Boolean)),
  mode: opt('mode') === 'casual' ? 'casual' : 'classic',
  ch4kill: opt('ch4') === 'kill',
};
const CUSTOM = Object.keys(SIM.dead).length || SIM.absent.size || SIM.late.size || SIM.mode !== 'classic' || SIM.ch4kill;

// ---------------------------------------------------------------- 工具
const issues = [];
function report(level, file, script, ln, msg) { issues.push({ level, where: `${file}.js ${script}${ln ? ' L' + ln : ''}`, msg }); }
const hanCount = (s) => (s.match(/\p{Script=Han}/gu) || []).length;
const flagsSet = new Set();
const flagsTested = new Set();
const speakers = new Map(); // 显示名 -> {id, n}

let glyphs = null;
try {
  glyphs = new Set();
  for (const line of fs.readFileSync(BDF, 'utf8').split('\n')) if (line.startsWith('ENCODING ')) glyphs.add(Number(line.slice(9)));
} catch { glyphs = null; }
const missingGlyphs = new Map(); // 字 -> 位置
function checkGlyphs(str, where) {
  if (!glyphs) return;
  for (const ch of str) {
    if (ch === ' ' || ch === '\t') continue;
    if (!glyphs.has(ch.codePointAt(0)) && !missingGlyphs.has(ch)) missingGlyphs.set(ch, where);
  }
}

// ---------------------------------------------------------------- 解析
function parseCond(arg, at) {
  if (!arg) { at('error', '条件为空'); return []; }
  const atoms = [];
  for (const raw of arg.split('&')) {
    const a = raw.trim();
    const m = a.match(/^(!?)(alive|dead|recruited|flag|mode):([A-Za-z0-9_]+)$/);
    if (!m) { at('error', '无法解析的条件：' + a); continue; }
    const [, neg, kind, val] = m;
    if (['alive', 'dead', 'recruited'].includes(kind) && !COMPANIONS.includes(val)) at('warn', `条件里的角色 id 不是可离队角色：${val}`);
    if (kind === 'mode' && val !== 'classic' && val !== 'casual') at('error', '未知 mode：' + val);
    if (kind === 'flag') flagsTested.add(val);
    atoms.push({ neg: !!neg, kind, val });
  }
  return atoms;
}

function validateCmd(cmd, arg, at) {
  const parts = arg ? arg.split(/\s+/) : [];
  switch (cmd) {
    case 'bg': if (!BGS.has(arg)) at('error', '未知背景：' + arg); break;
    case 'music': if (!MUSIC.has(arg)) at('error', '未知曲目：' + arg); break;
    case 'sfx': if (!SFX.has(arg)) at('error', '未知音效：' + arg); break;
    case 'wait': case 'shake': if (!/^[0-9]+$/.test(arg)) at('error', `@${cmd} 需要整数参数`); break;
    case 'flash': if (arg !== 'white' && arg !== 'red') at('error', '@flash 只能是 white|red'); break;
    case 'fadeout': case 'fadein': if (arg) at('warn', `@${cmd} 不需要参数`); break;
    case 'chapter': {
      const [a, b] = arg.split('|');
      if (!a || !b) at('error', '@chapter 格式应为 “第X章|标题”');
      break;
    }
    case 'show': {
      const [id, pos, ex] = parts;
      if (!CHARS[id]) at('error', '@show 未知角色：' + id);
      else if (ex && !CHARS[id][1].includes(ex)) at('error', `@show ${id} 没有表情 ${ex}`);
      if (!POS.includes(pos)) at('error', '@show 未知位置：' + pos);
      if (parts.length > 3) at('error', '@show 参数过多');
      break;
    }
    case 'hide': if (arg !== 'all' && !CHARS[arg]) at('error', '@hide 未知角色：' + arg); break;
    case 'set': if (!/^[A-Za-z0-9_]+$/.test(arg)) at('error', '@set 旗标名只能用字母数字下划线'); else flagsSet.add(arg); break;
    default: at('error', '未知指令：@' + cmd);
  }
}

function checkText(text, at, where, maxLen = 60) {
  if (!text) { at('error', '台词为空'); return; }
  const len = [...text].length;
  if (len > maxLen) at('warn', `单句 ${len} 字，超过 ${maxLen} 字建议上限`);
  if (/[,.!?:;()"'<>]/.test(text)) at('warn', '台词里有半角标点：' + text);
  if (/[A-Za-z]/.test(text)) at('warn', '台词里有英文字母：' + text);
  for (const m of text.matchAll(/…+/g)) if (m[0].length % 2) at('warn', '省略号应成对使用“……”');
  for (const m of text.matchAll(/—+/g)) if (m[0].length % 2) at('warn', '破折号应成对使用“——”');
  const lq = (text.match(/“/g) || []).length, rq = (text.match(/”/g) || []).length;
  if (lq !== rq) at('warn', '中文引号不成对');
  if (text.includes('`') || text.includes('${')) at('error', '台词里出现反引号或 ${');
  for (const w of SLANG) if (text.includes(w)) at('warn', `疑似现代网络用语“${w}”`);
  checkGlyphs(text, where);
}

function parseScript(src, name, file) {
  const root = [];
  let cur = root;
  const ifStack = [];
  src.split(/\r?\n/).forEach((raw, i) => {
    const ln = i + 1;
    const line = raw.trim();
    const at = (level, msg) => report(level, file, name, ln, msg);
    if (!line || line.startsWith('#')) return;
    if (line.startsWith('@')) {
      const m = line.match(/^@([a-z]+)\s*(.*)$/);
      if (!m) { at('error', '无法解析的指令：' + line); return; }
      const cmd = m[1];
      const arg = m[2].trim();
      if (cmd === 'if') {
        const node = { type: 'if', ln, branches: [{ cond: parseCond(arg, at), body: [], ln }], hasElse: false };
        cur.push(node);
        ifStack.push({ node, parent: cur });
        cur = node.branches[0].body;
      } else if (cmd === 'elif' || cmd === 'else') {
        const top = ifStack[ifStack.length - 1];
        if (!top) { at('error', `@${cmd} 没有对应的 @if`); return; }
        if (top.node.hasElse) at('error', `@${cmd} 出现在 @else 之后`);
        if (cmd === 'else' && arg) at('warn', '@else 不应带参数');
        const br = { cond: cmd === 'else' ? null : parseCond(arg, at), body: [], ln };
        if (cmd === 'else') top.node.hasElse = true;
        top.node.branches.push(br);
        cur = br.body;
      } else if (cmd === 'end') {
        const top = ifStack.pop();
        if (!top) { at('error', '@end 没有对应的 @if'); return; }
        cur = top.parent;
      } else {
        validateCmd(cmd, arg, at);
        if (cmd === 'chapter') checkGlyphs(arg.replace('|', ''), `${file}.js ${name}`);
        cur.push({ type: 'cmd', cmd, arg, ln });
      }
      return;
    }
    const idx = line.indexOf('：');
    if (idx < 0) { at('error', '无法解析的行（缺少中文冒号）：' + line); return; }
    const head = line.slice(0, idx).trim();
    const text = line.slice(idx + 1).trim();
    const hm = head.match(/^([^[\]()（）]+)(?:\[([a-z_]+)\])?(?:[(（]([a-z]+)[)）])?$/);
    if (!hm) { at('error', '无法解析的说话人：' + head); return; }
    const [, disp, idRaw, ex] = hm;
    if (/[（）]/.test(head)) at('warn', '表情括号请用半角 ()');
    let id = null;
    if (disp === '旁白') {
      if (idRaw || ex) at('warn', '旁白不需要头像或表情');
    } else if (idRaw) {
      if (!CHARS[idRaw]) at('error', '未知角色 id：' + idRaw);
      else id = idRaw;
    } else if (NAME2ID[disp]) {
      id = NAME2ID[disp];
    } else {
      at('error', `未知说话人“${disp}”（通用角色请写成 显示名[id]）`);
    }
    if (id && ex && !CHARS[id][1].includes(ex)) at('error', `${disp}[${id}] 没有表情 ${ex}`);
    checkGlyphs(disp, `${file}.js ${name}`);
    checkText(text, at, `${file}.js ${name} L${ln}`);
    const key = disp + (id && CHARS[id][0] !== disp ? `[${id}]` : '');
    const sp = speakers.get(key) || { id, n: 0 };
    sp.n++;
    speakers.set(key, sp);
    cur.push({ type: 'say', ln, disp, id, ex, text });
  });
  if (ifStack.length) report('error', file, name, ifStack[ifStack.length - 1].node.ln, '@if 未闭合（缺少 @end）');
  return root;
}

// ---------------------------------------------------------------- 在场保护检查（遍历全部分支）
// facts: id -> 'alive' | 'dead' | 'absent'
function atomFacts(cond, facts) {
  for (const a of cond) {
    if (!COMPANIONS.includes(a.val)) continue;
    if (a.kind === 'alive' && !a.neg) facts[a.val] = 'alive';
    else if (a.kind === 'dead' && !a.neg) facts[a.val] = 'dead';
    else if (a.kind === 'alive' && a.neg && facts[a.val] !== 'dead') facts[a.val] = 'absent';
  }
}

function checkPresence(nodes, name, file, facts) {
  const guaranteed = GUARANTEED[name] || [];
  for (const n of nodes) {
    if (n.type === 'if') {
      const prior = [];
      for (const br of n.branches) {
        const f = { ...facts };
        // 前面的分支若是单一 alive:X，则后续分支中 X 不在场
        for (const pc of prior) if (pc.length === 1 && pc[0].kind === 'alive' && !pc[0].neg && COMPANIONS.includes(pc[0].val) && f[pc[0].val] !== 'dead') f[pc[0].val] = 'absent';
        if (br.cond) atomFacts(br.cond, f);
        checkPresence(br.body, name, file, f);
        if (br.cond) prior.push(br.cond);
      }
      continue;
    }
    const at = (level, msg) => report(level, file, name, n.ln, msg);
    let ids = [];
    if (n.type === 'say' && COMPANIONS.includes(n.id)) ids = [n.id];
    if (n.type === 'cmd' && n.cmd === 'show') { const id = n.arg.split(/\s+/)[0]; if (COMPANIONS.includes(id)) ids = [id]; }
    for (const id of ids) {
      if (guaranteed.includes(id)) continue;
      if (facts[id] === 'alive') continue;
      if (facts[id] === 'dead' || facts[id] === 'absent') at('error', `${CHARS[id][0]} 在此分支已不在场，却出场/说话`);
      else at('warn', `${CHARS[id][0]} 的出场/台词没有包在 @if alive:${id} 里`);
    }
    // 艾德里克王的台词只出现在序章与第三章的遗信里（过去的声音），提到伙伴不算“出场”
    if (n.type === 'say' && n.id !== 'aldric') {
      for (const id of COMPANIONS) {
        if (id === n.id || guaranteed.includes(id)) continue;
        if (!n.text.includes(CHARS[id][0])) continue;
        if (facts[id] === 'alive' || facts[id] === 'dead') continue;
        at('warn', `台词提到了可能缺席的“${CHARS[id][0]}”，却没有 alive/dead 条件保护`);
      }
    }
  }
}

// ---------------------------------------------------------------- 路线模拟
function chapterOrd(name) {
  if (name === 'prologue' || name === 'interlude_proclaim') return 0;
  if (name === 'ending') return 6;
  if (name === 'interlude_square') return 2;
  const m = name.match(/^ch([1-5])_/);
  return m ? Number(m[1]) : -1;
}
function phaseOf(name) {
  if (/_pre$/.test(name) || name === 'prologue' || name === 'interlude_proclaim') return 0;
  if (/_post$/.test(name) || name === 'interlude_square' || name === 'ending') return 2;
  return 1; // 战斗中
}

function evalCond(cond, st) {
  return cond.every((a) => {
    let v = false;
    if (a.kind === 'alive') v = st.alive(a.val);
    else if (a.kind === 'dead') v = st.dead.has(a.val);
    else if (a.kind === 'recruited') v = st.recruited.has(a.val);
    else if (a.kind === 'flag') v = st.flags.has(a.val);
    else if (a.kind === 'mode') v = st.mode === a.val;
    return a.neg ? !v : v;
  });
}

function runScript(nodes, st, out, slots, warnSlots) {
  for (const n of nodes) {
    if (n.type === 'if') {
      const br = n.branches.find((b) => !b.cond || evalCond(b.cond, st));
      if (br) runScript(br.body, st, out, slots, warnSlots);
      continue;
    }
    if (n.type === 'cmd') {
      if (n.cmd === 'set') st.flags.add(n.arg);
      if (n.cmd === 'show') {
        const [id, pos] = n.arg.split(/\s+/);
        for (const p of POS) if (slots[p] === id) slots[p] = null;
        slots[pos] = id;
      }
      if (n.cmd === 'hide') {
        if (n.arg === 'all') for (const p of POS) slots[p] = null;
        else for (const p of POS) if (slots[p] === n.arg) slots[p] = null;
      }
      out.push({ cmd: n.cmd, arg: n.arg });
      continue;
    }
    if (n.id && !POS.some((p) => slots[p] === n.id)) {
      const free = ['left', 'right', 'farleft', 'farright'].find((p) => !slots[p]);
      if (free) slots[free] = n.id;
      else warnSlots(n.ln, `同屏已满 4 人，${n.disp} 无空位自动出场（请先 @hide）`);
    }
    out.push({ say: n, han: hanCount(n.text) });
  }
}

function simulate(scripts, order, sim, collectWarn) {
  const recruited = new Set(INITIAL.filter((id) => !sim.absent.has(id)));
  const dead = new Set();
  const flags = new Set();
  const result = [];
  for (const name of order) {
    const s = scripts.get(name);
    const ord = chapterOrd(name);
    const ph = phaseOf(name);
    for (const [id, dch] of Object.entries(sim.dead)) {
      if (ord > dch || (ord === dch && ph === 2)) { dead.add(id); recruited.delete(id); }
    }
    for (const id of sim.late) if (JOIN_CH[id] === ord && ph === 2 && !dead.has(id)) recruited.add(id);
    const onMap = (id) => JOIN_CH[id] === ord && ph === 1;
    const st = {
      recruited, dead, flags, mode: sim.mode,
      alive: (id) => !dead.has(id) && (recruited.has(id) || onMap(id)),
    };
    const need = REQUIRES[name];
    if (need) {
      if (!st.alive(need)) continue;
      const isTalk = RECRUIT_AT[need] === name;
      if (isTalk && (sim.absent.has(need) || sim.late.has(need))) continue;
      if (!isTalk && !recruited.has(need)) continue; // 专属首领对话：该角色必须已是我方
    }
    if (!s) continue;
    const out = [];
    const slots = { farleft: null, left: null, right: null, farright: null };
    runScript(s.nodes, st, out, slots, (ln, msg) => collectWarn && report('warn', s.file, name, ln, msg));
    result.push({ name, file: s.file, out, han: out.reduce((a, o) => a + (o.han || 0), 0) });
    const rid = Object.keys(RECRUIT_AT).find((id) => RECRUIT_AT[id] === name);
    if (rid && !sim.absent.has(rid) && !dead.has(rid)) recruited.add(rid);
  }
  return result;
}

// ---------------------------------------------------------------- 主流程
const scripts = new Map();
const fileScripts = {};
for (const f of ALL_FILES) {
  const p = path.join(STORY, f + '.js');
  fileScripts[f] = [];
  if (!fs.existsSync(p)) { report('error', f, '(文件)', 0, '文件不存在'); continue; }
  const src = fs.readFileSync(p, 'utf8');
  if (src.includes('${')) report('error', f, '(文件)', 0, '文件里出现 ${（模板字符串会被插值）');
  let mod = null;
  try { mod = (await import(pathToFileURL(p).href)).default; } catch (e) { report('error', f, '(文件)', 0, '无法作为 ES Module 载入：' + e.message); continue; }
  if (!mod || typeof mod !== 'object') { report('error', f, '(文件)', 0, '没有 export default 对象'); continue; }
  for (const [name, text] of Object.entries(mod)) {
    if (typeof text !== 'string') { report('error', f, name, 0, '脚本不是字符串'); continue; }
    if (scripts.has(name)) report('error', f, name, 0, '脚本名重复');
    const nodes = parseScript(text, name, f);
    scripts.set(name, { file: f, nodes });
    fileScripts[f].push(name);
    checkPresence(nodes, name, f, {});
  }
  for (const need of REQUIRED[f] || []) if (!mod[need]) report('error', f, need, 0, '缺少必需的脚本');
}

// 结局必须为每个可离队角色写 dead 悼念
if (scripts.has('ending')) {
  const txt = JSON.stringify(scripts.get('ending').nodes);
  for (const id of COMPANIONS) if (!txt.includes(`"kind":"dead","val":"${id}"`)) report('error', 'ending', 'ending', 0, `结局缺少 @if dead:${id} 的悼念`);
}
for (const f of flagsTested) if (!flagsSet.has(f)) report('error', '-', '旗标', 0, `flag:${f} 被判断但从未 @set`);
for (const f of flagsSet) if (!flagsTested.has(f)) report('info', '-', '旗标', 0, `@set ${f} 从未被判断`);
for (const n of MAINLINE) if (!scripts.has(n)) report('error', '-', n, 0, '主线顺序里的脚本不存在');
for (const n of scripts.keys()) if (!MAINLINE.includes(n) && !n.startsWith('death_') && !n.startsWith('retreat_') && !n.startsWith('gameover_') && n !== 'ch4_boss_death')
  report('warn', scripts.get(n).file, n, 0, '脚本不在主线顺序表里（统计时不计入主线）');

// bios
let bios = null;
try {
  bios = (await import(pathToFileURL(path.join(STORY, 'bios.js')).href)).default;
  for (const id of ['elwin', ...COMPANIONS]) {
    const t = bios[id];
    if (typeof t !== 'string') { report('error', 'bios', id, 0, '缺少人物介绍'); continue; }
    const n = [...t].length;
    const h = hanCount(t);
    if (n < 60 || n > 90) report('warn', 'bios', id, 0, `人物介绍 ${n} 字（含标点），不在 60~90 字范围`);
    if (h < 60) report('warn', 'bios', id, 0, `人物介绍只有 ${h} 个汉字，少于 60`);
    checkText(t, (level, msg) => report(level, 'bios', id, 0, msg), `bios.js ${id}`, 90);
  }
} catch (e) { report('error', 'bios', '(文件)', 0, '无法载入：' + e.message); }

// 主线统计（默认路线）
const mainOrder = MAINLINE.flatMap((n) => (n === 'ch4_last_turn' ? [] : n === 'ch4_boss_retreat' ? ['ch4_boss_death'] : [n]));
const defaultSim = { dead: {}, absent: new Set(), late: new Set(), mode: 'classic', ch4kill: false };
const mainRun = simulate(scripts, MAINLINE, defaultSim, true);
const mainHan = Object.fromEntries(mainRun.map((r) => [r.name, r.han]));
const allHan = (nodes) => nodes.reduce((a, n) => a + (n.type === 'say' ? hanCount(n.text) : n.type === 'if' ? n.branches.reduce((b, br) => b + allHan(br.body), 0) : 0), 0);

const pad = (s, n) => { s = String(s); const w = [...s].reduce((a, c) => a + (c.charCodeAt(0) > 255 ? 2 : 1), 0); return s + ' '.repeat(Math.max(0, n - w)); };
const lpad = (s, n) => ' '.repeat(Math.max(0, n - String(s).length)) + s;
console.log('《灰烬王冠》剧情脚本统计（有效字数 = 台词/旁白正文里的汉字）\n');
let total = 0;
const perFile = {};
const cat = { story: 0, event: 0, boss: 0 };
for (const f of ALL_FILES) {
  if (!fileScripts[f].length) continue;
  console.log(`== ${f}.js ==`);
  let sub = 0;
  for (const name of fileScripts[f]) {
    const s = scripts.get(name);
    const m = mainHan[name];
    console.log(`  ${pad(name, 22)} 主线 ${lpad(m == null ? '-' : m, 5)}   全部分支 ${lpad(allHan(s.nodes), 5)}`);
    if (m != null) {
      sub += m;
      if (/_boss/.test(name)) cat.boss += m; else if (phaseOf(name) === 1) cat.event += m; else cat.story += m;
    }
  }
  perFile[f] = sub;
  if (STORY_FILES.includes(f)) total += sub;
  console.log(`  ${pad('小计（主线）', 22)}      ${lpad(sub, 5)}\n`);
}
console.log('主线字数（各文件）：' + STORY_FILES.map((f) => `${f} ${perFile[f] || 0}`).join('，'));
console.log(`主线合计：${total} 字  （剧情场景 ${cat.story} / 战斗事件 ${cat.event} / 首领对话 ${cat.boss}）`);
console.log(`阅读时长：按 350 字/分 ≈ ${(total / 350).toFixed(1)} 分钟，按 400 字/分 ≈ ${(total / 400).toFixed(1)} 分钟`);
const altRun = simulate(scripts, mainOrder, defaultSim, false);
console.log(`（第四章击败格里姆路线合计：${altRun.reduce((a, r) => a + r.han, 0)} 字）`);
if (total < 7000 || total > 8000) report('warn', '-', '主线', 0, `主线字数 ${total} 不在 7000~8000 范围`);

console.log('\n说话人（显示名[头像] × 句数）：');
console.log('  ' + [...speakers.entries()].map(([k, v]) => `${k}${v.id && CHARS[v.id][0] === k ? '' : ''}×${v.n}`).join('  '));
console.log('\n旗标：set = ' + ([...flagsSet].join(', ') || '无') + '；tested = ' + ([...flagsTested].join(', ') || '无'));
if (bios) console.log('人物介绍字数（含标点/汉字）：' + Object.entries(bios).map(([k, v]) => `${k} ${[...v].length}/${hanCount(v)}`).join('，'));

if (missingGlyphs.size) report('error', '-', '字体', 0, '字库缺字：' + [...missingGlyphs.entries()].map(([c, w]) => `${c}(${w})`).join(' '));
if (!glyphs) report('info', '-', '字体', 0, '未找到 BDF 字库，跳过缺字检查');

// 自定义路线 / 台词转储
if (DUMP || CUSTOM) {
  const order = SIM.ch4kill ? mainOrder : MAINLINE;
  const run = simulate(scripts, order, SIM, false);
  const t = run.reduce((a, r) => a + r.han, 0);
  console.log(`\n—— 路线预览：dead=${JSON.stringify(SIM.dead)} absent=${[...SIM.absent]} late=${[...SIM.late]} mode=${SIM.mode}${SIM.ch4kill ? ' ch4=kill' : ''}  合计 ${t} 字 ——`);
  if (DUMP) {
    for (const r of run) {
      console.log(`\n[${r.name}]  (${r.han} 字)`);
      for (const o of r.out) {
        if (o.say) console.log(`  ${o.say.disp}${o.say.ex ? '(' + o.say.ex + ')' : ''}：${o.say.text}`);
        else if (['bg', 'chapter', 'music', 'set'].includes(o.cmd)) console.log(`    @${o.cmd} ${o.arg}`);
      }
    }
  }
}

const errors = issues.filter((i) => i.level === 'error');
const warns = issues.filter((i) => i.level === 'warn');
const infos = issues.filter((i) => i.level === 'info');
console.log(`\n错误 ${errors.length}，警告 ${warns.length}，提示 ${infos.length}`);
for (const i of [...errors, ...warns, ...infos]) console.log(`  [${i.level === 'error' ? '错误' : i.level === 'warn' ? '警告' : '提示'}] ${i.where}：${i.msg}`);
process.exitCode = errors.length ? 1 : 0;
