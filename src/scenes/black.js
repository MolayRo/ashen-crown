// 纯黑底层（剧情播放时的背景占位）
import { W, H } from '../core/renderer.js';
import { fill } from '../core/gfx.js';

export class BlackScene {
  update() {}
  draw(ctx) { fill(ctx, 0, 0, W, H, '#07060b'); }
}
