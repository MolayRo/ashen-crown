// 五个章节：地图、单位、事件、增援、目标
// 单位字段：cls 职业、lv 等级、x,y、items、ai（模式见 ai.js）、diff 出现的难度、drop 掉落最后一件物品
// 增援 turn = 该批敌人第一次行动的回合（在前一回合敌方回合结束时出现，前一回合我方回合开始时预告）

// ---- 网格工具（用于室内/城堡地图）----
function grid(w, h, ch) { return Array.from({ length: h }, () => Array(w).fill(ch)); }
function rect(g, x, y, w, h, ch) { for (let j = y; j < y + h; j++) for (let i = x; i < x + w; i++) g[j][i] = ch; }
function put(g, pts, ch) { for (const [x, y] of pts) g[y][x] = ch; }
function rows(g) { return g.map((r) => r.join('')); }

// =====================================================================
// 第一章 燃烧的边境村
// =====================================================================
const CH1 = {
  id: 'ch1', num: 1, title: '第一章', name: '燃烧的边境村', theme: 'plains',
  pre: 'ch1_pre', post: 'ch1_post', prep: false,
  music: { player: 'player1', enemy: 'enemy' },
  rows: [
    'TTTTTTThh.....TTTTTT^^^^',
    'TTTTT..h...T...HHH.TT^^^',
    'TTT....,....T..HVH..T^^A',
    'TT..T.........r."...hT^^',
    'T..TT...HH......"....hTT',
    '...T....VH...,..".......',
    '..TT.....,......""""""""',
    '.TT..r.....""""""".HH...',
    '...T..""""""......,HV.T.',
    '..TT..".....f.f.....,...',
    '"""""""......,.....TT...',
    '..T........HH.......TT..',
    '.TT..T.....VH...,....h..',
    'TT...TT..........T..hh..',
    'TTT......TT.....TTT.h^^.',
    'TTTT..TTTTT...TTTTTT^^^^',
  ],
  deploy: [[2, 10], [1, 11], [3, 11], [1, 9]],
  objective: { type: 'boss', text: '击败追兵队长 戈尔德', lose: '艾尔文阵亡' },
  bonus: '在追兵烧毁之前访问村庄，保护村民',
  villages: {
    '8,5': { script: 'ch1_village_a', item: 'vulnerary' },
    '20,8': { script: 'ch1_village_b', gold: 500 },
    '11,12': { script: 'ch1_village_c', item: 'seed_str' },
  },
  chests: {},
  units: [
    { char: 'doran', team: 'ally', x: 16, y: 2, hp: 18, ai: { mode: 'hold', leash: 1, home: [16, 2], wake: false } },
    { boss: 'gord', x: 21, y: 6, ai: { mode: 'hold', range: 3 } },
    { cls: 'fighter', lv: 2, x: 8, y: 11, items: ['iron_axe'] },
    { cls: 'soldier', lv: 2, x: 9, y: 8, items: ['iron_lance'] },
    { cls: 'mercenary', lv: 3, x: 13, y: 9, items: ['iron_sword'], ai: { mode: 'hold', range: 4 }, diff: ['normal', 'hard'] },
    { cls: 'fighter', lv: 2, x: 17, y: 11, items: ['iron_axe'], ai: { mode: 'raze', villages: [[11, 12]] } },
    { cls: 'fighter', lv: 2, x: 22, y: 12, items: ['iron_axe'], ai: { mode: 'raze', villages: [[20, 8]], start: 2 } },
    { cls: 'fighter', lv: 3, x: 13, y: 2, items: ['iron_axe'], ai: { mode: 'aggressive' }, diff: ['normal', 'hard'] },
    { cls: 'soldier', lv: 2, x: 15, y: 3, items: ['iron_lance'] },
    { cls: 'soldier', lv: 2, x: 18, y: 3, items: ['iron_lance'], drop: true },
    { cls: 'archer', lv: 2, x: 18, y: 5, items: ['iron_bow'], ai: { mode: 'hold', range: 4 } },
    { cls: 'archer', lv: 3, x: 12, y: 6, items: ['iron_bow'], ai: { mode: 'hold', range: 3 }, diff: ['hard'] },
    { cls: 'fighter', lv: 3, x: 10, y: 13, items: ['iron_axe'], diff: ['hard'] },
  ],
  reinforcements: [
    { turn: 4, warn: 'ch1_reinf_warn', units: [
      { cls: 'soldier', lv: 2, x: 23, y: 6, items: ['iron_lance'] },
      { cls: 'fighter', lv: 2, x: 23, y: 7, items: ['iron_axe'], diff: ['normal', 'hard'] },
      { cls: 'mercenary', lv: 3, x: 23, y: 5, items: ['iron_sword'], diff: ['hard'] },
    ] },
  ],
  events: [
    { id: 'start', on: 'start', script: 'ch1_start' },
    { id: 't2', on: 'turn', turn: 2, script: 'ch1_turn2', cond: 'onmap:doran' },
    { id: 'talk_doran', on: 'talk', a: 'elwin', b: 'doran', script: 'ch1_doran_talk', recruit: true },
    { id: 'boss_elwin', on: 'combat', unit: 'gord', with: 'elwin', script: 'ch1_boss_elwin' },
    { id: 'boss', on: 'combat', unit: 'gord', script: 'ch1_boss' },
    { id: 'boss_death', on: 'death', unit: 'gord', script: 'ch1_boss_death' },
  ],
  tutorial: true,
  shop: [],
};

// =====================================================================
// 第二章 断桥伏击
// =====================================================================
const CH2 = {
  id: 'ch2', num: 2, title: '第二章', name: '断桥伏击', theme: 'plains',
  pre: 'ch2_pre', post: 'ch2_post', after: 'interlude_square', prep: true,
  music: { player: 'player1', enemy: 'enemy' },
  rows: [
    'TTTTT^^hh..~~..TTTTT^^^^^^',
    'TTTT..h....~~...TTT.."""""',
    'TTT..."""""=="""""""""....',
    'TT....".T..~~.T...TT..h...',
    'T..T..".T..~~...,...HH.hh.',
    '...T..".,..~~.....r.VH.h..',
    '..TT.."....~~......T....h.',
    '.TT...".T..~~..T.....,.F..',
    '"""""""""""BB"""""""""""""',
    '..T....,...~~..T......h...',
    '.TT........~~..r.r........',
    '...T.......~~...rr.C...TT.',
    'TT....T....~~..T..rCr..TT.',
    'TTT........__......T....h.',
    'TTTT.......__....hh....^^^',
    'TTTTTT....T~~TTTTTT^^^^^^^',
  ],
  deploy: [[3, 8], [2, 9], [4, 9], [2, 7], [4, 7], [3, 10]],
  objective: { type: 'escape', text: '护送村长玛莎抵达东侧撤离点', lose: '艾尔文或玛莎阵亡',
    escape: [[25, 6], [25, 7], [25, 8], [25, 9], [25, 10]] },
  villages: {},
  chests: { '19,11': { item: 'steel_bow' }, '19,12': { item: 'elixir' } },
  units: [
    { boss: 'martha', team: 'player', escort: true, isBoss: false, x: 1, y: 8, ai: null },
    { boss: 'hagen', x: 23, y: 7, ai: { mode: 'guard' } },
    { char: 'sid', team: 'enemy', recruitable: true, x: 24, y: 11, ai: { mode: 'thief', start: 2, flee: 8, lurk: [17, 11], escape: [[25, 15], [24, 15]] } },
    { cls: 'knight', lv: 3, x: 13, y: 2, items: ['iron_lance'], ai: { mode: 'hold', leash: 1 } },
    { cls: 'soldier', lv: 3, x: 14, y: 3, items: ['iron_lance'], ai: { mode: 'hold', range: 3 } },
    { cls: 'archer', lv: 3, x: 14, y: 5, items: ['iron_bow'], ai: { mode: 'hold', range: 3 } },
    { cls: 'archer', lv: 3, x: 15, y: 12, items: ['iron_bow'], ai: { mode: 'hold', range: 3 } },
    { cls: 'fighter', lv: 3, x: 14, y: 13, items: ['iron_axe'], ai: { mode: 'hold', range: 2 } },
    { cls: 'soldier', lv: 3, x: 16, y: 8, items: ['iron_lance'], ai: { mode: 'hold', range: 4 } },
    { cls: 'mercenary', lv: 4, x: 18, y: 5, items: ['iron_sword'], diff: ['normal', 'hard'] },
    { cls: 'fighter', lv: 3, x: 20, y: 9, items: ['hand_axe'], ai: { mode: 'hold', range: 4 } },
    { cls: 'archer', lv: 3, x: 14, y: 9, items: ['iron_bow'], ai: { mode: 'hold', range: 2 }, diff: ['hard'] },
    { cls: 'fighter', lv: 4, x: 17, y: 10, items: ['iron_axe'], diff: ['hard'] },
  ],
  reinforcements: [
    { turn: 4, warn: 'ch2_reinf_warn', units: [
      { cls: 'cavalier', lv: 3, x: 25, y: 1, items: ['iron_lance'] },
      { cls: 'cavalier', lv: 3, x: 24, y: 1, items: ['iron_sword'], diff: ['normal', 'hard'] },
    ] },
    { turn: 7, warn: 'ch2_reinf_warn', units: [
      { cls: 'cavalier', lv: 4, x: 25, y: 1, items: ['javelin'] },
      { cls: 'soldier', lv: 4, x: 24, y: 1, items: ['iron_lance'], diff: ['hard'] },
    ], diff: ['normal', 'hard'] },
  ],
  events: [
    { id: 'start', on: 'start', script: 'ch2_start' },
    { id: 't3', on: 'turn', turn: 3, script: 'ch2_turn3_hint', cond: 'onmap:sid&!recruited:sid' },
    { id: 'talk_sid', on: 'talk', a: 'elwin', b: 'sid', script: 'ch2_sid_talk', recruit: true },
    { id: 'boss_elwin', on: 'combat', unit: 'hagen', with: 'elwin', script: 'ch2_boss_elwin' },
    { id: 'boss_doran', on: 'combat', unit: 'hagen', with: 'doran', script: 'ch2_boss_doran' },
    { id: 'boss', on: 'combat', unit: 'hagen', script: 'ch2_boss' },
    { id: 'boss_death', on: 'death', unit: 'hagen', script: 'ch2_boss_death' },
    { id: 'escape', on: 'escape', unit: 'martha', script: 'ch2_martha_escape' },
  ],
  shop: ['iron_sword', 'iron_lance', 'javelin', 'iron_bow', 'vulnerary', 'door_key'],
};

// =====================================================================
// 第三章 沉默的修道院（室内）
// =====================================================================
function ch3Rows() {
  const W = 24, H = 16;
  const g = grid(W, H, '#');
  // 南侧庭院（室外）
  rect(g, 1, 12, 22, 4, '.');
  put(g, [[2, 12], [3, 13], [20, 12], [21, 13], [1, 15], [22, 15], [6, 14], [17, 14]], 'T');
  put(g, [[4, 14], [8, 13], [15, 13], [19, 14]], ',');
  rect(g, 11, 12, 2, 4, '"');
  // 回廊大厅
  rect(g, 1, 8, 22, 3, '+');
  put(g, [[3, 9], [7, 9], [16, 9], [20, 9]], '|');
  // 正门
  put(g, [[11, 11], [12, 11]], 'G');
  // 礼拜堂
  rect(g, 8, 1, 8, 7, '+');
  rect(g, 11, 2, 2, 6, 'c');
  put(g, [[11, 1], [12, 1]], 'a');
  put(g, [[9, 2], [14, 2], [9, 5], [14, 5]], '|');
  // 西侧地牢
  rect(g, 1, 3, 5, 4, '+');
  put(g, [[3, 1]], 'P');
  put(g, [[3, 2]], 'D');
  put(g, [[3, 7]], '+');
  // 东侧储藏室
  rect(g, 17, 1, 6, 6, '+');
  put(g, [[18, 1], [21, 1]], 'C');
  put(g, [[19, 7]], 'D');
  // 楼梯（增援）
  put(g, [[22, 8]], 'S');
  put(g, [[1, 10]], 'S');
  return rows(g);
}

const CH3 = {
  id: 'ch3', num: 3, title: '第三章', name: '沉默的修道院', theme: 'indoor',
  pre: 'ch3_pre', post: 'ch3_post', prep: true,
  music: { player: 'player1', enemy: 'enemy' },
  rows: ch3Rows(),
  deploy: [[11, 14], [12, 14], [10, 15], [13, 15], [9, 14], [14, 14], [11, 15]],
  objective: { type: 'rout', text: '救出地牢中的囚犯，并击败全部驻军', lose: '艾尔文阵亡', need: 'flag:freed_mira' },
  villages: {},
  chests: { '18,1': { item: 'thunder' }, '21,1': { item: 'robe_hp' } },
  units: [
    { char: 'mira', team: 'npc', caged: true, x: 3, y: 1, ai: { mode: 'idle' } },
    { boss: 'morgan', x: 11, y: 1, ai: { mode: 'guard' } },
    { cls: 'darkmage', lv: 4, x: 9, y: 3, items: ['dark'], ai: { mode: 'hold', range: 4 } },
    { cls: 'darkmage', lv: 4, x: 14, y: 3, items: ['dark'], ai: { mode: 'hold', range: 4 } },
    { cls: 'priest', lv: 4, x: 12, y: 4, items: ['heal_staff'], ai: { mode: 'support' } },
    { cls: 'mercenary', lv: 5, x: 11, y: 7, items: ['iron_sword'], ai: { mode: 'hold', range: 3 } },
    { cls: 'soldier', lv: 4, x: 3, y: 4, name: '狱卒', items: ['iron_lance', 'door_key'], drop: true, ai: { mode: 'hold', range: 3 } },
    { cls: 'soldier', lv: 4, x: 5, y: 9, items: ['iron_lance'] },
    { cls: 'fighter', lv: 4, x: 17, y: 9, items: ['iron_axe'] },
    { cls: 'archer', lv: 4, x: 9, y: 10, items: ['iron_bow'], ai: { mode: 'hold', range: 4 } },
    { cls: 'knight', lv: 4, x: 19, y: 8, items: ['iron_lance'], ai: { mode: 'hold', range: 2 } },
    { cls: 'mage', lv: 3, x: 21, y: 10, items: ['fire'], ai: { mode: 'hold', range: 4 }, diff: ['normal', 'hard'] },
    { cls: 'darkmage', lv: 5, x: 4, y: 5, items: ['dark'], ai: { mode: 'hold', range: 3 }, diff: ['hard'] },
    { cls: 'mercenary', lv: 5, x: 14, y: 9, items: ['iron_sword'], diff: ['hard'] },
  ],
  reinforcements: [
    { turn: 3, warn: 'ch3_reinf_warn', units: [
      { cls: 'soldier', lv: 4, x: 22, y: 8, items: ['iron_lance'] },
      { cls: 'mercenary', lv: 4, x: 21, y: 8, items: ['iron_sword'], diff: ['normal', 'hard'] },
    ] },
    { turn: 5, warn: 'ch3_reinf_warn', units: [
      { cls: 'darkmage', lv: 4, x: 1, y: 10, items: ['dark'] },
      { cls: 'fighter', lv: 4, x: 2, y: 10, items: ['hammer'] },
    ] },
  ],
  events: [
    { id: 'start', on: 'start', script: 'ch3_start' },
    { id: 'free_mira', on: 'door', at: [3, 2], script: 'ch3_mira_freed', effect: 'free:mira' },
    { id: 'boss_elwin', on: 'combat', unit: 'morgan', with: 'elwin', script: 'ch3_boss_elwin' },
    { id: 'boss_mira', on: 'combat', unit: 'morgan', with: 'mira', script: 'ch3_boss_mira' },
    { id: 'boss', on: 'combat', unit: 'morgan', script: 'ch3_boss' },
    { id: 'boss_death', on: 'death', unit: 'morgan', script: 'ch3_boss_death' },
  ],
  shop: ['iron_sword', 'steel_sword', 'iron_lance', 'javelin', 'iron_axe', 'iron_bow', 'fire', 'heal_staff', 'vulnerary', 'door_key', 'chest_key'],
};

// =====================================================================
// 第四章 风雪山隘（坚守）
// =====================================================================
function ch4Rows() {
  const W = 26, H = 18;
  const g = grid(W, H, '.');
  // 两侧山岭
  rect(g, 0, 0, 5, 8, '^');
  rect(g, 21, 0, 5, 6, '^');
  put(g, [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [23, 0], [24, 0], [25, 0], [24, 1], [25, 1], [25, 2]], 'A');
  rect(g, 5, 0, 3, 3, '^');
  rect(g, 18, 0, 3, 3, '^');
  put(g, [[6, 0], [19, 0], [20, 1]], 'A');
  // 北方大道
  for (let y = 0; y <= 8; y++) g[y][12] = '"';
  put(g, [[13, 3], [13, 4], [11, 6]], '"');
  // 西侧崖道：窄路 + 悬崖
  rect(g, 0, 8, 3, 10, 'x');
  for (let y = 2; y <= 11; y++) g[y][5] = '.';
  for (let y = 2; y <= 8; y++) { g[y][4] = 'x'; }
  put(g, [[3, 9], [3, 10], [3, 11], [3, 12]], 'x');
  // 东侧坡道
  rect(g, 20, 6, 4, 5, 'h');
  put(g, [[24, 6], [25, 6], [25, 7], [24, 8], [25, 8]], '^');
  // 林木
  put(g, [[8, 4], [9, 5], [15, 4], [16, 5], [7, 7], [17, 7], [9, 2], [16, 2], [6, 13], [19, 13], [7, 15], [18, 16]], 'T');
  // 要塞：城墙 + 北门 + 东西侧门 + 中央要塞
  rect(g, 7, 9, 12, 7, '#');
  rect(g, 8, 10, 10, 5, '+');
  put(g, [[12, 9]], 'G');
  put(g, [[7, 12], [18, 12]], '+');
  put(g, [[12, 13]], 'F');
  put(g, [[9, 11], [15, 11]], 'F');
  // 中央要塞：三面石墙，只有北侧一个入口
  put(g, [[11, 13], [13, 13], [12, 14], [11, 14], [13, 14]], '#');
  // 要塞南侧：难民营地
  rect(g, 8, 16, 10, 2, '.');
  put(g, [[12, 16], [12, 17]], '"');
  return rows(g);
}

const CH4 = {
  id: 'ch4', num: 4, title: '第四章', name: '风雪山隘', theme: 'snow',
  pre: 'ch4_pre', post: 'ch4_post', prep: true,
  reward: { item: 'holy_sword', to: 'elwin' },
  music: { player: 'player2', enemy: 'enemy' },
  rows: ch4Rows(),
  deploy: [[12, 13], [12, 12], [11, 12], [13, 12], [12, 10], [10, 12], [14, 12], [10, 13]],
  objective: { type: 'defend', turns: 8, text: '坚守要塞 8 回合，或击败敌将格里姆', lose: '艾尔文阵亡 / 敌军踏上要塞中央', defendTile: [12, 13] },
  warning: '【注意】敌军踏上要塞中央（蓝色盾牌标记）就会失败！守住北门与两侧门，让艾尔文坐镇中央。',
  villages: {},
  chests: {},
  units: [
    { boss: 'grimm', x: 12, y: 1, ai: { mode: 'hold', until: 5 } },
    { char: 'vera', team: 'enemy', recruitable: true, x: 22, y: 3, ai: { mode: 'passive', goal: [16, 13] } },
    { cls: 'pegasus', lv: 5, x: 23, y: 4, items: ['iron_lance'], ai: { mode: 'hold', until: 2 } },
    { cls: 'pegasus', lv: 5, x: 21, y: 2, items: ['javelin'], ai: { mode: 'hold', until: 3 }, diff: ['normal', 'hard'] },
    { cls: 'soldier', lv: 5, x: 12, y: 4, items: ['iron_lance'], ai: { mode: 'seize' } },
    { cls: 'fighter', lv: 5, x: 11, y: 3, items: ['iron_axe'] },
    { cls: 'archer', lv: 5, x: 13, y: 2, items: ['iron_bow'] },
    { cls: 'mercenary', lv: 5, x: 5, y: 3, items: ['iron_sword'] },
    { cls: 'soldier', lv: 5, x: 5, y: 5, items: ['javelin'], ai: { mode: 'seize' } },
    { cls: 'fighter', lv: 5, x: 21, y: 8, items: ['hand_axe'] },
    { cls: 'cavalier', lv: 5, x: 22, y: 9, items: ['iron_lance'], diff: ['normal', 'hard'] },
    { cls: 'mage', lv: 5, x: 13, y: 5, items: ['fire'], diff: ['hard'] },
    { cls: 'wyvern', lv: 6, x: 24, y: 3, items: ['iron_axe'], diff: ['hard'] },
  ],
  reinforcements: [
    { turn: 3, warn: 'ch4_reinf_warn', units: [
      { cls: 'soldier', lv: 5, x: 12, y: 0, items: ['iron_lance'], ai: { mode: 'seize' } },
      { cls: 'archer', lv: 5, x: 11, y: 0, items: ['iron_bow'] },
    ] },
    { turn: 4, warn: 'ch4_reinf_warn', units: [
      { cls: 'fighter', lv: 5, x: 5, y: 2, items: ['iron_axe'] },
      { cls: 'fighter', lv: 5, x: 5, y: 3, items: ['hammer'], diff: ['normal', 'hard'] },
    ] },
    { turn: 5, warn: 'ch4_reinf_warn', units: [
      { cls: 'wyvern', lv: 6, x: 24, y: 4, items: ['iron_lance'] },
      { cls: 'cavalier', lv: 5, x: 23, y: 9, items: ['javelin'] },
    ] },
    { turn: 6, warn: 'ch4_reinf_warn', diff: ['hard'], units: [
      { cls: 'pegasus', lv: 6, x: 22, y: 2, items: ['iron_lance'] },
      { cls: 'pegasus', lv: 6, x: 24, y: 2, items: ['javelin'] },
    ] },
    { turn: 7, warn: 'ch4_reinf_warn', units: [
      { cls: 'soldier', lv: 6, x: 12, y: 0, items: ['steel_lance'], ai: { mode: 'seize' } },
      { cls: 'fighter', lv: 6, x: 11, y: 0, items: ['steel_axe'], diff: ['normal', 'hard'] },
      { cls: 'mercenary', lv: 6, x: 13, y: 0, items: ['steel_sword'], diff: ['hard'] },
      { cls: 'mage', lv: 6, x: 12, y: 1, items: ['thunder'], diff: ['hard'] },
    ] },
  ],
  events: [
    { id: 'start', on: 'start', script: 'ch4_start' },
    { id: 't5', on: 'turn', turn: 5, script: 'ch4_turn5', cond: 'onmap:grimm' },
    { id: 't8', on: 'turn', turn: 8, script: 'ch4_last_turn' },
    { id: 'talk_vera', on: 'talk', a: 'elwin', b: 'vera', script: 'ch4_vera_talk', recruit: true },
    { id: 'boss_elwin', on: 'combat', unit: 'grimm', with: 'elwin', script: 'ch4_boss_elwin' },
    { id: 'boss_vera', on: 'combat', unit: 'grimm', with: 'vera', script: 'ch4_boss_vera' },
    { id: 'boss', on: 'combat', unit: 'grimm', script: 'ch4_boss' },
    { id: 'boss_death', on: 'death', unit: 'grimm', script: 'ch4_boss_death' },
  ],
  shop: ['steel_sword', 'iron_lance', 'steel_lance', 'javelin', 'horseslayer', 'iron_axe', 'steel_bow', 'fire', 'thunder', 'heal_staff', 'mend_staff', 'vulnerary', 'elixir'],
};

// =====================================================================
// 第五章 重返王城（占领）
// =====================================================================
function ch5Rows() {
  const W = 28, H = 24;
  const g = grid(W, H, '#');
  // 城外（南）
  rect(g, 0, 16, 28, 8, '.');
  put(g, [[1, 17], [2, 18], [0, 20], [25, 17], [26, 19], [27, 21], [4, 22], [23, 22], [1, 23], [26, 23], [6, 19], [21, 19]], 'T');
  for (let y = 16; y < 24; y++) { g[y][13] = '"'; g[y][14] = '"'; }
  put(g, [[9, 21], [18, 21], [5, 17], [22, 17]], ',');
  // 外墙与城门
  rect(g, 0, 15, 28, 1, '#');
  put(g, [[13, 15], [14, 15]], 'G');
  // 庭院
  rect(g, 1, 10, 26, 5, '.');
  for (let y = 10; y < 15; y++) { g[y][13] = '"'; g[y][14] = '"'; }
  put(g, [[3, 11], [5, 13], [8, 11], [19, 11], [22, 13], [24, 11]], 'T');
  put(g, [[2, 13], [25, 13]], 'F');
  // 大厅外墙
  rect(g, 0, 9, 28, 1, '#');
  put(g, [[13, 9], [14, 9]], 'D');
  put(g, [[4, 9], [23, 9]], '+');
  // 大厅
  rect(g, 1, 5, 26, 4, '+');
  rect(g, 13, 5, 2, 4, 'c');
  put(g, [[4, 6], [8, 6], [19, 6], [23, 6], [4, 8], [23, 8]], '|');
  // 西侧宝库、东侧兵营
  rect(g, 1, 1, 7, 3, '+');
  put(g, [[2, 1], [4, 1], [6, 1]], 'C');
  put(g, [[4, 4]], 'D');
  rect(g, 20, 1, 7, 3, '+');
  put(g, [[26, 1], [20, 1]], 'S');
  put(g, [[23, 4]], '+');
  // 王座厅
  rect(g, 9, 1, 10, 4, '+');
  rect(g, 13, 2, 2, 3, 'c');
  put(g, [[13, 1]], 'K');
  put(g, [[14, 1]], 'c');
  put(g, [[10, 2], [17, 2], [10, 4], [17, 4]], '|');
  put(g, [[13, 4], [14, 4]], 'c');
  // 西侧小楼梯（增援）
  put(g, [[1, 7]], 'S');
  return rows(g);
}

const CH5 = {
  id: 'ch5', num: 5, title: '第五章', name: '重返王城', theme: 'castle',
  pre: 'ch5_pre', post: 'ch5_post', prep: true,
  music: { player: 'final', enemy: 'enemy' },
  rows: ch5Rows(),
  deploy: [[13, 21], [14, 21], [12, 22], [15, 22], [11, 21], [16, 21], [13, 23], [14, 23], [12, 20], [15, 20]],
  objective: { type: 'seize', text: '击败篡位者瓦尔德，由艾尔文占领王座', lose: '艾尔文阵亡', seize: [13, 1] },
  villages: {},
  chests: { '2,1': { item: 'killer_sword' }, '4,1': { item: 'starlight' }, '6,1': { item: 'silver_lance' } },
  units: [
    { boss: 'valder', x: 13, y: 1, tag: 'final', ai: { mode: 'guard' } },
    { cls: 'general', lv: 8, x: 12, y: 3, items: ['steel_lance'], ai: { mode: 'hold', leash: 2 } },
    { cls: 'general', lv: 8, x: 15, y: 3, items: ['hammer'], ai: { mode: 'hold', leash: 2 }, diff: ['normal', 'hard'] },
    { cls: 'darkmage', lv: 8, x: 11, y: 2, items: ['dark'], ai: { mode: 'hold', range: 3 } },
    { cls: 'priest', lv: 8, x: 16, y: 2, items: ['mend_staff'], ai: { mode: 'support' } },
    // 大厅
    { cls: 'knight', lv: 7, x: 13, y: 7, items: ['iron_lance'], ai: { mode: 'hold', range: 3 } },
    { cls: 'knight', lv: 7, x: 14, y: 7, items: ['javelin'], ai: { mode: 'hold', range: 3 } },
    { cls: 'mage', lv: 7, x: 9, y: 6, items: ['thunder'], ai: { mode: 'hold', range: 4 } },
    { cls: 'archer', lv: 7, x: 18, y: 6, items: ['steel_bow'], ai: { mode: 'hold', range: 4 } },
    { cls: 'mercenary', lv: 7, x: 6, y: 7, items: ['steel_sword'], ai: { mode: 'hold', range: 4 } },
    { cls: 'fighter', lv: 7, x: 21, y: 7, items: ['steel_axe'], ai: { mode: 'hold', range: 4 } },
    { cls: 'soldier', lv: 6, x: 4, y: 3, items: ['iron_lance', 'chest_key'], drop: true, ai: { mode: 'hold', range: 2 } },
    { cls: 'darkmage', lv: 7, x: 23, y: 2, items: ['dark'], ai: { mode: 'hold', range: 3 }, diff: ['normal', 'hard'] },
    // 庭院
    { cls: 'soldier', lv: 6, x: 12, y: 12, items: ['iron_lance'] },
    { cls: 'soldier', lv: 6, x: 15, y: 12, items: ['javelin'] },
    { cls: 'cavalier', lv: 6, x: 9, y: 12, items: ['iron_lance'] },
    { cls: 'cavalier', lv: 6, x: 18, y: 12, items: ['iron_sword'], diff: ['normal', 'hard'] },
    { cls: 'archer', lv: 6, x: 2, y: 13, items: ['iron_bow'], ai: { mode: 'hold', range: 4 } },
    { cls: 'archer', lv: 6, x: 25, y: 13, items: ['iron_bow'], ai: { mode: 'hold', range: 4 } },
    { cls: 'wyvern', lv: 7, x: 6, y: 11, items: ['iron_axe'] },
    { cls: 'wyvern', lv: 7, x: 21, y: 11, items: ['iron_lance'], diff: ['normal', 'hard'] },
    { cls: 'fighter', lv: 6, x: 13, y: 16, items: ['iron_axe'] },
    { cls: 'mage', lv: 7, x: 11, y: 10, items: ['fire'], diff: ['hard'] },
    { cls: 'knight', lv: 8, x: 16, y: 10, items: ['steel_lance'], diff: ['hard'] },
  ],
  reinforcements: [
    { turn: 4, warn: 'ch5_reinf_warn', units: [
      { cls: 'soldier', lv: 7, x: 26, y: 1, items: ['steel_lance'] },
      { cls: 'mercenary', lv: 7, x: 20, y: 1, items: ['iron_sword'] },
    ] },
    { turn: 6, warn: 'ch5_reinf_warn', units: [
      { cls: 'fighter', lv: 7, x: 1, y: 7, items: ['steel_axe'] },
      { cls: 'darkmage', lv: 7, x: 1, y: 6, items: ['dark'], diff: ['normal', 'hard'] },
    ] },
    { turn: 8, warn: 'ch5_reinf_warn', units: [
      { cls: 'wyvern', lv: 8, x: 26, y: 1, items: ['steel_axe'] },
      { cls: 'knight', lv: 8, x: 20, y: 1, items: ['steel_lance'] },
    ], diff: ['normal', 'hard'] },
  ],
  events: [
    { id: 'start', on: 'start', script: 'ch5_start' },
    { id: 'boss_elwin', on: 'combat', unit: 'valder', with: 'elwin', script: 'ch5_boss_elwin' },
    { id: 'boss_glenn', on: 'combat', unit: 'valder', with: 'glenn', script: 'ch5_boss_glenn' },
    { id: 'boss_vera', on: 'combat', unit: 'valder', with: 'vera', script: 'ch5_boss_vera' },
    { id: 'boss_doran', on: 'combat', unit: 'valder', with: 'doran', script: 'ch5_boss_doran' },
    { id: 'boss_sid', on: 'combat', unit: 'valder', with: 'sid', script: 'ch5_boss_sid' },
    { id: 'boss', on: 'combat', unit: 'valder', script: 'ch5_boss' },
    { id: 'boss_death', on: 'death', unit: 'valder', script: 'ch5_boss_defeated' },
  ],
  shop: ['steel_sword', 'killer_sword', 'steel_lance', 'javelin', 'horseslayer', 'steel_axe', 'hammer', 'steel_bow', 'longbow', 'thunder', 'mend_staff', 'physic_staff', 'vulnerary', 'elixir', 'door_key', 'chest_key'],
};

export const CHAPTERS = [CH1, CH2, CH3, CH4, CH5];
export function chapterById(id) { return CHAPTERS.find((c) => c.id === id); }
