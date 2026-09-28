// 流程控制：新游戏 → 序章 → 各章（战前剧情 → 整备 → 战斗 → 战后剧情）→ 结局
import { Campaign } from '../game/campaign.js';
import { CHAPTERS } from '../game/data/chapters.js';
import { BattleState } from '../game/battle.js';
import { beginBattle, completeChapter, advanceChapter, currentChapter } from '../game/flow.js';
import { writeSave, loadCampaign, markCleared } from '../game/saves.js';
import { hasScript } from '../game/story/index.js';
import { audio } from '../core/audio.js';
import { StoryScene } from './story.js';
import { BlackScene } from './black.js';

let scenes = null;
// 场景类在 main.js 中注册，避免循环依赖
export function registerScenes(s) { scenes = s; }

export function playScripts(game, ids, onDone, opts = {}) {
  const list = ids.filter((id) => id && hasScript(id));
  const next = () => {
    const id = list.shift();
    if (!id) { onDone && onDone(); return; }
    game.replace(new BlackScene());
    game.push(new StoryScene(id, { campaign: game.campaign, onDone: next, ...opts }));
  };
  next();
}

export function newGame(game, difficulty, mode) {
  const c = Campaign.newGame(difficulty, mode);
  game.campaign = c;
  c.stage = 'prologue';
  game.transition(() => goStage(game));
}

export function goStage(game) {
  const c = game.campaign;
  const ch = currentChapter(c);
  switch (c.stage) {
    case 'prologue':
      playScripts(game, ['prologue', 'interlude_proclaim'], () => {
        c.stage = 'pre';
        c.chapter = 0;
        goStage(game);
      });
      break;
    case 'pre':
      playScripts(game, [ch.pre], () => {
        c.stage = ch.prep ? 'prep' : 'battle';
        autosave(game);
        goStage(game);
      });
      break;
    case 'prep':
      game.transition(() => game.replace(new scenes.PrepScene()));
      break;
    case 'battle': {
      game.transition(() => startBattle(game));
      break;
    }
    case 'post':
      playScripts(game, [ch.post, ch.after], () => {
        advanceChapter(c);
        if (c.stage === 'ending') goStage(game);
        else {
          goStage(game);
        }
      });
      break;
    case 'ending':
      playScripts(game, ['ending'], () => {
        c.stage = 'complete';
        markCleared();
        writeSave('auto', c, null);
        game.transition(() => game.replace(new scenes.CreditsScene({ ending: true })));
      });
      break;
    default:
      toTitle(game);
  }
}

// 开战：保存本章开局快照（用于“重新开始本章”）
export function startBattle(game, restoredBattle = null) {
  const c = game.campaign;
  let state = restoredBattle;
  if (!state) {
    c.stage = 'battle';
    game.chapterSnapshot = JSON.stringify(c.toJSON());
    state = beginBattle(c);
  } else if (!game.chapterSnapshot) {
    game.chapterSnapshot = null;
  }
  game.replace(new scenes.MapScene(state, { fresh: !restoredBattle }));
}

export function autosave(game) {
  writeSave('auto', game.campaign, null);
}

export function battleWon(game, state) {
  const c = game.campaign;
  const res = completeChapter(c, state);
  game.lastResult = res;
  goStage(game);
}

export function restartChapter(game) {
  if (game.chapterSnapshot) {
    game.campaign = Campaign.fromJSON(JSON.parse(game.chapterSnapshot));
    game.campaign.stage = 'battle';
    game.transition(() => startBattle(game));
  } else {
    toTitle(game);
  }
}

export function loadFromSave(game, data) {
  const c = loadCampaign(data);
  game.campaign = c;
  game.chapterSnapshot = null;
  audio.stopMusic(0.6);
  if (c.stage === 'battle' && data.battle) {
    const ch = CHAPTERS.find((x) => x.id === data.battle.chapterId) || currentChapter(c);
    const state = BattleState.fromJSON(data.battle, ch, c);
    game.transition(() => game.replace(new scenes.MapScene(state, { fresh: false })));
    return;
  }
  if (c.stage === 'complete') { game.transition(() => game.replace(new scenes.TitleScene())); return; }
  game.transition(() => goStage(game));
}

export function toTitle(game) {
  audio.stopMusic(0.8);
  game.transition(() => game.replace(new scenes.TitleScene()));
}
