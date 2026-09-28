// 章节流程：开战、结算、战后处理（界面与自动测试共用）
import { CHAPTERS } from './data/chapters.js';
import { BattleState, rosterFromUnit, MAX_ITEMS } from './battle.js';
import { CHARACTERS } from './data/characters.js';
import { makeItem } from './data/items.js';

export function currentChapter(c) { return CHAPTERS[c.chapter] || null; }

export function beginBattle(c, opts = {}) {
  c.applyPendingDifficulty();
  const ch = currentChapter(c);
  c.stage = 'battle';
  return new BattleState(ch, c, opts);
}

// 胜利后写回：名册、仍存活的友军自动入队、休闲模式恢复撤退者、统计
export function completeChapter(c, state) {
  const ch = state.ch;
  state.finish();
  // 友军（绿色）存活到胜利 → 入队（第一章多兰被救下）
  for (const u of state.units) {
    if (u.team === 'ally' && !u.dead && CHARACTERS[u.id] && !c.isRecruited(u.id)) {
      c.addRecruit(u.id, { ...rosterFromUnit(u), hp: u.mhp });
      c.flags['rescued_' + u.id] = true;
    }
  }
  // 章节旗标
  for (const [k, v] of Object.entries(state.flags)) if (v) c.flags[ch.id + '_' + k] = true;
  const villages = Object.keys(ch.villages || {});
  const saved = villages.filter((k) => state.villages[k] === 'visited').length;
  const razed = villages.filter((k) => state.villages[k] === 'razed').length;
  c.flags[ch.id + '_villages_saved'] = saved;
  if (villages.length) {
    if (razed === 0) c.flags[ch.id + '_all_saved'] = true;
    if (razed > 0) c.flags[ch.id + '_some_razed'] = true;
  }
  c.flags[ch.id + '_turns'] = state.turn;
  c.flags[ch.id + '_clear'] = true;
  // 章节奖励（第四章：白鹿圣剑）
  if (ch.reward && !c.flags[ch.id + '_reward']) {
    c.flags[ch.id + '_reward'] = true;
    const r = c.roster[ch.reward.to];
    const item = makeItem(ch.reward.item);
    if (r && r.items.length < MAX_ITEMS) { r.items.unshift(item); r.equip = 0; } else c.convoy.push(item);
  }
  c.stage = 'post';
  return { saved, razed, turns: state.turn, gold: state.goldGained };
}

// 进入下一章（战后剧情播完之后）
export function advanceChapter(c) {
  c.chapter += 1;
  c.stage = c.chapter >= CHAPTERS.length ? 'ending' : 'pre';
}
