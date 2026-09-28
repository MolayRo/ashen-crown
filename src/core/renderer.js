// 渲染：所有画面先画到 320x180 的低分辨率画布，再由 WebGL 以最近邻放大到屏幕，
// 同一个着色器里做 CRT 效果（扫描线、屏幕曲率、暗角、色偏/荧光、荧光粉栅格）与亮度。
import { settings } from './settings.js';

export const W = 320;
export const H = 180;

const VS = `
attribute vec2 p;
varying vec2 uv;
void main() {
  uv = vec2(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5);
  gl_Position = vec4(p, 0.0, 1.0);
}`;

const FS = `
precision mediump float;
varying vec2 uv;
uniform sampler2D tex;
uniform vec2 src;
uniform float crtOn;
uniform float strength;
uniform float glow;
uniform float bright;
uniform float curv;

vec2 curve(vec2 u) {
  vec2 c = u - 0.5;
  float r2 = dot(c, c);
  c *= (1.0 + curv * r2) * (1.0 - curv * 0.25);
  return c + 0.5;
}
vec3 tap(vec2 u) { return texture2D(tex, u).rgb; }

void main() {
  if (crtOn < 0.5) {
    gl_FragColor = vec4(tap(uv) * bright, 1.0);
    return;
  }
  vec2 u = curve(uv);
  if (u.x < 0.0 || u.x > 1.0 || u.y < 0.0 || u.y > 1.0) {
    gl_FragColor = vec4(0.0, 0.0, 0.0, 1.0);
    return;
  }
  vec2 px = 1.0 / src;
  float ca = glow * 0.85 * px.x;
  vec3 col;
  col.r = tap(u + vec2(ca, 0.0)).r;
  col.g = tap(u).g;
  col.b = tap(u - vec2(ca, 0.0)).b;
  vec3 nb = (tap(u + vec2(px.x * 0.5, 0.0)) + tap(u - vec2(px.x * 0.5, 0.0))) * 0.5;
  col = mix(col, nb, 0.18 * strength);
  vec3 bl = (tap(u + vec2(px.x * 1.5, 0.0)) + tap(u - vec2(px.x * 1.5, 0.0))
           + tap(u + vec2(0.0, px.y * 1.5)) + tap(u - vec2(0.0, px.y * 1.5))) * 0.25;
  col += bl * bl * glow * 0.55;
  float fy = fract(u.y * src.y);
  float beam = 0.5 + 0.5 * cos((fy - 0.5) * 6.28318);
  float lum = dot(col, vec3(0.3, 0.55, 0.15));
  float sl = mix(1.0, 0.42 + 0.58 * beam, (0.3 + 0.55 * strength) * (1.0 - lum * 0.35));
  col *= sl;
  float m = mod(gl_FragCoord.x, 3.0);
  float ms = 0.12 * strength;
  vec3 mask = m < 1.0 ? vec3(1.0, 1.0 - ms, 1.0 - ms) : (m < 2.0 ? vec3(1.0 - ms, 1.0, 1.0 - ms) : vec3(1.0 - ms, 1.0 - ms, 1.0));
  col *= mask;
  vec2 vv = u * (1.0 - u);
  float vig = pow(clamp(vv.x * vv.y * 18.0, 0.0, 1.0), 0.12 + 0.38 * strength);
  col *= vig;
  col *= bright * (1.1 + 0.28 * strength);
  gl_FragColor = vec4(col, 1.0);
}`;

export class Renderer {
  constructor(display) {
    this.display = display;
    this.canvas = document.createElement('canvas');
    this.canvas.width = W;
    this.canvas.height = H;
    this.ctx = this.canvas.getContext('2d', { alpha: false });
    this.ctx.imageSmoothingEnabled = false;
    this.view = { x: 0, y: 0, w: W, h: H, dpr: 1 };
    this.gl = null;
    this.ctx2 = null;
    this._initGL();
    if (!this.gl) {
      this.ctx2 = display.getContext('2d');
    }
    this.resize();
    window.addEventListener('resize', () => this.resize());
    document.addEventListener('fullscreenchange', () => setTimeout(() => this.resize(), 30));
  }

  _initGL() {
    let gl = null;
    try {
      gl = this.display.getContext('webgl', { antialias: false, alpha: false, premultipliedAlpha: false, preserveDrawingBuffer: true });
    } catch (e) { gl = null; }
    if (!gl) return;
    const sh = (type, srcText) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, srcText);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.warn(gl.getShaderInfoLog(s));
        return null;
      }
      return s;
    };
    const vs = sh(gl.VERTEX_SHADER, VS);
    const fs = sh(gl.FRAGMENT_SHADER, FS);
    if (!vs || !fs) return;
    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { console.warn(gl.getProgramInfoLog(prog)); return; }
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, 'p');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.u = {};
    for (const n of ['tex', 'src', 'crtOn', 'strength', 'glow', 'bright', 'curv']) this.u[n] = gl.getUniformLocation(prog, n);
    gl.uniform1i(this.u.tex, 0);
    gl.uniform2f(this.u.src, W, H);
    this.gl = gl;
  }

  resize() {
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    const cw = Math.max(1, Math.round(window.innerWidth * dpr));
    const ch = Math.max(1, Math.round(window.innerHeight * dpr));
    this.display.width = cw;
    this.display.height = ch;
    let scale = Math.min(cw / W, ch / H);
    if (settings.pixelPerfect && !settings.crt && scale >= 1) scale = Math.floor(scale);
    const vw = Math.round(W * scale), vh = Math.round(H * scale);
    this.view = { x: Math.floor((cw - vw) / 2), y: Math.floor((ch - vh) / 2), w: vw, h: vh, dpr, cw, ch };
    if (this.ctx2) this.ctx2.imageSmoothingEnabled = false;
  }

  curvature() {
    return settings.crt ? (0.06 + 0.22 * settings.crtStrength / 100) : 0;
  }

  // 屏幕坐标（CSS 像素）→ 逻辑画布坐标，CRT 开启时套用与着色器相同的曲面变换
  toVirtual(clientX, clientY) {
    const r = this.display.getBoundingClientRect();
    const v = this.view;
    const dx = (clientX - r.left) * v.dpr - v.x;
    const dy = (clientY - r.top) * v.dpr - v.y;
    let ux = dx / v.w, uy = dy / v.h;
    if (settings.crt && this.gl) {
      const k = this.curvature();
      let cx = ux - 0.5, cy = uy - 0.5;
      const r2 = cx * cx + cy * cy;
      const f = (1 + k * r2) * (1 - k * 0.25);
      ux = cx * f + 0.5;
      uy = cy * f + 0.5;
    }
    return { x: ux * W, y: uy * H, inside: ux >= 0 && ux < 1 && uy >= 0 && uy < 1 };
  }

  present() {
    const gl = this.gl;
    const v = this.view;
    if (gl) {
      gl.viewport(0, 0, v.cw, v.ch);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.viewport(v.x, v.y, v.w, v.h);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, this.canvas);
      gl.uniform1f(this.u.crtOn, settings.crt ? 1 : 0);
      gl.uniform1f(this.u.strength, settings.crtStrength / 100);
      gl.uniform1f(this.u.glow, settings.crtGlow / 100);
      gl.uniform1f(this.u.bright, settings.brightness / 100);
      gl.uniform1f(this.u.curv, this.curvature());
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    } else {
      const c = this.ctx2;
      c.fillStyle = '#000';
      c.fillRect(0, 0, v.cw, v.ch);
      c.imageSmoothingEnabled = false;
      c.filter = settings.brightness !== 100 ? `brightness(${settings.brightness}%)` : 'none';
      c.drawImage(this.canvas, v.x, v.y, v.w, v.h);
      c.filter = 'none';
    }
  }
}
