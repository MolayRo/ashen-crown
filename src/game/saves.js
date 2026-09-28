// 存档：3 个手动存档位 + 自动存档（关前）。数据存 localStorage。
import { storage } from '../core/storage.js';
import { Campaign } from './campaign.js';
import { CHAPTERS } from './data/chapters.js';

export const SLOT_IDS = ['1', '2', '3'];
const KEY = (slot) => 'ashen.save.' + slot;
export const STAGE_NAMES = { prologue: '序章', pre: '战前', prep: '整备', battle: '战斗中', post: '战后', ending: '结局', complete: '通关' };

export function describe(c, battle) {
  const ch = CHAPTERS[c.chapter];
  const chName = c.stage === 'prologue' ? '序章 庆典之夜' : ch ? `${ch.title} ${ch.name}` : '尾声';
  let stage = STAGE_NAMES[c.stage] || '';
  if (battle && c.stage === 'battle') stage = `第 ${battle.turn} 回合`;
  return { chapter: chName, stage };
}

export function makeSave(slot, campaign, battle = null) {
  return {
    v: 1,
    slot,
    time: Date.now(),
    label: describe(campaign, battle),
    playtime: Math.floor(campaign.playtime),
    difficulty: campaign.difficulty,
    mode: campaign.mode,
    lv: campaign.roster.elwin ? campaign.roster.elwin.lv : 1,
    campaign: campaign.toJSON(),
    battle: battle ? battle.toJSON() : null,
  };
}

export function writeSave(slot, campaign, battle = null) {
  const data = makeSave(slot, campaign, battle);
  const ok = storage.setJSON(KEY(slot), data);
  return ok !== false;
}

export function readSave(slot) {
  const d = storage.getJSON(KEY(slot));
  if (!d || !d.campaign) return null;
  return d;
}

export function listSaves() {
  return ['auto', ...SLOT_IDS].map((slot) => ({ slot, data: readSave(slot) }));
}

export function latestSave() {
  let best = null;
  for (const s of listSaves()) if (s.data && (!best || s.data.time > best.data.time)) best = s;
  return best;
}

export function hasAnySave() { return !!latestSave(); }

export function loadCampaign(data) {
  return Campaign.fromJSON(data.campaign);
}

export function fmtTime(sec) {
  sec = Math.floor(sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function fmtDate(t) {
  const d = new Date(t);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

// 通关记录
export function markCleared() { storage.setItem('ashen.cleared', '1'); }
export function hasCleared() { return storage.getItem('ashen.cleared') === '1'; }
