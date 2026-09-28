// 无头战役模拟：我方由自动操作控制，逐章打通，统计胜率与关键数据
// 用法：node tools/tests/sim.mjs [难度 normal] [局数 20] [模式 classic] [--verbose]
import { Campaign } from '../../src/game/campaign.js';
import { CHAPTERS } from '../../src/game/data/chapters.js';
import { beginBattle, completeChapter, advanceChapter } from '../../src/game/flow.js';
import { autoPlayerPhase, autoPrep } from '../../src/game/autoplay.js';

const diff = process.argv[2] || 'normal';
const runs = parseInt(process.argv[3] || '20', 10);
const mode = process.argv[4] || 'classic';
const verbose = process.argv.includes('--verbose');

function runChapter(c, seed) {
  const s = beginBattle(c, { seed });
  s.begin();
  s.queue.length = 0;
  let guard = 0;
  while (!s.outcome && s.turn <= 40 && guard++ < 200) {
    s.startPlayerPhase === undefined;
    autoPlayerPhase(s);
    if (s.outcome) break;
    s.endPlayerPhase();
    let plan;
    let g2 = 0;
    while (!s.outcome && (plan = s.nextAi()) && g2++ < 200) s.applyAi(plan);
    if (s.outcome) break;
    let ph = s.endEnemyPhase();
    if (ph === 'ally') {
      while (!s.outcome && (plan = s.nextAi())) s.applyAi(plan);
      if (s.outcome) break;
      s.nextTurn();
    }
    s.queue.length = 0;
  }
  return s;
}

const retriesArg = process.argv.find((a) => a.startsWith('--retries='));
const retries = retriesArg ? parseInt(retriesArg.split('=')[1], 10) : 0;
let retryCount = 0;
const tally = CHAPTERS.map(() => ({ win: 0, lose: 0, turns: 0, reasons: {} }));
let fullClears = 0;
const recruitStats = {};
const deathStats = {};
for (let r = 0; r < runs; r++) {
  const c = Campaign.newGame(diff, mode);
  c.stage = 'pre';
  let ok = true;
  for (let i = 0; i < CHAPTERS.length; i++) {
    c.chapter = i;
    autoPrep(c, CHAPTERS[i]);
    // 像玩家一样：失败后读取关前存档重打（--retries=N）
    const snap = JSON.stringify(c.toJSON());
    let s = null;
    for (let attempt = 0; attempt <= retries; attempt++) {
      if (attempt > 0) {
        const fresh = Campaign.fromJSON(JSON.parse(snap));
        Object.assign(c, fresh);
        retryCount++;
      }
      s = runChapter(c, 1000 + r * 17 + i + attempt * 7919);
      if (s.outcome === 'victory') break;
    }
    const t = tally[i];
    if (s.outcome === 'victory') {
      t.win++; t.turns += s.turn;
      completeChapter(c, s);
      advanceChapter(c);
    } else {
      t.lose++;
      const why = s.outcome ? s.defeatReason : 'timeout';
      t.reasons[why] = (t.reasons[why] || 0) + 1;
      ok = false;
      if (verbose) {
        console.log(`#${r} ${CHAPTERS[i].id} 失败(${why}) 回合 ${s.turn}`);
        for (const u of s.units.filter((x) => x.team === 'player')) console.log('   ', u.name, u.lv, u.hp + '/' + u.mhp, u.dead ? '阵亡' : '', u.x, u.y);
      }
      break;
    }
  }
  if (ok) fullClears++;
  for (const id of c.recruited) recruitStats[id] = (recruitStats[id] || 0) + 1;
  for (const id of c.dead) deathStats[id] = (deathStats[id] || 0) + 1;
  if (verbose && ok) console.log(`#${r} 通关  等级：` + c.available().map((id) => `${c.roster[id].name}${c.roster[id].lv}`).join(' '));
}
console.log(`难度 ${diff} 模式 ${mode}  共 ${runs} 局  全通关 ${fullClears}` + (retries ? `（每章失败最多重打 ${retries} 次，共重打 ${retryCount} 次）` : ''));
tally.forEach((t, i) => {
  const n = t.win + t.lose;
  console.log(`${CHAPTERS[i].id}: 胜 ${t.win}/${n}  平均回合 ${t.win ? (t.turns / t.win).toFixed(1) : '-'}  失败原因 ${JSON.stringify(t.reasons)}`);
});
console.log('招募次数', JSON.stringify(recruitStats));
console.log('阵亡次数', JSON.stringify(deathStats));
