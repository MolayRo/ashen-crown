# -*- coding: utf-8 -*-
"""
bgkit —— 《灰烬王冠》剧情背景 / 标题画面用的像素画小工具库（由 gen_backgrounds.py 调用）。

画法约定
  * 画面由若干「材质层」叠成：遮罩 mask + 标量场 t(0..1) + 色阶 ramp（暗→亮）。
    t 经 4x4 Bayer 有序抖动量化成色阶下标：色带中段是纯色，交界处是抖动过渡（SNES/GBA 过场质感）。
  * 光照不做半透明混合：火光 / 烛光 / 晨光写进 Canvas.light，作为 t 的加项让像素在色阶里“升档”，
    所以成图只含色阶里的颜色。
  * 剪影 = 纯色填充 + 朝光一侧 1px 轮廓光；外描边用 INK / 材质最暗色，不用纯黑。
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from palette import PAL, INK, INK2, hx  # noqa: E402

W, H = 320, 180


def rgb(c):
    if isinstance(c, str):
        c = hx(c)
    return (int(c[0]), int(c[1]), int(c[2]))


# ---------------------------------------------------------------------------
# 扩展色阶（仅背景使用；饱和度与明度层次对齐主调色板，均为暗→亮）
# ---------------------------------------------------------------------------
EXTRA = {
    # 夜空：深靛 → 蓝紫
    'night':    ['#10122a', '#161a36', '#1e2446', '#282f58', '#343c6c', '#444e82', '#5a6698', '#7a86b2'],
    # 黄昏：紫 → 绯红 → 橙 → 金
    'dusk':     ['#1a1030', '#2c1640', '#46204e', '#6a2a56', '#943a58', '#be5250', '#e07448', '#f4a050', '#ffcc6a'],
    # 晨曦：蓝灰 → 藕粉 → 金
    'dawn':     ['#1e2444', '#2e3a5e', '#465478', '#6a7090', '#9a8aa0', '#c8a0a0', '#eab89c', '#fad4a4', '#fff0cc'],
    # 阴天
    'overcast': ['#1a1e2a', '#262c3a', '#343c4c', '#465062', '#5c6678', '#76808e', '#929aa6', '#b0b6c0'],
    # 浓烟（暖灰）
    'smoke':    ['#141016', '#1e181f', '#2a2228', '#382e32', '#483c3e', '#5c4e4c', '#74645e'],
    # 白天天空
    'day':      ['#2e5a9e', '#3e6eb4', '#5486c8', '#6ea0da', '#8cbae6', '#aed0f0', '#d0e6f8'],
    # 雾 / 风雪天
    'mist':     ['#343c4e', '#4a5468', '#626c80', '#7e8898', '#9ca4b2', '#bcc2cc', '#dce0e8'],
    # 彩色玻璃
    'glass_r':  ['#3a0c18', '#7a1a2a', '#c03040', '#f07058'],
    'glass_b':  ['#0e1a48', '#1e3c88', '#3a6ad0', '#8ab8f8'],
    'glass_g':  ['#0e3020', '#1e6040', '#40a060', '#a0e090'],
    'glass_y':  ['#4a2a08', '#a06a10', '#f0b830', '#fff0a0'],
    'glass_v':  ['#240e40', '#4a2280', '#8050c0', '#c8a0f0'],
}
XPAL = {k: [rgb(c) for c in v] for k, v in EXTRA.items()}


def R(name, i=None):
    """取色阶（或其中一个颜色）。主调色板优先，其次本模块的扩展色阶。"""
    if name in PAL:
        ramp = [rgb(c) for c in PAL[name]]
    elif name in XPAL:
        ramp = XPAL[name]
    elif name == 'INK':
        ramp = [rgb(INK)]
    elif name == 'INK2':
        ramp = [rgb(INK2)]
    else:
        raise KeyError(name)
    if i is None:
        return ramp
    return ramp[max(0, min(len(ramp) - 1, i))]


def C(spec):
    """颜色简写：'INK' / 'INK2' / '#rrggbb' / '色阶名:下标' / (r,g,b)。"""
    if isinstance(spec, tuple):
        return tuple(int(v) for v in spec[:3])
    if spec == 'INK':
        return rgb(INK)
    if spec == 'INK2':
        return rgb(INK2)
    if spec.startswith('#'):
        return rgb(spec)
    name, i = spec.split(':')
    return R(name, int(i))


def rp(*specs):
    """拼一条自定义色阶（暗→亮），例如 rp('INK', 'stone:1', 'rock:3', 'fire:3')。"""
    out = []
    for s in specs:
        if isinstance(s, (list, tuple)) and s and isinstance(s[0], (list, tuple, str)):
            out.extend(C(x) for x in s)
        else:
            out.append(C(s))
    return out


def allowed_colors():
    """背景允许使用的全部颜色（主调色板 + 扩展色阶 + INK）。"""
    s = {rgb(INK), rgb(INK2)}
    for v in PAL.values():
        s.update(rgb(c) for c in v)
    for v in XPAL.values():
        s.update(v)
    return s


# ---------------------------------------------------------------------------
# 抖动
# ---------------------------------------------------------------------------
def _bayer(n):
    if n == 1:
        return np.array([[0]])
    b = _bayer(n // 2)
    return np.block([[4 * b, 4 * b + 2], [4 * b + 3, 4 * b + 1]])


B4 = (_bayer(4) + 0.5) / 16.0
B8 = (_bayer(8) + 0.5) / 64.0


def ramp_idx(t, n, th, soft=0.5):
    """把 0..1 的场量化成 n 级下标。soft=1 全程抖动；0.5 = 色带中段纯色、交界抖动；0 = 硬色带。"""
    f = np.clip(t, 0.0, 1.0) * (n - 1)
    i = np.floor(f)
    frac = f - i
    if soft <= 0:
        g = (frac >= 0.5).astype(float)
    else:
        g = np.clip((frac - (0.5 - soft / 2.0)) / soft, 0.0, 1.0)
    idx = i + (g > th)
    return np.clip(idx, 0, n - 1).astype(int)


# ---------------------------------------------------------------------------
# 画布
# ---------------------------------------------------------------------------
class Canvas:
    def __init__(self, w=W, h=H, color='INK'):
        self.w, self.h = w, h
        self.px = np.zeros((h, w, 3), np.uint8)
        self.px[:] = C(color)
        self.yy, self.xx = np.mgrid[0:h, 0:w]
        self.yy = self.yy.astype(float)
        self.xx = self.xx.astype(float)
        self.t4 = B4[self.yy.astype(int) % 4, self.xx.astype(int) % 4]
        self.t8 = B8[self.yy.astype(int) % 8, self.xx.astype(int) % 8]
        self.light = np.zeros((h, w))      # 全局光照场（火光/烛光/暗角），ramp() 自动叠加

    def full(self):
        return np.ones((self.h, self.w), bool)

    def fill(self, mask, color):
        self.px[mask] = C(color)

    def ramp(self, mask, t, ramp, soft=0.5, gain=1.0, th=None):
        """在 mask 内用色阶 ramp 按场 t 上色；t 会自动加上 gain * self.light。"""
        cols = np.array([C(c) for c in ramp], np.uint8)
        if mask is None:
            mask = self.full()
        if np.isscalar(t):
            t = np.full((self.h, self.w), float(t))
        tt = t + gain * self.light if gain else t
        idx = ramp_idx(tt, len(cols), self.t4 if th is None else th, soft)
        self.px[mask] = cols[idx[mask]]

    def ramp2(self, mask, t, ramp_a, ramp_b, mix, soft=0.5, gain=1.0):
        """两条等长色阶按 mix 场（0→A，1→B）逐像素抖动选用；用于“冷光 + 暖光”双光源。"""
        ca = np.array([C(c) for c in ramp_a], np.uint8)
        cb = np.array([C(c) for c in ramp_b], np.uint8)
        if mask is None:
            mask = self.full()
        if np.isscalar(t):
            t = np.full((self.h, self.w), float(t))
        tt = t + gain * self.light if gain else t
        idx = ramp_idx(tt, len(ca), self.t4, soft)
        # 用错位的 Bayer 阈值选色阶，避免与色带抖动同相
        th2 = np.roll(np.roll(self.t4, 2, axis=0), 1, axis=1)
        useb = np.clip(mix, 0, 1) > th2
        out = np.where(useb[..., None], cb[np.clip(idx, 0, len(cb) - 1)], ca[idx])
        self.px[mask] = out[mask]

    def dot(self, x, y, color):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y, x] = C(color)

    def get(self, x, y):
        return tuple(self.px[int(y), int(x)])

    def image(self):
        return Image.fromarray(self.px, 'RGB')

    def colors(self):
        return {tuple(int(v) for v in c) for c in np.unique(self.px.reshape(-1, 3), axis=0)}


def save_indexed(img_rgb, path):
    """按精确颜色存成调色板 PNG（体积小、保证不引入新颜色）。"""
    a = np.array(img_rgb.convert('RGB'))
    flat = a.reshape(-1, 3)
    cols, inv = np.unique(flat, axis=0, return_inverse=True)
    if len(cols) > 256:
        img_rgb.save(path)
        return
    p = Image.fromarray(inv.reshape(a.shape[:2]).astype(np.uint8), 'P')
    pal = cols.astype(np.uint8).flatten().tolist()
    pal += pal[:3] * (256 - len(cols))          # 空位用第一个颜色填充（调色板里也不出现纯黑）
    p.putpalette(pal)
    p.save(path, optimize=True)


# ---------------------------------------------------------------------------
# 遮罩（PIL 无抗锯齿光栅化；ss>1 时超采样后按覆盖率 ≥50% 二值化，形状更准）
# ---------------------------------------------------------------------------
class Mask:
    def __init__(self, w=W, h=H, ss=4):
        self.w, self.h, self.ss = w, h, ss
        self.img = Image.new('L', (w * ss, h * ss), 0)
        self.d = ImageDraw.Draw(self.img)

    def _p(self, pts):
        s = self.ss
        return [((x + 0.5) * s - 0.5, (y + 0.5) * s - 0.5) for x, y in pts]

    def poly(self, pts, v=255):
        if len(pts) >= 3:
            self.d.polygon(self._p(pts), fill=v)
        return self

    def rect(self, x0, y0, x1, y1, v=255):
        """含端点的像素矩形 [x0,x1]×[y0,y1]。"""
        s = self.ss
        self.d.rectangle([x0 * s, y0 * s, (x1 + 1) * s - 1, (y1 + 1) * s - 1], fill=v)
        return self

    def ellipse(self, cx, cy, rx, ry, v=255):
        s = self.ss
        self.d.ellipse([(cx - rx + 0.5) * s, (cy - ry + 0.5) * s, (cx + rx + 0.5) * s - 1, (cy + ry + 0.5) * s - 1], fill=v)
        return self

    def line(self, pts, width=1, v=255):
        s = self.ss
        self.d.line(self._p(pts), fill=v, width=max(1, int(round(width * s))))
        return self

    def get(self):
        a = np.array(self.img, dtype=np.float32)
        if self.ss > 1:
            a = a.reshape(self.h, self.ss, self.w, self.ss).mean(axis=(1, 3))
            return a >= 127.5
        return a > 0


def poly_mask(pts, ss=4, w=W, h=H):
    return Mask(w, h, ss).poly(pts).get()


def rect_mask(x0, y0, x1, y1, w=W, h=H):
    m = np.zeros((h, w), bool)
    x0, x1 = max(0, int(x0)), min(w - 1, int(x1))
    y0, y1 = max(0, int(y0)), min(h - 1, int(y1))
    if x1 >= x0 and y1 >= y0:
        m[y0:y1 + 1, x0:x1 + 1] = True
    return m


def ellipse_mask(cx, cy, rx, ry, w=W, h=H):
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx - cx) / max(rx, 0.01)) ** 2 + ((yy - cy) / max(ry, 0.01)) ** 2 <= 1.0


def height_mask(top, w=W, h=H):
    """列高度图 → 遮罩：每列 y >= top[x] 的像素为真。"""
    top = np.asarray(top, float)
    yy = np.arange(h)[:, None]
    return yy >= np.round(top)[None, :w]


# ---------------------------------------------------------------------------
# 形态学
# ---------------------------------------------------------------------------
def shift(m, dx, dy):
    """out[y, x] = m[y - dy, x - dx]（越界为 False）。"""
    out = np.zeros_like(m)
    h, w = m.shape
    ys0, ys1 = max(0, dy), min(h, h + dy)
    xs0, xs1 = max(0, dx), min(w, w + dx)
    out[ys0:ys1, xs0:xs1] = m[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
    return out


def edge(m, dx, dy):
    """m 中「(x+dx, y+dy) 处不在 m」的像素 —— 朝 (dx,dy) 方向的边。"""
    return m & ~shift(m, -dx, -dy)


def rim(m, dirs=((0, -1), (-1, 0))):
    """朝光方向的 1px 轮廓（默认左上光：上边 + 左边）。"""
    out = np.zeros_like(m)
    for dx, dy in dirs:
        out |= edge(m, dx, dy)
    return out


def outline(m, diag=False):
    """m 外侧一圈（4 邻域；diag=True 时 8 邻域）。"""
    o = shift(m, 1, 0) | shift(m, -1, 0) | shift(m, 0, 1) | shift(m, 0, -1)
    if diag:
        o |= shift(m, 1, 1) | shift(m, -1, 1) | shift(m, 1, -1) | shift(m, -1, -1)
    return o & ~m


def dilate(m, r=1):
    out = m.copy()
    for _ in range(r):
        out = out | shift(out, 1, 0) | shift(out, -1, 0) | shift(out, 0, 1) | shift(out, 0, -1)
    return out


def erode(m, r=1):
    return ~dilate(~m, r)


def clean(m):
    """去掉孤立像素（与四邻都不相连的点）。"""
    n = shift(m, 1, 0).astype(int) + shift(m, -1, 0) + shift(m, 0, 1) + shift(m, 0, -1)
    return m & (n > 0)


# ---------------------------------------------------------------------------
# 噪声
# ---------------------------------------------------------------------------
def _smooth(f):
    return f * f * (3 - 2 * f)


def noise1d(n, period, seed):
    rng = np.random.default_rng(seed)
    g = rng.uniform(-1, 1, int(n / period) + 3)
    x = np.arange(n) / period
    i = np.floor(x).astype(int)
    f = _smooth(x - i)
    return g[i] * (1 - f) + g[i + 1] * f


def fbm1d(n, period, seed, octaves=4, pers=0.5):
    out = np.zeros(n)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += amp * noise1d(n, max(1.0, period / (2 ** o)), seed + o * 101)
        tot += amp
        amp *= pers
    return out / tot


def noise2d(w, h, px, py, seed):
    rng = np.random.default_rng(seed)
    gw, gh = int(w / px) + 3, int(h / py) + 3
    g = rng.uniform(-1, 1, (gh, gw))
    ys, xs = np.mgrid[0:h, 0:w]
    x = xs / px
    y = ys / py
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = _smooth(x - x0)
    fy = _smooth(y - y0)
    a = g[y0, x0] * (1 - fx) + g[y0, x0 + 1] * fx
    b = g[y0 + 1, x0] * (1 - fx) + g[y0 + 1, x0 + 1] * fx
    return a * (1 - fy) + b * fy


def fbm2d(w, h, px, py, seed, octaves=4, pers=0.5):
    out = np.zeros((h, w))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s = 2 ** o
        out += amp * noise2d(w, h, max(1.0, px / s), max(1.0, py / s), seed + o * 131)
        tot += amp
        amp *= pers
    return out / tot


# ---------------------------------------------------------------------------
# 场
# ---------------------------------------------------------------------------
def vgrad(cv, y0, y1):
    """y0 处为 0，y1 处为 1 的竖直渐变。"""
    return (cv.yy - y0) / float(y1 - y0)


def radial(cv, cx, cy, r, aspect=1.0, power=1.0):
    """中心 1、半径 r 处 0 的径向光（aspect>1 横向拉长）。"""
    d = np.sqrt(((cv.xx - cx) / aspect) ** 2 + (cv.yy - cy) ** 2) / float(r)
    return np.clip(1 - d, 0, 1) ** power


def vignette(cv, strength=0.12, rx=0.62, ry=0.72):
    d = np.sqrt(((cv.xx - cv.w / 2) / (cv.w * rx)) ** 2 + ((cv.yy - cv.h / 2) / (cv.h * ry)) ** 2)
    return -strength * np.clip(d - 0.55, 0, 1) / 0.45


# ---------------------------------------------------------------------------
# 地形剪影
# ---------------------------------------------------------------------------
def ridge_line(n, base, amp, period, seed, octaves=4, sharp=0.0, pers=0.5):
    """山脊线：返回每列 y。sharp>0 时混入“脊形噪声”得到尖峰。"""
    f = fbm1d(n, period, seed, octaves, pers)
    if sharp:
        r = 1 - np.abs(fbm1d(n, period * 1.3, seed + 7, octaves, pers)) * 2
        f = f * (1 - sharp) + r * sharp
    return base - amp * f


def peaks_line(n, peaks, base, seed=0, rough=2.0):
    """由若干 (x, y顶, 半宽左, 半宽右) 山峰拼成山脊线，加细碎起伏。"""
    y = np.full(n, float(base))
    xs = np.arange(n)
    for (px, py, wl, wr) in peaks:
        left = py + (base - py) * np.clip((px - xs) / float(wl), 0, 1) ** 0.9
        right = py + (base - py) * np.clip((xs - px) / float(wr), 0, 1) ** 0.9
        prof = np.where(xs < px, left, right)
        y = np.minimum(y, prof)
    y += fbm1d(n, 6, seed, 3) * rough
    return y


def conifer_line(n, base, h_min, h_max, spacing, seed, jitter=0.5):
    """针叶林剪影：返回每列 y（锯齿三角树冠连成一片）。"""
    rng = np.random.default_rng(seed)
    y = np.full(n, float(base))
    x = -spacing
    xs = np.arange(n)
    while x < n + spacing:
        hh = rng.uniform(h_min, h_max)
        hw = hh * rng.uniform(0.28, 0.36)
        prof = base - hh + np.abs(xs - x) / hw * hh
        # 枝层锯齿
        prof += ((np.abs(xs - x) + (base - prof)) % 5 < 1.5) * 1.0
        y = np.minimum(y, prof)
        x += spacing * rng.uniform(1 - jitter, 1 + jitter)
    return y


def round_tree(m, x, base, h, seed, w=None):
    """阔叶树剪影：几团椭圆拼的树冠 + 树干。"""
    rng = np.random.default_rng(seed)
    w = w or h * 0.8
    mm = Mask(m.shape[1], m.shape[0], 4)
    cy = base - h * 0.62
    for _ in range(7):
        ox = rng.uniform(-0.32, 0.32) * w
        oy = rng.uniform(-0.25, 0.2) * h
        r = rng.uniform(0.22, 0.34) * w
        mm.ellipse(x + ox, cy + oy, r, r * 0.9)
    mm.rect(int(x - max(1, w * 0.05)), int(base - h * 0.35), int(x + max(1, w * 0.05)), int(base))
    return m | mm.get()


# ---------------------------------------------------------------------------
# 天空元素
# ---------------------------------------------------------------------------
def stars(cv, mask, n, seed, dim='night:6', mid='night:7', bright='snow:4', twinkle=0.04, ymax=None, bias=1.5):
    """星星：越往上越密。mask 外不画。"""
    rng = np.random.default_rng(seed)
    ymax = ymax or cv.h
    placed = 0
    tries = 0
    while placed < n and tries < n * 30:
        tries += 1
        x = int(rng.integers(0, cv.w))
        y = int(ymax * rng.random() ** bias)
        if y >= cv.h or not mask[y, x]:
            continue
        r = rng.random()
        if r < twinkle and 2 <= x < cv.w - 2 and 2 <= y < cv.h - 2 and mask[y - 1:y + 2, x - 1:x + 2].all():
            cv.dot(x, y, bright)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cv.dot(x + dx, y + dy, mid)
        elif r < 0.3:
            cv.dot(x, y, mid)
        else:
            cv.dot(x, y, dim)
        placed += 1


def moon(cv, cx, cy, r, colors=('dawn:8', 'snow:3', 'snow:2'), phase=0.0, sky_mask=None):
    """圆月 / 弯月。phase>0 时用偏移圆切出弯月（phase = 切口偏移比例）。"""
    body = ellipse_mask(cx, cy, r, r)
    if phase:
        cut = ellipse_mask(cx + r * phase, cy - r * phase * 0.35, r, r)
        body &= ~cut
    if sky_mask is not None:
        body &= sky_mask
    cv.fill(body, colors[0])
    # 月面斑
    sh = body & ellipse_mask(cx + r * 0.25, cy + r * 0.2, r * 0.35, r * 0.28)
    cv.fill(sh, colors[1])
    sh2 = body & ellipse_mask(cx - r * 0.3, cy - r * 0.35, r * 0.18, r * 0.15)
    cv.fill(sh2, colors[1])
    return body


def firework(cv, cx, cy, r, ramp_cols, seed, rays=16, dotstep=2, droop=0.25, trail=True, core=None):
    """烟花：放射状点线，外端最亮，末端下垂；ramp_cols 暗→亮。"""
    rng = np.random.default_rng(seed)
    cols = [C(c) for c in ramp_cols]
    n = len(cols)
    for k in range(rays):
        a = 2 * math.pi * (k + rng.uniform(-0.2, 0.2)) / rays
        rr = r * rng.uniform(0.8, 1.05)
        steps = int(rr / dotstep)
        for s in range(2, steps + 1):
            d = s * dotstep
            f = d / rr
            x = cx + math.cos(a) * d
            y = cy + math.sin(a) * d + droop * r * f * f
            ci = int(round((n - 1) * min(1.0, f ** 1.3 + 0.1)))
            if f < 0.45 and s % 2:
                continue
            cv.dot(x, y, cols[ci])
        # 末梢亮点
        x = cx + math.cos(a) * (rr + 1)
        y = cy + math.sin(a) * (rr + 1) + droop * r
        cv.dot(x, y, cols[-1])
    cv.dot(cx, cy, core or cols[-1])
    if trail:
        for i in range(3, int(r * 1.6), 3):
            cv.dot(cx + rng.integers(-1, 2) * 0, cy + r * 0.5 + i, cols[max(0, n - 3)])


# ---------------------------------------------------------------------------
# 火 / 烟 / 粒子
# ---------------------------------------------------------------------------
FIRE = ['fire:0', 'fire:1', 'fire:2', 'fire:3', 'fire:4']


def tongue(mm, bx, by, h, w, lean=0.0, wob=0.0, seed=0, ss_scale=1.0):
    """一条火舌多边形（底宽顶尖，可倾斜摆动）。"""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 6.28)
    left, right = [], []
    N = 12
    for i in range(N + 1):
        s = i / N
        cx = bx + lean * h * s ** 1.6 + wob * math.sin(ph + s * 5.0) * s
        hw = w * (1 - s) ** 0.75 * (1 + 0.15 * math.sin(ph * 1.7 + s * 9))
        y = by - h * s
        left.append((cx - hw, y))
        right.append((cx + hw, y))
    mm.poly(left + right[::-1])


def flames(cv, x0, x1, base, hmin, hmax, seed, lean=0.0, density=1.0, cols=FIRE, layers=(1.0, 0.72, 0.46, 0.22), mask=None):
    """一排像素火焰：每条火舌画 4 层（外红→橙→黄→芯）。返回火焰总遮罩。"""
    rng = np.random.default_rng(seed)
    n = max(1, int((x1 - x0) / 5 * density))
    tongues = []
    for i in range(n):
        bx = rng.uniform(x0, x1)
        edge_f = 1 - abs((bx - x0) / max(1, (x1 - x0)) - 0.5) * 2   # 中间高两边低
        h = rng.uniform(hmin, hmax) * (0.45 + 0.55 * edge_f)
        w = h * rng.uniform(0.2, 0.3) + 1.5
        tongues.append((bx, h, w, rng.uniform(-0.25, 0.25) + lean, rng.uniform(0.5, 2.0), int(rng.integers(1 << 30))))
    total = np.zeros((cv.h, cv.w), bool)
    cols_l = [cols[1], cols[2], cols[3], cols[4]]
    for li, sc in enumerate(layers):
        mm = Mask(cv.w, cv.h, 4)
        for (bx, h, w, ln, wob, sd) in tongues:
            tongue(mm, bx, base + 1, h * sc, w * (0.55 + 0.45 * sc), ln, wob * sc, sd)
        m = mm.get()
        if mask is not None:
            m &= mask
        if li == 0:
            total = m.copy()
            # 外焰边缘抖动一圈暗红
            o = outline(m) & (cv.yy < base + 1) & (cv.t4 > 0.55)
            if mask is not None:
                o &= mask
            cv.fill(o, cols[0])
        cv.fill(m, cols_l[li])
    return total


def smoke_field(cv, sx, sy, height, width0, width1, lean, seed, px=14, py=12, rough=0.35):
    """一股向上扩散的烟柱密度场（0..1+），源点 (sx,sy)，高 height。"""
    s = np.clip((sy - cv.yy) / float(height), 0, 1.2)
    cx = sx + lean * height * s ** 1.4
    wid = width0 + (width1 - width0) * s ** 0.8
    d = np.abs(cv.xx - cx) / np.maximum(wid, 1)
    n = fbm2d(cv.w, cv.h, px, py, seed, 4)
    dens = (1 - d) + n * rough * (0.6 + s)
    dens *= (cv.yy <= sy + 2)
    dens *= np.clip((1.15 - s) / 0.35, 0, 1)
    return dens


def embers(cv, n, seed, region, cols=('fire:2', 'fire:3', 'fire:4'), tail='fire:1', mask=None, big=0.15, wind=0.0):
    """飘升的余烬：亮点 + 下方 1px 暗尾（表示上升）。region=(x0,y0,x1,y1)。"""
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = region
    for _ in range(n):
        x = int(rng.uniform(x0, x1))
        y = int(rng.uniform(y0, y1))
        if not (0 <= x < cv.w and 0 <= y < cv.h):
            continue
        if mask is not None and not mask[y, x]:
            continue
        c = cols[int(rng.integers(0, len(cols)))]
        cv.dot(x, y, c)
        if rng.random() < 0.6:
            cv.dot(x - (1 if wind > 0 else (-1 if wind < 0 else 0)) * (rng.random() < abs(wind)), y + 1, tail)
        if rng.random() < big:
            cv.dot(x + 1, y, c)
            cv.dot(x, y + 1, tail)
            cv.dot(x + 1, y + 1, tail)


def snowfall(cv, n, seed, cols=('snow:2', 'snow:3', 'snow:4'), wind=1.0, streak=0.3, mask=None, region=None, big=0.2):
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = region or (0, 0, cv.w, cv.h)
    for _ in range(n):
        x = int(rng.uniform(x0, x1))
        y = int(rng.uniform(y0, y1))
        if not (0 <= x < cv.w and 0 <= y < cv.h):
            continue
        if mask is not None and not mask[y, x]:
            continue
        depth = rng.random()
        c = cols[min(len(cols) - 1, int(depth * len(cols)))]
        cv.dot(x, y, c)
        if depth > 1 - big:
            cv.dot(x + 1, y, c)
            cv.dot(x, y + 1, c)
            cv.dot(x + 1, y + 1, cols[max(0, len(cols) - 2)])
        elif rng.random() < streak:
            L = int(1 + depth * 3)
            for k in range(1, L + 1):
                cv.dot(x - k * wind, y - k * 0.5, cols[0])


def rain(cv, n, seed, col='mist:3', col2='mist:4', length=(4, 8), slope=0.35, mask=None, region=None):
    rng = np.random.default_rng(seed)
    x0, y0, x1, y1 = region or (0, 0, cv.w, cv.h)
    for _ in range(n):
        x = rng.uniform(x0, x1)
        y = rng.uniform(y0, y1)
        L = int(rng.integers(length[0], length[1] + 1))
        c = col2 if rng.random() < 0.25 else col
        for k in range(L):
            xx, yy = int(round(x - k * slope)), int(round(y - k))
            if 0 <= xx < cv.w and 0 <= yy < cv.h and (mask is None or mask[yy, xx]):
                cv.dot(xx, yy, c)


def bird(cv, x, y, col, size=1, flap=0):
    """远处飞鸟：小 V 字（size 1/2，flap 0/1 两种姿态）。"""
    x, y = int(x), int(y)
    if size == 1:
        pts = [(-2, -1), (-1, 0), (0, 1), (1, 0), (2, -1)] if flap == 0 else [(-2, 0), (-1, -1), (0, 0), (1, -1), (2, 0)]
    else:
        pts = [(-3, -2), (-2, -1), (-1, 0), (0, 1), (1, 0), (2, -1), (3, -2), (-4, -2), (4, -2)] if flap == 0 else \
              [(-3, 0), (-2, -1), (-1, -1), (0, 0), (1, -1), (2, -1), (3, 0), (0, 1)]
    for dx, dy in pts:
        cv.dot(x + dx, y + dy, col)


# ---------------------------------------------------------------------------
# 建筑剪影
# ---------------------------------------------------------------------------
def crenel_top(mm, x0, x1, y, merlon=3, gap=3, h=3):
    """城垛：在 y 线上方加一排齿。"""
    x = x0
    while x <= x1:
        mm.rect(int(x), int(y - h), int(min(x1, x + merlon - 1)), int(y))
        x += merlon + gap


def royal_castle(cx, base, s=1.0, ss=4, w=W, h=H, ruined=False):
    """白鹿城（全剧统一造型）：中央高主塔尖顶 + 两侧尖顶塔 + 主堡 + 城墙与外角楼。
    部件按「远→近」排列，逐个上色即可得到前后遮挡的轮廓光。
    返回 dict：mask, parts[{m, type(body/roof), x0, x1, cyl}], windows[(x,y,w,h)], tips[(x,y)], gate(x0,y0,x1,y1)"""
    def S(v):
        return v * s

    parts, tips, wins = [], [], []

    def body(x0, x1, y0, y1, crenel=False, cyl=False):
        mm = Mask(w, h, ss)
        mm.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        if crenel:
            crenel_top(mm, x0, x1, y0, merlon=max(2, round(S(4))), gap=max(1, round(S(3))), h=max(1, round(S(3))))
        parts.append({'m': mm.get(), 'type': 'body', 'x0': x0, 'x1': x1, 'cyl': cyl})

    def cone(xc, top, half, rh, spire=0):
        mm = Mask(w, h, ss)
        mm.poly([(xc - half, top + 0.5), (xc, top - rh), (xc + half, top + 0.5)])
        if spire:
            mm.rect(int(round(xc)), int(round(top - rh - spire)), int(round(xc)), int(round(top - rh)))
        parts.append({'m': mm.get(), 'type': 'roof', 'x0': xc - half, 'x1': xc + half, 'cyl': True})
        tips.append((int(round(xc)), int(round(top - rh - spire))))

    def ctower(xc, bw, top, rh, bottom, over=2.0, spire=0):
        body(xc - bw / 2, xc + bw / 2, top, bottom, cyl=True)
        if ruined:
            crenel_top_m = Mask(w, h, ss)
            crenel_top(crenel_top_m, xc - bw / 2, xc + bw / 2, top, merlon=max(1, round(S(3))), gap=max(1, round(S(3))), h=max(1, round(S(2))))
            parts.append({'m': crenel_top_m.get(), 'type': 'body', 'x0': xc - bw / 2, 'x1': xc + bw / 2, 'cyl': True})
        else:
            cone(xc, top, bw / 2 + S(over), rh, spire)

    B = base
    # 主塔（最远）+ 两侧小角塔
    ctower(cx, S(18), B + S(-80), S(34), B + S(-40), spire=max(1, round(S(6))))
    for sd in (-1, 1):
        ctower(cx + S(11) * sd, S(6), B + S(-70), S(9), B + S(-52), over=0.6)
    # 主堡
    body(cx + S(-30), cx + S(30), B + S(-50), B, crenel=True)
    # 内侧尖塔
    for sd in (-1, 1):
        ctower(cx + S(38) * sd, S(13), B + S(-58), S(22), B, spire=max(1, round(S(4))))
    # 城墙（最近的横向部件）
    body(cx + S(-72), cx + S(72), B + S(-22), B, crenel=True)
    # 外角楼
    for sd in (-1, 1):
        ctower(cx + S(70) * sd, S(15), B + S(-42), S(18), B)
    # 城门楼
    body(cx + S(-10), cx + S(10), B + S(-30), B, crenel=True)

    m = np.zeros((h, w), bool)
    for p in parts:
        m |= p['m']

    ww = max(1, round(S(2)))
    wh = max(1, round(S(3)))
    for (wx, wy) in [(-70, -34), (70, -34), (-70, -22), (70, -22), (-38, -50), (38, -50), (-38, -38), (38, -38),
                     (0, -74), (0, -62), (-4, -50), (4, -50),
                     (-22, -44), (-14, -44), (14, -44), (22, -44), (-22, -34), (22, -34),
                     (-58, -12), (-50, -12), (50, -12), (58, -12), (-28, -12), (28, -12)]:
        wins.append((int(round(cx + S(wx) - ww / 2)), int(round(B + S(wy))), ww, wh))
    gate = (int(round(cx - S(5))), int(round(B - S(14))), int(round(cx + S(5))), int(round(B)))
    return {'mask': m, 'parts': parts, 'windows': wins, 'tips': tips, 'gate': gate}


def flag(cv, x, y, col, col2=None, length=5, height=3, wave=0, pole='INK', pole_h=4):
    """塔尖小旗。"""
    for k in range(pole_h):
        cv.dot(x, y - k, pole)
    top = y - pole_h + 1
    for i in range(length):
        dy = (i + wave) // 3 % 2
        for j in range(height - (1 if i == length - 1 else 0)):
            cv.dot(x + 1 + i, top + j + dy, col2 if (col2 and j == height - 1) else col)


def house(mm_wall, mm_roof, x, base, w, wall_h, roof_h, over=2):
    """正面山墙式民居：墙体矩形 + 三角屋顶（分别画进两张遮罩）。返回 (x0, x1, 墙顶y, 屋脊y)。"""
    x0, x1 = x, x + w - 1
    top = base - wall_h
    mm_wall.rect(x0, top, x1, base)
    mm_roof.poly([(x0 - over, top + 1), ((x0 + x1) / 2.0, top - roof_h), (x1 + over, top + 1)])
    return x0, x1, top, top - roof_h


def side_house(mm_wall, mm_roof, x, base, w, wall_h, roof_h, over=2, slope=0.5):
    """侧面长屋：墙体 + 梯形屋顶（屋脊平行画面）。"""
    x0, x1 = x, x + w - 1
    top = base - wall_h
    mm_wall.rect(x0, top, x1, base)
    inset = roof_h * slope
    mm_roof.poly([(x0 - over, top + 1), (x0 + inset, top - roof_h), (x1 - inset, top - roof_h), (x1 + over, top + 1)])
    return x0, x1, top, top - roof_h


# ---------------------------------------------------------------------------
# 预览
# ---------------------------------------------------------------------------
def upscale(img, k):
    return img.resize((img.width * k, img.height * k), Image.NEAREST)


def contact_sheet(imgs, cols, scale=1, gap=4, bg=(24, 22, 32)):
    ws = [im.width * scale for im in imgs]
    hs = [im.height * scale for im in imgs]
    cw, ch = max(ws), max(hs)
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cw + (cols + 1) * gap, rows * ch + (rows + 1) * gap), bg)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        sheet.paste(upscale(im.convert('RGB'), scale), (gap + c * (cw + gap), gap + r * (ch + gap)))
    return sheet


def mock_overlay(img):
    """在背景上叠一个示意对白框和左右两个 80×80 头像框，检查构图是否被遮挡。"""
    im = img.convert('RGB').copy()
    d = ImageDraw.Draw(im)
    d.rectangle([6, 118, 313, 173], fill=(247, 236, 208), outline=(28, 16, 8))
    d.rectangle([7, 119, 312, 172], outline=(154, 116, 64))
    for x0 in (8, 232):
        d.rectangle([x0, 38, x0 + 79, 117], outline=(255, 80, 200))
        d.line([x0, 38, x0 + 79, 117], fill=(255, 80, 200))
    return im
