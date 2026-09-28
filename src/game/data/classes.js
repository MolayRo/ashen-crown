// 职业表
// base：该职业 1 级通用基础值（敌军按等级自动成长时使用）
// growth：职业成长率（%）；角色升级时 = 职业成长 + 个人修正
// caps：职业能力上限；favored：职业专长（加点费用 1，其余 2）
// traits：职业特长（在 rules.js 中实现）
export const STATS = ['hp', 'str', 'mag', 'skl', 'spd', 'lck', 'def', 'res'];
export const STAT_NAMES = { hp: 'HP', str: '力量', mag: '魔力', skl: '技巧', spd: '速度', lck: '幸运', def: '防御', res: '魔防', mov: '移动' };

export const TRAITS = {
  leader:   { name: '统率', desc: '周围 2 格内的友军命中 +10、回避 +5。只有领主能占领王座。' },
  charge:   { name: '冲锋', desc: '本回合移动 4 格以上再发动攻击时，攻击力 +3。' },
  forest:   { name: '林行', desc: '森林中的移动消耗视为 1，在森林中命中 +10。' },
  prayer:   { name: '祝祷', desc: '用杖治疗时额外回复 魔力÷2 点 HP。' },
  bulwark:  { name: '坚壁', desc: '不会受到必杀。受到的伤害 -1。' },
  lockpick: { name: '开锁', desc: '无需钥匙即可开启宝箱与门；回避 +10。' },
  scholar:  { name: '魔导', desc: '魔法命中 +10，必杀 +5。' },
  sky:      { name: '凌空', desc: '飞越山地与水面，但惧怕弓箭（受到弓的特效伤害）。' },
  armored:  { name: '重甲', desc: '移动缓慢，受到破甲武器的特效伤害。' },
  mounted:  { name: '骑乘', desc: '受到斩马武器的特效伤害。' },
  noncombat:{ name: '平民', desc: '无法攻击，需要保护。' },
};

export const CLASSES = {
  lord: {
    name: '领主', moveType: 'foot', mov: 5, weapons: ['sword'], model: 'lord',
    base: { hp: 18, str: 5, mag: 1, skl: 6, spd: 7, lck: 5, def: 4, res: 2 },
    growth: { hp: 70, str: 40, mag: 5, skl: 45, spd: 45, lck: 40, def: 25, res: 20 },
    caps: { hp: 60, str: 20, mag: 12, skl: 22, spd: 22, lck: 25, def: 18, res: 16 },
    favored: ['str', 'skl', 'spd', 'lck'], traits: ['leader'],
    rec: ['spd', 'str', 'skl', 'def', 'hp'],
    desc: '王族的继承人。攻守均衡，是整支军队的核心。',
  },
  cavalier: {
    name: '骑士', moveType: 'horse', mov: 7, weapons: ['lance', 'sword'], model: 'cavalier',
    base: { hp: 20, str: 5, mag: 0, skl: 4, spd: 5, lck: 1, def: 5, res: 0 },
    growth: { hp: 70, str: 40, mag: 0, skl: 35, spd: 35, lck: 30, def: 30, res: 15 },
    caps: { hp: 60, str: 20, mag: 8, skl: 20, spd: 18, lck: 20, def: 20, res: 12 },
    favored: ['hp', 'str', 'def', 'skl'], traits: ['charge', 'mounted'],
    rec: ['str', 'def', 'spd', 'hp'],
    desc: '骑马作战的骑士。移动力高，能用枪与剑。',
  },
  hunter: {
    name: '猎人', moveType: 'foot', mov: 5, weapons: ['bow'], model: 'hunter',
    base: { hp: 18, str: 5, mag: 0, skl: 6, spd: 5, lck: 2, def: 3, res: 1 },
    growth: { hp: 60, str: 40, mag: 0, skl: 50, spd: 40, lck: 35, def: 20, res: 15 },
    caps: { hp: 55, str: 18, mag: 8, skl: 24, spd: 20, lck: 22, def: 15, res: 12 },
    favored: ['str', 'skl', 'spd'], traits: ['forest'],
    rec: ['str', 'skl', 'spd', 'hp'],
    desc: '山林里的射手。只能远程攻击，对飞行单位有特效。',
  },
  cleric: {
    name: '修女', moveType: 'foot', mov: 5, weapons: ['staff'], model: 'cleric',
    base: { hp: 16, str: 0, mag: 4, skl: 3, spd: 5, lck: 6, def: 1, res: 6 },
    growth: { hp: 50, str: 5, mag: 50, skl: 35, spd: 40, lck: 50, def: 10, res: 50 },
    caps: { hp: 50, str: 8, mag: 22, skl: 18, spd: 20, lck: 25, def: 12, res: 24 },
    favored: ['mag', 'spd', 'lck', 'res'], traits: ['prayer'],
    rec: ['mag', 'spd', 'hp', 'res'],
    desc: '侍奉神明的修女。无法攻击，但能用杖治疗同伴。',
  },
  knight: {
    name: '重甲骑士', moveType: 'armor', mov: 4, weapons: ['lance'], model: 'knight',
    base: { hp: 21, str: 6, mag: 0, skl: 3, spd: 1, lck: 0, def: 9, res: 0 },
    growth: { hp: 80, str: 45, mag: 0, skl: 30, spd: 15, lck: 25, def: 45, res: 10 },
    caps: { hp: 65, str: 22, mag: 6, skl: 18, spd: 12, lck: 18, def: 28, res: 12 },
    favored: ['hp', 'str', 'def'], traits: ['bulwark', 'armored'],
    rec: ['def', 'str', 'hp', 'spd'],
    desc: '身披重甲的步兵。防御极高、行动迟缓，惧怕魔法。',
  },
  thief: {
    name: '盗贼', moveType: 'foot', mov: 6, weapons: ['sword'], model: 'thief',
    base: { hp: 16, str: 3, mag: 0, skl: 5, spd: 8, lck: 3, def: 2, res: 1 },
    growth: { hp: 55, str: 30, mag: 5, skl: 50, spd: 60, lck: 45, def: 15, res: 20 },
    caps: { hp: 50, str: 16, mag: 8, skl: 24, spd: 25, lck: 25, def: 14, res: 14 },
    favored: ['skl', 'spd', 'lck'], traits: ['lockpick'],
    rec: ['spd', 'str', 'skl', 'lck'],
    desc: '身手敏捷的盗贼。无需钥匙就能打开宝箱与门。',
  },
  mage: {
    name: '法师', moveType: 'foot', mov: 5, weapons: ['tome'], model: 'mage',
    base: { hp: 16, str: 0, mag: 5, skl: 3, spd: 4, lck: 1, def: 1, res: 4 },
    growth: { hp: 50, str: 0, mag: 55, skl: 40, spd: 40, lck: 30, def: 10, res: 40 },
    caps: { hp: 50, str: 8, mag: 24, skl: 20, spd: 20, lck: 20, def: 12, res: 22 },
    favored: ['mag', 'skl', 'spd', 'res'], traits: ['scholar'],
    rec: ['mag', 'spd', 'skl', 'hp'],
    desc: '使用魔法书的术士。攻击对手的魔防，擅长对付重甲。',
  },
  pegasus: {
    name: '天马骑士', moveType: 'fly', mov: 7, weapons: ['lance'], model: 'pegasus',
    base: { hp: 16, str: 4, mag: 1, skl: 6, spd: 8, lck: 3, def: 3, res: 5 },
    growth: { hp: 55, str: 35, mag: 10, skl: 45, spd: 55, lck: 45, def: 15, res: 40 },
    caps: { hp: 52, str: 18, mag: 12, skl: 22, spd: 24, lck: 24, def: 14, res: 22 },
    favored: ['skl', 'spd', 'res', 'lck'], traits: ['sky'],
    rec: ['spd', 'str', 'skl', 'def'],
    desc: '骑乘天马的骑士。能飞越任何地形，但惧怕弓箭。',
  },
  // ---- 敌方职业 ----
  soldier: {
    name: '士兵', moveType: 'foot', mov: 5, weapons: ['lance'], model: 'soldier',
    base: { hp: 20, str: 5, mag: 0, skl: 3, spd: 3, lck: 1, def: 4, res: 0 },
    growth: { hp: 70, str: 35, mag: 0, skl: 30, spd: 25, lck: 20, def: 25, res: 10 },
    caps: { hp: 60, str: 20, mag: 8, skl: 20, spd: 20, lck: 20, def: 20, res: 12 },
    favored: ['str', 'def'], traits: [], desc: '手持长枪的步兵。',
  },
  fighter: {
    name: '战士', moveType: 'foot', mov: 5, weapons: ['axe'], model: 'fighter',
    base: { hp: 22, str: 6, mag: 0, skl: 2, spd: 4, lck: 0, def: 3, res: 0 },
    growth: { hp: 80, str: 50, mag: 0, skl: 30, spd: 30, lck: 20, def: 15, res: 5 },
    caps: { hp: 60, str: 22, mag: 6, skl: 18, spd: 18, lck: 18, def: 16, res: 10 },
    favored: ['hp', 'str'], traits: [], desc: '挥舞大斧的战士。力量大，命中低。',
  },
  mercenary: {
    name: '佣兵', moveType: 'foot', mov: 5, weapons: ['sword'], model: 'mercenary',
    base: { hp: 19, str: 5, mag: 0, skl: 7, spd: 7, lck: 2, def: 4, res: 0 },
    growth: { hp: 70, str: 40, mag: 0, skl: 45, spd: 40, lck: 25, def: 20, res: 15 },
    caps: { hp: 60, str: 20, mag: 8, skl: 22, spd: 22, lck: 20, def: 18, res: 14 },
    favored: ['skl', 'spd'], traits: [], desc: '以剑为生的佣兵。',
  },
  archer: {
    name: '弓兵', moveType: 'foot', mov: 5, weapons: ['bow'], model: 'archer',
    base: { hp: 18, str: 5, mag: 0, skl: 5, spd: 4, lck: 1, def: 3, res: 0 },
    growth: { hp: 60, str: 40, mag: 0, skl: 45, spd: 35, lck: 25, def: 15, res: 15 },
    caps: { hp: 55, str: 18, mag: 8, skl: 22, spd: 20, lck: 20, def: 15, res: 12 },
    favored: ['skl'], traits: [], desc: '远程射击的弓兵。无法反击贴身的敌人。',
  },
  darkmage: {
    name: '暗术士', moveType: 'foot', mov: 5, weapons: ['tome'], model: 'mage',
    base: { hp: 17, str: 0, mag: 5, skl: 3, spd: 3, lck: 0, def: 2, res: 5 },
    growth: { hp: 60, str: 0, mag: 50, skl: 35, spd: 30, lck: 20, def: 15, res: 40 },
    caps: { hp: 55, str: 8, mag: 22, skl: 18, spd: 18, lck: 18, def: 14, res: 22 },
    favored: ['mag', 'res'], traits: [], desc: '操纵暗魔法的术士。',
  },
  priest: {
    name: '神官', moveType: 'foot', mov: 5, weapons: ['staff'], model: 'cleric',
    base: { hp: 16, str: 0, mag: 4, skl: 2, spd: 3, lck: 2, def: 1, res: 5 },
    growth: { hp: 50, str: 0, mag: 45, skl: 30, spd: 30, lck: 35, def: 10, res: 45 },
    caps: { hp: 50, str: 8, mag: 20, skl: 18, spd: 18, lck: 22, def: 12, res: 22 },
    favored: ['mag'], traits: [], desc: '为敌军疗伤的神官。',
  },
  wyvern: {
    name: '飞龙骑士', moveType: 'fly', mov: 7, weapons: ['axe', 'lance'], model: 'wyvern',
    base: { hp: 24, str: 7, mag: 0, skl: 4, spd: 5, lck: 0, def: 8, res: 0 },
    growth: { hp: 80, str: 45, mag: 0, skl: 35, spd: 30, lck: 20, def: 35, res: 5 },
    caps: { hp: 60, str: 22, mag: 6, skl: 20, spd: 18, lck: 18, def: 22, res: 10 },
    favored: ['str', 'def'], traits: ['sky'], desc: '驾驭飞龙的北方骑士。防御坚固，惧怕弓箭。',
  },
  general: {
    name: '将军', moveType: 'armor', mov: 4, weapons: ['axe', 'lance'], model: 'general',
    base: { hp: 28, str: 9, mag: 0, skl: 5, spd: 3, lck: 2, def: 12, res: 3 },
    growth: { hp: 85, str: 45, mag: 0, skl: 30, spd: 15, lck: 20, def: 40, res: 15 },
    caps: { hp: 65, str: 24, mag: 8, skl: 20, spd: 14, lck: 20, def: 30, res: 15 },
    favored: ['def'], traits: ['bulwark', 'armored'], desc: '身经百战的重甲将军。',
  },
  usurper: {
    name: '篡位者', moveType: 'foot', mov: 5, weapons: ['sword', 'lance'], model: 'usurper',
    base: { hp: 40, str: 14, mag: 4, skl: 12, spd: 9, lck: 8, def: 12, res: 8 },
    growth: { hp: 80, str: 50, mag: 10, skl: 45, spd: 35, lck: 30, def: 40, res: 30 },
    caps: { hp: 70, str: 26, mag: 14, skl: 26, spd: 22, lck: 24, def: 26, res: 22 },
    favored: [], traits: [], desc: '弑君篡位的黑鹰公爵。',
  },
  civilian: {
    name: '村长', moveType: 'foot', mov: 5, weapons: [], model: 'civilian',
    base: { hp: 18, str: 0, mag: 0, skl: 0, spd: 3, lck: 6, def: 2, res: 3 },
    growth: { hp: 0, str: 0, mag: 0, skl: 0, spd: 0, lck: 0, def: 0, res: 0 },
    caps: { hp: 30, str: 5, mag: 5, skl: 5, spd: 10, lck: 20, def: 10, res: 10 },
    favored: [], traits: ['noncombat'], desc: '石溪村的村长。',
  },
};

export function hasTrait(unit, t) {
  const c = CLASSES[unit.cls];
  return !!(c && c.traits.includes(t));
}

// 敌方单位的职业名显示（例如敌方骑兵叫“骑兵”）
export const ENEMY_CLASS_NAMES = { cavalier: '骑兵', knight: '重甲兵', pegasus: '天马骑士', mage: '魔道士', cleric: '神官' };
