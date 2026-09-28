// 输入：键盘 + 鼠标 + 触摸，统一成“动作”。每帧由主循环调用 input.endFrame() 清除边沿状态。
const KEYMAP = {
  ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down',
  ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right',
  KeyZ: 'confirm', Enter: 'confirm', NumpadEnter: 'confirm', Space: 'confirm',
  KeyX: 'cancel', Escape: 'cancel', Backspace: 'cancel',
  KeyC: 'info', KeyI: 'info',
  Tab: 'next', KeyQ: 'next',
  KeyR: 'threat',
  KeyM: 'menu',
  ShiftLeft: 'fast', ShiftRight: 'fast', KeyF: 'fast', ControlLeft: 'fast', ControlRight: 'fast',
  KeyL: 'log',
  KeyE: 'end',
};
const DIRS = ['up', 'down', 'left', 'right'];
const REPEAT_DELAY = 14;  // 帧
const REPEAT_RATE = 4;

export class Input {
  constructor(renderer, target) {
    this.renderer = renderer;
    this.held = new Set();
    this.down = new Set();     // 本帧按下
    this.holdFrames = {};
    this.mouse = { x: -1, y: -1, moved: false, inside: false, left: false, right: false, clicked: false, rclicked: false, wheel: 0, active: false, pressX: 0, pressY: 0 };
    this.lastDevice = 'keyboard';
    this.onFirstGesture = null;
    this.anyKey = false;
    this._gestured = false;
    this._touchTimer = null;
    this._touchStart = null;

    window.addEventListener('keydown', (e) => this._key(e, true));
    window.addEventListener('keyup', (e) => this._key(e, false));
    window.addEventListener('blur', () => { this.held.clear(); });
    target.addEventListener('contextmenu', (e) => e.preventDefault());
    target.addEventListener('pointermove', (e) => this._move(e));
    target.addEventListener('pointerdown', (e) => this._pdown(e));
    target.addEventListener('pointerup', (e) => this._pup(e));
    target.addEventListener('pointerleave', () => { this.mouse.inside = false; });
    target.addEventListener('wheel', (e) => { e.preventDefault(); this.mouse.wheel += Math.sign(e.deltaY); this.lastDevice = 'mouse'; }, { passive: false });
  }

  _gesture() {
    if (!this._gestured) {
      this._gestured = true;
      if (this.onFirstGesture) this.onFirstGesture();
    }
  }

  _key(e, isDown) {
    const act = KEYMAP[e.code];
    if (e.code === 'F11') return;
    if (act || e.code === 'Tab') e.preventDefault();
    if (isDown) {
      this._gesture();
      this.anyKey = true;
      this.lastDevice = 'keyboard';
    }
    if (!act) return;
    if (isDown) {
      if (!this.held.has(act)) {
        this.down.add(act);
        this.holdFrames[act] = 0;
      }
      this.held.add(act);
    } else {
      this.held.delete(act);
    }
  }

  _pos(e) {
    const p = this.renderer.toVirtual(e.clientX, e.clientY);
    this.mouse.x = Math.floor(p.x);
    this.mouse.y = Math.floor(p.y);
    this.mouse.inside = p.inside;
  }

  _move(e) {
    const ox = this.mouse.x, oy = this.mouse.y;
    this._pos(e);
    if (this.mouse.x !== ox || this.mouse.y !== oy) {
      this.mouse.moved = true;
      this.mouse.active = true;
      if (e.pointerType !== 'touch') this.lastDevice = 'mouse';
    }
    if (this._touchStart && e.pointerType === 'touch') {
      const dx = e.clientX - this._touchStart.x, dy = e.clientY - this._touchStart.y;
      if (dx * dx + dy * dy > 200) { clearTimeout(this._touchTimer); this._touchTimer = null; }
    }
  }

  _pdown(e) {
    this._gesture();
    this._pos(e);
    this.mouse.active = true;
    this.lastDevice = e.pointerType === 'touch' ? 'touch' : 'mouse';
    if (e.pointerType === 'touch') {
      // 长按 = 取消（右键）
      this._touchStart = { x: e.clientX, y: e.clientY, t: performance.now() };
      clearTimeout(this._touchTimer);
      this._touchTimer = setTimeout(() => {
        this._touchTimer = null;
        this._touchStart = null;
        this.mouse.rclicked = true;
      }, 550);
      this.mouse.moved = true;
      return;
    }
    // 点击时光标立即对准指针位置（即使之前没有移动事件）
    this.mouse.moved = true;
    if (e.button === 0) { this.mouse.left = true; this.mouse.pressX = this.mouse.x; this.mouse.pressY = this.mouse.y; }
    if (e.button === 2) this.mouse.right = true;
    if (e.button === 1) { e.preventDefault(); this.down.add('info'); }
  }

  _pup(e) {
    this._pos(e);
    if (e.pointerType === 'touch') {
      if (this._touchTimer) {
        clearTimeout(this._touchTimer);
        this._touchTimer = null;
        this.mouse.clicked = true;
      }
      this._touchStart = null;
      return;
    }
    if (e.button === 0) { if (this.mouse.left) this.mouse.clicked = true; this.mouse.left = false; }
    if (e.button === 2) { if (this.mouse.right) this.mouse.rclicked = true; this.mouse.right = false; }
  }

  // 每帧开始时调用：更新长按计数
  beginFrame() {
    for (const a of this.held) this.holdFrames[a] = (this.holdFrames[a] || 0) + 1;
  }

  pressed(a) { return this.down.has(a); }
  isHeld(a) { return this.held.has(a); }

  // 方向键带自动连发
  repeat(a) {
    if (this.down.has(a)) return true;
    if (!this.held.has(a)) return false;
    const f = this.holdFrames[a] || 0;
    return f > REPEAT_DELAY && (f - REPEAT_DELAY) % REPEAT_RATE === 0;
  }

  dir() {
    for (const d of DIRS) if (this.repeat(d)) return d;
    return null;
  }

  confirm() { return this.down.has('confirm'); }
  cancel() { return this.down.has('cancel') || this.mouse.rclicked; }
  click() { return this.mouse.clicked; }
  fast() { return this.held.has('fast'); }

  consume(a) { this.down.delete(a); if (a === 'click') this.mouse.clicked = false; if (a === 'rclick') this.mouse.rclicked = false; }
  consumeAll() {
    this.down.clear();
    this.mouse.clicked = false;
    this.mouse.rclicked = false;
    this.mouse.wheel = 0;
    this.anyKey = false;
  }

  endFrame() {
    this.down.clear();
    this.mouse.clicked = false;
    this.mouse.rclicked = false;
    this.mouse.moved = false;
    this.mouse.wheel = 0;
    this.anyKey = false;
  }
}
