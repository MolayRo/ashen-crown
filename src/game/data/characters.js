// 可操控角色与剧情人物
// stats：初始能力（含移动力 mov 由职业决定，可被加点提升一次）
// growthMod：个人成长修正（加到职业成长率上）
export const PLAYABLE = ['elwin', 'glenn', 'nora', 'serin', 'doran', 'sid', 'mira', 'vera'];

export const CHARACTERS = {
  elwin: {
    name: '艾尔文', cls: 'lord', lv: 1, portrait: 'elwin', battle: 'elwin', lord: true,
    stats: { hp: 20, str: 6, mag: 1, skl: 6, spd: 8, lck: 7, def: 5, res: 2 },
    growthMod: { hp: 5, lck: 10, spd: 5, res: 5 },
    items: ['rapier', 'vulnerary'],
  },
  glenn: {
    name: '格伦', cls: 'cavalier', lv: 5, portrait: 'glenn', battle: 'glenn',
    stats: { hp: 30, str: 10, mag: 0, skl: 9, spd: 7, lck: 5, def: 10, res: 3 },
    growthMod: { str: -5, skl: -5, spd: -10, def: 5, res: -5 },
    items: ['iron_lance', 'iron_sword'],
  },
  nora: {
    name: '诺拉', cls: 'hunter', lv: 2, portrait: 'nora', battle: 'nora',
    stats: { hp: 19, str: 6, mag: 0, skl: 8, spd: 7, lck: 5, def: 3, res: 1 },
    growthMod: { skl: 10, spd: 5, lck: -5 },
    items: ['iron_bow', 'vulnerary'],
  },
  serin: {
    name: '赛琳', cls: 'cleric', lv: 1, portrait: 'serin', battle: 'serin',
    stats: { hp: 17, str: 1, mag: 5, skl: 5, spd: 6, lck: 8, def: 1, res: 6 },
    growthMod: { mag: 5, res: 10, lck: 5 },
    items: ['heal_staff', 'vulnerary'],
  },
  doran: {
    name: '多兰', cls: 'knight', lv: 4, portrait: 'doran', battle: 'doran',
    stats: { hp: 26, str: 9, mag: 0, skl: 5, spd: 3, lck: 3, def: 12, res: 1 },
    growthMod: { hp: 5, def: 5, spd: 5 },
    items: ['iron_lance', 'javelin'],
  },
  sid: {
    name: '希德', cls: 'thief', lv: 3, portrait: 'sid', battle: 'sid',
    stats: { hp: 18, str: 5, mag: 0, skl: 9, spd: 11, lck: 7, def: 3, res: 2 },
    growthMod: { str: 5, spd: 5, lck: 5 },
    items: ['iron_sword', 'vulnerary'],
  },
  mira: {
    name: '米拉', cls: 'mage', lv: 3, portrait: 'mira', battle: 'mira',
    stats: { hp: 17, str: 1, mag: 8, skl: 7, spd: 7, lck: 5, def: 2, res: 6 },
    growthMod: { mag: 10, spd: 5 },
    items: ['fire', 'vulnerary'],
  },
  vera: {
    name: '薇拉', cls: 'pegasus', lv: 6, portrait: 'vera', battle: 'vera',
    stats: { hp: 22, str: 8, mag: 3, skl: 11, spd: 13, lck: 9, def: 6, res: 9 },
    growthMod: { str: 5, spd: 5, res: 5 },
    items: ['iron_lance', 'javelin'],
  },
};

// 剧情人物显示名（脚本里说话人中文名 → id）
export const SPEAKERS = {
  '艾尔文': 'elwin', '格伦': 'glenn', '诺拉': 'nora', '赛琳': 'serin', '多兰': 'doran', '希德': 'sid', '米拉': 'mira', '薇拉': 'vera',
  '艾德里克王': 'aldric', '国王': 'aldric', '瓦尔德': 'valder', '戈尔德': 'gord', '哈根': 'hagen', '摩根': 'morgan', '格里姆': 'grimm',
  '玛莎': 'martha', '奥斯温': 'oswin', '本笃': 'abbot', '黑鹰士兵': 'soldier', '村民': 'villager',
};

// 每个人物可用的表情
export const EXPRESSIONS = {
  full: ['normal', 'smile', 'angry', 'sad', 'surprise'],
  mid: ['normal', 'smile', 'angry'],
  one: ['normal'],
};
export const PORTRAIT_EXPR = {
  elwin: 'full', glenn: 'full', nora: 'full', serin: 'full', doran: 'full', sid: 'full', mira: 'full', vera: 'full',
  aldric: 'full', valder: 'full',
  gord: 'mid', hagen: 'mid', morgan: 'mid', grimm: 'mid', martha: 'mid', oswin: 'mid', abbot: 'mid',
  soldier: 'one', villager: 'one',
};

// 首领与特殊敌人（固定数值，难度修正另算）
export const BOSSES = {
  gord:   { name: '戈尔德', cls: 'fighter', lv: 6, portrait: 'gord', battle: 'gord',
            stats: { hp: 30, str: 10, mag: 0, skl: 5, spd: 5, lck: 2, def: 5, res: 1 }, items: ['iron_axe', 'hand_axe'] },
  hagen:  { name: '哈根', cls: 'general', lv: 8, portrait: 'hagen', battle: 'hagen',
            stats: { hp: 34, str: 12, mag: 0, skl: 7, spd: 3, lck: 3, def: 14, res: 3 }, items: ['iron_lance', 'javelin'] },
  morgan: { name: '摩根', cls: 'darkmage', lv: 10, portrait: 'morgan', battle: 'morgan',
            stats: { hp: 30, str: 0, mag: 11, skl: 8, spd: 6, lck: 4, def: 4, res: 9 }, items: ['dark', 'elixir'] },
  grimm:  { name: '格里姆', cls: 'wyvern', lv: 12, portrait: 'grimm', battle: 'grimm',
            stats: { hp: 40, str: 15, mag: 0, skl: 9, spd: 8, lck: 5, def: 14, res: 3 }, items: ['steel_axe', 'hand_axe'] },
  valder: { name: '瓦尔德', cls: 'usurper', lv: 15, portrait: 'valder', battle: 'valder',
            stats: { hp: 40, str: 14, mag: 4, skl: 13, spd: 10, lck: 8, def: 9, res: 7 }, items: ['silver_sword', 'javelin'] },
  martha: { name: '玛莎', cls: 'civilian', lv: 1, portrait: 'martha', battle: 'martha',
            stats: { hp: 20, str: 0, mag: 0, skl: 0, spd: 4, lck: 8, def: 3, res: 4 }, items: ['vulnerary'] },
};
