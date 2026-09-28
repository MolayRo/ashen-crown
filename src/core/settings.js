// 设置：读写 localStorage，所有改动即时生效并持久保存
import { storage } from './storage.js';

const KEY = 'ashen.settings';

export const DEFAULTS = {
  masterVol: 80,      // 0..100
  musicVol: 70,
  sfxVol: 80,
  brightness: 100,    // 60..140
  pixelPerfect: true, // 整数倍缩放
  textSpeed: 2,       // 0 慢 1 中 2 快 3 瞬间
  battleAnim: 1,      // 1 完整演出 0 简略（地图）
  gameSpeed: 1,       // 0 普通 1 快速 2 极速（移动与演出速度）
  crt: true,
  crtStrength: 55,    // 0..100 扫描线/曲率/暗角
  crtGlow: 40,        // 0..100 荧光与色偏
  showGrid: false,
  autoCursor: true,   // 回合开始时光标移到王子
  confirmEnd: true,
};

export const settings = { ...DEFAULTS };

export function loadSettings() {
  const saved = storage.getJSON(KEY);
  if (saved && typeof saved === 'object') {
    for (const k of Object.keys(DEFAULTS)) {
      if (k in saved && typeof saved[k] === typeof DEFAULTS[k]) settings[k] = saved[k];
    }
  }
  return settings;
}

const listeners = new Set();
export function onSettingsChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function setSetting(key, value) {
  settings[key] = value;
  storage.setJSON(KEY, settings);
  for (const fn of listeners) fn(key, value);
}

export function resetSettings() {
  for (const k of Object.keys(DEFAULTS)) settings[k] = DEFAULTS[k];
  storage.setJSON(KEY, settings);
  for (const fn of listeners) fn('*', null);
}

// 帧数换算：动画速度设置对应的倍率
export function speedMul() {
  return [1, 1.6, 2.6][settings.gameSpeed] || 1;
}
