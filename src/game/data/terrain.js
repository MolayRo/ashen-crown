// 地形表：防御、回避、每回合回复、不同移动类型的消耗（缺省 = 无法通过）
// 移动类型：foot 步行、armor 重甲、horse 骑马、fly 飞行
const ALL1 = { foot: 1, armor: 1, horse: 1, fly: 1 };

export const TERRAIN = {
  '.': { name: '平原', def: 0, avo: 0, cost: ALL1 },
  ',': { name: '草地', def: 0, avo: 0, cost: ALL1 },
  '"': { name: '道路', def: 0, avo: 0, cost: ALL1 },
  'T': { name: '森林', def: 1, avo: 20, cost: { foot: 2, armor: 2, horse: 3, fly: 1 }, forest: true },
  'h': { name: '丘陵', def: 1, avo: 10, cost: { foot: 2, armor: 3, horse: 3, fly: 1 } },
  '^': { name: '山地', def: 2, avo: 30, cost: { foot: 4, fly: 1 } },
  'A': { name: '高山', def: 3, avo: 40, cost: { fly: 1 } },
  '~': { name: '河流', def: 0, avo: 0, cost: { fly: 1 } },
  '_': { name: '浅滩', def: 0, avo: -10, cost: { foot: 3, horse: 4, fly: 1 } },
  '=': { name: '桥', def: 0, avo: 0, cost: ALL1 },
  'B': { name: '断桥', def: 0, avo: 0, cost: { fly: 1 } },
  '#': { name: '墙壁', def: 0, avo: 0, cost: {} },
  '+': { name: '地板', def: 0, avo: 0, cost: ALL1 },
  'c': { name: '地毯', def: 0, avo: 0, cost: ALL1 },
  '|': { name: '石柱', def: 1, avo: 20, cost: { foot: 2, armor: 2, horse: 3, fly: 2 } },
  'D': { name: '门', def: 0, avo: 0, cost: {}, door: true },
  'C': { name: '宝箱', def: 0, avo: 0, cost: ALL1, chest: true },
  'V': { name: '村庄', def: 0, avo: 10, cost: ALL1, village: true },
  'H': { name: '民居', def: 0, avo: 0, cost: { fly: 1 } },
  'F': { name: '要塞', def: 2, avo: 20, heal: 20, cost: { foot: 2, armor: 2, horse: 2, fly: 2 } },
  'G': { name: '城门', def: 3, avo: 20, heal: 10, cost: ALL1 },
  'K': { name: '王座', def: 3, avo: 20, heal: 10, cost: ALL1 },
  'S': { name: '楼梯', def: 0, avo: 0, cost: ALL1 },
  'x': { name: '悬崖', def: 0, avo: 0, cost: { fly: 1 } },
  'r': { name: '废墟', def: 0, avo: 10, cost: { foot: 2, armor: 2, horse: 3, fly: 1 } },
  'f': { name: '栅栏', def: 0, avo: 0, cost: { fly: 1 } },
  'a': { name: '祭坛', def: 1, avo: 10, cost: ALL1 },
  'P': { name: '牢房', def: 0, avo: 0, cost: ALL1 },
};

// 雪地主题：雪原拖慢重甲和骑兵
const SNOW = {
  '.': { name: '雪原', def: 0, avo: 0, cost: { foot: 1, armor: 2, horse: 2, fly: 1 } },
  ',': { name: '雪原', def: 0, avo: 0, cost: { foot: 1, armor: 2, horse: 2, fly: 1 } },
  'T': { name: '雪林', def: 1, avo: 20, cost: { foot: 2, armor: 3, horse: 3, fly: 1 }, forest: true },
  '~': { name: '冰河', def: 0, avo: 0, cost: { fly: 1 } },
};

export function terrainOf(ch, theme) {
  if (theme === 'snow' && SNOW[ch]) return SNOW[ch];
  return TERRAIN[ch] || TERRAIN['.'];
}

// 门打开、村庄焚毁后地形字符的变化
export const OPENED = { D: '+', C: 'C', V: 'r' };
