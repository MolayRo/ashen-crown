// 游戏对象：场景栈 + 淡入淡出 + 全局协程
import { TaskRunner } from './tasks.js';
import { fill } from './gfx.js';
import { W, H } from './renderer.js';

export class Game {
  constructor(renderer, input) {
    this.renderer = renderer;
    this.input = input;
    this.ctx = renderer.ctx;
    this.scenes = [];
    this.tasks = new TaskRunner();
    this.frame = 0;
    this.fadeLevel = 0;      // 0 透明 .. 1 全黑
    this.fadeTarget = 0;
    this.fadeSpeed = 0.08;
    this.fadeColor = '#000000';
    this.campaign = null;
    this.audio = null;
    this.toast = null;
  }

  top() { return this.scenes[this.scenes.length - 1]; }

  push(scene) {
    this.scenes.push(scene);
    scene.game = this;
    if (scene.enter) scene.enter(this);
    this.input.consumeAll();
    return scene;
  }

  pop() {
    const s = this.scenes.pop();
    if (s && s.exit) s.exit(this);
    const t = this.top();
    if (t && t.resume) t.resume(this);
    this.input.consumeAll();
    return s;
  }

  replace(scene) {
    while (this.scenes.length) {
      const s = this.scenes.pop();
      if (s.exit) s.exit(this);
    }
    return this.push(scene);
  }

  remove(scene) {
    const i = this.scenes.indexOf(scene);
    if (i >= 0) {
      this.scenes.splice(i, 1);
      if (scene.exit) scene.exit(this);
    }
  }

  // 淡出 → 回调 → 淡入
  *fadeTo(level, frames = 16, color = '#000000') {
    this.fadeColor = color;
    this.fadeTarget = level;
    this.fadeSpeed = Math.abs(level - this.fadeLevel) / Math.max(1, frames);
    while (Math.abs(this.fadeLevel - level) > 0.001) yield;
  }

  transition(fn, frames = 16) {
    const self = this;
    this.busyTransition = true;
    this.tasks.add((function* () {
      yield* self.fadeTo(1, frames);
      yield 2;
      fn();
      yield 2;
      yield* self.fadeTo(0, frames);
      self.busyTransition = false;
    })());
  }

  showToast(text, frames = 120) {
    this.toast = { text, t: frames };
  }

  update() {
    this.frame++;
    this.input.beginFrame();
    if (this.fadeLevel !== this.fadeTarget) {
      const d = this.fadeTarget - this.fadeLevel;
      this.fadeLevel += Math.sign(d) * Math.min(Math.abs(d), this.fadeSpeed || 0.08);
    }
    this.tasks.update();
    const top = this.top();
    // 过场淡入淡出进行中时不处理输入
    if (top && top.update) {
      if (this.busyTransition) this.input.consumeAll();
      top.update(this);
    }
    for (const s of this.scenes) if (s !== top && s.backgroundUpdate) s.backgroundUpdate(this);
    if (this.toast && --this.toast.t <= 0) this.toast = null;
    this.input.endFrame();
  }

  draw() {
    const ctx = this.ctx;
    // 找到最底层需要绘制的场景（覆盖层会画出下面的场景）
    let start = this.scenes.length - 1;
    while (start > 0 && this.scenes[start].overlay) start--;
    if (start < 0) { fill(ctx, 0, 0, W, H, '#000'); }
    for (let i = Math.max(0, start); i < this.scenes.length; i++) {
      const s = this.scenes[i];
      if (s.draw) s.draw(ctx, this);
    }
    if (this.toast) this.drawToast(ctx);
    if (this.fadeLevel > 0.001) {
      ctx.globalAlpha = Math.round(this.fadeLevel * 8) / 8;
      fill(ctx, 0, 0, W, H, this.fadeColor);
      ctx.globalAlpha = 1;
    }
  }

  drawToast(ctx) {
    if (this.toastDrawer) this.toastDrawer(ctx, this.toast);
  }
}
