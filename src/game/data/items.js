// 武器与道具
// 武器：type 剑sword 枪lance 斧axe 弓bow 魔法tome 杖staff
// mt 威力、hit 命中、crit 必杀、wt 重量、rng [最小, 最大] 射程（杖的 'mag' 表示 魔力÷2）
// eff 特效：fly 飞行、armor 重甲、horse 骑马（威力×3）
// lock：专属角色
export const WEAPON_TYPES = { sword: '剑', lance: '枪', axe: '斧', bow: '弓', tome: '魔法', staff: '杖' };

export const ITEMS = {
  // ---- 剑 ----
  iron_sword:   { name: '铁剑', type: 'sword', mt: 5, hit: 90, crit: 0, wt: 5, rng: [1, 1], price: 460, icon: 'sword_iron', desc: '铁制的剑。轻便易用。' },
  steel_sword:  { name: '钢剑', type: 'sword', mt: 8, hit: 75, crit: 0, wt: 10, rng: [1, 1], price: 800, icon: 'sword_steel', desc: '钢制的剑。威力较高但沉重。' },
  killer_sword: { name: '杀手剑', type: 'sword', mt: 7, hit: 75, crit: 30, wt: 7, rng: [1, 1], price: 1300, icon: 'sword_killer', desc: '容易击中要害的剑。必杀率高。' },
  silver_sword: { name: '银剑', type: 'sword', mt: 12, hit: 80, crit: 0, wt: 8, rng: [1, 1], price: 1800, icon: 'sword_silver', desc: '银打造的名剑。' },
  rapier:       { name: '王家细剑', type: 'sword', mt: 6, hit: 95, crit: 10, wt: 3, rng: [1, 1], eff: ['armor', 'horse'], lock: 'elwin', price: 0, icon: 'sword_rapier', desc: '白鹿王家的细剑。对重甲与骑兵有特效。艾尔文专用。' },
  holy_sword:   { name: '白鹿圣剑', type: 'sword', mt: 13, hit: 90, crit: 10, wt: 6, rng: [1, 1], eff: ['armor', 'horse'], lock: 'elwin', bonus: { def: 3, res: 3 }, price: 0, icon: 'sword_holy', desc: '开国之王的佩剑。装备时防御、魔防 +3。艾尔文专用。' },
  // ---- 枪 ----
  iron_lance:   { name: '铁枪', type: 'lance', mt: 7, hit: 80, crit: 0, wt: 8, rng: [1, 1], price: 560, icon: 'lance_iron', desc: '铁制的长枪。' },
  steel_lance:  { name: '钢枪', type: 'lance', mt: 10, hit: 70, crit: 0, wt: 13, rng: [1, 1], price: 900, icon: 'lance_steel', desc: '钢制的长枪。威力较高但沉重。' },
  javelin:      { name: '标枪', type: 'lance', mt: 6, hit: 65, crit: 0, wt: 11, rng: [1, 2], price: 700, icon: 'lance_javelin', desc: '可以投掷的短枪。射程 1~2。' },
  horseslayer:  { name: '斩马枪', type: 'lance', mt: 7, hit: 70, crit: 0, wt: 13, rng: [1, 1], eff: ['horse'], price: 1100, icon: 'lance_horseslayer', desc: '对骑兵有特效的长枪。' },
  silver_lance: { name: '银枪', type: 'lance', mt: 14, hit: 75, crit: 0, wt: 10, rng: [1, 1], price: 2000, icon: 'lance_silver', desc: '银打造的名枪。' },
  // ---- 斧 ----
  iron_axe:     { name: '铁斧', type: 'axe', mt: 8, hit: 75, crit: 0, wt: 10, rng: [1, 1], price: 400, icon: 'axe_iron', desc: '铁制的斧头。' },
  steel_axe:    { name: '钢斧', type: 'axe', mt: 11, hit: 65, crit: 0, wt: 15, rng: [1, 1], price: 700, icon: 'axe_steel', desc: '钢制的斧头。' },
  hand_axe:     { name: '手斧', type: 'axe', mt: 7, hit: 60, crit: 0, wt: 12, rng: [1, 2], price: 650, icon: 'axe_hand', desc: '可以投掷的斧头。射程 1~2。' },
  hammer:       { name: '破甲锤', type: 'axe', mt: 10, hit: 55, crit: 0, wt: 15, rng: [1, 1], eff: ['armor'], price: 900, icon: 'axe_hammer', desc: '对重甲有特效的战锤。' },
  // ---- 弓 ----
  iron_bow:     { name: '铁弓', type: 'bow', mt: 6, hit: 85, crit: 0, wt: 5, rng: [2, 2], eff: ['fly'], price: 540, icon: 'bow_iron', desc: '铁制的弓。对飞行单位有特效。' },
  steel_bow:    { name: '钢弓', type: 'bow', mt: 9, hit: 70, crit: 0, wt: 9, rng: [2, 2], eff: ['fly'], price: 900, icon: 'bow_steel', desc: '钢制的弓。对飞行单位有特效。' },
  longbow:      { name: '长弓', type: 'bow', mt: 5, hit: 65, crit: 0, wt: 10, rng: [2, 3], eff: ['fly'], price: 1500, icon: 'bow_long', desc: '射程 2~3 的长弓。对飞行单位有特效。' },
  // ---- 魔法 ----
  fire:         { name: '火焰', type: 'tome', magic: true, mt: 5, hit: 90, crit: 0, wt: 4, rng: [1, 2], price: 560, icon: 'tome_fire', spell: 'fire', desc: '召唤火焰的魔法书。射程 1~2。' },
  thunder:      { name: '雷霆', type: 'tome', magic: true, mt: 8, hit: 80, crit: 5, wt: 6, rng: [1, 2], price: 900, icon: 'tome_thunder', spell: 'thunder', desc: '召唤落雷的魔法书。射程 1~2。' },
  dark:         { name: '暗之书', type: 'tome', magic: true, mt: 7, hit: 75, crit: 0, wt: 7, rng: [1, 2], price: 800, icon: 'tome_dark', spell: 'dark', desc: '记载暗魔法的禁书。射程 1~2。' },
  starlight:    { name: '星辉', type: 'tome', magic: true, mt: 11, hit: 85, crit: 5, wt: 5, rng: [1, 2], lock: 'mira', price: 0, icon: 'tome_light', spell: 'light', desc: '宫廷魔导师的秘传魔法。米拉专用。' },
  // ---- 杖 ----
  heal_staff:   { name: '治愈杖', type: 'staff', heal: 10, hit: 100, wt: 0, rng: [1, 1], price: 600, icon: 'staff_heal', desc: '为相邻的同伴回复 10 + 魔力 的 HP。' },
  mend_staff:   { name: '痊愈杖', type: 'staff', heal: 20, hit: 100, wt: 0, rng: [1, 1], price: 1000, icon: 'staff_mend', desc: '为相邻的同伴回复 20 + 魔力 的 HP。' },
  physic_staff: { name: '远疗杖', type: 'staff', heal: 10, hit: 100, wt: 0, rng: [1, 'mag'], price: 1800, icon: 'staff_physic', desc: '远距离治疗。射程 1~(魔力÷2)，回复 10 + 魔力。' },
  // ---- 道具 ----
  vulnerary:    { name: '伤药', type: 'item', uses: 3, heal: 10, price: 300, icon: 'vulnerary', desc: '回复 10 点 HP。可用 3 次。' },
  elixir:       { name: '灵药', type: 'item', uses: 2, heal: 99, price: 1500, icon: 'elixir', desc: '完全回复 HP。可用 2 次。' },
  door_key:     { name: '门钥匙', type: 'item', uses: 1, key: 'door', price: 50, icon: 'door_key', desc: '打开一扇门。' },
  chest_key:    { name: '宝箱钥匙', type: 'item', uses: 1, key: 'chest', price: 150, icon: 'chest_key', desc: '打开一个宝箱。' },
  seed_str:     { name: '力量之种', type: 'item', uses: 1, boost: { str: 2 }, price: 0, icon: 'seed_str', desc: '力量永久 +2。' },
  seed_mag:     { name: '魔力之种', type: 'item', uses: 1, boost: { mag: 2 }, price: 0, icon: 'seed_mag', desc: '魔力永久 +2。' },
  book_skl:     { name: '秘传之书', type: 'item', uses: 1, boost: { skl: 2 }, price: 0, icon: 'book_skl', desc: '技巧永久 +2。' },
  feather_spd:  { name: '疾风之羽', type: 'item', uses: 1, boost: { spd: 2 }, price: 0, icon: 'feather_spd', desc: '速度永久 +2。' },
  clover_lck:   { name: '幸运草', type: 'item', uses: 1, boost: { lck: 2 }, price: 0, icon: 'clover_lck', desc: '幸运永久 +2。' },
  shield_def:   { name: '守护之盾', type: 'item', uses: 1, boost: { def: 2 }, price: 0, icon: 'shield_def', desc: '防御永久 +2。' },
  talisman_res: { name: '护符', type: 'item', uses: 1, boost: { res: 2 }, price: 0, icon: 'talisman_res', desc: '魔防永久 +2。' },
  robe_hp:      { name: '天使之衣', type: 'item', uses: 1, boost: { hp: 7 }, price: 0, icon: 'robe_hp', desc: '最大 HP 永久 +7。' },
};

export function itemDef(id) { return ITEMS[id]; }
export function isWeapon(id) {
  const d = ITEMS[id];
  return !!d && d.type !== 'item' && d.type !== 'staff';
}
export function isStaff(id) { const d = ITEMS[id]; return !!d && d.type === 'staff'; }
export function makeItem(id, uses) {
  const d = ITEMS[id];
  if (!d) throw new Error('未知物品 ' + id);
  return { id, uses: uses != null ? uses : (d.uses || 0) };
}
