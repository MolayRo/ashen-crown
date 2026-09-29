// 操作说明与规则速查（分页）
import { W, H } from '../core/renderer.js';
import { fill, drawWindow, drawArrow } from '../core/gfx.js';
import { drawText, wrapText, textWidth } from '../core/font.js';
import { audio } from '../core/audio.js';

const PAGES = [
  { title: '基本操作', rows: [
    ['方向键 / WASD', '移动光标、选择菜单'],
    ['Z / 回车 / 空格', '确认、选择单位、推进对白'],
    ['X / Esc / 退格', '取消、返回（剧情中：跳过，会先确认）'],
    ['C / I / 鼠标中键', '查看光标处单位的详细资料'],
    ['Tab / Q', '光标跳到下一个可行动的我方单位'],
    ['R', '显示 / 隐藏敌方全体威胁范围'],
    ['M 或 选择空地', '打开地图菜单（部队、目标、存档、结束回合）'],
    ['E', '结束回合（仍有单位可行动时会确认）'],
    ['Shift / Ctrl / F', '按住时快进对白与动画'],
    ['L 或 滚轮向上', '剧情中回看之前的对白'],
    ['鼠标', '左键 = 确认，右键 = 取消，滚轮 = 翻动列表'],
    ['触摸', '轻点 = 确认，长按 = 取消'],
  ] },
  { title: '回合与行动', rows: [
    ['我方回合', '每个单位移动一次、行动一次（攻击、用杖、交谈、交换、待机等）。'],
    ['撤销移动', '移动后、行动之前按取消可退回原位；移动后交换过物品则不能撤销。'],
    ['敌方回合', '敌人按各自的行为行动：进攻、守点、固守、支援、烧村、抢宝箱。'],
    ['增援', '出现位置提前一回合标出红色“!”；刚出现的增援当回合不会行动。'],
    ['胜利 / 失败', '随时可在地图菜单“目标”中查看。艾尔文阵亡即失败。'],
  ] },
  { title: '战斗规则', rows: [
    ['伤害', '攻击力（力量或魔力 + 武器威力）- 对方防御（魔法看魔防）- 地形防御。'],
    ['命中', '武器命中 + 技巧×2 + 幸运÷2，减去对方回避（攻速×2 + 幸运 + 地形回避）。'],
    ['必杀', '武器必杀 + 技巧÷2 - 对方幸运。必杀造成 3 倍伤害。重甲“坚壁”不会被必杀。'],
    ['追击', '攻速比对方高 4 点以上时攻击两次。攻速 = 速度 - 武器超重（重量超过力量的部分）。'],
    ['反击', '被攻击者的武器射程覆盖距离时才能反击。弓不能反击贴身的敌人，杖不能反击。'],
    ['克制', '剑克斧、斧克枪、枪克剑：优势方威力 +1、命中 +15。'],
    ['特效', '弓对飞行、斩马枪对骑兵、破甲锤对重甲、王家细剑对骑兵与重甲：威力 ×3。'],
  ] },
  { title: '地形', rows: [
    ['森林', '防御 +1、回避 +20；步行消耗 2，骑马 3。'],
    ['丘陵', '防御 +1、回避 +10；移动消耗较大。'],
    ['山地', '防御 +2、回避 +30；只有步行（消耗 4）与飞行能进入。'],
    ['要塞', '防御 +2、回避 +20，每回合开始回复 20% HP。'],
    ['王座 / 城门', '防御 +3、回避 +20，每回合开始回复 10% HP。'],
    ['祭坛', '防御 +1、回避 +10。'],
    ['河流 / 高山 / 悬崖', '只有飞行单位能通过。浅滩可以涉水，但回避 -10。'],
    ['雪原', '第四章：重甲与骑马在雪地中行动迟缓。'],
    ['门 / 宝箱 / 村庄', '门与宝箱需要钥匙或盗贼；在村庄入口“访问”可获得道具，敌人会烧毁村庄。'],
  ] },
  { title: '成长与加点', rows: [
    ['经验', '攻击、击败敌人、用杖治疗都能获得经验，满 100 升级。击败首领经验更多。'],
    ['成长率', '升级时按“职业成长 + 个人成长”随机提升各项能力，并显示结果。'],
    ['潜能点', '每次升级额外获得 2 点，可在“部队 → 角色 → 加点”中自由分配。'],
    ['费用', '职业专长能力 1 点 = +1，其他能力 2 点 = +1；HP 1 点 = +2。'],
    ['上限', '每项能力通过加点最多 +5（HP 最多 +10），不能超过职业上限。'],
    ['移动力', '每人仅能提升 1 次，消耗 6 点。'],
    ['推荐', '加点界面按“推荐”会按职业定位自动分配，可以确认前再修改。'],
  ] },
  { title: '难度与模式', rows: [
    ['简单', '敌人较弱、数量较少，资源更充足。'],
    ['普通', '标准体验。'],
    ['困难', '敌人更强更多、更会集火，资源更少。'],
    ['修改难度', '可在设置里修改，从下一章开始生效。'],
    ['休闲模式', '伙伴倒下只会撤退，章节结束后归队。'],
    ['经典模式', '伙伴倒下即永久阵亡，剧情会随之变化。'],
    ['存档', '3 个存档位，每章开战前自动存档；我方回合也可在地图上随时存档。'],
  ] },
];

const TOP = 30;          // 第一行的 y
const BOTTOM = H - 20;   // 文字不能越过这里（下面是“翻页 / 返回”提示）

// 排版：键名列宽按本页最宽的键名定；一页放不下就自动拆成几屏（标题后标 1/2、2/2）
function layoutScreens() {
  const screens = [];
  for (const p of PAGES) {
    const keyW = Math.min(120, Math.max(...p.rows.map((r) => textWidth(r[0]))) + 10);
    const rows = p.rows.map(([k, v]) => {
      const keyLines = textWidth(k) > keyW - 6 ? wrapText(k, keyW - 6) : [k];
      const lines = wrapText(v, W - 40 - keyW);
      return { keyLines, lines, h: Math.max(keyLines.length, lines.length, 1) * 12 + 2 };
    });
    const parts = [];
    let cur = [];
    let y = TOP;
    for (const r of rows) {
      if (cur.length && y + r.h - 2 > BOTTOM) { parts.push(cur); cur = []; y = TOP; }
      cur.push(r);
      y += r.h;
    }
    if (cur.length) parts.push(cur);
    parts.forEach((rs, i) => screens.push({ title: parts.length > 1 ? `${p.title}（${i + 1}/${parts.length}）` : p.title, keyW, rows: rs }));
  }
  return screens;
}

export class HelpScene {
  constructor() { this.overlay = true; this.page = 0; this.screens = layoutScreens(); }
  update(game) {
    const input = game.input;
    const n = this.screens.length;
    if (input.repeat('left') || input.repeat('up')) { this.page = (this.page - 1 + n) % n; audio.sfx('page'); }
    if (input.repeat('right') || input.repeat('down') || input.confirm()) { this.page = (this.page + 1) % n; audio.sfx('page'); }
    if (input.click()) {
      if (input.mouse.x < W / 2) this.page = (this.page - 1 + n) % n; else this.page = (this.page + 1) % n;
      audio.sfx('page');
    }
    if (input.mouse.wheel) this.page = (this.page + Math.sign(input.mouse.wheel) + n) % n;
    if (input.cancel()) { audio.sfx('cancel'); game.pop(); }
  }
  draw(ctx, game) {
    ctx.globalAlpha = 0.75;
    fill(ctx, 0, 0, W, H, '#05040a');
    ctx.globalAlpha = 1;
    drawWindow(ctx, 6, 4, W - 12, H - 8, 'menu');
    const sc = this.screens[this.page];
    drawText(ctx, `操作说明 · ${sc.title}`, 16, 10, '#f8e0a0', { shadow: '#000' });
    drawText(ctx, `${this.page + 1}/${this.screens.length}`, W - 16, 10, '#b8c0e0', { align: 'right', shadow: '#000' });
    fill(ctx, 14, 25, W - 28, 1, 'rgba(255,240,200,0.3)');
    let y = TOP;
    for (const r of sc.rows) {
      r.keyLines.forEach((l, i) => drawText(ctx, l, 18, y + i * 12, '#f8d878', { shadow: '#000' }));
      r.lines.forEach((l, i) => drawText(ctx, l, 18 + sc.keyW, y + i * 12, '#f0ece0', { shadow: '#000' }));
      y += r.h;
    }
    drawArrow(ctx, 12, H / 2, 'left');
    drawArrow(ctx, W - 12, H / 2, 'right');
    drawText(ctx, '←→ 翻页　Esc 返回', W / 2, H - 18, '#a8b0d0', { align: 'center', shadow: '#000' });
  }
}
